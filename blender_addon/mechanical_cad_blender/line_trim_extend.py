"""Pure explicit line-end trimming/extension, with no inferred identity changes.

A picked endpoint moves to the intersection with a finite line segment, full
circle or directed analytic arc.
The boundary and every other entity remain untouched. Shared or constrained
endpoints are deliberately refused rather than detaching or losing relations.
"""

import math
from dataclasses import dataclass

from .arc_geometry import ArcGeometryError, arc_geometry


class LineEditError(ValueError):
    pass


@dataclass(frozen=True)
class LineEdit:
    point_id: str
    target: tuple
    fixed: tuple
    target_line: str
    boundary_line: str
    mode: str

    @property
    def proposal(self):
        return {
            "kind": "line",
            "anchor": {"kind": "new", "position": self.fixed},
            "endpoint": self.target,
        }


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def _circle_intersections(a, ab, length, center, radius):
    if not all(math.isfinite(x) for x in (*center, radius)) or radius <= 1e-7:
        raise LineEditError("The visible circle must have a finite positive radius.")
    direction = tuple(value / length for value in ab)
    relative = _sub(center, a)
    along = math.fsum(x * y for x, y in zip(relative, direction, strict=True))
    distance = abs(_cross(relative, direction))
    if distance > radius + 1e-7:
        raise LineEditError("The target line does not intersect this circle.")
    if abs(distance - radius) <= 1e-7:
        raise LineEditError("Tangent or nearly tangent contact is not a crossing boundary.")
    half_chord = math.sqrt((radius - distance) * (radius + distance))
    return ((along - half_chord) / length, (along + half_chord) / length)


def _arc_intersections(a, ab, length, arc):
    try:
        measured = arc_geometry(
            arc.center_mm,
            arc.start_mm,
            arc.end_mm,
            arc.direction,
            require_equal_radii=True,
        )
    except ArcGeometryError as exc:
        raise LineEditError(
            "The arc boundary needs a valid equal-radius solve: " + str(exc)
        ) from exc
    roots = _circle_intersections(a, ab, length, arc.center_mm, measured.start_radius)
    start_angle = math.atan2(arc.start_mm[1] - arc.center_mm[1], arc.start_mm[0] - arc.center_mm[0])
    accepted = []
    for root in roots:
        point = tuple(a[i] + root * ab[i] for i in range(2))
        # Spatial endpoint tolerance is explicit, not an angular expansion that
        # grows with radius. It also handles the signed-angle wrap at the start.
        if min(math.dist(point, arc.start_mm), math.dist(point, arc.end_mm)) <= 1e-7:
            accepted.append(root)
            continue
        angle = math.atan2(point[1] - arc.center_mm[1], point[0] - arc.center_mm[0])
        travel = (
            (angle - start_angle) if measured.sweep_radians > 0 else (start_angle - angle)
        ) % math.tau
        if travel <= abs(measured.sweep_radians):
            accepted.append(root)
    if not accepted:
        raise LineEditError("The circle intersections lie outside the picked finite arc sweep.")
    return accepted


def prepare_line_edit(
    sketch, points, target_line, boundary_line, near, mode, *, circles=None, arcs=None
):
    """Return an immutable preview from explicit IDs and visible local-mm points."""
    if mode not in {"Trim", "Extend"}:
        raise LineEditError("Choose Trim or Extend.")
    lines = {line["id"]: line for line in sketch["lines"]}
    circle_ids = {circle["id"] for circle in sketch.get("circles", ())}
    arc_ids = {arc["id"] for arc in sketch.get("arcs", ())}
    if target_line not in lines or target_line == boundary_line:
        raise LineEditError("Choose a target straight line and a different boundary.")
    if boundary_line not in lines and boundary_line not in circle_ids | arc_ids:
        raise LineEditError("Choose a finite boundary line, circle or arc.")
    line = lines[target_line]
    a, b = (tuple(points[line[key]]) for key in ("start", "end"))
    if not all(math.isfinite(x) for p in (a, b, near) for x in p):
        raise LineEditError("Line coordinates must be finite.")
    ab = _sub(b, a)
    length = math.dist(a, b)
    if length <= 1e-7:
        raise LineEditError("A zero-length line cannot be trimmed or used as a boundary.")
    tolerance = 1e-7 / length
    if boundary_line in arc_ids:
        if arcs is None or boundary_line not in arcs:
            raise LineEditError("The resolved arc is unavailable; check the sketch first.")
        intersections = _arc_intersections(a, ab, length, arcs[boundary_line])
    elif boundary_line in circle_ids:
        if circles is None or boundary_line not in circles:
            raise LineEditError("The resolved circle is unavailable; check the sketch first.")
        circle = circles[boundary_line]
        intersections = _circle_intersections(a, ab, length, circle.center_mm, circle.radius_mm)
    else:
        boundary = lines[boundary_line]
        c, d = (tuple(points[boundary[key]]) for key in ("start", "end"))
        if not all(math.isfinite(x) for p in (c, d) for x in p):
            raise LineEditError("Line coordinates must be finite.")
        cd = _sub(d, c)
        boundary_length = math.dist(c, d)
        if boundary_length <= 1e-7:
            raise LineEditError("A zero-length line cannot be trimmed or used as a boundary.")
        denominator = _cross(ab, cd)
        if abs(denominator) <= 1e-10 * length * boundary_length:
            raise LineEditError("Parallel or coincident lines have no unique intersection.")
        t = _cross(_sub(c, a), cd) / denominator
        u = _cross(_sub(c, a), ab) / denominator
        if not -1e-7 / boundary_length <= u <= 1 + 1e-7 / boundary_length:
            raise LineEditError("Intersection lies beyond the picked boundary segment.")
        intersections = (t,)
    start = math.dist(near, a) < math.dist(near, b)
    if abs(math.dist(near, a) - math.dist(near, b)) <= 1e-7:
        raise LineEditError("Pick closer to the endpoint you want to change.")
    if mode == "Trim":
        candidates = [t for t in intersections if tolerance < t < 1 - tolerance]
        if not candidates:
            raise LineEditError("Trim needs a boundary crossing inside the target line.")
    else:
        candidates = [t for t in intersections if (t < -tolerance if start else t > 1 + tolerance)]
        if not candidates:
            raise LineEditError(
                "Pick the endpoint facing the boundary, or use Trim for an interior crossing."
            )
    # First eligible crossing from the selected endpoint; excluded arc roots never win.
    t = min(candidates, key=lambda value: abs(value - (0 if start else 1)))
    point_id = line["start" if start else "end"]
    incident = []
    for name, roles in (
        ("lines", ("start", "end")),
        ("circles", ("center",)),
        ("arcs", ("start", "end", "center")),
    ):
        incident.extend(
            curve["id"]
            for curve in sketch.get(name, ())
            if any(curve[role] == point_id for role in roles)
        )
    if set(incident) != {target_line}:
        raise LineEditError(
            "This endpoint is shared. Trim/Extend will not detach or move connected curves."
        )
    affected = {point_id, target_line}
    relations = [
        relation["id"]
        for relation in sketch["constraints"]
        if affected.intersection(relation["refs"])
    ]
    if relations:
        raise LineEditError(
            "Release the target's relations explicitly before editing: " + ", ".join(relations)
        )
    target = tuple(a[i] + t * ab[i] for i in range(2))
    if any(abs(value) > 1e6 for value in target):
        raise LineEditError("The intersection exceeds the sketch coordinate limit.")
    return LineEdit(point_id, target, b if start else a, target_line, boundary_line, mode)
