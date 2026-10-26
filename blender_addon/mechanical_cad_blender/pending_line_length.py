"""Detached candidate preparation; pure pending-intent APIs remain reexported."""

import math

from .general_sketch_commands import AddLengthLine, PointRef, PointSeed, _point, _require
from .pending_line_length_intent import _NUMBER as _NUMBER
from .pending_line_length_intent import FORMULA_HELP as FORMULA_HELP
from .pending_line_length_intent import VERSION as VERSION
from .pending_line_length_intent import begin_intent as begin_intent
from .pending_line_length_intent import parse_length as parse_length
from .pending_line_length_intent import validate_pending as validate_pending
from .pending_line_length_intent import validate_raw as validate_raw


def prepare_length_candidate(state):
    """Return (detached authoring state, command result), without live mutation.

    References stay references. In particular an incompatible reused endpoint is
    rejected, never moved to make a requested length fit. Fresh solve evidence and
    checks of every captured existing position remain the accepting owner's duty.
    """
    from .draft_dispatch import clone

    intent = state.pending_length
    _require(intent is not None, "No pending Line length.")
    length = parse_length(intent["raw_text"])
    start_payload = intent["original_proposal"]["anchor"]
    start = (
        PointRef(start_payload["point_id"])
        if start_payload["kind"] == "existing"
        else PointSeed(*intent["anchor_position"])
    )
    endpoint = intent["endpoint"]
    if endpoint["kind"] == "existing":
        observed_length = math.dist(intent["anchor_position"], intent["endpoint_position"])
        _require(
            math.isclose(observed_length, length, rel_tol=1e-10, abs_tol=1e-8),
            "The reused endpoint does not match this length. Choose a new endpoint or use Dimension after creation.",
        )
        end = PointRef(endpoint["point_id"])
    else:
        position = _point(
            [intent["anchor_position"][i] + length * intent["direction"][i] for i in (0, 1)]
        )
        end = PointSeed(*position)
    staged = clone(state)
    result = staged.command_draft.execute(AddLengthLine(start, end, length, intent["axis"]))
    staged.cancel_proposal()
    if result.constraint_id is not None:
        staged.place_annotation(result.constraint_id, (0, 12))
    return staged, result
