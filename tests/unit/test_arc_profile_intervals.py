"""Independent exact/Decimal checks of the finite, native-free interval leaf."""

from __future__ import annotations

import ast
import os
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from mechanical_cad.arc_profile_intervals import IntervalContext
from mechanical_cad.arc_profile_primitives import (
    INTERVAL_PRECISIONS,
    MAX_OPERATIONS,
    Dyadic,
    DyadicInterval,
    PrimitiveContext,
    PrimitiveError,
)

ROOT = Path(__file__).resolve().parents[2]
ZERO, ONE = Dyadic(0, 0), Dyadic(1, 0)


def exact(value: Dyadic) -> Fraction:
    return Fraction(value.mantissa) * Fraction(2) ** value.exponent


def checked(interval: DyadicInterval) -> tuple[Fraction, Fraction]:
    assert interval.precision in INTERVAL_PRECISIONS
    for endpoint in (interval.lower, interval.upper):
        assert type(endpoint) is Dyadic
        assert endpoint.mantissa.bit_length() <= interval.precision
        assert -32768 <= endpoint.exponent <= 32768
        assert (endpoint.mantissa == 0 and endpoint.exponent == 0) or endpoint.mantissa & 1
    lower, upper = exact(interval.lower), exact(interval.upper)
    assert lower <= upper
    return lower, upper


def dec(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def reference_pi() -> Decimal:
    # Independent Gauss-Legendre iteration, not Machin's atan identity.
    with localcontext() as ctx:
        ctx.prec = 190
        a, b, t, weight = Decimal(1), Decimal(1) / Decimal(2).sqrt(), Decimal(1) / 4, 1
        for _ in range(10):
            mean = (a + b) / 2
            b = (a * b).sqrt()
            t -= weight * (a - mean) ** 2
            a = mean
            weight *= 2
        return (a + b) ** 2 / (4 * t)


def reference_angle(cross: Dyadic, dot: Dyadic, direction: str) -> Decimal:
    # Independent high-precision reference: eight half-angle transforms and
    # a convergence-selected forward series, not the production 128-term Horner
    # polynomial. This numerical oracle tests implementation, not a certificate.
    with localcontext() as ctx:
        ctx.prec = 180
        pi = reference_pi()
        y, x = dec(exact(cross)), dec(exact(dot))
        if y == 0:
            angle = pi
        elif x == 0:
            angle = pi / 2 if y > 0 else 3 * pi / 2
        else:
            z = abs(y / x)
            reciprocal = z > 1
            if reciprocal:
                z = 1 / z
            for _ in range(8):
                z /= 1 + (1 + z * z).sqrt()
            total, power, square, k = z, z, z * z, 1
            while True:
                power *= -square
                term = power / (2 * k + 1)
                total += term
                if abs(term) < Decimal("1e-175"):
                    break
                k += 1
            angle = total * 256
            if reciprocal:
                angle = pi / 2 - angle
            if x < 0:
                angle = pi - angle
            if y < 0:
                angle = 2 * pi - angle
        return angle - 2 * pi if direction == "CW" else angle


def interval(context: IntervalContext, low: int, high: int) -> DyadicInterval:
    return context.context._interval(
        context.context._make(low, 0), context.context._make(high, 0), context.precision
    )


@pytest.mark.parametrize("precision", INTERVAL_PRECISIONS)
@pytest.mark.parametrize("exponent", [-1000, -100, 0, 100, 1000])
@pytest.mark.parametrize("sign", [-1, 1])
def test_point_rounds_outward_with_normalized_significands(precision, exponent, sign):
    source = Dyadic(sign * ((1 << (precision + 19)) + 7), exponent)
    context = IntervalContext(PrimitiveContext(), precision)
    low, high = checked(context.point(source))
    assert low <= exact(source) <= high
    assert low < high
    assert context.point(0) == DyadicInterval(ZERO, ZERO, precision)


@pytest.mark.parametrize("precision", INTERVAL_PRECISIONS)
def test_all_sign_combinations_against_exact_rational_arithmetic(precision):
    context = IntervalContext(PrimitiveContext(), precision)
    pairs = [(-7, -3), (-2, 0), (-3, 4), (0, 0), (0, 5), (3, 9)]
    for low, high in pairs:
        left = interval(context, low, high)
        assert checked(context.neg(left)) == (-high, -low)
        assert checked(context.abs(left)) == (
            0 if low <= 0 <= high else min(abs(low), abs(high)),
            max(abs(low), abs(high)),
        )
        for bottom, top in pairs:
            right = interval(context, bottom, top)
            assert checked(context.add(left, right)) == (low + bottom, high + top)
            assert checked(context.sub(left, right)) == (low - top, high - bottom)
            products = [a * b for a in (low, high) for b in (bottom, top)]
            assert checked(context.mul(left, right)) == (min(products), max(products))
            if bottom <= 0 <= top:
                with pytest.raises(PrimitiveError, match="^interval_zero_divisor$"):
                    context.div(left, right)
            else:
                lower, upper = checked(context.div(left, right))
                ratios = [Fraction(a, b) for a in (low, high) for b in (bottom, top)]
                assert lower <= min(ratios) <= max(ratios) <= upper
    assert context.context.operations < MAX_OPERATIONS


@pytest.mark.parametrize("precision", INTERVAL_PRECISIONS)
def test_random_interval_arithmetic_rounding(precision):
    rng = random.Random(20261017)
    for _ in range(80):
        context = IntervalContext(PrimitiveContext(), precision)
        values = [context.point(Dyadic(rng.randrange(1, 1 << 100) | 1, -40)) for _ in range(4)]
        left = context.sub(values[0], values[1])
        right = context.sub(values[2], values[3])
        a, b = checked(left)
        d, e = checked(right)
        for result, expect_low, expect_high in (
            (context.add(left, right), a + d, b + e),
            (context.sub(left, right), a - e, b - d),
            (
                context.mul(left, right),
                min(a * d, a * e, b * d, b * e),
                max(a * d, a * e, b * d, b * e),
            ),
        ):
            low, high = checked(result)
            assert low <= expect_low <= expect_high <= high
        if not d <= 0 <= e:
            low, high = checked(context.div(left, right))
            ratios = [a / d, a / e, b / d, b / e]
            assert low <= min(ratios) <= max(ratios) <= high


@pytest.mark.parametrize("precision", INTERVAL_PRECISIONS)
def test_sqrt_monotonicity_and_exact_squared_bounds(precision):
    context = IntervalContext(PrimitiveContext(), precision)
    for low, high in [(0, 0), (0, 1), (1, 4), (2, 3), (1000, 1001)]:
        lower, upper = checked(context.sqrt(interval(context, low, high)))
        assert 0 <= lower and lower * lower <= low <= high <= upper * upper
    for exponent in (-1074, -1001, 1001):
        source = Dyadic(3, exponent)
        lower, upper = checked(context.sqrt(context.point(source)))
        assert lower * lower <= exact(source) <= upper * upper
    for low, high in [(-1, 1), (-2, -1), (-1, 0)]:
        with pytest.raises(PrimitiveError, match="^negative_radicand$"):
            context.sqrt(interval(context, low, high))


def test_scale_uses_exact_dyadic_or_integer_factor():
    context = IntervalContext(PrimitiveContext(), 64)
    source = interval(context, -3, 5)
    assert checked(context.scale(source, -2)) == (-10, 6)
    assert checked(context.scale(source, Dyadic(3, -2))) == (Fraction(-9, 4), Fraction(15, 4))
    assert checked(context.scale(source, 0)) == (0, 0)


@pytest.mark.parametrize("precision", INTERVAL_PRECISIONS)
def test_pi_enclosure_independent_gauss_legendre_reference(precision):
    context = IntervalContext(PrimitiveContext(), precision)
    low, high = checked(context.pi())
    with localcontext() as ctx:
        ctx.prec = 180
        assert dec(low) < reference_pi() < dec(high)
    assert high - low < Fraction(1, 1 << (precision - 8))
    operations = context.context.operations
    assert context.pi() is context.pi()
    assert context.context.operations == operations


@pytest.mark.parametrize("precision", INTERVAL_PRECISIONS)
@pytest.mark.parametrize("direction", ["CCW", "CW"])
@pytest.mark.parametrize(
    "cross,dot",
    [
        (0, -1),
        (1, 0),
        (-1, 0),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
        (3, 4),
        (3, -4),
        (-3, 4),
        (-3, -4),
        (4, 3),
        (4, -3),
        (-4, 3),
        (-4, -3),
    ],
)
def test_directed_angles_all_quadrants_and_reciprocal_branches(precision, direction, cross, dot):
    exact_context = PrimitiveContext()
    cross, dot = exact_context._make(cross, 0), exact_context._make(dot, 0)
    context = IntervalContext(exact_context, precision)
    low, high = checked(context.directed_angle(cross, dot, direction))
    with localcontext() as ctx:
        ctx.prec = 180
        reference = reference_angle(cross, dot, direction)
        assert dec(low) < reference < dec(high)
    assert (low > 0) if direction == "CCW" else (high < 0)
    assert high - low < Fraction(1, 1 << (precision - 10))
    assert exact_context.operations < 40_000


@pytest.mark.parametrize("precision", INTERVAL_PRECISIONS)
@pytest.mark.parametrize(
    "cross,dot",
    [
        (Dyadic(1, -100), Dyadic(-1, 0)),
        (Dyadic(-1, -100), Dyadic(-1, 0)),
        (Dyadic(1, 0), Dyadic(-1, -100)),
        (Dyadic(1, 0), Dyadic(1, -100)),
        (Dyadic(3, -90), Dyadic(-7, -90)),
    ],
)
def test_exact_signs_near_axes_and_scale_invariance(precision, cross, dot):
    for direction in ("CCW", "CW"):
        context = IntervalContext(PrimitiveContext(), precision)
        low, high = checked(context.directed_angle(cross, dot, direction))
        with localcontext() as ctx:
            ctx.prec = 180
            assert dec(low) < reference_angle(cross, dot, direction) < dec(high)


def test_exact_translated_vectors_are_not_rounded_before_angles():
    context = PrimitiveContext()
    center = (2**-1074, 2**-1074)
    start, end = (13, 29), (-29, 13)
    a, b = context.vector(center, start), context.vector(center, end)
    cross, dot = context.cross(a, b), context.dot(a, b)
    assert dot.mantissa != 0
    intervals = IntervalContext(context, 256)
    # Exact-ratio reduction would lead to extremely small terms; exhausting the
    # fixed exponent cap is an explicit bounded rejection, never rounded dot=0.
    with pytest.raises(PrimitiveError, match="^(exponent_limit|integer_limit)$"):
        intervals.directed_angle(cross, dot, "CCW")
    assert context.operations < MAX_OPERATIONS


@pytest.mark.parametrize("precision", [True, False, 0, 32, 65, 512, 64.0, "64", None])
def test_strict_precision_schedule(precision):
    with pytest.raises(PrimitiveError, match="^invalid_precision$"):
        IntervalContext(PrimitiveContext(), precision)


@pytest.mark.parametrize(
    "value", [True, False, 1.0, None, "1", Fraction(1), object.__new__(Dyadic)]
)
def test_point_rejects_nonexact_or_malformed_values(value):
    with pytest.raises(PrimitiveError, match="^invalid_dyadic$"):
        IntervalContext(PrimitiveContext(), 64).point(value)


def test_context_and_cached_state_are_read_only():
    context = PrimitiveContext()
    intervals = IntervalContext(context, 64)
    assert intervals.context is context and intervals.precision == 64
    for field in ("context", "_context", "precision", "_precision", "_pi", "_coefficients"):
        with pytest.raises(AttributeError):
            setattr(intervals, field, None)
        with pytest.raises(AttributeError):
            delattr(intervals, field)
    with pytest.raises(PrimitiveError, match="^interval_already_initialized$"):
        intervals.__init__(context, 128)
    with pytest.raises(PrimitiveError, match="^invalid_context$"):
        IntervalContext(None, 64)
    with pytest.raises(FrozenInstanceError):
        intervals.point(1).lower = ZERO


def test_revalidate_all_public_interval_inputs():
    context = IntervalContext(PrimitiveContext(), 64)
    good = context.point(1)
    invalid = [
        None,
        ONE,
        object.__new__(DyadicInterval),
        DyadicInterval(ONE, ZERO, 64),
        DyadicInterval(ZERO, ONE, True),
        DyadicInterval(ZERO, ONE, 128),
        DyadicInterval(ZERO, Dyadic((1 << 64) + 1, 0), 64),
        DyadicInterval(ZERO, Dyadic(1, -32769), 64),
    ]
    for bad in invalid:
        for operation in (context.neg, context.abs, context.sqrt):
            with pytest.raises(PrimitiveError):
                operation(bad)
        for operation in (context.add, context.sub, context.mul, context.div):
            with pytest.raises(PrimitiveError):
                operation(bad, good)
            with pytest.raises(PrimitiveError):
                operation(good, bad)
        with pytest.raises(PrimitiveError):
            context.scale(bad, 2)


@pytest.mark.parametrize(
    "cross,dot,direction,code",
    [
        (ZERO, ZERO, "CCW", "zero_angle_pair"),
        (ZERO, ONE, "CCW", "coincident_arc_rays"),
        (ONE, ONE, "ccw", "invalid_direction"),
        (ONE, ONE, True, "invalid_direction"),
        (ONE, ONE, None, "invalid_direction"),
        (None, ONE, "CW", "invalid_dyadic"),
    ],
)
def test_angle_invalid_or_nonfull_branch_requests_fail_closed(cross, dot, direction, code):
    with pytest.raises(PrimitiveError, match=f"^{code}$"):
        IntervalContext(PrimitiveContext(), 64).directed_angle(cross, dot, direction)


def test_operation_budget_is_aggregate_and_never_reset_or_raised():
    context = PrimitiveContext(max_operations=2000)
    first = IntervalContext(context, 64)
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        first.pi()
    assert context.operations == context.max_operations == 2000
    for precision in INTERVAL_PRECISIONS:
        another = IntervalContext(context, precision)
        for operation in (another.pi, lambda another=another: another.point(1)):
            with pytest.raises(PrimitiveError, match="^operation_limit$"):
                operation()
        assert context.operations == 2000


def test_integer_and_exponent_caps_are_fail_closed_before_allocation():
    context = IntervalContext(PrimitiveContext(max_bits=64), 64)
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        context.point(1 << 64)
    with pytest.raises(PrimitiveError, match="^integer_limit$"):
        context.mul(context.point(Dyadic((1 << 40) + 1, 0)), context.point(1 << 40))
    full = IntervalContext(PrimitiveContext(), 64)
    tiny = full.point(Dyadic(1, -32768))
    with pytest.raises(PrimitiveError, match="^exponent_limit$"):
        full.mul(tiny, full.point(Dyadic(1, -1)))
    huge = full.point(Dyadic(1, 32768))
    with pytest.raises(PrimitiveError, match="^exponent_limit$"):
        full.mul(huge, full.point(2))


def test_shared_work_estimate_reserves_budget_for_cells_and_later_checks():
    context = PrimitiveContext()
    # Exercise actual prior support work in the same budget, without assuming
    # this creates an incidence/profile certificate.
    for endpoint in ((3, 4), (-4, 3)):
        context.line_circle_roots((0, 0), endpoint, (0, 0), 5)
    before = context.operations
    intervals = IntervalContext(context, 64)
    intervals.directed_angle(Dyadic(3, 0), Dyadic(-1, 2), "CCW")
    used = context.operations - before
    assert used < 40_000
    second = context.operations
    intervals.directed_angle(Dyadic(-3, 0), Dyadic(-1, 2), "CW")
    assert context.operations - second < 12_000
    assert context.operations < 55_000


def test_no_native_or_unbounded_numeric_import_or_execution_under_traps():
    script = r"""
import builtins
import sys
forbidden = ('OCP', 'bpy', 'slvs', 'numpy', 'sympy', 'mpmath', 'fractions', 'decimal',
             'mechanical_cad.kernel', 'mechanical_cad.sketch_solver',
             'mechanical_cad.engine', 'mechanical_cad.sidecar',
             'mechanical_cad.blender_addon')
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(forbidden):
        raise AssertionError('Forbidden import attempted: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from mechanical_cad.arc_profile_intervals import IntervalContext
from mechanical_cad.arc_profile_primitives import PrimitiveContext, Dyadic
import math
for name in ('atan', 'atan2', 'sin', 'cos', 'sqrt', 'hypot'):
    setattr(math, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError('libm used')))
c = PrimitiveContext()
i = IntervalContext(c, 128)
a = i.directed_angle(Dyadic(3, 0), Dyadic(-1, 2), 'CW')
assert a.upper.mantissa < 0 and c.operations < 40000
assert not any(name.startswith(forbidden) for name in sys.modules)
print('ARC_INTERVALS_NATIVE_FREE_OK')
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.stdout.strip() == "ARC_INTERVALS_NATIVE_FREE_OK"


def test_leaf_uses_only_the_approved_primitive_dependency():
    source = ROOT / "src/mechanical_cad/arc_profile_intervals.py"
    tree = ast.parse(source.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            pytest.fail("No direct package imports are needed in the finite interval leaf")
        if isinstance(node, ast.ImportFrom):
            assert node.module in ("__future__", "arc_profile_primitives")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("PrimitiveContext", "eval", "exec", "Fraction", "float")


def rational_atan_bounds(value: Fraction, terms: int = 600) -> tuple[Fraction, Fraction]:
    """Exact forward sum with an independent rational alternating-tail bound."""
    power, square, total = value, value * value, Fraction(0)
    for k in range(terms):
        total += (-1 if k % 2 else 1) * power / (2 * k + 1)
        power *= square
    next_term = power / (2 * terms + 1)
    return (total, total + next_term) if terms % 2 == 0 else (total - next_term, total)


@pytest.mark.parametrize("precision", INTERVAL_PRECISIONS)
def test_series_and_angle_enclosures_contain_exact_rational_reference_bounds(precision):
    for value in (Fraction(0), Fraction(1, 16), Fraction(1, 5), Fraction(1, 4)):
        context = IntervalContext(PrimitiveContext(), precision)
        argument = context.div(context.point(value.numerator), context.point(value.denominator))
        lower, upper = checked(context._atan_series(argument))
        reference_low, reference_high = rational_atan_bounds(value, 200)
        assert lower <= reference_low <= reference_high <= upper
    a_low, a_high = rational_atan_bounds(Fraction(1, 5), 200)
    b_low, b_high = rational_atan_bounds(Fraction(1, 239), 200)
    pi_low, pi_high = 16 * a_low - 4 * b_high, 16 * a_high - 4 * b_low
    beta_low, beta_high = rational_atan_bounds(Fraction(3, 4))
    for cross in (-3, 3):
        for dot in (-4, 4):
            for direction in ("CW", "CCW"):
                expected_low, expected_high = beta_low, beta_high
                if dot < 0:
                    expected_low, expected_high = pi_low - expected_high, pi_high - expected_low
                if cross < 0:
                    expected_low, expected_high = (
                        2 * pi_low - expected_high,
                        2 * pi_high - expected_low,
                    )
                if direction == "CW":
                    expected_low, expected_high = (
                        expected_low - 2 * pi_high,
                        expected_high - 2 * pi_low,
                    )
                exact_context = PrimitiveContext()
                context = IntervalContext(exact_context, precision)
                lower, upper = checked(
                    context.directed_angle(
                        exact_context._make(cross, 0), exact_context._make(dot, 0), direction
                    )
                )
                assert lower <= expected_low <= expected_high <= upper
