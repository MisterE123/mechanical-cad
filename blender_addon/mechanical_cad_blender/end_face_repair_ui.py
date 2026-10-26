"""Proposal-owned explicit end-face review; no automatic binding or publication."""

import json

from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from . import document_state, execution_lease, staged_edit, workspace
from .common import _state
from .end_face_repair import end_face_candidates, replace_end_face, terminated_feature
from .help_ui import _panel_wrap
from .operators import _reject_candidate, _report_result

_CHOICES = {}


def _choices(key, values, prompt):
    values = [
        ("NONE", prompt, "Choose explicitly; no replacement is selected automatically"),
        *values,
    ]
    key = (key, tuple(values))
    _CHOICES[key] = values
    return _CHOICES[key]


def _choice_data(self):
    try:
        return json.loads(self.review_choices_json or "{}")
    except (ValueError, TypeError, AttributeError):
        return {}


def _sources(self, context):
    return _choices(
        "sources",
        [tuple(row) for row in _choice_data(self).get("sources", [])],
        "Select an earlier solid",
    )


def _faces(self, context):
    return _choices(
        ("faces", self.target),
        [tuple(row) for row in _choice_data(self).get("faces", {}).get(self.target, [])],
        "Select a valid parallel face",
    )


def _source_changed(self, context):
    # Even identical semantic IDs on different solids are different intent.
    self.end_face = "NONE"


class MCAD_OT_replace_end_face(Operator):
    bl_idname = "mcad.replace_end_face"
    bl_label = "Replace Up to Face Target"
    bl_description = "Explicitly replace a broken extrusion end reference in the retained proposal"
    bl_options = {"REGISTER", "UNDO"}

    feature_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    original_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    staged_token: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    review_choices_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    target: EnumProperty(name="Earlier target solid", items=_sources, update=_source_changed)
    end_face: EnumProperty(name="Replacement end face", items=_faces)

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
        from .staged_edit_ui import validate_review

        if _state(context).document_json != self.original_json:
            raise ValueError("The accepted Part changed. Reopen the end-face review.")
        validate_review(context, self.staged_token, self.original_json, self._document)
        document_state._assert_binding(context, self._binding)
        return document_state._evidence_projection(
            context, self._document, self._review_evidence, self._binding
        )["result"]

    def invoke(self, context, event):
        try:
            if not self.poll(context):
                raise ValueError(
                    "Finish or cancel the active operation before replacing an end face."
                )
            from .staged_edit_ui import review_document

            self.original_json = _state(context).document_json
            self._document = review_document(context, self.staged_token, self.original_json)
            self._feature = terminated_feature(self._document, self.feature_id)
            proposal = staged_edit.require(context, self.staged_token)
            if not any(
                row["id"] == self.feature_id
                and (row.get("error") or {}).get("code") == "invalid_extrusion_end_face"
                for row in proposal.failures
            ):
                raise ValueError("Choose a failed Up to Face reference in this proposal.")
            with document_state.replay_guard(context):
                self._binding = document_state._capture_binding(context)
                self._review_evidence = document_state._run_sidecar(
                    context, self._document, binding=self._binding
                )
                result = self._review(context)
                entries = end_face_candidates(self._document, self.feature_id, result)
            self._entries = entries
            labels = {f["id"]: f["label"] for f in self._document["features"]}
            source_ids = list(dict.fromkeys(row["target"] for row in entries))
            self.review_choices_json = json.dumps(
                {
                    "sources": [
                        (source, labels[source] + " [" + source + "]", source)
                        for source in source_ids
                    ],
                    "faces": {
                        source: [
                            (
                                row["face"],
                                row["role"] + " [" + row["face"] + "]",
                                f"Saved direction + offset gives {row['length']:.8g} mm travel",
                            )
                            for row in entries
                            if row["target"] == source
                        ]
                        for source in source_ids
                    },
                }
            )
            self.target = "NONE"
            self.end_face = "NONE"
            return context.window_manager.invoke_props_dialog(
                self, width=650, confirm_text="Apply Repair"
            )
        except Exception as exc:
            self._release()
            return _reject_candidate(self, context, str(exc))

    def draw(self, context):
        from .staged_edit_ui import draw_review_notice

        layout = self.layout
        draw_review_notice(layout)
        feature = self._feature
        labels = {f["id"]: f["label"] for f in self._document["features"]}
        source = feature["inputs"]["target"]
        for line in _panel_wrap(
            context,
            f"Replacing {feature['label']}: {labels[source]} [{source}] / {feature['end_face']}",
        ):
            layout.label(text=line)
        direction = feature["params"]["direction"]
        layout.label(
            text="Preserved direction: "
            + ("Along sketch normal" if direction == 1 else "Opposite sketch normal")
        )
        layout.label(text="Preserved offset (mm): " + str(feature["params"].get("offset", 0)))
        layout.prop(self, "target")
        layout.prop(self, "end_face")
        selected = next(
            (
                row
                for row in self._entries
                if row["target"] == self.target and row["face"] == self.end_face
            ),
            None,
        )
        if selected is not None:
            layout.label(
                text=f"Plane reach {selected['reach']:.8g} mm; with offset {selected['length']:.8g} mm"
            )
        else:
            layout.label(text="Choose the replacement explicitly; none is assumed.", icon="INFO")
        if not self._entries:
            layout.label(
                text="No valid earlier face for the saved direction and offset.", icon="ERROR"
            )
        layout.label(text="Uses the infinite face plane, not its finite boundary.")
        layout.label(text="Only stable parallel faces ahead in the saved direction are offered.")
        layout.label(text="The original profile, direction and offset are not changed.")

    def execute(self, context):
        try:
            if not self.poll(context):
                raise ValueError(
                    "Finish or cancel the active operation before replacing an end face."
                )
            result = self._review(context)
            candidate = replace_end_face(
                self._document, self.feature_id, self.target, self.end_face, result
            )
            success = staged_edit.accept(context, self.staged_token, candidate)
            if success is None:
                from .staged_edit_ui import report_repair_kept

                return report_repair_kept(self, context)
            return _report_result(self, context, success)
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))
        finally:
            self._release()

    def cancel(self, context):
        # Proposal, accumulated repairs and saved checkpoint are not dialog-owned.
        self._release()


CLASSES = (MCAD_OT_replace_end_face,)
