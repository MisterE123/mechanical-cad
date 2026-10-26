"""Source Blender Hole creation/edit/native preview Cancel and two-process reopen.

GPU overlay is captured rather than drawn; this is not actual GUI or Undo evidence.
"""

import json
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import execution_lease, register, sketch_pending, unregister  # noqa: E402
from mechanical_cad_blender import extrusion_preview as preview  # noqa: E402
from mechanical_cad_blender.hole_operators import MCAD_OT_round_hole  # noqa: E402
from mechanical_cad_blender.hole_recipe import inspect_hole  # noqa: E402

register()
if os.environ.get("MCAD_SMOKE_INPUT"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad


def run(operator, **kwargs):
    outcome = operator(**kwargs)
    assert outcome == {"FINISHED"}, (outcome, state.last_action_error)
    assert state.status == "READY", (state.status, state.last_action_error)
    return state.active_feature


def args(identifier):
    values = inspect_hole(json.loads(state.document_json), identifier)
    assert values
    values["feature_label"] = values.pop("label")
    return {
        key: value if key in {"base", "face", "counterbore"} else str(value)
        for key, value in values.items()
    }


def check_volume(diameter):
    expected = 24000 - math.pi * ((diameter / 2) ** 2 * 12 + (25 - (diameter / 2) ** 2) * 2)
    assert abs(state.volume - expected) < 1e-3, (state.volume, expected)


if os.environ.get("MCAD_SMOKE_INPUT"):
    run(bpy.ops.mcad.regenerate)
    identifier = state.active_feature
    check_volume(6)
    values = args(identifier)
    run(bpy.ops.mcad.round_hole, feature_id=identifier, **{**values, "diameter": "7"})
    check_volume(7)
    marker = "MCAD_ROUND_HOLE_REOPEN_OK"
else:
    run(bpy.ops.mcad.new_document, name="Round hole smoke")
    profile = run(bpy.ops.mcad.add_rectangle, width=40, height=30)
    base = run(bpy.ops.mcad.add_extrude, profile=profile, length=20)
    identifier = run(
        bpy.ops.mcad.round_hole,
        base=base,
        face=base + "/face/cap.end",
        diameter="5",
        depth="12",
        counterbore=True,
        counter_diameter="10",
        counter_depth="2",
    )
    check_volume(5)
    values = args(identifier)
    run(bpy.ops.mcad.round_hole, feature_id=identifier, **{**values, "diameter": "6"})
    check_volume(6)
    before = state.document_json
    try:
        result = bpy.ops.mcad.round_hole(feature_id=identifier, **{**values, "counter_depth": "12"})
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"} and state.document_json == before

    area = next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D")
    with bpy.context.temp_override(area=area):
        op = SimpleNamespace(
            **args(identifier), feature_id=identifier, recipe_id=identifier, original_json=before
        )
        op.preview_candidate = lambda context: MCAD_OT_round_hole.preview_candidate(op, context)
        owner = preview.Preview(op, bpy.context)
        op._extrusion_preview = owner
        captured = []
        owner.overlay = lambda response, candidate: captured.append(response)
        owner.changed = 0
        deadline = time.monotonic() + 35
        while not owner.completed and time.monotonic() < deadline:
            owner.tick(bpy.context)
            time.sleep(0.02)
        assert owner.completed and captured
        assert state.document_json == before
        op.diameter = "7"
        preview.changed(op, bpy.context)
        owner.changed = 0
        owner.tick(bpy.context)
        owner.changed = 0
        owner.tick(bpy.context)
        assert owner.pending is not None
        MCAD_OT_round_hole.cancel(op, bpy.context)
        deadline = time.monotonic() + 15
        while execution_lease.is_busy() and time.monotonic() < deadline:
            sketch_pending.reap()
            time.sleep(0.02)
        assert not execution_lease.is_busy() and state.document_json == before
    marker = "MCAD_ROUND_HOLE_SMOKE_OK"

bpy.ops.wm.save_as_mainfile(filepath=os.environ["MCAD_SMOKE_OUTPUT"])
print(marker, state.volume, flush=True)
unregister()
