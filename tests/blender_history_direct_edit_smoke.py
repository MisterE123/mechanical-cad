"""Real RNA row dispatch and delegated dismissal; no GUI/native geometry claim."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    panels,
    register,
    solid_operators,
    unregister,
    viewport_sketch,
)

opened = []
original_invoke = solid_operators.MCAD_OT_edit_solid_feature.invoke


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


def invoke(self, context):
    assert original_invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
    opened.append((self.feature_id, self.kind, self.feature_label))
    return {"CANCELLED"}


# Background RNA runs execute rather than opening a real modal dialog.
solid_operators.MCAD_OT_edit_solid_feature.execute = invoke
register()
state = bpy.context.scene.mechanical_cad
document = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
document_state._populate_document(bpy.context.scene, document)
state.feature_index = -1
before = (state.document_json, state.active_feature, state.feature_index)
solid = next(f for f in document["features"] if f["kind"] == "extrude")
assert bpy.ops.mcad.edit_history_feature(feature_id=solid["id"]) == {"CANCELLED"}
assert opened == [(solid["id"], solid["kind"], solid["label"])]
assert (state.document_json, state.active_feature, state.feature_index) == before
sketch = next(f for f in document["features"] if f["kind"] == "sketch_constrained")
with patch.object(viewport_sketch, "_begin_in_sketch") as begin:
    assert bpy.ops.mcad.edit_history_feature(feature_id=sketch["id"]) == {"FINISHED"}
    assert begin.call_args.args[1] == sketch["id"]
    assert begin.call_args.kwargs == {"editor": "mcad.rectangle_sketch"}
assert (state.document_json, state.active_feature, state.feature_index) == before


class Layout:
    enabled = True

    def __init__(self):
        self.children = []
        self.buttons = []
        self.labels = []

    def row(self, **kwargs):
        child = Layout()
        self.children.append(child)
        return child

    def label(self, **kwargs):
        self.labels.append(kwargs)

    def operator(self, name, **kwargs):
        op = SimpleNamespace()
        self.buttons.append((name, kwargs, op))
        return op


for kind, enabled in [("extrude", True), ("sketch_constrained", True), ("import_step", False), ("future_kind", False)]:
    item = SimpleNamespace(feature_id="clicked", kind=kind, label="Clicked feature")
    layout = Layout()
    with patch.object(document_state, "current_part_result", return_value=None):
        panels.MCAD_UL_features.draw_item(None, bpy.context, layout, state, item, 0, state, "feature_index", 0)
    edit = layout.children[0].children[0]
    assert edit.enabled == enabled
    name, kwargs, op = edit.buttons[0]
    assert name == "mcad.edit_history_feature" and kwargs["icon"] == "GREASEPENCIL"
    assert op.feature_id == "clicked"
    assert edit.operator_context == "INVOKE_DEFAULT"

# The operation family never disguises stale/failed/blocked status, assumed
# support, or the displayed output. Drawing remains side-effect free.
item = SimpleNamespace(feature_id="clicked", kind="extrude", label="Long extrusion name")
state.active_feature = "clicked"
for status_icon in ("DOT", "CHECKMARK", "ERROR", "CANCEL"):
    layout = Layout()
    before_draw = (state.document_json, state.active_feature, state.feature_index)
    with patch.object(panels, "row_presentation", return_value=(status_icon, True)):
        panels.MCAD_UL_features.draw_item(None, bpy.context, layout, state, item, 0, state, "feature_index", 0)
    assert layout.children[0].labels == [
        {"text": item.label, "icon": "MOD_SOLIDIFY"},
        {"text": "", "icon": status_icon},
        {"text": "Plane assumed", "icon": "INFO"},
        {"text": "", "icon": "HIDE_OFF"},
    ]
    assert (state.document_json, state.active_feature, state.feature_index) == before_draw
state.active_feature = before[1]

state.sketch_draft_json = "retained draft"
assert not bpy.ops.mcad.edit_history_feature.poll()
state.sketch_draft_json = ""
state.repair_intent_json = "retained repair"
assert not bpy.ops.mcad.edit_history_feature.poll()
state.repair_intent_json = ""
assert bpy.ops.mcad.edit_history_feature.poll()
assert (state.document_json, state.active_feature, state.feature_index) == before
unregister()
print("HISTORY_DIRECT_EDIT_SMOKE_OK", flush=True)
