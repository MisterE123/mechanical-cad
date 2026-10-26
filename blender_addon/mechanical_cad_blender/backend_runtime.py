"""One main-thread backend lifetime/generation for production evidence owners.

This module holds no scene, native process, execution lease or saved data. The
existing Blender lifecycle installs one invalidation callback that retires its
own pending and completed evidence. Generation changes precede that callback,
so failed cleanup or publication rollback cannot revive old authority.
"""

from __future__ import annotations

import math
import sys
import threading
import uuid
from dataclasses import replace

from . import bridge
from .backend_selection import BackendSelection, SelectionError, default_timeout_seconds
from .runtime_bundle_launch import LAUNCH_CONSTANT_FIELDS, capture_bundled_policy
from .runtime_bundle_manifest import BundleLimits
from .runtime_bundle_prepare import BundlePreparationJob

_LIFETIME = uuid.uuid4().hex
_GENERATION = 0
_OBSERVED = None
_INVALIDATE = None
_BUNDLE_REQUIRED = False
_BUNDLE_ENABLED = False
_BUNDLE_JOB = None
_BUNDLE_JOB_REQUEST = None
_BUNDLE_REQUEST = None
_BUNDLE_POLICY = None
_BUNDLE_STATE = "external"
_BUNDLE_MESSAGE = "External development backend; configure its paths explicitly."


def bundled_mode():
    """A manifest extension never falls back to external preferences or MCAD_* ."""
    _main_thread()
    return _BUNDLE_REQUIRED


def bundle_status():
    """Bounded presentation only: no polling, hashing, path inspection or launch."""
    _main_thread()
    return _BUNDLE_STATE, _BUNDLE_MESSAGE


def _bundle_capture(package_root, cache_root, constants):
    # Generated installed Python literals, not model data. Detach the dictionary
    # before any worker starts. Full constant/descriptor checks follow cleanup.
    if type(constants) is not dict or set(constants) != set(LAUNCH_CONSTANT_FIELDS):
        raise ValueError("Installed extension launch constants are incomplete.")
    captured = {}
    for name in LAUNCH_CONSTANT_FIELDS:
        value = constants[name]
        if type(value) in (str, bytes):
            if len(value) > 16384:
                raise ValueError("Installed extension launch constant is oversized.")
        elif type(value) is tuple:
            if len(value) > 8 or any(type(v) not in (str, int) for v in value):
                raise ValueError("Installed extension launch tuple is malformed.")
            if any(type(v) is str and len(v) > 128 for v in value):
                raise ValueError("Installed extension launch tuple is oversized.")
        elif type(value) is not int:
            raise ValueError("Installed extension launch constants must be literals.")
        captured[name] = value
    release = captured["RELEASE_IDENTITY_BYTES"]
    if type(release) is not bytes or not 0 < len(release) <= 16384:
        raise ValueError("Installed extension release identity is malformed.")
    if sys.platform == "win32" and captured["PLATFORM"] == "windows-x64":
        if cache_root is not None:
            raise ValueError("Windows bundled setup requires its automatic OS cache provider.")
        return package_root, None, release, captured
    if sys.platform != "linux" or captured["PLATFORM"] != "linux-x64":
        raise ValueError(
            "This bundled backend is not qualified for this platform. "
            "Windows support requires a separately verified Windows extension."
        )
    return package_root, cache_root, release, captured


def _bundle_failure(message):
    global _BUNDLE_STATE, _BUNDLE_MESSAGE, _BUNDLE_POLICY, _BUNDLE_REQUEST
    _BUNDLE_POLICY, _BUNDLE_REQUEST = None, None
    _BUNDLE_STATE = "failed"
    _BUNDLE_MESSAGE = message[:1500]


def fail_bundled_setup(message):
    """Missing generated metadata/path failures remain a closed extension mode."""
    global _BUNDLE_REQUIRED, _BUNDLE_ENABLED
    _main_thread()
    _BUNDLE_REQUIRED, _BUNDLE_ENABLED = True, False
    if _BUNDLE_JOB is not None:
        _BUNDLE_JOB.cancel()
    _bundle_failure(message if type(message) is str else "Bundled backend setup failed.")
    revoke("Bundled backend is unavailable; current evidence was revoked.")


def begin_bundled_setup(package_root, cache_root, constants):
    """Enable automatic offline setup without waiting or touching runtime files.

    An old cancelling/uncertain owner is retained across disable/re-enable. A new
    worker may start only after that original owner reports confirmed cleanup.
    """
    global _BUNDLE_REQUIRED, _BUNDLE_ENABLED, _BUNDLE_REQUEST, _BUNDLE_POLICY
    global _BUNDLE_STATE, _BUNDLE_MESSAGE
    _main_thread()
    _BUNDLE_REQUIRED, _BUNDLE_ENABLED, _BUNDLE_POLICY = True, True, None
    _BUNDLE_REQUEST = None
    if _BUNDLE_JOB is not None:
        _BUNDLE_JOB.cancel()
    _BUNDLE_STATE, _BUNDLE_MESSAGE = "preparing", "Preparing the bundled backend offline…"
    # State is closed before callbacks: a reentrant currentness read cannot use
    # the old policy even if owner invalidation raises.
    revoke("Bundled backend setup changed; current evidence was revoked.")
    try:
        _BUNDLE_REQUEST = _bundle_capture(package_root, cache_root, constants)
    except (TypeError, ValueError) as exc:
        _bundle_failure(str(exc))
    return poll_bundled_setup()


def stop_bundled_setup():
    """Revoke setup policy and cancel, without dropping or joining its owner."""
    global _BUNDLE_ENABLED, _BUNDLE_POLICY, _BUNDLE_REQUEST
    global _BUNDLE_STATE, _BUNDLE_MESSAGE
    _main_thread()
    if not _BUNDLE_REQUIRED:
        return
    _BUNDLE_ENABLED, _BUNDLE_POLICY, _BUNDLE_REQUEST = False, None, None
    _BUNDLE_STATE, _BUNDLE_MESSAGE = "disabled", "Bundled backend is disabled."
    if _BUNDLE_JOB is not None:
        _BUNDLE_JOB.cancel()
    revoke("Bundled backend disabled; current evidence was revoked.")


def poll_bundled_setup():
    """Main-thread timer seam. Return whether another bounded poll is needed."""
    global _BUNDLE_JOB, _BUNDLE_JOB_REQUEST, _BUNDLE_REQUEST, _BUNDLE_POLICY
    global _BUNDLE_STATE, _BUNDLE_MESSAGE
    _main_thread()
    if not _BUNDLE_ENABLED:
        return False
    if _BUNDLE_JOB is not None:
        state = _BUNDLE_JOB.poll()
        if state == "cleanup_blocked":
            _BUNDLE_POLICY, _BUNDLE_REQUEST = None, None
            _BUNDLE_STATE = "cleanup_blocked"
            _BUNDLE_MESSAGE = (
                "Bundled backend cleanup could not be confirmed. "
                "Save your work and restart Blender; no backend operation is allowed."
            )
            return False
        if not _BUNDLE_JOB.done:
            return True
        job = _BUNDLE_JOB
        request = _BUNDLE_JOB_REQUEST
        _BUNDLE_JOB = None  # Only after the original owner confirms cleanup.
        _BUNDLE_JOB_REQUEST = None
        if _BUNDLE_REQUEST is request and request is not None:
            try:
                descriptor = job.result()
                package, cache, release, constants = _BUNDLE_REQUEST
                location = (
                    job.windows_cache_location if constants["PLATFORM"] == "windows-x64" else None
                )
                if constants["PLATFORM"] == "windows-x64":
                    if location is None:
                        raise ValueError("Windows setup did not return its guarded cache binding.")
                    cache = location.cache_root
                policy = capture_bundled_policy(
                    descriptor,
                    package_root=package,
                    cache_root=cache,
                    release_data=release,
                    constants=constants,
                    windows_cache=location,
                )
            except (ValueError, RuntimeError, OSError, TypeError) as exc:
                _bundle_failure("Bundled backend setup failed: " + str(exc))
                return False
            else:
                _BUNDLE_REQUEST = None
                try:
                    revoke("Bundled backend became ready; request fresh CAD evidence.")
                except Exception:
                    _bundle_failure(
                        "Bundled backend owner invalidation failed. "
                        "Save your work and restart Blender before retrying."
                    )
                    return False
                _BUNDLE_POLICY = policy
                _BUNDLE_STATE, _BUNDLE_MESSAGE = "ready", "Bundled backend ready."
                return False
        else:
            # An explicit newer enable request superseded this job. Consume
            # only to discard its cleanup-confirmed result; never bind an old
            # descriptor to new package/cache/constants or automatically retry.
            try:
                job.result()
            except (ValueError, RuntimeError, OSError, TypeError):
                pass
    if _BUNDLE_REQUEST is None:
        return False
    package, cache, release, constants = _BUNDLE_REQUEST
    try:
        # Constructor captures bounded primitives only. Hashing and extraction
        # run on its single worker; no CAD lease or native process is created.
        if constants["PLATFORM"] == "windows-x64":
            _BUNDLE_JOB = BundlePreparationJob.for_bundled_windows(
                package, release, limits=BundleLimits()
            )
        else:
            _BUNDLE_JOB = BundlePreparationJob(
                package,
                cache,
                release,
                expected_platform=constants["PLATFORM"],
                limits=BundleLimits(),
            )
        _BUNDLE_JOB_REQUEST = _BUNDLE_REQUEST
        _BUNDLE_JOB.start()
    except (ValueError, RuntimeError, OSError, TypeError) as exc:
        _bundle_failure("Bundled backend preparation could not start: " + str(exc))
        return False
    return True


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise bridge.BridgeError("Backend evidence ownership requires Blender's main thread.")


def stamp():
    """Runtime-only epoch/revision; never serialize it into authored data."""
    _main_thread()
    return _LIFETIME, _GENERATION


def configure_invalidation(callback):
    """Install the single existing-lifecycle hook, not another owner registry."""
    global _INVALIDATE
    _main_thread()
    if callback is not None and not callable(callback):
        raise TypeError("Backend invalidation hook must be callable or None.")
    _INVALIDATE = callback


def _notify(reason):
    if _INVALIDATE is not None:
        _INVALIDATE(reason)


def revoke(reason="Backend settings changed; verify the current CAD data again."):
    """Revoke first, then notify owners. A→B→A always advances twice."""
    global _GENERATION, _OBSERVED
    _main_thread()
    _GENERATION += 1
    _OBSERVED = None
    _notify(reason)
    return stamp()


def new_lifetime(reason="Backend runtime restarted; saved reports are historical."):
    """A fresh unrepeatable epoch on registration/reload, without lease reset."""
    global _LIFETIME, _GENERATION, _OBSERVED
    _main_thread()
    _LIFETIME, _GENERATION, _OBSERVED = uuid.uuid4().hex, 0, None
    _notify(reason)
    return stamp()


def _preferences(context):
    try:
        addons = context.preferences.addons
    except (AttributeError, ReferenceError) as exc:
        raise bridge.BridgeError("Backend preferences are unavailable in this context.") from exc
    addon = addons.get(__package__)
    return addon.preferences if addon is not None else None


def _settings_key(selection, deflection):
    return (
        selection.project_root,
        selection.python_executable,
        selection.python_executable_target,
        selection.timeout,
        tuple(sorted(selection.launch_environment().items())),
        selection.bundled_policy,
        deflection,
    )


def configuration(context):
    """Capture settings once; an observed effective change revokes old evidence.

    The captured selection, not a later recapture, is passed to process launch.
    Environment defaults are observed at explicit owner boundaries. This does
    not detect arbitrary environment A→B→A between those observations.
    """
    global _GENERATION, _OBSERVED
    _main_thread()
    try:
        preferences = _preferences(context)
        deflection = float(preferences.linear_deflection if preferences else 0.1)
        if not math.isfinite(deflection):
            raise ValueError("Mesh tolerance must be finite.")
        if _BUNDLE_REQUIRED:
            if not _BUNDLE_ENABLED or _BUNDLE_POLICY is None:
                raise bridge.BridgeError(_BUNDLE_MESSAGE)
            selection = BackendSelection.capture_bundled(
                _BUNDLE_POLICY,
                preferences.timeout_seconds
                if preferences is not None
                else default_timeout_seconds(bundled_platform=_BUNDLE_POLICY.constants.PLATFORM),
                generation=_GENERATION,
                lifetime_id=_LIFETIME,
            )
        else:
            selection = BackendSelection.capture(
                preferences.project_root if preferences else "",
                preferences.python_executable if preferences else "",
                preferences.timeout_seconds if preferences else 60.0,
                generation=_GENERATION,
                lifetime_id=_LIFETIME,
            )
    except (
        ValueError,
        OSError,
        ReferenceError,
        AttributeError,
        TypeError,
        bridge.BridgeError,
    ) as exc:
        # A once-observed valid selection becoming unavailable is itself a
        # revocation. Repeated drawing while invalid must not advance forever.
        if _OBSERVED is not None:
            revoke("Backend settings are unavailable; current evidence was revoked.")
        raise bridge.BridgeError(str(exc)) from exc
    key = _settings_key(selection, deflection)
    if _OBSERVED is not None and _OBSERVED != key:
        _GENERATION += 1
        selection = replace(selection, generation=_GENERATION)
        # Store before notifying: a current-evidence UI predicate may recapture
        # from inside invalidation without recursive generation changes.
        _OBSERVED = key
        _notify("Effective backend settings changed; verify current CAD data again.")
    else:
        _OBSERVED = key
    return selection, deflection


def capture(context):
    return configuration(context)[0]


def assert_current(selection, context):
    """Compare at launch, poll, consumption, current-read and publication seams."""
    if type(selection) is not BackendSelection:
        raise bridge.BridgeError("Current backend evidence requires a captured selection.")
    current = capture(context)
    try:
        selection.assert_current(current)
    except (SelectionError, AttributeError) as exc:
        raise bridge.BridgeError("Backend evidence is stale; request a fresh operation.") from exc
    return current


def is_current(selection, context):
    try:
        assert_current(selection, context)
        return True
    except bridge.BridgeError:
        return False
