"""Pure visual-joint layout/hit contracts; no claim of native GPU or mouse QA."""

import importlib
import math
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_joint_overlay_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
overlay = importlib.import_module(PACKAGE + ".assembly_joint_overlay")


def center(bounds):
    return ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)


def contained(inner, outer):
    return (
        outer[0] <= inner[0] <= inner[2] <= outer[2]
        and outer[1] <= inner[1] <= inner[3] <= outer[3]
    )


@pytest.mark.parametrize("scale", [0.75, 1, 1.25, 1.5, 2, 3])
def test_default_viewport_shared_draw_hit_bounds(scale):
    safe = (50, 12, 672, 645)  # 966x706 default window with sidebar and native toolbars.
    panel = overlay.build_panel(
        safe,
        scale=scale,
        parent_name="Base",
        child_name="Sector",
        replaced_name="Existing slider",
        ready=True,
    )
    assert contained(panel.bounds, safe)
    assert panel.scale >= 1.0
    assert any("Preview not checked" in label.text for label in panel.labels)
    assert any("Replaces: Existing slider" in label.text for label in panel.labels)
    for button in panel.buttons:
        assert contained(button.bounds, panel.bounds)
        assert button.bounds[3] - button.bounds[1] >= 24
        assert overlay.hit_button(panel, center(button.bounds)) == button
        assert button.hint
    assert all(overlay.inside(label.position, panel.bounds) for label in panel.labels)


@pytest.mark.parametrize(
    "safe",
    [(0, 0, 180, 150), (0, 0, 250, 100), (0, 0, 100, 64), (0, 0, 301, 400), (0, 0, 400, 329)],
)
def test_small_viewport_keeps_cancel_without_shrinking_all_controls(safe):
    panel = overlay.build_panel(safe, scale=1.5, ready=True)
    assert contained(panel.bounds, safe)
    assert panel.scale >= 1.0
    assert [button.action for button in panel.buttons] == ["cancel"]
    assert panel.buttons[0].bounds[3] - panel.buttons[0].bounds[1] >= 24
    assert contained(panel.buttons[0].bounds, safe)


def test_names_remain_accessible_through_bounded_hover():
    names = ["P" * 128, "C" * 128, "J" * 128]
    safe = (20, 20, 660, 640)
    panel = overlay.build_panel(
        safe, parent_name=names[0], child_name=names[1], replaced_name=names[2], ready=True
    )
    for prefix, name in zip(("Parent:", "Child:", "Replaces:"), names, strict=True):
        label = next(label for label in panel.labels if label.text.startswith(prefix))
        hint = overlay.hint_at(panel, label.position)
        assert name in hint
        bounds, labels = overlay.tooltip_layout(hint, panel, safe)
        assert contained(bounds, safe)
        assert all(overlay.inside(label.position, bounds) for label in labels)
        assert name in "".join(label.text for label in labels)


def test_slider_field_is_wide_and_pending_text_blocks_apply():
    panel = overlay.build_panel((0, 0, 966, 706), kind="slider", ready=True, field="-120.125|")
    buttons = {button.action: button for button in panel.buttons}
    assert buttons["distance"].enabled
    assert buttons["distance"].bounds[2] - buttons["distance"].bounds[0] > 160
    assert not buttons["apply"].enabled
    assert buttons["cancel"].enabled


def test_only_cancel_available_before_picks():
    panel = overlay.build_panel((0, 0, 966, 706))
    assert [button.action for button in panel.buttons if button.enabled] == ["cancel"]


def test_coincident_handles_prefer_explicit_active_connector():
    parent = overlay.Handle("parent", "X", (0, 0), (100, 0), False)
    child = overlay.Handle("child", "X", (0, 0), (100, 0), True)
    assert overlay.pick_handle((parent, child), (60, 3)) == child
    assert overlay.pick_handle((parent, child), (60, 20)) is None
    assert overlay.segment_distance((1, 1), (0, 0), (0, 0)) == pytest.approx(math.sqrt(2))


@pytest.mark.parametrize(
    "rect,scale", [((0, 0, 0, 1), 1), ((0, 0, math.nan, 2), 1), ((0, 0, 5, 5), math.inf)]
)
def test_nonfinite_or_empty_layout_rejected(rect, scale):
    with pytest.raises(ValueError):
        overlay.build_panel(rect, scale=scale)


def test_revolute_degrees_and_literal_surface_disclosure():
    panel = overlay.build_panel(
        (0, 0, 966, 706), kind="revolute", distance=90, ready=True, connector_xyz=[1, 2, 3]
    )
    buttons = {button.action: button for button in panel.buttons}
    assert buttons["distance"].label == "Angle: 90 °"
    assert buttons["revolute"].selected and buttons["surface"].enabled
    assert "NOT a persistent face attachment" in buttons["surface"].hint
    assert any(label.text == "Local XYZ: 1, 2, 3 mm" for label in panel.labels)


def test_isolated_target_is_named_and_switching_controls_fit():
    panel = overlay.build_panel(
        (0, 0, 966, 706),
        mate_faces=True,
        target_name="Child copy",
        target_role="child",
        target_switch=True,
    )
    assert any(label.text == "Child: Child copy (isolated)" for label in panel.labels)
    buttons = {button.action: button for button in panel.buttons}
    assert buttons["target_prev"].enabled and buttons["target_next"].enabled
    for button in panel.buttons:
        assert overlay.inside(button.bounds[:2], panel.bounds)
        assert overlay.inside(button.bounds[2:], panel.bounds)


@pytest.mark.parametrize("scale", [1, 1.5, 2, 3])
@pytest.mark.parametrize("ready", [False, True])
def test_motion_only_panel_controls_cancel_and_exact_ready_apply(scale, ready):
    bounds = (10, 20, 1210, 1020)
    panel = overlay.build_motion_panel(
        bounds,
        scale=scale,
        name="Input shaft",
        angle=15,
        ready=ready,
        status="Pending · accepted display retained",
        error="Derived follower limit would be exceeded.",
    )
    actions = {button.action: button for button in panel.buttons}
    assert set(actions) == {"minus", "distance", "plus", "apply", "cancel"}
    assert actions["apply"].enabled is ready
    assert actions["cancel"].enabled
    for button in panel.buttons:
        assert contained(button.bounds, panel.bounds)
        assert overlay.hit_button(panel, center(button.bounds)) is button
    assert contained(panel.bounds, bounds)
    assert any("followers read-only" in label.text for label in panel.labels)


def test_compact_motion_panel_keeps_cancel_reachable():
    panel = overlay.build_motion_panel((4, 8, 204, 140))
    assert [button.action for button in panel.buttons] == ["cancel"]
    assert contained(panel.buttons[0].bounds, panel.bounds)


@pytest.mark.parametrize("ready", [False, True])
def test_slider_motion_panel_uses_mm_not_angles_and_no_connector_controls(ready):
    panel = overlay.build_motion_panel(
        (0, 0, 1200, 1000), kind="slider", distance=12.5, angle=999, ready=ready,
    )
    actions = {button.action: button for button in panel.buttons}
    assert set(actions) == {"minus", "distance", "plus", "apply", "cancel"}
    assert actions["minus"].label == "−1 mm" and actions["plus"].label == "+1 mm"
    assert actions["distance"].label == "12.5 mm"
    assert actions["minus"].bounds[2] - actions["minus"].bounds[0] == 64
    assert actions["plus"].bounds[2] - actions["plus"].bounds[0] == 64
    assert actions["distance"].bounds[2] - actions["distance"].bounds[0] >= 140
    assert actions["apply"].enabled is ready and actions["cancel"].enabled
    texts = [label.text for label in panel.labels] + [button.label for button in panel.buttons]
    assert any("Slide along mate +Z (mm)" in text for text in texts)
    assert not any("angle" in text.lower() or "degrees" in text or "°" in text or "999" in text for text in texts)
    assert all(contained(button.bounds, panel.bounds) for button in panel.buttons)
