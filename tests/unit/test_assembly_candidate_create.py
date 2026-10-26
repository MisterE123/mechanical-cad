"""Actual async candidate owner and shared sink with synthetic native/display ports."""

import copy
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from test_assembly_motion_preview import pending_host  # noqa: F401
from test_visual_joint_owner import host  # noqa: F401


@pytest.fixture
def creation(pending_host, monkeypatch):  # noqa: F811
    p = pending_host
    h = p.host
    h.storage.document_path = "/saved/old-assembly.json"
    h.context.scene.mechanical_cad.owner_id = "part-owner"
    h.response["ok"] = True
    h.response["result"]["canonical_assembly"]["name"] = "New validated candidate"
    monkeypatch.setattr(p.api.workspace, "get_role", lambda context: "ASSEMBLY", raising=False)
    monkeypatch.setattr(p.api.staged_edit_store, "require_no_live_edit", lambda context: None)
    transaction = NS(publish=Mock(), discard=Mock(), finalize=Mock(), cleanup_warnings=[])
    monkeypatch.setattr(h.display, "stage", Mock(return_value=transaction), raising=False)
    monkeypatch.setattr(
        h.state_api,
        "_evidence_fields",
        lambda *args: {
            name: "new " + name
            for name in (
                "report_json",
                "report_document_json",
                "report_request_json",
                "report_working_part_json",
                "report_preset_id",
            )
        },
    )
    p.transaction = transaction
    p.candidate = copy.deepcopy(h.response["result"]["canonical_assembly"])
    p.snapshot = p.api.capture_candidate(h.context)
    yield p
    p.api.cancel_all(wait_timeout=0)


def start(c):
    return c.api.prepare_candidate(c.host.context, c.candidate, c.snapshot)


def ready(c):
    pending = start(c)
    c.jobs[-1].state, c.jobs[-1].done = "ready", True
    return pending


def test_candidate_stays_local_until_exact_ready_commit(creation):
    c = creation
    before = vars(c.host.storage).copy()
    pending = start(c)
    assert pending.status()["candidate"] and not pending.status()["preview"]
    assert pending.request_snapshot()["action"] == "assembly_replay"
    assert vars(c.host.storage) == before
    c.candidate["name"] = "mutable caller is not authority"
    assert pending.request_snapshot()["assembly"]["name"] == "New validated candidate"
    assert c.api.poll(c.host.context, pending) is None
    c.jobs[-1].state, c.jobs[-1].done = "ready", True
    result = c.api.poll(c.host.context, pending)
    assert result["ok"] and c.host.storage.document_name == "New validated candidate"
    assert c.host.storage.document_path == ""
    assert c.host.storage.verification_status == "UNCHECKED"
    assert c.host.state_api._RUNTIME[c.snapshot["scene_key"]]["report_binding"] is None
    c.transaction.publish.assert_called_once()
    c.transaction.finalize.assert_called_once()
    c.transaction.discard.assert_not_called()
    assert not c.host.owner.execution_lease.is_busy()
    assert c.api.poll(c.host.context, pending) is None


@pytest.mark.parametrize("has_assembly", [False, True])
def test_candidate_does_not_require_existing_display(creation, has_assembly):
    c = creation
    c.host.state_api._RUNTIME.clear()
    if not has_assembly:
        c.host.storage.document_json = ""
        c.host.storage.owner_id = ""
    c.snapshot = c.api.capture_candidate(c.host.context)
    pending = ready(c)
    assert c.api.poll(c.host.context, pending)["ok"]
    assert c.host.storage.owner_id


@pytest.mark.parametrize("phase", ["running", "ready"])
def test_cancel_never_restores_or_writes_accepted_state(creation, phase):
    c = creation
    pending = start(c)
    c.jobs[-1].state, c.jobs[-1].done = phase, phase == "ready"
    before = vars(c.host.storage).copy()
    assert c.api.cancel(pending, "Creation cancelled")
    with pytest.raises((RuntimeError, ValueError), match="Creation cancelled"):
        c.api.poll(c.host.context, pending)
    assert vars(c.host.storage) == before and not c.receipts
    c.transaction.publish.assert_not_called()
    assert not c.host.owner.execution_lease.is_busy()


@pytest.mark.parametrize(
    "change",
    [
        "assembly",
        "owner",
        "part",
        "part_owner",
        "backend",
        "scale",
        "epoch",
        "runtime_epoch",
        "workspace",
        "layer",
        "role",
        "report",
        "path",
        "assembly_admission",
        "sketch_admission",
        "repair_admission",
        "part_intent",
        "mode",
        "deflection",
        "runtime",
        "request",
    ],
)
def test_changed_inputs_revoke_ready_candidate_without_rollback(creation, monkeypatch, change):
    c = creation
    h = c.host
    pending = ready(c)
    if change == "assembly":
        h.storage.document_json += " "
    elif change == "owner":
        h.storage.owner_id += "new"
    elif change == "part":
        h.context.scene.mechanical_cad.document_json += "new"
    elif change == "part_owner":
        h.context.scene.mechanical_cad.owner_id += "new"
    elif change == "backend":
        h.current[0] = replace(h.current[0], generation=3)
    elif change == "scale":
        h.context.scene.unit_settings.scale_length = 2
    elif change == "epoch":
        h.state_api._EPOCHS[c.snapshot["scene_key"]] = 42
    elif change == "runtime_epoch":
        h.state_api._RUNTIME_EPOCH = "new history"
    elif change == "workspace":
        h.context.workspace = object()
    elif change == "layer":
        h.context.view_layer = object()
    elif change == "role":
        monkeypatch.setattr(c.api.workspace, "get_role", lambda context: "PART")
    elif change == "report":
        h.storage.report_json = "newer report"
    elif change == "path":
        h.storage.document_path = "/new/save.json"
    elif change == "assembly_admission":
        h.state_api.begin_interaction()
    elif change == "sketch_admission":
        c.api.sketch_session._INTERACTION_REVISION += 1
    elif change == "repair_admission":
        c.api.staged_edit_store._INTERACTION_REVISION += 1
    elif change == "part_intent":
        h.context.scene.mechanical_cad.repair_intent_json = "unparsed new intent"
    elif change == "mode":
        h.context.mode = "EDIT_MESH"
    elif change == "deflection":
        monkeypatch.setattr(h.state_api, "_configuration", lambda context: (h.current[0], 0.9))
    elif change == "runtime":
        h.state_api._RUNTIME[c.snapshot["scene_key"]] = {"display_evidence": object()}
    else:
        c.jobs[-1].request["action"] = "assembly_check"
    before = vars(h.storage).copy()
    with pytest.raises((RuntimeError, ValueError)):
        c.api.poll(h.context, pending)
    assert vars(h.storage) == before
    c.transaction.publish.assert_not_called()
    assert not h.owner.execution_lease.is_busy()


def test_second_dialog_admission_revokes_original_replace_confirmation(creation):
    c = creation
    c.api.capture_candidate(c.host.context)
    with pytest.raises((RuntimeError, ValueError), match="newer editor"):
        start(c)
    assert not c.jobs


def test_ready_result_cannot_bypass_post_result_guard(creation):
    c = creation
    pending = ready(c)
    result = c.jobs[-1].result

    def changed(*args, **kwargs):
        evidence = result(*args, **kwargs)
        c.host.storage.report_json = "newer evidence"
        return evidence

    c.jobs[-1].result = changed
    with pytest.raises((RuntimeError, ValueError), match="evidence changed"):
        c.api.poll(c.host.context, pending)
    assert c.host.storage.report_json == "newer evidence"
    c.transaction.publish.assert_not_called()


@pytest.mark.parametrize("failure", ["stage", "publish", "partial_write", "guard_after_write"])
def test_sink_fault_rolls_back_path_canonical_report_and_display(creation, monkeypatch, failure):
    c = creation
    before = vars(c.host.storage).copy()
    pending = ready(c)
    if failure == "stage":
        c.host.display.stage.side_effect = RuntimeError("stage failure")
    elif failure == "publish":
        c.transaction.publish.side_effect = RuntimeError("publish failure")
    else:
        write = c.host.state_api._write_fields

        def fail(state, values):
            write(
                state,
                values
                if failure == "guard_after_write"
                else {
                    name: values[name] for name in ("document_json", "document_path", "report_json")
                },
            )
            if failure == "partial_write":
                raise RuntimeError("write failure")
            c.host.state_api.begin_interaction()

        monkeypatch.setattr(c.host.state_api, "_write_fields", fail)
    with pytest.raises((RuntimeError, ValueError)):
        c.api.poll(c.host.context, pending)
    for name in ("document_json", "document_path", "owner_id", "report_json"):
        assert getattr(c.host.storage, name) == before[name]
    if failure != "stage":
        c.transaction.discard.assert_called_once()
    assert c.host.state_api._RUNTIME[c.snapshot["scene_key"]] is c.host.runtime


@pytest.mark.parametrize("empty", [False, True])
def test_sink_rollback_preserves_newer_canonical_and_runtime(creation, monkeypatch, empty):
    c = creation
    if empty:
        c.host.storage.document_json = ""
        c.host.storage.owner_id = ""
        c.host.state_api._RUNTIME.clear()
        c.snapshot = c.api.capture_candidate(c.host.context)
    pending = ready(c)
    write = c.host.state_api._write_fields
    newer = {"display_evidence": object(), "display_owner_token": object()}
    expected_new = {}

    def change(state, values):
        write(state, values)
        state.document_json = "newer external canonical"
        state.report_json = "newer report"
        c.host.state_api._RUNTIME[c.snapshot["scene_key"]] = newer
        expected_new.update(vars(state))

    monkeypatch.setattr(c.host.state_api, "_write_fields", change)
    with pytest.raises((RuntimeError, ValueError)):
        c.api.poll(c.host.context, pending)
    assert vars(c.host.storage) == expected_new
    assert c.host.storage.document_json == "newer external canonical"
    assert c.host.storage.report_json == "newer report"
    assert c.host.state_api._RUNTIME[c.snapshot["scene_key"]] is newer
    c.transaction.discard.assert_called_once()


def test_old_finalizer_does_not_release_newer_lease(creation):
    c = creation
    pending = ready(c)
    c.api.cancel(pending)
    token = c.host.owner.execution_lease.try_acquire()
    assert token is not None
    c.api._release(pending)
    assert c.host.owner.execution_lease._TOKEN is token
    c.host.owner.execution_lease.release(token)


def test_start_failure_retains_delayed_cleanup_owner(creation, monkeypatch):
    c = creation
    factory = c.api._JOB_FACTORY

    def controlled(*args, **kwargs):
        job = factory(*args, **kwargs)
        job.start = Mock(side_effect=RuntimeError("start failed after spawning"))
        job.cancel = lambda: setattr(job, "state", "cancelling")
        return job

    monkeypatch.setattr(c.api, "_JOB_FACTORY", controlled)
    before = vars(c.host.storage).copy()
    with pytest.raises(RuntimeError, match="start failed"):
        start(c)
    retained = c.api.active_for_scene(c.host.context.scene)
    assert retained is not None and c.host.owner.execution_lease.is_busy()
    assert vars(c.host.storage) == before
    c.jobs[-1].state, c.jobs[-1].done = "cancelled", True
    c.api._finish_failure(retained)
    assert c.api.active_for_scene(c.host.context.scene) is None
    assert not c.host.owner.execution_lease.is_busy()


def test_runtime_revocation_rolls_back_own_writes_without_restoring_trust(creation, monkeypatch):
    c = creation
    before = vars(c.host.storage).copy()
    pending = ready(c)
    write = c.host.state_api._write_fields

    def revoke(state, values):
        write(state, values)
        c.host.state_api._RUNTIME.clear()
        c.host.state_api._RUNTIME_EPOCH = "new lifetime"

    monkeypatch.setattr(c.host.state_api, "_write_fields", revoke)
    with pytest.raises(RuntimeError):
        c.api.poll(c.host.context, pending)
    for name in ("document_json", "document_path", "report_json", "owner_id"):
        assert getattr(c.host.storage, name) == before[name]
    assert not c.host.state_api._RUNTIME


@pytest.mark.parametrize("untrusted", [{"saved": "report"}, NS(preview="ghost projection")])
def test_saved_or_preview_result_never_enters_shared_sink(creation, monkeypatch, untrusted):
    import ast
    from pathlib import Path

    c = creation
    module = c.host.state_api
    path = Path(module.__file__)
    node = next(
        n
        for n in ast.parse(path.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "_projection"
    )
    namespace = dict(vars(module))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    monkeypatch.setattr(module, "_projection", namespace["_projection"])
    pending = ready(c)
    c.jobs[-1].result = lambda *args, **kwargs: untrusted
    before = vars(c.host.storage).copy()
    with pytest.raises(RuntimeError, match="guarded backend evidence"):
        c.api.poll(c.host.context, pending)
    for name in ("document_json", "document_path", "report_json", "owner_id"):
        assert getattr(c.host.storage, name) == before[name]
    c.host.display.stage.assert_not_called()
