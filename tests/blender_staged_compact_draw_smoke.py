"""Read-only narrow panel drawing with real accepted/proposed native CAD state."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    bridge,
    document_state,
    history_rebuild,
    panels,
    register,
    repair_intent,
    staged_edit,
    staged_edit_store,
    staged_edit_ui,
    unregister,
    workspace_ui,
)
from staged_edit_cases import support_case  # noqa: E402


class NarrowContext:
    region = SimpleNamespace(width=240)

    def __getattr__(self, key):
        return getattr(bpy.context, key)


class Layout:
    def __init__(self):
        self.events = []
        self.buttons = []

    def operator(self, name, **kwargs):
        self.events.append(("operator", name))
        button = SimpleNamespace(identifier=name, **kwargs)
        self.buttons.append(button)
        return button

    def label(self, **kwargs):
        self.events.append(("label", kwargs.get("text", "")))

    def prop(self, owner, name, **kwargs):
        self.events.append(("prop", name))

    def template_list(self, *args, **kwargs):
        self.events.append(("history", args[0]))

    def row(self, **kwargs):
        return self

    box = row
    column = row

    def menu(self, *args, **kwargs):
        pass

    def separator(self):
        pass


assert bpy.app.background
register()
context = NarrowContext()
base, proposed = support_case()
assert document_state._commit_candidate(context, base)
try:
    document_state._commit_candidate(context, proposed, stage_feature_id="slot_tool")
except bridge.BridgeError as exc:
    context.scene.mechanical_cad.last_action_error = str(exc)
else:
    raise AssertionError("Expected retained rejected edit")
proposal = staged_edit.current(context)
state = context.scene.mechanical_cad
before = state.document_json
runtime = document_state.current_part_evidence(context)
with patch.object(
    document_state, "_run_sidecar", side_effect=AssertionError("Draw ran native replay")
):
    banner = Layout()
    assert staged_edit_ui.draw_staged_edit(banner, context)
    assert banner.events.index(("operator", "mcad.edit_sketch_support")) == 2
    assert banner.events.index(("operator", "mcad.discard_proposed_edit")) == 3
    assert len([event for event in banner.events if event[0] == "label"]) <= 12
    repair = next(
        button for button in banner.buttons if button.identifier == "mcad.edit_sketch_support"
    )
    assert repair.staged_token == proposal.token and repair.feature_id == "attached"
    detail = next(button for button in banner.buttons if button.identifier == "mcad.help")
    assert (
        "slot_tool" in detail.detail
        and "Valid reference repairs remain in the proposal" in detail.detail
    )
    for cls in (panels.MCAD_PT_main, workspace_ui.MCAD_PT_workspace_history):
        with patch.object(workspace_ui.workspace, "get_role", return_value="PART"):
            layout = Layout()
            cls.draw(SimpleNamespace(layout=layout), context)
        repair_index = layout.events.index(("operator", "mcad.edit_sketch_support"))
        history_index = next(i for i, event in enumerate(layout.events) if event[0] == "history")
        assert repair_index < history_index
        assert (
            sum(event == ("operator", "mcad.edit_sketch_support") for event in layout.events) == 1
        )
        assert not any(
            "Unapplied edit retained for repair;" in text
            for kind, text in layout.events
            if kind == "label"
        )
        # An unrelated failure must remain visible even with a pending proposal.
        state.last_action_error = "Ordinary unrelated failure"
        with patch.object(workspace_ui.workspace, "get_role", return_value="PART"):
            other = Layout()
            cls.draw(SimpleNamespace(layout=other), context)
        assert "Ordinary unrelated failure" in " ".join(
            text for kind, text in other.events if kind == "label"
        )
        state.last_action_error = "Unapplied edit retained for repair; accepted model unchanged."
    assert state.document_json == before
    assert staged_edit.current(context) is proposal
    assert document_state.current_part_evidence(context) == runtime
# A native workspace context override models a completed workspace switch, but
# repeated passive panel draws must not validate, pop ownership or write RNA.
# Recording layouts are not actual GUI qualification; unit tests additionally
# enforce Blender's draw-time ID write prohibition with a guarded state object.
original_workspace = context.window.workspace
other_workspace = next(w for w in bpy.data.workspaces if w != original_workspace)
state.repair_intent_json = "  {unsupported raw\n"
diagnostic = state.last_action_error
with (
    bpy.context.temp_override(workspace=other_workspace),
    patch.object(document_state, "_run_sidecar", side_effect=AssertionError("Draw replay")),
    patch.object(staged_edit_store, "_validated_current", side_effect=AssertionError("Draw validates")),
):
    assert context.workspace != proposal.binding["workspace"]
    for role in ("PART", "ASSEMBLY", "PART", "SKETCH", "PART"):
        for cls in (panels.MCAD_PT_main, workspace_ui.MCAD_PT_workspace_history):
            with patch.object(workspace_ui.workspace, "get_role", return_value=role):
                cls.draw(SimpleNamespace(layout=Layout()), context)
        assert staged_edit.current(context) is proposal
        assert state.last_action_error == diagnostic
        assert state.repair_intent_json == "  {unsupported raw\n"
        assert state.document_json == before
with bpy.context.temp_override(workspace=other_workspace):
    try:
        staged_edit.require(context, proposal.token)
    except bridge.BridgeError as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("Explicit action accepted a workspace-stale proposal")
assert staged_edit.current(context) is None
assert "NOT saved" in state.last_action_error
assert "not overwritten" in state.last_action_error
assert state.repair_intent_json == "  {unsupported raw\n"
assert state.document_json == before
# Dormant intent must remain accessible even when it cannot be parsed. Drawing
# cannot silently discard/migrate it or make a native validation request.
state.repair_intent_json = "{unsupported raw"
with (
    patch.object(document_state, "_run_sidecar", side_effect=AssertionError("Draw replay")),
    patch.object(repair_intent, "decode", side_effect=AssertionError("Draw parsed saved intent")),
):
    banner = Layout()
    assert staged_edit_ui.draw_staged_edit(banner, context)
    assert banner.events[:4] == [
        ("label", "Saved repair work"),
        ("label", "Not applied to model"),
        ("operator", "mcad.resume_saved_repair"),
        ("operator", "mcad.discard_saved_repair"),
    ]
    labels = [text for kind, text in banner.events if kind == "label"]
    assert len(labels) <= 6, labels
    assert "Resume checks saved repairs without applying changes." in " ".join(labels)
    detail = next(button for button in banner.buttons if button.identifier == "mcad.help")
    assert detail.topic == "error.details"
    assert "unsupported or incompatible intent stays saved" in detail.detail
    assert "Cancel in a repair review keeps the proposal" in detail.detail
    assert "never applies edits or restores old native evidence" in detail.detail
    for message in ("Saved repair base changed; Resume refused", "STEP export permission denied"):
        state.last_action_error = message
        for cls in (panels.MCAD_PT_main, workspace_ui.MCAD_PT_workspace_history):
            with patch.object(workspace_ui.workspace, "get_role", return_value="PART"):
                layout = Layout()
                cls.draw(SimpleNamespace(layout=layout), context)
            assert message in " ".join(text for kind, text in layout.events if kind == "label")
            assert any(
                button.identifier == "mcad.help" and getattr(button, "detail", "") == message
                for button in layout.buttons
            ), "Real errors keep their complete accessible diagnostic"
            assert layout.events.index(("operator", "mcad.resume_saved_repair")) < next(
                i for i, event in enumerate(layout.events) if event[0] == "history"
            )
            assert state.repair_intent_json == "{unsupported raw"
            assert state.last_action_error == message
            assert state.document_json == before
            assert staged_edit.current(context) is None
            assert document_state.current_part_evidence(context) == runtime
staged_edit.discard_saved(context)
document_state.invalidate_backend("Integrated history draw check", context.scene)
history_rebuild.schedule()
assert history_rebuild.active(context)
for cls in (panels.MCAD_PT_main, workspace_ui.MCAD_PT_workspace_history):
    with patch.object(workspace_ui.workspace, "get_role", return_value="PART"):
        layout = Layout()
        cls.draw(SimpleNamespace(layout=layout), context)
    assert layout.events.count(("operator", "mcad.cancel_history_rebuild")) == 1
    assert ("operator", "mcad.regenerate") not in layout.events
assert context.scene.mechanical_cad.document_json == before
history_rebuild.cancel("Integrated draw check complete")
# Load-origin rebuilding remains cancellable beside dormant saved cards, even
# when the intent is unsupported. Neither drawing nor replay owns these slots.
state.repair_intent_json = "{unsupported saved repair"
state.sketch_draft_json = "{unsupported saved sketch"
intent = (state.repair_intent_json, state.sketch_draft_json, state.sketch_annotation_json)
document_state.invalidate_backend("Loaded accepted display draw check", context.scene)
history_rebuild.schedule(after_load=True)
assert history_rebuild.active(context)
for cls in (panels.MCAD_PT_main, workspace_ui.MCAD_PT_workspace_history):
    with patch.object(workspace_ui.workspace, "get_role", return_value="PART"):
        layout = Layout()
        cls.draw(SimpleNamespace(layout=layout), context)
    assert layout.events.count(("operator", "mcad.cancel_history_rebuild")) == 1
    assert ("operator", "mcad.regenerate") not in layout.events
    assert ("operator", "mcad.resume_saved_repair") in layout.events
    assert ("operator", "mcad.discard_suspended_sketch") in layout.events
assert (state.repair_intent_json, state.sketch_draft_json, state.sketch_annotation_json) == intent
assert state.document_json == before
history_rebuild.cancel("Loaded display draw check complete")
unregister()
print("STAGED_COMPACT_DRAW_NATIVE_OK", flush=True)
