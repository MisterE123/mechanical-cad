"""Two-process native add-on proof and editable deliverable, background only."""

import json
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Quaternion

ROOT = Path(os.environ["MCAD_ROOT"])
OUT = Path(os.environ["MCAD_GEARBOX_OUT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    assembly_pending,
    assembly_state,
    document_state,
    execution_lease,
    history_rebuild,
    sketch_pending,
    workspace,
)

assert bpy.app.background
if not os.environ.get("MCAD_GEARBOX_REOPEN"):
    bpy.ops.wm.read_homefile(use_empty=True)
assert bpy.ops.preferences.addon_enable(module="mechanical_cad_blender") == {"FINISHED"}
prefs = bpy.context.preferences.addons["mechanical_cad_blender"].preferences
prefs.timeout_seconds = float(os.environ.get("MCAD_GEARBOX_TIMEOUT", "60"))
prefs.project_root = str(ROOT)
prefs.python_executable = os.environ["MCAD_PYTHON"]
checks = []
stage_durations = []
last_check_time = time.monotonic()


def check(value, label):
    global last_check_time
    elapsed = time.monotonic() - last_check_time
    last_check_time = time.monotonic()
    assert value, label
    checks.append(label)
    stage_durations.append({"stage": label, "seconds_since_previous_stage": elapsed})
    print("GEARBOX_NATIVE_CHECK", label, f"{elapsed:.3f}s", flush=True)


def drain():
    deadline = time.monotonic() + 180
    while history_rebuild._PENDING is not None or execution_lease.is_busy():
        assert time.monotonic() < deadline, "rebuild timeout"
        history_rebuild._tick()
        assembly_pending.reap(bpy.context)
        sketch_pending.reap()
        time.sleep(0.02)
    if bpy.app.timers.is_registered(history_rebuild._tick):
        bpy.app.timers.unregister(history_rebuild._tick)


def style():
    colors = {
        "housing": (0.16, 0.24, 0.30, 1),
        "cover": (0.32, 0.42, 0.50, 1),
        "input_gear": (0.95, 0.35, 0.08, 1),
        "middle_wheel": (0.98, 0.65, 0.10, 1),
        "middle_pinion": (0.98, 0.65, 0.10, 1),
        "output_wheel": (0.12, 0.60, 0.78, 1),
    }
    for obj in bpy.context.scene.objects:
        id = obj.get(assembly_display.INSTANCE_KEY)
        if id:
            obj.color = colors.get(id, (0.6, 0.6, 0.62, 1))
            if id == "cover":
                obj.hide_set(True)
            if id == "housing":
                obj.display_type = "WIRE"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.shading.color_type = "OBJECT"
                area.spaces.active.region_3d.view_location = (70, 0, 20)
                area.spaces.active.region_3d.view_distance = 300
                area.spaces.active.region_3d.view_rotation = Quaternion(
                    (0.8205, 0.4247, 0.1759, 0.3399)
                )
                area.spaces.active.clip_end = 10000


if os.environ.get("MCAD_GEARBOX_REOPEN_UPDATED"):
    check(
        bpy.ops.wm.open_mainfile(filepath=str(OUT / "reopened_wall45_updated_assembly.blend"))
        == {"FINISHED"},
        "independent process reopen revised assembly",
    )
    expected_updated = json.loads(
        (OUT / "native_wall45_updated_assembly.mcad-assembly.json").read_text()
    )
    check(
        json.loads(bpy.context.scene.mechanical_cad_assembly.document_json) == expected_updated,
        "revised canonical assembly round-trip",
    )
    drain()
    check(
        assembly_state.display_is_current(bpy.context),
        "revised assembly freshly revalidated after reopen",
    )
elif not os.environ.get("MCAD_GEARBOX_REOPEN"):
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = "MILLIMETERS"
    check(
        bpy.ops.mcad.assembly_load(filepath=str(OUT / "reduction_gearbox.mcad-assembly.json"))
        == {"FINISHED"},
        "native Load Assembly",
    )
    check(assembly_state.display_is_current(bpy.context), "fresh exact assembly display")
    model = json.loads(scene.mechanical_cad_assembly.document_json)
    check(
        len(model["instances"]) == 9 and len(model["gear_relations"]) == 2,
        "9 instances and chained gear relations retained",
    )
    check(
        bpy.ops.mcad.assembly_open_part(part_id="pinion", confirmed=True) == {"FINISHED"},
        "open embedded editable pinion Part",
    )
    check(
        bpy.ops.mcad.export_stl(filepath=str(OUT / "native_pinion_export.stl")) == {"FINISHED"},
        "native source-Part STL export",
    )
    check(
        json.loads(scene.mechanical_cad.document_json)["features"][0]["kind"] == "spur_gear",
        "canonical gear feature not imported mesh",
    )
    # Keep assembly workspace active; working Part remains an editable source.
    bpy.context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    bpy.context.workspace[workspace.ROLE_KEY] = "ASSEMBLY"
    scene.mechanical_cad.document_path = ""
    scene.mechanical_cad_assembly.document_path = ""
    # Hide the competing working-Part display only, no canonical data change.
    for obj in scene.objects:
        if obj.get("mechanical_cad_owner"):
            obj.hide_set(True)
    style()
    text = bpy.data.texts.new("START HERE - reduction gearbox")
    text.write(
        "Editable two-stage 4:1 demonstrator. Install Mechanical CAD Linux 1.17 first.\nThe housing is wireframe and the cover is hidden for inspection, not removed.\nAssembly panel: Replay; edit Input Rotation to drive both stages.\nOpen Embedded Source as Working Part, edit parameters, Replay, then Update All Instances.\nShafts are reference-only. Export each gear Part twice; never print the entire assembly.\nSee the supplied DESIGN_AND_USE.md for limits, example fit allowances, and evidence.\n"
    )
    check(
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "reduction_gearbox.blend")) == {"FINISHED"},
        "save editable blend",
    )
    (OUT / "native_saved_assembly.json").write_text(scene.mechanical_cad_assembly.document_json)
else:
    check(
        bpy.ops.wm.open_mainfile(filepath=str(OUT / "reduction_gearbox.blend")) == {"FINISHED"},
        "independent process reopen",
    )
    expected = json.loads((OUT / "native_saved_assembly.json").read_text())
    check(
        json.loads(bpy.context.scene.mechanical_cad_assembly.document_json) == expected,
        "all embedded sources and relations round-trip",
    )
    drain()
    check(
        assembly_state.display_is_current(bpy.context), "reopened assembly revalidated from sources"
    )
    check(
        bpy.ops.mcad.assembly_open_part(part_id="gearbox_housing", confirmed=True) == {"FINISHED"},
        "open embedded shelled housing",
    )
    state = bpy.context.scene.mechanical_cad
    wall = next(row for row in state.parameters if row.key == "wall")
    wall.value = 4.5
    check(document_state.regenerate(bpy.context), "edit upstream wall to 4.5 mm and regenerate")
    edited = json.loads(state.document_json)
    check(float(edited["parameters"]["wall"]) == 4.5, "upstream numeric parameter persisted")
    check(state.volume > 179010.4695, "changed housing volume is fresh")
    check(
        bpy.ops.mcad.export_step(filepath=str(OUT / "native_wall45_housing.step")) == {"FINISHED"},
        "native revised housing STEP export",
    )
    check(
        state.geometry_status == "PASSED" and (OUT / "native_wall45_housing.step").is_file(),
        "revised STEP actually written after passed checks",
    )
    check(
        bpy.ops.mcad.assembly_update_source() == {"FINISHED"},
        "explicit Update All Instances after wall edit",
    )
    updated = json.loads(bpy.context.scene.mechanical_cad_assembly.document_json)
    updated_housing = next(
        source["document"]
        for source in updated["part_sources"]
        if source["source_document_id"] == "gearbox_housing"
    )
    check(
        float(updated_housing["parameters"]["wall"]) == 4.5,
        "accepted assembly contains revised housing source",
    )
    check(
        updated["gear_relations"] == expected["gear_relations"],
        "source update preserves both gear relations",
    )
    check(
        assembly_state.display_is_current(bpy.context), "revised full assembly display is current"
    )
    (OUT / "native_wall45_updated_assembly.mcad-assembly.json").write_text(
        bpy.context.scene.mechanical_cad_assembly.document_json
    )
    # Proof of an edit goes in a separate file; do not overwrite nominal assembly.
    check(
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "reopened_wall45_updated_assembly.blend"))
        == {"FINISHED"},
        "save revised assembly proof",
    )
(
    OUT
    / (
        "native_updated_reopen_report.json"
        if os.environ.get("MCAD_GEARBOX_REOPEN_UPDATED")
        else "native_reopen_report.json"
        if os.environ.get("MCAD_GEARBOX_REOPEN")
        else "native_build_report.json"
    )
).write_text(
    json.dumps(
        {
            "checks": checks,
            "stage_durations": stage_durations,
            "timeout_seconds": prefs.timeout_seconds,
            "canonical_assembly_bytes": len(
                bpy.context.scene.mechanical_cad_assembly.document_json.encode()
            ),
            "blender": bpy.app.version_string,
            "native_cad_imported_in_blender": any(
                x in sys.modules for x in ("OCP", "mechanical_cad")
            ),
        },
        indent=2,
    )
    + "\n"
)
check(
    not any(x in sys.modules for x in ("OCP", "mechanical_cad")), "native CAD isolated from Blender"
)
print("GEARBOX_NATIVE_OK", flush=True)
