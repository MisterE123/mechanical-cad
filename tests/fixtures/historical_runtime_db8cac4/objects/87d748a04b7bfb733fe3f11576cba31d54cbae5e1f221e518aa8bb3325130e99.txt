"""Unselected Windows worker leaf, with a narrow injectable OS surface.

No Win32 binding happens on import. Production selection deliberately does not
import this module. Fake-API tests prove ordering only, never Windows support.
The existing owner must retain this object and its execution lease until all
cleanup succeeds. Calls are serialized on that worker; UI threads only set the
supplied cancellation token. There is no registry, result authority or retry of
an operation here. The request bytes are untouched file-backed stdin.
The existing worker must poll at its 10 ms observation interval; output can
overshoot on disk between polls. A slow OS call can outlast a deadline until it
returns. Neither output bounds nor timeout is a hard resource sandbox.

The trusted-local-runtime boundary uses documented pathname CreateProcessW and
DLL loading. Image-path observations are not atomic image authentication. No
PID lookup, process-name search, shell, breakaway or uncontained fallback exists.
"""

from __future__ import annotations

import math
import ntpath
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .backend_platform import (
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    LaunchObservation,
    LaunchSpec,
    LaunchValidation,
    ProcessError,
    RuntimePin,
)

WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
CREATE_FLAGS = 0x00000004 | 0x00080000 | 0x00000400 | 0x08000000
HANDLE_LIST = 0x00020002
JOB_LIST = 0x0002000D


def command_line(spec: LaunchSpec, descriptor_handle: int) -> str:
    """CRT quoting, explicit application, fixed flags and decimal data handle."""
    if type(descriptor_handle) is not int or not 0 < descriptor_handle < 2**64 - 1:
        raise ProcessError("invalid_descriptor_handle")
    for path in (spec.bundle.python_path, spec.bundle.root):
        drive, tail = ntpath.splitdrive(path)
        if (
            len(drive) != 2
            or drive[1] != ":"
            or not drive[0].isascii()
            or not drive[0].isalpha()
            or not tail.startswith(("/", "\\"))
            or any(char in path for char in ("\0", '"', "%"))
        ):
            raise ProcessError("runtime_path_unsupported")
    if ntpath.basename(spec.bundle.python_path).lower() != "python.exe":
        raise ProcessError("direct_interpreter_required")
    line = subprocess.list2cmdline(
        [
            spec.bundle.python_path,
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            "-c",
            spec.bootstrap,
            str(descriptor_handle),
        ]
    )
    try:
        units = len(line.encode("utf-16-le")) // 2 + 1
    except UnicodeEncodeError as exc:
        raise ProcessError("invalid_unicode") from exc
    if units > 32767:
        raise ProcessError("command_line_too_long")
    return line


def environment_block(spec: LaunchSpec) -> str:
    block = (
        "\0".join(
            f"{key}={value}"
            for key, value in sorted(spec.environment, key=lambda pair: pair[0].upper())
        )
        + "\0\0"
    )
    try:
        if len(block.encode("utf-16-le")) // 2 > 32767:
            raise ProcessError("environment_too_long")
    except UnicodeEncodeError as exc:
        raise ProcessError("invalid_unicode") from exc
    return block


@dataclass(frozen=True)
class CreatedProcess:
    process: int
    thread: int


class ProcessAPI(Protocol):
    """All returned resources transfer immediately; failed calls return none.

    create_suspended either returns both retained handles or reports failure.
    Atomic acquisition helpers must unwind their own partial local resources.
    No guarantee about undocumented OS rollback on failed creation is implied.
    """

    def open_file(self) -> object: ...
    def initialize_file(self, file: object, data: bytes) -> None: ...
    def duplicate(self, file: object, *, writable: bool) -> int: ...
    def create_job(self) -> int: ...
    def configure_job(self, job: int) -> None: ...
    def create_attributes(self) -> object: ...
    def set_handles(self, attributes: object, handles: tuple[int, ...]) -> None: ...
    def set_job(self, attributes: object, job: int) -> None: ...
    def create_suspended(self, spec, line, environment, handles, attributes) -> CreatedProcess: ...
    def is_in_job(self, process: int, job: int) -> bool: ...
    def observe(self, process: int) -> LaunchObservation: ...
    def resume(self, thread: int) -> int: ...
    def wait(self, process: int) -> int: ...
    def exit_code(self, process: int) -> int: ...
    def active_processes(self, job: int) -> int: ...
    def terminate_job(self, job: int) -> None: ...
    def terminate_process(self, process: int) -> None: ...
    def close_handle(self, handle: int) -> None: ...
    def close_attributes(self, attributes: object) -> None: ...
    def close_file(self, file: object) -> None: ...
    def file_size(self, file: object) -> int: ...
    def read_file(self, file: object, limit: int) -> bytes: ...


@dataclass
class _Resource:
    value: object
    close: Callable
    attempted: bool = False
    closed: bool = False


class WindowsOwnedProcess:
    """One finite handle owner; construction does not launch anything.

    Constructor success transfers validation resources and the acquired shared
    pin to this object. Constructor failure leaves them with the caller. start
    never throws away an owner on partial launch failure. close_after_cleanup
    returns False while termination, queries or any resource closure is unsafe.
    A failed close is not retried: a numeric handle may have been reused. Keep
    the pin/lease and diagnose cleanup_pending rather than claiming completion.
    """

    def __init__(
        self,
        spec: LaunchSpec,
        pin: RuntimePin,
        validation: LaunchValidation,
        *,
        api: ProcessAPI | None = None,
        clock=time.monotonic,
        cancelled=lambda: False,
        deadline: float | None = None,
        cleanup_checkpoint=None,
    ):
        if type(spec) is not LaunchSpec:
            raise ProcessError("captured_launch_required")
        if pin.bundle_id != spec.bundle.bundle_id or pin.mode != "shared":
            raise ProcessError("shared_bundle_pin_required")
        for callback in (
            pin.assert_held,
            pin.release,
            validation.before_create,
            validation.after_create,
            validation.close,
            clock,
            cancelled,
        ):
            if not callable(callback):
                raise ProcessError("invalid_process_contract")
        if cleanup_checkpoint is not None and not callable(cleanup_checkpoint):
            raise ProcessError("invalid_process_contract")
        if deadline is not None:
            try:
                finite = type(deadline) in (int, float) and math.isfinite(deadline)
            except OverflowError:
                finite = False
            if not finite:
                raise ProcessError("invalid_process_deadline")
            if deadline <= clock():
                raise ProcessError("timeout")
        pin.assert_held()
        command_line(spec, 1)
        self._environment = environment_block(spec)
        self._api = api if api is not None else Win32API()
        self._spec, self._pin, self._validation = spec, pin, validation
        self._clock, self._cancelled = clock, cancelled
        self._cleanup_checkpoint = cleanup_checkpoint
        self._cleanup_started_at = None
        self._cleanup_stopped = False
        self._resources: list[_Resource] = []
        self._transient: list[_Resource] = []
        self._files: list[object] = []
        self._job = self._process = self._thread = None
        self._membership = False
        self._job_terminated = self._root_terminated = False
        self._deadline = deadline
        self._exit_code = None
        self._quiescent = self._closed = self._poisoned = False
        self._validation_resource = _Resource(validation, lambda value: value.close())
        self._pin_resource = _Resource(pin, lambda value: value.release())
        self.state = "created"
        self.error: ProcessError | None = None
        self.cleanup_error: ProcessError | None = None
        self.observation: LaunchObservation | None = None
        self.attempted_start = self.resumed = False

    @property
    def tree_quiescent(self):
        """Original root termination plus zero owned-job active processes."""
        return self._quiescent

    @property
    def cleanup_uncertain(self):
        """An ambiguous close or rejected cleanup checkpoint prevents completion."""
        return self._poisoned

    @property
    def cleanup_started_at(self):
        """Original tracked cleanup start, never renewed by later observations."""
        return self._cleanup_started_at

    def _stop_cleanup(self):
        self._cleanup_stopped = self._poisoned = True
        self.cleanup_error = ProcessError("cleanup_checkpoint_failed")
        if self.error is None:
            self.error = ProcessError("cleanup_pending")
        self.state = "cleanup_pending"

    def _begin_cleanup(self, started_at=None):
        if self._cleanup_checkpoint is None or self._cleanup_started_at is not None:
            return
        if self._cleanup_stopped:
            return
        try:
            started_at = self._clock() if started_at is None else started_at
            if type(started_at) not in (int, float) or not math.isfinite(started_at):
                raise ValueError
            self._cleanup_started_at = started_at
        except Exception:
            self._stop_cleanup()

    def _check_cleanup(self):
        if self._cleanup_stopped:
            return False
        if self._cleanup_checkpoint is None or self._cleanup_started_at is None:
            return True
        try:
            if self._cleanup_checkpoint(self._cleanup_started_at) is not None:
                raise ValueError
        except BaseException:
            self._stop_cleanup()
            return False
        return True

    def _cleanup_query(self, query, *args):
        if not self._check_cleanup():
            raise self.cleanup_error
        try:
            return query(*args)
        finally:
            if not self._check_cleanup():
                raise self.cleanup_error

    def _own(self, value, close, *, transient=False):
        (self._transient if transient else self._resources).append(_Resource(value, close))
        return value

    def _fail(self, code, exc=None, *, cleanup_started_at=None):
        self._begin_cleanup(cleanup_started_at)
        failure = exc if isinstance(exc, ProcessError) else ProcessError(code)
        if self.error is None:
            self.error = failure
        self.state = "cleanup_pending"

    def _checkpoint(self):
        if self._cancelled():
            raise ProcessError("cancelled")
        if self.error is not None:
            raise self.error
        if self._deadline is not None and self._clock() >= self._deadline:
            raise ProcessError("timeout")

    def _check_pin(self):
        """Check retained ownership independently of the operation deadline.

        Quiescent output may be read after the deadline; it still requires the
        same held shared pin. A lost pin invalidates output, but never gates
        termination, handle observation or resource closure.
        """
        try:
            if self._pin.bundle_id != self._spec.bundle.bundle_id or self._pin.mode != "shared":
                raise ProcessError("bundle_pin_lost")
            self._cleanup_query(self._pin.assert_held)
        except Exception as exc:
            raise ProcessError("bundle_pin_lost") from exc

    def _check_stream_limits(self):
        """Both streams must be bounded, including the stream not being read."""
        for file, limit in zip(self._files[1:3], (MAX_STDOUT_BYTES, MAX_STDERR_BYTES), strict=True):
            if self._cleanup_query(self._api.file_size, file) > limit:
                raise ProcessError("output_limit")

    def start(self):
        if self.state != "created":
            if self.error is not None:
                return self
            raise ProcessError("already_started")
        self.state = "starting"
        try:
            if self._deadline is None:
                self._deadline = self._clock() + self._spec.timeout
            self._checkpoint()
            # Every acquisition is owned before another API call/checkpoint.
            for data in (self._spec.request_payload, b"", b"", self._spec.descriptor_payload):
                self._files.append(self._own(self._api.open_file(), self._api.close_file))
                self._checkpoint()
                self._api.initialize_file(self._files[-1], data)
                self._checkpoint()
            self._job = self._own(self._api.create_job(), self._api.close_handle)
            self._checkpoint()
            self._api.configure_job(self._job)
            self._checkpoint()
            handles = []
            for index, file in enumerate(self._files):
                handles.append(
                    self._own(
                        self._api.duplicate(file, writable=index in (1, 2)),
                        self._api.close_handle,
                        transient=True,
                    )
                )
                self._checkpoint()
            attributes = self._own(
                self._api.create_attributes(), self._api.close_attributes, transient=True
            )
            self._checkpoint()
            self._api.set_handles(attributes, tuple(handles))
            self._checkpoint()
            self._api.set_job(attributes, self._job)
            self._checkpoint()
            line = command_line(self._spec, handles[3])
            self._check_pin()
            self._validation.before_create(self._spec)
            self._checkpoint()
            self._check_pin()
            self._checkpoint()
            self.attempted_start = True
            child = self._api.create_suspended(
                self._spec, line, self._environment, tuple(handles), attributes
            )
            self._process = self._own(child.process, self._api.close_handle)
            self._thread = self._own(child.thread, self._api.close_handle)
            self._close_resources(self._transient)
            self._checkpoint()
            self._membership = self._api.is_in_job(self._process, self._job) is True
            if not self._membership:
                raise ProcessError("job_membership_failed")
            self._checkpoint()
            self.observation = self._api.observe(self._process)
            if type(self.observation) is not LaunchObservation:
                raise ProcessError("invalid_launch_observation")
            self._validation.after_create(self._spec, self.observation)
            self._check_pin()
            self._checkpoint()
            if self._api.resume(self._thread) != 1:
                raise ProcessError("unexpected_suspend_count")
            self.resumed = True
            self._check_pin()
            self._checkpoint()
            self.state = "running"
        except Exception as exc:
            self._fail("launch_failed", exc)
        finally:
            self._close_resources(self._transient)
        if self.error is not None:
            self._terminate()
            self.close_after_cleanup()
        return self

    def _close_resources(self, resources):
        for resource in reversed(resources):
            if resource.attempted:
                continue
            if not self._check_cleanup():
                return
            started_at = (
                self._clock()
                if self._cleanup_checkpoint is not None and self._cleanup_started_at is None
                else None
            )
            resource.attempted = True
            try:
                resource.close(resource.value)
                resource.closed = True
            except Exception as exc:
                self._poisoned = True
                self.cleanup_error = (
                    exc if isinstance(exc, ProcessError) else ProcessError("resource_close_failed")
                )
                self._fail("cleanup_pending", cleanup_started_at=started_at)
            if not self._check_cleanup():
                return

    def _terminate(self):
        # After quiescence, close may already have retired these handle values.
        # A later cancel/cleanup error must never use a closed, reusable value.
        if self._quiescent or self._cleanup_stopped:
            return
        for handle, method, flag in (
            (self._job, self._api.terminate_job, "_job_terminated"),
            (
                self._process if not self._membership else None,
                self._api.terminate_process,
                "_root_terminated",
            ),
        ):
            if handle is not None and not getattr(self, flag):
                if not self._check_cleanup():
                    return
                try:
                    method(handle)
                    setattr(self, flag, True)
                except Exception as exc:
                    self.cleanup_error = (
                        exc if isinstance(exc, ProcessError) else ProcessError("termination_failed")
                    )
                if not self._check_cleanup():
                    return

    def cancel_tree(self, reason="cancelled"):
        if self._closed:
            return
        if reason not in {"cancelled", "timeout", "output_limit", "unexpected_descendants"}:
            reason = "cancelled"
        self._fail(reason)
        self._terminate()

    def poll_exit(self):
        """Nonblocking root observation. An exit code is not cleanup/ready."""
        if self._closed or self._cleanup_stopped:
            return self._exit_code
        try:
            self._check_pin()
        except Exception as exc:
            self._fail("bundle_pin_lost", exc)
        if self._quiescent:
            return self._exit_code
        if self.state == "created":
            return None
        try:
            self._checkpoint()
            if self.resumed:
                self._check_stream_limits()
        except Exception as exc:
            self._fail("poll_failed", exc)
        if self.error is not None:
            self._terminate()
        try:
            if self._process is not None and self._exit_code is None:
                status = self._cleanup_query(self._api.wait, self._process)
                if status == WAIT_OBJECT_0:
                    code = self._cleanup_query(self._api.exit_code, self._process)
                    if type(code) is not int or not 0 <= code <= 0xFFFFFFFF:
                        raise ProcessError("invalid_exit_code")
                    self._exit_code = code
                elif status != WAIT_TIMEOUT:
                    raise ProcessError("unexpected_wait_status")
            active = (
                self._cleanup_query(self._api.active_processes, self._job)
                if self._job is not None
                else 0
            )
            if type(active) is not int or active < 0:
                raise ProcessError("invalid_job_accounting")
            root_done = self._process is None or self._exit_code is not None
            if root_done and active and self.error is None:
                self.cancel_tree("unexpected_descendants")
            self._quiescent = root_done and active == 0
            if self._quiescent:
                self.state = "cleanup_pending"
        except Exception as exc:
            self.cleanup_error = (
                exc if isinstance(exc, ProcessError) else ProcessError("cleanup_query_failed")
            )
            self._fail("cleanup_pending")
            self._terminate()
        if self.error is None:
            # A writer can grow either stream after the earlier size check,
            # including during the final root wait or job accounting query.
            # Quiescence remains valid even if these result checks fail, so
            # cleanup can still close every resource without a usable pin.
            try:
                if self._quiescent and self.resumed:
                    self._check_stream_limits()
                self._check_pin()
            except Exception as exc:
                self._fail("poll_failed", exc)
                self._terminate()
        return self._exit_code

    def read_output(self, *, stderr=False):
        """Bounded bytes for the transport validator, only after tree quiescence."""
        self.poll_exit()
        if not self._quiescent or self._closed or self.error is not None:
            raise ProcessError("output_unavailable")
        limit = MAX_STDERR_BYTES if stderr else MAX_STDOUT_BYTES
        try:
            self._check_pin()
            self._check_stream_limits()
            data = self._cleanup_query(
                self._api.read_file, self._files[2 if stderr else 1], limit + 1
            )
            if type(data) is not bytes or len(data) > limit:
                raise ProcessError("output_limit")
            self._check_stream_limits()
            self._check_pin()
        except Exception as exc:
            self._fail("output_read_failed", exc)
            raise self.error from None
        return data

    def close_after_cleanup(self):
        if self._closed:
            return True
        self._begin_cleanup()
        if self._cleanup_stopped:
            return False
        if self.state == "created":
            self.cancel_tree()
        self.poll_exit()
        if not self._quiescent:
            return False
        self._close_resources(self._transient)
        self._close_resources(self._resources)
        if self._poisoned:
            return False
        self._close_resources([self._validation_resource])
        if self._poisoned:
            return False
        self._close_resources([self._pin_resource])
        if self._poisoned:
            return False
        self._closed = True
        self.state = "closed"
        return True

    def cleanup_complete(self):
        """True only after root exit, job-empty, files/anchors/handles and pin close."""
        return self._closed


class Win32API:
    """Documented ctypes adapter, explicitly gated to native Windows x64.

    Not production-admitted or Windows-qualified. Structures mirror Windows SDK
    winnt.h/processthreadsapi.h: fixed-width DWORD/WORD/BOOL/LARGE_INTEGER and
    pointer-width HANDLE/SIZE_T/ULONG_PTR; no packed structures. Bound functions
    declare every argtype/restype. GetLastError is captured immediately through
    use_last_error, with no environment/model/path in diagnostics.

    References: Microsoft Learn CreateProcessW, UpdateProcThreadAttribute,
    InitializeProcThreadAttributeList, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION, WaitForSingleObject. Only Create's
    handle-list duplicates are inheritable; the unnamed job and returned root
    and thread have NULL security attributes (noninheritable). TemporaryFile
    owns its noninheritable source handle and deletes its own backing file.
    Explicit inheritance does not control another add-on's concurrent blanket
    inheritance: the short-lived duplicates can leak into such a child. The job
    is never duplicated or inherited, preserving its last-close backstop.
    """

    def __init__(self, *, temporary_directory: str | None = None):
        if os.name != "nt":
            raise ProcessError("native_windows_required")
        import ctypes as c
        import msvcrt
        import platform
        import tempfile

        if c.sizeof(c.c_void_p) != 8 or platform.machine().lower() not in {"amd64", "x86_64"}:
            raise ProcessError("windows_x64_required")
        # The integration owner must supply its validated private job directory.
        # Do not silently use inherited TEMP/TMP or a runtime-cache directory.
        if type(temporary_directory) is not str or not ntpath.isabs(temporary_directory):
            raise ProcessError("private_job_directory_required")
        self.temporary_directory = temporary_directory
        self.c, self.msvcrt, self.tempfile = c, msvcrt, tempfile
        D, W, B, H, P = c.c_uint32, c.c_uint16, c.c_int32, c.c_void_p, c.c_void_p
        Q, S, L = c.c_uint64, c.c_size_t, c.c_int64

        class BasicLimit(c.Structure):
            _fields_ = [
                ("ProcessTime", L),
                ("JobTime", L),
                ("Flags", D),
                ("MinWorkingSet", S),
                ("MaxWorkingSet", S),
                ("ActiveLimit", D),
                ("Affinity", S),
                ("Priority", D),
                ("Scheduling", D),
            ]

        class ExtendedLimit(c.Structure):
            _fields_ = [
                ("Basic", BasicLimit),
                ("IO", Q * 6),
                ("ProcessMemory", S),
                ("JobMemory", S),
                ("PeakProcessMemory", S),
                ("PeakJobMemory", S),
            ]

        class Accounting(c.Structure):
            _fields_ = [
                ("UserTime", L),
                ("KernelTime", L),
                ("PeriodUserTime", L),
                ("PeriodKernelTime", L),
                ("PageFaults", D),
                ("TotalProcesses", D),
                ("ActiveProcesses", D),
                ("TerminatedProcesses", D),
            ]

        class Startup(c.Structure):
            _fields_ = [
                ("cb", D),
                ("Reserved", c.c_wchar_p),
                ("Desktop", c.c_wchar_p),
                ("Title", c.c_wchar_p),
                ("X", D),
                ("Y", D),
                ("XSize", D),
                ("YSize", D),
                ("XChars", D),
                ("YChars", D),
                ("Fill", D),
                ("Flags", D),
                ("Show", W),
                ("ReservedSize", W),
                ("Reserved2", P),
                ("Input", H),
                ("Output", H),
                ("Error", H),
            ]

        class StartupEx(c.Structure):
            _fields_ = [("StartupInfo", Startup), ("Attributes", P)]

        class ProcessInfo(c.Structure):
            _fields_ = [("Process", H), ("Thread", H), ("PID", D), ("TID", D)]

        self.H, self.D = H, D
        self.ExtendedLimit, self.Accounting = ExtendedLimit, Accounting
        self.StartupEx, self.ProcessInfo = StartupEx, ProcessInfo
        # Fail explicitly on a surprising ABI rather than issue a malformed call.
        if tuple(
            map(c.sizeof, (BasicLimit, ExtendedLimit, Accounting, Startup, StartupEx, ProcessInfo))
        ) != (64, 144, 48, 104, 112, 24):
            raise ProcessError("unsupported_win32_abi")
        try:
            k = c.WinDLL("kernel32", use_last_error=True)
        except (OSError, AttributeError) as exc:
            raise ProcessError("required_win32_api_missing") from exc
        self.k = k
        signatures = {
            "CreateJobObjectW": (H, [P, c.c_wchar_p]),
            "SetInformationJobObject": (B, [H, c.c_int32, P, D]),
            "QueryInformationJobObject": (B, [H, c.c_int32, P, D, P]),
            "InitializeProcThreadAttributeList": (B, [P, D, D, c.POINTER(S)]),
            "UpdateProcThreadAttribute": (B, [P, D, S, P, S, P, P]),
            "DeleteProcThreadAttributeList": (None, [P]),
            "CreateProcessW": (
                B,
                [
                    c.c_wchar_p,
                    c.c_wchar_p,
                    P,
                    P,
                    B,
                    D,
                    P,
                    c.c_wchar_p,
                    c.POINTER(StartupEx),
                    c.POINTER(ProcessInfo),
                ],
            ),
            "GetCurrentProcess": (H, []),
            "DuplicateHandle": (B, [H, H, H, c.POINTER(H), D, B, D]),
            "IsProcessInJob": (B, [H, H, c.POINTER(B)]),
            "GetProcessId": (D, [H]),
            "GetProcessTimes": (B, [H, P, P, P, P]),
            "QueryFullProcessImageNameW": (B, [H, D, c.c_wchar_p, c.POINTER(D)]),
            "ResumeThread": (D, [H]),
            "WaitForSingleObject": (D, [H, D]),
            "GetExitCodeProcess": (B, [H, c.POINTER(D)]),
            "TerminateJobObject": (B, [H, D]),
            "TerminateProcess": (B, [H, D]),
            "CloseHandle": (B, [H]),
        }
        try:
            for name, (result, arguments) in signatures.items():
                function = getattr(k, name)
                function.restype, function.argtypes = result, arguments
        except AttributeError as exc:
            raise ProcessError("required_win32_api_missing") from exc

    def _check(self, success, operation):
        if not success:
            raise ProcessError("win32_error", operation=operation, winerror=self.c.get_last_error())
        return success

    def open_file(self):
        return self.tempfile.TemporaryFile(mode="w+b", dir=self.temporary_directory)

    @staticmethod
    def initialize_file(file, data):
        # The owner already retains this file if write/flush/rewind fails.
        if file.write(data) != len(data):
            raise ProcessError("short_input_write")
        file.flush()
        file.seek(0)

    def duplicate(self, file, *, writable):
        result = self.H()
        current = self.k.GetCurrentProcess()
        # Read-only descriptor/stdin; write-only stdout/stderr, no SAME_ACCESS.
        access = 0x40000000 if writable else 0x80000000
        self._check(
            self.k.DuplicateHandle(
                current,
                self.msvcrt.get_osfhandle(file.fileno()),
                current,
                self.c.byref(result),
                access,
                True,
                0,
            ),
            "DuplicateHandle",
        )
        return result.value

    def create_job(self):
        return self._check(self.k.CreateJobObjectW(None, None), "CreateJobObjectW")

    def configure_job(self, job):
        info = self.ExtendedLimit()
        info.Basic.Flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, no breakaway.
        self._check(
            self.k.SetInformationJobObject(job, 9, self.c.byref(info), self.c.sizeof(info)),
            "SetInformationJobObject",
        )

    def create_attributes(self):
        size = self.c.c_size_t()
        self.c.set_last_error(0)
        result = self.k.InitializeProcThreadAttributeList(None, 2, 0, self.c.byref(size))
        if result or self.c.get_last_error() != 122 or not 0 < size.value < 65536:
            raise ProcessError("attribute_size_failed")
        buffer = self.c.create_string_buffer(size.value)
        self._check(
            self.k.InitializeProcThreadAttributeList(buffer, 2, 0, self.c.byref(size)),
            "InitializeProcThreadAttributeList",
        )
        return _Attributes(buffer)

    def _attribute(self, attributes, key, values):
        array = (self.H * len(values))(*values)
        # Retain storage even on update failure, until Delete... finishes.
        attributes.values.append(array)
        self._check(
            self.k.UpdateProcThreadAttribute(
                attributes.buffer, 0, key, array, self.c.sizeof(array), None, None
            ),
            "UpdateProcThreadAttribute",
        )

    def set_handles(self, attributes, handles):
        self._attribute(attributes, HANDLE_LIST, handles)

    def set_job(self, attributes, job):
        self._attribute(attributes, JOB_LIST, (job,))

    def create_suspended(self, spec, line, environment, handles, attributes):
        startup = self.StartupEx()
        startup.StartupInfo.cb = self.c.sizeof(startup)
        startup.StartupInfo.Flags = 0x00000100  # STARTF_USESTDHANDLES.
        startup.StartupInfo.Input, startup.StartupInfo.Output, startup.StartupInfo.Error = handles[
            :3
        ]
        startup.Attributes = self.c.cast(attributes.buffer, self.c.c_void_p)
        process = self.ProcessInfo()
        line_buffer = self.c.create_unicode_buffer(line)
        env_buffer = self.c.create_unicode_buffer(environment)
        self._check(
            self.k.CreateProcessW(
                spec.bundle.python_path,
                line_buffer,
                None,
                None,
                True,
                CREATE_FLAGS,
                env_buffer,
                spec.bundle.root,
                self.c.byref(startup),
                self.c.byref(process),
            ),
            "CreateProcessW",
        )
        return CreatedProcess(process.Process, process.Thread)

    def is_in_job(self, process, job):
        result = self.c.c_int32()
        self._check(self.k.IsProcessInJob(process, job, self.c.byref(result)), "IsProcessInJob")
        return bool(result.value)

    def observe(self, process):
        pid = self._check(self.k.GetProcessId(process), "GetProcessId")
        times = [self.c.c_uint64() for _ in range(4)]
        self._check(
            self.k.GetProcessTimes(process, *(self.c.byref(t) for t in times)), "GetProcessTimes"
        )
        size = self.D(32768)
        path = self.c.create_unicode_buffer(size.value)
        self._check(
            self.k.QueryFullProcessImageNameW(process, 0, path, self.c.byref(size)),
            "QueryFullProcessImageNameW",
        )
        return LaunchObservation(pid, times[0].value, path.value)

    def resume(self, thread):
        result = self.k.ResumeThread(thread)
        self._check(result != 0xFFFFFFFF, "ResumeThread")
        return result

    def wait(self, process):
        result = self.k.WaitForSingleObject(process, 0)
        self._check(result != 0xFFFFFFFF, "WaitForSingleObject")
        return result

    def exit_code(self, process):
        result = self.D()
        self._check(self.k.GetExitCodeProcess(process, self.c.byref(result)), "GetExitCodeProcess")
        return result.value

    def active_processes(self, job):
        info = self.Accounting()
        self._check(
            self.k.QueryInformationJobObject(job, 1, self.c.byref(info), self.c.sizeof(info), None),
            "QueryInformationJobObject",
        )
        return info.ActiveProcesses

    def terminate_job(self, job):
        self._check(self.k.TerminateJobObject(job, 1), "TerminateJobObject")

    def terminate_process(self, process):
        self._check(self.k.TerminateProcess(process, 1), "TerminateProcess")

    def close_handle(self, handle):
        self._check(self.k.CloseHandle(handle), "CloseHandle")

    def close_attributes(self, attributes):
        self.k.DeleteProcThreadAttributeList(attributes.buffer)

    @staticmethod
    def close_file(file):
        file.close()

    @staticmethod
    def file_size(file):
        return os.fstat(file.fileno()).st_size

    @staticmethod
    def read_file(file, limit):
        file.seek(0)
        return file.read(limit)


@dataclass
class _Attributes:
    buffer: object
    values: list = field(default_factory=list)
