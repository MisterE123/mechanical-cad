"""Injected process logic only: no subprocess, Win32, Blender or CAD execution.

These tests do not qualify Windows. Genuine process containment, ctypes ABI,
runtime/file identity, native dependency and installed-Blender gates remain open.
"""

import importlib
import sys
import types
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_windows_process_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
contracts = importlib.import_module(PACKAGE + ".backend_platform")
bundle_module = importlib.import_module(PACKAGE + ".runtime_bundle_manifest")
process = importlib.import_module(PACKAGE + ".windows_process")


def spec(**changes):
    descriptor = bundle_module.BundleDescriptor(
        "1" * 64,
        "2" * 40,
        "3" * 64,
        "windows-x64",
        "4" * 64,
        "5" * 64,
        "C:\\Private Cache\\runtimes\\測定",
        "C:\\Private Cache\\runtimes\\測定\\python\\python.exe",
        "C:\\Private Cache\\runtimes\\測定\\bootstrap.py",
    )
    value = contracts.LaunchSpec(
        descriptor,
        "# fixed release bootstrap\npass",
        (("SystemRoot", "C:\\Windows"),),
        b'{"exact":" bytes ", "guard": {}}\n',
        b'{"runtime":1}',
        10,
    )
    return replace(value, **changes)


class Pin:
    bundle_id = "1" * 64
    mode = "shared"

    def __init__(self, api):
        self.api = api
        self.held = True
        self.releases = 0

    def assert_held(self):
        self.api.hit("pin_check")
        assert self.held

    def release(self):
        self.releases += 1
        self.api.hit("pin_release")
        self.held = False


class Validation:
    def __init__(self, api, pin):
        self.api, self.pin = api, pin
        self.closes = 0

    def before_create(self, captured):
        assert self.pin.held
        self.api.hit("validate_before")
        assert captured is self.api.spec

    def after_create(self, captured, observation):
        assert self.pin.held
        assert captured is self.api.spec
        assert observation.image_path == captured.bundle.python_path
        self.api.hit("validate_after")

    def close(self):
        self.closes += 1
        assert self.pin.held
        self.api.hit("validation_close")


class FakeAPI:
    def __init__(self):
        self.events = []
        self.acquired = []
        self.closed = []
        self.close_calls = []
        self.fault = None
        self.hook = lambda event: None
        self.files = []
        self.contents = {}
        self.active = 0
        self.root_signaled = False
        self.member = True
        self.wait_status = None
        self.kill_completes = True
        self.return_code = 0
        self.pid = 123
        self.command = None
        self.resume_count = 1
        self.flags = None

    def hit(self, event):
        self.events.append(event)
        self.hook(event)
        if event == self.fault:
            self.fault = None
            raise contracts.ProcessError("injected", operation=event)

    def acquire(self, handle):
        assert handle not in self.acquired
        self.acquired.append(handle)
        return handle

    def open_file(self):
        name = f"file{len(self.files)}"
        self.hit("open_" + name)
        self.files.append(name)
        self.contents[name] = b""
        return self.acquire(name)

    def initialize_file(self, file, data):
        self.hit("initialize_" + file)
        self.contents[file] = data

    def duplicate(self, file, *, writable):
        index = self.files.index(file)
        assert writable == (index in (1, 2))
        self.hit("duplicate" + str(index))
        return self.acquire(10 + index)

    def create_job(self):
        self.hit("create_job")
        return self.acquire(100)

    def configure_job(self, job):
        assert job == 100
        self.hit("configure_job")

    def create_attributes(self):
        self.hit("create_attributes")
        return self.acquire("attributes")

    def set_handles(self, attributes, handles):
        assert attributes == "attributes" and handles == (10, 11, 12, 13)
        self.hit("set_handles")

    def set_job(self, attributes, job):
        assert attributes == "attributes" and job == 100
        self.hit("set_job")

    def create_suspended(self, captured, line, environment, handles, attributes):
        assert captured is self.spec
        assert self.events.index("configure_job") < self.events.index("set_job")
        assert self.events.index("set_handles") < self.events.index("set_job")
        assert handles == (10, 11, 12, 13) and attributes == "attributes"
        assert environment == "SystemRoot=C:\\Windows\0\0"
        self.hit("create")
        self.command = line
        self.active = 1
        self.acquire(200)
        self.acquire(201)
        return process.CreatedProcess(200, 201)

    def is_in_job(self, root, job):
        assert (root, job) == (200, 100)
        assert all(h in self.closed for h in (10, 11, 12, 13, "attributes"))
        self.hit("membership")
        return self.member

    def observe(self, root):
        assert root == 200
        self.hit("observe")
        return contracts.LaunchObservation(self.pid, 456, self.spec.bundle.python_path)

    def resume(self, thread):
        assert thread == 201
        self.hit("resume")
        return self.resume_count

    def wait(self, root):
        assert root == 200
        self.hit("wait")
        if self.wait_status is not None:
            return self.wait_status
        return process.WAIT_OBJECT_0 if self.root_signaled else process.WAIT_TIMEOUT

    def exit_code(self, root):
        assert root == 200 and self.root_signaled
        self.hit("exit_code")
        return self.return_code

    def active_processes(self, job):
        assert job == 100
        self.hit("active")
        return self.active

    def terminate_job(self, job):
        assert job == 100
        self.hit("kill_job")
        if self.kill_completes:
            self.active = 0
            if self.member:
                self.root_signaled = True

    def terminate_process(self, root):
        assert root == 200
        self.hit("kill_root")
        if self.kill_completes:
            self.root_signaled = True

    def close(self, handle):
        assert handle in self.acquired and handle not in self.close_calls
        self.close_calls.append(handle)
        self.hit("close_" + str(handle))
        self.closed.append(handle)

    close_handle = close_attributes = close_file = close

    def file_size(self, file):
        self.hit("size_" + file)
        return len(self.contents[file])

    def read_file(self, file, limit):
        self.hit("read_" + file)
        return self.contents[file][:limit]


def owner(*, captured=None):
    api = FakeAPI()
    api.spec = captured or spec()
    pin = Pin(api)
    validation = Validation(api, pin)
    now, cancelled = [10.0], [False]
    child = process.WindowsOwnedProcess(
        api.spec, pin, validation, api=api, clock=lambda: now[0], cancelled=lambda: cancelled[0]
    )
    return child, api, pin, validation, now, cancelled


def finish(child, api):
    api.active, api.root_signaled = 0, True
    assert child.close_after_cleanup()
    assert child.cleanup_complete()
    assert Counter(api.acquired) == Counter(api.closed)
    assert len(api.close_calls) == len(set(api.close_calls))


def test_success_preserves_bytes_and_fixed_command_until_real_cleanup():
    child, api, pin, validation, _, _ = owner()
    assert api.acquired == [] and child.state == "created"
    child.start()
    assert child.state == "running" and child.resumed and child.error is None
    assert api.contents["file0"] is api.spec.request_payload
    assert api.contents["file3"] is api.spec.descriptor_payload
    assert (
        '"C:\\Private Cache\\runtimes\\測定\\python\\python.exe" -I -S -B -X utf8 -c '
        in api.command
    )
    assert api.command.endswith(" 13")
    assert child.poll_exit() is None and not child.close_after_cleanup()
    assert pin.held and validation.closes == 0
    api.root_signaled, api.active = True, 0
    api.contents["file1"], api.contents["file2"] = b'{"ok":true}', b"native log"
    assert child.poll_exit() == 0 and not child.cleanup_complete()
    assert child.read_output() == b'{"ok":true}'
    assert child.read_output(stderr=True) == b"native log"
    finish(child, api)
    assert pin.releases == validation.closes == 1 and not pin.held
    assert api.events[-2:] == ["validation_close", "pin_release"]
    assert child.close_after_cleanup() and pin.releases == 1


@pytest.mark.parametrize(
    "fault",
    [
        "open_file0",
        "open_file1",
        "open_file2",
        "open_file3",
        "create_job",
        "configure_job",
        "initialize_file0",
        "initialize_file1",
        "initialize_file2",
        "initialize_file3",
        "duplicate0",
        "duplicate1",
        "duplicate2",
        "duplicate3",
        "create_attributes",
        "set_handles",
        "set_job",
        "validate_before",
        "create",
        "membership",
        "observe",
        "validate_after",
        "resume",
    ],
)
def test_every_partial_acquisition_or_setup_failure_keeps_owner_and_unwinds(fault):
    child, api, pin, validation, _, _ = owner()
    api.fault = fault
    child.start()
    assert child.error is not None and not child.resumed
    assert child.close_after_cleanup() and child.cleanup_complete()
    assert Counter(api.acquired) == Counter(api.closed)
    assert pin.releases == validation.closes == 1
    if 200 in api.acquired:
        assert "kill_job" in api.events
    if fault in {"membership"}:
        assert "kill_root" in api.events


@pytest.mark.parametrize(
    "barrier",
    [
        "open_file0",
        "open_file3",
        "configure_job",
        "duplicate3",
        "set_job",
        "validate_before",
        "create",
        "membership",
        "observe",
        "validate_after",
        "resume",
    ],
)
def test_cancellation_at_each_launch_barrier(barrier):
    child, api, pin, _, _, cancelled = owner()
    api.hook = lambda event: cancelled.__setitem__(0, True) if event == barrier else None
    child.start()
    assert child.error.code == "cancelled"
    if barrier != "resume":
        assert "resume" not in api.events
    assert child.cleanup_complete() and pin.releases == 1
    assert Counter(api.acquired) == Counter(api.closed)


def test_cancel_before_start_and_subsequent_start_do_not_create():
    child, api, pin, _, _, cancelled = owner()
    cancelled[0] = True
    child.start().start()
    assert child.cleanup_complete() and child.error.code == "cancelled"
    assert not child.attempted_start and api.acquired == [] and pin.releases == 1


def test_explicit_cancel_before_start_does_not_create():
    child, api, _, _, _, _ = owner()
    child.cancel_tree()
    child.start()
    assert not child.attempted_start and api.acquired == []
    assert child.close_after_cleanup()


@pytest.mark.parametrize("barrier", ["open_file0", "validate_before", "create", "resume"])
def test_timeout_covers_setup_and_never_equates_kill_to_cleanup(barrier):
    child, api, pin, _, now, _ = owner()
    api.kill_completes = False
    api.hook = lambda event: now.__setitem__(0, 20.0) if event == barrier else None
    child.start()
    assert child.error.code == "timeout"
    if child.attempted_start:
        assert not child.cleanup_complete() and pin.held
        assert not child.close_after_cleanup()
        finish(child, api)
    else:
        assert child.cleanup_complete()


def test_root_exit_with_descendant_is_failure_until_empty():
    child, api, pin, _, _, _ = owner()
    child.start()
    api.kill_completes = False
    api.root_signaled, api.active = True, 1
    assert child.poll_exit() == 0
    assert child.error.code == "unexpected_descendants" and "kill_job" in api.events
    assert not child.close_after_cleanup() and pin.held
    with pytest.raises(contracts.ProcessError, match="output_unavailable"):
        child.read_output()
    finish(child, api)


def test_job_empty_does_not_replace_original_root_wait():
    child, api, pin, _, _, _ = owner()
    child.start()
    api.active = 0
    assert child.poll_exit() is None
    assert not child.close_after_cleanup() and pin.held
    finish(child, api)


@pytest.mark.parametrize("status", [128, 0xFFFFFFFF, 999])
def test_wait_status_other_than_signal_or_timeout_fails_closed(status):
    child, api, pin, _, _, _ = owner()
    child.start()
    api.wait_status = status
    api.kill_completes = False
    child.poll_exit()
    assert child.cleanup_error.code == "unexpected_wait_status"
    assert not child.cleanup_complete() and pin.held
    assert not child.close_after_cleanup()
    api.wait_status = None
    finish(child, api)


@pytest.mark.parametrize("fault", ["wait", "exit_code", "active", "kill_job"])
def test_cleanup_query_and_termination_failures_retain_pin_and_can_reap_later(fault):
    child, api, pin, _, _, _ = owner()
    child.start()
    api.kill_completes = False
    api.fault = fault
    if fault == "exit_code":
        api.root_signaled = True
    if fault == "kill_job":
        child.cancel_tree()
    else:
        child.poll_exit()
    assert child.cleanup_error is not None and pin.held and not child.cleanup_complete()
    finish(child, api)


@pytest.mark.parametrize("membership", [False, "query_failure"])
def test_unknown_membership_uses_exact_retained_root_for_defensive_cleanup(membership):
    child, api, pin, _, _, _ = owner()
    api.kill_completes = False
    if membership is False:
        api.member = False
    else:
        api.fault = "membership"
    child.start()
    assert "resume" not in api.events
    assert "kill_job" in api.events and "kill_root" in api.events
    assert pin.held and not child.cleanup_complete()
    finish(child, api)


def test_defensive_root_termination_failure_retains_owner():
    child, api, pin, _, _, _ = owner()
    api.member = False
    api.hook = lambda event: setattr(api, "fault", "kill_root") if event == "kill_root" else None
    child.start()
    assert not child.cleanup_complete() and pin.held and not api.root_signaled
    assert not child.close_after_cleanup()
    api.hook = lambda event: None
    assert child.close_after_cleanup()


@pytest.mark.parametrize(
    "fault",
    [
        "close_10",
        "close_attributes",
        "close_201",
        "close_200",
        "close_100",
        "close_file0",
        "validation_close",
        "pin_release",
    ],
)
def test_failed_close_is_never_retried_or_reported_complete(fault):
    child, api, pin, validation, _, _ = owner()
    api.fault = fault
    child.start()
    api.active, api.root_signaled = 0, True
    assert not child.close_after_cleanup()
    assert not child.cleanup_complete() and pin.held
    before = (list(api.close_calls), validation.closes, pin.releases)
    kills = (api.events.count("kill_job"), api.events.count("kill_root"))
    child.cancel_tree()
    assert not child.close_after_cleanup()
    assert before == (api.close_calls, validation.closes, pin.releases)
    assert kills == (api.events.count("kill_job"), api.events.count("kill_root"))
    if fault != "pin_release":
        assert pin.releases == 0


@pytest.mark.parametrize("resume_count", [0, 2, 0xFFFFFFFF])
def test_unexpected_resume_count_never_becomes_running(resume_count):
    child, api, _, _, _, _ = owner()
    api.resume_count = resume_count
    child.start()
    assert child.error.code == "unexpected_suspend_count" and not child.resumed
    assert child.cleanup_complete()


def test_pid_reuse_cannot_retarget_wait_kill_or_close():
    child, api, _, _, _, _ = owner()
    child.start()
    assert child.observation.process_id == 123
    api.pid = 987654
    child.cancel_tree()
    finish(child, api)
    assert child.observation.process_id == 123


@pytest.mark.parametrize("stderr", [False, True])
def test_output_overflow_cancels_without_publishing(stderr, monkeypatch):
    child, api, pin, _, _, _ = owner()
    monkeypatch.setattr(process, "MAX_STDERR_BYTES" if stderr else "MAX_STDOUT_BYTES", 4)
    child.start()
    api.kill_completes = False
    api.contents["file2" if stderr else "file1"] = b"oversize"
    child.poll_exit()
    assert child.error.code == "output_limit" and pin.held
    with pytest.raises(contracts.ProcessError, match="output_unavailable"):
        child.read_output(stderr=stderr)
    finish(child, api)


def test_cancel_after_root_exit_before_close_discards_output():
    child, api, _, _, _, _ = owner()
    child.start()
    api.active, api.root_signaled = 0, True
    assert child.poll_exit() == 0
    child.cancel_tree()
    with pytest.raises(contracts.ProcessError, match="output_unavailable"):
        child.read_output()
    finish(child, api)


@pytest.mark.parametrize(
    "changes",
    [
        {"timeout": True},
        {"timeout": float("nan")},
        {"timeout": float("inf")},
        {"request_payload": {}},
        {"request_payload": bytearray(b"{}")},
        {"request_payload": b"x" * (contracts.MAX_INPUT_BYTES + 1)},
        {"descriptor_payload": b"x" * (contracts.MAX_DESCRIPTOR_BYTES + 1)},
        {"bootstrap": "x" * 4097},
        {"bootstrap": "bad\0code"},
        {"environment": (("PATH", "external"),)},
        {"environment": (("SystemRoot", "a"), ("SYSTEMROOT", "a"))},
        {"environment": (("TEMP", "a\0b"),)},
        {"environment": {"TEMP": "external"}},
    ],
)
def test_invalid_finite_launch_records_rejected_before_api(changes):
    with pytest.raises(contracts.ProcessError):
        spec(**changes)


def test_timeout_clamping_and_redacted_launch_repr():
    assert spec(timeout=-10).timeout == 1 and spec(timeout=10000).timeout == 300
    captured = spec(environment=(("TEMP", "secret-value"),), bootstrap="secret code")
    assert "secret-value" not in repr(captured) and "secret code" not in repr(captured)
    assert "guard" not in repr(captured)


@pytest.mark.parametrize(
    "path",
    [
        "python.exe",
        "C:python.exe",
        "\\python.exe",
        "\\\\server\\python.exe",
        "\\\\?\\C:\\python.exe",
        "C:\\py.exe",
        "C:\\python.exe --flag",
        "C:\\%TEMP%\\python.exe",
    ],
)
def test_direct_absolute_application_is_required(path):
    value = spec()
    value = replace(value, bundle=replace(value.bundle, python_path=path))
    with pytest.raises(contracts.ProcessError):
        owner(captured=value)


def test_quoted_command_utf16_limit_includes_nul_and_surrogate_pairs():
    value = spec()
    base = process.command_line(value, 13)
    base_units = len(base.encode("utf-16-le")) // 2 + 1
    remaining = 32767 - base_units
    padding = "😀" * (remaining // 2) + "x" * (remaining % 2)
    exact = replace(
        value,
        bundle=replace(
            value.bundle, python_path=value.bundle.python_path.replace("測定", "測定" + padding)
        ),
    )
    assert len(process.command_line(exact, 13).encode("utf-16-le")) // 2 + 1 == 32767
    oversized = replace(
        exact,
        bundle=replace(exact.bundle, python_path=exact.bundle.python_path.replace("測定", "測定x")),
    )
    with pytest.raises(contracts.ProcessError, match="command_line_too_long"):
        process.command_line(oversized, 13)


def test_only_data_handle_is_appended_and_bootstrap_quoting_is_literal():
    value = spec(bootstrap='a = "quotes and \\"escaped\\" text"\n# ; & | %')
    line = process.command_line(value, 123)
    assert line.endswith(" 123") and "-I -S -B -X utf8 -c" in line
    with pytest.raises(contracts.ProcessError):
        process.command_line(value, True)


def test_native_api_fails_explicitly_on_non_windows_without_binding(monkeypatch):
    monkeypatch.setattr(process.os, "name", "posix")
    import ctypes

    monkeypatch.setattr(
        ctypes, "WinDLL", lambda *args, **kwargs: pytest.fail("bound Win32"), raising=False
    )
    with pytest.raises(contracts.ProcessError, match="native_windows_required"):
        process.Win32API()
    assert not any(
        name.startswith(PACKAGE + ".")
        and any(forbidden in name for forbidden in ("kernel_ocp", "sketch_solver"))
        for name in sys.modules
    )


def test_import_is_pure_and_never_imports_platform_native_or_cad_modules(monkeypatch):
    import builtins

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] not in {"ctypes", "msvcrt", "bpy", "OCP", "slvs"}
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.reload(process)


def test_terminal_exit_code_259_is_still_exit_when_original_handle_is_signaled():
    child, api, _, _, _, _ = owner()
    child.start()
    api.active, api.root_signaled, api.return_code = 0, True, 259
    assert child.poll_exit() == 259
    finish(child, api)


class FakeFunction:
    def __init__(self, name, calls):
        self.name, self.calls = name, calls
        self.callback = lambda *args: 1

    def __call__(self, *args):
        self.calls.append((self.name, args))
        return self.callback(*args)


def fake_bound_adapter(monkeypatch):
    """ctypes declarations exercised with no OS binding or native process."""
    import ctypes

    calls, functions, last_error = [], {}, [0]

    class Kernel:
        def __getattr__(self, name):
            return functions.setdefault(name, FakeFunction(name, calls))

    monkeypatch.setattr(process, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(get_osfhandle=lambda fd: fd))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: Kernel(), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: last_error[0], raising=False)
    monkeypatch.setattr(
        ctypes, "set_last_error", lambda n: last_error.__setitem__(0, n), raising=False
    )
    api = process.Win32API(temporary_directory="C:\\Private Jobs")
    return api, functions, calls, last_error


def test_ctypes_declarations_and_create_flags_are_explicit_with_fake_bindings(monkeypatch):
    api, functions, calls, _ = fake_bound_adapter(monkeypatch)
    c = api.c
    assert c.sizeof(api.StartupEx) == 112 and c.sizeof(api.ProcessInfo) == 24
    assert api.StartupEx.Attributes.offset == 104
    assert api.ProcessInfo.Process.offset == 0 and api.ProcessInfo.Thread.offset == 8
    assert api.ExtendedLimit.IO.offset == 64 and api.Accounting.ActiveProcesses.offset == 40
    assert all(
        hasattr(function, "argtypes") and hasattr(function, "restype")
        for function in functions.values()
    )

    def create(application, line, process_sa, thread_sa, inherit, flags, env, cwd, startup, info):
        assert application == value.bundle.python_path and cwd == value.bundle.root
        assert process_sa is thread_sa is None and inherit is True
        assert flags == 0x08080404 and not flags & 0x01000000  # No breakaway.
        assert line.value == command and env.value == "SystemRoot=C:\\Windows"
        assert startup._obj.StartupInfo.cb == 112
        assert startup._obj.StartupInfo.Flags == 0x100
        assert (
            startup._obj.StartupInfo.Input,
            startup._obj.StartupInfo.Output,
            startup._obj.StartupInfo.Error,
        ) == (10, 11, 12)
        info._obj.Process, info._obj.Thread = 200, 201
        return 1

    functions["CreateProcessW"].callback = create
    value = spec()
    command = process.command_line(value, 13)
    attributes = process._Attributes(c.create_string_buffer(128))
    child = api.create_suspended(
        value, command, process.environment_block(value), (10, 11, 12, 13), attributes
    )
    assert child == process.CreatedProcess(200, 201)
    assert calls[-1][0] == "CreateProcessW"


def test_fake_bound_job_is_unnamed_noninherited_and_only_kill_on_close(monkeypatch):
    api, functions, _, _ = fake_bound_adapter(monkeypatch)

    def create(sa, name):
        assert sa is name is None
        return 100

    def configure(job, kind, info, length):
        assert (job, kind, length) == (100, 9, 144)
        assert info._obj.Basic.Flags == 0x2000
        assert info._obj.Basic.ActiveLimit == 0
        return 1

    functions["CreateJobObjectW"].callback = create
    functions["SetInformationJobObject"].callback = configure
    assert api.create_job() == 100
    api.configure_job(100)


def test_fake_bound_attribute_storage_and_duplicate_rights_are_explicit(monkeypatch):
    api, functions, calls, last_error = fake_bound_adapter(monkeypatch)

    def initialize(buffer, count, flags, size):
        assert count == 2 and flags == 0
        size._obj.value = 128
        if buffer is None:
            last_error[0] = 122
            return 0
        return 1

    def duplicate(source, handle, target, result, access, inherit, options):
        assert access in (0x80000000, 0x40000000) and inherit is True and options == 0
        result._obj.value = 20 if access == 0x80000000 else 21
        return 1

    functions["InitializeProcThreadAttributeList"].callback = initialize
    functions["DuplicateHandle"].callback = duplicate
    attributes = api.create_attributes()
    api.set_handles(attributes, (10, 11, 12, 13))
    api.set_job(attributes, 100)
    assert [tuple(value) for value in attributes.values] == [(10, 11, 12, 13), (100,)]
    updates = [args for name, args in calls if name == "UpdateProcThreadAttribute"]
    assert [args[2] for args in updates] == [0x20002, 0x2000D]
    assert [args[4] for args in updates] == [32, 8]
    file = types.SimpleNamespace(fileno=lambda: 5)
    assert api.duplicate(file, writable=False) == 20
    assert api.duplicate(file, writable=True) == 21
    api.close_attributes(attributes)
    assert calls[-1][0] == "DeleteProcThreadAttributeList"


def test_pin_or_validation_failure_during_constructor_remains_caller_owned():
    api = FakeAPI()
    pin = Pin(api)
    pin.mode = "exclusive"
    validation = Validation(api, pin)
    with pytest.raises(contracts.ProcessError, match="shared_bundle_pin_required"):
        process.WindowsOwnedProcess(spec(), pin, validation, api=api)
    assert pin.held and pin.releases == validation.closes == 0 and api.acquired == []


def test_production_admission_and_owners_do_not_import_new_leaf():
    for name in ("backend_selection", "backend_runtime", "sidecar_job", "registration"):
        text = (ROOT / "blender_addon/mechanical_cad_blender" / (name + ".py")).read_text()
        assert "windows_process" not in text and "backend_platform" not in text
    selection = (ROOT / "blender_addon/mechanical_cad_blender/backend_selection.py").read_text()
    assert 'sys.platform != "linux"' in selection


def invalidate_pin_assurance(pin):
    """Retain a resource to close, but make the OS-backed pin check fail."""

    def unavailable():
        raise contracts.ProcessError("pin_unavailable")

    pin.assert_held = unavailable


@pytest.mark.parametrize("barrier", ["membership", "observe", "validate_after"])
def test_lost_pin_after_create_is_checked_again_before_resume(barrier):
    child, api, pin, validation, _, _ = owner()
    api.hook = lambda event: invalidate_pin_assurance(pin) if event == barrier else None
    child.start()
    assert "resume" not in api.events and not child.resumed
    assert child.error.code == "bundle_pin_lost"
    assert "kill_job" in api.events
    assert child.cleanup_complete() and not pin.held
    assert Counter(api.acquired) == Counter(api.closed)
    assert validation.closes == pin.releases == 1


def test_pin_loss_during_resume_is_detected_before_running_returns():
    child, api, pin, _, _, _ = owner()
    api.hook = lambda event: invalidate_pin_assurance(pin) if event == "resume" else None
    child.start()
    assert child.resumed and child.error.code == "bundle_pin_lost"
    assert "kill_job" in api.events and child.cleanup_complete()
    assert Counter(api.acquired) == Counter(api.closed)


def test_running_pin_loss_invalidates_output_without_blocking_reap_or_close():
    child, api, pin, validation, _, _ = owner()
    child.start()
    api.kill_completes = False
    invalidate_pin_assurance(pin)
    child.poll_exit()
    assert child.error.code == "bundle_pin_lost" and "kill_job" in api.events
    assert "wait" in api.events and "active" in api.events
    assert pin.held and pin.releases == 0
    assert not child.close_after_cleanup()
    with pytest.raises(contracts.ProcessError, match="output_unavailable"):
        child.read_output()
    finish(child, api)
    assert validation.closes == pin.releases == 1 and not pin.held


@pytest.mark.parametrize("barrier", ["wait", "active"])
def test_pin_loss_during_poll_is_detected_before_poll_returns(barrier):
    child, api, pin, _, _, _ = owner()
    child.start()
    api.kill_completes = False
    api.hook = lambda event: invalidate_pin_assurance(pin) if event == barrier else None
    child.poll_exit()
    assert child.error.code == "bundle_pin_lost" and "kill_job" in api.events
    assert not child.cleanup_complete() and pin.held
    finish(child, api)


@pytest.mark.parametrize("barrier", ["wait", "active", "size_file2"])
def test_pin_loss_during_final_observation_invalidates_quiescent_output(barrier):
    child, api, pin, _, _, _ = owner()
    child.start()
    api.active, api.root_signaled = 0, True
    api.hook = lambda event: invalidate_pin_assurance(pin) if event == barrier else None
    assert child.poll_exit() == 0
    assert child.error.code == "bundle_pin_lost"
    with pytest.raises(contracts.ProcessError, match="output_unavailable"):
        child.read_output()
    finish(child, api)


@pytest.mark.parametrize("stderr", [False, True])
@pytest.mark.parametrize("when", ["before_read", "during_read"])
def test_pin_loss_after_quiescence_prevents_either_output_return(stderr, when):
    child, api, pin, _, _, _ = owner()
    child.start()
    api.active, api.root_signaled = 0, True
    assert child.poll_exit() == 0
    if when == "before_read":
        invalidate_pin_assurance(pin)
    else:
        barrier = "read_file2" if stderr else "read_file1"
        api.hook = lambda event: invalidate_pin_assurance(pin) if event == barrier else None
    with pytest.raises(contracts.ProcessError):
        child.read_output(stderr=stderr)
    assert child.error.code == "bundle_pin_lost"
    finish(child, api)


def test_completed_output_pin_check_does_not_apply_a_later_timeout():
    child, api, pin, _, now, _ = owner()
    child.start()
    api.contents["file1"], api.contents["file2"] = b"stdout", b"stderr"
    api.active, api.root_signaled = 0, True
    assert child.poll_exit() == 0
    before = api.events.count("pin_check")
    now[0] += 1000
    assert child.read_output() == b"stdout"
    assert child.read_output(stderr=True) == b"stderr"
    assert api.events.count("pin_check") > before
    assert child.error is None and pin.held
    finish(child, api)


@pytest.mark.parametrize("overflow_stream", ["file1", "file2"])
@pytest.mark.parametrize("barrier", ["wait", "active"])
def test_both_streams_are_bounded_after_final_root_and_job_observation(
    overflow_stream, barrier, monkeypatch
):
    child, api, pin, _, _, _ = owner()
    monkeypatch.setattr(process, "MAX_STDOUT_BYTES", 4)
    monkeypatch.setattr(process, "MAX_STDERR_BYTES", 4)
    child.start()

    def finish_with_last_write(event):
        if event == barrier:
            api.contents[overflow_stream] = b"overflow"
            api.root_signaled, api.active = True, 0

    if barrier == "active":
        api.root_signaled = True
    api.hook = finish_with_last_write
    assert child.poll_exit() == 0
    assert child.error.code == "output_limit" and pin.held
    # Read the OTHER stream: neither output can bypass the pair's final bound.
    with pytest.raises(contracts.ProcessError, match="output"):
        child.read_output(stderr=overflow_stream == "file1")
    finish(child, api)


@pytest.mark.parametrize("overflow_stream", ["file1", "file2"])
@pytest.mark.parametrize("when", ["before_read", "during_read"])
def test_quiescent_reads_recheck_both_streams_not_only_the_requested_stream(
    overflow_stream, when, monkeypatch
):
    child, api, _, _, _, _ = owner()
    monkeypatch.setattr(process, "MAX_STDOUT_BYTES", 4)
    monkeypatch.setattr(process, "MAX_STDERR_BYTES", 4)
    child.start()
    api.root_signaled, api.active = True, 0
    assert child.poll_exit() == 0 and child.error is None
    if when == "before_read":
        api.contents[overflow_stream] = b"overflow"
    else:
        barrier = "read_file2" if overflow_stream == "file1" else "read_file1"

        def write_other_stream(event):
            if event == barrier:
                api.contents[overflow_stream] = b"overflow"

        api.hook = write_other_stream
    with pytest.raises(contracts.ProcessError, match="output_limit"):
        child.read_output(stderr=overflow_stream == "file1")
    assert child.error.code == "output_limit"
    finish(child, api)


def deadline_owner(deadline):
    api = FakeAPI()
    api.spec = spec()
    pin = Pin(api)
    validation = Validation(api, pin)
    now = [10.0]
    child = process.WindowsOwnedProcess(
        api.spec, pin, validation, api=api, clock=lambda: now[0], deadline=deadline
    )
    return child, api, pin, validation, now


@pytest.mark.parametrize(
    "deadline",
    [
        True,
        False,
        "20",
        b"20",
        [],
        {},
        object(),
        float("nan"),
        float("inf"),
        -float("inf"),
        10**1000,
    ],
)
def test_invalid_absolute_deadline_rejects_before_pin_or_api_acquisition(deadline, monkeypatch):
    api = FakeAPI()
    pin = Pin(api)
    validation = Validation(api, pin)
    monkeypatch.setattr(process, "Win32API", lambda: pytest.fail("acquired default API"))
    with pytest.raises(contracts.ProcessError, match="invalid_process_deadline"):
        process.WindowsOwnedProcess(spec(), pin, validation, clock=lambda: 10.0, deadline=deadline)
    assert api.events == api.acquired == []
    assert validation.closes == pin.releases == 0 and pin.held


@pytest.mark.parametrize("deadline", [-1.0, 9, 10.0])
def test_expired_absolute_deadline_remains_caller_owned_without_acquisition(deadline, monkeypatch):
    api = FakeAPI()
    pin = Pin(api)
    validation = Validation(api, pin)
    monkeypatch.setattr(process, "Win32API", lambda: pytest.fail("acquired default API"))
    with pytest.raises(contracts.ProcessError, match="timeout"):
        process.WindowsOwnedProcess(spec(), pin, validation, clock=lambda: 10.0, deadline=deadline)
    assert api.events == api.acquired == []
    assert validation.closes == pin.releases == 0 and pin.held


@pytest.mark.parametrize("deadline", [12, 12.5])
def test_supplied_deadline_is_never_renewed_by_delayed_start(deadline):
    child, api, pin, validation, now = deadline_owner(deadline)
    now[0] = 11.0
    child.start()
    assert child.state == "running" and child.error is None
    assert child._deadline == deadline
    now[0] = deadline
    child.poll_exit()
    assert child.error.code == "timeout" and "kill_job" in api.events
    assert child._deadline == deadline
    finish(child, api)
    assert validation.closes == pin.releases == 1


def test_supplied_deadline_expiring_before_start_acquires_no_process_resources():
    child, api, pin, validation, now = deadline_owner(12.0)
    now[0] = 12.0
    child.start()
    assert child.error.code == "timeout" and not child.attempted_start
    assert api.acquired == [] and child.cleanup_complete()
    assert validation.closes == pin.releases == 1


def test_none_deadline_preserves_start_time_timeout_default():
    child, api, _, _, now = deadline_owner(None)
    assert child._deadline is None
    now[0] = 100.0
    child.start()
    assert child._deadline == 110.0 and child.error is None
    now[0] = 109.9
    assert child.poll_exit() is None and child.error is None
    now[0] = 110.0
    child.poll_exit()
    assert child.error.code == "timeout"
    finish(child, api)


def test_quiescence_property_requires_root_and_job_and_is_read_only():
    child, api, _, _, _, _ = owner()
    assert child.tree_quiescent is False and child.cleanup_uncertain is False
    for name in ("tree_quiescent", "cleanup_uncertain"):
        with pytest.raises(AttributeError):
            setattr(child, name, True)
    child.start()
    api.kill_completes = False
    api.root_signaled, api.active = True, 1
    assert child.poll_exit() == 0 and child.tree_quiescent is False
    assert child.cleanup_uncertain is False
    api.active = 0
    child.poll_exit()
    assert child.tree_quiescent is True and child.cleanup_uncertain is False
    finish(child, api)
    assert child.tree_quiescent is True and child.cleanup_uncertain is False


@pytest.mark.parametrize(
    "fault",
    [
        "close_10",
        "close_11",
        "close_12",
        "close_13",
        "close_attributes",
        "close_201",
        "close_200",
        "close_100",
        "close_file0",
        "close_file1",
        "close_file2",
        "close_file3",
    ],
)
def test_uncertain_resource_close_retains_all_validation_anchors_and_pin(fault):
    child, api, pin, validation, _, _ = owner()
    api.fault = fault
    child.start()
    api.root_signaled, api.active = True, 0
    assert child.close_after_cleanup() is False
    assert child.tree_quiescent is True and child.cleanup_uncertain is True
    assert child.cleanup_complete() is False
    assert validation.closes == pin.releases == 0 and pin.held
    assert "validation_close" not in api.events and "pin_release" not in api.events
    assert Counter(api.close_calls) == Counter(api.acquired)
    before = list(api.close_calls)
    assert child.close_after_cleanup() is False
    assert api.close_calls == before and validation.closes == pin.releases == 0


@pytest.mark.parametrize("fault", ["wait", "exit_code", "active", "kill_job"])
def test_recoverable_query_or_termination_failure_does_not_poison_cleanup(fault):
    child, api, _, _, _, _ = owner()
    child.start()
    api.kill_completes = False
    api.fault = fault
    if fault == "exit_code":
        api.root_signaled = True
    if fault == "kill_job":
        child.cancel_tree()
    else:
        child.poll_exit()
    assert child.cleanup_error is not None and child.cleanup_uncertain is False
    finish(child, api)
    assert child.cleanup_uncertain is False


def cleanup_budget_owner(*, callback=None):
    api = FakeAPI()
    api.spec = spec()
    pin = Pin(api)
    validation = Validation(api, pin)
    now, checkpoints = [10.0], []

    def checkpoint(started_at):
        checkpoints.append((started_at, now[0]))
        api.events.append("cleanup_checkpoint")
        if callback is not None:
            return callback(started_at)
        if now[0] >= started_at + 5.0:
            raise RuntimeError("untrusted cleanup deadline diagnostic")

    child = process.WindowsOwnedProcess(
        api.spec,
        pin,
        validation,
        api=api,
        clock=lambda: now[0],
        cleanup_checkpoint=checkpoint,
    )
    return child, api, pin, validation, now, checkpoints


def assert_cleanup_stays_stopped(child, api, checkpoints):
    before = (list(api.events), list(api.close_calls), list(checkpoints))
    child.poll_exit()
    child.cancel_tree()
    child.start()
    assert child.close_after_cleanup() is False
    assert not child.cleanup_complete() and child.cleanup_uncertain
    assert before == (api.events, api.close_calls, checkpoints)


@pytest.mark.parametrize("callback", [False, 0, "callable", object()])
def test_invalid_cleanup_callback_rejects_before_ownership_transfer(callback):
    api = FakeAPI()
    pin = Pin(api)
    validation = Validation(api, pin)
    with pytest.raises(contracts.ProcessError, match="invalid_process_contract"):
        process.WindowsOwnedProcess(spec(), pin, validation, api=api, cleanup_checkpoint=callback)
    assert api.events == [] and validation.closes == pin.releases == 0 and pin.held


def test_cleanup_none_preserves_no_timestamp_and_no_new_clock_calls_on_failure():
    child, api, _, _, now, _ = owner()
    child.start()
    calls = []
    child._clock = lambda: calls.append(now[0]) or now[0]
    child.cancel_tree()
    assert calls == [] and child.cleanup_started_at is None
    finish(child, api)
    assert child.cleanup_started_at is None


@pytest.mark.parametrize("fault", ["open_file0", "initialize_file0", "set_job"])
def test_cleanup_starts_at_early_failure_before_any_resource_retirement(fault):
    child, api, pin, validation, _, checkpoints = cleanup_budget_owner()
    api.fault = fault
    child.start()
    assert child.cleanup_started_at == 10.0
    assert checkpoints and all(started == 10.0 for started, _ in checkpoints)
    assert child.cleanup_complete() and validation.closes == pin.releases == 1
    assert Counter(api.acquired) == Counter(api.closed)
    for index, event in enumerate(api.events):
        if event.startswith("close_") or event in {"validation_close", "pin_release"}:
            assert api.events[index - 1] == api.events[index + 1] == "cleanup_checkpoint"
    with pytest.raises(AttributeError):
        child.cleanup_started_at = 99.0


def test_failed_normal_transient_close_uses_call_entry_time_before_slow_return():
    child, api, pin, validation, now, checkpoints = cleanup_budget_owner()
    api.fault = "close_attributes"
    api.hook = lambda event: now.__setitem__(0, 16.0) if event == "close_attributes" else None
    child.start()
    assert child.cleanup_started_at == 10.0 and checkpoints == [(10.0, 16.0)]
    assert api.close_calls == ["attributes"]
    assert not child._transient[-1].closed and child._transient[-1].attempted
    assert all(not resource.attempted for resource in child._resources)
    assert validation.closes == pin.releases == 0 and pin.held
    assert "kill_job" not in api.events and "kill_root" not in api.events
    assert_cleanup_stays_stopped(child, api, checkpoints)


def test_successful_normal_transient_closes_do_not_begin_terminal_cleanup_budget():
    child, api, pin, validation, now, checkpoints = cleanup_budget_owner()
    api.hook = lambda event: now.__setitem__(0, 16.0) if event == "close_attributes" else None
    child.start()
    assert child.state == "running" and child.cleanup_started_at is None and checkpoints == []
    now[0] = 18.0
    api.root_signaled, api.active = True, 0
    finish(child, api)
    assert child.cleanup_started_at == 18.0
    assert all(started == 18.0 for started, _ in checkpoints)
    assert validation.closes == pin.releases == 1


def test_failure_before_transient_cleanup_keeps_first_time_through_slow_close():
    child, api, pin, validation, now, checkpoints = cleanup_budget_owner()
    api.fault = "set_job"
    api.hook = lambda event: now.__setitem__(0, 16.0) if event == "close_attributes" else None
    child.start()
    assert child.cleanup_started_at == 10.0
    assert checkpoints == [(10.0, 10.0), (10.0, 16.0)]
    assert child._transient[-1].closed and child._transient[-1].attempted
    assert api.close_calls == ["attributes"] and validation.closes == pin.releases == 0
    assert_cleanup_stays_stopped(child, api, checkpoints)


def test_cleanup_expired_precheck_leaves_next_resource_unattempted():
    child, api, pin, validation, now, checkpoints = cleanup_budget_owner()
    child.start()
    api.root_signaled, api.active = True, 0
    child.poll_exit()
    original = child._cleanup_checkpoint

    def expire_between_actions(started_at):
        if api.events[-1] == "cleanup_checkpoint":
            now[0] = started_at + 5.0
        original(started_at)

    child._cleanup_checkpoint = expire_between_actions
    assert child.close_after_cleanup() is False
    assert all(not resource.attempted for resource in child._resources)
    assert validation.closes == pin.releases == 0 and pin.held
    assert_cleanup_stays_stopped(child, api, checkpoints)


@pytest.mark.parametrize(
    "barrier",
    [
        "close_201",
        "close_200",
        "close_100",
        "close_file3",
        "close_file2",
        "close_file1",
        "close_file0",
    ],
)
def test_cleanup_late_successful_close_records_closed_and_stops_next_action(barrier):
    child, api, pin, validation, now, checkpoints = cleanup_budget_owner()
    child.start()
    api.root_signaled, api.active = True, 0
    api.hook = lambda event: now.__setitem__(0, 16.0) if event == barrier else None
    assert child.close_after_cleanup() is False
    resource = next(
        resource for resource in child._resources if "close_" + str(resource.value) == barrier
    )
    assert resource.attempted and resource.closed
    assert api.events[-2:] == [barrier, "cleanup_checkpoint"]
    assert validation.closes == pin.releases == 0 and pin.held
    assert child.cleanup_started_at == 10.0
    assert_cleanup_stays_stopped(child, api, checkpoints)


@pytest.mark.parametrize("barrier", ["validation_close", "pin_release"])
def test_cleanup_late_validation_or_pin_return_is_recorded_but_never_completed(barrier):
    child, api, pin, validation, now, checkpoints = cleanup_budget_owner()
    child.start()
    api.root_signaled, api.active = True, 0
    api.hook = lambda event: now.__setitem__(0, 16.0) if event == barrier else None
    assert child.close_after_cleanup() is False
    assert child._validation_resource.closed and validation.closes == 1
    assert pin.releases == (1 if barrier == "pin_release" else 0)
    assert child._pin_resource.closed is (barrier == "pin_release")
    assert pin.held is (barrier != "pin_release")
    assert api.events[-2:] == [barrier, "cleanup_checkpoint"]
    assert_cleanup_stays_stopped(child, api, checkpoints)


@pytest.mark.parametrize("barrier", ["kill_job", "wait", "exit_code", "active"])
def test_cleanup_late_termination_or_query_stops_all_later_owned_actions(barrier):
    child, api, pin, validation, now, checkpoints = cleanup_budget_owner()
    child.start()
    api.hook = lambda event: now.__setitem__(0, 16.0) if event == barrier else None
    child.cancel_tree()
    child.poll_exit()
    assert child.cleanup_started_at == 10.0
    assert api.events[-2:] == [barrier, "cleanup_checkpoint"]
    assert validation.closes == pin.releases == 0 and pin.held
    if barrier == "kill_job":
        assert child._job_terminated is True
    assert_cleanup_stays_stopped(child, api, checkpoints)


def test_cleanup_late_defensive_root_termination_preserves_request_observation():
    child, api, pin, validation, now, checkpoints = cleanup_budget_owner()
    api.member = False
    api.hook = lambda event: now.__setitem__(0, 16.0) if event == "kill_root" else None
    child.start()
    assert child.cleanup_started_at == 10.0 and child._root_terminated is True
    assert api.events[-2:] == ["kill_root", "cleanup_checkpoint"]
    assert validation.closes == pin.releases == 0 and pin.held
    assert_cleanup_stays_stopped(child, api, checkpoints)


@pytest.mark.parametrize("fault", ["wait", "exit_code", "active", "kill_job"])
def test_cleanup_transient_failure_reobserves_only_with_same_first_deadline(fault):
    child, api, _, _, now, checkpoints = cleanup_budget_owner()
    child.start()
    api.kill_completes = False
    api.fault = fault
    if fault == "exit_code":
        api.root_signaled = True
    if fault == "kill_job":
        child.cancel_tree()
    else:
        child.poll_exit()
    assert child.cleanup_started_at == 10.0 and not child.cleanup_uncertain
    now[0] = 14.0
    finish(child, api)
    assert child.cleanup_started_at == 10.0
    assert all(started == 10.0 for started, _ in checkpoints)


@pytest.mark.parametrize(
    "outcome",
    [False, True, 1, object(), RuntimeError("private data"), SystemExit(2), KeyboardInterrupt()],
)
def test_cleanup_checkpoint_invalid_outcome_latches_once_and_keeps_original_ownership(outcome):
    def fail(_started_at):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    child, api, pin, validation, _, checkpoints = cleanup_budget_owner(callback=fail)
    api.fault = "open_file0"
    child.start()
    assert checkpoints == [(10.0, 10.0)]
    assert child.cleanup_error.code == "cleanup_checkpoint_failed"
    assert "private" not in str(child.cleanup_error)
    assert validation.closes == pin.releases == 0 and pin.held
    assert not child._validation_resource.attempted and not child._pin_resource.attempted
    assert_cleanup_stays_stopped(child, api, checkpoints)


@pytest.mark.parametrize("cancelled", [False, True])
def test_every_tracked_cleanup_query_termination_and_close_is_bracketed(cancelled):
    child, api, pin, validation, _, checkpoints = cleanup_budget_owner()
    child.start()
    api.events.clear()
    if cancelled:
        child.cancel_tree()
    else:
        api.root_signaled, api.active = True, 0
    finish(child, api)
    actions = [
        (index, event) for index, event in enumerate(api.events) if event != "cleanup_checkpoint"
    ]
    assert len(checkpoints) == 2 * len(actions)
    for index, event in actions:
        assert event.startswith("close_") or event in {
            "pin_check",
            "size_file1",
            "size_file2",
            "kill_job",
            "wait",
            "exit_code",
            "active",
            "validation_close",
            "pin_release",
        }
        assert api.events[index - 1] == api.events[index + 1] == "cleanup_checkpoint"
    assert validation.closes == pin.releases == 1
    assert child.cleanup_started_at == 10.0
    assert all(started == 10.0 for started, _ in checkpoints)
