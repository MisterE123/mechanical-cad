"""Independent cyclic-order oracle for exact, isolated finite-arc membership.

Fraction arithmetic is test-only. The oracle uses a global angular ordering,
not the production minor/major half-plane branch. No numerical angle is used.
"""

from __future__ import annotations

import ast
import math
import os
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError
from decimal import Decimal
from fractions import Fraction as F
from pathlib import Path

import pytest

from mechanical_cad.arc_profile_primitives import (
    DEFAULT_OPERATIONS,
    MAX_OPERATIONS,
    ArcSupportRoot,
    ArcSupportRoots,
    Dyadic,
    PrimitiveContext,
    PrimitiveError,
    SupportRoots,
    UnresolvedArcSupportRoots,
    UnresolvedSupportRoots,
)

ROOT = Path(__file__).resolve().parents[2]
TINY = math.ulp(0.0)
LINE = ((-1, 0), (1, 0), (0, 0), 1)
ARC = {"arc_start": (1, 0), "arc_end": (0, 1), "direction": "CCW"}
ROUNDED_RADIUS = float.fromhex("0x1.fc7cea9829bacp+4")


def sign(value):
    return (value > 0) - (value < 0)


def radical_sign(p, q, d):
    """Independent rational-threshold sign, without production dyadics."""
    assert d >= 0
    if q == 0 or d == 0:
        return sign(p)
    if q < 0:
        return -radical_sign(-p, -q, d)
    if p >= 0:
        return 1
    return sign(d - (p / q) ** 2)


def sub(left, right):
    return tuple(F(a) - F(b) for a, b in zip(left, right, strict=True))


def dot(left, right):
    return left[0] * right[0] + left[1] * right[1]


def cross(left, right):
    return left[0] * right[1] - left[1] * right[0]


def half(x_sign, y_sign):
    return 0 if y_sign > 0 or (y_sign == 0 and x_sign > 0) else 1


def ray_order(left, right):
    lh, rh = half(*map(sign, left)), half(*map(sign, right))
    return sign(lh - rh) if lh != rh else -sign(cross(left, right))


def ray_root_order(ray, rational, radical, d):
    root_signs = [radical_sign(p, q, d) for p, q in zip(rational, radical, strict=True)]
    assert root_signs != [0, 0]
    lh, rh = half(*map(sign, ray)), half(*root_signs)
    if lh != rh:
        return sign(lh - rh)
    return -radical_sign(cross(ray, rational), cross(ray, radical), d)


def oracle(start, end, center, radius, *, arc_start, arc_end, direction):
    """Compute rational quadratic coefficients and cyclic root-ray ordering."""
    h, off = sub(end, start), sub(start, center)
    v0, v1 = sub(arc_start, center), sub(arc_end, center)
    a, b, c = dot(h, h), 2 * dot(h, off), dot(off, off) - F(radius) ** 2
    d = b * b - 4 * a * c
    records = []
    for branch in () if d < 0 else (0,) if d == 0 else (-1, 1):
        tp, tq = -b / (2 * a), F(branch) / (2 * a)
        rational = tuple(x + y * tp for x, y in zip(off, h, strict=True))
        radical = tuple(y * tq for y in h)
        lo, hi = radical_sign(tp, tq, d), radical_sign(tp - 1, tq, d)
        line = (
            "BEFORE_START"
            if lo < 0
            else "AT_START"
            if lo == 0
            else "INTERIOR"
            if hi < 0
            else "AT_END"
            if hi == 0
            else "AFTER_END"
        )
        start_order, end_order = (ray_root_order(ray, rational, radical, d) for ray in (v0, v1))
        if start_order == 0:
            arc = "AT_START"
        elif end_order == 0:
            arc = "AT_END"
        else:
            first, last = (v0, v1) if direction == "CCW" else (v1, v0)
            first_order, last_order = (
                (start_order, end_order) if direction == "CCW" else (end_order, start_order)
            )
            inside = (
                first_order < 0 and last_order > 0
                if ray_order(first, last) < 0
                else first_order < 0 or last_order > 0
            )
            arc = "INTERIOR" if inside else "OUTSIDE"
        records.append((branch, line, arc))
    return (a, b, c, d), records


def exact(value):
    return F(value.mantissa) * F(2) ** value.exponent


def check(*args, **kwargs):
    result = PrimitiveContext().line_arc_roots(*args, **kwargs)
    coefficients, expected = oracle(*args, **kwargs)
    support = result.support
    assert (
        tuple(map(exact, (support.a, support.b, support.c, support.discriminant))) == coefficients
    )
    assert len(result.roots) == len(support.roots) == len(expected)
    assert type(result.roots) is tuple
    assert support == PrimitiveContext().line_circle_roots(*args)
    for actual, original, (branch, line, arc) in zip(
        result.roots, support.roots, expected, strict=True
    ):
        assert actual.support is original
        assert original.branch == {-1: "MINUS", 0: "DOUBLE", 1: "PLUS"}[branch]
        assert original.multiplicity == (2 if branch == 0 else 1)
        assert original.position == line
        assert actual.arc_position == arc
    if type(support) is UnresolvedSupportRoots:
        assert type(result) is UnresolvedArcSupportRoots
        assert not isinstance(result, ArcSupportRoots)
        assert not result.isolated and result.code == "unresolved_isolation"
    else:
        assert type(result) is ArcSupportRoots and result.isolated
    return result


# These 14 inputs and canonical radii are retained from the independent design
# examples, exact_join_examples.json. They are self-contained here: no test
# depends on an engineering evidence directory or imports a profile classifier.
DESIGN_CASES = [
    ("quarter_exact", (0, 0), (10, 0), (0, 10), 10, "CCW", ((1, 1), (1, 1))),
    ("quarter_outward_gap", (0, 0), (10, 0), (0, 10 + 5e-10), 10, "CCW", ((1, 1), (1, 1))),
    ("quarter_inward_gap", (0, 0), (10, 0), (0, 10 - 5e-10), 10, "CCW", ((1, 1), (0, 0))),
    ("major_outward_gap", (0, 0), (10, 0), (0, 10 + 5e-10), 10, "CW", ((1, 1), (1, 0))),
    ("major_inward_gap", (0, 0), (10, 0), (0, 10 - 5e-10), 10, "CW", ((1, 1), (0, 1))),
    ("semicircle_exact", (0, 0), (10, 0), (-10, 0), 10, "CCW", ((1, 1), (1, 1))),
    ("rounded_hypot_quarter", (0, 0), (13, 29), (-29, 13), ROUNDED_RADIUS, "CCW", ((0, 0), (0, 0))),
    ("rounded_hypot_major", (0, 0), (13, 29), (-29, 13), ROUNDED_RADIUS, "CW", ((0, 1), (0, 1))),
    ("threshold_rounded_nominal", (0, 0), (10, 0), (0, 10 + 1e-9), 10, "CCW", ((1, 1), (1, 1))),
    (
        "threshold_lower_neighbor",
        (0, 0),
        (10, 0),
        (0, math.nextafter(10 + 1e-9, 10)),
        10,
        "CCW",
        ((1, 1), (1, 1)),
    ),
    (
        "far_local_eight_ulps",
        (999900, 999900),
        (999910, 999900),
        (999900, 999910 + 8 * math.ulp(999910.0)),
        10,
        "CCW",
        ((1, 1), (1, 1)),
    ),
    (
        "far_local_nine_ulps",
        (999900, 999900),
        (999910, 999900),
        (999900, 999910 + 9 * math.ulp(999910.0)),
        10,
        "CCW",
        ((1, 1), (1, 1)),
    ),
    ("sixty_degree_like_dot_positive", (0, 0), (10, 0), (6, 8), 10, "CCW", ((1, 1), (1, 1))),
    ("near_subnormal_exact_difference", (1, 0), (TINY, 0), (1, -1), 1, "CCW", ((0, 0), (1, 1))),
]


def finite_combinations(result):
    return tuple(
        (
            root.support.position in ("AT_START", "INTERIOR", "AT_END"),
            root.arc_position != "OUTSIDE",
        )
        for root in result.roots
    )


@pytest.mark.parametrize(
    "name,center,start,end,radius,direction,expected",
    DESIGN_CASES,
    ids=[case[0] for case in DESIGN_CASES],
)
def test_retained_design_examples(name, center, start, end, radius, direction, expected):
    result = check(start, end, center, radius, arc_start=start, arc_end=end, direction=direction)
    assert finite_combinations(result) == expected
    if name.startswith("rounded_hypot"):
        assert F(radius) ** 2 != F(13) ** 2 + F(29) ** 2
        assert all(root.arc_position not in ("AT_START", "AT_END") for root in result.roots)


def test_all_four_membership_combinations_are_retained():
    combinations = set()
    for _, center, start, end, radius, direction, _ in DESIGN_CASES[1:5]:
        result = check(
            start, end, center, radius, arc_start=start, arc_end=end, direction=direction
        )
        assert len(result.roots) == 2
        combinations.update(finite_combinations(result))
    assert combinations == {(True, True), (True, False), (False, True), (False, False)}


@pytest.mark.parametrize("direction", ["CCW", "CW"])
@pytest.mark.parametrize("end_ray", [(0, 1), (0, -1), (-1, 0)])
@pytest.mark.parametrize("ray", [(1, 0), (0, 1), (-1, 0), (0, -1)])
def test_exact_endpoints_opposite_rays_semicircles(direction, end_ray, ray):
    result = check((0, 0), ray, (0, 0), 1, arc_start=(2, 0), arc_end=end_ray, direction=direction)
    assert [root.support.position for root in result.roots] == ["BEFORE_START", "AT_END"]
    positive = result.roots[1]
    if ray == (1, 0):
        assert positive.arc_position == "AT_START"
    elif ray == end_ray:
        assert positive.arc_position == "AT_END"
    else:
        assert positive.arc_position not in ("AT_START", "AT_END")


@pytest.mark.parametrize("direction", ["CW", "CCW"])
@pytest.mark.parametrize("signed_zero", [0.0, -0.0])
def test_signed_zero_and_positive_axis_seam(direction, signed_zero):
    zero = check(*LINE, arc_start=(1, signed_zero), arc_end=(0, 1), direction=direction)
    ordinary = check(*LINE, arc_start=(1, 0), arc_end=(0, 1), direction=direction)
    assert zero == ordinary
    seam = check(*LINE, arc_start=(1, -TINY), arc_end=(1, TINY), direction=direction)
    expected = ("OUTSIDE", "INTERIOR") if direction == "CCW" else ("INTERIOR", "OUTSIDE")
    assert tuple(root.arc_position for root in seam.roots) == expected


@pytest.mark.parametrize("direction", ["CW", "CCW"])
def test_subnormal_cancellation_distinguishes_almost_endpoint(direction):
    # x=sqrt(1-TINY**2) is less than 1 although float sqrt would round to 1.
    # cross((1,TINY), (x,TINY)) = TINY*(1-x) is positive, about 2**-3223.
    result = check(
        (-1, TINY),
        (1, TINY),
        (0, 0),
        1,
        arc_start=(1, TINY),
        arc_end=(1, 2 * TINY),
        direction=direction,
    )
    assert result.roots[1].arc_position == ("INTERIOR" if direction == "CCW" else "OUTSIDE")
    assert all(root.arc_position not in ("AT_START", "AT_END") for root in result.roots)
    radial = check(
        (0, 0),
        (1, TINY),
        (0, 0),
        1,
        arc_start=(1, TINY),
        arc_end=(0, 1),
        direction=direction,
    )
    assert radial.roots[1].arc_position == "AT_START"


@pytest.mark.parametrize("direction", ["CW", "CCW"])
def test_tiny_exact_center_translation_and_near_antipodal_rays(direction):
    for offset in (TINY, -TINY):
        for arc_end in ((-1, TINY), (-1, -TINY)):
            check(
                (1, TINY),
                (2, TINY),
                (offset, 0),
                1,
                arc_start=(1, 0),
                arc_end=arc_end,
                direction=direction,
            )


@pytest.mark.parametrize("direction", ["CCW", "CW"])
@pytest.mark.parametrize(
    "arc_start,arc_end", [((1, 0), (-1, 0)), ((0, 1), (1, 0)), ((1, 0), (0, 1))]
)
def test_tangent_multiplicity_is_preserved(direction, arc_start, arc_end):
    result = check(
        (-1, 1),
        (1, 1),
        (0, 0),
        1,
        arc_start=arc_start,
        arc_end=arc_end,
        direction=direction,
    )
    assert len(result.roots) == 1
    assert result.roots[0].support.branch == "DOUBLE"
    assert result.roots[0].support.multiplicity == 2


def test_no_real_roots_preserves_empty_base_ledger():
    result = check((-1, 2), (1, 2), (0, 0), 1, **ARC)
    assert type(result.support) is SupportRoots
    assert result.support.discriminant.mantissa < 0
    assert result.roots == result.support.roots == ()


@pytest.mark.parametrize("direction", ["CW", "CCW"])
def test_unresolved_isolation_retains_opposite_memberships(direction):
    result = check(
        (1, -1),
        (1, 1),
        (TINY, 0),
        1,
        arc_start=(1, 0),
        arc_end=(0, 1),
        direction=direction,
    )
    assert type(result) is UnresolvedArcSupportRoots
    assert [root.support.branch for root in result.roots] == ["MINUS", "PLUS"]
    assert [root.support.position for root in result.roots] == ["INTERIOR", "INTERIOR"]
    assert all(root.support.parameter.precision == 256 for root in result.roots)
    assert exact(result.roots[0].support.parameter.upper) >= exact(
        result.roots[1].support.parameter.lower
    )
    expected = ("OUTSIDE", "INTERIOR") if direction == "CCW" else ("INTERIOR", "OUTSIDE")
    assert tuple(root.arc_position for root in result.roots) == expected


def test_deterministic_random_roots_against_cyclic_order_oracle():
    rng = random.Random(2026101705)
    for _ in range(300):
        points = [tuple(rng.randint(-32, 32) / 8 for _ in range(2)) for _ in range(5)]
        start, end, center, arc_start, arc_end = points
        v0, v1 = sub(arc_start, center), sub(arc_end, center)
        if start == end or not any(v0) or not any(v1):
            continue
        if cross(v0, v1) == 0 and dot(v0, v1) > 0:
            continue
        for direction in ("CW", "CCW"):
            check(
                start,
                end,
                center,
                rng.randint(1, 32) / 8,
                arc_start=arc_start,
                arc_end=arc_end,
                direction=direction,
            )


@pytest.mark.parametrize("direction", ["CCW", "CW"])
def test_axis_permutations_reflections_line_and_arc_reversal(direction):
    start, end, center, radius = (-4, 1), (5, 2), (1, -1), 4
    arc_start, arc_end = (4, 2), (-2, 1)
    args, kwargs = (
        (start, end, center, radius),
        dict(arc_start=arc_start, arc_end=arc_end, direction=direction),
    )
    base = check(*args, **kwargs)
    opposite = "CW" if direction == "CCW" else "CCW"
    reversed_line = check(end, start, center, radius, **kwargs)
    line_reverse = {
        "BEFORE_START": "AFTER_END",
        "AT_START": "AT_END",
        "INTERIOR": "INTERIOR",
        "AT_END": "AT_START",
        "AFTER_END": "BEFORE_START",
    }
    for original, reversed_root in zip(base.roots, reversed(reversed_line.roots), strict=True):
        assert original.arc_position == reversed_root.arc_position
        assert reversed_root.support.position == line_reverse[original.support.position]
    reverse_arc = check(*args, arc_start=arc_end, arc_end=arc_start, direction=opposite)
    endpoint_reverse = {"AT_START": "AT_END", "AT_END": "AT_START"}
    assert tuple(root.arc_position for root in reverse_arc.roots) == tuple(
        endpoint_reverse.get(root.arc_position, root.arc_position) for root in base.roots
    )
    for swap in (False, True):
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):

            def transform(point, swap=swap, sx=sx, sy=sy):
                x, y = reversed(point) if swap else point
                return sx * x + 999900, sy * y - 999900

            determinant = sx * sy * (-1 if swap else 1)
            transformed = check(
                transform(start),
                transform(end),
                transform(center),
                radius,
                arc_start=transform(arc_start),
                arc_end=transform(arc_end),
                direction=direction if determinant > 0 else opposite,
            )
            assert tuple(root.arc_position for root in transformed.roots) == tuple(
                root.arc_position for root in base.roots
            )
            assert transformed.support == base.support


@pytest.mark.parametrize("radius", [1e-6, 0.25, 1001, 1e6])
def test_primitive_domain_does_not_impose_future_profile_scale(radius):
    result = check(*LINE[:3], radius, arc_start=(1, 0), arc_end=(3, 4), direction="CW")
    assert len(result.roots) == 2


class FloatSubclass(float):
    pass


class IntSubclass(int):
    pass


class TupleSubclass(tuple):
    pass


class StrSubclass(str):
    pass


@pytest.mark.parametrize("slot", ["start", "end", "center", "arc_start", "arc_end"])
@pytest.mark.parametrize("value", [None, [], [0, 1], (1,), (1, 2, 3), TupleSubclass((1, 0))])
def test_strict_point_shape_validation(slot, value):
    inputs = dict(zip(("start", "end", "center", "radius"), LINE, strict=True)) | ARC
    inputs[slot] = value
    with pytest.raises(PrimitiveError, match="^invalid_point$"):
        PrimitiveContext().line_arc_roots(**inputs)


@pytest.mark.parametrize("slot", ["start", "end", "center", "arc_start", "arc_end"])
@pytest.mark.parametrize(
    "number", [True, None, "1", F(1), Decimal(1), FloatSubclass(1), IntSubclass(1)]
)
def test_strict_coordinate_types(slot, number):
    inputs = dict(zip(("start", "end", "center", "radius"), LINE, strict=True)) | ARC
    inputs[slot] = (number, 1)
    with pytest.raises(PrimitiveError, match="^invalid_number$"):
        PrimitiveContext().line_arc_roots(**inputs)


@pytest.mark.parametrize("slot", ["start", "end", "center", "arc_start", "arc_end"])
@pytest.mark.parametrize("number", [math.inf, -math.inf, math.nan, 1000001, -1000001])
def test_coordinate_domain(slot, number):
    inputs = dict(zip(("start", "end", "center", "radius"), LINE, strict=True)) | ARC
    inputs[slot] = (number, 1)
    with pytest.raises(PrimitiveError, match="^coordinate_domain$"):
        PrimitiveContext().line_arc_roots(**inputs)


@pytest.mark.parametrize("direction", [None, True, 1, "cw", "ccw", "", "CCW ", StrSubclass("CCW")])
def test_direction_is_exact_builtin_literal(direction):
    context = PrimitiveContext()
    with pytest.raises(PrimitiveError, match="^invalid_direction$"):
        context.line_arc_roots(*LINE, **(ARC | {"direction": direction}))
    assert context.operations == 0


@pytest.mark.parametrize(
    "radius", [True, "1", None, 0, -1, TINY, math.inf, math.nan, F(1), FloatSubclass(1), 1000001]
)
def test_radius_validation(radius):
    with pytest.raises(PrimitiveError, match="^radius_domain$"):
        PrimitiveContext().line_arc_roots(*LINE[:3], radius, **ARC)


@pytest.mark.parametrize("line", [LINE, ((-1, 2), (1, 2), (0, 0), 1)])
@pytest.mark.parametrize(
    "arc_start,arc_end,error",
    [
        ((0, 0), (1, 0), "zero_arc_ray"),
        ((1, 0), (-0.0, 0.0), "zero_arc_ray"),
        ((1, 0), (1, 0), "coincident_arc_rays"),
        ((1, 1), (2, 2), "coincident_arc_rays"),
        ((TINY, TINY), (1, 1), "coincident_arc_rays"),
    ],
)
def test_undefined_arcs_reject_even_when_line_has_no_real_roots(line, arc_start, arc_end, error):
    with pytest.raises(PrimitiveError, match=f"^{error}$"):
        PrimitiveContext().line_arc_roots(
            *line, arc_start=arc_start, arc_end=arc_end, direction="CCW"
        )


def test_empty_ledger_still_validates_direction():
    with pytest.raises(PrimitiveError, match="^invalid_direction$"):
        PrimitiveContext().line_arc_roots(
            (-1, 2), (1, 2), (0, 0), 1, **(ARC | {"direction": False})
        )


def test_degenerate_line_rejects_and_fabricated_records_are_not_an_input():
    with pytest.raises(PrimitiveError, match="^degenerate_line$"):
        PrimitiveContext().line_arc_roots((1, 0), (1, 0), (0, 0), 1, **ARC)
    fake = SupportRoots(Dyadic(1, 0), Dyadic(0, 0), Dyadic(0, 0), Dyadic(0, 0), ())
    with pytest.raises(PrimitiveError, match="^invalid_point$"):
        PrimitiveContext().line_arc_roots(fake, *LINE[1:], **ARC)


def test_same_context_builds_ledger_and_budget_is_not_reset(monkeypatch):
    original = PrimitiveContext.line_circle_roots
    observed = []

    def record(self, *args):
        observed.append((self, self.operations))
        return original(self, *args)

    monkeypatch.setattr(PrimitiveContext, "line_circle_roots", record)
    context = PrimitiveContext()
    context.coordinate(9)
    before = context.operations
    context.line_arc_roots(*LINE, **ARC)
    consumed = context.operations - before
    assert len(observed) == 1 and observed[0][0] is context and observed[0][1] > before
    limited = PrimitiveContext(max_operations=consumed)
    limited.line_arc_roots(*LINE, **ARC)
    assert limited.operations == consumed
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        limited.line_arc_roots(*LINE, **ARC)
    assert limited.operations == consumed
    with pytest.raises(PrimitiveError, match="^budget_already_initialized$"):
        limited.__init__()
    one_short = PrimitiveContext(max_operations=consumed - 1)
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        one_short.line_arc_roots(*LINE, **ARC)
    assert one_short.operations == consumed - 1


def test_budget_cannot_be_evaded_by_repeated_membership_calls():
    context = PrimitiveContext()
    count = 0
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        while True:
            context.line_arc_roots(*LINE, **ARC)
            count += 1
    assert 1 < count < DEFAULT_OPERATIONS
    assert context.operations == DEFAULT_OPERATIONS


def test_new_cancellation_predicates_obey_intermediate_bit_cap():
    args = ((-1, TINY), (1, TINY), (0, 0), 1)
    assert PrimitiveContext(max_bits=2200).line_circle_roots(*args).isolated
    context = PrimitiveContext(max_bits=2200)
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        context.line_arc_roots(*args, arc_start=(1, TINY), arc_end=(0, 1), direction="CCW")
    assert 0 < context.operations < MAX_OPERATIONS
    check(*args, arc_start=(1, TINY), arc_end=(0, 1), direction="CCW")


def test_records_are_deeply_immutable_detached_data():
    result = check(*LINE, **ARC)
    for record, field in [
        (result, "support"),
        (result, "roots"),
        (result, "isolated"),
        (result.roots[0], "support"),
        (result.roots[0], "arc_position"),
        (result.roots[0].support, "position"),
        (result.roots[0].support.parameter, "lower"),
    ]:
        assert not hasattr(record, "__dict__")
        with pytest.raises(FrozenInstanceError):
            setattr(record, field, None)
    ambiguous = check((1, -1), (1, 1), (TINY, 0), 1, **ARC)
    with pytest.raises(FrozenInstanceError):
        ambiguous.code = "accepted"
    # Public constructors deliberately do not validate caller-made evidence.
    assert ArcSupportRoot(None, "invented").arc_position == "invented"


def test_no_libm_approximation_supplies_membership(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Numerical angle/root approximation was called")

    for name in ("atan", "atan2", "hypot", "sqrt", "sin", "cos", "acos"):
        monkeypatch.setattr(math, name, forbidden)
    check((-1, TINY), (1, TINY), (0, 0), 1, **ARC)
    check(
        (13, 29),
        (-29, 13),
        (0, 0),
        ROUNDED_RADIUS,
        arc_start=(13, 29),
        arc_end=(-29, 13),
        direction="CW",
    )


def test_leaf_membership_import_is_native_free_without_site_packages():
    script = """
import sys
from mechanical_cad.arc_profile_primitives import PrimitiveContext
result = PrimitiveContext().line_arc_roots(
    (-1, 0), (1, 0), (0, 0), 1, arc_start=(1, 0), arc_end=(0, 1), direction='CCW')
assert tuple(root.arc_position for root in result.roots) == ('OUTSIDE', 'AT_START')
project = {name for name in sys.modules if name.startswith('mechanical_cad')}
assert project == {'mechanical_cad', 'mechanical_cad.arc_profile_primitives'}, project
assert not any(name.split('.')[0] in {'OCP', 'bpy', 'slvs', 'numpy', 'scipy', 'sympy'} for name in sys.modules)
print('ARC_MEMBERSHIP_NATIVE_FREE_OK')
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.stdout.strip() == "ARC_MEMBERSHIP_NATIVE_FREE_OK"


def test_no_production_consumer_or_duplicate_arithmetic_implementation():
    path = ROOT / "src/mechanical_cad/arc_profile_primitives.py"
    tree = ast.parse(path.read_text())
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert {node.module for node in imports if isinstance(node, ast.ImportFrom)} == {
        "__future__",
        "dataclasses",
    }
    assert [
        alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names
    ] == ["math"]
    # Reviewed exact paths: native adapter, new pure v3 adapter and dormant
    # client math/validation leaves. All existing runtime/owner importers stay closed.
    leaves = (
        "arc_profile_primitives",
        "arc_profile_incidence",
        "arc_profile_intervals",
        "arc_profile_sector",
        "arc_profile_sector_source",
        "arc_profile_sector_policy",
        "arc_profile_native_plan",
        "arc_profile_native_evidence",
    )
    allowed = {
        ROOT / "src/mechanical_cad/arc_profile_incidence.py": {"arc_profile_primitives"},
        ROOT / "src/mechanical_cad/arc_profile_intervals.py": {"arc_profile_primitives"},
        ROOT / "src/mechanical_cad/arc_profile_sector_source.py": {"arc_profile_primitives"},
        ROOT / "src/mechanical_cad/arc_profile_sector_policy.py": {
            "arc_profile_primitives",
            "arc_profile_intervals",
            "arc_profile_sector_source",
        },
        ROOT / "src/mechanical_cad/arc_profile_sector.py": {
            "arc_profile_primitives",
            "arc_profile_incidence",
            "arc_profile_intervals",
            "arc_profile_sector_source",
            "arc_profile_sector_policy",
        },
        ROOT / "src/mechanical_cad/arc_profile_native_plan.py": {
            "arc_profile_primitives",
            "arc_profile_intervals",
            "arc_profile_sector_source",
            "arc_profile_sector_policy",
        },
        ROOT / "src/mechanical_cad/arc_profile_native_evidence.py": {
            "arc_profile_native_plan",
            "arc_profile_primitives",
            "arc_profile_intervals",
        },
        ROOT / "src/mechanical_cad/kernel_ocp.py": {
            "arc_profile_native_plan",
            "arc_profile_native_evidence",
            "arc_profile_sector",
        },
        ROOT / "src/mechanical_cad/profile_adapter_v3.py": {"arc_profile_sector"},
        ROOT / "blender_addon/mechanical_cad_blender/arc_profile_intervals.py": {
            "arc_profile_primitives"
        },
        ROOT / "blender_addon/mechanical_cad_blender/arc_profile_sector_source.py": {
            "arc_profile_primitives"
        },
        ROOT / "blender_addon/mechanical_cad_blender/arc_profile_sector_policy.py": {
            "arc_profile_primitives",
            "arc_profile_intervals",
            "arc_profile_sector_source",
        },
        ROOT / "blender_addon/mechanical_cad_blender/sketch_contracts_v3.py": {
            "arc_profile_primitives",
            "arc_profile_sector_source",
            "arc_profile_sector_policy",
        },
    }
    for source_dir in (ROOT / "src", ROOT / "blender_addon"):
        for source in source_dir.rglob("*.py"):
            permitted = allowed.get(source, set())
            source_tree = ast.parse(source.read_text())
            dynamic_functions = {"__import__"}
            dynamic_modules = {"importlib", "builtins"}
            for node in ast.walk(source_tree):
                if isinstance(node, ast.Import):
                    dynamic_modules.update(
                        alias.asname or alias.name
                        for alias in node.names
                        if alias.name in {"importlib", "builtins"}
                    )
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    dynamic_functions.update(
                        alias.asname or alias.name
                        for alias in node.names
                        if (node.module, alias.name)
                        in {("importlib", "import_module"), ("builtins", "__import__")}
                    )
            for node in ast.walk(source_tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imported = [node.module or ""] + [alias.name for alias in node.names]
                    if (node.level, node.module) == (0, "mechanical_cad") or (
                        (node.level, node.module) == (1, None)
                        and source.parent == ROOT / "src/mechanical_cad"
                    ):
                        assert all(alias.name != "*" for alias in node.names), (
                            source,
                            "unbounded package wildcard import",
                        )
                elif isinstance(node, ast.Call) and (
                    isinstance(node.func, ast.Name)
                    and node.func.id in dynamic_functions
                    or isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in dynamic_modules
                    and node.func.attr in {"import_module", "__import__"}
                ):
                    imported = [
                        item.value
                        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]
                        for item in ast.walk(argument)
                        if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    ]
                    assert not any(
                        leaf in name.split(".") for leaf in leaves for name in imported
                    ), (source, "unreviewed dynamic profile import")
                else:
                    continue
                if source in {
                    ROOT / package / f"{leaf}.py"
                    for package in ("src/mechanical_cad", "blender_addon/mechanical_cad_blender")
                    for leaf in leaves
                }:
                    assert not any("kernel_ocp" in name.split(".") for name in imported), (
                        source,
                        "reverse kernel dependency",
                    )
                for leaf in leaves:
                    if any(leaf in name.split(".") for name in imported):
                        assert leaf in permitted, (source, leaf)
                        if isinstance(node, ast.Import):
                            assert all(
                                alias.name == f"mechanical_cad.{leaf}"
                                for alias in node.names
                                if leaf in alias.name.split(".")
                            ), (source, leaf, "noncanonical module path")
                        else:
                            assert (node.level, node.module) in {
                                (0, f"mechanical_cad.{leaf}"),
                                (0, "mechanical_cad"),
                                (1, leaf),
                                (1, None),
                            }, (source, leaf, "noncanonical module path")
