"""Explicit review of a transient proposal, separate from accepted history.

Drawing does no native work. Dialogs always bind fresh evidence to the accepted
Part and the exact retained proposal before attempting atomic publication.
"""

import json

from bpy.props import StringProperty
from bpy.types import Operator

from . import (
    document_state,
    execution_lease,
    repair_resume,
    staged_edit,
    staged_edit_store,
    workspace,
)
from .common import _state
from .end_face_repair import terminated_feature
from .help_ui import _panel_wrap
from .operators import _reject_candidate
from .projection_repair import projected_feature
from .support_intent_edit import attached_feature


def review_document(context, token, original_json):
    """Get a detached proposal only while its accepted base remains exact."""
    proposal = staged_edit.require(context, token)
    if proposal.base_json != original_json:
        raise ValueError("The accepted Part changed. Reopen the proposed edit review.")
    return proposal.document


def validate_review(context, token, original_json, document):
    """Reject expired or changed proposals before using a review's evidence."""
    proposal = staged_edit.require(context, token)
    if proposal.base_json != original_json or proposal.document != document:
        raise ValueError("The proposed edit changed. Reopen its repair dialog.")


def draw_review_notice(layout):
    box = layout.box()
    box.label(text="Reviewing proposed edit, not the accepted model", icon="INFO")
    box.label(text="Apply Repair rebuilds the entire proposed Part.")
    box.label(text="Valid repairs stay in the proposal until the entire Part succeeds.")
    box.label(text="Undo Proposal Repair reverses the last kept repair.")
    box.label(text="Cancel closes this review; the proposal and kept repairs remain.")
    box.label(text="Discard Proposed Edit abandons them; accepted model stays unchanged.")


def _repair_controls(layout, context, proposal, feature):
    enabled = (
        context.mode == "OBJECT"
        and not workspace.has_draft(context)
        and not document_state._REPLAY_RUNNING
        and not execution_lease.is_busy()
    )
    for validator, identifier, title, icon in (
        (terminated_feature, "mcad.replace_end_face", "Replace End Face", "FILE_REFRESH"),
        (attached_feature, "mcad.edit_sketch_support", "Review Support", "GREASEPENCIL"),
        (
            projected_feature,
            "mcad.replace_projection_reference",
            "Replace Reference",
            "FILE_REFRESH",
        ),
    ):
        try:
            validator(proposal.document, feature["id"])
        except ValueError:
            continue
        row = layout.row(align=True)
        row.enabled = enabled
        button = row.operator(identifier, text=title, icon=icon)
        button.feature_id = feature["id"]
        button.staged_token = proposal.token


def pending_message_is_duplicate(context, message):
    """Suppress only known retained-edit guidance, not unrelated action errors."""
    return staged_edit.current(context) is not None and any(
        text in message
        for text in (
            "Unapplied edit retained for repair; accepted model unchanged.",
            "An unapplied edit is retained for repair. Repair and accept it, or Discard proposed edit first.",
            "Repair and accept or discard the proposed edit before changing parameters; accepted model unchanged.",
        )
    )


def _excerpt(layout, context, message, *, lines=2):
    wrapped = list(_panel_wrap(context, message))
    for index, line in enumerate(wrapped[:lines]):
        if index == lines - 1 and len(wrapped) > lines:
            line = line.rstrip(".") + "…"
        layout.label(text=line)


def _proposal_details(proposal):
    document = proposal.document
    features = {feature["id"]: feature for feature in document["features"]}
    edited = features[proposal.feature_id]
    details = ["Proposed edit: " + edited["label"] + " [" + edited["id"] + "]"]
    changes = []
    accepted = {feature["id"]: feature for feature in json.loads(proposal.base_json)["features"]}
    for changed in document["features"]:
        previous = accepted[changed["id"]]
        if changed == previous:
            continue
        prefix = "" if changed["id"] == proposal.feature_id else changed["label"] + " · "
        for group in ("params", "inputs"):
            for key, value in changed.get(group, {}).items():
                old_value = previous.get(group, {}).get(key)
                if value != old_value:
                    changes.append(f"{prefix}{key}: {old_value} → {value}")
        for key in (
            "label",
            "kind",
            "support_face",
            "end_face",
            "edge_faces",
            "edge_pairs",
            "opening_faces",
        ):
            if previous.get(key) != changed.get(key):
                changes.append(f"{prefix}{key}: {previous.get(key)} → {changed.get(key)}")
    details.extend(changes)
    errors = []
    for failure in proposal.failures:
        feature = features.get(failure["id"])
        if feature is None:
            continue
        error = failure.get("error") or {}
        message = error.get("message") or "This feature needs explicit review."
        if error.get("code"):
            message = error["code"] + ": " + message
        errors.append("Failed: " + feature["label"] + " [" + feature["id"] + "] — " + message)
    details.extend(errors)
    details.extend(
        (
            "The accepted model is still shown. Save and Export use only the accepted model.",
            "Blender Save preserves repair intent separately, then suspends it for explicit Resume Repair.",
            "Apply Repair accepts the edits only when the entire Part succeeds.",
            "Valid reference repairs remain in the proposal; Undo Proposal Repair reverses them, including after Resume.",
            "Cancel closes only the current review, including after Resume; proposal history and annotation intent remain.",
            "Discard Proposed Edit deliberately abandons the live proposal and its saved checkpoint.",
            "Repair and accept, or explicitly discard the proposed edit before other editing.",
        )
    )
    return features, changes, errors, "\n\n".join(details)


def draw_staged_edit(layout, context):
    """Keep primary recovery controls ahead of bounded proposed-state details."""
    proposal = staged_edit.current(context)
    if proposal is None:
        if not staged_edit.saved_raw(context):
            return False
        box = layout.box()
        box.label(text="Saved repair work", icon="RECOVER_LAST")
        box.label(text="Not applied to model")
        # Put recovery actions before wrapped explanations, even in a narrow UI.
        row = box.row(align=True)
        row.enabled = not staged_edit_store.resume_reserved()
        row.operator_context = "INVOKE_DEFAULT"
        row.operator("mcad.resume_saved_repair", text="Resume Repair", icon="FILE_REFRESH")
        row.operator("mcad.discard_saved_repair", text="Discard", icon="TRASH")
        for line in _panel_wrap(context, "Resume checks saved repairs without applying changes."):
            box.label(text=line)
        owner = repair_resume.active_for_scene(context.scene)
        if owner is not None:
            box.operator("mcad.cancel_repair_resume", text="Cancel Resume", icon="CANCEL")
            _excerpt(box, context, owner.message, lines=2)
        button = box.operator("mcad.help", text="Repair details", icon="INFO")
        button.topic = "error.details"
        button.detail = (
            "Resume freshly validates the accepted model and all saved repair history using the current backend. "
            "It never applies edits or restores old native evidence. Only a complete successful Apply Repair accepts changes.\n\n"
            "Cancel Resume keeps the exact saved intent. After Resume, Cancel in a repair review keeps the proposal, "
            "repair history and annotation intent. Discard removes saved intent; Discard Proposed Edit abandons resumed work.\n\n"
            "Resume requires the same accepted model, scene owner, units and relevant annotation layout. "
            "Malformed, unsupported or incompatible intent stays saved until explicit Discard; failed Resume shows an error "
            "and never migrates, merges or rebinds the saved work.\n\n"
            "Loading a file restores intent only. Context or backend changes, successful Save, load and history changes still retire live ownership. "
            "Complete or discard the repair before other editing. JSON / STEP exports always use the accepted model."
        )
        layout.label(text="Accepted feature history", icon="CHECKMARK")
        return True
    features, changes, errors, details = _proposal_details(proposal)
    box = layout.box()
    box.label(text="Unapplied edit", icon="ERROR")
    box.label(text="Accepted model unchanged", icon="CHECKMARK")
    # These source-bound actions must precede all diffs and long diagnostics.
    for failure in proposal.failures:
        feature = features.get(failure["id"])
        if feature is not None:
            if len(proposal.failures) > 1:
                _excerpt(box, context, feature["label"], lines=1)
            _repair_controls(box, context, proposal, feature)
    if getattr(proposal, "repairs", ()):
        box.label(text=f"{len(proposal.repairs)} repair(s) kept in proposal", icon="INFO")
        button = box.operator(
            "mcad.undo_proposal_repair", text="Undo Proposal Repair", icon="LOOP_BACK"
        )
        button.staged_token = proposal.token
    button = box.operator("mcad.discard_proposed_edit", text="Discard Proposed Edit", icon="TRASH")
    button.staged_token = proposal.token
    for notice in (
        ".blend Save keeps intent; Resume revalidates.",
        "JSON / STEP Export use accepted model.",
    ):
        for line in _panel_wrap(context, notice):
            box.label(text=line)
    if changes:
        _excerpt(box, context, "; ".join(changes))
    if errors:
        _excerpt(box, context, " ".join(errors))
    button = box.operator("mcad.help", text="Full proposal details", icon="INFO")
    button.topic = "error.rebuild"
    button.detail = details
    layout.label(text="Accepted feature history", icon="CHECKMARK")
    return True


class MCAD_OT_discard_proposed_edit(Operator):
    bl_idname = "mcad.discard_proposed_edit"
    bl_label = "Discard Proposed Edit"
    bl_description = (
        "Forget the rejected edit and its checkpoint; leave the accepted Part and display unchanged"
    )

    staged_token: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return (
            not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
            and not staged_edit_store.resume_reserved()
        )

    def execute(self, context):
        try:
            staged_edit.discard(context, self.staged_token)
            _state(context).last_action_error = ""
            self.report({"INFO"}, "Proposed edit discarded; accepted model unchanged")
            return {"FINISHED"}
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))


class MCAD_OT_undo_proposal_repair(Operator):
    bl_idname = "mcad.undo_proposal_repair"
    bl_label = "Undo Proposal Repair"
    bl_description = "Reverse the last proposal-only repair; accepted model stays unchanged"

    staged_token: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return (
            not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
            and not staged_edit_store.resume_reserved()
        )

    def execute(self, context):
        try:
            staged_edit.undo_repair(context, self.staged_token)
            _state(context).last_action_error = ""
            self.report({"INFO"}, "Proposal repair undone; accepted model unchanged")
            return {"FINISHED"}
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))


def report_repair_kept(operator, context):
    _state(context).last_action_error = ""
    operator.report(
        {"INFO"},
        "Repair kept in proposal; accepted model unchanged. Repair remaining references or Undo Proposal Repair.",
    )
    # These dialog operators carry UNDO for full publication only. A transient
    # proposal revision must not add an empty canonical Blender history step.
    # This return is not a user Cancel: the successfully kept repair stays live.
    return {"CANCELLED"}


class MCAD_OT_resume_saved_repair(Operator):
    bl_idname = "mcad.resume_saved_repair"
    bl_label = "Resume Repair"
    bl_description = "Freshly validate saved proposal intent and its Undo history; never accept edits or restore old native evidence"

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
            and not staged_edit_store.resume_reserved()
            and bool(staged_edit.saved_raw(context))
            and staged_edit.current(context) is None
        )

    def invoke(self, context, event):
        try:
            return repair_resume.start(self, context)
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))

    def modal(self, context, event):
        return repair_resume.modal(self, context, event)

    def cancel(self, context):
        owner = getattr(self, "_repair_resume", None)
        if owner is not None:
            owner.close()

    def execute(self, context):
        # Explicit EXEC_DEFAULT/script compatibility, never the sidebar button.
        try:
            staged_edit.resume(context)
            _state(context).last_action_error = ""
            self.report({"INFO"}, "Repair resumed after fresh validation; accepted model unchanged")
            return {"FINISHED"}
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))


class MCAD_OT_cancel_repair_resume(Operator):
    bl_idname = "mcad.cancel_repair_resume"
    bl_label = "Cancel Resume"
    bl_description = (
        "Cancel pending validation; keep saved repair intent and accepted geometry unchanged"
    )

    @classmethod
    def poll(cls, context):
        return repair_resume.active_for_scene(context.scene) is not None

    def execute(self, context):
        owner = repair_resume.active_for_scene(context.scene)
        if owner is not None:
            owner.close()
        self.report({"INFO"}, "Resume cancelled; saved repair intent retained")
        return {"FINISHED"}


class MCAD_OT_discard_saved_repair(Operator):
    bl_idname = "mcad.discard_saved_repair"
    bl_label = "Discard Saved Repair"
    bl_description = "Explicitly remove saved repair intent, even if unsupported; leave accepted geometry unchanged"

    @classmethod
    def poll(cls, context):
        return (
            not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
            and not staged_edit_store.resume_reserved()
        )

    def execute(self, context):
        try:
            staged_edit.discard_saved(context)
            _state(context).last_action_error = ""
            self.report({"INFO"}, "Saved repair discarded; accepted model unchanged")
            return {"FINISHED"}
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))


CLASSES = (
    MCAD_OT_discard_proposed_edit,
    MCAD_OT_undo_proposal_repair,
    MCAD_OT_resume_saved_repair,
    MCAD_OT_discard_saved_repair,
    MCAD_OT_cancel_repair_resume,
)
