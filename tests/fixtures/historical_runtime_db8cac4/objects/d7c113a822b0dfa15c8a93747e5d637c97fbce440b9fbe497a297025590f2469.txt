"""Native-free authoritative Part snapshot boundary for explicit capture/update.

Call only from an explicit operation, never Panel.draw. Raw working Part JSON
remains untouched. This validator recognizes the core serializer's narrow
normalizations; it never evaluates expressions, solves, or imports the core.
"""

from __future__ import annotations

import copy
import hashlib

from . import bridge, sidecar_job
from . import part_contracts as contracts
from .request_contracts import RequestError

ACTION = "canonical_snapshot"

# Compatibility names share the leaf implementations; no second serializer or
# normalizer lives in this transport adapter.
_json = contracts._json
_keys = contracts._keys
_normalize_sketch = contracts._normalize_sketch
_normalize_sketch_v1 = contracts._normalize_sketch_v1
_numeric = contracts._numeric
_require = contracts._require
_vector = contracts._vector
normalize_sketch_v2 = contracts.normalize_sketch_v2


def _bounded_response(value):
    """Preserve the snapshot boundary's transport-budget compatibility hook."""
    return contracts._bounded_response(
        value,
        max_bytes=bridge.MAX_RESPONSE_BYTES,
        max_integer_bits=sidecar_job.MAX_INTEGER_BITS,
    )


def _expected_document(document, *, request_bound=True):
    """Keep historical BridgeError failures for request resource violations."""
    try:
        if _uses_schema3(document):
            from . import geometry_result_v3, part_contracts_v3

            geometry_result_v3.validate_source(document)
            return part_contracts_v3._expected_document(document, request_bound=request_bound)
        return contracts._expected_document(document, request_bound=request_bound)
    except RequestError as exc:
        raise bridge.BridgeError(str(exc)) from exc


def _uses_schema3(document):
    """Dispatch only an actual embedded integer schema 3; never coerce intent."""
    return (
        type(document) is dict
        and type(document.get("features")) is list
        and any(
            type(feature) is dict
            and type(feature.get("sketch")) is dict
            and type(feature["sketch"].get("schema_version")) is int
            and feature["sketch"]["schema_version"] == 3
            for feature in document["features"]
        )
    )


def canonical_equivalent(raw_document, canonical_document):
    """Keep legacy normalization frozen; admit only supported sector-solid sources."""
    if not _uses_schema3(raw_document):
        return contracts.canonical_equivalent(raw_document, canonical_document)
    try:
        expected = _json(_expected_document(raw_document), canonical=True)
        _bounded_response(canonical_document)
        candidate = _json(canonical_document, canonical=True)
        canonical = _json(
            _expected_document(canonical_document, request_bound=False), canonical=True
        )
        return expected == candidate == canonical
    except (bridge.BridgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def input_fingerprint(request):
    """Keep historical BridgeError failures for malformed request snapshots."""
    try:
        return contracts.input_fingerprint(request)
    except RequestError as exc:
        raise bridge.BridgeError(str(exc)) from exc


def validate_response(request, response):
    """Return a detached receipt only after binding bytes, identity, and intent."""
    try:
        request = sidecar_job.snapshot_request(request)
        _bounded_response(response)
        _keys(request, {"protocol_version", "action", "document"})
        _require(
            type(request["protocol_version"]) is int
            and request["protocol_version"] == 1
            and request["action"] == ACTION,
            "invalid snapshot request",
        )
        # Process-level validation failures retain the legacy common envelope.
        # They may be reported as errors, but can never yield a capture receipt.
        if type(response) is dict and response.get("ok") is False:
            _keys(response, {"protocol_version", "ok", "result", "error"})
            _require(
                type(response["protocol_version"]) is int
                and response["protocol_version"] == 1
                and response["result"] is None,
                "invalid snapshot failure",
            )
            _keys(response["error"], {"code", "message"})
            _require(
                all(type(value) is str and value for value in response["error"].values()),
                "malformed snapshot error",
            )
            raise bridge.BridgeError(f"{response['error']['code']}: {response['error']['message']}")
        _keys(
            response, {"protocol_version", "action", "input_fingerprint", "ok", "result", "error"}
        )
        _require(
            type(response["protocol_version"]) is int and response["protocol_version"] == 1,
            "snapshot protocol mismatch",
        )
        _require(response["action"] == ACTION, "snapshot action mismatch")
        _require(
            response["ok"] is True and response["error"] is None,
            "invalid snapshot success envelope",
        )
        _require(
            response["input_fingerprint"] == input_fingerprint(request),
            "stale or different raw request fingerprint",
        )
        result = response["result"]
        _keys(
            result,
            {
                "document_id",
                "schema_version",
                "canonical_document",
                "canonical_json",
                "content_hash",
            },
        )
        source = request["document"]
        expected = _expected_document(source)
        _require(result["document_id"] == source["id"], "different document identity")
        _require(
            type(result["schema_version"]) is int
            and result["schema_version"] == source["schema_version"],
            "different document schema",
        )
        # Compare serialized tokens, rather than Python equality (True == 1),
        # and preserve every original formula, ID, seed, feature/ref order.
        canonical_json = _json(expected, canonical=True)
        _require(
            _json(result["canonical_document"], canonical=True) == canonical_json,
            "canonical snapshot changed authored fields or unsupported defaults",
        )
        _require(
            type(result["canonical_json"]) is str and result["canonical_json"] == canonical_json,
            "canonical serialized bytes mismatch",
        )
        _require(
            result["content_hash"] == hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
            "canonical content hash mismatch",
        )
        return {**copy.deepcopy(result), "input_fingerprint": response["input_fingerprint"]}
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise bridge.BridgeError(f"Invalid canonical Part snapshot: {exc}") from exc


def canonical_snapshot(document, *, project_root="", python_executable="", timeout=60.0):
    """Legacy tooling-only capture; its dictionary cannot authorize production writes."""
    try:
        # Detach before transport so caller edits cannot retarget validation.
        request = sidecar_job.snapshot_request(
            {"protocol_version": 1, "action": ACTION, "document": document}
        )
        _expected_document(request["document"])
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise bridge.BridgeError(f"Invalid canonical Part snapshot input: {exc}") from exc
    response = bridge._exchange_raw(
        request, project_root=project_root, python_executable=python_executable, timeout=timeout
    )
    return validate_response(request, response)
