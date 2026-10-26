"""Independent client contract mutations; no server capability helper is imported."""

import copy
import hashlib
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_backend_contract_client_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
client = importlib.import_module(PACKAGE + ".backend_contracts")
selection_module = importlib.import_module(PACKAGE + ".backend_selection")


def operation(action="replay", result_version=2):
    result = {"protocol_version": 1, "action": action, "document": {"schema_version": 1}}
    if action.startswith("assembly_"):
        result["kind"] = "assembly"
    if action != "canonical_snapshot":
        result["result_version"] = result_version
    return result


def selection():
    return selection_module.BackendSelection.capture(
        str(ROOT), sys.executable, generation=1, lifetime_id="lifetime", environment={}
    )


def receipt_response(guarded, *, rejected=False):
    required = guarded["backend_contract"]["required_capabilities"]
    selected = selection()
    return {
        "protocol_version": 1,
        "ok": not rejected,
        "result": None,
        "error": {"code": "backend_capability_missing", "message": "Unavailable."}
        if rejected
        else None,
        "backend_receipt": {
            "version": 1,
            "request_id": guarded["backend_contract"]["request_id"],
            "request_fingerprint": hashlib.sha256(
                json.dumps(guarded, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            ).hexdigest(),
            "required_capabilities": list(required),
            "confirmed_capabilities": [] if rejected else list(required),
            "missing_capabilities": list(required) if rejected else [],
            "phase": "rejected_before_dispatch" if rejected else "dispatched",
            "backend": {
                "core_version": "0.5.1",
                "project_root": str(ROOT),
                "core_origin": str(ROOT / "src/mechanical_cad"),
                "solver_origin": None
                if rejected or guarded["action"] == "canonical_snapshot"
                else str(ROOT / "src/mechanical_cad/sketch_solver.py"),
                "python_executable": selected.python_executable,
                "python_executable_target": selected.python_executable_target,
                "python_prefix": "/diagnostic/not-inferred",
                "python_base_prefix": "/diagnostic/base",
                "python_version": [3, 12, 14],
            },
        },
    }


@pytest.mark.parametrize("action", sorted(client.ACTIONS))
def test_all_actions_require_baseline_and_explicit_solver_minimum(action):
    prepared = client.prepare_request(operation(action))
    required = prepared.guarded_request()["backend_contract"]["required_capabilities"]
    expected = (
        [client.BASELINE]
        if action == "canonical_snapshot"
        else [client.BASELINE, client.SOLVER_GUARD]
    )
    if action == "assembly_export_step":
        with pytest.raises(client.BackendContractError):
            client.prepare_request(operation(action), required_capabilities=expected)
        expected = sorted([*expected, client.ASSEMBLY_STEP_EXPORT])
    if action == "edge_catalog":
        # 538f1a8 and ADR 0002 make catalog observation a separate capability.
        with pytest.raises(client.BackendContractError):
            client.prepare_request(operation(action), required_capabilities=expected)
        expected = sorted([*expected, "mcad.edge-catalog/1"])
    assert required == expected
    assert prepared.operation_request() == operation(action)
    assert len(prepared.payload) <= client.MAX_GUARDED_REQUEST_BYTES
    if action != "canonical_snapshot":
        with pytest.raises(client.BackendContractError):
            client.prepare_request(operation(action), required_capabilities=[client.BASELINE])


def test_fresh_nonce_and_independent_type_sensitive_full_and_inner_fingerprints():
    ordinary = operation()
    ordinary["raw"] = [1, 1.0, True, -0.0, "  width + 1  ", "\U0001f600"]
    first, second = client.prepare_request(ordinary), client.prepare_request(ordinary)
    assert first.request_id != second.request_id
    assert first.fingerprint != second.fingerprint
    assert first.operation_request() == ordinary
    assert (
        first.fingerprint
        == hashlib.sha256(
            json.dumps(first.guarded_request(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    original = first.guarded_request()
    for replacement in [1.0, True, -0.0, 0.0]:
        changed = copy.deepcopy(original)
        changed["raw"][0] = replacement
        assert client.request_fingerprint(changed) != first.fingerprint
    ordinary["raw"].append("caller mutation")
    detached = first.operation_request()
    detached["raw"].append("projection mutation")
    assert len(first.operation_request()["raw"]) == 6
    with pytest.raises((AttributeError, TypeError)):
        first.payload = b"{}"


@pytest.mark.parametrize("version", [None, True, False, 1, 2.0, "2", 4])
def test_guarded_result_requires_explicit_exact_2_or_3(version):
    raw = operation(result_version=version)
    if version is None:
        raw.pop("result_version")
    with pytest.raises(client.BackendContractError):
        client.prepare_request(raw)


@pytest.mark.parametrize(
    "action,additional",
    [
        ("solve_sketch", {"mcad.solve-result/3"}),
        ("replay", {"mcad.part-result/3"}),
        ("check_geometry", {"mcad.part-result/3", "mcad.geometry-result/3"}),
        ("export_step", {"mcad.part-result/3", "mcad.geometry-result/3"}),
        ("export_stl", {"mcad.part-result/3", "mcad.geometry-result/3"}),
        ("assembly_replay", {"mcad.part-result/3", "mcad.assembly-result/3"}),
        ("assembly_check", {"mcad.part-result/3", "mcad.assembly-result/3"}),
        ("assembly_sample", {"mcad.part-result/3", "mcad.assembly-result/3"}),
    ],
)
def test_explicit_result3_uses_whole_arc_family_even_for_primitive_data(action, additional):
    assert (
        set(client.minimum_capabilities(operation(action, 3)))
        == {client.BASELINE, client.SOLVER_GUARD, client.SKETCH_ARCS} | additional
    )


def test_every_feature_and_assembly_source_is_scanned_including_empty_arc_arrays():
    raw = operation("assembly_replay")
    raw["assembly"] = {
        "assembly_schema_version": 1,
        "part_sources": [
            {
                "document": {
                    "schema_version": 2,
                    "features": [
                        {"sketch": {"schema_version": 1}},
                        {"sketch": {"schema_version": 3, "arcs": []}},
                    ],
                }
            }
        ],
    }
    with pytest.raises(client.BackendContractError, match="Schema-3"):
        client.prepare_request(raw)
    raw["result_version"] = 3
    assert "mcad.assembly-result/3" in client.minimum_capabilities(raw)
    for bad in [True, "3", 3.0, 4]:
        raw["assembly"]["part_sources"][0]["document"]["features"][1]["sketch"][
            "schema_version"
        ] = bad
        with pytest.raises(client.BackendContractError, match="schema"):
            client.prepare_request(raw)
    snapshot = operation("canonical_snapshot")
    snapshot["document"]["features"] = [{"sketch": {"schema_version": 3, "arcs": []}}]
    assert client.minimum_capabilities(snapshot) == [client.BASELINE, client.SNAPSHOT_SKETCH3]
    snapshot["result_version"] = 3
    with pytest.raises(client.BackendContractError):
        client.prepare_request(snapshot)


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c.update(version=True),
        lambda c: c.update(version=1.0),
        lambda c: c.update(version="1"),
        lambda c: c.update(version=2),
        lambda c: c.update(extra=None),
        lambda c: c.pop("version"),
        lambda c: c.update(request_id="A" * 32),
        lambda c: c.update(request_id="0" * 31),
        lambda c: c.update(required_capabilities=[]),
        lambda c: c.update(required_capabilities=[client.SOLVER_GUARD, client.BASELINE]),
        lambda c: c.update(required_capabilities=[client.BASELINE, client.BASELINE]),
        lambda c: c.update(required_capabilities=[" MCAD.guard"]),
        lambda c: c.update(required_capabilities=["x" * 97]),
    ],
)
def test_malformed_contract_fields_fail_closed(change):
    guarded = client.compose_request(operation())
    change(guarded["backend_contract"])
    with pytest.raises(client.BackendContractError):
        client.validate_request(guarded)


@pytest.mark.parametrize("path", ["document", "options", "requirements", "nested"])
def test_transport_metadata_never_enters_authored_or_nested_operation_data(path):
    raw = operation()
    raw[path] = {"data": [{"backend_contract": {}}]}
    with pytest.raises(client.BackendContractError, match="Nested"):
        client.prepare_request(raw)


def test_operation_exact_default_json_byte_boundary_and_unicode_expansion():
    raw = operation()
    raw["padding"] = ""
    budget = client.request_contracts.MAX_DOCUMENT_BYTES
    overhead = len(json.dumps(raw).encode())
    raw["padding"] = "x" * (budget - overhead)
    prepared = client.prepare_request(raw)
    assert len(json.dumps(prepared.operation_request()).encode()) == budget
    assert len(prepared.payload) > budget
    raw["padding"] += "x"
    with pytest.raises(client.BackendContractError):
        client.prepare_request(raw)
    raw["padding"] = "\u00e9" * ((budget - overhead) // 6 + 1)
    with pytest.raises(client.BackendContractError):
        client.prepare_request(raw)


def test_contract_36_nodes_and_4k_wrapper_budget_are_separate_from_operation():
    names = sorted([client.BASELINE, client.SOLVER_GUARD] + [f"x/{i:02}" for i in range(30)])
    guarded = client.compose_request(operation(), required_capabilities=names)
    assert len(guarded["backend_contract"]["required_capabilities"]) == 32
    assert len(json.dumps({"backend_contract": guarded["backend_contract"]}).encode()) < 4096
    guarded["backend_contract"]["required_capabilities"].append("x/99")
    with pytest.raises(client.BackendContractError):
        client.validate_request(guarded)
    guarded["backend_contract"] = {"padding": "x" * 4096}
    with pytest.raises(client.BackendContractError):
        client.validate_request(guarded)


def test_request_cycles_shared_expansion_integer_and_depth_limits():
    raw = operation()
    raw["cycle"] = raw
    with pytest.raises(client.BackendContractError):
        client.prepare_request(raw)
    raw = operation()
    dag = [0]
    for _ in range(25):
        dag = [dag, dag]
    raw["shared"] = dag
    with pytest.raises(client.BackendContractError):
        client.prepare_request(raw)
    raw = operation()
    raw["huge"] = 1 << 16384
    with pytest.raises(client.BackendContractError):
        client.prepare_request(raw)
    raw = operation()
    nested = 0
    for _ in range(64):
        nested = [nested]
    raw["nested"] = nested
    with pytest.raises(client.BackendContractError):
        client.prepare_request(raw)
    raw["nested"] = nested[0]
    assert client.prepare_request(raw)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(version=True),
        lambda r: r.update(version=1.0),
        lambda r: r.update(request_id="0" * 32),
        lambda r: r.update(request_fingerprint="f" * 64),
        lambda r: r.update(extra=1),
        lambda r: r.pop("phase"),
        lambda r: r.update(phase="success"),
        lambda r: r.update(phase=True),
        lambda r: r.update(confirmed_capabilities=[client.BASELINE]),
        lambda r: r.update(missing_capabilities=[client.SOLVER_GUARD]),
        lambda r: r["confirmed_capabilities"].append("x/invented"),
        lambda r: r["backend"].update(extra=1),
        lambda r: r["backend"].pop("python_prefix"),
        lambda r: r["backend"].update(python_version=[3, True, 0]),
        lambda r: r["backend"].update(python_version=[3, 12, 1001]),
        lambda r: r["backend"].update(python_version=[3, 12]),
        lambda r: r["backend"].update(core_version=""),
        lambda r: r["backend"].update(core_version="x" * 65),
        lambda r: r["backend"].update(python_prefix="relative"),
        lambda r: r["backend"].update(python_prefix=None),
        lambda r: r["backend"].update(python_prefix="/" + "x" * 4096),
        lambda r: r["backend"].update(python_prefix="/nul\0bad"),
        lambda r: r["backend"].update(solver_origin=None),
        lambda r: r["backend"].update(core_origin=str(ROOT)),
        lambda r: r["backend"].update(solver_origin=sys.executable),
        lambda r: r["backend"].update(project_root=str(ROOT.parent)),
        lambda r: r["backend"].update(python_executable="/different/python"),
        lambda r: r["backend"].update(python_executable_target="/bin/sh"),
    ],
)
def test_receipt_mutations_reject(change):
    guarded = client.compose_request(operation())
    response = receipt_response(guarded)
    change(response["backend_receipt"])
    with pytest.raises(client.BackendContractError):
        client.validate_receipt(guarded, response, selection())


def test_receipt_diagnostics_are_observations_and_rejected_null_solver_is_valid():
    guarded = client.compose_request(operation())
    response = receipt_response(guarded)
    accepted = client.validate_receipt(guarded, response, selection())
    assert accepted["backend"]["python_prefix"] == "/diagnostic/not-inferred"
    response["backend_receipt"]["backend"]["python_prefix"] = "/changed"
    assert accepted["backend"]["python_prefix"] != "/changed"
    rejected = receipt_response(guarded, rejected=True)
    assert (
        client.validate_receipt(guarded, rejected, selection())["phase"]
        == "rejected_before_dispatch"
    )
    rejected["result_version"] = 2
    with pytest.raises(client.BackendContractError):
        client.validate_receipt(guarded, rejected, selection())


def test_snapshot_null_solver_is_exact_and_missing_receipt_never_accepted():
    guarded = client.compose_request(operation("canonical_snapshot"))
    response = receipt_response(guarded)
    assert client.validate_receipt(guarded, response, selection())
    response["backend_receipt"]["backend"]["solver_origin"] = str(
        ROOT / "src/mechanical_cad/sketch_solver.py"
    )
    with pytest.raises(client.BackendContractError):
        client.validate_receipt(guarded, response, selection())
    response.pop("backend_receipt")
    with pytest.raises(client.BackendContractError) as error:
        client.validate_receipt(guarded, response, selection())
    assert error.value.code == "backend_contract_unavailable"


def test_same_base_binary_in_another_venv_is_not_same_invocation(tmp_path):
    first, second = tmp_path / "first-python", tmp_path / "second-python"
    first.symlink_to(sys.executable)
    second.symlink_to(sys.executable)
    selected = selection_module.BackendSelection.capture(
        str(ROOT), str(first), generation=1, lifetime_id="lifetime", environment={}
    )
    guarded = client.compose_request(operation())
    response = receipt_response(guarded)
    response["backend_receipt"]["backend"]["python_executable"] = str(first)
    assert client.validate_receipt(guarded, response, selected)
    response["backend_receipt"]["backend"]["python_executable"] = str(second)
    with pytest.raises(client.BackendContractError) as error:
        client.validate_receipt(guarded, response, selected)
    assert error.value.code == "backend_identity_mismatch"


def test_metadata_response_budget_is_independent_of_total_response_budget():
    guarded = client.compose_request(operation())
    response = receipt_response(guarded)
    # Paths remain individually <=4096 characters but ASCII escaping makes the
    # bounded diagnostic metadata exceed 64KiB before any filesystem lookup.
    for field in ("project_root", "core_origin", "python_executable", "python_prefix"):
        response["backend_receipt"]["backend"][field] = "/" + "\u00e9" * 4094
    with pytest.raises(client.BackendContractError):
        client.validate_receipt(guarded, response, selection())


@pytest.mark.parametrize(
    "action,kind",
    [
        ("canonical_snapshot", "assembly"),
        ("replay", "assembly"),
        ("assembly_replay", None),
        ("assembly_check", "part"),
    ],
)
def test_cross_family_dispatch_cannot_bypass_pure_snapshot_or_solver_policy(action, kind):
    raw = operation(action)
    if kind is None:
        raw.pop("kind", None)
    else:
        raw["kind"] = kind
    with pytest.raises(client.BackendContractError):
        client.prepare_request(raw)
