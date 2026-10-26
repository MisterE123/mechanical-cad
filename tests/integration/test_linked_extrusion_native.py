"""Linked dialog candidates preserve exact native history and persistence."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature

package_name = "linked_extrusion_test_addon"
package = types.ModuleType(package_name)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package_name] = package
linked = importlib.import_module(package_name + ".linked_extrusion_edit")


@pytest.mark.parametrize(
    "kind, z, length, expected", [("union", 10, "3", 1012), ("cut", 10, "-3", 988)]
)
def test_linked_edit_exact_volume_and_persisted_replay(kind, z, length, expected, tmp_path):
    original = Document(
        "part",
        "Linked tool",
        {"shared_depth": 2 if kind == "union" else -2},
        (
            Feature("p", "sketch_rectangle", "Base profile", {"width": 10, "height": 10}),
            Feature("base", "extrude", "Base", {"length": 10}, {"profile": "p"}),
            Feature(
                "q",
                "sketch_rectangle",
                "Tool profile",
                {"width": 2, "height": 2, "x": 2, "y": 2, "z": z},
            ),
            Feature("tool", "extrude", "Tool", {"length": "shared_depth"}, {"profile": "q"}),
            Feature("result", kind, "Result", {}, {"base": "base", "tool": "tool"}),
        ),
        "result",
    )
    source = json.loads(original.to_json())
    candidate = copy.deepcopy(source)
    candidate["features"][-1]["label"] = "Revised result"
    edited = linked.edit_linked_extrusion(
        source, candidate, "result", tool_id="tool", length=length, profile="q"
    )
    saved = tmp_path / "linked.mcad.json"
    saved.write_text(json.dumps(edited))
    restored = Document.from_json(saved.read_text())
    result = regenerate(restored, OCPKernel())
    assert result.ok, result.result
    assert result.result["features"][-1]["stats"]["volume"] == pytest.approx(expected, abs=1e-9)
    assert result.result["features"][-1]["stats"]["valid"]
    assert edited["parameters"] == source["parameters"]
    assert source["features"][-2]["params"]["length"] == "shared_depth"
    assert restored.active_feature == "result"
    assert len(restored.features) == 5
