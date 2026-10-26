"""Authoritative, native-free Part serialization receipts.

The existing Document serializer defines source identity. This boundary only
validates and serializes authored records; it does not solve, replay, or write.
"""

from __future__ import annotations

import hashlib
import json
import math

from .errors import CADException
from .model import MAX_DOCUMENT_BYTES, Document
from .result_policy import validate_result_version

BACKEND_CAPABILITIES = frozenset({"mcad.snapshot-sketch3/1"})


def validate_snapshot_source(document: Document) -> None:
    """Admit canonical typed graphs without solving or inventing geometry."""
    if any(
        feature.sketch is not None and feature.sketch.schema_version == 3
        for feature in document.features
    ):
        from .result_policy_v3 import validate_result_version_v3

        # Serialization preserves unresolved design intent; geometry admission
        # belongs to replay/export, not a canonical source receipt.
        validate_result_version_v3(document, 3)
    else:
        validate_result_version(document, 2)


def _check_input_budget(value):
    """Bound direct-Python JSON trees, including expanded shared-container DAGs."""
    memo, active = {}, set()

    def check(size, nodes):
        if size > MAX_DOCUMENT_BYTES or nodes > 1_000_000:
            raise CADException("document_too_large", "Snapshot input exceeds its JSON budget.")

    def visit(item, depth):
        if depth > 32:
            raise CADException("invalid_json", "Snapshot JSON nesting exceeds limit.")
        kind = type(item)
        if kind in (dict, list):
            identity = id(item)
            if identity in active:
                raise CADException("invalid_json", "Snapshot input contains cyclic JSON.")
            if identity in memo:
                size, nodes, height = memo[identity]
                if depth + height > 32:
                    raise CADException("invalid_json", "Snapshot JSON nesting exceeds limit.")
                return memo[identity]
            check(len(item), len(item) + 1)
            active.add(identity)
            size, nodes, height = 2, 1, 0
            try:
                entries = item.items() if kind is dict else enumerate(item)
                for index, (key, child) in enumerate(entries):
                    size += int(index > 0)
                    if kind is dict:
                        if type(key) is not str:
                            raise CADException(
                                "invalid_json", "Snapshot JSON keys must be strings."
                            )
                        size += visit(key, depth + 1)[0] + 1
                    child_size, child_nodes, child_height = visit(child, depth + 1)
                    size += child_size
                    nodes += child_nodes
                    height = max(height, child_height + 1)
                    check(size, nodes)
            finally:
                active.remove(identity)
            memo[identity] = size, nodes, height
            return memo[identity]
        if kind is str:
            check(len(item) + 2, 1)
            size = 2
            for character in item:
                code = ord(character)
                if character in '\\"\b\f\n\r\t':
                    size += 2
                elif 0x20 <= code <= 0x7E:
                    size += 1
                else:
                    size += 6 if code <= 0xFFFF else 12
                check(size, 1)
        elif kind is int:
            if item.bit_length() > 16_384:
                raise CADException(
                    "invalid_json", "Snapshot integer exceeds numeric resource limit."
                )
            size = len(str(item))
        elif kind is float and math.isfinite(item):
            size = len(repr(item))
        elif kind in (bool, type(None)):
            size = 5 if item is False else 4
        else:
            raise CADException("invalid_json", "Snapshot input must contain finite JSON data.")
        return size, 1, 0

    visit(value, 0)


def input_fingerprint(request: dict) -> str:
    """Bind the complete input tree, including omitted defaults and numeric types.

    Whitespace/key order are transport details. Unlike a Document content hash,
    this digest never fills defaults, sorts sketch records, or converts numbers.
    """
    try:
        _check_input_budget(request)
        raw = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False)
        payload = raw.encode("utf-8")
    except CADException:
        raise
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise CADException("invalid_json", "Snapshot input must be finite JSON.") from exc
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise CADException("document_too_large", "Snapshot input exceeds the 2 MiB limit.")
    return hashlib.sha256(payload).hexdigest()


def canonical_snapshot(data: dict) -> dict:
    """Return detached canonical data and the hash of exact Document JSON bytes."""
    input_fingerprint(data)  # Apply the JSON/size boundary to direct Python calls too.
    document = Document.from_dict(data)
    validate_snapshot_source(document)
    try:
        canonical_json = document.to_json()
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise CADException("invalid_json", "Snapshot must contain finite JSON.") from exc
    return {
        "document_id": document.id,
        "schema_version": document.schema_version,
        "canonical_document": document.to_dict(),
        "canonical_json": canonical_json,
        "content_hash": hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
    }
