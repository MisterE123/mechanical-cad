"""Explicit Replay reuses the candidate owner without replacing the save target."""

import copy

import pytest
from test_assembly_candidate_create import creation  # noqa: F401
from test_assembly_motion_preview import pending_host  # noqa: F401
from test_visual_joint_owner import host  # noqa: F401


def start(c):
    accepted = c.host.state_api.read_assembly(c.host.storage)
    c.host.response["result"]["canonical_assembly"] = copy.deepcopy(accepted)
    return c.api.prepare_replay(c.host.context)


def test_replay_preserves_path_and_uses_only_current_accepted_input(creation):  # noqa: F811
    c = creation
    before = vars(c.host.storage).copy()
    pending = start(c)
    assert pending.status()["replay"]
    assert pending.request_snapshot()["assembly"] == c.host.state_api.read_assembly(c.host.storage)
    assert pending.request_snapshot()["action"] == "assembly_replay"
    assert vars(c.host.storage) == before
    c.jobs[-1].state, c.jobs[-1].done = "ready", True
    assert c.api.poll(c.host.context, pending)["ok"]
    assert c.host.storage.document_path == before["document_path"]
    assert c.host.storage.verification_status == "UNCHECKED"
    c.transaction.publish.assert_called_once()
    assert not c.host.owner.execution_lease.is_busy()


def test_repeated_replay_does_not_revoke_original_owner(creation):  # noqa: F811
    c = creation
    pending = start(c)
    revision = c.host.state_api.interaction_revision()
    with pytest.raises(RuntimeError, match="running|progress|busy|operation"):
        c.api.prepare_replay(c.host.context)
    assert c.host.state_api.interaction_revision() == revision
    assert c.api.active_for_scene(c.host.context.scene) is pending
    assert len(c.jobs) == 1
    c.jobs[-1].state, c.jobs[-1].done = "ready", True
    assert c.api.poll(c.host.context, pending)["ok"]


@pytest.mark.parametrize("ready", [False, True])
def test_cancel_replay_preserves_complete_accepted_bundle(creation, ready):  # noqa: F811
    c = creation
    before = vars(c.host.storage).copy()
    runtime = c.host.state_api._RUNTIME.copy()
    pending = start(c)
    if ready:
        c.jobs[-1].state, c.jobs[-1].done = "ready", True
    c.api.cancel(pending)
    with pytest.raises(RuntimeError, match="replay cancelled"):
        c.api.poll(c.host.context, pending)
    assert vars(c.host.storage) == before
    assert c.host.state_api._RUNTIME == runtime
    c.transaction.publish.assert_not_called()


@pytest.mark.parametrize("change", ["history", "canonical", "report", "workspace", "dialog"])
def test_stale_replay_never_overwrites_newer_state(creation, change):  # noqa: F811
    c = creation
    pending = start(c)
    c.jobs[-1].state, c.jobs[-1].done = "ready", True
    if change == "history":
        c.host.state_api._RUNTIME_EPOCH = "new-history"
    elif change == "canonical":
        c.host.storage.document_json += " "
    elif change == "report":
        c.host.storage.report_json = "new report"
    elif change == "workspace":
        c.host.context.workspace = object()
    else:
        c.host.state_api.begin_interaction()
    before = vars(c.host.storage).copy()
    with pytest.raises(RuntimeError):
        c.api.poll(c.host.context, pending)
    assert vars(c.host.storage) == before
    c.transaction.publish.assert_not_called()
    assert not c.host.owner.execution_lease.is_busy()
