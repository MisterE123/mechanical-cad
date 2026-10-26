"""Saved engineering intent, explicit pose checks and bounded discrete sampling."""

import json
import math
import textwrap

from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import assembly_edit as edit
from . import assembly_pending, bridge, execution_lease
from . import assembly_state as state_api
from .assembly_coordinates import NO_SCALAR_COORDINATE, extra_names
from .assembly_job_ui import AssemblyJobMixin, draw_workload
from .assembly_operator_helpers import (
    AssemblyEdit,
    assembly,
    choices,
    help_lines,
    instance_choices,
    joint_choices,
    number,
    reject,
    rows,
    sample_coordinate_choices,
    state,
    unit_value,
)


def preset_choices(self, context):
    return [("*none*", "No active preset", "Measurements cannot establish a pass")] + choices(
        rows(context, "verification_presets")
    )


class MCAD_OT_assembly_select_preset(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_select_preset"
    bl_label = "Select Active Verification Preset"
    bl_description = (
        "Explicitly select saved verification intent or clear it; never infer a pass preset"
    )
    bl_options = {"REGISTER", "UNDO"}
    preset_id: EnumProperty(name="Active preset", items=preset_choices)

    def invoke(self, context, event):
        self.preset_id = assembly(context)["active_verification_preset"] or "*none*"
        return super().invoke(context, event)

    def draw(self, context):
        self.layout.prop(self, "preset_id")
        self.layout.label(text="Selection is saved. Run Check explicitly after Apply.")

    def execute(self, context):
        try:
            return self.apply(
                context,
                edit.select_verification_preset(
                    assembly(context), None if self.preset_id == "*none*" else self.preset_id
                ),
            )
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_preset(AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_preset"
    bl_label = "Edit Verification Preset"
    bl_description = "Save named pair clearance separately from advanced numerical query tolerances"
    bl_options = {"REGISTER", "UNDO"}
    preset_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    name: StringProperty(name="Preset name", default="Clearance check")
    kind: EnumProperty(
        name="Checking intent",
        items=[
            (
                "clearance",
                "Named pair clearance",
                "Engineering minimum separation for explicit pairs",
            ),
            ("interference_only", "Interference only", "No engineering clearance allowance"),
        ],
    )
    pair_a: EnumProperty(name="First instance", items=instance_choices)
    pair_b: EnumProperty(name="Second instance", items=instance_choices)
    requirement_name: StringProperty(name="Requirement name", default="Minimum separation")
    minimum_mm: StringProperty(name="Engineering minimum (mm)", default="1.0")
    accept_contact: BoolProperty(
        name="Accept intended contact within numerical tolerance band",
        default=False,
        description="Explicit policy for this zero-minimum pair, not proof of contact or zero penetration",
    )
    linear: StringProperty(name="Linear query tolerance (mm)", default="1e-6")
    volume: StringProperty(name="Common-volume threshold (mm³)", default="1e-9")
    deflection: StringProperty(name="Tessellation deflection (mm)", default="0.1")
    advanced: BoolProperty(name="Advanced numerical policy", default=False)
    activate: BoolProperty(name="Make this the active verification preset", default=False)
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context, event):
        data = assembly(context)
        self.accept_contact = False
        if self.preset_id:
            preset = next(p for p in data["verification_presets"] if p["id"] == self.preset_id)
            self.name, self.kind = preset["name"], preset["kind"]
            self.activate = data["active_verification_preset"] == self.preset_id
            policy = preset["policy"]
            self.linear = repr(policy["linear_tolerance_mm"])
            self.volume = repr(policy["volume_tolerance_mm3"])
            self.deflection = repr(policy["linear_deflection_mm"])
            selected = sorted((self.pair_a, self.pair_b))
            requirement = next(
                (r for r in preset["requirements"] if sorted(r["instances"]) == selected), None
            )
            if requirement is None and preset["requirements"]:
                requirement = preset["requirements"][0]
            if requirement:
                self.pair_a, self.pair_b = requirement["instances"]
                self.requirement_name = requirement["name"]
                self.minimum_mm = repr(requirement["minimum_mm"])
                self.accept_contact = requirement.get("contact_policy") == "accept_tolerance_band"
        else:
            self.activate = False
            if len(data["instances"]) >= 2:
                self.pair_a, self.pair_b = (i["id"] for i in data["instances"][:2])
        return super().invoke(context, event)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "name")
        layout.prop(self, "kind")
        if self.kind == "clearance":
            for key in ("pair_a", "pair_b", "requirement_name", "minimum_mm"):
                layout.prop(self, key)
            layout.prop(self, "accept_contact")
            if self.accept_contact:
                layout.label(text="Requires minimum 0 mm. Accepts only this named pair.")
                layout.label(
                    text="Tolerance ambiguity remains; not proof of zero penetration.", icon="ERROR"
                )
            layout.label(text="Apply adds/edits this pair; other named pairs stay saved.")
        else:
            layout.label(text="No engineering clearance requirement will be saved.", icon="INFO")
            if self.preset_id:
                layout.label(
                    text="Apply removes this preset’s existing clearance pairs.", icon="ERROR"
                )
        layout.prop(self, "advanced")
        if self.advanced:
            box = layout.box()
            for key in ("linear", "volume", "deflection"):
                box.prop(self, key)
            box.label(text="Numerical thresholds are not engineering fit allowances.")
        layout.prop(self, "activate")
        help_lines(
            layout,
            self,
            [
                "Clearance is the required separation of a named instance pair.",
                "Numerical policy controls finite-resolution kernel queries.",
                "Saving or selecting a preset does not run a check.",
                "No preset means measurements only; no pass is inferred.",
            ],
        )

    def execute(self, context):
        try:
            original = assembly(context)
            candidate = edit.edit_verification_preset(
                original,
                preset_id=self.preset_id,
                name=self.name,
                kind=self.kind,
                policy={
                    "linear_tolerance_mm": number(self.linear, "length"),
                    "volume_tolerance_mm3": number(self.volume),
                    "linear_deflection_mm": number(self.deflection, "length"),
                },
                pair=[self.pair_a, self.pair_b] if self.kind == "clearance" else None,
                minimum_mm=number(self.minimum_mm, "length") if self.kind == "clearance" else None,
                requirement_name=self.requirement_name,
                contact_policy="accept_tolerance_band"
                if self.kind == "clearance" and self.accept_contact
                else None,
            )
            if not self.activate:
                candidate = edit.select_verification_preset(
                    candidate, original["active_verification_preset"]
                )
            return self.apply(context, candidate)
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_standard_check_setup(AssemblyJobMixin, AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_standard_check_setup"
    bl_label = "Set Up Standard Checks"
    bl_description = (
        "Save strict interference-only settings: 1e-6 mm linear, 1e-9 mm³ volume, "
        "0.1 mm tessellation; no contact exceptions or clearance allowance. "
        "Then use Check current pose"
    )
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        try:
            # Capture admits only an idle, current context before any candidate
            # exists. The existing owner revalidates it through publication.
            snapshot = assembly_pending.capture_candidate(context)
            candidate = edit.standard_verification_preset(assembly(context))
            return self.begin_candidate(context, candidate, snapshot, editing=True)
        except Exception as exc:
            return reject(self, context, exc)

    def _job_accepted(self, context, response):
        self.report({"INFO"}, "Standard settings saved. Use Check current pose to check solids.")


class MCAD_OT_assembly_check(AssemblyJobMixin, AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_check"
    bl_label = "Check Current Pose"
    bl_description = (
        "Freshly check exact solids at the saved pose using only the explicitly active preset"
    )
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        try:
            # Reject repeated clicks before capture_dialog admits a newer
            # interaction, which would otherwise revoke the in-flight check.
            if execution_lease.is_busy():
                raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
            self._asynchronous = True
            self.capture_dialog(context)
            return self.execute(context)
        except Exception as exc:
            return reject(self, context, exc)

    def draw(self, context):
        draw_workload(self.layout, context)

    def execute(self, context):
        try:
            self.require_same_working_part(context)
            if self._expected is not None and state(context).document_json != self._expected:
                raise bridge.BridgeError(
                    "Assembly changed since checking opened. Reopen the dialog."
                )
            if self._asynchronous:
                return self.begin_job(context, "assembly_check")
            result = state_api.check(context)
            self.report({"INFO"}, state(context).verification_message[:1000])
            return {"FINISHED"} if result else {"CANCELLED"}
        except Exception as exc:
            return reject(self, context, exc)


class MCAD_OT_assembly_sample(AssemblyJobMixin, AssemblyEdit, Operator):
    bl_idname = "mcad.assembly_sample"
    bl_label = "Check Listed Joint Poses"
    bl_description = (
        "Check 1–32 explicit coordinates; retain all other saved coordinates; sampled-only evidence"
    )
    bl_options = {"REGISTER"}
    joint_id: EnumProperty(name="Sampled joint", items=sample_coordinate_choices)
    values: StringProperty(name="Explicit sample coordinates", default="0, 30, 60")
    show_help: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return super().poll(context) and bool(joint_choices(None, context))

    def invoke(self, context, event):
        self._asynchronous = True
        return super().invoke(context, event)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "joint_id")
        joint = next(
            (j for j in rows(context, "joints") if j["id"] == self.joint_id.split(":")[0]), {}
        )
        unit = (
            "degrees"
            if joint.get("kind") == "revolute"
            or (":" in self.joint_id and self.joint_id.split(":")[1].startswith("rotation"))
            else "mm"
        )
        layout.prop(self, "values", text=f"Listed samples ({unit})")
        draw_workload(layout, context, len(self.values.split(",")))
        layout.label(
            text="Only listed discrete poses; no continuous collision guarantee.", icon="ERROR"
        )
        help_lines(
            layout,
            self,
            [
                "Enter 1–32 comma-separated finite numbers; no inferred sweep.",
                "All other independent coordinates stay saved; gear-driven angles follow their driver.",
                "The active saved preset controls checking intent and precision.",
                "Sampling does not move the accepted display or change its pose.",
            ],
        )

    def execute(self, context):
        try:
            self.require_same_working_part(context)
            if self._expected is not None and state(context).document_json != self._expected:
                raise bridge.BridgeError(
                    "Assembly changed since sampling opened. Reopen the dialog."
                )
            joint = next(
                j for j in rows(context, "joints") if j["id"] == self.joint_id.split(":")[0]
            )
            entries = self.values.split(",")
            if not 1 <= len(entries) <= 32:
                raise bridge.BridgeError("List 1–32 explicit sample coordinates.")
            values = [
                unit_value(
                    v.strip(),
                    "revolute"
                    if (":" in self.joint_id and self.joint_id.split(":")[1].startswith("rotation"))
                    else joint["kind"],
                )
                for v in entries
            ]
            if self._asynchronous:
                return self.begin_job(
                    context, "assembly_sample", joint_id=self.joint_id, values=values
                )
            state_api.sample(context, self.joint_id, values)
            self.report({"INFO"}, state(context).verification_message[:1000])
            return {"FINISHED"}
        except Exception as exc:
            return reject(self, context, exc)


REPORT_PAGE_LINES = 8
REPORT_LINE_WIDTH = 72


def _report_number(value):
    return f"{value:.9g}" if isinstance(value, (float, int)) else "unavailable"


def _report_lines(response, section, pose_index):
    """Complete read-only text, paged after wrapping; never truncate diagnostic text."""
    report = response["report"]
    snapshot = response["result"]["canonical_assembly"]
    poses = report.get("poses", [])
    outcome = poses[pose_index] if 0 <= pose_index < len(poses) else {}
    names = {i["id"]: i["name"] for i in snapshot["instances"]}
    lines = []
    if section == "SUMMARY":
        basis = report.get("verification_basis") or {}
        preset = basis.get("preset") or {}
        lines = [
            f"Aggregate result: {report.get('status', 'unknown')}",
            f"Passed: {bool(report.get('passed'))} · Complete: {bool(report.get('complete'))}",
            f"Known interference: {bool(report.get('known_interference'))}",
            f"Known clearance violation: {bool(report.get('known_clearance_violation'))}",
            f"Threshold contact: {bool(report.get('has_threshold_contacts'))}",
            f"Preset: {preset.get('name', 'None · measurements only')}",
            f"Listed poses: {len(poses)}",
        ]
        if "policy_accepted" in report:
            lines += [
                f"Explicit tolerance-band policy accepted: {report['policy_accepted']}",
                "Measured clearance pass is unchanged; numerical ambiguity remains.",
                "Not proof of exact contact, zero penetration, physical fit or strength.",
            ]
        if outcome:
            lines += [
                f"Pose {pose_index}: {outcome.get('status', 'unknown')}",
                f"Pose passed: {bool(outcome.get('passed'))} · Complete: {bool(outcome.get('complete'))}",
            ]
    elif section == "COORDINATES" and outcome:
        pose = outcome["pose"]
        requested, effective = (
            pose.get("requested_coordinates") or {},
            pose.get("effective_coordinates") or {},
        )
        for joint in snapshot["joints"]:
            fields = (
                []
                if joint["kind"] in NO_SCALAR_COORDINATE
                else [(joint["id"], "coordinate", joint["kind"] == "revolute")]
            ) + [
                (joint["id"] + ":" + field, field, field.startswith("rotation"))
                for field in extra_names(joint["kind"])
            ]
            for key, field, angular in fields:
                wanted = requested.get(key, joint.get(field, 0))
                actual = effective.get(key)
                unit = "degrees" if angular else "mm"
                if angular:
                    wanted = math.degrees(wanted)
                    actual = math.degrees(actual) if actual is not None else None
                lines += [
                    joint["name"] + " · " + field.replace("_", " "),
                    f"Requested: {_report_number(wanted)} {unit} · Effective: {_report_number(actual)} {unit}",
                ]
    elif section == "PAIRS" and outcome:
        policy = report.get("effective_policy") or {}
        preset = (report.get("verification_basis") or {}).get("preset") or {}
        intended = {
            tuple(r["instances"])
            for r in preset.get("requirements", [])
            if r.get("contact_policy") == "accept_tolerance_band"
        }
        lines += [
            f"Linear tolerance: {_report_number(policy.get('linear_tolerance_mm'))} mm",
            f"Volume threshold: {_report_number(policy.get('volume_tolerance_mm3'))} mm³",
            "Numerical guardrails, not certified error bounds or fit allowances.",
        ]
        for index, pair in enumerate(outcome.get("pairs", [])):
            lines += [
                f"Pair {index + 1}: " + " / ".join(names.get(i, i) for i in pair["instances"]),
                f"{pair['relation']} · {pair['clearance_verdict']} · Complete: {pair['complete']}",
                f"Distance: {_report_number(pair.get('minimum_distance_mm'))} mm · "
                f"Required: {_report_number(pair.get('minimum_required_mm'))} mm",
                f"Common volume: {_report_number(pair.get('common_volume_mm3'))} mm³",
            ]
            if tuple(pair["instances"]) in intended:
                lines.append(
                    "Authored intent: accept tolerance-band contact; measurement remains unchanged."
                )
    elif section == "DIAGNOSTICS":

        def add(label, diagnostic):
            if diagnostic:
                lines.append(
                    label + ": " + json.dumps(diagnostic, ensure_ascii=False, sort_keys=True)
                )

        add("Request", response.get("error"))
        for diagnostic in report.get("diagnostics", []):
            add("Report", diagnostic)
        for diagnostic in outcome.get("diagnostics", []):
            add(f"Pose {pose_index}", diagnostic)
        for diagnostic in outcome.get("pose", {}).get("diagnostics", []):
            add(f"Pose {pose_index} kinematics", diagnostic)
        for pair in outcome.get("pairs", []):
            label = " / ".join(names.get(i, i) for i in pair["instances"])
            for diagnostic in pair.get("diagnostics", []):
                add(label, diagnostic)
        for source in response["result"].get("source_replays", []):
            for feature in source.get("features", []):
                add(
                    f"Source {source['source_document_id']} · feature {feature['id']}",
                    feature.get("error"),
                )
    if not lines:
        lines = [
            "No diagnostics recorded."
            if section == "DIAGNOSTICS"
            else "No rows for this pose. Select an available pose index."
        ]
    return [
        line
        for text in lines
        for line in textwrap.wrap(
            text, width=REPORT_LINE_WIDTH, break_long_words=True, break_on_hyphens=False
        )
    ]


def _report_page_reset(self, context):
    self.page = 1  # Operator RNA only; no scene/report mutation or Python draft attributes.


class MCAD_OT_assembly_report(Operator):
    bl_idname = "mcad.assembly_report"
    bl_label = "Inspect Assembly Evidence"
    bl_description = (
        "Read paged pose summaries, coordinates, named pair measurements and complete diagnostics"
    )
    section: EnumProperty(
        name="Section",
        items=[
            ("SUMMARY", "Summary", "Aggregate and selected-pose evidence"),
            ("COORDINATES", "Coordinates", "Requested and effective named joint values"),
            ("PAIRS", "Pairs", "Named instance-pair distances and common volumes"),
            ("DIAGNOSTICS", "Diagnostics", "Complete request, source, pose and pair errors"),
        ],
        update=_report_page_reset,
    )
    pose_index: IntProperty(
        name="Pose (zero-based)", default=0, min=0, max=31, update=_report_page_reset
    )
    page: IntProperty(name="Page", default=1, min=1)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=600, confirm_text="Close")

    def draw(self, context):
        layout = self.layout
        try:
            response = json.loads(state(context).report_json)
            lines = _report_lines(response, self.section, self.pose_index)
        except (ValueError, KeyError, TypeError):
            layout.label(text="No readable evidence. Run an explicit check.", icon="ERROR")
            return
        trusted = state_api.report_is_current(context)
        layout.label(
            text="Current evidence" if trusted else "Historical evidence · check again",
            icon="CHECKMARK" if trusted else "ERROR",
        )
        layout.label(text="Listed poses only. No continuous or structural guarantee.")
        layout.row(align=True).prop(self, "section", expand=True)
        controls = layout.row(align=True)
        controls.prop(self, "pose_index")
        controls.prop(self, "page")
        pages = max(1, (len(lines) + REPORT_PAGE_LINES - 1) // REPORT_PAGE_LINES)
        count = len(response["report"].get("poses", []))
        layout.label(
            text=f"Page {self.page} of {pages} · available poses: 0–{count - 1}"
            if count
            else f"Page {self.page} of {pages} · no evaluated poses"
        )
        if self.page > pages:
            layout.label(text=f"Choose page 1 through {pages}.", icon="INFO")
            return
        start = (self.page - 1) * REPORT_PAGE_LINES
        for line in lines[start : start + REPORT_PAGE_LINES]:
            layout.label(text=line)

    def execute(self, context):
        return {"FINISHED"}


def draw_verification(layout, context, data):
    """Display evidence without conflating pass, known violations or completeness."""
    active = data["active_verification_preset"]
    box = layout.box()
    box.label(text="Verification", icon="CHECKMARK")
    preset = next((p for p in data["verification_presets"] if p["id"] == active), None)
    box.label(text="Active: " + (preset["name"] if preset else "None · measurements only"))
    row = box.row(align=True)
    row.operator("mcad.assembly_select_preset", text="Select", icon="PRESET")
    row.operator("mcad.assembly_preset", text="New", icon="ADD")
    for saved in data["verification_presets"]:
        sub = box.box()
        op = sub.operator("mcad.assembly_preset", text=saved["name"], icon="PREFERENCES")
        op.preset_id = saved["id"]
        if saved["kind"] == "interference_only":
            sub.label(text="Interference only · no clearance allowance")
        for req in saved["requirements"]:
            op = sub.operator(
                "mcad.assembly_preset",
                text=f"{req['name']}: {req['minimum_mm']:g} mm",
                icon="DRIVER_DISTANCE",
            )
            op.preset_id = saved["id"]
            op.pair_a, op.pair_b = req["instances"]
            if req.get("contact_policy") == "accept_tolerance_band":
                sub.label(text="Explicit contact-band exception for this pair", icon="INFO")
    row = box.row(align=True)
    row.operator("mcad.assembly_sample", text="Sample", icon="ACTION")
    current = state(context)
    evidence_current = state_api.report_is_current(context)
    label = (
        "Current"
        if evidence_current
        else ("Stale" if current.verification_status == "CURRENT" else current.verification_status)
    )
    box.label(text="Evidence: " + label)
    if not current.report_json:
        return
    try:
        response = json.loads(current.report_json)
        report = response["report"]
    except (ValueError, KeyError, TypeError):
        box.label(text="Report unreadable; replay and check again.", icon="ERROR")
        return
    if response.get("action") == "assembly_replay":
        box.label(text="Display replay only; no verification pass.")
        return
    if not evidence_current:
        box.label(text="Historical evidence; check the current revision.", icon="ERROR")
    box.label(
        text=("Passed: " if evidence_current else "Historical pass: ")
        + ("Yes" if report.get("passed") else "No")
    )
    if "policy_accepted" in report:
        box.label(
            text=(
                "Contact policy accepted: "
                if evidence_current
                else "Historical policy acceptance: "
            )
            + ("Yes" if report["policy_accepted"] else "No")
        )
        box.label(text="Tolerance ambiguity remains; not proof of zero penetration.")
    box.label(
        text="Complete: " + ("Yes" if report.get("complete") else "No · unknown results remain")
    )
    box.label(text="Known interference: " + ("Yes" if report.get("known_interference") else "No"))
    box.label(
        text="Known clearance violation: "
        + ("Yes" if report.get("known_clearance_violation") else "No")
    )
    box.label(
        text="Threshold contact: " + ("Yes" if report.get("has_threshold_contacts") else "No")
    )
    if response.get("action") == "assembly_sample":
        box.label(text=f"Only {len(report.get('poses', []))} listed discrete poses checked.")
        box.label(text="No continuous collision guarantee.", icon="ERROR")
        for index, sample in enumerate(report.get("poses", [])):
            box.label(text=f"Sample {index + 1}: {sample.get('status', 'see report')}")
    box.operator("mcad.assembly_report", text="Inspect Poses and Pair Measurements", icon="INFO")
    box.label(text="No structural/load or manufacturing certification.")


CLASSES = (
    MCAD_OT_assembly_select_preset,
    MCAD_OT_assembly_preset,
    MCAD_OT_assembly_standard_check_setup,
    MCAD_OT_assembly_check,
    MCAD_OT_assembly_sample,
    MCAD_OT_assembly_report,
)
