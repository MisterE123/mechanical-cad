"""Pinned native SolveSpace line symmetry, not a midpoint-only approximation."""

from dataclasses import replace

import pytest

from mechanical_cad.sketch_model import Constraint, Line, Plane, Point, Sketch, SketchError
from mechanical_cad.sketch_solver import solve


def source(axis=(-5, -5, 5, 5), *, anchor_point=True, construction=True):
    a, b = axis[:2], axis[2:]
    return Sketch(
        "mirror",
        (Point("a", *a), Point("b", *b), Point("p", 1, 3), Point("q", 4, 0)),
        (Line("axis", "a", "b", construction),),
        (
            Constraint("fa", "fixed", ("a",), target=a),
            Constraint("fb", "fixed", ("b",), target=b),
            *((Constraint("fp", "fixed", ("p",), target=(1, 3)),) if anchor_point else ()),
            Constraint("sym", "symmetry", ("p", "q", "axis")),
        ),
        schema_version=3,
    )


@pytest.mark.parametrize(
    "axis,expected",
    [
        ((-5, -5, 5, 5), (3, 1)),
        ((-5, 2, 5, 2), (1, 1)),
        ((2, -5, 2, 5), (3, 3)),
        ((5, 5, -5, -5), (3, 1)),
        ((-1, -2, 5, 6), (3.24, 1.32)),
    ],
)
@pytest.mark.parametrize("construction", [True, False])
def test_native_arbitrary_axis_exact_reflection(axis, expected, construction):
    sketch = source(axis, construction=construction)
    report = solve(sketch)
    assert report.success, report
    assert report.remaining_dof == 0
    assert report.max_residual < 1e-7
    q = next(p for p in report.sketch.points if p.id == "q")
    assert (q.u, q.v) == pytest.approx(expected, abs=1e-7)
    assert len(report.sketch.points) == 4 and len(report.sketch.constraints) == 4
    assert Sketch.from_json(report.sketch.to_json()) == report.sketch


def test_two_equation_freedom_and_arbitrary_workplane():
    sketch = source(anchor_point=False)
    sketch = replace(sketch, plane=Plane(origin=(10, 20, 30), quaternion=(0.5, 0.5, 0.5, 0.5)))
    report = solve(sketch)
    assert report.success and report.remaining_dof == 2, report
    assert report.max_residual < 1e-7
    free_axis = replace(sketch, constraints=sketch.constraints[-1:])
    report = solve(free_axis)
    assert report.success and report.remaining_dof == 6, report


def test_reversed_duplicate_and_conflict_preserve_authored_constraints():
    sketch = source()
    duplicate = replace(
        sketch,
        constraints=sketch.constraints + (Constraint("sym2", "symmetry", ("q", "p", "axis")),),
    )
    report = solve(duplicate)
    assert report.success and report.remaining_dof == 0
    assert report.redundant_constraints == ("sym2",)
    assert len(report.sketch.constraints) == 5
    conflicting = replace(
        sketch, constraints=sketch.constraints + (Constraint("fq", "fixed", ("q",), target=(4, 0)),)
    )
    report = solve(conflicting)
    assert not report.success and report.remaining_dof is None
    assert report.sketch == conflicting
    assert report.failed_constraints
    assert set(report.failed_constraints) <= {c.id for c in conflicting.constraints}


def test_degenerate_axis_fails_explicitly():
    with pytest.raises(SketchError, match="nondegenerate axis"):
        solve(source((0, 0, 0, 0)))
