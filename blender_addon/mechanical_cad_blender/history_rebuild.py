"""One debounced accepted-model display replay after history/file restoration.

Handlers capture a main-thread binding only. A nonpersistent app timer launches
and consumes a guarded async sidecar using the existing process-only supervisor.
File Open dispatches exactly one active Part or Assembly; history remains Part-only.
There is no setup, retry loop, source refresh or Undo push.
RNA is dropped before history/load/disable; detached cleanup keeps its lease.
"""

import time
from dataclasses import dataclass

import bpy

from . import (
    assembly_job_ui,
    assembly_pending,
    assembly_state,
    backend_contracts,
    backend_runtime,
    bridge,
    document_state,
    execution_lease,
    sketch_pending,
    sketch_session,
    staged_edit_store,
    workspace,
)

DEBOUNCE_SECONDS = 0.25
CLEANUP_GRACE_SECONDS = 2.0
_PENDING = None
_SERIAL = 0
_WORKSPACE_WATCH = object()


@dataclass
class RestoredModel:
    binding: dict
    document: dict
    deadline: float
    pending: object = None
    after_load: bool = False
    dormant_intent: tuple = ()
    interaction_revision: tuple = ()
    assembly_snapshot: dict = None
    assembly_revision: int = 0


def _dormant_intent(context):
    """Opaque saved UI intent, never parsed, normalized, resumed or rebased."""
    state = context.scene.mechanical_cad
    return tuple(
        getattr(state, key, "")
        for key in ("repair_intent_json", "sketch_draft_json", "sketch_annotation_json")
    )


def _is_assembly(ticket):
    return ticket.assembly_snapshot is not None


def _state(ticket):
    scene = ticket.binding["scene"]
    return scene.mechanical_cad_assembly if _is_assembly(ticket) else scene.mechanical_cad


def _expected(ticket):
    return ticket.assembly_snapshot["fields"] if _is_assembly(ticket) else ticket.binding


def _workspace_changed():
    ticket = _PENDING
    if (
        ticket is not None
        and _is_assembly(ticket)
        and ticket.binding is not None
        and (
            getattr(bpy.context, "workspace", None) != ticket.binding["workspace"]
            or workspace.get_role(bpy.context) != "ASSEMBLY"
        )
    ):
        cancel("The active workspace changed. Replay the intended model explicitly.")


def _origin(ticket):
    return "file-open" if ticket.after_load else "Undo/Redo"


def _interaction_revision():
    return (sketch_session.interaction_revision(), staged_edit_store.interaction_revision())


def _redraw(ticket):
    """Refresh Python-owned controls, including an already-open sidebar region."""
    try:
        window = ticket.binding["window"]
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
                for region in area.regions:
                    if region.type in {"UI", "HEADER", "WINDOW"}:
                        region.tag_redraw()
    except (ReferenceError, AttributeError, TypeError):
        pass


def _notice(ticket, message):
    """Never annotate a replacement document, or resurrect freed scene RNA."""
    try:
        state = _state(ticket)
        expected = _expected(ticket)
        if (
            state.document_json == expected["document_json"]
            and state.owner_id == expected["owner_id"]
            and state.status != "READY"
        ):
            state.status = "DIRTY"
            state.error = (
                "Automatic "
                + _origin(ticket)
                + " rebuild stopped: "
                + str(message)[:1000]
                + (" Use Replay to retry." if _is_assembly(ticket) else " Use Regenerate to retry.")
            )
    except (ReferenceError, AttributeError, TypeError):
        pass


def cancel(reason="History rebuild cancelled."):
    """Revoke publication before cancelling; retain no RNA in detached cleanup."""
    global _PENDING, _SERIAL
    _SERIAL += 1
    ticket, _PENDING = _PENDING, None
    if ticket is not None:
        _notice(ticket, reason)
        _redraw(ticket)
        pending = ticket.pending
        assembly = _is_assembly(ticket)
        ticket.binding = None
        ticket.document = None
        ticket.pending = None
        ticket.dormant_intent = ()
        ticket.assembly_snapshot = None
        if assembly:
            bpy.msgbus.clear_by_owner(_WORKSPACE_WATCH)
        if pending is not None:
            try:
                if assembly:
                    assembly_pending.cancel(pending, reason)
                else:
                    sketch_pending.cancel(pending, reason)
            finally:
                assembly_job_ui.ensure_supervisor()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)


def schedule(*, after_load=False):
    """Queue once after invalidation, only with an already available backend.

    Load differs from history solely in allowing byte-bound dormant UI intent.
    Neither path starts setup, waits for setup readiness, or retries a failure.
    """
    global _PENDING
    cancel("A newer restoration replaced this rebuild.")
    context = bpy.context
    scene = getattr(context, "scene", None)
    if after_load and workspace.get_role(context) == "ASSEMBLY":
        _schedule_assembly(context)
        return
    state = getattr(scene, "mechanical_cad", None)
    if state is None or not state.document_json or state.status != "DIRTY":
        return
    try:
        _eligible(context, after_load=after_load)
        binding = document_state._capture_binding(context)
        document = document_state._read_document(state)
        ticket = RestoredModel(
            binding,
            document,
            time.monotonic() + CLEANUP_GRACE_SECONDS,
            after_load=after_load,
            dormant_intent=_dormant_intent(context),
            interaction_revision=_interaction_revision(),
        )
        _PENDING = ticket
        state.error = "Waiting to rebuild accepted CAD Part…"
        bpy.app.timers.register(_tick, first_interval=DEBOUNCE_SECONDS)
        _redraw(ticket)
    except Exception as exc:
        cancel(str(exc))
        # No process has started. Keep history invalidation and its hidden cache.
        state.error = (
            "Automatic "
            + ("file-open" if after_load else "Undo/Redo")
            + " rebuild unavailable: "
            + str(exc)[:1000]
            + (" Use Regenerate when ready.")
        )


def _assembly_eligible(context):
    if context.window is None or context.mode != "OBJECT":
        raise bridge.BridgeError("An active window in Object Mode is required.")
    if not hasattr(bpy.app.handlers, "exit_pre"):
        raise bridge.BridgeError("Native exit cleanup support is required.")
    if workspace.get_role(context) != "ASSEMBLY":
        raise bridge.BridgeError("The Assembly workspace is no longer active.")
    if workspace.active_draft() is not None:
        raise bridge.BridgeError("An active sketch draft owns the CAD interaction.")
    staged_edit_store.require_no_live_edit(context)
    state = context.scene.mechanical_cad_assembly
    if not state.owner_id:
        raise bridge.BridgeError("Saved Assembly display ownership is missing.")
    if assembly_state._RUNTIME.get(assembly_state._key(context.scene)) is not None:
        raise bridge.BridgeError("A newer assembly operation already owns this display.")


def _schedule_assembly(context):
    """Load-only branch of the same single ticket; dormant Part text is opaque."""
    global _PENDING
    state = getattr(context.scene, "mechanical_cad_assembly", None)
    if state is None or not state.document_json or state.status != "DIRTY":
        return
    serial = _SERIAL
    try:
        _assembly_eligible(context)
        binding = document_state._capture_binding(context)
        snapshot = assembly_state._capture(context, context.scene)
        document = assembly_state.read_assembly(state)
        assembly_state._preflight_assembly(document)
        if serial != _SERIAL:
            raise bridge.BridgeError("Restoration was superseded while observing backend settings.")
        ticket = RestoredModel(
            binding,
            document,
            time.monotonic() + CLEANUP_GRACE_SECONDS,
            after_load=True,
            dormant_intent=_dormant_intent(context),
            interaction_revision=_interaction_revision(),
            assembly_snapshot=snapshot,
            assembly_revision=assembly_state.interaction_revision(),
        )
        _PENDING = ticket
        # Native tab changes revoke without waiting for the replay polling timer.
        bpy.msgbus.subscribe_rna(
            key=(bpy.types.Window, "workspace"),
            owner=_WORKSPACE_WATCH,
            args=(),
            notify=_workspace_changed,
        )
        state.error = (
            "Waiting to rebuild accepted Assembly display… Saved checks remain historical."
        )
        bpy.app.timers.register(_tick, first_interval=DEBOUNCE_SECONDS)
        _redraw(ticket)
    except Exception as exc:
        cancel(str(exc))
        state.error = (
            "Automatic Assembly display rebuild unavailable: "
            + str(exc)[:1000]
            + " Use Replay when ready."
        )


def _eligible(context, *, after_load=False):
    if context.window is None or context.mode != "OBJECT":
        raise bridge.BridgeError("An active window in Object Mode is required.")
    if not hasattr(bpy.app.handlers, "exit_pre"):
        raise bridge.BridgeError("Native exit cleanup support is required.")
    if after_load:
        if workspace.get_role(context) == "ASSEMBLY":
            raise bridge.BridgeError("Assembly workspace is active; rebuild its Parts explicitly.")
        if workspace.active_draft() is not None:
            raise bridge.BridgeError("An active sketch draft owns the CAD interaction.")
        staged_edit_store.require_no_live_edit(context)
    else:
        document_state.require_no_sketch_draft(context)
        staged_edit_store.require_none(context)


def _assert_current(ticket, context):
    if _PENDING is not ticket or ticket.binding is None:
        raise bridge.BridgeError("The restored model request was retired.")
    if _is_assembly(ticket):
        _assembly_eligible(context)
    else:
        _eligible(context, after_load=ticket.after_load)
    if ticket.after_load and _dormant_intent(context) != ticket.dormant_intent:
        raise bridge.BridgeError("Saved sketch, repair or annotation intent changed.")
    if ticket.after_load and _interaction_revision() != ticket.interaction_revision:
        raise bridge.BridgeError("A sketch or repair interaction superseded this rebuild.")
    if _is_assembly(ticket):
        snapshot = ticket.assembly_snapshot
        if assembly_state.interaction_revision() != ticket.assembly_revision:
            raise bridge.BridgeError("A new assembly interaction superseded this rebuild.")
        assembly_state._assert_current(context, snapshot)
        state = context.scene.mechanical_cad_assembly
        if any(
            getattr(state, key) != snapshot["fields"][key]
            for key in (
                "report_json",
                "report_document_json",
                "report_request_json",
                "report_working_part_json",
                "report_preset_id",
            )
        ):
            raise bridge.BridgeError("Saved assembly report text changed during restoration.")
    document_state._assert_binding(context, ticket.binding)
    if backend_runtime.configuration(context)[1] != ticket.binding["deflection"]:
        raise bridge.BridgeError("Mesh tolerance changed.")
    # Configuration observation can itself revoke the request via lifecycle hooks.
    if _PENDING is not ticket or ticket.binding is None:
        raise bridge.BridgeError("The restored model request was retired.")


def _start(ticket, context):
    binding = ticket.binding
    if _is_assembly(ticket):
        ticket.pending = assembly_pending.prepare_display_rebuild(
            context, ticket.assembly_snapshot, ticket.document
        )
        context.scene.mechanical_cad_assembly.status = "BUILDING"
        context.scene.mechanical_cad_assembly.error = (
            "Rebuilding accepted Assembly display… Saved checks remain historical."
        )
        _redraw(ticket)
        return
    document_state._preflight_owned_display(context.scene)
    version = document_state._result_version(ticket.document)
    prepared = backend_contracts.prepare_request(
        {
            "protocol_version": 1,
            "action": "replay",
            "result_version": version,
            "document": ticket.document,
            "options": {"linear_deflection": binding["deflection"]},
        }
    )
    binding.update(
        prepared=prepared, request_fingerprint=prepared.fingerprint, result_version=version
    )
    ticket.pending = sketch_pending.prepare_guarded(
        prepared,
        {"operation": prepared.fingerprint},
        selection=binding["selection"],
        owner_token=binding["owner_token"],
    )
    # Start failures can leave a detached handle in cleanup even without returning it.
    context.scene.mechanical_cad.status = "BUILDING"
    context.scene.mechanical_cad.error = "Rebuilding accepted CAD Part…"
    _redraw(ticket)


def _tick():
    global _PENDING
    ticket = _PENDING
    if ticket is None:
        return None
    evidence = None
    try:
        context = bpy.context
        _assert_current(ticket, context)
        if ticket.pending is None:
            if not _is_assembly(ticket) and document_state.part_is_current(context):
                cancel("The restored Part has already been rebuilt.")
                return None
            # Only allow a short cleanup grace, never queue behind arbitrary work forever.
            if execution_lease.is_busy():
                if time.monotonic() < ticket.deadline:
                    return 0.1
                raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
            try:
                _start(ticket, context)
            finally:
                assembly_job_ui.ensure_supervisor()
            return 0.1
        binding = ticket.binding
        if _is_assembly(ticket):
            evidence = assembly_pending.poll(context, ticket.pending)
        else:
            evidence = sketch_pending.poll(
                ticket.pending,
                {"operation": binding["request_fingerprint"]},
                current_selection=backend_runtime.capture(context),
            )
        if evidence is None:
            return 0.1
        _assert_current(ticket, context)
        if _is_assembly(ticket):
            assembly_state.publish_restored_display(
                context,
                ticket.assembly_snapshot,
                evidence,
                validate_publication=lambda: _assert_current(ticket, context),
            )
            bpy.msgbus.clear_by_owner(_WORKSPACE_WATCH)
        else:
            # Poll has confirmed cleanup and released transport ownership. Only this
            # fresh evidence can reach the same regeneration sink used by manual replay.
            with document_state.replay_guard(context):
                _assert_current(ticket, context)
                document_state._preflight_owned_display(context.scene)
                document_state._apply_result(
                    context,
                    ticket.document,
                    evidence,
                    binding,
                    validate_publication=lambda: _assert_current(ticket, context),
                )
        _PENDING = None
        _redraw(ticket)
        ticket.binding = None
        ticket.document = None
        ticket.pending = None
        ticket.dormant_intent = ()
        ticket.assembly_snapshot = None
        return None
    except Exception as exc:
        if _PENDING is ticket:
            cancel(str(exc))
        return None
    finally:
        if evidence is not None:
            evidence.publication.cancel()


def active(context):
    """Read-only ownership query for a reachable, scene-local cancel control."""
    ticket = _PENDING
    try:
        return bool(
            ticket is not None
            and ticket.binding is not None
            and ticket.binding["scene"] == context.scene
            and ticket.binding["window"] == context.window
        )
    except (ReferenceError, AttributeError):
        return False


def draw_cancel(layout, context):
    if not active(context):
        return False
    layout.operator("mcad.cancel_history_rebuild", text="Cancel Rebuild", icon="CANCEL")
    return True


class MCAD_OT_cancel_history_rebuild(bpy.types.Operator):
    bl_idname = "mcad.cancel_history_rebuild"
    bl_label = "Cancel Rebuild"
    bl_description = (
        "Stop automatic accepted-model display rebuilding; manually Replay or Rebuild later"
    )

    @classmethod
    def poll(cls, context):
        return active(context)

    def execute(self, context):
        cancel("Cancelled by you; the restored model is unchanged.")
        return {"FINISHED"}


CLASSES = (MCAD_OT_cancel_history_rebuild,)
