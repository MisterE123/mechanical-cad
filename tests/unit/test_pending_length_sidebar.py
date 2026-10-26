"""Focused real draw-function checks without importing Blender."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"


class Layout:
    def __init__(self):
        self.labels = []
        self.actions = []

    def row(self, **_kwargs):
        return self

    def label(self, *, text, **_kwargs):
        self.labels.append(text)

    def operator(self, *_args, **_kwargs):
        return NS()


def load_draw():
    tree = ast.parse((ROOT / "workspace_ui.py").read_text())
    names = {"_draw_pending_length_status", "_draw_pending_diameter_status", "_draw_general_status"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    environment = {
        "_panel_wrap": lambda _context, text: [text],
        "_status_tool": lambda layout, _context, label, tool, *_args: layout.actions.append((label, tool)),
        "_diagnostic_button": lambda layout, error: layout.labels.append("diagnostic: " + error),
        "compact_status": NS(
            sketch_label=lambda *_args, **_kwargs: ("Solver status retained", "INFO"),
            profile_label=lambda *_args, **_kwargs: ("Profile status retained", "INFO"),
            summary=lambda text, *_args: text,
            disclosure=lambda *_args: False,
        ),
        "constraint_ui": NS(draw_inspector=lambda layout, *_args: layout.labels.append("RELATIONS")),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "sidebar", "exec"), environment)
    return environment["_draw_general_status"]


def owner(*, editing=True, pending=True, native=False):
    return NS(
        draft=NS(tool="Line", pending_diameter=None, pending_length={"axis": "horizontal", "raw_text": " 2 cm "} if pending else None,
                 proposal={"kind": "line"},),
        input_controller=NS(closed=not editing),
        commands=NS(pending_edit=None),
        current_solution_response=lambda: None, current_build_failure=None, current_diagnostics=None,
        pending=object() if native else None, error="", retained_outline=None, annotation_notice="",
        can_use_tool=lambda tool: not (native and tool == "CancelProposal"),
    )


def draw(value):
    layout = Layout()
    load_draw()(layout, NS(scene=NS(mechanical_cad=NS())), value)
    return layout


def test_active_field_omits_duplicate_values_disabled_controls_and_inspector():
    shown = draw(owner())
    assert "Unfinished Line" in shown.labels
    assert shown.actions == [("Back to Line", "CancelInput"), ("Discard Line", "CancelProposal")]
    assert not any("2 cm" in text or "Horizontal" in text for text in shown.labels)
    assert "RELATIONS" not in shown.labels
    assert "Solver status retained" in shown.labels and "Profile status retained" in shown.labels


def test_suspended_field_preserves_exact_raw_and_captured_axis():
    shown = draw(owner(editing=False))
    assert "Length: ' 2 cm '" in shown.labels and "Horizontal retained" in shown.labels
    assert shown.actions == [("Reopen Length", "Reopen"), ("Cancel Length", "CancelInput"),
                             ("Discard Line", "CancelProposal")]
    assert "RELATIONS" not in shown.labels


def test_native_work_shows_only_applicable_cancel_action():
    shown = draw(owner(native=True))
    assert shown.actions == [("Back to Line", "CancelInput")]
    assert "Solver status retained" in shown.labels


def test_real_error_stale_outline_and_annotation_notice_remain_visible():
    value = owner()
    value.error = "Native solve refused this placement"
    value.retained_outline = object()
    value.annotation_notice = "Annotation unavailable"
    shown = draw(value)
    assert value.error in shown.labels and value.annotation_notice in shown.labels
    assert "Stale outline · last good sketch" in shown.labels


def test_ordinary_proposal_and_relations_are_unchanged():
    shown = draw(owner(pending=False))
    assert shown.actions == [("Continue", "Continue"), ("Cancel Proposal", "CancelProposal")]
    assert "RELATIONS" in shown.labels


@pytest.mark.parametrize("tool,phrase", [
    ("CancelInput", "keep the unfinished Line"),
    ("CancelProposal", "accepted geometry is unchanged"),
    ("Reopen", "captured direction"),
])
def test_specific_tooltips_explain_cancel_scope(tool, phrase):
    tree = ast.parse((ROOT / "general_viewport.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MCAD_OT_general_tool")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "description")
    method.decorator_list = []
    environment = {"active": lambda _context: owner()}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "tooltip", "exec"), environment)
    assert phrase in environment["description"](NS(bl_description="original"), None, NS(tool=tool))


@pytest.mark.parametrize("editing", [True, False])
def test_viewport_hint_matches_active_or_suspended_field(editing):
    tree = ast.parse((ROOT / "general_viewport.py").read_text())
    method = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_line_hint")
    environment = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "hint", "exec"), environment)
    hint = environment["_line_hint"](owner(editing=editing))
    assert ("Enter creates" in hint) is editing
    assert ("Reopen Length" in hint) is not editing
