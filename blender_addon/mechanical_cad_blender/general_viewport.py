"""Bounded general line/circle/arc viewport adapter using the shared sketch owner.

No registration happens at import. Input belongs to one owner; text focus is an
explicit transient lease, and every accepted command/driver uses real async work.
"""

import math
import textwrap
import time

import blf
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Quaternion, Vector

from . import (
    dimension_click,
    dimension_input,
    document_state,
    draft_dispatch,
    execution_lease,
    general_sketch_overlay,
    general_view_geometry,
    line_axis,
    sketch_planes,
    sketch_session,
    workspace,
    workspace_ui,
)
from .common import MM_TO_METERS, _state
from .general_session import POINT_PICKER_EMPTY, POINT_SOURCE_EMPTY, DraftError, GeneralSession
from .general_sketch_commands import (
    AddPointLineDimension,
    AddRelation,
    CornerFillet,
    MovePoint,
    PointRef,
    PointSeed,
)
from .line_trim_extend import prepare_line_edit
from .point_line_dimension import existing_offset, perpendicular_foot
from .support_intent_edit import POLICY_ITEMS, capture_support_intent
from .topology_labels import face_label
from .viewport_sketch import (
    NAVIGATION_EVENTS,
    _begin_in_sketch,
    _can_start_sketch,
    _selected_editor,
)


def active(context=None):
    owner = sketch_session.active_session(context)
    return owner if type(owner) is GeneralSession else None


def tool_available(context, tool):
    """Use the owner's capability, shared with native palette and menus."""
    owner = active(context)
    return bool(owner is not None and owner.can_use_tool(tool))


def _navigation(owner, event):
    """Pointer navigation may pass a field; number/text keys stay field-owned."""
    if event.type not in NAVIGATION_EVENTS:
        return False
    controller = owner.input_controller
    if controller is not None and not controller.closed and event.type.startswith("NUMPAD_"):
        return False
    _click_tracker(owner).reset()
    if event.type == "MIDDLEMOUSE":
        owner.navigation = event.value != "RELEASE"
    return True


def _scale(owner):
    return MM_TO_METERS / float(owner.scene.unit_settings.scale_length)


def _project(owner, world):
    result = view3d_utils.location_3d_to_region_2d(
        owner.region, owner.rv3d, Vector(world) * _scale(owner)
    )
    return None if result is None else tuple(result)


def _xy(owner, event):
    return event.mouse_x - owner.region.x, event.mouse_y - owner.region.y


def _safe_rect(owner):
    left, bottom, right, top = 12.0, 12.0, owner.region.width - 12.0, owner.region.height - 12.0
    for region in owner.area.regions:
        if region.width <= 1 or region.height <= 1:
            continue
        if region.type == "UI":
            right = min(right, region.x - owner.region.x - 12)
        elif region.type == "TOOLS":
            left = max(left, region.x - owner.region.x + region.width + 12)
        elif region.type in {"HEADER", "TOOL_HEADER"}:
            y = region.y - owner.region.y
            if y < owner.region.height / 2:
                bottom = max(bottom, y + region.height + 12)
            else:
                top = min(top, y - 12)
    return left, bottom, max(left, right), max(bottom, top)


def _inside(point, bounds):
    x, y = point
    return bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]


def _over_view(owner, event):
    return _inside(_xy(owner, event), _safe_rect(owner))


def _pointer(owner, event):
    position = _xy(owner, event)
    origin = view3d_utils.region_2d_to_origin_3d(owner.region, owner.rv3d, position)
    ray = view3d_utils.region_2d_to_vector_3d(owner.region, owner.rv3d, position)
    plane = owner.geometry().plane
    hit = general_view_geometry.intersect_ray(plane, tuple(origin / _scale(owner)), tuple(ray))
    if hit is None:
        raise DraftError("View is edge-on to the sketch plane. Rotate the view to place geometry.")
    return hit.local_mm


def _pick(owner, event, kinds):
    result = general_view_geometry.pick_geometry(
        owner.geometry(), _xy(owner, event), lambda world: _project(owner, world), kinds=kinds
    )
    if result.status in {"ambiguous", "incomplete"}:
        raise DraftError(
            "Distinct point IDs overlap or are hidden; use the exact-ID Use existing point action."
            if kinds == ("point",)
            else "Selection is ambiguous or partly hidden. Use Points for an endpoint, or choose a visible curve."
        )
    return result.unique


def _anchor(owner, event):
    hit = _pick(owner, event, ("point",))
    if hit is not None:
        owner.message = "Reuse existing point " + hit.identifier
        return PointRef(hit.identifier)
    return PointSeed(*_pointer(owner, event))


def _line_endpoint(owner, event):
    """Fresh pointer/identity resolution shared by preview and final click."""
    points = owner.geometry().points
    start = line_axis.anchor_position(owner.draft.proposal, points)
    if not getattr(event, "shift", False):
        point = _anchor(owner, event)
        return point, None, ""
    axis, projected = line_axis.project_axis(start, _pointer(owner, event))
    hit = _pick(owner, event, ("point",))
    if hit is not None:
        point = PointRef(hit.identifier)
        try:
            line_axis.require_axis(start, line_axis.point_position(point, points), axis)
        except DraftError as exc:
            return PointSeed(*projected), axis, str(exc)
        return point, axis, ""
    return PointSeed(*projected), axis, ""


def _field_title(owner):
    if owner.draft.pending_diameter is not None:
        return "Driving diameter"
    if owner.draft.pending_length is not None:
        axis = owner.draft.pending_length["axis"]
        return "Driving length" + (" · " + axis.title() if axis else "")
    pending = owner.commands.pending_edit
    if pending is not None and owner.draft.annotations.get(pending.constraint_id, {}).get("display") == "diameter":
        return "Driving radius · diameter / 2"
    return "Raw dimension input"


def _line_hint(owner):
    if owner.draft.pending_diameter is not None:
        controller = owner.input_controller
        return "Diameter input retained · Reopen Diameter to edit" if controller is None or controller.closed else "Driving diameter: number or unit · Enter creates · Esc returns to Circle"
    if owner.draft.pending_length is not None:
        controller = owner.input_controller
        if controller is None or controller.closed:
            return "Length input retained · Reopen Length to edit"
        return "Driving length: number or unit · Enter creates · Esc returns to Line"
    if owner.proposal_capture and owner.draft.proposal and owner.draft.proposal["kind"] == "circle":
        return "Tab: driving diameter · Click: free circle"
    hint = getattr(owner, "line_axis_hint", None)
    if not owner.proposal_capture or owner.draft.point_input_phase != ("line", "end"):
        return None
    if hint and hint[:3] == (owner.draft, owner.commands.revision, owner.draft.ui_revision):
        return hint[3] + " · Tab: driving length"
    return "Tab: driving length · Hold Shift: Horizontal / Vertical"


def _reuse_phase(owner):
    """Only phases whose pointer click reaches _anchor; never a snap authority."""
    if (
        owner.pending is not None
        or owner.commands.pending_edit is not None
        or owner.navigation
        or owner.input_controller is not None
        or any(getattr(owner, name, None) for name in (
            "gesture_intent", "solid_projection_picker", "point_drag", "line_edit",
            "annotation_drag",
        ))
    ):
        return None
    proposal = owner.draft.proposal
    if proposal is not None and not owner.proposal_capture:
        return None
    phase = owner.draft.point_input_phase
    if phase is not None:
        if proposal is not None or owner.can_use_tool(owner.draft.tool):
            return phase
    elif proposal is None and owner.draft.tool == "Circle" and owner.can_use_tool("Circle"):
        return ("circle", "center")
    return None


def _reuse_binding(owner):
    phase = _reuse_phase(owner)
    if phase is None:
        return None
    # Geometry is an owner-cached pure display snapshot. View changes invalidate
    # pixels even when no mouse event arrives (e.g. Look Normal or resizing).
    return (
        owner.draft, owner.commands.revision, owner.draft.ui_revision, phase,
        owner.geometry(), tuple(tuple(row) for row in owner.rv3d.perspective_matrix),
        _safe_rect(owner), _scale(owner),
        (owner.region.x, owner.region.y, owner.region.width, owner.region.height),
    )


def _update_reuse_hover(owner, event):
    owner.reuse_hover = None
    binding = _reuse_binding(owner)
    position = _xy(owner, event)
    if binding is None or not _over_view(owner, event) or any(
        _inside(position, bounds) for _, bounds in getattr(owner, "label_bounds", ())
    ):
        return
    if owner.draft.point_input_phase == ("line", "end") and getattr(event, "shift", False):
        try:
            if _line_endpoint(owner, event)[2]:
                return
        except DraftError:
            return
    try:
        hit = _pick(owner, event, ("point",))
    except DraftError:
        # Ambiguous/incomplete picks remain silent, not a new diagnostic.
        return
    if hit is not None:
        owner.reuse_hover = (binding, position, hit.nearest_screen)


def _reuse_hover_position(owner):
    hover = getattr(owner, "reuse_hover", None)
    if hover is None:
        return None
    if hover[0] != _reuse_binding(owner) or any(
        _inside(hover[1], bounds) for _, bounds in getattr(owner, "label_bounds", ())
    ):
        owner.reuse_hover = None
        return None
    return hover[2]

def _draw(owner):
    if (
        not owner.alive
        or bpy.context.window != owner.window
        or bpy.context.area != owner.area
        or bpy.context.region != owner.region
        or not owner.valid_context()
    ):
        return
    try:
        geometry = owner.geometry()
        current = geometry.request_fingerprint if geometry.source == "solved" else None
        frame = general_sketch_overlay.build_frame(
            geometry,
            lambda world: _project(owner, world),
            current_request_fingerprint=current,
            selection=owner.draft.selection,
            relation_ids=tuple(item["id"] for item in owner.commands.sketch["constraints"]),
            annotations=owner.draft.display_annotations,
            proposal=(
                {
                    "kind": "line",
                    "anchor": {"kind": "new", "position": owner.point_drag["start"]},
                    "endpoint": owner.point_drag["target"],
                }
                if getattr(owner, "point_drag", None) and owner.point_drag["moved"]
                else owner.line_edit["preview"].proposal
                if getattr(owner, "line_edit", None) and owner.line_edit.get("preview")
                else _dimension_proposal(owner) or owner.draft.proposal
            ),
        )
        safe = _safe_rect(owner)
        ui_scale = float(bpy.context.preferences.system.ui_scale)
        owner.label_bounds = general_sketch_overlay.draw_frame(
            frame,
            current_request_fingerprint=current,
            usable_rect=safe,
            origin=(safe[0], safe[1]),
            scale=ui_scale,
        )
        preview = getattr(owner, "corner_fillet_preview", None)
        if preview and owner.gesture_intent is preview[0]:
            binding, plan, positions = preview
            if binding.commands is owner.commands and binding.snapshot == draft_dispatch.dumps(owner.draft):
                general_sketch_overlay.draw_corner_fillet_preview(
                    plan, positions, lambda p: _project(owner, geometry.plane.local_to_world(p))
                )
        reuse_position = _reuse_hover_position(owner)
        if reuse_position is not None and not owner.error:
            general_sketch_overlay.draw_reuse_hint(
                reuse_position, usable_rect=safe, scale=ui_scale
            )
        hint = _line_hint(owner)
        if hint:
            blf.size(0, 13 * ui_scale)
            blf.color(0, 1.0, 0.85, 0.35, 1.0)
            blf.position(0, safe[0] + 6, safe[3] - 62 * ui_scale, 0)
            blf.draw(0, hint)
        saved_plane = owner.display_plane
        blf.size(0, 12 * ui_scale)
        blf.color(0, 0.75, 0.85, 1.0, 1.0)
        blf.position(0, safe[0] + 6, safe[3] - 94 * ui_scale, 0)
        origin = ", ".join(f"{value:g}" for value in saved_plane["origin"])
        blf.draw(
            0,
            f"{'Face ' + owner.support_face if owner.support_face else 'Plane ' + saved_plane['id']} · origin ({origin}) mm · local U/V",
        )
        if owner.support_notice:
            blf.position(0, safe[0] + 6, safe[3] - 111 * ui_scale, 0)
            blf.draw(0, owner.support_notice)
        measurement = (
            _point_dimension(owner)
            if owner.draft.tool == "Dimension" and owner.commands.pending_edit is None
            else None
        )
        if measurement:
            blf.position(0, safe[0] + 6, safe[3] - 44 * ui_scale, 0)
            blf.draw(0, f"{measurement[3]} ~{measurement[2]:.6g} mm · click to place · Esc cancels")
        drag = getattr(owner, "point_drag", None)
        if drag:
            blf.position(0, safe[0] + 6, safe[3] - 44 * ui_scale, 0)
            blf.draw(
                0, "Drag point: release to solve · Esc cancels · existing dimensions stay fixed"
            )
        edit = getattr(owner, "line_edit", None)
        if edit:
            blf.position(0, safe[0] + 6, safe[3] - 44 * ui_scale, 0)
            instruction = (
                "Preview: Enter / Apply to accept, Esc / Cancel to discard"
                if edit.get("preview")
                else "Pick a boundary line, circle or arc"
                if edit.get("target")
                else "Pick target line near the endpoint to change"
            )
            blf.draw(0, f"{edit['mode']}: {instruction}")
        controller = owner.input_controller
        if controller is not None and not controller.closed:
            state = controller.snapshot()["buffer"]
            owner.field_layout = general_sketch_overlay.draw_editor(
                state["raw"],
                state["caret"],
                state["anchor"],
                error=owner.error or None,
                title=_field_title(owner),
                origin=owner.field_position,
                usable_rect=safe,
                scale=ui_scale,
                caret_visible=time.monotonic() % 1.0 < 0.6,
            )
        elif owner.error:
            blf.size(0, 13 * ui_scale)
            blf.color(0, 1, 0.5, 0.2, 1)
            blf.position(0, safe[0] + 6, safe[1] + 38 * ui_scale, 0)
            width = max(12, int((safe[2] - safe[0]) / (8 * ui_scale)))
            blf.draw(0, textwrap.shorten(owner.error, width=width, placeholder="…"))
    except Exception as exc:
        # A failed draw never accepts work or creates fallback solver authority.
        owner.error = "Sketch display: " + str(exc)


def _open_field(owner, constraint_id, position, *, select_all=False):
    from .reference_dimensions import READ_ONLY_MESSAGE, is_reference

    if is_reference(owner.draft.annotations.get(constraint_id)):
        owner.message = READ_ONLY_MESSAGE
        owner.error = ""
        return
    binding = owner.draft.annotations.get(constraint_id, {})
    if (
        owner.commands.pending_edit is None
        and binding.get("kind") == "radius"
        and binding.get("display") == "diameter"
    ):
        # Explicit diameter dialog owns conversion; never reinterpret retained
        # canonical-radius raw input or create a second dimension edit mode.
        return bpy.ops.mcad.sketch_numeric_relation(
            "INVOKE_DEFAULT", mode="DIAMETER", constraint_id=constraint_id
        )
    owner.open_dimension_field(constraint_id, position, select_all=select_all)


def _route_field(owner, context, event):
    controller = owner.input_controller
    if controller is None:
        return False
    position = _xy(owner, event)
    layout = getattr(owner, "field_layout", None)
    inside = bool(layout and _inside(position, layout.bounds))
    outside = event.type == "LEFTMOUSE" and event.value == "PRESS" and not inside
    index = None
    if event.type == "LEFTMOUSE":
        if event.value == "PRESS":
            owner.field_drag = inside
        elif event.value == "RELEASE":
            owner.field_drag = False
    if inside and (
        event.type == "LEFTMOUSE"
        or (event.type == "MOUSEMOVE" and getattr(owner, "field_drag", False))
    ):
        state = controller.snapshot()["buffer"]
        parts = dimension_input.TextBuffer(state["raw"]).display_parts()
        start, end = layout.visible_range
        scale = float(context.preferences.system.ui_scale)
        blf.size(0, 14 * scale)
        index = min(
            range(start, end + 1),
            key=lambda i: abs(
                layout.bounds[0]
                + 16 * scale
                + blf.dimensions(0, "".join(parts[start:i]))[0]
                - position[0]
            ),
        )

    def approve(action):
        if action.lease != controller.lease or owner.input_controller is not controller:
            return False
        owner.update_raw(action.raw)
        return True

    routed = controller.handle(
        dimension_input.InputEvent(
            event.type,
            event.value,
            event.unicode,
            bool(event.ctrl),
            bool(event.shift),
            bool(event.alt),
            bool(event.is_repeat),
        ),
        approve_raw=approve,
        clipboard_get=lambda: context.window_manager.clipboard,
        clipboard_set=lambda value: setattr(context.window_manager, "clipboard", value),
        caret_index=index,
        outside=outside,
    )
    for action in routed.actions:
        if action.kind == "accept":
            if owner.draft.pending_diameter is not None:
                owner.request_circle_diameter_accept(context)
            elif owner.draft.pending_length is not None:
                owner.request_line_length_accept(context)
            else:
                owner.request_driver_accept(context)
        elif action.kind == "cancel":
            owner.cancel_dimension()
        elif action.kind == "suspend":
            owner.cancel_native("Dimension input suspended; exact raw text retained.")
            owner.input_token = ""
            owner.checkpoint()
        elif action.kind in {"input_error", "owner_rejected"}:
            owner.error = action.detail
    return routed.handled


def _point_dimension(owner):
    """Return the exact two-target measurement, without changing accepted intent."""
    selected = owner.draft.selection
    if len(selected) != 2 or selected[0]["kind"] != "point":
        return None
    geometry = owner.geometry()
    point_id, other = selected[0]["id"], selected[1]
    start = geometry.points[point_id]
    if other["kind"] == "point":
        end = geometry.points[other["id"]]
        value = math.dist(start, end)
        if value < 1e-6:
            raise DraftError("Coincident points need Coincident, not a zero distance.")
        command = AddRelation("distance", (point_id, other["id"]), value=value)
        existing = next(
            (
                key
                for key, dim in geometry.dimensions.items()
                if dim.kind == "distance" and set(dim.refs) == {point_id, other["id"]}
            ),
            None,
        )
        title = "Point distance"
    elif other["kind"] == "line":
        line = geometry.lines[other["id"]]
        if point_id in (line.start_id, line.end_id):
            raise DraftError("Choose a point that is not an endpoint of the reference line.")
        end, value = perpendicular_foot(start, line.start_mm, line.end_mm)
        command = AddPointLineDimension(point_id, other["id"], PointSeed(*end), value)
        existing = existing_offset(owner.commands.sketch, point_id, other["id"])
        title = "Perpendicular offset (unsigned)"
    else:
        return None
    return start, end, value, title, command, existing


def _dimension_proposal(owner):
    if owner.draft.tool != "Dimension" or owner.commands.pending_edit is not None:
        return None
    measurement = _point_dimension(owner)
    if measurement is None:
        return None
    start, end = measurement[:2]
    return {"kind": "line", "anchor": {"kind": "new", "position": start}, "endpoint": end}


def _dimension(owner, context, event):
    selected = owner.draft.selection
    measurement = _point_dimension(owner)
    if measurement is not None:
        start, end, value, title, command, existing = measurement
        center = tuple((a + b) / 2 for a, b in zip(start, end, strict=True))
    elif len(selected) == 1 and selected[0]["kind"] == "point":
        hit = _pick(owner, event, ("point",))
        if hit is None:
            hit = _pick(owner, event, ("line",))
        if hit is None:
            owner.message = "Choose another point or a straight reference line."
            return
        if hit.kind == "point" and hit.identifier == selected[0]["id"]:
            return
        owner.draft.select((("point", selected[0]["id"]), (hit.kind, hit.identifier)))
        try:
            preview = _point_dimension(owner)
        except (ValueError, DraftError):
            owner.draft.select((("point", selected[0]["id"]),))
            raise
        owner.message = (
            f"{preview[3]} ~{preview[2]:.6g} mm: click to place, then type. Esc cancels."
        )
        return
    elif len(selected) != 1 or selected[0]["kind"] not in {"line", "circle", "arc"}:
        # Centers/endpoints must win over incident curves, just like Select.
        hit = _pick(owner, event, ("point",))
        if hit is None:
            hit = _pick(owner, event, ("line", "circle", "arc"))
        if hit is None:
            return
        owner.draft.select(((hit.kind, hit.identifier),))
        owner.message = (
            "Choose another point or a straight line for a perpendicular offset."
            if hit.kind == "point"
            else "Click to place the driving dimension."
        )
        return
    else:
        selected = selected[0]
        geometry = owner.geometry()
        if selected["kind"] in {"circle", "arc"}:
            entity = (geometry.arcs if selected["kind"] == "arc" else geometry.circles)[
                selected["id"]
            ]
            kind, refs, value = "radius", (selected["id"],), entity.radius_mm
            center = entity.center_mm
        else:
            entity = geometry.lines[selected["id"]]
            kind, refs, value = (
                "distance",
                (entity.start_id, entity.end_id),
                math.dist(entity.start_mm, entity.end_mm),
            )
            center = tuple((a + b) / 2 for a, b in zip(entity.start_mm, entity.end_mm, strict=True))
        existing = next(
            (
                identifier
                for identifier, dimension in geometry.dimensions.items()
                if dimension.kind == kind and set(dimension.refs) == set(refs)
            ),
            None,
        )
        command = AddRelation(kind, refs, value=value)
    location = _pointer(owner, event)
    offset = tuple(a - b for a, b in zip(location, center, strict=True))
    if existing:
        display = owner.draft.annotations.get(existing, {}).get("display")
        owner.draft.place_annotation(existing, offset, display=display)
        owner.draft.select(())
        owner.checkpoint()
        _open_field(owner, existing, _xy(owner, event), select_all=True)
    else:
        owner.execute(
            context, command, annotation_offset=offset, dimension_position=_xy(owner, event)
        )
        owner.draft.select(())


def _click_tracker(owner):
    if not hasattr(owner, "dimension_click"):
        owner.dimension_click = dimension_click.DimensionClick()
    return owner.dimension_click


def _line_edit_click(owner, event):
    edit = owner.line_edit
    if edit["revision"] != owner.commands.revision:
        owner.line_edit = None
        raise DraftError("Sketch changed; choose Trim or Extend again.")
    edit.pop("preview", None)
    hit = _pick(owner, event, ("line", "circle", "arc") if edit.get("target") else ("line",))
    if hit is None:
        raise DraftError(
            "Pick a visible boundary line, circle or arc." if edit.get("target")
            else "Pick a visible straight target line."
        )
    if not edit.get("target"):
        edit["target"] = hit.identifier
        edit["near"] = _pointer(owner, event)
        owner.draft.select((("line", hit.identifier),))
        owner.message = (
            "Pick a boundary line, circle or arc. "
            "The nearest crossing from your endpoint is used."
        )
        return
    edit["preview"] = prepare_line_edit(
        owner.commands.sketch,
        owner.geometry().points,
        edit["target"],
        hit.identifier,
        edit["near"],
        edit["mode"],
        circles=owner.geometry().circles,
        arcs=owner.geometry().arcs,
    )
    geometry = owner.geometry()
    boundary_kind = (
        "circle" if hit.identifier in geometry.circles
        else "arc" if hit.identifier in geometry.arcs else "line"
    )
    owner.draft.select((("line", edit["target"]), (boundary_kind, hit.identifier)))
    owner.error = ""
    owner.message = "Review the purple line. Apply / Enter accepts; Cancel / Esc discards."


def _apply_line_edit(owner, context):
    edit = getattr(owner, "line_edit", None)
    if not edit or not edit.get("preview"):
        raise DraftError("Pick a target line and boundary line, circle or arc first.")
    if edit["revision"] != owner.commands.revision:
        owner.line_edit = None
        raise DraftError("Sketch changed; create a fresh Trim/Extend preview.")
    preview = edit["preview"]
    # Revalidate shared IDs and all current relations immediately before mutation.
    fresh = prepare_line_edit(
        owner.commands.sketch,
        owner.geometry().points,
        edit["target"],
        preview.boundary_line,
        edit["near"],
        edit["mode"],
        circles=owner.geometry().circles,
        arcs=owner.geometry().arcs,
    )
    owner.execute(context, MovePoint(fresh.point_id, fresh.target))
    owner.line_edit = None


def _click(owner, context, event):
    if getattr(owner, "line_edit", None):
        _line_edit_click(owner, event)
        return
    labels = [
        identifier
        for identifier, bounds in getattr(owner, "label_bounds", ())
        if _inside(_xy(owner, event), bounds)
    ]
    if labels:
        if len(labels) != 1:
            raise DraftError("Dimension annotations overlap. Move the labels apart first.")
        if _click_tracker(owner).press(
            labels[0],
            _xy(owner, event),
            time.monotonic(),
            native_double=event.value == "DOUBLE_CLICK",
        ):
            owner.annotation_drag = None
            _open_field(owner, labels[0], _xy(owner, event))
        else:
            owner.annotation_drag = labels[0]
        return
    _click_tracker(owner).reset()
    if owner.draft.tool == "Dimension":
        _dimension(owner, context, event)
        return
    if owner.draft.tool == "Select":
        # Endpoint/center handles win over incident curves. Distinct coincident
        # point IDs still fail closed in the point-only picker.
        hit = _pick(owner, event, ("point",))
        if hit is None and owner.selection_mode != "point":
            hit = _pick(owner, event, ("line", "circle", "arc"))
        old = [(item["kind"], item["id"]) for item in owner.draft.selection] if event.shift else []
        if hit:
            binding = (hit.kind, hit.identifier)
            old = [item for item in old if item != binding] if binding in old else old + [binding]
        owner.draft.select(old)
        if hit and hit.kind == "point" and not event.shift and event.value == "PRESS":
            owner.begin_point_drag(hit.identifier, _xy(owner, event), _pointer(owner, event))
        return
    if owner.draft.point_input_phase is not None:
        phase = owner.draft.point_input_phase
        if owner.draft.proposal is not None and not owner.proposal_capture:
            raise DraftError(
                "This retained proposal is not capturing input. Choose Continue or Use existing point."
            )
        if phase == ("line", "end"):
            point, axis, blocked = _line_endpoint(owner, event)
            if blocked:
                raise DraftError(blocked)
            owner.accept_point_input(context, point, expected_phase=phase, axis=axis)
        else:
            owner.accept_point_input(context, _anchor(owner, event), expected_phase=phase)
        return
    if owner.draft.proposal is None:
        if owner.draft.tool == "Rectangle" and owner.can_use_tool("Rectangle"):
            owner.draft.begin_rectangle(PointSeed(*_pointer(owner, event)))
            owner.proposal_capture = True
            owner.message = "Choose opposite corner. H/V relations are explicit; Esc cancels."
            return
        if owner.draft.tool != "Circle" or not owner.can_use_tool("Circle"):
            raise DraftError("Choose an available drawing tool.")
        owner.draft.begin_circle(_anchor(owner, event))
        owner.proposal_capture = True
        return
    if not owner.proposal_capture:
        raise DraftError(
            "This retained proposal is not capturing input. Choose Continue or Cancel."
        )
    _move_proposal(owner, event)
    owner.accept_proposal(context)  # Circle only; all Line/Arc points use the owner adapter.


def _move_proposal(owner, event):
    point = _pointer(owner, event)
    proposal = owner.draft.proposal
    if proposal["kind"] == "line":
        endpoint, axis, blocked = _line_endpoint(owner, event)
        owner.draft.update_line(line_axis.point_position(endpoint, owner.geometry().points))
        text = (
            "Off-axis point: release Shift to reuse, or move away" if blocked else
            f"{axis.title()} constraint on click · release Shift for free Line" if axis else
            "Hold Shift: add Horizontal / Vertical constraint"
        )
        owner.line_axis_hint = (owner.draft, owner.commands.revision, owner.draft.ui_revision, text)
    elif proposal["kind"] == "rectangle":
        owner.draft.update_rectangle(point)
    elif proposal["kind"] == "arc":
        owner.draft.observe_arc(PointSeed(*point))
    else:
        anchor = proposal["anchor"]
        center = (
            owner.geometry().points[anchor["point_id"]]
            if anchor["kind"] == "existing"
            else anchor["position"]
        )
        owner.draft.update_circle(math.dist(center, point))


def _align_plane(owner, *, frame=False):
    """Look down the actual saved normal, including resumed/imported workplanes."""
    saved = owner.display_plane
    owner.rv3d.view_rotation = Quaternion(saved["quaternion"])
    owner.rv3d.view_perspective = "ORTHO"
    if frame:
        geometry = owner.geometry()
        points = list(geometry.points.values())
        for circle in geometry.circles.values():
            points.extend(
                (
                    tuple(value - circle.radius_mm for value in circle.center_mm),
                    tuple(value + circle.radius_mm for value in circle.center_mm),
                )
            )
        if points:
            low = [min(point[i] for point in points) for i in range(2)]
            high = [max(point[i] for point in points) for i in range(2)]
            center = tuple((a + b) / 2 for a, b in zip(low, high, strict=True))
            owner.rv3d.view_location = Vector(geometry.plane.local_to_world(center)) * _scale(owner)
            owner.rv3d.view_distance = max(
                50, max(b - a for a, b in zip(low, high, strict=True)) * 1.8
            ) * _scale(owner)
        else:
            owner.rv3d.view_location = Vector(saved["origin"]) * _scale(owner)
            owner.rv3d.view_distance = 100 * _scale(owner)
    owner.area.tag_redraw()


class MCAD_OT_new_plane_sketch(Operator):
    bl_idname = "mcad.new_plane_sketch"
    bl_label = "New Sketch on Plane"
    bl_description = "Choose a principal plane and signed offset; draw with existing solids visible"
    plane: EnumProperty(
        name="Plane",
        items=(
            ("XY", "XY · Top (+Z)", "Sketch X/Y coordinates; extrusion along +Z"),
            ("XZ", "XZ · Front (-Y)", "Sketch X/Z coordinates; extrusion along -Y"),
            ("YZ", "YZ · Right (+X)", "Sketch Y/Z coordinates; extrusion along +X"),
        ),
        default="XY",
    )
    plane_offset: FloatProperty(name="Offset (mm)", default=0.0, min=-1e6, max=1e6)

    @classmethod
    def poll(cls, context):
        return _can_start_sketch(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "plane")
        self.layout.prop(self, "plane_offset")
        self.layout.label(text="Offset follows the selected plane's positive normal.")
        self.layout.label(text="Model context stays visible; no automatic face attachment.")

    def execute(self, context):
        base = _state(context).document_json
        plane, offset = self.plane, self.plane_offset

        def begin(active_context):
            if _state(active_context).document_json != base:
                raise RuntimeError("The Part changed before Sketch opened; try again.")
            bpy.ops.mcad.general_sketch("INVOKE_DEFAULT", plane=plane, plane_offset=offset)

        workspace.request_workspace(context, "SKETCH", on_ready=begin)
        return {"FINISHED"}


_FACE_SKETCH_CHOICES = {}


def _face_sketch_sources(self, context):
    result = document_state.current_part_result(context)
    values = [
        (f["id"], f["id"], "Current exact solid")
        for f in (result or {}).get("features", [])
        if f.get("status") == "ok" and (f.get("output") or {}).get("kind") == "solid"
    ]
    key = ("sources", tuple(values))
    _FACE_SKETCH_CHOICES[key] = values or [
        ("NONE", "Rebuild the Part first", "No current exact solid")
    ]
    return _FACE_SKETCH_CHOICES[key]


def _face_sketch_faces(self, context):
    result = document_state.current_part_result(context)
    values = []
    for f in (result or {}).get("features", []):
        if f["id"] == self.support_source:
            values = [
                (face["id"], face_label(face), face["id"])
                for face in f.get("topology", [])
                if face.get("provenance", {}).get("semantic_status") == "stable"
                and face.get("signature", {}).get("surface") == "plane"
            ]
    key = ("faces", self.support_source, tuple(values))
    _FACE_SKETCH_CHOICES[key] = values or [("NONE", "Choose a solid with stable planar faces", "")]
    return _FACE_SKETCH_CHOICES[key]


class MCAD_OT_new_face_sketch(Operator):
    bl_idname = "mcad.new_face_sketch"
    bl_label = "New Sketch on Face"
    bl_description = (
        "Draw an associative sketch on an exact stable planar face, following upstream edits"
    )
    advanced_selection: BoolProperty(name="Choose face by ID", default=False, options={"SKIP_SAVE"})
    support_source: EnumProperty(name="Supporting solid", items=_face_sketch_sources)
    support_face: EnumProperty(name="Stable planar face", items=_face_sketch_faces)
    support_policy: EnumProperty(
        name="Support policy", items=POLICY_ITEMS, default="PRESERVE_PLANE"
    )

    @classmethod
    def poll(cls, context):
        return (
            _can_start_sketch(context) and document_state.current_part_result(context) is not None
        )

    def invoke(self, context, event):
        self._base = _state(context).document_json
        if self.advanced_selection:
            return context.window_manager.invoke_props_dialog(self)
        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"ERROR"}, "Open a 3D viewport to select a face.")
            return {"CANCELLED"}
        from .face_pick import FacePicker

        self._picker = FacePicker(context)
        self._picker.pick_instruction = (
            "Click a planar face. Default: Preserve logical plane + Minimal twist. Esc cancels."
            if self.support_policy == "PRESERVE_PLANE"
            else "Click a planar face. Strict policy: stop if its stable identity is lost. Esc cancels."
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
            if event.type in NAVIGATION_EVENTS:
                picker.hit, picker.points = None, []
                picker.area.tag_redraw()
                return {"PASS_THROUGH"}
            if event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
                inside = picker.hover(
                    context, event, accepting=event.type == "LEFTMOUSE" and event.value == "PRESS"
                )
                if not inside:
                    return {"PASS_THROUGH"}
                if event.type == "LEFTMOUSE" and event.value == "PRESS" and picker.hit:
                    picker.close()
                    picker.begin(context, support_policy=self.support_policy)
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

    def draw(self, context):
        self.layout.prop(self, "support_source")
        self.layout.prop(self, "support_face")
        self.layout.prop(self, "support_policy")
        self.layout.label(
            text="Default preserves the plane only across proven coplanar Cut splits."
        )
        if self.support_policy == "PRESERVE_PLANE":
            self.layout.label(
                text="Minimal twist orientation follows normal changes, not material spin."
            )
            self.layout.label(
                text="Review Support can change orientation or reset its saved frame."
            )
        self.layout.label(text="No fragment is chosen; the plane may span removed material.")
        self.layout.label(text="Origin is face centroid; local U/V, outward normal.")

    def execute(self, context):
        base = getattr(self, "_base", _state(context).document_json)
        support, face = self.support_source, self.support_face
        policy = self.support_policy
        if base != _state(context).document_json or support == "NONE" or face == "NONE":
            self.report(
                {"ERROR"}, "Choose a current stable planar face; reopen if the Part changed."
            )
            return {"CANCELLED"}

        def begin(active_context):
            if _state(active_context).document_json != base:
                raise RuntimeError("The Part changed before Sketch opened; try again.")
            bpy.ops.mcad.general_sketch(
                "INVOKE_DEFAULT",
                support_source=support,
                support_face=face,
                support_policy=policy,
            )

        workspace.request_workspace(context, "SKETCH", on_ready=begin)
        return {"FINISHED"}


class MCAD_OT_copied_face_sketch(Operator):
    bl_idname = "mcad.copied_face_sketch"
    bl_label = "Sketch on Copied Face Plane (Unlinked)"
    bl_description = "Copy a current native planar face into a fixed sketch plane, without a source link"

    @classmethod
    def poll(cls, context):
        return MCAD_OT_new_face_sketch.poll(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        from .copied_face_plane import DISCLOSURE

        self.layout.label(text=DISCLOSURE)
        self.layout.label(text="Choose a planar face after confirming. Esc cancels the pick.")
        self.layout.label(text="Origin: current native face centroid. Axes: deterministic world-axis frame.")
        self.layout.label(text="This does not recover STEP UV axes or create an associative attachment.")

    def execute(self, context):
        from .copied_face_plane import DISCLOSURE, CopiedPlanePicker

        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"ERROR"}, "Open a 3D viewport to select a face.")
            return {"CANCELLED"}
        try:
            self._picker = CopiedPlanePicker(context)
            self._picker.pick_instruction = DISCLOSURE + " Click a planar face; Esc cancels."
            self._picker.area.header_text_set(self._picker.pick_instruction)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        picker = self._picker
        try:
            if event.type in {"ESC", "RIGHTMOUSE"} or not picker.current(context):
                picker.close()
                return {"CANCELLED"}
            if event.type in NAVIGATION_EVENTS:
                picker.hit, picker.points = None, []
                picker.area.tag_redraw()
                return {"PASS_THROUGH"}
            if event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
                clicking = event.type == "LEFTMOUSE" and event.value == "PRESS"
                if not picker.hover(context, event, accepting=clicking):
                    return {"PASS_THROUGH"}
                if clicking and picker.hit:
                    picker.begin(context)
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


def _external_sketch_sources(self, context):
    owner = active(context)
    result = document_state.current_part_result(context)
    values = []
    if owner and result:
        for feature in owner.commands.candidate()["features"]:
            if feature["id"] == owner.commands.feature_id:
                break
            row = next((f for f in result["features"] if f["id"] == feature["id"]), None)
            if (
                feature["kind"] == "sketch_constrained"
                and row
                and row.get("status") == "ok"
                and row.get("sketch")
            ):
                values.append((feature["id"], feature["label"], feature["id"]))
    key = ("external_sources", tuple(values))
    _FACE_SKETCH_CHOICES[key] = values or [("NONE", "No prior solved constrained sketch", "")]
    return _FACE_SKETCH_CHOICES[key]


def _external_sketch_entities(self, context):
    result = document_state.current_part_result(context)
    values = []
    for feature in (result or {}).get("features", []):
        if feature["id"] == self.source_sketch and feature.get("sketch"):
            solved = feature["sketch"]["solved"]
            values = [
                (e["id"], kind + " " + e["id"], "Associative construction reference")
                for kind, collection in (("Line", "lines"), ("Circle", "circles"))
                for e in solved.get(collection, [])
            ]
    key = ("external_entities", self.source_sketch, tuple(values))
    _FACE_SKETCH_CHOICES[key] = values or [("NONE", "Choose a source with lines or circles", "")]
    return _FACE_SKETCH_CHOICES[key]


class MCAD_OT_project_sketch_geometry(Operator):
    bl_idname = "mcad.project_sketch_geometry"
    bl_label = "Project External Geometry"
    bl_description = "Link one prior sketch line or circle as source-driven construction geometry"
    source_sketch: EnumProperty(name="Source sketch", items=_external_sketch_sources)
    source_entity: EnumProperty(name="Source geometry", items=_external_sketch_entities)

    @classmethod
    def poll(cls, context):
        owner = active(context)
        return (
            owner is not None
            and owner.can_use_tool("Line")
            and document_state.current_part_result(context) is not None
        )

    def invoke(self, context, event):
        owner = active(context)
        self._binding = (owner, owner.commands.revision, owner.stored_snapshot)
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        self.layout.prop(self, "source_sketch")
        self.layout.prop(self, "source_entity")
        self.layout.label(text="Linked construction geometry follows its source.")
        self.layout.label(text="Choose an earlier sketch.")
        self.layout.label(text="Circles need parallel sketch planes.")
        self.layout.label(text="Constrain your geometry to projected points or curves.")

    def execute(self, context):
        try:
            owner = active(context)
            if owner is None:
                raise DraftError("Open a sketch before projecting external geometry.")
            if hasattr(self, "_binding") and self._binding != (
                owner,
                owner.commands.revision,
                owner.stored_snapshot,
            ):
                raise DraftError(
                    "The sketch changed while the projection dialog was open; reopen it."
                )
            owner.project_external(context, self.source_sketch, self.source_entity)
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class MCAD_OT_sketch_normal_view(Operator):
    bl_idname = "mcad.sketch_normal_view"
    bl_label = "Look Normal to Sketch"
    bl_description = "Return to the active sketch's own plane after orbiting the model"

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def execute(self, context):
        _align_plane(active(context))
        return {"FINISHED"}


class MCAD_OT_general_sketch(Operator):
    bl_idname = "mcad.general_sketch"
    bl_label = "Line / Circle / Arc Sketch"
    bl_description = (
        "Draw explicit lines, circles or a bounded center arc, then Finish the checked sketch"
    )
    bl_options = {"REGISTER", "UNDO"}
    feature_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    resume_saved: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})
    copied_plane_token: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    support_source: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    support_face: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    support_policy: EnumProperty(
        name="Support policy",
        items=POLICY_ITEMS,
        default="PRESERVE_PLANE",
        options={"HIDDEN", "SKIP_SAVE"},
    )

    plane: EnumProperty(
        name="Sketch plane",
        items=(
            ("XY", "XY · Top", "U = X, V = Y; normal +Z"),
            ("XZ", "XZ · Front", "U = X, V = Z; normal -Y"),
            ("YZ", "YZ · Right", "U = Y, V = Z; normal +X"),
        ),
        default="XY",
    )
    plane_offset: FloatProperty(
        name="Offset (mm)",
        default=0.0,
        min=-1e6,
        max=1e6,
        description="Signed distance along the plane normal, in millimetres",
    )

    @classmethod
    def poll(cls, context):
        return bool(
            context.mode == "OBJECT"
            and context.area
            and context.area.type == "VIEW_3D"
            and workspace.get_role(context) == "SKETCH"
            and _state(context).document_json
            and sketch_session.active_session() is None
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
        )

    def execute(self, context):
        # Script/background entry has no initiating event; acquisition is the
        # same checked path and still creates exactly one shared modal owner.
        return self.invoke(context, None)

    def invoke(self, context, event):
        try:
            if _state(context).sketch_draft_json and not self.resume_saved:
                raise DraftError("Resume or Discard the saved draft before starting another.")
            restored = (
                draft_dispatch.restore(
                    _state(context).sketch_draft_json, _state(context).document_json
                )
                if self.resume_saved
                else None
            )
            plane = (
                None
                if self.feature_id or restored
                else sketch_planes.principal_plane(self.plane, self.plane_offset)
            )
            support = None
            support_intent = None
            if self.support_source or self.support_face:
                if self.feature_id or restored or not (self.support_source and self.support_face):
                    raise DraftError("Choose a new sketch and one exact supporting face.")
                support = {"feature_id": self.support_source, "face_id": self.support_face}
                if self.support_policy == "PRESERVE_PLANE":
                    support_intent = capture_support_intent(
                        document_state.current_part_result(context),
                        self.support_source,
                        self.support_face,
                    )
                plane = sketch_planes.principal_plane("XY", 0)
            if self.copied_plane_token:
                if self.feature_id or restored or support is not None:
                    raise DraftError("A copied plane starts a new unlinked sketch only.")
                from .copied_face_plane import consume

                plane = consume(context, self.copied_plane_token)
            self.owner = GeneralSession(
                context,
                self.feature_id,
                restored=restored,
                plane=plane,
                support=support,
                support_intent=support_intent,
            )
            self.owner.start(((_draw, "POST_PIXEL"),))
            _align_plane(self.owner, frame=True)
            context.window_manager.modal_handler_add(self)
            if self.feature_id and not self.resume_saved:
                self.owner.check(context)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            if getattr(self, "owner", None):
                self.owner.cleanup()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        owner = self.owner
        # Pointer observations never survive clicks, navigation or keyboard
        # actions. TIMER redraws may retain them only while the binding matches.
        if event.type != "TIMER":
            owner.reuse_hover = None
        if not owner.alive:
            return {"FINISHED"} if owner.finished or owner.retained_for_repair else {"CANCELLED"}
        if not owner.valid_context():
            owner.suspend("Workspace or original editing context changed")
            return {"CANCELLED"}
        try:
            command, owner.command = owner.command, ""
            if command == "FINISH":
                owner.request_finish(context)
            elif command == "CANCEL":
                owner.discard()
                return {"CANCELLED"}
            # The edge picker owns its polling timers as well as pointer input.
            # Pass through before TIMER regardless of modal-handler ordering.
            if getattr(owner, "solid_projection_picker", None) is not None:
                return {"PASS_THROUGH"}
            if event.type == "TIMER":
                owner.tick(context)
                owner.area.tag_redraw()
                return (
                    {"FINISHED"}
                    if owner.finished or owner.retained_for_repair
                    else {"RUNNING_MODAL"}
                )
            # Own release even outside the viewport; never leave a held drag
            # behind after navigation, palette changes or a cancellation.
            if getattr(owner, "point_drag", None) is not None:
                if (
                    event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS"
                ) or event.type in NAVIGATION_EVENTS | {"WINDOW_DEACTIVATE"}:
                    owner.cancel_point_drag()
                    owner.area.tag_redraw()
                    return (
                        {"PASS_THROUGH"} if event.type in NAVIGATION_EVENTS else {"RUNNING_MODAL"}
                    )
                if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                    if _over_view(owner, event):
                        owner.update_point_drag(_xy(owner, event), _pointer(owner, event))
                        owner.finish_point_drag(context)
                    else:
                        owner.cancel_point_drag()
                    owner.area.tag_redraw()
                    return {"RUNNING_MODAL"}
                if event.type == "MOUSEMOVE":
                    if _over_view(owner, event):
                        owner.update_point_drag(_xy(owner, event), _pointer(owner, event))
                    owner.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if getattr(owner, "gesture_intent", None) is not None:
                return {"PASS_THROUGH"}
            if _navigation(owner, event):
                return {"PASS_THROUGH"}
            # A field owns its outside click and held-key tails. The next native
            # palette click can act on the retained input without leaking keys.
            if _route_field(owner, context, event):
                owner.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if workspace_ui.is_palette_event(context, event):
                _click_tracker(owner).reset()
                return {"PASS_THROUGH"}
            if event.type == "ESC" and event.value == "PRESS":
                if owner.pending:
                    owner.cancel_native()
                elif getattr(owner, "line_edit", None):
                    owner.line_edit = None
                    owner.message = "Trim/Extend cancelled; geometry unchanged."
                elif owner.draft.tool == "Dimension" and owner.draft.selection:
                    owner.draft.select(())
                    owner.message = "Dimension selection cancelled; geometry unchanged."
                elif owner.draft.proposal:
                    owner.cancel_line_proposal()
                else:
                    owner.suspend("Esc")
                    return {"CANCELLED"}
            if (
                getattr(owner, "line_edit", None)
                and event.value == "PRESS"
                and event.type in {"RET", "NUMPAD_ENTER"}
            ):
                _apply_line_edit(owner, context)
                owner.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if owner.pending is not None:
                return {"RUNNING_MODAL"} if _over_view(owner, event) else {"PASS_THROUGH"}
            if (event.type == "TAB" and event.value == "PRESS"
                and not event.ctrl and not event.alt and not event.is_repeat
                and owner.draft.tool == "Circle" and owner.draft.proposal is not None
                and owner.draft.proposal["kind"] == "circle"
                and owner.proposal_capture and owner.draft.pending_diameter is None
                and _over_view(owner, event) and not owner.navigation):
                owner.open_circle_diameter(context, _xy(owner, event))
                owner.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if (event.type == "TAB" and event.value == "PRESS"
                and not event.ctrl and not event.alt and not event.is_repeat
                and owner.draft.point_input_phase == ("line", "end")
                and owner.proposal_capture and owner.draft.pending_length is None
                and _over_view(owner, event) and not owner.navigation):
                endpoint, axis, error = _line_endpoint(owner, event)
                if error:
                    raise DraftError(error)
                owner.open_line_length(context, endpoint, _xy(owner, event), axis=axis)
                owner.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type == "MOUSEMOVE":
                _click_tracker(owner).move(_xy(owner, event))
            elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
                _click_tracker(owner).release(_xy(owner, event))
            elif event.value == "PRESS" and event.type != "LEFTMOUSE":
                _click_tracker(owner).reset()
            if not _over_view(owner, event):
                return {"PASS_THROUGH"}
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                if owner.annotation_drag:
                    owner.annotation_drag = None
                    owner.checkpoint()
            elif event.type == "MOUSEMOVE" and not owner.navigation:
                if owner.annotation_drag:
                    from .reference_dimensions import is_reference

                    placement = owner.draft.annotations[owner.annotation_drag]
                    if is_reference(placement):
                        geometry = owner.geometry()
                        source = getattr(geometry, placement["source_kind"] + "s")[
                            placement["refs"][0]
                        ]
                        center = (
                            tuple(
                                (a + b) / 2
                                for a, b in zip(source.start_mm, source.end_mm, strict=True)
                            )
                            if placement["kind"] == "length"
                            else source.center_mm
                        )
                    else:
                        relation = owner.geometry().dimensions[owner.annotation_drag]
                        if relation.kind == "radius":
                            geometry = owner.geometry()
                            curve_id = relation.refs[0]
                            curve = geometry.arcs.get(curve_id) or geometry.circles.get(curve_id)
                            if curve is None:
                                raise DraftError("This radius target is unavailable.")
                            center = curve.center_mm
                        elif relation.kind == "angle":
                            lines = [
                                owner.geometry().lines[reference] for reference in relation.refs
                            ]
                            center = tuple(
                                sum(
                                    point[axis]
                                    for line in lines
                                    for point in (line.start_mm, line.end_mm)
                                )
                                / 4
                                for axis in (0, 1)
                            )
                        else:
                            a, b = (owner.geometry().points[ref] for ref in relation.refs)
                            center = tuple((u + v) / 2 for u, v in zip(a, b, strict=True))
                    owner.draft.move_annotation(
                        owner.annotation_drag,
                        tuple(a - b for a, b in zip(_pointer(owner, event), center, strict=True)),
                    )
                elif owner.proposal_capture and owner.draft.proposal:
                    _move_proposal(owner, event)
                _update_reuse_hover(owner, event)
            elif (
                event.type in {"LEFT_SHIFT", "RIGHT_SHIFT"}
                and not owner.annotation_drag
                and not any(
                    _inside(_xy(owner, event), bounds)
                    for _, bounds in getattr(owner, "label_bounds", ())
                )
                and owner.proposal_capture
                and owner.draft.point_input_phase == ("line", "end")
                and not owner.navigation
            ):
                _move_proposal(owner, event)
                _update_reuse_hover(owner, event)
            elif event.type == "LEFTMOUSE" and event.value in {"PRESS", "DOUBLE_CLICK"}:
                _click(owner, context, event)
            elif event.value == "PRESS" and event.ctrl and event.type == "Z":
                owner.line_edit = None
                owner.local_history(context, redo=event.shift)
            elif event.value == "PRESS" and event.type in {"L", "R", "C", "D"}:
                tool = {"L": "Line", "R": "Rectangle", "C": "Circle", "D": "Dimension"}[event.type]
                if tool_available(context, tool):
                    owner.draft.select_tool(tool)
                    owner.draft.select(())
            owner.area.tag_redraw()
        except Exception as exc:
            owner.error = str(exc)
            if owner.input_controller:
                owner.input_controller.reject_accept()
            owner.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        if getattr(self, "owner", None) and self.owner.alive:
            self.owner.suspend("Viewport interaction ended")


class MCAD_OT_edit_general_sketch(Operator):
    """Compatibility entry; production Edit uses the shared explicit dispatcher."""

    bl_idname = "mcad.edit_general_sketch"
    bl_label = "Edit Selected General Sketch"
    bl_description = "Edit a supported general sketch while preserving its downstream features"

    @classmethod
    def poll(cls, context):
        if not _can_start_sketch(context):
            return False
        try:
            return _selected_editor(_state(context)) == "mcad.general_sketch"
        except (ValueError, KeyError, TypeError):
            return False

    def execute(self, context):
        if not self.poll(context):
            return {"CANCELLED"}
        state = _state(context)
        try:
            _begin_in_sketch(context, state.features[state.feature_index].feature_id)
        except (RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class MCAD_OT_general_tool(Operator):
    bl_idname = "mcad.general_tool"
    bl_label = "Sketch Tool"
    bl_description = "Choose an explicit sketch tool; existing draft geometry stays editable"
    tool: EnumProperty(
        items=[
            (name, name, name)
            for name in (
                "Select",
                "Points",
                "Line",
                "Rectangle",
                "Circle",
                "Arc",
                "Reverse",
                "UsePoint",
                "Dimension",
                "Trim",
                "Extend",
                "ApplyLineEdit",
                "CancelLineEdit",
                "Check",
                "CancelCheck",
                "Finish",
                "Continue",
                "CancelProposal",
                "Reopen",
                "CancelInput",
            )
        ]
    )

    @classmethod
    def description(cls, context, properties):
        owner = active(context)
        if owner is not None and owner.draft.pending_diameter is not None:
            if properties.tool == "CancelInput":
                return "Cancel diameter entry and keep the unfinished Circle for pointer placement"
            if properties.tool == "CancelProposal":
                return "Discard the unfinished Circle and its diameter input; accepted geometry is unchanged"
            if properties.tool == "Reopen":
                return "Reopen retained raw diameter with its captured center"
        if owner is not None and owner.draft.pending_length is not None:
            if properties.tool == "CancelInput":
                return "Cancel length entry and keep the unfinished Line for pointer placement"
            if properties.tool == "CancelProposal":
                return "Discard the unfinished Line and its length input; accepted geometry is unchanged"
            if properties.tool == "Reopen":
                return "Reopen the retained raw length with its captured direction and optional axis"
        return cls.bl_description

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def execute(self, context):
        owner = active(context)
        if not tool_available(context, self.tool):
            self.report(
                {"WARNING"},
                "This sketch action is unavailable until its current input or check is resolved",
            )
            return {"CANCELLED"}
        try:
            if self.tool in {"Arc", "Reverse", "UsePoint"}:
                owner.require_gesture_context(context)
            if self.tool == "Arc" and owner.draft.ui_version != 2:
                owner.enable_arc(owner.prepare_gesture("arc"))
                owner.area.tag_redraw()
                return {"FINISHED"}
            if self.tool == "Reverse":
                result = bpy.ops.mcad.reverse_arc_sweep("INVOKE_DEFAULT")
                return {"CANCELLED"} if "CANCELLED" in result else {"FINISHED"}
            if self.tool == "UsePoint":
                result = bpy.ops.mcad.use_existing_point("INVOKE_DEFAULT")
                return {"CANCELLED"} if "CANCELLED" in result else {"FINISHED"}
            if self.tool in {"Trim", "Extend"}:
                owner._require_idle()
                owner.draft.select_tool("Select")
                owner.line_edit = {"mode": self.tool, "revision": owner.commands.revision}
                owner.error = ""
                owner.message = (
                    "Pick target line near the endpoint to change, then a boundary line, circle or arc."
                )
            elif self.tool == "ApplyLineEdit":
                _apply_line_edit(owner, context)
            elif self.tool == "CancelLineEdit":
                owner.line_edit = None
                owner.message = "Trim/Extend cancelled; geometry unchanged."
            elif self.tool == "Check":
                owner.check(context)
            elif self.tool == "CancelCheck":
                owner.cancel_native()
            elif self.tool == "Finish":
                owner.request_finish(context)
            elif self.tool == "Continue":
                owner.draft.resume_proposal()
                owner.proposal_capture = True
            elif self.tool == "CancelProposal":
                owner.cancel_line_proposal()
            elif self.tool == "Reopen":
                if owner.draft.pending_diameter is not None:
                    owner.open_circle_diameter(context)
                elif owner.draft.pending_length is not None:
                    owner.open_line_length(context)
                else:
                    _open_field(owner, owner.commands.pending_edit.constraint_id, (100, 100))
            elif self.tool == "CancelInput":
                owner.cancel_dimension()
            else:
                owner._require_idle()
                owner.draft.select_tool("Select" if self.tool == "Points" else self.tool)
                owner.selection_mode = "point" if self.tool == "Points" else "geometry"
                if self.tool == "Dimension":
                    owner.draft.select(())
                    owner.message = "Pick a center/point then a straight reference line for perpendicular offset, or another point for distance."
                if self.tool == "Points":
                    owner.message = "Point selection: exact endpoints and centers. Overlapping IDs remain ambiguous."
                elif self.tool == "Rectangle":
                    owner.message = (
                        "Rectangle: choose two opposite corners, then Dimension its sides."
                    )
                elif self.tool == "Arc":
                    owner.message = (
                        "Center Arc: choose center, start and end. No constraints are inferred."
                    )
            owner.area.tag_redraw()
        except Exception as exc:
            owner.error = str(exc)
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class _GestureDialog:
    """Shared cancellation only; no registry or implicit execute admission."""

    def cancel(self, context):
        owner, binding = getattr(self, "owner", None), getattr(self, "binding", None)
        if owner is not None:
            owner.cancel_gesture(binding)

    def _prepare(self, context, kind):
        owner = active(context)
        if owner is None:
            raise DraftError("The original sketch owner is unavailable.")
        self.owner = owner
        owner.require_gesture_context(context)
        self.binding = owner.prepare_gesture(kind)

    def _failed(self, context, exc):
        self.cancel(context)
        self.report({"WARNING"}, str(exc))
        return {"CANCELLED"}


class MCAD_OT_remove_sketch_fillet(_GestureDialog, Operator):
    bl_idname = "mcad.remove_sketch_fillet"
    bl_label = "Restore Sharp Corner"
    bl_description = ("Remove the selected saved fillet and restore its original line intersection; "
                      "preserves original dimensions and other corners, refuses conflicting attachments")

    @classmethod
    def poll(cls, context):
        if tool_available(context, "RemoveFillet"):
            return True
        # Presentation only: the same owner dialog may bypass the busy hint.
        # Do not serialize history here; invoke/Apply enforce the full binding.
        owner = active(context)
        binding = getattr(owner, "gesture_intent", None)
        if owner is None or binding is None or binding.kind != "remove_fillet":
            return False
        try:
            # Poll must never consume another editor's live dialog.
            if (context.window != owner.window or context.scene != owner.scene
                    or context.area != owner.area or context.workspace != owner.workspace
                    or context.view_layer != owner.window.view_layer):
                return False
            return (binding.owner_token is owner.owner_token
                    and binding.draft is owner.draft and binding.commands is owner.commands
                    and binding.saved_slot == owner.stored_snapshot
                    and owner.scene.mechanical_cad.sketch_draft_json == owner.stored_snapshot
                    and owner.pending is None and owner.valid_context())
        except (ValueError, RuntimeError, AttributeError, ReferenceError):
            return False

    def invoke(self, context, event):
        try:
            self._prepare(context, "remove_fillet")
            self.arc_id = self.owner.draft.selection[0]["id"]
            self.review_record = self._review()
            return context.window_manager.invoke_props_dialog(self, width=550, confirm_text="Restore Sharp Corner")
        except Exception as exc:
            return self._failed(context, exc)

    def _review(self):
        from .sketch_remove_fillet import validate_annotation_attachments

        if self.owner.gesture_intent is not self.binding:
            raise DraftError("This removal review expired. Reopen Remove Sketch Fillet.")
        if self.owner.draft.selection != [{"kind": "arc", "id": self.arc_id}]:
            raise DraftError("The selected fillet changed. Reopen Remove Sketch Fillet.")
        if self.owner.current_solution_response() is None:
            raise DraftError("Check the sketch again before removing this fillet.")
        return validate_annotation_attachments(self.owner.draft, self.arc_id)

    def draw(self, context):
        self.layout.label(text="Restore both line ends to the original sharp corner.")
        self.layout.label(text="Removes this arc, its 3 private points and 5 required relations.")
        self.layout.label(text="Keeps original corner dimensions and all other fillets.")
        self.layout.label(text="Extra constraints, shared points and arc references prevent removal.")
        self.layout.label(text="Radius label placement stays visibly unavailable for Undo/Resume.")
        self.layout.label(text="Checks unchanged point placement before restoring. Cancel changes nothing.")
        self.layout.label(text="If free geometry would move, constrain it first. Finish validates the full Part.")
        # A read-only summary of the validated invocation; Apply recomputes it.
        record = getattr(self, "review_record", None)
        if record is not None:
            self.layout.label(text=f"Updates {len(record['peer_updates'])} neighboring fillet intent(s).")

    def execute(self, context):
        try:
            if active(context) is not getattr(self, "owner", None) or not hasattr(self, "binding"):
                raise DraftError("Open Remove Sketch Fillet before applying.")
            self.owner.require_gesture_context(context)
            self._review()
            self.owner._accept_gesture(self.binding, "remove_fillet")
            self.owner.request_fillet_removal(context, self.arc_id)
            return {"FINISHED"}
        except Exception as exc:
            return self._failed(context, exc)


class MCAD_OT_sketch_corner_fillet(_GestureDialog, Operator):
    bl_idname = "mcad.sketch_corner_fillet"
    bl_label = "Sketch Corner Fillet"
    bl_description = ("Round the shared corner of two selected straight lines with a real tangent arc. "
                      "Keeps the original corner as a dimensionable intersection witness; H/V stays intact")
    radius_mm: FloatProperty(name="Radius (mm)", default=1.0, min=0.000001, max=1000000, precision=4)
    show_limits: BoolProperty(name="Limits and retained intent", default=False)

    @classmethod
    def poll(cls, context):
        if tool_available(context, "CornerFillet"):
            return True
        # Blender polls again when a props dialog confirms. Only this exact
        # still-current owner gesture may cross the normal busy-input gate.
        owner = active(context)
        binding = getattr(owner, "gesture_intent", None)
        if owner is None or binding is None or binding.kind != "fillet":
            return False
        try:
            # Poll must never consume another editor's live dialog.
            if (context.window != owner.window or context.scene != owner.scene
                    or context.area != owner.area or context.workspace != owner.workspace
                    or context.view_layer != owner.window.view_layer):
                return False
            return (binding.owner_token is owner.owner_token
                    and binding.draft is owner.draft and binding.commands is owner.commands
                    and binding.snapshot == draft_dispatch.dumps(owner.draft)
                    and binding.saved_slot == owner.stored_snapshot
                    and owner.scene.mechanical_cad.sketch_draft_json == owner.stored_snapshot
                    and owner.pending is None and owner.valid_context())
        except (ValueError, RuntimeError, AttributeError, ReferenceError):
            return False

    def invoke(self, context, event):
        try:
            self._prepare(context, "fillet")
            self.line_ids = tuple(item["id"] for item in self.owner.draft.selection)
            self.positions = dict(self.owner.geometry().points)
            # An oversized default must not prevent the user entering a smaller radius.
            self.owner.corner_fillet_preview = None
            return context.window_manager.invoke_props_dialog(self, width=500, confirm_text="Apply")
        except Exception as exc:
            return self._failed(context, exc)

    def _preview(self):
        from .sketch_corner_fillet import prepare_corner

        self.owner.corner_fillet_preview = None
        if self.owner.gesture_intent is not self.binding:
            raise DraftError("This corner preview expired. Reopen Corner Fillet.")
        plan = prepare_corner(self.owner.commands.sketch, self.line_ids, self.radius_mm, self.positions)
        self.owner.corner_fillet_preview = (self.binding, plan, self.positions)
        self.owner.area.tag_redraw()
        return plan

    def draw(self, context):
        self.layout.prop(self, "radius_mm")
        self.layout.label(text="Purple: trimmed lines and tangent arc (unverified preview).")
        self.layout.label(text="Original corners stay dimensionable, including all four rectangle corners.")
        try:
            plan = self._preview()
            self.layout.label(text=f"Radius must stay below {plan.maximum_radius:.6g} mm.")
        except Exception as exc:
            self.layout.label(text=str(exc), icon="ERROR")
        self.layout.prop(self, "show_limits", icon="DISCLOSURE_TRI_DOWN" if self.show_limits else "DISCLOSURE_TRI_RIGHT")
        if self.show_limits:
            self.layout.label(text="H/V and point dimensions are retained; no constraints are deleted.")
            self.layout.label(text="Other line relations, coincident/projected/shared corners and collinear lines are refused.")
            self.layout.label(text="Adjacent fillets share a bounded line: their radii must leave a nonzero gap.")
            self.layout.label(text="Saved intent rejects overlapping radii and flipped branches on every native check.")
            self.layout.label(text="The witness lies on both infinite supporting lines, not on the trimmed segments.")
            self.layout.label(text="Apply runs native checks. Cancel changes nothing. Undo restores the corner.")

    def execute(self, context):
        try:
            if active(context) is not getattr(self, "owner", None) or not hasattr(self, "binding"):
                raise DraftError("Open Corner Fillet before applying.")
            self.owner.require_gesture_context(context)
            self._preview()
            self.owner._accept_gesture(self.binding, "fillet")
            self.owner.corner_fillet_preview = None
            self.owner.execute(context, CornerFillet(self.line_ids, self.radius_mm, self.positions))
            self.owner.message = "Corner fillet authored; native check pending. Edit its Radius dimension to resize."
            return {"FINISHED"}
        except Exception as exc:
            return self._failed(context, exc)


class MCAD_OT_enable_arc_editing(_GestureDialog, Operator):
    """Compatibility entry point: choosing Arc is the explicit authoring action."""

    bl_idname = "mcad.enable_arc_editing"
    bl_label = "Draw Center Arc"
    bl_description = "Choose center, start and end to draw an editable circular arc"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        try:
            self._prepare(context, "arc")
            self.owner.enable_arc(self.binding)
            self.owner.area.tag_redraw()
            return {"FINISHED"}
        except Exception as exc:
            return self._failed(context, exc)


def _picker_catalog(properties, context):
    # A property callback has no access to Python-only operator attributes.
    # Resolve only display data belonging to this exact still-open gesture.
    if context is None:
        return None
    try:
        owner = active(context)
        return (
            owner.point_picker_catalog(getattr(properties, "picker_token", ""), context)
            if owner is not None
            else None
        )
    except (AttributeError, ReferenceError):
        return None


def _point_items(properties, context):
    catalog = _picker_catalog(properties, context)
    return catalog.point_items if catalog is not None else POINT_PICKER_EMPTY


def _source_items(properties, context):
    catalog = _picker_catalog(properties, context)
    return (
        catalog.source_items.get(getattr(properties, "point_id", ""), POINT_SOURCE_EMPTY)
        if catalog is not None
        else POINT_SOURCE_EMPTY
    )


def _point_changed(operator, context):
    # Source selection must be explicit for the newly chosen exact point ID.
    operator.source = "point"


class MCAD_OT_use_existing_point(_GestureDialog, Operator):
    bl_idname = "mcad.use_existing_point"
    bl_label = "Use Existing Point"
    bl_description = "Choose one exact point ID and source role for the current Line or Arc phase"
    bl_options = {"INTERNAL"}
    picker_token: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    point_id: EnumProperty(name="Exact point ID", items=_point_items, update=_point_changed)
    source: EnumProperty(name="Source and role", items=_source_items)

    def invoke(self, context, event):
        try:
            self._prepare(context, "point")
            catalog = self.binding.point_catalog
            # Keep the binding (and every returned string) alive for the full
            # popup lifetime, even after its owner's gesture has been retired.
            self.point_items = catalog.point_items
            self.picker_token = catalog.token
            self.point_id = catalog.sentinel
            self.source = "point"
            return context.window_manager.invoke_props_dialog(self, width=520)
        except Exception as exc:
            return self._failed(context, exc)

    def _failed(self, context, exc):
        owner, binding = getattr(self, "owner", None), getattr(self, "binding", None)
        # Keep failures visible without writing a replacement/foreign owner's
        # overlay or disturbing a newer dialog belonging to the same session.
        show = False
        try:
            show = (
                owner is not None
                and active(context) is owner
                and context.window == owner.window
                and context.scene == owner.scene
                and context.area == owner.area
                and context.workspace == owner.workspace
                and context.view_layer == owner.window.view_layer
                and (owner.gesture_intent is None or owner.gesture_intent is binding)
            )
            if show and binding is not None:
                show = (
                    binding.owner_token is owner.owner_token
                    and binding.draft is owner.draft
                    and binding.commands is owner.commands
                )
        except (AttributeError, ReferenceError):
            show = False
        result = super()._failed(context, exc)
        if show:
            owner.error = str(exc)
            try:
                owner.area.tag_redraw()
            except (AttributeError, ReferenceError):
                pass
        return result

    def draw(self, context):
        phase = self.binding.phase
        self.layout.label(text=f"{phase[0].title()} · choose {phase[1]} point")
        self.layout.prop(self, "point_id")
        self.layout.prop(self, "source")
        self.layout.label(text="Exact identity only. No snapping or coincidence relation is added.")
        self.layout.label(text="Pointer input stays paused; use Continue to resume it.")

    def execute(self, context):
        try:
            if active(context) is not getattr(self, "owner", None) or not hasattr(self, "binding"):
                raise DraftError("Open the exact-point picker before confirming.")
            catalog = self.binding.point_catalog
            if catalog is None or self.picker_token != catalog.token:
                raise DraftError("This exact-point picker changed; reopen it.")
            if self.point_id not in self.binding.points:
                raise DraftError("Choose an exact point ID before confirming.")
            choices = {item[0] for item in catalog.source_items.get(self.point_id, ())}
            if self.source not in choices:
                raise DraftError("This point does not have the selected source role.")
            kind, source, role = catalog.source_bindings[self.source]
            self.owner.accept_point_input(
                context,
                PointRef(self.point_id),
                expected_phase=self.binding.phase,
                source_kind=kind,
                source_id=source,
                role=role,
                picker=self.binding,
            )
            self.owner.area.tag_redraw()
            return {"FINISHED"}
        except Exception as exc:
            return self._failed(context, exc)


class MCAD_OT_reverse_arc_sweep(_GestureDialog, Operator):
    bl_idname = "mcad.reverse_arc_sweep"
    bl_label = "Reverse Arc Sweep"
    bl_description = "Choose the complementary directed sweep without swapping point roles"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        try:
            self._prepare(context, "reverse")
            self.proposal = self.owner.draft.proposal is not None
            return context.window_manager.invoke_props_dialog(self, width=500)
        except Exception as exc:
            return self._failed(context, exc)

    def draw(self, context):
        self.layout.label(
            text="Reverse this unfinished proposal?"
            if self.proposal
            else "Reverse the selected arc's accepted sweep?"
        )
        self.layout.label(text="Center, start and end identities stay unchanged.")
        self.layout.label(
            text="The complementary arc changes the boundary and can change area and volume."
        )
        if self.proposal:
            self.layout.label(
                text="This changes only proposal direction; no command is accepted yet."
            )

    def execute(self, context):
        try:
            if active(context) is not getattr(self, "owner", None) or not hasattr(self, "binding"):
                raise DraftError("Open the sweep disclosure before confirming.")
            self.owner.reverse_arc(context, self.binding)
            self.owner.area.tag_redraw()
            return {"FINISHED"}
        except Exception as exc:
            return self._failed(context, exc)


CLASSES = (
    MCAD_OT_new_plane_sketch,
    MCAD_OT_new_face_sketch,
    MCAD_OT_copied_face_sketch,
    MCAD_OT_project_sketch_geometry,
    MCAD_OT_sketch_normal_view,
    MCAD_OT_general_sketch,
    MCAD_OT_edit_general_sketch,
    MCAD_OT_general_tool,
    MCAD_OT_enable_arc_editing,
    MCAD_OT_sketch_corner_fillet,
    MCAD_OT_remove_sketch_fillet,
    MCAD_OT_use_existing_point,
    MCAD_OT_reverse_arc_sweep,
)
