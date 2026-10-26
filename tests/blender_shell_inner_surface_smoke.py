"""Native inner-wall face picker, sketch, thickness edit and separate reopen."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import document_state, face_pick, register, solid_operators, unregister  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad
path = os.environ["MCAD_SHELL_INNER_FILE"]


def run(operator, **kwargs):
    result = operator(**kwargs)
    assert result == {"FINISHED"}, (result, state.last_action_error)
    assert state.status == "READY", (state.status, state.last_action_error)
    return state.active_feature


if os.environ.get("MCAD_SHELL_INNER_PHASE") == "reopen":
    bpy.ops.wm.open_mainfile(filepath=path)
    state = bpy.context.scene.mechanical_cad
    run(bpy.ops.mcad.regenerate)
    doc = json.loads(state.document_json)
    assert "/face/shell.inner." in doc["features"][-1]["support_face"]
    assert doc["features"][2]["params"]["thickness"] == "2"
    print("MCAD_SHELL_INNER_REOPEN_OK")
else:
    run(bpy.ops.mcad.new_document, name="Inner enclosure wall sketch")
    profile = run(bpy.ops.mcad.add_rectangle, width=20, height=15)
    base = run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
    opening = base + "/face/cap.end"
    shell = run(
        bpy.ops.mcad.add_solid_feature,
        kind="shell",
        base=base,
        shell_mode="OPEN",
        opening_face=opening,
        thickness="1",
        original_json=state.document_json,
    )
    feature = document_state.current_part_result(bpy.context)["features"][-1]
    inner = next(
        f
        for f in feature["topology"]
        if f["provenance"]["relation"] == "offset_from_face"
        and f["provenance"]["source_id"] == base + "/face/side.x_min"
    )
    choices = solid_operators._face_choices(
        SimpleNamespace(kind="sketch_face_circle", support=shell), bpy.context
    )
    label = next(item[1] for item in choices if item[0] == inner["id"])
    assert label.startswith("Inner wall from ") and "shell.inner." not in label
    triangle = feature["mesh"]["triangle_face_ids"].index(inner["id"])
    assert face_pick.resolve_triangle(feature, triangle)["id"] == inner["id"]
    assert abs(state.volume - 894) < 1e-6
    run(
        bpy.ops.mcad.add_solid_feature,
        kind="sketch_face_circle",
        support=shell,
        support_face=inner["id"],
        radius="1",
        original_json=state.document_json,
    )
    run(
        bpy.ops.mcad.edit_solid_feature,
        kind="shell",
        feature_id=shell,
        base=base,
        shell_mode="OPEN",
        opening_face=opening,
        thickness="2",
        original_json=state.document_json,
    )
    rows = document_state.current_part_result(bpy.context)["features"]
    assert rows[-1]["status"] == "ok"
    assert abs(rows[2]["stats"]["volume"] - 1592) < 1e-6
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("MCAD_SHELL_INNER_CREATE_OK")
unregister()
