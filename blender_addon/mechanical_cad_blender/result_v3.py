"""Dormant data-only result-3 solve/replay validation, with no launch or authority.

Raw operation identity, canonical document identity, genuine solver evidence,
feature algebra and sector geometry/provenance are checked separately.
"""

from __future__ import annotations

import copy

from . import part_contracts_v3 as snapshots
from .part_result_bridge import (
    _validate_cut_ancestry,
    _validate_cut_lineage,
    _validate_dependencies,
    _validate_face_support,
)
from .sector_topology_v3 import validate_sector_topology
from .sketch_bridge import _SUCCESS, _identifier, _keys, _number, _require
from .sketch_contracts_v3 import (
    _error,
    validate_output_v3,
    validate_profile_check,
    validate_sketch_report_v3,
)


def _graph(canonical, *, replay):
    from .sketch_projection import projection_input_types, validate_projection_sources

    validate_projection_sources(canonical)
    features = canonical["features"]
    by_id = {feature["id"]: feature for feature in features}
    _require(
        canonical["active_feature"] is None or canonical["active_feature"] in by_id,
        "active feature is missing",
    )
    for feature in features:
        _identifier(feature["id"])
        for port, target in feature["inputs"].items():
            _require(target in by_id and target != feature["id"], "invalid feature dependency")
            allowed = (
                {
                    "sketch_rectangle",
                    "sketch_circle",
                    "sketch_constrained",
                    "sketch_face_rectangle",
                    "sketch_face_circle",
                }
                if port in {"profile", "start", "end", "path"}
                or port in feature.get("loft_sections", {}).get("ports", [])
                else {
                    "extrude",
                    "extrude_through",
                    "extrude_to_face",
                    "extrude_symmetric",
                    "cut",
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
                    "spur_gear",
                    "loft",
                    "sweep",
                }
            )
            if port in projection_input_types(feature.get("projections", [])):
                if projection_input_types(feature.get("projections", []))[port] == "profile":
                    allowed = {"sketch_constrained"}
            _require(by_id[target]["kind"] in allowed, "dependency targets wrong feature kind")
    pending, complete = set(by_id), set()
    while pending:
        ready = {
            identifier
            for identifier in pending
            if set(by_id[identifier]["inputs"].values()) <= complete
        }
        _require(bool(ready), "cyclic feature dependencies")
        pending -= ready
        complete |= ready


def validate_request(operation):
    """Return a detached original operation; never rewrite raw intent/fingerprint."""
    request = snapshots.snapshot_request(operation)
    _require(type(request) is dict, "operation must be an object")
    action = request.get("action", "replay")
    _require(
        type(action) is str and action in {"solve_sketch", "replay"}, "unsupported result-3 action"
    )
    common = {"protocol_version", "result_version", "document"}
    if action == "solve_sketch":
        _keys(request, common | {"action", "feature_id"})
    else:
        _keys(request, common | {"action", "options"}, common)
        if "options" in request:
            _keys(request["options"], {"linear_deflection"}, set())
            if "linear_deflection" in request["options"]:
                _number(request["options"]["linear_deflection"], minimum=0.001, bound=10)
    _require(
        type(request["protocol_version"]) is int
        and request["protocol_version"] == 1
        and type(request["result_version"]) is int
        and request["result_version"] == 3,
        "explicit protocol 1/result 3 required",
    )
    canonical = snapshots._expected_document(request["document"])
    _graph(canonical, replay=action == "replay")
    if action == "solve_sketch":
        _identifier(request["feature_id"])
        _require(
            any(
                feature["id"] == request["feature_id"] and feature["kind"] == "sketch_constrained"
                for feature in canonical["features"]
            ),
            "solve requires an existing constrained feature",
        )
    return request


def _envelope(request, response, *, solve):
    snapshots._bounded_response(response)
    _require(
        type(response) is dict
        and type(response.get("protocol_version")) is int
        and response["protocol_version"] == 1
        and type(response.get("result_version")) is int
        and response["result_version"] == 3
        and type(response.get("ok")) is bool,
        "unsupported result-3 response",
    )
    common = {"protocol_version", "result_version", "ok", "result", "error"}
    if (
        response.get("result") is None
        and response["ok"] is False
        and "input_fingerprint" not in response
    ):
        _keys(response, common)
        _error(response["error"])
        return False
    _keys(response, common | {"input_fingerprint"} | ({"action"} if solve else set()))
    _require(
        response["input_fingerprint"] == snapshots.input_fingerprint(request),
        "complete raw operation fingerprint mismatch",
    )
    if solve:
        _require(response["action"] == "solve_sketch", "solve response action mismatch")
    if response["result"] is None:
        _require(response["ok"] is False, "successful response lacks result")
        _error(response["error"])
        return False
    return True


def validate_solve_response(response, request):
    request = validate_request(request)
    _require(request.get("action") == "solve_sketch", "solve response requires solve request")
    if not _envelope(request, response, solve=True):
        return copy.deepcopy(response)
    canonical = snapshots._expected_document(request["document"])
    result = response["result"]
    source = next(
        feature for feature in canonical["features"] if feature["id"] == request["feature_id"]
    )
    from .sketch_support_evidence import contextual, validate_solve_context

    fields = {"document_id", "document_hash", "feature_id", "sketch", "profile_check"}
    if contextual(source):
        fields.add("support_context")
    _keys(result, fields)
    _require(
        result["document_id"] == canonical["id"]
        and result["document_hash"] == snapshots.document_hash(canonical)
        and result["feature_id"] == request["feature_id"],
        "solve canonical source identity mismatch",
    )
    source = next(
        feature for feature in canonical["features"] if feature["id"] == request["feature_id"]
    )
    if contextual(source):
        source = validate_solve_context(
            canonical, source, result["support_context"], _validate_replay_body
        )
    feature = {
        "id": source["id"],
        "kind": source["kind"],
        "status": "ok" if response["ok"] else "failed",
        "sketch": result["sketch"],
    }
    validate_sketch_report_v3(feature, source)
    _require(
        type(result["sketch"]) is dict
        and response["ok"] == (result["sketch"]["status"] in _SUCCESS),
        "solve success contradicts native report",
    )
    if response["ok"]:
        _require(response["error"] is None, "successful solve also has error")
        validate_profile_check(result["profile_check"], result["sketch"]["solved"])
    else:
        _error(response["error"])
        _require(
            response["error"]["code"] == "sketch_solve_failed" and result["profile_check"] is None,
            "failed solve claims readiness",
        )
    return copy.deepcopy(response)


def _feature_evidence(feature, source):
    fields = {
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
    if source["kind"] == "cut":
        fields.add("cut_ancestry")
    if source["kind"] == "sketch_constrained" and "support_face" in source:
        fields.add("support_plane")
    from .sketch_projection import has_solid_projections

    if has_solid_projections(source.get("projections", [])):
        fields.add("projection_edges")
    _keys(feature, fields, fields - {"sketch"})
    _require(
        all(feature[key] == source[key] for key in ("id", "kind", "label", "inputs")),
        "feature identity/label/edges differ from source",
    )
    parameters = feature["resolved_params"]
    _require(
        type(parameters) is dict and set(parameters) <= set(source["params"]),
        "resolved feature parameters differ from source",
    )
    if feature["status"] == "ok":
        _require(
            set(parameters) == set(source["params"]), "successful feature lacks resolved parameters"
        )
    for key, value in parameters.items():
        _number(value, bound=1e12)
        authored = source["params"][key]
        _require(
            type(authored) is str or value == authored, "resolved literal feature parameter changed"
        )
    validate_output_v3(feature, source)


def _validate_replay_body(canonical, result):
    """Validate genuine v3 replay data independently of its action envelope.

    Callers own bounded JSON, canonical source admission and exact request
    binding. This shared body never coerces replay or sketch versions.
    """
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
        and result["result_version"] == 3
        and result["document_id"] == canonical["id"]
        and result["document_hash"] == snapshots.document_hash(canonical)
        and result["active_feature"] == canonical["active_feature"]
        and result["units"] == "mm",
        "replay canonical source/version mismatch",
    )
    _keys(result["parameters"], set(canonical["parameters"]))
    for key, value in result["parameters"].items():
        _number(value, bound=1e12)
        authored = canonical["parameters"][key]
        _require(
            type(authored) is str or value == authored, "resolved literal project parameter changed"
        )
    features = result["features"]
    _require(
        type(features) is list and len(features) == len(canonical["features"]),
        "replay added or omitted features",
    )
    for feature, source in zip(features, canonical["features"], strict=True):
        from .sketch_support_evidence import resolved_source

        _feature_evidence(feature, resolved_source(source, feature, features))
        if feature["kind"] == "extrude" and feature["status"] == "ok":
            profile = next(
                item for item in canonical["features"] if item["id"] == source["inputs"]["profile"]
            )
            profile_result = next(item for item in features if item["id"] == profile["id"])
            if (profile_result.get("output") or {}).get("profile", {}).get(
                "region_kind"
            ) == "curve_loop":
                _number(feature["resolved_params"]["length"], minimum=1, bound=1000)
    _validate_dependencies(features, canonical["features"])
    for feature, source in zip(features, canonical["features"], strict=True):
        if feature["topology"]:
            validate_sector_topology(
                feature, source, source_features=canonical["features"], result_features=features
            )
    _validate_cut_lineage(features)
    _validate_cut_ancestry(features)
    _validate_face_support(features, canonical["features"])
    expected = "ok" if all(feature["status"] == "ok" for feature in features) else "failed"
    _require(result["status"] == expected, "replay status contradicts features")


def validate_response(operation, response):
    """Dispatch exact result-3 solve/replay and return detached data-only evidence."""
    request = validate_request(operation)
    if request.get("action", "replay") == "solve_sketch":
        return validate_solve_response(response, request)
    if not _envelope(request, response, solve=False):
        return copy.deepcopy(response)
    canonical = snapshots._expected_document(request["document"])
    result = response["result"]
    _validate_replay_body(canonical, result)
    _require(
        response["ok"] == (result["status"] == "ok") and response["error"] is None,
        "replay success algebra contradicts features",
    )
    return copy.deepcopy(response)
