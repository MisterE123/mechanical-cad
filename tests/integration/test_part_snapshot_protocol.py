"""Canonical Part capture works in a real process without site/native packages."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mechanical_cad.model import Document
from mechanical_cad.part_snapshot import input_fingerprint
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples/regressions/viewport_schema2_capture.mcad.json"


def request():
    return {
        "protocol_version": 1,
        "action": "canonical_snapshot",
        "document": json.loads(FIXTURE.read_text()),
    }


def process(raw, cwd):
    # -S proves no installed packages are needed. The explicit import guard
    # also catches accidental lazy imports of geometry/solve actions themselves.
    script = """
import builtins, runpy
original = builtins.__import__
blocked = {"OCP", "slvs", "bpy", "cadquery", "engine", "actions", "kernel_ocp",
           "sketch_solver", "profile_region", "assembly_service"}
def isolated(name, *args, **kwargs):
    if any(piece in blocked for piece in name.split(".")):
        raise AssertionError("snapshot attempted a native/geometry import: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = isolated
runpy.run_module("mechanical_cad.sidecar", run_name="__main__")
"""
    result = subprocess.run(
        [sys.executable, "-S", "-B", "-c", script],
        input=raw,
        text=True,
        capture_output=True,
        timeout=10,
        cwd=cwd,
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        check=False,
    )
    return result, json.loads(result.stdout)


def test_real_process_snapshot_has_authoritative_bytes_no_native_imports_or_file_writes(tmp_path):
    candidate = request()
    result, response = process(json.dumps(candidate), tmp_path)
    assert result.returncode == 0, result.stderr
    assert response["ok"] is True and response["error"] is None
    assert response["action"] == "canonical_snapshot" and response["protocol_version"] == 1
    assert response["input_fingerprint"] == input_fingerprint(candidate)
    document = Document.from_dict(candidate["document"])
    assert response["result"]["canonical_json"] == document.to_json()
    assert response["result"]["content_hash"] == document.content_hash
    assert response["result"]["canonical_document"] == document.to_dict()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("change", ["action", "document", "constraint"])
def test_duplicate_wire_json_is_rejected_before_snapshot(change, tmp_path):
    raw = json.dumps(request())
    if change == "action":
        raw = raw.replace(
            '"action": "canonical_snapshot"', '"action": "replay", "action": "canonical_snapshot"'
        )
    elif change == "document":
        raw = raw.replace('"schema_version": 2', '"schema_version": 1, "schema_version": 2', 1)
    else:
        raw = raw.replace('"kind": "horizontal"', '"kind": "vertical", "kind": "horizontal"', 1)
    result, response = process(raw, tmp_path)
    assert result.returncode == 1 and response["ok"] is False
    assert response["result"] is None and response["error"]["code"] == "invalid_json"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "extra",
    [
        {"options": {}},
        {"options": {"linear_deflection": 0.1}},
        {"destination": "part.step"},
        {"command": "anything"},
    ],
)
def test_snapshot_has_no_geometry_options_or_write_destination(extra):
    from mechanical_cad.errors import CADException

    with pytest.raises(CADException):
        process_request({**request(), **extra})


def test_snapshot_validates_records_without_resolving_or_rewriting_feature_formulas(tmp_path):
    candidate = request()
    candidate["document"]["features"][1]["params"]["length"] = "unknown_feature_parameter + 2"
    result, response = process(json.dumps(candidate), tmp_path)
    assert result.returncode == 0, result.stderr
    assert response["result"]["canonical_document"]["features"][1]["params"]["length"] == (
        "unknown_feature_parameter + 2"
    )
    assert list(tmp_path.iterdir()) == []
