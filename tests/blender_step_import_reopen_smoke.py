"""Fresh-process embedded STEP regeneration without original source file."""

import json
import os
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(os.environ["MCAD_ROOT"]) / "blender_addon"))
from mechanical_cad_blender import document_state, register, unregister  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad
original = state.document_json
assert not Path("/tmp/mcad_import_valid.step").exists()
assert json.loads(original)["features"][0]["kind"] == "import_step"
assert document_state.regenerate(bpy.context)
assert state.document_json == original
assert state.status == "READY" and abs(state.volume - 6000) < 1e-6, state.error
print("MCAD_STEP_IMPORT_REOPEN_SMOKE_OK", flush=True)
unregister()
