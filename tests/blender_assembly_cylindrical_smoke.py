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
        kind="cylindrical",
        coordinate="20",
        use_limits=True,
        lower="0",
        upper="50",
        rotation="90",
        use_rotation_limits=True,
        rotation_lower="-180",
        rotation_upper="180",
    )
    == {"FINISHED"},
    "insert cylindrical",
)
joint = data()["joints"][-1]
check(
    joint["rotation"] == math.pi / 2 and joint["coordinate"] == 20,
    "two saved independent coordinates",
)
check(
    bpy.ops.mcad.assembly_joint(
        joint_id=joint["id"],
        coordinate="25",
        rotation="45",
        use_limits=True,
        lower="0",
        upper="50",
        use_rotation_limits=True,
        rotation_lower="-90",
        rotation_upper="90",
    )
    == {"FINISHED"},
    "edit two coordinates",
)
joint = data()["joints"][-1]
check(
    joint["rotation"] == math.pi / 4 and joint["rotation_limits"] == [-math.pi / 2, math.pi / 2],
    "independent angular limits",
)
prior = assembly_storage.document_json
rejected(
    lambda: bpy.ops.mcad.assembly_joint(
        joint_id=joint["id"],
        coordinate="25",
        rotation="100",
        use_rotation_limits=True,
        rotation_lower="-90",
        rotation_upper="90",
    ),
    "reject rotation outside limits",
)
check(assembly_storage.document_json == prior, "rejection preserves canonical assembly")
check(
    bpy.ops.mcad.assembly_sample(joint_id=joint["id"] + ":rotation", values="0, 45, 90")
    == {"FINISHED"},
    "sample independent angular coordinate",
)
result = report()["report"]
check(len(result["poses"]) == 3, "three exact sampled poses")
for row in result["poses"]:
    check(row["pose"]["structural_dof"] == 2, "two structural degrees of freedom")
    check(
        row["pose"]["effective_coordinates"][joint["id"]] == 25,
        "rotation samples retain translation",
    )
check(
    bpy.ops.mcad.assembly_sample(joint_id=joint["id"], values="0, 20, 40") == {"FINISHED"},
    "sample independent axial coordinate",
)
print("CYLINDRICAL_NATIVE_PASS", len(checks))
