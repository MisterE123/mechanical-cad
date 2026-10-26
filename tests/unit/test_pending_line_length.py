"""Raw pending Line-length persistence and detached command preparation."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_pending_line_length_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
a = importlib.import_module(PACKAGE + ".general_authoring")
c = importlib.import_module(PACKAGE + ".general_sketch_commands")
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
p = importlib.import_module(PACKAGE + ".pending_line_length")
s = importlib.import_module(PACKAGE + ".draft_dispatch")
BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}'


def state():
    result = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))
    result.begin_line(c.PointSeed(1, 2), (4, 6))
    return result


def test_raw_suspend_restore_cancel_and_original_proposal_exact():
    original = state()
    before, proposal = original.command_draft.checkpoint_payload(), original.proposal
    original.begin_pending_length(c.PointSeed(4, 6), {}, raw_text="  bad formula + 😃 ")
    original.update_pending_length("  2.5 cm  ")
    saved = s.dumps(original)
    loaded = s.restore(saved, BASE)
    assert loaded.pending_length["raw_text"] == "  2.5 cm  "
    assert loaded.pending_length["input_revision"] == 1
    assert loaded.command_draft.checkpoint_payload() == before
    assert loaded.proposal == proposal
    assert s.inspect(saved).phase == "LINE_LENGTH_EDIT"
    assert s.inspect(saved).pending_input
    assert loaded.command_draft.pending_edit is None
    assert not loaded.command_draft.has_current_solution
    pending = loaded.pending_length
    pending["direction"][0] = 900
    assert loaded.pending_length["direction"] == [0.6, 0.8]
    assert loaded.cancel_pending_length()
    assert not loaded.cancel_pending_length()
    assert loaded.proposal == proposal
    assert "pending_length" not in loaded.ui_payload()
    assert loaded.command_draft.checkpoint_payload() == before


def test_proposal_cancel_clears_both_and_no_other_ui_mutation_while_pending():
    original = state()
    original.begin_pending_length(c.PointSeed(4, 6), {})
    before = s.dumps(original)
    for operation in (
        lambda: original.update_line((9, 7)),
        lambda: original.select_tool("Circle"),
        lambda: original.begin_circle(c.PointSeed(0, 0)),
    ):
        with pytest.raises(c.DraftError):
            operation()
        assert s.dumps(original) == before
    original.cancel_proposal()
    assert original.pending_length is None and original.proposal is None


@pytest.mark.parametrize(
    "raw,value", [("5", 5), (" 2.5 cm ", 25), ("1 in", 25.4), ("1e-6", 1e-6), ("1000000 mm", 1e6)]
)
def test_literal_parser(raw, value):
    assert p.parse_length(raw) == value


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "0",
        "-1",
        "nan",
        "inf",
        "1e309",
        "1e-7",
        "1e7",
        "width",
        "2+3",
        "2 * mm",
        "0x20",
        "1_000",
        "3 deg",
        "10 mm + 2 mm",
    ],
)
def test_invalid_parser_retains_exact_raw(raw):
    original = state()
    original.begin_pending_length(c.PointSeed(4, 6), {}, raw_text=raw)
    before = s.dumps(original)
    with pytest.raises(c.DraftError):
        p.prepare_length_candidate(original)
    assert s.dumps(original) == before


def test_detached_candidate_creates_seed_distance_annotation_and_single_undo():
    original = state()
    original.begin_pending_length(c.PointSeed(4, 6), {}, raw_text="2 cm")
    before = s.dumps(original)
    staged, result = p.prepare_length_candidate(original)
    assert s.dumps(original) == before
    assert staged.pending_length is None and staged.proposal is None
    endpoint = staged.command_draft.sketch["points"][-1]
    assert [endpoint["u"], endpoint["v"]] == [13, 18]
    constraint = next(
        x for x in staged.command_draft.sketch["constraints"] if x["id"] == result.constraint_id
    )
    assert constraint["kind"] == "distance" and constraint["value"] == 20
    assert staged.annotations[result.constraint_id]["offset"] == [0, 12]
    assert staged.command_draft.revision == original.command_draft.revision + 1
    assert not staged.command_draft.has_current_solution
    staged.command_draft.undo()
    assert staged.command_draft.sketch == original.command_draft.sketch


def test_reused_endpoint_exact_identity_and_incompatible_length_rejected():
    draft = d.GeneralSketchDraft(BASE)
    result = draft.execute(c.AddLine(c.PointSeed(0, 0), c.PointSeed(3, 4)))
    start, end = result.entity_ids[:2]
    original = a.GeneralSketchAuthoringState(draft)
    original.begin_line(c.PointRef(start), (3, 4))
    original.begin_pending_length(c.PointRef(end), {start: [0, 0], end: [3, 4]}, raw_text="6")
    with pytest.raises(c.DraftError, match="reused endpoint"):
        p.prepare_length_candidate(original)
    original.update_pending_length("5")
    staged, result = p.prepare_length_candidate(original)
    assert staged.command_draft.sketch["points"] == draft.sketch["points"]
    assert staged.command_draft.sketch["lines"][-1]["start"] == start
    assert staged.command_draft.sketch["lines"][-1]["end"] == end


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("direction", [1, 1]),
        ("axis", "diagonal"),
        ("anchor_position", [2, 3]),
        ("input_revision", -1),
    ],
)
def test_strict_pending_schema_rejects_tamper(field, value):
    original = state()
    original.begin_pending_length(c.PointSeed(4, 6), {})
    payload = json.loads(s.dumps(original))
    payload["ui"]["pending_length"][field] = value
    with pytest.raises(s.SnapshotError):
        s.restore(json.dumps(payload), BASE)


def test_no_extension_in_legacy_snapshot_and_unknown_fields_rejected():
    original = state()
    before = s.dumps(original)
    assert "pending_length" not in json.loads(before)["ui"]
    assert s.dumps(s.restore(before, BASE)) == before
    original.begin_pending_length(c.PointSeed(4, 6), {})
    payload = json.loads(s.dumps(original))
    payload["ui"]["pending_length"]["solver_evidence"] = {}
    with pytest.raises(s.SnapshotError):
        s.restore(json.dumps(payload), BASE)
    ui = copy.deepcopy(original.ui_payload())
    ui["proposal"]["endpoint"] = [99, 88]
    with pytest.raises(c.DraftError, match="original proposal"):
        a.GeneralSketchAuthoringState(original.command_draft, ui)


@pytest.mark.parametrize(
    "axis,end,direction", [("horizontal", (-9, 2), [-1, 0]), ("vertical", (1, -8), [0, -1])]
)
def test_axis_intent_preserved_in_single_candidate(axis, end, direction):
    original = state()
    original.begin_pending_length(c.PointSeed(*end), {}, axis=axis, raw_text="3")
    assert original.pending_length["direction"] == direction
    staged, _ = p.prepare_length_candidate(original)
    kinds = [item["kind"] for item in staged.command_draft.sketch["constraints"]]
    assert set(kinds) == {axis, "distance"} and len(kinds) == 2


def test_arc_capability_retains_raw_pending_and_no_other_arc_behavior_changes():
    original = state().promote_arc_capability()
    original.begin_pending_length(c.PointSeed(4, 6), {}, raw_text="unfinished +")
    restored = s.restore(s.dumps(original), BASE)
    assert restored.ui_version == a.ARC_UI_VERSION
    assert restored.pending_length == original.pending_length
    restored.cancel_proposal()
    restored.begin_arc(c.PointSeed(0, 0))
    assert restored.pending_length is None


def test_zero_direction_or_off_axis_never_starts_field():
    original = state()
    before = s.dumps(original)
    with pytest.raises(c.DraftError, match="nonzero"):
        original.begin_pending_length(c.PointSeed(1, 2), {})
    with pytest.raises(c.DraftError, match="off axis"):
        original.begin_pending_length(c.PointSeed(4, 6), {}, axis="horizontal")
    assert s.dumps(original) == before


def test_fractional_length_recovery_correction_candidate_roundtrip_and_undo():
    recovery = importlib.import_module(PACKAGE + ".recovery_store")
    original = state()
    original.begin_pending_length(c.PointSeed(4, 6), {}, raw_text=" 1/0 in ")
    saved = s.dumps(original)
    with pytest.raises(c.DraftError, match="denominator"):
        p.prepare_length_candidate(original)
    assert s.dumps(original) == saved
    record = recovery.decode(recovery.encode("a" * 32, 1, BASE, saved, "2026-10-25T00:00:00Z"))
    restored = s.restore(record.draft_json, record.document_json)
    assert restored.pending_length["raw_text"] == " 1/0 in "
    assert not restored.command_draft.has_current_solution
    restored.update_pending_length(" 1/8 in ")
    before = s.dumps(restored)
    staged, _ = p.prepare_length_candidate(restored)
    assert s.dumps(restored) == before
    sketch = staged.command_draft.sketch
    assert sketch["constraints"][0]["value"] == 3.175
    assert [sketch["points"][-1][key] for key in ("u", "v")] == pytest.approx([2.905, 4.54])
    assert not staged.command_draft.has_current_solution
    staged = s.restore(s.dumps(staged), BASE)
    assert staged.command_draft.sketch == sketch
    staged.command_draft.undo()
    assert staged.command_draft.sketch == original.command_draft.sketch
    staged.command_draft.redo()
    assert staged.command_draft.sketch == sketch


@pytest.mark.parametrize("raw", ["1/2", "-1/8 in", "1/999999999 mm", "1000001/1 mm"])
def test_fraction_keeps_pending_literal_and_field_bounds(raw):
    with pytest.raises(c.DraftError):
        p.parse_length(raw)
