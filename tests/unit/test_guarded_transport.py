"""Guarded owners reuse bounded transport and preserve export uncertainty."""

import importlib
import json
import os
import shutil
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest
from captured_backend_fixture import captured_backend as captured_backend

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_guarded_transport_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
transport = importlib.import_module(PACKAGE + ".guarded_transport")
contracts = importlib.import_module(PACKAGE + ".backend_contracts")
selection_module = importlib.import_module(PACKAGE + ".backend_selection")
managed = importlib.import_module(PACKAGE + ".sidecar_job")
evidence_module = importlib.import_module(PACKAGE + ".guarded_evidence")
LINUX_MANUAL_CHILD = pytest.mark.skipif(
    sys.platform != "linux", reason="real child with the Linux manual backend profile"
)

WRAPPER = """
import json, os, sys, time
from pathlib import Path
from ._real_sidecar import process_request
request = json.load(sys.stdin)
Path('started').write_text(str(os.getpid()))
mode = os.environ.get('MCAD_TEST_TRANSPORT_MODE', '')
if mode == 'sleep':
    time.sleep(30)
if mode in ('stdout_overflow', 'stderr_overflow'):
    stream = sys.stdout.buffer if mode == 'stdout_overflow' else sys.stderr.buffer
    stream.write(b'x' * 200000)
    stream.flush()
    time.sleep(30)
if mode == 'missing':
    request.pop('backend_contract')
response = process_request(request)
if mode == 'wrong_nonce':
    response['backend_receipt']['request_id'] = 'f' * 32
if mode == 'invalid':
    sys.stdout.write('invalid json')
else:
    json.dump(response, sys.stdout, allow_nan=False)
sys.exit(0 if response['ok'] else 1)
"""


@pytest.fixture
def backend(tmp_path, monkeypatch, captured_backend):
    if sys.platform == "win32":
        selected = captured_backend(
            selection_module, generation=0, lifetime_id="test-lifetime"
        )
        root = Path(selected.project_root)

        def capture(requested_root, *, mode="", generation=0):
            # Only pre-launch rejection/cancellation cases use this inert host
            # profile. Native child behavior remains the real Linux contract.
            assert Path(requested_root) == root and mode == ""
            return replace(selected, generation=generation)

        monkeypatch.setattr(sys.modules[__name__], "selection", capture)
        return root
    module = tmp_path / "src/mechanical_cad"
    shutil.copytree(
        ROOT / "src/mechanical_cad", module, ignore=shutil.ignore_patterns("__pycache__")
    )
    (module / "sidecar.py").rename(module / "_real_sidecar.py")
    (module / "sidecar.py").write_text(WRAPPER)
    return tmp_path


def selection(root, *, mode="", generation=0):
    environment = dict(os.environ, MCAD_TEST_TRANSPORT_MODE=mode)
    return selection_module.BackendSelection.capture(
        str(root),
        sys.executable,
        generation=generation,
        lifetime_id="test-lifetime",
        environment=environment,
    )


def ordinary(action="canonical_snapshot"):
    document = json.loads(
        (ROOT / "examples/regressions/viewport_schema2_capture.mcad.json").read_text(encoding="utf-8")
    )
    result = {"protocol_version": 1, "action": action, "document": document}
    if action != "canonical_snapshot":
        result["result_version"] = 2
    if action.startswith("export_"):
        result["destination"] = "/unused/should-not-exist.step"
    return result


def prepared(action="canonical_snapshot", *, unsupported=False):
    operation = ordinary(action)
    required = contracts.minimum_capabilities(operation)
    if unsupported:
        required = sorted([*required, "unavailable/1"])
    return contracts.prepare_request(operation, required_capabilities=required)


@LINUX_MANUAL_CHILD
def test_real_snapshot_uses_exact_selection_without_second_resolution(backend, monkeypatch):
    selected, owner, request = selection(backend), object(), prepared()
    monkeypatch.setattr(managed.bridge, "resolve_configuration", lambda *a: pytest.fail("resolved"))
    monkeypatch.setattr(
        managed.subprocess, "run", lambda *a, **k: pytest.fail("unbounded transport")
    )
    result = transport.execute(
        request, selected, owner_token=owner, current_selection=lambda: selected
    )
    assert type(result) is evidence_module.GuardedEvidence
    projected = result.revalidate(
        selected,
        owner_token=owner,
        expected_action="canonical_snapshot",
        expected_result_version=None,
    )
    assert projected["document_id"] == ordinary()["document"]["id"]
    assert result.guarded_request() == request.guarded_request()
    assert result.receipt_snapshot()["backend"]["solver_origin"] is None


@LINUX_MANUAL_CHILD
def test_raw_and_prepared_snapshots_are_detached_and_completion_is_one_shot(backend):
    selected, owner, request = selection(backend), object(), prepared()
    job = transport.GuardedJob(request, selected, owner_token=owner)
    snapshot = job.request_snapshot()
    snapshot["document"]["name"] = "changed outside"
    assert job.request_snapshot() == request.guarded_request()
    job.start(selected)
    assert job.wait(5)
    assert job.poll(selected) == "ready"
    result = job.result(selected, owner_token=owner)
    for _ in range(2):
        result.revalidate(
            selected,
            owner_token=owner,
            expected_action="canonical_snapshot",
            expected_result_version=None,
        )
    with pytest.raises(transport.GuardedOperationError, match="already been consumed"):
        job.result(selected, owner_token=owner)


@pytest.mark.parametrize("action", ["canonical_snapshot", "export_step", "export_stl"])
def test_stale_before_start_is_definite_no_launch(backend, action):
    selected = selection(backend)
    job = transport.GuardedJob(prepared(action), selected, owner_token=object())
    with pytest.raises(transport.GuardedOperationError) as error:
        job.start(replace(selected, generation=1))
    assert not error.value.outcome_unknown
    assert job.state == "cancelled" and job.wait(0)
    assert not (backend / "started").exists()


@pytest.mark.parametrize("action", ["canonical_snapshot", "export_step", "export_stl"])
@LINUX_MANUAL_CHILD
def test_valid_pre_dispatch_rejection_never_claims_file_uncertainty(backend, action):
    selected = selection(backend)
    with pytest.raises(transport.GuardedOperationError) as error:
        transport.execute(
            prepared(action, unsupported=True),
            selected,
            owner_token=object(),
            current_selection=lambda: selected,
        )
    assert not error.value.outcome_unknown
    assert error.value.failure.definite_no_dispatch
    assert error.value.failure.code == "backend_capability_missing"


@pytest.mark.parametrize("mode", ["missing", "wrong_nonce", "invalid"])
@LINUX_MANUAL_CHILD
def test_bad_postlaunch_export_reply_remains_uncertain(backend, mode):
    selected = selection(backend, mode=mode)
    with pytest.raises(transport.GuardedOperationError) as error:
        transport.execute(
            prepared("export_step", unsupported=True),
            selected,
            owner_token=object(),
            current_selection=lambda: selected,
        )
    assert error.value.outcome_unknown
    assert "destination may already have been replaced" in str(error.value)
    assert str(error.value).count("destination may already have been replaced") == 1
    assert error.value.historical_export is None


@pytest.mark.parametrize("mode", ["stdout_overflow", "stderr_overflow"])
@LINUX_MANUAL_CHILD
def test_guarded_sync_reuses_live_stream_bounds_and_reaps_process(backend, mode, monkeypatch):
    monkeypatch.setattr(managed, "MAX_RESPONSE_BYTES", 1024)
    monkeypatch.setattr(managed, "MAX_STDERR_BYTES", 1024)
    processes = []
    original = managed.subprocess.Popen

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(managed.subprocess, "Popen", launch)
    selected = selection(backend, mode=mode)
    with pytest.raises(transport.GuardedOperationError, match="exceeds"):
        transport.execute(
            prepared(), selected, owner_token=object(), current_selection=lambda: selected
        )
    assert len(processes) == 1 and processes[0].poll() is not None


@LINUX_MANUAL_CHILD
def test_current_selection_is_not_used_to_change_launch(backend):
    selected, owner = selection(backend), object()
    changed = replace(selected, generation=1)
    calls = iter([selected, changed])
    with pytest.raises(transport.GuardedOperationError, match="changed"):
        transport.execute(
            prepared(), selected, owner_token=owner, current_selection=lambda: next(calls)
        )
    assert (backend / "started").exists()


@LINUX_MANUAL_CHILD
def test_stale_poll_cancels_ready_unconsumed_completion(backend):
    selected, owner = selection(backend), object()
    job = transport.GuardedJob(prepared(), selected, owner_token=owner).start(selected)
    assert job.wait(5)
    with pytest.raises(transport.GuardedOperationError):
        job.poll(replace(selected, generation=1))
    assert job.state == "cancelled"
    with pytest.raises(transport.GuardedOperationError, match="cancelled"):
        job.result(selected, owner_token=owner)


@LINUX_MANUAL_CHILD
def test_wrong_owner_cannot_consume_ready_response(backend):
    selected = selection(backend)
    job = transport.GuardedJob(prepared(), selected, owner_token=object()).start(selected)
    assert job.wait(5)
    with pytest.raises(transport.GuardedOperationError, match="another owner"):
        job.result(selected, owner_token=object())
    assert job.state == "cancelled"


@LINUX_MANUAL_CHILD
def test_historical_typed_export_is_not_relabelled_unknown_on_stale_handoff(backend, monkeypatch):
    # Acceptance/typed payload validation is covered by leaf tests. This seam
    # isolates transport's treatment of a successfully validated file receipt.
    selected, owner = selection(backend), object()
    accepted = object.__new__(evidence_module.GuardedEvidence)
    object.__setattr__(accepted, "_response_payload", b'{"ok": true}')
    monkeypatch.setattr(transport, "accept_response", lambda *a, **k: accepted)
    job = transport.GuardedJob(
        prepared("export_step", unsupported=True), selected, owner_token=owner
    )
    job.start(selected)
    assert job.wait(5)
    with pytest.raises(transport.GuardedOperationError) as error:
        job.result(replace(selected, generation=1), owner_token=owner)
    assert not error.value.outcome_unknown
    assert error.value.historical_export is accepted
    assert "file was written" in str(error.value)


def test_cancel_before_start_never_launches(backend):
    selected = selection(backend)
    job = transport.GuardedJob(prepared("export_step"), selected, owner_token=object())
    assert job.cancel() and job.wait(0)
    with pytest.raises(transport.GuardedOperationError) as error:
        job.start(selected)
    assert not error.value.outcome_unknown and not (backend / "started").exists()


@pytest.mark.parametrize(
    "field,value", [("action", "canonical_snapshot"), ("fingerprint", "f" * 64)]
)
def test_forged_prepared_metadata_is_rejected_before_launch(backend, field, value):
    request = prepared("export_step")
    object.__setattr__(request, field, value)
    with pytest.raises(transport.bridge.BridgeError, match="fields differ"):
        transport.GuardedJob(request, selection(backend), owner_token=object())
    assert not (backend / "started").exists()


@LINUX_MANUAL_CHILD
def test_postlaunch_prepared_action_mutation_cannot_suppress_export_uncertainty(backend):
    request, selected, owner = (
        prepared("export_step", unsupported=True),
        selection(backend),
        object(),
    )
    job = transport.GuardedJob(request, selected, owner_token=owner).start(selected)
    assert job.wait(5)
    object.__setattr__(request, "action", "canonical_snapshot")
    with pytest.raises(transport.GuardedOperationError, match="Invalid prepared") as error:
        job.result(selected, owner_token=owner)
    assert error.value.outcome_unknown
    assert job.request_snapshot()["action"] == "export_step"
