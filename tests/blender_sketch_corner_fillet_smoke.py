"""Native owner/registered dialog contract smoke; deterministic selection, not mouse QA."""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_session,
    general_viewport,
    register,
    unregister,
    workspace,
    workspace_ui,
)
from mechanical_cad_blender.general_sketch_commands import AddRectangle, AddRelation, PointSeed  # noqa: E402


def wait(owner):
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.pending is None
    assert not owner.error, owner.error


operator = general_viewport.MCAD_OT_sketch_corner_fillet


def dialog(context, radius):
    op = SimpleNamespace(radius_mm=radius, report=lambda *args: None)
    for name in ("_prepare", "_failed", "cancel", "_preview"):
        method = getattr(operator, name)
        setattr(op, name, lambda *args, method=method: method(op, *args))

    class Context:
        window_manager = SimpleNamespace(
            invoke_props_dialog=lambda *args, **kwargs: {"RUNNING_MODAL"}
        )

        def __getattr__(self, name):
            return getattr(context, name)

    assert operator.invoke(op, Context(), None) == {"RUNNING_MODAL"}
    return op


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    document_state._populate_document(
        context.scene,
        {
            "schema_version": 1,
            "id": "fillet",
            "name": "Corner",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    owner = general_session.GeneralSession(context)
    owner.start()
    owner.execute(context, AddRectangle(PointSeed(0, 0), PointSeed(20, 10)))
    wait(owner)
    pts = [p["id"] for p in owner.commands.sketch["points"]]
    for command in (
        AddRelation("fixed", (pts[0],), target=(0, 0)),
        AddRelation("distance", (pts[0], pts[1]), value=20),
        AddRelation("distance", (pts[1], pts[2]), value=10),
    ):
        owner.execute(context, command)
        wait(owner)
    lines = tuple(line["id"] for line in owner.commands.sketch["lines"][:2])
    owner.draft.select(tuple(("line", i) for i in lines))
    context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    context.workspace[workspace.ROLE_KEY] = "SKETCH"
    assert operator.poll(context)
    assert workspace_ui.available(context, "CORNER_FILLET")
    assert "CORNER_FILLET" in workspace_ui.palette_actions(context)
    before = owner.commands.checkpoint_payload()
    old_ui = owner.draft.ui_version
    op = dialog(context, 100)
    assert operator.poll(context), "Owning props dialog must remain confirmable"
    class WrongArea:
        area = None

        def __getattr__(self, name):
            return getattr(context, name)

    binding = owner.gesture_intent
    assert not operator.poll(WrongArea())
    assert owner.gesture_intent is binding, "Unrelated editor polling must not cancel dialog"
    try:
        op._preview()
    except ValueError:
        pass
    else:
        raise AssertionError("Oversized radius preview accepted")
    assert owner.corner_fillet_preview is None
    op.radius_mm = 2
    op._preview()
    assert owner.corner_fillet_preview is not None
    op.cancel(context)
    assert owner.commands.checkpoint_payload() == before
    assert owner.draft.ui_version == old_ui
    assert owner.corner_fillet_preview is None
    # Stale selection is rejected before changing authoring.
    stale = dialog(context, 2)
    owner.draft.select(())
    assert not operator.poll(context), "Stale dialog must not remain confirmable"
    assert operator.execute(stale, context) == {"CANCELLED"}
    assert owner.commands.checkpoint_payload() == before
    owner.draft.select(tuple(("line", i) for i in lines))
    op = dialog(context, 2)
    assert operator.execute(op, context) == {"FINISHED"}
    wait(owner)
    assert owner.draft.ui_version == 2
    assert owner.commands.sketch["schema_version"] == 3
    assert owner.current_solution_response() is not None
    after = owner.commands.sketch
    assert len(after["arcs"]) == 1
    assert len(after["constraints"]) == 12
    radius_annotation = next(r["id"] for r in after["constraints"] if r["kind"] == "radius")
    assert owner.draft.annotations[radius_annotation]["offset"] == [0.0, -8.0]
    assert owner.geometry().arcs[after["arcs"][0]["id"]].corner_fillet
    assert operator.execute(op, context) == {"CANCELLED"}
    assert owner.commands.sketch == after
    owner.local_history(context)
    wait(owner)
    assert owner.commands.sketch == before["accepted_sketch"]
    owner.local_history(context, redo=True)
    wait(owner)
    assert owner.commands.sketch == after
    canonical = context.scene.mechanical_cad.document_json
    radius_id = next(r["id"] for r in after["constraints"] if r["kind"] == "radius")
    owner.begin_dimension(radius_id)
    owner.update_raw("100")
    owner.request_driver_accept(context)
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    assert owner.pending is None
    assert owner.error and "Corner Fillet" in owner.error, owner.error
    assert owner.commands.sketch == after
    assert owner.commands.pending_edit.raw_text == "100"
    assert context.scene.mechanical_cad.document_json == canonical
    owner.cancel_dimension()
    owner.check(context)
    wait(owner)
    owner.suspend("Smoke finished")
    bpy.ops.wm.save_as_mainfile(
        filepath=str(Path(os.environ["TMPDIR"]) / "corner-fillet-smoke.blend")
    )
unregister()
print("SKETCH_CORNER_FILLET_SMOKE_OK", flush=True)
