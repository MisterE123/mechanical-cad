"""Host dialog ownership seams; actual registered RNA has a native smoke test."""

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def ui(monkeypatch):
    name = "end_face_repair_ui_tests"
    package = types.ModuleType(name)
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    monkeypatch.setitem(sys.modules, name, package)

    def module(suffix, **attrs):
        result = types.ModuleType(suffix)
        result.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, suffix, result)
        return result

    module("bpy")
    module("bpy.props", EnumProperty=lambda **k: None, StringProperty=lambda **k: None)
    module("bpy.types", Operator=type("Operator", (), {}))
    for suffix in ("document_state", "execution_lease", "staged_edit", "workspace"):
        module(name + "." + suffix)
    module(name + ".common", _state=lambda c: c.state)
    module(name + ".help_ui", _panel_wrap=lambda context, text: [text])
    module(
        name + ".operators",
        _reject_candidate=lambda op, c, message: ("REJECTED", message),
        _report_result=lambda op, c, result: result,
    )
    module(
        name + ".staged_edit_ui",
        validate_review=lambda *a: None,
        report_repair_kept=lambda *a: "KEPT",
        draw_review_notice=lambda layout: layout.label(
            text="Cancel keeps proposal; Discard abandons it"
        ),
    )
    return importlib.import_module(name + ".end_face_repair_ui")


def evidence(calls):
    return types.SimpleNamespace(
        publication=types.SimpleNamespace(cancel=lambda: calls.append("released"))
    )


def test_cancel_releases_only_owned_evidence_without_reading_proposal(ui):
    op = ui.MCAD_OT_replace_end_face()
    calls = []
    op._review_evidence = evidence(calls)
    ui.staged_edit.discard = lambda *a: pytest.fail("Dialog does not own proposal")
    ui.staged_edit.require = lambda *a: pytest.fail("Cancel must not inspect a newer proposal")
    op.cancel(None)
    op.cancel(None)
    assert calls == ["released"] and op._review_evidence is None


@pytest.mark.parametrize("stale", ["accepted", "proposal", "binding"])
def test_stale_review_rejects_before_candidate_or_accept_and_releases(ui, stale):
    op = ui.MCAD_OT_replace_end_face()
    op.poll = lambda c: True
    op.original_json = "accepted"
    op.staged_token = "old-token"
    op._document, op._binding = {}, {}
    calls = []
    op._review_evidence = evidence(calls)
    context = types.SimpleNamespace(
        state=types.SimpleNamespace(document_json="changed" if stale == "accepted" else "accepted")
    )
    validator = sys.modules[ui.__package__ + ".staged_edit_ui"]
    if stale == "proposal":
        validator.validate_review = lambda *a: (_ for _ in ()).throw(ValueError("Proposal changed"))
    ui.document_state._assert_binding = lambda *a: (_ for _ in ()).throw(
        ValueError("Binding changed")
    )
    ui.replace_end_face = lambda *a: pytest.fail("No stale candidate construction")
    ui.staged_edit.accept = lambda *a: pytest.fail("No stale publication")
    result = op.execute(context)
    assert result[0] == "REJECTED" and "changed" in result[1]
    assert calls == ["released"]


@pytest.mark.parametrize("outcome", [True, None, False, "raises"])
def test_execute_requires_full_staged_service_replay_and_releases(ui, outcome):
    op = ui.MCAD_OT_replace_end_face()
    op.poll = lambda c: True
    result, candidate = {"fresh": True}, {"candidate": True}
    op._review = lambda c: result
    op._document, op.feature_id, op.target, op.end_face, op.staged_token = (
        {},
        "pad",
        "body",
        "body/face/top",
        "revision",
    )
    calls = []
    op._review_evidence = evidence(calls)

    def replace(document, identifier, source, face, current):
        assert current is result and (identifier, source, face) == ("pad", "body", "body/face/top")
        return candidate

    def accept(context, token, received):
        assert token == "revision" and received is candidate
        calls.append("full replay")
        if outcome == "raises":
            raise ValueError("Unrelated downstream kernel error")
        return outcome

    ui.replace_end_face = replace
    ui.staged_edit.accept = accept
    actual = op.execute(None)
    assert calls == ["full replay", "released"]
    assert (
        actual == ("REJECTED", "Unrelated downstream kernel error")
        if outcome == "raises"
        else actual == ("KEPT" if outcome is None else outcome)
    )


def test_rna_choices_never_default_a_replacement_and_reset_on_source_change(ui):
    wrapper = types.SimpleNamespace(
        review_choices_json=json.dumps(
            {
                "sources": [["body", "Body [body]", "body"]],
                "faces": {"body": [["same/face/end", "End", "same/face/end"]]},
            }
        ),
        target="body",
        end_face="same/face/end",
    )
    assert ui._sources(wrapper, None)[0][0] == "NONE"
    assert ui._faces(wrapper, None)[0][0] == "NONE"
    ui._source_changed(wrapper, None)
    assert wrapper.end_face == "NONE"
    wrapper.review_choices_json = "malformed"
    assert len(ui._sources(wrapper, None)) == 1
