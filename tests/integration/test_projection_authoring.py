"""Source-linked draft projection: atomic history, persisted references, real solves."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_projection_authoring_tests")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
D = importlib.import_module(package.__name__ + ".general_sketch_draft")
C = importlib.import_module(package.__name__ + ".general_sketch_commands")
A = importlib.import_module(package.__name__ + ".general_authoring")
S = importlib.import_module(package.__name__ + ".draft_dispatch")
G = importlib.import_module(package.__name__ + ".general_view_geometry")


def base():
    sketch = {
        "schema_version": 2,
        "id": "source_geometry",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [{"id": "center", "u": 4, "v": 5}],
        "lines": [],
        "circles": [{"id": "circle", "center": "center", "radius": 2}],
        "constraints": [
            {"id": "fixed", "kind": "fixed", "refs": ["center"], "target": [4, 5]},
            {"id": "size", "kind": "radius", "refs": ["circle"], "value": "r"},
        ],
    }
    return {
        "schema_version": 2,
        "id": "part",
        "name": "Part",
        "units": "mm",
        "parameters": {"r": 2},
        "active_feature": "source",
        "features": [
            {
                "id": "source",
                "kind": "sketch_constrained",
                "label": "Source",
                "params": {},
                "inputs": {},
                "sketch": sketch,
            }
        ],
    }


@pytest.mark.parametrize("version", [2, 3])
def test_projection_undo_roundtrip_and_upstream_regeneration(version):
    document = base()
    original = json.dumps(document)
    draft = D.GeneralSketchDraft(original, journal_version=version)
    outcome = draft.project_external(
        "source", "circle", C.AddProjectionGeometry("circle", (C.PointSeed(0, 0),), 1)
    )
    point_id, target_id = outcome.entity_ids
    assert draft.candidate()["features"][-1]["projections"] == [
        {"source": "circle", "target": target_id}
    ]
    assert draft.sketch["circles"][0]["construction"]
    draft.undo()
    assert not draft.sketch["points"]
    assert "external" not in draft.candidate()["features"][-1]["inputs"]
    wrapper = A.GeneralSketchAuthoringState(draft, ui_version=1 if version == 2 else 2)
    saved = S.dumps(wrapper)
    restored = S.restore(saved, original).command_draft
    restored.redo()
    assert restored.candidate()["features"][-1]["projections"][0]["target"] == target_id
    restored.execute(C.AddCircle(C.PointRef(point_id), 4))
    request = restored.solve_request()
    response = process_request(request)
    assert response["ok"], response
    geometry = G.build_geometry(
        restored.sketch, source="solved", solve_request=request, solve_response=response
    )
    assert geometry.points[point_id] == pytest.approx((4, 5))
    assert geometry.circles[target_id].radius_mm == pytest.approx(2)
    assert restored.sketch["points"][0]["u"] == 0
    assert restored.sketch["circles"][0]["radius"] == 1
    radius = next(
        c["id"]
        for c in restored.sketch["constraints"]
        if c["kind"] == "radius" and c["refs"] == [target_id]
    )
    with pytest.raises(ValueError, match="source"):
        restored.begin_edit(radius)
    with pytest.raises(ValueError, match="source"):
        restored.execute(C.MovePoint(point_id, (8, 8)))
    changed = copy.deepcopy(request)
    changed["document"]["parameters"]["r"] = 3
    changed["document"]["features"][0]["sketch"]["constraints"][0]["target"] = [8, 9]
    response = process_request(changed)
    assert response["ok"], response
    solved = response["result"]["sketch"]["solved"]
    assert next(p for p in solved["points"] if p["id"] == point_id)["u"] == pytest.approx(8)
    assert next(c for c in solved["circles"] if c["id"] == target_id)["radius"] == pytest.approx(3)
    assert restored.sketch["circles"][0]["radius"] == 1


def test_projected_line_is_atomic_and_cannot_lose_its_managed_anchors():
    document = base()
    source = document["features"][0]["sketch"]
    source["points"] += [{"id": "a", "u": 1, "v": 2}, {"id": "b", "u": 7, "v": 2}]
    source["lines"] = [{"id": "edge", "start": "a", "end": "b", "construction": True}]
    source["constraints"] += [
        {"id": "a_fixed", "kind": "fixed", "refs": ["a"], "target": [1, 2]},
        {"id": "b_fixed", "kind": "fixed", "refs": ["b"], "target": [7, 2]},
    ]
    draft = D.GeneralSketchDraft(json.dumps(document))
    outcome = draft.project_external(
        "source", "edge", C.AddProjectionGeometry("line", (C.PointSeed(0, 0), C.PointSeed(1, 0)))
    )
    p1, p2, line = outcome.entity_ids
    request = draft.solve_request()
    response = process_request(request)
    assert response["ok"], response
    geometry = G.build_geometry(
        draft.sketch, source="solved", solve_request=request, solve_response=response
    )
    assert geometry.points[p1] == pytest.approx((1, 2))
    assert geometry.points[p2] == pytest.approx((7, 2))
    draft._record_validated_solution(request, response, draft.revision)
    before = draft.checkpoint_payload()
    with pytest.raises(ValueError, match="construction"):
        draft.execute(C.SetConstruction((("line", line),), False))
    assert draft.checkpoint_payload() == before
    fixed = draft.sketch["constraints"][0]["id"]
    with pytest.raises(ValueError, match="fixed"):
        draft.execute(C.DeleteBatch(draft.preview_delete((("constraint", fixed),))))
    assert draft.checkpoint_payload() == before
    with pytest.raises(ValueError, match="anchor points"):
        draft.execute(C.DeleteBatch(draft.preview_delete((("line", line),))))
    assert draft.checkpoint_payload() == before
    draft.undo()
    assert not draft.sketch["lines"]
    draft.redo()
    assert len(draft.sketch["lines"]) == 1


def test_solid_edge_draft_scaffold_undo_and_saved_ledger():
    document = base()
    document["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "label": "Pad",
            "params": {"length": 10},
            "inputs": {"profile": "source"},
        }
    )
    document["active_feature"] = "pad"
    original = json.dumps(document)
    draft = D.GeneralSketchDraft(original, journal_version=3)
    faces = ["pad/face/cap.end", "pad/face/side.line.a"]
    endpoint_faces = [["pad/face/side.line.b"], ["pad/face/side.line.c"]]
    outcome = draft.project_solid_edge(
        "pad",
        faces,
        endpoint_faces,
        C.AddProjectionGeometry("line", (C.PointSeed(0, 0), C.PointSeed(10, 0))),
    )
    p1, p2, line = outcome.entity_ids
    assert draft.candidate()["features"][-1]["projections"] == [
        {"faces": faces, "endpoint_faces": endpoint_faces, "target": line}
    ]
    assert draft.sketch["lines"][0]["construction"]
    assert len(draft.sketch["constraints"]) == 2
    draft.undo()
    assert "projections" not in draft.candidate()["features"][-1]
    wrapper = A.GeneralSketchAuthoringState(draft, ui_version=2)
    restored = S.restore(S.dumps(wrapper), original).command_draft
    restored.redo()
    assert restored.candidate()["features"][-1]["projections"] == [
        {"faces": faces, "endpoint_faces": endpoint_faces, "target": line}
    ]
    with pytest.raises(ValueError, match="source"):
        restored.execute(C.MovePoint(p1, (2, 2)))
    circle = restored.project_external(
        "source", "circle", C.AddProjectionGeometry("circle", (C.PointSeed(0, 0),), 1)
    ).entity_ids[-1]
    feature = restored.candidate()["features"][-1]
    assert feature["inputs"] == {"external": "pad", "external_2": "source"}
    assert feature["projections"][-1] == {
        "source": "circle",
        "target": circle,
        "input": "external_2",
    }


@pytest.mark.parametrize("version", [2, 3])
def test_two_sketch_sources_roundtrip_and_regenerate_independently(version):
    document = base()
    other = copy.deepcopy(document["features"][0])
    other.update(id="other", label="Other")
    other["sketch"]["id"] = "other_geometry"
    other["sketch"]["constraints"][0]["target"] = [14, 15]
    other["sketch"]["constraints"][1]["value"] = 7
    document["features"].append(other)
    original = json.dumps(document)
    draft = D.GeneralSketchDraft(original, journal_version=version)
    command = C.AddProjectionGeometry("circle", (C.PointSeed(0, 0),), 1)
    first = draft.project_external("source", "circle", command).entity_ids[-1]
    second = draft.project_external("other", "circle", command).entity_ids[-1]
    wrapper = A.GeneralSketchAuthoringState(draft, ui_version=1 if version == 2 else 2)
    restored = S.restore(S.dumps(wrapper), original).command_draft
    request = restored.solve_request()
    response = process_request(request)
    assert response["ok"], response
    D.operation_contracts.validate_response(request, response)
    solved = response["result"]["sketch"]["solved"]
    points = {p["id"]: (p["u"], p["v"]) for p in solved["points"]}
    circles = {c["id"]: c for c in solved["circles"]}
    assert points[circles[first]["center"]] == pytest.approx((4, 5))
    assert points[circles[second]["center"]] == pytest.approx((14, 15))
    assert circles[first]["radius"] == pytest.approx(2)
    assert circles[second]["radius"] == pytest.approx(7)
    changed = copy.deepcopy(request)
    changed["document"]["features"][1]["sketch"]["constraints"][0]["target"] = [24, 25]
    updated = process_request(changed)
    assert updated["ok"], updated
    D.operation_contracts.validate_response(changed, updated)
    moved = {p["id"]: (p["u"], p["v"]) for p in updated["result"]["sketch"]["solved"]["points"]}
    assert moved[circles[first]["center"]] == pytest.approx((4, 5))
    assert moved[circles[second]["center"]] == pytest.approx((24, 25))
