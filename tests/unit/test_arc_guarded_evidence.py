"""Genuine recorded inner data with an explicitly synthetic portable outer port.

No native process runs here. Historical receipt bytes are provenance only. The
synthetic outer port tests binding, defaults and dormant handoff semantics; it
does not assert fresh native identity or authorize a production owner.
"""

import ast
import copy
import hashlib
import importlib
import inspect
import json
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest
from arc_owner_review import reviewed_dynamic_calls

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
FIXTURES = ROOT / "tests/fixtures/arc_authoring_evidence"
PACKAGE = "mcad_arc_guarded_policy_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
contracts = importlib.import_module(PACKAGE + ".backend_contracts")
selections = importlib.import_module(PACKAGE + ".backend_selection")
evidence_module = importlib.import_module(PACKAGE + ".guarded_evidence")
transport = importlib.import_module(PACKAGE + ".guarded_transport")
policy = importlib.import_module(PACKAGE + ".operation_contracts")

CASES3 = (
    "radius_edit_5_0_solve_sketch",
    "radius_edit_5_0_replay",
    "radius_edit_7_0_solve_sketch",
    "radius_edit_7_0_replay",
    "rectangle_solve3",
    "rectangle_replay3",
)


def recorded(label):
    if label.startswith("rectangle"):
        guarded = json.loads((FIXTURES / (label + ".request.raw")).read_text())
        operation = {key: value for key, value in guarded.items() if key != "backend_contract"}
        response = json.loads((FIXTURES / (label + ".response.raw")).read_text())
    else:
        operation = json.loads((FIXTURES / (label + ".operation.json")).read_text())
        response = json.loads((FIXTURES / (label + ".response")).read_text())
    return operation, contracts.project_response(response)


def selection():
    return selections.BackendSelection.capture(
        str(ROOT), sys.executable, generation=2, lifetime_id="synthetic-port-only", environment={}
    )


def synthetic_outer(prepared, inner, selected):
    """Receipt test port, not a statement about a current native process."""
    required = prepared.guarded_request()["backend_contract"]["required_capabilities"]
    return {
        **copy.deepcopy(inner),
        "backend_receipt": {
            "version": 1,
            "request_id": prepared.request_id,
            "request_fingerprint": prepared.fingerprint,
            "required_capabilities": required,
            "confirmed_capabilities": required[:],
            "missing_capabilities": [],
            "phase": "dispatched",
            "backend": {
                "core_version": "synthetic-outer-port-only",
                "project_root": selected.project_root,
                "core_origin": selected.core_origin,
                "solver_origin": None
                if prepared.action == "canonical_snapshot"
                else str(Path(selected.core_origin) / "sketch_solver.py"),
                "python_executable": selected.python_executable,
                "python_executable_target": selected.python_executable_target,
                "python_prefix": "/synthetic/prefix",
                "python_base_prefix": "/synthetic/base",
                "python_version": [3, 12, 14],
            },
        },
    }


def accepted_case(label):
    operation, inner = recorded(label)
    prepared, selected, owner = contracts.prepare_request(operation), selection(), object()
    response = synthetic_outer(prepared, inner, selected)
    evidence = evidence_module.accept_response(prepared, response, selected, owner_token=owner)
    return prepared, response, selected, owner, evidence


def snapshot_case():
    root = ROOT / "tests/fixtures/result_v3/legacy_30383a1"
    operation = json.loads((root / "snapshot_viewport_rectangle.request.txt").read_text())
    inner = json.loads((root / "snapshot_viewport_rectangle.stdout.txt").read_text())
    prepared, selected, owner = contracts.prepare_request(operation), selection(), object()
    response = synthetic_outer(prepared, inner, selected)
    evidence = evidence_module.accept_response(prepared, response, selected, owner_token=owner)
    return prepared, response, selected, owner, evidence


def test_recorded_fixture_bytes_match_sealed_provenance():
    manifest = json.loads((FIXTURES / "provenance.json").read_text())
    for name, record in manifest["files"].items():
        data = (FIXTURES / name).read_bytes()
        assert len(data) == record["bytes"]
        assert hashlib.sha256(data).hexdigest() == record["sha256"]
    for label in ("rectangle_solve3", "rectangle_replay3", "rectangle_replay2"):
        terminal = json.loads((FIXTURES / (label + ".terminal.json")).read_text())
        assert terminal["cleanup_complete"] and terminal["returncode"] == 0
        for suffix, original in (("request.raw", "request.raw"), ("response.raw", "stdout.raw")):
            assert (
                hashlib.sha256((FIXTURES / (label + "." + suffix)).read_bytes()).hexdigest()
                == (terminal["digests"][original])
            )


@pytest.mark.parametrize("label", CASES3)
def test_genuine_inner_v3_acceptance_keeps_default_v2_owner_barrier(label):
    prepared, response, selected, owner, evidence = accepted_case(label)
    inner = contracts.project_response(response)
    assert policy.validate_response(prepared.operation_request(), inner) == inner
    for method in (evidence.revalidate, evidence.publication.consume):
        with pytest.raises(contracts.BackendContractError, match="result version"):
            method(selected, owner_token=owner)
    assert (
        evidence.revalidate(
            selected,
            owner_token=owner,
            expected_action=prepared.action,
            expected_result_version=3,
            require_success=True,
        )
        == inner
    )
    assert (
        evidence.publication.consume(
            selected,
            owner_token=owner,
            expected_action=prepared.action,
            expected_result_version=3,
            require_success=True,
        )
        == inner
    )
    with pytest.raises(contracts.BackendContractError, match="no longer available"):
        evidence.publication.consume(selected, owner_token=owner, expected_result_version=3)
    assert evidence.revalidate(selected, owner_token=owner, expected_result_version=3) == inner


def test_old_expected_version_defaults_are_exact_two():
    for method in (
        evidence_module.GuardedEvidence.revalidate,
        evidence_module.EvidencePublication.consume,
    ):
        default = inspect.signature(method).parameters["expected_result_version"].default
        assert type(default) is int and default == 2
    _, _, selected, owner, evidence = accepted_case("rectangle_replay2")
    assert evidence.revalidate(selected, owner_token=owner, require_success=True)
    assert evidence.publication.consume(selected, owner_token=owner, require_success=True)
    with pytest.raises(contracts.BackendContractError, match="result version"):
        evidence.revalidate(selected, owner_token=owner, expected_result_version=3)


@pytest.mark.parametrize("expected", [None, False, True, 2.0, 3.0, "3", [2, 3], {2, 3}])
def test_owner_expectation_is_exact_integer_never_wildcard_or_collection(expected):
    _, _, selected, owner, evidence = accepted_case("radius_edit_5_0_solve_sketch")
    for method in (evidence.revalidate, evidence.publication.consume):
        with pytest.raises(contracts.BackendContractError, match="result version"):
            method(selected, owner_token=owner, expected_result_version=expected)


@pytest.mark.parametrize(
    "action", [None, "replay", {"canonical_snapshot"}, {"canonical_snapshot", "replay"}]
)
def test_snapshot_none_requires_exact_snapshot_action(action):
    _, _, selected, owner, evidence = snapshot_case()
    for method in (evidence.revalidate, evidence.publication.consume):
        with pytest.raises(contracts.BackendContractError):
            method(
                selected, owner_token=owner, expected_action=action, expected_result_version=None
            )


def test_snapshot_default_and_numeric_expectations_reject_but_explicit_contract_passes():
    _, _, selected, owner, evidence = snapshot_case()
    for method in (evidence.revalidate, evidence.publication.consume):
        for version in (2, 3, False):
            with pytest.raises(contracts.BackendContractError, match="Snapshot"):
                method(
                    selected,
                    owner_token=owner,
                    expected_action="canonical_snapshot",
                    expected_result_version=version,
                )
        assert method(
            selected,
            owner_token=owner,
            expected_action="canonical_snapshot",
            expected_result_version=None,
            require_success=True,
        )


@pytest.mark.parametrize("label", CASES3)
def test_real_data_only_projection_cannot_be_reaccepted_as_guarded_authority(label):
    prepared, response, selected, owner, evidence = accepted_case(label)
    projection = contracts.project_response(response)
    assert type(projection) is dict and not hasattr(projection, "publication")
    with pytest.raises(contracts.BackendContractError):
        evidence_module.accept_response(prepared, projection, selected, owner_token=owner)
    assert evidence.operation_request() == prepared.operation_request()


@pytest.mark.parametrize("label", CASES3)
def test_v3_exact_G_nonce_owner_epoch_action_and_projection_are_all_required(label):
    prepared, response, selected, owner, evidence = accepted_case(label)
    other = contracts.prepare_request(prepared.operation_request())
    assert other.request_id != prepared.request_id
    with pytest.raises(contracts.BackendContractError, match="nonce"):
        evidence_module.accept_response(other, response, selected, owner_token=owner)
    with pytest.raises(contracts.BackendContractError, match="owner"):
        evidence.revalidate(selected, owner_token=object(), expected_result_version=3)
    with pytest.raises(contracts.BackendContractError, match="action"):
        evidence.revalidate(
            selected, owner_token=owner, expected_action="check_geometry", expected_result_version=3
        )
    for current in (
        replace(selected, generation=selected.generation + 2),
        replace(selected, lifetime_id="retired-and-restored"),
    ):
        with pytest.raises(selections.SelectionError):
            evidence.revalidate(current, owner_token=owner, expected_result_version=3)
    projection = contracts.project_response(response)
    projection["result"]["document_id"] = "other"
    with pytest.raises(contracts.BackendContractError, match="projection"):
        evidence.revalidate(
            selected, owner_token=owner, expected_result_version=3, projection=projection
        )
    assert evidence.publication.cancel()
    with pytest.raises(contracts.BackendContractError, match="cancelled"):
        evidence.revalidate(selected, owner_token=owner, expected_result_version=3)


@pytest.mark.parametrize("label", CASES3)
@pytest.mark.parametrize("mutation", ["version", "fingerprint", "document", "extra"])
def test_genuine_inner_adversaries_are_not_repaired_or_relabelled(label, mutation):
    prepared, response, selected, owner, _ = accepted_case(label)
    if mutation == "version":
        response["result_version"] = 2
    elif mutation == "fingerprint":
        response["input_fingerprint"] = "0" * 64
    elif mutation == "document":
        response["result"]["document_hash"] = "0" * 64
    else:
        response["result"]["extra"] = True
    with pytest.raises(contracts.BackendContractError):
        evidence_module.accept_response(prepared, response, selected, owner_token=owner)


def test_real_rectangle_v3_and_general_solve_cannot_enter_old_owner_sinks():
    rectangle = importlib.import_module(PACKAGE + ".sketch_draft")
    general = importlib.import_module(PACKAGE + ".general_sketch_draft")
    pending = importlib.import_module(PACKAGE + ".sketch_pending")
    prepared, _, selected, owner, evidence = accepted_case("rectangle_replay3")
    document = prepared.operation_request()["document"]
    feature = next(f["id"] for f in document["features"] if f["kind"] == "sketch_constrained")
    assert policy.result_version_for(document, owner_role="rectangle") == 2
    draft = rectangle.RectangleDraft(json.dumps(document), feature_id=feature, is_edit=True)
    for consume in (False, True):
        with pytest.raises(contracts.BackendContractError, match="result version"):
            draft.accept_guarded_replay(
                document, evidence, selected, owner_token=owner, consume=consume
            )
    assert draft.validated_json == "" and draft._guarded_evidence is None
    prepared, _, selected, owner, evidence = accepted_case("rectangle_solve3")
    operation = prepared.operation_request()
    draft = general.GeneralSketchDraft(
        json.dumps(operation["document"]), feature_id=operation["feature_id"], is_edit=True
    )
    draft.bind_guarded(owner, lambda: selected)
    with pytest.raises(contracts.BackendContractError, match="result version"):
        draft.record_guarded_solution(evidence, draft.revision, expected_prepared=prepared)
    with pytest.raises(ValueError, match="guarded"):
        draft.record_validated_solution(operation, recorded("rectangle_solve3")[1], draft.revision)
    assert not draft.has_current_solution
    with pytest.raises(pending.bridge.BridgeError, match="Result version"):
        pending._request_snapshot(operation)


class PortablePort:
    """No process execution: exact prepared bytes plus a synthetic outer reply."""

    inner = None

    @classmethod
    def from_selection(cls, prepared, selected):
        port = cls()
        port.prepared, port.selected, port.state = prepared, selected, "created"
        return port

    def request_snapshot(self):
        return self.prepared.guarded_request()

    def start(self):
        self.state = "ready"

    def result(self):
        assert self.state == "ready"
        self.state = "consumed"
        return synthetic_outer(self.prepared, self.inner, self.selected)

    def cancel(self):
        self.state = "cancelled"


@pytest.mark.parametrize("label", CASES3)
def test_generic_transport_exact_O_handoff_never_opts_receiving_owner_into_v3(monkeypatch, label):
    operation, inner = recorded(label)
    prepared, selected, owner = contracts.prepare_request(operation), selection(), object()
    monkeypatch.setattr(PortablePort, "inner", inner)
    monkeypatch.setattr(transport, "SidecarJob", PortablePort)
    job = transport.GuardedJob(prepared, selected, owner_token=owner).start(selected)
    evidence = job.result(selected, owner_token=owner)
    assert evidence.guarded_request() == prepared.guarded_request()
    with pytest.raises(contracts.BackendContractError, match="result version"):
        evidence.revalidate(selected, owner_token=owner)
    with pytest.raises(contracts.BackendContractError, match="result version"):
        evidence.publication.consume(selected, owner_token=owner)


ASSEMBLY_VERSION_PROVENANCE = {
    "assembly_export_owner.py": {
        "_checked_report": (
            {
                "assembly": "assembly_state.read_assembly(state)",
                "version": "assembly_export_bridge.result_version_for(assembly)",
            },
            "evidence.revalidate(selection, owner_token=runtime.get('report_owner_token'), "
            "expected_action='assembly_check', expected_result_version=version, require_success=True)",
        ),
        "_historical_projection": (
            {"prepared": "snapshot.get('prepared')"},
            "evidence.revalidate(snapshot['selection'], owner_token=snapshot['owner_token'], "
            "expected_action=ACTION, expected_result_version=prepared.operation_request()['result_version'])",
        ),
        "run_export": (
            {"request": "assembly_export_bridge.build_request(snapshot['assembly'], path)"},
            "evidence.publication.consume(assembly_state._current_selection(context, snapshot), "
            "owner_token=snapshot['owner_token'], expected_action=ACTION, "
            "expected_result_version=request['result_version'])",
        ),
    },
    "assembly_state.py": {
        "_projection": (
            {
                "prepared": "snapshot.get('prepared')",
                "operation": "prepared.operation_request()",
                "result_version": "_preflight_assembly(operation.get('assembly'), operation.get('action'))",
            },
            "validate(_current_selection(context, snapshot), owner_token=snapshot['owner_token'], "
            "expected_action=actions, expected_result_version=result_version, require_success=success)",
        ),
        "report_is_current": (
            {
                "result_version": "_preflight_assembly(read_assembly(state), evidence.operation_request().get('action'))",
            },
            "evidence.revalidate(backend_runtime.capture(_backend_context(context)), "
            "owner_token=runtime.get('report_owner_token'), "
            "expected_action={'assembly_check', 'assembly_sample'}, expected_result_version=result_version)",
        ),
    },
    "assembly_display.py": {
        "_validated": (
            {
                "operation": "evidence.operation_request()",
                "result_version": "operation_contracts.result_version_for_assembly(operation.get('assembly'), action=operation.get('action'))",
            },
            "validate(current_selection(), owner_token=owner_token, "
            "expected_action=assembly_bridge.ACTIONS, expected_result_version=result_version, "
            "require_success=True)",
        ),
    },
}


def verify_assembly_version_provenance(tree, filename):
    """Allow only the exact inventoried sinks with source-policy-derived versions."""
    allowed = set()
    for name, (assignments, validation) in ASSEMBLY_VERSION_PROVENANCE[filename].items():
        functions = [
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert len(functions) == 1
        function = functions[0]
        calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and any(keyword.arg == "expected_result_version" for keyword in node.keywords)
        ]
        assert len(calls) == 1
        call = calls[0]
        assert ast.dump(call, include_attributes=False) == ast.dump(
            ast.parse(validation, mode="eval").body, include_attributes=False
        )
        for variable, expression in assignments.items():
            assert all(
                argument.arg != variable
                for argument in ast.walk(function.args)
                if isinstance(argument, ast.arg)
            )
            stores = [
                node
                for node in ast.walk(function)
                if isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Store)
                and node.id == variable
            ]
            assert len(stores) == 1
            writes = [
                node
                for node in ast.walk(function)
                if isinstance(node, ast.Assign) and node.targets == [stores[0]]
            ]
            assert len(writes) == 1 and writes[0].lineno < call.lineno
            assert ast.dump(writes[0].value, include_attributes=False) == ast.dump(
                ast.parse(expression, mode="eval").body, include_attributes=False
            )
        allowed.add(call)
    return allowed


def check_capable_calls(sources, *, complete=True):
    capable = {"document_state.py", "general_session.py", "general_sketch_draft.py"}
    plumbing = {"guarded_evidence.py", "guarded_transport.py"}
    snapshots = {"guarded_operations.py", "assembly_operator_helpers.py"}
    seen = set()
    for name, source in sources.items():
        path = Path(name)
        tree = ast.parse(source)
        reviewed_calls = reviewed_dynamic_calls(tree, path.stem)
        if path.name == "geometry_operations.py":
            verify_geometry_version_provenance(tree)
        assembly_calls = (
            verify_assembly_version_provenance(tree, path.name)
            if path.name in ASSEMBLY_VERSION_PROVENANCE
            else set()
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all("service_v3" not in alias.name.split(".") for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert "service_v3" not in (node.module or "").split(".")
                assert all(alias.name != "service_v3" for alias in node.names)
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg != "expected_result_version":
                        continue
                    seen.add(path.name)
                    if path.name in snapshots:
                        assert (
                            isinstance(keyword.value, ast.Constant) and keyword.value.value is None
                        )
                    elif path.name == "geometry_operations.py":
                        assert ast.unparse(keyword.value) == "version"
                        assert node is next(
                            call
                            for call in ast.walk(
                                next(
                                    function
                                    for function in tree.body
                                    if isinstance(function, ast.FunctionDef)
                                    and function.name == "_historical_projection"
                                )
                            )
                            if isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Attribute)
                            and call.func.attr == "revalidate"
                        )
                    elif path.name in ASSEMBLY_VERSION_PROVENANCE:
                        assert node in assembly_calls
                    elif node in reviewed_calls:
                        # Exact reviewed owner bodies bind these versions to
                        # prepared requests/source policy, never result stamps.
                        pass
                    elif path.name not in capable | plumbing:
                        assert isinstance(keyword.value, ast.Constant)
                        assert type(keyword.value.value) is int and keyword.value.value == 2
    if complete:
        assert capable | plumbing | snapshots | ASSEMBLY_VERSION_PROVENANCE.keys() <= seen


GEOMETRY_HISTORICAL_SOURCE = '''def _historical_projection(evidence, prepared, binding, action):
    """Validate exact intended bytes without asserting current configuration.

    This projection is a historical fact only; every current sink separately
    checks the live selection, native context and one-shot publication claim.
    """
    version = binding.get("result_version")
    if (
        type(prepared) is not backend_contracts.PreparedRequest
        or type(version) is not int
        or version not in (2, 3)
        or prepared.operation_request().get("result_version") != version
        or prepared.action != action
        or action not in {"check_geometry", "export_step", "export_stl"}
        or binding.get("prepared") != prepared
        or binding.get("request_fingerprint") != prepared.fingerprint
        or type(evidence) is not GuardedEvidence
        or backend_contracts.request_fingerprint(evidence.guarded_request()) != prepared.fingerprint
    ):
        raise bridge.BridgeError("Geometry action requires its exact guarded completion.")
    return evidence.revalidate(
        binding["selection"],
        owner_token=binding["owner_token"],
        expected_action=action,
        expected_result_version=version,
    )
'''


def verify_geometry_version_provenance(tree):
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_historical_projection"
    )
    assert ast.dump(function, include_attributes=False) == ast.dump(
        ast.parse(GEOMETRY_HISTORICAL_SOURCE).body[0], include_attributes=False
    )
    run = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_geometry_action"
    )
    text = ast.unparse(run)
    for name, expression in {
        "version": "document_state._result_version(document, result_version, action=action)",
        "prepared_version": "prepared.operation_request().get('result_version')",
    }.items():
        stores = [
            node
            for node in ast.walk(run)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name
        ]
        assert len(stores) == 1
        assignments = [
            node
            for node in ast.walk(run)
            if isinstance(node, ast.Assign) and node.targets == [stores[0]]
        ]
        assert len(assignments) == 1 and ast.unparse(assignments[0].value) == expression
    version_writes = [
        node
        for node in ast.walk(run)
        if isinstance(node, ast.Subscript)
        and isinstance(node.ctx, ast.Store)
        and ast.unparse(node) == "binding['result_version']"
    ]
    assert len(version_writes) == 1
    assert (
        "version = document_state._result_version(document, result_version, action=action)" in text
    )
    assert "prepared = _prepare_action(document, action, destination, binding, version)" in text
    assert "prepared_version = prepared.operation_request().get('result_version')" in text
    assert "if type(prepared_version) is not int or prepared_version != version:" in text
    assert "binding['result_version'] = version" in text
    assert (
        text.index("prepared_version =")
        < text.index("binding['result_version'] =")
        < text.index("evidence = guarded_transport.execute")
    )


def test_only_explicit_capable_owners_can_admit_v3_and_data_only_jobs_stay_out():
    check_capable_calls({path.name: path.read_text() for path in ADDON.glob("*.py")})


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_version",
        "unbound_version",
        "supplied_version",
        "reassigned_version",
        "extra_callsite",
    ],
)
def test_geometry_historical_allowance_rejects_wrong_unbound_or_extra_calls(mutation):
    sources = {path.name: path.read_text() for path in ADDON.glob("*.py")}
    source = sources["geometry_operations.py"]
    if mutation == "wrong_version":
        source = source.replace("expected_result_version=version", "expected_result_version=3")
    elif mutation == "unbound_version":
        source = source.replace('version = binding.get("result_version")', "version = 3")
    elif mutation == "supplied_version":
        source = source.replace(
            'binding["result_version"] = version', 'binding["result_version"] = prepared_version'
        )
    elif mutation == "reassigned_version":
        source = source.replace(
            'binding["result_version"] = version',
            'version = 3\n            binding["result_version"] = version',
        )
    else:
        source += "\ndef forbidden(evidence, selection):\n    return evidence.revalidate(selection, expected_result_version=version)\n"
    sources["geometry_operations.py"] = source
    with pytest.raises(AssertionError):
        check_capable_calls(sources)


@pytest.mark.parametrize(
    "filename,function_name",
    [
        ("assembly_state.py", "_projection"),
        ("assembly_state.py", "report_is_current"),
        ("assembly_display.py", "_validated"),
    ],
)
@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_version",
        "unbound_version",
        "supplied_version",
        "reassigned_version",
        "extra_callsite",
    ],
)
def test_assembly_allowance_rejects_wrong_unbound_or_extra_calls(filename, function_name, mutation):
    sources = {path.name: path.read_text() for path in ADDON.glob("*.py")}
    tree = ast.parse(sources[filename])
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    if mutation == "wrong_version":
        keyword = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.keyword) and node.arg == "expected_result_version"
        )
        keyword.value = ast.Constant(3)
    elif mutation in {"unbound_version", "supplied_version"}:
        assignment = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "result_version"
                for target in node.targets
            )
        )
        assignment.value = ast.parse(
            "3"
            if mutation == "unbound_version"
            else "evidence.operation_request().get('result_version')",
            mode="eval",
        ).body
    elif mutation == "reassigned_version":
        function.body.extend(ast.parse("result_version = 3").body)
    else:
        tree.body.extend(
            ast.parse(
                "def forbidden(evidence, selection):\n"
                "    return evidence.revalidate(selection, expected_result_version=3)\n"
            ).body
        )
    sources[filename] = ast.unparse(ast.fix_missing_locations(tree))
    with pytest.raises(AssertionError):
        check_capable_calls(sources)


def test_v3_dispatch_and_guarded_revalidation_remain_native_free_in_clean_process():
    operation, inner = recorded("radius_edit_5_0_replay")
    script = f"""
import importlib, importlib.abc, json, sys, types
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}:
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Deny())
p = types.ModuleType('isolated'); p.__path__ = [{str(ADDON)!r}]
sys.modules['isolated'] = p
module = importlib.import_module('isolated.operation_contracts')
importlib.import_module('isolated.guarded_evidence')
request, response = json.load(sys.stdin)
assert module.result_version_for(request['document']) == 3
assert module.validate_response(request, response) == response
assert 'isolated.service_v3' not in sys.modules
print('ARC_OPERATION_NATIVE_FREE_OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps([operation, inner]),
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "ARC_OPERATION_NATIVE_FREE_OK"


@pytest.mark.parametrize(
    "function_name", ["_checked_report", "_historical_projection", "run_export"]
)
@pytest.mark.parametrize(
    "mutation", ["wrong_version", "wrong_action", "unbound_source", "extra_callsite"]
)
def test_assembly_export_allowance_rejects_unbound_versions_actions_or_extra_sinks(
    function_name, mutation
):
    sources = {path.name: path.read_text() for path in ADDON.glob("*.py")}
    filename = "assembly_export_owner.py"
    tree = ast.parse(sources[filename])
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    if mutation in {"wrong_version", "wrong_action"}:
        field = "expected_result_version" if mutation == "wrong_version" else "expected_action"
        keyword = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.keyword) and node.arg == field
        )
        keyword.value = ast.Constant(3 if mutation == "wrong_version" else "assembly_replay")
    elif mutation == "unbound_source":
        variable = next(iter(ASSEMBLY_VERSION_PROVENANCE[filename][function_name][0]))
        assignment = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == variable for target in node.targets
            )
        )
        assignment.value = ast.parse("evidence.operation_request()", mode="eval").body
    else:
        function.body.extend(
            ast.parse(
                "evidence.revalidate(selection, owner_token=owner, expected_result_version=3, expected_action='assembly_export_step')"
            ).body
        )
    sources[filename] = ast.unparse(tree)
    with pytest.raises(AssertionError):
        check_capable_calls(sources)


@pytest.mark.parametrize(
    "module,before,after",
    [
        ("direct_edge_pick", 'self.catalog_version = request["result_version"]', "self.catalog_version = 3"),
        ("direct_edge_pick", 'self.catalog_version = request["result_version"]', 'self.catalog_version = response["result_version"]'),
        ("projection_repair_ui", "self._version = document_state._result_version(self._document)", "self._version = 3"),
        ("solid_projection_picker", "expected_result_version=self.catalog_version", "expected_result_version=choice.evidence.result_version"),
        ("line_length_session", 'expected_result_version=prepared.operation_request()["result_version"]', "expected_result_version=response['result_version']"),
        ("circle_diameter_session", 'expected_result_version=prepared.operation_request()["result_version"]', "expected_result_version=3"),
        ("sketch_remove_fillet_session", 'expected_result_version=prepared.operation_request()["result_version"]', "expected_result_version=3"),
        ("extrusion_preview", "expected_result_version=operation_contracts.result_version_for(candidate)", "expected_result_version=3"),
    ],
)
def test_new_owner_versions_require_exact_reviewed_source_or_prepared_provenance(module, before, after):
    sources = {module + ".py": (ADDON / (module + ".py")).read_text()}
    check_capable_calls(sources, complete=False)
    original = sources[module + ".py"]
    assert before in original
    sources[module + ".py"] = original.replace(before, after, 1)
    with pytest.raises(AssertionError):
        check_capable_calls(sources, complete=False)


def test_reviewed_owner_module_is_not_a_blanket_dynamic_version_capability():
    sources = {"direct_edge_pick.py": (ADDON / "direct_edge_pick.py").read_text()}
    check_capable_calls(sources, complete=False)
    sources["direct_edge_pick.py"] += "\ndef rogue(e):\n    return e.revalidate(s, expected_result_version=self.catalog_version)\n"
    with pytest.raises(AssertionError):
        check_capable_calls(sources, complete=False)
