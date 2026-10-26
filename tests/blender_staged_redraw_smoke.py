"""Native redraw dispatch/lifecycle; actual visible refresh needs GUI verification."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    bridge,
    document_state,
    register,
    registration,
    staged_edit,
    staged_edit_store,
    unregister,
)
from staged_edit_cases import support_case  # noqa: E402

assert bpy.app.background
register()
context = bpy.context
base, proposed = support_case()
assert document_state._commit_candidate(context, base)
accepted = context.scene.mechanical_cad.document_json
views = [
    area
    for window in context.window_manager.windows
    for area in window.screen.areas
    if area.type == "VIEW_3D"
]
assert views and any(region.type == "UI" for area in views for region in area.regions)
for area in views:
    assert callable(area.tag_redraw)
    assert all(callable(region.tag_redraw) for region in area.regions)


def stage():
    try:
        document_state._commit_candidate(context, proposed, stage_feature_id="slot_tool")
    except bridge.BridgeError as exc:
        assert "retained for repair" in str(exc)
    else:
        raise AssertionError("Expected rejected upstream edit")
    assert context.scene.mechanical_cad.document_json == accepted
    return staged_edit.require(context, staged_edit.current(context).token)


with patch.object(
    staged_edit_store, "_notify_changed", wraps=staged_edit_store._notify_changed
) as redraw:
    proposal = stage()
    assert redraw.call_count == 1
    assert staged_edit.current(context) is proposal and redraw.call_count == 1
    staged_edit.discard(context, proposal.token)
    assert redraw.call_count == 2
    proposal = stage()
    assert redraw.call_count == 3
    registration._before_blend_save(None)
    assert staged_edit.current(context) is None and redraw.call_count == 4
    proposal = stage()
    assert redraw.call_count == 5
    original_scale = context.scene.unit_settings.scale_length
    context.scene.unit_settings.scale_length = 2 * original_scale
    assert staged_edit_store._supervise() is None and redraw.call_count == 6
    context.scene.unit_settings.scale_length = original_scale
    assert staged_edit.current(context) is None
    assert context.scene.mechanical_cad.document_json == accepted
unregister()
print("STAGED_REDRAW_NATIVE_OK", flush=True)
