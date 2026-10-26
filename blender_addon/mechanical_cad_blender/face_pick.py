"""Transient triangle picking, bound to the current exact display snapshot.

No mesh index is persisted: only an explicitly stable topology ID crosses into
sketch authoring. Edited/deformed/stale display caches are never identity evidence.
"""

import struct

import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from . import backend_runtime, document_state, workspace, workspace_ui
from .common import DOCUMENT_KEY, FEATURE_KEY, MM_TO_METERS, OWNER_KEY, _state
from .viewport_navigation import is_navigation_event
from .viewport_ray import ray_cast

_PICKERS = set()


def cancel_all():
    for picker in tuple(_PICKERS):
        picker.close()


def _f32(value):
    return struct.unpack("f", struct.pack("f", value))[0]


def resolve_triangle(feature, index):
    """Resolve only the explicit current triangle map, never geometric similarity."""
    mesh = feature.get("mesh") or {}
    ids = mesh.get("triangle_face_ids", [])
    if type(index) is not int or not 0 <= index < len(ids):
        raise ValueError("No exact CAD face under the pointer.")
    if len(ids) != len(mesh.get("triangles", [])):
        raise ValueError("The display face map is incomplete. Rebuild the Part.")
    matches = [f for f in feature.get("topology", []) if f.get("id") == ids[index]]
    if len(matches) != 1 or not ids[index]:
        raise ValueError("This face has no unambiguous exact identity.")
    face = matches[0]
    if face.get("kind") != "face" or face.get("provenance", {}).get("semantic_status") != "stable":
        raise ValueError("This face has no stable identity for an attached sketch.")
    if face.get("signature", {}).get("surface") != "plane":
        raise ValueError("Choose a planar face, not a curved surface.")
    return face


def bound_feature(context, obj, result, *, owner_id=None):
    """Compare the entire disposable display with its exact float32 publication."""
    state = _state(context)
    if (
        result is None
        or obj is None
        or obj.type != "MESH"
        or obj.get(OWNER_KEY) != (state.owner_id if owner_id is None else owner_id)
        or obj.get(DOCUMENT_KEY) != result.get("document_id")
        or obj.get("mechanical_cad_stale", True)
        or obj.mode != "OBJECT"
        or obj.modifiers
        or obj.data.shape_keys
    ):
        raise ValueError("Choose the current exact CAD solid. Rebuild stale geometry first.")
    matches = [f for f in result["features"] if f["id"] == obj.get(FEATURE_KEY)]
    if len(matches) != 1:
        raise ValueError("The displayed solid has no current replay binding.")
    feature = matches[0]
    if feature.get("status") != "ok" or (feature.get("output") or {}).get("kind") != "solid":
        raise ValueError("Choose a solid face, not a sketch.")
    scale = MM_TO_METERS / max(float(context.scene.unit_settings.scale_length), 1e-9)
    mesh = feature["mesh"]
    vertices = [tuple(v * scale for v in point) for point in mesh["vertices"]]
    origin = tuple(
        _f32((min(p[a] for p in vertices) + max(p[a] for p in vertices)) / 2) for a in range(3)
    )
    expected = [tuple(_f32(p[a] - origin[a]) for a in range(3)) for p in vertices]
    if (
        obj.matrix_world != Matrix.Translation(Vector(origin))
        or len(obj.data.vertices) != len(expected)
        or len(obj.data.polygons) != len(mesh["triangles"])
        or any(tuple(v.co) != p for v, p in zip(obj.data.vertices, expected, strict=True))
        or any(
            tuple(p.vertices) != tuple(t)
            for p, t in zip(obj.data.polygons, mesh["triangles"], strict=True)
        )
    ):
        raise ValueError(
            "The CAD display was edited or transformed. Rebuild before picking a face."
        )
    return feature


class HoverSnapshot:
    """Detached preview only; never substitutes for acceptance-time evidence.

    Keep full display comparison on every hit. Only the expensive immutable
    replay projection is reused, guarded by its exact live runtime association.
    """

    def __init__(self, context):
        self.projection = document_state.current_part_result(context)
        self.record = document_state._RUNTIME.get(document_state._scene_key(context.scene))
        if self.projection is None or self.record is None:
            raise ValueError("Rebuild the Part before selecting a face.")
        self.fields = dict(self.record)
        self.evidence = (self.record["evidence"], self.record["owner_token"])

    def owns(self, context, obj):
        return obj.get(OWNER_KEY) == _state(context).owner_id

    def bound_feature(self, context, obj, result):
        return bound_feature(context, obj, result)

    def current(self, context):
        try:
            state = _state(context)
            record = document_state._RUNTIME.get(document_state._scene_key(context.scene))
            if (
                record is not self.record
                or record.keys() != self.fields.keys()
                or any(record[key] is not value for key, value in self.fields.items())
                or record["scene"] != context.scene
                or record["owner_id"] != state.owner_id
                or record["document_json"] != state.document_json
                or record["scale"] != float(context.scene.unit_settings.scale_length)
                or state.status != "READY"
            ):
                return False
            backend_runtime.assert_current(record["selection"], context)
            return True
        except (ValueError, RuntimeError, ReferenceError, AttributeError, KeyError, OSError):
            return False

    def result(self, context, *, accepting=False):
        if not self.current(context):
            raise ValueError("The Part changed. Select its face again after rebuilding.")
        result = document_state.current_part_result(context) if accepting else self.projection
        if result is None or not self.current(context):
            raise ValueError("Current exact face evidence is unavailable. Rebuild the Part.")
        return result


def draw_highlight(points, color):
    """Draw a depth-tested face overlay without coplanar depth fighting."""
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    blend = gpu.state.blend_get()
    depth_test = gpu.state.depth_test_get()
    depth_mask = gpu.state.depth_mask_get()
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.depth_mask_set(False)
    try:
        # The overlay is exactly coplanar with the display. Bias clip-space
        # depth toward the viewer, not world geometry or pick coordinates.
        # Depth testing still hides the overlay behind foreground objects.
        projection = gpu.matrix.get_projection_matrix().copy()
        for column in range(4):
            projection[2][column] -= 1e-5 * projection[3][column]
        with gpu.matrix.push_pop_projection():
            gpu.matrix.load_projection_matrix(projection)
            shader.bind()
            shader.uniform_float("color", color)
            batch_for_shader(shader, "TRIS", {"pos": points}).draw(shader)
    finally:
        gpu.state.depth_mask_set(depth_mask)
        gpu.state.depth_test_set(depth_test)
        gpu.state.blend_set(blend)


class FacePicker:
    """One short-lived viewport gesture, owned by the new-face operator."""

    def __init__(self, context, *, snapshot=None):
        cancel_all()
        self.snapshot = HoverSnapshot(context) if snapshot is None else snapshot
        self.area = context.area
        self.region = next(r for r in self.area.regions if r.type == "WINDOW")
        self.rv3d = self.area.spaces.active.region_3d
        self.window = context.window
        self.screen = context.window.screen
        self.wm = context.window_manager
        self.timer = self.wm.event_timer_add(0.2, window=self.window)
        self.scene = context.scene
        self.base = _state(context).document_json
        self.evidence = self.snapshot.evidence
        self.hit = None
        self.points = []
        self.selected_points = []
        self.selected_object = None
        self.hover_object = None
        self.navigation_drag = False
        self.message = (
            "Hover a planar face, click to sketch. Esc cancels; middle mouse or wheel navigates."
        )
        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw, (), "WINDOW", "POST_VIEW")
        self.area.header_text_set(self.message)
        _PICKERS.add(self)

    def close(self, *, retain_snapshot=False):
        self.selected_points = []
        self.selected_object = None
        self.hover_object = None
        self.navigation_drag = False
        self.points = []
        if self.timer is not None:
            self.wm.event_timer_remove(self.timer)
            self.timer = None
        if self.handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handler, "WINDOW")
            self.handler = None
        _PICKERS.discard(self)
        if not retain_snapshot and hasattr(self.snapshot, "close"):
            self.snapshot.close()
        try:
            self.area.header_text_set(None)
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def current(self, context):
        from .viewport_sketch import _can_start_sketch

        return (
            self.handler is not None
            and context.window == self.window
            and context.scene == self.scene
            and self.window.screen == self.screen
            and context.area == self.area
            and self.area.type == "VIEW_3D"
            and _state(context).document_json == self.base
            and _can_start_sketch(context)
            and self.snapshot.current(context)
        )

    def hover_coordinates(self, context, event, instruction):
        self.hit, self.points = None, []
        self.hover_object = None
        self.message = instruction
        self.area.header_text_set(self.message)
        self.area.tag_redraw()
        if workspace_ui.is_palette_event(context, event) or is_navigation_event(
            context, self.region, event
        ):
            return None
        xy = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
        if not (0 <= xy[0] < self.region.width and 0 <= xy[1] < self.region.height):
            return None
        # Sidebar/header clicks belong to Blender, not the face picker.
        for region in self.area.regions:
            if region.type != "WINDOW" and region.width > 1 and region.height > 1:
                if (
                    region.x <= event.mouse_x < region.x + region.width
                    and region.y <= event.mouse_y < region.y + region.height
                ):
                    return None
        return xy

    def resolve_face(self, feature, index):
        return resolve_triangle(feature, index)

    def hover(self, context, event, *, accepting=False):
        xy = self.hover_coordinates(
            context,
            event,
            getattr(self, "pick_instruction", "Click a planar CAD face to sketch. Esc cancels."),
        )
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
                face = self.resolve_face(feature, index)
                self.hit = (feature["id"], face["id"])
                self.hover_object = obj
                self.points = [
                    obj.matrix_world @ obj.data.vertices[v].co
                    for i, triangle in enumerate(feature["mesh"]["triangles"])
                    if feature["mesh"]["triangle_face_ids"][i] == face["id"]
                    for v in triangle
                ]
                self.message = getattr(
                    self, "pick_instruction", "Click to sketch on this planar face. Esc cancels."
                )
                if getattr(self, "describe_support", True):
                    if face["role"].startswith("shell.inner."):
                        self.message += " Inner wall follows Shell thickness; Edit Feature changes it."
                    elif face["role"] == "shell.opening_lip":
                        self.message += (
                            " Lip follows this Shell's current opening; Edit Feature changes it."
                        )
                    elif face["role"].startswith("shell.opening_lip."):
                        self.message += " Lip follows its explicitly selected Shell opening face."
                    if face["role"] == "blend.surface" or face["role"].startswith("blend.surface."):
                        self.message += (
                            " Follows the selected blend edge; Edit Feature changes its intent."
                        )
            except ValueError as exc:
                self.message = str(exc)
        self.area.header_text_set(self.message)
        self.area.tag_redraw()
        return True

    def set_selected(self, context, source, identifiers):
        """Retain explicit picked faces as disposable, source-guarded feedback.

        Selection authority remains in the caller's semantic ID list. These
        triangles are only tinted display geometry, never used to resolve IDs.
        """
        if not identifiers:
            self.selected_points, self.selected_object = [], None
            self.area.tag_redraw()
            return
        if not self.current(context):
            raise ValueError("The Part changed; pick the Shell openings again.")
        obj = self.hover_object
        if obj is None:
            raise ValueError("Choose an opening on the current exact input display.")
        feature = self.snapshot.bound_feature(context, obj, self.snapshot.result(context))
        if feature["id"] != source:
            raise ValueError("Pick all openings on the same input body.")
        for identifier in identifiers:
            matches = [f for f in feature["topology"] if f["id"] == identifier]
            if (
                len(matches) != 1
                or matches[0]["provenance"]["semantic_status"] != "stable"
                or matches[0]["signature"]["surface"] != "plane"
            ):
                raise ValueError("Selected opening is no longer a unique stable planar face.")
        wanted = set(identifiers)
        self.selected_points = [
            obj.matrix_world @ obj.data.vertices[v].co
            for i, triangle in enumerate(feature["mesh"]["triangles"])
            if feature["mesh"]["triangle_face_ids"][i] in wanted
            for v in triangle
        ]
        self.selected_object = obj
        self.area.tag_redraw()

    def draw(self):
        if bpy.context.area != self.area or bpy.context.window != self.window:
            return
        try:
            if not self.current(bpy.context):
                raise ValueError("Stale face feedback")
            if self.selected_object is not None:
                # Orbit changes the view, never the bound world-space geometry.
                # Mesh/object edits revoke feedback immediately, before next click.
                self.snapshot.bound_feature(
                    bpy.context, self.selected_object, self.snapshot.result(bpy.context)
                )
                draw_highlight(self.selected_points, (1.0, 0.48, 0.08, 0.55))
            if self.points:
                draw_highlight(self.points, (0.15, 0.8, 1.0, 0.4))
        except (ValueError, RuntimeError, ReferenceError, AttributeError, KeyError):
            self.selected_points, self.selected_object = [], None
            self.points = []

    def begin(self, context, *, support_policy="PRESERVE_PLANE"):
        support, face = self.hit
        base, evidence = self.base, self.evidence

        def ready(active_context):
            if (
                _state(active_context).document_json != base
                or document_state.current_part_evidence(active_context) != evidence
            ):
                raise RuntimeError("The Part changed before Sketch opened; select the face again.")
            bpy.ops.mcad.general_sketch(
                "INVOKE_DEFAULT",
                support_source=support,
                support_face=face,
                support_policy=support_policy,
            )

        workspace.request_workspace(context, "SKETCH", on_ready=ready)
