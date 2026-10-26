"""Select-point drag lifecycle through native Blender and the real guarded solver."""

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
from mechanical_cad_blender.general_sketch_commands import AddLine, AddRelation, PointSeed  # noqa: E402


def wait(owner):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    document_state._populate_document(
        bpy.context.scene,
        {
            "schema_version": 1,
            "id": "drag_part",
            "name": "Drag",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    canonical = bpy.context.scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(bpy.context)
    owner.start()
    a, b, line = owner.execute(bpy.context, AddLine(PointSeed(0, 0), PointSeed(30, 0))).entity_ids
    wait(owner)
    owner.execute(bpy.context, AddRelation("horizontal", (line,)))
    wait(owner)
    owner.draft.select_tool("Select")
    original, revision = owner.commands.sketch, owner.commands.revision
    event = SimpleNamespace(mouse_x=region.x + 30, mouse_y=region.y, shift=False, value="PRESS")
    # The real picker sees an endpoint and its incident line at identical pixels.
    with (
        patch.object(general_viewport, "_project", side_effect=lambda owner, world: world[:2]),
        patch.object(general_viewport, "_pointer", return_value=(30, 0)),
    ):
        general_viewport._click(owner, bpy.context, event)
    assert list(owner.draft.selection) == [{"kind": "point", "id": b}]
    assert owner.point_drag and not owner.can_use_tool("Line")
    owner.update_point_drag((32, 0), (32, 0))
    owner.finish_point_drag(bpy.context)
    assert owner.commands.revision == revision  # click jitter is not a model edit
    owner.begin_point_drag(b, (30, 0), (30, 0))
    owner.update_point_drag((50, 10), (50, 10))
    assert owner.commands.sketch == original
    owner.cancel_point_drag()
    assert owner.commands.sketch == original and owner.pending is None
    # Modal cancellation owns tails without suspending the sketch session.
    modal = SimpleNamespace(owner=owner)
    for event_type in ("ESC", "RIGHTMOUSE", "MIDDLEMOUSE", "WINDOW_DEACTIVATE"):
        owner.begin_point_drag(b, (30, 0), (30, 0))
        owner.update_point_drag((50, 10), (50, 10))
        result = general_viewport.MCAD_OT_general_sketch.modal(
            modal, bpy.context, SimpleNamespace(type=event_type, value="PRESS")
        )
        assert owner.point_drag is None and owner.alive
        assert owner.commands.sketch == original
        assert result == ({"PASS_THROUGH"} if event_type == "MIDDLEMOUSE" else {"RUNNING_MODAL"})
    owner.begin_point_drag(b, (30, 0), (30, 0))
    owner.update_point_drag((50, 10), (50, 10))
    with patch.object(general_viewport, "_over_view", return_value=False):
        general_viewport.MCAD_OT_general_sketch.modal(
            modal, bpy.context, SimpleNamespace(type="LEFTMOUSE", value="RELEASE")
        )
    assert owner.point_drag is None and owner.commands.sketch == original
    owner.begin_point_drag(b, (30, 0), (30, 0))
    owner.update_point_drag((50, 10), (50, 10))
    owner.finish_point_drag(bpy.context)
    wait(owner)
    assert owner.commands.revision == revision + 1
    assert owner.commands.sketch["constraints"] == original["constraints"]
    points = owner.geometry().points
    assert abs(points[a][1] - points[b][1]) < 1e-7
    moved = owner.commands.sketch
    owner.local_history(bpy.context)
    wait(owner)
    assert owner.commands.sketch == original
    owner.local_history(bpy.context, redo=True)
    wait(owner)
    assert owner.commands.sketch == moved
    assert bpy.context.scene.mechanical_cad.document_json == canonical
    owner.begin_point_drag(b, (50, 10), (50, 10))
    owner.suspend("Smoke cancellation")
    assert owner.point_drag is None
unregister()
print("GENERAL_POINT_DRAG_SMOKE_OK")
