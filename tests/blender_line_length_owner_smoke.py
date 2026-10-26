"""Native pending Line-length owner: atomic acceptance and retained raw recovery."""
import math
import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402  # noqa: E402
    dimension_input,
    document_state,
    draft_dispatch,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import DraftError, PointRef, PointSeed  # noqa: E402


def wait(owner, *, success=True):
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(.01)
    assert owner.pending is None, "Native check timed out"
    if success:
        assert not owner.error, owner.error


def text(owner, raw):
    owner.input_controller.handle(
        dimension_input.InputEvent("A", unicode=raw),
        approve_raw=lambda action: (owner.update_raw(action.raw) is None),
    )
    assert owner.draft.pending_length["raw_text"] == raw


def begin(owner, start, end, raw, axis=None):
    owner.draft.select_tool("Line")
    owner.accept_point_input(bpy.context, start, expected_phase=("line", "start"))
    owner.open_line_length(bpy.context, end, axis=axis)
    text(owner, raw)


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
objects = set(bpy.data.objects)
with bpy.context.temp_override(window=window, area=area, region=region):
    document_state._populate_document(bpy.context.scene, {
        "schema_version": 1, "id": "length", "name": "Length", "units": "mm", "parameters": {},
        "features": [], "active_feature": None,
    })
    canonical = bpy.context.scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(bpy.context)
    owner.start()
    begin(owner, PointSeed(3, 4), PointSeed(6, 8), "2 cm")
    before = owner.commands.checkpoint_payload()
    owner.request_line_length_accept(bpy.context)
    try:
        owner.request_line_length_accept(bpy.context)
        raise AssertionError("Repeated Enter started a second acceptance")
    except DraftError:
        pass
    wait(owner)
    assert owner.draft.pending_length is None and owner.draft.proposal is None
    assert len(owner.commands.sketch["lines"]) == 1
    assert len(owner.commands.sketch["constraints"]) == 1
    assert owner.commands.sketch["constraints"][0]["kind"] == "distance"
    line = next(iter(owner.geometry().lines.values()))
    assert math.dist(line.start_mm, (3, 4)) < 1e-7
    assert math.dist(line.end_mm, (15, 20)) < 1e-7
    assert math.isclose(math.dist(line.start_mm, line.end_mm), 20)
    assert bpy.context.scene.mechanical_cad.document_json == canonical
    print("FIRST_LENGTH_OK", flush=True)
    owner.local_history(bpy.context)
    wait(owner, success=False)  # Empty sketch has no solvable/profile geometry.
    assert not owner.commands.sketch["lines"] and not owner.commands.sketch["constraints"]
    owner.local_history(bpy.context, redo=True)
    wait(owner)
    assert len(owner.commands.sketch["lines"]) == 1
    endpoint = owner.commands.sketch["lines"][0]["end"]
    begin(owner, PointRef(endpoint), PointSeed(25, 20), "10 mm", "horizontal")
    owner.request_line_length_accept(bpy.context)
    wait(owner)
    assert len(owner.commands.sketch["constraints"]) == 3
    assert owner.commands.sketch["constraints"][-1]["kind"] == "horizontal"
    assert math.dist(owner.geometry().points[endpoint], (15, 20)) < 1e-7
    print("REUSED_AXIS_LENGTH_OK", flush=True)
    begin(owner, PointSeed(1, 2), PointSeed(6, 2), "width + 1")
    raw = draft_dispatch.dumps(owner.draft)
    original = owner.draft.proposal
    try:
        owner.request_line_length_accept(bpy.context)
        raise AssertionError("Formula accepted")
    except DraftError as exc:
        assert "Dimension" in str(exc)
    assert draft_dispatch.dumps(owner.draft) == raw
    owner.cancel_dimension()
    assert owner.draft.proposal == original and owner.draft.pending_length is None
    owner.proposal_capture = True
    owner.open_line_length(bpy.context, PointSeed(6, 2))
    text(owner, "5 mm")
    saved = draft_dispatch.dumps(owner.draft)
    owner.suspend("Test raw recovery")
    restored = draft_dispatch.restore(saved, canonical)
    owner = general_session.GeneralSession(bpy.context, restored=restored)
    owner.start()
    assert owner.input_controller is None and not owner.input_token and not owner.proposal_capture
    assert owner.draft.pending_length["raw_text"] == "5 mm"
    owner.open_line_length(bpy.context)
    owner.request_line_length_accept(bpy.context)
    wait(owner)
    assert len(owner.commands.sketch["lines"]) == 3
    begin(owner, PointSeed(0, 0), PointSeed(0, 10), "10 mm", "vertical")
    owner.request_line_length_accept(bpy.context)
    owner.cancel_dimension()
    assert owner.draft.proposal is not None and owner.draft.pending_length is None
    owner.cancel_line_proposal()
    assert owner.draft.proposal is None
    assert len(owner.commands.sketch["lines"]) == 3
    # Let the shared supervisor release cancelled native resources, without
    # considering this cleanup an acceptance or retrying its old callback.
    from mechanical_cad_blender import execution_lease, sketch_pending
    deadline = time.monotonic() + 30
    while execution_lease.is_busy() and time.monotonic() < deadline:
        sketch_pending.reap()
        time.sleep(.01)
    begin(owner, PointSeed(50, 50), PointSeed(60, 50), "10 mm")
    owner.request_line_length_accept(bpy.context)
    owner.input_token = "f" * 32  # stale callback must not accept this new lease
    wait(owner, success=False)
    assert owner.error and len(owner.commands.sketch["lines"]) == 3
    assert owner.draft.pending_length["raw_text"] == "10 mm"
    owner.cancel_dimension()
    owner.cancel_line_proposal()
    owner.discard()
assert set(bpy.data.objects) == objects
unregister()
print("LINE_LENGTH_OWNER_SMOKE_OK", flush=True)
