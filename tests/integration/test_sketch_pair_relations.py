"""Actual native pair relations, independently checked in Blender's pure bridge."""

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Arc, Circle, Constraint, Line, Point, Sketch, SketchError
from mechanical_cad.sketch_solver import solve

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "pair_relation_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
bridge = importlib.import_module(PACKAGE + ".sketch_bridge")
v3 = importlib.import_module(PACKAGE + ".sketch_contracts_v3")
selection = importlib.import_module(PACKAGE + ".constraint_selection")
draft_module = importlib.import_module(PACKAGE + ".general_sketch_draft")


def line_pair(kind):
    return Sketch(
        "sketch",
        (Point("a", 0, 0), Point("b", 10, 0), Point("c", 0, 8), Point("d", 9, 12)),
        (Line("l", "a", "b"), Line("m", "c", "d")),
        (Constraint("relation", kind, ("l", "m")),),
        schema_version=2,
    )


@pytest.mark.parametrize("kind", ["parallel", "perpendicular", "equal"])
def test_line_pair_solve_bridge_selection_and_journal(kind):
    source = line_pair(kind)
    report = solve(source)
    assert report.success and report.max_residual < 1e-7
    normalized = bridge._normalized_sketch(report.sketch.to_dict(), numeric=True)
    assert bridge._residual(normalized) < 1e-7
    contract = selection.selection_contract(
        source.to_dict(),
        [
            {"kind": "line", "id": "m"},
            {"kind": "line", "id": "l"},
        ],
    )
    assert contract.action(kind).state == "existing"
    assert contract.action(kind).relation_ids == ("relation",)
    # Round-trip a real edit, Undo and Redo through the existing canonical journal.
    d = draft_module
    blank = {
        "schema_version": 1,
        "id": "doc",
        "name": "Part",
        "units": "mm",
        "parameters": {},
        "features": [],
        "active_feature": None,
    }
    draft = d.GeneralSketchDraft(json.dumps(blank))
    first = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(10, 0))).entity_ids[-1]
    second = draft.execute(d.AddLine(d.PointSeed(0, 8), d.PointSeed(9, 12))).entity_ids[-1]
    result = draft.execute(d.AddRelation(kind, (first, second)))
    assert result.changed
    request = draft.solve_request()
    response = process_request(request)
    assert response["ok"], response
    assert draft.record_validated_solution(request, response, draft.revision)
    saved = draft.checkpoint_payload()
    restored = d.GeneralSketchDraft.from_checkpoint_payload(saved)
    assert restored.sketch == draft.sketch
    restored.undo()
    assert not restored.sketch["constraints"]
    restored.redo()
    assert restored.sketch == draft.sketch


def test_equal_circle_radii_and_reference_validation():
    sketch = Sketch(
        "sketch",
        (Point("a", 0, 0), Point("b", 20, 0)),
        (),
        (Constraint("equal", "equal", ("circle1", "circle2")),),
        schema_version=2,
        circles=(Circle("circle1", "a", 5), Circle("circle2", "b", 8)),
    )
    result = solve(sketch)
    assert result.success and result.max_residual < 1e-7
    assert bridge._residual(bridge._normalized_sketch(result.sketch.to_dict())) < 1e-7
    wrong = sketch.to_dict()
    wrong["constraints"][0]["kind"] = "parallel"
    with pytest.raises(SketchError):
        Sketch.from_dict(wrong)
    with pytest.raises(ValueError):
        bridge._normalized_sketch(wrong)


@pytest.mark.parametrize("direction", ["cw", "ccw"])
@pytest.mark.parametrize("endpoint", ["a", "b"])
def test_arc_tangent_at_either_exact_endpoint(direction, endpoint):
    sketch = Sketch(
        "sketch",
        (Point("center", 0, 0), Point("a", 5, 0), Point("b", 0, 5), Point("d", 7, 8)),
        (Line("line", endpoint, "d"),),
        (Constraint("tangent", "tangent", ("arc", "line")),),
        schema_version=3,
        arcs=(Arc("arc", "center", "a", "b", direction),),
    )
    report = solve(sketch)
    assert report.success and report.max_residual < 1e-7
    normalized = v3.normalize_sketch_v3(report.sketch.to_dict(), numeric=True)
    assert v3._residual(normalized) < 1e-7
    contract = selection.selection_contract(
        sketch.to_dict(),
        [
            {"kind": "line", "id": "line"},
            {"kind": "arc", "id": "arc"},
        ],
    )
    assert contract.action("tangent").state == "existing"
    wrong = sketch.to_dict()
    wrong["lines"][0]["start"] = "center"
    with pytest.raises(SketchError):
        Sketch.from_dict(wrong)
    with pytest.raises(ValueError):
        v3.normalize_sketch_v3(wrong)
