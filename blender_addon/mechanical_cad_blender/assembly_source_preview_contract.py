"""Exact source-preview comparison, never replay/publication authority.

Call only with a freshly validated successful live response. This projection
excludes request identities/timings but preserves every ordered geometry, source
replay and pose field. Existing guarded evidence remains mandatory at publication.
"""

import math
import re

from . import assembly_bridge, bridge

_RESULT_FIELDS = {
    "canonical_assembly": dict,
    "assembly_digest": str,
    "source_hashes": dict,
    "instances": list,
    "parts": list,
    "source_replays": list,
}


def _json_tree(value):
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Source preview keys must be strings")
        for item in value.values():
            _json_tree(item)
    elif type(value) is list:
        for item in value:
            _json_tree(item)
    elif type(value) not in {str, int, float, bool, type(None)}:
        raise ValueError("Source preview requires JSON values")
    elif type(value) is float and not math.isfinite(value):
        raise ValueError("Source preview numbers must be finite")


def validate_source_preview_digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise bridge.BridgeError("Source preview requires an exact immutable SHA-256 digest.")


def source_preview_fingerprint(response):
    """Fingerprint complete relevant replay bytes, without rounding or list sorting."""
    try:
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise ValueError("Source preview requires successful live replay")
        result, report = response["result"], response["report"]
        if type(result) is not dict or type(report) is not dict:
            raise ValueError("Invalid source preview response")
        projected = {key: result[key] for key in _RESULT_FIELDS}
        if any(type(projected[key]) is not kind or not projected[key]
               for key, kind in _RESULT_FIELDS.items()):
            raise ValueError("Missing or malformed source preview fields")
        validate_source_preview_digest(projected["assembly_digest"])
        for digest in projected["source_hashes"].values():
            validate_source_preview_digest(digest)
        for key in ("instances", "parts", "source_replays"):
            if any(type(row) is not dict or not row for row in projected[key]):
                raise ValueError("Malformed source preview records")
        pose = report["base_pose"]
        if type(pose) is not dict or not pose:
            raise ValueError("Missing source preview base pose")
        projection = {"result": projected, "base_pose": pose}
        _json_tree(projection)
        return assembly_bridge.fingerprint(projection)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise bridge.BridgeError("Invalid exact source preview projection: " + str(exc)) from exc


def require_source_preview(response, expected_digest):
    """Reject any changed projected byte before staging a disposable display."""
    validate_source_preview_digest(expected_digest)
    if source_preview_fingerprint(response) != expected_digest:
        raise bridge.BridgeError(
            "The exact source replay differs from the displayed preview. Preview again before Apply."
        )
