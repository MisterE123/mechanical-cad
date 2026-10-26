"""Main-thread guarded Assembly transactions over detached cancellable jobs.

Check/Sample, transient motion replay, accepted-display rebuilding and explicit
candidate creation (including explicit accepted-Assembly Replay) share this owner. A worker owns finite JSON and its private
process; every Blender read, freshness check, report write and rollback happens
on the main thread. Registration owns timers and lifecycle wiring: cancel_all
must run before load/history/unregister; reap handles abandoned modal windows.
Polling returns fresh display-rebuild evidence only to its bound restoration owner;
report/preview polling and cancellation never publish native meshes or authored pose.
Only candidate-purpose polling enters the shared atomic canonical/display commit sink.
"""

from __future__ import annotations

import copy
import threading
import time

from . import (
    assembly_bridge,
    assembly_state,
    backend_runtime,
    bridge,
    execution_lease,
    guarded_transport,
    sketch_session,
    staged_edit_store,
    workspace,
)
from .assembly_coordinates import authored_coordinates

_ACTIVE = {}
_JOB_FACTORY = guarded_transport.GuardedJob
_TERMINAL = frozenset({"finished", "failed", "cancelled"})


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise bridge.BridgeError("Assembly report transactions require Blender's main thread.")


def _scene_key(scene):
    return assembly_state._key(scene)


class PendingReport:
    """Opaque main-thread handle. Status and request access return detached JSON."""

    def __init__(
        self,
        transaction,
        prepared,
        job,
        lease_token,
        *,
        preview=False,
        source_preview=False,
        rebuild=False,
        candidate=False,
        editing=False,
        replay=False,
    ):
        self._replay = replay
        self._candidate = candidate
        self._editing = editing
        self._preview = preview
        self._source_preview = source_preview
        self._rebuild = rebuild
        self._transaction = transaction
        self._prepared = prepared
        self._request = prepared.operation_request()
        self._job = job
        self._lease_token = lease_token
        self._phase = "running"
        self._error = ""
        self._abort_error = None
        self._cancelled = False
        self._notified = False
        self._detached = False
        self._started = time.monotonic()

    @property
    def done(self):
        return self._phase in _TERMINAL

    def request_snapshot(self):
        _main_thread()
        return copy.deepcopy(self._request)

    def status(self):
        """Read-only workload, not estimated progress or a verification verdict."""
        _main_thread()
        request = self._request
        assembly = request["assembly"]
        base = authored_coordinates(assembly["joints"])
        coordinates = request["coordinates"]
        if coordinates is not None:
            base.update(coordinates)
        samples = request["samples"]
        poses = (
            [{**base, samples["joint_id"]: value} for value in samples["values"]]
            if samples is not None
            else [base]
        )
        instances = len(assembly["instances"])
        pairs = instances * (instances - 1) // 2
        return copy.deepcopy(
            {
                "phase": self._phase,
                "state": self._phase,
                "message": self._error,
                "action": request["action"],
                "candidate": self._candidate,
                "editing": self._editing,
                "replay": self._replay,
                "preview": self._preview,
                "source_preview": self._source_preview,
                "rebuild": self._rebuild,
                "error": self._error,
                "elapsed_seconds": max(0.0, time.monotonic() - self._started),
                "instance_count": instances,
                "pairs_per_pose": pairs,
                "pose_count": len(poses),
                "pair_query_count": pairs * len(poses),
                "base_coordinates": base,
                "samples": samples,
                "sample_coordinates": poses if samples is not None else [],
                "preset_id": (
                    request["preset_id"]
                    if request["preset_id"] is not None
                    else assembly.get("active_verification_preset")
                ),
            }
        )


def active_for_scene(scene):
    _main_thread()
    return _ACTIVE.get(_scene_key(scene))


def status(scene):
    """Return detached active status without polling or changing RNA."""
    pending = active_for_scene(scene)
    return pending.status() if pending is not None else None


def prepare(context, action, *, preset_id=None, joint_id=None, values=None):
    """Snapshot/lock an exact original target and start detached finite-JSON work.

    action must be assembly_check or assembly_sample. Sampling always derives the
    complete authored base coordinate map, including fixed zeros; values are the
    entire explicitly requested list. No UI-selected pose becomes canonical.
    """
    _main_thread()
    if action not in {"assembly_check", "assembly_sample"}:
        raise bridge.BridgeError("Only assembly Check and Sample can run asynchronously.")
    if execution_lease.is_busy():
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    assembly_state._preflight_assembly(
        assembly_state.read_assembly(assembly_state._state(context)), action
    )
    token = execution_lease.try_acquire()
    if token is None:
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    transaction = None
    pending = None
    try:
        transaction = assembly_state._prepare_report(context, action)
        arguments = {"preset_id": preset_id}
        if action == "assembly_sample":
            if (
                type(values) not in (list, tuple)
                or not 1 <= len(values) <= assembly_bridge.MAX_SAMPLES
            ):
                raise bridge.BridgeError("Provide the full explicit list of 1 to 32 sample values.")
            arguments.update(
                assembly_state._sample_arguments(
                    transaction["assembly"],
                    joint_id,
                    values,
                )
            )
        elif joint_id is not None or values is not None:
            raise bridge.BridgeError("Sample coordinates cannot be attached to a static Check.")
        snapshot = transaction["snapshot"]
        prepared = assembly_state._prepare_operation(
            snapshot, transaction["assembly"], action, **arguments
        )
        request = prepared.operation_request()
        if action == "assembly_sample":
            samples = request["samples"]
            joints = {row["id"]: row for row in request["assembly"]["joints"]}
            if (
                joint_id not in joints
                or joints[joint_id]["kind"] == "fixed"
                or not 1 <= len(samples["values"]) <= assembly_bridge.MAX_SAMPLES
            ):
                raise bridge.BridgeError(
                    "Select a moving joint and 1 to 32 explicit sample values."
                )
        job = _JOB_FACTORY(prepared, snapshot["selection"], owner_token=snapshot["owner_token"])
        pending = PendingReport(transaction, prepared, job, token)
        _ACTIVE[transaction["key"]] = pending
        # Register before start: a cancelled pre-start job cannot subsequently run.
        job.start(assembly_state._current_selection(context, snapshot))
        return pending
    except Exception as exc:
        if pending is not None:
            _abort(pending, exc)
            if pending._job.done:
                _finish_failure(pending)
        else:
            try:
                if transaction is not None:
                    assembly_state._recover_report(transaction, exc)
            finally:
                if transaction is not None:
                    assembly_state._BUSY.discard(transaction["key"])
                execution_lease.release(token)
        raise


def prepare_motion_preview(context, joint_id, coordinate, *, expected_json):
    """Replay one independent driver over the full assembly, without publication.

    Shares Check/Sample's exact-input guards, process registry and cleanup lease.
    The returned projection is disposable; its receipt cannot publish later.
    """
    from .assembly_motion_draft import MotionDraft

    _main_thread()
    state = assembly_state._state(context)
    if state.document_json != expected_json:
        raise bridge.BridgeError("The accepted assembly changed. Start a fresh motion preview.")
    draft = MotionDraft(assembly_state.read_assembly(state), joint_id)
    draft.coordinate = coordinate
    candidate = draft.candidate()
    assembly_state._preflight_assembly(candidate, "assembly_replay")
    token = execution_lease.try_acquire()
    if token is None:
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    transaction = pending = None
    try:
        transaction = assembly_state._prepare_report(context, "assembly_replay", transient=True)
        snapshot = transaction["snapshot"]
        if snapshot["fields"]["document_json"] != expected_json:
            raise bridge.BridgeError("The accepted assembly changed before motion replay.")
        prepared = assembly_state._prepare_operation(snapshot, candidate)
        job = _JOB_FACTORY(prepared, snapshot["selection"], owner_token=snapshot["owner_token"])
        pending = PendingReport(transaction, prepared, job, token, preview=True)
        _ACTIVE[transaction["key"]] = pending
        job.start(assembly_state._current_selection(context, snapshot))
        return pending
    except Exception as exc:
        if pending is not None:
            _abort(pending, exc)
            if pending._job.done:
                _finish_failure(pending)
        else:
            if transaction is not None:
                assembly_state._BUSY.discard(transaction["key"])
            execution_lease.release(token)
        raise


def prepare_source_update_preview(context, *, expected_json, expected_working_part):
    """Canonicalize the bound working Part and replay its update without publication."""
    from . import assembly_edit
    from .assembly_operator_helpers import canonical_working_part

    _main_thread()
    if execution_lease.is_busy():
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    state = assembly_state._state(context)
    if (state.document_json != expected_json
            or assembly_state._working_part(context.scene) != expected_working_part):
        raise bridge.BridgeError("Assembly or working Part changed. Start a fresh source preview.")
    opening = assembly_state._capture(context, context.scene)
    document = canonical_working_part(context)
    assembly_state._assert_current(context, opening, drafts=True)
    original = assembly_state.read_assembly(state)
    candidate, affected = assembly_edit.update_source(original, document)
    if not affected or candidate == original:
        raise bridge.BridgeError("No changed accepted source is available to preview.")
    assembly_state._preflight_assembly(candidate, "assembly_replay")
    token = execution_lease.try_acquire()
    if token is None:
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    transaction = pending = None
    try:
        transaction = assembly_state._prepare_report(context, "assembly_replay", transient=True)
        snapshot = transaction["snapshot"]
        if (snapshot["fields"]["document_json"] != expected_json
                or snapshot["working_part"] != expected_working_part):
            raise bridge.BridgeError("Source preview inputs changed before replay.")
        prepared = assembly_state._prepare_operation(snapshot, candidate)
        job = _JOB_FACTORY(prepared, snapshot["selection"], owner_token=snapshot["owner_token"])
        pending = PendingReport(transaction, prepared, job, token, preview=True, source_preview=True)
        _ACTIVE[transaction["key"]] = pending
        job.start(assembly_state._current_selection(context, snapshot))
        return pending
    except Exception as exc:
        if pending is not None:
            _abort(pending, exc)
            if pending._job.done:
                _finish_failure(pending)
        else:
            if transaction is not None:
                assembly_state._BUSY.discard(transaction["key"])
            execution_lease.release(token)
        raise


def prepare_display_rebuild(context, snapshot, assembly):
    """One exact accepted-assembly replay; no old display or saved-draft authority.

    The restoration owner guards live interactions and opaque dormant intent.
    This adapter retains the same lease, registry, request and cleanup guards as
    Check/Sample. It returns fresh evidence, never saved report JSON.
    """
    _main_thread()
    assembly_state._preflight_assembly(assembly, "assembly_replay")
    assembly_state._assert_current(context, snapshot)
    key = _scene_key(context.scene)
    if assembly != assembly_state.read_assembly(assembly_state._state(context)):
        raise bridge.BridgeError(
            "Display restoration must replay only the exact accepted Assembly."
        )
    if snapshot["runtime"] is not None or assembly_state._RUNTIME.get(key) is not None:
        raise bridge.BridgeError("A current assembly operation already owns this display.")
    if key in assembly_state._BUSY:
        raise bridge.BridgeError("An assembly transaction is already running in this scene.")
    token = execution_lease.try_acquire()
    if token is None:
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    pending = None
    assembly_state._BUSY.add(key)
    try:
        transaction = {
            "scene": context.scene,
            "state": assembly_state._state(context),
            "key": key,
            "snapshot": snapshot,
            "assembly": assembly,
            "wrote_state": False,
        }
        prepared = assembly_state._prepare_operation(snapshot, assembly)
        job = _JOB_FACTORY(prepared, snapshot["selection"], owner_token=snapshot["owner_token"])
        pending = PendingReport(transaction, prepared, job, token, rebuild=True)
        _ACTIVE[key] = pending
        job.start(assembly_state._current_selection(context, snapshot))
        return pending
    except Exception as exc:
        if pending is not None:
            _abort(pending, exc)
            if pending._job.done:
                _finish_failure(pending)
        else:
            assembly_state._BUSY.discard(key)
            execution_lease.release(token)
        raise


def _candidate_admissions():
    return (
        assembly_state.interaction_revision(),
        sketch_session.interaction_revision(),
        staged_edit_store.interaction_revision(),
    )


def _candidate_part_intent(context):
    part = context.scene.mechanical_cad
    return tuple(
        getattr(part, name, "")
        for name in (
            "owner_id",
            "repair_intent_json",
            "sketch_draft_json",
            "sketch_annotation_json",
        )
    )


def capture_candidate(context):
    """Admit a local candidate dialog without taking ownership of native work.

    Reopening/cancelling another editor revokes this capture even when canonical
    bytes are unchanged. Direct EXEC uses the same admission, never a bypass.
    """
    _main_thread()
    if execution_lease.is_busy():
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    assembly_state._require_no_draft(context)
    staged_edit_store.require_no_live_edit(context)
    assembly_state.begin_interaction()
    snapshot = assembly_state._capture(context, context.scene)
    if snapshot["scene_key"] in assembly_state._BUSY:
        raise bridge.BridgeError("An assembly transaction is already running in this scene.")
    if context.mode != "OBJECT" or getattr(context, "window", None) is None:
        raise bridge.BridgeError("Run assembly creation or replay in an active Object-mode window.")
    snapshot["candidate_context"] = {
        "workspace": context.workspace,
        "view_layer": context.view_layer,
        "role": workspace.get_role(context),
        "part_intent": _candidate_part_intent(context),
        "admissions": _candidate_admissions(),
    }
    return snapshot


def _assert_candidate_inputs(context, snapshot, published=None):
    assembly_state._assert_current(
        context,
        snapshot,
        drafts=True,
        published=(published["document_json"], published["owner_id"]) if published else None,
    )
    staged_edit_store.require_no_live_edit(context)
    bound = snapshot["candidate_context"]
    if (
        context.mode != "OBJECT"
        or context.workspace != bound["workspace"]
        or context.view_layer != bound["view_layer"]
        or workspace.get_role(context) != bound["role"]
        or _candidate_part_intent(context) != bound["part_intent"]
        or _candidate_admissions() != bound["admissions"]
        or assembly_state._configuration(context)[1] != snapshot["deflection"]
    ):
        raise bridge.BridgeError(
            "Assembly operation cancelled: workspace, Part intent, settings or a newer editor changed."
        )
    state = assembly_state._state(context)
    fields = snapshot["fields"]
    expected = published or fields
    if any(
        getattr(state, name) != expected.get(name, fields[name])
        for name in (
            "document_path",
            "document_name",
            "report_json",
            "report_document_json",
            "report_request_json",
            "report_working_part_json",
            "report_preset_id",
        )
    ):
        raise bridge.BridgeError(
            "Assembly operation cancelled: accepted Assembly or evidence changed."
        )
    runtime = assembly_state._RUNTIME.get(snapshot["scene_key"])
    original = snapshot["runtime"]
    if (
        (runtime is None) != (original is None)
        or runtime is not None
        and any(
            runtime.get(name) is not original.get(name)
            for name in ("display_evidence", "display_owner_token")
        )
    ):
        raise bridge.BridgeError("Assembly operation cancelled: accepted Assembly display changed.")


def prepare_replay(context):
    """Replay the exact accepted Assembly with candidate publication guards.

    No new geometry or checks are inferred from cached meshes or old candidates.
    Busy admission precedes interaction revision so repeated clicks cannot revoke
    the owner already running. The save path survives successful publication.
    """
    snapshot = capture_candidate(context)
    return prepare_candidate(
        context,
        assembly_state.read_assembly(assembly_state._state(context)),
        snapshot,
        replay=True,
    )


def prepare_candidate(context, candidate, snapshot, *, replay=False, editing=False):
    """Replay a complete proposed assembly under one cancellable native owner.

    No accepted data, display or report is changed until the same owner's guarded
    poll commits the exact validated request. This is not preview or Check.
    """
    _main_thread()
    if execution_lease.is_busy():
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    candidate = copy.deepcopy(candidate)
    assembly_state._preflight_assembly(candidate, "assembly_replay")
    _assert_candidate_inputs(context, snapshot)
    if replay and candidate != assembly_state.read_assembly(assembly_state._state(context)):
        raise bridge.BridgeError("Replay must use the exact accepted Assembly.")
    key = snapshot["scene_key"]
    if key in assembly_state._BUSY:
        raise bridge.BridgeError("An assembly transaction is already running in this scene.")
    token = execution_lease.try_acquire()
    if token is None:
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    pending = None
    assembly_state._BUSY.add(key)
    try:
        transaction = {
            "scene": context.scene,
            "state": assembly_state._state(context),
            "key": key,
            "snapshot": snapshot,
            "assembly": candidate,
            "wrote_state": False,
        }
        prepared = assembly_state._prepare_operation(snapshot, candidate)
        job = _JOB_FACTORY(prepared, snapshot["selection"], owner_token=snapshot["owner_token"])
        pending = PendingReport(
            transaction, prepared, job, token, candidate=True, replay=replay, editing=editing
        )
        _ACTIVE[key] = pending
        job.start(assembly_state._current_selection(context, snapshot))
        return pending
    except Exception as exc:
        if pending is not None:
            _abort(pending, exc)
            if pending._job.done:
                _finish_failure(pending)
        else:
            assembly_state._BUSY.discard(key)
            execution_lease.release(token)
        raise


def _assert_inputs(context, pending):
    transaction = pending._transaction
    snapshot = transaction["snapshot"]
    if pending._candidate:
        _assert_candidate_inputs(context, snapshot)
        return
    assembly_state._assert_current(context, snapshot, drafts=not pending._rebuild)
    # External edits to report RNA must not be overwritten by an older attempt.
    fields = snapshot["fields"]
    original_binding = tuple(
        fields[name]
        for name in (
            "report_json",
            "report_document_json",
            "report_request_json",
            "report_working_part_json",
            "report_preset_id",
        )
    )
    runtime = assembly_state._RUNTIME.get(transaction["key"])
    if pending._rebuild:
        if assembly_state._binding(transaction["state"]) != original_binding or runtime is not None:
            raise bridge.BridgeError(
                "Assembly evidence or accepted display changed during restoration."
            )
        return
    if (
        assembly_state._binding(transaction["state"]) != original_binding
        or runtime is None
        or snapshot["runtime"] is None
        or runtime.get("display_evidence") is not snapshot["runtime"].get("display_evidence")
        or runtime.get("display_owner_token") is not snapshot["runtime"].get("display_owner_token")
    ):
        raise bridge.BridgeError(
            "Assembly evidence or accepted display changed during the request."
        )


def cleanup_message():
    """Read detached retained-job diagnostics without polling or changing state."""
    _main_thread()
    for pending in _ACTIVE.values():
        diagnostic = getattr(pending._job, "cleanup_diagnostic", "")
        if type(diagnostic) is str and diagnostic:
            return execution_lease.QUARANTINE_MESSAGE
    return ""


def _cleanup_diagnostic(pending):
    """Keep original ownership and replace stale/cancel reasons with actionable status."""
    diagnostic = getattr(pending._job, "cleanup_diagnostic", "")
    if type(diagnostic) is not str or not diagnostic:
        return False
    message = execution_lease.QUARANTINE_MESSAGE
    if pending._error != message:
        pending._notified = False
    pending._error = message
    pending._abort_error = bridge.BridgeError(message)
    pending._phase = "cancelling"
    return True


def _release(pending):
    # A cancelled request still owns native execution until SidecarJob confirms
    # process reaping and file cleanup. Identity release is safe even if an old
    # finalizer runs again after a newer pending operation has acquired the gate.
    if _cleanup_diagnostic(pending) or not pending._job.done:
        return
    key = pending._transaction["key"]
    if _ACTIVE.get(key) is pending:
        _ACTIVE.pop(key, None)
        assembly_state._BUSY.discard(key)
    execution_lease.release(pending._lease_token)


def _abort(pending, exc, *, cancelled=False):
    if _cleanup_diagnostic(pending):
        return
    if pending.done or pending._abort_error is not None:
        return
    pending._abort_error = exc
    pending._cancelled = cancelled
    pending._error = str(exc)
    pending._phase = "cancelling"
    try:
        pending._job.cancel()
    except Exception as cleanup_error:
        # Retain ownership until a later poll/reap establishes termination. A
        # failed cleanup request cannot make a native process safe to forget.
        pending._error += " Native process cancellation failed: " + str(cleanup_error)
        pending._abort_error = bridge.BridgeError(pending._error)
    _cleanup_diagnostic(pending)


def _finish_failure(pending):
    """Recovery always addresses the captured target, never the current scene."""
    if _cleanup_diagnostic(pending):
        return
    error = pending._abort_error or bridge.BridgeError(pending._error or "Assembly check failed.")
    if pending._detached or pending._preview or pending._rebuild or pending._candidate:
        # RNA may already be freed after load/Undo/unregister. Cleanup here is
        # process ownership only; never attempt to recover native scene fields.
        pending._phase = "cancelled" if pending._cancelled else "failed"
        _release(pending)
        return
    try:
        assembly_state._recover_report(pending._transaction, error)
        if pending._cancelled:
            state = pending._transaction["state"]
            state.status = "CANCELLED"
            state.error = (
                "Last attempt cancelled. Previously accepted assembly and evidence are retained. "
                + str(error)
            )
    except Exception as recovery_error:
        pending._error = str(error) + " Recovery failed: " + str(recovery_error)
        pending._phase = "failed"
        if isinstance(recovery_error, ReferenceError):
            # Deleted RNA cannot be restored. Drop capability under the captured
            # key so a later scene-pointer reuse cannot inherit its old trust.
            assembly_state._RUNTIME.pop(pending._transaction["key"], None)
        raise
    else:
        pending._phase = "cancelled" if pending._cancelled else "failed"
    finally:
        _release(pending)


def poll(context, pending=None):
    """Poll on the originating context; return accepted response or None.

    A rejection raises once after job cleanup. A finished/cancelled handle can be
    polled again safely and never consumes an old completion. Modal callers must
    retain the handle and pass it even after an active scene/window change.
    """
    _main_thread()
    if pending is None:
        pending = active_for_scene(context.scene)
    if pending is None:
        return None
    if _cleanup_diagnostic(pending):
        if not pending._notified:
            pending._notified = True
            raise pending._abort_error
        return None
    if pending.done:
        if pending._phase != "finished" and not pending._notified:
            pending._notified = True
            raise bridge.BridgeError(pending._error)
        return None
    if pending._abort_error is None:
        try:
            _assert_inputs(context, pending)
        except Exception as exc:
            _abort(pending, exc)
    if pending._abort_error is None:
        try:
            state = pending._job.poll(
                assembly_state._current_selection(context, pending._transaction["snapshot"])
            )
        except Exception as exc:
            _abort(pending, exc)
            state = pending._job.state
    else:
        # Cleanup observation has no publication authority and needs no RNA.
        state = pending._job.state
    if _cleanup_diagnostic(pending):
        if not pending._notified:
            pending._notified = True
            raise pending._abort_error
        return None
    if pending._abort_error is not None:
        if pending._job.done:
            pending._notified = True
            _finish_failure(pending)
            raise pending._abort_error
        return None
    if state in {"created", "running", "cancelling"}:
        return None
    try:
        if assembly_bridge.fingerprint(
            pending._job.request_snapshot()
        ) != assembly_bridge.fingerprint(pending._prepared.guarded_request()):
            raise bridge.BridgeError("The detached assembly job request changed before acceptance.")
        snapshot = pending._transaction["snapshot"]
        evidence = pending._job.result(
            assembly_state._current_selection(context, snapshot),
            owner_token=snapshot["owner_token"],
        )
        _assert_inputs(context, pending)
        if pending._candidate:
            response = assembly_state._commit_candidate_evidence(
                context,
                snapshot,
                evidence,
                scene=pending._transaction["scene"],
                clear_path=not (pending._replay or pending._editing),
                publication_guard=lambda published: _assert_candidate_inputs(
                    context, snapshot, published
                ),
            )
        elif pending._rebuild:
            assembly_state._projection(
                context, snapshot, evidence, actions="assembly_replay", success=True
            )
            response = evidence
        elif pending._preview:
            try:
                assembly_state._assert_report_display(context, pending._transaction, transient=True)
                response = assembly_state._projection(
                    context, snapshot, evidence, actions="assembly_replay",
                    success=not pending._source_preview,
                )
                if pending._source_preview and not response["ok"]:
                    raise bridge.BridgeError(assembly_state._error(response))
            finally:
                # Ghosts carry no retained publication capability. Apply uses a
                # fresh exact replay and compares the previewed complete pose.
                evidence.publication.cancel()
        else:
            response = assembly_state._publish_report(context, pending._transaction, evidence)
        pending._phase = "finished"
        pending._notified = True
        _release(pending)
        return response
    except Exception as exc:
        _abort(pending, exc)
        pending._notified = True
        if pending._job.done:
            _finish_failure(pending)
        raise


def cancel(pending, reason=None):
    """Cancel even a ready-but-unpublished result; cleanup remains nonblocking."""
    _main_thread()
    if pending is None or pending.done:
        return False
    if reason is None:
        reason = (
            "Assembly replay cancelled by the user."
            if pending._replay
            else "Assembly update cancelled by the user."
            if pending._candidate
            else "Assembly check cancelled by the user."
        )
    _abort(pending, bridge.BridgeError(str(reason)), cancelled=True)
    if pending._job.done:
        _finish_failure(pending)
    return True


def reap(context=None):
    """Main-thread maintenance, with no report acceptance or context substitution.

    Cancel deleted scenes and closed originating windows when context supplies
    window_manager. Other ready results stay unpublished until their own modal
    poll. Return whether work remains, for a registration-owned timer.
    """
    _main_thread()
    live_scenes = {_scene_key(scene) for scene in assembly_state._scenes()}
    windows = getattr(getattr(context, "window_manager", None), "windows", None)
    live_windows = (
        {window.as_pointer(): _scene_key(window.scene) for window in windows}
        if windows is not None
        else None
    )
    for pending in list(_ACTIVE.values()):
        if _cleanup_diagnostic(pending):
            continue
        snapshot = pending._transaction["snapshot"]
        if pending._abort_error is None and (
            snapshot["scene_key"] not in live_scenes
            or live_windows is not None
            and snapshot["window_key"] is not None
            and live_windows.get(snapshot["window_key"]) != snapshot["scene_key"]
        ):
            _abort(
                pending,
                bridge.BridgeError(
                    "Assembly check cancelled because its original scene or window changed or closed."
                ),
                cancelled=True,
            )
        if pending._abort_error is None:
            try:
                pending._job.poll(backend_runtime.capture(assembly_state._backend_context(context)))
            except Exception as exc:
                _abort(pending, exc)
        if _cleanup_diagnostic(pending):
            continue
        if pending._abort_error is not None and pending._job.done:
            try:
                _finish_failure(pending)
            except (ReferenceError, RuntimeError):
                # A deleted original RNA target cannot receive diagnostics. The
                # handle still retains the error and its captured busy key is freed.
                pass
    return bool(_ACTIVE)


def cancel_for_configuration(reason):
    """Revoke ready/running intent without waiting; the existing supervisor reaps."""
    _main_thread()
    for pending in list(_ACTIVE.values()):
        _abort(pending, bridge.BridgeError(str(reason)), cancelled=True)
    return bool(_ACTIVE)


def detach_all(reason="Original Blender data is being invalidated."):
    """Revoke RNA recovery before load/history/unregister can free native data.

    Busy/process ownership and the pure opaque lease token survive. Retained
    transactions contain only numeric identity keys, with no scene, window,
    state, display or runtime references. The token itself retains no references.
    The no-publication supervisor may subsequently release them without Blender
    field access. Exception tracebacks are also discarded after preserving text.
    """
    _main_thread()
    for pending in list(_ACTIVE.values()):
        _abort(pending, bridge.BridgeError(str(reason)), cancelled=True)
        transaction = pending._transaction
        snapshot = transaction["snapshot"]
        pending._transaction = {
            "key": transaction["key"],
            "snapshot": {
                "scene_key": snapshot["scene_key"],
                "window_key": snapshot["window_key"],
            },
        }
        pending._detached = True
        pending._abort_error = bridge.BridgeError(pending._error)
        assembly_state._RUNTIME.pop(transaction["key"], None)


def cancel_all(reason="Assembly checks cancelled for lifecycle change.", *, wait_timeout=5.0):
    """Cancel and reap before load/history/unregister; never publish a completion.

    Return False only when OS-level cleanup has not finished within the bounded
    shutdown wait. Keep those locks until a later reap confirms cleanup; do not
    pretend a still-running native process has stopped.
    """
    _main_thread()
    jobs = list(_ACTIVE.values())
    for pending in jobs:
        _abort(pending, bridge.BridgeError(str(reason)), cancelled=True)
    deadline = time.monotonic() + max(0.0, wait_timeout)
    for pending in jobs:
        pending._job.wait(max(0.0, deadline - time.monotonic()))
        if _cleanup_diagnostic(pending):
            continue
        if pending._job.done:
            try:
                _finish_failure(pending)
            except (ReferenceError, RuntimeError):
                pass
        else:
            pending._error = str(reason) + " Native process cleanup is still pending."
    return not _ACTIVE
