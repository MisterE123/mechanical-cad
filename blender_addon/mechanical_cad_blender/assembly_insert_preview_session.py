"""Shared insertion review owner; independent of the one-shot launcher."""

from . import assembly_pending, assembly_source_update_preview, assembly_state
from .assembly_insert_preview_draft import InsertPreviewDraft
from .bridge import BridgeError


class InsertPreviewSession(assembly_source_update_preview.SourceUpdatePreview):
    title = "Insert component · not saved / checked"
    apply_label = "Insert component"
    cancel_label = "Cancel Insertion Preview"
    header = "Insertion preview · new child + joint together · Apply inserts · Esc cancels"
    prepare_message = "Preparing insertion · accepted Assembly retained"
    failure_message = "Insertion refused · accepted Assembly retained"
    success_message = "Component inserted. Run an explicit check again."

    def __init__(self, context, draft):
        if type(draft) is not InsertPreviewDraft:
            raise BridgeError("Insertion review requires a newly constructed insertion draft.")
        super().__init__(context)
        self.draft = draft
        self.handoff_region = context.region
        if draft.original() != assembly_state.read_assembly(context.scene.mechanical_cad_assembly):
            raise BridgeError("Assembly changed. Reopen Insert.")

    def prepare_pending(self, context):
        return assembly_pending.prepare_insert_preview(
            context,
            self.draft,
            expected_json=self.snapshot["fields"]["document_json"],
            expected_working_part=self.snapshot["working_part"],
        )

    def describe_candidate(self):
        child = next(i for i in self.candidate["instances"] if i["id"] == self.draft.instance_id)
        joint = next(j for j in self.candidate["joints"] if j["id"] == self.draft.joint_id)
        parent = next(i for i in self.candidate["instances"] if i["id"] == joint["parent"])
        part = next(p for p in self.candidate["parts"] if p["id"] == self.draft.part_id)
        captured = self.draft.part_id not in {p["id"] for p in self.draft.original()["parts"]}
        self.revisions = (
            ("Capture " if captured else "Reuse ")
            + part["name"]
            + " · "
            + part["source_digest"][:10]
        )
        self.affected = [
            "Child: " + child["name"],
            "Parent: " + parent["name"],
            "Joint: " + joint["name"] + " (" + joint["kind"] + ")",
        ]

    def summary(self):
        return "New child + joint; existing instances retained"
