"""Explicit two-line corner replacement. Pure intent, never native evidence.

The old intersection point remains a dimensionable witness. It is constrained
onto both infinite supporting lines; no prior point or relation is deleted.
"""

import copy
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CornerPlan:
    corner: str
    outer: tuple[str, str]
    center: tuple[float, float]
    start: tuple[float, float]
    end: tuple[float, float]
    direction: str
    maximum_radius: float
    neighbors: tuple[str | None, str | None]
    support_points: tuple[str, ...]
    segment_ends: tuple[str, str]


def prepare_corner(sketch, line_ids, radius, positions):
    from .general_sketch_commands import DraftError, _identifier

    def require(condition, message):
        if not condition:
            raise DraftError(message)

    require(
        type(radius) in (int, float) and math.isfinite(radius) and 1e-6 <= radius <= 1e6,
        "Radius must be a positive finite number from 0.000001 to 1000000 mm.",
    )
    require(type(line_ids) in (tuple, list) and len(line_ids) == 2, "Select exactly two lines.")
    for identifier in line_ids:
        _identifier(identifier)
    require(len(set(line_ids)) == 2, "Select exactly two different lines.")
    lookup = {line["id"]: line for line in sketch["lines"]}
    require(all(i in lookup for i in line_ids), "The selected lines are no longer available.")
    lines = [lookup[i] for i in line_ids]
    require(
        not any(line.get("construction", False) for line in lines),
        "Corner Fillet needs two ordinary lines, not construction or projected geometry.",
    )
    shared = {lines[0]["start"], lines[0]["end"]} & {lines[1]["start"], lines[1]["end"]}
    require(
        len(shared) == 1,
        "The lines must share exactly one authored corner point; proximity is not connectivity.",
    )
    corner = next(iter(shared))
    require(
        not any(r["kind"] == "coincident" and corner in r["refs"] for r in sketch["constraints"]),
        "This corner has a coincidence relation. Release it explicitly before filleting.",
    )
    outer = tuple(line["end"] if line["start"] == corner else line["start"] for line in lines)
    require(
        not any(
            corner in [curve.get(role) for role in ("center", "start", "end")]
            for name in ("lines", "circles", "arcs")
            for curve in sketch.get(name, [])
            if curve["id"] not in line_ids
        ),
        "A third curve uses this corner. Corner Fillet will not detach shared geometry.",
    )
    # Resolve only explicitly authored fillet roles, never coordinate proximity.
    from .fillet_intent import CornerFilletIntent, validate_structure

    arcs = {a["id"]: a for a in sketch.get("arcs", [])}
    point_map = {p["id"]: p for p in sketch["points"]}
    neighbors = []
    witnesses = []
    allowed = set()
    for line_id, endpoint in zip(line_ids, outer, strict=True):
        owners = [a for a in arcs.values() if "fillet_intent" in a
                  and line_id in CornerFilletIntent.from_dict(a["fillet_intent"]).lines]
        require(len(owners) <= 1, "The selected line already has two fillet owners.")
        if not owners:
            neighbors.append(None)
            witnesses.append(endpoint)
            continue
        peer = owners[0]
        intent = validate_structure(peer, point_map, lookup, sketch["constraints"], arcs)
        role = intent.lines.index(line_id)
        require(intent.outer[role] == corner and intent.neighbors[role] is None
                and peer[("start", "end")[role]] == endpoint,
                "The existing fillet does not explicitly own the opposite end of this line.")
        neighbors.append(peer["id"])
        witnesses.append(intent.corner)
        allowed.update({("tangent", (peer["id"], line_id)),
                        ("point_on_line", (intent.corner, line_id))})
    support_points = tuple(dict.fromkeys((corner, *witnesses, *outer)))
    require(
        not any(
            set(relation["refs"]) & set(line_ids)
            and relation["kind"] not in {"horizontal", "vertical"}
            and (relation["kind"], tuple(relation["refs"])) not in allowed
            for relation in sketch["constraints"]
        ),
        "Release selected-line relations other than Horizontal/Vertical first. No relations are removed automatically.",
    )
    require(
        all(i in positions for i in support_points),
        "Check the sketch to obtain current corner positions.",
    )
    values = [tuple(positions[i]) for i in support_points]
    require(
        all(
            len(p) == 2
            and all(type(x) in (int, float) and math.isfinite(x) and abs(x) <= 1e6 for x in p)
            for p in values
        ),
        "Corner positions must be bounded finite coordinates.",
    )
    origin, a, b = [tuple(positions[i]) for i in (corner, *witnesses)]
    lengths = [math.dist(origin, p) for p in (a, b)]
    require(min(lengths) >= 1e-6, "A zero-length line cannot be filleted.")
    rays = [
        tuple((p[k] - origin[k]) / length for k in (0, 1))
        for p, length in zip((a, b), lengths, strict=True)
    ]
    available = []
    for endpoint, unit, length in zip(outer, rays, lengths, strict=True):
        offset = tuple(positions[endpoint][k] - origin[k] for k in (0, 1))
        along = sum(offset[k] * unit[k] for k in (0, 1))
        require(abs(offset[0] * unit[1] - offset[1] * unit[0]) <= 1e-7
                and 1e-6 <= along <= length + 1e-7,
                "The shared line must remain ordered along its original witness span; Check the sketch.")
        available.append(along)
    u, v = rays
    cross = u[0] * v[1] - u[1] * v[0]
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(u, v, strict=True))))
    require(abs(cross) > 1e-8, "Collinear or nearly collinear corners are unsupported.")
    half = math.atan2(abs(cross), dot) / 2
    distance = radius / math.tan(half)
    require(
        distance >= 1e-6,
        "Radius leaves a tangent point too close to the corner; choose a larger radius.",
    )
    maximum = min(available) * math.tan(half)
    require(
        distance < min(available) - 1e-6,
        f"Radius must be smaller than {maximum:.8g} mm and leave both lines nonzero.",
    )
    start = tuple(origin[k] + distance * u[k] for k in (0, 1))
    end = tuple(origin[k] + distance * v[k] for k in (0, 1))
    sign = 1 if cross > 0 else -1
    center = (start[0] - sign * radius * u[1], start[1] + sign * radius * u[0])
    require(
        math.dist(start, end) >= 1e-6,
        "This corner produces a degenerate arc; choose a larger radius or a less shallow corner.",
    )
    require(
        all(abs(x) <= 1e6 for p in (center, start, end) for x in p),
        "Fillet exceeds coordinate limits.",
    )
    return CornerPlan(corner, tuple(witnesses), center, start, end,
                      "cw" if cross > 0 else "ccw", maximum, tuple(neighbors), support_points, outer)


def make_record(sketch, line_ids, radius, positions, point_ids, arc_id, constraint_ids):
    """Deterministically derive the entire compound command from bounded intent."""
    plan = prepare_corner(sketch, line_ids, radius, positions)
    points = [
        {"id": identifier, "u": p[0], "v": p[1]}
        for identifier, p in zip(point_ids, (plan.center, plan.start, plan.end), strict=True)
    ]
    arc = dict(
        zip(
            ("id", "center", "start", "end", "direction"),
            (arc_id, *point_ids, plan.direction),
            strict=True,
        )
    )
    arc["fillet_intent"] = {
        "version": 2 if any(plan.neighbors) else 1,
        "corner": plan.corner,
        "lines": list(line_ids),
        "outer": list(plan.outer),
        "turn": "ccw" if plan.direction == "cw" else "cw",
        **({"neighbors": list(plan.neighbors)} if any(plan.neighbors) else {}),
    }
    relations = [
        ("radius", [arc_id]),
        ("tangent", [arc_id, line_ids[0]]),
        ("tangent", [arc_id, line_ids[1]]),
        ("point_on_line", [plan.corner, line_ids[0]]),
        ("point_on_line", [plan.corner, line_ids[1]]),
    ]
    constraints = [
        {"id": i, "kind": kind, "refs": refs, **({"value": radius} if kind == "radius" else {})}
        for i, (kind, refs) in zip(constraint_ids, relations, strict=True)
    ]
    updates = []
    for line_id, neighbor in zip(line_ids, plan.neighbors, strict=True):
        if neighbor is None:
            continue
        peer = next(a for a in sketch["arcs"] if a["id"] == neighbor)
        before = copy.deepcopy(peer["fillet_intent"])
        after = copy.deepcopy(before)
        after["version"] = 2
        after.setdefault("neighbors", [None, None])
        after["neighbors"][after["lines"].index(line_id)] = arc_id
        updates.append({"arc_id": neighbor, "before": before, "after": after})
    return {
        "op": "adjacent_corner_fillet" if updates else "corner_fillet",
        **({"peer_updates": updates} if updates else {}),
        "line_ids": list(line_ids),
        "radius": radius,
        "positions": {i: list(positions[i]) for i in plan.support_points},
        "points": points,
        "arc": arc,
        "constraints": constraints,
        "source_schema_version": sketch["schema_version"],
    }


def apply_record(sketch, command):
    from .general_sketch_commands import _keys, _require

    _keys(
        command,
        {
            "op",
            "line_ids",
            "radius",
            "positions",
            "points",
            "arc",
            "constraints",
            "source_schema_version",
        } | ({"peer_updates"} if command.get("op") == "adjacent_corner_fillet" else set()),
    )
    _require(
        type(command["line_ids"]) is list and type(command["positions"]) is dict,
        "Invalid corner fillet inputs.",
    )
    _require(
        type(command["points"]) is list
        and len(command["points"]) == 3
        and type(command["constraints"]) is list
        and len(command["constraints"]) == 5,
        "Corner Fillet requires exactly three points and five explicit relations.",
    )
    for point in command["points"]:
        _keys(point, {"id", "u", "v"})
    _keys(command["arc"], {"id", "center", "start", "end", "direction", "fillet_intent"})
    for index, relation in enumerate(command["constraints"]):
        _keys(relation, {"id", "kind", "refs", "value"} if index == 0 else {"id", "kind", "refs"})
    from .fillet_intent import CornerFilletIntent

    CornerFilletIntent.from_dict(command["arc"]["fillet_intent"])
    _require(type(command["source_schema_version"]) is int, "Invalid source sketch version.")
    if command["op"] == "adjacent_corner_fillet":
        _require(type(command["peer_updates"]) is list and 1 <= len(command["peer_updates"]) <= 2,
                 "Adjacent Corner Fillet requires one or two exact peer updates.")
        for update in command["peer_updates"]:
            _keys(update, {"arc_id", "before", "after"})
            CornerFilletIntent.from_dict(update["before"])
            CornerFilletIntent.from_dict(update["after"])
    expected = make_record(
        sketch,
        command["line_ids"],
        command["radius"],
        command["positions"],
        [p["id"] for p in command["points"]],
        command["arc"]["id"],
        [c["id"] for c in command["constraints"]],
    )
    _require(
        command == expected,
        "Corner Fillet command differs from its complete explicit construction.",
    )
    plan = prepare_corner(sketch, command["line_ids"], command["radius"], command["positions"])
    for identifier, endpoint in zip(command["line_ids"], command["points"][1:], strict=True):
        line = next(line for line in sketch["lines"] if line["id"] == identifier)
        line["start" if line["start"] == plan.corner else "end"] = endpoint["id"]
    for update in command.get("peer_updates", []):
        peer = next(a for a in sketch["arcs"] if a["id"] == update["arc_id"])
        peer["fillet_intent"] = copy.deepcopy(update["after"])
    sketch.setdefault("circles", [])
    sketch.setdefault("arcs", []).append(command["arc"].copy())
    sketch["schema_version"] = 3
    sketch["points"].extend(command["points"])
    sketch["constraints"].extend(command["constraints"])
