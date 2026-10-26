"""One-click blend intent from guarded native adjacency, never mesh edge guessing."""

import json

import bpy
import gpu
from bpy.props import EnumProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import assembly_job_ui, backend_contracts, backend_runtime, sketch_pending
from .blend_selection import validate_edge_pairs
from .common import MM_TO_METERS, _state
from .edge_catalog_bridge import nearest_segment
from .edge_pick import MCAD_OT_pick_blend_faces
from .face_pick import FacePicker
from .viewport_ray import ray_cast

_PREPARING = set()


def _supervise_preparation():
    # View ownership can disappear without another modal event. Cancellation
    # retires process-only work to the existing shared supervisor/reaper.
    for picker in tuple(_PREPARING):
        try:
            if (
                picker.window not in bpy.context.window_manager.windows[:]
                or picker.window.screen != picker.screen
                or picker.area not in picker.screen.areas[:]
                or picker.window.scene != picker.scene
            ):
                picker.close()
                continue
            with bpy.context.temp_override(
                window=picker.window, area=picker.area, region=picker.region
            ):
                if not picker.current(bpy.context):
                    picker.close()
        except (ReferenceError, RuntimeError):
            picker.close()
    return 0.1 if _PREPARING else None


class BlendEdgePicker(FacePicker):
    def __init__(self, context, kind, *, snapshot=None):
        self.pending = None
        self.kind, self.hit_obj = kind, None
        self.catalog = {}
        self.overlap_candidates = ()
        self.multiple = False
        self.selected_edges = {}
        self.selected_base = None
        self.selected_obj = None
        super().__init__(context, snapshot=snapshot)
        try:
            record = self.snapshot.record
            request = {**record["evidence"].operation_request(), "action": "edge_catalog"}
            if kind == "projection":
                request["options"] = {**request["options"], "projection_arcs": True}
            self.catalog_token = object()
            self.catalog_version = request["result_version"]
            self.deflection = request["options"]["linear_deflection"]
            self.catalog_identity = {
                "owner": _state(context).owner_id,
                "base": self.base,
                "scale": record["scale"],
            }
            self.pending = sketch_pending.prepare_guarded(
                backend_contracts.prepare_request(request),
                self.catalog_identity,
                selection=record["selection"],
                owner_token=self.catalog_token,
            )
            _PREPARING.add(self)
            assembly_job_ui.ensure_supervisor()
            if not bpy.app.timers.is_registered(_supervise_preparation):
                bpy.app.timers.register(_supervise_preparation, first_interval=0.1)
            self.area.header_text_set("Preparing exact edges… Esc cancels; you can navigate.")
        except Exception:
            self.close()
            raise

    def current(self, context):
        if self.pending is None:
            return super().current(context)
        return (
            self.handler is not None
            and context.window == self.window
            and context.scene == self.scene
            and self.window.screen == self.screen
            and context.area == self.area
            and self.area.type == "VIEW_3D"
            and context.mode == "OBJECT"
            and self.snapshot.current(context)
        )

    def close(self, *, retain_snapshot=False):
        _PREPARING.discard(self)
        if self.pending is not None:
            sketch_pending.cancel(self.pending, "Edge picking cancelled or its view changed.")
            self.pending = None
            assembly_job_ui.ensure_supervisor()
        self.selected_edges.clear()
        self.selected_obj = None
        self.overlap_candidates = ()
        super().close(retain_snapshot=retain_snapshot)

    def poll_catalog(self, context):
        identity = {
            "owner": _state(context).owner_id,
            "base": _state(context).document_json,
            "scale": float(context.scene.unit_settings.scale_length),
        }
        evidence = sketch_pending.poll(
            self.pending, identity, current_selection=backend_runtime.capture(context)
        )
        if evidence is None:
            return
        catalog = evidence.revalidate(
            backend_runtime.capture(context),
            owner_token=self.catalog_token,
            expected_action="edge_catalog",
            expected_result_version=self.catalog_version,
            require_success=True,
        )["result"]
        if not self.snapshot.current(context) or catalog["replay"] != self.snapshot.result(context):
            raise ValueError("The Part changed while preparing edges. Rebuild and try again.")
        self.catalog, self.catalog_evidence = catalog["catalogs"], evidence
        self.pending = None
        _PREPARING.discard(self)
        self.area.header_text_set(
            "Click one edge, or Shift-click multiple; Enter reviews. F: two faces. Esc cancels."
        )
        self.area.tag_redraw()

    def hover(self, context, event, *, accepting=False):
        self.hit_obj = None
        self.overlap_candidates = ()
        xy = self.hover_coordinates(
            context,
            event,
            "Click one edge, or Shift-click multiple; Enter reviews. F: two faces. Esc cancels.",
        )
        if xy is None:
            return False
        result = self.snapshot.result(context, accepting=accepting)
        if accepting:
            accepted = self.catalog_evidence.revalidate(
                backend_runtime.capture(context),
                owner_token=self.catalog_token,
                expected_action="edge_catalog",
                expected_result_version=self.catalog_version,
                require_success=True,
            )["result"]
            if accepted["catalogs"] != self.catalog or accepted["replay"] != result:
                raise ValueError("Edge display evidence changed. Pick the edge again.")
        scale = MM_TO_METERS / max(float(context.scene.unit_settings.scale_length), 1e-9)
        candidates = []
        occluded = False
        depsgraph = context.evaluated_depsgraph_get()
        for obj in context.visible_objects:
            if not self.snapshot.owns(context, obj) or obj.type != "MESH":
                continue
            try:
                feature = self.snapshot.bound_feature(context, obj, result)
            except ValueError:
                continue
            for entry in self.catalog.get(feature["id"], []):
                points = [Vector(p) * scale for p in entry["points"]]
                best = None
                for a, b in zip(points, points[1:], strict=False):
                    pa = view3d_utils.location_3d_to_region_2d(self.region, self.rv3d, a)
                    pb = view3d_utils.location_3d_to_region_2d(self.region, self.rv3d, b)
                    if pa is None or pb is None:
                        continue
                    distance, t = nearest_segment(xy, pa, pb)
                    if distance <= 12 and (best is None or distance < best[0]):
                        # Screen interpolation is not world interpolation in perspective.
                        wa = (self.rv3d.perspective_matrix @ a.to_4d()).w
                        wb = (self.rv3d.perspective_matrix @ b.to_4d()).w
                        denominator = wb * (1 - t) + wa * t
                        if wa <= 0 or wb <= 0 or denominator <= 0:
                            continue
                        world_t = t * wa / denominator
                        best = (distance, a.lerp(b, world_t), pa.lerp(pb, t))
                if best is None:
                    continue
                distance, point, pixel = best
                # A ray exactly on a silhouette can miss both adjacent triangles.
                # Subpixel probes allow that boundary, not a hidden edge: an
                # actual foreground hit on the center ray always blocks selection.
                visible = False
                ids = feature["mesh"]["triangle_face_ids"]
                pixel_world = view3d_utils.region_2d_to_location_3d(
                    self.region, self.rv3d, pixel + Vector((1, 0)), point
                )
                tolerance = max(self.deflection * scale * 1.5, scale * 1e-5)
                tolerance += (pixel_world - point).length
                for offset in ((0, 0), (0.75, 0), (-0.75, 0), (0, 0.75), (0, -0.75)):
                    probe = pixel + Vector(offset)
                    origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, probe)
                    direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, probe)
                    hit, location, normal, index, hit_obj, matrix = ray_cast(
                        context, depsgraph, origin, direction
                    )
                    if not hit:
                        continue
                    separation = (point - location).dot(direction)
                    if offset == (0, 0) and (
                        separation > tolerance
                        or (
                            abs(separation) <= tolerance
                            and (hit_obj.original != obj or matrix != obj.matrix_world)
                        )
                    ):
                        occluded = True
                        break
                    # A subpixel shift on a shallow face moves farther in world
                    # space than on the view plane. Bound that foreshortening;
                    # adjacency and the center-ray occlusion check still apply.
                    surface_tolerance = max(self.deflection * scale * 1.5, scale * 1e-5)
                    surface_tolerance += (pixel_world - point).length / max(
                        abs(normal.dot(direction)), 0.1
                    )
                    if (
                        hit_obj.original == obj
                        and matrix == obj.matrix_world
                        and (location - point).length <= surface_tolerance
                        and 0 <= index < len(ids)
                        and ids[index] in entry["faces"]
                    ):
                        visible = True
                        break
                if not visible:
                    continue
                candidates.append((distance, feature["id"], entry, points, obj))
        candidates.sort(key=lambda c: c[0])
        if candidates:
            if len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 3:
                self.overlap_candidates = tuple(
                    row for row in candidates if row[0] - candidates[0][0] < 3
                )
                self.message = (
                    "Ambiguous corner or overlapping edges. Move along the intended edge."
                )
            else:
                _, feature_id, entry, points, obj = candidates[0]
                self.hit = (feature_id, *entry["faces"])
                self.hit_obj, self.points = obj, points
                self.message = (
                    "Click edge; Shift-click starts a set. Enter reviews set. Esc cancels."
                )
        elif occluded:
            self.message = (
                "The edge is behind visible geometry. Isolate the solid or change the view."
            )
        else:
            self.message = (
                "No supported edge here. Some blend/imported faces lack stable support. "
                "F: two-face mode."
            )
        if self.multiple:
            self.message = (
                f"{len(self.selected_edges)} selected: click toggles; Enter reviews. "
                + self.message
            )
        self.area.header_text_set(self.message)
        self.area.tag_redraw()
        return True

    def toggle_edge(self):
        if not self.hit:
            return
        source, first, second = self.hit
        if self.selected_base and source != self.selected_base:
            raise ValueError("Pick all edges on the same input body")
        pair = tuple(sorted((first, second)))
        if pair in self.selected_edges:
            del self.selected_edges[pair]
        else:
            if len(self.selected_edges) >= 64:
                raise ValueError("Select at most 64 edges")
            self.selected_edges[pair] = list(self.points)
        self.selected_base = source
        self.selected_obj = self.hit_obj
        self.multiple = True
        self.area.header_text_set(
            f"{len(self.selected_edges)} orange edges: click toggles; Enter reviews; Esc cancels."
        )
        self.area.tag_redraw()

    def selected_arguments(self, context):
        if not self.current(context):
            raise ValueError("The Part changed; choose the edges again")
        result = self.snapshot.result(context, accepting=True)
        accepted = self.catalog_evidence.revalidate(
            backend_runtime.capture(context),
            owner_token=self.catalog_token,
            expected_action="edge_catalog",
            expected_result_version=self.catalog_version,
            require_success=True,
        )["result"]
        if accepted["catalogs"] != self.catalog or accepted["replay"] != result:
            raise ValueError("Edge evidence changed; choose the edges again")
        feature = self.snapshot.bound_feature(context, self.selected_obj, result)
        if feature["id"] != self.selected_base:
            raise ValueError("Selected edges belong to a different input body")
        pairs = validate_edge_pairs([list(pair) for pair in self.selected_edges])
        available = {
            tuple(sorted(entry["faces"])) for entry in self.catalog.get(self.selected_base, [])
        }
        if any(tuple(pair) not in available for pair in pairs):
            raise ValueError("Selected edges are absent from the exact native catalog")
        return dict(
            kind=self.kind,
            picked_document_json=self.base,
            picked_base=self.selected_base,
            picked_edge_pairs_json=json.dumps(pairs),
        )

    def collect_event(self, context, event):
        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS" and self.multiple:
            return "REVIEW"
        if (
            event.type == "LEFTMOUSE"
            and event.value == "PRESS"
            and (getattr(event, "shift", False) or self.multiple)
        ):
            if not self.hover(context, event, accepting=True):
                return "PASS"
            self.toggle_edge()
            return "TOGGLE"
        return None

    def choose(self):
        return self.hit is not None

    def dialog_arguments(self):
        if not self.hit:
            raise ValueError("Choose one unambiguous supported edge.")
        return dict(
            kind=self.kind,
            picked_document_json=self.base,
            picked_base=self.hit[0],
            picked_face_a=self.hit[1],
            picked_face_b=self.hit[2],
        )

    def draw(self):
        if (
            bpy.context.area != self.area
            or bpy.context.window != self.window
            or not (self.points or self.selected_edges)
        ):
            return
        if self.selected_edges:
            try:
                if not self.current(bpy.context):
                    raise ValueError("Edge selection expired")
                result = self.snapshot.result(bpy.context)
                self.snapshot.bound_feature(bpy.context, self.selected_obj, result)
            except (ValueError, ReferenceError, RuntimeError, AttributeError):
                self.selected_edges.clear()
                self.selected_obj = None
                self.points = []
                return
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        old_depth, old_width = gpu.state.depth_test_get(), gpu.state.line_width_get()
        try:
            gpu.state.depth_test_set("LESS_EQUAL")
            gpu.state.line_width_set(4)
            projection = gpu.matrix.get_projection_matrix().copy()
            for column in range(4):
                projection[2][column] -= 1e-5 * projection[3][column]
            with gpu.matrix.push_pop_projection():
                gpu.matrix.load_projection_matrix(projection)
                shader.bind()
                shader.uniform_float("color", (1.0, 0.55, 0.08, 1.0))
                for points in self.selected_edges.values():
                    batch_for_shader(shader, "LINE_STRIP", {"pos": points}).draw(shader)
                if self.points:
                    shader.uniform_float("color", (0.1, 0.75, 1.0, 1.0))
                    batch_for_shader(shader, "LINE_STRIP", {"pos": self.points}).draw(shader)
        finally:
            gpu.state.depth_test_set(old_depth)
            gpu.state.line_width_set(old_width)


class MCAD_OT_pick_blend_edge(bpy.types.Operator):
    bl_idname = "mcad.pick_blend_edge"
    bl_label = "Pick Edge to Blend"
    bl_description = (
        "Click a supported exact edge, then enter the fillet radius or chamfer distance"
    )
    kind: EnumProperty(items=[("fillet", "Fillet", ""), ("chamfer", "Chamfer", "")])
    poll = MCAD_OT_pick_blend_faces.__dict__["poll"]
    cancel = MCAD_OT_pick_blend_faces.cancel

    def invoke(self, context, event):
        try:
            self._picker = BlendEdgePicker(context, self.kind)
        except Exception as exc:
            self.report({"ERROR"}, str(exc) + " Use Pick Two Faces as a fallback.")
            return {"CANCELLED"}
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        picker = self._picker
        if picker.pending is not None:
            try:
                if event.type in {"ESC", "RIGHTMOUSE"} or not picker.current(context):
                    picker.close()
                    return {"CANCELLED"}
                if event.type == "TIMER":
                    picker.poll_catalog(context)
                return {"PASS_THROUGH"} if event.type != "TIMER" else {"RUNNING_MODAL"}
            except Exception as exc:
                picker.close()
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
        try:
            if event.type in {"ESC", "RIGHTMOUSE"} or not picker.current(context):
                picker.close()
                return {"CANCELLED"}
            collected = picker.collect_event(context, event)
            if collected == "REVIEW":
                if not picker.selected_edges:
                    self.report({"WARNING"}, "Pick at least one edge first")
                    return {"RUNNING_MODAL"}
                arguments = picker.selected_arguments(context)
                picker.close()
                bpy.ops.mcad.add_solid_feature("INVOKE_DEFAULT", **arguments)
                return {"FINISHED"}
            if collected:
                return {"PASS_THROUGH"} if collected == "PASS" else {"RUNNING_MODAL"}
        except Exception as exc:
            picker.close()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if event.type == "F" and event.value == "PRESS":
            self._picker.close()
            bpy.ops.mcad.pick_blend_faces("INVOKE_DEFAULT", kind=self.kind)
            return {"FINISHED"}
        return MCAD_OT_pick_blend_faces.modal(self, context, event)


CLASSES = (MCAD_OT_pick_blend_edge,)
