"""Fresh process restores an attached draft without treating cached geometry as evidence."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(os.environ["MCAD_ROOT"]) / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    draft_dispatch,
    general_session,
    register,
    unregister,
    workspace,
)

register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    state = context.scene.mechanical_cad
    original = state.document_json
    snapshot = state.sketch_draft_json
    assert snapshot
    assert document_state.current_part_result(context) is None
    document_state.regenerate(context)
    assert state.document_json == original and state.sketch_draft_json == snapshot
    restored = draft_dispatch.restore(snapshot, original)
    owner = general_session.GeneralSession(context, restored=restored)
    owner.start()
    assert owner.geometry().source == "authored"
    assert tuple(owner.geometry().plane.origin_mm) == (10, 10, 10)
    assert owner.commands.sketch["plane"]["origin"] == [0, 0, 0]
    owner.check(context)
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error
    assert owner.geometry().source == "solved"
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        deadline = time.monotonic() + 30
        while owner.pending is not None and time.monotonic() < deadline:
            owner.tick(context)
            time.sleep(0.01)
    assert owner.finished and not owner.error, owner.error
print("MCAD_ATTACHED_SKETCH_REOPEN_SMOKE_OK", flush=True)
unregister()
