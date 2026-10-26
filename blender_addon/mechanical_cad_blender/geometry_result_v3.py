"""Dormant, native-free geometry-result/3 source and evidence contracts.

Only the bounded directed-sector Part output is eligible. Full raw operations,
genuine replay-3 evidence and the action's closed outcome algebra are independent
requirements. Validation neither launches work nor grants publication authority.
"""

from __future__ import annotations

import copy
from pathlib import PurePath

from . import part_contracts_v3 as snapshots
from . import result_v3
from .part_geometry_evidence import validate_geometry_action
from .sketch_bridge import _keys, _number, _require
from .sketch_contracts_v3 import _error

GEOMETRY_ACTIONS = frozenset({"check_geometry", "export_step", "export_stl"})
_EXPORT_ACTIONS = frozenset({"export_step", "export_stl"})
_REPLAY_ERRORS = frozenset({"replay_failed", "io_error"})
_CHECK_ERRORS = frozenset({"geometry_check_failed", "io_error"})
_EXPORT_ERRORS = frozenset({"export_failed", "export_io_error", "empty_export"})
_BASE_CHECK_FIELDS = {"brep", "mesh", "linear_deflection_mm"}
# Only request/model/source/expression failures that occur before replay. The
# guarded dispatcher also emits common errors if serialization fails AFTER an
# export. In particular sidecar_error, invalid_json and document_too_large do
# not establish that nothing was written and must remain unvalidated outcomes.
_PREFLIGHT_ERRORS = frozenset(
    {
        "invalid_action",
        "invalid_destination",
        "invalid_request",
        "invalid_tolerance",
        "unsupported_protocol",
        "unsupported_result_version",
        "invalid_document",
        "unsupported_feature",
        "unsupported_schema",
        "unsupported_units",
        "migration_required",
        "duplicate_feature",
        "feature_cycle",
        "input_type_mismatch",
        "missing_reference",
        "invalid_sketch",
        "duplicate_id",
        "resource_limit",
        "sketch_too_large",
        "invalid_arc",
        "degenerate_arc",
        "invalid_expression",
        "invalid_number",
        "unknown_parameter",
        "parameter_cycle",
        "missing_active_feature",
        "not_a_solid",
        "unsupported_geometry_source",
        "unsupported_native_frame",
        "unsupported_profile_form",
        "unsupported_profile_graph",
        "unsupported_profile_scale",
    }
)


def _canonical_source(document):
    canonical = snapshots._expected_document(document)
    result_v3._graph(canonical, replay=True)
    from .solid_feature_edit import SOLID_KINDS

    active = next(
        (
            feature
            for feature in canonical["features"]
            if feature["id"] == canonical["active_feature"]
        ),
        None,
    )
    _require(
        active is not None and active["kind"] in SOLID_KINDS,
        "Geometry checks and export require a selected solid feature.",
    )
    return canonical


def validate_source(document):
    """Return detached eligible source intent, without solving or normalizing it.

    Expressions and authored point seeds remain the backend's fresh-solve input.
    No zero-DoF condition, extra-point restriction or new sector policy is added.
    """
    source = snapshots.snapshot_request(document)
    _canonical_source(source)
    return source


def validate_request(operation):
    """Require explicit protocol1/int3 and retain exact path/options spelling."""
    request = snapshots.snapshot_request(operation)
    action = request.get("action")
    _require(type(action) is str and action in GEOMETRY_ACTIONS, "unsupported geometry-3 action")
    fields = {"protocol_version", "result_version", "action", "document", "options"}
    required = fields - {"options"}
    if action in _EXPORT_ACTIONS:
        fields |= {"destination"}
        required |= {"destination"}
    _keys(request, fields, required)
    _require(
        type(request["protocol_version"]) is int
        and request["protocol_version"] == 1
        and type(request["result_version"]) is int
        and request["result_version"] == 3,
        "explicit protocol 1/result 3 required",
    )
    if "options" in request:
        _keys(request["options"], {"linear_deflection"}, set())
        if "linear_deflection" in request["options"]:
            _number(request["options"]["linear_deflection"], minimum=0.001, bound=10)
    if action in _EXPORT_ACTIONS:
        destination = request["destination"]
        _require(
            type(destination) is str
            and bool(destination.strip())
            and "\0" not in destination
            and not destination.endswith(("/", "/.", "/.."))
            and PurePath(destination).name not in {"", ".", ".."},
            "Choose an explicit local export file path.",
        )
    _canonical_source(request["document"])
    return request


def _validate_failure(request, response):
    """Only actual producer phases may retain the corresponding partial data."""
    _error(response["error"])
    _require(response["export"] is None, "failed action claims a completed export")
    result, checks, code = response["result"], response["geometry_check"], response["error"]["code"]
    if result is None:
        _require(checks is None and code in _REPLAY_ERRORS, "invalid pre-replay failure evidence")
    elif result["status"] == "failed":
        _require(
            checks is None and code == "regeneration_failed",
            "invalid failed-replay action evidence",
        )
    elif checks is None:
        _require(code in _CHECK_ERRORS, "invalid geometry-check failure evidence")
    else:
        _require(
            request["action"] in _EXPORT_ACTIONS and code in _EXPORT_ERRORS,
            "completed checks may accompany only an export-stage failure",
        )
        # The atomic writer returns encoded evidence only after replacement.
        # A failed STL export retains the complete base check, never a receipt
        # or encoded pair that could be mistaken for a completed write.
        _keys(checks, _BASE_CHECK_FIELDS)


def validate_response(operation, response):
    """Return detached exact-operation evidence; never fall back to result 2."""
    request = validate_request(operation)
    snapshots._bounded_response(response)
    _require(
        type(response) is dict
        and type(response.get("protocol_version")) is int
        and response["protocol_version"] == 1
        and type(response.get("result_version")) is int
        and response["result_version"] == 3
        and type(response.get("ok")) is bool,
        "unsupported geometry-3 response",
    )
    common = {"protocol_version", "result_version", "ok", "result", "error"}
    if "input_fingerprint" not in response:
        _keys(response, common)
        _require(
            response["ok"] is False and response["result"] is None,
            "unbound preflight failure cannot contain usable evidence",
        )
        _error(response["error"])
        _require(
            response["error"]["code"] in _PREFLIGHT_ERRORS,
            "common failure does not establish a pre-replay rejection",
        )
        return copy.deepcopy(response)
    _keys(response, common | {"input_fingerprint", "action", "geometry_check", "export"})
    _require(
        response["input_fingerprint"] == snapshots.input_fingerprint(request)
        and response["action"] == request["action"],
        "complete raw geometry operation identity mismatch",
    )
    result = response["result"]
    if result is not None:
        result_v3._validate_replay_body(_canonical_source(request["document"]), result)
    if response["ok"]:
        _require(
            result is not None and result["status"] == "ok" and response["error"] is None,
            "successful geometry action lacks complete replay",
        )
    else:
        _validate_failure(request, response)
    validate_geometry_action(request, response)
    return copy.deepcopy(response)
