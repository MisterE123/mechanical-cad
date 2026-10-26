"""Bounded exact geometry and persisted-graph evidence, not Blender GUI coverage."""

import importlib.util
import math
from pathlib import Path

import pytest

from mechanical_cad.model import Document
from mechanical_cad.sidecar import process_request

spec = importlib.util.spec_from_file_location(
    "hole_recipe_tests", Path(__file__).parents[1] / "unit/test_hole_recipe.py"
)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
validator = __import__("importlib").import_module("hole_test_addon.part_result_bridge")


def replay(document):
    document = Document.from_dict(document).to_dict()
    request = {"protocol_version": 1, "action": "replay", "result_version": 2, "document": document}
    result = process_request(request)
    validator.validate_response(request, result)
    return result


@pytest.mark.parametrize("face", ["cap.end", "side.x_max", "side.y_min"])
@pytest.mark.parametrize("counterbore", [False, True])
def test_exact_simple_counterbore_and_side_faces(face, counterbore):
    doc = helpers.make(face="pad/face/" + face, counterbore=counterbore)
    restored = Document.from_json(Document.from_dict(doc).to_json()).to_dict()
    assert helpers.recipe.inspect_hole(restored, helpers.ROOT)
    result = replay(restored)
    assert result["ok"], result
    final = result["result"]["features"][-1]
    removed = math.pi * 2.5**2 * 12 + (math.pi * (5**2 - 2.5**2) * 2 if counterbore else 0)
    assert final["stats"]["valid"] and final["stats"]["solids"] == 1
    assert final["stats"]["volume"] == pytest.approx(24000 - removed)
    restored["features"][1]["params"]["length"] = 24
    edited = helpers.make(
        restored, face="pad/face/" + face, counterbore=counterbore, diameter=6, editing=True
    )
    rebuilt = replay(edited)
    assert rebuilt["ok"], rebuilt
    removed = math.pi * 3**2 * 12 + (math.pi * (5**2 - 3**2) * 2 if counterbore else 0)
    assert rebuilt["result"]["features"][-1]["stats"]["volume"] == pytest.approx(28800 - removed)


@pytest.mark.parametrize("changes", [{"face": "pad/face/missing"}, {"x": 1000}])
def test_missing_face_and_no_material_removal_fail_closed(changes):
    result = replay(helpers.make(**changes))
    assert not result["ok"]


@pytest.mark.parametrize(
    "kind,params",
    [
        ("transform", {"rx": 23, "ry": 31, "rz": 17, "x": 11}),
        ("mirror", {"axis_x": 1, "axis_y": 2, "axis_z": 3, "x": 7}),
    ],
)
def test_rotated_and_mirrored_entry_normal_cuts_inward(kind, params):
    document = helpers.source()
    document["features"].append(
        {"id": "placed", "kind": kind, "params": params, "inputs": {"base": "pad"}}
    )
    document["active_feature"] = "placed"
    source_result = replay(document)
    assert source_result["ok"], source_result
    row = source_result["result"]["features"][-1]
    # Choose only explicit native stable cap provenance; no nearest-face lookup.
    cap = next(
        face
        for face in row["topology"]
        if face["role"] == "cap.end" and face["provenance"]["semantic_status"] == "stable"
    )
    drilled = helpers.make(document, base="placed", face=cap["id"], counterbore=True)
    result = replay(drilled)
    assert result["ok"], result
    stats = result["result"]["features"][-1]["stats"]
    assert stats["valid"] and stats["solids"] == 1
    assert stats["volume"] == pytest.approx(24000 - math.pi * (2.5**2 * 12 + (25 - 2.5**2) * 2))
