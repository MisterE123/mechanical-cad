"""Native async pair edits, cancellation, stale result and persistence contracts.

Background Blender only; not interactive dialog/Undo qualification.
"""

import json
import math
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
    execution_lease,
    gear_pair,
    register,
)
from mechanical_cad_blender.gear_pair_ui import MCAD_OT_gear_pair  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad_assembly
part = bpy.context.scene.mechanical_cad


def snapshot():
    return (
        state.document_json,
        state.document_path,
        state.report_json,
        state.report_request_json,
        state.report_document_json,
        part.document_json,
        part.repair_intent_json,
        {
            obj.as_pointer()
            for obj in assembly_display.owned_objects(bpy.context.scene, state.owner_id)
        },
    )


def start(**params):
    assert bpy.ops.mcad.gear_pair(**params) == {"RUNNING_MODAL"}
    return assembly_job_ui._OPERATORS[-1]


def drain(operator):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = operator.modal(bpy.context, SimpleNamespace(type="TIMER", value="NOTHING"))
        if result != {"RUNNING_MODAL"}:
            return result
        assembly_pending.reap(bpy.context)
        time.sleep(0.02)
    raise AssertionError("Edit timed out")


original = gear_pair.build_pair()
original["joints"][0]["coordinate"] = 0.21
original["parts"][1]["name"] = "Custom driver name"
assembly_state.commit_candidate(bpy.context, original)
state.document_path = "/saved/my-gears.mcad-assembly.json"
part.repair_intent_json = "untouched dormant intent"
assembly_state.check(bpy.context)
assert assembly_state.report_is_current(bpy.context)
before = snapshot()
# Invoke prefills exact accepted dimensions, with no canonical mutation.
recorded = {}
owner = SimpleNamespace(
    edit_existing=True, _expected=state.document_json, capture_dialog=lambda context: None
)


def dialog(operator, **kwargs):
    recorded.update(kwargs)
    return {"RUNNING_MODAL"}


assert MCAD_OT_gear_pair.invoke(
    owner, SimpleNamespace(window_manager=SimpleNamespace(invoke_props_dialog=dialog)), None
) == {"RUNNING_MODAL"}
assert recorded["title"] == "Edit Gear Pair"
assert owner.module == "2.0" and owner.teeth_a == 20 and owner.teeth_b == 40
assert owner.name == original["name"]
assert snapshot() == before
changes = dict(edit_existing=True, module="1.5", teeth_a=24, teeth_b=36, bore_b="6")
operator = start(**changes)
assert snapshot() == before
assert assembly_pending.status(bpy.context.scene)["editing"]
assert bpy.ops.mcad.assembly_cancel_check() == {"FINISHED"}
assert drain(operator) == {"CANCELLED"}
assert snapshot() == before
assert assembly_state.report_is_current(bpy.context)
print("GEAR_EDIT_CANCEL_OK", flush=True)

# Ready results are still provisional. A newer editor revokes publication.
operator = start(**changes)
operator._pending._job.wait(120)
assert operator._pending._job.state == "ready"
assembly_state.begin_interaction()
assert drain(operator) == {"CANCELLED"}
assert snapshot() == before
assert not execution_lease.is_busy()
print("GEAR_EDIT_STALE_OK", flush=True)

# Native-only invalid tooth/root construction: local parameters pass, replay fails.
operator = start(
    edit_existing=True,
    teeth_a=8,
    teeth_b=8,
    pressure_angle="30",
    bore_a="0",
    bore_b="0",
    pair_backlash="2",
    clearance="0.5",
)
assert drain(operator) == {"CANCELLED"}
assert snapshot() == before
assert assembly_state.report_is_current(bpy.context)
print("GEAR_EDIT_NATIVE_FAILURE_OK", flush=True)

operator = start(**changes)
assert drain(operator) == {"FINISHED"}
updated = json.loads(state.document_json)
assert updated["id"] == original["id"]
assert updated["parts"][1]["name"] == "Custom driver name"
assert updated["joints"][0]["coordinate"] == 0.21
assert updated["parts"][0]["mate_frames"][1]["placement"]["xyz_mm"] == [45, 0, 0]
assert updated["gear_relations"][0]["ratio"] == -24 / 36
assert updated["gear_relations"][0]["offset_rad"] == math.pi + math.pi / 36
assert state.document_path == before[1]
assert (part.document_json, part.repair_intent_json) == before[5:7]
assert state.verification_status == "UNCHECKED"
assert not assembly_state.report_is_current(bpy.context)
assert assembly_state.display_is_current(bpy.context)
assert gear_pair.recognize_pair(updated)["module"] == 1.5
assert not execution_lease.is_busy()
print("GEAR_EDIT_ACCEPT_OK", flush=True)

# Repeated edit is recognized, IDs stable, no accumulated shaft/phase offsets.
operator = start(edit_existing=True, module="2", teeth_a=20, teeth_b=40)
assert drain(operator) == {"FINISHED"}
restored = json.loads(state.document_json)
assert gear_pair.recognize_pair(restored)["module"] == 2
assert restored["parts"][0]["mate_frames"][1]["placement"]["xyz_mm"] == [60, 0, 0]
assert restored["joints"][0]["coordinate"] == 0.21
assert restored["id"] == original["id"]
print("GEAR_PAIR_EDIT_SMOKE_OK", flush=True)
