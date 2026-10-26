"""Native centered extrusion, history edit, atomic failure and fresh reopen."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister  # noqa: E402
from mechanical_cad_blender.solid_operators import MCAD_OT_edit_solid_feature  # noqa: E402

register()
if os.environ.get("MCAD_SMOKE_INPUT"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad


def run(op, **kwargs):
    assert op(**kwargs) == {"FINISHED"}, state.last_action_error
    assert state.status == "READY", state.last_action_error
    return state.active_feature


def edit_args(feature_id):
    op = SimpleNamespace(feature_id=feature_id)
    context = SimpleNamespace(
        scene=bpy.context.scene,
        window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"}),
    )
    assert MCAD_OT_edit_solid_feature.invoke(op, context, None) == {"RUNNING_MODAL"}
    keys = [
        "feature_id",
        "kind",
        "feature_label",
        "original_json",
        "profile",
        "length",
        "extrude_end_condition",
    ]
    return {key: getattr(op, key) for key in keys}


if os.environ.get("MCAD_SMOKE_INPUT"):
    run(bpy.ops.mcad.regenerate)
    args = edit_args(state.active_feature)
    assert args["extrude_end_condition"] == "SYMMETRIC"
    assert abs(state.volume - 1400) < 1e-3
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "length": "20"})
    assert abs(state.volume - 2000) < 1e-3
    marker = "MCAD_SYMMETRIC_REOPEN_OK"
else:
    run(bpy.ops.mcad.new_document, name="Symmetric extrusion")
    profile = run(bpy.ops.mcad.add_rectangle, width=10, height=10)
    pad = run(bpy.ops.mcad.add_extrude, profile=profile, length=10, end_condition="SYMMETRIC")
    assert abs(state.volume - 1000) < 1e-3
    args = edit_args(pad)
    assert args["kind"] == "extrude_symmetric"
    assert args["extrude_end_condition"] == "SYMMETRIC"
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "length": "14"})
    assert abs(state.volume - 1400) < 1e-3
    before = state.document_json
    args = edit_args(pad)
    try:
        result = bpy.ops.mcad.edit_solid_feature(
            **{**args, "length": "-4", "feature_label": "Must not publish"}
        )
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"}
    assert state.document_json == before
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "extrude_end_condition": "BLIND"})
    assert json.loads(state.document_json)["features"][-1]["kind"] == "extrude"
    args = edit_args(pad)
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "extrude_end_condition": "SYMMETRIC"})
    assert json.loads(state.document_json)["features"][-1]["kind"] == "extrude_symmetric"
    marker = "MCAD_SYMMETRIC_SMOKE_OK"

bpy.ops.wm.save_as_mainfile(filepath=os.environ["MCAD_SMOKE_OUTPUT"])
print(marker, state.volume, flush=True)
unregister()
