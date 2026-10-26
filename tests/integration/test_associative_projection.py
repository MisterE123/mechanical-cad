"""Projected authored identities rebuild, rather than freezing imported coordinates."""

import math
from dataclasses import replace

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.sketch_model import Circle, Constraint, Line, Plane, Point, SketchDefinition
from mechanical_cad.sketch_projection import project_sketch
from mechanical_cad.sketch_service import solve_sketch


def projected_document(radius=3):
    source = SketchDefinition(
        "source",
        (Point("p", 4, 5),),
        (),
        (
            Constraint("anchor", "fixed", ("p",), target=(4, 5)),
            Constraint("size", "radius", ("ring",), "r"),
        ),
        circles=(Circle("ring", "p", 1),),
        schema_version=2,
    )
    target = SketchDefinition(
        "target",
        (Point("q", 0, 0),),
        (),
        (
            Constraint("anchor", "fixed", ("q",), target=(0, 0)),
            Constraint("size", "radius", ("reference",), 1),
            Constraint("match", "equal", ("reference", "outline")),
        ),
        circles=(Circle("reference", "q", 1, True), Circle("outline", "q", 1)),
        plane=Plane((1, 2, 10)),
        schema_version=2,
    )
    return Document(
        "d",
        "Projection",
        {"r": radius},
        (
            Feature("source", "sketch_constrained", "Source", {}, {}, sketch=source),
            Feature(
                "target",
                "sketch_constrained",
                "Target",
                {},
                {"external": "source"},
                sketch=target,
                projections=({"source": "ring", "target": "reference"},),
            ),
            Feature("solid", "extrude", "Solid", {"length": 5}, {"profile": "target"}),
        ),
        "solid",
        schema_version=2,
    )


@pytest.mark.parametrize("radius", [3, 7])
def test_projected_circle_drives_real_solid_after_reopen_and_upstream_edit(radius):
    document = Document.from_json(projected_document(radius).to_json())
    original = document.to_json()
    replay = regenerate(document, OCPKernel(), result_version=2)
    assert replay.ok, replay.result
    row = replay.result["features"][1]
    p = row["sketch"]["solved"]["points"][0]
    assert (p["u"], p["v"]) == pytest.approx((3, 3))
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
        math.pi * radius**2 * 5
    )
    assert document.to_json() == original
    response = solve_sketch(document, "target")
    assert response["ok"], response
    context = response["result"]["support_context"]
    assert set(context) == {"document", "replay"}
    assert [f["id"] for f in context["document"]["features"]] == ["source"]
    assert response["result"]["document_hash"] == document.content_hash


def test_open_source_line_is_valid_external_dependency():
    doc = projected_document()
    source = SketchDefinition(
        "source",
        (Point("a", 2, 3), Point("b", 8, 3)),
        (Line("edge", "a", "b"),),
        (
            Constraint("fa", "fixed", ("a",), target=(2, 3)),
            Constraint("fb", "fixed", ("b",), target=(8, 3)),
        ),
        schema_version=2,
    )
    target = replace(
        doc.features[1].sketch,
        points=(*doc.features[1].sketch.points, Point("a", 0, 0), Point("b", 1, 0)),
        lines=(Line("guide", "a", "b", True),),
        constraints=(
            *doc.features[1].sketch.constraints,
            Constraint("fa", "fixed", ("a",), target=(0, 0)),
            Constraint("fb", "fixed", ("b",), target=(1, 0)),
        ),
    )
    doc = replace(
        doc,
        features=(
            replace(doc.features[0], sketch=source),
            replace(
                doc.features[1], sketch=target, projections=({"source": "edge", "target": "guide"},)
            ),
            doc.features[2],
        ),
    )
    replay = regenerate(doc, OCPKernel(), result_version=2)
    assert replay.ok, replay.result
    assert replay.result["features"][0]["output"]["profile"]["state"] == "unavailable"
    response = solve_sketch(doc, "target")
    assert response["ok"], response
    points = {p["id"]: p for p in response["result"]["sketch"]["solved"]["points"]}
    assert (points["a"]["u"], points["a"]["v"]) == pytest.approx((1, 1))
    assert (points["b"]["u"], points["b"]["v"]) == pytest.approx((7, 1))


def test_missing_source_and_tilted_circle_fail_explicitly():
    doc = projected_document()
    source = doc.features[0].sketch.to_dict()
    target = doc.features[1].sketch.to_dict()
    with pytest.raises(ValueError, match="missing"):
        project_sketch(target, source, [{"source": "gone", "target": "reference"}])
    target["plane"]["quaternion"] = [math.sqrt(0.5), math.sqrt(0.5), 0, 0]
    with pytest.raises(ValueError, match="parallel"):
        project_sketch(target, source, [dict(row) for row in doc.features[1].projections])


def test_projection_and_face_attachment_compose_and_follow_both_inputs():
    from test_associative_sketch_support import attached_document

    for depth in (10, 20):
        attached = attached_document(depth)
        projected = projected_document(3)
        source = projected.features[0]
        target = replace(
            attached.features[2],
            sketch=replace(projected.features[1].sketch, plane=Plane()),
            inputs={"support": "block", "external": "source"},
            projections=projected.features[1].projections,
        )
        doc = replace(
            attached,
            parameters={"depth": depth, "r": 3},
            features=(source, *attached.features[:2], target, *attached.features[3:]),
        )
        response = solve_sketch(doc, "attached")
        assert response["ok"], response
        context = response["result"]["support_context"]
        assert context["plane"]["origin"] == pytest.approx([10, 10, depth])
        assert [f["id"] for f in context["document"]["features"]] == [
            "source",
            "footprint",
            "block",
        ]
        p = response["result"]["sketch"]["solved"]["points"][0]
        assert (p["u"], p["v"]) == pytest.approx((-6, -5))
        replay = regenerate(doc, OCPKernel(), result_version=2)
        assert replay.ok, replay.result
        assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
            400 * depth - math.pi * 9 * 3
        )
