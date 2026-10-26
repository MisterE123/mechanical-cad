"""Private one-shot insertion-dialog handoff to full nonpublishing Assembly review."""

import bpy
from bpy.types import Operator

from . import assembly_source_update_preview, assembly_state
from .assembly_coordinates import NO_SCALAR_COORDINATE
from .assembly_insert_preview_draft import InsertPreviewDraft
from .assembly_insert_preview_session import InsertPreviewSession as InsertPreviewSession
from .assembly_operator_helpers import canonical_working_part, extra_joint_arguments, unit_value
from .bridge import BridgeError

_HANDOFF = None
_MATE_OWNER_TYPE = None


def cancel_handoff():
    """Lifecycle cleanup; no pending insertion intent survives file/history changes."""
    global _HANDOFF
    owner, _HANDOFF = _HANDOFF, None
    if owner is not None:
        owner.cancel("Insertion handoff cancelled")


def launch(context, draft, *, mate_faces=False):
    """Synchronous, consumed-once owner handoff; never serialize candidate authority."""
    global _HANDOFF, _MATE_OWNER_TYPE
    if _HANDOFF is not None:
        raise BridgeError("Another insertion handoff is pending.")
    if mate_faces:
        from .assembly_insert_mate_preview import InsertMateSession

        _MATE_OWNER_TYPE = InsertMateSession
        owner = InsertMateSession(context, draft)
    else:
        owner = InsertPreviewSession(context, draft)
    _HANDOFF = owner
    try:
        result = bpy.ops.mcad.assembly_insert_preview("INVOKE_DEFAULT")
        if "RUNNING_MODAL" not in result:
            owner.cancel("Insertion review did not start")
        return result
    except Exception:
        owner.cancel("Insertion review launch failed")
        raise
    finally:
        if _HANDOFF is owner:
            cancel_handoff()


def launch_from_dialog(operator, context):
    """Use only current dialog fields; capture and child creation are one draft."""
    operator.require_same_working_part(context)
    state = context.scene.mechanical_cad_assembly
    if operator._expected is None or state.document_json != operator._expected:
        raise BridgeError("Assembly changed while Insert was open. Reopen it.")
    accepted = assembly_state.read_assembly(state)
    working = canonical_working_part(context) if operator.use_working_part else None
    operator.require_same_working_part(context)
    if state.document_json != operator._expected:
        raise BridgeError("Assembly changed while capturing the Part. Reopen Insert.")
    kind = operator.kind
    draft = InsertPreviewDraft(
        accepted,
        operator.part_id,
        working_part=working,
        parent=operator.parent,
        parent_frame=operator.parent_frame,
        child_frame=operator.child_frame,
        kind=kind,
        coordinate=0.0 if kind in NO_SCALAR_COORDINATE else unit_value(operator.coordinate, kind),
        limits=[unit_value(operator.lower, kind), unit_value(operator.upper, kind)]
        if operator.use_limits and kind not in NO_SCALAR_COORDINATE
        else None,
        rotation=unit_value(operator.rotation, "revolute") if kind == "cylindrical" else 0.0,
        rotation_limits=[
            unit_value(operator.rotation_lower, "revolute"),
            unit_value(operator.rotation_upper, "revolute"),
        ]
        if kind == "cylindrical" and operator.use_rotation_limits
        else None,
        extra_coordinates=extra_joint_arguments(operator, kind),
        name=operator.name,
        joint_name=operator.joint_name,
    )
    if kind == "fixed" and getattr(operator, "mate_faces", False):
        return launch(context, draft, mate_faces=True)
    return launch(context, draft)


class MCAD_OT_assembly_insert_preview(Operator):
    bl_idname = "mcad.assembly_insert_preview"
    bl_label = "Preview Component Insertion"
    bl_description = (
        "Review full geometry and named-frame placement before inserting a child and joint"
    )
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        global _HANDOFF
        owner, _HANDOFF = _HANDOFF, None
        try:
            if not (type(owner) is InsertPreviewSession
                    or _MATE_OWNER_TYPE is not None and type(owner) is _MATE_OWNER_TYPE):
                raise BridgeError("Open Insert and choose Preview to review a new component.")
            if context.area != owner.area or context.region != owner.handoff_region:
                raise BridgeError("Insertion handoff moved to another editor. Reopen Insert.")
            owner.assert_current(context)
            self.owner = owner.start(context)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            if owner is not None:
                owner.cancel("Insertion review invocation failed")
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        if type(self.owner) is InsertPreviewSession:
            return assembly_source_update_preview.MCAD_OT_assembly_source_update_preview.modal(
                self, context, event)
        return self.owner.modal_event(self, context, event)

    cancel = assembly_source_update_preview.MCAD_OT_assembly_source_update_preview.cancel


CLASSES = (MCAD_OT_assembly_insert_preview,)
