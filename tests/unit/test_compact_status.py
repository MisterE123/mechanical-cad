"""Read-only status policy and actual draw-port tests; no native GUI claim."""

import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_arc_ui_availability import Layout, context, labels, ports
from test_arc_ui_availability import ui as ui

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "compact_status_test", ROOT / "blender_addon/mechanical_cad_blender/compact_status.py"
)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


@pytest.mark.parametrize("native,dof,text", [
    ("okay", 0, "Fully defined"),
    ("okay", 4, "Underdefined · 4 DoF"),
    ("redundant_okay", 0, "Fully defined · 0 DoF · redundant"),
    ("inconsistent", 0, "Conflicting constraints"),
    ("didnt_converge", 0, "Solve failed · did not converge"),
    ("too_many_unknowns", 0, "Solve failed · too many unknowns"),
    ("unknown", 0, "Solve unverified"),
    ("okay", None, "Solve unverified"),
    ("okay", True, "Solve unverified"),
])
def test_only_current_success_can_be_fully_defined(native, dof, text):
    report = {"status": native, "remaining_dof": dof}
    before = copy.deepcopy(report)
    assert status.sketch_label(report)[0].startswith(text)
    assert "defined" not in status.sketch_label(report, current=False)[0]
    assert status.sketch_label(report, pending=True)[0] == "Check pending"
    assert report == before


def test_profile_and_geometry_are_not_solver_or_build_success():
    assert status.profile_label(None)[0] == "Profile: unchecked"
    assert status.profile_label({"ready": False})[1] == "ERROR"
    assert status.profile_label({"ready": True})[0] == "Closed profile available"
    assert status.profile_label({"ready": True}, pending=True)[0] == "Profile: unchecked"
    assert "stale" in status.geometry_label("PASSED", current=False)[0]
    assert status.geometry_label("UNCHECKED", current=True)[0] == "Geometry check: not run"
    assert status.geometry_label("FAILED", current=True)[1] == "ERROR"


def test_disclosure_is_default_closed_and_never_mutates_state():
    state = SimpleNamespace()
    layout = Layout()
    assert not status.disclosure(layout, state, "show_sketch_details", "Details")
    assert vars(state) == {}
    state.show_sketch_details = True
    assert status.disclosure(layout, state, "show_sketch_details", "Details")
    assert vars(state) == {"show_sketch_details": True}


def draft(*, pending=None, response=None, error="", diagnostics=None):
    return SimpleNamespace(
        draft=SimpleNamespace(tool="Select", proposal=None, pending_length=None,
                              pending_diameter=None, retired_annotation_ids=()), selection_mode="entity",
        pending=pending, current_solution_response=lambda: response,
        current_build_failure=None, current_diagnostics=diagnostics,
        retained_outline=None, commands=SimpleNamespace(pending_edit=None),
        error=error, annotation_notice="", message="Long successful explanation",
        current_native_build_status="not_checked",
    )


def draw_status(ui, monkeypatch, owner, *, expanded=False):
    ctx = context(ui)
    ctx.scene.mechanical_cad.show_sketch_details = expanded
    monkeypatch.setattr(ui.workspace_ui.constraint_ui, "draw_inspector", ports.noop)
    layout = Layout()
    ui.workspace_ui._draw_general_status(layout, ctx, owner)
    return labels(layout)


def test_real_draw_defaults_to_solver_profile_without_success_paragraph(ui, monkeypatch):
    owner = draft(response={"result": {
        "sketch": {"status": "okay", "remaining_dof": 0},
        "profile_check": {"ready": False, "error": {"message": "Boundary diagnostic"}},
    }})
    text = draw_status(ui, monkeypatch, owner)
    assert "Fully defined" in text and "Profile unavailable" in text
    assert "Boundary diagnostic" not in text and "Long successful explanation" not in text
    expanded = draw_status(ui, monkeypatch, owner, expanded=True)
    assert "Boundary diagnostic" in expanded and "Long successful explanation" in expanded


def test_real_draw_pending_never_promotes_old_zero_dof(ui, monkeypatch):
    owner = draft(pending=object(), response={"result": {
        "sketch": {"status": "okay", "remaining_dof": 0},
        "profile_check": {"ready": True},
    }})
    text = draw_status(ui, monkeypatch, owner)
    assert "Check pending" in text and "Fully defined" not in text
    assert "Closed profile available" not in text


def test_real_draw_preserves_failure_and_stale_warning(ui, monkeypatch):
    owner = draft(error="Correct width then Check again", diagnostics=SimpleNamespace(
        solver_status="didnt_converge",
    ))
    owner.retained_outline = object()
    text = draw_status(ui, monkeypatch, owner)
    assert "did not converge" in text and "overdefined" not in text
    assert "Correct width then Check again" in text and "Stale outline" in text


def test_build_failure_is_visible_without_claiming_trial_solve_is_current(ui, monkeypatch):
    owner = draft()
    owner.current_build_failure = SimpleNamespace(
        remaining_dof=0, solver_status="okay", profile_ready=True,
        failed_features=[("pad", "invalid_shape", "Repair the profile and Check again")],
    )
    text = draw_status(ui, monkeypatch, owner)
    assert "Build failed" in text and "pad: Repair the profile" in text
    assert "Fully defined" not in text and "Closed profile available" not in text
    expanded = draw_status(ui, monkeypatch, owner, expanded=True)
    assert "invalid_shape" in expanded and "Trial solve: 0 DoF" in expanded


def current_presentation_fixture(ui, monkeypatch, ctx, result):
    """Supply detached projection evidence to the real presentation capture path."""
    scene = ctx.scene
    state = scene.mechanical_cad
    document_json = state.document_json
    response = {"result": copy.deepcopy(result)}

    def projection(context, _records, *, with_current_check=False):
        def current():
            return (
                context.scene is scene and scene.mechanical_cad is state
                and state.document_json == document_json and state.status == "READY"
            )

        if not current():
            return None
        return (None, response, current) if with_current_check else (None, response)

    monkeypatch.setattr(ui.document_state, "_runtime_projection", projection)


def test_committed_history_defaults_to_compact_status_without_diagnostic_ids(ui, monkeypatch):
    import sys

    ctx = context(ui)
    state = ctx.scene.mechanical_cad
    state.status = "READY"
    state.feature_index = 0
    # The host document starts empty; one detached history row is enough here.
    state.features = [SimpleNamespace(
        label="Sketch", feature_id="sketch", kind="sketch_constrained", sketch_report_json="retained report",
    )]
    report = {"status": "redundant_okay", "remaining_dof": 0,
              "failed_constraints": ["private_diagnostic_id"]}
    before = copy.deepcopy(report)
    current_presentation_fixture(ui, monkeypatch, ctx, {
        "features": [{"id": "sketch", "status": "ok", "sketch": report}],
    })
    monkeypatch.setattr(ui.workspace, "get_role", lambda _ctx: "SKETCH")
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _ctx: False)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace, "_LAST_ERROR", "", raising=False)
    monkeypatch.setattr(ui.workspace_ui, "_action_button", ports.noop)
    monkeypatch.setitem(sys.modules, ports.PACKAGE + ".support_intent_ui", SimpleNamespace(
        draw_support_intent=ports.noop,
    ))
    layout = Layout()
    ui.workspace_ui.MCAD_PT_workspace_history.draw(SimpleNamespace(layout=layout), ctx)
    text = labels(layout)
    assert "Fully defined" in text and "redundant" in text
    assert "private_diagnostic_id" not in text
    assert report == before


@pytest.mark.parametrize("header,palette", [(True, True), (False, True), (True, False), (False, False)])
def test_named_completion_fallback_does_not_depend_on_header_or_palette(ui, monkeypatch, header, palette):
    ctx = context(ui)
    ctx.space_data = SimpleNamespace(show_region_header=header, show_gizmo=palette)
    ctx.screen = SimpleNamespace(show_fullscreen=True)
    monkeypatch.setattr(ui.workspace_ui, "_draft_actions", lambda _ctx: ("FINISH", "CANCEL"))
    buttons = []
    monkeypatch.setattr(ui.workspace_ui, "_action_button", lambda layout, _ctx, action, **kwargs:
                        buttons.append((layout, action, kwargs.get("text"))))
    ui.workspace_ui._draw_draft_completion(Layout(), ctx)
    assert [(action, text) for _row, action, text in buttons] == [
        ("FINISH", "Finish Sketch"), ("CANCEL", "Cancel"),
    ]
    assert buttons[0][0] is buttons[1][0]


def test_completion_retains_rectangle_dimensions_and_existing_action_guards(ui, monkeypatch):
    ctx = context(ui)
    monkeypatch.setattr(ui.workspace_ui, "_draft_actions", lambda _ctx: (
        "DIMENSIONS", "FINISH", "CANCEL",
    ))
    monkeypatch.setattr(ui.workspace_ui, "available", lambda _ctx, action: action == "CANCEL")
    monkeypatch.setattr(ui.workspace_ui, "_icon", lambda *_args: 0)
    layout = Layout()
    ui.workspace_ui._draw_draft_completion(layout, ctx)
    controls = [control for kind, control in layout.entries if kind == "operator"]
    assert [item.action for item in controls] == ["DIMENSIONS", "FINISH", "CANCEL"]
    assert [item.enabled for item in controls] == [False, False, True]


@pytest.mark.parametrize("role", ["SKETCH", "PART"])
def test_primary_controls_precede_expanded_reports_in_real_history_draw(ui, monkeypatch, role):
    import sys

    ctx = context(ui)
    state = ctx.scene.mechanical_cad
    state.status = "READY"
    state.features = []
    state.show_part_details = True
    owner = object() if role == "SKETCH" else None
    monkeypatch.setattr(ui.document_state, "current_part_result", lambda _ctx: {"features": []})
    monkeypatch.setattr(ui.document_state, "geometry_report_is_current", lambda _ctx: False)
    monkeypatch.setattr(ui.workspace, "get_role", lambda _ctx: role)
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _ctx: owner is not None)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: owner)
    monkeypatch.setattr(ui.workspace, "_LAST_ERROR", "", raising=False)
    monkeypatch.setattr(ui.workspace_ui, "_has_general_tools", lambda _owner: True)
    monkeypatch.setattr(ui.workspace_ui, "_draft_actions", lambda _ctx: ("FINISH", "CANCEL"))
    monkeypatch.setattr(ui.workspace_ui, "_action_button", lambda layout, _ctx, action, **kwargs:
                        layout.label(text="ACTION " + action))
    monkeypatch.setattr(ui.workspace_ui, "_draw_general_status", lambda layout, *_args:
                        layout.label(text="EXPANDED SKETCH REPORT"))
    monkeypatch.setattr(ui.workspace_ui, "draw_part_limits", lambda layout, *_args:
                        layout.label(text="EXPANDED PART REPORT"))
    monkeypatch.setattr(ui.workspace_ui.operators, "part_action_reason", lambda *_args: "")
    monkeypatch.setitem(sys.modules, ports.PACKAGE + ".support_intent_ui", SimpleNamespace(
        draw_support_intent=ports.noop,
    ))
    layout = Layout()
    ui.workspace_ui.MCAD_PT_workspace_history.draw(SimpleNamespace(layout=layout), ctx)
    text = labels(layout)
    if role == "SKETCH":
        assert text.index("ACTION CANCEL") < text.index("EXPANDED SKETCH REPORT")
    else:
        assert text.index("ACTION CHECK") < text.index("EXPANDED PART REPORT")
        events = [(kind, value) for kind, value in layout.entries if kind in {"label", "menu"}]
        assert events.index(("menu", "MCAD_MT_export")) < events.index(("label", "EXPANDED PART REPORT"))


@pytest.mark.parametrize("raw,empty", [
    ('{"features": []}', True),
    ('{"features": [{"id": "sketch"}]}', False),
    ('{}', False), ('[]', False), ('null', False), ('invalid', False), (None, False),
])
def test_empty_document_uses_canonical_graph(raw, empty):
    assert status.document_is_empty(raw) is empty


@pytest.mark.parametrize("suspended,proposed", [(False, False), (True, False), (False, True)])
def test_empty_history_offers_named_start_without_bypassing_draft_guards(ui, monkeypatch, suspended, proposed):
    import sys

    ctx = context(ui)
    state = ctx.scene.mechanical_cad
    state.document_json = '{"features": []}'
    state.features = []
    state.status = "READY"
    before = state.document_json
    current_presentation_fixture(ui, monkeypatch, ctx, {"features": []})
    monkeypatch.setattr(ui.workspace, "get_role", lambda _ctx: "SKETCH")
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _ctx: suspended)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace, "_LAST_ERROR", "", raising=False)
    monkeypatch.setattr(ui.workspace_ui, "draw_suspended_draft", ports.noop)
    monkeypatch.setattr(ui.workspace_ui, "draw_staged_edit", lambda *_args: proposed)
    monkeypatch.setattr(ui.workspace_ui, "_action_button", lambda layout, _ctx, action, **kwargs:
                        layout.label(text="ACTION " + action + " " + kwargs.get("text", "")))
    monkeypatch.setitem(sys.modules, ports.PACKAGE + ".support_intent_ui", SimpleNamespace(
        draw_support_intent=ports.noop,
    ))
    layout = Layout()
    ui.workspace_ui.MCAD_PT_workspace_history.draw(SimpleNamespace(layout=layout), ctx)
    text = labels(layout)
    assert "Empty document" in text and "Build: Up to date" not in text
    assert ("ACTION NEW New Sketch" in text) is (not suspended and not proposed)
    assert ("ACTION RECTANGLE XY Rectangle" in text) is (not suspended and not proposed)
    assert ("ACTION IMPORT Import STEP" in text) is (not suspended and not proposed)
    assert "ACTION EDIT" not in text
    assert state.document_json == before


@pytest.mark.parametrize("raw,compact", [
    ('{"features": []}', True),
    ('{"features": [{"id": "sketch"}]}', False),
    ('{}', False), ('[]', False), ('invalid', False), ('', False),
])
def test_empty_part_palette_keeps_full_menu_and_uses_canonical_graph(ui, monkeypatch, raw, compact):
    ctx = context(ui)
    state = ctx.scene.mechanical_cad
    state.document_json = raw
    state.features = []  # A missing/stale display cache must not hide model tools.
    state.status = "FAILED"
    state.error = "Retained build error"
    monkeypatch.setattr(ui.workspace, "get_role", lambda _ctx: "PART")
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _ctx: False)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace_ui.staged_edit, "current", lambda _ctx: None)
    before = (state.document_json, state.status, state.error)
    full = ui.workspace_ui.menu_actions(ctx)
    assert len(full) == 26 and "EXTRUDE" in full and "EXPORT" in full
    assert ui.workspace_ui.palette_actions(ctx) == (("NEW", "RECTANGLE", "IMPORT") if compact else full)
    assert (state.document_json, state.status, state.error) == before


@pytest.mark.parametrize("role,suspended,proposed", [
    ("PART", True, False), ("PART", False, True), ("SKETCH", False, False),
    ("ASSEMBLY", False, False),
])
def test_start_palette_does_not_replace_other_owners(ui, monkeypatch, role, suspended, proposed):
    ctx = context(ui)
    ctx.scene.mechanical_cad.document_json = '{"features": []}'
    monkeypatch.setattr(ui.workspace, "get_role", lambda _ctx: role)
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _ctx: suspended)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace_ui.staged_edit, "current", lambda _ctx: object() if proposed else None)
    assert ui.workspace_ui.palette_actions(ctx) == ui.workspace_ui.menu_actions(ctx)


def test_import_start_action_preserves_operator_poll_and_draft_guard(ui, monkeypatch):
    ctx = context(ui)
    monkeypatch.setattr(ui.workspace, "is_cad_workspace", lambda _ctx: True)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace, "suspended_draft", lambda _ctx: {})
    monkeypatch.setattr(ui.workspace_ui, "_operator", lambda _action: SimpleNamespace(poll=lambda: False))
    assert not ui.workspace_ui.available(ctx, "IMPORT")
    monkeypatch.setattr(ui.workspace_ui, "_operator", lambda _action: SimpleNamespace(poll=lambda: True))
    assert ui.workspace_ui.available(ctx, "IMPORT")
    monkeypatch.setattr(ui.workspace, "suspended_draft", lambda _ctx: {"present": True})
    assert not ui.workspace_ui.available(ctx, "IMPORT")
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: object())
    assert not ui.workspace_ui.available(ctx, "IMPORT")


def test_empty_part_named_menu_still_draws_model_tools(ui, monkeypatch):
    ctx = context(ui)
    ctx.scene.mechanical_cad.document_json = '{"features": []}'
    monkeypatch.setattr(ui.workspace, "get_role", lambda _ctx: "PART")
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _ctx: False)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace_ui.staged_edit, "current", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace_ui, "action_reason", lambda *_args: "")
    actions = []
    monkeypatch.setattr(ui.workspace_ui, "_action_button", lambda _layout, _ctx, action: actions.append(action))
    ui.workspace_ui.MCAD_MT_workspace.draw(SimpleNamespace(layout=Layout()), ctx)
    assert set(ui.workspace_ui.menu_actions(ctx)) <= set(actions)
    assert {"FILLET_ADVANCED", "CHAMFER_ADVANCED", "SHELL_ADVANCED"} <= set(actions)


def fresh_state(**changes):
    values = dict(document_json="", status="EMPTY", features=[])
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("changes", [
    {}, {"document_json": " "}, {"document_json": "invalid"},
    {"document_json": '{"features": []}'}, {"status": "DIRTY"}, {"status": "FAILED"},
    {"features": [object()]}, {"document_name": "Retained"},
    {"document_path": "/retained"}, {"active_feature": "pad"}, {"parameters": [object()]},
    {"last_good_document_id": "previous"}, {"last_good_feature_id": "pad"},
    {"last_good_label": "Retained"}, {"sketch_draft_json": "invalid retained draft"},
    {"repair_intent_json": "retained repair"}, {"sketch_notice": "Review draft"},
    {"error": "Load failed"}, {"last_action_error": "Import failed"},
    {"geometry_report_json": "retained report"}, {"geometry_document_json": "retained"},
    {"geometry_status": "FAILED"}, {"geometry_message": "Retained message"},
])
def test_fresh_state_never_conflates_retained_or_malformed_data(changes):
    assert status.document_is_fresh(fresh_state(**changes)) is (not changes)


def test_fresh_part_palette_hides_gizmos_but_keeps_named_starters_and_full_menu(ui, monkeypatch):
    ctx = context(ui)
    ctx.scene.mechanical_cad = fresh_state()
    monkeypatch.setattr(ui.workspace, "get_role", lambda _ctx: "PART")
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _ctx: False)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace_ui.staged_edit, "current", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace_ui, "draw_suspended_draft", ports.noop)
    assert ui.workspace_ui.palette_actions(ctx) == ()
    assert len(ui.workspace_ui.menu_actions(ctx)) == 26
    assert ui.workspace_ui.palette_layout((), 900) is None
    monkeypatch.setattr(ui.workspace_ui, "_context_palette_layout", lambda _ctx: None)
    gizmos = {key: SimpleNamespace(hide=False, hide_select=False) for key in ui.workspace_ui._ACTIONS}
    group = SimpleNamespace(buttons=gizmos, backdrop=SimpleNamespace(hide=False))
    ui.workspace_ui.MCAD_GGT_workspace_palette.draw_prepare(group, ctx)
    assert group.backdrop.hide
    assert all(g.hide and g.hide_select for g in gizmos.values())
    layout = Layout()
    ui.workspace_ui.MCAD_PT_workspace_history.draw(SimpleNamespace(layout=layout), ctx)
    buttons = [value for kind, value in layout.entries if kind == "operator"]
    assert {item.text for item in buttons} >= {"New CAD Document", "Open CAD Document", "Import STEP Solid"}


@pytest.mark.parametrize("role,has_draft,proposed", [
    ("PART", True, False), ("PART", False, True), ("SKETCH", False, False),
    ("ASSEMBLY", False, False),
])
def test_fresh_scene_does_not_override_other_roles_or_retained_owners(ui, monkeypatch, role, has_draft, proposed):
    ctx = context(ui)
    ctx.scene.mechanical_cad = fresh_state()
    monkeypatch.setattr(ui.workspace, "get_role", lambda _ctx: role)
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _ctx: has_draft)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace_ui.staged_edit, "current", lambda _ctx: object() if proposed else None)
    assert ui.workspace_ui.palette_actions(ctx) == ui.workspace_ui.menu_actions(ctx)


@pytest.mark.parametrize("code,text", [
    ("DIRTY", "Needs rebuild"), ("BUILDING", "Updating"),
    ("FAILED", "Failed"), ("UNVERIFIED", "Unverified"),
])
def test_part_state_copy_preserves_failure_and_verification_meaning(code, text):
    assert status.part_state_text(code) == text


@pytest.mark.parametrize("code,text", [("DIRTY", "Needs rebuild"), ("BUILDING", "Updating")])
def test_workspace_draw_uses_plain_part_state_without_mutating_code(ui, monkeypatch, code, text):
    import sys

    ctx = context(ui)
    state = ctx.scene.mechanical_cad
    state.status = code
    state.features = []
    monkeypatch.setattr(ui.workspace, "get_role", lambda _ctx: "SKETCH")
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _ctx: False)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: None)
    monkeypatch.setattr(ui.workspace, "_LAST_ERROR", "", raising=False)
    monkeypatch.setattr(ui.workspace_ui, "_action_button", ports.noop)
    monkeypatch.setitem(sys.modules, ports.PACKAGE + ".support_intent_ui", SimpleNamespace(
        draw_support_intent=ports.noop,
    ))
    layout = Layout()
    ui.workspace_ui.MCAD_PT_workspace_history.draw(SimpleNamespace(layout=layout), ctx)
    assert "Part: " + text in labels(layout)
    assert "Part: Dirty" not in labels(layout) and "Part: Building" not in labels(layout)
    assert state.status == code


def test_expected_open_profile_is_informational_but_never_ready():
    readiness = {"ready": False, "error": {
        "code": "open_profile", "message": "Close this line chain before extrusion.",
    }}
    before = copy.deepcopy(readiness)
    assert status.profile_label(readiness) == (
        "Open sketch · close a loop", "INFO",
    )
    assert status.profile_label(readiness, pending=True) == ("Profile: unchecked", "INFO")
    assert readiness == before and readiness["ready"] is False


@pytest.mark.parametrize("code", [
    None, "unknown", "invalid_profile", "degenerate_profile", "self_intersecting_profile",
    "unresolved_coincidence", "branched_profile", "mixed_profile_regions",
    "multiple_profile_regions", "unsupported_profile_form", "unsupported_profile_coincidence",
    "unsupported_profile_scale", "unsupported_profile_sweep", "unsupported_profile_nontransverse",
    "unsupported_profile_contact", "unsupported_endpoint_discrepancy",
    "unsupported_endpoint_incidence", "numerically_ambiguous_profile",
])
def test_every_non_open_profile_diagnostic_retains_warning(code):
    # Even matching prose is not evidence of the expected state.
    readiness = {"ready": False, "error": {"code": code, "message": "Close this line chain before extrusion."}}
    assert status.profile_label(readiness) == ("Profile unavailable · review boundary", "ERROR")


def test_real_open_sketch_draw_preserves_dof_and_native_detail(ui, monkeypatch):
    owner = draft(response={"result": {
        "sketch": {"status": "okay", "remaining_dof": 3},
        "profile_check": {"ready": False, "error": {
            "code": "open_profile", "message": "Close this line chain before extrusion.",
        }},
    }})
    text = draw_status(ui, monkeypatch, owner)
    assert "Underdefined · 3 DoF" in text
    assert "Open sketch · close a loop" in text
    assert "Closed profile available" not in text
    assert "Close this line chain before extrusion." in draw_status(ui, monkeypatch, owner, expanded=True)
    owner.pending = object()
    text = draw_status(ui, monkeypatch, owner)
    assert "Open sketch" not in text and "Check pending" in text
    owner.pending = None
    owner.current_solution_response = lambda: None
    owner.retained_outline = object()
    text = draw_status(ui, monkeypatch, owner)
    assert "Open sketch" not in text and "Stale outline" in text


def test_retirement_explanation_is_collapsed_without_hiding_geometry_status(ui, monkeypatch):
    owner = draft(response={"result": {
        "sketch": {"status": "okay", "remaining_dof": 0},
        "profile_check": {"ready": True},
    }})
    owner.draft.retired_annotation_ids = ("radius",)
    text = draw_status(ui, monkeypatch, owner)
    assert "Fully defined" in text and "Closed profile available" in text
    assert "retired" not in text and "missing" not in text
    expanded = draw_status(ui, monkeypatch, owner, expanded=True)
    assert "1 retired radius label(s) retained" in expanded
    assert "Restore Sharp Corner" in expanded and "Undo" in expanded
    assert "Fully defined" in expanded
