"""Readable current dependencies, not guessed parameter intent."""

import importlib.util
from pathlib import Path

path = (
    Path(__file__).resolve().parents[2]
    / "blender_addon/mechanical_cad_blender/parameter_presentation.py"
)
spec = importlib.util.spec_from_file_location("parameter_presentation", path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def test_exact_and_formula_uses_are_explained():
    document = {
        "parameters": {"wall": 2, "outer": "wall * 3"},
        "features": [
            {
                "id": "plate",
                "label": "Plate",
                "params": {"length": "2 * wall"},
                "sketch": {"constraints": [{"id": "width", "value": "wall + 8"}]},
            },
            {"id": "other", "params": {"length": "wall_extra"}},
        ],
    }
    assert helper.parameter_usage(document, "wall") == (
        "Parameter: outer",
        "Plate: length",
        "Plate: width",
    )


def test_unlinked_parameter_is_not_presented_as_driving():
    document = {
        "parameters": {"depth": 10},
        "features": [{"id": "pad", "params": {"length": "12"}}],
    }
    assert helper.parameter_usage(document, "depth") == ()


def test_no_evaluation_of_expression():
    assert (
        helper.parameter_usage({"features": [{"params": {"length": "bad syntax !"}}]}, "bad") == ()
    )
