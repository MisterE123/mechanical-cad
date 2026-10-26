"""Live projected construction geometry is bound to current upstream solves."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_projection_contracts")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
operations = importlib.import_module(package.__name__ + ".operation_contracts")


def document(version=2):
    sketch = {
        "schema_version": version,
        "id": "source_geometry",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [{"id": "center", "u": 3, "v": 4}],
        "lines": [],
        "circles": [{"id": "circle", "center": "center", "radius": 5}],
        "constraints": [
            {"id": "fixed", "kind": "fixed", "refs": ["center"], "target": [3, 4]},
            {"id": "radius", "kind": "radius", "refs": ["circle"], "value": "r"},
        ],
    }
    if version == 3:
        sketch["arcs"] = []
    target = copy.deepcopy(sketch)
    target["id"] = "target_geometry"
    target["points"][0].update(u=0, v=0)
    target["circles"][0].update(radius=1, construction=True)
    target["constraints"][0]["target"] = [0, 0]
    target["constraints"][1]["value"] = 1
    target["points"].append({"id": "output_center", "u": 0, "v": 0})
    target["circles"].append({"id": "output", "center": "output_center", "radius": 1})
    target["constraints"] += [
        {"id": "follow", "kind": "coincident", "refs": ["center", "output_center"]},
        {"id": "output_radius", "kind": "radius", "refs": ["output"], "value": 1},
    ]
    return {
        "schema_version": 2,
        "id": "part",
        "name": "Projected sketch",
        "units": "mm",
        "parameters": {"r": 5},
        "active_feature": "boss",
        "features": [
            {"id": "source", "kind": "sketch_constrained", "sketch": sketch},
            {
                "id": "target",
                "kind": "sketch_constrained",
                "sketch": target,
                "inputs": {"external": "source"},
                "projections": [{"source": "circle", "target": "circle"}],
            },
            {
                "id": "boss",
                "kind": "extrude",
                "inputs": {"profile": "target"},
                "params": {"length": 2},
            },
        ],
    }


@pytest.mark.parametrize("version", [2, 3])
def test_live_solve_replay_and_upstream_edit(version):
    source = document(version)
    for radius in (5, 8):
        source["parameters"]["r"] = radius
        for action in ("solve_sketch", "replay"):
            req = {
                "protocol_version": 1,
                "result_version": version,
                "action": action,
                "document": source,
            }
            if action == "solve_sketch":
                req["feature_id"] = "target"
            response = process_request(req)
            assert response["ok"], response
            operations.validate_response(req, response)
            report = (
                response["result"]["sketch"]
                if action == "solve_sketch"
                else response["result"]["features"][1]["sketch"]
            )
            assert report["solved"]["circles"][0]["radius"] == pytest.approx(radius)
            assert source["features"][1]["sketch"]["circles"][0]["radius"] == 1
            forged = copy.deepcopy(response)
            if action == "solve_sketch":
                forged["result"]["support_context"]["document"]["parameters"]["r"] = 99
            else:
                forged["result"]["features"][1]["sketch"]["solved"]["circles"][0]["radius"] = 99
            with pytest.raises(ValueError):
                operations.validate_response(req, forged)


@pytest.mark.parametrize("version", [2, 3])
def test_missing_projection_never_publishes_frozen_geometry(version):
    source = document(version)
    source["features"][1]["projections"][0]["source"] = "deleted"
    for action in ("solve_sketch", "replay"):
        req = {
            "protocol_version": 1,
            "result_version": version,
            "action": action,
            "document": source,
        }
        if action == "solve_sketch":
            req["feature_id"] = "target"
        response = process_request(req)
        assert not response["ok"]
        operations.validate_response(req, response)
        if action == "solve_sketch":
            assert response["result"] is None
        else:
            assert response["result"]["features"][1].get("sketch") is None
            assert response["result"]["features"][-1]["status"] == "blocked"


def test_projection_capture_uses_full_result3_source_evidence():
    source = document(3)
    snapshots = importlib.import_module(package.__name__ + ".part_contracts_v3")
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
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


def test_projection_math_has_identical_independent_client_source():
    root = Path(__file__).resolve().parents[2]
    assert (root / "src/mechanical_cad/sketch_projection.py").read_text() == (
        root / "blender_addon/mechanical_cad_blender/sketch_projection.py"
    ).read_text()


@pytest.mark.parametrize("version", [2, 3])
def test_projection_and_face_attachment_share_one_bounded_context(version):
    source = document(version)
    source["features"][1]["inputs"]["support"] = "base"
    source["features"][1]["support_face"] = "base/face/cap.end"
    source["features"][1:1] = [
        {"id": "base_profile", "kind": "sketch_rectangle", "params": {"width": 10, "height": 10}},
        {
            "id": "base",
            "kind": "extrude",
            "inputs": {"profile": "base_profile"},
            "params": {"length": 10},
        },
    ]
    req = {
        "protocol_version": 1,
        "result_version": version,
        "action": "solve_sketch",
        "feature_id": "target",
        "document": source,
    }
    response = process_request(req)
    assert response["ok"], response
    operations.validate_response(req, response)
    context = response["result"]["support_context"]
    assert len(context["document"]["features"]) == 3
    assert context["plane"]["origin"] == pytest.approx([5, 5, 10])
    projected = response["result"]["sketch"]["solved"]["points"][0]
    assert [projected["u"], projected["v"]] == pytest.approx([-2, -1])
