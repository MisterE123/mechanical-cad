"""Synthetic OS provider/live capture contracts; native Blender proof is separate."""

import ctypes
import importlib
import ntpath
import os
import sys
import threading
import types
from dataclasses import replace

import pytest
from test_windows_runtime import PACKAGE, Fixture, cache, m, selection
from windows_cache_memory_fixture import OTHER, MemoryCacheAPI

hostmod = importlib.import_module(PACKAGE + ".windows_package_host")
prepare = importlib.import_module(PACKAGE + ".runtime_bundle_prepare")
runtime = importlib.import_module(PACKAGE + ".backend_runtime")
windows = importlib.import_module(PACKAGE + ".windows_runtime")
jobs = importlib.import_module(PACKAGE + ".sidecar_job")


@pytest.fixture
def native_leaves_forbidden(monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("native/cache preparation")
        pytest.fail("Synthetic live-capture test entered native/cache preparation")

    for owner, name in (
        (cache, "_WindowsAPI"),
        (prepare, "query_windows_automatic_cache_location"),
        (prepare, "materialize_bundle"),
        (prepare, "acquire_bundle_pin"),
        (windows, "WindowsRuntimeAPI"),
        (windows, "Win32API"),
        (jobs.subprocess, "Popen"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    monkeypatch.setattr(ctypes, "WinDLL", forbidden, raising=False)
    yield forbidden
    assert attempts == []


@pytest.fixture
def native_forbidden(monkeypatch, native_leaves_forbidden):
    monkeypatch.setattr(cache.WindowsCacheOwner, "check_private_entry", native_leaves_forbidden)


class HostFixture:
    def __init__(self):
        self.host = object.__new__(hostmod.WindowsPackageHost)
        self.host._resources, self.host.cleanup_uncertain = [], False
        self.closed, self.snapshots, self.queries = [], 0, []
        self.parents = {1: 2, 2: 3, 3: 4}
        self.identities = {1: 300000000000003, 2: 200000000000002, 3: 100000000000001}
        self.packages = {3: ("Example.App_123456789abcd", "Example.App_1.0.0.0_x64__123456789abcd")}
        self.changed, self.denied, self.uncertain = False, None, False

        def flags(handle, output):
            ctypes.cast(output, ctypes.POINTER(ctypes.c_uint32))[0] = 0
            return 1

        def open_process(access, inherit, pid):
            assert access == 0x101000 and inherit is False
            self.queries.append(pid)
            if self.denied == pid:
                raise PermissionError(5, "injected query denial")
            return pid + 100

        def close(handle):
            assert handle not in self.closed
            self.closed.append(handle)
            if self.uncertain:
                raise OSError("injected uncertain close")
            return 1

        self.host.k = types.SimpleNamespace(
            GetCurrentProcessId=lambda: 1,
            GetHandleInformation=flags,
            OpenProcess=open_process,
            CloseHandle=close,
        )

        def snapshot():
            self.snapshots += 1
            self.host._own(1000 + self.snapshots)
            value = dict(self.parents)
            if self.changed and self.snapshots == 2:
                value[2] = 99
            return value

        self.host._snapshot = snapshot
        self.host._creation = lambda handle, pid: self.identities[pid]
        self.host._package_string = lambda name, handle: self.packages.get(
            handle - 100, (None, None)
        )[0 if name == "GetPackageFamilyName" else 1]


def test_launcher_package_is_attested_from_retained_processes_and_closed_once():
    f = HostFixture()
    assert f.host.capture() == f.packages[3]
    assert f.queries == [1, 2, 3] and f.snapshots == 2
    assert all(resource[2] for resource in f.host._resources)
    assert f.closed == [1002, 103, 102, 101, 1001]


@pytest.mark.parametrize("damage", ["recycled", "changed", "cycle", "denied"])
def test_uncertain_or_denied_host_never_selects_another_route(damage):
    f = HostFixture()
    if damage == "recycled":
        f.identities[2] = f.identities[1] + 1
    elif damage == "changed":
        f.changed = True
    elif damage == "cycle":
        f.parents[2] = 1
    else:
        f.denied = 2
    with pytest.raises(OSError):
        f.host.capture()
    assert len(f.closed) == len(f.host._resources)
    assert not f.host.cleanup_uncertain


def test_host_close_uncertainty_retains_originals_and_is_absorbing():
    f = HostFixture()
    f.uncertain = True
    with pytest.raises(hostmod.PackageCacheCleanupError) as error:
        f.host.capture()
    assert error.value.owner is f.host and f.host.cleanup_uncertain
    before = list(f.closed)
    with pytest.raises(hostmod.PackageCacheCleanupError):
        f.host.capture()
    assert f.closed == before and all(resource[1] for resource in f.host._resources)


def test_automatic_capture_requires_registered_full_name_and_no_alias_fallback():
    fixture = Fixture()
    family, full = "Example.App_123456789abcd", "Example.App_1.0.0.0_x64__123456789abcd"
    host = types.SimpleNamespace(capture=lambda: (family, full))
    api = types.SimpleNamespace(query=lambda value: (full, fixture.known_folder))
    location = cache.query_windows_automatic_cache_location(host_api=host, package_api=api)
    assert location.package_family == family and location.package_full_name == full
    with pytest.raises(cache.WindowsCacheError, match="identity"):
        cache.query_windows_automatic_cache_location(
            host_api=host,
            package_api=types.SimpleNamespace(
                query=lambda value: (full + "new", fixture.known_folder)
            ),
        )


def test_unpacked_launcher_selects_known_folder_without_package_guessing():
    fixture = Fixture()
    allocations = []

    def query(output):
        output.value = 999
        return 0

    shell = types.SimpleNamespace(
        known_folder=query,
        read_known_folder=lambda pointer: fixture.known_folder,
        co_task_mem_free=lambda pointer: allocations.append(pointer),
    )
    location = cache.query_windows_automatic_cache_location(
        host_api=types.SimpleNamespace(capture=lambda: None), shell_api=shell
    )
    assert location.provider == "local-app-data" and location.package_family == ""
    assert allocations == [999]


def test_host_query_denial_does_not_fall_back_to_known_folder():
    called = []

    def denied():
        raise PermissionError(5, "injected host query denial")

    shell = types.SimpleNamespace(known_folder=lambda output: called.append(output))
    with pytest.raises(cache.WindowsCacheError):
        cache.query_windows_automatic_cache_location(
            host_api=types.SimpleNamespace(capture=denied), shell_api=shell
        )
    assert called == []


def test_automatic_capture_uncertainty_quarantines_preparation_before_cache_or_pin(monkeypatch):
    fixture = Fixture()
    original = object()

    def uncertain():
        raise cache.WindowsCacheError("cleanup_blocked", owner=original)

    monkeypatch.setattr(prepare, "query_windows_automatic_cache_location", uncertain)
    monkeypatch.setattr(prepare, "acquire_bundle_pin", lambda *a, **k: pytest.fail("pin acquired"))
    job = prepare.BundlePreparationJob.for_bundled_windows(
        fixture.package, fixture.release, limits=m.BundleLimits()
    ).start()
    job._worker.join(5)
    assert not job._worker.is_alive()
    assert job.state == "cleanup_blocked" and not job.done
    assert job._capture_owner is original and job._cache_owner is None and job._pin is None
    assert job.windows_cache_location is None
    with pytest.raises(prepare.BundlePreparationJobError, match="cleanup_blocked"):
        job.result()


def _memory_preparation_job(monkeypatch, *, fault=None):
    fixture = Fixture()
    events = []
    api = MemoryCacheAPI(cache, fixture.location)
    state = types.SimpleNamespace(
        fixture=fixture,
        events=events,
        api=api,
        owner=None,
        pin_releases=0,
        materializations=0,
    )
    monkeypatch.setattr(prepare, "query_windows_automatic_cache_location", lambda: fixture.location)

    def owner_factory(location, **kwargs):
        owner = cache.WindowsCacheOwner(location, api=api, **kwargs)
        assert type(owner) is cache.WindowsCacheOwner
        state.owner = api.owner = owner
        return owner

    monkeypatch.setattr(prepare, "WindowsCacheOwner", owner_factory)

    def release_pin():
        assert state.owner._state == "closed"
        assert all(resource.closed for resource in state.owner._resources)
        assert not api.handles and not api.allocations
        events.append("cache_close")  # Confirmed real owner close, before pin release.
        api.hit("pin_release")
        state.pin_releases += 1
        events.append("pin_release")

    pin = types.SimpleNamespace(release=release_pin)

    def acquire_pin(root, bundle_id, mode, **kwargs):
        assert root == fixture.location.cache_root and mode == "exclusive"
        assert state.owner._thread is threading.current_thread()
        state.owner.assert_held()
        assert state.owner._state == "held"
        events.append("cache_acquire")  # Real acquisition completed before this port.
        directory = ntpath.join(root, ".bundle-pins")
        lock = ntpath.join(directory, bundle_id + ".lock")
        api.add(directory, attributes=16 | (0x400 if fault == "reparse" else 0))
        security = api.secure(directory=False)
        if fault == "acl":
            security = replace(security, owner=OTHER)
        api.add(lock, directory=False, security=security, links=2 if fault == "two_links" else 1)
        if fault == "identity":
            api.info_change = lambda info: (
                replace(info, identity=(info.identity[0], info.identity[1] + 1))
                if info.path == root
                else info
            )
        return pin

    monkeypatch.setattr(prepare, "acquire_bundle_pin", acquire_pin)

    def materialize(*args, **kwargs):
        assert kwargs["windows_storage"].location == fixture.location
        assert type(kwargs["windows_storage"]) is cache.WindowsCacheOwner
        assert kwargs["pin"] is pin
        state.owner.assert_held()
        state.materializations += 1
        return fixture.descriptor

    monkeypatch.setattr(prepare, "materialize_bundle", materialize)
    state.job = prepare.BundlePreparationJob.for_bundled_windows(
        fixture.package, fixture.release, limits=m.BundleLimits()
    )
    api.fail_owner_close = fault == "owner_close"
    return state


def _assert_successful_memory_preparation(state):
    job, fixture, events, api = state.job, state.fixture, state.events, state.api
    assert job.windows_cache_location is None
    job.start()
    job._worker.join(5)
    assert not job._worker.is_alive()
    assert job.state == "ready" and events == ["cache_acquire", "cache_close", "pin_release"]
    assert job.result() == fixture.descriptor
    assert job.windows_cache_location == fixture.location
    assert job.windows_cache_location is not fixture.location
    assert job._cache_owner is None and job._pin is None and job._capture_owner is None
    assert state.materializations == state.pin_releases == 1
    assert state.owner._state == "closed" and not state.owner.cleanup_uncertain
    assert not api.handles and not api.allocations
    assert all(resource.closed for resource in state.owner._resources)
    pin_dir = ntpath.join(fixture.cache, ".bundle-pins")
    pin_lock = ntpath.join(pin_dir, fixture.bundle_id + ".lock")
    secured = {event[1] for event in api.events if event[0] == "security"}
    assert {pin_dir, pin_lock} <= secured
    assert api.events[-1] == ("pin_release",)
    before = list(api.events)
    with pytest.raises(cache.WindowsCacheError) as raised:
        state.owner.assert_held()
    assert raised.value.code == "windows_cache_worker_required"
    assert api.events == before


def test_automatic_preparation_transfers_recipe_only_after_cache_and_pin_retirement(
    monkeypatch, native_leaves_forbidden
):
    _assert_successful_memory_preparation(_memory_preparation_job(monkeypatch))


@pytest.mark.parametrize("fault", ["acl", "reparse", "two_links", "identity", "owner_close"])
def test_automatic_preparation_metadata_faults_never_transfer_recipe(
    monkeypatch, native_leaves_forbidden, fault
):
    _assert_successful_memory_preparation(_memory_preparation_job(monkeypatch))
    state = _memory_preparation_job(monkeypatch, fault=fault)
    job = state.job.start()
    job._worker.join(5)
    assert not job._worker.is_alive()
    assert len(state.api.close_calls) == len(set(state.api.close_calls))
    transferred = []

    def transfer():
        descriptor = job.result()
        transferred.append((descriptor, job.windows_cache_location))

    if fault == "owner_close":
        assert job.state == "cleanup_blocked" and not job.done
        assert state.owner.cleanup_uncertain
        assert job._cache_owner is state.owner and job._pin is not None
        assert job.windows_cache_location is None and state.pin_releases == 0
        assert state.events == ["cache_acquire"] and state.materializations == 1
        before = list(state.api.events)
        for _ in range(2):
            with pytest.raises(prepare.BundlePreparationJobError, match="cleanup_blocked"):
                transfer()
        assert state.api.events == before  # No uncertain resource release is retried.
    else:
        assert job.state == "failed" and job.done
        assert state.owner._state == "closed" and state.materializations == 0
        assert state.pin_releases == 1 and state.events[-2:] == ["cache_close", "pin_release"]
        assert job._cache_owner is None and job._pin is None
        with pytest.raises(prepare.BundlePreparationJobError, match="preparation_failed"):
            transfer()
    assert transferred == []


def windows_host(monkeypatch):
    if sys.platform == "win32":
        assert os.name == "nt"
        assert selection.sys is sys and runtime.sys is sys and selection.os is os
        return
    monkeypatch.setattr(selection, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(selection, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setattr(runtime, "sys", types.SimpleNamespace(platform="win32"))


def test_public_bundled_capture_is_exact_windows_policy_but_external_remains_closed(monkeypatch):
    windows_host(monkeypatch)
    fixture = Fixture()
    policy = fixture.policy()
    selected = selection.BackendSelection.capture_bundled(
        policy, 180, generation=0, lifetime_id="test"
    )
    assert selected.bundled_policy is policy and selected.launch_environment() == {}
    with pytest.raises(selection.SelectionError, match="Linux"):
        selection.BackendSelection.capture("ignored", "ignored", generation=0, lifetime_id="test")
    monkeypatch.setattr(selection, "os", types.SimpleNamespace(name="posix"))
    with pytest.raises(selection.SelectionError, match="operating system"):
        selection.BackendSelection.capture_bundled(policy, 180, generation=0, lifetime_id="test")


def test_windows_setup_capture_has_no_manual_cache_or_environment_override(
    monkeypatch, native_forbidden
):
    windows_host(monkeypatch)
    fixture = Fixture()
    captured = runtime._bundle_capture(fixture.package, None, fixture.constants)
    assert captured[1] is None and captured[2] == fixture.release
    assert captured[3] == fixture.constants and captured[3] is not fixture.constants
    with pytest.raises(ValueError, match="automatic OS"):
        runtime._bundle_capture(fixture.package, fixture.cache, fixture.constants)


def test_windows_configuration_currentness_revokes_old_timeout_and_lifetime(
    monkeypatch, native_forbidden
):
    windows_host(monkeypatch)
    fixture = Fixture()
    preferences = types.SimpleNamespace(timeout_seconds=180, linear_deflection=0.1)
    monkeypatch.setattr(runtime, "_preferences", lambda context: preferences)
    for name, value in dict(
        _BUNDLE_REQUIRED=True,
        _BUNDLE_ENABLED=True,
        _BUNDLE_POLICY=fixture.policy(),
        _OBSERVED=None,
        _GENERATION=0,
        _LIFETIME="native-development",
        _INVALIDATE=None,
    ).items():
        monkeypatch.setattr(runtime, name, value)
    old = runtime.capture(object())
    runtime.assert_current(old, object())
    preferences.timeout_seconds = 179
    with pytest.raises(runtime.bridge.BridgeError, match="stale"):
        runtime.assert_current(old, object())
    current = runtime.capture(object())
    runtime.new_lifetime()
    with pytest.raises(runtime.bridge.BridgeError, match="stale"):
        runtime.assert_current(current, object())
