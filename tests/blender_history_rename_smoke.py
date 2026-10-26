"""Native rename/Cancel/no-op/guards/rollback and Undo/Redo; not GUI evidence."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    execution_lease,
        history_operators,
    register,
    unregister,
)
from mechanical_cad_blender.history_edit import rename_feature  # noqa: E402

operator = history_operators.MCAD_OT_rename_history_feature
original_execute = operator.execute
scenario = "apply"


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


def dispatch(self, context):
    assert operator.invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
    self.feature_label = "Mounting plate outline"
    state = context.scene.mechanical_cad
    if scenario == "cancel":
        return {"CANCELLED"}
    if scenario == "zero":
        self.feature_label = self._document["features"][0]["label"]
        with patch.object(document_state, "_commit_candidate_locked", side_effect=AssertionError("no-op replayed")):
            return original_execute(self, context)
    if scenario == "invalid":
        self.feature_label = ""
    if scenario == "stale":
        state.document_json += " "
        try:
            return original_execute(self, context)
        finally:
            state.document_json = state.document_json[:-1]
    if scenario == "selection":
        state.feature_index = 1
        try:
            return original_execute(self, context)
        finally:
            state.feature_index = 0
    if scenario == "busy":
        token = execution_lease.try_acquire()
        assert token is not None
        try:
            return original_execute(self, context)
        finally:
            execution_lease.release(token)
    if scenario == "draft":
        state.sketch_draft_json = "{}"
        try:
            return original_execute(self, context)
        finally:
            state.sketch_draft_json = ""
    if scenario == "staged":
        from mechanical_cad_blender import staged_edit_store
        with patch.object(staged_edit_store, "require_none", side_effect=ValueError("pending staged edit")):
            return original_execute(self, context)
    if scenario == "failure":
        with patch.object(document_state, "_apply_result", side_effect=RuntimeError("injected publication failure")):
            return original_execute(self, context)
    if scenario == "selection_callback_failure":
        apply_result = document_state._apply_result

        def fail_after_reselection(context, document, evidence, binding, validate_publication):
            def fail_late():
                validate_publication()
                assert state.features[state.feature_index].feature_id == self._feature_id
                raise RuntimeError("injected failure after sketch reselection")

            return apply_result(context, document, evidence, binding, fail_late)

        with patch.object(document_state, "_apply_result", side_effect=fail_after_reselection):
            return original_execute(self, context)
    return original_execute(self, context)


operator.execute = dispatch
register()
context = bpy.context
state = context.scene.mechanical_cad
fixture = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
document_state._populate_document(context.scene, fixture)
assert document_state.regenerate(context)
state.feature_index = 0
assert operator.poll(context)
def mesh_geometry():
    return sorted((tuple(tuple(vertex.co) for vertex in obj.data.vertices),
                   tuple(tuple(poly.vertices) for poly in obj.data.polygons))
                  for obj in context.scene.objects if obj.type == "MESH" and obj.get("mechanical_cad_owner"))


geometry_before = mesh_geometry()
assert geometry_before
before = state.document_json
original = json.loads(before)
feature = original["features"][0]
for scenario in ("cancel", "zero", "invalid", "stale", "selection", "busy", "draft", "staged", "failure", "selection_callback_failure"):
    try:
        result = bpy.ops.mcad.rename_history_feature()
    except RuntimeError as exc:
        assert scenario not in {"cancel", "zero"}, str(exc)
    else:
        assert result == ({"FINISHED"} if scenario == "zero" else {"CANCELLED"}), (scenario, result)
    assert state.document_json == before, scenario
    assert document_state.current_part_result(context) is not None, scenario
    assert state.features[state.feature_index].feature_id == feature["id"], scenario
scenario = "apply"
bpy.ops.ed.undo_push(message="Before feature rename")
assert bpy.ops.mcad.rename_history_feature() == {"FINISHED"}
expected = rename_feature(original, feature["id"], "Mounting plate outline")
assert json.loads(state.document_json) == expected
assert state.features[state.feature_index].feature_id == feature["id"]
assert state.active_feature == original["active_feature"]
assert operator.poll(context)
assert mesh_geometry() == geometry_before
scenario = "cancel"
assert bpy.ops.mcad.rename_history_feature() == {"CANCELLED"}
accepted = state.document_json
bpy.ops.ed.undo_push(message="After feature rename")
assert bpy.ops.ed.undo() == {"FINISHED"}
state = bpy.context.scene.mechanical_cad
assert state.document_json == before
assert state.features[state.feature_index].feature_id == feature["id"]
assert state.active_feature == original["active_feature"]
assert bpy.ops.ed.redo() == {"FINISHED"}
state = bpy.context.scene.mechanical_cad
assert state.document_json == accepted
assert state.features[state.feature_index].feature_id == feature["id"]
assert state.active_feature == original["active_feature"]
assert document_state.regenerate(context)
print("HISTORY_RENAME_NATIVE_OK", flush=True)
unregister()
