"""Real associated mate frames cross strict source and pose evidence boundaries."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_associative_frame_contracts")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
edit = importlib.import_module(package.__name__ + ".assembly_edit")
contracts = importlib.import_module(package.__name__ + ".part_contracts")
bridge = importlib.import_module(package.__name__ + ".assembly_bridge")
policy = importlib.import_module(package.__name__ + ".operation_contracts")


def request(height=10, kind="fixed", face="pad/face/cap.end"):
    part = {
        "schema_version": 1,
        "id": "block",
        "name": "Block",
        "units": "mm",
        "parameters": {},
        "features": [
            {"id": "profile", "kind": "sketch_rectangle", "params": {"width": 10, "height": 10}},
            {
                "id": "pad",
                "kind": "extrude",
                "params": {"length": height},
                "inputs": {"profile": "profile"},
            },
        ],
        "active_feature": "pad",
    }
    assembly = edit.new_from_part(contracts._expected_document(part))
    definition = assembly["parts"][0]
    definition["mate_frames"].append(
        {
            "id": "face",
            "name": "Attached top",
            "placement": edit.origin_frame(),
            "support_face": face,
        }
    )
    assembly["instances"].append({"id": "child", "name": "Child", "part_id": definition["id"]})
    joint = {
        "id": "joint",
        "name": "Joint",
        "kind": kind,
        "parent": assembly["grounded_instance"],
        "child": "child",
        "parent_frame": "face",
        "child_frame": "origin",
    }
    if kind != "fixed":
        joint.update(coordinate=0.25, limits=None)
    assembly["joints"].append(joint)
    return {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 3,
        "action": "assembly_replay",
        "assembly": assembly,
    }


@pytest.mark.parametrize("kind", ["fixed", "slider", "revolute"])
def test_real_associative_frames_and_pose_bound_to_upstream_geometry(kind):
    for height in (10, 20):
        req = request(height, kind)
        assert policy.result_version_for_assembly(req["assembly"]) == 3
        response = process_request(req)
        assert response["ok"], response
        bridge.validate_response(req, response)
        pose = response["report"]["base_pose"]["transforms"]["child"]
        assert pose["xyz_mm"] == pytest.approx([5, 5, height + (0.25 if kind == "slider" else 0)])


@pytest.mark.parametrize(
    "mutation",
    ["resolved_translation", "resolved_rotation", "pose_translation", "support_identity"],
)
def test_associative_evidence_rejects_forged_frame_or_pose(mutation):
    req = request()
    response = process_request(req)
    assert response["ok"], response
    forged = copy.deepcopy(response)
    part = forged["result"]["parts"][0]
    if mutation == "resolved_translation":
        part["resolved_mate_frames"]["face"]["xyz_mm"][2] += 1
    elif mutation == "resolved_rotation":
        part["resolved_mate_frames"]["face"]["wxyz"] = [0, 1, 0, 0]
    elif mutation == "pose_translation":
        forged["report"]["base_pose"]["transforms"]["child"]["xyz_mm"][2] += 1
    else:
        part["mate_frames"][-1]["support_face"] = "pad/face/cap.start"
    if mutation == "pose_translation":
        common = importlib.import_module(package.__name__ + ".assembly_validation_common")
        forged["report_fingerprint"] = common.fingerprint(
            {
                "request": forged["request"],
                "report": forged["report"],
                "error": forged["error"],
                "source_replays": forged["result"]["source_replays"],
            }
        )
    error = importlib.import_module(package.__name__ + ".bridge").BridgeError
    with pytest.raises(
        error, match="pose transforms contradict" if mutation == "pose_translation" else None
    ):
        bridge.validate_response(req, forged)


def test_associative_missing_support_never_publishes_current_pose():
    req = request(face="pad/face/missing")
    response = process_request(req)
    assert not response["ok"]
    bridge.validate_response(req, response)


@pytest.mark.parametrize(
    "face",
    [
        "pad/face/cap.start",
        "pad/face/side.x_min",
        "pad/face/side.x_max",
        "pad/face/side.y_min",
        "pad/face/side.y_max",
    ],
)
def test_associated_basis_handles_all_planar_normal_directions(face):
    req = request(face=face)
    req["assembly"]["parts"][0]["mate_frames"][-1]["placement"] = {
        "xyz_mm": [1, 2, 3],
        "wxyz": [0.5, 0.5, 0.5, 0.5],
    }
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)
