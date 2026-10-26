"""Offline bounded bundle preparation, disconnected from backend activation.

The caller supplies an already-held OS-backed cross-process BundlePin. A stable
lock file lives outside the final runtime tree; do not unlink/recreate it. Shared
pins precede final verification and remain held through confirmed process-tree
and file-handle cleanup. Publication requires an exclusive pin. This module does
not acquire, convert, release or simulate such OS locks and never removes caches.
A descriptor is setup data only: after any pin gap, reacquire and reverify before
launch. Real multi-process/platform locking and crash-orphan lifetime tests remain
integration gates, not claims established by injected test pins.

No descriptor is returned for staging or before complete final verification.
Failed/cancelled stages are retained for diagnosis. Existing corrupt final trees
are left intact and rejected; repair/retirement needs separate lifetime design.
This protects cooperating instances and ordinary corruption, not hostile same-user
filesystem mutation. No native imports, subprocess, network or package writes.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import struct
import tempfile
import zipfile
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, Protocol

from .runtime_bundle_manifest import (
    BundleDescriptor,
    BundleError,
    parse_bundle_manifest,
    parse_release_manifest,
)
from .windows_cache import WindowsCacheCancelled, WindowsCacheOwner

_READY = ".bundle-ready.json"


class BundlePin(Protocol):
    bundle_id: str
    mode: Literal["shared", "exclusive"]

    def assert_held(self) -> None:
        """Raise unless this caller still holds its matching OS lifetime lock."""


class BundlePreparationError(BundleError):
    def __init__(self, message, staging_path=None):
        super().__init__(message)
        self.staging_path = staging_path


class BundleCancelled(BundlePreparationError):
    """Cancellation leaves any owned staging tree intact and unselectable."""


def _checkpoint(pin, bundle_id, cancelled, *, exclusive=False):
    if pin.bundle_id != bundle_id or pin.mode not in {"shared", "exclusive"}:
        raise BundleError("Wrong bundle lifetime pin.")
    if exclusive and pin.mode != "exclusive":
        raise BundleError("Materialization requires an exclusive lifetime pin.")
    try:
        pin.assert_held()
    except Exception as exc:
        raise BundleError("Bundle lifetime pin is unavailable.") from exc
    if cancelled():
        raise BundleCancelled("Bundle preparation cancelled.")


def _safe_path(path):
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BundleError("Symlink/reparse runtime paths are unsupported.")
    return path


@contextmanager
def _open_regular(path):
    path = _safe_path(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise BundleError("Bundle input must be a regular file.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    if os.name == "posix":
        # A regular file can be replaced after lstat. Never block opening a FIFO
        # in that gap; fstat below checks the actual opened object before reads.
        flags |= os.O_NONBLOCK
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BundleError("Bundle input must be a regular file.")
        # The wrapper never owns the raw fd: CPython may close a partially
        # constructed stream before fdopen raises. Keep one explicit owner.
        stream = os.fdopen(fd, "rb", closefd=False)
        try:
            yield stream
        finally:
            stream.close()
    finally:
        # Exactly one close attempt. Do not retry an uncertain/reused number.
        os.close(fd)


def _read_bounded(path, maximum):
    with _open_regular(path) as stream:
        if os.fstat(stream.fileno()).st_size > maximum:
            raise BundleError("Manifest exceeds trusted byte limit.")
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise BundleError("Manifest exceeds trusted byte limit.")
    return data


def _documents(package_root, release_data, expected_platform, limits, *, windows_storage=None):
    release = parse_release_manifest(
        release_data, expected_platform=expected_platform, limits=limits
    )
    if windows_storage is not None:
        if type(windows_storage) is not WindowsCacheOwner or expected_platform != "windows-x64":
            raise BundleError("Invalid concrete Windows cache owner.")
        windows_storage.check_installed_paths(package_root, release)
    data = _read_bounded(package_root / release.manifest_path, limits.max_json_bytes)
    manifest = parse_bundle_manifest(data, release, limits=limits)
    if windows_storage is not None:
        windows_storage.check_manifest_paths(release, manifest)
    return release, manifest


def _marker(release):
    return json.dumps(
        {
            "bundle_id": release.bundle_id,
            "manifest_sha256": release.manifest_sha256,
            "payload_sha256": release.payload_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _copy_hash(source, target, size, limits, checkpoint):
    digest, count = hashlib.sha256(), 0
    while True:
        checkpoint()
        chunk = source.read(min(limits.chunk_bytes, size - count + 1))
        if not chunk:
            break
        count += len(chunk)
        if count > size:
            raise BundleError("Bundle file exceeds its declared size.")
        digest.update(chunk)
        if target is not None:
            target.write(chunk)
    if count != size:
        raise BundleError("Bundle file has incorrect size.")
    return digest.hexdigest()


def _zip_directory(stream, size, limits):
    """Bound ZIP central-directory allocation before ZipFile constructs entries.

    Version 1 intentionally excludes ZIP64, multi-disk archives and ZIP comments.
    Final release inputs must stay within this declared, tested format.
    """
    if size < 22:
        raise BundleError("Truncated ZIP payload.")
    stream.seek(size - 22)
    tail = stream.read(22)
    signature, disk, cd_disk, disk_count, count, cd_size, offset, comment = struct.unpack(
        "<4s4H2LH", tail
    )
    if signature != b"PK\x05\x06" or disk or cd_disk or comment or disk_count != count:
        raise BundleError("Unsupported ZIP end record.")
    if count == 65535 or offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        raise BundleError("ZIP64 is outside the bounded bundle format.")
    if not 1 <= count <= limits.max_files or cd_size > limits.max_zip_metadata_bytes:
        raise BundleError("ZIP metadata exceeds trusted limits.")
    if offset + cd_size != size - 22:
        raise BundleError("Unexpected ZIP central-directory extent.")
    stream.seek(0)
    if stream.read(4) != b"PK\x03\x04":
        raise BundleError("ZIP payload must begin with a local file record.")
    stream.seek(0)
    return count


def _inventory(root, manifest, release, limits, checkpoint, *, ready, windows_storage=None):
    """Rehash the entire exact tree; a ready marker alone never establishes trust."""
    if windows_storage is not None:
        if (
            type(windows_storage) is not WindowsCacheOwner
            or release.platform != "windows-x64"
            or windows_storage.release != release
        ):
            raise BundleError("Invalid concrete Windows cache owner.")
        windows_storage.assert_held()
        windows_storage.check_private_entry(root, directory=True)
    _safe_path(root)
    expected = {item.path: item for item in manifest.files}
    directories = set()
    for path in expected:
        parts = path.split("/")
        directories.update("/".join(parts[:i]) for i in range(1, len(parts)))
    pending, seen_files, seen_dirs = [root], set(), set()
    while pending:
        parent = pending.pop()
        with os.scandir(parent) as scan:
            for entry in scan:
                checkpoint()
                relative = (parent / entry.name).relative_to(root).as_posix()
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise BundleError("Link/reparse entry in runtime inventory.")
                if stat.S_ISDIR(info.st_mode):
                    if relative not in directories:
                        raise BundleError("Unexpected runtime directory.")
                    if windows_storage is not None:
                        windows_storage.check_private_entry(parent / entry.name, directory=True)
                    seen_dirs.add(relative)
                    pending.append(parent / entry.name)
                    continue
                if windows_storage is None:
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise BundleError("Runtime inventory requires independent regular files.")
                else:
                    if not stat.S_ISREG(info.st_mode):
                        raise BundleError("Runtime inventory requires independent regular files.")
                    # Windows DirEntry.stat reports zero links. The original
                    # retained handle must prove exactly one, including marker.
                    windows_storage.check_private_entry(parent / entry.name, directory=False)
                if relative == _READY and ready:
                    if _read_bounded(parent / entry.name, len(_marker(release))) != _marker(
                        release
                    ):
                        raise BundleError("Ready marker mismatch.")
                    seen_files.add(relative)
                    continue
                item = expected.get(relative)
                if item is None or info.st_size != item.size:
                    raise BundleError("Unexpected or incorrectly sized runtime file.")
                if os.name == "posix" and stat.S_IMODE(info.st_mode) != item.mode:
                    raise BundleError("Runtime file mode mismatch.")
                with _open_regular(parent / entry.name) as stream:
                    if _copy_hash(stream, None, item.size, limits, checkpoint) != item.sha256:
                        raise BundleError("Runtime file digest mismatch.")
                seen_files.add(relative)
    if seen_files != set(expected) | ({_READY} if ready else set()) or seen_dirs != directories:
        raise BundleError("Runtime inventory is incomplete.")


def _descriptor(root, release, manifest):
    return BundleDescriptor(
        release.bundle_id,
        release.source_commit,
        release.runtime_lock_sha256,
        release.platform,
        release.manifest_sha256,
        release.payload_sha256,
        str(root),
        str(root / manifest.python_path),
        str(root / manifest.bootstrap_path),
    )


def verify_cached_bundle(
    package_root,
    cache_root,
    release_data,
    *,
    expected_platform,
    limits,
    pin,
    cancelled=lambda: False,
    windows_storage=None,
):
    """Recheck an existing final tree under a caller-owned shared/exclusive pin.

    The caller retains the pin after return. No marker-only or staging lookup is
    available. Verification is worker work, never a UI draw/currentness predicate.
    """
    if windows_storage is not None:
        if (
            type(windows_storage) is not WindowsCacheOwner
            or expected_platform != "windows-x64"
            or windows_storage.expected_platform != expected_platform
            or type(cache_root) is not str
            or cache_root != windows_storage.cache_root
        ):
            raise BundleError("Invalid concrete Windows cache owner.")
        # Validate the original immutable binding and DOS budgets before either
        # existing _safe_path call may inspect a root.
        captured_release = parse_release_manifest(
            release_data, expected_platform=expected_platform, limits=limits
        )
        windows_storage.check_installed_paths(package_root, captured_release)
        windows_storage.assert_held()
    package_root, cache_root = _safe_path(package_root), _safe_path(cache_root)
    release, manifest = _documents(
        package_root, release_data, expected_platform, limits, windows_storage=windows_storage
    )

    def checkpoint():
        _checkpoint(pin, release.bundle_id, cancelled)

    checkpoint()
    root = cache_root / release.bundle_id
    _inventory(
        root,
        manifest,
        release,
        limits,
        checkpoint,
        ready=True,
        windows_storage=windows_storage,
    )
    checkpoint()
    return _descriptor(root, release, manifest)


def materialize_bundle(
    package_root,
    cache_root,
    release_data,
    *,
    expected_platform,
    limits,
    pin,
    cancelled=lambda: False,
    windows_storage=None,
):
    """Verify one opened payload, stage, verify, then atomically publish once.

    Both supplied roots must exist. Cache and installed package roots must be
    disjoint. Exclusive pin is held throughout; no published tree is overwritten,
    renamed, repaired or deleted. Existing trees are fully rechecked. On failure,
    BundlePreparationError.staging_path identifies the retained owned attempt.
    """
    stage = None
    try:
        if windows_storage is not None:
            if (
                type(windows_storage) is not WindowsCacheOwner
                or expected_platform != "windows-x64"
                or windows_storage.expected_platform != expected_platform
                or type(cache_root) is not str
                or cache_root != windows_storage.cache_root
            ):
                raise BundleError("Invalid concrete Windows cache owner.")
            # Validate the original immutable binding and DOS budgets before either
            # existing _safe_path call may inspect a root.
            captured_release = parse_release_manifest(
                release_data, expected_platform=expected_platform, limits=limits
            )
            windows_storage.check_installed_paths(package_root, captured_release)
            windows_storage.assert_held()
        package_root, cache_root = _safe_path(package_root), _safe_path(cache_root)
        if (
            package_root == cache_root
            or package_root in cache_root.parents
            or cache_root in package_root.parents
        ):
            raise BundleError("Package and runtime cache roots must be disjoint.")
        release, manifest = _documents(
            package_root, release_data, expected_platform, limits, windows_storage=windows_storage
        )

        def checkpoint():
            _checkpoint(pin, release.bundle_id, cancelled, exclusive=True)

        checkpoint()
        final = cache_root / release.bundle_id
        with _open_regular(package_root / release.payload_path) as stream:
            initial = os.fstat(stream.fileno())
            if initial.st_size != release.payload_size:
                raise BundleError("Payload archive size mismatch.")
            if (
                _copy_hash(stream, None, release.payload_size, limits, checkpoint)
                != release.payload_sha256
            ):
                raise BundleError("Payload archive digest mismatch.")
            if os.path.lexists(final):
                _inventory(
                    final,
                    manifest,
                    release,
                    limits,
                    checkpoint,
                    ready=True,
                    windows_storage=windows_storage,
                )
                checkpoint()
                return _descriptor(final, release, manifest)
            if (
                shutil.disk_usage(cache_root).free
                < sum(f.size for f in manifest.files) + limits.reserve_free_bytes
            ):
                raise BundleError("Insufficient free space for private runtime staging.")
            count = _zip_directory(stream, release.payload_size, limits)
            with zipfile.ZipFile(stream) as archive:
                infos, expected = archive.infolist(), {f.path: f for f in manifest.files}
                if len(infos) != count or len(infos) != len(expected):
                    raise BundleError("ZIP file count differs from manifest.")
                seen = set()
                for info in infos:
                    checkpoint()
                    item = expected.get(info.filename)
                    mode = info.external_attr >> 16
                    if (
                        item is None
                        or info.filename in seen
                        or info.orig_filename != info.filename
                        or info.is_dir()
                        or info.flag_bits & ~0x80E
                        or info.compress_type not in {0, 8}
                        or info.file_size != item.size
                        or info.create_system != 3
                        or stat.S_IFMT(mode) != stat.S_IFREG
                        or stat.S_IMODE(mode) != item.mode
                    ):
                        raise BundleError("ZIP entry differs from exact regular-file inventory.")
                    seen.add(info.filename)
                if windows_storage is None:
                    stage = Path(
                        tempfile.mkdtemp(prefix=f".stage-{release.bundle_id}-", dir=cache_root)
                    )
                else:
                    stage = Path(windows_storage.create_stage(release, manifest))
                    windows_storage.check_manifest_paths(release, manifest, stage=stage)
                for info in infos:
                    checkpoint()
                    item, target = expected[info.filename], stage / info.filename
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    with archive.open(info, "r") as source, target.open("xb") as output:
                        if _copy_hash(source, output, item.size, limits, checkpoint) != item.sha256:
                            raise BundleError("Extracted file digest mismatch.")
                        output.flush()
                        os.fsync(output.fileno())
                    os.chmod(target, item.mode)
            after = os.fstat(stream.fileno())
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"):
                if getattr(initial, field) != getattr(after, field):
                    raise BundleError("Payload changed during preparation.")
        _inventory(
            stage,
            manifest,
            release,
            limits,
            checkpoint,
            ready=False,
            windows_storage=windows_storage,
        )
        with (stage / _READY).open("xb") as output:
            output.write(_marker(release))
            output.flush()
            os.fsync(output.fileno())
        _inventory(
            stage,
            manifest,
            release,
            limits,
            checkpoint,
            ready=True,
            windows_storage=windows_storage,
        )
        checkpoint()
        # A cooperating publisher cannot race the exclusive OS pin. If a final
        # tree appeared anyway, recheck it, retain our attempt, never replace it.
        if os.path.lexists(final):
            _inventory(
                final,
                manifest,
                release,
                limits,
                checkpoint,
                ready=True,
                windows_storage=windows_storage,
            )
        else:
            if windows_storage is not None:
                windows_storage.before_stage_rename(stage, final)
            os.rename(stage, final)
            if windows_storage is not None:
                windows_storage.after_stage_rename(final)
        _inventory(
            final,
            manifest,
            release,
            limits,
            checkpoint,
            ready=True,
            windows_storage=windows_storage,
        )
        checkpoint()
        return _descriptor(final, release, manifest)
    except (BundleCancelled, WindowsCacheCancelled) as exc:
        if type(windows_storage) is WindowsCacheOwner:
            exc.staging_path = windows_storage.owned_stage_path
        else:
            exc.staging_path = str(stage) if stage is not None and stage.exists() else None
        raise
    except (BundleError, OSError, zipfile.BadZipFile, zlib.error, RuntimeError, EOFError) as exc:
        if type(windows_storage) is WindowsCacheOwner:
            # Creation ownership is already known even if create_stage failed
            # before assignment. No diagnostic I/O may mask the original cause.
            retained = windows_storage.owned_stage_path
        else:
            retained = str(stage) if stage is not None and stage.exists() else None
        raise BundlePreparationError(str(exc), retained) from exc
