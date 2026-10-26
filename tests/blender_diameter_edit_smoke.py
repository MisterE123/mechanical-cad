"""Native diameter edit route/owner checks; popup adapter is not real GUI evidence."""
import copy
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    constraint_ui,
    dimension_input,
    document_state,
    draft_dispatch,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import PointSeed  # noqa: E402


def wait(owner):
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(.01)
    assert owner.pending is None and not owner.error, owner.error


def invoke(owner, rid):
    ctx = bpy.context
    proxy = NS(window=ctx.window, scene=ctx.scene, area=ctx.area, workspace=ctx.workspace,
               view_layer=ctx.view_layer,
               window_manager=NS(invoke_props_dialog=lambda op: {"RUNNING_MODAL"}))
    op = NS(mode="DIAMETER", constraint_id=rid, errors=[])
    op.report = lambda level, message: op.errors.append(message)
    assert constraint_ui.MCAD_OT_sketch_numeric_relation.invoke(op, proxy, None) == {"RUNNING_MODAL"}, op.errors
    return op


def apply(owner, op, raw=None):
    if raw is not None:
        op.value = raw
    assert constraint_ui.MCAD_OT_sketch_numeric_relation.execute(op, bpy.context) == {"FINISHED"}, op.errors
    wait(owner)


def radius(owner):
    return next(iter(owner.geometry().circles.values())).radius_mm


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    document_state._populate_document(bpy.context.scene, {
        "schema_version": 1, "id": "diameter_edit", "name": "Diameter edit", "units": "mm",
        "parameters": {"size": 20}, "features": [], "active_feature": None,
    })
    canonical = bpy.context.scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(bpy.context)
    owner.start()
    # Exercise the registered RNA field, not a SimpleNamespace string: display of a
    # full 256-character source must survive assignment without truncation.
    cls = constraint_ui.MCAD_OT_sketch_numeric_relation
    original_execute = cls.execute
    long_display = "2*(size" + " " * 252 + ")"
    seen = []
    def inspect_rna(self, context):
        seen.append(self.value)
        return {"FINISHED"}
    try:
        cls.execute = inspect_rna
        assert bpy.ops.mcad.sketch_numeric_relation("EXEC_DEFAULT", mode="DIAMETER", value=long_display) == {"FINISHED"}
        assert seen == [long_display] and len(seen[0]) == 260
    finally:
        cls.execute = original_execute

    owner.draft.select_tool("Circle")
    owner.draft.begin_circle(PointSeed(3, 4))
    owner.proposal_capture = True
    owner.open_circle_diameter(bpy.context)
    owner.input_controller.handle(
        dimension_input.InputEvent("A", unicode="20 mm"),
        approve_raw=lambda action: (owner.update_raw(action.raw) is None),
    )
    owner.request_circle_diameter_accept(bpy.context)
    wait(owner)
    rid = owner.commands.sketch["constraints"][0]["id"]
    before = draft_dispatch.dumps(owner.draft)
    op = invoke(owner, rid)
    assert op.value == "20.0"
    # Cancel/dismiss has no command to roll back.
    assert draft_dispatch.dumps(owner.draft) == before
    apply(owner, op)
    assert draft_dispatch.dumps(owner.draft) == before
    apply(owner, invoke(owner, rid), "3 cm")
    assert radius(owner) == 15
    assert owner.commands.sketch["constraints"][0]["value"] == "15.0"
    assert owner.draft.annotations[rid]["display"] == "diameter"
    owner.local_history(bpy.context)
    wait(owner)
    assert radius(owner) == 10
    owner.local_history(bpy.context, redo=True)
    wait(owner)
    assert radius(owner) == 15
    apply(owner, invoke(owner, rid), "size + 4")
    assert radius(owner) == 12
    assert owner.commands.sketch["constraints"][0]["value"] == "(size + 4)/2"
    before = draft_dispatch.dumps(owner.draft)
    op = invoke(owner, rid)
    assert op.value == "2*((size + 4)/2)"
    apply(owner, op)
    assert draft_dispatch.dumps(owner.draft) == before
    stale = invoke(owner, rid)
    owner.draft.move_annotation(rid, (20, 20))
    owner.checkpoint()
    stale.value = "100"
    assert constraint_ui.MCAD_OT_sketch_numeric_relation.execute(stale, bpy.context) == {"CANCELLED"}
    assert "sketch changed" in stale.errors[-1] and radius(owner) == 12
    assert bpy.context.scene.mechanical_cad.document_json == canonical
    # Existing raw radius edits retain their exact input through serialization.
    owner.begin_dimension(rid)
    owner.update_raw("size / 2")
    saved = draft_dispatch.dumps(owner.draft)
    restored = draft_dispatch.restore(saved, canonical)
    assert restored.command_draft.pending_edit.raw_text == "size / 2"
    owner.cancel_dimension()
    owner.check(bpy.context)
    wait(owner)
    document = copy.deepcopy(owner.commands.candidate())
    feature_id = owner.commands.feature_id
    document["features"].append({"id": "pad", "kind": "extrude", "params": {"length": 5},
                                 "inputs": {"profile": feature_id}})
    document["active_feature"] = "pad"
    owner.discard()
    document_state._populate_document(bpy.context.scene, document)
    canonical = bpy.context.scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(bpy.context, feature_id=feature_id)
    owner.start()
    owner.check(bpy.context)
    wait(owner)
    owner.draft.place_annotation(rid, (8, 8), display="diameter")
    owner.checkpoint()
    assert owner.commands.consumed_by
    started = []
    start_job = owner._start_job
    def observed(context, request, kind, **kwargs):
        started.append(kind)
        return start_job(context, request, kind, **kwargs)
    owner._start_job = observed
    apply(owner, invoke(owner, rid), "size")
    assert radius(owner) == 10 and "downstream" in started, started
    assert owner.commands.pending_edit is None
    assert bpy.context.scene.mechanical_cad.document_json == canonical
    owner.discard()
unregister()
print("DIAMETER_EDIT_SMOKE_OK", flush=True)
