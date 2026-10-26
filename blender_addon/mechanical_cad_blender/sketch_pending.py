"""Main-thread, process-only async transport for explicit typed sketch work.

The caller owns the complete session/base/input/configuration identity and any
publication transaction. This adapter retains only bounded detached JSON, a
SidecarJob and an opaque execution lease. It never accepts a command, publishes a
scene, imports native CAD or registers a timer/handler. Lifecycle supervision
must revoke the caller's publication capability and invoke cancel_all/reap.

A ready job still owns its lease until poll validates and consumes its response,
or cancellation invalidates it. Retired jobs retain ownership until job.done
confirms actual process reaping and file cleanup. Maintenance never accepts work.
"""

from __future__ import annotations

import copy
import json
import math
import threading
import time

from . import (
    backend_contracts,
    bridge,
    execution_lease,
    guarded_transport,
    operation_contracts,
    request_contracts,
    sidecar_job,
)
from . import sketch_action_bridge as sketch_action_bridge
from .general_sketch_draft import read_guarded_operation
from .guarded_evidence import GuardedEvidence

MAX_IDENTITY_BYTES = 128 * 1024
MAX_IDENTITY_DEPTH = 16
MAX_IDENTITY_NODES = 4096
MAX_MESSAGE_CHARS = 1500
_JOB_FACTORY = sidecar_job.SidecarJob
_GUARDED_JOB_FACTORY = guarded_transport.GuardedJob
_ACTIVE = {}
_TERMINAL = frozenset({"finished", "failed", "cancelled"})


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise bridge.BridgeError("Sketch jobs require the main thread.")


def _message(value):
    # Never retain exception instances, traceback frames or caller-owned objects.
    try:
        return str(value)[:MAX_MESSAGE_CHARS]
    except Exception:
        return "Sketch sidecar operation failed."


def _identity_snapshot(identity):
    try:
        return request_contracts.snapshot_request(
            identity,
            max_bytes=MAX_IDENTITY_BYTES,
            max_depth=MAX_IDENTITY_DEPTH,
            max_nodes=MAX_IDENTITY_NODES,
        )
    except (TypeError, ValueError) as exc:
        raise bridge.BridgeError(
            "Sketch identity must be a detached finite JSON object within "
            "128 KiB, depth 16 and 4096 nodes: " + _message(exc)
        ) from None


def _exact_json(snapshot):
    # JSON spelling distinguishes bool/int/float, including signed floating zero.
    # Object member order is not an identity; array order and exact strings are.
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _request_snapshot(request):
    snapshot = sidecar_job.snapshot_request(request)
    action = snapshot.get("action")
    if (
        type(snapshot.get("protocol_version")) is not int
        or snapshot["protocol_version"] != 1
        or type(snapshot.get("result_version")) is not int
        or snapshot["result_version"] not in (2, 3)
        or type(action) is not str
        or action not in {"solve_sketch", "replay", "edge_catalog"}
    ):
        raise bridge.BridgeError(
            "Sketch jobs require explicit protocol 1, result 2 or 3 solve_sketch/replay/edge_catalog."
        )
    required = {"protocol_version", "result_version", "action", "document"}
    allowed = required | {"options"}
    if action == "solve_sketch":
        required |= {"feature_id"}
        allowed = required
    if set(snapshot) - allowed or required - set(snapshot):
        raise bridge.BridgeError("Unexpected or missing sketch job request fields.")
    if type(snapshot["document"]) is not dict:
        raise bridge.BridgeError("Sketch job document must be a JSON object.")
    if action == "solve_sketch" and (
        type(snapshot["feature_id"]) is not str or not snapshot["feature_id"]
    ):
        raise bridge.BridgeError("Solve Sketch requires an explicit feature ID.")
    if "options" in snapshot and type(snapshot["options"]) is not dict:
        raise bridge.BridgeError("Replay options must be a JSON object.")
    try:
        expected = operation_contracts.result_version_for(
            snapshot["document"], action=action, owner_role="general"
        )
        if snapshot["result_version"] != expected:
            raise ValueError("Result version differs from the complete sketch candidate.")
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise bridge.BridgeError(str(exc)) from exc
    return snapshot


def _finite_timeout(value, label):
    try:
        if type(value) not in (int, float) or not math.isfinite(float(value)):
            raise ValueError
        return float(value)
    except (ValueError, OverflowError):
        raise bridge.BridgeError(label + " must be finite and numeric.") from None


def _handle(pending):
    if type(pending) is not PendingSketch:
        raise bridge.BridgeError("Expected an async sketch handle.")
    return pending


class PendingSketch:
    """Transient main-thread handle; all public snapshots are owned copies."""

    def __init__(
        self, request, identity, job, token, *, prepared=None, selection=None, owner_token=None
    ):
        self._request = request
        self._prepared = prepared
        self.selection = selection
        self.owner_token = owner_token
        self._identity = identity
        self._request_key = _exact_json(request)
        self._identity_key = _exact_json(identity)
        self._job = job
        self._lease_token = token
        self._phase = "running"
        self._retired = None
        self._error = ""
        self._notified = False
        self._started = time.monotonic()

    @property
    def done(self):
        _main_thread()
        return self._phase in _TERMINAL

    def request_snapshot(self):
        _main_thread()
        return copy.deepcopy(self._request)

    def identity_snapshot(self):
        _main_thread()
        return copy.deepcopy(self._identity)

    def status(self):
        _main_thread()
        return {
            "phase": self._phase,
            "action": self._request["action"],
            "message": self._error,
            "done": self.done,
            "cleanup_pending": self._retired is not None and not self.done,
            "elapsed_seconds": max(0.0, time.monotonic() - self._started),
        }


def status(pending=None):
    """Read-only detached status, or a list of all retained operation statuses."""
    _main_thread()
    if pending is not None:
        return _handle(pending).status()
    return [item.status() for item in _ACTIVE.values()]


def cleanup_message():
    """Read detached retained-job diagnostics without polling or changing state."""
    _main_thread()
    for pending in _ACTIVE.values():
        diagnostic = getattr(pending._job, "cleanup_diagnostic", "")
        if type(diagnostic) is str and diagnostic:
            return execution_lease.QUARANTINE_MESSAGE
    return ""


def _cleanup_diagnostic(pending):
    """Promote an absorbing cleanup error even after cancellation/staleness."""
    diagnostic = getattr(pending._job, "cleanup_diagnostic", "")
    if type(diagnostic) is not str or not diagnostic:
        return False
    message = execution_lease.QUARANTINE_MESSAGE
    if pending._error != message:
        pending._notified = False
    pending._error = message
    pending._retired = pending._retired or "failed"
    pending._phase = "cancelling"
    return True


def _cleaned(pending):
    if _cleanup_diagnostic(pending):
        return False
    try:
        return pending._job.done is True
    except Exception as exc:
        pending._error = "Could not confirm native process cleanup: " + _message(exc)
        pending._retired = pending._retired or "failed"
        pending._phase = "cancelling"
        return False


def _release(pending):
    if not _cleaned(pending):
        return False
    if _ACTIVE.get(id(pending)) is pending:
        _ACTIVE.pop(id(pending))
    execution_lease.release(pending._lease_token)
    pending._lease_token = None
    return True


def _finish_retired(pending):
    if pending._retired is not None and _release(pending):
        pending._phase = pending._retired


def _retire(pending, reason, *, cancelled=False):
    if _cleanup_diagnostic(pending):
        return
    if pending.done:
        return
    if pending._retired is None:
        pending._retired = "cancelled" if cancelled else "failed"
        pending._error = _message(reason)
        pending._phase = "cancelling"
    try:
        pending._job.cancel()
    except Exception as exc:
        pending._error = (pending._error + " Cancellation failed: " + _message(exc))[
            :MAX_MESSAGE_CHARS
        ]
    _finish_retired(pending)


def _notify_failure(pending):
    if pending._retired is not None and not pending._notified:
        pending._notified = True
        raise bridge.BridgeError(pending._error or "Sketch sidecar operation failed.")


def prepare(request, identity, *, project_root="", python_executable="", timeout=60.0):
    """Acquire the shared gate, detach exact inputs, and explicitly start one job.

    identity must include every caller-owned acceptance binding (session/owner,
    base, commands, raw input and configuration). No context or callable belongs
    here. Busy rejection never queues or retries the requested work.
    """
    _main_thread()
    token = execution_lease.try_acquire()
    if token is None:
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    pending = None
    try:
        snapshot = _request_snapshot(request)
        captured_identity = _identity_snapshot(identity)
        if type(project_root) is not str or type(python_executable) is not str:
            raise bridge.BridgeError("Sidecar paths must be strings.")
        _finite_timeout(timeout, "Sidecar timeout")
        job = _JOB_FACTORY(
            copy.deepcopy(snapshot),
            project_root=project_root,
            python_executable=python_executable,
            timeout=timeout,
        )
        pending = PendingSketch(snapshot, captured_identity, job, token)
        _ACTIVE[id(pending)] = pending
        # Retain ownership before start, including a partial/failed worker launch.
        job.start()
        return pending
    except Exception as exc:
        if pending is None:
            execution_lease.release(token)
        else:
            _retire(pending, exc)
            pending._notified = True
        raise bridge.BridgeError(_message(exc)) from None


def prepare_guarded(prepared, identity, *, selection, owner_token):
    """Start one guarded production job under the existing cleanup/lease owner.

    Selection and request are captured by the session once. No context, callback,
    RNA value, or independent settings resolver enters this detached handle.
    """
    _main_thread()
    if type(prepared) is not backend_contracts.PreparedRequest:
        raise bridge.BridgeError("Sketch production work needs a prepared guarded request.")
    snapshot = _request_snapshot(prepared.operation_request())
    captured_identity = _identity_snapshot(identity)
    token = execution_lease.try_acquire()
    if token is None:
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    pending = None
    try:
        job = _GUARDED_JOB_FACTORY(prepared, selection, owner_token=owner_token)
        pending = PendingSketch(
            snapshot,
            captured_identity,
            job,
            token,
            prepared=prepared,
            selection=selection,
            owner_token=owner_token,
        )
        _ACTIVE[id(pending)] = pending
        job.start(selection)
        return pending
    except Exception as exc:
        if pending is None:
            execution_lease.release(token)
        else:
            _retire(pending, exc)
            pending._notified = True
        raise bridge.BridgeError(_message(exc)) from None


def poll(pending, current_identity, *, current_selection=None):
    """Return a complete validated response once, or None while pending/finished.

    Every poll checks exact caller identity before inspecting/consuming a result.
    A stale identity cancels even an already-ready response. Valid native failure
    envelopes are returned for diagnostics; they are never acceptance authority.
    Transport/protocol failures raise BridgeError once and retain cleanup ownership.
    """
    _main_thread()
    pending = _handle(pending)
    if _cleanup_diagnostic(pending):
        _notify_failure(pending)
        return None
    if pending.done:
        _notify_failure(pending)
        return None
    if pending._retired is not None:
        _retire(pending, pending._error)
        if pending.done:
            _notify_failure(pending)
        return None
    try:
        current = _identity_snapshot(current_identity)
        if _exact_json(current) != pending._identity_key:
            raise bridge.BridgeError("Sketch owner, base, input or configuration identity changed.")
    except Exception as exc:
        _retire(pending, exc, cancelled=True)
        if pending.done:
            _notify_failure(pending)
        return None
    accepted = None
    try:
        state = (
            pending._job.poll(current_selection)
            if pending._prepared is not None
            else pending._job.poll()
        )
        if state in {"created", "running", "cancelling"}:
            if state == "cancelling":
                _retire(pending, "Sketch sidecar was cancelled.", cancelled=True)
            return None
        if state not in {"ready", "failed", "cancelled"}:
            raise bridge.BridgeError("Unexpected sketch sidecar state.")
        if not _cleaned(pending):
            return None
        if state == "cancelled":
            _retire(pending, "Sketch sidecar was cancelled.", cancelled=True)
            raise bridge.BridgeError("Sketch sidecar was cancelled.")
        if pending._prepared is not None:
            transported = backend_contracts.prepare_guarded_request(pending._job.request_snapshot())
            if transported != pending._prepared:
                raise bridge.BridgeError("The exact guarded sketch transport request changed.")
            accepted = pending._job.result(current_selection, owner_token=pending.owner_token)
            read_guarded_operation(
                accepted,
                pending._prepared,
                current_selection,
                owner_token=pending.owner_token,
                action=pending._request["action"],
            )
        else:
            # Explicit legacy helper path, never used by a production session.
            transported = sidecar_job.snapshot_request(pending._job.request_snapshot())
            if _exact_json(transported) != pending._request_key:
                raise bridge.BridgeError(
                    "The exact sketch transport request changed before acceptance."
                )
            response = pending._job.result()
            accepted = operation_contracts.validate_response(pending._request, response)
        if _exact_json(_identity_snapshot(current_identity)) != pending._identity_key:
            raise bridge.BridgeError("Sketch identity changed during response validation.")
        if not _release(pending):
            raise bridge.BridgeError("Native process cleanup is not confirmed after its response.")
        pending._phase = "finished"
        return accepted
    except Exception as exc:
        if type(accepted) is GuardedEvidence:
            try:
                accepted.publication.cancel()
            except (ValueError, TypeError, AttributeError):
                pass  # Malformed exact-class data is already rejected above.
        _retire(pending, exc)
        _notify_failure(pending)
        return None


def cancel(pending, reason="Sketch operation cancelled by the user."):
    """Revoke unconsumed work immediately; never wait for a running sidecar."""
    _main_thread()
    if pending is None:
        return False
    pending = _handle(pending)
    if pending.done:
        return False
    first = pending._retired is None
    _retire(pending, reason, cancelled=True)
    return first


def reap():
    """Clean retired/failed work without consuming any response or accepting it.

    Ready successful jobs stay retained for their owner's explicit poll/cancel.
    Return whether any handle remains, for the lifecycle owner's single timer.
    """
    _main_thread()
    for pending in list(_ACTIVE.values()):
        if _cleanup_diagnostic(pending):
            continue
        if pending._retired is not None:
            _retire(pending, pending._error)
            continue
        try:
            state = pending._job.state if pending._prepared is not None else pending._job.poll()
            if state in {"cancelled", "cancelling", "failed", "consumed"}:
                _retire(
                    pending,
                    "Sketch sidecar failed or was cancelled before acceptance.",
                    cancelled=state in {"cancelled", "cancelling"},
                )
        except Exception as exc:
            _retire(pending, exc)
    return bool(_ACTIVE)


def cancel_all(reason="Sketch work cancelled for lifecycle change.", *, wait_timeout=5.0):
    """Cancel all handles and use one bounded cleanup wait; never accept results.

    Return False if cleanup is still pending. In that case the shared gate stays
    owned until a later reap confirms termination. Nothing is automatically retried.
    """
    _main_thread()
    seconds = max(0.0, min(_finite_timeout(wait_timeout, "Cleanup wait timeout"), 300.0))
    jobs = list(_ACTIVE.values())
    for pending in jobs:
        _retire(pending, reason, cancelled=True)
    deadline = time.monotonic() + seconds
    for pending in jobs:
        if not pending.done:
            try:
                pending._job.wait(max(0.0, deadline - time.monotonic()))
            except Exception as exc:
                pending._error = "Native process cleanup wait failed: " + _message(exc)
            _finish_retired(pending)
    return not _ACTIVE
