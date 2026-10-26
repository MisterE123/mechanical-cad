"""Registered explicit point filter and endpoint picking; no GUI usability claim."""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_session,
    general_viewport,
    register,
    unregister,
    workspace,
    workspace_ui,
)
from mechanical_cad_blender.general_sketch_commands import AddLine, PointSeed  # noqa: E402

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


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
            "id": "point_filter",
            "name": "Point selection",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    owner = general_session.GeneralSession(context)
    owner.start()
    result = owner.execute(context, AddLine(PointSeed(0, 0), PointSeed(40, 30)))
    deadline = time.monotonic() + 20
    while owner.pending and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not owner.error, "Actual line solve completes")
    commands, revision = owner.commands, owner.commands.revision
    request, response = owner.evidence_request, owner.evidence_response
    event = SimpleNamespace(mouse_x=region.x, mouse_y=region.y, value="PRESS", shift=False)
    owner.label_bounds = ()
    with patch.object(general_viewport, "_project", side_effect=lambda _owner, world: world[:2]):
        check(
            owner.selection_mode == "geometry", "New owner starts with explicit generic selection"
        )
        try:
            general_viewport._click(owner, context, event)
        except ValueError as error:
            check(
                "ambiguous" in str(error), "Generic endpoint/line tie is not silently prioritized"
            )
        else:
            raise AssertionError("Generic endpoint should be ambiguous")
        check(
            bpy.ops.mcad.general_tool(tool="Points") == {"FINISHED"},
            "Native Points control selects filter",
        )
        general_viewport._click(owner, context, event)
        check(
            owner.draft.selection == [{"kind": "point", "id": result.entity_ids[0]}],
            "Point-only adapter selects the exact endpoint ID",
        )
        check(
            owner.selection_mode == "point" and owner.draft.tool == "Select",
            "Filter is explicit transient UI mode",
        )
        check(
            owner.commands is commands and owner.commands.revision == revision,
            "Selection preserves command identity/history",
        )
        check(
            owner.evidence_request is request
            and owner.evidence_response is response
            and owner.can_finish,
            "Selection preserves current native evidence",
        )
        with patch.object(workspace, "get_role", return_value="SKETCH"):
            check(
                "POINTS" in workspace_ui.palette_actions(context),
                "Points is discoverable in the native CAD palette",
            )
        check(
            bpy.ops.mcad.general_tool(tool="Select") == {"FINISHED"}
            and owner.selection_mode == "geometry",
            "Generic Select explicitly leaves point-only mode",
        )
    owner.cleanup()
unregister()
print("CONSTRAINT_SELECTION_SMOKE_OK", len(checks))
