"""Bounded explicit result-3 solve/replay protocol; no other action families."""

from __future__ import annotations

from .errors import CADException
from .model import Document
from .result_policy_v3 import validate_replay_v3
from .sketch_protocol import validate_request_budget

BACKEND_CAPABILITIES = frozenset({"mcad.part-result/3"})


def _envelope(request, action):
    if type(request.get("protocol_version")) is not int or request["protocol_version"] != 1:
        raise CADException("unsupported_protocol", "Only sidecar protocol 1 is supported.")
    if type(request.get("result_version")) is not int or request["result_version"] != 3:
        raise CADException("unsupported_result_version", "This service requires result_version 3.")
    if request.get("action", "replay") != action:
        raise CADException("invalid_action", "Result 3 supports only Solve Sketch and Part replay.")


def _bounded_fingerprint(request):
    if type(request) is not dict:
        raise CADException("invalid_request", "Request must be a JSON object.")
    return validate_request_budget(request)


def process_sketch_request_v3(request: dict) -> dict:
    """No engine, OCCT, destination or geometry/export imports on solve-only."""
    fingerprint = _bounded_fingerprint(request)
    response = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 3,
        "input_fingerprint": fingerprint,
        "ok": False,
        "result": None,
        "error": None,
    }
    try:
        _envelope(request, "solve_sketch")
        if set(request) != {
            "protocol_version",
            "action",
            "result_version",
            "document",
            "feature_id",
        }:
            raise CADException("invalid_request", "Solve Sketch accepts only its explicit fields.")
        document = Document.from_dict(request["document"])
        from .sketch_service_v3 import solve_sketch_v3

        response.update(solve_sketch_v3(document, request["feature_id"]))
    except CADException as exc:
        response["error"] = exc.to_dict()
    return response


def process_replay_request_v3(request: dict) -> dict:
    """Preflight every v3 policy before native imports or a common replay call."""
    fingerprint = _bounded_fingerprint(request)
    _envelope(request, "replay")
    if set(request) - {"protocol_version", "action", "result_version", "document", "options"}:
        raise CADException("invalid_request", "Unknown result-3 replay fields.")
    options = request.get("options", {})
    if type(options) is not dict or set(options) - {"linear_deflection"}:
        raise CADException("invalid_request", "Only linear_deflection is a supported option.")
    document = Document.from_dict(request.get("document"))
    validate_replay_v3(document, 3)
    linear_deflection = options.get("linear_deflection", 0.1)
    if type(linear_deflection) not in (int, float) or not 0.001 <= linear_deflection <= 10:
        raise CADException("invalid_tolerance", "Mesh linear deflection must be 0.001–10 mm.")
    from .engine import regenerate
    from .kernel_ocp import OCPKernel

    replay = regenerate(
        document, OCPKernel(), linear_deflection=linear_deflection, result_version=3
    )
    return {
        "protocol_version": 1,
        "result_version": 3,
        "input_fingerprint": fingerprint,
        "ok": replay.ok,
        "result": replay.result,
        "error": None,
    }
