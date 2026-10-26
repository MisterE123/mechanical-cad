"""Raw diameter intent and atomic circle commands, without native solver claims."""
import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

PACKAGE = "mcad_pending_circle_diameter_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
a, c, d, p, s, g = [importlib.import_module(PACKAGE + "." + name) for name in (
    "general_authoring", "general_sketch_commands", "general_sketch_draft",
    "pending_circle_diameter", "draft_dispatch", "general_view_geometry")]
BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}'


def state(raw=" 2.5 cm "):
    result = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))
    result.begin_circle(c.PointSeed(1, 2), 7)
    result.begin_pending_diameter({}, raw_text=raw)
    return result


def test_raw_suspend_restore_cancel_is_exact_and_not_solver_evidence():
    original = state("  unfinished + 😃  ")
    original.update_pending_diameter(" 2.5 cm ")
    before, proposal = original.command_draft.checkpoint_payload(), original.proposal
    saved = s.dumps(original)
    loaded = s.restore(saved, BASE)
    assert s.dumps(loaded) == saved
    assert loaded.pending_diameter["raw_text"] == " 2.5 cm "
    assert loaded.pending_diameter["input_revision"] == 1
    assert s.inspect(saved).phase == "CIRCLE_DIAMETER_EDIT"
    assert s.inspect(saved).pending_input
    assert loaded.command_draft.pending_edit is None
    assert not loaded.command_draft.has_current_solution
    copied = loaded.pending_diameter
    copied["center_position"][0] = 99
    assert loaded.pending_diameter["center_position"] == [1, 2]
    assert loaded.cancel_pending_diameter()
    assert not loaded.cancel_pending_diameter()
    assert loaded.proposal == proposal
    assert loaded.command_draft.checkpoint_payload() == before
    assert "pending_diameter" not in loaded.ui_payload()


@pytest.mark.parametrize("raw,value", [("5", 5), (" 2.5 cm ", 25), ("1 in", 25.4), ("2e-6", 2e-6), ("1000000 mm", 1e6)])
def test_literal_parser(raw, value):
    assert p.parse_diameter(raw) == value


@pytest.mark.parametrize("raw", ["", "0", "-1", "nan", "inf", "1e309", "1e-6", "1e7", "width", "2+3", "2 * mm", "0x20", "1_000", "3 deg", "10 mm + 2 mm"])
def test_invalid_literals_retain_exact_raw(raw):
    original = state(raw)
    before = s.dumps(original)
    with pytest.raises(c.DraftError):
        p.prepare_diameter_candidate(original)
    assert s.dumps(original) == before


@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("schema_version", True), ("center_position", [9, 3]),
    ("center_position", [True, 2]), ("raw_text", 5), ("input_revision", -1),
    ("input_revision", True), ("solver_evidence", {}), ("token", "lease"),
])
def test_strict_raw_snapshot_rejects_tampering(field, value):
    payload = json.loads(s.dumps(state()))
    payload["ui"]["pending_diameter"][field] = value
    with pytest.raises(s.SnapshotError):
        s.restore(json.dumps(payload), BASE)


def test_original_proposal_and_other_ui_are_immutable_while_pending():
    original = state()
    before = s.dumps(original)
    for op in (lambda: original.update_circle(8), lambda: original.select_tool("Line"),
               lambda: original.begin_line(c.PointSeed(0, 0)), lambda: original.resume_proposal()):
        with pytest.raises(c.DraftError):
            op()
        assert s.dumps(original) == before
    payload = json.loads(before)
    payload["ui"]["proposal"]["radius"] = 99
    with pytest.raises(s.SnapshotError):
        s.restore(json.dumps(payload), BASE)
    original.cancel_proposal()
    assert original.pending_diameter is None and original.proposal is None


def test_detached_candidate_has_canonical_radius_and_diameter_annotation_roundtrip():
    original = state("2 cm")
    before = s.dumps(original)
    candidate, receipt = p.prepare_diameter_candidate(original)
    assert s.dumps(original) == before
    assert candidate.pending_diameter is None and candidate.proposal is None
    sketch = candidate.command_draft.sketch
    circle, relation = sketch["circles"][0], sketch["constraints"][0]
    assert circle["radius"] == relation["value"] == 10
    assert relation["kind"] == "radius" and relation["refs"] == [circle["id"]]
    placement = candidate.annotations[receipt.constraint_id]
    assert placement == {"kind": "radius", "refs": [circle["id"]], "display": "diameter", "offset": [0, 12]}
    annotation = g.annotation_geometry(g.build_geometry(sketch, source="authored"), receipt.constraint_id, placement)
    assert annotation.kind == "diameter" and annotation.value == 10
    assert annotation.anchors_mm == ((1, 2), (1, 12))
    candidate = s.restore(s.dumps(candidate), BASE)
    candidate.command_draft.undo()
    assert not candidate.command_draft.sketch.get("circles", [])
    assert candidate.annotations[receipt.constraint_id] == placement
    candidate = s.restore(s.dumps(candidate), BASE)
    candidate.command_draft.redo()
    assert candidate.command_draft.sketch == sketch
    assert candidate.annotations[receipt.constraint_id] == placement


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("reuse", [False, True])
def test_atomic_command_undo_redo_restore(version, reuse):
    commands = d.GeneralSketchDraft(BASE, journal_version=version)
    center = c.PointSeed(1, 2)
    if reuse:
        center = c.PointRef(commands.execute(c.AddPoint(center)).entity_ids[0])
    before = commands.sketch
    receipt = commands.execute(c.AddDiameterCircle(center, 14))
    expected = commands.sketch
    assert len(receipt.entity_ids) == (2 if reuse else 3)
    assert receipt.constraint_id == expected["constraints"][0]["id"]
    assert expected["constraints"][0]["kind"] == "radius"
    payload = commands.checkpoint_payload()
    assert payload["journal"]["entries"][-1]["command"]["op"] == "add_diameter_circle"
    assert len(payload["journal"]["entries"]) == (2 if reuse else 1)
    commands.undo()
    assert commands.sketch == before
    commands = d.GeneralSketchDraft.from_checkpoint_payload(commands.checkpoint_payload(), expected_journal_version=version)
    commands.redo()
    assert commands.sketch == expected


@pytest.mark.parametrize("value", [True, False, "5", "2+3", None, 0, -1, 1e-6, 1e7, float("inf"), float("nan")])
def test_invalid_command_is_atomic(value):
    commands = d.GeneralSketchDraft(BASE)
    before = commands.checkpoint_payload()
    with pytest.raises(c.DraftError):
        commands.execute(c.AddDiameterCircle(c.PointSeed(0, 0), value))
    assert commands.checkpoint_payload() == before


@pytest.mark.parametrize("mutate", [
    lambda r: r["constraints"][0].update(value="5"),
    lambda r: r["constraints"][0].update(value=True),
    lambda r: r["constraints"][0].update(value=0),
    lambda r: r["constraints"][0].update(value=6),
    lambda r: r["constraints"][0].update(kind="distance"),
    lambda r: r["constraints"][0].update(refs=[r["points"][0]["id"]]),
    lambda r: r["points"].append({"id": "extra", "u": 8, "v": 9}),
    lambda r: r["circles"][0].update(construction=True),
    lambda r: r.update(op="add"),
    lambda r: r["constraints"].append(copy.deepcopy(r["constraints"][0])),
])
def test_malformed_compound_record_is_refused(mutate):
    commands = d.GeneralSketchDraft(BASE)
    commands.execute(c.AddDiameterCircle(c.PointSeed(0, 0), 10))
    entry = commands.checkpoint_payload()["journal"]["entries"][0]
    record = copy.deepcopy(entry["command"])
    mutate(record)
    with pytest.raises(c.DraftError):
        c._apply_record(entry["before"], record)


def test_legacy_circle_stays_radius_only_and_without_extension():
    commands = d.GeneralSketchDraft(BASE)
    commands.execute(c.AddCircle(c.PointSeed(0, 0), 5))
    assert not commands.sketch["constraints"]
    assert commands.checkpoint_payload()["journal"]["entries"][0]["command"]["op"] == "add"
    authoring = a.GeneralSketchAuthoringState(commands)
    saved = s.dumps(authoring)
    assert "pending_diameter" not in json.loads(saved)["ui"]
    assert s.dumps(s.restore(saved, BASE)) == saved


@pytest.mark.parametrize(
    "raw",
    [None, True, 7, "\ud800", "😃" * (c.MAX_RAW_TEXT_BYTES // 4 + 1)],
    ids=["none", "boolean", "integer", "invalid-surrogate", "utf8-over-byte-budget"],
)
def test_invalid_raw_updates_are_atomic(raw):
    original = state()
    before = s.dumps(original)
    with pytest.raises(c.DraftError):
        original.update_pending_diameter(raw)
    assert s.dumps(original) == before


def test_arc_capable_snapshot_retains_diameter_without_other_behavior_change():
    original = state().promote_arc_capability()
    restored = s.restore(s.dumps(original), BASE)
    assert restored.ui_version == a.ARC_UI_VERSION
    assert restored.pending_diameter == original.pending_diameter
    restored.cancel_proposal()
    restored.begin_arc(c.PointSeed(0, 0))
    assert restored.pending_diameter is None


def test_local_recovery_roundtrip_retains_exact_raw_without_runtime_authority():
    recovery = importlib.import_module(PACKAGE + ".recovery_store")
    original = state("  incomplete + 😃 \n")
    saved = s.dumps(original)
    encoded = recovery.encode("a" * 32, 1, BASE, saved, "2026-10-25T00:00:00Z")
    record = recovery.decode(encoded)
    assert record.document_json == BASE and record.draft_json == saved
    restored = s.restore(record.draft_json, record.document_json)
    assert restored.pending_diameter["raw_text"] == "  incomplete + 😃 \n"
    assert set(restored.pending_diameter) == {"schema_version", "original_proposal", "center_position", "raw_text", "input_revision"}
    assert not restored.command_draft.has_current_solution
    assert restored.command_draft.pending_edit is None


@pytest.mark.parametrize("field,value", [("schema_version", True), ("center_position", [9, 9]), ("owner_token", "fake"), ("guarded_evidence", {"ok": True})])
def test_local_recovery_rejects_malformed_diameter_intent(field, value):
    recovery = importlib.import_module(PACKAGE + ".recovery_store")
    payload = json.loads(s.dumps(state()))
    payload["ui"]["pending_diameter"][field] = value
    with pytest.raises(recovery.RecoveryError):
        recovery.encode("a" * 32, 1, BASE, json.dumps(payload), "2026-10-25T00:00:00Z")


@pytest.mark.parametrize("raw", ["0", "1e-7", "1e-6"])
def test_rejected_subminimum_values_report_the_actual_diameter_bound(raw):
    with pytest.raises(c.DraftError, match="0.000002"):
        p.parse_diameter(raw)


def test_formula_guidance_is_concise_and_names_the_existing_editor():
    with pytest.raises(c.DraftError) as failure:
        p.parse_diameter("2+3")
    assert str(failure.value) == "Use a number or unit. Add formulas later with Dimension."


def test_fractional_diameter_recovery_correction_halves_once_and_roundtrips():
    recovery = importlib.import_module(PACKAGE + ".recovery_store")
    original = state(" 1/0 in ")
    saved = s.dumps(original)
    with pytest.raises(c.DraftError, match="denominator"):
        p.prepare_diameter_candidate(original)
    assert s.dumps(original) == saved
    record = recovery.decode(recovery.encode("a" * 32, 1, BASE, saved, "2026-10-25T00:00:00Z"))
    restored = s.restore(record.draft_json, record.document_json)
    assert restored.pending_diameter["raw_text"] == " 1/0 in "
    assert not restored.command_draft.has_current_solution
    restored.update_pending_diameter(" 1/8 in ")
    before = s.dumps(restored)
    candidate, receipt = p.prepare_diameter_candidate(restored)
    assert s.dumps(restored) == before
    assert p.parse_diameter("1/8 in") == 3.175
    sketch = candidate.command_draft.sketch
    assert sketch["circles"][0]["radius"] == sketch["constraints"][0]["value"] == 1.5875
    assert candidate.annotations[receipt.constraint_id]["display"] == "diameter"
    assert not candidate.command_draft.has_current_solution
    candidate = s.restore(s.dumps(candidate), BASE)
    assert candidate.command_draft.sketch == sketch
    candidate.command_draft.undo()
    assert candidate.command_draft.sketch == original.command_draft.sketch
    candidate.command_draft.redo()
    assert candidate.command_draft.sketch == sketch


@pytest.mark.parametrize("raw", ["1/2", "-1/8 in", "1/1000000 mm", "1000001/1 mm"])
def test_fraction_keeps_diameter_literal_and_field_bounds(raw):
    with pytest.raises(c.DraftError):
        p.parse_diameter(raw)
