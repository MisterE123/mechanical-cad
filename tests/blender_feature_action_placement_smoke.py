"""Native RNA plus read-only panel draw ordering; GUI placement is separate evidence."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import panels, register, unregister, workspace_ui  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad
state.document_json = '{"features": [], "parameters": {}}'
state.document_name = "Placement test"
state.status = "FAILED"
state.error = "Visible rebuild failure"
state.last_action_error = "Visible rejected edit"
for index in range(25):
    feature = state.features.add()
    feature.feature_id = f"feature_{index}"
    feature.label = f"Feature {index}"
    feature.kind = "fillet"
    parameter = state.parameters.add()
    parameter.key = f"parameter_{index}"
state.feature_index = 24
# The cached rows represent a nonempty document; empty-document starter UI
# deliberately suppresses editing controls. Keep this placement fixture coherent.
state.document_json = json.dumps({"features": [
    {"id": item.feature_id, "label": item.label, "kind": item.kind}
    for item in state.features
], "parameters": {}})
before = state.document_json


class Layout:
    def __init__(self):
        self.events = []

    def operator(self, name, **kwargs):
        self.events.append(("operator", name))
        return SimpleNamespace()

    def label(self, **kwargs):
        self.events.append(("label", kwargs.get("text", "")))

    def prop(self, owner, name, **kwargs):
        self.events.append(("prop", name))

    def template_list(self, *args, **kwargs):
        self.events.append(("history", args[0]))

    def row(self, **kwargs):
        return self

    def box(self, **kwargs):
        return self

    def menu(self, *args, **kwargs):
        pass

    def separator(self):
        pass


def first(events, event):
    assert events.count(event) == 1, (event, events.count(event))
    return events.index(event)


with (
    patch.object(panels, "_panel_wrap", side_effect=lambda context, text: [text]),
    patch.object(panels.assembly_job_ui, "draw_backend_failure", return_value=False),
    patch.object(panels.document_state, "current_part_result", return_value=None),
    patch.object(panels.workspace, "has_draft", return_value=False),
    patch.object(panels, "draw_suspended_draft"),
    patch.object(panels, "draw_support_intent"),
    patch.object(
        panels,
        "draw_projection_repair",
        side_effect=lambda layout, context: layout.operator("mcad.replace_projection_reference"),
    ),
    patch.object(panels, "draw_part_limits"),
    patch.object(panels.operators, "feature_action_reason", return_value=""),
):
    layout = Layout()
    panels.MCAD_PT_main.draw(SimpleNamespace(layout=layout), bpy.context)
    edit = first(layout.events, ("operator", "mcad.edit_solid_feature"))
    display = first(layout.events, ("operator", "mcad.activate_feature"))
    history = first(layout.events, ("history", "MCAD_UL_features"))
    parameters = first(layout.events, ("label", "Parameters · millimetres"))
    assert edit < history < parameters and display < history
    assert first(layout.events, ("operator", "mcad.replace_projection_reference")) < history
    assert ("label", "Selected: Feature 24") in layout.events
    assert ("label", "Visible rebuild failure") in layout.events
    assert ("label", "Visible rejected edit") in layout.events
    # A proposed-graph banner owns repair actions; suppress the ordinary launcher.
    with (
        patch.object(panels.staged_edit, "current", return_value=object()),
        patch.object(panels, "draw_staged_edit", return_value=True),
    ):
        pending_layout = Layout()
        panels.MCAD_PT_main.draw(SimpleNamespace(layout=pending_layout), bpy.context)
        assert ("operator", "mcad.replace_projection_reference") not in pending_layout.events

with (
    patch.object(workspace_ui, "_panel_wrap", side_effect=lambda context, text: [text]),
    patch.object(workspace_ui.assembly_job_ui, "draw_backend_failure"),
    patch.object(workspace_ui.document_state, "current_part_result", return_value=None),
    patch.object(workspace_ui.workspace, "get_role", return_value="PART"),
    patch.object(workspace_ui.workspace, "active_draft", return_value=None),
    patch.object(workspace_ui.workspace, "has_draft", return_value=False),
    patch.object(workspace_ui, "draw_suspended_draft"),
    patch.object(workspace_ui, "draw_part_limits"),
    patch.object(
        workspace_ui,
        "draw_projection_repair",
        side_effect=lambda layout, context: layout.operator("mcad.replace_projection_reference"),
    ),
    patch.object(workspace_ui, "_draw_part_view_controls"),
    patch("mechanical_cad_blender.support_intent_ui.draw_support_intent"),
    patch.object(
        workspace_ui,
        "_action_button",
        side_effect=lambda layout, context, action, **kw: layout.events.append(("action", action)),
    ),
):
    layout = Layout()
    workspace_ui.MCAD_PT_workspace_history.draw(SimpleNamespace(layout=layout), bpy.context)
    edit = first(layout.events, ("action", "EDIT_FEATURE"))
    assert ("action", "EDIT") not in layout.events  # Selected Fillet uses Edit Feature.
    history = first(layout.events, ("history", "MCAD_UL_features"))
    assert edit < history
    assert first(layout.events, ("operator", "mcad.replace_projection_reference")) < history
    assert ("label", "Selected: Feature 24") in layout.events
    assert ("label", "Visible rebuild failure") in layout.events
    assert ("label", "Visible rejected edit") in layout.events
    # A proposed-graph banner owns repair actions; suppress the ordinary launcher.
    with (
        patch.object(workspace_ui.staged_edit, "current", return_value=object()),
        patch.object(workspace_ui, "draw_staged_edit", return_value=True),
    ):
        pending_layout = Layout()
        workspace_ui.MCAD_PT_workspace_history.draw(
            SimpleNamespace(layout=pending_layout), bpy.context
        )
        assert ("operator", "mcad.replace_projection_reference") not in pending_layout.events

assert state.document_json == before
props = bpy.ops.mcad.edit_solid_feature.get_rna_type().properties
assert all(key in props for key in ("radius", "resume_json", "edit_action", "show_help"))
print("MCAD_FEATURE_ACTION_PLACEMENT_SMOKE_OK", flush=True)
unregister()
