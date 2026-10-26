"""Bounded native whole-add-on toolbar registration/reload regression.

Run in fresh Blender 5.2 with --background --factory-startup
--python-exit-code 1. This checks registration, not visual GUI usability.
"""

import importlib
import os
import sys
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import registration, workspace_ui  # noqa: E402

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def foreign_header(self, context):
    pass


class REGISTRATION_TEST_GGT_foreign(bpy.types.GizmoGroup):
    bl_idname = "REGISTRATION_TEST_GGT_foreign"
    bl_label = "Registration test sentinel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"

    def setup(self, context):
        pass


def owned_headers():
    # Count by stable owner/name, not only current function identity: stale
    # callbacks from a previous module instance must not evade the assertion.
    return [
        callback
        for callback in bpy.types.VIEW3D_HT_header._dyn_ui_initialize()
        if getattr(callback, "__module__", "") == workspace_ui.__name__
        and getattr(callback, "__name__", "") == "_draw_header"
    ]


def verify(enabled):
    check(
        len(owned_headers()) == int(enabled), "Exactly one owned header when enabled; none disabled"
    )
    check(
        all(("bl_rna" in cls.__dict__) == enabled for cls in workspace_ui.CLASSES),
        "All owned palette/UI classes follow enable state",
    )
    check(
        bpy.types.GizmoGroup.bl_rna_get_subclass_py("MCAD_GGT_workspace_palette")
        is (workspace_ui.MCAD_GGT_workspace_palette if enabled else None),
        "The palette RNA identity has no stale registration",
    )
    check(
        (workspace_ui._PREVIEWS is not None) == enabled,
        "Icon previews are created and released with the palette",
    )
    check(
        foreign_header in bpy.types.VIEW3D_HT_header._dyn_ui_initialize(),
        "Unrelated header callback survives",
    )
    check("bl_rna" in REGISTRATION_TEST_GGT_foreign.__dict__, "Unrelated GizmoGroup survives")
    check(bpy.context.scene.unit_settings.scale_length == unit_scale, "User unit scale preserved")
    check(bpy.context.preferences.view.ui_scale == ui_scale, "User UI scale preserved")
    check(bpy.data.objects.get(sentinel.name) is sentinel, "Unrelated object preserved")
    for handlers, callback in registration._HISTORY_HANDLERS:
        count = sum(
            getattr(item, "__module__", "") == callback.__module__
            and getattr(item, "__name__", "") == callback.__name__
            for item in handlers
        )
        check(count == int(enabled), "Owned history callback is not duplicated or leaked")


unit_scale = bpy.context.scene.unit_settings.scale_length
ui_scale = bpy.context.preferences.view.ui_scale
sentinel = bpy.data.objects.new("Registration cycle sentinel", None)
bpy.context.scene.collection.objects.link(sentinel)
bpy.utils.register_class(REGISTRATION_TEST_GGT_foreign)
bpy.types.VIEW3D_HT_header.append(foreign_header)
try:
    for _cycle in range(3):
        check(
            addon_utils.enable("mechanical_cad_blender", default_set=False) is addon,
            "Blender's normal add-on enable succeeds",
        )
        addon.register()
        workspace_ui.register()
        verify(True)
        addon_utils.disable("mechanical_cad_blender", default_set=False)
        verify(False)
        addon.unregister()
        verify(False)
        # Reload only after normal unregister, as supported add-on reload does.
        # Submodule reload verifies old callback identity cannot hide a leak.
        importlib.reload(workspace_ui)
        importlib.reload(addon)
    print("TOOLBAR_REGISTRATION_SMOKE_OK", len(checks), "cycles=3")
finally:
    if registration._owns_scene_registration():
        addon.unregister()
    bpy.types.VIEW3D_HT_header.remove(foreign_header)
    bpy.utils.unregister_class(REGISTRATION_TEST_GGT_foreign)
