"""Native complete-pair Apply, rejection, Cancel and gear-only Part opening."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_job_ui,  # noqa: E402
    assembly_state,
    register,  # noqa: E402
)
from mechanical_cad_blender.gear_pair_ui import MCAD_OT_gear_pair  # noqa: E402

register()


def apply(**params):
    result = bpy.ops.mcad.gear_pair(**params)
    if result != {"RUNNING_MODAL"}:
        return result
    operator = assembly_job_ui._OPERATORS[-1]
    deadline = time.monotonic() + 120
    while result == {"RUNNING_MODAL"}:
        assert time.monotonic() < deadline
        result = operator.modal(bpy.context, SimpleNamespace(type="TIMER", value="NOTHING"))
        time.sleep(0.02)
    return result


state = bpy.context.scene.mechanical_cad_assembly
working = bpy.context.scene.mechanical_cad
before = working.document_json
started = time.monotonic()
assert apply() == {"FINISHED"}
print(f"GEAR_PAIR_APPLY_SECONDS: {time.monotonic() - started:.3f}", flush=True)
accepted = state.document_json
model = json.loads(accepted)
assert working.document_json == before
assert assembly_state.display_is_current(bpy.context)
assert len(model["parts"]) == 3 and len(model["joints"]) == 2
assert model["gear_relations"][0]["ratio"] == -0.5


def rejects(**params):
    try:
        assert apply(**params) == {"CANCELLED"}
    except RuntimeError:
        pass
    assert state.document_json == accepted
    assert working.document_json == before
    assert assembly_state.display_is_current(bpy.context)


rejects()  # No silent Assembly overwrite.
rejects(replace_existing=True, teeth_a=5)
rejects(replace_existing=True, bore_b="1000")
rejects(
    replace_existing=True,
    teeth_a=8,
    teeth_b=8,
    pressure_angle="30",
    bore_a="0",
    bore_b="0",
    pair_backlash="2",
    clearance="0.5",
)
# Invalid root-tip geometry is rejected by full native replay (not local input validation).
# The defaults above are unchanged after each failure.
MCAD_OT_gear_pair.cancel(SimpleNamespace(_pending=None, _cleanup_ui=lambda: None), bpy.context)
assert state.document_json == accepted
# Existing confirmed source-open path never copies the fixture into the gear Part.
assert bpy.ops.mcad.assembly_open_part(part_id="part_1", confirmed=True) == {"FINISHED"}
part = json.loads(working.document_json)
assert len(part["features"]) == 1 and part["features"][0]["kind"] == "spur_gear"
assert state.document_json == accepted
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "gear_a.stl"
    assert bpy.ops.mcad.export_stl(filepath=str(path)) == {"FINISHED"}
    assert path.stat().st_size > 84
    assert state.document_json == accepted
print(
    "GEAR_PAIR_SMOKE_OK: native Apply, validation failure atomicity, overwrite refusal, Cancel, gear-only Part open and STL"
)
