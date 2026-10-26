"""Small libslvs adapter; geometry solving is performed by SolveSpace.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import IntEnum
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from threading import RLock
from typing import Any

from .arc_geometry import ArcGeometryError, arc_geometry
from .errors import CADException
from .fillet_intent import FilletIntentError
from .fillet_intent import validate_solved as validate_fillet_solution

# Re-exports retain the initial spike API while records stay backend-independent.
from .sketch_model import (
    Arc,
    Circle,
    Constraint,
    Line,
    Plane,
    Point,
    Sketch,
    SketchError,
    active_scalar_count,
    validate,
)
from .sketch_model import finite_vector as _finite
from .sketch_relations import PAIR_RELATIONS, angle_residual, canonical_refs, pair_residual

__all__ = [
    "Arc",
    "Circle",
    "Constraint",
    "Line",
    "Plane",
    "Point",
    "Sketch",
    "SolveReport",
    "Status",
    "solve",
    "drag",
]

# Every native convenience-API caller must share this lock or isolate processes.
_SOLVER_LOCK = RLock()


class Status(IntEnum):
    OKAY = 0
    INCONSISTENT = 1
    DIDNT_CONVERGE = 2
    TOO_MANY_UNKNOWNS = 3
    REDUNDANT_OKAY = 4


@dataclass(frozen=True)
class SolveReport:
    status: Status
    # Only expose DoF as meaningful when the solve is successful.
    remaining_dof: int | None
    failed_constraints: tuple[str, ...]
    # Output equals input on failure. The caller explicitly commits success.
    sketch: Sketch
    max_residual: float | None
    # Exact repeated equations skipped only during native compilation. All
    # persistent records remain intact in sketch, including these stable IDs.
    redundant_constraints: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return self.status in (Status.OKAY, Status.REDUNDANT_OKAY)


def _residual(sketch: Sketch) -> float:
    """Independent checks on the small supported constraint subset, not a solver."""
    points = {p.id: p for p in sketch.points}
    lines = {line.id: line for line in sketch.lines}
    circles = {circle.id: circle for circle in sketch.circles}
    arcs = {}
    residuals = [0.0]
    for arc in sketch.arcs:
        geometry = arc_geometry(
            (points[arc.center].u, points[arc.center].v),
            (points[arc.start].u, points[arc.start].v),
            (points[arc.end].u, points[arc.end].v),
            arc.direction,
            require_equal_radii=True,
        )
        arcs[arc.id] = geometry
        residuals.append(abs(geometry.start_radius - geometry.end_radius))
    for c in sketch.constraints:
        if c.kind in ("horizontal", "vertical"):
            line = lines[c.refs[0]]
            a, b = points[line.start], points[line.end]
            residuals.append(abs(a.v - b.v) if c.kind == "horizontal" else abs(a.u - b.u))
        elif c.kind in ("distance", "coincident"):
            a, b = (points[r] for r in c.refs)
            length = math.hypot(a.u - b.u, a.v - b.v)
            residuals.append(abs(length - (c.value if c.kind == "distance" else 0.0)))
        elif c.kind == "angle":
            residuals.append(
                angle_residual(
                    c.refs,
                    c.value,
                    {key: (point.u, point.v) for key, point in points.items()},
                    {key: {"start": line.start, "end": line.end} for key, line in lines.items()},
                )
            )
        elif c.kind in PAIR_RELATIONS:
            residuals.append(
                pair_residual(
                    c.kind,
                    c.refs,
                    {key: (p.u, p.v) for key, p in points.items()},
                    {key: {"start": item.start, "end": item.end} for key, item in lines.items()},
                    {
                        key: {"radius": item.radius, "center": item.center}
                        for key, item in circles.items()
                    },
                    {
                        item.id: {"center": item.center, "start": item.start, "end": item.end}
                        for item in sketch.arcs
                    },
                )
            )
        elif c.kind == "fixed":
            p = points[c.refs[0]]
            residuals.append(math.hypot(p.u - c.target[0], p.v - c.target[1]))
        elif c.kind == "radius":
            radius = (
                arcs[c.refs[0]].start_radius if c.refs[0] in arcs else circles[c.refs[0]].radius
            )
            residuals.append(abs(radius - c.value))
    return max(residuals)


def _load_backend():
    try:
        backend = import_module("slvs")
        installed = version("slvs")
    except (ImportError, OSError, PackageNotFoundError) as exc:
        raise CADException(
            "solver_unavailable",
            "The constrained-sketch solver is unavailable. Install the optional "
            "sketch dependency in the Mechanical CAD sidecar Python environment: "
            "pip install 'mechanical-cad[sketch]' (slvs==3.2).",
        ) from exc
    if installed != "3.2":
        raise CADException("solver_version", f"slvs==3.2 is required; found {installed}.")
    return backend


# Advertised only by this actual imported adapter, which owns the audited guard.
BACKEND_CAPABILITIES = frozenset({"mcad.solver-dof-cycle-guard/1"})


def solve(sketch: Sketch, *, diagnose: bool = True) -> SolveReport:
    """Compile stable IDs into temporary native handles and solve atomically."""
    validate(sketch)
    if type(diagnose) is not bool:
        raise SketchError("invalid_sketch", "diagnose must be a boolean")
    # slvs 3.2 can report OKAY with an incorrect DoF for a cycle of active
    # coordinate equalities. Detect the known substitution hazard before native
    # work; a residual or successful native status cannot certify its rank.
    unique, _ = _unique_relations(sketch)
    _require_acyclic_coordinate_equalities(sketch, unique)
    with _SOLVER_LOCK:
        slvs = _load_backend()
        slvs.clear_sketch()
        try:
            return _solve_locked(sketch, diagnose, slvs)
        finally:
            slvs.clear_sketch()


def _unique_relations(sketch: Sketch) -> tuple[tuple[Constraint, ...], tuple[str, ...]]:
    """Collapse only provably identical current equations, never stored intent.

    Native slvs can falsely report inconsistency for exact duplicate relations
    from unsolved seeds. No tolerance, coincidence propagation, near-equality,
    or general algebraic equivalence is used here. Different formula records
    may resolve to equal values now and become distinct on the next rebuild.
    """
    equations, duplicates = {}, []
    for constraint in sorted(sketch.constraints, key=lambda item: item.id):
        refs = canonical_refs(constraint.kind, constraint.refs)
        key = (constraint.kind, refs, constraint.value, constraint.target)
        if key in equations:
            duplicates.append(constraint.id)
        else:
            # Native endpoint order can select a different underconstrained
            # placement. Normalize the temporary equation, not persisted intent.
            equations[key] = replace(constraint, refs=refs)
    # A new duplicate with a smaller ID must not move an equation earlier in
    # native compilation and thereby perturb the unconstrained solution branch.
    return tuple(equations[key] for key in sorted(equations)), tuple(duplicates)


def _require_acyclic_coordinate_equalities(
    sketch: Sketch, constraints: tuple[Constraint, ...]
) -> None:
    """Reject the pinned solver's proven active-parameter substitution hazard.

    This is a conservative capability gate, not rank estimation or a new solver.
    Coincidence equates both coordinates; H/V equate v/u respectively. Different
    lines can generate the same scalar equation, so parallel edges also count.
    Fixed-target parameters are group 1 and excluded from native substitution.
    Do not reduce a cyclic graph to a forest or delete authored constraint IDs.
    """
    parents = {(point.id, axis): (point.id, axis) for point in sketch.points for axis in (0, 1)}
    lines = {line.id: line for line in sketch.lines}

    def root(node):
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node

    for constraint in constraints:
        if constraint.kind == "coincident":
            start, end = constraint.refs
            axes = (0, 1)
        elif constraint.kind == "concentric":
            circles = {item.id: item for item in sketch.circles}
            start, end = (circles[identifier].center for identifier in constraint.refs)
            axes = (0, 1)
        elif constraint.kind in ("horizontal", "vertical"):
            line = lines[constraint.refs[0]]
            start, end = line.start, line.end
            axes = (1,) if constraint.kind == "horizontal" else (0,)
        else:
            continue
        for axis in axes:
            left, right = root((start, axis)), root((end, axis))
            if left == right:
                raise SketchError(
                    "solver_dof_indeterminate",
                    "Cannot reliably determine sketch freedom: cyclic coincidence or "
                    "horizontal/vertical coordinate equalities trigger a known slvs 3.2 "
                    "counting defect. Keep this draft and explicitly review its equality "
                    "relations; no relation has been removed and no current solve is accepted.",
                )
            parents[right] = left


def _solve_locked(sketch: Sketch, diagnose: bool, slvs) -> SolveReport:
    fixed_group, active_group = 1, 2
    origin = slvs.add_point_3d(fixed_group, *sketch.plane.origin)
    normal = slvs.add_normal_3d(fixed_group, *sketch.plane.quaternion)
    wp = slvs.add_workplane(fixed_group, origin, normal)
    entities: dict[str, Any] = {}
    constraints: dict[int, str] = {}
    radius_entities: dict[str, Any] = {}
    # Stable compile order matters for reproducible branch choices.
    for point in sorted(sketch.points, key=lambda x: x.id):
        entities[point.id] = slvs.add_point_2d(active_group, float(point.u), float(point.v), wp)
    for line in sorted(sketch.lines, key=lambda x: x.id):
        entities[line.id] = slvs.add_line_2d(
            active_group, entities[line.start], entities[line.end], wp
        )
    # Append the new entity family after legacy points/lines. A v1 sketch's
    # native entity and equation compilation order remains exactly unchanged.
    for circle in sorted(sketch.circles, key=lambda x: x.id):
        radius_entity = slvs.add_distance(active_group, float(circle.radius), wp)
        radius_entities[circle.id] = radius_entity
        entities[circle.id] = slvs.add_circle(
            active_group, normal, entities[circle.center], radius_entity, wp
        )
    for arc in sorted(sketch.arcs, key=lambda x: x.id):
        # slvs arcs are CCW in the workplane. Swapping only these temporary
        # arguments maps CW intent without replacing authored point identities.
        start, end = entities[arc.start], entities[arc.end]
        if arc.direction == "cw":
            start, end = end, start
        entities[arc.id] = slvs.add_arc(active_group, normal, entities[arc.center], start, end, wp)
    unique, redundant = _unique_relations(sketch)
    for c in unique:
        refs = [entities[r] for r in c.refs]
        if c.kind == "coincident":
            native = slvs.coincident(active_group, *refs, wp)
        elif c.kind in {"point_on_line", "midpoint"}:
            native = (slvs.coincident if c.kind == "point_on_line" else slvs.midpoint)(
                active_group, *refs, wp
            )
        elif c.kind == "symmetry":
            line = next(item for item in sketch.lines if item.id == c.refs[2])
            points = {item.id: item for item in sketch.points}
            a, b = points[line.start], points[line.end]
            if math.hypot(b.u - a.u, b.v - a.v) <= 1e-12:
                raise SketchError(
                    "invalid_sketch", "Symmetry requires a nondegenerate axis line seed."
                )
            # SYMMETRIC_LINE uses ptA, ptB and entityA (the infinite axis).
            native = slvs.add_constraint(
                active_group,
                slvs.ConstraintType.SYMMETRIC_LINE,
                wp,
                0.0,
                refs[0],
                refs[1],
                refs[2],
                slvs.E_NONE,
                slvs.E_NONE,
                slvs.E_NONE,
                0,
                0,
            )
        elif c.kind == "concentric":
            circles = {item.id: item for item in sketch.circles}
            native = slvs.coincident(
                active_group, *(entities[circles[r].center] for r in c.refs), wp
            )
        elif c.kind == "circle_line_tangent":
            circle = next(item for item in sketch.circles if item.id == c.refs[0])
            line = next(item for item in sketch.lines if item.id == c.refs[1])
            points = {item.id: item for item in sketch.points}
            a, b, center = points[line.start], points[line.end], points[circle.center]
            dx, dy = b.u - a.u, b.v - a.v
            length = math.hypot(dx, dy)
            if length <= 1e-12:
                raise SketchError(
                    "invalid_sketch", "Circle tangency requires a nondegenerate line seed."
                )
            along = ((center.u - a.u) * dx + (center.v - a.v) * dy) / (length * length)
            u, v = a.u + along * dx, a.v + along * dy
            if math.hypot(u - center.u, v - center.v) < 1e-9:
                u, v = (
                    center.u - dy / length * circle.radius,
                    center.v + dx / length * circle.radius,
                )
            contact = slvs.add_point_2d(active_group, u, v, wp)
            radius_line = slvs.add_line_2d(active_group, entities[circle.center], contact, wp)
            for equation in (
                slvs.coincident(active_group, contact, refs[1], wp),
                slvs.coincident(active_group, contact, refs[0], wp),
            ):
                constraints[equation["h"]] = c.id
            native = slvs.perpendicular(active_group, radius_line, refs[1], wp)
        elif c.kind == "horizontal":
            native = slvs.horizontal(active_group, refs[0], wp)
        elif c.kind == "vertical":
            native = slvs.vertical(active_group, refs[0], wp)
        elif c.kind == "distance":
            native = slvs.distance(active_group, *refs, float(c.value), wp)
        elif c.kind == "angle":
            native = slvs.angle(active_group, *refs, float(c.value), wp)
        elif c.kind in {"parallel", "perpendicular", "equal"}:
            native = getattr(slvs, c.kind)(active_group, *refs, wp)
        elif c.kind == "tangent":
            arc = next(item for item in sketch.arcs if item.id == c.refs[0])
            line = next(item for item in sketch.lines if item.id == c.refs[1])
            endpoint = next(iter({arc.start, arc.end} & {line.start, line.end}))
            native_start = arc.start if arc.direction == "ccw" else arc.end
            native = slvs.add_constraint(
                active_group,
                slvs.ConstraintType.ARC_LINE_TANGENT,
                wp,
                0.0,
                slvs.E_NONE,
                slvs.E_NONE,
                refs[0],
                refs[1],
                slvs.E_NONE,
                slvs.E_NONE,
                int(endpoint != native_start),
                0,
            )
        elif c.kind == "radius":
            # The canonical driving intent remains a radius. Only this native
            # call uses the diameter API; residuals and reported values use mm radius.
            native = slvs.diameter(active_group, refs[0], 2.0 * float(c.value))
        else:  # fixed: a group-1 target cannot be moved by the group-2 solve.
            target = slvs.add_point_2d(fixed_group, *c.target, wp)
            native = slvs.coincident(active_group, refs[0], target, wp)
        constraints[native["h"]] = c.id
    # slvs 3.2 returns a tuple only when diagnostics are requested.
    # Its .pyi does not describe that branch or the actual result keys.
    raw = slvs.solve_sketch(active_group, diagnose)
    info, failed = raw if diagnose else (raw, [])
    status = Status(info["result"])
    failed_ids = tuple(sorted({constraints[h] for h in failed}))
    if status not in (Status.OKAY, Status.REDUNDANT_OKAY):
        return SolveReport(status, None, failed_ids, sketch, None, redundant)
    positions = tuple(
        replace(
            point,
            u=slvs.get_param_value(entities[point.id]["param"][0]),
            v=slvs.get_param_value(entities[point.id]["param"][1]),
        )
        for point in sketch.points
    )
    circles = tuple(
        replace(circle, radius=slvs.get_param_value(radius_entities[circle.id]["param"][0]))
        for circle in sketch.circles
    )
    solved = replace(sketch, points=positions, circles=circles)
    try:
        validate(solved)
    except SketchError:
        # A native success code cannot authorize nonfinite/out-of-domain output.
        # In particular, a negative radius is a failure, never abs()-repaired.
        return SolveReport(Status.DIDNT_CONVERGE, None, failed_ids, sketch, None, redundant)
    try:
        validate_fillet_solution(solved.to_dict())
    except FilletIntentError as exc:
        raise CADException("fillet_out_of_bounds", str(exc)) from exc
    dof = info["dof"]
    if type(dof) is not int or not 0 <= dof <= active_scalar_count(sketch):
        return SolveReport(Status.DIDNT_CONVERGE, None, failed_ids, sketch, None, redundant)
    try:
        residual = _residual(solved)
    except ArcGeometryError:
        # A native success code never authorizes unequal solved arc radii or
        # an unsafe sweep. Keep the exact authored input; do not project it.
        return SolveReport(Status.DIDNT_CONVERGE, None, failed_ids, sketch, None, redundant)
    if residual > 1e-7:
        # Do not pass native false-positive results to the document/kernel.
        return SolveReport(Status.DIDNT_CONVERGE, None, failed_ids, sketch, residual, redundant)
    if redundant:
        status = Status.REDUNDANT_OKAY
    return SolveReport(status, dof, failed_ids, solved, residual, redundant)


def drag(sketch: Sketch, point_id: str, target: tuple[float, float]) -> SolveReport:
    """Exact-target drag trial, preserving all persistent constraints.

    This spike uses a temporary hard constraint and rejects unreachable cursor
    positions. It is NOT a nearest-feasible/soft interactive dragging algorithm.
    Successful results are re-solved without the temporary constraint so returned
    DoF and persistent records describe the original sketch, not the drag trial.
    """
    validate(sketch)
    if (
        type(point_id) is not str
        or point_id not in {p.id for p in sketch.points}
        or not _finite(target, 2)
    ):
        raise SketchError("invalid_sketch", "Drag requires an existing point and finite u/v target")
    # Internal constraint ID is intentionally outside the document ID namespace.
    drag_id = "drag-trial"
    used = {
        sketch.plane.id,
        *(
            r.id
            for r in (
                *sketch.points,
                *sketch.lines,
                *sketch.circles,
                *sketch.arcs,
                *sketch.constraints,
            )
        ),
    }
    suffix = 0
    while drag_id in used:
        suffix += 1
        drag_id = f"drag-trial-{suffix}"
    moved = replace(
        sketch,
        points=tuple(
            replace(p, u=float(target[0]), v=float(target[1])) if p.id == point_id else p
            for p in sketch.points
        ),
        constraints=sketch.constraints
        + (Constraint(drag_id, "fixed", (point_id,), target=tuple(target)),),
    )
    trial = solve(moved)
    if not trial.success:
        failed = tuple("@drag" if c == drag_id else c for c in trial.failed_constraints)
        return replace(trial, failed_constraints=failed, sketch=sketch)
    result = solve(replace(trial.sketch, constraints=sketch.constraints))
    return result if result.success else replace(result, sketch=sketch)
