"""Capture legacy bytes only from an independently verified ce5b50b source tree.

This is an optional developer provenance tool, not a pytest dependency. It never
executes the add-on entry point, runs native work, edits the baseline, or accepts
the current worktree as its expected-output authority. Invoke with the pinned
interpreter, -B, PYTHONDONTWRITEBYTECODE=1 and PYTHONPATH=<baseline>/src.
"""

import argparse
import hashlib
import io
import json
import os
import runpy
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

COMMIT = "ce5b50bb011b3949a6599c7cbc28d31024805e0a"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    source, repo = args.source.resolve(), args.repo.resolve()
    assert source != repo and not (source / ".git").exists()
    assert sys.dont_write_bytecode and os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"
    assert os.environ.get("PYTHONPATH") == str(source / "src")
    assert not args.output.exists(), "Refusing to overwrite a frozen expected-byte fixture."
    assert not args.receipt.exists(), "Use a unique durable receipt path."
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["commit"] == COMMIT
    listed = manifest["files"]
    actual_paths = {
        path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()
    }
    assert actual_paths == set(listed), "Archive file inventory differs from its source manifest."
    archive_bytes = subprocess.check_output(
        ["git", "-C", str(repo), "archive", "--format=tar", COMMIT]
    )
    with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as archive:
        git_files = {
            item.name: archive.extractfile(item).read()
            for item in archive.getmembers()
            if item.isfile()
        }
    assert set(git_files) == set(listed), (
        "Git commit file inventory differs from the source manifest."
    )
    verified = {}
    # Complete this entire check before importing ANY baseline implementation.
    for relative in sorted(listed):
        content = (source / relative).read_bytes()
        assert content == git_files[relative], ("Git mismatch", relative)
        assert len(content) == listed[relative]["bytes"], ("Manifest size mismatch", relative)
        assert sha256(content) == listed[relative]["sha256"], ("Manifest hash mismatch", relative)
        verified[relative] = {"bytes": len(content), "sha256": sha256(content)}

    recipe_path = repo / "tests/unit/test_arc_authoring_legacy_bytes.py"
    recipe = runpy.run_path(str(recipe_path), run_name="legacy_byte_capture_recipe")
    before = set(sys.modules)
    cases = recipe["collect_cases"](source)
    executed = {}
    for name in sorted(set(sys.modules) - before):
        assert name.split(".")[0] not in {"bpy", "OCP", "OCC", "slvs", "mechanical_cad"}, name
        if not name.startswith("mcad_legacy_bytes_"):
            continue
        path = getattr(sys.modules[name], "__file__", None)
        if path is None:
            continue  # The synthetic package deliberately has no executed init.
        relative = Path(path).resolve().relative_to(source).as_posix()
        assert relative.endswith(".py") and relative in verified, relative
        assert relative != "blender_addon/mechanical_cad_blender/__init__.py"
        assert sha256((source / relative).read_bytes()) == verified[relative]["sha256"]
        executed[relative] = verified[relative]
    assert executed
    # The baseline is read-only by contract. Recheck every byte after capture.
    for relative, expected in verified.items():
        assert sha256((source / relative).read_bytes()) == expected["sha256"], relative
    assert actual_paths == {
        path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()
    }
    hashes = {
        name: {
            key: sha256(value.encode("utf-8"))
            for key, value in case.items()
            if isinstance(value, str)
        }
        for name, case in cases.items()
    }
    fixture = {
        "format_version": 1,
        "baseline_commit": COMMIT,
        "provenance": {
            "source_manifest_sha256": sha256(manifest_bytes),
            "source_archive_sha256": manifest["archive_sha256"],
            "all_source_files_verified_against_git_and_manifest": len(verified),
            "recipe_sha256": sha256(recipe_path.read_bytes()),
            "capture_script_sha256": sha256(Path(__file__).read_bytes()),
            "executed_baseline_modules": executed,
            "native_or_blender_execution": False,
            "solver_evidence_fabricated": False,
        },
        "cases": cases,
        "sha256": hashes,
    }
    result_bytes = (
        json.dumps(fixture, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result_bytes)
    receipt = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "baseline_commit": COMMIT,
        "baseline_source": str(source),
        "source_manifest": str(args.manifest.resolve()),
        "provenance": fixture["provenance"],
        "python": sys.version,
        "executable": sys.executable,
        "dont_write_bytecode": sys.dont_write_bytecode,
        "pythonpath": os.environ["PYTHONPATH"],
        "output": str(args.output.resolve()),
        "output_bytes": len(result_bytes),
        "output_sha256": sha256(result_bytes),
        "case_names": list(cases),
        "case_count": len(cases),
        "baseline_unchanged_after_capture": True,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in (
                    "case_count",
                    "output_bytes",
                    "output_sha256",
                    "baseline_unchanged_after_capture",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
