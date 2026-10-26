"""Native add-on load/edit/export/save/reopen evidence for current-source example."""

import json
import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
OUT = Path(os.environ["ENCLOSURE_OUTPUT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister  # noqa: E402
from mechanical_cad_blender.hole_recipe import inspect_hole  # noqa: E402

register()


def run(op, **kwargs):
    started = time.monotonic()
    print("START", str(op), flush=True)
    result = op(**kwargs)
    print("DONE", str(op), time.monotonic() - started, flush=True)
    assert result == {"FINISHED"}, (op, result, bpy.context.scene.mechanical_cad.last_action_error)
    return result


if os.environ.get("ENCLOSURE_REOPEN"):
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "Ventilated enclosure current-source.blend"))
    for scene in bpy.data.scenes:
        if scene.name in ["Ventilated base", "Removable duct cover"]:
            bpy.context.window.scene = scene
            run(bpy.ops.mcad.regenerate)
            assert scene.mechanical_cad.status == "READY"
    bpy.context.window.scene = bpy.data.scenes["Removable duct cover"]
    st = bpy.context.scene.mechanical_cad
    run(
        bpy.ops.mcad.named_parameter,
        parameter_name="duct_middle",
        expression="21",
        replace_existing=True,
        original_json=st.document_json,
    )
    run(
        bpy.ops.mcad.named_parameter,
        parameter_name="duct_middle",
        expression="20",
        replace_existing=True,
        original_json=st.document_json,
    )
    if "Seated enclosure assembly" in bpy.data.scenes:
        bpy.context.window.scene = bpy.data.scenes["Seated enclosure assembly"]
        run(bpy.ops.mcad.assembly_replay)
    print("ENCLOSURE_REOPEN_OK", flush=True)
else:
    for name, file in [
        ("Ventilated base", "ventilated_body"),
        ("Removable duct cover", "removable_duct_cover"),
    ]:
        bpy.context.window.scene = bpy.data.scenes.new(name)
        run(bpy.ops.mcad.load_document, filepath=str(OUT / (file + ".mcad.json")))
        st = bpy.context.scene.mechanical_cad
        assert st.status == "READY"
        if name == "Ventilated base":
            run(
                bpy.ops.mcad.named_parameter,
                parameter_name="wall",
                expression="2.6",
                replace_existing=True,
                original_json=st.document_json,
            )
            run(
                bpy.ops.mcad.named_parameter,
                parameter_name="wall",
                expression="2.4",
                replace_existing=True,
                original_json=st.document_json,
            )
        else:
            root = "hole_" + f"{1:032x}"
            values = inspect_hole(json.loads(st.document_json), root)
            values["feature_label"] = values.pop("label")
            args = {
                k: v if k in {"base", "face", "counterbore"} else str(v) for k, v in values.items()
            }
            run(bpy.ops.mcad.round_hole, feature_id=root, **{**args, "diameter": "3.4"})
            run(bpy.ops.mcad.round_hole, feature_id=root, **args)
        run(bpy.ops.mcad.load_document, filepath=str(OUT / (file + ".mcad.json")))
        run(bpy.ops.mcad.export_step, filepath=str(OUT / (file + "_native.step")))
        run(bpy.ops.mcad.export_stl, filepath=str(OUT / (file + "_native.stl")))
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "Enclosure partial native checkpoint.blend"))
    if "override_replay_tolerance" in bpy.ops.mcad.assembly_load.get_rna_type().properties:
        bpy.context.window.scene = bpy.data.scenes.new("Seated enclosure assembly")
        run(
            bpy.ops.mcad.assembly_load,
            filepath=str(OUT / "ventilated_enclosure_seated.mcad-assembly.json"),
            override_replay_tolerance=True,
            replay_tolerance="1e-5",
        )
        run(
            bpy.ops.mcad.assembly_save,
            filepath=str(OUT / "ventilated_enclosure_seated_native.mcad-assembly.json"),
        )
    # Keep portable canonical source alongside the editable scenes.
    text = bpy.data.texts.new("Export-gap assembly variant source")
    text.write((OUT / "ventilated_enclosure.mcad-assembly.json").read_text())
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "Ventilated enclosure current-source.blend"))
    print("ENCLOSURE_NATIVE_CREATE_OK", flush=True)
unregister()
