"""Conservative pure classification of solved sketch profile boundaries.

Connectivity comes from shared point IDs and explicit coincidence constraints,
never geometric nearest-neighbor guesses. The legacy line-loop extractor retains
its contract; the classifier additionally admits an analytic disk or a supported
open line chain. Closed boundaries use explicit even/odd nesting; touching and crossing loops fail.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import CADException

if TYPE_CHECKING:
    from .sketch_model import Sketch

PROFILE_TOLERANCE_MM = 1e-7


@dataclass(frozen=True)
class ClosedProfile:
    """Counterclockwise local-plane vertices and corresponding stable line IDs."""

    points: tuple[tuple[float, float], ...]
    edge_ids: tuple[str, ...]


@dataclass(frozen=True)
class CircleProfile:
    """An analytic local-plane disk with one stable authored circle identity."""

    center: tuple[float, float]
    radius: float
    circle_id: str


@dataclass(frozen=True)
class ProfileRegion:
    """One filled outer boundary with its immediate empty interior boundaries."""

    outer: ClosedProfile | CircleProfile
    holes: tuple[ClosedProfile | CircleProfile, ...] = ()


@dataclass(frozen=True)
class ProfileRegions:
    """All bounded faces selected by the sketch's even/odd fill rule."""

    regions: tuple[ProfileRegion, ...]
    boundary_ids: tuple[str, ...]


@dataclass(frozen=True)
class OpenChainProfile:
    """Saveable connected linework, explicitly unavailable for extrusion."""

    points: tuple[tuple[float, float], ...]
    edge_ids: tuple[str, ...]
    reason_code: str = "open_profile"
    message: str = "Close this line chain before extrusion."


def validate_circle(center, radius, circle_id) -> CircleProfile:
    """Validate the analytic region without imposing a center-plus-radius bound."""
    from .sketch_model import IDENTIFIER

    if type(circle_id) is not str or not IDENTIFIER.fullmatch(circle_id):
        raise CADException("invalid_profile", "Circle boundary requires a stable ASCII ID.")
    if (
        not isinstance(center, (tuple, list))
        or len(center) != 2
        or any(
            type(value) not in (int, float) or abs(value) > 1e6 or not math.isfinite(value)
            for value in center
        )
    ):
        raise CADException("invalid_profile", "Circle center must be a finite bounded u/v pair.")
    if type(radius) not in (int, float) or not 1e-6 <= radius <= 1e6 or not math.isfinite(radius):
        raise CADException("degenerate_profile", "Circle radius must be within 1e-6–1e6 mm.")
    return CircleProfile(tuple(float(value) for value in center), float(radius), circle_id)


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, p, tolerance):
    return abs(_cross(a, b, p)) <= tolerance * math.dist(a, b) and all(
        min(a[axis], b[axis]) - tolerance <= p[axis] <= max(a[axis], b[axis]) + tolerance
        for axis in (0, 1)
    )


def _intersects(a, b, c, d, tolerance):
    ab_c, ab_d, cd_a, cd_b = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    if ab_c * ab_d < 0 and cd_a * cd_b < 0:
        return True
    return any(
        _on_segment(first, second, point, tolerance)
        for first, second, point in ((a, b, c), (a, b, d), (c, d, a), (c, d, b))
    )


def validate_polygon(points, edge_ids) -> ClosedProfile:
    """Validate a bounded simple polygon and normalize winding without losing IDs."""
    if (
        not isinstance(points, (tuple, list))
        or not isinstance(edge_ids, (tuple, list))
        or not 3 <= len(points) <= 256
        or len(points) != len(edge_ids)
    ):
        raise CADException("invalid_profile", "A profile needs 3–256 lines in one closed loop.")
    if any(not isinstance(i, str) or not i for i in edge_ids) or len(set(edge_ids)) != len(
        edge_ids
    ):
        raise CADException("invalid_profile", "Profile boundary line IDs must be unique strings.")
    tolerance = PROFILE_TOLERANCE_MM
    vertices = []
    for point in points:
        if (
            not isinstance(point, (tuple, list))
            or len(point) != 2
            or any(
                type(value) not in (int, float) or abs(value) > 1e6 or not math.isfinite(value)
                for value in point
            )
        ):
            raise CADException(
                "invalid_profile", "Profile coordinates must be finite bounded u/v pairs."
            )
        vertices.append(tuple(float(value) for value in point))
    count = len(vertices)
    for index, a in enumerate(vertices):
        b, c = vertices[(index + 1) % count], vertices[(index + 2) % count]
        if math.dist(a, b) < 1e-6:
            raise CADException("degenerate_profile", f"Boundary '{edge_ids[index]}' is too short.")
        # Adjacent segments may be collinear, but must not double back/overlap.
        if abs(_cross(a, b, c)) <= tolerance * max(math.dist(a, b), math.dist(b, c)) and (
            (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1]) > 0
        ):
            raise CADException("self_intersecting_profile", "Adjacent boundaries overlap.")
        for other in range(index + 1, count):
            if other == (index + 1) % count or index == (other + 1) % count:
                continue
            d, e = vertices[other], vertices[(other + 1) % count]
            if _intersects(a, b, d, e, tolerance):
                raise CADException(
                    "self_intersecting_profile", "Nonadjacent boundaries cross or touch."
                )
    origin = vertices[0]
    area_twice = sum(
        _cross(origin, vertices[index], vertices[(index + 1) % count])
        for index in range(1, count - 1)
    )
    if abs(area_twice) < 2e-12:
        raise CADException("degenerate_profile", "The closed profile has no usable area.")
    boundaries = tuple(edge_ids)
    if area_twice < 0:
        vertices = [vertices[0], *reversed(vertices[1:])]
        boundaries = tuple(reversed(boundaries))
    return ClosedProfile(tuple(vertices), boundaries)


def _require_profile_capability(sketch: Sketch) -> None:
    """Fail explicitly while new record semantics await analytic profile support."""
    from .sketch_model import sketch_capabilities

    if sketch_capabilities(sketch.schema_version).arcs:
        raise CADException(
            "unsupported_profile_version",
            "Arc-capable sketch profiles require the matching result-version-3 backend. "
            "This core-only preview does not yet construct arc profiles.",
        )


def closed_profile(sketch: Sketch) -> ClosedProfile:
    """Extract one closed line region from a successful numeric solver result."""
    _require_profile_capability(sketch)
    positions, adjacency, endpoints = _line_connectivity(sketch)
    if len(endpoints) < 3 or any(len(lines) != 2 for lines in adjacency.values()):
        raise CADException(
            "open_profile", "The profile must be one closed line loop without branches."
        )
    start = min(adjacency)
    current = start
    visited = set()
    ordered_points, ordered_edges = [], []
    while True:
        available = sorted(line for line in adjacency[current] if line not in visited)
        if not available:
            break
        line = available[0]
        ordered_points.append(positions[current])
        ordered_edges.append(line)
        visited.add(line)
        a, b = endpoints[line]
        current = b if current == a else a
        if current == start:
            break
    if current != start or len(visited) != len(endpoints):
        raise CADException(
            "multiple_profile_regions", "Only one closed region without holes is supported."
        )
    return validate_polygon(ordered_points, ordered_edges)


def _line_connectivity(sketch: Sketch):
    """Identity/coincidence connectivity shared with the frozen legacy extractor."""
    points = {point.id: point for point in sketch.points}
    parents = {identifier: identifier for identifier in points}

    def root(identifier):
        while parents[identifier] != identifier:
            identifier = parents[identifier]
        return identifier

    for constraint in sketch.constraints:
        if constraint.kind == "coincident":
            left, right = sorted(root(identifier) for identifier in constraint.refs)
            parents[right] = left
    groups = {}
    for identifier, point in points.items():
        groups.setdefault(root(identifier), []).append(point)
    positions = {}
    for identifier, members in groups.items():
        representative = points[identifier]
        position = (representative.u, representative.v)
        if any(math.dist(position, (point.u, point.v)) > PROFILE_TOLERANCE_MM for point in members):
            raise CADException(
                "unresolved_coincidence", "Coincident point results exceed the profile tolerance."
            )
        positions[identifier] = position
    adjacency = {}
    endpoints = {}
    for line in sketch.lines:
        if getattr(line, "construction", False):
            continue
        start, end = root(line.start), root(line.end)
        if start == end:
            raise CADException(
                "degenerate_profile", f"Line '{line.id}' collapses to one connected point."
            )
        endpoints[line.id] = (start, end)
        adjacency.setdefault(start, []).append(line.id)
        adjacency.setdefault(end, []).append(line.id)
    return positions, adjacency, endpoints


def _validate_open_chain(points, edge_ids) -> OpenChainProfile:
    """Validate all segments and contacts; an open chain has no area requirement."""
    if not 1 <= len(edge_ids) <= 256 or len(points) != len(edge_ids) + 1:
        raise CADException("invalid_profile", "An open chain requires 1–256 connected lines.")
    if any(
        type(value) not in (int, float) or abs(value) > 1e6 or not math.isfinite(value)
        for point in points
        for value in point
    ):
        raise CADException(
            "invalid_profile", "Profile coordinates must be finite bounded u/v pairs."
        )
    vertices = tuple(tuple(float(value) for value in point) for point in points)
    tolerance = PROFILE_TOLERANCE_MM
    for index, (a, b) in enumerate(zip(vertices, vertices[1:], strict=False)):
        if math.dist(a, b) < 1e-6:
            raise CADException("degenerate_profile", f"Boundary '{edge_ids[index]}' is too short.")
        if index + 2 < len(vertices):
            c = vertices[index + 2]
            if abs(_cross(a, b, c)) <= tolerance * max(math.dist(a, b), math.dist(b, c)) and (
                (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1]) > 0
            ):
                raise CADException("self_intersecting_profile", "Adjacent boundaries overlap.")
        for other in range(index + 2, len(edge_ids)):
            if _intersects(a, b, vertices[other], vertices[other + 1], tolerance):
                raise CADException(
                    "self_intersecting_profile", "Nonadjacent boundaries cross or touch."
                )
    return OpenChainProfile(vertices, tuple(edge_ids))


def classify_profile(
    sketch: Sketch,
) -> ClosedProfile | CircleProfile | OpenChainProfile | ProfileRegions:
    """Classify successfully solved records, independently of solver/kernel state.

    Only one connected, nondegenerate and nonintersecting unbranched line chain
    becomes an open output. Unsupported boundaries raise their profile-stage
    error; they never become a successful open sketch by catching an exception.
    Unused points remain in the solved sketch and its native DoF evidence.
    """
    _require_profile_capability(sketch)
    circles = tuple(
        circle for circle in sketch.circles if not getattr(circle, "construction", False)
    )
    positions, adjacency, endpoints = _line_connectivity(sketch)
    if circles or (endpoints and all(len(lines) == 2 for lines in adjacency.values())):
        loops = []
        for circle in circles:
            center = next(point for point in sketch.points if point.id == circle.center)
            loops.append(validate_circle((center.u, center.v), circle.radius, circle.id))
        if endpoints:
            if any(len(lines) > 2 for lines in adjacency.values()):
                raise CADException("branched_profile", "Branched linework is not a profile.")
            if any(len(lines) != 2 for lines in adjacency.values()):
                raise CADException(
                    "mixed_profile_regions",
                    "Close all line boundaries before combining them with circles.",
                )
            remaining = set(endpoints)
            while remaining:
                start = min(point for line in remaining for point in endpoints[line])
                current = start
                vertices, identifiers = [], []
                while True:
                    available = sorted(line for line in adjacency[current] if line in remaining)
                    if not available:
                        break
                    line = available[0]
                    vertices.append(positions[current])
                    identifiers.append(line)
                    remaining.remove(line)
                    a, b = endpoints[line]
                    current = b if current == a else a
                    if current == start:
                        break
                if current != start:
                    raise CADException("open_profile", "Every boundary must close explicitly.")
                if len(identifiers) < 3:
                    raise CADException(
                        "degenerate_profile", "A closed line region needs at least 3 lines."
                    )
                loops.append(validate_polygon(vertices, identifiers))
        if len(loops) == 1:
            return loops[0]
        from .region_nesting import nest_boundaries

        return nest_boundaries(loops)
    if not endpoints:
        if any(
            getattr(curve, "construction", False)
            for curve in (*sketch.lines, *sketch.circles, *getattr(sketch, "arcs", ()))
        ):
            return OpenChainProfile(
                (), (), message="Add a closed non-construction boundary before extrusion."
            )
        raise CADException("invalid_profile", "A profile requires linework or a circle.")
    if any(len(lines) > 2 for lines in adjacency.values()):
        raise CADException("branched_profile", "Branched linework is not a supported profile.")
    # Check connectivity before deciding open/closed, including a separate cycle
    # beside an otherwise valid chain. Coordinate proximity does not join graphs.
    pending, connected = [min(adjacency)], set()
    while pending:
        current = pending.pop()
        if current in connected:
            continue
        connected.add(current)
        for line in adjacency[current]:
            pending.extend(endpoint for endpoint in endpoints[line] if endpoint not in connected)
    if len(connected) != len(adjacency):
        raise CADException(
            "multiple_profile_regions", "Only one connected line chain or closed loop is supported."
        )
    ends = sorted(point for point, lines in adjacency.items() if len(lines) == 1)
    if not ends:
        if len(endpoints) < 3:
            raise CADException("degenerate_profile", "A closed line region needs at least 3 lines.")
        return closed_profile(sketch)
    if len(ends) != 2:
        raise CADException("invalid_profile", "Linework must form one chain with two endpoints.")
    current = ends[0]
    visited = set()
    ordered_points, ordered_edges = [positions[current]], []
    while len(visited) < len(endpoints):
        line = next(line for line in adjacency[current] if line not in visited)
        ordered_edges.append(line)
        visited.add(line)
        a, b = endpoints[line]
        current = b if current == a else a
        ordered_points.append(positions[current])
    return _validate_open_chain(ordered_points, ordered_edges)
