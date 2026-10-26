"""Finite JSON, identity and schema primitives for the native-free assembly boundary."""

from __future__ import annotations

import hashlib
import json
import math
import re

ASSEMBLY_PROTOCOL_VERSION = 1

ACTIONS = frozenset({"assembly_replay", "assembly_check", "assembly_sample"})

POLICY_VERSION = "assembly-exact-pose-v1"

EVALUATOR_VERSION = "rooted-tree-v1"

MAX_PARTS = 16

MAX_INSTANCES = 64

MAX_FRAMES = 128

MAX_JOINTS = 63

MAX_SAMPLES = 32

MAX_PAIR_QUERIES = 4096

MAX_VERTICES = 100_000

MAX_TRIANGLES = 200_000

_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")

_HASH = re.compile(r"^[0-9a-f]{64}$")

FLAGS = {
    "complete",
    "known_interference",
    "known_clearance_violation",
    "has_threshold_contacts",
    "passed",
}

DEFAULT_POLICY = {
    "linear_tolerance_mm": 1e-6,
    "volume_tolerance_mm3": 1e-9,
    "linear_deflection_mm": 0.1,
}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    ).hexdigest()


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _keys(value, required, optional=()):
    _require(type(value) is dict, "expected an object")
    _require(
        set(required) <= set(value) <= set(required) | set(optional), "unknown or missing fields"
    )


def _number(value, *, bound=1e100, minimum=None):
    _require(
        type(value) in (int, float) and math.isfinite(value), "non-finite or non-numeric value"
    )
    _require(
        abs(value) <= bound and (minimum is None or value >= minimum),
        "numeric value outside bounds",
    )
    return value


def _text(value, maximum=256):
    _require(type(value) is str and 0 < len(value) <= maximum, "missing or invalid text")


def _identifier(value):
    _require(type(value) is str and _ID.fullmatch(value), "invalid stable ID")


def _hash(value):
    _require(type(value) is str and _HASH.fullmatch(value), "invalid SHA-256 fingerprint")


def _records(value, maximum, key="id"):
    _require(type(value) is list and len(value) <= maximum, "record count exceeds limit")
    result = {}
    for row in value:
        _require(type(row) is dict and type(row.get(key)) is str, "missing record identity")
        _require(row[key] not in result, "duplicate record identity")
        result[row[key]] = row
    return result


def _vector(value, length, bound=1e100):
    _require(type(value) is list and len(value) == length, "invalid vector")
    for item in value:
        _number(item, bound=bound)


def _frame(value):
    _keys(value, {"xyz_mm", "wxyz"})
    _vector(value["xyz_mm"], 3, 1e6)
    _vector(value["wxyz"], 4, 1.00000001)
    _require(abs(sum(q * q for q in value["wxyz"]) - 1) <= 1e-9, "non-unit quaternion")


def _finite_tree(value, depth=0):
    _require(depth <= 32, "excessive response nesting")
    if type(value) is dict:
        _require(all(type(key) is str for key in value), "non-string object keys")
        for item in value.values():
            _finite_tree(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _finite_tree(item, depth + 1)
    elif type(value) in (int, float):
        _number(value)
    else:
        _require(value is None or type(value) in (str, bool), "non-JSON value")


def _diagnostics(value):
    _require(type(value) is list and len(value) <= 4096, "invalid diagnostics")
    for row in value:
        _keys(row, {"code", "message"}, {"subject", "details", "stage"})
        _text(row["code"])
        _text(row["message"], 100_000)
        if row.get("subject") is not None:
            _text(row["subject"])


def _versions(value):
    _require(type(value) is dict and 1 <= len(value) <= 16, "missing runtime versions")
    for key, item in value.items():
        _text(key)
        _text(item)


def _same_supplied(raw, canonical):
    """A source hash pins added Part serializer defaults; supplied data cannot change."""
    if type(raw) is dict:
        _require(
            type(canonical) is dict and set(raw) <= set(canonical), "canonical input dropped fields"
        )
        for key, value in raw.items():
            _same_supplied(value, canonical[key])
    elif type(raw) is list:
        _require(
            type(canonical) is list and len(raw) == len(canonical),
            "canonical input changed records",
        )
        for a, b in zip(raw, canonical, strict=True):
            _same_supplied(a, b)
    else:
        _require(
            raw == canonical and (type(raw) is bool) == (type(canonical) is bool),
            "canonical input changed a supplied value",
        )
