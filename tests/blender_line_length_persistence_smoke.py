"""Run separately with MCAD_LENGTH_PHASE=save then resume against one .blend."""
import json
import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
TARGET = Path(os.environ["MCAD_LENGTH_BLEND"])
PHASE = os.environ["MCAD_LENGTH_PHASE"]
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    dimension_input,
    document_state,
    draft_dispatch,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import AddLine, PointRef, PointSeed  # noqa: E402


def wait(owner):
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(.01)
    assert owner.pending is None and not owner.error, owner.error


register()
if PHASE == "resume":
    bpy.ops.wm.open_mainfile(filepath=str(TARGET))
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    if PHASE == "save":
        document_state._populate_document(bpy.context.scene, {
            "schema_version": 1, "id": "length_recovery", "name": "Recovery", "units": "mm",
            "parameters": {}, "features": [], "active_feature": None,
        })
        owner = general_session.GeneralSession(bpy.context)
        owner.start()
        owner.execute(bpy.context, AddLine(PointSeed(0, 0), PointSeed(10, 0)))
        wait(owner)
        point_id = owner.commands.sketch["lines"][0]["end"]
        owner.draft.select_tool("Line")
        owner.accept_point_input(bpy.context, PointRef(point_id), expected_phase=("line", "start"))
        owner.open_line_length(bpy.context, PointSeed(30, 0), axis="horizontal")
        owner.input_controller.handle(
            dimension_input.InputEvent("A", unicode=" 2 cm "),
            approve_raw=lambda action: (owner.update_raw(action.raw) is None),
        )
        saved_intent = owner.draft.pending_length
        canonical = bpy.context.scene.mechanical_cad.document_json
        owner.request_line_length_accept(bpy.context)
        assert owner.pending is not None and owner.length_attempt is not None
        # Save hooks checkpoint only raw intent. The live process may keep its
        # owner, but the second process must not restore its acceptance request.
        bpy.ops.wm.save_as_mainfile(filepath=str(TARGET))
        TARGET.with_suffix('.json').write_text(json.dumps({
            "intent": saved_intent, "canonical": canonical, "point_id": point_id,
            "sketch": owner.commands.sketch,
        }))
        persisted = draft_dispatch.restore(
            bpy.context.scene.mechanical_cad.sketch_draft_json, canonical
        )
        assert persisted.pending_length == saved_intent
        owner.suspend("Close first-process persistence fixture")
        print("LINE_LENGTH_PERSIST_SAVE_OK", flush=True)
    else:
        expected = json.loads(TARGET.with_suffix('.json').read_text())
        raw = bpy.context.scene.mechanical_cad.sketch_draft_json
        restored = draft_dispatch.restore(raw, expected["canonical"])
        assert restored.pending_length == expected["intent"]
        assert restored.command_draft.sketch == expected["sketch"]
        owner = general_session.GeneralSession(bpy.context, restored=restored)
        owner.start()
        assert owner.input_controller is None and not owner.input_token
        assert owner.length_attempt is None and owner.pending is None
        assert not owner.proposal_capture and not owner.commands.has_current_solution
        assert owner.guarded_evidence is None and owner.expected_prepared is None
        assert len(owner.commands.sketch["lines"]) == 1
        owner.open_line_length(bpy.context)
        assert owner.input_controller.raw == " 2 cm "
        owner.request_line_length_accept(bpy.context)
        wait(owner)
        assert len(owner.commands.sketch["lines"]) == 2
        assert owner.commands.sketch["lines"][-1]["start"] == expected["point_id"]
        assert owner.geometry().points[expected["point_id"]] == (10, 0)
        assert bpy.context.scene.mechanical_cad.document_json == expected["canonical"]
        owner.discard()
        print("LINE_LENGTH_PERSIST_RESUME_OK", flush=True)
unregister()
