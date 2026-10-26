"""History edits preserve source snapshots and precise untouched values."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

path = (
    Path(__file__).resolve().parents[2]
    / "blender_addon/mechanical_cad_blender/solid_feature_edit.py"
)
package = types.ModuleType("solid_feature_edit_test")
package.__path__ = [str(path.parent)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location(package.__name__ + ".solid_feature_edit", path)
edit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edit)


def test_edit_retains_identity_final_output_and_untouched_numeric_types():
    document = {
        "features": [
            {
                "id": "a",
                "kind": "extrude",
                "label": "Old",
                "params": {"length": 1.23456789012345},
                "inputs": {"profile": "p"},
            }
        ],
        "active_feature": "final",
    }
    candidate = edit.edit_feature(
        document,
        "a",
        label="Revised",
        params={"length": "1.23456789012345"},
        inputs={"profile": "p"},
    )
    assert candidate["features"][0]["id"] == "a"
    assert candidate["features"][0]["params"]["length"] == 1.23456789012345
    assert isinstance(candidate["features"][0]["params"]["length"], float)
    assert candidate["active_feature"] == "final"
    assert document["features"][0]["label"] == "Old"


def test_edit_changes_formula_and_input_without_mutating_original():
    document = {
        "features": [
            {
                "id": "a",
                "kind": "extrude",
                "label": "Old",
                "params": {"length": 10},
                "inputs": {"profile": "p"},
            }
        ],
        "active_feature": "a",
    }
    candidate = edit.edit_feature(
        document, "a", label="Longer", params={"length": "thickness * 2"}, inputs={"profile": "q"}
    )
    assert candidate["features"][0]["params"]["length"] == "thickness * 2"
    assert document["features"][0]["inputs"]["profile"] == "p"
    with pytest.raises(ValueError):
        edit.edit_feature(document, "a", label="Bad", params={}, inputs={"profile": "q"})
