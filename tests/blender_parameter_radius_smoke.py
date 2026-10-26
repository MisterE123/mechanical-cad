"""Real RNA radius intent dispatch; actual GUI and kernel checks are separate."""

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
selection_case = None
refusal_case = None


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)



def capture_commit(context, candidate, *args, **kwargs):
    captured.append(copy.deepcopy(candidate))
    if refusal_case is not None:
        error = document_state.bridge.CandidateExpressionError(
            "Unknown radius parameter", feature_id="other" if refusal_case == "wrong-id" else feature["id"],
            code="unknown_parameter",
        )
        if refusal_case == "wrong-code":
            error.code = "kernel_error"  # Defensive dispatch check, not a valid seam output.
        if refusal_case == "changed":
            context.scene.mechanical_cad.document_json += " "
        raise error
    if selection_case == "failed":
        return False
    if selection_case is not None:
        # Simulate fresh publication rows and its default active-output selection.
        state = context.scene.mechanical_cad
        rows = list(candidate["features"])
        if selection_case == "reordered":
            rows = rows[2:] + rows[:2]  # Edited circle moves from index 2 to 0.
        elif selection_case == "missing":
            rows = [row for row in rows if row["id"] != feature["id"]]
        state.features.clear()
        for source in rows:
            row = state.features.add()
            row.feature_id = source["id"]
            row.label = source["label"]
        state.feature_index = next(i for i, row in enumerate(rows) if row["id"] == candidate["active_feature"])
    return True


def run(self, context):
    # Isolated RNA face-choice fixture; exact face geometry is verified separately.
    faces = {"features": [{"id": "pad", "topology": [{
        "id": "face:top", "kind": "face", "signature": {"surface": "plane"},
        "provenance": {"semantic_status": "stable"},
    }]}]}
    with patch.object(document_state, "current_part_result", return_value=faces):
        assert original_invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
    assert self.radius_edit_scope == "FEATURE"
    assert self.radius_parameter_name == "hole_radius"
    assert self.radius == "hole_radius"
    self.radius_parameter_value = "6"
    self.radius = "" if case == "shared" else "5"
    self.radius_edit_scope = "PARAMETER" if case == "shared" else "FEATURE"
    if case == "unchanged":
        self.radius_edit_scope = "PARAMETER"
        self.radius_parameter_value = str(document["parameters"]["hole_radius"])
    if case == "support":
        self.radius_edit_scope = "PARAMETER"
        self.radius_parameter_value = "6"
        self.support = "pad2"
        with patch.object(document_state, "current_part_result", return_value={"features": [{
            "id": "pad2", "topology": [{"id": "face:new", "kind": "face",
            "signature": {"surface": "plane"}, "provenance": {"semantic_status": "stable"}}],
        }]}):
            self.support_face = "face:new"
    if refusal_case is not None:
        if case == "shared":
            self.radius_parameter_value = "bad_radius"
        else:
            self.radius = "bad_radius"
    if refusal_case in {"resume", "resume-support"}:
        from mechanical_cad_blender.solid_dialog_values import circle_expression_resume_values

        with patch.object(document_state, "current_part_result", return_value=faces):
            if refusal_case == "resume-support":
                faces["features"].append({"id": "pad2", "topology": [{
                    "id": "face:new", "kind": "face", "signature": {"surface": "plane"},
                    "provenance": {"semantic_status": "stable"},
                }]})
                self.support = "pad2"
                self.support_face = "face:new"
            values = circle_expression_resume_values(self)
            if refusal_case == "resume-support":
                # Adversarial JSON order: real RNA enum depends on self.support.
                values = {"support_face": values.pop("support_face"), **values}
                assert list(values)[0] == "support_face"
            self.resume_json = json.dumps(values)
            self.expression_retry = True
            self.allow_shared_extrusion = True  # Never restored as authority.
            assert original_invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
        assert not self.allow_shared_extrusion
        if refusal_case == "resume-support":
            with patch.object(document_state, "current_part_result", return_value=faces):
                assert self.support == "pad2" and self.support_face == "face:new"
                assert [row[0] for row in solid_operators._face_choices(self, context)] == ["face:new"]
        assert self.radius_edit_scope == ("PARAMETER" if case == "shared" else "FEATURE")
        assert (self.radius_parameter_value if case == "shared" else self.radius) == "bad_radius"
    if case == "stale":
        self.original_json = "{}"
    with patch.object(solid_operators, "_commit_candidate", side_effect=capture_commit):
        with patch.object(solid_operators, "_reject_candidate", return_value={"CANCELLED"}):
            faces["features"].append({"id": "pad2", "topology": [{
                "id": "face:new", "kind": "face", "signature": {"surface": "plane"},
                "provenance": {"semantic_status": "stable"},
            }]})
            with patch.object(document_state, "current_part_result", return_value=faces):
                return original_execute(self, context)


solid_operators.MCAD_OT_edit_solid_feature.execute = run
register()
state = bpy.context.scene.mechanical_cad
document = json.loads((ROOT / "examples/drilled_plate.mcad.json").read_text())
feature = next(f for f in document["features"] if f["kind"] == "sketch_circle" and f["params"]["radius"] == "hole_radius")
for circle_kind in ("sketch_circle", "sketch_face_circle"):
    feature["kind"] = circle_kind
    if circle_kind == "sketch_face_circle":
        feature["inputs"] = {"support": "pad"}
        feature["support_face"] = "face:top"
    second = copy.deepcopy(next(f for f in document["features"] if f["id"] == "pad"))
    second["id"] = "pad2"
    if not any(f["id"] == "pad2" for f in document["features"]):
        document["features"].append(second)
    document_state._populate_document(bpy.context.scene, document)
    before = state.document_json
    for case in ("shared", "feature", "unchanged", "stale", "support"):
        if case == "support" and circle_kind != "sketch_face_circle":
            continue
        captured.clear()
        result = bpy.ops.mcad.edit_solid_feature(feature_id=feature["id"])
        assert state.document_json == before
        if case == "stale":
            assert result == {"CANCELLED"} and not captured
            continue
        assert result == {"FINISHED"} and len(captured) == 1
        candidate = captured[0]
        pad = next(f for f in candidate["features"] if f["id"] == feature["id"])
        if case in {"shared", "support"}:
            if case == "support":
                assert pad["inputs"]["support"] == "pad2"
                assert pad["support_face"] == "face:new"
            assert candidate["parameters"]["hole_radius"] == "6"
            assert pad["params"]["radius"] == "hole_radius"
        elif case == "feature":
            assert candidate["parameters"] == document["parameters"]
            assert str(pad["params"]["radius"]) == "5"
        else:
            assert candidate["parameters"] == document["parameters"]
            assert type(candidate["parameters"]["hole_radius"]) is type(document["parameters"]["hole_radius"])
            assert pad["params"]["radius"] == "hole_radius"

# Explicit edits retain the edited stable ID, independent of row order/output.
document = json.loads((ROOT / "examples/drilled_plate.mcad.json").read_text())
feature = next(f for f in document["features"] if f["kind"] == "sketch_circle")
for selection_case in ("published", "reordered", "missing", "failed"):
    for case in ("shared", "feature", "stale"):
        document_state._populate_document(bpy.context.scene, document)
        state.feature_index = 1  # Deliberately not the explicit edited feature.
        original_index, active = state.feature_index, state.active_feature
        canonical = state.document_json
        captured.clear()
        result = bpy.ops.mcad.edit_solid_feature(feature_id=feature["id"])
        assert state.document_json == canonical and state.active_feature == active
        if case == "stale":
            assert result == {"CANCELLED"} and not captured
            assert state.feature_index == original_index
        else:
            assert result == {"FINISHED"} and len(captured) == 1
            if selection_case == "failed":
                # Failed commit cannot trigger post-success reselection.
                assert state.feature_index == original_index
            elif selection_case == "missing":
                assert state.features[state.feature_index].feature_id == active
            else:
                assert state.features[state.feature_index].feature_id == feature["id"]
                if selection_case == "reordered":
                    assert state.feature_index == 0
print("EDIT_SELECTION_RADIUS_DISPATCH_OK")

# Typed refusal return is restricted to the same direct-circle edit/context.
selection_case = None
for circle_kind in ("sketch_circle", "sketch_face_circle"):
    feature["kind"] = circle_kind
    if circle_kind == "sketch_face_circle":
        feature["inputs"] = {"support": "pad"}
        feature["support_face"] = "face:top"
    if circle_kind == "sketch_face_circle":
        second = copy.deepcopy(next(f for f in document["features"] if f["id"] == "pad"))
        second["id"] = "pad2"
        document["features"].append(second)
    for refusal_case in ("same", "resume", "resume-support", "wrong-id", "wrong-code", "changed"):
        if refusal_case == "resume-support" and circle_kind != "sketch_face_circle":
            continue
        for case in ("shared", "feature"):
            document_state._populate_document(bpy.context.scene, document)
            state.feature_index = 1
            canonical, active = state.document_json, state.active_feature
            queued = []
            captured.clear()
            with patch.object(solid_review, "queue_consent_reopen", side_effect=lambda context, values, captured_queue=queued, **kw: captured_queue.append((values, kw)) or True):
                result = bpy.ops.mcad.edit_solid_feature(feature_id=feature["id"])
            assert result == {"CANCELLED"} and len(captured) == 1
            assert state.feature_index == 1 and state.active_feature == active
            assert state.document_json == canonical + (" " if refusal_case == "changed" else "")
            assert len(queued) == (1 if refusal_case in {"same", "resume", "resume-support"} else 0)
            if queued:
                values, options = queued[0]
                assert options == {"expression": True}
                assert values["feature_id"] == feature["id"] and values["original_json"] == canonical
                if refusal_case == "resume-support":
                    assert values["support"] == "pad2" and values["support_face"] == "face:new"
                    candidate_feature = next(row for row in captured[0]["features"] if row["id"] == feature["id"])
                    assert candidate_feature["inputs"]["support"] == "pad2"
                    assert candidate_feature["support_face"] == "face:new"
                assert values["radius_edit_scope"] == ("PARAMETER" if case == "shared" else "FEATURE")
                assert values["radius_parameter_value" if case == "shared" else "radius"] == "bad_radius"
print("CIRCLE_EXPRESSION_REFUSAL_DISPATCH_OK")

unregister()
print("PARAMETER_RADIUS_SMOKE_OK")
