"""Explicit async Replay with native sidecar, cancellation and real Undo/Redo.

Background modal pumping verifies operator/ownership, not interactive redraw.
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
    gear_pair,
    register,
)

checks = []
register()


def check(value, label):
    assert value, label
    checks.append(label)
    print("REPLAY_ASYNC_CHECK", label, flush=True)


def snapshot():
    state = bpy.context.scene.mechanical_cad_assembly
    return {
        name: getattr(state, name)
        for name in assembly_state._STATE_FIELDS
        if name != "last_action_error"
    }


def objects():
    scene = bpy.context.scene
    return {
        obj.as_pointer()
        for obj in assembly_display.owned_objects(scene, scene.mechanical_cad_assembly.owner_id)
    }


def start():
    before = time.monotonic()
    result = bpy.ops.mcad.assembly_replay()
    elapsed = time.monotonic() - before
    check(result == {"RUNNING_MODAL"}, "Replay returns RUNNING_MODAL")
    check(elapsed < 2, "Replay start under two seconds")
    print("REPLAY_ASYNC_START_SECONDS", elapsed, flush=True)
    return assembly_job_ui._OPERATORS[-1]


def drain(operator):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = operator.modal(bpy.context, SimpleNamespace(type="TIMER", value="NOTHING"))
        if result in ({"FINISHED"}, {"CANCELLED"}):
            return result
        assembly_pending.reap(bpy.context)
        time.sleep(0.02)
    raise AssertionError("Replay timed out")


scene = bpy.context.scene
scene.objects["Cube"].location = (7, 8, 9)
original = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
document_state._populate_document(scene, original["part_sources"][0]["document"])
assembly_state.commit_candidate(bpy.context, original)
assembly_state.check(bpy.context)
scene.mechanical_cad_assembly.document_path = "/saved/accepted-assembly.json"
accepted, old_objects = snapshot(), objects()
check(assembly_state.report_is_current(bpy.context), "Existing Check is current")
operator = start()
check(snapshot() == accepted and objects() == old_objects, "Running Replay preserves bundle")
check(assembly_pending.status(scene)["replay"], "Distinct Replay status")
check(bpy.ops.mcad.assembly_cancel_check() == {"FINISHED"}, "Panel Cancel Replay works")
check(drain(operator) == {"CANCELLED"}, "Cancellation drains native owner")
check(snapshot() == accepted and objects() == old_objects, "Cancel preserves accepted bundle")
check(assembly_state.report_is_current(bpy.context), "Cancel preserves Check currentness")

operator = start()
operator._pending._job.wait(90)
check(operator._pending._job.state == "ready", "Native result ready before publication")
assembly_state.begin_interaction()
check(drain(operator) == {"CANCELLED"}, "New editor rejects ready Replay")
check(snapshot() == accepted and objects() == old_objects, "Stale completion preserves bundle")
check(assembly_state.report_is_current(bpy.context), "Stale completion preserves old Check")

operator = start()
revision = assembly_state.interaction_revision()
try:
    repeated = bpy.ops.mcad.assembly_replay()
    check(repeated == {"CANCELLED"}, "Repeated Replay rejected")
except RuntimeError:
    check(True, "Repeated Replay reports busy")
check(assembly_state.interaction_revision() == revision, "Repeated click cannot revoke owner")
check(len(assembly_job_ui._OPERATORS) == 1, "Only one modal owner")
check(drain(operator) == {"FINISHED"}, "Original Replay still accepted")
check(snapshot()["document_path"] == accepted["document_path"], "Successful Replay preserves path")
check(assembly_state.display_is_current(bpy.context), "Successful Replay display current")
check(not assembly_state.report_is_current(bpy.context), "Replay is not a Check")

# Native history restoration must not resurrect a pre-history candidate or check.
bpy.context.preferences.edit.use_global_undo = True
bpy.ops.ed.undo_push(message="Original accepted Assembly")
changed = assembly_state.read_assembly(bpy.context.scene.mechanical_cad_assembly)
changed["name"] = "New accepted revision"
assembly_state.commit_candidate(bpy.context, changed)
bpy.ops.ed.undo_push(message="Changed accepted Assembly")
check(bpy.ops.ed.undo() == {"FINISHED"}, "Native Undo")
check(
    json.loads(bpy.context.scene.mechanical_cad_assembly.document_json)["name"] == original["name"],
    "Undo restores original accepted JSON",
)
check(bpy.ops.ed.redo() == {"FINISHED"}, "Native Redo")
expected = bpy.context.scene.mechanical_cad_assembly.document_json
check(json.loads(expected)["name"] == "New accepted revision", "Redo restores changed JSON")
check(not assembly_state.display_is_current(bpy.context), "History display not trusted")
operator = start()
check(
    operator._pending.request_snapshot()["assembly"] == json.loads(expected),
    "Post-history Replay binds exact current accepted JSON",
)
check(drain(operator) == {"FINISHED"}, "Post-history Replay completes")
check(
    bpy.context.scene.mechanical_cad_assembly.document_json == expected,
    "Post-history canonical remains exact",
)

# Exercise the realistic expensive geometry which motivated this change.
assembly_state.commit_candidate(bpy.context, gear_pair.build_pair())
operator = start()
check(
    operator.modal(bpy.context, SimpleNamespace(type="MOUSEMOVE", value="NOTHING"))
    == {"PASS_THROUGH"},
    "Viewport navigation passes through during gear Replay",
)
check(drain(operator) == {"FINISHED"}, "Native gear pair Replay completes")
check(assembly_state.display_is_current(bpy.context), "Gear display current")
check(
    json.loads(bpy.context.scene.mechanical_cad_assembly.report_request_json)["action"]
    == "assembly_replay",
    "No automatic interference query",
)
check(not assembly_pending._ACTIVE and not execution_lease.is_busy(), "All native owners retired")
check(tuple(bpy.context.scene.objects["Cube"].location) == (7, 8, 9), "Unrelated Cube untouched")
check(
    not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules),
    "OCCT stays outside Blender",
)
print("ASSEMBLY_REPLAY_ASYNC_OK", len(checks), flush=True)
