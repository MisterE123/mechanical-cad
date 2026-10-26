"""Actual preview adapter AST with pure canonical edits and controlled transport seams."""

import ast
import copy
import importlib
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from test_assembly_pending_admission_order import PACKAGE, ROOT, lease, policy

edit = importlib.import_module(PACKAGE + ".assembly_edit")


@pytest.fixture
def adapter(monkeypatch):
    assert not lease.is_busy()
    calls = []
    original = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    document = copy.deepcopy(original["part_sources"][0]["document"])
    document["name"] += " updated"
    opening = {
        "fields": {"document_json": "accepted"},
        "working_part": "working",
        "selection": object(),
        "owner_token": object(),
    }
    context = NS(scene=NS(document_json="accepted"))
    transaction = {"snapshot": opening, "key": "scene"}
    state = NS(
        _state=Mock(side_effect=lambda c: calls.append("state") or c.scene),
        _working_part=Mock(return_value="working"),
        _capture=Mock(return_value=opening),
        _assert_current=Mock(side_effect=lambda *a, **kw: calls.append("current")),
        read_assembly=Mock(return_value=original),
        _preflight_assembly=Mock(
            side_effect=lambda d, action: (
                calls.append("preflight") or policy.result_version_for_assembly(d, action=action)
            )
        ),
        _prepare_report=Mock(
            side_effect=lambda *a, **kw: calls.append("transaction") or transaction
        ),
        _prepare_operation=Mock(side_effect=lambda snapshot, candidate: {"assembly": candidate}),
        _current_selection=Mock(return_value=opening["selection"]),
        _BUSY={"scene"},
        commit_candidate=Mock(),
    )
    canonical = Mock(side_effect=lambda c: calls.append("canonical") or document)
    job = NS(start=Mock(), done=True)
    pending = NS(_job=job)
    factory = Mock(return_value=job)
    pending_factory = Mock(return_value=pending)
    acquired, released = [], []
    real_acquire, real_release = lease.try_acquire, lease.release

    def acquire():
        calls.append("acquire")
        token = real_acquire()
        acquired.append(token)
        return token

    def release(token):
        released.append(token)
        return real_release(token)

    monkeypatch.setattr(lease, "try_acquire", acquire)
    monkeypatch.setattr(lease, "release", release)
    env = dict(
        _main_thread=Mock(),
        assembly_edit=edit,
        canonical_working_part=canonical,
        assembly_state=state,
        execution_lease=lease,
        bridge=NS(BridgeError=ValueError),
        _JOB_FACTORY=factory,
        PendingReport=pending_factory,
        _ACTIVE={},
        _abort=Mock(),
        _finish_failure=Mock(),
    )
    path = ROOT / "blender_addon/mechanical_cad_blender/assembly_pending.py"
    node = next(
        n
        for n in ast.parse(path.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "prepare_source_update_preview"
    )
    node.body = [n for n in node.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), env)

    def invoke():
        return env["prepare_source_update_preview"](
            context, expected_json="accepted", expected_working_part="working"
        )

    yield NS(
        env=env,
        invoke=invoke,
        state=state,
        calls=calls,
        canonical=canonical,
        context=context,
        original=original,
        document=document,
        opening=opening,
        transaction=transaction,
        job=job,
        pending=pending,
        acquired=acquired,
        released=released,
    )
    if lease.is_busy():
        assert real_release(lease._TOKEN)


def test_busy_refuses_before_rna_canonical_or_native(adapter):
    token = lease.try_acquire()
    adapter.calls.clear()
    with pytest.raises(ValueError, match="Another CAD operation"):
        adapter.invoke()
    assert adapter.calls == []
    adapter.state._state.assert_not_called()
    adapter.canonical.assert_not_called()
    adapter.env["_JOB_FACTORY"].assert_not_called()
    assert lease._TOKEN is token


@pytest.mark.parametrize("field", ["accepted", "working"])
def test_stale_expected_input_refuses_before_canonicalization(adapter, field):
    if field == "accepted":
        adapter.context.scene.document_json = "new"
    else:
        adapter.state._working_part.return_value = "new"
    with pytest.raises(ValueError, match="changed"):
        adapter.invoke()
    adapter.canonical.assert_not_called()
    assert not adapter.acquired


def test_canonicalization_must_revalidate_opening_before_update(adapter):
    adapter.state._assert_current.side_effect = ValueError("opening stale")
    with pytest.raises(ValueError, match="opening stale"):
        adapter.invoke()
    adapter.canonical.assert_called_once_with(adapter.context)
    adapter.state._assert_current.assert_called_once_with(
        adapter.context, adapter.opening, drafts=True
    )
    adapter.state.read_assembly.assert_not_called()
    assert not adapter.acquired


def test_canonical_candidate_is_detached_and_preview_has_no_publication(adapter):
    before = copy.deepcopy(adapter.original)
    expected, affected = edit.update_source(adapter.original, adapter.document)
    assert affected
    assert adapter.invoke() is adapter.pending
    assert (
        adapter.calls.index("current")
        < adapter.calls.index("preflight")
        < adapter.calls.index("acquire")
    )
    prepared = adapter.env["_JOB_FACTORY"].call_args.args[0]
    assert prepared["assembly"] == expected
    assert prepared["assembly"] is not adapter.original and adapter.original == before
    adapter.state._prepare_report.assert_called_once_with(
        adapter.context, "assembly_replay", transient=True
    )
    adapter.env["PendingReport"].assert_called_once_with(
        adapter.transaction,
        prepared,
        adapter.job,
        adapter.acquired[0],
        preview=True,
        source_preview=True,
    )
    adapter.job.start.assert_called_once_with(adapter.opening["selection"])
    assert adapter.env["_ACTIVE"] == {"scene": adapter.pending}
    adapter.state.commit_candidate.assert_not_called()
    assert adapter.context.scene.document_json == "accepted"


@pytest.mark.parametrize("mode", ["identical", "unaffected"])
def test_no_op_refuses_before_preflight_or_lease(adapter, mode):
    if mode == "identical":
        adapter.canonical.side_effect = lambda c: copy.deepcopy(
            adapter.original["part_sources"][0]["document"]
        )
    else:
        adapter.original["instances"] = []
    with pytest.raises(ValueError, match="No changed accepted source"):
        adapter.invoke()
    adapter.state._preflight_assembly.assert_not_called()
    assert not adapter.acquired


def test_preflight_failure_never_acquires(adapter):
    adapter.state._preflight_assembly.side_effect = ValueError("unsupported shape")
    with pytest.raises(ValueError, match="unsupported shape"):
        adapter.invoke()
    assert not adapter.acquired
    adapter.state._prepare_report.assert_not_called()


@pytest.mark.parametrize("field", ["accepted", "working"])
def test_transaction_rebind_refuses_and_releases_exact_lease(adapter, field):
    snapshot = copy.copy(adapter.opening)
    snapshot["fields"] = dict(adapter.opening["fields"])
    if field == "accepted":
        snapshot["fields"]["document_json"] = "new"
    else:
        snapshot["working_part"] = "new"
    adapter.transaction["snapshot"] = snapshot
    with pytest.raises(ValueError, match="changed before replay"):
        adapter.invoke()
    adapter.state._prepare_operation.assert_not_called()
    assert adapter.released == adapter.acquired and len(adapter.acquired) == 1
    assert not lease.is_busy() and not adapter.state._BUSY and not adapter.env["_ACTIVE"]


@pytest.mark.parametrize("seam", ["_prepare_report", "_prepare_operation", "_JOB_FACTORY"])
def test_failure_before_pending_owner_releases_exact_lease(adapter, seam):
    target = adapter.env[seam] if seam == "_JOB_FACTORY" else getattr(adapter.state, seam)
    target.side_effect = RuntimeError("controlled failure")
    with pytest.raises(RuntimeError, match="controlled failure"):
        adapter.invoke()
    assert adapter.released == adapter.acquired and len(adapter.acquired) == 1
    assert not lease.is_busy() and not adapter.env["_ACTIVE"]
    if seam != "_prepare_report":
        assert not adapter.state._BUSY


@pytest.mark.parametrize("done", [False, True])
def test_started_job_failure_delegates_cleanup_to_pending_owner(adapter, done):
    adapter.job.done = done
    adapter.job.start.side_effect = RuntimeError("start failed")
    with pytest.raises(RuntimeError, match="start failed"):
        adapter.invoke()
    assert adapter.env["_abort"].call_args.args[0] is adapter.pending
    assert adapter.env["_finish_failure"].call_count == int(done)
    assert not adapter.released  # Adapter must not free the live owner's lease itself.
    assert lease._TOKEN is adapter.acquired[0]
