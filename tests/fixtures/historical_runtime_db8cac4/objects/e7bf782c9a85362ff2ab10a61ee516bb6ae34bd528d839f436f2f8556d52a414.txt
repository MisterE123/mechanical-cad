"""Independent general-sketch UI snapshot codec; rectangle-v1 stays untouched.

A failed read/restore never edits the supplied text or canonical document. Callers
must retain the original slot bytes for explicit recovery/Discard. Successful
Resume restores local sketch Undo/Redo and observed raw input, but never native
solver evidence, queued acceptance, gesture capture, timers or process tokens.
"""

from __future__ import annotations

import hashlib

from .general_sketch_draft import DraftError, GeneralSketchDraft, _json, _keys, parse_json

VERSION = 1
KIND = "general_sketch_ui_draft"
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
STALE_MESSAGE = (
    "This suspended sketch belongs to a different committed document revision. "
    "Restore its exact original document, then Resume; or explicitly Discard this draft. "
    "Its saved text is retained; no automatic merge, rebase or overwrite is performed."
)


class SnapshotError(ValueError):
    """Unsupported/corrupt/stale input. The caller must retain the original bytes."""


def dumps(draft: GeneralSketchDraft) -> str:
    try:
        state = draft.checkpoint_payload()
        # Validate the same replay/identity invariants on both sides of storage.
        GeneralSketchDraft.from_checkpoint_payload(state, expected_journal_version=2)
        envelope = {
            "schema_version": VERSION,
            "kind": KIND,
            "base_sha256": hashlib.sha256(state["document_json"].encode("utf-8")).hexdigest(),
            "draft": state,
        }
        serialized = _json(envelope)
        if len(serialized.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            raise SnapshotError("The general sketch snapshot exceeds its byte limit.")
        return serialized
    except (DraftError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError) as exc:
        raise SnapshotError(f"Cannot save this general sketch draft: {exc}") from exc


def loads(serialized: str) -> dict:
    """Strictly inspect pure intent without treating it as successful evidence."""
    try:
        envelope = parse_json(serialized, MAX_SNAPSHOT_BYTES)
        _keys(envelope, {"schema_version", "kind", "base_sha256", "draft"})
        if (
            type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != VERSION
            or envelope["kind"] != KIND
        ):
            raise SnapshotError(
                "Unsupported general sketch kind/version; the saved text is retained."
            )
        state = envelope["draft"]
        draft = GeneralSketchDraft.from_checkpoint_payload(state, expected_journal_version=2)
        if envelope["base_sha256"] != draft.base_hash:
            raise SnapshotError("The saved general sketch base checksum does not match.")
        return draft.checkpoint_payload()
    except (DraftError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError) as exc:
        raise SnapshotError(
            f"The saved general sketch is incompatible; its text is retained: {exc}"
        ) from exc


def restore(serialized: str, current_document_json: str) -> GeneralSketchDraft:
    state = loads(serialized)
    if state["document_json"] != current_document_json:
        raise SnapshotError(STALE_MESSAGE)
    return GeneralSketchDraft.from_checkpoint_payload(state, expected_journal_version=2)
