"""Isolated shared-ID incidence prerequisites for one arc and chord/two radii.

This data-only adapter does not solve constraints or admit a closed region. A
numeric Sketch is input geometry, not solver evidence. Even exact endpoint
incidence leaves clearance, reference closure, area, conversion and native
checks outstanding. Positive bounded gaps additionally require incidence cells.
No runtime consumer imports this module, and its public records are containers,
not validators or capabilities. Authored geometry is never repaired or replaced.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .arc_geometry import ArcGeometry, arc_geometry
from .arc_profile_primitives import (
    ArcSupportRoots,
    Dyadic,
    PrimitiveContext,
    PrimitiveError,
    UnresolvedArcSupportRoots,
)
from .sketch_model import Arc, Line, Point, Sketch, validate


class IncidenceInputError(ValueError):
    """Malformed adapter arguments; these are not service wire error codes."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class AuthoredArc:
    """Copied original roles/coordinates, with the unchanged model direction."""

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
    """Exact squared quantities and necessary comparison, not a gap enclosure."""

    point_id: str
    squared_norm: Dyadic
    radius_squared: Dyadic
    exact_zero: bool
    within_bound: bool


@dataclass(frozen=True, slots=True)
class BoundaryLedger:
    """Unfiltered roots; temporary support order is separate from stored order."""

    line_id: str
    stored_start_id: str
    stored_end_id: str
    support_start_id: str
    support_end_id: str
    roots: ArcSupportRoots | UnresolvedArcSupportRoots


@dataclass(frozen=True, slots=True)
class NominalJoin:
    """Prescribed branch association; positive-gap cell ownership is unproved."""

    line_id: str
    branch: str
    point_id: str


@dataclass(frozen=True, slots=True)
class IncidenceReport:
    """Detached prerequisite data, never a validated closed profile.

    status is exact_endpoint_incidence, requires_incidence_cells, unsupported,
    or numerical_ambiguity. ledgers_complete only means every intended primitive
    call returned its full root ledger, including unresolved/empty/tangent ones;
    it never means those roots passed incidence prerequisites. On exhaustion,
    only completed prior calls survive. No failed call becomes an empty ledger.
    The operation counters and limits measure checked arithmetic only. Existing
    Sketch entity/payload limits separately bound validation, serialization,
    sorting and diagnostic alias reachability; there is no wall-clock guarantee.
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


def _xy(point: Point) -> tuple[int | float, int | float]:
    return point.u, point.v


def _authored(arc: Arc, points: dict[str, Point]) -> AuthoredArc:
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


def _same_pair(line: Line, start: str, end: str) -> bool:
    return (line.start == start and line.end == end) or (line.start == end and line.end == start)


def _exact_lines(sketch: Sketch, arc: Arc) -> tuple[Line, ...] | None:
    if len(sketch.lines) == 1:
        line = sketch.lines[0]
        return (line,) if _same_pair(line, arc.start, arc.end) else None
    first, second = sketch.lines
    if _same_pair(first, arc.center, arc.start) and _same_pair(second, arc.center, arc.end):
        return first, second
    if _same_pair(second, arc.center, arc.start) and _same_pair(first, arc.center, arc.end):
        return second, first
    return None


def _alias_form(sketch: Sketch, arc: Arc, points: dict[str, Point]) -> bool:
    """Bounded diagnostic after exact topology failure; never supplies geometry.

    Only the three expected roles are searched. Equal-coordinate or explicit
    coincidence-chain reachability can explain a rejected alias, never establish
    a shared-ID join. No representative or replacement coordinate is produced.
    Each search visits at most 256 points, scanning at most 256 coordinates per
    visit. These entity-bounded scans are not checked scalar-arithmetic work.
    """
    neighbors = {point.id: set() for point in sketch.points}
    for constraint in sketch.constraints:
        if constraint.kind == "coincident":
            first, second = constraint.refs
            neighbors[first].add(second)
            neighbors[second].add(first)
    reachable: dict[str, set[str]] = {}
    for role in (arc.center, arc.start, arc.end):
        seen, pending = {role}, [role]
        while pending:
            current = pending.pop()
            adjacent = neighbors[current] | {
                point.id for point in sketch.points if _xy(point) == _xy(points[current])
            }
            for neighbor in adjacent:
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        reachable[role] = seen

    def matches(line: Line, start: str, end: str) -> bool:
        return (line.start in reachable[start] and line.end in reachable[end]) or (
            line.end in reachable[start] and line.start in reachable[end]
        )

    if len(sketch.lines) == 1:
        return matches(sketch.lines[0], arc.start, arc.end)
    first, second = sketch.lines
    return (matches(first, arc.center, arc.start) and matches(second, arc.center, arc.end)) or (
        matches(second, arc.center, arc.start) and matches(first, arc.center, arc.end)
    )


def _gap(
    context: PrimitiveContext,
    point_id: str,
    squared_norm: Dyadic,
    radius: Dyadic,
    radius_squared: Dyadic,
) -> EndpointGap:
    # For r>=1 and N=10^9, both Nr-1 and sqrt(N²S) are nonnegative.
    # Squaring the two sides of r-1/N <= sqrt(S) <= r+1/N is
    # therefore equivalent, inclusive, and never needs a rounded square root.
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
    """Structural completeness, separately from isolation and finite membership."""
    return (
        len(ledger.support.roots) == len(ledger.roots) == 2
        and tuple(root.branch for root in ledger.support.roots) == ("MINUS", "PLUS")
        and all(root.multiplicity == 1 for root in ledger.support.roots)
        and all(
            member.support is support
            for member, support in zip(ledger.roots, ledger.support.roots, strict=True)
        )
    )


def _exact_endpoint_roots(form: str, boundaries: tuple[BoundaryLedger, ...]) -> bool:
    if form == "chord":
        minus, plus = boundaries[0].roots.roots
        return (
            minus.support.position == "AT_START"
            and minus.arc_position == "AT_START"
            and plus.support.position == "AT_END"
            and plus.arc_position == "AT_END"
        )
    for boundary, endpoint in zip(boundaries, ("AT_START", "AT_END"), strict=True):
        minus, plus = boundary.roots.roots
        if (
            minus.support.position != "BEFORE_START"
            or plus.support.position != "AT_END"
            or plus.arc_position != endpoint
        ):
            return False
    return True


def incidence_preflight(
    sketch: Sketch,
    height: int | float,
    *,
    context: PrimitiveContext | None = None,
) -> IncidenceReport:
    """Inspect exact shared-ID incidence prerequisites without side effects.

    Unchanged SketchError/ArcGeometryError exceptions precede new support gates.
    Core equal-radius checks run for every arc in authored-ID order, including
    unsupported multi-arc input. Numeric constraints are captured, never solved.
    One checked arithmetic context supplies the entire call; a supplied context
    is reused without resetting its counter or increasing its fixed limits.
    """
    validate(sketch)
    points = {point.id: point for point in sketch.points}
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
        for arc in sorted(sketch.arcs, key=lambda item: item.id)
    )
    if type(height) not in (int, float):
        raise IncidenceInputError("invalid_height")
    try:
        finite_height = math.isfinite(height)
    except OverflowError:
        raise IncidenceInputError("invalid_height") from None
    if not finite_height:
        raise IncidenceInputError("invalid_height")
    if context is None:
        context = PrimitiveContext()
    elif type(context) is not PrimitiveContext:
        raise IncidenceInputError("invalid_context")
    source_json = sketch.to_json()
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
            height,
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

    if len(sketch.arcs) != 1 or sketch.circles or len(sketch.lines) not in (1, 2):
        return report("unsupported", "unsupported_profile_form")
    arc = sketch.arcs[0]
    authored = _authored(arc, points)
    lines = _exact_lines(sketch, arc)
    if lines is None:
        code = (
            "unsupported_profile_coincidence"
            if _alias_form(sketch, arc, points)
            else "unsupported_profile_form"
        )
        return report("unsupported", code)
    form = "chord" if len(lines) == 1 else "sector"
    intended_count = len(lines)
    joins = (
        (
            NominalJoin(lines[0].id, "MINUS", arc.start),
            NominalJoin(lines[0].id, "PLUS", arc.end),
        )
        if form == "chord"
        else (
            NominalJoin(lines[0].id, "PLUS", arc.start),
            NominalJoin(lines[1].id, "PLUS", arc.end),
        )
    )
    stage = "SUPPORT"
    radius = core_arcs[0][1].start_radius
    if not (1 <= radius <= 1000 and 1 <= height <= 1000):
        return report("unsupported", "unsupported_profile_scale")
    try:
        start_ray = context.vector(authored.center, authored.start)
        end_ray = context.vector(authored.center, authored.end)
        ray_dot = context.dot(start_ray, end_ray)
        zero = context._make(0, 0)
        if context._compare(ray_dot, zero) > 0:
            return report("unsupported", "unsupported_profile_sweep")
        if (
            form == "sector"
            and context._compare(context.cross(start_ray, end_ray), zero) == 0
            and context._compare(ray_dot, zero) >= 0
        ):
            return report("unsupported", "unsupported_profile_sweep")
        radius_exact = context.coordinate(radius)
        radius_squared = context._mul(radius_exact, radius_exact)
        supports = (
            ((arc.start, arc.end),)
            if form == "chord"
            else ((arc.center, arc.start), (arc.center, arc.end))
        )
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
        # Every intended support call has returned before a discrepancy decision.
        if form == "chord":
            support = boundaries[0].roots.support
            if context._compare(support.discriminant, zero) <= 0:
                return report("unsupported", "unsupported_profile_nontransverse")
            lhs = context._mul(context._make(9, 0), support.discriminant)
            rhs = context._mul(context._make(16, 0), context._mul(support.a, radius_squared))
            if context._compare(lhs, rhs) < 0:
                return report("unsupported", "unsupported_profile_nontransverse")
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
            if not _exact_endpoint_roots(form, tuple(boundaries)):
                return report("unsupported", "unsupported_endpoint_incidence")
            return report("exact_endpoint_incidence", "exact_endpoint_incidence")
        return report("requires_incidence_cells", "requires_incidence_cells")
    except PrimitiveError as exc:
        if exc.code not in ("integer_limit", "operation_limit"):
            raise
        return report("numerical_ambiguity", exc.code)
