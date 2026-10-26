"""Versioned, explicit corner-fillet branch/segment intent. Native-free.

Mirrored in the Blender boundary: this is validation, never solver evidence.
"""

import math
import re
from dataclasses import dataclass

_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


class FilletIntentError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise FilletIntentError("Corner Fillet: " + message)


@dataclass(frozen=True)
class CornerFilletIntent:
    corner: str
    lines: tuple[str, str]
    outer: tuple[str, str]
    turn: str
    version: int = 1
    neighbors: tuple[str | None, str | None] = (None, None)

    def __post_init__(self):
        require(
            type(self.lines) is tuple and type(self.outer) is tuple
            and type(self.neighbors) is tuple,
            "persistent reference collections must be immutable tuples.",
        )
        require(type(self.version) is int and self.version in (1, 2), "unsupported intent version.")
        require(self.version == 2 or self.neighbors == (None, None),
                "version 1 cannot contain neighbor roles.")

    def to_dict(self):
        return {
            "version": self.version,
            "corner": self.corner,
            "lines": list(self.lines),
            "outer": list(self.outer),
            "turn": self.turn,
            **({"neighbors": list(self.neighbors)} if self.version == 2 else {}),
        }

    @classmethod
    def from_dict(cls, value):
        require(
            type(value) is dict and set(value) == ({"version", "corner", "lines", "outer", "turn"}
                | ({"neighbors"} if value.get("version") == 2 else set())),
            "unknown or incomplete persistent intent fields.",
        )
        require(
            type(value["version"]) is int and value["version"] in (1, 2), "unsupported intent version."
        )
        require(
            type(value["turn"]) is str and value["turn"] in {"cw", "ccw"}, "invalid corner turn."
        )
        for key in ("lines", "outer"):
            require(
                type(value[key]) is list and len(value[key]) == 2,
                "two explicit lines and outer points are required.",
            )
        for identifier in (value["corner"], *value["lines"], *value["outer"]):
            require(
                type(identifier) is str and _ID.fullmatch(identifier) is not None,
                "invalid referenced identity.",
            )
        require(
            len(set(value["lines"])) == 2 and len(set(value["outer"])) == 2,
            "duplicate supporting references.",
        )
        neighbors = value.get("neighbors", [None, None])
        require(type(neighbors) is list and len(neighbors) == 2 and all(
            n is None or (type(n) is str and _ID.fullmatch(n)) for n in neighbors
        ), "invalid explicit neighbor roles.")
        require(not (neighbors[0] is not None and neighbors[0] == neighbors[1]),
                "one neighbor cannot own both supporting lines.")
        return cls(value["corner"], tuple(value["lines"]), tuple(value["outer"]),
                   value["turn"], value["version"], tuple(neighbors))


def validate_structure(arc, points, lines, constraints, arcs=None):
    if "fillet_intent" not in arc:
        return None
    intent = CornerFilletIntent.from_dict(arc["fillet_intent"])
    require(
        not arc.get("construction", False),
        "a bounded fillet arc cannot become construction geometry.",
    )
    require(
        intent.turn == {"cw": "ccw", "ccw": "cw"}.get(arc["direction"]),
        "the original directed minor branch cannot be reversed.",
    )
    refs = (intent.corner, *intent.outer, arc["center"], arc["start"], arc["end"])
    require(
        len(set(refs)) == 6 and all(i in points for i in refs),
        "corner, outer and arc points must remain distinct and present.",
    )
    for identifier, outer, tangent, neighbor in zip(
        intent.lines, intent.outer, (arc["start"], arc["end"]), intent.neighbors, strict=True
    ):
        if neighbor is not None:
            require(arcs is not None and neighbor in arcs and neighbor != arc["id"],
                    "explicit neighboring fillet is missing.")
            peer = arcs[neighbor]
            require("fillet_intent" in peer, "neighbor must carry explicit fillet intent.")
            other = CornerFilletIntent.from_dict(peer["fillet_intent"])
            require(other.version == 2 and identifier in other.lines,
                    "neighbor does not own this supporting line.")
            role = other.lines.index(identifier)
            require(other.neighbors[role] == arc["id"] and other.corner == outer
                    and other.outer[role] == intent.corner,
                    "neighbor witness and line roles must be exactly reciprocal.")
            outer = peer[("start", "end")[role]]
        if arcs is not None:
            owners = {a["id"] for a in arcs.values() if "fillet_intent" in a
                      and identifier in CornerFilletIntent.from_dict(a["fillet_intent"]).lines}
            require(owners == ({arc["id"], neighbor} if neighbor is not None else {arc["id"]}),
                    "supporting line must have exactly its declared fillet owners.")
        require(identifier in lines, "a supporting line was removed.")
        line = lines[identifier]
        if intent.version == 2 and arcs is not None:
            require({i for i, candidate in lines.items()
                     if tangent in (candidate["start"], candidate["end"])} == {identifier}
                    and {a["id"] for a in arcs.values()
                         if tangent in (a.get("center"), a["start"], a["end"])} == {arc["id"]},
                    "a tangent endpoint must belong only to its declared line and fillet arc.")
        require(
            not line.get("construction", False)
            and {line["start"], line["end"]} == {outer, tangent},
            "supporting line endpoints or construction status changed; delete the fillet explicitly before this edit.",
        )
    signatures = [("radius", (arc["id"],))]
    signatures += [("tangent", (arc["id"], line)) for line in intent.lines]
    signatures += [("point_on_line", (intent.corner, line)) for line in intent.lines]
    for kind, refs in signatures:
        require(
            sum(c["kind"] == kind and tuple(c["refs"]) == refs for c in constraints) == 1,
            "the radius, tangent and intersection-witness relations must remain intact and unique.",
        )
    return intent


def validate_solved(sketch):
    points = {p["id"]: (p["u"], p["v"]) for p in sketch["points"]}
    lines = {line["id"]: line for line in sketch["lines"]}
    arcs = {a["id"]: a for a in sketch.get("arcs", [])}
    for arc in arcs.values():
        intent = validate_structure(arc, points, lines, sketch["constraints"], arcs)
        if intent is None:
            continue
        corner = points[intent.corner]
        rays = []
        for outer_id, tangent_id, line_id, neighbor in zip(
            intent.outer, (arc["start"], arc["end"]), intent.lines, intent.neighbors, strict=True
        ):
            outer, tangent = points[outer_id], points[tangent_id]
            ray = tuple(outer[k] - corner[k] for k in (0, 1))
            length = math.hypot(*ray)
            require(math.isfinite(length) and length > 2e-6, "supporting segment collapsed.")
            unit = tuple(x / length for x in ray)
            offset = tuple(tangent[k] - corner[k] for k in (0, 1))
            along = sum(a * b for a, b in zip(offset, unit, strict=True))
            across = abs(offset[0] * unit[1] - offset[1] * unit[0])
            require(
                across <= 1e-7 and 1e-6 <= along <= length - 1e-6,
                "radius moves a tangent point outside its original corner-to-outer segment; reduce the radius.",
            )
            if neighbor is not None:
                peer = arcs[neighbor]
                role = peer["fillet_intent"]["lines"].index(line_id)
                opposite = points[peer[("start", "end")[role]]]
                remaining = sum((opposite[k] - tangent[k]) * unit[k] for k in (0, 1))
                require(remaining >= 1e-6,
                        "adjacent radii overlap or collapse their shared line; reduce the radii.")
            rays.append(unit)
        cross = rays[0][0] * rays[1][1] - rays[0][1] * rays[1][0]
        require(
            abs(cross) > 1e-8 and ("ccw" if cross > 0 else "cw") == intent.turn,
            "supporting rays reversed or became collinear; the original corner branch is required.",
        )
        center, start, end = (points[arc[key]] for key in ("center", "start", "end"))
        a = math.atan2(start[1] - center[1], start[0] - center[0])
        b = math.atan2(end[1] - center[1], end[0] - center[0])
        sweep = ((b - a) if arc["direction"] == "ccw" else (a - b)) % math.tau
        require(0 < sweep < math.pi, "only the original minor tangent arc is permitted.")
