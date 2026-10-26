"""Two-process .blend persistence test. Run once with MCAD_MODE=save, then reopen."""

import json
import math
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"]).resolve()
PATH = Path(os.environ["MCAD_BLENDFILE"]).resolve()
MODE = os.environ["MCAD_MODE"]
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402

addon.register()
if MODE == "save":
    assert bpy.ops.mcad.new_demo() == {"FINISHED"}
    state = bpy.context.scene.mechanical_cad
    next(item for item in state.parameters if item.key == "width").value = 42.5
    assert bpy.ops.mcad.regenerate() == {"FINISHED"}
    assert state.status == "READY", state.error
    Path(str(PATH) + ".json").write_text(state.document_json, encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(PATH))
elif MODE == "reopen":
    bpy.ops.wm.open_mainfile(filepath=str(PATH))
    state = bpy.context.scene.mechanical_cad
    assert state.document_json == Path(str(PATH) + ".json").read_text(encoding="utf-8")
    assert state.status == "DIRTY", state.status
    next(item for item in state.parameters if item.key == "width").value = 67.5
    assert bpy.ops.mcad.regenerate() == {"FINISHED"}
    assert state.status == "READY", state.error
    assert abs(state.volume - (67.5 * 30 - math.pi * 4**2) * 10) < 0.01
else:
    raise AssertionError(f"Unsupported mode: {MODE}")
print(
    "MCAD_PERSISTENCE_RESULT="
    + json.dumps({"ok": True, "blender": bpy.app.version_string, "mode": MODE})
)
