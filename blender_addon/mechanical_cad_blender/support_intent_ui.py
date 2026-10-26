"""Explain and explicitly revise an attached sketch's saved support policy."""

import json
import textwrap

from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import document_state, execution_lease, workspace
from .common import _state
from .help_ui import (
    _draw_feature_help,
    _feature_help_previous,
    _panel_wrap,
)
from .operators import _reject_candidate, _report_result
from .support_intent_edit import (
    ORIENTATION_ITEMS,
    POLICY_ITEMS,
    attached_feature,
    edit_support_candidate,
    eligible_support_ids,
    orientation_choice,
    support_decision,
)
from .support_presentation import support_status, support_text
from .topology_labels import face_label

_CHOICES = {}


def _selected(context):
    state = _state(context)
    if not 0 <= state.feature_index < len(state.features):
        raise ValueError("Select a face-attached sketch in Feature History.")
    return attached_feature(
        document_state._read_document(state), state.features[state.feature_index].feature_id
    )


def _choices(key, values, empty):
    key = (key, tuple(values))
    _CHOICES[key] = values or [("NONE", empty, "")]
    return _CHOICES[key]


def _source_items(document, feature_id, result):
    values = []
    if document:
        allowed = eligible_support_ids(document, feature_id)
        labels = {f["id"]: f["label"] for f in document["features"]}
        values = [
            (row["id"], labels.get(row["id"], row["id"]) + " [" + row["id"] + "]", row["id"])
            for row in result.get("features", ())
            if row["id"] in allowed
            and row["status"] == "ok"
            and row.get("output", {}).get("kind") == "solid"
        ]
        original = attached_feature(document, feature_id)["inputs"]["support"]
        if original not in {item[0] for item in values}:
            values.insert(
                0, (original, labels.get(original, original) + " (needs review)", original)
            )
    return _choices("sources", values, "No successful supporting solid")


def _face_items(document, feature_id, result, source):
    values = []
    for row in result.get("features", ()):
        if row["id"] == source and row["status"] == "ok":
            values = [
                (
                    face["id"],
                    face_label(face)
                    if face["role"].startswith("shell.")
                    else face["role"] + " [" + face["id"] + "]",
                    face["id"],
                )
                for face in row.get("topology", ())
                if face.get("provenance", {}).get("semantic_status") == "stable"
                and face.get("signature", {}).get("surface") == "plane"
            ]
    if document:
        original = attached_feature(document, feature_id)
        if original["inputs"]["support"] == source:
            identifier = original["support_face"]
            if identifier not in {item[0] for item in values}:
                label = (
                    "Saved logical support"
                    if "support_intent" in original
                    else "Saved support (needs review)"
                )
                values.insert(0, (identifier, label, identifier))
    return _choices(("faces", source), values, "Choose a solid with a stable planar face")


def _sources(self, context):
    # Enum callbacks receive OperatorProperties, not necessarily the Python
    # Operator instance used by invoke. Only RNA properties cross that boundary.
    choices = json.loads(self.review_choices_json or "{}")
    values = [tuple(item) for item in choices.get("sources", ())]
    return _choices("sources", values, "No successful supporting solid")


def _faces(self, context):
    choices = json.loads(self.review_choices_json or "{}")
    values = [tuple(item) for item in choices.get("faces", {}).get(self.support_source, ())]
    return _choices(("faces", self.support_source), values, "Choose a stable planar face")


def _source_changed(self, context):
    values = _faces(self, context)
    if self.support_face not in {item[0] for item in values}:
        self.support_face = values[0][0]


def _support_why(layout, detail):
    """Keep all evidence available in bounded pages, not a tall sidebar report."""
    operator = layout.operator("mcad.help", text="Why?", icon="QUESTION")
    operator.topic = "sketch.support_intent"
    operator.detail = detail


def draw_support_intent(layout, context, *, presentation=None):
    """Contextual history disclosure; no native work or model edits on draw."""
    owner = workspace.active_draft(context)
    if owner is not None:
        notice = getattr(owner, "support_notice", "")
        if notice:
            box = layout.box()
            decision = getattr(owner, "support_decision", None)
            text, icon = support_status(decision)
            box.label(text=text, icon=icon)
            detail = notice
            if decision and decision.get("reason"):
                detail += "\n" + decision["reason"]
            _support_why(box, detail)
        return
    try:
        feature = _selected(context)
    except (ValueError, KeyError, TypeError, IndexError):
        return
    box = layout.box()
    if presentation is None:
        values = support_text(feature, document_state.current_part_result(context))
    else:
        values = presentation.selected_support(context, feature)
        if values is None:
            values = support_text(feature, None)
    text, icon, detail, error = values
    box.label(text=text, icon=icon)
    if error:
        # Keep the failure visible and readable without an unbounded report.
        # Why retains the complete diagnostic, including any clipped suffix.
        for line in _panel_wrap(context, textwrap.shorten(error, width=64, placeholder="...")):
            box.label(text=line)
    row = box.row(align=True)
    row.operator(
        "mcad.edit_sketch_support", text="Review Support", icon="GREASEPENCIL"
    ).feature_id = feature["id"]
    _support_why(row, detail)


def _review_help_next(self, context):
    # The visible Next control is bounded by the current decision's page count.
    # Do not consult Python-only evidence attributes through RNA callback wrappers.
    if self.help_next:
        self.help_page += 1
        self.help_next = False


class MCAD_OT_edit_sketch_support(Operator):
    bl_idname = "mcad.edit_sketch_support"
    bl_label = "Review Sketch Support"
    bl_description = "Explain the saved support, change its policy or select another face; Blender Undo restores the edit"
    bl_options = {"REGISTER", "UNDO"}

    feature_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    original_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    staged_token: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    review_choices_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    policy: EnumProperty(name="Support policy", items=POLICY_ITEMS, default="PRESERVE_PLANE")
    orientation: EnumProperty(name="Orientation", items=ORIENTATION_ITEMS, default="MINIMAL_TWIST")
    reset_frame: BoolProperty(
        name="Reset saved frame here",
        description="Explicitly adopt the current world-axis frame as a new baseline; may rotate or move the sketch",
        default=False,
        options={"SKIP_SAVE"},
    )
    support_source: EnumProperty(name="Supporting solid", items=_sources, update=_source_changed)
    support_face: EnumProperty(name="Supporting face", items=_faces)
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})
    help_page: IntProperty(default=1, min=1, options={"SKIP_SAVE"})
    help_previous: BoolProperty(update=_feature_help_previous, options={"SKIP_SAVE"})
    help_next: BoolProperty(update=_review_help_next, options={"SKIP_SAVE"})
    help_topic = "sketch.support_intent"
    help_summary = (
        "Full current decision and recovery limits are available here.",
        "Help stays in this dialog and preserves your choices.",
    )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and bool(_state(context).document_json)
            and not workspace.has_draft(context)
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
        )

    def _release(self):
        evidence = getattr(self, "_review_evidence", None)
        if evidence is not None:
            evidence.publication.cancel()
            self._review_evidence = None

    def _review(self, context):
        if _state(context).document_json != self.original_json:
            raise ValueError("The Part changed while this dialog was open. Reopen Review Support.")
        if getattr(self, "staged_token", ""):
            from .staged_edit_ui import validate_review

            validate_review(context, self.staged_token, self.original_json, self._document)
        document_state._assert_binding(context, self._binding)
        return document_state._evidence_projection(
            context, self._document, self._review_evidence, self._binding
        )["result"]

    def invoke(self, context, event):
        try:
            self.original_json = _state(context).document_json
            if getattr(self, "staged_token", ""):
                from .staged_edit_ui import review_document

                self._document = review_document(context, self.staged_token, self.original_json)
            else:
                self._document = json.loads(self.original_json)
            if not self.feature_id:
                self.feature_id = _selected(context)["id"]
            feature = attached_feature(self._document, self.feature_id)
            # A failed downstream sketch must not hide its valid upstream solid.
            # This read-only replay keeps partial diagnostics but publishes nothing.
            with document_state.replay_guard(context):
                self._binding = document_state._capture_binding(context)
                self._review_evidence = document_state._run_sidecar(
                    context, self._document, binding=self._binding
                )
                self._review_result = self._review(context)
            sources = _source_items(self._document, self.feature_id, self._review_result)
            self.review_choices_json = json.dumps(
                {
                    "sources": sources,
                    "faces": {
                        source: _face_items(
                            self._document, self.feature_id, self._review_result, source
                        )
                        for source, _label, _description in sources
                    },
                }
            )
            self.support_source = feature["inputs"]["support"]
            self.support_face = feature["support_face"]
            self.policy = "PRESERVE_PLANE" if "support_intent" in feature else "STRICT"
            self.orientation = orientation_choice(feature.get("support_intent"))
            self.reset_frame = False
            return context.window_manager.invoke_props_dialog(
                self,
                width=620,
                confirm_text="Apply Repair" if getattr(self, "staged_token", "") else "Apply",
            )
        except Exception as exc:
            self._release()
            return _reject_candidate(self, context, str(exc))

    def draw(self, context):
        layout = self.layout
        staged = bool(getattr(self, "staged_token", ""))
        layout.label(text=("Proposed sketch: " if staged else "Saved sketch: ") + self.feature_id)
        if staged:
            layout.label(text="Apply Repair keeps valid progress in the unapplied proposal.")
            layout.label(
                text="Only full success accepts the model. Undo Proposal Repair reverses progress."
            )
            layout.label(
                text="Cancel keeps proposal and repairs. Discard Proposed Edit abandons them."
            )
        layout.prop(self, "policy")
        layout.prop(self, "support_source")
        layout.prop(self, "support_face")
        orientation = layout.row()
        orientation.enabled = self.policy == "PRESERVE_PLANE"
        orientation.prop(self, "orientation")
        reset = layout.row()
        reset.enabled = self.policy == "PRESERVE_PLANE" and self.orientation == "MINIMAL_TWIST"
        reset.prop(self, "reset_frame")
        warning = layout.row()
        warning.alert = reset.enabled and self.reset_frame
        warning.label(
            text="Reset adopts World axes as a new baseline; may move or rotate geometry."
            if warning.alert
            else "Frame reset is optional and can move or rotate geometry."
        )
        try:
            candidate = edit_support_candidate(
                self._document,
                self.feature_id,
                self.policy,
                self.support_source,
                self.support_face,
                self._review_result,
                orientation=self.orientation,
                reset_frame=(
                    self.reset_frame
                    and self.policy == "PRESERVE_PLANE"
                    and self.orientation == "MINIMAL_TWIST"
                ),
            )
            decision = support_decision(
                attached_feature(candidate, self.feature_id), self._review_result
            )
            message = ("ASSUMPTION: " if decision["status"] == "assumed" else "Exact: ") + decision[
                "reason"
            ]
            original = attached_feature(self._document, self.feature_id)
            if decision.get("identity_status") == "split" and "support_intent" not in original:
                message = (
                    "Explicit repair: adopt the current original source face's plane and centroid; "
                    "no historical anchor was saved. " + message
                )
        except (ValueError, KeyError, AttributeError) as exc:
            message = "Needs review: " + str(exc)
        # Fixed two-line decision space: full exact diagnostic remains in this
        # dialog's paginated help, never in a nested operator that loses edits.
        lines = textwrap.wrap(message, width=78)
        for index in range(2):
            line = lines[index] if index < len(lines) else " "
            if index == 1 and len(lines) > 2:
                line = line[:74] + "..."
            layout.label(text=line)
        limits = (
            "Split preservation needs proven coplanar Cut ancestry. Missing lineage stops. "
            "Minimal twist follows normal changes, not material spin or edit history. "
            "Nearly opposite normals need World axes or an explicit frame reset. "
            "World axes preserves legacy behavior; reference-axis changes may turn it. "
            "Strict requires an exact face. Replace a split support before Apply. "
            "Reset explicitly adopts the current World axes frame as a new baseline. "
            "This may rotate or move your sketch and downstream geometry."
        )
        layout.label(
            text="Plane preservation is an explicit assumption, never an exact face match."
        )
        layout.label(text="Changing support or orientation can move or rotate the sketch.")
        if not staged:
            layout.label(
                text="Apply rebuilds atomically. Cancel changes nothing; Blender Undo restores."
            )
        _draw_feature_help(self, context, detail=message + " " + limits)

    def execute(self, context):
        try:
            result = self._review(context)
            candidate = edit_support_candidate(
                self._document,
                self.feature_id,
                self.policy,
                self.support_source,
                self.support_face,
                result,
                orientation=self.orientation,
                reset_frame=(
                    self.reset_frame
                    and self.policy == "PRESERVE_PLANE"
                    and self.orientation == "MINIMAL_TWIST"
                ),
            )
            if getattr(self, "staged_token", ""):
                from . import staged_edit

                success = staged_edit.accept(context, self.staged_token, candidate)
                if success is None:
                    from .staged_edit_ui import report_repair_kept

                    return report_repair_kept(self, context)
            else:
                success = document_state._commit_candidate(
                    context, candidate, _state(context).document_path
                )
            return _report_result(self, context, success)
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))
        finally:
            self._release()

    def cancel(self, context):
        # Close only this review. The live proposal (even a newer revision), its
        # history and saved intent belong to explicit Discard/lifecycle handling.
        self._release()


CLASSES = (MCAD_OT_edit_sketch_support,)
