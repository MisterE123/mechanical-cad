"""Run with native Blender --background --python-exit-code 1 --python this_file."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import workspace, workspace_ui  # noqa: E402
from mechanical_cad_blender.operators import MCAD_OT_focus, MCAD_OT_show_scene  # noqa: E402

addon.register()
workspace.register()
workspace_ui.register()
workspace_ui.register()
assert workspace_ui._REGISTERED
view_controls = []
workspace_ui._draw_part_view_controls(
    SimpleNamespace(operator=lambda name, **kwargs: view_controls.append((name, kwargs)))
)
assert view_controls == [
    ("mcad.focus_result", {"text": "Focus Part", "icon": "VIEWZOOM"}),
    ("mcad.show_scene", {"text": "Whole Scene", "icon": "SCENE_DATA"}),
]
assert "REGISTER" in MCAD_OT_focus.bl_options
assert "REGISTER" in MCAD_OT_show_scene.bl_options
assert len(workspace_ui._PREVIEWS) >= 16
assert workspace.get_role(bpy.context) is None
assert not workspace_ui.palette_actions(bpy.context)
source = bpy.context.workspace
name = source.name
source[workspace.OWNER_KEY] = workspace.OWNER
source[workspace.ROLE_KEY] = "PART"
assert workspace.get_role(bpy.context) == "PART"
assert workspace.find_workspace("PART") == source
assert workspace_ui.palette_actions(bpy.context) == ("NEW", "EXTRUDE", "CUT", "CHECK", "EXPORT")
source[workspace.ROLE_KEY] = "ASSEMBLY"
assembly_actions = (
    "ASSEMBLY_NEW",
    "ASSEMBLY_INSERT",
    "ASSEMBLY_FRAME",
    "ASSEMBLY_JOINT",
    "ASSEMBLY_CHECK",
    "ASSEMBLY_SAMPLE",
)
assert workspace_ui.palette_actions(bpy.context) == assembly_actions
for action in assembly_actions:
    assert workspace_ui._operator(action) is not None
    assert workspace_ui._icon(bpy.context, action) == 0  # legible native glyph fallback
    assert not workspace_ui.available(bpy.context, action)  # empty Part and Assembly
assert hasattr(bpy.context.scene, "mechanical_cad_assembly")


class FakeGizmo:
    shape = None

    def target_set_operator(self, name):
        return SimpleNamespace()


class FakeGizmos:
    def new(self, name):
        return FakeGizmo()


palette = SimpleNamespace(gizmos=FakeGizmos())
workspace_ui.MCAD_GGT_workspace_palette.setup(palette, bpy.context)
assert palette.shape_actions == (set(workspace_ui.palette_shapes.ACTIONS) - {"NEW", "EDIT"}) | {
    "RECTANGLE"
}
for action, gizmo in palette.buttons.items():
    if action in palette.shape_actions:
        assert isinstance(gizmo.shape, bytes) and gizmo.draw_options == {"BACKDROP"}
        assert not hasattr(gizmo, "icon") and not hasattr(gizmo, "icon_value")
    else:
        assert action.startswith("ASSEMBLY_") or action in {
            "NEW",
            "EDIT",
            *workspace_ui._GENERAL_TOOLS,
            *workspace_ui._CONSTRAINT_ACTIONS,
        }
with patch.object(workspace_ui.palette_shapes, "load_shape", return_value=None):
    fallback = SimpleNamespace(gizmos=FakeGizmos())
    workspace_ui.MCAD_GGT_workspace_palette.setup(fallback, bpy.context)
    assert not fallback.shape_actions
    assert all(button.shape is None for button in fallback.buttons.values())
source[workspace.ROLE_KEY] = "SKETCH"
assert workspace_ui.palette_actions(bpy.context) == ("NEW", "RECTANGLE", "EDIT")
reorder = {
    "window": bpy.context.window,
    "scene": bpy.context.scene,
    "ticks": 0,
    "phase": "reorder",
    "reorder": ["SKETCH"],
}
assert workspace._step(reorder) is False
assert not reorder["reorder"]
assert bpy.context.workspace == source  # native reordering does not switch screens
assert workspace._step(reorder) is False and reorder["phase"] == "finish"
cancel_calls = []
workspace.set_draft_handlers(
    lambda context: SimpleNamespace(can_edit_dimensions=True),
    lambda reason, context=None: cancel_calls.append(reason),
)
assert workspace_ui.palette_actions(bpy.context) == ("DIMENSIONS", "FINISH", "CANCEL")
with patch.object(
    workspace, "active_draft", return_value=SimpleNamespace(can_edit_dimensions=False)
):
    assert workspace_ui.palette_actions(bpy.context) == ("FINISH", "CANCEL")
with patch.object(workspace, "active_draft", return_value=object()):
    assert workspace_ui.palette_actions(bpy.context) == ("FINISH", "CANCEL")

workspace.request_workspace(bpy.context, "SKETCH")
assert not cancel_calls and not workspace._JOBS
workspace.request_workspace(bpy.context, "SKETCH", on_ready=lambda context: None)
assert cancel_calls and workspace._JOBS
workspace.cancel_pending_setup()
workspace.set_draft_handlers()
assert not workspace_ui.is_palette_event(SimpleNamespace(area=None), None)
fake_region = SimpleNamespace(type="WINDOW", height=500, width=966, x=0, y=0)
fake_context = SimpleNamespace(
    workspace={workspace.OWNER_KEY: workspace.OWNER, workspace.ROLE_KEY: "PART"},
    area=SimpleNamespace(
        regions=[fake_region],
        type="VIEW_3D",
        spaces=SimpleNamespace(active=SimpleNamespace(show_gizmo=True)),
    ),
    preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=2.0)),
)
assert workspace_ui.palette_bounds(fake_context) is None
assert not workspace_ui.is_palette_event(fake_context, SimpleNamespace(mouse_x=30, mouse_y=200))
fake_context.preferences.system.ui_scale = 1.0
bounds = workspace_ui.palette_bounds(fake_context)
assert bounds and bounds[1] > 0
assert workspace_ui.is_palette_event(fake_context, SimpleNamespace(mouse_x=30, mouse_y=200))
fake_context.area.spaces.active.show_gizmo = False
assert not workspace_ui.is_palette_event(fake_context, SimpleNamespace(mouse_x=30, mouse_y=200))
fake_context.area.spaces.active.show_gizmo = True
fake_context.area.spaces.active.show_gizmo_context = False
assert workspace_ui.palette_bounds(fake_context) is None
fake_context.area.spaces.active.show_gizmo_context = True
fake_context.area.spaces.active.show_region_toolbar = True
assert workspace_ui.palette_bounds(fake_context) is None
del source[workspace.OWNER_KEY]
del source[workspace.ROLE_KEY]
assert source.name == name
workspace.request_workspace(bpy.context, "PART")
pending = workspace._JOBS[bpy.context.window.as_pointer()]
pending["phase"] = "configure"
workspace.request_workspace(bpy.context, "SKETCH")
assert workspace._JOBS[bpy.context.window.as_pointer()] is pending
assert pending["phase"] == "configure" and pending["role"] == "SKETCH"
workspace.cancel_pending_setup()
assert not workspace._JOBS
workspace_ui.unregister()
workspace_ui.unregister()
workspace.unregister()
addon.unregister()
assert workspace_ui._PREVIEWS is None
assert not bpy.app.timers.is_registered(workspace._tick)
print("MCAD_WORKSPACE_SMOKE_OK", bpy.app.version_string)
