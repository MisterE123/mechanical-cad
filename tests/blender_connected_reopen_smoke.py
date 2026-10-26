"""Fresh-process recovery, upstream edit and export for the connected Part workflow."""

import json
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister, workspace_ui  # noqa:E402

register()
bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad
assert state.document_json
assert bpy.ops.mcad.regenerate() == {"FINISHED"}, state.last_action_error
assert abs(state.volume - 6000) < 1e-4
raw = json.loads(state.document_json)
rectangle = raw["features"][0]
width_name = rectangle["params"]["width"]
assert width_name in raw["parameters"]
assert bpy.ops.mcad.named_parameter(
    parameter_name=width_name,
    expression="50",
    replace_existing=True,
    original_json=state.document_json,
) == {"FINISHED"}, state.last_action_error
# Union minus base leaves the untranslated copy's extension, width20 by height30 by depth10.
assert abs(state.volume - 6000) < 1e-4
assert json.loads(state.document_json)["parameters"][width_name] == "50"
icons = {
    i.identifier
    for i in bpy.types.UILayout.bl_rna.functions["operator"].parameters["icon"].enum_items
}
for action, details in workspace_ui._ACTIONS.items():
    assert details[3] in icons, (action, details[3])
assert bpy.ops.mcad.check_geometry() == {"FINISHED"}, state.last_action_error
assert state.geometry_status == "PASSED", state.geometry_message
out = Path(os.environ["MCAD_SMOKE_OUTPUT"])
assert bpy.ops.mcad.export_step(filepath=str(out.with_suffix(".step"))) == {"FINISHED"}, (
    state.last_action_error
)
assert bpy.ops.mcad.export_stl(filepath=str(out.with_suffix(".stl"))) == {"FINISHED"}, (
    state.last_action_error
)
bpy.ops.wm.save_as_mainfile(filepath=str(out))
print(
    "MCAD_CONNECTED_REOPEN_EXPORT_OK",
    json.dumps({"volume": state.volume, "features": len(raw["features"])}),
    flush=True,
)
unregister()
