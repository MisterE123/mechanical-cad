"""Native-free failure fixtures plus optional real sidecar response checks."""

import copy
import dataclasses
import importlib
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
PACKAGE = "mcad_constraint_diagnostics_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
diagnostics = importlib.import_module(PACKAGE + ".constraint_diagnostics")
contracts = diagnostics.part_contracts
Error = diagnostics.ConstraintDiagnosticsError


def bindings():
    return {
        "session_id": "owner-1",
        "command_revision": 3,
        "input_token": "edit-lease-2",
        "input_revision": 2,
    }


def request():
    return {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "feature_id": "sketch",
        "document": {
            "schema_version": 2,
            "id": "part",
            "name": "Failed sketch candidate",
            "units": "mm",
            "parameters": {"radius_mm": 5},
            "features": [
                {
                    "id": "sketch",
                    "kind": "sketch_constrained",
                    "sketch": {
                        "schema_version": 2,
                        "id": "geometry",
                        "units": "mm",
                        "plane": {
                            "id": "xy",
                            "origin": [0, 0, 0],
                            "quaternion": [1, 0, 0, 0],
                        },
                        "points": [{"id": "center", "u": 3, "v": 4}],
                        "lines": [],
                        "circles": [{"id": "rim", "center": "center", "radius": 7}],
                        "constraints": [
                            {
                                "id": "radius",
                                "kind": "radius",
                                "refs": ["rim"],
                                "value": "radius_mm",
                            },
                            {
                                "id": "conflict",
                                "kind": "radius",
                                "refs": ["rim"],
                                "value": 20,
                            },
                            {
                                "id": "anchor",
                                "kind": "fixed",
                                "refs": ["center"],
                                "target": [3, 4],
                            },
                        ],
                    },
                }
            ],
            "active_feature": "sketch",
        },
    }


def failure(candidate, *, status="inconsistent", candidates=("radius", "conflict")):
    """Actual protocol shape; this fixture does not claim native solving ran."""
    canonical = contracts._expected_document(candidate["document"])
    return {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "input_fingerprint": contracts.input_fingerprint(candidate),
        "ok": False,
        "result": {
            "document_id": canonical["id"],
            "document_hash": contracts.document_hash(canonical),
            "feature_id": "sketch",
            "sketch": {
                "solver": "libslvs",
                "solver_version": "3.2",
                "status": status,
                "remaining_dof": None,
                "failed_constraints": list(candidates),
                "redundant_constraints": [],
                "max_residual_mm": None,
                "solved": None,
                "dimensions": {"radius": 5, "conflict": 20},
            },
            "profile_check": None,
        },
        "error": {"code": "sketch_solve_failed", "message": "Keep the draft to correct it."},
    }


@pytest.mark.parametrize("status", ["inconsistent", "didnt_converge", "too_many_unknowns"])
@pytest.mark.parametrize("candidates", [(), ("radius", "conflict")])
def test_failure_only_snapshot_uses_actual_report_status_and_candidate_ids(status, candidates):
    candidate = request()
    response = failure(candidate, status=status, candidates=candidates)
    before = copy.deepcopy((candidate, response))
    snapshot = diagnostics.FailureDiagnostics(response, candidate, **bindings())
    assert (candidate, response) == before
    assert snapshot.solver_status == status
    assert snapshot.candidate_constraint_ids == candidates
    assert snapshot.redundant_constraint_ids == ()
    assert snapshot.error_code == response["error"]["code"]
    assert snapshot.error_message == response["error"]["message"]
    assert snapshot.request_fingerprint == contracts.input_fingerprint(candidate)
    assert snapshot.document_id == "part" and snapshot.feature_id == "sketch"
    assert snapshot.sketch_id == "geometry"
    assert snapshot.document_hash == response["result"]["document_hash"]
    assert snapshot.for_current(copy.deepcopy(candidate), **bindings()) is snapshot


def test_redundant_ids_are_separate_and_report_order_is_preserved():
    candidate = request()
    source = candidate["document"]["features"][0]["sketch"]
    source["constraints"].append({**source["constraints"][0], "id": "radius_copy"})
    response = failure(candidate, candidates=("radius", "conflict"))
    report = response["result"]["sketch"]
    report["dimensions"]["radius_copy"] = 5
    report["redundant_constraints"] = ["radius_copy"]
    snapshot = diagnostics.FailureDiagnostics(response, candidate, **bindings())
    assert snapshot.candidate_constraint_ids == ("radius", "conflict")  # Not sorted.
    assert snapshot.redundant_constraint_ids == ("radius_copy",)


def test_no_mutable_aliases_or_current_solve_authority_are_retained():
    candidate = request()
    response = failure(candidate)
    snapshot = diagnostics.FailureDiagnostics(response, candidate, **bindings())
    assert {field.name for field in dataclasses.fields(snapshot)} == {
        "request_fingerprint",
        "session_id",
        "command_revision",
        "input_token",
        "input_revision",
        "document_id",
        "document_hash",
        "feature_id",
        "sketch_id",
        "solver_status",
        "candidate_constraint_ids",
        "redundant_constraint_ids",
        "error_code",
        "error_message",
    }
    assert all(
        type(getattr(snapshot, field.name)) in (str, int, tuple)
        for field in dataclasses.fields(snapshot)
    )
    response["result"]["sketch"]["failed_constraints"].clear()
    response["error"]["message"] = "Caller changed the response"
    candidate["document"]["features"][0]["sketch"]["constraints"].clear()
    assert snapshot.candidate_constraint_ids == ("radius", "conflict")
    assert snapshot.error_message == "Keep the draft to correct it."
    assert snapshot.for_current(request(), **bindings()) is snapshot
    assert snapshot.for_current(candidate, **bindings()) is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.error_message = "Changed"
    with pytest.raises(TypeError):
        snapshot.candidate_constraint_ids[0] = "Changed"
    with pytest.raises(TypeError):
        dataclasses.replace(snapshot, solver_status="okay")
    assert not hasattr(snapshot, "__dict__")


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(protocol_version=True),
        lambda r: r.update(result_version=1),
        lambda r: r.update(action="replay"),
        lambda r: r.update(input_fingerprint="0" * 64),
        lambda r: r.update(ok=0),
        lambda r: r.update(ok=True),
        lambda r: r.update(extra=True),
        lambda r: r["result"].update(document_id="other"),
        lambda r: r["result"].update(document_hash="0" * 64),
        lambda r: r["result"].update(feature_id="other"),
        lambda r: r["result"].update(extra=True),
        lambda r: r["result"].update(sketch=None),
        lambda r: r["result"].update(profile_check={"ready": True, "error": None}),
        lambda r: r["result"]["sketch"].update(extra=True),
        lambda r: r["result"]["sketch"].update(solver="unknown"),
        lambda r: r["result"]["sketch"].update(solver_version="3.3"),
        lambda r: r["result"]["sketch"].update(status="unknown"),
        lambda r: r["result"]["sketch"].update(status=[]),
        lambda r: r["result"]["sketch"].update(status="okay"),
        lambda r: r["result"]["sketch"].update(remaining_dof=0),
        lambda r: r["result"]["sketch"].update(solved={}),
        lambda r: r["result"]["sketch"].update(failed_constraints=["missing"]),
        lambda r: r["result"]["sketch"].update(failed_constraints=["center"]),
        lambda r: r["result"]["sketch"].update(failed_constraints=["radius", "radius"]),
        lambda r: r["result"]["sketch"].update(failed_constraints=[[]]),
        lambda r: r["result"]["sketch"].update(failed_constraints=("radius",)),
        lambda r: r["result"]["sketch"].update(redundant_constraints=["missing"]),
        lambda r: r["result"]["sketch"].update(dimensions={"radius": 5}),
        lambda r: r["result"]["sketch"]["dimensions"].update(conflict=21),
        lambda r: r["result"]["sketch"].update(max_residual_mm=float("nan")),
        lambda r: r["result"]["sketch"].update(max_residual_mm=1 << 20000),
        lambda r: r.update(error=None),
        lambda r: r["error"].update(code="not_a_solve_failure"),
        lambda r: r["error"].update(message=""),
        lambda r: r["error"].update(message="x" * 100_001),
        lambda r: r["error"].update(message="\ud800"),
        lambda r: r["error"].update(extra=True),
    ],
)
def test_invalid_unknown_or_contradictory_response_never_creates_diagnostics(change):
    candidate = request()
    response = failure(candidate)
    change(response)
    with pytest.raises(Error):
        diagnostics.FailureDiagnostics(response, candidate, **bindings())


@pytest.mark.parametrize("wire_error", [False, True])
def test_validated_action_and_wire_errors_without_native_report_are_not_constraint_diagnostics(
    wire_error,
):
    candidate = request()
    response = failure(candidate)
    response.update(result=None, error={"code": "invalid_expression", "message": "Unknown name."})
    if wire_error:
        response.pop("action")
        response.pop("input_fingerprint")
    assert diagnostics.sketch_action_bridge.validate_solve_response(response, candidate) == response
    with pytest.raises(Error, match="failed native solve report"):
        diagnostics.FailureDiagnostics(response, candidate, **bindings())


@pytest.mark.parametrize("profile_ready", [False, True])
def test_valid_successful_solve_cannot_be_used_as_failure_diagnostics(profile_ready):
    candidate = request()
    source = candidate["document"]["features"][0]["sketch"]
    source["constraints"].clear()
    response = failure(candidate, status="okay", candidates=())
    response.update(ok=True, error=None)
    response["result"]["sketch"].update(
        remaining_dof=3,
        solved=contracts._expected_document(candidate["document"])["features"][0]["sketch"],
        max_residual_mm=0,
        dimensions={},
    )
    response["result"]["profile_check"] = {
        "ready": profile_ready,
        "error": None if profile_ready else {"code": "invalid_profile", "message": "No profile."},
    }
    diagnostics.sketch_action_bridge.validate_solve_response(response, candidate)
    with pytest.raises(Error, match="failed native solve report"):
        diagnostics.FailureDiagnostics(response, candidate, **bindings())


def test_nonconvergence_residual_and_empty_candidates_never_become_solve_authority():
    candidate = request()
    response = failure(candidate, status="didnt_converge", candidates=())
    response["result"]["sketch"]["max_residual_mm"] = 0.25
    snapshot = diagnostics.FailureDiagnostics(response, candidate, **bindings())
    assert snapshot.solver_status == "didnt_converge"
    assert snapshot.candidate_constraint_ids == ()
    assert not hasattr(snapshot, "max_residual_mm")
    assert not hasattr(snapshot, "remaining_dof")


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "other-owner"),
        ("command_revision", 4),
        ("input_token", "next-raw"),
        ("session_id", ""),
        ("session_id", []),
        ("session_id", "x" * 257),
        ("session_id", "\udfff"),
        ("command_revision", -1),
        ("command_revision", True),
        ("command_revision", 3.0),
        ("command_revision", 1 << 63),
        ("input_token", None),
        ("input_token", "x" * 257),
        ("input_token", "\ud800"),
        ("input_revision", 3),
        ("input_revision", None),
        ("input_revision", -1),
        ("input_revision", True),
        ("input_revision", 2.0),
        ("input_revision", 1 << 63),
    ],
)
def test_changed_or_malformed_binding_is_unavailable(field, value):
    candidate = request()
    snapshot = diagnostics.FailureDiagnostics(failure(candidate), candidate, **bindings())
    current = {**bindings(), field: value}
    assert snapshot.for_current(candidate, **current) is None
    if (field, value) not in [
        ("session_id", "other-owner"),
        ("command_revision", 4),
        ("input_token", "next-raw"),
        ("input_revision", 3),
        ("input_revision", None),
    ]:
        with pytest.raises(Error):
            diagnostics.FailureDiagnostics(failure(candidate), candidate, **current)


def test_initial_empty_input_token_and_utf8_text_are_exact_and_valid():
    candidate = request()
    candidate["document"].update(id="pièce", name="輪郭")
    response = failure(candidate)
    response["error"]["message"] = "Échec de résolution 🧩"
    current = {**bindings(), "session_id": "session-輪", "input_token": "", "input_revision": None}
    snapshot = diagnostics.FailureDiagnostics(response, candidate, **current)
    assert snapshot.document_id == "pièce"
    assert snapshot.error_message == "Échec de résolution 🧩"
    assert snapshot.for_current(candidate, **current) is snapshot
    assert snapshot.for_current(candidate, **{**current, "input_token": "new"}) is None


def test_raw_input_a_to_b_to_a_never_revives_old_diagnostics_with_same_lease_and_request():
    candidate = request()
    snapshot = diagnostics.FailureDiagnostics(failure(candidate), candidate, **bindings())
    assert snapshot.for_current(candidate, **{**bindings(), "input_revision": 4}) is None
    assert snapshot.for_current(candidate, **{**bindings(), "input_revision": None}) is None


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["document"].update(name="Changed"),
        lambda r: r["document"]["parameters"].update(radius_mm=6),
        lambda r: r.update(feature_id="other"),
        lambda r: r["document"]["features"][0].update(id="other"),
        lambda r: r["document"]["features"][0]["sketch"].update(id="other"),
        lambda r: r["document"]["features"][0]["sketch"]["points"][0].update(u=4),
        lambda r: r["document"]["features"][0]["sketch"]["circles"][0].update(radius=8),
        lambda r: r["document"]["features"][0]["sketch"]["constraints"][0].update(id="other"),
        lambda r: r["document"]["features"][0]["sketch"]["constraints"][0].update(
            value="radius_mm + 0"
        ),
        lambda r: r["document"]["features"][0]["sketch"]["constraints"][0].update(refs=["other"]),
        lambda r: r["document"]["features"][0]["sketch"]["constraints"][-1].update(target=[0, 0]),
        lambda r: r["document"]["features"][0]["sketch"]["constraints"].reverse(),
    ],
)
def test_any_changed_exact_request_or_source_binding_is_unavailable(change):
    candidate = request()
    response = failure(candidate)
    snapshot = diagnostics.FailureDiagnostics(response, candidate, **bindings())
    change(candidate)
    assert snapshot.for_current(candidate, **bindings()) is None
    with pytest.raises(Error):
        diagnostics.FailureDiagnostics(response, candidate, **bindings())


def test_canonical_equivalence_cannot_rebind_the_raw_failed_request():
    candidate = request()
    snapshot = diagnostics.FailureDiagnostics(failure(candidate), candidate, **bindings())
    canonical = {**candidate, "document": contracts._expected_document(candidate["document"])}
    assert canonical != candidate
    assert contracts.document_hash(canonical["document"]) == snapshot.document_hash
    assert snapshot.for_current(canonical, **bindings()) is None


def hostile(kind):
    value = {}
    if kind == "cycle":
        value["cycle"] = value
    elif kind == "depth":
        for _ in range(66):
            value = {"child": value}
    elif kind == "dag":
        for _ in range(26):
            value = {"a": value, "b": value}
    elif kind == "large_text":
        value = {"text": "x" * (2 * 1024 * 1024)}
    elif kind == "non_json":
        value = {"value": object()}
    elif kind == "integer":
        value = {"value": 1 << 20000}
    return value


@pytest.mark.parametrize("kind", ["cycle", "depth", "dag", "large_text", "non_json", "integer"])
def test_resource_or_non_json_inputs_fail_before_unsafe_copy_or_encoding(kind):
    candidate = request()
    response = failure(candidate)
    snapshot = diagnostics.FailureDiagnostics(response, candidate, **bindings())
    bad = hostile(kind)
    with pytest.raises(Error):
        diagnostics.FailureDiagnostics(response, bad, **bindings())
    assert snapshot.for_current(bad, **bindings()) is None
    with pytest.raises(Error):
        diagnostics.FailureDiagnostics(bad, candidate, **bindings())


def test_invalid_utf8_anywhere_in_authored_source_is_rejected():
    candidate = request()
    candidate["document"]["name"] = "\ud800"
    response = failure(candidate)
    # The existing fingerprint encoder's ASCII escaping is not UTF-8 validation.
    diagnostics.sketch_action_bridge.validate_solve_response(response, candidate)
    with pytest.raises(Error):
        diagnostics.FailureDiagnostics(response, candidate, **bindings())


def test_legacy_embedded_v1_failure_uses_the_same_explicit_solve_v2_boundary():
    candidate = request()
    source = candidate["document"]["features"][0]["sketch"]
    source.update(
        schema_version=1,
        points=[{"id": "a", "u": 0, "v": 0}, {"id": "b", "u": 5, "v": 0}],
        lines=[{"id": "edge", "start": "a", "end": "b"}],
        constraints=[
            {"id": "length", "kind": "distance", "refs": ["a", "b"], "value": 5},
            {"id": "other", "kind": "distance", "refs": ["a", "b"], "value": 6},
        ],
    )
    source.pop("circles")
    response = failure(candidate, candidates=("length", "other"))
    response["result"]["sketch"]["dimensions"] = {"length": 5, "other": 6}
    snapshot = diagnostics.FailureDiagnostics(response, candidate, **bindings())
    assert snapshot.candidate_constraint_ids == ("length", "other")
    assert snapshot.for_current(candidate, **bindings()) is snapshot


def test_real_native_failed_solve_and_exact_duplicate_diagnostics_are_preserved():
    pytest.importorskip("slvs")
    from mechanical_cad.sidecar import process_request

    candidate = request()
    source = candidate["document"]["features"][0]["sketch"]
    source["constraints"].append({**source["constraints"][0], "id": "radius_copy"})
    response = process_request(candidate)
    assert not response["ok"] and response["result"] is not None
    report = response["result"]["sketch"]
    assert report["status"] in {"inconsistent", "didnt_converge"}
    assert report["solved"] is None and report["remaining_dof"] is None
    snapshot = diagnostics.FailureDiagnostics(response, candidate, **bindings())
    assert snapshot.candidate_constraint_ids == tuple(report["failed_constraints"])
    assert snapshot.redundant_constraint_ids == tuple(report["redundant_constraints"])
    assert snapshot.redundant_constraint_ids == ("radius_copy",)
    assert snapshot.for_current(candidate, **bindings()) is snapshot


def test_diagnostics_import_and_construction_are_native_free():
    candidate = request()
    response = failure(candidate)
    code = f"""
import builtins, importlib, sys, types
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}:
        raise AssertionError('forbidden dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
package = types.ModuleType('native_free_diagnostics')
package.__path__ = [{str(ADDON)!r}]
sys.modules[package.__name__] = package
module = importlib.import_module(package.__name__ + '.constraint_diagnostics')
snapshot = module.FailureDiagnostics({response!r}, {candidate!r}, **{bindings()!r})
assert snapshot.for_current({candidate!r}, **{bindings()!r}) is snapshot
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
