"""Exact linked edit binding, shared intent and parameter preservation."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

package_name = "linked_extrusion_test_addon"
package = types.ModuleType(package_name)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package_name] = package
linked = importlib.import_module(package_name + ".linked_extrusion_edit")


def document():
    return {
        "parameters": {"depth": -2},
        "features": [
            {
                "id": "tool",
                "kind": "extrude",
                "label": "Pocket depth",
                "params": {"length": "depth"},
                "inputs": {"profile": "p"},
            },
            {
                "id": "cut",
                "kind": "cut",
                "label": "Pocket",
                "params": {},
                "inputs": {"base": "base", "tool": "tool"},
            },
        ],
        "active_feature": "cut",
    }


def edit(source, **kwargs):
    options = dict(tool_id="tool", length="-3", profile="p")
    options.update(kwargs)
    return linked.edit_linked_extrusion(source, copy.deepcopy(source), "cut", **options)


def test_replaces_tool_expression_not_shared_parameter():
    source = document()
    result = edit(source)
    assert result["parameters"] == source["parameters"] == {"depth": -2}
    assert result["features"][0]["params"] == {"length": "-3"}
    assert source["features"][0]["params"] == {"length": "depth"}
    assert result["features"][1] == source["features"][1]
    assert result["active_feature"] == "cut"


def test_unchanged_numeric_depth_keeps_exact_type():
    source = document()
    source["features"][0]["params"]["length"] = -2.123456789012345
    result = edit(source, length="-2.123456789012345")
    assert result == source
    assert isinstance(result["features"][0]["params"]["length"], float)


def test_shared_tool_requires_opt_in_even_for_profile_change():
    source = document()
    source["features"].append(
        {"id": "copy", "kind": "transform", "label": "Other branch", "inputs": {"base": "tool"}}
    )
    with pytest.raises(ValueError, match="Other branch.*copy"):
        edit(source)
    with pytest.raises(ValueError, match="explicitly allow"):
        edit(source, length="depth", profile="q")
    assert edit(source, length="depth") == source
    result = edit(source, allow_shared=True)
    assert result["features"][0]["params"]["length"] == "-3"


def test_wrong_or_changed_tool_binding_rejects_without_mutation():
    source = document()
    with pytest.raises(ValueError, match="reopen"):
        edit(source, tool_id="another")
    candidate = copy.deepcopy(source)
    candidate["features"][1]["inputs"]["tool"] = "another"
    with pytest.raises(ValueError, match="Tool changed"):
        linked.edit_linked_extrusion(
            source, candidate, "cut", tool_id="tool", length="-3", profile="p"
        )
    assert source["features"][0]["params"]["length"] == "depth"
    assert candidate["features"][0]["params"]["length"] == "depth"


def test_unsupported_boolean_does_not_guess_tool():
    source = document()
    source["features"][1]["kind"] = "intersection"
    assert linked.linked_extrusion(source, "cut") is None


def test_switch_blind_to_through_and_back_preserves_ids_and_parameters():
    source = document()
    through = edit(source, end_condition="THROUGH_ALL", direction="-1")
    tool = through["features"][0]
    assert tool["kind"] == "extrude_through"
    assert tool["params"] == {"direction": -1}
    assert tool["inputs"] == {"profile": "p", "base": "base"}
    assert through["parameters"] == source["parameters"]
    assert linked.linked_extrusion(through, "cut")[0] == tool
    assert edit(through) == through
    blind = edit(through, end_condition="BLIND", length="depth")
    assert blind == source


def test_through_retarget_changes_explicit_dependency():
    source = edit(document(), end_condition="THROUGH_ALL", direction="-1")
    candidate = copy.deepcopy(source)
    candidate["features"][1]["inputs"]["base"] = "new_base"
    revised = linked.edit_linked_extrusion(
        source, candidate, "cut", tool_id="tool", length="", profile="p"
    )
    assert revised["features"][0]["inputs"]["base"] == "new_base"
    assert source["features"][0]["inputs"]["base"] == "base"


def test_switch_blind_symmetric_preserves_identity_and_depth_expression():
    source = document()
    symmetric = edit(source, end_condition="SYMMETRIC", length="total")
    assert symmetric["features"][0]["kind"] == "extrude_symmetric"
    assert symmetric["features"][0]["id"] == "tool"
    assert symmetric["features"][0]["params"] == {"length": "total"}
    assert symmetric["features"][0]["inputs"] == {"profile": "p"}
    assert linked.linked_extrusion(symmetric, "cut")[0] == symmetric["features"][0]
    assert edit(symmetric, length="total") == symmetric


def test_up_to_face_switch_preserves_exact_identity_offset_and_noop():
    source = document()
    candidate = edit(
        source,
        end_condition="UP_TO_FACE",
        target="stop",
        end_face="stop/face/cap.end",
        direction=-1,
        offset="gap",
    )
    tool = candidate["features"][0]
    assert tool["id"] == "tool" and tool["kind"] == "extrude_to_face"
    assert tool["inputs"] == {"profile": "p", "target": "stop"}
    assert tool["params"] == {"direction": -1, "offset": "gap"}
    assert tool["end_face"] == "stop/face/cap.end"
    assert edit(candidate) == candidate
    assert edit(candidate, end_condition="BLIND", length="depth") == source
    through = edit(candidate, end_condition="THROUGH_ALL")
    assert "end_face" not in through["features"][0]
    assert through["features"][0]["inputs"] == {"profile": "p", "base": "base"}
    assert candidate["parameters"] == source["parameters"]


def test_up_to_face_shared_target_or_face_edit_needs_explicit_consent():
    source = edit(
        document(),
        end_condition="UP_TO_FACE",
        target="stop",
        end_face="stop/face/cap.end",
        direction=-1,
    )
    source["features"].append(
        {"id": "copy", "kind": "transform", "label": "Other", "inputs": {"base": "tool"}}
    )
    with pytest.raises(ValueError, match="explicitly allow shared"):
        edit(source, target="other")
    with pytest.raises(ValueError, match="explicitly allow shared"):
        edit(source, end_face="stop/face/cap.start")
    result = edit(source, target="other", allow_shared=True)
    assert result["features"][0]["inputs"]["target"] == "other"
    assert source["features"][0]["inputs"]["target"] == "stop"


def test_up_to_face_noop_retains_literal_direction_and_offset_types():
    source = edit(
        document(),
        end_condition="UP_TO_FACE",
        target="stop",
        end_face="stop/face/cap.end",
        direction=-1,
        offset=1.123456789012345,
    )
    source["features"][0]["params"]["direction"] = -1.0
    result = edit(source, direction="-1", offset="1.123456789012345")
    assert result == source
    assert type(result["features"][0]["params"]["direction"]) is float
    assert type(result["features"][0]["params"]["offset"]) is float
