"""Real RNA linked depth intent and independent consent dispatch; actual GUI and kernel checks are separate."""

import copy
import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    register,
    solid_operators,
    solid_review,
    unregister,
)

original_invoke = solid_operators.MCAD_OT_edit_solid_feature.invoke
original_execute = solid_operators.MCAD_OT_edit_solid_feature.execute
case = "shared"
captured = []


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


def run(self, context):
    key = (context.window.as_pointer(), context.scene.as_pointer())
    solid_review._CONSENT_RETURNS[key] = object()
    assert original_invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
    assert key not in solid_review._CONSENT_RETURNS
    if case == "retry-target":
        from mechanical_cad_blender.solid_dialog_values import consent_resume_values

        faces = {"features": [
            {"id": source, "topology": [{"id": face, "kind": "face",
             "signature": {"surface": "plane"}, "provenance": {"semantic_status": "stable"}}]}
            for source, face in (("pad", "face:old"), ("pad2", "face:new"))
        ]}
        with patch.object(document_state, "current_part_result", return_value=faces):
            self.target = "pad2"
            self.end_face = "face:new"
            self.linked_end_condition = "UP_TO_FACE"
            values = consent_resume_values(self)
            values = {"end_face": values.pop("end_face"), **values}
            assert list(values)[0] == "end_face"
            self.resume_json = json.dumps(values)
            self.target = "pad"
            self.end_face = "face:old"
            self.consent_retry = True
            self.allow_shared_extrusion = True
            assert original_invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
            assert self.target == "pad2" and self.end_face == "face:new"
            assert [row[0] for row in solid_operators._end_face_choices(self, context)] == ["NONE", "face:new"]
            assert self.linked_end_condition == "UP_TO_FACE"
            assert not self.allow_shared_extrusion
        return {"CANCELLED"}
    assert self.linked_depth_scope == "FEATURE"
    assert self.depth_parameter_name == "height"
    assert self.linked_length == "height"
    self.depth_parameter_value = "12"
    self.linked_length = "" if case != "feature" else "14"
    self.linked_depth_scope = "FEATURE" if case == "feature" else "PARAMETER"
    self.allow_shared_extrusion = case != "denied"
    if case == "retry":
        from mechanical_cad_blender.solid_dialog_values import consent_resume_values

        self.resume_json = json.dumps(consent_resume_values(self))
        self.consent_retry = True
        assert original_invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
        assert not self.allow_shared_extrusion
        assert self.depth_parameter_value == "12" and self.linked_depth_scope == "PARAMETER"
        self.allow_shared_extrusion = True
    if case == "stale":
        self.original_json = "{}"
    with patch.object(
        solid_operators,
        "_commit_candidate",
        side_effect=lambda c, d, *a, **kw: captured.append(copy.deepcopy(d)) or True,
    ):
        with patch.object(solid_operators, "_reject_candidate", return_value={"CANCELLED"}):
            return original_execute(self, context)


solid_operators.MCAD_OT_edit_solid_feature.execute = run
register()
state = bpy.context.scene.mechanical_cad
document = json.loads((ROOT / "examples/drilled_plate.mcad.json").read_text())
feature = next(f for f in document["features"] if f["kind"] == "cut")
document["features"].append(
    {
        "id": "other",
        "kind": "transform",
        "label": "Other branch",
        "params": {k: 0 for k in ("x", "y", "z", "rx", "ry", "rz")},
        "inputs": {"base": "hole_tool"},
    }
)
document_state._populate_document(bpy.context.scene, document)
before = state.document_json
for case in ("denied", "shared", "feature", "retry", "stale"):
    captured.clear()
    state.feature_index = 1
    selection_before, active_before = state.feature_index, state.active_feature
    result = bpy.ops.mcad.edit_solid_feature(feature_id=feature["id"])
    assert state.document_json == before
    assert state.active_feature == active_before
    if case in {"denied", "stale"}:
        assert result == {"CANCELLED"} and not captured
        assert state.feature_index == selection_before
        continue
    assert result == {"FINISHED"} and len(captured) == 1
    assert state.features[state.feature_index].feature_id == feature["id"]
    candidate = captured[0]
    pad = next(f for f in candidate["features"] if f["id"] == "hole_tool")
    if case in {"shared", "retry"}:
        assert candidate["parameters"]["height"] == "12"
        assert pad["params"]["length"] == "height"
    elif case == "feature":
        assert candidate["parameters"] == document["parameters"]
        assert str(pad["params"]["length"]) == "14"
# Face-first consent payload must restore its owning target before real RNA enum.
case = "retry-target"
second = copy.deepcopy(next(f for f in document["features"] if f["id"] == "pad"))
second["id"] = "pad2"
document["features"].insert(next(i for i, row in enumerate(document["features"]) if row["id"] == "hole_tool"), second)
document_state._populate_document(bpy.context.scene, document)
before = state.document_json
assert bpy.ops.mcad.edit_solid_feature(feature_id=feature["id"]) == {"CANCELLED"}
assert state.document_json == before
print("CONSENT_TARGET_FACE_RESTORE_ORDER_OK")

# Deferred returns are single-shot and revoke on changed/closed context.

for expression in (False, True):
    for changed in (
        "none",
        "document",
        "window",
        "scene",
        "workspace",
        "layer",
        "area",
        "mode",
        "cancel_all",
        "new_editor",
    ):
        callbacks, reopened = [], []
        scene = SimpleNamespace(
            mechanical_cad=SimpleNamespace(document_json="base"), as_pointer=lambda: 2
        )
        area = SimpleNamespace(type="VIEW_3D")
        workspace, layer = object(), object()
        window = SimpleNamespace(
            scene=scene,
            workspace=workspace,
            view_layer=layer,
            screen=SimpleNamespace(areas=[area]),
            as_pointer=lambda: 1,
        )
        context = SimpleNamespace(
            window=window, area=area, scene=scene, workspace=workspace, view_layer=layer, mode="OBJECT"
        )
        fake = SimpleNamespace(
            context=SimpleNamespace(window_manager=SimpleNamespace(windows=[window]), mode="OBJECT"),
            app=SimpleNamespace(
                timers=SimpleNamespace(
                    register=lambda callback, captured=callbacks, **kw: captured.append(callback)
                )
            ),
            ops=SimpleNamespace(
                mcad=SimpleNamespace(
                    edit_solid_feature=lambda *a, captured=reopened, **kw: captured.append(kw)
                )
            ),
        )
        fake.context.temp_override = lambda **kw: nullcontext()
        with (
            patch.object(solid_review, "bpy", fake),
            patch.object(solid_review.execution_lease, "is_busy", return_value=False),
            patch.object(solid_review.execution_lease, "cleanup_message", return_value=None),
        ):
            assert solid_review.queue_consent_reopen(
                context, {"original_json": "base", "feature_id": "cut"}, expression=expression
            )
            if changed == "document":
                scene.mechanical_cad.document_json = "new"
            if changed == "window":
                fake.context.window_manager.windows = []
            if changed == "scene":
                window.scene = object()
            if changed == "workspace":
                window.workspace = object()
            if changed == "layer":
                window.view_layer = object()
            if changed == "area":
                window.screen.areas = []
            if changed == "mode":
                fake.context.mode = "EDIT_MESH"
            if changed == "new_editor":
                solid_review.cancel_consent_reopen(context)
            if changed == "cancel_all":
                solid_review.cancel_all()
            callbacks[0]()
            callbacks[0]()
            assert len(reopened) == (1 if changed == "none" else 0)
            if reopened:
                assert reopened[0]["consent_retry"] is (not expression)
                assert reopened[0]["expression_retry"] is expression

unregister()
print("LINKED_PARAMETER_DEPTH_SMOKE_OK")
