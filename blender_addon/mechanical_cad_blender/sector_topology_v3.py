"""Dormant exact sector provenance checks, without native or owner imports.

These are source-bound wire consistency checks. Native construction history and
R0/C0 qualification remain the separately checked kernel adapter's responsibility.
"""

from __future__ import annotations

from fractions import Fraction

from .sketch_bridge import _keys, _require
from .sketch_contracts_v3 import _arc_geometry, normalize_sketch_v3
from .topology_evidence import validate_signature, validate_topology


def _normal(plane):
    """The reviewed exact, origin-zero signed-permutation native frame domain."""
    _require(all(value == 0 for value in plane["origin"]), "unsupported native world origin")
    w, x, y, z = (Fraction(value) for value in plane["quaternion"])
    norm = w * w + x * x + y * y + z * z
    _require(norm > 0, "invalid quaternion")
    matrix = (
        (norm - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), norm - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), norm - 2 * (x * x + y * y)),
    )
    rows = tuple(tuple(value / norm for value in row) for row in matrix)
    _require(all(value in (-1, 0, 1) for row in rows for value in row), "unsupported native frame")
    _require(
        all(sum(value != 0 for value in row) == 1 for row in rows)
        and all(sum(rows[j][k] != 0 for j in range(3)) == 1 for k in range(3)),
        "unsupported native frame",
    )
    return [float(row[2]) for row in rows]


def validate_sector_topology(feature, source, *, source_features, result_features):
    """Check exact sector roles and signatures, otherwise use unchanged topology."""
    sources = {item["id"]: item for item in source_features}
    results = {item["id"]: item for item in result_features}
    profile = (
        source
        if source["kind"] == "sketch_constrained"
        else sources.get(source["inputs"].get("profile"))
    )
    profile_output = (results.get(profile["id"], {}).get("output") or {}) if profile else {}
    if profile_output.get("profile", {}).get("region_kind") != "curve_loop":
        return validate_topology(
            feature["topology"],
            feature_id=feature["id"],
            kind=feature["kind"],
            mesh=feature["mesh"],
            source_features=source_features,
        )
    _require(
        source["kind"] in {"sketch_constrained", "extrude"}, "unsupported sector topology operation"
    )
    solved = normalize_sketch_v3(results[profile["id"]]["sketch"]["solved"], numeric=True)
    _require(
        len(solved["arcs"]) == 1 and len(solved["lines"]) == 2 and not solved["circles"],
        "unsupported sector boundary count",
    )
    normal = _normal(solved["plane"])
    arc = solved["arcs"][0]
    radius = _arc_geometry(solved)[arc["id"]].start_radius
    solid = source["kind"] == "extrude"
    roles = (
        {
            "cap.start",
            "cap.end",
            "side.arc." + arc["id"],
            *("side.line." + line["id"] for line in solved["lines"]),
        }
        if solid
        else {"profile"}
    )
    topology = feature["topology"]
    _require(type(topology) is list and len(topology) == len(roles), "sector has wrong face count")
    by_id, seen = {}, set()
    for face in topology:
        _keys(face, {"id", "feature_id", "kind", "role", "signature", "provenance"})
        role = face["role"]
        _require(
            type(role) is str and role in roles and role not in seen,
            "wrong or repeated sector face role",
        )
        identifier = f"{source['id']}/face/{role}"
        _require(
            face["id"] == identifier
            and face["feature_id"] == source["id"]
            and face["kind"] == "face",
            "sector face identity mismatch",
        )
        seen.add(role)
        by_id[identifier] = face
        side = role.startswith("side.")
        relation = (
            "generated_from_profile_edge"
            if side
            else (
                {"cap.start": "first_shape", "cap.end": "last_shape"}.get(
                    role, "constructed_profile"
                )
            )
        )
        expected = {
            "semantic_status": "stable",
            "kernel": "OCCT",
            "operation": "extrude" if solid else "curve_profile",
            "operation_id": source["id"],
            "relation": relation,
            "evolution": relation,
        }
        if side:
            expected["source_boundary"] = role[len("side.") :]
        _keys(face["provenance"], set(expected))
        _require(
            face["provenance"] == expected, "sector provenance differs from exact authored boundary"
        )
        signature = face["signature"]
        validate_signature(signature)
        cylinder = role == "side.arc." + arc["id"]
        _require(
            signature["surface"] == ("cylinder" if cylinder else "plane"),
            "sector face has wrong surface",
        )
        if cylinder:
            _require(
                signature["radius"] == radius and signature["axis"] == [-value for value in normal],
                "cylinder radius/axis differs from canonical source",
            )
        elif role in {"profile", "cap.start", "cap.end"}:
            expected_normal = [-value for value in normal] if role == "cap.start" else normal
            _require(
                signature["normal"] == expected_normal,
                "profile/cap orientation differs from exact frame",
            )
        else:
            _require(
                sum(a * b for a, b in zip(signature["normal"], normal, strict=True)) == 0,
                "radial face normal leaves profile plane",
            )
    mesh = feature["mesh"]
    _require(
        type(mesh) is dict
        and type(mesh.get("triangle_face_ids")) is list
        and len(mesh["triangle_face_ids"]) == len(mesh["triangles"]),
        "missing sector face mesh",
    )
    _require(
        all(type(value) is str for value in mesh["triangle_face_ids"])
        and set(mesh["triangle_face_ids"]) == set(by_id),
        "sector tessellation omitted or invented face",
    )
    if solid:
        _require(
            type(feature["stats"]["faces"]) is int and feature["stats"]["faces"] == 5,
            "sector solid requires exactly five faces",
        )
    return by_id
