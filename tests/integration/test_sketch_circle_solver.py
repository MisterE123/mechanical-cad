"""Real pinned slvs circles, atomic diagnostics and independent output checks."""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

import mechanical_cad.sketch_solver as adapter
from mechanical_cad.errors import CADException
from mechanical_cad.sketch_model import (
    MAX_ACTIVE_SCALARS,
    Circle,
    Constraint,
    Line,
    Plane,
    Point,
    Sketch,
    SketchDefinition,
    SketchError,
    active_scalar_count,
    resolve_sketch,
)
from mechanical_cad.sketch_solver import Status, drag, solve

slvs = pytest.importorskip("slvs")


def circle(*, fixed=False, dimension=True, radius=10, seed=7):
    constraints = (Constraint("radius", "radius", ("circle",), radius),) if dimension else ()
    if fixed:
        constraints += (Constraint("anchor", "fixed", ("center",), target=(3, 4)),)
    return Sketch(
        "circle-sketch",
        (Point("center", 3, 4),),
        (),
        constraints,
        schema_version=2,
        circles=(Circle("circle", "center", seed),),
    )


def assert_circle(report, radius, dof):
    assert report.success, report
    assert report.remaining_dof == dof
    assert report.max_residual <= 1e-7
    assert report.sketch.circles[0].radius == pytest.approx(radius, abs=1e-10)
    assert report.sketch.circles[0].center == "center"
    assert report.sketch.points[0].u == pytest.approx(3)
    assert report.sketch.points[0].v == pytest.approx(4)


@pytest.mark.parametrize(
    "fixed,dimension,dof", [(False, False, 3), (False, True, 2), (True, False, 1), (True, True, 0)]
)
def test_actual_native_circle_degrees_of_freedom_and_atomic_source(fixed, dimension, dof):
    original = circle(fixed=fixed, dimension=dimension)
    before = original.to_json()
    report = solve(original)
    assert_circle(report, 10 if dimension else 7, dof)
    assert report.status == Status.OKAY
    assert report.sketch.constraints == original.constraints
    assert original.to_json() == before
    assert original.circles[0].radius == 7


def test_radius_compiles_to_native_diameter_but_preserves_radius_intent(monkeypatch):
    calls = []
    native = slvs.diameter

    def record(*args, **kwargs):
        calls.append(args)
        return native(*args, **kwargs)

    monkeypatch.setattr(slvs, "diameter", record)
    definition = SketchDefinition.from_dict(circle(fixed=True).to_dict())
    definition = replace(
        definition,
        constraints=tuple(
            replace(c, value="shaft_radius + clearance") if c.kind == "radius" else c
            for c in definition.constraints
        ),
    )
    before = definition.to_json()
    numeric = resolve_sketch(definition, {"shaft_radius": 9.25, "clearance": 0.75})
    report = solve(numeric)
    assert_circle(report, 10, 0)
    assert len(calls) == 1 and calls[0][2] == 20
    assert next(c.value for c in report.sketch.constraints if c.kind == "radius") == 10
    assert definition.to_json() == before
    assert numeric.circles[0].radius == 7


@pytest.mark.parametrize("diagnose", [False, True])
def test_conflicting_radii_are_atomic_with_stable_diagnostics(diagnose):
    original = circle(fixed=True)
    original = replace(
        original,
        constraints=original.constraints + (Constraint("other-radius", "radius", ("circle",), 11),),
    )
    before = original.to_json()
    report = solve(original, diagnose=diagnose)
    assert report.status == Status.INCONSISTENT
    assert not report.success and report.remaining_dof is None
    assert report.max_residual is None
    assert report.sketch is original
    assert report.redundant_constraints == ()
    if diagnose:
        assert report.failed_constraints
        assert set(report.failed_constraints) <= {"radius", "other-radius", "anchor"}
    else:
        assert report.failed_constraints == ()
    assert original.to_json() == before
    assert slvs.solve_sketch(2, True)[0]["dof"] == 0  # Cleared even on failure.


def test_identical_radius_duplicates_are_reported_without_deleting_authored_records():
    original = circle()
    duplicated = replace(
        original,
        constraints=(Constraint("000copy", "radius", ("circle",), 10), *original.constraints),
    )
    report = solve(duplicated)
    assert_circle(report, 10, 2)
    assert report.status == Status.REDUNDANT_OKAY
    assert report.redundant_constraints == ("radius",)
    assert report.sketch.constraints == duplicated.constraints
    assert report.sketch.points == solve(original).sketch.points
    reordered = replace(duplicated, constraints=tuple(reversed(duplicated.constraints)))
    assert solve(reordered).sketch.to_json() == report.sketch.to_json()


def test_equal_current_radius_formulas_remain_separate_intent_when_parameters_diverge():
    raw = circle(fixed=True).to_dict()
    definition = SketchDefinition.from_dict(raw)
    definition = replace(
        definition,
        constraints=(
            Constraint("first-radius", "radius", ("circle",), "shaft_radius + clearance"),
            Constraint("second-radius", "radius", ("circle",), "other_radius"),
            Constraint("anchor", "fixed", ("center",), target=(3, 4)),
        ),
    )
    before = definition.to_json()
    equal = solve(
        resolve_sketch(definition, {"shaft_radius": 9, "clearance": 1, "other_radius": 10})
    )
    assert_circle(equal, 10, 0)
    assert equal.redundant_constraints == ("second-radius",)
    divergent_input = resolve_sketch(
        definition, {"shaft_radius": 9, "clearance": 1, "other_radius": 11}
    )
    divergent = solve(divergent_input)
    assert not divergent.success and divergent.redundant_constraints == ()
    assert divergent.sketch is divergent_input
    assert definition.to_json() == before
    assert len(divergent.sketch.constraints) == 3


def test_nearly_equal_radii_are_never_exact_duplicates():
    original = circle(fixed=True)
    original = replace(
        original,
        constraints=original.constraints
        + (Constraint("near-radius", "radius", ("circle",), 10.00001),),
    )
    report = solve(original)
    assert not report.success
    assert report.redundant_constraints == ()
    assert report.sketch is original


def test_radius_edit_retains_center_entity_dimension_ids_and_authoritative_seed():
    original = circle(fixed=True)
    before = original.to_json()
    changed = replace(
        original,
        constraints=tuple(
            replace(c, value=24.75) if c.kind == "radius" else c for c in original.constraints
        ),
    )
    report = solve(changed)
    assert_circle(report, 24.75, 0)
    assert report.sketch.circles[0].id == original.circles[0].id
    assert [c.id for c in report.sketch.constraints] == [c.id for c in original.constraints]
    assert original.to_json() == before
    assert changed.circles[0].radius == 7


def test_all_entity_families_compile_stably_after_reordering():
    original = replace(
        circle(fixed=True),
        points=(Point("other-center", 9, 10), *circle().points),
        lines=(Line("line", "center", "other-center"),),
        circles=(Circle("other-circle", "other-center", 2), *circle().circles),
        constraints=(
            Constraint("other-radius", "radius", ("other-circle",), 3),
            *circle(fixed=True).constraints,
        ),
    )
    reordered = replace(
        original,
        points=tuple(reversed(original.points)),
        lines=tuple(reversed(original.lines)),
        circles=tuple(reversed(original.circles)),
        constraints=tuple(reversed(original.constraints)),
    )
    reports = [solve(s) for s in (original, reordered, original)]
    assert all(report.success and report.remaining_dof == 2 for report in reports)
    assert reports[0].sketch.to_json() == reports[1].sketch.to_json() == reports[2].sketch.to_json()
    assert (
        solve(Sketch.from_json(reports[0].sketch.to_json())).sketch.to_json()
        == reports[0].sketch.to_json()
    )


@pytest.mark.parametrize(
    "plane",
    [
        Plane((3, 4, 5), (math.sqrt(0.5), math.sqrt(0.5), 0, 0)),
        Plane((1e6, -1e6, 1e6), (1 + 1e-10, 0, 0, 0)),
    ],
)
def test_circle_solve_preserves_nonxy_far_origin_and_accepted_near_unit_workplane(plane):
    original = replace(circle(fixed=True), plane=plane)
    report = solve(original)
    assert_circle(report, 10, 0)
    assert report.sketch.plane is original.plane


@pytest.mark.parametrize("seed,radius", [(1e-6, 1e-6), (1e6, 1e6), (1e-6, 1e6), (1e6, 1e-6)])
def test_radius_domain_endpoint_seeds_and_targets_never_publish_invalid_results(seed, radius):
    original = circle(fixed=True, seed=seed, radius=radius)
    report = solve(original)
    if report.success:
        assert_circle(report, radius, 0)
        assert 1e-6 <= report.sketch.circles[0].radius <= 1e6
    else:
        # Accepted input bounds are not a native convergence promise.
        assert report.sketch is original
        assert report.remaining_dof is None
    assert original.circles[0].radius == seed


def test_extra_unreferenced_points_still_contribute_real_dof():
    original = replace(circle(), points=(*circle().points, Point("unused", 100, 200)))
    report = solve(original)
    assert report.success and report.remaining_dof == 4
    assert len(report.sketch.points) == 2
    assert active_scalar_count(original) == 5


@pytest.mark.parametrize(
    "value", [0, -7, 1e-7, 1e6 + 1, True, float("nan"), float("inf"), "radius"]
)
def test_invalid_circle_seed_rejects_before_native_loading(monkeypatch, value):
    monkeypatch.setattr(adapter, "_load_backend", lambda: pytest.fail("Native backend touched"))
    with pytest.raises(SketchError):
        solve(circle(seed=value))


def test_aggregate_scalar_overflow_rejects_before_native_loading(monkeypatch):
    monkeypatch.setattr(adapter, "_load_backend", lambda: pytest.fail("Native backend touched"))
    original = replace(
        circle(),
        points=(Point("center", 3, 4), *(Point(f"p{i}", 0, 0) for i in range(255))),
    )
    assert active_scalar_count(original) == MAX_ACTIVE_SCALARS + 1
    with pytest.raises(SketchError) as error:
        solve(original)
    assert error.value.code == "resource_limit"


def override_native_radius(monkeypatch, value):
    add_distance, get_value = slvs.add_distance, slvs.get_param_value
    parameters = set()

    def record(*args, **kwargs):
        result = add_distance(*args, **kwargs)
        parameters.add(result["param"][0])
        return result

    def replace_radius(parameter):
        return value if parameter in parameters else get_value(parameter)

    monkeypatch.setattr(slvs, "add_distance", record)
    monkeypatch.setattr(slvs, "get_param_value", replace_radius)


@pytest.mark.parametrize("value", [-10, 0, 1e-7, 1e6 + 1, float("nan"), float("inf"), True])
def test_native_success_with_invalid_radius_is_atomic_failure_without_abs_repair(
    monkeypatch, value
):
    original = circle(fixed=True)
    override_native_radius(monkeypatch, value)
    report = solve(original)
    assert report.status == Status.DIDNT_CONVERGE
    assert report.sketch is original
    assert report.remaining_dof is None
    assert report.max_residual is None
    assert slvs.solve_sketch(2, True)[0]["dof"] == 0


def test_independent_radius_residual_rejects_native_false_positive_in_radius_mm(monkeypatch):
    original = circle(fixed=True)
    override_native_radius(monkeypatch, 10.000001)
    report = solve(original)
    assert report.status == Status.DIDNT_CONVERGE
    assert report.sketch is original and report.remaining_dof is None
    assert report.max_residual == pytest.approx(1e-6)


def test_radius_residual_tolerance_is_not_accidentally_doubled_to_native_diameter(monkeypatch):
    original = circle(fixed=True)
    override_native_radius(monkeypatch, 10 + 0.75e-7)
    report = solve(original)
    assert report.success and report.remaining_dof == 0
    assert report.max_residual == pytest.approx(0.75e-7)


@pytest.mark.parametrize("dof", [-1, 4, 512, True, 3.0, None])
def test_successful_native_dof_must_fit_the_actual_candidate_scalar_ceiling(monkeypatch, dof):
    native = slvs.solve_sketch

    def replaced(group, diagnose):
        result = native(group, diagnose)
        if diagnose:
            info, failed = result
            return info | {"dof": dof}, failed
        return result | {"dof": dof}

    original = circle(dimension=False)
    monkeypatch.setattr(slvs, "solve_sketch", replaced)
    report = solve(original)
    assert report.status == Status.DIDNT_CONVERGE
    assert report.remaining_dof is None and report.sketch is original


def test_native_exception_still_cleans_up_and_does_not_mutate_input(monkeypatch):
    original = circle()
    before = original.to_json()
    native = slvs.diameter

    def fail(*args):
        raise RuntimeError("native failure")

    monkeypatch.setattr(slvs, "diameter", fail)
    with pytest.raises(RuntimeError, match="native failure"):
        solve(original)
    assert original.to_json() == before
    assert slvs.solve_sketch(2, True)[0]["dof"] == 0
    monkeypatch.setattr(slvs, "diameter", native)
    assert_circle(solve(original), 10, 2)


def test_concurrent_circle_solves_have_isolated_radii_and_actual_dof():
    values = list(range(2, 18))
    with ThreadPoolExecutor(max_workers=4) as pool:
        reports = list(pool.map(lambda radius: solve(circle(fixed=True, radius=radius)), values))
    for radius, report in zip(values, reports, strict=True):
        assert_circle(report, radius, 0)


def test_center_hard_target_drag_preserves_radius_and_restores_native_dof():
    original = circle()
    report = drag(original, "center", (12, 15))
    assert report.success and report.remaining_dof == 2
    assert report.sketch.points[0] == Point("center", 12, 15)
    assert report.sketch.circles[0].radius == 10
    assert report.sketch.constraints == original.constraints
    assert original.points[0] == Point("center", 3, 4)


@pytest.mark.parametrize("collision", ["circle", "plane"])
def test_drag_temporary_id_cannot_collide_with_circle_or_plane_identity(collision):
    original = circle()
    if collision == "circle":
        original = replace(original, circles=(Circle("drag-trial", "center", 7),), constraints=())
    else:
        original = replace(original, plane=replace(original.plane, id="drag-trial"))
    report = drag(original, "center", (12, 15))
    assert report.success
    assert report.remaining_dof == (3 if collision == "circle" else 2)
    assert report.sketch.constraints == original.constraints


def test_unreachable_fixed_center_drag_is_atomic_with_drag_diagnostic():
    original = circle(fixed=True)
    report = drag(original, "center", (12, 15))
    assert not report.success and report.sketch is original
    assert report.remaining_dof is None and "@drag" in report.failed_constraints


def test_missing_or_wrong_solver_stays_actionable_only_at_solve(monkeypatch):
    original = circle()
    assert Sketch.from_json(original.to_json()).to_json() == original.to_json()

    def missing(_):
        raise ImportError("missing optional native solver")

    monkeypatch.setattr(adapter, "import_module", missing)
    with pytest.raises(CADException) as error:
        solve(original)
    assert error.value.code == "solver_unavailable"
    monkeypatch.setattr(adapter, "import_module", lambda _: slvs)
    monkeypatch.setattr(adapter, "version", lambda _: "3.3")
    with pytest.raises(CADException) as error:
        solve(original)
    assert error.value.code == "solver_version"


def test_explicit_line_only_migration_preserves_native_compilation_order(monkeypatch):
    original = Sketch(
        "line",
        (Point("b", 8, 1), Point("a", 0, 0)),
        (Line("line", "a", "b"),),
        (
            Constraint("distance", "distance", ("a", "b"), 10),
            Constraint("axis", "horizontal", ("line",)),
            Constraint("anchor", "fixed", ("a",), target=(0, 0)),
        ),
    )
    log = []
    names = (
        "add_point_3d",
        "add_normal_3d",
        "add_workplane",
        "add_point_2d",
        "add_line_2d",
        "add_distance",
        "add_circle",
        "coincident",
        "horizontal",
        "vertical",
        "distance",
        "diameter",
    )
    for name in names:
        native = getattr(slvs, name)

        def trace(*args, _name=name, _native=native, **kwargs):
            log.append((_name, repr(args), repr(kwargs)))
            return _native(*args, **kwargs)

        monkeypatch.setattr(slvs, name, trace)
    legacy = solve(original)
    legacy_calls = list(log)
    log.clear()
    migrated = solve(original.migrate_to_v2())
    assert legacy.success and migrated.success
    assert log == legacy_calls
    assert legacy.sketch.points == migrated.sketch.points
    assert legacy.remaining_dof == migrated.remaining_dof == 0
