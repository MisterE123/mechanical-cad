"""Pure UI-intent contracts; no native/UI execution or solved-geometry claims."""

import hashlib
import importlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_general_authoring_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
a = importlib.import_module(PACKAGE + ".general_authoring")
s = importlib.import_module(PACKAGE + ".general_authoring_store")
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
v1 = importlib.import_module(PACKAGE + ".general_draft_store")
BASE = '{"schema_version":1, "id":"doc", "name":"Part 🛠", "units":"mm", "parameters":{"radius":"4 + 0.125"}, "features":[], "active_feature":null}\n'


def authoring():
    command = d.GeneralSketchDraft(BASE)
    p, q, line = command.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(3, 4))).entity_ids
    center, circle = command.execute(d.AddCircle(d.PointSeed(8, 2), 4.125)).entity_ids
    distance = command.execute(d.AddRelation("distance", (p, q), value=5)).constraint_id
    radius = command.execute(d.AddRelation("radius", (circle,), value="radius")).constraint_id
    return a.GeneralSketchAuthoringState(command), (p, q, line, center, circle, distance, radius)


def checkpoint(state):
    return state.command_draft.checkpoint_payload(), state.ui_payload()


def roundtrip(state):
    return s.restore(s.dumps(state), state.document_json)


def test_explicit_v1_editor_defaults_unchanged_checkpoint_and_exact_base():
    original, _ = authoring()
    command = original.command_draft
    before = v1.dumps(command)
    state = a.GeneralSketchAuthoringState.from_v1_draft(command)
    assert state.ui_payload() == a.empty_ui()
    assert state.command_draft.checkpoint_payload() == command.checkpoint_payload()
    assert state.document_json == BASE and state.feature_id == command.feature_id
    assert state.base_hash == hashlib.sha256(BASE.encode()).hexdigest()
    assert state.revision == command.revision and state.ui_revision == 0
    assert state.is_edit is False
    assert v1.dumps(command) == before
    assert json.loads(s.dumps(state))["draft"] == json.loads(before)["draft"]
    assert s.loads(s.dumps(state))["ui"] == a.empty_ui()
    with pytest.raises(d.DraftError, match="exact original"):
        state.require_current(BASE + " ")
    state.require_current(BASE)


def test_line_and_circle_begin_observe_continue_cancel_are_ui_only():
    state, ids = authoring()
    before = state.command_draft.checkpoint_payload()
    candidate = d._json(state.candidate())
    assert state.begin_line(d.PointRef(ids[0]))
    assert state.tool == "Line" and state.proposal["endpoint"] is None
    assert state.update_line((0, 0))  # An unfinished observation may have zero length.
    assert state.resume_proposal() == state.proposal
    assert state.status.proposal.available and not state.status.conflicts
    assert state.cancel_proposal()
    assert not state.cancel_proposal()
    assert state.begin_circle(d.PointSeed(1, 2), 0)
    assert state.tool == "Circle" and state.proposal["radius"] == 0
    assert state.update_circle(4.123456789123456)
    assert state.proposal["radius"] == 4.123456789123456
    assert state.cancel_proposal()
    assert state.command_draft.checkpoint_payload() == before
    assert d._json(state.candidate()) == candidate
    assert state.revision == before["revision"] and state.ui_revision == 6


def test_saved_proposal_reopens_with_continue_cancel_and_no_replayed_command():
    state, ids = authoring()
    state.begin_line(d.PointRef(ids[1]), (30, -40))
    command_before, ui_before = checkpoint(state)
    restored = roundtrip(state)
    assert checkpoint(restored) == (command_before, ui_before)
    for _ in range(3):
        assert restored.resume_proposal() == ui_before["proposal"]
    assert checkpoint(restored) == (command_before, ui_before)
    assert restored.cancel_proposal()
    assert restored.command_draft.checkpoint_payload() == command_before
    assert len(restored.command_draft.sketch["lines"]) == 1
    assert not restored.command_draft.has_current_solution
    assert not restored.command_draft.has_verified_trial
    envelope = json.loads(s.dumps(state))
    assert set(envelope) == {"schema_version", "kind", "base_sha256", "draft", "ui"}
    assert set(envelope["ui"]) == {
        "schema_version",
        "revision",
        "tool",
        "selection",
        "proposal",
        "annotations",
    }
    assert set(envelope["ui"]["proposal"]) == {"kind", "anchor", "endpoint"}
    assert not any(
        key in s.dumps(state)
        for key in (
            "pointer_capture",
            "queuedEnter",
            "input_lease",
            "process_token",
            "gesture_grab",
        )
    )


@pytest.mark.parametrize("kind", ["line", "circle"])
def test_existing_anchor_deleted_and_undone_is_recoverable_and_exact(kind):
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))
    command = state.command_draft
    point, other, line = command.execute(d.AddLine(d.PointSeed(1, 1), d.PointSeed(3, 3))).entity_ids
    if kind == "line":
        state.begin_line(d.PointRef(point), (10, 10))
    else:
        state.begin_circle(d.PointRef(point), 3)
    state.select((("point", point), ("line", line)))
    observed = state.ui_payload()
    command.execute(d.DeleteBatch(command.preview_delete((("point", point),))))
    assert state.ui_payload() == observed
    assert state.status.proposal.state == "missing"
    assert [item.state for item in state.status.selection] == ["missing", "missing"]
    saved = roundtrip(state)
    with pytest.raises(d.DraftError, match="unavailable"):
        saved.resume_proposal()
    assert saved.ui_payload() == observed
    # Equal-coordinate replacement is a new ID and cannot heal the original binding.
    replacement = command.execute(d.AddPoint(d.PointSeed(1, 1))).entity_ids[0]
    assert replacement != point and state.status.proposal.state == "missing"
    command.undo()
    command.undo()
    assert state.status.proposal.available
    assert all(item.available for item in state.status.selection)
    assert state.resume_proposal()["anchor"]["point_id"] == point
    saved.command_draft.undo()
    assert saved.status.proposal.available
    assert saved.resume_proposal()["anchor"]["point_id"] == point
    assert other in {item["id"] for item in saved.command_draft.sketch["points"]}


def test_undo_of_anchor_creation_and_redo_do_not_drop_proposal():
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))
    point = state.command_draft.execute(d.AddPoint(d.PointSeed(1, 2))).entity_ids[0]
    state.begin_circle(d.PointRef(point), 3)
    state.command_draft.undo()
    resumed = roundtrip(state)
    assert resumed.status.proposal.state == "missing"
    resumed.command_draft.redo()
    assert resumed.status.proposal.available
    assert resumed.proposal == state.proposal


def test_radius_annotation_tracks_exact_relation_and_raw_formula_without_conversion():
    state, ids = authoring()
    radius = ids[-1]
    original = checkpoint(state)[0]
    state.place_annotation(radius, (2.5, -4))
    state.move_annotation(radius, (8, 12))
    assert state.annotations[radius] == {
        "kind": "radius",
        "refs": [ids[4]],
        "display": "radius",
        "offset": [8, 12],
    }
    assert state.command_draft.checkpoint_payload() == original
    assert state.command_draft.sketch["constraints"][-1]["value"] == "radius"
    state.command_draft.undo()  # Radius relation, keeping the circle.
    assert state.status.annotations[0].state == "missing"
    resumed = roundtrip(state)
    before = checkpoint(resumed)
    with pytest.raises(d.DraftError, match="unavailable"):
        resumed.move_annotation(radius, (0, 0))
    assert checkpoint(resumed) == before
    resumed.command_draft.redo()
    assert resumed.status.annotations[0].available
    assert resumed.annotations[radius]["refs"] == [ids[4]]
    assert resumed.command_draft.sketch["constraints"][-1]["value"] == "radius"
    resumed.remove_annotation(radius)
    assert not resumed.annotations
    assert state.annotations


def test_annotations_are_unavailable_after_deletion_and_available_after_exact_undo():
    state, ids = authoring()
    radius = ids[-1]
    state.place_annotation(radius, (1, 2))
    command = state.command_draft
    # Synthetic private evidence fixture only: exercise audited deletion state,
    # not native solve correctness, which belongs to existing integration tests.
    command._solution = d._Solution(
        command.revision,
        None,
        d._json(command.candidate()),
        d._json(command.sketch["points"]),
        d._json(
            [{key: item[key] for key in ("id", "radius")} for item in command.sketch["circles"]]
        ),
    )
    command.execute(d.DeleteBatch(command.preview_delete((("constraint", radius),))))
    assert state.status.annotations[0].state == "missing"
    resumed = roundtrip(state)
    resumed.command_draft.undo()
    assert resumed.status.annotations[0].available
    assert resumed.annotations[radius] == state.annotations[radius]


def test_pruned_or_abandoned_relation_binding_is_quarantined_not_reinvented(monkeypatch):
    state, ids = authoring()
    radius = ids[-1]
    state.place_annotation(radius, (1, 2))
    state.command_draft.undo()
    state.command_draft.execute(d.AddPoint(d.PointSeed(3, 9)))  # Drop its Redo branch.
    assert state.status.annotations[0].state == "unverified"
    restored = roundtrip(state)
    assert restored.annotations == state.annotations
    assert restored.status.annotations[0].state == "unverified"
    with pytest.raises(d.DraftError, match="unavailable"):
        restored.move_annotation(radius, (2, 4))
    restored.remove_annotation(radius)
    assert not restored.annotations
    # A stale point remains a stable reserved ID, even after retained history prunes.
    point = ids[3]
    state.begin_line(d.PointRef(point), (50, 50))
    state.command_draft.undo()
    state.command_draft.undo()  # Undo distance relation.
    state.command_draft.undo()  # Undo circle and its center.
    monkeypatch.setattr(d, "MAX_JOURNAL_ENTRIES", 1)
    state.command_draft.execute(d.AddPoint(d.PointSeed(3, 9)))
    state.command_draft.execute(d.AddPoint(d.PointSeed(4, 9)))
    assert roundtrip(state).status.proposal.state == "missing"


def test_ui_operations_preserve_command_hash_history_and_current_evidence():
    state, ids = authoring()
    command = state.command_draft
    evidence = d._Solution(command.revision, None, d._json(command.candidate()), "[]", "[]")
    command._solution = evidence
    before = command.checkpoint_payload()
    digest = hashlib.sha256(d._json(command.candidate()).encode()).hexdigest()
    for tool in ("Line", "Circle", "Dimension", "Select"):
        state.select_tool(tool)
    state.select((("line", ids[2]), ("circle", ids[4])))
    state.place_annotation(ids[-2], (2, 3))
    state.place_annotation(ids[-1], (4, 5))
    state.move_annotation(ids[-2], (7, 8))
    state.begin_circle(d.PointSeed(9, 1), 2)
    state.cancel_proposal()
    assert command.checkpoint_payload() == before
    assert command._solution is evidence and command.has_current_solution
    assert hashlib.sha256(d._json(command.candidate()).encode()).hexdigest() == digest
    resumed = roundtrip(state)
    assert not resumed.command_draft.has_current_solution
    assert resumed.command_draft.checkpoint_payload() == before


@pytest.mark.parametrize(
    "raw", ["", " \t ", "radius + (", "NaN", "1e999", " 9.12345678912345 \n", "半径 × 2 🛠"]
)
def test_pending_invalid_raw_driver_text_survives_with_ui_and_without_autoaccept(raw):
    state, ids = authoring()
    state.place_annotation(ids[-1], (1, 2))
    state.begin_circle(d.PointRef(ids[3]), 4.125)
    state.command_draft.begin_edit(ids[-1])
    state.command_draft.update_edit(raw)
    before = checkpoint(state)
    resumed = roundtrip(state)
    assert checkpoint(resumed) == before
    assert resumed.command_draft.pending_edit.raw_text == raw
    assert resumed.command_draft.pending_edit.source == "radius"
    assert not resumed.command_draft.has_verified_trial
    with pytest.raises(d.DraftError, match="Check this exact"):
        resumed.command_draft.accept_edit()
    with pytest.raises(d.DraftError, match="driving field"):
        resumed.resume_proposal()
    resumed.command_draft.cancel_edit()
    assert resumed.resume_proposal()["radius"] == 4.125


@pytest.mark.parametrize(
    "action",
    [
        lambda x, ids: x.begin_line(d.PointRef("invented")),
        lambda x, ids: x.begin_line(d.PointRef(ids[2])),
        lambda x, ids: x.begin_line(d.PointSeed(float("nan"), 0)),
        lambda x, ids: x.begin_line(d.PointSeed(10**1000, 0)),
        lambda x, ids: x.begin_line(d.PointSeed(True, 0)),
        lambda x, ids: x.begin_line(d.PointSeed(0, 0), (1, float("inf"))),
        lambda x, ids: x.begin_circle(d.PointSeed(0, 0), -1),
        lambda x, ids: x.begin_circle(d.PointSeed(0, 0), 1e6 + 1),
        lambda x, ids: x.begin_circle(d.PointSeed(0, 0), True),
        lambda x, ids: x.begin_circle(d.PointSeed(0, 0), "radius"),
        lambda x, ids: x.select_tool("Arc"),
        lambda x, ids: x.select((("point", "invented"),)),
        lambda x, ids: x.select((("point", ids[0]), ("point", ids[0]))),
        lambda x, ids: x.select((("line", ids[0]),)),
        lambda x, ids: x.select([("point", ids[0])] * 33),
        lambda x, ids: x.place_annotation(ids[2], (0, 0)),
        lambda x, ids: x.place_annotation(ids[-1], (float("nan"), 0)),
        lambda x, ids: x.place_annotation(ids[-1], (0, 1e6 + 1)),
        lambda x, ids: x.remove_annotation(ids[-1]),
        lambda x, ids: x.resume_proposal(),
    ],
)
def test_invalid_ui_commands_leave_everything_unchanged(action):
    state, ids = authoring()
    before = checkpoint(state)
    with pytest.raises(d.DraftError):
        action(state, ids)
    assert checkpoint(state) == before


def test_invalid_proposal_updates_and_overwriting_are_atomic():
    state, ids = authoring()
    state.begin_line(d.PointRef(ids[0]), (3, 4))
    before = checkpoint(state)
    for action in [
        lambda: state.update_circle(4),
        lambda: state.update_line((True, 1)),
        lambda: state.begin_circle(d.PointSeed(0, 0), 1),
        lambda: state.begin_line(d.PointSeed(0, 0)),
    ]:
        with pytest.raises(d.DraftError):
            action()
        assert checkpoint(state) == before
    state.cancel_proposal()
    state.begin_circle(d.PointSeed(0, 0), 1)
    before = checkpoint(state)
    for value in [-1, float("nan"), float("inf"), True, "4", 10**1000]:
        with pytest.raises(d.DraftError):
            state.update_circle(value)
        assert checkpoint(state) == before


def test_ui_revision_exhaustion_preflights_every_change_and_allows_checked_noops():
    state, ids = authoring()
    state.begin_line(d.PointRef(ids[0]), (3, 4))
    state.place_annotation(ids[-1], (1, 2))
    ui = state.ui_payload()
    ui["revision"] = 2**53 - 1
    state = a.GeneralSketchAuthoringState(state.command_draft, ui)
    before = checkpoint(state)
    assert not state.select_tool("Line")
    assert not state.update_line((3, 4))
    assert not state.move_annotation(ids[-1], (1, 2))
    assert state.resume_proposal() == state.proposal
    for action in [
        lambda: state.select_tool("Select"),
        lambda: state.select((("line", ids[2]),)),
        lambda: state.cancel_proposal(),
        lambda: state.update_line((4, 5)),
        lambda: state.move_annotation(ids[-1], (2, 3)),
        lambda: state.remove_annotation(ids[-1]),
    ]:
        with pytest.raises(d.DraftError, match="UI revision"):
            action()
        assert checkpoint(state) == before
    assert roundtrip(state).ui_revision == 2**53 - 1


def test_inputs_and_observed_outputs_are_detached_from_caller_ownership():
    state, ids = authoring()
    ui = a.empty_ui()
    original = state.command_draft
    owner = a.GeneralSketchAuthoringState(original, ui)
    ui["tool"] = "Circle"
    original.execute(d.AddPoint(d.PointSeed(5, 8)))
    assert owner.tool == "Select" and owner.revision < original.revision
    owner.begin_line(d.PointRef(ids[0]), (1, 2))
    owner.place_annotation(ids[-1], (3, 4))
    owner.select((("point", ids[0]),))
    before = checkpoint(owner)
    for value in (owner.proposal, owner.resume_proposal()):
        value["anchor"]["point_id"] = "changed"
    owner.annotations[ids[-1]]["refs"].append("changed")
    owner.selection[0]["id"] = "changed"
    owner.ui_payload()["annotations"].clear()
    loaded = s.loads(s.dumps(owner))
    restored = s.restore(s.dumps(owner), BASE)
    loaded["draft"]["accepted_sketch"]["points"][0]["u"] = 888
    loaded["ui"]["annotations"].clear()
    assert checkpoint(restored) == before and checkpoint(owner) == before


def test_module_import_is_native_and_transport_free():
    script = f"""import importlib, sys, types
p = types.ModuleType("pure_ui")
p.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules["pure_ui"] = p
importlib.import_module("pure_ui.general_authoring_store")
assert not any(name == "bpy" or name.startswith(("OCP", "slvs")) for name in sys.modules)
assert "subprocess" not in sys.modules
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("kind", ["line", "circle"])
def test_boundary_coordinate_new_proposals_roundtrip_without_allocating_ids(kind):
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))
    before = state.command_draft.checkpoint_payload()
    if kind == "line":
        state.begin_line(d.PointSeed(-1e6, 1e6), (1e6, -1e6))
    else:
        state.begin_circle(d.PointSeed(-1e6, 1e6), 1e6)
    restored = roundtrip(state)
    assert restored.proposal == state.proposal
    assert restored.proposal["anchor"] == {"kind": "new", "position": [-1e6, 1e6]}
    assert restored.command_draft.checkpoint_payload() == before
    assert restored.status.proposal.available
    restored.cancel_proposal()
    assert restored.command_draft.checkpoint_payload() == before


def test_pending_driver_and_proposal_cancellation_are_independent():
    state, ids = authoring()
    state.begin_line(d.PointRef(ids[0]), (3, 4))
    state.command_draft.begin_edit(ids[-1])
    state.command_draft.update_edit("invalid +( \t")
    before = state.command_draft.checkpoint_payload()
    state.cancel_proposal()
    assert state.command_draft.checkpoint_payload() == before
    with pytest.raises(d.DraftError, match="driving field"):
        state.begin_circle(d.PointRef(ids[3]), 4)
    assert state.proposal is None


def test_discard_selected_relation_preserves_other_missing_ids_annotations_and_commands():
    state, ids = authoring()
    p, _q, _line, _center, _circle, distance, radius = ids
    state.select((("constraint", distance), ("constraint", radius), ("point", p)))
    state.place_annotation(radius, (20, 30))
    for identifier in (distance, radius):
        preview = state.command_draft.preview_delete((("constraint", identifier),))
        state.command_draft.execute(d.RecoverRemoveRelation(preview))
    before_command, before_ui = checkpoint(state)
    assert state.discard_selection((("constraint", radius),))
    assert state.selection == [{"kind": "constraint", "id": distance}, {"kind": "point", "id": p}]
    assert state.status.selection[0].state == "missing"
    assert state.annotations == before_ui["annotations"]
    assert state.ui_revision == before_ui["revision"] + 1
    assert state.command_draft.checkpoint_payload() == before_command
    assert not state.discard_selection((("constraint", radius),))
    assert state.ui_revision == before_ui["revision"] + 1
    assert checkpoint(roundtrip(state)) == checkpoint(state)


def test_discard_selection_failure_preserves_exact_ui_and_command_bytes():
    state, ids = authoring()
    state.select((("constraint", ids[-1]),))
    for targets in ((("constraint", "invented"),), (("line", ids[-1]),), "bad"):
        before = checkpoint(state)
        with pytest.raises(d.DraftError):
            state.discard_selection(targets)
        assert checkpoint(state) == before
    state._ui["revision"] = 2**53 - 1
    before = checkpoint(state)
    with pytest.raises(d.DraftError):
        state.discard_selection((("constraint", ids[-1]),))
    assert checkpoint(state) == before
