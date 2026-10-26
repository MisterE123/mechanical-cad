"""One-shot offline setup worker, deliberately disconnected from live selection.

Construction captures bounded immutable inputs without parsing/hashing or I/O.
Only start() creates a thread. That worker parses the exact release bytes, owns
an exclusive stable OS pin, calls materialize_bundle and releases its pin once.
No descriptor becomes ready until release returns successfully. This is setup
data only: every later operation needs a new shared pin and full verification.

poll(), cancel() and result() never join, hash, inspect paths or release handles.
One short state lock orders cancellation, completion and one-shot consumption.
Cancellation revokes any unconsumed completion, including ready/failed results.
It cannot interrupt an OS call; cancelling remains visible until cleanup finishes.

An acquisition error with .pin already represents uncertain cleanup. Retain that
owner without retrying release. A release failure likewise retains its original
owner in the absorbing cleanup_blocked state: done remains false and result()
cannot consume it. The lifecycle caller MUST retain this job while cleanup is
blocked. There is no global registry, destructor cleanup, numeric-handle retry,
cache repair/deletion, operation lease, native launch or Blender/RNA access.
"""

from __future__ import annotations

import math
import ntpath
import os
import threading
from dataclasses import replace
from pathlib import Path

from .runtime_bundle_manifest import (
    PLATFORMS,
    BundleDescriptor,
    BundleLimits,
    parse_release_manifest,
)
from .runtime_bundle_materialize import BundleCancelled, materialize_bundle
from .runtime_bundle_pin import (
    MAX_TIMEOUT_SECONDS,
    BundlePinCancelled,
    BundlePinError,
    BundlePinTimeout,
    acquire_bundle_pin,
)
from .windows_cache import (
    WindowsCacheCancelled,
    WindowsCacheError,
    WindowsCacheLocation,
    WindowsCacheOwner,
    _windows_path,
    query_windows_automatic_cache_location,
)

MAX_DIAGNOSTIC_CHARS = 1500
MAX_ROOT_CHARS = 4096
_CLEAN_STATES = frozenset({"ready", "failed", "cancelled", "consumed"})


class BundlePreparationJobError(RuntimeError):
    """Bounded setup diagnostic, never a native-operation result or authority."""

    def __init__(self, code, detail="", *, staging_path=None):
        self.code = code
        self.detail = detail[:MAX_DIAGNOSTIC_CHARS] if type(detail) is str else ""
        self.staging_path = staging_path
        super().__init__(code + (": " + self.detail if self.detail else ""))


def _root(value):
    # Strings only: even a custom __fspath__ callback is outside capture's
    # no-I/O contract. Do not resolve(), stat() or normalize away '..'.
    if (
        type(value) is not str
        or not value
        or len(value) > MAX_ROOT_CHARS
        or "\0" in value
        or not os.path.isabs(value)
        or ".." in Path(value).parts
        or len(Path(value).parts) > 128
    ):
        raise BundlePreparationJobError("invalid_root")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise BundlePreparationJobError("invalid_root") from exc
    return value


def _failure(code, exc):
    # Do not retain exception tracebacks or call arbitrary exception formatting.
    detail = exc.args[0] if exc.args and type(exc.args[0]) is str else ""
    stage = getattr(exc, "staging_path", None)
    if type(stage) is not str or len(stage) > MAX_ROOT_CHARS or "\0" in stage:
        stage = None
    return BundlePreparationJobError(code, detail, staging_path=stage)


class BundlePreparationJob:
    """Captured setup-only owner with explicit start and nonblocking polling.

    Roots are absolute primitive strings naming existing disjoint directories.
    Captured and returned setup paths use the existing 4096-character ceiling.
    limits must be an exact BundleLimits and is detached; release_data must be
    exact immutable bytes, bounded by those trusted limits. JSON validation and
    release-identity hashing happen only on the worker. No input is reread from
    preferences, environment variables, a release pathname or a live registry.

    States: created -> running -> ready/failed; cancel makes cancelling while
    work owns resources, then cancelled after confirmed release. Clean terminal
    results/errors can be consumed once. cleanup_blocked is never clean terminal.
    pin_timeout bounds lock acquisition only, not hashing or filesystem calls.
    """

    def __init__(
        self,
        package_root,
        cache_root,
        release_data,
        *,
        expected_platform,
        limits,
        pin_timeout=30.0,
        windows_cache=None,
    ):
        if type(limits) is not BundleLimits:
            raise BundlePreparationJobError("invalid_limits")
        limits = replace(limits)
        if type(release_data) is not bytes or len(release_data) > limits.max_json_bytes:
            raise BundlePreparationJobError("invalid_release_bytes")
        if type(expected_platform) is not str or expected_platform not in PLATFORMS:
            raise BundlePreparationJobError("invalid_platform")
        if (
            type(pin_timeout) not in (int, float)
            or not math.isfinite(pin_timeout)
            or not 0 < pin_timeout <= MAX_TIMEOUT_SECONDS
        ):
            raise BundlePreparationJobError("invalid_pin_timeout")
        self._automatic_windows = expected_platform == "windows-x64" and cache_root is None
        if self._automatic_windows:
            if windows_cache is not None:
                raise BundlePreparationJobError("invalid_windows_cache")
            self._package_root, self._cache_root = _windows_path(package_root, directory=True), None
        elif windows_cache is None:
            self._package_root, self._cache_root = _root(package_root), _root(cache_root)
        else:
            if (
                type(windows_cache) is not WindowsCacheLocation
                or expected_platform != "windows-x64"
                or type(cache_root) is not str
                or cache_root != windows_cache.cache_root
            ):
                raise BundlePreparationJobError("invalid_windows_cache")
            self._package_root = _windows_path(package_root, directory=True)
            self._cache_root = _windows_path(cache_root, directory=True)
        self._windows_cache = None if windows_cache is None else replace(windows_cache)
        self._cache_owner = None
        self._capture_owner = None
        self._release_data, self._platform = release_data, expected_platform
        self._limits, self._pin_timeout = limits, float(pin_timeout)
        self._lock = threading.Lock()
        self._state = "created"
        self._cancel_requested = False
        self._launch_allowed = False
        self._worker = None
        self._pin = None
        self._descriptor = None
        self._error = None

    @classmethod
    def for_bundled_windows(cls, package_root, release_data, *, limits, pin_timeout=30.0):
        """Capture the OS-selected provider on this setup worker, never from preferences."""
        if cls is not BundlePreparationJob:
            raise BundlePreparationJobError("invalid_windows_cache")
        return cls(
            package_root,
            None,
            release_data,
            expected_platform="windows-x64",
            limits=limits,
            pin_timeout=pin_timeout,
        )

    @property
    def windows_cache_location(self):
        """Detached setup metadata only; completion/descriptor checks grant no authority."""
        with self._lock:
            if self._state not in _CLEAN_STATES or self._windows_cache is None:
                return None
            return replace(self._windows_cache)

    @classmethod
    def for_windows_qualification(
        cls, package_root, location, release_data, *, limits, pin_timeout=30.0
    ):
        """Dormant fixed-cache setup on this same worker; no runtime admission."""
        if cls is not BundlePreparationJob or type(location) is not WindowsCacheLocation:
            raise BundlePreparationJobError("invalid_windows_cache")
        return cls(
            package_root,
            location.cache_root,
            release_data,
            expected_platform="windows-x64",
            limits=limits,
            pin_timeout=pin_timeout,
            windows_cache=location,
        )

    @property
    def state(self):
        with self._lock:
            return self._state

    @property
    def done(self):
        """True only for a cleanup-confirmed completion, including consumed."""
        return self.state in _CLEAN_STATES

    @property
    def diagnostic(self):
        """Bounded current error text; no traceback or ownership transfer."""
        with self._lock:
            return str(self._error) if self._error is not None else ""

    @property
    def staging_path(self):
        """Retained attempt for diagnosis only; never an executable selection."""
        with self._lock:
            return self._error.staging_path if self._error is not None else None

    def poll(self):
        """Read bounded state; no wait, result consumption or filesystem work."""
        return self.state

    def start(self):
        """Start once; an already-cancelled unstarted job cannot launch."""
        with self._lock:
            if self._state == "cancelled":
                return self
            if self._state != "created":
                raise BundlePreparationJobError("already_started")
            self._state = "running"
            try:
                self._worker = threading.Thread(
                    target=self._run, name="mechanical-cad-bundle-prepare", daemon=True
                )
                self._worker.start()
                self._launch_allowed = True
            except BaseException as exc:
                # The worker must pass our locked gate first. Even a start()
                # failure after launching a thread cannot perform any pin/I/O.
                self._error = _failure("worker_start_failed", exc)
                self._state = "failed"
                if not isinstance(exc, Exception):
                    raise
        return self

    def cancel(self):
        """Revoke unconsumed work without waiting; never retry owner cleanup."""
        with self._lock:
            if self._cancel_requested or self._state == "consumed":
                return False
            self._cancel_requested = True
            self._descriptor = None
            if self._state == "cleanup_blocked":
                return True
            stage = self._error.staging_path if self._error is not None else None
            self._error = BundlePreparationJobError("cancelled", staging_path=stage)
            self._state = "cancelling" if self._state == "running" else "cancelled"
            return True

    def result(self):
        """Consume one cleanup-confirmed descriptor/error; never wait for work.

        Not-ready and cleanup-blocked errors do not consume or release the job.
        A descriptor remains setup data, not proof that its cache is still valid.
        """
        with self._lock:
            if self._state == "consumed":
                raise BundlePreparationJobError("already_consumed")
            if self._state == "cleanup_blocked":
                raise BundlePreparationJobError("cleanup_blocked")
            if self._state not in _CLEAN_STATES:
                raise BundlePreparationJobError("not_ready")
            descriptor, error = self._descriptor, self._error
            self._descriptor = None
            self._error = None
            self._state = "consumed"
            if error is not None:
                raise error
            return descriptor

    def _cancelled(self):
        with self._lock:
            return self._cancel_requested

    def _run(self):
        with self._lock:
            if not self._launch_allowed:
                return
        pin, descriptor, error, blocked = None, None, None, False
        try:
            if self._cancelled():
                raise BundleCancelled("Bundle preparation cancelled.")
            release = parse_release_manifest(
                self._release_data, expected_platform=self._platform, limits=self._limits
            )
            if self._cancelled():
                raise BundleCancelled("Bundle preparation cancelled.")
            if self._automatic_windows:
                try:
                    location = query_windows_automatic_cache_location()
                except WindowsCacheError as exc:
                    if exc.code == "cleanup_blocked":
                        # The provider capture owns originals even before a
                        # cache owner or pin exists. Never drop this quarantine.
                        self._capture_owner, blocked = exc.owner, True
                    raise
                self._windows_cache = replace(location)
                self._cache_root = location.cache_root
            if self._windows_cache is not None:
                self._cache_owner = WindowsCacheOwner(
                    self._windows_cache,
                    package_root=self._package_root,
                    expected_platform=self._platform,
                    release=release,
                )
                self._cache_owner.acquire(cancelled=self._cancelled)
                if self._cancelled():
                    raise BundleCancelled("Bundle preparation cancelled.")
            try:
                pin = acquire_bundle_pin(
                    self._cache_root,
                    release.bundle_id,
                    "exclusive",
                    timeout=self._pin_timeout,
                    cancelled=self._cancelled,
                )
            except BundlePinError as exc:
                if exc.pin is not None:
                    # Acquisition already attempted cleanup. Never retry it.
                    self._pin, blocked = exc.pin, True
                raise
            self._pin = pin
            if self._cancelled():
                raise BundleCancelled("Bundle preparation cancelled.")
            if self._cache_owner is None:
                descriptor = materialize_bundle(
                    self._package_root,
                    self._cache_root,
                    self._release_data,
                    expected_platform=self._platform,
                    limits=self._limits,
                    pin=pin,
                    cancelled=self._cancelled,
                )
            else:
                self._cache_owner.assert_held()
                self._cache_owner.check_private_entry(
                    ntpath.join(self._cache_root, ".bundle-pins"), directory=True
                )
                self._cache_owner.check_private_entry(
                    ntpath.join(self._cache_root, ".bundle-pins", release.bundle_id + ".lock"),
                    directory=False,
                )
                descriptor = materialize_bundle(
                    self._package_root,
                    self._cache_root,
                    self._release_data,
                    expected_platform=self._platform,
                    limits=self._limits,
                    pin=pin,
                    cancelled=self._cancelled,
                    windows_storage=self._cache_owner,
                )
            if type(descriptor) is not BundleDescriptor:
                raise BundlePreparationJobError("invalid_descriptor")
            if any(
                len(path) > MAX_ROOT_CHARS
                for path in (
                    descriptor.root,
                    descriptor.python_path,
                    descriptor.bootstrap_path,
                    str(Path(descriptor.root) / "src" / "mechanical_cad"),
                )
            ):
                raise BundlePreparationJobError("prepared_path_too_long")
        except BaseException as exc:
            code = "preparation_failed"
            if isinstance(exc, (BundleCancelled, BundlePinCancelled, WindowsCacheCancelled)):
                code = "cancelled"
            elif isinstance(exc, BundlePinTimeout):
                code = "pin_timeout"
            elif isinstance(exc, BundlePinError):
                code = "pin_acquisition_failed"
            error = _failure(code, exc)
            if self._cache_owner is not None and error.staging_path is None:
                # Preserve known creation even for an unexpected helper failure
                # outside the materializer's fixed exception tuple. No path I/O.
                error.staging_path = self._cache_owner.owned_stage_path
        finally:
            # Keep the exclusive pin until every added cache resource is clean.
            # An uncertain pin acquisition already owns failed cleanup; retain
            # both original objects without retrying either resource owner.
            if self._cache_owner is not None and not blocked:
                try:
                    self._cache_owner.close()
                except BaseException as exc:
                    blocked = True
                    cleanup = _failure("cleanup_blocked", exc)
                    cleanup.staging_path = (
                        error.staging_path if error is not None else None
                    ) or self._cache_owner.owned_stage_path
                    error = cleanup
                else:
                    self._cache_owner = None
            if pin is not None and not blocked:
                try:
                    pin.release()
                except BaseException as exc:
                    blocked = True
                    cleanup = _failure("cleanup_blocked", exc)
                    if error is not None:
                        cleanup.staging_path = error.staging_path
                    error = cleanup
                else:
                    self._pin = None
            with self._lock:
                if blocked:
                    self._descriptor = None
                    self._error = BundlePreparationJobError(
                        "cleanup_blocked",
                        error.detail if error is not None else "",
                        staging_path=error.staging_path if error is not None else None,
                    )
                    self._state = "cleanup_blocked"
                elif self._cancel_requested or (error is not None and error.code == "cancelled"):
                    self._error = BundlePreparationJobError(
                        "cancelled", staging_path=error.staging_path if error is not None else None
                    )
                    self._state = "cancelled"
                else:
                    self._descriptor, self._error = descriptor, error
                    self._state = "ready" if error is None else "failed"
