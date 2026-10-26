"""Everyday relations retain exact native solve and independent residual evidence."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_common_relations")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
operations = importlib.import_module(package.__name__ + ".operation_contracts")


def document(kind, version):
    points = [
        {"id": "a", "u": 0, "v": 0},
        {"id": "b", "u": 10, "v": 0},
        {"id": "p", "u": 3, "v": 3},
    ]
    lines = [{"id": "line", "start": "a", "end": "b"}]
    circles = []
    constraints = [
        {"id": "fa", "kind": "fixed", "refs": ["a"], "target": [0, 0]},
        {"id": "fb", "kind": "fixed", "refs": ["b"], "target": [10, 0]},
    ]
    refs = ["p", "line"]
    if kind == "symmetry":
        points.append({"id": "q", "u": 4, "v": -2})
        constraints.append({"id": "fp", "kind": "fixed", "refs": ["p"], "target": [3, 3]})
        refs = ["p", "q", "line"]
    elif kind == "concentric":
        points = [points[0], points[2]]
        lines = []
        constraints = constraints[:1]
        circles = [
            {"id": "c1", "center": "a", "radius": 2},
            {"id": "c2", "center": "p", "radius": 3},
        ]
        constraints += [
            {"id": "r1", "kind": "radius", "refs": ["c1"], "value": 2},
            {"id": "r2", "kind": "radius", "refs": ["c2"], "value": 3},
        ]
        refs = ["c1", "c2"]
    elif kind == "circle_line_tangent":
        circles = [{"id": "c1", "center": "p", "radius": 2}]
        constraints += [{"id": "r1", "kind": "radius", "refs": ["c1"], "value": 2}]
        refs = ["c1", "line"]
    constraints += [{"id": "relation", "kind": kind, "refs": refs}]
    sketch = {
        "schema_version": version,
        "id": "geometry",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": points,
        "lines": lines,
        "constraints": constraints,
    }
    if version >= 2:
        sketch["circles"] = circles
    if version == 3:
        sketch["arcs"] = []
    return {
        "schema_version": 2,
        "id": "part",
        "name": "Common sketch relations",
        "units": "mm",
        "parameters": {},
        "active_feature": "sketch",
        "features": [{"id": "sketch", "kind": "sketch_constrained", "sketch": sketch}],
    }


@pytest.mark.parametrize(
    "kind,version",
    [
        (kind, version)
        for kind in ("point_on_line", "midpoint", "concentric", "circle_line_tangent", "symmetry")
        for version in (1, 2, 3)
        if version > 1 or kind in {"point_on_line", "midpoint", "symmetry"}
    ],
)
def test_native_relation_and_forged_residual(kind, version):
    source = document(kind, version)
    req = {
        "protocol_version": 1,
        "result_version": 3 if version == 3 else 2,
        "action": "solve_sketch",
        "feature_id": "sketch",
        "document": source,
    }
    response = process_request(req)
    assert response["ok"], response
    operations.validate_response(req, response)
    report = response["result"]["sketch"]
    assert report["remaining_dof"] == (1 if kind in {"point_on_line", "circle_line_tangent"} else 0)
    forged = copy.deepcopy(response)
    point = next(p for p in forged["result"]["sketch"]["solved"]["points"] if p["id"] == "p")
    point["v"] += 1
    with pytest.raises(ValueError):
        operations.validate_response(req, forged)


def test_relation_math_stays_identical_to_core():
    root = Path(__file__).resolve().parents[2]
    assert (root / "src/mechanical_cad/sketch_relations.py").read_text() == (
        root / "blender_addon/mechanical_cad_blender/sketch_relations.py"
    ).read_text()


@pytest.mark.parametrize("kind", ["point_on_line", "midpoint", "concentric", "circle_line_tangent"])
def test_invalid_relation_reference_shapes_rejected(kind):
    source = document(kind, 3)["features"][0]["sketch"]
    relation = next(c for c in source["constraints"] if c["id"] == "relation")
    if kind in {"point_on_line", "midpoint"}:
        relation["refs"] = ["a", "line"]
    elif kind == "concentric":
        source["circles"][1]["center"] = "a"
    else:
        relation["refs"].reverse()
    contracts = importlib.import_module(package.__name__ + ".sketch_contracts_v3")
    with pytest.raises(ValueError):
        contracts.normalize_sketch_v3(source)
