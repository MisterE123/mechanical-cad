"""Actual .blend load and disable retain supervision for delayed job cleanup.

Controlled process completion isolates registration/lifecycle behavior; the
separate transport suite owns real child-process cancellation/reaping coverage.
Run with native Blender --background --factory-startup --python-exit-code 1.
"""

import json
import os
import sys
import tempfile
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
from mechanical_cad_blender import (  # noqa: E402
    document_state,  # noqa: E402
    register,
    unregister,
)

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
with patch.object(pending, "_JOB_FACTORY", SlowCleanup):
    handle = pending.prepare(bpy.context, "assembly_check")
check(
    not ui.cancel_all("Delayed cleanup before file load"),
    "incomplete cleanup registers supervision",
)
with tempfile.TemporaryDirectory(prefix="mcad-load-supervisor-") as folder:
    path = str(Path(folder) / "pending.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
check(bpy.app.timers.is_registered(ui._supervise), "supervisor survives actual file load")
check(
    handle._detached and set(handle._transaction) == {"key", "snapshot"},
    "old transaction sheds every RNA reference",
)
check(handle._phase == "cancelling" and not handle.done, "unreaped old handle stays cancelling")
check(len(pending._ACTIVE) == 1 and len(state._BUSY) == 1, "unreaped ownership retained")
check(ui._supervise() == 0.1, "post-load supervisor continues while cleanup pending")
loaded = bpy.context.scene.mechanical_cad_assembly
check(loaded.report_json == saved_evidence, "load retains exact historical evidence")
check(loaded.document_json == saved_assembly, "load retains exact canonical assembly")
check(not state.report_is_current(bpy.context), "loaded historical report has no runtime trust")
check(loaded.verification_status == "STALE", "loaded historical report explicitly stale")
handle._job.state = "cancelled"
check(ui._supervise() is None, "supervisor stops after terminal cleanup")
check(not pending._ACTIVE and not state._BUSY, "post-load cleanup releases all old ownership")
check(handle.done and handle._job.consumed == 0, "old response never consumed or published")
if bpy.app.timers.is_registered(ui._supervise):
    bpy.app.timers.unregister(ui._supervise)
# Also exercise delayed cleanup after Scene properties/classes are unregistered.
state.replay(bpy.context)
with patch.object(pending, "_JOB_FACTORY", SlowCleanup):
    disabled = pending.prepare(bpy.context, "assembly_check")
unregister()
check(
    disabled._detached and set(disabled._transaction) == {"key", "snapshot"},
    "disable detaches state before freeing RNA",
)
check(not hasattr(bpy.types.Scene, "mechanical_cad_assembly"), "disable removes Scene storage")
check(bpy.app.timers.is_registered(ui._supervise), "disable retains cleanup supervisor")
check(ui._supervise() == 0.1, "supervisor works without addon Scene storage")
disabled._job.state = "cancelled"
check(ui._supervise() is None, "disabled supervisor stops after terminal cleanup")
check(not pending._ACTIVE and not state._BUSY, "disable cleanup releases all old ownership")
check(disabled._job.consumed == 0, "disabled late response never consumed")
if bpy.app.timers.is_registered(ui._supervise):
    bpy.app.timers.unregister(ui._supervise)
print("ASSEMBLY_JOB_LOAD_SMOKE_OK", len(checks))
