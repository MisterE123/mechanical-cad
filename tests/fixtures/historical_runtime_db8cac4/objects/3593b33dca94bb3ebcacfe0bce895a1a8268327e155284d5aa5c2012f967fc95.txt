"""Bounded, native-free conversion of a freshly certified sector reference.

Public records are detached data, never permission to construct a native shape.
The public geometry entry recomputes its source; the private continuation is only
for the genuine Sketch adapter that just classified in the same checked context.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace

from .arc_profile_intervals import IntervalContext
from .arc_profile_primitives import (
    DEFAULT_OPERATIONS,
    MAX_OPERATIONS,
    ArcSupportRoot,
    ArcSupportRoots,
    Dyadic,
    DyadicInterval,
    PrimitiveContext,
    SupportRoot,
    SupportRoots,
)
from .arc_profile_sector_policy import (
    CenterProxy,
    CircleDiskExit,
    ExactRatio,
    OuterDisk,
    RadialDiskExit,
    ResourceUsage,
    RootAssignment,
    SectorCertificate,
    _context,
    _outer_disk,
    _record_bytes,
    classify_sector_geometry,
)
from .arc_profile_sector_source import BoundaryLedger, IncidenceReport, SectorGeometrySource


class NativePlanError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class NativePlane:
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    quaternion: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class NativeFrame:
    origin: tuple[float, float, float]
    u: tuple[float, float, float]
    v: tuple[float, float, float]
    normal: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class NativeSupportCircleRoots:
    line_id: str
    point_id: str
    squared_norm: Dyadic
    radius: Dyadic
    trim_parameter: Dyadic
    a: Dyadic
    b: Dyadic
    c: Dyadic
    discriminant: Dyadic
    parameters: tuple[DyadicInterval, DyadicInterval]
    memberships: tuple[str, str]
    norm_difference: Dyadic
    endpoint_circle_gap: DyadicInterval
    multiplicities: tuple[int, int] = (1, 1)


@dataclass(frozen=True, slots=True)
class NativeLine:
    entity_id: str
    point_id: str
    direction: tuple[float, float]
    length: float
    trim_parameter: float
    squared_norm: Dyadic
    affine_error_squared: Dyadic
    root_gap: DyadicInterval
    root_vector: tuple[DyadicInterval, DyadicInterval]
    support_circle_roots: NativeSupportCircleRoots


@dataclass(frozen=True, slots=True)
class NativeDiskRoots:
    line_id: str
    point_id: str
    kind: str
    radius: ExactRatio
    a: Dyadic
    b: Dyadic
    c: Dyadic
    discriminant: Dyadic
    denominator: Dyadic
    parameters: tuple[DyadicInterval, DyadicInterval]
    memberships: tuple[str, str]
    endpoint_inside_margin: Dyadic
    circle_root_inside_margin: Dyadic
    foreign_ray_exclusion_margin: Dyadic
    negative_circle_root_exclusion: Dyadic


@dataclass(frozen=True, slots=True)
class NativeCenterRoots:
    line_id: str
    squared_norm: Dyadic
    radius: ExactRatio
    parameters: tuple[DyadicInterval, DyadicInterval]
    memberships: tuple[str, str]
    finite_exit_margin: Dyadic
    multiplicities: tuple[int, int] = (1, 1)


@dataclass(frozen=True, slots=True)
class NativeRadialDirection:
    entity_id: str
    direction: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class NativeActualSupport:
    version: int
    intended_plan_sha256: str
    directions: tuple[NativeRadialDirection, NativeRadialDirection]
    lines: tuple[NativeLine, NativeLine]
    radial_disk_roots: tuple[NativeDiskRoots, ...]
    center_proxy_roots: tuple[NativeCenterRoots, NativeCenterRoots]
    ray_dot: Dyadic
    ray_cross: Dyadic
    native_angle: DyadicInterval
    representation_area_allowance: DyadicInterval
    native_reference_area: DyadicInterval
    native_class_area: DyadicInterval
    line_collar_margins: tuple[Dyadic, Dyadic]
    frozen_cell_radius: ExactRatio
    auxiliary_root_count: int
    source_support_root_count: int
    retained_root_count: int
    precision: int
    resources: ResourceUsage


@dataclass(frozen=True, slots=True)
class NativePeriodicTrim:
    original_parameters: tuple[float, float]
    canonical_parameters: tuple[float, float]
    turn_count: int
    binary_period: float
    mathematical_period: DyadicInterval
    addition_residuals: tuple[Dyadic, Dyadic]
    period_residual: DyadicInterval
    phase_residuals: tuple[DyadicInterval, DyadicInterval]
    phase_bounds: tuple[Dyadic, Dyadic]
    original_span: Dyadic
    canonical_span: Dyadic
    span_residual: Dyadic


@dataclass(frozen=True, slots=True)
class NativePlan:
    version: int
    source: SectorCertificate
    plane: NativePlane
    frame: NativeFrame
    center: tuple[float, float]
    vertices: tuple[tuple[str, tuple[float, float, float]], ...]
    radius: float
    parameters: tuple[float, float]
    increasing_parameters: tuple[float, float]
    lines: tuple[NativeLine, NativeLine]
    circle_vectors: tuple[tuple[DyadicInterval, DyadicInterval], ...]
    circle_gaps: tuple[DyadicInterval, DyadicInterval]
    final_cell_radius: ExactRatio
    final_source_cells: tuple[OuterDisk, ...]
    radial_disk_roots: tuple[NativeDiskRoots, ...]
    center_proxy_roots: tuple[NativeCenterRoots, NativeCenterRoots]
    native_circle_exit_memberships: tuple[tuple[str, str, tuple[str, str]], ...]
    native_angle: DyadicInterval
    representation_area_allowance: DyadicInterval
    native_reference_area: DyadicInterval
    native_class_area: DyadicInterval
    source_comparison_area: DyadicInterval
    area_allowance: DyadicInterval
    source_area_midpoint: DyadicInterval
    local_scale_squared: Dyadic
    world_scale: Dyadic
    resources: ResourceUsage
    intent_norm_errors: tuple[Dyadic, Dyadic]
    periodic_trim: NativePeriodicTrim
    original_circle_gaps: tuple[DyadicInterval, DyadicInterval]
    original_cell_radius: ExactRatio
    auxiliary_root_count: int
    source_support_root_count: int
    retained_root_count: int
    accepted_support: NativeActualSupport | None = None


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise NativePlanError(code)


def _number(c: PrimitiveContext, value: int | float) -> Dyadic:
    """Exact bounded binary64 decoder, also suitable for native masses."""
    if type(value) is int:
        c._integer(value)
        return c._make(value, 0)
    if type(value) is not float or not math.isfinite(value):
        raise NativePlanError("invalid_native_number")
    if value == 0:
        return c._make(0, 0)
    digits, exponent = value.hex().split("p")
    negative = digits.startswith("-")
    digits = digits.removeprefix("-").removeprefix("0x").replace(".", "")
    c._bits(4 * len(digits))
    integer = int(digits, 16)
    return c._make(c._ineg(integer) if negative else integer, int(exponent) - 52)


def _sum(c: PrimitiveContext, values) -> Dyadic:
    result = c._make(0, 0)
    for value in values:
        result = c._add(result, value)
    return result


def _sq(c: PrimitiveContext, value: Dyadic) -> Dyadic:
    return c._mul(value, value)


def _si(i: IntervalContext, value: DyadicInterval) -> DyadicInterval:
    value = i.abs(value)
    return i._mul(value, value)


def _norm(i: IntervalContext, vector) -> DyadicInterval:
    squared = i.point(0)
    for value in vector:
        squared = i._add(squared, _si(i, value))
    return i._sqrt(squared)


def _delta(c: PrimitiveContext, value: Dyadic) -> None:
    _require(
        c._compare(c._mul(value, c._make(1_000_000_000, 0)), c._make(1, 0)) <= 0,
        "native_endpoint_discrepancy",
    )


def transform(frame: NativeFrame, point: tuple[float, float]) -> tuple[float, float, float]:
    """Exact signed selection; no translation or summed floating products."""
    return tuple(
        float(point[0] * a if a else point[1] * b if b else 0.0)
        for a, b in zip(frame.u, frame.v, strict=True)
    )


def _frame(c: PrimitiveContext, plane: NativePlane) -> NativeFrame:
    _require(type(plane) is NativePlane, "invalid_native_plane")
    _require(hasattr(plane, "origin") and hasattr(plane, "quaternion"), "invalid_native_plane")
    _require(
        type(plane.origin) is tuple
        and len(plane.origin) == 3
        and type(plane.quaternion) is tuple
        and len(plane.quaternion) == 4,
        "invalid_native_plane",
    )
    for value in plane.origin + plane.quaternion:
        _require(
            type(value) in (int, float)
            and -1_000_000 <= value <= 1_000_000
            and math.isfinite(value),
            "invalid_native_plane",
        )
    _require(all(value == 0 for value in plane.origin), "unsupported_native_frame")
    _require(
        all(-1.00000001 <= value <= 1.00000001 for value in plane.quaternion)
        and math.isclose(
            sum(value * value for value in plane.quaternion), 1.0, rel_tol=0.0, abs_tol=1e-9
        ),
        "unsupported_native_frame",
    )
    w, x, y, z = tuple(c.coordinate(value) for value in plane.quaternion)
    n = _sum(c, (_sq(c, value) for value in (w, x, y, z)))
    _require(n.mantissa > 0, "unsupported_native_frame")
    two = c._make(2, 0)

    def mul2(a, b):
        return c._mul(two, c._mul(a, b))

    entries = (
        c._sub(n, c._mul(two, c._add(_sq(c, y), _sq(c, z)))),
        c._sub(mul2(x, y), mul2(w, z)),
        c._add(mul2(x, z), mul2(w, y)),
        c._add(mul2(x, y), mul2(w, z)),
        c._sub(n, c._mul(two, c._add(_sq(c, x), _sq(c, z)))),
        c._sub(mul2(y, z), mul2(w, x)),
        c._sub(mul2(x, z), mul2(w, y)),
        c._add(mul2(y, z), mul2(w, x)),
        c._sub(n, c._mul(two, c._add(_sq(c, x), _sq(c, y)))),
    )
    matrix = []
    for value in entries:
        if value.mantissa == 0:
            matrix.append(0.0)
        elif c._compare(value, n) == 0:
            matrix.append(1.0)
        elif c._compare(value, c._neg(n)) == 0:
            matrix.append(-1.0)
        else:
            raise NativePlanError("unsupported_native_frame")
    rows = tuple(tuple(matrix[3 * j : 3 * j + 3]) for j in range(3))
    _require(
        all(sum(v != 0 for v in row) == 1 for row in rows)
        and all(sum(rows[j][k] != 0 for j in range(3)) == 1 for k in range(3)),
        "unsupported_native_frame",
    )
    u, v, normal = (tuple(rows[j][k] for j in range(3)) for k in range(3))
    _require(
        (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]) == normal,
        "unsupported_native_frame",
    )
    return NativeFrame(tuple(float(x) for x in plane.origin), u, v, normal)


class _ContinuationIntervals(IntervalContext):
    """Private fresh-result continuation; no public cache seeding or reset."""

    __slots__ = ("_source_pi",)

    def __init__(self, context, source):
        super().__init__(context, source.area.precision)
        self._value(source.area.pi)
        object.__setattr__(self, "_source_pi", source.area.pi)

    def pi(self):
        return self._source_pi


class _Trig:
    """One checked coefficient cache; 128 terms and explicit Lagrange tails."""

    def __init__(self, intervals: IntervalContext):
        self.i = intervals
        c = intervals.context
        factorial = c._make(1, 0)
        coefficients = [intervals.point(1)]
        for degree in range(1, 258):
            factorial = c._mul(factorial, c._make(degree, 0))
            coefficients.append(
                c._interval(
                    c._divide(Dyadic(1, 0), factorial, intervals.precision, upward=False),
                    c._divide(Dyadic(1, 0), factorial, intervals.precision, upward=True),
                    intervals.precision,
                )
            )
        self.coefficients = tuple(coefficients)

    def sincos(self, value: float):
        i, c = self.i, self.i.context
        _require(
            type(value) is float and math.isfinite(value) and -8 <= value <= 8,
            "unsupported_native_parameter",
        )
        if value == 0:
            return i.point(0), i.point(1)
        exact_t = _number(c, value)
        exact_t2 = c._mul(exact_t, exact_t)
        t = i.point(exact_t)
        t2 = i.point(exact_t2)

        def scale_square(interval):
            # t² is one exact nonnegative dyadic, established above. All
            # products remain checked; only generic interval sign dispatch is
            # avoided. Outward normalization is unchanged.
            return i._result(c._mul(exact_t2, interval.lower), c._mul(exact_t2, interval.upper))

        outputs = []
        for odd in (True, False):
            degree = 255 if odd else 254
            polynomial = self.coefficients[degree]
            for k in range(126, -1, -1):
                polynomial = i._sub(self.coefficients[2 * k + int(odd)], scale_square(polynomial))
            if odd:
                lo, hi = (
                    (polynomial.lower, polynomial.upper)
                    if exact_t.mantissa > 0
                    else (polynomial.upper, polynomial.lower)
                )
                partial = i._result(c._mul(exact_t, lo), c._mul(exact_t, hi))
            else:
                partial = polynomial
            power = t2
            for _ in range(7):
                power = i._mul(power, power)
            if odd:
                power = i._mul(i.abs(t), power)
            tail = i._mul(power, self.coefficients[257 if odd else 256])
            outputs.append(
                i._add(partial, c._interval(c._neg(tail.upper), tail.upper, i.precision))
            )
        return tuple(outputs)


def _line(c, i, arc, ledger, endpoint, radius, trim_parameter):
    center = arc.center
    h = tuple(float(endpoint[k]) - float(center[k]) for k in range(2))
    length = math.hypot(*h)
    _require(length > 0 and math.isfinite(length), "invalid_native_line")
    direction = (h[0] / length, h[1] / length)
    return _line_from_direction(
        c,
        i,
        arc,
        ledger.line_id,
        ledger.support_end_id,
        endpoint,
        radius,
        direction,
        length,
        trim_parameter,
    )


def _line_from_direction(
    c, i, arc, entity_id, point_id, endpoint, radius, direction, length, trim_parameter
):
    d = tuple(c.coordinate(v) for v in direction)
    v = c.vector(arc.center, endpoint)
    a, dot = c.dot(d, d), c.dot(d, v)
    _require(a.mantissa > 0 and dot.mantissa > 0, "native_line_alignment")
    _require(
        type(trim_parameter) is float
        and math.isfinite(trim_parameter)
        and 1 <= trim_parameter <= 1000,
        "invalid_native_trim_parameter",
    )
    ell = c.coordinate(trim_parameter)
    _require(c._compare(ell, radius) == 0, "native_trim_radius_changed")
    error = tuple(c._sub(c._mul(ell, d[k]), v[k]) for k in range(2))
    error2 = c.dot(error, error)
    _require(
        c._compare(c._mul(error2, c._make(10**18, 0)), c._make(1, 0)) <= 0,
        "native_whole_trace_displacement",
    )
    norm = c.sqrt_enclosure(a, i.precision)
    root = tuple(i._div(i.point(c._mul(radius, part)), norm) for part in d)
    gap = _norm(i, tuple(i._sub(root[k], i.point(v[k])) for k in range(2)))
    _delta(c, gap.upper)
    support = _support_circle_roots(c, i, entity_id, point_id, a, radius, ell, norm)
    return NativeLine(
        entity_id, point_id, direction, length, trim_parameter, a, error2, gap, root, support
    )


def _support_circle_roots(c, i, line_id, point_id, a, radius, trim, norm):
    """Both support roots; finite membership does not assert directed arc membership."""
    zero, one = c._make(0, 0), c._make(1, 0)
    constant = c._neg(c._mul(radius, radius))
    discriminant = c.discriminant(a, zero, constant)
    _require(
        a.mantissa > 0 and radius.mantissa > 0 and discriminant.mantissa > 0,
        "native_support_circle_nontransverse",
    )
    _require(c._compare(trim, radius) == 0, "native_trim_radius_changed")
    positive = i._div(i.point(radius), norm)
    negative = i._neg(positive)
    _require(
        negative.upper.mantissa < 0 and positive.lower.mantissa > 0,
        "unresolved_native_support_circle_roots",
    )
    difference = c._sub(a, one)
    position = (
        "INTERIOR" if difference.mantissa > 0 else "AFTER_END" if difference.mantissa < 0 else "END"
    )
    residual = i._mul(i.point(radius), i.abs(i._sub(norm, i.point(one))))
    return NativeSupportCircleRoots(
        line_id,
        point_id,
        a,
        radius,
        trim,
        a,
        zero,
        constant,
        discriminant,
        (negative, positive),
        ("BEFORE_START", position),
        difference,
        residual,
    )


def _radial_disk(c, i, line, other, v, radius, disk_radius, kind):
    d = tuple(c.coordinate(part) for part in line.direction)
    other_d = tuple(c.coordinate(part) for part in other.direction)
    ell = c.coordinate(line.trim_parameter)
    n, k = disk_radius.numerator, disk_radius.denominator
    n2, k2, s = _sq(c, n), _sq(c, k), c.dot(v, v)
    a = c._mul(line.squared_norm, k2)
    b = c._mul(c._make(-2, 0), c._mul(c.dot(d, v), k2))
    constant = c._sub(c._mul(s, k2), n2)
    disc = c.discriminant(a, b, constant)
    denominator = c._mul(c._make(2, 0), a)
    _require(
        a.mantissa > 0 and constant.mantissa > 0 and disc.mantissa > 0, "native_disk_nontransverse"
    )
    radical = c.sqrt_enclosure(disc, i.precision)
    parameters = tuple(c._parameter(b, denominator, radical, branch) for branch in (-1, 1))
    for branch, expected in ((-1, (1, -1)), (1, (1, 1))):
        signs = (
            c.radical_sign(c._neg(b), c._make(branch, 0), disc),
            c.radical_sign(c._sub(c._neg(b), c._mul(denominator, ell)), c._make(branch, 0), disc),
        )
        _require(signs == expected, "native_disk_finite_membership")
    _require(
        c._compare(parameters[0].upper, parameters[1].lower) < 0, "unresolved_native_disk_exits"
    )
    endpoint_margin = c._sub(n2, c._mul(line.affine_error_squared, k2))
    _require(endpoint_margin.mantissa > 0, "native_endpoint_outside_frozen_cell")
    # |r*d/sqrt(A)-v|^2 < rho^2, with positive alignment; homogeneous square.
    q = c._sub(c._mul(c._add(_sq(c, radius), s), k2), n2)
    j = c._mul(c._mul(c._make(2, 0), radius), c._mul(c.dot(d, v), k2))
    root_margin = c._sub(_sq(c, j), c._mul(_sq(c, q), line.squared_norm))
    _require(
        q.mantissa > 0 and j.mantissa > 0 and root_margin.mantissa > 0,
        "native_circle_root_outside_frozen_cell",
    )
    # A foreign outward ray's exact distance minimum, including positive projection.
    projection = c.dot(other_d, v)
    foreign = c._mul(constant, other.squared_norm)
    if projection.mantissa > 0:
        foreign = c._sub(foreign, c._mul(_sq(c, projection), k2))
    _require(foreign.mantissa > 0, "native_foreign_ray_enters_disk")
    negative_exclusion = q
    # q>0 and d.v>0 also exclude the negative circle root. Thus neither support
    # circle intersection is a disk exit: the retained circle/line exits differ.
    return NativeDiskRoots(
        line.entity_id,
        line.point_id,
        kind,
        disk_radius,
        a,
        b,
        constant,
        disc,
        denominator,
        parameters,
        ("INTERIOR", "AFTER_END"),
        endpoint_margin,
        root_margin,
        foreign,
        negative_exclusion,
    )


def _cross_i(i, a, b):
    return i._sub(i._mul(a[0], b[1]), i._mul(a[1], b[0]))


def _circle_memberships(c, i, disks, vectors, parameters):
    start, end = vectors
    if parameters[1] < parameters[0]:
        start, end = end, start
    span = c._sub(_number(c, max(parameters)), _number(c, min(parameters)))
    # The actual exact serialized span decides minor/major, never a modulo value.
    pi = disks[0][1]
    _require(
        c._compare(span, pi.lower) < 0 or c._compare(span, pi.upper) > 0,
        "unresolved_native_half_turn",
    )
    minor = c._compare(span, pi.lower) < 0
    results = []
    for disk, _ in disks:
        memberships = []
        for root in disk.circle_exits:
            radical = c.sqrt_enclosure(root.radicand, i.precision)
            vector = tuple(
                i._div(
                    i._add(i.point(root.rational[k]), i._mul(i.point(root.radical[k]), radical)),
                    i.point(root.denominator),
                )
                for k in range(2)
            )
            first, last = _cross_i(i, start, vector), _cross_i(i, vector, end)
            signs = []
            for value in (first, last):
                if value.lower.mantissa > 0:
                    signs.append(1)
                elif value.upper.mantissa < 0:
                    signs.append(-1)
                else:
                    raise NativePlanError("unresolved_native_circle_membership")
            inside = all(sign > 0 for sign in signs) if minor else any(sign > 0 for sign in signs)
            memberships.append("INTERIOR" if inside else "OUTSIDE")
        _require(
            tuple(memberships) == tuple(root.original_arc_position for root in disk.circle_exits),
            "native_circle_membership_changed",
        )
        results.append((disk.kind, disk.point_id, tuple(memberships)))
    return tuple(results)


def entry_context(context=None):
    """Create once at a genuine entry, or preserve the exact qualified context."""
    return PrimitiveContext(max_operations=MAX_OPERATIONS) if context is None else _context(context)


def prepare_native_geometry(source: SectorGeometrySource, plane: NativePlane, *, context=None):
    """Fresh shared-source classification; no supplied certificate is accepted."""
    c = entry_context(context)
    result = classify_sector_geometry(source, context=c)
    _require(result.status == "certified_sector", result.code)
    return _continue_native_plan(result.certificate, plane, c)


def _periodic_trim(c, i, parameters):
    """One prospective common shift, independent of every native observation."""
    _require(
        type(parameters) is tuple
        and len(parameters) == 2
        and all(type(t) is float and math.isfinite(t) and -8 <= t <= 8 for t in parameters),
        "unsupported_native_parameter",
    )
    period = float.fromhex("0x1.921fb54442d18p+2")
    lower = min(parameters)
    _require(-2 * period <= lower < period, "unsupported_native_periodic_domain")
    turns = 0 if lower >= 0 else 1 if lower >= -period else 2
    offset = turns * period
    canonical = tuple(t + offset for t in parameters)
    lo, hi = min(canonical), max(canonical)
    _require(0 <= lo < period and lo < hi < 12, "native_canonical_parameter_boundary")
    old = tuple(_number(c, t) for t in parameters)
    new = tuple(_number(c, t) for t in canonical)
    exact_period = _number(c, period)
    exact_offset = c._mul(c._make(turns, 0), exact_period)
    residuals = tuple(c._sub(c._sub(t1, t0), exact_offset) for t0, t1 in zip(old, new, strict=True))
    original_span = c._sub(old[1], old[0])
    canonical_span = c._sub(new[1], new[0])
    _require(
        original_span.mantissa != 0
        and canonical_span.mantissa != 0
        and (original_span.mantissa > 0) == (canonical_span.mantissa > 0),
        "native_periodic_direction_changed",
    )
    absolute_span = c._neg(canonical_span) if canonical_span.mantissa < 0 else canonical_span
    mathematical_period = i._mul(i.point(2), i.pi())
    _require(
        c._compare(absolute_span, exact_period) < 0
        and c._compare(absolute_span, mathematical_period.lower) < 0,
        "native_full_turn",
    )
    span_residual = c._sub(canonical_span, original_span)
    _require(
        c._compare(span_residual, c._sub(residuals[1], residuals[0])) == 0,
        "native_periodic_span_identity",
    )
    period_residual = i._sub(i.point(exact_period), mathematical_period)
    if turns == 0:
        _require(all(value.mantissa == 0 for value in residuals), "native_periodic_zero_turn")
        phases = (i.point(0), i.point(0))
    else:
        shift_residual = i._mul(i.point(turns), period_residual)
        phases = tuple(i._add(i.point(value), shift_residual) for value in residuals)
    bounds = tuple(i.abs(value).upper for value in phases)
    return NativePeriodicTrim(
        parameters,
        canonical,
        turns,
        period,
        mathematical_period,
        residuals,
        period_residual,
        phases,
        bounds,
        original_span,
        canonical_span,
        span_residual,
    )


def _common_cell_radius(c, source, gaps):
    """The original 16*max recipe, separately evaluated for each declared cell."""
    eta = list(g.eta for g in source.gap_enclosures)
    for gap in gaps:
        eta.append(ExactRatio(gap.upper, c._make(1, 0)))
    maximum = eta[0]
    for value in eta[1:]:
        if (
            c._compare(
                c._mul(value.numerator, maximum.denominator),
                c._mul(maximum.numerator, value.denominator),
            )
            > 0
        ):
            maximum = value
    return ExactRatio(c._mul(c._make(16, 0), maximum.numerator), maximum.denominator)


def _transport_periodic_component(c, i, component, bound):
    # Exact integer-turn periodicity plus the global derivative bound 1. A zero
    # phase retains the original interval, rather than manufacturing uncertainty.
    if bound.mantissa == 0:
        return component
    return i._result(c._sub(component.lower, bound), c._add(component.upper, bound))


def _continue_native_plan(
    source: SectorCertificate, plane: NativePlane, c: PrimitiveContext, *, operations_start=None
):
    """Internal continuation ONLY after the caller's fresh source classification."""
    _require(
        type(source) is SectorCertificate and type(c) is PrimitiveContext, "invalid_native_plan"
    )
    _require(c.operations == source.resources.operations_end, "native_context_discontinuity")
    _require(c.operations <= DEFAULT_OPERATIONS, "source_operation_limit")
    start = source.resources.operations_start if operations_start is None else operations_start
    _require(
        type(start) is int and 0 <= start <= source.resources.operations_start,
        "native_context_discontinuity",
    )
    frame = _frame(c, plane)
    report, area = source.incidence, source.area
    arc = report.arc
    radius_float = report.core_arcs[0][1].start_radius
    radius = c.coordinate(radius_float)
    center = tuple(float(v) for v in arc.center)
    a = math.atan2(float(arc.start[1]) - center[1], float(arc.start[0]) - center[0])
    sweep = report.core_arcs[0][1].sweep_radians
    b = a + sweep
    _require(
        -8 <= a <= 8 and -8 <= b <= 8 and ((b > a) == (arc.direction == "ccw")),
        "unsupported_native_parameter",
    )
    i = _ContinuationIntervals(c, source)
    theta = area.signed_angle
    sweep_error = i._mul(i.point(radius), i.abs(i._sub(theta, i.point(c.coordinate(sweep)))))
    _delta(c, sweep_error.upper)
    span = c._sub(c.coordinate(b), c.coordinate(a))
    _require(span.mantissa != 0, "native_zero_span")
    span_abs = c._neg(span) if span.mantissa < 0 else span
    _require(c._compare(span_abs, c._mul(c._make(2, 0), area.pi.lower)) < 0, "native_full_turn")
    trig = _Trig(i)
    rays = (c.vector(arc.center, arc.start), c.vector(arc.center, arc.end))
    original_components, original_gaps = [], []
    for parameter, ray in zip((a, b), rays, strict=True):
        sine, cosine = trig.sincos(parameter)
        vector = (i._mul(i.point(radius), cosine), i._mul(i.point(radius), sine))
        gap = _norm(i, tuple(i._sub(vector[k], i.point(ray[k])) for k in range(2)))
        _delta(c, gap.upper)
        original_components.append((cosine, sine))
        original_gaps.append(gap)
    original_rho = _common_cell_radius(c, source, original_gaps)
    periodic = _periodic_trim(c, i, (a, b))
    a, b = periodic.canonical_parameters
    span = periodic.canonical_span
    vectors, gaps = [], []
    for components, bound, ray in zip(
        original_components, periodic.phase_bounds, rays, strict=True
    ):
        vector = tuple(
            i._mul(i.point(radius), _transport_periodic_component(c, i, component, bound))
            for component in components
        )
        gap = _norm(i, tuple(i._sub(vector[k], i.point(ray[k])) for k in range(2)))
        _delta(c, gap.upper)
        vectors.append(vector)
        gaps.append(gap)
    # The serialized signed span remains on the certified source branch.
    branch_error = i.abs(i._sub(i.point(span), theta))
    _require(
        c._compare(
            i._mul(i.point(radius), branch_error).upper, i._div(i.point(3), i.point(10**9)).lower
        )
        <= 0,
        "native_unwrapped_branch",
    )
    rho = _common_cell_radius(c, source, gaps)
    # This final common radius is now frozen. Line checks can never enlarge it.
    _require(rho.numerator.mantissa > 0, "unresolved_zero_conversion_cell")
    lines = tuple(
        _line(c, i, arc, ledger, endpoint, radius, radius_float)
        for ledger, endpoint in zip(report.boundaries, (arc.start, arc.end), strict=True)
    )
    norm_errors = []
    for line in lines:
        error = c._sub(line.squared_norm, Dyadic(1, 0))
        if error.mantissa < 0:
            error = c._neg(error)
        _require(c._compare(error, Dyadic(1, -51)) <= 0, "native_normalization_precondition")
        norm_errors.append(error)
    d = tuple(tuple(c.coordinate(value) for value in line.direction) for line in lines)
    dot, cross = c.dot(*d), c.cross(*d)
    _require(
        dot.mantissa <= 0 and (cross.mantissa != 0 or dot.mantissa < 0),
        "native_ray_pair_unsupported",
    )
    # Exact quadrants reuse source pi rather than allocating a second pi series.
    if dot.mantissa == 0 or cross.mantissa == 0:
        _require(
            (dot.mantissa == 0) == (report.ray_dot.mantissa == 0)
            and (cross.mantissa == 0) == (source.jordan.ray_cross.mantissa == 0),
            "native_quadrant_changed",
        )
        _require(
            (cross.mantissa > 0) == (source.jordan.ray_cross.mantissa > 0)
            and (cross.mantissa < 0) == (source.jordan.ray_cross.mantissa < 0),
            "native_quadrant_changed",
        )
        native_theta = theta
    else:
        native_theta = i.directed_angle(cross, dot, arc.direction.upper())
    angle_difference = i.abs(i._sub(native_theta, theta))
    _require(
        c._compare(
            i._mul(i.point(radius), angle_difference).upper,
            i._div(i.point(2), i.point(10**9)).lower,
        )
        <= 0,
        "native_support_angle_budget",
    )
    rep = i._mul(i.point(c._mul(_sq(c, radius), Dyadic(1, -1))), angle_difference)
    cells = tuple(
        _outer_disk(c, i, report, rays, index, rho, "final_common_cell") for index in range(2)
    )
    proxy = ExactRatio(c._make(350, 0), c._make(10**9, 0))
    radial = tuple(
        _radial_disk(c, i, lines[index], lines[1 - index], rays[index], radius, disk_radius, kind)
        for kind, disk_radius in (("final_common_cell", rho), ("clearance_proxy", proxy))
        for index in range(2)
    )
    membership = _circle_memberships(
        c,
        i,
        tuple((disk, area.pi) for disk in cells + source.outer_proxies),
        tuple(vectors),
        (a, b),
    )
    # Frozen source clearance constants transfer: exact new roots establish the
    # same one-exit cap hypotheses, delta_N<=Delta, and d0.d1<=0.
    center_roots = []
    for line in lines:
        endpoint_error = c.sqrt_enclosure(line.affine_error_squared, i.precision)
        _require(
            c._compare(
                i._add(i._div(i.point(350), i.point(10**9)), endpoint_error).upper,
                i._div(i.point(400), i.point(10**9)).lower,
            )
            < 0,
            "native_line_collar",
        )
        _require(
            c._compare(
                c._mul(_sq(c, c.coordinate(line.trim_parameter)), line.squared_norm),
                i._mul(
                    i._div(i.point(350), i.point(10**9)), i._div(i.point(350), i.point(10**9))
                ).upper,
            )
            > 0,
            "native_center_proxy_no_exit",
        )
        b_i = i._div(i.point(proxy.numerator), i.point(proxy.denominator))
        parameter = i._div(b_i, c.sqrt_enclosure(line.squared_norm, i.precision))
        ell2a = c._mul(_sq(c, c.coordinate(line.trim_parameter)), line.squared_norm)
        margin = c._sub(c._mul(ell2a, _sq(c, proxy.denominator)), _sq(c, proxy.numerator))
        _require(
            parameter.lower.mantissa > 0 and margin.mantissa > 0, "native_center_proxy_no_exit"
        )
        center_roots.append(
            NativeCenterRoots(
                line.entity_id,
                line.squared_norm,
                proxy,
                (i._neg(parameter), parameter),
                ("BEFORE_START", "INTERIOR"),
                margin,
            )
        )
    auxiliary_count, support_count, full_count = _root_counts(
        source, cells, radial, tuple(center_roots), lines
    )
    _require(
        c._compare(
            c._mul(rho.numerator, proxy.denominator), c._mul(proxy.numerator, rho.denominator)
        )
        < 0,
        "native_cell_exceeds_proxy",
    )
    # Source R0, its floor/midpoint and later EV/C0 retain the exact old cell.
    # Only the native completion class below uses the new canonical cell.
    rho_i = i._div(i.point(original_rho.numerator), i.point(original_rho.denominator))
    allowance = i._mul(i._mul(i.point(2), area.pi), i._mul(rho_i, rho_i))
    source_comparison = i._result(
        c._sub(area.reference_area.lower, allowance.upper),
        c._add(area.reference_area.upper, allowance.upper),
    )
    _require(
        c._compare(
            c._mul(source_comparison.lower, area.area_floor.denominator), area.area_floor.numerator
        )
        >= 0,
        "native_source_area_floor",
    )
    native_reference = i._mul(i.point(c._mul(_sq(c, radius), Dyadic(1, -1))), i.abs(native_theta))
    canonical_rho_i = i._div(i.point(rho.numerator), i.point(rho.denominator))
    native_allowance = i._mul(i._mul(i.point(2), area.pi), i._mul(canonical_rho_i, canonical_rho_i))
    native_class = i._result(
        c._sub(native_reference.lower, native_allowance.upper),
        c._add(native_reference.upper, native_allowance.upper),
    )
    midpoint = i.point(
        c._mul(c._add(source_comparison.lower, source_comparison.upper), Dyadic(1, -1))
    )
    vertices = tuple(
        (identifier, transform(frame, tuple(float(x) for x in point)))
        for identifier, point in (
            (arc.center_id, arc.center),
            (arc.start_id, arc.start),
            (arc.end_id, arc.end),
        )
    )
    world = max(1.0, *(abs(value) for _, point in vertices for value in point))
    points = (arc.center, arc.start, arc.end)
    diagonal = tuple(
        c._sub(
            c.coordinate(max(point[k] for point in points)),
            c.coordinate(min(point[k] for point in points)),
        )
        for k in range(2)
    )
    scales = (c._make(1, 0), c.dot(diagonal, diagonal), _sq(c, radius))
    scale = scales[0]
    for value in scales[1:]:
        if c._compare(value, scale) > 0:
            scale = value
    ea = i._add(
        i.point(c._mul(Dyadic(3, -46), scale)),
        i._mul(i.point(c._mul(Dyadic(1, -49), c.coordinate(world))), i.point(area.perimeter.upper)),
    )
    exact_world = c.coordinate(world)
    usage = ResourceUsage(
        start, c.operations, c.max_bits, c.max_operations, source.resources.refinements
    )
    plan = NativePlan(
        1,
        source,
        plane,
        frame,
        center,
        vertices,
        radius_float,
        (a, b),
        (min(a, b), max(a, b)),
        lines,
        tuple(vectors),
        tuple(gaps),
        rho,
        cells,
        radial,
        tuple(center_roots),
        membership,
        native_theta,
        rep,
        native_reference,
        native_class,
        source_comparison,
        ea,
        midpoint,
        scale,
        exact_world,
        usage,
        tuple(norm_errors),
        periodic,
        tuple(original_gaps),
        original_rho,
        auxiliary_count,
        support_count,
        full_count,
    )
    plan_bytes(plan)
    return plan


def plan_bytes(plan: NativePlan) -> bytes:
    _require(type(plan) is NativePlan, "invalid_native_plan")
    return _record_bytes(
        plan,
        extra_record_types=(
            NativePlane,
            NativeFrame,
            NativeLine,
            NativeSupportCircleRoots,
            NativeDiskRoots,
            NativeCenterRoots,
            NativePlan,
            NativeRadialDirection,
            NativeActualSupport,
            NativePeriodicTrim,
        ),
    )


def _actual_direction(c, plan, intended, record):
    _require(type(record) is NativeRadialDirection, "invalid_native_direction_record")
    _require(
        hasattr(record, "entity_id") and hasattr(record, "direction"),
        "invalid_native_direction_record",
    )
    _require(
        type(record.entity_id) is str and record.entity_id == intended.entity_id,
        "native_direction_owner_changed",
    )
    values = record.direction
    _require(type(values) is tuple and len(values) == 3, "invalid_native_direction_record")
    expected = transform(plan.frame, intended.direction)
    for original, actual in zip(expected, values, strict=True):
        _require(
            type(actual) is float and math.isfinite(actual) and -2 <= actual <= 2,
            "invalid_native_direction_record",
        )
        if original == 0:
            _require(actual == 0, "native_zero_direction_changed")
        else:
            _require(
                (actual > 0) == (original > 0) and actual != 0, "native_direction_sign_changed"
            )
            error = c._sub(c.coordinate(actual), c.coordinate(original))
            if error.mantissa < 0:
                error = c._neg(error)
            _require(c._compare(error, Dyadic(1, -50)) <= 0, "native_direction_envelope_exceeded")
    # Exact signed component selection, never a floating dot-product inverse.
    return tuple(
        next(sign * values[k] for k, sign in enumerate(axis) if sign != 0)
        for axis in (plan.frame.u, plan.frame.v)
    )


def _actual_angle(c, i, plan, lines):
    source, arc = plan.source, plan.source.incidence.arc
    d = tuple(tuple(c.coordinate(value) for value in line.direction) for line in lines)
    dot, cross = c.dot(*d), c.cross(*d)
    _require(
        dot.mantissa <= 0 and (cross.mantissa != 0 or dot.mantissa < 0),
        "native_ray_pair_unsupported",
    )
    source_cross = source.jordan.ray_cross
    _require(
        (cross.mantissa > 0) == (source_cross.mantissa > 0)
        and (cross.mantissa < 0) == (source_cross.mantissa < 0),
        "native_support_branch_changed",
    )
    if dot.mantissa == 0 or cross.mantissa == 0:
        _require(
            (dot.mantissa == 0) == (source.incidence.ray_dot.mantissa == 0)
            and (cross.mantissa == 0) == (source_cross.mantissa == 0),
            "native_quadrant_changed",
        )
        theta = source.area.signed_angle
    else:
        theta = i.directed_angle(cross, dot, arc.direction.upper())
    difference = i.abs(i._sub(theta, source.area.signed_angle))
    radius = c.coordinate(plan.radius)
    _require(
        c._compare(
            i._mul(i.point(radius), difference).upper, i._div(i.point(2), i.point(10**9)).lower
        )
        <= 0,
        "native_support_angle_budget",
    )
    rep = i._mul(i.point(c._mul(_sq(c, radius), Dyadic(1, -1))), difference)
    return dot, cross, theta, rep


def _actual_center_roots(c, i, lines, proxy):
    roots, collars = [], []
    for line in lines:
        endpoint_error = c.sqrt_enclosure(line.affine_error_squared, i.precision)
        b = i._div(i.point(proxy.numerator), i.point(proxy.denominator))
        collar_margin = c._sub(
            i._div(i.point(400), i.point(10**9)).lower, i._add(b, endpoint_error).upper
        )
        _require(collar_margin.mantissa > 0, "native_line_collar")
        parameter = i._div(b, c.sqrt_enclosure(line.squared_norm, i.precision))
        ell2a = c._mul(_sq(c, c.coordinate(line.trim_parameter)), line.squared_norm)
        margin = c._sub(c._mul(ell2a, _sq(c, proxy.denominator)), _sq(c, proxy.numerator))
        _require(
            parameter.lower.mantissa > 0 and margin.mantissa > 0, "native_center_proxy_no_exit"
        )
        roots.append(
            NativeCenterRoots(
                line.entity_id,
                line.squared_norm,
                proxy,
                (i._neg(parameter), parameter),
                ("BEFORE_START", "INTERIOR"),
                margin,
            )
        )
        collars.append(collar_margin)
    return tuple(roots), tuple(collars)


def _source_support_root_count(source):
    """Count original branches once, checking their nested views and assignments."""
    _require(type(source) is SectorCertificate, "invalid_native_source_roots")
    try:
        _require(type(source.incidence) is IncidenceReport, "invalid_native_source_roots")
        boundaries, assignments = source.incidence.boundaries, source.assignments
        _require(
            type(boundaries) is tuple
            and len(boundaries) == 2
            and type(assignments) is tuple
            and len(assignments) == 4,
            "invalid_native_source_roots",
        )
        count = 0
        for index, boundary in enumerate(boundaries):
            _require(type(boundary) is BoundaryLedger, "invalid_native_source_roots")
            ledger = boundary.roots
            _require(type(ledger) is ArcSupportRoots, "invalid_native_source_roots")
            support, members = ledger.support, ledger.roots
            _require(
                type(support) is SupportRoots
                and type(support.roots) is tuple
                and len(support.roots) == 2
                and type(members) is tuple
                and len(members) == 2,
                "invalid_native_source_roots",
            )
            for j, (root, member) in enumerate(zip(support.roots, members, strict=True)):
                assignment = assignments[2 * index + j]
                _require(
                    type(root) is SupportRoot
                    and type(member) is ArcSupportRoot
                    and type(assignment) is RootAssignment
                    and member.support is root,
                    "invalid_native_source_roots",
                )
                labels = (
                    boundary.line_id,
                    root.branch,
                    root.position,
                    member.arc_position,
                    assignment.line_id,
                    assignment.branch,
                    assignment.original_line_position,
                    assignment.original_arc_position,
                )
                _require(
                    all(type(value) is str and len(value) <= 256 for value in labels)
                    and type(root.multiplicity) is int
                    and type(assignment.multiplicity) is int,
                    "invalid_native_source_roots",
                )
                _require(
                    root.branch == ("MINUS", "PLUS")[j]
                    and root.multiplicity == 1
                    and assignment.line_id == boundary.line_id
                    and assignment.branch == root.branch
                    and assignment.multiplicity == root.multiplicity
                    and assignment.original_line_position == root.position
                    and assignment.original_arc_position == member.arc_position,
                    "native_source_root_view_mismatch",
                )
                count += 1
        return count
    except AttributeError:
        raise NativePlanError("invalid_native_source_roots") from None


def _root_counts(
    source, cells, radial, center, lines, actual_radial=(), actual_center=(), actual_lines=()
):
    """Bound collection first; count each independent ledger, then its exact arity."""
    _require(type(source) is SectorCertificate, "invalid_native_root_inventory")
    try:
        _require(type(source.center_proxy) is CenterProxy, "invalid_native_root_inventory")
        collections = (
            (source.cells, (0, 2)),
            (source.outer_proxies, (2,)),
            (source.center_proxy.line_exits, (2,)),
            (cells, (2,)),
            (radial, (4,)),
            (center, (2,)),
            (lines, (2,)),
            (actual_radial, (0, 4)),
            (actual_center, (0, 2)),
            (actual_lines, (0, 2)),
        )
        _require(
            all(type(value) is tuple and len(value) in sizes for value, sizes in collections),
            "invalid_native_root_inventory",
        )
        _require(
            bool(actual_radial) == bool(actual_center) == bool(actual_lines),
            "invalid_native_root_inventory",
        )
        pairs = []
        for disk in source.cells + source.outer_proxies + cells:
            _require(type(disk) is OuterDisk, "invalid_native_root_inventory")
            pairs.extend(((disk.circle_exits, CircleDiskExit), (disk.radial_exits, RadialDiskExit)))
        for entry in source.center_proxy.line_exits:
            _require(type(entry) is tuple and len(entry) == 2, "invalid_native_root_inventory")
            _require(
                type(entry[0]) is str and len(entry[0]) <= 256, "invalid_native_root_inventory"
            )
            pairs.append((entry[1], RadialDiskExit))
        for records, kind in (
            (radial + actual_radial, NativeDiskRoots),
            (center + actual_center, NativeCenterRoots),
        ):
            for record in records:
                _require(type(record) is kind, "invalid_native_root_inventory")
                pairs.append((record.parameters, DyadicInterval))
        for line in lines + actual_lines:
            _require(type(line) is NativeLine, "invalid_native_root_inventory")
            _require(
                type(line.support_circle_roots) is NativeSupportCircleRoots,
                "invalid_native_root_inventory",
            )
            pairs.append((line.support_circle_roots.parameters, DyadicInterval))
        # A third branch is bounded diagnostic input, never accepted. Count it
        # before exact-pair rejection so a full65 inventory hits the hard cap.
        _require(
            all(type(pair) is tuple and len(pair) <= 3 for pair, _ in pairs),
            "invalid_native_root_inventory",
        )
        _require(
            all(type(root) is kind for pair, kind in pairs for root in pair),
            "invalid_native_root_inventory",
        )
        auxiliary = sum(len(pair) for pair, _ in pairs)
        support = _source_support_root_count(source)
        full = auxiliary + support
        _require(full <= 64, "auxiliary_root_limit")
        _require(all(len(pair) == 2 for pair, _ in pairs), "invalid_native_root_inventory")
        return auxiliary, support, full
    except AttributeError:
        raise NativePlanError("invalid_native_root_inventory") from None


def root_counts(plan, actual_radial=(), actual_center=(), actual_lines=()):
    """Detached count only, never permission to construct or register geometry."""
    _require(type(plan) is NativePlan, "invalid_native_plan")
    try:
        _require(
            all(type(value) is tuple for value in (actual_radial, actual_center, actual_lines)),
            "invalid_native_root_inventory",
        )
        if plan.accepted_support is not None:
            _require(
                not (actual_radial or actual_center or actual_lines),
                "invalid_native_root_inventory",
            )
            actual = plan.accepted_support
            _require(type(actual) is NativeActualSupport, "invalid_native_root_inventory")
            actual_radial, actual_center, actual_lines = (
                actual.radial_disk_roots,
                actual.center_proxy_roots,
                actual.lines,
            )
        return _root_counts(
            plan.source,
            plan.final_source_cells,
            plan.radial_disk_roots,
            plan.center_proxy_roots,
            plan.lines,
            actual_radial,
            actual_center,
            actual_lines,
        )
    except AttributeError:
        raise NativePlanError("invalid_native_root_inventory") from None


def retained_root_count(plan, actual_radial=(), actual_center=(), actual_lines=()):
    """Full structural count, including the four original support-circle roots."""
    return root_counts(plan, actual_radial, actual_center, actual_lines)[2]


def _continue_actual_support(plan, actual_directions, context):
    """Private freshly bound continuation; no native shape or cache authority."""
    _require(type(plan) is NativePlan and plan.accepted_support is None, "invalid_native_plan")
    c = context
    _require(
        type(c) is PrimitiveContext
        and c.operations == plan.resources.operations_end
        and c.max_bits == plan.resources.max_bits
        and c.max_operations == plan.resources.max_operations,
        "native_context_discontinuity",
    )
    _require(
        type(actual_directions) is tuple and len(actual_directions) == 2,
        "invalid_native_direction_record",
    )
    start = c.operations
    binding = hashlib.sha256(plan_bytes(plan)).hexdigest()
    i = _ContinuationIntervals(c, plan.source)
    arc = plan.source.incidence.arc
    radius = c.coordinate(plan.radius)
    lines = tuple(
        _line_from_direction(
            c,
            i,
            arc,
            intended.entity_id,
            intended.point_id,
            endpoint,
            radius,
            _actual_direction(c, plan, intended, record),
            intended.length,
            intended.trim_parameter,
        )
        for intended, record, endpoint in zip(
            plan.lines, actual_directions, (arc.start, arc.end), strict=True
        )
    )
    dot, cross, theta, rep = _actual_angle(c, i, plan, lines)
    rays = (c.vector(arc.center, arc.start), c.vector(arc.center, arc.end))
    proxy = plan.source.center_proxy.radius
    radial = tuple(
        _radial_disk(c, i, lines[index], lines[1 - index], rays[index], radius, disk_radius, kind)
        for kind, disk_radius in (
            ("final_common_cell", plan.final_cell_radius),
            ("clearance_proxy", proxy),
        )
        for index in range(2)
    )
    center, collars = _actual_center_roots(c, i, lines, proxy)
    auxiliary_count, support_count, count = root_counts(plan, radial, center, lines)
    # All unchanged circle/source witnesses are the exact objects in plan.
    # The actual root, alignment, dot, membership and collar hypotheses above
    # transfer their separated exterior-trace and Jordan-completion proofs.
    rho = plan.final_cell_radius
    rho_i = i._div(i.point(rho.numerator), i.point(rho.denominator))
    allowance = i._mul(i._mul(i.point(2), plan.source.area.pi), i._mul(rho_i, rho_i))
    reference = i._mul(i.point(c._mul(_sq(c, radius), Dyadic(1, -1))), i.abs(theta))
    area_class = i._result(
        c._sub(reference.lower, allowance.upper), c._add(reference.upper, allowance.upper)
    )
    usage = ResourceUsage(start, c.operations, c.max_bits, c.max_operations, 0)
    actual = NativeActualSupport(
        1,
        binding,
        actual_directions,
        lines,
        radial,
        center,
        dot,
        cross,
        theta,
        rep,
        reference,
        area_class,
        collars,
        rho,
        auxiliary_count,
        support_count,
        count,
        i.precision,
        usage,
    )
    result = replace(plan, accepted_support=actual)
    plan_bytes(result)  # The full intended+actual record must fit the same1MiB.
    return result


def prepare_native_representation(
    source: SectorGeometrySource, plane: NativePlane, actual_directions, *, context=None
):
    """Fresh source/intent and actual-field proof; never caller plan/certificate trust."""
    c = entry_context(context)
    plan = prepare_native_geometry(source, plane, context=c)
    return _continue_actual_support(plan, actual_directions, c)


@dataclass(frozen=True, slots=True)
class NativeEndpointObservation:
    """One prescribed circle evaluation, in authored endpoint order.

    These fields are observations, not a supplied distance or certificate. The
    world tuple is retained verbatim, including its binary64 signed zeroes.
    """

    point_id: str
    parameter: float
    world_point: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class NativeVertexLineWitness:
    role: str
    entity_id: str
    point_id: str
    endpoint_vector: tuple[Dyadic, Dyadic]
    representative_delta: tuple[Dyadic, Dyadic]
    distance_squared: Dyadic
    authored_delta: tuple[Dyadic, Dyadic]
    authored_distance_squared: Dyadic
    cell_margin: Dyadic
    resources: ResourceUsage


@dataclass(frozen=True, slots=True)
class NativeVertexEndpointWitness:
    observation: NativeEndpointObservation
    local_point: tuple[Dyadic, Dyadic]
    local_normal: Dyadic
    centered_point: tuple[Dyadic, Dyadic]
    authored_vector: tuple[Dyadic, Dyadic]
    authored_delta: tuple[Dyadic, Dyadic]
    authored_distance_squared: Dyadic
    authored_cell_margin: Dyadic
    circle_delta: tuple[DyadicInterval, DyadicInterval]
    circle_error: DyadicInterval
    circle_cell_margin: Dyadic
    intended_line: NativeVertexLineWitness
    actual_line: NativeVertexLineWitness
    authored_resources: ResourceUsage
    circle_resources: ResourceUsage
    resources: ResourceUsage


@dataclass(frozen=True, slots=True)
class NativeVertexRepresentation:
    """Detached immutable coordinates and checked mapping, never native state.

    The hashes bind this record to its fresh source and both plan prefixes.
    The content digest detects subsequent record alteration, not authenticity:
    public callers must use prepare_native_vertex_representation to recompute.
    """

    version: int
    source_geometry_sha256: str
    intended_plan_sha256: str
    accepted_plan_sha256: str
    precision: int
    vertices: tuple[tuple[str, tuple[float, float, float]], ...]
    endpoints: tuple[NativeVertexEndpointWitness, NativeVertexEndpointWitness]
    resources: ResourceUsage
    binding_sha256: str


@dataclass(frozen=True, slots=True)
class _NativeVertexContinuation:
    """Private live sequencing ticket, deliberately absent from every encoder."""

    plan: NativePlan
    context: PrimitiveContext
    operations_end: int
    max_bits: int
    max_operations: int
    accepted_plan_sha256: str


def _vertex_context_grammar(context):
    _require(
        type(context) is PrimitiveContext
        and all(hasattr(context, name) for name in ("operations", "max_bits", "max_operations"))
        and type(context.operations) is int
        and type(context.max_bits) is int
        and type(context.max_operations) is int
        and 1 <= context.max_bits <= 65_536
        and 1 <= context.max_operations <= MAX_OPERATIONS
        and 0 <= context.operations <= context.max_operations,
        "native_context_discontinuity",
    )


def _continue_actual_support_for_vertices(plan, actual_directions, context):
    """Run the unchanged actual proof once and retain its exact live lineage."""
    _vertex_context_grammar(context)
    accepted = _continue_actual_support(plan, actual_directions, context)
    ticket = _NativeVertexContinuation(
        accepted,
        context,
        context.operations,
        context.max_bits,
        context.max_operations,
        hashlib.sha256(plan_bytes(accepted)).hexdigest(),
    )
    return accepted, ticket


def _vertex_continuation(plan, context, continuation):
    _vertex_context_grammar(context)
    _require(
        type(continuation) is _NativeVertexContinuation
        and all(
            hasattr(continuation, name)
            for name in (
                "plan",
                "context",
                "operations_end",
                "max_bits",
                "max_operations",
                "accepted_plan_sha256",
            )
        ),
        "native_context_discontinuity",
    )
    _require(
        type(context) is PrimitiveContext
        and continuation.plan is plan
        and continuation.context is context
        and type(continuation.operations_end) is int
        and continuation.operations_end == context.operations
        and type(continuation.max_bits) is int
        and continuation.max_bits == context.max_bits
        and type(continuation.max_operations) is int
        and continuation.max_operations == context.max_operations
        and type(continuation.accepted_plan_sha256) is str
        and continuation.accepted_plan_sha256 == hashlib.sha256(plan_bytes(plan)).hexdigest(),
        "native_context_discontinuity",
    )


def _vertex_record_types():
    return (
        NativeEndpointObservation,
        NativeVertexLineWitness,
        NativeVertexEndpointWitness,
        NativeVertexRepresentation,
    )


def vertex_representation_bytes(representation: NativeVertexRepresentation) -> bytes:
    """Bounded exact-type encoding; floats retain their unambiguous hex values."""
    _require(type(representation) is NativeVertexRepresentation, "invalid_native_vertex_record")
    return _record_bytes(representation, extra_record_types=_vertex_record_types())


def _vertex_bundle_bytes(plan, representation):
    # One complete mathematical record keeps the original depth, node, tuple,
    # integer and 1 MiB bounds. Separately fitting records do not waive them.
    return _record_bytes(
        (plan, representation),
        extra_record_types=(
            NativePlane,
            NativeFrame,
            NativeLine,
            NativeSupportCircleRoots,
            NativeDiskRoots,
            NativeCenterRoots,
            NativePlan,
            NativeRadialDirection,
            NativeActualSupport,
            NativePeriodicTrim,
        )
        + _vertex_record_types(),
    )


def _vertex_observations(plan, observations):
    _require(
        type(observations) is tuple and len(observations) == 2,
        "invalid_native_endpoint_observation",
    )
    arc = plan.source.incidence.arc
    for observation, point_id, parameter in zip(
        observations, (arc.start_id, arc.end_id), plan.parameters, strict=True
    ):
        _require(
            type(observation) is NativeEndpointObservation
            and all(
                hasattr(observation, name) for name in ("point_id", "parameter", "world_point")
            ),
            "invalid_native_endpoint_observation",
        )
        _require(
            type(observation.point_id) is str and 1 <= len(observation.point_id) <= 256,
            "invalid_native_endpoint_observation",
        )
        _require(observation.point_id == point_id, "native_vertex_owner_changed")
        _require(
            type(observation.parameter) is float
            and math.isfinite(observation.parameter)
            and 0 <= observation.parameter < 12,
            "invalid_native_endpoint_observation",
        )
        _require(observation.parameter.hex() == parameter.hex(), "native_vertex_parameter_changed")
        _require(
            type(observation.world_point) is tuple and len(observation.world_point) == 3,
            "invalid_native_endpoint_observation",
        )
        for value in observation.world_point:
            _require(
                type(value) is float and math.isfinite(value) and -1_000_000 <= value <= 1_000_000,
                "invalid_native_endpoint_observation",
            )


def _vertex_usage(context, start):
    return ResourceUsage(start, context.operations, context.max_bits, context.max_operations, 0)


def _vertex_prefix(plan, context):
    """Check the unchanged accepted-support prefix before its private continuation."""
    _require(type(plan) is NativePlan, "invalid_native_plan")
    encoded = plan_bytes(plan)  # Includes missing-slot and callback-free grammar checks.
    actual = plan.accepted_support
    _require(type(actual) is NativeActualSupport, "unproved_native_support")
    _require(type(context) is PrimitiveContext, "native_context_discontinuity")
    usages = (plan.source.resources, plan.resources, actual.resources)
    for usage in usages:
        _require(
            type(usage) is ResourceUsage
            and all(
                type(value) is int
                for value in (
                    usage.operations_start,
                    usage.operations_end,
                    usage.max_bits,
                    usage.max_operations,
                )
            )
            and 0 <= usage.operations_start <= usage.operations_end <= usage.max_operations
            and usage.max_bits == context.max_bits
            and usage.max_operations == context.max_operations,
            "native_context_discontinuity",
        )
    _require(
        plan.source.resources.operations_end <= DEFAULT_OPERATIONS
        and plan.resources.operations_start <= plan.source.resources.operations_start
        and plan.source.resources.operations_end <= plan.resources.operations_end
        and actual.resources.operations_start == plan.resources.operations_end
        and context.operations == actual.resources.operations_end,
        "native_context_discontinuity",
    )
    _require(
        type(actual.precision) is int and actual.precision == plan.source.area.precision,
        "native_vertex_precision_changed",
    )
    intended_hash = hashlib.sha256(plan_bytes(replace(plan, accepted_support=None))).hexdigest()
    _require(
        type(actual.intended_plan_sha256) is str and actual.intended_plan_sha256 == intended_hash,
        "native_vertex_plan_changed",
    )
    source_hash = hashlib.sha256(plan.source.incidence.source_json.encode("utf-8")).hexdigest()
    _require(
        type(plan.source.geometry_sha256) is str and source_hash == plan.source.geometry_sha256,
        "native_vertex_source_changed",
    )
    _require(
        type(plan.vertices) is tuple
        and len(plan.vertices) == 3
        and type(plan.parameters) is tuple
        and len(plan.parameters) == 2
        and all(type(value) is float and math.isfinite(value) for value in plan.parameters)
        and type(plan.lines) is tuple
        and len(plan.lines) == 2
        and type(actual.lines) is tuple
        and len(actual.lines) == 2
        and type(plan.circle_vectors) is tuple
        and len(plan.circle_vectors) == 2
        and type(plan.circle_gaps) is tuple
        and len(plan.circle_gaps) == 2,
        "invalid_native_plan",
    )
    return intended_hash, hashlib.sha256(encoded).hexdigest()


def _vertex_squared_delta(context, squared, code):
    _require(
        context._compare(context._mul(squared, context._make(10**18, 0)), Dyadic(1, 0)) <= 0,
        code,
    )


def _vertex_disk_margin(context, squared, numerator_squared, denominator_squared, code):
    margin = context._sub(numerator_squared, context._mul(denominator_squared, squared))
    _require(margin.mantissa > 0, code)
    return margin


def _vertex_circle_margin(context, numerator, denominator, gap_upper, error_upper):
    margin = context._sub(
        numerator, context._mul(denominator, context._add(gap_upper, error_upper))
    )
    _require(margin.mantissa > 0, "native_vertex_circle_cell_margin")
    return margin


def _vertex_line_witness(context, role, line, radius, qbar, pbar, n2, k2):
    start = context.operations
    endpoint = tuple(context._mul(radius, context.coordinate(value)) for value in line.direction)
    delta = tuple(context._sub(q, a) for q, a in zip(qbar, endpoint, strict=True))
    squared = context.dot(delta, delta)
    _vertex_squared_delta(context, squared, "native_vertex_line_discrepancy")
    authored_delta = tuple(context._sub(a, p) for a, p in zip(endpoint, pbar, strict=True))
    authored_squared = context.dot(authored_delta, authored_delta)
    margin = _vertex_disk_margin(
        context, authored_squared, n2, k2, "native_vertex_line_outside_cell"
    )
    return NativeVertexLineWitness(
        role,
        line.entity_id,
        line.point_id,
        endpoint,
        delta,
        squared,
        authored_delta,
        authored_squared,
        margin,
        _vertex_usage(context, start),
    )


def _continue_vertex_representation(plan, observations, context, *, continuation=None):
    """Continue ONLY the adapter's freshly bound, same-context accepted support.

    This root-free mapping does not change supports, cells, authored vertices,
    directions, normalization divisors or mass allowances. It does not register
    a native object; detached callers must use the fresh public entry below.
    """
    _vertex_continuation(plan, context, continuation)
    intended_hash, accepted_hash = _vertex_prefix(plan, context)
    _vertex_observations(plan, observations)
    c = context
    start = c.operations
    actual = plan.accepted_support
    i = IntervalContext(c, actual.precision)
    rho = plan.final_cell_radius
    _require(
        type(rho) is ExactRatio and rho == actual.frozen_cell_radius, "native_vertex_cell_changed"
    )
    n, k = c._value(rho.numerator), c._value(rho.denominator)
    _require(n.mantissa > 0 and k.mantissa > 0, "native_vertex_cell_changed")
    n2, k2 = _sq(c, n), _sq(c, k)
    radius = c.coordinate(plan.radius)
    center = tuple(c.coordinate(value) for value in plan.center)
    arc = plan.source.incidence.arc
    endpoints = []
    for index, observation in enumerate(observations):
        endpoint_start = c.operations
        decoded = tuple(c.coordinate(value) for value in observation.world_point)
        # F is an exact signed permutation with zero world origin. Invert by
        # selection, then subtract the possibly nonzero LOCAL center exactly.
        local = tuple(
            next(
                decoded[j] if sign == 1.0 else c._neg(decoded[j])
                for j, sign in enumerate(axis)
                if sign != 0.0
            )
            for axis in (plan.frame.u, plan.frame.v, plan.frame.normal)
        )
        _require(local[2].mantissa == 0, "native_vertex_off_plane")
        qbar = tuple(c._sub(q, origin) for q, origin in zip(local[:2], center, strict=True))
        pbar = c.vector(arc.center, (arc.start, arc.end)[index])
        authored_delta = tuple(c._sub(q, p) for q, p in zip(qbar, pbar, strict=True))
        authored_squared = c.dot(authored_delta, authored_delta)
        _vertex_squared_delta(c, authored_squared, "native_vertex_authored_discrepancy")
        authored_margin = _vertex_disk_margin(
            c, authored_squared, n2, k2, "native_vertex_outside_cell"
        )
        authored_resources = _vertex_usage(c, endpoint_start)
        circle_start = c.operations
        _require(
            type(plan.circle_vectors[index]) is tuple and len(plan.circle_vectors[index]) == 2,
            "invalid_native_plan",
        )
        circle = tuple(i._value(value) for value in plan.circle_vectors[index])
        gap = i._value(plan.circle_gaps[index])
        circle_delta = tuple(
            i._sub(i.point(q), component) for q, component in zip(qbar, circle, strict=True)
        )
        error = _norm(i, circle_delta)
        _require(
            c._compare(c._mul(error.upper, c._make(10**9, 0)), Dyadic(1, 0)) <= 0,
            "native_vertex_circle_discrepancy",
        )
        circle_margin = _vertex_circle_margin(c, n, k, gap.upper, error.upper)
        circle_resources = _vertex_usage(c, circle_start)
        intended_line = _vertex_line_witness(
            c, "intended", plan.lines[index], radius, qbar, pbar, n2, k2
        )
        actual_line = _vertex_line_witness(
            c, "actual", actual.lines[index], radius, qbar, pbar, n2, k2
        )
        endpoints.append(
            NativeVertexEndpointWitness(
                observation,
                local[:2],
                local[2],
                qbar,
                pbar,
                authored_delta,
                authored_squared,
                authored_margin,
                circle_delta,
                error,
                circle_margin,
                intended_line,
                actual_line,
                authored_resources,
                circle_resources,
                _vertex_usage(c, endpoint_start),
            )
        )
    vertices = (plan.vertices[0],) + tuple(
        (observation.point_id, observation.world_point) for observation in observations
    )
    result = NativeVertexRepresentation(
        1,
        plan.source.geometry_sha256,
        intended_hash,
        accepted_hash,
        i.precision,
        vertices,
        tuple(endpoints),
        _vertex_usage(c, start),
        "",
    )
    result = replace(
        result, binding_sha256=hashlib.sha256(vertex_representation_bytes(result)).hexdigest()
    )
    _vertex_bundle_bytes(plan, result)
    return result


def validate_native_vertex_representation(plan, representation, *, context=None):
    """Check detached binding/integrity, not native identity or proof authority.

    The optional context verifies the continuing budget at use time. Live
    identity belongs to the private ticket and retained adapter state, never
    serialized data. No caller-supplied record authorizes construction or avoids the
    fresh source/observation recomputation of the public preparation entry.
    """
    _require(type(plan) is NativePlan, "invalid_native_plan")
    if context is not None:
        _vertex_context_grammar(context)
    vertex_representation_bytes(representation)
    _require(
        type(representation.binding_sha256) is str
        and representation.binding_sha256
        == hashlib.sha256(
            vertex_representation_bytes(replace(representation, binding_sha256=""))
        ).hexdigest(),
        "native_vertex_record_changed",
    )
    _require(type(plan.accepted_support) is NativeActualSupport, "unproved_native_support")
    _require(
        type(representation.version) is int
        and representation.version == 1
        and type(representation.precision) is int
        and representation.precision == plan.accepted_support.precision
        and representation.source_geometry_sha256 == plan.source.geometry_sha256
        and representation.intended_plan_sha256 == plan.accepted_support.intended_plan_sha256
        and representation.accepted_plan_sha256 == hashlib.sha256(plan_bytes(plan)).hexdigest(),
        "native_vertex_plan_changed",
    )
    _require(
        type(representation.endpoints) is tuple
        and len(representation.endpoints) == 2
        and all(type(value) is NativeVertexEndpointWitness for value in representation.endpoints),
        "invalid_native_vertex_record",
    )
    observations = tuple(value.observation for value in representation.endpoints)
    _vertex_observations(plan, observations)
    expected_vertices = (plan.vertices[0],) + tuple(
        (observation.point_id, observation.world_point) for observation in observations
    )
    _require(
        _record_bytes(representation.vertices) == _record_bytes(expected_vertices),
        "native_vertex_record_changed",
    )
    resources = representation.resources
    _require(
        type(resources) is ResourceUsage
        and all(
            type(value) is int
            for value in (
                resources.operations_start,
                resources.operations_end,
                resources.max_bits,
                resources.max_operations,
                resources.refinements,
                resources.max_refinements,
                resources.max_certificate_bytes,
            )
        )
        and resources.operations_start == plan.accepted_support.resources.operations_end
        and resources.operations_start <= resources.operations_end <= resources.max_operations
        and 1 <= resources.max_bits <= 65_536
        and 1 <= resources.max_operations <= MAX_OPERATIONS
        and resources.refinements == 0
        and resources.max_refinements == 256
        and resources.max_certificate_bytes == 1_048_576
        and resources.max_bits == plan.resources.max_bits
        and resources.max_operations == plan.resources.max_operations,
        "native_context_discontinuity",
    )
    if context is not None:
        _require(
            type(context) is PrimitiveContext
            and context.max_bits == resources.max_bits
            and context.max_operations == resources.max_operations
            and resources.operations_end <= context.operations <= context.max_operations,
            "native_context_discontinuity",
        )
    _vertex_bundle_bytes(plan, representation)


def native_vertex_coordinates(plan, representation, point_id):
    """Return the preserved absolute world tuple for one original authored ID."""
    _require(type(point_id) is str and 1 <= len(point_id) <= 256, "native_vertex_owner_changed")
    validate_native_vertex_representation(plan, representation)
    matches = tuple(
        point for identifier, point in representation.vertices if identifier == point_id
    )
    _require(len(matches) == 1, "native_vertex_owner_changed")
    return matches[0]


def prepare_native_vertex_representation(
    source: SectorGeometrySource,
    plane: NativePlane,
    actual_directions,
    endpoint_observations,
    *,
    context=None,
):
    """Recompute the source/intent/actual prefix once, then prove both observations.

    No plan, certificate, hash, counter or cache can be supplied as authority.
    The return value is mathematical data only and cannot register native state.
    """
    c = entry_context(context)
    _vertex_context_grammar(c)
    intended = prepare_native_geometry(source, plane, context=c)
    plan, continuation = _continue_actual_support_for_vertices(intended, actual_directions, c)
    return plan, _continue_vertex_representation(
        plan, endpoint_observations, c, continuation=continuation
    )
