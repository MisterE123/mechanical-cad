"""Strict native-free manufacturing evidence for explicitly negotiated results.

These checks validate the reported contract and bind it to replay evidence. They
neither reproduce kernel geometry nor certify physical manufacturability. A mesh
argument is an already-validated tessellation; this module binds its counts and
leaves coordinates, triangle indices, and face provenance to the mesh validator.
"""

from __future__ import annotations

import math

MAX_VERTICES = 100_000
MAX_TRIANGLES = 200_000
MAX_MEASURE = 1e100
WELD_TOLERANCE_MM = 1e-7
STL_PRECISION_CEILING_MM = 1e-5
_STATS_FIELDS = {"valid", "volume", "area", "solids", "faces"}
_MESH_FLAGS = {"watertight", "consistently_oriented", "vertex_manifold"}
_MESH_FIELDS = _MESH_FLAGS | {"vertices", "triangles", "signed_volume", "weld_tolerance"}
_CHECK_FIELDS = {"brep", "mesh", "linear_deflection_mm"}
_ENCODED_FIELDS = {"encoding", "encoded_mesh"}
_ENCODING_FIELDS = {
    "maximum_vertex_error_mm",
    "allowed_vertex_error_mm",
    "independent_precision_ceiling_mm",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _keys(value, fields, label):
    _require(
        type(value) is dict and len(value) == len(fields) and set(value) == fields,
        f"invalid {label} fields",
    )


def _number(value, label, *, minimum=0, maximum=MAX_MEASURE, positive=False):
    # Compare bounds before math.isfinite so enormous Python integers fail as
    # ValueError rather than overflowing during an implicit float conversion.
    _require(
        type(value) in (int, float)
        and minimum <= value <= maximum
        and math.isfinite(value)
        and (not positive or value > 0),
        f"invalid {label}",
    )


def _count(value, label, *, minimum=1, maximum=MAX_TRIANGLES):
    _require(type(value) is int and minimum <= value <= maximum, f"invalid {label}")


def validate_stats(stats):
    """Validate the exact OCCT valid-single-solid statistics contract.

    Result-v2 profile/sketch outputs have no solid stats; their caller must
    validate that discriminant separately instead of passing None here.
    """
    _keys(stats, _STATS_FIELDS, "solid statistics")
    _require(stats["valid"] is True, "solid statistics are not valid")
    _count(stats["solids"], "solid count", maximum=1)
    _count(stats["faces"], "solid face count")
    _number(stats["volume"], "solid volume", positive=True)
    _number(stats["area"], "solid area", positive=True)


def _tessellation_counts(mesh):
    _keys(mesh, {"vertices", "triangles", "triangle_face_ids"}, "tessellation")
    _require(type(mesh["vertices"]) is list, "invalid tessellation vertices")
    _require(type(mesh["triangles"]) is list, "invalid tessellation triangles")
    vertices, triangles = len(mesh["vertices"]), len(mesh["triangles"])
    _count(vertices, "tessellation vertex count", minimum=4, maximum=MAX_VERTICES)
    _count(triangles, "tessellation triangle count", minimum=4)
    return vertices, triangles


def validate_mesh_report(report, *, mesh=None):
    """Validate a successful numerical-seam-welded closed-mesh report.

    Welded vertices may be fewer than per-face tessellation vertices. Triangle
    counts do agree: the kernel rejects duplicate and collapsed triangles rather
    than silently removing them. A closed triangulation has an even face count.
    The report counts all input vertices, so no unused-vertex/Euler assumption is
    made here; disconnected closed shells are also possible.
    """
    _keys(report, _MESH_FIELDS, "manufacturing mesh report")
    _require(all(report[name] is True for name in _MESH_FLAGS), "unverified manifold mesh")
    vertices, triangles = report["vertices"], report["triangles"]
    _count(vertices, "welded vertex count", minimum=4, maximum=MAX_VERTICES)
    _count(triangles, "checked triangle count", minimum=4)
    _require(
        triangles % 2 == 0 and triangles <= vertices * (vertices - 1) * (vertices - 2) // 6,
        "inconsistent closed-mesh counts",
    )
    _number(report["weld_tolerance"], "mesh weld tolerance", positive=True)
    _require(report["weld_tolerance"] == WELD_TOLERANCE_MM, "unsupported mesh weld policy")
    _number(report["signed_volume"], "oriented mesh volume", positive=True)
    _require(
        report["signed_volume"] > WELD_TOLERANCE_MM**3,
        "mesh volume does not exceed its numerical weld threshold",
    )
    if mesh is not None:
        source_vertices, source_triangles = _tessellation_counts(mesh)
        _require(triangles == source_triangles, "checked triangle count differs from tessellation")
        _require(vertices <= source_vertices, "welding cannot add tessellation vertices")


def validate_geometry_check(
    checks,
    *,
    linear_deflection,
    stats=None,
    mesh=None,
    encoded=False,
    allow_partial_encoded=False,
):
    """Validate complete checks, optionally bound to replay stats/tessellation.

    encoded=True requires the full successful STL report. Only callers handling
    an unsuccessful STL export may set allow_partial_encoded=True: actions.py
    retains its complete base manufacturing check if encoding/writing fails.
    Either the complete encoding pair or neither field is accepted; an isolated
    encoding/encoded_mesh field never proves a completed encoding gate.
    """
    _require(type(encoded) is bool and type(allow_partial_encoded) is bool, "invalid check mode")
    _require(not allow_partial_encoded or encoded, "partial encoding requires STL check mode")
    _number(linear_deflection, "requested deflection", minimum=0.001, maximum=10)
    _require(type(checks) is dict and len(checks) in (3, 5), "missing or invalid geometry check")
    fields = set(checks)
    complete_encoded = fields == _CHECK_FIELDS | _ENCODED_FIELDS
    _require(
        (encoded and complete_encoded)
        or (fields == _CHECK_FIELDS and (not encoded or allow_partial_encoded)),
        "invalid geometry check fields or incomplete STL evidence",
    )
    _number(checks["linear_deflection_mm"], "checked deflection", minimum=0.001, maximum=10)
    _require(
        checks["linear_deflection_mm"] == linear_deflection,
        "checked tessellation tolerance differs from request",
    )
    brep, report = checks["brep"], checks["mesh"]
    validate_stats(brep)
    validate_mesh_report(report, mesh=mesh)
    _require(brep["faces"] <= report["triangles"], "B-rep faces exceed tessellated triangles")
    if stats is not None:
        validate_stats(stats)
        _require(brep["faces"] == stats["faces"], "checked face count differs from replay")
        for field in ("volume", "area"):
            _require(
                math.isclose(brep[field], stats[field], rel_tol=1e-12, abs_tol=1e-10),
                f"checked {field} differs from replay",
            )
    if not complete_encoded:
        return
    encoded_mesh, encoding = checks["encoded_mesh"], checks["encoding"]
    validate_mesh_report(encoded_mesh, mesh=mesh)
    _require(
        encoded_mesh["triangles"] == report["triangles"],
        "encoded triangle count differs from checked source",
    )
    _keys(encoding, _ENCODING_FIELDS, "STL encoding")
    for name in _ENCODING_FIELDS:
        _number(encoding[name], name)
    expected_error = min(STL_PRECISION_CEILING_MM, float(linear_deflection) * 0.1)
    _require(
        encoding["independent_precision_ceiling_mm"] == STL_PRECISION_CEILING_MM
        and encoding["allowed_vertex_error_mm"] == expected_error
        and encoding["maximum_vertex_error_mm"] <= expected_error,
        "STL encoding contradicts the independent precision policy",
    )
