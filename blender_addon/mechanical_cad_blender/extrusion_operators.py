"""One-step additive/subtractive extrusion through exact existing feature replay."""

from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import document_state, execution_lease, extrusion_preview
from .common import _state
from .document_state import _commit_candidate, _new_feature, _read_document
from .extrusion_candidate import extrusion_candidate
from .extrusion_end_condition import (
    OFFSET_DESCRIPTION,
    UP_TO_FACE_ITEM,
    _end_face_choices,
    _source_choices,
    draw_up_to_face,
    set_up_to_face,
)
from .help_ui import _draw_feature_help, _feature_help_next, _feature_help_previous
from .operators import _reject_candidate, _report_result
from .solid_dialog_values import (
    extrusion_depth,
    outward_support_profile,
    selected_history_id,
    solid_dialog_defaults,
)
from .solid_feature_edit import SOLID_KINDS
from .solid_operators import _profile_choices, _solid_choices


class MCAD_OT_extrude_boolean(Operator):
    bl_idname = "mcad.extrude_boolean"
    bl_label = "Add / Remove Extrusion"
    bl_description = "Extrude a sketch and add to or remove from a solid in one editable operation"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        name="Operation",
        items=[("ADD", "Add", "Union with base"), ("REMOVE", "Remove", "Cut from base")],
    )
    profile: EnumProperty(name="Profile", items=_profile_choices)
    base: EnumProperty(name="Base solid", items=_solid_choices)
    end_condition: EnumProperty(
        name="End condition",
        items=[
            ("BLIND", "Blind", "Extrude by a dimension or formula"),
            UP_TO_FACE_ITEM,
            (
                "SYMMETRIC",
                "Symmetric / Mid-plane",
                "Half the total depth on each side of the sketch",
            ),
            (
                "THROUGH_ALL",
                "Through All",
                "Remove through the target in the selected direction on every rebuild",
            ),
        ],
        default="BLIND",
    )
    target: EnumProperty(name="Earlier target solid", items=_source_choices)
    end_face: EnumProperty(name="End face", items=_end_face_choices)
    offset: StringProperty(name="Offset (mm)", description=OFFSET_DESCRIPTION, default="0")
    depth: StringProperty(name="Depth (mm or formula)", default="10")
    direction: EnumProperty(
        name="Direction",
        items=[
            ("NORMAL", "Along sketch normal", "Positive depth along the sketch normal"),
            ("REVERSE", "Opposite sketch normal", "Positive depth opposite the sketch normal"),
            (
                "SIGNED",
                "Signed depth (Blind only)",
                "Blind only: use the signed depth or formula exactly as entered; "
                "choose Along/Opposite for Up to Face or Through All",
            ),
        ],
        default="SIGNED",
    )
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})
    help_page: IntProperty(default=1, min=1, options={"SKIP_SAVE"})
    help_previous: BoolProperty(default=False, update=_feature_help_previous, options={"SKIP_SAVE"})
    help_next: BoolProperty(default=False, update=_feature_help_next, options={"SKIP_SAVE"})
    help_topic = "feature.extrude"
    help_summary = (
        "Add joins material; Remove cuts material from the target.",
        "Apply keeps both editable steps, or leaves your model unchanged.",
    )
    feature_label: StringProperty(name="Name", default="Extrusion")
    original_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

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
            solids = [f["id"] for f in document["features"] if f["kind"] in SOLID_KINDS]
            profiles = [f["id"] for f in document["features"] if f["kind"].startswith("sketch_")]
            if not solids or not profiles:
                raise ValueError("Create a base solid and a sketch profile first")
            defaults = solid_dialog_defaults(document, selected_history_id(state))
            if not self.properties.is_property_set("base"):
                self.base = defaults["base"]
            if not self.properties.is_property_set("profile"):
                self.profile = defaults["profile"]
            if not self.properties.is_property_set("direction"):
                if self.properties.is_property_set("depth"):
                    self.direction = "SIGNED"
                else:
                    # Only the canonical standard outward face frame establishes
                    # an inward direction. Free or flipped planes are not guessed.
                    inward = self.mode == "REMOVE" and outward_support_profile(
                        document, self.profile, self.base
                    )
                    self.direction = "REVERSE" if inward else "NORMAL"
            if not self.properties.is_property_set("feature_label"):
                self.feature_label = "Add extrusion" if self.mode == "ADD" else "Remove extrusion"
            self.original_json = state.document_json
            extrusion_preview.start(self, context)
            return context.window_manager.invoke_props_dialog(self, width=480, confirm_text="Apply")
        except Exception as exc:
            extrusion_preview.cancel(self, context)
            return _reject_candidate(self, context, str(exc))

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)
        layout.prop(self, "feature_label")
        inputs = layout.box()
        inputs.prop(self, "profile", text="Sketch profile")
        inputs.prop(
            self,
            "base",
            text=(
                "Add/Remove base solid" if self.end_condition == "UP_TO_FACE" else "Target solid"
            ),
        )
        depth = layout.box()
        depth.prop(self, "end_condition")
        if self.end_condition == "UP_TO_FACE":
            draw_up_to_face(depth, self)
            if self.direction == "SIGNED":
                depth.label(text="Choose Along or Opposite sketch normal.", icon="ERROR")
        elif self.end_condition == "SYMMETRIC":
            depth.prop(self, "depth", text="Total depth (mm)")
            depth.label(text="Half of the positive total depth on each side.")
        elif self.end_condition == "THROUGH_ALL":
            depth.prop(self, "direction")
            depth.label(text="Reaches through the target on every rebuild (Remove only).")
            if self.direction == "SIGNED":
                depth.label(text="Choose Along or Opposite sketch normal.", icon="ERROR")
        else:
            depth.prop(
                self,
                "depth",
                text="Signed depth (mm)" if self.direction == "SIGNED" else "Depth (mm)",
            )
            depth.prop(self, "direction")
            depth.label(
                text="Negative depth reverses the sketch normal."
                if self.direction == "SIGNED"
                else "Enter a positive distance or formula."
            )
        if self.mode == "REMOVE" and self.end_condition == "BLIND" and self.direction == "REVERSE":
            try:
                if outward_support_profile(
                    _read_document(_state(context)), self.profile, self.base
                ):
                    depth.label(text="Into supporting solid")
            except Exception:
                pass  # A replaced document is rejected on Apply.
        extrusion_preview.draw(self)
        _draw_feature_help(self, context)

    check = extrusion_preview.changed
    cancel = extrusion_preview.cancel
    modal = extrusion_preview.modal

    def preview_candidate(self, context):
        if self.mode not in {"ADD", "REMOVE"}:
            raise ValueError("Choose Add or Remove")
        if self.end_condition not in {"BLIND", "SYMMETRIC", "THROUGH_ALL", "UP_TO_FACE"}:
            raise ValueError("Choose an extrusion end condition")
        kind = "union" if self.mode == "ADD" else "cut"
        through = self.end_condition == "THROUGH_ALL"
        symmetric = self.end_condition == "SYMMETRIC"
        if through and (self.mode != "REMOVE" or self.direction == "SIGNED"):
            raise ValueError("Through All requires Remove and an explicit Along/Opposite direction")
        extrusion = _new_feature(
            context,
            "extrude_to_face"
            if self.end_condition == "UP_TO_FACE"
            else "extrude_through"
            if through
            else "extrude_symmetric"
            if symmetric
            else "extrude",
            (
                {"direction": -1 if self.direction == "REVERSE" else 1}
                if through or self.end_condition == "UP_TO_FACE"
                else {
                    "length": extrusion_depth(self.depth, "NORMAL" if symmetric else self.direction)
                }
            ),
            (
                {"profile": self.profile, "base": self.base}
                if through or self.end_condition == "UP_TO_FACE"
                else {"profile": self.profile}
            ),
            self.feature_label
            + (
                " Up to planar face"
                if self.end_condition == "UP_TO_FACE"
                else " Through All"
                if through
                else " symmetric depth"
                if symmetric
                else " depth"
            ),
        )
        if self.end_condition == "UP_TO_FACE":
            if self.direction == "SIGNED":
                raise ValueError("Up to planar face requires an explicit Along/Opposite direction")
            set_up_to_face(
                extrusion,
                profile=self.profile,
                target=self.target,
                end_face=self.end_face,
                direction=-1 if self.direction == "REVERSE" else 1,
                offset=self.offset,
            )
        boolean = _new_feature(
            context, kind, {}, {"base": self.base, "tool": extrusion["id"]}, self.feature_label
        )
        return extrusion_candidate(_read_document(_state(context)), extrusion, boolean)

    def execute(self, context):
        try:
            pending = extrusion_preview.apply(self, context)
            if pending is not None:
                return pending
            if not self.poll(context):
                raise ValueError("Finish the current operation before extruding")
            state = _state(context)
            if self.original_json and state.document_json != self.original_json:
                raise ValueError("Document changed; reopen Add/Remove Extrusion")
            candidate = self.preview_candidate(context)
            return _report_result(
                self, context, _commit_candidate(context, candidate, state.document_path)
            )
        except Exception as exc:
            extrusion_preview.cancel(self, context)
            return _reject_candidate(self, context, str(exc))


CLASSES = (MCAD_OT_extrude_boolean,)
