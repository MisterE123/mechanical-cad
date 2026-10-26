"""Schema-3 arc opt-in must retain the released equality-cycle safety boundary."""

from dataclasses import replace

import pytest

from mechanical_cad import sketch_solver
from mechanical_cad.sketch_model import Arc, Constraint, Line, Point, Sketch, SketchError


def source(kind, direction):
    pairs = (("a", "b"), ("b", "c"), ("c", "a"))
    return Sketch(
        "arc_and_cycle",
        (
            Point("a", 0, 0),
            Point("b", 2, 1),
            Point("c", 4, 0),
            Point("center", 20, 20),
            Point("start", 25, 20),
            Point("end", 20, 25),
        ),
        tuple(Line(f"line{i}", *pair) for i, pair in enumerate(pairs)),
        tuple(
            Constraint(f"relation{i}", kind, pair if kind == "coincident" else (f"line{i}",))
            for i, pair in enumerate(pairs)
        ),
        schema_version=3,
        arcs=(Arc("arc", "center", "start", "end", direction),),
    )


@pytest.mark.parametrize("kind", ["coincident", "horizontal", "vertical"])
@pytest.mark.parametrize("direction", ["cw", "ccw"])
@pytest.mark.parametrize("diagnose", [False, True])
def test_arc_presence_cannot_bypass_pre_native_cycle_guard(monkeypatch, kind, direction, diagnose):
    original = source(kind, direction)
    before = original.to_json()

    def forbidden():
        pytest.fail("An equality cycle must reject before loading or touching native arc state")

    monkeypatch.setattr(sketch_solver, "_load_backend", forbidden)
    with pytest.raises(SketchError) as caught:
        sketch_solver.solve(original, diagnose=diagnose)
    assert caught.value.code == "solver_dof_indeterminate"
    assert original.to_json() == before


@pytest.mark.parametrize("kind", ["coincident", "horizontal", "vertical"])
@pytest.mark.parametrize("direction", ["cw", "ccw"])
def test_arc_intrinsic_equation_is_not_mistaken_for_coordinate_equality(
    monkeypatch, kind, direction
):
    class ReachedNative(Exception):
        pass

    def native_boundary():
        raise ReachedNative

    original = source(kind, direction)
    forest = replace(original, constraints=original.constraints[:2])
    before = forest.to_json()
    monkeypatch.setattr(sketch_solver, "_load_backend", native_boundary)
    with pytest.raises(ReachedNative):
        sketch_solver.solve(forest)
    assert forest.to_json() == before
