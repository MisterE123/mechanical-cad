"""Native general-owner cyclic-equality rejection and explicit recovery.

This is a real sidecar/native-owner gate, not a manual GUI usability receipt.
"""

import copy
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
    constraint_actions,
    document_state,
    execution_lease,
    general_authoring_store,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    DraftError,
    PointRef,
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
    check(owner.pending is None, "Real native check completes")
    check(not execution_lease.is_busy(), "Completed check releases the execution lease")
    if success:
        check(not owner.error, "Ordinary native check succeeds: " + owner.error)
        check(owner.commands.has_current_solution, "Successful check has current authority")
    else:
        check("cyclic" in owner.error and "slvs 3.2" in owner.error, "Known hazard is readable")
        check(not owner.commands.has_current_solution, "Indeterminate DoF has no solve authority")
        check(owner.evidence_response is None, "Previous result is not current evidence")
        check(not owner.can_finish, "Indeterminate sketch cannot Finish")
        check(owner._failure_diagnostics is None, "No removable relation ID is fabricated")


def select(owner, kind, identifier):
    owner.draft.select(((kind, identifier),))
    owner.checkpoint()


def horizontal(owner, context, line, *, success=True):
    select(owner, "line", line)
    intent = constraint_actions.prepare(owner, "horizontal")
    result = constraint_actions.apply(owner, context, intent)
    check(result.changed, "Explicit H action records the authored relation")
    wait(owner, context, success=success)
    return result.constraint_id


register()
window = bpy.context.window
area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
region = next(item for item in area.regions if item.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    scene = context.scene
    document_state._populate_document(
        scene,
        {
            "schema_version": 1,
            "id": "dof_cycle_guard",
            "name": "DoF cycle recovery",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    canonical = scene.mechanical_cad.document_json
    unrelated = {item.name: item.as_pointer() for item in scene.objects}
    owner = general_session.GeneralSession(context)
    owner.start()
    owner.draft.begin_line(PointSeed(0, 0), (5, 0))
    a, b, first = owner.accept_proposal(context)
    wait(owner, context)
    owner.draft.begin_line(PointRef(b), (10, 5))
    c, second = owner.accept_proposal(context)
    wait(owner, context)
    owner.draft.begin_line(PointRef(c))
    (third,) = owner.accept_proposal(context, endpoint=PointRef(a))
    wait(owner, context)
    horizontal(owner, context, first)
    horizontal(owner, context, second)
    check(
        owner.evidence_response["result"]["sketch"]["remaining_dof"] == 4,
        "Acyclic H forest retains true four DoF",
    )
    closing = horizontal(owner, context, third, success=False)
    authored = copy.deepcopy(owner.commands.sketch)
    check(len(authored["constraints"]) == 3, "Failed check retains all three authored H relations")
    check(scene.mechanical_cad.document_json == canonical, "Failure does not publish a Part")
    stored = general_authoring_store.dumps(owner.draft)
    owner.check(context)
    wait(owner, context, success=False)
    check(
        general_authoring_store.dumps(owner.draft) == stored,
        "Repeated Check changes no draft bytes",
    )
    try:
        owner.request_finish(context)
    except DraftError:
        check(True, "Explicit Finish is rejected without current solve")
    else:
        raise AssertionError("Indeterminate draft finished")
    check(owner.commands.sketch == authored, "Rejected Finish changes no relation or point")

    owner.local_history(context)
    wait(owner, context)
    check(
        owner.evidence_response["result"]["sketch"]["remaining_dof"] == 4,
        "Undo restores truthful DoF",
    )
    owner.local_history(context, redo=True)
    wait(owner, context, success=False)
    check(owner.commands.sketch == authored, "Redo restores exact cyclic authored state")

    select(owner, "constraint", closing)
    recovery = constraint_actions.prepare(owner, "recover_remove_relation")
    check(
        recovery.requires_confirmation, "Authored-position recovery requests explicit confirmation"
    )
    check(recovery.relation_ids == (closing,), "Recovery targets only the user-selected relation")
    try:
        constraint_actions.apply(owner, context, recovery)
    except DraftError:
        check(True, "Unconfirmed recovery is rejected")
    else:
        raise AssertionError("Unconfirmed recovery applied")
    check(owner.commands.sketch == authored, "Cancelled recovery retains exact authored state")
    result = constraint_actions.apply(owner, context, recovery, confirmed=True)
    check(
        result.relation_ids == (closing,), "Confirmed explicit recovery names the exact removed ID"
    )
    wait(owner, context)
    check(
        owner.commands.sketch["points"] == authored["points"],
        "Explicit authored recovery preserves seed positions",
    )
    check(
        owner.evidence_response["result"]["sketch"]["remaining_dof"] == 4,
        "Recovery restores trustworthy DoF",
    )
    check(scene.mechanical_cad.document_json == canonical, "Local recovery does not publish a Part")
    owner.discard()
    check(scene.mechanical_cad.document_json == canonical, "Discard preserves the canonical Part")
    check(
        {item.name: item.as_pointer() for item in scene.objects} == unrelated,
        "Unrelated objects survive",
    )
unregister()
print("DOF_CYCLE_GUARD_SMOKE_OK", len(checks))
