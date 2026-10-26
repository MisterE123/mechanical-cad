"""Saved-sketch next-step UI, using existing replay and operation policy."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_arc_ui_availability import Layout, context, labels
from test_arc_ui_availability import ui as ui
from test_compact_status import status


@pytest.mark.parametrize("feature,ready,message", [
    ({"status": "ok", "output": {"kind": "profile"}}, True, "Closed profile"),
    ({"status": "ok", "output": {"kind": "sketch", "profile": {"state": "available"}}}, True, "Closed profile"),
    ({"status": "ok", "output": {"kind": "sketch", "profile": {"state": "unavailable", "reason": {"message": "Close this line chain before extrusion."}}}}, False, "Close this line chain"),
    ({"status": "ok", "output": {"kind": "sketch", "profile": {"state": "unavailable", "reason": {"message": "Ambiguous region"}}}}, False, "Ambiguous region"),
    ({"status": "failed", "output": {"kind": "profile"}}, False, "needs repair"),
    ({"status": "ok", "sketch": {"status": "okay", "remaining_dof": 0}}, False, "Profile unavailable"),
])
def test_profile_readiness_is_not_solve_success(feature, ready, message):
    result = status.saved_profile_state(feature)
    assert result[0] is ready and message in result[1]


@pytest.mark.parametrize("ready,current,reason,enabled,text", [
    (True, True, "", True, "Closed profile available"),
    (False, True, "", False, "Close this line chain"),
    (True, False, "", False, "Rebuild to check"),
    (True, True, "Unsupported region", False, "Unsupported region"),
])
def test_next_step_uses_selected_profile_and_current_evidence(ui, monkeypatch, ready, current, reason, enabled, text):
    ctx = context(ui)
    state = ctx.scene.mechanical_cad
    state.feature_index = 0
    feature = state.features[0]
    detail = SimpleNamespace(profile_state=(ready, "Closed profile available" if ready else "Close this line chain", "INFO"))
    presentation = SimpleNamespace(selected_detail=Mock(return_value=detail if current else None))
    policy = Mock(return_value=reason)
    monkeypatch.setattr(ui.operators, "feature_action_reason", policy)
    monkeypatch.setattr(ui.workspace_ui, "available", lambda *_: True)
    layout = Layout()
    before = state.document_json
    ui.workspace_ui._draw_selected_sketch_extrude(layout, ctx, presentation)
    buttons = [value for kind, value in layout.entries if kind == "operator"]
    assert len(buttons) == 1
    button = buttons[0]
    assert button.name == "mcad.add_extrude" and button.enabled is enabled
    if not reason:
        assert button.profile == feature.feature_id
    assert text in labels(layout)
    policy.assert_called_once_with(ctx, "extrude", profile=feature.feature_id)
    presentation.selected_detail.assert_called_once_with(ctx, feature.feature_id)
    assert state.document_json == before


def test_solid_selection_does_not_offer_sketch_action(ui):
    ctx = context(ui)
    ctx.scene.mechanical_cad.feature_index = 1
    layout = Layout()
    ui.workspace_ui._draw_selected_sketch_extrude(layout, ctx, None)
    assert not layout.entries


@pytest.mark.parametrize("explicit,eligible,expected", [(False, True, "selected"), (False, False, "original"), (True, True, "original")])
def test_invoke_prefill_preserves_explicit_and_excludes_unsupported(ui, monkeypatch, explicit, eligible, expected):
    ctx = context(ui)
    state = ctx.scene.mechanical_cad
    state.feature_index = 0
    state.features[0].feature_id = "selected"
    ctx.window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})
    op = ui.operators.MCAD_OT_extrude()
    op.profile, op.length, op.length_input = "original", 10, "10"
    op.end_condition = "BLIND"
    op.enter_part_after_apply = True  # A remembered value must not opt in.
    op.properties = SimpleNamespace(is_property_set=lambda name, **kwargs: name == "length_input" or (name == "profile" and (explicit or kwargs.get("ghost", True))))
    monkeypatch.setattr(ui.operators, "_profile_choices", lambda *_: [("selected", "Selected", "")] if eligible else [])
    monkeypatch.setattr(ui.operators, "feature_action_reason", lambda *a, **kw: "")
    monkeypatch.setattr(ui.operators.extrusion_preview, "start", lambda *a: None)
    assert op.invoke(ctx, None) == {"RUNNING_MODAL"}
    assert op.profile == expected
    assert op.enter_part_after_apply is False


@pytest.mark.parametrize("role,expected", [("SKETCH", True), ("PART", False)])
def test_shortcut_opts_into_part_only_in_sketch(ui, monkeypatch, role, expected):
    ctx = context(ui)
    ctx.scene.mechanical_cad.feature_index = 0
    monkeypatch.setattr(ui.workspace, "get_role", lambda _: role)
    monkeypatch.setattr(ui.operators, "feature_action_reason", lambda *a, **k: "")
    monkeypatch.setattr(ui.workspace_ui, "available", lambda *_: True)
    presentation = SimpleNamespace(selected_detail=lambda *a: SimpleNamespace(profile_state=(True, "Ready", "INFO")))
    layout = Layout()
    ui.workspace_ui._draw_selected_sketch_extrude(layout, ctx, presentation)
    button = next(value for kind, value in layout.entries if kind == "operator")
    assert button.enter_part_after_apply is expected


@pytest.mark.parametrize("enabled,role,changed", [(False, "SKETCH", False), (True, "PART", False), (True, "SKETCH", True), (True, "SKETCH", False)])
def test_handoff_is_opt_in_and_origin_bound(ui, monkeypatch, enabled, role, changed):
    ctx = context(ui)
    op = ui.operators.MCAD_OT_extrude()
    op.enter_part_after_apply = enabled
    op._shortcut_origin = (ctx.window, object() if changed else ctx.workspace, ctx.scene)
    monkeypatch.setattr(ui.workspace, "get_role", lambda _: role)
    request = Mock()
    monkeypatch.setattr(ui.workspace, "request_workspace", request)
    op._open_part_after_apply(ctx)
    assert request.call_count == int(enabled and role == "SKETCH" and not changed)


@pytest.mark.parametrize("success", [True, False])
def test_sync_handoff_requires_success_not_finished_status(ui, monkeypatch, success):
    ctx = context(ui)
    op = ui.operators.MCAD_OT_extrude()
    op.preview_candidate = lambda _: {}
    op._open_part_after_apply = Mock()
    monkeypatch.setattr(ui.operators.extrusion_preview, "apply", lambda *a: None)
    monkeypatch.setattr(ui.operators, "_commit_candidate", lambda *a: success)
    monkeypatch.setattr(ui.operators, "_report_result", lambda *a: {"FINISHED"})
    assert op.execute(ctx) == {"FINISHED"}
    assert op._open_part_after_apply.call_count == int(success)


@pytest.mark.parametrize("result,accepted", [({"RUNNING_MODAL"}, False), ({"CANCELLED"}, False), ({"FINISHED"}, False), ({"FINISHED"}, True)])
def test_modal_handoff_requires_accepted_publication(ui, monkeypatch, result, accepted):
    ctx = context(ui)
    op = ui.operators.MCAD_OT_extrude()
    op._extrusion_preview = SimpleNamespace(accepted=accepted)
    op._open_part_after_apply = Mock()
    monkeypatch.setattr(ui.operators.extrusion_preview, "modal", lambda *a: result)
    assert op.modal(ctx, None) == result
    assert op._open_part_after_apply.call_count == int(result == {"FINISHED"} and accepted)


def test_navigation_failure_reports_applied_geometry(ui, monkeypatch):
    ctx = context(ui)
    op = ui.operators.MCAD_OT_extrude()
    op.enter_part_after_apply = True
    op.report = Mock()
    monkeypatch.setattr(ui.workspace, "get_role", lambda _: "SKETCH")
    monkeypatch.setattr(ui.workspace, "request_workspace", Mock(side_effect=RuntimeError("Unavailable")))
    op._open_part_after_apply(ctx)
    assert op.report.call_args.args == ({"WARNING"}, "Extrusion applied; open Part to continue: Unavailable")


class FocusLayout(Layout):
    def row(self, **kwargs):
        return FocusLayout(self.entries, self.icons)

    def prop(self, instance, name, **kwargs):
        self.entries.append(("focus_prop", (name, getattr(self, "activate_init", False), kwargs.get("text"))))


def focus_operator(ui, monkeypatch, *, explicit_navigation, explicit_profile, navigation_value, end):
    ctx = context(ui)
    ctx.window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})
    op = ui.operators.MCAD_OT_extrude()
    op.profile, op.length, op.length_input = "original", 10, "height + clearance"
    op.enter_part_after_apply, op.end_condition = navigation_value, end
    op.target, op.end_face, op.direction, op.offset = "base", "face:top", "NORMAL", "gap"
    checks = []

    def is_set(name, **kwargs):
        checks.append((name, kwargs))
        if name == "enter_part_after_apply":
            return explicit_navigation if kwargs.get("ghost") is False else True
        if name == "profile":
            return explicit_profile if kwargs.get("ghost") is False else True
        return name == "length_input"

    op.properties = SimpleNamespace(is_property_set=is_set)
    monkeypatch.setattr(ui.operators, "_profile_choices", lambda *_: [])
    monkeypatch.setattr(ui.operators, "feature_action_reason", lambda *a, **kw: "")
    monkeypatch.setattr(ui.operators.extrusion_preview, "start", lambda *a: None)
    monkeypatch.setattr(ui.operators.extrusion_preview, "draw", lambda *a: None)
    monkeypatch.setattr(ui.operators, "_draw_feature_help", lambda *a: None)
    assert op.invoke(ctx, None) == {"RUNNING_MODAL"}
    return op, ctx, checks


@pytest.mark.parametrize(("explicit_navigation", "explicit_profile", "navigation_value", "shortcut"), [
    (True, True, True, True),
    (True, True, False, True),  # Part shortcut explicitly opts out of navigation.
    (False, True, True, False),  # Remembered navigation is not explicit intent.
    (True, False, True, False),  # An implicit/remembered profile is not a shortcut.
    (False, False, False, False),
])
@pytest.mark.parametrize("end", ["BLIND", "SYMMETRIC", "UP_TO_FACE"])
def test_initial_depth_focus_is_explicit_visible_and_one_shot(
    ui, monkeypatch, explicit_navigation, explicit_profile, navigation_value, shortcut, end,
):
    op, ctx, checks = focus_operator(
        ui, monkeypatch, explicit_navigation=explicit_navigation,
        explicit_profile=explicit_profile, navigation_value=navigation_value, end=end,
    )
    expected = shortcut and end != "UP_TO_FACE"
    assert op._initial_depth_focus is expected
    assert ("enter_part_after_apply", {"ghost": False}) in checks
    if explicit_navigation:
        assert ("profile", {"ghost": False}) in checks
    before = {name: getattr(op, name) for name in (
        "profile", "length", "length_input", "end_condition", "enter_part_after_apply",
        "target", "end_face", "direction", "offset",
    )}
    canonical = ctx.scene.mechanical_cad.document_json
    for first in (True, False):
        op.layout = FocusLayout()
        op.draw(ctx)
        controls = [value for kind, value in op.layout.entries if kind == "focus_prop"]
        focused = [name for name, active, label in controls if active]
        assert focused == (["length_input"] if first and expected else [])
        assert not op._initial_depth_focus
        if end == "UP_TO_FACE":
            assert "length_input" not in [name for name, active, label in controls]
            assert {"target", "end_face", "direction", "offset"}.issubset({name for name, active, label in controls})
        else:
            assert next(label for name, active, label in controls if name == "length_input") == (
                "Total depth (mm)" if end == "SYMMETRIC" else "Signed depth (mm)"
            )
        assert {name: getattr(op, name) for name in before} == before
        assert ctx.scene.mechanical_cad.document_json == canonical


def test_hiding_depth_before_first_draw_consumes_focus_without_later_steal(ui, monkeypatch):
    op, ctx, _ = focus_operator(
        ui, monkeypatch, explicit_navigation=True, explicit_profile=True,
        navigation_value=False, end="BLIND",
    )
    assert op._initial_depth_focus
    for end in ("UP_TO_FACE", "BLIND", "SYMMETRIC"):
        op.end_condition = end
        op.layout = FocusLayout()
        op.draw(ctx)
        assert not op._initial_depth_focus
        assert not any(active for kind, value in op.layout.entries if kind == "focus_prop" for _, active, _ in [value])
    assert op.length_input == "height + clearance"
