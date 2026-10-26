"""Verify the distributable add-on ZIP in an isolated Blender user directory.

Set MCAD_ADDON_ZIP, MCAD_ROOT, MCAD_PYTHON and BLENDER_USER_SCRIPTS to temporary
locations before launching Blender or the standalone bpy interpreter.
"""

import hashlib
import json
import os
import runpy
import subprocess
import sys
import tomllib
from pathlib import Path

import bpy

root = Path(os.environ["MCAD_ROOT"]).resolve()
archive = Path(os.environ["MCAD_ADDON_ZIP"]).resolve()
user_scripts = Path(os.environ["BLENDER_USER_SCRIPTS"]).resolve()
actual_scripts = Path(bpy.utils.user_resource("SCRIPTS", create=True)).resolve()
assert actual_scripts == user_scripts, (actual_scripts, user_scripts)
assert archive.is_file()
assert bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=True) == {"FINISHED"}
assert bpy.ops.preferences.addon_enable(module="mechanical_cad_blender") == {"FINISHED"}
preferences = bpy.context.preferences.addons["mechanical_cad_blender"].preferences
preferences.project_root = str(root)
preferences.python_executable = os.environ["MCAD_PYTHON"]
# Start with the actual empty-document path, not only the populated demo. This
# caught an apparent GUI redraw delay during release review; the canonical state
# must be ready immediately after the installed operator returns successfully.
state = bpy.context.scene.mechanical_cad
assert state.document_json == ""
assert bpy.ops.mcad.new_document(name="Installed blank creation probe") == {"FINISHED"}
blank = json.loads(state.document_json)
assert blank["name"] == "Installed blank creation probe"
assert blank["features"] == []
assert blank["active_feature"] is None
assert state.status == "READY", state.error
assert bpy.ops.mcad.new_demo() == {"FINISHED"}
assert state.status == "READY", state.error
assert abs(state.volume - 11497.345175425633) < 0.01
# Exercise the packaged schema-2 modules and icon resources, not source imports.
import mechanical_cad_blender as installed  # noqa: E402
from mechanical_cad_blender.sketch_draft import RectangleDraft  # noqa: E402

assert Path(installed.__file__).resolve().is_relative_to(user_scripts)
expected_version = tuple(
    int(v)
    for v in os.environ.get(
        "MCAD_EXPECTED_VERSION",
        tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"],
    ).split(".")
)
assert installed.bl_info["version"] == expected_version
# Add-on metadata alone cannot identify an older configured sidecar. Verify the
# actual interpreter/import environment as well as the native behavior below.
backend_probe = subprocess.run(
    [
        os.environ["MCAD_PYTHON"],
        "-c",
        "import hashlib,json,pathlib,mechanical_cad; "
        "from mechanical_cad import sketch_solver; "
        "p=pathlib.Path(sketch_solver.__file__).resolve(); "
        "print(json.dumps({'version':mechanical_cad.__version__, 'solver_path':str(p), "
        "'solver_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))",
    ],
    cwd=root,
    env=dict(os.environ, PYTHONPATH=str(root / "src")),
    text=True,
    capture_output=True,
    check=True,
    timeout=30,
)
backend = json.loads(backend_probe.stdout)
expected_solver = root / "src/mechanical_cad/sketch_solver.py"
assert backend["version"] == ".".join(map(str, expected_version)), backend
assert Path(backend["solver_path"]) == expected_solver, backend
assert backend["solver_sha256"] == hashlib.sha256(expected_solver.read_bytes()).hexdigest()
print("MCAD_INSTALLED_BACKEND=" + json.dumps(backend, sort_keys=True))
assert (Path(installed.__file__).parent / "assets/icons/manifest.json").is_file()
assert bpy.ops.mcad.load_document(filepath=str(root / "examples/viewport_rectangle.mcad.json")) == {
    "FINISHED"
}
assert state.status == "READY", state.error
assert abs(state.volume - 12000) < 0.01
before = json.loads(state.document_json)
draft = RectangleDraft(state.document_json, feature_id="sketch_1", is_edit=True)
assert draft.width_text == "40.0"
parameter = next(item for item in state.parameters if item.key == "sketch_1_width")
parameter.expression = "60"
assert state.status == "DIRTY"
assert bpy.ops.mcad.regenerate() == {"FINISHED"}
assert abs(state.volume - 18000) < 0.01
assert json.loads(state.document_json)["features"] == before["features"]
assert bpy.ops.mcad.check_geometry() == {"FINISHED"}
assert state.geometry_status == "PASSED"
assert not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules)
# Exercise packaged assembly source, typed verification, and native glyph assets.
from mechanical_cad_blender import assembly_state, palette_shapes  # noqa: E402

assert all(palette_shapes.load_shape(action) for action in palette_shapes.ACTIONS)
assert installed.bl_info["blender"] == (5, 2, 0)
part_before = state.document_json
assert bpy.ops.mcad.assembly_load(
    filepath=str(root / "examples/clevis_hinge/assembly.mcad-assembly.json")
) == {"FINISHED"}
assembly = bpy.context.scene.mechanical_cad_assembly
assert state.document_json == part_before  # Separate working Part remains untouched.
assert assembly_state.display_is_current(bpy.context)
assert assembly.verification_status == "UNCHECKED"
assert bpy.ops.mcad.assembly_check() == {"FINISHED"}
assert assembly_state.report_is_current(bpy.context)
report = json.loads(assembly.report_json)["report"]
assert report["complete"] and report["passed"]
assert len(report["poses"][0]["pairs"]) == 3
assert report["continuous_collision_guarantee"] is False
assert not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules)

# Reuse the full public-entry dispatch gate against already imported installed
# modules. The test script is a harness only; every addon module must remain
# rooted in this isolated installed package, never the source checkout.
installed.unregister()
runpy.run_path(str(root / "tests/blender_general_dispatch_smoke.py"), run_name="__main__")
# Exercise new relation transactions and confirmation routes from the exact ZIP.
# These are programmatic/native checks; ordinary GUI clicks remain a separate gate.
for harness in (
    "blender_constraint_actions_smoke.py",
    "blender_constraint_ui_smoke.py",
    "blender_dof_cycle_guard_smoke.py",
):
    runpy.run_path(str(root / "tests" / harness), run_name="__main__")
for name, module in tuple(sys.modules.items()):
    if name == "mechanical_cad_blender" or name.startswith("mechanical_cad_blender."):
        filename = getattr(module, "__file__", None)
        if filename:
            assert Path(filename).resolve().is_relative_to(user_scripts), (name, filename)
assert bpy.ops.preferences.addon_disable(module="mechanical_cad_blender") == {"FINISHED"}
print(
    "MCAD_INSTALL_RESULT="
    + json.dumps({"ok": True, "blender": bpy.app.version_string, "archive": archive.name})
)
