"""Load-only scheduler policy and cache-sink rollback, without native authority."""

import copy
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from test_history_rebuild import scheduler  # noqa: F401
from test_visual_joint_owner import host  # noqa: F401

REPORT = (
    "report_json",
    "report_document_json",
    "report_request_json",
    "report_working_part_json",
    "report_preset_id",
)


@pytest.fixture
def assembly_scheduler(scheduler):  # noqa: F811
    s = scheduler
    s.context.workspace = object()
    s.context.view_layer = object()
    s.binding.update(workspace=s.context.workspace, view_layer=s.context.view_layer)
    assembly = NS(
        document_json=" accepted assembly bytes\n",
        owner_id="assembly-owner",
        status="DIRTY",
        error="",
        **{key: key + " exact saved bytes" for key in REPORT},
    )
    s.context.scene.mechanical_cad_assembly = assembly
    s.n["workspace"].get_role.return_value = "ASSEMBLY"
    s.n["bpy"].msgbus = NS(subscribe_rna=Mock(), clear_by_owner=Mock())
    s.n["bpy"].types.Window = object
    snapshot = {"fields": vars(assembly).copy()}

    def current(context, captured):
        assert captured is snapshot
        if (
            assembly.document_json != snapshot["fields"]["document_json"]
            or assembly.owner_id != snapshot["fields"]["owner_id"]
        ):
            raise RuntimeError("Assembly changed")

    def binding(context, expected):
        if (
            context.workspace is not expected["workspace"]
            or context.view_layer is not expected["view_layer"]
        ):
            raise RuntimeError("Context changed")

    s.doc._assert_binding.side_effect = binding
    api = NS(
        _RUNTIME={},
        _key=lambda scene: 1,
        _capture=Mock(return_value=snapshot),
        read_assembly=Mock(return_value={"kind": "assembly", "accepted": True}),
        _preflight_assembly=Mock(),
        _assert_current=Mock(side_effect=current),
        interaction_revision=Mock(return_value=0),
        publish_restored_display=Mock(),
    )
    s.n["assembly_state"] = api
    s.n["assembly_pending"] = NS(cancel=Mock(), poll=Mock(return_value=None))
    s.assembly, s.api, s.snapshot = assembly, api, snapshot
    return s


def ready(s):
    s.n["schedule"](after_load=True)
    s.n["_tick"]()
    evidence = NS(publication=NS(cancel=Mock()))
    s.n["assembly_pending"].poll.return_value = evidence
    return evidence


def test_load_dispatches_single_assembly_ticket_even_without_part_document(assembly_scheduler):
    s = assembly_scheduler
    s.state.document_json = ""
    s.state.repair_intent_json = " malformed unknown repair { "
    s.state.sketch_draft_json = " malformed unknown draft [ "
    evidence = ready(s)
    assert s.n["_PENDING"].assembly_snapshot is s.snapshot
    s.n["_tick"]()
    s.api.publish_restored_display.assert_called_once()
    s.doc._apply_result.assert_not_called()
    s.doc.require_no_sketch_draft.assert_not_called()
    s.n["staged_edit_store"].require_none.assert_not_called()
    assert s.assembly.document_json == s.snapshot["fields"]["document_json"]
    assert s.state.sketch_draft_json == " malformed unknown draft [ "
    evidence.publication.cancel.assert_called_once()


@pytest.mark.parametrize(
    "change",
    [
        "canonical",
        "owner",
        "report",
        "workspace",
        "view_layer",
        "role",
        "draft",
        "assembly_interaction",
        "sketch_interaction",
        "repair_interaction",
        "runtime",
    ],
)
def test_ready_assembly_rebuild_revoked_by_newer_context_or_intent(assembly_scheduler, change):
    s = assembly_scheduler
    evidence = ready(s)

    def mutate(*args):
        if change == "canonical":
            s.assembly.document_json += "new"
        elif change == "owner":
            s.assembly.owner_id = "new-owner"
        elif change == "report":
            s.assembly.report_json = "new report"
        elif change in {"workspace", "view_layer"}:
            setattr(s.context, change, object())
        elif change == "role":
            s.n["workspace"].get_role.return_value = "PART"
        elif change == "draft":
            s.state.sketch_draft_json = "new dormant bytes"
        elif change == "assembly_interaction":
            s.api.interaction_revision.return_value = 1
        elif change == "sketch_interaction":
            s.n["sketch_session"].interaction_revision.return_value = 1
        elif change == "repair_interaction":
            s.n["staged_edit_store"].interaction_revision.return_value = 1
        else:
            s.api._RUNTIME[1] = {"new": "authority"}
        return evidence

    s.n["assembly_pending"].poll.side_effect = mutate
    assert s.n["_tick"]() is None
    assert s.n["_PENDING"] is None
    s.api.publish_restored_display.assert_not_called()
    evidence.publication.cancel.assert_called_once()


@pytest.mark.parametrize("reason", ["backend", "owner", "draft", "resume"])
def test_unavailable_assembly_never_launches_or_retries(assembly_scheduler, reason):
    s = assembly_scheduler
    if reason == "backend":
        s.doc._capture_binding.side_effect = RuntimeError("Backend preparing")
    elif reason == "owner":
        s.assembly.owner_id = ""
    elif reason == "draft":
        s.n["workspace"].active_draft.return_value = object()
    else:
        s.n["staged_edit_store"].require_no_live_edit.side_effect = RuntimeError(
            "Resume in progress"
        )
    s.n["schedule"](after_load=True)
    assert s.n["_PENDING"] is None and "Replay" in s.assembly.error
    s.doc._capture_binding.side_effect = None
    assert s.n["_tick"]() is None
    s.n["_start"].assert_not_called()


def test_new_load_and_cancel_drop_assembly_rna_before_cleanup(assembly_scheduler):
    s = assembly_scheduler
    ready(s)
    old = s.n["_PENDING"]

    def retired(*args):
        assert old.binding is None and old.document is None and old.assembly_snapshot is None

    s.n["assembly_pending"].cancel.side_effect = retired
    s.n["schedule"](after_load=True)
    assert s.n["_PENDING"] is not old
    s.n["assembly_pending"].cancel.assert_called_once()
    s.n["bpy"].msgbus.clear_by_owner.assert_called_once()


def test_assembly_final_publication_callback_checks_opaque_intent_again(assembly_scheduler):
    s = assembly_scheduler
    evidence = ready(s)

    def publish(*args, validate_publication):
        s.state.repair_intent_json = "newer repair intent"
        validate_publication()

    s.api.publish_restored_display.side_effect = publish
    s.n["_tick"]()
    assert s.n["_PENDING"] is None and "intent changed" in s.assembly.error
    evidence.publication.cancel.assert_called_once()


@pytest.fixture
def sink(host, monkeypatch):  # noqa: F811
    h = host
    api = h.state_api
    api._RUNTIME.clear()
    for key in REPORT:
        setattr(h.storage, key, " exact historical " + key + "\n")
    h.storage.status = "DIRTY"
    h.storage.display_status = "STALE"
    h.storage.verification_status = "STALE"
    snapshot = api._capture(h.context, h.context.scene)
    snapshot["prepared"] = NS(operation_request=lambda: {"assembly": copy.deepcopy(h.assembly)})
    transaction = NS(publish=Mock(), discard=Mock(), finalize=Mock(), cleanup_warnings=[])
    monkeypatch.setattr(h.display, "stage", Mock(return_value=transaction), raising=False)
    monkeypatch.setattr(api, "_projection", Mock(return_value=copy.deepcopy(h.response)))
    evidence = object()
    guard = Mock(side_effect=lambda: api._assert_current(h.context, snapshot))
    return NS(
        h=h, api=api, snapshot=snapshot, transaction=transaction, evidence=evidence, guard=guard
    )


def publish(s):
    return s.api.publish_restored_display(
        s.h.context, s.snapshot, s.evidence, validate_publication=s.guard
    )


def test_sink_publishes_only_display_and_leaves_report_historical(sink):
    s = sink
    before = {key: getattr(s.h.storage, key) for key in ("document_json", "owner_id", *REPORT)}
    publish(s)
    assert all(getattr(s.h.storage, key) == value for key, value in before.items())
    runtime = s.api._RUNTIME[s.api._key(s.h.context.scene)]
    assert runtime["display_evidence"] is s.evidence and runtime["report_binding"] is None
    assert s.h.storage.status == "READY" and s.h.storage.display_status == "CURRENT"
    assert (
        s.h.storage.verification_status == "STALE"
        and "historical" in s.h.storage.verification_message
    )
    s.transaction.publish.assert_called_once()
    s.transaction.finalize.assert_called_once()
    s.transaction.discard.assert_not_called()


@pytest.mark.parametrize("failure_at", [1, 2, 3, 4])
def test_sink_late_guard_rejection_rolls_back_without_rewinding_newer_text(sink, failure_at):
    s = sink
    count = [0]

    def guard():
        count[0] += 1
        if count[0] == failure_at:
            s.h.storage.document_json = "newer canonical text"
            s.h.storage.report_json = "newer report text"
            raise RuntimeError("Newer operation")

    s.guard.side_effect = guard
    with pytest.raises(RuntimeError, match="Newer operation"):
        publish(s)
    assert s.h.storage.document_json == "newer canonical text"
    assert s.h.storage.report_json == "newer report text"
    assert not s.api._RUNTIME
    if failure_at > 1:
        s.transaction.discard.assert_called_once()
    s.transaction.finalize.assert_not_called()


def test_sink_write_failure_restores_only_its_diagnostics(sink, monkeypatch):
    s = sink
    original = vars(s.h.storage).copy()

    def fail(state, fields):
        state.status = fields["status"]
        state.report_json = "newer report"
        raise RuntimeError("RNA write fault")

    monkeypatch.setattr(s.api, "_write_fields", fail)
    with pytest.raises(RuntimeError, match="RNA write fault"):
        publish(s)
    assert s.h.storage.document_json == original["document_json"]
    assert s.h.storage.status == original["status"] and s.h.storage.report_json == "newer report"
    assert not s.api._RUNTIME
    s.transaction.discard.assert_called_once()


def test_finalized_cache_cleanup_failure_is_not_false_canonical_failure(sink):
    s = sink
    s.transaction.finalize.side_effect = RuntimeError("orphan cleanup")
    publish(s)
    assert s.h.storage.display_status == "CURRENT"
    assert "orphan cleanup" in s.h.storage.last_action_error
    assert s.api._RUNTIME[s.api._key(s.h.context.scene)]["report_binding"] is None


def test_sink_rejects_preview_candidate_not_equal_to_accepted_snapshot(sink):
    s = sink
    candidate = copy.deepcopy(s.h.assembly)
    candidate["name"] = "unaccepted proposal"
    s.snapshot["prepared"] = NS(operation_request=lambda: {"assembly": candidate})
    with pytest.raises(s.h.owner.BridgeError, match="proposed Assembly"):
        publish(s)
    s.h.display.stage.assert_not_called()
    assert not s.api._RUNTIME


def test_sink_rollback_failure_never_restores_live_report_authority(sink):
    s = sink
    s.transaction.publish.side_effect = RuntimeError("publish fault")
    s.transaction.discard.side_effect = RuntimeError("rollback fault")
    original = {key: getattr(s.h.storage, key) for key in ("document_json", *REPORT)}
    with pytest.raises(RuntimeError, match="rollback fault"):
        publish(s)
    assert not s.api._RUNTIME
    assert all(getattr(s.h.storage, key) == value for key, value in original.items())
