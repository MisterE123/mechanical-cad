"""Pure associative construction projection, shared with independent clients."""

import math
import re
from copy import deepcopy


def projection_groups(projections):
    """Explicit source-port groups; absent port retains legacy external meaning."""
    groups = {}
    for row in projections:
        groups.setdefault(row.get("input", "external"), []).append(
            {key: value for key, value in row.items() if key != "input"}
        )
    return groups


def projection_input_types(projections):
    return {
        port: "solid" if is_solid_projection(rows) else "profile"
        for port, rows in projection_groups(projections).items()
    }


def extended_projections(projections):
    return any("input" in row for row in projections)


def has_solid_projections(projections):
    return any("faces" in row for row in projections)


def validate_projection_ownership(sketch, projections):
    entities = {e["id"]: e for key in ("lines", "circles", "arcs") for e in sketch.get(key, [])}
    used = set()
    for row in projections:
        entity = entities.get(row["target"])
        if entity is None or not entity.get("construction"):
            raise ValueError("Projected target must remain an explicit construction entity.")
        points = {entity[k] for k in ("start", "end", "center") if k in entity}
        if used & points:
            raise ValueError(
                "Projected entities must have independent managed points across sources."
            )
        used.update(points)


def validate_projection_sources(document):
    features = document["features"]
    positions = {f["id"]: i for i, f in enumerate(features)}
    for feature in features:
        rows = feature.get("projections", [])
        if extended_projections(rows):
            sources = [feature["inputs"][p] for p in projection_input_types(rows)]
            if len(set(sources)) != len(sources) or any(
                s not in positions or positions[s] >= positions[feature["id"]] for s in sources
            ):
                raise ValueError("Projection sources must be distinct earlier features.")


def is_solid_projection(projections):
    """Disjoint explicit row variants, never inferred from failed source lookup."""
    return bool(projections) and hasattr(projections[0], "keys") and "faces" in projections[0]


def validate_projections(projections):
    if not isinstance(projections, (list, tuple)) or not 1 <= len(projections) <= 64:
        raise ValueError("Projection requires 1 to 64 source/target references.")
    if any(type(row) is not dict for row in projections):
        raise ValueError("Projection references must be explicit objects.")
    if extended_projections(projections):
        for row in projections:
            port = row.get("input", "external")
            if type(port) is not str or not re.fullmatch(
                r"external(?:_[2-9][0-9]*|_1[0-9]+)?", port
            ):
                raise ValueError(
                    "Projection input must be external or a stable numbered external port."
                )
        targets = [row.get("target") for row in projections]
        if len(set(targets)) != len(targets):
            raise ValueError("A construction entity may have only one projection source.")
        for rows in projection_groups(projections).values():
            validate_projections(rows)
        return
    solid = is_solid_projection(projections)
    targets = set()
    for row in projections:
        if type(row) is not dict or set(row) - {"reverse"} != (
            (
                {"kind", "faces", "target"}
                if row.get("kind") == "circle"
                else {"kind", "faces", "endpoint_faces", "target"}
                if row.get("kind") == "arc"
                else {"faces", "endpoint_faces", "target"}
            )
            if solid
            else {"source", "target"}
        ):
            raise ValueError(
                "Use one explicit projection source kind: sketch entities or solid face pairs."
            )
        if "reverse" in row and type(row["reverse"]) is not bool:
            raise ValueError("Projection endpoint reversal must be an explicit boolean.")
        if row.get("kind") == "circle" and "reverse" in row:
            raise ValueError("Circular references do not have endpoint orientation.")
        values = (row["target"],) if solid else (row["source"], row["target"])
        for value in values:
            if type(value) is not str or not re.fullmatch(
                r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", value
            ):
                raise ValueError("Projection entities require stable authored identifiers.")
        if solid:
            faces = row["faces"]
            if (
                not isinstance(faces, (list, tuple))
                or len(faces) != 2
                or any(
                    type(f) is not str
                    or not 0 < len(f) <= 512
                    or f.startswith(("snapshot:", "pending:"))
                    for f in faces
                )
                or list(faces) != sorted(set(faces))
            ):
                raise ValueError("Solid projection requires two distinct sorted stable face IDs.")
            if row.get("kind") != "circle":
                validate_endpoint_faces(row["endpoint_faces"], faces)
        if row["target"] in targets:
            raise ValueError("A construction entity may have only one projection source.")
        targets.add(row["target"])


def validate_endpoint_faces(signatures, edge_faces):
    if not isinstance(signatures, (list, tuple)) or len(signatures) != 2:
        raise ValueError("Projected endpoints require two explicit incident-face signatures.")
    for signature in signatures:
        if (
            not isinstance(signature, (list, tuple))
            or not 1 <= len(signature) <= 32
            or any(
                type(f) is not str
                or not 0 < len(f) <= 512
                or f in edge_faces
                or f.startswith(("snapshot:", "pending:"))
                for f in signature
            )
            or list(signature) != sorted(set(signature))
        ):
            raise ValueError("Endpoint signatures require distinct stable incident faces.")
    if tuple(signatures[0]) >= tuple(signatures[1]):
        raise ValueError("Endpoint signatures must be unique and canonically ordered.")


def validate_circle(circle):
    if type(circle) is not dict or set(circle) != {"center", "normal", "radius"}:
        raise ValueError("Invalid analytic circular-edge evidence.")
    for key in ("center", "normal"):
        value = circle[key]
        if (
            type(value) is not list
            or len(value) != 3
            or any(
                type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e9 for v in value
            )
        ):
            raise ValueError("Circle requires finite exact center and normal.")
    if abs(math.sqrt(sum(v * v for v in circle["normal"])) - 1) > 1e-9:
        raise ValueError("Circle normal must have unit length.")
    radius = circle["radius"]
    if type(radius) not in (int, float) or not math.isfinite(radius) or not 1e-6 <= radius <= 1e6:
        raise ValueError("Circle radius is outside the supported domain.")
    return circle


def validate_arc(edge):
    """Exact directed circular interval; endpoint identity is checked separately."""
    validate_circle({key: edge[key] for key in ("center", "normal", "radius")})
    sweep = edge["sweep"]
    if (type(sweep) not in (int, float) or not math.isfinite(sweep)
            or not 1e-9 < abs(sweep) < 2 * math.pi - 1e-9):
        raise ValueError("Arc needs a finite nonzero partial signed sweep.")
    center, normal, radius = edge["center"], edge["normal"], edge["radius"]
    vectors = [[p[i] - center[i] for i in range(3)] for p in edge["points"]]
    for vector in vectors:
        if (not math.isclose(math.sqrt(sum(v*v for v in vector)), radius,
                             rel_tol=1e-9, abs_tol=1e-6)
                or abs(sum(a*b for a,b in zip(vector, normal, strict=True))) > 1e-6):
            raise ValueError("Arc endpoints do not lie on its exact circle.")
    a, b = vectors
    cross = [normal[1]*a[2]-normal[2]*a[1], normal[2]*a[0]-normal[0]*a[2],
             normal[0]*a[1]-normal[1]*a[0]]
    rotated = [a[i]*math.cos(sweep)+cross[i]*math.sin(sweep) for i in range(3)]
    if math.dist(rotated, b) > max(1e-6, radius * 1e-9):
        raise ValueError("Arc sweep does not connect its ordered endpoints.")
    return edge


def _validate_edge_surfaces(edge, topology):
    """Check exact analytic incidence against the bound source's own face rows.

    Not a second kernel: nonanalytic surfaces retain the existing native receipt
    trust boundary. A cylinder centroid is never substituted for its axis origin.
    """

    def vector(value):
        if (
            type(value) is not list
            or len(value) != 3
            or any(
                type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e12 for v in value
            )
        ):
            raise ValueError(
                "Bound source analytic evidence needs finite three-dimensional vectors."
            )
        return value

    by_id = {row["id"]: row["signature"] for row in topology}
    circular = edge.get("kind") == "circle"
    points = [edge["center"]] if circular else edge["points"]
    incidence = [(face, points) for face in edge["faces"]]
    if not circular:
        incidence.extend(
            (face, [point])
            for point, faces in zip(edge["points"], edge["endpoint_faces"], strict=True)
            for face in faces
        )
    for face, points in incidence:
        signature = by_id[face]
        surface = signature["surface"]
        if surface == "plane":
            normal, origin = vector(signature["normal"]), vector(signature["centroid"])
            for point in points:
                if (
                    abs(sum((p - o) * n for p, o, n in zip(point, origin, normal, strict=True)))
                    > 1e-6
                ):
                    raise ValueError("Projected edge lies outside its bound source plane.")
            if (
                circular
                and abs(abs(sum(a * b for a, b in zip(edge["normal"], normal, strict=True))) - 1)
                > 1e-7
            ):
                raise ValueError("Projected circle differs from its bound source plane.")
        elif surface == "cylinder" and "axis_origin" in signature:
            axis, origin = vector(signature["axis"]), vector(signature["axis_origin"])
            if (
                type(signature["radius"]) not in (int, float)
                or not math.isfinite(signature["radius"])
                or signature["radius"] <= 0
            ):
                raise ValueError("Bound source cylinder radius must be finite and positive.")
            for point in points:
                delta = [p - o for p, o in zip(point, origin, strict=True)]
                along = sum(a * d for a, d in zip(axis, delta, strict=True))
                radial = math.sqrt(
                    sum((d - along * a) ** 2 for d, a in zip(delta, axis, strict=True))
                )
                expected = 0 if circular else signature["radius"]
                if not math.isclose(radial, expected, abs_tol=1e-6, rel_tol=1e-9):
                    raise ValueError("Projected edge differs from its bound source cylinder.")
            if circular and (
                not math.isclose(edge["radius"], signature["radius"], abs_tol=1e-6, rel_tol=1e-9)
                or abs(abs(sum(a * b for a, b in zip(edge["normal"], axis, strict=True))) - 1)
                > 1e-7
            ):
                raise ValueError("Projected circle differs from its bound source cylinder.")


def validate_solid_edges(edges, projections, topology=None):
    """Check source-bound native line/circle evidence, not tessellation guesses."""
    validate_projections(projections)
    if not is_solid_projection(projections):
        raise ValueError("Expected solid-edge projection references.")
    if type(edges) is not list or len(edges) != len({tuple(r["faces"]) for r in projections}):
        raise ValueError("Missing or duplicate projected edge evidence.")
    expected = {tuple(r["faces"]) for r in projections}
    seen = set()
    stable = (
        None
        if topology is None
        else {row["id"] for row in topology if row["provenance"]["semantic_status"] == "stable"}
    )
    if topology is not None:
        ids = [row["id"] for row in topology]
        relevant = {face for row in projections for face in row["faces"]}
        relevant.update(face for row in projections for group in row.get("endpoint_faces", []) for face in group)
        if any(ids.count(face) != 1 for face in relevant):
            raise ValueError("Projected source identity is missing or aliased.")
    for edge in edges:
        arc = type(edge) is dict and edge.get("kind") == "arc"
        circular = type(edge) is dict and edge.get("kind") == "circle"
        keys = (
            {"kind", "faces", "center", "normal", "radius"}
            if circular
            else {"kind", "faces", "endpoint_faces", "points", "center", "normal", "radius", "sweep"}
            if arc else {"faces", "endpoint_faces", "points"}
        )
        if type(edge) is not dict or set(edge) != keys:
            raise ValueError("Invalid native analytic edge evidence.")
        faces = edge["faces"]
        if type(faces) is not list or tuple(faces) not in expected or tuple(faces) in seen:
            raise ValueError("Projected edge evidence differs from authored face pair.")
        seen.add(tuple(faces))
        authored = [row for row in projections if tuple(row["faces"]) == tuple(faces)]
        if any(row.get("kind", "line") != edge.get("kind", "line") for row in authored):
            raise ValueError("Projected edge analytic kind changed; repair the reference.")
        if stable is not None and not all(face in stable for face in faces):
            raise ValueError("Projected edge face is missing, split or ambiguous.")
        if circular:
            validate_circle({key: edge[key] for key in ("center", "normal", "radius")})
            if topology is not None:
                _validate_edge_surfaces(edge, topology)
            continue
        signatures = edge["endpoint_faces"]
        validate_endpoint_faces(signatures, faces)
        if any([list(v) for v in row["endpoint_faces"]] != signatures for row in authored):
            raise ValueError("Projected endpoint identity changed; repair the reference.")
        if stable is not None and not all(f in stable for group in signatures for f in group):
            raise ValueError("Projected endpoint face is missing, split or ambiguous.")
        points = edge["points"]
        if (
            type(points) is not list
            or len(points) != 2
            or any(
                type(p) is not list
                or len(p) != 3
                or any(
                    type(v) not in (float, int) or not math.isfinite(v) or abs(v) > 1e9 for v in p
                )
                for p in points
            )
            or math.dist(*points) < 1e-6
        ):
            raise ValueError("Projected edge must have two finite distinct native endpoints.")
        if arc:
            validate_arc(edge)
        if topology is not None:
            _validate_edge_surfaces(edge, topology)
            if arc:
                _validate_edge_surfaces({"kind": "circle", "faces": faces,
                    **{k: edge[k] for k in ("center", "normal", "radius")}}, topology)
    return edges


def project_solid_edges(target_sketch, edges, projections):
    validate_solid_edges(edges, projections)
    result = deepcopy(target_sketch)
    plane = result["plane"]
    inverse = [plane["quaternion"][0], *(-v for v in plane["quaternion"][1:])]
    points = {p["id"]: p for p in result["points"]}
    lines = {line["id"]: line for line in result["lines"]}
    circles = {circle["id"]: circle for circle in result["circles"]}
    arcs = {arc["id"]: arc for arc in result.get("arcs", [])}
    by_faces = {tuple(edge["faces"]): edge for edge in edges}
    used = set()
    for row in projections:
        edge = by_faces[tuple(row["faces"])]
        if row.get("kind") == "circle":
            circle = circles.get(row["target"])
            if circle is None or not circle.get("construction", False):
                raise ValueError("Circular edge target must remain a construction circle.")
            normal = _rotate(inverse, edge["normal"])
            if math.hypot(normal[0], normal[1]) > 1e-9:
                raise ValueError(
                    "Circular edge projection requires parallel planes, not an ellipse."
                )
            coordinate = _rotate(
                inverse, [edge["center"][i] - plane["origin"][i] for i in range(3)]
            )[:2]
            identifier = circle["center"]
            fixed = [
                c
                for c in result["constraints"]
                if c["kind"] == "fixed" and c["refs"] == [identifier]
            ]
            radii = [
                c
                for c in result["constraints"]
                if c["kind"] == "radius" and c["refs"] == [circle["id"]]
            ]
            if identifier in used or identifier not in points or len(fixed) != 1 or len(radii) != 1:
                raise ValueError(
                    "Projected circle needs independent managed center and radius constraints."
                )
            if any(not math.isfinite(v) or abs(v) > 1e6 for v in coordinate):
                raise ValueError("Projected circle center exceeds sketch coordinate bounds.")
            used.add(identifier)
            points[identifier]["u"], points[identifier]["v"] = coordinate
            fixed[0]["target"] = list(coordinate)
            circle["radius"] = radii[0]["value"] = edge["radius"]
            continue
        if row.get("kind") == "arc":
            arc = arcs.get(row["target"])
            if arc is None or not arc.get("construction") or "fillet_intent" in arc:
                raise ValueError("Arc target must remain an independent construction arc.")
            normal = _rotate(inverse, edge["normal"])
            if math.hypot(normal[0], normal[1]) > 1e-9:
                raise ValueError("Arc projection requires parallel planes, not an ellipse.")
            source_points = [edge["center"], *edge["points"]]
            sweep = edge["sweep"] * normal[2]
            if row.get("reverse", False):
                source_points[1:] = reversed(source_points[1:])
                sweep = -sweep
            arc["direction"] = "ccw" if sweep > 0 else "cw"
            for role, source_point in zip(("center", "start", "end"), source_points, strict=True):
                identifier = arc[role]
                coordinate = _rotate(inverse, [source_point[i]-plane["origin"][i] for i in range(3)])[:2]
                fixed = [c for c in result["constraints"]
                         if c["kind"] == "fixed" and c["refs"] == [identifier]]
                if (identifier in used or identifier not in points or len(fixed) != 1
                        or any(not math.isfinite(v) or abs(v)>1e6 for v in coordinate)):
                    raise ValueError("Projected arc requires independent bounded fixed anchors.")
                used.add(identifier)
                points[identifier]["u"], points[identifier]["v"] = coordinate
                fixed[0]["target"] = list(coordinate)
            continue
        line = lines.get(row["target"])
        if line is None or not line.get("construction", False):
            raise ValueError("Solid edge target must remain a construction line.")
        uv = [
            _rotate(inverse, [p[i] - plane["origin"][i] for i in range(3)])[:2]
            for p in by_faces[tuple(row["faces"])]["points"]
        ]
        if (
            any(not math.isfinite(v) or abs(v) > 1e6 for p in uv for v in p)
            or math.dist(*uv) < 1e-6
        ):
            raise ValueError(
                "Solid edge collapses in projection or exceeds sketch coordinate bounds."
            )
        if row.get("reverse", False):
            uv.reverse()
        for identifier, coordinate in zip((line["start"], line["end"]), uv, strict=True):
            if identifier in used:
                raise ValueError("Projected lines require independent managed endpoint identities.")
            used.add(identifier)
            fixed = [
                c
                for c in result["constraints"]
                if c["kind"] == "fixed" and c["refs"] == [identifier]
            ]
            if identifier not in points or len(fixed) != 1:
                raise ValueError(
                    "Projected endpoints require exactly one managed fixed constraint."
                )
            points[identifier]["u"], points[identifier]["v"] = coordinate
            fixed[0]["target"] = list(coordinate)
    return result


def _rotate(q, p):
    w, x, y, z = q
    a, b, c = p
    return (
        (1 - 2 * (y * y + z * z)) * a + 2 * (x * y - w * z) * b + 2 * (x * z + w * y) * c,
        2 * (x * y + w * z) * a + (1 - 2 * (x * x + z * z)) * b + 2 * (y * z - w * x) * c,
        2 * (x * z - w * y) * a + 2 * (y * z + w * x) * b + (1 - 2 * (x * x + y * y)) * c,
    )


def project_sketch(target_sketch, source_solved, projections):
    """Replace managed seeds/driving constraints, never mutate authored arguments.

    Inputs are already structurally validated canonical/solved sketch dictionaries.
    Projection target geometry remains ordinary construction geometry for relations.
    """
    validate_projections(projections)
    result = deepcopy(target_sketch)
    source_points = {p["id"]: p for p in source_solved["points"]}
    target_points = {p["id"]: p for p in result["points"]}
    sp, tp = source_solved["plane"], result["plane"]
    inverse = [tp["quaternion"][0], *(-v for v in tp["quaternion"][1:])]
    used = set()

    def point(identifier):
        p = source_points[identifier]
        rotated = _rotate(sp["quaternion"], (p["u"], p["v"], 0))
        world = [rotated[i] + sp["origin"][i] - tp["origin"][i] for i in range(3)]
        uv = _rotate(inverse, world)[:2]
        if any(not math.isfinite(v) or abs(v) > 1e6 for v in uv):
            raise ValueError("Projected point is outside the supported coordinate domain.")
        return uv

    def fix(identifier, uv):
        if identifier in used:
            raise ValueError("Projected entities must have independent managed points.")
        used.add(identifier)
        p = target_points[identifier]
        p["u"], p["v"] = uv
        constraints = [
            c for c in result["constraints"] if c["kind"] == "fixed" and c["refs"] == [identifier]
        ]
        if len(constraints) != 1:
            raise ValueError("Every projected point requires exactly one fixed constraint.")
        constraints[0]["target"] = list(uv)

    for ref in projections:
        found = False
        for kind in ("lines", "circles"):
            source = next(
                (e for e in source_solved.get(kind, []) if e["id"] == ref["source"]), None
            )
            target = next((e for e in result.get(kind, []) if e["id"] == ref["target"]), None)
            if source is None or target is None:
                continue
            found = True
            if not target.get("construction", False):
                raise ValueError("Projection targets must be construction entities.")
            if kind == "lines":
                start, end = point(source["start"]), point(source["end"])
                if ref.get("reverse", False):
                    start, end = end, start
                if math.dist(start, end) < 1e-6:
                    raise ValueError("Source line projects to a degenerate line.")
                fix(target["start"], start)
                fix(target["end"], end)
            else:
                if "reverse" in ref:
                    raise ValueError("Circular references do not have endpoint orientation.")
                normal = _rotate(inverse, _rotate(sp["quaternion"], (0, 0, 1)))
                if math.hypot(normal[0], normal[1]) > 1e-9:
                    raise ValueError("Circle projection requires parallel sketch planes.")
                fix(target["center"], point(source["center"]))
                target["radius"] = source["radius"]
                constraints = [
                    c
                    for c in result["constraints"]
                    if c["kind"] == "radius" and c["refs"] == [target["id"]]
                ]
                if len(constraints) != 1:
                    raise ValueError("Projected circle requires exactly one radius constraint.")
                constraints[0]["value"] = source["radius"]
        if not found:
            raise ValueError(
                "Projection source/target is missing or no longer the same line/circle type."
            )
    return result
