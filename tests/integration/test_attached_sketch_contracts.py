"""Constrained attached sketches preserve local intent and prove world support."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_attached_sketch_contracts")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
operations = importlib.import_module(package.__name__ + ".operation_contracts")


def document(version=2):
    sketch = {
        "schema_version": version,
        "id": "face_geometry",
        "units": "mm",
        "plane": {"id": "local_plane", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [{"id": "center", "u": 0, "v": 0}],
        "lines": [],
        "circles": [{"id": "circle", "center": "center", "radius": 2}],
        "constraints": [
            {"id": "center_fixed", "kind": "fixed", "refs": ["center"], "target": [0, 0]},
            {"id": "radius", "kind": "radius", "refs": ["circle"], "value": 2},
        ],
    }
    if version == 3:
        sketch["arcs"] = []
    return {
        "schema_version": 2,
        "id": "part",
        "name": "Attached sketch",
        "units": "mm",
        "parameters": {"height": 10},
        "active_feature": "boss",
        "features": [
            {
                "id": "base_profile",
                "kind": "sketch_rectangle",
                "params": {"width": 10, "height": 10},
            },
            {
                "id": "base",
                "kind": "extrude",
                "params": {"length": "height"},
                "inputs": {"profile": "base_profile"},
            },
            {
                "id": "attached",
                "kind": "sketch_constrained",
                "inputs": {"support": "base"},
                "support_face": "base/face/cap.end",
                "sketch": sketch,
            },
            {
                "id": "boss",
                "kind": "extrude",
                "params": {"length": 2},
                "inputs": {"profile": "attached"},
            },
        ],
    }


@pytest.mark.parametrize("version", [2, 3])
def test_attached_solve_replay_and_upstream_edit_keep_authored_local_plane(version):
    source = document(version)
    for height in (10, 20):
        source["parameters"]["height"] = height
        before = copy.deepcopy(source)
        req = {
            "protocol_version": 1,
            "result_version": version,
            "action": "solve_sketch",
            "feature_id": "attached",
            "document": source,
        }
        response = process_request(req)
        assert response["ok"], response
        operations.validate_response(req, response)
        context = response["result"]["support_context"]
        assert [f["id"] for f in context["document"]["features"]] == ["base_profile", "base"]
        assert context["plane"]["origin"] == pytest.approx([5, 5, height])
        assert response["result"]["sketch"]["solved"]["plane"]["origin"] == pytest.approx(
            [5, 5, height]
        )
        req = {"protocol_version": 1, "result_version": version, "document": source}
        response = process_request(req)
        assert response["ok"], response
        operations.validate_response(req, response)
        assert response["result"]["features"][2]["support_plane"]["origin"] == pytest.approx(
            [5, 5, height]
        )
        assert source == before


@pytest.mark.parametrize("mutation", ["plane", "ancestor_document", "ancestor_topology"])
def test_attached_solve_rejects_forged_context(mutation):
    req = {
        "protocol_version": 1,
        "result_version": 3,
        "action": "solve_sketch",
        "feature_id": "attached",
        "document": document(3),
    }
    response = process_request(req)
    assert response["ok"], response
    context = response["result"]["support_context"]
    if mutation == "plane":
        context["plane"]["origin"][2] += 1
    elif mutation == "ancestor_document":
        context["document"]["name"] = "Unrelated"
    else:
        context["replay"]["features"][-1]["topology"][0]["id"] = "forged/face/identity"
    with pytest.raises(ValueError):
        operations.validate_response(req, response)


@pytest.mark.parametrize("version", [2, 3])
def test_attached_export_and_assembly_capture_keep_full_support_evidence(version, tmp_path):
    source = document(version)
    req = {
        "protocol_version": 1,
        "result_version": version,
        "action": "export_step",
        "document": source,
        "destination": str(tmp_path / "boss.step"),
    }
    response = process_request(req)
    assert response["ok"], response
    operations.validate_response(req, response)
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
    snapshots = importlib.import_module(
        package.__name__ + (".part_contracts_v3" if version == 3 else ".part_contracts")
    )
    assembly = edit.new_from_part(snapshots._expected_document(source))
    assert operations.result_version_for_assembly(assembly) == 3
    req = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 3,
        "action": "assembly_replay",
        "assembly": assembly,
    }
    response = process_request(req)
    assert response["ok"], response
    operations.validate_response(req, response)


@pytest.mark.parametrize("version", [2, 3])
def test_missing_attached_support_returns_no_solved_plane_and_blocks_downstream(version):
    source = document(version)
    source["features"][2]["support_face"] = "base/face/deleted"
    req = {
        "protocol_version": 1,
        "result_version": version,
        "action": "solve_sketch",
        "feature_id": "attached",
        "document": source,
    }
    response = process_request(req)
    assert not response["ok"] and response["result"] is None
    operations.validate_response(req, response)
    req = {"protocol_version": 1, "result_version": version, "document": source}
    response = process_request(req)
    assert not response["ok"]
    operations.validate_response(req, response)
    assert response["result"]["features"][2]["support_plane"] is None
    assert response["result"]["features"][-1]["status"] == "blocked"


@pytest.mark.parametrize("version", [2, 3])
def test_attached_canonical_receipt_preserves_local_plane_and_support_identity(version):
    source = document(version)
    snapshot = importlib.import_module(package.__name__ + ".part_snapshot_bridge")
    req = {"protocol_version": 1, "action": "canonical_snapshot", "document": source}
    response = process_request(req)
    assert response["ok"], response
    receipt = snapshot.validate_response(req, response)
    attached = receipt["canonical_document"]["features"][2]
    assert attached["support_face"] == "base/face/cap.end"
    assert attached["inputs"] == {"support": "base"}
    assert attached["sketch"]["plane"] == source["features"][2]["sketch"]["plane"]


def test_nested_attached_ancestor_solve_has_one_flat_replay_context():
    source = document(3)
    second = copy.deepcopy(source["features"][2])
    second.update(id="second", inputs={"support": "boss"}, support_face="boss/face/cap.end")
    source["features"].append(second)
    source["active_feature"] = "second"
    req = {
        "protocol_version": 1,
        "result_version": 3,
        "action": "solve_sketch",
        "feature_id": "second",
        "document": source,
    }
    response = process_request(req)
    assert response["ok"], response
    operations.validate_response(req, response)
    context = response["result"]["support_context"]
    assert len(context["replay"]["features"]) == 4
    assert all("support_context" not in row for row in context["replay"]["features"])
    assert context["plane"]["origin"] == pytest.approx([5, 5, 12])
