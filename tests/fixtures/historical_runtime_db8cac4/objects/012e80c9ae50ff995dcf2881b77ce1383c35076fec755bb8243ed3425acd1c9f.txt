"""Reproduce module boundaries, hot reload and fresh-process .blend persistence.

Run with MCAD_ROOT and MCAD_PYTHON under Blender --background --factory-startup
--python-exit-code 1 --python tests/blender_module_smoke.py, or the standalone bpy
Python. The script launches one matching fresh Blender/Python process itself.
"""

import importlib
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
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv" / "bin" / "python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import document_state  # noqa: E402

checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)


def state():
    return bpy.context.scene.mechanical_cad


def width():
    return next(row for row in state().parameters if row.key == "width")


addon.register()
if os.environ.get("MCAD_MODULE_PHASE") == "reopen":
    path = Path(os.environ["MCAD_MODULE_BLEND"])
    bpy.ops.wm.open_mainfile(filepath=str(path))
    check(
        state().document_json == path.with_suffix(".json").read_text(), "Exact JSON survives reopen"
    )
    check(state().status == "DIRTY", "Fresh process requires replay of cached display")
    check(
        addon._owned_objects(bpy.context.scene)[0].hide_viewport,
        "Unverified saved display is hidden",
    )
    check(
        state().geometry_status == "OUTDATED",
        "Saved geometry check is unverified in the new session",
    )
    check(
        bpy.context.scene.unit_settings.length_unit == "MILLIMETERS", "Scene units survive reopen"
    )
    width().value = 67.5
    check(state().status == "DIRTY", "Reopened parameter callback is bound")
    check(addon.regenerate(bpy.context), "Reopened document regenerates after editing")
    bpy.context.view_layer.update()
    obj = addon._owned_objects(bpy.context.scene)[0]
    size_m = obj.dimensions.x * bpy.context.scene.unit_settings.scale_length
    check(
        math.isclose(size_m, 0.0675, rel_tol=1e-6),
        "Scene scale and edited physical dimensions agree",
    )
else:
    check(bpy.ops.mcad.new_demo() == {"FINISHED"}, "Demo succeeds")
    check(bpy.ops.mcad.regenerate.poll(), "Regenerate starts unlocked")
    check(bpy.ops.mcad.add_rectangle.poll(), "Authoring starts unlocked")
    document_state._REPLAY_RUNNING = True
    check(not bpy.ops.mcad.regenerate.poll(), "Replay operator shares module lock")
    check(not bpy.ops.mcad.add_rectangle.poll(), "Authoring operator shares module lock")
    try:
        addon.regenerate(bpy.context)
    except addon.bridge.BridgeError as exc:
        check("already in progress" in str(exc), "Public replay helper shares module lock")
    else:
        raise AssertionError("Public helper ignored the replay lock")
    addon.unregister()
    check(not document_state._REPLAY_RUNNING, "Unregister resets the shared replay lock")
    importlib.reload(addon)
    addon.register()
    width().value = 60
    check(state().status == "DIRTY", "Retained RNA callbacks work after package reload")
    check(addon.regenerate(bpy.context), "Reloaded document regenerates")
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.length_unit = "MILLIMETERS"
    bpy.context.scene.unit_settings.scale_length = 0.01
    check(
        bpy.ops.mcad.check_geometry() == {"FINISHED"},
        "Fresh geometry report is available to persist",
    )
    check(state().geometry_status == "PASSED", "Persisted geometry report starts verified")
    with tempfile.TemporaryDirectory(prefix="mcad-module-") as folder:
        path = Path(folder) / "document.blend"
        path.with_suffix(".json").write_text(state().document_json)
        check(bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"}, "Native scene saves")
        environment = dict(os.environ, MCAD_MODULE_PHASE="reopen", MCAD_MODULE_BLEND=str(path))
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
            command, env=environment, capture_output=True, text=True, timeout=120
        )
        check(child.returncode == 0, f"Fresh-process reopen passes: {child.stdout}\n{child.stderr}")
        check('"phase": "reopen"' in child.stdout, "Fresh process emitted its verified result")
check(
    not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules),
    "No native CAD import",
)
addon.unregister()
print(
    "MCAD_MODULE_RESULT="
    + json.dumps(
        {
            "ok": True,
            "blender": bpy.app.version_string,
            "phase": os.environ.get("MCAD_MODULE_PHASE", "main"),
            "check_count": len(checks),
        }
    )
)
