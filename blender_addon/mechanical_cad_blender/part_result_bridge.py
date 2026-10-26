"""Native-free exact-request validation of explicitly negotiated Part results.

Legacy bridge acceptance stays in bridge.py. No native CAD imports, solving,
model mutation or display publication occur at this boundary.
"""

from __future__ import annotations

import copy
import math

from . import part_contracts as snapshots
from .part_geometry_evidence import validate_geometry_action
from .sketch_bridge import _error_record, _keys, _number, _require, validate_output
from .topology_evidence import validate_topology


def validate_response(request, response):
    """Return owned v2 evidence, or reject stale/malformed/unsupported semantics."""
    request = snapshots.snapshot_request(request)
    snapshots._bounded_response(response)
    _keys(
        request,
        {"protocol_version", "result_version", "document", "action", "options", "destination"},
        {"protocol_version", "result_version", "document"},
    )
    action = request.get("action", "replay")
    _require(
        type(request["protocol_version"]) is int
        and request["protocol_version"] == 1
        and type(request["result_version"]) is int
        and request["result_version"] == 2,
        "Use matching add-on and backend versions supporting typed Part results.",
    )
    _require(
        type(action) is str and action in {"replay", "check_geometry", "export_step", "export_stl"},
        "unsupported typed Part action",
    )
    _require(
        type(response) is dict
        and type(response.get("protocol_version")) is int
        and response["protocol_version"] == 1
        and type(response.get("result_version")) is int
        and response["result_version"] == 2
        and type(response.get("ok")) is bool,
        "Use matching add-on and backend versions supporting typed Part results.",
    )
    # Parsing/schema failures can precede request fingerprinting. They carry no
    # usable result and can only become a readable failure, never display state.
    if (
        response.get("result") is None
        and response["ok"] is False
        and "input_fingerprint" not in response
    ):
        _keys(response, {"protocol_version", "result_version", "ok", "result", "error"})
        _error_record(response["error"])
        return copy.deepcopy(response)
    fields = {"protocol_version", "result_version", "input_fingerprint", "ok", "result", "error"}
    if action != "replay":
        fields |= {"action", "geometry_check", "export"}
    _keys(response, fields)
    _require(
        response["input_fingerprint"] == snapshots.input_fingerprint(request),
        "stale or different complete Part request",
    )
    if action != "replay":
        _require(response["action"] == action, "Part action response differs from request")
    result = response["result"]
    if result is None:
        _require(response["ok"] is False, "successful response lacks replay evidence")
        _error_record(response["error"])
        if action != "replay":
            _require(
                response["geometry_check"] is None and response["export"] is None,
                "missing replay cannot claim geometry or export evidence",
            )
        return copy.deepcopy(response)
    canonical = snapshots._expected_document(request["document"])
    expected_hash = snapshots.document_hash(canonical)
    _keys(
        result,
        {
            "document_id",
            "document_hash",
            "active_feature",
            "status",
            "units",
            "parameters",
            "features",
            "result_version",
        },
    )
    _require(
        type(result["result_version"]) is int
        and result["result_version"] == 2
        and result["document_id"] == canonical["id"]
        and result["document_hash"] == expected_hash
        and result["active_feature"] == canonical["active_feature"]
        and result["units"] == "mm",
        "Part replay identity/version differs from candidate",
    )
    _keys(result["parameters"], set(canonical["parameters"]))
    for key, value in result["parameters"].items():
        _number(value, bound=1e12)
        authored = canonical["parameters"][key]
        _require(type(authored) is str or value == authored, "resolved literal parameter changed")
    features = result["features"]
    _require(
        type(features) is list and len(features) == len(canonical["features"]),
        "Part replay omitted or added features",
    )
    from .sketch_projection import has_solid_projections

    statuses = []
    for feature, source in zip(features, canonical["features"], strict=True):
        _keys(
            feature,
            {
                "id",
                "label",
                "kind",
                "status",
                "error",
                "stats",
                "mesh",
                "topology",
                "resolved_params",
                "inputs",
                "output",
                "sketch",
            }
            | ({"cut_ancestry"} if source["kind"] == "cut" else set())
            | (
                {"support_plane"}
                if source["kind"] == "sketch_constrained" and "support_face" in source
                else set()
            )
            | (
                {"projection_edges"}
                if has_solid_projections(source.get("projections", []))
                else set()
            ),
            {
                "id",
                "label",
                "kind",
                "status",
                "error",
                "stats",
                "mesh",
                "topology",
                "resolved_params",
                "inputs",
                "output",
            }
            | ({"cut_ancestry"} if source["kind"] == "cut" else set())
            | (
                {"support_plane"}
                if source["kind"] == "sketch_constrained" and "support_face" in source
                else set()
            )
            | (
                {"projection_edges"}
                if has_solid_projections(source.get("projections", []))
                else set()
            ),
        )
        _require(
            feature["id"] == source["id"]
            and feature["kind"] == source["kind"]
            and feature["label"] == source["label"]
            and feature["inputs"] == source["inputs"],
            "Part feature identity, label or dependency edges changed",
        )
        parameters = feature["resolved_params"]
        _require(
            type(parameters) is dict and set(parameters) <= set(source["params"]),
            "resolved feature parameters do not match source",
        )
        if feature["status"] == "ok":
            _require(
                set(parameters) == set(source["params"]), "successful feature lacks parameters"
            )
        for key, value in parameters.items():
            _number(value, bound=1e12)
            authored = source["params"][key]
            _require(
                type(authored) is str or value == authored, "resolved literal dimension changed"
            )
        from .sketch_support_evidence import resolved_source

        validate_output(feature, resolved_source(source, feature, features))
        statuses.append(feature["status"])
    _validate_dependencies(features, canonical["features"])
    for feature in features:
        if feature["topology"]:
            validate_topology(
                feature["topology"],
                feature_id=feature["id"],
                kind=feature["kind"],
                mesh=feature["mesh"],
                source_features=canonical["features"],
            )
    _validate_cut_lineage(features)
    _validate_cut_ancestry(features)
    _validate_face_support(features, canonical["features"])
    _require(
        result["status"] == ("ok" if all(status == "ok" for status in statuses) else "failed"),
        "Part status contradicts per-feature evidence",
    )
    if action == "replay":
        _require(
            response["ok"] == (result["status"] == "ok") and response["error"] is None,
            "replay envelope contradicts feature results",
        )
    elif response["ok"]:
        _require(
            result["status"] == "ok" and response["error"] is None,
            "successful geometry action lacks complete replay",
        )
    else:
        _error_record(response["error"])
    if action != "replay":
        validate_geometry_action(request, response)
    return copy.deepcopy(response)


def _validate_cut_ancestry(features):
    from .cut_support_ancestry import validate_cut_ancestry

    rows = {row["id"]: row for row in features}
    for row in features:
        if row["kind"] != "cut":
            continue
        if row["status"] == "ok":
            validate_cut_ancestry(row, rows[row["inputs"]["base"]], rows[row["inputs"]["tool"]])
        else:
            _require(row.get("cut_ancestry") is None, "Failed Cut retained ancestry evidence")


def _validate_cut_lineage(features):
    """Bind inherited semantic roles to actual base-output faces, never list order.

    A cut or unary modifier retains the originating ID only for a surviving face.
    The current operation ID alone is therefore insufficient to validate lineage.
    """
    by_id = {feature["id"]: feature for feature in features}
    for feature in features:
        if (
            feature["kind"]
            not in {
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
            or feature["status"] != "ok"
        ):
            continue
        base = by_id[feature["inputs"]["base"]]
        _require(base["status"] == "ok", "cut inherits from an unavailable base")
        base_faces = {face["id"]: face for face in base["topology"]}
        tool = by_id.get(feature["inputs"].get("tool"))
        tool_faces = {face["id"] for face in tool["topology"]} if tool else set()
        if feature["kind"] in {"union", "intersection"}:
            available, ambiguous = {}, set()
            for identifier in set(feature["inputs"].values()):
                for face in by_id[identifier]["topology"]:
                    if face["id"] in available:
                        ambiguous.add(face["id"])
                    else:
                        available[face["id"]] = face
            base_faces = {
                identifier: face
                for identifier, face in available.items()
                if identifier not in ambiguous
            }
        inherited = []
        tool_lineage = []
        tool_by_id = {face["id"]: face for face in tool["topology"]} if tool else {}
        base_ancestry_ids, seen = set(), set()
        pending = [base] if feature["kind"] == "cut" else []
        while pending:
            ancestor = pending.pop()
            if ancestor["id"] in seen:
                continue
            seen.add(ancestor["id"])
            base_ancestry_ids.update(face["id"] for face in ancestor["topology"])
            pending.extend(by_id[identifier] for identifier in ancestor["inputs"].values())
        for face in feature["topology"]:
            if face["role"] == "cut.wall" and face["feature_id"] == feature["id"]:
                sources = face["provenance"].get("sources")
                _require(
                    type(sources) is list and sources and set(sources) <= tool_faces,
                    "cut wall cites an unavailable tool face",
                )
            if face["feature_id"] == feature["id"]:
                if face["role"].startswith("pattern.copy."):
                    provenance = face["provenance"]
                    source = tool_by_id.get(provenance["source_id"])
                    _require(
                        source is not None
                        and source["provenance"]["semantic_status"] == "stable"
                        and provenance["occurrence"] < feature["resolved_params"]["count"],
                        "pattern face cites a missing occurrence or unstable tool face",
                    )
                if face["role"].startswith("shell."):
                    source = base_faces.get(face["provenance"]["source_id"])
                    _require(
                        source is not None and source["provenance"]["semantic_status"] == "stable",
                        "shell surface cites an unavailable or ambiguous source face",
                    )
                if face["role"] == "blend.surface" or face["role"].startswith("blend.surface."):
                    _require(
                        all(
                            identifier in base_faces
                            and base_faces[identifier]["provenance"]["semantic_status"] == "stable"
                            for identifier in face["provenance"]["source_faces"]
                        ),
                        "blend surface cites an unavailable or ambiguous selected face",
                    )
                continue
            provenance = face["provenance"]
            if provenance["relation"] in {"tool_modified", "tool_unchanged"}:
                source = tool_by_id.get(provenance["source_id"])
                _require(
                    feature["kind"] == "cut"
                    and source is not None
                    and source["provenance"]["semantic_status"] == "stable"
                    and source["id"] not in base_ancestry_ids
                    and face["id"] == source["id"]
                    and face["feature_id"] == source["feature_id"]
                    and face["role"] == source["role"]
                    and provenance["semantic_status"] == "stable"
                    and provenance["image_count"] == 1,
                    "cut tool ancestry is not exact and unambiguous",
                )
                tool_lineage.append(face)
                continue
            source = base_faces.get(provenance["source_id"])
            _require(
                source is not None
                and face["feature_id"] == source["feature_id"]
                and face.get("role") == source.get("role"),
                "cut face does not inherit its base semantic identity",
            )
            if feature["kind"] == "shell":
                _require(
                    source["provenance"]["semantic_status"] == "stable"
                    and provenance["semantic_status"] == "stable"
                    and provenance["relation"] == "unchanged"
                    and provenance["image_count"] == 1
                    and face["id"] == source["id"]
                    and face["signature"] == source["signature"],
                    "shell outer ancestry must retain the exact unchanged source face",
                )
            inherited.append(face)
        _require(
            len({face["provenance"]["source_id"] for face in tool_lineage}) == len(tool_lineage),
            "cut tool source has multiple images",
        )
        counts = {}
        for face in inherited:
            identifier = face["provenance"]["source_id"]
            counts[identifier] = counts.get(identifier, 0) + 1
        for face in inherited:
            provenance = face["provenance"]
            # Multiple-source faces can become unresolved instead of inherited,
            # so observed descendants may be fewer than the native image count.
            _require(
                counts[provenance["source_id"]] <= provenance["image_count"],
                "cut lineage image count contradicts observed descendants",
            )
            source_status = base_faces[provenance["source_id"]]["provenance"]["semantic_status"]
            expected = "split" if provenance["image_count"] > 1 else source_status
            if provenance["relation"] == "generated" and expected == "stable":
                expected = "generated"
            _require(
                provenance.get("semantic_status") == expected,
                "cut lineage silently promoted an ambiguous source identity",
            )


def _validate_dependencies(features, sources=None):
    """Successful outputs require successful, appropriately typed input ports."""
    from .sketch_projection import projection_input_types

    by_id = {feature["id"]: feature for feature in features}
    canonical = {f["id"]: f for f in sources or []}
    for feature in features:
        profile_ports = {"profile", "start", "end"} | set(
            canonical.get(feature["id"], {}).get("loft_sections", {}).get("ports", [])
        )
        projection_types = projection_input_types(
            canonical.get(feature["id"], {}).get("projections", [])
        )
        failed_inputs = [
            by_id[target]
            for target in feature["inputs"].values()
            if by_id[target]["status"] != "ok"
        ]
        open_profile = any(
            by_id[target]["status"] == "ok"
            and by_id[target]["output"]["kind"] == "sketch"
            and by_id[target]["output"]["profile"]["state"] == "unavailable"
            for port, target in feature["inputs"].items()
            if port in profile_ports
        )
        if failed_inputs:
            _require(
                feature["status"] == "blocked" and feature["error"]["code"] == "upstream_failed",
                "successful or failed feature has failed or blocked input instead of upstream blocking",
            )
        elif feature["status"] == "blocked":
            _require(
                open_profile and feature["error"]["code"] == "profile_unavailable",
                "blocked feature has no unavailable input port",
            )
        if feature["status"] != "ok":
            continue
        for port, target in feature["inputs"].items():
            source = by_id[target]
            _require(source["status"] == "ok", "successful feature has failed or blocked input")
            output = source["output"]
            if port in profile_ports:
                available = output["kind"] == "profile" or (
                    output["kind"] == "sketch" and output["profile"]["state"] == "available"
                )
                _require(available, "successful extrusion requires an available profile")
            elif port in projection_types or port == "external":
                _require(
                    feature["kind"] == "sketch_constrained"
                    and (
                        (
                            projection_types.get(
                                port, "solid" if "projection_edges" in feature else "profile"
                            )
                            == "solid"
                            and output["kind"] == "solid"
                        )
                        or (
                            projection_types.get(
                                port, "solid" if "projection_edges" in feature else "profile"
                            )
                            == "profile"
                            and source["kind"] == "sketch_constrained"
                            and output["kind"] == "sketch"
                        )
                    ),
                    "projection source kind differs from explicit reference variant",
                )
            elif port == "path":
                _require(
                    feature["kind"] == "sweep" and output["kind"] == "sketch",
                    "successful sweep requires a solved sketch path",
                )
            else:
                _require(
                    output["kind"] == "solid", "successful solid modifier requires solid inputs"
                )


def _validate_face_support(features, sources):
    """Bind successful associative features to their exact replay's stable planar face."""
    by_id = {feature["id"]: feature for feature in features}
    for source in sources:
        if source["kind"] not in {"sketch_face_rectangle", "sketch_face_circle", "extrude_to_face"}:
            continue
        feature = by_id[source["id"]]
        if feature["status"] != "ok":
            continue
        to_face = source["kind"] == "extrude_to_face"
        port, reference = ("target", "end_face") if to_face else ("support", "support_face")
        support = by_id[source["inputs"][port]]
        _require(
            support["status"] == "ok" and support["output"]["kind"] == "solid",
            (
                "up-to-face extrusion requires a successful target solid"
                if to_face
                else "face profile requires a successful support solid"
            ),
        )
        faces = [face for face in support["topology"] if face["id"] == source[reference]]
        _require(
            len(faces) == 1
            and faces[0]["provenance"]["semantic_status"] == "stable"
            and faces[0]["signature"]["surface"] == "plane",
            (
                "up-to-face end face is missing, ambiguous or nonplanar"
                if to_face
                else "face profile support is missing, ambiguous or nonplanar"
            ),
        )
        if to_face:
            target_normal = faces[0]["signature"]["normal"]
            profile = by_id[source["inputs"]["profile"]]
            for profile_face in profile["topology"]:
                signature = profile_face["signature"]
                if signature["surface"] != "plane":
                    continue
                normal = signature["normal"]
                cross = (
                    normal[1] * target_normal[2] - normal[2] * target_normal[1],
                    normal[2] * target_normal[0] - normal[0] * target_normal[2],
                    normal[0] * target_normal[1] - normal[1] * target_normal[0],
                )
                _require(
                    math.hypot(*cross) <= 1e-7,
                    "up-to-face target is not parallel to its source profile",
                )
