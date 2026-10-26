"""Fresh-process readback of the GUI-authored raw draft, not another GUI test."""

import json
import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    draft_dispatch,
    face_pick,
    general_session,
    register,
    solid_review,
    unregister,
)

expected = json.loads(Path(os.environ["MCAD_CHOICE_EXPECTED"]).read_text())
register()
bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_CHOICE_BLEND"])
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    state = context.scene.mechanical_cad
    assert json.loads(state.document_json) == expected["document"]
    assert state.sketch_draft_json == expected["draft"]
    assert not face_pick._PICKERS and not solid_review._REVIEWS
    document_state.regenerate(context)
    restored = draft_dispatch.restore(state.sketch_draft_json, state.document_json)
    owner = general_session.GeneralSession(context, restored=restored)
    owner.start()
    assert not owner.commands.has_current_solution
    assert getattr(owner, "solid_projection_picker", None) is None
    owner.check(context)
    deadline = time.monotonic() + 60
    while owner.pending is not None:
        assert time.monotonic() < deadline
        owner.tick(context)
        time.sleep(0.01)
    assert not owner.error, owner.error
    assert owner.commands.has_current_solution
    assert owner.commands.candidate() == expected["owner"]["candidate"]
    owner.suspend("Fresh raw edge-reference readback verified")
assert "OCP" not in sys.modules and "slvs" not in sys.modules
unregister()
print("MCAD_PROJECTION_EDGE_CHOICE_REOPEN_OK", flush=True)
