"""Authored non-XY sketches pass through the real solver and exact solid replay."""

import importlib
import json
import math
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("OCP")
pytest.importorskip("slvs")
from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_principal_native")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
d = importlib.import_module(package.__name__ + ".general_sketch_draft")
planes = importlib.import_module(package.__name__ + ".sketch_planes")


@pytest.mark.parametrize("kind", ["XY", "XZ", "YZ"])
def test_offset_plane_circle_solve_extrude_and_reedit(kind):
    base = json.dumps(
        {
            "schema_version": 1,
            "id": "part",
            "name": "Part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
    )
    plane = planes.principal_plane(kind, 25)
    draft = d.GeneralSketchDraft(base, plane=plane)
    center, circle = draft.execute(d.AddCircle(d.PointSeed(3, 4), 5)).entity_ids
    draft.execute(d.AddRelation("fixed", (center,), target=(3, 4)))
    draft.execute(d.AddRelation("radius", (circle,), value=5))
    request = draft.solve_request()
    response = process_request(request)
    assert response["ok"], response
    assert draft.record_validated_solution(request, response, draft.revision)
    assert response["result"]["sketch"]["remaining_dof"] == 0
    candidate = draft.candidate()
    candidate["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "params": {"length": 10},
            "inputs": {"profile": draft.feature_id},
        }
    )
    candidate["active_feature"] = "pad"
    edited = d.GeneralSketchDraft(json.dumps(candidate), draft.feature_id, True)
    assert edited.sketch["plane"] == plane
    replay = process_request(edited.replay_request())
    assert replay["ok"], replay
    assert replay["result"]["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 250)
