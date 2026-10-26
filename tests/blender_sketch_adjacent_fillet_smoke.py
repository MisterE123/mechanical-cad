"""Adjacent-fillet owner transactions; deterministic selection, not mouse QA."""

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
    document_state._populate_document(context.scene, {
        "schema_version": 1, "id": "adjacent_fillet", "name": "Four Corners",
        "units": "mm", "parameters": {}, "features": [], "active_feature": None,
    })
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
    lines = [line["id"] for line in owner.commands.sketch["lines"]]
    original = owner.commands.sketch
    canonical = context.scene.mechanical_cad.document_json
    context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    context.workspace[workspace.ROLE_KEY] = "SKETCH"
    for index, radius in enumerate((1, 2, 3, 2)):
        pair = (lines[index], lines[(index + 1) % 4])
        owner.draft.select(tuple(("line", i) for i in pair))
        assert operator.poll(context)
        before = owner.commands.sketch
        op = dialog(context, radius)
        op._preview()
        op.cancel(context)
        assert owner.commands.sketch == before
        op = dialog(context, radius)
        assert operator.execute(op, context) == {"FINISHED"}
        wait(owner)
        after = owner.commands.sketch
        assert len(after["arcs"]) == index + 1
        assert context.scene.mechanical_cad.document_json == canonical
        assert operator.execute(op, context) == {"CANCELLED"}
        assert owner.commands.sketch == after
        owner.local_history(context)
        wait(owner)
        assert owner.commands.sketch == before
        owner.local_history(context, redo=True)
        wait(owner)
        assert owner.commands.sketch == after
    assert all(all(a["fillet_intent"]["neighbors"]) for a in after["arcs"])
    assert after["constraints"][:len(original["constraints"])] == original["constraints"]
    radius_id = next(r["id"] for r in after["constraints"] if r["kind"] == "radius")
    owner.begin_dimension(radius_id)
    owner.update_raw("3")
    owner.request_driver_accept(context)
    wait(owner)
    accepted = owner.commands.sketch
    assert float(next(r["value"] for r in accepted["constraints"] if r["id"] == radius_id)) == 3
    # The first corner has a 2 mm neighbor on a 10 mm original span.
    # A radius of 9 is individually interior, but overlaps that neighbor.
    owner.begin_dimension(radius_id)
    owner.update_raw("9")
    owner.request_driver_accept(context)
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    assert owner.pending is None and owner.error, owner.error
    assert "Corner Fillet" in owner.error, owner.error
    assert owner.commands.sketch == accepted
    assert owner.commands.pending_edit.raw_text == "9"
    assert context.scene.mechanical_cad.document_json == canonical
    owner.cancel_dimension()
    owner.check(context)
    wait(owner)
    assert not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules)
    owner.suspend("Adjacent fillet smoke complete")
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(os.environ["TMPDIR"]) / "adjacent-fillet-smoke.blend"))
unregister()
print("SKETCH_ADJACENT_FILLET_SMOKE_OK", flush=True)
