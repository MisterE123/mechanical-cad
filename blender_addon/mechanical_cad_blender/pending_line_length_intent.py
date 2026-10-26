"""Versioned raw Line-length intent, never solver evidence or an input lease.

Saved intent captures a direction once. Parsing and command preparation are
explicit, detached operations; a caller still owns fresh solve/placement guards.

The optional UI field is omitted when inactive, preserving old snapshot bytes.
Older strict readers reject snapshots containing this extension instead of
silently dropping pending text; its own version is checked independently.
"""

from __future__ import annotations

import copy
import math
import re

from .general_sketch_commands import (
    MAX_RAW_TEXT_BYTES,
    DraftError,
    PointRef,
    _integer,
    _keys,
    _point,
    _require,
)
from .unit_input import normalize_unit_input

VERSION = 1
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
FORMULA_HELP = "Enter a numeric length or unit literal. For formulas, create the line first, then use Dimension."


def validate_raw(raw):
    _require(type(raw) is str, "Line length input must be text.")
    try:
        size = len(raw.encode("utf-8"))
    except UnicodeError as exc:
        raise DraftError("Line length input must be valid Unicode.") from exc
    _require(size <= MAX_RAW_TEXT_BYTES, "Line length input exceeds its byte limit.")
    return raw


def parse_length(raw):
    """One numeric/unit literal only; never evaluate arithmetic or names."""
    validate_raw(raw)
    try:
        normalized = normalize_unit_input(raw, "length")
    except ValueError as exc:
        raise DraftError(f"{exc} {FORMULA_HELP}") from exc
    if type(normalized) is str:
        _require(_NUMBER.fullmatch(normalized.strip()) is not None, FORMULA_HELP)
        normalized = float(normalized)
    _require(
        type(normalized) in (int, float)
        and math.isfinite(normalized)
        and 1e-6 <= normalized <= 1e6,
        "Line length must be between 0.000001 and 1,000,000 mm.",
    )
    return normalized


def validate_pending(intent, proposal, bindings):
    from .general_authoring_anchors import _validate_anchor

    _keys(
        intent,
        {
            "schema_version",
            "original_proposal",
            "anchor_position",
            "endpoint",
            "endpoint_position",
            "direction",
            "axis",
            "raw_text",
            "input_revision",
        },
    )
    _require(
        type(intent["schema_version"]) is int and intent["schema_version"] == VERSION,
        "Unsupported pending Line-length version.",
    )
    _require(
        proposal is not None
        and proposal.get("kind") == "line"
        and intent["original_proposal"] == proposal,
        "Pending Line length must retain its exact original proposal.",
    )
    for field in ("anchor_position", "endpoint_position", "direction"):
        _require(type(intent[field]) is list, "Expected stored Line-length coordinates.")
    _point(intent["anchor_position"])
    _point(intent["endpoint_position"])
    _validate_anchor(intent["endpoint"], bindings)
    for anchor, position in (
        (proposal["anchor"], intent["anchor_position"]),
        (intent["endpoint"], intent["endpoint_position"]),
    ):
        if anchor["kind"] == "new":
            _require(anchor["position"] == position, "Captured new-point position changed.")
    direction = _point(intent["direction"])
    _require(abs(math.hypot(*direction) - 1) <= 1e-12, "Line direction must be unit length.")
    dx, dy = (intent["endpoint_position"][i] - intent["anchor_position"][i] for i in (0, 1))
    magnitude = math.hypot(dx, dy)
    _require(magnitude >= 1e-6, "Choose a nonzero Line direction before entering length.")
    _require(
        all(abs(direction[i] - (dx, dy)[i] / magnitude) <= 1e-12 for i in (0, 1)),
        "Captured Line direction does not match the chosen endpoint.",
    )
    axis = intent["axis"]
    _require(
        axis is None or type(axis) is str and axis in {"horizontal", "vertical"},
        "Unsupported pending Line axis.",
    )
    if axis is not None:
        _require(
            abs(direction[1 if axis == "horizontal" else 0]) <= 1e-12,
            "Chosen Line endpoint is off axis.",
        )
    validate_raw(intent["raw_text"])
    _integer(intent["input_revision"])


def begin_intent(state, endpoint, points, *, axis=None, raw_text=""):
    from .general_authoring_anchors import _anchor_payload
    from .line_axis import anchor_position, point_position

    proposal = state.resume_proposal()
    _require(proposal["kind"] == "line", "No unfinished Line proposal.")
    start = _point(anchor_position(proposal, points))
    if type(endpoint) is PointRef:
        state.existing_point(endpoint.id)
    end = _point(point_position(endpoint, points))
    delta = [end[i] - start[i] for i in (0, 1)]
    magnitude = math.hypot(*delta)
    _require(magnitude >= 1e-6, "Choose a nonzero Line direction before entering length.")
    return {
        "schema_version": VERSION,
        "original_proposal": copy.deepcopy(proposal),
        "anchor_position": start,
        "endpoint": _anchor_payload(endpoint),
        "endpoint_position": end,
        "direction": [value / magnitude for value in delta],
        "axis": axis,
        "raw_text": validate_raw(raw_text),
        "input_revision": 0,
    }
