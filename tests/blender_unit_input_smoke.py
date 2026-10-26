"""Native typed units, rejected edits, assembly radians and fresh-process reopen.

Run source-loaded with MCAD_ROOT, MCAD_PYTHON and MCAD_SMOKE_OUTPUT; run a second
Blender process with MCAD_SMOKE_INPUT pointing to the first saved scene.
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
sys.path.insert(0, str(ROOT / "tests"))
from blender_async_helpers import replay_assembly  # noqa: E402
from mechanical_cad_blender import assembly_state, register, unregister  # noqa: E402
from mechanical_cad_blender.solid_operators import MCAD_OT_edit_solid_feature  # noqa: E402

register()
if os.environ.get("MCAD_SMOKE_INPUT"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad
storage = bpy.context.scene.mechanical_cad_assembly


def run(op, **kwargs):
    assert op(**kwargs) == {"FINISHED"}, state.last_action_error
    return state.active_feature


def rejected(op, **kwargs):
    before = (state.document_json, storage.document_json)
    try:
        result = op(**kwargs)
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"}
    assert before == (state.document_json, storage.document_json)


def edit_args(feature_id):
    op = SimpleNamespace(feature_id=feature_id, resume_json="")
    context = SimpleNamespace(
        scene=bpy.context.scene,
        window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"}),
    )
    assert MCAD_OT_edit_solid_feature.invoke(op, context, None) == {"RUNNING_MODAL"}
    keys = (
        "feature_id",
        "kind",
        "feature_label",
        "original_json",
        "profile",
        "length",
        "extrude_end_condition",
    )
    return {key: getattr(op, key) for key in keys}


def assembly():
    return assembly_state.read_assembly(storage)


def check_saved():
    data = json.loads(state.document_json)
    assert data["features"][-1]["params"]["length"] == 20
    assert abs(state.volume - 2000) < 1e-3
    joint = assembly()["joints"][-1]
    assert math.isclose(joint["rotation"], 1.0)
    assert joint["coordinate"] == 25.4
    assert joint["limits"] == [0.0, 50.0]
    assert joint["rotation_limits"] == [-math.pi, math.pi]


if os.environ.get("MCAD_SMOKE_INPUT"):
    run(bpy.ops.mcad.regenerate)
    run(replay_assembly)
    check_saved()
    args = edit_args(state.active_feature)
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "length": "3 cm"})
    assert abs(state.volume - 3000) < 1e-3
    joint = assembly()["joints"][-1]
    run(bpy.ops.mcad.assembly_joint, joint_id=joint["id"], coordinate="2 cm", rotation="90 deg")
    joint = assembly()["joints"][-1]
    assert joint["coordinate"] == 20 and joint["rotation"] == math.pi / 2
    marker = "MCAD_UNIT_INPUT_REOPEN_OK"
else:
    run(bpy.ops.mcad.new_document, name="Unit input")
    profile = run(bpy.ops.mcad.add_rectangle, width=10, height=10)
    # Original numeric operator property remains compatible.
    run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
    assert abs(state.volume - 1000) < 1e-3
    pad = run(bpy.ops.mcad.add_extrude, profile=profile, length_input="1 in")
    assert abs(state.volume - 2540) < 1e-3
    args = edit_args(pad)
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "length": "2 cm"})
    assert abs(state.volume - 2000) < 1e-3
    args = edit_args(pad)
    rejected(bpy.ops.mcad.edit_solid_feature, **{**args, "length": "30 deg"})
    rejected(bpy.ops.mcad.edit_solid_feature, **{**args, "length": "1 in + 2 cm"})
    rejected(bpy.ops.mcad.add_extrude, profile=profile, length_input="nan mm")
    run(bpy.ops.mcad.assembly_new, grounded=True)
    data = assembly()
    run(
        bpy.ops.mcad.assembly_insert,
        part_id=data["parts"][0]["id"],
        parent=data["grounded_instance"],
        parent_frame="origin",
        child_frame="origin",
        kind="cylindrical",
        coordinate="1 in",
        use_limits=True,
        lower="0 mm",
        upper="5 cm",
        rotation="1 rad",
        use_rotation_limits=True,
        rotation_lower="-180 deg",
        rotation_upper="180 deg",
    )
    joint = assembly()["joints"][-1]
    rejected(
        bpy.ops.mcad.assembly_joint, joint_id=joint["id"], coordinate="2 deg", rotation="1 rad"
    )
    check_saved()
    marker = "MCAD_UNIT_INPUT_SMOKE_OK"

bpy.ops.wm.save_as_mainfile(filepath=os.environ["MCAD_SMOKE_OUTPUT"])
print(marker, state.volume, flush=True)
unregister()
