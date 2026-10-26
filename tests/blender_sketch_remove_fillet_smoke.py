"""Native owner Restore Sharp Corner lifecycle; not interactive mouse QA."""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_session,
    general_viewport,
    register,
    unregister,
    workspace,
)
from mechanical_cad_blender import (  # noqa: E402
    general_sketch_commands as c,
)
from mechanical_cad_blender import (  # noqa: E402
    general_sketch_draft as d,
)

BASE = {"schema_version": 1, "id": "restore_corner", "name": "Restore Sharp Corner",
        "units": "mm", "parameters": {}, "features": [], "active_feature": None}
operator = general_viewport.MCAD_OT_remove_sketch_fillet


def wait(owner, *, failed=False):
    deadline = time.monotonic() + 60
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.pending is None, "Removal job did not settle"
    assert bool(owner.error) == failed, owner.error


def dialog(context):
    op = SimpleNamespace(report=lambda *args: None)
    for name in ("_prepare", "_failed", "cancel", "_review"):
        method = getattr(operator, name)
        setattr(op, name, lambda *args, method=method: method(op, *args))

    class Context:
        window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"})

        def __getattr__(self, name):
            return getattr(context, name)

    assert operator.invoke(op, Context(), None) == {"RUNNING_MODAL"}
    return op


def positions(draft):
    return {p["id"]: (p["u"], p["v"]) for p in draft.sketch["points"]}


def rectangle():
    draft = d.GeneralSketchDraft(json.dumps(BASE), journal_version=3)
    draft.execute(c.AddRectangle(c.PointSeed(0, 0), c.PointSeed(20, 10)))
    pts = [p["id"] for p in draft.sketch["points"]]
    for command in (c.AddRelation("fixed", (pts[0],), target=(0, 0)),
                    c.AddRelation("distance", (pts[0], pts[1]), value=20),
                    c.AddRelation("distance", (pts[1], pts[2]), value=10)):
        draft.execute(command)
    lines = [line["id"] for line in draft.sketch["lines"]]
    for i, radius in enumerate((1, 2, 3, 2)):
        draft.execute(c.CornerFillet((lines[i], lines[(i + 1) % 4]), radius, positions(draft)))
    doc = draft.candidate()
    doc["features"].append({"id": "pad", "kind": "extrude", "label": "Plate",
                            "params": {"length": 5}, "inputs": {"profile": draft.feature_id}})
    doc["active_feature"] = "pad"
    return doc, draft.feature_id


def begin(context, doc, feature_id):
    document_state._populate_document(context.scene, doc)
    owner = general_session.GeneralSession(context, feature_id)
    owner.start()
    context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    context.workspace[workspace.ROLE_KEY] = "SKETCH"
    owner.check(context)
    wait(owner)
    return owner


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    # A genuine underconstrained solve drifts from raw seeds; deletion must not
    # silently accept that new placement. H/V still leaves four free DoF but is safe.
    for axis_locked in (False, True):
        draft = d.GeneralSketchDraft(json.dumps(BASE), journal_version=3)
        corner, _, first = draft.execute(c.AddLine(c.PointSeed(0, 0), c.PointSeed(20, 0))).entity_ids
        _, second = draft.execute(c.AddLine(c.PointRef(corner), c.PointSeed(0, 20))).entity_ids
        if axis_locked:
            draft.execute(c.AddRelation("horizontal", (first,)))
            draft.execute(c.AddRelation("vertical", (second,)))
        draft.execute(c.CornerFillet((first, second), 2, positions(draft)))
        owner = begin(context, draft.candidate(), draft.feature_id)
        owner.draft.select((("arc", owner.commands.sketch["arcs"][0]["id"]),))
        owner.checkpoint()
        before = owner.commands.checkpoint_payload()
        saved = context.scene.mechanical_cad.sketch_draft_json
        op = dialog(context)
        assert operator.execute(op, context) == {"FINISHED"}
        assert owner.commands.checkpoint_payload() == before
        wait(owner, failed=not axis_locked)
        if axis_locked:
            assert owner.commands.sketch["arcs"] == []
        else:
            assert "Constrain the sketch placement first" in owner.error, owner.error
            assert owner.commands.checkpoint_payload() == before
            assert context.scene.mechanical_cad.sketch_draft_json == saved
        owner.discard()

    doc, feature_id = rectangle()
    # Downstream failure must leave the rounded source draft and Part intact.
    doc["features"][-1]["params"]["length"] = 0
    owner = begin(context, doc, feature_id)
    owner.draft.select((("arc", owner.commands.sketch["arcs"][1]["id"]),))
    owner.checkpoint()
    before = owner.commands.checkpoint_payload()
    canonical = context.scene.mechanical_cad.document_json
    op = dialog(context)
    assert operator.execute(op, context) == {"FINISHED"}
    wait(owner, failed=True)
    assert owner.commands.checkpoint_payload() == before
    assert context.scene.mechanical_cad.document_json == canonical
    owner.discard()

    doc, feature_id = rectangle()
    owner = begin(context, doc, feature_id)
    arc = owner.commands.sketch["arcs"][1]
    radius = next(r["id"] for r in owner.commands.sketch["constraints"]
                  if r["kind"] == "radius" and r["refs"] == [arc["id"]])
    owner.draft.place_annotation(radius, (4, 7), display="diameter")
    owner.draft.select((("arc", arc["id"]),))
    owner.checkpoint()
    before, annotations = owner.commands.sketch, owner.draft.annotations
    canonical = context.scene.mechanical_cad.document_json
    op = dialog(context)
    assert operator.poll(context)
    op.cancel(context)
    assert owner.commands.sketch == before
    assert operator.execute(op, context) == {"CANCELLED"}
    op = dialog(context)
    assert operator.execute(op, context) == {"FINISHED"}
    assert owner.commands.sketch == before
    wait(owner)
    after = owner.commands.sketch
    assert len(after["arcs"]) == 3 and owner.removal_attempt is None
    assert len(owner.commands._solution_evidence) == 2
    from mechanical_cad_blender.annotation_retirement import mark_retired
    retired_annotations = {**annotations, radius: mark_retired(annotations[radius])}
    assert owner.draft.annotations == retired_annotations
    assert next(s for s in owner.draft.status.annotations if s.identifier == radius).state == "retired"
    assert radius not in owner.draft.display_annotations
    assert context.scene.mechanical_cad.document_json == canonical
    assert operator.execute(op, context) == {"CANCELLED"}
    owner.local_history(context)
    wait(owner)
    assert owner.commands.sketch == before and owner.draft.annotations == annotations
    owner.local_history(context, redo=True)
    wait(owner)
    assert owner.commands.sketch == after and owner.draft.annotations == retired_annotations
    assert not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules)
    owner.suspend("Sharp-corner restoration verified")
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(os.environ["TMPDIR"]) / "remove-fillet-smoke.blend"))
unregister()
print("SKETCH_REMOVE_FILLET_SMOKE_OK", flush=True)
