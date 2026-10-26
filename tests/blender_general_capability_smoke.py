"""Actual GeneralSession guarded-current, ABA, clone and teardown regressions."""

import copy
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    backend_contracts,
    backend_runtime,
    constraint_actions,
    document_state,
    execution_lease,
    general_authoring_store,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_draft import (  # noqa: E402
    AddRelation,
    PointSeed,
)

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def wait(owner, context, *, success=True):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not execution_lease.is_busy(), "Native process reaped")
    check(bool(owner.error) is not success, "Expected native operation outcome: " + owner.error)


def authored(owner):
    state = owner.scene.mechanical_cad
    return (
        state.document_json,
        state.sketch_draft_json,
        state.sketch_annotation_json,
        general_authoring_store.dumps(owner.draft),
        owner.commands.revision,
    )


def rejects(callback, message):
    try:
        callback()
    except (ValueError, RuntimeError):
        check(True, message)
    else:
        raise AssertionError(message)


register()
window = bpy.context.window
area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
region = next(item for item in area.regions if item.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    document_state._populate_document(
        context.scene,
        {
            "schema_version": 1,
            "id": "general_capability",
            "name": "Guarded owner",
            "units": "mm",
            "parameters": {"radius": 5},
            "features": [],
            "active_feature": None,
        },
    )
    owner = general_session.GeneralSession(context)
    owner.start()
    owner.draft.begin_circle(PointSeed(2, 3), 8)
    center, rim = owner.accept_proposal(context)
    wait(owner, context)
    owner.execute(context, AddRelation("radius", (rim,), value="radius"))
    wait(owner, context)
    owner.draft.select((("point", center),))
    owner.checkpoint()
    intent = constraint_actions.prepare(owner, "fix_here")
    original_evidence = owner.guarded_evidence
    original_request, original_response = owner.evidence_request, owner.evidence_response
    clone = general_authoring_store.restore(
        general_authoring_store.dumps(owner.draft),
        owner.draft.document_json,
    ).command_draft
    owner._bind_commands(clone)
    clone.transfer_guarded_solution(owner.commands)
    check(
        clone._solution_evidence[0] is original_evidence, "Clone retains original evidence object"
    )
    check(owner.geometry().source == "solved", "Guarded native solve renders as solved")
    before = authored(owner)
    backend_runtime.revoke("Test settings A to B")
    backend_runtime.revoke("Test settings B to A")
    check(authored(owner) == before, "ABA preserves canonical, draft, annotation and journal bytes")
    check(not clone.has_current_solution, "ABA immediately revokes detached same-owner clone")
    check(not owner.commands.has_current_solution and not owner.can_finish, "ABA revokes Finish")
    check(owner.current_solution_response() is None, "ABA hides current solver report")
    check(owner.geometry().source == "retained", "ABA keeps explicitly retained outline")
    rejects(
        lambda: constraint_actions.apply(owner, context, intent), "Prepared solved seed rejects ABA"
    )
    check(authored(owner) == before, "Rejected seed intent preserves authored bytes")
    # Same authored content and same old dictionaries cannot restore a receipt.
    owner.evidence_request, owner.evidence_response = original_request, original_response
    owner.guarded_evidence = original_evidence
    check(owner.current_solution_response() is None, "Saved projections cannot revive old evidence")
    rejects(
        lambda: owner.commands.record_validated_solution(
            original_request,
            original_response,
            owner.commands.revision,
        ),
        "Production command draft rejects legacy matching response",
    )
    check(authored(owner) == before, "Legacy bypass creates no authored mutation")
    # Even actions that use authored coordinates are bound to the preparation epoch.
    origin = constraint_actions.prepare(owner, "fix_origin")
    backend_runtime.revoke("Authored intent A to B")
    backend_runtime.revoke("Authored intent B to A")
    rejects(
        lambda: constraint_actions.apply(owner, context, origin, True),
        "Prepared authored origin intent rejects ABA",
    )
    check(authored(owner) == before, "Origin rejection preserves source and journal")
    owner.check(context)
    wait(owner, context)
    check(
        owner.can_finish and owner.current_solution_response() is not None,
        "Fresh explicit Check restores same-owner authority",
    )
    # Completion and publication are one-shot; retained reads cannot be replayed
    # as another accepted result after local authority was deliberately retired.
    accepted = owner.guarded_evidence
    accepted_prepared = owner.expected_prepared
    before = authored(owner)
    owner.commands.invalidate_solution()
    owner._clear_display_evidence()
    owner.pending = SimpleNamespace(
        selection=accepted.selection, request_snapshot=accepted.operation_request
    )
    owner.pending_kind = "solve"
    owner.pending_prepared = accepted_prepared
    with patch.object(general_session.sketch_pending, "poll", return_value=accepted):
        owner.tick(context)
    check(
        owner.pending is None and not owner.commands.has_current_solution,
        "Repeated accepted completion cannot revive local authority",
    )
    check(
        "publication" in owner.error.lower(), "Original one-shot claim rejects repeated completion"
    )
    check(authored(owner) == before, "Repeated completion preserves authored bytes")
    owner.check(context)
    wait(owner, context)
    # A Python-equal but type-different prepared request must reject before launch.
    request = owner.commands.solve_request()
    prepared = backend_contracts.prepare_request(request)
    changed = copy.deepcopy(request)
    changed["document"]["parameters"]["radius"] = 5.0
    check(changed == request, "Regression fixture is Python-equal")
    with patch.object(
        general_session.assembly_job_ui,
        "ensure_supervisor",
        side_effect=AssertionError("Mismatched request reached launch"),
    ):
        rejects(
            lambda: owner._start_job(context, changed, "solve", prepared=prepared),
            "Type-sensitive prepared request rejects numeric rewrite",
        )
    check(owner.pending is None and not execution_lease.is_busy(), "No mismatched process starts")
    owner.execute(context, AddRelation("radius", (rim,), value=9))
    wait(owner, context, success=False)
    check(owner.current_diagnostics is not None, "Failed native report has current diagnostics")
    before = authored(owner)
    backend_runtime.revoke("Failed report A to B")
    backend_runtime.revoke("Failed report B to A")
    check(owner.current_diagnostics is None, "Failed native diagnostics reject ABA")
    check(authored(owner) == before, "Diagnostic revocation preserves authored conflict")
    owner.cleanup()
    check(clone._current_selection is None, "Teardown retires callback on detached clone")
    check(not clone.has_current_solution, "Retired clone remains unverified")
    check(owner._backend_context is None, "Teardown drops backend RNA context")

unregister()
print("GENERAL_CAPABILITY_SMOKE_OK", len(checks))
