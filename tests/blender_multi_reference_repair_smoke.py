"""Native proposal revisions and automatic full-model history replay, no GUI claims."""

import copy
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
    sketch_pending,
    staged_edit,
    support_intent_ui,
    unregister,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402
from mechanical_cad_blender.staged_edit_ui import validate_review  # noqa: E402
from staged_edit_cases import (  # noqa: E402
    coupled_projection_case,
    feature,
    multiple_projection_case,
    same_sketch_projection_case,
    support_case,
)

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
support_execute = support_intent_ui.MCAD_OT_edit_sketch_support.execute


def repair_support(self, context):
    assert support_intent_ui.MCAD_OT_edit_sketch_support.invoke(self, DialogContext(), None) == {
        "RUNNING_MODAL"
    }
    self.support_source = "slotted"
    self.support_face = "block/face/cap.end"
    self.policy = "PRESERVE_PLANE"
    self.orientation = "WORLD_AXES"
    return support_execute(self, context)


support_intent_ui.MCAD_OT_edit_sketch_support.execute = repair_support
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


for fixture in (multiple_projection_case, same_sketch_projection_case, coupled_projection_case):
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
        if fixture is not multiple_projection_case:
            selected, source_name, target = "reference2", "replacement_ring2", "target"
        else:
            target = "target_two"
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

# Both chosen references can exist while their combined authored relation fails.
# Do not accept or advance the proposal when the final full solve is inconsistent.
base, proposed = coupled_projection_case()
feature(proposed, "source")["sketch"]["constraints"][-1]["value"] = "r + 2"
assert doc._commit_candidate(bpy.context, base)
accepted = snapshot()
reject(lambda: doc._commit_candidate(bpy.context, proposed, stage_feature_id="source"))
proposal = staged_edit.current(bpy.context)
selected, source_name = "reference", "replacement_ring"
assert bpy.ops.mcad.replace_projection_reference(
    "EXEC_DEFAULT", feature_id="target", staged_token=proposal.token
) == {"CANCELLED"}
partial = staged_edit.current(bpy.context)
check(
    partial is not None and len(partial.repairs) == 1,
    "Coupled first binding can be proven independently of stale drivers",
)
selected, source_name = "reference2", "replacement_ring2"
reject(
    lambda: bpy.ops.mcad.replace_projection_reference(
        "EXEC_DEFAULT", feature_id="target", staged_token=partial.token
    )
)
check(
    staged_edit.current(bpy.context) is partial,
    "Resolved but inconsistent combined constraints preserve prior proposal revision",
)
check(snapshot() == accepted, "Inconsistent final repair cannot publish canonical model or display")
assert bpy.ops.mcad.undo_proposal_repair(staged_token=partial.token) == {"FINISHED"}
check(
    staged_edit.current(bpy.context).document == proposed,
    "Explicit correction remains available after inconsistent final repair",
)
staged_edit.discard(bpy.context)

base, proposed = support_case()
for document in (base, proposed):
    attached = copy.deepcopy(feature(document, "attached"))
    attached["id"] = "attached_two"
    attached["sketch"]["id"] = "second_attached_geometry"
    document["features"].append(attached)
assert doc._commit_candidate(bpy.context, base)
accepted = snapshot()
reject(lambda: doc._commit_candidate(bpy.context, proposed, stage_feature_id="slot_tool"))
proposal = staged_edit.current(bpy.context)
assert bpy.ops.mcad.edit_sketch_support(
    "EXEC_DEFAULT", feature_id="attached", staged_token=proposal.token
) == {"CANCELLED"}
partial = staged_edit.current(bpy.context)
check(
    partial is not None and len(partial.repairs) == 1 and snapshot() == accepted,
    "Support repair also retains progress without accepted-model mutation",
)
assert bpy.ops.mcad.edit_sketch_support(
    "EXEC_DEFAULT", feature_id="attached_two", staged_token=partial.token
) == {"FINISHED"}
check(
    staged_edit.current(bpy.context) is None and doc.part_is_current(bpy.context),
    "Second support repair accepts the complete Part with native geometry",
)

unregister()
print("MCAD_MULTI_REFERENCE_REPAIR_OK=" + json.dumps({"checks": len(checks)}), flush=True)
