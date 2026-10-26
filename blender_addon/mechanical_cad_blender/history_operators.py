"""Everyday feature-history and named-parameter editing through canonical replay."""

from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from . import execution_lease, workspace
from .common import _state
from .document_state import _commit_candidate, _read_document
from .history_edit import feature_dependants, remove_feature, set_parameter
from .operators import _reject_candidate, _report_result


class _HistoryDialog:
    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and bool(_state(context).document_json)
            and not workspace.has_draft(context)
            and not execution_lease.is_busy()
        )

    def _original(self, context):
        if _state(context).document_json != self.original_json:
            raise ValueError("The document changed while this dialog was open; reopen the tool")
        return _read_document(_state(context))


class MCAD_OT_remove_history_feature(_HistoryDialog, Operator):
    bl_idname = "mcad.remove_history_feature"
    bl_label = "Remove Feature"
    bl_description = "Remove the selected feature; dependant features require an explicit choice. Undo restores the edit"
    bl_options = {"REGISTER", "UNDO"}
    feature_id: StringProperty(options={"HIDDEN"})
    original_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    include_dependants: BoolProperty(name="Also remove listed dependent features", default=False)

    def invoke(self, context, event):
        try:
            state = _state(context)
            if not self.feature_id:
                self.feature_id = state.features[state.feature_index].feature_id
            feature_dependants(_read_document(state), self.feature_id)
            self.original_json = state.document_json
            return context.window_manager.invoke_props_dialog(
                self, width=480, confirm_text="Remove"
            )
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))

    def draw(self, context):
        document = _read_document(_state(context))
        lookup = {f["id"]: f["label"] for f in document["features"]}
        self.layout.label(
            text="Remove: " + lookup.get(self.feature_id, self.feature_id), icon="TRASH"
        )
        dependants = feature_dependants(document, self.feature_id)
        if dependants:
            self.layout.label(text="These features depend on it:", icon="ERROR")
            for identifier in dependants:
                self.layout.label(text=lookup[identifier])
            self.layout.prop(self, "include_dependants")
        self.layout.label(text="Named parameters are kept. Blender Undo restores the edit.")

    def execute(self, context):
        try:
            candidate = remove_feature(
                self._original(context), self.feature_id, include_dependants=self.include_dependants
            )
            return _report_result(
                self, context, _commit_candidate(context, candidate, _state(context).document_path)
            )
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))


class MCAD_OT_named_parameter(_HistoryDialog, Operator):
    bl_idname = "mcad.named_parameter"
    bl_label = "Named Parameter"
    bl_description = (
        "Create or explicitly replace a project parameter used by feature dimensions and formulas"
    )
    bl_options = {"REGISTER", "UNDO"}
    parameter_name: StringProperty(name="Name", default="thickness")
    expression: StringProperty(name="Value or formula", default="3")
    replace_existing: BoolProperty(name="Replace existing parameter", default=False)
    original_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        self.original_json = _state(context).document_json
        return context.window_manager.invoke_props_dialog(self, width=480, confirm_text="Apply")

    def draw(self, context):
        self.layout.prop(self, "parameter_name")
        self.layout.prop(self, "expression")
        self.layout.prop(self, "replace_existing")
        self.layout.label(text="Lengths use millimetres; formulas can use other named parameters.")
        self.layout.label(text="The entire design rebuilds; invalid formulas fail visibly.")

    def execute(self, context):
        try:
            candidate = set_parameter(
                self._original(context),
                self.parameter_name,
                self.expression,
                replace_existing=self.replace_existing,
            )
            return _report_result(
                self, context, _commit_candidate(context, candidate, _state(context).document_path)
            )
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))


class MCAD_OT_offset_fixed_sketch_plane(_HistoryDialog, Operator):
    bl_idname = "mcad.offset_fixed_sketch_plane"
    bl_label = "Offset Fixed Sketch Plane"
    bl_description = "Move an unlinked sketch once along its own normal; no source following or parameter link"
    bl_options = {"REGISTER", "UNDO"}
    offset: StringProperty(name="Signed offset", default="0", description="Literal length in mm, cm, m, in or ft; no formulas")

    @classmethod
    def poll(cls, context):
        from . import document_state
        from .fixed_plane_edit import fixed_sketch

        if not super().poll(context):
            cls.poll_message_set("Choose a saved sketch in Object Mode; finish drafts and running CAD work first.")
            return False
        if document_state.has_staged_edit(context):
            cls.poll_message_set("Accept or discard the proposed edit before offsetting a fixed plane.")
            return False
        try:
            state = _state(context)
            if not 0 <= state.feature_index < len(state.features):
                cls.poll_message_set("Select a saved unlinked constrained sketch in Feature History.")
                return False
            fixed_sketch(_read_document(state), state.features[state.feature_index].feature_id)
            return True
        except ValueError as exc:
            cls.poll_message_set(str(exc))
            return False
        except KeyError:
            cls.poll_message_set("The saved sketch plane is incomplete; choose a valid unlinked sketch.")
            return False

    def invoke(self, context, event):
        from . import document_state
        from .fixed_plane_edit import fixed_sketch

        try:
            if not self.poll(context):
                raise ValueError("Choose an unlinked saved sketch with no draft, pending edit or running operation.")
            state = _state(context)
            self._feature_id = state.features[state.feature_index].feature_id
            self._document = _read_document(state)
            fixed_sketch(self._document, self._feature_id)
            self._binding = document_state._capture_binding(context)
            self.offset = "0"
            return context.window_manager.invoke_props_dialog(self, width=480, confirm_text="Apply Fixed Offset")
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))

    def draw(self, context):
        self.layout.prop(self, "offset")
        self.layout.label(text="One-time move along this plane's normal (+ or −).")
        self.layout.label(text="Fixed plane: no source following or parameter link.")
        self.layout.label(text="Local sketch geometry and constraints stay unchanged.")

    def execute(self, context):
        from . import document_state, staged_edit_store
        from .fixed_plane_edit import offset_candidate

        try:
            if not hasattr(self, "_binding"):
                raise ValueError("Open Offset Fixed Sketch Plane from the selected sketch first.")
            document_state.require_no_sketch_draft(context)
            staged_edit_store.require_none(context)
            with document_state.replay_guard(context):
                document_state._assert_binding(context, self._binding)
                state = _state(context)
                if (not 0 <= state.feature_index < len(state.features)
                        or state.features[state.feature_index].feature_id != self._feature_id):
                    raise ValueError("The selected feature changed; reopen Offset Fixed Sketch Plane.")
                candidate = offset_candidate(self._document, self._feature_id, self.offset)
                if candidate == self._document:
                    return {"FINISHED"}
                def reselect_edited_sketch():
                    # History selection is UI state, not the canonical active output.
                    # Keep this inside publication so any late failure rolls it back.
                    state.feature_index = next(
                        i for i, row in enumerate(state.features)
                        if row.feature_id == self._feature_id
                    )

                return _report_result(self, context, document_state._commit_candidate_locked(
                    context, candidate, state.document_path,
                    validate_publication=reselect_edited_sketch,
                ))
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))


class MCAD_OT_rename_history_feature(_HistoryDialog, Operator):
    bl_idname = "mcad.rename_history_feature"
    bl_label = "Rename Feature"
    bl_description = "Rename the selected history label without changing its identity, dimensions or references. Undo restores the name"
    bl_options = {"REGISTER", "UNDO"}
    feature_label: StringProperty(name="Name", description="Visible history label; stable ID and references stay unchanged")

    @classmethod
    def poll(cls, context):
        from . import document_state

        if not super().poll(context) or document_state.has_staged_edit(context):
            cls.poll_message_set("Finish drafts, proposed edits and running CAD work before renaming.")
            return False
        state = _state(context)
        if not 0 <= state.feature_index < len(state.features):
            cls.poll_message_set("Select a feature in Feature History to rename.")
            return False
        return True

    def invoke(self, context, event):
        from . import document_state

        try:
            if not self.poll(context):
                raise ValueError("Select a saved feature with no draft, proposed edit or running operation.")
            state = _state(context)
            self._feature_id = state.features[state.feature_index].feature_id
            self._document = _read_document(state)
            feature = next(f for f in self._document["features"] if f["id"] == self._feature_id)
            self.feature_label = feature.get("label", self._feature_id)
            self._binding = document_state._capture_binding(context)
            return context.window_manager.invoke_props_dialog(self, width=400, confirm_text="Rename")
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))

    def draw(self, context):
        self.layout.prop(self, "feature_label")
        self.layout.label(text="Only the name changes. Dimensions and references stay the same.")

    def execute(self, context):
        from . import document_state, staged_edit_store
        from .history_edit import rename_feature

        try:
            if not hasattr(self, "_binding"):
                raise ValueError("Open Rename Feature from the selected history feature first.")
            document_state.require_no_sketch_draft(context)
            staged_edit_store.require_none(context)
            with document_state.replay_guard(context):
                document_state._assert_binding(context, self._binding)
                state = _state(context)
                if (not 0 <= state.feature_index < len(state.features)
                        or state.features[state.feature_index].feature_id != self._feature_id):
                    raise ValueError("The selected feature changed; reopen Rename Feature.")
                candidate = rename_feature(self._document, self._feature_id, self.feature_label)
                if candidate == self._document:
                    return {"FINISHED"}

                def reselect_renamed_feature():
                    state.feature_index = next(
                        i for i, row in enumerate(state.features) if row.feature_id == self._feature_id
                    )

                return _report_result(self, context, document_state._commit_candidate_locked(
                    context, candidate, state.document_path,
                    validate_publication=reselect_renamed_feature,
                ))
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))


CLASSES = (MCAD_OT_remove_history_feature, MCAD_OT_named_parameter, MCAD_OT_offset_fixed_sketch_plane, MCAD_OT_rename_history_feature)
