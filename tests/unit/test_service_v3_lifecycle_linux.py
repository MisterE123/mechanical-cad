"""Native-free transport/receipt lifecycle, separate from strict-v3 semantics.

The inner validator is an explicit test port here. Genuine service responses
and unchanged production admission are tested in the integration module.
"""

import copy
import importlib
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

# Every case below exercises the manual selection contract, which production
# admits on Linux only. Windows bundled rejection stays in the portable module.
pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="dormant data service requires the Linux manual profile"
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_data_only_lifecycle_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
validator = types.ModuleType(PACKAGE + ".result_v3")
validator.validate_request = copy.deepcopy
validator.validate_response = lambda _request, response: copy.deepcopy(response)
sys.modules[validator.__name__] = validator
service = importlib.import_module(PACKAGE + ".service_v3")
contracts = importlib.import_module(PACKAGE + ".backend_contracts")
selections = importlib.import_module(PACKAGE + ".backend_selection")
managed = importlib.import_module(PACKAGE + ".sidecar_job")


def operation():
    return {
        "protocol_version": 1,
        "action": "replay",
        "result_version": 3,
        "document": {
            "schema_version": 1,
            "id": "lifecycle",
            "name": "Lifecycle test data",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    }


def selection(root=ROOT):
    return selections.BackendSelection.capture(
        str(root), sys.executable, generation=0, lifetime_id="data-only-tests", environment={}
    )


def response(prepared, selected):
    required = prepared.guarded_request()["backend_contract"]["required_capabilities"]
    return {
        "protocol_version": 1,
        "result_version": 3,
        "input_fingerprint": "test-port-inner-fingerprint",
        "ok": True,
        "result": {"lifecycle_data": [1, 2, 3]},
        "error": None,
        "backend_receipt": {
            "version": 1,
            "request_id": prepared.request_id,
            "request_fingerprint": prepared.fingerprint,
            "required_capabilities": required,
            "confirmed_capabilities": required[:],
            "missing_capabilities": [],
            "phase": "dispatched",
            "backend": {
                "core_version": "native-free-lifecycle-fixture",
                "project_root": selected.project_root,
                "core_origin": selected.core_origin,
                "solver_origin": str(Path(selected.core_origin) / "sketch_solver.py"),
                "python_executable": selected.python_executable,
                "python_executable_target": selected.python_executable_target,
                "python_prefix": sys.prefix,
                "python_base_prefix": sys.base_prefix,
                "python_version": list(sys.version_info[:3]),
            },
        },
    }


class TransportPort:
    """A process-lifecycle test port; it cannot manufacture CAD authority."""

    instances = []

    @classmethod
    def from_selection(cls, prepared, selected):
        instance = cls()
        instance.prepared, instance.selected = prepared, selected
        instance.payload = prepared.payload
        instance.response = response(prepared, selected)
        instance.state = "created"
        instance.events = []
        cls.instances.append(instance)
        return instance

    @property
    def done(self):
        return self.state in {"ready", "consumed", "cancelled"}

    def start(self):
        self.events.append("start")
        self.state = "ready"

    def poll(self):
        self.events.append("poll")
        return self.state

    def wait(self, timeout=None):
        self.events.append("wait")
        return self.done

    def cancel(self):
        self.events.append("cancel")
        if self.state in {"consumed", "cancelled"}:
            return False
        self.state = "cancelled"
        return True

    def result(self):
        self.events.append("read")
        if self.state != "ready":
            raise service.bridge.BridgeError("Not ready or already consumed/cancelled.")
        self.state = "consumed"
        return self.response


@pytest.fixture
def port(monkeypatch):
    TransportPort.instances = []
    monkeypatch.setattr(service, "SidecarJob", TransportPort)
    return TransportPort


def test_fresh_nonce_exact_launch_snapshot_and_copied_data_only(port):
    selected, source = selection(), operation()
    first = service.DataOnlyJob(source, selected, current_selection=lambda: selected)
    second = service.DataOnlyJob(source, selected, current_selection=lambda: selected)
    assert first.prepared.request_id != second.prepared.request_id
    assert first.prepared.operation_request() == second.prepared.operation_request() == source
    source["document"]["name"] = "external mutation"
    view = first.request_snapshot()
    view["document"]["name"] = "copy mutation"
    assert first.request_snapshot() == first.prepared.guarded_request()
    first.start()
    assert first.poll() == "ready" and first.wait(0)
    result = first.result()
    assert type(result) is dict and "backend_receipt" not in result
    assert not hasattr(result, "publication") and not hasattr(result, "revalidate")
    result["result"]["lifecycle_data"].append(4)
    assert port.instances[0].response["result"]["lifecycle_data"] == [1, 2, 3]
    assert port.instances[0].selected is selected
    assert port.instances[0].payload == first.prepared.payload
    with pytest.raises(service.bridge.BridgeError, match="consumed"):
        first.result()
    second.cancel()


def test_captured_selection_cannot_be_replaced_after_launch(port):
    selected = selection()
    job = service.DataOnlyJob(operation(), selected, current_selection=lambda: selected).start()
    with pytest.raises(AttributeError):
        job.selection = replace(selected, generation=2)
    assert job.selection is selected and port.instances[0].selected is selected
    assert job.result()["ok"]


@pytest.mark.parametrize(
    "action",
    [
        "check_geometry",
        "export_step",
        "export_stl",
        "canonical_snapshot",
        "assembly_replay",
        "assembly_check",
        "assembly_sample",
    ],
)
def test_unsupported_action_rejects_before_transport_construction(port, action):
    ordinary = operation()
    ordinary["action"] = action
    with pytest.raises(service.bridge.BridgeError, match="only solve/replay"):
        service.DataOnlyJob(ordinary, selection(), current_selection=selection)
    assert not port.instances


@pytest.mark.parametrize("version", [None, True, 1, 2, 3.0, "3", 4])
def test_exact_result3_required_even_at_lifecycle_port(port, version):
    ordinary = operation()
    ordinary["result_version"] = version
    with pytest.raises(service.bridge.BridgeError):
        service.DataOnlyJob(ordinary, selection(), current_selection=selection)
    assert not port.instances


@pytest.mark.parametrize("boundary", ["construct", "launch", "poll", "read", "validated"])
@pytest.mark.parametrize(
    "field,value", [("generation", 2), ("lifetime_id", "reloaded"), ("timeout", 70)]
)
def test_selection_checked_at_every_observation_and_reaped(
    port, monkeypatch, boundary, field, value
):
    selected = selection()
    current = [selected]
    changed = replace(selected, **{field: value})
    if boundary == "construct":
        current[0] = changed
        with pytest.raises(selections.SelectionError):
            service.DataOnlyJob(operation(), selected, current_selection=lambda: current[0])
        assert not port.instances
        return
    job = service.DataOnlyJob(operation(), selected, current_selection=lambda: current[0])
    if boundary == "launch":
        current[0] = changed
        action = job.start
    else:
        job.start()
        if boundary == "validated":

            def validate(_operation, value):
                current[0] = changed
                return value

            monkeypatch.setattr(validator, "validate_response", validate)
        else:
            current[0] = changed
        action = job.poll if boundary == "poll" else job.result
    with pytest.raises(selections.SelectionError):
        action()
    assert port.instances[0].events[-2:] == ["cancel", "wait"]
    if boundary in {"launch", "poll", "read"}:
        assert "read" not in port.instances[0].events


def test_selection_supplier_failure_cancels_and_reaps(port):
    selected = selection()
    current = [selected]

    def observe():
        if current[0] is None:
            raise RuntimeError("preferences disappeared")
        return current[0]

    job = service.DataOnlyJob(operation(), selected, current_selection=observe).start()
    current[0] = None
    with pytest.raises(RuntimeError, match="disappeared"):
        job.result()
    assert port.instances[0].events[-2:] == ["cancel", "wait"]


@pytest.mark.parametrize("boundary", ["launch", "poll", "read", "validated"])
@pytest.mark.parametrize("change", ["root", "python", "target", "environment"])
def test_launch_identity_and_environment_cannot_change_mid_operation(
    port, monkeypatch, boundary, change
):
    selected = selection()
    environment = selected.launch_environment()
    if change == "root":
        root = str(ROOT / "src")
        environment["PYTHONPATH"] = str(Path(root) / "src")
        changed = replace(
            selected, project_root=root, _environment=tuple(sorted(environment.items()))
        )
    elif change == "environment":
        environment["MCAD_TEST_DIFFERENT_ENVIRONMENT"] = "1"
        changed = replace(selected, _environment=tuple(sorted(environment.items())))
    else:
        field = "python_executable" if change == "python" else "python_executable_target"
        changed = replace(selected, **{field: str(ROOT / "different-python")})
    current = [selected]
    job = service.DataOnlyJob(operation(), selected, current_selection=lambda: current[0])
    if boundary != "launch":
        job.start()
    if boundary == "validated":

        def validate(_operation, value):
            current[0] = changed
            return value

        monkeypatch.setattr(validator, "validate_response", validate)
    else:
        current[0] = changed
    action = {"launch": job.start, "poll": job.poll, "read": job.result, "validated": job.result}[
        boundary
    ]
    with pytest.raises(selections.SelectionError):
        action()
    assert port.instances[0].events[-2:] == ["cancel", "wait"]


def test_request_mutation_during_validation_cannot_escape(port, monkeypatch):
    selected = selection()
    job = service.DataOnlyJob(operation(), selected, current_selection=lambda: selected).start()

    def validate(_operation, value):
        object.__setattr__(job.prepared, "request_id", "f" * 32)
        return value

    monkeypatch.setattr(validator, "validate_response", validate)
    with pytest.raises(contracts.BackendContractError, match="captured bytes"):
        job.result()
    assert port.instances[0].events[-2:] == ["cancel", "wait"]


@pytest.mark.parametrize(
    "field,value", [("request_id", "f" * 32), ("fingerprint", "f" * 64), ("action", "export_step")]
)
def test_mutated_prepared_fields_cannot_launch_or_escape_validation(port, field, value):
    selected = selection()
    job = service.DataOnlyJob(operation(), selected, current_selection=lambda: selected)
    object.__setattr__(job.prepared, field, value)
    with pytest.raises(contracts.BackendContractError, match="captured bytes"):
        job.start()
    assert port.instances[0].events == ["cancel", "wait"]


@pytest.mark.parametrize(
    "mutation",
    [
        "absent",
        "nonce",
        "fingerprint",
        "missing",
        "phase",
        "root",
        "invocation",
        "target",
        "unknown",
    ],
)
def test_receipt_rejected_before_inner_validation(port, monkeypatch, mutation):
    selected = selection()
    job = service.DataOnlyJob(operation(), selected, current_selection=lambda: selected).start()
    raw = port.instances[0].response
    receipt = raw["backend_receipt"]
    if mutation == "absent":
        raw.pop("backend_receipt")
    elif mutation in {"nonce", "fingerprint"}:
        key = "request_id" if mutation == "nonce" else "request_fingerprint"
        receipt[key] = "f" * (32 if mutation == "nonce" else 64)
    elif mutation == "missing":
        receipt["missing_capabilities"] = [receipt["confirmed_capabilities"].pop()]
    elif mutation == "phase":
        receipt["phase"] = "future"
    elif mutation == "unknown":
        receipt["extra"] = True
    else:
        key = {
            "root": "project_root",
            "invocation": "python_executable",
            "target": "python_executable_target",
        }[mutation]
        receipt["backend"][key] = str(ROOT.parent)
    monkeypatch.setattr(validator, "validate_response", lambda *_: pytest.fail("inner validation"))
    with pytest.raises(contracts.BackendContractError):
        job.result()
    assert port.instances[0].events[-2:] == ["cancel", "wait"]


def test_receipt_copied_from_fresh_identical_operation_rejects(port):
    selected = selection()
    jobs = [
        service.DataOnlyJob(operation(), selected, current_selection=lambda: selected).start()
        for _ in range(2)
    ]
    port.instances[1].response["backend_receipt"] = port.instances[0].response["backend_receipt"]
    assert jobs[0].result()["ok"]
    with pytest.raises(contracts.BackendContractError, match="nonce"):
        jobs[1].result()


@pytest.mark.parametrize("phase", ["dispatched", "rejected_before_dispatch"])
def test_common_failure_returns_only_detached_failure_data(port, monkeypatch, phase):
    selected = selection()
    job = service.DataOnlyJob(operation(), selected, current_selection=lambda: selected).start()
    receipt = port.instances[0].response["backend_receipt"]
    receipt["phase"] = phase
    raw = {
        "protocol_version": 1,
        "ok": False,
        "result": None,
        "error": {"code": "backend_capability_missing", "message": "Unavailable test capability"},
        "backend_receipt": receipt,
    }
    if phase == "dispatched":
        raw["result_version"] = 3
        raw["error"]["code"] = "missing_dependency"
    else:
        receipt["missing_capabilities"] = receipt["confirmed_capabilities"]
        receipt["confirmed_capabilities"] = []
        receipt["backend"]["solver_origin"] = None
    port.instances[0].response = raw
    monkeypatch.setattr(validator, "validate_response", lambda *_: pytest.fail("failure authority"))
    result = job.result()
    assert not result["ok"] and result["result"] is None and type(result) is dict
    assert "backend_receipt" not in result


def test_extra_response_fields_survive_projection_and_inner_failure_reaps(port, monkeypatch):
    selected = selection()
    job = service.DataOnlyJob(operation(), selected, current_selection=lambda: selected).start()
    port.instances[0].response["unreviewed_authority"] = True

    def validate(_request, projected):
        assert projected["unreviewed_authority"] is True
        assert "backend_receipt" not in projected
        raise ValueError("inner evidence invalid")

    monkeypatch.setattr(validator, "validate_response", validate)
    with pytest.raises(ValueError, match="inner evidence invalid"):
        job.result()
    assert port.instances[0].events[-2:] == ["cancel", "wait"]


def test_cancel_before_start_and_ready_result_prevents_data_reuse(port):
    selected = selection()
    for started in (False, True):
        job = service.DataOnlyJob(operation(), selected, current_selection=lambda: selected)
        if started:
            job.start()
        assert job.cancel() and job.done
        with pytest.raises(service.bridge.BridgeError):
            job.start() if not started else job.result()


def test_execute_performs_one_launch_and_never_retries_inner_rejection(port, monkeypatch):
    selected = selection()

    def invalid(*_args):
        raise ValueError("invalid inner source")

    monkeypatch.setattr(validator, "validate_response", invalid)
    with pytest.raises(ValueError, match="inner source"):
        service.execute(operation(), selected, current_selection=lambda: selected)
    assert len(port.instances) == 1
    assert port.instances[0].events.count("start") == 1
    assert port.instances[0].events[-2:] == ["cancel", "wait"]


@pytest.mark.parametrize("mode", ["sleep", "stdout", "stderr", "invalid"])
def test_real_native_free_process_is_reaped_on_cancel_or_transport_failure(
    tmp_path, monkeypatch, mode
):
    module = tmp_path / "src/mechanical_cad"
    module.mkdir(parents=True)
    (module / "__init__.py").write_text("")
    (module / "sidecar.py").write_text(
        "import sys,time\n"
        + ("time.sleep(30)\n" if mode == "sleep" else "")
        + (
            "sys.stdout.write('x'*20000);sys.stdout.flush();time.sleep(30)\n"
            if mode == "stdout"
            else ""
        )
        + (
            "sys.stderr.write('x'*20000);sys.stderr.flush();time.sleep(30)\n"
            if mode == "stderr"
            else ""
        )
        + ("sys.stdout.write('invalid json')\n" if mode == "invalid" else "")
    )
    selected = selection(tmp_path)
    monkeypatch.setattr(service, "SidecarJob", managed.SidecarJob)
    monkeypatch.setattr(managed, "MAX_RESPONSE_BYTES", 1024)
    monkeypatch.setattr(managed, "MAX_STDERR_BYTES", 1024)
    processes = []
    original = managed.subprocess.Popen

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(managed.subprocess, "Popen", launch)
    job = service.DataOnlyJob(operation(), selected, current_selection=lambda: selected).start()
    if mode == "sleep":
        assert not job.wait(0.1)
        job.cancel()
    else:
        assert job.wait(5)
    with pytest.raises(service.bridge.BridgeError):
        job.result()
    assert job.done and len(processes) == 1 and processes[0].poll() is not None
