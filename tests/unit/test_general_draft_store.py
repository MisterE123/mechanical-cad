"""Strict independent UI snapshot kind, exact base, and unverified journal Resume."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_general_store_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
s = importlib.import_module(PACKAGE + ".general_draft_store")
legacy = importlib.import_module(PACKAGE + ".draft_store")


def draft():
    base = '{"schema_version":1, "id":"doc", "name":"Part", "units":"mm", "parameters":{}, "features":[], "active_feature":null}\n'
    result = d.GeneralSketchDraft(base)
    _, circle = result.execute(d.AddCircle(d.PointSeed(2, 3), 4)).entity_ids
    result.execute(d.AddRelation("radius", (circle,), value=4.123456789123456))
    return result


def roundtrip(value):
    return s.restore(s.dumps(value), value.document_json)


def test_snapshot_kind_version_roundtrip_and_local_history_are_independent():
    original = draft()
    original.undo()
    restored = roundtrip(original)
    assert restored.checkpoint_payload() == original.checkpoint_payload()
    assert restored.document_json.endswith("\n") and restored.can_redo
    assert not restored.has_current_solution and not restored.has_verified_trial
    restored.redo()
    original.redo()
    assert restored.candidate() == original.candidate()
    envelope = json.loads(s.dumps(original))
    assert envelope["kind"] == "general_sketch_ui_draft" and envelope["schema_version"] == 1
    with pytest.raises(legacy.SnapshotError, match="kind"):
        legacy.loads(s.dumps(original))


@pytest.mark.parametrize(
    "raw", ["", " \t ", "unknown + (", "1e309", "NaN", " 4.123456789123456 \n", "radius × 2 🛠"]
)
def test_invalid_pending_raw_and_exact_source_type_survive_without_autoaccept(raw):
    original = draft()
    driver = original.sketch["constraints"][0]["id"]
    original.begin_edit(driver)
    original.update_edit(raw)
    before = original.candidate()
    restored = roundtrip(original)
    assert restored.pending_edit.raw_text == raw
    assert restored.pending_edit.source == 4.123456789123456
    assert type(restored.pending_edit.source) is float
    assert restored.candidate() == before
    assert not restored.has_verified_trial and not restored.has_current_solution
    with pytest.raises(d.DraftError, match="Check this exact"):
        restored.accept_edit()


def test_fresh_restore_drops_all_runtime_evidence_and_queued_accept_state():
    original = draft()
    original._solution = d._Solution(
        original.revision, None, d._json(original.candidate()), "[]", "[]"
    )
    driver = original.sketch["constraints"][0]["id"]
    original.begin_edit(driver)
    original._trial_solution = d._Solution(
        original.revision, 0, d._json(original.trial_candidate()), "[]", "[]"
    )
    encoded = s.dumps(original)
    assert all(
        word not in encoded
        for word in (
            "solver_report",
            "remaining_dof",
            "validated_json",
            "input_fingerprint",
            "_solution",
            "queued_accept",
        )
    )
    restored = s.restore(encoded, original.document_json)
    assert not restored.has_current_solution and not restored.has_verified_trial
    assert restored.pending_edit.input_revision == 0


def test_stale_even_whitespace_only_base_retains_original_snapshot():
    original = draft()
    encoded = s.dumps(original)
    before = encoded
    with pytest.raises(s.SnapshotError, match="different committed document"):
        s.restore(encoded, original.document_json + " ")
    assert encoded == before
    assert s.restore(encoded, original.document_json).candidate() == original.candidate()


def test_undo_branch_ids_remain_reserved_across_fresh_resume():
    original = draft()
    original.undo()
    original.undo()
    allocated = set(original._allocated_ids)
    restored = roundtrip(original)
    result = restored.execute(d.AddCircle(d.PointSeed(2, 3), 4))
    assert not allocated.intersection(result.entity_ids)
    assert not restored.can_redo
    assert roundtrip(restored).checkpoint_payload() == restored.checkpoint_payload()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.update(schema_version=True),
        lambda e: e.update(schema_version=2),
        lambda e: e.update(kind="rectangle_ui_draft"),
        lambda e: e.update(base_sha256="forged"),
        lambda e: e["draft"].update(solver_report={"status": "okay"}),
        lambda e: e["draft"].update(validated_json="{}"),
        lambda e: e["draft"].update(gesture_token="native-pointer"),
        lambda e: e["draft"].update(next_id=1),
        lambda e: e["draft"].update(allocated_ids=[]),
        lambda e: e["draft"].update(revision=0),
        lambda e: e["draft"].update(is_edit=1),
        lambda e: e["draft"]["journal"].update(schema_version=True),
        lambda e: e["draft"]["journal"].update(cursor=99),
        lambda e: e["draft"]["journal"]["entries"][0].update(sequence=2),
        lambda e: e["draft"]["journal"]["entries"][1]["before"]["points"][0].update(u=123),
        lambda e: e["draft"]["journal"]["entries"][1]["after"]["points"][0].update(u=123),
        lambda e: e["draft"]["journal"]["entries"][0]["command"].update(solved={"okay": True}),
        lambda e: e["draft"]["accepted_sketch"]["points"][0].update(u=123),
        lambda e: e["draft"]["journal"]["anchor"].update(id="forged"),
    ],
)
def test_unknown_fields_forged_evidence_and_broken_journal_fail_closed(mutate):
    encoded = json.loads(s.dumps(draft()))
    mutate(encoded)
    raw = json.dumps(encoded)
    before = raw
    with pytest.raises(s.SnapshotError):
        s.loads(raw)
    assert raw == before


def test_pending_binding_cannot_be_retargeted_or_autoqueued():
    original = draft()
    original.begin_edit(original.sketch["constraints"][0]["id"])
    for mutate in [
        lambda p: p.update(constraint_id="missing"),
        lambda p: p.update(source=99),
        lambda p: p.update(refs=["other"]),
        lambda p: p.update(base_revision=0),
        lambda p: p.update(queued_accept=True),
        lambda p: p.update(input_revision=True),
    ]:
        envelope = json.loads(s.dumps(original))
        mutate(envelope["draft"]["pending_edit"])
        with pytest.raises(s.SnapshotError):
            s.loads(json.dumps(envelope))


@pytest.mark.parametrize(
    "raw", ['{"kind":1,"kind":2}', '{"value":NaN}', "[" * 33 + "0" + "]" * 33, "{} junk"]
)
def test_duplicate_nonfinite_deep_and_malformed_json_is_rejected(raw):
    with pytest.raises(s.SnapshotError):
        s.loads(raw)


def test_snapshot_and_expanded_journal_have_separate_budgets(monkeypatch):
    original = draft()
    encoded = s.dumps(original)
    monkeypatch.setattr(s, "MAX_SNAPSHOT_BYTES", len(encoded.encode()) - 1)
    with pytest.raises(s.SnapshotError):
        s.loads(encoded)
    monkeypatch.setattr(s, "MAX_SNAPSHOT_BYTES", 8 * 1024 * 1024)
    envelope = json.loads(encoded)
    entries_bytes = len(d._json(envelope["draft"]["journal"]["entries"]).encode())
    monkeypatch.setattr(d, "MAX_JOURNAL_BYTES", entries_bytes - 1)
    with pytest.raises(s.SnapshotError, match="Expanded local journal"):
        s.loads(encoded)


def test_suspended_external_history_never_reinterprets_or_rebases_base():
    original = draft()
    raw = s.dumps(original)
    document = json.loads(original.document_json)
    document["name"] = "Unrelated rename"
    with pytest.raises(s.SnapshotError):
        s.restore(raw, json.dumps(document))
    assert s.loads(raw)["document_json"] == original.document_json


def test_snapshot_sources_are_not_aliases_of_mutable_caller_data():
    original = draft()
    state = s.loads(s.dumps(original))
    retained = copy.deepcopy(state)
    restored = d.GeneralSketchDraft.from_checkpoint_payload(state)
    state["accepted_sketch"]["points"][0]["u"] = 99
    state["journal"]["entries"][0]["after"]["points"][0]["u"] = 99
    assert restored.checkpoint_payload() == retained


def test_pruned_history_cannot_reintroduce_a_deleted_generated_identity():
    value = draft()
    for index in range(36):
        added = value.execute(d.AddPoint(d.PointSeed(index, 0))).entity_ids[0]
        if index == 0:
            retired = added
        if index < 35:
            value.execute(d.DeleteBatch(value.preview_delete((("point", added),))))
    state = value.checkpoint_payload()
    assert state["journal"]["anchor_sequence"] > 0
    last = state["journal"]["entries"][-1]
    last["command"]["points"][0]["id"] = retired
    for sketch in (last["after"], state["accepted_sketch"]):
        next(item for item in sketch["points"] if item["id"] == added)["id"] = retired
    with pytest.raises(d.DraftError, match="allocation provenance"):
        d.GeneralSketchDraft.from_checkpoint_payload(state)


def test_pruned_history_keeps_all_original_identities_reserved(monkeypatch):
    original = draft().candidate()
    original["features"][0]["sketch"]["points"].append({"id": "p_d900", "u": 2, "v": 0})
    value = d.GeneralSketchDraft(json.dumps(original), original["features"][0]["id"], True)
    monkeypatch.setattr(d, "MAX_JOURNAL_ENTRIES", 2)
    value.execute(d.DeleteBatch(value.preview_delete((("point", "p_d900"),))))
    for index in range(4):
        added = value.execute(d.AddPoint(d.PointSeed(index, 1))).entity_ids[0]
    state = value.checkpoint_payload()
    assert "p_d900" not in {item["id"] for item in state["journal"]["anchor"]["points"]}
    last = state["journal"]["entries"][-1]
    last["command"]["points"][0]["id"] = "p_d900"
    for sketch in (last["after"], state["accepted_sketch"]):
        next(item for item in sketch["points"] if item["id"] == added)["id"] = "p_d900"
    with pytest.raises(d.DraftError):
        d.GeneralSketchDraft.from_checkpoint_payload(state)


def test_allocation_watermarks_preserve_pruning_branch_gaps_and_redo(monkeypatch):
    value = draft()
    monkeypatch.setattr(d, "MAX_JOURNAL_ENTRIES", 3)
    for index in range(6):
        value.execute(d.AddPoint(d.PointSeed(index, 0)))
    value.undo()
    value.undo()
    retired = set(value._allocated_ids)
    value.execute(d.AddPoint(d.PointSeed(10, 0)))
    state = value.checkpoint_payload()
    entries = state["journal"]["entries"]
    assert entries[-1]["allocation_before"] > entries[-2]["allocation_after"]
    assert entries[-1]["after"]["points"][-1]["id"] not in retired
    value.undo()
    resumed = roundtrip(value)
    assert resumed.can_redo and resumed.checkpoint_payload() == value.checkpoint_payload()
    resumed.redo()
    value.redo()
    assert resumed.checkpoint_payload() == value.checkpoint_payload()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state["journal"].update(schema_version=1),
        lambda state: state["journal"].pop("anchor_next_id"),
        lambda state: state["journal"].update(anchor_next_id=2),
        lambda state: state["journal"]["entries"][0].update(allocation_before=0),
        lambda state: state["journal"]["entries"][0].update(allocation_after=1),
        lambda state: state["journal"]["entries"][1].update(allocation_before=1),
        lambda state: state["journal"]["entries"][1].update(allocation_after=2**53),
    ],
)
def test_old_or_corrupt_allocation_provenance_fails_closed(mutate):
    value = draft()
    envelope = json.loads(s.dumps(value))
    mutate(envelope["draft"])
    raw = json.dumps(envelope)
    with pytest.raises(s.SnapshotError):
        s.loads(raw)
    assert json.loads(raw) == envelope
