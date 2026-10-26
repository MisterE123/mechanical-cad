"""Fresh-process typed-sketch persistence and editable downstream continuity.

This tests actual .blend I/O and native sidecar replay. Native interactive
workspace-layout persistence has its own staged GUI fixture.
"""

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender.sketch_draft import RectangleDraft  # noqa: E402

checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)


def state():
    return bpy.context.scene.mechanical_cad


addon.register()
phase = os.environ.get("MCAD_SKETCH_PHASE", "save")
if phase == "reopen":
    path = Path(os.environ["MCAD_SKETCH_BLEND"])
    bpy.ops.wm.open_mainfile(filepath=str(path))
    saved = path.with_suffix(".json").read_text()
    check(state().document_json == saved, "Schema-2 source survives exact native save/reopen")
    check(state().status == "DIRTY", "Loaded display requires a fresh replay")
    check(state().geometry_status == "OUTDATED", "Saved geometry report is not trusted")
    row = next(item for item in state().features if item.feature_id == "sketch_1")
    check(row.sketch_report_status == "OUTDATED", "Saved DoF report is not current")
    check(addon._owned_objects(bpy.context.scene)[0].hide_viewport, "Unverified geometry is hidden")
    check(addon.regenerate(bpy.context), "Saved typed sketch replays successfully")
    draft = RectangleDraft(state().document_json, feature_id="sketch_1", is_edit=True)
    check(draft.width_text == "40.0", "Reopened rectangle is still an editable tool definition")
    source_before = json.loads(saved)
    parameter = next(item for item in state().parameters if item.key == "sketch_1_width")
    parameter.expression = "55"
    check(state().status == "DIRTY", "Reopened expression callback remains bound")
    check(row.sketch_report_status == "OUTDATED", "Dimension edit invalidates prior DoF")
    check(addon.regenerate(bpy.context), "Upstream edit rebuilds the same downstream solid")
    current = json.loads(state().document_json)
    check(current["active_feature"] == "extrude_1", "Active downstream output identity survives")
    check(
        [f["id"] for f in current["features"]] == [f["id"] for f in source_before["features"]],
        "No replacement features created",
    )
    check(
        current["features"][0]["sketch"] == source_before["features"][0]["sketch"],
        "Rebuild retains all sketch seeds and constraints",
    )
    check(math.isclose(state().volume, 16500, rel_tol=1e-6), "Edited volume is 55 x30 x10 mm cubed")
    row = next(item for item in state().features if item.feature_id == "sketch_1")
    check(json.loads(row.sketch_report_json)["remaining_dof"] == 0, "Fresh native DoF is restored")
else:
    check(
        bpy.ops.mcad.load_document(filepath=str(ROOT / "examples/viewport_rectangle.mcad.json"))
        == {"FINISHED"},
        "Editable fixture loads",
    )
    check(
        state().status == "READY" and abs(state().volume - 12000) < 0.01,
        "Original exact part is valid",
    )
    check(
        bpy.ops.mcad.check_geometry() == {"FINISHED"}, "Verified canonical geometry report exists"
    )
    with tempfile.TemporaryDirectory(prefix="mcad-sketch-persistence-") as directory:
        path = Path(directory) / "rectangle.blend"
        path.with_suffix(".json").write_text(state().document_json)
        check(
            bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"}, "Native .blend saved"
        )
        environment = dict(os.environ, MCAD_SKETCH_PHASE="reopen", MCAD_SKETCH_BLEND=str(path))
        if bpy.app.binary_path and Path(bpy.app.binary_path).is_file():
            command = [
                bpy.app.binary_path,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python-expr",
                "import sys; sys.dont_write_bytecode = True",
                "--python",
                str(Path(__file__).resolve()),
            ]
        else:
            command = [sys.executable, str(Path(__file__).resolve())]
        child = subprocess.run(
            command, env=environment, text=True, capture_output=True, timeout=120
        )
        check(
            child.returncode == 0, f"Fresh-process assertions pass: {child.stdout}\n{child.stderr}"
        )
        check('"phase": "reopen"' in child.stdout, "Child reports the actual reopen phase")
        print(child.stdout)
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Native CAD stays outside Blender",
)
addon.unregister()
print(
    "MCAD_CONSTRAINED_PERSISTENCE_RESULT="
    + json.dumps(
        {"ok": True, "blender": bpy.app.version_string, "phase": phase, "check_count": len(checks)}
    )
)
