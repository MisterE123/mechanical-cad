"""Real Blender owner: attached drawing, suspend/resume, finish, upstream movement."""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    draft_dispatch,
    general_session,
    general_viewport,
    register,
    unregister,
    workspace,
)
from mechanical_cad_blender.general_sketch_draft import PointSeed  # noqa: E402

register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")


def wait(owner, context):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    assert owner.pending is None, "Native solve deadline"
    assert not owner.error, owner.error


with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    state = context.scene.mechanical_cad
    assert bpy.ops.mcad.new_document(name="Drawn associative face") == {"FINISHED"}
    assert bpy.ops.mcad.add_rectangle(width=20, height=20) == {"FINISHED"}
    profile = state.active_feature
    assert bpy.ops.mcad.add_extrude(profile=profile, length=10) == {"FINISHED"}
    block = state.active_feature
    support = {"feature_id": block, "face_id": block + "/face/cap.end"}
    assert bpy.ops.mcad.new_face_sketch.get_rna_type()
    owner = general_session.GeneralSession(context, support=support)
    owner.start()
    assert tuple(owner.geometry().plane.origin_mm) == (10, 10, 10)
    assert owner.commands.sketch["plane"]["origin"] == [0, 0, 0]
    general_viewport._align_plane(owner, frame=True)
    owner.draft.begin_circle(PointSeed(0, 0), 2)
    owner.proposal_capture = True
    owner.accept_proposal(context)
    wait(owner, context)
    assert owner.geometry().source == "solved"
    assert tuple(owner.geometry().plane.origin_mm) == (10, 10, 10)
    owner.suspend("Test draft persistence")
    bpy.ops.wm.save_as_mainfile(filepath="/tmp/attached_sketch_draft.blend")
    snapshot = state.sketch_draft_json
    restored = draft_dispatch.restore(snapshot, state.document_json)
    owner = general_session.GeneralSession(context, restored=restored)
    owner.start()
    assert tuple(owner.geometry().plane.origin_mm) == (10, 10, 10)
    owner.check(context)
    wait(owner, context)
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        wait(owner, context)
    assert owner.finished
    saved = json.loads(state.document_json)
    attached = saved["features"][-1]
    assert attached["support_face"] == support["face_id"]
    assert attached["sketch"]["plane"]["origin"] == [0, 0, 0]
    assert bpy.ops.mcad.add_extrude(profile=attached["id"], length=-3) == {"FINISHED"}
    for f in (changed := json.loads(state.document_json))["features"]:
        if f["id"] == block:
            f["params"]["length"] = 25
    document_state._commit_candidate(context, changed)
    assert state.status == "READY", state.error
    row = next(
        f
        for f in document_state.current_part_result(context)["features"]
        if f["id"] == attached["id"]
    )
    assert row["support_plane"]["origin"] == [10, 10, 25]
    owner = general_session.GeneralSession(context, attached["id"])
    owner.start()
    assert tuple(owner.geometry().plane.origin_mm) == (10, 10, 25)
    owner.discard("Test complete")
    bpy.ops.wm.save_as_mainfile(
        filepath=os.environ.get("MCAD_SMOKE_OUTPUT", "/tmp/attached_sketch.blend")
    )
print("MCAD_ATTACHED_SKETCH_SMOKE_OK", flush=True)
unregister()
