"""Native action registration/poll and empty/nonempty palette selection."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import register, unregister, workspace, workspace_ui  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad
with patch.object(workspace, "get_role", return_value="PART"), patch.object(
    workspace, "is_cad_workspace", return_value=True,
):
    assert state.status == "EMPTY" and state.document_json == ""
    assert workspace_ui.palette_actions(bpy.context) == ()
    assert workspace_ui.palette_layout((), 900) is None
    state.document_json = json.dumps({"schema_version": 1, "id": "empty", "name": "Empty", "units": "mm", "parameters": {}, "features": [], "active_feature": None})
    assert workspace_ui.palette_actions(bpy.context) == ("NEW", "RECTANGLE", "IMPORT")
    assert len(workspace_ui.menu_actions(bpy.context)) == 26
    assert workspace_ui.available(bpy.context, "IMPORT")
    state.sketch_draft_json = "retained draft"
    assert not workspace_ui.available(bpy.context, "IMPORT")
    state.sketch_draft_json = ""
    state.document_json = (ROOT / "examples/viewport_rectangle.mcad.json").read_text()
    state.status = "FAILED"
    assert workspace_ui.palette_actions(bpy.context) == workspace_ui.menu_actions(bpy.context)
unregister()
print("EMPTY_PALETTE_SMOKE_OK", bpy.app.version_string)
