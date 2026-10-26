"""Exercise the bounded arc equation ceiling with the pinned native solver.

These are resource acceptance controls, not a general complexity or timing claim.
The independent arc audit supplied both fixtures before their regression adoption.
"""

from dataclasses import replace

import pytest

from mechanical_cad import sketch_solver
from mechanical_cad.sketch_model import (
    MAX_NATIVE_EQUATIONS,
    Arc,
    Constraint,
    Point,
    Sketch,
    SketchError,
    active_scalar_count,
    native_equation_count,
)
from mechanical_cad.sketch_solver import Status, solve

pytest.importorskip("slvs")


def ceiling_sketch(*, anchored):
    coordinates = ((0.0, 0.0), (5.0, 0.0), (0.0, 5.0))
    points = tuple(Point(f"p{i}", *coordinates[i % 3]) for i in range(256 if anchored else 3))
    constraints = ()
    if anchored:
        constraints = tuple(
            Constraint(f"fixed{i}", "fixed", (point.id,), target=(point.u, point.v))
            for i, point in enumerate(points)
        ) + tuple(Constraint(f"join{i}", "coincident", (f"p{i}", f"p{i + 3}")) for i in range(128))
    return Sketch(
        "native_ceiling",
        points,
        (),
        constraints,
        schema_version=3,
        arcs=tuple(Arc(f"arc{i}", "p0", "p1", "p2", "ccw" if i % 2 else "cw") for i in range(256)),
    )


@pytest.mark.parametrize("anchored,rows,scalars,dof", [(False, 256, 6, 5), (True, 1024, 512, 0)])
def test_native_intrinsic_and_equation_ceilings_are_accepted(anchored, rows, scalars, dof):
    original = ceiling_sketch(anchored=anchored)
    before = original.to_json()
    assert native_equation_count(original) == rows
    assert active_scalar_count(original) == scalars
    # No exact authored relation is removed by temporary duplicate filtering.
    unique, redundant = sketch_solver._unique_relations(original)
    assert len(unique) == len(original.constraints) and not redundant
    report = solve(original, diagnose=False)
    assert report.success and report.status == Status.REDUNDANT_OKAY
    assert report.remaining_dof == dof and report.max_residual == 0.0
    assert report.failed_constraints == report.redundant_constraints == ()
    assert report.sketch.arcs == original.arcs
    assert original.to_json() == before


def test_one_row_over_native_ceiling_rejects_before_loading_backend(monkeypatch):
    original = ceiling_sketch(anchored=True)
    oversized = replace(
        original,
        arcs=original.arcs[:-1],
        constraints=original.constraints + (Constraint("join128", "coincident", ("p128", "p131")),),
    )
    assert native_equation_count(oversized) == MAX_NATIVE_EQUATIONS + 1

    def forbidden():
        pytest.fail("The intrinsic equation resource limit must run before native loading")

    monkeypatch.setattr(sketch_solver, "_load_backend", forbidden)
    with pytest.raises(SketchError) as caught:
        solve(oversized)
    assert caught.value.code == "resource_limit"
    assert oversized.arcs == original.arcs[:-1]
    assert oversized.points is original.points
