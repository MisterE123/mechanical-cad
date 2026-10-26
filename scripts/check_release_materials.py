"""Offline accounting gate for a pinned materials review, not legal clearance.

Checks the exact tagged project source, runtime/material bytes, complete component
and issue review coverage. Does not build, execute, qualify or publish anything.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import stat
import struct
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "_materials_candidate_adapter", Path(__file__).with_name("build_release_candidate.py")
)
A = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(A)

REVIEW_FIELDS = {
    "schema_version",
    "source_commit",
    "platform",
    "materials_map_sha256",
    "project_source_path",
    "components",
    "issues",
}
COMPONENT_FIELDS = {
    "id",
    "selected_license_route",
    "source_status",
    "notice_status",
    "evidence_paths",
    "rationale",
}
ISSUE_FIELDS = {"id", "disposition", "evidence_paths", "rationale"}
SOURCE_STATUSES = {"reviewed_present", "reviewed_not_required", "blocked"}
NOTICE_STATUSES = {"reviewed_present", "blocked"}
DISPOSITIONS = {"reviewed_nonblocking", "blocks_distribution"}


class ReviewError(ValueError):
    """Malformed, stale or incomplete review accounting."""


def require(condition, message):
    if not condition:
        raise ReviewError(message)


def fields(value, expected):
    require(type(value) is dict and set(value) == expected, "Unexpected review fields")


def entries(items, expected_ids, expected_fields):
    require(type(items) is list and len(items) == len(expected_ids), "Incomplete review coverage")
    result = {}
    for item in items:
        fields(item, expected_fields)
        identifier = item["id"]
        require(
            type(identifier) is str and identifier in expected_ids and identifier not in result,
            "Unknown or duplicate review id",
        )
        result[identifier] = item
    require(set(result) == set(expected_ids), "Incomplete review coverage")
    return result


def text(value):
    require(
        type(value) is str
        and value.strip()
        and len(value.encode("utf-8")) <= 4096
        and all(not unicodedata.category(c).startswith("C") for c in value),
        "Invalid review text",
    )


def evidence(row, allowed):
    paths = row["evidence_paths"]
    require(type(paths) is list and 0 < len(paths) <= len(allowed), "Missing review evidence")
    require(all(type(p) is str for p in paths), "Invalid evidence reference")
    require(
        len(set(paths)) == len(paths) and set(paths) <= allowed,
        "Unknown or duplicate review evidence",
    )
    text(row["rationale"])


def evaluate(review, materials_map, map_sha256):
    """Account for a review; callers must first authenticate map and inventory bytes."""
    fields(review, REVIEW_FIELDS)
    require(
        type(review["schema_version"]) is int and review["schema_version"] == 1,
        "Unsupported review schema",
    )
    for name, expected in (
        ("source_commit", materials_map["source_commit"]),
        ("platform", materials_map["platform"]),
        ("materials_map_sha256", map_sha256),
    ):
        require(review[name] == expected, "Review identity mismatch: " + name)
    components = {item["id"]: item for item in materials_map["components"]}
    issues = {item["id"]: item for item in materials_map["unresolved_issues"]}
    project = next(c for c in components.values() if c["kind"] == "project_package")
    require(
        type(review["project_source_path"]) is str
        and review["project_source_path"] in project["source_paths"],
        "Project source archive must be a declared project source",
    )
    reviews = entries(review["components"], components, COMPONENT_FIELDS)
    issue_reviews = entries(review["issues"], issues, ISSUE_FIELDS)
    component_blockers, issue_blockers = [], []
    for identifier, component in components.items():
        row = reviews[identifier]
        allowed = set(
            component["source_paths"] + component["notice_paths"] + component["provenance_paths"]
        )
        evidence(row, allowed)
        text(row["selected_license_route"])
        require(
            row["source_status"] in SOURCE_STATUSES and row["notice_status"] in NOTICE_STATUSES,
            "Unknown component review status",
        )
        require(
            component["kind"] != "project_package"
            or row["source_status"] != "reviewed_not_required",
            "Complete project source cannot be waived",
        )
        if row["source_status"] == "reviewed_present":
            require(
                component["source_paths"]
                and set(component["source_paths"]) <= set(row["evidence_paths"]),
                "Present source review must reference every declared source",
            )
        if row["notice_status"] == "reviewed_present":
            require(
                component["notice_paths"]
                and set(component["notice_paths"]) <= set(row["evidence_paths"]),
                "Present notice review must reference every declared notice",
            )
        if "blocked" in (row["source_status"], row["notice_status"]):
            component_blockers.append(identifier)
    for identifier, row in issue_reviews.items():
        affected = [c for c in components.values() if identifier in c["unresolved_issue_ids"]]
        allowed = {
            p
            for c in affected
            for key in ("source_paths", "notice_paths", "provenance_paths")
            for p in c[key]
        }
        evidence(row, allowed)
        require(row["disposition"] in DISPOSITIONS, "Unknown issue disposition")
        if row["disposition"] == "blocks_distribution":
            issue_blockers.append(identifier)
    blocked = bool(component_blockers or issue_blockers)
    return {
        "schema_version": 1,
        "status": "MATERIALS_REVIEW_BLOCKED" if blocked else "MATERIALS_REVIEW_RECORDED",
        "source_commit": materials_map["source_commit"],
        "platform": materials_map["platform"],
        "materials_map_sha256": map_sha256,
        "component_count": len(components),
        "retained_issue_count": len(issues),
        "blocked_component_ids": sorted(component_blockers),
        "blocked_issue_ids": sorted(issue_blockers),
        "reviewed_nonblocking_issue_ids": sorted(set(issues) - set(issue_blockers)),
        "retained_issue_ids": sorted(issues),
        "selected_license_routes": {
            i: reviews[i]["selected_license_route"] for i in sorted(reviews)
        },
        "legal_clearance": "NOT_ESTABLISHED_BY_THIS_TOOL",
        "native_qualification": "NOT_RUN",
        "release_admission": "NOT_ESTABLISHED_BY_THIS_TOOL",
    }


def verify_project_source(path, source_files):
    """Verify exact file-only repo-relative Git blobs; never extract or run them."""
    A.checked_path(path)
    size = path.stat().st_size
    require(
        path.suffix == ".zip" and 22 <= size <= A.MAX_SOURCE, "Project source must be a bounded ZIP"
    )
    expected = {item["path"]: item for item in source_files}
    with path.open("rb") as raw:
        raw.seek(size - 22)
        signature, disk, cd_disk, disk_count, count, cd_size, offset, comment = struct.unpack(
            "<4s4H2LH", raw.read(22)
        )
        require(
            signature == b"PK\x05\x06"
            and not disk
            and not cd_disk
            and not comment
            and disk_count == count == len(expected)
            and count < 65535
            and cd_size <= 16 * 1024 * 1024
            and offset + cd_size == size - 22,
            "Project source ZIP directory is unbounded or unsupported",
        )
        with zipfile.ZipFile(raw) as archive:
            infos = archive.infolist()
            require(len(infos) == count, "Project source archive count mismatch")
            seen, local_end = set(), 0
            for info in infos:
                name = info.filename
                A.source_path_parts(name)
                require(
                    name in expected and name not in seen and info.orig_filename == name,
                    "Unknown/duplicate project source member",
                )
                seen.add(name)
                item = expected[name]
                require(
                    not info.is_dir()
                    and not info.flag_bits & ~0x800
                    and info.create_system == 3
                    and info.extract_version <= 20
                    and info.external_attr >> 16 == stat.S_IFREG | item["mode"]
                    and info.file_size == item["size"]
                    and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    and not info.comment
                    and not info.extra
                    and not info.volume,
                    "Project source member metadata mismatch",
                )
                require(info.header_offset == local_end, "Project source ZIP gap/prefix")
                raw.seek(local_end)
                header = raw.read(30)
                require(len(header) == 30, "Truncated source ZIP local header")
                sig, ver, flags, method, _, _, crc, compressed, expanded, namesize, extra = (
                    struct.unpack("<4s5H3L2H", header)
                )
                encoded = name.encode("utf-8" if flags & 0x800 else "cp437")
                require(
                    sig == b"PK\x03\x04"
                    and ver == info.extract_version
                    and flags == info.flag_bits
                    and method == info.compress_type
                    and crc == info.CRC
                    and compressed == info.compress_size
                    and expanded == info.file_size
                    and namesize == len(encoded)
                    and not extra
                    and raw.read(namesize) == encoded,
                    "Source ZIP local metadata mismatch",
                )
                local_end += 30 + namesize + compressed
                require(local_end <= offset, "Project source ZIP overlaps directory")
                digest, length = hashlib.sha256(), 0
                with archive.open(info) as stream:
                    while chunk := stream.read(min(1024 * 1024, item["size"] - length + 1)):
                        length += len(chunk)
                        require(length <= item["size"], "Oversize project source member")
                        digest.update(chunk)
                require(
                    length == item["size"] and digest.hexdigest() == item["sha256"],
                    "Project source content mismatch",
                )
            require(local_end == offset, "Project source ZIP trailing local data")
        raw.seek(0)
        return hashlib.file_digest(raw, "sha256").hexdigest()


def check(args):
    repo, inputs = A.checked_path(args.source_repo), A.checked_path(args.inputs_root)
    work_parent = A.checked_path(args.work_parent)
    version = A.validation_identity(args)
    require(args.platform in {"linux-x64", "windows-x64"}, "Unsupported platform")
    require(
        {p.name for p in inputs.iterdir()} == {"runtime", "materials", "metadata"},
        "Input root fields",
    )
    for name in ("runtime", "materials", "metadata"):
        A.checked_path(inputs / name)
    metadata = inputs / "metadata"
    require({p.name for p in metadata.iterdir()} == A.METADATA, "Input metadata fields")
    values = {name: A.read_metadata(metadata / name) for name in A.METADATA}
    review_bytes = A.read_metadata(Path(args.review))
    for data, expected in (
        (values["runtime-lock.json"], args.runtime_lock_sha256),
        (values["materials-map.json"], args.materials_map_sha256),
        (review_bytes, args.review_sha256),
    ):
        require(
            type(expected) is str
            and re.fullmatch(r"[0-9a-f]{64}", expected)
            and A.digest(data) == expected,
            "Pinned input hash mismatch",
        )
    with tempfile.TemporaryDirectory(prefix="materials-review-", dir=work_parent) as directory:
        source = Path(directory)
        source_files = A.export_source(repo, args.source_commit, source)
        A.version_check(source, version)
        builder = A.load_builder(source)
        runtime_files = A.strict_json(values["runtime-inventory.json"])
        material_files = A.strict_json(values["materials-inventory.json"])
        A.verify_tree(inputs / "runtime", runtime_files, builder)
        A.verify_tree(inputs / "materials", material_files, builder)
        limits = builder.MaterialsLimits()
        materials_map = builder._parse_map(
            values["materials-map.json"],
            source_commit=args.source_commit,
            platform=args.platform,
            runtime_lock=values["runtime-lock.json"],
            source=builder.C.validate_file_inventory(source_files, limits=limits),
            runtime=builder.C.validate_file_inventory(runtime_files, limits=limits),
            materials=builder.C.validate_file_inventory(material_files, limits=limits),
            limits=limits,
        )
        review = A.strict_json(review_bytes)
        result = evaluate(review, materials_map, args.materials_map_sha256)
        project_path = inputs / "materials" / review["project_source_path"]
        result["project_source_archive_sha256"] = verify_project_source(project_path, source_files)
        project_record = next(
            i for i in material_files if i["path"] == review["project_source_path"]
        )
        require(
            result["project_source_archive_sha256"] == project_record["sha256"],
            "Project source archive changed during check",
        )
        result["project_source_file_count"] = len(source_files)
    require(A.read_metadata(Path(args.review)) == review_bytes, "Review changed during check")
    for name, data in values.items():
        require(A.read_metadata(metadata / name) == data, "Metadata changed during check")
    A.validation_identity(args)
    result.update(
        review_sha256=A.digest(review_bytes),
        runtime_lock_sha256=args.runtime_lock_sha256,
        source_inventory_sha256=materials_map["source_inventory_sha256"],
        runtime_inventory_sha256=materials_map["runtime_inventory_sha256"],
        materials_inventory_sha256=materials_map["materials_inventory_sha256"],
    )
    if getattr(args, "candidate_only", False):
        result["candidate_validation_only"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "source-repo",
        "source-commit",
        "tag",
        "inputs-root",
        "platform",
        "review",
        "runtime-lock-sha256",
        "materials-map-sha256",
        "review-sha256",
        "work-parent",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument(
        "--main-ref",
        default="refs/remotes/origin/main",
        choices=("refs/heads/main", "refs/remotes/origin/main"),
    )
    parser.add_argument("--candidate-only", action="store_true")
    try:
        result = check(parser.parse_args())
        print(A.canonical(result).decode(), end="")
        return 2 if result["status"] == "MATERIALS_REVIEW_BLOCKED" else 0
    except Exception as error:
        print(
            f"Materials review failed ({type(error).__name__}); no admission claimed.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
