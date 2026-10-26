"""Current sidebar and feature-history presentation.

Panel drawing is read-only; authoring and replay are explicit operators."""

from bpy.types import Panel, UIList

from . import (
    assembly_job_ui,
    backend_runtime,
    compact_status,
    document_state,
    operators,
    staged_edit,
    workspace,
)
from .common import _state
from .display import _owned_objects
from .feature_glyphs import feature_glyph
from .feature_history_draw import capture_presentation, draw_history, row_presentation
from .help_ui import _diagnostic_button, _help_button, _panel_wrap
from .projection_repair_ui import draw_projection_repair
from .solid_feature_edit import FEATURE_FIELDS
from .staged_edit_ui import draw_staged_edit, pending_message_is_duplicate
from .support_intent_ui import draw_support_intent
from .workspace_ui import draw_part_limits, draw_suspended_draft


class MCAD_UL_features(UIList):
    def _matching_flags(self, items):
        from bl_ui import UI_UL_list

        # The default UIList searches RNA `name`, which these display rows do not
        # populate. Search the actual visible label and stable ID instead.
        flags = UI_UL_list.filter_items_by_name(
            self.filter_name, self.bitflag_filter_item, items, propname="label"
        )
        return UI_UL_list.filter_items_by_name(
            self.filter_name, self.bitflag_filter_item, items,
            propname="feature_id", flags=flags,
        )

    def filter_items(self, context, data, propname):
        # History order is canonical. Never reorder/copy the RNA collection or
        # change its selected index: row presentation and edit targets bind it.
        self.use_filter_sort_lock = True
        self.use_filter_sort_reverse = False
        self.use_filter_invert = False
        if self.filter_name:
            # A collapsed active search can look like deleted history. Keep its
            # native drawer visible until cleared; empty searches cost no space.
            self.use_filter_show = True
        return self._matching_flags(getattr(data, propname)), []

    def draw_filter(self, context, layout):
        layout.prop(self, "filter_name", text="", placeholder="Name or ID", icon="VIEWZOOM")
        if self.filter_name:
            state = _state(context)
            flags = self._matching_flags(state.features)
            count = sum(bool(flag & self.bitflag_filter_item) for flag in flags)
            layout.label(
                text=f"{count} of {len(state.features)} features shown"
                if count else "No matches · clear search"
            )
            index = state.feature_index
            if 0 <= index < len(flags) and not flags[index] & self.bitflag_filter_item:
                layout.label(text="Selection hidden by search", icon="INFO")

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        state = _state(context)
        row = layout.row(align=True)
        status_icon, assumed = row_presentation(context, data, item, index)
        row.label(text=item.label, icon=feature_glyph(item.kind))
        # Family stays recognizable while stale. Keep the separately guarded
        # status beside it: a familiar operation icon is never proof of replay.
        row.label(text="", icon=status_icon)
        if assumed:
            row.label(text="Plane assumed", icon="INFO")
        if item.feature_id == state.active_feature:
            row.label(text="", icon="HIDE_OFF")
        edit = row.row(align=True)
        # Cached kind only controls presentation; the action re-reads canonical
        # data and guards all live owners before choosing an editor.
        edit.enabled = item.kind == "sketch_constrained" or item.kind in FEATURE_FIELDS
        edit.operator_context = "INVOKE_DEFAULT"
        edit.operator("mcad.edit_history_feature", text="", icon="GREASEPENCIL").feature_id = (
            item.feature_id
        )


class MCAD_PT_main(Panel):
    bl_label = "Mechanical CAD"
    bl_idname = "MCAD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CAD"

    @classmethod
    def poll(cls, context):
        return not workspace.is_cad_workspace(context)

    def draw(self, context):
        layout = self.layout
        blocked = assembly_job_ui.draw_backend_failure(layout, context)
        state = _state(context)
        layout.operator(
            "mcad.open_workspace", text="Open CAD Workspaces", icon="WORKSPACE"
        ).role = "PART"
        if state.sketch_notice:
            box = layout.box()
            box.label(text="Sketch notice", icon="INFO")
            for line in _panel_wrap(context, state.sketch_notice):
                box.label(text=line)
        draw_suspended_draft(layout, context)
        row = layout.row(align=True)
        row.operator("mcad.new_document", text="New", icon="ADD")
        row.operator("mcad.new_demo", text="Demo")
        row = layout.row(align=True)
        row.operator("mcad.load_document", text="Load", icon="FILE_FOLDER")
        row.operator("mcad.save_document", text="Save", icon="FILE_TICK")
        _help_button(row, "persistence")
        row = layout.row(align=True)
        _help_button(row, "workflow.overview", "Workflow")
        _help_button(row, "roadmap", "Scope")
        layout.operator("mcad.help_browser", text="Search CAD Help", icon="QUESTION")
        if state.last_action_error and not pending_message_is_duplicate(
            context, state.last_action_error
        ):
            box = layout.box()
            box.alert = True
            for line in _panel_wrap(context, state.last_action_error):
                box.label(text=line)
            _diagnostic_button(box, state.last_action_error)
        if not state.document_json:
            layout.label(text="Start with New, Demo or load a CAD document.")
            if backend_runtime.bundled_mode():
                setup_state, message = backend_runtime.bundle_status()
                if blocked and setup_state == "ready":
                    message = "Bundled files prepared; native operations are blocked."
                for line in _panel_wrap(context, message):
                    layout.label(text=line, icon="INFO")
                _help_button(layout, "setup.bundled", "Bundled backend")
            else:
                layout.label(text="Set the external Python path in preferences.", icon="INFO")
                _help_button(layout, "setup.backend", "Backend setup")
            return
        layout.label(text=state.document_name, icon="MESH_CUBE")
        proposed = draw_staged_edit(layout, context)
        # Launch dialogs before variable-height diagnostics, parameters and history.
        # Blender anchors native dialogs near the clicked control; a bottom-of-list
        # Edit button can place its Apply/Cancel footer below the window.
        if 0 <= state.feature_index < len(state.features):
            row = layout.row(align=True)
            row.label(text="Selected: " + state.features[state.feature_index].label)
            row.operator("mcad.rename_history_feature", text="", icon="FONT_DATA")
        row = layout.row(align=True)
        row.operator("mcad.edit_solid_feature", text="Edit Feature", icon="GREASEPENCIL")
        row.operator("mcad.activate_feature", text="Display", icon="HIDE_OFF")
        if staged_edit.current(context) is None:
            draw_projection_repair(layout, context)
        presentation = capture_presentation(context)
        status = (
            "UNVERIFIED" if state.status == "READY" and not presentation.is_current(context) else state.status
        )
        row = layout.row()
        row.alert = status == "FAILED"
        row.label(
            text="Build: Up to date" if status == "READY" else f"Status: {compact_status.part_state_text(status)}",
            icon="ERROR" if status == "FAILED" else "INFO",
        )
        _help_button(row, "verification.geometry")
        if state.status == "FAILED":
            if any(obj.get("mechanical_cad_stale") for obj in _owned_objects(context.scene)):
                layout.label(text="STALE: last-good wireframe", icon="ERROR")
                layout.label(text="Not the current CAD output.")
            _help_button(layout, "error.rebuild", "How to fix this")
        if state.error:
            box = layout.box()
            for line in _panel_wrap(context, state.error):
                box.label(text=line)
            if state.status == "FAILED":
                _diagnostic_button(box, state.error, failed=True)
        if context.mode != "OBJECT":
            layout.label(text="Return to Object Mode to regenerate.", icon="ERROR")
        from .history_rebuild import draw_cancel

        if not draw_cancel(layout, context):
            layout.operator("mcad.regenerate", icon="FILE_REFRESH")
        row = layout.row(align=True)
        row.operator("mcad.focus_result", text="Focus Result", icon="VIEWZOOM")
        row.operator("mcad.show_scene", text="Whole Scene")

        row = layout.row(align=True)
        row.label(text="Feature history")
        _help_button(row, "history.edit")
        draw_history(layout, context, "", rows=5, presentation=presentation)
        if 0 <= state.feature_index < len(state.features):
            feature = state.features[state.feature_index]
            detail = layout.box()
            detail.label(text=f"ID: {feature.feature_id}")
            selected = presentation.selected_detail(context, feature.feature_id)
            detail.label(text=f"{feature.kind} · {selected.status if selected else 'unverified'}")
            if feature.error:
                for line in _panel_wrap(context, feature.error):
                    detail.label(text=line)
        if not proposed:
            draw_support_intent(layout, context, presentation=presentation)
        box = layout.box()
        box.enabled = not workspace.has_draft(context) and not document_state.has_staged_edit(
            context
        )
        row = box.row(align=True)
        row.label(text="Parameters · millimetres")
        _help_button(row, "sketch.dimensions")
        for parameter in state.parameters:
            row = box.row(align=True)
            row.prop(
                parameter, "expression" if parameter.is_expression else "value", text=parameter.key
            )
            row.prop(parameter, "is_expression", text="", icon="DRIVER")
        if not state.parameters:
            box.label(text="This document has no named parameters.")

        draw_part_limits(layout, context)
        reasons = set()
        for kind in ("sketch_rectangle", "sketch_circle", "extrude", "cut"):
            reason = operators.feature_action_reason(context, kind)
            if reason and reason not in reasons:
                reasons.add(reason)
                for line in _panel_wrap(context, reason):
                    layout.label(text=line, icon="INFO")
        row = layout.row(align=True)
        row.enabled = context.mode == "OBJECT"
        row.operator("mcad.add_rectangle", text="Rectangle")
        _help_button(row, "sketch.rectangle")
        row.operator("mcad.add_circle", text="Circle")
        _help_button(row, "sketch.circle")
        row = layout.row(align=True)
        row.enabled = context.mode == "OBJECT"
        row.operator("mcad.add_extrude", text="Extrude")
        _help_button(row, "feature.extrude")
        row.operator("mcad.add_cut", text="Cut")
        _help_button(row, "feature.boolean_operands")
        volume_text = presentation.volume_text(context)
        if volume_text is not None and status == "READY":
            layout.label(text=volume_text)
        layout.separator()
        layout.label(text="Meshes are display-only.", icon="INFO")
        layout.label(text="Edit parameters, then Regenerate.")
        row = layout.row(align=True)
        row.label(text="CAD mm → metres, respecting scene scale.")
        _help_button(row, "units")
