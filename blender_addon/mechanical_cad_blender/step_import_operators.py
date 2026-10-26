"""Bounded, self-contained STEP import through the existing exact Part transaction."""

import uuid
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from . import document_state, execution_lease, sketch_session
from .common import _state
from .operators import _reject_candidate, _report_result
from .step_asset import MAX_STEP_BYTES, encode_step


def read_step_asset(path):
    """Bound the read itself, including a file changed after its initial stat."""
    path = Path(path)
    if not path.is_file():
        raise ValueError("Choose a regular STEP file.")
    if path.stat().st_size > MAX_STEP_BYTES:
        raise ValueError("STEP import supports files up to 512 KiB.")
    with path.open("rb") as stream:
        data = stream.read(MAX_STEP_BYTES + 1)
    if len(data) > MAX_STEP_BYTES:
        raise ValueError("STEP import supports files up to 512 KiB.")
    return encode_step(data)


class MCAD_OT_import_step(Operator, ImportHelper):
    bl_idname = "mcad.import_step"
    bl_label = "Import STEP Solid"
    bl_description = (
        "Embed one exact closed STEP solid into Part history; no external file dependency"
    )
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".step"
    filter_glob: StringProperty(default="*.step;*.stp;*.STEP;*.STP", options={"HIDDEN"})
    feature_label: StringProperty(name="Feature name", default="")

    @classmethod
    def poll(cls, context):
        return bool(
            context.mode == "OBJECT"
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
            and sketch_session.active_session(context) is None
            and not _state(context).sketch_draft_json
        )

    def invoke(self, context, event):
        state = _state(context)
        self._binding = (context.scene, state.document_json, state.sketch_draft_json)
        return ImportHelper.invoke(self, context, event)

    def draw(self, context):
        self.layout.prop(self, "feature_label")
        self.layout.label(text="One valid closed solid, up to 512 KiB.")
        self.layout.label(text="STEP bytes are embedded; the original file is not needed later.")
        self.layout.label(text="Imported faces are not stable associative face selectors.")

    def execute(self, context):
        try:
            state = _state(context)
            if not self.poll(context):
                raise ValueError("Finish or discard the active sketch and wait for CAD work first.")
            if hasattr(self, "_binding") and self._binding != (
                context.scene,
                state.document_json,
                state.sketch_draft_json,
            ):
                raise ValueError("The Part changed while choosing the file; reopen Import STEP.")
            path = Path(bpy.path.abspath(self.filepath)).expanduser()
            asset = read_step_asset(path)
            label = self.feature_label.strip() or path.stem or "Imported solid"
            if len(label) > 128:
                raise ValueError("Use an imported feature name no longer than 128 characters.")
            if state.document_json:
                candidate = document_state._read_document(state)
            else:
                candidate = {
                    "schema_version": 2,
                    "id": uuid.uuid4().hex,
                    "name": label,
                    "units": "mm",
                    "parameters": {},
                    "features": [],
                    "active_feature": None,
                }
            used = {feature["id"] for feature in candidate["features"]}
            index = 1
            while f"import_step_{index}" in used:
                index += 1
            identifier = f"import_step_{index}"
            candidate["features"].append(
                {
                    "id": identifier,
                    "kind": "import_step",
                    "label": label,
                    "params": {},
                    "inputs": {},
                    "step_data": asset,
                }
            )
            candidate["active_feature"] = identifier
            return _report_result(
                self,
                context,
                document_state._commit_candidate(context, candidate, state.document_path),
            )
        except Exception as exc:
            return _reject_candidate(
                self, context, f"STEP import rejected; current Part unchanged: {exc}"
            )


CLASSES = (MCAD_OT_import_step,)
