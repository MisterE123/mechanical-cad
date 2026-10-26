"""Guarded retained evidence composes actual operation schemas, never native CAD.

Core services below generate real ordinary envelopes with either no geometry or
explicit native-free test ports. These tests do not claim native qualification.
"""

import copy
import hashlib
import importlib
import json
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_guarded_evidence_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
contracts = importlib.import_module(PACKAGE + ".backend_contracts")
selections = importlib.import_module(PACKAGE + ".backend_selection")
evidence_module = importlib.import_module(PACKAGE + ".guarded_evidence")


def selection():
    return selections.BackendSelection.capture(
        str(ROOT), sys.executable, generation=2, lifetime_id="evidence-lifetime", environment={}
    )


def wrap(prepared, ordinary, *, phase="dispatched", missing=()):
    """Independent client fixture; never calls the server's receipt producer."""
    selected = selection()
    guarded = prepared.guarded_request()
    required = guarded["backend_contract"]["required_capabilities"]
    return {
        **copy.deepcopy(ordinary),
        "backend_receipt": {
            "version": 1,
            "request_id": guarded["backend_contract"]["request_id"],
            "request_fingerprint": hashlib.sha256(
                json.dumps(guarded, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "required_capabilities": list(required),
            "confirmed_capabilities": [name for name in required if name not in missing],
            "missing_capabilities": list(missing),
            "phase": phase,
            "backend": {
                "core_version": "test-ordinary-fixture",
                "project_root": str(ROOT),
                "core_origin": str(ROOT / "src/mechanical_cad"),
                "solver_origin": None
                if prepared.action == "canonical_snapshot" or phase != "dispatched"
                else str(ROOT / "src/mechanical_cad/sketch_solver.py"),
                "python_executable": selected.python_executable,
                "python_executable_target": selected.python_executable_target,
                "python_prefix": "/observed/prefix",
                "python_base_prefix": "/observed/base",
                "python_version": [3, 12, 14],
            },
        },
    }


def part_fixture(*, failed=False, action="replay"):
    from mechanical_cad.actions import run_geometry_action
    from mechanical_cad.engine import regenerate
    from mechanical_cad.model import Document, Feature
    from mechanical_cad.part_snapshot import input_fingerprint

    features = (
        (Feature("bad", "sketch_rectangle", "Invalid dimension", {"width": -1, "height": 5}),)
        if failed
        else ()
    )
    document = Document("part", "Fixture", {}, features, "bad" if failed else None)
    document = Document.from_dict(document.to_dict())
    ordinary = {
        "protocol_version": 1,
        "action": action,
        "result_version": 2,
        "document": document.to_dict(),
    }
    if action.startswith("export_"):
        ordinary["destination"] = "/never-written/fixture.step"
    if action == "replay":
        replay = regenerate(document, object(), result_version=2)
        response = {"ok": replay.ok, "result": replay.result, "error": None}
    else:
        response = run_geometry_action(
            document,
            action,
            destination=ordinary.get("destination"),
            kernel=object(),
            result_version=2,
        )
    response.update(
        protocol_version=1, result_version=2, input_fingerprint=input_fingerprint(ordinary)
    )
    prepared = contracts.prepare_request(ordinary)
    return prepared, wrap(prepared, response)


def snapshot_fixture():
    from mechanical_cad.sidecar import process_request

    raw = json.loads((ROOT / "examples/regressions/viewport_schema2_capture.mcad.json").read_text())
    operation = {"protocol_version": 1, "action": "canonical_snapshot", "document": raw}
    prepared = contracts.prepare_request(operation)
    return prepared, wrap(prepared, process_request(operation))


def solve_fixture(monkeypatch, *, failed=False):
    from mechanical_cad import sketch_evaluation
    from mechanical_cad.model import Document, Feature
    from mechanical_cad.sidecar import process_request
    from mechanical_cad.sketch_model import Constraint, Line, Point, SketchDefinition
    from mechanical_cad.sketch_solver import SolveReport, Status

    sketch = SketchDefinition(
        "open",
        (Point("a", 0, 0), Point("b", 5, 0)),
        (Line("edge", "a", "b"),),
        (Constraint("length", "distance", ("a", "b"), 5),),
        schema_version=2,
    )
    document = Document(
        "part",
        "Open sketch fixture",
        {},
        (Feature("profile", "sketch_constrained", "Sketch", sketch=sketch),),
        "profile",
        schema_version=2,
    )

    # A synthetic native-port report drives the real ordinary service/validator.
    # It is deliberately separate from the server capability implementation.
    def solve(numeric):
        return SolveReport(
            Status.INCONSISTENT if failed else Status.OKAY,
            None if failed else 3,
            ("length",) if failed else (),
            numeric,
            None if failed else 0.0,
        )

    monkeypatch.setattr(sketch_evaluation, "solve", solve)
    ordinary = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "document": document.to_dict(),
        "feature_id": "profile",
    }
    prepared = contracts.prepare_request(ordinary)
    return prepared, wrap(prepared, process_request(ordinary))


def assembly_fixture(action="assembly_replay"):
    from mechanical_cad.assembly_model import AssemblyDocument
    from mechanical_cad.assembly_policy import fingerprint
    from mechanical_cad.assembly_service import run_assembly_action

    assembly = AssemblyDocument.from_json(
        (ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()
    )
    ordinary = {
        "protocol_version": 1,
        "kind": "assembly",
        "action": action,
        "result_version": 2,
        "assembly": assembly.to_dict(),
    }
    prepared = contracts.prepare_request(ordinary)
    response = run_assembly_action(assembly, action, result_version=2, kernel=object())
    response.update(
        protocol_version=1,
        kind="assembly",
        assembly_protocol_version=1,
        input_fingerprint=fingerprint(ordinary),
    )
    return prepared, wrap(prepared, response)


def test_real_empty_part_fixture_and_snapshot_validation_are_detached_and_reusable():
    for fixture in (part_fixture, snapshot_fixture):
        prepared, response = fixture()
        owner = object()
        accepted = evidence_module.accept_response(
            prepared, response, selection(), owner_token=owner
        )
        assert type(accepted) is evidence_module.GuardedEvidence
        expectation = {
            "expected_action": prepared.action,
            "expected_result_version": prepared.operation_request().get("result_version"),
        }
        first = accepted.revalidate(
            selection(), owner_token=owner, require_success=True, **expectation
        )
        second = accepted.revalidate(
            selection(), owner_token=owner, require_success=True, **expectation
        )
        assert first == second and first is not second
        first["mutated"] = True
        response["result"]["document_id"] = "external mutation"
        assert "mutated" not in accepted.revalidate(selection(), owner_token=owner, **expectation)
        with pytest.raises(contracts.BackendContractError, match="projection"):
            accepted.revalidate(selection(), owner_token=owner, projection=first, **expectation)
        with pytest.raises((AttributeError, TypeError)):
            accepted.selection = selection()


def test_current_epoch_generation_owner_and_action_are_all_required():
    prepared, response = snapshot_fixture()
    owner = object()
    accepted = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    for current in (
        replace(selection(), generation=3),
        replace(selection(), lifetime_id="reenabled"),
    ):
        with pytest.raises(selections.SelectionError):
            accepted.revalidate(current, owner_token=owner)
    with pytest.raises(contracts.BackendContractError, match="owner"):
        accepted.revalidate(selection(), owner_token=object())
    for action in ("solve_sketch", "replay", "check_geometry", "export_step", "assembly_replay"):
        with pytest.raises(contracts.BackendContractError, match="action"):
            accepted.revalidate(selection(), owner_token=owner, expected_action=action)
    assert accepted.revalidate(
        selection(),
        owner_token=owner,
        expected_action="canonical_snapshot",
        expected_result_version=None,
    )


def test_retained_evidence_separate_from_single_publication_and_cancellation():
    prepared, response = part_fixture()
    owner = object()
    accepted = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    claim = accepted.publication
    assert claim is accepted.publication
    claim.consume(selection(), owner_token=owner, expected_action="replay", require_success=True)
    with pytest.raises(contracts.BackendContractError):
        claim.consume(selection(), owner_token=owner)
    assert accepted.revalidate(selection(), owner_token=owner)
    forged = evidence_module.EvidencePublication(accepted)
    with pytest.raises(contracts.BackendContractError):
        forged.consume(selection(), owner_token=owner)
    another = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    assert another.publication.cancel()
    assert not another.publication.cancel()
    with pytest.raises(contracts.BackendContractError):
        another.publication.consume(selection(), owner_token=owner)


@pytest.mark.parametrize("action", ["replay", "check_geometry", "export_step", "export_stl"])
def test_real_partial_part_and_geometry_failure_remain_diagnostics_not_success(action):
    prepared, response = part_fixture(failed=True, action=action)
    owner = object()
    accepted = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    assert type(accepted) is evidence_module.GuardedEvidence and not accepted.successful
    projection = accepted.revalidate(selection(), owner_token=owner, expected_action=action)
    assert projection["result"]["features"][0]["status"] == "failed"
    with pytest.raises(contracts.BackendContractError, match="successful authority"):
        accepted.revalidate(selection(), owner_token=owner, require_success=True)


@pytest.mark.parametrize("failed", [False, True])
def test_real_solve_service_fixture_uses_existing_typed_validator(monkeypatch, failed):
    prepared, response = solve_fixture(monkeypatch, failed=failed)
    owner = object()
    accepted = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    assert accepted.successful is not failed
    projection = accepted.revalidate(selection(), owner_token=owner)
    projection["result"]["sketch"]["remaining_dof"] = 1
    with pytest.raises(contracts.BackendContractError):
        accepted.revalidate(selection(), owner_token=owner, projection=projection)
    forged = copy.deepcopy(response)
    forged["result"]["sketch"]["solved"] = {} if failed else forged["result"]["sketch"]["solved"]
    if not failed:
        forged["result"]["sketch"]["solved"]["points"][0]["id"] = "foreign"
    with pytest.raises(contracts.BackendContractError):
        evidence_module.accept_response(prepared, forged, selection(), owner_token=owner)


@pytest.mark.parametrize("action", ["assembly_replay", "assembly_check", "assembly_sample"])
def test_real_blocked_assembly_fixture_and_legacy_class_cannot_bypass(action):
    prepared, response = assembly_fixture(action)
    owner = object()
    accepted = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    assert type(accepted) is evidence_module.GuardedEvidence and not accepted.successful
    assert accepted.revalidate(selection(), owner_token=owner)["report"]["complete"] is False
    assembly_bridge = importlib.import_module(PACKAGE + ".assembly_bridge")
    legacy = assembly_bridge.AssemblyResponse(
        contracts.project_response(response), prepared.operation_request()
    )
    with pytest.raises(contracts.BackendContractError):
        evidence_module.accept_response(prepared, legacy, selection(), owner_token=owner)


@pytest.mark.parametrize("action", sorted(contracts.ACTIONS))
def test_strict_common_failure_all_actions_has_no_operation_authority(action):
    operation = {"protocol_version": 1, "action": action, "document": {}}
    if action.startswith("assembly_"):
        operation["kind"] = "assembly"
    ordinary = {
        "protocol_version": 1,
        "ok": False,
        "result": None,
        "error": {"code": "invalid_document", "message": "No document."},
    }
    if action != "canonical_snapshot":
        operation["result_version"] = ordinary["result_version"] = 2
    prepared = contracts.prepare_request(operation)
    response = wrap(prepared, ordinary)
    accepted = evidence_module.accept_response(
        prepared, response, selection(), owner_token=object()
    )
    assert type(accepted) is evidence_module.GuardedFailure
    assert not accepted.definite_no_dispatch
    assert not hasattr(accepted, "publication") and not hasattr(accepted, "revalidate")
    for field, value in (
        ("extra", 1),
        ("result_version", True),
        ("error", {"code": "x", "message": "bad", "extra": 1}),
    ):
        forged = copy.deepcopy(response)
        forged[field] = value
        with pytest.raises(contracts.BackendContractError):
            evidence_module.accept_response(prepared, forged, selection(), owner_token=object())


def test_valid_pre_dispatch_failure_is_no_dispatch_and_cannot_claim_result_or_version():
    prepared = contracts.prepare_request(
        {"protocol_version": 1, "action": "replay", "result_version": 3, "document": {}}
    )
    ordinary = {
        "protocol_version": 1,
        "ok": False,
        "result": None,
        "error": {"code": "backend_capability_missing", "message": "No result 3."},
    }
    missing = ["mcad.part-result/3", contracts.SKETCH_ARCS]
    response = wrap(prepared, ordinary, phase="rejected_before_dispatch", missing=missing)
    accepted = evidence_module.accept_response(
        prepared, response, selection(), owner_token=object()
    )
    assert accepted.definite_no_dispatch and accepted.rejected_before_dispatch
    response["result_version"] = 3
    with pytest.raises(contracts.BackendContractError):
        evidence_module.accept_response(prepared, response, selection(), owner_token=object())


def test_malformed_result3_never_grants_authority_even_with_positive_receipt():
    prepared = contracts.prepare_request(
        {"protocol_version": 1, "action": "replay", "result_version": 3, "document": {}}
    )
    response = wrap(
        prepared,
        {
            "protocol_version": 1,
            "result_version": 3,
            "ok": True,
            "input_fingerprint": "0" * 64,
            "result": {},
            "error": None,
        },
    )
    with pytest.raises(contracts.BackendContractError, match="Invalid guarded replay"):
        evidence_module.accept_response(prepared, response, selection(), owner_token=object())


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(input_fingerprint="0" * 64),
        lambda r: r["result"].update(document_id="different"),
        lambda r: r["result"].update(extra=True),
        lambda r: r.update(extra=True),
        lambda r: r.update(result_version=True),
        lambda r: r["backend_receipt"].update(request_id="f" * 32),
    ],
)
def test_positive_receipt_cannot_replace_inner_fingerprints_and_strict_schema(change):
    prepared, response = part_fixture()
    change(response)
    with pytest.raises(contracts.BackendContractError):
        evidence_module.accept_response(prepared, response, selection(), owner_token=object())


def test_native_free_import_isolation_in_fresh_interpreter():
    script = f"""
import importlib, importlib.abc, sys, types
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}:
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Deny())
p = types.ModuleType('isolated'); p.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules['isolated'] = p
for name in ('backend_selection', 'backend_contracts', 'guarded_evidence'):
    importlib.import_module('isolated.' + name)
print('GUARDED_NATIVE_FREE_OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "GUARDED_NATIVE_FREE_OK"


@pytest.mark.parametrize("action", ["assembly_replay", "assembly_check", "assembly_sample"])
def test_assembly_public_projection_round_trip_checks_nested_response_and_private_request(action):
    prepared, response = assembly_fixture(action)
    owner = object()
    accepted = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    projection = accepted.revalidate(selection(), owner_token=owner)
    assert accepted.revalidate(selection(), owner_token=owner, projection=projection) == projection
    projection["report"]["complete"] = True
    with pytest.raises(contracts.BackendContractError):
        accepted.revalidate(selection(), owner_token=owner, projection=projection)
    projection = accepted.revalidate(selection(), owner_token=owner)
    projection._request["assembly"]["name"] = "changed private source"
    with pytest.raises(contracts.BackendContractError, match="request"):
        accepted.revalidate(selection(), owner_token=owner, projection=projection)
    projection = accepted.revalidate(selection(), owner_token=owner)
    projection._request["cycle"] = projection._request
    with pytest.raises(contracts.BackendContractError):
        accepted.revalidate(selection(), owner_token=owner, projection=projection)


@pytest.mark.parametrize(
    "field,size,valid",
    [
        ("code", 128, True),
        ("code", 129, False),
        ("message", 100_000, True),
        ("message", 100_001, False),
    ],
)
def test_common_failure_exact_error_string_edges(field, size, valid):
    operation = {"protocol_version": 1, "action": "replay", "result_version": 2, "document": {}}
    prepared = contracts.prepare_request(operation)
    ordinary = {
        "protocol_version": 1,
        "result_version": 2,
        "ok": False,
        "result": None,
        "error": {"code": "error", "message": "Failure."},
    }
    ordinary["error"][field] = "x" * size
    response = wrap(prepared, ordinary)
    if valid:
        assert (
            type(
                evidence_module.accept_response(
                    prepared, response, selection(), owner_token=object()
                )
            )
            is evidence_module.GuardedFailure
        )
    else:
        with pytest.raises(contracts.BackendContractError):
            evidence_module.accept_response(prepared, response, selection(), owner_token=object())


def test_identical_input_new_operation_rejects_old_nonce_and_ordinary_hash_is_unchanged():
    prepared, response = part_fixture()
    next_operation = contracts.prepare_request(prepared.operation_request())
    assert prepared.request_id != next_operation.request_id
    with pytest.raises(contracts.BackendContractError, match="nonce"):
        evidence_module.accept_response(next_operation, response, selection(), owner_token=object())
    ordinary = prepared.operation_request()
    expected = hashlib.sha256(
        json.dumps(ordinary, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert response["input_fingerprint"] == expected
    assert response["backend_receipt"]["request_fingerprint"] != expected


def test_all_nine_operation_projections_validate_without_core_or_native_imports(monkeypatch):
    fixtures = [snapshot_fixture(), solve_fixture(monkeypatch)]
    fixtures += [
        part_fixture(action=action)
        for action in ("replay", "check_geometry", "export_step", "export_stl")
    ]
    fixtures += [
        assembly_fixture(action)
        for action in ("assembly_replay", "assembly_check", "assembly_sample")
    ]
    payload = json.dumps([[request.guarded_request(), response] for request, response in fixtures])
    script = f"""
import importlib, importlib.abc, json, sys, types
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}:
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Deny())
p = types.ModuleType('isolated'); p.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules['isolated'] = p
selection = importlib.import_module('isolated.backend_selection').BackendSelection.capture(
    {str(ROOT)!r}, sys.executable, generation=2, lifetime_id='evidence-lifetime', environment={{}})
evidence = importlib.import_module('isolated.guarded_evidence')
for request, response in json.load(sys.stdin):
    owner = object()
    accepted = evidence.accept_response(request, response, selection, owner_token=owner)
    expected = dict(expected_action=request.get('action', 'replay'),
                    expected_result_version=request.get('result_version'))
    projection = accepted.revalidate(selection, owner_token=owner, **expected)
    accepted.revalidate(selection, owner_token=owner, projection=projection, **expected)
print('NINE_GUARDED_PROJECTIONS_NATIVE_FREE_OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", script], input=payload, capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "NINE_GUARDED_PROJECTIONS_NATIVE_FREE_OK"


def test_cancelled_claim_revokes_retained_authority_but_keeps_historical_bytes():
    prepared, response = part_fixture()
    owner = object()
    accepted = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    historical = accepted.response_snapshot()
    assert accepted.publication.cancel()
    with pytest.raises(contracts.BackendContractError, match="cancelled"):
        accepted.revalidate(selection(), owner_token=owner)
    assert accepted.response_snapshot() == historical
    assert accepted.operation_request() == prepared.operation_request()
    assert accepted.guarded_request() == prepared.guarded_request()
    assert accepted.successful  # Historical outcome, explicitly not current authority.


def test_cancellation_during_operation_revalidation_cannot_escape_final_check(monkeypatch):
    prepared, response = part_fixture()
    owner = object()
    accepted = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    validate = evidence_module._validate

    def cancelling_validate(*args):
        result = validate(*args)
        assert accepted.publication.cancel()
        return result

    monkeypatch.setattr(evidence_module, "_validate", cancelling_validate)
    with pytest.raises(contracts.BackendContractError, match="cancelled"):
        accepted.publication.consume(selection(), owner_token=owner)
    assert accepted.response_snapshot() == response


def test_consumed_claim_still_allows_retained_reads_and_cannot_be_cancelled_as_pending():
    prepared, response = part_fixture()
    owner = object()
    accepted = evidence_module.accept_response(prepared, response, selection(), owner_token=owner)
    accepted.publication.consume(selection(), owner_token=owner)
    assert not accepted.publication.cancel()
    assert accepted.revalidate(selection(), owner_token=owner)
