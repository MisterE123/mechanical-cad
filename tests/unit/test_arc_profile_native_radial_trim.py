"""Native-free canonical-radius trim proofs and detached negative controls.

Synthetic directions and observations never claim native construction success.
The rational oracle classifies radicals without sqrt or epsilon; the kernel is
parsed only. Tests start no subprocess and create no native object.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.abc
import inspect
import json
import math
import sys
from dataclasses import fields, is_dataclass, replace
from fractions import Fraction as F
from pathlib import Path

import pytest

import mechanical_cad.arc_profile_native_evidence as evidence
import mechanical_cad.arc_profile_native_plan as native
from mechanical_cad.arc_profile_intervals import IntervalContext
from mechanical_cad.arc_profile_primitives import Dyadic, PrimitiveContext, PrimitiveError
from mechanical_cad.arc_profile_sector_policy import ExactRatio, classify_sector_geometry
from mechanical_cad.arc_profile_sector_source import (
    SectorArc,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
    SourceInputError,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = (
    ("cardinal", (5.0, 0.0), (0.0, 5.0)),
    ("pythagorean", (3.0, 4.0), (-4.0, 3.0)),
    ("rounded", (13.0, 29.0), (-29.0, 13.0)),
    ("outward_gap", (5.0, 0.0), (0.0, 5.0 + 0.5e-9)),
    ("inward_gap", (5.0, 0.0), (0.0, 5.0 - 0.5e-9)),
)


class NoNativeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"OCP", "OCC", "cadquery", "slvs", "bpy", "bmesh"}:
            raise AssertionError(f"native import forbidden: {fullname}")
        if fullname == "mechanical_cad.kernel_ocp":
            raise AssertionError("native adapter is parsed, never imported")
        return None


@pytest.fixture(autouse=True)
def no_native_imports():
    blocker = NoNativeImports()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


def source(case=CASES[0], direction="ccw"):
    _, start, end = case
    return SectorGeometrySource(
        (SectorPoint("c", 0.0, 0.0), SectorPoint("a", *start), SectorPoint("b", *end)),
        (SectorLine("ra", "c", "a"), SectorLine("rb", "c", "b")),
        (SectorArc("arc", "c", "a", "b", direction),),
    )


def fraction(value):
    if type(value) is Dyadic:
        return F(value.mantissa) * F(2) ** value.exponent
    if type(value) is ExactRatio:
        return fraction(value.numerator) / fraction(value.denominator)
    return F(value)


def sign(value):
    return (value > 0) - (value < 0)


def radical_sign(p, q, h):
    """Exact sign of p+q*sqrt(h), using rational squares only."""
    assert h >= 0
    if q == 0 or h == 0:
        return sign(p)
    if p == 0 or sign(p) == sign(q):
        return sign(q)
    return sign(q) * sign(q * q * h - p * p)


def encloses(interval, p, q, h):
    lo, hi = fraction(interval.lower), fraction(interval.upper)
    assert lo <= hi
    assert radical_sign(p - lo, q, h) >= 0
    assert radical_sign(p - hi, q, h) <= 0


def dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def observations(plan, normalize=False):
    result = []
    for line in plan.lines:
        direction = line.direction
        if normalize:
            norm = math.sqrt(sum(x * x for x in direction))
            direction = tuple(x / norm for x in direction)
        result.append(
            native.NativeRadialDirection(line.entity_id, native.transform(plan.frame, direction))
        )
    return tuple(result)


def prepare(case=CASES[0], direction="ccw", normalize=False):
    c = native.entry_context()
    plan = native.prepare_native_geometry(source(case, direction), native.NativePlane(), context=c)
    accepted = native._continue_actual_support(plan, observations(plan, normalize), c)
    return plan, accepted, c


@pytest.fixture(scope="module", params=CASES, ids=lambda case: case[0])
def prepared(request):
    return request.param, *prepare(request.param)


@pytest.fixture(scope="module")
def cardinal():
    return prepare()


@pytest.fixture(scope="module")
def outward():
    return prepare(CASES[3])


def assert_support_roots(line, radius):
    roots = line.support_circle_roots
    a, r, t = fraction(line.squared_norm), F(radius), F(line.trim_parameter)
    assert roots.line_id == line.entity_id and roots.point_id == line.point_id
    assert fraction(roots.squared_norm) == fraction(roots.a) == a > 0
    assert fraction(roots.radius) == fraction(roots.trim_parameter) == t == r > 0
    assert fraction(roots.b) == 0
    assert fraction(roots.c) == -r * r
    assert fraction(roots.discriminant) == 4 * a * r * r > 0
    assert fraction(roots.norm_difference) == a - 1
    assert roots.multiplicities == (1, 1)
    position = "INTERIOR" if a > 1 else "AFTER_END" if a < 1 else "END"
    assert roots.memberships == ("BEFORE_START", position)
    assert len(roots.parameters) == 2
    for branch, interval in zip((-1, 1), roots.parameters, strict=True):
        p, q, h = F(0), branch * r / a, a
        assert a * (p * p + q * q * h) - r * r == 0
        assert (2 * a * p) * q == 0
        encloses(interval, p, q, h)
        assert radical_sign(p, q, h) == branch
        assert radical_sign(p - t, q, h) == (-1 if branch < 0 else -sign(a - 1))
    assert fraction(roots.parameters[0].upper) < 0 < fraction(roots.parameters[1].lower)
    s = sign(a - 1)
    encloses(roots.endpoint_circle_gap, -s * r, s * r, a)
    assert fraction(roots.endpoint_circle_gap.lower) >= 0
    if a != 1:
        assert fraction(roots.endpoint_circle_gap.upper) > 0


def test_both_intended_and_actual_support_root_ledgers_have_exact_oracles(prepared):
    _, plan, accepted, _ = prepared
    for line in plan.lines + accepted.accepted_support.lines:
        assert_support_roots(line, plan.radius)
    # Arc membership stays a separate complete witness; support classification
    # above is deliberately not a claim about a directed finite arc.
    assert plan.native_circle_exit_memberships
    assert all(len(membership) == 2 for _, _, membership in plan.native_circle_exit_memberships)


@pytest.mark.parametrize("exponent", [53, 100, 1000])
@pytest.mark.parametrize("side,position", [(-1, "AFTER_END"), (0, "END"), (1, "INTERIOR")])
def test_exact_norm_classification_does_not_use_rounded_sqrt(exponent, side, position):
    c = native.entry_context()
    i = IntervalContext(c, 64)
    a = Dyadic(1, 0) if side == 0 else Dyadic((1 << exponent) + side, -exponent)
    radius = Dyadic(5, 0)
    norm = c.sqrt_enclosure(a, 64)
    roots = native._support_circle_roots(c, i, "ray", "point", a, radius, radius, norm)
    line = type(
        "OracleLine",
        (),
        {
            "entity_id": "ray",
            "point_id": "point",
            "squared_norm": a,
            "trim_parameter": 5.0,
            "support_circle_roots": roots,
        },
    )()
    assert_support_roots(line, 5.0)
    assert roots.memberships[1] == position
    if side and exponent >= 100:
        assert float(fraction(a)) == 1.0
        assert fraction(roots.parameters[1].lower) <= 5 <= fraction(roots.parameters[1].upper)


@pytest.mark.parametrize("side", [-1, 1])
def test_real_binary64_directions_retain_near_unit_classification(side):
    x = math.nextafter(1.0, 0.0)
    y = 2**-26 if side > 0 else math.nextafter(2**-26, 0.0)
    case = ("near_unit", (x, y), (-y, x))
    plan, accepted, _ = prepare(case)
    for line in plan.lines + accepted.accepted_support.lines:
        a = dot(tuple(map(F, line.direction)), tuple(map(F, line.direction)))
        assert sign(a - 1) == side and 0 < abs(a - 1) < F(1, 2**100)
        assert_support_roots(line, plan.radius)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case[0])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("quaternion", [(1.0, 0.0, 0.0, 0.0), (0.5, 0.5, 0.5, 0.5)])
def test_complete_one_normalization_path_preserves_intent_and_frozen_cells(
    case, direction, quaternion
):
    c = native.entry_context()
    plan = native.prepare_native_geometry(
        source(case, direction), native.NativePlane(quaternion=quaternion), context=c
    )
    before = native.plan_bytes(plan)
    records = observations(plan, normalize=True)
    result = native._continue_actual_support(plan, records, c)
    actual = result.accepted_support
    assert native.plan_bytes(plan) == before
    assert actual.intended_plan_sha256 == hashlib.sha256(before).hexdigest()
    assert actual.directions is records
    assert actual.frozen_cell_radius is plan.final_cell_radius
    for name in (
        "source",
        "plane",
        "frame",
        "center",
        "vertices",
        "radius",
        "parameters",
        "increasing_parameters",
        "lines",
        "circle_vectors",
        "circle_gaps",
        "final_cell_radius",
        "final_source_cells",
        "periodic_trim",
        "original_circle_gaps",
        "original_cell_radius",
        "source_comparison_area",
        "source_area_midpoint",
        "area_allowance",
        "local_scale_squared",
        "world_scale",
    ):
        assert getattr(result, name) is getattr(plan, name)
    gaps = [fraction(item.eta) for item in plan.source.gap_enclosures]
    assert fraction(plan.original_cell_radius) == 16 * max(
        gaps + [fraction(g.upper) for g in plan.original_circle_gaps]
    )
    assert fraction(plan.final_cell_radius) == 16 * max(
        gaps + [fraction(g.upper) for g in plan.circle_gaps]
    )
    assert all(cell.radius is plan.final_cell_radius for cell in plan.final_source_cells)
    assert all(fraction(margin) > 0 for margin in actual.line_collar_margins)
    assert actual.resources.operations_start == plan.resources.operations_end
    assert actual.resources.operations_end == c.operations <= 200_000
    assert len(native.plan_bytes(result)) <= 1_048_576
    for line, intended in zip(actual.lines, plan.lines, strict=True):
        assert line.length == intended.length
        assert line.trim_parameter == intended.trim_parameter == plan.radius
        assert_support_roots(line, plan.radius)


def test_normalization_divisor_and_finite_trim_are_distinct(prepared):
    case, plan, accepted, _ = prepared
    for intended, actual, endpoint in zip(
        plan.lines, accepted.accepted_support.lines, case[1:], strict=True
    ):
        h = tuple(float(value) for value in endpoint)
        divisor = math.hypot(*h)
        assert type(intended.length) is type(actual.length) is float
        assert type(intended.trim_parameter) is type(actual.trim_parameter) is float
        assert intended.length == actual.length == divisor
        assert intended.direction == tuple(value / divisor for value in h)
        assert intended.trim_parameter == actual.trim_parameter == plan.radius
        for line in (intended, actual):
            d, v = tuple(map(F, line.direction)), tuple(map(F, endpoint))
            error = tuple(F(line.trim_parameter) * x - y for x, y in zip(d, v, strict=True))
            assert fraction(line.affine_error_squared) == dot(error, error) <= F(1, 10**18)
            a, r = dot(d, d), F(plan.radius)
            for interval, component in zip(line.root_vector, d, strict=True):
                encloses(interval, 0, r * component / a, a)
            lower, upper = fraction(line.root_gap.lower), fraction(line.root_gap.upper)
            constant, coefficient = r * r + dot(v, v), -2 * r * dot(d, v) / a
            assert 0 <= lower <= upper <= F(1, 10**9)
            assert radical_sign(constant - lower * lower, coefficient, a) >= 0
            assert radical_sign(constant - upper * upper, coefficient, a) <= 0
            for s in (F(0), F(1, 7), F(1, 2), F(1)):
                assert dot(tuple(s * x for x in error), tuple(s * x for x in error)) <= dot(
                    error, error
                )
    if case[0] in {"outward_gap", "inward_gap"}:
        assert plan.lines[1].length != plan.lines[1].trim_parameter
        assert plan.lines[1].support_circle_roots.memberships == ("BEFORE_START", "END")
        old = plan.source.incidence.boundaries[1].roots.support.roots[1].position
        assert old == ("INTERIOR" if case[0] == "outward_gap" else "AFTER_END")
        assert fraction(plan.lines[1].affine_error_squared) > 0


@pytest.mark.parametrize("case", CASES[3:], ids=lambda case: case[0])
def test_dividing_authored_ray_by_radius_is_rejected_by_fresh_boundary(case):
    intended, _, _ = prepare(case)
    wrong = tuple(
        native.NativeRadialDirection(
            line.entity_id, (*tuple(x / intended.radius for x in endpoint), 0.0)
        )
        for line, endpoint in zip(intended.lines, case[1:], strict=True)
    )
    assert wrong[1].direction != observations(intended)[1].direction
    with pytest.raises(native.NativePlanError, match="^native_direction_envelope_exceeded$"):
        native.prepare_native_representation(source(case), native.NativePlane(), wrong)


def test_finite_disk_and_center_proofs_use_frozen_radius_trim(prepared):
    case, plan, accepted, _ = prepared
    rays = dict(zip(("a", "b"), (tuple(map(F, p)) for p in case[1:]), strict=True))
    for lines, radial, center in (
        (plan.lines, plan.radial_disk_roots, plan.center_proxy_roots),
        (
            accepted.accepted_support.lines,
            accepted.accepted_support.radial_disk_roots,
            accepted.accepted_support.center_proxy_roots,
        ),
    ):
        by_id = {line.entity_id: line for line in lines}
        for roots in radial:
            line = by_id[roots.line_id]
            d, v, t = tuple(map(F, line.direction)), rays[roots.point_id], F(line.trim_parameter)
            n, k = fraction(roots.radius.numerator), fraction(roots.radius.denominator)
            a, b, constant = dot(d, d) * k * k, -2 * dot(d, v) * k * k, dot(v, v) * k * k - n * n
            disc, denominator = b * b - 4 * a * constant, 2 * a
            assert tuple(map(fraction, (roots.a, roots.b, roots.c))) == (a, b, constant)
            assert fraction(roots.discriminant) == disc > 0
            assert fraction(roots.denominator) == denominator > 0
            assert roots.memberships == ("INTERIOR", "AFTER_END")
            for branch, interval, end_sign in zip((-1, 1), roots.parameters, (-1, 1), strict=True):
                p, q = -b / denominator, F(branch) / denominator
                assert a * (p * p + q * q * disc) + b * p + constant == 0
                assert (2 * a * p + b) * q == 0
                encloses(interval, p, q, disc)
                assert radical_sign(p, q, disc) == 1
                assert radical_sign(p - t, q, disc) == end_sign
            assert (
                fraction(roots.endpoint_inside_margin)
                == n * n - k * k * fraction(line.affine_error_squared)
                > 0
            )
            r = F(plan.radius)
            q = (r * r + dot(v, v)) * k * k - n * n
            j = 2 * r * dot(d, v) * k * k
            assert q > 0 and j > 0
            assert fraction(roots.circle_root_inside_margin) == j * j - q * q * dot(d, d) > 0
            assert fraction(roots.negative_circle_root_exclusion) == q
            other = next(item for item in lines if item.entity_id != line.entity_id)
            other_d = tuple(map(F, other.direction))
            assert (
                fraction(roots.foreign_ray_exclusion_margin)
                == constant * dot(other_d, other_d) - max(F(0), dot(other_d, v)) ** 2 * k * k
                > 0
            )
        for roots in center:
            line = by_id[roots.line_id]
            a, b, t = fraction(roots.squared_norm), fraction(roots.radius), F(line.trim_parameter)
            assert roots.memberships == ("BEFORE_START", "INTERIOR") and roots.multiplicities == (
                1,
                1,
            )
            for branch, interval in zip((-1, 1), roots.parameters, strict=True):
                encloses(interval, 0, F(branch), b * b / a)
            n, k = fraction(roots.radius.numerator), fraction(roots.radius.denominator)
            assert fraction(roots.finite_exit_margin) == a * t * t * k * k - n * n > 0
    assert accepted.accepted_support.frozen_cell_radius is plan.final_cell_radius
    assert accepted.final_source_cells is plan.final_source_cells
    assert accepted.source is plan.source


def test_source_valid_geometry_can_fail_actual_delta_even_inside_direction_envelope():
    case = ("near_delta", (1000.0, 0.0), (0.0, 1000.0 - 1e-9))
    value = source(case)
    certified = classify_sector_geometry(value)
    assert certified.status == "certified_sector"
    intended = native.prepare_native_geometry(value, native.NativePlane())
    records = observations(intended)
    first, second = records
    changed = 1.0 + 2**-50
    assert F(changed) - F(second.direction[1]) == F(1, 2**50)
    second = replace(second, direction=(0.0, changed, 0.0))
    assert (F(intended.radius) * F(changed) - F(case[2][1])) ** 2 > F(1, 10**18)
    with pytest.raises(native.NativePlanError, match="^native_whole_trace_displacement$"):
        native.prepare_native_representation(value, native.NativePlane(), (first, second))


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("before_disk", "native_disk_finite_membership"),
        ("after_disk", "native_disk_finite_membership"),
        ("outside_cell", "native_endpoint_outside_frozen_cell"),
    ],
)
def test_disk_gate_recomputes_finite_order_and_unchanged_cell(cardinal, mutation, code):
    plan, _, _ = cardinal
    c = native.entry_context()
    i = native._ContinuationIntervals(c, plan.source)
    line, other = plan.lines
    if mutation == "outside_cell":
        line = replace(line, affine_error_squared=Dyadic(1, 0))
    else:
        line = replace(line, trim_parameter=0.0 if mutation == "before_disk" else 6.0)
    ray = c.vector(plan.source.incidence.arc.center, plan.source.incidence.arc.start)
    with pytest.raises(native.NativePlanError, match=f"^{code}$"):
        native._radial_disk(
            c,
            i,
            line,
            other,
            ray,
            c.coordinate(plan.radius),
            plan.final_cell_radius,
            "final_common_cell",
        )


@pytest.mark.parametrize(
    "mutation,code", [("exit", "native_center_proxy_no_exit"), ("collar", "native_line_collar")]
)
def test_center_gate_recomputes_finite_exit_and_collar(cardinal, mutation, code):
    plan, _, _ = cardinal
    c = native.entry_context()
    i = native._ContinuationIntervals(c, plan.source)
    line = replace(
        plan.lines[0],
        **(
            {"trim_parameter": 0.0}
            if mutation == "exit"
            else {"affine_error_squared": Dyadic(1, -20)}
        ),
    )
    with pytest.raises(native.NativePlanError, match=f"^{code}$"):
        native._actual_center_roots(c, i, (line, plan.lines[1]), plan.source.center_proxy.radius)


def test_full_structural_counts_include_source_and_both_native_ledgers(prepared):
    _, plan, accepted, _ = prepared
    source_roots = sum(
        len(ledger.roots.support.roots) for ledger in plan.source.incidence.boundaries
    )
    assert source_roots == 4
    source_auxiliary = sum(
        len(d.circle_exits) + len(d.radial_exits)
        for d in plan.source.cells + plan.source.outer_proxies + plan.final_source_cells
    )
    source_auxiliary += sum(len(roots) for _, roots in plan.source.center_proxy.line_exits)
    for ledger in plan.source.incidence.boundaries:
        assert all(
            wrapper.support is root
            for wrapper, root in zip(ledger.roots.roots, ledger.roots.support.roots, strict=True)
        )
    intended = sum(
        len(item.parameters) for item in plan.radial_disk_roots + plan.center_proxy_roots
    )
    intended += sum(len(line.support_circle_roots.parameters) for line in plan.lines)
    actual = accepted.accepted_support
    actual_count = sum(
        len(item.parameters) for item in actual.radial_disk_roots + actual.center_proxy_roots
    )
    actual_count += sum(len(line.support_circle_roots.parameters) for line in actual.lines)
    assert intended == actual_count == 16
    prefix = (source_auxiliary + intended, 4, source_auxiliary + intended + 4)
    full = (prefix[0] + actual_count, 4, prefix[2] + actual_count)
    assert native.root_counts(plan) == prefix
    assert native.root_counts(accepted) == full
    assert (
        native.root_counts(plan, actual.radial_disk_roots, actual.center_proxy_roots, actual.lines)
        == full
    )
    assert native.retained_root_count(plan) == prefix[2]
    assert native.retained_root_count(accepted) == full[2]
    assert (
        plan.auxiliary_root_count,
        plan.source_support_root_count,
        plan.retained_root_count,
    ) == prefix
    assert (
        actual.auxiliary_root_count,
        actual.source_support_root_count,
        actual.retained_root_count,
    ) == full
    assert full == ((60, 4, 64) if plan.source.cells else (52, 4, 56))


def test_full_structural_65_rejects_without_deduplicating_values(outward):
    plan, accepted, _ = outward
    actual = accepted.accepted_support
    assert native.retained_root_count(accepted) == 64
    roots = actual.lines[0].support_circle_roots
    extra = replace(roots, parameters=roots.parameters + roots.parameters[:1])
    lines = (replace(actual.lines[0], support_circle_roots=extra), actual.lines[1])
    with pytest.raises(native.NativePlanError, match="^auxiliary_root_limit$"):
        native.retained_root_count(plan, actual.radial_disk_roots, actual.center_proxy_roots, lines)


def test_reported_counts_are_rederived_rather_than_trusted(outward):
    _, accepted, _ = outward
    false_actual = replace(
        accepted.accepted_support,
        auxiliary_root_count=0,
        source_support_root_count=0,
        retained_root_count=0,
    )
    forged = replace(
        accepted,
        auxiliary_root_count=0,
        source_support_root_count=0,
        retained_root_count=0,
        accepted_support=false_actual,
    )
    assert native.root_counts(forged) == (60, 4, 64)
    assert native.retained_root_count(forged) == 64


def without_slot(record, missing):
    incomplete = object.__new__(type(record))
    for field in fields(record):
        if field.name != missing:
            object.__setattr__(incomplete, field.name, getattr(record, field.name))
    return incomplete


@pytest.mark.parametrize(
    "missing",
    [
        "source",
        "final_source_cells",
        "radial_disk_roots",
        "center_proxy_roots",
        "lines",
        "accepted_support",
    ],
)
def test_root_inventory_missing_plan_slots_reject_controlled(cardinal, missing):
    plan, _, _ = cardinal
    with pytest.raises(native.NativePlanError, match="^invalid_native_root_inventory$"):
        native.root_counts(without_slot(plan, missing))


@pytest.mark.parametrize("missing", ["radial_disk_roots", "center_proxy_roots", "lines"])
def test_root_inventory_missing_actual_slots_reject_controlled(cardinal, missing):
    _, accepted, _ = cardinal
    incomplete = without_slot(accepted.accepted_support, missing)
    with pytest.raises(native.NativePlanError, match="^invalid_native_root_inventory$"):
        native.root_counts(replace(accepted, accepted_support=incomplete))


@pytest.mark.parametrize("kind", ["line", "support", "disk", "center"])
def test_missing_nested_root_inventory_slots_reject_controlled(cardinal, kind):
    plan, _, _ = cardinal
    if kind in {"line", "support"}:
        first = plan.lines[0]
        if kind == "line":
            first = without_slot(first, "support_circle_roots")
        else:
            first = replace(
                first, support_circle_roots=without_slot(first.support_circle_roots, "parameters")
            )
        plan = replace(plan, lines=(first, plan.lines[1]))
    else:
        name = "radial_disk_roots" if kind == "disk" else "center_proxy_roots"
        roots = getattr(plan, name)
        plan = replace(plan, **{name: (without_slot(roots[0], "parameters"), *roots[1:])})
    with pytest.raises(native.NativePlanError, match="^invalid_native_root_inventory$"):
        native.root_counts(plan)


class HostileCollection:
    def __iter__(self):
        raise AssertionError("untrusted collection must not be iterated")

    def __len__(self):
        raise AssertionError("untrusted collection length must not be read")

    def __bool__(self):
        raise AssertionError("untrusted collection truth value must not be read")


@pytest.mark.parametrize("name", ["actual_radial", "actual_center", "actual_lines"])
@pytest.mark.parametrize("kind", ["hostile", "list", "huge_tuple"])
def test_actual_root_collection_bounds_precede_custom_hooks(cardinal, name, kind):
    plan, _, _ = cardinal
    value = (
        HostileCollection() if kind == "hostile" else [] if kind == "list" else (None,) * 100_000
    )
    with pytest.raises(native.NativePlanError, match="^invalid_native_root_inventory$"):
        native.root_counts(plan, **{name: value})


@pytest.mark.parametrize(
    "name", ["final_source_cells", "radial_disk_roots", "center_proxy_roots", "lines"]
)
@pytest.mark.parametrize("kind", ["hostile", "huge_tuple"])
def test_intended_root_collection_bounds_precede_custom_hooks(cardinal, name, kind):
    plan, _, _ = cardinal
    value = HostileCollection() if kind == "hostile" else (None,) * 100_000
    with pytest.raises(native.NativePlanError, match="^invalid_native_root_inventory$"):
        native.root_counts(replace(plan, **{name: value}))


@pytest.mark.parametrize("kind", ["hostile", "missing", "one", "three", "huge_tuple"])
def test_support_root_branch_collection_has_exact_arity(cardinal, kind):
    plan, _, _ = cardinal
    roots = plan.lines[0].support_circle_roots
    value = {
        "hostile": HostileCollection(),
        "missing": (),
        "one": roots.parameters[:1],
        "three": roots.parameters + roots.parameters[:1],
        "huge_tuple": (None,) * 100_000,
    }[kind]
    line = replace(plan.lines[0], support_circle_roots=replace(roots, parameters=value))
    with pytest.raises(native.NativePlanError, match="^invalid_native_root_inventory$"):
        native.root_counts(replace(plan, lines=(line, plan.lines[1])))


@pytest.mark.parametrize("name", ["actual_radial", "actual_center", "actual_lines"])
def test_partial_or_double_supplied_actual_inventory_is_rejected(cardinal, name):
    plan, accepted, _ = cardinal
    actual = accepted.accepted_support
    records = {
        "actual_radial": actual.radial_disk_roots,
        "actual_center": actual.center_proxy_roots,
        "actual_lines": actual.lines,
    }
    for target in (plan, accepted):
        with pytest.raises(native.NativePlanError, match="^invalid_native_root_inventory$"):
            native.root_counts(target, **{name: records[name]})


@pytest.mark.parametrize(
    "mutation",
    ["copied_root", "assignment_owner", "assignment_class", "assignment_branch", "multiplicity"],
)
def test_source_root_wrappers_and_assignments_remain_cross_checked(outward, mutation):
    plan, _, _ = outward
    source_certificate = plan.source
    if mutation.startswith("assignment") or mutation == "multiplicity":
        first, *remaining = source_certificate.assignments
        change = {
            "assignment_owner": {"line_id": "unknown"},
            "assignment_class": {"original_line_position": "END"},
            "assignment_branch": {"branch": "MINUS" if first.branch == "PLUS" else "PLUS"},
            "multiplicity": {"multiplicity": 2},
        }[mutation]
        source_certificate = replace(
            source_certificate, assignments=(replace(first, **change), *remaining)
        )
    else:
        first, second = source_certificate.incidence.boundaries
        wrapper, other = first.roots.roots
        copied = replace(wrapper, support=replace(wrapper.support))
        first = replace(first, roots=replace(first.roots, roots=(copied, other)))
        source_certificate = replace(
            source_certificate,
            incidence=replace(source_certificate.incidence, boundaries=(first, second)),
        )
    with pytest.raises(
        native.NativePlanError, match="native_source_root|invalid_native_source_roots"
    ):
        native.root_counts(replace(plan, source=source_certificate))


def forged_roots(roots, mutation):
    return replace(
        roots,
        **{
            "missing_negative": {"parameters": roots.parameters[1:]},
            "swapped": {"parameters": roots.parameters[::-1]},
            "wrong_negative": {"parameters": (roots.parameters[1], roots.parameters[1])},
            "multiplicity": {"multiplicities": (2, 1)},
            "owner": {"line_id": "foreign"},
            "point": {"point_id": "foreign"},
            "class": {"memberships": ("BEFORE_START", "AFTER_END")},
            "polynomial": {"c": Dyadic(-1, 0)},
            "discriminant": {"discriminant": Dyadic(1, 0)},
            "norm_difference": {"norm_difference": Dyadic(1, -100)},
            "radius": {"radius": Dyadic(3, 1)},
            "trim": {"trim_parameter": Dyadic(3, 1)},
            "residual": {"endpoint_circle_gap": roots.parameters[1]},
        }[mutation],
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_negative",
        "swapped",
        "wrong_negative",
        "multiplicity",
        "owner",
        "point",
        "class",
        "polynomial",
        "discriminant",
        "norm_difference",
        "radius",
        "trim",
        "residual",
    ],
)
def test_detached_forged_root_proofs_are_not_public_validation_inputs(cardinal, mutation):
    intended, accepted, _ = cardinal
    roots = forged_roots(intended.lines[0].support_circle_roots, mutation)
    changed_line = replace(intended.lines[0], support_circle_roots=roots)
    changed_plan = replace(intended, lines=(changed_line, intended.lines[1]))
    records = observations(intended)
    for fake_source in (
        roots,
        changed_line,
        changed_plan,
        replace(accepted, lines=changed_plan.lines),
    ):
        with pytest.raises(SourceInputError, match="^invalid_source$"):
            native.prepare_native_representation(fake_source, native.NativePlane(), records)
    with pytest.raises(native.NativePlanError, match="^invalid_native_direction_record$"):
        native.prepare_native_representation(source(), native.NativePlane(), (roots, records[1]))


@pytest.mark.parametrize(
    "slot,value",
    [
        ("length", 1.0),
        ("length", True),
        ("trim_parameter", 6.0),
        ("trim_parameter", 5),
        ("trim_parameter", math.nan),
    ],
)
def test_modified_divisor_or_trim_cannot_be_submitted_as_authority(cardinal, slot, value):
    plan, _, _ = cardinal
    changed = replace(plan.lines[0], **{slot: value})
    fake = replace(plan, lines=(changed, plan.lines[1]))
    with pytest.raises(SourceInputError, match="^invalid_source$"):
        native.prepare_native_representation(fake, native.NativePlane(), observations(plan))


def test_fresh_entry_has_no_plan_root_or_cache_argument_and_reclassifies(cardinal, monkeypatch):
    plan, _, _ = cardinal
    assert tuple(inspect.signature(native.prepare_native_representation).parameters) == (
        "source",
        "plane",
        "actual_directions",
        "context",
    )
    original = native.classify_sector_geometry
    seen = []

    def classify(value, *, context):
        seen.append((value, context))
        return original(value, context=context)

    monkeypatch.setattr(native, "classify_sector_geometry", classify)
    c, value = native.entry_context(), source()
    fresh = native.prepare_native_representation(
        value, native.NativePlane(), observations(plan), context=c
    )
    assert seen == [(value, c)]
    assert fresh.source is not plan.source
    assert fresh.lines[0].support_circle_roots is not plan.lines[0].support_circle_roots
    assert fresh.accepted_support.resources.operations_end == c.operations


def synthetic_edge(plan, index=1):
    """Detached raw fields only; independently checked against fresh preparation."""
    actual = plan.accepted_support
    line = actual.lines[index]
    role = f"line.{line.entity_id}"
    ids, orientation = evidence.expected_edge_metadata(plan, role, "support")
    curve = {
        "kind": "line",
        "location": native.transform(plan.frame, plan.center),
        "direction": native.transform(plan.frame, line.direction),
        "u": None,
        "v": None,
        "normal": None,
        "radius": None,
        "range": (0.0, line.trim_parameter),
        "identity_location": True,
    }
    pcurve = {**curve, "location": plan.center, "direction": line.direction}
    location = {
        "identity": True,
        "matrix": ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0)),
    }
    representations = (
        {
            "index": 0,
            "representation_type": "BRep_Curve3D",
            "is_curve3d": True,
            "is_on_surface": False,
            "is_closed_surface": False,
            "surface_index": None,
            "surface_is_retained": False,
            "surface_fields": None,
            "location": location,
            "range": curve["range"],
            "curve3d": curve,
            "pcurves": (),
        },
        {
            "index": 1,
            "representation_type": "BRep_CurveOnSurface",
            "is_curve3d": False,
            "is_on_surface": True,
            "is_closed_surface": False,
            "surface_index": 0,
            "surface_is_retained": True,
            "surface_fields": {
                "kind": "Geom_Plane",
                "origin": plan.frame.origin,
                "u": plan.frame.u,
                "v": plan.frame.v,
                "normal": plan.frame.normal,
                "radius": None,
            },
            "location": location,
            "range": pcurve["range"],
            "curve3d": None,
            "pcurves": (pcurve,),
        },
    )
    points = tuple(dict(plan.vertices)[name] for name in ids)
    return {
        "role": role,
        "curve": curve,
        "pcurve": pcurve,
        "stored_pcurve_count": 1,
        "stored_representation_count": 2,
        "retained_pcurve_count": 1,
        "selected_pcurve_index": 1,
        "representations": representations,
        "pcurve_surface_matches": True,
        "orientation": orientation,
        "expected_orientation": orientation,
        "endpoint_ids": ids,
        "expected_endpoint_ids": ids,
        "vertex_identity_matches": True,
        "edge_identity_matches": True,
        "vertex_coordinates": points,
        "vertex_parameters": curve["range"],
        "edge_tolerance": 1e-7,
        "vertex_tolerances": (1e-7, 1e-7),
        "locations_identity": True,
        "evaluated_endpoints": points,
        "observed_distances": (0.0, 0.0),
        "equation_bounds_transfer": True,
    }


def check_edge(plan, record):
    return evidence.validate_edge_observation(
        plan,
        record["role"],
        record,
        context=PrimitiveContext(),
        traversal="support",
        pcurve_required=True,
    )


def test_detached_observation_uses_radius_range_even_when_authored_length_differs(outward):
    _, accepted, _ = outward
    record = synthetic_edge(accepted)
    assert accepted.lines[1].length != record["curve"]["range"][1]
    check_edge(accepted, record)


@pytest.mark.parametrize(
    "mutation",
    [
        "stale_3d_range",
        "stale_2d_range",
        "stale_vertex_parameter",
        "direction_after_binding",
        "2d_3d_disagreement",
        "adjusted_vertex",
        "replaced_vertex",
        "edge_tolerance",
        "vertex_tolerance",
        "wrong_owner",
        "selected_owner",
        "count",
        "false_evaluation",
        "false_distance",
        "expected_metadata",
    ],
)
def test_radius_range_observation_forgeries_fail_closed(outward, mutation):
    _, plan, _ = outward
    record = copy.deepcopy(synthetic_edge(plan))
    if mutation in {"stale_3d_range", "stale_2d_range"}:
        target = "curve" if mutation == "stale_3d_range" else "pcurve"
        record[target]["range"] = (0.0, plan.lines[1].length)
    elif mutation == "stale_vertex_parameter":
        record["vertex_parameters"] = (0.0, plan.lines[1].length)
    elif mutation in {"direction_after_binding", "2d_3d_disagreement"}:
        if mutation == "direction_after_binding":
            record["curve"]["direction"] = (0.0, math.nextafter(1.0, 0.0), 0.0)
        record["pcurve"]["direction"] = (0.0, math.nextafter(1.0, 0.0))
    elif mutation == "adjusted_vertex":
        record["vertex_coordinates"] = (record["vertex_coordinates"][0], (0.0, plan.radius, 0.0))
    elif mutation == "replaced_vertex":
        record["vertex_identity_matches"] = False
    elif mutation == "edge_tolerance":
        record["edge_tolerance"] = math.nextafter(1e-7, math.inf)
    elif mutation == "vertex_tolerance":
        record["vertex_tolerances"] = (1e-7, math.nextafter(1e-7, math.inf))
    elif mutation == "wrong_owner":
        record["representations"][1]["surface_is_retained"] = False
    elif mutation == "selected_owner":
        record["selected_pcurve_index"] = 0
    elif mutation == "count":
        record["stored_pcurve_count"] = 2
    elif mutation == "false_evaluation":
        record["evaluated_endpoints"] = (
            record["vertex_coordinates"][0],
            (0.0, plan.radius + 1e-8, 0.0),
        )
    elif mutation == "false_distance":
        record["observed_distances"] = (0.0, 1e-8)
    else:
        record["endpoint_ids"] = record["expected_endpoint_ids"] = ("c", "a")
    assert record["equation_bounds_transfer"] is True
    with pytest.raises(native.NativePlanError):
        check_edge(plan, record)


def test_complete_synthetic_phases_keep_one_budget_and_one_mebibyte(prepared):
    _, plan, accepted, c = prepared
    actual = accepted.accepted_support
    assert plan.source.resources.operations_end <= 100_000
    assert (
        plan.source.resources.operations_end
        < plan.resources.operations_end
        == actual.resources.operations_start
    )
    assert (
        actual.resources.operations_start
        < actual.resources.operations_end
        == c.operations
        <= 200_000
    )
    assert len(native.plan_bytes(accepted)) <= 1_048_576
    assert actual.intended_plan_sha256 == hashlib.sha256(native.plan_bytes(plan)).hexdigest()


def test_new_root_work_keeps_supplied_lower_budget_and_exact_exhaustion(cardinal):
    plan, accepted, _ = cardinal
    required = accepted.accepted_support.resources.operations_end
    exact = PrimitiveContext(max_operations=required)
    result = native.prepare_native_representation(
        source(), native.NativePlane(), observations(plan), context=exact
    )
    assert result.accepted_support.resources.operations_end == exact.operations == required
    short = PrimitiveContext(max_operations=required - 1)
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        native.prepare_native_representation(
            source(), native.NativePlane(), observations(plan), context=short
        )
    assert short.operations == short.max_operations == required - 1


def encode(value):
    if is_dataclass(value):
        return {field.name: encode(getattr(value, field.name)) for field in fields(value)}
    if type(value) in (tuple, list):
        return [encode(item) for item in value]
    return value.hex() if type(value) is float else value


@pytest.mark.parametrize(
    "case,expected",
    [
        (CASES[3], "c59eb58f7339eeae3e0381ce5405c298aa90f358cab72418a7a6deb656361f40"),
        (CASES[4], "1d9e85dde77d4210724306c026f28c7626c56ee865dbbb57a453e429e862b3d2"),
    ],
)
def test_inward_outward_source_mass_windows_match_pretrim_fingerprints(case, expected):
    plan, accepted, _ = prepare(case)
    for item in (plan, accepted):
        values = (
            item.original_circle_gaps,
            item.original_cell_radius,
            item.source_comparison_area,
            item.source_area_midpoint,
            item.area_allowance,
            item.local_scale_squared,
            item.world_scale,
            item.source.area.perimeter,
            tuple(
                evidence.mass_limits(item, height, context=PrimitiveContext())
                for height in (1.0, 7.25, 1000.0)
            ),
        )
        payload = json.dumps(encode(values), sort_keys=True, separators=(",", ":")).encode()
        assert hashlib.sha256(payload).hexdigest() == expected


def test_normalization_expression_keeps_hypot_divisor_and_not_radius():
    tree = ast.parse(inspect.getsource(native._line))
    assignments = {
        target.id: node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert (
        ast.unparse(assignments["h"])
        == "tuple((float(endpoint[k]) - float(center[k]) for k in range(2)))"
    )
    assert ast.unparse(assignments["length"]) == "math.hypot(*h)"
    assert ast.unparse(assignments["direction"]) == "(h[0] / length, h[1] / length)"
    assert "trim_parameter" not in ast.unparse(assignments["length"])


def test_kernel_retains_one_explicit_vertex_parameter_overload_and_original_directions():
    tree = ast.parse((ROOT / "src/mechanical_cad/kernel_ocp.py").read_text())
    kernel = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OCPKernel"
    )
    method = next(
        node
        for node in kernel.body
        if isinstance(node, ast.FunctionDef) and node.name == "sector_profile"
    )
    calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)]
    radial = [
        node
        for node in calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "BRepBuilderAPI_MakeEdge"
        and node.args
        and ast.unparse(node.args[0]) == "curve"
    ]
    assert len(radial) == 1
    assert tuple(map(ast.unparse, radial[0].args)) == (
        "curve",
        "vertices[arc.center_id]",
        "vertices[line.point_id]",
        "0.0",
        "line.trim_parameter",
    )
    for name, expected in (
        (
            "Geom_Line",
            "Geom_Line(gp_Pnt(*transform(plan.frame, plan.center)), gp_Dir(*transform(plan.frame, line.direction)))",
        ),
        ("Geom2d_Line", "Geom2d_Line(gp_Pnt2d(*plan.center), gp_Dir2d(*line.direction))"),
    ):
        constructors = [
            node for node in calls if isinstance(node.func, ast.Name) and node.func.id == name
        ]
        assert len(constructors) == 1 and ast.unparse(constructors[0]) == expected
    raw_support = [
        node
        for node in calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "_curve_profile_curve_record"
        and node.args
        and ast.unparse(node.args[0]) == "curve"
    ]
    assert len(raw_support) == 1
    assert ast.unparse(raw_support[0].args[1]) == "(0.0, line.trim_parameter)"
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "length" for node in ast.walk(method)
    )
