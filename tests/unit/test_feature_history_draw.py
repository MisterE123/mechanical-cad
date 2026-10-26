"""Synchronous presentation sharing never substitutes for fresh action proof."""
import importlib
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_geometry3_owner import host as _host
from test_geometry3_owner import run

host = _host


@pytest.fixture
def draw(host):
    assert run(host)
    module = importlib.import_module(host.doc.__package__ + ".feature_history_draw")
    yield module
    assert not module._SCOPES


class Layout:
    def __init__(self, callback):
        self.callback = callback

    def template_list(self, *args, **kwargs):
        self.callback()


def first_row(draw, host):
    state = host.context.scene.mechanical_cad
    return draw.row_presentation(host.context, state, state.features[0], 0)


def count_proofs(host, monkeypatch):
    calls = []
    original = host.doc._evidence_projection
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(host.doc, "_evidence_projection", counted)
    return calls


@pytest.mark.parametrize("count", [1, 7])
@pytest.mark.parametrize("list_id", ["", "cad_history"])
def test_rows_share_one_proof_only_within_draw(host, draw, monkeypatch, count, list_id):
    calls = count_proofs(host, monkeypatch)
    shown = []
    layout = Layout(lambda: shown.extend(first_row(draw, host) for _ in range(count)))
    draw.draw_history(layout, host.context, list_id, rows=count)
    assert shown == [("CHECKMARK", False)] * count
    assert calls == [1] and not draw._SCOPES
    draw.draw_history(layout, host.context, list_id, rows=count)
    assert len(calls) == 2
    assert first_row(draw, host) == ("CHECKMARK", False)
    assert len(calls) == 3


@pytest.mark.parametrize("mutation", ["document", "owner", "scale", "status", "epoch", "revoked", "record", "removed", "bytes", "prepared", "scene", "items", "id"])
def test_later_rows_recheck_exact_live_guards(host, draw, mutation):
    state = host.context.scene.mechanical_cad
    key = host.doc._scene_key(host.context.scene)
    record = host.doc._RUNTIME[key]
    shown = []
    def callbacks():
        shown.append(first_row(draw, host))
        if mutation == "document":
            state.document_json += " "
        elif mutation == "owner":
            state.owner_id += "changed"
        elif mutation == "scale":
            host.context.scene.unit_settings.scale_length *= 2
        elif mutation == "status":
            state.status = "DIRTY"
        elif mutation == "epoch":
            host.current[0] = replace(host.current[0], generation=host.current[0].generation + 1)
        elif mutation == "revoked":
            record["evidence"].publication._state = "cancelled"
        elif mutation == "record":
            host.doc._RUNTIME[key] = dict(record)
        elif mutation == "removed":
            host.doc._RUNTIME.pop(key)
        elif mutation == "bytes":
            object.__setattr__(record["evidence"], "_response_payload", b"{}")
        elif mutation == "prepared":
            object.__setattr__(record["prepared"], "payload", b"{}")
        elif mutation == "scene":
            host.context.scene = SimpleNamespace(mechanical_cad=state)
        elif mutation == "items":
            state.features.reverse()
        else:
            state.features[0].feature_id = "unrecognized"
        shown.append(first_row(draw, host))
    draw.draw_history(Layout(callbacks), host.context, "", rows=7)
    assert shown == [("CHECKMARK", False), ("DOT", False)]


@pytest.mark.parametrize("mutation", ["removed", "repointed"])
def test_later_row_rechecks_solver_filesystem_identity(host, tmp_path, mutation):
    import sys
    root = tmp_path / "backend"
    source = root / "src/mechanical_cad/sketch_solver.py"
    source.parent.mkdir(parents=True)
    source.write_text("# Fixture, never imported.\n")
    outside = tmp_path / "other.py"
    outside.write_text("# Not the selected core.\n")
    host.current[0] = host.modules.backend_selection.BackendSelection.capture(
        str(root), sys.executable, generation=2, lifetime_id="draw", environment={}
    )
    assert run(host)
    draw = importlib.import_module(host.doc.__package__ + ".feature_history_draw")
    shown = []
    def callbacks():
        shown.append(first_row(draw, host))
        source.unlink()
        if mutation == "repointed":
            source.symlink_to(outside)
        shown.append(first_row(draw, host))
    draw.draw_history(Layout(callbacks), host.context, "", rows=7)
    assert shown == [("CHECKMARK", False), ("DOT", False)]


def test_post_guard_status_change_refuses_checkmark(host, draw, monkeypatch):
    original = host.modules.backend_runtime.assert_current
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        host.context.scene.mechanical_cad.status = "DIRTY"
        return result
    def callback():
        monkeypatch.setattr(host.modules.backend_runtime, "assert_current", changed)
        assert first_row(draw, host) == ("DOT", False)
    draw.draw_history(Layout(callback), host.context, "", rows=7)


def test_action_readers_inside_scope_still_validate(host, draw, monkeypatch):
    calls = count_proofs(host, monkeypatch)
    def callbacks():
        assert first_row(draw, host)[0] == "CHECKMARK"
        assert host.doc.current_part_result(host.context)
        assert host.doc.current_part_evidence(host.context)
    draw.draw_history(Layout(callbacks), host.context, "", rows=7)
    assert len(calls) == 3


def test_exception_and_nested_scope_cleanup(host, draw):
    def fail():
        assert first_row(draw, host)[0] == "CHECKMARK"
        raise RuntimeError("layout failed")
    def outer():
        scope = draw._SCOPES[-1]
        with pytest.raises(RuntimeError, match="layout failed"):
            draw.draw_history(Layout(fail), host.context, "nested", rows=1)
        assert draw._SCOPES == [scope]
        assert first_row(draw, host)[0] == "CHECKMARK"
    draw.draw_history(Layout(outer), host.context, "", rows=7)
    assert not draw._SCOPES


def test_profile_readiness_is_derived_from_current_output(host, draw):
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    identifier = state.features[0].feature_id
    presentation = draw.capture_presentation(host.context)
    detail = presentation.selected_detail(host.context, identifier)
    assert detail.profile_state == (True, "Closed profile available", "CHECKMARK")
    state.document_json += " "
    assert presentation.selected_detail(host.context, identifier) is None


def test_selected_profile_presentation_cannot_follow_a_new_selection(host, draw):
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    identifier = state.features[0].feature_id
    presentation = draw.capture_presentation(host.context)
    state.feature_index = 1
    assert presentation.selected_detail(host.context, identifier) is None
