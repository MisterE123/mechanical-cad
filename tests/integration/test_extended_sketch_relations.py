"""Common geometric relations use native equations and independent exact residuals."""

import math
from dataclasses import replace

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.sketch_model import (
    Circle,
    Constraint,
    Line,
    Point,
    SketchDefinition,
    resolve_sketch,
)
from mechanical_cad.sketch_solver import solve


def line_sketch(kind, schema=2):
    return SketchDefinition(
        "relations",
        (Point("a", -10, 0), Point("b", 10, 0), Point("p", 3, 3)),
        (Line("line", "a", "b", True),),
        (
            Constraint("anchor_a", "fixed", ("a",), target=(-10, 0)),
            Constraint("anchor_b", "fixed", ("b",), target=(10, 0)),
            Constraint(
                "relation", kind, ("circle" if kind == "circle_line_tangent" else "p", "line")
            ),
            *(
                (Constraint("size", "radius", ("circle",), 2),)
                if kind == "circle_line_tangent"
                else ()
            ),
        ),
        circles=(Circle("circle", "p", 2),) if kind == "circle_line_tangent" else (),
        schema_version=schema,
    )


@pytest.mark.parametrize(
    "kind,dof", [("point_on_line", 1), ("midpoint", 0), ("circle_line_tangent", 1)]
)
def test_native_relation_geometry_dof_and_no_exported_auxiliary_points(kind, dof):
    source = line_sketch(kind)
    report = solve(resolve_sketch(source, {}))
    assert report.success, report
    assert report.remaining_dof == dof
    assert report.max_residual < 1e-7
    assert len(report.sketch.points) == len(source.points)
    point = next(p for p in report.sketch.points if p.id == "p")
    assert point.v == pytest.approx(2 if kind == "circle_line_tangent" else 0)
    if kind == "midpoint":
        assert point.u == pytest.approx(0)
    assert source.points[-1].v == 3


@pytest.mark.parametrize("schema", [1, 2, 3])
def test_midpoint_and_point_on_line_preserve_schema(schema):
    for kind in ("point_on_line", "midpoint"):
        source = line_sketch(kind, schema)
        reopened = SketchDefinition.from_json(source.to_json())
        report = solve(resolve_sketch(reopened, {}))
        assert report.success, report
        assert report.sketch.schema_version == schema


def test_concentric_ring_rebuilds_as_real_annular_solid():
    source = SketchDefinition(
        "ring",
        (Point("a", 0, 0), Point("b", 1, 1)),
        (),
        (
            Constraint("anchor", "fixed", ("a",), target=(0, 0)),
            Constraint("outer_size", "radius", ("outer",), 5),
            Constraint("inner_size", "radius", ("inner",), 2),
            Constraint("centers", "concentric", ("outer", "inner")),
        ),
        circles=(Circle("outer", "a", 5), Circle("inner", "b", 2)),
        schema_version=2,
    )
    report = solve(resolve_sketch(source, {}))
    assert report.success and report.remaining_dof == 0, report
    document = Document(
        "d",
        "Concentric ring",
        {},
        (
            Feature("ring", "sketch_constrained", "Ring", {}, {}, sketch=source),
            Feature("solid", "extrude", "Solid", {"length": 3}, {"profile": "ring"}),
        ),
        "solid",
        schema_version=2,
    )
    replay = regenerate(Document.from_json(document.to_json()), OCPKernel(), result_version=2)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 21 * 3)


def test_circle_line_tangent_profile_extrudes_without_contact_geometry():
    source = line_sketch("circle_line_tangent")
    document = Document(
        "d",
        "Tangent circle",
        {},
        (
            Feature("profile", "sketch_constrained", "Circle", {}, {}, sketch=source),
            Feature("solid", "extrude", "Solid", {"length": 3}, {"profile": "profile"}),
        ),
        "solid",
        schema_version=2,
    )
    replay = regenerate(document, OCPKernel(), result_version=2)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 4 * 3)


def test_inconsistent_circle_tangency_keeps_authored_geometry_and_unique_diagnostics():
    source = line_sketch("circle_line_tangent")
    source = replace(
        source,
        constraints=(
            *source.constraints,
            Constraint("locked_center", "fixed", ("p",), target=(3, 3)),
        ),
    )
    numeric = resolve_sketch(source, {})
    report = solve(numeric)
    assert not report.success
    assert report.sketch == numeric
    assert report.remaining_dof is None
    assert len(report.failed_constraints) == len(set(report.failed_constraints))


def test_concentric_participates_in_native_coordinate_cycle_guard():
    from mechanical_cad.sketch_model import SketchError

    source = SketchDefinition(
        "cycle",
        (Point("a", 0, 0), Point("b", 1, 1), Point("c", 2, 2)),
        (),
        (
            Constraint("ab", "concentric", ("one", "two")),
            Constraint("bc", "concentric", ("two", "three")),
            Constraint("ca", "coincident", ("c", "a")),
        ),
        circles=(Circle("one", "a", 1), Circle("two", "b", 2), Circle("three", "c", 3)),
        schema_version=2,
    )
    with pytest.raises(SketchError, match="cyclic"):
        solve(resolve_sketch(source, {}))
