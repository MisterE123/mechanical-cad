"""Registered-provider capture/retirement contracts, no native qualification."""

import ctypes as c
import importlib
import json
import ntpath
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest
from test_windows_cache import OTHER, USER, FakeAPI, release, secure, w, worker

p = importlib.import_module(w.__package__ + ".windows_package_cache")
FAMILY = "Example.App_123456789abcd"
FULL = "Example.App_1.0.0.0_x64__123456789abcd"
ROOT = "C:\\Users\\Alice\\AppData\\Local\\Packages\\" + FAMILY + "\\LocalCache"


def provider(full=FULL, root=ROOT):
    return SimpleNamespace(query=lambda family: (full, root))


def location():
    return w.query_windows_package_cache_location(FAMILY, api=provider())


def test_os_provider_identity_is_frozen_and_preserved_by_owner():
    captured = location()
    assert captured.provider == "registered-package-local-cache"
    assert captured.known_folder == ROOT
    assert captured.cache_root == ntpath.join(ROOT, "MechanicalCAD", "r")
    with pytest.raises(FrozenInstanceError):
        captured.package_full_name = FULL + "changed"
    owner = w.WindowsCacheOwner(
        captured, package_root="C:\\Installed", expected_platform="windows-x64", release=release()
    )
    assert owner.location == captured and owner.location is not captured


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "environment"),
        ("package_family", ""),
        ("package_full_name", ""),
        ("package_full_name", "bad/name"),
        ("package_family", object()),
        ("provider", object()),
    ],
)
def test_invalid_provider_identity_is_not_a_recipe(field, value):
    with pytest.raises(w.WindowsCacheError):
        replace(location(), **{field: value})


@pytest.mark.parametrize("change", ["registration", "root", "denied"])
def test_provider_change_or_denial_stops_before_token_open_or_creation(change):
    captured = location()
    api = FakeAPI(captured)
    if change == "denied":

        def denied(family):
            raise PermissionError(5, "read denied")

        api.package_cache_api = SimpleNamespace(query=denied)
    else:
        api.package_cache_api = provider(
            FULL + "new" if change == "registration" else FULL,
            ROOT + "new" if change == "root" else ROOT,
        )
    owner = w.WindowsCacheOwner(
        captured,
        package_root="C:\\Installed",
        expected_platform="windows-x64",
        release=release(),
        api=api,
    )
    with pytest.raises(w.WindowsCacheError):
        worker(owner.acquire)
    assert api.events == [] and owner._created_paths == []


def test_worker_requeries_provider_then_preserves_retained_ancestry_guards():
    captured = location()
    api = FakeAPI(captured)
    api.package_cache_api = provider()
    owner = w.WindowsCacheOwner(
        captured,
        package_root="C:\\Installed",
        expected_platform="windows-x64",
        release=release(),
        api=api,
    )

    def acquire_and_close():
        owner.acquire()
        owner.assert_held()
        assert owner.location == captured
        owner.close()

    worker(acquire_and_close)
    assert not api.handles and set(api.free_calls) == set(api.allocations)


class FakeABI:
    def __init__(self, *, failure=None, cleanup_failure=False, cleanup_phase=None):
        self.api = object.__new__(p.PackageCacheAPI)
        self.api.registered_full_name = lambda family: FULL
        self.api.runtime = self
        self.api._call = self.call
        self.failure, self.cleanup_failure = failure, cleanup_failure
        self.cleanup_phase = cleanup_phase
        self.created, self.retired, self.uninitialized = [], [], 0
        self.path = c.create_unicode_buffer(ROOT)

    def allocate(self, kind, output):
        pointer = 100 + len(self.created)
        self.created.append((kind, pointer))
        c.cast(output, c.POINTER(c.c_void_p))[0] = pointer
        return -2147467259 if len(self.created) == self.failure else 0

    def RoInitialize(self, mode):
        assert mode == 1
        return 0

    def RoUninitialize(self):
        self.uninitialized += 1
        if self.cleanup_phase == "RoUninitialize":
            raise OSError("uncertain apartment retirement")

    def WindowsCreateString(self, value, length, output):
        return self.allocate("string", output)

    def WindowsDeleteString(self, pointer):
        self.retired.append(("string", pointer))
        return (
            -2147467259
            if self.cleanup_failure or self.cleanup_phase == "WindowsDeleteString"
            else 0
        )

    def RoGetActivationFactory(self, name, iid, output):
        return self.allocate("interface", output)

    def WindowsGetStringRawBuffer(self, path, length):
        c.cast(length, c.POINTER(c.c_uint32))[0] = len(ROOT)
        return c.addressof(self.path)

    def call(self, pointer, slot, args, *values, **kwargs):
        if slot == 2:
            self.retired.append(("interface", pointer))
            if self.cleanup_phase == "Release":
                raise OSError("uncertain interface retirement")
            return 0
        return self.allocate("string" if slot == 12 else "interface", values[-1])


@pytest.mark.parametrize("failure", [None, *range(1, 9)])
def test_partial_com_and_hstring_outputs_are_retired_once(failure):
    abi = FakeABI(failure=failure)
    if failure is None:
        assert abi.api.query(FAMILY) == (FULL, ROOT)
    else:
        with pytest.raises(OSError):
            abi.api.query(FAMILY)
    assert abi.retired == list(reversed(abi.created))
    assert len(set(abi.retired)) == len(abi.retired)
    assert abi.uninitialized == 1


def test_cleanup_uncertainty_blocks_a_successful_provider_capture():
    abi = FakeABI(cleanup_failure=True)
    with pytest.raises(w.WindowsCacheError) as error:
        w.query_windows_package_cache_location(FAMILY, api=abi.api)
    assert error.value.code == "cleanup_blocked"
    assert abi.retired == list(reversed(abi.created)) and abi.uninitialized == 1
    before = list(abi.created), list(abi.retired)
    with pytest.raises(p.PackageCacheCleanupError):
        abi.api.query(FAMILY)
    assert (abi.created, abi.retired) == before
    assert all(resource[2] for resource in abi.api._resources)


@pytest.mark.parametrize("phase", ["WindowsDeleteString", "Release", "RoUninitialize"])
def test_uncertain_provider_is_retained_by_original_cache_owner_and_close_never_clears_it(phase):
    captured = location()
    abi = FakeABI(cleanup_phase=phase)
    api = FakeAPI(captured)
    api.package_cache_api = abi.api
    owner = w.WindowsCacheOwner(
        captured,
        package_root="C:\\Installed",
        expected_platform="windows-x64",
        release=release(),
        api=api,
    )

    def acquire_close():
        with pytest.raises(w.WindowsCacheError) as error:
            owner.acquire()
        assert error.value.code == "cleanup_blocked" and error.value.owner is owner
        assert owner.cleanup_uncertain and owner._provider_owner is abi.api
        before = list(abi.created), list(abi.retired), abi.uninitialized
        for _ in range(2):
            with pytest.raises(w.WindowsCacheError, match="cleanup"):
                owner.close()
            assert owner.cleanup_uncertain and owner._provider_owner is abi.api
        assert (abi.created, abi.retired, abi.uninitialized) == before

    worker(acquire_close)
    assert api.events == [] and not owner._created_paths


@pytest.mark.parametrize("phase", ["WindowsDeleteString", "Release", "RoUninitialize"])
def test_preparation_keeps_original_uncertain_provider_and_cannot_publish_descriptor(
    monkeypatch, phase
):
    prepare = importlib.import_module(w.__package__ + ".runtime_bundle_prepare")
    manifest = importlib.import_module(w.__package__ + ".runtime_bundle_manifest")
    captured = location()
    abi = FakeABI(cleanup_phase=phase)
    api = FakeAPI(captured)
    api.package_cache_api = abi.api
    monkeypatch.setattr(w, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(w, "_WindowsAPI", lambda: api)
    monkeypatch.setattr(prepare, "acquire_bundle_pin", lambda *a, **kw: pytest.fail("pin acquired"))
    raw = json.dumps({"schema_version": 1, **vars(release())}).encode()
    job = prepare.BundlePreparationJob.for_windows_qualification(
        "C:\\Installed", captured, raw, limits=manifest.BundleLimits()
    ).start()
    job._worker.join(5)
    assert not job._worker.is_alive()
    assert job.state == "cleanup_blocked" and not job.done
    assert job._cache_owner.cleanup_uncertain
    assert job._cache_owner._provider_owner is abi.api
    assert job._descriptor is None and job._pin is None and api.events == []
    before = list(abi.retired), abi.uninitialized
    with pytest.raises(prepare.BundlePreparationJobError, match="cleanup_blocked"):
        job.result()
    assert (abi.retired, abi.uninitialized) == before


@pytest.mark.parametrize("phase", ["WindowsDeleteString", "Release", "RoUninitialize"])
def test_operation_job_cannot_release_uncertain_provider_or_return_result(monkeypatch, phase):
    from test_windows_runtime import Fixture

    def load(name):
        return importlib.import_module(w.__package__ + "." + name)
    launch, manifest = load("runtime_bundle_launch"), load("runtime_bundle_manifest")
    selection, jobs, contracts = (
        load("backend_selection"),
        load("sidecar_job"),
        load("backend_contracts"),
    )
    fixture = Fixture()
    captured = w.WindowsCacheLocation(
        fixture.known_folder, fixture.cache, "registered-package-local-cache", FAMILY, FULL
    )
    abi = FakeABI(cleanup_phase=phase)
    api = FakeAPI(captured)
    api.package_cache_api = abi.api
    monkeypatch.setattr(w, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(w, "_WindowsAPI", lambda: api)
    policy = launch.capture_bundled_policy(
        manifest.BundleDescriptor(**vars(fixture.descriptor)),
        package_root=fixture.package,
        cache_root=fixture.cache,
        release_data=fixture.release,
        constants=fixture.constants,
        windows_cache=captured,
    )
    selected = selection.BackendSelection._capture_windows_bundled_transport(
        policy, 5, generation=0, lifetime_id="uncertain-provider-regression"
    )
    request = contracts.prepare_request(
        {"protocol_version": 1, "action": "canonical_snapshot", "document": {}}
    )
    job = jobs.SidecarJob.from_selection(request, selected).start()
    assert job._worker_stopped.wait(5)
    assert job.state == "cleanup_uncertain" and not job.done
    operation = job._bundle_owner
    assert operation.cleanup_uncertain and not operation.cleanup_complete
    assert operation.cache_owner.cleanup_uncertain
    assert operation.cache_owner._provider_owner is abi.api
    assert operation.pin is None and operation.process is None
    before = list(abi.retired), abi.uninitialized
    with pytest.raises(jobs.bridge.BridgeError):
        job.result()
    assert (abi.retired, abi.uninitialized) == before


@pytest.mark.parametrize("directory", [False, True])
def test_owner_rights_grant_requires_exact_current_user_owner(directory):
    value = secure(directory=directory)
    value = replace(
        value,
        aces=tuple(
            replace(ace, sid=w._OWNER_RIGHTS) if ace.sid == USER else ace for ace in value.aces
        ),
    )
    w._private_security(value, USER, directory=directory)
    with pytest.raises(w.WindowsCacheError):
        w._private_security(replace(value, owner=OTHER), USER, directory=directory)


@pytest.mark.parametrize(
    "sid",
    [
        bytes.fromhex("010100000000000300000000"),  # CREATOR OWNER is a different SID.
        bytes.fromhex("010100000000000100000000"),  # Everyone remains forbidden.
    ],
)
def test_owner_relative_support_never_admits_other_well_known_principals(sid):
    with pytest.raises(w.WindowsCacheError):
        w._private_security(
            replace(secure(), aces=(w._Ace(sid, w._FILE_ALL_ACCESS, 3),)), USER, directory=True
        )
