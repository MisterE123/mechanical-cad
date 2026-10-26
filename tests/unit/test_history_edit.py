import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender/history_edit.py"
spec = importlib.util.spec_from_file_location("history_edit_test", path)
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)


def document():
    return {
        "features": [
            {"id": "sketch", "inputs": {}},
            {"id": "pad", "inputs": {"profile": "sketch"}},
            {"id": "round", "inputs": {"base": "pad"}},
            {"id": "other", "inputs": {}},
        ],
        "parameters": {"wall": 2},
        "active_feature": "round",
    }


def test_dependants_are_transitive_and_cascade_is_explicit():
    original = document()
    assert history.feature_dependants(original, "sketch") == ["pad", "round"]
    with pytest.raises(ValueError, match="explicitly"):
        history.remove_feature(original, "sketch")
    candidate = history.remove_feature(original, "sketch", include_dependants=True)
    assert [f["id"] for f in candidate["features"]] == ["other"]
    assert candidate["active_feature"] == "other"
    assert candidate["parameters"] == {"wall": 2}
    assert len(original["features"]) == 4


def test_remove_last_feature_selects_empty_output():
    candidate = history.remove_feature(
        {"features": [{"id": "a", "inputs": {}}], "parameters": {}, "active_feature": "a"}, "a"
    )
    assert candidate["active_feature"] is None


def test_parameter_overwrite_requires_explicit_choice_and_keeps_source():
    original = document()
    with pytest.raises(ValueError, match="exists"):
        history.set_parameter(original, "wall", "3")
    candidate = history.set_parameter(original, "wall", "3", replace_existing=True)
    assert candidate["parameters"]["wall"] == "3"
    assert original["parameters"]["wall"] == 2
    with pytest.raises(ValueError):
        history.set_parameter(original, "bad name", "2")
    with pytest.raises(ValueError):
        history.set_parameter(original, "new", "")


@pytest.mark.parametrize("label", ["Mounting plate", "底板 Ø20", "x" * 256, "  spaced  "])
def test_rename_preserves_everything_except_label_and_matches_model(label):
    import json

    from mechanical_cad.model import Document

    original = json.loads((path.parents[2] / "examples/viewport_rectangle.mcad.json").read_text())
    candidate = history.rename_feature(original, "sketch_1", label)
    assert Document.from_dict(candidate).features[0].label == label
    assert candidate["features"][0]["label"] == label
    candidate["features"][0]["label"] = original["features"][0]["label"]
    assert candidate == original
    assert history.rename_feature(original, "sketch_1", original["features"][0]["label"]) == original


@pytest.mark.parametrize("label", ["", "x" * 257, None, 123])
def test_rename_invalid_label_matches_model_rejection(label):
    from mechanical_cad.errors import CADException
    from mechanical_cad.model import Feature

    with pytest.raises(ValueError, match="nonempty text"):
        history.rename_feature(document(), "sketch", label)
    with pytest.raises(CADException, match="nonempty text"):
        Feature.from_dict({"id": "sketch", "kind": "sketch_rectangle", "label": label,
                           "params": {"width": 10, "height": 20}})


def test_rename_rejects_missing_target_without_mutation():
    original = document()
    with pytest.raises(ValueError, match="existing feature"):
        history.rename_feature(original, "missing", "Mounting plate")
    assert original == document()
