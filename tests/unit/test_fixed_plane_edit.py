"""Detached literal plane moves, with no mesh, source or parameter authority."""

import copy
import importlib
import json
import math
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
package = types.ModuleType("fixed_plane_test_addon")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
edit = importlib.import_module(package.__name__ + ".fixed_plane_edit")


def document():
    return {"parameters": {"distance": 4}, "active_feature": "sketch", "features": [{
        "id": "sketch", "kind": "sketch_constrained", "inputs": {}, "params": {},
        "sketch": {"plane": {"id": "copied_plane", "origin": [1.123456789012345, -0.0, 3],
                              "quaternion": [0.5, 0.5, 0.5, 0.5]},
                   "points": [{"id": "p", "u": 2, "v": "distance"}],
                   "constraints": [{"id": "fix", "kind": "fixed", "refs": ["p"]}]},
    }]}


@pytest.mark.parametrize("text, distance", [("0.5 in", 12.7), ("-2 cm", -20), ("1e-3 m", 1), ("3", 3)])
def test_signed_literal_only_changes_origin(text, distance):
    source = document()
    before = copy.deepcopy(source)
    candidate = edit.offset_candidate(source, "sketch", text)
    plane = candidate["features"][0]["sketch"]["plane"]
    assert plane["origin"] == [math.fsum((1.123456789012345, distance)), 0, 3]
    plane["origin"] = before["features"][0]["sketch"]["plane"]["origin"]
    assert candidate == source == before


@pytest.mark.parametrize("text", ["0", "-0 mm", "+0.0 in"])
def test_zero_preserves_exact_serialized_values(text):
    source = document()
    assert json.dumps(edit.offset_candidate(source, "sketch", text)) == json.dumps(source)


@pytest.mark.parametrize("patch", [{"kind": "sketch_rectangle"}, {"support_face": "f"},
    {"support_intent": {}}, {"inputs": {"support": "s"}},
    {"projections": [{"id": "p"}]}, {"inputs": {"projection_a": "source"}}])
def test_attached_or_linked_never_detached(patch):
    source = document()
    source["features"][0].update(patch)
    before = copy.deepcopy(source)
    with pytest.raises(ValueError):
        edit.offset_candidate(source, "sketch", "2")
    assert source == before


@pytest.mark.parametrize("text", ["distance", "2+3", "1 mm + 2 mm", "nan", "inf", "2 deg", "1000001", "1e300", ""])
def test_invalid_input_preserves_source(text):
    source = document()
    before = copy.deepcopy(source)
    with pytest.raises(ValueError):
        edit.offset_candidate(source, "sketch", text)
    assert source == before


def test_oblique_normal_uses_double_precision_and_keeps_raw_quaternion():
    source = document()
    plane = source["features"][0]["sketch"]["plane"]
    plane["quaternion"] = [0.9128709291752769, 0.18257418583505536, 0.3651483716701107, 0]
    frame = edit.Workplane.from_saved(plane)
    candidate = edit.offset_candidate(source, "sketch", "-0.123456789012345")
    moved = candidate["features"][0]["sketch"]["plane"]
    assert moved["quaternion"] == plane["quaternion"]
    assert moved["origin"] == [math.fsum((o, -0.123456789012345*n)) for o, n in zip(frame.origin_mm, frame.normal, strict=True)]
    plane["origin"][0] = 999999
    with pytest.raises(ValueError):
        edit.offset_candidate(source, "sketch", "1000000")
