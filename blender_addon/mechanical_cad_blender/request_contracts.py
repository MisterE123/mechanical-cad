"""Pure bounded JSON request snapshots shared by native-free add-on boundaries.

No transport or native imports belong here. Transport adapters translate
RequestError to their established public error type without copying this parser.
"""

from __future__ import annotations

import math
from typing import Any

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_REQUEST_DEPTH = 64
MAX_REQUEST_NODES = 1_000_000
MAX_INTEGER_BITS = 16_384


class RequestError(ValueError):
    """A request cannot be safely represented as bounded finite JSON."""


def snapshot_request(
    request: dict[str, Any],
    *,
    max_bytes: int = MAX_DOCUMENT_BYTES,
    max_depth: int = MAX_REQUEST_DEPTH,
    max_nodes: int = MAX_REQUEST_NODES,
    max_integer_bits: int = MAX_INTEGER_BITS,
) -> dict[str, Any]:
    """Validate resources and detach exact JSON before traversal or full encoding.

    Size accounting matches json.dumps' default ASCII escaping and separators.
    Memoized container sizes reject exponentially expanded shared-container DAGs
    without walking that expansion; active IDs detect cycles. The returned copy
    retains benign sharing, but shares no mutable container with the caller.
    Depth, expanded-node count and integer bit length are separately bounded.
    This helper can precede action-specific validators that recursively walk JSON.
    """
    memo = {}
    active = set()

    def check_size(size, budget):
        if size > budget:
            raise RequestError("Document exceeds the 2 MiB input limit.")
        return size

    def string_size(value, budget):
        # A code point always requires at least one output byte. Reject huge
        # strings in O(1), before any escaping or iteration over their contents.
        check_size(len(value) + 2, budget)
        size = 2
        for character in value:
            code = ord(character)
            if character in '\\"\b\f\n\r\t':
                size += 2
            elif 0x20 <= code <= 0x7E:
                size += 1
            else:
                size += 6 if code <= 0xFFFF else 12
            check_size(size, budget)
        return size

    def visit(value, depth, byte_budget, node_budget):
        if depth > max_depth:
            raise ValueError("request exceeds the JSON nesting limit")
        if node_budget < 1:
            raise ValueError("request exceeds the JSON node limit")
        kind = type(value)
        if kind not in (dict, list):
            if kind is str:
                size = string_size(value, byte_budget)
            elif value is None:
                size = 4
            elif kind is bool:
                size = 4 if value else 5
            elif kind is int:
                # Do not decimalize an attacker-sized integer even when Python's
                # own configurable integer-string conversion limit is disabled.
                if value.bit_length() > max_integer_bits:
                    raise ValueError("integer exceeds the JSON numeric resource limit")
                size = len(str(value))
            elif kind is float and math.isfinite(value):
                size = len(repr(value))
            else:
                raise ValueError("request contains a non-finite or non-JSON value")
            return value, check_size(size, byte_budget), 1, 0

        identity = id(value)
        if identity in active:
            raise ValueError("request contains cyclic JSON containers")
        if identity in memo:
            snapshot, size, nodes, height = memo[identity]
            if depth + height > max_depth:
                raise ValueError("request exceeds the JSON nesting limit")
            check_size(size, byte_budget)
            if nodes > node_budget:
                raise ValueError("request exceeds the JSON node limit")
            return snapshot, size, nodes, height
        if len(value) >= node_budget:
            raise ValueError("request exceeds the JSON node limit")
        # Every list entry costs at least one byte plus its separator. Dictionary
        # entries additionally need an empty quoted key and a colon separator.
        minimum = 2 + max(0, len(value) - 1) * 2 + len(value) * (5 if kind is dict else 1)
        check_size(minimum, byte_budget)
        active.add(identity)
        snapshot = {} if kind is dict else []
        size, nodes, height = 2, 1, 0
        try:
            entries = value.items() if kind is dict else enumerate(value)
            for index, (key, item) in enumerate(entries):
                if index:
                    size += 2  # ', '
                if kind is dict:
                    if type(key) is not str:
                        raise ValueError("JSON object keys must be strings")
                    size += string_size(key, byte_budget - size) + 2  # ': '
                check_size(size, byte_budget)
                copied, child_size, child_nodes, child_height = visit(
                    item, depth + 1, byte_budget - size, node_budget - nodes
                )
                size = check_size(size + child_size, byte_budget)
                nodes += child_nodes
                if nodes > node_budget:
                    raise ValueError("request exceeds the JSON node limit")
                height = max(height, child_height + 1)
                if kind is dict:
                    snapshot[key] = copied
                else:
                    snapshot.append(copied)
        finally:
            active.remove(identity)
        memo[identity] = snapshot, size, nodes, height
        return memo[identity]

    try:
        if type(request) is not dict:
            raise ValueError("CAD request must be a JSON object")
        snapshot, _, _, _ = visit(request, 0, max_bytes, max_nodes)
        return snapshot
    except RequestError:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError, RuntimeError) as exc:
        raise RequestError(f"Document cannot be encoded as finite JSON: {exc}") from exc
