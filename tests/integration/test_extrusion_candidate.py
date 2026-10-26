"""One-action extrusion candidates keep editable history and exact solid behavior."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature

PACKAGE = "extrusion_candidate_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package
build = importlib.import_module(PACKAGE + ".extrusion_candidate").extrusion_candidate


def source():
    return Document(
        "part",
        "Part",
        {"depth": 5},
        (
            Feature("base_profile", "sketch_rectangle", "Base", {"width": 10, "height": 10}),
            Feature("base", "extrude", "Base", {"length": 10}, {"profile": "base_profile"}),
            Feature("profile", "sketch_rectangle", "Profile", {"width": 4, "height": 4, "z": 10}),
        ),
        "base",
    ).to_dict()


def nodes(kind="cut", depth="-depth"):
    return (
        Feature("tool", "extrude", "Depth", {"length": depth}, {"profile": "profile"}).to_dict(),
        Feature("result", kind, "Result", {}, {"base": "base", "tool": "tool"}).to_dict(),
    )


@pytest.mark.parametrize("kind,depth,volume", [("cut", "-depth", 920), ("union", "depth", 1080)])
def test_exact_add_remove_and_upstream_parameter_edit(kind, depth, volume):
    original = source()
    before = copy.deepcopy(original)
    tool, boolean = nodes(kind, depth)
    candidate = build(original, tool, boolean)
    assert original == before and tool["params"]["length"] == depth
    assert candidate["active_feature"] == "result"
    assert candidate["features"][-2]["params"]["length"] == "tool_length"
    assert candidate["parameters"]["tool_length"] == depth
    doc = Document.from_json(Document.from_dict(candidate).to_json())
    result = regenerate(doc, OCPKernel())
    assert result.ok, result.result
    stats = result.result["features"][-1]["stats"]
    assert stats["valid"] and stats["solids"] == 1
    assert stats["volume"] == pytest.approx(volume)
    candidate["parameters"]["depth"] = 2
    revised = regenerate(Document.from_dict(candidate), OCPKernel())
    assert revised.ok, revised.result
    assert revised.result["features"][-1]["stats"]["volume"] == pytest.approx(
        1000 + (32 if kind == "union" else -32)
    )


@pytest.mark.parametrize("mutation", ["profile", "base", "tool", "id", "parameter", "empty"])
def test_invalid_candidate_does_not_mutate_source_or_feature_arguments(mutation):
    original = source()
    tool, boolean = nodes()
    if mutation == "profile":
        tool["inputs"]["profile"] = "missing"
    elif mutation == "base":
        boolean["inputs"]["base"] = "profile"
    elif mutation == "tool":
        boolean["inputs"]["tool"] = "base"
    elif mutation == "id":
        tool["id"] = "base"
    elif mutation == "parameter":
        original["parameters"]["tool_length"] = 9
    else:
        tool["params"]["length"] = " "
    before = copy.deepcopy((original, tool, boolean))
    with pytest.raises(ValueError):
        build(original, tool, boolean)
    assert (original, tool, boolean) == before


def test_failed_native_extrusion_retains_original_history():
    original = source()
    before = copy.deepcopy(original)
    candidate = build(original, *nodes("union", "0"))
    result = regenerate(Document.from_dict(candidate), OCPKernel())
    assert not result.ok
    assert original == before and len(original["features"]) == 3
    assert result.result["features"][-1]["status"] == "blocked"
