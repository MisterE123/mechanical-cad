"""Dormant Windows transport composition, conditional on a verified short-path runtime.

Only the worker binds Win32. Public backend admission remains closed. Retained
handles prevent ordinary replacement; pathname CreateProcess is not executable-
by-handle authentication or protection from hostile same-user software. Genuine
Windows, initial DLL-origin and default-cache qualification remain separate gates.
"""

from __future__ import annotations

import hashlib
import math
import ntpath
import os
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from . import runtime_bundle_materialize as materialize
from . import runtime_bundle_pin as pins
from .backend_platform import LaunchObservation, LaunchSpec, ProcessError
from .runtime_bundle_launch import (
    MAX_RELEASE_BYTES,
    BundleCleanupUncertain,
    BundledLaunchPolicy,
    _windows_path,
)
from .runtime_bundle_manifest import (
    BundleDescriptor,
    BundleLimits,
    parse_bundle_manifest,
    parse_release_manifest,
)
from .windows_cache import WindowsCacheOwner
from .windows_process import Win32API, WindowsOwnedProcess

POLL_INTERVAL = 0.01
CLEANUP_SECONDS = 5.0
_DLL_DIRECTORIES = (
    "python",
    "python/DLLs",
    "packages/OCP",
    "packages/slvs",
    "packages/cadquery_ocp_novtk.libs",
)


def _verify_cached_tree(policy, pin, cancelled, *, windows_storage):
    """The one unchanged full materializer verification, under the original pin."""
    return materialize.verify_cached_bundle(
        policy.package_root,
        policy.cache_root,
        policy.release_data,
        expected_platform="windows-x64",
        limits=BundleLimits(),
        pin=pin,
        cancelled=cancelled,
        windows_storage=windows_storage,
    )


def _read_launch_inputs(policy):
    """Bounded filesystem reads only; returned bytes are validated by the owner."""
    release = materialize._read_bounded(
        Path(policy.package_root) / policy.constants.RELEASE_IDENTITY_PATH, MAX_RELEASE_BYTES
    )
    bootstrap = materialize._read_bounded(Path(policy.descriptor.bootstrap_path), 1024 * 1024)
    manifest = materialize._read_bounded(
        Path(policy.package_root)
        / "_backend"
        / policy.descriptor.bundle_id
        / "bundle-manifest.json",
        BundleLimits().max_json_bytes,
    )
    return release, bootstrap, manifest


@dataclass(frozen=True)
class AnchorInfo:
    identity: tuple
    final_path: str
    directory: bool
    disk: bool
    reparse: bool
    offline: bool
    links: int
    size: int
    filesystem: str
    local: bool
    inheritable: bool


@dataclass
class _Anchor:
    handle: object
    path: str
    directory: bool
    info: AnchorInfo | None = None
    attempted: bool = False
    closed: bool = False


class WindowsRuntimeAPI:
    """Narrow lazy file/volume/OS-directory leaf; no CAD or process authority."""

    def __init__(self):
        if os.name != "nt":
            raise ProcessError("native_windows_required")
        import ctypes as c
        import msvcrt
        import platform

        if c.sizeof(c.c_void_p) != 8 or platform.machine().lower() not in {"amd64", "x86_64"}:
            raise ProcessError("windows_x64_required")
        self.c, self.msvcrt = c, msvcrt
        self.k = c.WinDLL("kernel32", use_last_error=True)
        D, B, H, P, W = c.c_uint32, c.c_int32, c.c_void_p, c.c_void_p, c.c_wchar_p

        class FileTime(c.Structure):
            _fields_ = [("low", D), ("high", D)]

        class Info(c.Structure):
            _fields_ = [
                ("attributes", D),
                ("creation", FileTime),
                ("access", FileTime),
                ("write", FileTime),
                ("volume", D),
                ("size_high", D),
                ("size_low", D),
                ("links", D),
                ("index_high", D),
                ("index_low", D),
            ]

        self.Info = Info
        for name, args, result in (
            ("CreateFileW", [W, D, D, P, D, D, H], H),
            ("GetFileInformationByHandle", [H, c.POINTER(Info)], B),
            ("GetFileType", [H], D),
            ("GetHandleInformation", [H, c.POINTER(D)], B),
            ("GetFinalPathNameByHandleW", [H, W, D, D], D),
            ("GetVolumeInformationByHandleW", [H, W, D, c.POINTER(D), P, P, W, D], B),
            ("GetDriveTypeW", [W], D),
            ("GetSystemWindowsDirectoryW", [W, D], D),
            ("SetFilePointerEx", [H, c.c_int64, P, D], B),
            ("ReadFile", [H, P, D, c.POINTER(D), P], B),
            ("CloseHandle", [H], B),
        ):
            try:
                function = getattr(self.k, name)
            except AttributeError as exc:
                raise ProcessError("required_runtime_api_missing") from exc
            function.argtypes, function.restype = args, result

    def _check(self, value, operation):
        if not value:
            raise ProcessError(
                "runtime_win32_error", operation=operation, winerror=self.c.get_last_error()
            )
        return value

    def open_anchor(self, path, *, directory):
        # NULL security attributes => noninheritable. No delete sharing; code
        # files additionally deny write sharing. OPEN_REPARSE_POINT never follows.
        handle = self.k.CreateFileW(
            path,
            0x00020080 if directory else 0x80000000,
            3 if directory else 1,
            None,
            3,
            0x00200000 | (0x02000000 if directory else 0x80),
            None,
        )
        if handle in (None, 0, self.c.c_void_p(-1).value):
            self._check(False, "open_anchor")
        return handle

    def info(self, handle):
        c = self.c
        value, flags, serial = self.Info(), c.c_uint32(), c.c_uint32()
        self._check(self.k.GetFileInformationByHandle(handle, c.byref(value)), "file_info")
        self._check(self.k.GetHandleInformation(handle, c.byref(flags)), "handle_info")
        final, filesystem = c.create_unicode_buffer(264), c.create_unicode_buffer(32)
        count = self._check(self.k.GetFinalPathNameByHandleW(handle, final, 264, 0), "final_path")
        if count >= 264 or not final.value.startswith("\\\\?\\"):
            raise ProcessError("runtime_final_path_unsupported")
        path = final.value[4:]
        _windows_path(path, directory=bool(value.attributes & 0x10))
        self._check(
            self.k.GetVolumeInformationByHandleW(
                handle, None, 0, c.byref(serial), None, None, filesystem, 32
            ),
            "volume_info",
        )
        if serial.value != value.volume:
            raise ProcessError("runtime_volume_changed")
        return AnchorInfo(
            (value.volume, value.index_high, value.index_low),
            path,
            bool(value.attributes & 0x10),
            self.k.GetFileType(handle) == 1,
            bool(value.attributes & 0x400),
            bool(value.attributes & 0x1000),
            value.links,
            (value.size_high << 32) | value.size_low,
            filesystem.value,
            self.k.GetDriveTypeW(ntpath.splitdrive(path)[0] + "\\") == 3,
            bool(flags.value & 1),
        )

    def stream_handle(self, file):
        return self.msvcrt.get_osfhandle(file.fileno())

    def stream_info(self, file):
        return self.info(self.stream_handle(file))

    def read_anchor(self, handle, offset, limit):
        c = self.c
        self._check(self.k.SetFilePointerEx(handle, offset, None, 0), "file_seek")
        buffer, count = c.create_string_buffer(limit), c.c_uint32()
        self._check(self.k.ReadFile(handle, buffer, limit, c.byref(count), None), "file_read")
        return buffer.raw[: count.value]

    def close_anchor(self, handle):
        self._check(self.k.CloseHandle(handle), "close_anchor")

    def system_directory(self):
        value = self.c.create_unicode_buffer(260)
        count = self._check(self.k.GetSystemWindowsDirectoryW(value, 260), "system_directory")
        if count >= 260:
            raise ProcessError("system_directory_too_long")
        return value.value

    @staticmethod
    def make_directory(path, *, existing=False):
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            if not existing:
                raise

    @staticmethod
    def directory_entries(path):
        # Five entries are enough to reject any unexpected extra file.
        with os.scandir(path) as entries:
            result = []
            for item in entries:
                result.append(item.name)
                if len(result) > 4:
                    break
            return tuple(result)

    @staticmethod
    def remove_directory(path):
        os.rmdir(path)


class _TrackedProcessAPI(Win32API):
    """Record references only after the real owner has acquired each file."""

    def __init__(self, *, temporary_directory, validation):
        super().__init__(temporary_directory=temporary_directory)
        self._validation = validation

    def initialize_file(self, file, data):
        self._validation.streams.append(file)
        self._validation.before_write(file)
        return super().initialize_file(file, data)


class WindowsRuntimeValidation:
    """One retained anchor set and one owned empty-directory retirement attempt."""

    def __init__(self, policy, pin, api, checkpoint, cleanup_checkpoint, *, windows_storage):
        self.policy, self.pin, self.api, self.checkpoint = policy, pin, api, checkpoint
        self.windows_storage = windows_storage
        self.cleanup_checkpoint = cleanup_checkpoint
        self.anchors = []
        self.streams = []
        self._stream_observations = []
        self.job_directory = None
        self.environment = ()
        self._by_path = {}
        self._job_created = self._close_attempted = self.closed = False
        self._assert_cache_binding()

    def _assert_cache_binding(self):
        if type(self.policy) is not BundledLaunchPolicy:
            raise ProcessError("windows_bundled_policy_required")
        p = replace(self.policy)
        if p.constants.PLATFORM != "windows-x64":
            raise ProcessError("windows_bundled_policy_required")
        expected = parse_release_manifest(
            p.release_data, expected_platform="windows-x64", limits=BundleLimits()
        )
        owner = self.windows_storage
        if (
            type(owner) is not WindowsCacheOwner
            or type(owner.location) is not type(p.windows_cache)
            or type(owner.location.known_folder) is not str
            or type(owner.location.cache_root) is not str
            or type(owner.package_root) is not str
            or type(owner.expected_platform) is not str
            or type(owner.release) is not type(expected)
            or any(
                type(getattr(owner.release, name)) is not type(value)
                for name, value in vars(expected).items()
            )
        ):
            raise ProcessError("windows_cache_binding_mismatch")
        if (
            replace(owner.location) != p.windows_cache
            or owner.cache_root != p.cache_root
            or owner.package_root != p.package_root
            or owner.expected_platform != "windows-x64"
            or owner.release != expected
        ):
            raise ProcessError("windows_cache_binding_mismatch")

    @staticmethod
    def _valid_info(info, path, directory):
        if (
            type(info) is not AnchorInfo
            or type(info.identity) is not tuple
            or len(info.identity) != 3
            or any(type(v) is not int or not 0 <= v <= 0xFFFFFFFF for v in info.identity)
            or not any(info.identity[1:])
            or info.final_path != path
            or type(info.directory) is not bool
            or info.directory != directory
            or info.disk is not True
            or info.reparse is not False
            or info.offline is not False
            or info.local is not True
            or info.inheritable is not False
            or info.filesystem != "NTFS"
            or type(info.size) is not int
            or info.size < 0
            or type(info.links) is not int
            or info.links < 0
            or (not directory and info.links != 1)
        ):
            raise ProcessError("runtime_identity_rejected")
        _windows_path(info.final_path, directory=directory)
        return info

    def _anchor(self, path, directory):
        self.checkpoint()
        _windows_path(path, directory=directory)
        if path in self._by_path:
            return self._by_path[path]
        anchor = _Anchor(self.api.open_anchor(path, directory=directory), path, directory)
        self.anchors.append(anchor)  # Ownership precedes every query/checkpoint.
        self.checkpoint()
        anchor.info = self._valid_info(self.api.info(anchor.handle), path, directory)
        self.checkpoint()
        self._by_path[path] = anchor
        return anchor

    def _ancestors(self, path):
        drive, tail = ntpath.splitdrive(path)
        current = drive + "\\"
        self._anchor(current, True)
        for component in tail[1:].split("\\"):
            if component:
                current = ntpath.join(current, component)
                self._anchor(current, True)

    def _system_directory(self):
        """Bind OS root spelling to two retained handles, never accept a cache alias.

        GetSystemWindowsDirectoryW can return C:\\WINDOWS while the filesystem
        reports C:\\Windows. Case folding alone does not establish identity,
        including on case-sensitive NTFS directories. Retain both originals and
        prove identical complete observations before using the canonical spelling.
        """
        reported = _windows_path(self.api.system_directory(), directory=True)
        self.checkpoint()
        original = _Anchor(self.api.open_anchor(reported, directory=True), reported, True)
        self.anchors.append(original)
        self.checkpoint()
        info = self.api.info(original.handle)
        if type(info) is not AnchorInfo or type(info.final_path) is not str:
            raise ProcessError("runtime_identity_rejected")
        self._valid_info(info, info.final_path, True)
        if ntpath.normcase(reported) != ntpath.normcase(info.final_path):
            raise ProcessError("system_directory_identity_rejected")
        self._ancestors(info.final_path)
        canonical = self._by_path[info.final_path]
        if canonical.info != info or self.api.info(original.handle) != info:
            raise ProcessError("system_directory_identity_rejected")
        original.path, original.info = info.final_path, info
        self.checkpoint()
        return info.final_path

    def _hash(self, anchor, item):
        if anchor.info.size != item.size:
            raise ProcessError("critical_file_size_changed")
        digest, offset = hashlib.sha256(), 0
        while offset < item.size:
            self.checkpoint()
            limit = min(128 * 1024, item.size - offset)
            raw = self.api.read_anchor(anchor.handle, offset, limit)
            self.checkpoint()
            if type(raw) is not bytes or not 0 < len(raw) <= limit:
                raise ProcessError("critical_file_read_failed")
            digest.update(raw)
            offset += len(raw)
        if self.api.read_anchor(anchor.handle, offset, 1) != b"":
            raise ProcessError("critical_file_size_changed")
        self.checkpoint()
        if digest.hexdigest() != item.sha256:
            raise ProcessError("critical_file_digest_changed")

    def acquire(self, manifest):
        self._assert_cache_binding()
        self.windows_storage.assert_held()
        self.checkpoint()
        p = self.policy
        self._ancestors(p.package_root)
        self._ancestors(p.cache_root)
        self._ancestors(p.descriptor.root)
        by_path = {item.path: item for item in manifest.files}
        names = {}
        for item in manifest.files:
            self.checkpoint()
            full = ntpath.join(p.descriptor.root, *item.path.split("/"))
            _windows_path(full)
            # Check every parent and the conventional stage projection without
            # pretending that the current tempfile suffix is a long-path promise.
            stage = ntpath.join(
                p.cache_root,
                ".stage-" + p.descriptor.bundle_id + "-xxxxxxxx",
                *item.path.split("/"),
            )
            _windows_path(stage)
            for candidate in (full, stage):
                parent = ntpath.dirname(candidate)
                while len(parent) > 3:
                    _windows_path(parent, directory=True)
                    parent = ntpath.dirname(parent)
            suffix = ntpath.splitext(item.path)[1].lower()
            if suffix in {".dll", ".pyd"}:
                basename = ntpath.basename(full).casefold()
                if basename in names:
                    raise ProcessError("duplicate_private_dll_provider")
                names[basename] = item.path
            if item.path in {manifest.python_path, manifest.bootstrap_path} or suffix in {
                ".dll",
                ".pyd",
            }:
                self._ancestors(ntpath.dirname(full))
                self._hash(self._anchor(full, False), item)
        for relative in _DLL_DIRECTORIES:
            if not any(name.startswith(relative + "/") for name in by_path):
                raise ProcessError("private_dll_directory_not_inventoried")
            self._ancestors(ntpath.join(p.descriptor.root, *relative.split("/")))
        job_parent = ntpath.join(p.cache_root, ".jobs")
        _windows_path(job_parent, directory=True)
        self.api.make_directory(job_parent, existing=True)
        self.checkpoint()
        self._ancestors(job_parent)
        self.windows_storage.check_private_handle(
            self._by_path[job_parent].handle, job_parent, directory=True
        )
        self.checkpoint()
        self.job_directory = ntpath.join(job_parent, uuid.uuid4().hex)
        _windows_path(self.job_directory, directory=True)
        self.api.make_directory(self.job_directory)
        self._job_created = True
        self.checkpoint()
        self._ancestors(self.job_directory)
        self.windows_storage.check_private_handle(
            self._by_path[self.job_directory].handle, self.job_directory, directory=True
        )
        self.checkpoint()
        if self.api.directory_entries(self.job_directory) != ():
            raise ProcessError("private_job_directory_not_empty")
        system = self._system_directory()
        self.environment = (
            ("SystemRoot", system),
            ("WINDIR", system),
            ("TEMP", self.job_directory),
            ("TMP", self.job_directory),
        )
        self._recheck()

    def _recheck(self):
        self._assert_cache_binding()
        self.windows_storage.assert_held()
        self.pin.assert_held()
        for anchor in self.anchors:
            self.checkpoint()
            current = self._valid_info(self.api.info(anchor.handle), anchor.path, anchor.directory)
            if not self._same_anchor(current, anchor.info):
                raise ProcessError("runtime_anchor_changed")
        if self.job_directory is not None:
            for path in (ntpath.dirname(self.job_directory), self.job_directory):
                self.checkpoint()
                self.windows_storage.check_private_handle(
                    self._by_path[path].handle, path, directory=True
                )
        self.checkpoint()

    @staticmethod
    def _same_anchor(current, original):
        # NTFS directory index allocation grows while this owner creates its
        # own files, and need not shrink on removal. It is not file identity.
        # All complete native IDs, exact path, kind, volume, link/attribute and
        # inheritance observations still match; regular file sizes stay exact.
        if current.directory:
            current = replace(current, size=original.size)
        return current == original

    def before_write(self, file):
        self._recheck()
        if (
            len(self._stream_observations) >= 4
            or len(self.streams) != len(self._stream_observations) + 1
            or self.streams[-1] is not file
        ):
            raise ProcessError("private_stream_set_invalid")
        handle = self.api.stream_handle(file)
        self.checkpoint()
        if type(handle) is not int or handle <= 0:
            raise ProcessError("private_stream_identity_invalid")
        info = self.api.info(handle)
        self.checkpoint()
        if type(info) is not AnchorInfo or type(info.final_path) is not str:
            raise ProcessError("private_stream_identity_invalid")
        _windows_path(info.final_path)
        self._valid_info(info, info.final_path, False)
        if ntpath.dirname(info.final_path) != self.job_directory or info.size != 0:
            raise ProcessError("private_stream_path_or_size_invalid")
        if any(
            file is original
            or handle == borrowed
            or info.identity == identity
            or info.final_path == path
            for original, borrowed, identity, path in self._stream_observations
        ):
            raise ProcessError("private_stream_identity_invalid")
        self.windows_storage.check_private_handle(handle, info.final_path, directory=False)
        self.checkpoint()
        self._stream_observations.append((file, handle, info.identity, info.final_path))

    def before_create(self, spec):
        self._assert_cache_binding()
        if (
            type(spec) is not LaunchSpec
            or type(spec.bundle) is not BundleDescriptor
            or any(
                type(getattr(spec.bundle, name)) is not str
                for name in BundleDescriptor.__dataclass_fields__
            )
        ):
            raise ProcessError("captured_runtime_changed")
        if spec.bundle != self.policy.descriptor or spec.environment != self.environment:
            raise ProcessError("captured_runtime_changed")
        self._recheck()
        if (
            len(self.streams) != 4
            or len(self._stream_observations) != 4
            or len({id(file) for file in self.streams}) != 4
        ):
            raise ProcessError("private_stream_set_invalid")
        entries = self.api.directory_entries(self.job_directory)
        self.checkpoint()
        if sorted(entries) != sorted(
            ntpath.basename(item[3]) for item in self._stream_observations
        ):
            raise ProcessError("private_stream_set_invalid")
        observed = []
        expected_sizes = (len(spec.request_payload), 0, 0, len(spec.descriptor_payload))
        for file, expected_size, original in zip(
            self.streams, expected_sizes, self._stream_observations, strict=True
        ):
            self.checkpoint()
            handle = self.api.stream_handle(file)
            if type(handle) is not int or handle <= 0:
                raise ProcessError("private_stream_identity_invalid")
            info = self.api.info(handle)
            self.checkpoint()
            if type(info) is not AnchorInfo or type(info.final_path) is not str:
                raise ProcessError("private_stream_identity_invalid")
            _windows_path(info.final_path)
            self._valid_info(info, info.final_path, False)
            if (
                file is not original[0]
                or handle != original[1]
                or info.identity != original[2]
                or info.final_path != original[3]
            ):
                raise ProcessError("private_stream_identity_changed")
            if ntpath.dirname(info.final_path) != self.job_directory:
                raise ProcessError("private_stream_path_invalid")
            if info.size != expected_size:
                raise ProcessError("private_stream_size_changed")
            self.windows_storage.check_private_handle(handle, info.final_path, directory=False)
            self.checkpoint()
            observed.append(info)
        if len({v.identity for v in observed}) != 4 or len({v.final_path for v in observed}) != 4:
            raise ProcessError("private_stream_identity_invalid")
        names = self.api.directory_entries(self.job_directory)
        if (
            type(names) is not tuple
            or len(names) != 4
            or set(names) != {ntpath.basename(v.final_path) for v in observed}
        ):
            raise ProcessError("private_stream_directory_mismatch")
        self._recheck()

    def after_create(self, spec, observed):
        if (
            type(observed) is not LaunchObservation
            or type(observed.process_id) is not int
            or not 0 < observed.process_id <= 0xFFFFFFFF
            or type(observed.creation_time) is not int
            or not 0 < observed.creation_time < 2**64
            or observed.image_path != spec.bundle.python_path
        ):
            raise ProcessError("process_image_identity_rejected")
        self._recheck()

    def _cleanup_call(self, method, *args):
        self.cleanup_checkpoint()
        try:
            return method(*args)
        finally:
            self.cleanup_checkpoint()

    def _close_anchor(self, anchor):
        self.cleanup_checkpoint()
        if anchor.attempted:
            if not anchor.closed:
                raise ProcessError("anchor_close_uncertain")
            return
        anchor.attempted = True
        try:
            self.api.close_anchor(anchor.handle)
            anchor.closed = True
        finally:
            self.cleanup_checkpoint()

    def close(self):
        if self.closed:
            return
        if self._close_attempted:
            raise ProcessError("validation_close_uncertain")
        self.cleanup_checkpoint()
        self._close_attempted = True
        if self._job_created:
            anchor = self._by_path.get(self.job_directory)
            if anchor is None:
                raise ProcessError("private_directory_identity_unconfirmed")
            current = self._valid_info(
                self._cleanup_call(self.api.info, anchor.handle), anchor.path, True
            )
            if (
                not self._same_anchor(current, anchor.info)
                or self._cleanup_call(self.api.directory_entries, self.job_directory) != ()
            ):
                raise ProcessError("private_directory_retirement_unconfirmed")
            # Parent anchors stay retained through removal; the directory's own
            # no-delete-share handle must close first. Never retry either action.
            self._close_anchor(anchor)
            self._cleanup_call(self.api.remove_directory, self.job_directory)
            self._job_created = False
        for anchor in reversed(self.anchors):
            self._close_anchor(anchor)
        self.windows_storage.close(cleanup_checkpoint=self.cleanup_checkpoint)
        self.cleanup_checkpoint()
        self.closed = True


class WindowsOperationOwner:
    """One original deadline, pin transfer and finite cleanup observation budget."""

    def __init__(self, policy, payload):
        if type(policy) is not BundledLaunchPolicy:
            raise ProcessError("windows_bundled_policy_required")
        policy = replace(policy)
        if policy.constants.PLATFORM != "windows-x64":
            raise ProcessError("windows_bundled_policy_required")
        self.policy, self.payload = policy, payload
        self.pin = self.validation = self.process = self.spec = None
        self.cache_owner = None
        self.deadline = self._cleanup_deadline = None
        self._clock, self._sleep = time.monotonic, time.sleep
        self._cancelled = lambda: False
        self._transferred = self._local_cleanup_attempted = False
        self.cleanup_uncertain = self.cleanup_complete = False
        self.failure_code = None

    @property
    def attempted_start(self):
        return self.process is not None and self.process.attempted_start

    def checkpoint(self):
        if self._cancelled():
            self.failure_code = "cancelled"
            raise ProcessError("cancelled")
        if self.deadline is not None and self._clock() >= self.deadline:
            self.failure_code = "timeout"
            raise ProcessError("timeout")
        if self.pin is not None:
            self.pin.assert_held()
            if self._cancelled():
                self.failure_code = "cancelled"
                raise ProcessError("cancelled")
            if self.deadline is not None and self._clock() >= self.deadline:
                self.failure_code = "timeout"
                raise ProcessError("timeout")

    def _verification_cancelled(self):
        self.checkpoint()
        return False

    def acquire(self, *, timeout, cancelled):
        try:
            self._acquire(timeout=timeout, cancelled=cancelled)
        except ProcessError as exc:
            self.failure_code = exc.code
            raise

    def _acquire(self, *, timeout, cancelled):
        self._cancelled = cancelled
        self.deadline = self._clock() + timeout
        self.checkpoint()
        if type(self.policy) is not BundledLaunchPolicy:
            raise ProcessError("windows_bundled_policy_required")
        p = replace(self.policy)
        if p.constants.PLATFORM != "windows-x64":
            raise ProcessError("windows_bundled_policy_required")
        self.policy = p
        release = parse_release_manifest(
            p.release_data, expected_platform="windows-x64", limits=BundleLimits()
        )
        for name in ("bundle-manifest.json", "payload.zip"):
            _windows_path(ntpath.join(p.package_root, "_backend", p.descriptor.bundle_id, name))
        _windows_path(ntpath.join(p.cache_root, ".bundle-pins", p.descriptor.bundle_id + ".lock"))
        self.cache_owner = WindowsCacheOwner(
            p.windows_cache,
            package_root=p.package_root,
            expected_platform="windows-x64",
            release=release,
        )
        acquired = self.cache_owner.acquire_existing(cancelled=self._verification_cancelled)
        owner = self.cache_owner
        if (
            acquired is not owner
            or type(owner) is not WindowsCacheOwner
            or type(owner.location) is not type(p.windows_cache)
            or type(owner.location.known_folder) is not str
            or type(owner.location.cache_root) is not str
            or type(owner.package_root) is not str
            or type(owner.expected_platform) is not str
            or type(owner.release) is not type(release)
            or any(
                type(getattr(owner.release, name)) is not type(value)
                for name, value in vars(release).items()
            )
        ):
            raise ProcessError("windows_cache_binding_mismatch")
        if (
            replace(owner.location) != p.windows_cache
            or owner.cache_root != p.cache_root
            or owner.package_root != p.package_root
            or owner.expected_platform != "windows-x64"
            or owner.release != release
        ):
            raise ProcessError("windows_cache_binding_mismatch")
        self.checkpoint()
        try:
            self.pin = pins.acquire_bundle_pin(
                p.cache_root,
                p.descriptor.bundle_id,
                "shared",
                timeout=self.deadline - self._clock(),
                cancelled=self._verification_cancelled,
            )
        except pins.BundlePinError as exc:
            if exc.pin is not None:
                self.pin, self.cleanup_uncertain = exc.pin, True
            raise
        self.checkpoint()
        self.cache_owner.check_private_entry(
            ntpath.join(p.cache_root, ".bundle-pins"), directory=True
        )
        self.checkpoint()
        self.cache_owner.check_private_entry(
            ntpath.join(p.cache_root, ".bundle-pins", p.descriptor.bundle_id + ".lock"),
            directory=False,
        )
        self.checkpoint()
        descriptor = _verify_cached_tree(
            p, self.pin, self._verification_cancelled, windows_storage=self.cache_owner
        )
        self.checkpoint()
        if type(descriptor) is not BundleDescriptor or descriptor != p.descriptor:
            raise ProcessError("verified_runtime_changed")
        values = _read_launch_inputs(p)
        self.checkpoint()
        if (
            type(values) is not tuple
            or len(values) != 3
            or any(type(v) is not bytes for v in values)
        ):
            raise ProcessError("invalid_runtime_input_bytes")
        release, bootstrap, manifest_data = values
        if release != p.release_data or not 0 < len(bootstrap) <= 1024 * 1024:
            raise ProcessError("installed_launch_input_changed")
        if hashlib.sha256(bootstrap).hexdigest() != p.constants.BOOTSTRAP_SHA256:
            raise ProcessError("installed_bootstrap_changed")
        release = parse_release_manifest(
            release, expected_platform="windows-x64", limits=BundleLimits()
        )
        manifest = parse_bundle_manifest(manifest_data, release, limits=BundleLimits())
        if (
            manifest.python_path != p.constants.PYTHON_PATH
            or manifest.bootstrap_path != p.constants.BOOTSTRAP_PATH
        ):
            raise ProcessError("manifest_launch_profile_changed")
        self.checkpoint()
        api = WindowsRuntimeAPI()
        self.validation = WindowsRuntimeValidation(
            p,
            self.pin,
            api,
            self.checkpoint,
            self.cleanup_checkpoint,
            windows_storage=self.cache_owner,
        )
        self.validation.acquire(manifest)
        self.checkpoint()
        self.spec = LaunchSpec(
            replace(p.descriptor),
            p.constants.ENTRY_LOADER,
            self.validation.environment,
            self.payload,
            p.descriptor_bytes(),
            timeout,
        )
        process_api = _TrackedProcessAPI(
            temporary_directory=self.validation.job_directory, validation=self.validation
        )
        self.checkpoint()
        self.process = WindowsOwnedProcess(
            self.spec,
            self.pin,
            self.validation,
            api=process_api,
            deadline=self.deadline,
            clock=self._clock,
            cancelled=self._cancelled,
            cleanup_checkpoint=self.cleanup_checkpoint,
        )
        self._transferred = True  # Constructor success transfers exactly once, before start.
        self.checkpoint()

    def exchange(self, decode):
        try:
            self.process.start()
            if self.process.cleanup_started_at is not None:
                self.cleanup_checkpoint(self.process.cleanup_started_at)
            self.checkpoint()
            while True:
                self.checkpoint()
                code = self.process.poll_exit()
                self.checkpoint()  # An in-budget call returning late cannot authorize output.
                if self.process.error is not None:
                    raise self.process.error
                if self.process.tree_quiescent:
                    break
                self._sleep(POLL_INTERVAL)
            stdout = self.process.read_output()
            self.checkpoint()
            stderr = self.process.read_output(stderr=True)
            self.checkpoint()
            result = decode(code, stdout, stderr)
            self.checkpoint()
            return result
        except Exception as exc:
            self.failure_code = exc.code if isinstance(exc, ProcessError) else "response_failed"
            raise
        finally:
            self.cleanup()

    def cleanup_checkpoint(self, started_at=None):
        """Same first cleanup budget, with an absorbing failed-checkpoint latch."""
        if self.cleanup_uncertain:
            raise BundleCleanupUncertain("Windows cleanup remains uncertain.")
        try:
            if started_at is None:
                started_at = (
                    self._clock()
                    if self._cleanup_deadline is None
                    else self._cleanup_deadline - CLEANUP_SECONDS
                )
            if type(started_at) not in (int, float) or not math.isfinite(started_at):
                raise BundleCleanupUncertain("Invalid Windows cleanup observation.")
            deadline = started_at + CLEANUP_SECONDS
            self._cleanup_deadline = (
                deadline
                if self._cleanup_deadline is None
                else min(self._cleanup_deadline, deadline)
            )
            if self._clock() >= self._cleanup_deadline:
                raise BundleCleanupUncertain("Windows cleanup observation expired.")
        except BaseException:
            self.cleanup_uncertain = True
            raise

    def cleanup(self):
        if self.cleanup_complete:
            return
        if self.cleanup_uncertain:
            raise BundleCleanupUncertain("Windows cleanup remains uncertain.")
        started_at = self.process.cleanup_started_at if self._transferred else None
        self.cleanup_checkpoint(started_at)
        try:
            if self._transferred:
                while True:
                    if self.process.cleanup_uncertain:
                        raise BundleCleanupUncertain("Windows cleanup remains uncertain.")
                    self.cleanup_checkpoint(self.process.cleanup_started_at)
                    if not self.process.tree_quiescent:
                        reason = self.failure_code or "cancelled"
                        self.process.cancel_tree(reason)
                        self.cleanup_checkpoint(self.process.cleanup_started_at)
                    closed = self.process.close_after_cleanup()
                    self.cleanup_checkpoint(self.process.cleanup_started_at)
                    if closed:
                        self.cleanup_complete = True
                        return
                    self._sleep(POLL_INTERVAL)
            else:
                if self._local_cleanup_attempted:
                    raise BundleCleanupUncertain("Windows local cleanup cannot be retried.")
                self._local_cleanup_attempted = True
                if self.validation is not None:
                    self.cleanup_checkpoint()
                    self.validation.close()
                    self.cleanup_checkpoint()
                elif self.cache_owner is not None:
                    self.cache_owner.close(cleanup_checkpoint=self.cleanup_checkpoint)
                    self.cleanup_checkpoint()
                if self.pin is not None:
                    self.cleanup_checkpoint()
                    self.pin.release()
                    self.cleanup_checkpoint()
                self.cleanup_complete = True
        except BaseException:
            self.cleanup_uncertain = True
            raise
