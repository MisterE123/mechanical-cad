"""Placement captures exact text immediately; native acceptance remains guarded."""

import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_session,
    general_viewport,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import AddLine, PointSeed  # noqa: E402


def wait(owner):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error


def event(key, text="", value="PRESS"):
    return SimpleNamespace(
        type=key,
        value=value,
        unicode=text,
        ctrl=False,
        shift=False,
        alt=False,
        is_repeat=False,
        mouse_x=300,
        mouse_y=200,
    )


def place(owner):
    with patch.object(general_viewport, "_pointer", return_value=(10, 4)):
        general_viewport._dimension(owner, bpy.context, event("LEFTMOUSE"))
    assert owner.pending is None  # No delayed callback may capture future focus.
    assert owner.input_controller is not None and not owner.input_controller.closed
    state = owner.input_controller.snapshot()["buffer"]
    assert {state["caret"], state["anchor"]} == {0, len(state["raw"])}
    assert "Type a value" in owner.message


def type_value(owner, text):
    for character in text:
        assert general_viewport._route_field(owner, bpy.context, event("A", character))
        general_viewport._route_field(owner, bpy.context, event("A", value="RELEASE"))
    assert owner.commands.pending_edit.raw_text == text


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    document_state._populate_document(
        bpy.context.scene,
        {
            "schema_version": 1,
            "id": "dimension_placement",
            "name": "Part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    owner = general_session.GeneralSession(bpy.context)
    owner.start()
    line = owner.execute(bpy.context, AddLine(PointSeed(0, 0), PointSeed(20, 0))).entity_ids[-1]
    wait(owner)
    owner.draft.select((("line", line),))
    place(owner)
    identifier = owner.commands.pending_edit.constraint_id
    type_value(owner, "25 + 5")
    general_viewport._route_field(owner, bpy.context, event("RET"))
    assert owner.pending is not None
    wait(owner)
    assert owner.commands.pending_edit is None and owner.input_controller.closed
    constraint = next(c for c in owner.commands.sketch["constraints"] if c["id"] == identifier)
    assert constraint["value"] == "25 + 5", constraint
    solved_line = owner.geometry().lines[line]
    assert abs(math.dist(solved_line.start_mm, solved_line.end_mm) - 30) < 1e-6
    # Formula-preserving reopening uses the same field, and Esc cancels only text.
    place(owner)
    assert owner.input_controller.raw == "25 + 5"
    type_value(owner, "77")
    general_viewport._route_field(owner, bpy.context, event("ESC"))
    assert owner.commands.pending_edit is None and owner.input_controller.closed
    assert (
        next(c for c in owner.commands.sketch["constraints"] if c["id"] == identifier)["value"]
        == "25 + 5"
    )
    owner.check(bpy.context)
    wait(owner)
    owner.local_history(bpy.context)
    wait(owner)
    assert (
        next(c for c in owner.commands.sketch["constraints"] if c["id"] == identifier)["value"]
        == 20
    )
    owner.local_history(bpy.context, redo=True)
    wait(owner)
    assert (
        next(c for c in owner.commands.sketch["constraints"] if c["id"] == identifier)["value"]
        == "25 + 5"
    )
    # Cancellation during trial never reopens or accepts input on a later tick.
    place(owner)
    type_value(owner, "40")
    general_viewport._route_field(owner, bpy.context, event("RET"))
    assert owner.pending is not None
    general_viewport._route_field(owner, bpy.context, event("ESC"))
    assert owner.pending is None and owner.commands.pending_edit is None
    owner.tick(bpy.context)
    assert owner.input_controller.closed
    assert (
        next(c for c in owner.commands.sketch["constraints"] if c["id"] == identifier)["value"]
        == "25 + 5"
    )
    owner.cleanup()
unregister()
print("DIMENSION_PLACEMENT_SMOKE_OK")
