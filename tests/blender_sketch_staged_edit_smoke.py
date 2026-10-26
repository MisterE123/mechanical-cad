"""Registered Edit Sketch -> Finish -> explicit repair, real sidecar evidence.

Native background RNA dispatch is not GUI usability/installer qualification.
Only workspace scheduling and popup presentation are intercepted.
"""

import copy
import json
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    display,
    general_session,
    general_viewport,
    projection_repair_ui,
    register,
    sketch_session,
    staged_edit,
    unregister,
    workspace,
)
from mechanical_cad_blender import (  # noqa: E402
    document_state as doc,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddCircle,
    AddRelation,
    DeleteBatch,
    PointRef,
    PointSeed,
    SetConstruction,
)
from staged_edit_cases import feature, projection_case  # noqa: E402

checks = []
editor = None
mode = "accept"


def check(value, message):
    assert value, message
    checks.append(message)
    print("SKETCH_STAGE_CHECK=" + message, flush=True)


def accepted_snapshot():
    return (
        bpy.context.scene.mechanical_cad.document_json,
        id(doc._RUNTIME.get(doc._scene_key(bpy.context.scene))),
        tuple(
            (o.as_pointer(), o.data.as_pointer()) for o in display._owned_objects(bpy.context.scene)
        ),
    )


original_invoke = general_viewport.MCAD_OT_general_sketch.invoke


def invoke(self, context, event):
    global editor
    check(isinstance(self, bpy.types.Operator), "Actual registered sketch RNA operator invoked")
    result = original_invoke(self, context, event)
    editor = self
    return result


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *args, **kwargs: {"RUNNING_MODAL"})

    def __getattr__(self, name):
        return getattr(bpy.context, name)


repair_execute = projection_repair_ui.MCAD_OT_replace_projection_reference.execute


def repair(self, context):
    check(isinstance(self.properties, bpy.types.OperatorProperties), "Actual repair RNA properties")
    assert projection_repair_ui.MCAD_OT_replace_projection_reference.invoke(
        self, DialogContext(), None
    ) == {"RUNNING_MODAL"}
    if mode == "cancel":
        self.cancel(context)
        return {"CANCELLED"}
    return repair_execute(self, context)


general_viewport.MCAD_OT_general_sketch.invoke = invoke
projection_repair_ui.MCAD_OT_replace_projection_reference.execute = repair
register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")


def wait(owner):
    deadline = time.monotonic() + 40
    while owner.pending is not None and time.monotonic() < deadline:
        general_viewport.MCAD_OT_general_sketch.modal(
            editor, bpy.context, SimpleNamespace(type="TIMER")
        )
        time.sleep(0.01)
    check(owner.pending is None, "Native async operation completed")


def open_edit(base):
    staged_edit.cancel_all()
    assert doc._commit_candidate(bpy.context, copy.deepcopy(base))
    bpy.context.scene.mechanical_cad.feature_index = 0
    assert bpy.ops.mcad.edit_viewport_sketch() == {"FINISHED"}
    owner = sketch_session.active_session(bpy.context)
    check(
        owner is not None and owner.commands.is_edit, "Edit Sketch acquires existing sketch owner"
    )
    wait(owner)
    assert owner.can_finish, owner.error
    return owner


def revise(owner):
    plan = owner.commands.preview_delete((("circle", "ring"),))
    owner.execute(bpy.context, DeleteBatch(plan))
    wait(owner)
    owner.execute(bpy.context, AddCircle(PointRef("p"), 4))
    wait(owner)
    circle = owner.commands.sketch["circles"][0]["id"]
    owner.execute(bpy.context, AddRelation("radius", (circle,), value="r + 1"))
    wait(owner)
    constraint = owner.commands.sketch["constraints"][-1]["id"]
    owner.draft.place_annotation(constraint, (37.25, -18.5))
    owner.checkpoint()
    owner.check(bpy.context)
    wait(owner)
    check(owner.can_finish, "Complete revised sketch has successful native solve")
    return owner.commands.candidate(), circle


def finish(owner):
    assert bpy.ops.mcad.finish_sketch() == {"FINISHED"}
    general_viewport.MCAD_OT_general_sketch.modal(
        editor, bpy.context, SimpleNamespace(type="TIMER")
    )
    wait(owner)


with (
    bpy.context.temp_override(window=window, area=area, region=region),
    patch.object(workspace, "get_role", return_value="SKETCH"),
    patch.object(
        workspace,
        "request_workspace",
        side_effect=lambda context, role, on_ready=None: on_ready(context) if on_ready else None,
    ),
):
    base, _ = projection_case()
    for mode in ("cancel", "accept"):
        owner = open_edit(base)
        before = accepted_snapshot()
        annotations = bpy.context.scene.mechanical_cad.sketch_annotation_json
        candidate, circle = revise(owner)
        finish(owner)
        proposal = staged_edit.current(bpy.context)
        check(proposal is not None, "Actual Finish retains failed downstream reference candidate")
        check(
            proposal.document == candidate,
            "Proposal preserves every candidate value including formula text",
        )
        check(
            not owner.finished and owner.retained_for_repair,
            "Retained proposal is distinct from successful Finish",
        )
        check(
            not owner.alive and sketch_session.active_session() is None,
            "Active draft released after handoff",
        )
        check(
            not bpy.context.scene.mechanical_cad.sketch_draft_json, "No duplicate saved draft owner"
        )
        check(
            accepted_snapshot() == before,
            "Failed Finish preserves accepted JSON, native authority and mesh datablocks",
        )
        check(
            bpy.context.scene.mechanical_cad.sketch_annotation_json == annotations,
            "Proposed annotation layout is unapplied",
        )
        check("37.25" in proposal.annotation_after, "Proposal owns dimension-label intent")
        check(
            "Unapplied sketch edit" in bpy.context.scene.mechanical_cad.last_action_error,
            "Finish explicitly reports unapplied status",
        )
        token = proposal.token
        for operation in (
            lambda: bpy.ops.mcad.edit_viewport_sketch(),
            lambda: bpy.ops.mcad.general_sketch("EXEC_DEFAULT"),
        ):
            try:
                outcome = operation()
            except RuntimeError as exc:
                assert "retained" in str(exc).lower(), str(exc)
            else:
                assert outcome == {"CANCELLED"}
            check(
                staged_edit.current(bpy.context) is proposal,
                "Another Sketch entry cannot replace the proposal",
            )
            check(
                sketch_session.active_session() is None
                and not bpy.context.scene.mechanical_cad.sketch_draft_json,
                "Another Sketch entry creates no competing draft owner",
            )
        if mode == "accept":
            repaired = proposal.document
            feature(repaired, "target")["projections"][0]["source"] = circle
            apply_result = doc._apply_result

            def fail_after_layout(*args, _apply=apply_result, **kwargs):
                _apply(*args, **kwargs)
                raise RuntimeError("Injected after annotation publication")

            with patch.object(doc, "_apply_result", side_effect=fail_after_layout):
                try:
                    staged_edit.accept(bpy.context, token, repaired)
                except RuntimeError as exc:
                    assert "Injected" in str(exc)
                else:
                    raise AssertionError("Expected publication rollback")
            check(
                staged_edit.current(bpy.context) is proposal,
                "Failed publication keeps exact proposal for retry",
            )
            check(
                accepted_snapshot() == before,
                "Failed publication restores accepted JSON/runtime/meshes",
            )
            check(
                bpy.context.scene.mechanical_cad.sketch_annotation_json == annotations,
                "Failed publication rolls annotation layout back atomically",
            )
        result = bpy.ops.mcad.replace_projection_reference(
            "EXEC_DEFAULT", feature_id="target", staged_token=token
        )
        assert result == ({"FINISHED"} if mode == "accept" else {"CANCELLED"})
        check(
            staged_edit.current(bpy.context) is (proposal if mode == "cancel" else None),
            "Cancel retains exact proposal; complete repair retires it",
        )
        if mode == "cancel":
            check(
                accepted_snapshot() == before,
                "Cancel retains proposed sketch edits, accepted Part intact",
            )
            check(
                bpy.context.scene.mechanical_cad.sketch_annotation_json == annotations,
                "Cancel does not publish proposed annotations",
            )
            check("37.25" in proposal.annotation_after, "Cancel retains annotation intent")
            assert bpy.ops.mcad.discard_proposed_edit(staged_token=proposal.token) == {"FINISHED"}
            check(
                staged_edit.current(bpy.context) is None, "Explicit Discard abandons sketch edits"
            )
        else:
            saved = json.loads(bpy.context.scene.mechanical_cad.document_json)
            check(
                feature(saved, "source") == feature(candidate, "source"),
                "Repair preserves all edited source geometry and formulas",
            )
            check(
                feature(saved, "target")["projections"][0]["source"] == circle,
                "Explicit repair targets newly authored circle identity",
            )
            check(
                bpy.context.scene.mechanical_cad.sketch_annotation_json
                == proposal.annotation_after,
                "Complete successful repair publishes retained annotations atomically",
            )
            check(
                abs(
                    doc.current_part_result(bpy.context)["features"][-1]["stats"]["volume"]
                    - 80 * math.pi
                )
                < 1e-7,
                "Repaired native Part has exact proposed radius volume",
            )

    owner = open_edit(base)
    candidate, _ = revise(owner)
    draft_before = bpy.context.scene.mechanical_cad.sketch_draft_json
    before = accepted_snapshot()
    with patch.object(
        general_session,
        "_discard_stored",
        side_effect=RuntimeError("Injected draft release failure"),
    ):
        finish(owner)
    check(
        staged_edit.current(bpy.context) is None,
        "Failed draft release rolls back proposal ownership",
    )
    check(
        owner.alive and owner.commands.candidate() == candidate,
        "Failed handoff retains complete active editable draft",
    )
    check(
        bpy.context.scene.mechanical_cad.sketch_draft_json == draft_before,
        "Failed handoff preserves exact saved draft",
    )
    check(accepted_snapshot() == before, "Failed handoff preserves accepted model")
    owner.discard()

    owner = open_edit(base)
    owner.commands.invalidate_solution()
    check(not bpy.ops.mcad.finish_sketch.poll(), "Unsolved draft cannot enter registered Finish")
    check(staged_edit.current(bpy.context) is None, "Unsolved draft never staged")
    owner.check(bpy.context)
    wait(owner)
    owner.draft.begin_circle(PointSeed(0, 0), 1)
    check(
        not bpy.ops.mcad.finish_sketch.poll(), "Unfinished geometry cannot enter registered Finish"
    )
    owner.discard()

    # A simultaneous non-reference downstream failure is not staged.
    extra_consumer = copy.deepcopy(base)
    extra_consumer["features"].append(
        {
            "id": "source_solid",
            "kind": "extrude",
            "label": "Source consumer",
            "inputs": {"profile": "source"},
            "params": {"length": 2},
        }
    )
    owner = open_edit(extra_consumer)
    candidate, circle = revise(owner)
    owner.execute(bpy.context, SetConstruction((("circle", circle),), True))
    wait(owner)
    check(owner.can_finish, "Construction-only source sketch solves successfully")
    before = accepted_snapshot()
    finish(owner)
    check(
        staged_edit.current(bpy.context) is None,
        "Non-reference downstream extrusion failure is not staged",
    )
    check(
        owner.alive and bpy.context.scene.mechanical_cad.sketch_draft_json,
        "Non-reference downstream failure retains editable draft",
    )
    check(
        accepted_snapshot() == before, "Non-reference downstream rejection preserves accepted Part"
    )
    owner.discard()

    # Ordinary full-success Finish remains the original canonical path.
    owner = open_edit(base)
    finish(owner)
    check(
        owner.finished and not owner.retained_for_repair,
        "Successful unchanged Finish still publishes normally",
    )
    check(
        staged_edit.current(bpy.context) is None and doc.part_is_current(bpy.context),
        "Successful Finish has current Part, no proposal",
    )

unregister()
print("MCAD_SKETCH_STAGED_EDIT_RESULT=" + json.dumps({"ok": True, "checks": checks}), flush=True)
