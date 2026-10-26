import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, load_document, save_document
from mechanical_cad.topology import resolve_reference

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.kernel


def run_sidecar(request):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    process = subprocess.run(
        [sys.executable, "-m", "mechanical_cad.sidecar"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=30,
        env=env,
    )
    return process, json.loads(process.stdout)


def test_drilled_plate_real_geometry_and_edit_replay(plate):
    replay = regenerate(plate, OCPKernel())
    assert replay.ok
    body = replay.result["features"][-1]
    assert body["stats"]["valid"]
    assert body["stats"]["solids"] == 1
    assert body["stats"]["volume"] == pytest.approx((40 * 30 - math.pi * 4**2) * 10)
    changed = regenerate(plate.with_parameter("width", 60), OCPKernel())
    assert changed.ok
    assert changed.result["features"][-1]["stats"]["volume"] == pytest.approx(
        (60 * 30 - math.pi * 4**2) * 10
    )
    assert changed.result["features"][2]["resolved_params"]["x"] == 30
    assert max(point[0] for point in changed.result["features"][-1]["mesh"]["vertices"]) == 60


def test_source_reorder_preserves_geometry(plate):
    original = regenerate(plate, OCPKernel())
    data = plate.to_dict()
    data["features"].reverse()
    changed = regenerate(Document.from_dict(data), OCPKernel())
    assert changed.ok
    original_stats = {item["id"]: item["stats"] for item in original.result["features"]}
    changed_stats = {item["id"]: item["stats"] for item in changed.result["features"]}
    assert changed_stats == original_stats


def test_profile_display_is_actual_tessellated_planar_face(plate):
    replay = regenerate(plate, OCPKernel())
    for index in (0, 2):
        item = replay.result["features"][index]
        assert item["mesh"]["triangles"] and item["stats"] is None
        assert all(point[2] == 0 for point in item["mesh"]["vertices"])


def test_parameter_chain_fixture_replays():
    document = load_document(ROOT / "examples" / "parameter_chain.mcad.json")
    replay = regenerate(document, OCPKernel())
    assert replay.ok
    assert replay.result["features"][0]["stats"]["volume"] == pytest.approx(math.pi * 6**2 * 18)


def test_save_reload_replay_preserves_precise_geometry(plate, tmp_path):
    path = tmp_path / "plate.mcad.json"
    save_document(plate, path)
    first = regenerate(plate, OCPKernel())
    second = regenerate(load_document(path), OCPKernel())
    assert first.result["document_hash"] == second.result["document_hash"]
    assert first.result["features"][-1]["stats"] == second.result["features"][-1]["stats"]
    assert (
        first.result["features"][-1]["mesh"]["vertices"]
        == second.result["features"][-1]["mesh"]["vertices"]
    )


def test_replay_old_document_restores_original_geometry(plate):
    old = regenerate(plate, OCPKernel())
    regenerate(plate.with_parameter("height", 20), OCPKernel())
    restored = regenerate(plate, OCPKernel())
    assert restored.result["features"][-1]["stats"] == old.result["features"][-1]["stats"]


def test_semantic_cap_survives_dimension_edit(plate):
    reference = {"feature_id": "pad", "role": "cap.end", "kind": "face"}
    for width in (40, 60):
        result = regenerate(plate.with_parameter("width", width), OCPKernel())
        pad = next(item for item in result.result["features"] if item["id"] == "pad")
        resolution = resolve_reference(reference, pad["topology"])
        assert resolution.status == "resolved"


def test_sidecar_is_valid_single_json_and_real_kernel(plate):
    process, response = run_sidecar(
        {"protocol_version": 1, "document": plate.to_dict(), "options": {"linear_deflection": 0.1}}
    )
    assert process.returncode == 0, process.stderr
    assert response["ok"] and response["result"]["status"] == "ok"
    assert response["result"]["features"][-1]["stats"]["volume"] > 11000


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"protocol_version": 2}, "unsupported_protocol"),
        ({"protocol_version": True}, "unsupported_protocol"),
        ({"protocol_version": 1, "options": {"command": "bad"}}, "invalid_request"),
        ({"protocol_version": 1, "document": {}}, "invalid_document"),
        ([], "invalid_request"),
    ],
)
def test_sidecar_failures_are_structured(payload, code):
    process, response = run_sidecar(payload)
    assert process.returncode == 1
    assert not response["ok"] and response["result"] is None
    assert response["error"]["code"] == code


def test_sidecar_reports_failure_and_no_stale_active_mesh(plate):
    process, response = run_sidecar(
        {"protocol_version": 1, "document": plate.with_parameter("hole_radius", -1).to_dict()}
    )
    assert process.returncode == 1
    assert not response["ok"]
    assert response["result"]["features"][-1]["status"] == "blocked"
    assert response["result"]["features"][-1]["mesh"] is None


def test_identical_document_replays_to_identical_portable_result(plate):
    assert regenerate(plate, OCPKernel()).result == regenerate(plate, OCPKernel()).result
