"""One local-fields dialog creates a complete pair through the assembly owner."""

import json
import textwrap

from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import assembly_pending, gear_pair, history_rebuild
from .assembly_job_ui import AssemblyJobMixin
from .assembly_operator_helpers import (
    AssemblyEdit,
    activate_assembly_workspace,
    number,
    reject,
    state,
    unit_value,
)


class MCAD_OT_gear_pair(AssemblyJobMixin, AssemblyEdit, Operator):
    bl_idname = "mcad.gear_pair"
    bl_label = "New Printable Gear Pair"
    bl_description = (
        "Configure two editable external spur gears with automatic shafts and gear ratio"
    )
    bl_options = {"REGISTER", "UNDO"}

    edit_existing: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})

    name: StringProperty(name="Assembly name", default="Printable spur gear pair")
    module: StringProperty(
        name="Module (mm)",
        default="2",
        description="Gear module in millimetres: larger values make larger teeth and increase shaft spacing",
    )
    teeth_a: IntProperty(name="Driver A teeth", default=20, min=3, max=200)
    teeth_b: IntProperty(name="Driven B teeth", default=40, min=3, max=200)
    pressure_angle: StringProperty(
        name="Pressure (deg)", default="20", description="Pressure angle in degrees"
    )
    thickness: StringProperty(
        name="Thickness (mm)",
        default="8",
        description="Shared gear thickness along the shaft axes, in millimetres",
    )
    bore_a: StringProperty(
        name="A bore (mm)", default="5", description="Driver A bore diameter in millimetres"
    )
    bore_b: StringProperty(
        name="B bore (mm)", default="5", description="Driven B bore diameter in millimetres"
    )
    pair_backlash: StringProperty(
        name="Backlash (mm)",
        default="0.2",
        description=(
            "Total pair circular backlash in millimetres at the pitch circle; "
            "half is removed from each gear's tooth thickness"
        ),
    )
    clearance: StringProperty(
        name="Root (× module)",
        default="0.25",
        description=(
            "Root clearance: extra root depth as a dimensionless multiple of module, "
            "not millimetres, shaft spacing or bore tolerance"
        ),
    )
    profile_tolerance: StringProperty(
        name="Profile tolerance (mm)",
        default="0.01",
        description="Maximum involute approximation tolerance in millimetres; not printer fit allowance",
    )
    show_advanced: BoolProperty(
        name="Advanced tooth profile",
        default=False,
        options={"SKIP_SAVE"},
        description="Show pressure angle, root clearance and profile accuracy without changing their values",
    )
    show_details: BoolProperty(
        name="How it works and printing",
        default=False,
        options={"SKIP_SAVE"},
        description="Explain automatic assembly, backlash, printing and validation limits; keep draft inputs",
    )
    replace_existing: BoolProperty(
        name="Replace current assembly (save it first)",
        default=False,
        description="Explicitly replace the accepted Assembly; the working Part is never changed",
    )

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    _creation_snapshot = None

    def capture_dialog(self, context):
        super().capture_dialog(context)
        self._creation_snapshot = assembly_pending.capture_candidate(context)
        history_rebuild.cancel("Gear configuration superseded the queued display rebuild.")

    def invoke(self, context, event):
        self.replace_existing = False
        try:
            self.capture_dialog(context)
            if self.edit_existing:
                accepted = json.loads(self._expected)
                for key, value in gear_pair.recognize_pair(accepted).items():
                    setattr(self, key, value if key.startswith("teeth_") else str(value))
                self.name = accepted["name"]
            return context.window_manager.invoke_props_dialog(
                self,
                width=520,
                confirm_text="Apply",
                title="Edit Gear Pair" if self.edit_existing else self.bl_label,
            )
        except Exception as exc:
            return reject(self, context, exc)

    def parameters(self):
        return {
            "module": unit_value(self.module, "slider"),
            "teeth_a": self.teeth_a,
            "teeth_b": self.teeth_b,
            "pressure_angle": number(self.pressure_angle),
            "thickness": unit_value(self.thickness, "slider"),
            "bore_a": unit_value(self.bore_a, "slider"),
            "bore_b": unit_value(self.bore_b, "slider"),
            "pair_backlash": unit_value(self.pair_backlash, "slider"),
            "clearance": number(self.clearance),
            "profile_tolerance": unit_value(self.profile_tolerance, "slider"),
        }

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "name")
        # Keep everyday controls first. Disclosure state belongs to this operator,
        # not to the saved model; draw never rewrites a parameter or resets a draft.
        for fields in (
            ("teeth_a", "teeth_b"),
            ("module",),
            ("thickness",),
            ("bore_a",),
            ("bore_b",),
            ("pair_backlash",),
        ):
            row = layout.row(align=True)
            for field in fields:
                row.prop(self, field)
        layout.label(text="Backlash is shared equally; bores have no print-fit allowance.")
        try:
            dims = gear_pair.pair_dimensions(**self.parameters())
            layout.label(
                text=f"Shaft spacing: {dims['center_distance']:g} mm · B/A ratio: {dims['ratio']:g}"
            )
        except (ValueError, RuntimeError) as exc:
            # Validation stays visible even when its input is in a closed section.
            for line in textwrap.wrap(str(exc), width=65):
                layout.label(text=line, icon="ERROR")
        advanced = getattr(self, "show_advanced", False)
        layout.prop(
            self,
            "show_advanced",
            icon="TRIA_DOWN" if advanced else "TRIA_RIGHT",
            emboss=False,
        )
        if advanced:
            for field in ("pressure_angle", "clearance", "profile_tolerance"):
                layout.row().prop(self, field)
        else:
            # Custom saved values remain discoverable, not silently defaulted.
            for line in textwrap.wrap(
                f"Pressure {self.pressure_angle}° · Root {self.clearance} × module · "
                f"Tolerance {self.profile_tolerance} mm",
                width=65,
            ):
                layout.label(text=line)
        layout.label(text="Reference base is NOT FOR PRINT. Export each gear Part.")
        layout.label(text="Interference NOT checked. Use Check Pose after Apply.")
        layout.label(text="Approximate profile; no contact, strength or print-fit guarantee.")
        editing = getattr(self, "edit_existing", False)
        if editing:
            layout.label(text="Updates both gears and mates; keeps driver angle and names.")
        details = getattr(self, "show_details", False)
        layout.prop(
            self,
            "show_details",
            icon="TRIA_DOWN" if details else "TRIA_RIGHT",
            emboss=False,
        )
        if details:
            for message in (
                "Automatic +Z revolute shafts and tooth-to-gap starting phase. "
                "B/A is the signed angular ratio: minus means opposite rotation.",
                "Backlash reduces pitch-circle tooth thickness equally on both gears; "
                "it is not bore allowance or radial clearance. Test your printer's fit.",
                "Apply validates solids and joints asynchronously. Esc or Cancel "
                "stops native work. Run pose checks again after editing.",
            ):
                for line in textwrap.wrap(message, width=65):
                    layout.label(text=line)
        if state(context).document_json and not editing:
            layout.prop(self, "replace_existing")

    def execute(self, context):
        try:
            if self._creation_snapshot is None:
                self.capture_dialog(context)  # EXEC_DEFAULT shares dialog admission.
            self.require_same_working_part(context)
            if (
                state(context).document_json
                and not self.replace_existing
                and not self.edit_existing
            ):
                raise ValueError(
                    "Save the current assembly and explicitly allow replacement first."
                )
            candidate = (
                gear_pair.edit_pair(json.loads(self._expected), name=self.name, **self.parameters())
                if self.edit_existing
                else gear_pair.build_pair(name=self.name, **self.parameters())
            )
            return self.begin_candidate(
                context,
                candidate,
                self._creation_snapshot,
                editing=self.edit_existing,
            )
        except Exception as exc:
            return reject(self, context, exc)

    def _cleanup_ui(self):
        super()._cleanup_ui()
        # Lifecycle cancellation may free these RNA owners immediately after
        # cleanup. The retained process handle is detached by the shared owner.
        self._creation_snapshot = None
        self._workspace = None
        self._manager = None

    def _job_accepted(self, context, response):
        # Native validation and atomic publication have completed. Never switch
        # workspace or clear the old save path while a candidate is pending.
        activate_assembly_workspace(context)

    def _job_failed(self, context, exc):
        try:
            assembly_pending._assert_candidate_inputs(
                context, self._pending._transaction["snapshot"]
            )
        except Exception:
            return  # Never annotate a newer document/window after stale rejection.
        state(context).last_action_error = str(exc)


CLASSES = (MCAD_OT_gear_pair,)


def draw_gear_parts(layout, data):
    """Gear-only opening uses the existing explicit working-Part confirmation."""
    sources = {source["source_document_id"]: source["document"] for source in data["part_sources"]}
    gears = []
    for part in data["parts"]:
        document = sources.get(part["source_document_id"], {})
        if any(
            feature["id"] == part["output_feature_id"] and feature["kind"] == "spur_gear"
            for feature in document.get("features", [])
        ):
            gears.append(part)
    if not gears:
        return
    box = layout.box()
    try:
        gear_pair.recognize_pair(data)
    except ValueError:
        for line in textwrap.wrap(
            "Pair shortcut unavailable: customized or unrecognized. "
            "Edit Parts/mates, or save and create a new pair.",
            width=30,
        ):
            box.label(text=line)
    else:
        box.operator(
            "mcad.gear_pair", text="Edit Gear Pair", icon="PREFERENCES"
        ).edit_existing = True
    box.label(text="Gear Parts · edit / export", icon="INFO")
    for part in gears:
        button = box.operator("mcad.assembly_open_part", text="Open " + part["name"] + " Part")
        button.part_id = part["id"]
    for message in (
        "Open a gear Part for STL/STEP.",
        "Assembly STEP includes the reference base, if present.",
    ):
        for line in textwrap.wrap(message, width=30):
            box.label(text=line)
