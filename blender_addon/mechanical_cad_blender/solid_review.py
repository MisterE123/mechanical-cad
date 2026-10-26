"""Source-bound input inspection, never publication or a second canonical model."""

import json
import uuid

import bpy
from mathutils import Matrix, Vector

from . import document_state, execution_lease
from .common import DOCUMENT_KEY, FEATURE_KEY, MM_TO_METERS, OWNER_KEY, _state
from .face_pick import _f32, bound_feature
from .shell_selection import toggle_opening
from .viewport_navigation import navigation_passthrough

_REVIEWS = set()
_CONSENT_RETURNS = {}


def cancel_all():
    _CONSENT_RETURNS.clear()
    for review in tuple(_REVIEWS):
        review.close()


def cancel_consent_reopen(context):
    """A newer editor owns this window/scene; supersede an older deferred draft."""
    if context.window is not None:
        key = (context.window.as_pointer(), context.scene.as_pointer())
        _CONSENT_RETURNS.pop(key, None)


def queue_consent_reopen(context, values, *, expression=False):
    """One deferred return, not a retained model, permission or geometry receipt."""
    if context.window is None or context.area is None or context.area.type != "VIEW_3D":
        return False
    values = dict(values)
    window, area, scene = context.window, context.area, context.scene
    workspace, layer = context.workspace, context.view_layer
    key = (window.as_pointer(), scene.as_pointer())
    token = object()
    _CONSENT_RETURNS[key] = token

    def reopen():
        if _CONSENT_RETURNS.get(key) is not token:
            return None
        _CONSENT_RETURNS.pop(key, None)  # Single shot, including refusal or cancellation.
        try:
            if (
                window not in bpy.context.window_manager.windows[:]
                or window.scene != scene
                or window.workspace != workspace
                or window.view_layer != layer
                or area not in window.screen.areas[:]
                or area.type != "VIEW_3D"
                or scene.mechanical_cad.document_json != values["original_json"]
                or execution_lease.is_busy()
                or execution_lease.cleanup_message()
            ):
                return None
            with bpy.context.temp_override(window=window, area=area):
                if bpy.context.mode != "OBJECT":
                    return None
                bpy.ops.mcad.edit_solid_feature(
                    "INVOKE_DEFAULT", feature_id=values["feature_id"],
                    resume_json=json.dumps(values), consent_retry=not expression,
                    expression_retry=expression,
                )
        except (ReferenceError, RuntimeError):
            pass
        return None

    try:
        bpy.app.timers.register(reopen, first_interval=0.1)
    except (RuntimeError, ValueError):
        _CONSENT_RETURNS.pop(key, None)
        raise
    return True


def _supervise():
    for review in tuple(_REVIEWS):
        try:
            if (
                review.window not in bpy.context.window_manager.windows[:]
                or review.area not in review.window.screen.areas[:]
                or review.window.scene != review.scene
            ):
                review.close()
                continue
            with bpy.context.temp_override(window=review.window, area=review.area):
                if not review.current(bpy.context):
                    review.close()
        except (ReferenceError, RuntimeError):
            review.close()
    return 0.2 if _REVIEWS else None


class InputBodyReview:
    """One exact input object with an independent owner and revocable replay receipt.

    Final objects are only hidden in the captured view layer, never replaced.
    Selection, feature history, active output and accepted runtime remain untouched.
    """

    def __init__(self, context, source_id):
        self.closed = False
        self.obj = self.mesh = self.receipt = None
        self.hidden = []
        self.scene, self.window, self.area = context.scene, context.window, context.area
        self.layer = context.view_layer
        self.active = self.layer.objects.active
        self.base = _state(context).document_json
        self.document = json.loads(self.base)
        self.source_id = source_id
        self.owner = "review:" + uuid.uuid4().hex
        try:
            with document_state.replay_guard(context):
                self.record = document_state._capture_binding(context)
                self.receipt = document_state._run_sidecar(
                    context, self.document, binding=self.record
                )
                self.record["evidence"] = self.receipt
                self.evidence = (self.receipt, self.record["owner_token"])
                self.projection = document_state._evidence_projection(
                    context, self.document, self.receipt, self.record
                )["result"]
            rows = [f for f in self.projection["features"] if f["id"] == source_id]
            if (
                len(rows) != 1
                or rows[0]["status"] != "ok"
                or rows[0].get("output", {}).get("kind") != "solid"
            ):
                raise ValueError(
                    "This feature's exact input solid is unavailable. Fix its upstream error."
                )
            mesh = rows[0]["mesh"]
            scale = MM_TO_METERS / self.record["scale"]
            vertices = [tuple(v * scale for v in p) for p in mesh["vertices"]]
            origin = tuple(
                _f32((min(p[a] for p in vertices) + max(p[a] for p in vertices)) / 2)
                for a in range(3)
            )
            self.mesh = bpy.data.meshes.new("CAD input review (temporary)")
            self.mesh.from_pydata(
                [tuple(p[a] - origin[a] for a in range(3)) for p in vertices],
                [],
                mesh["triangles"],
            )
            self.mesh.update()
            self.obj = bpy.data.objects.new("INPUT REVIEW · " + source_id, self.mesh)
            self.obj[OWNER_KEY] = self.owner
            self.obj[DOCUMENT_KEY] = self.projection["document_id"]
            self.obj[FEATURE_KEY] = source_id
            self.obj["mechanical_cad_stale"] = False
            self.obj["mechanical_cad_display_only"] = True
            self.obj.hide_render = True
            self.obj.matrix_world = Matrix.Translation(Vector(origin))
            self.scene.collection.objects.link(self.obj)
            for obj in self.scene.objects:
                if (
                    obj.get(OWNER_KEY) == _state(context).owner_id
                    and obj.name in self.layer.objects
                ):
                    self.hidden.append(
                        (
                            obj,
                            obj.hide_get(view_layer=self.layer),
                            obj.select_get(view_layer=self.layer),
                        )
                    )
                    obj.hide_set(True, view_layer=self.layer)
            context.view_layer.update()
            bound_feature(context, self.obj, self.projection, owner_id=self.owner)
            _REVIEWS.add(self)
            if not bpy.app.timers.is_registered(_supervise):
                bpy.app.timers.register(_supervise, first_interval=0.2)
        except Exception:
            self.close()
            raise

    def current(self, context):
        if self.closed:
            return False
        try:
            document_state._assert_binding(context, self.record)
            return (
                context.mode == "OBJECT"
                and context.area == self.area
                and self.area.type == "VIEW_3D"
                and self.obj is not None
                and self.obj.name in context.view_layer.objects
                and not self.obj.hide_get(view_layer=self.layer)
            )
        except (ValueError, RuntimeError, ReferenceError, AttributeError):
            return False

    def result(self, context, *, accepting=False):
        if not self.current(context):
            raise ValueError("Input review changed or expired. Reopen the picking operation.")
        if accepting:
            return document_state._evidence_projection(
                context, self.document, self.receipt, self.record
            )["result"]
        return self.projection

    def owns(self, context, obj):
        return obj == self.obj and obj.get(OWNER_KEY) == self.owner

    def bound_feature(self, context, obj, result):
        if not self.owns(context, obj):
            raise ValueError("Choose only this feature's reviewed input body.")
        feature = bound_feature(context, obj, result, owner_id=self.owner)
        if feature["id"] != self.source_id:
            raise ValueError("The review input identity changed.")
        return feature

    def close(self):
        if self.closed:
            return
        self.closed = True
        _REVIEWS.discard(self)
        if self.receipt is not None:
            self.receipt.publication.cancel()
        for obj, hidden, selected in self.hidden:
            try:
                obj.hide_set(hidden, view_layer=self.layer)
                obj.select_set(selected, view_layer=self.layer)
            except (ReferenceError, RuntimeError):
                pass
        self.hidden.clear()
        try:
            if self.active is None or self.active.name in self.layer.objects:
                self.layer.objects.active = self.active
        except (ReferenceError, RuntimeError):
            pass
        if self.obj is not None:
            try:
                bpy.data.objects.remove(self.obj, do_unlink=True)
            except ReferenceError:
                pass
            self.obj = None
        if self.mesh is not None:
            try:
                if self.mesh.users == 0:
                    bpy.data.meshes.remove(self.mesh)
            except ReferenceError:
                pass
            self.mesh = None


class InputReview(InputBodyReview):
    """An existing feature may review only its saved input, never another body."""

    def __init__(self, context, feature_id, source_id):
        document = json.loads(_state(context).document_json)
        feature = next(f for f in document["features"] if f["id"] == feature_id)
        if feature["kind"] not in {"fillet", "chamfer", "shell"}:
            raise ValueError("Only Fillet, Chamfer and Shell support input reselection.")
        if feature["inputs"]["base"] != source_id:
            raise ValueError("Apply the changed input first, then reopen to reselect on that body.")
        super().__init__(context, source_id)


class MCAD_OT_reselect_solid_input(bpy.types.Operator):
    bl_idname = "mcad.reselect_solid_input"
    bl_label = "Reselect Feature Input"
    bl_description = "Review the saved input body without changing the Part"
    editor_json: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        from .direct_edge_pick import BlendEdgePicker
        from .face_pick import FacePicker
        from .viewport_sketch import _can_start_sketch

        review = None
        try:
            if not context.area or context.area.type != "VIEW_3D" or not _can_start_sketch(context):
                raise ValueError("Finish the current operation and reselect in the 3D view.")
            self.values = json.loads(self.editor_json)
            if self.values["original_json"] != _state(context).document_json:
                raise ValueError("The Part changed. Reopen Edit Feature.")
            document = json.loads(self.values["original_json"])
            feature = next(f for f in document["features"] if f["id"] == self.values["feature_id"])
            self.kind = feature["kind"]
            review = InputReview(context, feature["id"], self.values["base"])
            self._picker = (
                FacePicker(context, snapshot=review)
                if self.kind == "shell"
                else BlendEdgePicker(context, self.kind, snapshot=review)
            )
            self._multiple = False
            self._selected_openings = []
            self._picker.pick_instruction = "INPUT REVIEW: click one opening; Shift-click multiple, Enter reviews; Esc keeps old."
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            if review is not None:
                review.close()
            self.report({"ERROR"}, str(exc))
            values = getattr(self, "values", None)
            if (
                isinstance(values, dict)
                and values.get("original_json") == _state(context).document_json
            ):
                self._return_editor(context)
            return {"CANCELLED"}

    def _return_editor(self, context=None):
        # Cancellation may still be reaping its native edge-catalog process.
        # Retain values, not this operator's RNA, until that lease is released.
        values = dict(self.values)
        if context is None:
            window, area, scene = self._picker.window, self._picker.area, self._picker.scene
        else:
            window, area, scene = context.window, context.area, context.scene

        def reopen():
            if execution_lease.cleanup_message():
                return None
            try:
                if (
                    window not in bpy.context.window_manager.windows[:]
                    or window.scene != scene
                    or area not in window.screen.areas[:]
                    or scene.mechanical_cad.document_json != values["original_json"]
                ):
                    return None
                if execution_lease.is_busy():
                    return 0.1
                with bpy.context.temp_override(window=window, area=area):
                    bpy.ops.mcad.edit_solid_feature(
                        "INVOKE_DEFAULT",
                        feature_id=values["feature_id"],
                        resume_json=json.dumps(values),
                    )
            except (ReferenceError, RuntimeError):
                pass
            return None

        bpy.app.timers.register(reopen, first_interval=0.1)

    def modal(self, context, event):
        from .viewport_sketch import NAVIGATION_EVENTS

        picker = self._picker
        try:
            if not picker.current(context):
                raise ValueError(
                    "Input review became stale. Reopen Edit Feature; nothing was applied."
                )
            if event.type in {"ESC", "RIGHTMOUSE"}:
                picker.close()
                self._return_editor()
                return {"CANCELLED"}
            if self.kind == "shell" and navigation_passthrough(picker, context, event):
                return {"PASS_THROUGH"}
            if (
                self.kind == "shell"
                and event.type in {"RET", "NUMPAD_ENTER"}
                and event.value == "PRESS"
            ):
                if not self._selected_openings:
                    self.report({"WARNING"}, "Pick at least one planar opening first")
                    return {"RUNNING_MODAL"}
                self.values["opening_faces_json"] = json.dumps(self._selected_openings)
                self.values["opening_face"] = self._selected_openings[0]
                self.values["shell_mode"] = "OPEN"
                picker.close()
                self._return_editor()
                return {"FINISHED"}
            if getattr(picker, "pending", None) is not None:
                if event.type == "TIMER":
                    picker.poll_catalog(context)
                return {"PASS_THROUGH"} if event.type != "TIMER" else {"RUNNING_MODAL"}
            if self.kind != "shell" and hasattr(picker, "collect_event"):
                collected = picker.collect_event(context, event)
                if collected == "REVIEW":
                    if not picker.selected_edges:
                        self.report({"WARNING"}, "Pick at least one edge first")
                        return {"RUNNING_MODAL"}
                    picked = picker.selected_arguments(context)
                    if picked["picked_base"] != self.values["base"]:
                        raise ValueError("Pick belongs to a different input body")
                    self.values["edge_pairs_json"] = picked["picked_edge_pairs_json"]
                    self.values["edge_mode"] = "MULTI"
                    picker.close()
                    self._return_editor()
                    return {"FINISHED"}
                if collected:
                    return {"PASS_THROUGH"} if collected == "PASS" else {"RUNNING_MODAL"}
            if event.type == "F" and event.value == "PRESS" and self.kind != "shell":
                from .edge_pick import BlendFacePicker

                snapshot = picker.snapshot
                picker.close(retain_snapshot=True)
                try:
                    self._picker = BlendFacePicker(context, self.kind, snapshot=snapshot)
                except Exception:
                    snapshot.close()
                    raise
                return {"RUNNING_MODAL"}
            if event.type in NAVIGATION_EVENTS:
                picker.hit, picker.points = None, []
                picker.area.tag_redraw()
                return {"PASS_THROUGH"}
            if event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
                accepting = event.type == "LEFTMOUSE" and event.value == "PRESS"
                if not picker.hover(context, event, accepting=accepting):
                    return {"PASS_THROUGH"}
                if accepting and picker.hit:
                    if self.kind == "shell":
                        source, opening = picker.hit
                        if getattr(event, "shift", False) or getattr(self, "_multiple", False):
                            self._multiple = True
                            _, self._selected_openings = toggle_opening(
                                self._selected_openings, self.values["base"], picker.hit
                            )
                            picker.set_selected(
                                context, self.values["base"], self._selected_openings
                            )
                            picker.pick_instruction = (
                                f"{len(self._selected_openings)} orange openings: click toggles; "
                                "Enter reviews; Esc keeps old selection."
                            )
                            picker.area.header_text_set(picker.pick_instruction)
                            return {"RUNNING_MODAL"}
                        self.values["opening_face"] = opening
                        self.values["opening_faces_json"] = json.dumps([opening])
                        self.values["shell_mode"] = "OPEN"
                    else:
                        if not picker.choose():
                            return {"RUNNING_MODAL"}
                        picked = picker.dialog_arguments()
                        source = picked["picked_base"]
                        self.values["face_a"] = picked["picked_face_a"]
                        self.values["face_b"] = picked["picked_face_b"]
                        self.values["edge_mode"] = "PAIR"
                    if source != self.values["base"]:
                        raise ValueError("Pick belongs to a different input body.")
                    picker.close()
                    self._return_editor()
                    return {"FINISHED"}
            if self.kind == "shell" and event.type in {
                "MOUSEMOVE",
                "LEFTMOUSE",
                "INBETWEEN_MOUSEMOVE",
            }:
                return {"PASS_THROUGH"}
            return {"RUNNING_MODAL"}
        except Exception as exc:
            picker.close()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def cancel(self, context):
        picker = getattr(self, "_picker", None)
        if picker is not None:
            picker.close()


CLASSES = (MCAD_OT_reselect_solid_input,)
