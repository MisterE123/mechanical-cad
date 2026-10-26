"""Native 5.2 operator workflow, authored from scratch, using the real sidecar.

Run with --background --factory-startup --python-exit-code 1. This does not claim
interactive GUI/Undo review; those are separately exercised by the UI reviewer.
"""

import copy
import json
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
from types import SimpleNamespace  # noqa: E402

from mechanical_cad_blender import assembly_edit  # noqa: E402
from mechanical_cad_blender.assembly_operator_helpers import joint_help_lines  # noqa: E402

for parent, name in [(root, "Arm"), (None, "Finger"), (root, "Sibling")]:
    parent = parent or data()["instances"][-1]["id"]
    check(
        bpy.ops.mcad.assembly_insert(
            part_id=part,
            parent=parent,
            parent_frame="origin",
            child_frame="origin",
            kind="fixed",
            name=name,
            joint_name=name + " mount",
        )
        == {"FINISHED"},
        "insert " + name,
    )
root, arm, finger, sibling = [row["id"] for row in data()["instances"]]
a = data()
policy = {"linear_tolerance_mm": 1e-6, "volume_tolerance_mm3": 1e-9, "linear_deflection_mm": 0.1}
a = assembly_edit.edit_verification_preset(
    a,
    name="Retained policy",
    kind="clearance",
    policy=policy,
    pair=[root, arm],
    minimum_mm=2,
    requirement_name="Arm clearance",
)
preset = a["verification_presets"][-1]["id"]
a = assembly_edit.edit_verification_preset(
    a,
    preset_id=preset,
    name="Retained policy",
    kind="clearance",
    policy=policy,
    pair=[root, sibling],
    minimum_mm=3,
    requirement_name="Sibling clearance",
)
a = assembly_edit.edit_verification_preset(
    a,
    name="Removed policy",
    kind="clearance",
    policy=policy,
    pair=[arm, finger],
    minimum_mm=4,
    requirement_name="Finger clearance",
)
assembly_state.commit_candidate(bpy.context, a)
prior = assembly_storage.document_json
parts = copy.deepcopy(data()["parts"])
rejected(
    lambda: bpy.ops.mcad.assembly_remove_component(instance_id=arm),
    "explicit branch removal confirmation required",
)
rejected(
    lambda: bpy.ops.mcad.assembly_remove_component(instance_id=root, confirmed=True),
    "root removal rejected",
)
check(assembly_storage.document_json == prior, "rejections preserve canonical assembly")
candidate, impact = assembly_edit.remove_component(data(), arm)
check(
    [r["name"] for r in impact["instances"]] == ["Arm", "Finger"],
    "preview names the affected components",
)
check(
    [r["name"] for r in impact["joints"]] == ["Arm mount", "Finger mount"],
    "preview names dependent joints",
)
check(impact["active_preset_cleared"], "preview exposes active policy removal")
fake = SimpleNamespace(
    confirmed=True,
    _candidate=candidate,
    _impact=impact,
    _expected=prior + " ",
    report=lambda *args: None,
)
check(
    assembly_operators.MCAD_OT_assembly_remove_component.execute(fake, bpy.context)
    == {"CANCELLED"},
    "stale preview rejected",
)
check(assembly_storage.document_json == prior, "stale preview preserves original")
original_runner = assembly_state._run_sidecar


def fail_replay(*args, **kwargs):
    raise RuntimeError("Injected removal replay failure")


assembly_state._run_sidecar = fail_replay
try:
    rejected(
        lambda: bpy.ops.mcad.assembly_remove_component(instance_id=arm, confirmed=True),
        "failed candidate replay rejected",
    )
finally:
    assembly_state._run_sidecar = original_runner
check(assembly_storage.document_json == prior, "failed replay keeps original branch and policies")
bpy.ops.wm.save_as_mainfile(filepath="/tmp/mcad_remove_before.blend")
bpy.ops.wm.open_mainfile(filepath="/tmp/mcad_remove_before.blend")
check(
    bpy.ops.mcad.assembly_remove_component(instance_id=arm, confirmed=True) == {"FINISHED"},
    "remove branch after reopening",
)
a = data()
check([r["id"] for r in a["instances"]] == [root, sibling], "only requested branch removed")
check(a["parts"] == parts, "reusable definitions retained")
check(
    len(a["joints"]) == 1 and a["joints"][0]["name"] == "Sibling mount", "remaining joint retained"
)
check(a["active_verification_preset"] is None, "removed active preset cleared")
check(
    len(a["verification_presets"]) == 1
    and a["verification_presets"][0]["requirements"][0]["name"] == "Sibling clearance",
    "remaining policy preserved",
)
removed = bpy.context.scene.mechanical_cad_assembly.document_json
bpy.ops.wm.save_as_mainfile(filepath="/tmp/mcad_remove_after.blend")
bpy.ops.wm.open_mainfile(filepath="/tmp/mcad_remove_after.blend")
check(
    bpy.context.scene.mechanical_cad_assembly.document_json == removed,
    "accepted removal survives reopen",
)
for kind in ("cylindrical", "planar", "spherical"):
    help_text = " ".join(joint_help_lines(kind))
    check(
        "degrees" in help_text
        and "independent limits" in help_text
        and "continuous" in help_text
        and "rooted tree" in help_text,
        "popup help explains " + kind,
    )
print("REMOVE_COMPONENT_NATIVE_PASS", len(checks))
