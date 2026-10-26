"""Intermediate consumed-sketch Line is draft-only; Finish remains full replay."""
import json
import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    dimension_input,  # noqa: E402
    document_state,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import PointSeed  # noqa: E402


def wait(owner):
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(.01)
    assert owner.pending is None


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
objects = set(bpy.data.objects)
with bpy.context.temp_override(window=window, area=area, region=region):
    document_state._populate_document(bpy.context.scene, json.loads(
        (ROOT / "examples/viewport_rectangle.mcad.json").read_text()
    ))
    canonical = bpy.context.scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(bpy.context, feature_id="sketch_1")
    owner.start()
    owner.check(bpy.context)
    wait(owner)
    assert not owner.error, owner.error
    before = dict(owner.geometry().points)
    assert owner.commands.consumed_by
    owner.draft.select_tool("Line")
    owner.accept_point_input(bpy.context, PointSeed(100, 100), expected_phase=("line", "start"))
    owner.open_line_length(bpy.context, PointSeed(105, 100), axis="horizontal")
    owner.input_controller.handle(
        dimension_input.InputEvent("A", unicode="5 mm"),
        approve_raw=lambda action: (owner.update_raw(action.raw) is None),
    )
    owner.request_line_length_accept(bpy.context)
    wait(owner)
    assert not owner.error, owner.error
    assert len(owner.commands.sketch["lines"]) == 5
    assert owner.commands.has_current_solution
    assert all(owner.geometry().points[key] == value for key, value in before.items())
    assert bpy.context.scene.mechanical_cad.document_json == canonical
    print("CONSUMED_INTERMEDIATE_LENGTH_OK", flush=True)
    owner.request_finish(bpy.context)
    wait(owner)
    assert not owner.finished
    assert owner.error or owner.retained_for_repair
    assert bpy.context.scene.mechanical_cad.document_json == canonical
    if owner.alive:
        owner.discard()
assert set(bpy.data.objects) == objects
unregister()
print("LINE_LENGTH_CONSUMED_SMOKE_OK", flush=True)
