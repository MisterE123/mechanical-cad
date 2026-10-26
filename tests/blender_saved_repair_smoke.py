"""Native saved-intent ownership, exact replay and separate-process reopen.

Run with MCAD_REPAIR_BLEND=<absolute temporary .blend path>; then repeat with
MCAD_REPAIR_REOPEN=1. No UI/native-geometry authority is loaded from saved intent.
"""

import copy
import json
import math
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    backend_runtime,
    display,
    execution_lease,
    geometry_operations,
    history_rebuild,
    projection_repair_ui,
    register,
    registration,
    repair_intent,
    sketch_annotation_store,
    sketch_pending,
    sketch_session,
    staged_edit,
    staged_edit_store,
    staged_edit_ui,
    unregister,
    workspace,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402
from staged_edit_cases import multiple_projection_case, same_sketch_projection_case  # noqa: E402

BLEND = Path(os.environ["MCAD_REPAIR_BLEND"])
EXPECTED = BLEND.with_suffix(".expected.json")
INVALID = BLEND.with_suffix(".unsupported.blend")
checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("SAVED_REPAIR_CHECK=" + message, flush=True)


def reject(callback):
    try:
        callback()
    except Exception:
        return
    raise AssertionError("Expected refusal")


def snapshot():
    scene = bpy.context.scene
    return (
        scene.mechanical_cad.document_json,
        id(doc._RUNTIME.get(doc._scene_key(scene))),
        tuple(
            (o.as_pointer(), o.data.as_pointer(), o.hide_viewport, o.hide_get())
            for o in display._owned_objects(scene)
        ),
        scene.mechanical_cad.sketch_annotation_json,
    )


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *args, **kw: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


execute_repair = projection_repair_ui.MCAD_OT_replace_projection_reference.execute


def repair_operator(self, context):
    assert projection_repair_ui.MCAD_OT_replace_projection_reference.invoke(
        self, DialogContext(), None
    ) == {"RUNNING_MODAL"}
    self.target = "reference"
    self.replacement = str(
        next(i for i, e in enumerate(self._entries) if e["row"] == {"source": "replacement_ring"})
    )
    return execute_repair(self, context)


projection_repair_ui.MCAD_OT_replace_projection_reference.execute = repair_operator


def repair(feature_id, expected):
    proposal = staged_edit.current(bpy.context)
    assert (
        bpy.ops.mcad.replace_projection_reference(
            "EXEC_DEFAULT", feature_id=feature_id, staged_token=proposal.token
        )
        == expected
    )


def drain():
    deadline = time.monotonic() + 60
    while history_rebuild._PENDING is not None or execution_lease.is_busy():
        assert time.monotonic() < deadline
        history_rebuild._tick()
        sketch_pending.reap()
        time.sleep(0.01)
    if bpy.app.timers.is_registered(history_rebuild._tick):
        bpy.app.timers.unregister(history_rebuild._tick)


register()
assert bpy.app.background
bpy.context.preferences.edit.use_global_undo = True

if os.environ.get("MCAD_REPAIR_REOPEN"):
    expected = json.loads(EXPECTED.read_text())
    assert bpy.ops.wm.open_mainfile(filepath=str(INVALID)) == {"FINISHED"}
    check(
        bpy.context.scene.mechanical_cad.repair_intent_json == "unsupported raw repair",
        "Unsupported raw intent survives a separate-process load",
    )
    assert bpy.ops.wm.save_as_mainfile(filepath=str(INVALID)) == {"FINISHED"}
    check(
        bpy.context.scene.mechanical_cad.repair_intent_json == "unsupported raw repair",
        "Unsupported intent can be saved again without migration or Resume",
    )
    with patch.object(
        doc, "_run_sidecar", side_effect=AssertionError("Load must not replay saved intent")
    ):
        assert bpy.ops.wm.open_mainfile(filepath=str(BLEND)) == {"FINISHED"}
    state = bpy.context.scene.mechanical_cad
    check(
        state.document_json == expected["accepted"],
        "Reopen restores exact accepted canonical bytes",
    )
    check(
        state.repair_intent_json == expected["raw"],
        "Reopen restores only exact proposal intent text",
    )
    check(
        staged_edit.current(bpy.context) is None and not doc.part_is_current(bpy.context),
        "Load creates no live proposal or current geometry authority",
    )
    check(
        not state.last_action_error,
        "Successful repair Save reopens without an informational notice in the error field",
    )
    accepted = snapshot()
    calls = []
    run = doc._run_sidecar

    def record(*args, **kwargs):
        calls.append(copy.deepcopy(args[1]))
        return run(*args, **kwargs)

    with patch.object(doc, "_run_sidecar", side_effect=record):
        assert bpy.ops.mcad.resume_saved_repair() == {"FINISHED"}
    proposal = staged_edit.current(bpy.context)
    check(
        len(calls) == 3 and calls[0] == json.loads(expected["accepted"]),
        "Resume freshly replays base and both retained proposal states",
    )
    check(
        snapshot() == accepted and not state.repair_intent_json,
        "Resume consumes intent only after success without geometry publication",
    )
    check(
        len(proposal.repairs) == 1 and proposal.token not in expected["tokens"],
        "Fresh owner retains proposal-local Undo but no old token",
    )
    assert bpy.ops.mcad.undo_proposal_repair(staged_token=proposal.token) == {"FINISHED"}
    check(
        staged_edit.current(bpy.context).candidate_json == json.loads(expected["raw"])["states"][0],
        "Proposal Undo after separate-process Resume restores exact prior intent",
    )
    check(
        snapshot() == accepted,
        "Resumed proposal Undo leaves canonical data and hidden display unchanged",
    )
    staged_edit.discard(bpy.context)
    state.repair_intent_json = "unreadable raw"
    assert bpy.ops.mcad.discard_saved_repair() == {"FINISHED"}
    check(
        not state.repair_intent_json and snapshot() == accepted,
        "Explicit Discard handles unreadable saved intent without accepted changes",
    )
    unregister()
    print("MCAD_SAVED_REPAIR_REOPEN_OK=" + json.dumps(checks), flush=True)
else:
    base, proposed = multiple_projection_case()
    assert doc._commit_candidate(bpy.context, base)
    bpy.ops.ed.undo_push(message="Accepted before saved repair")
    accepted = snapshot()
    reject(lambda: doc._commit_candidate(bpy.context, proposed, stage_feature_id="source"))
    original = staged_edit.current(bpy.context)
    # Seed the annotation intent at the same validated storage boundary used by
    # sketch Finish. Native viewport handoff itself has its independent smoke.
    layout = sketch_annotation_store.replace_annotations(
        "",
        base["id"],
        "source",
        {
            "size": {
                "kind": "radius",
                "refs": ["replacement_ring"],
                "display": "radius",
                "offset": [2, 3],
            },
        },
    )
    original = replace(original, annotation_before="", annotation_after=layout)
    staged_edit_store._PENDING[bpy.context.scene.as_pointer()] = original
    repair("target", {"CANCELLED"})
    partial = staged_edit.current(bpy.context)
    check(
        len(partial.repairs) == 1 and snapshot() == accepted,
        "Native partial repair retains history with no accepted mutation",
    )
    state = bpy.context.scene.mechanical_cad

    with patch.object(
        repair_intent, "encode", side_effect=ValueError("injected checkpoint failure")
    ):
        registration._before_blend_save(None)
        registration._after_blend_save(None)
    check(
        staged_edit.current(bpy.context) is partial and not state.repair_intent_json,
        "Checkpoint failure never retires live work or claims persistence",
    )
    check(
        "checkpoint failed" in state.last_action_error.lower(),
        "Checkpoint failure is visibly disclosed",
    )
    registration._before_blend_save(None)
    check(
        not state.last_action_error,
        "Successful checkpoint clears obsolete errors before file serialization",
    )
    raw = state.repair_intent_json
    check(
        bool(raw) and staged_edit.current(bpy.context) is partial,
        "save_pre writes intent but retains live owner",
    )
    registration._failed_blend_save(None)
    check(
        "Blender Save failed" in state.last_action_error,
        "Failed Save warning remains in the visible error channel",
    )
    check(
        staged_edit.current(bpy.context) is partial and state.repair_intent_json == raw,
        "save_post_fail retains live owner and in-memory checkpoint",
    )
    for replacement in ("externally replaced raw", ""):
        state.repair_intent_json = replacement
        registration._before_blend_save(None)
        registration._after_blend_save(None)
        check(
            state.repair_intent_json == replacement and staged_edit.current(bpy.context) is partial,
            "Save does not overwrite an externally changed checkpoint slot",
        )
        state.repair_intent_json = raw
    registration._before_blend_save(None)
    # A newer revision must not be retired by an older Save completion.
    assert bpy.ops.mcad.undo_proposal_repair(staged_token=partial.token) == {"FINISHED"}
    revised = staged_edit.current(bpy.context)
    registration._after_blend_save(None)
    check(
        staged_edit.current(bpy.context) is revised,
        "Late save_post cannot retire a newer live revision",
    )
    repair("target", {"CANCELLED"})
    partial = staged_edit.current(bpy.context)
    # The actual failing operator/hook combination must keep live work, whether
    # Blender rejects the path before or after save_pre on this platform.
    reject(
        lambda: bpy.ops.wm.save_as_mainfile(
            filepath=str(BLEND.parent / "absent-dir" / "failure.blend")
        )
    )
    check(
        staged_edit.current(bpy.context) is partial,
        "Actual failed Blender Save leaves live repair recoverable",
    )
    assert bpy.ops.wm.save_as_mainfile(filepath=str(BLEND)) == {"FINISHED"}
    check(
        not state.last_action_error,
        "Successful repair Save does not display a previous-error notice",
    )
    raw = state.repair_intent_json
    check(
        staged_edit.current(bpy.context) is None and bool(raw),
        "Actual successful Blender Save suspends checkpointed proposal",
    )
    check(snapshot() == accepted, "Blender Save does not change accepted JSON runtime or display")
    check(
        original.token not in raw and partial.token not in raw,
        "Saved JSON includes no old native or proposal token",
    )
    EXPECTED.write_text(
        json.dumps(
            {"accepted": state.document_json, "raw": raw, "tokens": [original.token, partial.token]}
        )
    )

    # Accepted-only exports remain available even with dormant saved intent.
    output = BLEND.with_suffix(".mcad.json")
    assert bpy.ops.mcad.save_document(filepath=str(output)) == {"FINISHED"}
    check(
        json.loads(output.read_text()) == json.loads(accepted[0]),
        "JSON Save exports accepted model, not repair intent",
    )
    step = BLEND.with_suffix(".step")
    assert geometry_operations.run_geometry_action(
        bpy.context, "export_step", destination=str(step)
    )
    report = json.loads(state.geometry_report_json)
    check(
        abs(report["geometry_check"]["brep"]["volume"] - 45 * math.pi) < 1e-7 and step.is_file(),
        "STEP export freshly validates accepted radius 3, never proposed radius 4",
    )
    check(
        state.document_json == accepted[0] and state.repair_intent_json == raw,
        "Export never consumes or accepts saved intent",
    )

    # Export legitimately refreshes accepted evidence/display; Resume must leave
    # that new accepted snapshot unchanged.
    accepted = snapshot()

    # Corrupt/unsupported/stale data remains byte-for-byte recoverable.
    good = json.loads(raw)
    corruptions = [
        "{not JSON",
        json.dumps({**good, "schema_version": 999}),
        json.dumps({**good, "scale": good["scale"] * 2}),
        json.dumps({**good, "owner_id": "different-owner"}),
    ]
    changed_base = copy.deepcopy(good)
    changed_base["base_json"] += " "
    import hashlib

    changed_base["base_hash"] = hashlib.sha256(changed_base["base_json"].encode()).hexdigest()
    corruptions.append(json.dumps(changed_base))
    invalid_binding = copy.deepcopy(good)
    last = json.loads(invalid_binding["states"][-1])
    next(f for f in last["features"] if f["id"] == "target")["projections"][0]["source"] = (
        "missing-replacement"
    )
    invalid_binding["states"][-1] = json.dumps(last)
    corruptions.append(json.dumps(invalid_binding))
    now_successful = copy.deepcopy(good)
    successful_candidate = json.loads(good["base_json"])
    next(f for f in successful_candidate["features"] if f["id"] == "source")["sketch"][
        "constraints"
    ][1]["value"] = "r + 1"
    now_successful["states"] = [json.dumps(successful_candidate)]
    corruptions.append(json.dumps(now_successful))
    for bad in corruptions:
        state.repair_intent_json = bad
        reject(lambda: staged_edit.resume(bpy.context))
        check(
            state.repair_intent_json == bad
            and staged_edit.current(bpy.context) is None
            and snapshot() == accepted,
            "Failed Resume preserves raw intent and accepted geometry",
        )
    state.repair_intent_json = "unsupported raw repair"
    assert bpy.ops.wm.save_as_mainfile(filepath=str(INVALID)) == {"FINISHED"}
    check(
        state.repair_intent_json == "unsupported raw repair",
        "Unsupported intent remains normally saveable",
    )
    state.repair_intent_json = raw
    state.sketch_annotation_json = sketch_annotation_store.replace_annotations(
        "", base["id"], "source", {}
    )
    reject(lambda: staged_edit.resume(bpy.context))
    check(
        state.repair_intent_json == raw and staged_edit.current(bpy.context) is None,
        "Changed annotation base refuses Resume without consuming intent",
    )
    state.sketch_annotation_json = ""
    state.sketch_draft_json = "unsupported independent draft"
    reject(lambda: staged_edit.resume(bpy.context))
    check(
        state.sketch_draft_json == "unsupported independent draft"
        and state.repair_intent_json == raw,
        "Resume cannot compete with or overwrite an independent saved draft",
    )
    state.sketch_draft_json = ""
    with patch.object(workspace, "active_draft", return_value=SimpleNamespace(scene=object())):
        reject(lambda: staged_edit.resume(bpy.context))
    check(
        state.repair_intent_json == raw,
        "Resume refuses a global active sketch owner in another scene",
    )
    reject(lambda: staged_edit_store.require_none(bpy.context))
    reject(lambda: sketch_session.SketchSession(bpy.context, object()))
    reject(lambda: doc._commit_candidate(bpy.context, base))
    check(
        state.repair_intent_json == raw,
        "Dormant repair prevents competing feature edits and sketch admission",
    )

    run = doc._run_sidecar
    claims = []

    def invalidate_backend(*args, **kwargs):
        evidence = run(*args, **kwargs)
        claims.append(evidence.publication)
        backend_runtime.revoke("Injected changed backend during Resume")
        return evidence

    with patch.object(doc, "_run_sidecar", side_effect=invalidate_backend):
        reject(lambda: staged_edit.resume(bpy.context))
    check(
        state.repair_intent_json == raw
        and staged_edit.current(bpy.context) is None
        and snapshot()[0] == accepted[0]
        and tuple(row[:2] for row in snapshot()[2]) == tuple(row[:2] for row in accepted[2]),
        "Changed backend rejects fresh-but-stale Resume response without losing raw intent",
    )
    check(not execution_lease.is_busy(), "Failed Resume releases the guarded operation lease")
    check(
        all(claim._state == "cancelled" for claim in claims),
        "Rejected Resume cancels every fresh publication claim",
    )
    # Backend invalidation deliberately marks/hides accepted display as stale.
    # Resume must not turn it current or publish replacement geometry.
    accepted = snapshot()
    scale = bpy.context.scene.unit_settings.scale_length

    def invalidate_units(*args, **kwargs):
        evidence = run(*args, **kwargs)
        bpy.context.scene.unit_settings.scale_length = scale * 2
        return evidence

    with patch.object(doc, "_run_sidecar", side_effect=invalidate_units):
        reject(lambda: staged_edit.resume(bpy.context))
    bpy.context.scene.unit_settings.scale_length = scale
    check(
        state.repair_intent_json == raw and staged_edit.current(bpy.context) is None,
        "Changed units reject late Resume evidence",
    )

    if bpy.app.timers.is_registered(staged_edit_store._supervise):
        bpy.app.timers.unregister(staged_edit_store._supervise)
    with patch.object(
        bpy.app.timers, "register", side_effect=RuntimeError("injected owner setup failure")
    ):
        reject(lambda: staged_edit.resume(bpy.context))
    check(
        state.repair_intent_json == raw
        and staged_edit.current(bpy.context) is None
        and snapshot() == accepted,
        "Failed fresh-owner installation preserves original saved intent",
    )
    assert bpy.ops.mcad.resume_saved_repair() == {"FINISHED"}
    resumed = staged_edit.current(bpy.context)
    check(
        len(resumed.repairs) == 1 and snapshot() == accepted and not state.repair_intent_json,
        "Registered Resume preserves partial repair history without accepted publication",
    )
    check(
        "UNDO" not in getattr(staged_edit_ui.MCAD_OT_resume_saved_repair, "bl_options", set()),
        "Resume has no canonical Undo option",
    )
    assert bpy.ops.mcad.undo_proposal_repair(staged_token=resumed.token) == {"FINISHED"}
    check(
        staged_edit.current(bpy.context).document == original.document and snapshot() == accepted,
        "Resumed proposal Undo restores original edit without canonical change",
    )
    repair("target", {"CANCELLED"})
    repair("target_two", {"FINISHED"})
    repaired = state.document_json
    check(
        state.sketch_annotation_json == layout,
        "Only final complete repair publishes saved annotation intent",
    )
    check(
        staged_edit.current(bpy.context) is None
        and not state.repair_intent_json
        and doc.part_is_current(bpy.context),
        "Final repair accepts atomically and leaves no saved or live proposal",
    )
    check(
        abs(doc.current_part_result(bpy.context)["features"][-1]["stats"]["volume"] - 80 * math.pi)
        < 1e-7,
        "Accepted complete repair has exact radius-4 native volume",
    )
    bpy.ops.ed.undo_push(message="Complete resumed repair")
    assert bpy.ops.ed.undo() == {"FINISHED"}
    drain()
    check(
        bpy.context.scene.mechanical_cad.document_json == accepted[0],
        "One ordinary Undo restores original accepted model after complete resumed repair",
    )
    assert bpy.ops.ed.redo() == {"FINISHED"}
    drain()
    check(
        bpy.context.scene.mechanical_cad.document_json == repaired,
        "Ordinary Redo restores complete repaired model",
    )
    # A history step in one still-failed sketch needs a fresh minimal binding
    # probe, not its old failure rows or another reference's stale driver values.
    base, proposed = same_sketch_projection_case()
    bpy.context.scene.mechanical_cad.repair_intent_json = ""
    assert doc._commit_candidate(bpy.context, base)
    reject(lambda: doc._commit_candidate(bpy.context, proposed, stage_feature_id="source"))
    repair("target", {"CANCELLED"})
    registration._before_blend_save(None)
    registration._after_blend_save(None)
    accepted_probe = snapshot()
    probe_calls = []
    run = doc._run_sidecar

    def record_probe(*args, **kwargs):
        probe_calls.append(args[1])
        return run(*args, **kwargs)

    with patch.object(doc, "_run_sidecar", side_effect=record_probe):
        assert bpy.ops.mcad.resume_saved_repair() == {"FINISHED"}
    check(
        len(probe_calls) == 4 and snapshot() == accepted_probe,
        "Same-sketch history Resume freshly proves the selected binding without publication",
    )
    check(
        len(staged_edit.current(bpy.context).repairs) == 1,
        "Same-sketch Resume retains exact Undo history",
    )
    staged_edit.discard(bpy.context)
    unregister()
    print("MCAD_SAVED_REPAIR_SMOKE_OK=" + json.dumps(checks), flush=True)
