"""Shared pure authoring checks, independent of commands and geometry reducers.

The command module reexports these names to preserve existing callers and the
single recoverable exception identity across authoring tools.
"""

import json
import math
import re

from .sketch_bridge import _normalized_sketch

JOURNAL_VERSION = 2
ARC_JOURNAL_VERSION = 3
_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


class DraftError(ValueError):
    """A recoverable authoring/validation problem; accepted intent is unchanged."""


def _require(condition, message):
    if not condition:
        raise DraftError(message)


def _keys(value, expected):
    _require(type(value) is dict and set(value) == set(expected), "Unsupported draft fields.")


def _identifier(value):
    _require(type(value) is str and _ID.fullmatch(value), "Invalid stable sketch ID.")
    return value


def _json(value):
    # Streaming encoding bounds expanded shared-container trees before building
    # one large string. JSON's circular guard and recursion handling stay active.
    try:
        encoder = json.JSONEncoder(
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        chunks, size = [], 0
        for chunk in encoder.iterencode(value):
            size += len(chunk.encode("utf-8"))
            _require(size <= 8 * 1024 * 1024, "Expanded draft JSON exceeds its byte limit.")
            chunks.append(chunk)
        return "".join(chunks)
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, DraftError):
            raise
        raise DraftError("Draft data must be bounded finite JSON.") from exc


def _coordinate(value):
    _require(type(value) in (int, float) and -1e6 <= value <= 1e6, "Coordinate outside ±1e6 mm.")
    _require(math.isfinite(value), "Coordinates must be finite.")
    return value


def _point(value):
    _require(type(value) in (tuple, list) and len(value) == 2, "Expected two XY coordinates.")
    return [_coordinate(number) for number in value]


def _journal_version(value):
    _require(type(value) is int and value in (2, 3), "Unsupported local journal version.")
    return value


def _validate_sketch(sketch, *, journal_version=JOURNAL_VERSION):
    _journal_version(journal_version)
    try:
        if journal_version == ARC_JOURNAL_VERSION:
            from .operation_contracts import validate_authoring_sketch

            validate_authoring_sketch(sketch)
        elif type(sketch) is dict and sketch.get("schema_version") == 3:
            raise DraftError("Sketch schema 3 requires explicit journal 3 capability.")
        else:
            _normalized_sketch(sketch)  # Validate only; never install normalized data.
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError, RecursionError) as exc:
        raise DraftError(f"Invalid sketch intent: {exc}") from exc
    return sketch
