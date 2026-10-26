"""Assembly modal controls and shared process-only native job supervision.

The transport thread never accesses Blender. Modal timers consume guarded results;
a separate supervisor reaps cancelled jobs if the originating window disappears.
"""

import time

import bpy
from bpy.types import Operator

from . import assembly_pending, assembly_state, bridge, execution_lease, sketch_pending
from .help_ui import _panel_wrap

_OPERATORS = []


def draw_backend_failure(layout, context):
    """Bounded display of retained cleanup failure; never poll or start work."""
    message = (
        execution_lease.cleanup_message()
        or sketch_pending.cleanup_message()
        or assembly_pending.cleanup_message()
    )
    if not message:
        return False
    box = layout.box()
    box.alert = True
    box.label(text="Native operations blocked", icon="ERROR")
    for line in _panel_wrap(context, message):
        box.label(text=line)
    return True


def draw_workload(layout, context, pose_count=1):
    data = assembly_state.read_assembly(context.scene.mechanical_cad_assembly)
    count = len(data["instances"])
    pairs = count * (count - 1) // 2
    layout.label(text=f"{count} instances · {pairs} pairs × {pose_count} poses")
    layout.label(text=f"Requested pair checks: {pairs * pose_count}; fresh Part replay included")
    preset = next(
        (p for p in data["verification_presets"] if p["id"] == data["active_verification_preset"]),
        None,
    )
    layout.label(text="Preset: " + (preset["name"] if preset else "None · measurements only"))
    layout.label(text="Navigate while checking. Esc or Cancel Check stops the request.")
    layout.label(text="Previous evidence stays unchanged unless this exact request finishes.")


def draw_pending(layout, context):
    details = assembly_pending.status(context.scene)
    if not details:
        return False
    box = layout.box()
    if details.get("replay"):
        box.label(text="Replaying assembly · " + details["state"], icon="TIME")
        box.label(text=f"{details['elapsed_seconds']:.1f} s elapsed · native geometry replay")
        for message in (
            "Accepted geometry and checks retained until completion.",
            "Replay is not an interference check. Navigate while waiting.",
        ):
            for line in _panel_wrap(context, message):
                box.label(text=line)
        if details["message"]:
            for line in _panel_wrap(context, details["message"]):
                box.label(text=line, icon="ERROR")
        row = box.row()
        row.enabled = details["message"] != execution_lease.QUARANTINE_MESSAGE
        row.operator("mcad.assembly_cancel_check", text="Cancel Replay", icon="CANCEL")
        return True
    if details.get("candidate"):
        box.label(
            text=("Editing" if details.get("editing") else "Creating")
            + " assembly · "
            + details["state"],
            icon="TIME",
        )
        box.label(text=f"{details['elapsed_seconds']:.1f} s elapsed · full native validation")
        for message in ("Accepted assembly unchanged.", "Interference NOT checked by this update."):
            for line in _panel_wrap(context, message):
                box.label(text=line)
        if details["message"]:
            for line in _panel_wrap(context, details["message"]):
                box.label(text=line, icon="ERROR")
        row = box.row()
        row.enabled = details["message"] != execution_lease.QUARANTINE_MESSAGE
        row.operator(
            "mcad.assembly_cancel_check",
            text="Cancel Edit" if details.get("editing") else "Cancel Creation",
            icon="CANCEL",
        )
        return True
    if details.get("rebuild"):
        box.label(text="Assembly display rebuild · " + details["state"], icon="TIME")
        box.label(text="Accepted sources only. Saved checks remain historical.")
        if details["message"]:
            for line in _panel_wrap(context, details["message"]):
                box.label(text=line, icon="ERROR")
        box.operator("mcad.cancel_history_rebuild", text="Cancel Rebuild", icon="CANCEL")
        return True
    if details.get("insert_preview"):
        box.label(text="Insertion preview · " + details["state"], icon="TIME")
        box.label(text=f"{details['elapsed_seconds']:.1f} s elapsed · accepted Assembly retained")
        if details["message"]:
            for message in _panel_wrap(context, details["message"]):
                box.label(text=message, icon="ERROR")
        box.operator("mcad.assembly_source_update_cancel", text="Cancel Insertion Preview", icon="CANCEL")
        return True
    if details.get("source_preview"):
        box.label(text="Source update preview · " + details["state"], icon="TIME")
        box.label(text=f"{details['elapsed_seconds']:.1f} s elapsed · accepted source retained")
        if details["message"]:
            for message in _panel_wrap(context, details["message"]):
                box.label(text=message, icon="ERROR")
        box.operator("mcad.assembly_source_update_cancel", text="Cancel Source Preview", icon="CANCEL")
        return True
    if details.get("preview"):
        box.label(text="Driver motion preview · " + details["state"], icon="TIME")
        box.label(text="Full assembly replay. Accepted display and checks retained.")
        if details["message"]:
            for line in _panel_wrap(context, details["message"]):
                box.label(text=line, icon="ERROR")
        box.operator(
            "mcad.assembly_visual_joint_cancel", text="Cancel Motion Preview", icon="CANCEL"
        )
        return True
    box.label(text="Assembly check · " + details["state"].replace("_", " "), icon="TIME")
    box.label(
        text=f"{details['pairs_per_pose']} pairs × {details['pose_count']} poses · "
        f"{details['elapsed_seconds']:.1f} s elapsed"
    )
    box.label(text="Previous evidence retained. No partial result is current.")
    if details["message"]:
        for line in _panel_wrap(context, details["message"]):
            box.label(text=line, icon="ERROR")
    row = box.row()
    row.enabled = details["message"] != execution_lease.QUARANTINE_MESSAGE
    row.operator("mcad.assembly_cancel_check", text="Cancel Check", icon="CANCEL")
    return True


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _supervise():
    # Cleanup must survive add-on disable until the worker has actually reaped
    # its process. It never publishes, even after Scene RNA is unregistered.
    active = False
    for reap in (lambda: assembly_pending.reap(bpy.context), sketch_pending.reap):
        try:
            active = reap() or active
        except Exception as exc:
            # One failed adapter must not strand the other adapter's process.
            # Keep no exception/traceback or native context in retained state.
            print("Mechanical CAD native job supervision:", str(exc))
            active = True
    try:
        windows = {window.as_pointer() for window in bpy.context.window_manager.windows}
        for operator in list(_OPERATORS):
            if operator._window_pointer not in windows:
                operator._cleanup_ui()
            elif hasattr(operator, "_supervise_owner"):
                operator._supervise_owner(bpy.context)
        _redraw()
    except Exception as exc:
        # Missing UI resources must not let Blender discard a timer still
        # responsible for reaping either adapter's owned native process.
        print("Mechanical CAD job interaction supervision:", str(exc))
    return 0.1 if active or _OPERATORS else None


def ensure_supervisor():
    """Cover an explicitly started/cancelled job with the one cleanup timer.

    General editors call this after acquiring or cancelling their transport.
    The persistent supervisor only reaps; it cannot accept a successful result.
    """
    if not bpy.app.timers.is_registered(_supervise):
        bpy.app.timers.register(_supervise, first_interval=0.1, persistent=True)


def watch_owner(owner):
    """Reuse the one native cleanup supervisor for a main-thread input owner."""
    if owner not in _OPERATORS:
        _OPERATORS.append(owner)
    ensure_supervisor()


def unwatch_owner(owner):
    if owner in _OPERATORS:
        _OPERATORS.remove(owner)


class AssemblyJobMixin:
    """Shared modal implementation; Check starts directly; Sample/creation retain their input dialogs."""

    _asynchronous = False
    _ui_closed = True
    _pending = None
    _timer = None
    _manager = None
    _workspace = None
    _window_pointer = None

    def _require_job_support(self):
        if not hasattr(bpy.app.handlers, "exit_pre"):
            raise bridge.BridgeError(
                "Cancellable assembly operations require Blender 5.2 LTS with native exit cleanup."
            )

    def begin_job(self, context, action, **arguments):
        self._require_job_support()
        self._pending = assembly_pending.prepare(context, action, **arguments)
        return self._begin_pending(context, "Checking assembly. Esc or Cancel Check to stop.")

    def begin_replay(self, context):
        self._require_job_support()
        try:
            self._pending = assembly_pending.prepare_replay(context)
        finally:
            ensure_supervisor()
        return self._begin_pending(context, "Replaying assembly. Esc or Cancel Replay to stop.")

    def begin_candidate(self, context, candidate, snapshot, *, editing=False):
        self._require_job_support()
        try:
            self._pending = assembly_pending.prepare_candidate(
                context, candidate, snapshot, editing=editing
            )
        finally:
            # A start failure can leave a cancelling job registered until native
            # reaping finishes. Cover it before any modal UI setup is attempted.
            ensure_supervisor()
        return self._begin_pending(context, "Updating assembly. Esc or Cancel to stop.")

    def _begin_pending(self, context, status_text):
        self._ui_closed = False
        try:
            self._manager = context.window_manager
            self._window_pointer = context.window.as_pointer()
            self._workspace = context.workspace
            self._timer = self._manager.event_timer_add(0.1, window=context.window)
            self._manager.modal_handler_add(self)
            _OPERATORS.append(self)
            self._workspace.status_text_set(status_text)
            ensure_supervisor()
        except Exception:
            assembly_pending.cancel(self._pending, "Could not start the assembly interaction.")
            cancel_all("Assembly interaction setup failed.")
            self._cleanup_ui()
            raise
        return {"RUNNING_MODAL"}

    def _cleanup_ui(self):
        self._ui_closed = True
        if self._timer is not None and self._manager is not None:
            try:
                self._manager.event_timer_remove(self._timer)
            except (ReferenceError, RuntimeError):
                pass
        self._timer = None
        if self._workspace is not None:
            try:
                self._workspace.status_text_set(None)
            except (ReferenceError, RuntimeError):
                pass
        if self in _OPERATORS:
            _OPERATORS.remove(self)

    def modal(self, context, event):
        if self._ui_closed:
            return {"CANCELLED"}
        if event.type == "ESC" and event.value == "PRESS":
            assembly_pending.cancel(self._pending)
            return {"RUNNING_MODAL"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        try:
            response = assembly_pending.poll(context, self._pending)
        except Exception as exc:
            if self._pending is not None and not self._pending.done:
                assembly_pending.cancel(self._pending, str(exc))
            self._cleanup_ui()
            self._job_failed(context, exc)
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        if response is None:
            return {"RUNNING_MODAL"}
        self._cleanup_ui()
        try:
            self._job_accepted(context, response)
        except Exception as exc:
            # Acceptance is complete. A focus/status failure must not discard
            # the operator's FINISHED/Undo boundary or pretend creation failed.
            self.report({"WARNING"}, "Assembly accepted; focus needs attention: " + str(exc))
        self.report({"INFO"}, context.scene.mechanical_cad_assembly.verification_message[:1000])
        return {"FINISHED"}

    def _job_accepted(self, context, response):
        pass

    def _job_failed(self, context, exc):
        pass

    def cancel(self, context):
        if self._pending is not None and not self._pending.done:
            assembly_pending.cancel(self._pending)
        self._cleanup_ui()


class MCAD_OT_assembly_cancel_check(Operator):
    bl_idname = "mcad.assembly_cancel_check"
    bl_label = "Cancel Assembly Operation"
    bl_description = (
        "Stop this pending sidecar request without changing accepted geometry or evidence"
    )

    @classmethod
    def poll(cls, context):
        return bool(assembly_pending.active_for_scene(context.scene))

    def execute(self, context):
        job = assembly_pending.active_for_scene(context.scene)
        if job:
            assembly_pending.cancel(job)
        return {"FINISHED"}


def cancel_for_configuration(reason):
    """Nonblocking settings revocation under the existing cleanup supervisor.

    Cancellation never releases a running job's lease. The same supervisor
    keeps ownership until the worker has reaped its child and closed its files.
    """
    failures = []
    active = False
    try:
        active = assembly_pending.cancel_for_configuration(reason) or active
    except Exception as exc:
        failures.append(str(exc))
    try:
        complete = sketch_pending.cancel_all(reason, wait_timeout=0.0)
        active = not complete or active
    except Exception as exc:
        failures.append(str(exc))
    for operator in list(_OPERATORS):
        try:
            operator._cleanup_ui()
        except Exception as exc:
            failures.append(str(exc))
    if active or _OPERATORS or failures:
        ensure_supervisor()
    elif bpy.app.timers.is_registered(_supervise):
        bpy.app.timers.unregister(_supervise)
    if failures:
        raise bridge.BridgeError(
            "Backend work was revoked; cleanup needs attention: " + "; ".join(failures)
        )


def cancel_all(reason, *, detach=False):
    """Revoke both adapters with one five-second total cleanup deadline.

    The shared sketch owner must retire its input/publication intent first.
    Sketch handles are already detached data; legacy assembly transactions are
    detached here when their original RNA is about to be invalidated.
    """
    deadline = time.monotonic() + 5.0
    complete = True
    for adapter in (assembly_pending, sketch_pending):
        try:
            adapter_complete = adapter.cancel_all(
                reason, wait_timeout=max(0.0, deadline - time.monotonic())
            )
            complete = adapter_complete and complete
        except Exception as exc:
            print("Mechanical CAD native job cancellation:", str(exc))
            complete = False
        finally:
            if detach and adapter is assembly_pending:
                try:
                    assembly_pending.detach_all(reason)
                except Exception as exc:
                    print("Mechanical CAD assembly job detachment:", str(exc))
                    complete = False
    for operator in list(_OPERATORS):
        try:
            operator._cleanup_ui()
        except Exception as exc:
            print("Mechanical CAD job interaction cleanup:", str(exc))
            complete = False
    if complete:
        if bpy.app.timers.is_registered(_supervise):
            bpy.app.timers.unregister(_supervise)
    else:
        ensure_supervisor()
    return complete


def unregister():
    cancel_all("Add-on disabled; pending native work cancelled.", detach=True)


CLASSES = (MCAD_OT_assembly_cancel_check,)
