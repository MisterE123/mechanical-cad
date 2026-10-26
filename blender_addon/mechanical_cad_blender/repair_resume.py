"""Cancellable main-thread Resume owner over the shared guarded job adapter.

No worker receives Blender RNA. A reservation spans native jobs without holding
an execution lease or claiming publication authority. Only the final validated
ownership transfer may clear saved intent; cancel never writes that slot.
"""

import hashlib
import threading
import time

import bpy

from . import (
    assembly_job_ui,
    backend_contracts,
    backend_runtime,
    bridge,
    document_state,
    execution_lease,
    extrusion_preview,
    sketch_pending,
    staged_edit,
    staged_edit_store,
)

_OWNERS = []


def active_for_scene(scene):
    return next((owner for owner in _OWNERS if owner.scene == scene and not owner.closed), None)


def cancel_all(reason="Repair Resume cancelled"):
    for owner in tuple(_OWNERS):
        owner.close(reason)


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise bridge.BridgeError("Repair Resume requires Blender's main thread.")


class ResumeOwner:
    def __init__(self, context):
        _main_thread()
        if context.window is None or context.area is None or context.area.type != "VIEW_3D":
            raise bridge.BridgeError("Start Resume Repair from a 3D View.")
        self.closed = False
        self.success = False
        self.message = "Preparing repair Resume"
        self.pending = None
        self.plan = None
        self.reservation = object()
        self.scene = context.scene
        self.window = context.window
        self.area = context.area
        self.workspace = context.workspace
        self.manager = context.window_manager
        self.timer = None
        self._window_pointer = context.window.as_pointer()
        self.started = time.monotonic()
        self.identity = None
        if execution_lease.is_busy():
            raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
        self.plan = staged_edit.ResumeValidation(context)
        try:
            self.raw_digest = hashlib.sha256(self.plan.raw.encode()).hexdigest()
            staged_edit_store.reserve_resume(context, self.plan.raw, self.reservation)
            self.plan.reservation = self.reservation
            _OWNERS.append(self)
            self.plan.assert_current(context)
            # Stop debounced previews before they can acquire a lease in a gap.
            # A running/ready job was rejected by the real lease gate above.
            extrusion_preview.cancel_all("Repair Resume started")
            self.timer = self.manager.event_timer_add(0.1, window=self.window)
            assembly_job_ui.watch_owner(self)
            self._update_message()
        except Exception:
            self.close("Repair Resume interaction could not start")
            raise

    def _update_message(self):
        if self.plan is not None:
            self.message = f"{self.plan.label} · {self.plan.completed_requests} checks finished · {time.monotonic() - self.started:.1f}s"
        staged_edit_store._notify_changed()

    def assert_current(self, context):
        if self.closed or self.plan is None:
            raise bridge.BridgeError("Repair Resume was cancelled or replaced.")
        if (
            self.window not in tuple(context.window_manager.windows)
            or self.window.scene != self.scene
            or self.window.workspace != self.workspace
            or self.area not in tuple(self.window.screen.areas)
            or self.area.type != "VIEW_3D"
            or context.mode != "OBJECT"
        ):
            raise bridge.BridgeError(
                "Repair Resume window, editor, scene, workspace or mode changed."
            )
        self.plan.assert_current(context)
        # Backend reads above may synchronously revoke this owner.
        if self.closed or self.plan is None:
            raise bridge.BridgeError("Repair Resume was revoked during its context check.")
        staged_edit_store.require_resume(self.reservation)

    def _supervise_owner(self, context):
        """Revoke missing/stale owners only; never poll, advance or install."""
        if self.closed:
            return
        try:
            with context.temp_override(window=self.window, area=self.area):
                self.assert_current(bpy.context)
        except Exception as exc:
            self.close(str(exc))

    def _cleanup_ui(self):
        self.close("Repair Resume window closed; saved intent retained")

    def close(self, reason="Repair Resume cancelled; saved intent retained", *, success=False):
        _main_thread()
        if self.closed:
            return
        self.closed = True
        self.success = success
        self.message = str(reason)[:1500]
        pending, manager, timer = self.pending, self.manager, self.timer
        if self.plan is not None:
            self.plan.retire()
        self.pending = self.plan = self.timer = None
        self.window = self.scene = self.area = self.workspace = self.manager = None
        self.identity = None
        staged_edit_store.release_resume(self.reservation)
        if self in _OWNERS:
            _OWNERS.remove(self)
        # Detach original-scene UI references before native cleanup. The adapter
        # alone retains detached process/lease responsibility until reaped.
        try:
            assembly_job_ui.unwatch_owner(self)
            if timer is not None:
                try:
                    manager.event_timer_remove(timer)
                except Exception:
                    pass  # Lost UI must never strand a native child.
        finally:
            if pending is not None:
                try:
                    sketch_pending.cancel(pending, reason)
                finally:
                    assembly_job_ui.ensure_supervisor()
        staged_edit_store._notify_changed()

    def tick(self, context):
        _main_thread()
        if self.closed:
            return
        try:
            self.assert_current(context)
            if self.pending is None:
                if self.plan.complete:
                    if execution_lease.is_busy():
                        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
                    self.plan.install(context)
                    self.close(
                        "Repair resumed after fresh validation; accepted model unchanged",
                        success=True,
                    )
                    return
                binding = self.plan.binding
                prepared = backend_contracts.prepare_request(
                    {
                        "protocol_version": 1,
                        "action": "replay",
                        "result_version": document_state._result_version(self.plan.document),
                        "document": self.plan.document,
                        "options": {"linear_deflection": binding["deflection"]},
                    }
                )
                binding.update(
                    prepared=prepared,
                    request_fingerprint=prepared.fingerprint,
                    result_version=prepared.operation_request()["result_version"],
                )
                self.identity = {
                    "raw": self.raw_digest,
                    "base": self.plan.value["base_hash"],
                    "step": self.plan.completed_requests,
                    "request": prepared.fingerprint,
                }
                self.assert_current(context)
                try:
                    self.pending = sketch_pending.prepare_guarded(
                        prepared,
                        self.identity,
                        selection=binding["selection"],
                        owner_token=binding["owner_token"],
                    )
                finally:
                    # A partially started adapter handle can outlive a throwing
                    # prepare call even when no handle was returned to this owner.
                    assembly_job_ui.ensure_supervisor()
                self._update_message()
                return
            selection, _ = backend_runtime.configuration(context)
            self.assert_current(context)
            evidence = sketch_pending.poll(self.pending, self.identity, current_selection=selection)
            if evidence is None:
                self._update_message()
                return
            self.pending = None
            try:
                self.assert_current(context)
                result = document_state._evidence_projection(
                    context, self.plan.document, evidence, self.plan.binding
                )["result"]
                self.plan.advance(context, result)
            finally:
                evidence.publication.cancel()
            # Deliberately leave a main-thread event gap before the next job or
            # install, with the input reservation intact and Cancel available.
            self._update_message()
        except Exception as exc:
            self.close(str(exc))
            raise


def start(operator, context):
    owner = ResumeOwner(context)
    operator._repair_resume = owner
    try:
        context.window_manager.modal_handler_add(operator)
    except Exception:
        owner.close("Repair Resume modal interaction could not start")
        raise
    return {"RUNNING_MODAL"}


def modal(operator, context, event):
    owner = getattr(operator, "_repair_resume", None)
    if owner is None:
        return {"CANCELLED"}
    if event.type == "ESC" and event.value == "PRESS":
        owner.close()
    elif not owner.closed and event.type == "TIMER":
        try:
            owner.tick(context)
        except Exception:
            pass  # The owner has retired safely and retains a bounded message.
    elif not owner.closed:
        return {"PASS_THROUGH"}
    if not owner.closed:
        return {"RUNNING_MODAL"}
    operator.report({"INFO"} if owner.success else {"WARNING"}, owner.message[:1000])
    operator._repair_resume = None
    return {"FINISHED"} if owner.success else {"CANCELLED"}
