"""Actual failed-solve diagnostics stay separate from current geometry authority."""

import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    execution_lease,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import AddRelation, PointSeed  # noqa: E402

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def wait(owner, context):
    deadline = time.monotonic() + 20
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None, "Actual native request completes")
    check(not execution_lease.is_busy(), "Completed actual child releases its lease")


register()
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    scene = context.scene
    document_state._populate_document(
        scene,
        {
            "schema_version": 1,
            "id": "conflict_native",
            "name": "Constraint diagnostics test",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    canonical = scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(context)
    owner.start()
    owner.draft.begin_circle(PointSeed(3, 4), 5)
    circle = owner.accept_proposal(context)[-1]
    wait(owner, context)
    owner.execute(context, AddRelation("radius", (circle,), value=5))
    wait(owner, context)
    conflicting = owner.execute(context, AddRelation("radius", (circle,), value=7))
    wait(owner, context)
    diagnostic = owner.current_diagnostics
    check(diagnostic is not None, "Actual inconsistent solve retains a strict diagnostic snapshot")
    check(
        diagnostic.solver_status in {"inconsistent", "didnt_converge"},
        "Diagnostic carries native failure status: " + diagnostic.solver_status,
    )
    check(bool(diagnostic.candidate_constraint_ids), "Native conflict candidates are retained")
    check(
        set(diagnostic.candidate_constraint_ids)
        <= {item["id"] for item in owner.commands.sketch["constraints"]},
        "Candidates name only authored relation identities",
    )
    check(not owner.commands.has_current_solution and not owner.can_finish, "No solve authority")
    check(
        owner.evidence_response is None and owner.evidence_request is None, "No geometry evidence"
    )
    check(
        owner.geometry().source == "authored", "Failure diagnostic never supplies solved geometry"
    )
    check(diagnostic.input_revision is None, "Ordinary check has no dimension-input revision")
    owner.draft.select((("constraint", conflicting.constraint_id),))
    owner.checkpoint()
    check(owner.current_diagnostics is diagnostic, "UI-only selection retains exact diagnostics")
    old = scene.mechanical_cad.document_json
    scene.mechanical_cad.document_json = old + " "
    check(
        owner.current_diagnostics is None,
        "Even a raw source-byte change makes diagnostics unavailable",
    )
    scene.mechanical_cad.document_json = old
    check(
        owner.current_diagnostics is None,
        "Observed source replacement cannot revive old diagnostics",
    )
    owner.check(context)
    wait(owner, context)
    check(owner.current_diagnostics is not None, "Explicit new Check restores diagnostic currency")
    slot = scene.mechanical_cad.sketch_draft_json
    scene.mechanical_cad.sketch_draft_json = slot + " "
    check(owner.current_diagnostics is None, "Observed saved-slot replacement retires diagnostics")
    scene.mechanical_cad.sketch_draft_json = slot
    check(owner.current_diagnostics is None, "Restored slot cannot revive the retired diagnostic")
    owner.check(context)
    wait(owner, context)
    check(owner.current_diagnostics is not None, "Fresh Check required after slot replacement")
    # No inspector query is needed to observe a mismatch: rejected authoring
    # entry points must retire candidates too.
    scene.mechanical_cad.document_json = old + " "
    try:
        owner.check(context)
    except ValueError:
        pass
    else:
        raise AssertionError("Changed source must reject Check")
    scene.mechanical_cad.document_json = old
    check(
        owner.current_diagnostics is None,
        "Rejected Check retires diagnostics without inspector access",
    )
    owner.check(context)
    wait(owner, context)
    scene.mechanical_cad.sketch_draft_json = slot + " "
    try:
        owner.execute(context, AddRelation("radius", (circle,), value=9))
    except ValueError:
        pass
    else:
        raise AssertionError("Changed slot must reject authoring")
    scene.mechanical_cad.sketch_draft_json = slot
    check(
        owner.current_diagnostics is None,
        "Rejected command retires diagnostics without inspector access",
    )
    owner.check(context)
    wait(owner, context)
    scene.mechanical_cad.document_json = old + " "
    check(not owner.can_use_tool("Check"), "Tool polling observes a changed base")
    scene.mechanical_cad.document_json = old
    check(owner.current_diagnostics is None, "Tool polling cannot leave revivable diagnostics")
    owner.check(context)
    wait(owner, context)
    scene.mechanical_cad.sketch_draft_json = slot + " "
    try:
        owner.checkpoint()
    except ValueError:
        pass
    else:
        raise AssertionError("Changed slot must reject direct checkpoint")
    scene.mechanical_cad.sketch_draft_json = slot
    check(owner.current_diagnostics is None, "Direct checkpoint rejection retires diagnostics")
    owner.begin_dimension(conflicting.constraint_id)
    check(owner.current_diagnostics is None, "Opening new input retires old failure diagnostics")
    owner.update_raw("6")
    owner.request_driver_accept(context)
    wait(owner, context)
    trial = owner.current_diagnostics
    check(trial is not None, "Actual failed input trial retains exact diagnostic candidates")
    check(trial.input_revision == owner.commands.pending_edit.input_revision, "Raw revision bound")
    check(trial.input_token == owner.input_token, "Input lease token bound")
    first_request = owner.commands.solve_request(trial=True)
    owner.update_raw("8")
    owner.update_raw("6")
    check(owner.current_diagnostics is None, "Raw A-B-A cannot revive a prior failure snapshot")
    check(
        trial.for_current(
            first_request,
            session_id=owner.session_id,
            command_revision=owner.commands.revision,
            input_token=owner.input_token,
            input_revision=owner.commands.pending_edit.input_revision,
        )
        is None,
        "Identical request bytes still require exact current raw revision",
    )
    owner.request_driver_accept(context)
    wait(owner, context)
    check(owner.current_diagnostics is not None, "Explicit retry establishes new diagnostics")
    owner.cancel_native()
    check(owner.current_diagnostics is None, "Cancellation retires diagnostics")
    owner.update_raw("1 / 0")
    owner.request_driver_accept(context)
    wait(owner, context)
    check(
        owner.error and owner.current_diagnostics is None,
        "Expression failure has no native candidates",
    )
    owner.cancel_dimension()
    owner.local_history(context)
    check(owner.current_diagnostics is None, "Undo retires diagnostics before new check")
    wait(owner, context)
    check(owner.commands.has_current_solution and owner.can_finish, "Undo and actual check recover")
    check(owner.current_diagnostics is None, "Successful check exposes no obsolete failed IDs")
    check(
        scene.mechanical_cad.document_json == canonical,
        "All local operations preserve canonical Part",
    )
    owner.cleanup()
    check(owner.current_diagnostics is None, "Retired owner exposes no diagnostics")
unregister()
print("CONSTRAINT_DIAGNOSTICS_SMOKE_OK", len(checks))
