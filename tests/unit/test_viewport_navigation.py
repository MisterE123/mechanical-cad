"""Native navigation UI is reserved dynamically, without selecting faces below it."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

spec = importlib.util.spec_from_file_location(
    "viewport_navigation",
    Path(__file__).parents[2] / "blender_addon/mechanical_cad_blender/viewport_navigation.py",
)
nav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nav)


def context(*, scale=1, x=100, y=200, sidebar=0):
    region = NS(type="WINDOW", x=x, y=y, width=1000, height=800, alignment="NONE")
    regions = [region]
    if sidebar:
        regions.append(
            NS(type="UI", alignment="RIGHT", x=x + 1000 - sidebar, y=y, width=sidebar, height=800)
        )
    return NS(
        area=NS(spaces=NS(active=NS(show_gizmo=True, show_gizmo_navigate=True)), regions=regions),
        preferences=NS(
            system=NS(ui_scale=scale),
            view=NS(
                mini_axis_type="GIZMO",
                show_navigate_ui=True,
                gizmo_size_navigate_v3d=80,
                mini_axis_size=25,
            ),
        ),
    ), region


@pytest.mark.parametrize("flag", ["show_gizmo", "show_gizmo_navigate"])
def test_hidden_gizmos_reserve_no_viewport_space(flag):
    c, r = context()
    setattr(c.area.spaces.active, flag, False)
    assert nav.navigation_bounds(c, r) is None
    assert not nav.is_navigation_event(c, r, NS(mouse_x=1090, mouse_y=990))


def test_hidden_axis_and_buttons_reserve_nothing():
    c, r = context()
    c.preferences.view.mini_axis_type = "NONE"
    c.preferences.view.show_navigate_ui = False
    assert nav.navigation_bounds(c, r) is None


@pytest.mark.parametrize("scale", [0.75, 1, 1.5, 2])
def test_scale_sidebar_and_region_origin(scale):
    c, r = context(scale=scale, x=300, y=400, sidebar=240)
    left, bottom, right, top = nav.navigation_bounds(c, r)
    assert (right, top) == (1060, 1200)
    assert right - left == pytest.approx(100 * scale)
    assert top - bottom == pytest.approx(244 * scale)
    assert nav.is_navigation_event(c, r, NS(mouse_x=right - 50 * scale, mouse_y=top - 50 * scale))
    assert not nav.is_navigation_event(c, r, NS(mouse_x=left - 1, mouse_y=top - 50 * scale))


def test_overlaid_top_header_and_hidden_sidebar():
    c, r = context(sidebar=1)
    c.area.regions.append(
        NS(type="TOOL_HEADER", alignment="TOP", x=100, y=970, width=1000, height=30)
    )
    assert nav.navigation_bounds(c, r)[2:] == (1100, 970)


def test_axis_only_does_not_reserve_button_column():
    c, r = context()
    c.preferences.view.show_navigate_ui = False
    assert nav.navigation_bounds(c, r) == (1000, 900, 1100, 1000)


def test_drag_stays_passthrough_outside_then_releases():
    c, r = context()
    retained = ["cap.start", "cap.end"]
    picker = NS(
        region=r,
        area=NS(tag_redraw=lambda: None),
        hit=("b", "face"),
        points=[1],
        selected_points=retained,
    )
    for kind, value, x, y in [
        ("LEFTMOUSE", "PRESS", 1050, 950),
        ("MOUSEMOVE", "NOTHING", 500, 500),
        ("LEFTMOUSE", "RELEASE", 500, 500),
    ]:
        assert nav.navigation_passthrough(
            picker, c, NS(type=kind, value=value, mouse_x=x, mouse_y=y)
        )
        assert picker.selected_points is retained and not picker.points and picker.hit is None
    assert not picker.navigation_drag
    assert not nav.navigation_passthrough(
        picker, c, NS(type="LEFTMOUSE", value="PRESS", mouse_x=500, mouse_y=500)
    )


def test_native_consumed_release_cannot_latch_next_geometry_click():
    c, r = context()
    picker = NS(region=r, area=NS(tag_redraw=lambda: None), navigation_drag=True)
    assert not nav.navigation_passthrough(
        picker, c, NS(type="LEFTMOUSE", value="PRESS", mouse_x=500, mouse_y=500)
    )
    assert not picker.navigation_drag
