"""Native unfinished Circle diameter: draft-only acceptance and raw recovery."""
import math
import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    dimension_input,
    document_state,
    draft_dispatch,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddCircle,
    DraftError,
    PointRef,
    PointSeed,
)


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
    assert owner.draft.pending_diameter["raw_text"] == raw


def begin(owner, center, raw):
    owner.draft.select_tool("Circle")
    owner.draft.begin_circle(center)
    owner.proposal_capture = True
    owner.open_circle_diameter(bpy.context)
    text(owner, raw)


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
objects = set(bpy.data.objects)
with bpy.context.temp_override(window=window, area=area, region=region):
    document_state._populate_document(bpy.context.scene, {
        "schema_version": 1, "id": "diameter", "name": "Diameter", "units": "mm", "parameters": {},
        "features": [], "active_feature": None,
    })
    canonical = bpy.context.scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(bpy.context)
    owner.start()
    begin(owner, PointSeed(3, 4), "2 cm")
    owner.request_circle_diameter_accept(bpy.context)
    try:
        owner.request_circle_diameter_accept(bpy.context)
        raise AssertionError("Repeated Enter started a second acceptance")
    except DraftError:
        pass
    wait(owner)
    assert owner.draft.pending_diameter is None and owner.draft.proposal is None
    circle = next(iter(owner.geometry().circles.values()))
    assert math.dist(circle.center_mm, (3, 4)) < 1e-7
    assert math.isclose(circle.radius_mm, 10)
    driver = owner.commands.sketch["constraints"][0]
    assert driver["kind"] == "radius" and driver["value"] == 10
    assert owner.draft.annotations[driver["id"]]["display"] == "diameter"
    assert bpy.context.scene.mechanical_cad.document_json == canonical
    owner.local_history(bpy.context)
    wait(owner, success=False)
    assert not owner.commands.sketch.get("circles") and not owner.commands.sketch["constraints"]
    owner.local_history(bpy.context, redo=True)
    wait(owner)
    assert owner.draft.annotations[driver["id"]]["display"] == "diameter"
    # An unrelated ordinary free circle retains its solved size, as does the first driver.
    owner.execute(bpy.context, AddCircle(PointSeed(50, 60), 7))
    wait(owner)
    before_radii = {k: v.radius_mm for k, v in owner.geometry().circles.items()}
    before_points = dict(owner.geometry().points)
    center = owner.commands.sketch["circles"][0]["center"]
    begin(owner, PointRef(center), "10 mm")
    owner.request_circle_diameter_accept(bpy.context)
    wait(owner)
    assert all(math.dist(owner.geometry().points[k], v) < 1e-7 for k, v in before_points.items())
    assert all(abs(owner.geometry().circles[k].radius_mm - v) < 1e-7 for k, v in before_radii.items())
    assert owner.commands.sketch["circles"][-1]["center"] == center
    print("CIRCLE_DIAMETER_REUSE_AND_RADII_OK", flush=True)
    begin(owner, PointSeed(100, 100), "width + 1")
    raw, original = draft_dispatch.dumps(owner.draft), owner.draft.proposal
    try:
        owner.request_circle_diameter_accept(bpy.context)
        raise AssertionError("Formula accepted")
    except DraftError as exc:
        assert "Dimension" in str(exc)
    assert draft_dispatch.dumps(owner.draft) == raw
    owner.cancel_dimension()
    assert owner.draft.proposal == original and owner.draft.pending_diameter is None
    owner.proposal_capture = True
    owner.open_circle_diameter(bpy.context)
    text(owner, "5 mm")
    saved = draft_dispatch.dumps(owner.draft)
    owner.suspend("Test raw recovery")
    owner = general_session.GeneralSession(bpy.context, restored=draft_dispatch.restore(saved, canonical))
    owner.start()
    assert owner.input_controller is None and not owner.input_token and not owner.proposal_capture
    assert owner.diameter_attempt is None and owner.pending is None
    owner.open_circle_diameter(bpy.context)
    owner.request_circle_diameter_accept(bpy.context)
    wait(owner)
    assert len(owner.commands.sketch["circles"]) == 4
    begin(owner, PointSeed(80, 80), "10 mm")
    owner.request_circle_diameter_accept(bpy.context)
    owner.cancel_dimension()
    assert owner.draft.proposal is not None and owner.draft.pending_diameter is None
    owner.cancel_line_proposal()
    assert owner.draft.proposal is None and len(owner.commands.sketch["circles"]) == 4
    from mechanical_cad_blender import execution_lease, sketch_pending
    deadline = time.monotonic() + 30
    while execution_lease.is_busy() and time.monotonic() < deadline:
        sketch_pending.reap()
        time.sleep(.01)
    begin(owner, PointSeed(50, 50), "10 mm")
    owner.request_circle_diameter_accept(bpy.context)
    owner.input_token = "f" * 32
    wait(owner, success=False)
    assert owner.error and len(owner.commands.sketch["circles"]) == 4
    assert owner.draft.pending_diameter["raw_text"] == "10 mm"
    owner.cancel_dimension()
    owner.cancel_line_proposal()
    assert bpy.context.scene.mechanical_cad.document_json == canonical
    owner.discard()
assert set(bpy.data.objects) == objects
unregister()
print("CIRCLE_DIAMETER_OWNER_SMOKE_OK", flush=True)
