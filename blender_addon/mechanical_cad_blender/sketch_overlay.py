"""Drawing-only rectangle preview and screen-space dimensions.

Callbacks are scoped to the owning window, workspace and viewport. They never
change the model, call the sidecar, or create Blender object/mesh datablocks.
"""

import textwrap

import blf
import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .common import MM_TO_METERS


def _here(session):
    try:
        context = bpy.context
        return (
            session.alive
            and context.window == session.window
            and context.area == session.area
            and context.workspace == session.workspace
            and context.scene == session.scene
        )
    except ReferenceError:
        return False


def _world(session, point):
    factor = MM_TO_METERS / max(float(session.scene.unit_settings.scale_length), 1e-9)
    return Vector((point[0] * factor, point[1] * factor, 0))


def draw_lines(session):
    if not _here(session) or session.draft.phase == "FIRST_POINT":
        return
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    points = [_world(session, point) for point in session.draft.points()]
    previous_depth = gpu.state.depth_test_get()
    gpu.state.depth_test_set("NONE")
    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(2)
    shader.bind()
    shader.uniform_float(
        "color", (1.0, 0.42, 0.10, 1.0) if session.draft.error else (0.12, 0.8, 1.0, 1.0)
    )
    batch_for_shader(shader, "LINE_STRIP", {"pos": points}).draw(shader)
    gpu.state.line_width_set(1)
    gpu.state.blend_set("NONE")
    gpu.state.depth_test_set(previous_depth)


def _text(x, y, text, size=14, color=(0.92, 0.96, 1.0, 1.0)):
    blf.position(0, x, y, 0)
    blf.size(0, size)
    blf.color(0, *color)
    blf.draw(0, text)


def draw_text(session):
    if not _here(session):
        return
    draft = session.draft
    scale = max(float(bpy.context.preferences.system.ui_scale), 0.5)
    x, y = 82 * scale, 26 * scale
    right = session.region.width
    for region in session.area.regions:
        if region.type == "UI" and region.width > 1 and region.x > session.region.x:
            right = min(right, region.x - session.region.x)
    width = max(20, min(110, int((right - x - 20) / (7 * scale))))

    def paragraph(text, color=(0.92, 0.96, 1.0, 1.0)):
        nonlocal y
        for line in textwrap.wrap(text, width=width):
            _text(x, y, line, 13 * scale, color)
            y += 20 * scale
        y += 2 * scale

    hint = {
        "FIRST_POINT": "Rectangle: click the first corner on XY · Esc cancels",
        "SECOND_POINT": "Click the opposite corner · Middle mouse / wheel navigate · Esc cancels",
        "DIMENSIONS": "D: edit dimensions · Enter: Finish Sketch · Esc: discard draft",
    }[draft.phase]
    paragraph(hint)
    paragraph("Switching workspace suspends this draft. Resume it explicitly when you return.")
    if draft.phase != "FIRST_POINT":
        positioning = "fixed" if draft.fix_corner else "free translation"
        anchor = f"Lower-left in sketch coordinates: {positioning} · X {draft.anchor[0]:.6g}, Y {draft.anchor[1]:.6g} mm · H/V edges"
        paragraph(anchor)
    report = session.current_solver_report() if not session.popup_open else None
    if session.popup_open or draft.pending_dimensions is not None:
        solver = "Dimension inputs are not applied yet; the outline shows the last-applied draft."
    elif report:
        dof = report.get("remaining_dof")
        solver = f"Solver: {report.get('status', 'unknown')} · remaining DoF: {dof if dof is not None else 'unavailable'}"
        failed = report.get("failed_constraints") or []
        if failed:
            solver += " · diagnostic constraint candidates: " + ", ".join(
                str(item) for item in failed
            )
    else:
        solver = "Preview is unverified; Apply Dimensions or Finish runs the real sketch solver."
    paragraph(solver)
    if draft.error:
        paragraph(draft.error, (1.0, 0.55, 0.2, 1.0))
    if draft.phase != "FIRST_POINT":
        anchor_screen = view3d_utils.location_3d_to_region_2d(
            session.region, session.rv3d, _world(session, draft.anchor)
        )
        if anchor_screen is not None:
            _text(
                anchor_screen.x - 6 * scale,
                anchor_screen.y - 5 * scale,
                "+",
                22 * scale,
                (1.0, 0.65, 0.15, 1.0),
            )
            _text(
                anchor_screen.x + 8 * scale,
                anchor_screen.y + 8 * scale,
                "fixed" if draft.fix_corner else "free",
                12 * scale,
            )
        ax, ay = draft.anchor
        dimensions = (
            ((ax + draft.width / 2, ay), f"W {draft.width:.6g} mm", (0, -22)),
            ((ax + draft.width, ay + draft.height / 2), f"H {draft.height:.6g} mm", (12, 0)),
        )
        for point, label, offset in dimensions:
            screen = view3d_utils.location_3d_to_region_2d(
                session.region, session.rv3d, _world(session, point)
            )
            if screen is not None:
                _text(screen.x + offset[0] * scale, screen.y + offset[1] * scale, label, 15 * scale)
