"""Real sidebar and viewport functions exercised without importing Blender."""
import ast
from types import SimpleNamespace as NS

import pytest
from test_pending_length_sidebar import ROOT, draw
from test_pending_length_sidebar import owner as line_owner


def owner(*, editing=True, pending=True, native=False):
    result = line_owner(editing=editing, pending=False, native=native)
    result.draft.tool = "Circle"
    result.draft.pending_diameter = {"raw_text": " 2.5 cm "} if pending else None
    result.draft.proposal = {"kind": "circle"}
    result.draft.annotations = {}
    result.draft.point_input_phase = None
    result.proposal_capture = True
    return result


def viewport_function(name, value=None):
    tree = ast.parse((ROOT / "general_viewport.py").read_text(encoding="utf-8"))
    if name == "description":
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MCAD_OT_general_tool")
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
        node.decorator_list = []
    else:
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    environment = {"active": lambda _context: value}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "diameter-ui", "exec"), environment)
    return environment[name]


def test_active_diameter_has_only_contextual_cancel_actions_and_status():
    shown = draw(owner())
    assert "Unfinished Circle" in shown.labels
    assert shown.actions == [("Back to Circle", "CancelInput"), ("Discard Circle", "CancelProposal")]
    assert not any("2.5 cm" in label for label in shown.labels)
    assert "RELATIONS" not in shown.labels
    assert "Solver status retained" in shown.labels and "Profile status retained" in shown.labels


def test_suspended_diameter_shows_exact_raw_and_reopen():
    shown = draw(owner(editing=False))
    assert "Diameter: ' 2.5 cm '" in shown.labels
    assert shown.actions == [("Reopen Diameter", "Reopen"), ("Cancel Diameter", "CancelInput"), ("Discard Circle", "CancelProposal")]
    assert "RELATIONS" not in shown.labels


def test_pending_native_check_keeps_status_errors_and_only_applicable_cancel():
    value = owner(native=True)
    value.error = "Native solve refused this center"
    value.retained_outline = object()
    value.annotation_notice = "Annotation unavailable"
    shown = draw(value)
    assert shown.actions == [("Back to Circle", "CancelInput")]
    for label in (value.error, value.annotation_notice, "Solver status retained", "Profile status retained", "Stale outline · last good sketch"):
        assert label in shown.labels


@pytest.mark.parametrize("tool,phrase", [("CancelInput", "keep the unfinished Circle"), ("CancelProposal", "accepted geometry is unchanged"), ("Reopen", "captured center")])
def test_tooltips_explain_cancel_scope_and_retained_center(tool, phrase):
    assert phrase in viewport_function("description", owner())(NS(bl_description="original"), None, NS(tool=tool))


@pytest.mark.parametrize("editing", [True, False])
def test_pending_hint_distinguishes_active_and_suspended(editing):
    hint = viewport_function("_line_hint")(owner(editing=editing))
    assert ("Enter creates" in hint) is editing
    assert ("Reopen Diameter" in hint) is not editing


def test_diameter_hint_only_after_center_chosen_and_capture_active():
    value = owner(pending=False)
    hint = viewport_function("_line_hint")
    value.draft.proposal = None
    assert hint(value) is None
    value.draft.proposal = {"kind": "circle"}
    assert hint(value) == "Tab: driving diameter · Click: free circle"
    value.proposal_capture = False
    assert hint(value) is None


def test_field_title_truthfully_distinguishes_diameter_entry_from_radius_edit():
    title = viewport_function("_field_title")
    value = owner()
    assert title(value) == "Driving diameter"
    value.draft.pending_diameter = None
    value.commands.pending_edit = NS(constraint_id="radius")
    value.draft.annotations = {"radius": {"kind": "radius", "display": "diameter"}}
    assert title(value) == "Driving radius · diameter / 2"
    value.draft.annotations["radius"]["display"] = "radius"
    assert title(value) == "Raw dimension input"
    value.draft.annotations.clear()
    assert title(value) == "Raw dimension input"
    value.commands.pending_edit = None
    assert title(value) == "Raw dimension input"
    value.draft.pending_length = {"axis": "horizontal"}
    assert title(value) == "Driving length · Horizontal"
