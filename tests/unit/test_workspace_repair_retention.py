"""Workspace-only suspension keeps strict intent, never stale repair authority."""

from dataclasses import replace

import pytest
from test_staged_end_face_repair import host as host  # noqa: F401
from test_staged_end_face_repair import partial, prepare_resume, retain


@pytest.fixture
def bound(host):
    host.context.workspace = object()
    host.context.view_layer = object()
    old_capture = host.doc._capture_binding

    def capture(context):
        return dict(
            old_capture(context), workspace=context.workspace, view_layer=context.view_layer
        )

    def check(context, binding):
        if capture(context) != binding:
            raise host.error("stale original binding")

    host.doc._capture_binding = capture
    host.doc._assert_binding = check
    old_replay = host.doc._run_sidecar

    def replay(context, candidate, *, binding):
        check(context, binding)
        return old_replay(
            context,
            candidate,
            binding={k: v for k, v in binding.items() if k not in {"workspace", "view_layer"}},
        )

    host.doc._run_sidecar = replay
    host.binding = capture(host.context)
    return host


def switch(bound):
    bound.context.workspace = object()


def assert_expired(bound, token):
    with pytest.raises(bound.error, match="expired"):
        bound.module.require(bound.context, token)


@pytest.mark.parametrize("trigger", ["timer", "action", "save"])
def test_empty_slot_workspace_recovery_preserves_complete_partial_history(bound, trigger):
    original, proposal = partial(bound)
    expected = bound.codec.encode(proposal)
    switch(bound)
    assert bound.module.current(bound.context) is proposal  # Passive draw still has no effects.
    assert not bound.state.repair_intent_json
    if trigger == "timer":
        assert bound.module._supervise() is None
    elif trigger == "action":
        assert_expired(bound, proposal.token)
    else:
        bound.module.before_save()
    assert bound.module.current(bound.context) is None
    assert bound.state.repair_intent_json == expected
    if trigger == "save":
        assert not bound.state.last_action_error
    else:
        assert "preserved in memory" in bound.state.last_action_error
    assert bound.state.document_json == proposal.base_json and not bound.published
    value = bound.codec.decode(expected)
    assert value["states"] == [original.candidate_json, proposal.candidate_json]
    assert "accepted_annotations" not in value and "token" not in value
    assert not bound.store._CHECKPOINTS
    bound.context.workspace = proposal.binding["workspace"]
    assert_expired(bound, proposal.token)  # Returning cannot revive the expired token.


def test_owned_checkpoint_is_replaced_and_resume_undo_then_save_is_unpoisoned(bound):
    original, proposal = partial(bound)
    older = bound.codec.encode(original)
    bound.state.repair_intent_json = older
    bound.store._CHECKPOINTS[bound.context.scene.as_pointer()] = older
    switch(bound)
    assert_expired(bound, proposal.token)
    raw = bound.state.repair_intent_json
    assert raw == bound.codec.encode(proposal) and raw != older
    prepare_resume(bound, raw)
    resumed = bound.module.resume(bound.context)
    assert resumed.token != proposal.token and len(resumed.repairs) == 1
    assert not bound.state.repair_intent_json and not bound.store._DORMANT_SAVES
    assert resumed.accepted_annotations == bound.state.sketch_annotation_json
    assert bound.replays == [bound.base, original.document, proposal.document]
    bound.module.undo_repair(bound.context, resumed.token)
    assert bound.module.current(bound.context).candidate_json == original.candidate_json
    bound.module.before_save()
    assert bound.codec.decode(bound.state.repair_intent_json)["states"] == [original.candidate_json]
    bound.module.after_save(succeeded=True)
    assert bound.module.current(bound.context) is None and not bound.published


@pytest.mark.parametrize("slot", ["malformed", "unrelated", "externally_cleared"])
@pytest.mark.parametrize("trigger", ["timer", "action", "save"])
def test_collision_retires_old_token_but_preserves_exact_raw_and_loss_warning(bound, slot, trigger):
    original, proposal = partial(bound)
    key = bound.context.scene.as_pointer()
    if slot == "malformed":
        raw = "  {unsupported raw\n"
    else:
        raw = bound.codec.encode(original)
        if slot == "externally_cleared":
            bound.store._CHECKPOINTS[key] = raw
            raw = ""
    bound.state.repair_intent_json = raw
    switch(bound)
    if trigger == "timer":
        bound.module._supervise()
    elif trigger == "save":
        bound.module.before_save()
    else:
        assert_expired(bound, proposal.token)
    assert bound.module.current(bound.context) is None
    assert bound.state.repair_intent_json == raw
    warning = bound.state.last_action_error
    assert "NOT saved" in warning and "not overwritten" in warning
    bound.module.after_save(succeeded=True)
    bound.module.before_save()
    bound.module.after_save(succeeded=True)
    assert bound.state.last_action_error == warning
    bound.context.workspace = proposal.binding["workspace"]
    assert_expired(bound, proposal.token)
    assert bound.state.document_json == proposal.base_json and not bound.published


@pytest.mark.parametrize(
    "change",
    [
        "scene",
        "window",
        "view_layer",
        "base",
        "hash",
        "owner",
        "scale",
        "backend",
        "deflection",
        "annotations",
    ],
)
def test_workspace_plus_broader_change_never_creates_recovery_intent(bound, change):
    proposal = retain(bound)
    switch(bound)
    if change == "scene":
        bound.context.window.scene = object()
    elif change in {"window", "view_layer"}:
        setattr(bound.context, change, object())
    elif change == "base":
        bound.state.document_json += " "
    elif change == "hash":
        proposal = replace(proposal, base_hash="0" * 64)
        bound.store._PENDING[bound.context.scene.as_pointer()] = proposal
    elif change == "owner":
        bound.state.owner_id = "different"
    elif change == "scale":
        bound.context.scene.unit_settings.scale *= 2
    elif change == "backend":
        bound.context.backend_revision += 1
    elif change == "deflection":
        bound.context.deflection += 1
    else:
        bound.state.sketch_annotation_json = "changed annotations"
    assert_expired(bound, proposal.token)
    assert bound.module.current(bound.context) is None
    assert not bound.state.repair_intent_json and not bound.store._DORMANT_SAVES
    assert not bound.published


def test_codec_failure_never_claims_new_intent_was_saved(bound, monkeypatch):
    proposal = retain(bound)
    switch(bound)
    monkeypatch.setattr(
        bound.codec, "encode", lambda proposal: (_ for _ in ()).throw(ValueError("bad scope"))
    )
    bound.module.before_save()
    assert bound.module.current(bound.context) is None and not bound.state.repair_intent_json
    assert (
        "NOT saved" in bound.state.last_action_error
        and "bad scope" in bound.state.last_action_error
    )
    assert_expired(bound, proposal.token)


def test_failed_workspace_save_keeps_only_dormant_intent_then_successful_retry(bound):
    proposal = retain(bound)
    switch(bound)
    bound.module.before_save()
    raw = bound.state.repair_intent_json
    assert raw and bound.module.current(bound.context) is None
    bound.module.after_save(succeeded=False)
    assert "in memory only" in bound.state.last_action_error
    assert "live repair" not in bound.state.last_action_error
    assert bound.state.repair_intent_json == raw
    assert_expired(bound, proposal.token)
    bound.module.before_save()
    bound.module.after_save(succeeded=True)
    assert bound.state.repair_intent_json == raw and not bound.state.last_action_error


def test_late_save_completion_cannot_touch_resumed_owner_or_replaced_raw(bound):
    proposal = retain(bound)
    switch(bound)
    bound.module.before_save()
    raw = bound.state.repair_intent_json
    prepare_resume(bound, raw)
    resumed = bound.module.resume(bound.context)
    bound.state.last_action_error = "New review warning"
    bound.module.after_save(succeeded=True)
    assert bound.module.current(bound.context) is resumed
    assert bound.state.last_action_error == "New review warning"
    assert resumed.token != proposal.token
    bound.module.discard(bound.context, resumed.token)
    bound.binding = bound.doc._capture_binding(bound.context)
    retain(bound)
    switch(bound)
    bound.module.before_save()
    bound.state.repair_intent_json = "externally changed raw"
    bound.state.last_action_error = "External warning"
    bound.module.after_save(succeeded=False)
    assert bound.state.repair_intent_json == "externally changed raw"
    assert bound.state.last_action_error == "External warning"


def test_backend_revocation_during_comparison_cannot_write_for_retired_owner(bound):
    proposal = retain(bound)
    switch(bound)
    original = proposal.assert_binding

    def revoke(context, binding):
        if binding["workspace"] == context.workspace:
            bound.module.cancel_all()
        original(context, binding)

    proposal = replace(proposal, assert_binding=revoke)
    bound.store._PENDING[bound.context.scene.as_pointer()] = proposal
    assert_expired(bound, proposal.token)
    assert not bound.state.repair_intent_json and not bound.store._DORMANT_SAVES


def test_load_history_backend_teardown_never_invokes_workspace_preservation(bound):
    retain(bound)
    switch(bound)
    bound.module.cancel_all("Opening file or history/backend invalidation")
    assert bound.module.current(bound.context) is None
    assert not bound.state.repair_intent_json and not bound.store._DORMANT_SAVES


def test_workspace_checkpoint_write_failure_reports_loss_without_overwriting_raw(bound):
    proposal = retain(bound)
    original_state = bound.state

    class RejectIntentWrite:
        def __getattr__(self, key):
            return getattr(original_state, key)

        def __setattr__(self, key, value):
            if key == "repair_intent_json":
                raise RuntimeError("injected intent write failure")
            setattr(original_state, key, value)

    bound.context.scene.mechanical_cad = RejectIntentWrite()
    switch(bound)
    with pytest.raises(bound.error, match="NOT saved.*write failure"):
        bound.module.require(bound.context, proposal.token)
    assert not original_state.repair_intent_json
    assert bound.module.current(bound.context) is None and not bound.published


def test_slot_changed_during_codec_is_not_overwritten(bound, monkeypatch):
    proposal = retain(bound)
    switch(bound)
    encode = bound.codec.encode

    def altered(proposal):
        raw = encode(proposal)
        bound.state.repair_intent_json = "externally replaced during validation"
        return raw

    monkeypatch.setattr(bound.codec, "encode", altered)
    with pytest.raises(bound.error, match="NOT saved.*changed during"):
        bound.module.require(bound.context, proposal.token)
    assert bound.state.repair_intent_json == "externally replaced during validation"
    assert bound.module.current(bound.context) is None


def test_workspace_recovery_refuses_missing_runtime_annotation_snapshot(bound):
    proposal = retain(bound)
    switch(bound)
    # A legacy/malformed in-process owner without the runtime snapshot has no
    # evidence that its accepted annotation layout remained unchanged.
    proposal = replace(proposal, accepted_annotations=None)
    bound.store._PENDING[bound.context.scene.as_pointer()] = proposal
    assert_expired(bound, proposal.token)
    assert not bound.state.repair_intent_json


@pytest.mark.parametrize("trigger", ["action", "save"])
def test_synchronous_owner_revocation_cannot_return_or_checkpoint_stale_owner(bound, trigger):
    proposal = retain(bound)
    proposal = replace(proposal, assert_binding=lambda *args: bound.module.cancel_all())
    bound.store._PENDING[bound.context.scene.as_pointer()] = proposal
    if trigger == "action":
        assert_expired(bound, proposal.token)
    else:
        bound.module.before_save()
        assert "live ownership expired" in bound.state.last_action_error
        assert "live work retained" not in bound.state.last_action_error
    assert bound.module.current(bound.context) is None
    assert not bound.state.repair_intent_json and not bound.store._DORMANT_SAVES


def test_new_owner_cannot_inherit_old_dormant_receipt_and_erase_collision_loss(bound):
    first = retain(bound)
    switch(bound)
    assert_expired(bound, first.token)
    old_raw = bound.state.repair_intent_json
    assert bound.store._DORMANT_SAVES
    bound.state.repair_intent_json = ""  # External slot replacement, not Resume.
    bound.binding = bound.doc._capture_binding(bound.context)
    second = retain(bound)
    assert not bound.store._DORMANT_SAVES
    bound.state.repair_intent_json = old_raw
    switch(bound)
    with pytest.raises(bound.error, match="NOT saved"):
        bound.module.require(bound.context, second.token)
    warning = bound.state.last_action_error
    bound.module.before_save()
    bound.module.after_save(succeeded=False)
    assert bound.state.repair_intent_json == old_raw
    assert bound.state.last_action_error == warning and "NOT saved" in warning


@pytest.mark.parametrize("phase", ["before", "after"])
def test_deleted_dormant_scene_does_not_break_other_save_receipts(bound, phase):
    proposal = retain(bound)
    switch(bound)
    assert_expired(bound, proposal.token)
    raw = bound.state.repair_intent_json

    class DeletedState:
        def __getattr__(self, name):
            raise ReferenceError("Scene was deleted")

    dead_key = -1234
    if phase == "after":
        bound.module.before_save()
        bound.store._SAVE_PENDING[dead_key] = (None, "dead raw")
    bound.store._DORMANT_SAVES[dead_key] = (DeletedState(), "dead raw", "old notice")
    if phase == "before":
        bound.module.before_save()
    bound.module.after_save(succeeded=False)
    assert dead_key not in bound.store._DORMANT_SAVES
    assert not bound.store._SAVE_PENDING
    assert bound.state.repair_intent_json == raw
    assert "in memory only" in bound.state.last_action_error
