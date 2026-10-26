"""Blender RNA storage and sidecar configuration preferences.

Property callbacks live in document_state; persisted scene JSON stays canonical."""

import sys
from textwrap import wrap

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, PropertyGroup

from . import assembly_job_ui, backend_runtime
from .backend_selection import default_timeout_seconds
from .document_state import _parameter_changed, _parameter_mode_changed


def _backend_settings_changed(_preferences, _context):
    # Advance before notifying owners, including A→B→A edits. The shared
    # callback never solves or waits for a native process from an RNA update.
    backend_runtime.revoke("Backend settings changed; run a fresh CAD operation to verify.")


class MCAD_Parameter(PropertyGroup):
    key: StringProperty(
        name="Parameter", description="Stable named dimension referenced by feature history"
    )
    is_expression: BoolProperty(
        name="Formula",
        description="Switch between a saved formula and its resolved numeric value",
        update=_parameter_mode_changed,
    )
    resolved_text: StringProperty(options={"HIDDEN"})
    resolved_expression: StringProperty(options={"HIDDEN"})
    expression: StringProperty(
        name="Formula",
        description="Safe arithmetic using other named parameters; evaluated by the sidecar",
        update=_parameter_changed,
    )
    value: FloatProperty(
        name="Value (mm)",
        description="Authoritative dimension in millimetres; regenerate after editing",
        precision=4,
        update=_parameter_changed,
    )


class MCAD_Feature(PropertyGroup):
    feature_id: StringProperty()
    label: StringProperty()
    kind: StringProperty()
    status: StringProperty(default="pending")
    error: StringProperty()
    sketch_report_json: StringProperty(options={"HIDDEN"})
    sketch_report_status: StringProperty(default="UNVERIFIED")
    sketch_document_json: StringProperty(options={"HIDDEN"})


class MCAD_State(PropertyGroup):
    owner_id: StringProperty(options={"HIDDEN"})
    last_good_mesh: PointerProperty(type=bpy.types.Mesh, options={"HIDDEN"})
    last_good_origin: FloatVectorProperty(size=3, options={"HIDDEN"})
    last_good_document_id: StringProperty(options={"HIDDEN"})
    last_good_feature_id: StringProperty(options={"HIDDEN"})
    last_good_label: StringProperty(options={"HIDDEN"})
    document_json: StringProperty(options={"HIDDEN"})
    document_path: StringProperty(name="Document", subtype="FILE_PATH")
    document_name: StringProperty(name="Name")
    parameters: CollectionProperty(type=MCAD_Parameter)
    features: CollectionProperty(type=MCAD_Feature)
    feature_index: IntProperty(default=0, min=0)
    active_feature: StringProperty()
    status: StringProperty(default="EMPTY")
    error: StringProperty()
    last_action_error: StringProperty()
    sketch_notice: StringProperty(name="Sketch notice")
    sketch_draft_json: StringProperty(
        name="Saved UI sketch draft",
        options={"HIDDEN"},
        description="Versioned suspended UI state, separate from the canonical CAD feature graph",
    )
    repair_intent_json: StringProperty(
        name="Saved unapplied repair intent",
        options={"HIDDEN"},
        description="Versioned proposal intent only; explicit Resume freshly validates, never restores native evidence",
    )
    sketch_draft_scene_id: StringProperty(options={"HIDDEN"})
    sketch_annotation_json: StringProperty(
        name="Saved sketch annotation layout",
        options={"HIDDEN"},
        description="Versioned viewport annotation placements; not CAD geometry or constraints",
    )
    volume: FloatProperty(name="Volume (mm³)", precision=3)
    show_sketch_details: BoolProperty(
        name="Sketch details", default=False, options={"SKIP_SAVE"},
        description="Show solver evidence, profile diagnostics and sketch guidance",
    )
    show_reference_measurements: BoolProperty(
        name="Reference measurements", default=False, options={"SKIP_SAVE"},
        description="Show the read-only measurement report; viewport labels remain visible",
    )
    show_part_details: BoolProperty(
        name="Part details", default=False, options={"SKIP_SAVE"},
        description="Show detailed Part limitations and verification evidence",
    )
    geometry_status: StringProperty(default="UNCHECKED")
    geometry_message: StringProperty()
    geometry_report_json: StringProperty(options={"HIDDEN"})
    geometry_document_json: StringProperty(options={"HIDDEN"})


class MCAD_Preferences(AddonPreferences):
    bl_idname = __package__
    local_recovery_enabled: BoolProperty(
        name="Enable local recovery (unencrypted)", default=False,
        description="Linux/POSIX only; unavailable on Windows. Explicit opt-in: store unencrypted Part/sketch snapshots on this computer; two generations per scope, 128 MiB total; off retains snapshots",
    )
    show_recovery_details: BoolProperty(
        name="Storage and coverage details", default=False, options={"SKIP_SAVE"},
        description="Show local recovery retention, capture limits, exclusions and storage folder",
    )
    project_root: StringProperty(
        name="Project Root",
        description="Repository containing src/mechanical_cad; defaults to MCAD_ROOT or this add-on's checkout",
        subtype="DIR_PATH",
        update=_backend_settings_changed,
    )
    python_executable: StringProperty(
        name="Python Executable",
        description="Legacy Linux development backend only; standalone extensions choose their bundled interpreter automatically",
        subtype="FILE_PATH",
        update=_backend_settings_changed,
    )
    timeout_seconds: FloatProperty(
        name="Replay timeout (seconds)",
        default=default_timeout_seconds(
            bundled_platform="windows-x64"
            if sys.platform == "win32" and __package__.startswith("bl_ext.")
            else None
        ),
        min=1,
        max=300,
        update=_backend_settings_changed,
    )
    linear_deflection: FloatProperty(
        name="Mesh tolerance (mm)",
        default=0.1,
        min=0.005,
        max=10.0,
        precision=3,
        update=_backend_settings_changed,
    )

    def draw(self, context):
        layout = self.layout
        blocked = assembly_job_ui.draw_backend_failure(layout, context)
        if backend_runtime.bundled_mode():
            state, message = backend_runtime.bundle_status()
            layout.label(text="Automatic offline backend", icon="PACKAGE")
            if blocked and state == "ready":
                message = "Bundled files prepared; native operations are blocked."
            for line in wrap(message, width=72):
                layout.label(
                    text=line, icon="CHECKMARK" if state == "ready" and not blocked else "INFO"
                )
        else:
            layout.prop(self, "project_root")
            layout.prop(self, "python_executable")
            layout.label(text="Legacy development setup (Linux only)", icon="INFO")
        layout.prop(self, "timeout_seconds")
        layout.prop(self, "linear_deflection")
        layout.label(text="OpenCascade runs in external Python, never inside Blender.", icon="INFO")
        from . import local_recovery

        recovery = layout.box()
        recovery.label(text="Optional local recovery (not a crash fix)")
        local_recovery.draw_configuration(recovery, context)
        credits = layout.box()
        credits.label(text="Copyright (c) 2026 Mechanical CAD contributors. GPL-3.0-or-later.")
        for line in wrap(
            "This software contains paintlib code. paintlib is copyright (c) 1996-2002 "
            "Ulrich von Zadow and other contributors.",
            width=72,
        ):
            credits.label(text=line)
        credits.label(text="Uses FreeImage and Open CASCADE Technology (LGPL-2.1 + exception).")
        credits.label(text="OCCT: copyright OPEN CASCADE SAS and contributors; see licenses/occt/.")
        credits.label(text="LibRaw: Copyright (C) 2008-2018 LibRaw LLC; LGPL-2.1, see licenses/.")
        credits.label(text="Licenses and source access: MATERIALS.md in the ZIP.")
