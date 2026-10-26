"""Symmetric depth is a saved positive total, centered on the sketch plane."""

import importlib
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel, _shape_bounds
from mechanical_cad.model import Document, Feature
from mechanical_cad.sidecar import process_request

PACKAGE = "symmetric_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package


def document(depth=10, z=0):
    return Document(
        "symmetric",
        "Symmetric",
        {"total": depth, "plane_z": z},
        (
            Feature("p", "sketch_circle", "Circle", {"radius": 2, "z": "plane_z"}),
            Feature("pad", "extrude_symmetric", "Mid-plane", {"length": "total"}, {"profile": "p"}),
        ),
        "pad",
    )


@pytest.mark.parametrize("depth,z", [(10, 0), (4, 15), (100, -30)])
@pytest.mark.parametrize("version", [1, 2, 3])
def test_total_depth_centered_and_replayed(depth, z, version):
    restored = Document.from_json(document(depth, z).to_json())
    replay = regenerate(restored, OCPKernel(), result_version=version)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(4 * math.pi * depth)
    bounds = _shape_bounds(replay.shapes["pad"])
    assert bounds[2] == pytest.approx(z - depth / 2)
    assert bounds[5] == pytest.approx(z + depth / 2)
    assert restored.features[-1].kind == "extrude_symmetric"
    topology = replay.result["features"][-1]["topology"]
    assert {f["role"] for f in topology if f["provenance"]["semantic_status"] == "stable"} == {
        "cap.start",
        "cap.end",
        "side.circle",
    }


@pytest.mark.parametrize("version", [2, 3])
def test_symmetric_source_bound_transport(version):
    validator = importlib.import_module(
        PACKAGE + (".result_v3" if version == 3 else ".part_result_bridge")
    )
    request = {
        "protocol_version": 1,
        "result_version": version,
        "document": document().to_dict(),
        "options": {"linear_deflection": 0.1},
    }
    response = process_request(request)
    assert response["ok"], response
    assert validator.validate_response(request, response) == response


@pytest.mark.parametrize("depth", [-4, 0])
def test_nonpositive_total_depth_fails(depth):
    replay = regenerate(document(depth), OCPKernel())
    assert not replay.ok
    assert replay.result["features"][-1]["status"] == "failed"


def test_symmetric_face_profile_uses_its_rotated_normal():
    kernel = OCPKernel()
    base = kernel.extrude(kernel.rectangle(10, 20), 6)
    kernel.topology(base, "base", "extrude", {})
    profile = kernel.face_circle(base, "base/face/side.x_min", 1)
    pad = kernel.extrude_symmetric(profile, 8)
    assert kernel.inspect(pad)["volume"] == pytest.approx(8 * math.pi)
    bounds = _shape_bounds(pad)
    assert bounds[0] == pytest.approx(-4)
    assert bounds[3] == pytest.approx(4)
    faces = kernel.topology(pad, "pad", "extrude_symmetric", {})
    assert {f["role"] for f in faces} == {"cap.start", "cap.end", "side.circle"}


@pytest.mark.parametrize("kind", ["extrude_symmetric", "extrude_through", "extrude_to_face"])
@pytest.mark.parametrize("profile_kind", ["circle", "arc_loop"])
def test_current_general_circle_and_analytic_arc_loop(kind, profile_kind):
    from mechanical_cad.sketch_model import Arc, Line, Point, SketchDefinition

    if profile_kind == "circle":
        # Same current general sketch authoring command used by the viewport.
        import json

        draft_module = importlib.import_module(PACKAGE + ".general_sketch_draft")
        empty = Document("draft", "Draft", {}, (), None).to_json()
        draft = draft_module.GeneralSketchDraft(empty)
        draft.execute(draft_module.AddCircle(draft_module.PointSeed(0, 0), 2))
        sketch = Document.from_json(json.dumps(draft.candidate())).features[0].sketch
        area = 4 * math.pi
    else:
        sketch = SketchDefinition(
            "slot",
            (
                Point("a", 0, -2),
                Point("b", 4, -2),
                Point("c", 4, 2),
                Point("d", 0, 2),
                Point("left", 0, 0),
                Point("right", 4, 0),
            ),
            (Line("lower", "a", "b"), Line("upper", "c", "d")),
            (),
            schema_version=3,
            arcs=(
                Arc("right_arc", "right", "b", "c", "ccw"),
                Arc("left_arc", "left", "d", "a", "ccw"),
            ),
        )
        area = 16 + 4 * math.pi
    doc = Document(
        "current",
        "Current drawn profiles",
        {},
        (
            Feature(
                "p",
                "sketch_rectangle",
                "Base profile",
                {"width": 20, "height": 20, "x": -10, "y": -10},
            ),
            Feature("base", "extrude", "Base", {"length": 10}, {"profile": "p"}),
            Feature("sketch", "sketch_constrained", "Current sketch", sketch=sketch),
            Feature(
                "tool",
                kind,
                "Tool",
                {"direction": 1}
                if kind in {"extrude_through", "extrude_to_face"}
                else {"length": 10},
                {
                    "profile": "sketch",
                    **(
                        {"base": "base"}
                        if kind == "extrude_through"
                        else {"target": "base"}
                        if kind == "extrude_to_face"
                        else {}
                    ),
                },
                end_face="base/face/cap.end" if kind == "extrude_to_face" else None,
            ),
            Feature("cut", "cut", "Remove", {}, {"base": "base", "tool": "tool"}),
        ),
        "cut",
        schema_version=2,
    )
    request = {"protocol_version": 1, "result_version": 3, "document": doc.to_dict()}
    response = process_request(request)
    assert response["ok"], response
    importlib.import_module(PACKAGE + ".result_v3").validate_response(request, response)
    assert response["result"]["features"][-1]["stats"]["volume"] == pytest.approx(
        4000 - area * (5 if kind == "extrude_symmetric" else 10)
    )


@pytest.mark.parametrize("operation,expected", [("cut", 980), ("union", 1020)])
def test_symmetric_add_remove_candidate_exact_volume(operation, expected):
    build = importlib.import_module(PACKAGE + ".extrusion_candidate").extrusion_candidate
    source = Document(
        "part",
        "Part",
        {},
        (
            Feature("p", "sketch_rectangle", "Base profile", {"width": 10, "height": 10}),
            Feature("base", "extrude", "Base", {"length": 10}, {"profile": "p"}),
            Feature(
                "q",
                "sketch_rectangle",
                "Tool profile",
                {"width": 2, "height": 2, "x": 4, "y": 4, "z": 10},
            ),
        ),
        "base",
    ).to_dict()
    tool = Feature(
        "tool", "extrude_symmetric", "Symmetric", {"length": "10"}, {"profile": "q"}
    ).to_dict()
    boolean = Feature("result", operation, "Result", {}, {"base": "base", "tool": "tool"}).to_dict()
    candidate = build(source, tool, boolean)
    replay = regenerate(Document.from_dict(candidate), OCPKernel(), result_version=2)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(expected)
    assert candidate["parameters"] == {"tool_length": "10"}
    assert source["parameters"] == {}
