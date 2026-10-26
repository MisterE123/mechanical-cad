"""Native candidate creation/cancellation and fresh-process accepted reopen.

Run writer, then MCAD_GEAR_ASYNC_REOPEN=1 reader, using MCAD_GEAR_ASYNC_DIRECTORY.
Background modal/timer pumping does not establish interactive GUI/Undo coverage.
"""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    assembly_job_ui,
    assembly_pending,
    assembly_state,
    document_state,
    execution_lease,
    history_rebuild,
    register,
    workspace,
)

OUT = Path(os.environ["MCAD_GEAR_ASYNC_DIRECTORY"])
OUT.mkdir(exist_ok=True, parents=True)
REPORT = (
    "report_json",
    "report_document_json",
    "report_request_json",
    "report_working_part_json",
    "report_preset_id",
)
PART = (
    "document_json",
    "owner_id",
    "repair_intent_json",
    "sketch_annotation_json",
    "sketch_draft_json",
)
checks = []
register()


def check(value, label):
    assert value, label
    checks.append(label)
    print("GEAR_ASYNC_CHECK", label, flush=True)


def snapshot():
    scene = bpy.context.scene
    state = scene.mechanical_cad_assembly
    return {
        "assembly": state.document_json,
        "owner": state.owner_id,
        "path": state.document_path,
        "report": {name: getattr(state, name) for name in REPORT},
        "part": {name: getattr(scene.mechanical_cad, name) for name in PART},
    }


def objects():
    state = bpy.context.scene.mechanical_cad_assembly
    return {
        obj.as_pointer()
        for obj in assembly_display.owned_objects(bpy.context.scene, state.owner_id)
    }


def drain_operator(operator):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = operator.modal(bpy.context, SimpleNamespace(type="TIMER", value="NOTHING"))
        if result in ({"FINISHED"}, {"CANCELLED"}):
            return result
        assembly_pending.reap(bpy.context)
        time.sleep(0.02)
    raise AssertionError("Candidate completion timed out")


def drain_load():
    deadline = time.monotonic() + 120
    while history_rebuild._PENDING is not None or execution_lease.is_busy():
        assert time.monotonic() < deadline
        history_rebuild._tick()
        assembly_pending.reap(bpy.context)
        time.sleep(0.02)


def start_operator():
    started = time.monotonic()
    result = bpy.ops.mcad.gear_pair(replace_existing=True)
    elapsed = time.monotonic() - started
    check(result == {"RUNNING_MODAL"}, "Apply starts modal instead of blocking")
    check(elapsed < 2, "Apply returns in under two seconds")
    print("GEAR_ASYNC_START_SECONDS", elapsed, flush=True)
    return assembly_job_ui._OPERATORS[-1]


if os.environ.get("MCAD_GEAR_ASYNC_REOPEN"):
    expected = json.loads((OUT / "expected.json").read_text())
    check(
        bpy.ops.wm.open_mainfile(filepath=str(OUT / "gears.blend")) == {"FINISHED"},
        "Fresh-process Open",
    )
    check(snapshot() == expected, "Open preserves exact canonical/report/Part bytes")
    check(not assembly_state.display_is_current(bpy.context), "Saved display is not trusted")
    check(
        history_rebuild._PENDING is not None,
        "Accepted Assembly rebuild queued, not candidate resumed",
    )
    drain_load()
    check(snapshot() == expected, "Fresh accepted replay preserves all saved bytes")
    check(assembly_state.display_is_current(bpy.context), "Fresh accepted gear geometry restored")
    check(not assembly_state.report_is_current(bpy.context), "Reopen does not claim checks")
    check(
        assembly_state._RUNTIME[assembly_state._key(bpy.context.scene)]["report_binding"] is None,
        "Report has no current authority",
    )
    check(
        bpy.context.scene.mechanical_cad_assembly.verification_status != "CURRENT",
        "Checks explicitly historical",
    )
    check(tuple(bpy.data.objects["Cube"].location) == (7, 8, 9), "Unrelated object preserved")
    check(
        not assembly_pending._ACTIVE and not execution_lease.is_busy(),
        "One restoration owner fully retired",
    )
    print("GEAR_ASYNC_REOPEN_OK", len(checks))
    raise SystemExit(0)

scene = bpy.context.scene
scene.objects["Cube"].location = (7, 8, 9)
bpy.context.workspace[workspace.OWNER_KEY] = workspace.OWNER
bpy.context.workspace[workspace.ROLE_KEY] = "ASSEMBLY"
old = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
document_state._populate_document(scene, old["part_sources"][0]["document"])
assembly_state.commit_candidate(bpy.context, old)
assembly_state.check(bpy.context)
state = scene.mechanical_cad_assembly
state.document_path = "/saved/original-assembly.json"
scene.mechanical_cad.repair_intent_json = " opaque dormant repair {unknown-version:999 "
scene.mechanical_cad.sketch_annotation_json = " opaque saved annotation \n"
accepted = snapshot()
accepted_objects = objects()
check(
    assembly_state.report_is_current(bpy.context), "Existing explicit Check current before creation"
)
operator = start_operator()
check(
    snapshot() == accepted and objects() == accepted_objects,
    "Running candidate changes no accepted bytes or objects",
)
check(assembly_pending.status(scene)["candidate"], "Creating gear pair status is explicit")
check(bpy.ops.mcad.assembly_cancel_check() == {"FINISHED"}, "Panel Cancel Creation available")
check(drain_operator(operator) == {"CANCELLED"}, "Running native work cancelled")
check(
    snapshot() == accepted and objects() == accepted_objects,
    "Cancel retains original report/path/display/Part",
)
check(
    assembly_state.report_is_current(bpy.context), "Cancellation does not erase old check authority"
)


# Real native ready-but-unpublished candidate, cheap geometry to isolate ownership.
def ready_candidate():
    captured = assembly_pending.capture_candidate(bpy.context)
    candidate = assembly_state.read_assembly(state)
    candidate["name"] = "Unaccepted candidate"
    pending = assembly_pending.prepare_candidate(bpy.context, candidate, captured)
    pending._job.wait(90)
    check(pending._job.state == "ready", "Native candidate ready before acceptance")
    return pending


pending = ready_candidate()
assembly_pending.cancel(pending, "Ready creation cancelled")
check(
    snapshot() == accepted and objects() == accepted_objects,
    "Ready Cancel cannot accept cached result",
)
pending = ready_candidate()
assembly_state.begin_interaction()  # A new dialog can open and cancel without changing JSON.
try:
    assembly_pending.poll(bpy.context, pending)
    raise AssertionError("New dialog admission was ignored")
except RuntimeError:
    pass
check(snapshot() == accepted and objects() == accepted_objects, "New dialog revokes ready result")
check(not execution_lease.is_busy(), "Ready rejection releases exact lease")

# Native Open while the previous candidate owns the process revokes old RNA/results.
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "baseline.blend"))
operator = start_operator()
handle = operator._pending
bpy.ops.wm.open_mainfile(filepath=str(OUT / "baseline.blend"))
check(handle.done or handle._detached, "Open retires or detaches old creation owner")
drain_load()
check(snapshot() == accepted, "New file load preserves accepted baseline, not pending candidate")
check(
    assembly_state.display_is_current(bpy.context),
    "Baseline accepted display restored after cancellation",
)
check(
    not assembly_pending._ACTIVE and not execution_lease.is_busy(),
    "Old process owner cannot compete with restoration",
)

operator = start_operator()
before = snapshot()
check(before == accepted, "New default creation starts against exact restored baseline")
started = time.monotonic()
check(
    drain_operator(operator) == {"FINISHED"}, "Default complete gear pair accepted asynchronously"
)
print("GEAR_ASYNC_NATIVE_SECONDS", time.monotonic() - started, flush=True)
state = bpy.context.scene.mechanical_cad_assembly
model = json.loads(state.document_json)
check(
    len(model["parts"]) == 3 and len(model["joints"]) == 2,
    "Both gear solids and rooted joints accepted together",
)
check(model["gear_relations"][0]["ratio"] == -0.5, "Complete authored gear relation retained")
check(state.document_path == "", "Old path cleared only at successful acceptance")
check(snapshot()["part"] == accepted["part"], "Working Part and dormant intent byte-identical")
check(assembly_state.display_is_current(bpy.context), "New accepted display current")
check(
    state.verification_status == "UNCHECKED" and not assembly_state.report_is_current(bpy.context),
    "Replay explicitly not a Check",
)
check(
    json.loads(state.report_request_json)["action"] == "assembly_replay",
    "No per-Apply interference request",
)
check(tuple(bpy.data.objects["Cube"].location) == (7, 8, 9), "Unrelated object unchanged")
check(
    not assembly_pending._ACTIVE and not execution_lease.is_busy(),
    "Creation fully releases single owner",
)
bpy.context.scene.mechanical_cad.sketch_draft_json = " unknown dormant draft [ "
expected = snapshot()
(OUT / "expected.json").write_text(json.dumps(expected))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "gears.blend"))
print("GEAR_ASYNC_WRITE_OK", len(checks))
