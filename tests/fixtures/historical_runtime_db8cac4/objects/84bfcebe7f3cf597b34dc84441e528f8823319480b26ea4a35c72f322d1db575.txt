"""Portable integrity of real recovered-baseline geometry wire observations.

These pure checks establish the stored original bytes and untouched legacy helper
spans. Fresh current-sidecar byte comparisons are a separate native service gate.
No missing historical run is recreated or claimed by this corpus.
"""

import ast
import hashlib
import json
from pathlib import Path

import pytest
from test_arc_profile_native_end_cap import geometry_revision_originals

from mechanical_cad.part_snapshot import input_fingerprint

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/geometry_v3/legacy_recovered_69d0f81"
MANIFEST_SHA256 = "dcbca6f38afd8ab092ff25958320b3985aa520f659dcba6291666ec2e9508b6a"
CASES = (
    ("01_v1_check_geometry", 1, "check_geometry"),
    ("02_v1_export_step", 1, "export_step"),
    ("03_v1_export_stl", 1, "export_stl"),
    ("04_v2_check_geometry", 2, "check_geometry"),
    ("05_v2_export_step", 2, "export_step"),
    ("06_v2_export_stl", 2, "export_stl"),
)


def manifest():
    raw = (FIXTURE / "MANIFEST.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256
    value = json.loads(raw)
    assert value["schema"] == "recovered-legacy-geometry-wire-v1"
    assert value["source_commit"] == "69d0f8164e73bfbbcdf0c48d6546f97803d12f58"
    assert value["source_zip_sha256"] == (
        "7030e8c4202af11f349d68577157ce2cc878b25539991d8891b3045725e280a9"
    )
    assert [row["id"] for row in value["rows"]] == [row[0] for row in CASES]
    return value


@pytest.mark.parametrize("case,version,action", CASES)
def test_real_legacy_raw_request_and_stdout_are_exact(case, version, action):
    row = next(item for item in manifest()["rows"] if item["id"] == case)
    raw = {}
    for kind in ("request", "response"):
        name = f"{case}.{kind}.raw"
        raw[kind] = (FIXTURE / name).read_bytes()
        assert row[kind]["file"] == name
        assert len(raw[kind]) == row[kind]["bytes"]
        assert hashlib.sha256(raw[kind]).hexdigest() == row[kind]["sha256"]
    request, response = (json.loads(raw[kind]) for kind in ("request", "response"))
    assert request["action"] == action and request["result_version"] == version
    assert response["ok"] is True and response["error"] is None
    assert response["action"] == action and response["result"]["status"] == "ok"
    assert response["result"]["active_feature"] == "pad"
    assert response["geometry_check"]["brep"]["solids"] == 1
    assert response["geometry_check"]["brep"]["volume"] == pytest.approx(100)
    assert (
        raw["response"]
        == (json.dumps(response, allow_nan=False, separators=(",", ":")) + "\n").encode()
    )
    assert ("result_version" in response) == (version == 2)
    if version == 2:
        assert response["result_version"] == 2
        assert response["input_fingerprint"] == input_fingerprint(request)
    else:
        assert "input_fingerprint" not in response
    assert "backend_receipt" not in response
    if action == "check_geometry":
        assert response["export"] is None and "destination" not in request
    else:
        assert "/./" in request["destination"] and " " in request["destination"]
        assert response["export"]["destination"] == str(Path(request["destination"]))
        assert response["export"]["atomic_replace"] is True
        assert response["export"]["bytes"] == row["export_file"]["bytes"]


def _function_bytes(raw, name):
    matches = [
        item
        for item in ast.parse(raw).body
        if isinstance(item, ast.FunctionDef) and item.name == name
    ]
    assert len(matches) == 1 and not matches[0].decorator_list
    node = matches[0]
    return b"".join(raw.splitlines(keepends=True)[node.lineno - 1 : node.end_lineno])


@pytest.mark.parametrize("name", ("_destination", "_atomic_export"))
def test_legacy_destination_and_atomic_writer_function_bytes_stay_exact(name):
    relative = "src/mechanical_cad/actions.py"
    _, originals = geometry_revision_originals(ROOT)
    original = _function_bytes(originals[relative], name)
    current = _function_bytes((ROOT / relative).read_bytes(), name)
    assert current == original
    assert hashlib.sha256(original).hexdigest() == manifest()["helper_sha256"][name]


def test_corpus_is_only_fresh_baseline_capture_not_lost_070_reconstruction():
    value = manifest()
    assert value["qualification_scope"] == "fresh recovered immutable 0.6 baseline only"
    assert value["lost_070_receipts_reused"] is False
    assert value["collected_native_processes"] == 6
    assert all(row["exit_code"] == 0 and row["collected"] is True for row in value["rows"])
