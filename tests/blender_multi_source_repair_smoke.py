"""Native proposal revisions and automatic full-model history replay, no GUI claims."""

import json
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    display,
    execution_lease,
    history_rebuild,
    projection_repair_ui,
    register,
    registration,
    repair_resume,
    sketch_pending,
    staged_edit,
    unregister,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402
from mechanical_cad_blender.staged_edit_ui import validate_review  # noqa: E402
from staged_edit_cases import feature  # noqa: E402

checks = []
selected = "reference"
source_name = "replacement_ring"


def check(value, message):
    assert value, message
    checks.append(message)
    print("MULTI_REPAIR_CHECK=" + message, flush=True)


def snapshot():
    return (
        bpy.context.scene.mechanical_cad.document_json,
        id(doc._RUNTIME.get(doc._scene_key(bpy.context.scene))),
        tuple(
            (o.as_pointer(), o.data.as_pointer()) for o in display._owned_objects(bpy.context.scene)
        ),
        bpy.context.scene.mechanical_cad.sketch_annotation_json,
    )


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})

    def __getattr__(self, name):
        return getattr(bpy.context, name)


execute = projection_repair_ui.MCAD_OT_replace_projection_reference.execute


def repair(self, context):
    assert projection_repair_ui.MCAD_OT_replace_projection_reference.invoke(
        self, DialogContext(), None
    ) == {"RUNNING_MODAL"}
    self.target = selected
    self.replacement = str(
        next(i for i, e in enumerate(self._entries) if e["row"] == {"source": source_name})
    )
    return execute(self, context)


projection_repair_ui.MCAD_OT_replace_projection_reference.execute = repair
register()
assert bpy.app.background
bpy.context.preferences.edit.use_global_undo = True
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")


def reject(fn):
    try:
        fn()
    except Exception:
        return
    raise AssertionError("Invalid repair unexpectedly accepted")


def drain():
    deadline = time.monotonic() + 40
    while history_rebuild._PENDING is not None or execution_lease.is_busy():
        assert time.monotonic() < deadline
        history_rebuild._tick()
        sketch_pending.reap()
        time.sleep(0.02)
    if bpy.app.timers.is_registered(history_rebuild._tick):
        bpy.app.timers.unregister(history_rebuild._tick)


from multi_source_cases import multiple_source_repairs  # noqa: E402

for fixture in (multiple_source_repairs,):
    selected, source_name = "reference", "replacement_ring"
    with bpy.context.temp_override(
        window=bpy.context.window,
        area=next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D"),
        region=next(
            r
            for r in next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D").regions
            if r.type == "WINDOW"
        ),
    ):
        base, proposed = fixture()
        assert doc._commit_candidate(bpy.context, base)
        accepted = snapshot()
        bpy.ops.ed.undo_push(message="Accepted before multiple repairs")
        reject(
            lambda proposed=proposed: doc._commit_candidate(
                bpy.context, proposed, stage_feature_id="source"
            )
        )
        original = staged_edit.current(bpy.context)
        check(
            original is not None and original.document == proposed,
            "Original upstream edit retained",
        )
        old_token = original.token
        check(snapshot() == accepted, "Retaining proposal does not change accepted data or display")
        # Unrelated authored formula is not a reference repair.
        bad = original.document
        feature(bad, "target")["sketch"]["constraints"][-1]["value"] = "r + 100"
        reject(lambda old_token=old_token, bad=bad: staged_edit.accept(bpy.context, old_token, bad))
        check(
            staged_edit.current(bpy.context) is original,
            "Unrelated/invalid repair leaves exact proposal",
        )
        invalid = original.document
        feature(invalid, "target")["projections"][0]["source"] = "missing_native_source"
        reject(
            lambda old_token=old_token, invalid=invalid: staged_edit.accept(
                bpy.context, old_token, invalid
            )
        )
        check(
            staged_edit.current(bpy.context) is original and snapshot() == accepted,
            "Fresh native invalid selected-binding proof cannot retain progress",
        )

        result = bpy.ops.mcad.replace_projection_reference(
            "EXEC_DEFAULT", feature_id="target", staged_token=old_token
        )
        check(result == {"CANCELLED"}, "Partial repair adds no canonical Blender Undo step")
        partial = staged_edit.current(bpy.context)
        check(
            partial is not None and len(partial.repairs) == 1 and partial.token != old_token,
            "Partial repair kept with new revision token",
        )
        check(
            snapshot() == accepted,
            "Partial repair leaves accepted JSON runtime meshes and annotations exact",
        )
        check(
            feature(partial.document, "source") == feature(proposed, "source"),
            "Original source geometry formulas and IDs retained",
        )
        reject(
            lambda old_token=old_token, original=original: validate_review(
                bpy.context, old_token, original.base_json, original.document
            )
        )
        reject(
            lambda old_token=old_token, partial=partial: staged_edit.accept(
                bpy.context, old_token, partial.document
            )
        )
        check(
            staged_edit.current(bpy.context) is partial,
            "Stale dialogs cannot edit revised proposal",
        )
        # Saved intent must retain source-qualified partial history, not old
        # result receipts, and reconstruct it through fresh multi-source replay.
        prior_document = partial.document
        prior_token = partial.token
        registration._before_blend_save(None)
        check(
            bool(bpy.context.scene.mechanical_cad.repair_intent_json),
            "Multi-source intent checkpointed",
        )
        registration._after_blend_save(None)
        check(staged_edit.current(bpy.context) is None, "Multi-source live owner suspended")
        resume_owner = repair_resume.ResumeOwner(bpy.context)
        resume_deadline = time.monotonic() + 60
        while not resume_owner.closed:
            assert time.monotonic() < resume_deadline
            resume_owner.tick(bpy.context)
            sketch_pending.reap()
            time.sleep(0.02)
        check(resume_owner.success, "Guarded modal multi-source Resume completes")
        partial = staged_edit.current(bpy.context)
        check(
            partial.document == prior_document
            and len(partial.repairs) == 1
            and partial.token != prior_token
            and snapshot() == accepted,
            "Fresh multi-source Resume preserves exact candidate, history and accepted display",
        )
        assert bpy.ops.mcad.undo_proposal_repair(staged_token=partial.token) == {"FINISHED"}
        undone = staged_edit.current(bpy.context)
        check(
            undone.document == original.document
            and not undone.repairs
            and undone.token not in {old_token, partial.token},
            "Explicit proposal Undo restores original candidate with fresh token",
        )
        check(snapshot() == accepted, "Proposal Undo does not touch canonical history or display")
        assert bpy.ops.mcad.replace_projection_reference(
            "EXEC_DEFAULT", feature_id="target", staged_token=undone.token
        ) == {"CANCELLED"}
        partial = staged_edit.current(bpy.context)
        selected, source_name, target = "reference3", "replacement_ring2", "target"
        assert bpy.ops.mcad.replace_projection_reference(
            "EXEC_DEFAULT", feature_id=target, staged_token=partial.token
        ) == {"FINISHED"}
        check(
            staged_edit.current(bpy.context) is None,
            "Second repair accepts complete Part atomically",
        )
        saved = bpy.context.scene.mechanical_cad.document_json
        check(
            feature(json.loads(saved), "source") == feature(proposed, "source"),
            "Acceptance preserves upstream formula and authored identities",
        )
        check(doc.part_is_current(bpy.context), "Accepted complete native replay is current")
        bpy.ops.ed.undo_push(message="Complete multiple reference repair")
    # Blender background needs explicit checkpoints, not application Undo pushes.
    assert bpy.ops.ed.undo() == {"FINISHED"}
    check(
        history_rebuild._PENDING is not None, "Whole-model Undo schedules automatic native rebuild"
    )
    drain()
    check(
        bpy.context.scene.mechanical_cad.document_json == accepted[0]
        and doc.part_is_current(bpy.context),
        "One Undo restores accepted base and fresh geometry",
    )
    assert bpy.ops.ed.redo() == {"FINISHED"}
    check(history_rebuild._PENDING is not None, "Redo schedules automatic native rebuild")
    drain()
    check(
        bpy.context.scene.mechanical_cad.document_json == saved
        and doc.part_is_current(bpy.context),
        "Redo restores all proposal repairs with fresh geometry",
    )
    volume = doc.current_part_result(bpy.context)["features"][-1]["stats"]["volume"]
    check(abs(volume - 80 * math.pi) < 1e-7, "Repaired native solid has exact expected volume")

unregister()
print("MCAD_MULTI_SOURCE_REPAIR_OK=" + json.dumps({"checks": len(checks)}), flush=True)
