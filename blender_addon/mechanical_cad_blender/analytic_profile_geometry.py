"""Native-free analytic line/arc/circle region geometry.

Vendored byte-for-byte into the Blender bridge; tested for source equality.
Values are solved millimetres, identities are explicit, and ambiguous contact is
rejected. This is profile readiness, never native solid validity certification.
"""

import math

TOL = 1e-7
TAU = 2 * math.pi


def require(condition, message):
    if not condition:
        raise ValueError(message)


def xy(point):
    return (point["u"], point["v"])


def angle(center, point):
    return math.atan2(point[1] - center[1], point[0] - center[0])


def arc_contains(edge, point, *, interior=False):
    radius = math.dist(edge["start"], edge["center"])
    if abs(math.dist(point, edge["center"]) - radius) > TOL:
        return False
    extent = abs(edge["sweep"])
    if extent >= TAU - 1e-12:
        return True
    delta = (angle(edge["center"], point) - angle(edge["center"], edge["start"])) * (
        1 if edge["sweep"] > 0 else -1
    )
    delta %= TAU
    tolerance = TOL / max(radius, TOL)
    if interior:
        return tolerance < delta < extent - tolerance
    return delta <= extent + tolerance or TAU - delta <= tolerance


def arc_midpoint(edge):
    a = angle(edge["center"], edge["start"]) + edge["sweep"] / 2
    r = math.dist(edge["center"], edge["start"])
    return (edge["center"][0] + r * math.cos(a), edge["center"][1] + r * math.sin(a))


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def intersections(a, b):
    """Return contact points, or None for coincident positive-length overlap."""
    if a["kind"] == b["kind"] == "line":
        p, q = a["start"], b["start"]
        u, v = sub(a["end"], p), sub(b["end"], q)
        determinant = cross(u, v)
        if abs(determinant) <= 1e-12 * math.hypot(*u) * math.hypot(*v):
            if abs(cross(sub(q, p), u)) > TOL * math.hypot(*u):
                return []
            axis = 0 if abs(u[0]) >= abs(u[1]) else 1
            first = sorted((p[axis], a["end"][axis]))
            second = sorted((q[axis], b["end"][axis]))
            lo, hi = max(first[0], second[0]), min(first[1], second[1])
            if hi < lo - TOL:
                return []
            if hi > lo + TOL:
                return None
            return [point for point in (p, a["end"], q, b["end"]) if abs(point[axis] - lo) <= TOL]
        t, s = cross(sub(q, p), v) / determinant, cross(sub(q, p), u) / determinant
        if -TOL / math.hypot(*u) <= t <= 1 + TOL / math.hypot(*u) and -TOL / math.hypot(
            *v
        ) <= s <= 1 + TOL / math.hypot(*v):
            return [(p[0] + t * u[0], p[1] + t * u[1])]
        return []
    if b["kind"] == "line":
        a, b = b, a
    if a["kind"] == "line":
        p, u, offset = a["start"], sub(a["end"], a["start"]), sub(a["start"], b["center"])
        radius = math.dist(b["center"], b["start"])
        length2 = u[0] ** 2 + u[1] ** 2
        projection = -(offset[0] * u[0] + offset[1] * u[1]) / length2
        closest = (p[0] + projection * u[0], p[1] + projection * u[1])
        distance = math.dist(closest, b["center"])
        if distance > radius + TOL:
            return []
        half = math.sqrt(max(0, radius * radius - distance * distance) / length2)
        contacts = []
        for t in (projection - half, projection + half):
            if -TOL / math.sqrt(length2) <= t <= 1 + TOL / math.sqrt(length2):
                point = (p[0] + t * u[0], p[1] + t * u[1])
                if arc_contains(b, point):
                    contacts.append(point)
        return contacts
    ca, cb = a["center"], b["center"]
    ra, rb, d = math.dist(ca, a["start"]), math.dist(cb, b["start"]), math.dist(ca, cb)
    if d <= TOL and abs(ra - rb) <= TOL:
        if abs(a["sweep"]) >= TAU - 1e-12 or abs(b["sweep"]) >= TAU - 1e-12:
            return None
        if any(
            arc_contains(b, p, interior=True) for p in (a["start"], a["end"], arc_midpoint(a))
        ) or any(
            arc_contains(a, p, interior=True) for p in (b["start"], b["end"], arc_midpoint(b))
        ):
            return None
        return [p for p in (a["start"], a["end"]) if arc_contains(b, p)]
    if d <= TOL or d > ra + rb + TOL or d < abs(ra - rb) - TOL:
        return []
    along = (ra * ra - rb * rb + d * d) / (2 * d)
    height = math.sqrt(max(0, ra * ra - along * along))
    ux, uy = (cb[0] - ca[0]) / d, (cb[1] - ca[1]) / d
    contacts = [
        (ca[0] + along * ux + sign * height * -uy, ca[1] + along * uy + sign * height * ux)
        for sign in (-1, 1)
    ]
    return [point for point in contacts if arc_contains(a, point) and arc_contains(b, point)]


def reverse(edge):
    result = {**edge, "start": edge["end"], "end": edge["start"]}
    if edge["kind"] != "line":
        result["sweep"] = -edge["sweep"]
    return result


def area(loop):
    value = 0
    origin = loop[0]["start"]
    for edge in loop:
        value += cross(sub(edge["start"], origin), sub(edge["end"], origin))
        if edge["kind"] != "line":
            radius = math.dist(edge["center"], edge["start"])
            value += radius * radius * (edge["sweep"] - math.sin(edge["sweep"]))
    return value / 2


def inside(point, loop):
    # Rotate a ray away from every authored endpoint to avoid double counts.
    for attempt in range(64):
        theta = attempt * 0.6180339887498949
        c, s = math.cos(theta), math.sin(theta)

        def rotate(p, c=c, s=s):
            x, y = p[0] - point[0], p[1] - point[1]
            return (c * x + s * y, -s * x + c * y)

        if all(abs(rotate(edge["start"])[1]) > TOL for edge in loop):
            break
    else:
        raise ValueError("Numerically ambiguous profile containment ray.")
    count = 0
    for edge in loop:
        start, end = rotate(edge["start"]), rotate(edge["end"])
        if edge["kind"] == "line":
            if (start[1] > 0) != (end[1] > 0):
                x = start[0] - start[1] * (end[0] - start[0]) / (end[1] - start[1])
                count += x > 0
        else:
            center = rotate(edge["center"])
            radius = math.dist(edge["center"], edge["start"])
            if abs(center[1]) >= radius - TOL:
                continue  # Tangent rays do not cross the region.
            dx = math.sqrt(radius * radius - center[1] * center[1])
            rotated = {**edge, "start": start, "end": end, "center": center}
            for x in (center[0] - dx, center[0] + dx):
                if x > 0 and arc_contains(rotated, (x, 0)):
                    count += 1
    return bool(count % 2)


def classify(sketch, *, open_path=False):
    """Return ordered CCW analytic regions from a genuine solved sketch dict."""
    sketch = {
        **sketch,
        **{
            kind: [curve for curve in sketch.get(kind, []) if not curve.get("construction", False)]
            for kind in ("lines", "arcs", "circles")
        },
    }
    points = {p["id"]: xy(p) for p in sketch["points"]}
    parents = {identifier: identifier for identifier in points}

    def root(identifier):
        while parents[identifier] != identifier:
            identifier = parents[identifier]
        return identifier

    for constraint in sketch["constraints"]:
        if constraint["kind"] == "coincident":
            left, right = sorted(root(identifier) for identifier in constraint["refs"])
            parents[right] = left
    for identifier, p in points.items():
        require(math.dist(p, points[root(identifier)]) <= TOL, "Unresolved coincident endpoints.")
    edges, adjacency = {}, {}
    for kind, records in (("line", sketch["lines"]), ("arc", sketch.get("arcs", []))):
        for record in records:
            a, b = root(record["start"]), root(record["end"])
            require(a != b, "Collapsed profile boundary.")
            start, end = points[a], points[b]
            require(math.dist(start, end) >= 1e-6, "Profile boundary endpoints too close.")
            edge = {"kind": kind, "entity_id": record["id"], "start": start, "end": end}
            if kind == "arc":
                center = points[record["center"]]
                radius = math.dist(start, center)
                require(
                    1e-6 <= radius <= 1e6 and abs(radius - math.dist(end, center)) <= TOL,
                    "Arc endpoints have inconsistent radii.",
                )
                sign = 1 if record["direction"] == "ccw" else -1
                sweep = ((angle(center, end) - angle(center, start)) * sign) % TAU
                require(sweep * radius >= 1e-6, "Degenerate arc sweep.")
                edge.update(center=center, sweep=sweep * sign)
            require(record["id"] not in edges, "Duplicate boundary identity.")
            edges[record["id"]] = (a, b, edge)
            adjacency.setdefault(a, []).append(record["id"])
            adjacency.setdefault(b, []).append(record["id"])
    if open_path:
        require(not sketch.get("circles"), "Open paths cannot contain circles.")
        require(1 <= len(edges) <= 256, "Path needs 1–256 boundaries.")
        ends = sorted(point for point, items in adjacency.items() if len(items) == 1)
        require(
            len(ends) == 2 and all(len(items) <= 2 for items in adjacency.values()),
            "Path must be open and nonbranching.",
        )
        current, ordered, remaining = ends[0], [], set(edges)
        while remaining:
            candidates = [name for name in adjacency[current] if name in remaining]
            require(len(candidates) == 1, "Path must be one connected chain.")
            name = candidates[0]
            remaining.remove(name)
            a, b, edge = edges[name]
            ordered.append(edge if current == a else reverse(edge))
            current = b if current == a else a
        require(current == ends[1], "Path must end at its other endpoint.")
        for i, left in enumerate(ordered):
            for j in range(i + 1, len(ordered)):
                contacts = intersections(left, ordered[j])
                require(
                    contacts is not None
                    and all(j == i + 1 and math.dist(p, left["end"]) <= TOL for p in contacts),
                    "Path boundaries self-intersect, overlap or touch away from a shared endpoint.",
                )
        return {"boundaries": ordered, "boundary_ids": [edge["entity_id"] for edge in ordered]}
    require(
        all(len(items) == 2 for items in adjacency.values()),
        "Every line/arc boundary must close without branches.",
    )
    loops, remaining = [], set(edges)
    while remaining:
        start = min(point for name in remaining for point in edges[name][:2])
        current, loop = start, []
        while True:
            candidates = sorted(name for name in adjacency[current] if name in remaining)
            require(candidates, "Open analytic boundary.")
            name = candidates[0]
            remaining.remove(name)
            a, b, edge = edges[name]
            if current == a:
                current = b
                loop.append(edge)
            else:
                current = a
                loop.append(reverse(edge))
            if current == start:
                break
        loops.append(loop)
    for circle in sketch.get("circles", []):
        center, radius = points[circle["center"]], circle["radius"]
        require(1e-6 <= radius <= 1e6, "Invalid circle radius.")
        point = (center[0] + radius, center[1])
        loops.append(
            [
                {
                    "kind": "circle",
                    "entity_id": circle["id"],
                    "center": center,
                    "start": point,
                    "end": point,
                    "sweep": TAU,
                }
            ]
        )
    require(loops and sum(map(len, loops)) <= 256, "Profile needs 1–256 analytic boundaries.")
    ids = [edge["entity_id"] for loop in loops for edge in loop]
    require(len(set(ids)) == len(ids), "Duplicate boundary identity.")
    for index, loop in enumerate(loops):
        for i, left in enumerate(loop):
            for j in range(i + 1, len(loop)):
                right = loop[j]
                contacts = intersections(left, right)
                allowed = []
                if j == i + 1:
                    allowed.append(left["end"])
                if i == 0 and j == len(loop) - 1:
                    allowed.append(left["start"])
                require(
                    contacts is not None
                    and all(any(math.dist(p, q) <= TOL for q in allowed) for p in contacts),
                    "Analytic boundaries self-intersect or overlap.",
                )
        signed = area(loop)
        require(abs(signed) >= 1e-12, "Analytic loop has no usable area.")
        if signed < 0:
            loops[index] = [reverse(edge) for edge in reversed(loop)]
    loops.sort(key=lambda loop: tuple(sorted(edge["entity_id"] for edge in loop)))
    for i, loop in enumerate(loops):
        for other in loops[i + 1 :]:
            require(
                all(intersections(a, b) == [] for a in loop for b in other),
                "Separate boundaries cross, overlap or touch.",
            )
    containers = [
        {j for j, other in enumerate(loops) if j != i and inside(loop[0]["start"], other)}
        for i, loop in enumerate(loops)
    ]
    regions = []
    for i, loop in enumerate(loops):
        depth = len(containers[i])
        if depth % 2 == 0:
            holes = [
                other
                for j, other in enumerate(loops)
                if i in containers[j] and len(containers[j]) == depth + 1
            ]
            regions.append({"outer": loop, "holes": holes})
    return {"regions": regions, "boundary_ids": sorted(ids)}


def is_sector_form(sketch):
    """Recognize only the historical one-arc/two-radii topology, not readiness."""
    if any(
        curve.get("construction", False)
        for kind in ("lines", "arcs", "circles")
        for curve in sketch.get(kind, [])
    ):
        return False  # Certified-sector source contract predates construction geometry.
    arcs = [arc for arc in sketch.get("arcs", []) if not arc.get("construction", False)]
    lines = [line for line in sketch["lines"] if not line.get("construction", False)]
    circles = [
        circle for circle in sketch.get("circles", []) if not circle.get("construction", False)
    ]
    if len(arcs) != 1 or len(lines) != 2 or circles:
        return False
    parents = {point["id"]: point["id"] for point in sketch["points"]}

    def root(identifier):
        while parents[identifier] != identifier:
            identifier = parents[identifier]
        return identifier

    for constraint in sketch["constraints"]:
        if constraint["kind"] == "coincident":
            left, right = sorted(root(identifier) for identifier in constraint["refs"])
            parents[right] = left
    arc = arcs[0]
    expected = {
        frozenset((root(arc["center"]), root(arc[endpoint]))) for endpoint in ("start", "end")
    }
    actual = {frozenset((root(line["start"]), root(line["end"]))) for line in lines}
    return expected == actual
