"""Strict, pure JSON snapshots of UI drafts, separate from canonical CAD history.

No Blender objects, callbacks, solver/kernel handles or executable data may cross
this boundary. A snapshot restores only against the exact serialized base; it
never merges, rebases, or certifies its cached outline as current geometry.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict

VERSION = 1
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
STALE_MESSAGE = (
    "This suspended sketch belongs to a different committed document revision. "
    "Restore its exact original document (for example with Undo), then Resume; "
    "or Discard this draft and edit the current document. No automatic rebase or overwrite is performed."
)
STATE_FIELDS = {
    "document_json",
    "feature_id",
    "is_edit",
    "phase",
    "first",
    "anchor",
    "width",
    "height",
    "width_text",
    "height_text",
    "width_key",
    "height_key",
    "error",
    "solver_report",
    "validated_json",
    "fix_corner",
    "fixed_target",
    "seed_bounds",
    "seed_override",
    "last_solved_points",
    "original_values",
    "original_text",
    "pending_dimensions",
}


class SnapshotError(ValueError):
    """An unreadable or incompatible snapshot; the caller must retain its bytes."""


def _reject_constant(value):
    raise SnapshotError(f"Non-finite number in saved sketch draft: {value}")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotError(f"Duplicate field in saved sketch draft: {key}")
        result[key] = value
    return result


def _number(value, *, length=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or abs(value) > 1e6
        or not math.isfinite(value)
        or (length and value < 0)
    ):
        raise SnapshotError("Saved draft coordinates or dimensions are invalid.")


def _point(value, *, optional=False):
    if optional and value is None:
        return
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SnapshotError("Saved draft point is invalid.")
    for number in value:
        _number(number)


def _points(value):
    if value is None:
        return
    if not isinstance(value, list) or len(value) != 4:
        raise SnapshotError("Saved draft seed points are invalid.")
    identifiers = set()
    for point in value:
        if not isinstance(point, dict) or set(point) != {"id", "u", "v"}:
            raise SnapshotError("Saved draft seed point fields are unsupported.")
        if not isinstance(point["id"], str):
            raise SnapshotError("Saved draft point identity is invalid.")
        identifiers.add(point["id"])
        _point((point["u"], point["v"]))
    if identifiers != {"p0", "p1", "p2", "p3"}:
        raise SnapshotError("Saved draft point identities are invalid.")


def _validate_state(state):
    if not isinstance(state, dict) or set(state) != STATE_FIELDS:
        raise SnapshotError("Saved draft fields are unsupported. The saved draft is retained.")
    for key in (
        "document_json",
        "feature_id",
        "phase",
        "width_text",
        "height_text",
        "width_key",
        "height_key",
        "error",
        "validated_json",
    ):
        if not isinstance(state[key], str):
            raise SnapshotError(f"Saved draft {key} must be text.")
    for key in ("is_edit", "fix_corner"):
        if not isinstance(state[key], bool):
            raise SnapshotError(f"Saved draft {key} must be boolean.")
    if state["phase"] not in {"FIRST_POINT", "SECOND_POINT", "DIMENSIONS"}:
        raise SnapshotError("Saved draft phase is unsupported.")
    if not all(state[key] for key in ("document_json", "feature_id", "width_key", "height_key")):
        raise SnapshotError("Saved draft identity or base is missing.")
    _point(state["anchor"])
    _point(state["first"], optional=True)
    _point(state["fixed_target"], optional=True)
    for key in ("width", "height"):
        _number(state[key], length=True)
    bounds = state["seed_bounds"]
    if bounds is not None:
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 3:
            raise SnapshotError("Saved draft seed bounds are invalid.")
        _point(bounds[0])
        _number(bounds[1], length=True)
        _number(bounds[2], length=True)
    if state["phase"] == "SECOND_POINT" and state["first"] is None:
        raise SnapshotError("Saved draft is missing its first corner.")
    if state["phase"] == "DIMENSIONS":
        if not state["is_edit"] and bounds is None:
            raise SnapshotError("Saved draft is missing its authoring seeds.")
        if state["fix_corner"] and state["fixed_target"] is None:
            raise SnapshotError("Saved draft is missing its fixed-position intent.")
    _points(state["seed_override"])
    _points(state["last_solved_points"])
    if state["solver_report"] is not None or state["validated_json"]:
        raise SnapshotError("Saved drafts cannot claim verified solver results.")
    for key in ("original_values", "original_text"):
        if not isinstance(state[key], dict):
            raise SnapshotError("Saved draft original parameter values are invalid.")
    if any(not isinstance(value, str) for value in state["original_text"].values()):
        raise SnapshotError("Saved draft original parameter text is invalid.")
    pending = state["pending_dimensions"]
    if pending is not None and (
        not isinstance(pending, dict)
        or set(pending) != {"width", "height", "fix_corner"}
        or not isinstance(pending["width"], str)
        or not isinstance(pending["height"], str)
        or not isinstance(pending["fix_corner"], bool)
        or state["phase"] != "DIMENSIONS"
    ):
        raise SnapshotError("Saved draft pending dimension input is invalid.")


def dumps(draft):
    """Capture all authoring intent and raw input; deliberately drop verification."""
    state = asdict(draft)
    state["solver_report"] = None
    state["validated_json"] = ""
    _validate_state(state)
    envelope = {
        "schema_version": VERSION,
        "kind": "rectangle_ui_draft",
        "base_sha256": hashlib.sha256(state["document_json"].encode()).hexdigest(),
        "draft": state,
    }
    result = json.dumps(envelope, ensure_ascii=False, allow_nan=False, sort_keys=True)
    if len(result.encode()) > MAX_SNAPSHOT_BYTES:
        raise SnapshotError("The sketch draft is too large to store safely.")
    return result


def loads(serialized):
    """Inspect without changing anything. Unknown/corrupt records fail closed."""
    if not isinstance(serialized, str) or len(serialized.encode()) > MAX_SNAPSHOT_BYTES:
        raise SnapshotError("The saved sketch draft is not bounded JSON text.")
    try:
        envelope = json.loads(
            serialized, parse_constant=_reject_constant, object_pairs_hook=_strict_object
        )
        if not isinstance(envelope, dict) or set(envelope) != {
            "schema_version",
            "kind",
            "base_sha256",
            "draft",
        }:
            raise SnapshotError("Saved draft format is unsupported. The saved draft is retained.")
        if type(envelope["schema_version"]) is not int or envelope["schema_version"] != VERSION:
            raise SnapshotError("Saved draft version is unsupported. The saved draft is retained.")
        if envelope["kind"] != "rectangle_ui_draft":
            raise SnapshotError("Saved draft kind is unsupported.")
        state = envelope["draft"]
        _validate_state(state)
        if envelope["base_sha256"] != hashlib.sha256(state["document_json"].encode()).hexdigest():
            raise SnapshotError("The saved draft's base-document checksum does not match.")
        base = json.loads(
            state["document_json"],
            parse_constant=_reject_constant,
            object_pairs_hook=_strict_object,
        )
        if (
            not isinstance(base, dict)
            or not isinstance(base.get("features"), list)
            or not isinstance(base.get("parameters"), dict)
        ):
            raise SnapshotError("The saved draft's base document is invalid.")
        return state
    except (TypeError, KeyError, ValueError, OverflowError, RecursionError) as exc:
        if isinstance(exc, SnapshotError):
            raise
        raise SnapshotError(
            "The saved sketch draft cannot be read; its stored text is retained."
        ) from exc


def restore(serialized, current_document_json, draft_type):
    """Restore exact state, never reinitialize seeds or accept an old DoF claim."""
    state = loads(serialized)
    if state["document_json"] != current_document_json:
        raise SnapshotError(STALE_MESSAGE)
    try:
        draft = draft_type(
            state["document_json"], feature_id=state["feature_id"], is_edit=state["is_edit"]
        )
        if (
            draft.width_key != state["width_key"]
            or draft.height_key != state["height_key"]
            or draft.original_values != state["original_values"]
            or draft.original_text != state["original_text"]
        ):
            raise SnapshotError("Saved draft parameter identity differs from its base document.")
        if not state["is_edit"] and any(
            feature.get("id") == state["feature_id"]
            for feature in json.loads(state["document_json"])["features"]
        ):
            raise SnapshotError("The saved draft's new feature ID already exists in its base.")
        for key, value in state.items():
            setattr(draft, key, copy.deepcopy(value))
        for key in ("first", "anchor", "fixed_target"):
            if getattr(draft, key) is not None:
                setattr(draft, key, tuple(getattr(draft, key)))
        if draft.seed_bounds is not None:
            anchor, width, height = draft.seed_bounds
            draft.seed_bounds = (tuple(anchor), width, height)
        return draft
    except (TypeError, KeyError, ValueError, OverflowError, RecursionError) as exc:
        if isinstance(exc, SnapshotError):
            raise
        raise SnapshotError("The saved sketch is incompatible with this rectangle editor.") from exc
