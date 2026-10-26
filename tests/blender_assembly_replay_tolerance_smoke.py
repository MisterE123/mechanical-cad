"""Bounded native Load/edit/save policy gate. Optional complex source via environment."""

import json
import os
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_state,  # noqa: E402
    register,  # noqa: E402
)

register()
state = bpy.context.scene.mechanical_cad_assembly
source = Path(
    os.environ.get("MCAD_TOLERANCE_MODEL", ROOT / "examples/reused_blocks.mcad-assembly.json")
)
complex_source = bool(os.environ.get("MCAD_TOLERANCE_MODEL"))
checks = []
original_objects = list(bpy.context.scene.objects)


def check(value, name):
    assert value, name
    checks.append(name)
    print("POLICY_CHECK " + name, flush=True)


def refused(call, name):
    before = state.document_json
    try:
        result = call()
        assert result == {"CANCELLED"}, name
    except RuntimeError:
        pass
    check(before == state.document_json, name)


if complex_source:
    refused(
        lambda: bpy.ops.mcad.assembly_load(filepath=str(source)),
        "default refuses high stored tolerance",
    )
check(
    bpy.ops.mcad.assembly_load(
        filepath=str(source), override_replay_tolerance=True, replay_tolerance="1e-5"
    )
    == {"FINISHED"},
    "explicit native Load",
)
check(json.loads(state.document_json)["replay_tolerance_mm"] == 1e-5, "canonical saved policy")
check(assembly_state.display_is_current(bpy.context), "fresh display")
check(state.verification_status == "UNCHECKED", "not certified")
report = json.loads(state.report_json)
check(
    report["report"]["effective_policy"]["linear_tolerance_mm"] == 1e-5, "actual effective policy"
)
check(not report["report"]["passed"], "replay never passes verification")
refused(
    lambda: bpy.ops.mcad.assembly_replay_tolerance(tolerance="nan"),
    "invalid policy preserves accepted state",
)
if complex_source:
    refused(
        lambda: bpy.ops.mcad.assembly_replay_tolerance(tolerance="1e-6"),
        "too strict replay refuses atomically",
    )
assembly_state.check(bpy.context)
check(assembly_state.report_is_current(bpy.context), "fresh check evidence current before edit")
check(
    bpy.ops.mcad.assembly_replay_tolerance(tolerance="2e-5") == {"FINISHED"},
    "edit policy and freshly replay",
)
check(state.verification_status == "UNCHECKED", "policy edit clears check authority")
check(not assembly_state.report_is_current(bpy.context), "old check authority revoked")
with tempfile.TemporaryDirectory() as temp:
    saved = Path(temp) / "saved.mcad-assembly.json"
    check(
        bpy.ops.mcad.assembly_save(filepath=str(saved)) == {"FINISHED"}, "native save revalidates"
    )
    check(json.loads(saved.read_text())["replay_tolerance_mm"] == 2e-5, "portable saved policy")
    check(
        bpy.ops.mcad.assembly_load(filepath=str(saved), override_replay_tolerance=False)
        == {"FINISHED"},
        "reload uses saved tolerance",
    )
    check(
        json.loads(state.report_json)["report"]["effective_policy"]["linear_tolerance_mm"] == 2e-5,
        "reload effective policy",
    )
check(
    all(obj.name in bpy.context.scene.objects for obj in original_objects),
    "unrelated scene objects preserved",
)
print("ASSEMBLY_REPLAY_TOLERANCE_OK " + json.dumps(checks))
