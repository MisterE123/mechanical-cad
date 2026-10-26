"""Pure source-review owner contracts; not native GPU or interactive qualification."""

import ast
import copy
import importlib
import math
import sys
import types
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
SOURCE = ADDON / "assembly_source_update_preview.py"
PACKAGE = "source_update_overlay_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
overlay = importlib.import_module(PACKAGE + ".assembly_joint_overlay")


@pytest.fixture
def host():
    tree = ast.parse(SOURCE.read_text())
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    bpy = NS(
        types=NS(SpaceView3D=NS(draw_handler_remove=Mock())),
        app=NS(timers=NS(is_registered=Mock(return_value=True), unregister=Mock())),
    )
    state = NS(
        _assert_current=Mock(),
        display_is_current=Mock(return_value=True),
        commit_candidate=Mock(),
        require_idle=Mock(),
    )
    pending = NS(cancel=Mock())
    viewport = NS(
        active=Mock(return_value=None),
        _safe_rect=lambda o: (0, 0, 600, 500),
        NAVIGATION_EVENTS={"MIDDLEMOUSE"},
        _screen_xy=lambda o, e: e.point,
    )
    registry = types.ModuleType("source_preview_registry_test")
    registry_path = ADDON / "assembly_source_preview_registry.py"
    exec(compile(registry_path.read_text(), str(registry_path), "exec"), registry.__dict__)
    env = dict(
        assembly_source_preview_registry=registry,
        active=registry.active,
        bpy=bpy,
        Operator=object,
        copy=copy,
        math=math,
        overlay=overlay,
        assembly_joint_viewport=viewport,
        assembly_state=state,
        assembly_pending=pending,
        execution_lease=NS(is_busy=Mock(return_value=False), BUSY_MESSAGE="busy"),
        BridgeError=ValueError,
    )
    exec(compile(tree, str(SOURCE), "exec"), env)
    owner = env["SourceUpdatePreview"].__new__(env["SourceUpdatePreview"])
    region = NS(type="WINDOW")
    area = NS(type="VIEW_3D", regions=[region], header_text_set=Mock(), tag_redraw=Mock())
    scene = NS(
        mechanical_cad_assembly=NS(document_json="accepted"),
        mechanical_cad=NS(document_json="part"),
    )
    layer, workspace = object(), object()
    window = NS(workspace=workspace, screen=NS(areas=[area]))
    manager = NS(windows=[window], event_timer_remove=Mock())
    context = NS(
        scene=scene,
        window=window,
        area=area,
        region=region,
        view_layer=layer,
        workspace=workspace,
        mode="OBJECT",
        window_manager=manager,
    )
    owner.__dict__.update(
        scene=scene,
        window=window,
        area=area,
        region=region,
        view_layer=layer,
        workspace=workspace,
        manager=manager,
        snapshot={"fields": {"document_json": "accepted"}, "working_part": "part"},
        alive=True,
        finished=False,
        committing=False,
        pending=None,
        candidate={"parts": [{"id": "part"}]},
        expectation="exact",
        ghost_positions=((1, 2, 3),),
        handlers=["view", "pixel"],
        timer="timer",
        watchdog=lambda: None,
        affected=[f"Instance {i}" for i in range(8)],
        revisions="old → new",
        page=0,
        error="",
        hover="",
        hint="",
        ui_scale=1,
        message="Preview ready",
    )
    registry._ACTIVE = owner
    bpy.context = context
    return NS(
        env=env,
        owner=owner,
        context=context,
        bpy=bpy,
        state=state,
        pending=pending,
        viewport=viewport,
    )


def test_cancel_releases_resources_once_and_never_publishes(host):
    o = host.owner
    o.pending = token = object()
    o.cancel()
    o.cancel()
    assert not o.alive and not o.finished and not o.ready()
    assert o.expectation is None and not o.ghost_positions and not o.handlers
    assert host.env["assembly_source_preview_registry"]._ACTIVE is None
    host.pending.cancel.assert_called_once_with(token, "Source update preview cancelled")
    assert host.bpy.types.SpaceView3D.draw_handler_remove.call_count == 2
    host.context.window_manager.event_timer_remove.assert_called_once_with("timer")
    host.bpy.app.timers.unregister.assert_called_once()
    host.state.commit_candidate.assert_not_called()
    assert not o.apply(host.context)


@pytest.mark.parametrize(
    "mutation",
    ["assembly", "part", "window", "layer", "mode", "workspace", "area", "region", "closed"],
)
def test_stale_binding_refuses_apply_and_clears_preview(host, mutation):
    c, o = host.context, host.owner
    if mutation == "assembly":
        c.scene.mechanical_cad_assembly.document_json = "new"
    if mutation == "part":
        c.scene.mechanical_cad.document_json = "new"
    if mutation == "window":
        c.window = object()
    if mutation == "layer":
        c.view_layer = object()
    if mutation == "mode":
        c.mode = "EDIT_MESH"
    if mutation == "workspace":
        o.window.workspace = object()
    if mutation == "area":
        o.area.type = "TEXT_EDITOR"
    if mutation == "region":
        o.area.regions = []
    if mutation == "closed":
        o.manager.windows = []
    assert not o.apply(c)
    host.state.commit_candidate.assert_not_called()
    assert o.expectation is None and not o.ghost_positions
    assert "changed" in o.error


@pytest.mark.parametrize("reason", ["pending", "display", "snapshot", "commit"])
def test_unready_or_rejected_apply_never_finishes(host, reason):
    o = host.owner
    if reason == "pending":
        o.pending = object()
    if reason == "display":
        host.state.display_is_current.return_value = False
    if reason == "snapshot":
        host.state._assert_current.side_effect = ValueError("stale")
    if reason == "commit":
        host.state.commit_candidate.side_effect = ValueError("replay refused")
    assert not o.apply(host.context)
    assert o.alive and not o.finished and not o.committing and o.expectation is None
    assert host.state.commit_candidate.call_count == int(reason == "commit")


def test_apply_is_detached_exact_and_one_shot(host):
    o = host.owner
    before = copy.deepcopy(o.candidate)
    assert o.apply(host.context)
    assert not o.apply(host.context)
    host.state.commit_candidate.assert_called_once_with(
        host.context, before, expected_json="accepted", expected_source_preview="exact"
    )
    assert host.state.commit_candidate.call_args.args[1] is not o.candidate
    assert o.finished and not o.alive and o.candidate == before
    assert host.env["assembly_source_preview_registry"]._ACTIVE is None


@pytest.mark.parametrize(
    "page,expected", [(-10, [0, 1, 2]), (0, [0, 1, 2]), (1, [3, 4, 5]), (2, [6, 7]), (999, [6, 7])]
)
def test_layout_pages_three_names_without_mutating_page(host, page, expected):
    o = host.owner
    o.page = page
    before = copy.copy(o.__dict__)
    panel = o.panel_layout()
    assert [label.text for label in panel.labels if label.text.startswith("Instance ")] == [
        f"Instance {i}" for i in expected
    ]
    assert o.__dict__ == before
    buttons = {b.action: b for b in panel.buttons}
    assert buttons["previous"].enabled == (expected[0] > 0)
    assert buttons["next"].enabled == (expected[-1] < 7)
    for b in panel.buttons:
        left, bottom, right, top = panel.bounds
        assert left <= b.bounds[0] <= b.bounds[2] <= right
        assert bottom <= b.bounds[1] <= b.bounds[3] <= top


@pytest.mark.parametrize("safe", [(0, 0, 180, 150), (0, 0, 100, 64), (0, 0, 600, 250)])
def test_narrow_panel_keeps_cancel_and_no_apply(host, safe):
    host.viewport._safe_rect = lambda o: safe
    panel = host.owner.panel_layout()
    assert any(b.action == "cancel" and b.enabled for b in panel.buttons)
    assert not any(b.action == "apply" and b.enabled for b in panel.buttons)
    for b in panel.buttons:
        assert safe[0] <= b.bounds[0] <= b.bounds[2] <= safe[2]
        assert safe[1] <= b.bounds[1] <= b.bounds[3] <= safe[3]


@pytest.mark.parametrize("other", ["source", "joint", "lease"])
def test_independent_owners_exclude_preview(host, other):
    if other != "source":
        host.env["assembly_source_preview_registry"]._ACTIVE = None
    if other == "joint":
        host.viewport.active.return_value = object()
    if other == "lease":
        host.env["execution_lease"].is_busy.return_value = True
    with pytest.raises(ValueError, match="existing Assembly preview|busy"):
        host.env["SourceUpdatePreview"](host.context)
    host.state.commit_candidate.assert_not_called()


def event(kind, value="PRESS", **kw):
    return NS(type=kind, value=value, ctrl=False, point=(0, 0), **kw)


@pytest.mark.parametrize(
    "kind,expected", [("ESC", {"CANCELLED"}), ("MIDDLEMOUSE", {"PASS_THROUGH"})]
)
def test_modal_cancel_or_navigation_never_publishes(host, kind, expected):
    op = host.env["MCAD_OT_assembly_source_update_preview"]()
    op.owner = host.owner
    assert op.modal(host.context, event(kind)) == expected
    host.state.commit_candidate.assert_not_called()


def test_stale_modal_cancels_without_poll_or_apply(host):
    op = host.env["MCAD_OT_assembly_source_update_preview"]()
    op.owner = host.owner
    host.context.mode = "EDIT_MESH"
    assert op.modal(host.context, event("TIMER")) == {"CANCELLED"}
    host.state.commit_candidate.assert_not_called()


def test_draw_is_cached_and_has_no_model_or_mesh_traversal():
    tree = ast.parse(SOURCE.read_text())
    functions = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and n.name in {"_draw_view", "_draw_pixel", "draw_context", "panel_layout"}
    ]
    for fn in functions:
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {
                    "mesh",
                    "vertices",
                    "polygons",
                    "commit_candidate",
                    "poll",
                    "_show_response",
                }
            if isinstance(node, ast.Name):
                assert node.id not in {
                    "boundary_edges",
                    "transform_points",
                    "source_preview_fingerprint",
                }
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                assert not any(isinstance(t, (ast.Attribute, ast.Subscript)) for t in targets)


def test_interactive_update_routes_explicitly_to_preview_not_commit():
    tree = ast.parse((ADDON / "assembly_operators.py").read_text())
    cls = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "MCAD_OT_assembly_update_source"
    )
    invoke = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "invoke")
    calls = [n for n in ast.walk(invoke) if isinstance(n, ast.Call)]
    assert len(calls) == 1
    assert ast.unparse(calls[0].func) == "bpy.ops.mcad.assembly_source_update_preview"
    assert ast.literal_eval(calls[0].args[0]) == "INVOKE_DEFAULT"


@pytest.mark.parametrize("child_result", [{"RUNNING_MODAL"}, {"CANCELLED"}])
def test_launcher_never_finishes_or_registers_repeat_execute(child_result):
    source = ADDON / "assembly_operators.py"
    cls = next(n for n in ast.parse(source.read_text()).body
               if isinstance(n, ast.ClassDef) and n.name == "MCAD_OT_assembly_update_source")
    invoke = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "invoke")
    launch = Mock(return_value=child_result)
    env = {"bpy": NS(ops=NS(mcad=NS(assembly_source_update_preview=launch)))}
    exec(compile(ast.Module(body=[invoke], type_ignores=[]), str(source), "exec"), env)
    assert env["invoke"](object(), object(), object()) == {"CANCELLED"}
    launch.assert_called_once_with("INVOKE_DEFAULT")


def test_ctrl_z_cancels_then_passes_undo_to_host(host):
    op = host.env["MCAD_OT_assembly_source_update_preview"]()
    op.owner = host.owner
    undo = event("Z")
    undo.ctrl = True
    assert op.modal(host.context, undo) == {"CANCELLED", "PASS_THROUGH"}
    host.state.commit_candidate.assert_not_called()
    assert not host.owner.alive


@pytest.mark.parametrize("action", ["previous", "next", "apply", "cancel"])
def test_modal_buttons_respect_enabled_state_and_explicit_apply(host, action):
    o = host.owner
    if action == "next":
        o.page = 2  # Last page cannot advance.
    if action == "apply":
        o.expectation = None  # Pending/refused Apply cannot publish.
    panel = o.panel_layout()
    button = next(b for b in panel.buttons if b.action == action)
    point = ((button.bounds[0] + button.bounds[2]) / 2, (button.bounds[1] + button.bounds[3]) / 2)
    op = host.env["MCAD_OT_assembly_source_update_preview"]()
    op.owner = o
    click = event("LEFTMOUSE")
    click.point = point
    page = o.page
    result = op.modal(host.context, click)
    assert result == ({"CANCELLED"} if action == "cancel" else {"RUNNING_MODAL"})
    assert o.page == page
    host.state.commit_candidate.assert_not_called()


def test_preview_result_error_cannot_become_apply_authority(host):
    o = host.owner
    o.pending = object()
    host.pending.poll = Mock(side_effect=ValueError("exact result rejected"))
    o.tick(host.context)
    assert o.pending is None and o.expectation is None and not o.ghost_positions
    assert o.error == "exact result rejected" and not o.ready()
    assert not o.apply(host.context)
    host.state.commit_candidate.assert_not_called()


def test_start_error_clears_shared_owner_before_propagating(host):
    registry = host.env["assembly_source_preview_registry"]
    registry._ACTIVE = None
    host.owner.prepare_pending = Mock(side_effect=ValueError("prepare failed"))
    with pytest.raises(ValueError, match="prepare failed"):
        host.owner.start(host.context)
    assert registry._ACTIVE is None and registry.active() is None
    assert not host.owner.alive
    host.state.commit_candidate.assert_not_called()


@pytest.mark.parametrize("reason", ["Opening a file", "History changed", "Add-on disabled"])
def test_lifecycle_cancel_uses_and_clears_shared_registry(host, reason):
    registry = host.env["assembly_source_preview_registry"]
    assert host.env["active"] is registry.active
    assert registry.active() is host.owner
    assert host.env["cancel_active"](reason)
    assert registry._ACTIVE is None and registry.active() is None
    assert not host.env["cancel_active"](reason)
    host.state.commit_candidate.assert_not_called()


def test_registration_lifecycle_routes_source_preview_cleanup():
    tree = ast.parse((ADDON / "registration.py").read_text())
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in ("_before_blend_load", "_before_history_change", "unregister"):
        assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id == "_retire_native_jobs"
                   for node in ast.walk(functions[name]))
    assert any(isinstance(node, ast.Call)
               and ast.unparse(node.func) == "assembly_source_update_preview.cancel_active"
               for node in ast.walk(functions["_retire_native_jobs"]))
