"""Bounded scheduler policy with fake RNA; native replay has a separate smoke test."""

import ast
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

SOURCE = (
    Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender/history_rebuild.py"
)


@pytest.fixture
def scheduler():
    state = NS(
        document_json='{"id":"a"}',
        owner_id="owner",
        status="DIRTY",
        error="",
        repair_intent_json="",
        sketch_draft_json="",
        sketch_annotation_json="",
    )
    scene = NS(mechanical_cad=state)
    context = NS(scene=scene, window=object(), mode="OBJECT")
    timers = set()
    timer_api = NS(
        is_registered=lambda callback: callback in timers,
        register=Mock(side_effect=lambda callback, **kwargs: timers.add(callback)),
        unregister=Mock(side_effect=lambda callback: timers.remove(callback)),
    )
    binding = {
        "scene": scene,
        "window": context.window,
        "document_json": state.document_json,
        "owner_id": state.owner_id,
        "deflection": 0.1,
        "selection": object(),
        "owner_token": object(),
    }
    bpy = NS(
        context=context,
        app=NS(timers=timer_api, handlers=NS(exit_pre=[])),
        types=NS(Operator=object),
    )
    doc = NS(
        require_no_sketch_draft=Mock(),
        _capture_binding=Mock(return_value=binding),
        _read_document=Mock(return_value={"id": "a"}),
        _assert_binding=Mock(),
        _preflight_owned_display=Mock(),
        replay_guard=lambda context: nullcontext(),
        _apply_result=Mock(),
        part_is_current=Mock(return_value=False),
    )
    now = [10.0]
    n = {
        "bpy": bpy,
        "dataclass": dataclass,
        "time": NS(monotonic=lambda: now[0]),
        "document_state": doc,
        "bridge": NS(BridgeError=RuntimeError),
        "assembly_job_ui": NS(ensure_supervisor=Mock()),
        "staged_edit_store": NS(
            require_none=Mock(),
            require_no_live_edit=Mock(),
            interaction_revision=Mock(return_value=0),
        ),
        "sketch_session": NS(interaction_revision=Mock(return_value=0)),
        "workspace": NS(active_draft=Mock(return_value=None), get_role=Mock(return_value=None)),
        "backend_runtime": NS(
            configuration=Mock(return_value=(binding["selection"], 0.1)), capture=Mock()
        ),
        "execution_lease": NS(is_busy=Mock(return_value=False), BUSY_MESSAGE="Busy"),
        "sketch_pending": NS(cancel=Mock(), poll=Mock(return_value=None)),
    }
    tree = ast.parse(SOURCE.read_text())
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    exec(compile(tree, str(SOURCE), "exec"), n)
    n["_start"] = Mock(side_effect=lambda ticket, context: setattr(ticket, "pending", object()))
    return NS(n=n, state=state, context=context, binding=binding, timers=timers, now=now, doc=doc)


def test_history_only_schedules_and_repeated_events_debounce(scheduler):
    s = scheduler
    s.n["schedule"]()
    old = s.n["_PENDING"]
    s.n["schedule"]()
    assert old.binding is None and old.document is None
    assert len(s.timers) == 1
    assert s.n["bpy"].app.timers.register.call_args.kwargs == {"first_interval": 0.25}
    s.n["_start"].assert_not_called()
    s.n["_tick"]()
    s.n["_start"].assert_called_once()


@pytest.mark.parametrize("attribute,value", [("document_json", ""), ("status", "READY")])
def test_only_dirty_existing_part_is_eligible(scheduler, attribute, value):
    s = scheduler
    setattr(s.state, attribute, value)
    s.n["schedule"]()
    assert s.n["_PENDING"] is None and not s.timers
    s.doc._capture_binding.assert_not_called()


@pytest.mark.parametrize("blocked", ["mode", "draft", "proposal", "window", "backend"])
def test_unsupported_context_never_launches_or_retries(scheduler, blocked):
    s = scheduler
    if blocked == "mode":
        s.context.mode = "EDIT_MESH"
    elif blocked == "window":
        s.context.window = None
    elif blocked == "draft":
        s.doc.require_no_sketch_draft.side_effect = RuntimeError("Draft retained")
    elif blocked == "proposal":
        s.n["staged_edit_store"].require_none.side_effect = RuntimeError("Repair retained")
    else:
        s.doc._capture_binding.side_effect = RuntimeError("Backend unavailable")
    s.n["schedule"]()
    assert s.n["_PENDING"] is None and not s.timers
    assert "Regenerate" in s.state.error
    s.n["_start"].assert_not_called()


def test_busy_cleanup_grace_is_bounded_without_launch_retry(scheduler):
    s = scheduler
    s.n["schedule"]()
    s.n["execution_lease"].is_busy.return_value = True
    assert s.n["_tick"]() == 0.1
    s.now[0] += 2.1
    assert s.n["_tick"]() is None
    assert s.n["_PENDING"] is None and not s.timers
    s.n["_start"].assert_not_called()
    assert "Regenerate" in s.state.error


def test_cancellation_is_terminal_and_drops_rna_before_transport(scheduler):
    s = scheduler
    s.n["schedule"]()
    ticket = s.n["_PENDING"]
    s.n["_tick"]()

    def check_retired(*args):
        assert ticket.binding is None and ticket.document is None
        assert s.n["_PENDING"] is None

    s.n["sketch_pending"].cancel.side_effect = check_retired
    s.n["cancel"]("Cancelled by you")
    assert s.n["_tick"]() is None
    assert not s.timers and "Cancelled by you" in s.state.error
    s.doc._apply_result.assert_not_called()


def test_context_change_cannot_annotate_replacement_document(scheduler):
    s = scheduler
    s.n["schedule"]()
    s.n["_tick"]()
    s.state.document_json = '{"id":"replacement"}'
    s.state.error = "New document status"
    s.doc._assert_binding.side_effect = RuntimeError("Changed")
    assert s.n["_tick"]() is None
    assert s.state.error == "New document status"
    s.doc._apply_result.assert_not_called()


def test_configuration_revocation_during_observation_cannot_publish(scheduler):
    s = scheduler
    s.n["schedule"]()
    s.n["_tick"]()

    def changed(context):
        s.n["cancel"]("Backend changed")
        return (s.binding["selection"], 0.1)

    s.n["backend_runtime"].configuration.side_effect = changed
    assert s.n["_tick"]() is None
    s.doc._apply_result.assert_not_called()


def test_success_uses_existing_sink_once_and_never_changes_json(scheduler):
    s = scheduler
    s.n["schedule"]()
    s.n["_tick"]()
    ticket = s.n["_PENDING"]
    ticket.binding["request_fingerprint"] = "fingerprint"
    evidence = NS(publication=NS(cancel=Mock()))
    s.n["sketch_pending"].poll.return_value = evidence
    original = s.state.document_json
    assert s.n["_tick"]() is None
    assert s.n["_PENDING"] is None and ticket.binding is None
    s.doc._apply_result.assert_called_once()
    evidence.publication.cancel.assert_called_once()
    assert s.state.document_json == original


def test_failed_publication_never_repeats(scheduler):
    s = scheduler
    s.n["schedule"]()
    s.n["_tick"]()
    s.n["_PENDING"].binding["request_fingerprint"] = "fingerprint"
    evidence = NS(publication=NS(cancel=Mock()))
    s.n["sketch_pending"].poll.return_value = evidence
    s.doc._apply_result.side_effect = RuntimeError("Publication failed")
    assert s.n["_tick"]() is None
    assert s.n["_tick"]() is None
    s.doc._apply_result.assert_called_once()
    assert "Regenerate" in s.state.error
    evidence.publication.cancel.assert_called_once()


def test_cancel_operator_has_no_undo_and_draw_is_read_only(scheduler):
    s = scheduler
    s.n["schedule"]()
    cls = s.n["MCAD_OT_cancel_history_rebuild"]
    assert "UNDO" not in getattr(cls, "bl_options", ())
    layout = NS(operator=Mock())
    assert s.n["draw_cancel"](layout, s.context)
    layout.operator.assert_called_once()
    s.n["_start"].assert_not_called()
    assert cls().execute(s.context) == {"FINISHED"}
    assert s.n["_PENDING"] is None


def test_manual_rebuild_before_timer_does_not_launch_twice_or_invalidate_success(scheduler):
    s = scheduler
    s.n["schedule"]()
    s.doc.part_is_current.return_value = True
    s.state.status = "READY"
    s.state.error = ""
    assert s.n["_tick"]() is None
    s.n["_start"].assert_not_called()
    assert s.state.status == "READY" and s.state.error == ""


def test_sidebar_and_viewport_redraw_when_queued_and_cancelled(scheduler):
    s = scheduler
    ui, viewport = NS(type="UI", tag_redraw=Mock()), NS(type="WINDOW", tag_redraw=Mock())
    area = NS(type="VIEW_3D", tag_redraw=Mock(), regions=[ui, viewport])
    window = NS(screen=NS(areas=[area]))
    s.context.window = window
    s.binding["window"] = window
    s.n["schedule"]()
    area.tag_redraw.assert_called_once()
    ui.tag_redraw.assert_called_once()
    viewport.tag_redraw.assert_called_once()
    s.n["cancel"]("Cancelled by you")
    assert (
        area.tag_redraw.call_count
        == ui.tag_redraw.call_count
        == viewport.tag_redraw.call_count
        == 2
    )


def test_load_rebuilds_only_accepted_document_beside_opaque_dormant_intent(scheduler):
    s = scheduler
    s.state.repair_intent_json = "  unsupported repair\n"
    s.state.sketch_draft_json = "  saved draft bytes\n"
    s.state.sketch_annotation_json = '{ "labels" : [] }'
    original = dict(vars(s.state))
    s.n["schedule"](after_load=True)
    ticket = s.n["_PENDING"]
    assert ticket.after_load and ticket.document == {"id": "a"}
    s.doc.require_no_sketch_draft.assert_not_called()
    s.n["staged_edit_store"].require_none.assert_not_called()
    s.n["_tick"]()
    ticket.binding["request_fingerprint"] = "fingerprint"
    evidence = NS(publication=NS(cancel=Mock()))
    s.n["sketch_pending"].poll.return_value = evidence
    s.n["_tick"]()
    s.doc._apply_result.assert_called_once()
    for key in (
        "document_json",
        "repair_intent_json",
        "sketch_draft_json",
        "sketch_annotation_json",
    ):
        assert getattr(s.state, key) == original[key]


@pytest.mark.parametrize(
    "changed", ["repair_intent_json", "sketch_draft_json", "sketch_annotation_json"]
)
@pytest.mark.parametrize("ready", [False, True])
def test_load_saved_intent_changes_revoke_even_a_ready_result(scheduler, changed, ready):
    s = scheduler
    s.n["schedule"](after_load=True)
    s.n["_tick"]()
    s.n["_PENDING"].binding["request_fingerprint"] = "fingerprint"
    evidence = NS(publication=NS(cancel=Mock()))
    if ready:

        def poll(*args, **kwargs):
            setattr(s.state, changed, "new intent")
            return evidence

        s.n["sketch_pending"].poll.side_effect = poll
    else:
        setattr(s.state, changed, "new intent")
    assert s.n["_tick"]() is None
    assert s.n["_PENDING"] is None
    s.doc._apply_result.assert_not_called()
    if ready:
        evidence.publication.cancel.assert_called_once()


@pytest.mark.parametrize("owner", ["draft", "repair", "resume"])
@pytest.mark.parametrize("started", [False, True])
def test_load_never_displaces_live_interaction(scheduler, owner, started):
    s = scheduler
    if started:
        s.n["schedule"](after_load=True)
        s.n["_tick"]()
    if owner == "draft":
        s.n["workspace"].active_draft.return_value = object()
    else:
        s.n["staged_edit_store"].require_no_live_edit.side_effect = RuntimeError(owner)
    if started:
        s.n["_tick"]()
    else:
        s.n["schedule"](after_load=True)
    assert s.n["_PENDING"] is None
    assert "Regenerate" in s.state.error
    s.doc._apply_result.assert_not_called()


def test_load_backend_not_ready_is_terminal_even_if_it_later_becomes_ready(scheduler):
    s = scheduler
    s.doc._capture_binding.side_effect = RuntimeError("Bundled backend preparing")
    s.n["schedule"](after_load=True)
    s.doc._capture_binding.side_effect = None
    for _ in range(3):
        assert s.n["_tick"]() is None
    assert s.n["_PENDING"] is None and not s.timers
    assert "file-open" in s.state.error and "Regenerate" in s.state.error
    s.n["_start"].assert_not_called()


@pytest.mark.parametrize("owner", ["sketch_session", "staged_edit_store"])
def test_intervening_then_cancelled_input_does_not_revive_load_ticket(scheduler, owner):
    s = scheduler
    s.n["schedule"](after_load=True)
    # The owner has already closed and all raw bytes are identical again.
    s.n[owner].interaction_revision.return_value += 1
    assert s.n["_tick"]() is None and s.n["_PENDING"] is None
    s.n["_start"].assert_not_called()


def test_load_does_not_publish_a_stored_part_in_assembly_workspace(scheduler):
    s = scheduler
    s.n["workspace"].get_role.return_value = "ASSEMBLY"
    s.n["schedule"](after_load=True)
    assert s.n["_PENDING"] is None
    assert s.state.error == ""  # Assembly branch never annotates the inactive Part.
    s.n["_start"].assert_not_called()
    # The existing history policy is deliberately unchanged.
    s.n["schedule"]()
    assert s.n["_PENDING"] is not None


def test_load_rechecks_saved_intent_at_final_publication_seam(scheduler):
    s = scheduler
    s.n["schedule"](after_load=True)
    s.n["_tick"]()
    s.n["_PENDING"].binding["request_fingerprint"] = "fingerprint"
    evidence = NS(publication=NS(cancel=Mock()))
    s.n["sketch_pending"].poll.return_value = evidence

    def publish(*args, validate_publication):
        s.state.sketch_annotation_json = "new annotation intent"
        validate_publication()

    s.doc._apply_result.side_effect = publish
    assert s.n["_tick"]() is None and s.n["_PENDING"] is None
    assert "annotation intent changed" in s.state.error
    evidence.publication.cancel.assert_called_once()
