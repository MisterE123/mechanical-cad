"""Bounded, native-free standalone bundle data contracts; no selection authority.

These leaves are deliberately disconnected from registration and live backend
selection. Hashes establish consistency, not publisher authenticity. Limits come
from trusted release policy, never from the JSON being checked.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

PLATFORMS = frozenset({"linux-x64", "windows-x64"})
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"})


class BundleError(ValueError):
    """Malformed, mismatched or unsupported bundle data."""


@dataclass(frozen=True)
class BundleLimits:
    """Trusted resource ceilings; reducing these is useful for synthetic tests."""

    max_json_bytes: int = 8 * 1024 * 1024
    max_json_depth: int = 8
    max_files: int = 50_000
    max_path_bytes: int = 240
    max_path_depth: int = 16
    max_file_bytes: int = 512 * 1024 * 1024
    max_total_bytes: int = 2 * 1024 * 1024 * 1024
    max_payload_bytes: int = 1024 * 1024 * 1024
    max_zip_metadata_bytes: int = 16 * 1024 * 1024
    chunk_bytes: int = 128 * 1024
    reserve_free_bytes: int = 16 * 1024 * 1024

    def __post_init__(self):
        for name, value in vars(self).items():
            if type(value) is not int or value < (0 if name == "reserve_free_bytes" else 1):
                raise BundleError("Bundle limits must be trusted positive integers.")
        if self.max_files >= 65535:
            raise BundleError("This bounded format does not support ZIP64.")


@dataclass(frozen=True)
class ReleaseManifest:
    bundle_id: str
    source_commit: str
    runtime_lock_sha256: str
    platform: str
    manifest_path: str
    manifest_sha256: str
    payload_path: str
    payload_sha256: str
    payload_size: int


@dataclass(frozen=True)
class BundleFile:
    path: str
    size: int
    sha256: str
    mode: int


@dataclass(frozen=True)
class BundleManifest:
    bundle_id: str
    platform: str
    python_path: str
    bootstrap_path: str
    files: tuple[BundleFile, ...]


@dataclass(frozen=True)
class BundleDescriptor:
    """Primitive setup identity only. Neither a lifetime pin nor CAD evidence.

    Paths always describe the verified final tree. A consumer must reacquire a
    shared OS lifetime pin and revalidate after any preparation-to-launch gap.
    """

    bundle_id: str
    source_commit: str
    runtime_lock_sha256: str
    platform: str
    manifest_sha256: str
    payload_sha256: str
    root: str
    python_path: str
    bootstrap_path: str

    def __post_init__(self):
        for value in vars(self).values():
            if type(value) is not str or not value or len(value) > 32767 or "\x00" in value:
                raise BundleError("Bundle descriptor requires bounded primitive strings.")
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise BundleError("Invalid Unicode bundle descriptor.") from exc
        for value in (
            self.bundle_id,
            self.runtime_lock_sha256,
            self.manifest_sha256,
            self.payload_sha256,
        ):
            _digest(value)
        if _COMMIT.fullmatch(self.source_commit) is None or self.platform not in PLATFORMS:
            raise BundleError("Invalid bundle descriptor identity.")


def _exact(value, keys):
    if type(value) is not dict or value.keys() != keys:
        raise BundleError("Bundle object has missing or unknown fields.")
    return value


def _integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise BundleError("Bundle integer is outside its trusted limit.")
    return value


def _digest(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise BundleError("Expected lowercase SHA-256 hex.")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BundleError("Duplicate JSON field.")
        result[key] = value
    return result


def _constant(value):
    raise BundleError("Non-finite JSON number.")


def _json(data, limits):
    if type(data) is not bytes or len(data) > limits.max_json_bytes:
        raise BundleError("Manifest must be bounded immutable bytes.")
    try:
        text = data.decode("utf-8", errors="strict")
        depth, quoted, escaped = 0, False, False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > limits.max_json_depth:
                    raise BundleError("Manifest nesting exceeds trusted limit.")
            elif char in "]}":
                depth -= 1
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BundleError("Invalid UTF-8 JSON manifest.") from exc


def validate_path(value, limits):
    """One portable canonical relative spelling, including case-sensitive hosts."""
    if type(value) is not str or not value or unicodedata.normalize("NFC", value) != value:
        raise BundleError("Bundle path must be nonempty NFC text.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise BundleError("Invalid Unicode bundle path.") from exc
    if len(encoded) > limits.max_path_bytes or len(value.split("/")) > limits.max_path_depth:
        raise BundleError("Bundle path exceeds trusted limit.")
    for part in value.split("/"):
        if not part or part in {".", ".."} or part.endswith((".", " ")):
            raise BundleError("Noncanonical bundle path.")
        if any(unicodedata.category(c).startswith("C") or c in '\\:<>"|?*' for c in part):
            raise BundleError("Unsafe bundle path character.")
        stem = part.split(".", 1)[0].rstrip(" ").upper()
        if stem in _RESERVED or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem):
            raise BundleError("Reserved Windows path component.")
    return value


def bundle_identity(source_commit, runtime_lock_sha256, platform):
    if type(source_commit) is not str or _COMMIT.fullmatch(source_commit) is None:
        raise BundleError("Expected exact source commit.")
    _digest(runtime_lock_sha256)
    if type(platform) is not str or platform not in PLATFORMS:
        raise BundleError("Unsupported bundle platform.")
    identity = [source_commit, runtime_lock_sha256, platform]
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode("ascii")).hexdigest()


def parse_release_manifest(data, *, expected_platform, limits):
    value = _exact(
        _json(data, limits),
        {
            "schema_version",
            "bundle_id",
            "source_commit",
            "runtime_lock_sha256",
            "platform",
            "manifest_path",
            "manifest_sha256",
            "payload_path",
            "payload_sha256",
            "payload_size",
        },
    )
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise BundleError("Unsupported release manifest schema.")
    expected_id = bundle_identity(
        value["source_commit"], value["runtime_lock_sha256"], value["platform"]
    )
    if value["platform"] != expected_platform or value["bundle_id"] != expected_id:
        raise BundleError("Release platform or bundle identity mismatch.")
    for key, name in (("manifest_path", "bundle-manifest.json"), ("payload_path", "payload.zip")):
        if value[key] != f"_backend/{expected_id}/{name}":
            raise BundleError("Unexpected packaged bundle location.")
        validate_path(value[key], limits)
    for key in ("manifest_sha256", "payload_sha256"):
        _digest(value[key])
    _integer(value["payload_size"], limits.max_payload_bytes)
    return ReleaseManifest(**{key: item for key, item in value.items() if key != "schema_version"})


def validate_file_inventory(files, *, limits):
    """Validate the shared bounded regular-file inventory and detach its records."""
    if type(files) is not list or not 1 <= len(files) <= limits.max_files:
        raise BundleError("Payload file count exceeds trusted limit.")
    entries, spelling, kinds, total = [], {}, {}, 0
    for item in files:
        _exact(item, {"path", "size", "sha256", "mode"})
        path = validate_path(item["path"], limits)
        if path.split("/", 1)[0].casefold() == ".bundle-ready.json":
            raise BundleError("Reserved materialization marker.")
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            key, kind = prefix.casefold(), index == len(parts)
            if key in spelling and (spelling[key] != prefix or kinds[key] != kind or kind):
                raise BundleError("Duplicate, case collision or file/directory conflict.")
            spelling[key], kinds[key] = prefix, kind
        size = _integer(item["size"], limits.max_file_bytes)
        total += size
        if total > limits.max_total_bytes:
            raise BundleError("Payload expanded size exceeds trusted limit.")
        if type(item["mode"]) is not int or item["mode"] not in {0o644, 0o755}:
            raise BundleError("Only regular 0644/0755 file modes are permitted.")
        entries.append(BundleFile(path, size, _digest(item["sha256"]), item["mode"]))
    return tuple(entries)


def parse_bundle_manifest(data, release, *, limits):
    if type(data) is not bytes or len(data) > limits.max_json_bytes:
        raise BundleError("Manifest must be bounded immutable bytes.")
    if hashlib.sha256(data).hexdigest() != release.manifest_sha256:
        raise BundleError("Payload manifest digest mismatch.")
    value = _exact(
        _json(data, limits),
        {
            "schema_version",
            "bundle_id",
            "platform",
            "python_path",
            "bootstrap_path",
            "files",
        },
    )
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise BundleError("Unsupported payload manifest schema.")
    if value["bundle_id"] != release.bundle_id or value["platform"] != release.platform:
        raise BundleError("Payload manifest identity mismatch.")
    entries = validate_file_inventory(value["files"], limits=limits)
    by_path = {item.path: item for item in entries}
    python_path = validate_path(value["python_path"], limits)
    bootstrap_path = validate_path(value["bootstrap_path"], limits)
    if bootstrap_path != "bootstrap.py" or not python_path.startswith("python/"):
        raise BundleError("Unexpected runtime entry-point layout.")
    for required in (python_path, bootstrap_path, "src/mechanical_cad/__init__.py"):
        if required not in by_path:
            raise BundleError("Missing runtime entry point or backend source root.")
    if release.platform == "windows-x64":
        if python_path != "python/python.exe":
            raise BundleError("Windows requires its direct bundled interpreter.")
    elif by_path[python_path].mode != 0o755:
        raise BundleError("POSIX interpreter requires explicit executable mode.")
    return BundleManifest(
        release.bundle_id, release.platform, python_path, bootstrap_path, tuple(entries)
    )
