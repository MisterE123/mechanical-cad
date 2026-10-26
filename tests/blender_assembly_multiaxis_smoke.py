"""Native 5.2 operator workflow, authored from scratch, using the real sidecar.

Run with --background --factory-startup --python-exit-code 1. This does not claim
interactive GUI/Undo review; those are separately exercised by the UI reviewer.
"""

import copy
import json
import math
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402  # noqa: E402
    assembly_operators,
    assembly_properties,
    assembly_state,
    assembly_ui,
    assembly_verification_ui,
    register,
)

checks = []


def check(value, label):
    if not value:
        raise AssertionError(label)
    checks.append(label)


def rejected(operation, label):
    try:
        result = operation()
    except RuntimeError:
        checks.append(label)
        return
    check(result == {"CANCELLED"}, label)


def data():
    return assembly_state.read_assembly(bpy.context.scene.mechanical_cad_assembly)


def report():
    return json.loads(bpy.context.scene.mechanical_cad_assembly.report_json)


register()
extra_classes = []
for cls in (
    *assembly_properties.CLASSES,
    *assembly_operators.CLASSES,
    *assembly_verification_ui.CLASSES,
    *assembly_ui.CLASSES,
):
    if not getattr(cls, "is_registered", False):
        bpy.utils.register_class(cls)
        extra_classes.append(cls)
extra_storage = not hasattr(bpy.types.Scene, "mechanical_cad_assembly")
if extra_storage:
    bpy.types.Scene.mechanical_cad_assembly = bpy.props.PointerProperty(
        type=assembly_properties.MCAD_AssemblyState
    )
scene = bpy.context.scene
part_state = scene.mechanical_cad
assembly_storage = scene.mechanical_cad_assembly
unrelated = bpy.data.objects.new("Unrelated user object", None)
scene.collection.objects.link(unrelated)

# Actual ordinary Part-authoring operators; no canned assembly/part fixture.
check(bpy.ops.mcad.new_document(name="Authored bracket") == {"FINISHED"}, "new user Part")
check(
    bpy.ops.mcad.add_rectangle(width=12, height=8, x=0, y=0, z=0) == {"FINISHED"}, "user rectangle"
)
profile = part_state.active_feature
check(bpy.ops.mcad.add_extrude(profile=profile, length=4) == {"FINISHED"}, "user extrusion")
working_before = part_state.document_json
rejected(
    lambda: bpy.ops.mcad.assembly_new(name="Bracket assembly", grounded=False),
    "first root requires explicit ground confirmation",
)
check(not assembly_storage.document_json, "rejected grounding creates no assembly")
check(
    bpy.ops.mcad.assembly_new(name="Bracket assembly", instance_name="Base bracket", grounded=True)
    == {"FINISHED"},
    "new grounded assembly",
)
check(part_state.document_json == working_before, "capturing preserves exact working Part text")
root = data()["grounded_instance"]
part = data()["parts"][0]["id"]
source_before = copy.deepcopy(data()["part_sources"][0])
check(
    bpy.ops.mcad.assembly_insert(
        part_id=part,
        parent=root,
        parent_frame="origin",
        child_frame="origin",
        kind="planar",
        translation_x="20",
        translation_y="30",
        rotation="90",
        use_translation_x_limits=True,
        translation_x_lower="0",
        translation_x_upper="50",
    )
    == {"FINISHED"},
    "insert planar with XY and rotation",
)
plane = data()["joints"][-1]
check(
    plane["translation_x"] == 20
    and plane["translation_y"] == 30
    and plane["rotation"] == math.pi / 2,
    "saved planar axes",
)
check("coordinate" not in plane, "no ambiguous planar scalar")
check(
    bpy.ops.mcad.assembly_joint(
        joint_id=plane["id"],
        translation_x="25",
        translation_y="35",
        rotation="45",
        use_translation_x_limits=True,
        translation_x_lower="0",
        translation_x_upper="50",
    )
    == {"FINISHED"},
    "edit planar axes",
)
check(
    bpy.ops.mcad.assembly_insert(
        part_id=part,
        parent=root,
        parent_frame="origin",
        child_frame="origin",
        kind="spherical",
        rotation_x="30",
        rotation_y="45",
        rotation="60",
        use_rotation_x_limits=True,
        rotation_x_lower="-90",
        rotation_x_upper="90",
    )
    == {"FINISHED"},
    "insert ball with three explicit angles",
)
ball = data()["joints"][-1]
check(
    ball["rotation_x"] == math.pi / 6
    and ball["rotation_y"] == math.pi / 4
    and "coordinate" not in ball,
    "saved ball axes",
)
check(
    bpy.ops.mcad.assembly_joint(
        joint_id=ball["id"],
        rotation_x="15",
        rotation_y="25",
        rotation="35",
        use_rotation_y_limits=True,
        rotation_y_lower="-40",
        rotation_y_upper="40",
    )
    == {"FINISHED"},
    "edit ball axes and limits",
)
prior = assembly_storage.document_json
rejected(
    lambda: bpy.ops.mcad.assembly_joint(
        joint_id=ball["id"],
        rotation_y="70",
        use_rotation_y_limits=True,
        rotation_y_lower="-40",
        rotation_y_upper="40",
    ),
    "reject ball axis limit violation",
)
check(assembly_storage.document_json == prior, "rejected ball edit preserves source")
for identifier, axis, values in [
    (plane["id"], "translation_x", "0, 20, 40"),
    (plane["id"], "translation_y", "0, 30"),
    (plane["id"], "rotation", "0, 90"),
    (ball["id"], "rotation_x", "0, 90"),
    (ball["id"], "rotation_y", "0, 30"),
    (ball["id"], "rotation", "0, 90"),
]:
    check(
        bpy.ops.mcad.assembly_sample(joint_id=identifier + ":" + axis, values=values)
        == {"FINISHED"},
        "sample " + axis,
    )
    result = report()["report"]
    check(
        all(row["pose"]["structural_dof"] == 6 for row in result["poses"]),
        "combined six structural degrees of freedom",
    )
check(assembly_storage.document_json == prior, "sampling does not mutate authored axes")
bpy.ops.wm.save_as_mainfile(filepath="/tmp/mcad_multiaxis_roundtrip.blend")
bpy.ops.wm.open_mainfile(filepath="/tmp/mcad_multiaxis_roundtrip.blend")
check(
    bpy.context.scene.mechanical_cad_assembly.document_json == prior,
    "blend reopen preserves exact axes and limits",
)
print("MULTIAXIS_NATIVE_PASS", len(checks))
