"""Independent server admission, resource edges, and unchanged operation identities."""

import ast
import copy
import hashlib
import json
import os
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from mechanical_cad import backend_contract as bc
from mechanical_cad import sidecar, sketch_solver
from mechanical_cad.errors import CADException
from mechanical_cad.part_snapshot import input_fingerprint
from mechanical_cad.sketch_model import Constraint
from mechanical_cad.sketch_relations import SYMMETRIC_RELATIONS

ROOT = Path(__file__).resolve().parents[2]
PROJECT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
BASELINE = "mcad.backend-contract/1"
GUARD = "mcad.solver-dof-cycle-guard/1"
NONCE = "0123456789abcdef0123456789abcdef"
ACTIONS = (
    "replay",
    "canonical_snapshot",
    "solve_sketch",
    "check_geometry",
    "export_step",
    "export_stl",
    "assembly_replay",
    "assembly_check",
    "assembly_sample",
)


def ordinary(action="replay"):
    request = {"protocol_version": 1, "action": action, "document": None}
    if action != "canonical_snapshot":
        request["result_version"] = 2
    if action == "solve_sketch":
        request["feature_id"] = "sketch"
    if action.startswith("assembly_"):
        request.pop("document")
        request.update(kind="assembly", assembly_protocol_version=1, assembly=None)
    if action.startswith("export_"):
        request["destination"] = "/unused/part.step"
    return request


def guarded(action="replay", *, extra=()):
    required = [BASELINE] if action == "canonical_snapshot" else [BASELINE, GUARD]
    return {
        **ordinary(action),
        "backend_contract": {
            "version": 1,
            "request_id": NONCE,
            "required_capabilities": sorted([*required, *extra]),
        },
    }


def compact_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@pytest.fixture(autouse=True)
def selected_root(monkeypatch):
    monkeypatch.chdir(ROOT)


@pytest.mark.parametrize("action", ACTIONS)
def test_unknown_capability_rejects_all_nine_actions_before_dispatch(action, monkeypatch):
    called = []
    monkeypatch.setattr(sidecar, "_process_legacy_request", lambda value: called.append(value))
    request = guarded(action, extra=("unavailable/1",))
    response = sidecar.process_request(request)
    assert called == []
    assert set(response) == {"protocol_version", "ok", "result", "error", "backend_receipt"}
    assert response["ok"] is False and response["result"] is None
    assert response["error"]["code"] == "backend_capability_missing"
    receipt = response["backend_receipt"]
    assert receipt["phase"] == "rejected_before_dispatch"
    assert receipt["missing_capabilities"] == ["unavailable/1"]
    assert receipt["confirmed_capabilities"] == (
        [BASELINE] if action == "canonical_snapshot" else [BASELINE, GUARD]
    )
    assert receipt["request_fingerprint"] == compact_hash(request)


@pytest.mark.parametrize("action", ACTIONS)
def test_each_action_admits_exact_detached_operation_and_receipts_failure(action, monkeypatch):
    request = guarded(action)
    before = copy.deepcopy(request)
    calls = []

    def dispatch(operation):
        calls.append(operation)
        assert "backend_contract" not in operation
        raise CADException("original_error", "Preserve this exact action error.")

    monkeypatch.setattr(sidecar, "_process_legacy_request", dispatch)
    response = sidecar.process_request(request)
    assert len(calls) == 1 and calls[0] == ordinary(action)
    assert calls[0] is not request and request == before
    assert response["backend_receipt"]["phase"] == "dispatched"
    assert response["backend_receipt"]["missing_capabilities"] == []
    assert response["error"] == {
        "code": "original_error",
        "message": "Preserve this exact action error.",
    }
    assert ("result_version" in response) == (action != "canonical_snapshot")


@pytest.mark.parametrize(
    "contract",
    [
        None,
        {},
        [],
        {"version": 1},
        {"version": True, "request_id": NONCE, "required_capabilities": [BASELINE, GUARD]},
        {"version": 1.0, "request_id": NONCE, "required_capabilities": [BASELINE, GUARD]},
        {"version": 2, "request_id": NONCE, "required_capabilities": [BASELINE, GUARD]},
    ],
)
def test_malformed_presence_never_selects_legacy(contract, monkeypatch):
    monkeypatch.setattr(sidecar, "_process_legacy_request", lambda _: pytest.fail("dispatched"))
    request = guarded()
    request["backend_contract"] = contract
    response = sidecar.process_request(request)
    assert response["error"]["code"] == "backend_contract_invalid"
    assert "backend_receipt" not in response and "result_version" not in response


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "uppercase_nonce",
        "short_nonce",
        "cap_tuple",
        "cap_empty",
        "cap_duplicate",
        "cap_unsorted",
        "cap_number",
        "cap_uppercase",
        "cap_space",
        "cap_unicode",
        "cap_newline",
        "cap_long",
        "cap_count",
        "missing_baseline",
        "missing_guard",
    ],
)
def test_contract_mutations_fail_before_implementation_import(change, monkeypatch):
    request = guarded()
    contract = request["backend_contract"]
    if change == "unknown":
        contract["extra"] = True
    elif change == "uppercase_nonce":
        contract["request_id"] = NONCE.upper()
    elif change == "short_nonce":
        contract["request_id"] = NONCE[:-1]
    elif change == "cap_tuple":
        contract["required_capabilities"] = (BASELINE, GUARD)
    elif change == "cap_empty":
        contract["required_capabilities"] = []
    elif change == "cap_duplicate":
        contract["required_capabilities"] = [BASELINE, BASELINE, GUARD]
    elif change == "cap_unsorted":
        contract["required_capabilities"].reverse()
    elif change == "cap_count":
        contract["required_capabilities"] = [f"a/{i:02}" for i in range(33)]
    elif change == "missing_baseline":
        contract["required_capabilities"] = [GUARD]
    elif change == "missing_guard":
        contract["required_capabilities"] = [BASELINE]
    else:
        invalid = {
            "cap_number": 2,
            "cap_uppercase": "MCAD/1",
            "cap_space": " mcad/1",
            "cap_unicode": "mçad/1",
            "cap_newline": "mcad/1\n",
            "cap_long": "x" * 97,
        }[change]
        contract["required_capabilities"] = [BASELINE, GUARD, invalid]
    monkeypatch.setattr(bc, "observe_backend", lambda _: pytest.fail("observed implementation"))
    assert sidecar.process_request(request)["error"]["code"] == "backend_contract_invalid"


@pytest.mark.parametrize("version", [None, 1, True, 2.0, "2", 0, 4])
def test_guarded_result_one_or_unknown_never_dispatches(version, monkeypatch):
    request = guarded()
    if version is None:
        request.pop("result_version")
    else:
        request["result_version"] = version
    monkeypatch.setattr(bc, "observe_backend", lambda _: pytest.fail("imported implementation"))
    assert sidecar.process_request(request)["error"]["code"] == "backend_contract_invalid"


@pytest.mark.parametrize("action", ACTIONS)
def test_arc_family_minimum_admits_only_complete_supported_actions(action, monkeypatch):
    request = guarded(action)
    operation = {key: value for key, value in request.items() if key != "backend_contract"}
    document = {"schema_version": 2, "features": [{"sketch": {"schema_version": 3, "arcs": []}}]}
    if action.startswith("assembly_"):
        operation["assembly"] = {"schema_version": 1, "part_sources": [{"document": document}]}
    else:
        operation["document"] = document
    if action != "canonical_snapshot":
        operation["result_version"] = 3
    expected = {BASELINE}
    if action == "canonical_snapshot":
        expected.add("mcad.snapshot-sketch3/1")
    else:
        expected |= {GUARD, "mcad.sketch-arcs/1"}
        if action == "solve_sketch":
            expected.add("mcad.solve-result/3")
        else:
            expected.add("mcad.part-result/3")
            if action.startswith("assembly_"):
                expected.add("mcad.assembly-result/3")
            elif action != "replay":
                expected.add("mcad.geometry-result/3")
    assert bc.minimum_capabilities(operation) == expected
    request = {**operation, "backend_contract": request["backend_contract"]}
    request["backend_contract"]["required_capabilities"] = sorted(expected)
    calls = []
    monkeypatch.setattr(
        sidecar, "_process_legacy_request", lambda value: calls.append(value) or {"ok": True}
    )
    response = sidecar.process_request(request)
    # This dispatch stub establishes capability observation, not source admission.
    assert calls == [operation]
    assert response["backend_receipt"]["phase"] == "dispatched"
    assert set(response["backend_receipt"]["confirmed_capabilities"]) == expected
    if action != "canonical_snapshot":
        assert response["result_version"] == 3
    else:
        assert "result_version" not in response


@pytest.mark.parametrize("action", ["replay", "assembly_replay"])
def test_scan_inactive_later_features_and_every_embedded_source(action):
    request = ordinary(action)
    first = {"schema_version": 2, "features": [{"sketch": {"schema_version": 2}}]}
    last = {
        "schema_version": 2,
        "active_feature": "first",
        "features": [
            {"id": "first", "sketch": {"schema_version": 2}},
            {"id": "unused", "sketch": {"schema_version": 3, "arcs": []}},
        ],
    }
    if action.startswith("assembly_"):
        request["assembly"] = {"part_sources": [{"document": first}, {"document": last}]}
    else:
        request["document"] = last
    with pytest.raises(CADException, match="requires explicit result"):
        bc.minimum_capabilities(request)


@pytest.mark.parametrize("location", ["document", "options", "assembly", "requirements", "unknown"])
def test_nested_contract_is_never_authored_data(location):
    request = guarded()
    request[location] = {"nested": [{"backend_contract": {}}]}
    assert sidecar.process_request(request)["error"]["code"] == "backend_contract_invalid"


@pytest.mark.parametrize("marker", [None, [], {GUARD}, frozenset(), frozenset({"other/1"})])
def test_old_or_malformed_actual_adapter_cannot_be_relabelled(marker, monkeypatch):
    monkeypatch.setattr(sketch_solver, "BACKEND_CAPABILITIES", marker)
    response = sidecar.process_request(guarded())
    receipt = response["backend_receipt"]
    assert response["error"]["code"] == "backend_capability_missing"
    assert receipt["missing_capabilities"] == [GUARD]
    assert receipt["backend"]["solver_origin"] == str(Path(sketch_solver.__file__).resolve())


def test_missing_adapter_has_null_origin_before_dispatch(monkeypatch):
    def missing(*args):
        raise ImportError("old installation has no adapter")

    monkeypatch.setattr(bc.importlib, "import_module", missing)
    response = sidecar.process_request(guarded())
    assert response["backend_receipt"]["backend"]["solver_origin"] is None
    assert response["backend_receipt"]["missing_capabilities"] == [GUARD]


def test_snapshot_unneeded_solver_requirement_does_not_import_adapter(monkeypatch):
    monkeypatch.setattr(bc.importlib, "import_module", lambda *args: pytest.fail("imported solver"))
    response = sidecar.process_request(guarded("canonical_snapshot", extra=(GUARD,)))
    assert response["error"]["code"] == "backend_capability_missing"
    assert response["backend_receipt"]["backend"]["solver_origin"] is None


def test_import_identity_is_actual_and_foreign_solver_is_rejected(monkeypatch):
    foreign = SimpleNamespace(
        __file__=str(ROOT / "README.md"), BACKEND_CAPABILITIES=frozenset({GUARD})
    )
    monkeypatch.setattr(bc.importlib, "import_module", lambda *args: foreign)
    response = sidecar.process_request(guarded())
    assert response["error"]["code"] == "backend_identity_mismatch"
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch"
    assert response["backend_receipt"]["backend"]["solver_origin"] == str(ROOT / "README.md")


def test_wrong_launch_root_rejects_with_actual_identity_receipt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = sidecar.process_request(guarded("canonical_snapshot"))
    assert response["error"]["code"] == "backend_identity_mismatch"
    assert response["backend_receipt"]["backend"]["project_root"] == str(tmp_path)


def test_identity_reports_real_runtime_and_does_not_guess_dependency_versions():
    identity, supported, mismatch = bc.observe_backend(ordinary())
    assert mismatch is False and supported == {BASELINE, GUARD}
    assert identity == {
        "core_version": PROJECT_VERSION,
        "project_root": str(ROOT),
        "core_origin": str(ROOT / "src/mechanical_cad"),
        "solver_origin": str(ROOT / "src/mechanical_cad/sketch_solver.py"),
        "python_executable": os.path.abspath(sys.executable),
        "python_executable_target": str(Path(sys.executable).resolve()),
        "python_prefix": str(Path(sys.prefix).resolve()),
        "python_base_prefix": str(Path(sys.base_prefix).resolve()),
        "python_version": list(sys.version_info[:3]),
    }


@pytest.mark.parametrize("value", [1, 1.0, True, -0.0, 0.0])
def test_full_and_inner_fingerprints_preserve_exact_numeric_types(value):
    request = guarded("canonical_snapshot")
    request["document"] = {"value": value}
    prepared = bc.prepare_request(request)
    assert prepared.request_fingerprint == compact_hash(request)
    assert input_fingerprint(prepared.operation) == compact_hash(
        ordinary("canonical_snapshot") | {"document": {"value": value}}
    )
    assert prepared.request_fingerprint != input_fingerprint(prepared.operation)


def test_nonce_and_requirements_change_outer_identity_only_and_detach_inputs():
    request = guarded("canonical_snapshot")
    request["document"] = {"parameters": {"length": " 2 + 3 "}, "values": [-0.0, 1, 1.0, True]}
    first = bc.prepare_request(request)
    request["backend_contract"]["request_id"] = "f" * 32
    second = bc.prepare_request(request)
    assert first.request_fingerprint != second.request_fingerprint
    assert input_fingerprint(first.operation) == input_fingerprint(second.operation)
    request["document"]["values"].append(99)
    assert first.operation["document"]["values"] == [-0.0, 1, 1.0, True]


def test_default_encoding_operation_byte_edge_is_independent_of_metadata():
    request = guarded("canonical_snapshot")
    request["document"] = ""
    size = len(
        json.dumps(
            {key: value for key, value in request.items() if key != "backend_contract"}
        ).encode()
    )
    request["document"] = "x" * (bc.MAX_OPERATION_BYTES - size)
    prepared = bc.prepare_request(request)
    assert len(json.dumps(prepared.operation).encode()) == bc.MAX_OPERATION_BYTES
    assert len(json.dumps(request).encode()) > bc.MAX_OPERATION_BYTES
    request["document"] += "x"
    with pytest.raises(CADException) as exc:
        bc.prepare_request(request)
    assert exc.value.code == "document_too_large"


@pytest.mark.parametrize("text", ['"\\\n\t', "é", "🚀", "\ud800"])
def test_exact_ascii_escaping_and_separator_byte_accounting(text):
    value = {"v": [text, -0.0, 1.0, True, None]}
    size = len(json.dumps(value, allow_nan=False).encode())
    assert bc.snapshot_json(value, max_bytes=size, max_nodes=99, max_depth=3) == value
    with pytest.raises(CADException):
        bc.snapshot_json(value, max_bytes=size - 1, max_nodes=99, max_depth=3)


def test_exact_contract_node_and_member_overhead_budgets():
    request = guarded()
    names = sorted([BASELINE, GUARD] + [f"x/{i:02}/" + "a" * 89 for i in range(30)])
    request["backend_contract"]["required_capabilities"] = names
    contract = request["backend_contract"]
    assert len(names) == 32 and all(len(name) <= 96 for name in names)
    size = len(json.dumps({"backend_contract": contract}).encode())
    assert size <= 4096
    assert bc.prepare_request(request).contract == contract
    assert bc.snapshot_json(contract, max_bytes=4096, max_nodes=36, max_depth=2) == contract
    with pytest.raises(CADException):
        bc.snapshot_json(contract, max_bytes=4096, max_nodes=35, max_depth=2)
    wrapper = {"backend_contract": contract}
    assert bc.snapshot_json(wrapper, max_bytes=size, max_nodes=37, max_depth=3) == wrapper
    with pytest.raises(CADException):
        bc.snapshot_json(wrapper, max_bytes=size - 1, max_nodes=37, max_depth=3)


def test_expanded_nodes_depth_and_shared_dags_remain_independent():
    shared = [0] * 10
    value = {"a": shared, "b": shared}  # 1 + 11 + 11 = 23 value/container nodes.
    detached = bc.snapshot_json(value, max_bytes=1000, max_nodes=23, max_depth=2)
    assert detached == value and detached["a"] is not shared
    with pytest.raises(CADException):
        bc.snapshot_json(value, max_bytes=1000, max_nodes=22, max_depth=2)
    with pytest.raises(CADException):
        bc.snapshot_json(value, max_bytes=1000, max_nodes=23, max_depth=1)
    bomb = []
    for _ in range(25):
        bomb = [bomb, bomb]
    with pytest.raises(CADException):
        bc.snapshot_json(bomb, max_bytes=2**40, max_nodes=1_000_000, max_depth=32)
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(CADException, match="cyclic"):
        bc.snapshot_json(cyclic, max_bytes=1000, max_nodes=100, max_depth=64)


def test_million_node_edge_and_contract_addition_do_not_steal_operation_budget():
    # A large independent byte budget isolates the exact node check from bytes.
    operation = {"values": [0] * 999_998}  # dict + list + scalar values = 1,000,000.
    copied = bc.snapshot_json(operation, max_bytes=4_000_000, max_nodes=1_000_000, max_depth=2)
    assert len(copied["values"]) == 999_998
    contract = {
        "version": 1,
        "request_id": NONCE,
        "required_capabilities": [f"a/{i:02}" for i in range(32)],
    }
    whole = {**operation, "backend_contract": contract}
    assert bc.snapshot_json(whole, max_bytes=4_000_000, max_nodes=1_000_036, max_depth=3) == whole
    with pytest.raises(CADException):
        bc.snapshot_json(whole, max_bytes=4_000_000, max_nodes=1_000_035, max_depth=3)
    operation["values"].append(0)
    with pytest.raises(CADException):
        bc.snapshot_json(operation, max_bytes=4_000_000, max_nodes=1_000_000, max_depth=2)


def test_part_depth_32_is_not_raised_by_shallow_metadata():
    request = guarded("canonical_snapshot")
    value = 0
    for _ in range(31):
        value = [value]
    request["document"] = value
    bc.prepare_request(request)
    request["document"] = [value]
    with pytest.raises(CADException, match="nesting"):
        bc.prepare_request(request)


def _reviewed_cycle_guard_bytes(original):
    """Only the 3d8270c concentric-center equality extension may change old bytes."""
    before = '        elif constraint.kind in ("horizontal", "vertical"):\n'
    added = (
        '        elif constraint.kind == "concentric":\n'
        '            circles = {item.id: item for item in sketch.circles}\n'
        '            start, end = (circles[identifier].center for identifier in constraint.refs)\n'
        '            axes = (0, 1)\n'
    )
    assert original.count(before) == 1
    return original.replace(before, added + before)


def _assert_reviewed_cycle_guard(original, current):
    assert current == _reviewed_cycle_guard_bytes(original)


@pytest.mark.parametrize("mutation", ["omitted", "wrong_axis", "unrelated", "duplicate_anchor"])
def test_cycle_guard_equivalence_rejects_unreviewed_mutations(mutation):
    # A minimal original exercises the exact transformation and comparison;
    # the independent preserved-fixture test below binds it to real source.
    original = '        elif constraint.kind in ("horizontal", "vertical"):\n'
    reviewed = _reviewed_cycle_guard_bytes(original)
    if mutation == "duplicate_anchor":
        with pytest.raises(AssertionError):
            _reviewed_cycle_guard_bytes(original + original)
        return
    mutated = {
        "omitted": original,
        "wrong_axis": reviewed.replace("axes = (0, 1)", "axes = (0,)"),
        "unrelated": reviewed + "# unreviewed change\n",
    }[mutation]
    with pytest.raises(AssertionError):
        _assert_reviewed_cycle_guard(original, mutated)


def test_solver_cleanup_and_reviewed_cycle_guard_preserve_qualified_arc_core():
    source = (ROOT / "tests/fixtures/backend_capability/sketch_solver-51ed72d.py.txt").read_bytes()
    assert hashlib.sha256(source).hexdigest() == (
        "35577e8ac6f8c7517d34bce981987bec9167f6e5ebe688ffa4ab31630a3a12da"
    ), (
        "The preserved 51ed72d solver fixture changed; see fixtures/backend_capability/provenance.json"
    )
    original = source.decode("utf-8")
    current = (ROOT / "src/mechanical_cad/sketch_solver.py").read_text()

    def functions(source):
        lines = source.splitlines(keepends=True)
        return {
            node.name: "".join(lines[node.lineno - 1 : node.end_lineno])
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
        }

    old, new = functions(original), functions(current)
    assert new["solve"] == old["solve"]
    _assert_reviewed_cycle_guard(
        old["_require_acyclic_coordinate_equalities"],
        new["_require_acyclic_coordinate_equalities"],
    )
    assert sketch_solver.BACKEND_CAPABILITIES == frozenset({GUARD})


@pytest.mark.parametrize("field,value", [("protocol_version", True), ("protocol_version", 2)])
def test_admitted_protocol_errors_preserve_the_old_common_shape(field, value):
    request = guarded()
    request[field] = value
    response = sidecar.process_request(request)
    assert response["error"]["code"] == "unsupported_protocol"
    assert response["backend_receipt"]["phase"] == "dispatched"
    assert response["result_version"] == 2


@pytest.mark.parametrize("action", ["canonical_snapshot", "solve_sketch", "replay"])
@pytest.mark.parametrize("kind", [None, "assembly", "part"])
def test_cross_family_kind_cannot_turn_snapshot_into_an_assembly_dispatch(
    action, kind, monkeypatch
):
    request = guarded(action)
    request["kind"] = kind
    monkeypatch.setattr(bc, "observe_backend", lambda _: pytest.fail("implementation import"))
    assert sidecar.process_request(request)["error"]["code"] == "backend_contract_invalid"


@pytest.mark.parametrize("target", ["document", "sketch", "assembly"])
@pytest.mark.parametrize("value", [True, 1.0, "1", 0, 9])
def test_present_unknown_schema_types_are_rejected_without_imports(target, value, monkeypatch):
    request = guarded("assembly_replay" if target == "assembly" else "replay")
    if target == "document":
        request["document"] = {"schema_version": value}
    elif target == "sketch":
        request["document"] = {"features": [{"sketch": {"schema_version": value}}]}
    else:
        request["assembly"] = {"assembly_schema_version": value}
    monkeypatch.setattr(bc, "observe_backend", lambda _: pytest.fail("implementation import"))
    assert sidecar.process_request(request)["error"]["code"] == "backend_contract_invalid"


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        (1, 2),
        b"bytes",
        {1: "value"},
        pytest.param(1 << 16_384, id="integer-over-bit-limit"),
    ],
)
def test_invalid_direct_json_never_reaches_admission(value, monkeypatch):
    request = guarded()
    request["document"] = value
    monkeypatch.setattr(bc, "observe_backend", lambda _: pytest.fail("implementation import"))
    response = sidecar.process_request(request)
    assert response["error"]["code"] == "invalid_json"
    assert "backend_receipt" not in response


def test_exact_4k_member_accounting_and_independent_64k_receipt_metadata():
    member = {"backend_contract": ""}
    member["backend_contract"] = "x" * (4096 - len(json.dumps(member)))
    assert len(json.dumps(member).encode()) == 4096
    assert bc.snapshot_json(member, max_bytes=4096, max_nodes=36, max_depth=3) == member
    member["backend_contract"] += "x"
    with pytest.raises(CADException):
        bc.snapshot_json(member, max_bytes=4096, max_nodes=36, max_depth=3)
    member = {"backend_receipt": ""}
    member["backend_receipt"] = "x" * (65536 - len(json.dumps(member)))
    assert bc.snapshot_json(member, max_bytes=65536, max_nodes=100, max_depth=4) == member
    member["backend_receipt"] += "x"
    with pytest.raises(CADException):
        bc.snapshot_json(member, max_bytes=65536, max_nodes=100, max_depth=4)


def test_dispatched_generic_exception_retains_receipt_and_existing_error_shape(monkeypatch):
    def fail(operation):
        raise RuntimeError("an ordinary dispatcher failure")

    monkeypatch.setattr(sidecar, "_process_legacy_request", fail)
    response = sidecar.process_request(guarded())
    assert response["error"] == {
        "code": "sidecar_error",
        "message": "RuntimeError: an ordinary dispatcher failure",
    }
    assert response["result"] is None and response["result_version"] == 2
    assert response["backend_receipt"]["phase"] == "dispatched"


def test_over_budget_dispatched_response_is_failure_only_with_same_receipt(monkeypatch):
    monkeypatch.setattr(
        sidecar, "_process_legacy_request", lambda _: {"ok": True, "result": "x" * 1000}
    )
    monkeypatch.setattr(bc, "MAX_RESPONSE_BYTES", 500)
    response = sidecar.process_request(guarded())
    assert response["ok"] is False and response["result"] is None
    assert response["backend_receipt"]["phase"] == "dispatched"
    assert response["error"]["code"] == "document_too_large"


@pytest.mark.parametrize("value", [None, [], {"ok": True, "result": float("nan")}])
def test_dispatched_serialization_defects_cannot_lose_receipt(value, monkeypatch):
    monkeypatch.setattr(sidecar, "_process_legacy_request", lambda _: value)
    response = sidecar.process_request(guarded())
    assert response["ok"] is False and response["result"] is None
    assert response["backend_receipt"]["phase"] == "dispatched"
    assert response["result_version"] == 2


@pytest.mark.parametrize("action", [name for name in ACTIONS if name != "canonical_snapshot"])
def test_primitive_result_three_still_requires_complete_arc_result_family(action, monkeypatch):
    operation = ordinary(action)
    operation["result_version"] = 3
    minimum = bc.minimum_capabilities(operation)
    assert {BASELINE, GUARD, "mcad.sketch-arcs/1"} <= minimum
    assert (
        "mcad.solve-result/3" in minimum
        if action == "solve_sketch"
        else "mcad.part-result/3" in minimum
    )
    request = {
        **operation,
        "backend_contract": {
            "version": 1,
            "request_id": NONCE,
            "required_capabilities": sorted(minimum),
        },
    }
    calls = []
    monkeypatch.setattr(
        sidecar, "_process_legacy_request", lambda value: calls.append(value) or {"ok": True}
    )
    response = sidecar.process_request(request)
    # Downstream dispatch is stubbed: real source admission remains separate.
    assert calls == [operation]
    assert response["backend_receipt"]["phase"] == "dispatched"
    assert response["backend_receipt"]["confirmed_capabilities"] == sorted(minimum)


def test_omitted_action_still_binds_exact_replay_default_without_inserting_it(monkeypatch):
    request = guarded()
    request.pop("action")
    seen = []

    def dispatch(operation):
        seen.append(operation)
        raise CADException("invalid_document", "ordinary failure")

    monkeypatch.setattr(sidecar, "_process_legacy_request", dispatch)
    response = sidecar.process_request(request)
    assert "action" not in seen[0]
    assert response["backend_receipt"]["request_fingerprint"] == compact_hash(request)
    assert response["backend_receipt"]["phase"] == "dispatched"


@pytest.mark.parametrize("kind", sorted(SYMMETRIC_RELATIONS))
def test_expanded_symmetric_relation_deduplication_preserves_authored_intent(kind):
    original = (Constraint("a", kind, ("left", "right")), Constraint("b", kind, ("right", "left")))
    equations, duplicates = sketch_solver._unique_relations(SimpleNamespace(constraints=original))
    assert len(equations) == 1 and duplicates == ("b",)
    assert equations[0].refs == ("left", "right")
    assert original[1].refs == ("right", "left")
