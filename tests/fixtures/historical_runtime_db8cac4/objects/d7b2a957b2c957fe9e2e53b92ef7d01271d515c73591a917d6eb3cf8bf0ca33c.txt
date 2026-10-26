"""Actual native Undo detaches old RNA while delayed job cleanup continues.

Controlled process completion isolates registration/lifecycle behavior; the
separate transport suite owns real child-process cancellation/reaping coverage.
Run with native Blender --background --factory-startup --python-exit-code 1.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import assembly_job_ui as ui  # noqa: E402
from mechanical_cad_blender import assembly_pending as pending  # noqa: E402
from mechanical_cad_blender import assembly_state as state  # noqa: E402
from mechanical_cad_blender import document_state, register, unregister  # noqa: E402

checks = []


def check(value, label):
    assert value, label
    checks.append(label)


class SlowCleanup:
    def __init__(self, prepared, selection, *, owner_token):
        self.state = "created"
        self.consumed = 0

    @property
    def done(self):
        return self.state == "cancelled"

    def start(self, current_selection):
        self.state = "running"
        return self

    def cancel(self):
        self.state = "cancelling"
        return True

    def poll(self, current_selection):
        return self.state

    def wait(self, timeout=None):
        return False

    def result(self, current_selection, *, owner_token):
        self.consumed += 1
        raise AssertionError("Lifecycle maintenance must never consume a response")


register()
scene = bpy.context.scene
assembly = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
document_state._populate_document(scene, assembly["part_sources"][0]["document"])
state.commit_candidate(bpy.context, assembly)
state.check(bpy.context)
check(state.report_is_current(bpy.context), "accepted report initially current")
saved_evidence = scene.mechanical_cad_assembly.report_json
saved_assembly = scene.mechanical_cad_assembly.document_json
bpy.context.preferences.edit.use_global_undo = True
bpy.ops.ed.undo_push(message="Baseline assembly")
scene["audit_change"] = 1
bpy.ops.ed.undo_push(message="Unrelated native change")
with patch.object(pending, "_JOB_FACTORY", SlowCleanup):
    handle = pending.prepare(bpy.context, "assembly_check")
check(bpy.ops.ed.undo() == {"FINISHED"}, "native Undo executes")
check(handle._phase == "cancelling" and handle._detached, "native Undo detaches delayed job")
check(bpy.app.timers.is_registered(ui._supervise), "native Undo keeps supervision")
check(not state.report_is_current(bpy.context), "native Undo does not restore report trust")
check(
    bpy.context.scene.mechanical_cad_assembly.verification_status == "STALE",
    "native Undo makes evidence explicitly stale",
)
handle._job.state = "cancelled"
check(ui._supervise() is None, "native Undo delayed cleanup completes")
check(not pending._ACTIVE and not state._BUSY, "native Undo releases old ownership")
check(handle._job.consumed == 0, "native Undo never consumes old result")
if bpy.app.timers.is_registered(ui._supervise):
    bpy.app.timers.unregister(ui._supervise)
unregister()
print("ASSEMBLY_JOB_UNDO_SMOKE_OK", len(checks))
