"""Pure synthetic generated-side trace controls; never native success evidence.

Every construction below is detached Python data. The real collector is covered
separately by source inspection and binding doubles; no native import is allowed.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.abc
import itertools
import math
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from mechanical_cad.arc_profile_native_evidence import (
    _generated_cell,
    _generated_delta,
    expected_edge_metadata,
    validate_generated_trace_observation,
)
from mechanical_cad.arc_profile_native_plan import (
    NativeEndpointObservation,
    NativePlane,
    NativePlanError,
    NativeRadialDirection,
    _continue_actual_support_for_vertices,
    _continue_vertex_representation,
    entry_context,
    plan_bytes,
    prepare_native_geometry,
    transform,
)
from mechanical_cad.arc_profile_primitives import Dyadic, PrimitiveContext
from mechanical_cad.arc_profile_sector_source import (
    SectorArc,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
)


class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (
            fullname.split(".")[0] in {"OCP", "OCC", "cadquery", "slvs", "bpy"}
            or fullname == "mechanical_cad.kernel_ocp"
        ):
            raise AssertionError(fullname)


@pytest.fixture(autouse=True)
def no_native_imports():
    blocker = NoNative()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


def location(v=(0.0, 0.0, 0.0)):
    return {
        "identity": v == (0.0, 0.0, 0.0),
        "matrix": tuple(tuple(float(i == j) for j in range(3)) + (v[i],) for i in range(3)),
    }


def curve(kind, origin, direction, ran, ident=True, u=None, v=None, n=None, r=None):
    return {
        "kind": kind,
        "location": origin,
        "direction": direction,
        "range": ran,
        "identity_location": ident,
        "u": u,
        "v": v,
        "normal": n,
        "radius": r,
    }


def cross(a, b):
    return tuple(a[i] * b[j] - a[j] * b[i] for i, j in ((1, 2), (2, 0), (0, 1)))


def fixture(
    *, center=(0.0, 0.0), angle=0.0, sweep=math.pi / 2, gap=0.0, h=7.0, quat=(1.0, 0.0, 0.0, 0.0)
):
    p0 = tuple(center[i] + 5.0 * v for i, v in enumerate((math.cos(angle), math.sin(angle))))
    p1 = tuple(
        center[i] + (5.0 - gap) * v
        for i, v in enumerate((math.cos(angle + sweep), math.sin(angle + sweep)))
    )
    if angle == 0.0 and sweep == math.pi / 2:
        p1 = (center[0], center[1] + 5.0 - gap)
    src = SectorGeometrySource(
        (SectorPoint("c", *center), SectorPoint("a", *p0), SectorPoint("b", *p1)),
        (SectorLine("ra", "c", "a"), SectorLine("rb", "c", "b")),
        (SectorArc("arc", "c", "a", "b", "ccw"),),
    )
    c = entry_context()
    p = prepare_native_geometry(src, NativePlane(quaternion=quat), context=c)
    ds = tuple(
        NativeRadialDirection(line.entity_id, transform(p.frame, line.direction))
        for line in p.lines
    )
    p, ticket = _continue_actual_support_for_vertices(p, ds, c)
    obs = tuple(
        NativeEndpointObservation(
            pid,
            param,
            transform(
                p.frame,
                tuple(
                    center[j] + p.radius * v
                    for j, v in enumerate((math.cos(param), math.sin(param)))
                ),
            ),
        )
        for pid, param in zip(("a", "b"), p.parameters, strict=True)
    )
    q = _continue_vertex_representation(p, obs, c, continuation=ticket)
    return p, q, generated_record(p, q, h), c


def generated_record(p, q, height=7.0):
    h = height
    arc = p.source.incidence.arc
    point_ids = (arc.center_id, arc.start_id, arc.end_id)
    outer_ids = (arc.start_id, arc.end_id)
    vec = tuple(h * v for v in p.frame.normal)
    pts = dict(q.vertices)
    origin = transform(p.frame, p.center)
    roles = tuple(f"{u.kind}.{u.entity_id}" for u in p.source.boundary)
    surfaces = {}
    for role in roles:
        is_arc = role.startswith("arc.")
        u = (
            p.frame.u
            if is_arc
            else transform(
                p.frame,
                next(
                    line.direction
                    for line in p.accepted_support.lines
                    if role == "line." + line.entity_id
                ),
            )
        )
        v = p.frame.v if is_arc else tuple(-n for n in p.frame.normal)
        surfaces["side." + role] = {
            "kind": "Geom_CylindricalSurface" if is_arc else "Geom_Plane",
            "origin": origin,
            "u": u,
            "v": v,
            "normal": tuple(-n for n in p.frame.normal) if is_arc else cross(u, v),
            "radius": p.radius if is_arc else None,
        }
    vertices = tuple(
        {
            "id": f"{lv}.{pid}",
            "point": tuple(v + t for v, t in zip(pts[pid], vec, strict=True))
            if lv == "top"
            else pts[pid],
            "tolerance": 1e-7,
            "location": location(vec if lv == "top" else (0.0, 0.0, 0.0)),
            "history_matches": True,
        }
        for lv in ("base", "top")
        for pid in point_ids
    )
    ed = []
    for role in tuple(f"{lv}.{r}" for lv in ("base", "top") for r in roles) + tuple(
        f"vertical.{pid}" for pid in point_ids
    ):
        top = role.startswith("top.")
        levelloc = vec if top else (0.0, 0.0, 0.0)
        if role.startswith("vertical."):
            pid = role[9:]
            ids = ("base." + pid, "top." + pid)
            ran = (0.0, h)
            cv = curve("line", pts[pid], p.frame.normal, ran)
        else:
            lv, pr = role.split(".", 1)
            ids = tuple(lv + "." + pid for pid in expected_edge_metadata(p, pr, "support")[0])
            if pr.startswith("arc."):
                ran = p.increasing_parameters
                cv = curve(
                    "circle",
                    origin,
                    None,
                    ran,
                    u=p.frame.u,
                    v=p.frame.v,
                    n=p.frame.normal,
                    r=p.radius,
                )
            else:
                line = next(
                    line for line in p.accepted_support.lines if pr == "line." + line.entity_id
                )
                ran = (0.0, line.trim_parameter)
                cv = curve("line", origin, transform(p.frame, line.direction), ran)
        inv = [
            {
                "index": 0,
                "representation_type": "BRep_Curve3D",
                "is_curve3d": True,
                "is_on_surface": False,
                "is_closed_surface": False,
                "is_regularity": False,
                "regularity": None,
                "surface_index": None,
                "surface_is_retained": False,
                "surface_fields": None,
                "location": location(),
                "range": ran,
                "curve3d": cv,
                "pcurves": (),
                "owner_roles": (),
            }
        ]
        if ".arc." in role or role in tuple("vertical." + pid for pid in outer_ids):
            ploc = tuple(-t for t in vec) if top else (0.0, 0.0, 0.0)
            uv = (
                (p.parameters[outer_ids.index(role[9:])], 0.0)
                if role.startswith("vertical.")
                else (0.0, -h if top else 0.0)
            )
            d = (0.0, -1.0) if role.startswith("vertical.") else (1.0, 0.0)
            pc = curve("line", uv, d, ran, ident=ploc == (0.0, 0.0, 0.0))
            inv.append(
                {
                    "index": 1,
                    "representation_type": "BRep_CurveOnSurface",
                    "is_curve3d": False,
                    "is_on_surface": True,
                    "is_closed_surface": False,
                    "is_regularity": False,
                    "regularity": None,
                    "surface_index": 0,
                    "surface_is_retained": False,
                    "surface_fields": surfaces["side.arc." + arc.id],
                    "location": location(ploc),
                    "range": ran,
                    "curve3d": None,
                    "pcurves": (pc,),
                    "owner_roles": ("side.arc." + arc.id,),
                }
            )
        ed.append(
            {
                "role": role,
                "location": location(levelloc),
                "range": ran,
                "endpoint_ids": ids,
                "tolerance": 1e-7,
                "representations": tuple(inv),
                "identity_matches": True,
            }
        )
    edges = {e["role"]: e for e in ed}
    faces = []
    for use in p.source.boundary:
        pr = f"{use.kind}.{use.entity_id}"
        sr = "side." + pr
        cyc = (
            (f"base.{pr}", (f"base.{use.start_id}", f"base.{use.end_id}")),
            (f"vertical.{use.end_id}", (f"base.{use.end_id}", f"top.{use.end_id}")),
            (f"top.{pr}", (f"top.{use.end_id}", f"top.{use.start_id}")),
            (f"vertical.{use.start_id}", (f"top.{use.start_id}", f"base.{use.start_id}")),
        )
        occ = tuple(
            {
                "edge_role": r,
                "local_orientation": int(ids != edges[r]["endpoint_ids"]),
                "orientation": int(ids != edges[r]["endpoint_ids"]),
                "endpoint_ids": ids,
            }
            for r, ids in cyc
        )
        faces.append(
            {
                "role": sr,
                "generated_is_same": True,
                "generated_is_partner": True,
                "generated_is_equal": True,
                "generated_orientation": 0,
                "orientation": 0,
                "shape_location": location(),
                "surface_location": location(),
                "surface_fields": surfaces[sr],
                "wire_local_orientation": 0,
                "wire_orientation": 0,
                "occurrences": occ,
            }
        )
    return {
        "height": h,
        "actual_vector": vec,
        "vertices": vertices,
        "edges": tuple(ed),
        "faces": tuple(faces),
    }


def planar_branches(p, q, r):
    for face in r["faces"]:
        if face["surface_fields"]["kind"] != "Geom_Plane":
            continue
        for occ in face["occurrences"]:
            edge = next(e for e in r["edges"] if e["role"] == occ["edge_role"])
            role = edge["role"]
            vertical = role.startswith("vertical.")
            top = role.startswith("top.")
            origin = (
                (0.0 if role == "vertical.c" else p.radius, 0.0)
                if vertical
                else (0.0, -r["height"] if top else 0.0)
            )
            direction = (0.0, -1.0) if vertical else (1.0, 0.0)
            v = tuple(-x for x in r["actual_vector"]) if top else (0.0, 0.0, 0.0)
            idx = len(edge["representations"])
            surfaces = [
                x["surface_index"]
                for x in edge["representations"]
                if x["surface_index"] is not None
            ]
            si = max(surfaces, default=-1) + 1
            branch = curve("line", origin, direction, edge["range"], ident=v == (0.0, 0.0, 0.0))
            entry = {
                "index": idx,
                "representation_type": "BRep_CurveOnSurface",
                "is_curve3d": False,
                "is_on_surface": True,
                "is_closed_surface": False,
                "is_regularity": False,
                "regularity": None,
                "surface_index": si,
                "surface_is_retained": False,
                "surface_fields": face["surface_fields"],
                "location": location(v),
                "range": edge["range"],
                "curve3d": None,
                "pcurves": (branch,),
                "owner_roles": (face["role"],),
            }
            edge["representations"] += (entry,)


def mutate(which, r):
    e = r["edges"][0]
    f = r["faces"][0]
    rep = e["representations"][0]
    if which == "unknown":
        r["extra"] = 1
    elif which == "vertex_count":
        r["vertices"] = r["vertices"][:-1]
    elif which == "vertex_id":
        r["vertices"][0]["id"] = "base.a"
    elif which == "vertex_point":
        r["vertices"][1]["point"] = (5.00000001, 0.0, 0.0)
    elif which == "vertex_history":
        r["vertices"][1]["history_matches"] = False
    elif which == "edge_identity":
        e["identity_matches"] = False
    elif which == "top_translation":
        r["vertices"][3]["location"] = location((0.0, 0.0, 14.0))
    elif which == "curve_origin":
        rep["curve3d"]["location"] = (0.0, 0.0, 1.0)
    elif which == "curve_normal":
        rep["curve3d"]["normal"] = (0.0, 0.0, -1.0)
    elif which == "curve_radius":
        rep["curve3d"]["radius"] = 5.1
    elif which == "edge_range":
        e["range"] = (0.0, 1.0)
    elif which == "matrix_shear":
        e["location"]["matrix"] = ((1.0, 0.1, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))
    elif which == "cylinder_owner":
        e["representations"][1]["owner_roles"] = ()
    elif which == "cylinder_location":
        e["representations"][1]["location"] = location((0.0, 0.0, -7.0))
        e["representations"][1]["pcurves"][0]["identity_location"] = False
    elif which == "duplicate_branch":
        x = copy.deepcopy(e["representations"][1])
        x["index"] = 2
        e["representations"] += (x,)
    elif which == "seam":
        x = e["representations"][1]
        x["is_closed_surface"] = True
        x["is_regularity"] = True
        x["representation_type"] = "BRep_CurveOnClosedSurface"
        x["pcurves"] += tuple(copy.deepcopy(x["pcurves"]))
    elif which == "pcurve_coefficient":
        e["representations"][1]["pcurves"][0]["direction"] = (1.0, 0.1)
    elif which == "surface_u":
        f["surface_fields"]["u"] = (math.nextafter(1.0, 2.0), 0.0, 0.0)
    elif which == "surface_axis":
        f["surface_fields"]["normal"] = (0.0, 0.0, 1.0)
    elif which == "face_placement":
        f["surface_location"] = location((0.0, 0.0, 7.0))
    elif which == "face_partner":
        f["generated_is_partner"] = False
    elif which == "face_equal":
        f["generated_is_equal"] = False
    elif which == "orientation":
        f["occurrences"][0]["local_orientation"] ^= 1
    elif which == "wrong_face_edge":
        f["occurrences"][0]["edge_role"] = "base.line.ra"
    elif which == "reordered_cycle":
        f["occurrences"] = (f["occurrences"][1], f["occurrences"][0], *f["occurrences"][2:])
    elif which == "foreign_bad_type":
        x = copy.deepcopy(e["representations"][1])
        x.update(index=2, surface_index=1, owner_roles=())
        x["surface_fields"]["kind"] = "Geom_BSplineSurface"
        e["representations"] += (x,)
    elif which == "native_old_ruling":
        x = next(e for e in r["edges"] if e["role"] == "vertical.b")
        x["representations"][0]["curve3d"]["location"] = (0.0, 5.0 - 2**-31, 0.0)
    else:
        raise AssertionError(which)


names = (
    "unknown vertex_count vertex_id vertex_point vertex_history edge_identity top_translation curve_origin curve_normal curve_radius edge_range matrix_shear cylinder_owner cylinder_location duplicate_branch seam pcurve_coefficient surface_u surface_axis face_placement face_partner face_equal orientation wrong_face_edge foreign_bad_type native_old_ruling"
).split()
SNAPSHOT7_EVIDENCE_SPANS = {
    "NativeMassCheck": "364047fc1f70d4f0ebf17db2cf2fbbd5cd0ec88a14d9111fc63af182a9fb422c",
    "_keys": "dfb787462885e79444167bee98d65f3229f8a68ac93ebeb572d42fee23ac5a2f",
    "_finite": "1067b338bb39974df1848538b9ae41af286bf377120430cde4037e768de5238d",
    "_vector": "7dde9ac66a10fa105a9af2f7597cc7d5484c65214513203cfd94281fa6969bda",
    "_yes": "80676f3b838e82a0053b25848a6d2d7a5d3ebfab4691805f67dad34453f3875f",
    "_validate_curve_fields": "9c6cab5252689e58c4206d76e36058ca9a06194e54d49de49d807a6e13de419e",
    "validate_initial_curve_fields": "7bdba9dab4af427667e965bd8b4f46d91d84ec6156a350dcbef21ba400cd4d0b",
    "validate_curve_fields": "24e7b74468d7538be474267fa77ead92d79cfff99da1af788c37b5989cdcb7dc",
    "expected_edge_metadata": "21d13df733b88029454a48637f577f4debc7f558ed536c2d08d46f7b8666f828",
    "_stored_curve_grammar": "8c0ae199a6a1479a13dbd4a6d2d78a85a827925d28b246340ab70670fda0a81d",
    "validate_representation_inventory": "8e86cb5a263c7aa5c5d21cce6f5fd8a7eb82bc6c3c5c88f2da221e84c1801f35",
    "_distance": "f74159b38713b490f720db1d0398127c53ee5d9fb53fababc539d6955cce1dc3",
    "native_height": "d5fec24971d2ae29784ee5eb38683c1ef8accbde4469a9d57b55c6c4792ec1a2",
    "validate_end_cap_observation": "3114cb8995e1d80eaeaeb0ab485a032f81eaa125fce3b95831f6ced77d437c3b",
    "mass_limits": "63dc43d4a871ea8d4ebb37b4bcdd787bf9222951a46ffa6dfbc79ffe63854de2",
    "mass_check_record": "492f8739c74a25f94e2ffa5cb46b4633f66070df86af250a7945e4eb5a2f750e",
    "check_masses": "faa4e57c4721414fe7783871930aa2d88b4e8ce4a82f7041649a70000b1ddef2",
    "bounded_evidence_bytes": "1e71a405559a1eb71e8bf6aa83fb32e5af36228c8db03ae3ab3fb3075325420d",
}


def check(p, q, r, c):
    return validate_generated_trace_observation(p, q, r, height=r["height"], context=c)


@pytest.mark.parametrize(
    "settings",
    (
        {},
        {"center": (17.0, -29.0), "angle": 0.4, "sweep": 2.0, "gap": 2**-31},
        {"center": (999000.0, 999000.0), "gap": 2**-31, "h": 1000.0},
        {"quat": (0.0, 1.0, 0.0, 0.0)},
    ),
)
def test_synthetic_whole_trace_preserves_all_mathematical_baselines(settings):
    p, q, r, c = fixture(**settings)
    before = plan_bytes(p)
    start = c.operations
    source = p.source
    radius = p.final_cell_radius
    root_counts = (p.retained_root_count, p.accepted_support.retained_root_count)
    out = check(p, q, r, c)
    assert plan_bytes(p) == before and p.source is source and p.final_cell_radius is radius
    assert root_counts == (p.retained_root_count, p.accepted_support.retained_root_count)
    assert 0 < c.operations - start <= 32768 and c.operations <= 200000
    assert out["operations_start"] == start and out["operations_end"] == c.operations
    assert out["analytic_supports"] == "exact_checked_coefficients_and_ranges"
    assert out["affine_trace_policy"] == "bounded_endpoint_residuals"
    assert len(out["inferred_planar_projections"]) == 16


@pytest.mark.parametrize(
    "settings", ({}, {"center": (17.0, -29.0), "angle": 0.4, "sweep": 2.0, "gap": 2**-31})
)
def test_actual_stored_planar_affine_branches_have_no_inferred_native_curves(settings):
    p, q, r, c = fixture(**settings)
    planar_branches(p, q, r)
    assert not check(p, q, r, c)["inferred_planar_projections"]


@pytest.mark.parametrize("orientation", (0, 1))
@pytest.mark.parametrize("generated_orientation", (0, 1))
def test_generated_wrapper_and_actual_material_occurrence_are_distinct(
    orientation, generated_orientation
):
    p, q, r, c = fixture()
    for face in r["faces"]:
        face["orientation"] = orientation
        face["wire_orientation"] = orientation
        face["generated_orientation"] = generated_orientation
        face["generated_is_equal"] = orientation == generated_orientation
        for occurrence in face["occurrences"]:
            occurrence["local_orientation"] ^= orientation
    check(p, q, r, c)


@pytest.mark.parametrize("order", tuple(itertools.permutations(range(4))))
def test_native_iterator_order_is_preserved_and_unique_oriented_cycle_is_derived(order):
    p, q, r, c = fixture()
    for f in r["faces"]:
        f["occurrences"] = tuple(f["occurrences"][k] for k in order)
    before = copy.deepcopy(r)
    out = check(p, q, r, c)
    assert r == before
    for indices in out["oriented_cycle_indices"]:
        inferred = indices["occurrence_indices"]
        assert inferred[0] == 0 and len(set(inferred)) == 4
        assert tuple(order[k] for k in inferred) == tuple((order[0] + k) % 4 for k in range(4))


@pytest.mark.parametrize("name", names)
def test_generated_structural_fields_and_whole_trace_mutations_reject(name):
    p, q, r, c = fixture()
    mutate(name, r)
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


@pytest.mark.parametrize("seam", (False, True))
def test_foreign_support_entries_and_both_foreign_branches_are_retained(seam):
    p, q, r, c = fixture()
    x = copy.deepcopy(r["edges"][0]["representations"][1])
    x.update(index=2, surface_index=1, owner_roles=())
    if seam:
        x["is_closed_surface"] = True
        x["is_regularity"] = True
        x["representation_type"] = "BRep_CurveOnClosedSurface"
        x["pcurves"] += (copy.deepcopy(x["pcurves"][0]),)
    r["edges"][0]["representations"] += (x,)
    before = copy.deepcopy(r)
    check(p, q, r, c)
    assert r == before


@pytest.mark.parametrize("field", ("shape_location", "surface_location"))
def test_face_support_placement_is_observed_and_applied_once(field):
    p, q, r, c = fixture()
    r["faces"][0][field] = location((0.0, 0.0, 7.0))
    with pytest.raises(NativePlanError, match="native_generated_location_changed"):
        check(p, q, r, c)


@pytest.mark.parametrize("where", ("record", "vertices", "point", "height", "orientation"))
def test_callback_capable_types_and_boolean_numeric_aliases_reject(where):
    p, q, r, c = fixture()

    class BadDict(dict):
        def __eq__(self, other):
            raise AssertionError("callback executed")

    class BadTuple(tuple):
        def __eq__(self, other):
            raise AssertionError("callback executed")

    if where == "record":
        r = BadDict(r)
    elif where == "vertices":
        r["vertices"] = BadTuple(r["vertices"])
    elif where == "point":
        r["vertices"][0]["point"] = BadTuple(r["vertices"][0]["point"])
    elif where == "height":
        r["height"] = True
    else:
        r["faces"][0]["orientation"] = True
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


def test_projected_cell_boundary_is_strict_independently_of_delta():
    p, q, r, c = fixture()
    rad = p.final_cell_radius
    # Homogeneous displacement n/k lies exactly on the original cell boundary.
    with pytest.raises(NativePlanError, match="native_generated_projected_cell_failure"):
        _generated_cell(c, (rad.numerator, Dyadic(0, 0), Dyadic(0, 0)), rad.denominator, rad)
    # Exact Delta equality is inclusive. It does not relax strict cell membership.
    _generated_delta(c, (Dyadic(1, 0), Dyadic(0, 0), Dyadic(0, 0)), c._make(10**9, 0))


def test_detached_projected_residual_matches_independent_rational_arithmetic():
    p, q, r, c = fixture(center=(17.0, -29.0), angle=0.4, sweep=2.0, gap=2**-31)
    out = check(p, q, r, c)
    by_side = {x["role"]: x for x in r["faces"]}
    by_edge = {x["role"]: x for x in r["edges"]}

    def exact(x):
        return Fraction(x[0]) * Fraction(2) ** x[1]

    for witness in out["inferred_planar_projections"]:
        face = by_side[witness["side_role"]]
        edge = by_edge[witness["edge_role"]]
        cv = edge["representations"][0]["curve3d"]
        idx = edge["endpoint_ids"].index(witness["endpoint_id"])
        t = Fraction(edge["range"][idx])
        x = tuple(
            Fraction(a) + t * Fraction(d) + Fraction(row[3])
            for a, d, row in zip(
                cv["location"], cv["direction"], edge["location"]["matrix"], strict=True
            )
        )
        surface = face["surface_fields"]
        u = tuple(map(Fraction, surface["u"]))
        v = tuple(map(Fraction, surface["v"]))
        w = tuple(a - Fraction(b) for a, b in zip(x, surface["origin"], strict=True))
        a = sum(z * z for z in u)
        b = sum(i * j for i, j in zip(w, u, strict=True))
        height = sum(i * j for i, j in zip(w, v, strict=True))
        residual = tuple(
            a * z - b * ui - a * height * vi for z, ui, vi in zip(w, u, v, strict=True)
        )
        assert tuple(map(exact, witness["residual_numerator"])) == residual
        assert exact(witness["denominator"]) == a
        assert 10**18 * sum(z * z for z in residual) <= a * a


def test_existing_evidence_functions_match_immutable_snapshot7_spans():
    path = Path(__file__).resolve().parents[2] / "src/mechanical_cad/arc_profile_native_evidence.py"
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    actual = {}
    for node in ast.parse(raw).body:
        if (
            isinstance(node, (ast.FunctionDef, ast.ClassDef))
            and node.name in SNAPSHOT7_EVIDENCE_SPANS
        ):
            first = min([node.lineno, *[decorator.lineno for decorator in node.decorator_list]])
            actual[node.name] = hashlib.sha256(
                b"".join(lines[first - 1 : node.end_lineno])
            ).hexdigest()
    assert actual == SNAPSHOT7_EVIDENCE_SPANS


def test_projection_outside_cell_rejects_even_when_q_and_radial_endpoint_are_inside():
    from mechanical_cad.arc_profile_native_evidence import (
        _generated_plane_endpoint,
        _generated_projection,
    )
    from mechanical_cad.arc_profile_sector_policy import ExactRatio

    c = PrimitiveContext()
    zero, one = Dyadic(0, 0), Dyadic(1, 0)
    rho, offset = Dyadic(1, -31), Dyadic(3, -33)
    radius = ExactRatio(rho, one)
    authored, q, radial = (zero, offset, zero), (offset, offset, zero), (zero, zero, zero)
    # Both actual finite endpoints are strictly inside this authored-centered
    # cell. Projection is a separate mathematical point with its own obligation.
    _generated_cell(c, (offset, zero, zero), one, radius)
    _generated_cell(c, (zero, c._neg(offset), zero), one, radius)
    residual, vertical = _generated_projection(
        c, q, radial, (one, zero, zero), (zero, zero, c._neg(one)), one
    )
    assert vertical == zero and residual == (zero, offset, zero)
    projected = (offset, zero, zero)
    with pytest.raises(NativePlanError, match="native_generated_projected_cell_failure"):
        _generated_plane_endpoint(c, q, projected, one, q, authored, True, radius)


@pytest.mark.parametrize("where", ("cylinder", "plane"))
def test_nonaffine_endpoint_impostor_cannot_establish_a_whole_trace(where):
    p, q, r, c = fixture()
    if where == "plane":
        planar_branches(p, q, r)
        edge = next(edge for edge in r["edges"] if edge["role"] == "base.line.ra")
        entry = edge["representations"][1]
    else:
        entry = r["edges"][0]["representations"][1]
    branch = entry["pcurves"][0]
    entry["pcurves"] = (
        curve(
            "circle",
            branch["location"],
            None,
            branch["range"],
            ident=branch["identity_location"],
            u=(1.0, 0.0),
            v=(0.0, 1.0),
            r=1.0,
        ),
    )
    with pytest.raises(NativePlanError, match="native_generated_nonaffine_trace"):
        check(p, q, r, c)


def test_plane_axis_positive_scaling_is_exactly_allowed_but_angle_change_is_not():
    p, q, r, c = fixture()
    face = next(face for face in r["faces"] if face["role"] == "side.line.ra")
    face["surface_fields"]["normal"] = tuple(
        2.0 * component for component in face["surface_fields"]["normal"]
    )
    check(p, q, r, c)
    face["surface_fields"]["normal"] = (math.ulp(0.0), 2.0, 0.0)
    with pytest.raises(NativePlanError, match="native_generated_surface_fields_changed"):
        check(p, q, r, c)


def test_generated_inventory_limits_are_unchanged():
    p, q, r, c = fixture()
    edge = r["edges"][0]
    original = edge["representations"][1]
    entries = list(edge["representations"])
    for index in range(2, 9):
        item = copy.deepcopy(original)
        item.update(index=index, surface_index=index - 1, owner_roles=())
        entries.append(item)
    edge["representations"] = tuple(entries)
    with pytest.raises(NativePlanError, match="native_representation_limit"):
        check(p, q, r, c)
