"""CPU picking on a supplied validated transient mesh, never model authority.

The caller must retain its guarded seed/context/fingerprint and exact target
instance-to-part mapping. This helper neither discovers targets nor validates a
replay receipt. It never reads Blender objects/tags, publishes, or invokes a
backend. Mesh vertices and pose translation are canonical millimetres; the ray
origin is in the same world-mm space. Returned triangle indices are never saved.
"""

import math
from dataclasses import dataclass, field

from .assembly_face_pick import resolve_face
from .assembly_joint_draft import transform_points
from .assembly_validation_common import MAX_TRIANGLES, MAX_VERTICES
from .bridge import BridgeError

DEFAULT_TRIANGLE_BUDGET = 24000
_MAX_COORDINATE_MM = 1e9


def _vector(value, *, bound):
    if type(value) not in (list, tuple) or len(value) != 3:
        raise BridgeError("Face picking requires three finite coordinates.")
    if any(type(v) not in (int, float) for v in value):
        raise BridgeError("Face picking requires real numeric coordinates.")
    try:
        result = tuple(float(v) for v in value)
    except (ValueError, OverflowError) as exc:
        raise BridgeError("Face picking coordinates exceed safe limits.") from exc
    if any(not math.isfinite(v) or abs(v) > bound for v in result):
        raise BridgeError("Face picking coordinates exceed safe limits.")
    return result


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def pick_surface(
    part, pose, ray_origin_mm, ray_direction, *, max_triangles=DEFAULT_TRIANGLE_BUDGET
):
    """Return nearest geometry without semantic qualification; None means miss.

    Curved/unstable faces still occlude. Compare exact candidate-instance hits
    and foreign geometry before resolving the selected target's semantic face.
    Rays are two-sided; budget overflow or degenerate triangles reject rather
    than subsampling/skipping. All inputs must still belong to the owner's
    current validated seed; this transient record is no replay authority.
    """
    if type(max_triangles) is not int or not 1 <= max_triangles <= MAX_TRIANGLES:
        raise BridgeError("Choose a bounded positive face-picking triangle budget.")
    origin = _vector(ray_origin_mm, bound=_MAX_COORDINATE_MM)
    direction = _vector(ray_direction, bound=1e100)
    length = math.hypot(*direction)
    if not length:
        raise BridgeError("Face picking requires a nonzero ray direction.")
    direction = tuple(v / length for v in direction)
    if type(part) is not dict or type(part.get("mesh")) is not dict:
        raise BridgeError("Face picking requires a validated candidate part mesh.")
    mesh = part["mesh"]
    vertices, triangles, ids = (mesh.get(k) for k in ("vertices", "triangles", "triangle_face_ids"))
    if type(vertices) not in (list, tuple) or not 0 < len(vertices) <= MAX_VERTICES:
        raise BridgeError("Candidate mesh exceeds the face-picking vertex budget.")
    if type(triangles) not in (list, tuple) or not 0 < len(triangles) <= max_triangles:
        raise BridgeError("Candidate mesh exceeds the face-picking triangle budget.")
    if type(ids) not in (list, tuple) or len(ids) != len(triangles):
        raise BridgeError("Candidate mesh has no exact triangle-to-face mapping.")
    points = [_vector(v, bound=_MAX_COORDINATE_MM) for v in vertices]
    points = [_vector(v, bound=_MAX_COORDINATE_MM) for v in transform_points(pose, points)]
    hits = []
    for index, triangle in enumerate(triangles):
        if (
            type(triangle) not in (list, tuple)
            or len(triangle) != 3
            or any(type(v) is not int or not 0 <= v < len(points) for v in triangle)
        ):
            raise BridgeError("Candidate mesh has invalid triangle indices.")
        a, b, c = (points[i] for i in triangle)
        edge1, edge2 = _sub(b, a), _sub(c, a)
        area = math.hypot(*_cross(edge1, edge2))
        if not area or area <= 1e-12 * math.hypot(*edge1) * math.hypot(*edge2):
            raise BridgeError("Candidate mesh contains a degenerate picking triangle.")
        cross = _cross(direction, edge2)
        determinant = _dot(edge1, cross)
        if abs(determinant) <= 1e-12 * area:
            continue
        offset = _sub(origin, a)
        u = _dot(offset, cross) / determinant
        q = _cross(offset, edge1)
        v = _dot(direction, q) / determinant
        if u < -1e-10 or v < -1e-10 or u + v > 1 + 1e-10:
            continue
        distance = _dot(edge2, q) / determinant
        if distance >= 0:
            hits.append((distance, index))
    if not hits:
        return None
    nearest = min(distance for distance, _ in hits)
    tolerance = distance_tolerance(nearest)
    tied = tuple(index for distance, index in hits if abs(distance - nearest) <= tolerance)
    point = tuple(o + nearest * d for o, d in zip(origin, direction, strict=True))
    return SurfaceHit(point, nearest, part, tied)


@dataclass(frozen=True)
class SurfaceHit:
    """Disposable geometric hit, paired to this exact supplied part object.

    Private indices are valid only for the still-guarded mesh. Never serialize,
    store in the model, or reuse after candidate/pose/context changes. Part
    identity checking prevents accidental cross-part resolution, not mutation
    or replay forgery: the owner must maintain its original evidence guards.
    """

    point_mm: tuple
    distance_mm: float
    _part: dict = field(repr=False, compare=False)
    _triangle_indices: tuple = field(repr=False)


def distance_tolerance(distance_mm):
    """Conservative world-mm tie band shared with caller occlusion comparisons."""
    if type(distance_mm) not in (int, float) or not math.isfinite(distance_mm) or distance_mm < 0:
        raise BridgeError("Surface comparison requires a finite nonnegative ray distance.")
    return 1e-7 + 1e-12 * distance_mm


def resolve_surface_face(part, hit):
    """Resolve only after occlusion picks this exact target, never skip blockers."""
    if type(hit) is not SurfaceHit or hit._part is not part:
        raise BridgeError("Surface hit belongs to a different transient part. Pick again.")
    faces = {resolve_face(part, index) for index in hit._triangle_indices}
    if len(faces) != 1:
        raise BridgeError("Pointer meets multiple semantic faces. Pick inside one planar face.")
    return faces.pop()


def pick_face(part, pose, ray_origin_mm, ray_direction, *, max_triangles=DEFAULT_TRIANGLE_BUDGET):
    """Single-target convenience; multi-instance owners must compare surfaces first.

    Returns semantic ``face_id``, world ``point_mm`` and ``distance_mm`` or None.
    Same-face tessellation seam ties are allowed; distinct semantic ties refuse.
    Nearest nonplanar/unstable surfaces remain blockers, never skipped.
    """
    hit = pick_surface(part, pose, ray_origin_mm, ray_direction, max_triangles=max_triangles)
    if hit is None:
        return None
    return {
        "face_id": resolve_surface_face(part, hit),
        "point_mm": hit.point_mm,
        "distance_mm": hit.distance_mm,
    }
