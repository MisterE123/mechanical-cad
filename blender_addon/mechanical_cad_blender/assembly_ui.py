"""Concise named assembly history and contextual native-icon command menu."""

import json

from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from . import (
    assembly_display,
    assembly_export_owner,
    assembly_joint_viewport,
    assembly_operators,
    assembly_source_update_preview,
    assembly_state,
    workspace,
)
from .assembly_component_context import selected_component
from .assembly_coordinates import NO_SCALAR_COORDINATE, extra_names, structural_dof
from .assembly_gears import controlling_joint, saved_coordinates
from .assembly_job_ui import draw_pending, draw_workload
from .assembly_operator_helpers import assembly, focus_assembly, state, unit_text
from .assembly_summary import verification_summary
from .assembly_verification_ui import draw_verification
from .help_ui import _panel_wrap


class MCAD_OT_assembly_select(Operator):
    bl_idname = "mcad.assembly_select"
    bl_label = "Select Assembly Item"
    bl_description = (
        "Inspect this named definition, instance or joint without changing canonical geometry"
    )
    part_id: StringProperty(options={"HIDDEN"})
    instance_id: StringProperty(options={"HIDDEN"})
    joint_id: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        current, data = state(context), assembly(context)
        instances = {i["id"]: i for i in data["instances"]}
        joints = {j["id"]: j for j in data["joints"]}
        part_ids = {p["id"] for p in data["parts"]}
        joint = joints.get(self.joint_id) if self.joint_id else None
        selected = joint["child"] if joint else self.instance_id
        if selected and selected not in instances or self.part_id and self.part_id not in part_ids:
            self.report({"ERROR"}, "This assembly item no longer exists")
            return {"CANCELLED"}
        if self.joint_id and joint is None:
            self.report({"ERROR"}, "This joint no longer exists")
            return {"CANCELLED"}
        part_id = instances[selected]["part_id"] if selected else self.part_id
        if not part_id:
            return {"CANCELLED"}
        current.selected_part_id = part_id
        if selected:
            current.selected_instance_id = selected
        elif instances.get(current.selected_instance_id, {}).get("part_id") != part_id:
            current.selected_instance_id = ""
        old_joint = joints.get(current.selected_joint_id)
        if joint:
            current.selected_joint_id = joint["id"]
        elif old_joint and (
            instances[old_joint["child"]]["part_id"] != part_id
            or selected
            and old_joint["child"] != selected
        ):
            current.selected_joint_id = ""
        elif not old_joint:
            current.selected_joint_id = ""
        targets = []
        for obj in assembly_display.owned_objects(context.scene, current.owner_id):
            instance_id = obj.get(assembly_display.INSTANCE_KEY)
            include = (
                instance_id == selected
                if selected
                else (obj.get(assembly_display.DEFINITION_KEY) == part_id)
            )
            if joint and obj.get(assembly_display.ROLE_KEY) == "frame":
                include = include or (
                    instance_id == joint["parent"]
                    and obj.get(assembly_display.FRAME_KEY) == joint["parent_frame"]
                )
            if include and obj.name in context.view_layer.objects and not obj.hide_select:
                targets.append(obj)
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in targets:
            obj.select_set(True)
        if targets:
            context.view_layer.objects.active = next(
                (o for o in targets if o.get(assembly_display.ROLE_KEY) == "instance"), targets[0]
            )
        return {"FINISHED"}


class MCAD_OT_assembly_focus(Operator):
    bl_idname = "mcad.assembly_focus"
    bl_label = "Focus Assembly"
    bl_description = (
        "Frame all owned assembly instances and axes; leave inherited Part-only local view"
    )
    whole_scene: BoolProperty(name="Show whole scene", default=False)

    def execute(self, context):
        if not focus_assembly(context, whole_scene=self.whole_scene):
            self.report({"WARNING"}, "Open a 3D Viewport to focus the assembly")
        return {"FINISHED"}


def message(layout, context, text, icon="NONE"):
    for index, line in enumerate(_panel_wrap(context, text)):
        layout.label(text=line, icon=icon if index == 0 else "NONE")


def draw_capture_limit(layout, context):
    reason = assembly_operators.working_part_capture_reason(context)
    if reason:
        message(layout, context, "Working Part capture/update unavailable: " + reason, icon="INFO")
        message(
            layout,
            context,
            "Existing accepted reusable parts and Assembly operations remain available.",
        )
    return reason


def _part_details(layout, context, data):
    box = layout.box()
    box.label(text="Reusable parts", icon="OUTLINER_DATA_MESH")
    selected = state(context).selected_part_id
    if selected not in {p["id"] for p in data["parts"]}:
        selected = data["parts"][0]["id"]
    for part in data["parts"]:
        row = box.row(align=True)
        op = row.operator(
            "mcad.assembly_select",
            text=part["name"],
            icon="MESH_CUBE",
            depress=part["id"] == selected,
        )
        op.part_id = part["id"]
        op = row.operator("mcad.assembly_open_part", text="", icon="GREASEPENCIL")
        op.part_id = part["id"]
        if part["id"] != selected:
            continue
        detail = box.column(align=True)
        detail.label(text="Source revision: " + part["source_digest"][:12])
        detail.label(text="Output: " + part["output_feature_id"])
        detail.operator(
            "mcad.assembly_open_part", text="Edit Part / Export Part", icon="GREASEPENCIL"
        ).part_id = part["id"]
        message(
            detail,
            context,
            "Opens the editable source in Part. After editing, return here and Update All Instances.",
        )
        for frame in part["mate_frames"]:
            op = detail.operator(
                "mcad.assembly_frame", text=frame["name"], icon="ORIENTATION_LOCAL"
            )
            op.part_id, op.frame_id = part["id"], frame["id"]
            xyz = ", ".join(f"{v:g}" for v in frame["placement"]["xyz_mm"])
            detail.label(text=f"  XYZ: {xyz} mm")
            quat = ", ".join(f"{v:.5g}" for v in frame["placement"]["wxyz"])
            detail.label(text=f"  WXYZ: {quat}")
        op = detail.operator("mcad.assembly_frame", text="Add Mate Frame", icon="ADD")
        op.part_id = part["id"]
    try:
        response = json.loads(state(context).report_json)
        for part in response.get("result", {}).get("parts", []):
            if part["id"] == selected:
                volume = part["geometry_check"]["brep"]["volume"]
                box.label(text=f"Part volume: {volume:g} mm³")
    except (ValueError, KeyError, TypeError):
        pass


def _instance_details(layout, context, data):
    box = layout.box()
    box.label(text="Instances", icon="OUTLINER_COLLECTION")
    component = selected_component(context, data)
    selected_id = component["id"] if component else ""
    if component is None:
        message(box, context, "Select one current component in the viewport or its named row.")
    parts = {p["id"]: p["name"] for p in data["parts"]}
    sources = {p["id"]: p for p in data["parts"]}
    for instance in data["instances"]:
        grounded = instance["id"] == data["grounded_instance"]
        row = box.row(align=True)
        op = row.operator(
            "mcad.assembly_select",
            text=instance["name"],
            icon="PINNED" if grounded else "MESH_CUBE",
            depress=instance["id"] == selected_id,
        )
        op.part_id, op.instance_id = instance["part_id"], instance["id"]
        edit_source = row.operator(
            "mcad.assembly_edit_instance_source", text="", icon="GREASEPENCIL"
        )
        edit_source.assembly_id = data["id"]
        edit_source.instance_id = instance["id"]
        edit_source.source_part_id = instance["part_id"]
        edit_source.source_digest = sources[instance["part_id"]]["source_digest"]
        edit_source.output_feature_id = sources[instance["part_id"]]["output_feature_id"]
        if instance["id"] == selected_id:
            box.label(text=("Grounded · " if grounded else "Uses · ") + parts[instance["part_id"]])
        if not grounded and instance["id"] == selected_id:
            box.operator(
                "mcad.assembly_remove_component", text="Remove Component…", icon="TRASH"
            ).instance_id = instance["id"]
            incoming = next((j for j in data["joints"] if j["child"] == instance["id"]), None)
            if incoming:
                move = box.row()
                move.enabled = assembly_state.display_is_current(context) and not data.get(
                    "gear_relations"
                )
                move.operator(
                    "mcad.assembly_visual_joint",
                    text="Place / Edit Component",
                    icon="ORIENTATION_LOCAL",
                ).joint_id = incoming["id"]
                message(
                    box,
                    context,
                    "Move the parent connector to place this component and its children. Child connector sets the attachment point.",
                )

    box.operator("mcad.assembly_insert", text="Reuse a Part", icon="DUPLICATE")
    reason = assembly_operators.working_part_capture_reason(context)
    row = box.row(align=True)
    capture = row.row(align=True)
    capture.enabled = not reason
    capture.operator(
        "mcad.assembly_insert", text="Add Working Part", icon="ADD"
    ).use_working_part = True
    if reason:
        row.operator("mcad.assembly_status_details", text="", icon="INFO")


def _joint_details(layout, context, data):
    box = layout.box()
    box.label(text="Tree joints", icon="CONSTRAINT")
    display_current = assembly_state.display_is_current(context)
    if data.get("gear_relations"):
        message(
            box,
            context,
            "Gear-coupled motion: edit the driver below. Connectors use named Mate Frames.",
        )
    else:
        place = box.row()
        place.enabled = len(data["instances"]) > 1 and display_current
        place.operator(
            "mcad.assembly_visual_joint", text="Place Joint in Viewport", icon="PIVOT_CURSOR"
        )
        message(
            box,
            context,
            "Pick parent and child, sample surfaces or position literal connectors, then preview and Apply.",
        )
        place.operator(
            "mcad.assembly_visual_joint", text="Mate by Faces", icon="FACESEL"
        ).mate_faces = True
        message(
            box,
            context,
            "Pick parent planar face, then child planar face. Centroid and normal define each connector; Flip, Roll and XYZ offsets are explicit. Choose any existing joint kind; replaces the child's incoming joint.",
        )
    coordinates = saved_coordinates(data)
    instances = {i["id"]: i["name"] for i in data["instances"]}
    if not data["joints"]:
        box.label(text="Grounded root only. Insert a child to add a joint.")
    for joint in data["joints"]:
        row = box.row(align=True)
        row.operator(
            "mcad.assembly_select",
            text=joint["name"],
            icon="CONSTRAINT",
            depress=joint["id"] == state(context).selected_joint_id,
        ).joint_id = joint["id"]
        if joint["kind"] != "fixed":
            op = row.operator("mcad.assembly_joint", text="Edit", icon="GREASEPENCIL")
            op.joint_id = joint["id"]
        if not data.get("gear_relations"):
            visual = box.row()
            visual.enabled = display_current
            visual.operator(
                "mcad.assembly_visual_joint",
                text="Edit Connectors in Viewport",
                icon="PIVOT_CURSOR",
            ).joint_id = joint["id"]
        if joint["kind"] in {"revolute", "slider"}:
            driver_id = (controlling_joint(data, joint["id"])
                         if joint["kind"] == "revolute" else joint["id"])
            driver_name = next(j["name"] for j in data["joints"] if j["id"] == driver_id)
            motion = box.row()
            motion.enabled = display_current
            op = motion.operator(
                "mcad.assembly_visual_joint",
                text="Preview Slider Motion"
                if joint["kind"] == "slider" else "Preview Driver Motion"
                if driver_id == joint["id"]
                else "Preview Driver: " + driver_name,
                icon="PLAY",
            )
            op.joint_id, op.motion_only = driver_id, True
        message(box, context, f"{instances[joint['parent']]} → {instances[joint['child']]}")
        if joint["kind"] == "fixed":
            box.label(text="Fixed · no motion coordinate")
            message(box, context, "Edit Connectors in Viewport to change placement.")
        elif joint["kind"] not in NO_SCALAR_COORDINATE:
            unit = "°" if joint["kind"] == "revolute" else "mm"
            value = float(unit_text(coordinates[joint["id"]], joint["kind"]))
            box.label(text=f"{joint['kind'].title()}: {value:g} {unit} · local +Z")
            if joint["coordinate"] is None:
                driver = controlling_joint(data, joint["id"])
                name = next(j["name"] for j in data["joints"] if j["id"] == driver)
                message(
                    box,
                    context,
                    "Gear-controlled angle (read-only). Edit/sample independent driver: " + name,
                )
            if joint["limits"]:
                lower, upper = [float(unit_text(v, joint["kind"])) for v in joint["limits"]]
                box.label(text=f"Limits: {lower:g} to {upper:g} {unit}")
            else:
                box.label(text="No authored limits")
        for field in extra_names(joint["kind"]):
            unit_kind = "slider" if field.startswith("translation") else "revolute"
            unit = "mm" if unit_kind == "slider" else "°"
            label = field.replace("_", " ").title() + (" Z" if field == "rotation" else "")
            box.label(text=f"{label}: {float(unit_text(joint[field], unit_kind)):g} {unit}")
            if joint[field + "_limits"] is not None:
                lo, hi = [float(unit_text(v, unit_kind)) for v in joint[field + "_limits"]]
                box.label(text=f"{label} limits: {lo:g} to {hi:g} {unit}")
        if joint["kind"] == "spherical":
            box.label(text="Fixed center; Euler X → Y → Z, component limits.")
        box.label(text=f"Frames: {joint['parent_frame']} → {joint['child_frame']}")


def _gear_details(layout, context, data):
    box = layout.box()
    box.label(text="Gear coordinate relations", icon="CONSTRAINT")
    joints = {joint["id"]: joint for joint in data["joints"]}
    relations = data.get("gear_relations", [])
    dof = sum(structural_dof(joint) for joint in joints.values()) - len(relations)
    box.label(text=f"Independent tree coordinates: {dof}")
    message(box, context, "Structural count, not a closed-loop solver or contact verification.")
    add = box.row()
    add.enabled = len([joint for joint in joints.values() if joint["kind"] == "revolute"]) >= 2
    add.operator("mcad.assembly_gear", text="Add Gear Relation", icon="ADD")
    for relation in relations:
        row = box.row(align=True)
        row.operator(
            "mcad.assembly_gear", text=relation["name"], icon="GREASEPENCIL"
        ).relation_id = relation["id"]
        row.operator(
            "mcad.assembly_remove_gear", text="Remove", icon="TRASH"
        ).relation_id = relation["id"]
        for role in ("driver", "driven"):
            joint = joints[relation[role + "_joint"]]
            message(box, context, role.title() + ": " + joint["name"] + " (" + joint["id"] + ")")
        direction = "opposite" if relation["ratio"] < 0 else "same"
        phase = float(unit_text(relation["offset_rad"], "revolute"))
        message(
            box,
            context,
            f"Signed ratio: {relation['ratio']:g} ({direction} coordinate direction); phase: {phase:g}°",
        )
        message(
            box, context, "Driven angle = ratio × driver angle + phase. Driven limits still apply."
        )
    if relations:
        message(
            box,
            context,
            "No tooth geometry, physical contact, dynamics or rack/screw coupling is inferred.",
        )


class MCAD_OT_assembly_status_details(Operator):
    bl_idname = "mcad.assembly_status_details"
    bl_label = "Assembly Status Details"
    bl_description = (
        "Explain geometry, checks, working Part and STEP. "
        "Contact policy acceptance is not a measured clearance pass"
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=520)

    def draw(self, context):
        layout = self.layout
        current = state(context)
        display_current = assembly_state.display_is_current(context)
        draw_workload(layout, context)
        message(
            layout,
            context,
            "Accepted Assembly geometry is current."
            if display_current
            else "Assembly geometry needs rebuilding. Use Rebuild before checking.",
        )
        if assembly_state.source_updates(context):
            message(
                layout,
                context,
                "The working Part has edits not yet accepted by this Assembly. "
                "Use Update All Instances to include them; Rebuild uses accepted Parts.",
            )
        draw_capture_limit(layout, context)
        reason = assembly_export_owner.availability_reason(context)
        message(
            layout,
            context,
            "STEP unavailable: " + reason
            if reason
            else "STEP is available for the checked, accepted Assembly pose.",
        )
        if current.last_action_error:
            message(layout, context, current.last_action_error, icon="ERROR")
        verdict, _icon = verification_summary(
            current.report_json, current=assembly_state.report_is_current(context)
        )
        if verdict.endswith("Contact policy accepted"):
            report = json.loads(current.report_json)["report"]
            message(
                layout,
                context,
                f"Check status: {report.get('status', 'unavailable')}; "
                f"passed={report.get('passed')!r}; "
                f"policy_accepted={report.get('policy_accepted')!r}",
            )
            message(
                layout,
                context,
                "Contact policy accepted: tolerance-band exceptions are allowed. "
                "This is not a measured clearance pass or proof of exact touching.",
            )
        if current.verification_message:
            message(layout, context, current.verification_message)
        layout.operator("mcad.assembly_report", text="Inspect Check Measurements", icon="INFO")
        if current.export_message:
            message(layout, context, "Last export (historical): " + current.export_message)
        message(
            layout,
            context,
            "Checks cover listed poses only, not continuous motion, "
            "physical fit, strength or manufacturing certification.",
        )

    def execute(self, context):
        return {"FINISHED"}


def _section(layout, context, field, title):
    current = state(context)
    opened = getattr(current, field)
    layout.prop(
        current, field, text=title, emboss=False, icon="TRIA_DOWN" if opened else "TRIA_RIGHT"
    )
    return layout.column() if opened else None


def _primary_actions(layout, context, data):
    """Brief currentness and action strip; existing operators retain all admission guards."""
    current = state(context)
    display_current = assembly_state.display_is_current(context)
    checked = assembly_state.report_is_current(context)
    row = layout.row(align=True)
    row.label(
        text="Geometry current" if display_current else "Rebuild before checking",
        icon="CHECKMARK" if display_current else "ERROR",
    )
    row.operator("mcad.assembly_status_details", text="", icon="INFO")
    label, icon = verification_summary(current.report_json, current=checked)
    layout.label(text=label, icon=icon)
    row = layout.row(align=True)
    row.operator("mcad.assembly_replay", text="Rebuild", icon="FILE_REFRESH")
    check = row.row(align=True)
    check.enabled = display_current
    check.operator("mcad.assembly_check", text="Check", icon="CHECKMARK")
    export = row.row(align=True)
    reason = assembly_export_owner.availability_reason(context)
    export.enabled = not reason
    export.operator("mcad.assembly_export_step", text="STEP", icon="EXPORT")
    if reason:
        layout.operator("mcad.assembly_status_details", text="Why STEP is unavailable", icon="INFO")
    selected = next(
        (p for p in data["verification_presets"] if p["id"] == data["active_verification_preset"]),
        None,
    )
    if selected:
        layout.label(text="Check settings: " + selected["name"], icon="PRESET")
    if not data["active_verification_preset"]:
        if data["verification_presets"]:
            layout.operator(
                "mcad.assembly_select_preset", text="Choose saved check settings", icon="PRESET"
            )
        else:
            layout.operator(
                "mcad.assembly_standard_check_setup", text="Set up standard checks", icon="ADD"
            )
            layout.label(text="Strict · no contact exceptions", icon="INFO")
    if current.last_action_error:
        layout.operator(
            "mcad.assembly_status_details", text="Action failed · view details", icon="ERROR"
        )
    if assembly_state.source_updates(context):
        layout.label(text="Working Part edits not included", icon="INFO")
        layout.operator(
            "mcad.assembly_update_source", text="Update All Instances", icon="FILE_REFRESH"
        )


def draw_assembly_history(layout, context):
    """Assembly-only pane: no Part feature rows masquerade as assembly history."""
    current = state(context)
    layout.label(text="Assembly", icon="OUTLINER_COLLECTION")
    if assembly_source_update_preview.active(context):
        layout.operator("mcad.assembly_source_update_cancel", text=assembly_source_update_preview.active(context).cancel_label, icon="CANCEL")
        layout = layout.column()
        layout.enabled = False
    if assembly_joint_viewport.active(context):
        message(
            layout,
            context,
            "Visual joint preview is not saved or checked. Use Apply or Cancel in the viewport.",
            icon="INFO",
        )
        layout.operator(
            "mcad.assembly_visual_joint_cancel", text="Cancel Joint Preview", icon="CANCEL"
        )
        layout = layout.column()
        layout.enabled = False
    if draw_pending(layout, context):
        layout = layout.column()
        layout.enabled = False
    else:
        from .history_rebuild import draw_cancel

        if draw_cancel(layout, context):
            message(
                layout,
                context,
                "Waiting to rebuild accepted Assembly display; saved checks remain historical.",
            )
            layout = layout.column()
            layout.enabled = False
    if workspace.active_draft() or workspace.has_draft(context):
        message(
            layout,
            context,
            "Finish, cancel or discard the sketch draft before assembly work.",
            icon="ERROR",
        )
        layout = layout.column()
        layout.enabled = False
    if not current.document_json:
        draw_capture_limit(layout, context)
        message(
            layout,
            context,
            "Capture an existing solid Part, or configure a new printable gear pair.",
        )
        layout.operator("mcad.assembly_new", icon="ADD")
        layout.operator("mcad.gear_pair", icon="MOD_SCREW")
        layout.operator("mcad.assembly_load", icon="FILE_FOLDER")
        return
    try:
        data = assembly(context)
    except Exception as exc:
        message(layout, context, str(exc), icon="ERROR")
        layout.operator("mcad.assembly_load", icon="FILE_FOLDER")
        return
    layout.label(text=data["name"])
    _primary_actions(layout, context, data)
    row = layout.row(align=True)
    row.operator("mcad.assembly_save", text="Save", icon="FILE_TICK")
    row.operator("mcad.assembly_focus", text="Focus", icon="ZOOM_SELECTED")
    for obj in assembly_display.owned_objects(context.scene, current.owner_id):
        warning = obj.get("mechanical_cad_assembly_precision_warning")
        if warning:
            message(layout, context, str(warning), icon="ERROR")
            break
    # Primary pair editing/printing must not hide behind low-level mate frames.
    # The same guarded source-open and recognition paths remain authoritative.
    from .gear_pair_ui import draw_gear_parts

    draw_gear_parts(layout, data)
    _instance_details(layout, context, data)
    body = _section(layout, context, "show_parts", "Reusable Parts & mate frames")
    if body:
        _part_details(body, context, data)
    body = _section(layout, context, "show_joints", "Joints & motion")
    if body:
        _joint_details(body, context, data)
        _gear_details(body, context, data)
    body = _section(layout, context, "show_checks", "Check policy & detailed report")
    if body:
        draw_verification(body, context, data)
    body = _section(layout, context, "show_options", "Assembly options")
    if body:
        body.label(text=f"Rebuild tolerance: {data.get('replay_tolerance_mm', 1e-6)!r} mm")
        body.label(text="Rebuild precision is separate from check policy.")
        body.operator("mcad.assembly_replay_tolerance", text="Set Rebuild Tolerance")
        body.operator(
            "mcad.assembly_focus", text="Show Whole Scene", icon="SCENE_DATA"
        ).whole_scene = True
        message(body, context, "Rooted joint trees only. No closed-loop mate solver.", icon="INFO")


def draw_assembly_menu(layout, context):
    if assembly_source_update_preview.active(context):
        layout.operator("mcad.assembly_source_update_cancel", text=assembly_source_update_preview.active(context).cancel_label, icon="CANCEL")
        return
    if assembly_joint_viewport.active(context):
        layout.operator(
            "mcad.assembly_visual_joint_cancel", text="Cancel Joint Preview", icon="CANCEL"
        )
        return
    draw_capture_limit(layout, context)
    layout.operator("mcad.assembly_new", icon="ADD")
    layout.operator("mcad.gear_pair", icon="MOD_SCREW")
    layout.operator("mcad.assembly_load", icon="FILE_FOLDER")
    layout.operator("mcad.assembly_save", icon="FILE_TICK")
    layout.operator("mcad.assembly_focus", icon="ZOOM_SELECTED")
    layout.operator(
        "mcad.assembly_focus", text="Show Whole Scene", icon="SCENE_DATA"
    ).whole_scene = True
    layout.separator()
    layout.operator("mcad.assembly_insert", icon="DUPLICATE")
    layout.operator("mcad.assembly_frame", icon="ORIENTATION_LOCAL")
    layout.operator("mcad.assembly_gear", icon="CONSTRAINT")
    layout.operator("mcad.assembly_visual_joint", icon="PIVOT_CURSOR")
    layout.operator("mcad.assembly_open_part", icon="GREASEPENCIL")
    layout.operator("mcad.assembly_update_source", icon="FILE_REFRESH")
    layout.operator("mcad.assembly_replay", icon="FILE_REFRESH")
    layout.separator()
    layout.operator("mcad.assembly_preset", icon="PREFERENCES")
    layout.operator("mcad.assembly_select_preset", icon="PRESET")
    layout.operator("mcad.assembly_check", icon="CHECKMARK")
    layout.operator("mcad.assembly_sample", icon="ACTION")
    layout.operator("mcad.assembly_export_step", icon="EXPORT")


CLASSES = (MCAD_OT_assembly_select, MCAD_OT_assembly_focus, MCAD_OT_assembly_status_details)
