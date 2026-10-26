"""Exact native placement, independent sidecar receipts, samples and source updates."""

import copy
import importlib.util
import math
from pathlib import Path

import pytest

from mechanical_cad.assembly_service import preflight_source_update, run_assembly_action
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "gear_model_fixture", ROOT / "tests/unit/test_assembly_gears.py"
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
bridge = fixture.importlib.import_module(fixture.PACKAGE + ".assembly_bridge")
pytestmark = pytest.mark.kernel


def request(model, **kwargs):
    return {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "assembly": model.to_dict(),
        "result_version": 3,
        "action": "assembly_replay",
        **kwargs,
    }


def test_exact_placement_replay_and_bound_native_free_receipt():
    model = fixture.mechanism()
    req = request(model)
    response = process_request(req)
    assert response["ok"], response["error"]
    bridge.validate_response(req, response)
    part = response["result"]["parts"][0]
    assert part["geometry_check"]["brep"]["valid"] and part["geometry_check"]["brep"]["solids"] == 1
    assert part["geometry_check"]["brep"]["volume"] > 0
    pose = response["report"]["base_pose"]
    assert pose["effective_coordinates"]["follower"] == 0.75
    assert pose["transforms"]["b"]["xyz_mm"] == [100.0, 0.0, 0.0]
    assert pose["transforms"]["b"]["wxyz"] == pytest.approx(
        [math.cos(0.375), 0, 0, math.sin(0.375)]
    )
    forged = copy.deepcopy(response)
    forged["report"]["base_pose"]["effective_coordinates"]["follower"] = 0.5
    forged["report_fingerprint"] = bridge.fingerprint(
        {
            "request": forged["request"],
            "report": forged["report"],
            "error": forged["error"],
            "source_replays": forged["result"]["source_replays"],
        }
    )
    with pytest.raises(fixture.edit.BridgeError, match="effective coordinates"):
        bridge.validate_response(req, forged)


def test_exact_samples_rederive_chained_gears_and_block_derived_limit_without_clamping():
    model = fixture.mechanism()
    req = request(
        model,
        action="assembly_sample",
        coordinates={"driver": 0.25},
        samples={"joint_id": "driver", "values": [0, 0.5, 2]},
    )
    response = process_request(req)
    bridge.validate_response(req, response)
    poses = response["report"]["poses"]
    assert len(poses) == 3
    assert [row["pose"]["effective_coordinates"] for row in poses[:2]] == [
        {"driver": 0.0, "follower": 1.25, "tail": 0.375},
        {"driver": 0.5, "follower": 0.25, "tail": -0.125},
    ]
    assert poses[2]["pose"]["status"] == "blocked"
    assert poses[2]["pose"]["effective_coordinates"] == {}
    assert poses[2]["pose"]["transforms"] == {}
    assert poses[2]["pose"]["diagnostics"][0]["code"] == "limit_violation"
    assert not response["report"]["complete"] and not response["report"]["passed"]
    assert model.joints[0].coordinate == 0.25


def test_update_source_and_pose_check_preserve_relation_and_exact_derived_angle():
    model = fixture.mechanism()
    source = model.part_sources[0].document
    parameter = next(iter(source.parameters))
    changed = source.with_parameter(parameter, 42)
    response = preflight_source_update(model, source.id, changed, result_version=3)
    assert response["ok"], response["error"]
    updated = fixture.AssemblyDocument.from_dict(response["update"]["candidate"])
    assert updated.gear_relations == model.gear_relations
    checked = run_assembly_action(updated, "assembly_check", result_version=3)
    assert checked["report"]["base_pose"]["effective_coordinates"] == {
        "driver": 0.25,
        "follower": 0.75,
        "tail": 0.125,
    }
    assert checked["report"]["poses"]


def test_geared_assembly_preserves_up_to_face_source_evidence_and_refresh():
    from dataclasses import replace

    from mechanical_cad.assembly_model import PartSource

    face_spec = importlib.util.spec_from_file_location(
        "gear_up_to_face_fixture", ROOT / "tests/integration/test_extrusion_up_to_face.py"
    )
    face_fixture = importlib.util.module_from_spec(face_spec)
    face_spec.loader.exec_module(face_fixture)
    source = face_fixture.document(target_z=10)
    original = fixture.mechanism()
    model = replace(
        original,
        part_sources=(PartSource.from_document(source),),
        parts=(
            replace(
                original.parts[0],
                source_document_id=source.id,
                source_digest=source.content_hash,
                output_feature_id=source.active_feature,
            ),
        ),
    )
    req = request(model)
    response = process_request(req)
    assert response["ok"], response.get("error")
    bridge.validate_response(req, response)
    assert response["result"]["parts"][0]["geometry_check"]["brep"]["volume"] == pytest.approx(
        10 * math.pi
    )
    assert response["report"]["base_pose"]["effective_coordinates"] == {
        "driver": 0.25,
        "follower": 0.75,
        "tail": 0.125,
    }
    legacy = process_request(request(model, result_version=2))
    assert not legacy["ok"] and legacy["error"]["code"] == "unsupported_result_version"
    update = preflight_source_update(
        model, source.id, source.with_parameter("stop_z", 20), result_version=3
    )
    assert update["ok"], update.get("error")
    refreshed = fixture.AssemblyDocument.from_dict(update["update"]["candidate"])
    assert refreshed.gear_relations == model.gear_relations
    next_request = request(refreshed)
    next_response = process_request(next_request)
    bridge.validate_response(next_request, next_response)
    assert next_response["result"]["parts"][0]["geometry_check"]["brep"]["volume"] == pytest.approx(
        20 * math.pi
    )
    assert (
        next_response["report"]["base_pose"]["effective_coordinates"]
        == response["report"]["base_pose"]["effective_coordinates"]
    )


@pytest.mark.parametrize("failure", ["source", "mesh"])
def test_literal_geared_source_failure_retains_specific_diagnostic_and_no_authority(
    failure, monkeypatch
):
    model = fixture.mechanism()
    source = model.part_sources[0].document
    raw = source.to_dict()
    # Fail an authored extrusion dimension, without changing the literal frames.
    if failure == "source":
        raw["parameters"]["extrude_1_length"] = 0
    else:
        from mechanical_cad.kernel_ocp import KernelError, OCPKernel

        def reject_mesh(self, shape, linear_deflection=0.1):
            raise KernelError("Mesh is not watertight with consistently oriented manifold edges")

        monkeypatch.setattr(OCPKernel, "manufacturing_check", reject_mesh)
    changed = fixture.Document.from_dict(raw)
    from mechanical_cad.assembly_model import replace_source

    failed_model = replace_source(model, source.id, changed)
    req = request(failed_model)
    response = process_request(req)
    assert response["ok"] is False
    assert response["error"]["code"] == (
        "source_replay_failed" if failure == "source" else "assembly_kernel_error"
    )
    if failure == "mesh":
        assert "Mesh is not watertight" in response["error"]["message"]
    assert response["result"]["parts"] == []
    assert response["report"]["poses"] == []
    assert response["report"]["complete"] is False
    assert response["report"]["passed"] is False
    bridge.validate_response(req, response)
    # Even this diagnostic-only packet must retain exact canonical kinematics.
    forged = copy.deepcopy(response)
    forged["report"]["base_pose"]["transforms"]["b"]["xyz_mm"][0] += 1
    forged["report_fingerprint"] = bridge.fingerprint(
        {
            "request": forged["request"],
            "report": forged["report"],
            "error": forged["error"],
            "source_replays": forged["result"]["source_replays"],
        }
    )
    with pytest.raises(fixture.edit.BridgeError, match="pose transforms contradict"):
        bridge.validate_response(req, forged)


def test_face_attached_geared_pose_still_requires_native_part_evidence():
    from dataclasses import replace

    model = fixture.mechanism()
    part = model.parts[0]
    model = replace(
        model,
        parts=(
            replace(
                part,
                mate_frames=(
                    replace(part.mate_frames[0], support_face="extrude_1/face/cap.end"),
                    *part.mate_frames[1:],
                ),
            ),
        ),
    )
    evidence = fixture.importlib.import_module(fixture.PACKAGE + ".assembly_frame_evidence")
    with pytest.raises(ValueError, match="lacks resolved part evidence"):
        evidence.validate_associative_pose(
            {}, {"canonical_assembly": model.to_dict(), "parts": []}, {}, {}
        )
