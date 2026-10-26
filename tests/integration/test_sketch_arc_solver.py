"""Pinned native arc adapter, directed identities and independent output gates."""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

import mechanical_cad.sketch_solver as adapter
from mechanical_cad.arc_geometry import arc_geometry
from mechanical_cad.sketch_model import (
    Arc,
    Circle,
    Constraint,
    Line,
    Plane,
    Point,
    Sketch,
    SketchDefinition,
    resolve_sketch,
)
from mechanical_cad.sketch_solver import Status, drag, solve

slvs = pytest.importorskip("slvs")


def arc_sketch(*, direction="ccw", angle=math.pi / 2, fixed=True, radius=5, sector=False):
    constraints = (Constraint("radius", "radius", ("arc",), radius),)
    if fixed:
        constraints += (Constraint("anchor", "fixed", ("c",), target=(0, 0)),)
    lines = ()
    if sector:
        lines = (Line("radial_start", "c", "s"), Line("radial_end", "e", "c"))
        constraints += (
            Constraint("start_axis", "horizontal", ("radial_start",)),
            Constraint("end_axis", "vertical", ("radial_end",)),
        )
    return Sketch(
        "directed_arc",
        (Point("c", 0, 0), Point("s", 5, 0), Point("e", 5 * math.cos(angle), 5 * math.sin(angle))),
        lines,
        constraints,
        schema_version=3,
        arcs=(Arc("arc", "c", "s", "e", direction),),
    )


def geometry(sketch):
    points = {p.id: (p.u, p.v) for p in sketch.points}
    arc = sketch.arcs[0]
    return arc_geometry(
        points[arc.center],
        points[arc.start],
        points[arc.end],
        arc.direction,
        require_equal_radii=True,
    )


@pytest.mark.parametrize("direction", ["cw", "ccw"])
@pytest.mark.parametrize("angle", [math.pi / 2, math.pi, 3 * math.pi / 2])
@pytest.mark.parametrize("radius", [5, 7])
def test_native_arc_radius_edits_keep_authored_direction_and_identities(direction, angle, radius):
    original = arc_sketch(direction=direction, angle=angle, radius=radius)
    before = original.to_json()
    report = solve(original)
    assert report.success, report
    assert report.remaining_dof == 2
    measured = geometry(report.sketch)
    expected = angle if direction == "ccw" else angle - math.tau
    assert measured.sweep_radians == pytest.approx(expected, abs=1e-8)
    assert measured.start_radius == pytest.approx(radius, abs=1e-10)
    assert report.sketch.arcs == original.arcs
    assert tuple(p.id for p in report.sketch.points) == tuple(p.id for p in original.points)
    assert report.sketch.constraints == original.constraints
    assert original.to_json() == before


@pytest.mark.parametrize(
    "fixed,dimension,expected",
    [(False, False, 5), (True, False, 3), (False, True, 4), (True, True, 2)],
)
def test_intrinsic_arc_equal_radius_equation_counts_once(fixed, dimension, expected):
    original = arc_sketch(fixed=fixed)
    if not dimension:
        original = replace(
            original, constraints=tuple(c for c in original.constraints if c.kind != "radius")
        )
    report = solve(original)
    assert report.success and report.remaining_dof == expected


@pytest.mark.parametrize("direction", ["cw", "ccw"])
@pytest.mark.parametrize("angle", [math.pi / 2, 3 * math.pi / 2])
def test_quarter_and_major_shared_endpoint_sectors_are_fully_constrained(direction, angle):
    original = arc_sketch(direction=direction, angle=angle, sector=True, radius=7)
    report = solve(original)
    assert report.success and report.remaining_dof == 0
    measured = geometry(report.sketch)
    assert measured.start_radius == pytest.approx(7)
    assert measured.sweep_radians == pytest.approx(
        angle if direction == "ccw" else angle - math.tau
    )
    assert report.sketch.lines == original.lines
    assert report.sketch.arcs == original.arcs
    assert len(report.sketch.points) == 3


def test_native_mapping_reuses_point_handles_and_swaps_only_clockwise_arguments(monkeypatch):
    native_arc, native_line, native_diameter = slvs.add_arc, slvs.add_line_2d, slvs.diameter
    arcs, lines, diameters = [], [], []

    def record_arc(*args):
        arcs.append(args)
        return native_arc(*args)

    def record_line(*args):
        lines.append(args)
        return native_line(*args)

    def record_diameter(*args):
        diameters.append(args)
        return native_diameter(*args)

    monkeypatch.setattr(slvs, "add_arc", record_arc)
    monkeypatch.setattr(slvs, "add_line_2d", record_line)
    monkeypatch.setattr(slvs, "diameter", record_diameter)
    original = arc_sketch(direction="cw", sector=True, radius=7)
    report = solve(original)
    assert report.success
    arc_args = arcs[0]
    # Alphabetic line compilation order: end-to-center, then center-to-start.
    assert arc_args[2] is lines[0][2] is lines[1][1]
    assert arc_args[3] is lines[0][1]  # Canonical end is native start.
    assert arc_args[4] is lines[1][2]  # Canonical start is native end.
    assert len(diameters) == 1 and diameters[0][2] == 14
    assert report.sketch.arcs == original.arcs


def test_radius_expression_remains_authored_and_unequal_seeds_are_not_normalized():
    original = SketchDefinition.from_dict(arc_sketch().to_dict())
    original = replace(
        original,
        points=(Point("c", 0, 0), Point("s", 5, 0), Point("e", 0, 6)),
        constraints=tuple(
            replace(c, value="shaft_radius + gap") if c.kind == "radius" else c
            for c in original.constraints
        ),
    )
    before = original.to_json()
    numeric = resolve_sketch(original, {"shaft_radius": 6, "gap": 1})
    assert numeric.points == original.points
    report = solve(numeric)
    assert report.success and geometry(report.sketch).start_radius == pytest.approx(7)
    assert original.to_json() == before
    assert next(c.value for c in original.constraints if c.kind == "radius") == "shaft_radius + gap"


@pytest.mark.parametrize("diagnose", [False, True])
def test_fixed_endpoint_incompatible_radius_fails_without_releasing_intent(diagnose):
    original = arc_sketch(radius=7)
    original = replace(
        original,
        constraints=original.constraints
        + (Constraint("fixed_start", "fixed", ("s",), target=(5, 0)),),
    )
    before = original.to_json()
    report = solve(original, diagnose=diagnose)
    assert not report.success
    assert report.remaining_dof is None and report.sketch is original
    assert set(report.failed_constraints) <= {c.id for c in original.constraints}
    if not diagnose:
        assert report.failed_constraints == ()
    assert original.to_json() == before


def test_complementary_arcs_keep_intrinsic_redundancy_separate_from_authored_ids():
    original = replace(
        arc_sketch(),
        constraints=(),
        arcs=(Arc("arc", "c", "s", "e", "ccw"), Arc("return", "c", "s", "e", "cw")),
    )
    report = solve(original)
    assert report.success and report.status == Status.REDUNDANT_OKAY
    assert report.remaining_dof == 5
    assert report.failed_constraints == report.redundant_constraints == ()
    assert report.sketch.arcs == original.arcs


def override_point(monkeypatch, index, value):
    native_add, native_get = slvs.add_point_2d, slvs.get_param_value
    parameters = []

    def add(*args):
        result = native_add(*args)
        if args[0] == 2:
            parameters.extend(result["param"][:2])
        return result

    def get(parameter):
        return value if parameter == parameters[index] else native_get(parameter)

    monkeypatch.setattr(slvs, "add_point_2d", add)
    monkeypatch.setattr(slvs, "get_param_value", get)


@pytest.mark.parametrize("value", [0, 5.000001, float("nan"), float("inf"), True])
def test_native_success_with_invalid_arc_output_is_atomic_without_projection(monkeypatch, value):
    original = arc_sketch()
    override_point(monkeypatch, 3, value)  # Compile order c,e,s: end v.
    report = solve(original)
    assert not report.success and report.status == Status.DIDNT_CONVERGE
    assert report.remaining_dof is None and report.sketch is original
    assert report.max_residual is None


def test_small_radius_intrinsic_residual_uses_relative_gate(monkeypatch):
    original = arc_sketch(radius=1e-6)
    original = replace(
        original, points=(Point("c", 0, 0), Point("s", 1e-6, 0), Point("e", 0, 1e-6))
    )
    override_point(monkeypatch, 3, 1e-6 + 5e-14)
    report = solve(original)
    assert not report.success and report.sketch is original
    assert report.remaining_dof is None


def test_compile_order_serialization_and_plane_are_repeatable():
    original = arc_sketch(sector=True, radius=7)
    original = replace(
        original,
        plane=Plane((1e6, -1e6, 100), (math.sqrt(0.5), math.sqrt(0.5), 0, 0)),
        points=(*original.points, Point("other_center", 20, 20)),
        circles=(Circle("other_circle", "other_center", 3),),
    )
    reversed_input = replace(
        original,
        points=tuple(reversed(original.points)),
        lines=tuple(reversed(original.lines)),
        constraints=tuple(reversed(original.constraints)),
    )
    a, b, c = [solve(s) for s in (original, reversed_input, original)]
    assert a.success and b.success and c.success
    assert a.sketch.to_json() == b.sketch.to_json() == c.sketch.to_json()
    assert a.sketch.plane is original.plane
    assert solve(Sketch.from_json(a.sketch.to_json())).success


def test_arc_ids_are_reserved_in_temporary_drag_namespace():
    original = arc_sketch()
    original = replace(
        original,
        arcs=(replace(original.arcs[0], id="drag-trial"),),
        constraints=tuple(
            replace(c, refs=("drag-trial",)) if c.kind == "radius" else c
            for c in original.constraints
        ),
    )
    report = drag(original, "s", (0, -5))
    assert report.success
    assert report.sketch.arcs == original.arcs
    assert report.sketch.constraints == original.constraints
    assert report.remaining_dof == 2


def test_independent_arc_solves_are_serialized_and_native_state_is_cleared():
    with ThreadPoolExecutor(max_workers=4) as pool:
        reports = list(pool.map(lambda r: solve(arc_sketch(radius=r)), range(3, 11)))
    for radius, report in zip(range(3, 11), reports, strict=True):
        assert report.success and geometry(report.sketch).start_radius == pytest.approx(radius)
    assert slvs.solve_sketch(2, True)[0]["dof"] == 0


def test_arc_native_exception_clears_state_and_preserves_source(monkeypatch):
    original = arc_sketch()
    before = original.to_json()

    def fail(*args):
        raise RuntimeError("arc native failure")

    monkeypatch.setattr(slvs, "add_arc", fail)
    with pytest.raises(RuntimeError, match="arc native failure"):
        adapter.solve(original)
    assert original.to_json() == before
    assert slvs.solve_sketch(2, True)[0]["dof"] == 0
