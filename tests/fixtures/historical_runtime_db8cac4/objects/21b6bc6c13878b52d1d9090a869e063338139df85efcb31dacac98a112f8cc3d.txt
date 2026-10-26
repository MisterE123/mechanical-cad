"""Same-worker fixed-cache composition with named concrete-method doubles only.

No Win32 call, DOS filesystem, native child, live policy or Blender is exercised.
The cache leaf separately tests its OS observations; these tests keep the real
preparation state machine and original owner identities under controlled faults.
"""

import importlib
import json
import ntpath
import threading
import types
from dataclasses import FrozenInstanceError

import pytest
import test_runtime_bundle_prepare as prior

w, m, p = prior.w, prior.m, prior.p
c = importlib.import_module(prior.PACKAGE + ".windows_cache")
PACKAGE_ROOT = r"C:\Blender\extension"
KNOWN = r"C:\Users\Alice\AppData\Local"
LOCATION = c.WindowsCacheLocation(KNOWN, ntpath.join(KNOWN, "MechanicalCAD", "r"))
BUNDLE = m.bundle_identity("a" * 40, "b" * 64, "windows-x64")


def release_bytes():
    value = json.loads(prior.release_bytes())
    value.update(
        bundle_id=BUNDLE,
        platform="windows-x64",
        manifest_path=f"_backend/{BUNDLE}/bundle-manifest.json",
        payload_path=f"_backend/{BUNDLE}/payload.zip",
    )
    return prior.encode(value)


def descriptor():
    root = ntpath.join(LOCATION.cache_root, BUNDLE)
    return m.BundleDescriptor(
        BUNDLE,
        "a" * 40,
        "b" * 64,
        "windows-x64",
        "c" * 64,
        "d" * 64,
        root,
        ntpath.join(root, "python", "python.exe"),
        ntpath.join(root, "bootstrap.py"),
    )


def job():
    return w.BundlePreparationJob.for_windows_qualification(
        PACKAGE_ROOT, LOCATION, release_bytes(), limits=prior.LIMITS, pin_timeout=1
    )


@pytest.fixture
def controlled(monkeypatch):
    state = types.SimpleNamespace(
        events=[],
        job=None,
        owner=None,
        pin=prior.Pin(),
        fail=None,
        block=False,
        stage=None,
        acquire_hook=None,
        pin_hook=None,
        materialize_hook=None,
        close_hook=None,
    )

    def acquire(owner, *, cancelled):
        assert threading.current_thread() is not threading.main_thread()
        assert state.job._cache_owner is owner
        state.owner = owner
        state.events.append("cache_acquire")
        if state.acquire_hook:
            state.acquire_hook()
        if state.fail == "cache_acquire":
            raise c.WindowsCacheError("injected_cache_acquire")

    def held(owner):
        assert owner is state.owner
        state.events.append("cache_held")

    def entry(owner, path, *, directory):
        assert owner is state.owner and state.pin.held
        state.events.append(("private_entry", path, directory))
        if state.fail == "pin_security":
            raise c.WindowsCacheError("injected_pin_security")

    def close(owner):
        assert owner is state.owner and state.pin.held
        state.events.append("cache_close")
        if state.close_hook:
            state.close_hook()
        if state.block:
            raise c.WindowsCacheError("cleanup_blocked")

    def pin(*args, **kwargs):
        assert state.owner is state.job._cache_owner
        state.events.append("pin_acquire")
        assert args == (LOCATION.cache_root, BUNDLE, "exclusive")
        if state.pin_hook:
            state.pin_hook()
        if state.fail == "pin_clean":
            raise p.BundlePinError("injected_clean_pin")
        if state.fail == "pin_uncertain":
            raise p.BundlePinError("injected_uncertain_pin", pin=state.pin)
        return state.pin

    def materialize(*args, **kwargs):
        state.events.append("materialize")
        assert kwargs["windows_storage"] is state.owner
        assert kwargs["pin"] is state.pin and state.pin.held
        if state.materialize_hook:
            state.materialize_hook()
        if state.fail == "materialize":
            raise prior.u.BundlePreparationError("original failure", state.stage)
        if state.fail == "materialize_unexpected":
            raise ValueError("original unexpected post-create failure")
        return descriptor()

    original_release = state.pin.release

    def release():
        state.events.append("pin_release")
        original_release()
        if state.fail == "pin_release":
            raise RuntimeError("original pin close uncertain")

    state.pin.release = release
    monkeypatch.setattr(c.WindowsCacheOwner, "acquire", acquire)
    monkeypatch.setattr(c.WindowsCacheOwner, "assert_held", held)
    monkeypatch.setattr(c.WindowsCacheOwner, "check_private_entry", entry)
    monkeypatch.setattr(c.WindowsCacheOwner, "close", close)
    monkeypatch.setattr(
        c.WindowsCacheOwner, "owned_stage_path", property(lambda owner: state.stage)
    )
    monkeypatch.setattr(w, "acquire_bundle_pin", pin)
    monkeypatch.setattr(w, "materialize_bundle", materialize)
    return state


def start(state):
    state.job = job()
    state.job.start()
    return prior.finish(state.job)


def test_named_entry_captures_only_frozen_recipe_without_io(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("capture/poll performed worker or known-folder work")

    monkeypatch.setattr(c, "query_windows_cache_location", forbidden)
    monkeypatch.setattr(w, "parse_release_manifest", forbidden)
    monkeypatch.setattr(c.WindowsCacheOwner, "acquire", forbidden)
    owner = job()
    assert owner._windows_cache == LOCATION and owner._windows_cache is not LOCATION
    assert owner._package_root == PACKAGE_ROOT and owner._cache_root == LOCATION.cache_root
    with pytest.raises(FrozenInstanceError):
        owner._windows_cache.cache_root = r"C:\other"
    assert owner.poll() == "created" and owner._cache_owner is None
    owner.cancel()
    owner.start()
    assert owner.poll() == "cancelled" and owner.done


@pytest.mark.parametrize("location", [None, object(), KNOWN, {"cache_root": LOCATION.cache_root}])
def test_named_entry_rejects_non_recipe_without_io(location):
    with pytest.raises(w.BundlePreparationJobError, match="invalid_windows_cache"):
        w.BundlePreparationJob.for_windows_qualification(
            PACKAGE_ROOT, location, release_bytes(), limits=prior.LIMITS
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_platform", "linux-x64"),
        ("cache_root", r"C:\elsewhere"),
        ("cache_root", object()),
        ("windows_cache", object()),
    ],
)
def test_constructor_rejects_recipe_profile_or_cache_mismatch(field, value):
    options = dict(
        package_root=PACKAGE_ROOT,
        cache_root=LOCATION.cache_root,
        release_data=release_bytes(),
        expected_platform="windows-x64",
        limits=prior.LIMITS,
        windows_cache=LOCATION,
    )
    options[field] = value
    with pytest.raises(w.BundlePreparationJobError, match="invalid_windows_cache"):
        w.BundlePreparationJob(**options)


def test_success_closes_original_cache_owner_before_original_pin(controlled):
    state = controlled
    assert start(state) == "ready"
    assert state.events[0:2] == ["cache_acquire", "pin_acquire"]
    assert state.events[-3:] == ["materialize", "cache_close", "pin_release"]
    entries = [event for event in state.events if isinstance(event, tuple)]
    assert entries == [
        ("private_entry", ntpath.join(LOCATION.cache_root, ".bundle-pins"), True),
        (
            "private_entry",
            ntpath.join(LOCATION.cache_root, ".bundle-pins", BUNDLE + ".lock"),
            False,
        ),
    ]
    assert state.job._cache_owner is None and state.job._pin is None
    assert state.job.result() == descriptor()
    with pytest.raises(w.BundlePreparationJobError, match="already_consumed"):
        state.job.result()


@pytest.mark.parametrize("failure", ["cache_acquire", "pin_clean", "pin_security", "materialize"])
def test_clean_failure_closes_partial_cache_before_pin(controlled, failure):
    state = controlled
    state.fail = failure
    state.stage = ntpath.join(LOCATION.cache_root, ".stage-" + BUNDLE + "-01234567")
    assert start(state) == "failed" and state.job.done
    assert state.events.count("cache_close") == 1
    if failure in {"cache_acquire", "pin_clean"}:
        assert state.pin.release_calls == 0
    else:
        assert state.events[-2:] == ["cache_close", "pin_release"]
    if failure == "materialize":
        assert state.job.staging_path == state.stage
        assert "original failure" in state.job.diagnostic


def test_uncertain_pin_acquisition_retains_both_without_cleanup_retry(controlled):
    state = controlled
    state.fail = "pin_uncertain"
    assert start(state) == "cleanup_blocked" and not state.job.done
    assert state.job._cache_owner is state.owner and state.job._pin is state.pin
    assert "cache_close" not in state.events and state.pin.release_calls == 0
    state.job.cancel()
    for _ in range(3):
        assert state.job.poll() == "cleanup_blocked"
        with pytest.raises(w.BundlePreparationJobError, match="cleanup_blocked"):
            state.job.result()
    assert state.pin.release_calls == 0


def test_uncertain_cache_close_retains_pin_and_created_stage(controlled):
    state = controlled
    state.block = True
    state.stage = ntpath.join(LOCATION.cache_root, ".stage-" + BUNDLE + "-01234567")
    assert start(state) == "cleanup_blocked" and not state.job.done
    assert state.job._cache_owner is state.owner and state.job._pin is state.pin
    assert state.pin.release_calls == 0 and state.pin.held
    assert state.job.staging_path == state.stage and state.job._descriptor is None
    state.job.cancel()
    assert state.events.count("cache_close") == 1


def test_uncertain_pin_release_does_not_reclose_clean_cache(controlled):
    state = controlled
    state.fail = "pin_release"
    assert start(state) == "cleanup_blocked" and not state.job.done
    assert state.job._cache_owner is None and state.job._pin is state.pin
    assert state.events.count("cache_close") == state.pin.release_calls == 1
    state.job.cancel()
    assert state.events.count("cache_close") == state.pin.release_calls == 1


@pytest.mark.parametrize("phase", ["acquire", "pin", "materialize", "close"])
def test_cancellation_waits_for_same_owner_cleanup(controlled, phase):
    state = controlled
    setattr(state, phase + "_hook", lambda: state.job.cancel())
    assert start(state) == "cancelled" and state.job.done
    assert state.job._descriptor is None and state.events.count("cache_close") == 1
    assert state.pin.release_calls == (0 if phase == "acquire" else 1)


def test_ready_cancellation_preserves_existing_one_shot_revocation(controlled):
    state = controlled
    assert start(state) == "ready"
    assert state.job.cancel()
    assert state.job.poll() == "cancelled"
    with pytest.raises(w.BundlePreparationJobError, match="cancelled"):
        state.job.result()


def test_recipe_and_job_subclasses_do_not_enter_named_qualification():
    class LocationSubclass(c.WindowsCacheLocation):
        pass

    class JobSubclass(w.BundlePreparationJob):
        pass

    for factory, location in (
        (w.BundlePreparationJob, LocationSubclass(KNOWN, LOCATION.cache_root)),
        (JobSubclass, LOCATION),
    ):
        with pytest.raises(w.BundlePreparationJobError, match="invalid_windows_cache"):
            factory.for_windows_qualification(
                PACKAGE_ROOT, location, release_bytes(), limits=prior.LIMITS
            )


def test_package_path_callback_is_rejected_without_invocation():
    class CallbackPath:
        def __fspath__(self):
            pytest.fail("path-like callback must not execute during capture")

    with pytest.raises(m.BundleError):
        w.BundlePreparationJob.for_windows_qualification(
            CallbackPath(), LOCATION, release_bytes(), limits=prior.LIMITS
        )


def test_unexpected_post_create_error_keeps_owned_stage_and_original_detail(controlled):
    state = controlled
    state.fail = "materialize_unexpected"
    state.stage = ntpath.join(LOCATION.cache_root, ".stage-" + BUNDLE + "-01234567")
    assert start(state) == "failed" and state.job.done
    assert state.job.staging_path == state.stage
    assert "original unexpected post-create failure" in state.job.diagnostic
    assert state.events[-2:] == ["cache_close", "pin_release"]
    with pytest.raises(
        w.BundlePreparationJobError, match="original unexpected post-create failure"
    ) as raised:
        state.job.result()
    assert raised.value.code == "preparation_failed" and raised.value.staging_path == state.stage
