"""Native-free drawing geometry and bounded, explicitly approximate pick proposals.

Nothing here solves, binds a reference, adds a constraint, or establishes topology.
All coordinates are millimetres; the caller projects world mm to viewport pixels
using one unchanged camera snapshot. Invisible projections return None. Blender
unit conversion belongs in that callback, not in saved sketch coordinates.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from . import operation_contracts
from .arc_geometry import arc_geometry
from .general_sketch_draft import read_guarded_operation
from .guarded_evidence import GuardedEvidence
from .reference_dimensions import is_reference, validate_reference
from .sketch_bridge import (
    _identifier,
    _keys,
    _require,
)
from .sketch_bridge import (
    _normalized_sketch as _legacy_normalized_sketch,
)
from .sketch_contracts_v3 import normalize_sketch_v3

MAX_CIRCLE_SEGMENTS = 2048
MAX_PROJECT_CALLS = 65536
_PIXEL_BOUND = 1e12


def _normalized_sketch(sketch, *, numeric=False):
    if (
        type(sketch) is dict
        and type(sketch.get("schema_version")) is int
        and (sketch["schema_version"] == 3)
    ):
        return normalize_sketch_v3(sketch, numeric=numeric)
    return _legacy_normalized_sketch(sketch, numeric=numeric)


def _number(value, bound=1e12, *, minimum=None):
    _require(type(value) in (int, float) and -bound <= value <= bound, "Invalid finite number.")
    value = float(value)
    _require(math.isfinite(value), "Invalid finite number.")
    _require(minimum is None or value >= minimum, "Number below the supported limit.")
    return value


def _vector(value, size, bound=1e12):
    _require(type(value) in (tuple, list) and len(value) == size, "Invalid coordinate vector.")
    return tuple(_number(item, bound) for item in value)


def _dot(left, right):
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


@dataclass(frozen=True)
class Workplane:
    """Temporary normalized basis; the saved WXYZ quaternion is never rewritten."""

    origin_mm: tuple
    u_axis: tuple
    v_axis: tuple
    normal: tuple

    @classmethod
    def from_saved(cls, plane):
        _keys(plane, {"id", "origin", "quaternion"})
        _identifier(plane["id"])
        origin = _vector(plane["origin"], 3, 1e6)
        quaternion = _vector(plane["quaternion"], 4, 1e6)
        norm_squared = _dot(quaternion, quaternion)
        _require(abs(norm_squared - 1) <= 1e-9, "Non-unit workplane quaternion.")
        w, x, y, z = (value / math.sqrt(norm_squared) for value in quaternion)
        return cls(
            origin,
            (1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)),
            (2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x)),
            (2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)),
        )

    def local_to_world(self, local_mm):
        """Map local XY mm onto the plane. Circle extents may exceed seed bounds."""
        u, v = _vector(local_mm, 2)
        return tuple(
            math.fsum((origin, u * a, v * b))
            for origin, a, b in zip(self.origin_mm, self.u_axis, self.v_axis, strict=True)
        )

    def world_to_local(self, world_mm):
        """Return (u, v, signed normal distance) mm; do not hide an off-plane point."""
        world = _vector(world_mm, 3)
        relative = tuple(a - b for a, b in zip(world, self.origin_mm, strict=True))
        return tuple(_dot(relative, axis) for axis in (self.u_axis, self.v_axis, self.normal))


@dataclass(frozen=True)
class RayPlaneHit:
    world_mm: tuple
    local_mm: tuple
    distance_mm: float


def intersect_ray(plane, origin_mm, direction, *, parallel_tolerance=1e-12):
    """Intersect a forward ray; parallel/coplanar rays and hits behind it miss.

    Normalize direction so parallel_tolerance is angular and distance_mm is a
    physical distance. No camera-plane fallback or coordinate seed is invented.
    """
    _require(type(plane) is Workplane, "Expected a normalized workplane.")
    origin, direction = _vector(origin_mm, 3), _vector(direction, 3)
    tolerance = _number(parallel_tolerance, 1e-3, minimum=0)
    length = math.hypot(*direction)
    _require(length > 0, "A ray needs a nonzero direction.")
    direction = tuple(value / length for value in direction)
    denominator = _dot(direction, plane.normal)
    if abs(denominator) <= tolerance:
        return None
    distance = (
        _dot(tuple(a - b for a, b in zip(plane.origin_mm, origin, strict=True)), plane.normal)
        / denominator
    )
    if distance < 0:
        return None
    world = tuple(math.fsum((a, distance * b)) for a, b in zip(origin, direction, strict=True))
    local = plane.world_to_local(world)
    return RayPlaneHit(world, local[:2], distance)


@dataclass(frozen=True)
class LineGeometry:
    start_id: str
    end_id: str
    start_mm: tuple
    end_mm: tuple
    construction: bool = False


@dataclass(frozen=True)
class CircleGeometry:
    center_id: str
    center_mm: tuple
    radius_mm: float
    construction: bool = False


@dataclass(frozen=True)
class ArcGeometry:
    center_id: str
    start_id: str
    end_id: str
    center_mm: tuple
    start_mm: tuple
    end_mm: tuple
    direction: str
    radius_mm: float
    sweep_radians: float
    construction: bool = False
    corner_fillet: bool = False


@dataclass(frozen=True)
class Dimension:
    kind: str
    refs: tuple
    value: int | float | str


@dataclass(frozen=True)
class SketchGeometry:
    """Read-only stable-ID maps. These are display records, never solver evidence."""

    source: str
    sketch_id: str
    request_fingerprint: str | None
    plane: Workplane
    points: MappingProxyType
    lines: MappingProxyType
    circles: MappingProxyType
    dimensions: MappingProxyType
    arcs: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    axis_relations: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))


def retained_outline(geometry):
    """Drop solver authority while keeping a previously checked display outline.

    The owner must bind this transient copy to its unchanged command revision.
    It is not persisted, accepted as a solution, or usable as export evidence.
    """
    _require(
        type(geometry) is SketchGeometry and geometry.source == "solved",
        "Only an explicitly solved display can become a retained outline.",
    )
    return replace(geometry, source="retained", request_fingerprint=None)


def build_guarded_geometry(
    authored_sketch, evidence, *, expected_prepared, current_selection, owner_token
):
    """Production solved display requires the original live guarded operation."""
    _require(type(evidence) is GuardedEvidence, "Expected guarded solved display evidence.")
    response = read_guarded_operation(
        evidence,
        expected_prepared,
        current_selection,
        owner_token=owner_token,
        action="solve_sketch",
        require_success=True,
    )
    request = expected_prepared.operation_request()
    source = next(
        item for item in request["document"]["features"] if item["id"] == request["feature_id"]
    )
    _normalized_sketch(authored_sketch)  # Bound and validate before encoding.
    _require(
        json.dumps(source["sketch"], sort_keys=True, allow_nan=False)
        == json.dumps(authored_sketch, sort_keys=True, allow_nan=False),
        "Guarded solve request differs from the exact authored sketch.",
    )
    return build_geometry(
        authored_sketch,
        source="solved",
        solve_request=request,
        solve_response=response,
    )


def build_geometry(authored_sketch, *, source, solve_request=None, solve_response=None):
    """Choose authored seeds or exact-request-validated solved geometry explicitly.

    For solved display the caller supplies its CURRENT complete request and response.
    The owner still checks base/revision/lifecycle currency: no pure geometry helper
    can know whether a supplied request is the owner's current request. Failed,
    absent, or mismatched evidence raises; authored seeds are never a silent fallback.
    Source dimension literals/formulas remain exactly as authored in either mode.
    """
    _require(type(source) is str and source in {"authored", "solved"}, "Choose a geometry source.")
    authored = _normalized_sketch(authored_sketch)
    selected, fingerprint = authored, None
    if source == "authored":
        _require(
            solve_request is None and solve_response is None,
            "Authored geometry does not consume solver evidence.",
        )
    else:
        _require(
            type(solve_request) is dict and type(solve_response) is dict,
            "Supply the current complete solve request and response.",
        )
        _require(solve_request.get("action") == "solve_sketch", "Expected solve_sketch display.")
        validated = operation_contracts.validate_response(solve_request, solve_response)
        _require(validated["ok"], "Current successful solve evidence is required.")
        request_source = next(
            item
            for item in solve_request["document"]["features"]
            if item["id"] == solve_request["feature_id"]
        )
        _require(
            _normalized_sketch(request_source["sketch"]) == authored,
            "Solve request differs from the supplied authored sketch.",
        )
        selected = _normalized_sketch(validated["result"]["sketch"]["solved"], numeric=True)
        fingerprint = validated["input_fingerprint"]
    points = {point["id"]: (point["u"], point["v"]) for point in selected["points"]}
    arcs = {}
    for arc in selected.get("arcs", []):
        center, start, end = (points[arc[key]] for key in ("center", "start", "end"))
        measured = arc_geometry(
            center, start, end, arc["direction"], require_equal_radii=source == "solved"
        )
        arcs[arc["id"]] = ArcGeometry(
            arc["center"],
            arc["start"],
            arc["end"],
            center,
            start,
            end,
            arc["direction"],
            measured.start_radius,
            measured.sweep_radians,
            arc.get("construction", False),
            "fillet_intent" in arc,
        )
    return SketchGeometry(
        source,
        selected["id"],
        fingerprint,
        Workplane.from_saved(selected["plane"]),
        MappingProxyType(points),
        MappingProxyType(
            {
                line["id"]: LineGeometry(
                    line["start"],
                    line["end"],
                    points[line["start"]],
                    points[line["end"]],
                    line.get("construction", False),
                )
                for line in selected["lines"]
            }
        ),
        MappingProxyType(
            {
                circle["id"]: CircleGeometry(
                    circle["center"],
                    points[circle["center"]],
                    circle["radius"],
                    circle.get("construction", False),
                )
                for circle in selected.get("circles", [])
            }
        ),
        MappingProxyType(
            {
                item["id"]: Dimension(item["kind"], tuple(item["refs"]), item["value"])
                for item in sorted(authored_sketch["constraints"], key=lambda item: item["id"])
                if item["kind"] in {"distance", "radius", "angle"}
            }
        ),
        MappingProxyType(arcs),
        MappingProxyType({
            item["id"]: (item["kind"], item["refs"][0])
            for item in authored["constraints"]
            if item["kind"] in {"horizontal", "vertical"}
        }),
    )


@dataclass(frozen=True)
class AnnotationGeometry:
    constraint_id: str
    kind: str
    refs: tuple
    value: int | float | str | None
    anchors_mm: tuple
    label_mm: tuple
    segments_mm: tuple


def annotation_geometry(geometry, constraint_id, placement):
    """Build layout for an exact available distance/radius binding, without editing.

    Distance offsets are from the endpoint midpoint; radius offsets are from the
    center, in local XY mm. A zero radius offset uses +U for a full circle and
    the swept midpoint for an arc. Values/formulas are not rounded or halved.
    Missing/changed bindings fail here; the UI owner retains their recovery state.
    """
    _require(type(geometry) is SketchGeometry, "Expected sketch display geometry.")
    _identifier(constraint_id)
    reference = is_reference(placement)
    if reference:
        validate_reference(constraint_id, placement)
        source_kind = placement["source_kind"]
        source = getattr(geometry, source_kind + "s").get(placement["refs"][0])
        _require(source is not None, "Reference measurement target is unavailable.")
        kind, refs, value = placement["kind"], tuple(placement["refs"]), None
    else:
        _keys(placement, {"kind", "refs", "display", "offset"})
        relation = geometry.dimensions.get(constraint_id)
        _require(relation is not None, "Annotation relation is unavailable.")
        _require(
            type(placement["refs"]) is list
            and placement["refs"] == list(relation.refs)
            and placement["kind"] == relation.kind
            and (placement["display"] == relation.kind or (relation.kind == "radius" and placement["display"] == "diameter")),
            "Annotation identity or radius-only display does not match its relation.",
        )
        kind, refs, value = placement["display"], relation.refs, relation.value
    offset = _vector(placement["offset"], 2, 1e6)
    if kind in {"radius", "diameter"}:
        circle = geometry.circles.get(refs[0]) or geometry.arcs[refs[0]]
        center = circle.center_mm
        length = math.hypot(*offset)
        direction = tuple(value / length for value in offset) if length else (1.0, 0.0)
        edge = tuple(a + circle.radius_mm * b for a, b in zip(center, direction, strict=True))
        if type(circle) is ArcGeometry and not length:
            edge = _arc_point(circle, 0.5)
        elif type(circle) is ArcGeometry:
            start = math.atan2(circle.start_mm[1] - center[1], circle.start_mm[0] - center[0])
            desired = math.atan2(direction[1], direction[0])
            delta = (desired - start) % math.tau
            if circle.sweep_radians < 0:
                delta = -((start - desired) % math.tau)
            if abs(delta) > abs(circle.sweep_radians):
                # Finite-sweep annotation only; authored endpoints remain raw.
                angle = start + circle.sweep_radians
                end = (
                    center[0] + circle.radius_mm * math.cos(angle),
                    center[1] + circle.radius_mm * math.sin(angle),
                )
                edge = min((circle.start_mm, end), key=lambda point: math.dist(point, edge))
        label = tuple(a + b for a, b in zip(center, offset, strict=True))
        anchors, segments = (center, edge), ((center, edge), (edge, label))
    elif kind == "angle":
        first, second = (geometry.lines[identifier] for identifier in refs)
        a, b = (
            tuple((x + y) / 2 for x, y in zip(line.start_mm, line.end_mm, strict=True))
            for line in (first, second)
        )
        label = tuple((x + y) / 2 + d for x, y, d in zip(a, b, offset, strict=True))
        anchors, segments = (a, b), ((a, label), (b, label))
    else:
        a, b = (
            (source.start_mm, source.end_mm)
            if kind == "length"
            else (geometry.points[identifier] for identifier in refs)
        )
        length = math.dist(a, b)
        _require(length > 0, "Collapsed distance anchors have no aligned annotation direction.")
        normal = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)
        displacement = tuple(value * _dot(offset, normal) for value in normal)
        left = tuple(p + d for p, d in zip(a, displacement, strict=True))
        right = tuple(p + d for p, d in zip(b, displacement, strict=True))
        label = tuple((p + q) / 2 + d for p, q, d in zip(a, b, offset, strict=True))
        anchors, segments = (a, b), ((a, left), (left, right), (right, b))
    return AnnotationGeometry(constraint_id, kind, refs, value, anchors, label, segments)


@dataclass(frozen=True)
class HitCandidate:
    kind: str
    identifier: str
    distance_px: float
    nearest_screen: tuple
    method: str
    observed_error_px: float = 0.0


@dataclass(frozen=True)
class ProjectionIssue:
    kind: str
    identifier: str
    reason: str
    turns: tuple | None = None


@dataclass(frozen=True)
class PickResult:
    status: str
    candidates: tuple
    nearest: tuple
    unavailable: tuple
    projection_calls: int

    @property
    def unique(self):
        """A unique *proposal*, never permission to bind or create a constraint."""
        return self.nearest[0] if self.status == "unique" else None


class _ProjectionLimit(Exception):
    pass


class _Projection:
    def __init__(self, plane, callback, limit):
        self.plane, self.callback, self.limit = plane, callback, limit
        self.cache, self.calls = {}, 0

    def at(self, local):
        if local not in self.cache:
            if self.calls == self.limit:
                raise _ProjectionLimit
            self.calls += 1
            value = self.callback(self.plane.local_to_world(local))
            self.cache[local] = None if value is None else _vector(value, 2, _PIXEL_BOUND)
        return self.cache[local]


def _nearest_segment(query, a, b):
    delta = (b[0] - a[0], b[1] - a[1])
    square = _dot(delta, delta)
    fraction = (
        max(0.0, min(1.0, _dot((query[0] - a[0], query[1] - a[1]), delta) / square))
        if square
        else 0.0
    )
    nearest = tuple(p + fraction * d for p, d in zip(a, delta, strict=True))
    return math.dist(query, nearest), nearest


def _arc_point(arc, fraction):
    """Point on the finite support-circle stroke, never a repaired endpoint seed."""
    if fraction == 0:
        return arc.start_mm
    start = math.atan2(arc.start_mm[1] - arc.center_mm[1], arc.start_mm[0] - arc.center_mm[0])
    angle = start + fraction * arc.sweep_radians
    return (
        arc.center_mm[0] + arc.radius_mm * math.cos(angle),
        arc.center_mm[1] + arc.radius_mm * math.sin(angle),
    )


def _curve_segments(curve, projection, error_px, limit):
    """Eight seed spans over one circle or finite arc, bounded dyadic refinement.

    Observed deviation is a sampling diagnostic, NOT a proven error bound for an
    arbitrary projector. Invisible or over-budget spans are omitted and reported.
    Arc fractions traverse only the signed sweep, including both interval ends;
    the raw observed end may differ from the support-circle stroke's end.
    Circle sampling retains its exact closed-seam evaluation and subdivision.
    """

    def project(turn):
        if type(curve) is ArcGeometry:
            return projection.at(_arc_point(curve, turn))
        angle = math.tau * (0.0 if turn == 1.0 else turn)
        local = (
            curve.center_mm[0] + curve.radius_mm * math.cos(angle),
            curve.center_mm[1] + curve.radius_mm * math.sin(angle),
        )
        return projection.at(local)

    pending = [(index / 8, (index + 1) / 8) for index in reversed(range(8))]
    segments, issues, leaves, observed = [], [], 8, 0.0
    while pending:
        start, end = pending.pop()
        try:
            values = [project(start + (end - start) * fraction / 4) for fraction in range(5)]
        except _ProjectionLimit:
            issues.append(("projection_budget", (start, end)))
            issues.extend(("projection_budget", span) for span in reversed(pending))
            break
        if any(value is None for value in values):
            issues.append(("invisible_span", (start, end)))
            continue
        a, b = values[0], values[-1]
        error = max(_nearest_segment(value, a, b)[0] for value in values[1:-1])
        if error > error_px:
            if leaves == limit:
                issues.append(("refinement_budget", (start, end)))
                continue
            leaves += 1
            midpoint = (start + end) / 2
            pending.extend(((midpoint, end), (start, midpoint)))
        else:
            observed = max(observed, error)
            segments.append((a, b))
    return segments, observed, issues


def _circle_segments(circle, projection, error_px, limit):
    """Compatibility entry for the unchanged full-circle sampling policy."""
    return _curve_segments(circle, projection, error_px, limit)


def pick_geometry(
    geometry,
    screen_xy,
    project,
    *,
    radius_px=8.0,
    kinds=("point", "line", "circle", "arc"),
    tie_tolerance_px=1e-6,
    circle_error_px=0.25,
    max_circle_segments=512,
    max_project_calls=32768,
):
    """Return bounded, deterministic screen-space selection proposals.

    Point/line picks use visible projected points/endpoint chords. The callback is
    expected to be an ordinary camera projection (straight lines stay straight).
    A line with an invisible endpoint is not extrapolated or clipped speculatively.
    Circle/finite-arc picks use sampled chords and expose observed refinement error.
    That error is only a conservative ambiguity band for this sampling policy, not
    a guarantee about an arbitrary callback between samples. Near-threshold/tied
    candidates remain ambiguous. Any unresolved span makes the result incomplete.
    No point priority, snapping, topology, automatic binding or constraint is added.
    """
    _require(type(geometry) is SketchGeometry, "Expected sketch display geometry.")
    query = _vector(screen_xy, 2, _PIXEL_BOUND)
    radius = _number(radius_px, 1024, minimum=1e-6)
    tie = _number(tie_tolerance_px, 1, minimum=0)
    error = _number(circle_error_px, min(4, radius), minimum=1e-6)
    _require(callable(project), "Expected an explicit projection callback.")
    _require(
        type(kinds) in (tuple, list)
        and len(kinds) <= 4
        and all(type(kind) is str and kind in {"point", "line", "circle", "arc"} for kind in kinds)
        and len(set(kinds)) == len(kinds),
        "Invalid pick entity kinds.",
    )
    _require(
        type(max_circle_segments) is int and 8 <= max_circle_segments <= MAX_CIRCLE_SEGMENTS,
        "Circle refinement limit exceeded.",
    )
    _require(
        type(max_project_calls) is int and 1 <= max_project_calls <= MAX_PROJECT_CALLS,
        "Projection call limit exceeded.",
    )
    projection = _Projection(geometry.plane, project, max_project_calls)
    candidates, unavailable = [], []

    def add(kind, identifier, distance, nearest, method, observed=0.0):
        if distance <= radius + observed:
            candidates.append(HitCandidate(kind, identifier, distance, nearest, method, observed))

    for kind in ("point", "line", "circle", "arc"):
        if kind not in kinds:
            continue
        for identifier, entity in getattr(geometry, kind + "s").items():
            try:
                if kind == "point":
                    point = projection.at(entity)
                    if point is not None:
                        add(kind, identifier, math.dist(query, point), point, "projected_point")
                elif kind == "line":
                    a, b = projection.at(entity.start_mm), projection.at(entity.end_mm)
                    if a is None or b is None:
                        unavailable.append(ProjectionIssue(kind, identifier, "invisible_endpoint"))
                    else:
                        add(kind, identifier, *_nearest_segment(query, a, b), "endpoint_chord")
                else:
                    segments, observed, issues = _curve_segments(
                        entity, projection, error, max_circle_segments
                    )
                    unavailable.extend(
                        ProjectionIssue(kind, identifier, reason, span) for reason, span in issues
                    )
                    if segments:
                        distance, nearest = min(_nearest_segment(query, a, b) for a, b in segments)
                        add(kind, identifier, distance, nearest, "sampled_" + kind, observed)
            except _ProjectionLimit:
                unavailable.append(ProjectionIssue(kind, identifier, "projection_budget"))
    candidates.sort(key=lambda hit: (hit.distance_px, hit.kind, hit.identifier))
    nearest = ()
    if candidates:
        best = candidates[0]
        nearest = tuple(
            hit
            for hit in candidates
            if hit.distance_px - hit.observed_error_px
            <= best.distance_px + best.observed_error_px + tie
        )
    if unavailable:
        status = "incomplete"
    elif not nearest:
        status = "miss"
    elif len(nearest) > 1 or nearest[0].distance_px + nearest[0].observed_error_px > radius:
        status = "ambiguous"
    else:
        status = "unique"
    return PickResult(status, tuple(candidates), nearest, tuple(unavailable), projection.calls)
