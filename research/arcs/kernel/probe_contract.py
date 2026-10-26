# ruff: noqa: E402, F401, F403, F405
# Research-only direct native API probes; not imported by production.
"""Isolated OCP arc-contract experiments. Not a production implementation."""

import json
import math
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("MCAD_ROOT", str(Path(__file__).resolve().parents[3]))).resolve()
sys.path.insert(0, str(REPO / "src"))
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeVertex,
    BRepBuilderAPI_MakeWire,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.Geom import Geom_Circle
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pln, gp_Pnt, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.Precision import Precision
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_VERTEX
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS

from mechanical_cad.kernel_ocp import (
    OCPKernel,
    _Operation,
    _profile_plane,
    _subshapes,
    check_watertight_mesh,
)

EVIDENCE = Path(os.environ.get("MCAD_ARC_EVIDENCE", "/tmp/mcad-arc-kernel-evidence"))
EVIDENCE.mkdir(parents=True, exist_ok=True)


def evidence_path(name):
    return EVIDENCE / name


TAU = math.tau


def point(theta, radius=10):
    return (radius * math.cos(theta), radius * math.sin(theta))


def signed_sweep(start, end, center, direction):
    a = math.atan2(start[1] - center[1], start[0] - center[0])
    b = math.atan2(end[1] - center[1], end[0] - center[0])
    return ((b - a) % TAU) if direction == "ccw" else -((a - b) % TAU)


def edge_evidence(edge):
    curve = BRepAdaptor_Curve(edge)
    first, last = curve.FirstParameter(), curve.LastParameter()
    a = TopExp.FirstVertex_s(edge, True)
    b = TopExp.LastVertex_s(edge, True)
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, props)
    return {
        "curve": str(curve.GetType()),
        "parameters": [first, last],
        "orientation": str(edge.Orientation()),
        "start": list(BRep_Tool.Pnt_s(a).Coord()),
        "end": list(BRep_Tool.Pnt_s(b).Coord()),
        "length": props.Mass(),
        "valid": BRepCheck_Analyzer(edge).IsValid(),
        "vertices_same": a.IsSame(b),
    }


def arc_edge(
    center,
    start,
    end,
    direction,
    vertices=None,
    world=lambda p: (*p, 0.0),
    normal=(0, 0, 1),
    u=(1, 0, 0),
    radius_mode="start",
):
    radius_a, radius_b = math.dist(center, start), math.dist(center, end)
    radius = radius_a if radius_mode == "start" else (radius_a + radius_b) / 2
    angle = math.atan2(start[1] - center[1], start[0] - center[0])
    sweep = signed_sweep(start, end, center, direction)
    circ = gp_Circ(gp_Ax2(gp_Pnt(*world(center)), gp_Dir(*normal), gp_Dir(*u)), radius)
    lo, hi = (angle, angle + sweep) if sweep > 0 else (angle + sweep, angle)
    if vertices:
        va, vb = vertices if sweep > 0 else tuple(reversed(vertices))
        builder = BRepBuilderAPI_MakeEdge(Geom_Circle(circ), va, vb, lo, hi)
    else:
        builder = BRepBuilderAPI_MakeEdge(circ, lo, hi)
    if not builder.IsDone():
        raise ValueError(str(builder.Error()))
    edge = builder.Edge()
    if sweep < 0:
        edge = TopoDS.Edge(edge.Reversed())
    return edge


def build_profile(
    points, segments, *, height=7.0, origin=(0, 0, 0), quaternion=(1, 0, 0, 0), reverse_walk=False
):
    origin, u, v, normal = _profile_plane(origin, quaternion, strict=True)

    def world(p):
        return tuple(origin[k] + p[0] * u[k] + p[1] * v[k] for k in range(3))

    vertices = {
        key: BRepBuilderAPI_MakeVertex(gp_Pnt(*world(p))).Vertex() for key, p in points.items()
    }
    wire = BRepBuilderAPI_MakeWire()
    raw = {}
    inserted = {}
    seq = list(reversed(segments)) if reverse_walk else segments
    for record in seq:
        ident, kind, start, end, *rest = record
        if kind == "arc":
            edge = arc_edge(
                points[rest[0]],
                points[start],
                points[end],
                rest[1],
                (vertices[start], vertices[end]),
                world,
                normal,
                u,
            )
        else:
            edge = BRepBuilderAPI_MakeEdge(vertices[start], vertices[end]).Edge()
        if reverse_walk:
            edge = TopoDS.Edge(edge.Reversed())
        raw[f"{kind}.{ident}"] = edge
        wire.Add(edge)
        if not wire.IsDone():
            raise ValueError("wire " + str(wire.Error()))
        inserted[f"{kind}.{ident}"] = wire.Edge()
    face_maker = BRepBuilderAPI_MakeFace(
        gp_Pln(gp_Pnt(*origin), gp_Dir(*normal)), wire.Wire(), True
    )
    if not face_maker.IsDone():
        raise ValueError("face construction")
    face = face_maker.Face()
    # Exercise the explicit-plane builder with either whole-wire traversal.
    # Production should normalize winding in the pure classifier first.
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    kernel = OCPKernel()
    kernel._remember(
        _Operation(face, "arc_profile_spike", face_maker, boundaries=inserted, normal=normal)
    )
    solid = kernel.extrude(face, height)
    topology = kernel.topology(solid, "ext", "extrude", {})
    mesh = kernel.tessellate(solid, 0.01)
    mesh_check = check_watertight_mesh(mesh)
    op = kernel._operations[id(solid)]
    return {
        "valid": BRepCheck_Analyzer(solid).IsValid(),
        "wire_unique_vertices": len(_subshapes(wire.Wire(), TopAbs_VERTEX)),
        "wire_unique_edges": len(_subshapes(wire.Wire(), TopAbs_EDGE)),
        "inserted_same_as_raw": {key: inserted[key].IsSame(raw[key]) for key in inserted},
        "generated_counts": {
            key: sum(sh.ShapeType() == TopAbs_FACE for sh in op.builder.Generated(edge))
            for key, edge in inserted.items()
        },
        "raw_generated_counts": {
            key: sum(sh.ShapeType() == TopAbs_FACE for sh in op.builder.Generated(edge))
            for key, edge in raw.items()
        },
        "stats": kernel.inspect(solid),
        "topology": topology,
        "mesh": {
            "vertices": len(mesh["vertices"]),
            "triangles": len(mesh["triangles"]),
            "face_ids": sorted(set(mesh["triangle_face_ids"])),
            "check": mesh_check,
        },
    }


def safely(fn):
    try:
        return fn()
    except Exception as exc:
        return {"error": type(exc).__name__, "message": str(exc)}


def run():
    evidence = {
        "ocp_confusion": Precision.Confusion_s(),
        "ocp_angular": Precision.Angular_s(),
        "directed_arcs": {},
        "raw_parameter_boundaries": {},
        "radial_mismatch": {},
        "profiles": {},
    }
    for label, a, b, d in [
        ("quarter_ccw", 0, math.pi / 2, "ccw"),
        ("major_cw", 0, math.pi / 2, "cw"),
        ("quarter_cw", math.pi / 2, 0, "cw"),
        ("major_ccw", math.pi / 2, 0, "ccw"),
        ("seam_ccw", math.radians(350), math.radians(10), "ccw"),
        ("semicircle_ccw", 0, math.pi, "ccw"),
        ("semicircle_cw", 0, math.pi, "cw"),
    ]:
        evidence["directed_arcs"][label] = safely(
            lambda a=a, b=b, d=d: edge_evidence(arc_edge((0, 0), point(a), point(b), d))
        )
    circ = gp_Circ(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0)), 10.0)
    for angle in [
        0.0,
        1e-15,
        1e-12,
        1e-10,
        1e-8,
        1e-7,
        1e-6,
        TAU - 1e-12,
        TAU - 1e-8,
        TAU,
        TAU + 1e-6,
        2 * TAU,
    ]:

        def raw(angle=angle):
            maker = BRepBuilderAPI_MakeEdge(circ, 0.0, angle)
            return (
                edge_evidence(maker.Edge())
                if maker.IsDone()
                else {"done": False, "error": str(maker.Error())}
            )

        evidence["raw_parameter_boundaries"][repr(angle)] = safely(raw)
    for offset in [0.0, 1e-9, 5e-8, 1e-7, 1.1e-7, 2e-7, 1e-6]:
        for mode in ("start", "mean"):

            def mismatch(offset=offset, mode=mode):
                start = (10.0, 0.0)
                end = (0.0, 10.0 + offset)
                vertices = tuple(
                    BRepBuilderAPI_MakeVertex(gp_Pnt(*p, 0.0)).Vertex() for p in (start, end)
                )
                return edge_evidence(
                    arc_edge((0, 0), start, end, "ccw", vertices, radius_mode=mode)
                )

            evidence["radial_mismatch"][f"{offset:g}_{mode}"] = safely(mismatch)
    cases = {
        "semicircle": (
            {"c": (0, 0), "a": (10, 0), "b": (-10, 0)},
            [("round", "arc", "a", "b", "c", "ccw"), ("chord", "line", "b", "a")],
            math.pi * 100 / 2,
        ),
        "quarter_segment": (
            {"c": (0, 0), "a": (10, 0), "b": (0, 10)},
            [("round", "arc", "a", "b", "c", "ccw"), ("chord", "line", "b", "a")],
            50 * (math.pi / 2 - 1),
        ),
        "major_segment": (
            {"c": (0, 0), "a": (0, 10), "b": (10, 0)},
            [("round", "arc", "a", "b", "c", "ccw"), ("chord", "line", "b", "a")],
            50 * (3 * math.pi / 2 + 1),
        ),
        "two_arcs_disk": (
            {"c": (0, 0), "a": (10, 0), "b": (-10, 0)},
            [("upper", "arc", "a", "b", "c", "ccw"), ("lower", "arc", "b", "a", "c", "ccw")],
            100 * math.pi,
        ),
        "rounded_rect": (
            {"c": (10, 0), "a": (0, -10), "b": (10, -10), "d": (10, 10), "e": (0, 10)},
            [
                ("bottom", "line", "a", "b"),
                ("round", "arc", "b", "d", "c", "ccw"),
                ("top", "line", "d", "e"),
                ("left", "line", "e", "a"),
            ],
            200 + 50 * math.pi,
        ),
    }
    for label, (points, segments, area) in cases.items():
        evidence["profiles"][label] = safely(
            lambda points=points, segments=segments: build_profile(points, segments)
        )
        evidence["profiles"][label]["analytic_area"] = area
        evidence["profiles"][label]["analytic_volume"] = area * 7
    points, segments, area = cases["rounded_rect"]
    for label, kwargs in [
        ("rounded_rect_reversed", {"reverse_walk": True}),
        (
            "rounded_rect_tilted",
            {"origin": (123, -55, 89), "quaternion": (math.cos(0.37), math.sin(0.37), 0, 0)},
        ),
        ("rounded_rect_large_origin", {"origin": (1e6, -1e6, 1e6)}),
        ("rounded_rect_negative_height", {"height": -7}),
    ]:
        evidence["profiles"][label] = safely(
            lambda kwargs=kwargs: build_profile(points, segments, **kwargs)
        )
        evidence["profiles"][label]["analytic_volume"] = area * 7
    return evidence


if __name__ == "__main__":
    result = run()
    destination = evidence_path("probe_contract_results.json")
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(destination)
    print(
        json.dumps(
            {
                "directed_lengths": {
                    k: v.get("length", v) for k, v in result["directed_arcs"].items()
                },
                "profiles": {
                    k: (
                        {
                            "volume": v.get("stats", {}).get("volume"),
                            "expected": v.get("analytic_volume"),
                            "valid": v.get("valid"),
                            "error": v.get("message"),
                            "roles": [x["role"] for x in v.get("topology", [])],
                            "generated_counts": v.get("generated_counts"),
                        }
                    )
                    for k, v in result["profiles"].items()
                },
            },
            indent=2,
        )
    )
