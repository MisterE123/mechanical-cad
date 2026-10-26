"""General-owner setup/cancel failures with real sidecars and native input routing."""

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
    assembly_job_ui,
    dimension_input,
    document_state,
    execution_lease,
    general_session,
    general_viewport,
    register,
    sketch_pending,
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
    check(owner.pending is None and not owner.error, "Real operation completes successfully")


def event(kind, value="PRESS", unicode=""):
    return SimpleNamespace(
        type=kind,
        value=value,
        unicode=unicode,
        mouse_x=0,
        mouse_y=0,
        ctrl=False,
        shift=False,
        alt=False,
        is_repeat=False,
    )


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
            "id": "failure_test",
            "name": "Failure test",
            "units": "mm",
            "parameters": {"radius": 5},
            "features": [],
            "active_feature": None,
        },
    )
    canonical = scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(context)
    owner.start()
    owner.draft.begin_circle(PointSeed(0, 0), 5)
    ids = owner.accept_proposal(context)
    wait(owner, context)
    relation = owner.execute(context, AddRelation("radius", (ids[-1],), value="radius"))
    wait(owner, context)

    # This must fail before any child/lease exists, even without an old timer.
    if bpy.app.timers.is_registered(assembly_job_ui._supervise):
        bpy.app.timers.unregister(assembly_job_ui._supervise)
    with patch.object(
        assembly_job_ui, "ensure_supervisor", side_effect=RuntimeError("setup refused")
    ):
        with patch.object(
            sketch_pending, "prepare_guarded", wraps=sketch_pending.prepare_guarded
        ) as prepare:
            try:
                owner.check(context)
            except RuntimeError as exc:
                check(str(exc) == "setup refused", "Original setup failure stays explicit")
            else:
                raise AssertionError("Expected supervisor failure")
            check(not prepare.called, "Supervisor failure creates no process or transport handle")
    check(owner.pending is None, "Failed setup leaves no unreachable owner handle")
    check(not execution_lease.is_busy(), "Failed setup cannot strand the execution lease")
    check(not sketch_pending.reap(), "No cancelling child remains after failed setup")
    owner.check(context)
    wait(owner, context)
    check(scene.mechanical_cad.document_json == canonical, "Retry remains a local sketch check")

    general_viewport._open_field(owner, relation.constraint_id, (100, 100))
    revision = owner.commands.revision
    raw = owner.commands.pending_edit.raw_text
    routed = owner.input_controller.handle(dimension_input.InputEvent("RET"))
    check([a.kind for a in routed.actions] == ["accept"], "Enter explicitly requests acceptance")
    owner.request_driver_accept(context)
    check(owner.input_controller.accept_requested, "Controller is latched while trial runs")
    check(owner.pending is not None, "Trial has a real pending native handle")
    check(bpy.ops.mcad.general_tool(tool="CancelCheck") == {"FINISHED"}, "Native Cancel Check runs")
    check(not owner.input_controller.accept_requested, "Cancel Check releases acceptance latch")
    check(not owner.input_controller.closed, "Cancel Check retains the editable field")
    check(owner.commands.pending_edit.raw_text == raw, "Cancel Check retains exact raw input")
    check(owner.commands.revision == revision, "Cancelled trial accepts no command")
    deadline = time.monotonic() + 10
    while execution_lease.is_busy() and time.monotonic() < deadline:
        sketch_pending.reap()
        time.sleep(0.01)
    check(not execution_lease.is_busy(), "Cancelled real child is reaped before lease release")
    general_viewport._route_field(owner, context, event("RET", "RELEASE"))
    check(
        general_viewport._route_field(owner, context, event("ONE", unicode="1")),
        "Typing routes again",
    )
    check(owner.commands.pending_edit.raw_text == raw + "1", "New typing reaches retained draft")

    check(bpy.ops.mcad.general_tool(tool="CancelInput") == {"FINISHED"}, "Native Cancel Input runs")
    check(
        owner.commands.pending_edit is None and not owner.input_token,
        "Cancel Input revokes the edit",
    )
    check(owner.input_controller.closed, "Cancel Input closes its controller")
    check(not owner.error, "Cancel Input clears obsolete validation error")
    check(
        not general_viewport._route_field(owner, context, event("X", unicode="x")),
        "Closed field does not swallow a new key",
    )
    check(owner.commands.revision == revision, "Input cancellation preserves accepted revision")
    check(
        scene.mechanical_cad.document_json == canonical, "Failure/cancel paths never publish a Part"
    )
    owner.check(context)
    wait(owner, context)
    check(owner.geometry().circles[ids[-1]].radius_mm == 5, "Fresh check restores accepted driver")
    owner.discard()
unregister()
print("GENERAL_FAILURE_SMOKE_OK", len(checks))
