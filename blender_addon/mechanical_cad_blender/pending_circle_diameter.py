"""Data-only unfinished Circle diameter intent; no native authority or input lease."""

import copy

from .general_sketch_commands import (
    AddDiameterCircle,
    DraftError,
    PointRef,
    PointSeed,
    _integer,
    _keys,
    _point,
    _require,
)
from .pending_line_length import FORMULA_HELP, parse_length, validate_raw

VERSION = 1


def parse_diameter(raw):
    try:
        value = parse_length(raw)
    except DraftError as exc:
        raise DraftError(
            str(exc)
            .replace(FORMULA_HELP, "Use a number or unit. Add formulas later with Dimension.")
            .replace("Line length", "Circle diameter")
            .replace("line first", "circle first")
            .replace("numeric length", "numeric diameter")
            .replace("0.000001", "0.000002")
        ) from exc
    _require(value >= 2e-6, "Circle diameter must be between 0.000002 and 1,000,000 mm.")
    return value


def validate_pending(intent, proposal, bindings):
    _keys(
        intent,
        {"schema_version", "original_proposal", "center_position", "raw_text", "input_revision"},
    )
    _require(
        type(intent["schema_version"]) is int and intent["schema_version"] == VERSION,
        "Unsupported pending Circle-diameter version.",
    )
    _require(
        proposal is not None
        and proposal.get("kind") == "circle"
        and intent["original_proposal"] == proposal,
        "Pending Circle diameter must retain its exact original proposal.",
    )
    _require(type(intent["center_position"]) is list, "Expected stored center coordinates.")
    _point(intent["center_position"])
    if proposal["anchor"]["kind"] == "new":
        _require(
            proposal["anchor"]["position"] == intent["center_position"], "Captured center changed."
        )
    validate_raw(intent["raw_text"])
    _integer(intent["input_revision"])


def begin_intent(state, points, *, raw_text=""):
    from .line_axis import anchor_position

    proposal = state.resume_proposal()
    _require(
        proposal["kind"] == "circle" and state.tool == "Circle", "No unfinished Circle proposal."
    )
    return {
        "schema_version": VERSION,
        "original_proposal": copy.deepcopy(proposal),
        "center_position": _point(anchor_position(proposal, points)),
        "raw_text": validate_raw(raw_text),
        "input_revision": 0,
    }


def prepare_diameter_candidate(state):
    from .draft_dispatch import clone

    intent = state.pending_diameter
    _require(intent is not None, "No pending Circle diameter.")
    diameter = parse_diameter(intent["raw_text"])
    anchor = intent["original_proposal"]["anchor"]
    center = (
        PointRef(anchor["point_id"])
        if anchor["kind"] == "existing"
        else PointSeed(*intent["center_position"])
    )
    staged = clone(state)
    result = staged.command_draft.execute(AddDiameterCircle(center, diameter))
    staged.cancel_proposal()
    staged.place_annotation(result.constraint_id, (0, 12), display="diameter")
    return staged, result
