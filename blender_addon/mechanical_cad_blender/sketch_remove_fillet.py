"""Explicit corner restoration; no inferred history and no deletion cascade."""

import copy

from .fillet_intent import CornerFilletIntent, validate_structure
from .general_sketch_commands import _identifier, _json, _keys, _require, _validate_sketch
from .request_contracts import snapshot_request


def make_record(sketch, arc_id):
    _identifier(arc_id)
    _validate_sketch(sketch, journal_version=3)
    arcs = {a["id"]: a for a in sketch.get("arcs", [])}
    _require(arc_id in arcs and "fillet_intent" in arcs[arc_id],
             "Select one arc with explicit Sketch Fillet intent.")
    arc = arcs[arc_id]
    points = {p["id"]: p for p in sketch["points"]}
    lines = {line["id"]: line for line in sketch["lines"]}
    intent = validate_structure(arc, points, lines, sketch["constraints"], arcs)
    private = {arc[role] for role in ("center", "start", "end")}
    removed = private | {arc_id}
    signatures = {("radius", (arc_id,))}
    signatures.update(("tangent", (arc_id, line)) for line in intent.lines)
    signatures.update(("point_on_line", (intent.corner, line)) for line in intent.lines)
    relations = [r for r in sketch["constraints"]
                 if (r["kind"], tuple(r["refs"])) in signatures]
    required = {r["id"] for r in relations}
    allowed = set()
    for line_id, neighbor in zip(intent.lines, intent.neighbors, strict=True):
        if neighbor is not None:
            peer = arcs[neighbor]["fillet_intent"]
            allowed.update({("tangent", (neighbor, line_id)),
                            ("point_on_line", (peer["corner"], line_id))})
    for relation in sketch["constraints"]:
        if relation["id"] in required:
            continue
        _require(not removed.intersection(relation["refs"]),
                 "Remove Fillet refused: an extra relation uses its arc or private points. Release it explicitly first.")
        _require(not set(intent.lines).intersection(relation["refs"])
                 or relation["kind"] in {"horizontal", "vertical"}
                 or (relation["kind"], tuple(relation["refs"])) in allowed,
                 "Remove Fillet refused: a supporting-line relation may change meaning. Release it explicitly first.")
    for collection in ("lines", "circles", "arcs"):
        for curve in sketch.get(collection, []):
            if curve["id"] in {arc_id, *intent.lines}:
                continue
            _require(not private.intersection(curve.get(role) for role in ("center", "start", "end")),
                     "Remove Fillet refused: another curve uses a private fillet point.")
            if "fillet_intent" in curve:
                other = curve["fillet_intent"]
                _require(not removed.intersection([other["corner"], *other["outer"]]),
                         "Remove Fillet refused: another fillet retains one of its private points.")
    updates = []
    for line_id, tangent in zip(intent.lines, (arc["start"], arc["end"]), strict=True):
        before = lines[line_id]
        after = copy.deepcopy(before)
        after["start" if before["start"] == tangent else "end"] = intent.corner
        updates.append({"before": copy.deepcopy(before), "after": after})
    peers = []
    for line_id, neighbor in zip(intent.lines, intent.neighbors, strict=True):
        if neighbor is None:
            continue
        before = arcs[neighbor]["fillet_intent"]
        after = copy.deepcopy(before)
        after["neighbors"][after["lines"].index(line_id)] = None
        peers.append({"arc_id": neighbor, "before": copy.deepcopy(before), "after": after})
    return {"op": "remove_corner_fillet", "arc_id": arc_id,
            "arc": copy.deepcopy(arc),
            "points": [copy.deepcopy(p) for p in sketch["points"] if p["id"] in private],
            "constraints": copy.deepcopy(relations), "line_updates": updates,
            "peer_updates": peers, "source_schema_version": sketch["schema_version"]}


def _exact_types(value, expected):
    """Validate every nested field before equality, without JSON coercion."""
    _require(type(value) is type(expected), "Remove Fillet record has an incorrect field type.")
    if type(expected) is dict:
        _keys(value, expected)
        for key in expected:
            _exact_types(value[key], expected[key])
    elif type(expected) is list:
        _require(len(value) == len(expected), "Remove Fillet record has an incorrect array length.")
        for item, reference in zip(value, expected, strict=True):
            _exact_types(item, reference)


def apply_record(sketch, command):
    command = snapshot_request(command)
    _keys(command, {"op", "arc_id", "arc", "points", "constraints", "line_updates",
                    "peer_updates", "source_schema_version"})
    _require(type(command["source_schema_version"]) is int, "Invalid source sketch version.")
    _require(type(command["arc"]) is dict and "fillet_intent" in command["arc"],
             "Remove Fillet requires complete explicit arc intent.")
    CornerFilletIntent.from_dict(command["arc"]["fillet_intent"])
    _require(type(command["peer_updates"]) is list, "Invalid peer updates.")
    for update in command["peer_updates"]:
        _keys(update, {"arc_id", "before", "after"})
        CornerFilletIntent.from_dict(update["before"])
        CornerFilletIntent.from_dict(update["after"])
    expected = make_record(sketch, command["arc_id"])
    _exact_types(command, expected)
    # Canonical JSON compares exact JSON types too: True != 1 != 1.0. The expected
    # nested records derive only from strictly validated input, never tool text.
    _require(_json(command) == _json(expected),
             "Remove Fillet command differs from its exact current construction and replacements.")
    for update in expected["line_updates"]:
        line = next(line for line in sketch["lines"] if line["id"] == update["before"]["id"])
        line.clear()
        line.update(copy.deepcopy(update["after"]))
    for update in expected["peer_updates"]:
        peer = next(a for a in sketch["arcs"] if a["id"] == update["arc_id"])
        peer["fillet_intent"] = copy.deepcopy(update["after"])
    for collection in ("points", "constraints"):
        ids = {r["id"] for r in expected[collection]}
        sketch[collection] = [r for r in sketch[collection] if r["id"] not in ids]
    sketch["arcs"] = [a for a in sketch["arcs"] if a["id"] != command["arc_id"]]


def validate_annotation_attachments(authoring, arc_id):
    """Retain the required radius placement, refuse other removed-source labels.

    Line reference measurements keep their explicit identity and recompute. A
    required radius placement is explicitly retired in bounded UI metadata,
    so Undo/Resume can restore its exact placement and display mode.
    """
    record = make_record(authoring.command_draft.sketch, arc_id)
    private = {p["id"] for p in record["points"]} | {arc_id}
    radius = next(r for r in record["constraints"] if r["kind"] == "radius")
    for identifier, binding in authoring.annotations.items():
        if not private.intersection(binding["refs"]):
            continue
        _require(identifier == radius["id"] and binding.get("role") is None
                 and binding["kind"] == "radius" and binding["refs"] == radius["refs"],
                 "Remove Fillet refused: a reference annotation uses the arc or its private points. Remove that annotation explicitly first.")
    return record


def retain_removal_ui(authoring, record):
    """Retire only the command's required radius, retaining exact label data."""
    from .annotation_retirement import mark_retired

    radius = next(r for r in record["constraints"] if r["kind"] == "radius")
    annotations = authoring.annotations
    binding = annotations.get(radius["id"])
    if binding is not None:
        _require(binding["kind"] == "radius" and binding["refs"] == radius["refs"]
                 and binding.get("role") is None, "Retirement requires the exact removed radius.")
        annotations[radius["id"]] = mark_retired(binding)
        authoring._update(annotations=annotations)
    removed = {record["arc_id"], *(p["id"] for p in record["points"]),
               *(r["id"] for r in record["constraints"])}
    authoring.discard_selection(tuple((r["kind"], r["id"]) for r in authoring.selection
                                      if r["id"] in removed))


def restore_removal_ui(authoring, record):
    """Undo the matching retirement marker, not user-hidden or unrelated labels."""
    radius = next(r for r in record["constraints"] if r["kind"] == "radius")
    annotations = authoring.annotations
    binding = annotations.get(radius["id"])
    if binding is not None and "retirement" in binding:
        _require(binding["kind"] == "radius" and binding["refs"] == radius["refs"],
                 "Restoration requires the exact removed radius.")
        del binding["retirement"]
        authoring._update(annotations=annotations)
