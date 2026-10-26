"""Native-free recipe edits, conservative grouping and no mutation on rejection."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

package = types.ModuleType("hole_test_addon")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
recipe = importlib.import_module(package.__name__ + ".hole_recipe")
ROOT = "hole_" + "a" * 32


def source():
    return {
        "schema_version": 1,
        "id": "part",
        "name": "Plate",
        "units": "mm",
        "parameters": {},
        "features": [
            {
                "id": "profile",
                "kind": "sketch_rectangle",
                "label": "Plate",
                "params": {"width": 40, "height": 30},
                "inputs": {},
            },
            {
                "id": "pad",
                "kind": "extrude",
                "label": "Pad",
                "params": {"length": 20},
                "inputs": {"profile": "profile"},
            },
        ],
        "active_feature": "pad",
    }


def make(document=None, **kwargs):
    values = dict(base="pad", face="pad/face/cap.end", diameter="5", depth="12")
    values.update(kwargs)
    return recipe.hole_candidate(source() if document is None else document, ROOT, **values)


@pytest.mark.parametrize("counterbore", [False, True])
def test_roundtrip_edit_preserves_source_and_active_output(counterbore):
    original = source()
    before = copy.deepcopy(original)
    doc = make(original, counterbore=counterbore, diameter="0.2 in", x="1 cm")
    assert original == before
    values = recipe.inspect_hole(doc, ROOT)
    assert values["diameter"] == pytest.approx(5.08)
    assert values["x"] == 10
    doc["active_feature"] = "pad"
    before = copy.deepcopy(doc)
    changed = make(doc, counterbore=counterbore, diameter=6, editing=True)
    assert changed["active_feature"] == "pad"
    assert doc == before
    assert recipe.inspect_hole(changed, ROOT)["diameter"] == 6


@pytest.mark.parametrize(
    "changes",
    [
        {"diameter": 0},
        {"depth": -1},
        {"depth": "nan"},
        {"diameter": "size"},
        {"x": 1e7},
        {"face": "NONE"},
        {"counterbore": True, "counter_diameter": 4},
        {"counterbore": True, "counter_depth": 12},
        {"counterbore": True, "counter_depth": 0},
    ],
)
def test_rejections_leave_document_unchanged(changes):
    document = make()
    before = copy.deepcopy(document)
    with pytest.raises(ValueError):
        make(document, editing=True, **changes)
    assert document == before


def test_shared_intermediate_and_changed_recipe_refuse_group_edit():
    document = make(counterbore=True)
    document["features"].append(
        {
            "id": "shared",
            "kind": "cut",
            "params": {},
            "inputs": {"base": "pad", "tool": ROOT + "_tool"},
        }
    )
    assert recipe.inspect_hole(document, ROOT) is None
    with pytest.raises(ValueError, match="shared"):
        make(document, counterbore=True, editing=True)
    document = make()
    document["features"][-2]["params"]["length"] = 12
    assert recipe.inspect_hole(document, ROOT) is None


def test_downstream_final_consumer_is_allowed_but_unknown_extra_fields_are_not():
    document = make()
    document["features"].append(
        {"id": "downstream", "kind": "transform", "params": {}, "inputs": {"base": ROOT}}
    )
    assert recipe.inspect_hole(document, ROOT)
    document["features"][-3]["unsupported"] = True
    assert recipe.inspect_hole(document, ROOT) is None
