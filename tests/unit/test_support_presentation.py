"""Selected support sharing remains immutable, source-bound and presentation-only."""
import importlib
import json
from dataclasses import replace

import pytest
from test_feature_history_draw import count_proofs
from test_panel_presentation import draw as _draw
from test_panel_presentation import host as _host

host = _host
draw = _draw


def source_for(state):
    return {"id": state.features[0].feature_id, "kind": "sketch_constrained",
            "support_face": "face", "support_intent": {"orientation": {}}}


@pytest.mark.parametrize("mutation", ["selection", "policy", "orientation", "status", "document", "revoked", "bytes"])
def test_support_rejects_changed_binding(host, draw, mutation):
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    source = source_for(state)
    scope = replace(draw.capture_presentation(host.context),
                    support=(source["id"], json.dumps(source, sort_keys=True), ("text", "INFO", "why", "")))
    assert scope.selected_support(host.context, source)
    record = host.doc._RUNTIME[host.doc._scene_key(host.context.scene)]
    if mutation == "selection":
        state.feature_index = 1
    elif mutation == "policy":
        source.pop("support_intent")
    elif mutation == "orientation":
        source["support_intent"].pop("orientation")
    elif mutation == "status":
        state.status = "DIRTY"
    elif mutation == "document":
        state.document_json += " "
    elif mutation == "revoked":
        record["evidence"].publication._state = "cancelled"
    else:
        object.__setattr__(record["evidence"], "_response_payload", b"{}")
    assert scope.selected_support(host.context, source) is None


@pytest.mark.parametrize("mutation", ["selection", "policy", "status"])
def test_support_rechecks_after_guard(host, draw, monkeypatch, mutation):
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    source = source_for(state)
    scope = replace(draw.capture_presentation(host.context),
                    support=(source["id"], json.dumps(source, sort_keys=True), ("text", "INFO", "why", "")))
    original = host.modules.backend_runtime.assert_current
    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        if mutation == "selection":
            state.feature_index = 1
        elif mutation == "policy":
            source.pop("support_intent", None)
        else:
            state.status = "DIRTY"
        return value
    monkeypatch.setattr(host.modules.backend_runtime, "assert_current", changed)
    assert scope.selected_support(host.context, source) is None


def test_capture_support_does_not_add_proof_or_share_action_authority(host, draw, monkeypatch):
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    source = source_for(state)
    # Detached presentation fixture only, not geometry authority.
    monkeypatch.setattr(draw, "attached_feature", lambda *args: source)
    monkeypatch.setattr(draw, "support_text", lambda *args: ("ASSUMPTION ACTIVE", "INFO", "full why", ""))
    count = count_proofs(host, monkeypatch)
    scope = draw.capture_presentation(host.context)
    assert scope.selected_support(host.context, source) == ("ASSUMPTION ACTIVE", "INFO", "full why", "")
    assert count == [1]
    assert host.doc.current_part_result(host.context)
    assert count == [1, 1]


@pytest.mark.parametrize("status", ["assumed", "exact", "error", "unverified"])
@pytest.mark.parametrize("policy", ["strict", "world", "minimal"])
def test_support_full_disclosure_strings(host, monkeypatch, status, policy):
    module = importlib.import_module(host.doc.__package__ + ".support_presentation")
    feature = {"id": "attached"}
    if policy != "strict":
        feature["support_intent"] = {"orientation": {}} if policy == "minimal" else {}
    reason = "Complete ancestry diagnostic " * 20
    def decision(*args):
        if status == "error":
            raise ValueError(reason)
        return {"status": status, "reason": reason}
    monkeypatch.setattr(module, "support_decision", decision)
    text, icon, why, error = module.support_text(feature, None if status == "unverified" else {})
    assert why.startswith("Sketch support policy: " + ("Strict exact face" if policy == "strict" else "Preserve logical plane"))
    if policy != "strict":
        assert ("Minimal twist" if policy == "minimal" else "World axes") in why
    if status == "unverified":
        assert text == "Support unverified" and "current ancestry" in why
    elif status == "error":
        assert (text, icon, error) == ("Support needs review", "ERROR", reason)
        assert why.endswith(reason)
    else:
        assert text == ("ASSUMPTION ACTIVE" if status == "assumed" else "Support: exact face")
        assert why.endswith(reason) and not error


def test_selected_support_refuses_removed_solver(host, tmp_path):
    import sys

    from test_feature_history_draw import run
    root = tmp_path / "backend"
    solver = root / "src/mechanical_cad/sketch_solver.py"
    solver.parent.mkdir(parents=True)
    solver.write_text("# Fixture, never imported.\n")
    host.current[0] = host.modules.backend_selection.BackendSelection.capture(
        str(root), sys.executable, generation=2, lifetime_id="support", environment={}
    )
    assert run(host)
    module = importlib.import_module(host.doc.__package__ + ".feature_history_draw")
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    source = source_for(state)
    scope = replace(module.capture_presentation(host.context), support=(
        source["id"], json.dumps(source, sort_keys=True), ("text", "INFO", "why", "")))
    assert scope.selected_support(host.context, source)
    solver.unlink()
    assert scope.selected_support(host.context, source) is None
