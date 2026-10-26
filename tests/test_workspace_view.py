"""Native-free policy tests; do not establish Blender maximize/draft behavior."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def view(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    name = "mcad_workspace_view_test"
    package = ModuleType(name)
    package.__path__ = [str(root / "blender_addon/mechanical_cad_blender")]
    monkeypatch.setitem(sys.modules, name, package)
    workspace = ModuleType(name + ".workspace")
    workspace.is_cad_workspace = lambda context: context.cad
    workspace.active_draft = lambda context: getattr(context, "draft", None)
    monkeypatch.setitem(sys.modules, workspace.__name__, workspace)
    native = Mock(return_value={"FINISHED"})
    native.poll.return_value = True
    bpy = SimpleNamespace(
        types=SimpleNamespace(Operator=object),
        ops=SimpleNamespace(screen=SimpleNamespace(screen_full_area=native)),
    )
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    spec = importlib.util.spec_from_file_location(
        name + ".workspace_view", package.__path__[0] + "/workspace_view.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, native


def context(**changes):
    values = dict(
        cad=True, screen=SimpleNamespace(show_fullscreen=False),
        area=SimpleNamespace(type="VIEW_3D"), window=object(),
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_native_maximize_keeps_sidebar_and_never_rebuilds_layout(view):
    module, native = view
    before = context()
    assert module.MCAD_OT_focus_workspace.poll(before)
    assert module.MCAD_OT_focus_workspace().execute(before) == {"FINISHED"}
    native.assert_called_once_with(use_hide_panels=False)
    assert module.focus_label(before) == "Focus CAD"
    before.screen.show_fullscreen = True
    assert module.focus_label(before) == "Restore Layout"


@pytest.mark.parametrize("changes", [
    {"cad": False}, {"area": None}, {"area": SimpleNamespace(type="PROPERTIES")},
    {"window": None},
])
def test_focus_never_operates_on_unrelated_editor(view, changes):
    module, native = view
    assert not module.MCAD_OT_focus_workspace.poll(context(**changes))
    native.assert_not_called()


def test_native_unavailable_is_disabled(view):
    module, native = view
    native.poll.return_value = False
    assert not module.MCAD_OT_focus_workspace.poll(context())


@pytest.mark.parametrize("status,error,draft,expected", [
    ("DIRTY", "", object(), True),
    ("DIRTY", "Regenerate to build this document.", object(), True),
    ("DIRTY", "Regenerate to build this document.", None, False),
    ("DIRTY", "Input changed; repair the support reference.", object(), False),
    ("FAILED", "", object(), False),
    ("READY", "", object(), False),
    ("STALE", "", object(), False),
])
def test_only_benign_dirty_draft_notice_is_compact(view, status, error, draft, expected):
    module, _ = view
    state = SimpleNamespace(status=status, error=error)
    assert module.compact_draft_part_status(state, draft) is expected
    assert (state.status, state.error) == (status, error)


def test_focus_button_has_explicit_restore_label_and_compact_header_variant(view):
    module, _ = view
    layout = Mock()
    ctx = context()
    module.draw_focus(layout, ctx)
    layout.operator.assert_called_with(
        "mcad.focus_workspace", text="Focus CAD", icon="FULLSCREEN_ENTER"
    )
    ctx.screen.show_fullscreen = True
    module.draw_focus(layout, ctx)
    layout.operator.assert_called_with(
        "mcad.focus_workspace", text="Restore Layout", icon="FULLSCREEN_EXIT"
    )
    module.draw_focus(layout, ctx, compact=True)
    layout.operator.assert_called_with(
        "mcad.focus_workspace", text="", icon="FULLSCREEN_EXIT"
    )


def test_focus_saves_active_draft_before_native_transition(view):
    module, native = view
    owner = Mock()
    owner.suspend.return_value = True
    operator = module.MCAD_OT_focus_workspace()
    operator.report = Mock()
    assert operator.execute(context(draft=owner)) == {"FINISHED"}
    owner.checkpoint.assert_called_once_with()
    owner.suspend.assert_called_once()
    native.assert_called_once_with(use_hide_panels=False)
    assert "Resume" in operator.report.call_args.args[1]


@pytest.mark.parametrize("failure", ["checkpoint", "suspend"])
def test_failed_draft_save_never_changes_layout(view, failure):
    module, native = view
    owner = Mock()
    if failure == "checkpoint":
        owner.checkpoint.side_effect = ValueError("conflicting saved draft")
    else:
        owner.suspend.return_value = False
    operator = module.MCAD_OT_focus_workspace()
    operator.report = Mock()
    assert operator.execute(context(draft=owner)) == {"CANCELLED"}
    native.assert_not_called()
    assert operator.report.call_args.args[0] == {"ERROR"}
