"""Contextual native CAD controls: left gizmos, right history, named menus.

The only custom-drawn geometry is an inert backing strip for contrast. Native
button gizmos own icon rendering, hit testing and tooltips. Every action also has
a normal named menu route when gizmos are hidden. Nothing here edits model JSON.
"""

import json
from pathlib import Path

import bpy
import bpy.utils.previews
from bpy.props import EnumProperty, StringProperty
from mathutils import Matrix

from . import (
    assembly_job_ui,
    assembly_ui,
    compact_status,
    constraint_ui,
    document_state,
    execution_lease,
    operators,
    palette_shapes,
    staged_edit,
    tool_glyphs,
    workspace,
    workspace_view,
)
from .help_ui import _diagnostic_button, _help_button, _panel_wrap
from .parameter_presentation import parameter_usage
from .projection_repair_ui import draw_projection_repair
from .staged_edit_ui import draw_staged_edit, pending_message_is_duplicate

# Explicit allowlist: icon assets do not make unimplemented actions available.
_ACTIONS = {
    "IMPORT": (
        "Import STEP Solid",
        "mcad.import_step",
        "history.inspect",
        "IMPORT",
        "Import one exact closed STEP solid into Part history",
    ),
    "NEW": (
        "New Sketch",
        "mcad.new_plane_sketch",
        "sketch.line",
        "CURVE_DATA",
        "Choose an XY, XZ or YZ sketch plane and offset; draw with existing parts visible for context",
    ),
    "NEW_FACE_SKETCH": (
        "Sketch on Face",
        "mcad.new_face_sketch",
        "sketch.line",
        "FACESEL",
        "Click a stable planar face to start an attached sketch that follows upstream edits",
    ),
    "EDIT": (
        "Edit Sketch",
        "mcad.edit_viewport_sketch",
        "history.inspect",
        "EDITMODE_HLT",
        "Edit the selected sketch while preserving its downstream features",
    ),
    "RECTANGLE": (
        "XY Rectangle Shortcut",
        "mcad.new_rectangle_sketch",
        "sketch.rectangle",
        "MESH_PLANE",
        "Start the rectangle shortcut: click two XY corners, then set width and height",
    ),
    "USE_SOLID_EDGE": (
        "Use Solid Edge",
        "mcad.use_solid_edge",
        "sketch.line",
        "EDGESEL",
        "Click a straight solid edge, circular arc or full circle to link construction geometry",
    ),
    "PROJECT": (
        "Project Geometry",
        "mcad.project_sketch_geometry",
        "sketch.line",
        "SNAP_ON",
        "Link a prior sketch line or circle as associative construction geometry",
    ),
    "DRAW_RECTANGLE": (
        "Rectangle",
        "mcad.general_tool",
        "sketch.rectangle",
        "MESH_PLANE",
        "Draw a rectangle with two corners on the current sketch plane; edit its edge dimensions",
    ),
    "FACE_SKETCH_ADVANCED": (
        "Sketch on Face (List)",
        "mcad.new_face_sketch",
        "sketch.line",
        "FACESEL",
        "Choose a stable planar support by feature and face name instead of viewport picking",
    ),
    "SELECT": (
        "Select",
        "mcad.general_tool",
        "history.inspect",
        "RESTRICT_SELECT_OFF",
        "Select explicit sketch entities; Shift adds or removes an entity",
    ),
    "POINTS": (
        "Select Points",
        "mcad.general_tool",
        "history.inspect",
        "VERTEXSEL",
        "Select only endpoints and circle/arc centers; distinct overlapping point identities remain ambiguous",
    ),
    "LINE": (
        "Line",
        "mcad.general_tool",
        "sketch.line",
        "CURVE_PATH",
        "Draw a line with two clicks; hold Shift at the second point to add a Horizontal/Vertical constraint; existing points must lie on that axis",
    ),
    "CIRCLE": (
        "Circle",
        "mcad.general_tool",
        "sketch.circle",
        "MESH_CIRCLE",
        "Draw a circle: click its center, then a point on its radius",
    ),
    "ARC": (
        "Center Arc",
        "mcad.general_tool",
        "sketch.circle",
        "CURVE_BEZCIRCLE",
        "Draw center, start and end to create an editable circular arc",
    ),
    "REVERSE": (
        "Reverse Sweep",
        "mcad.general_tool",
        "sketch.circle",
        "ARROW_LEFTRIGHT",
        "Choose the directed complementary arc without changing its center, endpoint roles, IDs or seeds",
    ),
    "USE_POINT": (
        "Use Existing Point",
        "mcad.general_tool",
        "history.inspect",
        "VERTEXSEL",
        "Choose an exact existing point ID and role for this Line or Arc phase; inspector selection alone never accepts input",
    ),
    "DIMENSION": (
        "Dimension",
        "mcad.general_tool",
        "sketch.dimension",
        "DRIVER_DISTANCE",
        "Press D; click a line interior for length or a circle/arc perimeter for radius.\n"
        "Click two points for straight-line distance, or a point/center then a straight "
        "reference line for unsigned perpendicular offset.\n"
        "Place the label; enter a millimetre value or named formula. Double-click a label to edit.",
    ),
    "HORIZONTAL": (
        "Horizontal",
        "mcad.constraint_action",
        "constraint.horizontal",
        "IPO_CONSTANT",
        "Keep the selected line horizontal in its sketch plane; inspect an existing relation instead of duplicating it",
    ),
    "VERTICAL": (
        "Vertical",
        "mcad.constraint_action",
        "constraint.vertical",
        "ALIGN_JUSTIFY",
        "Keep the selected line vertical in its sketch plane; inspect an existing relation instead of duplicating it",
    ),
    "FIX_HERE": (
        "Fix Here",
        "mcad.constraint_action",
        "constraint.fixed",
        "LOCKED",
        "Fix this point at its current validated solved position; an existing anchor is inspected rather than replaced",
    ),
    "FIX_ORIGIN": (
        "Fix at Origin",
        "mcad.constraint_action",
        "constraint.fixed",
        "PIVOT_CURSOR",
        "Review fixing this point at sketch-plane (0, 0) mm; connected geometry may move",
    ),
    "REMOVE_RELATION": (
        "Remove Relation",
        "mcad.constraint_action",
        "edit.delete",
        "UNLOCKED",
        "Remove only this selected relation, preserving current solved positions before the next check",
    ),
    "RECOVER_RELATION": (
        "Remove Using Authored Positions",
        "mcad.constraint_action",
        "edit.delete",
        "ERROR",
        "Review removing only this relation without a current solution; preserve authored positions and require a fresh check",
    ),
    "SKETCH_CHECK": (
        "Check Sketch",
        "mcad.general_tool",
        "verify.model",
        "CHECKMARK",
        "Explicitly solve this draft; report real degrees of freedom and conflicts without committing the Part",
    ),
    "CANCEL_CHECK": (
        "Cancel Check",
        "mcad.general_tool",
        "edit.cancel",
        "CANCEL",
        "Cancel the running native check; keep authored geometry and exact raw input for explicit retry",
    ),
    "DIMENSIONS": (
        "Dimensions",
        "mcad.sketch_dimensions",
        "sketch.dimension",
        "DRIVER_DISTANCE",
        "Set the draft width and height as millimetre values or named expressions",
    ),
    "FINISH": (
        "Finish Sketch",
        "mcad.finish_sketch",
        "edit.apply",
        "CHECKMARK",
        "Validate and commit this sketch, then return to Part",
    ),
    "CANCEL": (
        "Cancel Sketch",
        "mcad.cancel_sketch",
        "edit.cancel",
        "CANCEL",
        "Discard the temporary sketch changes; keep the committed design",
    ),
    "EXTRUDE": (
        "Extrude",
        "mcad.add_extrude",
        "feature.extrude",
        "MOD_SOLIDIFY",
        "Extrude a named sketch profile by a specified length",
    ),
    "EXTRUDE_ADD": (
        "Extrude Add",
        "mcad.extrude_boolean",
        "feature.extrude",
        "ADD",
        "Extrude a profile and join it to the base in one operation with editable history",
    ),
    "EXTRUDE_REMOVE": (
        "Extrude Remove",
        "mcad.extrude_boolean",
        "feature.cut",
        "REMOVE",
        "Extrude a cutting profile and remove it from the base in one operation",
    ),
    "HOLE": (
        "Hole", "mcad.round_hole", "feature.cut", "MESH_CIRCLE",
        "Simple or counterbored round hole from an explicit planar face",
    ),
    "CUT": (
        "Cut",
        "mcad.add_cut",
        "feature.cut",
        "MOD_BOOLEAN",
        "Subtract an explicitly selected tool solid from the base solid",
    ),
    "CHECK": (
        "Check Geometry",
        "mcad.check_geometry",
        "verify.model",
        "CHECKMARK",
        "Replay the canonical model and check the exact solid",
    ),
    "ASSEMBLY_NEW": (
        "New Assembly",
        "mcad.assembly_new",
        "assembly.component",
        "OUTLINER_COLLECTION",
        "Capture the working Part as the explicitly grounded first assembly instance",
    ),
    "ASSEMBLY_INSERT": (
        "Insert Instance",
        "mcad.assembly_insert",
        "assembly.instance",
        "DUPLICATE",
        "Reuse a named part with explicit parent, mate frames and joint type",
    ),
    "ASSEMBLY_FRAME": (
        "Mate Frame",
        "mcad.assembly_frame",
        "mate.fixed",
        "ORIENTATION_LOCAL",
        "Create a named literal or associative planar-face mate frame for component connections",
    ),
    "ASSEMBLY_JOINT": (
        "Joint Coordinate",
        "mcad.assembly_joint",
        "mate.revolute",
        "DRIVER_ROTATIONAL_DIFFERENCE",
        "Edit an existing revolute angle or slider distance within explicit motion limits",
    ),
    "ASSEMBLY_CHECK": (
        "Check Assembly",
        "mcad.assembly_check",
        "verify.interference",
        "CHECKMARK",
        "Freshly check the accepted assembly at its saved pose using explicit verification intent",
    ),
    "ASSEMBLY_SAMPLE": (
        "Sample Motion",
        "mcad.assembly_sample",
        "verify.clearance",
        "ACTION",
        "Check only an explicit bounded list of joint coordinates; other joint values stay current",
    ),
    "EXPORT": (
        "Export",
        None,
        "file.export",
        "EXPORT",
        "Export the verified canonical part as STEP or STL",
    ),
}

_SOLID_ACTIONS = {
    "UNION": "union",
    "INTERSECTION": "intersection",
    "REVOLVE": "revolve",
    "FILLET": "fillet",
    "CHAMFER": "chamfer",
    "MIRROR": "mirror",
    "TRANSFORM": "transform",
    "LINEAR_CUT_PATTERN": "linear_cut_pattern",
    "CIRCULAR_CUT_PATTERN": "circular_cut_pattern",
    "LINEAR_PATTERN": "linear_pattern",
    "CIRCULAR_PATTERN": "circular_pattern",
    "SHELL": "shell",
    "LOFT": "loft",
    "SWEEP": "sweep",
    "FACE_RECTANGLE": "sketch_face_rectangle",
    "FACE_CIRCLE": "sketch_face_circle",
}
for _key, _label, _icon_name, _description in (
    (
        "LINEAR_CUT_PATTERN",
        "Linear Hole Pattern",
        "MOD_ARRAY",
        "Repeat a cutting solid along a spacing vector; separated holes remain one final Part",
    ),
    (
        "CIRCULAR_CUT_PATTERN",
        "Circular Hole Pattern",
        "MOD_ARRAY",
        "Repeat a cutting solid around an explicit axis for a bolt circle or radial cuts",
    ),
    (
        "FACE_RECTANGLE",
        "Rectangle on Face",
        "FACESEL",
        "Create an associative rectangle on a named stable planar face; the support follows upstream edits",
    ),
    (
        "FACE_CIRCLE",
        "Circle on Face",
        "MESH_CIRCLE",
        "Create an associative circle on a named stable planar face for a hole or boss",
    ),
    (
        "LOFT",
        "Loft",
        "MOD_SKIN",
        "Build a solid between two named sketch profiles; edit the sections later",
    ),
    (
        "SWEEP",
        "Sweep",
        "MOD_CURVE",
        "Sweep a closed profile along an explicit solved line-chain sketch path",
    ),
    (
        "LINEAR_PATTERN",
        "Linear Pattern",
        "MOD_ARRAY",
        "Repeat and fuse a solid at an editable spacing; copies must remain connected",
    ),
    (
        "CIRCULAR_PATTERN",
        "Circular Pattern",
        "MOD_ARRAY",
        "Repeat and fuse a solid about an explicit axis with an editable angular spacing",
    ),
    (
        "SHELL",
        "Hollow / Shell",
        "MOD_SOLIDIFY",
        "Click a planar opening face and set inward wall thickness",
    ),
    (
        "UNION",
        "Union / Add",
        "MOD_BOOLEAN",
        "Join two touching or overlapping solids into an editable feature",
    ),
    ("INTERSECTION", "Intersection", "MOD_BOOLEAN", "Keep material shared by two solids"),
    (
        "REVOLVE",
        "Revolve",
        "MOD_SCREW",
        "Revolve a sketch profile about an explicit axis; edit the angle later",
    ),
    (
        "FILLET",
        "Fillet",
        "MOD_BEVEL",
        "Round all edges or choose a stable face pair for one edge; impossible blends fail visibly",
    ),
    (
        "CHAMFER",
        "Chamfer",
        "MOD_BEVEL",
        "Bevel all edges or choose a stable face pair for one edge; selection remains explicit",
    ),
    (
        "MIRROR",
        "Mirror Result",
        "MOD_MIRROR",
        "Reflect one solid across an explicit datum plane; no automatic fusion",
    ),
    (
        "TRANSFORM",
        "Move / Rotate",
        "ORIENTATION_GLOBAL",
        "Add an editable rigid transform to a solid in millimetres and degrees",
    ),
):
    _ACTIONS[_key] = (_label, "mcad.add_solid_feature", "feature.extrude", _icon_name, _description)
for _blend in ("FILLET", "CHAMFER"):
    _label, _operator_id, _asset, _glyph, _description = _ACTIONS[_blend]
    _advanced = _blend + "_ADVANCED"
    _SOLID_ACTIONS[_advanced] = _SOLID_ACTIONS[_blend]
    _ACTIONS[_advanced] = (
        _label + " (All / Named Edges)",
        _operator_id,
        _asset,
        _glyph,
        "Choose all edges or named faces through the advanced feature dialog",
    )
    _SOLID_ACTIONS[_blend + "_FACES"] = _SOLID_ACTIONS[_blend]
    _ACTIONS[_blend + "_FACES"] = (
        _label + " (Pick Two Faces)",
        "mcad.pick_blend_faces",
        _asset,
        _glyph,
        "Pick two explicit stable faces sharing exactly one edge",
    )
    _ACTIONS[_blend] = (
        _label,
        "mcad.pick_blend_edge",
        _asset,
        _glyph,
        "Click an exact edge, then enter the blend size; F switches to two faces",
    )

_SOLID_ACTIONS["SHELL_ADVANCED"] = "shell"
_ACTIONS["SHELL_ADVANCED"] = (
    "Shell (Closed / Named Opening)",
    "mcad.add_solid_feature",
    "feature.extrude",
    "MOD_SOLIDIFY",
    "Choose a closed cavity or check one or more stable planar openings",
)
_ACTIONS["SHELL"] = (
    "Shell",
    "mcad.pick_shell_face",
    "feature.extrude",
    "MOD_SOLIDIFY",
    "Click the planar lid to remove, then set wall thickness; choose Closed cavity in the dialog if needed",
)

_ACTIONS["EDIT_FEATURE"] = (
    "Edit Feature",
    "mcad.edit_solid_feature",
    "history.inspect",
    "GREASEPENCIL",
    "Edit the selected history feature's dimensions, formulas, inputs and name",
)
_ACTIONS["NORMAL_VIEW"] = (
    "Normal to Sketch",
    "mcad.sketch_normal_view",
    "history.inspect",
    "AXIS_TOP",
    "Align this viewport to the actual saved sketch plane",
)
for _key, _label, _glyph, _description in (
    (
        "POINT_ON_LINE",
        "Point on Line",
        "SNAP_ON",
        "Constrain a selected point to a line, including its extension",
    ),
    (
        "MIDPOINT",
        "Midpoint",
        "SNAP_ON",
        "Place a selected point exactly halfway along a selected line",
    ),
    (
        "CONCENTRIC",
        "Concentric",
        "MESH_CIRCLE",
        "Keep two circles centred together with independent radii",
    ),
    (
        "CIRCLE_TANGENT",
        "Circle-line Tangent",
        "SNAP_ON",
        "Make a selected circle tangent to a selected supporting line",
    ),
    (
        "COINCIDENT",
        "Coincident",
        "SNAP_ON",
        "Make two selected points share a position; collapsed geometry is rejected",
    ),
    ("PARALLEL", "Parallel", "ALIGN_JUSTIFY", "Keep two selected lines parallel"),
    (
        "PERPENDICULAR",
        "Perpendicular",
        "SNAP_PERPENDICULAR",
        "Keep two selected lines perpendicular",
    ),
    (
        "EQUAL",
        "Equal",
        "ARROW_LEFTRIGHT",
        "Give two selected lines equal lengths or circles equal radii",
    ),
    ("TANGENT", "Tangent", "SNAP_ON", "Make an arc and line tangent at their shared endpoint"),
):
    _ACTIONS[_key] = (
        _label,
        "mcad.constraint_action",
        "constraint.horizontal",
        _glyph,
        _description,
    )

_SKETCH_OPERATOR_ARGS = {
    "FACE_SKETCH_ADVANCED": {"advanced_selection": True},
    "ANGLE": {"mode": "ANGLE"},
    "DIAMETER": {"mode": "DIAMETER"},
    "CONSTRUCTION": {},
    "CORNER_FILLET": {},
    "REMOVE_FILLET": {},
}
_ACTIONS.update(
    {
        "REMOVE_FILLET": (
            "Restore Sharp Corner", "mcad.remove_sketch_fillet", "sketch.general",
            "LOOP_BACK", "Restore the original sharp corner; preserves other corners and refuses conflicting attachments",
        ),
        "CORNER_FILLET": (
            "Sketch Corner Fillet", "mcad.sketch_corner_fillet", "sketch.general",
            "MOD_BEVEL", "Round two selected lines at their shared corner; editable radius and tangent arc, with original corner dimensions retained",
        ),
        "ANGLE": (
            "Angle Dimension",
            "mcad.sketch_numeric_relation",
            "sketch.dimension",
            "DRIVER_ROTATIONAL_DIFFERENCE",
            "Set a driving angle in degrees between two selected lines",
        ),
        "DIAMETER": (
            "Diameter Dimension",
            "mcad.sketch_numeric_relation",
            "sketch.dimension",
            "MESH_CIRCLE",
            "Set the selected circle diameter using its single radius driver",
        ),
        "CONSTRUCTION": (
            "Construction Geometry",
            "mcad.sketch_construction",
            "sketch.line",
            "MOD_WIREFRAME",
            "Toggle selected geometry as a construction reference, excluded from solid profiles",
        ),
        "TRIM": (
            "Trim Line",
            "mcad.general_tool",
            "edit.delete",
            "SCULPTMODE_HLT",
            "Pick the line endpoint to shorten, then a boundary line, circle or arc; preview before applying",
        ),
        "EXTEND": (
            "Extend Line",
            "mcad.general_tool",
            "sketch.line",
            "ARROW_LEFTRIGHT",
            "Pick the line endpoint to extend, then a boundary line, circle or arc; preview before applying",
        ),
        "APPLY_LINE_EDIT": (
            "Apply Line Edit",
            "mcad.general_tool",
            "edit.apply",
            "CHECKMARK",
            "Accept the previewed endpoint edit; constrained or shared endpoints are rejected",
        ),
        "CANCEL_LINE_EDIT": (
            "Cancel Line Edit",
            "mcad.general_tool",
            "edit.cancel",
            "CANCEL",
            "Discard the endpoint edit preview without changing sketch geometry",
        ),
    }
)

_GENERAL_TOOLS = {
    "DRAW_RECTANGLE": "Rectangle",
    "TRIM": "Trim",
    "EXTEND": "Extend",
    "APPLY_LINE_EDIT": "ApplyLineEdit",
    "CANCEL_LINE_EDIT": "CancelLineEdit",
    "SELECT": "Select",
    "POINTS": "Points",
    "LINE": "Line",
    "CIRCLE": "Circle",
    "ARC": "Arc",
    "REVERSE": "Reverse",
    "USE_POINT": "UsePoint",
    "DIMENSION": "Dimension",
    "SKETCH_CHECK": "Check",
    "CANCEL_CHECK": "CancelCheck",
}

_CONSTRAINT_ACTIONS = {
    "POINT_ON_LINE": "point_on_line",
    "MIDPOINT": "midpoint",
    "CONCENTRIC": "concentric",
    "CIRCLE_TANGENT": "circle_line_tangent",
    "COINCIDENT": "coincident",
    "PARALLEL": "parallel",
    "PERPENDICULAR": "perpendicular",
    "EQUAL": "equal",
    "TANGENT": "tangent",
    "HORIZONTAL": "horizontal",
    "VERTICAL": "vertical",
    "FIX_HERE": "fix_here",
    "FIX_ORIGIN": "fix_origin",
    "REMOVE_RELATION": "remove_relation",
    "RECOVER_RELATION": "recover_remove_relation",
}

_GENERAL_PALETTE_TOOLS = (
    "SELECT",
    "POINTS",
    "LINE",
    "DRAW_RECTANGLE",
    "CIRCLE",
    "DIMENSION",
    "ARC",
    "REVERSE",
    "USE_POINT",
    "TRIM",
    "EXTEND",
    "PROJECT",
    "USE_SOLID_EDGE",
)


_PREVIEWS = None
_ASSETS = {}
_REGISTERED = False


def _theme(context):
    # Palette background follows panel theme; pack dark means light glyph ink.
    color = context.preferences.themes[0].user_interface.wcol_regular.inner
    return "dark" if sum(color[:3]) / 3 < 0.5 else "light"


def _icon(context, action):
    # The menu and viewport must identify the same operation. The legacy asset
    # catalog reused "line", "horizontal" and "extrude" for unrelated tools.
    if _PREVIEWS is None:
        return 0
    name = tool_glyphs.ALIASES.get(action, action)
    preview = _PREVIEWS.get(f"tool:{_theme(context)}:{name}")
    return preview.icon_id if preview else 0


def _operator(action):
    identifier = _ACTIONS[action][1]
    if identifier is None:
        return None
    namespace, name = identifier.split(".", 1)
    operator = getattr(getattr(bpy.ops, namespace), name)
    try:
        operator.get_rna_type()
    except KeyError:
        return None
    return operator


def _has_general_tools(draft):
    return callable(getattr(draft, "can_use_tool", None))


def _tool_available(draft, tool):
    return bool(_has_general_tools(draft) and draft.can_use_tool(tool))


def action_reason(context, action):
    """Explain policy rejections from the same complete candidate used by execution."""
    feature_kind = {"NEW": "sketch_constrained", "EXTRUDE": "extrude", "CUT": "cut"}.get(action)
    if feature_kind:
        return operators.feature_action_reason(context, feature_kind)
    if action == "RECTANGLE":
        return operators.part_action_reason(context, "replay", owner_role="rectangle")
    operation = {"CHECK": "check_geometry", "EXPORT": "export_step"}.get(action)
    return operators.part_action_reason(context, operation) if operation else ""


def draw_part_limits(layout, context):
    reason = operators.part_action_reason(context, "canonical_snapshot")
    if reason:
        for line in _panel_wrap(context, reason):
            layout.label(text=line, icon="INFO")
        for line in _panel_wrap(
            context,
            "Snapshots and Assembly capture/update are unavailable for this Part. Ordinary Save remains available.",
        ):
            layout.label(text=line)
        geometry_reason = operators.part_action_reason(context, "check_geometry")
        message = (
            "Geometry Check and STEP/STL are unavailable: " + geometry_reason
            if geometry_reason
            else "Geometry Check and STEP/STL are available for this solid; each action solves and rebuilds it afresh."
        )
        for line in _panel_wrap(context, message):
            layout.label(text=line)


def available(context, action):
    if action not in _ACTIONS or not workspace.is_cad_workspace(context):
        return False
    draft = workspace.active_draft(context)
    if not draft and workspace.suspended_draft(context).get("present"):
        return False
    draft_actions = {
        "PROJECT",
        "USE_SOLID_EDGE",
        "DIMENSIONS",
        "FINISH",
        "CANCEL",
        "NORMAL_VIEW",
        *_GENERAL_TOOLS,
        *_CONSTRAINT_ACTIONS,
        *_SKETCH_OPERATOR_ARGS,
    }
    if draft and action not in draft_actions:
        return False
    if not draft and action in draft_actions:
        return False
    if action in _CONSTRAINT_ACTIONS:
        return constraint_ui.action_available(context, _CONSTRAINT_ACTIONS[action])
    if action in _GENERAL_TOOLS:
        return _tool_available(draft, _GENERAL_TOOLS[action])
    if draft and action == "FINISH" and _has_general_tools(draft):
        return _tool_available(draft, "Finish")
    if action_reason(context, action):
        return False
    if action == "EXPORT":
        return bool(
            getattr(context.scene, "mechanical_cad", None)
            and context.scene.mechanical_cad.document_json
        )
    operator = _operator(action)
    return operator is not None and operator.poll()


def _draft_actions(context):
    draft = workspace.active_draft(context)
    if draft is None:
        return ()
    if _has_general_tools(draft):
        check = "CANCEL_CHECK" if draft.pending is not None else "SKETCH_CHECK"
        contextual = ()
        selection = draft.draft.selection
        if len(selection) == 1:
            kind = selection[0]["kind"]
            if kind == "line":
                contextual = ("HORIZONTAL", "VERTICAL")
            elif kind == "point":
                contextual = ("FIX_HERE", "FIX_ORIGIN")
            elif kind == "constraint":
                contextual = (
                    "REMOVE_RELATION"
                    if draft.commands.has_current_solution
                    else "RECOVER_RELATION",
                )
        if len(selection) == 2:
            contextual = tuple(
                action
                for action in (
                    "COINCIDENT",
                    "PARALLEL",
                    "PERPENDICULAR",
                    "EQUAL",
                    "TANGENT",
                    "POINT_ON_LINE",
                    "MIDPOINT",
                    "CONCENTRIC",
                    "CIRCLE_TANGENT",
                )
                if constraint_ui.action_available(context, _CONSTRAINT_ACTIONS[action])
            )
        if len(selection) == 1 and selection[0]["kind"] in {"line", "circle", "arc"}:
            contextual += ("CONSTRUCTION",)
            if selection[0]["kind"] == "circle":
                contextual += ("DIAMETER",)
        if len(selection) == 1 and selection[0]["kind"] == "arc" and any(
            a["id"] == selection[0]["id"] and "fillet_intent" in a
            for a in draft.commands.sketch.get("arcs", [])
        ):
            contextual += ("REMOVE_FILLET",)
        if len(selection) == 2 and all(item["kind"] == "line" for item in selection):
            contextual += ("ANGLE", "CORNER_FILLET")
        if getattr(draft, "line_edit", None) is not None:
            contextual = ("APPLY_LINE_EDIT", "CANCEL_LINE_EDIT")
        return (
            *_GENERAL_PALETTE_TOOLS,
            *contextual,
            check,
            "FINISH",
            "CANCEL",
        )
    dimensions = ("DIMENSIONS",) if getattr(draft, "can_edit_dimensions", False) else ()
    return dimensions + ("FINISH", "CANCEL")


def palette_actions(context):
    """Keep the first Part tools useful without hiding the complete named menu."""
    if (
        workspace.get_role(context) == "PART"
        and not workspace.has_draft(context)
        and staged_edit.current(context) is None
    ):
        state = context.scene.mechanical_cad
        if compact_status.document_is_fresh(state):
            return ()  # Named New / Open / Import starters are already in the sidebar.
        if compact_status.document_is_empty(state.document_json):
            return ("NEW", "RECTANGLE", "IMPORT")
    return menu_actions(context)


def menu_actions(context):
    role = workspace.get_role(context)
    if role == "ASSEMBLY":
        return (
            "ASSEMBLY_NEW",
            "ASSEMBLY_INSERT",
            "ASSEMBLY_FRAME",
            "ASSEMBLY_JOINT",
            "ASSEMBLY_CHECK",
            "ASSEMBLY_SAMPLE",
        )
    if workspace.active_draft(context):
        return _draft_actions(context)
    if role == "SKETCH":
        return ("NEW", "NEW_FACE_SKETCH", "RECTANGLE", "EDIT")
    if role == "PART":
        return (
            "NEW",
            "NEW_FACE_SKETCH",
            "FACE_RECTANGLE",
            "FACE_CIRCLE",
            "EXTRUDE",
            "EXTRUDE_ADD",
            "EXTRUDE_REMOVE",
            "HOLE",
            "REVOLVE",
            "LOFT",
            "SWEEP",
            "UNION",
            "CUT",
            "INTERSECTION",
            "FILLET",
            "CHAMFER",
            "MIRROR",
            "TRANSFORM",
            "LINEAR_PATTERN",
            "CIRCULAR_PATTERN",
            "LINEAR_CUT_PATTERN",
            "CIRCULAR_CUT_PATTERN",
            "SHELL",
            "EDIT_FEATURE",
            "CHECK",
            "EXPORT",
        )
    return ()


def palette_slots(actions):
    """Reserve five contextual slots in the general palette, without menu spacers.

    ``actions`` is the compact sequence from ``palette_actions``. The general
    tools and the three footer actions retain their positions as selection and
    check state change. Rectangle and other workspace palettes stay compact.
    """
    actions = tuple(actions)
    if actions[: len(_GENERAL_PALETTE_TOOLS)] != _GENERAL_PALETTE_TOOLS:
        return actions
    contextual = actions[len(_GENERAL_PALETTE_TOOLS) : -3]
    return (
        _GENERAL_PALETTE_TOOLS + contextual + (None,) * max(0, 5 - len(contextual)) + actions[-3:]
    )


def palette_layout(actions, region_height, ui_scale=1.0, region_width=None):
    """Fit the full contextual palette without shrinking its native hit targets.

    Slot reservation is selection-independent. Use up to four columns on short
    viewports; keep the final action pair together in multi-column layouts.
    """
    slots = palette_slots(actions)
    if not slots:
        return None
    top = region_height - 132 * ui_scale
    layout = None
    for columns in range(1, 5):
        before_footer = max(0, len(slots) - 2)
        footer_cell = ((before_footer + columns - 1) // columns) * columns
        rows = len(slots) if columns == 1 else footer_cell // columns + 1
        minimum_height = (164 + rows * 42) * ui_scale
        minimum_width = (70 + (columns - 1) * 42) * ui_scale
        if region_height >= minimum_height and (
            region_width is None or region_width >= minimum_width
        ):
            layout = columns, rows, footer_cell
            break
    if layout is None:
        return None  # The named CAD menu remains a last resort for tiny views.
    columns, rows, footer_cell = layout
    bottom = top - (rows * 42 + 12) * ui_scale
    left, right = 8 * ui_scale, (62 + (columns - 1) * 42) * ui_scale
    positions = {}
    for index, action in enumerate(slots):
        if action is None:
            continue
        cell = index
        if columns > 1 and index >= len(slots) - 2:
            cell = footer_cell + index - (len(slots) - 2)
        row, column = divmod(cell, columns)
        positions[action] = (
            (35 + column * 42) * ui_scale,
            top - (27 + row * 42) * ui_scale,
            0,
        )
    return (left, bottom, right, top), positions


def _context_palette_layout(context):
    if not context.area or context.area.type != "VIEW_3D":
        return None
    space = context.area.spaces.active
    if (
        not space.show_gizmo
        or not getattr(space, "show_gizmo_context", True)
        or getattr(space, "show_region_toolbar", False)
    ):
        return None
    region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
    if region is None:
        return None
    return palette_layout(
        palette_actions(context),
        region.height,
        context.preferences.system.ui_scale,
        region.width,
    )


def palette_bounds(context):
    """Window-region pixel coordinates; shared with modal event passthrough."""
    layout = _context_palette_layout(context)
    return layout[0] if layout is not None else None


def is_palette_event(context, event):
    if not context.area or context.area.type != "VIEW_3D":
        return False
    space = context.area.spaces.active
    if not space.show_gizmo:
        return False
    bounds = palette_bounds(context)
    if bounds is None:
        return False
    region = next(r for r in context.area.regions if r.type == "WINDOW")
    x, y = event.mouse_x - region.x, event.mouse_y - region.y
    left, bottom, right, top = bounds
    return left <= x <= right and bottom <= y <= top


class MCAD_OT_open_workspace(bpy.types.Operator):
    bl_idname = "mcad.open_workspace"
    bl_label = "Open CAD Workspaces"
    bl_description = "Open the shared CAD design in Sketch, Part and Assembly workspaces"
    role: EnumProperty(items=[(role, role.title(), "") for role in workspace.ROLES], default="PART")

    @classmethod
    def poll(cls, context):
        return context.window is not None and context.mode == "OBJECT"

    def execute(self, context):
        try:
            workspace.request_workspace(context, self.role)
        except (RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class MCAD_OT_workspace_action(bpy.types.Operator):
    bl_idname = "mcad.workspace_action"
    bl_label = "CAD Tool"
    action: EnumProperty(items=[(key, value[0], value[4]) for key, value in _ACTIONS.items()])

    @classmethod
    def poll(cls, context):
        return workspace.is_cad_workspace(context)

    @classmethod
    def description(cls, context, properties):
        action = properties.action
        detail = action_reason(context, action) or _ACTIONS[action][4]
        return f"{_ACTIONS[action][0]}: {detail}"

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        if not available(context, self.action):
            self.report(
                {"WARNING"},
                action_reason(context, self.action)
                or "This tool is unavailable in the current CAD context",
            )
            return {"CANCELLED"}
        if self.action == "EXPORT":
            result = bpy.ops.wm.call_menu("INVOKE_DEFAULT", name="MCAD_MT_export")
        else:
            properties = (
                {"mode": "ADD" if self.action == "EXTRUDE_ADD" else "REMOVE"}
                if self.action in {"EXTRUDE_ADD", "EXTRUDE_REMOVE"}
                else {"kind": _SOLID_ACTIONS[self.action]}
                if self.action in _SOLID_ACTIONS
                else _SKETCH_OPERATOR_ARGS[self.action]
                if self.action in _SKETCH_OPERATOR_ARGS
                else {"tool": _GENERAL_TOOLS[self.action]}
                if self.action in _GENERAL_TOOLS
                else {"action": _CONSTRAINT_ACTIONS[self.action]}
                if self.action in _CONSTRAINT_ACTIONS
                else {}
            )
            result = _operator(self.action)("INVOKE_DEFAULT", **properties)
        # The invoked operator owns its own modal handler and Undo transaction.
        return {"CANCELLED"} if result == {"CANCELLED"} else {"FINISHED"}


class MCAD_GT_palette_backdrop(bpy.types.Gizmo):
    """Inert flat backing rectangle; native buttons remain the only hit targets."""

    bl_idname = "MCAD_GT_palette_backdrop"

    def setup(self):
        self.shape = self.new_custom_shape(
            "TRIS",
            (
                (0, 0, 0),
                (1, 0, 0),
                (1, 1, 0),
                (0, 0, 0),
                (1, 1, 0),
                (0, 1, 0),
            ),
        )

    def draw(self, context):
        self.draw_custom_shape(self.shape, matrix=self.matrix_basis)

    def test_select(self, context, location):
        return -1


class MCAD_GGT_workspace_palette(bpy.types.GizmoGroup):
    bl_idname = "MCAD_GGT_workspace_palette"
    bl_label = "CAD Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE", "SHOW_MODAL_ALL"}

    @classmethod
    def poll(cls, context):
        return workspace.get_role(context) in {"SKETCH", "PART", "ASSEMBLY"}

    def setup(self, context):
        self.buttons = {}
        self.shape_actions = set()
        for action in _ACTIONS:
            gizmo = self.gizmos.new("GIZMO_GT_button_2d")
            # Original semantic CAD geometry distinguishes tools that previously
            # shared native glyphs. Native buttons still own hit tests/tooltips.
            shape = tool_glyphs.shape(action)
            if shape is not None:
                palette_shapes._validate_payload(shape)
                gizmo.shape = shape
                self.shape_actions.add(action)
            gizmo.draw_options = {"BACKDROP"} if shape is not None else {"BACKDROP", "OUTLINE"}
            gizmo.use_tooltip = True
            gizmo.use_event_handle_all = False
            gizmo.alpha_highlight = 1.0
            gizmo.target_set_operator("mcad.workspace_action").action = action
            self.buttons[action] = gizmo

        self.backdrop = self.gizmos.new("MCAD_GT_palette_backdrop")
        self.backdrop.hide_select = True
        self.backdrop.alpha = 1.0

    def draw_prepare(self, context):
        layout = _context_palette_layout(context)
        if layout is None:
            self.backdrop.hide = True
            for gizmo in self.buttons.values():
                gizmo.hide = True
                gizmo.hide_select = True
            return
        bounds, positions = layout
        left, bottom, right, top = bounds
        color = context.preferences.themes[0].user_interface.wcol_regular.inner
        self.backdrop.hide = False
        self.backdrop.color = tuple(color[:3])
        matrix = Matrix.Diagonal((right - left, top - bottom, 1, 1))
        matrix.translation = (left, bottom, 0)
        self.backdrop.matrix_basis = matrix
        for action, gizmo in self.buttons.items():
            gizmo.hide = action not in positions
            gizmo.hide_select = True
            if gizmo.hide:
                continue
            enabled = available(context, action)
            gizmo.hide_select = not enabled
            gizmo.alpha = 1.0 if enabled else 0.28
            if action not in self.shape_actions:
                gizmo.icon = _ACTIONS[action][3]
            gizmo.color = (0.12, 0.32, 0.50) if action == "FINISH" else (0.12, 0.12, 0.12)
            gizmo.color_highlight = (0.25, 0.48, 0.70)
            gizmo.line_width = (
                0.3 if action in self.shape_actions else 3 if action == "FINISH" else 1
            )
            gizmo.scale_basis = 17
            gizmo.matrix_basis.translation = positions[action]


def _action_button(layout, context, action, text=None):
    row = layout.row(align=True)
    row.enabled = available(context, action)
    kwargs = {"text": text if text is not None else _ACTIONS[action][0]}
    icon = _icon(context, action)
    if icon:
        kwargs["icon_value"] = icon
    else:
        kwargs["icon"] = _ACTIONS[action][3]
    row.operator("mcad.workspace_action", **kwargs).action = action


class MCAD_MT_export(bpy.types.Menu):
    bl_label = "Export CAD Part"

    def draw(self, context):
        for action, label in (("export_step", "STEP"), ("export_stl", "STL")):
            reason = operators.part_action_reason(context, action)
            row = self.layout.row()
            row.enabled = not reason
            row.operator("mcad." + action, text="Export " + label, icon="EXPORT")
        reason = operators.part_action_reason(context, "export_step")
        if reason:
            for line in _panel_wrap(context, reason):
                self.layout.label(text=line, icon="INFO")


class MCAD_MT_workspace(bpy.types.Menu):
    bl_label = "CAD"

    def draw(self, context):
        layout = self.layout
        workspace_view.draw_focus(layout, context)
        layout.operator("mcad.help_browser", text="Search CAD Help", icon="QUESTION")
        layout.separator()
        if workspace.get_role(context) == "ASSEMBLY":
            assembly_ui.draw_assembly_menu(layout, context)
            layout.separator()
            for role in workspace.ROLES:
                layout.operator("mcad.open_workspace", text=role.title()).role = role
            return
        documents = layout.column()
        documents.enabled = not workspace.has_draft(context)
        documents.operator("mcad.new_document", text="New Document", icon="ADD")
        documents.operator("mcad.load_document", text="Open Document", icon="FILE_FOLDER")
        documents.operator("mcad.import_step", text="Import STEP Solid", icon="IMPORT")
        documents.operator("mcad.save_document", text="Save Document", icon="FILE_TICK")
        if not workspace.has_draft(context):
            _action_button(layout, context, "FACE_SKETCH_ADVANCED")
            layout.operator("mcad.copied_face_sketch", text="Sketch on Copied Face Plane (Unlinked)")
        layout.separator()
        reasons = set()
        for action in menu_actions(context):
            _action_button(layout, context, action)
            reason = action_reason(context, action)
            if reason and reason not in reasons:
                reasons.add(reason)
                for line in _panel_wrap(context, reason):
                    layout.label(text=line, icon="INFO")
        # Keep named routes discoverable even when selection hides a direct action.
        if workspace.get_role(context) in {"SKETCH", "PART"}:
            layout.operator("mcad.offset_fixed_sketch_plane", text="Offset Fixed Sketch Plane")
        if workspace.get_role(context) == "SKETCH":
            _action_button(layout, context, "EDIT_FEATURE")
        if workspace.get_role(context) == "PART":
            _action_button(layout, context, "RECTANGLE")
            _action_button(layout, context, "EDIT")
            _action_button(layout, context, "FILLET_FACES")
            _action_button(layout, context, "CHAMFER_FACES")
            _action_button(layout, context, "FILLET_ADVANCED")
            _action_button(layout, context, "CHAMFER_ADVANCED")
            _action_button(layout, context, "SHELL_ADVANCED")
            # Export already has a named action above; do not duplicate it.
            layout.separator()
            _draw_part_view_controls(layout)
        layout.separator()
        for role in workspace.ROLES:
            layout.operator("mcad.open_workspace", text=role.title()).role = role


def _draw_part_view_controls(layout):
    """Expose view-local recovery without changing model or global visibility."""
    layout.operator("mcad.focus_result", text="Focus Part", icon="VIEWZOOM")
    layout.operator("mcad.show_scene", text="Whole Scene", icon="SCENE_DATA")


def _draw_header(self, context):
    if not workspace.is_cad_workspace(context):
        return
    layout = self.layout
    layout.separator()
    draft = workspace.active_draft(context)
    menu_label = "CAD · " + workspace.get_role(context).title()
    if draft and _has_general_tools(draft) and _context_palette_layout(context) is None:
        menu_label += " · Tools"
    layout.menu("MCAD_MT_workspace", text=menu_label)
    workspace_view.draw_focus(layout, context, compact=True)
    if draft:
        for action in _draft_actions(context):
            if action in {"DIMENSIONS", "FINISH", "CANCEL"}:
                _action_button(layout, context, action)


def _status_tool(layout, context, label, tool, icon="NONE"):
    row = layout.row(align=True)
    row.enabled = _tool_available(workspace.active_draft(context), tool)
    row.operator("mcad.general_tool", text=label, icon=icon).tool = tool


def _draw_draft_completion(layout, context):
    """Named sidebar fallback stays reachable even when header/palette is clipped."""
    actions = _draft_actions(context)
    if "DIMENSIONS" in actions:
        _action_button(layout, context, "DIMENSIONS")
    row = layout.row(align=True)
    for action, label in (("FINISH", "Finish Sketch"), ("CANCEL", "Cancel")):
        if action in actions:
            _action_button(row, context, action, text=label)


def _draw_pending_length_status(layout, context, owner):
    """One contextual sidebar, not a second copy of the active text field."""
    pending = owner.draft.pending_length
    controller = owner.input_controller
    editing = controller is not None and not controller.closed
    layout.label(text="Unfinished Line" if editing else "Length input retained", icon="INFO")
    if not editing:
        raw = repr(pending["raw_text"])
        preview = raw if len(raw) <= 160 else raw[:159] + "…"
        for line in _panel_wrap(context, "Length: " + preview):
            layout.label(text=line)
        if pending["axis"]:
            layout.label(text=pending["axis"].title() + " retained")
    row = layout.row(align=True)
    if not editing:
        _status_tool(row, context, "Reopen Length", "Reopen", "GREASEPENCIL")
    _status_tool(row, context, "Back to Line" if editing else "Cancel Length", "CancelInput", "BACK")
    if owner.can_use_tool("CancelProposal"):
        _status_tool(row if editing else layout, context, "Discard Line", "CancelProposal", "CANCEL")


def _draw_pending_diameter_status(layout, context, owner):
    """One contextual sidebar, not a second copy of the active text field."""
    pending = owner.draft.pending_diameter
    controller = owner.input_controller
    editing = controller is not None and not controller.closed
    layout.label(text="Unfinished Circle" if editing else "Diameter input retained", icon="INFO")
    if not editing:
        raw = repr(pending["raw_text"])
        preview = raw if len(raw) <= 160 else raw[:159] + "…"
        for line in _panel_wrap(context, "Diameter: " + preview):
            layout.label(text=line)
    row = layout.row(align=True)
    if not editing:
        _status_tool(row, context, "Reopen Diameter", "Reopen", "GREASEPENCIL")
    _status_tool(row, context, "Back to Circle" if editing else "Cancel Diameter", "CancelInput", "BACK")
    if owner.can_use_tool("CancelProposal"):
        _status_tool(row if editing else layout, context, "Discard Circle", "CancelProposal", "CANCEL")


def _draw_general_status(layout, context, owner):
    """Concise draft information inside the existing right-side history panel."""
    row = layout.row(align=True)
    tool = (
        "Select Points"
        if owner.draft.tool == "Select" and owner.selection_mode == "point"
        else owner.draft.tool
    )
    row.label(text="Line / Circle / Arc · " + tool, icon="CURVE_DATA")
    row.operator("mcad.help", text="", icon="QUESTION").topic = "sketch.general"
    layout.operator("mcad.sketch_normal_view", text="View Normal to Sketch", icon="AXIS_TOP")
    response = owner.current_solution_response()
    attempt = owner.current_build_failure
    data = response["result"]["sketch"] if response is not None else None
    readiness = response["result"].get("profile_check") if response is not None else None
    diagnostics = owner.current_diagnostics if data is None else None
    status_report = data if data is not None else (
        {"status": diagnostics.solver_status} if diagnostics is not None else None
    )
    label, icon = compact_status.sketch_label(status_report, pending=owner.pending is not None)
    layout.label(text=label, icon=icon)
    label, icon = compact_status.profile_label(readiness, pending=owner.pending is not None)
    layout.label(text=label, icon=icon)
    if attempt is not None:
        layout.label(text="Build failed · draft retained", icon="ERROR")
        if attempt.failed_features:
            identifier, code, detail = attempt.failed_features[0]
            for line in _panel_wrap(context, compact_status.summary(f"{identifier}: {detail}")):
                layout.label(text=line)
    if response is None and getattr(owner, "retained_outline", None) is not None:
        layout.label(text="Stale outline · last good sketch", icon="ERROR")
    if owner.draft.pending_length is not None:
        _draw_pending_length_status(layout, context, owner)
    elif owner.draft.pending_diameter is not None:
        _draw_pending_diameter_status(layout, context, owner)
    elif owner.draft.proposal:
        row = layout.row(align=True)
        _status_tool(row, context, "Continue", "Continue", "PLAY")
        _status_tool(row, context, "Cancel Proposal", "CancelProposal", "CANCEL")
    if owner.commands.pending_edit:
        layout.label(text="Exact dimension input retained; not accepted", icon="INFO")
        raw = repr(owner.commands.pending_edit.raw_text)
        preview = raw if len(raw) <= 160 else raw[:159] + "…"
        for line in _panel_wrap(context, "Input: " + preview):
            layout.label(text=line)
        row = layout.row(align=True)
        _status_tool(row, context, "Reopen Input", "Reopen", "GREASEPENCIL")
        _status_tool(row, context, "Cancel Input", "CancelInput", "CANCEL")
    if owner.error:
        for line in _panel_wrap(context, compact_status.summary(owner.error)):
            layout.label(text=line, icon="ERROR")
        _diagnostic_button(layout, owner.error)
    if owner.annotation_notice:
        layout.label(text=compact_status.summary(owner.annotation_notice, 56), icon="INFO")
    if owner.draft.pending_length is None and owner.draft.pending_diameter is None:
        constraint_ui.draw_inspector(layout, context, owner)
    state = context.scene.mechanical_cad
    if compact_status.disclosure(layout, state, "show_sketch_details", "Sketch details"):
        details = layout.box()
        retired = owner.draft.retired_annotation_ids
        if retired:
            details.label(text=f"{len(retired)} retired radius label(s) retained", icon="INFO")
            for line in _panel_wrap(context, "Restore Sharp Corner removed these dimensions. Their label placement is retained for Undo."):
                details.label(text=line)
        if data is not None:
            details.label(text="Native solve: " + str(data.get("status", "unknown")))
            for field in ("failed_constraints", "redundant_constraints"):
                if data.get(field):
                    prefix = "Redundancy candidates" if field == "failed_constraints" else "Redundant constraints"
                    for line in _panel_wrap(context, prefix + ": " + ", ".join(data[field])):
                        details.label(text=line, icon="INFO")
        if readiness is not None and not readiness.get("ready"):
            for line in _panel_wrap(context, (readiness.get("error") or {}).get("message", "Review the profile boundary.")):
                details.label(text=line)
        if attempt is not None:
            details.label(text=f"Trial solve: {attempt.remaining_dof} DoF · {attempt.solver_status}")
            for identifier, code, detail in attempt.failed_features:
                for line in _panel_wrap(context, f"{identifier} · {code}: {detail}"):
                    details.label(text=line)
        else:
            details.label(text="Downstream build: " + owner.current_native_build_status)
        for message in (owner.annotation_notice, owner.error or owner.message):
            for line in _panel_wrap(context, message):
                details.label(text=line)
        details.label(text="Esc suspends · Ctrl-Z local history")
        for line in _panel_wrap(context, "Switching workspaces saves this draft. Return to Sketch and choose Resume."):
            details.label(text=line)


def _draw_selected_history_edit(layout, context):
    """Choose by feature family, never by transient poll/replay readiness."""
    from .solid_feature_edit import FEATURE_FIELDS

    state = context.scene.mechanical_cad
    if not 0 <= state.feature_index < len(state.features):
        return
    feature = state.features[state.feature_index]
    row = layout.row(align=True)
    row.label(text="Selected: " + feature.label)
    row.operator("mcad.rename_history_feature", text="", icon="FONT_DATA")
    if feature.kind == "sketch_constrained":
        _action_button(layout, context, "EDIT", text="Edit Sketch")
    elif feature.kind in FEATURE_FIELDS:
        _action_button(layout, context, "EDIT_FEATURE", text="Edit Feature")
    row = layout.row(align=True)
    row.operator("mcad.activate_feature", text="Display Selected", icon="HIDE_OFF")
    row.operator("mcad.remove_history_feature", text="", icon="TRASH")
    # Keep linked/projected constrained sketches visible with the operator's
    # guarded poll explanation; primitives use their dimension editor instead.
    if feature.kind == "sketch_constrained":
        layout.operator("mcad.offset_fixed_sketch_plane", text="Offset Fixed Sketch Plane")


def _draw_selected_sketch_extrude(layout, context, presentation):
    """One existing Extrude dialog, with the selected sketch explicitly bound."""
    state = context.scene.mechanical_cad
    if not 0 <= state.feature_index < len(state.features):
        return
    feature = state.features[state.feature_index]
    if not feature.kind.startswith("sketch_"):
        return
    detail = presentation.selected_detail(context, feature.feature_id)
    ready, message, icon = (
        detail.profile_state if detail is not None
        else (False, "Rebuild to check the sketch profile", "INFO")
    )
    reason = operators.feature_action_reason(context, "extrude", profile=feature.feature_id)
    if reason:
        ready, message, icon = False, reason, "INFO"
    row = layout.row(align=True)
    row.enabled = ready and available(context, "EXTRUDE")
    row.operator_context = "INVOKE_DEFAULT"
    op = row.operator("mcad.add_extrude", text="Extrude Selected Sketch", icon="MOD_SOLIDIFY")
    op.enter_part_after_apply = workspace.get_role(context) == "SKETCH"
    # Do not assign an excluded dynamic-enum value to a disabled button.
    if not reason:
        op.profile = feature.feature_id
    for index, line in enumerate(_panel_wrap(context, message)):
        layout.label(text=line, icon=icon if index == 0 else "NONE")


class MCAD_PT_workspace_history(bpy.types.Panel):
    bl_label = "Feature History"
    bl_idname = "MCAD_PT_workspace_history"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CAD"

    @classmethod
    def poll(cls, context):
        return workspace.is_cad_workspace(context)

    def draw(self, context):
        layout = self.layout
        state = context.scene.mechanical_cad
        role = workspace.get_role(context)
        draft = workspace.active_draft(context)
        toolbar = layout.row(align=True)
        toolbar.menu("MCAD_MT_workspace", text="Tools & Document")
        workspace_view.draw_focus(toolbar, context)
        assembly_job_ui.draw_backend_failure(layout, context)
        notice = getattr(state, "sketch_notice", "")
        if notice:
            box = layout.box()
            for index, line in enumerate(_panel_wrap(context, notice)):
                box.label(text=line, icon="INFO" if index == 0 else "NONE")
        draw_suspended_draft(layout, context)
        if role == "ASSEMBLY":
            assembly_ui.draw_assembly_history(layout, context)
            return
        if not state.document_json:
            layout.operator("mcad.new_document", text="New CAD Document", icon="ADD")
            layout.operator("mcad.load_document", text="Open CAD Document", icon="FILE_FOLDER")
            layout.operator("mcad.import_step", text="Import STEP Solid", icon="IMPORT")
            return
        layout.label(text=state.document_name)
        proposed = draw_staged_edit(layout, context)
        empty_document = compact_status.document_is_empty(state.document_json)
        if empty_document and not workspace.has_draft(context) and not proposed:
            row = layout.row(align=True)
            _action_button(row, context, "NEW", text="New Sketch")
            _action_button(row, context, "RECTANGLE", text="XY Rectangle")
            _action_button(layout, context, "IMPORT", text="Import STEP")
        # Primary edit launchers stay above the variable-height history/details.
        if not draft and not empty_document and role in {"SKETCH", "PART"}:
            _draw_selected_history_edit(layout, context)
            if staged_edit.current(context) is None:
                draw_projection_repair(layout, context)
        from .feature_history_draw import capture_presentation, draw_history

        presentation = capture_presentation(context)
        if role in {"SKETCH", "PART"} and not workspace.has_draft(context) and not proposed:
            _draw_selected_sketch_extrude(layout, context, presentation)
        if not presentation.is_current(context):
            from .history_rebuild import draw_cancel

            box = layout.box()
            box.alert = state.status == "FAILED"
            status = "UNVERIFIED" if state.status == "READY" else state.status
            compact = workspace_view.compact_draft_part_status(state, draft)
            if compact:
                row = box.row(align=True)
                row.label(text="Part: " + compact_status.part_state_text("DIRTY"), icon="INFO")
                details = row.operator("mcad.help", text="", icon="QUESTION")
                details.topic = "error.details"
                details.detail = (
                    "The current sketch draft is shown separately. The committed Part "
                    "needs rebuilding; this status does not describe the draft solve. "
                    "Finish Sketch saves the draft and rebuilds its dependents."
                )
                if not draw_cancel(box, context):
                    row.operator("mcad.regenerate", text="", icon="FILE_REFRESH")
            else:
                box.label(text="Part: " + compact_status.part_state_text(status), icon="ERROR" if box.alert else "INFO")
                if state.status == "FAILED":
                    box.label(text="Any visible Part is stale / last-good", icon="ERROR")
                if draft:
                    box.label(text="Current draft is shown separately")
                if state.error:
                    for line in _panel_wrap(context, compact_status.summary(state.error)):
                        box.label(text=line)
                    _diagnostic_button(box, state.error, failed=state.status == "FAILED")
                if not draw_cancel(box, context):
                    box.operator("mcad.regenerate", text="Rebuild", icon="FILE_REFRESH")
        else:
            layout.label(
                text="Empty document" if empty_document else "Build: Up to date",
                icon="INFO" if empty_document else "CHECKMARK",
            )
        draw_history(
            layout, context, "cad_history", rows=min(7, max(2, len(state.features))),
            presentation=presentation,
        )
        from .support_intent_ui import draw_support_intent

        if not proposed:
            draw_support_intent(layout, context, presentation=presentation)
        # The committed cache still matches document_json while a draft exists,
        # but it does not describe that draft. Only the viewport's draft report
        # may claim a current degree-of-freedom count during editing.
        if not workspace.has_draft(context) and 0 <= state.feature_index < len(state.features):
            feature = state.features[state.feature_index]
            if getattr(feature, "sketch_report_json", ""):
                selected = presentation.selected_detail(context, feature.feature_id)
                if selected is not None and selected.sketch_label is not None:
                    label, icon = selected.sketch_label
                    layout.label(text=label, icon=icon)
                    if compact_status.disclosure(layout, state, "show_sketch_details", "Sketch details"):
                        if selected.failed_detail:
                            for line in _panel_wrap(context, selected.failed_detail):
                                layout.label(text=line, icon=selected.failed_detail_icon)
                        if selected.redundant_detail:
                            for line in _panel_wrap(context, selected.redundant_detail):
                                layout.label(text=line, icon="INFO")
                else:
                    layout.label(text="Sketch solve needs verification", icon="INFO")
        if workspace._LAST_ERROR:
            for line in _panel_wrap(context, workspace._LAST_ERROR):
                layout.label(text=line, icon="ERROR")
        if draft:
            # Complete/cancel before variable-height relations and reports. The
            # header can be clipped and the palette can be hidden independently.
            _draw_draft_completion(layout, context)
            if _has_general_tools(draft):
                _draw_general_status(layout, context, draft)
            else:
                layout.label(text="Editing rectangle · mm", icon="EDITMODE_HLT")
        if role == "PART":
            if operators.part_action_reason(context, "canonical_snapshot"):
                layout.label(text="Snapshot / Assembly unavailable", icon="INFO")
            _draw_part_view_controls(layout.row(align=True))
            row = layout.row(align=True)
            _action_button(row, context, "CHECK", text="Check")
            row.menu("MCAD_MT_export", text="Export", icon="EXPORT")
            label, icon = compact_status.geometry_label(
                state.geometry_status,
                current=document_state.geometry_report_is_current(context),
            )
            geometry_row = layout.row(align=True)
            geometry_row.label(text=label, icon=icon)
            _help_button(geometry_row, "verification.geometry")
            if compact_status.disclosure(layout, state, "show_part_details", "Part details"):
                draw_part_limits(layout, context)
                for line in _panel_wrap(context, state.geometry_message):
                    layout.label(text=line)
        if state.last_action_error and not pending_message_is_duplicate(
            context, state.last_action_error
        ):
            box = layout.box()
            box.alert = True
            for line in _panel_wrap(context, compact_status.summary(state.last_action_error)):
                box.label(text=line)
            _diagnostic_button(box, state.last_action_error)


class MCAD_OT_copy_parameter_name(bpy.types.Operator):
    bl_idname = "mcad.copy_parameter_name"
    bl_label = "Copy Parameter Name"
    bl_description = "Copy the exact symbol to use in a dimension formula"
    parameter_name: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        try:
            document = json.loads(context.scene.mechanical_cad.document_json)
        except (ValueError, TypeError):
            self.report({"WARNING"}, "Open a CAD document first")
            return {"CANCELLED"}
        if self.parameter_name not in document.get("parameters", {}):
            self.report({"WARNING"}, "This parameter no longer exists")
            return {"CANCELLED"}
        context.window_manager.clipboard = self.parameter_name
        self.report({"INFO"}, "Parameter name copied")
        return {"FINISHED"}


class MCAD_PT_workspace_parameters(bpy.types.Panel):
    bl_label = "Named Parameters"
    bl_parent_id = "MCAD_PT_workspace_history"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CAD"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return workspace.get_role(context) in {"SKETCH", "PART"}

    def draw(self, context):
        state = context.scene.mechanical_cad
        editable = (
            not workspace.has_draft(context)
            and not document_state.has_staged_edit(context)
            and not document_state._REPLAY_RUNNING
            and not execution_lease.is_busy()
        )
        controls = self.layout.row()
        controls.enabled = editable
        controls.operator("mcad.named_parameter", text="Add / Set Parameter", icon="ADD")
        try:
            document = json.loads(state.document_json)
        except (ValueError, TypeError):
            document = {}
        for parameter in state.parameters:
            box = self.layout.box()
            for line in _panel_wrap(context, parameter.key):
                box.label(text=line)
            row = box.row(align=True)
            value_row = row.row(align=True)
            value_row.enabled = editable
            value_row.prop(parameter, "expression" if parameter.is_expression else "value", text="")
            value_row.prop(parameter, "is_expression", text="", icon="DRIVER")
            row.operator(
                "mcad.copy_parameter_name", text="", icon="COPYDOWN"
            ).parameter_name = parameter.key
            usage = parameter_usage(document, parameter.key)
            note = "; ".join(usage) if usage else "Not used by the current features or parameters"
            for line in _panel_wrap(context, note):
                box.label(text=line, icon="INFO" if not usage else "NONE")


def draw_suspended_draft(layout, context):
    """Recovery controls remain discoverable even outside the owning workspace."""
    recovery = workspace.draft_recovery_notice()
    if recovery:
        box = layout.box()
        for index, line in enumerate(_panel_wrap(context, recovery)):
            box.label(text=line, icon="ERROR" if index == 0 else "NONE")
    saved = workspace.suspended_draft(context)
    if not saved.get("present") or workspace.active_draft(context):
        return
    box = layout.box()
    box.alert = not saved.get("compatible")
    box.label(text="Saved sketch draft", icon="RECOVER_LAST")
    for line in _panel_wrap(context, saved.get("message", "Resume or discard this draft.")):
        box.label(text=line)
    if workspace.get_role(context) == "SKETCH":
        row = box.row()
        row.enabled = bool(saved.get("compatible") and saved.get("editor_available"))
        row.operator("mcad.resume_sketch", text="Resume", icon="PLAY")
    else:
        box.operator("mcad.open_workspace", text="Return to Sketch").role = "SKETCH"
    box.operator("mcad.discard_suspended_sketch", text="Discard Draft", icon="TRASH")


CLASSES = (
    workspace_view.MCAD_OT_focus_workspace,
    MCAD_OT_open_workspace,
    MCAD_OT_workspace_action,
    MCAD_GT_palette_backdrop,
    MCAD_GGT_workspace_palette,
    MCAD_MT_export,
    MCAD_MT_workspace,
    MCAD_PT_workspace_history,
    MCAD_OT_copy_parameter_name,
    MCAD_PT_workspace_parameters,
)


def register():
    global _PREVIEWS, _REGISTERED, _ASSETS
    if _REGISTERED:
        return
    root = Path(__file__).resolve().parent / "assets" / "icons"
    manifest = root / "manifest.json"
    _ASSETS = (
        {item["action_id"]: item for item in json.loads(manifest.read_text())["assets"]}
        if manifest.is_file()
        else {}
    )
    _PREVIEWS = bpy.utils.previews.new()
    for theme in ("dark", "light"):
        for action_id in {spec[2] for spec in _ACTIONS.values()}:
            asset = _ASSETS.get(action_id)
            if asset:
                path = root / asset["png"][theme]["48"]
                if path.is_file():
                    _PREVIEWS.load(f"{theme}:{action_id}", str(path), "IMAGE")
    glyph_root = root.parent / "tool_glyphs"
    for theme in ("dark", "light"):
        for action in tool_glyphs.STROKES:
            path = glyph_root / theme / f"{action}.png"
            if path.is_file():
                _PREVIEWS.load(f"tool:{theme}:{action}", str(path), "IMAGE")
    registered = []
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.types.VIEW3D_HT_header.append(_draw_header)
        _REGISTERED = True
    except Exception:
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
        bpy.utils.previews.remove(_PREVIEWS)
        _PREVIEWS = None
        raise


def unregister():
    global _PREVIEWS, _REGISTERED
    if _REGISTERED:
        bpy.types.VIEW3D_HT_header.remove(_draw_header)
        for cls in reversed(CLASSES):
            bpy.utils.unregister_class(cls)
    if _PREVIEWS is not None:
        bpy.utils.previews.remove(_PREVIEWS)
        _PREVIEWS = None
    _REGISTERED = False
