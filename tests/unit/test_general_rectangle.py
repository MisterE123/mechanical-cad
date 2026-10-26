"""Rectangle intent, proposal cancellation, strict history and workplane preservation."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

PACKAGE = "mcad_rectangle_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
a = importlib.import_module(PACKAGE + ".general_authoring")
p = importlib.import_module(PACKAGE + ".general_proposals")
s = importlib.import_module(PACKAGE + ".draft_dispatch")


def blank():
    return json.dumps(
        {
            "schema_version": 1,
            "id": "part",
            "name": "Part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
    )


def test_rectangle_atomic_history_and_explicit_intent():
    draft = d.GeneralSketchDraft(blank())
    before = draft.sketch
    receipt = draft.execute(d.AddRectangle(d.PointSeed(10, 7), d.PointSeed(-2, -3)))
    accepted = draft.sketch
    assert len(receipt.entity_ids) == 12
    assert len(accepted["points"]) == len(accepted["lines"]) == len(accepted["constraints"]) == 4
    assert [c["kind"] for c in accepted["constraints"]] == ["horizontal", "vertical"] * 2
    assert [line["end"] for line in accepted["lines"]] == [
        line["start"] for line in accepted["lines"][1:] + accepted["lines"][:1]
    ]
    draft.undo()
    assert draft.sketch == before
    restored = d.GeneralSketchDraft.from_checkpoint_payload(draft.checkpoint_payload())
    restored.redo()
    assert restored.sketch == accepted
    assert len(restored.checkpoint_payload()["journal"]["entries"]) == 1


@pytest.mark.parametrize("opposite", [(0, 3), (5, 0), (1e-7, 4), (float("nan"), 4)])
def test_invalid_rectangle_leaves_ids_and_history_unchanged(opposite):
    draft = d.GeneralSketchDraft(blank())
    before = draft.checkpoint_payload()
    with pytest.raises(d.DraftError):
        draft.execute(d.AddRectangle(d.PointSeed(0, 0), d.PointSeed(*opposite)))
    assert draft.checkpoint_payload() == before


def test_rectangle_proposal_resume_cancel_accept_and_stale_replacement():
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(blank()))
    state.select_tool("Rectangle")
    state.begin_rectangle(d.PointSeed(2, 3))
    state.update_rectangle((12, 8))
    restored = s.restore(s.dumps(state), blank())
    assert restored.proposal == state.proposal
    assert restored.command_draft.sketch["lines"] == []
    cancelled = s.clone(restored)
    cancelled.cancel_proposal()
    assert cancelled.command_draft.sketch["lines"] == []
    prepared = p.prepare_proposal(restored)
    accepted = prepared.replacement(restored)
    assert accepted.proposal is None and len(accepted.command_draft.sketch["lines"]) == 4
    restored.update_rectangle((13, 8))
    with pytest.raises(d.DraftError, match="changed"):
        prepared.replacement(restored)


@pytest.mark.parametrize("corrupt", ["open_loop", "relation", "seed"])
def test_checkpoint_rejects_rectangle_semantic_tampering(corrupt):
    draft = d.GeneralSketchDraft(blank())
    draft.execute(d.AddRectangle(d.PointSeed(0, 0), d.PointSeed(12, 8)))
    payload = copy.deepcopy(draft.checkpoint_payload())
    record = payload["journal"]["entries"][0]["command"]
    if corrupt == "open_loop":
        record["lines"][-1]["end"] = record["points"][1]["id"]
    elif corrupt == "relation":
        record["constraints"][0]["kind"] = "vertical"
    else:
        record["points"][1]["v"] = 2
    with pytest.raises(d.DraftError):
        d.GeneralSketchDraft.from_checkpoint_payload(payload)
