"""Original CAD glyph geometry shared by native buttons and menu previews.

24-unit, Y-up artwork. A small, code-owned vocabulary of strokes makes related
operations visibly related without reusing the same symbol for different tools.
No external resource data reaches the native shape decoder.
"""

from math import cos, hypot, pi, sin


def line(*points):
    return tuple(zip(points, points[1:], strict=False))


def arc(x, y, radius, start=0, end=360, steps=20):
    angles = [pi * (start + (end - start) * i / steps) / 180 for i in range(steps + 1)]
    return line(*[(x + radius * cos(a), y + radius * sin(a)) for a in angles])


def rect(x, y, width, height):
    return line((x, y), (x + width, y), (x + width, y + height), (x, y + height), (x, y))


def plus(x, y, size=3):
    return line((x - size, y), (x + size, y)) + line((x, y - size), (x, y + size))


def arrow(x, y, dx, dy):
    length = hypot(dx, dy)
    ux, uy = dx / length, dy / length
    return line((x, y), (x + dx, y + dy)) + line(
        (x + dx - 3 * ux - 2 * uy, y + dy - 3 * uy + 2 * ux),
        (x + dx, y + dy),
        (x + dx - 3 * ux + 2 * uy, y + dy - 3 * uy - 2 * ux),
    )


PLANE = line((3, 5), (16, 5), (21, 17), (8, 17), (3, 5))
BOX = (
    line((4, 6), (14, 3), (21, 8), (21, 18), (11, 21), (4, 16), (4, 6))
    + line((4, 16), (14, 13), (21, 18))
    + line((14, 13), (14, 3))
)
LINEAR = rect(3, 8, 4, 8) + rect(10, 8, 4, 8) + rect(17, 8, 4, 8)
RADIAL = sum((rect(x, y, 4, 4) for x, y in ((10, 17), (17, 10), (10, 3), (3, 10))), ())

# Each key represents an actual supported action, not a future asset-catalog entry.
STROKES = {
    "LINE": line((6, 6), (18, 18)) + rect(3, 3, 3, 3) + rect(18, 18, 3, 3),
    "DIMENSION": line((4, 5), (4, 19))
    + line((20, 5), (20, 19))
    + arrow(10, 12, -6, 0)
    + arrow(14, 12, 6, 0),
    "ARC": arc(12, 11, 8, 20, 160) + line((12, 11), (12, 13)),
    "REVERSE": arc(12, 12, 8, 35, 315) + line((14, 4), (18, 6), (18, 2)),
    "USE_POINT": plus(12, 12, 7) + rect(10, 10, 4, 4),
    "EXTEND": line((3, 12), (11, 12)) + arrow(13, 12, 8, 0) + line((16, 5), (16, 19)),
    "SKETCH_CHECK": arc(10, 14, 6) + line((14, 9), (21, 2)) + line((7, 14), (9, 12), (13, 16)),
    "CANCEL_CHECK": arc(10, 14, 6)
    + line((14, 9), (21, 2))
    + line((8, 12), (12, 16))
    + line((8, 16), (12, 12)),
    "VERTICAL": line((12, 4), (12, 20)) + line((9, 4), (15, 4)) + line((9, 20), (15, 20)),
    "PARALLEL": line((5, 4), (11, 20)) + line((13, 4), (19, 20)),
    "EQUAL": line((5, 8), (19, 8)) + line((5, 16), (19, 16)),
    "POINT_ON_LINE": line((3, 5), (21, 19)) + rect(10, 10, 4, 4),
    "MIDPOINT": line((3, 12), (21, 12))
    + line((3, 8), (3, 16))
    + line((21, 8), (21, 16))
    + rect(10, 10, 4, 4),
    "COINCIDENT": arrow(2, 12, 7, 0) + arrow(22, 12, -7, 0) + rect(10, 10, 4, 4),
    "TANGENT": line((3, 5), (21, 5)) + arc(12, 13, 8, 180, 360),
    "CIRCLE_TANGENT": line((3, 4), (21, 4)) + arc(12, 12, 8),
    "CONCENTRIC": arc(12, 12, 8) + arc(12, 12, 4),
    "DIAMETER": arc(12, 12, 8) + arrow(12, 12, 6, 6) + arrow(12, 12, -6, -6),
    "NEW_FACE_SKETCH": PLANE + plus(18, 19, 3),
    "FACE_RECTANGLE": PLANE + rect(9, 8, 6, 6),
    "FACE_CIRCLE": PLANE + arc(12, 11, 3),
    "FILLET": line((4, 3), (4, 12)) + arc(13, 12, 9, 90, 180) + line((13, 21), (21, 21)),
    "CHAMFER": line((4, 3), (4, 12), (13, 21), (21, 21)),
    "UNION": line((3, 3), (14, 3), (14, 9), (21, 9), (21, 21), (9, 21), (9, 15), (3, 15), (3, 3)),
    "CUT": line((3, 3), (18, 3), (18, 10), (10, 10), (10, 21), (3, 21), (3, 3))
    + line((14, 17), (22, 17)),
    "INTERSECTION": rect(3, 3, 12, 12)
    + rect(9, 9, 12, 12)
    + line((9, 9), (15, 15))
    + line((9, 15), (15, 9)),
    "LINEAR_PATTERN": LINEAR,
    "CIRCULAR_PATTERN": RADIAL,
    "LINEAR_CUT_PATTERN": LINEAR
    + line((4, 12), (6, 12))
    + line((11, 12), (13, 12))
    + line((18, 12), (20, 12)),
    "CIRCULAR_CUT_PATTERN": RADIAL
    + line((11, 19), (13, 19))
    + line((18, 12), (20, 12))
    + line((11, 5), (13, 5))
    + line((4, 12), (6, 12)),
    # Different-sized section loops joined by rails: Loft changes section.
    "LOFT": line((3, 5), (12, 2), (21, 5), (12, 8), (3, 5))
    + line((7, 19), (12, 17), (17, 19), (12, 21), (7, 19))
    + line((3, 5), (7, 19))
    + line((21, 5), (17, 19)),
    # Constant-width elbow and end section: Sweep follows a bent path.
    "SWEEP": line((3, 3), (3, 11))
    + arc(13, 11, 10, 90, 180, 10)
    + line((13, 21), (21, 21), (21, 15), (13, 15))
    + arc(13, 11, 4, 90, 180, 8)
    + line((9, 11), (9, 3))
    + line((3, 3), (6, 2), (9, 3), (6, 5), (3, 3)),
    # Section through a stepped bore. Broad shoulders communicate counterbore;
    # the open narrow channel continues through the bottom (not a blind pocket).
    "HOLE": line((2, 3), (2, 19), (7, 19), (7, 13), (10, 13), (10, 3), (2, 3))
    + line((22, 3), (22, 19), (17, 19), (17, 13), (14, 13), (14, 3), (22, 3)),
    # Open-top cutaway, with separated inside/outside walls and a solid floor.
    "SHELL": line((3, 21), (3, 3), (21, 3), (21, 21), (17, 21), (17, 7), (7, 7), (7, 21), (3, 21)),
    "PROJECT": line((3, 6), (15, 6))
    + line((7, 19), (19, 19))
    + arrow(11, 16, -3, -7)
    + arrow(18, 16, -3, -7),
    "USE_SOLID_EDGE": BOX + arrow(3, 2, 6, 3),
    "APPLY_LINE_EDIT": line((3, 18), (15, 18)) + line((8, 8), (12, 4), (21, 13)),
    "CANCEL_LINE_EDIT": line((3, 18), (15, 18)) + line((11, 4), (21, 14)) + line((11, 14), (21, 4)),
}
ALIASES = {
    "FILLET_ADVANCED": "FILLET",
    "FILLET_FACES": "FILLET",
    "CHAMFER_ADVANCED": "CHAMFER",
    "CHAMFER_FACES": "CHAMFER",
    "SHELL_ADVANCED": "SHELL",
    "FACE_SKETCH_ADVANCED": "NEW_FACE_SKETCH",
}


def polygons(action):
    """Return stroke quads; use both for native shapes and offline PNG rendering."""
    strokes = STROKES.get(ALIASES.get(action, action), ())
    result = []
    for (x1, y1), (x2, y2) in strokes:
        length = hypot(x2 - x1, y2 - y1)
        if length < 0.001:
            continue
        nx, ny = -(y2 - y1) * 0.75 / length, (x2 - x1) * 0.75 / length
        result.append(
            ((x1 - nx, y1 - ny), (x2 - nx, y2 - ny), (x2 + nx, y2 + ny), (x1 + nx, y1 + ny))
        )
    return tuple(result)


def shape(action):
    """Encode code-owned convex quads using Blender's repeated-final sentinel."""
    data = bytearray()
    for polygon in polygons(action):
        # Native button shapes occupy the entire hit target, unlike built-in
        # icons. Inset artwork, not the gizmo, to retain the full 34px target
        # and match the visual weight of the surrounding native symbols.
        points = [
            (round(127.5 + (x - 12) * 255 / 24 * 0.72), round(127.5 + (y - 12) * 255 / 24 * 0.72))
            for x, y in polygon
        ]
        if any(not 0 <= value <= 255 for point in points for value in point):
            raise ValueError("CAD glyph lies outside its design grid")
        data.extend(value for point in (*points, points[-1]) for value in point)
    return bytes(data) if data else None
