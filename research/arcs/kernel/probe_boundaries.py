# ruff: noqa: E402, F401, F403, F405
# Research-only direct native API probes; not imported by production.
"""Additional raw OCCT probes; these intentionally bypass application guards."""

import json
import math
import os
from pathlib import Path

from probe_contract import *


def radius_parameter_grid():
    results = []
    for radius in [1e-6, 1e-3, 1.0, 10.0, 1000.0, 1e6]:
        for sweep in [
            1e-10,
            0.999e-9,
            1e-9,
            1.001e-9,
            1e-8,
            1e-6,
            TAU - 1e-10,
            TAU - 1e-9,
            TAU - 1e-8,
        ]:
            for explicit_vertices in (False, True):
                start, end = point(0, radius), point(sweep, radius)
                vertices = (
                    tuple(BRepBuilderAPI_MakeVertex(gp_Pnt(*p, 0)).Vertex() for p in (start, end))
                    if explicit_vertices
                    else None
                )
                result = safely(
                    lambda start=start, end=end, vertices=vertices: edge_evidence(
                        arc_edge((0, 0), start, end, "ccw", vertices)
                    )
                )
                results.append(
                    {
                        "radius": radius,
                        "sweep": sweep,
                        "chord": math.dist(start, end),
                        "explicit_vertices": explicit_vertices,
                        **result,
                    }
                )
    return results


def raw_wire_history():
    points = {"c": (0, 0), "a": (10, 0), "b": (-10, 0)}
    arc = arc_edge(points["c"], points["a"], points["b"], "ccw")
    line = BRepBuilderAPI_MakeEdge(gp_Pnt(*points["b"], 0), gp_Pnt(*points["a"], 0)).Edge()
    wire = BRepBuilderAPI_MakeWire()
    wire.Add(arc)
    saved_arc = wire.Edge()
    wire.Add(line)
    saved_line = wire.Edge()
    face = BRepBuilderAPI_MakeFace(
        gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), wire.Wire(), True
    ).Face()
    prism = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, 7))
    return {
        "raw_arc_is_inserted": arc.IsSame(saved_arc),
        "raw_line_is_inserted": line.IsSame(saved_line),
        "generated_raw_arc": len(list(prism.Generated(arc))),
        "generated_raw_line": len(list(prism.Generated(line))),
        "generated_inserted_arc": len(list(prism.Generated(saved_arc))),
        "generated_inserted_line": len(list(prism.Generated(saved_line))),
        "unique_vertices": len(_subshapes(wire.Wire(), TopAbs_VERTEX)),
    }


def open_wire():
    points = {"c": (0, 0), "a": (10, 0), "b": (0, 10), "d": (-10, 10)}
    vs = {k: BRepBuilderAPI_MakeVertex(gp_Pnt(*p, 0)).Vertex() for k, p in points.items()}
    arc = arc_edge(points["c"], points["a"], points["b"], "ccw", (vs["a"], vs["b"]))
    line = BRepBuilderAPI_MakeEdge(vs["b"], vs["d"]).Edge()
    wire = BRepBuilderAPI_MakeWire()
    wire.Add(arc)
    wire.Add(line)
    return {
        "done": wire.IsDone(),
        "valid": BRepCheck_Analyzer(wire.Wire()).IsValid(),
        "closed": wire.Wire().Closed(),
        "vertices": len(_subshapes(wire.Wire(), TopAbs_VERTEX)),
        "edges": len(_subshapes(wire.Wire(), TopAbs_EDGE)),
    }


# Star imports intentionally omit underscored helpers.
from probe_contract import _subshapes

result = {
    "parametric_confusion": Precision.PConfusion_s(),
    "radius_parameter_grid": radius_parameter_grid(),
    "raw_wire_history": safely(raw_wire_history),
    "open_wire": safely(open_wire),
}
path = evidence_path("probe_boundaries_results.json")
path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(path)
print(json.dumps({k: v for k, v in result.items() if k != "radius_parameter_grid"}, indent=2))
print("R=1e6 parameter cases:")
for row in result["radius_parameter_grid"]:
    if row["radius"] == 1e6:
        print(
            {
                k: row.get(k)
                for k in (
                    "sweep",
                    "chord",
                    "explicit_vertices",
                    "length",
                    "vertices_same",
                    "error",
                    "message",
                )
            }
        )
