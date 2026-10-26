"""Second-process reopening of the actual saved fillet owner smoke .blend."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import general_session, register, sketch_session, unregister, workspace  # noqa: E402

register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")


def enter(context, role, on_ready=None):
    assert role == "SKETCH"
    context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    context.workspace[workspace.ROLE_KEY] = role
    if on_ready:
        on_ready(context)
    return True


with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    saved = context.scene.mechanical_cad.sketch_draft_json
    assert saved and "fillet_intent" in saved
    with patch.object(workspace, "request_workspace", side_effect=enter):
        assert bpy.ops.mcad.resume_sketch() == {"FINISHED"}
    owner = sketch_session.active_session(context)
    assert type(owner) is general_session.GeneralSession
    assert owner.current_solution_response() is None
    assert not owner.can_finish
    assert owner.pending is None
    assert getattr(owner, "corner_fillet_preview", None) is None
    assert owner.commands.sketch["arcs"][0]["fillet_intent"]["version"] == 2
    assert len(owner.commands.sketch["arcs"]) == 4
    assert all(all(a["fillet_intent"]["neighbors"]) for a in owner.commands.sketch["arcs"])
    after = owner.commands.sketch
    owner.check(context)
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error
    assert owner.current_solution_response() is not None
    assert owner.commands.sketch == after
    owner.suspend("Reopen verified")
unregister()
print("SKETCH_ADJACENT_FILLET_REOPEN_OK", flush=True)
