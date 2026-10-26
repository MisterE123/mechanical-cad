"""Native Blender operator face mate + source update, with real isolated backend."""

import json
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_state,  # noqa: E402
    register,  # noqa: E402
)

register()
scene = bpy.context.scene


def data():
    return assembly_state.read_assembly(scene.mechanical_cad_assembly)


def response():
    return assembly_state.current_display_response(bpy.context)


def done(result):
    assert result == {"FINISHED"}, result


done(bpy.ops.mcad.new_document(name="Face datum source"))
done(bpy.ops.mcad.add_rectangle(width=12, height=8))
done(bpy.ops.mcad.add_extrude(profile=scene.mechanical_cad.active_feature, length=4))
pad = scene.mechanical_cad.active_feature
done(bpy.ops.mcad.assembly_new(name="Face attachment", grounded=True))
part = data()["parts"][0]["id"]
root = data()["grounded_instance"]
done(
    bpy.ops.mcad.assembly_frame(
        part_id=part,
        name="Top face + 2 mm",
        associative=True,
        support_face=pad + "/face/cap.end",
        xyz="0, 0, 2",
    )
)
frame = data()["parts"][0]["mate_frames"][-1]["id"]
done(
    bpy.ops.mcad.assembly_insert(
        part_id=part,
        parent=root,
        parent_frame=frame,
        child_frame="origin",
        kind="fixed",
        name="Mounted part",
    )
)
child = data()["instances"][-1]["id"]
assert abs(response()["report"]["base_pose"]["transforms"][child]["xyz_mm"][2] - 6) < 1e-8
# Explicit canonical source edit, not display mesh edits.
part_doc = json.loads(scene.mechanical_cad.document_json)
next(f for f in part_doc["features"] if f["id"] == pad)["params"]["length"] = 14
scene.mechanical_cad.document_json = json.dumps(part_doc)
done(bpy.ops.mcad.assembly_update_source())
assert abs(response()["report"]["base_pose"]["transforms"][child]["xyz_mm"][2] - 16) < 1e-8
assert data()["parts"][0]["mate_frames"][-1]["support_face"] == pad + "/face/cap.end"
print("MCAD_ASSOCIATIVE_ASSEMBLY_FRAME_OK")
