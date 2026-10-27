"""Compact Assembly status preserves evidence distinctions and existing dispatch."""

import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_assembly_workflow_ui import Layout

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
spec = importlib.util.spec_from_file_location("assembly_summary", ADDON / "assembly_summary.py")
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def report(**changes):
    data = dict(complete=True, passed=True, verification_basis={"configured": True})
    data.update(changes)
    return json.dumps({"action": "assembly_check", "report": data})


@pytest.mark.parametrize("raw", ["", report(), report(policy_accepted=True), "invalid"])
def test_saved_verdict_never_becomes_current(raw):
    text, icon = summary.verification_summary(raw, current=False)
    assert text in {"Check again", "Not checked"}
    assert icon != "CHECKMARK"


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({}, "Measured pass"),
        (
            {"policy_accepted": True, "has_threshold_contacts": True},
            "Contact policy accepted",
        ),
        ({"has_threshold_contacts": True}, "Contact uncertain"),
        ({"known_interference": True, "policy_accepted": True}, "Interference found"),
        ({"known_clearance_violation": True}, "Clearance violation"),
        ({"complete": False, "policy_accepted": True}, "Check incomplete"),
        ({"verification_basis": {}}, "Measured · no pass policy"),
        ({"passed": False}, "Check did not pass"),
    ],
)
def test_verdict_precedence_is_not_policy_as_pass(fields, expected):
    assert summary.verification_summary(report(**fields), current=True)[0] == expected


def test_sampling_and_replay_cannot_claim_current_pose_pass():
    data = json.loads(report())
    data["action"] = "assembly_sample"
    assert (
        summary.verification_summary(json.dumps(data), current=True)[0] == "Samples: Measured pass"
    )
    data["action"] = "assembly_replay"
    assert summary.verification_summary(json.dumps(data), current=True) == ("Not checked", "INFO")


def controls(
    *,
    reason="",
    display=True,
    checked=True,
    updates=(),
    capture="",
    error="",
    active="preset",
    presets=(),
):
    source = ADDON / "assembly_ui.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_primary_actions"
    ]
    current = SimpleNamespace(report_json=report(), last_action_error=error)
    namespace = {
        "state": lambda _: current,
        "verification_summary": summary.verification_summary,
        "assembly_state": SimpleNamespace(
            display_is_current=lambda _: display,
            report_is_current=lambda _: checked,
            source_updates=lambda _: updates,
        ),
        "assembly_export_owner": SimpleNamespace(availability_reason=lambda _: reason),
        "assembly_operators": SimpleNamespace(working_part_capture_reason=lambda _: capture),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    before = vars(current).copy()
    layout = Layout()
    namespace["_primary_actions"](
        layout, object(), {"active_verification_preset": active, "verification_presets": presets}
    )
    assert vars(current) == before
    return layout.events


@pytest.mark.parametrize("reason", ["", "Runtime changed", "Check Pose first", "Incomplete check"])
def test_primary_actions_dispatch_existing_operators_and_explain_disabled_export(reason):
    events = controls(reason=reason)
    operators = [e for e in events if e[0] == "operator"]
    for name in ("mcad.assembly_replay", "mcad.assembly_check", "mcad.assembly_export_step"):
        assert sum(e[1] == name for e in operators) == 1
    export = next(e for e in operators if e[1] == "mcad.assembly_export_step")
    assert export[3] is (not reason)
    assert any(e[2].get("text") == "Why STEP is unavailable" for e in operators) is bool(reason)


def test_working_part_does_not_relabel_accepted_assembly_or_disable_its_actions():
    events = controls(updates=("part",))
    labels = [e[1]["text"] for e in events if e[0] == "label"]
    assert "Geometry current" in labels
    assert "Working Part edits not included" in labels
    assert any(e[0] == "operator" and e[1] == "mcad.assembly_update_source" for e in events)
    events = controls(capture="Working Part failed")
    operators = [e for e in events if e[0] == "operator"]
    assert all(e[3] for e in operators)
    assert not any("Working Part unavailable" in e[2].get("text", "") for e in operators)
    assert sum(e[1] == "mcad.assembly_status_details" for e in operators) == 1


def test_stale_display_and_evidence_stay_separate_from_action_failure():
    events = controls(display=False, checked=False, error="Native failure")
    labels = [e[1]["text"] for e in events if e[0] == "label"]
    assert "Rebuild before checking" in labels and "Check again" in labels
    assert "Measured pass" not in labels
    assert any(
        e[0] == "operator" and e[2].get("text") == "Action failed · view details" for e in events
    )


def test_primary_strip_precedes_tree_and_details_are_opt_in():
    source = (ADDON / "assembly_ui.py").read_text()
    tree = ast.parse(source)
    draw = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "draw_assembly_history"
    )
    calls = [n for n in ast.walk(draw) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]

    def line(name):
        return min(n.lineno for n in calls if n.func.id == name)

    assert line("_primary_actions") < line("_instance_details") < line("_part_details")
    props = (ADDON / "assembly_properties.py").read_text()
    for field in ("show_parts", "show_joints", "show_checks", "show_options"):
        assert f"{field}: BoolProperty(" in props
    # No duplicate primary check/export hiding below the tree.
    assert '"mcad.assembly_check"' not in ast.get_source_segment(source, draw)
    assert '"mcad.assembly_export_step"' not in ast.get_source_segment(source, draw)


@pytest.mark.parametrize("raw", ["bad", "null", "[]", '{"action":"assembly_check","report":null}'])
def test_unreadable_report_is_not_a_pass(raw):
    assert summary.verification_summary(raw, current=True) == ("Check unavailable", "ERROR")


@pytest.mark.parametrize("opened", [False, True])
def test_disclosure_only_reads_ui_state(opened):
    source = ADDON / "assembly_ui.py"
    tree = ast.parse(source.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_section"]
    current = SimpleNamespace(show_checks=opened)
    namespace = {"state": lambda _: current}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    layout = Layout()
    properties = []
    layout.prop = lambda *args, **kwargs: properties.append((args, kwargs))
    body = namespace["_section"](layout, object(), "show_checks", "Check report")
    assert (body is not None) is opened
    assert current.show_checks is opened
    assert properties[0][0] == (current, "show_checks")


@pytest.mark.parametrize("display", [False, True])
def test_check_only_enabled_for_current_geometry_with_visible_next_step(display):
    events = controls(display=display)
    check = next(e for e in events if e[0] == "operator" and e[1] == "mcad.assembly_check")
    assert check[3] is display
    if not display:
        assert any(e[0] == "label" and e[1]["text"] == "Rebuild before checking" for e in events)


@pytest.mark.parametrize(
    "presets, operator",
    [([], "mcad.assembly_standard_check_setup"), ([{"id": "one"}], "mcad.assembly_select_preset")],
)
def test_missing_policy_offers_creation_or_existing_selection(presets, operator):
    events = controls(active=None, presets=presets)
    assert any(e[0] == "operator" and e[1] == operator for e in events)


def test_selected_settings_visible_without_opening_advanced_details():
    events = controls(
        active="strict", presets=[{"id": "strict", "name": "Standard strict interference"}]
    )
    labels = [e[1]["text"] for e in events if e[0] == "label"]
    assert "Check settings: Standard strict interference" in labels
    assert not any(
        e[0] == "operator" and e[1] == "mcad.assembly_standard_check_setup" for e in events
    )


def test_primary_check_label_fits_compact_sidebar_and_keeps_pose_tooltip():
    events = controls()
    check = next(e for e in events if e[0] == "operator" and e[1] == "mcad.assembly_check")
    assert check[2]["text"] == "Check"
    source = (ADDON / "assembly_verification_ui.py").read_text()
    assert 'bl_label = "Check Current Pose"' in source


def test_contact_policy_details_preserve_raw_flags_and_qualification():
    source = (ADDON / "assembly_ui.py").read_text()
    assert "passed={report.get('passed')!r}" in source
    assert "policy_accepted={report.get('policy_accepted')!r}" in source
    assert "not a measured clearance pass or proof of exact touching" in source
