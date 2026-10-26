"""Viewport-only presentation for explicit projection edge choices."""

import textwrap

import blf
import gpu
from gpu_extras.batch import batch_for_shader

from .projection_edge_choice_labels import choice_labels


def prepare_layout(picker):
    compact = choice_labels(picker.edge_choice.rows, picker.base)
    # Size to the actual labels, not the full viewport. Long distinguishing
    # identities still wrap in full; no ellipsis or hidden candidate truncation.
    longest = max(len(line) for pair in compact for line in pair)
    width = min(max(336, longest * 9 + 40), 480, picker.region.width - 64)
    if width < 336:
        raise ValueError("Enlarge the 3D view to show every edge choice.")
    top = picker.region.height - 80
    rows, labels = [], []
    for i, pair in enumerate(compact):
        lines = [f"{i + 1}. {pair[0]}", pair[1]]
        wrapped = tuple(part for line in lines for part in
                        textwrap.wrap(line, max(24, int((width - 24) / 9))))
        height = 18 * len(wrapped) + 12
        rows.append((24, top - height, 24 + width, top))
        labels.append(wrapped)
        top -= height
    bottom = top - 40
    if bottom < 24:
        raise ValueError("Enlarge the 3D view or zoom/orbit to show fewer edge choices.")
    return (rows, (24, bottom, 180, bottom + 32),
            (195, bottom, 350, bottom + 32), labels)


def draw_choice(picker):
    choice = picker.edge_choice
    rows, apply, cancel, labels = picker.choice_panel
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    old_blend = gpu.state.blend_get()
    gpu.state.blend_set("ALPHA")

    def box(bounds, color):
        x1, y1, x2, y2 = bounds
        shader.bind()
        shader.uniform_float("color", color)
        batch_for_shader(shader, "TRIS", {"pos": [(x1, y1), (x2, y1), (x2, y2),
                                                  (x1, y1), (x2, y2), (x1, y2)]}).draw(shader)

    def text(x, y, value, size=14, secondary=False):
        blf.size(0, size)
        blf.color(0, *((0.76, 0.82, 0.86, 1) if secondary else (1, 1, 1, 1)))
        blf.position(0, x, y, 0)
        blf.draw(0, value)

    try:
        box((16, cancel[1] - 8, rows[0][2] + 8, rows[0][3] + 42), (0.035, 0.045, 0.055, 0.97))
        text(32, rows[0][3] + 24, "Choose Edge", 15)
        text(32, rows[0][3] + 6, "Select to preview, then Apply", 12)
        for i, (lines, bounds) in enumerate(zip(labels, rows, strict=True)):
            box(bounds, (0.05, 0.34, 0.48, 1) if i == choice.selected else (0.12, 0.14, 0.16, 1))
            for line, label in enumerate(lines):
                text(32, bounds[3] - 18 - 18 * line, label, 12, secondary=line > 0)
        box(apply, (0.05, 0.35, 0.48, 1) if choice.selected is not None else (0.16, 0.17, 0.18, 1))
        box(cancel, (0.16, 0.17, 0.18, 1))
        text(apply[0] + 12, apply[1] + 10, "Apply · Enter")
        text(cancel[0] + 12, cancel[1] + 10, "Cancel · Esc")
    finally:
        gpu.state.blend_set(old_blend)
