"""Boolean face inheritance crosses the client boundary only with exact lineage."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_boolean_lineage_contracts")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
bridge = importlib.import_module(package.__name__ + ".part_result_bridge")


def document(kind="union", same=False):
    features = [
        {"id": "pa", "kind": "sketch_rectangle", "params": {"width": 10, "height": 10}},
        {"id": "a", "kind": "extrude", "params": {"length": 10}, "inputs": {"profile": "pa"}},
    ]
    if not same:
        features += [
            {"id": "pb", "kind": "sketch_rectangle", "params": {"width": 10, "height": 10, "x": 5}},
            {"id": "b", "kind": "extrude", "params": {"length": 10}, "inputs": {"profile": "pb"}},
        ]
    features += [
        {"id": "boolean", "kind": kind, "inputs": {"base": "a", "tool": "a" if same else "b"}}
    ]
    return {
        "schema_version": 1,
        "id": "part",
        "name": "Two-source Boolean",
        "units": "mm",
        "parameters": {},
        "features": features,
        "active_feature": "boolean",
    }


@pytest.mark.parametrize("kind", ["union", "intersection"])
def test_exact_two_operand_inheritance_and_merged_unknown(kind):
    req = {"protocol_version": 1, "result_version": 2, "document": document(kind)}
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)
    faces = response["result"]["features"][-1]["topology"]
    assert {"a", "b"} <= {face["feature_id"] for face in faces}
    assert any(face["provenance"]["semantic_status"] == "merged" for face in faces)
    forged = copy.deepcopy(response)
    inherited = next(
        face for face in forged["result"]["features"][-1]["topology"] if face["feature_id"] == "b"
    )
    inherited["provenance"]["source_id"] = "a/face/side.x_min"
    with pytest.raises(ValueError):
        bridge.validate_response(req, forged)


def test_same_operand_twice_is_one_actual_lineage_source():
    req = {"protocol_version": 1, "result_version": 2, "document": document(same=True)}
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)
    assert all(
        face["provenance"]["semantic_status"] == "stable"
        for face in response["result"]["features"][-1]["topology"]
    )


@pytest.mark.parametrize("kind", ["union", "intersection"])
def test_boolean_tool_face_can_support_associative_profile(kind):
    source = document(kind)
    face = "b/face/side.x_max" if kind == "union" else "b/face/side.x_min"
    source["features"] += [
        {
            "id": "attached",
            "kind": "sketch_face_circle",
            "params": {"radius": 1},
            "inputs": {"support": "boolean"},
            "support_face": face,
        },
        {
            "id": "boss",
            "kind": "extrude",
            "params": {"length": 2},
            "inputs": {"profile": "attached"},
        },
    ]
    source["active_feature"] = "boss"
    req = {"protocol_version": 1, "result_version": 2, "document": source}
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)


@pytest.mark.parametrize("angle", [180, 360])
def test_revolve_actual_construction_faces_support_profile(angle):
    source = document(same=True)
    source["features"] = [
        {"id": "section", "kind": "sketch_rectangle", "params": {"width": 2, "height": 5, "x": 3}},
        {
            "id": "turned",
            "kind": "revolve",
            "params": {"angle": angle, "axis_y": 1, "axis_z": 0},
            "inputs": {"profile": "section"},
        },
        {
            "id": "attached",
            "kind": "sketch_face_circle",
            "params": {"radius": 0.25, "x": 4},
            "inputs": {"support": "turned"},
            "support_face": "turned/face/side.y_max",
        },
        {
            "id": "boss",
            "kind": "extrude",
            "params": {"length": 1},
            "inputs": {"profile": "attached"},
        },
    ]
    source["active_feature"] = "boss"
    req = {"protocol_version": 1, "result_version": 2, "document": source}
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)
    roles = {face["role"] for face in response["result"]["features"][1]["topology"]}
    assert ("cap.start" in roles) == (angle == 180)
