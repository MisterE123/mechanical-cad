"""Source-loaded Windows registration and closed admission; no native CAD in Blender."""

import json
import math
import os
import sys
from pathlib import Path

import bpy

assert sys.platform == "win32"
ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister  # noqa: E402
from mechanical_cad_blender.gear_pair import build_pair  # noqa: E402

register()
scene = bpy.context.scene
working = scene.mechanical_cad
assembly = scene.mechanical_cad_assembly
before = (working.document_json, assembly.document_json)
objects = tuple(scene.objects)
units = (scene.unit_settings.system, scene.unit_settings.scale_length)
candidate = build_pair(teeth_a=19, teeth_b=37)
assert candidate["gear_relations"][0]["offset_rad"] == math.pi + math.pi / 37
assert json.loads(json.dumps(candidate))["parts"][1]["name"] == "Gear A (19 teeth)"
try:
    result = bpy.ops.mcad.gear_pair()
except RuntimeError as exc:
    assert "qualified for Linux only" in str(exc), str(exc)
else:
    assert result == {"CANCELLED"}
assert (working.document_json, assembly.document_json) == before
assert tuple(scene.objects) == objects
assert (scene.unit_settings.system, scene.unit_settings.scale_length) == units
assert not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules)
assert "mechanical_cad.kernel_ocp" not in sys.modules
unregister()
print("MCAD_GEAR_WINDOWS_BOUNDARY_OK: registration, pure candidate, closed Apply, unchanged state; native CAD remains external")
