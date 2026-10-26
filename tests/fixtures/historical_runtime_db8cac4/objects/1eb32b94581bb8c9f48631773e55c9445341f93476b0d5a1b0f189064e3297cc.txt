"""Stable native palette layout through real general-sketch state transitions.

Run native Blender with --background --python-exit-code 1. Real owners, commands,
sidecar checks and production draw/bounds code are exercised. Small gizmo/context
adapters expose computed positions at controlled viewport sizes and UI scales;
this is headless layout evidence, not a GUI mouse/visual acceptance claim.
"""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_job_ui,
    constraint_ui,
    document_state,
    execution_lease,
    general_session,
    register,
    unregister,
    workspace,
    workspace_ui,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddLine,
    AddRelation,
    PointSeed,
)

checks = []
TOOLS = ("SELECT", "POINTS", "LINE", "CIRCLE", "DIMENSION", "ARC", "REVERSE", "USE_POINT")
FIXED_INDICES = {
    **{action: index for index, action in enumerate(TOOLS)},
    "FINISH": 11,
    "CANCEL": 12,
}


def check(value, message):
    assert value, message
    checks.append(message)


def wait(owner, context):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not owner.error, "Real native sketch check completes")
    check(not execution_lease.is_busy(), "Completed layout-state check releases the native lease")


class Gizmo:
    """Record native draw assignments while retaining actual mathutils matrices."""

    def __init__(self, kind):
        self.kind = kind
        self.matrix_basis = Matrix.Identity(4)
        self.hide = False
        self.hide_select = False
        self.shape = None
        self.icon_value = 0

    def target_set_operator(self, identifier):
        self.target = SimpleNamespace(identifier=identifier)
        return self.target


def group(context):
    result = SimpleNamespace(gizmos=SimpleNamespace(new=Gizmo))
    workspace_ui.MCAD_GGT_workspace_palette.setup(result, context)
    check(result.backdrop.hide_select, "The backdrop is never a selectable gizmo")
    check(
        all(
            gizmo.target.identifier == "mcad.workspace_action" and gizmo.target.action == action
            for action, gizmo in result.buttons.items()
        ),
        "Production setup retains every exact native action target",
    )
    return result


def layout_context(context, scale=1, height=None, width=None):
    region = SimpleNamespace(
        type="WINDOW",
        height=720 * scale if height is None else height,
        width=966 * scale if width is None else width,
        x=103,
        y=47,
    )
    space = SimpleNamespace(show_gizmo=True, show_gizmo_context=True, show_region_toolbar=False)
    return SimpleNamespace(
        area=SimpleNamespace(
            type="VIEW_3D", spaces=SimpleNamespace(active=space), regions=[region]
        ),
        preferences=SimpleNamespace(
            system=SimpleNamespace(ui_scale=scale), themes=context.preferences.themes
        ),
        workspace=context.workspace,
        window=context.window,
        scene=context.scene,
        region=SimpleNamespace(type="UI", width=1, height=1),
    )


def rendered(context, palette, *, native_context=None):
    actions = workspace_ui.palette_actions(context)
    # Layout adapters deliberately change area dimensions; capabilities still
    # inspect the genuine owner and original native context, including pending.
    available = workspace_ui.available
    enabled = {
        action: available(native_context, action) if native_context is not None else True
        for action in actions
    }
    with patch.object(
        workspace_ui, "available", side_effect=lambda _context, action: enabled[action]
    ):
        workspace_ui.MCAD_GGT_workspace_palette.draw_prepare(palette, context)
    bounds = workspace_ui.palette_bounds(context)
    if bounds is None:
        check(palette.backdrop.hide, "Unavailable palette hides the entire backing strip")
        check(
            all(gizmo.hide and gizmo.hide_select for gizmo in palette.buttons.values()),
            "Every invisible gizmo explicitly loses selection when the palette is hidden",
        )
        return None
    check(not palette.backdrop.hide, "A fitting palette draws its backing strip")
    left, bottom, right, top = bounds
    check(
        tuple(palette.backdrop.matrix_basis.translation) == (left, bottom, 0)
        and palette.backdrop.matrix_basis[0][0] == right - left
        and palette.backdrop.matrix_basis[1][1] == top - bottom,
        "Production backing strip matches modal bounds exactly",
    )
    positions = {}
    region = context.area.regions[0]
    for action, gizmo in palette.buttons.items():
        if action not in actions:
            check(
                gizmo.hide and gizmo.hide_select, f"Absent {action} is invisible and unselectable"
            )
            continue
        check(not gizmo.hide, f"Visible {action} retains its reserved slot")
        check(gizmo.hide_select == (not enabled[action]), f"{action} preserves native availability")
        check(
            gizmo.alpha == (1.0 if enabled[action] else 0.28),
            f"{action} preserves disabled contrast",
        )
        positions[action] = tuple(gizmo.matrix_basis.translation)
        x, y, _ = positions[action]
        radius = 17 * context.preferences.system.ui_scale
        check(
            left <= x - radius < x + radius <= right and bottom <= y - radius < y + radius <= top,
            f"{action} native target fits inside bounds",
        )
        check(gizmo.use_tooltip, f"{action} retains its native hover explanation")
        check(
            workspace_ui.is_palette_event(
                context, SimpleNamespace(mouse_x=region.x + x, mouse_y=region.y + y)
            ),
            f"{action} uses region-offset-aware modal passthrough",
        )
    centers = list(positions.values())
    for index, (x, y, _) in enumerate(centers):
        for other_x, other_y, _ in centers[index + 1 :]:
            check(
                (x - other_x) ** 2 + (y - other_y) ** 2
                >= (42 * context.preferences.system.ui_scale) ** 2,
                "Visible native button targets do not overlap",
            )
    for x, y in ((left - 1, bottom), (right + 1, top), (left, bottom - 1), (right, top + 1)):
        check(
            not workspace_ui.is_palette_event(
                context, SimpleNamespace(mouse_x=region.x + x, mouse_y=region.y + y)
            ),
            "A pointer beyond any backing edge is not swallowed by palette passthrough",
        )
    return bounds, positions


def general_layout(context, palette, contextual=(), check_action="SKETCH_CHECK"):
    expected = TOOLS + contextual + (check_action, "FINISH", "CANCEL")
    check(
        workspace_ui.palette_actions(context) == expected,
        "Menu action API stays compact and unchanged",
    )
    slots = workspace_ui.palette_slots(expected)
    check(
        slots
        == TOOLS
        + contextual
        + (None,) * (2 - len(contextual))
        + (check_action, "FINISH", "CANCEL"),
        "General palette always reserves exactly two contextual slots and thirteen total slots",
    )
    for scale in (1, 1.25, 1.5, 2):
        proxy = layout_context(context, scale)
        bounds, positions = rendered(proxy, palette, native_context=context)
        check(
            bounds == (8 * scale, 30 * scale, 62 * scale, 588 * scale),
            "General backing bounds stay fixed at every tested UI scale",
        )
        check(
            (bounds, positions)
            == workspace_ui.palette_layout(expected, 720 * scale, scale, 966 * scale),
            "Production draw and bounds use the same pure layout result",
        )
        for action, index in {**FIXED_INDICES, check_action: 10}.items():
            check(
                positions[action] == (35 * scale, (588 - 27 - index * 42) * scale, 0),
                f"{action} has its fixed screen-space slot at UI scale {scale}",
            )
        for index, action in enumerate(contextual, start=8):
            check(
                positions[action] == (35 * scale, (588 - 27 - index * 42) * scale, 0),
                "Contextual actions use only the two reserved slots",
            )
        # Actual WINDOW width/height choose the layout, not context.region (the
        # header/sidebar adapter above is deliberately tiny) or selection state.
        check(
            workspace_ui.palette_bounds(layout_context(context, scale, 710 * scale, 70 * scale))
            == (8 * scale, 20 * scale, 62 * scale, 578 * scale),
            "Single column retains its exact minimum height and width",
        )
        for height in (710 * scale - 1, 709 * scale, 706 * scale, 600 * scale, 458 * scale):
            compact = layout_context(context, scale, height, 112 * scale)
            compact_bounds, compact_positions = rendered(compact, palette, native_context=context)
            check(
                compact_bounds
                == (8 * scale, height - 438 * scale, 104 * scale, height - 132 * scale),
                "Compact General backing uses fixed seven-row bounds",
            )
            for index, action in enumerate(slots):
                if action is None:
                    continue
                row, column = divmod(index + (1 if index >= 11 else 0), 2)
                check(
                    compact_positions[action]
                    == ((35 + column * 42) * scale, height - (159 + row * 42) * scale, 0),
                    f"{action} retains its reserved compact cell",
                )
            check(
                (compact_bounds, compact_positions)
                == workspace_ui.palette_layout(expected, height, scale, 112 * scale),
                "Compact draw and passthrough use the identical pure layout",
            )
        for height, width in (
            (706 * scale, 112 * scale - 1),
            (710 * scale, 70 * scale - 1),
        ):
            narrow = layout_context(context, scale, height, width)
            check(
                rendered(narrow, palette, native_context=context) is None,
                "A narrow WINDOW region hides all targets instead of clipping controls",
            )
        short = layout_context(context, scale, 458 * scale - 1)
        check(
            rendered(short, palette, native_context=context) is None,
            "A region below the compact minimum consistently uses named actions",
        )
        check(
            workspace_ui.palette_actions(short) == expected,
            "Short-region fallback keeps every named menu action",
        )
        check(
            rendered(proxy, palette, native_context=context) is not None,
            "Returning from compact/hidden layouts restores the original single column",
        )


register()
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
window.workspace[workspace.OWNER_KEY] = workspace.OWNER
window.workspace[workspace.ROLE_KEY] = "SKETCH"
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    document_state._populate_document(
        context.scene,
        dict(
            schema_version=1,
            id="stable_palette",
            name="Stable palette",
            units="mm",
            parameters={},
            features=[],
            active_feature=None,
        ),
    )
    owner = general_session.GeneralSession(context)
    owner.start()
    palette = group(context)
    try:
        general_layout(context, palette)
        first, second, line = owner.execute(
            context, AddLine(PointSeed(2, 3), PointSeed(12, 3))
        ).entity_ids
        check(owner.pending is not None, "Real authored geometry starts a pending check")
        general_layout(context, palette, check_action="CANCEL_CHECK")
        wait(owner, context)
        for targets, contextual in (
            ((("line", line),), ("HORIZONTAL", "VERTICAL")),
            ((("point", first),), ("FIX_HERE", "FIX_ORIGIN")),
            ((("point", first), ("point", second)), ()),
            ((), ()),
        ):
            constraint_ui.select_bindings(owner, targets, context=context)
            general_layout(context, palette, contextual)
        relation = owner.execute(context, AddRelation("horizontal", (line,))).constraint_id
        wait(owner, context)
        constraint_ui.select_bindings(owner, (("constraint", relation),), context=context)
        general_layout(context, palette, ("REMOVE_RELATION",))
        owner.check(context)
        check(owner.pending is not None, "Explicit native recheck keeps the relation selection")
        general_layout(context, palette, ("RECOVER_RELATION",), "CANCEL_CHECK")
        owner.cancel_native("Layout regression cancels its own pending check")
        general_layout(context, palette, ("RECOVER_RELATION",))
        deadline = time.monotonic() + 30
        while execution_lease.is_busy() and time.monotonic() < deadline:
            assembly_job_ui._supervise()
            time.sleep(0.01)
        check(not execution_lease.is_busy(), "Canceled native check finishes process cleanup")
        owner.check(context)
        wait(owner, context)
        general_layout(context, palette, ("REMOVE_RELATION",))
        for flag, value in (
            ("show_gizmo", False),
            ("show_gizmo_context", False),
            ("show_region_toolbar", True),
        ):
            proxy = layout_context(context)
            # Render visible immediately before each hidden transition to catch
            # stale selectable Check/contextual/Footer gizmos.
            rendered(proxy, palette, native_context=context)
            setattr(proxy.area.spaces.active, flag, value)
            check(
                rendered(proxy, palette, native_context=context) is None,
                f"{flag} hides and deselects all palette gizmos",
            )
            check(
                not workspace_ui.is_palette_event(proxy, SimpleNamespace(mouse_x=138, mouse_y=347)),
                "A hidden palette never captures viewport events",
            )
        for mode in ("missing area", "other editor", "missing window region"):
            proxy = layout_context(context)
            if mode == "missing area":
                proxy.area = None
            elif mode == "other editor":
                proxy.area.type = "PROPERTIES"
            else:
                proxy.area.regions = []
            check(
                rendered(proxy, palette, native_context=context) is None,
                f"{mode} safely hides and deselects the palette",
            )
    finally:
        owner.discard()

    # Existing non-general layouts retain every old slot and height, including
    # Rectangle before/after its dimensions become available.
    legacy = (
        ("SKETCH", SimpleNamespace(can_edit_dimensions=False), ("FINISH", "CANCEL")),
        ("SKETCH", SimpleNamespace(can_edit_dimensions=True), ("DIMENSIONS", "FINISH", "CANCEL")),
        ("SKETCH", None, ("NEW", "RECTANGLE", "EDIT")),
        ("PART", None, ("NEW", "EXTRUDE", "CUT", "CHECK", "EXPORT")),
        (
            "ASSEMBLY",
            None,
            (
                "ASSEMBLY_NEW",
                "ASSEMBLY_INSERT",
                "ASSEMBLY_FRAME",
                "ASSEMBLY_JOINT",
                "ASSEMBLY_CHECK",
                "ASSEMBLY_SAMPLE",
            ),
        ),
        (None, None, ()),
    )
    for role, draft, expected in legacy:
        with (
            patch.object(workspace, "get_role", return_value=role),
            patch.object(workspace, "active_draft", return_value=draft),
        ):
            check(
                workspace_ui.palette_actions(context) == expected,
                "Legacy palette actions are unchanged",
            )
            check(
                workspace_ui.palette_slots(expected) == expected,
                "Legacy layouts introduce no spacer slots",
            )
            for scale in (1, 2):
                proxy = layout_context(context, scale)
                result = rendered(proxy, palette)
                if not expected:
                    check(result is None, "An empty palette creates no selectable gizmos")
                    continue
                bounds, positions = result
                check(
                    bounds
                    == (
                        8 * scale,
                        (588 - len(expected) * 42 - 12) * scale,
                        62 * scale,
                        588 * scale,
                    ),
                    "Legacy backing height is unchanged",
                )
                check(
                    all(
                        positions[action] == (35 * scale, (588 - 27 - index * 42) * scale, 0)
                        for index, action in enumerate(expected)
                    ),
                    "Legacy button positions are unchanged",
                )

unregister()
check(
    "OCP" not in sys.modules and "slvs" not in sys.modules,
    "Layout tests load no native CAD kernel in Blender",
)
print("PALETTE_POSITIONS_SMOKE_OK", len(checks), bpy.app.version_string)
