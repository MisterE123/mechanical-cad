"""Real source-replay comparison rejects before display stage; no accepted edit."""

import copy
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
OUT = Path(os.environ["MCAD_SOURCE_CONTRACT_OUT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import assembly_display, assembly_edit, assembly_state, register  # noqa: E402
from mechanical_cad_blender.assembly_source_preview_contract import source_preview_fingerprint  # noqa: E402

register()
assert bpy.ops.mcad.assembly_load(
    filepath=str(ROOT / "examples/reused_blocks.mcad-assembly.json")
) == {"FINISHED"}
state = bpy.context.scene.mechanical_cad_assembly
canonical = state.document_json
original = json.loads(canonical)
report = state.report_json
objects = [
    (
        obj.as_pointer(),
        obj.data.as_pointer() if obj.data else 0,
        tuple(tuple(row) for row in obj.matrix_world),
    )
    for obj in assembly_display.owned_objects(bpy.context.scene, state.owner_id)
]
response = assembly_state.current_display_response(bpy.context)
expected = source_preview_fingerprint(response)
source = copy.deepcopy(original["part_sources"][0]["document"])
source["parameters"]["width"] = 20
candidate, affected = assembly_edit.update_source(original, source)
assert set(affected) == {"root", "a", "b"}
with patch.object(
    assembly_display, "stage", side_effect=AssertionError("Mismatch reached display stage")
) as stage:
    try:
        assembly_state.commit_candidate(
            bpy.context, candidate, expected_json=canonical, expected_source_preview=expected
        )
    except assembly_state.bridge.BridgeError as exc:
        assert "differs from the displayed preview" in str(exc), str(exc)
    else:
        raise AssertionError("Changed source reused old preview")
    assert stage.call_count == 0
assert state.document_json == canonical and state.report_json == report
assert objects == [
    (
        obj.as_pointer(),
        obj.data.as_pointer() if obj.data else 0,
        tuple(tuple(row) for row in obj.matrix_world),
    )
    for obj in assembly_display.owned_objects(bpy.context.scene, state.owner_id)
]
assert assembly_state.display_is_current(bpy.context)
assert not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "native-contract.json").write_text(
    json.dumps(
        {
            "ok": True,
            "stage_calls": 0,
            "canonical_unchanged": True,
            "report_unchanged": True,
            "display_identity_pose_unchanged": True,
            "current_display_retained": True,
            "affected": affected,
            "expected_source_preview": expected,
        },
        indent=2,
    )
)
print("ASSEMBLY_SOURCE_PREVIEW_CONTRACT_OK", flush=True)
