"""Strict native-free geometric source and independent sector prerequisites.

This leaf owns geometry records, not Sketch, solver, plane or constraint state.
All points, including unused points, remain source data. Reports are detached
containers and never evidence accepted from callers. The deliberately small
prerequisite cross-check recomputes the existing arc rules and checked root
ledgers; it does not implement a second complete sector certificate.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from .arc_geometry import ArcGeometry, arc_geometry
from .arc_profile_primitives import (
    ArcSupportRoots,
    Dyadic,
    PrimitiveContext,
    PrimitiveError,
    UnresolvedArcSupportRoots,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_MAX_POINTS = 256
_MAX_CURVES = 256
_MAX_ACTIVE_SCALARS = 512
_MAX_COORDINATE = 1_000_000
_MIN_RADIUS = 1e-6
_MAX_RADIUS = 1e6


class SourceInputError(ValueError):
    """Malformed geometric input; codes are local, not service wire codes."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SectorPoint:
    id: str
    u: int | float
    v: int | float


@dataclass(frozen=True, slots=True)
class SectorLine:
    id: str
    start: str
    end: str


@dataclass(frozen=True, slots=True)
class SectorArc:
    id: str
    center: str
    start: str
    end: str
    direction: str


@dataclass(frozen=True, slots=True)
class SectorCircle:
    id: str
    center: str
    radius: int | float


@dataclass(frozen=True, slots=True)
class SectorGeometrySource:
    """Geometry-only input, strictly revalidated at each public boundary.

    Record constructors are detached containers, not validation certificates.
    No schema migration, coincidence aliases or metadata proxy is supported.
    """

    points: tuple[SectorPoint, ...]
    lines: tuple[SectorLine, ...]
    arcs: tuple[SectorArc, ...]
    circles: tuple[SectorCircle, ...] = ()
    version: int = 1


@dataclass(frozen=True, slots=True)
class AuthoredArc:
    id: str
    center_id: str
    start_id: str
    end_id: str
    center: tuple[int | float, int | float]
    start: tuple[int | float, int | float]
    end: tuple[int | float, int | float]
    direction: str


@dataclass(frozen=True, slots=True)
class EndpointGap:
    point_id: str
    squared_norm: Dyadic
    radius_squared: Dyadic
    exact_zero: bool
    within_bound: bool


@dataclass(frozen=True, slots=True)
class BoundaryLedger:
    line_id: str
    stored_start_id: str
    stored_end_id: str
    support_start_id: str
    support_end_id: str
    roots: ArcSupportRoots | UnresolvedArcSupportRoots


@dataclass(frozen=True, slots=True)
class NominalJoin:
    line_id: str
    branch: str
    point_id: str


@dataclass(frozen=True, slots=True)
class IncidenceReport:
    """Locally owned prerequisite report, never accepted evidence.

    ``source_json`` contains only geometry. ``height`` is the fixed integer 1,
    a compatibility tag for the detached incidence shape, not input geometry or
    an extrusion dimension. Arithmetic counters describe one shared context.
    ``ledgers_complete`` means both calls returned, even for rejected roots;
    resource failure retains completed prior calls without inventing empties.
    """

    status: str
    stage: str
    code: str
    source_json: str
    height: int | float
    core_arcs: tuple[tuple[str, ArcGeometry], ...]
    arc: AuthoredArc | None
    form: str | None
    ray_dot: Dyadic | None
    gaps: tuple[EndpointGap, ...]
    boundaries: tuple[BoundaryLedger, ...]
    nominal_joins: tuple[NominalJoin, ...]
    intended_ledger_count: int
    ledgers_complete: bool
    operations_start: int
    operations_end: int
    max_bits: int
    max_operations: int


def _identifier(value: object) -> None:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise SourceInputError("invalid_id")


def _number(value: object, *, radius: bool = False) -> None:
    if type(value) not in (int, float):
        raise SourceInputError("invalid_number")
    # Bound integers before a float conversion or string allocation. For floats,
    # the direct comparison also rejects infinities; NaN needs the finite check.
    if not -_MAX_COORDINATE <= value <= _MAX_COORDINATE or not math.isfinite(value):
        raise SourceInputError("invalid_number")
    if radius and not _MIN_RADIUS <= value <= _MAX_RADIUS:
        raise SourceInputError("invalid_number")


def _validate_source(source: SectorGeometrySource) -> None:
    if type(source) is not SectorGeometrySource:
        raise SourceInputError("invalid_source")
    try:
        _validate_fields(source)
    except AttributeError:
        # Exact dataclasses can still be manufactured with missing slots via
        # object.__new__; they cannot bypass public-boundary validation.
        raise SourceInputError("invalid_source") from None


def _validate_fields(source: SectorGeometrySource) -> None:
    if type(source.version) is not int or source.version != 1:
        raise SourceInputError("unsupported_version")
    for records, record_type, limit in (
        (source.points, SectorPoint, _MAX_POINTS),
        (source.lines, SectorLine, _MAX_CURVES),
        (source.arcs, SectorArc, _MAX_CURVES),
        (source.circles, SectorCircle, _MAX_CURVES),
    ):
        if type(records) is not tuple:
            raise SourceInputError("invalid_records")
        if len(records) > limit:
            raise SourceInputError("resource_limit")
        if any(type(record) is not record_type for record in records):
            raise SourceInputError("invalid_record")
    if len(source.lines) + len(source.arcs) + len(source.circles) > _MAX_CURVES:
        raise SourceInputError("resource_limit")
    if len(source.points) + len(source.points) + len(source.circles) > _MAX_ACTIVE_SCALARS:
        raise SourceInputError("resource_limit")
    identities: set[str] = set()
    for records in (source.points, source.lines, source.arcs, source.circles):
        for record in records:
            _identifier(record.id)
            if record.id in identities:
                raise SourceInputError("duplicate_id")
            identities.add(record.id)
    points = {point.id: point for point in source.points}
    for point in source.points:
        _number(point.u)
        _number(point.v)
    for line in source.lines:
        _identifier(line.start)
        _identifier(line.end)
        if line.start == line.end or line.start not in points or line.end not in points:
            raise SourceInputError("missing_reference")
    for arc in source.arcs:
        references = (arc.center, arc.start, arc.end)
        for reference in references:
            _identifier(reference)
        if len(set(references)) != 3 or any(reference not in points for reference in references):
            raise SourceInputError("missing_reference")
        if type(arc.direction) is not str or arc.direction not in ("cw", "ccw"):
            raise SourceInputError("invalid_direction")
    for circle in source.circles:
        _identifier(circle.center)
        if circle.center not in points:
            raise SourceInputError("missing_reference")
        _number(circle.radius, radius=True)


def geometry_json(source: SectorGeometrySource) -> str:
    """Canonical ID-sorted JSON retaining stored integer/float numeric types.

    No float coercion occurs. Python's finite JSON numbers round-trip the exact
    binary64 value, including signed zero, and distinguish ``1`` from ``1.0``.
    This binds record data, not original textual spelling from an external file.
    Every unused point is retained, and the sole version is this leaf's own 1.
    """
    _validate_source(source)
    data = {
        "version": source.version,
        "points": [
            {"id": point.id, "u": point.u, "v": point.v}
            for point in sorted(source.points, key=lambda item: item.id)
        ],
        "lines": [
            {"id": line.id, "start": line.start, "end": line.end}
            for line in sorted(source.lines, key=lambda item: item.id)
        ],
        "arcs": [
            {
                "id": arc.id,
                "center": arc.center,
                "start": arc.start,
                "end": arc.end,
                "direction": arc.direction,
            }
            for arc in sorted(source.arcs, key=lambda item: item.id)
        ],
        "circles": [
            {"id": circle.id, "center": circle.center, "radius": circle.radius}
            for circle in sorted(source.circles, key=lambda item: item.id)
        ],
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _xy(point: SectorPoint) -> tuple[int | float, int | float]:
    return point.u, point.v


def _authored(arc: SectorArc, points: dict[str, SectorPoint]) -> AuthoredArc:
    return AuthoredArc(
        arc.id,
        arc.center,
        arc.start,
        arc.end,
        _xy(points[arc.center]),
        _xy(points[arc.start]),
        _xy(points[arc.end]),
        arc.direction,
    )


def _same_pair(line: SectorLine, start: str, end: str) -> bool:
    return (line.start == start and line.end == end) or (line.start == end and line.end == start)


def _sector_lines(
    source: SectorGeometrySource, arc: SectorArc
) -> tuple[SectorLine, SectorLine] | None:
    first, second = source.lines
    if _same_pair(first, arc.center, arc.start) and _same_pair(second, arc.center, arc.end):
        return first, second
    if _same_pair(second, arc.center, arc.start) and _same_pair(first, arc.center, arc.end):
        return second, first
    return None


def _gap(
    context: PrimitiveContext,
    point_id: str,
    squared_norm: Dyadic,
    radius: Dyadic,
    radius_squared: Dyadic,
) -> EndpointGap:
    # With r>=1 and N=10^9, squaring the nonnegative bounds is equivalent
    # to r-1/N <= sqrt(S) <= r+1/N. No rounded square root is used.
    n, one = context._make(1_000_000_000, 0), context._make(1, 0)
    nr = context._mul(n, radius)
    lower, upper = context._sub(nr, one), context._add(nr, one)
    scaled = context._mul(context._mul(n, n), squared_norm)
    inside = context._compare(context._mul(lower, lower), scaled) <= 0
    inside = context._compare(scaled, context._mul(upper, upper)) <= 0 and inside
    return EndpointGap(
        point_id,
        squared_norm,
        radius_squared,
        context._compare(squared_norm, radius_squared) == 0,
        inside,
    )


def _simple_pair(ledger: ArcSupportRoots | UnresolvedArcSupportRoots) -> bool:
    return (
        len(ledger.support.roots) == len(ledger.roots) == 2
        and tuple(root.branch for root in ledger.support.roots) == ("MINUS", "PLUS")
        and all(root.multiplicity == 1 for root in ledger.support.roots)
        and all(
            member.support is support
            for member, support in zip(ledger.roots, ledger.support.roots, strict=True)
        )
    )


def _exact_endpoint_roots(boundaries: tuple[BoundaryLedger, ...]) -> bool:
    for boundary, endpoint in zip(boundaries, ("AT_START", "AT_END"), strict=True):
        minus, plus = boundary.roots.roots
        if (
            minus.support.position != "BEFORE_START"
            or plus.support.position != "AT_END"
            or plus.arc_position != endpoint
        ):
            return False
    return True


def geometry_preflight(
    source: SectorGeometrySource, context: PrimitiveContext | None = None
) -> IncidenceReport:
    """Recompute one shared-ID, one-arc/two-radius geometric prerequisite.

    Every original arc is core-checked in ID order before the GRAPH form gate,
    using unchanged arc_geometry with require_equal_radii=True. Both full root
    ledgers use the same nonresetting checked context before discrepancy/root
    decisions. No alias repair, chord support or supplied report is accepted.
    """
    _validate_source(source)
    points = {point.id: point for point in source.points}
    core_arcs = tuple(
        (
            arc.id,
            arc_geometry(
                _xy(points[arc.center]),
                _xy(points[arc.start]),
                _xy(points[arc.end]),
                arc.direction,
                require_equal_radii=True,
            ),
        )
        for arc in sorted(source.arcs, key=lambda item: item.id)
    )
    if context is None:
        context = PrimitiveContext()
    elif type(context) is not PrimitiveContext:
        raise SourceInputError("invalid_context")
    source_json = geometry_json(source)
    operations_start = context.operations
    authored = None
    form = None
    ray_dot = None
    gaps: list[EndpointGap] = []
    boundaries: list[BoundaryLedger] = []
    joins: tuple[NominalJoin, ...] = ()
    intended_count = 0
    stage = "GRAPH"

    def report(status: str, code: str) -> IncidenceReport:
        return IncidenceReport(
            status,
            stage,
            code,
            source_json,
            1,
            core_arcs,
            authored,
            form,
            ray_dot,
            tuple(gaps),
            tuple(boundaries),
            joins,
            intended_count,
            intended_count > 0 and len(boundaries) == intended_count,
            operations_start,
            context.operations,
            context.max_bits,
            context.max_operations,
        )

    if len(source.arcs) != 1 or source.circles or len(source.lines) != 2:
        return report("unsupported", "unsupported_profile_form")
    arc = source.arcs[0]
    authored = _authored(arc, points)
    lines = _sector_lines(source, arc)
    if lines is None:
        return report("unsupported", "unsupported_profile_form")
    form = "sector"
    intended_count = 2
    joins = (
        NominalJoin(lines[0].id, "PLUS", arc.start),
        NominalJoin(lines[1].id, "PLUS", arc.end),
    )
    stage = "SUPPORT"
    radius = core_arcs[0][1].start_radius
    if not 1 <= radius <= 1000:
        return report("unsupported", "unsupported_profile_scale")
    try:
        start_ray = context.vector(authored.center, authored.start)
        end_ray = context.vector(authored.center, authored.end)
        ray_dot = context.dot(start_ray, end_ray)
        zero = context._make(0, 0)
        if context._compare(ray_dot, zero) > 0:
            return report("unsupported", "unsupported_profile_sweep")
        if (
            context._compare(context.cross(start_ray, end_ray), zero) == 0
            and context._compare(ray_dot, zero) >= 0
        ):
            return report("unsupported", "unsupported_profile_sweep")
        radius_exact = context.coordinate(radius)
        radius_squared = context._mul(radius_exact, radius_exact)
        supports = ((arc.center, arc.start), (arc.center, arc.end))
        for line, (start_id, end_id) in zip(lines, supports, strict=True):
            ledger = context.line_arc_roots(
                _xy(points[start_id]),
                _xy(points[end_id]),
                authored.center,
                radius,
                arc_start=authored.start,
                arc_end=authored.end,
                direction={"ccw": "CCW", "cw": "CW"}[arc.direction],
            )
            boundaries.append(
                BoundaryLedger(line.id, line.start, line.end, start_id, end_id, ledger)
            )
        stage = "DISCREPANCY"
        for point_id, ray in ((arc.start, start_ray), (arc.end, end_ray)):
            gaps.append(
                _gap(context, point_id, context.dot(ray, ray), radius_exact, radius_squared)
            )
        if not all(gap.within_bound for gap in gaps):
            return report("unsupported", "unsupported_endpoint_discrepancy")
        stage = "ROOTS"
        if any(type(boundary.roots) is UnresolvedArcSupportRoots for boundary in boundaries):
            return report("numerical_ambiguity", "unresolved_isolation")
        if any(
            type(boundary.roots) is not ArcSupportRoots
            or not _simple_pair(boundary.roots)
            or context._compare(boundary.roots.support.discriminant, zero) <= 0
            for boundary in boundaries
        ):
            return report("unsupported", "unsupported_profile_contact")
        if all(gap.exact_zero for gap in gaps):
            if not _exact_endpoint_roots(tuple(boundaries)):
                return report("unsupported", "unsupported_endpoint_incidence")
            return report("exact_endpoint_incidence", "exact_endpoint_incidence")
        return report("requires_incidence_cells", "requires_incidence_cells")
    except PrimitiveError as exc:
        if exc.code not in ("integer_limit", "operation_limit"):
            raise
        return report("numerical_ambiguity", exc.code)
