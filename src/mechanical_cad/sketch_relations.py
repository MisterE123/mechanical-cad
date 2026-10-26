"""Pure geometric checks for explicit sketch relations.

No solving or geometric inference is performed here. Tangency requires an
explicitly shared arc endpoint; proximity never establishes connectivity.
"""

import math

NEW_RELATIONS = frozenset(
    {"point_on_line", "midpoint", "concentric", "circle_line_tangent", "symmetry"}
)
PAIR_RELATIONS = frozenset({"parallel", "perpendicular", "equal", "tangent"}) | NEW_RELATIONS
SYMMETRIC_RELATIONS = frozenset(
    {"distance", "coincident", "parallel", "perpendicular", "equal", "concentric"}
)


def equation_count(kind):
    return (
        3
        if kind == "circle_line_tangent"
        else 2
        if kind in {"fixed", "coincident", "midpoint", "concentric", "symmetry"}
        else 1
    )


def auxiliary_scalar_count(kind):
    return 2 if kind == "circle_line_tangent" else 0


def canonical_refs(kind, refs):
    """Canonical equation order, never altering persisted authored references."""
    if kind == "symmetry":
        return tuple(sorted(refs[:2])) + tuple(refs[2:])
    return tuple(sorted(refs)) if kind in SYMMETRIC_RELATIONS else tuple(refs)


def valid_pair(kind, refs, lines, circles, arcs, points=None):
    if kind == "symmetry":
        return bool(
            len(refs) == 3
            and points is not None
            and refs[0] != refs[1]
            and all(ref in points for ref in refs[:2])
            and refs[2] in lines
            and not set(refs[:2]) & {lines[refs[2]]["start"], lines[refs[2]]["end"]}
        )
    if len(refs) != 2 or refs[0] == refs[1]:
        return False
    if kind in {"point_on_line", "midpoint"}:
        return bool(
            points is not None
            and refs[0] in points
            and refs[1] in lines
            and refs[0] not in {lines[refs[1]]["start"], lines[refs[1]]["end"]}
        )
    if kind == "concentric":
        return (
            all(ref in circles for ref in refs)
            and circles[refs[0]]["center"] != circles[refs[1]]["center"]
        )
    if kind == "circle_line_tangent":
        return refs[0] in circles and refs[1] in lines
    if kind in {"parallel", "perpendicular", "angle"}:
        return all(ref in lines for ref in refs)
    if kind == "equal":
        return all(ref in lines for ref in refs) or all(ref in circles for ref in refs)
    if kind == "tangent" and refs[0] in arcs and refs[1] in lines:
        arc, line = arcs[refs[0]], lines[refs[1]]
        return len({arc["start"], arc["end"]} & {line["start"], line["end"]}) == 1
    return False


def pair_residual(kind, refs, points, lines, circles, arcs):
    def vector(line):
        a, b = points[line["start"]], points[line["end"]]
        return b[0] - a[0], b[1] - a[1]

    if kind == "symmetry":
        p, q = (points[ref] for ref in refs[:2])
        line = lines[refs[2]]
        a, b = points[line["start"]], points[line["end"]]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length <= 1e-12:
            return math.inf
        # Both equations matter: midpoint on axis AND connector perpendicular.
        midpoint = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        on_axis = abs(dx * (midpoint[1] - a[1]) - dy * (midpoint[0] - a[0])) / length
        perpendicular = abs(dx * (q[0] - p[0]) + dy * (q[1] - p[1])) / length
        return max(on_axis, perpendicular)
    if kind == "concentric":
        return math.dist(points[circles[refs[0]]["center"]], points[circles[refs[1]]["center"]])
    if kind in {"point_on_line", "midpoint", "circle_line_tangent"}:
        line = lines[refs[1]]
        a, b = points[line["start"]], points[line["end"]]
        p = points[circles[refs[0]]["center"]] if kind == "circle_line_tangent" else points[refs[0]]
        if kind == "midpoint":
            return math.dist(p, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        length = math.dist(a, b)
        if length <= 1e-12:
            return math.inf
        distance = abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / length
        return (
            abs(distance - circles[refs[0]]["radius"])
            if kind == "circle_line_tangent"
            else distance
        )
    if kind == "equal" and refs[0] in circles:
        return abs(circles[refs[0]]["radius"] - circles[refs[1]]["radius"])
    if kind == "tangent":
        arc, line = arcs[refs[0]], lines[refs[1]]
        endpoint = next(iter({arc["start"], arc["end"]} & {line["start"], line["end"]}))
        p, center = points[endpoint], points[arc["center"]]
        a = p[0] - center[0], p[1] - center[1]
        b = vector(line)
    else:
        a, b = (vector(lines[ref]) for ref in refs)
    length_a, length_b = math.hypot(*a), math.hypot(*b)
    if kind == "equal":
        return abs(length_a - length_b)
    if min(length_a, length_b) <= 1e-12:
        return math.inf
    # Millimetres: displacement needed at the shorter vector's endpoint.
    product = a[0] * b[1] - a[1] * b[0] if kind == "parallel" else a[0] * b[0] + a[1] * b[1]
    return abs(product) / max(length_a, length_b)


def angle_residual(refs, value, points, lines):
    vectors = []
    for ref in refs:
        line = lines[ref]
        a, b = points[line["start"]], points[line["end"]]
        vectors.append((b[0] - a[0], b[1] - a[1]))
    a, b = vectors
    la, lb = math.hypot(*a), math.hypot(*b)
    if min(la, lb) <= 1e-12:
        return math.inf
    cosine = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (la * lb)))
    return abs(math.acos(cosine) - math.radians(value)) * min(la, lb)
