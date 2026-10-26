"""Native 5.2 toolbar identities, exact targets, repeated enable and reopen.

Run with --background --python-exit-code 1. Set MCAD_TOOLBAR_BLEND to persist,
then launch a second process with that blend and MCAD_TOOLBAR_REOPEN=1.
This exercises native registration and button geometry, not GUI usability.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1]))
if archive := os.environ.get("MCAD_TOOLBAR_ZIP"):
    assert bpy.ops.preferences.addon_install(filepath=archive, overwrite=True) == {"FINISHED"}
    assert bpy.ops.preferences.addon_enable(module="mechanical_cad_blender") == {"FINISHED"}
else:
    sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import tool_glyphs, workspace, workspace_ui  # noqa: E402

if os.environ.get("MCAD_TOOLBAR_ZIP"):
    assert Path(addon.__file__).resolve().is_relative_to(Path(os.environ["BLENDER_USER_SCRIPTS"]))

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def header_count():
    return sum(
        callback is workspace_ui._draw_header
        for callback in bpy.types.VIEW3D_HT_header._dyn_ui_initialize()
    )


addon.register()
addon.register()
workspace_ui.register()
check(header_count() == 1, "Repeated enable registers exactly one CAD header callback")
if os.environ.get("MCAD_TOOLBAR_REOPEN"):
    check(
        bpy.data.objects.get("Toolbar identity sentinel") is not None,
        "Reopen preserves unrelated user objects",
    )
else:
    sentinel = bpy.data.objects.new("Toolbar identity sentinel", None)
    bpy.context.scene.collection.objects.link(sentinel)


class Gizmo:
    def __init__(self, kind):
        self.kind = kind
        self.matrix_basis = Matrix.Identity(4)

    def target_set_operator(self, identifier):
        self.target = SimpleNamespace(identifier=identifier)
        return self.target


palette = SimpleNamespace(gizmos=SimpleNamespace(new=Gizmo))
workspace_ui.MCAD_GGT_workspace_palette.setup(palette, bpy.context)
check(len(palette.buttons) == len(workspace_ui._ACTIONS), "Exactly one button per supported action")
for action, button in palette.buttons.items():
    check(button.target.action == action, f"{action} retains its exact action target")
    check(button.target.identifier == "mcad.workspace_action", f"{action} retains native dispatch")
    if action in palette.shape_actions:
        check(button.shape == tool_glyphs.shape(action), f"{action} uses semantic native geometry")
        check(
            f"tool:dark:{tool_glyphs.ALIASES.get(action, action)}" in workspace_ui._PREVIEWS,
            f"{action} has matching menu artwork",
        )
    with patch.object(workspace_ui, "action_reason", return_value="Select geometry first"):
        tip = workspace_ui.MCAD_OT_workspace_action.description(
            bpy.context, SimpleNamespace(action=action)
        )
        check(
            tip.startswith(workspace_ui._ACTIONS[action][0] + ":"),
            f"{action} tooltip identifies the command even when disabled",
        )


def identity(action):
    return tool_glyphs.shape(action) or workspace_ui._ACTIONS[action][3]


for role in ("PART", "SKETCH", "ASSEMBLY"):
    with (
        patch.object(workspace, "get_role", return_value=role),
        patch.object(workspace, "active_draft", return_value=None),
    ):
        actions = workspace_ui.palette_actions(bpy.context)
    check(len(actions) == len(set(actions)), f"{role} has no duplicate commands")
    check(
        len({identity(action) for action in actions}) == len(actions),
        f"{role} has no indistinguishable toolbar symbols",
    )

# All possible general-sketch tools/relations, including transient line-edit
# and check controls. Legacy rectangle DIMENSIONS is not a general draft tool.
actions = tuple(
    dict.fromkeys(
        (
            *workspace_ui._GENERAL_PALETTE_TOOLS,
            *workspace_ui._CONSTRAINT_ACTIONS,
            "ANGLE",
            "DIAMETER",
            "CONSTRUCTION",
            "APPLY_LINE_EDIT",
            "CANCEL_LINE_EDIT",
            "SKETCH_CHECK",
            "CANCEL_CHECK",
            "FINISH",
            "CANCEL",
        )
    )
)
check(
    len({identity(action) for action in actions}) == len(actions),
    "General sketch actions have distinct visual identities",
)
base = (*workspace_ui._GENERAL_PALETTE_TOOLS, "SKETCH_CHECK", "FINISH", "CANCEL")
changed = (
    *workspace_ui._GENERAL_PALETTE_TOOLS,
    "CONCENTRIC",
    "DIAMETER",
    "CANCEL_CHECK",
    "FINISH",
    "CANCEL",
)
for scale in (1, 1.5, 2):
    for width, height in ((966, 720), (500, 600), (220, 450)):
        before = workspace_ui.palette_layout(base, height * scale, scale, width * scale)
        after = workspace_ui.palette_layout(changed, height * scale, scale, width * scale)
        check(before is not None and after is not None, "Palette fits at controlled viewport size")
        for action in (*workspace_ui._GENERAL_PALETTE_TOOLS, "FINISH", "CANCEL"):
            check(before[1][action] == after[1][action], f"{action} stays in its fixed slot")

for _ in range(3):
    workspace_ui.unregister()
    check(header_count() == 0, "Disable removes the CAD header callback")
    workspace_ui.register()
    workspace_ui.register()
    check(header_count() == 1, "Re-enable restores exactly one CAD header callback")
check(
    bpy.data.objects.get("Toolbar identity sentinel") is not None,
    "Repeated UI registration preserves unrelated objects",
)
if path := os.environ.get("MCAD_TOOLBAR_BLEND"):
    bpy.ops.wm.save_as_mainfile(filepath=path)
addon.unregister()
check(header_count() == 0, "Complete add-on disable removes the CAD header callback")
print("TOOLBAR_IDENTITY_SMOKE_OK", len(checks))
