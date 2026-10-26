"""Bounded local sketch history and fail-closed restoration, never model history.

Journal sequence numbers describe contiguous retained command positions; the live
revision increases independently on command, Undo and Redo. Native evidence is
never serialized or replayed. Seed transitions are explicit ordinary authoring
intent on Resume. Expanded serialized history size is bounded as well as count.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from .general_sketch_commands import (
    JOURNAL_VERSION,
    MAX_RAW_TEXT_BYTES,
    DraftError,
    PendingDimensionEdit,
    _apply_record,
    _identifier,
    _ids,
    _integer,
    _journal_version,
    _json,
    _keys,
    _record,
    _require,
    _successor,
    _validate_sketch,
)


@dataclass(frozen=True)
class History:
    anchor: dict
    anchor_sequence: int
    anchor_next_id: int
    entries: list
    cursor: int


@dataclass(frozen=True)
class RestoredHistory(History):
    sketch: dict
    revision: int
    allocated_ids: set[str]
    next_id: int


def append_entry(
    before,
    after,
    command,
    entries,
    cursor,
    anchor,
    anchor_sequence,
    *,
    anchor_next_id,
    allocation_before,
    allocation_after,
    max_entries,
    max_bytes,
):
    """Build a detached branch atomically, pruning only the oldest local edits."""
    journal = copy.deepcopy(entries[:cursor])
    sequence = _successor(anchor_sequence + len(journal), "local journal position")
    journal.append(
        {
            "sequence": sequence,
            "allocation_before": allocation_before,
            "allocation_after": allocation_after,
            "command": copy.deepcopy(command),
            "before": copy.deepcopy(before),
            "after": copy.deepcopy(after),
        }
    )
    while len(journal) > max_entries or len(_json(journal).encode("utf-8")) > max_bytes:
        _require(len(journal) > 1, "This sketch edit exceeds the local history byte budget.")
        first = journal.pop(0)
        anchor, anchor_sequence = first["after"], first["sequence"]
        anchor_next_id = first["allocation_after"]
    return History(copy.deepcopy(anchor), anchor_sequence, anchor_next_id, journal, len(journal))


_PREFIXES = {"points": "p", "lines": "l", "circles": "c", "constraints": "r"}
_ALLOCATED_ID = re.compile(r"([plcr])_d([1-9][0-9]*)")
_ARC_PREFIXES = {**_PREFIXES, "arcs": "a"}
_ARC_ALLOCATED_ID = re.compile(r"([plcra])_d([1-9][0-9]*)")


def _generated_ordinal(identifier, *, journal_version=JOURNAL_VERSION):
    pattern = _ARC_ALLOCATED_ID if journal_version == 3 else _ALLOCATED_ID
    match = pattern.fullmatch(identifier)
    _require(match is not None, "Unrecognized allocated sketch identity.")
    return match[1], _integer(int(match[2]), minimum=1)


def _allocation_transition(
    command, before, after, original_ids, *, journal_version=JOURNAL_VERSION
):
    """Replay the allocator, including permanent imported-ID reservations.

    The counter may jump between entries after Undo/branch. Within an accepted
    add, only collisions with original IDs may be skipped: all generated IDs
    from older or abandoned edits are strictly below the recorded starting mark.
    """
    counter = before
    if command["op"] in {
        "add",
        "add_projection",
        "add_rectangle",
        "add_point_line_dimension",
        "add_axis_line",
        "add_length_line",
        "add_diameter_circle",
    }:
        allocations = [
            (prefix, item)
            for collection, prefix in _PREFIXES.items()
            for item in command[collection]
        ]
    elif command["op"] in {"corner_fillet", "adjacent_corner_fillet", "add_projection_arc"}:
        _require(journal_version == 3, "Corner Fillet requires journal 3 capability.")
        allocations = ([("p", point) for point in command["points"]]
                       + [("a", command["arc"])]
                       + [("r", relation) for relation in command["constraints"]])
    elif command["op"] == "add_arc":
        _require(journal_version == 3, "Arc allocation requires journal 3 capability.")
        allocations = [("p", point) for point in command["points"]] + [("a", command["arc"])]
    else:
        allocations = []
    for prefix, item in allocations:
        while f"{prefix}_d{counter}" in original_ids:
            counter = _successor(counter, "stable-ID allocation counter")
        _require(
            item["id"] == f"{prefix}_d{counter}",
            "Journal allocation provenance would reuse or replace an identity.",
        )
        counter = _successor(counter, "stable-ID allocation counter")
    _require(counter == after, "Journal allocation range differs from its explicit command.")


def restore_history(
    state,
    original,
    *,
    max_entries,
    max_bytes,
    max_allocated_ids,
    expected_journal_version=JOURNAL_VERSION,
    validate_candidate=None,
):
    """Replay every retained command, including redo, with exact state continuity."""
    journal_version = _journal_version(expected_journal_version)
    journal = state["journal"]
    _keys(
        journal,
        {"schema_version", "anchor_sequence", "anchor_next_id", "anchor", "cursor", "entries"},
    )
    _require(
        type(journal["schema_version"]) is int and journal["schema_version"] == journal_version,
        "Unsupported local journal version.",
    )
    _validate_sketch(original, journal_version=journal_version)
    revision = _integer(state["revision"])
    allocated, next_id = state["allocated_ids"], _integer(state["next_id"], minimum=1)
    _require(
        type(allocated) is list and len(allocated) <= max_allocated_ids,
        "Invalid stable-ID allocation ledger.",
    )
    for identifier in allocated:
        _identifier(identifier)
    _require(
        allocated == sorted(set(allocated)) and _ids(original) <= set(allocated),
        "Invalid stable-ID ledger identities.",
    )
    original_ids = _ids(original)
    for identifier in set(allocated) - original_ids:
        _, ordinal = _generated_ordinal(identifier, journal_version=journal_version)
        _require(ordinal < next_id, "The ID allocator would reuse an accepted identity.")
    anchor_sequence = _integer(journal["anchor_sequence"])
    anchor_next_id = _integer(journal["anchor_next_id"], minimum=1)
    _require(anchor_next_id <= next_id, "Journal allocation watermark exceeds the allocator.")
    cursor = _integer(journal["cursor"])
    entries = journal["entries"]
    _require(
        type(entries) is list and len(entries) <= max_entries and cursor <= len(entries),
        "Invalid local journal count/cursor.",
    )
    _require(
        len(_json(entries).encode("utf-8")) <= max_bytes,
        "Expanded local journal exceeds its byte limit.",
    )
    anchor = _validate_sketch(journal["anchor"], journal_version=journal_version)
    if validate_candidate is not None:
        validate_candidate(anchor)
    _require(
        anchor["id"] == original["id"] and anchor["plane"] == original["plane"],
        "Journal sketch/workplane identity changed.",
    )
    if anchor_sequence == 0:
        _require(
            _json(anchor) == _json(original) and anchor_next_id == 1,
            "Journal origin differs from its exact base or initial allocator.",
        )
    prefixes = _ARC_PREFIXES if journal_version == 3 else _PREFIXES
    original_kinds = {
        item["id"]: collection for collection in prefixes for item in original.get(collection, [])
    }
    for collection, prefix in prefixes.items():
        for item in anchor.get(collection, []):
            identifier = item["id"]
            if identifier in original_ids:
                _require(
                    original_kinds.get(identifier) == collection,
                    "Journal checkpoint changed an original entity's kind.",
                )
            else:
                actual_prefix, ordinal = _generated_ordinal(
                    identifier, journal_version=journal_version
                )
                _require(
                    actual_prefix == prefix and ordinal < anchor_next_id,
                    "Journal checkpoint violates its allocation watermark.",
                )
    running, seen = anchor, set(_ids(anchor)) | original_ids
    _require(seen <= set(allocated), "Journal checkpoint has unallocated IDs.")
    watermark = anchor_next_id
    current = anchor
    for index, entry in enumerate(entries, 1):
        _keys(
            entry,
            {"sequence", "allocation_before", "allocation_after", "command", "before", "after"},
        )
        allocation_before = _integer(entry["allocation_before"], minimum=1)
        allocation_after = _integer(entry["allocation_after"], minimum=1)
        _require(
            watermark <= allocation_before <= allocation_after <= next_id,
            "Journal allocation watermark continuity is broken.",
        )
        _require(
            type(entry["sequence"]) is int and entry["sequence"] == anchor_sequence + index,
            "Journal revision continuity is broken.",
        )
        _require(
            _json(entry["before"]) == _json(running),
            "Journal canonical state continuity is broken.",
        )
        after = _apply_record(running, entry["command"], journal_version=journal_version)
        if validate_candidate is not None:
            validate_candidate(after)
        _allocation_transition(
            entry["command"],
            allocation_before,
            allocation_after,
            original_ids,
            journal_version=journal_version,
        )
        watermark = allocation_after
        _require(
            _json(after) == _json(entry["after"]) and _json(after) != _json(running),
            "Journal result does not match its explicit command.",
        )
        added = _ids(after) - _ids(running)
        _require(
            not added & seen and _ids(after) <= set(allocated),
            "Journal reuses or invents a stable identity.",
        )
        seen.update(added)
        running = after
        if index == cursor:
            current = running
    _require(
        revision >= anchor_sequence + len(entries), "Live revision predates its accepted journal."
    )
    _require(
        _json(current) == _json(state["accepted_sketch"]),
        "Accepted sketch differs from the local history cursor.",
    )
    return RestoredHistory(
        copy.deepcopy(anchor),
        anchor_sequence,
        anchor_next_id,
        copy.deepcopy(entries),
        cursor,
        copy.deepcopy(current),
        revision,
        set(allocated),
        next_id,
    )


def restore_pending(pending, sketch, revision):
    """Restore observed text and target ownership, with no queued acceptance."""
    if pending is None:
        return None
    _keys(
        pending,
        {"constraint_id", "kind", "refs", "source", "base_revision", "input_revision", "raw_text"},
    )
    _require(type(pending["refs"]) is list, "Invalid pending dimension references.")
    base_revision = _integer(pending["base_revision"])
    input_revision = _integer(pending["input_revision"])
    relation = _record(sketch, "constraints", pending["constraint_id"])
    _require(
        relation["kind"] in {"distance", "radius", "angle"},
        "Choose a driving distance, radius or angle.",
    )
    _require(
        base_revision == revision
        and pending["kind"] == relation["kind"]
        and pending["refs"] == relation["refs"]
        and _json(pending["source"]) == _json(relation["value"]),
        "Pending dimension binding differs from accepted intent.",
    )
    raw = pending["raw_text"]
    _require(
        type(raw) is str and len(raw) <= MAX_RAW_TEXT_BYTES, "Raw dimension input is too large."
    )
    try:
        _require(
            len(raw.encode("utf-8")) <= MAX_RAW_TEXT_BYTES, "Raw dimension input is too large."
        )
    except UnicodeError as exc:
        raise DraftError("Raw dimension input is not valid Unicode.") from exc
    return PendingDimensionEdit(
        pending["constraint_id"],
        relation["kind"],
        tuple(relation["refs"]),
        relation["value"],
        revision,
        input_revision,
        raw,
    )
