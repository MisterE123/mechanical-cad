"""Bounded, exact raw text for a general-sketch inline dimension field.

This is adapted from the isolated inline-modal text-buffer proof, not its
synthetic evaluator or controller. It never parses, evaluates, normalizes or
trims text. Invalid formulas remain editable verbatim; an evaluator's formula
length/grammar restrictions are separate from the draft's raw-retention budget.

Caret/selection indices count Unicode scalars, not UTF-8 bytes, UTF-16 units or
graphemes. Valid UTF-8 and the existing general draft raw limit are enforced on
construction and every edit. Lone surrogates and oversized imports are rejected;
callers must retain rejected source text separately for explicit recovery.

This intentionally does not provide native-textbox IME/composition, grapheme,
bidi/shaping, accessibility/screen-reader or OS text-services parity. A separate
ordinary native-panel fallback is required. No Blender, clipboard, renderer,
solver or native-kernel access belongs here. Clipboard callers explicitly read
``selected_text`` and pass retrieved text to ``insert``.

Each text mutation is one *local text* Undo step. This history neither invokes
nor substitutes for the sketch command journal or Blender's canonical Undo.
Navigation is not a text revision. History retains at most 128 combined Undo/Redo
records, each at most MAX_RAW_TEXT_BYTES (currently 64 KiB) in UTF-8: at most
8 MiB of raw-history payload, plus bounded Python object overhead. A scalar
length preflight also bounds temporary encodings, copies and display projection.
"""

from __future__ import annotations

import unicodedata

from .general_sketch_commands import MAX_COUNTER, MAX_RAW_TEXT_BYTES

_TextState = tuple[str, int, int]
_History = tuple[_TextState, ...]
_HISTORY_LIMIT = 128


def _utf8_size(raw: str) -> int:
    """Encode only after a bounded scalar-length check by the caller."""
    return len(raw.encode("utf-8", errors="strict"))


def _validate_text(raw: str, limit: int) -> None:
    if len(raw) > limit:
        raise ValueError(f"Text exceeds the {limit}-byte UTF-8 limit.")
    try:
        size = _utf8_size(raw)
    except UnicodeEncodeError as exc:
        raise ValueError("Text must contain valid Unicode scalars encodable as UTF-8.") from exc
    if size > limit:
        raise ValueError(f"Text exceeds the {limit}-byte UTF-8 limit.")


def _push(history: _History, state: _TextState) -> _History:
    """Prepare bounded immutable history before any live buffer mutation."""
    return history[-(_HISTORY_LIMIT - 1) :] + (state,)


class TextBuffer:
    """Exact text, scalar caret/anchor, and bounded local text Undo/Redo.

    ``limit`` is a UTF-8 byte budget between zero and MAX_RAW_TEXT_BYTES;
    it cannot expand the production resource bounds. Construction raises
    TypeError/ValueError for malformed or oversized input. Insertion returns
    False and sets ``error`` for invalid Unicode or exceeded byte budgets,
    preserving text, selection, revision and both history stacks.

    Text methods return whether text changed; navigation methods return whether
    the caret/anchor changed. An identical selected replacement collapses its
    selection but creates no revision/history entry. Errors persist through
    navigation/no-ops and clear on a successful text mutation. Revision exhaustion
    raises OverflowError, and allocation failures propagate MemoryError; both
    leave the entire buffer unchanged. All allocations needed for an edit or
    history transition complete before live text/history/caret are replaced.
    """

    HISTORY_LIMIT = _HISTORY_LIMIT
    __slots__ = (
        "_raw",
        "_limit",
        "_caret",
        "_anchor",
        "_revision",
        "_error",
        "_undo",
        "_redo",
    )

    def __init__(self, raw: str, limit: int = MAX_RAW_TEXT_BYTES):
        if type(raw) is not str:
            raise TypeError("raw must be a string")
        self._require_int(limit, "limit")
        if not 0 <= limit <= MAX_RAW_TEXT_BYTES:
            raise ValueError(f"limit must be between 0 and {MAX_RAW_TEXT_BYTES} bytes")
        _validate_text(raw, limit)
        self._raw = raw
        self._limit = limit
        self._caret = self._anchor = len(raw)
        self._revision = 0
        self._error: str | None = None
        self._undo: _History = ()
        self._redo: _History = ()

    @staticmethod
    def _require_int(value: int, name: str) -> None:
        if type(value) is not int:
            raise TypeError(f"{name} must be an integer")

    @staticmethod
    def _require_select(select: bool) -> None:
        if type(select) is not bool:
            raise TypeError("select must be a boolean")

    @property
    def raw(self) -> str:
        return self._raw

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def caret(self) -> int:
        return self._caret

    @property
    def anchor(self) -> int:
        return self._anchor

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def selection(self) -> tuple[int, int]:
        return min(self._caret, self._anchor), max(self._caret, self._anchor)

    @property
    def selected_text(self) -> str:
        start, end = self.selection
        return self._raw[start:end]

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _state(self) -> _TextState:
        return self._raw, self._caret, self._anchor

    def _next_revision(self) -> int:
        if self._revision >= MAX_COUNTER:
            raise OverflowError("Local text revision limit reached; the buffer is unchanged.")
        return self._revision + 1

    def _replace(self, start: int, end: int, text: str) -> bool:
        """Prepare a bounded replacement and history before committing any edit."""
        # Check before concatenation/encoding: arbitrarily large pasted strings
        # must not be copied even when every scalar is one UTF-8 byte.
        if len(self._raw) - (end - start) + len(text) > self._limit:
            self._error = f"Text exceeds the {self._limit}-byte UTF-8 limit."
            return False
        new_raw = self._raw[:start] + text + self._raw[end:]
        new_caret = start + len(text)
        if new_raw == self._raw:
            self._caret = self._anchor = new_caret
            return False
        try:
            _validate_text(new_raw, self._limit)
        except ValueError as exc:
            self._error = str(exc)
            return False
        revision = self._next_revision()
        undo = _push(self._undo, self._state())
        # Slot assignments below perform no allocations. Even MemoryError during
        # the preparations above leaves text, caret, errors and history intact.
        self._raw = new_raw
        self._caret = self._anchor = new_caret
        self._undo = undo
        self._redo = ()
        self._revision = revision
        self._error = None
        return True

    def insert(self, text: str) -> bool:
        """Insert exact text at the caret, or replace the selection atomically."""
        if type(text) is not str:
            raise TypeError("text must be a string")
        start, end = self.selection
        return self._replace(start, end, text)

    def backspace(self) -> bool:
        """Delete selection, otherwise one Unicode scalar before the caret."""
        start, end = self.selection
        if start == end:
            if start == 0:
                return False
            start -= 1
        return self._replace(start, end, "")

    def delete(self) -> bool:
        """Delete selection, otherwise one Unicode scalar after the caret."""
        start, end = self.selection
        if start == end:
            if end == len(self._raw):
                return False
            end += 1
        return self._replace(start, end, "")

    def place(self, index: int, select: bool = False) -> bool:
        """Place at a clamped scalar index, preserving the anchor with shift."""
        self._require_int(index, "index")
        self._require_select(select)
        caret = max(0, min(index, len(self._raw)))
        anchor = self._anchor if select else caret
        changed = (caret, anchor) != (self._caret, self._anchor)
        self._caret = caret
        self._anchor = anchor
        return changed

    def move(self, delta: int, select: bool = False) -> bool:
        """Move by scalars; unshifted movement collapses a selection first.

        Nonzero unshifted movement collapses to the directional selection edge
        without an extra step. A zero delta is always a no-op.
        """
        self._require_int(delta, "delta")
        self._require_select(select)
        if delta == 0:
            return False
        start, end = self.selection
        if not select and start != end:
            return self.place(start if delta < 0 else end)
        return self.place(self._caret + delta, select=select)

    def home(self, select: bool = False) -> bool:
        return self.place(0, select=select)

    def end(self, select: bool = False) -> bool:
        return self.place(len(self._raw), select=select)

    def select_all(self) -> bool:
        caret, anchor = len(self._raw), 0
        changed = (caret, anchor) != (self._caret, self._anchor)
        self._caret = caret
        self._anchor = anchor
        return changed

    def undo(self) -> bool:
        """Undo one local text edit, restoring the exact pre-edit selection."""
        if not self._undo:
            return False
        revision = self._next_revision()
        raw, caret, anchor = self._undo[-1]
        undo = self._undo[:-1]
        redo = _push(self._redo, self._state())
        self._raw = raw
        self._caret = caret
        self._anchor = anchor
        self._undo = undo
        self._redo = redo
        self._revision = revision
        self._error = None
        return True

    def redo(self) -> bool:
        """Redo one local text edit, restoring its pre-Undo caret/selection."""
        if not self._redo:
            return False
        revision = self._next_revision()
        raw, caret, anchor = self._redo[-1]
        undo = _push(self._undo, self._state())
        redo = self._redo[:-1]
        self._raw = raw
        self._caret = caret
        self._anchor = anchor
        self._undo = undo
        self._redo = redo
        self._revision = revision
        self._error = None
        return True

    def display_parts(self) -> list[str]:
        """Return one display string per raw scalar, escaping invisible controls.

        Rendering, measurement, selection and hit tests must use these same parts:
        raw boundary ``i`` follows parts[:i]. Multiple-glyph escapes represent one
        raw scalar. C0/C1 and format controls (including bidi controls and ZWJ),
        plus Unicode line/paragraph separators, are escaped without rewriting raw.
        This is a display projection, never a serialization or parsing format.
        """
        shortcuts = {
            "\n": r"\n",
            "\r": r"\r",
            "\t": r"\t",
            "\b": r"\b",
            "\f": r"\f",
            "\v": r"\v",
        }
        parts = []
        for char in self._raw:
            if char in shortcuts:
                parts.append(shortcuts[char])
            elif unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"}:
                value = ord(char)
                if value <= 0xFF:
                    parts.append(f"\\x{value:02x}")
                elif value <= 0xFFFF:
                    parts.append(f"\\u{value:04x}")
                else:
                    parts.append(f"\\U{value:08x}")
            else:
                parts.append(char)
        return parts

    def snapshot(self) -> dict:
        """Return detached JSON-serializable diagnostics, never persisted history."""
        return {
            "raw": self._raw,
            "caret": self._caret,
            "anchor": self._anchor,
            "selection": list(self.selection),
            "revision": self._revision,
            "error": self._error,
            "limit": self._limit,
            "can_undo": self.can_undo,
            "can_redo": self.can_redo,
        }
