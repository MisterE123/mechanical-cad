"""Strict, bounded solve-only action and opt-in Part result-v2 input guards."""

from __future__ import annotations

import json

from .errors import CADException
from .model import Document, reject_duplicate_keys
from .part_snapshot import input_fingerprint
from .sketch_model import (
    SUPPORTED_SKETCH_SCHEMA_VERSIONS,
    _parse_number,
    _reject_constant,
    sketch_capabilities,
)


def parse_bounded_numbers(raw: str | bytes) -> dict:
    """Apply new-action numeric lexeme policy without changing legacy requests."""
    return json.loads(
        raw,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=_reject_constant,
        parse_int=lambda token: _parse_number(token, integer=True),
        parse_float=_parse_number,
    )


def validate_request_budget(request: dict) -> str:
    """Bound direct Python trees as well as wire requests before model parsing."""
    fingerprint = input_fingerprint(request)
    # Direct calls have no original numeric spelling. Validate their canonical
    # representation, while main() checks the original wire spelling as well.
    parse_bounded_numbers(json.dumps(request, sort_keys=True, separators=(",", ":")))
    return fingerprint


def needs_numeric_policy(request: dict) -> bool:
    """New capabilities opt in; old Part data keeps its old accepted lexemes."""
    if request.get("action") == "solve_sketch" or request.get("result_version") == 2:
        return True
    document = request.get("document")
    if not isinstance(document, dict) or not isinstance(document.get("features"), list):
        return False
    return any(
        isinstance(feature, dict)
        and isinstance(feature.get("sketch"), dict)
        and type(feature["sketch"].get("schema_version")) is int
        and feature["sketch"]["schema_version"] in SUPPORTED_SKETCH_SCHEMA_VERSIONS
        and sketch_capabilities(feature["sketch"]["schema_version"]).bounded_payload
        for feature in document["features"]
    )


def process_sketch_request(request: dict) -> dict:
    """No destinations or writes; attached sketches may replay their native support."""
    fingerprint = validate_request_budget(request)
    response = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "input_fingerprint": fingerprint,
        "ok": False,
        "result": None,
        "error": None,
    }
    try:
        if set(request) != {
            "protocol_version",
            "action",
            "result_version",
            "document",
            "feature_id",
        }:
            raise CADException("invalid_request", "Solve Sketch accepts only its explicit fields.")
        if type(request["result_version"]) is not int or request["result_version"] != 2:
            raise CADException(
                "unsupported_result_version", "Solve Sketch requires result_version 2."
            )
        document = Document.from_dict(request["document"])
        from .sketch_service import solve_sketch

        response.update(solve_sketch(document, request["feature_id"]))
    except CADException as exc:
        response["error"] = exc.to_dict()
    return response
