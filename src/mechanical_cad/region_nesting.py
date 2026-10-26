"""Pure analytic nesting of validated closed line/circle boundaries.

No triangulation or proximity-based joins: contacts within tolerance are rejected.
The deterministic even/odd rule supports holes and islands, independent of winding.
"""

from __future__ import annotations

import math

from .errors import CADException
from .profile_region import (
    PROFILE_TOLERANCE_MM,
    CircleProfile,
    ProfileRegion,
    ProfileRegions,
    _intersects,
)


def boundary_key(loop):
    return (loop.circle_id,) if isinstance(loop, CircleProfile) else tuple(sorted(loop.edge_ids))


def _segments(loop):
    return zip(loop.points, (*loop.points[1:], loop.points[0]), strict=True)


def _distance_to_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _contact(left, right):
    tol = PROFILE_TOLERANCE_MM
    if isinstance(left, CircleProfile) and isinstance(right, CircleProfile):
        distance = math.dist(left.center, right.center)
        return abs(left.radius - right.radius) - tol <= distance <= left.radius + right.radius + tol
    if isinstance(right, CircleProfile):
        left, right = right, left
    if isinstance(left, CircleProfile):
        for a, b in _segments(right):
            closest = _distance_to_segment(left.center, a, b)
            farthest = max(math.dist(left.center, a), math.dist(left.center, b))
            if closest <= left.radius + tol and farthest >= left.radius - tol:
                return True
        return False
    return any(
        _intersects(a, b, c, d, tol) for a, b in _segments(left) for c, d in _segments(right)
    )


def _inside(point, loop):
    if isinstance(loop, CircleProfile):
        return math.dist(point, loop.center) < loop.radius
    x, y = point
    inside = False
    for a, b in _segments(loop):
        if (a[1] > y) != (b[1] > y):
            crossing = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < crossing:
                inside = not inside
    return inside


def _sample(loop):
    # Sample ON the boundary, not its center: centers can be inside child holes.
    if isinstance(loop, CircleProfile):
        return (loop.center[0] + loop.radius, loop.center[1])
    return loop.points[0]


def nest_boundaries(loops):
    """Return all filled regions; refuse ambiguous touching/crossing boundaries."""
    loops = tuple(sorted(loops, key=boundary_key))
    if not loops:
        raise CADException("invalid_profile", "No closed boundaries were supplied.")
    identifiers = tuple(identifier for loop in loops for identifier in boundary_key(loop))
    if len(set(identifiers)) != len(identifiers):
        raise CADException("invalid_profile", "Boundary entity IDs must be unique.")
    for index, left in enumerate(loops):
        for right in loops[index + 1 :]:
            if _contact(left, right):
                raise CADException(
                    "self_intersecting_profile",
                    "Profile boundaries cross, overlap or touch. Separate them before extrusion.",
                )
    containers = [
        {
            other
            for other, parent in enumerate(loops)
            if other != index and _inside(_sample(loop), parent)
        }
        for index, loop in enumerate(loops)
    ]
    regions = []
    for index, loop in enumerate(loops):
        depth = len(containers[index])
        if depth % 2:
            continue
        holes = tuple(
            child
            for other, child in enumerate(loops)
            if index in containers[other] and len(containers[other]) == depth + 1
        )
        regions.append(ProfileRegion(loop, holes))
    return ProfileRegions(tuple(regions), identifiers)
