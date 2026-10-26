"""Production contracts adapted from the isolated pure-buffer proof tests.

No Blender session, evaluator, clipboard or native kernel is used. Randomized
cases compare against an independent timeline oracle rather than two stacks.
"""

from __future__ import annotations

import importlib
import json
import random
import subprocess
import sys
import types
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_dimension_text_buffer_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
module = importlib.import_module(PACKAGE + ".dimension_text_buffer")
TextBuffer = module.TextBuffer
MAX_RAW_TEXT_BYTES = module.MAX_RAW_TEXT_BYTES
MAX_COUNTER = module.MAX_COUNTER


class BufferTests(unittest.TestCase):
    def assert_position(self, buffer, caret, anchor=None):
        if anchor is None:
            anchor = caret
        self.assertEqual((buffer.caret, buffer.anchor), (caret, anchor))
        self.assertEqual(buffer.selection, tuple(sorted((caret, anchor))))
        start, end = buffer.selection
        self.assertEqual(buffer.selected_text, buffer.raw[start:end])

    def test_initial_exact_text_and_caret(self):
        raw = "  e\u0301 + é\t\r\n👩\u200d🔬  "
        b = TextBuffer(raw)
        self.assertEqual(b.raw, raw)
        self.assert_position(b, len(raw))
        self.assertEqual(b.revision, 0)
        self.assertIsNone(b.error)
        self.assertFalse(b.can_undo)
        self.assertFalse(b.can_redo)

    def test_empty_buffer_boundaries_and_noops(self):
        b = TextBuffer("")
        for method in (b.backspace, b.delete, b.home, b.end, b.select_all, b.undo, b.redo):
            self.assertFalse(method())
        self.assertFalse(b.insert(""))
        self.assertFalse(b.move(-1))
        self.assertFalse(b.move(1))
        self.assert_position(b, 0)
        self.assertEqual(b.revision, 0)

    def test_insertion_at_end_and_middle_is_verbatim(self):
        b = TextBuffer("ab")
        self.assertTrue(b.insert(" 1,20\t"))
        self.assertEqual(b.raw, "ab 1,20\t")
        b.place(1)
        self.assertTrue(b.insert("\r\n💡"))
        self.assertEqual(b.raw, "a\r\n💡b 1,20\t")
        self.assert_position(b, 4)
        self.assertEqual(b.revision, 2)

    def test_forward_selection_replacement(self):
        b = TextBuffer("abcdef")
        b.place(1)
        b.place(4, select=True)
        self.assert_position(b, 4, 1)
        self.assertEqual(b.selected_text, "bcd")
        self.assertTrue(b.insert("XY"))
        self.assertEqual(b.raw, "aXYef")
        self.assert_position(b, 3)

    def test_reversed_selection_replacement(self):
        b = TextBuffer("abcdef")
        b.place(5)
        b.place(2, select=True)
        self.assertEqual(b.selected_text, "cde")
        b.insert("💡")
        self.assertEqual(b.raw, "ab💡f")
        self.assert_position(b, 3)
        b.undo()
        self.assertEqual(b.raw, "abcdef")
        self.assert_position(b, 2, 5)

    def test_identical_replacement_collapses_without_text_revision(self):
        b = TextBuffer("abc")
        b.place(1)
        b.end(select=True)
        self.assertFalse(b.insert("bc"))
        self.assertEqual(b.raw, "abc")
        self.assert_position(b, 3)
        self.assertEqual(b.revision, 0)
        self.assertFalse(b.can_undo)

    def test_empty_replacement_deletes_selection(self):
        b = TextBuffer("abcdef")
        b.place(4)
        b.place(1, select=True)
        self.assertTrue(b.insert(""))
        self.assertEqual(b.raw, "aef")
        self.assert_position(b, 1)

    def test_unshifted_arrows_collapse_forward_selection(self):
        for delta, expected in ((-1, 1), (1, 4), (-99, 1), (99, 4)):
            with self.subTest(delta=delta):
                b = TextBuffer("abcde")
                b.place(1)
                b.place(4, select=True)
                self.assertTrue(b.move(delta))
                self.assert_position(b, expected)
                self.assertEqual(b.revision, 0)

    def test_unshifted_arrows_collapse_reversed_selection(self):
        b = TextBuffer("abcde")
        b.place(4)
        b.place(1, select=True)
        b.move(1)
        self.assert_position(b, 4)
        b.place(1, select=True)
        b.move(-1)
        self.assert_position(b, 1)

    def test_shift_arrows_reverse_through_anchor(self):
        b = TextBuffer("abcde")
        b.place(2)
        b.move(2, select=True)
        self.assert_position(b, 4, 2)
        b.move(-3, select=True)
        self.assert_position(b, 1, 2)
        b.move(-99, select=True)
        self.assert_position(b, 0, 2)
        b.move(99, select=True)
        self.assert_position(b, 5, 2)

    def test_zero_move_keeps_selection(self):
        b = TextBuffer("abc")
        b.select_all()
        before = b.snapshot()
        self.assertFalse(b.move(0))
        self.assertFalse(b.move(0, select=True))
        self.assertEqual(b.snapshot(), before)

    def test_home_end_and_shift_home_end(self):
        b = TextBuffer("abcd")
        b.place(2)
        b.home(select=True)
        self.assert_position(b, 0, 2)
        b.end(select=True)
        self.assert_position(b, 4, 2)
        b.home()
        self.assert_position(b, 0)
        b.end()
        self.assert_position(b, 4)
        self.assertFalse(b.end())
        self.assertFalse(b.can_undo)

    def test_place_clamps_and_shift_click_preserves_anchor(self):
        b = TextBuffer("abc")
        b.place(-99)
        self.assert_position(b, 0)
        b.place(99, select=True)
        self.assert_position(b, 3, 0)
        b.place(1, select=True)
        self.assert_position(b, 1, 0)
        b.place(2)
        self.assert_position(b, 2)

    def test_select_all_and_replace(self):
        b = TextBuffer("abc")
        self.assertTrue(b.select_all())
        self.assertFalse(b.select_all())
        self.assertEqual(b.selected_text, "abc")
        b.insert(" x ")
        self.assertEqual(b.raw, " x ")
        self.assert_position(b, 3)

    def test_backspace_delete_boundaries(self):
        b = TextBuffer("abc")
        self.assertFalse(b.delete())
        self.assertTrue(b.backspace())
        self.assertEqual(b.raw, "ab")
        self.assert_position(b, 2)
        b.home()
        self.assertFalse(b.backspace())
        self.assertTrue(b.delete())
        self.assertEqual(b.raw, "b")
        self.assert_position(b, 0)
        self.assertEqual(b.revision, 2)

    def test_both_delete_commands_remove_selection_in_either_direction(self):
        for method in ("delete", "backspace"):
            for caret, anchor in ((1, 4), (4, 1)):
                with self.subTest(method=method, caret=caret):
                    b = TextBuffer("abcde")
                    b.place(anchor)
                    b.place(caret, select=True)
                    self.assertTrue(getattr(b, method)())
                    self.assertEqual(b.raw, "ae")
                    self.assert_position(b, 1)
                    b.undo()
                    self.assert_position(b, caret, anchor)

    def test_codepoint_not_grapheme_or_utf16_semantics(self):
        b = TextBuffer("e\u0301💡👩\u200d🔬")
        self.assertEqual(len(b.raw), 6)
        b.place(2)
        b.backspace()
        self.assertEqual(b.raw, "e💡👩\u200d🔬")
        self.assert_position(b, 1)
        b.delete()
        self.assertEqual(b.raw, "e👩\u200d🔬")
        b.place(2)
        b.delete()
        self.assertEqual(b.raw, "e👩🔬")

    def test_default_and_maximum_limit_match_saved_raw_budget(self):
        self.assertEqual(MAX_RAW_TEXT_BYTES, 64 * 1024)
        b = TextBuffer("x" * (MAX_RAW_TEXT_BYTES - 1))
        self.assertEqual(b.limit, MAX_RAW_TEXT_BYTES)
        self.assertTrue(b.insert("x"))
        self.assertEqual(len(b.raw.encode("utf-8")), MAX_RAW_TEXT_BYTES)
        self.assertFalse(b.insert("x"))
        self.assertIn(str(MAX_RAW_TEXT_BYTES), b.error)
        with self.assertRaises(ValueError):
            TextBuffer("x" * (MAX_RAW_TEXT_BYTES + 1))
        with self.assertRaises(ValueError):
            TextBuffer("", limit=MAX_RAW_TEXT_BYTES + 1)

    def test_utf8_budget_counts_bytes_not_scalars(self):
        for scalar in ("a", "é", "א", "界", "💡"):
            width = len(scalar.encode("utf-8"))
            with self.subTest(scalar=scalar):
                b = TextBuffer(scalar, limit=width * 2)
                self.assertTrue(b.insert(scalar))
                self.assertEqual(b.caret, 2)
                before = b.raw
                self.assertFalse(b.insert("x"))
                self.assertEqual(b.raw, before)
                with self.assertRaises(ValueError):
                    TextBuffer(scalar * 2, limit=width * 2 - 1)
        b = TextBuffer("💡" * (MAX_RAW_TEXT_BYTES // 4))
        self.assertEqual(b.caret, MAX_RAW_TEXT_BYTES // 4)
        self.assertFalse(b.insert("a"))

    def test_overlimit_insertion_rejected_atomically(self):
        b = TextBuffer("abcd", limit=4)
        b.place(3)
        b.place(1, select=True)
        before = b.snapshot()
        self.assertFalse(b.insert("123"))
        after = b.snapshot()
        self.assertIsNotNone(after.pop("error"))
        before.pop("error")
        self.assertEqual(after, before)
        self.assertEqual(b.selected_text, "bc")
        self.assertFalse(b.can_undo)

    def test_rejection_preserves_undo_redo_history(self):
        b = TextBuffer("a", limit=3)
        b.insert("b")
        b.insert("c")
        b.undo()
        self.assertEqual(b.raw, "ab")
        self.assertFalse(b.insert("XYZ"))
        self.assertTrue(b.can_redo)
        self.assertTrue(b.redo())
        self.assertEqual(b.raw, "abc")
        self.assertIsNone(b.error)
        b.undo()
        b.undo()
        self.assertEqual(b.raw, "a")

    def test_replacement_uses_net_length(self):
        b = TextBuffer("abcd", limit=4)
        b.select_all()
        self.assertTrue(b.insert("💡"))
        self.assertEqual(b.raw, "💡")
        b.select_all()
        self.assertTrue(b.insert("wxyz"))
        self.assertEqual(b.raw, "wxyz")
        self.assertIsNone(b.error)

    def test_oversized_constructor_never_retains_unbounded_text(self):
        for raw, limit in (
            ("abcdef", 3),
            ("abc", 0),
            ("éé", 3),
            ("💡", 3),
            ("x" * (MAX_RAW_TEXT_BYTES + 1), MAX_RAW_TEXT_BYTES),
        ):
            with self.subTest(length=len(raw), limit=limit):
                with self.assertRaises(ValueError):
                    TextBuffer(raw, limit=limit)

    def test_zero_limit_accepts_only_empty_text(self):
        b = TextBuffer("", limit=0)
        self.assertFalse(b.insert("a"))
        self.assertFalse(b.insert(""))
        self.assertEqual(b.raw, "")
        self.assertFalse(b.can_undo)
        self.assertEqual(b.revision, 0)

    def test_error_persists_through_navigation_and_clears_on_edit(self):
        b = TextBuffer("abc", limit=3)
        b.insert("!")
        error = b.error
        b.home()
        b.move(1)
        b.select_all()
        self.assertEqual(b.error, error)
        b.insert("z")
        self.assertIsNone(b.error)

    def test_undo_redo_restores_text_caret_and_reversed_selection(self):
        b = TextBuffer("abcdef")
        b.place(5)
        b.place(2, select=True)
        b.insert("X")
        self.assertEqual(b.raw, "abXf")
        b.home()
        b.move(1, select=True)
        self.assertTrue(b.undo())
        self.assertEqual(b.raw, "abcdef")
        self.assert_position(b, 2, 5)
        self.assertTrue(b.redo())
        self.assertEqual(b.raw, "abXf")
        self.assert_position(b, 1, 0)
        self.assertEqual(b.revision, 3)

    def test_revision_is_monotonic_including_history(self):
        b = TextBuffer("x")
        b.insert("a")
        self.assertEqual(b.revision, 1)
        b.home()
        b.end()
        self.assertEqual(b.revision, 1)
        b.undo()
        self.assertEqual(b.revision, 2)
        self.assertFalse(b.undo())
        self.assertEqual(b.revision, 2)
        b.redo()
        self.assertEqual(b.revision, 3)
        self.assertFalse(b.redo())
        self.assertEqual(b.revision, 3)

    def test_new_edit_discards_redo(self):
        b = TextBuffer("a")
        b.insert("b")
        b.insert("c")
        b.undo()
        b.insert("X")
        self.assertEqual(b.raw, "abX")
        self.assertFalse(b.can_redo)
        self.assertFalse(b.redo())
        b.undo()
        self.assertEqual(b.raw, "ab")
        b.undo()
        self.assertEqual(b.raw, "a")

    def test_navigation_and_noop_do_not_discard_redo(self):
        b = TextBuffer("a")
        b.insert("b")
        b.undo()
        b.home()
        b.insert("")
        b.move(0)
        b.end()
        self.assertFalse(b.delete())
        self.assertTrue(b.can_redo)
        b.redo()
        self.assertEqual(b.raw, "ab")

    def test_history_is_bounded_and_redo_roundtrips_bound(self):
        b = TextBuffer("")
        for _ in range(TextBuffer.HISTORY_LIMIT + 30):
            b.insert("x")
        final = b.raw
        undone = 0
        while b.undo():
            undone += 1
        self.assertEqual(undone, TextBuffer.HISTORY_LIMIT)
        self.assertEqual(b.raw, "x" * 30)
        redone = 0
        while b.redo():
            redone += 1
        self.assertEqual(redone, TextBuffer.HISTORY_LIMIT)
        self.assertEqual(b.raw, final)
        self.assertEqual(b.revision, 3 * TextBuffer.HISTORY_LIMIT + 30)

    def test_display_parts_escape_controls_without_rewriting(self):
        raw = "a\t\n\r\b\f\v\x00\x1b\x7f\x85\u202e\u200d\u2028\u2029\U000e0001💡e\u0301"
        b = TextBuffer(raw)
        expected = [
            "a",
            r"\t",
            r"\n",
            r"\r",
            r"\b",
            r"\f",
            r"\v",
            r"\x00",
            r"\x1b",
            r"\x7f",
            r"\x85",
            r"\u202e",
            r"\u200d",
            r"\u2028",
            r"\u2029",
            r"\U000e0001",
            "💡",
            "e",
            "\u0301",
        ]
        before = b.snapshot()
        self.assertEqual(b.display_parts(), expected)
        self.assertEqual(len(b.display_parts()), len(raw))
        self.assertEqual(b.raw, raw)
        self.assertEqual(b.snapshot(), before)

    def test_all_c0_c1_controls_have_visible_nonempty_parts(self):
        raw = "".join(chr(i) for i in list(range(32)) + list(range(127, 160)))
        parts = TextBuffer(raw).display_parts()
        self.assertEqual(len(parts), len(raw))
        for part in parts:
            self.assertTrue(part.startswith("\\"))
            self.assertTrue(part.isascii())
            self.assertFalse(any(unicodedata.category(c) == "Cc" for c in part))

    def test_display_boundary_mapping_and_mouse_placement(self):
        raw = "a\n💡\x00z"
        b = TextBuffer(raw)
        parts = b.display_parts()
        # An artificial monospace renderer's exact mapping. A real renderer
        # substitutes measured advances, retaining the same raw-part indices.
        offsets = [0]
        for part in parts:
            offsets.append(offsets[-1] + len(part))
        self.assertEqual(offsets, [0, 1, 3, 4, 8, 9])
        for index, x in enumerate(offsets):
            picked = min(range(len(offsets)), key=lambda i: abs(offsets[i] - x))
            b.place(picked)
            self.assert_position(b, index)
        # A visible four-glyph escape is one selectable raw code point.
        b.place(3)
        b.place(4, select=True)
        self.assertEqual(b.selected_text, "\x00")
        self.assertEqual("".join(parts[3:4]), r"\x00")

    def test_backslash_and_literal_escape_remain_separate_raw_scalars(self):
        b = TextBuffer("\\n\n")
        self.assertEqual(b.display_parts(), ["\\", "n", r"\n"])
        self.assertEqual(len(b.display_parts()), 3)
        b.place(2)
        b.delete()
        self.assertEqual(b.raw, "\\n")

    def test_snapshot_is_serializable_and_detached(self):
        b = TextBuffer("é💡")
        b.select_all()
        snap = b.snapshot()
        self.assertEqual(json.loads(json.dumps(snap)), snap)
        snap["raw"] = "changed"
        snap["selection"][0] = 99
        self.assertEqual(b.raw, "é💡")
        self.assertEqual(b.selection, (0, 2))
        parts = b.display_parts()
        parts.clear()
        self.assertEqual(len(b.display_parts()), 2)

    def test_public_state_is_readonly(self):
        b = TextBuffer("a")
        for name in (
            "raw",
            "limit",
            "caret",
            "anchor",
            "revision",
            "error",
            "selection",
            "selected_text",
            "can_undo",
            "can_redo",
        ):
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    setattr(b, name, 0)

    def test_invalid_argument_types_do_not_mutate(self):
        for raw in (None, 1, ["a"], b"a"):
            with self.assertRaises(TypeError):
                TextBuffer(raw)
        for limit in (True, 1.5, "5", None):
            with self.assertRaises(TypeError):
                TextBuffer("", limit=limit)
        with self.assertRaises(ValueError):
            TextBuffer("", limit=-1)
        b = TextBuffer("abc")
        for operation, argument in (
            (b.insert, None),
            (b.insert, b"a"),
            (b.place, 1.2),
            (b.place, True),
            (b.move, None),
            (b.move, False),
        ):
            with self.subTest(operation=operation.__name__, argument=argument):
                before = b.snapshot()
                with self.assertRaises(TypeError):
                    operation(argument)
                self.assertEqual(b.snapshot(), before)


class ProductionBoundaryTests(unittest.TestCase):
    @staticmethod
    def capture(buffer):
        return buffer.snapshot(), buffer._undo, buffer._redo

    def test_surrogates_rejected_by_constructor_and_paste(self):
        for raw in ("\ud800", "\udfff", "ok\ud800x", "\ud83d\udca1"):
            with self.subTest(raw=repr(raw)):
                with self.assertRaises(ValueError, msg="Only Unicode scalars are accepted"):
                    TextBuffer(raw)
                b = TextBuffer("abc")
                b.insert("d")
                b.undo()
                b.place(1)
                b.end(select=True)
                before, undo, redo = self.capture(b)
                self.assertFalse(b.insert(raw))
                self.assertIn("Unicode scalars", b.error)
                after = b.snapshot()
                before.pop("error")
                after.pop("error")
                self.assertEqual(after, before)
                self.assertEqual((b._undo, b._redo), (undo, redo))
                self.assertTrue(b.redo())
                self.assertEqual(b.raw, "abcd")

    def test_bytes_are_never_implicitly_decoded(self):
        for value in (b"1", b"\xff", b"\xed\xa0\x80", bytearray(b"1")):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    TextBuffer(value)
                b = TextBuffer("x")
                before = self.capture(b)
                with self.assertRaises(TypeError):
                    b.insert(value)
                self.assertEqual(self.capture(b), before)

    def test_oversized_inputs_rejected_before_encoding(self):
        with patch.object(module, "_utf8_size", side_effect=AssertionError("unbounded encode")):
            with self.assertRaises(ValueError):
                TextBuffer("x" * (MAX_RAW_TEXT_BYTES + 1))
        b = TextBuffer("abc", limit=3)
        b.select_all()
        before = self.capture(b)
        with patch.object(module, "_utf8_size", side_effect=AssertionError("unbounded encode")):
            self.assertFalse(b.insert("💡" * (MAX_RAW_TEXT_BYTES + 1)))
        after = self.capture(b)
        self.assertEqual(after[1:], before[1:])
        before[0].pop("error")
        self.assertIsNotNone(after[0].pop("error"))
        self.assertEqual(after[0], before[0])

    def test_exact_utf8_replacement_budget_in_both_selection_directions(self):
        for caret, anchor in ((1, 2), (2, 1)):
            b = TextBuffer("a💡b", limit=6)
            b.place(anchor)
            b.place(caret, select=True)
            self.assertTrue(b.insert("éé"))  # Two scalars replace one at the same byte size.
            self.assertEqual(b.raw, "aééb")
            self.assertEqual(b.caret, 3)
            self.assertTrue(b.undo())
            self.assertEqual((b.caret, b.anchor), (caret, anchor))
            before = self.capture(b)
            self.assertFalse(b.insert("é💡"))  # Scalar count fits but bytes do not.
            self.assertEqual(b.raw, "a💡b")
            self.assertEqual((b._undo, b._redo), before[1:])
            self.assertEqual((b.caret, b.anchor), (caret, anchor))

    def test_invalid_formulas_and_long_saved_pending_text_are_not_evaluated(self):
        samples = (
            "",
            "   ",
            "  60mm  + 2  ",
            "1 / 0",
            "1 + (",
            "NaN",
            "∞",
            "=width * )",
            "radius + missing",
            "__import__('os').system('exit')",
            "  e\u0301 + é\t\r\n👩\u200d🔬  ",
            "x" * MAX_RAW_TEXT_BYTES,
        )
        for raw in samples:
            with self.subTest(length=len(raw), prefix=repr(raw[:20])):
                b = TextBuffer(raw)
                self.assertEqual(b.raw.encode("utf-8"), raw.encode("utf-8"))
                b.select_all()
                before = b.snapshot()
                self.assertTrue(b.insert("replacement"))
                self.assertTrue(b.undo())
                self.assertEqual(b.raw, raw)
                self.assertEqual((b.caret, b.anchor), (len(raw), 0))
                self.assertEqual(b.selected_text, raw)
                self.assertTrue(b.redo())
                self.assertEqual(b.raw, "replacement")
                self.assertEqual(before["revision"], 0)

    def test_revision_limit_is_preflight_for_all_text_mutations(self):
        for operation in ("insert", "backspace", "delete", "undo", "redo"):
            with self.subTest(operation=operation):
                b = TextBuffer("abc")
                b.insert("d")
                b.undo()
                b.home()
                b.move(1, select=True)
                # Establish both stacks for every operation without changing its
                # applicability: this fixture has one Undo and one Redo entry.
                b.redo()
                b.insert("e")
                b.undo()
                b.select_all()
                b._revision = MAX_COUNTER
                before = self.capture(b)
                with self.assertRaisesRegex(OverflowError, "revision limit"):
                    if operation == "insert":
                        b.insert("changed")
                    else:
                        getattr(b, operation)()
                self.assertEqual(self.capture(b), before)

    def test_last_revision_available_then_navigation_and_noops_keep_working(self):
        b = TextBuffer("a")
        b._revision = MAX_COUNTER - 1
        self.assertTrue(b.insert("b"))
        self.assertEqual(b.revision, MAX_COUNTER)
        self.assertTrue(b.home())
        self.assertTrue(b.end(select=True))
        self.assertFalse(b.insert("ab"))
        self.assertEqual((b.caret, b.anchor), (2, 2))
        self.assertFalse(b.delete())
        self.assertFalse(b.move(0))
        self.assertFalse(b.redo())
        self.assertEqual(b.revision, MAX_COUNTER)
        empty = TextBuffer("")
        empty._revision = MAX_COUNTER
        self.assertFalse(empty.undo())
        self.assertFalse(empty.redo())
        self.assertFalse(empty.insert(""))
        self.assertFalse(empty.backspace())

    def test_memory_failure_during_encoding_leaves_all_state_unchanged(self):
        b = TextBuffer("abc", limit=10)
        b.insert("d")
        b.undo()
        b.select_all()
        self.assertFalse(b.insert("x" * 11))  # Existing error must also survive.
        before = self.capture(b)
        with patch.object(module, "_utf8_size", side_effect=MemoryError("test allocation")):
            with self.assertRaises(MemoryError):
                b.insert("é")
        self.assertEqual(self.capture(b), before)

    def test_memory_failure_during_history_preparation_is_atomic(self):
        for operation in ("insert", "backspace", "delete", "undo", "redo"):
            with self.subTest(operation=operation):
                b = TextBuffer("abc", limit=10)
                b.insert("d")
                b.insert("e")
                b.undo()
                b.select_all()
                self.assertFalse(b.insert("x" * 11))
                before = self.capture(b)
                with patch.object(module, "_push", side_effect=MemoryError("test history")):
                    with self.assertRaises(MemoryError):
                        if operation == "insert":
                            b.insert("z")
                        else:
                            getattr(b, operation)()
                self.assertEqual(self.capture(b), before)
                # Failed mutation must not consume an Undo or Redo record.
                self.assertTrue(b.redo())
                self.assertEqual(b.raw, "abcde")

    def test_overflow_preflight_precedes_history_allocation(self):
        b = TextBuffer("a")
        b.insert("b")
        b._revision = MAX_COUNTER
        with patch.object(module, "_push", side_effect=AssertionError("allocated history")):
            with self.assertRaises(OverflowError):
                b.undo()
            with self.assertRaises(OverflowError):
                b.insert("c")

    def test_combined_history_payload_stays_bounded_at_maximum_text_size(self):
        b = TextBuffer("x" * MAX_RAW_TEXT_BYTES)
        for count in range(TextBuffer.HISTORY_LIMIT + 1):
            b.select_all()
            self.assertTrue(b.insert(f"{count:03d}" + "x" * (MAX_RAW_TEXT_BYTES - 3)))
        self.assertEqual(len(b._undo), TextBuffer.HISTORY_LIMIT)
        for _ in range(TextBuffer.HISTORY_LIMIT):
            self.assertTrue(b.undo())
            self.assertEqual(len(b._undo) + len(b._redo), TextBuffer.HISTORY_LIMIT)
        self.assertFalse(b.undo())
        self.assertEqual(
            sum(len(raw.encode("utf-8")) for raw, _, _ in b._undo + b._redo),
            MAX_RAW_TEXT_BYTES * TextBuffer.HISTORY_LIMIT,
        )
        for _ in range(TextBuffer.HISTORY_LIMIT):
            self.assertTrue(b.redo())
            self.assertEqual(len(b._undo) + len(b._redo), TextBuffer.HISTORY_LIMIT)
        self.assertFalse(b.redo())

    def test_noop_preserves_redo_and_existing_error_at_revision_limit(self):
        b = TextBuffer("abc", limit=4)
        b.insert("d")
        b.undo()
        b.select_all()
        self.assertFalse(b.insert("xxxxx"))
        error = b.error
        history = b._undo, b._redo
        b._revision = MAX_COUNTER
        self.assertFalse(b.insert("abc"))
        self.assertEqual((b.caret, b.anchor), (3, 3))
        self.assertEqual(b.error, error)
        self.assertEqual((b._undo, b._redo), history)
        self.assertEqual(b.revision, MAX_COUNTER)

    def test_select_flags_require_booleans_even_for_navigation_noops(self):
        b = TextBuffer("abc")
        for value in (0, 1, "yes", None, []):
            for name, args in (("place", (0,)), ("move", (0,)), ("home", ()), ("end", ())):
                with self.subTest(value=value, name=name):
                    before = self.capture(b)
                    with self.assertRaises(TypeError):
                        getattr(b, name)(*args, select=value)
                    self.assertEqual(self.capture(b), before)

    def test_scalar_subclasses_are_not_an_unbounded_execution_hook(self):
        class HostileText(str):
            def __len__(self):
                raise AssertionError("must not inspect user subclass")

        class HostileInt(int):
            def __lt__(self, other):
                raise AssertionError("must not compare user subclass")

        for raw in (HostileText("x"),):
            with self.assertRaises(TypeError):
                TextBuffer(raw)
            with self.assertRaises(TypeError):
                TextBuffer("").insert(raw)
        with self.assertRaises(TypeError):
            TextBuffer("", limit=HostileInt(1))
        with self.assertRaises(TypeError):
            TextBuffer("").place(HostileInt(1))

    def test_native_free_import_in_fresh_process(self):
        script = f"""
import importlib
import importlib.abc
import sys
import types
class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}:
            raise AssertionError('Forbidden native/core dependency: ' + fullname)
sys.meta_path.insert(0, NoNative())
package = types.ModuleType('dimension_leaf')
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules['dimension_leaf'] = package
buffer = importlib.import_module('dimension_leaf.dimension_text_buffer').TextBuffer(' 1 + ( ')
assert buffer.raw == ' 1 + ( '
assert buffer.insert('é')
assert buffer.undo()
print('native-free dimension buffer OK')
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script], capture_output=True, text=True, check=True
        )
        self.assertEqual(result.stdout.strip(), "native-free dimension buffer OK")


class RandomizedBufferTests(unittest.TestCase):
    ALPHABET = list("ab 12,+-") + [
        "é",
        "e",
        "\u0301",
        "💡",
        "👩",
        "\u200d",
        "🔬",
        "ا",
        "ב",
        "\t",
        "\n",
        "\r",
        "\x00",
        "\u202e",
        "\u2028",
        "\U000e0001",
    ]

    def test_random_edit_navigation_and_history_against_reference(self):
        # Independent timeline-based history oracle, rather than the buffer's
        # two stacks. Exercise UTF-8 budgets, malformed Unicode rejection,
        # history branching, reversed selections and exact valid Unicode.
        for seed in range(16):
            rng = random.Random(seed)
            limit = rng.randrange(0, 21)
            raw = "".join(rng.choices(self.ALPHABET, k=rng.randrange(0, 26)))
            while len(raw.encode("utf-8")) > limit:
                raw = raw[:-1]
            caret = anchor = len(raw)
            b = TextBuffer(raw, limit=limit)
            timeline = [(raw, caret, anchor)]
            cursor = 0
            revision = 0
            for step in range(1200):
                operation = rng.choice(
                    (
                        "insert",
                        "backspace",
                        "delete",
                        "move",
                        "place",
                        "home",
                        "end",
                        "select_all",
                        "undo",
                        "redo",
                    )
                )
                select = bool(rng.randrange(2))
                start, end = sorted((caret, anchor))
                before = b.snapshot()
                old_state = (raw, caret, anchor)
                expected = False
                text_changed = False
                rejected = False
                if operation in {"insert", "backspace", "delete"}:
                    text = ""
                    applicable = True
                    if operation == "insert":
                        text = "".join(
                            rng.choices(self.ALPHABET + ["\ud800", "\udfff"], k=rng.randrange(9))
                        )
                        actual = b.insert(text)
                    elif operation == "backspace":
                        actual = b.backspace()
                        if start == end:
                            applicable = start > 0
                            start -= int(applicable)
                    else:
                        actual = b.delete()
                        if start == end:
                            applicable = end < len(raw)
                            end += int(applicable)
                    if applicable:
                        candidate = raw[:start] + text + raw[end:]
                        try:
                            within_budget = len(candidate.encode("utf-8")) <= limit
                        except UnicodeEncodeError:
                            within_budget = False
                        if candidate == raw:
                            caret = anchor = start + len(text)
                        elif not within_budget:
                            rejected = True
                        else:
                            timeline[cursor] = old_state
                            timeline = timeline[: cursor + 1]
                            raw = candidate
                            caret = anchor = start + len(text)
                            timeline.append((raw, caret, anchor))
                            cursor += 1
                            if len(timeline) > TextBuffer.HISTORY_LIMIT + 1:
                                timeline.pop(0)
                                cursor -= 1
                            expected = text_changed = True
                elif operation in {"undo", "redo"}:
                    actual = getattr(b, operation)()
                    next_cursor = cursor + (-1 if operation == "undo" else 1)
                    if 0 <= next_cursor < len(timeline):
                        timeline[cursor] = old_state
                        cursor = next_cursor
                        raw, caret, anchor = timeline[cursor]
                        expected = text_changed = True
                else:
                    if operation == "move":
                        delta = rng.randrange(-8, 9)
                        actual = b.move(delta, select=select)
                        if delta:
                            if not select and start != end:
                                caret = start if delta < 0 else end
                            else:
                                caret = max(0, min(len(raw), caret + delta))
                            if not select:
                                anchor = caret
                    elif operation == "place":
                        index = rng.randrange(-5, len(raw) + 6)
                        actual = b.place(index, select=select)
                        caret = max(0, min(len(raw), index))
                        if not select:
                            anchor = caret
                    elif operation in {"home", "end"}:
                        actual = getattr(b, operation)(select=select)
                        caret = 0 if operation == "home" else len(raw)
                        if not select:
                            anchor = caret
                    else:
                        actual = b.select_all()
                        caret, anchor = len(raw), 0
                    expected = (raw, caret, anchor) != old_state
                revision += int(text_changed)
                with self.subTest(seed=seed, step=step, operation=operation):
                    self.assertIs(actual, expected)
                    self.assertEqual((b.raw, b.caret, b.anchor), (raw, caret, anchor))
                    self.assertEqual(b.revision, revision)
                    self.assertEqual(b.can_undo, cursor > 0)
                    self.assertEqual(b.can_redo, cursor < len(timeline) - 1)
                    self.assertTrue(0 <= b.caret <= len(b.raw))
                    self.assertTrue(0 <= b.anchor <= len(b.raw))
                    self.assertEqual(b.selection, tuple(sorted((caret, anchor))))
                    self.assertEqual(b.selected_text, raw[min(caret, anchor) : max(caret, anchor)])
                    self.assertEqual(len(b.display_parts()), len(raw))
                    self.assertTrue(all(b.display_parts()))
                    if rejected:
                        after = b.snapshot()
                        self.assertIsNotNone(after.pop("error"))
                        before.pop("error")
                        self.assertEqual(after, before)
                    elif text_changed:
                        self.assertIsNone(b.error)
                    self.assertLessEqual(len(b.raw.encode("utf-8")), limit)
                    self.assertLessEqual(len(b._undo) + len(b._redo), TextBuffer.HISTORY_LIMIT)

    def test_random_verbatim_roundtrip_through_edit_undo_redo(self):
        rng = random.Random(12041984)
        for case in range(200):
            original = "".join(rng.choices(self.ALPHABET, k=rng.randrange(100)))
            paste = "".join(rng.choices(self.ALPHABET, k=rng.randrange(100)))
            b = TextBuffer(original)
            first, last = sorted(
                (rng.randrange(len(original) + 1), rng.randrange(len(original) + 1))
            )
            b.place(last)
            b.place(first, select=True)
            expected = original[:first] + paste + original[last:]
            changed = b.insert(paste)
            with self.subTest(case=case):
                self.assertEqual(b.raw, expected)
                self.assertEqual(changed, expected != original)
                if changed:
                    self.assertTrue(b.undo())
                    self.assertEqual(b.raw, original)
                    self.assertEqual((b.caret, b.anchor), (first, last))
                    self.assertTrue(b.redo())
                    self.assertEqual(b.raw, expected)
                    self.assertEqual(b.caret, first + len(paste))


if __name__ == "__main__":
    unittest.main()
