"""Select blend intent through two visible, exactly bound semantic faces.

The display has triangle-to-face provenance, not native edge provenance. Thus
this deliberately asks for two faces rather than pretending triangle edges are
CAD edges. Native replay alone decides whether the pair shares one unique edge.
"""

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator
from bpy_extras import view3d_utils

from . import document_state
from .face_pick import FacePicker, draw_highlight
from .viewport_ray import ray_cast
from .viewport_sketch import NAVIGATION_EVENTS, _can_start_sketch


def resolve_face(feature, index):
    mesh = feature.get("mesh") or {}
    ids = mesh.get("triangle_face_ids", [])
    if len(ids) != len(mesh.get("triangles", [])):
        raise ValueError("The display face map is incomplete. Rebuild the Part.")
    if type(index) is not int or not 0 <= index < len(ids):
        raise ValueError("No exact CAD face under the pointer.")
    matches = [f for f in feature.get("topology", []) if f.get("id") == ids[index]]
    if (
        len(matches) != 1
        or not ids[index]
        or matches[0].get("kind") != "face"
        or matches[0].get("provenance", {}).get("semantic_status") != "stable"
    ):
        raise ValueError("This face has no unambiguous stable identity. Use another face.")
    return matches[0]


def face_points(obj, feature, face_id):
    return [
        obj.matrix_world @ obj.data.vertices[v].co
        for i, triangle in enumerate(feature["mesh"]["triangles"])
        if feature["mesh"]["triangle_face_ids"][i] == face_id
        for v in triangle
    ]


class BlendFacePicker(FacePicker):
    def __init__(self, context, kind, *, snapshot=None):
        self.first = None
        self.first_obj = None
        self.first_points = []
        self.hit_obj = None
        self.kind = kind
        super().__init__(context, snapshot=snapshot)
        self.message = "Click the first face beside the edge to blend. Esc cancels."
        self.area.header_text_set(self.message)

    def current(self, context):
        if not super().current(context):
            return False
        if self.first_obj is not None:
            try:
                self.snapshot.bound_feature(context, self.first_obj, self.snapshot.result(context))
            except (ValueError, ReferenceError):
                return False
        return True

    def hover(self, context, event, *, accepting=False):
        self.hit_obj = None
        instruction = (
            "Click a second face beside the same edge. Esc cancels."
            if self.first
            else "Click the first face beside the edge to blend. Esc cancels."
        )
        xy = self.hover_coordinates(context, event, instruction)
        if xy is None:
            return False
        origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, xy)
        direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, xy)
        hit, _, _, index, obj, hit_matrix = ray_cast(
            context, context.evaluated_depsgraph_get(), origin, direction
        )
        if hit and self.snapshot.owns(context, obj.original):
            try:
                obj = obj.original
                if hit_matrix != obj.matrix_world:
                    raise ValueError("Choose the original CAD display, not an instance.")
                feature = self.snapshot.bound_feature(
                    context, obj, self.snapshot.result(context, accepting=accepting)
                )
                face = resolve_face(feature, index)
                candidate = (feature["id"], face["id"])
                if self.first and (candidate[0] != self.first[0] or obj != self.first_obj):
                    raise ValueError("Choose the second face on the same solid.")
                if candidate == self.first:
                    raise ValueError("First face selected (amber). Choose a different face.")
                self.hit, self.hit_obj = candidate, obj
                self.points = face_points(obj, feature, face["id"])
                self.message = (
                    "Click to select this as the second face. Esc cancels."
                    if self.first
                    else "Click to select this as the first face. Esc cancels."
                )
            except ValueError as exc:
                self.message = str(exc)
        self.area.header_text_set(self.message)
        self.area.tag_redraw()
        return True

    def choose(self):
        """Retain the first explicit pick; never infer an adjacent semantic face."""
        if not self.hit:
            return False
        if self.first is None:
            self.first, self.first_obj = self.hit, self.hit_obj
            self.first_points = list(self.points)
            self.hit, self.hit_obj, self.points = None, None, []
            self.area.header_text_set(
                "First face selected (amber). Click the second face; Esc cancels."
            )
            self.area.tag_redraw()
            return False
        if self.hit[0] != self.first[0] or self.hit_obj != self.first_obj:
            raise ValueError("Choose both faces on the same solid.")
        if self.hit == self.first:
            raise ValueError("Choose two different faces beside one edge.")
        return True

    def dialog_arguments(self):
        if not self.first or not self.hit or self.first == self.hit:
            raise ValueError("Select two distinct faces before opening the blend dialog.")
        return dict(
            kind=self.kind,
            picked_document_json=self.base,
            picked_base=self.first[0],
            picked_face_a=self.first[1],
            picked_face_b=self.hit[1],
        )

    def draw(self):
        super().draw()
        if (
            bpy.context.area != self.area
            or bpy.context.window != self.window
            or not self.first_points
        ):
            return
        draw_highlight(self.first_points, (1.0, 0.55, 0.08, 0.45))


class MCAD_OT_pick_blend_faces(Operator):
    bl_idname = "mcad.pick_blend_faces"
    bl_label = "Pick Two Faces Sharing the Edge"
    bl_description = (
        "Pick two faces sharing the edge, then set the fillet radius or chamfer distance"
    )
    kind: EnumProperty(items=[("fillet", "Fillet", ""), ("chamfer", "Chamfer", "")])

    @classmethod
    def poll(cls, context):
        return bool(
            context.area
            and context.area.type == "VIEW_3D"
            and _can_start_sketch(context)
            and document_state.current_part_result(context)
        )

    def invoke(self, context, event):
        self._picker = BlendFacePicker(context, self.kind)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        picker = self._picker
        try:
            if event.type in {"ESC", "RIGHTMOUSE"} or not picker.current(context):
                picker.close()
                return {"CANCELLED"}
            if event.type in NAVIGATION_EVENTS:
                picker.hit, picker.points, picker.hit_obj = None, [], None
                picker.area.tag_redraw()
                return {"PASS_THROUGH"}
            if event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
                if not picker.hover(
                    context, event, accepting=event.type == "LEFTMOUSE" and event.value == "PRESS"
                ):
                    return {"PASS_THROUGH"}
                if event.type == "LEFTMOUSE" and event.value == "PRESS" and picker.choose():
                    arguments = picker.dialog_arguments()
                    picker.close()
                    bpy.ops.mcad.add_solid_feature("INVOKE_DEFAULT", **arguments)
                    return {"FINISHED"}
            return {"RUNNING_MODAL"}
        except Exception as exc:
            picker.close()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def cancel(self, context):
        picker = getattr(self, "_picker", None)
        if picker is not None:
            picker.close()


CLASSES = (MCAD_OT_pick_blend_faces,)
