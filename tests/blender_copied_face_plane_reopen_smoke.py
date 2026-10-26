"""Second-process replay of an unlinked copied plane after source replacement."""

import json
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import document_state, register, unregister  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad
before = state.document_json
assert document_state.regenerate(bpy.context)
assert state.document_json == before
sketch = json.loads(before)["features"][-1]
expected = json.loads(Path(bpy.data.filepath + ".plane.json").read_text())
assert sketch["sketch"]["plane"] == expected
assert sketch["inputs"] == {}
assert not {"support_face", "support_intent"} & sketch.keys()
assert not sketch.get("projections")
assert not sketch["sketch"].get("projections")
row = document_state.current_part_result(bpy.context)["features"][-1]
assert row["status"] == "ok"
assert row["sketch"]["solved"]["plane"] == expected
print("COPIED_FACE_PLANE_REOPEN_OK", flush=True)
unregister()
