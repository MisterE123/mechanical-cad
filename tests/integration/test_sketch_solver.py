import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from mechanical_cad.sketch_solver import Constraint, Line, Plane, Point, Sketch, Status, drag, solve

slvs = pytest.importorskip("slvs")


def rectangle(*, fixed=False, dimensions=True, width=40.0, height=20.0):
    # Eight distinct point entities test real coincidence constraints; a shared
    # point rectangle would not exercise coincident endpoint solving at all.
    points = tuple(
        Point(f"p{i}", *xy)
        for i, xy in enumerate(
            (
                (0.0, 0.0),
                (39.0, 0.5),
                (40.0, -0.3),
                (40.5, 19.0),
                (39.8, 20.4),
                (0.2, 20.1),
                (-0.2, 20.5),
                (0.4, -0.1),
            )
        )
    )
    lines = tuple(Line(f"l{i}", f"p{2 * i}", f"p{2 * i + 1}") for i in range(4))
    constraints = tuple(
        Constraint(f"join{i}", "coincident", (f"p{2 * i + 1}", f"p{(2 * i + 2) % 8}"))
        for i in range(4)
    ) + tuple(
        Constraint(f"axis{i}", "horizontal" if i % 2 == 0 else "vertical", (f"l{i}",))
        for i in range(4)
    )
    if dimensions:
        constraints += (
            Constraint("width", "distance", ("p0", "p1"), width),
            Constraint("height", "distance", ("p2", "p3"), height),
        )
    if fixed:
        constraints += (Constraint("anchor", "fixed", ("p0",), target=(0.0, 0.0)),)
    return Sketch("rectangle-sketch", points, lines, constraints)


def xy(sketch):
    return {p.id: (p.u, p.v) for p in sketch.points}


def assert_rectangle(report, width=40.0, height=20.0):
    assert report.success, report
    assert report.max_residual < 1e-7
    p = xy(report.sketch)
    assert math.dist(p["p0"], p["p1"]) == pytest.approx(width)
    assert math.dist(p["p2"], p["p3"]) == pytest.approx(height)
    for i in range(4):
        assert p[f"p{2 * i + 1}"] == pytest.approx(p[f"p{(2 * i + 2) % 8}"])
        axis = 1 if i % 2 == 0 else 0
        assert p[f"p{2 * i}"][axis] == pytest.approx(p[f"p{2 * i + 1}"][axis])


def test_native_binding_contract_not_incorrect_pyi():
    slvs.clear_sketch()
    try:
        wp = slvs.add_base_2d(1)
        slvs.add_point_2d(2, 1.0, 2.0, wp)
        result = slvs.solve_sketch(2, True)
        assert isinstance(result, tuple) and len(result) == 2
        info, failed = result
        assert info == {"result": 0, "dof": 2, "nbad": 0}
        assert failed == []
        assert slvs.solve_sketch(2, False) == {"result": 0, "dof": 2, "nbad": 0}
    finally:
        slvs.clear_sketch()


def test_fully_constrained_rectangle_with_real_coincident_endpoints():
    sketch = rectangle(fixed=True)
    before = sketch.to_json()
    report = solve(sketch)
    assert_rectangle(report)
    assert report.remaining_dof == 0
    assert xy(report.sketch)["p0"] == pytest.approx((0.0, 0.0))
    assert xy(report.sketch)["p3"] == pytest.approx((40.0, 20.0))
    assert sketch.to_json() == before  # No partial mutations or silent commits.


@pytest.mark.parametrize(
    "fixed,dimensions,dof",
    [(False, False, 4), (False, True, 2), (True, False, 2), (True, True, 0)],
)
def test_structural_remaining_degrees_of_freedom(fixed, dimensions, dof):
    report = solve(rectangle(fixed=fixed, dimensions=dimensions))
    assert report.success
    assert report.remaining_dof == dof


def test_inconsistent_dimensions_return_stable_ids_and_original_geometry():
    sketch = rectangle(fixed=True)
    sketch = replace(
        sketch,
        constraints=sketch.constraints
        + (Constraint("conflicting-width", "distance", ("p0", "p1"), 41.0),),
    )
    report = solve(sketch)
    assert report.status == Status.INCONSISTENT
    assert not report.success
    assert {"width", "conflicting-width"}.issubset(report.failed_constraints)
    assert report.remaining_dof is None
    assert report.sketch is sketch


def test_failure_can_disable_expensive_diagnostics():
    sketch = rectangle()
    sketch = replace(
        sketch,
        constraints=sketch.constraints + (Constraint("bad-width", "distance", ("p0", "p1"), 41.0),),
    )
    report = solve(sketch, diagnose=False)
    assert not report.success and report.failed_constraints == ()


def test_exact_target_drag_preserves_dimensions_and_persistent_dof():
    before = solve(rectangle()).sketch
    report = drag(before, "p0", (13.25, -7.5))
    assert_rectangle(report)
    assert xy(report.sketch)["p0"] == pytest.approx((13.25, -7.5))
    assert report.remaining_dof == 2
    assert report.sketch.constraints == before.constraints
    assert all(c.id != "drag-trial" for c in report.sketch.constraints)


def test_unreachable_drag_is_rejected_without_geometry_change():
    before = solve(rectangle(fixed=True)).sketch
    report = drag(before, "p0", (13.25, -7.5))
    assert not report.success
    assert "@drag" in report.failed_constraints
    assert report.sketch is before


def test_serialization_re_solve_stable_ids_and_double_precision():
    first = solve(rectangle(fixed=True, width=40.1234567890123, height=20.9876543210987))
    assert_rectangle(first, 40.1234567890123, 20.9876543210987)
    text = first.sketch.to_json()
    loaded = Sketch.from_json(text)
    assert loaded.to_json() == text
    second = solve(loaded)
    assert second.success
    assert {p.id for p in second.sketch.points} == {p.id for p in first.sketch.points}
    for key, value in xy(first.sketch).items():
        assert xy(second.sketch)[key] == pytest.approx(value, abs=1e-10)
    assert '"param"' not in text and '"h"' not in text


def test_compile_order_and_repeated_solves_are_deterministic():
    original = rectangle(fixed=True)
    reordered = replace(
        original,
        points=tuple(reversed(original.points)),
        lines=tuple(reversed(original.lines)),
        constraints=tuple(reversed(original.constraints)),
    )
    a, b, c = solve(original), solve(reordered), solve(original)
    assert a.sketch.to_json() == b.sketch.to_json() == c.sketch.to_json()


def test_non_xy_plane_is_preserved():
    plane = Plane((3.0, 4.0, 5.0), (math.sqrt(0.5), math.sqrt(0.5), 0.0, 0.0))
    report = solve(replace(rectangle(fixed=True), plane=plane))
    assert_rectangle(report)
    assert report.sketch.plane == plane


def test_independent_sketches_and_failure_do_not_leak_native_state():
    a = rectangle(fixed=True, width=25.0)
    b = rectangle(fixed=True, width=70.0)
    for sketch, width in ((a, 25.0), (b, 70.0), (a, 25.0)):
        assert_rectangle(solve(sketch), width, 20.0)
    # The global native state is also cleared on successful return.
    assert slvs.solve_sketch(2, True)[0]["dof"] == 0


def test_concurrent_adapter_callers_are_serialized():
    widths = [float(10 + i) for i in range(20)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda w: solve(rectangle(fixed=True, width=w)), widths))
    for width, report in zip(widths, results, strict=True):
        assert_rectangle(report, width, 20.0)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: replace(s, points=s.points + (s.points[0],)),
        lambda s: replace(s, points=(replace(s.points[0], u=float("nan")),) + s.points[1:]),
        lambda s: replace(s, points=(replace(s.points[0], u=float("inf")),) + s.points[1:]),
        lambda s: replace(s, lines=(Line("bad-line", "missing", "p0"),)),
        lambda s: replace(
            s, constraints=(Constraint("bad-ref", "distance", ("p0", "missing"), 10.0),)
        ),
        lambda s: replace(
            s, constraints=(Constraint("bad-type", "unknown_relation", ("l0", "l1")),)
        ),
        lambda s: replace(
            s,
            constraints=(Constraint("bad-dimension", "distance", ("p0", "p1"), -10.0),),
        ),
        lambda s: replace(s, plane=Plane(quaternion=(0.0, 0.0, 0.0, 0.0))),
        lambda s: replace(s, units="inch"),
    ],
)
def test_invalid_inputs_rejected_before_native_execution(mutation):
    with pytest.raises(ValueError):
        solve(mutation(rectangle()))


def test_unknown_schema_is_rejected():
    with pytest.raises(ValueError, match="schema"):
        Sketch.from_json(rectangle().to_json().replace('"schema_version":1', '"schema_version":99'))


def test_zero_length_seed_reports_native_failure_without_fake_success():
    s = Sketch(
        "degenerate",
        (Point("a", 0.0, 0.0), Point("b", 0.0, 0.0)),
        (Line("l", "a", "b"),),
        (
            Constraint("length", "distance", ("a", "b"), 10.0),
            Constraint("horizontal", "horizontal", ("l",)),
        ),
    )
    report = solve(s)
    # The native solver labels this INCONSISTENT even though a nonzero seed
    # makes the model feasible. Failure IDs are diagnostic candidates, not an
    # infeasibility proof. Do not silently invent a seed perturbation here.
    assert report.status == Status.INCONSISTENT
    assert report.sketch is s and report.remaining_dof is None


def test_near_degenerate_but_nonzero_seed_solves():
    s = Sketch(
        "near-degenerate",
        (Point("a", 0.0, 0.0), Point("b", 1e-5, 1e-5)),
        (Line("l", "a", "b"),),
        (
            Constraint("length", "distance", ("a", "b"), 10.0),
            Constraint("horizontal", "horizontal", ("l",)),
        ),
    )
    report = solve(s)
    assert report.success
    assert report.remaining_dof == 2
    assert math.dist(*xy(report.sketch).values()) == pytest.approx(10.0)


def test_editing_existing_dimension_re_solves_without_replacing_ids():
    before = solve(rectangle(fixed=True)).sketch
    changed = replace(
        before,
        constraints=tuple(
            replace(c, value=55.75) if c.id == "width" else c for c in before.constraints
        ),
    )
    report = solve(changed)
    assert_rectangle(report, width=55.75)
    assert report.remaining_dof == 0
    assert [p.id for p in report.sketch.points] == [p.id for p in before.points]
    assert [c.id for c in report.sketch.constraints] == [c.id for c in before.constraints]
    assert xy(before)["p1"] == (40.0, 0.0)


@pytest.mark.parametrize("point_id,target", [("p0", (0.0, 0.0)), ("p3", (40.0, 20.0))])
def test_no_op_drag_of_fully_constrained_sketch_succeeds(point_id, target):
    before = solve(rectangle(fixed=True)).sketch
    report = drag(before, point_id, target)
    assert report.success and report.remaining_dof == 0
    assert report.sketch.to_json() == before.to_json()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: replace(s, points=[*s.points]),
        lambda s: replace(s, constraints=(Constraint("bad", "distance", ("p0", "p1"), "width"),)),
        lambda s: replace(s, points=(replace(s.points[0], u=1_000_001),) + s.points[1:]),
    ],
)
def test_invalid_records_never_touch_native_state(monkeypatch, mutation):
    def forbidden():
        pytest.fail("Native state touched before validation")

    monkeypatch.setattr(slvs, "clear_sketch", forbidden)
    with pytest.raises(ValueError):
        solve(mutation(rectangle()))


def test_non_boolean_diagnostic_option_rejects_before_native_state(monkeypatch):
    def forbidden():
        pytest.fail("Native state touched before option validation")

    monkeypatch.setattr(slvs, "clear_sketch", forbidden)
    with pytest.raises(ValueError, match="boolean"):
        solve(rectangle(), diagnose="false")


def test_malformed_drag_reference_has_typed_error():
    from mechanical_cad.sketch_model import SketchError

    with pytest.raises(SketchError):
        drag(rectangle(), [], (0.0, 0.0))


def test_named_dimension_resolution_drives_native_rectangle_and_retains_expression():
    from mechanical_cad.sketch_model import SketchDefinition, resolve_sketch

    data = rectangle(fixed=True).to_dict()
    next(c for c in data["constraints"] if c["id"] == "width")["value"] = "width + allowance"
    definition = SketchDefinition.from_dict(data)
    before = definition.to_json()
    first = solve(resolve_sketch(definition, {"width": 40.0, "allowance": 0.25}))
    second = solve(resolve_sketch(definition, {"width": 55.0, "allowance": 0.25}))
    assert_rectangle(first, 40.25)
    assert_rectangle(second, 55.25)
    assert first.remaining_dof == second.remaining_dof == 0
    assert definition.to_json() == before


@pytest.mark.parametrize("constraint_id", ["axis0", "axis1", "axis2", "join0", "width", "anchor"])
@pytest.mark.parametrize("reverse_refs", [False, True])
def test_exact_redundancy_from_unsolved_seeds_is_reported_without_losing_records(
    constraint_id, reverse_refs
):
    """MCAD-SKETCH-001: duplicate relations must not falsely blame the anchor."""
    sketch = rectangle(fixed=True)
    source = next(c for c in sketch.constraints if c.id == constraint_id)
    duplicate = replace(
        source, id="redundant", refs=tuple(reversed(source.refs)) if reverse_refs else source.refs
    )
    sketch = replace(sketch, constraints=sketch.constraints + (duplicate,))
    before = sketch.to_json()
    result = solve(sketch)
    assert_rectangle(result)
    assert result.status == Status.REDUNDANT_OKAY
    assert result.remaining_dof == 0
    # The lexical representative is compile-order deterministic, not persistent
    # record deletion. "redundant" sorts before "width" in the width case.
    assert result.redundant_constraints == (max(constraint_id, "redundant"),)
    assert result.failed_constraints == ()
    assert result.sketch.constraints == sketch.constraints
    assert sketch.to_json() == before
    assert (
        solve(replace(sketch, constraints=tuple(reversed(sketch.constraints)))).sketch.to_json()
        == result.sketch.to_json()
    )


def test_near_equal_distances_are_not_classified_as_exact_duplicates():
    sketch = rectangle(fixed=True)
    sketch = replace(
        sketch,
        constraints=sketch.constraints
        + (Constraint("near_width", "distance", ("p1", "p0"), 40.00001),),
    )
    result = solve(sketch)
    assert not result.success
    assert result.redundant_constraints == ()
    assert result.sketch is sketch


def test_conflicting_fixed_targets_are_not_classified_as_duplicates():
    sketch = rectangle(fixed=True)
    sketch = replace(
        sketch,
        constraints=sketch.constraints
        + (Constraint("other_anchor", "fixed", ("p0",), target=(1.0, 0.0)),),
    )
    result = solve(sketch)
    assert not result.success
    assert result.redundant_constraints == ()


@pytest.mark.parametrize("join", ["join0", "join1", "join2", "join3"])
def test_reversed_duplicate_does_not_translate_underconstrained_seed_solution(join):
    sketch = rectangle(fixed=False)
    original = solve(sketch)
    relation = next(c for c in sketch.constraints if c.id == join)
    modified = replace(
        sketch,
        constraints=sketch.constraints
        + (replace(relation, id="000copy", refs=tuple(reversed(relation.refs))),),
    )
    duplicated = solve(modified)
    assert original.success and duplicated.success
    assert original.remaining_dof == duplicated.remaining_dof == 2
    assert xy(duplicated.sketch) == xy(original.sketch)
    assert duplicated.sketch.constraints == modified.constraints
    assert duplicated.status == Status.REDUNDANT_OKAY


def test_symmetric_reference_order_does_not_change_native_solution():
    sketch = rectangle(fixed=False)
    reversed_refs = replace(
        sketch,
        constraints=tuple(
            replace(c, refs=tuple(reversed(c.refs))) if c.kind in {"distance", "coincident"} else c
            for c in sketch.constraints
        ),
    )
    assert xy(solve(sketch).sketch) == xy(solve(reversed_refs).sketch)
