"""Primary edit launchers precede unbounded panel content, without duplicates."""

import ast
from pathlib import Path

ADDON = Path(__file__).resolve().parents[2] / "blender_addon" / "mechanical_cad_blender"


def draw_source(module, panel):
    tree = ast.parse((ADDON / module).read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == panel)
    return next(
        node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "draw"
    )


def call_lines(node, argument):
    return [
        call.lineno
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and any(isinstance(arg, ast.Constant) and arg.value == argument for arg in call.args)
    ]


def history_lines(node):
    return [
        call.lineno for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        and call.func.id == "draw_history"
    ]


def test_standard_sidebar_has_one_primary_edit_above_history_and_parameters():
    draw = draw_source("panels.py", "MCAD_PT_main")
    edit = call_lines(draw, "mcad.edit_solid_feature")
    display = call_lines(draw, "mcad.activate_feature")
    history = history_lines(draw)
    assert len(edit) == len(display) == len(history) == 1
    assert edit[0] < history[0] and display[0] < history[0]
    parameter_loop = next(
        node
        for node in ast.walk(draw)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Attribute)
        and node.iter.attr == "parameters"
    )
    assert history[0] < parameter_loop.lineno


def test_workspace_has_one_primary_edit_per_kind_above_history():
    draw = draw_source("workspace_ui.py", "MCAD_PT_workspace_history")
    history = history_lines(draw)
    for action in ("EDIT_FEATURE", "EDIT", "mcad.activate_feature"):
        lines = call_lines(draw, action)
        assert len(lines) == len(history) == 1
        assert lines[0] < history[0]


def test_projection_repair_launcher_precedes_history_in_both_sidebars():
    for module, panel in (
        ("panels.py", "MCAD_PT_main"),
        ("workspace_ui.py", "MCAD_PT_workspace_history"),
    ):
        draw = draw_source(module, panel)
        launchers = [
            call.lineno
            for call in ast.walk(draw)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "draw_projection_repair"
        ]
        assert len(launchers) == 1
        assert launchers[0] < history_lines(draw)[0]


def test_project_geometry_palette_follows_active_draft_and_operator_poll():
    from types import SimpleNamespace

    tree = ast.parse((ADDON / "workspace_ui.py").read_text())
    available = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "available"
    )
    state = {"draft": object(), "poll": True}
    namespace = {
        "_ACTIONS": {"PROJECT"},
        "workspace": SimpleNamespace(
            is_cad_workspace=lambda context: True,
            active_draft=lambda context: state["draft"],
            suspended_draft=lambda context: {"present": False},
        ),
        "_GENERAL_TOOLS": {},
        "_CONSTRAINT_ACTIONS": {},
        "_SKETCH_OPERATOR_ARGS": {},
        "action_reason": lambda context, action: "",
        "_operator": lambda action: SimpleNamespace(poll=lambda: state["poll"]),
    }
    exec(
        compile(ast.Module(body=[available], type_ignores=[]), "workspace_ui.available", "exec"),
        namespace,
    )
    assert namespace["available"](None, "PROJECT")
    state["poll"] = False
    assert not namespace["available"](None, "PROJECT")
    state["poll"] = True
    state["draft"] = None
    assert not namespace["available"](None, "PROJECT")


def test_projection_chooser_has_readable_width_and_short_guidance():
    tree = ast.parse((ADDON / "general_viewport.py").read_text())
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MCAD_OT_project_sketch_geometry"
    )
    invoke = next(
        node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "invoke"
    )
    calls = [
        node
        for node in ast.walk(invoke)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "invoke_props_dialog"
    ]
    assert len(calls) == 1
    assert any(
        kw.arg == "width" and isinstance(kw.value, ast.Constant) and kw.value.value == 500
        for kw in calls[0].keywords
    )
    draw = next(
        node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "draw"
    )
    labels = [
        kw.value.value
        for node in ast.walk(draw)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "label"
        for kw in node.keywords
        if kw.arg == "text" and isinstance(kw.value, ast.Constant)
    ]
    assert len(labels) == 4 and all(len(label) <= 55 for label in labels)
