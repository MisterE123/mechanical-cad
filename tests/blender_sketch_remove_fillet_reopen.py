"""Second-process Restore Sharp Corner raw-intent and annotation restoration."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, sketch_session, unregister, workspace  # noqa: E402

register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")


def enter(context, role, on_ready=None):
    context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    context.workspace[workspace.ROLE_KEY] = role
    if on_ready:
        on_ready(context)
    return True


def wait(owner):
    deadline = time.monotonic() + 60
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error


with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    saved = context.scene.mechanical_cad.sketch_draft_json
    assert "remove_corner_fillet" in saved
    with patch.object(workspace, "request_workspace", side_effect=enter):
        assert bpy.ops.mcad.resume_sketch() == {"FINISHED"}
    owner = sketch_session.active_session(context)
    assert owner.current_solution_response() is None and not owner.can_finish
    assert owner.pending is None and owner.removal_attempt is None
    assert len(owner.commands.sketch["arcs"]) == 3
    annotations = owner.draft.annotations
    assert any(s.state == "retired" for s in owner.draft.status.annotations)
    owner.check(context)
    wait(owner)
    owner.local_history(context)
    wait(owner)
    assert len(owner.commands.sketch["arcs"]) == 4
    assert all(s.available for s in owner.draft.status.annotations)
    original_annotations = {key: {field: value for field, value in binding.items() if field != "retirement"}
                            for key, binding in annotations.items()}
    assert owner.draft.annotations == original_annotations
    owner.local_history(context, redo=True)
    wait(owner)
    assert len(owner.commands.sketch["arcs"]) == 3
    assert owner.draft.annotations == annotations
    owner.suspend("Sharp-corner reopen verified")
unregister()
print("SKETCH_REMOVE_FILLET_REOPEN_OK", flush=True)
