"""Native Blender operators, explicit face catalogs, rollback and two-process reopen.

Run with MCAD_ROOT, MCAD_PYTHON, MCAD_SMOKE_OUTPUT. Set MCAD_SMOKE_INPUT for
fresh-process reopen. This is not GUI or installed-package qualification.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister  # noqa: E402
from mechanical_cad_blender.document_state import _commit_candidate  # noqa: E402
from mechanical_cad_blender.extrusion_end_condition import _end_face_choices, _source_choices  # noqa: E402
from mechanical_cad_blender.solid_feature_edit import FEATURE_FIELDS, FEATURE_INPUTS  # noqa: E402
from mechanical_cad_blender.solid_operators import MCAD_OT_edit_solid_feature, _SolidDialog  # noqa: E402

register()
if os.environ.get("MCAD_SMOKE_INPUT"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad
checks = 0


def check(value, message="Check failed"):
    global checks
    assert value, message
    checks += 1


def run(op, **kwargs):
    check(op(**kwargs) == {"FINISHED"}, state.last_action_error)
    check(state.status == "READY", state.last_action_error)
    return state.active_feature


def volume(expected):
    check(abs(state.volume - expected) < 1e-4, (state.volume, expected))


def seed(stop_z):
    run(bpy.ops.mcad.new_document, name="Up to planar face")
    doc = json.loads(state.document_json)
    doc["parameters"] = {"stop_z": stop_z, "gap": 0, "blind_depth": 2}
    doc["features"] = [
        dict(
            id="p",
            kind="sketch_rectangle",
            label="Base profile",
            params={"width": 10, "height": 10},
            inputs={},
        ),
        dict(
            id="base", kind="extrude", label="Base", params={"length": 10}, inputs={"profile": "p"}
        ),
        dict(
            id="stop_p",
            kind="sketch_rectangle",
            label="Independent target profile",
            params={"width": 3, "height": 3, "x": 50, "z": "stop_z-1"},
            inputs={},
        ),
        dict(
            id="stop",
            kind="extrude",
            label="Independent target",
            params={"length": 1},
            inputs={"profile": "stop_p"},
        ),
        dict(
            id="other",
            kind="transform",
            label="Same face IDs, different source",
            params={"z": 2},
            inputs={"base": "stop"},
        ),
        dict(
            id="q",
            kind="sketch_rectangle",
            label="Tool profile",
            params={"width": 2, "height": 2, "x": 4, "y": 4, "z": 10},
            inputs={},
        ),
    ]
    doc["active_feature"] = "base"
    check(_commit_candidate(bpy.context, doc, state.document_path))


def editor(identifier):
    op = SimpleNamespace(feature_id=identifier, resume_json="")
    context = SimpleNamespace(
        scene=bpy.context.scene,
        window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"}),
    )
    check(MCAD_OT_edit_solid_feature.invoke(op, context, None) == {"RUNNING_MODAL"})
    keys = {"feature_id", "kind", "feature_label", "original_json", "extrude_end_condition"}
    keys.update(FEATURE_FIELDS[op.kind])
    keys.update(FEATURE_INPUTS.get(op.kind, ()))
    if op.kind == "extrude_to_face":
        keys.add("end_face")
    if op.linked_tool_id:
        keys.update(
            {
                "linked_tool_id",
                "linked_profile",
                "linked_length",
                "linked_direction",
                "linked_end_condition",
                "allow_shared_extrusion",
            }
        )
        if op.linked_end_condition == "UP_TO_FACE":
            keys.update({"target", "end_face", "offset"})
    return {key: getattr(op, key) for key in keys}, op


def reject(op, **kwargs):
    before = state.document_json
    objects = [
        (o.as_pointer(), o.data.as_pointer() if o.data else None) for o in bpy.context.scene.objects
    ]
    try:
        result = op(**kwargs)
    except RuntimeError:
        result = {"CANCELLED"}
    check(result == {"CANCELLED"})
    check(state.document_json == before)
    check(
        objects
        == [
            (o.as_pointer(), o.data.as_pointer() if o.data else None)
            for o in bpy.context.scene.objects
        ]
    )


class Layout:
    def __init__(self):
        self.fields, self.labels = [], []
        self.field_labels = {}

    def prop(self, obj, name, **kw):
        self.fields.append(name)
        self.field_labels[name] = kw.get("text")

    def label(self, **kw):
        self.labels.append(kw.get("text", ""))

    def box(self):
        return self

    def column(self):
        return self

    def row(self, **kw):
        return self


for operator in (
    bpy.ops.mcad.add_extrude,
    bpy.ops.mcad.extrude_boolean,
    bpy.ops.mcad.edit_solid_feature,
):
    offset = operator.get_rna_type().properties["offset"]
    check(offset.name == "Offset (mm)")
    check("Number or formula in mm" in offset.description)
    check(
        "Positive extends past" in offset.description and "selected direction" in offset.description
    )
    check("negative stops short" in offset.description)
signed = bpy.ops.mcad.extrude_boolean.get_rna_type().properties["direction"].enum_items["SIGNED"]
check(signed.name == "Signed depth (Blind only)")
check("Blind only" in signed.description and "Along/Opposite" in signed.description)


if os.environ.get("MCAD_SMOKE_INPUT"):
    run(bpy.ops.mcad.regenerate)
    args, op = editor(state.active_feature)
    check(args["linked_end_condition"] == "UP_TO_FACE")
    check(args["target"] == "stop" and args["end_face"] == "stop/face/cap.end")
    check(args["offset"] == "gap+1" and args["linked_direction"] == "-1")
    volume(972)
    doc = json.loads(state.document_json)
    doc["parameters"]["stop_z"] = 3
    check(_commit_candidate(bpy.context, doc, state.document_path))
    volume(968)
    marker = "MCAD_UP_TO_FACE_REOPEN_OK"
else:
    seed(15)
    standalone = run(
        bpy.ops.mcad.add_extrude,
        profile="q",
        end_condition="UP_TO_FACE",
        target="stop",
        end_face="stop/face/cap.end",
        direction="1",
        offset="gap",
    )
    volume(20)
    args, op = editor(standalone)
    check(args["extrude_end_condition"] == "UP_TO_FACE")
    check(args["target"] == "stop" and args["end_face"] == "stop/face/cap.end")
    check({row[0] for row in _source_choices(op, bpy.context)} == {"NONE", "base", "stop", "other"})
    face_choice = next(
        row for row in _end_face_choices(op, bpy.context) if row[0] == "stop/face/cap.end"
    )
    check("[stop/face/cap.end]" in face_choice[1] and face_choice[2] == "stop/face/cap.end")
    before = state.document_json
    run(bpy.ops.mcad.edit_solid_feature, **args)
    check(state.document_json == before, "No-op edit rewrote formulas or numeric types")
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "offset": "gap+1"})
    volume(24)
    args, _ = editor(standalone)
    reject(bpy.ops.mcad.edit_solid_feature, **{**args, "direction": "-1"})
    reject(bpy.ops.mcad.edit_solid_feature, **{**args, "end_face": "stop/face/side.x_min"})
    run(
        bpy.ops.mcad.edit_solid_feature,
        **{**args, "extrude_end_condition": "BLIND", "length": "blind_depth"},
    )
    volume(8)
    args, _ = editor(standalone)
    run(
        bpy.ops.mcad.edit_solid_feature,
        **{
            **args,
            "extrude_end_condition": "UP_TO_FACE",
            "target": "other",
            "end_face": "stop/face/cap.end",
            "direction": "1",
            "offset": "gap",
        },
    )
    volume(28)
    # Independent target is not the union Base, and the face is explicitly chosen.
    added = run(
        bpy.ops.mcad.extrude_boolean,
        mode="ADD",
        base="base",
        profile="q",
        end_condition="UP_TO_FACE",
        target="stop",
        end_face="stop/face/cap.end",
        direction="NORMAL",
        offset="gap",
    )
    volume(1020)
    args, op = editor(added)
    check(args["linked_end_condition"] == "UP_TO_FACE")
    check(args["base"] == "base" and args["target"] == "stop")
    op.layout = Layout()
    op.help_summary, op.help_topic = (), "feature.cut"
    op.show_help, op.help_page = False, 1
    _SolidDialog.draw(op, bpy.context)
    check({"target", "end_face", "offset", "linked_direction"} <= set(op.layout.fields))
    check(op.layout.field_labels["end_face"] == "End face")
    check(op.layout.field_labels["offset"] == "Offset (mm)")
    check(any("infinite face plane" in text for text in op.layout.labels))
    check(any("Positive offset: past plane" in text for text in op.layout.labels))
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "offset": "gap+1"})
    volume(1024)
    doc = json.loads(state.document_json)
    doc["parameters"]["stop_z"] = 17
    check(_commit_candidate(bpy.context, doc, state.document_path))
    volume(1032)
    seed(5)
    removed = run(
        bpy.ops.mcad.extrude_boolean,
        mode="REMOVE",
        base="base",
        profile="q",
        end_condition="UP_TO_FACE",
        target="stop",
        end_face="stop/face/cap.end",
        direction="REVERSE",
        offset="gap",
    )
    volume(980)
    args, op = editor(removed)
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "target": "other"})
    volume(988)
    args, _ = editor(removed)
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "target": "stop", "offset": "gap+1"})
    volume(976)
    args, _ = editor(removed)
    reject(bpy.ops.mcad.edit_solid_feature, **{**args, "linked_direction": "1"})
    doc = json.loads(state.document_json)
    doc["parameters"]["stop_z"] = 4
    check(_commit_candidate(bpy.context, doc, state.document_path))
    volume(972)
    tool = json.loads(state.document_json)["features"][-2]
    check(tool["kind"] == "extrude_to_face")
    check(tool["params"] == {"direction": -1, "offset": "gap+1"})
    check(tool["inputs"] == {"profile": "q", "target": "stop"})
    check(
        json.loads(state.document_json)["parameters"] == {"gap": 0, "blind_depth": 2, "stop_z": 4}
    )
    marker = "MCAD_UP_TO_FACE_SMOKE_OK"

bpy.ops.wm.save_as_mainfile(filepath=os.environ["MCAD_SMOKE_OUTPUT"])
print(marker, checks, state.volume, flush=True)
unregister()
