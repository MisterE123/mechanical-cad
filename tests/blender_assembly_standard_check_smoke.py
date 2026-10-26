"""Bounded native first-check setup; background is not interactive GUI/Undo QA."""

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
    assembly_job_ui,
    assembly_pending,
    assembly_state,
    assembly_verification_ui,
    execution_lease,
    register,
)
from mechanical_cad_blender.assembly_operator_helpers import AssemblyEdit  # noqa: E402


class MCAD_OT_standard_check_invoke_probe(
    assembly_job_ui.AssemblyJobMixin, AssemblyEdit, bpy.types.Operator
):
    """Background bpy.ops bypasses invoke; explicitly enter the production method."""

    bl_idname = "mcad.standard_check_invoke_probe"
    bl_label = "Native Check Invoke Probe"

    def execute(self, context):
        implementation = assembly_verification_ui.MCAD_OT_assembly_check
        if not self._asynchronous:
            return implementation.invoke(self, context, None)
        return implementation.execute(self, context)


register()
bpy.utils.register_class(MCAD_OT_standard_check_invoke_probe)
state = bpy.context.scene.mechanical_cad_assembly
data = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
data["verification_presets"] = []
data["active_verification_preset"] = None
assembly_state.commit_candidate(bpy.context, data)
state.document_path = "/saved/first-check.mcad-assembly.json"
baseline = state.document_json


def drain(operator):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = operator.modal(bpy.context, SimpleNamespace(type="TIMER", value="NOTHING"))
        if result in ({"FINISHED"}, {"CANCELLED"}):
            return result
        time.sleep(0.02)
    raise AssertionError("Standard setup timeout")


def start():
    assert bpy.ops.mcad.assembly_standard_check_setup() == {"RUNNING_MODAL"}
    return assembly_job_ui._OPERATORS[-1]


def rejected():
    try:
        result = bpy.ops.mcad.assembly_standard_check_setup()
    except RuntimeError:
        return
    assert result == {"CANCELLED"}


operator = start()
rejected()  # Repeated click must not revoke the original owner.
assert not operator._pending.done
assembly_pending.cancel(operator._pending, "Cancel first setup")
assert drain(operator) == {"CANCELLED"}
assert state.document_json == baseline and not execution_lease.is_busy()

operator = start()
operator._pending._job.wait(60)
assembly_state.begin_interaction()  # Even unchanged bytes cannot reuse stale authority.
assert drain(operator) == {"CANCELLED"}
assert state.document_json == baseline and not execution_lease.is_busy()

operator = start()
assert drain(operator) == {"FINISHED"}
saved = assembly_state.read_assembly(state)
preset = saved["verification_presets"][0]
assert saved["active_verification_preset"] == preset["id"]
assert preset["kind"] == "interference_only" and preset["requirements"] == []
assert state.document_path == "/saved/first-check.mcad-assembly.json"
assert assembly_state.display_is_current(bpy.context)
assert not assembly_state.report_is_current(bpy.context)
accepted = state.document_json
rejected()
assert state.document_json == accepted
assert bpy.ops.mcad.standard_check_invoke_probe() == {"RUNNING_MODAL"}
operator = assembly_job_ui._OPERATORS[-1]
try:
    repeat = bpy.ops.mcad.standard_check_invoke_probe()
except RuntimeError:
    repeat = {"CANCELLED"}
assert repeat == {"CANCELLED"}
assert drain(operator) == {"FINISHED"}
assert assembly_state.report_is_current(bpy.context)
assert state.report_preset_id == preset["id"]
assert state.report_document_json == accepted
assert json.loads(state.report_json)["report"]["verification_basis"]["configured"]
print("STANDARD_CHECK_SMOKE_OK", flush=True)
