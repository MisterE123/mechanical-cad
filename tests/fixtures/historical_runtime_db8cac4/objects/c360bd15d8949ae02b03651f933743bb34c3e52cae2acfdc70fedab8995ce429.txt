"""Bounded, native-free reference-region certificates for one arc/two radii.

The input is a strictly bounded immutable geometry source, not a Sketch, solved
or native evidence. Full schema, constraints, plane and source binding remain
the responsibility of the genuine core/client adapters. Exact
binary64 endpoint rays define the source circle arc; the unchanged core radius
and sweep remain separately recorded. Positive gaps describe a class of simple
Jordan closures with fixed exterior traces, never literal connector simplicity.
Public frozen records are data only. Consumers must call check_sector_certificate
against the bound geometry source, using their existing non-resetting context.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, fields, replace

from .arc_geometry import ArcGeometry
from .arc_profile_intervals import IntervalContext
from .arc_profile_primitives import (
    INTERVAL_PRECISIONS,
    MAX_INTEGER_BITS,
    MAX_OPERATIONS,
    ArcSupportRoot,
    ArcSupportRoots,
    Dyadic,
    DyadicInterval,
    PrimitiveContext,
    PrimitiveError,
    SupportRoot,
    SupportRoots,
    UnresolvedArcSupportRoots,
    UnresolvedSupportRoots,
)
from .arc_profile_sector_source import (
    AuthoredArc,
    BoundaryLedger,
    EndpointGap,
    IncidenceReport,
    NominalJoin,
    SectorGeometrySource,
    geometry_preflight,
)

MAX_CERTIFICATE_BYTES = 1_048_576
MAX_REFINEMENTS = 256
MAX_AUXILIARY_ROOTS = 64


class SectorInputError(ValueError):
    """Malformed new adapter arguments, separate from unchanged model errors."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ExactRatio:
    """Fixed homogeneous scalar, not a generic rational arithmetic API."""

    numerator: Dyadic
    denominator: Dyadic


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    operations_start: int
    operations_end: int
    max_bits: int
    max_operations: int
    refinements: int
    max_refinements: int = MAX_REFINEMENTS
    max_certificate_bytes: int = MAX_CERTIFICATE_BYTES


@dataclass(frozen=True, slots=True)
class StrictInequality:
    """Exact lhs < rhs, with denominator products already cleared positively."""

    label: str
    lhs: Dyadic
    rhs: Dyadic


@dataclass(frozen=True, slots=True)
class GapEnclosure:
    point_id: str
    norm: DyadicInterval
    gap: DyadicInterval
    eta: ExactRatio


@dataclass(frozen=True, slots=True)
class BoundaryUse:
    entity_id: str
    kind: str
    start_id: str
    end_id: str
    reversed_from_authored: bool


@dataclass(frozen=True, slots=True)
class RootAssignment:
    line_id: str
    branch: str
    multiplicity: int
    original_line_position: str
    original_arc_position: str
    original_finite_crossing: bool
    reference_line_position: str
    reference_arc_position: str
    assigned_join_id: str | None
    assigned_cell_id: str | None


@dataclass(frozen=True, slots=True)
class CircleDiskExit:
    """x-c=(rational+radical*sqrt(radicand))/denominator.

    The common positive denominator is exact. angular_parameter encloses the
    signed perp(v) coefficient, so MINUS/PLUS are strictly isolated even when
    rounded Cartesian projections overlap. Both support exits are retained.
    """

    branch: str
    multiplicity: int
    rational: tuple[Dyadic, Dyadic]
    radical: tuple[Dyadic, Dyadic]
    radicand: Dyadic
    denominator: Dyadic
    angular_parameter: DyadicInterval
    original_arc_position: str
    retained: bool
    transverse_sign: int


@dataclass(frozen=True, slots=True)
class RadialDiskExit:
    """t=(rational+radical*sqrt(radicand))/denominator on c+t*v."""

    branch: str
    multiplicity: int
    rational: Dyadic
    radical: Dyadic
    radicand: Dyadic
    denominator: Dyadic
    parameter: DyadicInterval
    original_line_position: str
    retained: bool
    transverse_sign: int


@dataclass(frozen=True, slots=True)
class OuterDisk:
    kind: str
    point_id: str
    line_id: str
    radius: ExactRatio
    squared_norm: Dyadic
    alpha_numerator: Dyadic
    denominator: Dyadic
    radical_squared: Dyadic
    circle_exits: tuple[CircleDiskExit, ...]
    radial_exits: tuple[RadialDiskExit, ...]
    inequalities: tuple[StrictInequality, ...]
    trim_rule: str


@dataclass(frozen=True, slots=True)
class CenterProxy:
    point_id: str
    radius: ExactRatio
    line_exits: tuple[tuple[str, tuple[RadialDiskExit, ...]], ...]
    inequalities: tuple[StrictInequality, ...]


@dataclass(frozen=True, slots=True)
class ClearanceProof:
    delta: ExactRatio
    collar_length: ExactRatio
    proxy_radius: ExactRatio
    distance: ExactRatio
    inequalities: tuple[StrictInequality, ...]
    line_circle_identity: str
    line_line_identity: str
    pair_ids: tuple[tuple[str, str], ...]
    proxy_portions_inside_collars: bool


@dataclass(frozen=True, slots=True)
class JordanProof:
    center_id: str
    outer_ids: tuple[str, str]
    positive_ray_dot: Dyadic
    ray_cross: Dyadic
    center_continuation: str
    reference_radial_endpoints: tuple[str, str]
    radial_interiors_strictly_inside_circle: bool
    radial_interiors_disjoint: bool
    source_arc_unchanged: bool
    same_exterior_simple_closure: bool
    normalized_winding: int


@dataclass(frozen=True, slots=True)
class AreaProof:
    precision: int
    pi: DyadicInterval
    signed_angle: DyadicInterval
    signed_reference_area: DyadicInterval
    reference_area: DyadicInterval
    source_cell_allowance: DyadicInterval
    source_area: DyadicInterval
    perimeter: DyadicInterval
    area_floor: ExactRatio
    area_floor_margin: StrictInequality


@dataclass(frozen=True, slots=True)
class SectorCertificate:
    version: int
    semantics: str
    geometry_sha256: str
    incidence: IncidenceReport
    boundary: tuple[BoundaryUse, ...]
    assignments: tuple[RootAssignment, ...]
    gap_enclosures: tuple[GapEnclosure, ...]
    source_cell_radius: ExactRatio
    cells: tuple[OuterDisk, ...]
    outer_proxies: tuple[OuterDisk, ...]
    center_proxy: CenterProxy
    clearance: ClearanceProof
    jordan: JordanProof
    area: AreaProof
    resources: ResourceUsage


@dataclass(frozen=True, slots=True)
class SectorResult:
    status: str
    stage: str
    code: str
    incidence: IncidenceReport
    certificate: SectorCertificate | None
    assignments: tuple[RootAssignment, ...]
    cells: tuple[OuterDisk, ...]
    outer_proxies: tuple[OuterDisk, ...]
    resources: ResourceUsage


@dataclass(frozen=True, slots=True)
class CertificateCheck:
    accepted: bool
    code: str
    recomputed: SectorResult | None


@dataclass(frozen=True, slots=True)
class ExtrusionPreflight:
    supported: bool
    code: str
    height: int | float


def extrusion_preflight(height: int | float) -> ExtrusionPreflight:
    """Nominal height-only support; never evidence of perpendicular native height."""
    if type(height) not in (int, float):
        raise SectorInputError("invalid_height")
    try:
        finite = math.isfinite(height)
    except OverflowError:
        finite = False
    if not finite:
        raise SectorInputError("invalid_height")
    supported = 1 <= height <= 1000
    return ExtrusionPreflight(
        supported, "supported_height" if supported else "unsupported_profile_scale", height
    )


def _context(context: PrimitiveContext | None) -> PrimitiveContext:
    if context is None:
        return PrimitiveContext()
    if type(context) is not PrimitiveContext:
        raise SectorInputError("invalid_context")
    return context


def _constant(context: PrimitiveContext, numerator: int, denominator: int = 1) -> ExactRatio:
    return ExactRatio(context._make(numerator, 0), context._make(denominator, 0))


def _strict(context: PrimitiveContext, label: str, lhs: Dyadic, rhs: Dyadic) -> StrictInequality:
    if context._compare(lhs, rhs) >= 0:
        raise PrimitiveError("unproved_strict_inequality")
    return StrictInequality(label, lhs, rhs)


def _square(context: PrimitiveContext, value: Dyadic) -> Dyadic:
    return context._mul(value, value)


def _ratio_interval(intervals: IntervalContext, ratio: ExactRatio) -> DyadicInterval:
    return intervals.div(intervals.point(ratio.numerator), intervals.point(ratio.denominator))


def _gap_enclosures(
    context: PrimitiveContext, intervals: IntervalContext, report: IncidenceReport
) -> tuple[GapEnclosure, ...]:
    radius = context.coordinate(report.core_arcs[0][1].start_radius)
    one, n = context._make(1, 0), context._make(1_000_000_000, 0)
    records = []
    for gap in report.gaps:
        norm = context.sqrt_enclosure(gap.squared_norm, intervals.precision)
        enclosure = (
            intervals.point(0)
            if gap.exact_zero
            else intervals.abs(intervals.sub(norm, intervals.point(radius)))
        )
        # The independent exact discrepancy gate already established d<=1/N.
        # Clipping this certified upper bound is consequently sound, including
        # the mathematically inclusive non-dyadic boundary.
        eta = (
            ExactRatio(enclosure.upper, one)
            if context._compare(context._mul(enclosure.upper, n), one) <= 0
            else ExactRatio(one, n)
        )
        records.append(GapEnclosure(gap.point_id, norm, enclosure, eta))
    return tuple(records)


def _cell_radius(context: PrimitiveContext, gaps: tuple[GapEnclosure, ...]) -> ExactRatio:
    first, second = (gap.eta for gap in gaps)
    maximum = (
        first
        if context._compare(
            context._mul(first.numerator, second.denominator),
            context._mul(second.numerator, first.denominator),
        )
        >= 0
        else second
    )
    return ExactRatio(context._mul(context._make(16, 0), maximum.numerator), maximum.denominator)


def _assignments(report: IncidenceReport, positive_cells: bool) -> tuple[RootAssignment, ...]:
    records = []
    for ledger, endpoint in zip(report.boundaries, ("AT_START", "AT_END"), strict=True):
        if len(ledger.roots.roots) != 2:
            raise PrimitiveError("unsupported_profile_contact")
        minus, plus = ledger.roots.roots
        if (
            minus.support.branch != "MINUS"
            or minus.support.multiplicity != 1
            or minus.support.position != "BEFORE_START"
            or plus.support.branch != "PLUS"
            or plus.support.multiplicity != 1
            or plus.support.position not in ("INTERIOR", "AT_END", "AFTER_END")
            or plus.arc_position != endpoint
        ):
            raise PrimitiveError("unsupported_profile_contact")
        for root in (minus, plus):
            own = root.support.branch == "PLUS"
            point_id = ledger.support_end_id if own else None
            records.append(
                RootAssignment(
                    ledger.line_id,
                    root.support.branch,
                    root.support.multiplicity,
                    root.support.position,
                    root.arc_position,
                    root.support.position in ("AT_START", "INTERIOR", "AT_END")
                    and root.arc_position != "OUTSIDE",
                    "AT_END" if own else "BEFORE_START",
                    root.arc_position,
                    point_id,
                    point_id if positive_cells else None,
                )
            )
    return tuple(records)


def _radial_exits(
    context: PrimitiveContext,
    intervals: IntervalContext,
    squared_norm: Dyadic,
    radius: ExactRatio,
    *,
    at_center: bool = False,
) -> tuple[RadialDiskExit, ...]:
    # t=offset +/- n/(k sqrt(S))=(offset*k*S +/- n*sqrt(S))/(k*S).
    denominator = context._mul(radius.denominator, squared_norm)
    rational = context._make(0, 0) if at_center else denominator
    norm = context.sqrt_enclosure(squared_norm, intervals.precision)
    distance = intervals.div(_ratio_interval(intervals, radius), norm)
    offset = intervals.point(0 if at_center else 1)
    results = []
    for branch in (-1, 1):
        parameter = (
            intervals.sub(offset, distance) if branch < 0 else intervals.add(offset, distance)
        )
        retained = branch > 0 if at_center else branch < 0
        position = "INTERIOR" if retained else "BEFORE_START" if at_center else "AFTER_END"
        # Algebraic comparison, independently of the interval bounds. Source
        # domain ensures sqrt(S)>radius and hence exactly these finite positions.
        start_sign = context.radical_sign(
            rational, context._mul(context._make(branch, 0), radius.numerator), squared_norm
        )
        end_sign = context.radical_sign(
            context._sub(rational, denominator),
            context._mul(context._make(branch, 0), radius.numerator),
            squared_norm,
        )
        expected = (1, -1) if retained else (-1, -1) if at_center else (1, 1)
        if (start_sign, end_sign) != expected:
            raise PrimitiveError("unsupported_endpoint_incidence")
        results.append(
            RadialDiskExit(
                "MINUS" if branch < 0 else "PLUS",
                1,
                rational,
                context._mul(context._make(branch, 0), radius.numerator),
                squared_norm,
                denominator,
                parameter,
                position,
                retained,
                branch,
            )
        )
    if context._compare(results[0].parameter.upper, results[1].parameter.lower) >= 0:
        raise PrimitiveError("unresolved_disk_exits")
    return tuple(results)


def _outer_disk(
    context: PrimitiveContext,
    intervals: IntervalContext,
    report: IncidenceReport,
    rays: tuple[tuple[Dyadic, Dyadic], ...],
    index: int,
    disk_radius: ExactRatio,
    kind: str,
) -> OuterDisk:
    """The only circle/disk formula; no rounded auxiliary points or general rationals.

    rho=n/k, T=(r²+S)k²-n², Z=2Sk²,
    H=4r²Sk⁴-T². Then x-c=(T*v +/-sqrt(H)*perp(v))/Z.
    Z>0,T>0,H>0 give two transverse circle exits, on the near half circle.
    Exact determinant signs choose the sole finite-arc exit. The radial support
    has two exits too, but only the inward exit belongs to the finite source line.
    """
    arc = report.arc
    ledger = report.boundaries[index]
    v, other = rays[index], rays[1 - index]
    s = report.gaps[index].squared_norm
    other_s = report.gaps[1 - index].squared_norm
    r = context.coordinate(report.core_arcs[0][1].start_radius)
    r2 = _square(context, r)
    n, k = disk_radius.numerator, disk_radius.denominator
    n2, k2 = _square(context, n), _square(context, k)
    zero, two, four = context._make(0, 0), context._make(2, 0), context._make(4, 0)
    kr = context._mul(k, r)
    lower, upper = context._sub(kr, n), context._add(kr, n)
    scaled_s = context._mul(k2, s)
    t = context._sub(context._mul(context._add(r2, s), k2), n2)
    z = context._mul(two, scaled_s)
    h = context._sub(
        context._mul(four, context._mul(context._mul(r2, s), _square(context, k2))),
        _square(context, t),
    )
    difference = context._sub(v[0], other[0]), context._sub(v[1], other[1])
    distance2 = context.dot(difference, difference)
    checks = (
        _strict(context, "positive_disk_radius", zero, n),
        _strict(context, "positive_denominator", zero, k),
        _strict(context, "positive_lower_radial_bound", zero, lower),
        _strict(context, "own_root_strict_inside_lower", _square(context, lower), scaled_s),
        _strict(context, "own_root_strict_inside_upper", scaled_s, _square(context, upper)),
        _strict(context, "center_and_foreign_finite_radius_excluded", n2, scaled_s),
        _strict(
            context,
            "outer_disks_strictly_disjoint",
            context._mul(four, n2),
            context._mul(k2, distance2),
        ),
        _strict(context, "center_proxy_strictly_disjoint", context._mul(four, n2), scaled_s),
        _strict(
            context, "own_root_outside_other_disk", n2, context._mul(k2, context._add(r2, other_s))
        ),
        _strict(context, "negative_root_outside_own_disk", n2, context._mul(k2, r2)),
        _strict(context, "short_circle_portion", zero, t),
        _strict(context, "two_transverse_circle_exits", zero, h),
    )
    perp = context._neg(v[1]), v[0]
    rational = context._mul(t, v[0]), context._mul(t, v[1])
    beta = intervals.div(context.sqrt_enclosure(h, intervals.precision), intervals.point(z))
    if context._compare(beta.lower, zero) <= 0:
        raise PrimitiveError("unresolved_disk_exits")
    turn = context._compare(context.cross(rays[0], rays[1]), zero)
    circle_exits = []
    for branch in (-1, 1):
        branch_d = context._make(branch, 0)
        radical = context._mul(branch_d, perp[0]), context._mul(branch_d, perp[1])
        position = context._arc_position(
            rays[0], rays[1], rational, radical, h, turn, arc.direction == "cw"
        )
        expected_branch = (1 if arc.direction == "ccw" else -1) * (1 if index == 0 else -1)
        retained = branch == expected_branch
        if position != ("INTERIOR" if retained else "OUTSIDE"):
            raise PrimitiveError("unsupported_endpoint_incidence")
        circle_exits.append(
            CircleDiskExit(
                "MINUS" if branch < 0 else "PLUS",
                1,
                rational,
                radical,
                h,
                z,
                intervals.neg(beta) if branch < 0 else beta,
                position,
                retained,
                branch,
            )
        )
    return OuterDisk(
        kind,
        ledger.support_end_id,
        ledger.line_id,
        disk_radius,
        s,
        t,
        z,
        h,
        tuple(circle_exits),
        _radial_exits(context, intervals, s, disk_radius),
        checks,
        "unchanged_source_arc_and_radial_trim_inside_convex_disk",
    )


def _center_proxy(
    context: PrimitiveContext,
    intervals: IntervalContext,
    report: IncidenceReport,
    proxy: ExactRatio,
) -> CenterProxy:
    n2, k2 = _square(context, proxy.numerator), _square(context, proxy.denominator)
    r = context.coordinate(report.core_arcs[0][1].start_radius)
    checks = [_strict(context, "source_circle_excluded", n2, context._mul(k2, _square(context, r)))]
    exits = []
    for ledger, gap in zip(report.boundaries, report.gaps, strict=True):
        checks.append(
            _strict(context, "finite_radius_has_one_exit", n2, context._mul(k2, gap.squared_norm))
        )
        exits.append(
            (
                ledger.line_id,
                _radial_exits(context, intervals, gap.squared_norm, proxy, at_center=True),
            )
        )
    return CenterProxy(report.arc.center_id, proxy, tuple(exits), tuple(checks))


def _clearance(context: PrimitiveContext, report: IncidenceReport) -> ClearanceProof:
    # A single common denominator N=10^9 makes every constant exact without
    # any rational engine: Delta=1/N, b=350/N, L=400/N, D=200/N.
    n = context._make(1_000_000_000, 0)
    n2 = _square(context, n)
    r = context.coordinate(report.core_arcs[0][1].start_radius)
    r2 = _square(context, r)
    four_r2 = context._mul(context._make(4, 0), r2)
    x2 = context._make(123_201, 0)  # 351², the worst-case b+Delta chord bound.
    l2 = context._make(160_000, 0)  # 400².
    checks = (
        _strict(
            context,
            "line_circle_clearance_margin",
            context._make(80_000, 0),
            context._make(121_801, 0),
        ),
        _strict(context, "half_radius_clearance", context._make(400, 0), context._mul(r, n)),
        _strict(context, "radial_pair_clearance", context._make(200, 0), context._make(350, 0)),
        _strict(context, "short_arc_collar_denominator", x2, context._mul(four_r2, n2)),
        _strict(
            context,
            "short_arc_proxy_inside_length_collar",
            context._mul(context._mul(four_r2, x2), n2),
            context._mul(l2, context._sub(context._mul(four_r2, n2), x2)),
        ),
        _strict(
            context, "line_proxy_inside_length_collar", context._make(350, 0), context._make(400, 0)
        ),
    )
    first, second = report.boundaries
    return ClearanceProof(
        _constant(context, 1, 1_000_000_000),
        _constant(context, 400, 1_000_000_000),
        _constant(context, 350, 1_000_000_000),
        _constant(context, 200, 1_000_000_000),
        checks,
        "distance_squared=y_squared+(s/r)*x_squared; s<r/2 or s/r>=1/2; max(x,y)>=b-Delta",
        "distance_squared=s_squared+t_squared-2*s*t*unit_ray_dot>=s_squared+t_squared",
        (
            (report.arc.id, first.line_id),
            (report.arc.id, second.line_id),
            (first.line_id, second.line_id),
        ),
        True,
    )


def _boundary(report: IncidenceReport) -> tuple[BoundaryUse, ...]:
    arc = report.arc
    first, second = report.boundaries
    if arc.direction == "ccw":
        arc_use = BoundaryUse(arc.id, "arc", arc.start_id, arc.end_id, False)
        radial = ((second, arc.end_id, arc.center_id), (first, arc.center_id, arc.start_id))
    else:
        arc_use = BoundaryUse(arc.id, "arc", arc.end_id, arc.start_id, True)
        radial = ((first, arc.start_id, arc.center_id), (second, arc.center_id, arc.end_id))
    return (arc_use,) + tuple(
        BoundaryUse(ledger.line_id, "line", start, end, ledger.stored_start_id != start)
        for ledger, start, end in radial
    )


def _area(
    context: PrimitiveContext,
    intervals: IntervalContext,
    report: IncidenceReport,
    cross: Dyadic,
    dot: Dyadic,
    rho: ExactRatio,
    gaps: tuple[GapEnclosure, ...],
) -> AreaProof:
    r = context.coordinate(report.core_arcs[0][1].start_radius)
    r2 = intervals.point(_square(context, r))
    angle = intervals.directed_angle(cross, dot, {"ccw": "CCW", "cw": "CW"}[report.arc.direction])
    signed = intervals.scale(intervals.mul(r2, angle), context._make(1, -1))
    reference = intervals.abs(signed)
    pi = intervals.pi()
    rho_interval = _ratio_interval(intervals, rho)
    allowance = intervals.scale(intervals.mul(pi, intervals.mul(rho_interval, rho_interval)), 2)
    area = intervals.add(
        reference,
        intervals.context._interval(
            context._neg(allowance.upper), allowance.upper, intervals.precision
        ),
    )
    floor = _constant(context, 1, 1_000_000_000_000)
    # The broad supported sector domain has a strictly positive margin. Testing
    # strictness here is stronger than the required inclusive area floor.
    margin = _strict(
        context,
        "positive_source_area_floor",
        floor.numerator,
        context._mul(area.lower, floor.denominator),
    )
    perimeter = intervals.add(
        intervals.mul(intervals.point(r), intervals.abs(angle)),
        intervals.add(gaps[0].norm, gaps[1].norm),
    )
    return AreaProof(
        intervals.precision, pi, angle, signed, reference, allowance, area, perimeter, floor, margin
    )


def classify_sector_geometry(
    source: SectorGeometrySource, *, context: PrimitiveContext | None = None
) -> SectorResult:
    """Complete geometry-only gate, never full-source, solver or native authority.

    The strict source preflight freshly derives the core result and complete
    prerequisite ledger. Every exact operation, even a failed refinement, shares
    the caller's context. No supplied report or certificate can mint readiness.
    """
    context = _context(context)
    start = context.operations
    report = geometry_preflight(source, context=context)
    assignments: tuple[RootAssignment, ...] = ()
    cells: tuple[OuterDisk, ...] = ()
    proxies: tuple[OuterDisk, ...] = ()
    stage, refinements = report.stage, 0

    def usage() -> ResourceUsage:
        return ResourceUsage(
            start, context.operations, context.max_bits, context.max_operations, refinements
        )

    def result(
        status: str, code: str, certificate: SectorCertificate | None = None
    ) -> SectorResult:
        return SectorResult(
            status, stage, code, report, certificate, assignments, cells, proxies, usage()
        )

    if report.form == "chord":
        stage = "GRAPH"
        return result("unsupported", "unsupported_profile_form")
    if report.status in ("unsupported", "numerical_ambiguity"):
        return result(report.status, report.code)
    stage = "ROOTS"
    try:
        rays = (
            context.vector(report.arc.center, report.arc.start),
            context.vector(report.arc.center, report.arc.end),
        )
        cross, dot = context.cross(*rays), context.dot(*rays)
        positive_cells = not all(gap.exact_zero for gap in report.gaps)
        assignments = _assignments(report, positive_cells)
        last_code = "unresolved_disk_exits"
        for precision in INTERVAL_PRECISIONS:
            refinements += 1
            if refinements > MAX_REFINEMENTS:
                raise PrimitiveError("refinement_limit")
            intervals = IntervalContext(context, precision)
            stage = "CELLS"
            gaps = _gap_enclosures(context, intervals, report)
            rho = _cell_radius(context, gaps)
            if positive_cells:
                # Positive true gaps cannot be replaced with a zero enclosure.
                if rho.numerator.mantissa <= 0:
                    raise PrimitiveError("unresolved_gap")
                _strict(
                    context,
                    "source_cell_smaller_than_proxy",
                    context._mul(rho.numerator, context._make(1_000_000_000, 0)),
                    context._mul(context._make(350, 0), rho.denominator),
                )
                try:
                    cells = ()
                    for i in range(2):
                        cells += (
                            _outer_disk(context, intervals, report, rays, i, rho, "source_cell"),
                        )
                except PrimitiveError as exc:
                    if exc.code != "unresolved_disk_exits":
                        raise
                    last_code = exc.code
                    continue
            elif rho.numerator.mantissa != 0:
                raise PrimitiveError("invalid_zero_cell")
            proxy = _constant(context, 350, 1_000_000_000)
            try:
                proxies = ()
                for i in range(2):
                    proxies += (
                        _outer_disk(context, intervals, report, rays, i, proxy, "clearance_proxy"),
                    )
                center = _center_proxy(context, intervals, report, proxy)
            except PrimitiveError as exc:
                if exc.code != "unresolved_disk_exits":
                    raise
                last_code = exc.code
                continue
            stage = "CLEARANCE"
            clearance = _clearance(context, report)
            auxiliary_count = sum(
                len(disk.circle_exits) + len(disk.radial_exits) for disk in cells + proxies
            ) + sum(len(exits) for _, exits in center.line_exits)
            if auxiliary_count > MAX_AUXILIARY_ROOTS:
                raise PrimitiveError("auxiliary_root_limit")
            stage = "JORDAN"
            if dot.mantissa > 0 or (cross.mantissa == 0 and dot.mantissa >= 0):
                raise PrimitiveError("unsupported_profile_sweep")
            jordan = JordanProof(
                report.arc.center_id,
                (report.arc.start_id, report.arc.end_id),
                dot,
                cross,
                "straight_continuation" if cross.mantissa == 0 else "ordinary_corner",
                (report.arc.start_id, report.arc.end_id),
                True,
                True,
                True,
                True,
                1,
            )
            stage = "AREA"
            area = _area(context, intervals, report, cross, dot, rho, gaps)
            certificate = SectorCertificate(
                1,
                "exact_authored_ray_sector_reference_region_class",
                hashlib.sha256(report.source_json.encode("utf-8")).hexdigest(),
                report,
                _boundary(report),
                assignments,
                gaps,
                rho,
                cells,
                proxies,
                center,
                clearance,
                jordan,
                area,
                usage(),
            )
            # Encoding validates bounded container structure and the complete
            # certificate ceiling before any passing result can escape.
            certificate_bytes(certificate)
            stage = "COMPLETE"
            return result("certified_sector", "certified_sector", certificate)
        return result("numerical_ambiguity", last_code)
    except PrimitiveError as exc:
        definite = exc.code in (
            "unsupported_profile_contact",
            "unsupported_endpoint_incidence",
            "unsupported_profile_sweep",
        )
        return result("unsupported" if definite else "numerical_ambiguity", exc.code)
    except SectorInputError as exc:
        return result("numerical_ambiguity", exc.code)


_RECORD_TYPES = (
    ArcGeometry,
    AuthoredArc,
    BoundaryLedger,
    EndpointGap,
    IncidenceReport,
    NominalJoin,
    ArcSupportRoot,
    ArcSupportRoots,
    Dyadic,
    DyadicInterval,
    SupportRoot,
    SupportRoots,
    UnresolvedArcSupportRoots,
    UnresolvedSupportRoots,
    ExactRatio,
    ResourceUsage,
    StrictInequality,
    GapEnclosure,
    BoundaryUse,
    RootAssignment,
    CircleDiskExit,
    RadialDiskExit,
    OuterDisk,
    CenterProxy,
    ClearanceProof,
    JordanProof,
    AreaProof,
    SectorCertificate,
)


def certificate_bytes(certificate: SectorCertificate) -> bytes:
    if type(certificate) is not SectorCertificate:
        raise SectorInputError("invalid_certificate")
    return _record_bytes(certificate)


def _record_bytes(certificate: object, *, extra_record_types: tuple[type, ...] = ()) -> bytes:
    """Bounded canonical diagnostic encoding, not a wire or authentication format.

    Exact integer values are hex-tagged, avoiding Python's decimal conversion
    limit and preserving bool/int distinctions. Only exact known record types,
    tuples and scalar types are accepted; no arbitrary object hooks run.
    """
    output = bytearray()
    nodes = 0

    def append(text: str) -> None:
        encoded = text.encode("ascii")
        if len(output) + len(encoded) > MAX_CERTIFICATE_BYTES:
            raise SectorInputError("certificate_limit")
        output.extend(encoded)

    def encode(value: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > 16 or nodes > 8192:
            raise SectorInputError("certificate_structure_limit")
        kind = type(value)
        if value is None:
            append("null")
        elif kind is bool:
            append("true" if value else "false")
        elif kind is int:
            if value.bit_length() > MAX_INTEGER_BITS:
                raise SectorInputError("certificate_integer_limit")
            append('{"integer":' + json.dumps(hex(value)) + "}")
        elif kind is float:
            if not math.isfinite(value):
                raise SectorInputError("invalid_certificate_number")
            append('{"binary64":' + json.dumps(value.hex()) + "}")
        elif kind is str:
            if len(value) > MAX_CERTIFICATE_BYTES:
                raise SectorInputError("certificate_limit")
            append(json.dumps(value, ensure_ascii=True))
        elif kind is tuple:
            if len(value) > 256:
                raise SectorInputError("certificate_structure_limit")
            append("[")
            for index, item in enumerate(value):
                if index:
                    append(",")
                encode(item, depth + 1)
            append("]")
        elif kind in _RECORD_TYPES + extra_record_types:
            append('{"record":' + json.dumps(kind.__name__))
            for field in fields(value):
                append("," + json.dumps(field.name) + ":")
                try:
                    child = getattr(value, field.name)
                except AttributeError:
                    raise SectorInputError("invalid_certificate") from None
                encode(child, depth + 1)
            append("}")
        else:
            raise SectorInputError("invalid_certificate_type")

    encode(certificate, 0)
    return bytes(output)


def check_sector_geometry_certificate(
    source: SectorGeometrySource,
    certificate: SectorCertificate,
    *,
    context: PrimitiveContext | None = None,
) -> CertificateCheck:
    """Recompute every field from the geometry source; public records never authenticate.

    Recompute in the supplied aggregate budget. Arithmetic counters may have a
    different absolute starting offset, but their exact work deltas and ceilings
    must match. The checked incidence prerequisite and certificate retain the
    same offset. Canonical encoding compares types as well as values, so forged
    booleans, enum strings, hashes, source bytes, roles and witnesses all reject.
    """
    context = _context(context)
    try:
        supplied = certificate_bytes(certificate)
        resources = certificate.resources
        if type(resources) is not ResourceUsage or any(
            type(value) is not int
            for value in (
                resources.operations_start,
                resources.operations_end,
                resources.max_bits,
                resources.max_operations,
                resources.refinements,
                resources.max_refinements,
                resources.max_certificate_bytes,
            )
        ):
            return CertificateCheck(False, "invalid_certificate_resources", None)
        if not (
            0
            <= resources.operations_start
            < resources.operations_end
            <= resources.max_operations
            <= MAX_OPERATIONS
            and 1 <= resources.max_bits <= MAX_INTEGER_BITS
            and 1 <= resources.refinements <= MAX_REFINEMENTS
            and resources.max_refinements == MAX_REFINEMENTS
            and resources.max_certificate_bytes == MAX_CERTIFICATE_BYTES
            and resources.max_bits == context.max_bits
            and resources.max_operations == context.max_operations
        ):
            return CertificateCheck(False, "invalid_certificate_resources", None)
        actual = classify_sector_geometry(source, context=context)
        if actual.status != "certified_sector":
            return CertificateCheck(False, actual.code, actual)
        expected = actual.certificate
        offset = resources.operations_start - expected.resources.operations_start
        normalized_incidence = replace(
            expected.incidence,
            operations_start=expected.incidence.operations_start + offset,
            operations_end=expected.incidence.operations_end + offset,
        )
        normalized = replace(
            expected,
            incidence=normalized_incidence,
            resources=replace(
                expected.resources,
                operations_start=expected.resources.operations_start + offset,
                operations_end=expected.resources.operations_end + offset,
            ),
        )
        if certificate_bytes(normalized) != supplied:
            return CertificateCheck(False, "certificate_mismatch", actual)
        return CertificateCheck(True, "verified_sector_certificate", actual)
    except (SectorInputError, PrimitiveError, AttributeError, TypeError) as exc:
        return CertificateCheck(False, getattr(exc, "code", "invalid_certificate"), None)
