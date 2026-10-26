"""Typed general-sketch commands and a strict, deterministic intent reducer.

This dependency leaf owns bounded JSON/geometry primitives and stable-ID command
records. It validates authoring intent only; it never solves, calculates DoF,
launches a process, imports Blender/core, or interprets saved seeds as evidence.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from typing import Literal, TypeAlias

from .general_sketch_validation import _ID as _ID
from .general_sketch_validation import ARC_JOURNAL_VERSION as ARC_JOURNAL_VERSION
from .general_sketch_validation import JOURNAL_VERSION as JOURNAL_VERSION
from .general_sketch_validation import DraftError as DraftError
from .general_sketch_validation import _coordinate as _coordinate
from .general_sketch_validation import _identifier as _identifier
from .general_sketch_validation import _journal_version as _journal_version
from .general_sketch_validation import _json as _json
from .general_sketch_validation import _keys as _keys
from .general_sketch_validation import _normalized_sketch as _normalized_sketch
from .general_sketch_validation import _point as _point
from .general_sketch_validation import _require as _require
from .general_sketch_validation import _validate_sketch as _validate_sketch
from .rectangle_tool import rectangle_corners, validate_rectangle_record
from .sketch_relations import canonical_refs

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_JOURNAL_ENTRIES = 64
MAX_JOURNAL_BYTES = 2 * 1024 * 1024
MAX_ALLOCATED_IDS = 8192
MAX_RAW_TEXT_BYTES = 64 * 1024
MAX_COUNTER = 2**53 - 1
Scalar: TypeAlias = int | float | str
RelationKind: TypeAlias = Literal[
    "horizontal",
    "vertical",
    "coincident",
    "fixed",
    "distance",
    "radius",
    "parallel",
    "perpendicular",
    "equal",
    "tangent",
    "point_on_line",
    "midpoint",
    "symmetry",
    "concentric",
    "circle_line_tangent",
    "angle",
]
EntityKind: TypeAlias = Literal["point", "line", "circle", "arc", "constraint"]
_COLLECTION = {"point": "points", "line": "lines", "circle": "circles", "constraint": "constraints"}
_ARC_COLLECTION = {**_COLLECTION, "arc": "arcs"}


def _duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON fields are unsupported.")
        result[key] = value
    return result


def _reject_constant(value):
    raise DraftError(f"Non-finite JSON number: {value}")


def _parse_number(token, *, integer=False):
    _require(len(token) <= 128, "JSON numeric token is too long.")
    value = int(token) if integer else float(token)
    _require(integer or math.isfinite(value), "JSON numbers must be finite.")
    return value


def parse_json(text, limit):
    """Strict text boundary shared by snapshots; no eval, pickle or coercion."""
    _require(type(text) is str and len(text) <= limit, "Draft JSON exceeds its byte limit.")
    try:
        _require(len(text.encode("utf-8")) <= limit, "Draft JSON exceeds its byte limit.")
        depth, quoted, escaped = 0, False, False
        for character in text:
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in "[{":
                depth += 1
                _require(depth <= 32, "Draft JSON nesting is too deep.")
            elif character in "]}":
                depth -= 1
        return json.loads(
            text,
            object_pairs_hook=_duplicate_keys,
            parse_constant=_reject_constant,
            parse_int=lambda token: _parse_number(token, integer=True),
            parse_float=_parse_number,
        )
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        if isinstance(exc, DraftError):
            raise
        raise DraftError("Draft JSON is unreadable; retain its original text.") from exc


def _integer(value, *, minimum=0):
    _require(
        type(value) is int and minimum <= value <= MAX_COUNTER, "Invalid draft revision/count."
    )
    return value


def _successor(value, label):
    """Reserve a persistable successor before any authoring state is mutated."""
    _integer(value)
    _require(value < MAX_COUNTER, f"The {label} limit is reached; the draft is unchanged.")
    return value + 1


def _radius(value):
    _coordinate(value)
    _require(value >= 1e-6, "Radius must be between 0.000001 and 1,000,000 mm.")
    return value


def _line_length(value):
    _require(
        type(value) in (int, float) and 1e-6 <= value <= 1e6 and math.isfinite(value),
        "Line length must be a finite numeric literal from 0.000001 to 1,000,000 mm.",
    )
    return value


def _ids(sketch):
    return {
        sketch["plane"]["id"],
        *(item["id"] for name in _ARC_COLLECTION.values() for item in sketch.get(name, [])),
    }


def _record(sketch, collection, identifier):
    result = next((item for item in sketch.get(collection, []) if item["id"] == identifier), None)
    _require(result is not None, f"The {identifier} target no longer exists.")
    return result


@dataclass(frozen=True)
class PointRef:
    id: str


@dataclass(frozen=True)
class PointSeed:
    u: float
    v: float


PointInput: TypeAlias = PointRef | PointSeed


@dataclass(frozen=True)
class AddPoint:
    point: PointSeed


@dataclass(frozen=True)
class AddLine:
    start: PointInput
    end: PointInput
    axis: str | None = None


@dataclass(frozen=True)
class AddLengthLine:
    """One line with an editable literal-mm distance and optional axis relation."""

    start: PointInput
    end: PointInput
    length_mm: float
    axis: str | None = None


@dataclass(frozen=True)
class AddRectangle:
    """Two opposite local-plane corners; four shared points and explicit H/V intent."""

    first: PointSeed
    opposite: PointSeed


@dataclass(frozen=True)
class AddCircle:
    center: PointInput
    radius: float


@dataclass(frozen=True)
class AddDiameterCircle:
    """One circle and canonical radius driver from a literal diameter."""

    center: PointInput
    diameter: float


@dataclass(frozen=True)
class AddProjectionGeometry:
    """One atomic construction entity with explicit anchor/radius drivers."""

    kind: str
    points: tuple[PointSeed, ...]
    radius: float = 1.0
    direction: str = "ccw"


@dataclass(frozen=True)
class AddArc:
    center: PointInput
    start: PointInput
    end: PointInput
    direction: Literal["ccw", "cw"]


@dataclass(frozen=True)
class CornerFillet:
    line_ids: tuple[str, str]
    radius: float
    positions: dict


@dataclass(frozen=True)
class RemoveCornerFillet:
    arc_id: str


@dataclass(frozen=True)
class ReverseArcSweep:
    arc_id: str


@dataclass(frozen=True)
class AddPointLineDimension:
    """Atomic perpendicular offset using ordinary native construction relations."""

    point_id: str
    line_id: str
    foot: PointSeed
    value: Scalar


@dataclass(frozen=True)
class AddRelation:
    kind: RelationKind
    refs: tuple[str, ...]
    value: Scalar | None = None
    target: tuple[float, float] | None = None


@dataclass(frozen=True)
class MovePoint:
    point_id: str
    target: tuple[float, float]
    preserve_constraints: bool = False


@dataclass(frozen=True)
class SetConstruction:
    targets: tuple[tuple[str, str], ...]
    construction: bool


@dataclass(frozen=True)
class EditFixedTarget:
    constraint_id: str
    target: tuple[float, float]


@dataclass(frozen=True)
class EditDriver:
    """Journal command; use the pending edit/trial acceptance API to apply it."""

    constraint_id: str
    value: Scalar


@dataclass(frozen=True)
class DeletePreview:
    revision: int
    targets: tuple[tuple[EntityKind, str], ...]
    points: tuple[str, ...]
    lines: tuple[str, ...]
    circles: tuple[str, ...]
    constraints: tuple[str, ...]
    arcs: tuple[str, ...] = ()

    @property
    def requires_solution(self):
        return bool(self.constraints)


@dataclass(frozen=True)
class DeleteBatch:
    preview: DeletePreview


@dataclass(frozen=True)
class RecoverRemoveRelation:
    """Remove one relation using exact authored seeds when no current solve exists.

    This is an explicit recovery policy, not a weaker form of DeleteBatch. The
    draft orchestration rejects successful-current-solve use; preparation accepts
    no external seeds and permits no geometry deletion or implicit cascade.
    """

    preview: DeletePreview


Command: TypeAlias = (
    AddPoint
    | AddLine
    | AddLengthLine
    | AddCircle
    | AddDiameterCircle
    | AddRectangle
    | AddProjectionGeometry
    | AddArc
    | ReverseArcSweep
    | CornerFillet
    | RemoveCornerFillet
    | AddRelation
    | AddPointLineDimension
    | MovePoint
    | SetConstruction
    | EditFixedTarget
    | EditDriver
    | DeleteBatch
    | RecoverRemoveRelation
)


@dataclass(frozen=True)
class CommandResult:
    changed: bool
    revision: int
    entity_ids: tuple[str, ...] = ()
    constraint_id: str | None = None


@dataclass(frozen=True)
class PendingDimensionEdit:
    constraint_id: str
    kind: str
    refs: tuple[str, ...]
    source: Scalar
    base_revision: int
    input_revision: int
    raw_text: str
    error: str = ""


@dataclass(frozen=True)
class _Solution:
    revision: int
    input_revision: int | None
    candidate_json: str
    points_json: str
    circles_json: str


def _delete_sets(sketch, targets, *, journal_version=JOURNAL_VERSION):
    _validate_sketch(sketch, journal_version=journal_version)
    collections = _ARC_COLLECTION if sketch["schema_version"] == 3 else _COLLECTION
    removed = {name: set() for name in collections.values()}
    _require(
        type(targets) in (tuple, list) and 0 < len(targets) <= 1024, "Select targets for deletion."
    )
    normalized = []
    for target in targets:
        _require(type(target) in (tuple, list) and len(target) == 2, "Invalid deletion target.")
        kind, identifier = target
        _require(type(kind) is str and kind in collections, "Unknown deletion target kind.")
        _identifier(identifier)
        collection = collections[kind]
        _record(sketch, collection, identifier)
        removed[collection].add(identifier)
        normalized.append((kind, identifier))
    for line in sketch["lines"]:
        if {line["start"], line["end"]} & removed["points"]:
            removed["lines"].add(line["id"])
    for circle in sketch.get("circles", []):
        if circle["center"] in removed["points"]:
            removed["circles"].add(circle["id"])
    for arc in sketch.get("arcs", []):
        if {arc["center"], arc["start"], arc["end"]} & removed["points"]:
            removed["arcs"].add(arc["id"])
    entities = removed["points"] | removed["lines"] | removed["circles"]
    entities |= removed.get("arcs", set())
    for constraint in sketch["constraints"]:
        if set(constraint["refs"]) & entities:
            removed["constraints"].add(constraint["id"])
    return tuple(sorted(set(normalized))), {
        name: sorted(values) for name, values in removed.items()
    }


def _apply_record(sketch, command, *, journal_version=JOURNAL_VERSION):
    """Deterministic journal reducer. Stored seeds are intent, never evidence."""
    _require(type(command) is dict and type(command.get("op")) is str, "Invalid journal command.")
    _validate_sketch(sketch, journal_version=journal_version)
    result = copy.deepcopy(sketch)
    op = command["op"]
    if op in {
        "add",
        "add_projection",
        "add_rectangle",
        "add_point_line_dimension",
        "add_axis_line",
        "add_length_line",
        "add_diameter_circle",
    }:
        _keys(command, {"op", "points", "lines", "circles", "constraints"})
        for name in _COLLECTION.values():
            _require(type(command[name]) is list, "Invalid add command records.")
        _require(any(command[name] for name in _COLLECTION.values()), "Empty add command.")
        point_count = len(command["points"])
        shape = (len(command["lines"]), len(command["circles"]), len(command["constraints"]))
        valid = (
            (shape == (0, 0, 0) and point_count == 1)
            or (shape == (1, 0, 0) and point_count <= 2)
            or (shape == (0, 1, 0) and point_count <= 1)
            or (shape == (0, 0, 1) and point_count == 0)
        )
        if op == "add_projection":
            valid = (shape == (1, 0, 2) and point_count == 2) or (
                shape == (0, 1, 2) and point_count == 1
            )
            _require(valid, "A projection needs one construction entity and its complete drivers.")
            entity = (command["lines"] or command["circles"])[0]
            _require(entity.get("construction") is True, "Projected geometry must be construction.")
            fixed = [c for c in command["constraints"] if c.get("kind") == "fixed"]
            _require(
                {c["refs"][0] for c in fixed} == {p["id"] for p in command["points"]},
                "Projected points need fixed anchors.",
            )
        if op == "add_point_line_dimension":
            from .point_line_dimension import validate_record

            validate_record(command, sketch, require=_require, keys=_keys)
            valid = True
        if op == "add_axis_line":
            _require(shape == (1, 0, 1) and point_count <= 2, "Invalid axis-line command.")
            line, relation = command["lines"][0], command["constraints"][0]
            _keys(relation, {"id", "kind", "refs"})
            _require(
                relation["kind"] in {"horizontal", "vertical"} and relation["refs"] == [line["id"]],
                "Axis relation must refer only to the new line.",
            )
            _require(
                {p["id"] for p in command["points"]}
                == {line["start"], line["end"]} - {p["id"] for p in sketch["points"]},
                "Axis-line points must be exactly its new endpoints.",
            )
            valid = True
        if op == "add_length_line":
            _require(
                shape in {(1, 0, 1), (1, 0, 2)} and point_count <= 2,
                "Invalid length-line command.",
            )
            line, distance = command["lines"][0], command["constraints"][0]
            _keys(line, {"id", "start", "end"})
            _keys(distance, {"id", "kind", "refs", "value"})
            _require(
                distance["kind"] == "distance" and distance["refs"] == [line["start"], line["end"]],
                "Length relation must refer only to the new line's endpoints.",
            )
            _line_length(distance["value"])
            _require(
                {p["id"] for p in command["points"]}
                == {line["start"], line["end"]} - {p["id"] for p in sketch["points"]},
                "Length-line points must be exactly its new endpoints.",
            )
            if len(command["constraints"]) == 2:
                axis = command["constraints"][1]
                _keys(axis, {"id", "kind", "refs"})
                _require(
                    axis["kind"] in {"horizontal", "vertical"} and axis["refs"] == [line["id"]],
                    "Length-line axis must refer only to the new line.",
                )
            valid = True
        if op == "add_diameter_circle":
            _require(shape == (0, 1, 1) and point_count <= 1, "Invalid diameter-circle command.")
            circle, radius = command["circles"][0], command["constraints"][0]
            _keys(circle, {"id", "center", "radius"})
            _keys(radius, {"id", "kind", "refs", "value"})
            _require(radius["kind"] == "radius" and radius["refs"] == [circle["id"]],
                     "Diameter driver must refer only to the new circle.")
            _radius(radius["value"])
            _require(radius["value"] == circle["radius"] and radius["value"] <= 500000,
                     "Diameter seed and driver must match the bounded literal.")
            _require({p["id"] for p in command["points"]}
                     == {circle["center"]} - {p["id"] for p in sketch["points"]},
                     "Diameter-circle points must be exactly its new center.")
            valid = True
        if op == "add_rectangle":
            validate_rectangle_record(command, require=_require, keys=_keys)
            valid = True
        _require(valid, "Unsupported compound add command.")
        if command["circles"] and result["schema_version"] == 1:
            result["schema_version"] = 2
            result["circles"] = []
        for name in _COLLECTION.values():
            if command[name]:
                result.setdefault(name, []).extend(copy.deepcopy(command[name]))
        _validate_sketch(result, journal_version=journal_version)
        for line in command["lines"]:
            start = _record(result, "points", line["start"])
            end = _record(result, "points", line["end"])
            _require(
                math.dist((start["u"], start["v"]), (end["u"], end["v"])) >= 1e-6,
                "A line needs endpoints at least 0.000001 mm apart.",
            )
    elif op == "add_projection_arc":
        _require(journal_version == ARC_JOURNAL_VERSION, "Arc projection requires journal 3.")
        _keys(command, {"op", "points", "arc", "constraints", "source_schema_version"})
        arc = command["arc"]
        _keys(arc, {"id", "center", "start", "end", "direction", "construction"})
        _require(arc["construction"] is True, "Projected arc must be construction.")
        _require(len(command["points"]) == 3 and len(command["constraints"]) == 3,
                 "Projected arc requires exactly three independent fixed anchors.")
        ids = [arc[role] for role in ("center", "start", "end")]
        _require([p["id"] for p in command["points"]] == ids and len(set(ids)) == 3,
                 "Projected arc point roles must retain allocation order.")
        for constraint, point in zip(command["constraints"], command["points"], strict=True):
            _keys(constraint, {"id", "kind", "refs", "target"})
            _require(constraint["kind"] == "fixed" and constraint["refs"] == [point["id"]]
                     and constraint["target"] == [point["u"], point["v"]],
                     "Projected arc anchors must match their explicit point seeds.")
        plain = {key: value for key, value in arc.items() if key != "construction"}
        result = _apply_record(result, {"op": "add_arc", "points": command["points"],
                               "arc": plain, "source_schema_version": command["source_schema_version"]},
                               journal_version=journal_version)
        result["arcs"][-1]["construction"] = True
        result["constraints"].extend(copy.deepcopy(command["constraints"]))
    elif op == "add_arc":
        _require(journal_version == ARC_JOURNAL_VERSION, "AddArc requires journal 3 capability.")
        _keys(command, {"op", "points", "arc", "source_schema_version"})
        source_version = command["source_schema_version"]
        _require(
            type(source_version) is int and source_version == result["schema_version"],
            "Arc migration source schema differs from its exact previous state.",
        )
        _require(type(command["points"]) is list, "Invalid arc point records.")
        arc = command["arc"]
        _keys(arc, {"id", "center", "start", "end", "direction"})
        for name in ("id", "center", "start", "end"):
            _identifier(arc[name])
        prior_points = {point["id"] for point in result["points"]}
        new_roles = [
            arc[role] for role in ("center", "start", "end") if arc[role] not in prior_points
        ]
        _require(
            all(type(point) is dict and "id" in point for point in command["points"])
            and [point["id"] for point in command["points"]] == new_roles,
            "Arc points must be exactly its new center/start/end roles in allocation order.",
        )
        if source_version == 1:
            result["circles"] = []
        if source_version in (1, 2):
            result["schema_version"] = 3
            result["arcs"] = []
        result["points"].extend(copy.deepcopy(command["points"]))
        result["arcs"].append(copy.deepcopy(arc))
    elif op in {"corner_fillet", "adjacent_corner_fillet"}:
        from .sketch_corner_fillet import apply_record

        _require(journal_version == ARC_JOURNAL_VERSION, "Corner Fillet requires journal 3 capability.")
        apply_record(result, copy.deepcopy(command))
    elif op == "remove_corner_fillet":
        from .sketch_remove_fillet import apply_record

        _require(journal_version == ARC_JOURNAL_VERSION, "Remove Fillet requires journal 3 capability.")
        apply_record(result, copy.deepcopy(command))
    elif op == "reverse_arc":
        _require(
            journal_version == ARC_JOURNAL_VERSION, "Arc reversal requires journal 3 capability."
        )
        _keys(command, {"op", "arc_id", "from_direction", "to_direction"})
        _identifier(command["arc_id"])
        arc = _record(result, "arcs", command["arc_id"])
        _require(
            command["from_direction"] == arc["direction"]
            and command["to_direction"] == {"cw": "ccw", "ccw": "cw"}[arc["direction"]],
            "Arc reversal must change only the current direction to its opposite.",
        )
        arc["direction"] = command["to_direction"]
    elif op in {"move_point", "drag_point"}:
        _keys(command, {"op", "point_id", "target"})
        point = _record(result, "points", command["point_id"])
        incident = {point["id"]}
        for name, roles in (
            ("lines", ("start", "end")),
            ("circles", ("center",)),
            ("arcs", ("center", "start", "end")),
        ):
            incident.update(
                curve["id"]
                for curve in result.get(name, [])
                if any(curve[role] == point["id"] for role in roles)
            )
        if op == "move_point":
            _require(
                not any(
                    incident.intersection(relation["refs"]) for relation in result["constraints"]
                ),
                "Release relations on this endpoint and its connected curves before trimming or extending.",
            )
        else:
            _require(
                not any(isinstance(point[axis], str) for axis in ("u", "v")),
                "This point has coordinate formulas; edit its formulas instead of dragging.",
            )
            _require(
                not any(
                    r["kind"] == "fixed" and point["id"] in r["refs"] for r in result["constraints"]
                ),
                "This point is fixed; edit or release its fixed relation before dragging.",
            )
        point["u"], point["v"] = _point(command["target"])
    elif op == "construction":
        _keys(command, {"op", "targets", "construction"})
        _require(type(command["construction"]) is bool, "Construction must be a boolean.")
        _require(
            type(command["targets"]) is list and 0 < len(command["targets"]) <= 32,
            "Choose one to 32 curves.",
        )
        seen = set()
        for pair in command["targets"]:
            _require(type(pair) is list and len(pair) == 2, "Invalid construction target.")
            kind, identifier = pair
            _require(
                kind in {"line", "circle", "arc"} and identifier not in seen,
                "Construction targets must be distinct curves.",
            )
            seen.add(identifier)
            entity = _record(result, kind + "s", identifier)
            if command["construction"]:
                entity["construction"] = True
            else:
                entity.pop("construction", None)
    elif op in {"driver", "fixed_target"}:
        field = "value" if op == "driver" else "target"
        _keys(command, {"op", "constraint_id", field})
        constraint = _record(result, "constraints", command["constraint_id"])
        _require(
            constraint["kind"]
            in ({"distance", "radius", "angle"} if op == "driver" else {"fixed"}),
            "Wrong relation edit kind.",
        )
        constraint[field] = copy.deepcopy(command[field])
    elif op in {"delete", "delete_v3"}:
        _require(
            (op == "delete" and result["schema_version"] in (1, 2))
            or (op == "delete_v3" and result["schema_version"] == 3 and journal_version == 3),
            "Deletion operation does not match the explicit sketch/journal version.",
        )
        _keys(command, {"op", "targets", "removed", "seeds"})
        targets, removed = _delete_sets(result, command["targets"], journal_version=journal_version)
        _require(
            [list(item) for item in targets] == command["targets"]
            and removed == command["removed"],
            "Deletion cascade differs from its announced targets.",
        )
        seeds = command["seeds"]
        if removed["constraints"]:
            _keys(seeds, {"points", "circles"})
            for name, fields in (("points", {"id", "u", "v"}), ("circles", {"id", "radius"})):
                _require(type(seeds[name]) is list, "Invalid release seed records.")
                _require(
                    len(seeds[name]) == len(result.get(name, [])),
                    "Incomplete release seed identities.",
                )
                seen = set()
                for seed in seeds[name]:
                    _keys(seed, fields)
                    _require(seed["id"] not in seen, "Duplicate release seed identity.")
                    seen.add(seed["id"])
                    record = _record(result, name, seed["id"])
                    for field in fields - {"id"}:
                        record[field] = (
                            _radius(seed[field]) if field == "radius" else _coordinate(seed[field])
                        )
        else:
            _require(seeds is None, "Unrequested geometry reseeding is unsupported.")
        for name in removed:
            if name in result:
                result[name] = [item for item in result[name] if item["id"] not in removed[name]]
    else:
        raise DraftError("Unsupported journal operation.")
    return _validate_sketch(result, journal_version=journal_version)


@dataclass(frozen=True)
class PreparedCommand:
    record: dict | None
    allocated_ids: set[str]
    next_id: int
    entity_ids: tuple[str, ...]
    constraint_id: str | None


def prepare_command(
    sketch,
    command,
    revision,
    allocated_ids,
    next_id,
    *,
    release_seeds=None,
    max_allocated_ids=MAX_ALLOCATED_IDS,
    journal_version=JOURNAL_VERSION,
):
    """Prepare atomic accepted intent; ID allocation remains provisional on errors.

    DeleteBatch release seeds are ordinary data supplied only after the
    orchestration layer's current-solution gate. RecoverRemoveRelation instead
    copies current authored seeds here, after the owner's no-current-solve gate.
    This helper makes no claim about native validity or solver authority.
    """
    _validate_sketch(sketch, journal_version=journal_version)

    def allocate(prefix, allocated, counter):
        while f"{prefix}_d{counter[0]}" in allocated:
            counter[0] = _successor(counter[0], "stable-ID allocation counter")
        _require(
            len(allocated) < max_allocated_ids,
            "This draft's stable-ID budget is exhausted; finish or cancel before starting another draft.",
        )
        identifier = f"{prefix}_d{counter[0]}"
        counter[0] = _successor(counter[0], "stable-ID allocation counter")
        allocated.add(identifier)
        return identifier

    allocated, counter = set(allocated_ids), [next_id]
    record = {"op": "add", "points": [], "lines": [], "circles": [], "constraints": []}
    created, relation_id = [], None

    def point(source):
        if isinstance(source, PointRef):
            return _record(sketch, "points", source.id)["id"]
        _require(isinstance(source, PointSeed), "Expected an explicit point reference or seed.")
        coordinates = _point((source.u, source.v))
        identifier = allocate("p", allocated, counter)
        record["points"].append({"id": identifier, "u": coordinates[0], "v": coordinates[1]})
        created.append(identifier)
        return identifier

    if isinstance(command, AddPoint):
        _require(isinstance(command.point, PointSeed), "A new point requires a seed.")
        point(command.point)
    elif isinstance(command, (AddLine, AddLengthLine)):
        if isinstance(command, AddLengthLine):
            _line_length(command.length_mm)
        _require(command.axis in (None, "horizontal", "vertical"), "Invalid line axis.")
        start, end = point(command.start), point(command.end)
        positions = {
            item["id"]: (item["u"], item["v"]) for item in sketch["points"] + record["points"]
        }
        _require(
            start != end and math.dist(positions[start], positions[end]) >= 1e-6,
            "A line needs distinct endpoints at least 0.000001 mm apart.",
        )
        identifier = allocate("l", allocated, counter)
        record["lines"].append({"id": identifier, "start": start, "end": end})
        created.append(identifier)
        if isinstance(command, AddLengthLine):
            relation_id = allocate("r", allocated, counter)
            record["constraints"].append(
                {
                    "id": relation_id,
                    "kind": "distance",
                    "refs": [start, end],
                    "value": command.length_mm,
                }
            )
            created.append(relation_id)
            record["op"] = "add_length_line"
        if command.axis is not None:
            axis_id = allocate("r", allocated, counter)
            record["constraints"].append(
                {"id": axis_id, "kind": command.axis, "refs": [identifier]}
            )
            created.append(axis_id)
            if not isinstance(command, AddLengthLine):
                relation_id = axis_id
                record["op"] = "add_axis_line"
    elif isinstance(command, AddRectangle):
        _require(
            type(command.first) is PointSeed and type(command.opposite) is PointSeed,
            "Rectangle corners must be explicit local-plane coordinates.",
        )
        corners = rectangle_corners(
            _point((command.first.u, command.first.v)),
            _point((command.opposite.u, command.opposite.v)),
        )
        _require(
            abs(corners[2][0] - corners[0][0]) >= 1e-6
            and abs(corners[2][1] - corners[0][1]) >= 1e-6,
            "Rectangle width and height must be at least 0.000001 mm.",
        )
        ids = [point(PointSeed(*corner)) for corner in corners]
        for index in range(4):
            identifier = allocate("l", allocated, counter)
            record["lines"].append(
                {"id": identifier, "start": ids[index], "end": ids[(index + 1) % 4]}
            )
            created.append(identifier)
        for index, line in enumerate(record["lines"]):
            identifier = allocate("r", allocated, counter)
            record["constraints"].append(
                {
                    "id": identifier,
                    "kind": "horizontal" if index % 2 == 0 else "vertical",
                    "refs": [line["id"]],
                }
            )
            created.append(identifier)
        record["op"] = "add_rectangle"
    elif isinstance(command, (AddCircle, AddDiameterCircle)):
        if isinstance(command, AddDiameterCircle):
            _line_length(command.diameter)
            radius = _radius(command.diameter / 2)
        else:
            radius = _radius(command.radius)
        center = point(command.center)
        identifier = allocate("c", allocated, counter)
        record["circles"].append({"id": identifier, "center": center, "radius": radius})
        created.append(identifier)
        if isinstance(command, AddDiameterCircle):
            relation_id = allocate("r", allocated, counter)
            record["constraints"].append({"id": relation_id, "kind": "radius",
                                          "refs": [identifier], "value": radius})
            created.append(relation_id)
            record["op"] = "add_diameter_circle"
    elif isinstance(command, AddProjectionGeometry):
        _require(command.kind in {"line", "circle", "arc"}, "Project a line, circle or arc.")
        _require(
            type(command.points) is tuple
            and len(command.points) == {"line": 2, "circle": 1, "arc": 3}[command.kind],
            "Wrong projected point count.",
        )
        point_ids = [point(p) for p in command.points]
        identifier = allocate({"line": "l", "circle": "c", "arc": "a"}[command.kind], allocated, counter)
        if command.kind == "line":
            record["lines"].append(
                {"id": identifier, "start": point_ids[0], "end": point_ids[1], "construction": True}
            )
        elif command.kind == "circle":
            record["circles"].append(
                {
                    "id": identifier,
                    "center": point_ids[0],
                    "radius": _radius(command.radius),
                    "construction": True,
                }
            )
        created.append(identifier)
        for item in record["points"]:
            relation = allocate("r", allocated, counter)
            record["constraints"].append(
                {
                    "id": relation,
                    "kind": "fixed",
                    "refs": [item["id"]],
                    "target": [item["u"], item["v"]],
                }
            )
        if command.kind == "circle":
            relation = allocate("r", allocated, counter)
            record["constraints"].append(
                {
                    "id": relation,
                    "kind": "radius",
                    "refs": [identifier],
                    "value": _radius(command.radius),
                }
            )
        record["op"] = "add_projection"
        if command.kind == "arc":
            _require(journal_version == ARC_JOURNAL_VERSION, "Arc projection requires journal 3.")
            _require(command.direction in {"cw", "ccw"}, "Choose an explicit arc direction.")
            record = {"op": "add_projection_arc", "points": record["points"],
                      "constraints": record["constraints"],
                      "source_schema_version": sketch["schema_version"],
                      "arc": {"id": identifier, "center": point_ids[0], "start": point_ids[1],
                              "end": point_ids[2], "direction": command.direction,
                              "construction": True}}
    elif isinstance(command, AddArc):
        _require(journal_version == ARC_JOURNAL_VERSION, "AddArc requires journal 3 capability.")
        center, start, end = point(command.center), point(command.start), point(command.end)
        identifier = allocate("a", allocated, counter)
        record = {
            "op": "add_arc",
            "points": record["points"],
            "arc": {
                "id": identifier,
                "center": center,
                "start": start,
                "end": end,
                "direction": command.direction,
            },
            "source_schema_version": sketch["schema_version"],
        }
        created.append(identifier)
    elif isinstance(command, CornerFillet):
        from .sketch_corner_fillet import make_record

        _require(journal_version == ARC_JOURNAL_VERSION, "Corner Fillet requires journal 3 capability.")
        point_ids = [allocate("p", allocated, counter) for _ in range(3)]
        arc_id = allocate("a", allocated, counter)
        constraint_ids = [allocate("r", allocated, counter) for _ in range(5)]
        record = make_record(sketch, command.line_ids, command.radius, command.positions,
                             point_ids, arc_id, constraint_ids)
        created.extend((*point_ids, arc_id))
        relation_id = constraint_ids[0]
    elif isinstance(command, RemoveCornerFillet):
        from .sketch_remove_fillet import make_record

        _require(journal_version == ARC_JOURNAL_VERSION, "Remove Fillet requires journal 3 capability.")
        record = make_record(sketch, command.arc_id)
    elif isinstance(command, ReverseArcSweep):
        _require(
            journal_version == ARC_JOURNAL_VERSION, "Arc reversal requires journal 3 capability."
        )
        arc = _record(sketch, "arcs", command.arc_id)
        record = {
            "op": "reverse_arc",
            "arc_id": command.arc_id,
            "from_direction": arc["direction"],
            "to_direction": {"cw": "ccw", "ccw": "cw"}[arc["direction"]],
        }
    elif isinstance(command, AddPointLineDimension):
        from .point_line_dimension import existing_offset
        from .unit_input import normalize_driver_input

        _record(sketch, "points", command.point_id)
        line = _record(sketch, "lines", command.line_id)
        _require(
            command.point_id not in (line["start"], line["end"]),
            "An endpoint cannot have an offset from its own line.",
        )
        existing = existing_offset(sketch, command.point_id, command.line_id)
        if existing:
            return PreparedCommand(None, allocated, counter[0], (), existing)
        _require(isinstance(command.foot, PointSeed), "The perpendicular foot needs a seed.")
        foot = point(command.foot)
        segment = allocate("l", allocated, counter)
        record["lines"].append(
            {"id": segment, "start": foot, "end": command.point_id, "construction": True}
        )
        created.append(segment)
        for kind, refs, value in (
            ("point_on_line", [foot, command.line_id], None),
            ("perpendicular", [command.line_id, segment], None),
            (
                "distance",
                [foot, command.point_id],
                normalize_driver_input(command.value, "distance"),
            ),
        ):
            relation_id = allocate("r", allocated, counter)
            record["constraints"].append(
                {
                    "id": relation_id,
                    "kind": kind,
                    "refs": refs,
                    **({"value": value} if value is not None else {}),
                }
            )
            created.append(relation_id)
        record["op"] = "add_point_line_dimension"
    elif isinstance(command, AddRelation):
        from .unit_input import normalize_driver_input

        _require(type(command.refs) is tuple, "Relation references must be a typed tuple.")
        relation = {"kind": command.kind, "refs": list(command.refs)}
        if command.value is not None:
            relation["value"] = normalize_driver_input(command.value, command.kind)
        if command.target is not None:
            relation["target"] = _point(command.target)
        signature = _relation_signature(relation)
        for existing in sketch["constraints"]:
            if _relation_signature(existing) == signature:
                return PreparedCommand(None, allocated, counter[0], (), existing["id"])
        relation_id = allocate("r", allocated, counter)
        record["constraints"].append({"id": relation_id, **relation})
        created.append(relation_id)
    elif isinstance(command, MovePoint):
        _require(type(command.preserve_constraints) is bool, "Invalid point movement mode.")
        record = {
            "op": "drag_point" if command.preserve_constraints else "move_point",
            "point_id": command.point_id,
            "target": _point(command.target),
        }
    elif isinstance(command, SetConstruction):
        _require(
            type(command.targets) is tuple and type(command.construction) is bool,
            "Construction needs typed targets and an explicit boolean.",
        )
        record = {
            "op": "construction",
            "targets": [list(pair) for pair in command.targets],
            "construction": command.construction,
        }
    elif isinstance(command, EditFixedTarget):
        record = {
            "op": "fixed_target",
            "constraint_id": command.constraint_id,
            "target": _point(command.target),
        }
    elif isinstance(command, DeleteBatch):
        plan = command.preview
        _require(
            isinstance(plan, DeletePreview) and plan.revision == revision,
            "The deletion preview is stale; review the current cascade again.",
        )
        _require(
            plan
            == deletion_preview(sketch, revision, plan.targets, journal_version=journal_version),
            "The deletion cascade differs from its preview.",
        )
        targets, removed = _delete_sets(sketch, plan.targets, journal_version=journal_version)
        seeds = None
        if plan.requires_solution:
            _require(
                release_seeds is not None,
                "Check the current sketch successfully before releasing constraints; the draft is retained.",
            )
            seeds = copy.deepcopy(release_seeds)
        record = {
            "op": "delete_v3" if sketch["schema_version"] == 3 else "delete",
            "targets": [list(item) for item in targets],
            "removed": removed,
            "seeds": seeds,
        }
    elif isinstance(command, RecoverRemoveRelation):
        plan = command.preview
        _require(
            type(plan) is DeletePreview
            and type(plan.revision) is int
            and plan.revision == revision,
            "The recovery preview is stale; review the current relation again.",
        )
        _require(
            type(plan.targets) is tuple
            and len(plan.targets) == 1
            and type(plan.targets[0]) is tuple
            and len(plan.targets[0]) == 2
            and plan.targets[0][0] == "constraint"
            and plan.points == plan.lines == plan.circles == plan.arcs == ()
            and plan.constraints == (plan.targets[0][1],),
            "Recovery removes exactly one selected relation and no geometry.",
        )
        _require(
            plan
            == deletion_preview(sketch, revision, plan.targets, journal_version=journal_version),
            "The recovery deletion differs from its current preview.",
        )
        _require(release_seeds is None, "Recovery accepts only current authored positions.")
        targets, removed = _delete_sets(sketch, plan.targets, journal_version=journal_version)
        # The persisted delete operation already means an explicit seed transition
        # followed by deletion. It records intent, not where its seeds came from.
        # Preserve numeric types, order and exact authored values without solving.
        record = {
            "op": "delete_v3" if sketch["schema_version"] == 3 else "delete",
            "targets": [list(item) for item in targets],
            "removed": removed,
            "seeds": {
                "points": [
                    {key: point[key] for key in ("id", "u", "v")} for point in sketch["points"]
                ],
                "circles": [
                    {key: circle[key] for key in ("id", "radius")}
                    for circle in sketch.get("circles", [])
                ],
            },
        }
    else:
        raise DraftError("Unsupported typed sketch command.")
    if journal_version == ARC_JOURNAL_VERSION:
        _apply_record(sketch, record, journal_version=journal_version)
    return PreparedCommand(record, allocated, counter[0], tuple(created), relation_id)


def _relation_signature(relation):
    refs = relation.get("refs")
    _require(type(refs) is list, "Relation references must be a list.")
    for reference in refs:
        _identifier(reference)
    kind = relation.get("kind")
    _require(type(kind) is str, "Relation kind must be text.")
    refs = canonical_refs(kind, refs)
    value, target = relation.get("value"), relation.get("target")
    _require(type(value) in (int, float, str, type(None)), "Invalid relation source value.")
    # Equal numeric values compare equal without changing their stored type.
    # Formula strings remain exact: no evaluation/algebraic inference here.
    return kind, tuple(refs), value, None if target is None else tuple(target)


def deletion_preview(sketch, revision, targets, *, journal_version=JOURNAL_VERSION):
    normalized, removed = _delete_sets(sketch, targets, journal_version=journal_version)
    return DeletePreview(
        revision,
        normalized,
        *(tuple(removed[name]) for name in _COLLECTION.values()),
        arcs=tuple(removed.get("arcs", ())),
    )
