"""Strict saved repair intent, not native evidence or canonical model history.

Version 1 retains exact base bytes and ordered proposal states. No migration,
receipt, token, failure report, mesh or executable value belongs in this codec.
"""

import hashlib
import json
import math

from . import operation_contracts, repair_scope, sketch_annotation_store
from .general_sketch_commands import parse_json

VERSION = 1
KIND = "unapplied_repair_intent"
MAX_BYTES = 32 * 1024 * 1024
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_STATES = 32  # At most 64 native requests: base + states + selected-binding probes.
_FIELDS = {
    "schema_version",
    "kind",
    "base_json",
    "base_hash",
    "owner_id",
    "scale",
    "feature_id",
    "states",
    "annotation_before",
    "annotation_after",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def document(raw):
    candidate = parse_json(raw, MAX_DOCUMENT_BYTES)
    json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode("utf-8")
    operation_contracts.validate_authoring_candidate(candidate)
    return candidate


def original_scope(base, candidate, feature_id):
    _require(
        all(base.get(k) == candidate.get(k) for k in set(base) | set(candidate) if k != "features"),
        "Original proposal changed the accepted Part envelope.",
    )
    old, new = base["features"], candidate["features"]
    _require(len(old) == len(new), "Original proposal added or deleted features.")
    changed = [(a, b) for a, b in zip(old, new, strict=True) if a != b]
    _require(
        len(changed) == 1
        and changed[0][0]["id"] == changed[0][1]["id"] == feature_id
        and changed[0][0]["kind"] == changed[0][1]["kind"],
        "Original proposal must edit exactly its named existing feature, retaining its kind and order.",
    )


def _annotations(before, after, base, feature_id):
    if after is None:
        _require(before is None, "Annotation before/after intent must be paired.")
        return
    _require(type(before) is str and type(after) is str, "Invalid annotation intent.")
    sketch_annotation_store.validate(before)
    sketch_annotation_store.validate(after)
    original = next(f for f in base["features"] if f["id"] == feature_id)
    _require(original["kind"] == "sketch_constrained", "Only sketch edits carry annotation intent.")
    # Compare all other document/feature placements, including unavailable records.
    for raw in (before, after):
        _require(
            len(raw.encode()) <= sketch_annotation_store.MAX_STORE_BYTES,
            "Annotation intent too large.",
        )
    maps = []
    for raw in (before, after):
        layouts = sketch_annotation_store._load(raw)["documents"]
        if base["id"] in layouts:
            layouts[base["id"]].pop(feature_id, None)
            if not layouts[base["id"]]:
                del layouts[base["id"]]
        maps.append(layouts)
    _require(maps[0] == maps[1], "Annotation intent changed unrelated sketch placements.")


def decode(raw):
    value = parse_json(raw, MAX_BYTES)
    json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    _require(type(value) is dict and set(value) == _FIELDS, "Unsupported saved repair fields.")
    _require(
        type(value["schema_version"]) is int
        and value["schema_version"] == VERSION
        and value["kind"] == KIND,
        "Unsupported saved repair kind/version; original text retained.",
    )
    _require(
        type(value["owner_id"]) is str and 0 < len(value["owner_id"]) <= 128,
        "Invalid accepted owner identity.",
    )
    scale = value["scale"]
    _require(
        type(scale) in (int, float) and math.isfinite(scale) and scale > 0,
        "Invalid saved unit scale.",
    )
    states = value["states"]
    _require(
        type(states) is list and 1 <= len(states) <= MAX_STATES,
        "Saved repair requires 1 to 32 proposal states.",
    )
    base = document(value["base_json"])
    _require(
        value["base_hash"] == hashlib.sha256(value["base_json"].encode()).hexdigest(),
        "Saved repair accepted-base hash differs.",
    )
    feature_id = value["feature_id"]
    _require(
        type(feature_id) is str and feature_id in {f["id"] for f in base["features"]},
        "Saved edited feature is missing.",
    )
    candidates = [document(state) for state in states]
    original_scope(base, candidates[0], feature_id)
    for previous, candidate in zip(candidates[:-1], candidates[1:], strict=True):
        repair_scope.validate_transition(
            previous, candidate, feature_id, {f["id"] for f in previous["features"]}
        )
    _annotations(value["annotation_before"], value["annotation_after"], base, feature_id)
    return value


def encode(proposal):
    value = {
        "schema_version": VERSION,
        "kind": KIND,
        "base_json": proposal.base_json,
        "base_hash": proposal.base_hash,
        "owner_id": proposal.binding["owner_id"],
        "scale": proposal.binding["scale"],
        "feature_id": proposal.feature_id,
        "states": [candidate for candidate, _failed in proposal.repairs]
        + [proposal.candidate_json],
        "annotation_before": proposal.annotation_before
        if proposal.annotation_after is not None
        else None,
        "annotation_after": proposal.annotation_after,
    }
    # Bound strings before serialization, then check the actual escaped envelope.
    _require(len(value["states"]) <= MAX_STATES, "Saved repair history exceeds 32 states.")
    _require(
        sum(len(v) for v in value["states"]) + len(value["base_json"]) <= MAX_BYTES,
        "Saved repair intent exceeds its byte limit.",
    )
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    decode(raw)
    return raw
