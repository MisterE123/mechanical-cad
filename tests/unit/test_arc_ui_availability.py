"""Pure production UI ports; no Blender, sidecar, solver or kernel is launched.

Host/layout adapters retain production policy, menu, inspector and execution code.
These are behavior tests, not installed-GUI or native qualification.
"""

import copy
import importlib
import importlib.util
import json
import sys
import textwrap
import types
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "arc_ui_host_ports", ROOT / "tests/integration/service_v3_owner_fakes.py"
)
ports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ports)
ports.PACKAGE = "mcad_arc_ui_tests"


def legacy():
    return json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())


def sector(*, extruded=True, empty=False, inactive=False):
    path = ROOT / "tests/fixtures/arc_authoring_evidence/radius_edit_5_0_replay.operation.json"
    result = json.loads(path.read_text())["document"]
    if not extruded:
        result["features"] = result["features"][:1]
        result["active_feature"] = result["features"][0]["id"]
    if empty or inactive:
        result["features"][0]["sketch"]["arcs"] = []
        result["features"][0]["sketch"]["constraints"] = []
    if inactive:
        feature = result["features"][0]
        feature["id"] = "inactive_schema3"
        result = legacy()
        result["features"].append(feature)
    return result


@pytest.fixture
def ui(monkeypatch):
    modules = ports.load_owners()
    package = sys.modules[ports.PACKAGE]
    bpy = modules.bpy
    bpy.types = ports.module(
        "bpy.types",
        **{
            name: type(name, (), {})
            for name in (
                "Operator",
                "Menu",
                "Panel",
                "UIList",
                "PropertyGroup",
                "Gizmo",
                "GizmoGroup",
            )
        },
    )
    bpy.utils = ports.module("bpy.utils", previews=ports.module("bpy.utils.previews"))
    bpy.props = ports.module(
        "bpy.props",
        **{
            name: ports.noop
            for name in (
                "BoolProperty",
                "CollectionProperty",
                "EnumProperty",
                "FloatProperty",
                "IntProperty",
                "StringProperty",
            )
        },
    )
    modules.workspace.ROLES = ("SKETCH", "PART", "ASSEMBLY")
    modules.workspace.get_role = lambda _context: "PART"
    modules.workspace.is_cad_workspace = lambda _context: True
    modules.workspace.suspended_draft = lambda _context: {}
    modules.workspace.draft_recovery_notice = lambda: ""
    help_ui = sys.modules[ports.PACKAGE + ".help_ui"]
    help_ui._panel_wrap = lambda _context, text: textwrap.wrap(str(text), width=80)
    help_ui._diagnostic_button = help_ui._help_button = ports.noop
    stubs = {
        "bpy": bpy,
        "bpy.types": bpy.types,
        "bpy.props": bpy.props,
        "bpy.utils": bpy.utils,
        "bpy.utils.previews": bpy.utils.previews,
        "bpy_extras": ports.module("bpy_extras"),
        "bpy_extras.io_utils": ports.module(
            "bpy_extras.io_utils",
            ExportHelper=type("ExportHelper", (), {}),
            ImportHelper=type("ImportHelper", (), {}),
        ),
        "mathutils": ports.module("mathutils", Matrix=object),
        # This availability fixture has no active visual session. Actual
        # viewport-owner behavior has its own synthetic-host and native tests.
        ports.PACKAGE + ".assembly_joint_viewport": ports.module(
            ports.PACKAGE + ".assembly_joint_viewport", active=lambda _context=None: None
        ),
    }
    with patch.dict(sys.modules, stubs):
        for name in (
            "operators",
            "solid_operators",
            "assembly_operators",
            "general_session",
            "constraint_ui",
            "assembly_ui",
        ):
            setattr(modules, name, importlib.import_module(ports.PACKAGE + "." + name))
        if not hasattr(getattr(package, "workspace_ui", None), "action_reason"):
            sys.modules.pop(ports.PACKAGE + ".workspace_ui", None)
            if hasattr(package, "workspace_ui"):
                delattr(package, "workspace_ui")
        modules.workspace_ui = importlib.import_module(ports.PACKAGE + ".workspace_ui")
        retained = {
            key: value for key, value in sys.modules.items() if key.startswith(ports.PACKAGE + ".")
        }
    sys.modules.update(retained)
    selected = modules.backend_selection.BackendSelection.capture(
        str(ROOT), sys.executable, generation=0, lifetime_id="ui-host-port", environment={}
    )
    modules.selected = selected
    monkeypatch.setattr(modules.backend_runtime, "capture", lambda _context: selected)
    yield modules


def context(ui, document=None):
    ctx = ports.context_for(ui, document or legacy(), ui.selected)
    ctx.area = object()
    ctx.window.view_layer = ctx.view_layer
    ctx.scene.mechanical_cad_assembly.document_json = (
        ROOT / "examples/reused_blocks.mcad-assembly.json"
    ).read_text()
    return ctx


class Layout:
    def __init__(self, entries=None, icons=None):
        self.entries = [] if entries is None else entries
        self.icons = [] if icons is None else icons
        self.enabled = True

    def row(self, **_kwargs):
        child = Layout(self.entries, self.icons)
        child.enabled = self.enabled
        return child

    box = column = row

    def label(self, **kwargs):
        self.entries.append(("label", kwargs.get("text", "")))
        self.icons.append((kwargs.get("text", ""), kwargs.get("icon", "NONE")))

    def operator(self, name, **kwargs):
        result = types.SimpleNamespace(name=name, enabled=self.enabled, **kwargs)
        self.entries.append(("operator", result))
        return result

    def prop(self, instance, name, **kwargs):
        self.entries.append(("prop", (name, self.enabled)))

    def template_list(self, *_args, **_kwargs):
        pass

    def separator(self):
        pass

    def menu(self, name, **kwargs):
        self.entries.append(("menu", name))


def labels(layout):
    return " ".join(value for kind, value in layout.entries if kind == "label")


@pytest.mark.parametrize("variant", [{"extruded": False}])
def test_schema3_action_visibility_uses_whole_candidate_without_side_effects(
    ui, monkeypatch, variant
):
    ctx = context(ui, sector(**variant))
    before = copy.deepcopy(vars(ctx.scene.mechanical_cad))
    monkeypatch.setattr(
        ui.workspace_ui,
        "_operator",
        lambda *_: pytest.fail("Rejected policy must precede operator work"),
    )
    for action in ("CHECK", "EXPORT"):
        assert ui.workspace_ui.action_reason(ctx, action)
        assert not ui.workspace_ui.available(ctx, action)
    assert ui.operators.part_action_reason(ctx, "canonical_snapshot")
    assert ui.assembly_operators.working_part_capture_reason(ctx)
    assert not ui.assembly_operators.MCAD_OT_assembly_new.poll(ctx)
    assert not ui.assembly_operators.MCAD_OT_assembly_update_source.poll(ctx)
    assert ui.assembly_operators.MCAD_OT_assembly_insert.poll(ctx)
    assert ui.assembly_operators.MCAD_OT_assembly_replay.poll(ctx)
    menu = Layout()
    ui.workspace_ui.MCAD_MT_export.draw(types.SimpleNamespace(layout=menu), ctx)
    assert all(not item.enabled for kind, item in menu.entries if kind == "operator")
    assert "Geometry" in labels(menu) or "sector" in labels(menu)
    detail = Layout()
    ui.assembly_ui.draw_capture_limit(detail, ctx)
    assert "Existing accepted reusable parts" in labels(detail)
    assert vars(ctx.scene.mechanical_cad) == before
    assert ui.operators.MCAD_OT_save.poll(ctx)


@pytest.mark.parametrize("malformation", ["missing_profile", "unsupported_kind"])
def test_malformed_arc_graph_still_rejects_actions_and_capture_without_mutation(
    ui, monkeypatch, malformation
):
    document = sector()
    if malformation == "missing_profile":
        document["features"][-1]["inputs"]["profile"] = "missing_profile"
    else:
        document["features"][-1]["kind"] = "unknown_solid_operation"
    ctx = context(ui, document)
    before = copy.deepcopy(vars(ctx.scene.mechanical_cad))
    monkeypatch.setattr(ui.workspace_ui, "_operator",
                        lambda *_: pytest.fail("Malformed graph must reject before operator work"))
    for action in ("CHECK", "EXPORT"):
        assert ui.workspace_ui.action_reason(ctx, action)
        assert not ui.workspace_ui.available(ctx, action)
    assert ui.operators.part_action_reason(ctx, "canonical_snapshot")
    assert ui.assembly_operators.working_part_capture_reason(ctx)
    assert not ui.assembly_operators.MCAD_OT_assembly_new.poll(ctx)
    assert not ui.assembly_operators.MCAD_OT_assembly_update_source.poll(ctx)
    assert ui.assembly_operators.MCAD_OT_assembly_insert.poll(ctx)
    assert ui.operators.MCAD_OT_save.poll(ctx)
    assert vars(ctx.scene.mechanical_cad) == before


@pytest.mark.parametrize(
    "kind,cls",
    [
        ("sketch_rectangle", "MCAD_OT_rectangle"),
        ("sketch_circle", "MCAD_OT_circle"),
        ("extrude", "MCAD_OT_extrude"),
        ("cut", "MCAD_OT_cut"),
    ],
)
def test_arc_graph_ui_and_direct_feature_execution_agree_before_append(ui, monkeypatch, kind, cls):
    ctx = context(ui, sector())
    state = ctx.scene.mechanical_cad
    before = state.document_json
    unsupported = kind == "cut"  # Only one solid: no valid base/tool pair.
    assert bool(ui.operators.feature_action_reason(ctx, kind)) == unsupported
    operator_class = getattr(ui.operators, cls)
    assert operator_class.poll(ctx) != unsupported
    submitted = []
    monkeypatch.setattr(ui.operators, "_append_feature",
                        lambda _ctx, feature: submitted.append(copy.deepcopy(feature)) or True)
    monkeypatch.setattr(ui.operators, "_commit_candidate",
                        lambda _ctx, candidate, _path: submitted.append(copy.deepcopy(candidate)) or True)
    operator = operator_class()
    operator.report = lambda *_: None
    for name in ("width", "height", "radius", "length"):
        setattr(operator, name, 10)
    operator.x = operator.y = operator.z = 0
    operator.profile = sector()["features"][0]["id"]
    operator.base, operator.tool = "base", "tool"
    operator.end_condition = "BLIND"
    operator.enter_part_after_apply = False
    operator.properties = types.SimpleNamespace(is_property_set=lambda *_: False)
    assert operator.execute(ctx) == ({"CANCELLED"} if unsupported else {"FINISHED"})
    assert state.document_json == before
    if unsupported:
        assert not submitted and state.last_action_error
    else:
        assert len(submitted) == 1
        feature = submitted[0]["features"][-1] if kind == "extrude" else submitted[0]
        assert feature["kind"] == kind
        if kind == "extrude":
            assert submitted[0]["features"][:-1] == json.loads(before)["features"]
            assert feature["inputs"] == {"profile": operator.profile}


def test_first_sole_arc_extrusion_and_legacy_feature_controls_remain_available(ui, monkeypatch):
    ctx = context(ui, sector(extruded=False))
    assert not ui.operators.feature_action_reason(ctx, "extrude")
    assert ui.operators.MCAD_OT_extrude.poll(ctx)
    assert len(ui.operators._profile_choices(None, ctx)) == 1
    submitted = []
    monkeypatch.setattr(
        ui.operators,
        "_commit_candidate",
        lambda _ctx, candidate, _path: submitted.append(copy.deepcopy(candidate)) or True,
    )
    op = ui.operators.MCAD_OT_extrude()
    op.profile, op.length = sector(extruded=False)["active_feature"], 10
    op.report = lambda *_: None
    op.end_condition, op.enter_part_after_apply = "BLIND", False
    op.properties = types.SimpleNamespace(is_property_set=lambda *_: False)
    before = ctx.scene.mechanical_cad.document_json
    assert op.execute(ctx) == {"FINISHED"}
    feature = submitted[0]["features"][-1]
    assert feature["inputs"] == {"profile": op.profile}
    assert submitted[0]["parameters"][feature["params"]["length"]] == 10
    assert submitted[0]["features"][:-1] == json.loads(before)["features"]
    assert ctx.scene.mechanical_cad.document_json == before
    old = context(ui)
    for kind in ("sketch_rectangle", "sketch_circle", "extrude", "sketch_constrained"):
        assert not ui.operators.feature_action_reason(old, kind)
    for action in ("check_geometry", "export_step", "export_stl", "canonical_snapshot"):
        assert not ui.operators.part_action_reason(old, action)
    assert ui.assembly_operators.MCAD_OT_assembly_new.poll(old)
    assert ui.assembly_operators.MCAD_OT_assembly_update_source.poll(old)


@pytest.mark.parametrize("variant", [{"extruded": False}])
def test_unsupported_capture_rejects_but_existing_definition_insert_does_not_capture(
    ui, monkeypatch, variant
):
    ctx = context(ui, sector(**variant))
    assert ui.assembly_operators.working_part_capture_reason(ctx)
    monkeypatch.setattr(
        ui.assembly_operators,
        "canonical_working_part",
        lambda *_: pytest.fail("No capture for unsupported sources or existing definitions"),
    )
    for cls in (
        ui.assembly_operators.MCAD_OT_assembly_new,
        ui.assembly_operators.MCAD_OT_assembly_update_source,
    ):
        op = cls()
        op.grounded = True
        op.report = lambda *_: None
        assert op.execute(ctx) == {"CANCELLED"}
    op = ui.assembly_operators.MCAD_OT_assembly_insert()
    op.report = lambda *_: None
    op.part_id = "existing"
    op.use_working_part = True
    assert op.execute(ctx) == {"CANCELLED"}
    op.use_working_part = False
    op.use_limits = False
    op.kind = "fixed"
    op.parent, op.parent_frame, op.child_frame = "root", "parent", "child"
    op.name, op.joint_name = "Child", "Joint"
    calls = []
    monkeypatch.setattr(
        ui.assembly_operators.edit,
        "insert_instance",
        lambda candidate, part_id, **kwargs: calls.append(part_id) or candidate,
    )
    op.apply = lambda _context, candidate: {"FINISHED"}
    assert op.execute(ctx) == {"FINISHED"}
    assert calls == ["existing"]


@pytest.mark.parametrize("operation", ["new", "insert", "update_source"])
def test_supported_sector_capture_actions_reach_explicit_capture_and_apply(
    ui, monkeypatch, operation
):
    ctx = context(ui, sector())
    before = ctx.scene.mechanical_cad.document_json
    assert not ui.assembly_operators.working_part_capture_reason(ctx)
    calls = []
    captured, candidate = object(), object()
    monkeypatch.setattr(
        ui.assembly_operators,
        "canonical_working_part",
        lambda context: calls.append(("capture", context)) or captured,
    )

    def source_edit(*args, **_kwargs):
        assert args[-1] is captured
        calls.append(("edit", operation))
        return candidate if operation == "new" else (candidate, "sector")

    edit_name = {"new": "new_from_part", "insert": "capture_definition"}.get(
        operation, "update_source"
    )
    monkeypatch.setattr(ui.assembly_operators.edit, edit_name, source_edit)

    def insert(actual, part_id, **_kwargs):
        assert actual is candidate and part_id == "sector"
        calls.append(("insert", part_id))
        return candidate

    monkeypatch.setattr(ui.assembly_operators.edit, "insert_instance", insert)
    monkeypatch.setattr(ui.assembly_operators, "activate_assembly_workspace", lambda *_: None)
    cls = getattr(ui.assembly_operators, "MCAD_OT_assembly_" + operation)
    assert cls.poll(ctx)
    op = cls()
    op.grounded, op.use_working_part, op.use_limits = True, True, False
    op.name, op.instance_name, op.joint_name = "Sector", "Base", "Joint"
    op.part_id, op.kind = "existing", "fixed"
    op.parent, op.parent_frame, op.child_frame = "root", "parent", "child"
    op.report = lambda *_: None

    def apply(context, actual):
        assert context is ctx and actual is candidate
        calls.append(("apply", operation))
        return {"FINISHED"}

    op.apply = apply
    assert op.execute(ctx) == {"FINISHED"}
    assert calls == [
        ("capture", ctx),
        ("edit", operation),
        *([("insert", "sector")] if operation == "insert" else []),
        ("apply", operation),
    ]
    assert ctx.scene.mechanical_cad.document_json == before


def inspector_owner(ui, monkeypatch):
    ctx = context(ui, sector(extruded=False))
    owner = object.__new__(ui.general_session.GeneralSession)
    document = sector(extruded=False)
    commands = ui.general_sketch_draft.GeneralSketchDraft(
        json.dumps(document), document["active_feature"], True, journal_version=3
    )
    authoring = importlib.import_module(ports.PACKAGE + ".general_authoring")
    owner.draft = authoring.GeneralSketchAuthoringState(commands, ui_version=2)
    owner.area, owner.workspace, owner.window = ctx.area, ctx.workspace, ctx.window
    owner.proposal_capture = False
    owner.annotation_drag = owner.publication = owner.pending = None
    owner._require_idle = lambda: None
    owner.checkpoint = lambda: None
    monkeypatch.setattr(ui.constraint_ui.sketch_session, "active_session", lambda _ctx=None: owner)
    return ctx, owner


@pytest.mark.parametrize("role", ["center", "start", "end"])
def test_arc_inspector_exact_kind_id_role_selects_only_and_retains_original_commands(
    ui, monkeypatch, role
):
    ctx, owner = inspector_owner(ui, monkeypatch)
    arc = owner.commands.sketch["arcs"][0]
    owner.draft.select((("arc", arc["id"]),))
    original_commands = owner.commands
    before = original_commands.checkpoint_payload()
    op = types.SimpleNamespace(
        kind="point",
        identifier=arc[role],
        source_kind="arc",
        source_id=arc["id"],
        source_role=role.upper(),
        report=lambda *_: None,
    )
    assert ui.constraint_ui.MCAD_OT_constraint_select.execute(op, ctx) == {"FINISHED"}
    assert owner.draft.selection == [{"kind": "point", "id": arc[role]}]
    assert owner.commands is original_commands
    assert owner.commands.checkpoint_payload() == before
    assert owner.draft.proposal is None
    assert json.loads(ui.constraint_ui.draft_dispatch.dumps(owner.draft))["schema_version"] == 3


@pytest.mark.parametrize(
    "kind,role",
    [
        ("NONE", "CENTER"),
        ("circle", "CENTER"),
        ("line", "START"),
        ("arc", "NONE"),
        ("arc", "START"),
    ],
)
def test_inspector_rejects_wrong_source_kind_role_and_identity_without_inference(
    ui, monkeypatch, kind, role
):
    ctx, owner = inspector_owner(ui, monkeypatch)
    arc = owner.commands.sketch["arcs"][0]
    owner.draft.select((("arc", arc["id"]),))
    original = owner.draft
    op = types.SimpleNamespace(
        kind="point",
        identifier=arc["center"],
        source_kind=kind,
        source_id=arc["id"],
        source_role=role,
        report=lambda *_: None,
    )
    assert ui.constraint_ui.MCAD_OT_constraint_select.execute(op, ctx) == {"CANCELLED"}
    assert owner.draft is original


def test_inspector_proposal_barrier_and_checkpoint_failure_preserve_wrapper_and_command_evidence(
    ui, monkeypatch
):
    ctx, owner = inspector_owner(ui, monkeypatch)
    arc = owner.commands.sketch["arcs"][0]
    original = owner.draft
    commands = owner.commands
    owner.proposal_capture = True
    with pytest.raises(ValueError, match="unfinished"):
        ui.constraint_ui.select_bindings(owner, (("point", arc["center"]),), context=ctx)
    assert owner.draft is original and owner.commands is commands
    owner.proposal_capture = False
    owner.gesture_intent = object()
    with pytest.raises(ValueError, match="gesture"):
        ui.constraint_ui.select_bindings(owner, (("point", arc["center"]),), context=ctx)
    owner.gesture_intent = None
    monkeypatch.setattr(
        owner, "checkpoint", lambda: (_ for _ in ()).throw(RuntimeError("slot CAS"))
    )
    with pytest.raises(RuntimeError, match="slot CAS"):
        ui.constraint_ui.select_bindings(owner, (("point", arc["center"]),), context=ctx)
    assert owner.draft is original and owner.commands is commands


def test_status_keeps_trial_solve_readiness_and_native_detail_with_raw_input(ui, monkeypatch):
    ctx = context(ui)
    attempt = types.SimpleNamespace(
        remaining_dof=5,
        solver_status="underconstrained",
        profile_ready=True,
        failed_features=(("profile", "unsupported_arc_interval", "periodic range shifted"),),
    )
    owner = types.SimpleNamespace(
        draft=types.SimpleNamespace(tool="Arc", proposal=None, pending_length=None,
                                    pending_diameter=None, retired_annotation_ids=()),
        current_diagnostics=None,
        selection_mode="geometry",
        pending=None,
        current_solution_response=lambda: None,
        current_build_failure=attempt,
        current_native_build_status="not_checked",
        commands=types.SimpleNamespace(
            pending_edit=types.SimpleNamespace(raw_text="  radius + 0  ")
        ),
        annotation_notice="",
        message="",
        error="",
        can_use_tool=lambda tool: True,
    )
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _context: owner)
    monkeypatch.setattr(ui.constraint_ui, "draw_inspector", lambda *_: None)
    layout = Layout()
    ui.workspace_ui._draw_general_status(layout, ctx, owner)
    text = labels(layout)
    assert "Build failed" in text and "periodic range shifted" in text
    assert "Trial solve" not in text and "Closed profile available" not in text
    assert "Profile: unchecked" in text
    ctx.scene.mechanical_cad.show_sketch_details = True
    expanded = Layout()
    ui.workspace_ui._draw_general_status(expanded, ctx, owner)
    assert "Trial solve: 5 DoF" in labels(expanded)
    assert "unsupported_arc_interval" in labels(expanded)
    assert "'  radius + 0  '" in text and "not accepted" in text
    owner.current_build_failure = None
    owner.evidence_response = {"result": {"sketch": {"remaining_dof": 0}}}
    owner.current = True
    layout = Layout()
    ui.workspace_ui._draw_general_status(layout, ctx, owner)
    assert "Unverified · Check sketch" in labels(layout) and "Fully defined" not in labels(layout)
    assert "Downstream build: not_checked" in labels(layout)
    owner.current_solution_response = lambda: {
        "result": {
            "sketch": {"remaining_dof": 0, "status": "okay"},
            "profile_check": {"ready": True},
        }
    }
    owner.current_native_build_status = "succeeded"
    layout = Layout()
    ui.workspace_ui._draw_general_status(layout, ctx, owner)
    assert "Fully defined" in labels(layout) and "Downstream build: succeeded" in labels(layout)
    assert "Closed profile available" in labels(layout)
    ctx.scene.mechanical_cad.show_sketch_details = False
    compact = Layout()
    ui.workspace_ui._draw_general_status(compact, ctx, owner)
    assert "Fully defined" in labels(compact) and "Closed profile available" in labels(compact)
    assert "Downstream build:" not in labels(compact)
    assert "'  radius + 0  '" in labels(compact) and "not accepted" in labels(compact)


def test_palette_new_tools_have_stable_slots_named_routes_and_short_viewport_fallback(
    ui, monkeypatch
):
    base = ("SELECT", "POINTS", "LINE", "DRAW_RECTANGLE", "CIRCLE", "DIMENSION",
            "ARC", "REVERSE", "USE_POINT", "TRIM", "EXTEND", "PROJECT", "USE_SOLID_EDGE")
    assert ui.workspace_ui._GENERAL_PALETTE_TOOLS == base
    reference = None
    for contextual in (
        (),
        ("HORIZONTAL", "VERTICAL"),
        ("FIX_HERE", "FIX_ORIGIN"),
        ("REMOVE_RELATION",),
    ):
        for check in ("SKETCH_CHECK", "CANCEL_CHECK"):
            actions = base + contextual + (check, "FINISH", "CANCEL")
            bounds, positions = ui.workspace_ui.palette_layout(actions, 720)
            fixed = {action: positions[action] for action in base + ("FINISH", "CANCEL")}
            assert reference is None or fixed == reference
            reference = fixed
            assert len(ui.workspace_ui.palette_slots(actions)) == 21
            assert bounds == (8, 114, 104, 588)
            assert ui.workspace_ui.palette_layout(actions, 709) is not None
            assert ui.workspace_ui.palette_layout(actions, 710) is not None
            assert ui.workspace_ui.palette_layout(actions, 415) is None
            assert ui.workspace_ui.palette_layout(actions, 416) is not None
    ctx = context(ui)
    owner = types.SimpleNamespace(
        pending=None,
        commands=types.SimpleNamespace(has_current_solution=False),
        draft=types.SimpleNamespace(selection=[]),
        can_use_tool=lambda tool: True,
    )
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _context: owner)
    for action, tool in (("ARC", "Arc"), ("REVERSE", "Reverse"), ("USE_POINT", "UsePoint")):
        assert ui.workspace_ui._GENERAL_TOOLS[action] == tool
        assert ui.workspace_ui.available(ctx, action)
        assert ui.workspace_ui._icon(ctx, action) == 0
    monkeypatch.setattr(
        ui.workspace_ui, "_operator", lambda _action: types.SimpleNamespace(poll=lambda: True)
    )
    layout = Layout()
    ui.workspace_ui.MCAD_MT_workspace.draw(types.SimpleNamespace(layout=layout), ctx)
    routed = {
        item.action
        for kind, item in layout.entries
        if kind == "operator" and item.name == "mcad.workspace_action"
    }
    assert {"ARC", "REVERSE", "USE_POINT"} <= routed


def palette_context(*, height=706, width=966, scale=1):
    return types.SimpleNamespace(
        region=types.SimpleNamespace(type="UI", width=1, height=1),
        area=types.SimpleNamespace(
            type="VIEW_3D",
            regions=[types.SimpleNamespace(type="WINDOW", height=height, width=width, x=103, y=47)],
            spaces=types.SimpleNamespace(
                active=types.SimpleNamespace(
                    show_gizmo=True, show_gizmo_context=True, show_region_toolbar=False
                )
            ),
        ),
        preferences=types.SimpleNamespace(
            system=types.SimpleNamespace(ui_scale=scale),
            themes=[
                types.SimpleNamespace(
                    user_interface=types.SimpleNamespace(
                        wcol_regular=types.SimpleNamespace(inner=(0.2, 0.2, 0.2, 1))
                    )
                )
            ],
        ),
    )


@pytest.mark.parametrize("scale", [1, 1.2, 1.25, 1.3, 1.5, 1.8, 2])
def test_palette_responsive_thresholds_and_fixed_context_footer_slots(ui, scale):
    module = ui.workspace_ui
    base = module._GENERAL_PALETTE_TOOLS
    references = {}
    for contextual in (
        (),
        ("HORIZONTAL", "VERTICAL"),
        ("FIX_HERE", "FIX_ORIGIN"),
        ("REMOVE_RELATION",),
        ("RECOVER_RELATION",),
        ("HORIZONTAL", "VERTICAL", "FIX_HERE", "FIX_ORIGIN", "REMOVE_RELATION"),
    ):
        for check in ("SKETCH_CHECK", "CANCEL_CHECK"):
            actions = base + contextual + (check, "FINISH", "CANCEL")
            # Independent literal contract: 13 tools, five context cells,
            # Check and an aligned final Finish/Cancel pair. Native radius17.
            for columns, rows, minimum_height, width, footer in (
                (1, 21, 1046, 70, 19), (2, 11, 626, 112, 20),
                (3, 8, 500, 154, 21), (4, 6, 416, 196, 20),
            ):
                for height in (minimum_height, minimum_height + 13):
                    bounds, positions = module.palette_layout(
                        actions, height * scale, scale, width * scale)
                    top = height * scale - 132 * scale
                    left, bottom, right, _ = bounds
                    assert bounds == (8 * scale, top - (rows * 42 + 12) * scale,
                                      (62 + (columns - 1) * 42) * scale, top)
                    cells = dict(zip(base, range(13), strict=True))
                    cells.update((action, 13 + index) for index, action in enumerate(contextual))
                    cells.update({check: 18, "FINISH": footer, "CANCEL": footer + 1})
                    expected = {action: ((35 + (cell % columns) * 42) * scale,
                                        top - (27 + (cell // columns) * 42) * scale, 0)
                                for action, cell in cells.items()}
                    assert positions == expected
                    fixed = {action: positions[action] for action in base + ("FINISH", "CANCEL")}
                    fixed["check"] = positions[check]
                    assert references.setdefault((columns, height), fixed) == fixed
                    assert module.palette_layout(actions, height * scale, scale,
                                                 width * scale - 1) is None
                    for x, y, _ in positions.values():
                        assert left <= x - 17 * scale < x + 17 * scale <= right
                        assert bottom <= y - 17 * scale < y + 17 * scale <= top
                    centers = list(positions.values())
                    for index, (x, y, _) in enumerate(centers):
                        for other_x, other_y, _ in centers[index + 1:]:
                            assert (x - other_x) ** 2 + (y - other_y) ** 2 > (34 * scale) ** 2
                assert module.palette_layout(actions, minimum_height * scale - 1,
                                             scale, width * scale) is None


@pytest.mark.parametrize("scale", [1.2, 1.3])
def test_palette_single_column_uses_explicit_native_center_at_nonbinary_scales(ui, scale):
    module = ui.workspace_ui
    for actions in (
        ("FINISH", "CANCEL"),
        ("DIMENSIONS", "FINISH", "CANCEL"),
        ("NEW", "RECTANGLE", "EDIT"),
        ("NEW", "EXTRUDE", "CUT", "CHECK", "EXPORT"),
        (
            "ASSEMBLY_NEW",
            "ASSEMBLY_INSERT",
            "ASSEMBLY_FRAME",
            "ASSEMBLY_JOINT",
            "ASSEMBLY_CHECK",
            "ASSEMBLY_SAMPLE",
        ),
        module._GENERAL_PALETTE_TOOLS + ("SKETCH_CHECK", "FINISH", "CANCEL"),
        module._GENERAL_PALETTE_TOOLS
        + ("HORIZONTAL", "VERTICAL", "CANCEL_CHECK", "FINISH", "CANCEL"),
    ):
        slots = module.palette_slots(actions)
        for height in (1060 * scale, 1200 * scale):
            # The center is explicitly 35 logical pixels, not a midpoint
            # recomputation that can shift by one ULP at nonbinary scales.
            top = height - 132 * scale
            bottom = top - (len(slots) * 42 + 12) * scale
            left, right = 8 * scale, 62 * scale
            positions = {
                action: (35 * scale, top - (27 + index * 42) * scale, 0)
                for index, action in enumerate(slots)
                if action is not None
            }
            assert module.palette_layout(actions, height, scale, 966 * scale) == (
                (left, bottom, right, top),
                positions,
            )


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_palette_draw_passthrough_and_visibility_transitions_share_responsive_bounds(
    ui, monkeypatch, scale
):
    module = ui.workspace_ui
    ctx = palette_context(height=720 * scale, width=966 * scale, scale=scale)
    region = ctx.area.regions[0]
    actions = module._GENERAL_PALETTE_TOOLS + ("SKETCH_CHECK", "FINISH", "CANCEL")
    monkeypatch.setattr(module, "palette_actions", lambda _context: actions)
    disabled = {"ARC", "REVERSE", "USE_POINT", "FINISH"}
    monkeypatch.setattr(module, "available", lambda _context, action: action not in disabled)
    monkeypatch.setattr(module.palette_shapes, "load_shape", lambda _action: None)
    monkeypatch.setattr(module, "_PREVIEWS", None)
    monkeypatch.setattr(
        module,
        "Matrix",
        types.SimpleNamespace(Diagonal=lambda diagonal: types.SimpleNamespace(diagonal=diagonal)),
    )

    def new_gizmo(_kind):
        target = types.SimpleNamespace()
        return types.SimpleNamespace(
            matrix_basis=types.SimpleNamespace(), target_set_operator=lambda _identifier: target
        )

    group = types.SimpleNamespace(gizmos=types.SimpleNamespace(new=new_gizmo))
    module.MCAD_GGT_workspace_palette.setup(group, ctx)
    assert group.backdrop.hide_select
    assert all(
        gizmo.use_tooltip and not gizmo.use_event_handle_all for gizmo in group.buttons.values()
    )

    def event(x, y):
        return types.SimpleNamespace(mouse_x=region.x + x, mouse_y=region.y + y)

    # The original 966 x 706 viewport now fits. Switching width/height must not
    # leave an old one-column or second-column invisible hit target behind.
    for height, width in (
        (720, 966),
        (706, 966),
        (626, 112),
        (625, 112),
        (500, 154),
        (499, 154),
        (416, 196),
        (415, 196),
        (706, 111),
        (720, 69),
        (706, 966),
        (720, 966),
    ):
        region.height, region.width = height * scale, width * scale
        module.MCAD_GGT_workspace_palette.draw_prepare(group, ctx)
        layout = module._context_palette_layout(ctx)
        assert module.palette_bounds(ctx) == (layout[0] if layout else None)
        if layout is None:
            assert group.backdrop.hide
            assert all(gizmo.hide and gizmo.hide_select for gizmo in group.buttons.values())
            assert not module.is_palette_event(ctx, event(35 * scale, 200 * scale))
            continue
        bounds, positions = layout
        left, bottom, right, top = bounds
        assert not group.backdrop.hide
        assert group.backdrop.matrix_basis.translation == (left, bottom, 0)
        assert group.backdrop.matrix_basis.diagonal == (right - left, top - bottom, 1, 1)
        for action, gizmo in group.buttons.items():
            assert gizmo.hide == (action not in positions)
            assert gizmo.hide_select == (action not in positions or action in disabled)
            if action in positions:
                assert gizmo.matrix_basis.translation == positions[action]
                assert gizmo.scale_basis == 17
                assert gizmo.alpha == (0.28 if action in disabled else 1)
                assert module.is_palette_event(ctx, event(*positions[action][:2]))
        for x, y in ((left - 1, bottom), (right + 1, top), (left, bottom - 1), (right, top + 1)):
            assert not module.is_palette_event(ctx, event(x, y))
        if height in (706, 720):
            # Two-column reserved context cells and footer alignment spacer.
            for row, column in ((6, 1), (7, 0), (7, 1), (8, 0), (8, 1), (9, 1)):
                empty = ((35 + column * 42) * scale, top - (27 + row * 42) * scale, 0)
                assert empty not in positions.values()
                assert module.is_palette_event(ctx, event(*empty[:2]))
    for flag, value in (
        ("show_gizmo", False),
        ("show_gizmo_context", False),
        ("show_region_toolbar", True),
    ):
        space = ctx.area.spaces.active
        original = getattr(space, flag)
        setattr(space, flag, value)
        module.MCAD_GGT_workspace_palette.draw_prepare(group, ctx)
        assert module.palette_bounds(ctx) is None
        assert all(gizmo.hide and gizmo.hide_select for gizmo in group.buttons.values())
        assert not module.is_palette_event(ctx, event(35 * scale, 200 * scale))
        setattr(space, flag, original)
        module.MCAD_GGT_workspace_palette.draw_prepare(group, ctx)
        assert not group.backdrop.hide
        assert all(not group.buttons[action].hide for action in actions)
    disabled.clear()
    actions = module._GENERAL_PALETTE_TOOLS + (
        "HORIZONTAL",
        "VERTICAL",
        "CANCEL_CHECK",
        "FINISH",
        "CANCEL",
    )
    region.height = 706 * scale
    module.MCAD_GGT_workspace_palette.draw_prepare(group, ctx)
    assert group.buttons["SKETCH_CHECK"].hide and group.buttons["SKETCH_CHECK"].hide_select
    for action in actions:
        assert not group.buttons[action].hide and not group.buttons[action].hide_select
        assert group.buttons[action].alpha == 1
    assert group.buttons["CANCEL_CHECK"].matrix_basis.translation == (35 * scale, 169 * scale, 0)
    assert group.buttons["FINISH"].matrix_basis.translation == (35 * scale, 127 * scale, 0)
    assert group.buttons["CANCEL"].matrix_basis.translation == (77 * scale, 127 * scale, 0)


def test_general_palette_hidden_fallback_labels_existing_header_menu_only(ui, monkeypatch):
    module = ui.workspace_ui
    ctx = palette_context()
    owner = types.SimpleNamespace(
        pending=None,
        commands=types.SimpleNamespace(has_current_solution=False),
        draft=types.SimpleNamespace(selection=[]),
        can_use_tool=lambda _tool: True,
    )
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _context: owner)
    monkeypatch.setattr(ui.workspace, "get_role", lambda _context: "SKETCH")
    monkeypatch.setattr(
        module, "_operator", lambda _action: types.SimpleNamespace(poll=lambda: True)
    )
    for height, label in (
        (706, "CAD · Sketch"),
        (415, "CAD · Sketch · Tools"),
        (720, "CAD · Sketch"),
    ):
        ctx.area.regions[0].height = height
        layout = Layout()
        menus = []
        layout.menu = lambda name, menus=menus, **kwargs: menus.append((name, kwargs["text"]))
        module._draw_header(types.SimpleNamespace(layout=layout), ctx)
        assert menus == [("MCAD_MT_workspace", label)]
        assert [item.action for kind, item in layout.entries
                if kind == "operator" and item.name == "mcad.workspace_action"] == [
            "FINISH",
            "CANCEL",
        ]
        named = Layout()
        module.MCAD_MT_workspace.draw(types.SimpleNamespace(layout=named), ctx)
        assert set(module._GENERAL_PALETTE_TOOLS) <= {
            item.action
            for kind, item in named.entries
            if kind == "operator" and item.name == "mcad.workspace_action"
        }
    owner = None
    ctx.area.regions[0].height = 1
    layout = Layout()
    menus = []
    layout.menu = lambda name, **kwargs: menus.append((name, kwargs["text"]))
    module._draw_header(types.SimpleNamespace(layout=layout), ctx)
    assert menus == [("MCAD_MT_workspace", "CAD · Sketch")]


@pytest.mark.parametrize("variant", [{"extruded": False}, {"empty": True}, {}])
def test_insert_dialog_can_leave_retained_capture_mode_for_existing_v2_definition(
    ui, monkeypatch, variant
):
    ctx = context(ui, sector(**variant))
    op = ui.assembly_operators.MCAD_OT_assembly_insert()
    op.layout = Layout()
    op.use_working_part, op.show_help = True, False
    op.kind = "fixed"
    monkeypatch.setattr(ui.assembly_operators, "joint_fields", lambda *_: None)
    monkeypatch.setattr(ui.assembly_operators, "help_lines", lambda *_: None)
    op.draw(ctx)
    assert ("prop", ("use_working_part", True)) in op.layout.entries
    op.use_working_part = False
    op.layout = Layout()
    op.draw(ctx)
    assert ("prop", ("use_working_part", variant != {"extruded": False})) in op.layout.entries
    assert ("prop", ("part_id", True)) in op.layout.entries


@pytest.mark.parametrize("style", ["underscores", "numbers"])
def test_legacy_probe_id_collisions_keep_valid_feature_actions_available(ui, style):
    document = legacy()
    identifiers = [
        "ui_candidate" + "_" * index if style == "underscores" else f"ui_candidate_{index + 1}"
        for index in range(117)
    ]
    document["features"] = [
        dict(id=identifier, kind="sketch_circle", label="Circle", params={"radius": 2}, inputs={})
        for identifier in identifiers
    ]
    document["active_feature"] = identifiers[0]
    ctx = context(ui, document)
    before = ctx.scene.mechanical_cad.document_json
    for kind in ("sketch_rectangle", "sketch_circle", "sketch_constrained", "extrude"):
        assert not ui.operators.feature_action_reason(ctx, kind)
    assert ctx.scene.mechanical_cad.document_json == before


@pytest.mark.parametrize("variant", [{}, {"empty": True}, {"inactive": True}])
def test_supported_sector_outputs_and_assembly_capture_are_available_without_mutation(
    ui, monkeypatch, variant
):
    ctx = context(ui, sector(**variant))
    before = copy.deepcopy(vars(ctx.scene.mechanical_cad))
    monkeypatch.setattr(
        ui.workspace_ui, "_operator", lambda *_: types.SimpleNamespace(poll=lambda: True)
    )
    for action in ("CHECK", "EXPORT"):
        assert not ui.workspace_ui.action_reason(ctx, action)
        assert ui.workspace_ui.available(ctx, action)
    menu = Layout()
    ui.workspace_ui.MCAD_MT_export.draw(types.SimpleNamespace(layout=menu), ctx)
    assert all(item.enabled for kind, item in menu.entries if kind == "operator")
    limits = Layout()
    ui.workspace_ui.draw_part_limits(limits, ctx)
    assert labels(limits) == ""
    assert not ui.operators.part_action_reason(ctx, "canonical_snapshot")
    assert not ui.assembly_operators.working_part_capture_reason(ctx)
    assert ui.assembly_operators.MCAD_OT_assembly_new.poll(ctx)
    assert ui.assembly_operators.MCAD_OT_assembly_update_source.poll(ctx)
    assert vars(ctx.scene.mechanical_cad) == before


@pytest.mark.parametrize("variant", [{"extruded": False}])
def test_unsupported_sector_limits_explain_capture_and_geometry_rejections(ui, variant):
    ctx = context(ui, sector(**variant))
    before = copy.deepcopy(vars(ctx.scene.mechanical_cad))
    limits = Layout()
    ui.workspace_ui.draw_part_limits(limits, ctx)
    assert "Snapshots and Assembly capture/update are unavailable" in labels(limits)
    assert "Geometry Check and STEP/STL are unavailable" in labels(limits)
    assert ui.operators.part_action_reason(ctx, "canonical_snapshot")
    assert ui.assembly_operators.working_part_capture_reason(ctx)
    assert vars(ctx.scene.mechanical_cad) == before


def draw_history(ui, monkeypatch, report, *, current=True, draft=False, feature=True):
    ctx = context(ui, sector())
    state = ctx.scene.mechanical_cad
    state.status = "READY"
    state.show_sketch_details = True  # Explicitly inspect the collapsed diagnostic report.
    state.feature_index = 0
    state.features[0].status = "ok"
    state.features[0].sketch_report_json = json.dumps(
        {
            "status": "redundant_okay",
            "failed_constraints": ["saved_candidate"],
            "remaining_dof": 0,
        }
    )
    result = {
        "features": [{"id": state.features[0].feature_id, "status": "ok", "sketch": report}]
        if feature else []
    }
    # The current history draw captures a detached runtime projection, not the
    # saved report field nor an unbound current_part_result dictionary.
    document_json = state.document_json
    response = {"result": copy.deepcopy(result)}
    def projection(context, _records, *, with_current_check=False):
        def matches():
            return (current and context.scene is ctx.scene
                    and context.scene.mechanical_cad is state
                    and state.document_json == document_json and state.status == "READY")
        if not matches():
            return None
        return (None, response, matches) if with_current_check else (None, response)
    monkeypatch.setattr(ui.document_state, "_runtime_projection", projection)
    monkeypatch.setattr(ui.workspace, "get_role", lambda _context: "SKETCH")
    monkeypatch.setattr(ui.workspace, "has_draft", lambda _context: draft)
    monkeypatch.setattr(ui.workspace, "active_draft", lambda _context: object() if draft else None)
    monkeypatch.setattr(ui.workspace, "_LAST_ERROR", "", raising=False)
    monkeypatch.setitem(
        sys.modules, ports.PACKAGE + ".support_intent_ui",
        ports.module(ports.PACKAGE + ".support_intent_ui", draw_support_intent=ports.noop),
    )
    monkeypatch.setattr(ui.workspace_ui, "draw_suspended_draft", ports.noop)
    monkeypatch.setattr(ui.workspace_ui, "_action_button", ports.noop)
    monkeypatch.setattr(ui.workspace_ui, "_draft_actions", lambda _context: ())
    layout = Layout()
    ui.workspace_ui.MCAD_PT_workspace_history.draw(types.SimpleNamespace(layout=layout), ctx)
    return layout


@pytest.mark.parametrize("dof", [0, 5])
def test_exact_redundant_okay_history_uses_ordered_info_candidates_without_mutating_report(
    ui, monkeypatch, dof
):
    report = {
        "status": "redundant_okay",
        "remaining_dof": dof,
        "failed_constraints": ["second", "first"],
        "redundant_constraints": ["known_b", "known_a"],
    }
    before = copy.deepcopy(report)
    layout = draw_history(ui, monkeypatch, report)
    assert ("Redundancy candidates: second, first", "INFO") in layout.icons
    assert ("Redundant constraints: known_b, known_a", "INFO") in layout.icons
    assert not any("Conflict candidates:" in text for text, _ in layout.icons)
    assert not any(icon == "ERROR" for text, icon in layout.icons if "second" in text)
    assert ("Fully defined" if dof == 0 else str(dof) + " DoF") in labels(layout)
    assert report == before


@pytest.mark.parametrize("status", ["okay", "redundant_okay", "inconsistent", "too_many_unknowns"])
@pytest.mark.parametrize("empty", [True, False])
def test_history_candidate_wording_depends_only_on_exact_status(ui, monkeypatch, status, empty):
    report = {
        "status": status,
        "remaining_dof": 0,
        "failed_constraints": [] if empty else ["candidate"],
    }
    layout = draw_history(ui, monkeypatch, report)
    candidates = [(text, icon) for text, icon in layout.icons if "candidates:" in text]
    expected = (
        []
        if empty
        else [
            ("Redundancy candidates: candidate", "INFO")
            if status == "redundant_okay"
            else ("Conflict candidates: candidate", "ERROR")
        ]
    )
    assert candidates == expected


@pytest.mark.parametrize("variant", ["no_current", "no_feature", "no_report", "draft"])
def test_saved_candidate_json_never_becomes_current_history(ui, monkeypatch, variant):
    report = (
        None
        if variant == "no_report"
        else {"status": "redundant_okay", "failed_constraints": ["live_candidate"]}
    )
    layout = draw_history(
        ui,
        monkeypatch,
        report,
        current=variant != "no_current",
        feature=variant != "no_feature",
        draft=variant == "draft",
    )
    assert "saved_candidate" not in labels(layout) and "live_candidate" not in labels(layout)
    if variant != "draft":
        assert "Sketch solve needs verification" in labels(layout)
    else:
        assert "Editing rectangle" in labels(layout)


def test_duplicate_feature_names_have_consistent_distinct_choice_labels(ui, monkeypatch):
    document = legacy()
    document["features"] = [
        {"id": "sketch_1", "label": "Sketch", "kind": "sketch_circle"},
        {"id": "sketch_2", "label": "Sketch", "kind": "sketch_constrained"},
        {"id": "solid_1", "label": "Solid", "kind": "extrude"},
        {"id": "solid_2", "label": "Solid", "kind": "sweep"},
    ]
    before = copy.deepcopy(document)
    state = types.SimpleNamespace(
        features=[
            types.SimpleNamespace(feature_id=f["id"], label=f["label"], kind=f["kind"], status="ok")
            for f in document["features"]
        ]
    )
    ctx = types.SimpleNamespace(scene=types.SimpleNamespace(mechanical_cad=state))
    monkeypatch.setattr(ui.operators, "feature_action_reason", lambda *args, **kwargs: "")
    monkeypatch.setattr(ui.solid_operators, "_read_document", lambda _state: document)
    for callback, expected in (
        (
            "_profile_choices",
            [("sketch_1", "Sketch [sketch_1]"), ("sketch_2", "Sketch [sketch_2]")],
        ),
        ("_solid_choices", [("solid_1", "Solid [solid_1]"), ("solid_2", "Solid [solid_2]")]),
    ):
        ordinary = getattr(ui.operators, callback)(None, ctx)
        shared = getattr(ui.solid_operators, callback)(None, ctx)
        assert [row[:2] for row in ordinary] == expected
        assert [row[:2] for row in shared] == expected
        assert getattr(ui.solid_operators, callback)(None, ctx) == shared
    assert document == before


def test_new_assembly_preselects_required_ground_without_mutating_until_apply(ui, monkeypatch):
    ctx = context(ui)
    before_part = ctx.scene.mechanical_cad.document_json
    before_assembly = ctx.scene.mechanical_cad_assembly.document_json
    dialogs, candidates = [], []
    ctx.window_manager = types.SimpleNamespace(
        invoke_props_dialog=lambda operator, **kwargs: dialogs.append(operator) or {"RUNNING_MODAL"}
    )
    op = ui.assembly_operators.MCAD_OT_assembly_new()
    op.name, op.instance_name, op.show_help = "Assembly", "Base", False
    op.report = lambda *_: None
    op.grounded = False  # Reused operator state must not reintroduce the checkbox trap.
    assert op.invoke(ctx, None) == {"RUNNING_MODAL"}
    assert dialogs == [op] and op.grounded is True
    op.layout = Layout()
    op.draw(ctx)
    assert ("prop", ("grounded", True)) in op.layout.entries
    op.cancel(ctx)
    assert ctx.scene.mechanical_cad.document_json == before_part
    assert ctx.scene.mechanical_cad_assembly.document_json == before_assembly
    assert op.invoke(ctx, None) == {"RUNNING_MODAL"}
    monkeypatch.setattr(
        ui.assembly_operators, "canonical_working_part", lambda _ctx: json.loads(before_part)
    )
    monkeypatch.setattr(ui.assembly_operators, "activate_assembly_workspace", lambda *_: None)
    op.apply = lambda _ctx, candidate: candidates.append(candidate) or {"FINISHED"}
    assert op.execute(ctx) == {"FINISHED"}
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["grounded_instance"] == candidate["instances"][0]["id"]
    assert candidate["ground"] == ui.assembly_operators.edit.origin_frame()
    assert candidate["joints"] == []
    assert ctx.scene.mechanical_cad.document_json == before_part
    op.grounded = False
    assert op.execute(ctx) == {"CANCELLED"}
    assert len(candidates) == 1


def test_solid_edge_palette_availability_and_dispatch_respect_draft_and_operator_poll(
    ui, monkeypatch
):
    """Exercise the actual palette gate and dispatcher, not direct picker invocation."""
    ctx = context(ui)
    module = ui.workspace_ui
    state = {"draft": object(), "operator_ready": True, "suspended": False}
    calls = []
    reports = []

    class RegisteredPicker:
        def get_rna_type(self):
            return object()

        def poll(self):
            # Blender delegates this to the registered picker poll, which owns
            # current-display and active general-sketch ownership requirements.
            return state["operator_ready"]

        def __call__(self, mode, **properties):
            calls.append((mode, properties))
            return {"RUNNING_MODAL"}

    monkeypatch.setattr(ui.workspace, "active_draft", lambda _ctx: state["draft"])
    monkeypatch.setattr(
        ui.workspace, "suspended_draft", lambda _ctx: {"present": state["suspended"]}
    )
    monkeypatch.setattr(
        ui.bpy,
        "ops",
        types.SimpleNamespace(mcad=types.SimpleNamespace(use_solid_edge=RegisteredPicker())),
        raising=False,
    )
    action = module.MCAD_OT_workspace_action()
    action.action = "USE_SOLID_EDGE"
    action.report = lambda levels, message: reports.append((levels, message))
    assert "USE_SOLID_EDGE" in module._GENERAL_PALETTE_TOOLS
    assert module.available(ctx, action.action)
    assert action.execute(ctx) == {"FINISHED"}
    assert calls == [("INVOKE_DEFAULT", {})]

    for draft, operator_ready, suspended in (
        (object(), False, False),  # stale display, busy/foreign/invalid owner
        (None, True, False),  # never offer a sketch action outside a draft
        (None, True, True),  # suspended draft is not an active owner
    ):
        state.update(draft=draft, operator_ready=operator_ready, suspended=suspended)
        assert not module.available(ctx, action.action)
        assert action.execute(ctx) == {"CANCELLED"}
    assert calls == [("INVOKE_DEFAULT", {})]
    assert len(reports) == 3
