"""Pick an exact straight or circular edge into the active sketch as a linked reference."""

import json

import bpy
from bpy.props import EnumProperty, StringProperty

from . import backend_runtime, document_state
from .common import _state
from .direct_edge_pick import BlendEdgePicker
from .face_pick import HoverSnapshot
from .general_viewport import active
from .projection_edge_choice import EdgeChoice, freeze_candidates
from .solid_review import InputBodyReview
from .viewport_sketch import NAVIGATION_EVENTS


def cancel_active():
    # Save must also retire the legacy displayed-body picker, which has no
    # ProjectionReview for solid_review.cancel_all() to close.
    picker = getattr(active(), "solid_projection_picker", None)
    if picker is not None:
        picker.close()


def earlier_solid_items(owner, result):
    """Source-qualified choices from earlier history and current typed evidence."""
    rows = {row["id"]: row for row in result["features"]}
    items = []
    for feature in owner.commands.candidate()["features"]:
        identifier = feature["id"]
        if identifier == owner.commands.feature_id:
            break
        row = rows.get(identifier, {})
        if row.get("status") == "ok" and row.get("output", {}).get("kind") == "solid":
            label = feature.get("label") or identifier
            items.append(
                (
                    identifier,
                    f"{label} · {identifier}",
                    "Pick an exact edge from this earlier solid",
                )
            )
    return tuple(items)


class ProjectionSelection:
    """Captured chooser context, not a saved source binding or draft command."""

    def __init__(self, context, owner):
        if owner is None or not owner.can_use_tool("Line"):
            raise ValueError("Finish or cancel sketch input before using a solid edge.")
        owner.require_gesture_context(context)
        self.owner = owner
        self.revision, self.saved = owner.commands.revision, owner.stored_snapshot
        self.window, self.area = context.window, context.area
        self.screen, self.layer = self.window.screen, context.view_layer
        self.snapshot = HoverSnapshot(context)
        self.items = earlier_solid_items(owner, self.snapshot.result(context))
        if not self.items:
            raise ValueError("No current earlier solid is available for this sketch.")

    def current(self, context):
        return (
            self.owner is active(context)
            and self.owner.alive
            and self.owner.valid_context()
            and self.owner.commands.revision == self.revision
            and self.owner.stored_snapshot == self.saved
            and _state(context).sketch_draft_json == self.saved
            and context.window == self.window
            and self.window.screen == self.screen
            and context.area == self.area
            and self.area.type == "VIEW_3D"
            and context.view_layer == self.layer
            and context.mode == "OBJECT"
            and self.snapshot.current(context)
        )

    def require_source(self, context, source_id):
        if not self.current(context):
            raise ValueError("The sketch or source Part changed. Reopen Use Solid Edge.")
        if source_id not in {item[0] for item in self.items}:
            raise ValueError(
                "Choose an eligible earlier solid, not this sketch or a later feature."
            )


class ProjectionReview(InputBodyReview):
    """Reuse the exact disposable input-body lifecycle in a still-open sketch."""

    def __init__(self, context, selection, source_id):
        selection.require_source(context, source_id)
        self.selection = selection
        super().__init__(context, source_id)
        try:
            # Independent read-only replay may not replace the accepted runtime.
            if self.result(context, accepting=True) != selection.snapshot.result(
                context, accepting=True
            ):
                raise ValueError("The source Part changed while preparing the picking body.")
        except Exception:
            self.close()
            raise

    def current(self, context):
        return self.selection.current(context) and super().current(context)

    def close(self):
        if self.closed:
            return
        super().close()
        # Save/backend/context supervision may retire the body without another
        # modal event. Release the sketch's gesture owner at the same boundary.
        picker = getattr(self.selection.owner, "solid_projection_picker", None)
        if picker is not None and picker.snapshot is self:
            picker.close()


class SolidProjectionPicker(BlendEdgePicker):
    def __init__(self, context, owner, *, snapshot=None):
        self.owner = owner
        self.edge_choice = None
        self.choice_handler = None
        self.view_layer = context.view_layer
        self.revision = owner.commands.revision
        self.saved = owner.stored_snapshot
        super().__init__(context, "projection", snapshot=snapshot)
        owner.solid_projection_picker = self

    def current(self, context):
        return (
            self.handler is not None
            and active(context) is self.owner
            and getattr(self.owner, "solid_projection_picker", None) is self
            and context.view_layer == self.view_layer
            and self.owner.alive
            and self.owner.valid_context()
            and self.owner.commands.revision == self.revision
            and self.owner.stored_snapshot == self.saved
            and _state(context).sketch_draft_json == self.saved
            and context.window == self.window
            and context.scene == self.scene
            and self.window.screen == self.screen
            and context.area == self.area
            and context.mode == "OBJECT"
            and _state(context).document_json == self.base
            and self.snapshot.current(context)
            and self.choice_display_current(context)
        )

    def choice_display_current(self, context):
        choice = self.edge_choice
        if choice is None:
            return True
        try:
            current = not choice.retired and all(
                obj.data == data
                and obj.name in self.scene.objects
                and obj.name in self.view_layer.objects
                and obj.visible_get(view_layer=self.view_layer, viewport=self.area.spaces.active)
                for obj, data in self.choice_display
            )
        except (ReferenceError, RuntimeError, AttributeError):
            current = False
        if not current:
            # An observed loss of display ownership cannot become valid again
            # by hiding/unhiding, relinking, or swapping datablocks back.
            choice.retired = True
        return current

    def close(self):
        if self.edge_choice is not None:
            self.edge_choice.retired = True
            self.edge_choice = None
        if self.choice_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.choice_handler, "WINDOW")
            self.choice_handler = None
        if getattr(self.owner, "solid_projection_picker", None) is self:
            self.owner.solid_projection_picker = None
        super().close()

    def poll_catalog(self, context):
        super().poll_catalog(context)
        if self.pending is None:
            source = getattr(self.snapshot, "source_id", None)
            name = (
                next((item[1] for item in self.snapshot.selection.items if item[0] == source), "")
                if isinstance(self.snapshot, ProjectionReview)
                else "displayed solid"
            )
            self.area.header_text_set(
                f"Use Solid Edge · {name}: click a line, circular arc or full circle. Esc cancels."
            )

    def hover(self, context, event, *, accepting=False):
        self.hit_endpoint_faces = None
        result = super().hover(context, event, accepting=accepting)
        if self.hit is not None:
            feature_id, a, b = self.hit
            entry = next(e for e in self.catalog[feature_id] if e["faces"] == [a, b])
            if "arc" in entry:
                self.hit_endpoint_faces = entry["arc"]["endpoint_faces"]
                self.message = "Click to link this arc as construction geometry. Esc cancels."
            elif "circle" in entry:
                self.message = "Click to link this circle as construction geometry. Esc cancels."
            elif len(entry["points"]) != 2:
                self.hit = None
                self.points = []
                self.message = (
                    "Choose a line, circular arc or full circle; other curves are unsupported."
                )
            elif "endpoint_faces" not in entry:
                self.hit = None
                self.points = []
                self.message = "This edge's endpoints lack stable identity. Choose another edge."
            else:
                self.hit_endpoint_faces = entry["endpoint_faces"]
                self.message = "Click to link this edge as construction geometry. Esc cancels."
        elif getattr(self, "overlap_candidates", ()):
            try:
                freeze_candidates(self.overlap_candidates, self.catalog)
                self.message = "Overlapping edges: click to Choose Edge. Esc cancels."
            except ValueError as exc:
                self.overlap_candidates = ()
                self.message = str(exc)
        elif self.message in {
            "Click an edge to blend. F: pick two faces instead. Esc cancels.",
            "No supported edge here. Some blend/imported faces lack stable support. F: two-face mode.",
        }:
            self.message = "Hover a line, circular arc or full circle, away from corners. Esc cancels."
        if isinstance(self.snapshot, ProjectionReview):
            label = next(
                item[1]
                for item in self.snapshot.selection.items
                if item[0] == self.snapshot.source_id
            )
            self.message = f"{label}: {self.message}"
        self.area.header_text_set(self.message)
        return result


    def begin_choice(self, context):
        self.edge_choice = EdgeChoice(self, self.overlap_candidates)
        self.choice_display = tuple((obj, obj.data) for obj in self.edge_choice.objects)
        if not self.choice_display_current(context):
            raise ValueError("The source display changed. Reopen Use Solid Edge.")
        from .projection_edge_choice_draw import prepare_layout
        self.choice_panel = prepare_layout(self)
        self.choice_size = (self.region.width, self.region.height)
        self.choice_matrix = self.rv3d.perspective_matrix.copy()
        self.hit, self.points = None, []
        self.choice_handler = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_choice, (), "WINDOW", "POST_PIXEL"
        )
        self.message = "Choose Edge: click a row (or 1–6), then Apply. Esc cancels."
        self.area.header_text_set(self.message)
        self.area.tag_redraw()

    def validate_choice(self, context):
        choice = self.edge_choice
        if choice is None:
            raise ValueError("Choose Edge expired.")
        choice.require(self)
        if (not self.choice_display_current(context) or not self.current(context) or self.rv3d.perspective_matrix != self.choice_matrix
                or (self.region.width, self.region.height) != self.choice_size):
            raise ValueError("The sketch, source or view changed. Reopen Use Solid Edge.")
        result = self.snapshot.result(context, accepting=True)
        accepted = choice.evidence.revalidate(
            backend_runtime.capture(context), owner_token=choice.catalog_token,
            expected_action="edge_catalog", expected_result_version=self.catalog_version,
            require_success=True,
        )["result"]
        if accepted["catalogs"] != self.catalog or accepted["replay"] != result:
            raise ValueError("Edge evidence changed. Reopen Use Solid Edge.")
        for index, (source, raw) in enumerate(choice.rows):
            entry = json.loads(raw)
            if self.snapshot.bound_feature(context, choice.objects[index], result)["id"] != source:
                raise ValueError("The displayed source changed. Pick again.")
            matches = [e for e in accepted["catalogs"].get(source, ())
                       if e["faces"] == entry["faces"]]
            if len(matches) != 1 or matches[0] != entry:
                raise ValueError("The exact edge identity changed. Pick again.")
        return choice

    def choice_layout(self):
        rows, apply, cancel, _text = self.choice_panel
        return rows, apply, cancel

    def draw_choice(self):
        # Presentation only: no transaction/journal capture or evidence admission.
        if (bpy.context.window != self.window or bpy.context.area != self.area
                or self.edge_choice is None or not self.current(bpy.context)):
            return
        from .projection_edge_choice_draw import draw_choice
        draw_choice(self)

    def choice_event(self, context, event):
        choice = self.edge_choice
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            choice.released = True
            return None
        if (not choice.released or event.value != "PRESS"
                or getattr(event, "is_repeat", False)):
            return None
        index = None
        apply = event.type in {"RET", "NUMPAD_ENTER"}
        keys = ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX")
        if event.type in keys:
            index = keys.index(event.type)
            if index >= len(choice.rows):
                return None
        if event.type == "LEFTMOUSE":
            x, y = event.mouse_x - self.region.x, event.mouse_y - self.region.y
            rows, apply_box, cancel_box = self.choice_layout()
            def inside(box):
                return box[0] <= x <= box[2] and box[1] <= y <= box[3]
            if inside(cancel_box):
                return "CANCEL"
            apply = inside(apply_box)
            index = next((i for i, box in enumerate(rows) if inside(box)), None)
        if index is not None:
            self.validate_choice(context).select(self, index)
            self.points = list(choice.points[index])
            self.area.tag_redraw()
        elif apply and choice.selected is not None:
            self.validate_choice(context)
            return "APPLY"
        return None

    def apply_choice(self, context):
        choice = self.validate_choice(context)
        source, entry = choice.consume(self)
        endpoints = entry.get("arc", entry).get("endpoint_faces")
        self.close()
        self.owner.project_solid_edge(
            context, source, entry["faces"], endpoints,
            choice.evidence, choice.catalog_token, self.catalog_version,
        )


_NO_SOURCES = (("NONE", "No eligible earlier solids", ""),)
_SOURCE_CHOICES = {}


def _source_items(self, context):
    # RNA callbacks receive OperatorProperties, not the Python invoke instance.
    # Dialog redraw must use frozen choices, even if the live Part has changed.
    captured = getattr(self, "source_choices_json", "")
    if captured:
        values = tuple(tuple(item) for item in json.loads(captured))
    else:
        # Direct explicit EXEC_DEFAULT calls have not captured a dialog yet.
        owner = active(context) if context is not None else None
        result = document_state.current_part_result(context) if owner is not None else None
        values = earlier_solid_items(owner, result) if result is not None else ()
    return _SOURCE_CHOICES.setdefault(values, values or _NO_SOURCES)


class MCAD_OT_use_solid_edge(bpy.types.Operator):
    bl_idname = "mcad.use_solid_edge"
    bl_label = "Use Solid Edge"
    bl_description = "Choose an earlier solid, then link one exact line, circular arc or full circle without leaving this sketch"
    source_choices_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    source_solid: EnumProperty(name="Source solid", items=_source_items, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        owner = active(context)
        return bool(
            context.area
            and context.area.type == "VIEW_3D"
            and owner
            and owner.can_use_tool("Line")
            and document_state.current_part_result(context) is not None
        )

    def invoke(self, context, event):
        try:
            self._selection = ProjectionSelection(context, active(context))
            self.source_choices_json = json.dumps(self._selection.items)
            choices = {item[0] for item in self._selection.items}
            displayed = _state(context).active_feature
            self.source_solid = displayed if displayed in choices else self._selection.items[0][0]
            return context.window_manager.invoke_props_dialog(
                self, width=460, confirm_text="Pick Edge"
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def draw(self, context):
        self.layout.prop(self, "source_solid")
        self.layout.label(text="Temporarily show this body to pick a line, arc or full circle.")
        self.layout.label(text="Esc returns to your sketch. The Part output stays unchanged.")

    def execute(self, context):
        review = None
        try:
            selection = getattr(self, "_selection", None)
            if selection is None:
                # Explicit EXEC_DEFAULT calls capture the same guard at admission.
                source_id = self.source_solid
                selection = self._selection = ProjectionSelection(context, active(context))
                self.source_choices_json = json.dumps(selection.items)
                self.source_solid = source_id
            selection.require_source(context, self.source_solid)
            review = ProjectionReview(context, selection, self.source_solid)
            self._picker = SolidProjectionPicker(context, selection.owner, snapshot=review)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            if review is not None:
                review.close()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def cancel(self, context):
        picker = getattr(self, "_picker", None)
        if picker is not None:
            picker.close()

    def modal(self, context, event):
        picker = self._picker
        try:
            if not picker.current(context):
                raise ValueError(
                    "Solid selection became stale; nothing was added. Reopen Use Solid Edge."
                )
            if event.type in {"ESC", "RIGHTMOUSE"}:
                picker.close()
                return {"CANCELLED"}
            if picker.edge_choice is not None:
                if event.type in NAVIGATION_EVENTS:
                    raise ValueError("View navigation cancelled Choose Edge. Click the source again.")
                action = picker.choice_event(context, event)
                if action == "CANCEL":
                    picker.close()
                    return {"CANCELLED"}
                if action == "APPLY":
                    picker.apply_choice(context)
                    return {"FINISHED"}
                return {"RUNNING_MODAL"}
            if event.type in NAVIGATION_EVENTS:
                picker.hit, picker.points = None, []
                picker.area.tag_redraw()
                return {"PASS_THROUGH"}
            if picker.pending is not None:
                if event.type == "TIMER":
                    picker.poll_catalog(context)
            elif event.type == "MOUSEMOVE":
                picker.hover(context, event)
            elif event.type == "LEFTMOUSE" and event.value == "PRESS":
                picker.hover(context, event, accepting=True)
                if picker.overlap_candidates:
                    picker.begin_choice(context)
                elif picker.hit is not None:
                    source_id, *faces = picker.hit
                    picker.close()
                    picker.owner.project_solid_edge(
                        context,
                        source_id,
                        faces,
                        picker.hit_endpoint_faces,
                        picker.catalog_evidence,
                        picker.catalog_token,
                        picker.catalog_version,
                    )
                    return {"FINISHED"}
            if event.type in {
                "TIMER",
                "MIDDLEMOUSE",
                "WHEELUPMOUSE",
                "WHEELDOWNMOUSE",
                "TRACKPADPAN",
                "TRACKPADZOOM",
            }:
                return {"PASS_THROUGH"}
            return {"RUNNING_MODAL"}
        except Exception as exc:
            picker.close()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


CLASSES = (MCAD_OT_use_solid_edge,)
