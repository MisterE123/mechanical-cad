"""Detached fixed face-mate intent over a validated insertion seed.

No response/digest here is publication authority. The live owner must supply a
successful guarded seed replay, retain original accepted/context bindings, and
freshly validate every final candidate before preview and explicit Apply.
"""

import copy

from .assembly_bridge import fingerprint
from .assembly_insert_preview_draft import InsertPreviewDraft
from .assembly_joint_draft import JointDraft
from .assembly_source_preview_contract import source_preview_fingerprint
from .bridge import BridgeError


class InsertMateDraft:
    def __init__(self, insertion, response):
        if type(insertion) is not InsertPreviewDraft:
            raise BridgeError("Visual insertion requires a newly constructed insertion draft.")
        self._seed = insertion.candidate()
        self._original = insertion.original()
        self._seed_fingerprint = source_preview_fingerprint(response)
        if fingerprint(response["result"]["canonical_assembly"]) != fingerprint(self._seed):
            raise BridgeError("Face-picking replay does not match the exact insertion seed.")
        self._child_id, self._joint_id = insertion.instance_id, insertion.joint_id
        joint = next(j for j in self._seed["joints"] if j["id"] == self._joint_id)
        if joint["kind"] != "fixed":
            raise BridgeError("Visual insertion currently supports a fixed joint only.")
        self._parent_id = joint["parent"]
        rows = response["result"]["parts"]
        parts = {row["id"]: row for row in rows}
        if len(parts) != len(rows) or set(parts) != {p["id"] for p in self._seed["parts"]}:
            raise BridgeError("Insertion picking requires complete, unique Part evidence.")
        if fingerprint(response["result"]["instances"]) != fingerprint(self._seed["instances"]):
            raise BridgeError("Insertion picking instances do not match the seed.")
        self._joint = JointDraft(
            self._seed, response["report"]["base_pose"]["transforms"],
            self._parent_id, self._child_id, self._joint_id, parts=parts,
        )
        self._has_pair = False

    @property
    def seed_fingerprint(self):
        return self._seed_fingerprint

    @property
    def parent_id(self):
        return self._parent_id

    @property
    def instance_id(self):
        return self._child_id

    @property
    def joint_id(self):
        return self._joint_id

    @property
    def has_face_pair(self):
        return self._has_pair

    def original(self):
        return copy.deepcopy(self._original)

    def seed(self):
        return copy.deepcopy(self._seed)

    def candidate(self):
        return self._joint.candidate()

    def attach_face_pair(self, parent_face, child_face):
        # JointDraft validates parent before child. Adopt only a complete pair;
        # deepcopy preserves generated connector IDs across every attempted edit.
        proposed = copy.deepcopy(self._joint)
        proposed.attach_face_pair(parent_face, child_face)
        proposed.candidate()
        self._joint = proposed
        self._has_pair = True
