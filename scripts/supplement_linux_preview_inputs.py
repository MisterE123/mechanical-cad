"""Offline additive materials preparation; never approval or release admission."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import os
import re
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "_supplement_refresh", ROOT / "scripts/prepare_linux_preview_inputs.py"
)
P = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(P)
A, B = P.A, P.B
STATUS = P.STATUS
MAX_ADDITIONS = 64
MAX_BYTES = 512 * 1024**2
IMPLEMENTATION_FILES = tuple(
    sorted(
        set(P.IMPLEMENTATION_FILES)
        | {"scripts/supplement_linux_preview_inputs.py", "docs/LINUX_PREVIEW_INPUT_SUPPLEMENT.md"}
    )
)


def require(value, message):
    if not value:
        raise ValueError(message)


def pinned_json(path, digest):
    require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid SHA256 pin")
    raw = A.read_metadata(path)
    require(A.digest(raw) == digest, "Pinned metadata mismatch")
    return raw, A.strict_json(raw)


def inventory(root):
    names = B.BUILDER._tree_files(root, B.MaterialsLimits())
    return [P.file_record(root / name, name) for name in sorted(names)]


def verify_tree(root, records, builder):
    A.verify_tree(root, records, builder)
    for row in records:
        info = (root / row["path"]).lstat()
        require(
            stat.S_ISREG(info.st_mode)
            and stat.S_IMODE(info.st_mode) == row["mode"]
            and info.st_nlink == 1,
            "File mode or independent regular-file identity mismatch",
        )


def parse_additions(value):
    require(
        type(value) is dict
        and set(value) == {"schema_version", "files"}
        and type(value["schema_version"]) is int
        and value["schema_version"] == 1,
        "Invalid additions schema",
    )
    rows = value["files"]
    require(type(rows) is list and 0 < len(rows) <= MAX_ADDITIONS, "Addition count bound")
    records = []
    for row in rows:
        require(
            type(row) is dict and set(row) == {"path", "mode", "size", "sha256", "roles"},
            "Invalid addition fields",
        )
        roles = row["roles"]
        require(
            type(roles) is list
            and 0 < len(roles) <= 3
            and all(type(r) is str for r in roles)
            and len(set(roles)) == len(roles)
            and set(roles) <= {"source", "notice", "provenance"},
            "Invalid addition roles",
        )
        require(
            type(row["path"]) is str
            and all(
                row["path"].startswith("sources/" if r == "source" else "licenses/") for r in roles
            ),
            "Invalid role path",
        )
        require(type(row["mode"]) is int and row["mode"] == 0o644, "Additions must be data")
        records.append({k: v for k, v in row.items() if k != "roles"})
    B._material_inventory(records, B.MaterialsLimits())
    require(sum(r["size"] for r in records) <= MAX_BYTES, "Addition byte bound")
    return records


def validate_map(value, source, runtime, materials, lock):
    B._parse_map(
        A.canonical(value),
        source_commit=value["source_commit"],
        platform="linux-x64",
        runtime_lock=lock,
        source=B.C.validate_file_inventory(source, limits=B.MaterialsLimits()),
        runtime=B.C.validate_file_inventory(runtime, limits=B.MaterialsLimits()),
        materials=B.C.validate_file_inventory(materials, limits=B.MaterialsLimits()),
        limits=B.MaterialsLimits(),
    )


def copy_records(root, destination, records):
    for row in records:
        src, dest = root / row["path"], destination / row["path"]
        P.make_directory(dest.parent)
        P.reserve_space(dest.parent, row["size"] + 4096)
        require(P.file_record(src, row["path"]) == row, "Input changed before copy")
        digest, size = hashlib.sha256(), 0
        with B.BUILDER._open(src) as source, dest.open("xb") as target:
            while chunk := source.read(min(1024**2, row["size"] - size + 1)):
                size += len(chunk)
                require(size <= row["size"], "Input grew during copy")
                P.reserve_space(dest.parent, len(chunk) + 4096)
                digest.update(chunk)
                target.write(chunk)
        dest.chmod(row["mode"])
        require(
            size == row["size"] and digest.hexdigest() == row["sha256"], "Copy identity mismatch"
        )
        require(P.file_record(src, row["path"]) == row, "Input changed during copy")


def supplement(args):
    require(sys.platform == "linux" and os.name == "posix", "Linux preparation host required")
    base, additions = A.checked_path(args.base), A.checked_path(args.additions_root)
    manifest_path = A.checked_path(args.additions_manifest)
    output = Path(os.path.abspath(args.output))
    A.checked_path(output.parent)
    require(not os.path.lexists(output), "Fresh output required; no overwrite or retry")
    for root in (base, additions, ROOT):
        require(
            output != root and root not in output.parents and output not in root.parents,
            "Output must be separate from input and implementation trees",
        )
    receipt_raw, receipt = pinned_json(base / "preparation-receipt.json", args.base_receipt_sha256)
    require(
        {p.name for p in (base / "inputs").iterdir()} == {"runtime", "materials", "metadata"},
        "Unexpected input directory entries",
    )
    meta = base / "inputs/metadata"
    require(
        {p.name for p in meta.iterdir()}
        == {
            "runtime-lock.json",
            "runtime-inventory.json",
            "materials-inventory.json",
            "materials-map.json",
        },
        "Unexpected base metadata entries",
    )
    map_raw, old = pinned_json(meta / "materials-map.json", args.base_map_sha256)
    require(
        receipt["status"] == STATUS and receipt["materials_map_sha256"] == args.base_map_sha256,
        "Base receipt/map binding mismatch",
    )
    source = inventory(base / "source")
    runtime_raw = A.read_metadata(meta / "runtime-inventory.json")
    materials_raw = A.read_metadata(meta / "materials-inventory.json")
    runtime, materials = A.strict_json(runtime_raw), A.strict_json(materials_raw)
    lock = A.read_metadata(meta / "runtime-lock.json")
    for field, actual in (
        ("source_inventory_sha256", A.digest(A.canonical(source))),
        ("runtime_inventory_sha256", A.digest(runtime_raw)),
        ("materials_inventory_sha256", A.digest(materials_raw)),
        ("runtime_lock_sha256", A.digest(lock)),
    ):
        require(receipt[field] == actual == old[field], "Base identity mismatch: " + field)
    require(receipt["source_commit"] == old["source_commit"], "Base source mismatch")
    require(
        len(old["unresolved_issues"]) == 42
        and len([c for c in old["components"] if c["kind"] != "project_package"]) == 42,
        "Expected 42 historical components and issues",
    )
    for root, records in (
        (base / "source", source),
        (base / "inputs/runtime", runtime),
        (base / "inputs/materials", materials),
    ):
        verify_tree(root, records, B)
    validate_map(old, source, runtime, materials, lock)
    manifest_raw, manifest = pinned_json(manifest_path, args.additions_sha256)
    new_records = parse_additions(manifest)
    verify_tree(additions, new_records, B)
    # Complete combined inventory validation catches aliases, collisions and parents.
    B.C.validate_file_inventory(materials + new_records, limits=B.MaterialsLimits())
    implementation = [P.file_record(ROOT / n, n) for n in IMPLEMENTATION_FILES]
    implementation_sha = A.digest(A.canonical(implementation))
    prefix = "licenses/provenance/supplement-" + args.additions_sha256
    helper_zip = "sources/preparation/linux-input-supplement-" + implementation_sha + ".zip"
    generated = {
        helper_zip,
        prefix + ".json",
        prefix + "-manifest.json",
        prefix + "-base-receipt.json",
    }
    require(
        not generated.intersection(r["path"] for r in materials + new_records),
        "Generated material collision",
    )
    B.C.validate_file_inventory(
        materials
        + new_records
        + [{"path": n, "mode": 0o644, "size": 0, "sha256": "0" * 64} for n in generated],
        limits=B.MaterialsLimits(),
    )
    block = max(4096, os.statvfs(output.parent).f_frsize)
    budget = sum(
        P.allocation_bytes(output.parent, r["size"]) + block * (len(r["path"].split("/")) + 3)
        for r in source + runtime + materials + new_records + implementation
    )
    budget += 2 * P.zip_budget(implementation) + 32 * 1024**2
    P.reserve_space(output.parent, budget)
    output.mkdir(mode=0o700)
    # Failure leaves diagnostic partial bytes; never delete, retry or claim completion.
    for src, dest, records in (
        (base / "source", output / "source", source),
        (base / "inputs/runtime", output / "inputs/runtime", runtime),
        (base / "inputs/materials", output / "inputs/materials", materials),
        (additions, output / "inputs/materials", new_records),
        (ROOT, output / "supplement-source", implementation),
    ):
        copy_records(src, dest, records)
    mats = output / "inputs/materials"
    P.make_directory((mats / helper_zip).parent)
    helper_sha = P.export_zip(mats / helper_zip, output / "supplement-source", implementation)
    helper_record = P.file_record(mats / helper_zip, helper_zip)
    require(helper_record["sha256"] == helper_sha, "Helper ZIP changed after verification")
    generated_records = [helper_record]
    evidence = {
        "schema_version": 1,
        "status": STATUS,
        "source_commit": old["source_commit"],
        "base_receipt_sha256": A.digest(receipt_raw),
        "base_materials_map_sha256": A.digest(map_raw),
        "additions_manifest_sha256": A.digest(manifest_raw),
        "implementation_source_path": helper_zip,
        "implementation_source_sha256": helper_sha,
        "implementation_source_inventory_sha256": implementation_sha,
        "implementation_separate_from_target_source": True,
        "review": "NOT_PERFORMED",
        "native_qualification": "NOT_RUN",
        "release_admission": "NOT_ESTABLISHED",
        **P.preserved_identity(old),
    }
    for name, raw in (
        (prefix + ".json", A.canonical(evidence)),
        (prefix + "-manifest.json", manifest_raw),
        (prefix + "-base-receipt.json", receipt_raw),
    ):
        P.make_directory((mats / name).parent)
        P.write_new(mats / name, raw)
        generated_records.append(
            {"path": name, "mode": 0o644, "size": len(raw), "sha256": A.digest(raw)}
        )
    updated = copy.deepcopy(old)
    project = next(c for c in updated["components"] if c["kind"] == "project_package")
    for role in ("source", "notice", "provenance"):
        extra = [r["path"] for r in manifest["files"] if role in r["roles"]]
        if role == "source":
            extra.append(helper_zip)
        if role == "provenance":
            extra.extend(generated - {helper_zip})
        project[role + "_paths"] = sorted(project[role + "_paths"] + extra)
    result_materials = sorted(materials + new_records + generated_records, key=lambda r: r["path"])
    verify_tree(mats, result_materials, B)
    updated["materials_inventory_sha256"] = A.digest(A.canonical(result_materials))
    require(
        P.preserved_identity(updated) == P.preserved_identity(old), "Historical binding changed"
    )
    validate_map(updated, source, runtime, result_materials, lock)
    out_meta = output / "inputs/metadata"
    P.make_directory(out_meta)
    for name, raw in (
        ("runtime-lock.json", lock),
        ("runtime-inventory.json", runtime_raw),
        ("materials-inventory.json", A.canonical(result_materials)),
        ("materials-map.json", A.canonical(updated)),
    ):
        P.write_new(out_meta / name, raw)
    for original, destination, records in (
        (base / "source", output / "source", source),
        (base / "inputs/runtime", output / "inputs/runtime", runtime),
        (base / "inputs/materials", None, materials),
        (additions, None, new_records),
    ):
        verify_tree(original, records, B)
        if destination is not None:
            verify_tree(destination, records, B)
    verify_tree(mats, result_materials, B)
    require(
        pinned_json(base / "preparation-receipt.json", args.base_receipt_sha256)[0] == receipt_raw
        and pinned_json(meta / "materials-map.json", args.base_map_sha256)[0] == map_raw
        and pinned_json(manifest_path, args.additions_sha256)[0] == manifest_raw,
        "Pinned metadata changed during preparation",
    )
    for name, expected in (
        ("runtime-lock.json", lock),
        ("runtime-inventory.json", runtime_raw),
        ("materials-inventory.json", materials_raw),
    ):
        require(A.read_metadata(meta / name) == expected, "Base metadata changed: " + name)
    result = dict(
        evidence,
        materials_map_sha256=A.digest(A.canonical(updated)),
        materials_inventory_sha256=updated["materials_inventory_sha256"],
        source_inventory_sha256=old["source_inventory_sha256"],
        runtime_inventory_sha256=old["runtime_inventory_sha256"],
        runtime_lock_sha256=old["runtime_lock_sha256"],
        materials_files=len(result_materials),
        runtime_files=len(runtime),
        issues_retained=42,
        nonproject_components_retained=42,
    )
    P.write_new(output / "preparation-receipt.json", A.canonical(result))
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in (
        "base",
        "base-receipt-sha256",
        "base-map-sha256",
        "additions-root",
        "additions-manifest",
        "additions-sha256",
        "output",
    ):
        result.add_argument("--" + name, required=True)
    return result


if __name__ == "__main__":
    print(A.canonical(supplement(parser().parse_args())).decode(), end="")
