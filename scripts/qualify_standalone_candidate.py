#!/usr/bin/env python3
"""Bounded isolated install/write/read harness; no download or publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MARKER = "MCAD_STANDALONE_RESULT="
MODES = ("install", "write", "read")
LIMITS = [
    "Only the three installed standalone smoke modes are checked.",
    "This is not a full test-suite, GUI-usability, or cross-platform qualification.",
    "No downloads, publication, installer replacement, or cleanup is performed.",
    "Timeout terminates the direct Blender child; separately spawned sidecars may require scoped manual cleanup.",
]


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field: " + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError("Non-finite JSON constant: " + value)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def file_identity(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def validate_result(log, receipt, expected):
    markers = [line[len(MARKER):] for line in log.splitlines() if line.startswith(MARKER)]
    if len(markers) != 1:
        raise ValueError("Expected exactly one standalone result marker")
    marker = strict_json(markers[0])
    recorded = strict_json(receipt.read_text(encoding="utf-8"))
    if type(recorded) is not dict or type(marker) is not dict:
        raise ValueError("Standalone result must be a JSON object")
    if recorded != marker:
        raise ValueError("Receipt and stdout marker disagree")
    for key, value in expected.items():
        if type(recorded.get(key)) is not type(value) or recorded.get(key) != value:
            raise ValueError("Standalone identity mismatch: " + key)
    if recorded.get("ok") is not True:
        raise ValueError("Standalone receipt does not report explicit success")
    return recorded


def child_environment(base, archive, commit, version, mode):
    env = os.environ.copy()
    for key in ("MCAD_ROOT", "MCAD_PYTHON", "PYTHONPATH", "BLENDER_USER_SCRIPTS"):
        env.pop(key, None)
    env.update({
        "MCAD_VERIFY_BASE": str(base), "MCAD_VERIFY_ARCHIVE": str(archive),
        "MCAD_VERIFY_COMMIT": commit, "MCAD_VERIFY_VERSION": version,
        "MCAD_VERIFY_MODE": mode, "MCAD_VERIFY_BLENDER_VERSION": "5.2.2",
        "BLENDER_USER_CONFIG": str(base / "profile/config"),
        "BLENDER_USER_EXTENSIONS": str(base / "profile/extensions"),
        "TMPDIR": str(base / "tmp"), "TMP": str(base / "tmp"), "TEMP": str(base / "tmp"),
        "PYTHONNOUSERSITE": "1",
    })
    return env


def qualify(*, blender, archive, source_commit, version, work_root, timeout=900, script=None):
    blender, archive, work_root = (Path(p).absolute() for p in (blender, archive, work_root))
    script = Path(script) if script is not None else Path(__file__).resolve().parents[1] / "tests/blender_standalone_release_smoke.py"
    script = script.absolute()
    fixture = script.parent / "fixtures/standalone_constrained_plate.mcad.json"
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("Source commit must be a full lowercase 40-character commit")
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("Version must be a plain three-component release version")
    if type(timeout) not in (int, float) or not 0 < timeout <= 86400:
        raise ValueError("Per-mode timeout must be finite and between 0 and 86400 seconds")
    for label, path in (("Blender", blender), ("Archive", archive), ("Native script", script), ("Native fixture", fixture)):
        if not path.is_file():
            raise ValueError(label + " must be an existing local file: " + str(path))
    # Never adopt or clear a previous profile, evidence root, or symlink.
    work_root.mkdir(parents=True, exist_ok=False)
    for child in ("profile/config", "profile/extensions", "tmp", "logs", "receipts", "artifacts"):
        (work_root / child).mkdir(parents=True, exist_ok=False)
    sha, size = file_identity(archive)
    script_sha, script_size = file_identity(script)
    fixture_sha, fixture_size = file_identity(fixture)
    summary = {"ok": False, "archive": str(archive), "archive_sha256": sha, "archive_bytes": size,
                   "source_commit": source_commit, "version": version, "blender": str(blender),
                   "required_blender_version": "5.2.2", "script": str(script), "script_sha256": script_sha, "script_bytes": script_size,
                   "fixture": str(fixture), "fixture_sha256": fixture_sha, "fixture_bytes": fixture_size,
                   "modes": [], "limits": LIMITS}
    try:
        for mode in MODES:
            expected = {"mode": mode, "archive_sha256": sha, "source_commit": source_commit, "version": version,
                        "blender": "5.2.2", "interactive_gui": False}
            command = [str(blender), "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script)]
            record = {"mode": mode, "command": command, "timeout_seconds": timeout,
                          "returncode": None, "log": str(work_root / "logs" / (mode + ".log")),
                          "receipt": str(work_root / "receipts" / (mode + ".json")), "ok": False}
            summary["modes"].append(record)
            options = {"cwd": str(work_root), "env": child_environment(work_root, archive, source_commit, version, mode),
                           "timeout": timeout, "stderr": subprocess.STDOUT}
            # subprocess implements this in the child, avoiding process-global
            # os.umask or unsafe preexec_fn; Windows has no POSIX mode mask.
            if os.name == "posix":
                options["umask"] = 0o022
            try:
                with Path(record["log"]).open("wb") as output:
                    result = subprocess.run(command, check=False, stdout=output, **options)
                record["returncode"] = result.returncode
                if result.returncode != 0:
                    raise ValueError("Native mode exited nonzero: " + str(result.returncode))
                record["result"] = validate_result(
                    Path(record["log"]).read_text(encoding="utf-8", errors="replace"),
                    Path(record["receipt"]), expected,
                )
                record["ok"] = True
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                record["error"] = str(exc)
                record["timed_out"] = isinstance(exc, subprocess.TimeoutExpired)
                raise
        final_sha, final_size = file_identity(archive)
        if (final_sha, final_size) != (sha, size):
            raise ValueError("Candidate archive changed during qualification")
        if file_identity(script) != (script_sha, script_size) or file_identity(fixture) != (fixture_sha, fixture_size):
            raise ValueError("Qualification script or fixture changed during qualification")
        summary["ok"] = True
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        summary["error"] = str(exc)
    finally:
        (work_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("blender", "archive", "source-commit", "version", "work-root"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--timeout", type=float, default=900, help="Per-process seconds (default900)")
    args = parser.parse_args(argv)
    try:
        result = qualify(**vars(args))
    except (OSError, ValueError) as exc:
        print("Standalone harness refused: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
