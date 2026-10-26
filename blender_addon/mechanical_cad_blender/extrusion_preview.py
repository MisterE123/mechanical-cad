"""Disposable, exact sidecar feature previews; never canonical scene objects.

The original display is untouched. A cyan boundary overlay represents the proposed
active solid, not a selectable or exportable shape. Apply requests fresh guarded
work and uses the existing atomic Part publication seam, never preview evidence.
"""

import json
import math
import time

import bpy

from . import (
    assembly_job_ui,
    backend_contracts,
    backend_runtime,
    execution_lease,
    operation_contracts,
    sketch_pending,
    staged_edit_store,
)
from .extrusion_preview_geometry import boundary_edges, focus_parameters, preview_bounds
from .feature_guidance import feature_error
from .part_publication import PartPublicationIntent

_OWNERS = []
DEBOUNCE = 0.3
MAX_PREVIEW_TRIANGLES = 200_000


def _key(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def cancel_all(reason="Feature preview retired"):
    for owner in tuple(_OWNERS):
        owner.close(reason)


class Preview:
    def __init__(self, operator, context):
        self.operator = operator
        self.window = context.window
        self.area = context.area
        self.scene = context.scene
        self.workspace = context.workspace
        self.view_layer = context.view_layer
        self.base = self.scene.mechanical_cad.document_json
        self.scale = self.scene.unit_settings.scale_length
        self.owner_token = object()
        self.pending = None
        self.publication = None
        self.batch = None
        self.bounds = None
        self.shader = None
        self.handler = None
        self.status_handler = None
        self.timer = None
        self.closed = False
        self.applying = False
        self.key = None
        self.changed = time.monotonic()
        self.message = "Preview pending (cyan outline); original model unchanged"
        self.error = ""
        self.completed = False
        self.accepted = False
        # Bind before the debounce window, not only when native work first starts.
        self.selection = backend_runtime.capture(context)
        self.identity = None
        _OWNERS.append(self)

    def valid(self, context):
        return (
            not self.closed
            and self.window in tuple(context.window_manager.windows)
            and self.window.scene == self.scene
            and self.window.workspace == self.workspace
            and context.scene == self.scene
            and self.window.view_layer == self.view_layer
            and context.view_layer == self.view_layer
            and self.area.type == "VIEW_3D"
            and self.area in tuple(self.window.screen.areas)
            and self.scene.mechanical_cad.document_json == self.base
            and self.scene.unit_settings.scale_length == self.scale
            and context.mode == "OBJECT"
        )

    def invalidate(self):
        self.batch = None
        self.bounds = None
        if self.pending is not None:
            sketch_pending.cancel(self.pending, "Feature input changed")
            self.pending = None
            assembly_job_ui.ensure_supervisor()
        if self.publication is not None:
            self.publication.retire()
            self.publication = None

    def close(self, reason="Preview cancelled"):
        if self.closed:
            return
        self.closed = True
        self.invalidate()
        if self.handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handler, "WINDOW")
            self.handler = None
        if self.status_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.status_handler, "WINDOW")
            self.status_handler = None
        if self.timer is not None:
            bpy.context.window_manager.event_timer_remove(self.timer)
            self.timer = None
        if self in _OWNERS:
            _OWNERS.remove(self)
        self.message = reason
        self.redraw()
        self.operator = None

    def redraw(self):
        try:
            for area in self.window.screen.areas:
                area.tag_redraw()
        except (ReferenceError, AttributeError, RuntimeError):
            pass

    def draw_status(self):
        """Popup text is cached by Blender; viewport status is genuinely live."""
        context = bpy.context
        if context.area != self.area or context.window != self.window or not self.valid(context):
            return
        import textwrap

        import blf

        blf.size(0, 13)
        color = (
            (1.0, 0.65, 0.2, 1.0) if self.message.startswith("No current") else (0.1, 0.9, 1.0, 1.0)
        )
        blf.color(0, *color)
        sidebar = next((r.width for r in self.area.regions if r.type == "UI"), 0)
        width = max(28, min(90, (context.region.width - sidebar - 150) // 7))
        for index, line in enumerate(textwrap.wrap("PREVIEW: " + self.message, width=width)):
            blf.position(0, 110, context.region.height - 80 - 19 * index, 0)
            blf.draw(0, line)

    def draw_wire(self):
        context = bpy.context
        if self.batch is None or not self.valid(context) or context.window != self.window:
            return
        import gpu

        previous = gpu.state.depth_test_get()
        try:
            gpu.state.depth_test_set("NONE")
            self.shader.bind()
            self.shader.uniform_float("color", (0.05, 0.85, 1.0, 1.0))
            self.batch.draw(self.shader)
        finally:
            gpu.state.depth_test_set(previous)

    def overlay(self, response, candidate):
        result = response["result"]
        feature = next(f for f in result["features"] if f["id"] == candidate["active_feature"])
        mesh = feature["mesh"]
        if not mesh or len(mesh["triangles"]) > MAX_PREVIEW_TRIANGLES:
            raise ValueError("Preview unavailable: mesh exceeds interactive wire limit")
        import gpu
        from gpu_extras.batch import batch_for_shader

        scale = 0.001 / self.scale
        vertices = [tuple(v * scale for v in p) for p in mesh["vertices"]]
        try:
            bounds = preview_bounds(vertices)
        except ValueError:
            bounds = None  # Unsupported framing must not change preview acceptance.
        edges = boundary_edges(mesh)
        self.shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        self.batch = batch_for_shader(self.shader, "LINES", {"pos": vertices}, indices=list(edges))
        self.bounds = bounds
        if self.handler is None:
            self.handler = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_wire, (), "WINDOW", "POST_VIEW"
            )

    def configuration(self, context):
        """Keep the dialog bound to one backend even when edited input changes."""
        try:
            selection, deflection = backend_runtime.configuration(context)
            if not self.valid(context):
                raise ValueError("Feature context changed; reopen the feature dialog")
            if self.selection is not None:
                self.selection.assert_current(selection)
        except Exception:
            self.close("Backend or feature context changed; reopen the feature dialog")
            raise
        self.selection = selection
        return selection, deflection

    def tick(self, context):
        staged_edit_store.require_no_resume()
        if not self.valid(context):
            raise ValueError("Document, window, units or mode changed; reopen the feature dialog")
        candidate = self.operator.preview_candidate(context)
        selection, deflection = self.configuration(context)
        signature = _key(candidate)
        if self.key != signature:
            if self.applying and self.key is not None:
                raise ValueError("Feature input changed during Apply; reopen the feature dialog")
            self.invalidate()
            self.key = signature
            self.completed = False
            self.changed = time.monotonic()
            self.message = "Preview pending; original model unchanged"
        if self.pending is None:
            if self.completed or (not self.applying and time.monotonic() - self.changed < DEBOUNCE):
                return
            if execution_lease.is_busy():
                self.message = "Waiting for native cleanup; no current preview"
                return
            request = {
                "protocol_version": 1,
                "action": "replay",
                "result_version": operation_contracts.result_version_for(candidate),
                "document": candidate,
                "options": {"linear_deflection": deflection},
            }
            if self.applying:
                self.publication = PartPublicationIntent(
                    context,
                    request,
                    selection,
                    self.scene.mechanical_cad.document_path,
                    owner_token=self.owner_token,
                )
                prepared = self.publication.prepared
            else:
                prepared = backend_contracts.prepare_request(request)
            self.identity = {"base": self.base, "intent": signature, "scale": self.scale}
            # Identity is bounded separately: retain digests, not a second document.
            import hashlib

            self.identity = {
                k: hashlib.sha256(str(v).encode()).hexdigest() for k, v in self.identity.items()
            }
            assembly_job_ui.ensure_supervisor()
            self.pending = sketch_pending.prepare_guarded(
                prepared,
                self.identity,
                selection=selection,
                owner_token=self.owner_token,
            )
            self.message = (
                "Applying exact feature…"
                if self.applying
                else "Building preview; original model unchanged"
            )
            return
        evidence = sketch_pending.poll(self.pending, self.identity, current_selection=selection)
        if evidence is None:
            return
        self.pending = None
        try:
            response = evidence.revalidate(
                selection,
                owner_token=self.owner_token,
                expected_action="replay",
                expected_result_version=operation_contracts.result_version_for(candidate),
                require_success=False,
            )
            # Failed replay is diagnostic evidence only. Never draw or publish
            # partial geometry, but retain the actual native failure and remedy.
            if not evidence.successful:
                failed = next((f for f in response["result"]["features"] if f.get("error")), None)
                detail = failed["error"]["message"] if failed else "Exact rebuild failed"
                raise ValueError(feature_error(getattr(self.operator, "kind", ""), detail))
            if self.applying:
                if not self.publication.publish(context, evidence):
                    raise ValueError("Feature could not be applied")
                self.completed = True
                self.accepted = True
            else:
                self.overlay(response, candidate)
                self.message = "Cyan outline: proposed result, not applied"
                self.completed = True
        finally:
            evidence.publication.cancel()
        self.redraw()


def start(operator, context):
    staged_edit_store.require_no_resume()
    cancel_all("Another feature preview dialog opened")
    owner = Preview(operator, context)
    operator._extrusion_preview = owner
    owner.status_handler = bpy.types.SpaceView3D.draw_handler_add(
        owner.draw_status, (), "WINDOW", "POST_PIXEL"
    )
    owner.redraw()

    def timer():
        if owner.closed:
            return None
        try:
            with bpy.context.temp_override(window=owner.window, area=owner.area):
                if not owner.valid(bpy.context):
                    raise ValueError("Feature window or document changed")
                # Applying belongs exclusively to the modal Undo transaction.
                # Keep supervising it so a lost window cannot strand a ready job.
                if not owner.applying:
                    owner.tick(bpy.context)
        except Exception as exc:
            owner.invalidate()
            owner.message = "No current preview: " + str(exc)[:400]
            owner.completed = True
            # Lost owners must release RNA/draw resources, not just mark failure.
            try:
                if not owner.valid(bpy.context):
                    owner.close(owner.message)
                    return None
            except Exception:
                owner.close(owner.message)
                return None
        owner.redraw()
        return 0.1

    bpy.app.timers.register(timer, first_interval=DEBOUNCE)
    return owner


def changed(operator, context):
    owner = getattr(operator, "_extrusion_preview", None)
    if owner and not owner.closed:
        # Help/status UI and passive status-property refreshes are not geometry
        # edits. Never cancel/replay an unchanged canonical candidate for them.
        try:
            if _key(operator.preview_candidate(context)) == owner.key:
                return True
        except Exception:
            pass  # Invalid edited input must still retire the previous outline.
        owner.invalidate()
        owner.key = None
        owner.completed = False
        owner.changed = time.monotonic()
        owner.message = "Preview pending; original model unchanged"
    return True


def draw(operator):
    owner = getattr(operator, "_extrusion_preview", None)
    if owner:
        operator.layout.label(
            text="Live preview status appears at the top of the viewport.", icon="INFO"
        )
        operator.layout.label(
            text="Cyan outline is proposed geometry. Accepted geometry stays visible."
        )
        operator.layout.operator("mcad.focus_preview", text="Focus Preview", icon="VIEWZOOM")


def cancel(operator, context):
    owner = getattr(operator, "_extrusion_preview", None)
    if owner:
        owner.close()


def apply(operator, context):
    owner = getattr(operator, "_extrusion_preview", None)
    if owner is None or (owner.closed and owner.accepted):
        # EXEC_DEFAULT/script calls retain the established synchronous API.
        return None
    if not owner.valid(context):
        owner.close()
        raise ValueError("Document changed; reopen the feature dialog")
    owner.configuration(context)
    owner.invalidate()
    owner.key = _key(operator.preview_candidate(context))
    owner.completed = False
    owner.applying = True
    owner.timer = context.window_manager.event_timer_add(0.1, window=context.window)
    context.window_manager.modal_handler_add(operator)
    return {"RUNNING_MODAL"}


def modal(operator, context, event):
    owner = operator._extrusion_preview
    if event.type == "ESC" or owner.closed:
        owner.close()
        return {"CANCELLED"}
    if event.type != "TIMER":
        return {"RUNNING_MODAL"}
    try:
        owner.tick(context)
        if owner.completed:
            owner.close("Applied")
            return {"FINISHED"}
    except Exception as exc:
        owner.close()
        operator.report({"ERROR"}, str(exc)[:1000])
        return {"CANCELLED"}
    return {"RUNNING_MODAL"}


def focus(context):
    """Explicit view navigation only; never select, evaluate, accept or publish."""
    owners = [owner for owner in _OWNERS if owner.window == context.window
              and owner.area == context.area and owner.valid(context)]
    if len(owners) != 1:
        raise ValueError("No current preview belongs to this viewport")
    owner = owners[0]
    if (owner.applying or owner.pending is not None or not owner.completed
            or owner.batch is None or owner.bounds is None):
        raise ValueError("Wait for a completed current preview before focusing")
    owner.configuration(context)
    if owner.key != _key(owner.operator.preview_candidate(context)):
        raise ValueError("Preview input changed; wait for its fresh outline")
    space = owner.area.spaces.active
    if space.type != "VIEW_3D" or space.region_quadviews:
        raise ValueError("Focus Preview needs its single owning 3D viewport")
    region = next((r for r in owner.area.regions if r.type == "WINDOW"), None)
    view = space.region_3d
    if region is None or region.width <= 0 or region.height <= 0 or view is None:
        raise ValueError("The preview viewport is unavailable")
    center, distance = focus_parameters(
        owner.bounds, space.lens, 0.45 * region.width / region.height, view.view_perspective,
    )
    # Do not use object framing: it changes selection/local-view membership.
    from mathutils import Vector

    # The modal editor occupies the right/central view. Reserve the left portion
    # for inspection, without moving the dialog or making a selectable object.
    horizontal_scale = abs(float(view.window_matrix[0][0]))
    old_distance = float(view.view_distance)
    if (not math.isfinite(horizontal_scale) or horizontal_scale <= 1e-12
            or not math.isfinite(old_distance) or old_distance <= 0):
        raise ValueError("The current viewport projection cannot be framed safely")
    # Use native projection scale rather than guessing Blender's sensor fit.
    # NDC -0.44 places the result at 28% of the owning WINDOW region width.
    offset = 0.44 * distance / horizontal_scale
    if view.view_perspective == "ORTHO":
        offset /= old_distance
    right = view.view_rotation @ Vector((1.0, 0.0, 0.0))
    location = Vector(center) + right * offset
    if any(not math.isfinite(v) or abs(v) > 1e12 for v in location):
        raise ValueError("Preview framing is outside supported view bounds")
    view.view_location = location
    view.view_distance = distance
    owner.redraw()
