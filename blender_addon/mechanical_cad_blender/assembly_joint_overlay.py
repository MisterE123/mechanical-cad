"""Bounded disposable joint overlay geometry; no model or backend authority.

The panel layout and handle geometry are shared by drawing and hit testing.
Blender/GPU imports are deliberately lazy so layout contracts remain pure tests.
"""

from __future__ import annotations

import math
import textwrap
from contextlib import contextmanager
from dataclasses import dataclass

AXIS_COLORS = ((1.0, 0.26, 0.22, 1.0), (0.3, 0.9, 0.38, 1.0), (0.3, 0.57, 1.0, 1.0))
GOLD = (1.0, 0.71, 0.18, 0.9)
TEXT = (0.92, 0.94, 0.97, 1.0)
MUTED = (0.65, 0.71, 0.79, 1.0)


@dataclass(frozen=True)
class Button:
    action: str
    label: str
    hint: str
    bounds: tuple
    selected: bool = False
    enabled: bool = True


@dataclass(frozen=True)
class Label:
    text: str
    position: tuple
    color: tuple = TEXT
    hint: str = ""


@dataclass(frozen=True)
class Panel:
    bounds: tuple
    buttons: tuple
    labels: tuple
    scale: float
    font_size: float


@dataclass(frozen=True)
class Handle:
    end: str
    axis: str
    origin: tuple
    tip: tuple
    selected: bool


def inside(point, bounds):
    return bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]


def segment_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = (
        max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length))
        if length
        else 0.0
    )
    return math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy)


def pick_handle(handles, point, *, scale=1.0):
    """Prefer the active connector when two literal connectors coincide."""
    choices = [
        (segment_distance(point, h.origin, h.tip), not h.selected, h)
        for h in handles
        if math.dist(h.origin, h.tip) >= 5 * scale
    ]
    # The active connector wins overlapping axes, then the nearest line wins.
    choices = [row for row in choices if row[0] <= 9 * scale]
    if not choices:
        return None
    choices.sort(key=lambda row: (row[1], row[0]))
    return choices[0][2]


def hit_button(panel, point):
    return next((b for b in panel.buttons if inside(point, b.bounds)), None)


def hint_at(panel, point):
    button = hit_button(panel, point)
    if button is not None:
        return button.hint
    for label in panel.labels:
        bounds = (
            label.position[0],
            label.position[1] - 3 * panel.scale,
            panel.bounds[2],
            label.position[1] + 14 * panel.scale,
        )
        if label.hint and inside(point, bounds):
            return label.hint
    return ""


def build_motion_panel(
    usable_rect,
    *,
    scale=1.0,
    name="",
    angle=0.0,
    kind="revolute",
    distance=0.0,
    field="",
    ready=False,
    status="",
    error="",
    followers="",
):
    """Motion-only controls; no connector handles or follower edit affordance."""
    if kind not in {"revolute", "slider"}:
        raise ValueError("Motion panel supports revolute or slider coordinates only.")
    linear = kind == "slider"
    unit = " mm" if linear else "°"
    shown = distance if linear else angle
    if len(usable_rect) != 4 or not all(math.isfinite(v) for v in usable_rect):
        raise ValueError("Motion panel requires finite viewport bounds.")
    left, bottom, right, top = usable_rect
    if right <= left or top <= bottom or not math.isfinite(scale):
        raise ValueError("Motion panel requires a nonempty viewport and finite scale.")
    scale = min(max(1.0, min(3.0, scale)), (right - left) / 302, (top - bottom) / 280)
    if scale < 1:
        # The established compact fallback always keeps Cancel reachable.
        return build_panel(usable_rect, scale=1.0)
    width, height = 302 * scale, 280 * scale
    bounds = (left, bottom, left + width, bottom + height)
    x, y = left + 9 * scale, bottom + height - 21 * scale
    labels = []
    for text, color in (
        ("Slider motion · not saved / checked" if linear else "Driver motion · not saved / checked", GOLD),
        (("Independent slider: " if linear else "Independent driver: ") + name, TEXT),
        ("Slide along mate +Z (mm)" if linear else "Angle about mate +Z (degrees)", MUTED),
    ):
        labels.append(Label(text, (x, y), color, text))
        y -= 19 * scale
    step_width = 64 if linear else 45
    buttons = [
        Button(
            "minus",
            "−1" + unit,
            "Decrease slider by one millimetre." if linear else "Decrease independent driver by one degree.",
            (x, y - 24 * scale, x + step_width * scale, y),
        ),
        Button(
            "distance",
            field or f"{shown:.7g}{unit}",
            "Type exact slide distance in mm; Enter previews it." if linear else "Type exact driver angle; Enter previews it.",
            (x + (step_width + 5) * scale, y - 24 * scale, x + (279 - step_width) * scale, y),
            bool(field),
        ),
        Button(
            "plus",
            "+1" + unit,
            "Increase slider by one millimetre." if linear else "Increase independent driver by one degree.",
            (x + (284 - step_width) * scale, y - 24 * scale, x + 284 * scale, y),
        ),
    ]
    y -= 45 * scale
    for text, color in (
        ("All assembly branches evaluated" if linear else "All branches evaluated; followers read-only", MUTED),
        (followers or ("Other joint coordinates remain unchanged" if linear else "Controlled angles follow explicit gear relations"), MUTED),
        (status, GOLD),
    ):
        labels.append(Label(text, (x, y), color, text))
        y -= 19 * scale
    for line in textwrap.wrap(error or "No contact or dynamics verification.", width=39)[:3]:
        labels.append(Label(line, (x, y), GOLD if error else MUTED, error))
        y -= 16 * scale
    buttons.extend(
        (
            Button(
                "apply",
                "Apply slider motion" if linear else "Apply driver motion",
                "Save only this exact completed preview. Fresh replay must match.",
                (x, bottom + 10 * scale, x + 174 * scale, bottom + 36 * scale),
                enabled=ready,
            ),
            Button(
                "cancel",
                "Cancel / Esc",
                "Discard all motion intent; retain the accepted assembly.",
                (x + 179 * scale, bottom + 10 * scale, x + 284 * scale, bottom + 36 * scale),
            ),
        )
    )
    return Panel(bounds, tuple(buttons), tuple(labels), scale, 11.5 * scale)


def build_panel(
    usable_rect,
    *,
    scale=1.0,
    parent_name="",
    child_name="",
    joint_name="",
    replaced_name="",
    selected="parent",
    kind="fixed",
    distance=0.0,
    ready=False,
    error="",
    hint="",
    field="",
    connector_xyz=None,
    mate_faces=False,
    support_id=None,
    target_name="",
    target_role="parent",
    target_switch=False,
):
    """Keep all controls inside the actual usable viewport, including UI scaling."""
    if len(usable_rect) != 4 or not all(math.isfinite(v) for v in usable_rect):
        raise ValueError("Joint panel requires finite viewport bounds.")
    left, bottom, right, top = usable_rect
    if right <= left or top <= bottom:
        raise ValueError("Joint panel requires a nonempty viewport.")
    if not math.isfinite(scale):
        raise ValueError("Joint panel requires a finite UI scale.")
    scale = max(1.0, min(3.0, float(scale)))
    panel_height = 474.0 if target_name or target_switch else 426.0
    fitted = min(scale, (right - left) / 302.0, (top - bottom) / panel_height)
    if fitted < 1.0:
        width, height = min(right - left, 302 * scale), min(top - bottom, 105 * scale)
        bounds = (left, bottom, left + width, bottom + height)
        pad = min(6.0, width / 8)
        button_height = min(28 * scale, max(1, height - 2 * pad))
        button = Button(
            "cancel",
            "Cancel / Esc",
            "Enlarge the 3D viewport to edit a visual joint.",
            (left + pad, bottom + pad, left + width - pad, bottom + pad + button_height),
        )
        labels = (
            (
                Label(
                    "Enlarge viewport to edit joints",
                    (left + pad, bottom + height - 18 * scale),
                    GOLD,
                ),
            )
            if height > button_height + 35 * scale
            else ()
        )
        return Panel(bounds, (button,), labels, scale, 11.5 * scale)
    scale = fitted
    width, height = 302 * scale, panel_height * scale
    bounds = (left, bottom, left + width, bottom + height)
    labels, buttons = [], []
    pad, row_h, gap = 9 * scale, 25 * scale, 5 * scale
    y = bottom + height - 21 * scale

    def label(text, color=TEXT, hint=""):
        nonlocal y
        labels.append(Label(str(text), (left + pad, y), color, hint))
        y -= 18 * scale

    def row(items, weights=None):
        nonlocal y
        available = width - 2 * pad - gap * (len(items) - 1)
        weights = weights or [1] * len(items)
        x = left + pad
        for weight, (action, text, explanation, chosen, enabled) in zip(
            weights, items, strict=True
        ):
            cell = available * weight / sum(weights)
            buttons.append(
                Button(
                    action,
                    text,
                    explanation,
                    (x, y - row_h + 4 * scale, x + cell, y + 4 * scale),
                    chosen,
                    enabled,
                )
            )
            x += cell + gap
        y -= row_h + gap

    label(("Mate by Faces" if mate_faces else "Visual joint") + " · Preview not checked", GOLD)
    if target_name or target_switch:
        label(
            target_role.title()
            + ": "
            + (target_name + " (isolated)" if target_name else "choose target below"),
            GOLD,
            hint="Temporarily showing only this assembly component for face picking: "
            + target_name,
        )
        row(
            [
                (
                    "target_prev",
                    "Previous",
                    "Show the previous eligible target component only.",
                    False,
                    target_switch,
                ),
                (
                    "target_next",
                    "Next target",
                    "Show the next eligible target component only.",
                    False,
                    target_switch,
                ),
            ]
        )
    label(
        "Parent: "
        + (parent_name or ("click a planar face" if mate_faces else "click an assembly instance")),
        hint="Parent instance: " + parent_name if parent_name else "",
    )
    label(
        "Child: "
        + (
            child_name
            or (
                ("click child planar face" if mate_faces else "click another instance")
                if parent_name
                else "choose parent first"
            )
        ),
        hint="Child instance: " + child_name if child_name else "",
    )
    label(
        "Replaces: " + replaced_name if replaced_name else "Choose two existing instances",
        MUTED,
        hint="Apply replaces the child’s existing incoming joint: " + replaced_name
        if replaced_name
        else "",
    )
    row(
        [
            (
                "parent",
                "Parent handle",
                "Edit the parent connector at its accepted placement.",
                selected == "parent",
                ready,
            ),
            (
                "child",
                "Child handle",
                "Edit the child connector at its accepted placement.",
                selected == "child",
                ready,
            ),
            (
                "reselect",
                "Pick pair",
                "Discard this preview and select parent, then child again.",
                False,
                bool(parent_name),
            ),
        ]
    )
    row(
        [
            ("fixed", "Fixed", "Align the two connectors rigidly.", kind == "fixed", ready),
            (
                "slider",
                "Slider",
                "Translate along the parent connector's +Z direction.",
                kind == "slider",
                ready,
            ),
            (
                "revolute",
                "Revolute",
                "Rotate about the parent connector's +Z; author angles in degrees.",
                kind == "revolute",
                ready,
            ),
        ]
    )
    row(
        [
            (
                "cylindrical",
                "Cylindrical",
                "Translate and rotate about Z. Named motion/limits use joint Edit after Apply.",
                kind == "cylindrical",
                ready,
            ),
            (
                "planar",
                "Planar",
                "XY translation and Z rotation. Named motion/limits use joint Edit after Apply.",
                kind == "planar",
                ready,
            ),
            (
                "spherical",
                "Ball",
                "XYZ rotations at fixed center. Named motion/limits use joint Edit after Apply.",
                kind == "spherical",
                ready,
            ),
        ]
    )
    label(
        "New pair: centroids / opposing normals"
        if mate_faces
        else "Literal coordinates; no persistent face attachment",
        MUTED,
        hint=("Attached: " + support_id)
        if support_id
        else "No face attached to selected connector",
    )
    if connector_xyz is not None:
        label("Local XYZ: " + ", ".join(f"{v:.5g}" for v in connector_xyz) + " mm", MUTED)
    else:
        label("Local XYZ: choose a connector", MUTED)
    row(
        [
            (
                "surface",
                "Pick face" if mate_faces else "Pick surface",
                "Replace stable planar support; existing face-local offset and Flip are retained."
                if mate_faces
                else "Sample point and normal on the selected instance. Stores literal coordinates, NOT a persistent face attachment.",
                False,
                ready,
            ),
            (
                "origin",
                "Origin",
                "Reset selected connector to its Part-local origin and axes.",
                False,
                ready,
            ),
            (
                "roll",
                "Roll 90°",
                "Turn the selected connector about its local Z axis.",
                False,
                ready,
            ),
        ]
    )
    label("Selected connector +Z direction", MUTED)
    row(
        [
            (
                "axis_X",
                "+X",
                "Point the selected connector's +Z along its instance-local +X.",
                False,
                ready,
            ),
            (
                "axis_Y",
                "+Y",
                "Point the selected connector's +Z along its instance-local +Y.",
                False,
                ready,
            ),
            (
                "axis_Z",
                "+Z",
                "Point the selected connector's +Z along its instance-local +Z.",
                False,
                ready,
            ),
            ("flip", "Flip", "Reverse the selected connector's +Z direction.", False, ready),
        ]
    )
    shown_distance = field if field else f"{distance:.6g}"
    unit = "°" if kind == "revolute" else "mm"
    motion = "Angle" if kind == "revolute" else "Slide"
    row(
        [
            (
                "distance",
                (
                    "Motion: joint Edit"
                    if kind in {"planar", "spherical"}
                    else f"{motion}: {shown_distance} {unit}"
                ),
                "Named axes and all limits are preserved; use existing joint Edit after Apply. Scalar angle/slide: Enter accepts.",
                bool(field),
                ready and kind in {"slider", "revolute", "cylindrical"},
            ),
            (
                "minus",
                "−1",
                "Decrease motion by one degree or millimetre.",
                False,
                ready and kind in {"slider", "revolute", "cylindrical"},
            ),
            (
                "plus",
                "+1",
                "Increase motion by one degree or millimetre.",
                False,
                ready and kind in {"slider", "revolute", "cylindrical"},
            ),
        ],
        weights=[3, 1, 1],
    )
    row(
        [
            (
                "apply",
                "Apply joint",
                "Replay the candidate through the guarded assembly transaction; then run an explicit pose check.",
                False,
                ready and not field,
            ),
            (
                "clear_motion",
                "Reset motion",
                "Explicitly zero ALL motion coordinates and remove ALL motion limits before changing kind.",
                False,
                ready,
            ),
            (
                "cancel",
                "Cancel / Esc",
                "Discard all transient joint edits; accepted assembly and display stay unchanged.",
                False,
                True,
            ),
        ]
    )
    message = (
        error
        or hint
        or (
            "Drag RGB axes · X/Y/Z constrain · type mm"
            if ready
            else "Click owned meshes · middle mouse or wheel navigates"
        )
    )
    # Two bounded lines; actual font clipping also applies at draw time.
    limit = 45
    words, lines, line = message.split(), [], ""
    for word in words:
        if line and len(line) + len(word) + 1 > limit:
            lines.append(line)
            line = word
        else:
            line += (" " if line else "") + word
    lines.append(line)
    for text in lines[:2]:
        label(text, (1.0, 0.45, 0.25, 1.0) if error else MUTED)
    return Panel(bounds, tuple(buttons), tuple(labels), scale, 11.5 * scale)


@contextmanager
def drawing_state():
    import gpu

    previous = (
        gpu.state.blend_get(),
        gpu.state.depth_test_get(),
        gpu.state.depth_mask_get(),
        gpu.state.line_width_get(),
    )
    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        gpu.state.depth_mask_set(False)
        yield
    finally:
        try:
            gpu.state.line_width_set(previous[3])
        finally:
            try:
                gpu.state.depth_mask_set(previous[2])
            finally:
                try:
                    gpu.state.depth_test_set(previous[1])
                finally:
                    gpu.state.blend_set(previous[0])


def _batch(shader, mode, points, color):
    from gpu_extras.batch import batch_for_shader

    if not points:
        return
    shader.bind()
    shader.uniform_float("color", color)
    batch_for_shader(shader, mode, {"pos": points}).draw(shader)


def _box(shader, bounds, color):
    x, y, right, top = bounds
    _batch(
        shader, "TRIS", ((x, y), (right, y), (right, top), (x, y), (right, top), (x, top)), color
    )


def _text(text, position, size, color, max_width):
    import blf

    blf.size(0, size)
    if max_width <= 0:
        return
    if blf.dimensions(0, text)[0] > max_width:
        while text and blf.dimensions(0, text + "…")[0] > max_width:
            text = text[:-1]
        text += "…"
    blf.position(0, *position, 0)
    blf.color(0, *color)
    blf.draw(0, text)


def draw_panel(panel, handles, connector_labels, *, hover="", hint="", usable_rect=None):
    """Draw precisely the bounds used by the modal owner's hit tests."""
    import gpu

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    with drawing_state():
        for handle in sorted(handles, key=lambda h: h.selected):
            color = AXIS_COLORS["XYZ".index(handle.axis)]
            gpu.state.line_width_set((3.5 if handle.selected else 1.5) * panel.scale)
            _batch(shader, "LINES", (handle.origin, handle.tip), color)
            size = 4 * panel.scale
            x, y = handle.tip
            _box(shader, (x - size, y - size, x + size, y + size), color)
            direction = (handle.tip[0] - handle.origin[0], handle.tip[1] - handle.origin[1])
            length = math.hypot(*direction)
            if length > 1:
                dx, dy = (value / length for value in direction)
                arrow = (
                    (x, y),
                    (
                        x - 10 * panel.scale * dx + 5 * panel.scale * dy,
                        y - 10 * panel.scale * dy - 5 * panel.scale * dx,
                    ),
                    (
                        x - 10 * panel.scale * dx - 5 * panel.scale * dy,
                        y - 10 * panel.scale * dy + 5 * panel.scale * dx,
                    ),
                )
                _batch(shader, "TRIS", arrow, color)
            label = ("P +" if handle.end == "parent" else "C +") + handle.axis
            _text(
                label,
                (x + 6 * panel.scale, y + 4 * panel.scale),
                panel.font_size,
                color,
                70 * panel.scale,
            )
        for text, point, selected in connector_labels:
            _text(
                text,
                (point[0] + 8 * panel.scale, point[1] - 19 * panel.scale),
                panel.font_size,
                GOLD if selected else TEXT,
                180 * panel.scale,
            )
        _box(shader, panel.bounds, (0.025, 0.033, 0.047, 0.95))
        for button in panel.buttons:
            color = (0.11, 0.29, 0.43, 1.0) if button.selected else (0.13, 0.16, 0.20, 1.0)
            if hover == button.action and button.enabled:
                color = (0.23, 0.33, 0.40, 1.0)
            _box(shader, button.bounds, color)
            _text(
                button.label,
                (button.bounds[0] + 5 * panel.scale, button.bounds[1] + 7 * panel.scale),
                panel.font_size,
                TEXT if button.enabled else (0.4, 0.43, 0.48, 1),
                button.bounds[2] - button.bounds[0] - 10 * panel.scale,
            )
        for label in panel.labels:
            _text(
                label.text,
                label.position,
                panel.font_size,
                label.color,
                panel.bounds[2] - label.position[0] - 9 * panel.scale,
            )

        if hint and usable_rect is not None:
            tooltip_bounds, tooltip_labels = tooltip_layout(hint, panel, usable_rect)
            _box(shader, tooltip_bounds, (0.06, 0.085, 0.12, 0.98))
            for label in tooltip_labels:
                _text(
                    label.text,
                    label.position,
                    panel.font_size,
                    TEXT,
                    tooltip_bounds[2] - label.position[0] - 7 * panel.scale,
                )


def tooltip_layout(hint, panel, usable_rect):
    left, bottom, right, top = usable_rect
    scale = panel.scale
    width = min(355 * scale, right - left)
    characters = max(1, int((width - 14 * scale) / (6.3 * scale)))
    lines = textwrap.wrap(hint, width=characters) or [""]
    lines = lines[: max(1, int((top - bottom - 14 * scale) / (16 * scale)))]
    height = min(top - bottom, (len(lines) * 16 + 14) * scale)
    x = min(max(left, panel.bounds[0]), right - width)
    y = min(max(bottom, panel.bounds[3] + 6 * scale), top - height)
    bounds = (x, y, x + width, y + height)
    labels = tuple(
        Label(line, (x + 7 * scale, y + height - (index * 16 + 18) * scale))
        for index, line in enumerate(lines)
    )
    return bounds, labels


def draw_ghost(positions):
    """Gold wires are a bounded UI placement preview, never checked geometry."""
    import gpu

    if not positions:
        return
    with drawing_state():
        gpu.state.line_width_set(1.4)
        _batch(gpu.shader.from_builtin("UNIFORM_COLOR"), "LINES", positions, GOLD)
