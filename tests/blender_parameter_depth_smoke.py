"""Real RNA depth intent dispatch; actual GUI and kernel checks are separate."""

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import document_state, register, solid_operators, unregister  # noqa: E402

original_invoke = solid_operators.MCAD_OT_edit_solid_feature.invoke
original_execute = solid_operators.MCAD_OT_edit_solid_feature.execute
case = "shared"
captured = []


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


def run(self, context):
    assert original_invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
    assert self.depth_edit_scope == "FEATURE"
    assert self.depth_parameter_name == "height"
    assert self.length == "height"
    self.depth_parameter_value = "12"
    self.length = "" if case == "shared" else "14"
    self.depth_edit_scope = "PARAMETER" if case == "shared" else "FEATURE"
    if case == "unchanged":
        self.depth_edit_scope = "PARAMETER"
        self.depth_parameter_value = str(document["parameters"]["height"])
    if case == "stale":
        self.original_json = "{}"
    with patch.object(solid_operators, "_commit_candidate", side_effect=lambda c, d, *a, **kw: captured.append(copy.deepcopy(d)) or True):
        with patch.object(solid_operators, "_reject_candidate", return_value={"CANCELLED"}):
            return original_execute(self, context)


solid_operators.MCAD_OT_edit_solid_feature.execute = run
register()
state = bpy.context.scene.mechanical_cad
document = json.loads((ROOT / "examples/drilled_plate.mcad.json").read_text())
feature = next(f for f in document["features"] if f["kind"] == "extrude" and f["params"]["length"] == "height")
document_state._populate_document(bpy.context.scene, document)
before = state.document_json
for case in ("shared", "feature", "unchanged", "stale"):
    captured.clear()
    result = bpy.ops.mcad.edit_solid_feature(feature_id=feature["id"])
    assert state.document_json == before
    if case == "stale":
        assert result == {"CANCELLED"} and not captured
        continue
    assert result == {"FINISHED"} and len(captured) == 1
    candidate = captured[0]
    pad = next(f for f in candidate["features"] if f["id"] == feature["id"])
    if case == "shared":
        assert candidate["parameters"]["height"] == "12"
        assert pad["params"]["length"] == "height"
    elif case == "feature":
        assert candidate["parameters"] == document["parameters"]
        assert str(pad["params"]["length"]) == "14"
    else:
        assert candidate["parameters"] == document["parameters"]
        assert type(candidate["parameters"]["height"]) is type(document["parameters"]["height"])
        assert pad["params"]["length"] == "height"
unregister()
print("PARAMETER_DEPTH_SMOKE_OK")
