"""Native Blender rectangle owner, proposal, overlay, Undo/Redo and Finish seams."""

import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_session,
    general_sketch_overlay,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import PointSeed  # noqa: E402


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
            "id": "rectangle_part",
            "name": "Rectangle",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    owner = general_session.GeneralSession(bpy.context)
    owner.start()
    assert bpy.ops.mcad.general_tool(tool="Rectangle") == {"FINISHED"}
    assert owner.draft.tool == "Rectangle"
    owner.draft.begin_rectangle(PointSeed(0, 0))
    owner.draft.update_rectangle((20, 10))
    frame = general_sketch_overlay.build_frame(
        owner.geometry(),
        lambda world: (world[0], world[1]),
        proposal=owner.draft.proposal,
    )
    assert len([stroke for stroke in frame.strokes if stroke.proposal]) == 4
    assert bpy.ops.mcad.general_tool(tool="CancelProposal") == {"FINISHED"}
    assert owner.draft.proposal is None and not owner.commands.sketch["lines"]
    owner.draft.begin_rectangle(PointSeed(0, 0), (20, 10))
    owner.proposal_capture = True
    owner.accept_proposal(bpy.context)
    wait(owner)
    assert owner.can_finish and owner.commands.has_current_solution
    assert len(owner.commands.sketch["constraints"]) == 4
    owner.local_history(bpy.context)
    wait(owner)
    assert not owner.commands.sketch["lines"]
    owner.local_history(bpy.context, redo=True)
    wait(owner)
    assert len(owner.commands.sketch["lines"]) == 4 and owner.can_finish
    owner.request_finish(bpy.context)
    wait(owner)
    assert owner.finished, owner.error
    assert '"horizontal"' in bpy.context.scene.mechanical_cad.document_json
unregister()
print("GENERAL_RECTANGLE_SMOKE_OK")
