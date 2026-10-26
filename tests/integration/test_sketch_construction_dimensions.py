"""Connected construction and numeric dimensions through real native solving."""

import importlib
import json
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Sketch

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "construction_dimension_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
c = importlib.import_module(PACKAGE + ".general_sketch_commands")


def draft():
    return d.GeneralSketchDraft(
        json.dumps(
            {
                "schema_version": 1,
                "id": "doc",
                "name": "Part",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            }
        )
    )


def check(owner):
    request = owner.solve_request()
    response = process_request(request)
    assert response["ok"], response
    assert owner.record_validated_solution(request, response, owner.revision)
    return response


def test_construction_ignored_for_profile_but_retained_for_solver_and_journal():
    owner = draft()
    _, circle = owner.execute(c.AddCircle(c.PointSeed(0, 0), 10)).entity_ids
    _, _, line = owner.execute(c.AddLine(c.PointSeed(-20, 0), c.PointSeed(20, 0))).entity_ids
    owner.execute(c.SetConstruction((("line", line),), True))
    owner.execute(c.AddRelation("horizontal", (line,)))
    response = check(owner)
    assert response["result"]["profile_check"]["ready"]
    assert owner.sketch["lines"][0]["construction"]
    assert Sketch.from_dict(owner.sketch).lines[0].construction
    restored = d.GeneralSketchDraft.from_checkpoint_payload(owner.checkpoint_payload())
    assert restored.sketch == owner.sketch
    restored.undo()
    restored.undo()
    assert not restored.sketch["lines"][0].get("construction", False)
    restored.redo()
    assert restored.sketch["lines"][0]["construction"]
    owner.execute(c.SetConstruction((("circle", circle),), True))
    response = check(owner)
    assert not response["result"]["profile_check"]["ready"]
    assert response["result"]["profile_check"]["error"]["code"] == "open_profile"


def test_angle_formula_native_edit_and_diameter_radius_conversion():
    owner = draft()
    line1 = owner.execute(c.AddLine(c.PointSeed(0, 0), c.PointSeed(10, 0))).entity_ids[-1]
    line2 = owner.execute(c.AddLine(c.PointSeed(0, 5), c.PointSeed(10, 8))).entity_ids[-1]
    relation = owner.execute(c.AddRelation("angle", (line1, line2), value="30+30")).constraint_id
    response = check(owner)
    assert response["result"]["sketch"]["dimensions"][relation] == 60
    owner.begin_edit(relation)
    owner.update_edit("45")
    request = owner.solve_request(trial=True)
    response = process_request(request)
    assert response["ok"] and response["result"]["sketch"]["dimensions"][relation] == 45
    owner.cancel_edit()
    _, circle = owner.execute(c.AddCircle(c.PointSeed(50, 0), 5)).entity_ids
    radius = owner.execute(c.AddRelation("radius", (circle,), value="(24)/2")).constraint_id
    response = check(owner)
    assert response["result"]["sketch"]["dimensions"][radius] == 12


def test_move_endpoint_journal_and_constrained_rejection():
    owner = draft()
    a, b, line = owner.execute(c.AddLine(c.PointSeed(0, 0), c.PointSeed(10, 0))).entity_ids
    owner.execute(c.MovePoint(b, (20, 0)))
    assert next(p for p in owner.sketch["points"] if p["id"] == b)["u"] == 20
    owner.undo()
    assert next(p for p in owner.sketch["points"] if p["id"] == b)["u"] == 10
    owner.redo()
    owner.execute(c.AddRelation("horizontal", (line,)))
    with pytest.raises(ValueError, match="Release relations"):
        owner.execute(c.MovePoint(a, (1, 2)))


def test_drag_point_preserves_relations_formulas_and_single_history_step():
    owner = draft()
    a, b, line = owner.execute(c.AddLine(c.PointSeed(0, 0), c.PointSeed(10, 0))).entity_ids
    owner.execute(c.AddRelation("horizontal", (line,)))
    owner.execute(c.AddRelation("distance", (a, b), value="5*2"))
    check(owner)
    original = owner.sketch
    revision = owner.revision
    owner.execute(c.MovePoint(b, (20, 4), preserve_constraints=True))
    assert owner.revision == revision + 1
    assert owner.sketch["constraints"] == original["constraints"]
    response = check(owner)
    points = {p["id"]: (p["u"], p["v"]) for p in response["result"]["sketch"]["solved"]["points"]}
    assert math.dist(points[a], points[b]) == pytest.approx(10)
    assert points[a][1] == pytest.approx(points[b][1])
    restored = d.GeneralSketchDraft.from_checkpoint_payload(owner.checkpoint_payload())
    assert restored.sketch == owner.sketch
    restored.undo()
    assert restored.sketch == original
    restored.redo()
    assert restored.sketch == owner.sketch


def test_drag_fixed_point_is_atomic_and_does_not_remove_driver():
    owner = draft()
    a, _, _ = owner.execute(c.AddLine(c.PointSeed(0, 0), c.PointSeed(10, 0))).entity_ids
    owner.execute(c.AddRelation("fixed", (a,), target=(0, 0)))
    original, revision = owner.sketch, owner.revision
    with pytest.raises(ValueError, match="point is fixed"):
        owner.execute(c.MovePoint(a, (1, 2), preserve_constraints=True))
    assert owner.sketch == original and owner.revision == revision


def test_drag_does_not_replace_coordinate_formulas():
    owner = draft()
    a, _, _ = owner.execute(c.AddLine(c.PointSeed(0, 0), c.PointSeed(10, 0))).entity_ids
    sketch = owner.sketch
    sketch["points"][0]["u"] = "1+2"
    before = json.dumps(sketch, sort_keys=True)
    with pytest.raises(ValueError, match="coordinate formulas|Invalid sketch intent"):
        c._apply_record(sketch, {"op": "drag_point", "point_id": a, "target": [4, 5]})
    assert json.dumps(sketch, sort_keys=True) == before
