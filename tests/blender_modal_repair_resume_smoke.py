"""Native guarded modal Resume: cancellation, stale ownership and exact history.

Background checks drive the production main-thread owner explicitly. Real GUI
navigation, button layout and installed-package qualification remain separate.
"""

import json
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
    assembly_job_ui,
    backend_runtime,
    display,
    execution_lease,
    extrusion_preview,
    projection_repair_ui,
    register,
    registration,
    repair_resume,
    sketch_pending,
    staged_edit,
    staged_edit_store,
    staged_edit_ui,
    unregister,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402
from staged_edit_cases import multiple_projection_case, same_sketch_projection_case  # noqa: E402

checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("MODAL_REPAIR_CHECK=" + message, flush=True)


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


def saved_case(case=multiple_projection_case):
    base, proposed = case()
    assert doc._commit_candidate(bpy.context, base)
    reject(lambda: doc._commit_candidate(bpy.context, proposed, stage_feature_id="source"))
    proposal = staged_edit.current(bpy.context)
    assert bpy.ops.mcad.replace_projection_reference(
        "EXEC_DEFAULT", feature_id="target", staged_token=proposal.token
    ) == {"CANCELLED"}
    partial = staged_edit.current(bpy.context)
    assert len(partial.repairs) == 1
    registration._before_blend_save(None)
    registration._after_blend_save(None)
    raw = bpy.context.scene.mechanical_cad.repair_intent_json
    assert raw and staged_edit.current(bpy.context) is None
    return raw, partial.token


def drain():
    deadline = time.monotonic() + 60
    while sketch_pending.status() or execution_lease.is_busy():
        assert time.monotonic() < deadline, sketch_pending.status()
        assembly_job_ui._supervise()
        time.sleep(0.01)


def unchanged(raw, accepted):
    assert bpy.context.scene.mechanical_cad.repair_intent_json == raw
    assert snapshot() == accepted
    assert staged_edit.current(bpy.context) is None


def ready(owner):
    deadline = time.monotonic() + 60
    while owner.pending._job.poll(owner.plan.binding["selection"]) != "ready":
        assert time.monotonic() < deadline
        time.sleep(0.01)


def one_check(owner):
    count = owner.plan.completed_requests
    owner.tick(bpy.context)
    deadline = time.monotonic() + 60
    while owner.pending is not None:
        assert time.monotonic() < deadline
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.plan.completed_requests == count + 1


def modal_finish(owner):
    while not owner.plan.complete:
        one_check(owner)
    count = owner.plan.completed_requests
    assert bpy.context.scene.mechanical_cad.repair_intent_json
    owner.tick(bpy.context)
    assert owner.closed and owner.success
    return count


# Blender background dispatch skips Invoke. Keep registered RNA/modal handler
# behavior but trampoline only this smoke's EXEC into the real Invoke method.
def invoke_resume(self, context):
    return staged_edit_ui.MCAD_OT_resume_saved_repair.invoke(self, context, None)


staged_edit_ui.MCAD_OT_resume_saved_repair.execute = invoke_resume
register()
assert bpy.app.background
area = next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D")
with bpy.context.temp_override(area=area):
    raw, old_token = saved_case()
    accepted = snapshot()

    with patch.object(doc, "_run_sidecar", side_effect=AssertionError("Invoke must not block")):
        assert bpy.ops.mcad.resume_saved_repair("EXEC_DEFAULT") == {"RUNNING_MODAL"}
    owner = repair_resume.active_for_scene(bpy.context.scene)
    check(
        owner is not None and owner.pending is None,
        "User Invoke starts without a synchronous native replay",
    )
    plan = owner.plan
    reject(lambda: doc.regenerate(bpy.context))
    reject(lambda: extrusion_preview.start(SimpleNamespace(), bpy.context))
    reject(lambda: staged_edit_store.discard_saved(bpy.context))
    reject(lambda: repair_resume.ResumeOwner(bpy.context))
    other = bpy.data.scenes.new("Other scene reservation test")
    with bpy.context.temp_override(scene=other):
        reject(lambda: staged_edit_store.require_none(bpy.context))
        reject(lambda: doc.regenerate(bpy.context))
        assert doc.has_staged_edit(bpy.context)
    check(
        not execution_lease.is_busy() and staged_edit_store.resume_reserved(),
        "Between-job reservation blocks competing edits in every scene without a fake native lease",
    )
    owner.tick(bpy.context)
    pending = owner.pending
    assert execution_lease.is_busy()
    assert bpy.ops.mcad.cancel_repair_resume() == {"FINISHED"}
    check(
        owner.closed
        and owner.plan is None
        and owner.scene is None
        and plan.binding is None
        and plan._iterator is None,
        "Visible Cancel detaches RNA and validation generator before native cleanup",
    )
    drain()
    unchanged(raw, accepted)
    check(
        pending.done and not staged_edit_store.resume_reserved(),
        "Pending native cancellation reaps the owned process and preserves exact saved intent",
    )

    owner = repair_resume.ResumeOwner(bpy.context)
    owner.tick(bpy.context)
    pending, timer = owner.pending, owner.timer
    owner.manager = SimpleNamespace(
        event_timer_remove=lambda timer: (_ for _ in ()).throw(
            TypeError("Injected timer cleanup failure")
        )
    )
    owner.close()
    bpy.context.window_manager.event_timer_remove(timer)
    drain()
    unchanged(raw, accepted)
    check(
        pending.done and owner.closed,
        "Unexpected UI teardown failure still cancels and reaps the native job",
    )

    owner = repair_resume.ResumeOwner(bpy.context)
    one_check(owner)
    assert not execution_lease.is_busy()
    reports = []
    operator = SimpleNamespace(
        _repair_resume=owner, report=lambda kind, message: reports.append(message)
    )
    assert repair_resume.modal(
        operator, bpy.context, SimpleNamespace(type="ESC", value="PRESS")
    ) == {"CANCELLED"}
    unchanged(raw, accepted)
    check(
        bool(reports) and not staged_edit_store.resume_reserved(),
        "Esc between states preserves original raw intent and frees only the reservation",
    )

    owner = repair_resume.ResumeOwner(bpy.context)
    owner.tick(bpy.context)
    ready(owner)
    assert execution_lease.is_busy()
    replacement = raw + " "
    bpy.context.scene.mechanical_cad.repair_intent_json = replacement
    reject(lambda: owner.tick(bpy.context))
    drain()
    unchanged(replacement, accepted)
    check(owner.closed, "Already-ready response is rejected when exact saved text changes")
    bpy.context.scene.mechanical_cad.repair_intent_json = raw
    replacement_owner = repair_resume.ResumeOwner(bpy.context)
    owner.tick(bpy.context)
    check(
        not replacement_owner.closed and staged_edit_store.resume_reserved(),
        "Late tick from retired owner cannot cancel or advance a replacement",
    )
    replacement_owner.close()

    for label, change in (
        ("history", lambda: registration._before_history_change(None)),
        ("load", lambda: registration._before_blend_load(None)),
        ("backend", lambda: backend_runtime.revoke("Injected backend generation change")),
        ("save", lambda: registration._before_blend_save(None)),
    ):
        for phase in ("pending", "between states"):
            owner = repair_resume.ResumeOwner(bpy.context)
            if phase == "pending":
                owner.tick(bpy.context)
            else:
                one_check(owner)
            change()
            drain()
            # Existing history/backend hooks may hide last-good display caches.
            # Resume itself must never replace their native meshes or canonical data.
            current = snapshot()
            assert current[0] == accepted[0] and current[2] == accepted[2]
            assert [r[:2] for r in current[1]] == [r[:2] for r in accepted[1]]
            accepted = current
            unchanged(raw, accepted)
            check(
                owner.closed and not staged_edit_store.resume_reserved(),
                f"{label} change cancels {phase} without consuming intent",
            )

    owner = repair_resume.ResumeOwner(bpy.context)
    owner.tick(bpy.context)
    ready(owner)
    scale = bpy.context.scene.unit_settings.scale_length
    bpy.context.scene.unit_settings.scale_length = scale * 2
    assembly_job_ui._supervise()
    bpy.context.scene.unit_settings.scale_length = scale
    drain()
    unchanged(raw, accepted)
    check(
        owner.closed, "Shared supervisor rejects ready work after units change without consuming it"
    )

    owner = repair_resume.ResumeOwner(bpy.context)
    owner.tick(bpy.context)
    owner._window_pointer = -1
    assembly_job_ui._supervise()
    drain()
    unchanged(raw, accepted)
    check(
        owner.closed and owner.window is None,
        "Lost-window supervisor detaches the input owner and reaps pending work",
    )

    owner = repair_resume.ResumeOwner(bpy.context)
    area.type = "TEXT_EDITOR"
    assembly_job_ui._supervise()
    area.type = "VIEW_3D"
    unchanged(raw, accepted)
    check(owner.closed, "Changed editor revokes a between-job owner without accepting geometry")

    with patch.object(
        assembly_job_ui, "watch_owner", side_effect=RuntimeError("Injected UI setup failure")
    ):
        reject(lambda: repair_resume.ResumeOwner(bpy.context))
    unchanged(raw, accepted)
    check(
        not repair_resume._OWNERS and not staged_edit_store.resume_reserved(),
        "Interaction setup failure leaves no reservation or raw-text mutation",
    )

    owner = repair_resume.ResumeOwner(bpy.context)
    with patch.object(
        sketch_pending, "prepare_guarded", side_effect=RuntimeError("Injected start failure")
    ):
        reject(lambda: owner.tick(bpy.context))
    unchanged(raw, accepted)
    check(
        owner.closed and not execution_lease.is_busy(),
        "Native job start failure retires Resume without retry",
    )

    factory = sketch_pending._GUARDED_JOB_FACTORY
    started_jobs = []

    def start_then_fail(*args, **kwargs):
        job = factory(*args, **kwargs)
        start = job.start

        def fail(selection):
            start(selection)
            raise RuntimeError("Injected failure after actual native start")

        job.start = fail
        started_jobs.append(job)
        return job

    owner = repair_resume.ResumeOwner(bpy.context)
    with patch.object(sketch_pending, "_GUARDED_JOB_FACTORY", side_effect=start_then_fail):
        reject(lambda: owner.tick(bpy.context))
    assert bpy.app.timers.is_registered(assembly_job_ui._supervise)
    drain()
    unchanged(raw, accepted)
    check(
        owner.closed and all(job.done for job in started_jobs),
        "Partially started job remains covered by shared cleanup when prepare returns no handle",
    )

    owner = repair_resume.ResumeOwner(bpy.context)
    while not owner.plan.complete:
        one_check(owner)
    with patch.object(
        staged_edit_store, "restore_validated", side_effect=RuntimeError("Injected install failure")
    ):
        reject(lambda: owner.tick(bpy.context))
    unchanged(raw, accepted)
    check(owner.closed, "Final installation failure retains the original intent and accepted model")

    owner = repair_resume.ResumeOwner(bpy.context)
    while not owner.plan.complete:
        one_check(owner)
    original_assert = doc._assert_binding
    calls = []

    def revoke_during_install(context, binding):
        original_assert(context, binding)
        calls.append(True)
        if len(calls) == 4:
            repair_resume.cancel_all("Injected final owner revocation")

    with patch.object(doc, "_assert_binding", side_effect=revoke_during_install):
        reject(lambda: owner.tick(bpy.context))
    unchanged(raw, accepted)
    check(
        owner.closed and len(calls) >= 4,
        "Revocation inside the final binding check cannot resurrect a proposal owner",
    )

    owner = repair_resume.ResumeOwner(bpy.context)
    poll, claims = sketch_pending.poll, []

    def record_claim(*args, **kwargs):
        evidence = poll(*args, **kwargs)
        if evidence is not None:
            claims.append(evidence.publication)
        return evidence

    with (
        patch.object(
            doc, "_run_sidecar", side_effect=AssertionError("Modal must use guarded async jobs")
        ),
        patch.object(sketch_pending, "poll", side_effect=record_claim),
    ):
        count = modal_finish(owner)
    proposal = staged_edit.current(bpy.context)
    check(
        len(claims) == 3 and all(claim._state == "cancelled" for claim in claims),
        "Successful modal validation retains no native publication claims",
    )
    check(
        count == 3 and not bpy.context.scene.mechanical_cad.repair_intent_json,
        "Exact successful multi-state Resume uses three guarded jobs and consumes raw only at final install",
    )
    check(
        snapshot() == accepted and len(proposal.repairs) == 1 and proposal.token != old_token,
        "Successful Resume creates fresh proposal ownership, preserves history and never publishes geometry",
    )
    assert bpy.ops.mcad.undo_proposal_repair(staged_token=proposal.token) == {"FINISHED"}
    check(
        staged_edit.current(bpy.context).candidate_json == json.loads(raw)["states"][0]
        and snapshot() == accepted,
        "Undo Proposal Repair after modal Resume restores exact prior candidate without canonical Undo",
    )
    staged_edit.discard(bpy.context)

    raw, _ = saved_case(same_sketch_projection_case)
    accepted = snapshot()
    owner = repair_resume.ResumeOwner(bpy.context)
    count = modal_finish(owner)
    check(
        count == 4 and snapshot() == accepted,
        "Selected-binding proof runs as its own guarded job when another projection still fails",
    )
    staged_edit.discard(bpy.context)

    raw, _ = saved_case()
    accepted = snapshot()
    owner = repair_resume.ResumeOwner(bpy.context)
    owner.tick(bpy.context)
    unregister()
    drain()
    check(
        owner.closed and not repair_resume._OWNERS and not staged_edit_store.resume_reserved(),
        "Add-on disable cancels pending Resume before unregistering RNA",
    )

print("MCAD_MODAL_REPAIR_RESUME_OK=" + json.dumps(checks), flush=True)
