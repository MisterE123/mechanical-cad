"""Pick a planar shell opening using the exact guarded CAD face display."""

import json

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from . import document_state
from .face_pick import FacePicker
from .shell_selection import toggle_opening
from .viewport_navigation import navigation_passthrough
from .viewport_sketch import NAVIGATION_EVENTS, _can_start_sketch


class MCAD_OT_pick_shell_face(Operator):
    bl_idname = "mcad.pick_shell_face"
    bl_label = "Pick Shell Opening"
    bl_description = "Click one opening, or Shift-click multiple faces and press Enter"
    kind: StringProperty(default="shell", options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return bool(
            context.area
            and context.area.type == "VIEW_3D"
            and _can_start_sketch(context)
            and document_state.current_part_result(context)
        )

    def invoke(self, context, event):
        self._multiple = False
        self._selected = []
        self._source = ""
        self._picker = FacePicker(context)
        self._picker.pick_instruction = (
            "Click one face; Shift-click toggles multiple, Enter reviews. C closed; Esc cancels."
        )
        self._picker.area.header_text_set(self._picker.pick_instruction)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        picker = self._picker
        try:
            if event.type in {"ESC", "RIGHTMOUSE"} or not picker.current(context):
                picker.close()
                return {"CANCELLED"}
            if navigation_passthrough(picker, context, event):
                return {"PASS_THROUGH"}
            if event.type == "C" and event.value == "PRESS":
                picker.close()
                bpy.ops.mcad.add_solid_feature("INVOKE_DEFAULT", kind="shell", shell_mode="CLOSED")
                return {"FINISHED"}
            if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
                if not self._selected:
                    self.report({"WARNING"}, "Pick at least one planar opening first")
                    return {"RUNNING_MODAL"}
                return self._review()
            if event.type in NAVIGATION_EVENTS:
                picker.hit, picker.points = None, []
                picker.area.tag_redraw()
                return {"PASS_THROUGH"}
            if event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
                accepting = event.type == "LEFTMOUSE" and event.value == "PRESS"
                if not picker.hover(context, event, accepting=accepting):
                    return {"PASS_THROUGH"}
                if accepting and picker.hit:
                    if getattr(event, "shift", False) or getattr(self, "_multiple", False):
                        self._multiple = True
                        self._source, self._selected = toggle_opening(
                            self._selected, self._source, picker.hit
                        )
                        picker.set_selected(context, self._source, self._selected)
                        picker.pick_instruction = f"{len(self._selected)} orange openings: click toggles; Enter reviews; Esc cancels."
                        picker.area.header_text_set(picker.pick_instruction)
                        return {"RUNNING_MODAL"}
                    self._source, opening = picker.hit
                    self._selected = [opening]
                    return self._review()
            if event.type in {"MOUSEMOVE", "LEFTMOUSE", "INBETWEEN_MOUSEMOVE"}:
                return {"PASS_THROUGH"}
            return {"RUNNING_MODAL"}
        except Exception as exc:
            picker.close()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def _review(self):
        picker = self._picker
        original = picker.base
        picker.close()
        bpy.ops.mcad.add_solid_feature(
            "INVOKE_DEFAULT",
            kind="shell",
            picked_base=self._source,
            picked_opening_faces_json=json.dumps(self._selected),
            picked_document_json=original,
        )
        return {"FINISHED"}

    def cancel(self, context):
        picker = getattr(self, "_picker", None)
        if picker is not None:
            picker.close()


CLASSES = (MCAD_OT_pick_shell_face,)
