"""Preview poll diagnostics retain validation and revoke publication capability."""

import ast
import copy
import json
import time
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from test_assembly_pending_admission_order import ROOT, lease


@pytest.fixture
def preview():
    assert not lease.is_busy()
    token = lease.try_acquire()
    context = object()
    snapshot = {"owner_token": object()}
    transaction = {"key": "scene", "snapshot": snapshot, "state": object(), "scene": object()}
    request = {"action": "assembly_replay", "assembly": {"id": "test"}}
    evidence = NS(publication=NS(cancel=Mock()))
    response = {"ok": True, "result": {"id": "detached"}}
    state = NS(
        _BUSY={"scene"},
        _current_selection=Mock(return_value="selection"),
        _assert_report_display=Mock(),
        _projection=Mock(return_value=response),
        _error=Mock(return_value="Named mate face missing in updated source"),
        _recover_report=Mock(),
        _publish_report=Mock(),
        _commit_candidate_evidence=Mock(),
    )
    job = NS(
        done=True,
        state="finished",
        cleanup_diagnostic="",
        cancel=Mock(),
        poll=Mock(return_value="finished"),
        request_snapshot=lambda: copy.deepcopy(request),
        result=Mock(return_value=evidence),
    )
    prepared = NS(
        operation_request=lambda: copy.deepcopy(request),
        guarded_request=lambda: copy.deepcopy(request),
    )
    env = dict(
        time=time,
        copy=copy,
        _TERMINAL={"finished", "failed", "cancelled"},
        _main_thread=Mock(),
        _assert_inputs=Mock(),
        _ACTIVE={},
        assembly_state=state,
        execution_lease=lease,
        bridge=NS(BridgeError=ValueError),
        assembly_bridge=NS(fingerprint=lambda value: json.dumps(value, sort_keys=True)),
    )
    path = ROOT / "blender_addon/mechanical_cad_blender/assembly_pending.py"
    names = {
        "PendingReport",
        "poll",
        "_cleanup_diagnostic",
        "_release",
        "_abort",
        "_finish_failure",
    }
    nodes = [
        n
        for n in ast.parse(path.read_text()).body
        if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), env)
    pending = env["PendingReport"](
        transaction, prepared, job, token, preview=True, source_preview=True
    )
    env["_ACTIVE"]["scene"] = pending
    yield NS(
        env=env,
        context=context,
        state=state,
        pending=pending,
        evidence=evidence,
        response=response,
        job=job,
        token=token,
    )
    if lease.is_busy():
        assert lease.release(token)


def assert_no_publication_or_recovery(host):
    host.state._publish_report.assert_not_called()
    host.state._commit_candidate_evidence.assert_not_called()
    host.state._recover_report.assert_not_called()


def test_source_failure_is_validated_before_diagnostic_never_returns_ready(preview):
    h = preview
    h.response["ok"] = False
    order = []

    def validated(*args, **kwargs):
        assert kwargs == {"actions": "assembly_replay", "success": False}
        order.append("validated")
        return h.response

    def diagnostic(response):
        assert order == ["validated"] and response is h.response
        order.append("diagnostic")
        return "Named mate face missing in updated source"

    h.state._projection.side_effect = validated
    h.state._error.side_effect = diagnostic
    with pytest.raises(ValueError, match="Named mate face missing"):
        h.env["poll"](h.context, h.pending)
    assert order == ["validated", "diagnostic"]
    assert h.pending._phase == "failed" and h.pending._notified
    h.evidence.publication.cancel.assert_called_once()
    h.job.cancel.assert_called_once()
    assert not lease.is_busy() and not h.env["_ACTIVE"] and not h.state._BUSY
    assert_no_publication_or_recovery(h)
    assert h.env["poll"](h.context, h.pending) is None
    h.state._projection.assert_called_once()


@pytest.mark.parametrize("failure", ["malformed schema", "wrong owner", "stale display"])
def test_invalid_projection_never_uses_unvalidated_diagnostic(preview, failure):
    h = preview
    h.response["ok"] = False
    target = h.state._assert_report_display if failure == "stale display" else h.state._projection
    target.side_effect = ValueError(failure)
    with pytest.raises(ValueError, match=failure):
        h.env["poll"](h.context, h.pending)
    h.state._error.assert_not_called()
    h.evidence.publication.cancel.assert_called_once()
    assert h.pending._phase == "failed" and not lease.is_busy() and not h.env["_ACTIVE"]
    assert_no_publication_or_recovery(h)


@pytest.mark.parametrize("source", [False, True])
def test_successful_preview_uses_correct_validation_mode_and_revokes_capability(preview, source):
    h = preview
    h.pending._source_preview = source
    assert h.env["poll"](h.context, h.pending) is h.response
    assert h.state._projection.call_args.kwargs == {
        "actions": "assembly_replay",
        "success": not source,
    }
    h.state._error.assert_not_called()
    h.evidence.publication.cancel.assert_called_once()
    assert h.pending._phase == "finished" and not lease.is_busy()
    assert_no_publication_or_recovery(h)


def test_motion_failed_success_validation_never_gets_source_diagnostic(preview):
    h = preview
    h.pending._source_preview = False
    h.state._projection.side_effect = ValueError("Assembly replay failed")
    with pytest.raises(ValueError, match="Assembly replay failed"):
        h.env["poll"](h.context, h.pending)
    assert h.state._projection.call_args.kwargs["success"] is True
    h.state._error.assert_not_called()
    h.evidence.publication.cancel.assert_called_once()
    assert not lease.is_busy()
    assert_no_publication_or_recovery(h)


def test_failed_preview_holds_lease_until_native_cleanup_confirmed(preview):
    h = preview
    h.response["ok"] = False
    h.job.cancel.side_effect = lambda: setattr(h.job, "done", False)
    with pytest.raises(ValueError, match="Named mate face missing"):
        h.env["poll"](h.context, h.pending)
    assert h.pending._phase == "cancelling" and lease._TOKEN is h.token
    assert h.env["_ACTIVE"]["scene"] is h.pending
    h.evidence.publication.cancel.assert_called_once()
    h.job.done = True
    with pytest.raises(ValueError, match="Named mate face missing"):
        h.env["poll"](h.context, h.pending)
    assert not lease.is_busy() and not h.env["_ACTIVE"]
    assert_no_publication_or_recovery(h)


@pytest.mark.parametrize("source", [False, True])
def test_pending_status_detaches_source_preview_flag_without_reclassifying_motion(preview, source):
    h = preview
    h.pending._source_preview = source
    h.pending._request = {
        "action": "assembly_replay",
        "assembly": {"joints": [], "instances": [{}, {}]},
        "coordinates": None,
        "samples": None,
        "preset_id": None,
    }
    h.env["authored_coordinates"] = lambda joints: {}
    before = copy.deepcopy(h.pending._request)
    info = h.pending.status()
    assert info["preview"] is True and info["source_preview"] is source
    assert info["state"] == "running" and info["instance_count"] == 2
    info["source_preview"] = not source
    info["base_coordinates"]["changed"] = 1
    assert h.pending._source_preview is source and h.pending._request == before
    assert_no_publication_or_recovery(h)
