"""Explicit shared depth is separate from local expression replacement."""

import copy
import importlib.util
import sys
import types
from pathlib import Path

import pytest

root = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"
package = types.ModuleType("depth_edit_test")
package.__path__ = [str(root)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location(package.__name__ + ".parameter_depth_edit", root / "parameter_depth_edit.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def document():
    return {
        "parameters": {"depth": 10, "derived": "depth * 2"},
        "features": [
            {"id": "pad", "kind": "extrude", "label": "Plate", "params": {"length": "depth"}},
            {"id": "tool", "kind": "extrude", "label": "Tool", "params": {"length": "derived"}},
        ],
        "active_feature": "tool",
    }


@pytest.mark.parametrize("value", [12, "12", "depth * 2", " depth", "unknown"])
def test_only_exact_names_offer_shared_edit(document, value):
    feature = document["features"][0]
    feature["params"]["length"] = value
    assert helper.depth_parameter(document, feature) == ""


def test_shared_edit_keeps_links_and_original_snapshot(document):
    before = copy.deepcopy(document)
    result = helper.edit_shared_depth(document, copy.deepcopy(document), "pad", "depth", "1.2 cm")
    assert float(result["parameters"]["depth"]) == 12
    assert result["features"] == before["features"]
    assert result["active_feature"] == "tool"
    assert document == before
    assert helper.affected_uses(document, "depth") == ("Parameter: derived", "Plate: length", "Tool: length")


def test_unchanged_parameter_keeps_numeric_type(document):
    result = helper.edit_shared_depth(document, copy.deepcopy(document), "pad", "depth", "10")
    assert type(result["parameters"]["depth"]) is int


@pytest.mark.parametrize("mutation", ["link", "kind", "name"])
def test_shared_edit_rejects_changed_intent(document, mutation):
    candidate = copy.deepcopy(document)
    name = "depth"
    if mutation == "link":
        candidate["features"][0]["params"]["length"] = "12"
    if mutation == "kind":
        candidate["features"][0]["kind"] = "extrude_to_face"
    if mutation == "name":
        name = "derived"
    with pytest.raises(ValueError):
        helper.edit_shared_depth(document, candidate, "pad", name, "12")


def test_cycles_are_bounded_not_evaluated(document):
    document["parameters"]["depth"] = "derived"
    assert len(helper.affected_uses(document, "depth")) == 4


def test_shared_formula_is_retained_not_evaluated(document):
    result = helper.edit_shared_depth(document, copy.deepcopy(document), "pad", "depth", "other * 2")
    assert result["parameters"]["depth"] == "other * 2"
    assert result["features"][0]["params"]["length"] == "depth"


def test_empty_shared_value_rejects_without_mutation(document):
    before = copy.deepcopy(document)
    with pytest.raises(ValueError):
        helper.edit_shared_depth(document, copy.deepcopy(document), "pad", "depth", " ")
    assert document == before


@pytest.fixture
def linked_document(document):
    document["features"].append({
        "id": "cut", "kind": "cut", "label": "Pocket", "params": {},
        "inputs": {"base": "base", "tool": "pad"},
    })
    return document


def test_linked_shared_parameter_keeps_tool_formula(linked_document):
    result = helper.edit_shared_linked_depth(linked_document, copy.deepcopy(linked_document), "cut", "pad", "depth", "12")
    assert result["parameters"]["depth"] == "12"
    assert result["features"] == linked_document["features"]
    assert linked_document["parameters"]["depth"] == 10


def test_unchanged_tool_formula_still_requires_independent_shared_tool_consent(linked_document):
    linked_document["features"].append({"id": "other", "label": "Other branch", "inputs": {"base": "pad"}})
    before = copy.deepcopy(linked_document)
    candidate = copy.deepcopy(linked_document)
    with pytest.raises(ValueError, match="Other branch.*explicitly allow"):
        helper.edit_shared_linked_depth(linked_document, candidate, "cut", "pad", "depth", "12")
    assert linked_document == candidate == before
    result = helper.edit_shared_linked_depth(linked_document, candidate, "cut", "pad", "depth", "12", allow_shared=True)
    assert result["parameters"]["depth"] == "12"
    assert result["features"] == before["features"]
    assert linked_document == candidate == before


def test_no_shared_change_does_not_require_consent(linked_document):
    linked_document["features"].append({"id": "other", "label": "Other branch", "inputs": {"base": "pad"}})
    assert helper.edit_shared_linked_depth(linked_document, copy.deepcopy(linked_document), "cut", "pad", "depth", "10") == linked_document


@pytest.mark.parametrize("change", ["rebind", "missing", "duplicate", "unsupported"])
def test_linked_shared_edit_rejects_uncertain_binding_without_mutation(linked_document, change):
    candidate = copy.deepcopy(linked_document)
    if change == "rebind":
        candidate["features"][-1]["inputs"]["tool"] = "tool"
    elif change == "missing":
        candidate["features"] = candidate["features"][1:]
    elif change == "duplicate":
        candidate["features"].append(copy.deepcopy(candidate["features"][0]))
    else:
        linked_document["features"][-1]["kind"] = "intersection"
    before_source, before_candidate = copy.deepcopy(linked_document), copy.deepcopy(candidate)
    with pytest.raises(ValueError, match="reopen"):
        helper.edit_shared_linked_depth(linked_document, candidate, "cut", "pad", "depth", "12", allow_shared=True)
    assert linked_document == before_source and candidate == before_candidate


def test_pending_consent_hint_is_read_only_and_matches_shared_refusal(linked_document):
    linked_document["features"].append({"id": "other", "label": "Other branch", "inputs": {"base": "pad"}})
    before = copy.deepcopy(linked_document)
    options = {"tool_id": "pad", "length": "depth", "profile": "p"}
    # Give the synthetic tool a stable profile, as real authoring documents do.
    linked_document["features"][0]["inputs"] = {"profile": "p"}
    before = copy.deepcopy(linked_document)
    assert not helper.pending_tool_consent(linked_document, "cut", **options)
    assert helper.pending_tool_consent(linked_document, "cut", parameter_name="depth", parameter_value="12", **options)
    assert not helper.pending_tool_consent(linked_document, "cut", parameter_name="depth", parameter_value="10", **options)
    options["length"] = "12"
    assert helper.pending_tool_consent(linked_document, "cut", **options)
    assert linked_document == before


def test_consent_refusal_has_no_geometric_hint_but_real_error_keeps_it():
    import importlib

    linked = importlib.import_module(package.__name__ + ".linked_extrusion_edit")
    guidance = importlib.import_module(package.__name__ + ".feature_guidance")
    refusal = guidance.feature_error("cut", linked.SharedToolConsentRequired("Shared tool needs consent"))
    assert "Model unchanged" in refusal and "Cancel" in refusal
    assert "Also update the shared tool and listed features" in refusal
    assert "one valid solid" not in refusal
    geometric = guidance.feature_error("cut", ValueError("Boolean failed"))
    assert "Boolean failed" in geometric and "one valid solid" in geometric
