"""Actual reporting owner with synthetic guarded evidence; no native GUI claim."""

import copy
from types import SimpleNamespace

import pytest
from test_geometry3_owner import host as host  # noqa: F401
from test_geometry3_owner import run


@pytest.fixture
def reports(host, monkeypatch):
    messages, popups = [], []
    monkeypatch.setattr(host.geometry.bpy, "app", SimpleNamespace(background=False), raising=False)
    monkeypatch.setattr(
        host.geometry.bpy, "ops",
        SimpleNamespace(mcad=SimpleNamespace(help=lambda *args, **kw: popups.append((args, kw)))),
        raising=False,
    )
    operator = SimpleNamespace(report=lambda level, text: messages.append((level, text)))
    return operator, messages, popups


@pytest.mark.parametrize("action,confirmation", [
    ("check_geometry", "Geometry checks passed"),
    ("export_step", "STEP exported"),
    ("export_stl", "STL exported; import in millimetres"),
])
def test_current_success_is_brief_without_popup_and_preserves_report(host, reports, action, confirmation):
    assert run(host, action)
    state = host.context.scene.mechanical_cad
    before = copy.deepcopy(vars(state))
    operator, messages, popups = reports
    assert host.geometry._show_report(operator, host.context, True, action=action) == {"FINISHED"}
    assert messages == [({"INFO"}, confirmation + ". See Part details.")]
    assert not popups
    assert vars(state) == before
    if action == "export_stl":
        assert "STL has no stored units" in state.geometry_message


@pytest.mark.parametrize("success,status,geometry_status,current", [
    (False, "FAILED", "FAILED", False),
    (False, "FAILED", "UNKNOWN", False),
    (False, "DIRTY", "OUTDATED", False),
    (True, "READY", "PASSED", False),  # Saved labels are not live evidence.
    (True, "READY", "UNKNOWN", True),
    (True, "READY", "OUTDATED", True),
    (False, "READY", "PASSED", True),
    (True, "DIRTY", "PASSED", True),
])
def test_warning_or_uncertain_state_keeps_full_popup(host, reports, success, status, geometry_status, current):
    assert run(host)
    state = host.context.scene.mechanical_cad
    state.status, state.geometry_status = status, geometry_status
    if not current:
        host.doc._GEOMETRY_RUNTIME.clear()
    state.geometry_message = "Important warning\n" + "diagnostic " * 150
    before = copy.deepcopy(vars(state))
    operator, messages, popups = reports
    assert host.geometry._show_report(operator, host.context, success) == {"FINISHED"}
    assert messages == [({"WARNING"}, state.geometry_message[:1000])]
    assert popups == [(("INVOKE_DEFAULT",), {"topic": "geometry.actions", "detail": state.geometry_message})]
    assert vars(state) == before


def test_confirmed_historical_write_keeps_warning_and_receipt(host, reports):
    # Native-free owner fixture confirms the write, then rejects publication.
    host.after_wait = lambda: setattr(host.context.scene.mechanical_cad, "document_json", "{}")
    assert not run(host, "export_step")
    state = host.context.scene.mechanical_cad
    assert state.geometry_status == "OUTDATED" and "written:" in state.geometry_message
    before = copy.deepcopy(vars(state))
    operator, messages, popups = reports
    assert host.geometry._show_report(operator, host.context, False, action="export_step") == {"FINISHED"}
    assert messages[0][0] == {"WARNING"} and len(popups) == 1
    assert popups[0][1]["detail"] == state.geometry_message
    assert vars(state) == before


@pytest.mark.parametrize("background,window", [(True, True), (False, False)])
@pytest.mark.parametrize("success", [True, False])
def test_without_popup_context_preserves_reporting(host, reports, background, window, success):
    assert run(host)
    host.geometry.bpy.app.background = background
    if not window:
        host.context.window = None
    operator, messages, popups = reports
    assert host.geometry._show_report(operator, host.context, success) == {"FINISHED"}
    assert len(messages) == 1 and not popups


def test_missing_popup_context_does_not_change_outcome(host, reports):
    assert run(host)
    operator, messages, _ = reports

    def unavailable(*args, **kwargs):
        raise RuntimeError("No popup context")

    host.geometry.bpy.ops.mcad.help = unavailable
    assert host.geometry._show_report(operator, host.context, False) == {"FINISHED"}
    assert messages[0][0] == {"WARNING"}


@pytest.mark.parametrize("error", [ReferenceError, OSError, KeyError])
def test_unavailable_live_verification_keeps_complete_report(host, reports, monkeypatch, error):
    assert run(host, "export_step")
    state = host.context.scene.mechanical_cad
    before = copy.deepcopy(vars(state))

    def unavailable(_context):
        raise error("Current verification is unavailable")

    monkeypatch.setattr(host.doc, "geometry_report_is_current", unavailable)
    operator, messages, popups = reports
    assert host.geometry._show_report(operator, host.context, True, action="export_step") == {"FINISHED"}
    assert messages[0][0] == {"WARNING"}
    assert "STEP written:" in messages[0][1]
    assert popups[0][1]["detail"] == state.geometry_message
    assert vars(state) == before


@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_operator_routes_its_action_to_confirmation_without_changing_execution(host, reports, monkeypatch, action):
    assert run(host, action)
    operator, messages, popups = reports
    calls = []

    def execute(context, selected_action, *, destination):
        calls.append((context, selected_action, destination))
        return True

    monkeypatch.setattr(host.geometry, "run_geometry_action", execute)
    destination = None if action == "check_geometry" else host.destination
    result = host.geometry._GeometryActionOperator._execute_action(
        operator, host.context, action, destination=destination
    )
    assert result == {"FINISHED"} and calls == [(host.context, action, destination)]
    expected = {"check_geometry": "Geometry checks passed", "export_step": "STEP exported", "export_stl": "STL exported"}
    assert messages[0][1].startswith(expected[action]) and not popups
