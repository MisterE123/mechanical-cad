"""Real owner axis acceptance: fresh guard, atomic history and native sidecar."""
import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import document_state, general_session, register, unregister  # noqa: E402
from mechanical_cad_blender.general_sketch_commands import AddPoint, DraftError, PointRef, PointSeed  # noqa: E402


def wait(owner):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(.01)
    assert owner.pending is None and not owner.error, owner.error


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    document_state._populate_document(bpy.context.scene, {
        "schema_version": 1, "id": "axis", "name": "Axis", "units": "mm", "parameters": {},
        "features": [], "active_feature": None,
    })
    owner = general_session.GeneralSession(bpy.context)
    owner.start()
    bpy.ops.mcad.general_tool(tool="Line")
    owner.execute(bpy.context, AddPoint(PointSeed(10, 1)))
    wait(owner)
    off = owner.commands.sketch["points"][0]["id"]
    owner.accept_point_input(bpy.context, PointSeed(0, 0), expected_phase=("line", "start"))
    before = owner.commands.checkpoint_payload()
    try:
        owner.accept_point_input(bpy.context, PointRef(off), expected_phase=("line", "end"), axis="horizontal")
        raise AssertionError("Owner accepted off-axis reuse")
    except DraftError as exc:
        assert "off axis" in str(exc)
    assert owner.commands.checkpoint_payload() == before
    assert owner.draft.proposal is not None
    owner.accept_point_input(bpy.context, PointSeed(10, 0), expected_phase=("line", "end"), axis="horizontal")
    wait(owner)
    assert owner.commands.sketch["constraints"][0]["kind"] == "horizontal"
    geometry = owner.geometry()
    assert geometry.source == "solved"
    relation = owner.commands.sketch["constraints"][0]
    assert geometry.axis_relations[relation["id"]] == ("horizontal", relation["refs"][0])
    owner.local_history(bpy.context)
    wait(owner)
    assert not owner.commands.sketch["lines"] and not owner.commands.sketch["constraints"]
    assert owner.commands.sketch["points"][0]["v"] == 1
    owner.local_history(bpy.context, redo=True)
    wait(owner)
    assert len(owner.commands.sketch["lines"]) == len(owner.commands.sketch["constraints"]) == 1
    owner.discard()
unregister()
print("LINE_AXIS_OWNER_SMOKE_OK")
