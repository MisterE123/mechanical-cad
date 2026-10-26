"""Native Through All Apply/edit/failure and two-process persistence check.

Run with MCAD_ROOT, MCAD_PYTHON, MCAD_SMOKE_OUTPUT; a second process sets
MCAD_SMOKE_INPUT. This exercises operators, not interactive GUI qualification.
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
from mechanical_cad_blender import register, unregister  # noqa: E402
from mechanical_cad_blender.document_state import _commit_candidate  # noqa: E402
from mechanical_cad_blender.solid_operators import MCAD_OT_edit_solid_feature, _SolidDialog  # noqa: E402

register()
if os.environ.get("MCAD_SMOKE_INPUT"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad


def run(op, **kwargs):
    assert op(**kwargs) == {"FINISHED"}, state.last_action_error
    assert state.status == "READY", state.last_action_error
    return state.active_feature


def edit_arguments(identifier):
    op = SimpleNamespace(feature_id=identifier)
    context = SimpleNamespace(
        scene=bpy.context.scene,
        window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"}),
    )
    assert MCAD_OT_edit_solid_feature.invoke(op, context, None) == {"RUNNING_MODAL"}
    return {
        key: getattr(op, key)
        for key in (
            "feature_id",
            "kind",
            "feature_label",
            "base",
            "tool",
            "original_json",
            "linked_tool_id",
            "linked_length",
            "linked_profile",
            "linked_direction",
            "linked_end_condition",
            "allow_shared_extrusion",
        )
    }, op


def check_volume(thickness, drilled_depth=None):
    assert (
        abs(
            state.volume
            - (100 * thickness - math.pi * (thickness if drilled_depth is None else drilled_depth))
        )
        < 1e-3
    )


if os.environ.get("MCAD_SMOKE_INPUT"):
    run(bpy.ops.mcad.regenerate)
    doc = json.loads(state.document_json)
    remove = doc["active_feature"]
    args, _ = edit_arguments(remove)
    assert args["linked_end_condition"] == "THROUGH_ALL"
    assert args["linked_direction"] == "-1"
    check_volume(40)
    doc["parameters"]["thickness"] = 75
    assert _commit_candidate(bpy.context, doc, state.document_path)
    check_volume(75)
    marker = "MCAD_THROUGH_ALL_REOPEN_OK"
else:
    run(bpy.ops.mcad.new_document, name="Through All")
    doc = json.loads(state.document_json)
    doc["parameters"] = {"thickness": 10}
    doc["features"] = [
        dict(
            id="p",
            kind="sketch_rectangle",
            label="Base profile",
            params={"width": 10, "height": 10},
            inputs={},
        ),
        dict(
            id="base",
            kind="extrude",
            label="Base",
            params={"length": "thickness"},
            inputs={"profile": "p"},
        ),
        dict(
            id="q",
            kind="sketch_circle",
            label="Hole profile",
            params={"radius": 1, "x": 5, "y": 5, "z": "thickness"},
            inputs={},
        ),
    ]
    doc["active_feature"] = "base"
    assert _commit_candidate(bpy.context, doc, state.document_path)
    remove = run(
        bpy.ops.mcad.extrude_boolean,
        mode="REMOVE",
        end_condition="THROUGH_ALL",
        direction="REVERSE",
        profile="q",
        base="base",
        feature_label="Through hole",
    )
    check_volume(10)
    doc = json.loads(state.document_json)
    assert doc["features"][-2]["params"] == {"direction": -1}
    assert doc["parameters"] == {"thickness": 10}
    doc["parameters"]["thickness"] = 40
    assert _commit_candidate(bpy.context, doc, state.document_path)
    check_volume(40)
    args, captured = edit_arguments(remove)
    assert args["linked_end_condition"] == "THROUGH_ALL"
    assert args["linked_direction"] == "-1"

    class Layout:
        enabled = True

        def __init__(self):
            self.fields, self.labels = [], []

        def prop(self, op, name, **kwargs):
            self.fields.append(name)

        def label(self, **kwargs):
            self.labels.append(kwargs.get("text", ""))

        def box(self):
            return self

        def column(self):
            return self

        def row(self, **kwargs):
            return self

    captured.layout = Layout()
    captured.show_help, captured.help_page = False, 1
    captured.help_summary, captured.help_topic = ("Through All", "Atomic Apply"), "feature.cut"
    _SolidDialog.draw(captured, bpy.context)
    assert "linked_end_condition" in captured.layout.fields
    assert "linked_direction" in captured.layout.fields
    assert "linked_length" not in captured.layout.fields
    # Wrong direction rejects the complete candidate, including label edits.
    before = state.document_json
    failed = {**args, "linked_direction": "1", "feature_label": "Must not publish"}
    try:
        result = bpy.ops.mcad.edit_solid_feature(**failed)
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"}
    assert state.document_json == before
    # Same stable tool ID can be changed to Blind and back, visibly and atomically.
    run(
        bpy.ops.mcad.edit_solid_feature,
        **{**args, "linked_end_condition": "BLIND", "linked_length": "-3"},
    )
    check_volume(40, 3)
    args, _ = edit_arguments(remove)
    run(
        bpy.ops.mcad.edit_solid_feature,
        **{**args, "linked_end_condition": "THROUGH_ALL", "linked_direction": "-1"},
    )
    check_volume(40)
    marker = "MCAD_THROUGH_ALL_SMOKE_OK"

bpy.ops.wm.save_as_mainfile(filepath=os.environ["MCAD_SMOKE_OUTPUT"])
print(marker, state.volume, flush=True)
unregister()
