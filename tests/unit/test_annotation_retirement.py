"""Retirement is bounded presentation intent, not missing-binding forgiveness."""

import copy
import json

import pytest
from test_arc_overlay_geometry import overlay as overlay_fixture
from test_general_view_geometry import geometry, projection
from test_remove_fillet_owner import c, load, rounded
from test_remove_fillet_owner import host as owner_host

host = owner_host
overlay = overlay_fixture

retirement = load("annotation_retirement")
layout = load("sketch_annotation_store")
removal = load("sketch_remove_fillet")


def removed(host, monkeypatch):
    arc, radius = rounded(host, monkeypatch)
    draft = host.owner.draft
    original = draft.annotations
    record = removal.make_record(draft.command_draft.sketch, arc["id"])
    draft.command_draft.execute(c.RemoveCornerFillet(arc["id"]))
    removal.retain_removal_ui(draft, record)
    return draft, radius["id"], original, record


def test_finish_layout_reopen_retains_exact_data_without_history(host, monkeypatch):
    draft, identifier, original, _ = removed(host, monkeypatch)
    raw = layout.replace_annotations("", "doc", draft.feature_id, draft.annotations)
    assert json.loads(raw)["schema_version"] == 2
    lookup = layout.annotations_for(raw, "doc", draft.feature_id, draft.command_draft.sketch)
    assert lookup.unavailable[identifier].state == "retired"
    assert lookup.annotations == {}
    assert lookup.all_annotations[identifier] == retirement.mark_retired(original[identifier])
    assert layout.replace_annotations(raw, "doc", draft.feature_id, lookup.all_annotations) == raw
    # Finish discards the local journal. A new editor must still retain the label.
    authoring = load("general_authoring")
    commands = load("general_sketch_draft").GeneralSketchDraft(
        json.dumps(draft.candidate()), draft.feature_id, True, journal_version=3)
    ui = authoring.empty_ui(ui_version=2)
    ui["annotations"] = lookup.all_annotations
    reopened = authoring.GeneralSketchAuthoringState(commands, ui, ui_version=2)
    assert reopened.annotations == draft.annotations
    assert reopened.status.annotations[0].state == "retired"
    assert not reopened.status.conflicts and not reopened.display_annotations
    assert reopened.command_draft.sketch == draft.command_draft.sketch


def test_retirement_only_changes_presentation_and_undo_restores_exact_label(host, monkeypatch):
    draft, identifier, original, record = removed(host, monkeypatch)
    after = draft.command_draft.checkpoint_payload()
    assert draft.status.annotations[0].state == "retired"
    assert draft.command_draft.checkpoint_payload() == after
    draft.command_draft.undo()
    # A marker cannot hide a now-existing identity, even an exact signature.
    assert draft.status.annotations[0].state == "changed"
    assert identifier in draft.display_annotations
    removal.restore_removal_ui(draft, record)
    assert draft.annotations == original and draft.status.annotations[0].available
    draft.remove_annotation(identifier)  # Explicit user hiding is not retirement.
    draft.command_draft.redo()
    removal.retain_removal_ui(draft, record)
    assert draft.annotations == {} and draft.status.annotations == ()


def test_unmarked_missing_and_reused_id_are_not_suppressed(host, monkeypatch):
    draft, identifier, original, _ = removed(host, monkeypatch)
    draft._update(annotations=original)
    assert draft.status.annotations[0].state == "missing"
    assert draft.status.conflicts and draft.display_annotations == original
    binding = retirement.mark_retired(original[identifier])
    for occupied in ({identifier}, set(binding["refs"])):
        assert retirement.retired_status(identifier, binding, occupied) == "changed"


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(kind="distance"),
    lambda b: b.update(display="angle"),
    lambda b: b.update(role="reference"),
    lambda b: b["retirement"].update(schema_version=True),
    lambda b: b["retirement"].update(schema_version=2),
    lambda b: b["retirement"].update(reason="delete"),
    lambda b: b["retirement"].update(extra=1),
    lambda b: b.update(offset=[float("nan"), 0]),
])
def test_strict_retirement_payload_and_atomic_layout_failure(mutation):
    binding = retirement.mark_retired({"kind": "radius", "refs": ["arc"],
                                       "display": "diameter", "offset": [-0.0, 1.25]})
    mutation(binding)
    before = copy.deepcopy(binding)
    with pytest.raises(ValueError):
        layout.replace_annotations("", "doc", "sketch", {"radius": binding})
    assert repr(binding) == repr(before)


def test_version_one_cannot_smuggle_retirement_and_ordinary_layout_stays_v1():
    binding = {"kind": "radius", "refs": ["arc"], "display": "radius", "offset": [0, 1]}
    old = layout.replace_annotations("", "doc", "sketch", {"radius": binding})
    assert json.loads(old)["schema_version"] == 1
    data = json.loads(old)
    data["documents"]["doc"]["sketch"]["radius"] = retirement.mark_retired(binding)
    with pytest.raises(ValueError, match="version 2"):
        layout.validate(json.dumps(data))


def test_presentation_never_dumps_or_replays_command_journal(host, monkeypatch):
    draft, identifier, _, _ = removed(host, monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError("Retirement drawing must not dump/replay history")
    monkeypatch.setattr(type(draft.command_draft), "checkpoint_payload", forbidden)
    assert draft.retired_annotation_ids == (identifier,)
    assert draft.display_annotations == {}


def test_retirement_plane_id_collision_is_a_real_conflict(host, monkeypatch):
    draft, identifier, _, _ = removed(host, monkeypatch)
    annotations = draft.annotations
    annotations[identifier]["refs"] = [draft.command_draft.sketch["plane"]["id"]]
    draft._update(annotations=annotations)
    assert draft.status.annotations[0].state == "changed"
    assert draft.status.conflicts and identifier in draft.display_annotations


def test_real_overlay_frame_omits_retired_only_not_missing(host, monkeypatch, overlay):
    draft, identifier, original, _ = removed(host, monkeypatch)
    current = geometry(draft.command_draft.sketch)
    frame = overlay.build_frame(current, projection, annotations=draft.display_annotations)
    assert not frame.unavailable
    draft._update(annotations=original)
    frame = overlay.build_frame(current, projection, annotations=draft.display_annotations)
    assert any(item.identifier == identifier for item in frame.unavailable)
