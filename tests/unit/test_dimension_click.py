"""Native-independent event sequence contract for direct annotation editing."""

import importlib.util
from pathlib import Path

PATH = Path(__file__).parents[2] / "blender_addon/mechanical_cad_blender/dimension_click.py"
spec = importlib.util.spec_from_file_location("dimension_click_test", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
DimensionClick = module.DimensionClick


def first_click(tracker):
    assert not tracker.press("radius", (100, 100), 1)
    tracker.release((100, 100))


def test_press_release_press_opens_exactly_once():
    tracker = DimensionClick()
    first_click(tracker)
    assert tracker.press("radius", (101, 102), 1.2)
    tracker.release((101, 102))
    assert not tracker.press("radius", (101, 102), 1.3)


def test_press_without_release_is_not_a_double_click():
    tracker = DimensionClick()
    assert not tracker.press("radius", (100, 100), 1)
    assert not tracker.press("radius", (100, 100), 1.1)


def test_drag_returning_to_label_is_not_double_click():
    tracker = DimensionClick()
    assert not tracker.press("radius", (100, 100), 1)
    tracker.move((120, 100))
    tracker.move((100, 100))
    tracker.release((100, 100))
    assert not tracker.press("radius", (100, 100), 1.2)


def test_time_distance_identity_and_clock_bounds():
    for name, point, stamp in (
        ("different", (100, 100), 1.2),
        ("radius", (105, 100), 1.2),
        ("radius", (100, 100), 1.36),
        ("radius", (100, 100), 0.9),
    ):
        tracker = DimensionClick()
        first_click(tracker)
        assert not tracker.press(name, point, stamp)


def test_navigation_reset_prevents_accidental_open():
    tracker = DimensionClick()
    first_click(tracker)
    tracker.reset()
    assert not tracker.press("radius", (100, 100), 1.2)


def test_moving_away_between_clicks_prevents_open():
    tracker = DimensionClick()
    first_click(tracker)
    tracker.move((150, 100))
    assert not tracker.press("radius", (100, 100), 1.2)


def test_native_double_click_also_opens_and_clears_history():
    tracker = DimensionClick()
    assert tracker.press("radius", (100, 100), 1.2, native_double=True)
    tracker.release((100, 100))
    assert not tracker.press("radius", (100, 100), 1.3)
