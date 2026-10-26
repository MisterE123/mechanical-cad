"""Explicit bounded geometry-result-3 protocol, dormant until service admission.

Request failures raise CADException for the ordinary common failure envelope.
Admitted actions preserve complete/partial fresh replay and geometry evidence.
No canonical or legacy wire shape is changed here.
"""

from __future__ import annotations

from .actions import EXPORT_ACTIONS, GEOMETRY_ACTIONS, _destination, run_geometry_action
from .errors import CADException
from .geometry_policy_v3 import validate_geometry_v3
from .model import Document
from .sketch_protocol import validate_request_budget

# Direct service qualification precedes guarded owner/capability activation.
BACKEND_CAPABILITIES = frozenset({"mcad.geometry-result/3"})


def process_geometry_request_v3(request: dict, *, kernel=None) -> dict:
    """Preflight the full exact request before any solve, native import or write."""
    if type(request) is not dict:
        raise CADException("invalid_request", "Request must be a JSON object.")
    fingerprint = validate_request_budget(request)
    if type(request.get("protocol_version")) is not int or request["protocol_version"] != 1:
        raise CADException("unsupported_protocol", "Only sidecar protocol 1 is supported.")
    if type(request.get("result_version")) is not int or request["result_version"] != 3:
        raise CADException("unsupported_result_version", "This service requires result_version 3.")
    action = request.get("action")
    if type(action) is not str or action not in GEOMETRY_ACTIONS:
        raise CADException(
            "invalid_action", "Geometry result 3 requires an explicit geometry action."
        )
    required = {"protocol_version", "result_version", "action", "document"}
    if action in EXPORT_ACTIONS:
        required.add("destination")
    if required - set(request) or set(request) - (required | {"options"}):
        raise CADException("invalid_request", "Geometry action has missing or unknown fields.")
    options = request.get("options", {})
    if type(options) is not dict or set(options) - {"linear_deflection"}:
        raise CADException("invalid_request", "Only linear_deflection is a supported option.")
    linear_deflection = options.get("linear_deflection", 0.1)
    if type(linear_deflection) not in (int, float) or not 0.001 <= linear_deflection <= 10:
        raise CADException("invalid_tolerance", "Mesh linear deflection must be 0.001–10 mm.")
    destination = request.get("destination")
    if action in EXPORT_ACTIONS:
        if type(destination) is not str:
            raise CADException("invalid_destination", "Choose an explicit local export file path.")
        if destination.endswith(("/", "/.", "/..")):
            raise CADException("invalid_destination", "Choose an export file, not a directory.")
        _destination(destination)
    document = Document.from_dict(request["document"])
    validate_geometry_v3(document, 3)
    return {
        "protocol_version": 1,
        "result_version": 3,
        "input_fingerprint": fingerprint,
        **run_geometry_action(
            document,
            action,
            destination=destination,
            linear_deflection=linear_deflection,
            kernel=kernel,
            result_version=3,
        ),
    }
