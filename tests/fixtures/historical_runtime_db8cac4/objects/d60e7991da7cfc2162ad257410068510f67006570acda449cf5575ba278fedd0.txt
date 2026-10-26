"""Explicit general envelope 3: journal 3 and authoring UI 2 only.

The shared dispatcher selects this pure codec only for an explicit capable
envelope/state. It retains exact original base text, all local history and raw
observations; it never restores solver evidence, queued acceptance, pointer
capture or owner authorization. Visible Arc controls remain separately gated.
"""

from __future__ import annotations

from .general_authoring import ARC_UI_VERSION, GeneralSketchAuthoringState
from .general_draft_store import KIND, STALE_MESSAGE, SnapshotError
from .general_sketch_commands import DraftError, _json, _keys, _require, parse_json
from .general_sketch_draft import GeneralSketchDraft

VERSION = 3
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


def _decode(envelope):
    _keys(envelope, {"schema_version", "kind", "base_sha256", "draft", "ui"})
    _require(
        type(envelope["schema_version"]) is int
        and envelope["schema_version"] == VERSION
        and envelope["kind"] == KIND,
        "Unsupported arc authoring kind/version; the saved text is retained.",
    )
    command_draft = GeneralSketchDraft.from_checkpoint_payload(
        envelope["draft"],
        expected_journal_version=3,
    )
    _require(
        envelope["base_sha256"] == command_draft.base_hash,
        "The saved authoring base checksum does not match.",
    )
    return GeneralSketchAuthoringState(
        command_draft,
        envelope["ui"],
        ui_version=ARC_UI_VERSION,
    )


def _envelope(state):
    return {
        "schema_version": VERSION,
        "kind": KIND,
        "base_sha256": state.base_hash,
        "draft": state.command_draft.checkpoint_payload(),
        "ui": state.ui_payload(),
    }


def dumps(state: GeneralSketchAuthoringState) -> str:
    try:
        _require(type(state) is GeneralSketchAuthoringState, "Expected general authoring state.")
        _require(
            state.ui_version == ARC_UI_VERSION and state.command_draft.journal_version == 3,
            "Arc envelope 3 requires exactly UI 2 and journal 3.",
        )
        envelope = _envelope(state)
        _decode(envelope)
        serialized = _json(envelope)
        _require(
            len(serialized.encode("utf-8")) <= MAX_SNAPSHOT_BYTES,
            "The combined arc authoring snapshot exceeds its byte limit.",
        )
        return serialized
    except (DraftError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError) as exc:
        raise SnapshotError(f"Cannot save this arc authoring draft: {exc}") from exc


def loads(serialized: str) -> dict:
    """Return detached validated intent, never an owner capability or saved evidence."""
    try:
        envelope = parse_json(serialized, MAX_SNAPSHOT_BYTES)
        _json(envelope)
        return _envelope(_decode(envelope))
    except (DraftError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError) as exc:
        raise SnapshotError(
            f"The saved arc authoring draft is incompatible; its text is retained: {exc}"
        ) from exc


def restore(serialized: str, current_document_json: str) -> GeneralSketchAuthoringState:
    envelope = loads(serialized)
    if envelope["draft"]["document_json"] != current_document_json:
        raise SnapshotError(STALE_MESSAGE)
    return _decode(envelope)
