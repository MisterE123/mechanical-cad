"""Detached candidate preparation; pure pending-intent APIs remain reexported."""

from .general_sketch_commands import AddDiameterCircle, PointRef, PointSeed, _require
from .pending_circle_diameter_intent import VERSION as VERSION
from .pending_circle_diameter_intent import begin_intent as begin_intent
from .pending_circle_diameter_intent import parse_diameter as parse_diameter
from .pending_circle_diameter_intent import validate_pending as validate_pending


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
