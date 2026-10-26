"""Native adapter routing; actual human double-click remains a separate GUI gate."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import general_viewport as viewport  # noqa: E402

owner = SimpleNamespace(
    label_bounds=(("radius", (80, 80, 120, 120)),),
    region=SimpleNamespace(x=0, y=0),
    annotation_drag=None,
)
press = SimpleNamespace(mouse_x=100, mouse_y=100, value="PRESS")
with patch.object(viewport, "_open_field") as opened:
    with patch.object(viewport.time, "monotonic", return_value=1):
        viewport._click(owner, None, press)
    assert owner.annotation_drag == "radius"
    assert not opened.called
    viewport._click_tracker(owner).release((100, 100))
    with patch.object(viewport.time, "monotonic", return_value=1.2):
        viewport._click(owner, None, press)
    assert opened.call_count == 1
    assert opened.call_args.args == (owner, "radius", (100, 100))
    assert owner.annotation_drag is None

# Importing the adapter has not installed development operators.
import bpy  # noqa: E402

assert not hasattr(bpy.types, "MCAD_OT_general_sketch")
for cls in viewport.CLASSES:
    bpy.utils.register_class(cls)
assert hasattr(bpy.types, "MCAD_OT_edit_general_sketch")
for cls in reversed(viewport.CLASSES):
    bpy.utils.unregister_class(cls)
print("GENERAL_CLICK_SMOKE_OK", 8)
