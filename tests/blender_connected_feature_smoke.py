"""Connected user operators on real Blender + sidecar; not a GUI-usability claim."""

import json
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister, workspace_ui  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad


def run(op, **kwargs):
    result = op(**kwargs)
    assert result == {"FINISHED"}, (op, result, state.error, state.last_action_error)
    assert state.status == "READY", (state.status, state.error, state.last_action_error)
    return state.active_feature


run(bpy.ops.mcad.new_document, name="Connected feature workshop")
profile = run(bpy.ops.mcad.add_rectangle, width=40, height=30)
base = run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
assert abs(state.volume - 12000) < 1e-5
fillet = run(
    bpy.ops.mcad.add_solid_feature,
    kind="fillet",
    base=base,
    radius="1",
    feature_label="Rounded plate",
)
assert 11000 < state.volume < 12000
shifted = run(
    bpy.ops.mcad.add_solid_feature, kind="transform", base=base, x="20", feature_label="Offset copy"
)
union = run(
    bpy.ops.mcad.add_solid_feature,
    kind="union",
    base=base,
    tool=shifted,
    feature_label="Joined plate",
)
assert abs(state.volume - 18000) < 1e-4
cut = run(bpy.ops.mcad.add_cut, base=union, tool=base)
assert abs(state.volume - 6000) < 1e-4
run(
    bpy.ops.mcad.named_parameter,
    parameter_name="wall",
    expression="2.5",
    original_json=state.document_json,
)
assert json.loads(state.document_json)["parameters"]["wall"] == "2.5"
for action in (
    "REVOLVE",
    "UNION",
    "INTERSECTION",
    "FILLET",
    "CHAMFER",
    "TRANSFORM",
    "EDIT_FEATURE",
):
    assert action in workspace_ui._ACTIONS
assert bpy.ops.mcad.new_plane_sketch.get_rna_type()
assert bpy.ops.mcad.sketch_normal_view.get_rna_type()
assert bpy.ops.mcad.remove_history_feature.get_rna_type()
path = os.environ["MCAD_SMOKE_OUTPUT"]
bpy.ops.wm.save_as_mainfile(filepath=path)
assert Path(path).is_file()
print(
    "MCAD_CONNECTED_FEATURE_SMOKE_OK",
    json.dumps(
        {
            "features": len(json.loads(state.document_json)["features"]),
            "volume": state.volume,
            "path": path,
        }
    ),
    flush=True,
)
unregister()
