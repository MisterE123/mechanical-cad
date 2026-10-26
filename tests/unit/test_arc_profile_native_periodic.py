"""Pure prospective periodic-trim controls, never native qualification evidence.

The rational oracle does not use the implementation's pi, trig or interval
arithmetic. Snapshot4 fingerprints below bind exact original source-R0 inputs;
the historical checkout is neither required nor imported by these tests.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.abc
import inspect
import json
import math
import sys
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from fractions import Fraction as F
from pathlib import Path

import pytest

import mechanical_cad.arc_profile_native_evidence as evidence
import mechanical_cad.arc_profile_native_plan as native
from mechanical_cad.arc_profile_primitives import Dyadic, PrimitiveContext, PrimitiveError
from mechanical_cad.arc_profile_sector_policy import ExactRatio, SectorInputError
from mechanical_cad.arc_profile_sector_source import (
    SectorArc,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
    SourceInputError,
)

ROOT = Path(__file__).resolve().parents[2]
TAU = float.fromhex("0x1.921fb54442d18p+2")
CASES = (
    ("cardinal", (5.0, 0.0), (0.0, 5.0), (0.0, 0.0)),
    ("pythagorean", (3.0, 4.0), (-4.0, 3.0), (0.0, 0.0)),
    ("rounded", (13.0, 29.0), (-29.0, 13.0), (0.0, 0.0)),
    ("nonquadrantal", (5.0, 0.0), (-3.0, 4.0), (0.0, 0.0)),
    ("outward_gap", (5.0, 0.0), (0.0, 5.0 + 0.5e-9), (0.0, 0.0)),
    ("inward_gap", (5.0, 0.0), (0.0, 5.0 - 0.5e-9), (0.0, 0.0)),
    ("seam", (-3.0, -4.0), (4.0, -3.0), (0.0, 0.0)),
    ("semicircle", (5.0, 0.0), (-5.0, 0.0), (0.0, 0.0)),
    ("translated", (1027.0, 15.0), (985.0, -1.0), (1014.0, -14.0)),
    ("cut_above", (-5.0, 2**-40), (3.0, 4.0), (0.0, 0.0)),
    ("cut_below", (-5.0, -(2**-40)), (3.0, 4.0), (0.0, 0.0)),
)
CONTROLS = tuple((case, direction) for case in CASES for direction in ("ccw", "cw"))

# Generated from the immutable revised_pure_snapshot4 source, with native
# imports blocked, using exactly snapshot_values/encode below at heights1,7.25,1000.
SNAPSHOT4 = {
    "cardinal_ccw": "b97c241baa73cd922518862afd510bb4b1b88ff1f93a4e85032e06e29cf85ffa",
    "cardinal_cw": "290eb78c271e09e61593df3fe1d9c19bb2c540c28010f024ea0d08643157658a",
    "pythagorean_ccw": "2ad34e17caa21f30856181317cba41b9028008188dacc1d463749f2578e2ae81",
    "pythagorean_cw": "21c78ca1692cb11acedaac32fe05d06ea4e623b4ef4a695c996ee16282aa27a5",
    "rounded_ccw": "6831ec640ca2d2824be8e18face1b404cffc27bc5d4402c3a4cfed75137b6fb3",
    "rounded_cw": "597a98bd9d7b484bc5d51f58fd6200d5c5e3aef1670d955a892a6e446da5f0f9",
    "nonquadrantal_ccw": "b561098f9f7f8e2f7c2c4d26bbd83eb8243e0bd89acc98de5683bf4e7af531d8",
    "nonquadrantal_cw": "1479fa004cc98f47d7463f88a8ee244a053f3be16216e0e2c8861779eead4541",
    "outward_gap_ccw": "c59eb58f7339eeae3e0381ce5405c298aa90f358cab72418a7a6deb656361f40",
    "outward_gap_cw": "551e2f84c11367b7d734f78cc971304392f77966bc2a56c4f6fbd5b94b51f744",
    "inward_gap_ccw": "1d9e85dde77d4210724306c026f28c7626c56ee865dbbb57a453e429e862b3d2",
    "inward_gap_cw": "5c1bc5d25b943043dbd93d34429029e4f40f002e827ff42394e749b4442f3bc0",
    "seam_ccw": "38faeaaf211d16e30804b1d88e183a9445eb43a3ad0fc7c135c12d0c4ba685af",
    "seam_cw": "fc5a1c6ec3b7d045b0ac0b7338991f25b61cb08354260dd895d27effed1ee1ab",
    "semicircle_ccw": "23fca0528c574ea55aaf380c269bfdfd7047a7e716e786d811376c0cd55ea1e3",
    "semicircle_cw": "23fca0528c574ea55aaf380c269bfdfd7047a7e716e786d811376c0cd55ea1e3",
    "translated_ccw": "7ac68d5fac14968bc9e8469c0fd1ce922a14396d3778cffb2b36d44874270edf",
    "translated_cw": "f1f5a0c518b59a4e6e88462cde1b0a331ca408fc1a1ed046f782401c7c1a7539",
    "cut_above_ccw": "d1d12acf64fd67aba2ebc59ac959f8516cba0e582487269352844a17e2822832",
    "cut_above_cw": "6a6bd970128e332e51894cccfa53b01fe487feed4de1c1d41d96fec695f2f46c",
    "cut_below_ccw": "eda6880ad2b7ce76a22981a64df962fc6872e10695d669ff675e62b05e3508c4",
    "cut_below_cw": "3856ba2acb300d4c18a69fa0931aa3ac44268879704f99a77a7d98f0169feb2a",
}


class NoNativeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"OCP", "OCC", "cadquery", "slvs", "bpy"}:
            raise AssertionError(f"native import forbidden: {fullname}")
        if fullname == "mechanical_cad.kernel_ocp":
            raise AssertionError("the native adapter may only be parsed in these tests")
        return None


@pytest.fixture(autouse=True)
def no_native_imports():
    blocker = NoNativeImports()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


def fraction(value):
    if type(value) is Dyadic:
        return F(value.mantissa) * F(2) ** value.exponent
    if type(value) is ExactRatio:
        return fraction(value.numerator) / fraction(value.denominator)
    return F(value)


def bounds(interval):
    return fraction(interval.lower), fraction(interval.upper)


def source(case=CASES[0], direction="ccw"):
    _, start, end, center = case
    return SectorGeometrySource(
        (SectorPoint("c", *center), SectorPoint("a", *start), SectorPoint("b", *end)),
        (SectorLine("ra", "c", "a"), SectorLine("rb", "c", "b")),
        (SectorArc("arc", "c", "a", "b", direction),),
    )


def fresh_plan(case=CASES[0], direction="ccw", context=None):
    c = native.entry_context() if context is None else context
    return native.prepare_native_geometry(
        source(case, direction), native.NativePlane(), context=c
    ), c


@pytest.fixture(scope="module", params=CONTROLS, ids=lambda item: item[0][0] + "_" + item[1])
def control(request):
    case, direction = request.param
    return case, direction, fresh_plan(case, direction)[0]


@pytest.fixture(scope="module")
def shifted_plan():
    return fresh_plan(CASES[6], "cw")[0]


def machin_pi():
    def atan(q):
        value = sum((F((-1) ** n, (2 * n + 1) * q ** (2 * n + 1)) for n in range(64)), F(0))
        return value, value + F(1, 129 * q**129)

    a, b = atan(5), atan(239)
    return 16 * a[0] - 4 * b[1], 16 * a[1] - 4 * b[0]


PI = machin_pi()


def periodic(parameters):
    c = native.entry_context()
    result = native.classify_sector_geometry(source(), context=c)
    assert result.status == "certified_sector"
    i = native._ContinuationIntervals(c, result.certificate)
    return native._periodic_trim(c, i, parameters), c


def assert_trim_oracle(record):
    a, b = map(F, record.original_parameters)
    ap, bp = map(F, record.canonical_parameters)
    k = record.turn_count
    lower = min(record.original_parameters)
    assert type(k) is int and k == (0 if lower >= 0 else 1 if lower >= -TAU else 2)
    assert record.binary_period.hex() == TAU.hex()
    for old, new in zip(record.original_parameters, record.canonical_parameters, strict=True):
        assert new.hex() == (old + k * TAU).hex()
        assert F(new) == F(float(F(old) + k * F(TAU)))
    lo, hi = sorted((ap, bp))
    assert 0 <= lo < F(TAU) and lo < hi < 12 and hi - lo < F(TAU)
    assert hi - lo < bounds(record.mathematical_period)[0]
    residuals = (ap - a - k * F(TAU), bp - b - k * F(TAU))
    assert tuple(map(fraction, record.addition_residuals)) == residuals
    assert fraction(record.original_span) == b - a
    assert fraction(record.canonical_span) == bp - ap
    assert fraction(record.span_residual) == (bp - ap) - (b - a) == residuals[1] - residuals[0]
    assert (bp > ap) == (b > a)
    period_lo, period_hi = bounds(record.period_residual)
    assert period_lo <= F(TAU) - 2 * PI[1] <= F(TAU) - 2 * PI[0] <= period_hi < 0
    for old, new, residual, phase, error in zip(
        (a, b), (ap, bp), residuals, record.phase_residuals, record.phase_bounds, strict=True
    ):
        plo, phi = bounds(phase)
        assert plo <= new - old - 2 * k * PI[1] <= new - old - 2 * k * PI[0] <= phi
        assert plo <= residual + k * period_lo <= residual + k * period_hi <= phi
        assert fraction(error) == max(abs(plo), abs(phi))
        if k == 0:
            assert (plo, phi, fraction(error), residual) == (0, 0, 0, 0)
    # Whole-trim lineage: one common symbolic integer, at rational interior points.
    for s in (F(0), F(1, 7), F(1, 2), F(6, 7), F(1)):
        shift = ((1 - s) * ap + s * bp) - ((1 - s) * a + s * b)
        assert shift - k * F(TAU) == (1 - s) * residuals[0] + s * residuals[1]
        lo = (1 - s) * bounds(record.phase_residuals[0])[0] + s * bounds(record.phase_residuals[1])[
            0
        ]
        hi = (1 - s) * bounds(record.phase_residuals[0])[1] + s * bounds(record.phase_residuals[1])[
            1
        ]
        assert lo <= shift - 2 * k * PI[1] <= shift - 2 * k * PI[0] <= hi
        assert max(abs(lo), abs(hi)) <= max(map(fraction, record.phase_bounds))


def test_exact_common_turn_residuals_and_whole_trim_lineage(control):
    case, direction, plan = control
    record = plan.periodic_trim
    assert type(record) is native.NativePeriodicTrim
    assert_trim_oracle(record)
    arc = plan.source.incidence.arc
    start = math.atan2(
        float(arc.start[1]) - float(arc.center[1]), float(arc.start[0]) - float(arc.center[0])
    )
    sweep = plan.source.incidence.core_arcs[0][1].sweep_radians
    assert record.original_parameters == (start, start + sweep)
    assert plan.parameters == record.canonical_parameters
    assert plan.increasing_parameters == tuple(sorted(plan.parameters))
    assert arc.direction == direction
    assert dict(plan.vertices) == {"c": (*case[3], 0.0), "a": (*case[1], 0.0), "b": (*case[2], 0.0)}
    theta = bounds(plan.source.area.signed_angle)
    signed_span = fraction(record.canonical_span)
    assert F(plan.radius) * max(abs(signed_span - endpoint) for endpoint in theta) <= F(3, 10**9)
    assert F(plan.radius) * max(map(fraction, record.phase_bounds)) < F(1, 10**9)


def encode(value):
    if is_dataclass(value):
        return {field.name: encode(getattr(value, field.name)) for field in fields(value)}
    if type(value) in (list, tuple):
        return [encode(item) for item in value]
    return value.hex() if type(value) is float else value


def snapshot_values(plan):
    return (
        plan.original_circle_gaps,
        plan.original_cell_radius,
        plan.source_comparison_area,
        plan.source_area_midpoint,
        plan.area_allowance,
        plan.local_scale_squared,
        plan.world_scale,
        plan.source.area.perimeter,
        tuple(
            evidence.mass_limits(plan, height, context=PrimitiveContext())
            for height in (1.0, 7.25, 1000.0)
        ),
    )


def test_exact_snapshot4_source_r0_ea_midpoint_and_mass_inputs(control):
    case, direction, plan = control
    payload = json.dumps(
        encode(snapshot_values(plan)), sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(payload).hexdigest() == SNAPSHOT4[case[0] + "_" + direction]
    source_gaps = [fraction(item.eta) for item in plan.source.gap_enclosures]
    assert fraction(plan.original_cell_radius) == 16 * max(
        source_gaps + [bounds(g)[1] for g in plan.original_circle_gaps]
    )
    assert fraction(plan.final_cell_radius) == 16 * max(
        source_gaps + [bounds(g)[1] for g in plan.circle_gaps]
    )
    assert fraction(plan.original_cell_radius) <= fraction(plan.final_cell_radius) < F(350, 10**9)
    assert all(cell.radius is plan.final_cell_radius for cell in plan.final_source_cells)


def test_new_cell_and_representation_allowance_cannot_widen_source_mass_limits(shifted_plan):
    plan = shifted_plan
    assert fraction(plan.final_cell_radius) > fraction(plan.original_cell_radius)
    baseline = snapshot_values(plan)[2:]
    changed = replace(
        plan,
        final_cell_radius=ExactRatio(Dyadic(349, 0), Dyadic(1_953_125, 9)),
        representation_area_allowance=replace(
            plan.representation_area_allowance, upper=Dyadic(999, 0)
        ),
        native_class_area=replace(plan.native_class_area, upper=Dyadic(999, 0)),
    )
    assert snapshot_values(changed)[2:] == baseline


@pytest.mark.parametrize("case,direction", [(CASES[0], "ccw"), (CASES[0], "cw"), (CASES[6], "cw")])
def test_only_original_two_taylor_calls_feed_checked_transport(monkeypatch, case, direction):
    calls = []
    original = native._Trig.sincos

    def observe(self, parameter):
        result = original(self, parameter)
        calls.append((self.i.context, parameter, result))
        return result

    monkeypatch.setattr(native._Trig, "sincos", observe)
    plan, context = fresh_plan(case, direction)
    assert len(calls) == 2
    assert tuple(item[1] for item in calls) == plan.periodic_trim.original_parameters
    assert all(item[0] is context and -8 <= item[1] <= 8 for item in calls)
    for (_, _, (sine, cosine)), vector, error in zip(
        calls, plan.circle_vectors, plan.periodic_trim.phase_bounds, strict=True
    ):
        for original_component, component in zip((cosine, sine), vector, strict=True):
            lower, upper = bounds(original_component)
            radius, error_bound = F(plan.radius), fraction(error)
            assert bounds(component)[0] <= radius * (lower - error_bound)
            assert bounds(component)[1] >= radius * (upper + error_bound)
    if plan.periodic_trim.turn_count == 0:
        assert plan.circle_gaps == plan.original_circle_gaps
        assert plan.final_cell_radius == plan.original_cell_radius
    if case[0] == "seam":
        assert max(plan.parameters) > 8
    assert plan.resources.operations_end == context.operations <= 200_000


def test_common_shift_does_not_claim_literal_trim_length_equality():
    plan, _ = fresh_plan(CASES[1], "cw")
    record = plan.periodic_trim
    assert record.turn_count == 1
    assert record.addition_residuals[0] != record.addition_residuals[1]
    assert record.original_span != record.canonical_span
    assert record.span_residual == Dyadic(-1, -53)
    assert_trim_oracle(record)


@pytest.mark.parametrize(
    "parameters,turns",
    [
        ((0.0, 1.0), 0),
        ((-0.0, 1.0), 0),
        ((1.0, 0.0), 0),
        ((math.nextafter(0.0, math.inf), 1.0), 0),
        ((-math.ulp(TAU), 1.0), 1),
        ((math.nextafter(-TAU, -math.inf), -4.0), 2),
        ((-TAU, -4.0), 1),
        ((math.nextafter(-TAU, math.inf), -4.0), 1),
        ((math.nextafter(TAU, -math.inf), 7.0), 0),
        ((-8.0, -3.0), 2),
        ((-7.0, -1.0), 2),
        ((-6.7, math.nextafter(12.0, -math.inf) - 2 * TAU), 2),
    ],
)
def test_neighbors_of_predeclared_turn_and_admission_boundaries(parameters, turns):
    record, context = periodic(parameters)
    assert record.turn_count == turns
    assert_trim_oracle(record)
    assert context.operations > 0


@pytest.mark.parametrize(
    "parameters,code",
    [
        ((-math.ulp(0.0), 1.0), "native_canonical_parameter_boundary"),
        ((-0.25 * math.ulp(TAU), 1.0), "native_canonical_parameter_boundary"),
        ((TAU, 7.0), "unsupported_native_periodic_domain"),
        ((math.nextafter(TAU, math.inf), 7.0), "unsupported_native_periodic_domain"),
        ((0.0, 0.0), "native_canonical_parameter_boundary"),
        ((0.0, TAU), "native_full_turn"),
        ((0.0, math.nextafter(TAU, math.inf)), "native_full_turn"),
        ((-7.0, 12.0 - 2 * TAU), "native_canonical_parameter_boundary"),
        ((-7.0, math.nextafter(12.0 - 2 * TAU, -math.inf)), "native_canonical_parameter_boundary"),
        ((math.nextafter(-8.0, -math.inf), -3.0), "unsupported_native_parameter"),
        ((1.0, math.nextafter(8.0, math.inf)), "unsupported_native_parameter"),
    ],
)
def test_canonical_boundary_has_no_second_candidate_or_snap(parameters, code):
    with pytest.raises(native.NativePlanError, match=f"^{code}$"):
        periodic(parameters)


class HostileFloat(float):
    def __float__(self):
        raise AssertionError("no scalar subclass coercion")

    def __lt__(self, other):
        raise AssertionError("no scalar subclass comparison")


class HostileTuple(tuple):
    def __iter__(self):
        raise AssertionError("no container subclass iteration")


@pytest.mark.parametrize(
    "parameters",
    [
        None,
        {},
        [],
        [0.0, 1.0],
        (),
        (0.0,),
        (0.0, 1.0, 2.0),
        True,
        (0, 1.0),
        (False, 1.0),
        ("0", 1.0),
        (F(0), 1.0),
        (math.nan, 1.0),
        (math.inf, 1.0),
        (-math.inf, 1.0),
        (HostileFloat(0), 1.0),
        HostileTuple((0.0, 1.0)),
    ],
)
def test_original_periodic_input_grammar_rejects_without_coercion(parameters):
    with pytest.raises(native.NativePlanError, match="^unsupported_native_parameter$"):
        periodic(parameters)


def test_signed_zero_is_retained_in_original_and_single_addition_binding():
    negative, _ = periodic((-0.0, 1.0))
    positive, _ = periodic((0.0, 1.0))
    assert negative.original_parameters[0].hex() == "-0x0.0p+0"
    assert negative.canonical_parameters[0].hex() == "0x0.0p+0"
    assert negative == positive  # Numeric equality is weaker than diagnostic binding.
    assert encode(negative) != encode(positive)


def test_periodic_record_is_frozen_and_every_witness_is_bound(shifted_plan):
    record = shifted_plan.periodic_trim
    with pytest.raises(FrozenInstanceError):
        record.turn_count = 0
    base = native.plan_bytes(shifted_plan)
    zero = Dyadic(0, 0)
    interval = replace(record.period_residual, lower=zero, upper=zero)
    mutations = {
        "original_parameters": tuple(reversed(record.original_parameters)),
        "canonical_parameters": (
            math.nextafter(record.canonical_parameters[0], math.inf),
            record.canonical_parameters[1],
        ),
        "turn_count": record.turn_count - 1,
        "binary_period": math.nextafter(record.binary_period, math.inf),
        "mathematical_period": interval,
        "addition_residuals": (Dyadic(1, 0), record.addition_residuals[1]),
        "period_residual": interval,
        "phase_residuals": (interval, record.phase_residuals[1]),
        "phase_bounds": (Dyadic(1, 0), record.phase_bounds[1]),
        "original_span": zero,
        "canonical_span": zero,
        "span_residual": Dyadic(1, 0),
    }
    assert set(mutations) == {field.name for field in fields(native.NativePeriodicTrim)}
    encodings = [
        native.plan_bytes(replace(shifted_plan, periodic_trim=replace(record, **{field: value})))
        for field, value in mutations.items()
    ]
    assert len({base, *encodings}) == 1 + len(mutations)


@pytest.mark.parametrize("missing", [field.name for field in fields(native.NativePeriodicTrim)])
def test_missing_periodic_record_slot_is_controlled(shifted_plan, missing):
    incomplete = object.__new__(native.NativePeriodicTrim)
    for field in fields(native.NativePeriodicTrim):
        if field.name != missing:
            object.__setattr__(
                incomplete, field.name, getattr(shifted_plan.periodic_trim, field.name)
            )
    with pytest.raises(SectorInputError, match="^invalid_certificate$"):
        native.plan_bytes(replace(shifted_plan, periodic_trim=incomplete))


def test_periodic_subclass_and_nonfinite_diagnostic_data_are_rejected(shifted_plan):
    class Derived(native.NativePeriodicTrim):
        pass

    record = shifted_plan.periodic_trim
    derived = Derived(**{field.name: getattr(record, field.name) for field in fields(record)})
    with pytest.raises(SectorInputError, match="^invalid_certificate_type$"):
        native.plan_bytes(replace(shifted_plan, periodic_trim=derived))
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(SectorInputError, match="^invalid_certificate_number$"):
            native.plan_bytes(
                replace(shifted_plan, periodic_trim=replace(record, binary_period=value))
            )


@pytest.mark.parametrize(
    "cache", ["periodic_trim", "plan", "parameters", "expected_range", "trig_cache", "source_pi"]
)
def test_public_entry_never_accepts_periodic_or_evaluation_cache(monkeypatch, shifted_plan, cache):
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected keyword must reject before classification")

    monkeypatch.setattr(native, "classify_sector_geometry", forbidden)
    with pytest.raises(TypeError):
        native.prepare_native_geometry(
            source(), native.NativePlane(), **{cache: shifted_plan.periodic_trim}
        )
    with pytest.raises(TypeError):
        native.prepare_native_representation(
            source(), native.NativePlane(), (), **{cache: shifted_plan.periodic_trim}
        )


def test_detached_records_cannot_replace_original_source(shifted_plan):
    for detached in (shifted_plan, shifted_plan.periodic_trim, shifted_plan.source):
        with pytest.raises(SourceInputError, match="^invalid_source$"):
            native.prepare_native_geometry(detached, native.NativePlane())
    assert tuple(inspect.signature(native._periodic_trim).parameters) == ("c", "i", "parameters")


def test_canonical_cells_keep_all_source_and_actual_root_obligations(control):
    case, direction, original = control
    plan, c = fresh_plan(case, direction)
    directions = tuple(
        native.NativeRadialDirection(line.entity_id, native.transform(plan.frame, line.direction))
        for line in plan.lines
    )
    accepted = native._continue_actual_support(plan, directions, c)
    actual = accepted.accepted_support
    assert actual.frozen_cell_radius is plan.final_cell_radius
    assert accepted.periodic_trim is plan.periodic_trim
    assert accepted.original_cell_radius is plan.original_cell_radius
    assert accepted.original_circle_gaps is plan.original_circle_gaps
    assert actual.intended_plan_sha256 == hashlib.sha256(native.plan_bytes(plan)).hexdigest()
    source_count = sum(
        len(disk.circle_exits) + len(disk.radial_exits)
        for disk in plan.source.cells + plan.source.outer_proxies
    )
    source_count += sum(len(roots) for _, roots in plan.source.center_proxy.line_exits)
    selected_count = sum(
        len(disk.circle_exits) + len(disk.radial_exits) for disk in plan.final_source_cells
    )
    intended_count = sum(
        len(item.parameters) for item in plan.radial_disk_roots + plan.center_proxy_roots
    )
    actual_count = sum(
        len(item.parameters) for item in actual.radial_disk_roots + actual.center_proxy_roots
    )
    assert (
        actual.retained_root_count
        == source_count
        + selected_count
        + intended_count
        + actual_count
        + sum(len(line.support_circle_roots.parameters) for line in plan.lines + actual.lines)
        + sum(len(boundary.roots.support.roots) for boundary in plan.source.incidence.boundaries)
        <= 64
    )
    assert actual.retained_root_count == (64 if plan.source.cells else 56)
    assert all(fraction(margin) > 0 for margin in actual.line_collar_margins)
    for record in plan.radial_disk_roots + actual.radial_disk_roots:
        assert record.memberships == ("INTERIOR", "AFTER_END")
        assert bounds(record.parameters[0])[1] < bounds(record.parameters[1])[0]
        for field in (
            "discriminant",
            "denominator",
            "endpoint_inside_margin",
            "circle_root_inside_margin",
            "foreign_ray_exclusion_margin",
            "negative_circle_root_exclusion",
        ):
            assert fraction(getattr(record, field)) > 0
    for record in plan.center_proxy_roots + actual.center_proxy_roots:
        assert record.memberships == ("BEFORE_START", "INTERIOR")
        assert fraction(record.finite_exit_margin) > 0
    assert len(plan.native_circle_exit_memberships) == 4
    assert all(
        positions.count("INTERIOR") == 1 for _, _, positions in plan.native_circle_exit_memberships
    )
    assert snapshot_values(accepted) == snapshot_values(original)
    assert len(native.plan_bytes(accepted)) <= 1024 * 1024
    assert c.operations == actual.resources.operations_end <= c.max_operations == 200_000


@pytest.mark.parametrize("change", ["reverse", "complement"])
def test_exact_circle_membership_rejects_changed_directed_branch(shifted_plan, change):
    c = native.entry_context()
    i = native._ContinuationIntervals(c, shifted_plan.source)
    parameters = shifted_plan.parameters
    if change == "reverse":
        altered = tuple(reversed(parameters))
    else:
        a, b = parameters
        altered = (a, a + math.copysign(TAU - abs(b - a), b - a))
    disks = tuple(
        (disk, shifted_plan.source.area.pi)
        for disk in shifted_plan.final_source_cells + shifted_plan.source.outer_proxies
    )
    with pytest.raises(native.NativePlanError, match="native_circle_membership_changed"):
        native._circle_memberships(c, i, disks, shifted_plan.circle_vectors, altered)


@pytest.mark.parametrize("dimension", [2, 3])
@pytest.mark.parametrize(
    "change",
    ["ulp", "common_plus", "common_minus", "unequal", "reverse", "full_circle", "original"],
)
def test_actual_serialized_range_stays_exact_not_modulo(shifted_plan, dimension, change):
    plan, c = fresh_plan(CASES[6], "cw")
    directions = tuple(
        native.NativeRadialDirection(line.entity_id, native.transform(plan.frame, line.direction))
        for line in plan.lines
    )
    plan = native._continue_actual_support(plan, directions, c)
    record = {
        "kind": "circle",
        "location": (0.0,) * dimension,
        "direction": None,
        "u": (1.0, 0.0) if dimension == 2 else plan.frame.u,
        "v": (0.0, 1.0) if dimension == 2 else plan.frame.v,
        "normal": None if dimension == 2 else plan.frame.normal,
        "radius": plan.radius,
        "range": plan.increasing_parameters,
        "identity_location": True,
    }
    evidence.validate_curve_fields(plan, "arc.arc", record, dimensions=dimension)
    lo, hi = plan.increasing_parameters
    altered = {
        "ulp": (math.nextafter(lo, math.inf), hi),
        "common_plus": (lo + TAU, hi + TAU),
        "common_minus": (lo - TAU, hi - TAU),
        "unequal": (lo, hi + TAU),
        "reverse": (hi, lo),
        "full_circle": (lo, lo + TAU),
        "original": tuple(sorted(plan.periodic_trim.original_parameters)),
    }[change]
    record["range"] = altered
    with pytest.raises(
        native.NativePlanError, match="native_surface_trace_mismatch|native_curve_fields_changed"
    ):
        evidence.validate_curve_fields(plan, "arc.arc", record, dimensions=dimension)


def test_periodic_arithmetic_respects_exact_supplied_budget(shifted_plan):
    required = shifted_plan.resources.operations_end
    c = PrimitiveContext(max_operations=required)
    exact, c = fresh_plan(CASES[6], "cw", c)
    assert c.operations == required == exact.resources.operations_end
    c = PrimitiveContext(max_operations=required - 1)
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        fresh_plan(CASES[6], "cw", c)
    assert c.operations == required - 1


def historical_line_from_direction(node):
    """Invert only the sealed trim input and appended support-record statements."""
    assert node.args.args[-1].arg == "trim_parameter"
    node.args.args.pop()
    changes = (
        (
            "_require(type(trim_parameter) is float and math.isfinite(trim_parameter) "
            'and 1 <= trim_parameter <= 1000, "invalid_native_trim_parameter")',
            None,
        ),
        ("ell = c.coordinate(trim_parameter)", "ell = c.coordinate(length)"),
        ('_require(c._compare(ell, radius) == 0, "native_trim_radius_changed")', None),
        ("support = _support_circle_roots(c, i, entity_id, point_id, a, radius, ell, norm)", None),
        (
            "return NativeLine(entity_id, point_id, direction, length, trim_parameter, "
            "a, error2, gap, root, support)",
            "return NativeLine(entity_id, point_id, direction, length, a, error2, gap, root)",
        ),
    )
    for current, historical in changes:
        expected = ast.dump(ast.parse(current).body[0], include_attributes=False)
        indices = [
            index
            for index, statement in enumerate(node.body)
            if ast.dump(statement, include_attributes=False) == expected
        ]
        assert len(indices) == 1
        index = indices[0]
        if historical is None:
            node.body.pop(index)
        else:
            node.body[index] = ast.parse(historical).body[0]
    return node


@pytest.mark.parametrize(
    "before,after",
    (
        ("a.mantissa > 0 and dot.mantissa > 0", "a.mantissa >= 0 and dot.mantissa > 0"),
        ("c._make(10**18, 0)", "c._make(10**17, 0)"),
        (
            "i._div(i.point(c._mul(radius, part)), norm)",
            "i._mul(i.point(c._mul(radius, part)), norm)",
        ),
        ("i._sub(root[k], i.point(v[k]))", "i._add(root[k], i.point(v[k]))"),
        ("_delta(c, gap.upper)", "_delta(c, gap.lower)"),
        ('"invalid_native_trim_parameter"', '"unapproved_trim_check"'),
    ),
)
def test_radial_inverse_guard_rejects_unrelated_line_proof_changes(before, after):
    source = inspect.getsource(native._line_from_direction)
    assert source.count(before) == 1
    node = ast.parse(source.replace(before, after)).body[0]
    try:
        restored = historical_line_from_direction(node)
    except AssertionError:
        return
    digest = hashlib.sha256(ast.dump(restored, include_attributes=False).encode()).hexdigest()
    assert digest != "536bb352cf133ecff9a9ececd219ed717dfda672015737c89f60260118d9537e"


def test_original_taylor_and_all_branch_membership_leaves_remain_snapshot4_exact():
    expected = {
        "_Trig": "43a3cbc8ce0914728531e97881e2f6bb45ec13d55e02028897ca766535854559",
        "_line_from_direction": "536bb352cf133ecff9a9ececd219ed717dfda672015737c89f60260118d9537e",
        "_radial_disk": "ae93e501a6cbfb101bf836b63dff5fa8acb9f486c16e8a4d2392f0dc017eca2d",
        "_circle_memberships": "20a67a3632f67c89dad941c0e6d22efbb0d5cb31bdd21f731355592593b62a34",
        "_actual_angle": "88959034188359a2b866990475b21a78f04b33920a0d5c59591d0980258c328b",
    }
    tree = ast.parse((ROOT / "src/mechanical_cad/arc_profile_native_plan.py").read_text())
    nodes = {
        node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    nodes["_line_from_direction"] = historical_line_from_direction(nodes["_line_from_direction"])
    # _radial_disk changes only the selected finite parameter's field name.
    radial = nodes["_radial_disk"]
    uses = [
        node
        for node in ast.walk(radial)
        if isinstance(node, ast.Attribute) and node.attr == "trim_parameter"
    ]
    assert len(uses) == 1
    uses[0].attr = "length"
    for name, digest in expected.items():
        assert (
            hashlib.sha256(ast.dump(nodes[name], include_attributes=False).encode()).hexdigest()
            == digest
        )
