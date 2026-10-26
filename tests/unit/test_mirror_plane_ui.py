"""Plane controls classify without evaluating or rewriting saved intent."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

path = (
    Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender/mirror_plane_ui.py"
)
spec = importlib.util.spec_from_file_location("mirror_plane_ui_test", path)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


def operator(normal=("0", "0", "1")):
    return SimpleNamespace(
        kind="mirror",
        axis_x=normal[0],
        axis_y=normal[1],
        axis_z=normal[2],
        x="along_x",
        y="along_y",
        z="height + 2",
        mirror_plane="CUSTOM",
        mirror_initializing=False,
    )


@pytest.mark.parametrize(
    "normal,parameters,mode",
    [
        (("0", "0", "1"), {}, "XY"),
        (("0", "-2", "0"), {}, "XZ"),
        (("4", "0", "0"), {}, "YZ"),
        (("nx", "ny", "nz"), {"nx": 0, "ny": "0", "nz": "1"}, "XY"),
        (("nx", "0", "1"), {"nx": "a - a"}, "CUSTOM"),
        (("0", "0", "0"), {}, "CUSTOM"),
        (("1", "1", "0"), {}, "CUSTOM"),
        (("nan", "0", "1"), {}, "CUSTOM"),
    ],
)
def test_initialize_preserves_all_authored_values(normal, parameters, mode):
    op = operator(normal)
    before = {key: getattr(op, key) for key in ("axis_x", "axis_y", "axis_z", "x", "y", "z")}
    ui.initialize(op, parameters)
    assert op.mirror_plane == mode and not op.mirror_initializing
    assert {key: getattr(op, key) for key in before} == before


@pytest.mark.parametrize("mode", ["XY", "XZ", "YZ", "CUSTOM"])
def test_explicit_selection_changes_only_normal(mode):
    op = operator(("nx", "ny", "nz"))
    op.mirror_plane = mode
    ui.changed(op, None)
    assert (op.x, op.y, op.z) == ("along_x", "along_y", "height + 2")
    assert (op.axis_x, op.axis_y, op.axis_z) == (
        ui.PRESETS[mode][0] if mode != "CUSTOM" else ("nx", "ny", "nz")
    )


def test_initialization_callback_guard():
    op = operator(("nx", "ny", "nz"))
    op.mirror_initializing, op.mirror_plane = True, "XY"
    ui.changed(op, None)
    assert (op.axis_x, op.axis_y, op.axis_z) == ("nx", "ny", "nz")
