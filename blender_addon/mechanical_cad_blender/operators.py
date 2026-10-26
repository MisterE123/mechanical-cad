"""Undoable CAD authoring, persistence and viewport navigation operators.

Operators delegate canonical edits and replay to document_state. No operator
imports the kernel or treats edited Blender mesh data as a CAD operation."""

import copy
import json
import os
import tempfile
import uuid
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import bridge, document_state, execution_lease, extrusion_preview, operation_contracts
from .common import _state
from .display import _focus_display, _owned_objects
from .document_paths import normalized_document_path, normalized_export_check
from .document_state import (
    _append_feature,
    _commit_candidate,
    _new_feature,
    _read_document,
    demo_document,
    regenerate,
)
from .extrusion_end_condition import (
    DIRECTION_ITEMS,
    OFFSET_DESCRIPTION,
    UP_TO_FACE_ITEM,
    _end_face_choices,
    _source_choices,
    draw_up_to_face,
    set_up_to_face,
)
from .help_ui import _draw_feature_help, _feature_help_next, _feature_help_previous
from .solid_feature_edit import SOLID_KINDS


def _report_result(operator, context, success):
    if success:
        operator.report({"INFO"}, "CAD model regenerated from feature history")
        return {"FINISHED"}
    # FINISHED records an undoable failed draft. CAD success remains the
    # explicit FAILED status, never inferred from Blender operator completion.
    operator.report({"WARNING"}, _state(context).error[:1000])
    return {"FINISHED"}


def _reject_candidate(operator, context, message):
    _state(context).last_action_error = str(message)
    operator.report({"ERROR"}, str(message)[:1000])
    return {"CANCELLED"}


def part_action_reason(context, action, *, owner_role="part"):
    """Read-only whole-document policy; an empty reason is not runtime authority."""
    try:
        operation_contracts.result_version_for(
            _read_document(_state(context)), action=action, owner_role=owner_role
        )
    except (ValueError, RuntimeError, TypeError, KeyError, AttributeError) as exc:
        return str(exc)
    return ""


def _feature_candidate(document, feature):
    candidate = copy.deepcopy(document)
    candidate["features"].append(copy.deepcopy(feature))
    candidate["active_feature"] = feature["id"]
    if feature["kind"] == "sketch_constrained":
        candidate["schema_version"] = 2
    return candidate


def feature_action_reason(context, kind, *, profile=None):
    """Test a prospective full graph through the shared operation policy.

    Probe dimensions are only for action discovery. Actual execution validates
    its exact submitted feature again before handing off to canonical authoring.
    """
    try:
        document = _read_document(_state(context))
        used = {item["id"] for item in document["features"]}
        index = 1
        while f"ui_candidate_{index}" in used:
            index += 1
        identifier = f"ui_candidate_{index}"
        feature = dict(id=identifier, kind=kind, label="New feature", params={}, inputs={})
        if kind == "extrude":
            profiles = [
                item["id"] for item in document["features"] if item["kind"].startswith("sketch_")
            ]
            if profile is not None:
                profiles = [profile]
            if not profiles:
                return "Create a supported sketch profile before extruding."
            reasons = []
            for selected in profiles:
                feature.update(params={"length": 10}, inputs={"profile": selected})
                try:
                    operation_contracts.result_version_for(_feature_candidate(document, feature))
                    return ""
                except (ValueError, TypeError, KeyError) as exc:
                    reasons.append(str(exc))
            return reasons[0]
        if kind == "sketch_rectangle":
            feature["params"] = dict(width=10, height=10, x=0, y=0, z=0)
        elif kind == "sketch_circle":
            feature["params"] = dict(radius=5, x=0, y=0, z=0)
        elif kind == "sketch_constrained":
            feature["sketch"] = dict(
                schema_version=1,
                id=identifier + "_sketch",
                units="mm",
                plane=dict(id=identifier + "_plane", origin=[0, 0, 0], quaternion=[1, 0, 0, 0]),
                points=[],
                lines=[],
                constraints=[],
            )
        elif kind == "cut":
            solids = [item["id"] for item in document["features"] if item["kind"] in SOLID_KINDS]
            if len(solids) < 2:
                return "Cut requires two supported solid features."
            feature["inputs"] = {"base": solids[-2], "tool": solids[-1]}
        else:
            return "This feature action is unavailable."
        operation_contracts.result_version_for(_feature_candidate(document, feature))
    except (ValueError, RuntimeError, TypeError, KeyError, AttributeError) as exc:
        return str(exc)
    return ""


def _poll_reason(cls, reason):
    if reason and callable(getattr(cls, "poll_message_set", None)):
        cls.poll_message_set(reason)
    return not reason


class MCAD_OT_new_demo(Operator):
    bl_idname = "mcad.new_demo"
    bl_label = "New Demo"
    bl_description = "Replace the current CAD document with a parametric drilled plate"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.mode != "OBJECT":
            self.report({"ERROR"}, "Return to Object Mode first")
            return {"CANCELLED"}
        try:
            return _report_result(self, context, _commit_candidate(context, demo_document()))
        except Exception as exc:
            return _reject_candidate(self, context, f"New Demo rejected: {exc}")


class MCAD_OT_regenerate(Operator):
    bl_idname = "mcad.regenerate"
    bl_label = "Regenerate"
    bl_description = "Replay authoritative CAD history; replace the disposable Blender mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and bool(_state(context).document_json)
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
        )

    def execute(self, context):
        try:
            return _report_result(self, context, regenerate(context))
        except bridge.BridgeError as exc:
            return _reject_candidate(self, context, exc)


class MCAD_OT_load(Operator, ImportHelper):
    bl_idname = "mcad.load_document"
    bl_label = "Load CAD Document"
    bl_description = "Validate and replay a .mcad.json document before accepting it"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".mcad.json"
    filter_glob: StringProperty(default="*.mcad.json;*.json", options={"HIDDEN"})

    def execute(self, context):
        if context.mode != "OBJECT":
            self.report({"ERROR"}, "Return to Object Mode first")
            return {"CANCELLED"}
        try:
            path = Path(bpy.path.abspath(self.filepath)).expanduser()
            if path.stat().st_size > bridge.MAX_DOCUMENT_BYTES:
                raise bridge.BridgeError("Document exceeds the 2 MiB input limit.")
            document = bridge.parse_document_json(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise bridge.BridgeError("CAD document must be a JSON object.")
            return _report_result(self, context, _commit_candidate(context, document, str(path)))
        except Exception as exc:
            return _reject_candidate(
                self, context, f"Load rejected; current document unchanged: {exc}"
            )


class MCAD_OT_save(Operator, ExportHelper):
    check = normalized_export_check

    bl_idname = "mcad.save_document"
    bl_label = "Save CAD Document"
    bl_description = "Save parameters and feature history as portable JSON (no display mesh)"
    filename_ext = ".mcad.json"
    filter_glob: StringProperty(default="*.mcad.json", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return bool(_state(context).document_json)

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = _state(context).document_path or "model.mcad.json"
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        temporary = None
        try:
            document = _read_document(_state(context))
            path = Path(bpy.path.abspath(self.filepath)).expanduser()
            path = normalized_document_path(path, self.filename_ext)
            content = json.dumps(document, indent=2, allow_nan=False) + "\n"
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
            _state(context).document_path = str(path)
            self.report({"INFO"}, f"Saved {path.name}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Could not save CAD document: {exc}")
            return {"CANCELLED"}
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


class MCAD_OT_activate_feature(Operator):
    bl_idname = "mcad.activate_feature"
    bl_label = "Display Selected Feature"
    bl_description = "Make the selected history feature the displayed CAD result"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        state = _state(context)
        return (
            context.mode == "OBJECT"
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
            and 0 <= state.feature_index < len(state.features)
        )

    def execute(self, context):
        state = _state(context)
        try:
            document_state.require_no_sketch_draft(context)
            document = _read_document(state)
        except bridge.BridgeError as exc:
            return _reject_candidate(self, context, exc)
        try:
            document["active_feature"] = state.features[state.feature_index].feature_id
            operation_contracts.result_version_for(document)
            # Guard before canonical mutation: a direct invocation can race a
            # previously successful poll while another adapter acquires execution.
            with document_state.replay_guard(context):
                state.document_json = json.dumps(document, allow_nan=False)
                return _report_result(self, context, document_state._regenerate_locked(context))
        except (ValueError, bridge.BridgeError) as exc:
            return _reject_candidate(self, context, exc)


_ENUM_CACHE = {}


def _feature_choices(context, category):
    if context is None or not hasattr(context.scene, "mechanical_cad"):
        return []
    rows = _state(context).features
    choices = [
        (row.feature_id, f"{row.label} [{row.feature_id}]", f"{row.kind}; status: {row.status}")
        for row in rows
        if (
            row.kind.startswith("sketch_")
            and not feature_action_reason(context, "extrude", profile=row.feature_id)
            if category == "profile"
            else row.kind in SOLID_KINDS
        )
    ]
    # Blender stores enum string pointers; retain strings for the life of the UI.
    key = (category, tuple(choices))
    return _ENUM_CACHE.setdefault(key, choices)


def _profile_choices(self, context):
    return _feature_choices(context, "profile")


def _solid_choices(self, context):
    return _feature_choices(context, "solid")


class MCAD_OT_new_document(Operator):
    bl_idname = "mcad.new_document"
    bl_label = "New CAD Document"
    bl_description = (
        "Start an empty millimetre CAD document for sketches, parametric parts and assemblies"
    )
    bl_options = {"REGISTER", "UNDO"}
    name: StringProperty(
        name="Document name",
        default="Untitled part",
        description="Human-readable name saved in the CAD document",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400, confirm_text="Create")

    def execute(self, context):
        if context.mode != "OBJECT":
            self.report({"ERROR"}, "Return to Object Mode first")
            return {"CANCELLED"}
        document = {
            "schema_version": 1,
            "id": f"document_{uuid.uuid4().hex}",
            "name": self.name or "Untitled part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
        try:
            return _report_result(self, context, _commit_candidate(context, document))
        except Exception as exc:
            return _reject_candidate(self, context, f"New document rejected: {exc}")


class _MCAD_FeatureOperator:
    @classmethod
    def poll(cls, context):
        return (
            context.mode == "OBJECT"
            and bool(_state(context).document_json)
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
            and _poll_reason(cls, feature_action_reason(context, cls.feature_kind))
        )

    def invoke(self, context, event):
        reason = feature_action_reason(context, self.feature_kind)
        if reason:
            return _reject_candidate(self, context, reason)
        return context.window_manager.invoke_props_dialog(self, width=440, confirm_text="Apply")

    def _apply(self, context, feature):
        try:
            operation_contracts.result_version_for(
                _feature_candidate(_read_document(_state(context)), feature)
            )
            return _report_result(self, context, _append_feature(context, feature))
        except Exception as exc:
            return _reject_candidate(self, context, f"Feature not added: {exc}")


class MCAD_OT_rectangle(_MCAD_FeatureOperator, Operator):
    feature_kind = "sketch_rectangle"
    bl_idname = "mcad.add_rectangle"
    bl_label = "Add Rectangle Sketch"
    bl_description = "Create an XY-plane rectangle from dimensions and lower-left corner; Apply adds editable named parameters"
    bl_options = {"REGISTER", "UNDO"}
    help_topic: StringProperty(default="sketch.rectangle", options={"HIDDEN", "SKIP_SAVE"})
    help_summary = (
        "Apply saves an XY-plane rectangle profile.",
        "Edit named parameters and Regenerate to revise.",
    )
    show_help: BoolProperty(
        name="Help",
        description="Read help in this same draft dialog without losing entered values",
        default=False,
        options={"SKIP_SAVE"},
    )
    help_page: IntProperty(default=1, min=1, options={"HIDDEN", "SKIP_SAVE"})
    help_previous: BoolProperty(update=_feature_help_previous, options={"SKIP_SAVE"})
    help_next: BoolProperty(update=_feature_help_next, options={"SKIP_SAVE"})

    width: FloatProperty(
        name="Width (mm)", description="Rectangle extent along +X", default=40, min=0.001
    )
    height: FloatProperty(
        name="Height (mm)", description="Rectangle extent along +Y", default=30, min=0.001
    )
    x: FloatProperty(name="Corner X (mm)", description="Lower-left corner X coordinate")
    y: FloatProperty(name="Corner Y (mm)", description="Lower-left corner Y coordinate")
    z: FloatProperty(name="Plane Z (mm)", description="XY-plane offset along Z")

    def draw(self, context):
        self.layout.label(text="Plane: XY; origin: lower-left corner")
        for key in ("width", "height", "x", "y", "z"):
            self.layout.prop(self, key)
        _draw_feature_help(self, context)

    def execute(self, context):
        feature = _new_feature(
            context,
            "sketch_rectangle",
            {key: getattr(self, key) for key in ("width", "height", "x", "y", "z")},
            {},
            "Rectangle sketch",
        )
        return self._apply(context, feature)


class MCAD_OT_circle(_MCAD_FeatureOperator, Operator):
    feature_kind = "sketch_circle"
    bl_idname = "mcad.add_circle"
    bl_label = "Add Circle Sketch"
    bl_description = (
        "Create an XY-plane circle from radius and centre; Apply adds editable named parameters"
    )
    bl_options = {"REGISTER", "UNDO"}
    help_topic: StringProperty(default="sketch.circle", options={"HIDDEN", "SKIP_SAVE"})
    help_summary = (
        "Apply saves a circle profile; radius is half its diameter.",
        "Edit named parameters and Regenerate to revise.",
    )
    show_help: BoolProperty(
        name="Help",
        description="Read help in this same draft dialog without losing entered values",
        default=False,
        options={"SKIP_SAVE"},
    )
    help_page: IntProperty(default=1, min=1, options={"HIDDEN", "SKIP_SAVE"})
    help_previous: BoolProperty(update=_feature_help_previous, options={"SKIP_SAVE"})
    help_next: BoolProperty(update=_feature_help_next, options={"SKIP_SAVE"})

    radius: FloatProperty(
        name="Radius (mm)",
        description="Distance from the circle centre to its edge",
        default=4,
        min=0.001,
    )
    x: FloatProperty(name="Centre X (mm)", description="Circle centre X coordinate")
    y: FloatProperty(name="Centre Y (mm)", description="Circle centre Y coordinate")
    z: FloatProperty(name="Plane Z (mm)", description="XY-plane offset along Z")

    def draw(self, context):
        self.layout.label(text="Plane: XY; origin: circle centre")
        for key in ("radius", "x", "y", "z"):
            self.layout.prop(self, key)
        _draw_feature_help(self, context)

    def execute(self, context):
        feature = _new_feature(
            context,
            "sketch_circle",
            {key: getattr(self, key) for key in ("radius", "x", "y", "z")},
            {},
            "Circle sketch",
        )
        return self._apply(context, feature)


class MCAD_OT_extrude(_MCAD_FeatureOperator, Operator):
    feature_kind = "extrude"
    bl_idname = "mcad.add_extrude"
    bl_label = "Extrude Sketch"
    bl_description = (
        "Choose a recorded profile and signed normal distance; negative lengths extrude inward"
    )
    bl_options = {"REGISTER", "UNDO"}
    help_topic: StringProperty(default="feature.extrude", options={"HIDDEN", "SKIP_SAVE"})
    help_summary = (
        "Apply extrudes along the profile normal (+Z for XY).",
        "Check the profile; its dimensions stay editable.",
    )
    show_help: BoolProperty(
        name="Help",
        description="Read help in this same draft dialog without losing entered values",
        default=False,
        options={"SKIP_SAVE"},
    )
    help_page: IntProperty(default=1, min=1, options={"HIDDEN", "SKIP_SAVE"})
    help_previous: BoolProperty(update=_feature_help_previous, options={"SKIP_SAVE"})
    help_next: BoolProperty(update=_feature_help_next, options={"SKIP_SAVE"})

    enter_part_after_apply: BoolProperty(
        default=False, options={"HIDDEN", "SKIP_SAVE"},
        description="Open Part after applying the selected-sketch shortcut",
    )

    profile: EnumProperty(
        name="Profile to extrude",
        description="Recorded primitive or constrained profile used to build the solid",
        items=_profile_choices,
    )
    end_condition: EnumProperty(
        name="End condition",
        items=[
            ("BLIND", "Blind", "Signed depth along the sketch normal"),
            UP_TO_FACE_ITEM,
            (
                "SYMMETRIC",
                "Symmetric / Mid-plane",
                "Half the positive total depth on each side of the sketch",
            ),
        ],
        default="BLIND",
    )
    target: EnumProperty(name="Earlier target solid", items=_source_choices)
    end_face: EnumProperty(name="End face", items=_end_face_choices)
    offset: StringProperty(name="Offset (mm)", description=OFFSET_DESCRIPTION, default="0")
    direction: EnumProperty(name="Direction", items=DIRECTION_ITEMS)
    length: FloatProperty(
        name="Length (mm)",
        description="Signed extrusion along the profile normal; negative goes inward, zero is invalid",
        default=10,
        min=-1e6,
        max=1e6,
    )
    length_input: StringProperty(
        name="Depth or formula",
        description="Millimetres or a parameter formula; explicit literals accept mm, cm, m, in or ft",
        default="10",
        maxlen=256,
    )

    @classmethod
    def poll(cls, context):
        return super().poll(context) and bool(_feature_choices(context, "profile"))

    def invoke(self, context, event):
        state = _state(context)
        # Only the selected-profile shortcut requests initial keyboard entry.
        # Its navigation flag is explicitly set even from the Part workspace.
        self._initial_depth_focus = (
            self.properties.is_property_set("enter_part_after_apply", ghost=False)
            and self.properties.is_property_set("profile", ghost=False)
            and self.end_condition in {"BLIND", "SYMMETRIC"}
        )
        if not self.properties.is_property_set("enter_part_after_apply", ghost=False):
            self.enter_part_after_apply = False
        self._shortcut_origin = (context.window, context.workspace, context.scene)
        if not self.properties.is_property_set("length_input"):
            self.length_input = str(self.length)
        # Ignore remembered last-dialog values; preserve an explicitly bound profile.
        if (
            not self.properties.is_property_set("profile", ghost=False)
            and 0 <= state.feature_index < len(state.features)
        ):
            selected = state.features[state.feature_index]
            if selected.feature_id in {item[0] for item in _profile_choices(self, context)}:
                self.profile = selected.feature_id
        extrusion_preview.start(self, context)
        result = super().invoke(context, event)
        if result != {"RUNNING_MODAL"}:
            extrusion_preview.cancel(self, context)
        return result

    def draw(self, context):
        initial_depth_focus = getattr(self, "_initial_depth_focus", False)
        self._initial_depth_focus = False
        self.layout.prop(self, "profile")
        self.layout.prop(self, "end_condition")
        if self.end_condition == "UP_TO_FACE":
            draw_up_to_face(self.layout, self)
        else:
            depth_row = self.layout.row()
            depth_row.activate_init = initial_depth_focus
            depth_row.prop(
                self,
                "length_input",
                text="Total depth (mm)"
                if self.end_condition == "SYMMETRIC"
                else "Signed depth (mm)",
            )
            self.layout.label(
                text="Half of the positive total depth on each side."
                if self.end_condition == "SYMMETRIC"
                else "Positive: normal direction. Negative: inward. Zero is invalid."
            )
        extrusion_preview.draw(self)
        _draw_feature_help(self, context)

    check = extrusion_preview.changed
    cancel = extrusion_preview.cancel

    def _open_part_after_apply(self, context):
        from . import workspace

        if not self.enter_part_after_apply:
            return
        origin = getattr(self, "_shortcut_origin", None)
        if origin is not None and origin != (context.window, context.workspace, context.scene):
            return
        if workspace.get_role(context) != "SKETCH":
            return
        try:
            workspace.request_workspace(context, "PART", on_ready=_focus_display)
        except Exception as exc:
            # Geometry is already published. Navigation failure is not Apply failure.
            self.report({"WARNING"}, "Extrusion applied; open Part to continue: " + str(exc))

    def modal(self, context, event):
        result = extrusion_preview.modal(self, context, event)
        if result == {"FINISHED"} and self._extrusion_preview.accepted:
            self._open_part_after_apply(context)
        return result

    def preview_candidate(self, context):
        from .unit_input import normalize_unit_input

        if self.end_condition not in {"BLIND", "SYMMETRIC", "UP_TO_FACE"}:
            raise ValueError("Choose an extrusion end condition")
        length = self.length
        if (
            self.end_condition != "UP_TO_FACE"
            and self.properties.is_property_set("length_input")
            and self.length_input != str(length)
        ):
            length = normalize_unit_input(self.length_input, "length")
        feature = _new_feature(
            context,
            "extrude_to_face"
            if self.end_condition == "UP_TO_FACE"
            else "extrude_symmetric"
            if self.end_condition == "SYMMETRIC"
            else "extrude",
            {"length": length},
            {"profile": self.profile},
            "Up to planar face"
            if self.end_condition == "UP_TO_FACE"
            else "Symmetric extrusion"
            if self.end_condition == "SYMMETRIC"
            else "Extrusion",
        )
        candidate = _read_document(_state(context))
        if self.end_condition == "UP_TO_FACE":
            set_up_to_face(
                feature,
                profile=self.profile,
                target=self.target,
                end_face=self.end_face,
                direction=self.direction,
                offset=self.offset,
            )
        else:
            key = feature["id"] + "_length"
            if key in candidate["parameters"]:
                raise ValueError("Extrusion parameter already exists")
            candidate["parameters"][key] = feature["params"]["length"]
            feature["params"]["length"] = key
        candidate["features"].append(feature)
        candidate["active_feature"] = feature["id"]
        return candidate

    def execute(self, context):
        try:
            pending = extrusion_preview.apply(self, context)
            if pending is not None:
                return pending
            candidate = self.preview_candidate(context)
            success = _commit_candidate(context, candidate, _state(context).document_path)
            result = _report_result(self, context, success)
            if success:
                self._open_part_after_apply(context)
            return result
        except Exception as exc:
            extrusion_preview.cancel(self, context)
            return _reject_candidate(self, context, str(exc))


class MCAD_OT_cut(_MCAD_FeatureOperator, Operator):
    feature_kind = "cut"
    bl_idname = "mcad.add_cut"
    bl_label = "Cut Solid"
    bl_description = (
        "Choose the base to keep and tool to subtract; Apply creates a new boolean result"
    )
    bl_options = {"REGISTER", "UNDO"}
    help_topic: StringProperty(default="feature.boolean_operands", options={"HIDDEN", "SKIP_SAVE"})
    help_summary = (
        "Apply saves Base minus Tool as one nonempty solid.",
        "Source features remain in the saved history.",
    )
    show_help: BoolProperty(
        name="Help",
        description="Read help in this same draft dialog without losing entered values",
        default=False,
        options={"SKIP_SAVE"},
    )
    help_page: IntProperty(default=1, min=1, options={"HIDDEN", "SKIP_SAVE"})
    help_previous: BoolProperty(update=_feature_help_previous, options={"SKIP_SAVE"})
    help_next: BoolProperty(update=_feature_help_next, options={"SKIP_SAVE"})

    base: EnumProperty(
        name="Base · keep this solid",
        description="Solid whose remaining material becomes the result",
        items=_solid_choices,
    )
    tool: EnumProperty(
        name="Tool · subtract this solid",
        description="Solid volume removed from the base",
        items=_solid_choices,
    )

    @classmethod
    def poll(cls, context):
        return super().poll(context) and len(_feature_choices(context, "solid")) >= 2

    def invoke(self, context, event):
        solids = _feature_choices(context, "solid")
        if len(solids) >= 2:
            self.base, self.tool = solids[-2][0], solids[-1][0]
        return super().invoke(context, event)

    def draw(self, context):
        self.layout.prop(self, "base", text="Base (keep)")
        self.layout.prop(self, "tool", text="Tool (subtract)")
        self.layout.label(text="Result = Base minus Tool. Verify both choices.")
        self.layout.label(text="Both source solids remain in the feature history.")
        _draw_feature_help(self, context)

    def execute(self, context):
        if self.base == self.tool:
            self.report({"ERROR"}, "Choose two different solids for Base and Tool")
            return {"CANCELLED"}
        feature = _new_feature(
            context, "cut", {}, {"base": self.base, "tool": self.tool}, "Boolean cut"
        )
        return self._apply(context, feature)


class MCAD_OT_focus(Operator):
    bl_idname = "mcad.focus_result"
    bl_label = "Focus CAD Result"
    bl_description = "Frame the CAD result in local view without deleting other objects; Show Whole Scene restores the full scene"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _state(context).status in {"READY", "FAILED"} and bool(_owned_objects(context.scene))

    def execute(self, context):
        if not _focus_display(context):
            self.report({"WARNING"}, "Open a 3D Viewport to focus the CAD result")
        return {"FINISHED"}


class MCAD_OT_show_scene(Operator):
    bl_idname = "mcad.show_scene"
    bl_label = "Show Whole Scene"
    bl_description = "Leave the isolated CAD local view and frame all scene objects"
    bl_options = {"REGISTER"}

    def execute(self, context):
        _focus_display(context, whole_scene=True)
        return {"FINISHED"}


class MCAD_OT_focus_preview(Operator):
    bl_idname = "mcad.focus_preview"
    bl_label = "Focus Preview"
    bl_description = "Frame the current proposed outline only; does not Apply or change selection"

    def execute(self, context):
        try:
            extrusion_preview.focus(context)
            return {"FINISHED"}
        except (ValueError, ReferenceError, RuntimeError) as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
