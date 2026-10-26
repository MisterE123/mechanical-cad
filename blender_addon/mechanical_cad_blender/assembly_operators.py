"""Explicit assembly authoring; all accepted candidates use the isolated sidecar."""

import textwrap
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper

from . import assembly_edit as edit
from . import (
    assembly_export_owner,
    assembly_files,
    assembly_gear_ui,
    bridge,
    compact_status,
    display,
    document_state,
    gear_pair_ui,
    operation_contracts,
    workspace,
)
from . import assembly_state as state_api
from .assembly_component_context import selected_component
from .assembly_coordinates import NO_SCALAR_COORDINATE
from .assembly_gears import controlling_joint, saved_coordinates
from .assembly_job_ui import AssemblyJobMixin
from .assembly_operator_helpers import (
    JOINT_KINDS,
    AssemblyEdit,
    activate_assembly_workspace,
    assembly,
    canonical_working_part,
    child_frames,
    degrees_from_quaternion,
    extra_joint_arguments,
    help_lines,
    instance_choices,
    joint_choices,
    joint_fields,
    joint_help_lines,
    load_extra_joint_fields,
    parent_frames,
    part_choices,
    quaternion_from_degrees,
    reject,
    rows,
    state,
    support_face_choices,
    unit_text,
    unit_value,
    vector,
)


def working_part_capture_reason(context):
    """Working-Part capture policy only; accepted Assembly reuse is independent."""
    try:
        operation_contracts.result_version_for(
            document_state._read_document(context.scene.mechanical_cad),
            action="canonical_snapshot",
        )
    except (ValueError, RuntimeError, TypeError, KeyError, AttributeError) as exc:
        return str(exc)
    return ""


def _capture_poll(cls, context):
    reason = working_part_capture_reason(context)
    if reason and callable(getattr(cls, "poll_message_set", None)):
        cls.poll_message_set(reason)
    return not reason


def _require_capture(context):
    reason = working_part_capture_reason(context)
    if reason:
        raise bridge.BridgeError(reason)


def _draw_capture_reason(layout, context):
    reason = working_part_capture_reason(context)
    if reason:
        # Short explicit explanation also remains visible when a control is disabled.
        layout.label(text="Working Part capture/update unavailable", icon="INFO")
        for line in textwrap.wrap(reason, width=64):
            layout.label(text=line)
    return reason


class MCAD_OT_assembly_new(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_new"
    bl_label = "New Assembly from Part"
    bl_description = "Capture the working Part snapshot and explicitly ground its first instance"
    bl_options = {"REGISTER", "UNDO"}
    name: StringProperty(name="Assembly name", default="Assembly")
    instance_name: StringProperty(name="Grounded instance name", default="Base")
    grounded: BoolProperty(name="Ground first instance at world origin (required)", default=True)
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and bool(context.scene.mechanical_cad.document_json)
            and _capture_poll(cls, context)
        )

    def invoke(self, context, event):
        self.grounded = True
        return super().invoke(context, event)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Source: " + context.scene.mechanical_cad.document_name, icon="MESH_CUBE")
        layout.prop(self, "name")
        layout.prop(self, "instance_name")
        layout.prop(self, "grounded")
        if state(context).document_json:
            layout.label(
                text="Apply replaces the current assembly. Save it first if needed.", icon="ERROR"
            )
        help_lines(
            layout,
            self,
            [
                "The first instance is the fixed root of a rooted tree.",
                "The working Part stays separate and unchanged.",
                "Part snapshots are embedded; there are no external file links.",
            ],
        )

    def execute(self, context):
        try:
            _require_capture(context)
            if not self.grounded:
                raise bridge.BridgeError("Explicitly confirm grounding the first instance.")
            self.require_same_working_part(context)
            result = self.apply(
                context,
                edit.new_from_part(
                    canonical_working_part(context),
                    name=self.name,
                    instance_name=self.instance_name,
                ),
            )
            state(context).document_path = ""
            activate_assembly_workspace(context)
            return result
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_insert(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_insert"
    bl_label = "Insert Child Instance"
    bl_description = (
        "Preview a reused or working Part with explicit parent, named frames and one joint"
    )
    bl_options = {"REGISTER", "UNDO"}
    use_working_part: BoolProperty(name="Capture working Part", default=False)
    part_id: EnumProperty(name="Reusable definition", items=part_choices)
    parent: EnumProperty(name="Parent instance", items=instance_choices)
    parent_frame: EnumProperty(name="Parent mate frame", items=parent_frames)
    child_frame: EnumProperty(name="Child mate frame", items=child_frames)
    name: StringProperty(name="Instance name", default="Child")
    joint_name: StringProperty(name="Joint name", default="Joint")
    kind: EnumProperty(name="Joint", items=JOINT_KINDS)
    _original_axes = {}
    _preview_on_confirm = False
    mate_faces: BoolProperty(name="Mate by planar faces after preview", default=False, options={"SKIP_SAVE"})
    translation_x: StringProperty(default="0")
    use_translation_x_limits: BoolProperty(name="Explicit translation x limits")
    translation_x_lower: StringProperty(default="-90")
    translation_x_upper: StringProperty(default="90")
    translation_y: StringProperty(default="0")
    use_translation_y_limits: BoolProperty(name="Explicit translation y limits")
    translation_y_lower: StringProperty(default="-90")
    translation_y_upper: StringProperty(default="90")
    rotation_x: StringProperty(default="0")
    use_rotation_x_limits: BoolProperty(name="Explicit rotation x limits")
    rotation_x_lower: StringProperty(default="-90")
    rotation_x_upper: StringProperty(default="90")
    rotation_y: StringProperty(default="0")
    use_rotation_y_limits: BoolProperty(name="Explicit rotation y limits")
    rotation_y_lower: StringProperty(default="-90")
    rotation_y_upper: StringProperty(default="90")
    coordinate: StringProperty(default="0")
    rotation: StringProperty(default="0")
    use_rotation_limits: BoolProperty(name="Explicit rotation limits")
    rotation_lower: StringProperty(default="-180")
    rotation_upper: StringProperty(default="180")
    use_limits: BoolProperty(name="Explicit limits")
    lower: StringProperty(default="-90")
    upper: StringProperty(default="90")
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context, event):
        data = assembly(context)
        component = selected_component(context, data)
        if not self.properties.is_property_set("part_id"):
            selected = component["part_id"] if component else state(context).selected_part_id
            if selected in {p["id"] for p in data["parts"]}:
                self.part_id = selected
        if not self.properties.is_property_set("parent"):
            selected = component["id"] if component else ""
            self.parent = (
                selected
                if selected in {i["id"] for i in data["instances"]}
                else data["grounded_instance"]
            )
        self.capture_dialog(context)
        self._preview_on_confirm = True
        return context.window_manager.invoke_props_dialog(self, width=520, confirm_text="Preview")

    def cancel(self, context):
        self._preview_on_confirm = False

    def draw(self, context):
        layout = self.layout
        layout.label(text="Preview first; insertion is saved only by Apply in the viewport.", icon="INFO")
        reason = _draw_capture_reason(layout, context)
        capture = layout.row()
        capture.enabled = not reason or self.use_working_part
        capture.prop(self, "use_working_part")
        if self.use_working_part:
            layout.label(text="Working Part: " + context.scene.mechanical_cad.document_name)
        else:
            layout.prop(self, "part_id")
        for key in ("name", "parent", "parent_frame", "child_frame", "joint_name", "kind"):
            layout.prop(self, key)
        if self.kind == "fixed":
            layout.prop(self, "mate_faces")
        joint_fields(layout, self, self.kind)
        help_lines(
            layout,
            self,
            joint_help_lines(self.kind),
        )

    def execute(self, context):
        if self._preview_on_confirm:
            # Only the child modal can register a successful insertion/Undo.
            self._preview_on_confirm = False
            try:
                from .assembly_insert_preview import launch_from_dialog

                launch_from_dialog(self, context)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        try:
            candidate, part_id = assembly(context), self.part_id
            if self.use_working_part:
                _require_capture(context)
                self.require_same_working_part(context)
                candidate, part_id = edit.capture_definition(
                    candidate, canonical_working_part(context)
                )
            limits = (
                [unit_value(self.lower, self.kind), unit_value(self.upper, self.kind)]
                if self.use_limits and self.kind not in NO_SCALAR_COORDINATE
                else None
            )
            candidate = edit.insert_instance(
                candidate,
                part_id,
                parent=self.parent,
                parent_frame=self.parent_frame,
                child_frame=self.child_frame,
                kind=self.kind,
                coordinate=0.0
                if self.kind in NO_SCALAR_COORDINATE
                else unit_value(self.coordinate, self.kind),
                limits=limits,
                rotation=unit_value(self.rotation, "revolute")
                if self.kind == "cylindrical"
                else 0.0,
                rotation_limits=[
                    unit_value(self.rotation_lower, "revolute"),
                    unit_value(self.rotation_upper, "revolute"),
                ]
                if self.kind == "cylindrical" and self.use_rotation_limits
                else None,
                extra_coordinates=extra_joint_arguments(self, self.kind),
                name=self.name,
                joint_name=self.joint_name,
            )
            return self.apply(context, candidate)
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_remove_component(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_remove_component"
    bl_label = "Remove Component Branch"
    bl_description = "Review and remove a component, its descendants and dependent verification requirements; retain reusable Parts"
    bl_options = {"REGISTER", "UNDO"}
    instance_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    confirmed: BoolProperty(
        name="Remove this branch and the listed policy references",
        default=False,
        options={"SKIP_SAVE"},
    )
    preview_page: IntProperty(name="Impact page", default=1, min=1, options={"SKIP_SAVE"})
    _candidate = None
    _impact = None

    def prepare(self, context):
        self.capture_dialog(context)
        component = selected_component(context, assembly(context)) if not self.instance_id else None
        selected = self.instance_id or (component["id"] if component else "")
        if not selected:
            raise bridge.BridgeError("Select one current Assembly component or use its named row.")
        self._candidate, self._impact = edit.remove_component(assembly(context), selected)
        self.instance_id = selected

    def invoke(self, context, event):
        try:
            self.confirmed = False
            self.preview_page = 1
            self.prepare(context)
            return context.window_manager.invoke_props_dialog(
                self, width=620, confirm_text="Remove branch"
            )
        except Exception as exc:
            return reject(self, context, exc)

    def draw(self, context):
        layout = self.layout
        impact = self._impact
        if not impact:
            layout.label(text="Choose a non-root component.")
            return
        layout.label(text="This removes the selected component and all children.", icon="ERROR")
        lines = ["Component: " + row["name"] for row in impact["instances"]]
        lines += ["Joint: " + row["name"] for row in impact["joints"]]
        lines += [
            "Requirement: "
            + row["preset"]
            + " / "
            + row["name"]
            + " ("
            + " ↔ ".join(row["instances"])
            + ")"
            for row in impact["requirements"]
        ]
        lines += [
            "Remove empty clearance preset: " + row["name"] for row in impact["deleted_presets"]
        ]
        pages = max(1, (len(lines) + 9) // 10)
        page = min(self.preview_page, pages)
        layout.label(text=f"Affected items, page {page} of {pages}")
        if pages > 1:
            layout.prop(self, "preview_page")
        for line in lines[(page - 1) * 10 : page * 10]:
            for wrapped in textwrap.wrap(line, width=76):
                layout.label(text=wrapped)
        if impact["active_preset_cleared"]:
            layout.label(
                text="Active preset is removed: checks become measurements-only.", icon="ERROR"
            )
        elif impact["requirements"]:
            layout.label(text="Surviving clearance requirements remain unchanged.")
        else:
            layout.label(text="No verification policy references are affected.")
        layout.label(text="Reusable Part definitions and source snapshots are kept.")
        layout.label(text="Cancel changes nothing. Blender Undo restores the accepted edit.")
        layout.prop(self, "confirmed")

    def execute(self, context):
        try:
            if not self.confirmed:
                raise bridge.BridgeError(
                    "Review the affected branch and explicitly confirm removal."
                )
            if self._candidate is None:
                self.prepare(context)
            if state(context).document_json != self._expected:
                raise bridge.BridgeError(
                    "The assembly changed while removal was open. Reopen the preview."
                )
            result = self.apply(context, self._candidate)
            current = state(context)
            if current.selected_instance_id in {row["id"] for row in self._impact["instances"]}:
                current.selected_instance_id = ""
            if current.selected_joint_id in {row["id"] for row in self._impact["joints"]}:
                current.selected_joint_id = ""
            return result
        except Exception as exc:
            return reject(self, context, exc)

    def cancel(self, context):
        self._candidate = None
        self._impact = None


class MCAD_OT_assembly_frame(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_frame"
    bl_label = "Edit Mate Frame"
    bl_description = "Create a literal frame or an associative stable planar-face frame with explicit local offset"
    bl_options = {"REGISTER", "UNDO"}
    part_id: EnumProperty(name="Part definition", items=part_choices)
    frame_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    name: StringProperty(name="Frame name", default="Mate frame")
    associative: BoolProperty(name="Attach to stable planar face", default=False)
    support_face: EnumProperty(name="Named source face", items=support_face_choices)
    xyz: StringProperty(name="XYZ (mm)", default="0, 0, 0")
    rotation_degrees: StringProperty(name="XYZ rotation (degrees)", default="0, 0, 0")
    advanced_quaternion: BoolProperty(name="Advanced: enter unit WXYZ quaternion", default=False)
    wxyz: StringProperty(name="WXYZ quaternion", default="1, 0, 0, 0")
    _original_orientation = None
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context, event):
        if not self.properties.is_property_set("part_id") or not self.part_id:
            selected = state(context).selected_part_id
            valid = {p["id"] for p in rows(context, "parts")}
            self.part_id = selected if selected in valid else rows(context, "parts")[0]["id"]
        if self.frame_id:
            part = next(p for p in rows(context, "parts") if p["id"] == self.part_id)
            frame = next(f for f in part["mate_frames"] if f["id"] == self.frame_id)
            self.name = frame["name"]
            self.associative = "support_face" in frame
            if self.associative:
                self.support_face = frame["support_face"]
            self.xyz = ", ".join(map(repr, frame["placement"]["xyz_mm"]))
            original = frame["placement"]["wxyz"]
            self.wxyz = ", ".join(map(repr, original))
            self.rotation_degrees = degrees_from_quaternion(original)
            self._original_orientation = (self.rotation_degrees, self.wxyz, original)
        return super().invoke(context, event)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.enabled = not bool(self.frame_id)
        row.prop(self, "part_id")
        layout.prop(self, "name")
        layout.prop(self, "associative")
        if self.associative:
            layout.prop(self, "support_face")
        layout.prop(self, "xyz", text="Face-local offset (mm)" if self.associative else "XYZ (mm)")
        layout.prop(self, "advanced_quaternion")
        layout.prop(self, "wxyz" if self.advanced_quaternion else "rotation_degrees")
        layout.label(
            text="Follows explicit Part updates; face-local rotation/offset."
            if self.associative
            else "Literal part-local frame; not attached to a surface."
        )
        help_lines(
            layout,
            self,
            [
                "XYZ: three comma-separated lengths; mm/cm/m/in/ft literals accepted.",
                "XYZ rotation: right-hand degrees or deg/rad literals, X then Y then Z.",
                "Advanced WXYZ requires four already unit-length values.",
                "Face mode uses the exact planar face centroid and outward +Z normal.",
                "Missing, split or nonplanar faces require explicit reference repair.",
                "Local +Z is the joint axis; local XY fixes zero rotation.",
            ],
        )

    def execute(self, context):
        try:
            orientation = (
                vector(self.wxyz, 4)
                if self.advanced_quaternion
                else quaternion_from_degrees(self.rotation_degrees)
            )
            if self._original_orientation:
                angles, quaternion, original = self._original_orientation
                if (self.advanced_quaternion and self.wxyz == quaternion) or (
                    not self.advanced_quaternion and self.rotation_degrees == angles
                ):
                    orientation = original
            return self.apply(
                context,
                edit.edit_frame(
                    assembly(context),
                    self.part_id,
                    frame_id=self.frame_id,
                    name=self.name,
                    placement={"xyz_mm": vector(self.xyz, 3, "length"), "wxyz": orientation},
                    support_face=self.support_face if self.associative else None,
                ),
            )
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_joint(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_joint"
    bl_label = "Edit Joint Coordinate"
    bl_description = (
        "Edit the canonical joint coordinate and explicit limits; never read mesh transforms"
    )
    bl_options = {"REGISTER", "UNDO"}
    joint_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    _original_axes = {}
    translation_x: StringProperty(default="0")
    use_translation_x_limits: BoolProperty(name="Explicit translation x limits")
    translation_x_lower: StringProperty(default="-90")
    translation_x_upper: StringProperty(default="90")
    translation_y: StringProperty(default="0")
    use_translation_y_limits: BoolProperty(name="Explicit translation y limits")
    translation_y_lower: StringProperty(default="-90")
    translation_y_upper: StringProperty(default="90")
    rotation_x: StringProperty(default="0")
    use_rotation_x_limits: BoolProperty(name="Explicit rotation x limits")
    rotation_x_lower: StringProperty(default="-90")
    rotation_x_upper: StringProperty(default="90")
    rotation_y: StringProperty(default="0")
    use_rotation_y_limits: BoolProperty(name="Explicit rotation y limits")
    rotation_y_lower: StringProperty(default="-90")
    rotation_y_upper: StringProperty(default="90")
    coordinate: StringProperty(default="0")
    rotation: StringProperty(default="0")
    use_rotation_limits: BoolProperty(name="Explicit rotation limits")
    rotation_lower: StringProperty(default="-180")
    rotation_upper: StringProperty(default="180")
    use_limits: BoolProperty(name="Explicit limits")
    lower: StringProperty(default="-90")
    upper: StringProperty(default="90")
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})
    _original = None

    @classmethod
    def poll(cls, context):
        return super().poll(context) and bool(joint_choices(None, context))

    def invoke(self, context, event):
        moving = [j for j in rows(context, "joints") if j["kind"] != "fixed"]
        if self.joint_id not in {j["id"] for j in moving}:
            component = selected_component(context, assembly(context))
            selected = next(
                (j for j in moving if component and j["child"] == component["id"]), None
            )
            if selected is None:
                self.report({"ERROR"}, "Select one current moving component or use a named joint Edit button.")
                return {"CANCELLED"}
            self.joint_id = selected["id"]
        joint = next(j for j in moving if j["id"] == self.joint_id)
        value = saved_coordinates(assembly(context))[joint["id"]]
        self.coordinate = unit_text(value, joint["kind"])
        self.use_limits = joint.get("limits") is not None
        if self.use_limits:
            self.lower, self.upper = (unit_text(v, joint["kind"]) for v in joint["limits"])
        load_extra_joint_fields(self, joint)
        self._original = (self.coordinate, self.lower, self.upper, joint)
        return super().invoke(context, event)

    def draw(self, context):
        joint = next((j for j in rows(context, "joints") if j["id"] == self.joint_id), {})
        self.layout.label(text=joint.get("name", "Joint"), icon="CONSTRAINT")
        if joint.get("coordinate", 0.0) is None:
            driver = controlling_joint(assembly(context), joint["id"])
            name = next(j["name"] for j in rows(context, "joints") if j["id"] == driver)
            self.layout.label(text="Controlled by gear relation. Edit/sample: " + name)
            row = self.layout.row()
            row.enabled = False
            row.prop(self, "coordinate", text="Driven angle (degrees, read-only)")
            self.layout.prop(self, "use_limits")
            if self.use_limits:
                self.layout.prop(self, "lower", text="Lower (degrees)")
                self.layout.prop(self, "upper", text="Upper (degrees)")
        else:
            joint_fields(self.layout, self, joint.get("kind", "slider"))
        help_lines(
            self.layout,
            self,
            joint_help_lines(joint.get("kind", "slider")),
        )

    def execute(self, context):
        try:
            joint = next(j for j in rows(context, "joints") if j["id"] == self.joint_id)
            if joint.get("coordinate", 0.0) is None:
                # UI permits limits only. A direct scripted coordinate attempt also
                # fails rather than pretending to move a controlled axis.
                if self.properties.is_property_set("coordinate") and not self._original:
                    raise ValueError(
                        "This angle is gear-controlled; edit/sample the independent driver."
                    )
                coordinate = None
            else:
                coordinate = unit_value(self.coordinate, joint["kind"])
            limits = (
                [unit_value(self.lower, joint["kind"]), unit_value(self.upper, joint["kind"])]
                if self.use_limits
                else None
            )
            if self._original:
                old_coord, old_lower, old_upper, old = self._original
                if self.coordinate == old_coord:
                    coordinate = old.get("coordinate", 0.0)
                if limits and old.get("limits"):
                    limits = [
                        old["limits"][n] if value == old_value else limits[n]
                        for n, (value, old_value) in enumerate(
                            ((self.lower, old_lower), (self.upper, old_upper))
                        )
                    ]
            return self.apply(
                context,
                edit.edit_joint(
                    assembly(context),
                    self.joint_id,
                    coordinate=coordinate,
                    limits=limits,
                    extra_coordinates=extra_joint_arguments(self, joint["kind"]),
                    rotation=unit_value(self.rotation, "revolute")
                    if joint["kind"] == "cylindrical"
                    else None,
                    rotation_limits=[
                        unit_value(self.rotation_lower, "revolute"),
                        unit_value(self.rotation_upper, "revolute"),
                    ]
                    if joint["kind"] == "cylindrical" and self.use_rotation_limits
                    else None,
                ),
            )
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_edit_instance_source(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_edit_instance_source"
    bl_label = "Edit Source Part"
    bl_description = (
        "Open this instance's shared source in the existing replacement-confirmation dialog. "
        "Editing the working Part does not change the Assembly until Update All Instances"
    )
    assembly_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    instance_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    source_part_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    source_digest: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    output_feature_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        try:
            state_api.require_idle(context)
            data = assembly(context)
            instance = next((i for i in data["instances"] if i["id"] == self.instance_id), None)
            part = next((p for p in data["parts"] if p["id"] == self.source_part_id), None)
            if (
                data["id"] != self.assembly_id
                or instance is None
                or instance["part_id"] != self.source_part_id
                or part is None
                or part["source_digest"] != self.source_digest
                or part["output_feature_id"] != self.output_feature_id
            ):
                raise bridge.BridgeError(
                    "This instance or its source changed. Use its current Edit Source Part button."
                )
            result = bpy.ops.mcad.assembly_open_part("INVOKE_DEFAULT", part_id=part["id"])
            return {"CANCELLED"} if "CANCELLED" in result else {"FINISHED"}
        except Exception as exc:
            return reject(self, context, exc)

    def invoke(self, context, event):
        return self.execute(context)


class MCAD_OT_assembly_open_part(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_open_part"
    bl_label = "Open Embedded Source as Working Part"
    bl_description = (
        "Explicitly replace the working Part with this embedded source; assembly stays unchanged"
    )
    bl_options = {"REGISTER", "UNDO"}
    part_id: EnumProperty(name="Source definition", items=part_choices)
    confirmed: BoolProperty(name="Replace my current working Part", default=False)
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context, event):
        self.confirmed = False
        if not self.properties.is_property_set("part_id"):
            selected = state(context).selected_part_id
            if selected in {p["id"] for p in rows(context, "parts")}:
                self.part_id = selected
        return super().invoke(context, event)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "part_id")
        users = sum(i["part_id"] == self.part_id for i in rows(context, "instances"))
        noun = "instance" if users == 1 else "instances"
        layout.label(text=f"Source used by {users} {noun}. Update All Instances applies to all.")
        working = context.scene.mechanical_cad
        if compact_status.document_is_fresh(working):
            layout.label(text="No working Part open", icon="INFO")
            layout.label(text="Open this source in Part; the Assembly stays unchanged.")
            layout.prop(self, "confirmed", text="Open as working Part")
        else:
            layout.label(text="Current working Part: " + working.document_name)
            layout.label(
                text="Save the working Part first if you want to retain its edits.", icon="ERROR"
            )
            layout.prop(self, "confirmed")
        help_lines(
            layout,
            self,
            [
                "Only the working Part is replaced after confirmation.",
                "Assembly keeps its accepted embedded source revision.",
                "After editing Part, use Update All Instances explicitly.",
            ],
        )

    def execute(self, context):
        try:
            state_api.require_idle(context)
            if not self.confirmed:
                raise bridge.BridgeError(
                    "Confirm replacing the working Part before opening a source."
                )
            self.require_same_working_part(context)
            if self._expected is not None and state(context).document_json != self._expected:
                raise bridge.BridgeError("The assembly changed. Reopen this dialog.")
            document_state._commit_candidate(
                context, edit.working_copy(assembly(context), self.part_id)
            )
            if not bpy.app.background:
                try:
                    workspace.request_workspace(context, "PART", on_ready=display._focus_display)
                except RuntimeError as exc:
                    state(context).last_action_error = "Part opened; switch to Part: " + str(exc)
            return {"FINISHED"}
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_update_source(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_update_source"
    bl_label = "Update All Instances"
    bl_description = (
        "Validate the working Part revision and update every affected assembly instance atomically"
    )
    bl_options = {"REGISTER", "UNDO"}
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return super().poll(context) and _capture_poll(cls, context)

    def invoke(self, context, event):
        # The interactive path reviews a transient full assembly first. Explicit
        # execute remains the existing guarded headless/programmatic operation.
        bpy.ops.mcad.assembly_source_update_preview("INVOKE_DEFAULT")
        # Only the child modal owns Undo. Never register this nonpublishing
        # launcher as Repeat Last: its explicit execute path commits directly.
        return {"CANCELLED"}

    def draw(self, context):
        layout = self.layout
        updates = state_api.source_updates(context)
        data = assembly(context)
        for update in updates:
            layout.label(text="Accepted revision: " + update["accepted_digest"][:12])
            layout.label(text="Working draft: " + update["working_digest"][:12])
            for instance in data["instances"]:
                if instance["id"] in update["instance_ids"]:
                    layout.label(text="Update: " + instance["name"], icon="MESH_CUBE")
        if not updates:
            layout.label(text="No changed working Part source is available.", icon="INFO")
        layout.label(
            text="Literal frames stay at their authored coordinates.", icon="ORIENTATION_LOCAL"
        )
        help_lines(
            layout,
            self,
            [
                "All affected instances update together, or none do.",
                "Face-attached frames follow the current stable planar source face.",
                "Missing or changed topology requires explicit frame repair.",
                "Previous verification becomes stale; check again.",
                "Cancel retains the accepted source and every instance.",
            ],
        )

    def execute(self, context):
        try:
            _require_capture(context)
            self.require_same_working_part(context)
            candidate, _ = edit.update_source(assembly(context), canonical_working_part(context))
            return self.apply(context, candidate)
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_replay(AssemblyJobMixin, AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_replay"
    bl_label = "Replay Assembly"
    bl_description = (
        "Rebuild the accepted assembly asynchronously; Esc or Cancel Replay stops the request"
    )
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        try:
            return self.begin_replay(context)
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_export_step(Operator, ExportHelper):
    bl_idname = "mcad.assembly_export_step"
    bl_label = "Export Assembly STEP"
    bl_description = (
        "Freshly check the saved Assembly pose, then export named reusable Parts and placements"
    )
    bl_options = {"REGISTER"}
    filename_ext = ".step"
    filter_glob: StringProperty(default="*.step;*.stp", options={"HIDDEN"})
    check_existing: BoolProperty(default=True, options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        reason = (
            "Switch to Object Mode before exporting the Assembly."
            if context.mode != "OBJECT"
            else assembly_export_owner.availability_reason(context)
        )
        if reason and callable(getattr(cls, "poll_message_set", None)):
            cls.poll_message_set(reason)
        return not reason

    def invoke(self, context, event):
        try:
            self._export_snapshot = assembly_export_owner.capture(context)
            if not self.filepath:
                name = bpy.path.clean_name(self._export_snapshot["assembly"]["name"]) or "assembly"
                self.filepath = name + self.filename_ext
            return ExportHelper.invoke(self, context, event)
        except Exception as exc:
            self.report({"ERROR"}, str(exc)[:1000])
            return {"CANCELLED"}

    def execute(self, context):
        try:
            if not self.filepath.strip():
                raise bridge.BridgeError("Choose an explicit Assembly STEP file path.")
            path = Path(bpy.path.abspath(self.filepath)).expanduser().absolute()
            if path.suffix.lower() not in (".step", ".stp"):
                path = path.with_name(path.name + self.filename_ext)
            response = assembly_export_owner.run_export(
                context, str(path), snapshot=getattr(self, "_export_snapshot", None)
            )
            self.report({"INFO"} if response["ok"] else {"WARNING"}, state(context).export_message)
            return {"FINISHED"} if response["ok"] else {"CANCELLED"}
        except Exception as exc:
            # The owner already records honest file outcomes, including a write
            # followed by stale settings or unavailable RNA. Never overwrite it
            # with a generic claim that the destination was not written.
            try:
                state(context).last_action_error = str(exc)
            except (AttributeError, ReferenceError, RuntimeError):
                pass
            self.report({"ERROR"}, str(exc)[:1000])
            return {"CANCELLED"}

    def cancel(self, context):
        self._export_snapshot = None

    def draw(self, context):
        self.layout.label(text="Fresh saved-pose check; named Parts and placements in millimetres.")
        self.layout.label(text="Shared Parts remain reusable STEP definitions.")
        self.layout.label(text="No feature history or editable joints are stored in STEP.")
        self.layout.label(
            text="Existing files require confirmation; Blender Undo does not undo files."
        )


CLASSES = (
    (
        MCAD_OT_assembly_new,
        MCAD_OT_assembly_insert,
        MCAD_OT_assembly_remove_component,
        MCAD_OT_assembly_frame,
        MCAD_OT_assembly_joint,
        MCAD_OT_assembly_edit_instance_source,
        MCAD_OT_assembly_open_part,
        MCAD_OT_assembly_update_source,
        MCAD_OT_assembly_replay,
        MCAD_OT_assembly_export_step,
    )
    + assembly_files.CLASSES
    + assembly_gear_ui.CLASSES
    + gear_pair_ui.CLASSES
)
