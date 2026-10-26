"""Registered Trim/Extend actions, preview and journal with the actual owner.

Picking coordinates are supplied deterministically. This is not GUI usability
qualification; the native backend and transaction paths are real.
"""

import json
import math
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
    general_viewport,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddArc,
    AddLine,
    PointSeed,
    ReverseArcSweep,
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
checks = []
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    cases = (
        ("minor_ccw", -45, 45, "ccw", False, "Trim", 10, 7),
        ("major_cw", -45, 45, "cw", False, "Trim", 10, 3),
        ("reversed_minor", 45, -45, "cw", False, "Trim", 10, 7),
        ("reverse_command", -45, 45, "ccw", True, "Trim", 10, 3),
        ("start_endpoint", 0, 90, "ccw", False, "Trim", 10, 7),
        ("end_endpoint", 90, 180, "ccw", False, "Trim", 10, 3),
        ("extend_near", 135, 225, "ccw", False, "Extend", 2, 3),
        ("extend_excludes_opposite_circle_hit", -45, 45, "ccw", False, "Extend", 2, 7),
        ("outside_finite_arc", 45, 135, "ccw", False, "Trim", 10, None),
    )
    for name, start, end, direction, reverse, mode, target_end, expected in cases:
        document_state._populate_document(
            context.scene,
            {
                "schema_version": 1,
                "id": "arc_trim",
                "name": "Arc Trim",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            },
        )
        owner = general_session.GeneralSession(context)
        owner.start()
        owner.enable_arc(owner.prepare_gesture("arc"))
        owner.draft.select_tool("Select")
        _, endpoint, line = owner.execute(
            context, AddLine(PointSeed(0, 0), PointSeed(target_end, 0))
        ).entity_ids
        wait(owner)

        def seed(angle):
            angle = math.radians(angle)
            return PointSeed(5 + 2 * math.cos(angle), 2 * math.sin(angle))

        arc = owner.execute(
            context, AddArc(PointSeed(5, 0), seed(start), seed(end), direction)
        ).entity_ids[-1]
        wait(owner)
        if reverse:
            owner.execute(context, ReverseArcSweep(arc))
            wait(owner)
        before = owner.commands.sketch
        assert bpy.ops.mcad.general_tool(tool=mode) == {"FINISHED"}
        with (
            patch.object(general_viewport, "_pick", return_value=SimpleNamespace(identifier=line)),
            patch.object(general_viewport, "_pointer", return_value=(target_end, 0)),
        ):
            general_viewport._line_edit_click(owner, None)

        def pick_arc(_owner, _event, kinds, arc=arc):
            assert "arc" in kinds
            return SimpleNamespace(identifier=arc)

        with patch.object(general_viewport, "_pick", side_effect=pick_arc):
            if expected is None:
                try:
                    general_viewport._line_edit_click(owner, None)
                except ValueError as exc:
                    assert "outside the picked finite arc sweep" in str(exc), str(exc)
                else:
                    raise AssertionError("An excluded supporting-circle hit was accepted")
                assert owner.commands.sketch == before
                assert not owner.can_use_tool("ApplyLineEdit")
                assert bpy.ops.mcad.general_tool(tool="CancelLineEdit") == {"FINISHED"}
                owner.discard()
                checks.append(name)
                continue
            general_viewport._line_edit_click(owner, None)
        assert abs(owner.line_edit["preview"].target[0] - expected) < 1e-6
        assert owner.commands.sketch == before
        assert bpy.ops.mcad.general_tool(tool="ApplyLineEdit") == {"FINISHED"}
        wait(owner)
        assert abs(owner.geometry().points[endpoint][0] - expected) < 1e-6
        for field in ("arcs", "lines", "constraints"):
            assert owner.commands.sketch[field] == before[field]
        owner.local_history(context)
        wait(owner)
        assert owner.commands.sketch == before
        owner.local_history(context, redo=True)
        wait(owner)
        assert abs(owner.geometry().points[endpoint][0] - expected) < 1e-6
        owner.discard()
        checks.append(name)
unregister()
print("MCAD_ARC_TRIM_EXTEND_RESULT=" + json.dumps({"ok": True, "checks": checks}))
