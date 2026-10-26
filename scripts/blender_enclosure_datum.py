"""Native saved-file proof for the datum-driven primary model and named contact."""

import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
OUT = Path(os.environ["ENCLOSURE_OUTPUT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import assembly_state, document_state, register, unregister  # noqa: E402

register()
receipt = {"source": str(ROOT), "blender": bpy.app.version_string, "operations": []}


def run(op, **kwargs):
    name = str(op)
    print("START", name, flush=True)
    t = time.monotonic()
    result = op(**kwargs)
    elapsed = time.monotonic() - t
    print("DONE", name, elapsed, result, flush=True)
    assert result == {"FINISHED"}, (name, result)
    receipt["operations"].append({"operator": name, "seconds": elapsed, "result": sorted(result)})


def exact_volume():
    result = document_state.current_part_result(bpy.context)
    assert result is not None
    return next(
        f["stats"]["volume"] for f in result["features"] if f["id"] == result["active_feature"]
    )


main = OUT / "Ventilated enclosure current-source.blend"
if os.environ.get("ENCLOSURE_PRIMARY_REOPEN"):
    run(bpy.ops.wm.open_mainfile, filepath=str(main))
    for name in ["Ventilated base", "Removable duct cover"]:
        bpy.context.window.scene = bpy.data.scenes[name]
        run(bpy.ops.mcad.regenerate)
        assert bpy.context.scene.mechanical_cad.status == "READY"
    bpy.context.window.scene = bpy.data.scenes["Seated enclosure assembly"]
    # Replay operator is modal. In headless proof use the same synchronous native
    # add-on replay service, then a real native Check Current Pose operator.
    start = time.monotonic()
    response = assembly_state.replay(bpy.context)
    assert response["ok"]
    receipt["saved_assembly_replay_seconds"] = time.monotonic() - start
    run(bpy.ops.mcad.assembly_check)
    report = json.loads(bpy.context.scene.mechanical_cad_assembly.report_json)["report"]
    assert report["policy_accepted"] and not report["passed"] and report["complete"]
    assert (
        json.loads(bpy.context.scene.mechanical_cad_assembly.document_json)["replay_tolerance_mm"]
        == 1e-5
    )
    marker = "ENCLOSURE_DATUM_REOPEN_OK"
else:
    regression = OUT / "repros" / "Grouped-hole workflow regression.blend"
    if not regression.exists():
        shutil.copy2(main, regression)
    run(bpy.ops.wm.open_mainfile, filepath=str(regression))
    for name in ["Ventilated base", "Removable duct cover"]:
        bpy.context.window.scene = bpy.data.scenes[name]
        run(bpy.ops.mcad.regenerate)
        assert bpy.context.scene.mechanical_cad.status == "READY"
    receipt["grouped_saved_parts_reopened"] = True
    for name, file in [
        ("Ventilated base", "ventilated_body_datum"),
        ("Removable duct cover", "removable_duct_cover_datum"),
    ]:
        bpy.context.window.scene = bpy.data.scenes[name]
        run(bpy.ops.mcad.load_document, filepath=str(OUT / (file + ".mcad.json")))
        state = bpy.context.scene.mechanical_cad
        if name == "Removable duct cover":
            initial = exact_volume()
            run(
                bpy.ops.mcad.named_parameter,
                parameter_name="mount_diameter",
                expression="3.6",
                replace_existing=True,
                original_json=state.document_json,
            )
            expected = initial - 4 * math.pi / 4 * (3.6**2 - 3.2**2) * (3.6 - 1.6)
            actual = exact_volume()
            assert abs(actual - expected) < 1e-5, (actual, expected)
            receipt["datum_edit_volume_mm3"] = actual
            run(
                bpy.ops.mcad.named_parameter,
                parameter_name="mount_diameter",
                expression="3.2",
                replace_existing=True,
                original_json=state.document_json,
            )
            run(bpy.ops.mcad.load_document, filepath=str(OUT / (file + ".mcad.json")))
            run(bpy.ops.mcad.export_step, filepath=str(OUT / (file + "_native.step")))
    bpy.context.window.scene = bpy.data.scenes["Seated enclosure assembly"]
    run(
        bpy.ops.mcad.assembly_load,
        filepath=str(OUT / "ventilated_enclosure_datum.mcad-assembly.json"),
    )
    run(bpy.ops.mcad.assembly_check)
    response = json.loads(bpy.context.scene.mechanical_cad_assembly.report_json)
    report = response["report"]
    assert report["policy_accepted"] and not report["passed"] and report["complete"]
    receipt["contact_report"] = report
    run(
        bpy.ops.mcad.assembly_export_step,
        filepath=str(OUT / "ventilated_enclosure_datum_native.step"),
    )
    run(bpy.ops.wm.save_as_mainfile, filepath=str(main))
    marker = "ENCLOSURE_DATUM_NATIVE_OK"
receipt["marker"] = marker
(
    OUT
    / (
        "native_datum_reopen.json"
        if os.environ.get("ENCLOSURE_PRIMARY_REOPEN")
        else "native_datum_create.json"
    )
).write_text(json.dumps(receipt, indent=2) + "\n")
print(marker, flush=True)
unregister()
