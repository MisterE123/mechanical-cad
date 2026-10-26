"""Native selected chamfer picking, attached profile, edit and .blend reopen."""

import json
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import document_state, face_pick, register, unregister  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad
path = os.environ["MCAD_BLEND_SURFACE_FILE"]


def run(operator, **kwargs):
    result = operator(**kwargs)
    assert result == {"FINISHED"}, (result, state.last_action_error)
    assert state.status == "READY", (state.status, state.last_action_error)
    return state.active_feature


if os.environ.get("MCAD_BLEND_SURFACE_PHASE") == "reopen":
    bpy.ops.wm.open_mainfile(filepath=path)
    state = bpy.context.scene.mechanical_cad
    run(bpy.ops.mcad.regenerate)
    doc = json.loads(state.document_json)
    assert doc["features"][-1]["support_face"].endswith("/face/blend.surface")
    assert doc["features"][2]["params"]["distance"] == "3"
    print("MCAD_BLEND_SURFACE_REOPEN_OK")
else:
    run(bpy.ops.mcad.new_document, name="Reusable selected bevel")
    profile = run(bpy.ops.mcad.add_rectangle, width=40, height=30)
    base = run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
    pair = [base + "/face/cap.end", base + "/face/side.y_min"]
    blend = run(
        bpy.ops.mcad.add_solid_feature,
        kind="chamfer",
        base=base,
        edge_mode="PAIR",
        face_a=pair[0],
        face_b=pair[1],
        distance="2",
        original_json=state.document_json,
    )
    feature = document_state.current_part_result(bpy.context)["features"][-1]
    face_id = blend + "/face/blend.surface"
    triangle = feature["mesh"]["triangle_face_ids"].index(face_id)
    picked = face_pick.resolve_triangle(feature, triangle)
    assert picked["provenance"]["relation"] == "generated_from_selected_edge"
    assert abs(state.volume - 11920) < 1e-6
    run(
        bpy.ops.mcad.add_solid_feature,
        kind="sketch_face_circle",
        support=blend,
        support_face=face_id,
        radius="0.3",
        original_json=state.document_json,
    )
    run(
        bpy.ops.mcad.edit_solid_feature,
        kind="chamfer",
        feature_id=blend,
        base=base,
        edge_mode="PAIR",
        face_a=pair[0],
        face_b=pair[1],
        distance="3",
        original_json=state.document_json,
    )
    rows = document_state.current_part_result(bpy.context)["features"]
    assert rows[-1]["status"] == "ok"
    assert abs(rows[2]["stats"]["volume"] - 11820) < 1e-6
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("MCAD_BLEND_SURFACE_CREATE_OK")
unregister()
