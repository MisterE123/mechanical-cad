"""Contextual relation availability is exact-ID and order-aware, never proximity."""

import importlib
import sys
import types
from pathlib import Path

import pytest

package = types.ModuleType("mcad_position_relation_selection")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
S = importlib.import_module(package.__name__ + ".constraint_selection")


def sketch():
    return {
        "schema_version": 2,
        "id": "sketch",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [
            {"id": "a", "u": 0, "v": 0},
            {"id": "b", "u": 10, "v": 0},
            {"id": "p", "u": 5, "v": 4},
            {"id": "q", "u": 8, "v": 8},
        ],
        "lines": [{"id": "line", "start": "a", "end": "b"}],
        "circles": [
            {"id": "c1", "center": "p", "radius": 2},
            {"id": "c2", "center": "q", "radius": 3},
        ],
        "constraints": [],
    }


@pytest.mark.parametrize(
    ("kind", "selected", "refs"),
    [
        ("point_on_line", [("line", "line"), ("point", "p")], ("p", "line")),
        ("midpoint", [("line", "line"), ("point", "p")], ("p", "line")),
        ("concentric", [("circle", "c2"), ("circle", "c1")], ("c2", "c1")),
        ("circle_line_tangent", [("line", "line"), ("circle", "c1")], ("c1", "line")),
    ],
)
def test_contextual_refs_existing_and_bad_selection(kind, selected, refs):
    source = sketch()
    selection = [{"kind": k, "id": i} for k, i in selected]
    action = S.selection_contract(source, selection).action(kind)
    assert action.state == "eligible" and action.refs == refs
    assert action.reason
    source["constraints"].append({"id": "relation", "kind": kind, "refs": list(refs)})
    action = S.selection_contract(source, selection[::-1]).action(kind)
    assert action.state == "existing" and action.relation_ids == ("relation",)
    assert S.selection_contract(source, []).action(kind).state == "unavailable"


def test_endpoint_and_shared_center_relations_are_not_redundantly_added():
    source = sketch()
    selection = [{"kind": "point", "id": "a"}, {"kind": "line", "id": "line"}]
    for kind in ("point_on_line", "midpoint"):
        action = S.selection_contract(source, selection).action(kind)
        assert action.state == "unavailable" and "endpoint" in action.reason
    source["circles"][1]["center"] = "p"
    action = S.selection_contract(
        source, [{"kind": "circle", "id": "c1"}, {"kind": "circle", "id": "c2"}]
    ).action("concentric")
    assert action.state == "unavailable" and "same exact center" in action.reason
