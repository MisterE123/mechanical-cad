"""Registered Trim/Extend actions, preview and journal with the actual owner.

Picking coordinates are supplied deterministically. This is not GUI usability
qualification; the native backend and transaction paths are real.
"""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_session,
    general_sketch_overlay,
    general_viewport,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddCircle,
    AddLine,
    AddRelation,
    PointSeed,
)


def wait(owner):
    deadline = time.monotonic() + 40
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.pending is None
    assert not owner.error, owner.error


register()
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    document_state._populate_document(
        context.scene,
        {
            "schema_version": 1,
            "id": "trim_extend",
            "name": "Trim Extend",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    owner = general_session.GeneralSession(context)
    owner.start()
    a, b, line = owner.execute(context, AddLine(PointSeed(0, 0), PointSeed(10, 0))).entity_ids
    wait(owner)
    _, _, boundary = owner.execute(context, AddLine(PointSeed(5, -3), PointSeed(5, 3))).entity_ids
    wait(owner)
    before = owner.commands.sketch
    assert bpy.ops.mcad.general_tool(tool="Trim") == {"FINISHED"}
    assert not owner.can_use_tool("Finish")
    assert not owner.can_use_tool("ApplyLineEdit")
    with (
        patch.object(general_viewport, "_pick", return_value=SimpleNamespace(identifier=line)),
        patch.object(general_viewport, "_pointer", return_value=(9, 0)),
    ):
        general_viewport._line_edit_click(owner, None)
    with patch.object(general_viewport, "_pick", return_value=SimpleNamespace(identifier=boundary)):
        general_viewport._line_edit_click(owner, None)
    assert owner.can_use_tool("ApplyLineEdit")
    assert owner.commands.sketch == before
    geometry = owner.geometry()
    frame = general_sketch_overlay.build_frame(
        geometry,
        lambda point: (point[0] * 10, point[1] * 10),
        current_request_fingerprint=geometry.request_fingerprint,
        proposal=owner.line_edit["preview"].proposal,
    )
    assert any(stroke.proposal for stroke in frame.strokes)
    assert bpy.ops.mcad.general_tool(tool="CancelLineEdit") == {"FINISHED"}
    assert owner.commands.sketch == before
    assert owner.line_edit is None
    assert bpy.ops.mcad.general_tool(tool="Trim") == {"FINISHED"}
    with (
        patch.object(general_viewport, "_pick", return_value=SimpleNamespace(identifier=line)),
        patch.object(general_viewport, "_pointer", return_value=(9, 0)),
    ):
        general_viewport._line_edit_click(owner, None)
    with patch.object(general_viewport, "_pick", return_value=SimpleNamespace(identifier=boundary)):
        general_viewport._line_edit_click(owner, None)
    assert bpy.ops.mcad.general_tool(tool="ApplyLineEdit") == {"FINISHED"}
    wait(owner)
    assert owner.line_edit is None
    assert owner.geometry().points[b] == (5, 0)
    owner.local_history(context)
    wait(owner)
    assert owner.geometry().points[b] == (10, 0)
    owner.local_history(context, redo=True)
    wait(owner)
    assert owner.geometry().points[b] == (5, 0)
    for mode, end_x, center_x, expected_x in (("Trim", 40, 30, 33), ("Extend", 25, 30, 27)):
        _, endpoint, target = owner.execute(
            context, AddLine(PointSeed(20, 20), PointSeed(end_x, 20))
        ).entity_ids
        wait(owner)
        _, circle = owner.execute(context, AddCircle(PointSeed(center_x, 20), 2)).entity_ids
        wait(owner)
        owner.execute(context, AddRelation("radius", (circle,), value=3))
        wait(owner)
        before_circle = owner.commands.sketch
        assert bpy.ops.mcad.general_tool(tool=mode) == {"FINISHED"}

        def pick_target(_owner, _event, kinds, target=target):
            assert kinds == ("line",)
            return SimpleNamespace(identifier=target)

        def pick_circle(_owner, _event, kinds, circle=circle):
            assert "circle" in kinds
            return SimpleNamespace(identifier=circle)

        with (
            patch.object(general_viewport, "_pick", side_effect=pick_target),
            patch.object(general_viewport, "_pointer", return_value=(end_x, 20)),
        ):
            general_viewport._line_edit_click(owner, None)
        with patch.object(general_viewport, "_pick", side_effect=pick_circle):
            general_viewport._line_edit_click(owner, None)
        assert abs(owner.line_edit["preview"].target[0] - expected_x) < 1e-6
        assert owner.commands.sketch == before_circle
        assert bpy.ops.mcad.general_tool(tool="CancelLineEdit") == {"FINISHED"}
        assert owner.commands.sketch == before_circle
        assert owner.line_edit is None
        assert bpy.ops.mcad.general_tool(tool=mode) == {"FINISHED"}
        with (
            patch.object(general_viewport, "_pick", side_effect=pick_target),
            patch.object(general_viewport, "_pointer", return_value=(end_x, 20)),
        ):
            general_viewport._line_edit_click(owner, None)
        with patch.object(general_viewport, "_pick", side_effect=pick_circle):
            general_viewport._line_edit_click(owner, None)
        assert bpy.ops.mcad.general_tool(tool="ApplyLineEdit") == {"FINISHED"}
        wait(owner)
        assert abs(owner.geometry().points[endpoint][0] - expected_x) < 1e-6
        for field in ("lines", "circles", "constraints"):
            assert owner.commands.sketch[field] == before_circle[field]
        owner.local_history(context)
        wait(owner)
        assert owner.commands.sketch == before_circle
        owner.local_history(context, redo=True)
        wait(owner)
        assert abs(owner.geometry().points[endpoint][0] - expected_x) < 1e-6
    owner.discard()
unregister()
print(
    "MCAD_TRIM_EXTEND_RESULT="
    + json.dumps(
        {
            "ok": True,
            "checks": [
                "registered Trim tool",
                "two explicit picks",
                "visible preview stroke",
                "Cancel preserves sketch",
                "Apply performs native solve",
                "unchanged point IDs",
                "local Undo and Redo",
                "circle boundary Trim and Extend use native solved radius",
                "circle boundary picker admits circles only after target",
                "circle boundary constraints and identities preserved",
                "circle preview Cancel and repeat",
            ],
        }
    )
)
