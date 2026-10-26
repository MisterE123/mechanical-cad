"""Bounded offline documentary wrapper; never a release or legal approval.

Only the unchanged local contract builder creates the internal base ZIP. Source
archives remain opaque outer files: no extraction, dependency discovery, network,
native import or candidate execution. See docs/STANDALONE_PACKAGE_MATERIALS.md.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import os
import re
import stat
import struct
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts/package_standalone_extension.py"
_SPEC = importlib.util.spec_from_file_location("_mcad_materials_base_builder", BUILDER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = BUILDER
_SPEC.loader.exec_module(BUILDER)
C = BUILDER.CONTRACTS
BuildError = BUILDER.BuildError
STATUS = BUILDER.STATUS
COVERAGE = "external-runtime-inputs-and-declared-project-package"
GENERATED = frozenset({"PACKAGED_MATERIALS.json", "MATERIALS.md"})
RESERVED = frozenset({"sources", "licenses", *(name.casefold() for name in GENERATED)})
SOURCE_SUFFIXES = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tar.xz",
    ".tar.bz2",
    ".tgz",
    ".txz",
    ".srpm",
    ".src.rpm",
)
LOOSE_IMPORT = re.compile(
    r"(?:\.(?:py|pyw|pyc|pyo|pth|pyd|dll|exe|dylib|so|com|bat|cmd|ps1|sh)(?:\..*)?)$", re.I
)
COMPONENT_FIELDS = {
    "id",
    "kind",
    "name",
    "declared_identity",
    "source_paths",
    "notice_paths",
    "provenance_paths",
    "unresolved_issue_ids",
}
MAP_FIELDS = {
    "schema_version",
    "source_commit",
    "platform",
    "runtime_lock_sha256",
    "source_inventory_sha256",
    "runtime_inventory_sha256",
    "coverage_scope",
    "materials_inventory_sha256",
    "components",
    "runtime_bindings",
    "unresolved_issues",
}
ROLES = frozenset({"missing_source_material", "missing_notice_material", "other_unresolved"})


@dataclass(frozen=True)
class MaterialsLimits(C.BundleLimits):
    """Trusted v1 ceilings. Callers/tests may reduce, never enlarge, any ceiling."""

    max_outer_zip_bytes: int = 1024 * 1024 * 1024
    max_components: int = 256
    max_issues: int = 1024
    max_runtime_bindings: int = 50_000
    max_references: int = 100_000
    max_text_bytes: int = 1024
    max_issue_text_bytes: int = 4096
    max_id_bytes: int = 128

    def __post_init__(self):
        super().__post_init__()
        for field in fields(self):
            if getattr(self, field.name) > field.default:
                raise BuildError("Materials limits may only reduce trusted ceilings.")


def _limits(limits):
    if limits is None:
        return MaterialsLimits()
    if type(limits) is not MaterialsLimits:
        raise BuildError("Expected trusted MaterialsLimits.")
    return limits


def _records(inventory):
    return sorted((asdict(item) for item in inventory), key=lambda item: item["path"])


def _inventory_digest(inventory):
    return BUILDER._digest(BUILDER._json(_records(inventory)))


def _text(value, maximum):
    if type(value) is not str or not value.strip():
        raise BuildError("Expected nonempty materials text.")
    try:
        size = len(value.encode("utf-8", errors="strict"))
    except UnicodeError as exc:
        raise BuildError("Invalid materials Unicode.") from exc
    if size > maximum or any(unicodedata.category(char).startswith("C") for char in value):
        raise BuildError("Materials text exceeds its limit or contains control characters.")
    return value


def _identifier(value, limits):
    _text(value, limits.max_id_bytes)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value, flags=re.ASCII) is None:
        raise BuildError("Expected an ASCII stable materials identifier.")
    return value


def _array(value, maximum, *, nonempty=False):
    if type(value) is not list or not int(nonempty) <= len(value) <= maximum:
        raise BuildError("Materials collection exceeds its trusted count.")
    return value


def _parse_map(data, *, source_commit, platform, runtime_lock, source, runtime, materials, limits):
    """Detach, bound, check exact declarations, then canonicalize in linear passes."""
    value = C._exact(C._json(data, limits), MAP_FIELDS)
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise BuildError("Unsupported materials schema.")
    C.bundle_identity(value["source_commit"], value["runtime_lock_sha256"], value["platform"])
    expected = {
        "source_commit": source_commit,
        "platform": platform,
        "runtime_lock_sha256": BUILDER._digest(runtime_lock),
        "source_inventory_sha256": _inventory_digest(source),
        "runtime_inventory_sha256": _inventory_digest(runtime),
        "materials_inventory_sha256": _inventory_digest(materials),
        "coverage_scope": COVERAGE,
    }
    for name, expected_value in expected.items():
        if name.endswith("sha256"):
            C._digest(value[name])
        if value[name] != expected_value:
            raise BuildError(f"Materials identity mismatch: {name}")
    components = _array(value["components"], limits.max_components, nonempty=True)
    issues = _array(value["unresolved_issues"], limits.max_issues)
    bindings = _array(value["runtime_bindings"], min(limits.max_runtime_bindings, limits.max_files))
    # Reject aggregate references before sorting or resolving any reference set.
    references = 0
    for item in components:
        C._exact(item, COMPONENT_FIELDS)
        for key in ("source_paths", "notice_paths", "provenance_paths", "unresolved_issue_ids"):
            references += len(_array(item[key], limits.max_references))
            if references > limits.max_references:
                raise BuildError("Materials references exceed trusted limit.")
    for item in bindings:
        C._exact(item, {"path", "component_ids"})
        references += len(_array(item["component_ids"], limits.max_references, nonempty=True))
        if references > limits.max_references:
            raise BuildError("Materials references exceed trusted limit.")

    by_issue, by_component = {}, {}
    for item in issues:
        C._exact(item, {"id", "role", "description"})
        identifier = _identifier(item["id"], limits)
        if identifier in by_issue or type(item["role"]) is not str or item["role"] not in ROLES:
            raise BuildError("Duplicate issue or unknown unresolved role.")
        _text(item["description"], limits.max_issue_text_bytes)
        by_issue[identifier] = item
    material_paths, runtime_paths = {i.path for i in materials}, {i.path for i in runtime}
    used_materials, used_issues, external, project = set(), set(), set(), set()

    def reference_set(items, allowed, validator):
        seen = set()
        for item in items:
            validator(item)
            if item not in allowed or item in seen:
                raise BuildError("Unknown or duplicate materials reference.")
            seen.add(item)
        return seen

    for item in components:
        identifier = _identifier(item["id"], limits)
        if identifier in by_component:
            raise BuildError("Duplicate component identifier.")
        if item["kind"] == "external_runtime":
            external.add(identifier)
        elif item["kind"] == "project_package":
            project.add(identifier)
        else:
            raise BuildError("Unknown component kind.")
        _text(item["name"], limits.max_text_bytes)
        _text(item["declared_identity"], limits.max_text_bytes)
        for key in ("source_paths", "notice_paths", "provenance_paths"):
            used_materials.update(
                reference_set(item[key], material_paths, lambda p: C.validate_path(p, limits))
            )
            prefix = {"source_paths": "sources/", "notice_paths": "licenses/"}.get(key)
            if prefix is not None and any(not path.startswith(prefix) for path in item[key]):
                raise BuildError("Material reference has the wrong declared role prefix.")
        linked = reference_set(
            item["unresolved_issue_ids"], by_issue, lambda i: _identifier(i, limits)
        )
        used_issues.update(linked)
        roles = {by_issue[i]["role"] for i in linked}
        for key, role in (
            ("source_paths", "missing_source_material"),
            ("notice_paths", "missing_notice_material"),
        ):
            if not item[key] and role not in roles:
                raise BuildError(f"Empty {key} requires its typed unresolved issue.")
        by_component[identifier] = item
    if len(project) != 1:
        raise BuildError("Exactly one project_package component is required.")
    used_runtime, used_components = set(), set()
    for item in bindings:
        path = C.validate_path(item["path"], limits)
        if path not in runtime_paths or path in used_runtime:
            raise BuildError("Unknown or duplicate runtime binding.")
        used_runtime.add(path)
        used_components.update(
            reference_set(item["component_ids"], external, lambda i: _identifier(i, limits))
        )
    if used_runtime != runtime_paths or used_components != external:
        raise BuildError("Runtime coverage or external component use is incomplete.")
    if used_materials != material_paths or used_issues != by_issue.keys():
        raise BuildError("Unreferenced material or unresolved issue.")
    for item in components:
        for key in ("source_paths", "notice_paths", "provenance_paths", "unresolved_issue_ids"):
            item[key].sort()
    for item in bindings:
        item["component_ids"].sort()
    components.sort(key=lambda item: item["id"])
    bindings.sort(key=lambda item: item["path"])
    issues.sort(key=lambda item: item["id"])
    _bounded(BUILDER._json(value), limits)
    return value


def _bounded(data, limits):
    if len(data) > limits.max_json_bytes:
        raise BuildError("Generated materials document exceeds trusted byte limit.")
    return data


def _material_inventory(files, limits):
    materials = C.validate_file_inventory(files, limits=limits)
    for item in materials:
        prefix, _, relative = item.path.partition("/")
        if item.mode != 0o644 or prefix not in {"sources", "licenses"} or not relative:
            raise BuildError("Materials require outer sources/ or licenses/ and mode 0644.")
        if prefix == "sources" and not relative.lower().endswith(SOURCE_SUFFIXES):
            raise BuildError("Source materials must be opaque source archives.")
        if prefix == "licenses" and any(LOOSE_IMPORT.search(p) for p in relative.split("/")):
            raise BuildError("Loose importable or executable notice materials are forbidden.")
    return materials


def _escape(value):
    # No raw markup, links or remote loads from caller-supplied names or paths.
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", html.escape(value, quote=True))


def _index(value, materials, base_sha256, limits):
    lines = [
        "# Packaged materials",
        "",
        STATUS,
        "",
        "Declared coverage: " + COVERAGE,
        "",
        "Hashes and bindings establish declared coverage and exact bytes only. They do not",
        "establish dependency discovery, corresponding-source equivalence, license sufficiency,",
        "copyright ownership, redistribution rights, rebuild success or native/release approval.",
        "BUILD_CONTRACT.json describes the unchanged legacy base contract.",
        "Source archives are inert and are never extracted or executed by this wrapper.",
        "",
        "Base ZIP SHA-256: " + base_sha256,
        "Source commit: " + value["source_commit"],
        "Platform: " + value["platform"],
        "",
    ]
    for component in value["components"]:
        lines += [
            "## " + _escape(component["id"]),
            "Name: " + _escape(component["name"]),
            "Kind: " + component["kind"],
            "Declared identity: " + _escape(component["declared_identity"]),
        ]
        for key in ("source_paths", "notice_paths", "provenance_paths", "unresolved_issue_ids"):
            lines.append(key + ": " + (", ".join(map(_escape, component[key])) or "none supplied"))
        lines.append("")
    lines += ["## Runtime bindings", ""]
    for binding in value["runtime_bindings"]:
        lines.append(
            _escape(binding["path"]) + ": " + ", ".join(map(_escape, binding["component_ids"]))
        )
    lines += ["", "## Material bytes", ""]
    for item in sorted(materials, key=lambda item: item.path):
        lines.append(f"{_escape(item.path)}: {item.size} bytes; SHA-256 {item.sha256}")
    lines += ["", "## Declared unresolved issues", ""]
    for issue in value["unresolved_issues"]:
        lines.append(f"{_escape(issue['id'])} ({issue['role']}): {_escape(issue['description'])}")
    if not value["unresolved_issues"]:
        lines.append("None declared. This is not legal or release approval.")
    return _bounded(("\n".join(lines) + "\n").encode("utf-8"), limits)


def _zip_directory(stream, size, limits):
    """Bound allocation before ZipFile; same non-ZIP64 format as the runtime leaf."""
    if not 22 <= size <= limits.max_outer_zip_bytes:
        raise BuildError("Outer ZIP size exceeds trusted limits.")
    stream.seek(size - 22)
    tail = stream.read(22)
    if len(tail) != 22:
        raise BuildError("Truncated ZIP end record.")
    signature, disk, cd_disk, disk_count, count, cd_size, offset, comment = struct.unpack(
        "<4s4H2LH", tail
    )
    if signature != b"PK\x05\x06" or disk or cd_disk or comment or disk_count != count:
        raise BuildError("Unsupported ZIP end record.")
    if count == 65535 or offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        raise BuildError("ZIP64 is outside the bounded materials format.")
    if not 1 <= count <= limits.max_files or cd_size > limits.max_zip_metadata_bytes:
        raise BuildError("Outer ZIP metadata exceeds trusted limits.")
    if offset + cd_size != size - 22:
        raise BuildError("Unexpected ZIP directory extent.")
    stream.seek(0)
    if stream.read(4) != b"PK\x03\x04":
        raise BuildError("Outer ZIP must begin with a local file record.")
    stream.seek(0)
    return count


def _zip_metadata(info):
    return (
        info.filename,
        info.date_time,
        info.compress_type,
        info.create_system,
        info.create_version,
        info.extract_version,
        info.flag_bits,
        info.volume,
        info.internal_attr,
        info.external_attr,
        info.extra,
        info.comment,
        info.CRC,
        info.file_size,
        info.compress_size,
        info.header_offset,
    )


def _archive_snapshot(path, limits, expected_names, *, expected=None):
    """Bound metadata first, then hash every member without extracting anything."""
    with BUILDER._open(path) as stream:
        size = os.fstat(stream.fileno()).st_size
        count = _zip_directory(stream, size, limits)
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            if count != len(infos) or {i.filename for i in infos} != expected_names:
                raise BuildError("Unexpected base or final ZIP members.")
            records, metadata = [], {}
            for info in infos:
                stored = info.filename.endswith("/payload.zip")
                if (
                    info.date_time != (1980, 1, 1, 0, 0, 0)
                    or info.create_system != 3
                    or info.external_attr != (stat.S_IFREG | 0o644) << 16
                    or info.compress_type
                    != (zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
                    or info.flag_bits & ~0x800
                    or info.extra
                    or info.comment
                    or info.extract_version > 20
                    or info.create_version > 20
                    or info.volume
                    or info.internal_attr
                ):
                    raise BuildError("Unexpected outer member metadata.")
                records.append(
                    {
                        "path": info.filename,
                        "size": info.file_size,
                        "mode": 0o644,
                        "sha256": "0" * 64,
                    }
                )
                metadata[info.filename] = _zip_metadata(info)
            inventory = C.validate_file_inventory(records, limits=limits)
            result = []
            for item, info in zip(inventory, infos, strict=True):
                digest, total = hashlib.sha256(), 0
                with archive.open(info) as member:
                    while chunk := member.read(min(limits.chunk_bytes, item.size - total + 1)):
                        total += len(chunk)
                        if total > item.size:
                            raise BuildError("ZIP member grew.")
                        digest.update(chunk)
                if total != item.size:
                    raise BuildError("ZIP member size mismatch.")
                result.append(C.BundleFile(item.path, item.size, digest.hexdigest(), item.mode))
            snapshot = {item.path: item for item in result}
            if expected is not None and snapshot != expected:
                raise BuildError("Retained ZIP member bytes changed.")
    return snapshot, metadata


def _file_item(path, maximum, limits):
    with BUILDER._open(path) as stream:
        size = os.fstat(stream.fileno()).st_size
        if size > maximum:
            raise BuildError("Archive exceeds trusted compressed byte limit.")
        digest, total = hashlib.sha256(), 0
        while chunk := stream.read(min(limits.chunk_bytes, size - total + 1)):
            total += len(chunk)
            if total > size:
                raise BuildError("Archive grew during hashing.")
            digest.update(chunk)
        if total != size:
            raise BuildError("Archive shrank during hashing.")
    return C.BundleFile(path.name, size, digest.hexdigest(), 0o644)


def _verify_file(path, item, limits):
    with BUILDER._open(path) as stream:
        BUILDER._copy_checked(stream, None, item, limits)


class _CappedOutput:
    def __init__(self, stream, maximum):
        self.stream, self.maximum = stream, maximum

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def write(self, data):
        if self.stream.tell() + len(data) > self.maximum:
            raise BuildError("Final ZIP exceeds trusted compressed byte limit.")
        return self.stream.write(data)


def _append(path, entries, limits):
    with path.open("r+b") as stream:
        with zipfile.ZipFile(
            _CappedOutput(stream, limits.max_outer_zip_bytes), "a", allowZip64=False
        ) as archive:
            for item, source in sorted(entries, key=lambda pair: pair[0].path):
                info = BUILDER._zip_info(
                    item.path, item.mode, stored=item.path.endswith("/payload.zip")
                )
                info.file_size = item.size
                with archive.open(info, "w") as target:
                    if type(source) is bytes:
                        if BUILDER._digest(source) != item.sha256 or len(source) != item.size:
                            raise BuildError("Generated materials bytes changed.")
                        target.write(source)
                    else:
                        with BUILDER._open(source) as material:
                            BUILDER._copy_checked(material, target, item, limits)


def _write_receipt(path, receipt):
    with path.open("xb") as stream:
        stream.write(BUILDER._json(receipt))


def build_materials_extension(
    *,
    source_root,
    source_commit,
    source_files,
    runtime_root,
    runtime_files,
    runtime_lock,
    platform,
    python_path,
    destination,
    materials_root,
    materials_files,
    materials_map,
    limits=None,
):
    """Build one unqualified outer package from required exact, separately rooted inputs.

    No caller-supplied base ZIP is accepted. A published result is irrevocable to
    this wrapper, even when the subsequent diagnostic receipt cannot be stored.
    """
    limits = _limits(limits)
    roots = tuple(BUILDER._path(root) for root in (source_root, runtime_root, materials_root))
    source_root, runtime_root, materials_root = roots
    destination = Path(os.path.abspath(destination))
    output_root = BUILDER._path(destination.parent)
    if any(output_root == root or root in output_root.parents for root in roots):
        raise BuildError("Materials output must be outside all input trees.")
    if os.path.lexists(destination):
        raise BuildError("Materials destination already exists.")
    if type(runtime_lock) is not bytes or not 0 < len(runtime_lock) <= limits.max_json_bytes:
        raise BuildError("Runtime lock must be bounded immutable bytes.")
    bundle_id = C.bundle_identity(source_commit, BUILDER._digest(runtime_lock), platform)
    source = C.validate_file_inventory(source_files, limits=limits)
    runtime = C.validate_file_inventory(runtime_files, limits=limits)
    materials = _material_inventory(materials_files, limits)
    value = _parse_map(
        materials_map,
        source_commit=source_commit,
        platform=platform,
        runtime_lock=runtime_lock,
        source=source,
        runtime=runtime,
        materials=materials,
        limits=limits,
    )
    map_sha256 = BUILDER._digest(BUILDER._json(value))
    base_names, source_outer = set(), {}
    for item in source:
        if item.path.startswith(BUILDER.ADDON_PREFIX):
            name = item.path.removeprefix(BUILDER.ADDON_PREFIX)
            if name.split("/", 1)[0].casefold() in RESERVED:
                raise BuildError("Source add-on shadows reserved materials namespace.")
        elif item.path in {"LICENSE", "THIRD_PARTY_NOTICES.md"}:
            name = item.path
        else:
            continue
        base_names.add(name)
        source_outer[name] = C.BundleFile(name, item.size, item.sha256, 0o644)
    base_names.update(
        {
            "blender_manifest.toml",
            "release_identity.json",
            "BUILD_CONTRACT.json",
            "runtime-lock.json",
            BUILDER.GENERATED_LAUNCH_MODULE,
            f"_backend/{bundle_id}/bundle-manifest.json",
            f"_backend/{bundle_id}/payload.zip",
        }
    )
    material_paths = {i.path for i in materials}
    if BUILDER._tree_files(materials_root, limits) != material_paths:
        raise BuildError("Materials tree differs from its exact inventory.")
    for item in materials:
        _verify_file(materials_root / item.path, item, limits)
    work = Path(tempfile.mkdtemp(prefix="standalone-materials-", dir=output_root))
    base_path = work / "base.zip"
    base_receipt = BUILDER.build_contract_extension(
        source_root=source_root,
        source_commit=source_commit,
        source_files=_records(source),
        runtime_root=runtime_root,
        runtime_files=_records(runtime),
        runtime_lock=runtime_lock,
        platform=platform,
        python_path=python_path,
        destination=base_path,
        limits=limits,
    )
    base_item = _file_item(base_path, limits.max_outer_zip_bytes, limits)
    if (
        base_receipt.get("published") is not True
        or base_receipt.get("status") != STATUS
        or type(base_receipt.get("bytes")) is not int
        or base_receipt["bytes"] != base_item.size
        or base_receipt.get("sha256") != base_item.sha256
        or base_receipt.get("bundle_id") != bundle_id
    ):
        raise BuildError("Internal base builder receipt does not match its exact archive.")
    base, base_metadata = _archive_snapshot(base_path, limits, base_names)
    for name, item in source_outer.items():
        if base[name] != item:
            raise BuildError("Base member differs from inventoried source.")
    if base["runtime-lock.json"].sha256 != BUILDER._digest(runtime_lock):
        raise BuildError("Base runtime lock differs.")
    _verify_file(base_path, base_item, limits)
    record = {
        "schema_version": 1,
        "status": STATUS,
        "qualification": "Mechanical declared coverage and bytes only; no legal, native or release approval",
        "base_zip_sha256": base_item.sha256,
        "base_zip_bytes": base_item.size,
        "legacy_base_contract_path": "BUILD_CONTRACT.json",
        "wrapper_sha256": BUILDER._digest(Path(__file__).read_bytes()),
        "builder_sha256": BUILDER._digest(BUILDER_PATH.read_bytes()),
        "contract_sha256": BUILDER._digest(BUILDER.CONTRACT_PATH.read_bytes()),
        "materials_map_sha256": map_sha256,
        "materials_inventory_sha256": _inventory_digest(materials),
        "source_inventory_sha256": _inventory_digest(source),
        "runtime_inventory_sha256": _inventory_digest(runtime),
        "runtime_lock_sha256": BUILDER._digest(runtime_lock),
        "source_commit": source_commit,
        "platform": platform,
        "bundle_id": bundle_id,
        "material_files": len(materials),
        "material_bytes": sum(i.size for i in materials),
        "materials_inventory": _records(materials),
        "materials_map": value,
    }
    documents = {
        "PACKAGED_MATERIALS.json": _bounded(BUILDER._json(record), limits),
        "MATERIALS.md": _index(value, materials, base_item.sha256, limits),
    }
    additions = [(item, materials_root / item.path) for item in materials]
    for name, data in documents.items():
        additions.append((C.BundleFile(name, len(data), BUILDER._digest(data), 0o644), data))
    final_inventory = C.validate_file_inventory(
        [asdict(i) for i in base.values()] + [asdict(i) for i, _ in additions],
        limits=limits,
    )
    # Exact fixed central-directory fields (46 bytes) plus UTF-8 file names; no extras/comments.
    if (
        sum(46 + len(i.path.encode("utf-8")) for i in final_inventory)
        > limits.max_zip_metadata_bytes
    ):
        raise BuildError("Aggregate outer ZIP metadata exceeds trusted limit.")
    final_path = work / "materials-extension.zip"
    with final_path.open("xb") as target, BUILDER._open(base_path) as original:
        BUILDER._copy_checked(
            original, _CappedOutput(target, limits.max_outer_zip_bytes), base_item, limits
        )
    _append(final_path, additions, limits)
    final_expected = {i.path: i for i in final_inventory}
    _, final_metadata = _archive_snapshot(
        final_path, limits, set(final_expected), expected=final_expected
    )
    if any(final_metadata[name] != metadata for name, metadata in base_metadata.items()):
        raise BuildError("Original base ZIP metadata changed.")
    _verify_file(base_path, base_item, limits)
    # Recheck original trees after streaming; a changed/extra material is never silently ignored.
    if BUILDER._tree_files(materials_root, limits) != material_paths:
        raise BuildError("Materials tree changed during packaging.")
    for root, inventory in (
        (source_root, source),
        (runtime_root, runtime),
        (materials_root, materials),
    ):
        for item in inventory:
            _verify_file(root / item.path, item, limits)
    final_item = _file_item(final_path, limits.max_outer_zip_bytes, limits)
    receipt = {
        "status": STATUS,
        "destination": str(destination),
        "work_directory": str(work),
        "sha256": final_item.sha256,
        "bytes": final_item.size,
        "bundle_id": bundle_id,
        "base_zip_sha256": base_item.sha256,
        "base_zip_bytes": base_item.size,
        "materials_map_sha256": map_sha256,
        "materials_inventory_sha256": _inventory_digest(materials),
        "source_commit": source_commit,
        "platform": platform,
        "material_files": len(materials),
        "material_bytes": sum(i.size for i in materials),
        "outer_files": len(final_inventory),
        "outer_expanded_bytes": sum(i.size for i in final_inventory),
        "published": False,
        "receipt_phase": "before_publication",
    }
    _write_receipt(work / "MATERIALS_RECEIPT.before.json", receipt)
    _verify_file(final_path, final_item, limits)
    os.link(final_path, destination)
    receipt["published"] = True
    receipt["receipt_phase"] = "after_publication"
    try:
        _write_receipt(work / "MATERIALS_RECEIPT.json", receipt)
    except OSError as exc:
        receipt["receipt_write_error"] = type(exc).__name__
        receipt["receipt_phase"] = "after_publication_receipt_write_failed"
    return receipt
