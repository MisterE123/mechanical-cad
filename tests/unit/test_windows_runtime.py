"""Inert short-DOS fixtures and injected file/Win32 leaves, never Windows qualification."""

import hashlib
import importlib
import json
import ntpath
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest
import test_windows_cache as cache_tests
from test_windows_process import FakeAPI

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_windows_transport_test"
package = sys.modules.setdefault(PACKAGE, types.ModuleType(PACKAGE))
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
w = importlib.import_module(PACKAGE + ".windows_runtime")
launch = importlib.import_module(PACKAGE + ".runtime_bundle_launch")
m = importlib.import_module(PACKAGE + ".runtime_bundle_manifest")
selection = importlib.import_module(PACKAGE + ".backend_selection")
contracts = importlib.import_module(PACKAGE + ".backend_contracts")
jobs = importlib.import_module(PACKAGE + ".sidecar_job")
cache = importlib.import_module(PACKAGE + ".windows_cache")
CACHE_OWNER_INIT = cache.WindowsCacheOwner.__init__


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def digest(value):
    return hashlib.sha256(value).hexdigest()


class Fixture:
    def __init__(self, **changes):
        self.package, self.known_folder = "C:\\Installed é", "C:\\User測定\\Local"
        self.location = cache.WindowsCacheLocation(
            self.known_folder, ntpath.join(self.known_folder, "MechanicalCAD", "r")
        )
        self.cache = self.location.cache_root
        self.bundle_id = m.bundle_identity("a" * 40, "b" * 64, "windows-x64")
        self.root = ntpath.join(self.cache, self.bundle_id)
        self.contents = {
            "python/python.exe": b"inert interpreter",
            "bootstrap.py": b"inert bootstrap",
            "src/mechanical_cad/__init__.py": b"inert source",
            "python/python312.dll": b"inert Python DLL",
            "python/DLLs/_socket.pyd": b"inert extension",
            "packages/OCP/OCP.pyd": b"inert OCP",
            "packages/slvs/solvespace.pyd": b"inert slvs",
            "packages/cadquery_ocp_novtk.libs/occt.dll": b"inert OCCT",
        }
        self.contents.update(changes)
        self.manifest = encode(
            {
                "schema_version": 1,
                "bundle_id": self.bundle_id,
                "platform": "windows-x64",
                "python_path": "python/python.exe",
                "bootstrap_path": "bootstrap.py",
                "files": [
                    {"path": name, "size": len(raw), "sha256": digest(raw), "mode": 0o644}
                    for name, raw in self.contents.items()
                ],
            }
        )
        self.release = encode(
            {
                "schema_version": 1,
                "bundle_id": self.bundle_id,
                "platform": "windows-x64",
                "source_commit": "a" * 40,
                "runtime_lock_sha256": "b" * 64,
                "manifest_path": f"_backend/{self.bundle_id}/bundle-manifest.json",
                "manifest_sha256": digest(self.manifest),
                "payload_path": f"_backend/{self.bundle_id}/payload.zip",
                "payload_sha256": "c" * 64,
                "payload_size": 1,
            }
        )
        self.descriptor = m.BundleDescriptor(
            self.bundle_id,
            "a" * 40,
            "b" * 64,
            "windows-x64",
            digest(self.manifest),
            "c" * 64,
            self.root,
            ntpath.join(self.root, "python", "python.exe"),
            ntpath.join(self.root, "bootstrap.py"),
        )
        self.constants = dict(
            SCHEMA_VERSION=1,
            BUILD_STATUS="UNQUALIFIED_CONTRACT_ARTIFACT",
            SOURCE_COMMIT="a" * 40,
            RUNTIME_LOCK_SHA256="b" * 64,
            BUNDLE_ID=self.bundle_id,
            PLATFORM="windows-x64",
            PYTHON_IMPLEMENTATION="cpython",
            PYTHON_VERSION=(3, 12, 10, "final", 0),
            PYTHON_CACHE_TAG="cpython-312",
            PYTHON_BITS=64,
            PYTHON_PATH="python/python.exe",
            PYTHON_FLAGS=launch.PYTHON_FLAGS,
            BOOTSTRAP_PATH="bootstrap.py",
            BOOTSTRAP_SHA256=digest(self.contents["bootstrap.py"]),
            RELEASE_IDENTITY_PATH="release_identity.json",
            RELEASE_IDENTITY_BYTES=self.release,
            RELEASE_IDENTITY_SHA256=digest(self.release),
            BUNDLE_MANIFEST_SHA256=digest(self.manifest),
            PAYLOAD_SHA256="c" * 64,
            ENTRY_LOADER="raise SystemExit('inert loader')",
        )

    def policy(self):
        return launch.capture_bundled_policy(
            self.descriptor,
            package_root=self.package,
            cache_root=self.cache,
            release_data=self.release,
            constants=self.constants,
            windows_cache=self.location,
        )

    def selected(self, timeout=10):
        return selection.BackendSelection._capture_windows_bundled_transport(
            self.policy(),
            timeout,
            generation=0,
            lifetime_id="pure-qualification",
        )


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, amount):
        self.sleeps.append(amount)
        self.now += amount


class Pin:
    mode = "shared"

    def __init__(self, fixture, events):
        self.bundle_id, self.events = fixture.bundle_id, events
        self.held, self.releases = True, 0
        self.fail_release = False

    def assert_held(self):
        self.events.append("pin_check")
        if not self.held:
            raise RuntimeError("inert pin lost")

    def release(self):
        self.releases += 1
        self.events.append("pin_release")
        if self.fail_release:
            raise RuntimeError("inert ambiguous release")
        self.held = False


class RuntimeAPI:
    def __init__(self, fixture, events):
        self.fixture, self.events = fixture, events
        self.handles, self.closed, self.close_calls = {}, [], []
        self.directories = set()
        self.next_handle = 1
        self.identities = {}
        self.final_path = lambda path: path
        self.process_api = None
        self.hook = lambda event: None
        self.info_change = lambda info: info
        self.stream_change = lambda info: info
        self.entries_change = lambda names: names
        self.system = "C:\\Windows"

    def hit(self, event):
        self.events.append(event)
        self.hook(event)

    def open_anchor(self, path, *, directory):
        self.hit("open_anchor")
        value = self.next_handle
        self.next_handle += 1
        self.handles[value] = (path, directory)
        return value

    def info(self, handle):
        if handle >= 1000000:
            self.hit("stream_info")
            process = self.process_api
            index = handle - 1000000
            file = process.files[index]
            assert file in process.files and file not in process.closed
            path = ntpath.join(process.temporary_directory, "tmp" + str(index))
            return self.stream_change(
                w.AnchorInfo(
                    (1, 1, index + 1),
                    path,
                    False,
                    True,
                    False,
                    False,
                    1,
                    len(process.contents[file]),
                    "NTFS",
                    True,
                    False,
                )
            )
        self.hit("anchor_info")
        assert handle not in self.closed
        path, directory = self.handles[handle]
        path = self.final_path(path)
        identity = self.identities.setdefault(path, (1, 0, len(self.identities) + 1))
        raw = self.fixture.contents.get(
            ntpath.relpath(path, self.fixture.root).replace("\\", "/"), b""
        )
        return self.info_change(
            w.AnchorInfo(
                identity,
                path,
                directory,
                True,
                False,
                False,
                0 if directory else 1,
                len(raw),
                "NTFS",
                True,
                False,
            )
        )

    def read_anchor(self, handle, offset, limit):
        self.hit("anchor_read")
        path, _ = self.handles[handle]
        raw = self.fixture.contents[ntpath.relpath(path, self.fixture.root).replace("\\", "/")]
        return raw[offset : offset + limit]

    def close_anchor(self, handle):
        assert handle not in self.close_calls
        self.close_calls.append(handle)
        self.hit("close_anchor")
        self.closed.append(handle)

    def make_directory(self, path, *, existing=False):
        self.hit("mkdir")
        assert existing or path not in self.directories
        self.directories.add(path)

    def directory_entries(self, path):
        self.hit("directory_entries")
        process = self.process_api
        names = (
            ()
            if process is None
            else tuple(
                "tmp" + str(index)
                for index, file in enumerate(process.files)
                if file not in process.closed
            )
        )
        return self.entries_change(names)

    def remove_directory(self, path):
        self.hit("rmdir")
        assert path in self.directories
        self.directories.remove(path)

    def system_directory(self):
        self.hit("system_directory")
        return self.system

    def stream_info(self, file):
        return self.info(self.stream_handle(file))

    def stream_handle(self, file):
        self.hit("stream_handle")
        assert file in self.process_api.files and file not in self.process_api.closed
        return 1000000 + self.process_api.files.index(file)


class CacheAPI(cache_tests.FakeAPI):
    """Real concrete cache owner; only its raw OS leaf observes inert records."""

    def __init__(self, fixture, runtime, events):
        super().__init__(fixture.location)
        self.runtime, self.runtime_events = runtime, events
        self.add(ntpath.dirname(fixture.cache))
        self.add(fixture.cache)
        self.add(ntpath.join(fixture.cache, ".bundle-pins"))
        self.add(
            ntpath.join(fixture.cache, ".bundle-pins", fixture.bundle_id + ".lock"), directory=False
        )

    def hit(self, *event):
        super().hit(*event)
        if hasattr(self, "runtime_events"):
            self.runtime_events.append("cache_" + event[0])

    def add(self, path, **kwargs):
        super().add(path, **kwargs)
        info, security = self.paths[path]
        self.paths[path] = (replace(info, identity=(1, info.identity[1])), security)

    def info(self, handle):
        if handle in self.runtime.handles or handle >= 1000000:
            self.hit("borrowed_info", handle)
            info = self.runtime.info(handle)
            value = cache._Info(
                (info.identity[0], (info.identity[1] << 32) | info.identity[2]),
                info.final_path,
                (16 if info.directory else 0)
                | (0x400 if info.reparse else 0)
                | (0x1000 if info.offline else 0),
                info.disk,
                info.directory,
                info.links,
            )
            return self.info_change(value)
        return cache._Info(**vars(super().info(handle)))

    def volume(self, handle, path):
        return cache._Volume(**vars(super().volume(handle, path)))

    def security_descriptor(self, handle, output):
        if handle in self.runtime.handles or handle >= 1000000:
            info = self.info(handle)
            self.allocate("observed", cache_tests.secure(directory=info.directory), output)
            return 0
        return super().security_descriptor(handle, output)

    def parse_security(self, pointer):
        value = super().parse_security(pointer)
        return cache._Security(
            value.owner,
            value.present,
            value.protected,
            tuple(cache._Ace(**vars(ace)) for ace in value.aces),
        )


class ProcessAPI(FakeAPI):
    def __init__(self, events):
        super().__init__()
        self.events = events
        self.response = b'{"protocol_version":1,"ok":true}'
        self.stderr = b""
        self.complete_on_resume = True

    def create_suspended(self, captured, line, environment, handles, attributes):
        self.spec = captured
        assert handles == (10, 11, 12, 13) and attributes == "attributes"
        assert set(dict(captured.environment)) == {"SystemRoot", "WINDIR", "TEMP", "TMP"}
        self.hit("create")
        self.command, self.active = line, 1
        self.acquire(200)
        self.acquire(201)
        return types.SimpleNamespace(process=200, thread=201)

    def observe(self, root):
        self.hit("observe")
        return w.LaunchObservation(self.pid, 456, self.spec.bundle.python_path)

    def resume(self, thread):
        result = FakeAPI.resume(self, thread)
        self.contents[self.files[1]], self.contents[self.files[2]] = self.response, self.stderr
        if self.complete_on_resume:
            self.root_signaled, self.active = True, 0
        return result


def prepared(action="canonical_snapshot"):
    request = {"protocol_version": 1, "action": action, "document": {}}
    if action.startswith("export_"):
        request.update(result_version=2, destination="C:\\Unused\\never-written.step")
    return contracts.prepare_request(
        request, required_capabilities=contracts.minimum_capabilities(request)
    )


def install(monkeypatch, fixture=None):
    fixture = fixture or Fixture()
    events, clock = [], Clock()
    pin, runtime, process = Pin(fixture, events), RuntimeAPI(fixture, events), ProcessAPI(events)
    runtime.process_api = process
    cache_api = CacheAPI(fixture, runtime, events)

    def initialize_cache(self, *args, **kwargs):
        CACHE_OWNER_INIT(self, *args, **kwargs, api=cache_api)
        cache_api.owner = self

    def acquire(cache, bundle_id, mode, **kwargs):
        events.append("acquire_pin")
        assert (cache, bundle_id, mode) == (fixture.cache, fixture.bundle_id, "shared")
        assert 0 < kwargs["timeout"] <= 10
        assert not kwargs["cancelled"]()
        return pin

    def verify(policy, actual_pin, cancelled, *, windows_storage):
        events.append("verify_tree")
        assert actual_pin is pin and pin.held and not cancelled()
        assert policy == fixture.policy()
        assert windows_storage is cache_api.owner
        windows_storage.assert_held()
        return fixture.descriptor

    def inputs(policy):
        events.append("read_inputs")
        assert policy == fixture.policy()
        return fixture.release, fixture.contents["bootstrap.py"], fixture.manifest

    def process_init(self, *, temporary_directory):
        self.__dict__ = process.__dict__
        self.temporary_directory = temporary_directory

    monkeypatch.setattr(w, "time", clock)
    monkeypatch.setattr(cache.WindowsCacheOwner, "__init__", initialize_cache)
    monkeypatch.setattr(w.pins, "acquire_bundle_pin", acquire)
    monkeypatch.setattr(w, "_verify_cached_tree", verify)
    monkeypatch.setattr(w, "_read_launch_inputs", inputs)
    monkeypatch.setattr(w, "WindowsRuntimeAPI", lambda: runtime)
    monkeypatch.setattr(w.Win32API, "__init__", process_init)
    for name in dir(ProcessAPI):
        if not name.startswith("_") and callable(getattr(ProcessAPI, name)):
            monkeypatch.setattr(w.Win32API, name, getattr(ProcessAPI, name), raising=False)
    return types.SimpleNamespace(
        fixture=fixture,
        events=events,
        pin=pin,
        runtime=runtime,
        process=process,
        clock=clock,
        cache=cache_api,
    )


def run_job(env, request=None):
    job = jobs.SidecarJob.from_selection(request or prepared(), env.fixture.selected())
    job.start()
    job._worker_stopped.wait(5)
    assert job._worker_stopped.is_set()
    return job


def test_exact_policy_has_no_io_and_stable_windows_projection(monkeypatch):
    fixture = Fixture()
    monkeypatch.setattr(w, "WindowsRuntimeAPI", lambda: pytest.fail("Win32 during capture"))
    selected = fixture.selected()
    assert selected == fixture.selected()
    assert selected.launch_environment() == {}
    assert selected.core_origin == ntpath.join(fixture.root, "src", "mechanical_cad")
    assert len(json.loads(selected.bundled_policy.descriptor_bytes())) == 10


def test_package_provider_registration_is_part_of_captured_selection_currentness():
    fixture = Fixture()
    fixture.location = replace(
        fixture.location,
        provider="registered-package-local-cache",
        package_family="Example.App_123456789abcd",
        package_full_name="Example.App_1.0.0.0_x64__123456789abcd",
    )
    old = fixture.selected()
    fixture.location = replace(
        fixture.location, package_full_name="Example.App_2.0.0.0_x64__123456789abcd"
    )
    new = fixture.selected()
    assert old.bundled_policy.windows_cache != new.bundled_policy.windows_cache
    with pytest.raises(selection.SelectionError, match="changed"):
        old.assert_current(new)


def test_os_windows_root_case_spelling_requires_same_retained_file_identity(monkeypatch):
    env = install(monkeypatch)
    env.runtime.system = "C:\\WINDOWS"
    env.runtime.final_path = lambda path: "C:\\Windows" if path == "C:\\WINDOWS" else path
    job = run_job(env)
    assert job.state == "ready", (job._error, env.events)
    assert dict(job._bundle_owner.spec.environment)["SystemRoot"] == "C:\\Windows"
    assert len(env.runtime.close_calls) == len(set(env.runtime.close_calls))


@pytest.mark.parametrize("damage", ["different_identity", "unexpected_alias"])
def test_os_windows_root_never_adopts_an_unproven_alias(monkeypatch, damage):
    env = install(monkeypatch)
    env.runtime.system = "C:\\WINDOWS" if damage == "different_identity" else "C:\\OtherRoot"
    reported = env.runtime.system
    env.runtime.final_path = lambda path: "C:\\Windows" if path == reported else path
    if damage == "different_identity":
        count = 0

        def change(info):
            nonlocal count
            if info.final_path == "C:\\Windows":
                count += 1
                if count > 1:
                    return replace(info, identity=(1, 9, 9))
            return info

        env.runtime.info_change = change
    job = run_job(env)
    assert job.state == "failed" and "create" not in env.events
    assert job._bundle_owner.failure_code == "system_directory_identity_rejected"
    assert env.pin.releases == 1


def test_owned_ntfs_directory_allocation_growth_does_not_poison_streams_or_cleanup(monkeypatch):
    env = install(monkeypatch)

    def allocated(info):
        if (
            info.directory
            and info.final_path == getattr(env.process, "temporary_directory", None)
            and len(env.process.files) >= 3
        ):
            return replace(info, size=4096)
        return info

    env.runtime.info_change = allocated
    job = run_job(env)
    assert job.state == "ready", job._error
    assert job._bundle_owner.cleanup_complete and env.pin.releases == 1


def test_extra_output_directory_entry_is_rejected_before_child_creation(monkeypatch):
    env = install(monkeypatch)
    env.runtime.entries_change = lambda names: (*names, "foreign") if len(names) == 4 else names
    job = run_job(env)
    assert job.state == "failed" and "create" not in env.events
    assert job._bundle_owner.process.error.code == "private_stream_set_invalid"


@pytest.mark.parametrize(
    "path",
    [
        "C:relative",
        "\\\\server\\share",
        "\\\\?\\C:\\x",
        "c:\\x",
        "C:\\a\\..\\b",
        "C:\\NUL",
        "C:\\x:ads",
        "C:\\tail.",
        "C:\\" + "x" * 257,
        "C:/x",
        "C:\\%PATH%",
    ],
)
def test_unsupported_dos_spellings_reject(path):
    with pytest.raises(launch.BundleLaunchError):
        launch._windows_path(path)


def test_space_unicode_short_path_is_accepted():
    assert launch._windows_path("C:\\Short path\\測定") == "C:\\Short path\\測定"


@pytest.mark.parametrize(
    "field,value",
    [
        ("PYTHON_PATH", "python/other.exe"),
        ("PYTHON_VERSION", (3, 12, 14, "final", 0)),
        ("PYTHON_BITS", 32),
        ("PLATFORM", "windows-arm64"),
        ("BOOTSTRAP_PATH", "other.py"),
        ("BOOTSTRAP_SHA256", "bad"),
        ("PYTHON_FLAGS", ("-c",)),
        ("ENTRY_LOADER", "\0"),
    ],
)
def test_exact_profile_rejects_mismatched_constants(field, value):
    fixture = Fixture()
    fixture.constants[field] = value
    with pytest.raises(m.BundleError):
        fixture.policy()


@pytest.mark.parametrize(
    "change",
    [
        "descriptor_type",
        "descriptor_identity",
        "input_type",
        "release",
        "bootstrap",
        "manifest",
        "exception",
    ],
)
def test_invalid_verified_filesystem_seam_returns_never_create(monkeypatch, change):
    env = install(monkeypatch)
    if change.startswith("descriptor"):
        value = (
            object()
            if change == "descriptor_type"
            else replace(env.fixture.descriptor, payload_sha256="f" * 64)
        )
        monkeypatch.setattr(w, "_verify_cached_tree", lambda *args, **kwargs: value)
    else:
        values = [env.fixture.release, env.fixture.contents["bootstrap.py"], env.fixture.manifest]
        if change == "input_type":
            result = values
        elif change == "exception":

            def fail(*args):
                raise OSError("private path should not escape")

            monkeypatch.setattr(w, "_read_launch_inputs", fail)
            result = None
        else:
            values[{"release": 0, "bootstrap": 1, "manifest": 2}[change]] += b"changed"
            result = tuple(values)
        if result is not None:
            monkeypatch.setattr(w, "_read_launch_inputs", lambda *args: result)
    job = run_job(env)
    assert job.state == "failed" and env.pin.releases == 1 and "create" not in env.events
    assert "private path" not in str(job._error)


@pytest.mark.parametrize(
    "field,value",
    [
        ("disk", False),
        ("directory", False),
        ("reparse", True),
        ("offline", True),
        ("local", False),
        ("inheritable", True),
        ("filesystem", "FAT32"),
        ("identity", (1, 0, 0)),
        ("final_path", "C:\\Alias"),
    ],
)
def test_unsupported_anchor_metadata_cannot_create(monkeypatch, field, value):
    env = install(monkeypatch)
    env.runtime.info_change = lambda info: replace(info, **{field: value})
    job = run_job(env)
    assert job.state == "failed" and env.pin.releases == 1 and "create" not in env.events


@pytest.mark.parametrize("field,value", [("links", 2), ("size", 999)])
def test_nonregular_or_multilink_code_rejected(monkeypatch, field, value):
    env = install(monkeypatch)
    env.runtime.info_change = lambda info: (
        info if info.directory else replace(info, **{field: value})
    )
    job = run_job(env)
    assert job.state == "failed" and env.pin.releases == 1 and "create" not in env.events


def test_changed_anchor_after_capture_rejects_before_create(monkeypatch):
    env = install(monkeypatch)
    count = {}

    def changed(info):
        count[info.identity] = count.get(info.identity, 0) + 1
        return replace(info, identity=(9, 0, 1)) if count[info.identity] > 1 else info

    env.runtime.info_change = changed
    job = run_job(env)
    assert job.state in {"failed", "cleanup_uncertain"} and "create" not in env.events


def test_critical_bytes_rehashed_from_retained_handles(monkeypatch):
    env = install(monkeypatch)
    original = env.runtime.read_anchor
    env.runtime.read_anchor = lambda handle, offset, limit: (
        b"!" * len(original(handle, offset, limit))
    )
    job = run_job(env)
    assert job.state == "failed" and env.pin.releases == 1 and "create" not in env.events


def test_conflicting_private_dll_basename_rejects(monkeypatch):
    env = install(monkeypatch, Fixture(**{"packages/OCP/python312.dll": b"conflicting"}))
    job = run_job(env)
    assert job.state == "failed" and "create" not in env.events and env.pin.releases == 1


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_id",
        "wrong_dir",
        "too_long",
        "reparse",
        "multilink",
        "enumerated_substitution",
        "missing",
        "extra",
    ],
)
def test_original_stream_handles_and_directory_set_are_both_required(monkeypatch, change):
    env = install(monkeypatch)
    if change in {"enumerated_substitution", "missing", "extra"}:

        def altered(names):
            if len(names) != 4:
                return names
            if change == "missing":
                return names[:-1]
            if change == "extra":
                return names + ("foreign",)
            return ("substitute",) + names[1:]

        env.runtime.entries_change = altered
    else:

        def altered(info):
            if len(env.process.files) != 4 or not env.process.contents[env.process.files[3]]:
                return info
            values = {
                "duplicate_id": {"identity": (1, 1, 1)},
                "wrong_dir": {"final_path": "C:\\Foreign\\file"},
                "too_long": {"final_path": ntpath.join(ntpath.dirname(info.final_path), "x" * 260)},
                "reparse": {"reparse": True},
                "multilink": {"links": 2},
            }
            return replace(info, **values[change])

        env.runtime.stream_change = altered
    job = run_job(env)
    assert job.state == "failed" and "create" not in env.events and env.pin.releases == 1
    assert len(env.process.files) == 4
    assert all(file in env.process.closed for file in env.process.files)


@pytest.mark.parametrize(
    "event",
    [
        "open_anchor",
        "anchor_info",
        "anchor_read",
        "mkdir",
        "directory_entries",
        "system_directory",
        "stream_info",
    ],
)
def test_runtime_api_faults_have_owned_once_only_cleanup(monkeypatch, event):
    env = install(monkeypatch)
    fired = []

    def fail(actual):
        if actual == event and not fired:
            fired.append(True)
            raise RuntimeError("inert API failure")

    env.runtime.hook = fail
    job = run_job(env)
    assert fired and job.state == "failed" and "create" not in env.events
    assert env.pin.releases == 1 and len(env.runtime.close_calls) == len(
        set(env.runtime.close_calls)
    )


def test_environment_is_worker_derived_and_selection_stays_stable(monkeypatch):
    env = install(monkeypatch)
    before = dict(w.os.environ)
    for key in ("PATH", "PYTHONHOME", "PYTHONPATH", "MCAD_ROOT", "TEMP", "TMP", "SYSTEMROOT"):
        monkeypatch.setenv(key, "hostile-unused")
    captured_environment = dict(w.os.environ)
    first = env.fixture.selected()
    job = run_job(env)
    assert job.state == "ready"
    actual = dict(job._bundle_owner.spec.environment)
    assert actual == {
        "SystemRoot": "C:\\Windows",
        "WINDIR": "C:\\Windows",
        "TEMP": job._bundle_owner.validation.job_directory,
        "TMP": job._bundle_owner.validation.job_directory,
    }
    assert dict(w.os.environ) == captured_environment and first == env.fixture.selected()
    assert before != captured_environment


def test_unique_operation_directories_do_not_enter_selection_equality(monkeypatch):
    first_env = install(monkeypatch)
    first_selection = first_env.fixture.selected()
    first = run_job(first_env)
    second_env = install(monkeypatch)
    second = run_job(second_env)
    assert first.state == second.state == "ready"
    assert first_selection == second_env.fixture.selected()
    assert (
        first._bundle_owner.validation.job_directory
        != second._bundle_owner.validation.job_directory
    )


def test_poisoned_pin_acquisition_is_retained_without_release_retry(monkeypatch):
    env = install(monkeypatch)

    def poisoned(*args, **kwargs):
        raise w.pins.BundlePinError("inert ambiguous acquisition", pin=env.pin)

    monkeypatch.setattr(w.pins, "acquire_bundle_pin", poisoned)
    job = run_job(env)
    assert job.state == "cleanup_uncertain" and env.pin.releases == 0
    assert job._bundle_owner.pin is env.pin and "create" not in env.events


@pytest.mark.parametrize(
    "package,cache",
    [
        ("C:\\", "C:\\cache"),
        ("C:\\package", "C:\\"),
        ("C:\\Cache", "C:\\cache"),
        ("C:\\Cache\\package", "C:\\cache"),
    ],
)
def test_windows_package_and_cache_cannot_overlap_even_at_drive_root(package, cache):
    fixture = Fixture()
    with pytest.raises(launch.BundleLaunchError, match="disjoint"):
        launch.capture_bundled_policy(
            fixture.descriptor,
            package_root=package,
            cache_root=cache,
            release_data=fixture.release,
            constants=fixture.constants,
            windows_cache=fixture.location,
        )


def test_runtime_binding_failure_releases_only_original_pin(monkeypatch):
    env = install(monkeypatch)

    def unavailable():
        raise RuntimeError("inert unavailable API")

    monkeypatch.setattr(w, "WindowsRuntimeAPI", unavailable)
    job = run_job(env)
    assert job.state == "failed" and env.pin.releases == 1
    assert job._bundle_owner.validation is None and "create" not in env.events


def test_oversized_installed_input_path_fails_before_pin_or_filesystem_seams(monkeypatch):
    env = install(monkeypatch)
    env.fixture.package = "C:\\" + "x" * 170
    job = run_job(env)
    assert job.state == "failed" and env.events == []
    assert job._bundle_owner.pin is None


def test_import_and_inert_capture_do_not_bind_win32_or_import_native(monkeypatch):
    import ctypes
    import importlib.util

    events = []

    def binding(*args, **kwargs):
        events.append(True)
        raise AssertionError("native binding during import")

    monkeypatch.setattr(ctypes, "WinDLL", binding, raising=False)
    name = PACKAGE + ".fresh_windows_leaf"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "blender_addon/mechanical_cad_blender/windows_runtime.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    assert Fixture().selected().bundled_policy.constants.PLATFORM == "windows-x64"
    assert not events


def test_duplicate_observational_stream_alias_is_rejected_before_create(monkeypatch):
    env = install(monkeypatch)

    def corrupt(event):
        if event == "initialize_file3":
            env.process._validation.streams[1] = env.process._validation.streams[0]

    env.process.hook = corrupt
    job = run_job(env)
    assert job.state == "failed" and "create" not in env.events and env.pin.releases == 1
    assert all(file in env.process.closed for file in env.process.files)


def test_recording_allocation_failure_is_already_owned_by_process(monkeypatch):
    env = install(monkeypatch)
    job = jobs.SidecarJob.from_selection(prepared(), env.fixture.selected())
    original = w.Win32API.__init__

    class FailedAppend(list):
        def append(self, value):
            raise MemoryError("inert recording allocation failure")

    def initialize(self, **kwargs):
        original(self, **kwargs)
        job._bundle_owner.validation.streams = FailedAppend()

    monkeypatch.setattr(w.Win32API, "__init__", initialize)
    job.start()
    assert job.wait(5) and job.state == "failed"
    assert env.process.files == ["file0"] and "file0" in env.process.closed
    assert env.pin.releases == 1 and "create" not in env.events


@pytest.mark.parametrize("index", range(4))
def test_actual_stream_size_must_match_initial_owned_payload_before_create(monkeypatch, index):
    env = install(monkeypatch)
    env.runtime.stream_change = lambda info: (
        replace(info, size=info.size + 1) if info.identity[2] == index + 1 else info
    )
    job = run_job(env)
    assert job.state == "failed" and "create" not in env.events and env.pin.releases == 1


def test_original_checkpoint_rechecks_deadline_after_pin_observation(monkeypatch):
    env = install(monkeypatch)
    owner = w.WindowsOperationOwner(env.fixture.policy(), b"{}")
    owner.pin, owner.deadline = env.pin, 110
    original = env.pin.assert_held

    def late_observation():
        original()
        env.clock.now += 11

    env.pin.assert_held = late_observation
    with pytest.raises(w.ProcessError) as caught:
        owner.checkpoint()
    assert caught.value.code == "timeout" and env.clock.now == 111
