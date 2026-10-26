"""Explicit local-plane line axis intent, without snapping or solver authority."""

from .general_sketch_commands import DraftError, PointRef


def anchor_position(proposal, points):
    anchor = proposal["anchor"]
    return points[anchor["point_id"]] if anchor["kind"] == "existing" else anchor["position"]


def point_position(point, points):
    return points[point.id] if isinstance(point, PointRef) else (point.u, point.v)


def project_axis(start, pointer):
    axis = "horizontal" if abs(pointer[0] - start[0]) >= abs(pointer[1] - start[1]) else "vertical"
    return axis, (pointer[0], start[1]) if axis == "horizontal" else (start[0], pointer[1])


def require_axis(start, end, axis):
    if axis not in {"horizontal", "vertical"}:
        raise DraftError("Choose Horizontal or Vertical for the Line endpoint.")
    fixed = 1 if axis == "horizontal" else 0
    if abs(start[fixed] - end[fixed]) > 1e-9:
        raise DraftError("Existing point is off axis. Release Shift to reuse it, or move away to create a new point.")
