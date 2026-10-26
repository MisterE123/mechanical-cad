"""Real support replay plus solver evidence, keeping authored planes local."""

import math

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.sketch_model import Circle, Constraint, Line, Plane, Point, SketchDefinition
from mechanical_cad.sketch_service import solve_sketch


def attached_document(depth=10, *, lines=False):
    if lines:
        points = (Point("a", -2, -2), Point("b", 2, -2), Point("c", 2, 2), Point("d", -2, 2))
        geometry = tuple(
            Line("edge" + str(i), a, b)
            for i, (a, b) in enumerate((("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")))
        )
        constraints = tuple(
            Constraint("fixed" + p.id, "fixed", (p.id,), target=(p.u, p.v)) for p in points
        )
        sketch = SketchDefinition("drawn", points, geometry, constraints, schema_version=2)
    else:
        sketch = SketchDefinition(
            "drawn",
            (Point("center", 0, 0),),
            (),
            (
                Constraint("anchor", "fixed", ("center",), target=(0, 0)),
                Constraint("size", "radius", ("circle",), 2),
            ),
            schema_version=2,
            circles=(Circle("circle", "center", 2),),
        )
    return Document(
        "d",
        "Attached constrained pocket",
        {"depth": depth},
        (
            Feature("footprint", "sketch_rectangle", "Footprint", {"width": 20, "height": 20}),
            Feature("block", "extrude", "Block", {"length": "depth"}, {"profile": "footprint"}),
            Feature(
                "attached",
                "sketch_constrained",
                "Drawn face sketch",
                {},
                {"support": "block"},
                sketch=sketch,
                support_face="block/face/cap.end",
            ),
            Feature("tool", "extrude", "Pocket tool", {"length": -3}, {"profile": "attached"}),
            Feature("cut", "cut", "Pocket", {}, {"base": "block", "tool": "tool"}),
        ),
        "cut",
        schema_version=2,
    )


@pytest.mark.parametrize("lines", [False, True])
@pytest.mark.parametrize("depth", [10, 25])
def test_drawn_attached_sketch_replays_after_save_and_upstream_edit(lines, depth):
    original = attached_document(depth, lines=lines)
    document = Document.from_json(original.to_json())
    before = document.to_json()
    kernel = OCPKernel()
    replay = regenerate(document, kernel, result_version=2)
    assert replay.ok, replay.result
    row = replay.result["features"][2]
    assert row["support_plane"]["origin"] == pytest.approx([10, 10, depth])
    assert row["sketch"]["solved"]["plane"] == row["support_plane"]
    area = 16 if lines else math.pi * 4
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(400 * depth - area * 3)
    assert kernel.manufacturing_check(replay.shapes["cut"])["mesh"]["watertight"]
    assert document.to_json() == before
    assert document.features[2].sketch.plane.origin == (0, 0, 0)


def test_solve_context_replays_only_exact_support_ancestors():
    document = attached_document()
    # An unfinished downstream feature must not prevent drawing on valid support.
    data = document.to_dict()
    data["features"][3]["params"]["length"] = 0
    document = Document.from_dict(data)
    response = solve_sketch(document, "attached")
    assert response["ok"], response
    result = response["result"]
    assert result["document_hash"] == document.content_hash
    context = result["support_context"]
    assert [f["id"] for f in context["document"]["features"]] == ["footprint", "block"]
    assert context["document"]["active_feature"] == "block"
    assert (
        context["replay"]["document_hash"] == Document.from_dict(context["document"]).content_hash
    )
    assert context["plane"]["origin"] == pytest.approx([10, 10, 10])
    assert result["sketch"]["solved"]["plane"] == context["plane"]


def test_local_plane_offset_and_rotation_are_composed_not_replaced():
    from dataclasses import replace

    doc = attached_document()
    feature = doc.features[2]
    plane = Plane((2, 3, 1), (math.sqrt(0.5), 0, 0, math.sqrt(0.5)), id="local_offset")
    feature = replace(feature, sketch=replace(feature.sketch, plane=plane))
    doc = doc.with_feature(feature, make_active=False)
    response = solve_sketch(doc, "attached")
    assert response["ok"], response
    world = response["result"]["support_context"]["plane"]
    assert world["origin"] == pytest.approx([12, 13, 11])
    assert world["quaternion"] == pytest.approx(plane.quaternion)
    assert doc.features[2].sketch.plane == plane


def test_missing_support_stops_solve_without_fake_solver_report():
    from mechanical_cad.errors import CADException

    data = attached_document().to_dict()
    data["features"][2]["support_face"] = "block/face/does_not_exist"
    with pytest.raises(CADException, match="missing"):
        solve_sketch(Document.from_dict(data), "attached")


def test_support_failure_blocks_downstream_and_keeps_explicit_unresolved_plane():
    data = attached_document().to_dict()
    data["features"][2]["support_face"] = "block/face/does_not_exist"
    replay = regenerate(Document.from_dict(data), OCPKernel(), result_version=2)
    assert not replay.ok
    assert replay.result["features"][2]["support_plane"] is None
    assert "sketch" not in replay.result["features"][2]
    assert replay.result["features"][3]["status"] == "blocked"
