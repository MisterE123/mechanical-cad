# ruff: noqa: E402, F401, F403, F405
# Research-only direct native API probes; not imported by production.
"""Native cut/history and isolated endpoint-graph reference traversal probes."""

import itertools
import json
import math
import os
from pathlib import Path

from probe_contract import *
from probe_contract import _Operation, _subshapes

from mechanical_cad.topology import TopologyReference, resolve_reference


def reverse_record(record):
    ident, kind, start, end, *rest = record
    return (
        ident,
        kind,
        end,
        start,
        *([rest[0], "cw" if rest[1] == "ccw" else "ccw"] if rest else []),
    )


def ordered_walk(points, segments, coincidences=()):
    """An isolated graph proof, not full geometry/profile validation."""
    roots = {x: x for x in points}

    def root(x):
        while roots[x] != x:
            x = roots[x]
        return x

    for left, right in coincidences:
        a, b = sorted((root(left), root(right)))
        roots[b] = a
    by_id = {record[0]: record for record in segments}
    adjacency = {}
    endpoints = {}
    for ident, _kind, a, b, *_ in segments:
        a, b = root(a), root(b)
        if a == b:
            raise ValueError("collapsed endpoint IDs")
        endpoints[ident] = (a, b)
        adjacency.setdefault(a, []).append(ident)
        adjacency.setdefault(b, []).append(ident)
    if any(len(x) > 2 for x in adjacency.values()):
        raise ValueError("branched graph")
    ends = sorted(k for k, v in adjacency.items() if len(v) == 1)
    start = ends[0] if ends else min(adjacency)
    if ends and len(ends) != 2:
        raise ValueError("disconnected graph")
    current = start
    seen = set()
    out = []
    while True:
        available = sorted(i for i in adjacency[current] if i not in seen)
        if not available:
            break
        ident = available[0]
        record = by_id[ident]
        a, b = endpoints[ident]
        if a != current:
            record = reverse_record(record)
        out.append(record)
        seen.add(ident)
        current = b if a == current else a
        if current == start:
            break
    if len(seen) != len(segments):
        raise ValueError("disconnected graph")
    return ("open" if ends else "closed"), out


def graph_cases():
    points = {"c": (10, 0), "a": (0, -10), "b": (10, -10), "d": (10, 10), "e": (0, 10)}
    records = [
        ("bottom", "line", "a", "b"),
        ("round", "arc", "b", "d", "c", "ccw"),
        ("top", "line", "d", "e"),
        ("left", "line", "e", "a"),
    ]
    traversals = set()
    geometry = []
    for perm in itertools.permutations(records):
        for mask in range(16):
            data = [reverse_record(r) if mask & (1 << i) else r for i, r in enumerate(perm)]
            state, walk = ordered_walk(points, data)
            traversals.add(repr(walk))
    # Actual native geometry from all four cyclic rotations, both entire walk
    # directions, and every independent authored endpoint orientation.
    signatures = []
    for shift in range(4):
        for mask in range(16):
            rotated = records[shift:] + records[:shift]
            authored = [reverse_record(r) if mask & (1 << i) else r for i, r in enumerate(rotated)]
            _, walk = ordered_walk(points, authored)
            result = build_profile(points, walk)
            signatures.append(
                {
                    face["role"]: (
                        face["provenance"]["semantic_status"],
                        face["signature"]["surface"],
                    )
                    for face in result["topology"]
                }
            )
            geometry.append(result["stats"]["volume"])
    cases = {
        "one_arc": (
            {"c": (0, 0), "a": (10, 0), "b": (0, 10)},
            [("round", "arc", "a", "b", "c", "ccw")],
            (),
        ),
        "mixed_open": (
            {"c": (0, 0), "a": (10, 0), "b": (0, 10), "d": (-10, 10)},
            [("round", "arc", "a", "b", "c", "ccw"), ("tail", "line", "b", "d")],
            (),
        ),
        "equal_coords_distinct_ids": (
            {"c": (0, 0), "a": (10, 0), "b": (0, 10), "b2": (0, 10), "d": (-10, 10)},
            [("round", "arc", "a", "b", "c", "ccw"), ("tail", "line", "b2", "d")],
            (),
        ),
        "explicit_coincidence": (
            {"c": (0, 0), "a": (10, 0), "b": (0, 10), "b2": (0, 10), "d": (-10, 10)},
            [("round", "arc", "a", "b", "c", "ccw"), ("tail", "line", "b2", "d")],
            (("b", "b2"),),
        ),
        "branch": (
            {"c": (0, 0), "a": (10, 0), "b": (0, 10), "d": (-10, 10), "e": (0, 20)},
            [
                ("round", "arc", "a", "b", "c", "ccw"),
                ("tail", "line", "b", "d"),
                ("twig", "line", "b", "e"),
            ],
            (),
        ),
        "two_arc_disk": (
            {"c": (0, 0), "a": (10, 0), "b": (-10, 0)},
            [("upper", "arc", "a", "b", "c", "ccw"), ("lower", "arc", "b", "a", "c", "ccw")],
            (),
        ),
    }
    return {
        "permutation_orientation_combinations": 24 * 16,
        "distinct_canonical_traversals": len(traversals),
        "native_rebuilds": len(signatures),
        "all_semantic_role_status_surface_maps_equal": all(x == signatures[0] for x in signatures),
        "min_volume": min(geometry),
        "max_volume": max(geometry),
        "cases": {
            name: safely(lambda p=p, r=r, c=c: ordered_walk(p, r, c))
            for name, (p, r, c) in cases.items()
        },
    }


def cut_cases():
    results = {}
    for name, z, length in [("full_height_notch", -1, 9), ("partial_height_window", 1, 5)]:
        kernel = OCPKernel()
        va = BRepBuilderAPI_MakeVertex(gp_Pnt(10, 0, 0)).Vertex()
        vb = BRepBuilderAPI_MakeVertex(gp_Pnt(-10, 0, 0)).Vertex()
        arc = arc_edge((0, 0), (10, 0), (-10, 0), "ccw", (va, vb))
        line = BRepBuilderAPI_MakeEdge(vb, va).Edge()
        wire = BRepBuilderAPI_MakeWire()
        wire.Add(arc)
        arc = wire.Edge()
        wire.Add(line)
        line = wire.Edge()
        face_maker = BRepBuilderAPI_MakeFace(
            gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), wire.Wire(), True
        )
        face = face_maker.Face()
        kernel._remember(
            _Operation(
                face,
                "arc_profile_spike",
                face_maker,
                boundaries={"arc.round": arc, "line.chord": line},
            )
        )
        solid = kernel.extrude(face, 7)
        kernel.topology(solid, "ext", "extrude", {})
        tool_profile = kernel.rectangle(2, 3, -1, 8, z)
        tool = kernel.extrude(tool_profile, length)
        kernel.topology(tool, "tool", "extrude", {})
        cut = kernel.cut(solid, tool)
        topology = kernel.topology(cut, "notch", "cut", {})
        reference = TopologyReference("ext", "side.arc.round")
        resolution = resolve_reference(reference, topology)
        results[name] = {
            "stats": kernel.inspect(cut),
            "arc_images": [x for x in topology if x["role"] == "side.arc.round"],
            "resolution": resolution.to_dict(),
        }
    return results


result = {"graph_and_order": graph_cases(), "cuts": cut_cases()}
path = evidence_path("probe_lineage_results.json")
path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(path)
print(
    json.dumps(
        {
            "graph_and_order": {k: v for k, v in result["graph_and_order"].items() if k != "cases"},
            "cuts": {
                k: {
                    "volume": v["stats"]["volume"],
                    "arc_images": len(v["arc_images"]),
                    "statuses": [x["provenance"]["semantic_status"] for x in v["arc_images"]],
                    "resolution": v["resolution"]["status"],
                }
                for k, v in result["cuts"].items()
            },
        },
        indent=2,
    )
)
