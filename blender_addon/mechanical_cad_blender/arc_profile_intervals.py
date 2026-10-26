"""Finite outward intervals for the bounded source-sector certificate.

All scalar arithmetic uses the supplied, non-resetting PrimitiveContext. This
leaf has no native dependencies, libm angle certificate, general rational
engine, or authority to admit a profile. Public interval records are data only
and are revalidated on entry. Precision is normalized significand bits.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from .arc_profile_primitives import Dyadic, DyadicInterval, PrimitiveContext, PrimitiveError

_ZERO = Dyadic(0, 0)
_ONE = Dyadic(1, 0)
_QUARTER = Dyadic(1, -2)


class IntervalContext:
    """Fixed-precision interval operations sharing an existing exact budget.

    Pi and the 129 odd reciprocal coefficients are cached only in this wrapper,
    after their checked construction in the same underlying context. A second
    wrapper never resets that context. Internal formulas avoid repeat public
    input validation; every resulting endpoint still uses checked primitive
    arithmetic, directed rounding and an independently ordered enclosure.
    """

    __slots__ = ("_context", "_precision", "_pi", "_coefficients")

    def __init__(self, context: PrimitiveContext, precision: int):
        if hasattr(self, "_context"):
            raise PrimitiveError("interval_already_initialized")
        if type(context) is not PrimitiveContext:
            raise PrimitiveError("invalid_context")
        context._precision(precision)
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "_precision", precision)
        object.__setattr__(self, "_pi", None)
        object.__setattr__(self, "_coefficients", None)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("IntervalContext state is read-only")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("IntervalContext state is read-only")

    @property
    def context(self) -> PrimitiveContext:
        return self._context

    @property
    def precision(self) -> int:
        return self._precision

    def _value(self, value: DyadicInterval) -> DyadicInterval:
        if type(value) is not DyadicInterval:
            raise PrimitiveError("invalid_interval")
        try:
            lower, upper, precision = value.lower, value.upper, value.precision
        except AttributeError:
            raise PrimitiveError("invalid_interval") from None
        self.context._precision(precision)
        if precision != self.precision:
            raise PrimitiveError("precision_mismatch")
        return self.context._interval(lower, upper, precision)

    def _result(self, lower: Dyadic, upper: Dyadic) -> DyadicInterval:
        c, p = self.context, self.precision
        return c._interval(c._round(lower, p, upward=False), c._round(upper, p, upward=True), p)

    def point(self, value: Dyadic | int) -> DyadicInterval:
        """Enclose one exact dyadic or bounded integer by outward rounding."""
        if type(value) is int:
            value = self.context._make(value, 0)
        else:
            value = self.context._value(value)
        return self._result(value, value)

    def _neg(self, value: DyadicInterval) -> DyadicInterval:
        c = self.context
        return self._result(c._neg(value.upper), c._neg(value.lower))

    def neg(self, value: DyadicInterval) -> DyadicInterval:
        return self._neg(self._value(value))

    def _add(self, left: DyadicInterval, right: DyadicInterval) -> DyadicInterval:
        c = self.context
        return self._result(c._add(left.lower, right.lower), c._add(left.upper, right.upper))

    def add(self, left: DyadicInterval, right: DyadicInterval) -> DyadicInterval:
        return self._add(self._value(left), self._value(right))

    def _sub(self, left: DyadicInterval, right: DyadicInterval) -> DyadicInterval:
        c = self.context
        return self._result(c._sub(left.lower, right.upper), c._sub(left.upper, right.lower))

    def sub(self, left: DyadicInterval, right: DyadicInterval) -> DyadicInterval:
        return self._sub(self._value(left), self._value(right))

    def _mul(self, left: DyadicInterval, right: DyadicInterval) -> DyadicInterval:
        c = self.context
        a, b, d, e = left.lower, left.upper, right.lower, right.upper
        sa, sb = c._icmp(a.mantissa, 0), c._icmp(b.mantissa, 0)
        sd, se = c._icmp(d.mantissa, 0), c._icmp(e.mantissa, 0)
        # Monotonic corners avoid four products in the usual fixed-sign case.
        if sa >= 0:
            if sd >= 0:
                lower, upper = c._mul(a, d), c._mul(b, e)
            elif se <= 0:
                lower, upper = c._mul(b, d), c._mul(a, e)
            else:
                lower, upper = c._mul(b, d), c._mul(b, e)
        elif sb <= 0:
            if sd >= 0:
                lower, upper = c._mul(a, e), c._mul(b, d)
            elif se <= 0:
                lower, upper = c._mul(b, e), c._mul(a, d)
            else:
                lower, upper = c._mul(a, e), c._mul(a, d)
        elif sd >= 0:
            lower, upper = c._mul(a, e), c._mul(b, e)
        elif se <= 0:
            lower, upper = c._mul(b, d), c._mul(a, d)
        else:
            lo0, lo1 = c._mul(a, e), c._mul(b, d)
            hi0, hi1 = c._mul(a, d), c._mul(b, e)
            lower = lo0 if c._compare(lo0, lo1) <= 0 else lo1
            upper = hi0 if c._compare(hi0, hi1) >= 0 else hi1
        return self._result(lower, upper)

    def mul(self, left: DyadicInterval, right: DyadicInterval) -> DyadicInterval:
        return self._mul(self._value(left), self._value(right))

    def scale(self, value: DyadicInterval, factor: Dyadic | int) -> DyadicInterval:
        """Multiply an enclosure by an exact factor (not a binary64 value)."""
        return self._mul(self._value(value), self.point(factor))

    def _div(self, numerator: DyadicInterval, denominator: DyadicInterval) -> DyadicInterval:
        c, p = self.context, self.precision
        low_sign = c._icmp(denominator.lower.mantissa, 0)
        high_sign = c._icmp(denominator.upper.mantissa, 0)
        if low_sign <= 0 <= high_sign:
            raise PrimitiveError("interval_zero_divisor")
        if high_sign < 0:
            numerator, denominator = self._neg(numerator), self._neg(denominator)
        if c._icmp(numerator.lower.mantissa, 0) >= 0:
            lower_den, upper_den = denominator.upper, denominator.lower
        elif c._icmp(numerator.upper.mantissa, 0) <= 0:
            lower_den, upper_den = denominator.lower, denominator.upper
        else:
            lower_den = upper_den = denominator.lower
        return c._interval(
            c._divide(numerator.lower, lower_den, p, upward=False),
            c._divide(numerator.upper, upper_den, p, upward=True),
            p,
        )

    def div(self, numerator: DyadicInterval, denominator: DyadicInterval) -> DyadicInterval:
        return self._div(self._value(numerator), self._value(denominator))

    def _sqrt(self, value: DyadicInterval) -> DyadicInterval:
        c, p = self.context, self.precision
        if c._icmp(value.lower.mantissa, 0) < 0:
            raise PrimitiveError("negative_radicand")
        lower = c.sqrt_enclosure(value.lower, p)
        if c._compare(value.lower, value.upper) == 0:
            return lower
        upper = c.sqrt_enclosure(value.upper, p)
        return c._interval(lower.lower, upper.upper, p)

    def sqrt(self, value: DyadicInterval) -> DyadicInterval:
        return self._sqrt(self._value(value))

    def abs(self, value: DyadicInterval) -> DyadicInterval:
        value = self._value(value)
        c = self.context
        if c._icmp(value.lower.mantissa, 0) >= 0:
            return value
        if c._icmp(value.upper.mantissa, 0) <= 0:
            return self._neg(value)
        negative_lower = c._neg(value.lower)
        upper = negative_lower if c._compare(negative_lower, value.upper) >= 0 else value.upper
        return self._result(_ZERO, upper)

    def _atan_coefficients(self) -> tuple[DyadicInterval, ...]:
        if self._coefficients is None:
            c, p = self.context, self.precision
            coefficients = []
            for k in range(129):
                # Series denominators are scalar values, so even their bounded
                # construction uses the shared checked integer operations.
                denominator = c._make(c._iadd(c._imul(2, k), 1), 0)
                coefficients.append(
                    c._interval(
                        c._divide(_ONE, denominator, p, upward=False),
                        c._divide(_ONE, denominator, p, upward=True),
                        p,
                    )
                )
            object.__setattr__(self, "_coefficients", tuple(coefficients))
        return self._coefficients

    def _atan_series(self, value: DyadicInterval) -> DyadicInterval:
        """128 alternating terms and the positive next-term remainder.

        For 0 <= x <= 1/4, t=x*x and the Horner recurrence evaluates exactly
        the polynomial sum(k=0..127) (-1)^k*x**(2*k+1)/(2*k+1), outwardly.
        The omitted alternating tail lies in [0, x**257/257]. Seven squarings
        produce t**128 for that explicit bound, without a refinement loop.
        """
        c = self.context
        if c._icmp(value.lower.mantissa, 0) < 0 or c._compare(value.upper, _QUARTER) > 0:
            raise PrimitiveError("atan_series_domain")
        coefficients = self._atan_coefficients()
        square = self._mul(value, value)
        polynomial = coefficients[127]
        for k in range(126, -1, -1):
            polynomial = self._sub(coefficients[k], self._mul(square, polynomial))
        partial = self._mul(value, polynomial)
        power = square
        for _ in range(7):
            power = self._mul(power, power)
        remainder = self._mul(self._mul(value, power), coefficients[128])
        tail = c._interval(_ZERO, remainder.upper, self.precision)
        return self._add(partial, tail)

    def pi(self) -> DyadicInterval:
        """Machin's identity, 16 atan(1/5) - 4 atan(1/239), with signed tails."""
        if self._pi is None:
            one = self.point(1)
            fifth = self._div(one, self.point(5))
            part = self._div(one, self.point(239))
            result = self._sub(
                self._mul(self.point(16), self._atan_series(fifth)),
                self._mul(self.point(4), self._atan_series(part)),
            )
            object.__setattr__(self, "_pi", result)
        return self._pi

    def directed_angle(self, cross: Dyadic, dot: Dyadic, direction: str) -> DyadicInterval:
        """Exact-ray signed angle: CCW in (0,2*pi), CW in (-2*pi,0).

        The input is the exact dyadic cross/dot pair of the authored rays.
        Signs and reciprocal reduction use that pair before interval rounding.
        Quadrant axes are explicit. Coincident positive rays and the zero pair
        do not specify a proper nonfull arc and are rejected. No modulo sweep
        or binary64 atan2 value participates in this enclosure.
        """
        c = self.context
        cross, dot = c._value(cross), c._value(dot)
        if type(direction) is not str or direction not in ("CW", "CCW"):
            raise PrimitiveError("invalid_direction")
        cross_sign, dot_sign = c._icmp(cross.mantissa, 0), c._icmp(dot.mantissa, 0)
        if cross_sign == 0:
            if dot_sign == 0:
                raise PrimitiveError("zero_angle_pair")
            if dot_sign > 0:
                raise PrimitiveError("coincident_arc_rays")
            return self._neg(self.pi()) if direction == "CW" else self.pi()
        elif dot_sign == 0:
            if cross_sign > 0:
                factor = Dyadic(-3, -1) if direction == "CW" else Dyadic(1, -1)
            else:
                factor = Dyadic(-1, -1) if direction == "CW" else Dyadic(3, -1)
            return self._mul(self.pi(), self.point(factor))
        else:
            y = c._neg(cross) if cross_sign < 0 else cross
            x = c._neg(dot) if dot_sign < 0 else dot
            reciprocal = c._compare(y, x) > 0
            numerator, denominator = (x, y) if reciprocal else (y, x)
            # Divide exact coefficients directly. Rounding them independently
            # first could turn an exactly <=1 ratio into an interval above 1.
            reduced = c._interval(
                c._divide(numerator, denominator, self.precision, upward=False),
                c._divide(numerator, denominator, self.precision, upward=True),
                self.precision,
            )
            one = self.point(1)
            for _ in range(2):
                root = self._sqrt(self._add(one, self._mul(reduced, reduced)))
                reduced = self._div(reduced, self._add(one, root))
            angle = self._mul(self.point(4), self._atan_series(reduced))
            if reciprocal:
                half_pi = self._mul(self.pi(), self.point(Dyadic(1, -1)))
                angle = self._sub(half_pi, angle)
            if dot_sign < 0:
                angle = self._sub(self.pi(), angle)
            if (cross_sign < 0) != (direction == "CW"):
                angle = self._sub(self._mul(self.point(2), self.pi()), angle)
        return self._neg(angle) if direction == "CW" else angle
