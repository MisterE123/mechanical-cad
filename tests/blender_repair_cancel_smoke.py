"""Focused native/RNA Cancel vs Discard, not GUI or .blend I/O qualification.

Run source-loaded in isolated background Blender with MCAD_ROOT and MCAD_PYTHON.
Only dialog presentation is intercepted; invoke, properties, evidence, partial
Apply, Resume validation and explicit Discard use their real production paths.
"""

import copy
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    display,
    projection_repair_ui,
    register,
    registration,
    repair_intent,
    sketch_annotation_store,
    staged_edit,
    staged_edit_store,
    support_intent_ui,
    unregister,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402
from staged_edit_cases import feature, multiple_projection_case, support_case  # noqa: E402

checks = []
mode = "cancel"


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("REPAIR_CANCEL_CHECK=" + message, flush=True)


def snapshot():
    scene = bpy.context.scene
    return (
        scene.mechanical_cad.document_json,
        id(doc._RUNTIME.get(doc._scene_key(scene))),
        tuple((o.as_pointer(), o.data.as_pointer()) for o in display._owned_objects(scene)),
        scene.mechanical_cad.sketch_annotation_json,
    )


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *args, **kw: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


support = support_intent_ui.MCAD_OT_edit_sketch_support
projection = projection_repair_ui.MCAD_OT_replace_projection_reference
original_execute = {support: support.execute, projection: projection.execute}


def review(cls, self, context):
    assert isinstance(self.properties, bpy.types.OperatorProperties)
    assert cls.invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
    before = snapshot()
    pending = staged_edit.current(context)
    state = context.scene.mechanical_cad
    if cls is support:
        self.support_source = "slotted"
        self.support_face = "block/face/cap.end"
        self.policy = "PRESERVE_PLANE"
        self.orientation = "WORLD_AXES"
        fields = ("_review_evidence",)
    else:
        self.target = "reference"
        self.replacement = (
            str(
                next(
                    i
                    for i, row in enumerate(self._entries)
                    if row["row"] == {"source": "replacement_ring"}
                )
            )
            if pending
            else "0"
        )
        fields = ("_catalog_evidence", "_plane_evidence")
    if mode == "apply":
        return original_execute[cls](self, context)
    if mode == "stale":
        assert pending and pending.repairs
        assert bpy.ops.mcad.undo_proposal_repair(staged_token=pending.token) == {"FINISHED"}
        newer = staged_edit.current(context)
        assert newer is not pending and newer.token != self.staged_token
        try:
            self._review(context)
        except Exception as exc:
            assert "expired" in str(exc).lower(), str(exc)
        else:
            raise AssertionError("Stale review acquired newer proposal authority")
        pending = newer
    elif mode == "expired":
        # The unchanged lifecycle path retires ownership, not ordinary Cancel.
        staged_edit.cancel_all("Lifecycle retired the live proposal")
        pending = None
    expected = repair_intent.encode(pending) if pending is not None else None
    saved = state.repair_intent_json
    diagnostic = state.last_action_error
    self.cancel(context)
    self.cancel(context)
    check(
        all(getattr(self, field, None) is None for field in fields),
        f"{cls.bl_label}: Cancel releases dialog evidence once",
    )
    check(
        staged_edit.current(context) is pending,
        f"{cls.bl_label}: {mode} retains exact live owner or remains expired",
    )
    check(
        (repair_intent.encode(pending) if pending else None) == expected,
        f"{cls.bl_label}: {mode} preserves token history candidate and annotation intent",
    )
    check(
        state.repair_intent_json == saved and state.last_action_error == diagnostic,
        f"{cls.bl_label}: {mode} leaves checkpoint and diagnostics untouched",
    )
    check(
        snapshot() == before,
        f"{cls.bl_label}: {mode} leaves accepted JSON runtime meshes and annotations unchanged",
    )
    return {"CANCELLED"}


support.execute = lambda self, context: review(support, self, context)
projection.execute = lambda self, context: review(projection, self, context)
register()
assert bpy.app.background

for kind in ("projection", "support"):
    if kind == "projection":
        base, proposed = multiple_projection_case()
        upstream, first, second = "source", "target", "target_two"
        operator = bpy.ops.mcad.replace_projection_reference
    else:
        base, proposed = support_case()
        for document in (base, proposed):
            attached = copy.deepcopy(feature(document, "attached"))
            attached["id"] = "attached_two"
            attached["sketch"]["id"] = "second_attached_geometry"
            document["features"].append(attached)
        upstream, first, second = "slot_tool", "attached", "attached_two"
        operator = bpy.ops.mcad.edit_sketch_support
    assert doc._commit_candidate(bpy.context, base)
    accepted = snapshot()
    mode = "cancel"
    assert operator("EXEC_DEFAULT", feature_id=first) == {"CANCELLED"}
    check(
        snapshot() == accepted and staged_edit.current(bpy.context) is None,
        f"{kind}: ordinary accepted-model Cancel unchanged",
    )
    try:
        doc._commit_candidate(bpy.context, proposed, stage_feature_id=upstream)
    except Exception:
        pass
    original = staged_edit.current(bpy.context)
    assert original is not None and original.document == proposed
    if kind == "projection":
        # Same validated ownership seam as Finish; actual Finish is covered by
        # blender_sketch_staged_edit_smoke.py, not faked here as viewport evidence.
        annotation = sketch_annotation_store.replace_annotations(
            "",
            base["id"],
            "source",
            {
                "size": {
                    "kind": "radius",
                    "refs": ["replacement_ring"],
                    "display": "radius",
                    "offset": [2, 3],
                }
            },
        )
        original = replace(original, annotation_before="", annotation_after=annotation)
        staged_edit_store._PENDING[bpy.context.scene.as_pointer()] = original
    mode = "apply"
    assert operator("EXEC_DEFAULT", feature_id=first, staged_token=original.token) == {"CANCELLED"}
    partial = staged_edit.current(bpy.context)
    check(
        partial is not None and partial.token != original.token and len(partial.repairs) == 1,
        f"{kind}: partial Apply CANCELLED means kept progress, not user cancellation",
    )
    check(snapshot() == accepted, f"{kind}: partial Apply adds no accepted-model mutation")
    registration._before_blend_save(None)
    registration._failed_blend_save(None)
    checkpoint = bpy.context.scene.mechanical_cad.repair_intent_json
    assert checkpoint
    mode = "cancel"
    assert operator("EXEC_DEFAULT", feature_id=second, staged_token=partial.token) == {"CANCELLED"}
    check(
        staged_edit.current(bpy.context) is partial,
        f"{kind}: second review Cancel retains accumulated partial repair",
    )
    mode = "stale"
    assert operator("EXEC_DEFAULT", feature_id=second, staged_token=partial.token) == {"CANCELLED"}
    newer = staged_edit.current(bpy.context)
    check(
        newer.token != partial.token and not newer.repairs,
        f"{kind}: stale Cancel cannot clear newer proposal",
    )
    mode = "apply"
    assert operator("EXEC_DEFAULT", feature_id=first, staged_token=newer.token) == {"CANCELLED"}
    partial = staged_edit.current(bpy.context)
    expected = repair_intent.encode(partial)
    registration._before_blend_save(None)
    registration._after_blend_save(None)
    check(
        staged_edit.current(bpy.context) is None,
        f"{kind}: successful Save hook still suspends live authority",
    )
    saved = bpy.context.scene.mechanical_cad.repair_intent_json
    assert saved == expected
    assert bpy.ops.mcad.resume_saved_repair("EXEC_DEFAULT") == {"FINISHED"}
    resumed = staged_edit.current(bpy.context)
    check(
        resumed.token != partial.token and repair_intent.encode(resumed) == expected,
        f"{kind}: Resume creates fresh owner with exact history and intent",
    )
    mode = "cancel"
    assert operator("EXEC_DEFAULT", feature_id=second, staged_token=resumed.token) == {"CANCELLED"}
    check(
        staged_edit.current(bpy.context) is resumed,
        f"{kind}: Cancel after Resume retains exact reconstructed history",
    )
    assert bpy.ops.mcad.discard_proposed_edit(staged_token=resumed.token) == {"FINISHED"}
    check(
        staged_edit.current(bpy.context) is None
        and not bpy.context.scene.mechanical_cad.repair_intent_json,
        f"{kind}: explicit Discard clears live proposal and owned checkpoint",
    )
    check(snapshot() == accepted, f"{kind}: explicit Discard does not change accepted model")
    # Recreate one proposal to check stale callbacks never reinstall expired work.
    try:
        doc._commit_candidate(bpy.context, proposed, stage_feature_id=upstream)
    except Exception:
        pass
    pending = staged_edit.current(bpy.context)
    assert pending
    mode = "expired"
    assert operator("EXEC_DEFAULT", feature_id=first, staged_token=pending.token) == {"CANCELLED"}
    check(
        staged_edit.current(bpy.context) is None,
        f"{kind}: Cancel cannot revive lifecycle-expired work",
    )

unregister()
print("MCAD_REPAIR_CANCEL_OK=" + json.dumps({"checks": len(checks)}), flush=True)
