"""Native-free evidence checks for line/circle regions, not a CAD kernel.

Checks the exact solved boundaries and rejects contacts rather than trusting a
backend region tag. Reuses the existing single-loop geometric checker.
"""

import math


def expected_region_kind(sketch):
    from .profile_geometry_checks import _cross, _line_connectivity, _on_segment, _require

    sketch = {
        **sketch,
        **{
            kind: [curve for curve in sketch.get(kind, []) if not curve.get("construction", False)]
            for kind in ("lines", "arcs", "circles")
        },
    }
    _require(not sketch.get("arcs"), "line/circle regions cannot contain arcs")
    points = {point["id"]: (point["u"], point["v"]) for point in sketch["points"]}
    parents = {identifier: identifier for identifier in points}

    def root(identifier):
        while parents[identifier] != identifier:
            identifier = parents[identifier]
        return identifier

    for constraint in sketch["constraints"]:
        if constraint["kind"] == "coincident":
            left, right = sorted(root(identifier) for identifier in constraint["refs"])
            parents[right] = left
    adjacency = {}
    for line in sketch["lines"]:
        a, b = root(line["start"]), root(line["end"])
        adjacency.setdefault(a, []).append((line, b))
        adjacency.setdefault(b, []).append((line, a))
    loops = []
    remaining = set(adjacency)
    while remaining:
        pending, component = [min(remaining)], set()
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(neighbor for _, neighbor in adjacency[current])
        remaining.difference_update(component)
        lines = [line for line in sketch["lines"] if root(line["start"]) in component]
        _line_connectivity({**sketch, "lines": lines}, closed=True)
        segments = [(points[root(line["start"])], points[root(line["end"])]) for line in lines]
        loops.append(("polygon", segments))
    for circle in sketch.get("circles", []):
        center, radius = points[circle["center"]], circle["radius"]
        _require(math.isfinite(radius) and 1e-6 <= radius <= 1e6, "invalid region circle radius")
        loops.append(("circle", (center, radius)))
    _require(loops, "profile requires a closed boundary")

    def segment_distance(point, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(
            0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy))
        )
        return math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy)

    def segments_intersect(a, b, c, d):
        crossing = _cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0
        return crossing or any(
            _on_segment(first, second, point)
            for first, second, point in ((a, b, c), (a, b, d), (c, d, a), (c, d, b))
        )

    def contact(left, right):
        if left[0] == right[0] == "circle":
            (a, ra), (b, rb) = left[1], right[1]
            return abs(ra - rb) - 1e-7 <= math.dist(a, b) <= ra + rb + 1e-7
        if right[0] == "circle":
            left, right = right, left
        if left[0] == "circle":
            center, radius = left[1]
            return any(
                segment_distance(center, a, b) <= radius + 1e-7
                and max(math.dist(center, a), math.dist(center, b)) >= radius - 1e-7
                for a, b in right[1]
            )
        return any(segments_intersect(a, b, c, d) for a, b in left[1] for c, d in right[1])

    for index, loop in enumerate(loops):
        for other in loops[index + 1 :]:
            _require(not contact(loop, other), "profile boundaries cross, overlap or touch")
    if len(loops) > 1:
        return "regions"
    return "circle" if loops[0][0] == "circle" else "line_loop"
