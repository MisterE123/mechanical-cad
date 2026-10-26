"""Real linked Add/Remove edits, atomic rejection, shared intent and fresh reopen.

Use MCAD_SMOKE_OUTPUT; second process also sets MCAD_SMOKE_INPUT. Not GUI evidence.
"""

import json
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister  # noqa: E402
from mechanical_cad_blender.document_state import _append_feature, _new_feature  # noqa: E402
from mechanical_cad_blender.solid_operators import MCAD_OT_edit_solid_feature, _SolidDialog  # noqa: E402

register()
if os.environ.get("MCAD_SMOKE_INPUT"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad


def run(operator, **kwargs):
    result = operator(**kwargs)
    assert result == {"FINISHED"}, (result, state.last_action_error)
    assert state.status == "READY", (state.status, state.last_action_error)
    return state.active_feature


def rejected(**kwargs):
    before = state.document_json
    try:
        result = bpy.ops.mcad.edit_solid_feature(**kwargs)
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"}, result
    assert state.document_json == before


def edit_arguments(identifier):
    operator = SimpleNamespace(feature_id=identifier)
    context = SimpleNamespace(
        scene=bpy.context.scene,
        window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"}),
    )
    assert MCAD_OT_edit_solid_feature.invoke(operator, context, None) == {"RUNNING_MODAL"}
    return {
        key: getattr(operator, key)
        for key in (
            "feature_id",
            "kind",
            "feature_label",
            "base",
            "tool",
            "original_json",
            "linked_tool_id",
            "linked_length",
            "linked_profile",
            "allow_shared_extrusion",
        )
    }, operator


if os.environ.get("MCAD_SMOKE_INPUT"):
    run(bpy.ops.mcad.regenerate)
    document = json.loads(state.document_json)
    pocket = next(f["id"] for f in document["features"] if f["label"] == "Pocket revised")
    args, _ = edit_arguments(pocket)
    assert args["linked_length"] == "-3"
    assert abs(state.volume - (12000 - 12 * math.pi)) < 1e-3
    args.update(linked_length="-4", allow_shared_extrusion=True)
    run(bpy.ops.mcad.edit_solid_feature, **args)
    assert abs(state.volume - (12000 - 16 * math.pi)) < 1e-3
    marker = "MCAD_LINKED_EXTRUSION_REOPEN_OK"
else:
    run(bpy.ops.mcad.new_document, name="Linked extrusion editing")
    profile = run(bpy.ops.mcad.add_rectangle, width=40, height=30)
    base = run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
    circle = _new_feature(
        bpy.context, "sketch_circle", {"radius": 2, "x": 10, "y": 10, "z": 10}, {}, "Boss profile"
    )
    assert _append_feature(bpy.context, circle)
    added = run(
        bpy.ops.mcad.extrude_boolean,
        mode="ADD",
        profile=circle["id"],
        base=base,
        depth="5",
        feature_label="Boss",
    )
    args, _ = edit_arguments(added)
    original = json.loads(state.document_json)
    args["linked_length"] = "3"
    run(bpy.ops.mcad.edit_solid_feature, **args)
    assert abs(state.volume - (12000 + 12 * math.pi)) < 1e-3
    assert json.loads(state.document_json)["parameters"] == original["parameters"]
    pocket_profile = _new_feature(
        bpy.context, "sketch_circle", {"radius": 2, "x": 20, "y": 10, "z": 10}, {}, "Pocket profile"
    )
    assert _append_feature(bpy.context, pocket_profile)
    pocket = run(
        bpy.ops.mcad.extrude_boolean,
        mode="REMOVE",
        profile=pocket_profile["id"],
        base=added,
        depth="-5",
        feature_label="Pocket",
    )
    args, captured = edit_arguments(pocket)
    assert captured.linked_tool_id == args["tool"]
    assert not captured.linked_consumers
    args.update(linked_length="-2", feature_label="Pocket revised")
    run(bpy.ops.mcad.edit_solid_feature, **args)
    assert abs(state.volume - (12000 + 4 * math.pi)) < 1e-3
    before = json.loads(state.document_json)
    # Zero depth native failure must publish neither rename nor tool change.
    args, _ = edit_arguments(pocket)
    args.update(linked_length="0", feature_label="Must not publish")
    rejected(**args)
    assert json.loads(state.document_json) == before
    args, _ = edit_arguments(pocket)
    args["original_json"] += " "
    rejected(**args)
    assert "Document changed" in state.last_action_error
    # A second consumer is an explicit branch, not hidden shared intent.
    tool = next(f for f in before["features"] if f["id"] == pocket)["inputs"]["tool"]
    shared = _new_feature(
        bpy.context, "cut", {}, {"base": base, "tool": tool}, "Other pocket branch"
    )
    assert _append_feature(bpy.context, shared)
    args, captured = edit_arguments(pocket)
    assert "Other pocket branch" in captured.linked_consumers
    assert shared["id"] in captured.linked_consumers

    # Exercise actual draw code with the shared fields disabled until opt-in.
    class Layout:
        enabled = True

        def __init__(self):
            self.fields = []
            self.labels = []

        def prop(self, operator, name, **kwargs):
            self.fields.append((name, self.enabled))

        def label(self, **kwargs):
            self.labels.append(kwargs.get("text"))

        def box(self):
            return self

        def column(self):
            return self

        def row(self, **kwargs):
            return self

    captured.layout = Layout()
    captured.show_help = False
    captured.help_page = 1
    captured.help_summary = ("Linked extrusion", "Atomic Apply")
    captured.help_topic = "feature.cut"
    _SolidDialog.draw(captured, bpy.context)
    assert ("linked_length", False) in captured.layout.fields
    assert ("linked_profile", False) in captured.layout.fields
    assert ("allow_shared_extrusion", True) in captured.layout.fields
    assert "Other pocket branch" in " ".join(captured.layout.labels)
    assert captured.linked_length == args["linked_length"]
    args["linked_length"] = "-3"
    rejected(**args)
    assert "explicitly allow shared edits" in state.last_action_error
    args["allow_shared_extrusion"] = True
    run(bpy.ops.mcad.edit_solid_feature, **args)
    assert state.active_feature == shared["id"]
    assert abs(state.volume - (12000 - 12 * math.pi)) < 1e-3
    after = json.loads(state.document_json)
    assert after["parameters"] == before["parameters"]
    assert [f["id"] for f in after["features"][:-1]] == [f["id"] for f in before["features"]]
    marker = "MCAD_LINKED_EXTRUSION_SMOKE_OK"

output = os.environ["MCAD_SMOKE_OUTPUT"]
bpy.ops.wm.save_as_mainfile(filepath=output)
print(marker, json.dumps({"volume": state.volume, "path": output}), flush=True)
unregister()
