"""Explicit native constraint controls using the existing general-sketch owner.

The popup retains a single prepared action across confirmation. UI selection uses
an independent wrapper over the *same* command draft, so it cannot drop current
solver evidence, replay history, or acquire a native execution lease. This module
owns no lifecycle handlers, timers, geometry caches, or command implementation.
"""

import copy
import math
import textwrap

from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import constraint_actions, constraint_selection, draft_dispatch, sketch_session
from .general_session import DraftError, GeneralSession

PAGE_SIZE = 6
ACTION_ITEMS = (
    ("symmetry", "Symmetry", "Mirror two points across a selected straight axis line"),
    ("coincident", "Coincident", "Join exactly two selected points; connected geometry may move"),
    (
        "point_on_line",
        "Point on line",
        "Place a selected point on a line's infinite supporting line",
    ),
    (
        "midpoint",
        "Midpoint",
        "Place a selected point halfway between the selected line's endpoints",
    ),
    (
        "concentric",
        "Concentric circles",
        "Keep two selected circles centered together, with independent radii",
    ),
    (
        "circle_line_tangent",
        "Circle-line tangent",
        "Make a circle tangent to a line's infinite supporting line",
    ),
    ("parallel", "Parallel", "Keep two selected lines parallel"),
    ("perpendicular", "Perpendicular", "Keep two selected lines at a right angle"),
    ("equal", "Equal", "Make two lines equal in length or two circles equal in radius"),
    ("tangent", "Tangent", "Make an arc and line tangent at their explicitly shared endpoint"),
    (
        "horizontal",
        "Horizontal",
        "Constrain the selected line horizontally, or inspect its existing relation",
    ),
    (
        "vertical",
        "Vertical",
        "Constrain the selected line vertically, or inspect its existing relation",
    ),
    (
        "fix_here",
        "Fix here",
        "Anchor the selected point at its current validated solved coordinates",
    ),
    (
        "fix_origin",
        "Fix at origin",
        "Explicitly anchor this point at sketch-plane (0, 0); geometry may move",
    ),
    (
        "remove_relation",
        "Remove relation",
        "Release only the selected relation using current solved positions",
    ),
    (
        "recover_remove_relation",
        "Remove using authored positions",
        "Remove only this relation without a current solution; authored positions are retained",
    ),
)


def active(context=None):
    owner = sketch_session.active_session(context)
    return owner if type(owner) is GeneralSession else None


def _require_ui_idle(owner, context=None):
    if type(owner) is not GeneralSession or active(context) is not owner:
        raise DraftError("Choose the active general sketch in its original window and scene.")
    owner._require_idle()
    if context is not None and (
        context.area != owner.area
        or context.workspace != owner.workspace
        or context.view_layer != owner.window.view_layer
    ):
        raise DraftError("Use the original sketch viewport for this selection or action.")
    if owner.commands.pending_edit is not None:
        raise DraftError("Accept or cancel the retained dimension text first.")
    if owner.draft.proposal is not None or owner.proposal_capture:
        raise DraftError("Continue or cancel the unfinished line, circle or arc first.")
    if (
        owner.annotation_drag is not None
        or owner.publication is not None
        or getattr(owner, "gesture_intent", None) is not None
    ):
        raise DraftError("Finish the active sketch gesture or publication first.")


def select_bindings(owner, targets, *, context=None):
    """Checkpoint exact UI identities atomically without replacing command state.

    A shallow wrapper copy is intentional: ``select`` validates into a detached
    UI payload, while the original command object and its evidence remain owned
    by this same session. No field of the original wrapper is changed on failure.
    """
    _require_ui_idle(owner, context)
    original = owner.draft
    candidate = copy.copy(original)
    if not candidate.select(targets):
        return False
    draft_dispatch.dumps(candidate)
    owner.draft = candidate
    try:
        owner.checkpoint()
    except Exception:
        owner.draft = original
        raise
    sketch_session._tag_redraw(owner)
    return True


def action_available(context, action):
    """Cheap display hint only; invocation and Apply still prepare exact bindings."""
    owner = active(context)
    try:
        _require_ui_idle(owner, context)
        return constraint_selection.applicability_hint(
            owner.commands.sketch,
            owner.draft.selection,
            action,
            has_solution=(
                owner.commands.has_current_solution
                if action in {"fix_here", "remove_relation", "recover_remove_relation"}
                else False
            ),
            has_retained_evidence=(
                owner.evidence_request is not None or owner.evidence_response is not None
            ),
        )
    except (ValueError, TypeError, KeyError, AttributeError, ReferenceError):
        return False


def _error(operator, exc):
    operator.report({"WARNING"}, str(exc))
    return {"CANCELLED"}


def _clear_intent(operator):
    operator._prepared_intent = None
    operator._prepared_owner = None
    operator._confirmation_pending = False


def _publish_annotation_ui(owner, candidate):
    """Keep the command owner and current native evidence during a UI-only edit."""
    original = owner.draft
    draft_dispatch.dumps(candidate)
    owner.draft = candidate
    try:
        owner.checkpoint()
    except Exception:
        owner.draft = original
        raise
    owner.error = ""
    sketch_session._tag_redraw(owner)


class MCAD_OT_sketch_reference_dimension(Operator):
    bl_idname = "mcad.sketch_reference_dimension"
    bl_label = "Add Reference Dimension"
    bl_description = "Add a read-only measured label without a solver constraint; Remove Reference removes it, local Undo edits geometry"
    mode: EnumProperty(
        items=[
            ("length", "Length", "Selected line length"),
            ("radius", "Radius", "Selected circle/arc radius"),
            ("diameter", "Diameter", "Selected circle/arc supporting-circle diameter"),
        ]
    )

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def execute(self, context):
        from .reference_dimensions import READ_ONLY_MESSAGE

        try:
            owner = active(context)
            _require_ui_idle(owner, context)
            selected = owner.draft.selection
            if len(selected) != 1:
                raise DraftError("Select exactly one authored line, circle or arc.")
            kind, identifier = selected[0]["kind"], selected[0]["id"]
            if (self.mode == "length" and kind != "line") or (
                self.mode != "length" and kind not in {"circle", "arc"}
            ):
                raise DraftError(
                    "Select a line for length, or a circle/arc for radius or diameter."
                )
            candidate = copy.copy(owner.draft)
            offset = (
                (0, 8) if self.mode == "length" else (8, -8) if self.mode == "diameter" else (8, 8)
            )
            _, changed = candidate.place_reference(self.mode, kind, identifier, offset)
            if changed:
                _publish_annotation_ui(owner, candidate)
            owner.message = READ_ONLY_MESSAGE + (
                " Reference already exists." if not changed else ""
            )
            return {"FINISHED"}
        except (ValueError, TypeError, KeyError, AttributeError, ReferenceError) as exc:
            return _error(self, exc)


class MCAD_OT_remove_reference_dimension(Operator):
    bl_idname = "mcad.remove_reference_dimension"
    bl_label = "Remove Reference"
    bl_description = "Remove only this read-only measurement label; geometry and solver constraints stay unchanged"
    annotation_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def execute(self, context):
        from .reference_dimensions import is_reference

        try:
            owner = active(context)
            _require_ui_idle(owner, context)
            if not is_reference(owner.draft.annotations.get(self.annotation_id)):
                raise DraftError("Choose an existing reference measurement label.")
            candidate = copy.copy(owner.draft)
            candidate.remove_annotation(self.annotation_id)
            _publish_annotation_ui(owner, candidate)
            owner.message = "Reference label removed; geometry and constraints unchanged."
            return {"FINISHED"}
        except (ValueError, TypeError, KeyError, AttributeError, ReferenceError) as exc:
            return _error(self, exc)


def _diameter_display_text(source):
    """Presentation only: numeric radius text is a number, not a new formula.

    Do not evaluate arithmetic or parameter names. The dialog keeps its exact
    initial text and original source binding so unchanged Apply is a true no-op.
    """
    if type(source) in (int, float):
        return str(2 * source)
    try:
        literal = float(source)
    except (ValueError, TypeError, OverflowError):
        pass
    else:
        if math.isfinite(literal) and math.isfinite(2 * literal):
            return str(2 * literal)
    return "2*(" + source + ")"


def _diameter_radius_value(raw):
    # Newly entered full numeric literals need no symbolic wrapper. Arithmetic
    # and parameter expressions remain exact, explicitly divided by two.
    if type(raw) is not str:
        return raw / 2
    if not raw.isascii():
        return "(" + raw + ")/2"
    try:
        literal = float(raw)
    except (ValueError, OverflowError):
        pass
    else:
        if math.isfinite(literal):
            return literal / 2
    return "(" + raw + ")/2"


class MCAD_OT_sketch_numeric_relation(Operator):
    bl_idname = "mcad.sketch_numeric_relation"
    bl_label = "Set sketch dimension"
    bl_description = (
        "Enter a driving angle in degrees or a diameter in millimetres, including formulas"
    )
    bl_options = {"INTERNAL"}

    mode: EnumProperty(
        items=(
            ("ANGLE", "Angle", "Degrees between directed lines"),
            ("DIAMETER", "Diameter", "Circle or arc diameter in millimetres"),
        )
    )
    constraint_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    value: StringProperty(
        name="Value",
        description="Length literals accept mm/cm/m/in/ft; angle literals accept deg/rad; formulas keep existing units",
        # A maximum-length canonical radius formula needs four extra display
        # characters for 2*(...). Unchanged Apply must not truncate/rewrite it.
        # Changed input still passes the existing bounded canonical validators.
        maxlen=512,
    )

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def invoke(self, context, event):
        try:
            owner = active(context)
            _require_ui_idle(owner, context)
            # Annotation activation supplies the exact driver identity without
            # changing the user's selection. Ordinary inspector calls retain
            # their existing selection contract.
            target = getattr(self, "constraint_id", "")
            selection = (
                ({"kind": "constraint", "id": target},) if target else owner.draft.selection
            )
            contract = constraint_selection.selection_contract(owner.commands.sketch, selection)
            selected = contract.selection
            kind = "angle" if self.mode == "ANGLE" else "radius"
            relation = None
            if len(selected) == 1 and selected[0].kind == "constraint":
                relation = next((item for item in contract.relations if item.kind == kind), None)
                if relation is None:
                    raise DraftError("Select the matching angle or radius relation.")
                refs = relation.refs
            else:
                if self.mode == "ANGLE":
                    if len(selected) != 2 or any(item.kind != "line" for item in selected):
                        raise DraftError("Shift-select two lines to set their angle.")
                elif len(selected) != 1 or selected[0].kind not in {"circle", "arc"}:
                    raise DraftError("Select one circle or arc to set its diameter.")
                refs = tuple(item.id for item in selected)
                matches = [
                    item
                    for item in constraint_selection.relation_descriptors(owner.commands.sketch)
                    if item.kind == kind and set(item.refs) == set(refs)
                ]
                if len(matches) > 1:
                    raise DraftError(
                        "Multiple driving relations exist. Select the exact relation in the inspector."
                    )
                relation = matches[0] if matches else None
            self._owner = owner
            self._binding = constraint_actions._binding(owner)
            self._refs = refs
            self._relation_id = relation.id if relation else None
            if relation:
                source = relation.source_value
                self.value = (
                    str(source)
                    if self.mode == "ANGLE"
                    else _diameter_display_text(source)
                )
            elif self.mode == "ANGLE":
                self.value = "90"
            else:
                curve = next(
                    (
                        item
                        for item in owner.commands.sketch.get("circles", [])
                        if item["id"] == refs[0]
                    ),
                    None,
                )
                self.value = str(2 * curve["radius"]) if curve else "10"
            self._initial_text = self.value
            return context.window_manager.invoke_props_dialog(self)
        except Exception as exc:
            return _error(self, exc)

    def draw(self, context):
        self.layout.label(
            text="Angle (degrees, >0 to 180)" if self.mode == "ANGLE" else "Diameter (mm)"
        )
        self.layout.prop(self, "value")
        if self.mode == "DIAMETER":
            _wrapped(self.layout, "Enter the full diameter.")
            _wrapped(self.layout, "Stored as a driving radius = diameter / 2.")
            _wrapped(self.layout, "Radius formulas appear doubled; enter diameter formulas in mm.")
        _wrapped(self.layout, "Apply solves the draft; incompatible values remain recoverable.")

    def execute(self, context):
        try:
            from .general_sketch_commands import AddRelation

            owner = active(context)
            _require_ui_idle(owner, context)
            if (
                owner is not getattr(self, "_owner", None)
                or constraint_actions._binding(owner) != self._binding
            ):
                raise DraftError("The sketch changed. Reopen the dimension editor.")
            if self._relation_id and self.value == self._initial_text:
                return {"FINISHED"}
            raw = self.value.strip()
            if not raw:
                raise DraftError("Enter a number or formula.")
            from .unit_input import normalize_unit_input

            raw = normalize_unit_input(raw, "angle" if self.mode == "ANGLE" else "length")
            value = raw if self.mode == "ANGLE" else _diameter_radius_value(raw)
            if self._relation_id:
                owner.begin_dimension(self._relation_id)
                owner.update_raw(str(value))
                owner.checkpoint()
                owner.request_driver_accept(context)
            else:
                owner.execute(
                    context,
                    AddRelation(
                        "angle" if self.mode == "ANGLE" else "radius", self._refs, value=value
                    ),
                    annotation_offset=(0.0, 5.0),
                )
            return {"FINISHED"}
        except Exception as exc:
            return _error(self, exc)


class MCAD_OT_sketch_construction(Operator):
    bl_idname = "mcad.sketch_construction"
    bl_label = "Toggle construction"
    bl_description = "Use selected curves as construction references, or restore profile boundaries"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def execute(self, context):
        try:
            from .general_sketch_commands import SetConstruction

            owner = active(context)
            _require_ui_idle(owner, context)
            selected = constraint_selection.normalize_selection(
                owner.commands.sketch, owner.draft.selection
            )
            if not selected or any(item.kind not in {"line", "circle", "arc"} for item in selected):
                raise DraftError("Select one or more lines, circles or arcs.")
            targets = tuple((item.kind, item.id) for item in selected)
            curves = [
                next(
                    curve
                    for curve in owner.commands.sketch[kind + "s"]
                    if curve["id"] == identifier
                )
                for kind, identifier in targets
            ]
            construction = not all(curve.get("construction", False) for curve in curves)
            owner.execute(context, SetConstruction(targets, construction))
            return {"FINISHED"}
        except Exception as exc:
            return _error(self, exc)


class MCAD_OT_constraint_fixed_target(Operator):
    bl_idname = "mcad.constraint_fixed_target"
    bl_label = "Edit fixed point"
    bl_description = "Change this fixed relation's sketch-plane target in millimetres"
    bl_options = {"INTERNAL"}

    u: FloatProperty(name="U (mm)", precision=5, min=-1e6, max=1e6)
    v: FloatProperty(name="V (mm)", precision=5, min=-1e6, max=1e6)

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def invoke(self, context, event):
        try:
            owner = active(context)
            _require_ui_idle(owner, context)
            contract = constraint_selection.selection_contract(
                owner.commands.sketch, owner.draft.selection
            )
            if len(contract.selection) != 1 or contract.selection[0].kind != "constraint":
                raise DraftError("Select the exact fixed relation first.")
            relation = next(item for item in contract.relations if item.kind == "fixed")
            self._owner = owner
            self._binding = constraint_actions._binding(owner)
            self._relation_id = relation.id
            self._original = relation.fixed_target
            self.u, self.v = self._original
            self._displayed = (self.u, self.v)
            return context.window_manager.invoke_props_dialog(self)
        except Exception as exc:
            return _error(self, exc)

    def draw(self, context):
        self.layout.label(text="Connected geometry can move after Apply.")
        self.layout.prop(self, "u")
        self.layout.prop(self, "v")

    def execute(self, context):
        try:
            from .general_sketch_commands import EditFixedTarget

            owner = active(context)
            _require_ui_idle(owner, context)
            if (
                owner is not getattr(self, "_owner", None)
                or constraint_actions._binding(owner) != self._binding
            ):
                raise DraftError("The sketch changed. Reopen the fixed-point editor.")
            # Blender RNA floats may round double precision. Preserve untouched components.
            target = tuple(
                original if displayed == initial else displayed
                for original, displayed, initial in zip(
                    self._original, (self.u, self.v), self._displayed, strict=True
                )
            )
            owner.execute(context, EditFixedTarget(self._relation_id, target))
            return {"FINISHED"}
        except Exception as exc:
            return _error(self, exc)


class MCAD_OT_constraint_action(Operator):
    bl_idname = "mcad.constraint_action"
    bl_label = "Sketch constraint"
    bl_description = "Apply an explicit relation to the exact selected sketch identities"
    bl_options = {"INTERNAL"}

    action: EnumProperty(name="Action", items=ACTION_ITEMS, default="horizontal")

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    @classmethod
    def description(cls, context, properties):
        return next(
            (item[2] for item in ACTION_ITEMS if item[0] == properties.action), cls.bl_description
        )

    def invoke(self, context, event):
        _clear_intent(self)
        try:
            owner = active(context)
            _require_ui_idle(owner, context)
            intent = constraint_actions.prepare(owner, self.action)
            self._prepared_intent = intent
            self._prepared_owner = owner
            if intent.requires_confirmation:
                self._confirmation_pending = True
                return context.window_manager.invoke_props_dialog(
                    self, width=460, confirm_text="Apply"
                )
            return self.execute(context)
        except Exception as exc:
            _clear_intent(self)
            return _error(self, exc)

    def draw(self, context):
        intent = getattr(self, "_prepared_intent", None)
        if intent is None:
            self.layout.label(text="This action has no prepared confirmation.", icon="ERROR")
            return
        title = next(item[1] for item in ACTION_ITEMS if item[0] == intent.action)
        self.layout.label(text=title, icon="ERROR")
        _wrapped(self.layout, intent.disclosure, width=62)
        if intent.relation_ids:
            _wrapped(self.layout, "Relation: " + ", ".join(intent.relation_ids), width=62)
        if intent.refs:
            _wrapped(self.layout, "References: " + ", ".join(intent.refs), width=62)
        if intent.target is not None:
            self.layout.label(text="Sketch-plane target: " + _target(intent.target) + " mm")

    def execute(self, context):
        # Only this instance's native invoke/confirmation path can supply the
        # confirmation flag. It is not an RNA property that callers can set.
        intent = getattr(self, "_prepared_intent", None)
        prepared_owner = getattr(self, "_prepared_owner", None)
        confirmed = bool(getattr(self, "_confirmation_pending", False))
        _clear_intent(self)
        try:
            owner = active(context)
            _require_ui_idle(owner, context)
            if intent is None:
                intent = constraint_actions.prepare(owner, self.action)
                if intent.requires_confirmation:
                    raise DraftError(
                        "Use the confirmation dialog to review this exact action first."
                    )
                confirmed = False
            elif prepared_owner is not owner or intent.action != self.action:
                raise DraftError("The prepared constraint action changed. Review it again.")
            result = constraint_actions.apply(owner, context, intent, confirmed=confirmed)
            if intent.state == "existing" and len(result.relation_ids) == 1:
                select_bindings(owner, (("constraint", result.relation_ids[0]),), context=context)
            sketch_session._tag_redraw(owner)
            return {"FINISHED"}
        except Exception as exc:
            return _error(self, exc)

    def cancel(self, context):
        _clear_intent(self)


class MCAD_OT_constraint_select(Operator):
    bl_idname = "mcad.constraint_select"
    bl_label = "Inspect sketch identity"
    bl_description = (
        "Select this exact existing relation or point; never infer an overlapping endpoint"
    )
    bl_options = {"INTERNAL"}

    kind: EnumProperty(
        items=(("constraint", "Relation", ""), ("point", "Point", "")), default="constraint"
    )
    identifier: StringProperty(name="Stable ID", maxlen=256)
    source_kind: EnumProperty(
        items=(
            ("NONE", "None", ""),
            ("line", "Line", ""),
            ("circle", "Circle", ""),
            ("arc", "Arc", ""),
        ),
        default="NONE",
    )
    source_id: StringProperty(name="Source curve ID", maxlen=256)
    source_role: EnumProperty(
        items=(
            ("NONE", "None", ""),
            ("START", "Start", ""),
            ("END", "End", ""),
            ("CENTER", "Center", ""),
        ),
        default="NONE",
    )

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def execute(self, context):
        try:
            owner = active(context)
            _require_ui_idle(owner, context)
            if self.source_role != "NONE":
                kind = self.source_kind
                allowed = {
                    "line": {"START", "END"},
                    "circle": {"CENTER"},
                    "arc": {"CENTER", "START", "END"},
                }
                if (
                    kind not in allowed
                    or self.source_role not in allowed[kind]
                    or self.kind != "point"
                    or owner.draft.selection != [{"kind": kind, "id": self.source_id}]
                ):
                    raise DraftError("The selected curve changed. Choose its point again.")
                record = next(
                    (
                        item
                        for item in owner.commands.sketch.get(kind + "s", [])
                        if item["id"] == self.source_id
                    ),
                    None,
                )
                role = self.source_role.lower()
                if record is None or record[role] != self.identifier:
                    raise DraftError("This curve point binding is unavailable. Choose it again.")
            elif self.source_kind != "NONE" or self.source_id:
                raise DraftError(
                    "Choose an explicit source curve kind, ID and point role together."
                )
            select_bindings(owner, ((self.kind, self.identifier),), context=context)
            return {"FINISHED"}
        except Exception as exc:
            return _error(self, exc)


class MCAD_OT_constraint_history(Operator):
    bl_idname = "mcad.constraint_history"
    bl_label = "Local sketch history"
    bl_description = "Undo or redo one local sketch action using the sketch journal"
    bl_options = {"INTERNAL"}

    direction: EnumProperty(
        items=(("UNDO", "Undo sketch action", ""), ("REDO", "Redo sketch action", "")),
        default="UNDO",
    )

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def execute(self, context):
        try:
            owner = active(context)
            _require_ui_idle(owner, context)
            owner.local_history(context, redo=self.direction == "REDO")
            return {"FINISHED"}
        except Exception as exc:
            return _error(self, exc)


def _page_state(owner, scope, key, count):
    current = getattr(owner, "_constraint_" + scope + "_page", None)
    index = current[1] if current is not None and current[0] == key else 0
    return max(0, min(index, max(0, (count - 1) // PAGE_SIZE)))


def _candidate_ids(owner):
    diagnostics = owner.current_diagnostics
    if diagnostics is None:
        return ()
    return tuple(
        dict.fromkeys(diagnostics.candidate_constraint_ids + diagnostics.redundant_constraint_ids)
    )


class MCAD_OT_constraint_page(Operator):
    bl_idname = "mcad.constraint_page"
    bl_label = "More sketch relations"
    bl_description = "Browse bounded inspector rows; this does not edit the sketch"
    bl_options = {"INTERNAL"}

    scope: EnumProperty(
        items=(
            ("relations", "Relations", ""),
            ("conflicts", "Conflict candidates", ""),
            ("references", "References", ""),
        ),
        default="relations",
    )
    delta: IntProperty(default=1, min=-1, max=1)

    @classmethod
    def poll(cls, context):
        return active(context) is not None

    def execute(self, context):
        try:
            owner = active(context)
            _require_ui_idle(owner, context)
            if self.scope == "conflicts":
                key = _candidate_ids(owner)
                count = len(key)
            elif self.scope == "references":
                from .reference_dimensions import is_reference

                key = tuple(
                    key for key, binding in owner.draft.annotations.items() if is_reference(binding)
                )
                count = len(key)
            else:
                contract = constraint_selection.selection_contract(
                    owner.commands.sketch, owner.draft.selection
                )
                key = tuple((item.kind, item.id) for item in contract.selection)
                count = len(contract.relations)
            index = _page_state(owner, self.scope, key, count) + self.delta
            index = max(0, min(index, max(0, (count - 1) // PAGE_SIZE)))
            setattr(owner, "_constraint_" + self.scope + "_page", (key, index))
            sketch_session._tag_redraw(owner)
            return {"FINISHED"}
        except Exception as exc:
            return _error(self, exc)


def _target(target):
    return "(" + ", ".join(str(value) for value in target) + ")"


def _relation_label(relation):
    label = {"fixed": "Fixed point"}.get(relation.kind, relation.kind.capitalize())
    if relation.source_value is not None:
        label += ": " + str(relation.source_value)
    elif relation.fixed_target is not None:
        label += ": " + _target(relation.fixed_target)
    return label


def _wrapped(layout, text, *, width=38):
    for line in textwrap.wrap(
        str(text), width=width, break_long_words=True, break_on_hyphens=False
    ) or [""]:
        layout.label(text=line)


def _selection_button(
    layout, identifier, *, text, kind="constraint", source_kind="NONE", source_id="", role="NONE"
):
    operator = layout.operator("mcad.constraint_select", text=text, icon="RESTRICT_SELECT_OFF")
    operator.kind = kind
    operator.identifier = identifier
    operator.source_kind = source_kind
    operator.source_id = source_id
    operator.source_role = role


def _action_button(layout, context, action, label):
    row = layout.row(align=True)
    row.enabled = action_available(context, action)
    row.operator_context = "INVOKE_DEFAULT"
    row.operator("mcad.constraint_action", text=label).action = action
    if action in {"point_on_line", "midpoint", "concentric", "circle_line_tangent", "symmetry"}:
        row.operator("mcad.help", text="", icon="QUESTION").topic = "sketch.position_relations"


def _pager(layout, owner, scope, key, count):
    index = _page_state(owner, scope, key, count)
    if count > PAGE_SIZE:
        row = layout.row(align=True)
        back = row.row(align=True)
        back.enabled = index > 0
        button = back.operator("mcad.constraint_page", text="", icon="TRIA_LEFT")
        button.scope, button.delta = scope, -1
        row.label(text=f"{index * PAGE_SIZE + 1}–{min(count, (index + 1) * PAGE_SIZE)} / {count}")
        forward = row.row(align=True)
        forward.enabled = (index + 1) * PAGE_SIZE < count
        button = forward.operator("mcad.constraint_page", text="", icon="TRIA_RIGHT")
        button.scope, button.delta = scope, 1
    return slice(index * PAGE_SIZE, (index + 1) * PAGE_SIZE)


def draw_inspector(layout, context, owner):
    """Bounded contextual inspector. Diagnostic candidates remain inspection only."""
    if type(owner) is not GeneralSession or active(context) is not owner:
        return
    box = layout.box()
    title = box.row(align=True)
    title.label(text="Sketch relations")
    title.operator("mcad.help", text="", icon="QUESTION").topic = "sketch.constraints"
    try:
        _require_ui_idle(owner, context)
        ready = True
    except (ValueError, ReferenceError, AttributeError) as exc:
        ready = False
        _wrapped(box, str(exc))
    history = box.row(align=True)
    for redo, label in ((False, "Undo sketch"), (True, "Redo sketch")):
        row = history.row(align=True)
        row.enabled = ready and (owner.commands.can_redo if redo else owner.commands.can_undo)
        row.operator(
            "mcad.constraint_history", text=label, icon="LOOP_FORWARDS" if redo else "LOOP_BACK"
        ).direction = "REDO" if redo else "UNDO"
    try:
        contract = constraint_selection.selection_contract(
            owner.commands.sketch, owner.draft.selection
        )
    except (ValueError, TypeError, KeyError) as exc:
        box.label(text="Selection binding unavailable", icon="ERROR")
        _wrapped(box, str(exc))
        missing = tuple(item for item in owner.draft.status.selection if not item.available)
        for item in missing[:PAGE_SIZE]:
            _wrapped(box, f"{item.identifier}: {item.state}")
        if len(missing) > PAGE_SIZE:
            box.label(text=f"{len(missing) - PAGE_SIZE} more unavailable selections")
        contract = None
    if contract is not None:
        selected = contract.selection[0] if len(contract.selection) == 1 else None
        controls = box.column(align=True)
        controls.enabled = ready
        if len(contract.selection) == 2 and all(item.kind == "line" for item in contract.selection):
            controls.operator("mcad.sketch_corner_fillet", text="Corner Fillet…", icon="MOD_BEVEL")
            controls.operator("mcad.sketch_numeric_relation", text="Set angle…").mode = "ANGLE"
        if selected and selected.kind == "arc" and any(
            a["id"] == selected.id and "fillet_intent" in a
            for a in owner.commands.sketch.get("arcs", [])
        ):
            controls.operator("mcad.remove_sketch_fillet", text="Restore Sharp Corner…", icon="LOOP_BACK")
        if selected and selected.kind in {"circle", "arc"}:
            controls.operator(
                "mcad.sketch_numeric_relation", text="Set diameter…"
            ).mode = "DIAMETER"
        if selected and selected.kind in {"line", "circle", "arc"}:
            reference = controls.row(align=True)
            for mode in ("length",) if selected.kind == "line" else ("radius", "diameter"):
                reference.operator(
                    "mcad.sketch_reference_dimension", text=mode.title() + " (REF)"
                ).mode = mode
        if selected and selected.kind == "constraint":
            for relation in contract.relations:
                if relation.kind in {"angle", "radius"}:
                    controls.operator(
                        "mcad.sketch_numeric_relation",
                        text="Edit angle…" if relation.kind == "angle" else "Edit diameter…",
                    ).mode = "ANGLE" if relation.kind == "angle" else "DIAMETER"
        if contract.selection and all(
            item.kind in {"line", "circle", "arc"} for item in contract.selection
        ):
            controls.operator("mcad.sketch_construction", text="Toggle construction")
            for item in contract.selection:
                curve = next(
                    curve
                    for curve in owner.commands.sketch[item.kind + "s"]
                    if curve["id"] == item.id
                )
                if curve.get("construction", False):
                    controls.label(text=item.id + ": construction reference")
        if selected is None:
            controls.label(
                text="Shift-select entities for a relation (symmetry: two points + line)."
            )
            for action, label in (
                ("coincident", "Coincident"),
                ("parallel", "Parallel"),
                ("perpendicular", "Perpendicular"),
                ("equal", "Equal"),
                ("tangent", "Arc tangent"),
                ("point_on_line", "Point on line"),
                ("midpoint", "Midpoint"),
                ("symmetry", "Symmetry"),
                ("concentric", "Concentric circles"),
                ("circle_line_tangent", "Circle-line tangent"),
            ):
                spec = contract.action(action)
                if spec.state in {"eligible", "existing"}:
                    _action_button(controls, context, action, label)
            if len(contract.selection) in {2, 3}:
                controls.label(text=" + ".join(item.id for item in contract.selection))
        else:
            controls.label(text=selected.kind.capitalize() + ": " + selected.id)
            if selected.kind == "line":
                row = controls.row(align=True)
                _action_button(row, context, "horizontal", "Horizontal")
                _action_button(row, context, "vertical", "Vertical")
                line = next(
                    item for item in owner.commands.sketch["lines"] if item["id"] == selected.id
                )
                row = controls.row(align=True)
                for role in ("start", "end"):
                    _selection_button(
                        row,
                        line[role],
                        text=role.capitalize() + " point",
                        kind="point",
                        source_kind="line",
                        source_id=selected.id,
                        role=role.upper(),
                    )
            elif selected.kind in {"circle", "arc"}:
                curve = next(
                    item
                    for item in owner.commands.sketch[selected.kind + "s"]
                    if item["id"] == selected.id
                )
                for role in ("center", "start", "end") if selected.kind == "arc" else ("center",):
                    _selection_button(
                        controls,
                        curve[role],
                        text=role.capitalize() + " point",
                        kind="point",
                        source_kind=selected.kind,
                        source_id=selected.id,
                        role=role.upper(),
                    )
            elif selected.kind == "point":
                row = controls.row(align=True)
                _action_button(row, context, "fix_here", "Fix here")
                _action_button(row, context, "fix_origin", "Fix at origin…")
            elif selected.kind == "constraint":
                if any(item.kind == "fixed" for item in contract.relations):
                    controls.operator(
                        "mcad.constraint_fixed_target", text="Edit fixed coordinates…"
                    )
                if owner.commands.has_current_solution:
                    _action_button(controls, context, "remove_relation", "Remove relation")
                else:
                    _action_button(
                        controls,
                        context,
                        "recover_remove_relation",
                        "Remove using authored positions…",
                    )
            key = tuple((item.kind, item.id) for item in contract.selection)
            visible = _pager(controls, owner, "relations", key, len(contract.relations))
            for relation in contract.relations[visible]:
                detail = controls.box()
                _selection_button(
                    detail,
                    relation.id,
                    text=textwrap.shorten(_relation_label(relation), width=44, placeholder="…"),
                )
                _wrapped(detail, "Refs: " + ", ".join(relation.refs))
                if selected.kind == "constraint":
                    _wrapped(detail, "Stable ID: " + relation.id)
                    _wrapped(detail, _relation_label(relation))
            if not contract.relations:
                controls.label(text="No incident relations.")
    from .reference_dimensions import is_reference

    references = [
        (key, binding) for key, binding in owner.draft.annotations.items() if is_reference(binding)
    ]
    from .compact_status import disclosure

    if references and disclosure(
        box, context.scene.mechanical_cad, "show_reference_measurements",
        f"Reference measurements ({len(references)})",
    ):
        reference_box = box.box()
        header = reference_box.row(align=True)
        header.label(text="Reference measurements (read-only)")
        header.operator("mcad.help", text="", icon="QUESTION").topic = "sketch.reference_dimensions"
        states = {item.identifier: item.state for item in owner.draft.status.annotations}
        visible = _pager(
            reference_box, owner, "references", tuple(key for key, _ in references), len(references)
        )
        for key, binding in references[visible]:
            row = reference_box.row(align=True)
            row.label(
                text=binding["kind"].title()
                + " · "
                + binding["refs"][0]
                + (" · unavailable" if states.get(key) != "available" else "")
            )
            control = row.row(align=True)
            control.enabled = ready
            control.operator(
                "mcad.remove_reference_dimension", text="", icon="X"
            ).annotation_id = key
    unavailable = tuple(item for item in owner.draft.status.conflicts if item.scope == "annotation")
    if unavailable:
        box.label(text="Unavailable annotation bindings", icon="ERROR")
        for item in unavailable[:PAGE_SIZE]:
            _wrapped(box, f"{item.identifier}: {item.state}")
        if len(unavailable) > PAGE_SIZE:
            box.label(text=f"{len(unavailable) - PAGE_SIZE} more retained bindings")
    candidates = _candidate_ids(owner)
    if candidates:
        diagnostics = box.box()
        diagnostics.label(text="Conflict candidates", icon="ERROR")
        _wrapped(diagnostics, "Inspect these IDs. A candidate is not permission to delete it.")
        visible = _pager(diagnostics, owner, "conflicts", candidates, len(candidates))
        authored = {
            item.id: item
            for item in constraint_selection.relation_descriptors(owner.commands.sketch)
        }
        for identifier in candidates[visible]:
            row = diagnostics.column(align=True)
            row.enabled = ready and identifier in authored
            label = (
                identifier + ": " + _relation_label(authored[identifier])
                if identifier in authored
                else identifier + ": unavailable"
            )
            _selection_button(
                row, identifier, text=textwrap.shorten(label, width=44, placeholder="…")
            )


CLASSES = (
    MCAD_OT_sketch_reference_dimension,
    MCAD_OT_remove_reference_dimension,
    MCAD_OT_constraint_action,
    MCAD_OT_constraint_fixed_target,
    MCAD_OT_sketch_construction,
    MCAD_OT_sketch_numeric_relation,
    MCAD_OT_constraint_select,
    MCAD_OT_constraint_history,
    MCAD_OT_constraint_page,
)
