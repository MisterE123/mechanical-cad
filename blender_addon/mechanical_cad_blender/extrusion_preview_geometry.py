"""Disposable outlines from a validated mesh, never persistent face identity."""


import math


def boundary_edges(mesh):
    """Suppress same-face tessellation diagonals; retain boundaries and seams.

    Vertex/triangle/face indices are used only within this one preview mesh.
    OCCT generally duplicates boundary vertices per face. Shared-index meshes
    are also supported: an edge separating two surface IDs remains visible.
    Unknown surface IDs cannot establish a same-face diagonal, so keep them.
    """
    edges = {}
    for triangle, face in zip(mesh["triangles"], mesh["triangle_face_ids"], strict=True):
        a, b, c = triangle
        for u, v in ((a, b), (b, c), (c, a)):
            key = tuple(sorted((u, v)))
            edges.setdefault(key, []).append(face)
    return [
        key
        for key, faces in edges.items()
        if len(faces) != 2 or faces[0] is None or faces[0] != faces[1]
    ]


# View-only limits: refuse unstable extremes rather than moving the user's view.
_MAX_COORDINATE = 1e12
_MIN_EXTENT = 1e-9


def _point(value):
    try:
        if len(value) != 3:
            raise ValueError("Preview points require three coordinates")
        if any(type(component) not in {int, float} for component in value):
            raise ValueError("Preview coordinates must be real numbers")
        point = tuple(float(component) for component in value)
    except (TypeError, OverflowError) as exc:
        raise ValueError("Invalid preview coordinates") from exc
    if any(not math.isfinite(component) or abs(component) > _MAX_COORDINATE for component in point):
        raise ValueError("Preview coordinates exceed safe view limits")
    return point


def preview_bounds(vertices):
    """Compute finite disposable bounds once, after preview evidence is accepted.

    A plane or line has usable bounds; a point or numerically tiny extent does
    not. These bounds are framing hints, never geometry or publication evidence.
    """
    low = high = None
    try:
        for vertex in vertices:
            point = _point(vertex)
            low = point if low is None else tuple(min(a, b) for a, b in zip(low, point, strict=True))
            high = point if high is None else tuple(max(a, b) for a, b in zip(high, point, strict=True))
    except TypeError as exc:
        raise ValueError("Preview vertices must be iterable") from exc
    if low is None:
        raise ValueError("Cannot focus an empty preview")
    diagonal = math.dist(low, high)
    if not _MIN_EXTENT < diagonal <= _MAX_COORDINATE:
        raise ValueError("Preview extent exceeds safe view limits")
    return low, high


def focus_parameters(bounds, lens, aspect, perspective):
    """Return view center/distance without accessing Blender or mutating a scene.

    Enclose the bounds in a sphere with 25 percent breathing room. A conservative
    32 mm view sensor and narrower-axis factor avoid clipping in wide/tall
    regions. Orthographic distance uses the same lens-dependent view scale;
    perspective also accounts for the sphere's depth. Camera views are excluded.
    """
    if type(perspective) is not str or perspective not in {"PERSP", "ORTHO"}:
        raise ValueError("Focus requires a perspective or orthographic user view")
    try:
        if len(bounds) != 2:
            raise ValueError("Invalid preview bounds")
        low, high = (_point(point) for point in bounds)
    except TypeError as exc:
        raise ValueError("Invalid preview bounds") from exc
    if any(a > b for a, b in zip(low, high, strict=True)):
        raise ValueError("Preview bounds are reversed")
    preview_bounds((low, high))
    if (
        type(lens) not in {int, float} or type(aspect) not in {int, float}
        or not 1 <= lens <= 250 or not 0.05 <= aspect <= 20
    ):
        raise ValueError("View lens or aspect exceeds safe limits")
    center = tuple(a + (b - a) / 2 for a, b in zip(low, high, strict=True))
    radius = math.dist(low, high) / 2
    tangent = 16 * min(1, aspect, 1 / aspect) / lens
    divisor = math.sin(math.atan(tangent)) if perspective == "PERSP" else tangent
    distance = 1.25 * radius / divisor
    if not math.isfinite(distance) or not _MIN_EXTENT < distance <= _MAX_COORDINATE:
        raise ValueError("Focus distance exceeds safe view limits")
    return center, distance
