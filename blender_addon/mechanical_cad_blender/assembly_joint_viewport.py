"""One transient visual joint editor over the accepted assembly display.

Only Apply calls the existing guarded transaction. Picking, connector movement,
preview and drawing never edit accepted display objects or persist a second
canonical draft. Connector arithmetic is local; independent driver motion uses
guarded asynchronous full-assembly replay, never subtree-only transforms.
"""

import copy
import math
import time

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Vector

from . import assembly_display, execution_lease, workspace
from . import assembly_joint_overlay as overlay
from . import assembly_state as state_api
from .assembly_face_pick import resolve_face
from .assembly_joint_draft import JOINT_KINDS, JointDraft, rotate, surface_frame, transform_points
from .bridge import BridgeError
from .extrusion_preview_geometry import boundary_edges

_ACTIVE = None
MAX_GHOST_EDGES = 24000
NAVIGATION_EVENTS = {
    "MIDDLEMOUSE",
    "WHEELUPMOUSE",
    "WHEELDOWNMOUSE",
    "TRACKPADPAN",
    "TRACKPADZOOM",
    "NDOF_MOTION",
    "NUMPAD_0",
    "NUMPAD_1",
    "NUMPAD_2",
    "NUMPAD_3",
    "NUMPAD_4",
    "NUMPAD_5",
    "NUMPAD_6",
    "NUMPAD_7",
    "NUMPAD_8",
    "NUMPAD_9",
    "NUMPAD_PERIOD",
}


def active(context=None):
    if _ACTIVE is None or not _ACTIVE.alive:
        return None
    if context is not None and not _ACTIVE.light_binding(context):
        return None
    return _ACTIVE


def cancel_active(reason="Joint preview cancelled"):
    owner = active()
    if owner is None:
        return False
    owner.cancel(reason)
    return True


def _pointer(value):
    return value.as_pointer() if value is not None else 0


def _frame_copy(frame):
    return {"xyz_mm": list(frame["xyz_mm"]), "wxyz": list(frame["wxyz"])}


def _screen_xy(owner, event):
    return event.mouse_x - owner.region.x, event.mouse_y - owner.region.y


def _safe_rect(owner):
    left, bottom, right, top = 12.0, 12.0, owner.region.width - 12.0, owner.region.height - 12.0
    for region in owner.area.regions:
        if region.width <= 1 or region.height <= 1:
            continue
        x, y = region.x - owner.region.x, region.y - owner.region.y
        if region.type == "UI":
            right = min(right, x - 12)
        elif region.type == "TOOLS":
            left = max(left, x + region.width + 12)
        elif region.type in {"HEADER", "TOOL_HEADER"}:
            if y < owner.region.height / 2:
                bottom = max(bottom, y + region.height + 12)
            else:
                top = min(top, y - 12)
    return left, bottom, max(left + 1, right), max(bottom + 1, top)


def _project(owner, point_mm):
    point = view3d_utils.location_3d_to_region_2d(
        owner.region, owner.rv3d, Vector(point_mm) * owner.scale
    )
    return tuple(point) if point is not None else None


def _axis_projection(owner, end, axis):
    frame = owner.connector_frames[end]
    origin = _project(owner, frame["xyz_mm"])
    vector = [0.0, 0.0, 0.0]
    vector["XYZ".index(axis)] = 1.0
    direction = rotate(frame["wxyz"], vector)
    point = [a + b for a, b in zip(frame["xyz_mm"], direction, strict=True)]
    tip = _project(owner, point)
    if origin is None or tip is None:
        return None
    return origin, (tip[0] - origin[0], tip[1] - origin[1])


def _screen_handles(owner):
    handles, labels = [], []
    for end, frame in owner.connector_frames.items():
        origin = _project(owner, frame["xyz_mm"])
        if origin is None:
            continue
        selected = owner.selected_connector == end
        # Literal connectors can coincide. Active axes remain pickable on top;
        # their identity is also available in the explicit panel selector.
        labels.append((end.title() + " connector", origin, selected))
        for axis in "XYZ":
            projection = _axis_projection(owner, end, axis)
            if projection is None:
                continue
            start, delta = projection
            length = math.hypot(*delta)
            if length < 1e-8:
                continue
            reach = (72 if selected else 53) * owner.ui_scale
            tip = tuple(a + b * reach / length for a, b in zip(start, delta, strict=True))
            handles.append(overlay.Handle(end, axis, start, tip, selected))
    return tuple(handles), tuple(labels)


def _draw_pixel(owner):
    if not owner.draw_context():
        return
    try:
        owner.panel = owner.panel_layout()
        owner.handles, labels = _screen_handles(owner)
        overlay.draw_panel(
            owner.panel,
            owner.handles,
            labels,
            hover=owner.hover,
            hint=owner.hint,
            usable_rect=_safe_rect(owner),
        )
    except Exception as exc:
        owner.error = "Joint overlay: " + str(exc)


def _draw_view(owner):
    if owner.draw_context():
        overlay.draw_ghost(owner.ghost_positions)


def _nearest_visible_mesh(view_layer, viewport, depsgraph, origin, direction, *, exclude_objects=()):
    """Pick visible base meshes without losing real foreign surface occlusion.

    Scene.ray_cast has no View3D argument and ignores local-view membership.
    This click-only query reads evaluated display geometry; hit faces never become
    CAD identity. Unsupported visible surfaces fail closed rather than allowing a
    pick through them. Focus Assembly isolates the supported accepted mesh set.
    """
    if not math.isfinite(direction.length) or direction.length <= 0:
        raise BridgeError("The viewport did not provide a finite picking ray.")
    direction = direction.normalized()
    objects = tuple(view_layer.objects)
    # Generated instances have separate placement/visibility semantics. The
    # bounded editor does not infer their identity or silently ignore occlusion.
    for instance in depsgraph.object_instances:
        if not instance.is_instance:
            continue
        parent = instance.parent
        original_parent = parent.original if parent is not None else None
        if original_parent not in objects or original_parent.visible_get(
            view_layer=view_layer, viewport=viewport
        ):
            raise BridgeError(
                "Visible generated instances are not supported by joint picking. "
                "Use Focus Assembly to isolate the accepted meshes."
            )
    nearest, nearest_distance, ambiguous = None, math.inf, False
    nonsurface_types = {"EMPTY", "CAMERA", "LIGHT", "LIGHT_PROBE", "ARMATURE", "LATTICE", "SPEAKER"}
    for obj in objects:
        if obj in exclude_objects:
            continue
        if not obj.visible_get(view_layer=view_layer, viewport=viewport):
            continue
        if obj.type in nonsurface_types:
            continue
        if obj.type != "MESH":
            raise BridgeError(
                "Joint picking cannot safely test a visible non-mesh surface. "
                "Use Focus Assembly to isolate the accepted meshes."
            )
        try:
            evaluated = obj.evaluated_get(depsgraph)
            matrix = evaluated.matrix_world.copy()
            inverse = matrix.inverted()
            local_origin = inverse @ origin
            local_direction = inverse.to_3x3() @ direction
            if not math.isfinite(local_direction.length) or local_direction.length <= 0:
                raise ValueError("A visible mesh has an invalid picking transform.")
            hit, location, _normal, _index = evaluated.ray_cast(
                local_origin, local_direction.normalized(), depsgraph=depsgraph
            )
            if not hit:
                continue
            distance = ((matrix @ location) - origin).dot(direction)
            if not math.isfinite(distance):
                raise ValueError("A visible mesh returned a nonfinite picking hit.")
        except (ValueError, RuntimeError, ReferenceError) as exc:
            raise BridgeError(
                "A visible mesh could not be tested safely for joint picking. "
                "Use Focus Assembly or repair the display before picking."
            ) from exc
        if distance < 0:
            continue
        same_depth = math.isclose(distance, nearest_distance, rel_tol=1e-7, abs_tol=1e-8)
        if distance < nearest_distance and not same_depth:
            nearest, nearest_distance, ambiguous = obj, distance, False
        elif same_depth and obj != nearest:
            ambiguous = True
    if ambiguous:
        raise BridgeError("Visible surfaces overlap at this pick. Choose a clear instance surface.")
    return nearest


class JointViewportSession:
    """Scene/window/view-layer-bound UI owner; all model candidates are detached."""

    motion_only = False
    timer_interval = 0.4

    def __init__(self, context, joint_id="", *, mate_faces=False):
        from . import assembly_source_preview_registry

        if assembly_source_preview_registry.active():
            raise BridgeError("Finish or cancel the source update preview first.")
        if active() is not None:
            raise BridgeError("Finish or cancel the open visual joint first.")
        state_api.require_idle(context)
        if execution_lease.is_busy():
            raise BridgeError(execution_lease.BUSY_MESSAGE)
        if context.mode != "OBJECT" or context.area is None or context.area.type != "VIEW_3D":
            raise BridgeError("Open a 3D viewport in Object Mode to edit a visual joint.")
        self.scene, self.window, self.area = context.scene, context.window, context.area
        self.region = next((r for r in self.area.regions if r.type == "WINDOW"), None)
        if self.region is None or self.window is None:
            raise BridgeError("Visual joints require an open 3D viewport window.")
        self.rv3d = self.area.spaces.active.region_3d
        if self.rv3d is None:
            raise BridgeError("Visual joints require a perspective or orthographic 3D view.")
        self.view_layer = context.view_layer
        self.workspace = self.window.workspace
        self.manager = context.window_manager
        self.snapshot = state_api._capture(context, self.scene)
        self.assembly = state_api.read_assembly(self.scene.mechanical_cad_assembly)
        response = state_api.current_display_response(context)
        pose = response["report"]["base_pose"]
        self.accepted_transforms = {
            key: _frame_copy(value) for key, value in pose["transforms"].items()
        }
        self.scale = 0.001 / self.snapshot["scale"]
        self.ui_scale = max(0.5, min(3.0, float(context.preferences.system.ui_scale)))
        self.instances = {item["id"]: item for item in self.assembly["instances"]}
        self.parts = {part["id"]: part for part in response["result"]["parts"]}
        self.owner_id = self.snapshot["fields"]["owner_id"]
        self.owned_meshes = {
            obj.get(assembly_display.INSTANCE_KEY): obj
            for obj in assembly_display.owned_objects(self.scene, self.owner_id)
            if obj.type == "MESH" and obj.get(assembly_display.ROLE_KEY) == "instance"
        }
        self.pick_target = ""
        self._pick_visibility = []
        self.mate_faces = mate_faces
        self.parent_face = None
        self.parent_id = ""
        self.child_id = ""
        self.draft = None
        self.selected_connector = "parent"
        self.alive, self.finished, self.committing = True, False, False
        self.error = ""
        self.message = "Pick the parent instance, then the child instance."
        self.hover, self.hint = "", ""
        self.drag = None
        self.field_raw, self.field_active = "", False
        self.preview_transforms, self.connector_frames = {}, {}
        self.ghost_positions = ()
        self.ghost_edges = {}
        self.panel, self.handles = None, ()
        self.handlers, self.timer = [], None
        self.watchdog = None
        self.navigation = False
        self.surface_pick = False
        if joint_id:
            joint = next((j for j in self.assembly["joints"] if j["id"] == joint_id), None)
            if joint is None:
                raise BridgeError("The selected joint no longer exists.")
            self.parent_id, self.child_id = joint["parent"], joint["child"]
            self.draft = JointDraft(
                self.assembly,
                self.accepted_transforms,
                self.parent_id,
                self.child_id,
                joint_id=joint_id,
                parts=self.parts,
            )
            self.mate_faces = mate_faces or any(
                self.draft.support_id(end) for end in ("parent", "child")
            )
            self.refresh_preview()
        self.assert_current(context)

    def light_binding(self, context):
        try:
            state = self.scene.mechanical_cad_assembly
            return bool(
                self.alive
                and context.scene == self.scene
                and context.window == self.window
                and context.view_layer == self.view_layer
                and self.window.workspace == self.workspace
                and self.window in self.manager.windows[:]
                and self.area in self.window.screen.areas[:]
                and self.area.type == "VIEW_3D"
                and self.region in self.area.regions[:]
                and self.area.spaces.active.region_3d == self.rv3d
                and state.document_json == self.snapshot["fields"]["document_json"]
                and state.owner_id == self.owner_id
                and self.scene.mechanical_cad.document_json == self.snapshot["working_part"]
                and float(self.scene.unit_settings.scale_length) == self.snapshot["scale"]
                and context.mode == "OBJECT"
            )
        except (ReferenceError, AttributeError, RuntimeError):
            return False

    def assert_current(self, context, *, display=False):
        if not self.light_binding(context):
            raise BridgeError(
                "The original joint viewport or accepted assembly changed. Start a fresh edit."
            )
        state_api._assert_current(context, self.snapshot, drafts=True)
        if display and not state_api.display_is_current(context):
            raise BridgeError(
                "The accepted assembly display changed. Replay it before editing joints."
            )

    def draw_context(self):
        try:
            return bool(
                self.alive
                and bpy.context.window == self.window
                and bpy.context.area == self.area
                and bpy.context.region == self.region
            )
        except ReferenceError:
            return False

    def start_resources(self):
        self.handlers.append(
            bpy.types.SpaceView3D.draw_handler_add(_draw_view, (self,), "WINDOW", "POST_VIEW")
        )
        self.handlers.append(
            bpy.types.SpaceView3D.draw_handler_add(_draw_pixel, (self,), "WINDOW", "POST_PIXEL")
        )
        self.timer = self.manager.event_timer_add(self.timer_interval, window=self.window)
        self.area.header_text_set(
            "Visual joint: pick parent / child · drag RGB connector axes · X/Y/Z + number · Esc cancels"
        )

        # Window closure can stop modal events. This bounded watchdog only owns UI
        # resources; it never launches work or resurrects a cancelled edit.
        def watchdog():
            if not self.alive:
                return None
            try:
                if (
                    self.window not in self.manager.windows[:]
                    or self.area not in self.window.screen.areas[:]
                    or self.area.type != "VIEW_3D"
                    or self.window.workspace != self.workspace
                ):
                    self.cancel("Joint viewport closed or changed")
                    return None
            except (ReferenceError, AttributeError, RuntimeError):
                self.cancel("Joint viewport no longer exists")
                return None
            return 0.5

        self.watchdog = watchdog
        bpy.app.timers.register(watchdog, first_interval=0.5)

    def start(self):
        global _ACTIVE
        if active() is not None and active() is not self:
            raise BridgeError("Another visual joint owns the viewport.")
        _ACTIVE = self
        try:
            self.start_resources()
            if self.mate_faces and self.draft is None:
                self.isolate_target()
            self.area.tag_redraw()
        except Exception:
            self.cancel("Could not open the joint viewport")
            raise
        return self

    def cancel(self, reason="Joint preview cancelled"):
        global _ACTIVE
        self.restore_pick_visibility()
        self.alive = False
        self.message = reason
        if _ACTIVE is self:
            _ACTIVE = None
        for handler in self.handlers:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(handler, "WINDOW")
            except (ReferenceError, ValueError, RuntimeError):
                pass
        self.handlers.clear()
        if self.timer is not None:
            try:
                self.manager.event_timer_remove(self.timer)
            except (ReferenceError, ValueError, RuntimeError):
                pass
            self.timer = None
        if self.watchdog is not None:
            try:
                if bpy.app.timers.is_registered(self.watchdog):
                    bpy.app.timers.unregister(self.watchdog)
            except (ReferenceError, ValueError, RuntimeError):
                pass
            self.watchdog = None
        try:
            self.area.header_text_set(None)
            self.area.tag_redraw()
        except (ReferenceError, RuntimeError):
            pass
        self.drag = None
        self.ghost_positions, self.handles = (), ()
        self.connector_frames = {}
        self.field_active = False

    def target_choices(self):
        if self.draft is not None:
            return [getattr(self.draft, self.selected_connector + "_id")]
        if not self.parent_id:
            root = self.assembly["grounded_instance"]
            return [root] + [key for key in self.instances if key != root]
        choices = []
        for key in self.instances:
            if key == self.assembly["grounded_instance"] or key == self.parent_id:
                continue
            descendants = {key}
            for _ in self.instances:
                descendants.update(
                    j["child"] for j in self.assembly["joints"] if j["parent"] in descendants
                )
            if self.parent_id not in descendants:
                choices.append(key)
        return choices

    def restore_pick_visibility(self):
        for obj, hidden in self._pick_visibility:
            try:
                obj.hide_set(hidden, view_layer=self.view_layer)
            except (ReferenceError, RuntimeError):
                pass  # Deleted display objects cannot be resurrected by cleanup.
        self._pick_visibility.clear()
        self.pick_target = ""

    def isolate_target(self, step=0):
        """Temporary view-layer visibility only; never change canonical placement."""
        choices = self.target_choices()
        if not choices:
            self.restore_pick_visibility()
            raise BridgeError(
                "No eligible child for this parent. Use Pick pair and choose another parent."
            )
        index = choices.index(self.pick_target) if self.pick_target in choices else 0
        target = choices[(index + step) % len(choices)]
        if not self._pick_visibility:
            self._pick_visibility = [
                (obj, obj.hide_get(view_layer=self.view_layer))
                for obj in self.owned_meshes.values()
            ]
        try:
            for identifier, obj in self.owned_meshes.items():
                obj.hide_set(identifier != target, view_layer=self.view_layer)
            self.pick_target = target
            self.view_layer.update()
            obj = self.owned_meshes[target]
            if not obj.visible_get(view_layer=self.view_layer, viewport=self.area.spaces.active):
                raise BridgeError(
                    "Target is hidden by its collection or local view. Cancel, use Focus Assembly, then retry."
                )
        except Exception:
            self.restore_pick_visibility()
            raise

    def choose_instance(self, context, instance_id):
        self.assert_current(context, display=True)
        if instance_id not in self.instances or instance_id not in self.owned_meshes:
            raise BridgeError("Pick an existing instance in the current owned assembly display.")
        if not self.parent_id:
            self.parent_id = instance_id
            self.message = "Now pick the child instance. Its incoming joint will be replaced."
            self.error = ""
            return
        draft = JointDraft(
            self.assembly, self.accepted_transforms, self.parent_id, instance_id, parts=self.parts
        )
        self.child_id, self.draft = instance_id, draft
        self.mate_faces = self.mate_faces or any(
            draft.support_id(end) for end in ("parent", "child")
        )
        self.selected_connector = "child"
        self.refresh_preview()

    def select_connector(self, end):
        self.restore_pick_visibility()
        if end not in {"parent", "child"}:
            raise BridgeError("Choose the parent or child connector.")
        self.selected_connector = end
        self.surface_pick = False
        self.drag = None

    def _edit(self, context, operation):
        self.assert_current(context)
        if self.draft is None:
            raise BridgeError("Pick parent and child instances first.")
        previous = {
            key: copy.deepcopy(getattr(self.draft, key))
            for key in (
                "parent_frame",
                "child_frame",
                "kind",
                "coordinate",
                "name",
                "limits",
                "_supports",
                "extra_coordinates",
                "extra_limits",
            )
        }
        try:
            operation()
            self.refresh_preview()
        except Exception:
            for key, value in previous.items():
                setattr(self.draft, key, value)
            self.refresh_preview()
            raise

    def set_kind(self, context, kind):
        self._edit(context, lambda: self.draft.change_kind(kind))

    def clear_motion(self, context):
        """Explicit user action; never an implicit side effect of changing kind."""

        def clear():
            self.draft.coordinate, self.draft.limits = 0.0, None
            self.draft.extra_coordinates = dict.fromkeys(self.draft.extra_coordinates, 0.0)
            self.draft.extra_limits = dict.fromkeys(self.draft.extra_limits)

        self._edit(context, clear)

    def set_distance(self, context, distance_mm):
        value = float(distance_mm)
        if self.draft.kind == "revolute":
            value = math.radians(value)
        if not math.isfinite(value):
            raise BridgeError(
                "Enter a finite motion value (degrees for Revolute; millimetres for Slider)."
            )
        self._edit(context, lambda: setattr(self.draft, "coordinate", value))

    def translate_connector(self, context, end, axis, distance_mm):
        self._edit(context, lambda: self.draft.translate_connector(end, axis, distance_mm))

    def align_connector(self, context, signed_axis):
        self._edit(
            context, lambda: self.draft.align_connector(self.selected_connector, signed_axis)
        )

    def flip_connector(self, context):
        self._edit(context, lambda: self.draft.turn_connector(self.selected_connector, "X", 2))

    def roll_connector(self, context):
        self._edit(context, lambda: self.draft.turn_connector(self.selected_connector, "Z", 1))

    def _prepare_edges(self):
        self.ghost_edges = {}
        identifiers = self.draft.subtree_ids
        allowance = max(1, MAX_GHOST_EDGES // max(1, len(identifiers)))
        for identifier in identifiers:
            mesh = self.parts[self.instances[identifier]["part_id"]]["mesh"]
            edges = boundary_edges(mesh)
            # Bound only after classifying every edge, otherwise sampling triangles
            # would create artificial boundaries along discarded tessellation.
            stride = max(1, math.ceil(len(edges) / allowance))
            edges = edges[::stride]
            self.ghost_edges[identifier] = tuple(
                tuple(mesh["vertices"][index]) for edge in sorted(edges) for index in edge
            )

    def refresh_preview(self):
        if self.draft is None:
            self.preview_transforms, self.connector_frames = {}, {}
            self.ghost_positions = ()
            return
        # Candidate validates bounded tree/frame inputs before any new preview is
        # displayed. None of this is backend geometry or verification evidence.
        self.draft.candidate()
        transforms = self.draft.preview_transforms()
        self.preview_transforms = transforms
        self.connector_frames = {
            end: self.draft.connector_world(end) for end in ("parent", "child")
        }
        if set(self.ghost_edges) != set(self.draft.subtree_ids):
            self._prepare_edges()
        positions = []
        for identifier, vertices in self.ghost_edges.items():
            positions.extend(
                tuple(value * self.scale for value in point)
                for point in transform_points(transforms[identifier], vertices)
            )
        self.ghost_positions = tuple(positions)
        self.error = ""
        self.message = (
            "Preview not checked. Apply replays the joint; run an explicit pose check afterward."
        )

    def apply(self, context):
        if not self.alive or self.committing:
            return False
        self.committing = True
        try:
            self.assert_current(context, display=True)
            if self.draft is None:
                raise BridgeError("Pick both existing instances before Apply.")
            if self.field_active:
                raise BridgeError("Accept or cancel the distance field before Apply.")
            candidate = self.draft.candidate()
            self.restore_pick_visibility()
            state_api.commit_candidate(
                context, candidate, expected_json=self.snapshot["fields"]["document_json"]
            )
        except Exception as exc:
            self.error = str(exc)
            try:
                self.assert_current(context, display=True)
            except Exception:
                self.cancel("Joint edit cancelled because its accepted bindings changed")
            return False
        finally:
            self.committing = False
        self.finished = True
        self.cancel("Joint applied. Replay succeeded; current pose is not checked.")
        return True

    def panel_layout(self):
        original = self.draft.original_joint if self.draft else None
        field = (self.field_raw + "|") if self.field_active else ""
        return overlay.build_panel(
            _safe_rect(self),
            mate_faces=self.mate_faces,
            support_id=self.draft.support_id(self.selected_connector) if self.draft else None,
            target_name=self.instances.get(self.pick_target, {}).get("name", ""),
            target_role=(
                self.selected_connector if self.draft else "child" if self.parent_id else "parent"
            ),
            target_switch=self.draft is None and self.mate_faces,
            scale=self.ui_scale,
            parent_name=self.instances.get(self.parent_id, {}).get("name", ""),
            child_name=self.instances.get(self.child_id, {}).get("name", ""),
            joint_name=self.draft.name if self.draft else "",
            replaced_name=original["name"] if original else "",
            selected=self.selected_connector,
            kind=self.draft.kind if self.draft else "fixed",
            distance=(
                math.degrees(self.draft.coordinate)
                if self.draft.kind == "revolute"
                else self.draft.coordinate
            )
            if self.draft
            else 0.0,
            ready=self.draft is not None,
            error=self.error,
            hint=self.hint,
            field=field,
            connector_xyz=(
                getattr(self.draft, self.selected_connector + "_frame")["xyz_mm"]
                if self.draft
                else None
            ),
        )

    def pick_instance(self, context, point):
        self.assert_current(context, display=True)
        origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, point)
        direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, point)
        original = _nearest_visible_mesh(
            self.view_layer,
            self.area.spaces.active,
            context.evaluated_depsgraph_get(),
            origin,
            direction,
        )
        if original is None:
            raise BridgeError("Click a visible assembly instance mesh.")
        identifier = original.get(assembly_display.INSTANCE_KEY)
        if self.owned_meshes.get(identifier) != original:
            raise BridgeError(
                "A visible object in front is not an instance in this accepted assembly display."
            )
        return identifier

    def pick_face(self, context, point):
        try:
            self.assert_current(context, display=True)
            if not self.pick_target:
                self.isolate_target()
            self._pick_target_face(context, point)
        except Exception:
            self.restore_pick_visibility()
            raise

    def _pick_target_face(self, context, point):
        identifier = self.pick_instance(context, point)
        if identifier != self.pick_target:
            raise BridgeError("Click a face on the named target component.")
        obj = self.owned_meshes[identifier]
        inverse = obj.matrix_world.inverted()
        origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, point)
        direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, point)
        hit, _location, _normal, index = obj.ray_cast(
            inverse @ origin,
            (inverse.to_3x3() @ direction).normalized(),
            depsgraph=context.evaluated_depsgraph_get(),
        )
        if not hit:
            raise BridgeError("The face could not be located. Pick again.")
        face_id = resolve_face(self.parts[self.instances[identifier]["part_id"]], index)
        if self.draft is not None:
            end = self.selected_connector
            if identifier != getattr(self.draft, end + "_id"):
                raise BridgeError("Pick a planar face on the selected " + end + " instance.")
            self._edit(context, lambda: self.draft.attach_face(end, face_id, preserve_offset=True))
            self.surface_pick = False
            self.restore_pick_visibility()
        elif not self.parent_id:
            self.choose_instance(context, identifier)
            self.parent_face = face_id
            self.isolate_target()
        else:
            # Construct detached draft first: a rejected child never leaves a half-pair.
            draft = JointDraft(
                self.assembly,
                self.accepted_transforms,
                self.parent_id,
                identifier,
                parts=self.parts,
            )
            draft.attach_face_pair(self.parent_face, face_id)
            self.child_id, self.draft = identifier, draft
            self.selected_connector = "child"
            self.restore_pick_visibility()
            self.refresh_preview()
        self.hint = "New pair: opposing normals at centroids. Flip reverses; support edits retain offsets. Preview not checked."

    def pick_surface_connector(self, context, point):
        identifier = self.pick_instance(context, point)
        end = self.selected_connector
        if identifier != getattr(self.draft, end + "_id"):
            raise BridgeError("Pick a visible surface on the selected " + end + " instance.")
        obj = self.owned_meshes[identifier].evaluated_get(context.evaluated_depsgraph_get())
        matrix = obj.matrix_world.copy()
        inverse = matrix.inverted()
        origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, point)
        direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, point)
        hit, location, normal, _index = obj.ray_cast(
            inverse @ origin,
            (inverse.to_3x3() @ direction).normalized(),
            depsgraph=context.evaluated_depsgraph_get(),
        )
        if not hit:
            raise BridgeError("The surface moved or could not be sampled. Pick again.")
        world = matrix @ location
        normal = inverse.transposed().to_3x3() @ normal
        frame = surface_frame([v / self.scale for v in world], list(normal))
        self._edit(context, lambda: self.draft.set_connector_world(end, frame))
        self.surface_pick = False
        xyz = getattr(self.draft, end + "_frame")["xyz_mm"]
        self.hint = (
            "Literal local XYZ: " + ", ".join(f"{v:.6g}" for v in xyz) + " mm; not attached to face"
        )

    def begin_drag(self, context, end, axis, point):
        self.assert_current(context)
        if self.draft is None:
            raise BridgeError("Pick both instances before moving a connector.")
        self.selected_connector = end
        self.drag = {
            "end": end,
            "axis": axis,
            "start": tuple(point),
            "frame": _frame_copy(getattr(self.draft, end + "_frame")),
            "raw": "",
            "distance": 0.0,
        }
        self.error = ""

    def move_drag(self, context, point, *, distance=None):
        if self.drag is None:
            return
        if not self.light_binding(context):
            raise BridgeError("The accepted assembly changed during connector movement.")
        drag = self.drag
        previous = _frame_copy(getattr(self.draft, drag["end"] + "_frame"))
        setattr(self.draft, drag["end"] + "_frame", _frame_copy(drag["frame"]))
        try:
            if distance is None:
                # Project the baseline connector, not its moving screen position.
                frame = self.draft.connector_world(drag["end"])
                vector = [0.0, 0.0, 0.0]
                vector["XYZ".index(drag["axis"])] = 1.0
                direction = rotate(frame["wxyz"], vector)
                a = _project(self, frame["xyz_mm"])
                b = _project(self, [u + v for u, v in zip(frame["xyz_mm"], direction, strict=True)])
                if a is None or b is None or math.dist(a, b) < 1e-5:
                    raise BridgeError(
                        "This axis points into the view. Rotate the view, or type an exact distance."
                    )
                delta = (b[0] - a[0], b[1] - a[1])
                distance = sum(
                    (p - s) * d for p, s, d in zip(point, drag["start"], delta, strict=True)
                ) / sum(d * d for d in delta)
            self.draft.translate_connector(drag["end"], drag["axis"], distance)
            self.refresh_preview()
            drag["distance"] = distance
            self.hint = f"{drag['end'].title()} {drag['axis']}: {distance:.6g} mm · Enter accepts"
        except Exception:
            setattr(self.draft, drag["end"] + "_frame", previous)
            self.refresh_preview()
            raise

    def click_action(self, context, action):
        if action == "cancel":
            self.cancel()
        elif action == "apply":
            self.apply(context)
        elif action in {"target_prev", "target_next"}:
            self.assert_current(context, display=True)
            self.isolate_target(-1 if action == "target_prev" else 1)
        elif action == "reselect":
            self.assert_current(context)
            self.restore_pick_visibility()
            self.parent_id = self.child_id = ""
            self.parent_face = None
            self.surface_pick = False
            self.draft = None
            self.drag = None
            self.field_active = False
            self.refresh_preview()
            if self.mate_faces:
                self.isolate_target()
        elif action in {"parent", "child"}:
            self.select_connector(action)
        elif action in JOINT_KINDS:
            self.set_kind(context, action)
        elif action == "surface":
            if self.mate_faces:
                self.isolate_target()
            self.surface_pick = True
            self.drag = None
            self.hint = (
                "Pick a stable planar face; origin = centroid, +Z = normal"
                if self.mate_faces
                else "Click selected instance surface: literal coordinates, not persistent face attachment"
            )
        elif action == "origin":
            end = self.selected_connector
            self._edit(
                context,
                lambda: setattr(
                    self.draft,
                    end + "_frame",
                    {"xyz_mm": [0.0, 0.0, 0.0], "wxyz": [1.0, 0.0, 0.0, 0.0]},
                ),
            )
        elif action.startswith("axis_"):
            self.align_connector(context, "+" + action[-1])
        elif action == "flip":
            self.flip_connector(context)
        elif action == "roll":
            self.roll_connector(context)
        elif action == "clear_motion":
            self.clear_motion(context)
        elif action == "distance":
            self.drag = None
            self.field_active, self.field_raw = True, ""
            self.hint = "Type degrees for Revolute or mm for Slider; Enter accepts. Esc cancels."
        elif action in {"minus", "plus"}:
            value = (
                math.degrees(self.draft.coordinate)
                if self.draft.kind == "revolute"
                else self.draft.coordinate
            )
            self.set_distance(context, value + (-1 if action == "minus" else 1))


class MotionViewportSession(JointViewportSession):
    """Debounced full-assembly replay ghosts over an untouched accepted display."""

    motion_only = True
    debounce_seconds = 0.18
    timer_interval = 0.08

    def __init__(self, context, joint_id):
        from .assembly_motion_draft import MotionDraft

        super().__init__(context)
        self.draft = MotionDraft(self.assembly, joint_id)
        self.parent_id, self.child_id = self.draft.parent_id, self.draft.child_id
        self.pending = None
        self._queued = False
        self._ready_candidate = self._ready_pose = None
        self._submitted_candidate = None
        self.refresh_preview()

    def start_resources(self):
        super().start_resources()
        self.area.header_text_set(
            "Slider motion: exact mm / ±1 mm · full assembly preview · Apply saves · Esc cancels"
            if self.draft.kind == "slider" else
            "Driver motion: exact degrees / ±1° · full assembly preview · Apply saves · Esc cancels"
        )

    def _clear_preview(self):
        from . import assembly_pending

        self._ready_candidate = self._ready_pose = None
        self.preview_transforms = {}
        self.ghost_positions = ()
        self.ghost_edges = {}
        if self.pending is not None and not self.pending.done:
            assembly_pending.cancel(self.pending, "Superseded motion preview")

    def refresh_preview(self):
        self._clear_preview()
        self._queued = False
        try:
            self.draft.candidate()
        except Exception as exc:
            self.error = str(exc)
            self.message = ("Invalid slide" if self.draft.kind == "slider" else "Invalid angle") + " · accepted display retained"
            raise
        self.error = ""
        self.message = "Pending · accepted display retained"
        self._queued = True
        self._deadline = time.monotonic() + self.debounce_seconds

    def set_distance(self, context, distance_mm):
        self.assert_current(context, display=True)
        value = float(distance_mm)
        self.draft.coordinate = math.radians(value) if self.draft.kind == "revolute" else value
        self.refresh_preview()

    def tick(self, context):
        from . import assembly_job_ui, assembly_pending

        self.assert_current(context, display=True)
        if self.pending is not None:
            pending = self.pending
            try:
                response = assembly_pending.poll(context, pending)
            except Exception as exc:
                if not self._queued and not self.field_active:
                    self.error = str(exc)
                    self.message = "Preview failed · accepted display retained"
                response = None
            if response is not None and not self._queued:
                # Final UI-owner guard supplements the request/receipt guard.
                self.assert_current(context, display=True)
                if self._submitted_candidate != self.draft.candidate() or self.field_active:
                    raise BridgeError("Motion intent changed before preview display.")
                self._show_response(response)
            if pending.done:
                self.pending = None
        if self.pending is None and self._queued and time.monotonic() >= self._deadline:
            self._queued = False  # one attempt per user input, never an automatic retry
            try:
                self._submitted_candidate = self.draft.candidate()
                self.pending = assembly_pending.prepare_motion_preview(
                    context,
                    self.draft.joint_id,
                    self.draft.coordinate,
                    expected_json=self.snapshot["fields"]["document_json"],
                )
                assembly_job_ui.ensure_supervisor()
                self.message = "Evaluating all branches · accepted display retained"
            except Exception as exc:
                self.error = str(exc)
                self.message = "Preview failed · change coordinate or reopen to retry"
        self.area.tag_redraw()

    def _show_response(self, response):
        parts = {part["id"]: part for part in response["result"]["parts"]}
        transforms = response["report"]["base_pose"]["transforms"]
        positions = []
        allowance = max(1, MAX_GHOST_EDGES // max(1, len(self.instances)))
        for identifier, instance in self.instances.items():
            mesh = parts[instance["part_id"]]["mesh"]
            edges = boundary_edges(mesh)
            edges = edges[:: max(1, math.ceil(len(edges) / allowance))]
            vertices = [mesh["vertices"][index] for edge in sorted(edges) for index in edge]
            positions.extend(
                tuple(value * self.scale for value in point)
                for point in transform_points(transforms[identifier], vertices)
            )
        self.preview_transforms = copy.deepcopy(transforms)
        self.ghost_positions = tuple(positions)
        self._ready_candidate = copy.deepcopy(self._submitted_candidate)
        self._ready_pose = copy.deepcopy(response["report"]["base_pose"])
        self.error = ""
        self.message = "Preview ready · not saved or checked"

    def ready(self):
        if self.field_active or self.pending is not None or self._queued or self.error:
            return False
        try:
            return self._ready_pose is not None and self._ready_candidate == self.draft.candidate()
        except ValueError:
            return False

    def apply(self, context):
        if not self.alive or self.committing:
            return False
        try:
            self.assert_current(context, display=True)
            if not self.ready():
                raise BridgeError("Wait for this exact coordinate's full preview before Apply.")
            self.committing = True
            state_api.commit_candidate(
                context,
                self.draft.candidate(),
                expected_json=self.snapshot["fields"]["document_json"],
                expected_preview=self._ready_pose,
            )
        except Exception as exc:
            self.error = str(exc)
            self._queued = False
            self._clear_preview()
            try:
                self.assert_current(context, display=True)
            except Exception:
                self.cancel("Motion preview bindings changed")
            return False
        finally:
            self.committing = False
        self.finished = True
        self.cancel("Driver motion applied. Run an explicit pose check.")
        return True

    def cancel(self, reason="Driver motion preview cancelled"):
        self._queued = False
        self._clear_preview()
        super().cancel(reason)

    def click_action(self, context, action):
        if action == "distance":
            self._clear_preview()
            self._queued = False
            self.message = ("Enter slide distance (mm)" if self.draft.kind == "slider" else "Enter driver angle") + " · accepted display retained"
        if action not in {"distance", "minus", "plus", "cancel", "apply"}:
            raise BridgeError("Connector editing is unavailable in driver-motion mode.")
        super().click_action(context, action)

    def panel_layout(self):
        followers = ""
        if self._ready_pose is not None:
            values = self._ready_pose["effective_coordinates"]
            controlled = [j for j in self.assembly["joints"] if j.get("coordinate") is None]
            followers = "; ".join(
                f"{j['name']}: {math.degrees(values[j['id']]):.5g}°" for j in controlled
            )
        return overlay.build_motion_panel(
            _safe_rect(self),
            scale=self.ui_scale,
            name=self.draft.name + " / " + self.instances[self.child_id]["name"],
            kind=self.draft.kind,
            angle=math.degrees(self.draft.coordinate) if self.draft.kind == "revolute" else 0.0,
            distance=self.draft.coordinate if self.draft.kind == "slider" else 0.0,
            field=(self.field_raw + "|") if self.field_active else "",
            ready=self.ready(),
            status=self.message,
            error=self.error,
            followers=followers,
        )


def _numeric_event(owner, context, event, point):
    if event.value != "PRESS":
        return False
    raw = owner.field_raw if owner.field_active else owner.drag["raw"] if owner.drag else None
    if raw is None:
        return False
    if event.type in {"RET", "NUMPAD_ENTER"}:
        if owner.field_active:
            owner.set_distance(context, float(raw))
            owner.field_active = False
        else:
            if raw:
                owner.move_drag(context, point, distance=float(raw))
            owner.drag = None
        owner.hint = ""
        return True
    if event.type == "BACK_SPACE":
        raw = raw[:-1]
    else:
        text = getattr(event, "unicode", "") or getattr(event, "ascii", "")
        if not text or text not in "0123456789.+-eE" or len(raw) >= 48:
            return False
        raw += text
    if owner.field_active:
        owner.field_raw = raw
    else:
        owner.drag["raw"] = raw
        try:
            value = float(raw)
        except ValueError:
            owner.hint = "Distance: " + raw + " mm · Enter accepts"
        else:
            owner.move_drag(context, point, distance=value)
    return True


class MCAD_OT_assembly_visual_joint(Operator):
    bl_idname = "mcad.assembly_visual_joint"
    bl_label = "Visual Joint"
    bl_description = "Pick two existing assembly instances and move literal connector handles before applying an existing Assembly joint kind"
    bl_options = {"REGISTER", "UNDO"}
    joint_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    mate_faces: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})
    motion_only: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return bool(
            context.mode == "OBJECT"
            and context.area
            and context.area.type == "VIEW_3D"
            and getattr(context.scene, "mechanical_cad_assembly", None)
            and context.scene.mechanical_cad_assembly.document_json
            and active() is None
            and not execution_lease.is_busy()
            and not workspace.active_draft()
        )

    def execute(self, context):
        return self.invoke(context, None)

    def invoke(self, context, event):
        try:
            data = state_api.read_assembly(context.scene.mechanical_cad_assembly)
            if data.get("gear_relations") and not getattr(self, "motion_only", False):
                raise BridgeError(
                    "Use named Mate Frame edits and joint angles for gear-coupled assemblies; "
                    "visual connector editing is unavailable. Use Preview Driver Motion for independent angles."
                )
            if getattr(self, "motion_only", False):
                if self.mate_faces:
                    raise BridgeError("Driver-motion preview cannot edit connectors.")
                self.owner = MotionViewportSession(context, self.joint_id)
            else:
                self.owner = JointViewportSession(
                    context, self.joint_id, mate_faces=self.mate_faces
                )
            self.owner.start()
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            if getattr(self, "owner", None):
                self.owner.cancel(str(exc))
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        owner = self.owner
        if not owner.alive:
            return {"FINISHED"} if owner.finished else {"CANCELLED"}
        if not owner.light_binding(context):
            owner.cancel("Original joint editing context changed")
            return {"CANCELLED"}
        try:
            if event.type == "ESC" and event.value == "PRESS":
                owner.cancel()
                return {"CANCELLED"}
            if event.type == "Z" and event.ctrl and event.value == "PRESS":
                owner.cancel("Joint preview discarded before Undo / Redo")
                return {"CANCELLED", "PASS_THROUGH"}
            if event.type == "TIMER":
                if owner.motion_only:
                    owner.tick(context)
                else:
                    owner.assert_current(context)
                owner.area.tag_redraw()
                return {"RUNNING_MODAL"}
            point = _screen_xy(owner, event)
            # Cancel remains actionable while raw numeric input owns the other
            # keys/clicks, including incomplete or invalid text. Do not parse or
            # accept that text merely to discard the transient editor.
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                button = overlay.hit_button(owner.panel_layout(), point)
                if button is not None and button.action == "cancel":
                    owner.cancel()
                    return {"CANCELLED"}
            if event.type in NAVIGATION_EVENTS and not (
                owner.field_active and event.type.startswith("NUMPAD_")
            ):
                if owner.drag is not None:
                    owner.drag = None
                    owner.hint = ""
                if event.type == "MIDDLEMOUSE":
                    owner.navigation = event.value != "RELEASE"
                return {"PASS_THROUGH"}
            if _numeric_event(owner, context, event, point):
                owner.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if owner.field_active:
                # Keep incomplete raw text local; never leak transform hotkeys.
                return {"RUNNING_MODAL"}
            if not overlay.inside(point, _safe_rect(owner)):
                return {"PASS_THROUGH"}
            panel = owner.panel_layout()
            button = overlay.hit_button(panel, point)
            if event.type == "MOUSEMOVE" and not owner.navigation:
                if owner.drag is not None and not owner.drag["raw"]:
                    owner.move_drag(context, point)
                else:
                    owner.hover = button.action if button else ""
                    owner.hint = overlay.hint_at(panel, point)
            elif (
                event.type in {"X", "Y", "Z"}
                and event.value == "PRESS"
                and not event.ctrl
                and not event.alt
                and owner.draft is not None
                and not owner.motion_only
            ):
                if owner.drag:
                    owner.drag["axis"] = event.type
                    owner.move_drag(
                        context,
                        point,
                        distance=float(owner.drag["raw"]) if owner.drag["raw"] else None,
                    )
                else:
                    owner.begin_drag(context, owner.selected_connector, event.type, point)
            elif event.type == "LEFTMOUSE" and event.value == "PRESS":
                if owner.drag is not None:
                    owner.assert_current(context)
                    owner.drag = None
                elif button is not None:
                    if button.enabled:
                        owner.click_action(context, button.action)
                elif not overlay.inside(point, panel.bounds):
                    handles, _labels = _screen_handles(owner)
                    handle = overlay.pick_handle(handles, point, scale=owner.ui_scale)
                    if owner.surface_pick and owner.draft is not None:
                        if owner.mate_faces:
                            owner.pick_face(context, point)
                        else:
                            owner.pick_surface_connector(context, point)
                    elif handle:
                        owner.begin_drag(context, handle.end, handle.axis, point)
                    elif owner.draft is None:
                        if owner.mate_faces:
                            owner.pick_face(context, point)
                        else:
                            owner.choose_instance(context, owner.pick_instance(context, point))
            elif (
                event.type == "LEFTMOUSE"
                and event.value == "RELEASE"
                and owner.drag is not None
                and not owner.drag["raw"]
            ):
                owner.assert_current(context)
                owner.drag = None
            owner.area.tag_redraw()
        except Exception as exc:
            owner.restore_pick_visibility()
            owner.error = str(exc)
            try:
                owner.assert_current(context)
            except Exception:
                owner.cancel("Joint editing context changed")
                self.report({"WARNING"}, str(exc))
                return {"CANCELLED"}
            owner.area.tag_redraw()
        if not owner.alive:
            if owner.finished:
                self.report(
                    {"INFO"}, "Joint applied. Run an explicit pose check before checked export."
                )
            return {"FINISHED"} if owner.finished else {"CANCELLED"}
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        if getattr(self, "owner", None):
            self.owner.cancel("Joint tool ended")


class MCAD_OT_assembly_visual_joint_cancel(Operator):
    bl_idname = "mcad.assembly_visual_joint_cancel"
    bl_label = "Cancel Joint Preview"
    bl_description = "Discard transient visual joint edits without changing the accepted assembly"

    @classmethod
    def poll(cls, context):
        return active() is not None

    def execute(self, context):
        cancel_active("Joint preview cancelled")
        return {"FINISHED"}


CLASSES = (MCAD_OT_assembly_visual_joint, MCAD_OT_assembly_visual_joint_cancel)
