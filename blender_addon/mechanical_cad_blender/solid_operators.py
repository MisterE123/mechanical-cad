"""Connected exact-solid tools and editable history, using the existing replay seam."""

import json

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator, PropertyGroup, UIList

from . import document_state, execution_lease, extrusion_preview, mirror_plane_ui
from .blend_selection import validate_edge_pairs
from .common import _state
from .document_state import _append_feature, _commit_candidate, _new_feature, _read_document
from .extrusion_end_condition import (
    OFFSET_DESCRIPTION,
    UP_TO_FACE_ITEM,
    _end_face_choices,
    _source_choices,
    draw_up_to_face,
    end_condition,
    set_up_to_face,
)
from .feature_guidance import feature_error
from .help_ui import _draw_feature_help, _feature_help_next, _feature_help_previous
from .linked_extrusion_edit import (
    SharedToolConsentRequired,
    edit_linked_extrusion,
    linked_extrusion,
)
from .loft_sections import set_sections
from .operators import _reject_candidate, _report_result
from .parameter_depth_edit import (
    affected_uses,
    depth_parameter,
    edit_shared_depth,
    edit_shared_linked_depth,
    parameter_definition_hint,
    pending_tool_consent,
)
from .parameter_radius_edit import edit_shared_radius, radius_parameter
from .shell_selection import opening_ids
from .solid_dialog_values import (
    circle_expression_resume_values,
    consent_resume_values,
    picked_blend_faces,
    picked_shell_face,
    selected_history_id,
    solid_dialog_defaults,
    validate_circle_expression_resume,
    validate_consent_resume,
)
from .solid_feature_edit import (
    FEATURE_FIELDS,
    FEATURE_INPUTS,
    SOLID_KINDS,
    edit_feature,
    set_sweep_placement,
)
from .topology_labels import face_label
from .unit_input import ANGLE_INPUT_HELP, LENGTH_INPUT_HELP, feature_dimension, normalize_unit_input

_CHOICES = {}


def _choices(self, context, profile=False):
    try:
        document = _read_document(_state(context))
        values = [
            (f["id"], f"{f['label']} [{f['id']}]", f["id"])
            for f in document["features"]
            if (f["kind"].startswith("sketch_") if profile else f["kind"] in SOLID_KINDS)
        ]
    except Exception:
        values = []
    key = ("profile" if profile else "solid", tuple(values))
    _CHOICES[key] = values or [("NONE", "No suitable feature", "")]
    return _CHOICES[key]


def _solid_choices(self, context):
    return _choices(self, context)


def _profile_choices(self, context):
    return _choices(self, context, True)


def _face_choices(self, context):
    result = document_state.current_part_result(context)
    source_id = self.support if self.kind.startswith("sketch_face_") else self.base
    values = []
    if result:
        for feature in result.get("features", []):
            if feature["id"] == source_id:
                values = [
                    (face["id"], face_label(face), face["id"])
                    for face in feature.get("topology", [])
                    if face.get("provenance", {}).get("semantic_status") == "stable"
                    and (
                        not (self.kind.startswith("sketch_face_") or self.kind == "shell")
                        or face.get("signature", {}).get("surface") == "plane"
                    )
                ]
                break
    key = ("faces", source_id, tuple(values))
    _CHOICES[key] = values or [("NONE", "No stable faces; rebuild or select another base", "")]
    return _CHOICES[key]


def _set_blend_selection(feature, operator):
    feature.pop("edge_faces", None)
    feature.pop("edge_pairs", None)
    if operator.edge_mode == "PAIR":
        if operator.face_a == "NONE" or operator.face_b == "NONE":
            raise ValueError("Rebuild and select two stable faces before applying")
        feature["edge_faces"] = [operator.face_a, operator.face_b]
    elif operator.edge_mode == "MULTI":
        feature["edge_pairs"] = validate_edge_pairs(json.loads(operator.edge_pairs_json))


class MCAD_PG_loft_section(PropertyGroup):
    profile: EnumProperty(name="Section profile", items=_profile_choices)


class MCAD_UL_loft_sections(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=str(index + 1))
        layout.prop(item, "profile", text="")


def _initialize_loft(operator, profiles):
    operator.loft_section_rows.clear()
    for profile in profiles:
        operator.loft_section_rows.add().profile = profile
    operator.loft_section_index = 0


def _loft_mode(self, context):
    # EXEC callers may supply a complete RNA collection after the mode property.
    # Seed only an already-invoked dialog, never append hidden default rows to it.
    if (
        self.loft_mode == "ORDERED"
        and not self.loft_section_rows
        and getattr(getattr(self, "options", None), "is_invoke", False)
    ):
        _initialize_loft(self, [self.start, self.end])


def _loft_action(self, context):
    action = self.loft_action
    if action == "NONE":
        return
    rows = self.loft_section_rows
    index = min(max(self.loft_section_index, 0), max(0, len(rows) - 1))
    if action == "ADD" and len(rows) < 16:
        used = {row.profile for row in rows}
        available = [p for p, _, _ in _profile_choices(self, context) if p not in used]
        if available:
            rows.add().profile = available[0]
            self.loft_section_index = len(rows) - 1
    elif action == "REMOVE" and len(rows) > 2:
        rows.remove(index)
        self.loft_section_index = min(index, len(rows) - 1)
    elif action in {"UP", "DOWN"}:
        target = index + (-1 if action == "UP" else 1)
        if 0 <= target < len(rows):
            rows.move(index, target)
            self.loft_section_index = target
    self.loft_action = "NONE"


def _set_loft(feature, operator):
    if operator.loft_mode == "ORDERED":
        set_sections(feature, [row.profile for row in operator.loft_section_rows])
    else:
        feature.pop("loft_sections", None)
        feature["inputs"] = {"start": operator.start, "end": operator.end}


class MCAD_PG_shell_opening(PropertyGroup):
    face_id: StringProperty()
    label: StringProperty()
    selected: BoolProperty(name="Remove face")
    available: BoolProperty()


class MCAD_UL_shell_openings(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "selected", text=item.label, icon="NONE" if item.available else "ERROR")


def _shell_values(operator):
    if getattr(operator, "shell_choices_ready", False):
        encoded = json.dumps([row.face_id for row in operator.shell_openings if row.selected])
    else:
        encoded = getattr(operator, "opening_faces_json", "")
    return opening_ids(encoded, getattr(operator, "opening_face", ""))


def _shell_choices(operator, context):
    if operator.kind != "shell" or not hasattr(operator, "shell_openings"):
        return
    if operator.shell_choices_ready and operator.shell_choices_base == operator.base:
        return
    if operator.shell_choices_ready:
        selected = [row.face_id for row in operator.shell_openings if row.selected]
    elif operator.opening_faces_json:
        selected = opening_ids(operator.opening_faces_json)
    elif operator.properties.is_property_set("opening_face"):
        selected = [operator.opening_face]
    else:
        selected = []
    choices = [
        (identifier, label)
        for identifier, label, _ in _face_choices(operator, context)
        if identifier != "NONE"
    ]
    available = {identifier for identifier, _ in choices}
    labels = dict(choices)
    # Keep saved explicit order on an untouched edit, not topology enumeration order.
    choices = [
        (identifier, labels.get(identifier, "Unavailable opening: " + identifier))
        for identifier in selected
    ] + [(identifier, label) for identifier, label in choices if identifier not in selected]
    operator.shell_openings.clear()
    for identifier, label in choices:
        row = operator.shell_openings.add()
        row.face_id, row.label = identifier, label
        row.selected, row.available = identifier in selected, identifier in available
    operator.shell_choices_base = operator.base
    operator.shell_choices_ready = True


def _solid_check(operator, context):
    _shell_choices(operator, context)
    return extrusion_preview.changed(operator, context)


_FIELD_LABELS = {
    "ruled": "Straight sides (0 = smooth, 1 = straight)",
    "count": "Number of instances",
    "thickness": "Wall thickness (mm)",
    "width": "Width (mm)",
    "height": "Height (mm)",
    "length": "Signed depth (mm)",
    "radius": "Radius (mm)",
    "distance": "Chamfer distance (mm)",
    "angle": "Angle (degrees)",
}


def _draw_dimensions(layout, operator):
    """Group Cartesian components without replacing any expression widgets."""
    if operator.kind == "mirror":
        mirror_plane_ui.draw(layout, operator)
        return
    fields = FEATURE_FIELDS.get(operator.kind, ())
    grouped = {"axis_x", "axis_y", "axis_z", "x", "y", "z", "rx", "ry", "rz", "dx", "dy", "dz"}
    for name in fields:
        if name not in grouped:
            label = _FIELD_LABELS.get(name, name.replace("_", " ").title())
            if name == "length" and (
                operator.kind == "extrude_symmetric"
                or getattr(operator, "extrude_end_condition", "") == "SYMMETRIC"
            ):
                label = "Total depth (mm)"
            if name == "angle" and operator.kind in {"circular_pattern", "circular_cut_pattern"}:
                label = "Total pattern angle (degrees)"
            parameter = getattr(operator, "radius_parameter_name", "") if name == "radius" else ""
            if parameter:
                layout.prop(operator, "radius_edit_scope", expand=True)
            if parameter and operator.radius_edit_scope == "PARAMETER":
                box = layout.box()
                box.label(text="Shared parameter: " + parameter, icon="LINKED")
                box.prop(operator, "radius_parameter_value", text="Radius (mm)")
                box.label(text="Updates these uses; keeps the radius linked:")
                for usage in affected_uses(json.loads(operator.original_json), parameter):
                    box.label(text=usage)
            else:
                layout.prop(operator, name, text=label)
                if parameter:
                    layout.label(text=parameter_definition_hint(
                        json.loads(operator.original_json), parameter,
                    ))
                    layout.label(text="Replacing " + parameter + " unlinks only this radius.")
    groups = [
        (
            ("axis_x", "axis_y", "axis_z"),
            "Plane normal (world coordinates)"
            if operator.kind == "mirror"
            else "Axis direction (world coordinates)",
        ),
        (
            ("x", "y", "z"),
            (
                "Move by (mm)"
                if operator.kind == "transform"
                else "Plane origin (mm)"
                if operator.kind == "mirror"
                else "Axis position (mm)"
                if "axis_x" in fields
                else "Position on face (mm)"
                if operator.kind.startswith("sketch_face_")
                else "Position (mm)"
            ),
        ),
        (("rx", "ry", "rz"), "Rotate (degrees)"),
        (("dx", "dy", "dz"), "Spacing between instances (mm)"),
    ]
    for names, title in groups:
        if all(name in fields for name in names):
            box = layout.box()
            box.label(text=title)
            row = box.row(align=True)
            for name, axis in zip(names, "XYZ", strict=True):
                row.prop(operator, name, text=axis)


class _SolidDialog:
    @property
    def help_topic(self):
        return "feature." + self.kind

    @property
    def help_summary(self):
        return (
            "Open help for inputs, direction and feature limits.",
            "Apply preserves the old model if exact rebuilding fails.",
        )

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and bool(_state(context).document_json)
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
        )

    def draw(self, context):
        layout = self.layout
        if not getattr(self, "feature_id", ""):
            layout.prop(self, "kind")
        if getattr(self, "consent_retry", False):
            layout.label(text="Draft restored; review shared-tool permission before Apply.", icon="INFO")
        if getattr(self, "expression_retry", False):
            layout.label(text="Draft restored; correct the expression before Apply.", icon="INFO")
        layout.prop(self, "feature_label")
        if self.kind.startswith("sketch_face_"):
            layout.prop(self, "support_face")
            layout.label(text="Associative face frame: centroid origin, outward normal.")
            layout.label(text="X and Y lie on the face; Z offsets along its outward normal.")
        for name in FEATURE_INPUTS.get(self.kind, ()):
            if name != "target" and not (self.kind == "loft" and self.loft_mode == "ORDERED"):
                layout.prop(self, name)
        if getattr(self, "linked_tool_id", ""):
            box = layout.box()
            box.label(text="Extrusion: " + self.linked_tool_label)
            if self.tool != self.linked_tool_id:
                box.label(
                    text="Apply the new tool, then reopen to edit its extrusion.", icon="INFO"
                )
            else:
                if self.linked_consumers:
                    box.label(text="Shared tool also affects:", icon="ERROR")
                    for consumer in self.linked_consumers.split("\n"):
                        box.label(text=consumer)
                    box.prop(self, "allow_shared_extrusion")
                    if not self.allow_shared_extrusion:
                        shared_mode = (
                            self.linked_depth_scope == "PARAMETER"
                            and self.linked_end_condition in {"BLIND", "SYMMETRIC"}
                        )
                        if pending_tool_consent(
                            json.loads(self.original_json), self.feature_id,
                            tool_id=self.linked_tool_id,
                            length=self.depth_parameter_name if shared_mode else self.linked_length,
                            profile=self.linked_profile,
                            end_condition=self.linked_end_condition,
                            direction=self.linked_direction,
                            **({"target": self.target, "end_face": self.end_face, "offset": self.offset}
                               if self.linked_end_condition == "UP_TO_FACE" else {}),
                            parameter_name=self.depth_parameter_name if shared_mode else "",
                            parameter_value=self.depth_parameter_value,
                        ):
                            warning = box.column(align=True)
                            warning.alert = True
                            warning.label(text="Pending depth edits need shared-tool permission.", icon="ERROR")
                            warning.label(text="Enable the checkbox above, or Cancel to keep the model.")
                fields = box.column()
                fields.enabled = not self.linked_consumers or self.allow_shared_extrusion
                fields.prop(self, "linked_profile", text="Extrusion profile")
                fields.prop(self, "linked_end_condition", text="End condition")
                if self.linked_end_condition == "UP_TO_FACE":
                    draw_up_to_face(fields, self, direction="linked_direction")
                elif self.linked_end_condition == "THROUGH_ALL":
                    fields.prop(self, "linked_direction", text="Direction")
                    box.label(text="Through All follows the selected target on every rebuild.")
                else:
                    parameter = getattr(self, "depth_parameter_name", "")
                    if parameter:
                        fields.row().prop(self, "linked_depth_scope", expand=True)
                    if parameter and self.linked_depth_scope == "PARAMETER":
                        shared = fields.box()
                        shared.label(text="Shared parameter: " + parameter, icon="LINKED")
                        shared.prop(self, "depth_parameter_value", text="Value or formula (mm)")
                        shared.label(text="Updates these uses; keeps the tool depth linked:")
                        for usage in affected_uses(json.loads(self.original_json), parameter):
                            shared.label(text=usage)
                    else:
                        fields.prop(
                            self,
                            "linked_length",
                            text="Total depth (mm)"
                            if self.linked_end_condition == "SYMMETRIC"
                            else "Signed depth (mm)",
                        )
                        if parameter:
                            fields.label(text=parameter_definition_hint(
                                json.loads(self.original_json), parameter,
                            ))
                        box.label(text="Changes this tool's formula, not project parameters.")
                    if self.linked_end_condition == "SYMMETRIC":
                        box.label(text="Half of the positive total depth on each side.")
        if self.kind in {"extrude", "extrude_symmetric", "extrude_to_face"}:
            layout.prop(self, "extrude_end_condition", text="End condition")
            if self.extrude_end_condition == "UP_TO_FACE":
                draw_up_to_face(layout, self)
            else:
                parameter = getattr(self, "depth_parameter_name", "")
                if parameter:
                    layout.prop(self, "depth_edit_scope", expand=True)
                if parameter and self.depth_edit_scope == "PARAMETER":
                    box = layout.box()
                    box.label(text="Shared parameter: " + parameter, icon="LINKED")
                    box.prop(self, "depth_parameter_value", text="Value or formula (mm)")
                    box.label(text="Updates these uses; keeps the depth linked:")
                    for usage in affected_uses(json.loads(self.original_json), parameter):
                        box.label(text=usage)
                else:
                    layout.prop(
                        self,
                        "length",
                        text=(
                            "Total depth (mm)"
                            if self.extrude_end_condition == "SYMMETRIC"
                            else "Signed depth (mm)"
                        ),
                    )
                    if parameter:
                        layout.label(text=parameter_definition_hint(
                            json.loads(self.original_json), parameter,
                        ))
                        layout.label(text="Replacing " + parameter + " unlinks only this depth.")
                if self.extrude_end_condition == "SYMMETRIC":
                    layout.label(text="Half of the positive total depth on each side.")
        if self.kind == "extrude_through":
            layout.label(text="End condition: Through All")
            layout.label(text="Reaches through the target on every rebuild.")
        if self.kind not in {"extrude", "extrude_symmetric", "extrude_to_face"}:
            _draw_dimensions(layout, self)
        if self.kind in {"fillet", "chamfer"}:
            layout.prop(self, "edge_mode")
            if self.edge_mode == "MULTI":
                try:
                    count = len(validate_edge_pairs(json.loads(self.edge_pairs_json)))
                    layout.label(text=f"{count} explicitly selected edges")
                except (ValueError, TypeError):
                    layout.label(text="Choose edges in the viewport first", icon="ERROR")
                layout.label(text="Edit Feature → Reselect replaces the complete edge set.")
                layout.label(
                    text="Unique blend surfaces follow their saved face pairs; ambiguous ones stay unnamed."
                )
            elif self.edge_mode == "PAIR":
                layout.prop(self, "face_a")
                layout.prop(self, "face_b")
                layout.label(
                    text=(
                        "Viewport edge selection; native unique-edge check on Apply."
                        if getattr(self, "picked_base", "")
                        else "Faces must share exactly one edge; missing lineage fails safely."
                    )
                )
            else:
                layout.label(
                    text="Selection: ALL edges, reapplied after upstream edits.", icon="INFO"
                )
            layout.label(text="Impossible blends fail; no partial result is accepted.")
            extrusion_preview.draw(self)
        if self.kind == "revolve":
            layout.label(text="Axis origin and direction are world-space; angle is degrees.")
        if self.kind == "mirror":
            layout.label(text="Result: reflected solid only. Original stays in history.")
            layout.label(text="No automatic fusion or second body.")
            extrusion_preview.draw(self)
        if self.kind == "transform":
            layout.label(text="Rotate world X, Y, Z, then translate in millimetres.")
        if self.kind in {"linear_pattern", "circular_pattern"}:
            layout.label(text="Copies include the original and must join into one solid.")
        if self.kind in {"linear_cut_pattern", "circular_cut_pattern"}:
            layout.label(text="Cut repeated tools; count includes original placement.")
            layout.label(text="Separated tools are allowed; the base must remain one solid.")
        if self.kind == "shell":
            layout.prop(self, "shell_mode")
            if self.shell_mode == "OPEN":
                box = layout.box()
                box.label(text="Opening faces (check every face to remove)")
                box.template_list(
                    "MCAD_UL_shell_openings",
                    "",
                    self,
                    "shell_openings",
                    self,
                    "shell_opening_index",
                    rows=6,
                    maxrows=8,
                )
                count = sum(row.selected for row in self.shell_openings)
                box.label(text=f"{count} selected · 1–64 stable planar faces")
                layout.label(text="Thickness offsets inward; unchecked faces remain.")
            else:
                layout.label(text="Closed cavity: all outside walls remain.")
        if self.kind == "loft":
            layout.prop(self, "loft_mode", expand=True)
            if self.loft_mode == "ORDERED":
                layout.template_list(
                    "MCAD_UL_loft_sections",
                    "",
                    self,
                    "loft_section_rows",
                    self,
                    "loft_section_index",
                    rows=5,
                    maxrows=8,
                )
                row = layout.row(align=True)
                for value, label in (
                    ("ADD", "Add"),
                    ("REMOVE", "Remove"),
                    ("UP", "Move up"),
                    ("DOWN", "Move down"),
                ):
                    row.prop_enum(self, "loft_action", value, text=label)
                layout.label(
                    text=f"{len(self.loft_section_rows)} sections · 2–16 distinct profiles"
                )
                layout.label(text="Traversed top to bottom, never sorted by position.")
            layout.label(text="One closed outer outline per section, without holes.")
            layout.label(text="Ruled 0: smooth interpolation through sections.")
            layout.label(text="Ruled 1: straight spans between consecutive sections.")
            layout.label(text="No guides, seam control or stable generated face identity.")
        if self.kind == "sweep":
            extrusion_preview.draw(self)
            layout.prop(self, "sweep_placement_mode")
            if self.sweep_placement_mode == "AUTO":
                layout.label(
                    text="Moves filled-area centroid to path start; normal follows tangent."
                )
                layout.label(text="Not sketch origin or box center; source sketch stays unchanged.")
                layout.label(text="Zero roll: section +U follows the path-plane normal.")
                layout.label(text="Start: smallest endpoint ID (after explicit coincidence).")
                layout.prop(self, "sweep_reverse")
                layout.prop(self, "sweep_roll")
                layout.label(text="Positive roll turns +U toward +V about the travel tangent.")
                layout.label(
                    text="Construction assumption only; no stable face identity is inferred."
                )
            else:
                layout.label(text="Uses the original section position and orientation unchanged.")
                layout.label(text="Place section at path start, normal to its first tangent.")
            layout.label(text="Path: solved connected open lines/arcs; no branches or crossings.")
        if self.kind != "sweep":
            layout.label(
                text="Lengths: mm/cm/m/in/ft. Angles: deg/rad. Formulas keep existing units."
            )
        if getattr(self, "feature_id", "") and not (
            getattr(self, "depth_parameter_name", "") or getattr(self, "radius_parameter_name", "")
        ):
            layout.label(text="Replacing a parameter name changes this feature's link only.")
        if getattr(self, "feature_id", "") and self.kind in {"fillet", "chamfer", "shell"}:
            layout.prop(self, "edit_action", expand=True)
            if self.edit_action == "RESELECT":
                layout.label(text="Continue shows the exact INPUT body, not the finished feature.")
                layout.label(
                    text="Pick, then review all fields before Apply. Esc keeps the old selection."
                )
        _draw_feature_help(self, context)


_FIELDS = {
    "mirror_initializing": BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"}),
    "mirror_plane": EnumProperty(
        name="Mirror plane",
        default="CUSTOM",
        update=mirror_plane_ui.changed,
        items=[
            ("XY", "XY plane", "Reflect across XY with a signed Z offset"),
            ("XZ", "XZ plane", "Reflect across XZ with a signed Y offset"),
            ("YZ", "YZ plane", "Reflect across YZ with a signed X offset"),
            ("CUSTOM", "Custom plane", "Preserve or enter any nonzero normal and plane origin"),
        ],
        options={"SKIP_SAVE"},
    ),
    "show_help": BoolProperty(default=False, options={"SKIP_SAVE"}),
    "help_page": IntProperty(default=1, min=1, options={"SKIP_SAVE"}),
    "help_previous": BoolProperty(
        default=False, update=_feature_help_previous, options={"SKIP_SAVE"}
    ),
    "help_next": BoolProperty(default=False, update=_feature_help_next, options={"SKIP_SAVE"}),
    "edge_mode": EnumProperty(
        name="Edges",
        items=[
            ("ALL", "All edges", "Reapply all-edge intent"),
            ("MULTI", "Selected edge set", "Explicit stable face pairs picked with Shift-click"),
            (
                "PAIR",
                "One edge between named faces",
                "Persist two unambiguous semantic face identities",
            ),
        ],
    ),
    "edge_pairs_json": StringProperty(options={"HIDDEN", "SKIP_SAVE"}),
    "sweep_placement_mode": EnumProperty(
        name="Section placement",
        default="AUTO",
        items=[
            (
                "AUTO",
                "Center at path start",
                "Explicit automatic placement by filled-area centroid and path tangent",
            ),
            ("AUTHORED", "Keep authored placement", "Do not move or rotate the original section"),
        ],
    ),
    "sweep_reverse": BoolProperty(
        name="Start at other end (reverse path traversal)",
        default=False,
        description="Traverse from the other endpoint, not just flip the section normal",
    ),
    "sweep_roll": StringProperty(
        name="Section roll (°)",
        description="Literal angle in degrees, or with deg/rad; -360 to 360 degrees; no formulas",
        default="0",
    ),
    "loft_mode": EnumProperty(
        name="Sections",
        default="LEGACY",
        update=_loft_mode,
        items=[
            ("LEGACY", "Two sections", "Keep legacy start/end inputs"),
            ("ORDERED", "Ordered section list", "Explicitly order 2–16 profiles"),
        ],
    ),
    "loft_section_rows": CollectionProperty(type=MCAD_PG_loft_section, options={"SKIP_SAVE"}),
    "loft_section_index": IntProperty(default=0, options={"SKIP_SAVE"}),
    "loft_action": EnumProperty(
        update=_loft_action,
        options={"SKIP_SAVE"},
        items=[
            ("NONE", "", ""),
            ("ADD", "Add", "Append an unused profile; create more sketches first"),
            ("REMOVE", "Remove", "Remove selected row, keeping at least two"),
            ("UP", "Move up", "Move selected section earlier"),
            ("DOWN", "Move down", "Move selected section later"),
        ],
    ),
    "shell_mode": EnumProperty(
        name="Shell mode",
        items=[
            ("CLOSED", "Closed cavity", "Retain all outer faces"),
            ("OPEN", "Open enclosure", "Remove selected stable planar faces"),
        ],
    ),
    "opening_faces_json": StringProperty(options={"HIDDEN", "SKIP_SAVE"}),
    "shell_openings": CollectionProperty(type=MCAD_PG_shell_opening, options={"SKIP_SAVE"}),
    "shell_opening_index": IntProperty(default=0, options={"HIDDEN", "SKIP_SAVE"}),
    "shell_choices_ready": BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"}),
    "shell_choices_base": StringProperty(options={"HIDDEN", "SKIP_SAVE"}),
    "opening_face": EnumProperty(name="Opening face", items=_face_choices),
    "face_a": EnumProperty(name="First face", items=_face_choices),
    "face_b": EnumProperty(name="Second face", items=_face_choices),
    "feature_label": StringProperty(name="Feature name", default="Solid feature"),
    "base": EnumProperty(name="Base solid", items=_solid_choices),
    "target": EnumProperty(name="Earlier target solid", items=_source_choices),
    "end_face": EnumProperty(name="End face", items=_end_face_choices),
    "offset": StringProperty(name="Offset (mm)", description=OFFSET_DESCRIPTION, default="0"),
    "support": EnumProperty(name="Supporting solid", items=_solid_choices),
    "support_face": EnumProperty(name="Supporting face", items=_face_choices),
    "tool": EnumProperty(name="Tool solid", items=_solid_choices),
    "profile": EnumProperty(name="Profile", items=_profile_choices),
    "direction": EnumProperty(
        name="Direction",
        items=[
            ("1", "Along sketch normal", "Remove forward from the sketch plane"),
            ("-1", "Opposite sketch normal", "Remove backward from the sketch plane"),
        ],
    ),
    "start": EnumProperty(name="Start profile", items=_profile_choices),
    "end": EnumProperty(name="End profile", items=_profile_choices),
    "path": EnumProperty(name="Solved line/arc path", items=_profile_choices),
}
for _name, _default in dict(
    ruled="0",
    count="3",
    dx="10",
    dy="0",
    dz="0",
    thickness="1",
    width="40",
    height="30",
    length="10",
    radius="1",
    distance="1",
    angle="360",
    axis_x="0",
    axis_y="1",
    axis_z="0",
    x="0",
    y="0",
    z="0",
    rx="0",
    ry="0",
    rz="0",
).items():
    _FIELDS[_name] = StringProperty(
        name=_name.replace("_", " ").title(),
        default=_default,
        description=(
            ANGLE_INPUT_HELP
            if _name in {"angle", "rx", "ry", "rz"}
            else LENGTH_INPUT_HELP
            if feature_dimension("sketch_rectangle", _name) == "length"
            or _name in {"dx", "dy", "dz", "length", "radius", "distance", "thickness"}
            else "Unitless number or existing parameter formula; unit suffixes are not accepted"
        ),
    )


class MCAD_OT_add_solid_feature(_SolidDialog, Operator):
    bl_idname = "mcad.add_solid_feature"
    bl_label = "Solid Feature"
    bl_description = "Add a parametric boolean, revolve, all-edge blend, or rigid transform"
    bl_options = {"REGISTER", "UNDO"}
    kind: EnumProperty(
        name="Operation",
        items=[
            (
                "sketch_face_rectangle",
                "Rectangle on Face",
                "Associative rectangle on a stable planar face",
            ),
            ("sketch_face_circle", "Circle on Face", "Associative circle on a stable planar face"),
            ("union", "Union / Add", "Join two touching or overlapping solids"),
            ("intersection", "Intersection", "Keep material shared by two solids"),
            ("cut", "Cut / Subtract", "Remove the tool from the base"),
            ("revolve", "Revolve", "Sweep a profile around an explicit world axis"),
            ("fillet", "Fillet", "Round all edges or one explicitly selected edge"),
            ("chamfer", "Chamfer", "Bevel all edges or one explicitly selected edge"),
            (
                "mirror",
                "Mirror Result",
                "Reflect one solid across a datum plane; no original copy or fusion",
            ),
            ("transform", "Move / Rotate", "Parametric world-space rigid transform"),
            ("linear_pattern", "Linear Pattern", "Fuse equally spaced copies into one solid"),
            ("circular_pattern", "Circular Pattern", "Fuse rotated copies into one solid"),
            (
                "linear_cut_pattern",
                "Linear Hole Pattern",
                "Cut equally spaced tool copies from a base",
            ),
            (
                "circular_cut_pattern",
                "Circular Hole Pattern",
                "Cut rotated tool copies from a base",
            ),
            ("shell", "Hollow / Shell", "Create an open enclosure or closed cavity"),
            ("loft", "Loft", "Create a solid through 2–16 explicitly ordered closed profiles"),
            ("sweep", "Sweep", "Sweep a section along a solved planar line/arc path"),
        ],
    )

    original_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    picked_opening_faces_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    picked_opening_face: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    picked_base: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    picked_edge_pairs_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    picked_face_a: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    picked_face_b: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    picked_document_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        state = _state(context)
        document = _read_document(state)
        defaults = solid_dialog_defaults(document, selected_history_id(state))
        solids = [f["id"] for f in document["features"] if f["kind"] in SOLID_KINDS]
        profiles = [f["id"] for f in document["features"] if f["kind"].startswith("sketch_")]
        if solids:
            if not self.properties.is_property_set("base"):
                self.base = defaults["base"]
            if not self.properties.is_property_set("support"):
                self.support = self.base
            if not self.properties.is_property_set("tool"):
                self.tool = next((f for f in reversed(solids) if f != self.base), solids[-1])
        if profiles:
            selected = selected_history_id(state)
            start = selected if selected in profiles else profiles[0]
            for name, value in {
                "profile": defaults["profile"],
                "start": start,
                "end": next((p for p in reversed(profiles) if p != start), profiles[-1]),
                "path": profiles[-1],
            }.items():
                if not self.properties.is_property_set(name):
                    setattr(self, name, value)
        if self.kind in {"circular_pattern", "circular_cut_pattern", "mirror"}:
            if not self.properties.is_property_set("axis_y"):
                self.axis_y = "0"
            if not self.properties.is_property_set("axis_z"):
                self.axis_z = "1"
        mirror_plane_ui.initialize(self, document["parameters"])
        if not self.properties.is_property_set("feature_label"):
            self.feature_label = self.kind.replace("_", " ").capitalize()
        if getattr(self, "picked_opening_face", "") or getattr(
            self, "picked_opening_faces_json", ""
        ):
            try:
                if self.kind != "shell" or self.picked_document_json != state.document_json:
                    raise ValueError("Document changed after picking; choose the opening again")
                openings = opening_ids(
                    getattr(self, "picked_opening_faces_json", ""),
                    getattr(self, "picked_opening_face", ""),
                )
                for opening in openings:
                    picked_shell_face(
                        document,
                        document_state.current_part_result(context),
                        self.picked_base,
                        opening,
                    )
                self.base, self.opening_face = self.picked_base, openings[0]
                self.opening_faces_json = json.dumps(openings)
                self.shell_mode = "OPEN"
            except Exception as exc:
                return _reject_candidate(self, context, str(exc))
        elif getattr(self, "picked_edge_pairs_json", ""):
            try:
                if (
                    self.kind not in {"fillet", "chamfer"}
                    or self.picked_document_json != state.document_json
                ):
                    raise ValueError("Document changed after picking; choose the edges again")
                pairs = validate_edge_pairs(json.loads(self.picked_edge_pairs_json))
                for first, second in pairs:
                    picked_blend_faces(
                        document,
                        document_state.current_part_result(context),
                        self.picked_base,
                        first,
                        second,
                    )
                self.base = self.picked_base
                self.edge_mode = "MULTI"
                self.edge_pairs_json = json.dumps(pairs)
            except Exception as exc:
                return _reject_candidate(self, context, str(exc))
        elif any(
            getattr(self, key, "") for key in ("picked_base", "picked_face_a", "picked_face_b")
        ):
            try:
                if self.kind not in {"fillet", "chamfer"}:
                    raise ValueError("Picked edge faces require Fillet or Chamfer")
                if getattr(self, "picked_document_json", "") != state.document_json:
                    raise ValueError("Document changed after picking; choose the edge again")
                base, first, second = picked_blend_faces(
                    document,
                    document_state.current_part_result(context),
                    self.picked_base,
                    self.picked_face_a,
                    self.picked_face_b,
                )
                self.base = base
                self.edge_mode = "PAIR"
                self.face_a, self.face_b = first, second
            except Exception as exc:
                return _reject_candidate(self, context, str(exc))
        self.original_json = state.document_json
        try:
            if self.kind == "loft" and self.loft_mode == "ORDERED" and not self.loft_section_rows:
                _initialize_loft(self, [self.start, self.end])
            _shell_choices(self, context)
            if self.kind in {"fillet", "chamfer", "sweep", "mirror"}:
                extrusion_preview.start(self, context)
            return context.window_manager.invoke_props_dialog(self, width=560, confirm_text="Apply")
        except Exception as exc:
            extrusion_preview.cancel(self, context)
            return _reject_candidate(self, context, str(exc))

    check = _solid_check
    cancel = extrusion_preview.cancel
    modal = extrusion_preview.modal

    def preview_candidate(self, context):
        """Detached creation intent, identical to synchronous Apply before normalization."""
        if self.kind not in {"fillet", "chamfer", "sweep", "mirror"}:
            raise ValueError("Reopen the dialog to preview a different operation")
        state = _state(context)
        if self.original_json and state.document_json != self.original_json:
            raise ValueError("Document changed; reopen the feature dialog")
        document = _read_document(state)
        params = {key: getattr(self, key) for key in FEATURE_FIELDS[self.kind]}
        inputs = {key: getattr(self, key) for key in FEATURE_INPUTS[self.kind]}
        if "NONE" in inputs.values():
            raise ValueError("Create the required profile or solid first")
        feature = _new_feature(context, self.kind, params, inputs, self.feature_label)
        if self.kind == "sweep":
            set_sweep_placement(
                feature, self.sweep_placement_mode, reverse=self.sweep_reverse, roll=self.sweep_roll
            )
        elif self.kind in {"fillet", "chamfer"}:
            _set_blend_selection(feature, self)
        for name, value in list(feature["params"].items()):
            key = f"{feature['id']}_{name}"
            if key in document["parameters"]:
                raise ValueError(f"Parameter {key} already exists")
            document["parameters"][key] = value
            feature["params"][name] = key
        document["features"].append(feature)
        document["active_feature"] = feature["id"]
        return document

    def execute(self, context):
        try:
            pending = extrusion_preview.apply(self, context)
            if pending is not None:
                return pending
            if not self.poll(context):
                raise ValueError("Finish the current operation before adding a solid feature")
            if self.original_json and _state(context).document_json != self.original_json:
                raise ValueError("Document changed; reopen Solid Feature to retain those edits")
            params = {key: getattr(self, key) for key in FEATURE_FIELDS[self.kind]}
            inputs = {key: getattr(self, key) for key in FEATURE_INPUTS[self.kind]}
            if self.kind == "loft" and self.loft_mode == "ORDERED":
                inputs = {
                    f"section_{i + 1}": row.profile for i, row in enumerate(self.loft_section_rows)
                }
            if "NONE" in inputs.values():
                raise ValueError("Create the required profile or solid first")
            feature = _new_feature(context, self.kind, params, inputs, self.feature_label)
            if self.kind == "sweep":
                set_sweep_placement(
                    feature,
                    self.sweep_placement_mode,
                    reverse=self.sweep_reverse,
                    roll=self.sweep_roll,
                )
            if self.kind == "loft":
                _set_loft(feature, self)
            if self.kind == "shell" and self.shell_mode == "OPEN":
                feature["opening_faces"] = _shell_values(self)
            if self.kind.startswith("sketch_face_"):
                feature["support_face"] = self.support_face
            if self.kind in {"fillet", "chamfer"}:
                _set_blend_selection(feature, self)
            return _report_result(self, context, _append_feature(context, feature))
        except Exception as exc:
            extrusion_preview.cancel(self, context)
            return _reject_candidate(self, context, feature_error(self.kind, exc))


class MCAD_OT_edit_solid_feature(_SolidDialog, Operator):
    bl_idname = "mcad.edit_solid_feature"
    bl_label = "Edit Feature"
    bl_description = "Edit selected feature dimensions, formulas, input features, and name"
    bl_options = {"REGISTER", "UNDO"}
    feature_id: StringProperty(options={"HIDDEN"})
    kind: StringProperty(options={"HIDDEN"})
    original_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    resume_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    consent_retry: BoolProperty(options={"HIDDEN", "SKIP_SAVE"}, default=False)
    expression_retry: BoolProperty(options={"HIDDEN", "SKIP_SAVE"}, default=False)
    edit_action: EnumProperty(
        name="Next step",
        options={"SKIP_SAVE"},
        items=[
            ("APPLY", "Apply edits", "Rebuild the entire candidate atomically"),
            ("RESELECT", "Reselect edge / opening", "Review and pick on the saved input body"),
        ],
    )

    radius_parameter_name: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    radius_parameter_value: StringProperty(options={"SKIP_SAVE"})
    radius_edit_scope: EnumProperty(
        name="Edit radius", options={"SKIP_SAVE"},
        items=[
            ("FEATURE", "This feature only", "Replace this radius expression; leave project parameters unchanged"),
            ("PARAMETER", "Shared parameter", "Change the named radius parameter and all its uses; keep this radius linked"),
        ], default="FEATURE",
    )

    depth_parameter_name: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    depth_parameter_value: StringProperty(options={"SKIP_SAVE"})
    depth_edit_scope: EnumProperty(
        name="Edit depth",
        options={"SKIP_SAVE"},
        items=[
            ("FEATURE", "This feature only", "Replace this depth expression; leave project parameters unchanged"),
            ("PARAMETER", "Shared parameter", "Change the named parameter and all its uses; keep this depth linked"),
        ],
        default="FEATURE",
    )

    linked_depth_scope: EnumProperty(
        name="Edit tool depth",
        options={"SKIP_SAVE"},
        items=[
            ("FEATURE", "Tool formula only", "Replace this tool depth expression; leave project parameters unchanged"),
            ("PARAMETER", "Shared parameter", "Change the named parameter and all its uses; keep the tool depth linked"),
        ],
        default="FEATURE",
    )

    linked_tool_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    linked_tool_label: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    linked_consumers: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    extrude_end_condition: EnumProperty(
        name="End condition",
        items=[
            ("BLIND", "Blind", "Signed depth along the normal"),
            UP_TO_FACE_ITEM,
            ("SYMMETRIC", "Symmetric / Mid-plane", "Half the total depth on each side"),
        ],
    )
    linked_end_condition: EnumProperty(
        name="End condition",
        items=[
            ("BLIND", "Blind", "Use a signed depth"),
            UP_TO_FACE_ITEM,
            ("SYMMETRIC", "Symmetric / Mid-plane", "Half the positive total depth on each side"),
            ("THROUGH_ALL", "Through All", "Follow the target solid extent on every rebuild"),
        ],
    )
    linked_direction: EnumProperty(
        name="Direction",
        items=[
            ("1", "Along sketch normal", "Remove forward from the sketch plane"),
            ("-1", "Opposite sketch normal", "Remove backward from the sketch plane"),
        ],
    )
    linked_length: StringProperty(name="Signed depth (mm)", options={"SKIP_SAVE"})
    linked_profile: EnumProperty(name="Extrusion profile", items=_profile_choices)
    allow_shared_extrusion: BoolProperty(
        name="Also update the shared tool and listed features", default=False, options={"SKIP_SAVE"}
    )

    def invoke(self, context, event):
        from .solid_review import cancel_consent_reopen

        cancel_consent_reopen(context)
        try:
            state = _state(context)
            document = _read_document(state)
            if not self.feature_id:
                self.feature_id = state.features[state.feature_index].feature_id
            feature = next(f for f in document["features"] if f["id"] == self.feature_id)
            from .hole_recipe import inspect_hole

            if inspect_hole(document, self.feature_id) is not None:
                return bpy.ops.mcad.round_hole("INVOKE_DEFAULT", feature_id=self.feature_id)
            if feature["kind"] not in FEATURE_FIELDS:
                raise ValueError("Use Edit Sketch for constrained sketch geometry")
            self.radius_parameter_name = radius_parameter(document, feature)
            self.radius_parameter_value = (
                str(document["parameters"][self.radius_parameter_name])
                if self.radius_parameter_name else ""
            )
            self.radius_edit_scope = "FEATURE"
            self.depth_parameter_name = depth_parameter(document, feature)
            self.depth_parameter_value = (
                str(document["parameters"][self.depth_parameter_name])
                if self.depth_parameter_name else ""
            )
            self.depth_edit_scope = "FEATURE"
            self.linked_depth_scope = "FEATURE"
            self.linked_tool_id = ""
            self.linked_consumers = ""
            self.allow_shared_extrusion = False
            linked = linked_extrusion(document, self.feature_id)
            if linked:
                tool, consumers = linked
                self.linked_tool_id = tool["id"]
                self.linked_tool_label = tool["label"]
                self.depth_parameter_name = depth_parameter(document, tool)
                self.depth_parameter_value = (
                    str(document["parameters"][self.depth_parameter_name])
                    if self.depth_parameter_name else ""
                )
                self.linked_end_condition = end_condition(tool["kind"])
                if tool["kind"] == "extrude_to_face":
                    self.target = tool["inputs"]["target"]
                    self.end_face = tool["end_face"]
                    self.offset = str(tool["params"].get("offset", 0))
                self.linked_direction = str(int(tool["params"].get("direction", 1)))
                self.linked_length = str(tool["params"].get("length", 10))
                self.linked_profile = tool["inputs"]["profile"]
                self.linked_consumers = "\n".join(
                    f"{item['label']} ({item['id']})" for item in consumers
                )
            self.kind = feature["kind"]
            self.extrude_end_condition = end_condition(self.kind)
            if self.kind == "extrude_to_face":
                self.target = feature["inputs"]["target"]
                self.end_face = feature["end_face"]
            self.feature_label = feature["label"]
            placement = feature.get("sweep_placement")
            self.sweep_placement_mode = "AUTO" if placement is not None else "AUTHORED"
            self.sweep_reverse = placement["reverse"] if placement is not None else False
            self.sweep_roll = str(placement["roll_degrees"]) if placement is not None else "0"
            if self.kind == "loft":
                if "loft_sections" in feature:
                    profiles = [feature["inputs"][p] for p in feature["loft_sections"]["ports"]]
                    self.start, self.end = profiles[0], profiles[-1]
                    _initialize_loft(self, profiles)
                    self.loft_mode = "ORDERED"
                else:
                    self.loft_mode = "LEGACY"
            for key, value in {**feature["params"], **feature["inputs"]}.items():
                if self.kind == "loft" and "loft_sections" in feature and key in feature["inputs"]:
                    continue
                setattr(self, key, str(int(value)) if key == "direction" else str(value))
            mirror_plane_ui.initialize(self, document["parameters"])
            if "support_face" in feature:
                self.support_face = feature["support_face"]
            self.shell_mode = "OPEN" if "opening_faces" in feature else "CLOSED"
            self.opening_faces_json = ""
            if hasattr(self, "shell_choices_ready"):
                self.shell_choices_ready = False
            if "opening_faces" in feature:
                self.opening_face = feature["opening_faces"][0]
                self.opening_faces_json = json.dumps(feature["opening_faces"])
            self.edge_mode = (
                "MULTI"
                if "edge_pairs" in feature
                else ("PAIR" if "edge_faces" in feature else "ALL")
            )
            self.edge_pairs_json = json.dumps(feature.get("edge_pairs", []))
            if "edge_faces" in feature:
                self.face_a, self.face_b = feature["edge_faces"]
            self.original_json = state.document_json
            if self.resume_json:
                values = json.loads(self.resume_json)
                if (
                    values.get("original_json") != self.original_json
                    or values.get("feature_id") != self.feature_id
                ):
                    raise ValueError("Document changed; reopen Edit Feature.")
                allowed = (
                    set(FEATURE_FIELDS[self.kind])
                    | set(FEATURE_INPUTS.get(self.kind, ()))
                    | {
                        "feature_id",
                        "original_json",
                        "feature_label",
                        "edge_mode",
                        "edge_pairs_json",
                        "shell_mode",
                        "face_a",
                        "face_b",
                        "opening_face",
                        "opening_faces_json",
                    }
                )
                if self.consent_retry and self.expression_retry:
                    raise ValueError("Ambiguous retained editor intent")
                if self.expression_retry:
                    validate_circle_expression_resume(
                        values, self.original_json, self.feature_id, self.kind,
                        self.radius_parameter_name,
                    )
                    allowed = set(values)
                    self.allow_shared_extrusion = False
                if self.consent_retry:
                    if self.kind not in {"cut", "union"}:
                        raise ValueError("Retained consent edit requires its exact Boolean tool")
                    validate_consent_resume(values, self.original_json, self.feature_id, self.linked_tool_id)
                    allowed = set(values)
                if set(values) - allowed or any(not isinstance(v, str) for v in values.values()):
                    raise ValueError("Invalid retained feature editor values.")
                # Dynamic face enums depend on their owning input. Restore input
                # IDs first regardless of JSON/frozenset order, then face choices.
                face_fields = {"support_face", "end_face", "face_a", "face_b", "opening_face"}
                for key in sorted(values, key=lambda name: (name in face_fields, name)):
                    setattr(self, key, values[key])
                self.resume_json = ""
            _shell_choices(self, context)
            self.edit_action = "APPLY"
            return context.window_manager.invoke_props_dialog(
                self,
                width=560,
                confirm_text="Continue" if self.kind in {"fillet", "chamfer", "shell"} else "Apply",
            )
        except Exception as exc:
            return _reject_candidate(self, context, feature_error(self.kind, exc))

    check = _solid_check

    def execute(self, context):
        try:
            if not self.poll(context):
                raise ValueError("Finish the current operation before editing a solid feature")
            state = _state(context)
            if state.document_json != self.original_json:
                raise ValueError("Document changed; reopen Edit Feature to retain those edits")
            if self.edit_action == "RESELECT":
                if self.kind not in {"fillet", "chamfer", "shell"}:
                    raise ValueError("This feature does not support visual reselection.")
                keys = (
                    set(FEATURE_FIELDS[self.kind])
                    | set(FEATURE_INPUTS.get(self.kind, ()))
                    | {
                        "feature_id",
                        "original_json",
                        "feature_label",
                        "edge_mode",
                        "edge_pairs_json",
                        "shell_mode",
                        "face_a",
                        "face_b",
                        "opening_face",
                        "opening_faces_json",
                    }
                )
                values = {key: getattr(self, key) for key in keys}
                if self.kind == "shell" and self.shell_mode == "OPEN":
                    values["opening_faces_json"] = json.dumps(_shell_values(self))
                bpy.ops.mcad.reselect_solid_input("INVOKE_DEFAULT", editor_json=json.dumps(values))
                return {"CANCELLED"}  # The editor itself has not committed an Undo step.
            document = _read_document(state)
            feature = next(f for f in document["features"] if f["id"] == self.feature_id)
            shared_depth = (
                self.depth_edit_scope == "PARAMETER"
                and self.extrude_end_condition in {"BLIND", "SYMMETRIC"}
            )
            shared_radius = self.radius_edit_scope == "PARAMETER"
            depth_input = self.depth_parameter_name if shared_depth else self.length
            candidate = edit_feature(
                document,
                self.feature_id,
                label=self.feature_label,
                params={
                    k: depth_input if k == "length" and shared_depth
                    else self.radius_parameter_name if k == "radius" and shared_radius
                    else getattr(self, k)
                    for k in feature["params"]
                },
                inputs=(
                    dict(feature["inputs"])
                    if self.kind == "loft"
                    else {k: getattr(self, k) for k in feature["inputs"]}
                ),
            )
            if self.linked_tool_id:
                linked_shared = (
                    self.linked_depth_scope == "PARAMETER"
                    and self.linked_end_condition in {"BLIND", "SYMMETRIC"}
                    and self.tool == self.linked_tool_id
                )
                candidate = edit_linked_extrusion(
                    document,
                    candidate,
                    self.feature_id,
                    tool_id=self.linked_tool_id,
                    length=self.depth_parameter_name if linked_shared else self.linked_length,
                    profile=self.linked_profile,
                    allow_shared=self.allow_shared_extrusion,
                    end_condition=self.linked_end_condition,
                    direction=self.linked_direction,
                    **(
                        {"target": self.target, "end_face": self.end_face, "offset": self.offset}
                        if self.linked_end_condition == "UP_TO_FACE"
                        else {}
                    ),
                )
                if linked_shared:
                    candidate = edit_shared_linked_depth(
                        document, candidate, self.feature_id, self.linked_tool_id,
                        self.depth_parameter_name, self.depth_parameter_value,
                        allow_shared=self.allow_shared_extrusion,
                    )
            target = next(f for f in candidate["features"] if f["id"] == self.feature_id)
            if self.kind == "sweep":
                set_sweep_placement(
                    target,
                    self.sweep_placement_mode,
                    reverse=self.sweep_reverse,
                    roll=self.sweep_roll,
                )
            if self.kind == "loft":
                _set_loft(target, self)
            if self.kind == "shell":
                if self.shell_mode == "OPEN":
                    target["opening_faces"] = _shell_values(self)
                else:
                    target.pop("opening_faces", None)
            if self.kind in {"extrude", "extrude_symmetric", "extrude_to_face"}:
                if self.extrude_end_condition == "UP_TO_FACE":
                    set_up_to_face(
                        target,
                        profile=self.profile,
                        target=self.target,
                        end_face=self.end_face,
                        direction=self.direction,
                        offset=self.offset,
                    )
                elif self.extrude_end_condition in {"BLIND", "SYMMETRIC"}:
                    old_length = feature["params"].get("length")
                    target["kind"] = (
                        "extrude_symmetric"
                        if self.extrude_end_condition == "SYMMETRIC"
                        else "extrude"
                    )
                    target["params"] = {
                        "length": old_length
                        if str(old_length) == depth_input
                        else normalize_unit_input(depth_input, "length")
                    }
                    target["inputs"] = {"profile": self.profile}
                    target.pop("end_face", None)
                else:
                    raise ValueError("Choose Blind, Symmetric or Up to planar face")
            if shared_radius:
                candidate = edit_shared_radius(
                    document, candidate, self.feature_id,
                    self.radius_parameter_name, self.radius_parameter_value,
                )
            if shared_depth:
                candidate = edit_shared_depth(
                    document, candidate, self.feature_id,
                    self.depth_parameter_name, self.depth_parameter_value,
                )
            # Shared parameter updates return a detached copy; reacquire its feature.
            target = next(f for f in candidate["features"] if f["id"] == self.feature_id)
            if self.kind.startswith("sketch_face_"):
                target["support_face"] = self.support_face
            if self.kind in {"fillet", "chamfer"}:
                _set_blend_selection(target, self)
            success = _commit_candidate(
                context, candidate, state.document_path, stage_feature_id=self.feature_id
            )
            if success:
                # History selection is not the canonical output. Resolve the edited
                # stable ID in the fresh collection, never a filtered/old position.
                for index, row in enumerate(_state(context).features):
                    if row.feature_id == self.feature_id:
                        _state(context).feature_index = index
                        break
            return _report_result(self, context, success)
        except document_state.bridge.CandidateExpressionError as exc:
            if (
                self.kind in {"sketch_circle", "sketch_face_circle"}
                and exc.feature_id == self.feature_id
                and exc.code in {"unknown_parameter", "invalid_expression"}
                and _state(context).document_json == self.original_json
            ):
                from .solid_review import queue_consent_reopen

                try:
                    if queue_consent_reopen(
                        context, circle_expression_resume_values(self), expression=True
                    ):
                        _state(context).last_action_error = str(exc)
                        self.report({"WARNING"}, "Expression rejected; model unchanged. Returning draft.")
                        return {"CANCELLED"}
                except (ValueError, ReferenceError, RuntimeError):
                    pass
            return _reject_candidate(self, context, feature_error(self.kind, exc))
        except SharedToolConsentRequired as exc:
            from .solid_review import queue_consent_reopen

            message = feature_error(self.kind, exc)
            try:
                if queue_consent_reopen(context, consent_resume_values(self)):
                    _state(context).last_action_error = message
                    self.report({"WARNING"}, "Shared-tool permission required; model unchanged.")
                    return {"CANCELLED"}
            except (ValueError, ReferenceError, RuntimeError):
                pass
            return _reject_candidate(self, context, message)
        except Exception as exc:
            return _reject_candidate(self, context, feature_error(self.kind, exc))


for _class in (MCAD_OT_add_solid_feature, MCAD_OT_edit_solid_feature):
    _class.__annotations__.update(_FIELDS)

CLASSES = (
    MCAD_PG_loft_section,
    MCAD_UL_loft_sections,
    MCAD_PG_shell_opening,
    MCAD_UL_shell_openings,
    MCAD_OT_add_solid_feature,
    MCAD_OT_edit_solid_feature,
)
