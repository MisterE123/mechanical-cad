"""Explicit create/edit/remove gear controls, using the normal assembly transaction."""

import textwrap

from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from . import assembly_edit as edit
from .assembly_gears import saved_coordinates
from .assembly_operator_helpers import (
    AssemblyEdit,
    assembly,
    choices,
    number,
    reject,
    rows,
    unit_text,
    unit_value,
)


def _explain(layout, text):
    for line in textwrap.wrap(text, width=68):
        layout.label(text=line)


def revolute_choices(self, context):
    return choices([joint for joint in rows(context, "joints") if joint["kind"] == "revolute"])


class MCAD_OT_assembly_gear(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_gear"
    bl_label = "Gear Relation"
    bl_description = "Couple two revolute coordinates at a signed ratio; not physical tooth contact"
    bl_options = {"REGISTER", "UNDO"}
    relation_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    name: StringProperty(name="Relation name", default="Gear relation")
    driver_joint: EnumProperty(name="Driver joint", items=revolute_choices)
    driven_joint: EnumProperty(
        name="Driven joint",
        items=revolute_choices,
        description="Controlled revolute joint; its angle becomes read-only and follows the driver",
    )
    ratio: StringProperty(
        name="Signed ratio",
        default="-1",
        description="Driven / driver angular motion: driven angle = ratio × driver angle + phase. "
        "Negative reverses coordinate direction; positive preserves it, using each joint's mate-local +Z",
    )
    offset: StringProperty(
        name="Phase (deg)",
        default="0",
        description="Offset / phase in degrees, added after multiplying the driver angle by the ratio. "
        "Ignored while Keep current alignment derives phase from the captured saved pose",
    )
    keep_alignment: BoolProperty(
        name="Keep current alignment",
        default=True,
        description="Explicitly calculate phase from the captured saved pose instead of the offset field",
    )
    _original = None

    @classmethod
    def poll(cls, context):
        return super().poll(context) and len(revolute_choices(None, context)) >= 2

    def invoke(self, context, event):
        data = assembly(context)
        relation = next(
            (row for row in data.get("gear_relations", []) if row["id"] == self.relation_id), None
        )
        if self.relation_id and relation is None:
            return reject(self, context, ValueError("This gear relation no longer exists."))
        if relation:
            self.name = relation["name"]
            self.driver_joint, self.driven_joint = (
                relation["driver_joint"],
                relation["driven_joint"],
            )
            self.ratio, self.offset = (
                repr(relation["ratio"]),
                unit_text(relation["offset_rad"], "revolute"),
            )
            self.keep_alignment = False
            self._original = (self.ratio, self.offset, relation)
        else:
            choices_ = revolute_choices(self, context)
            self.driver_joint, self.driven_joint = choices_[0][0], choices_[1][0]
        return super().invoke(context, event)

    def candidate(self, context):
        ratio = number(self.ratio)
        offset = 0.0 if self.keep_alignment else unit_value(self.offset, "revolute")
        if self._original:
            texts_ratio, texts_offset, original = self._original
            if self.ratio == texts_ratio:
                ratio = original["ratio"]
            if self.offset == texts_offset:
                offset = original["offset_rad"]
        return edit.edit_gear_relation(
            assembly(context),
            relation_id=self.relation_id,
            name=self.name,
            driver_joint=self.driver_joint,
            driven_joint=self.driven_joint,
            ratio=ratio,
            offset_rad=offset,
            keep_alignment=self.keep_alignment,
        )

    def draw(self, context):
        layout = self.layout
        for field in ("name", "driver_joint", "driven_joint", "ratio", "keep_alignment"):
            layout.prop(self, field)
        row = layout.row()
        row.enabled = not self.keep_alignment
        row.prop(self, "offset")
        layout.label(text="Driven angle = signed ratio × driver angle + phase.")
        layout.label(text="Ratio: driven / driver motion. Phase: offset in degrees.")
        layout.label(text="Negative: opposite coordinate direction. Positive: same direction.")
        _explain(layout, "Signs refer to each joint's mate-local +Z, not visual tooth contact.")
        try:
            before = saved_coordinates(assembly(context))
            candidate = self.candidate(context)
            after = saved_coordinates(candidate)
            relation = next(
                row
                for row in candidate["gear_relations"]
                if row["driven_joint"] == self.driven_joint
            )
            layout.label(text=f"Phase: {float(unit_text(relation['offset_rad'], 'revolute')):g}°")
            layout.label(
                text=f"Driven: {float(unit_text(before[self.driven_joint], 'revolute')):g}° → "
                f"{float(unit_text(after[self.driven_joint], 'revolute')):g}° after Apply"
            )
        except Exception as exc:
            layout.label(text=str(exc)[:90], icon="ERROR")
        _explain(layout, "Driven angle becomes read-only; edit/sample the independent driver.")
        layout.label(
            text="Kinematics only. Check exact poses separately; no tooth/contact solving."
        )

    def execute(self, context):
        try:
            return self.apply(context, self.candidate(context))
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_remove_gear(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_remove_gear"
    bl_label = "Remove Gear Relation"
    bl_description = "Release the driven joint at its current angle without moving the assembly"
    bl_options = {"REGISTER", "UNDO"}
    relation_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def draw(self, context):
        relation = next(
            (
                row
                for row in assembly(context).get("gear_relations", [])
                if row["id"] == self.relation_id
            ),
            {},
        )
        self.layout.label(text=relation.get("name", "Gear relation"))
        self.layout.label(text="The driven joint becomes independent at its current angle.")
        self.layout.label(text="Remaining downstream relations and the current pose are preserved.")

    def execute(self, context):
        try:
            return self.apply(
                context, edit.remove_gear_relation(assembly(context), self.relation_id)
            )
        except Exception as exc:
            return reject(self, context, exc)


CLASSES = (MCAD_OT_assembly_gear, MCAD_OT_assembly_remove_gear)
