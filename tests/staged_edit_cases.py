"""Native-free fixtures shared by kernel and registered Blender repair checks."""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def feature(document, identifier):
    return next(row for row in document["features"] if row["id"] == identifier)


def support_case():
    base = json.loads(
        (ROOT / "examples/topology_support/split_plane_preserved.mcad.json").read_text()
    )
    feature(base, "slot_tool")["params"]["length"] = 1
    feature(base, "attached").pop("support_intent")
    proposed = copy.deepcopy(base)
    feature(proposed, "slot_tool")["params"]["length"] = 5
    return base, proposed


def projection_case():
    base = {
        "schema_version": 2,
        "id": "staged_projection",
        "name": "Explicit upstream projection repair",
        "units": "mm",
        "parameters": {"r": 3},
        "active_feature": "solid",
        "features": [
            {
                "id": "source",
                "kind": "sketch_constrained",
                "label": "Source",
                "inputs": {},
                "params": {},
                "sketch": {
                    "schema_version": 2,
                    "id": "source_geometry",
                    "units": "mm",
                    "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
                    "points": [{"id": "p", "u": 4, "v": 5}],
                    "lines": [],
                    "circles": [{"id": "ring", "center": "p", "radius": 1}],
                    "constraints": [
                        {"id": "anchor", "kind": "fixed", "refs": ["p"], "target": [4, 5]},
                        {"id": "size", "kind": "radius", "refs": ["ring"], "value": "r"},
                    ],
                },
            },
            {
                "id": "target",
                "kind": "sketch_constrained",
                "label": "Target",
                "inputs": {"external": "source"},
                "params": {},
                "projections": [{"source": "ring", "target": "reference"}],
                "sketch": {
                    "schema_version": 2,
                    "id": "target_geometry",
                    "units": "mm",
                    "plane": {"id": "xy", "origin": [1, 2, 10], "quaternion": [1, 0, 0, 0]},
                    "points": [{"id": "q", "u": 0, "v": 0}],
                    "lines": [],
                    "circles": [
                        {"id": "reference", "center": "q", "radius": 1, "construction": True},
                        {"id": "outline", "center": "q", "radius": 1},
                    ],
                    "constraints": [
                        {"id": "anchor", "kind": "fixed", "refs": ["q"], "target": [0, 0]},
                        {"id": "size", "kind": "radius", "refs": ["reference"], "value": 1},
                        {"id": "match", "kind": "equal", "refs": ["reference", "outline"]},
                    ],
                },
            },
            {
                "id": "solid",
                "kind": "extrude",
                "label": "Dependent solid",
                "inputs": {"profile": "target"},
                "params": {"length": 5},
            },
        ],
    }
    proposed = copy.deepcopy(base)
    source = feature(proposed, "source")["sketch"]
    source["circles"][0]["id"] = "replacement_ring"
    source["constraints"][1]["refs"] = ["replacement_ring"]
    source["constraints"][1]["value"] = "r + 1"
    return base, proposed


def multiple_projection_case():
    """Two independent reference consumers of the same explicitly edited source."""
    base, proposed = projection_case()
    for document in (base, proposed):
        target = copy.deepcopy(feature(document, "target"))
        target["id"] = "target_two"
        target["label"] = "Second reference consumer"
        target["sketch"]["id"] = "second_target_geometry"
        document["features"].insert(2, target)
    return base, proposed


def same_sketch_projection_case():
    base, _ = projection_case()
    source = feature(base, "source")["sketch"]
    source["points"].append({"id": "p2", "u": 15, "v": 5})
    source["circles"].append({"id": "ring2", "center": "p2", "radius": 2})
    source["constraints"].extend(
        [
            {"id": "anchor2", "kind": "fixed", "refs": ["p2"], "target": [15, 5]},
            {"id": "size2", "kind": "radius", "refs": ["ring2"], "value": 2},
        ]
    )
    target = feature(base, "target")
    target["projections"].append({"source": "ring2", "target": "reference2"})
    sketch = target["sketch"]
    sketch["points"].append({"id": "q2", "u": 14, "v": 3})
    sketch["circles"].append(
        {"id": "reference2", "center": "q2", "radius": 2, "construction": True}
    )
    sketch["constraints"].extend(
        [
            {"id": "anchor2", "kind": "fixed", "refs": ["q2"], "target": [14, 3]},
            {"id": "size2", "kind": "radius", "refs": ["reference2"], "value": 2},
        ]
    )
    proposed = copy.deepcopy(base)
    source = feature(proposed, "source")["sketch"]
    for row in source["circles"]:
        row["id"] = "replacement_" + row["id"]
    for row in source["constraints"]:
        if row["kind"] == "radius":
            row["refs"] = ["replacement_" + row["refs"][0]]
    source["constraints"][1]["value"] = "r + 1"
    return base, proposed


def coupled_projection_case():
    base, _ = same_sketch_projection_case()
    # Current schema-3 evidence preserves libslvs redundant_okay candidates;
    # the intentionally unchanged legacy validator rejects that native report.
    for f in base["features"]:
        if "sketch" in f:
            f["sketch"]["schema_version"] = 3
            f["sketch"]["arcs"] = []
    source = feature(base, "source")["sketch"]
    source["constraints"][-1]["value"] = "r"
    target = feature(base, "target")["sketch"]
    target["constraints"][-1]["value"] = "r"
    target["constraints"].append(
        {
            "id": "coupled",
            "kind": "equal",
            "refs": ["reference", "reference2"],
        }
    )
    proposed = copy.deepcopy(base)
    source = feature(proposed, "source")["sketch"]
    for row in source["circles"]:
        row["id"] = "replacement_" + row["id"]
    for row in source["constraints"]:
        if row["kind"] == "radius":
            row["refs"] = ["replacement_" + row["refs"][0]]
            row["value"] = "r + 1"
    return base, proposed
