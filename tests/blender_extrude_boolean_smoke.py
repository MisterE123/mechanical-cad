"""Real Blender Add/Remove operators and fresh-process editable-history recovery.

Run once with MCAD_SMOKE_OUTPUT; run again with MCAD_SMOKE_INPUT pointing to it.
MCAD_ROOT and MCAD_PYTHON select the source and native sidecar. Not a GUI claim.
"""

import json
import math
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister  # noqa: E402
from mechanical_cad_blender.document_state import _append_feature, _new_feature  # noqa: E402

register()
if os.environ.get("MCAD_SMOKE_INPUT"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad
# Display volume is a Blender float property; native exact tests use tighter tolerances.


def run(operator, **kwargs):
    result = operator(**kwargs)
    assert result == {"FINISHED"}, (result, state.error, state.last_action_error)
    assert state.status == "READY", (state.status, state.last_action_error)
    return state.active_feature


if os.environ.get("MCAD_SMOKE_INPUT"):
    run(bpy.ops.mcad.regenerate)
    assert abs(state.volume - (12000 + 12 * math.pi)) < 1e-3
    document = json.loads(state.document_json)
    assert document["features"][-1]["kind"] == "cut"
    assert document["active_feature"] == document["features"][-1]["id"]
    depth = document["features"][-2]["params"]["length"]
    run(
        bpy.ops.mcad.named_parameter,
        parameter_name=depth,
        expression="-3",
        replace_existing=True,
        original_json=state.document_json,
    )
    assert abs(state.volume - (12000 + 8 * math.pi)) < 1e-3
    run(bpy.ops.mcad.check_geometry)
    assert state.geometry_status == "PASSED", state.geometry_message
    marker = "MCAD_EXTRUDE_BOOLEAN_REOPEN_OK"
else:
    run(bpy.ops.mcad.new_document, name="One-step extrusion smoke")
    profile = run(bpy.ops.mcad.add_rectangle, width=40, height=30)
    base = run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
    circle = _new_feature(
        bpy.context,
        "sketch_circle",
        {"radius": 2, "x": 10, "y": 10, "z": 10},
        {},
        "Boss and pocket profile",
    )
    assert _append_feature(bpy.context, circle)
    added = run(
        bpy.ops.mcad.extrude_boolean,
        mode="ADD",
        profile=circle["id"],
        base=base,
        depth="5",
        feature_label="Boss",
    )
    assert abs(state.volume - (12000 + 20 * math.pi)) < 1e-3
    circle = _new_feature(
        bpy.context, "sketch_circle", {"radius": 2, "x": 20, "y": 10, "z": 10}, {}, "Pocket profile"
    )
    assert _append_feature(bpy.context, circle)
    removed = run(
        bpy.ops.mcad.extrude_boolean,
        mode="REMOVE",
        profile=circle["id"],
        base=added,
        depth="-5",
        feature_label="Pocket",
    )
    assert abs(state.volume - 12000) < 1e-3
    document = json.loads(state.document_json)
    assert [f["kind"] for f in document["features"] if not f["kind"].startswith("sketch_")][
        -4:
    ] == ["extrude", "union", "extrude", "cut"]
    assert document["active_feature"] == removed
    before = state.document_json
    # Real replay rejection must not publish either node or alter accepted history.
    try:
        failed = bpy.ops.mcad.extrude_boolean(
            mode="ADD",
            profile=circle["id"],
            base=removed,
            depth="0",
            feature_label="Invalid zero depth",
        )
    except RuntimeError:
        failed = {"CANCELLED"}
    assert failed == {"CANCELLED"} and state.document_json == before
    depth = document["features"][-2]["params"]["length"]
    run(
        bpy.ops.mcad.named_parameter,
        parameter_name=depth,
        expression="-2",
        replace_existing=True,
        original_json=state.document_json,
    )
    assert abs(state.volume - (12000 + 12 * math.pi)) < 1e-3
    marker = "MCAD_EXTRUDE_BOOLEAN_SMOKE_OK"

output = os.environ["MCAD_SMOKE_OUTPUT"]
bpy.ops.wm.save_as_mainfile(filepath=output)
assert Path(output).is_file()
print(
    marker,
    json.dumps({"volume": state.volume, "active": state.active_feature, "path": output}),
    flush=True,
)
unregister()
