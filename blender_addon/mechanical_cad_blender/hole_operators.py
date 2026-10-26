"""Friendly finite-depth round holes, sharing exact replay and preview ownership."""

import uuid

from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from . import document_state, execution_lease, extrusion_preview
from .common import _state
from .document_state import _commit_candidate, _read_document
from .hole_recipe import hole_candidate, inspect_hole
from .operators import _reject_candidate, _report_result
from .solid_dialog_values import picked_shell_face, selected_history_id, solid_dialog_defaults
from .solid_operators import _solid_choices
from .topology_labels import face_label

_FACE_ITEMS = {}


def _faces(self, context):
    result = document_state.current_part_result(context)
    items = [("NONE", "Choose entry face…", "An explicit stable planar face is required")]
    if result:
        for row in result.get("features", []):
            if row["id"] == self.base and row.get("status") == "ok":
                items.extend(
                    (f["id"], face_label(f), f["id"])
                    for f in row.get("topology", [])
                    if f.get("provenance", {}).get("semantic_status") == "stable"
                    and f.get("signature", {}).get("surface") == "plane"
                )
    key = (self.base, tuple(items))
    _FACE_ITEMS[key] = items
    return _FACE_ITEMS[key]


def _base_changed(self, context):
    self.face = "NONE"


class MCAD_OT_round_hole(Operator):
    bl_idname = "mcad.round_hole"
    bl_label = "Hole"
    bl_description = "Cut a simple or counterbored round hole inward from an explicit planar face"
    bl_options = {"REGISTER", "UNDO"}

    feature_id: StringProperty(options={"HIDDEN"})
    recipe_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    original_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    base: EnumProperty(name="Target solid", items=_solid_choices, update=_base_changed)
    face: EnumProperty(name="Entry face", items=_faces)
    feature_label: StringProperty(name="Name", default="Hole")
    diameter: StringProperty(name="Hole diameter", default="5")
    depth: StringProperty(name="Total hole depth", default="10")
    x: StringProperty(name="Center X", default="0")
    y: StringProperty(name="Center Y", default="0")
    counterbore: BoolProperty(name="Counterbore", default=False)
    counter_diameter: StringProperty(name="Counterbore diameter", default="10")
    counter_depth: StringProperty(name="Counterbore depth", default="2")

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and bool(_state(context).document_json)
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
        )

    def invoke(self, context, event):
        try:
            state = _state(context)
            document = _read_document(state)
            self.original_json = state.document_json
            self.recipe_id = self.feature_id or "hole_" + uuid.uuid4().hex
            if self.feature_id:
                values = inspect_hole(document, self.feature_id)
                if values is None:
                    raise ValueError(
                        "This is not an intact Hole recipe; use Edit Feature for its steps"
                    )
                for key, value in values.items():
                    setattr(
                        self,
                        "feature_label" if key == "label" else key,
                        value if key in {"base", "face", "counterbore", "label"} else str(value),
                    )
            elif not self.properties.is_property_set("base"):
                base = solid_dialog_defaults(document, selected_history_id(state))["base"]
                if not base:
                    raise ValueError("Create a solid before adding a hole")
                self.base = base
            extrusion_preview.start(self, context)
            return context.window_manager.invoke_props_dialog(self, width=500, confirm_text="Apply")
        except Exception as exc:
            extrusion_preview.cancel(self, context)
            return _reject_candidate(self, context, str(exc))

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "feature_label")
        layout.prop(self, "base")
        layout.prop(self, "face")
        row = layout.row()
        row.enabled = not bool(self.feature_id)
        row.prop(self, "counterbore")
        row = layout.row(align=True)
        row.prop(self, "diameter")
        row.prop(self, "depth")
        if self.counterbore:
            row = layout.row(align=True)
            row.prop(self, "counter_diameter")
            row.prop(self, "counter_depth")
        box = layout.box()
        box.label(text="Center from entry-face centroid (local axes)")
        row = box.row(align=True)
        row.prop(self, "x")
        row.prop(self, "y")
        box.label(text="X follows projected world X; on X-facing faces, world Y.")
        layout.label(text="Lengths: mm by default, or type units such as 0.25 in.")
        layout.label(text="Depth goes inward. Both depths start at the entry face.")
        layout.label(text="Finite depth may break through; edge breakouts are allowed.")
        layout.label(text="No threads, countersink or automatic Through All.")
        extrusion_preview.draw(self)

    check = extrusion_preview.changed
    cancel = extrusion_preview.cancel
    modal = extrusion_preview.modal

    def preview_candidate(self, context):
        state = _state(context)
        if self.original_json and state.document_json != self.original_json:
            raise ValueError("Document changed; reopen Hole")
        document = _read_document(state)
        if self.face in {"", "NONE"}:
            raise ValueError("Choose an entry face to preview the hole")
        picked_shell_face(
            document, document_state.current_part_result(context), self.base, self.face
        )
        if not self.recipe_id:
            self.recipe_id = self.feature_id or "hole_" + uuid.uuid4().hex
        return hole_candidate(
            document,
            self.recipe_id,
            base=self.base,
            face=self.face,
            diameter=self.diameter,
            depth=self.depth,
            x=self.x,
            y=self.y,
            counterbore=self.counterbore,
            counter_diameter=self.counter_diameter,
            counter_depth=self.counter_depth,
            label=self.feature_label,
            editing=bool(self.feature_id),
        )

    def execute(self, context):
        try:
            pending = extrusion_preview.apply(self, context)
            if pending is not None:
                return pending
            if not self.poll(context):
                raise ValueError("Finish the current operation before adding a hole")
            candidate = self.preview_candidate(context)
            return _report_result(
                self, context, _commit_candidate(context, candidate, _state(context).document_path)
            )
        except Exception as exc:
            extrusion_preview.cancel(self, context)
            return _reject_candidate(self, context, str(exc))


CLASSES = (MCAD_OT_round_hole,)
