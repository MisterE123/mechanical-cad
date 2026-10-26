"""Registered UI draw/fixed-offset poll checks; no rendered GUI or kernel claim."""

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    execution_lease,
    fixed_plane_edit,
    register,
    unregister,
    workspace_ui,
)
from mechanical_cad_blender.solid_feature_edit import FEATURE_FIELDS  # noqa: E402


class Layout:
    def __init__(self, buttons=None):
        self.buttons = buttons if buttons is not None else []
        self.enabled = True

    def row(self, **kwargs):
        return Layout(self.buttons)

    column = row

    def operator(self, name, **kwargs):
        op = SimpleNamespace(name=name, enabled=self.enabled, **kwargs)
        self.buttons.append(op)
        return op

    def label(self, **kwargs):
        pass

    def separator(self):
        pass


register()
state = bpy.context.scene.mechanical_cad
fixture = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
document_state._populate_document(bpy.context.scene, fixture)
state.feature_index = 0
before = state.document_json


def direct(context=bpy.context, ready=True):
    layout = Layout()
    with patch.object(workspace_ui, "available", return_value=ready), patch.object(workspace_ui, "_icon", return_value=0):
        workspace_ui._draw_selected_history_edit(layout, context)
    return layout.buttons


def actions(buttons):
    return [b.action for b in buttons if hasattr(b, "action")]


def offset(buttons):
    return [b for b in buttons if b.name == "mcad.offset_fixed_sketch_plane"]


# Every family supported by the existing parameter editor keeps that launcher.
for kind in (*FEATURE_FIELDS, "sketch_constrained", "import_step", "future_kind"):
    selected = SimpleNamespace(kind=kind, label="Selected")
    ctx = SimpleNamespace(scene=SimpleNamespace(mechanical_cad=SimpleNamespace(
        features=[selected], feature_index=0,
    )))
    expected = ["EDIT"] if kind == "sketch_constrained" else ["EDIT_FEATURE"] if kind in FEATURE_FIELDS else []
    for ready in (True, False):
        buttons = direct(ctx, ready)
        assert actions(buttons) == expected, (kind, buttons)
        assert bool(offset(buttons)) == (kind == "sketch_constrained")
        assert all(b.enabled == ready for b in buttons if hasattr(b, "action"))
        assert any(b.name == "mcad.activate_feature" for b in buttons)
        assert any(b.name == "mcad.remove_history_feature" for b in buttons)

assert bpy.ops.mcad.offset_fixed_sketch_plane.poll()
assert offset(direct())
# Busy and stale do not change applicability or hide the direct controls.
token = execution_lease.try_acquire()
assert token is not None
try:
    assert not bpy.ops.mcad.offset_fixed_sketch_plane.poll()
    assert offset(direct(ready=False)) and actions(direct(ready=False)) == ["EDIT"]
finally:
    execution_lease.release(token)
state.document_json += " "
assert offset(direct()) and actions(direct()) == ["EDIT"]
state.document_json = before

# Attached and projected candidates retain a visible guarded explanation.
for field, value in (("support_face", {}), ("support_intent", {}), ("projections", [{"id": "linked"}]), ("inputs", {"support": "source"})):
    candidate = copy.deepcopy(fixture)
    candidate["features"][0][field] = value
    state.document_json = json.dumps(candidate)
    assert offset(direct())
    assert not bpy.ops.mcad.offset_fixed_sketch_plane.poll(), field
    try:
        fixed_plane_edit.fixed_sketch(candidate, candidate["features"][0]["id"])
    except ValueError as exc:
        assert "Attached sketches and linked projections" in str(exc)
    else:
        raise AssertionError(field)
state.document_json = before

# Both workspaces keep explicit menu access to both distinct editors and offset.
for role in ("SKETCH", "PART"):
    layout = Layout()
    with patch.object(workspace_ui.workspace, "get_role", return_value=role), patch.object(workspace_ui.workspace_view, "draw_focus"), patch.object(workspace_ui, "available", return_value=False), patch.object(workspace_ui, "_icon", return_value=0), patch.object(workspace_ui, "action_reason", return_value=""):
        workspace_ui.MCAD_MT_workspace.draw(SimpleNamespace(layout=layout), bpy.context)
    assert "EDIT" in actions(layout.buttons) and "EDIT_FEATURE" in actions(layout.buttons)
    assert len(offset(layout.buttons)) == 1
    assert offset(layout.buttons)[0].text == "Offset Fixed Sketch Plane"

# Assembly keeps its existing menu dispatch and never receives Part-only offset.
layout = Layout()
with patch.object(workspace_ui.workspace, "get_role", return_value="ASSEMBLY"), patch.object(workspace_ui.workspace_view, "draw_focus"), patch.object(workspace_ui.assembly_ui, "draw_assembly_menu") as assembly_menu:
    workspace_ui.MCAD_MT_workspace.draw(SimpleNamespace(layout=layout), bpy.context)
    assembly_menu.assert_called_once_with(layout, bpy.context)
assert not offset(layout.buttons)
assert not actions(layout.buttons)

assert state.document_json == before
unregister()
print("CONTEXTUAL_HISTORY_ACTIONS_SMOKE_OK", flush=True)
