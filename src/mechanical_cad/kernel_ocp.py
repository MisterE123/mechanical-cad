"""Small OCCT adapter. Native shapes and builders never cross the worker boundary.

The document owns feature identity; OCCT owns exact B-rep geometry. Display meshes
and geometric signatures are disposable. Semantic names below come from explicit
construction and operation history, never face enumeration or nearest geometry.
This adapter deliberately does not claim arbitrary persistent topological naming.
"""

from __future__ import annotations

import math
import platform
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from itertools import product
from pathlib import Path
from typing import Any

import OCP
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_Copy,
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Transform,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.collections import Array1_gp_Pnt, List_TopoDS_Shape
from OCP.Geom import Geom_BezierCurve
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane
from OCP.gp import gp_Ax1, gp_Ax2, gp_Circ, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Standard import Standard_Failure
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.StlAPI import StlAPI_Writer
from OCP.TopAbs import (
    TopAbs_COMPOUND,
    TopAbs_COMPSOLID,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_REVERSED,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
    TopAbs_WIRE,
)
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Iterator, TopoDS_Shape

from .errors import CADException


class KernelError(ValueError):
    """A modeling operation did not produce the requested valid geometry."""


class _ExtrusionEndFaceError(CADException, KernelError):
    """A recognized end-face rejection, not an arbitrary native failure.

    Retain KernelError compatibility for direct adapter callers while giving
    replay a typed, bounded reference-repair signal.
    """

    def __init__(self, message: str) -> None:
        super().__init__("invalid_extrusion_end_face", message)


class _AssemblyQueryError(KernelError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class _Operation:
    shape: TopoDS_Shape
    kind: str
    builder: Any = None
    inputs: dict[str, TopoDS_Shape] = field(default_factory=dict)
    boundaries: dict[str, TopoDS_Shape] = field(default_factory=dict)
    faces: list[tuple[TopoDS_Shape, dict[str, Any]]] = field(default_factory=list)
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    profile_u: tuple[float, float, float] | None = None
    shell_openings: tuple[str, ...] = ()
    blend_edge: TopoDS_Shape | None = None
    blend_faces: tuple[str, ...] = ()
    blend_selections: list = field(default_factory=list)
    pattern_sources: list = field(default_factory=list)
    boolean_copies: list = field(default_factory=list)


def _number(value: float, name: str, *, positive: bool = False) -> float:
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise KernelError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        qualifier = "positive finite" if positive else "finite"
        raise KernelError(f"{name} must be a {qualifier} number")
    return result


def _profile_plane(origin, quaternion, *, strict: bool = False):
    """Temporary normalized origin/U/V/normal; authored quaternion stays untouched."""
    if (
        not isinstance(origin, (tuple, list))
        or not isinstance(quaternion, (tuple, list))
        or len(origin) != 3
        or len(quaternion) != 4
    ):
        raise KernelError("Profile plane requires a 3D origin and unit quaternion")
    if strict:
        origin = tuple(_query_number(value, "plane origin", bound=1e6) for value in origin)
        rotation = tuple(
            _query_number(value, "plane quaternion", bound=1.00000001) for value in quaternion
        )
    else:
        # Preserve the legacy polygon adapter's accepted numeric inputs.
        origin = tuple(_number(value, "plane origin") for value in origin)
        rotation = tuple(_number(value, "plane quaternion") for value in quaternion)
    norm = sum(value * value for value in rotation)
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise KernelError("Profile plane quaternion must have unit length")
    w, x, y, z = (value / math.sqrt(norm) for value in rotation)
    u = (1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y))
    v = (2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x))
    normal = (2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y))
    return origin, u, v, normal


def _subshapes(shape: TopoDS_Shape, kind: Any) -> list[TopoDS_Shape]:
    result: list[TopoDS_Shape] = []
    explorer = TopExp_Explorer(shape, kind)
    while explorer.More():
        item = explorer.Current()
        if not any(item.IsSame(previous) for previous in result):
            result.append(item)
        explorer.Next()
    return result


def _query_number(value: Any, name: str, *, bound: float, positive: bool = False) -> float:
    """Assembly adapter inputs are strict JSON numbers, never booleans/strings."""
    if type(value) not in (int, float):
        raise KernelError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise KernelError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or abs(result) > bound or (positive and result <= 0):
        raise KernelError(
            f"{name} must be finite, within +/-{bound:g}, and {'positive' if positive else 'bounded'}"
        )
    return result


def _assembly_step_inputs(assembly_name, parts, instances):
    """Validate detached assembly records before native allocation or file access."""

    def text(value, label, limit=256):
        if type(value) is not str or not value or len(value) > limit or "\x00" in value:
            raise KernelError(f"{label} requires nonempty text up to {limit} characters")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise KernelError(f"{label} contains invalid Unicode") from exc

    def records(values, keys, label):
        if type(values) not in (list, tuple) or not 1 <= len(values) <= 16:
            raise KernelError(f"Assembly STEP requires 1-16 {label} records")
        seen = set()
        for row in values:
            if type(row) is not dict or set(row) != keys:
                raise KernelError(f"Assembly STEP {label} fields must be {sorted(keys)}")
            text(row["id"], f"{label} ID", 128)
            text(row["name"], f"{label} name")
            if row["id"] in seen:
                raise KernelError(f"Duplicate Assembly STEP {label} ID: {row['id']}")
            seen.add(row["id"])
        return {row["id"]: row for row in values}

    text(assembly_name, "Assembly name")
    definitions = records(parts, {"id", "name", "shape"}, "Part")
    occurrences = records(instances, {"id", "name", "part_id", "frame"}, "instance")
    placements = {}
    for instance_id, instance in occurrences.items():
        text(instance["part_id"], "Referenced Part ID", 128)
        if instance["part_id"] not in definitions:
            raise KernelError(f"Missing Assembly STEP Part definition: {instance['part_id']}")
        frame = instance["frame"]
        if isinstance(frame, dict):
            if set(frame) != {"xyz_mm", "wxyz"}:
                raise KernelError("Frame requires exactly xyz_mm and wxyz")
            xyz, quaternion = frame["xyz_mm"], frame["wxyz"]
        else:
            xyz, quaternion = getattr(frame, "xyz_mm", None), getattr(frame, "wxyz", None)
        # This shares the existing strict, normalized rigid-frame calculation;
        # neither authored frames nor exact local shapes are transformed here.
        origin, u, v, normal = _profile_plane(xyz, quaternion, strict=True)
        placements[instance_id] = tuple(
            coordinate for i in range(3) for coordinate in (u[i], v[i], normal[i], origin[i])
        )
    return definitions, occurrences, placements


def _shape_bounds(shape: TopoDS_Shape) -> tuple[float, ...]:
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, False)
    if bounds.IsVoid() or bounds.IsWhole() or bounds.IsOpen():
        raise _AssemblyQueryError("invalid_bounds", "Solid has no finite geometric bounds")
    # OCP 8.0's Get() returns an unregistered Bnd_Box::Limits binding type.
    result = (*bounds.CornerMin().Coord(), *bounds.CornerMax().Coord())
    if any(not math.isfinite(value) for value in result):
        raise _AssemblyQueryError("invalid_bounds", "Solid has non-finite geometric bounds")
    return result


def _exact_volume(shape: TopoDS_Shape) -> float:
    # A local reference also avoids large-origin inertia/volume cancellation.
    bounds = _shape_bounds(shape)
    center = tuple(bounds[i] / 2 + bounds[i + 3] / 2 for i in range(3))
    properties = GProp_GProps(gp_Pnt(*center))
    BRepGProp.VolumeProperties_s(shape, properties, True, False, False)
    result = properties.Mass()
    if not math.isfinite(result):
        raise _AssemblyQueryError("invalid_volume", "Solid volume is not finite")
    return result


def _boundary(shape: TopoDS_Shape) -> TopoDS_Compound:
    """No solid containers: extrema must measure surfaces even in containment."""
    result, builder = TopoDS_Compound(), BRep_Builder()
    builder.MakeCompound(result)
    for face in _subshapes(shape, TopAbs_FACE):
        builder.Add(result, face)
    return result


def _copy_transform(shape: TopoDS_Shape, transform: gp_Trsf) -> TopoDS_Shape:
    builder = BRepBuilderAPI_Transform(shape, transform, True, False)
    if not builder.IsDone():
        raise _AssemblyQueryError("transform_failed", "OCCT rigid-copy transform failed")
    return builder.Shape()


def _diagnostic(exc: Exception, stage: str) -> dict[str, str]:
    return {"code": getattr(exc, "code", f"{stage}_failed"), "message": str(exc)[:500]}


def _surface_signature(shape: TopoDS_Shape) -> dict[str, Any]:
    face = TopoDS.Face(shape)
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    surface = BRepAdaptor_Surface(face)
    surface_type = surface.GetType()
    signature: dict[str, Any] = {
        "surface": str(surface_type).split("GeomAbs_")[-1].lower(),
        "area": props.Mass(),
        "centroid": list(props.CentreOfMass().Coord()),
    }
    if surface_type == GeomAbs_Plane:
        normal = surface.Plane().Axis().Direction().Coord()
        orientation = -1 if face.Orientation() == TopAbs_REVERSED else 1
        # Reflections can produce an indirect plane frame: its UV derivative
        # cross product is then opposite the stored axis. Use the oriented
        # surface normal, not the axis alone, for supports and connectors.
        if not surface.Plane().Position().Direct():
            orientation *= -1
        signature["normal"] = [orientation * value for value in normal]
    elif surface_type == GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        signature["radius"] = cylinder.Radius()
        signature["axis"] = list(cylinder.Axis().Direction().Coord())
        signature["axis_origin"] = list(cylinder.Axis().Location().Coord())
    return signature


def check_watertight_mesh(mesh: dict[str, Any], weld_tolerance: float = 1e-7) -> dict[str, Any]:
    """Check an oriented closed triangle 2-manifold after numerical seam welding.

    This is a topological export gate, not a self-intersection or engineering
    certification. Welding only defines this check; it never changes the B-rep.
    False negatives for very small features or near-coincident shells are safer
    than quietly repairing geometry. Coordinates/tolerance are millimetres.
    """
    tolerance = _number(weld_tolerance, "weld_tolerance", positive=True)
    vertices: list[tuple[float, float, float]] = []
    buckets: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    remap: list[int] = []
    for item in mesh["vertices"]:
        if len(item) != 3:
            raise KernelError("Mesh vertices must have three coordinates")
        point = tuple(_number(value, "mesh coordinate") for value in item)
        cell = tuple(math.floor(value / tolerance) for value in point)
        matching = None
        for offset in product((-1, 0, 1), repeat=3):
            neighbor = tuple(cell[axis] + offset[axis] for axis in range(3))
            for candidate in buckets.get(neighbor, ()):
                if math.dist(point, vertices[candidate]) <= tolerance:
                    matching = candidate
                    break
            if matching is not None:
                break
        if matching is None:
            matching = len(vertices)
            vertices.append(point)
            buckets[cell].append(matching)
        remap.append(matching)

    edges: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    links: dict[int, list[tuple[int, int]]] = defaultdict(list)
    triangles: set[tuple[int, int, int]] = set()
    signed_volume = 0.0
    origin = vertices[0] if vertices else (0.0, 0.0, 0.0)
    for item in mesh["triangles"]:
        if len(item) != 3 or any(
            type(index) is not int or not 0 <= index < len(remap) for index in item
        ):
            raise KernelError("Mesh contains an invalid triangle index")
        a, b, c = (remap[index] for index in item)
        if len({a, b, c}) != 3:
            raise KernelError("Mesh has a collapsed triangle after numerical welding")
        key = tuple(sorted((a, b, c)))
        if key in triangles:
            raise KernelError("Mesh has duplicate triangles")
        triangles.add(key)
        pa, pb, pc = vertices[a], vertices[b], vertices[c]
        ab = tuple(pb[axis] - pa[axis] for axis in range(3))
        ac = tuple(pc[axis] - pa[axis] for axis in range(3))
        normal = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        if sum(value * value for value in normal) <= tolerance**4:
            raise KernelError("Mesh has a zero-area or numerically collapsed triangle")
        # Translation-invariant local coordinates prevent catastrophic volume
        # cancellation for small parts placed far from the global origin.
        la, lb, lc = (
            tuple(point[axis] - origin[axis] for axis in range(3)) for point in (pa, pb, pc)
        )
        cross = (
            lb[1] * lc[2] - lb[2] * lc[1],
            lb[2] * lc[0] - lb[0] * lc[2],
            lb[0] * lc[1] - lb[1] * lc[0],
        )
        signed_volume += sum(la[axis] * cross[axis] for axis in range(3)) / 6
        for start, end in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted((start, end)))].append((start, end))
        links[a].append((b, c))
        links[b].append((c, a))
        links[c].append((a, b))
    if not triangles:
        raise KernelError("Mesh contains no triangles")
    for uses in edges.values():
        if len(uses) != 2 or uses[0] != uses[1][::-1]:
            raise KernelError("Mesh is not watertight with consistently oriented manifold edges")
    # Edge multiplicity alone misses two surfaces pinched at one shared vertex.
    for segments in links.values():
        adjacency: dict[int, list[int]] = defaultdict(list)
        for a, b in segments:
            adjacency[a].append(b)
            adjacency[b].append(a)
        if any(len(neighbors) != 2 for neighbors in adjacency.values()):
            raise KernelError("Mesh has a non-manifold vertex link")
        pending, visited = [next(iter(adjacency))], set()
        while pending:
            vertex = pending.pop()
            if vertex not in visited:
                visited.add(vertex)
                pending.extend(adjacency[vertex])
        if len(visited) != len(adjacency):
            raise KernelError("Mesh has a pinched non-manifold vertex")
    if not math.isfinite(signed_volume) or signed_volume <= tolerance**3:
        raise KernelError("Mesh has nonpositive oriented volume")
    return {
        "watertight": True,
        "consistently_oriented": True,
        "vertex_manifold": True,
        "vertices": len(vertices),
        "triangles": len(triangles),
        "signed_volume": signed_volume,
        "weld_tolerance": tolerance,
    }


@dataclass
class _CurveProfileState:
    shape: Any
    source: Any
    plan: Any
    context: Any
    vertices: dict[str, Any]
    edges: dict[str, Any]
    surface: Any
    area: float
    evidence: dict[str, Any]


class _CurveProfileError(KernelError):
    def __init__(self, code, evidence):
        super().__init__(code)
        self.code = code
        self.evidence = evidence


def _curve_profile_curve_record(curve, parameter_range, identity_location, dimensions):
    from .arc_profile_native_plan import NativePlanError

    kind = curve.DynamicType().Name()
    if kind == ("Geom_Line" if dimensions == 3 else "Geom2d_Line"):
        line = curve.Lin() if dimensions == 3 else curve.Lin2d()
        result = {
            "kind": "line",
            "location": tuple(line.Location().Coord()),
            "direction": tuple(line.Direction().Coord()),
            "u": None,
            "v": None,
            "normal": None,
            "radius": None,
        }
    elif kind == ("Geom_Circle" if dimensions == 3 else "Geom2d_Circle"):
        circle = curve.Circ() if dimensions == 3 else curve.Circ2d()
        axes = circle.Position()
        result = {
            "kind": "circle",
            "location": tuple(circle.Location().Coord()),
            "direction": None,
            "u": tuple(axes.XDirection().Coord()),
            "v": tuple(axes.YDirection().Coord()),
            "normal": tuple(axes.Direction().Coord()) if dimensions == 3 else None,
            "radius": circle.Radius(),
        }
    else:
        raise NativePlanError("native_curve_kind_changed")
    result.update(range=tuple(parameter_range), identity_location=identity_location)
    return result


def _curve_profile_location_record(location):
    matrix = location.Transformation()
    return {
        "identity": location.IsIdentity(),
        "matrix": tuple(
            tuple(matrix.Value(row, column) for column in range(1, 5)) for row in range(1, 4)
        ),
    }


def _curve_profile_surface_record(surface):
    from .arc_profile_native_plan import NativePlanError

    kind = surface.DynamicType().Name()
    if kind == "Geom_Plane":
        support, radius = surface.Pln(), None
    elif kind == "Geom_CylindricalSurface":
        support = surface.Cylinder()
        radius = support.Radius()
    else:
        raise NativePlanError("unsupported_native_surface_metadata")
    axes = support.Position()
    return {
        "kind": kind,
        "origin": tuple(support.Location().Coord()),
        "u": tuple(axes.XDirection().Coord()),
        "v": tuple(axes.YDirection().Coord()),
        "normal": tuple(axes.Direction().Coord()),
        "radius": radius,
    }


def _curve_profile_end_cap_record(profile, first, last, retained_surface, actual_vector, height):
    """Observe raw placement before the separate translated-instance predicates."""
    is_null = last.IsNull()
    shape_type = None if is_null else last.ShapeType()
    surface, surface_location, surface_type, surface_fields = None, None, None, None
    if not is_null and shape_type == TopAbs_FACE:
        location = TopLoc_Location()
        surface = BRep_Tool.Surface_s(TopoDS.Face(last), location)
        surface_location = _curve_profile_location_record(location)
        surface_type = surface.DynamicType().Name()
        if surface_type == "Geom_Plane":
            surface_fields = _curve_profile_surface_record(surface)
    return {
        "shape_type": None if shape_type is None else int(shape_type),
        "is_null": is_null,
        "orientation": None if is_null else int(last.Orientation()),
        "profile_orientation": int(profile.Orientation()),
        "first_is_equal": first.IsEqual(profile),
        "shape_location": None if is_null else _curve_profile_location_record(last.Location()),
        "surface_location": surface_location,
        "surface_type": surface_type,
        "surface_fields": surface_fields,
        "surface_is_retained": surface is retained_surface,
        "is_partner": last.IsPartner(profile),
        "is_same": last.IsSame(profile),
        "is_equal": last.IsEqual(profile),
        "actual_vector": actual_vector,
        "height": height,
    }


def _curve_profile_representation_inventory(edge, surface):
    from .arc_profile_native_plan import _require

    records, native, surfaces = [], [], []
    for index, rep in enumerate(edge.TShape().Curves()):
        _require(index < 8, "native_representation_limit")
        is3d, on_surface, closed = (
            rep.IsCurve3D(),
            rep.IsCurveOnSurface(),
            rep.IsCurveOnClosedSurface(),
        )
        kind = rep.DynamicType().Name()
        _require(
            (is3d, on_surface, closed, kind)
            in (
                (True, False, False, "BRep_Curve3D"),
                (False, True, False, "BRep_CurveOnSurface"),
                (False, True, True, "BRep_CurveOnClosedSurface"),
            ),
            "unsupported_native_representation_metadata",
        )
        location = _curve_profile_location_record(rep.Location())
        parameters = tuple(rep.Range())
        owner = rep.Surface() if on_surface else None
        owner_index = None
        if on_surface:
            matches = [k for k, known in enumerate(surfaces) if known is owner]
            if not matches:
                surfaces.append(owner)
                matches = [len(surfaces) - 1]
            owner_index = matches[0]
        branches = ()
        if on_surface:
            curves = (rep.PCurve(), rep.PCurve2()) if closed else (rep.PCurve(),)
            branches = tuple(
                _curve_profile_curve_record(curve, parameters, location["identity"], 2)
                for curve in curves
            )
        records.append(
            {
                "index": index,
                "representation_type": kind,
                "is_curve3d": is3d,
                "is_on_surface": on_surface,
                "is_closed_surface": closed,
                "surface_index": owner_index,
                "surface_is_retained": on_surface and owner is surface,
                "surface_fields": _curve_profile_surface_record(owner) if on_surface else None,
                "location": location,
                "range": parameters,
                "curve3d": _curve_profile_curve_record(
                    rep.Curve3D(), parameters, location["identity"], 3
                )
                if is3d
                else None,
                "pcurves": branches,
            }
        )
        native.append(rep)
    return tuple(records), tuple(native)


def _curve_profile_edge_record(
    plan,
    role,
    edge,
    expected_edge,
    vertices,
    expected_ids,
    expected_orientation,
    surface,
    *,
    retained_circle=None,
):
    from OCP.TopExp import TopExp

    from .arc_profile_native_plan import NativePlanError

    inventory, representations = _curve_profile_representation_inventory(edge, surface)
    curves = [item for item in inventory if item["is_curve3d"]]
    pcurves = [item for item in inventory if item["is_on_surface"]]
    retained = [item for item in pcurves if item["surface_is_retained"]]
    if len(curves) != 1:
        raise NativePlanError("native_evidence_incomplete")
    curve_rep = representations[curves[0]["index"]]
    curve = curve_rep.Curve3D()
    record3d = _curve_profile_curve_record(
        curve, curve_rep.Range(), curve_rep.Location().IsIdentity(), 3
    )
    first, last = TopExp.FirstVertex_s(edge, True), TopExp.LastVertex_s(edge, True)
    expected_vertices = tuple(vertices[identifier] for identifier in expected_ids)
    observed_ids = []
    for vertex in (first, last):
        matches = [
            identifier for identifier, original in vertices.items() if original.IsSame(vertex)
        ]
        observed_ids.append(matches[0] if len(matches) == 1 else "?")
    parameters = tuple(BRep_Tool.Parameter_s(vertex, edge) for vertex in (first, last))
    evaluated = tuple(curve.Value(parameter) for parameter in parameters)
    points = tuple(BRep_Tool.Pnt_s(vertex) for vertex in (first, last))
    selected = retained[0] if len(retained) == 1 else None
    record2d = (
        selected["pcurves"][0]
        if selected is not None and not selected["is_closed_surface"]
        else None
    )
    stored_owner = selected is not None
    result = {
        "role": role,
        "curve": record3d,
        "pcurve": record2d,
        "stored_pcurve_count": len(pcurves),
        "stored_representation_count": len(inventory),
        "retained_pcurve_count": len(retained),
        "selected_pcurve_index": selected["index"] if selected is not None else None,
        "representations": inventory,
        "pcurve_surface_matches": stored_owner,
        "orientation": int(edge.Orientation()),
        "expected_orientation": expected_orientation,
        "endpoint_ids": tuple(observed_ids),
        "expected_endpoint_ids": tuple(expected_ids),
        "vertex_identity_matches": all(
            a.IsSame(b) for a, b in zip((first, last), expected_vertices, strict=True)
        ),
        "edge_identity_matches": edge.IsSame(expected_edge),
        "vertex_coordinates": tuple(tuple(point.Coord()) for point in points),
        "vertex_parameters": parameters,
        "edge_tolerance": BRep_Tool.Tolerance_s(edge),
        "vertex_tolerances": tuple(BRep_Tool.Tolerance_s(vertex) for vertex in (first, last)),
        "locations_identity": edge.Location().IsIdentity()
        and all(v.Location().IsIdentity() for v in (first, last)),
        "evaluated_endpoints": tuple(tuple(point.Coord()) for point in evaluated),
        "observed_distances": tuple(a.Distance(b) for a, b in zip(evaluated, points, strict=True)),
        "equation_bounds_transfer": True,
    }
    if retained_circle is not None:
        result["curve_support_identity_matches"] = (
            curve is retained_circle if role == f"arc.{plan.source.incidence.arc.id}" else True
        )
    return result


def _curve_profile_children(shape):
    items = []
    iterator = TopoDS_Iterator(shape)
    while iterator.More():
        items.append(iterator.Value())
        iterator.Next()
    return items


def _curve_profile_face_snapshot(
    plan, face, wire, surface, vertices, edges, expected, *, retained_circle=None
):
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_WIRE

    from .arc_profile_native_plan import _require

    _require(
        face.Location().IsIdentity() and wire.Location().IsIdentity(), "native_location_changed"
    )
    location = TopLoc_Location()
    actual_surface = BRep_Tool.Surface_s(face, location)
    _require(location.IsIdentity() and actual_surface is surface, "native_face_surface_changed")
    _require(actual_surface.DynamicType().Name() == "Geom_Plane", "native_face_surface_changed")
    plane = actual_surface.Pln()
    axes = plane.Position()
    actual_plane = {
        "origin": tuple(plane.Location().Coord()),
        "u": tuple(axes.XDirection().Coord()),
        "v": tuple(axes.YDirection().Coord()),
        "normal": tuple(axes.Direction().Coord()),
    }
    _require(
        actual_plane
        == {
            "origin": plan.frame.origin,
            "u": plan.frame.u,
            "v": plan.frame.v,
            "normal": plan.frame.normal,
        },
        "native_face_fields_changed",
    )
    children = _curve_profile_children(face)
    _require(
        len(children) == 1 and children[0].ShapeType() == TopAbs_WIRE and children[0].IsSame(wire),
        "native_wire_identity_changed",
    )
    _require(BRepTools.OuterWire_s(face).IsSame(wire), "native_material_side_ambiguous")
    _require(
        int(face.Orientation()) == 0 and int(children[0].Orientation()) == 0,
        "native_material_side_ambiguous",
    )
    occurrences = _curve_profile_children(children[0])
    _require(
        len(occurrences) == 3 and all(s.ShapeType() == TopAbs_EDGE for s in occurrences),
        "native_edge_count_changed",
    )
    _require(len(_subshapes(face, TopAbs_VERTEX)) == 3, "native_vertex_identity_changed")
    explorer = BRepTools_WireExplorer(TopoDS.Wire(children[0]), face)
    ordered = []
    observations = []
    while explorer.More():
        edge = explorer.Current()
        matches = [role for role, original in edges.items() if original.IsSame(edge)]
        _require(len(matches) == 1, "native_edge_identity_changed")
        role = matches[0]
        ordered.append(role)
        endpoint_ids, orientation = expected[role]
        observations.append(
            _curve_profile_edge_record(
                plan,
                role,
                edge,
                edges[role],
                vertices,
                endpoint_ids,
                orientation,
                actual_surface,
                retained_circle=retained_circle,
            )
        )
        explorer.Next()
    wanted = list(expected)
    _require(
        len(ordered) == 3 and any(ordered == wanted[k:] + wanted[:k] for k in range(3)),
        "native_ordered_boundary_changed",
    )
    _require(len(set(ordered)) == 3, "native_repeated_edge")
    return {
        "plane": actual_plane,
        "face_orientation": int(face.Orientation()),
        "wire_orientation": int(children[0].Orientation()),
        "wire_count": len(children),
        "ordered_roles": ordered,
        "stored_pcurve_associations": "actual_BRep_TEdge_Curves_on_face_surface",
        "material_side": "positive_ordered_outer_wire_on_retained_oriented_plane",
        "edges": observations,
    }


def _curve_profile_native_type_record(value):
    from .arc_profile_native_plan import _require

    cls = type(value)
    module, name = cls.__module__, cls.__qualname__
    _require(
        type(module) is str
        and type(name) is str
        and 1 <= len(module) <= 128
        and 1 <= len(name) <= 128,
        "native_type_metadata_unavailable",
    )
    return {"module": module, "qualname": name}


def _curve_profile_generated_children(shape, limit, *, cumulative, event, label):
    """Fixed direct occurrence traversal; no geometry-aware ordering or projection."""
    from .arc_profile_native_plan import _require

    items = []
    iterator = TopoDS_Iterator(shape, cumulative, cumulative)
    while iterator.More():
        if len(items) == limit:
            event("raw_generated_collection_overflow", {"label": label, "limit": limit})
            _require(False, "native_generated_cardinality_changed")
        items.append(iterator.Value())
        iterator.Next()
    return tuple(items)


def _curve_profile_regularity_type_record(value):
    """Read actual type metadata without invoking a foreign metaclass hook."""
    from .arc_profile_native_plan import _require

    cls = type(value)
    module = type.__dict__["__module__"].__get__(cls)
    name = type.__dict__["__qualname__"].__get__(cls)
    _require(
        type(module) is str
        and type(name) is str
        and 1 <= len(module) <= 128
        and 1 <= len(name) <= 128,
        "native_type_metadata_unavailable",
    )
    return {"module": module, "qualname": name}


def _curve_profile_generated_regularity_record(
    rep, owners, surfaces, item, records, *, event, label
):
    """Collect only stored advisory metadata; never query a geometric range."""
    from .arc_profile_native_plan import _require

    payload = {
        "surface1": None,
        "surface2": None,
        "location2": None,
        "continuity_value": None,
        "continuity_name": None,
        "continuity_type": None,
    }
    item["regularity"] = payload
    field = "enum_type_binding"
    try:
        from OCP.GeomAbs import GeomAbs_Shape

        for name in ("surface1", "surface2"):
            field = name
            getter = rep.Surface if name == "surface1" else rep.Surface2
            owner = getter()
            slot = {
                "surface_index": None,
                "owner_roles": tuple(role for role, known in owners.items() if known is owner),
                "surface_fields": None,
            }
            payload[name] = slot
            field = f"{name}.type"
            kind = None if owner is None else owner.DynamicType().Name()
            slot["surface_fields"] = {"kind": kind}
            _require(
                type(kind) is str and kind in ("Geom_Plane", "Geom_CylindricalSurface"),
                "unsupported_native_surface_metadata",
            )
            field = f"{name}.fields"
            slot["surface_fields"] = _curve_profile_surface_record(owner)
            matches = [index for index, known in enumerate(surfaces) if known is owner]
            if not matches:
                field = f"{name}.surface_index"
                _require(len(surfaces) < 8, "native_representation_limit")
                surfaces.append(owner)
                matches = [len(surfaces) - 1]
            slot["surface_index"] = matches[0]
        field = "location2"
        payload["location2"] = _curve_profile_location_record(rep.Location2())
        field = "continuity"
        continuity = rep.Continuity()
        field = "continuity_type"
        payload["continuity_type"] = _curve_profile_regularity_type_record(continuity)
        _require(type(continuity) is GeomAbs_Shape, "invalid_native_regularity_enum")
        field = "continuity_value"
        value = int(continuity)
        payload["continuity_value"] = value
        names = (
            "GeomAbs_C0",
            "GeomAbs_G1",
            "GeomAbs_C1",
            "GeomAbs_G2",
            "GeomAbs_C2",
            "GeomAbs_C3",
            "GeomAbs_CN",
        )
        _require(type(value) is int and 0 <= value < len(names), "invalid_native_regularity_enum")
        payload["continuity_name"] = names[value]
    except Exception as exc:
        event(
            "raw_generated_regularity_metadata_failure",
            {
                "role": label,
                "unavailable_field": field,
                "exception_type": _curve_profile_regularity_type_record(exc),
                "representations": tuple(records) + (item,),
            },
        )
        raise
    return payload


def _curve_profile_generated_inventory(edge, owners, *, event, label):
    """Retain every bounded stored record, including foreign owners and branches."""
    from .arc_profile_native_plan import _require

    records, surfaces = [], []
    for index, rep in enumerate(edge.TShape().Curves()):
        if index == 8:
            event(
                "raw_generated_inventory_overflow",
                {"role": label, "representations": tuple(records)},
            )
            _require(False, "native_representation_limit")
        is3d, on_surface, closed = (
            rep.IsCurve3D(),
            rep.IsCurveOnSurface(),
            rep.IsCurveOnClosedSurface(),
        )
        kind = rep.DynamicType().Name()
        item = {
            "index": index,
            "representation_type": kind,
            "is_curve3d": is3d,
            "is_on_surface": on_surface,
            "is_closed_surface": closed,
            "is_regularity": None,
            "regularity": None,
            "surface_index": None,
            "surface_is_retained": False,
            "surface_fields": None,
            "location": _curve_profile_location_record(rep.Location()),
            "range": (),
            "curve3d": None,
            "pcurves": (),
            "owner_roles": (),
        }
        try:
            item["is_regularity"] = rep.IsRegularity()
        except Exception as exc:
            event(
                "raw_generated_regularity_metadata_failure",
                {
                    "role": label,
                    "unavailable_field": "IsRegularity",
                    "exception_type": _curve_profile_regularity_type_record(exc),
                    "representations": tuple(records) + (item,),
                },
            )
            raise
        regularity = item["is_regularity"]
        supported = (
            type(kind) is str
            and all(type(flag) is bool for flag in (is3d, on_surface, closed, regularity))
            and (
                is3d,
                on_surface,
                closed,
                regularity,
                kind,
            )
            in (
                (True, False, False, False, "BRep_Curve3D"),
                (False, True, False, False, "BRep_CurveOnSurface"),
                (False, True, True, True, "BRep_CurveOnClosedSurface"),
                (False, False, False, True, "BRep_CurveOn2Surfaces"),
            )
        )
        if not supported:
            records.append(item)
            event(
                "raw_generated_unsupported_representation",
                {"role": label, "representations": tuple(records)},
            )
            _require(False, "unsupported_native_representation_metadata")
        if kind == "BRep_CurveOn2Surfaces":
            _curve_profile_generated_regularity_record(
                rep, owners, surfaces, item, records, event=event, label=label
            )
            records.append(item)
            continue
        parameters = tuple(rep.Range())
        item["range"] = parameters
        if on_surface:
            owner = rep.Surface()
            matches = [k for k, known in enumerate(surfaces) if known is owner]
            if not matches:
                if len(surfaces) == 8:
                    records.append(item)
                    event(
                        "raw_generated_inventory_overflow",
                        {"role": label, "representations": tuple(records)},
                    )
                    _require(False, "native_representation_limit")
                surfaces.append(owner)
                matches = [len(surfaces) - 1]
            item["surface_index"] = matches[0]
            item["owner_roles"] = tuple(role for role, known in owners.items() if known is owner)
            item["surface_is_retained"] = "retained_profile_plane" in item["owner_roles"]
            owner_kind = owner.DynamicType().Name()
            item["surface_fields"] = {"kind": owner_kind}
            if owner_kind not in ("Geom_Plane", "Geom_CylindricalSurface"):
                records.append(item)
                event(
                    "raw_generated_unsupported_surface",
                    {"role": label, "representations": tuple(records)},
                )
                _require(False, "unsupported_native_surface_metadata")
            item["surface_fields"] = _curve_profile_surface_record(owner)
            curves = (rep.PCurve(), rep.PCurve2()) if closed else (rep.PCurve(),)
            branches = []
            for curve in curves:
                curve_kind = None if curve is None else curve.DynamicType().Name()
                if curve_kind not in ("Geom2d_Line", "Geom2d_Circle"):
                    item["pcurves"] = tuple(branches)
                    records.append(item)
                    event(
                        "raw_generated_unsupported_curve",
                        {
                            "role": label,
                            "curve_kind": curve_kind,
                            "representations": tuple(records),
                        },
                    )
                    _require(False, "native_curve_kind_changed")
                branches.append(
                    _curve_profile_curve_record(curve, parameters, item["location"]["identity"], 2)
                )
            item["pcurves"] = tuple(branches)
        else:
            curve = rep.Curve3D()
            curve_kind = None if curve is None else curve.DynamicType().Name()
            if curve_kind not in ("Geom_Line", "Geom_Circle"):
                records.append(item)
                event(
                    "raw_generated_unsupported_curve",
                    {"role": label, "curve_kind": curve_kind, "representations": tuple(records)},
                )
                _require(False, "native_curve_kind_changed")
            item["curve3d"] = _curve_profile_curve_record(
                curve, parameters, item["location"]["identity"], 3
            )
        records.append(item)
    return tuple(records)


def _curve_profile_generated_trace_record(
    plan, state, builder, shape, solid_faces, roles, height, vector, event
):
    """Collect only the fixed three side faces and their shared nine-edge graph."""
    from OCP.TopAbs import TopAbs_WIRE
    from OCP.TopExp import TopExp

    from .arc_profile_native_plan import _require

    arc = plan.source.incidence.arc
    point_ids = (arc.center_id, arc.start_id, arc.end_id)
    profile_roles = tuple(f"{use.kind}.{use.entity_id}" for use in plan.source.boundary)
    vertex_handles, vertex_records = {}, []
    for level in ("base", "top"):
        for point_id in point_ids:
            original = state.vertices[point_id]
            history = (
                builder.FirstShape(original) if level == "base" else builder.LastShape(original)
            )
            identifier = f"{level}.{point_id}"
            raw = {"id": identifier, "is_null": history.IsNull(), "shape_type": None}
            if not raw["is_null"]:
                raw["shape_type"] = int(history.ShapeType())
            if raw["is_null"] or history.ShapeType() != TopAbs_VERTEX:
                event("raw_generated_vertex_history", raw)
                _require(False, "native_generated_identity_changed")
            vertex = TopoDS.Vertex(original if level == "base" else history)
            matches = history.IsSame(original) if level == "base" else history.IsPartner(original)
            item = {
                "id": identifier,
                "point": tuple(BRep_Tool.Pnt_s(vertex).Coord()),
                "tolerance": BRep_Tool.Tolerance_s(vertex),
                "location": _curve_profile_location_record(vertex.Location()),
                "history_matches": matches,
            }
            event("raw_generated_vertex", item)
            vertex_handles[identifier] = vertex
            vertex_records.append(item)
    _require(
        all(
            not a.IsSame(b)
            for k, a in enumerate(vertex_handles.values())
            for b in tuple(vertex_handles.values())[k + 1 :]
        ),
        "native_generated_identity_changed",
    )

    def endpoint_ids(edge, oriented):
        result = []
        for vertex in (TopExp.FirstVertex_s(edge, oriented), TopExp.LastVertex_s(edge, oriented)):
            matches = (
                []
                if vertex.IsNull()
                else [
                    identifier for identifier, held in vertex_handles.items() if held.IsSame(vertex)
                ]
            )
            result.append(matches[0] if len(matches) == 1 else "?")
        return tuple(result)

    edge_handles = {}
    for level in ("base", "top"):
        for role in profile_roles:
            original = state.edges[role]
            held = builder.FirstShape(original) if level == "base" else builder.LastShape(original)
            raw = {"role": f"{level}.{role}", "is_null": held.IsNull(), "shape_type": None}
            if not raw["is_null"]:
                raw["shape_type"] = int(held.ShapeType())
            if (
                raw["is_null"]
                or held.ShapeType() != TopAbs_EDGE
                or (level == "base" and not held.IsSame(original))
            ):
                event("raw_generated_edge_history", raw)
                _require(False, "native_generated_identity_changed")
            edge_handles[f"{level}.{role}"] = TopoDS.Edge(held)
    owners = {"retained_profile_plane": state.surface}
    held_faces = []
    for role in profile_roles:
        side_role, generated = f"side.{role}", roles[f"side.{role}"]
        matches = [face for face in solid_faces if face.IsSame(generated)]
        raw = {
            "role": side_role,
            "actual_face_match_count": len(matches),
            "generated_orientation": int(generated.Orientation()),
        }
        if len(matches) != 1:
            event("raw_generated_face_association", raw)
            _require(False, "native_generated_identity_changed")
        face = TopoDS.Face(matches[0])
        location = TopLoc_Location()
        surface = BRep_Tool.Surface_s(face, location)
        surface_kind = None if surface is None else surface.DynamicType().Name()
        raw.update(
            orientation=int(face.Orientation()),
            surface_type=surface_kind,
            shape_location=_curve_profile_location_record(face.Location()),
            surface_location=_curve_profile_location_record(location),
        )
        if surface_kind not in ("Geom_Plane", "Geom_CylindricalSurface"):
            event("raw_generated_face_support", raw)
            _require(False, "native_generated_surface_fields_changed")
        owners[side_role] = surface
        local_wires = _curve_profile_generated_children(
            face, 1, cumulative=False, event=event, label=side_role
        )
        wires = _curve_profile_generated_children(
            face, 1, cumulative=True, event=event, label=side_role
        )
        if (
            len(wires) != 1
            or len(local_wires) != 1
            or wires[0].ShapeType() != TopAbs_WIRE
            or not wires[0].IsPartner(local_wires[0])
        ):
            event(
                "raw_generated_face_topology",
                {**raw, "wire_count": len(wires), "local_wire_count": len(local_wires)},
            )
            _require(False, "native_generated_cardinality_changed")
        # Local orientations come from the local wire, never from an already
        # face-composed wire whose orientation would be applied twice.
        local_edges = _curve_profile_generated_children(
            local_wires[0], 4, cumulative=False, event=event, label=side_role
        )
        edges = _curve_profile_generated_children(
            wires[0], 4, cumulative=True, event=event, label=side_role
        )
        if len(edges) != 4 or len(local_edges) != 4:
            event(
                "raw_generated_face_topology",
                {**raw, "edge_count": len(edges), "local_edge_count": len(local_edges)},
            )
            _require(False, "native_generated_cardinality_changed")
        occurrences = []
        for local, occurrence in zip(local_edges, edges, strict=True):
            if occurrence.ShapeType() != TopAbs_EDGE or not occurrence.IsPartner(local):
                event(
                    "raw_generated_occurrence_mismatch",
                    {
                        **raw,
                        "shape_type": int(occurrence.ShapeType()),
                        "partner": occurrence.IsPartner(local),
                    },
                )
                _require(False, "native_generated_identity_changed")
            edge = TopoDS.Edge(occurrence)
            matches = [key for key, held in edge_handles.items() if held.IsSame(edge)]
            if not matches:
                ids = endpoint_ids(edge, False)
                vertical = [
                    point_id
                    for point_id in point_ids
                    if ids == (f"base.{point_id}", f"top.{point_id}")
                ]
                if len(vertical) == 1:
                    edge_role = f"vertical.{vertical[0]}"
                    if edge_role in edge_handles:
                        event(
                            "raw_generated_split_vertical",
                            {
                                "role": edge_role,
                                "endpoint_ids": ids,
                                "existing_is_same": edge_handles[edge_role].IsSame(edge),
                            },
                        )
                        _require(False, "native_generated_identity_changed")
                    edge_handles[edge_role] = edge
                    matches = [edge_role]
            edge_role = matches[0] if len(matches) == 1 else "?"
            occurrences.append(
                {
                    "edge_role": edge_role,
                    "local_orientation": int(local.Orientation()),
                    "orientation": int(occurrence.Orientation()),
                    "endpoint_ids": endpoint_ids(edge, True),
                }
            )
        item = {
            "role": side_role,
            "generated_is_same": generated.IsSame(face),
            "generated_is_equal": generated.IsEqual(face),
            "generated_is_partner": generated.IsPartner(face),
            "generated_orientation": int(generated.Orientation()),
            "orientation": int(face.Orientation()),
            "shape_location": _curve_profile_location_record(face.Location()),
            "surface_location": _curve_profile_location_record(location),
            "surface_fields": _curve_profile_surface_record(surface),
            "wire_local_orientation": int(local_wires[0].Orientation()),
            "wire_orientation": int(wires[0].Orientation()),
            "occurrences": tuple(occurrences),
        }
        event("raw_generated_face", item)
        held_faces.append(item)
    expected_edge_roles = tuple(
        f"{level}.{role}" for level in ("base", "top") for role in profile_roles
    ) + tuple(f"vertical.{point_id}" for point_id in point_ids)
    _require(set(edge_handles) == set(expected_edge_roles), "native_generated_cardinality_changed")
    _require(
        all(
            not a.IsSame(b)
            for k, a in enumerate(edge_handles.values())
            for b in tuple(edge_handles.values())[k + 1 :]
        ),
        "native_generated_identity_changed",
    )
    edge_records = []
    for role in expected_edge_roles:
        edge = edge_handles[role]
        occurrence_count = sum(
            item["edge_role"] == role for face in held_faces for item in face["occurrences"]
        )
        item = {
            "role": role,
            "location": _curve_profile_location_record(edge.Location()),
            "range": tuple(BRep_Tool.Range_s(edge)),
            "endpoint_ids": endpoint_ids(edge, False),
            "tolerance": BRep_Tool.Tolerance_s(edge),
            "identity_matches": occurrence_count == (2 if role.startswith("vertical.") else 1),
            "representations": _curve_profile_generated_inventory(
                edge, owners, event=event, label=role
            ),
        }
        event("raw_generated_edge", item)
        edge_records.append(item)
    return {
        "height": height,
        "actual_vector": vector,
        "vertices": tuple(vertex_records),
        "edges": tuple(edge_records),
        "faces": tuple(held_faces),
    }


class OCPKernel:
    """A millimetre-based B-rep kernel with conservative operation provenance.

    Positive rectangle dimensions extend from (x,y,z) in local +X/+Y. Profiles
    lie in XY; signed extrusion length is along Z. This explicit initial scope
    avoids pretending to support arbitrary sketch workplanes.
    """

    def __init__(self, *, cut_tool_lineage: bool = False) -> None:
        self._operations: dict[int, _Operation] = {}
        self._cut_tool_lineage = cut_tool_lineage
        self._selected_blend_lineage = False
        self._pattern_face_lineage = False
        self._shell_surface_lineage = False

    def set_topology_result_version(self, result_version: int) -> None:
        """Keep legacy replay topology unchanged; typed consumers opt in."""
        if type(result_version) is not int or result_version not in (1, 2, 3):
            raise KernelError("Unsupported topology result version")
        self._cut_tool_lineage = result_version >= 2
        self._selected_blend_lineage = result_version >= 2
        self._pattern_face_lineage = result_version >= 2
        self._shell_surface_lineage = result_version >= 2

    def _remember(self, operation: _Operation) -> TopoDS_Shape:
        # Each record strongly retains its shape: Python id cannot be recycled
        # while this kernel/document evaluation is alive.
        self._operations[id(operation.shape)] = operation
        return operation.shape

    @staticmethod
    def _validate(shape: TopoDS_Shape, *, solid: bool = False) -> None:
        if (
            not isinstance(shape, TopoDS_Shape)
            or shape.IsNull()
            or not BRepCheck_Analyzer(shape, True, False, True).IsValid()
        ):
            raise KernelError("OCCT produced a null or invalid B-rep")
        if solid and not _subshapes(shape, TopAbs_SOLID):
            raise KernelError("The operation produced no solid")

    def sector_profile(self, sketch, *, context=None, evidence_sink=None):
        """Fresh bounded sector construction; no caller plan/certificate is accepted."""
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.Geom import Geom_Circle, Geom_Line, Geom_Plane
        from OCP.Geom2d import Geom2d_Circle, Geom2d_Line
        from OCP.gp import gp_Ax2d, gp_Ax3, gp_Dir2d, gp_Pnt2d
        from OCP.TopoDS import TopoDS_Face

        from .arc_profile_native_evidence import (
            bounded_evidence_bytes,
            check_masses,
            mass_check_record,
            validate_curve_fields,
            validate_edge_observation,
            validate_initial_curve_fields,
        )
        from .arc_profile_native_plan import (
            NativeEndpointObservation,
            NativePlane,
            NativeRadialDirection,
            _continue_actual_support_for_vertices,
            _continue_native_plan,
            _continue_vertex_representation,
            _require,
            entry_context,
            plan_bytes,
            transform,
            vertex_representation_bytes,
        )
        from .arc_profile_sector import certificate_bytes, classify_sector

        c = entry_context(context)
        start = c.operations
        evidence = {"events": [], "operation": "curve_profile", "operations_start": start}

        def event(stage, value):
            item = {"stage": stage, "value": value, "operations": c.operations}
            candidate = dict(evidence)
            candidate["events"] = [*evidence["events"], item]
            bounded_evidence_bytes(candidate)
            evidence["events"].append(item)
            if evidence_sink is not None:
                import json

                evidence_sink(json.loads(json.dumps(evidence["events"][-1], allow_nan=False)))

        try:
            source = classify_sector(sketch, context=c)
            _require(source.status == "certified_sector", source.code)
            certificate = source.certificate
            evidence["source_json"] = certificate.source_json
            evidence["source_sha256"] = certificate.source_sha256
            event("fresh_source_certificate", certificate_bytes(certificate).decode("ascii"))
            event(
                "source_resource_lineage",
                {
                    "entry_absolute_start": start,
                    "source_absolute_end": c.operations,
                    "core_source_delta": c.operations - start,
                    "shared_source_absolute_start": certificate.geometry.resources.operations_start,
                    "shared_source_delta": c.operations
                    - certificate.geometry.resources.operations_start,
                    "original_source_ceiling": 100_000,
                    "aggregate_ceiling": c.max_operations,
                },
            )
            plan = _continue_native_plan(
                certificate.geometry,
                NativePlane(sketch.plane.origin, sketch.plane.quaternion),
                c,
                operations_start=start,
            )
            event("frozen_native_plan", plan_bytes(plan).decode("ascii"))
            actual_frame = _profile_plane(sketch.plane.origin, sketch.plane.quaternion, strict=True)
            _require(
                actual_frame == (plan.frame.origin, plan.frame.u, plan.frame.v, plan.frame.normal),
                "unsupported_native_frame",
            )
            axes = gp_Ax3(
                gp_Pnt(*plan.frame.origin), gp_Dir(*plan.frame.normal), gp_Dir(*plan.frame.u)
            )
            surface = Geom_Plane(axes)
            arc = plan.source.incidence.arc
            circle = Geom_Circle(
                gp_Circ(
                    gp_Ax2(
                        gp_Pnt(*transform(plan.frame, plan.center)),
                        gp_Dir(*plan.frame.normal),
                        gp_Dir(*plan.frame.u),
                    ),
                    plan.radius,
                )
            )
            arc_role = f"arc.{arc.id}"
            support = _curve_profile_curve_record(circle, plan.increasing_parameters, True, 3)
            event("circle_support", support)
            validate_initial_curve_fields(plan, arc_role, support)
            retained_circle = circle
            actual_directions, radial_curves = [], {}
            for line in plan.lines:
                role = f"line.{line.entity_id}"
                curve = Geom_Line(
                    gp_Pnt(*transform(plan.frame, plan.center)),
                    gp_Dir(*transform(plan.frame, line.direction)),
                )
                support = _curve_profile_curve_record(curve, (0.0, line.trim_parameter), True, 3)
                event("radial_support", {"role": role, **support})
                validate_initial_curve_fields(plan, role, support)
                actual_directions.append(
                    NativeRadialDirection(line.entity_id, support["direction"])
                )
                radial_curves[role] = curve
            plan, continuation = _continue_actual_support_for_vertices(
                plan, tuple(actual_directions), c
            )
            event("fresh_actual_support_proof", plan_bytes(plan).decode("ascii"))
            observations, representative_points = [], []
            for identifier, parameter in zip(
                (arc.start_id, arc.end_id), plan.parameters, strict=True
            ):
                point = circle.Value(parameter)
                representative_points.append(point)
                coordinates = tuple(point.Coord())
                event(
                    "raw_canonical_vertex_candidate",
                    {
                        "point_id": identifier,
                        "parameter": parameter,
                        "world_point": coordinates,
                        "parameter_hex": parameter.hex(),
                        "world_point_hex": tuple(value.hex() for value in coordinates),
                        "point_object_id": id(point),
                        "point_type": _curve_profile_native_type_record(point),
                        "circle_object_id": id(circle),
                        "circle_type": _curve_profile_native_type_record(circle),
                        "circle_is_verified_support": circle is retained_circle,
                    },
                )
                _require(type(point) is gp_Pnt, "native_circle_evaluation_type_changed")
                observations.append(NativeEndpointObservation(identifier, parameter, coordinates))
            observations = tuple(observations)
            representative_points = tuple(representative_points)
            representatives = _continue_vertex_representation(
                plan, observations, c, continuation=continuation
            )
            event(
                "fresh_native_vertex_mapping",
                vertex_representation_bytes(representatives).decode("ascii"),
            )
            vertices = {
                identifier: BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
                for identifier, point in representatives.vertices
            }
            vertex_snapshot = {
                identifier: {
                    "point": tuple(BRep_Tool.Pnt_s(vertex).Coord()),
                    "tolerance": BRep_Tool.Tolerance_s(vertex),
                    "identity_location": vertex.Location().IsIdentity(),
                }
                for identifier, vertex in vertices.items()
            }
            event("canonical_native_vertices", vertex_snapshot)
            _require(
                len(vertices) == 3
                and all(
                    not a.IsSame(b)
                    for k, a in enumerate(vertices.values())
                    for b in list(vertices.values())[k + 1 :]
                ),
                "native_vertex_identity_changed",
            )
            for identifier, point in representatives.vertices:
                value = vertex_snapshot[identifier]
                _require(
                    value["point"] == point
                    and value["identity_location"]
                    and 0 <= value["tolerance"] <= 1e-7,
                    "native_vertex_changed",
                )
            ids = (
                (arc.start_id, arc.end_id)
                if plan.parameters[1] > plan.parameters[0]
                else (arc.end_id, arc.start_id)
            )
            maker = BRepBuilderAPI_MakeEdge(
                circle, vertices[ids[0]], vertices[ids[1]], *plan.increasing_parameters
            )
            _require(maker.IsDone(), "native_arc_constructor_failed")
            raw = {arc_role: maker.Edge()}
            raw_expected = {arc_role: (ids, 0)}
            pc = Geom2d_Circle(
                gp_Ax2d(gp_Pnt2d(*plan.center), gp_Dir2d(1.0, 0.0)), plan.radius, True
            )
            pcurves = {arc_role: pc}
            for line in plan.lines:
                role = f"line.{line.entity_id}"
                curve = radial_curves[role]
                maker = BRepBuilderAPI_MakeEdge(
                    curve,
                    vertices[arc.center_id],
                    vertices[line.point_id],
                    0.0,
                    line.trim_parameter,
                )
                _require(maker.IsDone(), "native_line_constructor_failed")
                raw[role] = maker.Edge()
                raw_expected[role] = ((arc.center_id, line.point_id), 0)
                pcurves[role] = Geom2d_Line(gp_Pnt2d(*plan.center), gp_Dir2d(*line.direction))
            low = BRep_Builder()
            for role, edge in raw.items():
                endpoint_ids, orientation = raw_expected[role]
                observation = _curve_profile_edge_record(
                    plan,
                    role,
                    edge,
                    edge,
                    vertices,
                    endpoint_ids,
                    orientation,
                    surface,
                    retained_circle=retained_circle,
                )
                event("raw_edge", observation)
                validate_edge_observation(
                    plan,
                    role,
                    observation,
                    context=c,
                    traversal="support",
                    representatives=representatives,
                )
                pc_record = _curve_profile_curve_record(
                    pcurves[role], observation["curve"]["range"], True, 2
                )
                validate_curve_fields(plan, role, pc_record, dimensions=2)
                low.UpdateEdge(edge, pcurves[role], surface, TopLoc_Location(), 1e-7)
                low.Range(edge, surface, TopLoc_Location(), *observation["curve"]["range"])
                observation = _curve_profile_edge_record(
                    plan,
                    role,
                    edge,
                    edge,
                    vertices,
                    endpoint_ids,
                    orientation,
                    surface,
                    retained_circle=retained_circle,
                )
                event("inserted_pcurve", observation)
                validate_edge_observation(
                    plan,
                    role,
                    observation,
                    context=c,
                    traversal="support",
                    pcurve_required=True,
                    representatives=representatives,
                )
            wire_builder = BRepBuilderAPI_MakeWire()
            edges, expected = {}, {}
            for use in plan.source.boundary:
                role = f"{use.kind}.{use.entity_id}"
                endpoint_ids = (use.start_id, use.end_id)
                edge = raw[role]
                orientation = 0
                if raw_expected[role][0] != endpoint_ids:
                    _require(
                        tuple(reversed(raw_expected[role][0])) == endpoint_ids,
                        "native_boundary_plan_mismatch",
                    )
                    edge = TopoDS.Edge(edge.Reversed())
                    orientation = 1
                wire_builder.Add(edge)
                _require(wire_builder.IsDone(), "native_wire_constructor_failed")
                edges[role] = wire_builder.Edge()
                expected[role] = (endpoint_ids, orientation)
                for inserted_role, inserted_edge in edges.items():
                    insertion_ids, insertion_orientation = expected[inserted_role]
                    observation = _curve_profile_edge_record(
                        plan,
                        inserted_role,
                        inserted_edge,
                        raw[inserted_role],
                        vertices,
                        insertion_ids,
                        insertion_orientation,
                        surface,
                        retained_circle=retained_circle,
                    )
                    event("wire_insertion", observation)
                    validate_edge_observation(
                        plan,
                        inserted_role,
                        observation,
                        context=c,
                        traversal="boundary",
                        pcurve_required=True,
                        representatives=representatives,
                    )
            wire = wire_builder.Wire()
            face = TopoDS_Face()
            low.MakeFace(face, surface, 1e-7)
            low.Add(face, wire)
            snapshot = _curve_profile_face_snapshot(
                plan,
                face,
                wire,
                surface,
                vertices,
                edges,
                expected,
                retained_circle=retained_circle,
            )
            event("face_owned_representation", snapshot)
            for observation in snapshot["edges"]:
                validate_edge_observation(
                    plan,
                    observation["role"],
                    observation,
                    context=c,
                    traversal="boundary",
                    pcurve_required=True,
                    representatives=representatives,
                )
            self._validate(face)
            mass = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, mass)
            area = mass.Mass()
            event("raw_face_empirical_area", {"area": area})
            area_check = check_masses(plan, area, context=c)
            event(
                "face_empirical_area",
                {
                    "area": area,
                    "exact_comparison": mass_check_record(area_check),
                    "r0_pass": True,
                    "equation_reference_class": "planned_simple_local_completions",
                    "kernel_integration_error_theorem": False,
                },
            )
            evidence["operations_end"] = c.operations
            bounded_evidence_bytes(evidence)
            state = _CurveProfileState(
                face, certificate, plan, c, vertices, edges, surface, area, evidence
            )
            state.circle = retained_circle
            state.representative_points = representative_points
            state.representatives = representatives
            state.representative_continuation = continuation
            state.expected = expected
            state.wire = wire
            states = self.__dict__.setdefault("_curve_profile_states", {})
            states[id(face)] = state
            self._remember(
                _Operation(
                    face,
                    "curve_profile",
                    boundaries=edges,
                    normal=plan.frame.normal,
                    profile_u=plan.frame.u,
                )
            )
            return face
        except Exception as exc:
            if getattr(exc, "code", None) in {"native_evidence_limit", "invalid_native_evidence"}:
                raise
            evidence["operations_end"] = c.operations
            evidence["failure"] = {
                "code": getattr(exc, "code", "native_evidence_incomplete"),
                "type": type(exc).__name__,
                "message": str(exc),
            }
            event("failure", evidence["failure"])
            raise _CurveProfileError(evidence["failure"]["code"], evidence) from exc

    def sector_evidence(self, shape):
        """Detached diagnostic evidence; it cannot create retained native state."""
        import copy

        from .arc_profile_native_evidence import bounded_evidence_bytes

        state = self.__dict__.get("_curve_profile_states", {}).get(id(shape))
        if type(state) is not _CurveProfileState or state.shape is not shape:
            raise KernelError("No retained checked sector state for this exact shape")
        bounded_evidence_bytes(state.evidence)
        return copy.deepcopy(state.evidence)

    def extrude_sector(self, profile, height, *, evidence_sink=None):
        """One checked prism, using the privately retained face/context provenance."""
        from .arc_profile_native_evidence import (
            bounded_evidence_bytes,
            check_masses,
            mass_check_record,
            mass_limits,
            native_height,
            validate_edge_observation,
            validate_end_cap_observation,
            validate_generated_trace_observation,
        )
        from .arc_profile_native_plan import _require

        states = self.__dict__.get("_curve_profile_states", {})
        state = states.get(id(profile))
        _require(
            type(state) is _CurveProfileState
            and state.shape is profile
            and self._operations[id(profile)].kind == "curve_profile",
            "unbound_sector_profile",
        )
        plan, c = state.plan, state.context
        _require(
            state.representative_continuation.plan is plan
            and state.representative_continuation.context is c
            and state.representative_continuation.operations_end
            == state.representatives.resources.operations_start
            and c.operations >= state.representatives.resources.operations_end
            and c.max_bits == state.representative_continuation.max_bits
            and c.max_operations == state.representative_continuation.max_operations,
            "native_context_discontinuity",
        )
        import copy

        evidence = copy.deepcopy(state.evidence)

        def event(stage, value):
            item = {"stage": stage, "value": value, "operations": c.operations}
            candidate = dict(evidence)
            candidate["events"] = [*evidence["events"], item]
            bounded_evidence_bytes(candidate)
            evidence["events"].append(item)
            if evidence_sink is not None:
                import json

                evidence_sink(json.loads(json.dumps(evidence["events"][-1], allow_nan=False)))

        try:
            height = native_height(height)
            snapshot = _curve_profile_face_snapshot(
                plan,
                profile,
                state.wire,
                state.surface,
                state.vertices,
                state.edges,
                state.expected,
                retained_circle=state.circle,
            )
            event("pre_extrusion_face", snapshot)
            for observation in snapshot["edges"]:
                validate_edge_observation(
                    plan,
                    observation["role"],
                    observation,
                    context=c,
                    traversal="boundary",
                    pcurve_required=True,
                    representatives=state.representatives,
                )
            from dataclasses import asdict

            limits = mass_limits(plan, height, context=c)
            event("frozen_extrusion_limits", [asdict(value) for value in limits])
            vector = tuple(height * part for part in plan.frame.normal)
            builder = BRepPrimAPI_MakePrism(profile, gp_Vec(*vector), False, True)
            _require(builder.IsDone(), "native_prism_constructor_failed")
            actual_vector = tuple(builder.Prism().Vec().Coord())
            _require(actual_vector == vector, "native_extrusion_vector_changed")
            shape = builder.Shape()
            self._validate(shape, solid=True)
            solids, faces = _subshapes(shape, TopAbs_SOLID), _subshapes(shape, TopAbs_FACE)
            _require(len(solids) == 1 and len(faces) == 5, "native_extrusion_topology_changed")
            first, last = builder.FirstShape(), builder.LastShape()
            _require(
                first.ShapeType() == TopAbs_FACE
                and last.ShapeType() == TopAbs_FACE
                and first.IsSame(profile),
                "native_cap_history_changed",
            )
            post_snapshot = _curve_profile_face_snapshot(
                plan,
                TopoDS.Face(first),
                state.wire,
                state.surface,
                state.vertices,
                state.edges,
                state.expected,
                retained_circle=state.circle,
            )
            event("post_extrusion_first_cap", post_snapshot)
            for observation in post_snapshot["edges"]:
                validate_edge_observation(
                    plan,
                    observation["role"],
                    observation,
                    context=c,
                    traversal="boundary",
                    pcurve_required=True,
                    representatives=state.representatives,
                )
            end_record = _curve_profile_end_cap_record(
                profile, first, last, state.surface, actual_vector, height
            )
            event("raw_last_cap_representation", end_record)
            end_fields = validate_end_cap_observation(plan, end_record, height=height, context=c)
            event("actual_last_cap_plane", end_fields)
            roles = {"cap.start": first, "cap.end": last}
            for role, edge in state.edges.items():
                generated = []
                for item in builder.Generated(edge):
                    if len(generated) == 2:
                        event("raw_generated_history_overflow", {"role": role, "limit": 2})
                        _require(False, "native_generated_history_changed")
                    generated.append(item)
                event(
                    "raw_generated_history",
                    {
                        "role": role,
                        "entries": tuple(
                            {
                                "shape_type": int(item.ShapeType()),
                                "orientation": int(item.Orientation()),
                            }
                            for item in generated
                        ),
                    },
                )
                _require(
                    len(generated) == 1 and generated[0].ShapeType() == TopAbs_FACE,
                    "native_generated_history_changed",
                )
                roles[f"side.{role}"] = generated[0]
            _require(
                all(sum(face.IsSame(item) for item in roles.values()) == 1 for face in faces)
                and all(sum(face.IsSame(item) for face in faces) == 1 for item in roles.values()),
                "native_split_merged_history",
            )
            for face in faces:
                for kind, cast in ((TopAbs_EDGE, TopoDS.Edge), (TopAbs_VERTEX, TopoDS.Vertex)):
                    for item in _subshapes(face, kind):
                        _require(
                            0 <= BRep_Tool.Tolerance_s(cast(item)) <= 1e-7,
                            "native_tolerance_exceeded",
                        )
            kinds = {role: _surface_signature(item)["surface"] for role, item in roles.items()}
            _require(
                kinds["cap.start"] == kinds["cap.end"] == "plane"
                and kinds[f"side.arc.{plan.source.incidence.arc.id}"] == "cylinder"
                and all(kinds[f"side.line.{line.entity_id}"] == "plane" for line in plan.lines),
                "native_extrusion_surface_changed",
            )
            event(
                "actual_prism_provenance",
                {
                    "vector": actual_vector,
                    "roles": list(roles),
                    "surface_kinds": kinds,
                    "first_shape_matches_profile": first.IsSame(profile),
                    "last_shape_matches_final_cap": any(last.IsSame(face) for face in faces),
                    "generated_from_actual_inserted_edges": True,
                    "face_count": len(faces),
                    "solid_count": len(solids),
                },
            )
            trace_record = _curve_profile_generated_trace_record(
                plan, state, builder, shape, faces, roles, height, actual_vector, event
            )
            trace_proof = validate_generated_trace_observation(
                plan, state.representatives, trace_record, height=height, context=c
            )
            event("generated_trace_proof", trace_proof)
            volume = _exact_volume(shape)
            event(
                "raw_prism_empirical_masses",
                {"area": state.area, "height": height, "volume": volume},
            )
            mass_check = check_masses(plan, state.area, context=c, height=height, volume=volume)
            event(
                "prism_empirical_masses",
                {
                    "area": state.area,
                    "height": height,
                    "volume_local": volume,
                    "exact_comparison": mass_check_record(mass_check),
                    "r0_pass": True,
                    "c0_pass": True,
                },
            )
            evidence["operations_end"] = c.operations
            bounded_evidence_bytes(evidence)
            self._remember(_Operation(shape, "extrude", builder, {"profile": profile}))
            solid_state = _CurveProfileState(
                shape,
                state.source,
                plan,
                c,
                state.vertices,
                state.edges,
                state.surface,
                state.area,
                evidence,
            )
            solid_state.circle = state.circle
            solid_state.representative_points = state.representative_points
            solid_state.representatives = state.representatives
            solid_state.representative_continuation = state.representative_continuation
            states[id(shape)] = solid_state
            return shape
        except Exception as exc:
            if getattr(exc, "code", None) in {"native_evidence_limit", "invalid_native_evidence"}:
                raise
            evidence["operations_end"] = c.operations
            evidence["failure"] = {
                "code": getattr(exc, "code", "native_evidence_incomplete"),
                "type": type(exc).__name__,
                "message": str(exc),
            }
            event("failure", evidence["failure"])
            raise _CurveProfileError(evidence["failure"]["code"], evidence) from exc

    def spur_gear(self, **params):
        """Bounded cubic involute flanks, analytic tip/root arcs and bore.

        Only caps and bore retain semantic provenance. Sampling segment indices
        are deliberately NOT stable face IDs when parameters/tolerance change.
        """
        from .spur_gear import gear_spec
        from .spur_gear_curves import flank_spans

        spec = gear_spec(**params)
        spans = flank_spans(spec)
        wire = BRepBuilderAPI_MakeWire()

        def polar(radius, angle):
            return gp_Pnt(radius * math.cos(angle), radius * math.sin(angle), 0)

        def radial(center, side):
            if spec.root_radius < spec.base_radius:
                angle = center + side * spec.root_half_angle
                start, end = polar(spec.root_radius, angle), polar(spec.base_radius, angle)
                wire.Add(
                    BRepBuilderAPI_MakeEdge(*((start, end) if side == -1 else (end, start))).Edge()
                )

        def arc(radius, start, end):
            circle = gp_Circ(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), radius)
            wire.Add(BRepBuilderAPI_MakeEdge(circle, start, end).Edge())

        for tooth in range(spec.tooth_count):
            center = 2 * math.pi * tooth / spec.tooth_count
            radial(center, -1)
            for side in (-1, 1):
                angle = center + side * spec.base_half_angle
                cosine, sine = math.cos(angle), math.sin(angle)
                for span in spans if side == -1 else reversed(spans):
                    poles = Array1_gp_Pnt(1, 4)
                    for i, (x, y) in enumerate(
                        span.poles if side == -1 else reversed(span.poles), 1
                    ):
                        y *= -side
                        poles.SetValue(i, gp_Pnt(cosine * x - sine * y, sine * x + cosine * y, 0))
                    wire.Add(BRepBuilderAPI_MakeEdge(Geom_BezierCurve(poles)).Edge())
                if side == -1:
                    arc(spec.tip_radius, center - spec.tip_half_angle, center + spec.tip_half_angle)
            radial(center, 1)
            arc(
                spec.root_radius,
                center + spec.root_half_angle,
                center + 2 * math.pi / spec.tooth_count - spec.root_half_angle,
            )
        if not wire.IsDone():
            raise KernelError("OCCT could not close the gear profile wire")
        builder = BRepBuilderAPI_MakeFace(wire.Wire())
        boundaries = {}
        if spec.bore_diameter:
            circle = gp_Circ(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), spec.bore_diameter / 2)
            bore = BRepBuilderAPI_MakeEdge(circle).Edge()
            hole = BRepBuilderAPI_MakeWire(bore).Wire()
            hole.Reverse()
            builder.Add(hole)
            boundaries["bore"] = bore
        profile = builder.Face()
        self._validate(profile)
        self._remember(
            _Operation(profile, "gear_profile", builder, boundaries=boundaries, profile_u=(1, 0, 0))
        )
        return self.extrude(profile, spec.thickness)

    def rectangle(
        self, width: float, height: float, x: float = 0, y: float = 0, z: float = 0
    ) -> TopoDS_Shape:
        width, height = (
            _number(width, "width", positive=True),
            _number(height, "height", positive=True),
        )
        x, y, z = (_number(value, name) for value, name in ((x, "x"), (y, "y"), (z, "z")))
        points = [
            gp_Pnt(x, y, z),
            gp_Pnt(x + width, y, z),
            gp_Pnt(x + width, y + height, z),
            gp_Pnt(x, y + height, z),
        ]
        wire = BRepBuilderAPI_MakeWire()
        boundaries = {}
        for index, role in enumerate(("y_min", "x_max", "y_max", "x_min")):
            edge = BRepBuilderAPI_MakeEdge(points[index], points[(index + 1) % 4]).Edge()
            wire.Add(edge)
            # MakeWire may replace the added edge's vertices to share the
            # existing wire's vertices. Retain the actual inserted edge.
            boundaries[role] = wire.Edge()
        builder = BRepBuilderAPI_MakeFace(wire.Wire())
        shape = builder.Face()
        self._validate(shape)
        return self._remember(
            _Operation(shape, "rectangle", builder, boundaries=boundaries, profile_u=(1, 0, 0))
        )

    def circle(self, radius: float, x: float = 0, y: float = 0, z: float = 0) -> TopoDS_Shape:
        radius = _number(radius, "radius", positive=True)
        x, y, z = (_number(value, name) for value, name in ((x, "x"), (y, "y"), (z, "z")))
        circle = gp_Circ(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1)), radius)
        edge = BRepBuilderAPI_MakeEdge(circle).Edge()
        builder = BRepBuilderAPI_MakeFace(BRepBuilderAPI_MakeWire(edge).Wire())
        shape = builder.Face()
        self._validate(shape)
        return self._remember(
            _Operation(shape, "circle", builder, boundaries={"circle": edge}, profile_u=(1, 0, 0))
        )

    def circle_profile(
        self,
        center: tuple,
        radius: float,
        circle_id: str,
        *,
        origin: tuple = (0.0, 0.0, 0.0),
        quaternion: tuple = (1.0, 0.0, 0.0, 0.0),
    ) -> TopoDS_Shape:
        """Exact solved disk, with explicit workplane +U as parameter zero.

        The whole circular boundary retains the authored circle identity. Its
        seam is a parameter convention, never a persistent authored edge role.
        """
        from .errors import CADException
        from .profile_region import validate_circle

        try:
            region = validate_circle(center, radius, circle_id)
        except CADException as exc:
            raise KernelError(str(exc)) from exc
        origin, u, v, normal = _profile_plane(origin, quaternion, strict=True)
        center_world = tuple(
            origin[axis] + region.center[0] * u[axis] + region.center[1] * v[axis]
            for axis in range(3)
        )
        circle = gp_Circ(gp_Ax2(gp_Pnt(*center_world), gp_Dir(*normal), gp_Dir(*u)), region.radius)
        edge_builder = BRepBuilderAPI_MakeEdge(circle)
        if not edge_builder.IsDone():
            raise KernelError("OCCT could not construct the circular sketch boundary")
        wire = BRepBuilderAPI_MakeWire(edge_builder.Edge())
        if not wire.IsDone():
            raise KernelError("OCCT could not construct the circular sketch wire")
        edge = wire.Edge()
        plane = gp_Pln(gp_Pnt(*origin), gp_Dir(*normal))
        builder = BRepBuilderAPI_MakeFace(plane, wire.Wire(), True)
        if not builder.IsDone():
            raise KernelError("OCCT could not construct the circular sketch face")
        shape = builder.Face()
        self._validate(shape)
        return self._remember(
            _Operation(
                shape,
                "circle_profile",
                builder,
                boundaries={f"circle.{circle_id}": edge},
                normal=normal,
                profile_u=u,
            )
        )

    def polygon(
        self,
        points: list | tuple,
        edge_ids: list | tuple,
        *,
        origin: tuple = (0.0, 0.0, 0.0),
        quaternion: tuple = (1.0, 0.0, 0.0, 0.0),
    ) -> TopoDS_Shape:
        """Build one simple planar line region with explicit boundary provenance.

        Input points are solved local-plane (u,v) coordinates. The unit quaternion
        is (w,x,y,z); extrusion follows that plane's normal. No geometric edge
        matching or automatic closing/repair is performed.
        """
        from .errors import CADException
        from .profile_region import validate_polygon

        try:
            region = validate_polygon(points, edge_ids)
        except CADException as exc:
            raise KernelError(str(exc)) from exc
        origin, u, v, normal = _profile_plane(origin, quaternion)
        vertices = [
            gp_Pnt(*(origin[axis] + a * u[axis] + b * v[axis] for axis in range(3)))
            for a, b in region.points
        ]
        wire = BRepBuilderAPI_MakeWire()
        boundaries = {}
        for index, identifier in enumerate(region.edge_ids):
            builder = BRepBuilderAPI_MakeEdge(
                vertices[index], vertices[(index + 1) % len(vertices)]
            )
            if not builder.IsDone():
                raise KernelError("OCCT could not construct a sketch boundary")
            wire.Add(builder.Edge())
            if not wire.IsDone():
                raise KernelError("OCCT could not connect the explicit sketch boundaries")
            boundaries[f"line.{identifier}"] = wire.Edge()
        # The workplane is authoritative. Avoid refitting a plane from a long,
        # thin wire, which can spuriously fail after harmless quaternion rounding.
        plane = gp_Pln(gp_Pnt(*origin), gp_Dir(*normal))
        builder = BRepBuilderAPI_MakeFace(plane, wire.Wire(), True)
        if not builder.IsDone():
            raise KernelError("OCCT could not construct the closed sketch face")
        shape = builder.Face()
        self._validate(shape)
        return self._remember(
            _Operation(shape, "polygon", builder, boundaries=boundaries, normal=normal, profile_u=u)
        )

    def support_face_signature(self, base, face_id, intent=None):
        """Current face evidence or explicitly saved logical-plane split intent.

        An inferred construction plane never changes native face identity.
        """
        from .support_intent import resolve_support_signature

        operation = self._operations.get(id(base))
        try:
            source = self._operations.get(id(operation.inputs.get("base"))) if operation else None
            signature, _ = resolve_support_signature(
                face_id,
                intent,
                [candidate for _, candidate in operation.faces] if operation else [],
                [candidate for _, candidate in source.faces] if source else [],
            )
            return {
                key: list(value) if isinstance(value, (list, tuple)) else value
                for key, value in signature.items()
            }
        except ValueError as exc:
            raise KernelError(str(exc)) from exc

    def supported_workplane(self, base, face_id, x=0, y=0, z=0, angle=0):
        """Resolve a stable planar face; centroid-centered deterministic world frame.

        X is projected world X, except near an X-facing normal where world Y
        is used. Local offsets and in-plane rotation follow the current face.
        """
        operation = self._operations.get(id(base))
        matches = (
            [
                (face, candidate)
                for face, candidate in operation.faces
                if candidate["id"] == face_id
                and candidate["provenance"]["semantic_status"] == "stable"
            ]
            if operation
            else []
        )
        if len(matches) != 1:
            raise KernelError(
                "Sketch support face is missing, split, or ambiguous; repair the reference"
            )
        face, _ = matches[0]
        surface = BRepAdaptor_Surface(TopoDS.Face(face))
        if surface.GetType() != GeomAbs_Plane:
            raise KernelError("Sketch support must be a planar face")
        signature = _surface_signature(face)
        normal = signature["normal"]
        reference = (0, 1, 0) if abs(normal[0]) > 0.9 else (1, 0, 0)
        dot = sum(reference[i] * normal[i] for i in range(3))
        u = tuple(reference[i] - dot * normal[i] for i in range(3))
        length = math.hypot(*u)
        u = tuple(value / length for value in u)
        v = (
            normal[1] * u[2] - normal[2] * u[1],
            normal[2] * u[0] - normal[0] * u[2],
            normal[0] * u[1] - normal[1] * u[0],
        )
        x, y, z, angle = (_number(value, "support placement") for value in (x, y, z, angle))
        origin = tuple(
            signature["centroid"][i] + x * u[i] + y * v[i] + z * normal[i] for i in range(3)
        )
        cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        rotated_u = tuple(cosine * u[i] + sine * v[i] for i in range(3))
        rotated_v = tuple(-sine * u[i] + cosine * v[i] for i in range(3))
        transform = gp_Trsf()
        transform.SetValues(
            *(
                value
                for i in range(3)
                for value in (rotated_u[i], rotated_v[i], normal[i], origin[i])
            )
        )
        rotation = transform.GetRotation()
        return origin, (rotation.W(), rotation.X(), rotation.Y(), rotation.Z())

    def face_rectangle(self, support, support_face, width, height, x=0, y=0, z=0, angle=0):
        origin, quaternion = self.supported_workplane(support, support_face, x, y, z, angle)
        width, height = (
            _number(width, "width", positive=True),
            _number(height, "height", positive=True),
        )
        shape = self.polygon(
            ((0, 0), (width, 0), (width, height), (0, height)),
            ("bottom", "right", "top", "left"),
            origin=origin,
            quaternion=quaternion,
        )
        operation = self._operations[id(shape)]
        operation.kind = "sketch_face_rectangle"
        operation.boundaries = {
            name: operation.boundaries[f"line.{source}"]
            for name, source in (
                ("x_min", "left"),
                ("x_max", "right"),
                ("y_min", "bottom"),
                ("y_max", "top"),
            )
        }
        return shape

    def face_circle(self, support, support_face, radius, x=0, y=0, z=0, angle=0):
        origin, quaternion = self.supported_workplane(support, support_face, x, y, z, angle)
        shape = self.circle_profile((0, 0), radius, "circle", origin=origin, quaternion=quaternion)
        operation = self._operations[id(shape)]
        operation.kind = "sketch_face_circle"
        operation.boundaries = {"circle": operation.boundaries["circle.circle"]}
        return shape

    def analytic_region_profile(self, regions, *, origin=(0, 0, 0), quaternion=(1, 0, 0, 0)):
        """Exact ordered lines/arcs/circles, with explicit islands and holes."""
        origin, u, v, normal = _profile_plane(origin, quaternion, strict=True)
        plane = gp_Pln(gp_Pnt(*origin), gp_Dir(*normal))
        boundaries = {}

        def world(point):
            return gp_Pnt(*(origin[i] + point[0] * u[i] + point[1] * v[i] for i in range(3)))

        def wire(loop):
            builder = BRepBuilderAPI_MakeWire()
            for boundary in loop.boundaries:
                if hasattr(boundary, "center"):
                    radius = math.dist(boundary.start, boundary.center)
                    circle = gp_Circ(
                        gp_Ax2(world(boundary.center), gp_Dir(*normal), gp_Dir(*u)), radius
                    )
                    sweep = _number(boundary.sweep, "arc sweep")
                    if not 1e-12 < abs(sweep) <= 2 * math.pi + 1e-10:
                        raise KernelError("Arc sweep must be nonzero and at most one turn")
                    start = math.atan2(
                        boundary.start[1] - boundary.center[1],
                        boundary.start[0] - boundary.center[0],
                    )
                    if abs(abs(sweep) - 2 * math.pi) <= 1e-10:
                        edge = BRepBuilderAPI_MakeEdge(circle).Edge()
                    else:
                        low, high = (start, start + sweep) if sweep > 0 else (start + sweep, start)
                        edge_builder = BRepBuilderAPI_MakeEdge(circle, low, high)
                        if not edge_builder.IsDone():
                            raise KernelError("OCCT could not construct the directed arc")
                        edge = edge_builder.Edge()
                    if sweep < 0:
                        edge = TopoDS.Edge(edge.Reversed())
                    role = f"{getattr(boundary, 'kind', 'arc')}.{boundary.entity_id}"
                else:
                    edge_builder = BRepBuilderAPI_MakeEdge(
                        world(boundary.start), world(boundary.end)
                    )
                    if not edge_builder.IsDone():
                        raise KernelError("OCCT could not construct the line boundary")
                    edge = edge_builder.Edge()
                    role = f"line.{boundary.entity_id}"
                if role in boundaries:
                    raise KernelError("Analytic profile boundary IDs must be unique")
                builder.Add(edge)
                if not builder.IsDone():
                    raise KernelError("Analytic boundaries do not form a connected wire")
                boundaries[role] = builder.Edge()
            return builder.Wire()

        faces = []
        for region in regions:
            builder = BRepBuilderAPI_MakeFace(plane, wire(region.outer), True)
            for hole in region.holes:
                builder.Add(TopoDS.Wire(wire(hole).Reversed()))
            if not builder.IsDone():
                raise KernelError("OCCT could not create the analytic profile region")
            face = builder.Face()
            self._validate(face)
            faces.append(face)
        if not faces:
            raise KernelError("At least one analytic profile region is required")
        if len(faces) == 1:
            shape = faces[0]
        else:
            shape, builder = TopoDS_Compound(), BRep_Builder()
            builder.MakeCompound(shape)
            for face in faces:
                builder.Add(shape, face)
        return self._remember(
            _Operation(shape, "analytic_regions", boundaries=boundaries, normal=normal, profile_u=u)
        )

    def region_profile(self, regions, *, origin=(0, 0, 0), quaternion=(1, 0, 0, 0)):
        """Explicit outer/inner loops; holes never become independent capped solids."""
        from .profile_region import CircleProfile

        origin, u, _, normal = _profile_plane(origin, quaternion, strict=True)
        plane = gp_Pln(gp_Pnt(*origin), gp_Dir(*normal))
        faces, boundaries = [], {}

        def make_wire(loop):
            if isinstance(loop, CircleProfile):
                face = self.circle_profile(
                    loop.center, loop.radius, loop.circle_id, origin=origin, quaternion=quaternion
                )
            else:
                face = self.polygon(
                    loop.points, loop.edge_ids, origin=origin, quaternion=quaternion
                )
            operation = self._operations[id(face)]
            if set(boundaries).intersection(operation.boundaries):
                raise KernelError("Profile boundary IDs must be unique across all regions")
            boundaries.update(operation.boundaries)
            return TopoDS.Wire(_subshapes(face, TopAbs_WIRE)[0])

        for region in regions:
            builder = BRepBuilderAPI_MakeFace(plane, make_wire(region.outer), True)
            for hole in region.holes:
                builder.Add(TopoDS.Wire(make_wire(hole).Reversed()))
            if not builder.IsDone():
                raise KernelError("OCCT could not build the profile holes")
            face = builder.Face()
            self._validate(face)
            faces.append(face)
        if not faces:
            raise KernelError("At least one closed profile region is required")
        if len(faces) == 1:
            shape = faces[0]
        else:
            shape, compound_builder = TopoDS_Compound(), BRep_Builder()
            compound_builder.MakeCompound(shape)
            for face in faces:
                compound_builder.Add(shape, face)
        return self._remember(
            _Operation(shape, "regions", boundaries=boundaries, normal=normal, profile_u=u)
        )

    def extrude(self, profile: TopoDS_Shape, length: float) -> TopoDS_Shape:
        length = _number(length, "length")
        if length == 0:
            raise KernelError("Extrusion length must be nonzero")
        self._validate(profile)
        operation = self._operations.get(id(profile))
        normal = operation.normal if operation else (0.0, 0.0, 1.0)
        builder = BRepPrimAPI_MakePrism(profile, gp_Vec(*(value * length for value in normal)))
        if not builder.IsDone():
            raise KernelError("OCCT could not construct the extrusion")
        shape = builder.Shape()
        self._validate(shape, solid=True)
        return self._remember(_Operation(shape, "extrude", builder, {"profile": profile}))

    def extrude_symmetric(self, profile, length):
        """Positive total depth centered on the authored profile's plane.

        Translate a native profile copy by half the total depth. Transfer each
        explicit authored boundary only through one-image native transform
        history, then retain ordinary prism provenance. This is a transient
        construction step, not a second saved sketch or guessed offset.
        """
        length = _number(length, "total depth", positive=True)
        self._validate(profile)
        original = self._operations.get(id(profile))
        if original is None:
            raise KernelError("Symmetric extrusion requires a known planar sketch normal")
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(*(-0.5 * length * value for value in original.normal)))
        builder = BRepBuilderAPI_Transform(profile, transform, True)
        if not builder.IsDone():
            raise KernelError("Could not position the symmetric extrusion profile")
        shifted = builder.Shape()
        self._validate(shifted)
        boundaries = {}
        for role, edge in original.boundaries.items():
            images = list(builder.Modified(edge))
            if len(images) == 1 and images[0].ShapeType() == TopAbs_EDGE:
                boundaries[role] = images[0]
        self._remember(
            _Operation(
                shifted, original.kind, builder, boundaries=boundaries, normal=original.normal
            )
        )
        return self.extrude(shifted, length)

    def extrude_to_face(self, profile, target, end_face, direction, offset=0):
        """Stop at an explicitly named parallel face plane, recomputed on replay.

        The selected finite face supplies an infinite construction plane. This
        does not trim to its outline or search for a nearby alternative. Positive
        offset extends past that plane along the explicitly selected direction.
        """
        if type(direction) not in (int, float) or direction not in (-1, 1):
            raise KernelError("Up to Face direction must be +1 or -1")
        offset = _number(offset, "Up to Face offset")
        if abs(offset) > 1e6:
            raise KernelError("Up to Face offset must be within ±1e6 mm")
        self._validate(target, solid=True)
        self._validate(profile)
        target_operation = self._operations.get(id(target))
        matches = (
            [
                (face, candidate)
                for face, candidate in target_operation.faces
                if candidate["id"] == end_face
            ]
            if target_operation
            else []
        )
        if len(matches) != 1 or matches[0][1]["provenance"]["semantic_status"] != "stable":
            raise _ExtrusionEndFaceError(
                "Up to Face end face is missing, split, or ambiguous; choose an exact stable face"
            )
        target_surface = BRepAdaptor_Surface(TopoDS.Face(matches[0][0]))
        if target_surface.GetType() != GeomAbs_Plane:
            raise _ExtrusionEndFaceError("Up to Face end face must be planar")
        operation = self._operations.get(id(profile))
        if operation is None or operation.normal is None:
            raise KernelError("Up to Face requires a known planar sketch normal")
        normal = operation.normal
        target_plane = target_surface.Plane()
        target_normal = target_plane.Axis().Direction().Coord()
        # Compare the cross product, not 1-dot: a small angle must not be
        # magnified into an appreciable wedge on a large profile.
        cross = (
            normal[1] * target_normal[2] - normal[2] * target_normal[1],
            normal[2] * target_normal[0] - normal[0] * target_normal[2],
            normal[0] * target_normal[1] - normal[1] * target_normal[0],
        )
        if math.hypot(*cross) > 1e-9:
            raise _ExtrusionEndFaceError("Up to Face end face must be parallel to the sketch plane")
        profile_faces = _subshapes(profile, TopAbs_FACE)
        if not profile_faces:
            raise KernelError("Up to Face requires a closed planar profile")
        source_surface = BRepAdaptor_Surface(TopoDS.Face(profile_faces[0]))
        if source_surface.GetType() != GeomAbs_Plane:
            raise KernelError("Up to Face requires a planar profile")
        origin = source_surface.Plane().Location().Coord()
        destination = target_plane.Location().Coord()
        reach = direction * sum((destination[i] - origin[i]) * normal[i] for i in range(3))
        if reach < 1e-6:
            raise _ExtrusionEndFaceError(
                "Up to Face end face is not ahead of the sketch in this direction"
            )
        length = reach + offset
        if not 1e-6 <= length <= 1e6:
            raise KernelError("Up to Face offset must leave a positive reach within 1e6 mm")
        return self.extrude(profile, direction * length)

    def extrude_through(self, profile, base, direction):
        """One-sided Through All intent, sized afresh from exact B-rep bounds.

        The bounding box is conservative for arbitrary workplane normals. It is
        never derived from display tessellation, and the computed length is not
        persisted as a design dimension. Original profile/builder provenance is
        retained by extrude(); no topology identities are guessed or rebound.
        """
        if direction not in (-1, 1):
            raise KernelError("Through All direction must be +1 or -1")
        self._validate(base, solid=True)
        self._validate(profile)
        operation = self._operations.get(id(profile))
        if operation is None or operation.normal is None:
            raise KernelError("Through All requires a known planar sketch normal")
        normal = tuple(direction * value for value in operation.normal)

        def projection_range(shape):
            box = _shape_bounds(shape)
            lower = sum(normal[i] * box[i if normal[i] >= 0 else i + 3] for i in range(3))
            upper = sum(normal[i] * box[i + 3 if normal[i] >= 0 else i] for i in range(3))
            return lower, upper

        base_min, base_max = projection_range(base)
        profile_min, _ = projection_range(profile)
        reach = base_max - profile_min
        # Cross the far boundary instead of relying on coincident end faces.
        # A wrong direction still fails the subsequent cut's measurable-removal
        # check; do not silently turn a one-sided operation into both directions.
        margin = max(1e-4, (base_max - base_min) * 1e-6)
        if reach <= 0:
            raise KernelError("Target is not ahead of the sketch in the selected direction")
        return self.extrude(profile, direction * (reach + margin))

    def cut(self, base: TopoDS_Shape, tool: TopoDS_Shape) -> TopoDS_Shape:
        self._validate(base, solid=True)
        self._validate(tool, solid=True)
        builder = BRepAlgoAPI_Cut(base, tool)
        builder.Build()
        if not builder.IsDone():
            raise KernelError("OCCT could not construct the boolean cut")
        shape = builder.Shape()
        self._validate(shape, solid=True)
        before_volume, after_volume = GProp_GProps(), GProp_GProps()
        BRepGProp.VolumeProperties_s(base, before_volume)
        BRepGProp.VolumeProperties_s(shape, after_volume)
        minimum_change = 1e-12 * max(abs(before_volume.Mass()), 1.0)
        if before_volume.Mass() - after_volume.Mass() <= minimum_change:
            raise KernelError("Cut tool does not remove measurable material from the base solid")
        return self._remember(_Operation(shape, "cut", builder, {"base": base, "tool": tool}))

    def _solid_operation(self, builder, kind, inputs):
        builder.Build()
        if not builder.IsDone():
            raise KernelError(f"OCCT could not construct {kind}; revise its dimensions or inputs")
        shape = builder.Shape()
        self._validate(shape, solid=True)
        if len(_subshapes(shape, TopAbs_SOLID)) != 1:
            raise KernelError(f"{kind} must produce one connected solid")
        return self._remember(_Operation(shape, kind, builder, inputs))

    def _isolated_boolean(self, base, tool, kind):
        self._validate(base, solid=True)
        self._validate(tool, solid=True)
        factory = BRepAlgoAPI_Fuse if kind == "union" else BRepAlgoAPI_Common

        def fresh():
            # Copy the whole operand graph together, preserving shared topology.
            # copyGeom=True isolates surfaces/curves as well as TShapes. Boolean
            # constructors may build immediately, so isolation must precede them.
            compound, assembler = TopoDS_Compound(), BRep_Builder()
            assembler.MakeCompound(compound)
            for operand in (base,) if base.IsSame(tool) else (base, tool):
                # Add marks its child non-free even though no geometry changes.
                # Restore that ownership flag before copying or running OCCT.
                was_free = operand.Free()
                try:
                    assembler.Add(compound, operand)
                finally:
                    operand.Free(was_free)
            copier = BRepBuilderAPI_Copy(compound, True, False)
            if not copier.IsDone():
                raise KernelError("OCCT could not isolate Boolean operands")
            copied = {
                name: copier.ModifiedShape(shape)
                for name, shape in (("base", base), ("tool", tool))
            }
            mapping = []
            for name, shape in (("base", base), ("tool", tool)):
                copied_faces = _subshapes(copied[name], TopAbs_FACE)
                for face in _subshapes(shape, TopAbs_FACE):
                    if any(face.IsSame(source) for source, _ in mapping):
                        continue
                    images = list(copier.Modified(face))
                    if (
                        len(images) != 1
                        or images[0].ShapeType() != TopAbs_FACE
                        or images[0].IsSame(face)
                        or not images[0].IsSame(copier.ModifiedShape(face))
                        or copier.IsDeleted(face)
                        or list(copier.Generated(face))
                        or not any(images[0].IsSame(item) for item in copied_faces)
                        or any(images[0].IsSame(image) for _, image in mapping)
                    ):
                        raise KernelError("Boolean operand copy has unresolved face history")
                    mapping.append((face, images[0]))
            builder = factory(copied["base"], copied["tool"])
            builder.Build()
            if not builder.IsDone():
                raise KernelError(
                    f"OCCT could not construct {kind}; revise its dimensions or inputs"
                )
            return builder, mapping

        builder, mapping = fresh()
        try:
            # Preserve successful seam cleanup and its composed native history.
            builder.SimplifyResult(True, True)
        except Standard_Failure:
            # Discard the entire potentially mutated graph and history. Retry only
            # the exact Boolean, with another deep copy of untouched originals.
            builder, mapping = fresh()
        shape = builder.Shape()
        self._validate(shape, solid=True)
        if len(_subshapes(shape, TopAbs_SOLID)) != 1:
            raise KernelError(f"{kind} must produce one connected solid")
        return self._remember(
            _Operation(shape, kind, builder, {"base": base, "tool": tool}, boolean_copies=mapping)
        )

    def union(self, base, tool):
        """Add material, requiring a connected single-body result."""
        return self._isolated_boolean(base, tool, "union")

    def intersection(self, base, tool):
        return self._isolated_boolean(base, tool, "intersection")

    def revolve(self, profile, angle, axis_x=0, axis_y=0, axis_z=1, x=0, y=0, z=0):
        """Explicit world-space axis; degrees, with signed sweep direction."""
        self._validate(profile)
        angle = _number(angle, "angle")
        if not 1e-6 <= abs(angle) <= 360:
            raise KernelError("Revolve angle must be nonzero and within ±360 degrees")
        axis = tuple(_number(v, "axis") for v in (axis_x, axis_y, axis_z))
        if math.hypot(*axis) < 1e-12:
            raise KernelError("Revolve axis must have a nonzero direction")
        origin = tuple(_number(v, "origin") for v in (x, y, z))
        builder = BRepPrimAPI_MakeRevol(
            profile, gp_Ax1(gp_Pnt(*origin), gp_Dir(*axis)), math.radians(angle), True
        )
        return self._solid_operation(builder, "revolve", {"profile": profile})

    def _selected_edges(self, base, edge_faces):
        if edge_faces is None:
            return _subshapes(base, TopAbs_EDGE)
        if len(edge_faces) != 2 or edge_faces[0] == edge_faces[1]:
            raise KernelError("Select two distinct stable faces defining one edge")
        operation = self._operations.get(id(base))
        if operation is None:
            raise KernelError("Selected edge has no retained source topology")
        selected = []
        for identifier in edge_faces:
            matches = [
                face
                for face, candidate in operation.faces
                if candidate["id"] == identifier
                and candidate["provenance"]["semantic_status"] == "stable"
            ]
            if len(matches) != 1:
                raise KernelError(
                    f"Selected face {identifier} is missing, split, or ambiguous; repair the selection"
                )
            if len([c for f, c in operation.faces if f.IsSame(matches[0])]) != 1:
                raise KernelError("Selected face has aliased semantic identity; repair the selection")
            selected.append(matches[0])
        left = _subshapes(selected[0], TopAbs_EDGE)
        right = _subshapes(selected[1], TopAbs_EDGE)
        edges = [edge for edge in left if any(edge.IsSame(other) for other in right)]
        if len(edges) != 1:
            raise KernelError("Selected faces must share exactly one edge; repair the selection")
        return edges

    def projected_circle(self, shape, faces):
        """Exact full-circle data from the same unique stable face-pair contract."""
        edge = self._selected_edges(shape, faces)[0]
        curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
        if curve.GetType() != GeomAbs_Circle:
            raise KernelError("Projected source is not an exact circular edge")
        first, last = curve.FirstParameter(), curve.LastParameter()
        if (
            not all(math.isfinite(v) for v in (first, last))
            or abs(last - first - 2 * math.pi) > 1e-9
        ):
            raise KernelError("Use Solid Edge requires a full circle, not a partial arc")
        circle = curve.Circle()
        result = {
            "center": list(circle.Location().Coord()),
            "normal": list(circle.Axis().Direction().Coord()),
            "radius": circle.Radius(),
        }
        from .sketch_projection import validate_circle

        validate_circle(result)
        return result

    def projected_edges(self, shape, rows):
        result, seen = [], set()
        for row in rows:
            pair = tuple(row["faces"])
            if pair in seen:
                continue
            seen.add(pair)
            if row.get("kind") == "circle":
                result.append(
                    {"kind": "circle", "faces": list(pair), **self.projected_circle(shape, pair)}
                )
            elif row.get("kind") == "arc":
                result.append(self.projected_arc(shape, pair))
            else:
                result.extend(self.projected_edge_endpoints(shape, [pair]))
        return result

    def projected_edge_endpoints(self, shape, face_pairs):
        """Resolve exact straight edges from persistent unique face pairs each replay."""
        result = []
        for pair in sorted({tuple(pair) for pair in face_pairs}):
            edge = self._selected_edges(shape, pair)[0]
            curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
            if curve.GetType() != GeomAbs_Line:
                raise KernelError("Use Solid Edge currently requires a straight native edge")
            first, last = curve.FirstParameter(), curve.LastParameter()
            if not all(math.isfinite(v) for v in (first, last)) or last <= first:
                raise KernelError("Projected edge has no bounded native interval")
            endpoints = self._projected_endpoint_identity(shape, edge, pair)
            points = [item[1] for item in endpoints]
            result.append(
                {
                    "faces": list(pair),
                    "endpoint_faces": [item[0] for item in endpoints],
                    "points": points,
                }
            )
        return result

    def _projected_endpoint_identity(self, shape, edge, pair):
        """Native incidence proves identities; coordinates never select a vertex."""
        vertices = _subshapes(edge, TopAbs_VERTEX)
        if len(vertices) != 2:
            raise KernelError("Projected edge endpoints are not two unique native vertices")
        operation = self._operations[id(shape)]
        endpoints = []
        for vertex in vertices:
            incident = []
            for face, candidate in operation.faces:
                if (candidate["id"] in pair
                        or not any(vertex.IsSame(other) for other in _subshapes(face, TopAbs_VERTEX))):
                    continue
                if candidate["provenance"]["semantic_status"] != "stable":
                    raise KernelError("Projected endpoint has unstable incident-face identity")
                matches = [(f, c) for f, c in operation.faces if c["id"] == candidate["id"]]
                aliases = [c for f, c in operation.faces if f.IsSame(face)]
                if len(matches) != 1 or len(aliases) != 1:
                    raise KernelError("Projected endpoint has aliased incident-face identity")
                incident.append(candidate["id"])
            incident.sort()
            if not incident or len(incident) > 32 or len(set(incident)) != len(incident):
                raise KernelError("Projected endpoint lacks a stable incident-face identity")
            endpoints.append((incident, list(BRep_Tool.Pnt_s(TopoDS.Vertex(vertex)).Coord()), vertex))
        endpoints.sort(key=lambda item: item[0])
        if endpoints[0][0] == endpoints[1][0]:
            raise KernelError("Projected endpoints have ambiguous incident-face identity")
        if math.dist(endpoints[0][1], endpoints[1][1]) < 1e-6:
            raise KernelError("Projected edge is degenerate")
        return endpoints

    def projected_arc(self, shape, faces):
        """Partial circle with proven endpoints and signed native parameter interval."""
        edge = self._selected_edges(shape, faces)[0]
        curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
        if curve.GetType() != GeomAbs_Circle:
            raise KernelError("Projected source is not an exact circular arc")
        first, last = curve.FirstParameter(), curve.LastParameter()
        extent = last - first
        if (not all(math.isfinite(v) for v in (first, last))
                or not 1e-9 < extent < 2 * math.pi - 1e-9):
            raise KernelError("Projected arc needs a bounded partial circle")
        endpoints = self._projected_endpoint_identity(shape, edge, faces)
        # Parameter values describe the already identified native vertices. No
        # point-distance matching, traversal index or face orientation names them.
        parameters = [BRep_Tool.Parameter_s(TopoDS.Vertex(item[2]), TopoDS.Edge(edge))
                      for item in endpoints]
        forward = abs(parameters[0] - first) < 1e-9 and abs(parameters[1] - last) < 1e-9
        backward = abs(parameters[0] - last) < 1e-9 and abs(parameters[1] - first) < 1e-9
        if forward == backward:
            raise KernelError("Arc endpoint parameter roles are not uniquely proven")
        sweep = extent if forward else -extent
        circle = curve.Circle()
        result = {"kind": "arc", "faces": list(faces),
                  "endpoint_faces": [item[0] for item in endpoints],
                  "points": [item[1] for item in endpoints],
                  "center": list(circle.Location().Coord()),
                  "normal": list(circle.Axis().Direction().Coord()),
                  "radius": circle.Radius(), "sweep": sweep}
        from .sketch_projection import validate_arc

        validate_arc(result)
        return result

    def edge_display_catalog(self, shape, deflection=0.1, *, projection_arcs=False):
        """Native adjacency only; lines/circles with exactly one stable face pair.

        Polylines are disposable hit targets, not edge identifiers. Non-manifold,
        seam, degenerate, unstable and multiply-shared pairs are omitted.
        """
        self._require_single_solid(shape)
        operation = self._operations.get(id(shape))
        if operation is None:
            return []
        faces = _subshapes(shape, TopAbs_FACE)
        result = []
        for edge in _subshapes(shape, TopAbs_EDGE):
            adjacent = [
                face
                for face in faces
                if any(edge.IsSame(other) for other in _subshapes(face, TopAbs_EDGE))
            ]
            if len(adjacent) != 2 or BRep_Tool.Degenerated_s(TopoDS.Edge(edge)):
                continue
            if any(BRep_Tool.IsClosed_s(TopoDS.Edge(edge), TopoDS.Face(f)) for f in adjacent):
                continue
            ids = []
            for face in adjacent:
                matches = [
                    candidate
                    for old, candidate in operation.faces
                    if old.IsSame(face) and candidate["provenance"]["semantic_status"] == "stable"
                ]
                if len(matches) != 1:
                    break
                ids.append(matches[0]["id"])
            if len(ids) != 2 or ids[0] == ids[1]:
                continue
            try:
                selected = self._selected_edges(shape, ids)
            except KernelError:
                continue
            if not selected[0].IsSame(edge):
                continue
            curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
            first, last = curve.FirstParameter(), curve.LastParameter()
            if not all(math.isfinite(v) for v in (first, last)) or last <= first:
                continue
            if curve.GetType() == GeomAbs_Line:
                count = 1
            elif curve.GetType() == GeomAbs_Circle:
                radius = curve.Circle().Radius()
                angle = 2 * math.acos(max(-1.0, min(1.0, 1 - deflection / radius)))
                if angle <= 0:
                    continue
                count = max(8, math.ceil((last - first) / min(angle, 0.1)))
                if count > 4096:
                    continue
            else:
                continue
            points = [
                list(curve.Value(first + (last - first) * i / count).Coord())
                for i in range(count + 1)
            ]
            if len(result) >= 2048 or sum(len(e["points"]) for e in result) + len(points) > 100000:
                raise KernelError("Edge display catalog exceeds its resource budget")
            entry = {"faces": sorted(ids), "points": points}
            if curve.GetType() == GeomAbs_Line:
                try:
                    entry = self.projected_edge_endpoints(shape, [sorted(ids)])[0]
                except KernelError:
                    pass  # Blending needs edge identity, not independently stable endpoints.
            elif curve.GetType() == GeomAbs_Circle:
                try:
                    entry["circle"] = self.projected_circle(shape, sorted(ids))
                except KernelError:
                    if projection_arcs:
                        try:
                            arc = self.projected_arc(shape, sorted(ids))
                            entry["arc"] = {key: value for key, value in arc.items()
                                            if key not in {"kind", "faces"}}
                        except KernelError:
                            pass  # Unsupported identity remains a display-only blend target.
            result.append(entry)
        return sorted(result, key=lambda item: item["faces"])

    def _blend_edges(self, base, edge_faces, edge_pairs):
        if edge_pairs is None:
            return self._selected_edges(base, edge_faces)
        from .blend_selection import validate_edge_pairs

        if edge_faces is not None:
            raise KernelError("Choose a single edge or an explicit edge set, not both")
        try:
            if not isinstance(edge_pairs, (tuple, list)) or any(
                not isinstance(pair, (tuple, list)) for pair in edge_pairs
            ):
                raise ValueError("Edges must be a list of explicit face pairs")
            pairs = validate_edge_pairs([list(pair) for pair in edge_pairs])
        except (TypeError, ValueError) as exc:
            raise KernelError(str(exc)) from exc
        edges = []
        for pair in pairs:
            edge = self._selected_edges(base, pair)[0]
            if any(edge.IsSame(other) for other in edges):
                raise KernelError("Selected face pairs resolve to the same native edge")
            edges.append(edge)
        return edges

    def fillet(self, base, radius, *, edge_faces=None, edge_pairs=None):
        """Round all edges or a completely resolved explicit semantic selection.

        No transient native edge index is saved; failure never yields a partial blend.
        """
        self._validate(base, solid=True)
        radius = _number(radius, "radius", positive=True)
        builder = BRepFilletAPI_MakeFillet(base)
        edges = self._blend_edges(base, edge_faces, edge_pairs)
        for edge in edges:
            builder.Add(radius, TopoDS.Edge(edge))
        return self._remember_selected_blend(builder, "fillet", base, edges, edge_faces, edge_pairs)

    def chamfer(self, base, distance, *, edge_faces=None, edge_pairs=None):
        """Symmetric chamfer on all edges or an explicit set, never snapshot indices."""
        self._validate(base, solid=True)
        distance = _number(distance, "distance", positive=True)
        builder = BRepFilletAPI_MakeChamfer(base)
        edges = self._blend_edges(base, edge_faces, edge_pairs)
        for edge in edges:
            builder.Add(distance, TopoDS.Edge(edge))
        return self._remember_selected_blend(
            builder, "chamfer", base, edges, edge_faces, edge_pairs
        )

    def _remember_selected_blend(self, builder, kind, base, edges, edge_faces, edge_pairs):
        shape = self._solid_operation(builder, kind, {"base": base})
        if edge_faces is not None and len(edges) == 1:
            operation = self._operations[id(shape)]
            operation.blend_edge = edges[0]
            operation.blend_faces = tuple(sorted(edge_faces))
        if edge_pairs is not None:
            from .blend_selection import validate_edge_pairs

            pairs = validate_edge_pairs([list(pair) for pair in edge_pairs])
            self._operations[id(shape)].blend_selections = list(zip(edges, pairs, strict=True))
        return shape

    def transform(self, base, x=0, y=0, z=0, rx=0, ry=0, rz=0):
        """Rotate about world X, then Y, then Z, then translate (mm/degrees)."""
        self._validate(base, solid=True)
        transform = gp_Trsf()
        for axis, angle in zip(((1, 0, 0), (0, 1, 0), (0, 0, 1)), (rx, ry, rz), strict=True):
            rotation = gp_Trsf()
            rotation.SetRotation(
                gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis)), math.radians(_number(angle, "rotation"))
            )
            transform = rotation.Multiplied(transform)
        transform.SetTranslationPart(gp_Vec(*(_number(v, "translation") for v in (x, y, z))))
        builder = BRepBuilderAPI_Transform(base, transform, True)
        return self._solid_operation(builder, "transform", {"base": base})

    def mirror(self, base, axis_x=0, axis_y=0, axis_z=1, x=0, y=0, z=0):
        """Reflect one solid across a datum plane; do not retain/fuse the source."""
        self._validate(base, solid=True)
        normal = tuple(_number(v, "plane normal") for v in (axis_x, axis_y, axis_z))
        if math.hypot(*normal) < 1e-12:
            raise KernelError("Mirror plane requires a nonzero normal direction")
        origin = tuple(_number(v, "plane origin") for v in (x, y, z))
        transform = gp_Trsf()
        transform.SetMirror(gp_Ax2(gp_Pnt(*origin), gp_Dir(*normal)))
        builder = BRepBuilderAPI_Transform(base, transform, True)
        return self._solid_operation(builder, "mirror", {"base": base})

    def loft(self, start, end, ruled=0):
        """Two explicit closed single-wire sections, yielding one exact solid."""
        return self._loft_sections((start, end), ruled, {"start": start, "end": end})

    def loft_sections(self, sections, ruled=0):
        """Consume explicit authored order, never a spatially sorted substitute."""
        if not 2 <= len(sections) <= 16:
            raise KernelError("Loft requires 2–16 sections")
        return self._loft_sections(
            sections, ruled, {f"section_{i + 1}": s for i, s in enumerate(sections)}
        )

    def _loft_sections(self, sections, ruled, inputs):
        from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections

        if ruled not in (0, 1):
            raise KernelError("Loft ruled must be 0 or 1")
        builder = BRepOffsetAPI_ThruSections(True, bool(ruled), 1e-6)
        for profile in sections:
            self._validate(profile)
            faces = _subshapes(profile, TopAbs_FACE)
            wires = _subshapes(profile, TopAbs_WIRE)
            if len(faces) != 1 or len(wires) != 1:
                raise KernelError(
                    "Loft currently requires one closed outer wire per section, without holes"
                )
            builder.AddWire(TopoDS.Wire(wires[0]))
        builder.CheckCompatibility(True)
        shape = self._solid_operation(builder, "loft", inputs)
        properties = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, properties)
        if not math.isfinite(properties.Mass()) or properties.Mass() <= 1e-9:
            raise KernelError("Loft must enclose positive measurable volume; separate the sections")
        return shape

    def _place_sweep_section(self, profile, start, tangent, path_normal, placement):
        operation = self._operations.get(id(profile))
        if operation is None or operation.profile_u is None:
            raise KernelError("Automatic Sweep placement requires an authored section workplane")
        if len(_subshapes(profile, TopAbs_FACE)) != 1:
            raise KernelError(
                "Automatic Sweep requires one filled planar region, optionally with holes"
            )
        properties = GProp_GProps()
        BRepGProp.SurfaceProperties_s(profile, properties)
        if not math.isfinite(properties.Mass()) or properties.Mass() <= 0:
            raise KernelError("Sweep section has no finite positive area")
        center = properties.CentreOfMass()

        def cross(a, b):
            return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

        source_u, source_n = operation.profile_u, operation.normal
        source_v = cross(source_n, source_u)
        zero_v = cross(tangent, path_normal)
        roll = math.radians(placement["roll_degrees"])
        target_u = tuple(
            math.cos(roll) * path_normal[i] + math.sin(roll) * zero_v[i] for i in range(3)
        )
        target_v = cross(tangent, target_u)
        # R = target basis * source basis transpose; no mirrored orientation.
        rotation = tuple(
            tuple(
                target_u[i] * source_u[j] + target_v[i] * source_v[j] + tangent[i] * source_n[j]
                for j in range(3)
            )
            for i in range(3)
        )
        source_center = (center.X(), center.Y(), center.Z())
        target_center = (start.X(), start.Y(), start.Z())
        translation = tuple(
            target_center[i] - sum(rotation[i][j] * source_center[j] for j in range(3))
            for i in range(3)
        )
        transform = gp_Trsf()
        transform.SetValues(*(value for i in range(3) for value in (*rotation[i], translation[i])))
        return _copy_transform(profile, transform)

    def sweep(self, profile, path, *, placement=None):
        """Legacy authored placement, or explicit v1 centroid/path-start construction."""
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe

        from .profile_region import ClosedProfile, OpenChainProfile, classify_profile
        from .sketch_model import Sketch

        self._validate(profile)
        if placement is not None:
            from .sweep_placement import validate_placement

            validate_placement(placement)
        if not isinstance(path, Sketch):
            raise KernelError("Sweep path must be a solved constrained line sketch")
        if path.schema_version == 3:
            from .profile_adapter_v3 import classify_profile_v3

            # Classify the genuine solved records; curves are never flattened.
            region = classify_profile_v3(path)
        else:
            region = classify_profile(path)
        from .analytic_profile import AnalyticOpenPath, LineBoundary

        if not isinstance(region, (ClosedProfile, OpenChainProfile, AnalyticOpenPath)):
            raise KernelError(
                "Sweep path requires one connected line/arc open chain or supported line loop"
            )
        if placement is not None and isinstance(region, ClosedProfile):
            raise KernelError("Automatic Sweep placement requires an open path with two endpoints")
        origin, u, v, normal = _profile_plane(path.plane.origin, path.plane.quaternion, strict=True)
        if isinstance(region, AnalyticOpenPath):
            boundaries = region.boundaries
        else:
            points = list(region.points)
            if isinstance(region, ClosedProfile):
                points.append(points[0])
            boundaries = [
                LineBoundary(start, end, str(i))
                for i, (start, end) in enumerate(zip(points, points[1:], strict=False))
            ]

        if not boundaries:
            raise KernelError("Sweep needs a nonempty solved path")
        if placement is not None and placement["reverse"]:
            from dataclasses import replace

            boundaries = [
                replace(
                    boundary,
                    start=boundary.end,
                    end=boundary.start,
                    **({"sweep": -boundary.sweep} if boundary.kind == "arc" else {}),
                )
                for boundary in reversed(boundaries)
            ]

        def world(point):
            return gp_Pnt(*(origin[i] + point[0] * u[i] + point[1] * v[i] for i in range(3)))

        if placement is not None:
            first = boundaries[0]
            if first.kind == "arc":
                radial = (first.start[0] - first.center[0], first.start[1] - first.center[1])
                sign = 1 if first.sweep > 0 else -1
                local_tangent = (-sign * radial[1], sign * radial[0])
            else:
                local_tangent = (first.end[0] - first.start[0], first.end[1] - first.start[1])
            length = math.hypot(*local_tangent)
            if length < 1e-6:
                raise KernelError("Sweep initial tangent is degenerate")
            tangent = tuple(
                (local_tangent[0] * u[i] + local_tangent[1] * v[i]) / length for i in range(3)
            )
            profile = self._place_sweep_section(
                profile, world(first.start), tangent, normal, placement
            )

        wire = BRepBuilderAPI_MakeWire()
        for boundary in boundaries:
            if boundary.kind == "arc":
                circle = gp_Circ(
                    gp_Ax2(world(boundary.center), gp_Dir(*normal), gp_Dir(*u)),
                    math.dist(boundary.start, boundary.center),
                )
                start = math.atan2(
                    boundary.start[1] - boundary.center[1], boundary.start[0] - boundary.center[0]
                )
                sweep = boundary.sweep
                low, high = (start, start + sweep) if sweep > 0 else (start + sweep, start)
                maker = BRepBuilderAPI_MakeEdge(circle, low, high)
                if not maker.IsDone():
                    raise KernelError("Could not build the exact sweep arc")
                edge = maker.Edge()
                if sweep < 0:
                    edge = TopoDS.Edge(edge.Reversed())
            else:
                maker = BRepBuilderAPI_MakeEdge(world(boundary.start), world(boundary.end))
                if not maker.IsDone():
                    raise KernelError("Could not build the solved sweep line")
                edge = maker.Edge()
            wire.Add(edge)
            if not wire.IsDone():
                raise KernelError("Sweep path is not connected")
        if not wire.IsDone():
            raise KernelError("Sweep needs a nonempty solved path")
        builder = BRepOffsetAPI_MakePipe(wire.Wire(), profile)
        return self._solid_operation(builder, "sweep", {"profile": profile})

    def _pattern(self, base, count, transforms, kind):
        count = _number(count, "count")
        if count != int(count) or not 2 <= count <= 64:
            raise KernelError("Pattern count must be an integer between 2 and 64")
        self._validate(base, solid=True)
        result = base
        for transform in transforms(int(count)):
            copy = _copy_transform(base, transform)
            result = self.union(result, copy)
        operation = self._operations[id(result)]
        operation.kind = kind
        operation.inputs = {"base": base}
        return result

    def linear_pattern(self, base, count, dx=10, dy=0, dz=0):
        """Fuse equally spaced whole-source copies, including the original."""
        delta = tuple(_number(v, "spacing") for v in (dx, dy, dz))
        if math.hypot(*delta) < 1e-9:
            raise KernelError("Linear pattern requires nonzero spacing")

        def transforms(count):
            for index in range(1, count):
                transform = gp_Trsf()
                transform.SetTranslation(gp_Vec(*(index * v for v in delta)))
                yield transform

        return self._pattern(base, count, transforms, "linear_pattern")

    def circular_pattern(self, base, count, angle, axis_x=0, axis_y=0, axis_z=1, x=0, y=0, z=0):
        """Total angular extent; full circles exclude their duplicate endpoint."""
        angle = _number(angle, "angle")
        if not 1e-6 <= abs(angle) <= 360:
            raise KernelError("Pattern angle must be nonzero and within ±360 degrees")
        axis = tuple(_number(v, "axis") for v in (axis_x, axis_y, axis_z))
        if math.hypot(*axis) < 1e-12:
            raise KernelError("Pattern axis requires a nonzero direction")
        origin = tuple(_number(v, "origin") for v in (x, y, z))

        def transforms(count):
            divisor = count if abs(angle) == 360 else count - 1
            for index in range(1, count):
                transform = gp_Trsf()
                transform.SetRotation(
                    gp_Ax1(gp_Pnt(*origin), gp_Dir(*axis)), math.radians(index * angle / divisor)
                )
                yield transform

        return self._pattern(base, count, transforms, "circular_pattern")

    def _cut_pattern(self, base, tool, count, transforms, kind):
        """Sequential native cuts with one composed history back to the authored base."""
        count = _number(count, "count")
        if count != int(count) or not 2 <= count <= 64:
            raise KernelError("Pattern count must be an integer between 2 and 64")
        self._validate(base, solid=True)
        self._validate(tool, solid=True)
        result, history = base, None
        pattern_sources, cutters, overlapping = [], [], set()
        source = self._operations.get(id(tool))
        for occurrence, transform in enumerate(transforms(int(count))):
            copier = (
                BRepBuilderAPI_Transform(tool, transform, True, False)
                if transform is not None
                else None
            )
            if copier and not copier.IsDone():
                raise KernelError("Pattern tool transform failed")
            cutter = copier.Shape() if copier else tool
            if self._pattern_face_lineage:
                # This bounded rule deliberately excludes intersecting cutters.
                # Native Common volume, not proximity or face enumeration, proves
                # material overlap. Neither occurrence may claim a merged cavity.
                for previous, prior in enumerate(cutters):
                    common = BRepAlgoAPI_Common(prior, cutter)
                    common.Build()
                    if not common.IsDone():
                        raise KernelError("Could not verify pattern occurrence separation")
                    mass = GProp_GProps()
                    BRepGProp.VolumeProperties_s(common.Shape(), mass)
                    if mass.Mass() > 1e-12:
                        overlapping.update((previous, occurrence))
                for face, candidate in source.faces if source else []:
                    images = list(copier.Modified(face)) if copier else [face]
                    if len(images) == 1 and images[0].ShapeType() == TopAbs_FACE:
                        pattern_sources.append((occurrence, images[0], candidate))
                    else:
                        # Incomplete transform ancestry cannot exclude a competing claim.
                        overlapping.add(occurrence)
            cutters.append(cutter)
            builder = BRepAlgoAPI_Cut(result, cutter)
            builder.Build()
            if not builder.IsDone():
                raise KernelError("OCCT could not construct a patterned cut")
            result = builder.Shape()
            self._validate(result, solid=True)
            if len(_subshapes(result, TopAbs_SOLID)) != 1:
                raise KernelError("Patterned cuts must leave one connected solid")
            if history is None:
                history = builder.History()
            else:
                history.Merge(builder.History())
        before, after = GProp_GProps(), GProp_GProps()
        BRepGProp.VolumeProperties_s(base, before)
        BRepGProp.VolumeProperties_s(result, after)
        if before.Mass() - after.Mass() <= 1e-12 * max(abs(before.Mass()), 1.0):
            raise KernelError("Patterned tools do not remove measurable material from the base")

        class ComposedHistory:
            def Modified(self, shape):
                return history.Modified(shape)

            def Generated(self, shape):
                return history.Generated(shape)

            def IsDeleted(self, shape):
                return history.IsRemoved(shape)

        return self._remember(
            _Operation(
                result,
                kind,
                ComposedHistory(),
                {"base": base},
                pattern_sources=[
                    (index, face, candidate, index not in overlapping)
                    for index, face, candidate in pattern_sources
                ],
            )
        )

    def linear_cut_pattern(self, base, tool, count, dx=10, dy=0, dz=0):
        """Cut all placements, including the original tool, without fusing tools."""
        delta = tuple(_number(v, "spacing") for v in (dx, dy, dz))
        if math.hypot(*delta) < 1e-9:
            raise KernelError("Linear cut pattern requires nonzero spacing")

        def transforms(count):
            yield None
            for index in range(1, count):
                transform = gp_Trsf()
                transform.SetTranslation(gp_Vec(*(index * v for v in delta)))
                yield transform

        return self._cut_pattern(base, tool, count, transforms, "linear_cut_pattern")

    def circular_cut_pattern(
        self, base, tool, count, angle, axis_x=0, axis_y=0, axis_z=1, x=0, y=0, z=0
    ):
        """Full circles omit their duplicate endpoint; partial sweeps include both ends."""
        angle = _number(angle, "angle")
        if not 1e-6 <= abs(angle) <= 360:
            raise KernelError("Pattern angle must be nonzero and within ±360 degrees")
        axis = tuple(_number(v, "axis") for v in (axis_x, axis_y, axis_z))
        if math.hypot(*axis) < 1e-12:
            raise KernelError("Pattern axis requires a nonzero direction")
        origin = tuple(_number(v, "origin") for v in (x, y, z))

        def transforms(count):
            yield None
            divisor = count if abs(angle) == 360 else count - 1
            for index in range(1, count):
                transform = gp_Trsf()
                transform.SetRotation(
                    gp_Ax1(gp_Pnt(*origin), gp_Dir(*axis)), math.radians(index * angle / divisor)
                )
                yield transform

        return self._cut_pattern(base, tool, count, transforms, "circular_cut_pattern")

    def shell(self, base, thickness, *, opening_faces=None):
        """Inward shell, optionally removing explicitly stable planar faces."""
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid

        self._validate(base, solid=True)
        thickness = _number(thickness, "thickness", positive=True)
        if opening_faces is not None:
            if (
                not isinstance(opening_faces, (tuple, list))
                or not 1 <= len(opening_faces) <= 64
                or any(type(item) is not str for item in opening_faces)
                or len(set(opening_faces)) != len(opening_faces)
            ):
                raise KernelError("Open shell requires 1–64 distinct planar openings")
            operation = self._operations.get(id(base))
            remove = List_TopoDS_Shape()
            selected = []
            for identifier in opening_faces:
                matches = (
                    []
                    if operation is None
                    else [
                        (face, candidate)
                        for face, candidate in operation.faces
                        if candidate["id"] == identifier
                    ]
                )
                if len(matches) != 1 or matches[0][1]["provenance"]["semantic_status"] != "stable":
                    raise KernelError(
                        f"Shell opening {identifier!r} is missing, split, or ambiguous; pick it again"
                    )
                face = matches[0][0]
                if any(face.IsSame(previous) for previous in selected):
                    raise KernelError("Shell opening identities alias the same native face")
                if BRepAdaptor_Surface(TopoDS.Face(face)).GetType() != GeomAbs_Plane:
                    raise KernelError(f"Shell opening {identifier!r} requires a planar face")
                selected.append(face)
                remove.Append(face)
            offset = BRepOffsetAPI_MakeThickSolid()
            offset.MakeThickSolidByJoin(_subshapes(base, TopAbs_SOLID)[0], remove, -thickness, 1e-6)
            result = self._solid_operation(offset, "shell", {"base": base})
            before = self.inspect(base)["volume"]
            remaining = self.inspect(result)["volume"]
            if not 0 < remaining < before - max(before, 1) * 1e-12:
                raise KernelError("Wall thickness does not leave a measurable open cavity")
            self._operations[id(result)].shell_openings = tuple(opening_faces)
            return result
        offset = BRepOffsetAPI_MakeThickSolid()
        offset.MakeThickSolidByJoin(
            _subshapes(base, TopAbs_SOLID)[0], List_TopoDS_Shape(), -thickness, 1e-6
        )
        if not offset.IsDone():
            raise KernelError("Wall thickness cannot produce a valid inner offset")
        inner = offset.Shape()
        self._validate(inner, solid=True)
        before = self.inspect(base)["volume"]
        result = self._solid_operation(BRepAlgoAPI_Cut(base, inner), "shell", {"base": base})
        remaining = self.inspect(result)["volume"]
        if not 0 < remaining < before - max(before, 1) * 1e-12:
            raise KernelError("Wall thickness does not leave a measurable enclosed cavity")
        return result

    def inspect(self, shape: TopoDS_Shape) -> dict[str, Any]:
        self._validate(shape)
        volume, area = GProp_GProps(), GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, volume)
        BRepGProp.SurfaceProperties_s(shape, area)
        return {
            "valid": True,
            "volume": volume.Mass(),
            "area": area.Mass(),
            "solids": len(_subshapes(shape, TopAbs_SOLID)),
            "faces": len(_subshapes(shape, TopAbs_FACE)),
        }

    @staticmethod
    def runtime_versions() -> dict[str, str]:
        """Actual binding/package/interpreter versions, not inferred OCCT versions."""
        try:
            distribution = version("cadquery-ocp-novtk")
        except PackageNotFoundError:
            distribution = "not_installed"
        return {
            "adapter": "assembly-brep-1",
            "ocp": OCP.__version__,
            "cadquery_ocp_novtk": distribution,
            "python": platform.python_version(),
            "occt_runtime": "not_exposed_by_binding",
        }

    def transformed(
        self, shape: TopoDS_Shape, frame: Any, *, linear_tolerance_mm: float = 1e-6
    ) -> TopoDS_Shape:
        """Independent solid copy under a literal XYZ/WXYZ rigid frame.

        Accepted near-unit quaternions are normalized only in this temporary
        calculation. Neither authored data nor the source B-rep is modified. A
        transformed copy has no remembered semantic topology/provenance.
        """
        tolerance = _query_number(
            linear_tolerance_mm, "linear_tolerance_mm", bound=1.0, positive=True
        )
        if isinstance(frame, dict):
            if set(frame) != {"xyz_mm", "wxyz"}:
                raise KernelError("Frame requires exactly xyz_mm and wxyz")
            xyz, quaternion = frame["xyz_mm"], frame["wxyz"]
        else:
            xyz, quaternion = getattr(frame, "xyz_mm", None), getattr(frame, "wxyz", None)
        if (
            type(xyz) not in (tuple, list)
            or len(xyz) != 3
            or type(quaternion) not in (tuple, list)
            or len(quaternion) != 4
        ):
            raise KernelError("Frame requires three XYZ coordinates and a WXYZ quaternion")
        xyz = tuple(_query_number(v, "Frame coordinate", bound=1e6) for v in xyz)
        quaternion = tuple(
            _query_number(v, "Frame quaternion", bound=1.00000001) for v in quaternion
        )
        norm_squared = sum(value * value for value in quaternion)
        if abs(norm_squared - 1.0) > 1e-9:
            raise KernelError("Frame quaternion must have unit length")
        w, x, y, z = (value / math.sqrt(norm_squared) for value in quaternion)
        transform = gp_Trsf()
        transform.SetValues(
            1 - 2 * (y * y + z * z),
            2 * (x * y - w * z),
            2 * (x * z + w * y),
            xyz[0],
            2 * (x * y + w * z),
            1 - 2 * (x * x + z * z),
            2 * (y * z - w * x),
            xyz[1],
            2 * (x * z - w * y),
            2 * (y * z + w * x),
            1 - 2 * (x * x + y * y),
            xyz[2],
        )
        try:
            self._require_single_solid(shape, linear_tolerance_mm=tolerance)
            result = _copy_transform(shape, transform)
            self._require_single_solid(result, linear_tolerance_mm=tolerance)
            return result
        except KernelError:
            raise
        except Exception as exc:
            raise KernelError(f"OCCT rigid-copy transform failed: {exc}") from exc

    def pair_check(
        self,
        a: TopoDS_Shape,
        b: TopoDS_Shape,
        *,
        minimum_required_mm: float = 0.0,
        linear_tolerance_mm: float = 1e-6,
        volume_tolerance_mm3: float = 1e-9,
    ) -> dict[str, Any]:
        """Common volume and minimum boundary distance at one static pose.

        Caller-parameter errors raise KernelError before native work. Geometry or
        native failures become explicit incomplete results; a failed distance
        query cannot erase already-proven interference. Distance is nonnegative
        surface separation, never penetration depth or a continuous-motion test.
        """
        linear = _query_number(linear_tolerance_mm, "linear_tolerance_mm", bound=1, positive=True)
        volume_tolerance = _query_number(
            volume_tolerance_mm3, "volume_tolerance_mm3", bound=1, positive=True
        )
        required = _query_number(minimum_required_mm, "minimum_required_mm", bound=1e6)
        if required < 0:
            raise KernelError("minimum_required_mm must be nonnegative")
        result: dict[str, Any] = {
            "relation": "unknown",
            "common_volume_mm3": None,
            "minimum_distance_mm": None,
            "minimum_required_mm": required,
            "clearance_verdict": "indeterminate",
            "witness_points_mm": None,
            "complete": False,
            "known_interference": False,
            "known_clearance_violation": False,
            "diagnostics": [],
        }
        try:
            inputs = [self._require_single_solid(s, linear_tolerance_mm=linear) for s in (a, b)]
            bounds = [_shape_bounds(s) for s in (a, b)]
            origin = tuple(
                min(box[i] for box in bounds) / 2 + max(box[i + 3] for box in bounds) / 2
                for i in range(3)
            )
            # Recenter both temporary copies together. This never changes the
            # canonical frame and returned witnesses are restored to world mm.
            shift = gp_Trsf()
            shift.SetTranslation(gp_Vec(*(-value for value in origin)))
            local_a, local_b = (_copy_transform(s, shift) for s in (a, b))
            for shape in (local_a, local_b):
                self._require_single_solid(shape, linear_tolerance_mm=linear)
        except Exception as exc:
            result["diagnostics"].append(_diagnostic(exc, "input_geometry"))
            return result

        try:
            common = BRepAlgoAPI_Common()
            arguments, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
            arguments.Append(local_a)
            tools.Append(local_b)
            common.SetArguments(arguments)
            common.SetTools(tools)
            common.SetNonDestructive(True)
            common.SetRunParallel(False)
            # Never raise fuzzy tolerance to bridge a small real clearance.
            common.Build()
            if not common.IsDone():
                raise _AssemblyQueryError("common_failed", "OCCT Boolean common did not complete")
            overlap = common.Shape()
            self._validate(overlap)
            pieces = _subshapes(overlap, TopAbs_SOLID)
            volumes = [
                self._require_single_solid(s, linear_tolerance_mm=linear)["volume"] for s in pieces
            ]
            common_volume = math.fsum(volumes)
            smaller = min(stats["volume"] for stats in inputs)
            if not math.isfinite(common_volume) or common_volume > smaller + max(
                volume_tolerance, smaller * 1e-9
            ):
                raise _AssemblyQueryError(
                    "common_invalid", "Common volume exceeds the input solid volume"
                )
            result["common_volume_mm3"] = common_volume
            if common_volume > volume_tolerance:
                result["relation"] = "interference"
                result["known_interference"] = True
            elif pieces:
                result["relation"] = "indeterminate_small_overlap"
                result["diagnostics"].append(
                    {
                        "code": "small_positive_overlap",
                        "message": "Positive common volume is at or below the volume threshold; it is not clear",
                    }
                )
        except Exception as exc:
            result["diagnostics"].append(_diagnostic(exc, "common"))

        try:
            distance = BRepExtrema_DistShapeShape(_boundary(local_a), _boundary(local_b), linear)
            if not distance.IsDone() or distance.NbSolution() < 1:
                raise _AssemblyQueryError(
                    "distance_failed", "OCCT surface-distance query did not complete"
                )
            gap = distance.Value()
            if not math.isfinite(gap) or gap < 0 or distance.InnerSolution():
                raise _AssemblyQueryError(
                    "distance_invalid", "OCCT returned an invalid surface distance"
                )
            points = [
                list(distance.PointOnShape1(1).Coord()),
                list(distance.PointOnShape2(1).Coord()),
            ]
            if any(not math.isfinite(v) for point in points for v in point):
                raise _AssemblyQueryError(
                    "distance_invalid", "OCCT returned a non-finite distance witness"
                )
            if abs(math.dist(*points) - gap) > linear:
                raise _AssemblyQueryError(
                    "distance_invalid", "Distance witnesses disagree with the measured distance"
                )
            world_points = [[v + origin[i] for i, v in enumerate(point)] for point in points]
            for point, box in zip(world_points, bounds, strict=True):
                if any(
                    not math.isfinite(v) or not box[i] - linear <= v <= box[i + 3] + linear
                    for i, v in enumerate(point)
                ):
                    raise _AssemblyQueryError(
                        "distance_invalid", "Distance witness is outside its solid bounds"
                    )
            result["minimum_distance_mm"] = gap
            result["witness_points_mm"] = world_points
            result["known_clearance_violation"] = gap + linear < required
            if result["common_volume_mm3"] == 0:
                result["relation"] = "contact_or_near" if gap <= linear else "separated"
            # With separated boundaries, whole-solid extrema independently
            # distinguishes containment from separation. This is a consistency
            # check only; its zero containment distance is never reported as the
            # minimum surface distance. An empty Common must not conceal a solid
            # that the distance algorithm classifies as contained.
            if gap > linear and result["common_volume_mm3"] is not None:
                solid_distance = BRepExtrema_DistShapeShape(local_a, local_b, linear)
                if not solid_distance.IsDone() or solid_distance.NbSolution() < 1:
                    raise _AssemblyQueryError(
                        "distance_consistency_failed",
                        "OCCT solid-distance cross-check did not complete",
                    )
                solid_gap = solid_distance.Value()
                contained = solid_distance.InnerSolution()
                has_overlap = result["common_volume_mm3"] > 0
                if (
                    not math.isfinite(solid_gap)
                    or solid_gap < 0
                    or (has_overlap and (not contained or solid_gap > linear))
                    or (not has_overlap and (contained or abs(solid_gap - gap) > linear))
                ):
                    result["relation"] = "indeterminate_kernel_disagreement"
                    result["known_interference"] = False
                    raise _AssemblyQueryError(
                        "kernel_disagreement", "Common volume and solid/surface distances disagree"
                    )
        except Exception as exc:
            result["diagnostics"].append(_diagnostic(exc, "distance"))

        result["complete"] = not result["diagnostics"]
        if result["known_interference"]:
            result["clearance_verdict"] = "fail_interference"
        elif result["known_clearance_violation"]:
            result["clearance_verdict"] = "fail_clearance"
        elif result["complete"]:
            result["clearance_verdict"] = (
                "at_threshold"
                if result["minimum_distance_mm"] <= required + linear
                else "pass_at_pose"
            )
        return result

    @staticmethod
    def _candidate(
        face: TopoDS_Shape,
        feature_id: str,
        role: str,
        *,
        status: str = "stable",
        operation: str,
        relation: str,
        **provenance: Any,
    ) -> dict[str, Any]:
        # Unresolved IDs are replaced with explicitly snapshot-local IDs in
        # topology(). Such IDs are selection handles, never persistent names.
        identifier = (
            f"{feature_id}/face/{role}" if status == "stable" else f"pending:{feature_id}:{role}"
        )
        return {
            "id": identifier,
            "feature_id": feature_id,
            "role": role,
            "kind": "face",
            "signature": _surface_signature(face),
            "provenance": {
                "semantic_status": status,
                "kernel": "OCCT",
                "operation": operation,
                "operation_id": feature_id,
                "relation": relation,
                "evolution": relation,
                **provenance,
            },
        }

    def topology(
        self,
        shape: TopoDS_Shape,
        feature_id: str,
        kind: str,
        params: dict[str, Any],
        inputs: dict[str, TopoDS_Shape] | None = None,
    ) -> list[dict[str, Any]]:
        """Describe face identity, with geometry only as a repair suggestion.

        The descriptor kind/params never prove a role: only retained builders
        and explicit construction do. Imported/arbitrary B-reps are unknown.
        Inputs are accepted for engine compatibility but cannot manufacture
        missing provenance.
        """
        del kind, params, inputs
        operation = self._operations.get(id(shape))
        faces = _subshapes(shape, TopAbs_FACE)
        assignments: list[tuple[TopoDS_Shape, dict[str, Any]]] = []

        def assign(face: TopoDS_Shape, role: str, relation: str, **provenance: Any) -> None:
            matches = [output for output in faces if output.IsSame(face)]
            for output in matches:
                assignments.append(
                    (
                        output,
                        self._candidate(
                            output,
                            feature_id,
                            role,
                            operation=operation.kind,
                            relation=relation,
                            **provenance,
                        ),
                    )
                )

        if operation and operation.kind in {
            "rectangle",
            "circle",
            "polygon",
            "circle_profile",
            "curve_profile",
            "regions",
            "analytic_regions",
            "sketch_face_rectangle",
            "sketch_face_circle",
        }:
            assign(shape, "profile", "constructed_profile")
        elif operation and operation.kind in {"extrude", "revolve"}:
            assign(operation.builder.FirstShape(), "cap.start", "first_shape")
            assign(operation.builder.LastShape(), "cap.end", "last_shape")
            profile = self._operations.get(id(operation.inputs["profile"]))
            if profile:
                for role, edge in profile.boundaries.items():
                    generated = [
                        face
                        for face in operation.builder.Generated(edge)
                        if face.ShapeType() == TopAbs_FACE
                    ]
                    for face in generated:
                        assign(
                            face,
                            f"side.{role}",
                            "generated_from_profile_edge",
                            status="stable" if len(generated) == 1 else "split",
                            source_boundary=role,
                        )
        elif operation and operation.kind in {
            "cut",
            "fillet",
            "chamfer",
            "transform",
            "mirror",
            "linear_cut_pattern",
            "circular_cut_pattern",
        }:
            assignments = self._cut_topology(operation, faces, feature_id)
            if operation.kind in {"linear_cut_pattern", "circular_cut_pattern"}:
                assignments += self._pattern_face_topology(
                    operation, faces, feature_id, assignments
                )
            if operation.kind in {"fillet", "chamfer"}:
                assignments += self._selected_blend_topology(
                    operation, faces, feature_id, assignments
                )
        elif operation and operation.kind == "shell" and operation.shell_openings:
            assignments = self._open_shell_topology(operation, faces, feature_id)
        elif operation and operation.kind in {"union", "intersection"}:
            assignments = self._boolean_topology(operation, faces, feature_id)

        resolved: list[tuple[TopoDS_Shape, dict[str, Any]]] = []
        for face in faces:
            matches = [item for assigned, item in assignments if face.IsSame(assigned)]
            if len(matches) == 1:
                resolved.append((face, matches[0]))
            else:
                resolved.append(
                    (
                        face,
                        self._candidate(
                            face,
                            feature_id,
                            "unresolved",
                            status="merged" if matches else "unknown",
                            operation=operation.kind if operation else "untracked",
                            relation="multiple_sources" if matches else "no_history",
                            sources=[item["id"] for item in matches],
                        ),
                    )
                )
        for snapshot_index, (_, candidate) in enumerate(resolved):
            if candidate["provenance"]["semantic_status"] != "stable":
                candidate["id"] = f"snapshot:{feature_id}:face:{snapshot_index}"
                candidate["provenance"]["id_scope"] = "evaluation_snapshot_only"
        if operation:
            operation.faces = resolved
        return [candidate for _, candidate in resolved]

    def cut_ancestry(self, shape: TopoDS_Shape) -> dict[str, Any] | None:
        """Return complete current-face history for one ordinary Cut only.

        These IDs are the current topology catalog's request-local handles,
        not newly stable names. Every source face participates, including split,
        generated and unknown candidates. Relations are independent: a native
        claim must not disappear just because another relation also applies.
        Call topology() on both inputs and the output before requesting this
        ledger. Missing or ambiguous native/catalog mappings fail closed.
        """
        operation = self._operations.get(id(shape))
        if operation is None or operation.kind != "cut":
            return None
        if operation.builder is None or set(operation.inputs) != {"base", "tool"}:
            raise KernelError("Cut ancestry requires a complete native Cut operation")

        def catalog(current: TopoDS_Shape, label: str):
            source = self._operations.get(id(current))
            if source is None or not source.faces:
                raise KernelError(f"Cut ancestry requires current {label} topology")
            # Match the existing transport's per-topology face bound. Both
            # operands together therefore have at most 400,000 source rows.
            if len(source.faces) > 200_000:
                raise KernelError("Cut ancestry exceeds the 200000-face catalog budget")
            native = _subshapes(current, TopAbs_FACE)
            if len(native) != len(source.faces):
                raise KernelError(f"Cut ancestry has incomplete {label} native face mapping")
            result, identifiers = [], set()
            for face in native:
                matches = [candidate for item, candidate in source.faces if item.IsSame(face)]
                if len(matches) != 1:
                    raise KernelError(f"Cut ancestry has ambiguous {label} native face mapping")
                identifier = matches[0].get("id")
                if type(identifier) is not str or not identifier or identifier in identifiers:
                    raise KernelError(f"Cut ancestry requires unique current {label} face IDs")
                identifiers.add(identifier)
                result.append((face, identifier))
            return result

        outputs = catalog(shape, "output")
        operands = [(port, catalog(operation.inputs[port], port)) for port in ("base", "tool")]
        sources = []
        for port, faces in operands:
            for source, source_id in faces:
                deleted = bool(operation.builder.IsDeleted(source))
                modified = list(operation.builder.Modified(source))
                generated = list(operation.builder.Generated(source))
                sources.append(
                    {
                        "port": port,
                        "source_id": source_id,
                        "deleted": deleted,
                        "modified": [
                            identifier
                            for output, identifier in outputs
                            if any(output.IsSame(item) for item in modified)
                        ],
                        "generated": [
                            identifier
                            for output, identifier in outputs
                            if any(output.IsSame(item) for item in generated)
                        ],
                        "unchanged": [
                            identifier
                            for output, identifier in outputs
                            if not deleted and output.IsSame(source)
                        ],
                    }
                )
        return {"version": 1, "sources": sources}

    def _pattern_face_topology(self, operation, faces, feature_id, inherited):
        """Feature-owned occurrence intent, never native face order or proximity."""
        if not self._pattern_face_lineage:
            return []
        claims = []
        for occurrence, source_face, source, separate in operation.pattern_sources:
            modified = list(operation.builder.Modified(source_face))
            generated = list(operation.builder.Generated(source_face))
            images = [
                face
                for face in faces
                if any(face.IsSame(item) for item in modified + generated)
                or (face.IsSame(source_face) and not operation.builder.IsDeleted(source_face))
            ]
            claims.append((occurrence, source, separate, images, generated))
        assignments = []
        for occurrence, source, separate, images, generated in claims:
            if (
                not separate
                or len(images) != 1
                or source["provenance"]["semantic_status"] != "stable"
            ):
                continue
            face = images[0]
            if any(face.IsSame(item) for item in generated):
                continue
            if any(face.IsSame(item) for item, _ in inherited):
                continue
            if sum(any(face.IsSame(item) for item in other[3]) for other in claims) != 1:
                continue
            if (
                sum(
                    index == occurrence and item["id"] == source["id"] for index, item, *_ in claims
                )
                != 1
            ):
                continue
            role = f"pattern.copy.{occurrence}." + sha256(source["id"].encode()).hexdigest()
            assignments.append(
                (
                    face,
                    self._candidate(
                        face,
                        feature_id,
                        role,
                        operation=operation.kind,
                        relation="pattern_tool_face",
                        source_id=source["id"],
                        occurrence=occurrence,
                        source_count=1,
                        image_count=1,
                    ),
                )
            )
        return assignments

    def _selected_blend_topology(self, operation, faces, feature_id, inherited):
        """Name a new blend surface, not an image of either neighboring face.

        The saved selected face pair owns this feature's intent. Only a unique
        native Generated image of its one edge qualifies. Tangent-chain, corner,
        split and competing face/edge/vertex ancestry cannot acquire this role.
        """
        if operation.blend_selections:
            return self._multiple_blend_topology(operation, faces, feature_id, inherited)
        edge = operation.blend_edge
        if not self._selected_blend_lineage or edge is None:
            return []
        generated = list(operation.builder.Generated(edge))
        images = [face for face in faces if any(face.IsSame(item) for item in generated)]
        if len(images) != 1:
            return []
        output = images[0]
        if any(output.IsSame(face) for face, _ in inherited):
            return []
        base = operation.inputs["base"]
        for kind in (TopAbs_EDGE, TopAbs_VERTEX):
            for source in _subshapes(base, kind):
                if source.IsSame(edge):
                    continue
                if any(output.IsSame(item) for item in operation.builder.Generated(source)):
                    return []
        return [
            (
                output,
                self._candidate(
                    output,
                    feature_id,
                    "blend.surface",
                    operation=operation.kind,
                    relation="generated_from_selected_edge",
                    source_faces=list(operation.blend_faces),
                    image_count=1,
                ),
            )
        ]

    def _multiple_blend_topology(self, operation, faces, feature_id, inherited):
        from .blend_selection import selected_surface_role, unique_generated_images

        if not self._selected_blend_lineage:
            return []
        base = operation.inputs["base"]
        builder = operation.builder
        claims = []
        for kind in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
            for source in _subshapes(base, kind):
                images = list(builder.Generated(source))
                if kind == TopAbs_FACE:
                    # Even unnamed/split face ancestry disqualifies a new face.
                    images += list(builder.Modified(source)) + [source]
                claims.append((source, images))
        assignments = []
        selections = operation.blend_selections
        for edge, output in unique_generated_images(
            [edge for edge, _ in selections], faces, claims
        ):
            if any(output.IsSame(face) for face, _ in inherited):
                continue
            pair = next(pair for source, pair in selections if source.IsSame(edge))
            assignments.append(
                (
                    output,
                    self._candidate(
                        output,
                        feature_id,
                        selected_surface_role(pair, len(selections)),
                        operation=operation.kind,
                        relation="generated_from_selected_edge",
                        source_faces=list(pair),
                        image_count=1,
                    ),
                )
            )
        return assignments

    def _open_shell_topology(self, operation, faces, feature_id):
        """Retained outer identity and typed, feature-owned offset construction.

        Inner Generated walls and the opening's Modified rim are new surfaces,
        never identity images of the outside. Typed replay names them separately
        only with a unique source and image; legacy replay stays unchanged.
        """
        base = self._operations.get(id(operation.inputs["base"]))
        if base is None:
            return []
        history = [
            (
                face,
                candidate,
                list(operation.builder.Modified(face)),
                list(operation.builder.Generated(face)),
            )
            for face, candidate in base.faces
        ]
        assignments = []
        for source, candidate, modified, generated in history:
            if (
                candidate["provenance"]["semantic_status"] != "stable"
                or candidate["id"] in operation.shell_openings
                or sum(c["id"] == candidate["id"] for _, c, _, _ in history) != 1
                or operation.builder.IsDeleted(source)
                or modified
            ):
                continue
            same = [face for face in faces if face.IsSame(source)]
            if len(same) != 1 or any(same[0].IsSame(face) for face in generated):
                continue
            output = same[0]
            if output.Orientation() != source.Orientation():
                continue
            sources = [
                previous
                for previous, _, changes, additions in history
                if output.IsSame(previous)
                or any(output.IsSame(face) for face in changes + additions)
            ]
            if len(sources) != 1:
                continue
            assignments.append(
                (
                    output,
                    self._candidate(
                        output,
                        candidate["feature_id"],
                        candidate["role"],
                        operation="shell",
                        relation="unchanged",
                        source_id=candidate["id"],
                        modifying_feature_id=feature_id,
                        operation_id=feature_id,
                        source_count=1,
                        image_count=1,
                    ),
                )
            )
        if self._shell_surface_lineage:
            for _source, candidate, modified, generated in history:
                opening = candidate["id"] in operation.shell_openings
                changes = modified if opening else generated
                if (
                    candidate["provenance"]["semantic_status"] != "stable"
                    or sum(c["id"] == candidate["id"] for _, c, _, _ in history) != 1
                    or (generated if opening else modified)
                ):
                    continue
                images = [face for face in faces if any(face.IsSame(item) for item in changes)]
                if len(images) != 1:
                    continue
                output = images[0]
                claims = [
                    previous
                    for previous, _, changes, additions in history
                    if output.IsSame(previous)
                    or any(output.IsSame(face) for face in changes + additions)
                ]
                if len(claims) != 1 or any(
                    output.IsSame(previous) for previous, _, _, _ in history
                ):
                    continue
                # Feature-owned construction intent, never the outer face identity.
                # Inner walls digest their source ID, never geometry or enumeration.
                # Legacy single-lip intent is unchanged. Multiple lips bind to source IDs.
                role = (
                    (
                        "shell.opening_lip"
                        if len(operation.shell_openings) == 1
                        else "shell.opening_lip." + sha256(candidate["id"].encode()).hexdigest()
                    )
                    if opening
                    else "shell.inner." + sha256(candidate["id"].encode()).hexdigest()
                )
                assignments.append(
                    (
                        output,
                        self._candidate(
                            output,
                            feature_id,
                            role,
                            operation="shell",
                            relation="rim_from_opening" if opening else "offset_from_face",
                            source_id=candidate["id"],
                            source_count=1,
                            image_count=1,
                        ),
                    )
                )
        return assignments

    def _boolean_topology(self, operation, faces, feature_id):
        """Propagate proven native history from both operands, never their names alone.

        Copies may inherit the same semantic IDs while occupying distinct physical
        faces. Those aliases have no unique persistent meaning in the combined
        result, even if one image disappears. Leave them unknown rather than
        choosing a branch by list order or apparent geometric similarity.
        """
        operands = []
        for shape in operation.inputs.values():
            if not any(shape.IsSame(previous) for previous in operands):
                operands.append(shape)
        sources = {}
        for shape in operands:
            source = self._operations.get(id(shape))
            for face, candidate in source.faces if source else []:
                if candidate["provenance"]["semantic_status"] != "stable":
                    continue
                bucket = sources.setdefault(candidate["id"], [])
                if not any(face.IsSame(previous) for previous in bucket):
                    bucket.append(face)
        ambiguous = {identifier for identifier, values in sources.items() if len(values) > 1}
        assignments = []
        for shape in operands:
            # Reuse the established exact modified/generated/deleted source
            # mapping. Unlike cut, both operands own retained semantic surfaces.
            source_operation = _Operation(
                operation.shape, operation.kind, operation.builder, {"base": shape}
            )
            source = self._operations.get(id(shape))
            mapped_sources = []
            for original, candidate in source.faces if source else []:
                images = [
                    image
                    for previous, image in operation.boolean_copies
                    if previous.IsSame(original)
                ]
                if len(images) != 1:
                    raise KernelError("Boolean source has unresolved copy ancestry")
                mapped_sources.append((images[0], candidate))
            for face, candidate in self._cut_topology(
                source_operation, faces, feature_id, source_faces=mapped_sources
            ):
                if candidate["provenance"].get("source_id") not in ambiguous:
                    assignments.append((face, candidate))
        return assignments

    def _cut_topology(
        self,
        operation: _Operation,
        faces: list[TopoDS_Shape],
        feature_id: str,
        *,
        source_faces=None,
    ) -> list[tuple[TopoDS_Shape, dict[str, Any]]]:
        assignments: list[tuple[TopoDS_Shape, dict[str, Any]]] = []
        base = self._operations.get(id(operation.inputs["base"]))
        tool = self._operations.get(id(operation.inputs.get("tool")))
        for source in source_faces if source_faces is not None else base.faces if base else []:
            source_face, source_candidate = source
            modified = list(operation.builder.Modified(source_face))
            generated = list(operation.builder.Generated(source_face))
            images: list[tuple[TopoDS_Shape, str]] = []
            for face in faces:
                relation = None
                if any(face.IsSame(item) for item in modified):
                    relation = "modified"
                elif any(face.IsSame(item) for item in generated):
                    relation = "generated"
                elif face.IsSame(source_face) and not operation.builder.IsDeleted(source_face):
                    relation = "unchanged"
                if relation:
                    images.append((face, relation))
            for face, relation in images:
                previous_status = source_candidate["provenance"]["semantic_status"]
                status = "split" if len(images) > 1 else previous_status
                if relation == "generated" and status == "stable":
                    status = "generated"
                candidate = self._candidate(
                    face,
                    source_candidate["feature_id"],
                    source_candidate["role"],
                    status=status,
                    operation=operation.kind,
                    relation=relation,
                    source_id=source_candidate["id"],
                    modifying_feature_id=feature_id,
                    operation_id=feature_id,
                    source_count=1,
                    image_count=len(images),
                )
                assignments.append((face, candidate))

        # An ordinary Cut may retain a tool surface with opposite orientation.
        # IsSame deliberately ignores orientation; Modified is native ancestry,
        # not a geometric comparison. Generated-only, split and aliased sources
        # remain diagnostic snapshot identities, as do all patterned cuts.
        tool_images = []
        # A base may already have lost an aliased/merged tool identity. Do not
        # resurrect that identity from a second operand merely because it no
        # longer appears among the base's current snapshot-local descriptors.
        base_ids, seen = set(), set()
        pending = (
            [base] if base and tool and self._cut_tool_lineage and operation.kind == "cut" else []
        )
        while pending:
            ancestor = pending.pop()
            if id(ancestor) in seen:
                continue
            seen.add(id(ancestor))
            base_ids.update(candidate["id"] for _, candidate in ancestor.faces)
            pending.extend(
                self._operations[id(shape)]
                for shape in ancestor.inputs.values()
                if id(shape) in self._operations
            )
        for tool_face, source in tool.faces if tool else []:
            modified = list(operation.builder.Modified(tool_face))
            generated = list(operation.builder.Generated(tool_face))
            images = []
            for face in faces:
                relation = None
                if any(face.IsSame(item) for item in modified):
                    relation = "tool_modified"
                elif any(face.IsSame(item) for item in generated):
                    relation = "tool_generated"
                elif face.IsSame(tool_face) and not operation.builder.IsDeleted(tool_face):
                    relation = "tool_unchanged"
                if relation:
                    images.append((face, relation))
            tool_images.append((source, images))
        for face in faces:
            sources = [
                (source, images, relation)
                for source, images in tool_images
                for image, relation in images
                if image.IsSame(face)
            ]
            if not sources:
                continue
            source, images, relation = sources[0]
            stable = (
                self._cut_tool_lineage
                and operation.kind == "cut"
                and len(sources) == 1
                and len(images) == 1
                and source["provenance"]["semantic_status"] == "stable"
                and source["id"] not in base_ids
                and relation in {"tool_modified", "tool_unchanged"}
                and sum(item["id"] == source["id"] for item, _ in tool_images) == 1
            )
            if stable:
                candidate = self._candidate(
                    face,
                    source["feature_id"],
                    source["role"],
                    operation="cut",
                    relation=relation,
                    source_id=source["id"],
                    modifying_feature_id=feature_id,
                    operation_id=feature_id,
                    source_count=1,
                    image_count=1,
                )
            else:
                candidate = self._candidate(
                    face,
                    feature_id,
                    "cut.wall",
                    status="generated",
                    operation=operation.kind,
                    relation="tool_surface",
                    sources=[item["id"] for item, _, _ in sources],
                )
            assignments.append((face, candidate))
        return assignments

    def tessellate(
        self,
        shape: TopoDS_Shape,
        linear_deflection: float = 0.1,
    ) -> dict[str, Any]:
        """Produce a display mesh; per-face vertices may repeat at CAD seams."""
        self._validate(shape)
        deflection = _number(linear_deflection, "linear_deflection", positive=True)
        # Conservative analytic-circle preflight for the currently supported
        # profile/extrusion family. Never silently loosen the requested mesh.
        estimated_points = 0
        for edge in _subshapes(shape, TopAbs_EDGE):
            curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
            if curve.GetType() == GeomAbs_Circle:
                radius = curve.Circle().Radius()
                half_angle = math.acos(max(-1.0, min(1.0, 1.0 - deflection / radius)))
                if half_angle == 0:
                    raise KernelError(
                        "Requested tessellation exceeds the analytic-circle resource budget"
                    )
                estimated_points += 3 * math.ceil(math.pi / min(half_angle, 0.1))
        if estimated_points > 100_000:
            raise KernelError("Requested tessellation exceeds the analytic-circle resource budget")
        mesher = BRepMesh_IncrementalMesh(shape, deflection, False, 0.2, True)
        if not mesher.IsDone():
            raise KernelError("OCCT could not tessellate the shape")
        vertices: list[list[float]] = []
        triangles: list[list[int]] = []
        triangle_face_ids: list[str | None] = []
        operation = self._operations.get(id(shape))
        for item in _subshapes(shape, TopAbs_FACE):
            face = TopoDS.Face(item)
            location = TopLoc_Location()
            mesh = BRep_Tool.Triangulation_s(face, location)
            if mesh is None:
                raise KernelError("A face has no triangulation")
            if (
                len(vertices) + mesh.NbNodes() > 100_000
                or len(triangles) + mesh.NbTriangles() > 200_000
            ):
                raise KernelError(
                    "Tessellation exceeds the 100000-vertex/200000-triangle output budget"
                )
            offset = len(vertices)
            transform = location.Transformation()
            vertices.extend(
                list(mesh.Node(i).Transformed(transform).Coord())
                for i in range(1, mesh.NbNodes() + 1)
            )
            source_id = (
                next(
                    (candidate["id"] for old, candidate in operation.faces if face.IsSame(old)),
                    None,
                )
                if operation
                else None
            )
            for index in range(1, mesh.NbTriangles() + 1):
                a, b, c = mesh.Triangle(index).Get()
                if face.Orientation() == TopAbs_REVERSED:
                    b, c = c, b
                indices = [offset + a - 1, offset + b - 1, offset + c - 1]
                # OCCT spherical blend poles can contain coincident UV nodes.
                # These are zero-area parameterization triangles, not surface
                # facets. Omit only geometrically coincident-node triangles;
                # the unchanged manifold checker still rejects any actual gap.
                points = [vertices[i] for i in indices]
                if any(
                    math.dist(points[i], points[j]) <= 1e-12 for i, j in ((0, 1), (1, 2), (2, 0))
                ):
                    continue
                triangles.append(indices)
                triangle_face_ids.append(source_id)
        return {
            "vertices": vertices,
            "triangles": triangles,
            "triangle_face_ids": triangle_face_ids,
        }

    def export_step(self, shape: TopoDS_Shape, path: str | Path) -> None:
        self._require_single_solid(shape)
        writer = STEPControl_Writer()
        if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
            raise KernelError("STEP shape transfer failed")
        if writer.Write(str(path)) != IFSelect_RetDone:
            raise KernelError(f"Could not write STEP file: {path}")

    def export_assembly_step(
        self, assembly_name: str, parts: list | tuple, instances: list | tuple, path: str | Path
    ) -> None:
        """Write one named XCAF assembly using exact local Part definitions.

        Parts contain id/name/shape; instances contain id/name/part_id/frame.
        Frames are already-evaluated rigid world placements, as in transformed().
        References use stable Part IDs, never names or geometric similarity.
        Only the assembly root is transferred: uninstantiated definitions are not
        free solids in the STEP file. Names and reuse are exchange data; canonical
        application IDs, feature history, mates and provenance are not exported.

        The caller owns fresh canonical replay and atomic destination replacement.
        All inputs and solids are checked before this temporary path is written.
        """
        definitions, occurrences, placements = _assembly_step_inputs(
            assembly_name, parts, instances
        )
        for part in definitions.values():
            if not isinstance(part["shape"], TopoDS_Shape):
                raise KernelError("Assembly STEP Part requires an exact native shape")
            self._require_single_solid(part["shape"])

        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        from OCP.STEPCAFControl import STEPCAFControl_Writer
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDocStd import TDocStd_Document
        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        try:
            document = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
            XCAFDoc_DocumentTool.SetLengthUnit_s(document, 0.001)  # Internal mm, in metres.
            shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
            root = shapes.NewShape()
            TDataStd_Name.Set_s(root, TCollection_ExtendedString(assembly_name, True))
            labels = {}
            original_shapes = []
            for part_id, part in definitions.items():
                shape = part["shape"]
                if any(shape.IsPartner(previous) for previous in original_shapes):
                    # STEP transfer keys by topology, even with explicit XCAF
                    # labels. Distinct Part IDs sharing a replay handle need
                    # distinct topology; retain their exact curves/surfaces.
                    copied = BRepBuilderAPI_Copy(shape, False, False)
                    if not copied.IsDone():
                        raise KernelError("Assembly STEP definition topology copy failed")
                    shape = copied.Shape()
                    if (
                        shape.IsPartner(part["shape"])
                        or not shape.Location().IsEqual(part["shape"].Location())
                        or shape.Orientation() != part["shape"].Orientation()
                    ):
                        raise KernelError("Assembly STEP definition identity copy is invalid")
                    self._require_single_solid(shape)
                original_shapes.append(part["shape"])
                label = shapes.NewShape()
                shapes.SetShape(label, shape)
                TDataStd_Name.Set_s(label, TCollection_ExtendedString(part["name"], True))
                labels[part_id] = label
            for instance_id, instance in occurrences.items():
                transform = gp_Trsf()
                transform.SetValues(*placements[instance_id])
                component = shapes.AddComponent(
                    root, labels[instance["part_id"]], TopLoc_Location(transform)
                )
                if component.IsNull():
                    raise KernelError("Could not create Assembly STEP component")
                TDataStd_Name.Set_s(component, TCollection_ExtendedString(instance["name"], True))
            shapes.UpdateAssemblies()
            writer = STEPCAFControl_Writer()
            writer.SetNameMode(True)
            writer.SetColorMode(False)
            writer.SetLayerMode(False)
            writer.SetPropsMode(False)
            writer.SetCleanDuplicates(False)
            if not writer.Transfer(root, STEPControl_AsIs):
                raise KernelError("Assembly STEP transfer failed")
            if writer.Write(str(path)) != IFSelect_RetDone:
                raise KernelError(f"Could not write Assembly STEP file: {path}")
        except KernelError:
            raise
        except Exception as exc:
            raise KernelError(f"OCCT Assembly STEP export failed: {exc}") from exc

    def _require_single_solid(
        self, shape: TopoDS_Shape, *, linear_tolerance_mm: float | None = None
    ) -> dict[str, Any]:
        """Shared part-export/assembly gate; wrappers must contain only one solid.

        Assembly queries additionally require stored tolerances and coordinate
        precision compatible with their requested linear resolution.
        """
        stats = self.inspect(shape)
        if stats["solids"] != 1:
            raise KernelError("Part export requires exactly one valid solid")
        pending, solid_occurrences = [shape], 0
        while pending:
            item = pending.pop()
            if item.ShapeType() == TopAbs_SOLID:
                solid_occurrences += 1
            elif item.ShapeType() in (TopAbs_COMPOUND, TopAbs_COMPSOLID):
                children = TopoDS_Iterator(item)
                while children.More():
                    pending.append(children.Value())
                    children.Next()
            else:
                raise KernelError(
                    "Single-solid geometry must not contain loose faces, edges or vertices"
                )
        if solid_occurrences != 1:
            raise KernelError("Part export requires exactly one valid solid occurrence")
        shells = _subshapes(shape, TopAbs_SHELL)
        if not shells or not all(BRep_Tool.IsClosed_s(shell) for shell in shells):
            raise KernelError("Single-solid geometry requires every shell to be closed")
        stats["volume"] = _exact_volume(shape)
        if not math.isfinite(stats["volume"]) or stats["volume"] <= 0:
            raise KernelError("Part export requires positive solid volume")
        if not math.isfinite(stats["area"]) or stats["area"] <= 0:
            raise KernelError("Single-solid geometry requires finite positive surface area")
        if linear_tolerance_mm is not None:
            tolerances = [
                BRep_Tool.Tolerance_s(cast(item))
                for kind, cast in (
                    (TopAbs_VERTEX, TopoDS.Vertex),
                    (TopAbs_EDGE, TopoDS.Edge),
                    (TopAbs_FACE, TopoDS.Face),
                )
                for item in _subshapes(shape, kind)
            ]
            if not tolerances or any(not math.isfinite(v) or v < 0 for v in tolerances):
                raise _AssemblyQueryError(
                    "invalid_shape_tolerance", "Solid has invalid stored tolerances"
                )
            if max(tolerances) > linear_tolerance_mm * (1 + 1e-12):
                raise _AssemblyQueryError(
                    "excessive_shape_tolerance",
                    f"Stored B-rep tolerance {max(tolerances):.12g} mm exceeds requested "
                    f"linear resolution {linear_tolerance_mm:.12g} mm. "
                    "For display replay, explicitly choose a suitable replay tolerance; "
                    "verification resolution remains a separate policy.",
                )
            coordinate_size = max(abs(v) for v in _shape_bounds(shape))
            if 32 * math.ulp(coordinate_size) > linear_tolerance_mm:
                raise _AssemblyQueryError(
                    "coordinate_resolution",
                    "World-coordinate precision cannot support the requested linear resolution",
                )
        return stats

    def manufacturing_check(
        self,
        shape: TopoDS_Shape,
        linear_deflection: float = 0.1,
    ) -> dict[str, Any]:
        """Single-solid/mesh checks only; not a manufacturability certification."""
        stats = self._require_single_solid(shape)
        mesh = self.tessellate(shape, linear_deflection)
        return {
            "brep": stats,
            "mesh": check_watertight_mesh(mesh),
            "linear_deflection_mm": linear_deflection,
        }

    def export_stl(
        self,
        shape: TopoDS_Shape,
        path: str | Path,
        linear_deflection: float = 0.1,
    ) -> dict[str, Any]:
        """Write OCCT binary STL only after checking both source and encoded mesh.

        STL carries neither units nor CAD feature history. This application's
        coordinates are millimetres; consumers must select that import unit.
        """
        checks = self.manufacturing_check(shape, linear_deflection)
        source_mesh = self.tessellate(shape, linear_deflection)
        # Independent strict export precision ceiling. This may reject large
        # translated coordinates even when coarse tessellation was requested.
        allowed_error = min(1e-5, float(linear_deflection) * 0.1)
        packed_vertices = []
        maximum_error = 0.0
        for vertex in source_mesh["vertices"]:
            try:
                packed = struct.pack("<3f", *vertex)
            except (OverflowError, struct.error) as exc:
                raise KernelError("STL coordinates exceed finite binary32 range") from exc
            encoded_vertex = struct.unpack("<3f", packed)
            maximum_error = max(maximum_error, math.dist(vertex, encoded_vertex))
            packed_vertices.append(packed)
        if maximum_error > allowed_error:
            raise KernelError(
                f"STL binary32 coordinate error {maximum_error:.9g} mm exceeds "
                f"allowed {allowed_error:.9g} mm; move the part near the origin or use STEP"
            )
        checks["encoding"] = {
            "maximum_vertex_error_mm": maximum_error,
            "allowed_vertex_error_mm": allowed_error,
            "independent_precision_ceiling_mm": 1e-5,
        }
        writer = StlAPI_Writer()
        writer.ASCIIMode = False
        buffer = BytesIO()
        if not writer.Write(shape, buffer):
            raise KernelError("OCCT could not encode binary STL")
        encoded = buffer.getvalue()
        if len(encoded) < 84:
            raise KernelError("OCCT produced an incomplete binary STL")
        count = struct.unpack_from("<I", encoded, 80)[0]
        if len(encoded) != 84 + 50 * count:
            raise KernelError("OCCT produced an inconsistent binary STL size")
        # OCCT writes degenerate pole triangles retained in its UV mesh.
        # Remove only exact duplicate encoded vertices, matching the checked
        # zero-area source filtering; manifold and source equality still gate.
        records = [encoded[84 + 50 * i : 84 + 50 * (i + 1)] for i in range(count)]
        records = [
            record for record in records if len({record[12:24], record[24:36], record[36:48]}) == 3
        ]
        count = len(records)
        encoded = encoded[:80] + struct.pack("<I", count) + b"".join(records)
        vertices = []
        encoded_triangles = Counter()
        for index in range(count):
            values = struct.unpack_from("<9f", encoded, 84 + 50 * index + 12)
            vertices.extend([list(values[offset : offset + 3]) for offset in (0, 3, 6)])
            encoded_triangles[
                tuple(
                    sorted(struct.pack("<3f", *values[offset : offset + 3]) for offset in (0, 3, 6))
                )
            ] += 1
        source_triangles = Counter(
            tuple(sorted(packed_vertices[index] for index in triangle))
            for triangle in source_mesh["triangles"]
        )
        if encoded_triangles != source_triangles:
            raise KernelError("STL encoded triangles differ from the checked source tessellation")
        checks["encoded_mesh"] = check_watertight_mesh(
            {
                "vertices": vertices,
                "triangles": [[3 * i, 3 * i + 1, 3 * i + 2] for i in range(count)],
            }
        )
        Path(path).write_bytes(encoded)
        return checks

    def import_step_data(self, asset):
        """Read an immutable bounded Part payload, never a saved external file path."""
        from tempfile import TemporaryDirectory

        from .step_asset import decode_step

        data = decode_step(asset)
        with TemporaryDirectory(prefix="mcad-step-") as directory:
            path = Path(directory) / "part.step"
            path.write_bytes(data)
            reader = STEPControl_Reader()
            if reader.ReadFile(str(path)) != IFSelect_RetDone:
                raise KernelError("OCCT could not read the embedded STEP exchange data")
            if reader.NbRootsForTransfer() != 1:
                raise KernelError("STEP import requires exactly one transferable Part root")
            # OCCT system unit is millimetres; honor the file's declared unit conversion.
            reader.SetSystemLengthUnit(1.0)
            if not reader.TransferRoots():
                raise KernelError("STEP file contains no transferable solid")
            shape = reader.OneShape()
            self._validate(shape, solid=True)
            self._require_single_solid(shape)
            return self._remember(_Operation(shape, "import_step"))

    def import_step(self, path: str | Path) -> TopoDS_Shape:
        reader = STEPControl_Reader()
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            raise KernelError(f"Could not read STEP file: {path}")
        if not reader.TransferRoots():
            raise KernelError("STEP file contains no transferable shape")
        shape = reader.OneShape()
        self._validate(shape)
        # STEP transfers geometry, not this application's feature history.
        return self._remember(_Operation(shape, "import_step"))
