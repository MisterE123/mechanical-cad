"""Integrated sketch repair and automatic history replay, real sidecar evidence.

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
    execution_lease,
    general_viewport,
    history_rebuild,
    projection_repair_ui,
    register,
    sketch_pending,
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
    bpy.ops.ed.undo_push(message="Accepted sketch before repair")
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


def drain_history():
    deadline = time.monotonic() + 40
    while history_rebuild._PENDING is not None or execution_lease.is_busy():
        assert time.monotonic() < deadline, "Integrated history replay timed out"
        history_rebuild._tick()
        sketch_pending.reap()
        time.sleep(0.02)
    if bpy.app.timers.is_registered(history_rebuild._tick):
        bpy.app.timers.unregister(history_rebuild._tick)


def assert_restored(expected_json, expected_annotations, volume):
    state = bpy.context.scene.mechanical_cad
    check(state.document_json == expected_json, "History preserves exact canonical JSON")
    check(
        state.sketch_annotation_json == expected_annotations,
        "History preserves exact annotation intent",
    )
    check(
        not state.sketch_draft_json and sketch_session.active_session() is None,
        "History has no competing saved or active sketch draft",
    )
    check(staged_edit.current(bpy.context) is None, "History has no retained proposal")
    check(
        state.status == "READY" and doc.part_is_current(bpy.context),
        "History has fresh current geometry",
    )
    check(
        abs(doc.current_part_result(bpy.context)["features"][-1]["stats"]["volume"] - volume)
        < 1e-7,
        "History freshly replays the expected old or repaired native solid",
    )
    check(
        any(not obj.hide_get() for obj in display._owned_objects(bpy.context.scene)),
        "History fresh display is visible",
    )


assert bpy.app.background
bpy.context.preferences.edit.use_global_undo = True
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
    owner = open_edit(base)
    accepted_json = bpy.context.scene.mechanical_cad.document_json
    accepted_annotations = bpy.context.scene.mechanical_cad.sketch_annotation_json
    candidate, circle = revise(owner)
    finish(owner)
    proposal = staged_edit.current(bpy.context)
    check(
        proposal is not None and proposal.document == candidate,
        "Failed Finish retains exact edited sketch",
    )
    check(
        not owner.alive and not owner.finished and owner.retained_for_repair,
        "Failed Finish transfers ownership without claiming success",
    )
    check(
        bpy.context.scene.mechanical_cad.document_json == accepted_json,
        "Proposal leaves accepted canonical data unchanged",
    )
    check(
        bpy.context.scene.mechanical_cad.sketch_annotation_json == accepted_annotations,
        "Proposal leaves accepted annotations unchanged",
    )
    result = bpy.ops.mcad.replace_projection_reference(
        "EXEC_DEFAULT", feature_id="target", staged_token=proposal.token
    )
    check(
        result == {"FINISHED"}, "Registered repair accepts proposed sketch and reference atomically"
    )
    repaired_json = bpy.context.scene.mechanical_cad.document_json
    repaired_annotations = bpy.context.scene.mechanical_cad.sketch_annotation_json
    check(
        repaired_annotations == proposal.annotation_after and "37.25" in repaired_annotations,
        "Repair publishes proposed annotation position",
    )
    saved = json.loads(repaired_json)
    check(
        feature(saved, "source") == feature(candidate, "source"),
        "Repair preserves source formulas and identities",
    )
    check(
        feature(saved, "target")["projections"][0]["source"] == circle,
        "Repair references the new authored circle",
    )
    # Native background Blender requires explicit history checkpoints; neither
    # helper nor auto-replay adds any checkpoint between this pair.
    bpy.ops.ed.undo_push(message="Accepted sketch with explicit reference repair")

# Do not retain RNA context overrides across Undo, which destroys those handles.
for _ in range(2):
    check(bpy.ops.ed.undo() == {"FINISHED"}, "One Undo restores entire pre-edit transaction")
    check(history_rebuild._PENDING is not None, "Undo schedules automatic guarded replay")
    drain_history()
    assert_restored(accepted_json, accepted_annotations, 45 * math.pi)
    check(bpy.ops.ed.redo() == {"FINISHED"}, "Redo remains available with no replay Undo step")
    check(history_rebuild._PENDING is not None, "Redo schedules automatic guarded replay")
    drain_history()
    assert_restored(repaired_json, repaired_annotations, 80 * math.pi)
check(
    not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules),
    "No native OCP inside Blender",
)
unregister()
print("MCAD_HISTORY_SKETCH_INTEGRATION_OK=" + json.dumps({"checks": len(checks)}), flush=True)
