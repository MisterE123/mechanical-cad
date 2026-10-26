"""Native file-selector operator transaction, immutable import and downstream Part use."""

import json
import os
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(os.environ["MCAD_ROOT"]) / "blender_addon"))
from mechanical_cad_blender import document_state, register, unregister  # noqa: E402
from mechanical_cad_blender.step_asset import decode_step  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad
assert not state.document_json
assert bpy.ops.mcad.import_step(
    filepath="/tmp/mcad_import_valid.step", feature_label="Imported block"
) == {"FINISHED"}
assert state.status == "READY", state.error
assert abs(state.volume - 6000) < 1e-6
original = state.document_json
feature = json.loads(original)["features"][0]
assert feature["kind"] == "import_step"
assert decode_step(feature["step_data"]) == Path("/tmp/mcad_import_valid.step").read_bytes()
row = document_state.current_part_result(bpy.context)["features"][0]
assert all(face["provenance"]["semantic_status"] != "stable" for face in row["topology"])
for name in ("bad", "multiple", "oversize"):
    try:
        result = bpy.ops.mcad.import_step(filepath="/tmp/mcad_import_" + name + ".step")
        assert result == {"CANCELLED"}, result
    except RuntimeError:
        pass  # Blender propagates ERROR reports as RuntimeError for script calls.
    assert state.document_json == original, name
    assert state.status == "READY" and abs(state.volume - 6000) < 1e-6
    assert state.last_action_error
assert bpy.ops.mcad.add_solid_feature(
    kind="transform", base=feature["id"], x="20", feature_label="Moved import"
) == {"FINISHED"}
assert state.status == "READY", state.error
assert abs(state.volume - 6000) < 1e-6
assert bpy.ops.mcad.assembly_new(name="Imported assembly", grounded=True) == {"FINISHED"}
assert bpy.context.scene.mechanical_cad_assembly.document_json
Path("/tmp/mcad_import_valid.step").unlink()
bpy.ops.wm.save_as_mainfile(filepath="/tmp/mcad_step_import.blend")
print("MCAD_STEP_IMPORT_SMOKE_OK", flush=True)
unregister()
