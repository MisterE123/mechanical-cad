"""Row launch uses explicit canonical identity without display/ownership mutation."""

import json
from types import SimpleNamespace

import pytest
from test_arc_gesture_owner import ROOT, load
from test_arc_gesture_owner import host as _host

host = _host


@pytest.fixture
def launch(host, monkeypatch):
    viewport = load("viewport_sketch")
    staged = load("staged_edit_store")
    host.lifecycle._ACTIVE = None
    host.context.mode = "OBJECT"
    host.state.repair_intent_json = ""
    host.state.feature_index = -1
    host.state.active_feature = "other"
    host.state.features = []
    doc = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
    host.state.document_json = json.dumps(doc)
    selected = next(f for f in doc["features"] if f["kind"] == "sketch_constrained")
    cls = viewport.MCAD_OT_edit_history_feature
    monkeypatch.setattr(cls, "poll_message_set", lambda message: None, raising=False)
    monkeypatch.setattr(staged, "require_none", lambda context: None)
    calls = []
    monkeypatch.setattr(viewport, "_begin_in_sketch", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(
        viewport.bpy, "ops", SimpleNamespace(mcad=SimpleNamespace(
            edit_solid_feature=lambda *a, **kw: calls.append((a, kw)) or {"RUNNING_MODAL"}
        )), raising=False,
    )
    op = cls()
    op.feature_id = selected["id"]
    return SimpleNamespace(host=host, viewport=viewport, staged=staged, op=op, calls=calls, doc=doc)


def test_exact_unselected_sketch_opens_without_selection_or_output_change(launch):
    h = launch.host
    before = vars(h.state).copy()
    assert launch.op.execute(h.context) == {"FINISHED"}
    assert launch.calls == [((h.context, launch.op.feature_id), {"editor": "mcad.rectangle_sketch"})]
    assert vars(h.state) == before


def test_solid_uses_existing_modal_and_exact_id(launch):
    feature = next(f for f in launch.doc["features"] if f["kind"] == "extrude")
    launch.op.feature_id = feature["id"]
    before = vars(launch.host.state).copy()
    assert launch.op.execute(launch.host.context) == {"FINISHED"}
    assert launch.calls == [(("INVOKE_DEFAULT",), {"feature_id": feature["id"]})]
    assert vars(launch.host.state) == before


@pytest.mark.parametrize("kind", ["import_step", "unknown_generated_kind"])
def test_uneditable_canonical_kind_never_routes_to_solid_or_sketch(launch, kind):
    feature = next(f for f in launch.doc["features"] if f["id"] == launch.op.feature_id)
    feature["kind"] = kind
    launch.host.state.document_json = json.dumps(launch.doc)
    assert launch.op.execute(launch.host.context) == {"CANCELLED"}
    assert not launch.calls


def test_removed_row_rejected(launch):
    launch.op.feature_id = "missing"
    assert launch.op.execute(launch.host.context) == {"CANCELLED"}
    assert not launch.calls


@pytest.mark.parametrize("owner", ["draft", "active", "replay", "lease", "staged", "saved", "resume"])
def test_existing_owner_not_replaced(launch, monkeypatch, owner):
    h, viewport, staged = launch.host, launch.viewport, launch.staged
    if owner == "draft":
        h.state.sketch_draft_json = "retained draft"
    elif owner == "active":
        h.lifecycle._ACTIVE = h.owner
    elif owner == "replay":
        monkeypatch.setattr(viewport.document_state, "_REPLAY_RUNNING", True)
    elif owner == "lease":
        monkeypatch.setattr(viewport.execution_lease, "is_busy", lambda: True)
    elif owner == "staged":
        monkeypatch.setattr(staged, "current", lambda context: object())
    elif owner == "saved":
        h.state.repair_intent_json = "retained repair"
    else:
        monkeypatch.setattr(staged, "resume_reserved", lambda: True)
    before = vars(h.state).copy()
    assert not launch.op.poll(h.context)
    assert launch.op.execute(h.context) == {"CANCELLED"}
    assert not launch.calls
    assert vars(h.state) == before


def test_existing_editor_cancellation_is_preserved(launch, monkeypatch):
    feature = next(f for f in launch.doc["features"] if f["kind"] == "extrude")
    launch.op.feature_id = feature["id"]
    monkeypatch.setattr(launch.viewport.bpy.ops.mcad, "edit_solid_feature", lambda *a, **kw: {"CANCELLED"})
    assert launch.op.execute(launch.host.context) == {"CANCELLED"}
