"""Explicit shell selection stays bounded and source-bound without Blender."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "shell_selection",
    Path(__file__).parents[2] / "blender_addon/mechanical_cad_blender/shell_selection.py",
)
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)


def test_legacy_singleton_and_ordered_multiple_selection():
    assert selection.opening_ids("", "top") == ["top"]
    assert selection.opening_ids('["top", "bottom"]') == ["top", "bottom"]


@pytest.mark.parametrize(
    "value", [[], ["x", "x"], ["NONE"], [""], [1], {}, "x", list(map(str, range(65)))]
)
def test_invalid_explicit_list_never_becomes_legacy_default(value):
    with pytest.raises(ValueError):
        selection.opening_ids(json.dumps(value), "legacy")


def test_multiselect_toggle_preserves_source_and_has_limit():
    assert selection.toggle_opening(["top"], "base", ("base", "bottom")) == (
        "base",
        ["top", "bottom"],
    )
    assert selection.toggle_opening(["top"], "base", ("base", "top")) == ("base", [])
    with pytest.raises(ValueError, match="same input"):
        selection.toggle_opening(["top"], "base", ("other", "bottom"))
    with pytest.raises(ValueError, match="at most 64"):
        selection.toggle_opening(list(map(str, range(64))), "base", ("base", "another"))
