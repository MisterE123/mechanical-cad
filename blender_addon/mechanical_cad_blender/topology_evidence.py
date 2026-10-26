"""Strict native-free face metadata and mesh-to-face binding for opted-in results.

Semantic roles come from authored feature/entity identities. This is a protocol
consistency check, not an independent proof that OCCT built the claimed surface.
"""

from __future__ import annotations

import json
import math
import re
from hashlib import sha256

from .sketch_bridge import _identifier, _keys, _number, _require


def _blend_surface_role(pair, count):
    if count == 1:
        return "blend.surface"
    return (
        "blend.surface."
        + sha256(
            json.dumps(sorted(pair), ensure_ascii=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def validate_signature(signature):
    """Closed OCCT surface kinds; nonanalytic surfaces carry area/centroid only."""
    _require(type(signature) is dict, "face signature must be an object")
    surface = signature.get("surface")
    _require(
        type(surface) is str
        and surface
        in {
            "plane",
            "cylinder",
            "cone",
            "sphere",
            "torus",
            "beziersurface",
            "bsplinesurface",
            "surfaceofrevolution",
            "surfaceofextrusion",
            "offsetsurface",
            "othersurface",
        },
        "unsupported face surface",
    )
    fields = {"surface", "area", "centroid"}
    fields |= (
        {"normal"} if surface == "plane" else {"radius", "axis"} if surface == "cylinder" else set()
    )
    if surface == "cylinder" and "axis_origin" in signature:
        fields.add("axis_origin")
        origin = signature["axis_origin"]
        _require(type(origin) is list and len(origin) == 3, "invalid cylinder axis origin")
        for value in origin:
            _number(value, bound=1e12)
    _keys(signature, fields)
    _require(_number(signature["area"], minimum=0, bound=1e100) > 0, "face has no positive area")
    center = signature["centroid"]
    _require(type(center) is list and len(center) == 3, "invalid face centroid")
    for value in center:
        _number(value, bound=1e12)
    if surface not in {"plane", "cylinder"}:
        return
    direction = signature["normal" if surface == "plane" else "axis"]
    _require(type(direction) is list and len(direction) == 3, "invalid face direction")
    values = [_number(value, bound=1.0000001) for value in direction]
    _require(math.isclose(sum(v * v for v in values), 1, abs_tol=1e-7), "non-unit face direction")
    if surface == "cylinder":
        _require(_number(signature["radius"], minimum=0, bound=1e12) > 0, "invalid cylinder radius")


def _origin_features(source, features):
    """Follow only identity-bearing input ports, never unrelated profile tools."""
    allowed, pending = set(), [source["id"]]
    while pending:
        identifier = pending.pop()
        _require(identifier in features, "invalid topology ancestry")
        if identifier in allowed:
            continue
        allowed.add(identifier)
        current = features[identifier]
        if current["kind"] in {"union", "intersection", "cut"}:
            pending.extend(current["inputs"][port] for port in ("base", "tool"))
        elif current["kind"] == "shell" and current.get("opening_faces"):
            pending.append(current["inputs"]["base"])
        elif current["kind"] in {
            "cut",
            "fillet",
            "chamfer",
            "transform",
            "mirror",
            "linear_cut_pattern",
            "circular_cut_pattern",
        }:
            pending.append(current["inputs"]["base"])
    return allowed


def _roles(source, features):
    kind = source["kind"]
    if kind in {
        "sketch_rectangle",
        "sketch_circle",
        "sketch_constrained",
        "sketch_face_rectangle",
        "sketch_face_circle",
    }:
        return {"profile", "unresolved"}
    if kind == "shell" and source.get("opening_faces"):
        base = features[source["inputs"]["base"]]
        roles = {"unresolved"}
        for origin in _origin_features(base, features):
            for role in _roles(features[origin], features) - {"unresolved"}:
                identifier = f"{origin}/face/{role}"
                roles.add(
                    (
                        "shell.opening_lip"
                        if len(source["opening_faces"]) == 1
                        else "shell.opening_lip." + sha256(identifier.encode()).hexdigest()
                    )
                    if identifier in source["opening_faces"]
                    else "shell.inner." + sha256(identifier.encode()).hexdigest()
                )
        return roles
    if kind == "spur_gear":
        return {"cap.start", "cap.end", "side.bore", "unresolved"}
    if kind == "cut":
        return {"cut.wall", "unresolved"}
    if kind in {"fillet", "chamfer"}:
        pairs = source.get("edge_pairs") or (
            [source["edge_faces"]] if source.get("edge_faces") else []
        )
        return {"unresolved"} | {_blend_surface_role(pair, len(pairs)) for pair in pairs}
    if kind in {
        "union",
        "intersection",
        "fillet",
        "chamfer",
        "transform",
        "mirror",
        "linear_pattern",
        "linear_cut_pattern",
        "circular_cut_pattern",
        "circular_pattern",
        "shell",
        "import_step",
        "loft",
        "sweep",
    }:
        return {"unresolved"}
    _require(
        kind in {"extrude", "extrude_through", "extrude_to_face", "extrude_symmetric", "revolve"},
        "unsupported topology source feature",
    )
    profile = features[source["inputs"]["profile"]]
    roles = {"cap.start", "cap.end", "unresolved"}
    if profile["kind"] in {"sketch_rectangle", "sketch_face_rectangle"}:
        return roles | {"side.x_min", "side.x_max", "side.y_min", "side.y_max"}
    if profile["kind"] in {"sketch_circle", "sketch_face_circle"}:
        return roles | {"side.circle"}
    _require(profile["kind"] == "sketch_constrained", "unsupported extrusion profile")
    return (
        roles
        | {"side.line." + line["id"] for line in profile["sketch"]["lines"]}
        | {"side.circle." + circle["id"] for circle in profile["sketch"].get("circles", [])}
        | {"side.arc." + arc["id"] for arc in profile["sketch"].get("arcs", [])}
    )


def _role_allowed(role, source, features):
    # Construction-owned roles have bounded syntax, independent of count
    # expressions. Full replay separately binds source identity and actual count.
    if source["kind"] in {"linear_cut_pattern", "circular_cut_pattern"}:
        match = re.fullmatch(r"pattern\.copy\.(0|[1-9][0-9]?)\.([0-9a-f]{64})", role)
        return role == "unresolved" or (match is not None and int(match[1]) < 64)
    if source["kind"] == "shell" and source.get("opening_faces"):
        if re.fullmatch(r"shell\.inner\.[0-9a-f]{64}", role):
            return True
    return role in _roles(source, features)


def validate_topology(topology, *, feature_id, kind, mesh, source_features):
    """Return face-ID map after schema, provenance, ancestry and mesh binding."""
    _require(type(source_features) is list, "missing canonical topology sources")
    features = {source["id"]: source for source in source_features}
    _require(
        feature_id in features and features[feature_id]["kind"] == kind, "topology source mismatch"
    )
    origins = _origin_features(features[feature_id], features)
    _require(type(topology) is list and 1 <= len(topology) <= 200_000, "invalid topology count")
    by_id = {}
    for index, face in enumerate(topology):
        _keys(face, {"id", "feature_id", "role", "kind", "signature", "provenance"})
        _identifier(face["feature_id"])
        _require(face["feature_id"] in origins and face["kind"] == "face", "unrelated face origin")
        _require(
            type(face["id"]) is str and face["id"] not in by_id, "invalid or duplicate face ID"
        )
        _require(
            type(face["role"]) is str
            and _role_allowed(face["role"], features[face["feature_id"]], features),
            "unsupported semantic face role",
        )
        validate_signature(face["signature"])
        # Revolved boundaries can produce planes, cones, cylinders or general
        # swept surfaces. Only their actual cap faces are necessarily planar.
        revolved_side = features[face["feature_id"]]["kind"] == "revolve" and face[
            "role"
        ].startswith("side.")
        if (
            face["role"] not in {"cut.wall", "unresolved", "blend.surface"}
            and not face["role"].startswith(("shell.", "pattern.copy.", "blend.surface."))
            and not revolved_side
        ):
            expected_surface = (
                "cylinder"
                if face["role"] in {"side.circle", "side.bore"}
                or face["role"].startswith(("side.circle.", "side.arc."))
                else "plane"
            )
            _require(
                face["signature"]["surface"] == expected_surface,
                "face surface contradicts its analytic semantic role",
            )
        provenance = face["provenance"]
        required = {
            "semantic_status",
            "kernel",
            "operation",
            "operation_id",
            "relation",
            "evolution",
        }
        _keys(
            provenance,
            required
            | {
                "id_scope",
                "source_boundary",
                "source_faces",
                "occurrence",
                "source_id",
                "modifying_feature_id",
                "source_count",
                "image_count",
                "sources",
            },
            required,
        )
        status, relation = provenance["semantic_status"], provenance["relation"]
        _require(
            type(status) is str and status in {"stable", "split", "merged", "generated", "unknown"},
            "invalid semantic status",
        )
        _require(
            type(relation) is str
            and relation
            in {
                "constructed_profile",
                "first_shape",
                "last_shape",
                "generated_from_profile_edge",
                "generated_from_selected_edge",
                "offset_from_face",
                "rim_from_opening",
                "pattern_tool_face",
                "unchanged",
                "modified",
                "generated",
                "tool_surface",
                "tool_modified",
                "tool_unchanged",
                "multiple_sources",
                "no_history",
            },
            "invalid face evolution",
        )
        expected_operation = {
            "sketch_rectangle": {"rectangle"},
            "sketch_circle": {"circle"},
            "sketch_face_rectangle": {"sketch_face_rectangle"},
            "sketch_face_circle": {"sketch_face_circle"},
            "sketch_constrained": {"polygon", "circle_profile", "regions", "analytic_regions"},
            **{
                value: {value}
                for value in (
                    "union",
                    "intersection",
                    "revolve",
                    "fillet",
                    "chamfer",
                    "transform",
                    "mirror",
                    "linear_pattern",
                    "linear_cut_pattern",
                    "circular_cut_pattern",
                    "circular_pattern",
                    "shell",
                    "import_step",
                    "loft",
                    "sweep",
                )
            },
            "spur_gear": {"extrude"},
            "extrude": {"extrude"},
            "extrude_symmetric": {"extrude"},
            "extrude_through": {"extrude"},
            "extrude_to_face": {"extrude"},
            "cut": {"cut"},
        }[kind]
        _require(
            provenance["kernel"] == "OCCT"
            and provenance["operation_id"] == feature_id
            and type(provenance["operation"]) is str
            and provenance["operation"] in expected_operation
            and provenance["evolution"] == relation,
            "face provenance operation mismatch",
        )
        if (
            kind
            in {
                "union",
                "intersection",
                "fillet",
                "chamfer",
                "transform",
                "mirror",
                "linear_pattern",
                "linear_cut_pattern",
                "circular_cut_pattern",
                "circular_pattern",
                "shell",
                "import_step",
                "loft",
                "sweep",
            }
            and face["feature_id"] == feature_id
            and face["role"] != "blend.surface"
            and not face["role"].startswith(("shell.", "pattern.copy.", "blend.surface."))
        ):
            _require(
                face["feature_id"] == feature_id
                and face["role"] == "unresolved"
                and (
                    (
                        status == "unknown"
                        and relation == "no_history"
                        and provenance.get("sources") == []
                    )
                    or (
                        kind
                        in {"union", "intersection", "linear_cut_pattern", "circular_cut_pattern"}
                        and status == "merged"
                        and relation == "multiple_sources"
                        and type(provenance.get("sources")) is list
                        and len(provenance["sources"]) >= 2
                    )
                ),
                "operation without identity history must retain unknown snapshot topology",
            )
        if status == "stable":
            _require(
                face["id"] == f"{face['feature_id']}/face/{face['role']}"
                and "id_scope" not in provenance,
                "stable face identity differs from semantic role",
            )
            _require(
                face["role"] != "unresolved"
                and (kind != "cut" or face["feature_id"] != feature_id),
                "cut-generated or unresolved face cannot acquire stable semantic identity",
            )
        else:
            _require(
                face["id"] == f"snapshot:{feature_id}:face:{index}"
                and provenance.get("id_scope") == "evaluation_snapshot_only",
                "ambiguous face identity must remain snapshot-local",
            )
        if kind == "shell" and face["feature_id"] != feature_id:
            _require(
                bool(features[feature_id].get("opening_faces"))
                and status == "stable"
                and relation == "unchanged"
                and provenance.get("source_id") == face["id"]
                and face["id"] not in features[feature_id]["opening_faces"]
                and provenance.get("source_count") == 1
                and provenance.get("image_count") == 1,
                "shell may retain only an unchanged non-opening outer face",
            )
        if face["feature_id"] != feature_id:
            _require(
                kind
                in {
                    "cut",
                    "shell",
                    "fillet",
                    "chamfer",
                    "transform",
                    "mirror",
                    "union",
                    "intersection",
                    "linear_cut_pattern",
                    "circular_cut_pattern",
                }
                and provenance.get("modifying_feature_id") == feature_id
                and relation
                in {"unchanged", "modified", "generated", "tool_modified", "tool_unchanged"}
                and type(provenance.get("source_id")) is str
                and provenance["source_id"]
                and type(provenance.get("source_count")) is int
                and provenance["source_count"] == 1
                and type(provenance.get("image_count")) is int
                and 1 <= provenance["image_count"] <= len(topology),
                "inherited face lacks explicit modifier provenance",
            )
        if face["role"] == "unresolved":
            _require(
                (status, relation) in {("unknown", "no_history"), ("merged", "multiple_sources")}
                or (
                    kind
                    in {
                        "cut",
                        "fillet",
                        "chamfer",
                        "transform",
                        "mirror",
                        "union",
                        "intersection",
                        "linear_cut_pattern",
                        "circular_cut_pattern",
                    }
                    and face["feature_id"] != feature_id
                    and status in {"unknown", "split", "merged"}
                    and relation in {"unchanged", "modified", "generated"}
                ),
                "unresolved face contradicts its provenance",
            )
        elif kind not in {
            "cut",
            "shell",
            "fillet",
            "chamfer",
            "transform",
            "mirror",
            "union",
            "intersection",
            "linear_cut_pattern",
            "circular_cut_pattern",
        }:
            expected_relation = (
                "constructed_profile"
                if kind.startswith("sketch_")
                else "first_shape"
                if face["role"] == "cap.start"
                else "last_shape"
                if face["role"] == "cap.end"
                else "generated_from_profile_edge"
            )
            _require(
                relation == expected_relation, "face role contradicts its construction relation"
            )
        elif face["feature_id"] == feature_id and face["role"].startswith("pattern.copy."):
            _require(
                kind in {"linear_cut_pattern", "circular_cut_pattern"}
                and status == "stable"
                and relation == "pattern_tool_face"
                and type(provenance.get("occurrence")) is int
                and 0 <= provenance["occurrence"] < 64
                and type(provenance.get("source_id")) is str
                and face["role"]
                == f"pattern.copy.{provenance['occurrence']}."
                + sha256(provenance["source_id"].encode()).hexdigest()
                and type(provenance.get("source_count")) is int
                and provenance["source_count"] == 1
                and type(provenance.get("image_count")) is int
                and provenance["image_count"] == 1,
                "pattern face requires one authored occurrence and unique tool ancestry",
            )
        elif face["feature_id"] == feature_id and face["role"].startswith("shell."):
            opening = provenance.get("source_id") in features[feature_id].get("opening_faces", [])
            _require(
                kind == "shell"
                and bool(features[feature_id].get("opening_faces"))
                and status == "stable"
                and relation == ("rim_from_opening" if opening else "offset_from_face")
                and type(provenance.get("source_id")) is str
                and face["role"]
                == (
                    (
                        "shell.opening_lip"
                        if len(features[feature_id]["opening_faces"]) == 1
                        else "shell.opening_lip."
                        + sha256(provenance["source_id"].encode()).hexdigest()
                    )
                    if opening
                    else "shell.inner." + sha256(provenance["source_id"].encode()).hexdigest()
                )
                and type(provenance.get("source_count")) is int
                and provenance["source_count"] == 1
                and type(provenance.get("image_count")) is int
                and provenance["image_count"] == 1,
                "shell surface requires unique authored offset/opening ancestry",
            )
        elif face["feature_id"] == feature_id and (
            face["role"] == "blend.surface" or face["role"].startswith("blend.surface.")
        ):
            authored = features[feature_id]
            pairs = authored.get("edge_pairs") or (
                [authored["edge_faces"]] if authored.get("edge_faces") else []
            )
            _require(
                kind in {"fillet", "chamfer"}
                and status == "stable"
                and relation == "generated_from_selected_edge"
                and type(provenance.get("image_count")) is int
                and provenance["image_count"] == 1
                and type(provenance.get("source_faces")) is list
                and any(provenance["source_faces"] == sorted(pair) for pair in pairs)
                and len(provenance["source_faces"]) == 2
                and face["role"] == _blend_surface_role(provenance["source_faces"], len(pairs)),
                "blend surface requires the authored selected edge and one native image",
            )
        elif face["feature_id"] == feature_id:
            _require(
                face["role"] == "cut.wall" and status == "generated" and relation == "tool_surface",
                "cut wall contradicts generated-tool provenance",
            )
        extra_fields = {
            "constructed_profile": set(),
            "first_shape": set(),
            "last_shape": set(),
            "generated_from_profile_edge": {"source_boundary"},
            "generated_from_selected_edge": {"source_faces", "image_count"},
            "offset_from_face": {"source_id", "source_count", "image_count"},
            "rim_from_opening": {"source_id", "source_count", "image_count"},
            "pattern_tool_face": {"source_id", "occurrence", "source_count", "image_count"},
            "unchanged": {"source_id", "modifying_feature_id", "source_count", "image_count"},
            "modified": {"source_id", "modifying_feature_id", "source_count", "image_count"},
            "generated": {"source_id", "modifying_feature_id", "source_count", "image_count"},
            "tool_surface": {"sources"},
            "tool_modified": {"source_id", "modifying_feature_id", "source_count", "image_count"},
            "tool_unchanged": {"source_id", "modifying_feature_id", "source_count", "image_count"},
            "multiple_sources": {"sources"},
            "no_history": {"sources"},
        }[relation]
        _keys(provenance, required | extra_fields | ({"id_scope"} if status != "stable" else set()))
        if "source_id" in provenance:
            tool_lineage = relation in {"tool_modified", "tool_unchanged"}
            if tool_lineage:
                _require(
                    kind == "cut" and status == "stable" and provenance["image_count"] == 1,
                    "only exact ordinary cut tool ancestry can be stable",
                )
            ports = (
                ("tool",)
                if tool_lineage or relation == "pattern_tool_face"
                else (("base", "tool") if kind in {"union", "intersection"} else ("base",))
            )
            matches = []
            for port in ports:
                try:
                    _reference(
                        provenance["source_id"],
                        features[features[feature_id]["inputs"][port]],
                        features,
                    )
                    matches.append(port)
                except ValueError:
                    pass
            _require(matches, "inherited face source is unrelated to operation inputs")
        if relation == "tool_surface":
            _require(provenance["sources"], "cut wall has no tool sources")
            for reference in provenance["sources"]:
                _reference(reference, features[features[feature_id]["inputs"]["tool"]], features)
        if "sources" in provenance:
            _require(
                type(provenance["sources"]) is list
                and len(provenance["sources"]) <= 200_000
                and all(type(value) is str and value for value in provenance["sources"]),
                "invalid face sources",
            )
        if "source_boundary" in provenance:
            _require(
                type(provenance["source_boundary"]) is str
                and face["role"] == "side." + provenance["source_boundary"],
                "face boundary role mismatch",
            )
        by_id[face["id"]] = face
    _require(type(mesh) is dict and type(mesh.get("triangles")) is list, "missing topology mesh")
    face_ids = mesh.get("triangle_face_ids")
    _require(
        type(face_ids) is list
        and len(face_ids) == len(mesh["triangles"])
        and all(type(value) is str and value in by_id for value in face_ids),
        "mesh faces are not bound to output topology",
    )
    _require(set(face_ids) == set(by_id), "tessellation omitted an output face")
    return by_id


def _reference(identifier, source, features):
    """Check diagnostic source handles against authored origin/role domains.

    Full Part replay additionally checks exact base/tool face membership. An
    assembly summary does not duplicate every intermediate face payload.
    """
    _require(type(identifier) is str, "invalid topology source reference")
    if identifier.startswith("snapshot:"):
        pieces = identifier.split(":")
        _require(
            len(pieces) == 4
            and pieces[:3] == ["snapshot", source["id"], "face"]
            and pieces[3].isascii()
            and pieces[3].isdigit()
            and len(pieces[3]) <= 6
            and 0 <= int(pieces[3]) < 200_000,
            "unrelated snapshot topology source",
        )
        return
    parts = identifier.split("/face/")
    _require(
        len(parts) == 2
        and parts[0] in _origin_features(source, features)
        and _role_allowed(parts[1], features[parts[0]], features)
        and parts[1] != "unresolved",
        "unrelated semantic topology source",
    )
