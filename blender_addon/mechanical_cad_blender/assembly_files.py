"""Explicit portable assembly-file dialogs with fresh validation and atomic writes."""

import os
import tempfile
from pathlib import Path

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import assembly_state as state_api
from . import bridge
from .assembly_operator_helpers import (
    AssemblyEdit,
    activate_assembly_workspace,
    assembly,
    number,
    reject,
    state,
)
from .document_paths import normalized_document_path, normalized_export_check


class MCAD_OT_assembly_load(AssemblyEdit, Operator, ImportHelper):
    bl_idname = "mcad.assembly_load"
    bl_label = "Load Assembly"
    bl_description = (
        "Validate an embedded-source assembly file before replacing the accepted assembly"
    )
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".mcad-assembly.json"
    filter_glob: StringProperty(default="*.mcad-assembly.json;*.json", options={"HIDDEN"})

    override_replay_tolerance: BoolProperty(
        name="Override saved replay tolerance",
        default=False,
        description="Save an explicit display admission tolerance; does not change verification",
    )
    replay_tolerance: StringProperty(name="Replay tolerance (mm)", default="1e-6")

    def draw(self, context):
        self.layout.prop(self, "override_replay_tolerance")
        row = self.layout.row()
        row.enabled = self.override_replay_tolerance
        row.prop(self, "replay_tolerance")
        self.layout.label(text="Display admission only, not a clearance check.")
        self.layout.label(text="Unchecked: use saved tolerance, or legacy 1e-6 mm.")

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def invoke(self, context, event):
        self.capture_dialog(context)
        return ImportHelper.invoke(self, context, event)

    def execute(self, context):
        try:
            self.require_same_working_part(context)
            path = Path(bpy.path.abspath(self.filepath)).expanduser()
            if path.stat().st_size > bridge.MAX_DOCUMENT_BYTES:
                raise bridge.BridgeError("Assembly exceeds the 2 MiB file limit.")
            candidate = bridge.parse_document_json(path.read_text("utf-8"))
            if self.override_replay_tolerance:
                candidate["replay_tolerance_mm"] = number(self.replay_tolerance, "length")
            self.apply(context, candidate)
            state(context).document_path = str(path)
            activate_assembly_workspace(context)
            return {"FINISHED"}
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_save(AssemblyEdit, Operator, ExportHelper):
    bl_idname = "mcad.assembly_save"
    bl_label = "Save Assembly"
    bl_description = (
        "Validate and atomically save the portable assembly with embedded Part snapshots"
    )
    filename_ext = ".mcad-assembly.json"
    check = normalized_export_check
    filter_glob: StringProperty(default="*.mcad-assembly.json;*.json", options={"HIDDEN"})

    def invoke(self, context, event):
        self.capture_dialog(context)
        self.filepath = (
            self.filepath or state(context).document_path or "assembly.mcad-assembly.json"
        )
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        temporary = None
        try:
            self.require_same_working_part(context)
            if self._expected is not None and state(context).document_json != self._expected:
                raise bridge.BridgeError("Assembly changed while choosing a file. Save again.")
            state_api.validate_snapshot(context)
            content = state(context).document_json
            path = Path(bpy.path.abspath(self.filepath)).expanduser()
            path = normalized_document_path(path, self.filename_ext)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as stream:
                temporary = stream.name
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
            state(context).document_path = str(path)
            return {"FINISHED"}
        except Exception as exc:
            return reject(self, context, exc)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


class MCAD_OT_assembly_replay_tolerance(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_replay_tolerance"
    bl_label = "Set Replay Tolerance"
    bl_description = "Save display admission tolerance separately from verification resolution"
    bl_options = {"REGISTER", "UNDO"}
    tolerance: StringProperty(name="Replay tolerance (mm)", default="1e-6")

    def invoke(self, context, event):
        self.tolerance = repr(assembly(context).get("replay_tolerance_mm", 1e-6))
        return super().invoke(context, event)

    def draw(self, context):
        self.layout.prop(self, "tolerance")
        self.layout.label(text="Finite range: 1e-9 to 1 mm. No automatic widening.")
        self.layout.label(text="Admits stored B-rep tolerance for display placement only.")
        self.layout.label(text="Checks keep their own resolution. Prior checks become stale.")

    def execute(self, context):
        try:
            candidate = assembly(context)
            candidate["replay_tolerance_mm"] = number(self.tolerance, "length")
            return self.apply(context, candidate)
        except Exception as exc:
            return reject(self, context, exc)


CLASSES = (MCAD_OT_assembly_load, MCAD_OT_assembly_save, MCAD_OT_assembly_replay_tolerance)
