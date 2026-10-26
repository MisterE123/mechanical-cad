"""Native-free immutable bundled policy and worker-owned Linux launch resources.

Generated constants are trusted installed code, never values from model JSON or
runtime descriptors. A setup policy is not CAD authority. Each operation verifies
its complete immutable runtime again under a fresh shared OS pin. Only confirmed
child, temporary-file and descriptor cleanup permits releasing that pin. Failed
cleanup retains the original owner; numeric descriptors are never closed twice.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import runtime_bundle_materialize as materialize
from . import runtime_bundle_pin as pins
from .runtime_bundle_manifest import (
    BundleDescriptor,
    BundleError,
    BundleLimits,
    parse_release_manifest,
    validate_path,
)
from .windows_cache import WindowsCacheLocation

MAX_RELEASE_BYTES = 16 * 1024
MAX_DESCRIPTOR_BYTES = 16 * 1024
PYTHON_FLAGS = ("-I", "-S", "-B", "-X", "utf8", "-c")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class BundleLaunchError(BundleError):
    """Bundled setup or launch failed without a fallback to external Python."""


class BundleCleanupUncertain(RuntimeError):
    """Original resources remain owned; completion must not be reported."""


def _path(value):
    if (
        type(value) is not str
        or not 0 < len(value) <= 4096
        or "\0" in value
        or not os.path.isabs(value)
        or os.path.normpath(value) != value
        or ".." in Path(value).parts
    ):
        raise BundleLaunchError("Bundled paths must be bounded absolute canonical paths.")
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise BundleLaunchError("Invalid bundled path text.") from exc
    return value


def _windows_path(value, *, directory=False):
    """Ordinary exact DOS spelling only; no aliases or long-path opt-in."""
    if type(value) is not str or not value or "\0" in value:
        raise BundleLaunchError("Unsupported Windows runtime path.")
    drive, tail = ntpath.splitdrive(value)
    if (
        len(drive) != 2
        or drive[1] != ":"
        or drive[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        or not tail.startswith("\\")
        or "/" in value
        or "%" in value
        or ntpath.normpath(value) != value
    ):
        raise BundleLaunchError("Unsupported Windows runtime path.")
    try:
        if len(value.encode("utf-16-le", "strict")) // 2 >= (248 if directory else 260):
            raise BundleLaunchError("Windows runtime path exceeds the short-path limit.")
        if tail != "\\":
            validate_path(
                tail[1:].replace("\\", "/"), BundleLimits(max_path_bytes=4096, max_path_depth=128)
            )
    except (UnicodeError, BundleError) as exc:
        raise BundleLaunchError("Unsupported Windows runtime path.") from exc
    return value


@dataclass(frozen=True, slots=True)
class BundledLaunchConstants:
    SCHEMA_VERSION: int
    BUILD_STATUS: str
    SOURCE_COMMIT: str
    RUNTIME_LOCK_SHA256: str
    BUNDLE_ID: str
    PLATFORM: str
    PYTHON_IMPLEMENTATION: str
    PYTHON_VERSION: tuple
    PYTHON_CACHE_TAG: str
    PYTHON_BITS: int
    PYTHON_PATH: str
    PYTHON_FLAGS: tuple
    BOOTSTRAP_PATH: str
    BOOTSTRAP_SHA256: str
    RELEASE_IDENTITY_PATH: str
    RELEASE_IDENTITY_BYTES: bytes = field(repr=False)
    RELEASE_IDENTITY_SHA256: str
    BUNDLE_MANIFEST_SHA256: str
    PAYLOAD_SHA256: str
    ENTRY_LOADER: str = field(repr=False)

    def __post_init__(self):
        if type(self.PLATFORM) is not str or self.PLATFORM not in {"linux-x64", "windows-x64"}:
            raise BundleLaunchError("Unsupported trusted bundled launch profile.")
        python_path = (
            "python/python.exe" if self.PLATFORM == "windows-x64" else "python/bin/python3.12"
        )
        for name, expected in (
            ("SCHEMA_VERSION", 1),
            ("BUILD_STATUS", "UNQUALIFIED_CONTRACT_ARTIFACT"),
            ("PYTHON_IMPLEMENTATION", "cpython"),
            ("PYTHON_CACHE_TAG", "cpython-312"),
            ("PYTHON_BITS", 64),
            ("PYTHON_PATH", python_path),
            ("BOOTSTRAP_PATH", "bootstrap.py"),
            ("RELEASE_IDENTITY_PATH", "release_identity.json"),
        ):
            value = getattr(self, name)
            if type(value) is not type(expected) or value != expected:
                raise BundleLaunchError("Unsupported trusted bundled launch profile.")
        for name, expected in (
            (
                "PYTHON_VERSION",
                (3, 12, 10 if self.PLATFORM == "windows-x64" else 15, "final", 0),
            ),
            ("PYTHON_FLAGS", PYTHON_FLAGS),
        ):
            value = getattr(self, name)
            if (
                type(value) is not tuple
                or value != expected
                or any(type(a) is not type(b) for a, b in zip(value, expected, strict=True))
            ):
                raise BundleLaunchError("Unsupported trusted isolated Python profile.")
        if (
            type(self.SOURCE_COMMIT) is not str
            or re.fullmatch("[0-9a-f]{40}", self.SOURCE_COMMIT) is None
        ):
            raise BundleLaunchError("Invalid trusted source identity.")
        for name in (
            "RUNTIME_LOCK_SHA256",
            "BUNDLE_ID",
            "BOOTSTRAP_SHA256",
            "RELEASE_IDENTITY_SHA256",
            "BUNDLE_MANIFEST_SHA256",
            "PAYLOAD_SHA256",
        ):
            value = getattr(self, name)
            if type(value) is not str or _DIGEST.fullmatch(value) is None:
                raise BundleLaunchError("Invalid trusted bundled digest.")
        if (
            type(self.RELEASE_IDENTITY_BYTES) is not bytes
            or not 0 < len(self.RELEASE_IDENTITY_BYTES) <= MAX_RELEASE_BYTES
            or hashlib.sha256(self.RELEASE_IDENTITY_BYTES).hexdigest()
            != self.RELEASE_IDENTITY_SHA256
        ):
            raise BundleLaunchError("Trusted release bytes do not match their digest.")
        loader = self.ENTRY_LOADER
        if (
            type(loader) is not str
            or not 0 < len(loader) <= 4096
            or not loader.isascii()
            or "\0" in loader
        ):
            raise BundleLaunchError("Invalid trusted fixed entry loader.")


LAUNCH_CONSTANT_FIELDS = tuple(BundledLaunchConstants.__dataclass_fields__)


@dataclass(frozen=True, slots=True)
class BundledLaunchPolicy:
    descriptor: BundleDescriptor
    package_root: str
    cache_root: str
    release_data: bytes = field(repr=False)
    constants: BundledLaunchConstants = field(repr=False)
    windows_cache: WindowsCacheLocation | None = field(default=None, repr=False)

    def __post_init__(self):
        if (
            type(self.descriptor) is not BundleDescriptor
            or type(self.constants) is not BundledLaunchConstants
        ):
            raise BundleLaunchError("Bundled selection requires exact immutable setup records.")
        c, d = self.constants, self.descriptor
        if type(c.PLATFORM) is not str:
            raise BundleLaunchError("Unsupported trusted bundled launch profile.")
        windows = c.PLATFORM == "windows-x64"
        if windows:
            for name in LAUNCH_CONSTANT_FIELDS:
                value = getattr(c, name)
                if name in {"PYTHON_VERSION", "PYTHON_FLAGS"}:
                    types = (int, int, int, str, int) if name == "PYTHON_VERSION" else (str,) * 6
                    if (
                        type(value) is not tuple
                        or len(value) != len(types)
                        or any(
                            type(item) is not kind for item, kind in zip(value, types, strict=True)
                        )
                    ):
                        raise BundleLaunchError("Invalid trusted Windows constant shape.")
                else:
                    kind = (
                        int
                        if name in {"SCHEMA_VERSION", "PYTHON_BITS"}
                        else bytes
                        if name == "RELEASE_IDENTITY_BYTES"
                        else str
                    )
                    if type(value) is not kind:
                        raise BundleLaunchError("Invalid trusted Windows constant shape.")
            if (
                any(
                    type(getattr(d, name)) is not str
                    for name in BundleDescriptor.__dataclass_fields__
                )
                or type(self.windows_cache) is not WindowsCacheLocation
                or type(self.windows_cache.known_folder) is not str
                or type(self.windows_cache.cache_root) is not str
                or type(self.package_root) is not str
                or type(self.cache_root) is not str
                or type(self.release_data) is not bytes
            ):
                raise BundleLaunchError(
                    "Windows selection requires an exact automatic cache recipe."
                )
            c, d, location = replace(c), replace(d), replace(self.windows_cache)
            object.__setattr__(self, "constants", c)
            object.__setattr__(self, "descriptor", d)
            object.__setattr__(self, "windows_cache", location)
            package = _windows_path(self.package_root, directory=True)
            cache = _windows_path(self.cache_root, directory=True)
            # Case-insensitive overlap rejects aliases; it never establishes identity equality.
            left, right = ntpath.normcase(package), ntpath.normcase(cache)
            overlap = (
                left == right
                or left.startswith(right.rstrip("\\") + "\\")
                or right.startswith(left.rstrip("\\") + "\\")
            )
            path_join, check_path = ntpath.join, _windows_path
        else:
            if self.windows_cache is not None:
                raise BundleLaunchError(
                    "Linux bundled selection cannot carry a Windows cache recipe."
                )
            if sys.platform != "linux" or os.name != "posix":
                raise BundleLaunchError("Bundled live selection is currently Linux only.")
            package, cache = Path(_path(self.package_root)), Path(_path(self.cache_root))
            overlap = package == cache or package in cache.parents or cache in package.parents
            path_join, check_path = os.path.join, _path
        if overlap:
            raise BundleLaunchError("Package and cache roots must be disjoint.")
        if windows and self.cache_root != self.windows_cache.cache_root:
            raise BundleLaunchError("Windows automatic cache recipe differs from its root.")
        if type(self.release_data) is not bytes or self.release_data != c.RELEASE_IDENTITY_BYTES:
            raise BundleLaunchError("Captured release bytes differ from trusted launch constants.")
        release = parse_release_manifest(
            self.release_data,
            expected_platform=c.PLATFORM,
            limits=BundleLimits(max_json_bytes=MAX_RELEASE_BYTES),
        )
        expected_root = path_join(str(cache), c.BUNDLE_ID)
        for name, expected in (
            ("bundle_id", c.BUNDLE_ID),
            ("source_commit", c.SOURCE_COMMIT),
            ("runtime_lock_sha256", c.RUNTIME_LOCK_SHA256),
            ("platform", c.PLATFORM),
            ("manifest_sha256", c.BUNDLE_MANIFEST_SHA256),
            ("payload_sha256", c.PAYLOAD_SHA256),
        ):
            if getattr(d, name) != expected or getattr(release, name) != expected:
                raise BundleLaunchError("Captured bundled identity is inconsistent.")
        for name, expected in (
            ("root", expected_root),
            ("python_path", path_join(expected_root, *c.PYTHON_PATH.split("/"))),
            ("bootstrap_path", path_join(expected_root, c.BOOTSTRAP_PATH)),
        ):
            if check_path(getattr(d, name)) != expected:
                raise BundleLaunchError("Captured bundled runtime path is inconsistent.")
        # ld.so expands $ tokens and separates ':' entries even without a shell.
        native = str(Path(d.root) / "native")
        if not windows and (":" in native or "$" in native):
            raise BundleLaunchError(
                "Private native path cannot contain loader separators or tokens."
            )
        if len(self.descriptor_bytes()) > MAX_DESCRIPTOR_BYTES:
            raise BundleLaunchError("Setup descriptor exceeds its trusted byte limit.")

    def descriptor_bytes(self):
        return json.dumps(
            {"schema_version": 1, **asdict(self.descriptor)},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")

    def launch_environment(self):
        """Build the entire child allowlist from scratch; never consult os.environ."""
        if self.constants.PLATFORM == "windows-x64":
            # SystemRoot and per-operation TEMP are captured by the Windows worker.
            return {}
        return {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "LD_LIBRARY_PATH": str(Path(self.descriptor.root) / "native"),
        }


def capture_bundled_policy(
    descriptor, *, package_root, cache_root, release_data, constants, windows_cache=None
):
    """Bounded in-memory capture after preparation cleanup; no filesystem I/O.

    The caller supplies the literal fields of its trusted generated
    standalone_launch_constants module. Never pass model or descriptor JSON as
    launch constants. Full inventory verification belongs to each worker launch.
    """
    if windows_cache is not None:
        if (
            type(constants) is not dict
            or any(type(key) is not str for key in constants)
            or set(constants) != set(LAUNCH_CONSTANT_FIELDS)
            or type(constants["PLATFORM"]) is not str
            or constants["PLATFORM"] != "windows-x64"
        ):
            raise BundleLaunchError("Windows capture requires exact trusted constant fields.")
        for name in LAUNCH_CONSTANT_FIELDS:
            value = constants[name]
            if name in {"PYTHON_VERSION", "PYTHON_FLAGS"}:
                types = (int, int, int, str, int) if name == "PYTHON_VERSION" else (str,) * 6
                if (
                    type(value) is not tuple
                    or len(value) != len(types)
                    or any(type(item) is not kind for item, kind in zip(value, types, strict=True))
                ):
                    raise BundleLaunchError("Invalid trusted Windows constant shape.")
            else:
                kind = (
                    int
                    if name in {"SCHEMA_VERSION", "PYTHON_BITS"}
                    else bytes
                    if name == "RELEASE_IDENTITY_BYTES"
                    else str
                )
                if type(value) is not kind:
                    raise BundleLaunchError("Invalid trusted Windows constant shape.")
        if (
            type(descriptor) is not BundleDescriptor
            or any(
                type(getattr(descriptor, name)) is not str
                for name in BundleDescriptor.__dataclass_fields__
            )
            or type(windows_cache) is not WindowsCacheLocation
            or type(windows_cache.known_folder) is not str
            or type(windows_cache.cache_root) is not str
            or type(package_root) is not str
            or type(cache_root) is not str
            or type(release_data) is not bytes
        ):
            raise BundleLaunchError("Windows capture requires exact automatic cache records.")
        windows_cache = replace(windows_cache)
    if not isinstance(constants, Mapping) or set(constants) != set(LAUNCH_CONSTANT_FIELDS):
        raise BundleLaunchError("Missing or unexpected trusted launch constant fields.")
    if (
        windows_cache is None
        and type(constants["PLATFORM"]) is str
        and constants["PLATFORM"] == "windows-x64"
    ):
        raise BundleLaunchError("Windows selection requires its automatic cache recipe.")
    if type(descriptor) is not BundleDescriptor:
        raise BundleLaunchError("Bundled selection requires an exact immutable descriptor.")
    return BundledLaunchPolicy(
        BundleDescriptor(**asdict(descriptor)),
        package_root,
        cache_root,
        release_data,
        BundledLaunchConstants(**dict(constants)),
        windows_cache,
    )


class BundledOperationOwner:
    """One worker's original pin and descriptor resources, retained on uncertainty."""

    def __init__(self, policy):
        if type(policy) is not BundledLaunchPolicy:
            raise BundleLaunchError("Bundled launch requires its captured policy.")
        self.policy, self.pin = policy, None
        self._directory = self._path = None
        self._write_fd = self._read_fd = None
        self._descriptor_created = False
        self._write_close_attempted = self._read_close_attempted = False
        self.cleanup_uncertain = False
        self.cleanup_complete = False
        self._cleanup_attempted = False

    def acquire(self, *, timeout, cancelled):
        p = self.policy
        try:
            self.pin = pins.acquire_bundle_pin(
                p.cache_root, p.descriptor.bundle_id, "shared", timeout=timeout, cancelled=cancelled
            )
        except pins.BundlePinError as exc:
            if exc.pin is not None:
                # Acquisition already attempted cleanup. Do not retry it.
                self.pin = exc.pin
                self.cleanup_uncertain = True
            raise
        descriptor = materialize.verify_cached_bundle(
            p.package_root,
            p.cache_root,
            p.release_data,
            expected_platform="linux-x64",
            limits=BundleLimits(),
            pin=self.pin,
            cancelled=cancelled,
        )
        if descriptor != p.descriptor:
            raise BundleLaunchError("Verified runtime differs from the captured setup descriptor.")
        release = materialize._read_bounded(
            Path(p.package_root) / p.constants.RELEASE_IDENTITY_PATH, MAX_RELEASE_BYTES
        )
        if release != p.release_data:
            raise BundleLaunchError("Installed release identity changed after preparation.")
        bootstrap = materialize._read_bounded(Path(descriptor.bootstrap_path), 64 * 1024)
        if hashlib.sha256(bootstrap).hexdigest() != p.constants.BOOTSTRAP_SHA256:
            raise BundleLaunchError("Verified bootstrap differs from the trusted fixed loader.")
        if not (Path(descriptor.root) / "native").is_dir():
            raise BundleLaunchError("Verified private native directory is missing.")
        self.pin.assert_held()
        if cancelled():
            raise pins.BundlePinCancelled("bundled_launch_cancelled")
        self._directory = tempfile.mkdtemp(prefix="mechanical-cad-setup-")
        self._path = Path(self._directory) / "descriptor.json"
        self._write_fd = os.open(
            self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600
        )
        self._descriptor_created = True
        data = p.descriptor_bytes()
        while data:
            count = os.write(self._write_fd, data)
            if count <= 0:
                raise BundleLaunchError("Could not write bounded setup descriptor.")
            data = data[count:]
        self._close_fd("write")
        self._read_fd = os.open(self._path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if self._read_fd <= 2:
            raise BundleLaunchError("Setup descriptor cannot replace a standard stream.")
        self.pin.assert_held()

    def command(self):
        if self._read_fd is None or self.cleanup_uncertain or self._cleanup_attempted:
            raise BundleLaunchError("Bundled launch resources are unavailable.")
        return [
            self.policy.descriptor.python_path,
            *self.policy.constants.PYTHON_FLAGS,
            self.policy.constants.ENTRY_LOADER,
            str(self._read_fd),
        ]

    @property
    def pass_fds(self):
        return (self._read_fd,)

    def _close_fd(self, which):
        fd = getattr(self, "_" + which + "_fd")
        attempted = "_" + which + "_close_attempted"
        if fd is None or getattr(self, attempted):
            return
        setattr(self, attempted, True)
        try:
            os.close(fd)
        except BaseException:
            self.cleanup_uncertain = True
            raise

    def cleanup(self):
        """Call only after confirmed process and transport-file cleanup."""
        if self.cleanup_complete:
            return
        if self._cleanup_attempted or self.cleanup_uncertain:
            raise BundleCleanupUncertain(
                "Bundled resource cleanup is uncertain; ownership retained."
            )
        self._cleanup_attempted = True
        try:
            self._close_fd("write")
            self._close_fd("read")
            if self._descriptor_created:
                self._path.unlink()
            if self._directory is not None:
                os.rmdir(self._directory)
            if self.pin is not None:
                self.pin.release()
        except BaseException as exc:
            self.cleanup_uncertain = True
            raise BundleCleanupUncertain(
                "Bundled resource cleanup is uncertain; ownership retained."
            ) from exc
        self.cleanup_complete = True
