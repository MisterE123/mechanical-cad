"""Transient all-instance source-update review; only explicit Apply publishes."""

import copy
import math

import bpy
from bpy.types import Operator

from . import assembly_joint_overlay as overlay
from . import assembly_joint_viewport, assembly_pending, assembly_state, execution_lease
from .assembly_joint_draft import transform_points
from .assembly_source_preview_contract import source_preview_fingerprint
from .bridge import BridgeError
from .extrusion_preview_geometry import boundary_edges

_ACTIVE = None
MAX_GHOST_EDGES = 24000


def active(context=None):
    owner = _ACTIVE
    return (
        owner
        if owner and owner.alive and (context is None or owner.light_binding(context))
        else None
    )


def cancel_active(reason="Source update preview cancelled"):
    owner = active()
    if owner:
        owner.cancel(reason)
    return bool(owner)


def _draw_view(owner):
    if owner.draw_context():
        overlay.draw_ghost(owner.ghost_positions)


def _draw_pixel(owner):
    if owner.draw_context():
        try:
            overlay.draw_panel(
                owner.panel_layout(),
                (),
                (),
                hover=owner.hover,
                hint=owner.hint,
                usable_rect=assembly_joint_viewport._safe_rect(owner),
            )
        except (ReferenceError, RuntimeError):
            pass


class SourceUpdatePreview:
    """One scene/window/viewport owner over a detached source-update candidate."""

    def __init__(self, context):
        if active() or assembly_joint_viewport.active():
            raise BridgeError("Finish or cancel the existing Assembly preview first.")
        assembly_state.require_idle(context)
        if execution_lease.is_busy():
            raise BridgeError(execution_lease.BUSY_MESSAGE)
        if context.mode != "OBJECT" or context.area is None or context.area.type != "VIEW_3D":
            raise BridgeError("Open a 3D viewport in Object Mode to preview the source update.")
        if not assembly_state.display_is_current(context):
            raise BridgeError("Rebuild the accepted Assembly before previewing a source update.")
        self.scene, self.window, self.area = context.scene, context.window, context.area
        self.region = next((r for r in self.area.regions if r.type == "WINDOW"), None)
        if self.window is None or self.region is None:
            raise BridgeError("Source update preview requires a live viewport.")
        self.view_layer, self.workspace = context.view_layer, context.window.workspace
        self.manager = context.window_manager
        self.snapshot = assembly_state._capture(context, self.scene)
        self.scale = 0.001 / self.snapshot["scale"]
        self.ui_scale = max(1.0, min(3.0, float(context.preferences.system.ui_scale)))
        self.alive, self.finished, self.committing = True, False, False
        self.pending = None
        self.candidate = None
        self.expectation = None
        self.ghost_positions = ()
        self.affected = []
        self.revisions = ""
        self.page = 0
        self.error, self.hover, self.hint = "", "", ""
        self.message = "Preparing exact source update · accepted display retained"
        self.handlers, self.timer, self.watchdog = [], None, None

    def light_binding(self, context):
        try:
            return bool(
                self.alive
                and context.scene == self.scene
                and context.window == self.window
                and context.view_layer == self.view_layer
                and context.mode == "OBJECT"
                and self.window.workspace == self.workspace
                and self.window in self.manager.windows[:]
                and self.area in self.window.screen.areas[:]
                and self.area.type == "VIEW_3D"
                and self.region in self.area.regions[:]
                and self.scene.mechanical_cad_assembly.document_json
                == self.snapshot["fields"]["document_json"]
                and self.scene.mechanical_cad.document_json == self.snapshot["working_part"]
            )
        except (AttributeError, ReferenceError, RuntimeError):
            return False

    def assert_current(self, context):
        if not self.light_binding(context):
            raise BridgeError("Source update inputs or owning viewport changed. Preview again.")
        assembly_state._assert_current(context, self.snapshot, drafts=True)
        if not assembly_state.display_is_current(context):
            raise BridgeError("Accepted display changed. Rebuild and preview again.")

    def draw_context(self):
        try:
            return (
                self.alive
                and bpy.context.window == self.window
                and bpy.context.area == self.area
                and bpy.context.region == self.region
            )
        except (AttributeError, ReferenceError):
            return False

    def start(self, context):
        global _ACTIVE
        if active():
            raise BridgeError("Another source update preview is active.")
        _ACTIVE = self
        try:
            self.pending = assembly_pending.prepare_source_update_preview(
                context,
                expected_json=self.snapshot["fields"]["document_json"],
                expected_working_part=self.snapshot["working_part"],
            )
            self.candidate = self.pending.request_snapshot()["assembly"]
            original = assembly_state.read_assembly(self.scene.mechanical_cad_assembly)
            old = {p["id"]: p for p in original["parts"]}
            changed = {
                p["id"]
                for p in self.candidate["parts"]
                if p["source_digest"] != old[p["id"]]["source_digest"]
            }
            self.affected = [
                i["name"] for i in self.candidate["instances"] if i["part_id"] in changed
            ]
            first = next(p for p in self.candidate["parts"] if p["id"] in changed)
            self.revisions = (
                old[first["id"]]["source_digest"][:10] + " → " + first["source_digest"][:10]
            )
            for callback, stage in ((_draw_view, "POST_VIEW"), (_draw_pixel, "POST_PIXEL")):
                self.handlers.append(
                    bpy.types.SpaceView3D.draw_handler_add(callback, (self,), "WINDOW", stage)
                )
            self.timer = self.manager.event_timer_add(0.4, window=self.window)
            self.area.header_text_set(
                "Source update preview · all instances together · Apply saves · Esc cancels"
            )

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
                        self.cancel("Source update viewport closed or changed")
                        return None
                except (ReferenceError, AttributeError, RuntimeError):
                    self.cancel("Source update viewport no longer exists")
                    return None
                return 0.5

            self.watchdog = watchdog
            bpy.app.timers.register(watchdog, first_interval=0.5)
            return self
        except Exception:
            self.cancel("Could not start source update preview")
            raise

    def tick(self, context):
        self.assert_current(context)
        if self.pending is not None:
            pending = self.pending
            try:
                response = assembly_pending.poll(context, pending)
                if response is None:
                    return
                self.pending = None
                self._show_response(response)
            except Exception as exc:
                self.pending = None
                self.expectation = None
                self.ghost_positions = ()
                self.error = str(exc)
                self.message = "Preview refused · accepted source retained"
        self.area.tag_redraw()

    def _show_response(self, response):
        fingerprint = source_preview_fingerprint(response)
        parts = {part["id"]: part for part in response["result"]["parts"]}
        instances = response["result"]["instances"]
        transforms = response["report"]["base_pose"]["transforms"]
        allowance = max(1, MAX_GHOST_EDGES // max(1, len(instances)))
        positions = []
        for instance in instances:
            mesh = parts[instance["part_id"]]["mesh"]
            edges = boundary_edges(mesh)
            edges = edges[:: max(1, math.ceil(len(edges) / allowance))]
            vertices = [mesh["vertices"][index] for edge in sorted(edges) for index in edge]
            positions.extend(
                tuple(value * self.scale for value in point)
                for point in transform_points(transforms[instance["id"]], vertices)
            )
        self.ghost_positions = tuple(positions)
        self.expectation = fingerprint
        self.error = ""
        self.message = "Preview ready · not saved or checked"

    def ready(self):
        return bool(self.alive and self.pending is None and self.expectation and not self.error)

    def apply(self, context):
        if self.committing or not self.alive:
            return False
        try:
            self.assert_current(context)
            if not self.ready():
                raise BridgeError("Wait for this exact full source update preview before Apply.")
            self.committing = True
            assembly_state.commit_candidate(
                context,
                copy.deepcopy(self.candidate),
                expected_json=self.snapshot["fields"]["document_json"],
                expected_source_preview=self.expectation,
            )
        except Exception as exc:
            self.error = str(exc)
            self.expectation = None
            self.ghost_positions = ()
            self.message = "Update refused · accepted source retained"
            return False
        finally:
            self.committing = False
        self.finished = True
        self.cancel("Source updated. Run an explicit check again.")
        return True

    def cancel(self, reason="Source update preview cancelled"):
        global _ACTIVE
        self.alive = False
        self.expectation = None
        self.ghost_positions = ()
        self.message = reason
        if _ACTIVE is self:
            _ACTIVE = None
        if self.pending is not None:
            pending, self.pending = self.pending, None
            try:
                assembly_pending.cancel(pending, reason)
            except (ReferenceError, RuntimeError):
                pass
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

    def panel_layout(self):
        left, bottom, right, top = assembly_joint_viewport._safe_rect(self)
        scale = min(self.ui_scale, (right - left) / 360, (top - bottom) / 350)
        if scale < 1:
            return overlay.build_panel((left, bottom, right, top), scale=1)
        x, y = left + 10 * scale, bottom + 327 * scale
        labels = []
        for text in (
            "Update source · not saved / checked",
            self.revisions,
            f"All {len(self.affected)} affected instances update together",
        ):
            labels.append(
                overlay.Label(text, (x, y), overlay.GOLD if not labels else overlay.TEXT, text)
            )
            y -= 20 * scale
        pages = max(1, math.ceil(len(self.affected) / 3))
        page = min(max(0, self.page), pages - 1)
        for name in self.affected[page * 3 : (page + 1) * 3]:
            labels.append(overlay.Label(name, (x, y), overlay.TEXT, name))
            y -= 19 * scale
        for text in (
            "Full geometry + mate placement preview",
            "No contact or dynamics verification",
            self.message,
            self.error,
        ):
            if text:
                labels.append(overlay.Label(text, (x, y), overlay.MUTED, text))
                y -= 19 * scale
        buttons = (
            overlay.Button(
                "previous",
                "‹",
                "Previous affected instances",
                (x, bottom + 57 * scale, x + 35 * scale, bottom + 82 * scale),
                enabled=page > 0,
            ),
            overlay.Button(
                "next",
                f"{page + 1}/{pages} ›",
                "Next affected instances",
                (x + 40 * scale, bottom + 57 * scale, x + 120 * scale, bottom + 82 * scale),
                enabled=page + 1 < pages,
            ),
            overlay.Button(
                "apply",
                "Apply all instances",
                "Freshly replay and save only the exact previewed update",
                (x, bottom + 10 * scale, x + 210 * scale, bottom + 40 * scale),
                enabled=self.ready(),
            ),
            overlay.Button(
                "cancel",
                "Cancel / Esc",
                "Keep the accepted source and every instance",
                (x + 215 * scale, bottom + 10 * scale, x + 340 * scale, bottom + 40 * scale),
            ),
        )
        return overlay.Panel(
            (left, bottom, left + 360 * scale, bottom + 350 * scale),
            buttons,
            tuple(labels),
            scale,
            12 * scale,
        )


class MCAD_OT_assembly_source_update_preview(Operator):
    bl_idname = "mcad.assembly_source_update_preview"
    bl_label = "Preview All-Instance Source Update"
    bl_description = (
        "Review full changed geometry and mate placement before updating all instances together"
    )
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        try:
            self.owner = SourceUpdatePreview(context).start(context)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            if getattr(self, "owner", None):
                self.owner.cancel("Source update invocation failed")
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        owner = self.owner
        if not owner.alive:
            return {"FINISHED"} if owner.finished else {"CANCELLED"}
        if not owner.light_binding(context):
            owner.cancel("Source update context changed")
            return {"CANCELLED"}
        if event.value == "PRESS" and (event.type == "ESC" or event.type == "Z" and event.ctrl):
            owner.cancel()
            return {"CANCELLED", "PASS_THROUGH"} if event.type == "Z" else {"CANCELLED"}
        try:
            if event.type == "TIMER":
                owner.tick(context)
            elif event.type in assembly_joint_viewport.NAVIGATION_EVENTS:
                return {"PASS_THROUGH"}
            else:
                point = assembly_joint_viewport._screen_xy(owner, event)
                panel = owner.panel_layout()
                button = overlay.hit_button(panel, point)
                if event.type == "MOUSEMOVE":
                    owner.hover = button.action if button else ""
                    owner.hint = overlay.hint_at(panel, point)
                if event.type == "LEFTMOUSE" and event.value == "PRESS" and button:
                    if button.action == "cancel":
                        owner.cancel()
                    elif button.enabled and button.action == "apply":
                        owner.apply(context)
                    elif button.enabled:
                        owner.page += 1 if button.action == "next" else -1
                owner.area.tag_redraw()
        except Exception as exc:
            owner.cancel(str(exc))
            self.report({"WARNING"}, str(exc))
        return (
            {"RUNNING_MODAL"}
            if owner.alive
            else ({"FINISHED"} if owner.finished else {"CANCELLED"})
        )

    def cancel(self, context):
        if getattr(self, "owner", None):
            self.owner.cancel()


class MCAD_OT_assembly_source_update_cancel(Operator):
    bl_idname = "mcad.assembly_source_update_cancel"
    bl_label = "Cancel Source Update Preview"

    @classmethod
    def poll(cls, context):
        return active() is not None

    def execute(self, context):
        cancel_active()
        return {"FINISHED"}


CLASSES = (MCAD_OT_assembly_source_update_preview, MCAD_OT_assembly_source_update_cancel)
