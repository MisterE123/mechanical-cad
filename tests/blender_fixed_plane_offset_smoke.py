"""Focused native copied-plane offset/guards/rollback and save for reopen.

Load the copied-plane fixture blend. Dialog dispatch is simulated in background;
this establishes native/RNA lifecycle evidence, not interactive GUI usability.
"""

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
    fixed_plane_edit,
    history_operators,
    register,
    unregister,
)
from mechanical_cad_blender.fixed_plane_edit import offset_candidate  # noqa: E402

operator = history_operators.MCAD_OT_offset_fixed_sketch_plane
original_execute = operator.execute
scenario = "apply"


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


def dispatch(self, context):
    assert operator.invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
    self.offset = "-0.5 in"
    state = context.scene.mechanical_cad
    if scenario == "cancel":
        return {"CANCELLED"}
    if scenario == "zero":
        self.offset = "-0 mm"
    if scenario == "stale":
        state.document_json += " "
        try:
            return original_execute(self, context)
        finally:
            state.document_json = state.document_json[:-1]
    if scenario == "selection":
        state.feature_index = 0
        try:
            return original_execute(self, context)
        finally:
            state.feature_index = len(state.features) - 1
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
assert document_state.regenerate(context)
state.feature_index = len(state.features) - 1
# Poll tooltips explain the selected target without changing eligibility.
state.feature_index = 0
with patch.object(operator, "poll_message_set") as message:
    assert not operator.poll(context)
    assert "unlinked constrained sketch" in message.call_args.args[0]
with patch.object(history_operators, "_state", return_value=SimpleNamespace(
    document_json=state.document_json, feature_index=0, features=[]
)):
    with patch.object(operator, "poll_message_set") as message:
        assert not operator.poll(context)
        assert "Feature History" in message.call_args.args[0]
state.feature_index = len(state.features) - 1
with patch.object(document_state, "has_staged_edit", return_value=True):
    with patch.object(operator, "poll_message_set") as message:
        assert not operator.poll(context)
        assert "proposed edit" in message.call_args.args[0]
with patch.object(fixed_plane_edit, "fixed_sketch", side_effect=ValueError("Attached sketches and linked projections cannot use a fixed plane offset.")):
    with patch.object(operator, "poll_message_set") as message:
        assert not operator.poll(context)
        assert "linked projections" in message.call_args.args[0]
assert operator.poll(context)
before = state.document_json
original = json.loads(before)
feature = original["features"][-1]
assert feature["sketch"]["plane"]["id"] == "copied_plane"
for scenario in ("cancel", "zero", "stale", "selection", "busy", "draft", "staged", "failure", "selection_callback_failure"):
    try:
        result = bpy.ops.mcad.offset_fixed_sketch_plane()
    except RuntimeError as exc:
        assert scenario not in {"cancel", "zero"}, str(exc)
    else:
        assert result == ({"FINISHED"} if scenario == "zero" else {"CANCELLED"}), (scenario, result)
    assert state.document_json == before, scenario
    assert document_state.current_part_result(context) is not None, scenario
    assert state.features[state.feature_index].feature_id == feature["id"], scenario
scenario = "apply"
bpy.ops.ed.undo_push(message="Before fixed plane offset")
assert bpy.ops.mcad.offset_fixed_sketch_plane() == {"FINISHED"}
expected = offset_candidate(original, feature["id"], "-0.5 in")
assert json.loads(state.document_json) == expected
assert state.features[state.feature_index].feature_id == feature["id"]
assert state.active_feature == original["active_feature"]
assert operator.poll(context)
scenario = "cancel"
assert bpy.ops.mcad.offset_fixed_sketch_plane() == {"CANCELLED"}
accepted = state.document_json
bpy.ops.ed.undo_push(message="After fixed plane offset")
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
output = os.environ.get("MCAD_FIXED_BLEND", "/tmp/mcad_fixed_plane.blend")
Path(output + ".plane.json").write_text(json.dumps(expected["features"][-1]["sketch"]["plane"]))
bpy.ops.wm.save_as_mainfile(filepath=output)
print("FIXED_PLANE_OFFSET_NATIVE_OK", flush=True)
unregister()
