"""All Part actions remain native-icon reachable in normal short viewports."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister, workspace_ui  # noqa: E402

register()
with (
    patch.object(workspace_ui.workspace, "get_role", return_value="PART"),
    patch.object(workspace_ui.workspace, "active_draft", return_value=None),
):
    actions = workspace_ui.palette_actions(bpy.context)

for scale in (1.0, 1.25, 1.5, 2.0):
    for height in (540, 600, 720, 1080, 1600):
        result = workspace_ui.palette_layout(actions, height * scale, scale, 900 * scale)
        assert result is not None, (height, scale)
        (left, bottom, right, top), positions = result
        assert set(positions) == set(actions)
        assert len(set(positions.values())) == len(actions)
        for x, y, _ in positions.values():
            assert left < x < right and bottom < y < top
        assert positions["CHECK"][1] == positions["EXPORT"][1] or right == 62 * scale
        assert min(y for _, y, _ in positions.values()) > 20 * scale
assert workspace_ui.palette_layout(actions, 200, 1, 80) is None
print("MCAD_RESPONSIVE_PALETTE_OK", len(actions), "actions;20 view sizes")
unregister()
