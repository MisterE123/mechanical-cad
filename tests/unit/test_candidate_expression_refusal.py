"""Typed expression refusals occur only after exact prepublication validation."""

import ast
import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"
PACKAGE = "candidate_expression_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package
bridge = importlib.import_module(PACKAGE + ".bridge")


@pytest.fixture
def seam(monkeypatch):
    calls = []
    document = {"features": [{"id": "circle", "kind": "sketch_circle"}], "active_feature": "circle"}
    state = types.SimpleNamespace(document_json="original", feature_index=2, active_feature="output")
    response = {"ok": False, "result": {"status": "failed", "features": [{
        "id": "circle", "status": "failed", "error": {"code": "unknown_parameter", "message": "Unknown parameter typo"},
    }]}}
    staged = types.ModuleType(PACKAGE + ".staged_edit_store")
    staged.require_none = lambda context: calls.append("staged")
    monkeypatch.setitem(sys.modules, staged.__name__, staged)

    def forbidden(*args, **kwargs):
        raise AssertionError("Publication mutation must not start")

    def projection(*args, **kwargs):
        calls.append("projection")
        return response

    namespace = {
        "__name__": PACKAGE + ".document_state", "__package__": PACKAGE,
        "bridge": bridge, "json": json, "_REPLAY_RUNNING": True,
        "_assert_binding": lambda *args: calls.append("binding"),
        "_preflight_owned_display": lambda scene: calls.append("display-preflight"),
        "_evidence_projection": projection, "_state": lambda context: state,
        "_snapshot_fields": forbidden, "_CandidateDisplay": forbidden,
        "_populate_document": forbidden, "_apply_result": forbidden,
    }
    node = next(n for n in ast.parse((ROOT / "document_state.py").read_bytes()).body
                if isinstance(n, ast.FunctionDef) and n.name == "_publish_candidate_locked")
    exec(compile(ast.Module(body=[node], type_ignores=[]), "document_state.py", "exec"), namespace)

    def run(candidate_json=None):
        return namespace["_publish_candidate_locked"](
            object(), document, object(), {"scene": object()},
            json.dumps(document) if candidate_json is None else candidate_json,
        )

    return types.SimpleNamespace(document=document, state=state, response=response, calls=calls,
                                 namespace=namespace, run=run)


@pytest.mark.parametrize("code", ["unknown_parameter", "invalid_expression"])
def test_typed_refusal_is_after_evidence_and_before_any_mutation(seam, code):
    seam.response["result"]["features"][0]["error"]["code"] = code
    before = copy.deepcopy((seam.document, vars(seam.state)))
    with pytest.raises(bridge.CandidateExpressionError) as caught:
        seam.run()
    assert caught.value.feature_id == "circle" and caught.value.code == code
    assert not caught.value.outcome_unknown
    assert seam.calls == ["staged", "binding", "display-preflight", "projection"]
    assert (seam.document, vars(seam.state)) == before


@pytest.mark.parametrize("change", ["unknown-id", "empty-id", "nonstring-id", "duplicate-id",
                                   "blocked", "wrong-code", "nonstring-code", "wrong-message",
                                   "success-envelope", "success-result", "earlier-geometry-failure"])
def test_malformed_or_mismatched_failure_remains_generic(seam, change):
    row = seam.response["result"]["features"][0]
    if change == "unknown-id":
        row["id"] = "other"
    elif change == "empty-id":
        row["id"] = " "
    elif change == "nonstring-id":
        row["id"] = 5
    elif change == "duplicate-id":
        seam.document["features"].append(copy.deepcopy(seam.document["features"][0]))
    elif change == "blocked":
        row["status"] = "blocked"
    elif change == "wrong-code":
        row["error"]["code"] = "kernel_error"
    elif change == "nonstring-code":
        row["error"]["code"] = ["unknown_parameter"]
    elif change == "wrong-message":
        row["error"]["message"] = None
    elif change == "success-envelope":
        seam.response["ok"] = True
    elif change == "success-result":
        seam.response["result"]["status"] = "ok"
    else:
        seam.response["result"]["features"].insert(0, {
            "id": "circle", "status": "failed", "error": {"code": "kernel_error", "message": "Actual geometry failure"},
        })
    with pytest.raises(bridge.BridgeError) as caught:
        seam.run()
    assert not isinstance(caught.value, bridge.CandidateExpressionError)


def test_changed_candidate_rejected_before_evidence_projection(seam):
    original = json.dumps(seam.document)
    seam.document["features"][0]["kind"] = "changed"
    with pytest.raises(bridge.BridgeError, match="exact candidate changed") as caught:
        seam.run(original)
    assert not isinstance(caught.value, bridge.CandidateExpressionError)
    assert "projection" not in seam.calls


@pytest.mark.parametrize("boundary", ["_assert_binding", "_evidence_projection"])
def test_guard_rejection_cannot_be_reclassified(seam, boundary):
    def reject(*args, **kwargs):
        raise bridge.BridgeError("authentic boundary refusal")
    seam.namespace[boundary] = reject
    with pytest.raises(bridge.BridgeError, match="authentic boundary refusal") as caught:
        seam.run()
    assert not isinstance(caught.value, bridge.CandidateExpressionError)


@pytest.mark.parametrize("identifier,code", [("", "unknown_parameter"), ("circle", "geometry_error"), (1, "invalid_expression")])
def test_typed_constructor_refuses_unvalidated_identity(identifier, code):
    with pytest.raises(bridge.BridgeError) as caught:
        bridge.CandidateExpressionError("reason", feature_id=identifier, code=code)
    assert not isinstance(caught.value, bridge.CandidateExpressionError)
