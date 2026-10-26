"""Native 5.2.2 gear operators, exact poses, limits, Undo and two-process persistence.

Run create and reopen in separate --background --python-exit-code 1 processes.
No manual GUI, installed ZIP or physical tooth-contact qualification is claimed.
"""

import json
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
sys.path.insert(0, str(ROOT / "tests"))
from blender_async_helpers import replay_assembly  # noqa: E402
from mechanical_cad_blender import assembly_state, register  # noqa: E402
from mechanical_cad_blender.assembly_operator_helpers import AssemblyEdit, sample_coordinate_choices  # noqa: E402

OUT = Path(os.environ.get("MCAD_GEAR_OUT", "/tmp/mcad_gear_smoke"))
MODE = os.environ.get("MCAD_GEAR_MODE", "create")
OUT.mkdir(exist_ok=True)
register()
checks = []

# Short field labels fit the shared 520px dialog; full meaning stays in tooltips.
gear_properties = bpy.ops.mcad.assembly_gear.get_rna_type().properties
for field, label, meaning in (
    ("driven_joint", "Driven joint", "Controlled revolute joint"),
    ("ratio", "Signed ratio", "driven angle = ratio × driver angle + phase"),
    ("offset", "Phase (deg)", "Offset / phase in degrees"),
):
    assert gear_properties[field].name == label
    assert meaning in gear_properties[field].description
assert "mate-local +Z" in gear_properties["ratio"].description
assert "Keep current alignment" in gear_properties["offset"].description
checks.append("compact gear labels retain full tooltip meaning")


def done(result, label):
    assert result == {"FINISHED"}, (label, result)
    checks.append(label)


def state():
    return bpy.context.scene.mechanical_cad_assembly


def data():
    return assembly_state.read_assembly(state())


def pose():
    return assembly_state.current_display_response(bpy.context)["report"]["base_pose"]


def reject(operation, label):
    before = state().document_json
    try:
        result = operation()
        assert result == {"CANCELLED"}, (label, result)
    except RuntimeError:
        pass
    assert state().document_json == before, label + " changed accepted assembly"
    checks.append(label)


def same(actual, expected):
    assert math.isclose(actual, expected, abs_tol=1e-12), (actual, expected)


def exact_pose(joints, angles):
    result = pose()
    assert result["structural_dof"] == 1
    for index, (joint, angle) in enumerate(zip(joints, angles, strict=True)):
        same(result["effective_coordinates"][joint["id"]], math.radians(angle))
        transform = result["transforms"][joint["child"]]
        for actual, expected in zip(
            transform["wxyz"],
            [math.cos(math.radians(angle) / 2), 0, 0, math.sin(math.radians(angle) / 2)],
            strict=True,
        ):
            same(actual, expected)
        assert transform["xyz_mm"] == [float((index + 1) * 30), 0.0, 0.0]


if MODE == "reopen":
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "gears.blend"))
    expected = json.loads((OUT / "expected.json").read_text())
    assert data() == expected
    assert not assembly_state.report_is_current(bpy.context)
    done(replay_assembly(), "fresh reopen replay")
    joints = data()["joints"]
    exact_pose(joints, (20, 20, 5))
    done(
        bpy.ops.mcad.assembly_joint(joint_id=joints[0]["id"], coordinate="25"), "edit after reopen"
    )
    exact_pose(joints, (25, 10, 0))
    done(
        bpy.ops.mcad.assembly_load(filepath=str(OUT / "gears.mcad-assembly.json")),
        "portable file load",
    )
    assert data() == expected
    exact_pose(joints, (20, 20, 5))
    assert not any(key == "OCP" or key.startswith("OCP.") for key in sys.modules)
    print("ASSEMBLY_GEAR_REOPEN_OK", len(checks))
else:
    done(bpy.ops.mcad.new_document(name="Gear test carrier"), "new Part")
    done(bpy.ops.mcad.add_rectangle(width=12, height=8), "draw Part profile")
    done(
        bpy.ops.mcad.add_extrude(profile=bpy.context.scene.mechanical_cad.active_feature, length=4),
        "exact Part extrusion",
    )
    done(
        bpy.ops.mcad.assembly_new(name="Directed coordinate gears", grounded=True), "grounded root"
    )
    root, part = data()["grounded_instance"], data()["parts"][0]["id"]
    for index, angle in enumerate((10, 40, 15)):
        done(
            bpy.ops.mcad.assembly_frame(
                part_id=part, name=f"Axis {index + 1}", xyz=f"{(index + 1) * 30}, 0, 0"
            ),
            "literal axis",
        )
        frame = data()["parts"][0]["mate_frames"][-1]["id"]
        done(
            bpy.ops.mcad.assembly_insert(
                part_id=part,
                parent=root,
                parent_frame=frame,
                child_frame="origin",
                kind="revolute",
                name=f"Wheel {index + 1}",
                coordinate=str(angle),
            ),
            "independent revolute branch",
        )
    joints = data()["joints"]
    done(
        bpy.ops.mcad.assembly_gear(
            name="Opposed 2:1",
            driver_joint=joints[0]["id"],
            driven_joint=joints[1]["id"],
            ratio="-2",
            keep_alignment=True,
        ),
        "create aligned relation",
    )
    relation1 = data()["gear_relations"][0]
    same(relation1["offset_rad"], math.radians(60))
    done(
        bpy.ops.mcad.assembly_gear(
            name="Half speed",
            driver_joint=joints[1]["id"],
            driven_joint=joints[2]["id"],
            ratio="0.5",
            offset="-5",
            keep_alignment=False,
        ),
        "chain explicit phase",
    )
    relation2 = data()["gear_relations"][1]
    done(
        bpy.ops.mcad.assembly_gear(
            relation_id=relation2["id"],
            name=relation2["name"],
            driver_joint=joints[1]["id"],
            driven_joint=joints[2]["id"],
            ratio="0.25",
            offset="5",
            keep_alignment=False,
        ),
        "edit relation signed ratio and phase",
    )
    same(data()["gear_relations"][1]["offset_rad"], math.radians(5))
    done(
        bpy.ops.mcad.assembly_gear(
            relation_id=relation2["id"],
            name=relation2["name"],
            driver_joint=joints[1]["id"],
            driven_joint=joints[2]["id"],
            ratio="0.5",
            offset="-5",
            keep_alignment=False,
        ),
        "restore explicit relation without hidden phase changes",
    )
    exact_pose(joints, (10, 40, 15))
    choices = sample_coordinate_choices(None, bpy.context)
    assert [row[0] for row in choices] == [joints[0]["id"]]
    cancel_before = state().document_json
    AssemblyEdit.cancel(SimpleNamespace(), bpy.context)
    assert state().document_json == cancel_before
    bpy.context.preferences.edit.use_global_undo = True
    bpy.ops.ed.undo_push(message="Gear relations baseline")
    done(
        bpy.ops.mcad.assembly_joint(joint_id=joints[0]["id"], coordinate="20"),
        "driver moves cross-branch followers",
    )
    exact_pose(joints, (20, 20, 5))
    bpy.ops.ed.undo_push(message="Moved independent gear driver")
    done(bpy.ops.ed.undo(), "native Undo")
    assert data()["gear_relations"] == [relation1, relation2]
    same(data()["joints"][0]["coordinate"], math.radians(10))
    done(bpy.ops.ed.redo(), "native Redo")
    same(data()["joints"][0]["coordinate"], math.radians(20))
    done(replay_assembly(), "fresh replay after history")
    exact_pose(joints, (20, 20, 5))
    done(
        bpy.ops.mcad.assembly_joint(
            joint_id=joints[1]["id"], use_limits=True, lower="-90", upper="90"
        ),
        "controlled axis limits",
    )
    reject(
        lambda: bpy.ops.mcad.assembly_joint(joint_id=joints[0]["id"], coordinate="100"),
        "derived limit rejection",
    )
    exact_pose(joints, (20, 20, 5))
    reject(
        lambda: bpy.ops.mcad.assembly_joint(joint_id=joints[1]["id"], coordinate="2"),
        "manual driven edit rejected",
    )
    reject(
        lambda: bpy.ops.mcad.assembly_gear(
            driver_joint=joints[0]["id"], driven_joint=joints[1]["id"], ratio="3"
        ),
        "second driver rejected",
    )
    reject(
        lambda: bpy.ops.mcad.assembly_gear(
            driver_joint=joints[2]["id"], driven_joint=joints[0]["id"], ratio="1"
        ),
        "relation cycle rejected",
    )
    reject(
        lambda: bpy.ops.mcad.assembly_remove_component(
            instance_id=joints[0]["child"], confirmed=True
        ),
        "component removal names affected relation",
    )
    assert "Opposed 2:1" in state().last_action_error
    done(
        bpy.ops.mcad.assembly_sample(joint_id=joints[0]["id"], values="0, 10, 20"),
        "sample independent driver",
    )
    samples = json.loads(state().report_json)["report"]["poses"]
    assert len(samples) == 3
    for row, driver in zip(samples, (0, 10, 20), strict=True):
        same(row["pose"]["effective_coordinates"][joints[1]["id"]], math.radians(60 - 2 * driver))
        same(row["pose"]["effective_coordinates"][joints[2]["id"]], math.radians(25 - driver))
        assert joints[1]["id"] not in row["pose"]["requested_coordinates"]
    done(replay_assembly(), "restore saved pose display")
    exact_pose(joints, (20, 20, 5))
    before_relations = data()["gear_relations"]
    doc = json.loads(bpy.context.scene.mechanical_cad.document_json)
    next(feature for feature in doc["features"] if feature["kind"] == "extrude")["params"][
        "length"
    ] = 6
    bpy.context.scene.mechanical_cad.document_json = json.dumps(doc)
    done(bpy.ops.mcad.assembly_update_source(), "all-instance source refresh")
    assert data()["gear_relations"] == before_relations
    exact_pose(joints, (20, 20, 5))
    accepted = state().document_json
    done(
        bpy.ops.mcad.assembly_save(filepath=str(OUT / "gears.mcad-assembly.json")),
        "portable gear save",
    )
    done(
        bpy.ops.mcad.assembly_remove_gear(relation_id=relation1["id"]),
        "release driver relation without jump",
    )
    same(
        next(j for j in data()["joints"] if j["id"] == joints[1]["id"])["coordinate"],
        math.radians(20),
    )
    same(pose()["effective_coordinates"][joints[2]["id"]], math.radians(5))
    assert data()["gear_relations"] == [relation2]
    done(
        bpy.ops.mcad.assembly_load(filepath=str(OUT / "gears.mcad-assembly.json")),
        "restore portable relations",
    )
    assert state().document_json == accepted
    (OUT / "expected.json").write_text(json.dumps(data(), sort_keys=True))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "gears.blend"))
    assert not any(key == "OCP" or key.startswith("OCP.") for key in sys.modules)
    print("ASSEMBLY_GEAR_CREATE_OK", len(checks))
