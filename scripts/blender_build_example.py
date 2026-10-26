"""Build the editable release .blend in an explicit, isolated background process.

Launch Blender with --background --factory-startup and MCAD_ROOT, MCAD_PYTHON,
MCAD_EXAMPLE_OUTPUT. This creates a new empty scene; never run in an interactive
user session. The output path comes from the caller, not saved model data.
"""

import json
import os
import sys
from pathlib import Path

import bpy

if not bpy.app.background:
    raise RuntimeError("Example generation is restricted to an isolated background process.")
root = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
output = Path(os.environ["MCAD_EXAMPLE_OUTPUT"]).resolve()
if output.exists():
    raise FileExistsError(f"Choose a new output path; refusing to replace {output}")
os.environ["MCAD_ROOT"] = str(root)
os.environ.setdefault("MCAD_PYTHON", str(root / ".venv/bin/python"))
sys.path.insert(0, str(root / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402

bpy.ops.wm.read_homefile(use_empty=True)
addon.register()
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 0.001
scene.unit_settings.length_unit = "MILLIMETERS"
assert bpy.ops.mcad.load_document(filepath=str(root / "examples/viewport_rectangle.mcad.json")) == {
    "FINISHED"
}
assert scene.mechanical_cad.status == "READY", scene.mechanical_cad.error
assert abs(scene.mechanical_cad.volume - 12000) < 0.01
assert bpy.ops.mcad.check_geometry() == {"FINISHED"}
assert scene.mechanical_cad.geometry_status == "PASSED"
# A portable example must not retain this build machine's source-save target.
scene.mechanical_cad.document_path = ""
output.parent.mkdir(parents=True, exist_ok=True)
assert bpy.ops.wm.save_as_mainfile(filepath=str(output)) == {"FINISHED"}
print(
    "MCAD_EXAMPLE_RESULT="
    + json.dumps(
        {
            "ok": True,
            "blender": bpy.app.version_string,
            "output": str(output),
            "volume_mm3": scene.mechanical_cad.volume,
            "on_reopen": "Regenerate to revalidate saved display and solver caches",
        }
    )
)
addon.unregister()
