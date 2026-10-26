"""Exact-reference tests for the isolated, native-free primitive leaf."""

from __future__ import annotations

import ast
import hashlib
import math
import os
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError
from fractions import Fraction
from pathlib import Path

import pytest

from mechanical_cad.arc_profile_primitives import (
    DEFAULT_OPERATIONS,
    INTERVAL_PRECISIONS,
    MAX_INTEGER_BITS,
    MAX_OPERATIONS,
    Dyadic,
    DyadicInterval,
    PrimitiveContext,
    PrimitiveError,
    SupportRoot,
    SupportRoots,
    UnresolvedSupportRoots,
)

ROOT = Path(__file__).resolve().parents[2]
TINY = math.ulp(0.0)
ZERO = Dyadic(0, 0)
ONE = Dyadic(1, 0)


def exact(value: Dyadic) -> Fraction:
    return Fraction(value.mantissa) * Fraction(2) ** value.exponent


def reference_number(value: int | float) -> Fraction:
    return Fraction(value)


def assert_interval(interval: DyadicInterval) -> tuple[Fraction, Fraction]:
    assert interval.precision in INTERVAL_PRECISIONS
    for endpoint in (interval.lower, interval.upper):
        assert type(endpoint) is Dyadic
        assert endpoint.mantissa.bit_length() <= interval.precision
        assert -32768 <= endpoint.exponent <= 32768
        assert (endpoint.mantissa == 0 and endpoint.exponent == 0) or endpoint.mantissa & 1
    lo, hi = exact(interval.lower), exact(interval.upper)
    assert lo <= hi
    return lo, hi


def assert_root_ledger(result: SupportRoots | UnresolvedSupportRoots) -> None:
    a, b, c, d = map(exact, (result.a, result.b, result.c, result.discriminant))
    assert a > 0 and d == b * b - 4 * a * c
    if d < 0:
        assert type(result) is SupportRoots and result.roots == ()
    elif d == 0:
        assert type(result) is SupportRoots
        assert len(result.roots) == 1
        assert result.roots[0].branch == "DOUBLE"
        assert result.roots[0].multiplicity == 2
    else:
        assert [root.branch for root in result.roots] == ["MINUS", "PLUS"]
        assert [root.multiplicity for root in result.roots] == [1, 1]
    for root in result.roots:
        lo, hi = assert_interval(root.parameter)
        if root.branch == "DOUBLE":
            assert lo <= -b / (2 * a) <= hi
        elif root.branch == "MINUS":
            # lo <= (-b-sqrt(d))/(2a) <= hi, checked by rational signs/squares.
            left, right = -b - 2 * a * hi, -b - 2 * a * lo
            assert right >= 0 and right * right >= d
            assert left <= 0 or left * left <= d
        else:
            left, right = 2 * a * lo + b, 2 * a * hi + b
            assert right >= 0 and right * right >= d
            assert left <= 0 or left * left <= d
    if d > 0 and result.isolated:
        assert exact(result.roots[0].parameter.upper) < exact(result.roots[1].parameter.lower)


@pytest.mark.parametrize(
    "value",
    [
        0,
        -0.0,
        0.0,
        1,
        -1,
        1e6,
        -1e6,
        0.1,
        -0.1,
        TINY,
        -TINY,
        math.nextafter(1e6, 0),
        math.nextafter(0.0, -1),
        2.0**-1022,
    ],
)
def test_exact_coordinate(value):
    assert exact(PrimitiveContext().coordinate(value)) == reference_number(value)


def test_random_binary64_decoding():
    rng = random.Random(20261017)
    context = PrimitiveContext()
    for _ in range(500):
        value = math.ldexp(rng.uniform(-1, 1), rng.randrange(-1074, 20))
        assert exact(context.coordinate(value)) == Fraction(value)
    assert context.coordinate(-0.0) == context.coordinate(0.0) == ZERO


def test_exact_translation_and_fixed_polynomials():
    context = PrimitiveContext()
    u = context.vector((TINY, -1e6), (1e6, TINY))
    v = context.vector((-1e6, TINY), (TINY, 1e6))
    ru = (Fraction(1e6) - Fraction(TINY), Fraction(TINY) + Fraction(1e6))
    rv = (Fraction(TINY) + Fraction(1e6), Fraction(1e6) - Fraction(TINY))
    assert tuple(map(exact, u)) == ru
    assert exact(u[0]) != Fraction(1e6 - TINY)  # Rounded translation loses the offset.
    assert exact(context.dot(u, v)) == ru[0] * rv[0] + ru[1] * rv[1]
    assert exact(context.cross(u, v)) == ru[0] * rv[1] - ru[1] * rv[0]
    assert u[0].mantissa.bit_length() > 1000
    a, b, c = context.dot(u, u), context.dot(u, v), context.cross(u, v)
    assert exact(context.discriminant(a, b, c)) == exact(b) ** 2 - 4 * exact(a) * exact(c)
    assert context.operations < MAX_OPERATIONS


def test_zero_dot_cross_and_discriminant_equality():
    context = PrimitiveContext()
    u = context.vector((0, 0), (13, 29))
    v = context.vector((0, 0), (-29, 13))
    assert context.dot(u, v) == ZERO
    assert context.cross(u, u) == ZERO
    assert context.discriminant(ONE, Dyadic(1, 1), ONE) == ZERO
    assert context.discriminant(ONE, ONE, ONE).mantissa < 0


@pytest.mark.parametrize("value", [True, None, "1", [], {}, complex(1), Fraction(1)])
def test_coordinate_strict_types(value):
    with pytest.raises(PrimitiveError, match="^invalid_number$"):
        PrimitiveContext().coordinate(value)


@pytest.mark.parametrize(
    "value",
    [
        math.nan,
        math.inf,
        -math.inf,
        1000001,
        math.nextafter(1e6, math.inf),
        pytest.param(1 << 100000, id="huge_integer"),
    ],
)
def test_coordinate_domain_is_bounded_and_data_free(value):
    with pytest.raises(PrimitiveError, match="^coordinate_domain$"):
        PrimitiveContext().coordinate(value)


@pytest.mark.parametrize("point", [None, [0, 0], (0,), (0, 0, 0), "ab"])
def test_point_shape(point):
    with pytest.raises(PrimitiveError, match="^invalid_point$"):
        PrimitiveContext().vector(point, (0, 0))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_bits": True},
        {"max_bits": 0},
        {"max_bits": -1},
        {"max_bits": 65537},
        {"max_bits": 128.0},
        {"max_operations": 0},
        {"max_operations": True},
        {"max_operations": 200001},
        {"max_operations": -1},
        {"max_operations": 100000.0},
        pytest.param({"max_operations": 1 << 100000}, id="huge_operation_limit"),
        {"max_operations": "100"},
    ],
)
def test_budget_validation(kwargs):
    with pytest.raises(PrimitiveError, match="^invalid_budget$"):
        PrimitiveContext(**kwargs)


def test_limits_and_counter_are_read_only_and_nonresetting():
    context = PrimitiveContext(max_operations=2)
    assert context.coordinate(1) == ONE and context.operations == 2
    for name in ("max_bits", "max_operations", "operations", "_max_bits", "_operations"):
        with pytest.raises(AttributeError):
            setattr(context, name, 1)
    for _ in range(2):
        with pytest.raises(PrimitiveError, match="^operation_limit$"):
            context.coordinate(1)
    assert context.operations == 2
    with pytest.raises(PrimitiveError, match="^budget_already_initialized$"):
        context.__init__(max_operations=2)
    with pytest.raises(AttributeError):
        del context._operations
    assert (context.operations, context.max_bits, context.max_operations) == (2, 65536, 2)


def test_default_operation_limit_remains_the_original_pure_budget():
    context = PrimitiveContext()
    assert type(context) is PrimitiveContext
    assert (context.operations, context.max_bits, context.max_operations) == (
        0,
        65536,
        DEFAULT_OPERATIONS,
    )
    assert context.max_operations == 100000 < MAX_OPERATIONS


@pytest.mark.parametrize("limit", [100001, 200000])
def test_explicit_native_budget_uses_the_same_primitive_class(limit):
    context = PrimitiveContext(max_operations=limit)
    assert type(context) is PrimitiveContext
    assert (context.operations, context.max_bits, context.max_operations) == (0, 65536, limit)
    assert context.coordinate(1) == ONE
    assert context.operations == 2


@pytest.mark.parametrize("limit", [1, 2, 17, 100000, 100001, 200000])
def test_explicit_limits_preserve_the_same_nonresetting_counter(limit):
    context = PrimitiveContext(max_operations=limit)
    assert type(context) is PrimitiveContext
    context._tick()
    assert context.operations == 1 and context.max_operations == limit
    with pytest.raises(PrimitiveError, match="^budget_already_initialized$"):
        context.__init__(max_operations=MAX_OPERATIONS)
    for name in ("max_operations", "_max_operations", "operations", "_operations"):
        with pytest.raises(AttributeError):
            setattr(context, name, MAX_OPERATIONS)
    assert context.operations == 1 and context.max_operations == limit
    for _ in range(limit - 1):
        context._tick()
    for _ in range(2):
        with pytest.raises(PrimitiveError, match="^operation_limit$"):
            context.coordinate(1)
    assert context.operations == limit and context.max_operations == limit
    with pytest.raises(PrimitiveError, match="^budget_already_initialized$"):
        context.__init__()
    assert context.operations == limit and context.max_operations == limit


@pytest.mark.parametrize(
    "args",
    [(True, 0), (1, True), (1.0, 0), (2, 0), (0, 1), (1, -65536), (1, 65536), (1 << 65536, 0)],
)
def test_malformed_dyadic(args):
    with pytest.raises(PrimitiveError):
        Dyadic(*args)


def test_revalidate_externally_forged_dyadics_before_arithmetic():
    context = PrimitiveContext()
    for bad in (None, (1, 0), object.__new__(Dyadic)):
        with pytest.raises(PrimitiveError, match="^invalid_dyadic$"):
            context.sqrt_enclosure(bad)
    for field, value in (("exponent", 10**100), ("mantissa", 1 << 65536), ("mantissa", True)):
        bad = Dyadic(1, 0)
        object.__setattr__(bad, field, value)
        with pytest.raises(PrimitiveError):
            context.radical_sign(ONE, ONE, bad)
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        PrimitiveContext(max_bits=32).sqrt_enclosure(Dyadic(1, -100))


def test_preallocation_caps_do_not_wait_for_result_cancellation():
    context = PrimitiveContext(max_bits=8)
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        context._imul(31, 15)  # Product would fit 9 bits, precheck is 5+4.
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        context._iadd(255, -255)  # Exact zero is not a reason to bypass allocation guard.
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        context._ishift(1, 10**100)
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        context._ishift(0, 10**100)
    enormous_shift = 1 << 100000
    for shift_helper in (context._ishift, context._iright):
        with pytest.raises(PrimitiveError, match="^integer_limit$"):
            shift_helper(1, enormous_shift)
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        context._make(1, -1000)
    assert context.operations == 0  # Rejection occurs before executing any arithmetic.
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        PrimitiveContext(max_bits=1000).coordinate(TINY)
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        PrimitiveContext(max_bits=128).sqrt_enclosure(Dyadic(3, 0), 256)


@pytest.mark.parametrize("precision", INTERVAL_PRECISIONS)
@pytest.mark.parametrize(
    "value",
    [
        ZERO,
        ONE,
        Dyadic(1, 2),
        Dyadic(2**53 - 1, 900),
        Dyadic(3, 0),
        Dyadic(7, -1080),
        Dyadic(1, -2148),
        Dyadic(2**1095 - 1, -1074),
        Dyadic(1, 10000),
    ],
)
def test_sqrt_verified_enclosures_and_normalized_significands(value, precision):
    context = PrimitiveContext()
    result = context.sqrt_enclosure(value, precision)
    lo, hi = assert_interval(result)
    assert 0 <= lo <= hi and lo**2 <= exact(value) <= hi**2
    if exact(value) == 0:
        assert lo == hi == 0
    elif lo != hi:
        # At most one ulp on the original normalized grid, including carry.
        k = value.mantissa.bit_length() - 1 + value.exponent
        assert hi - lo == Fraction(2) ** (k // 2 - (precision - 1))


def test_random_sqrt_fraction_oracle():
    rng = random.Random(1901)
    for precision in INTERVAL_PRECISIONS:
        context = PrimitiveContext()
        for _ in range(100):
            value = Dyadic(rng.randrange(1, 2**201) | 1, rng.randrange(-3000, 3000))
            lo, hi = assert_interval(context.sqrt_enclosure(value, precision))
            assert lo * lo <= exact(value) <= hi * hi


@pytest.mark.parametrize("precision", [True, 0, 32, 65, 512, 64.0, "64"])
def test_invalid_interval_precision(precision):
    with pytest.raises(PrimitiveError, match="^invalid_precision$"):
        PrimitiveContext().sqrt_enclosure(ONE, precision)


def test_sqrt_negative_and_exponent_exhaustion():
    with pytest.raises(PrimitiveError, match="^negative_radicand$"):
        PrimitiveContext().sqrt_enclosure(Dyadic(-1, 0))
    with pytest.raises(PrimitiveError, match="^exponent_limit$"):
        PrimitiveContext().sqrt_enclosure(Dyadic(3, -65534), 64)


@pytest.mark.parametrize(
    "p,q,d,expected",
    [
        (ZERO, ZERO, ZERO, 0),
        (ONE, ZERO, ONE, 1),
        (ZERO, Dyadic(-1, 0), ONE, -1),
        (Dyadic(-3, 0), ONE, Dyadic(9, 0), 0),
        (Dyadic(3, 0), Dyadic(-1, 0), Dyadic(9, 0), 0),
        (ONE, Dyadic(-1, 0), Dyadic(3, 0), -1),
        (Dyadic(-1, 0), ONE, Dyadic(3, 0), 1),
        (ONE, ONE, Dyadic(3, 0), 1),
        (Dyadic(-1, 0), Dyadic(-1, 0), ONE, -1),
    ],
)
def test_exact_radical_sign(p, q, d, expected):
    assert PrimitiveContext().radical_sign(p, q, d) == expected


def test_exact_radical_sign_after_extreme_cancellation():
    context = PrimitiveContext()
    # sqrt(1±2^-2000) is indistinguishable from 1 at output precision, but its
    # exact sign relative to 1 is known without interval refinement.
    above = Dyadic(2**2000 + 1, -2000)
    below = Dyadic(2**2000 - 1, -2000)
    assert context.radical_sign(Dyadic(-1, 0), ONE, above) == 1
    assert context.radical_sign(Dyadic(-1, 0), ONE, below) == -1
    assert context.radical_sign(ONE, Dyadic(-1, 0), above) == -1
    assert context.radical_sign(ONE, Dyadic(-1, 0), below) == 1
    for value in (above, below):
        lo, hi = assert_interval(context.sqrt_enclosure(value, 256))
        assert lo <= 1 <= hi


@pytest.mark.parametrize(
    "start,end,center,radius,positions",
    [
        ((-2, 0), (2, 0), (0, 0), 1, ("INTERIOR", "INTERIOR")),
        ((-1, 0), (1, 0), (0, 0), 1, ("AT_START", "AT_END")),
        ((0, 0), (1, 0), (0, 0), 1, ("BEFORE_START", "AT_END")),
        ((0, 0), (0.5, 0), (0, 0), 1, ("BEFORE_START", "AFTER_END")),
        ((1, 0), (2, 0), (0, 0), 1, ("BEFORE_START", "AT_START")),
        ((2, 0), (3, 0), (0, 0), 1, ("BEFORE_START", "BEFORE_START")),
        ((-3, 0), (-2, 0), (0, 0), 1, ("AFTER_END", "AFTER_END")),
        ((10, 0), (0, 10 + 2**-31), (0, 0), 10, ("AT_START", "INTERIOR")),
        ((10, 0), (0, 10 - 2**-31), (0, 0), 10, ("AT_START", "AFTER_END")),
        ((0, 0), (math.nextafter(1, math.inf), 0), (0, 0), 1, ("BEFORE_START", "INTERIOR")),
        ((0, 0), (math.nextafter(1, 0), 0), (0, 0), 1, ("BEFORE_START", "AFTER_END")),
    ],
)
def test_root_positions(start, end, center, radius, positions):
    result = PrimitiveContext().line_circle_roots(start, end, center, radius)
    assert type(result) is SupportRoots and result.isolated
    assert tuple(root.position for root in result.roots) == positions
    assert_root_ledger(result)


@pytest.mark.parametrize(
    "start,end,position",
    [
        ((-1, 1), (1, 1), "INTERIOR"),
        ((0, 1), (1, 1), "AT_START"),
        ((-1, 1), (0, 1), "AT_END"),
        ((1, 1), (2, 1), "BEFORE_START"),
        ((-2, 1), (-1, 1), "AFTER_END"),
    ],
)
def test_tangent_is_one_explicit_multiplicity_two_root(start, end, position):
    result = PrimitiveContext().line_circle_roots(start, end, (0, 0), 1)
    assert_root_ledger(result)
    assert result.roots[0].position == position


def test_no_real_roots_is_explicit_empty_ledger():
    result = PrimitiveContext().line_circle_roots((-1, 2), (1, 2), (0, 0), 1)
    assert_root_ledger(result)
    assert result.discriminant.mantissa < 0


def test_extreme_line_and_circle_support_inputs():
    for args in [
        ((-1e6, TINY), (1e6, -TINY), (TINY, -TINY), 1e6),
        ((0, 0), (TINY, TINY), (1, 0), 1),
        ((0, 0), (1, 0), (0, 0), 1e-6),
    ]:
        context = PrimitiveContext()
        result = context.line_circle_roots(*args)
        assert_root_ledger(result)
        assert context.operations < MAX_OPERATIONS


def test_membership_is_exact_despite_an_endpoint_straddling_enclosure():
    for center_x, expected in ((TINY, "INTERIOR"), (-TINY, "BEFORE_START")):
        result = PrimitiveContext().line_circle_roots((1, TINY), (2, TINY), (center_x, 0), 1)
        assert_root_ledger(result)
        root = result.roots[1]
        lo, hi = assert_interval(root.parameter)
        if center_x > 0:
            assert lo <= 0 <= hi  # Width alone cannot prove interior membership.
        else:
            assert hi < 0
        assert root.position == expected


def test_distinct_close_roots_are_retained_in_type_distinct_ambiguity():
    result = PrimitiveContext().line_circle_roots((1, -1), (1, 1), (TINY, 0), 1)
    assert type(result) is UnresolvedSupportRoots
    assert not isinstance(result, SupportRoots)
    assert not result.isolated and result.code == "unresolved_isolation"
    assert result.discriminant.mantissa > 0
    assert tuple(root.branch for root in result.roots) == ("MINUS", "PLUS")
    assert tuple(root.position for root in result.roots) == ("INTERIOR", "INTERIOR")
    assert all(root.parameter.precision == 256 for root in result.roots)
    assert exact(result.roots[0].parameter.upper) >= exact(result.roots[1].parameter.lower)
    assert_root_ledger(result)


@pytest.mark.parametrize(
    "radius",
    [
        True,
        None,
        "1",
        0,
        -1,
        TINY,
        math.nan,
        math.inf,
        math.nextafter(1e-6, 0),
        math.nextafter(1e6, math.inf),
    ],
)
def test_radius_validation(radius):
    with pytest.raises(PrimitiveError, match="^radius_domain$"):
        PrimitiveContext().line_circle_roots((0, 0), (1, 0), (0, 0), radius)


def test_degenerate_line_and_resource_exhaustion():
    with pytest.raises(PrimitiveError, match="^degenerate_line$"):
        PrimitiveContext().line_circle_roots((1, 2), (1.0, 2.0), (0, 0), 1)
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        PrimitiveContext(max_operations=10).line_circle_roots((0, 0), (1, 0), (0, 0), 1)


def test_all_root_records_are_immutable():
    result = PrimitiveContext().line_circle_roots((-1, 0), (1, 0), (0, 0), 1)
    assert type(result.roots) is tuple
    for record, field in [
        (ONE, "mantissa"),
        (result, "isolated"),
        (result.roots[0], "position"),
        (result.roots[0].parameter, "lower"),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(record, field, None)
    unresolved = PrimitiveContext().line_circle_roots((1, -1), (1, 1), (TINY, 0), 1)
    with pytest.raises(FrozenInstanceError):
        unresolved.code = "accepted"


def test_random_roots_exact_rational_coefficient_oracle():
    rng = random.Random(8771)
    for _ in range(150):
        start, end, center = [tuple(rng.randint(-50, 50) / 8 for _ in range(2)) for _ in range(3)]
        if start == end:
            continue
        radius = rng.randint(1, 20) / 8
        result = PrimitiveContext().line_circle_roots(start, end, center, radius)
        h = tuple(Fraction(y) - Fraction(x) for x, y in zip(start, end, strict=True))
        off = tuple(Fraction(x) - Fraction(y) for x, y in zip(start, center, strict=True))
        assert exact(result.a) == h[0] ** 2 + h[1] ** 2
        assert exact(result.b) == 2 * (h[0] * off[0] + h[1] * off[1])
        assert exact(result.c) == off[0] ** 2 + off[1] ** 2 - Fraction(radius) ** 2
        assert_root_ledger(result)


def test_leaf_import_is_native_free_even_without_site_packages():
    script = """
import sys
from mechanical_cad.arc_profile_primitives import PrimitiveContext
result = PrimitiveContext().line_circle_roots((-1, 0), (1, 0), (0, 0), 1)
assert len(result.roots) == 2
for name in sys.modules:
    assert not name.startswith(('OCP', 'bpy', 'slvs', 'mechanical_cad.kernel',
                                'mechanical_cad.sketch_solver', 'mechanical_cad.engine',
                                'mechanical_cad.sidecar', 'mechanical_cad.blender_addon'))
print('ARC_PRIMITIVES_NATIVE_FREE_OK')
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.stdout.strip() == "ARC_PRIMITIVES_NATIVE_FREE_OK"


def test_original_arc_policy_bytes_unchanged_and_no_runtime_importers():
    policy = ROOT / "src/mechanical_cad/arc_geometry.py"
    assert hashlib.sha256(policy.read_bytes()).hexdigest() == (
        "b2017ca26300712cdaece7325fcd12fd1330d650896a5494dea56967fa1a82aa"
    )
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


def test_public_constants_and_record_types_are_bounded():
    assert MAX_INTEGER_BITS == 65536 and MAX_OPERATIONS == 200000
    assert DEFAULT_OPERATIONS == 100000
    assert INTERVAL_PRECISIONS == (64, 128, 256)
    assert SupportRoot.__dataclass_params__.frozen


def test_private_interval_entry_points_reject_precision_before_arithmetic():
    context = PrimitiveContext()
    huge_precision = 1 << 100000
    for precision in (huge_precision, True, 65, "64"):
        calls = (
            lambda precision=precision: context._endpoint(ONE, precision),
            lambda precision=precision: context._round(ONE, precision, upward=True),
            lambda precision=precision: context._divide(ONE, ONE, precision, upward=False),
            lambda precision=precision: context._parameter(
                ONE, ONE, DyadicInterval(ONE, ONE, precision), 1
            ),
        )
        for call in calls:
            with pytest.raises(PrimitiveError, match="^invalid_precision$"):
                call()
        assert context.operations == 0
