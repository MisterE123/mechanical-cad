"""Native-free support panel checks; GUI popup/modal behavior needs Blender QA."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def ui(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    name = "mcad_support_disclosure_test"
    package = ModuleType(name)
    package.__path__ = [str(root / "blender_addon/mechanical_cad_blender")]
    monkeypatch.setitem(sys.modules, name, package)
    for dependency in (
        "document_state", "execution_lease", "workspace", "common", "operators",
        "support_intent_edit", "topology_labels",
    ):
        monkeypatch.setitem(sys.modules, name + "." + dependency, Mock())
    monkeypatch.setitem(sys.modules, "bpy.props", Mock())
    monkeypatch.setitem(sys.modules, "bpy.types", SimpleNamespace(Operator=object))
    spec = importlib.util.spec_from_file_location(
        name + ".support_intent_ui", package.__path__[0] + "/support_intent_ui.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The extracted pure formatter owns the same mocked support decision.
    formatter = sys.modules[name + ".support_presentation"]
    monkeypatch.setattr(formatter, "support_decision", module.support_decision)
    module.workspace.active_draft.return_value = None
    module._selected = Mock(return_value={"id": "attached", "support_intent": {"orientation": {}}})
    return module


class Layout:
    def __init__(self):
        self.labels = []
        self.buttons = []

    def box(self):
        return self

    def row(self, **kwargs):
        return self

    def label(self, **kwargs):
        self.labels.append(kwargs)

    def operator(self, name, **kwargs):
        button = SimpleNamespace(identifier=name, **kwargs)
        self.buttons.append(button)
        return button


def draw(ui):
    layout = Layout()
    context = SimpleNamespace(
        region=SimpleNamespace(width=240),
        preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=1)),
    )
    ui.draw_support_intent(layout, context)
    # Drawing never launches a replay or edits canonical data.
    ui.document_state._run_sidecar.assert_not_called()
    ui.document_state._commit_candidate.assert_not_called()
    return layout


@pytest.mark.parametrize("status,expected", [
    ("assumed", "ASSUMPTION ACTIVE"),
    ("exact", "Support: exact face"),
    ("unknown", "Support unverified"),
])
def test_draft_is_compact_and_complete_reason_remains_available(ui, status, expected):
    notice = "Preserve logical plane; Minimal twist; no fragment selected."
    reason = "Long specific provenance decision. " * 30
    ui.workspace.active_draft.return_value = SimpleNamespace(
        support_notice=notice, support_decision={"status": status, "reason": reason},
    )
    layout = draw(ui)
    assert [label["text"] for label in layout.labels] == [expected]
    assert len(layout.buttons) == 1
    why = layout.buttons[0]
    assert why.identifier == "mcad.help"
    assert why.topic == "sketch.support_intent"
    assert why.detail == notice + "\n" + reason
    ui.document_state.current_part_result.assert_not_called()
    ui.support_decision.assert_not_called()


@pytest.mark.parametrize("status,expected", [
    ("assumed", "ASSUMPTION ACTIVE"), ("exact", "Support: exact face"),
])
def test_history_keeps_status_review_and_full_details(ui, status, expected):
    reason = "Actual support reason " * 50
    ui.support_decision.return_value = {"status": status, "reason": reason}
    layout = draw(ui)
    assert [label["text"] for label in layout.labels] == [expected]
    review, why = layout.buttons
    assert review.identifier == "mcad.edit_sketch_support"
    assert review.feature_id == "attached"
    assert why.text == "Why?"
    assert reason in why.detail
    assert "Preserve logical plane" in why.detail and "Minimal twist" in why.detail


def test_unverified_does_not_claim_exact_or_consult_support(ui):
    ui.document_state.current_part_result.return_value = None
    layout = draw(ui)
    assert layout.labels[0]["text"] == "Support unverified"
    assert "current ancestry" in layout.buttons[-1].detail
    ui.support_decision.assert_not_called()


def test_failure_has_bounded_readable_excerpt_and_complete_detail(ui):
    error = "Support ancestry is missing; cannot preserve the saved plane. " * 30
    ui.support_decision.side_effect = ValueError(error)
    layout = draw(ui)
    assert layout.labels[0] == {"text": "Support needs review", "icon": "ERROR"}
    assert 1 < len(layout.labels) <= 5
    assert all(len(label["text"]) <= 26 for label in layout.labels[1:])
    assert "..." in layout.labels[-1]["text"]
    assert error in layout.buttons[-1].detail
    assert layout.buttons[0].feature_id == "attached"


def test_unattached_draft_has_no_support_panel(ui):
    ui.workspace.active_draft.return_value = SimpleNamespace(support_notice="")
    layout = draw(ui)
    assert not layout.labels and not layout.buttons
