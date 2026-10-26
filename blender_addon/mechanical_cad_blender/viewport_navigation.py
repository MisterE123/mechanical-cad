"""Conservative native navigation UI exclusion, never geometry hit authority.

Blender does not expose the built-in gizmo map's hit test through RNA. Derive
its reserved footprint from visible viewport edges and user settings instead of
fixed screen coordinates. Layout source: Blender v5.0.0,
https://github.com/blender/blender/blob/v5.0.0/source/blender/editors/space_view3d/view3d_gizmo_navigate.cc
Also checked against upstream main on 2026-10-24 (2.2 axis spacing). Runtime
qualification is separate: Blender 5.2.2 d13f752e3b9c. Layout units are:
10 edge margin, 28 mini button size, 2 button gap. Reserve all mini slots so view
lock/camera changes cannot expose a UI-covered face to the CAD picker.
"""


def navigation_bounds(context, region):
    space = context.area.spaces.active
    view = context.preferences.view
    if not space.show_gizmo or not space.show_gizmo_navigate:
        return None
    rotate = view.mini_axis_type == "GIZMO"
    if not rotate and not view.show_navigate_ui:
        return None
    scale = context.preferences.system.ui_scale
    scale = scale if scale > 0 else 1.0
    right, top = region.x + region.width, region.y + region.height
    for overlay in context.area.regions:
        if overlay is region or overlay.width <= 1 or overlay.height <= 1:
            continue
        if overlay.type == "UI" and overlay.alignment == "RIGHT" and region.x < overlay.x < right:
            right = overlay.x
        if (
            overlay.type in {"HEADER", "TOOL_HEADER"}
            and overlay.alignment == "TOP"
            and region.y < overlay.y < top
        ):
            top = overlay.y
    size = view.gizmo_size_navigate_v3d if rotate else 0
    width = max(size + 20, 40) * scale
    height = (size + 20) * scale
    if view.show_navigate_ui:
        if rotate:
            start = (10 + size / 2) * 2.2
        elif view.mini_axis_type == "MINIMAL":
            start = max(40 + view.mini_axis_size * 1.6, 50 + view.mini_axis_size * 2)
        else:
            start = 30 * 0.75
        height = max(height, (start + 4 * 30 + 14) * scale)
    return right - width, top - height, right, top


def is_navigation_event(context, region, event):
    bounds = navigation_bounds(context, region)
    if bounds is None:
        return False
    left, bottom, right, top = bounds
    return left <= event.mouse_x <= right and bottom <= event.mouse_y <= top


def navigation_passthrough(picker, context, event):
    """Keep a UI-started drag out of face picking even after leaving its bounds."""
    if event.type not in {"LEFTMOUSE", "MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
        return False
    active = getattr(picker, "navigation_drag", False)
    over = is_navigation_event(context, picker.region, event)
    if event.type == "LEFTMOUSE":
        if event.value == "PRESS":
            # A native modal may consume its release before our handler sees it.
            # A new press begins a new gesture, never keeps an old drag latched.
            active = False
            picker.navigation_drag = over
        elif event.value == "RELEASE":
            picker.navigation_drag = False
    if active or over:
        picker.hit, picker.points = None, []
        picker.area.tag_redraw()
        return True
    return False
