"""Shared native-free profile checks; no protocol or bridge dependencies."""

import math


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def profile_geometry(sketch):
    """Construction participates in solving but never contributes a profile boundary."""
    return {
        **sketch,
        **{
            name: [curve for curve in sketch.get(name, []) if not curve.get("construction", False)]
            for name in ("lines", "circles", "arcs")
        },
    }


def _line_connectivity(sketch, *, closed):
    """Verify the claimed graph type using identities/coincidence, never proximity."""
    original = sketch
    sketch = profile_geometry(sketch)
    if not closed and not any(sketch[name] for name in ("lines", "circles", "arcs")):
        _require(
            any(
                curve.get("construction", False)
                for name in ("lines", "circles", "arcs")
                for curve in original.get(name, [])
            ),
            "An empty sketch does not establish an open chain.",
        )
        return
    points = {p["id"]: (p["u"], p["v"]) for p in sketch["points"]}
    parents = {identifier: identifier for identifier in points}

    def root(identifier):
        while parents[identifier] != identifier:
            identifier = parents[identifier]
        return identifier

    for constraint in sketch["constraints"]:
        if constraint["kind"] == "coincident":
            left, right = sorted(root(identifier) for identifier in constraint["refs"])
            parents[right] = left
    for identifier in points:
        _require(
            math.dist(points[identifier], points[root(identifier)]) <= 1e-7,
            "coincident point group exceeds the profile tolerance",
        )
    adjacency = {}
    for line in sketch["lines"]:
        a, b = root(line["start"]), root(line["end"])
        _require(
            a != b and math.dist(points[a], points[b]) >= 1e-6,
            "profile contains a collapsed or too-short line",
        )
        adjacency.setdefault(a, []).append((line["id"], b))
        adjacency.setdefault(b, []).append((line["id"], a))
    _require(
        adjacency and all(len(neighbors) <= 2 for neighbors in adjacency.values()),
        "profile contains missing or branched linework",
    )
    ends = sum(len(neighbors) == 1 for neighbors in adjacency.values())
    _require(ends == (0 if closed else 2), "profile availability contradicts line connectivity")
    if closed:
        _require(len(sketch["lines"]) >= 3, "a line loop requires at least three edges")
    visited, pending = set(), [next(iter(adjacency))]
    while pending:
        point = pending.pop()
        if point not in visited:
            visited.add(point)
            pending.extend(neighbor for _, neighbor in adjacency[point])
    _require(len(visited) == len(adjacency), "profile contains disconnected line regions")
    start = min(adjacency) if closed else min(p for p in adjacency if len(adjacency[p]) == 1)
    current, used, vertices = start, set(), [points[start]]
    while len(used) < len(sketch["lines"]):
        available = sorted(
            (line, neighbor) for line, neighbor in adjacency[current] if line not in used
        )
        _require(available, "incomplete profile traversal")
        line, current = available[0]
        used.add(line)
        vertices.append(points[current])
    if closed:
        _require(current == start, "line loop does not close")
    _line_geometry(vertices, closed=closed)


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, p):
    return abs(_cross(a, b, p)) <= 1e-7 * math.dist(a, b) and all(
        min(a[axis], b[axis]) - 1e-7 <= p[axis] <= max(a[axis], b[axis]) + 1e-7 for axis in (0, 1)
    )


def _line_geometry(vertices, *, closed):
    """Reject a forged ready/open classification of crossed or collapsed linework."""
    count = len(vertices) - 1
    for index, (a, b) in enumerate(zip(vertices, vertices[1:], strict=False)):
        c = (
            vertices[(index + 2) % count]
            if closed
            else (vertices[index + 2] if index + 2 < len(vertices) else None)
        )
        if c is not None:
            overlap = (
                abs(_cross(a, b, c)) <= 1e-7 * max(math.dist(a, b), math.dist(b, c))
                and (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1]) > 0
            )
            _require(not overlap, "adjacent profile boundaries overlap")
        for other in range(index + 2, count):
            if closed and index == 0 and other == count - 1:
                continue
            c, d = vertices[other], vertices[other + 1]
            crossing = (
                _cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0
            )
            touching = any(
                _on_segment(first, second, point)
                for first, second, point in ((a, b, c), (a, b, d), (c, d, a), (c, d, b))
            )
            _require(not (crossing or touching), "nonadjacent profile boundaries cross or touch")
    if closed:
        area_twice = sum(
            _cross(vertices[0], vertices[index], vertices[index + 1])
            for index in range(1, count - 1)
        )
        _require(abs(area_twice) >= 2e-12, "closed profile has no usable area")
