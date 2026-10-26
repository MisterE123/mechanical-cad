"""Real opted-in Part transport plus malformed/stale typed evidence rejection."""

import copy
import importlib
import subprocess
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("OCP")
pytest.importorskip("slvs")

from mechanical_cad.model import load_document
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_part_result_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
validator = importlib.import_module(PACKAGE + ".part_result_bridge")
bridge = importlib.import_module(PACKAGE + ".bridge")


def request(name="circle_sketch_part", **changes):
    doc = load_document(ROOT / "examples" / (name + ".mcad.json"))
    return {
        "protocol_version": 1,
        "result_version": 2,
        "document": doc.to_dict(),
        "options": {"linear_deflection": 0.1},
        **changes,
    }


@pytest.mark.parametrize(
    "name", ["circle_sketch_part", "open_line_sketch", "drilled_plate", "constrained_plate"]
)
def test_real_v2_result_roundtrip_preserves_all_evidence_and_owns_copy(name):
    req = request(name)
    response = process_request(req)
    validated = validator.validate_response(req, response)
    assert response == validated and validated is not response
    validated["result"]["features"].clear()
    assert response["result"]["features"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.pop("result_version"),
        lambda r: r.update(result_version=True),
        lambda r: r.pop("input_fingerprint"),
        lambda r: r.update(input_fingerprint="0" * 64),
        lambda r: r["result"].update(document_hash="0" * 64),
        lambda r: r["result"].update(active_feature="profile"),
        lambda r: r["result"].update(result_version=1),
        lambda r: r["result"]["features"].reverse(),
        lambda r: r["result"]["features"].pop(),
        lambda r: r["result"]["features"][0].update(label="changed"),
        lambda r: r["result"]["features"][-1]["inputs"].update(profile="other"),
        lambda r: r["result"]["features"][-1].update(output={"kind": "profile", "display": "mesh"}),
        lambda r: r["result"]["parameters"].update(diameter=40),
        lambda r: r["result"].update(status="failed"),
        lambda r: r.update(ok=False),
        lambda r: r["result"]["features"][0].update(unexpected="field"),
    ],
)
def test_tampered_current_output_is_rejected(mutation):
    req = request()
    response = process_request(req)
    mutation(response)
    with pytest.raises((ValueError, bridge.BridgeError)):
        validator.validate_response(req, response)


def test_changed_tolerance_action_or_destination_cannot_reuse_same_document_result():
    req = request()
    response = process_request(req)
    changed = copy.deepcopy(req)
    changed["options"]["linear_deflection"] = 0.2
    with pytest.raises(ValueError, match="complete Part request"):
        validator.validate_response(changed, response)
    changed = {**req, "action": "check_geometry"}
    with pytest.raises(ValueError):
        validator.validate_response(changed, response)


def test_blocked_and_failed_typed_results_keep_only_valid_current_outputs():
    req = request("open_line_sketch")
    req["document"]["features"].append(
        {"id": "pad", "kind": "extrude", "params": {"length": 5}, "inputs": {"profile": "profile"}}
    )
    req["document"]["active_feature"] = "pad"
    response = validator.validate_response(req, process_request(req))
    assert not response["ok"]
    assert response["result"]["features"][-1]["error"]["code"] == "profile_unavailable"
    assert response["result"]["features"][-1]["output"] is None


@pytest.mark.parametrize("name", ["circle_sketch_part", "open_line_sketch"])
def test_real_sidecar_client_uses_explicit_new_path(name):
    req = request(name)
    result = bridge.replay(
        req["document"], result_version=2, project_root=str(ROOT), python_executable=sys.executable
    )
    assert result["status"] == "ok" and result["result_version"] == 2


@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_real_geometry_client_preserves_negotiated_output_and_export_metadata(tmp_path, action):
    req = request()
    destination = None if action == "check_geometry" else str(tmp_path / "part.file")
    response = bridge.geometry_action(
        req["document"],
        action,
        result_version=2,
        destination=destination,
        project_root=str(ROOT),
        python_executable=sys.executable,
    )
    assert response["ok"] and response["result_version"] == 2
    assert response["result"]["features"][-1]["output"]["kind"] == "solid"


def test_real_geometry_client_accepts_explicit_open_not_solid_failure(tmp_path):
    req = request("open_line_sketch")
    path = tmp_path / "keep.step"
    path.write_text("keep")
    response = bridge.geometry_action(
        req["document"],
        "export_step",
        result_version=2,
        destination=str(path),
        project_root=str(ROOT),
        python_executable=sys.executable,
    )
    assert not response["ok"] and response["error"]["code"] == "not_a_solid"
    assert path.read_text() == "keep"


def test_missing_version_never_triggers_legacy_retry(monkeypatch):
    req = request()
    response = process_request(req)
    response.pop("result_version")
    calls = []

    def exchange(request, **kwargs):
        calls.append(request)
        return response

    monkeypatch.setattr(bridge, "_exchange_raw", exchange)
    with pytest.raises(bridge.BridgeError, match="matching add-on and backend"):
        bridge.replay(req["document"], result_version=2)
    assert len(calls) == 1 and calls[0]["result_version"] == 2


def test_native_free_validator_import_under_python_no_site():
    script = f"""
import sys,types,importlib
p=types.ModuleType('isolated');p.__path__=[{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules['isolated']=p
importlib.import_module('isolated.part_result_bridge')
assert not any(n == 'bpy' or n == 'OCP' or n == 'slvs' or n.startswith('mechanical_cad.') for n in sys.modules)
print('NATIVE_FREE')
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", script], text=True, capture_output=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "NATIVE_FREE"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda face: face.update(feature_id="unrelated"),
        lambda face: face.update(role="other_side"),
        lambda face: face["provenance"].update(source_id="absent/face/source"),
        lambda face: face["provenance"].update(operation_id="other_cut"),
        lambda face: face["provenance"].update(modifying_feature_id="other_cut"),
        lambda face: face["provenance"].update(semantic_status="generated"),
        lambda face: face["provenance"].update(image_count=0),
    ],
)
def test_cut_provenance_retains_only_the_actual_base_face_identity(mutation):
    req = request("drilled_plate")
    response = process_request(req)
    cut = response["result"]["features"][-1]
    inherited = next(face for face in cut["topology"] if face["feature_id"] != cut["id"])
    mutation(inherited)
    with pytest.raises(ValueError):
        validator.validate_response(req, response)


def test_split_cut_lineage_stays_ambiguous_across_a_second_cut_and_list_reorder():
    req = request("drilled_plate")
    features = req["document"]["features"]
    profile = next(item for item in features if item["id"] == "hole_profile")
    profile.update(
        kind="sketch_rectangle",
        params={"width": 2, "height": 32, "x": 19, "y": -1, "z": 5},
    )
    features.extend(
        [
            {
                "id": "bore_profile",
                "kind": "sketch_circle",
                "params": {"radius": 2, "x": 5, "y": 5},
            },
            {
                "id": "bore_tool",
                "kind": "extrude",
                "params": {"length": 10},
                "inputs": {"profile": "bore_profile"},
            },
            {"id": "bore", "kind": "cut", "inputs": {"base": "body", "tool": "bore_tool"}},
        ]
    )
    req["document"]["active_feature"] = "bore"
    features.reverse()  # Canonical list order is not execution/topological order.
    response = process_request(req)
    assert response["ok"]
    validator.validate_response(req, response)
    cut = next(item for item in response["result"]["features"] if item["id"] == "bore")
    split = next(
        face for face in cut["topology"] if face["provenance"]["semantic_status"] == "split"
    )
    assert split["feature_id"] == "pad"
    split["provenance"]["semantic_status"] = "stable"
    split["provenance"].pop("id_scope")
    old_id = split["id"]
    split["id"] = f"{split['feature_id']}/face/{split['role']}"
    cut["mesh"]["triangle_face_ids"] = [
        split["id"] if identifier == old_id else identifier
        for identifier in cut["mesh"]["triangle_face_ids"]
    ]
    with pytest.raises(ValueError, match="promoted"):
        validator.validate_response(req, response)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(geometry_check=None),
        lambda r: r["geometry_check"].update(future_schema=True),
        lambda r: r["geometry_check"]["brep"].update(area=-100),
        lambda r: r["geometry_check"]["brep"].update(faces=True),
        lambda r: r["geometry_check"]["mesh"].update(triangles="not a count"),
        lambda r: r["geometry_check"]["mesh"].update(vertices=1),
        lambda r: r["geometry_check"]["mesh"].update(weld_tolerance=0.001),
        lambda r: r["geometry_check"]["mesh"].update(signed_volume=-1),
        lambda r: r["geometry_check"]["mesh"].update(unknown=True),
        lambda r: r["result"]["features"][-1]["topology"][0].update(signature="not a signature"),
        lambda r: r["result"]["features"][-1]["topology"][0]["signature"].update(area=-1),
        lambda r: r["result"]["features"][-1]["topology"][0]["signature"].update(unknown=True),
    ],
)
def test_strict_geometry_check_and_signature_schema_rejects_nested_corruption(
    mutation, monkeypatch
):
    req = request(action="check_geometry")
    response = process_request(req)
    assert response["ok"]
    mutation(response)
    with pytest.raises(ValueError):
        validator.validate_response(req, response)
    monkeypatch.setattr(bridge, "_exchange_raw", lambda *args, **kwargs: response)
    with pytest.raises(bridge.BridgeError):
        bridge.geometry_action(req["document"], "check_geometry", result_version=2)


@pytest.mark.parametrize("action", ["export_step", "export_stl"])
@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(export=None),
        lambda r: r["export"].update(extra=True),
        lambda r: r["export"].update(bytes=True),
        lambda r: r["export"].update(document_hash="0" * 64),
        lambda r: r["export"].update(destination="another.file"),
    ],
)
def test_actual_export_receipt_is_required_and_bound(tmp_path, action, mutation):
    req = request(action=action, destination=str(tmp_path / "part.file"))
    response = process_request(req)
    assert response["ok"]
    validator.validate_response(req, response)
    mutation(response)
    with pytest.raises(ValueError):
        validator.validate_response(req, response)


def test_successful_extrusion_cannot_consume_unavailable_or_failed_profile():
    solid_req = request()
    solid_response = process_request(solid_req)
    solid_feature = copy.deepcopy(solid_response["result"]["features"][-1])
    solid_source = copy.deepcopy(solid_req["document"]["features"][-1])
    solid_source["params"] = copy.deepcopy(solid_feature["resolved_params"])
    solid_source["inputs"] = solid_feature["inputs"] = {"profile": "profile"}
    open_req = request("open_line_sketch")
    open_req["document"]["features"].append(solid_source)
    open_req["document"]["active_feature"] = solid_source["id"]
    response = process_request(open_req)
    assert not response["ok"]
    response["result"]["features"][-1] = solid_feature
    response["result"]["status"] = "ok"
    response["ok"] = True
    with pytest.raises(ValueError, match="available profile"):
        validator.validate_response(open_req, response)
    failed = copy.deepcopy(solid_response)
    profile = failed["result"]["features"][0]
    profile.update(
        status="failed",
        error={"code": "kernel_error", "message": "failed"},
        mesh=None,
        stats=None,
        topology=[],
        output=None,
    )
    profile.pop("sketch")
    failed["ok"] = False
    failed["result"]["status"] = "failed"
    with pytest.raises(ValueError, match="failed or blocked input"):
        validator.validate_response(solid_req, failed)


def test_circle_side_and_cut_wall_sources_must_belong_to_authored_geometry():
    req = request()
    response = process_request(req)
    solid = response["result"]["features"][-1]
    side = next(face for face in solid["topology"] if face["role"].startswith("side."))
    old = side["id"]
    side.update(
        role="side.circle.missing_curve", id=side["feature_id"] + "/face/side.circle.missing_curve"
    )
    side["provenance"]["source_boundary"] = "circle.missing_curve"
    solid["mesh"]["triangle_face_ids"] = [
        side["id"] if identifier == old else identifier
        for identifier in solid["mesh"]["triangle_face_ids"]
    ]
    with pytest.raises(ValueError, match="semantic face role"):
        validator.validate_response(req, response)
    req = request("drilled_plate")
    response = process_request(req)
    wall = next(
        face
        for face in response["result"]["features"][-1]["topology"]
        if face["provenance"]["relation"] == "tool_unchanged"
    )
    wall["provenance"]["source_id"] = "invented/face/identity"
    with pytest.raises(ValueError, match="source"):
        validator.validate_response(req, response)
