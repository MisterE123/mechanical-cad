"""Native 5.2 operator workflow, authored from scratch, using the real sidecar.

Run with --background --factory-startup --python-exit-code 1. This does not claim
interactive GUI/Undo review; those are separately exercised by the UI reviewer.
"""

import copy
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402  # noqa: E402
    assembly_display,
    assembly_files,
    assembly_operators,
    assembly_properties,
    assembly_state,
    assembly_ui,
    assembly_verification_ui,
    register,
    unregister,
)
from mechanical_cad_blender.assembly_operator_helpers import AssemblyEdit, degrees_from_quaternion  # noqa: E402

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
    bpy.ops.mcad.assembly_frame(part_id=part, name="Upper datum", xyz="0, 0, 4", wxyz="1, 0, 0, 0")
    == {"FINISHED"},
    "named literal frame",
)
frame = data()["parts"][0]["mate_frames"][-1]
check(frame["placement"]["xyz_mm"] == [0, 0, 4], "frame coordinate accepted in mm")
check(
    bpy.ops.mcad.assembly_insert(
        part_id=part,
        parent=root,
        parent_frame="origin",
        child_frame="origin",
        kind="slider",
        coordinate="30",
        use_limits=True,
        lower="0",
        upper="100",
        name="Moving bracket",
        joint_name="Bracket slide",
    )
    == {"FINISHED"},
    "insert reused child",
)
child = data()["instances"][-1]["id"]
slide = data()["joints"][-1]["id"]
check(
    len(data()["parts"]) == 1 and len(data()["instances"]) == 2,
    "two instances reuse one definition",
)
owned = assembly_display.owned_objects(scene, assembly_storage.owner_id)
instances = [o for o in owned if o.get(assembly_display.ROLE_KEY) == "instance"]
check(instances[0].data == instances[1].data, "reused instances share display mesh")
check(
    len([o for o in owned if o.get(assembly_display.ROLE_KEY) == "frame"]) == 4,
    "both named frames visible on both instances",
)

check(
    bpy.ops.mcad.assembly_preset(
        name="Bracket clearance",
        kind="clearance",
        pair_a=root,
        pair_b=child,
        requirement_name="Bracket axial gap",
        minimum_mm="2",
        activate=False,
    )
    == {"FINISHED"},
    "saved named pair",
)
preset = data()["verification_presets"][0]["id"]
requirement_id = data()["verification_presets"][0]["requirements"][0]["id"]
check(data()["active_verification_preset"] is None, "saving does not infer active intent")
check(bpy.ops.mcad.assembly_check() == {"FINISHED"}, "unconfigured measurement check")
check(not report()["report"]["passed"], "measurements only never pass")
check(
    bpy.ops.mcad.assembly_select_preset(preset_id=preset) == {"FINISHED"},
    "explicit preset selection",
)
check(bpy.ops.mcad.assembly_check() == {"FINISHED"}, "actual saved-preset check")
check(
    report()["report"]["passed"] and report()["report"]["complete"], "configured clear pose passes"
)
check(
    bpy.ops.mcad.assembly_joint(
        joint_id=slide, coordinate="0", use_limits=True, lower="0", upper="100"
    )
    == {"FINISHED"},
    "edit slider coordinate",
)
check(not assembly_state.report_is_current(bpy.context), "coordinate edit invalidates old evidence")
check(
    bpy.ops.mcad.assembly_sample(joint_id=slide, values="0, 30") == {"FINISHED"},
    "explicit sample list",
)
check(
    report()["report"]["known_interference"] and not report()["report"]["passed"],
    "known violating sample retained",
)
check(report()["report"]["continuous_collision_guarantee"] is False, "sampled-only boundary")
check(data()["joints"][0]["coordinate"] == 0, "sampling does not move saved coordinate")

# Revolute conversion boundary and whole-map sampling preserve the other joint.
check(
    bpy.ops.mcad.assembly_insert(
        part_id=part,
        parent=child,
        parent_frame=frame["id"],
        child_frame="origin",
        kind="revolute",
        coordinate="90",
        use_limits=True,
        lower="-180",
        upper="180",
        name="Swing bracket",
        joint_name="Bracket hinge",
    )
    == {"FINISHED"},
    "explicit revolute child",
)
hinge = data()["joints"][-1]["id"]
third = data()["instances"][-1]["id"]
check(data()["joints"][-1]["coordinate"] == math.pi / 2, "degrees stored as canonical radians")
check(
    bpy.ops.mcad.assembly_preset(
        preset_id=preset,
        name="Bracket clearance",
        kind="clearance",
        pair_a=root,
        pair_b=third,
        requirement_name="Swing clearance",
        minimum_mm="3",
        activate=True,
    )
    == {"FINISHED"},
    "add second pair",
)
check(
    len(data()["verification_presets"][0]["requirements"]) == 2
    and data()["verification_presets"][0]["requirements"][0]["id"] == requirement_id,
    "editing one pair preserves other named pair and stable ID",
)
check(
    bpy.ops.mcad.assembly_sample(joint_id=slide, values="10, 30") == {"FINISHED"},
    "sample whole map",
)
for pose in report()["report"]["poses"]:
    check(
        pose["pose"]["effective_coordinates"][hinge] == math.pi / 2,
        "nonsampled revolute coordinate retained",
    )

accepted = assembly_storage.document_json
AssemblyEdit.cancel(SimpleNamespace(), bpy.context)
check(assembly_storage.document_json == accepted, "Cancel is mutation-free")
rejected(
    lambda: bpy.ops.mcad.assembly_frame(
        part_id=part, name="Bad frame", xyz="0, 0, 0", wxyz="1, 1, 0, 0", advanced_quaternion=True
    ),
    "sidecar rejects nonunit frame",
)
check(assembly_storage.document_json == accepted, "invalid frame leaves assembly exact")
rejected(
    lambda: bpy.ops.mcad.assembly_joint(
        joint_id=slide, coordinate="101", use_limits=True, lower="0", upper="100"
    ),
    "sidecar rejects joint limit",
)
check(assembly_storage.document_json == accepted, "invalid limit leaves assembly exact")

# Working Part changes are separate. Explicit source-open protects a different Part.
check(bpy.ops.mcad.new_document(name="Unsaved other Part") == {"FINISHED"}, "separate working Part")
other_part = part_state.document_json
rejected(
    lambda: bpy.ops.mcad.assembly_open_part(part_id=part, confirmed=False),
    "embedded source requires replacement confirmation",
)
check(part_state.document_json == other_part, "unconfirmed source-open preserves working Part")
check(
    bpy.ops.mcad.assembly_open_part(part_id=part, confirmed=True) == {"FINISHED"},
    "confirmed source-open",
)
check(assembly_storage.document_json == accepted, "opening source never changes assembly")
length = next(p for p in part_state.parameters if "length" in p.key)
length.value = 6
check(bpy.ops.mcad.regenerate() == {"FINISHED"}, "edit source length via ordinary Part parameter")
check(assembly_storage.document_json == accepted, "working Part edit leaves accepted source intact")
updates = assembly_state.source_updates(bpy.context)
check(len(updates) == 1 and len(updates[0]["instance_ids"]) == 3, "all affected instances named")
AssemblyEdit.cancel(SimpleNamespace(), bpy.context)
check(assembly_storage.document_json == accepted, "update Cancel retains old source")
check(bpy.ops.mcad.assembly_update_source() == {"FINISHED"}, "atomic explicit all-instance update")
check(
    data()["part_sources"][0]["source_digest"] != source_before["source_digest"],
    "new source revision",
)
check(data()["parts"][0]["mate_frames"][-1] == frame, "literal frame does not follow thickness")
check(not assembly_state.report_is_current(bpy.context), "source update invalidates verification")
check(unrelated.name in scene.objects, "unrelated scene object preserved")

# Ordinary degree fields and exact untouched negative-sign quaternion retention.
check(
    bpy.ops.mcad.assembly_frame(
        part_id=part, name="Rotated datum", xyz="3, 2, 1", rotation_degrees="90, 0, 0"
    )
    == {"FINISHED"},
    "normal XYZ degrees author a literal orientation",
)
rotated = data()["parts"][0]["mate_frames"][-1]
check(
    math.isclose(rotated["placement"]["wxyz"][0], math.sqrt(0.5), abs_tol=1e-15)
    and math.isclose(rotated["placement"]["wxyz"][1], math.sqrt(0.5), abs_tol=1e-15),
    "degree conversion uses canonical double WXYZ",
)
negative = [-v for v in rotated["placement"]["wxyz"]]
check(
    bpy.ops.mcad.assembly_frame(
        part_id=part,
        frame_id=rotated["id"],
        name="Rotated datum",
        xyz="3, 2, 1",
        wxyz=", ".join(map(repr, negative)),
        advanced_quaternion=True,
    )
    == {"FINISHED"},
    "advanced quaternion keeps authored negative sign",
)
angles, quaternion = degrees_from_quaternion(negative), ", ".join(map(repr, negative))
captured = []
draft = SimpleNamespace(
    part_id=part,
    frame_id=rotated["id"],
    name="Rotated datum",
    xyz="3, 2, 1",
    rotation_degrees=angles,
    wxyz=quaternion,
    advanced_quaternion=False,
    _original_orientation=(angles, quaternion, negative),
    apply=lambda context, candidate: captured.append(candidate) or {"FINISHED"},
)
check(
    assembly_operators.MCAD_OT_assembly_frame.execute(draft, bpy.context) == {"FINISHED"},
    "unchanged normal-mode dialog produces a candidate",
)
check(
    captured[0]["parts"][0]["mate_frames"][-1]["placement"]["wxyz"] == negative,
    "untouched orientation preserves every original double and sign",
)

# A second working Part can be captured with a fixed child in one atomic operation.
check(bpy.ops.mcad.new_document(name="User cover") == {"FINISHED"}, "new independent source Part")
check(bpy.ops.mcad.add_rectangle(width=5, height=5) == {"FINISHED"}, "second user rectangle")
check(
    bpy.ops.mcad.add_extrude(profile=part_state.active_feature, length=2) == {"FINISHED"},
    "second user extrusion",
)
cover_before = part_state.document_json
check(
    bpy.ops.mcad.assembly_insert(
        use_working_part=True,
        parent=root,
        parent_frame=frame["id"],
        child_frame="origin",
        kind="fixed",
        name="Cover",
        joint_name="Cover seat",
    )
    == {"FINISHED"},
    "capture new source and fixed child together",
)
check(
    len(data()["parts"]) == 2
    and len(data()["part_sources"]) == 2
    and len(data()["instances"]) == 4,
    "new definition remains separate and reusable",
)
check(
    "coordinate" not in data()["joints"][-1] and "limits" not in data()["joints"][-1],
    "fixed joint stores no invented coordinate or limits",
)
check(part_state.document_json == cover_before, "capturing second Part preserves working text")


cover = data()["instances"][-1]
check(
    bpy.ops.mcad.assembly_select(instance_id=cover["id"]) == {"FINISHED"},
    "named instance selects its viewport display",
)
check(
    all(o.get(assembly_display.INSTANCE_KEY) == cover["id"] for o in bpy.context.selected_objects),
    "instance selection highlights only its owned instance and frames",
)
check(bpy.ops.mcad.assembly_select(part_id=part) == {"FINISHED"}, "definition selection")
check(
    not assembly_storage.selected_instance_id,
    "definition change clears unrelated selected instance",
)
check(
    {o.get(assembly_display.INSTANCE_KEY) for o in bpy.context.selected_objects}
    == {root, child, third},
    "definition selection highlights all its reused instances",
)
check(bpy.ops.mcad.assembly_select(joint_id=hinge) == {"FINISHED"}, "joint selection")
check(
    assembly_storage.selected_instance_id == third and assembly_storage.selected_joint_id == hinge,
    "joint selection binds its child",
)
check(
    bpy.ops.mcad.assembly_select(part_id=cover["part_id"]) == {"FINISHED"},
    "select other definition",
)
check(
    not assembly_storage.selected_joint_id and not assembly_storage.selected_instance_id,
    "other definition clears unrelated instance and joint selection",
)


# Invoke binds the scene/window, even if another scene has byte-identical documents.
class ScopedDialog(AssemblyEdit):
    pass


scoped = ScopedDialog()
invoke_context = SimpleNamespace(
    scene=scene,
    window=bpy.context.window,
    window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"}),
)
check(scoped.invoke(invoke_context, None) == {"RUNNING_MODAL"}, "dialog invocation captured target")
clone = scene.copy()
clone_before = clone.mechanical_cad_assembly.document_json
original_before = assembly_storage.document_json
check(clone_before == original_before, "cloned scene has byte-identical assembly")
try:
    bpy.context.window.scene = clone
    try:
        scoped.apply(bpy.context, data())
    except Exception as exc:
        check("scene or window changed" in str(exc), "invoked edit rejects cloned scene switch")
    else:
        raise AssertionError("cloned scene target must not be accepted")
    check(
        clone.mechanical_cad_assembly.document_json == clone_before
        and assembly_storage.document_json == original_before,
        "both scene snapshots retained",
    )
finally:
    bpy.context.window.scene = scene
    bpy.data.scenes.remove(clone)

with tempfile.TemporaryDirectory(prefix="mcad-authoring-") as directory:
    path = Path(directory) / "authored.mcad-assembly.json"
    check(bpy.ops.mcad.assembly_save(filepath=str(path)) == {"FINISHED"}, "atomic portable save")
    saved = path.read_text()
    check(json.loads(saved) == data(), "saved file contains accepted embedded sources")
    replace = assembly_files.os.replace

    def fail_replace(*args):
        raise OSError("injected atomic replacement failure")

    assembly_files.os.replace = fail_replace
    try:
        rejected(
            lambda: bpy.ops.mcad.assembly_save(filepath=str(path)),
            "atomic replacement failure is reported",
        )
        check(path.read_text() == saved, "failed replacement keeps destination exact")
        check(not list(Path(directory).glob("*.tmp")), "failed Save cleans its temporary file")
    finally:
        assembly_files.os.replace = replace

    check(bpy.ops.mcad.assembly_load(filepath=str(path)) == {"FINISHED"}, "fresh load and replay")
    check(assembly_storage.document_json == saved, "save/load stable canonical bytes")
    bad = Path(directory) / "bad.mcad-assembly.json"
    bad.write_text('{"kind":"assembly","output_path":"/tmp/never-write"}')
    accepted = assembly_storage.document_json
    rejected(lambda: bpy.ops.mcad.assembly_load(filepath=str(bad)), "reject hidden output path")
    check(assembly_storage.document_json == accepted, "failed Load preserves accepted assembly")
    part_state.sketch_draft_json = '{"suspended":true}'
    rejected(
        lambda: bpy.ops.mcad.assembly_save(filepath=str(path)), "saved draft blocks assembly Save"
    )
    check(path.read_text() == saved, "blocked Save never overwrites existing file")
    rejected(lambda: bpy.ops.mcad.assembly_check(), "saved draft blocks checks")
    part_state.sketch_draft_json = ""

check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "no native CAD or solver imported in Blender",
)
if extra_storage:
    del bpy.types.Scene.mechanical_cad_assembly
for cls in reversed(extra_classes):
    bpy.utils.unregister_class(cls)
unregister()
print("ASSEMBLY_AUTHORING_SMOKE_OK", len(checks))
