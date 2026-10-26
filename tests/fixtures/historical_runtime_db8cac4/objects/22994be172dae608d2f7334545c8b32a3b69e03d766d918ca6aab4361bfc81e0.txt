"""Isolated, bounded exact primitives for a proposed arc-profile policy.

This leaf does not admit profiles, change arc_geometry, or construct native
geometry. All input coordinates denote their exact binary64 values. A shared
PrimitiveContext is one non-resetting arithmetic budget; callers must not create
fresh contexts to evade an aggregate work limit.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

MAX_INTEGER_BITS = 65_536
MAX_OPERATIONS = 200_000
DEFAULT_OPERATIONS = 100_000
INTERVAL_PRECISIONS = (64, 128, 256)
MAX_INTERVAL_EXPONENT = 32_768
MAX_COORDINATE = 1_000_000
MIN_RADIUS = 1e-6
MAX_RADIUS = 1e6


class PrimitiveError(ValueError):
    """Data-free primitive failure; these codes are not service wire codes."""

    def __init__(self, code: str):
        # Only module-owned constants are passed here; never interpolate input.
        super().__init__(code)
        self.code = code


def _validate_dyadic(value: Dyadic, cap: int = MAX_INTEGER_BITS) -> None:
    if type(value) is not Dyadic:
        raise PrimitiveError("invalid_dyadic")
    try:
        m, e = value.mantissa, value.exponent
    except AttributeError:
        raise PrimitiveError("invalid_dyadic") from None
    if type(m) is not int or type(e) is not int:
        raise PrimitiveError("invalid_dyadic")
    if m.bit_length() > cap or not -cap < e < cap:
        raise PrimitiveError("integer_limit")
    if (m == 0 and e != 0) or (m != 0 and m & 1 == 0):
        raise PrimitiveError("invalid_dyadic")
    # Implicit numerator and denominator are bounded before any expansion.
    if m != 0 and (m.bit_length() + max(e, 0) > cap or 1 + max(-e, 0) > cap):
        raise PrimitiveError("integer_limit")


@dataclass(frozen=True, slots=True)
class Dyadic:
    """Exact mantissa * 2**exponent; odd nonzero mantissa, or exactly (0, 0)."""

    mantissa: int
    exponent: int

    def __post_init__(self) -> None:
        _validate_dyadic(self)


@dataclass(frozen=True, slots=True)
class DyadicInterval:
    """Closed parameter/value enclosure, with normalized significand precision."""

    lower: Dyadic
    upper: Dyadic
    precision: int


@dataclass(frozen=True, slots=True)
class SupportRoot:
    """One exact quadratic branch, with a bounded parameter enclosure.

    The owning SupportRoots coefficients define its exact value. MINUS/PLUS mean
    (-b -/+ sqrt(discriminant))/(2*a); DOUBLE means -b/(2*a).
    Position is exact even if this enclosure straddles 0 or 1.
    """

    branch: str
    multiplicity: int
    position: str
    parameter: DyadicInterval


@dataclass(frozen=True, slots=True)
class SupportRoots:
    """Complete real-root ledger for a nondegenerate line/circle support pair.

    Negative discriminant: roots=(). Zero: one DOUBLE of multiplicity two.
    Positive: two ordered, distinct simple roots, MINUS then PLUS, with disjoint
    parameter enclosures. This does not admit a join/profile, and a successful
    double root is not a transverse join. Unresolved isolation returns the
    separate UnresolvedSupportRoots type, never an instance of this class.
    """

    a: Dyadic
    b: Dyadic
    c: Dyadic
    discriminant: Dyadic
    roots: tuple[SupportRoot, ...]
    isolated: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class UnresolvedSupportRoots:
    """Ambiguity result retaining both roots and exact finite-line membership.

    The last 256-significand-bit enclosures overlap or touch; they are NOT
    isolating intervals. This separate type must never satisfy a later isolated
    root admission check. The code is primitive-only, not a wire error code.
    """

    a: Dyadic
    b: Dyadic
    c: Dyadic
    discriminant: Dyadic
    roots: tuple[SupportRoot, ...]
    isolated: bool = field(default=False, init=False)
    code: str = field(default="unresolved_isolation", init=False)


_ZERO = Dyadic(0, 0)
_ONE = Dyadic(1, 0)
_TWO = Dyadic(1, 1)
_FOUR = Dyadic(1, 2)


class PrimitiveContext:
    """Checked fixed-form arithmetic with read-only limits and work counter.

    Every integer arithmetic operation (including comparisons, division, isqrt,
    and normalization) is charged before execution. Bounded input parsing,
    bit-length queries, exponent bookkeeping and control flow are not scalar
    arithmetic operations. Additions precheck max operand bits + 1, products
    sum operand bits, and shifts operand bits + shift; cancellation never rescues
    an over-budget operation. Smaller limits are for tests, never larger limits.
    """

    __slots__ = ("_max_bits", "_max_operations", "_operations")

    def __init__(
        self, *, max_bits: int = MAX_INTEGER_BITS, max_operations: int = DEFAULT_OPERATIONS
    ):
        if hasattr(self, "_operations"):
            raise PrimitiveError("budget_already_initialized")
        if (
            type(max_bits) is not int
            or not 1 <= max_bits <= MAX_INTEGER_BITS
            or type(max_operations) is not int
            or not 1 <= max_operations <= MAX_OPERATIONS
        ):
            raise PrimitiveError("invalid_budget")
        object.__setattr__(self, "_max_bits", max_bits)
        object.__setattr__(self, "_max_operations", max_operations)
        object.__setattr__(self, "_operations", 0)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("PrimitiveContext state is read-only")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("PrimitiveContext state is read-only")

    @property
    def max_bits(self) -> int:
        return self._max_bits

    @property
    def max_operations(self) -> int:
        return self._max_operations

    @property
    def operations(self) -> int:
        return self._operations

    def _tick(self) -> None:
        if self._operations >= self._max_operations:
            raise PrimitiveError("operation_limit")
        object.__setattr__(self, "_operations", self._operations + 1)

    def _bits(self, bits: int) -> None:
        if bits > self._max_bits:
            raise PrimitiveError("integer_limit")

    def _integer(self, value: int) -> None:
        if type(value) is not int:
            raise PrimitiveError("invalid_integer")
        self._bits(value.bit_length())

    def _iadd(self, left: int, right: int) -> int:
        self._integer(left)
        self._integer(right)
        self._bits(max(left.bit_length(), right.bit_length()) + 1)
        self._tick()
        return left + right

    def _imul(self, left: int, right: int) -> int:
        self._integer(left)
        self._integer(right)
        self._bits(left.bit_length() + right.bit_length())
        self._tick()
        return left * right

    def _ineg(self, value: int) -> int:
        self._integer(value)
        self._tick()
        return -value

    def _ishift(self, value: int, shift: int) -> int:
        self._integer(value)
        if type(shift) is not int or shift < 0:
            raise PrimitiveError("invalid_shift")
        if shift > self.max_bits:
            raise PrimitiveError("integer_limit")
        self._bits(value.bit_length() + shift)
        self._tick()
        return value << shift

    def _iright(self, value: int, shift: int) -> int:
        self._integer(value)
        if type(shift) is not int or shift < 0:
            raise PrimitiveError("invalid_shift")
        if shift >= self.max_bits:
            raise PrimitiveError("integer_limit")
        self._bits(shift + 1)  # Also bound an implicit power-of-two divisor.
        self._tick()
        return value >> shift

    def _idivmod(self, numerator: int, denominator: int) -> tuple[int, int]:
        self._integer(numerator)
        self._integer(denominator)
        if denominator <= 0:
            raise PrimitiveError("invalid_divisor")
        self._tick()
        self._tick()
        return divmod(numerator, denominator)

    def _icmp(self, left: int, right: int) -> int:
        self._integer(left)
        self._integer(right)
        self._tick()
        return (left > right) - (left < right)

    def _make(self, mantissa: int, exponent: int) -> Dyadic:
        self._integer(mantissa)
        if type(exponent) is not int or not -self.max_bits < exponent < self.max_bits:
            raise PrimitiveError("integer_limit")
        if mantissa == 0:
            return _ZERO
        # Negation and bitwise normalization remain within the checked width.
        negative = self._ineg(mantissa)
        self._tick()
        zeros = (mantissa & negative).bit_length() - 1
        if zeros:
            mantissa = self._iright(mantissa, zeros)
            exponent += zeros
        result = Dyadic(mantissa, exponent)
        _validate_dyadic(result, self.max_bits)
        return result

    def _value(self, value: Dyadic) -> Dyadic:
        _validate_dyadic(value, self.max_bits)
        return value

    def _neg(self, value: Dyadic) -> Dyadic:
        self._value(value)
        return self._make(self._ineg(value.mantissa), value.exponent)

    def _add(self, left: Dyadic, right: Dyadic) -> Dyadic:
        self._value(left)
        self._value(right)
        if left.mantissa == 0:
            return right
        if right.mantissa == 0:
            return left
        exponent = min(left.exponent, right.exponent)
        lm = self._ishift(left.mantissa, left.exponent - exponent)
        rm = self._ishift(right.mantissa, right.exponent - exponent)
        return self._make(self._iadd(lm, rm), exponent)

    def _sub(self, left: Dyadic, right: Dyadic) -> Dyadic:
        return self._add(left, self._neg(right))

    def _mul(self, left: Dyadic, right: Dyadic) -> Dyadic:
        self._value(left)
        self._value(right)
        return self._make(self._imul(left.mantissa, right.mantissa), left.exponent + right.exponent)

    def _compare(self, left: Dyadic, right: Dyadic) -> int:
        self._value(left)
        self._value(right)
        self._tick()
        if left == right:
            return 0
        if left.mantissa <= 0 <= right.mantissa:
            return -1
        if right.mantissa <= 0 <= left.mantissa:
            return 1
        difference = self._sub(left, right)
        return self._icmp(difference.mantissa, 0)

    def coordinate(self, value: int | float) -> Dyadic:
        """Decode a finite binary64 coordinate in [-1e6, 1e6], without translation.

        Integers in that domain are exactly representable. float.hex is an exact,
        fixed-size binary64 decoder; mantissa parsing occurs only after a width
        check. No as_integer_ratio denominator is allocated ahead of the budget.
        """
        if type(value) not in (int, float):
            raise PrimitiveError("invalid_number")
        if type(value) is int:
            if value < -MAX_COORDINATE or value > MAX_COORDINATE:
                raise PrimitiveError("coordinate_domain")
            return self._make(value, 0)
        if not math.isfinite(value) or value < -MAX_COORDINATE or value > MAX_COORDINATE:
            raise PrimitiveError("coordinate_domain")
        if value == 0.0:
            return _ZERO
        encoded, exponent_text = value.hex().split("p")
        negative = encoded.startswith("-")
        digits = encoded.removeprefix("-").removeprefix("0x").replace(".", "")
        exponent = int(exponent_text) - 52
        # Strip hexadecimal trailing zeroes before allocating the integer.
        shortened = digits.rstrip("0").lstrip("0")
        exponent += 4 * (len(digits) - len(digits.rstrip("0")))
        self._bits(4 * (len(shortened) - 1) + int(shortened[0], 16).bit_length())
        mantissa = int(shortened, 16)
        if negative:
            mantissa = self._ineg(mantissa)
        return self._make(mantissa, exponent)

    def _point(self, value: tuple[int | float, int | float]) -> tuple[Dyadic, Dyadic]:
        if type(value) is not tuple or len(value) != 2:
            raise PrimitiveError("invalid_point")
        return self.coordinate(value[0]), self.coordinate(value[1])

    def vector(
        self, start: tuple[int | float, int | float], end: tuple[int | float, int | float]
    ) -> tuple[Dyadic, Dyadic]:
        """Exact end - start, after independently decoding each coordinate."""
        a, b = self._point(start), self._point(end)
        return self._sub(b[0], a[0]), self._sub(b[1], a[1])

    def _vector(self, value: tuple[Dyadic, Dyadic]) -> tuple[Dyadic, Dyadic]:
        if type(value) is not tuple or len(value) != 2:
            raise PrimitiveError("invalid_vector")
        return self._value(value[0]), self._value(value[1])

    def dot(self, left: tuple[Dyadic, Dyadic], right: tuple[Dyadic, Dyadic]) -> Dyadic:
        left, right = self._vector(left), self._vector(right)
        return self._add(self._mul(left[0], right[0]), self._mul(left[1], right[1]))

    def cross(self, left: tuple[Dyadic, Dyadic], right: tuple[Dyadic, Dyadic]) -> Dyadic:
        left, right = self._vector(left), self._vector(right)
        return self._sub(self._mul(left[0], right[1]), self._mul(left[1], right[0]))

    def discriminant(self, a: Dyadic, b: Dyadic, c: Dyadic) -> Dyadic:
        """Exact b*b - 4*a*c; its mantissa carries the exact sign."""
        a, b, c = self._value(a), self._value(b), self._value(c)
        return self._sub(self._mul(b, b), self._mul(_FOUR, self._mul(a, c)))

    def radical_sign(self, p: Dyadic, q: Dyadic, d: Dyadic) -> int:
        """Exact sign of p + q*sqrt(d), including equality and cancellation."""
        p, q, d = self._value(p), self._value(q), self._value(d)
        if d.mantissa < 0:
            raise PrimitiveError("negative_radicand")
        ps, qs = self._icmp(p.mantissa, 0), self._icmp(q.mantissa, 0)
        if qs == 0 or d.mantissa == 0:
            return ps
        if ps == 0 or ps == qs:
            return qs
        delta = self._compare(self._mul(p, p), self._mul(self._mul(q, q), d))
        return ps * delta

    def _precision(self, precision: int) -> None:
        if type(precision) is not int or precision not in INTERVAL_PRECISIONS:
            raise PrimitiveError("invalid_precision")

    def _endpoint(self, value: Dyadic, precision: int) -> Dyadic:
        self._precision(precision)
        self._value(value)
        if value.mantissa.bit_length() > precision:
            raise PrimitiveError("precision_limit")
        if not -MAX_INTERVAL_EXPONENT <= value.exponent <= MAX_INTERVAL_EXPONENT:
            raise PrimitiveError("exponent_limit")
        return value

    def _interval(self, lower: Dyadic, upper: Dyadic, precision: int) -> DyadicInterval:
        self._precision(precision)
        self._endpoint(lower, precision)
        self._endpoint(upper, precision)
        if self._compare(lower, upper) > 0:
            raise PrimitiveError("invalid_enclosure")
        return DyadicInterval(lower, upper, precision)

    def _round(self, value: Dyadic, precision: int, *, upward: bool) -> Dyadic:
        self._precision(precision)
        self._value(value)
        excess = value.mantissa.bit_length() - precision
        if excess <= 0:
            return self._endpoint(value, precision)
        lower = self._iright(value.mantissa, excess)
        restored = self._ishift(lower, excess)
        if upward and self._icmp(restored, value.mantissa) != 0:
            lower = self._iadd(lower, 1)
        return self._endpoint(self._make(lower, value.exponent + excess), precision)

    def sqrt_enclosure(self, d: Dyadic, precision: int = 64) -> DyadicInterval:
        """Enclose sqrt(d) with integer isqrt and verified exact square inequalities.

        If 2**k <= d < 2**(k+1), use grid exponent floor(k/2)-(p-1).
        The scaled floor sqrt is isqrt(floor(d/grid**2)). This identity holds
        also for a rational scaled radicand. Both final squares are checked.
        """
        d = self._value(d)
        self._precision(precision)
        if d.mantissa < 0:
            raise PrimitiveError("negative_radicand")
        if d.mantissa == 0:
            return self._interval(_ZERO, _ZERO, precision)
        log2 = d.mantissa.bit_length() - 1 + d.exponent
        exponent = log2 // 2 - (precision - 1)
        scale = d.exponent - 2 * exponent
        if scale >= 0:
            scaled = self._ishift(d.mantissa, scale)
        else:
            self._bits(1 - scale)  # Bound implicit denominator before scaling.
            scaled = self._iright(d.mantissa, -scale)
        self._tick()
        root = math.isqrt(scaled)
        lower = self._endpoint(self._make(root, exponent), precision)
        lower_square = self._mul(lower, lower)
        relation = self._compare(lower_square, d)
        if relation > 0:
            raise PrimitiveError("invalid_enclosure")
        upper = (
            lower
            if relation == 0
            else self._endpoint(self._make(self._iadd(root, 1), exponent), precision)
        )
        if self._compare(self._mul(upper, upper), d) < 0:
            raise PrimitiveError("invalid_enclosure")
        return self._interval(lower, upper, precision)

    def _divide(
        self, numerator: Dyadic, denominator: Dyadic, precision: int, *, upward: bool
    ) -> Dyadic:
        """One directed rational-to-normalized-dyadic division, with no Fraction."""
        self._precision(precision)
        numerator, denominator = self._value(numerator), self._value(denominator)
        if denominator.mantissa <= 0:
            raise PrimitiveError("invalid_divisor")
        if numerator.mantissa == 0:
            return _ZERO
        n, d = numerator.mantissa, denominator.mantissa
        positive_n = self._ineg(n) if n < 0 else n
        log2 = positive_n.bit_length() - d.bit_length()
        if log2 >= 0:
            comparison = self._icmp(positive_n, self._ishift(d, log2))
        else:
            comparison = self._icmp(self._ishift(positive_n, -log2), d)
        if comparison < 0:
            log2 -= 1
        exponent = numerator.exponent - denominator.exponent + log2 - (precision - 1)
        scale = precision - 1 - log2
        if scale >= 0:
            n = self._ishift(n, scale)
        else:
            d = self._ishift(d, -scale)
        quotient, remainder = self._idivmod(n, d)
        if upward and remainder:
            quotient = self._iadd(quotient, 1)
        result = self._endpoint(self._make(quotient, exponent), precision)
        check = self._compare(self._mul(result, denominator), numerator)
        if (upward and check < 0) or (not upward and check > 0):
            raise PrimitiveError("invalid_enclosure")
        return result

    def _position(self, b: Dyadic, denominator: Dyadic, d: Dyadic, branch: int) -> str:
        p = self._neg(b)
        q = self._make(branch, 0)
        start_sign = self.radical_sign(p, q, d)
        end_sign = self.radical_sign(self._sub(p, denominator), q, d)
        if start_sign < 0:
            return "BEFORE_START"
        if start_sign == 0:
            return "AT_START"
        if end_sign < 0:
            return "INTERIOR"
        return "AT_END" if end_sign == 0 else "AFTER_END"

    def _parameter(
        self, b: Dyadic, denominator: Dyadic, radical: DyadicInterval, branch: int
    ) -> DyadicInterval:
        p = radical.precision
        self._precision(p)
        negative_b = self._neg(b)
        if branch < 0:
            lower = self._sub(negative_b, radical.upper)
            upper = self._sub(negative_b, radical.lower)
        elif branch > 0:
            lower = self._add(negative_b, radical.lower)
            upper = self._add(negative_b, radical.upper)
        else:
            lower = upper = negative_b
        # Round after the interval addition, then after division. Exact
        # polynomial coefficients remain separate from interval significands.
        lower = self._round(lower, p, upward=False)
        upper = self._round(upper, p, upward=True)
        return self._interval(
            self._divide(lower, denominator, p, upward=False),
            self._divide(upper, denominator, p, upward=True),
            p,
        )

    def line_circle_roots(
        self,
        start: tuple[int | float, int | float],
        end: tuple[int | float, int | float],
        center: tuple[int | float, int | float],
        radius: int | float,
    ) -> SupportRoots | UnresolvedSupportRoots:
        """All roots of |start + t*(end-start) - center|**2 = radius**2.

        Points use the coordinate domain ±1e6; radius is a finite binary64 in
        [1e-6, 1e6]. These support-helper limits do NOT implement the proposed
        profile scale, arc domain, finite-arc membership, or any profile gate.
        Distinct endpoint coordinates are required, but no minimum line length.
        Precision follows exactly 64,128,256 and stops at the first strict
        interval separation. At most three attempts, never root clustering.
        """
        start, end, center = self._point(start), self._point(end), self._point(center)
        if type(radius) not in (int, float) or not MIN_RADIUS <= radius <= MAX_RADIUS:
            raise PrimitiveError("radius_domain")
        radius_exact = self.coordinate(radius)
        h = self._sub(end[0], start[0]), self._sub(end[1], start[1])
        offset = self._sub(start[0], center[0]), self._sub(start[1], center[1])
        a = self.dot(h, h)
        if a.mantissa == 0:
            raise PrimitiveError("degenerate_line")
        b = self._mul(_TWO, self.dot(h, offset))
        c = self._sub(self.dot(offset, offset), self._mul(radius_exact, radius_exact))
        d = self.discriminant(a, b, c)
        if d.mantissa < 0:
            return SupportRoots(a, b, c, d, ())
        denominator = self._mul(_TWO, a)
        if d.mantissa == 0:
            zero = self._interval(_ZERO, _ZERO, 64)
            root = SupportRoot(
                "DOUBLE",
                2,
                self._position(b, denominator, d, 0),
                self._parameter(b, denominator, zero, 0),
            )
            return SupportRoots(a, b, c, d, (root,))
        positions = self._position(b, denominator, d, -1), self._position(b, denominator, d, 1)
        for precision in INTERVAL_PRECISIONS:
            radical = self.sqrt_enclosure(d, precision)
            minus = self._parameter(b, denominator, radical, -1)
            plus = self._parameter(b, denominator, radical, 1)
            isolated = self._compare(minus.upper, plus.lower) < 0
            roots = (
                SupportRoot("MINUS", 1, positions[0], minus),
                SupportRoot("PLUS", 1, positions[1], plus),
            )
            if isolated:
                break
        if isolated:
            return SupportRoots(a, b, c, d, roots)
        return UnresolvedSupportRoots(a, b, c, d, roots)

    def _arc_position(
        self,
        start_ray: tuple[Dyadic, Dyadic],
        end_ray: tuple[Dyadic, Dyadic],
        rational: tuple[Dyadic, Dyadic],
        radical: tuple[Dyadic, Dyadic],
        d: Dyadic,
        turn: int,
        clockwise: bool,
    ) -> str:
        """Membership of rational + radical*sqrt(d) between nonzero rays.

        The caller proves distinct positive rays and a nonzero circle direction.
        A zero determinant is an endpoint only on the positive ray. For a CCW
        minor arc the two open half-plane tests intersect; for a major arc they
        unite. Antipodal rays use the single common open half-plane. Reversing
        direction reverses all three determinant signs, without angle arithmetic.
        """
        after_start = self.radical_sign(
            self.cross(start_ray, rational), self.cross(start_ray, radical), d
        )
        before_end = self.radical_sign(
            self.cross(rational, end_ray), self.cross(radical, end_ray), d
        )
        if (
            after_start == 0
            and self.radical_sign(self.dot(start_ray, rational), self.dot(start_ray, radical), d)
            > 0
        ):
            return "AT_START"
        if (
            before_end == 0
            and self.radical_sign(self.dot(end_ray, rational), self.dot(end_ray, radical), d) > 0
        ):
            return "AT_END"
        if clockwise:
            after_start = self._ineg(after_start)
            before_end = self._ineg(before_end)
            turn = self._ineg(turn)
        interior = (
            after_start > 0 or before_end > 0 if turn < 0 else after_start > 0 and before_end > 0
        )
        return "INTERIOR" if interior else "OUTSIDE"

    def line_arc_roots(
        self,
        start: tuple[int | float, int | float],
        end: tuple[int | float, int | float],
        center: tuple[int | float, int | float],
        radius: int | float,
        *,
        arc_start: tuple[int | float, int | float],
        arc_end: tuple[int | float, int | float],
        direction: str,
    ) -> ArcSupportRoots | UnresolvedArcSupportRoots:
        """Attach exact finite-arc membership to every line/circle support root.

        arc_start/end are authored points, NOT already translated vectors. Their
        exact differences from center define the start/end rays. Direction must
        be the built-in string "CW" or "CCW". Nonzero, distinct positive rays
        select a proper nonfull arc; antipodal rays select an exact semicircle.
        The supplied canonical radius is never derived, averaged or adjusted to
        either point. All coordinates and radius keep the support-helper domain,
        independently of any future profile scale or sweep restrictions.

        This method recomputes its own support ledger using this same context;
        caller-fabricated evidence is never an input. Each original SupportRoot
        is retained unchanged, including finite-line position and multiplicity.
        Membership does not use its interval or assume it is isolated. Ambiguous
        isolation remains a distinct result type with both memberships attached.
        No profile, core-sweep correspondence or native trim is certified here.
        """
        if type(direction) is not str or direction not in ("CW", "CCW"):
            raise PrimitiveError("invalid_direction")
        start_ray, end_ray = self.vector(center, arc_start), self.vector(center, arc_end)
        if (start_ray[0].mantissa == 0 and start_ray[1].mantissa == 0) or (
            end_ray[0].mantissa == 0 and end_ray[1].mantissa == 0
        ):
            raise PrimitiveError("zero_arc_ray")
        turn = self._compare(self.cross(start_ray, end_ray), _ZERO)
        if turn == 0 and self._compare(self.dot(start_ray, end_ray), _ZERO) > 0:
            raise PrimitiveError("coincident_arc_rays")
        support = self.line_circle_roots(start, end, center, radius)
        memberships = []
        if support.roots:
            h, offset = self.vector(start, end), self.vector(center, start)
            denominator = self._mul(_TWO, support.a)
            # Multiplication by positive 2A preserves every direction sign:
            # 2A*(root-center) = (2A*offset-B*h) +/- sqrt(D)*h.
            rational = (
                self._sub(self._mul(denominator, offset[0]), self._mul(support.b, h[0])),
                self._sub(self._mul(denominator, offset[1]), self._mul(support.b, h[1])),
            )
            for root in support.roots:
                branch = self._make({"MINUS": -1, "DOUBLE": 0, "PLUS": 1}[root.branch], 0)
                radical = self._mul(branch, h[0]), self._mul(branch, h[1])
                position = self._arc_position(
                    start_ray,
                    end_ray,
                    rational,
                    radical,
                    support.discriminant,
                    turn,
                    direction == "CW",
                )
                memberships.append(ArcSupportRoot(root, position))
        if type(support) is UnresolvedSupportRoots:
            return UnresolvedArcSupportRoots(support, tuple(memberships))
        return ArcSupportRoots(support, tuple(memberships))


@dataclass(frozen=True, slots=True)
class ArcSupportRoot:
    """An unchanged original root and its exact original finite-arc membership.

    arc_position is OUTSIDE, AT_START, INTERIOR or AT_END. The support record's
    independent finite-line position is never filtered or replaced. Like the
    base ledger records, this detached record is not an evidence validator.
    """

    support: SupportRoot
    arc_position: str


@dataclass(frozen=True, slots=True)
class ArcSupportRoots:
    """Complete isolated support ledger with membership for every original root.

    No roots, or a multiplicity-two tangent, remain valid primitive outcomes;
    neither supplies a transverse-profile admission. Public constructors are
    detached data containers, not validators of caller-manufactured evidence.
    """

    support: SupportRoots
    roots: tuple[ArcSupportRoot, ...]
    isolated: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class UnresolvedArcSupportRoots:
    """Non-isolated support roots with exact memberships, retained as ambiguity.

    This separate type is never an ArcSupportRoots instance. Both root branches,
    their overlapping enclosures and exact memberships survive unchanged. It
    cannot establish isolated roots, a join, a profile, or a native trim.
    """

    support: UnresolvedSupportRoots
    roots: tuple[ArcSupportRoot, ...]
    isolated: bool = field(default=False, init=False)
    code: str = field(default="unresolved_isolation", init=False)
