"""Explicit general envelope v2: untouched command checkpoint plus UI schema 1.

The v1 codec remains separate and byte-for-byte unchanged. Neither decoder guesses
or upgrades. Restoring this envelope creates no command, solver evidence, pointer
capture, queued acceptance or input lease. Callers retain failed original text.
"""

from __future__ import annotations

from .general_authoring import GeneralSketchAuthoringState
from .general_draft_store import KIND, STALE_MESSAGE, SnapshotError
from .general_sketch_commands import DraftError, _json, _keys, _require, parse_json
from .general_sketch_draft import GeneralSketchDraft

VERSION = 2
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


def _decode(envelope):
    _keys(envelope, {"schema_version", "kind", "base_sha256", "draft", "ui"})
    _require(
        type(envelope["schema_version"]) is int
        and envelope["schema_version"] == VERSION
        and envelope["kind"] == KIND,
        "Unsupported general authoring kind/version; the saved text is retained.",
    )
    command_draft = GeneralSketchDraft.from_checkpoint_payload(
        envelope["draft"], expected_journal_version=2
    )
    _require(
        envelope["base_sha256"] == command_draft.base_hash,
        "The saved authoring base checksum does not match.",
    )
    return GeneralSketchAuthoringState(command_draft, envelope["ui"])


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
        envelope = _envelope(state)
        _decode(envelope)  # Check identical command and UI invariants on write/read.
        serialized = _json(envelope)
        _require(
            len(serialized.encode("utf-8")) <= MAX_SNAPSHOT_BYTES,
            "The combined general authoring snapshot exceeds its byte limit.",
        )
        return serialized
    except (DraftError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError) as exc:
        raise SnapshotError(f"Cannot save this general authoring draft: {exc}") from exc


def loads(serialized: str) -> dict:
    """Return detached validated intent, with the nested command payload exact."""
    try:
        envelope = parse_json(serialized, MAX_SNAPSHOT_BYTES)
        _json(envelope)  # Validate every decoded Unicode string, including escaped surrogates.
        return _envelope(_decode(envelope))
    except (DraftError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError) as exc:
        raise SnapshotError(
            f"The saved general authoring draft is incompatible; its text is retained: {exc}"
        ) from exc


def restore(serialized: str, current_document_json: str) -> GeneralSketchAuthoringState:
    envelope = loads(serialized)
    if envelope["draft"]["document_json"] != current_document_json:
        raise SnapshotError(STALE_MESSAGE)
    return _decode(envelope)
