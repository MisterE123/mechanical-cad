"""Background-script adapters for real modal operators, not synchronous bypasses."""

import time
from types import SimpleNamespace

import bpy


def replay_assembly(timeout=120):
    """Start explicit Replay and pump its own guarded owner to a terminal state."""
    from mechanical_cad_blender import assembly_job_ui, assembly_pending

    result = bpy.ops.mcad.assembly_replay()
    if result != {"RUNNING_MODAL"}:
        return result
    operator = assembly_job_ui._OPERATORS[-1]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = operator.modal(bpy.context, SimpleNamespace(type="TIMER", value="NOTHING"))
        if result in ({"FINISHED"}, {"CANCELLED"}):
            return result
        assembly_pending.reap(bpy.context)
        time.sleep(0.02)
    assembly_pending.cancel(operator._pending, "Background test replay timed out")
    raise AssertionError("Explicit Assembly Replay timed out")
