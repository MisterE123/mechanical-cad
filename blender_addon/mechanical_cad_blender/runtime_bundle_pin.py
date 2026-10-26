"""Unselected worker-only OS lifetime pins; no runtime/cache deletion exists.

Shared pins cover exact verification and use; exclusive pins cover publication.
Every pin has its own original, non-inheritable handle. The stable lock lives at
cache_root/.bundle-pins/<bundle_id>.lock, outside the immutable bundle directory.
Never unlink, replace, truncate or repair these files, including after a crash.
There is no lock conversion: release, reacquire and fully reverify after any gap.

Acquisition uses a fixed monotonic deadline and nonblocking OS lock attempts.
Cancellation/deadlines are observed between calls; a slow filesystem/OS call can
outlast the deadline. This is a trusted local filesystem contract, not protection
against hostile same-user mutation or a hard real-time bound. Network filesystems
and fork-sharing of acquired owners are outside this leaf's supported contract.

All callers serialize ownership on a worker and retain their execution lease
until release succeeds. A close/unlock failure permanently poisons this owner;
never retry a numeric handle after uncertain closure (handle-reuse/ABA risk).
Acquisition failures with uncertain cleanup expose the owner as error.pin, which
must likewise be retained. No destructor silently releases an abandoned owner.

Linux parent death may leave a backend child alive after its parent-only pin is
released. Thus all cache retirement remains deferred; a free lock proves neither
child containment nor safe removal. Windows process/Job Object cleanup is owned
separately. Fake Win32 tests are not genuine Windows qualification.
"""

from __future__ import annotations

import errno
import math
import os
import re
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

POLL_SECONDS = 0.01
MAX_TIMEOUT_SECONDS = 300.0
_BUNDLE_ID = re.compile(r"[0-9a-f]{64}\Z")
_REPARSE = 0x400


class BundlePinError(RuntimeError):
    """Bounded diagnostic; pin is set when cleanup ownership must be retained."""

    def __init__(self, code, *, pin=None):
        self.code = code
        self.pin = pin
        super().__init__(code)


class BundlePinCancelled(BundlePinError):
    pass


class BundlePinTimeout(BundlePinError):
    pass


@dataclass(frozen=True)
class _Info:
    identity: tuple
    directory: bool
    regular: bool
    links: int
    reparse: bool = False


def _path_info(path):
    info = path.lstat()
    return _Info(
        (info.st_dev, info.st_ino),
        stat.S_ISDIR(info.st_mode),
        stat.S_ISREG(info.st_mode),
        0 if stat.S_ISDIR(info.st_mode) else info.st_nlink,
        stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE),
    )


def _validate(info, *, directory):
    valid_kind = info.directory if directory else info.regular and info.links == 1
    if info.reparse or not valid_kind:
        raise BundlePinError("unsafe_pin_path")


@dataclass
class _Anchor:
    path: Path
    handle: object
    directory: bool
    path_info: _Info | None
    handle_info: _Info | None = None
    close_attempted: bool = False
    closed: bool = False


class RuntimeBundlePin:
    """Already-held pin implementing BundlePin and RuntimePin structurally.

    Construct through acquire_bundle_pin, never directly. assert_held performs
    bounded filesystem identity checks, not runtime verification or CAD work.
    An assertion failure permanently revokes this pin, but release still cleans
    its original handles. release failure cannot become success on a later call.
    """

    def __init__(self, bundle_id, mode, api):
        self._bundle_id, self._mode, self._api = bundle_id, mode, api
        self._anchors = []
        self._locked = False
        self._state = "acquiring"
        self._guard = threading.Lock()

    @property
    def bundle_id(self):
        return self._bundle_id

    @property
    def mode(self):
        return self._mode

    def _own(self, path, *, directory):
        # Snapshot before open, then transfer the handle immediately, even when
        # metadata inspection fails. No post-open failure loses that handle.
        before = _path_info(path) if path.exists() or path.is_symlink() else None
        if before is not None:
            _validate(before, directory=directory)
        parent = self._anchors[-1].handle if self._anchors else None
        handle = self._api.open(path, directory=directory, parent=parent)
        anchor = _Anchor(path, handle, directory, before)
        self._anchors.append(anchor)
        actual = self._api.info(handle)
        _validate(actual, directory=directory)
        after = _path_info(path)
        _validate(after, directory=directory)
        if before is not None and before != after:
            raise BundlePinError("pin_path_changed")
        self._api.check_path_identity(actual, after)
        anchor.path_info, anchor.handle_info = after, actual

    def _check_anchors(self):
        for anchor in self._anchors:
            current = _path_info(anchor.path)
            actual = self._api.info(anchor.handle)
            _validate(current, directory=anchor.directory)
            _validate(actual, directory=anchor.directory)
            if current != anchor.path_info or actual != anchor.handle_info:
                raise BundlePinError("pin_path_changed")
            self._api.check_path_identity(actual, current)

    def assert_held(self):
        if not self._guard.acquire(blocking=False):
            raise BundlePinError("pin_owner_busy", pin=self)
        try:
            if self._state != "held" or not self._locked:
                raise BundlePinError("pin_not_held", pin=self)
            try:
                self._check_anchors()
            except Exception as exc:
                self._state = "revoked"
                raise BundlePinError("pin_identity_unavailable", pin=self) from exc
        finally:
            self._guard.release()

    def release(self):
        """Attempt each original resource once, including after revocation."""
        if not self._guard.acquire(blocking=False):
            raise BundlePinError("pin_owner_busy", pin=self)
        try:
            if self._state == "released":
                return
            if self._state == "uncertain":
                raise BundlePinError("pin_release_uncertain", pin=self)
            self._state = "releasing"
            failure = None
            if self._locked:
                # Never retry even when the OS reports an uncertain unlock.
                self._locked = False
                try:
                    self._api.unlock(self._anchors[-1].handle)
                except BaseException as exc:
                    failure = exc
            for anchor in reversed(self._anchors):
                if anchor.close_attempted:
                    continue
                anchor.close_attempted = True
                try:
                    self._api.close(anchor.handle)
                    anchor.closed = True
                except BaseException as exc:
                    failure = failure or exc
            self._state = "uncertain" if failure is not None else "released"
            if failure is not None:
                raise BundlePinError("pin_release_uncertain", pin=self) from failure
        finally:
            self._guard.release()


def acquire_bundle_pin(
    cache_root,
    bundle_id: str,
    mode: Literal["shared", "exclusive"],
    *,
    timeout=30.0,
    cancelled=lambda: False,
):
    """Acquire on a worker; cache_root is an existing private runtime directory.

    It is the same root supplied to materialize_bundle, NOT the final bundle
    directory. Only .bundle-pins and its stable per-bundle file may be created.
    No runtime directory, PID marker, timestamp or file contents are touched.
    """
    return _acquire(cache_root, bundle_id, mode, timeout=timeout, cancelled=cancelled)


def _acquire(
    cache_root,
    bundle_id,
    mode,
    *,
    timeout,
    cancelled,
    api=None,
    clock=time.monotonic,
    sleep=time.sleep,
):
    if threading.current_thread() is threading.main_thread():
        raise BundlePinError("worker_acquisition_required")
    if type(bundle_id) is not str or _BUNDLE_ID.fullmatch(bundle_id) is None:
        raise BundlePinError("invalid_bundle_id")
    if type(mode) is not str or mode not in {"shared", "exclusive"}:
        raise BundlePinError("invalid_pin_mode")
    if (
        type(timeout) not in (int, float)
        or not math.isfinite(timeout)
        or not 0 < timeout <= MAX_TIMEOUT_SECONDS
    ):
        raise BundlePinError("invalid_pin_timeout")
    if not callable(cancelled):
        raise BundlePinError("invalid_pin_cancellation")
    raw = os.fspath(cache_root)
    if not isinstance(raw, str) or not raw or "\0" in raw or len(raw) > 32000:
        raise BundlePinError("invalid_cache_root")
    # Reject parent traversal before normalization can erase its ancestry.
    if not os.path.isabs(raw) or ".." in Path(raw).parts:
        raise BundlePinError("absolute_cache_root_required")
    root = Path(raw)
    if len(root.parts) > 128:
        raise BundlePinError("cache_path_too_deep")
    if os.name == "nt":
        # Initial contract permits ordinary drive-absolute paths only, not UNC,
        # device paths, alternate streams or silently normalized components.
        if (
            len(root.drive) != 2
            or root.drive[1] != ":"
            or any(":" in part or part.endswith((".", " ")) for part in root.parts[1:])
        ):
            raise BundlePinError("unsupported_windows_cache_path")
    deadline = clock() + float(timeout)

    def checkpoint():
        if cancelled():
            raise BundlePinCancelled("pin_acquisition_cancelled")
        if clock() >= deadline:
            raise BundlePinTimeout("pin_acquisition_timeout")

    checkpoint()
    api = api if api is not None else (_PosixAPI() if os.name == "posix" else _Win32API())
    pin = RuntimeBundlePin(bundle_id, mode, api)
    try:
        # Retain EVERY ancestry handle. Windows opens deny delete sharing, so
        # ancestors cannot be renamed across native/path identity observations.
        for component in (*reversed(root.parents), root):
            checkpoint()
            pin._own(component, directory=True)
        lock_root = root / ".bundle-pins"
        checkpoint()
        pin._check_anchors()
        try:
            api.mkdir(lock_root, parent=pin._anchors[-1].handle)
        except FileExistsError:
            pass
        checkpoint()
        pin._own(lock_root, directory=True)
        checkpoint()
        pin._own(lock_root / (bundle_id + ".lock"), directory=False)
        while True:
            checkpoint()
            pin._check_anchors()
            checkpoint()
            if api.try_lock(pin._anchors[-1].handle, mode):
                pin._locked = True
                checkpoint()
                pin._check_anchors()
                checkpoint()
                pin._state = "held"
                return pin
            checkpoint()
            sleep(min(POLL_SECONDS, max(0.0, deadline - clock())))
    except BaseException as exc:
        try:
            pin.release()
        except BundlePinError as cleanup:
            raise cleanup from exc
        if isinstance(exc, (BundlePinError, KeyboardInterrupt, SystemExit)):
            raise
        raise BundlePinError("pin_acquisition_failed") from exc


class _PosixAPI:
    def __init__(self):
        if os.name != "posix" or not all(
            hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY")
        ):
            raise BundlePinError("posix_pin_unavailable")
        import fcntl

        self._fcntl = fcntl

    def open(self, path, *, directory, parent=None):
        flags = os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
        flags |= os.O_RDONLY | os.O_DIRECTORY if directory else os.O_RDWR | os.O_CREAT
        # os.open descriptors are non-inheritable (PEP 446); no fallible setup
        # follows acquisition before the handle transfers to RuntimeBundlePin.
        return os.open(path if parent is None else path.name, flags, 0o600, dir_fd=parent)

    def mkdir(self, path, *, parent):
        os.mkdir(path.name, mode=0o700, dir_fd=parent)

    def info(self, handle):
        info = os.fstat(handle)
        if os.get_inheritable(handle):
            raise BundlePinError("inheritable_pin_handle")
        return _Info(
            (info.st_dev, info.st_ino),
            stat.S_ISDIR(info.st_mode),
            stat.S_ISREG(info.st_mode),
            0 if stat.S_ISDIR(info.st_mode) else info.st_nlink,
        )

    def check_path_identity(self, actual, observed):
        if actual != observed:
            raise BundlePinError("pin_path_changed")

    def try_lock(self, handle, mode):
        flags = self._fcntl.LOCK_SH if mode == "shared" else self._fcntl.LOCK_EX
        try:
            self._fcntl.flock(handle, flags | self._fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                return False
            raise

    def unlock(self, handle):
        self._fcntl.flock(handle, self._fcntl.LOCK_UN)

    def close(self, handle):
        os.close(handle)


class _Win32API:
    """Lazy narrow ctypes adapter; injected kernel tests run without Windows.

    Synchronous handles plus FAIL_IMMEDIATELY preclude pending asynchronous lock
    requests. Only ERROR_LOCK_VIOLATION means contention; all other errors abort.
    Directory/file handles omit FILE_SHARE_DELETE and open reparse points rather
    than following them. Metadata rejects reparse, non-disk and nonregular files.
    """

    def __init__(self, *, kernel=None, last_error=None):
        import ctypes
        from ctypes import wintypes as w

        if kernel is None:
            if os.name != "nt":
                raise BundlePinError("windows_pin_unavailable")
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            last_error = ctypes.get_last_error
        self._c, self._k, self._last_error = ctypes, kernel, last_error

        # Fixed-width integers also make injected non-Windows ABI-layout tests
        # meaningful (ctypes.wintypes.DWORD can be host-sized on POSIX).
        dword, boolean = ctypes.c_uint32, ctypes.c_int32

        class FileTime(ctypes.Structure):
            _fields_ = [("low", dword), ("high", dword)]

        class Info(ctypes.Structure):
            _fields_ = [
                ("attributes", dword),
                ("creation", FileTime),
                ("access", FileTime),
                ("write", FileTime),
                ("volume", dword),
                ("size_high", dword),
                ("size_low", dword),
                ("links", dword),
                ("index_high", dword),
                ("index_low", dword),
            ]

        class Overlapped(ctypes.Structure):
            _fields_ = [
                ("internal", ctypes.c_size_t),
                ("internal_high", ctypes.c_size_t),
                ("offset", dword),
                ("offset_high", dword),
                ("event", w.HANDLE),
            ]

        self._Info, self._Overlapped = Info, Overlapped
        for name, args, result in (
            (
                "CreateFileW",
                [w.LPCWSTR, dword, dword, ctypes.c_void_p, dword, dword, w.HANDLE],
                w.HANDLE,
            ),
            ("GetFileInformationByHandle", [w.HANDLE, ctypes.POINTER(Info)], boolean),
            ("GetFileType", [w.HANDLE], dword),
            ("GetHandleInformation", [w.HANDLE, ctypes.POINTER(dword)], boolean),
            (
                "LockFileEx",
                [w.HANDLE, dword, dword, dword, dword, ctypes.POINTER(Overlapped)],
                boolean,
            ),
            ("UnlockFileEx", [w.HANDLE, dword, dword, dword, ctypes.POINTER(Overlapped)], boolean),
            ("CloseHandle", [w.HANDLE], boolean),
        ):
            function = getattr(kernel, name)
            function.argtypes, function.restype = args, result

    def _failed(self, operation):
        raise BundlePinError(f"win32_pin_{operation}_failed:{self._last_error()}")

    def open(self, path, *, directory, parent=None):
        # GENERIC_READ/WRITE for locking; metadata-only directory anchors.
        access = 0x80 if directory else 0xC0000000
        flags = 0x00200000 | (0x02000000 if directory else 0x80)
        handle = self._k.CreateFileW(str(path), access, 3, None, 3 if directory else 4, flags, None)
        if handle in (None, 0, self._c.c_void_p(-1).value):
            self._failed("open")
        return handle

    def mkdir(self, path, *, parent):
        # Retained ancestors deny delete sharing before this pathname operation.
        path.mkdir(mode=0o700)

    def info(self, handle):
        info, flags = self._Info(), self._c.c_uint32()
        if not self._k.GetFileInformationByHandle(handle, self._c.byref(info)):
            self._failed("info")
        if not self._k.GetHandleInformation(handle, self._c.byref(flags)):
            self._failed("handle_info")
        if flags.value & 1:
            raise BundlePinError("inheritable_pin_handle")
        disk = self._k.GetFileType(handle) == 1
        directory = bool(info.attributes & 0x10)
        return _Info(
            (info.volume, info.index_high, info.index_low),
            disk and directory,
            disk and not directory,
            0 if directory else info.links,
            bool(info.attributes & _REPARSE),
        )

    def check_path_identity(self, actual, observed):
        # Native file IDs and Python st_ino may differ in width across Windows
        # versions. Do not compare those representations. Every ancestor and the
        # file remain open without delete sharing; pre/post lstat and retained
        # native identity checks detect ordinary changes under that contract.
        pass

    def try_lock(self, handle, mode):
        flags = 1 | (2 if mode == "exclusive" else 0)
        overlap = self._Overlapped()
        if self._k.LockFileEx(handle, flags, 0, 1, 0, self._c.byref(overlap)):
            return True
        if self._last_error() == 33:  # ERROR_LOCK_VIOLATION, never IO_PENDING.
            return False
        self._failed("lock")

    def unlock(self, handle):
        overlap = self._Overlapped()
        if not self._k.UnlockFileEx(handle, 0, 1, 0, self._c.byref(overlap)):
            self._failed("unlock")

    def close(self, handle):
        if not self._k.CloseHandle(handle):
            self._failed("close")
