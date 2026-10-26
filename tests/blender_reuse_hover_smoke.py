"""Native point-picker preview seams; no GUI qualification or native solver."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mathutils import Matrix

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import general_view_geometry as geometry  # noqa: E402
from mechanical_cad_blender import general_viewport as viewport  # noqa: E402
from mechanical_cad_blender.general_sketch_commands import PointRef, PointSeed  # noqa: E402

sketch = {
    "schema_version": 2, "id": "sketch", "units": "mm",
    "plane": {"id": "plane", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
    "points": [{"id": "a", "u": 100, "v": 100}, {"id": "b", "u": 150, "v": 100}],
    "lines": [{"id": "line", "start": "a", "end": "b"}],
    "circles": [], "constraints": [],
}
current = geometry.build_geometry(sketch, source="authored")
owner = SimpleNamespace(
    draft=SimpleNamespace(ui_revision=0, tool="Line", proposal=None, point_input_phase=("line", "start")),
    commands=SimpleNamespace(revision=0, pending_edit=None),
    pending=None, navigation=False, input_controller=None, proposal_capture=False,
    can_use_tool=lambda tool: True, geometry=lambda: current,
    region=SimpleNamespace(x=0, y=0, width=600, height=400),
    area=SimpleNamespace(regions=[]), rv3d=SimpleNamespace(perspective_matrix=Matrix.Identity(4)),
    scene=SimpleNamespace(unit_settings=SimpleNamespace(scale_length=1)),
    error="Important diagnostic", message="Keep this status", label_bounds=(),
)
event = SimpleNamespace(mouse_x=103, mouse_y=100)
with patch.object(viewport, "_project", side_effect=lambda owner, world: world[:2]):
    viewport._update_reuse_hover(owner, event)
    assert viewport._reuse_hover_position(owner) == (100, 100)
    assert owner.error == "Important diagnostic" and owner.message == "Keep this status"
    # Draw validation does not pick again; hover never supplies click authority.
    with patch.object(viewport, "_pick", side_effect=AssertionError("draw picked")):
        assert viewport._reuse_hover_position(owner) == (100, 100)
    event.mouse_x = 150
    assert viewport._anchor(owner, event) == PointRef("b")
    event.mouse_x = 300
    with patch.object(viewport, "_pointer", return_value=(300, 100)):
        assert viewport._anchor(owner, event) == PointSeed(300, 100)
    event.mouse_x = 100
    for tool, phase, proposal, capture, expected in (
        ("Line", ("line", "start"), None, False, True),
        ("Line", ("line", "end"), {"kind": "line"}, True, True),
        ("Line", ("line", "end"), {"kind": "line"}, False, False),
        ("Arc", ("arc", "center"), None, False, True),
        ("Arc", ("arc", "start"), {"kind": "arc"}, True, True),
        ("Arc", ("arc", "end"), {"kind": "arc"}, True, True),
        ("Circle", None, None, False, True),
        ("Circle", None, {"kind": "circle"}, True, False),
        ("Rectangle", None, None, False, False),
        ("Rectangle", None, {"kind": "rectangle"}, True, False),
        ("Select", None, None, False, False),
    ):
        owner.draft.tool, owner.draft.point_input_phase = tool, phase
        owner.draft.proposal, owner.proposal_capture = proposal, capture
        viewport._update_reuse_hover(owner, event)
        assert (viewport._reuse_hover_position(owner) is not None) == expected, (tool, phase)
    owner.draft.tool, owner.draft.point_input_phase = "Line", ("line", "start")
    owner.draft.proposal = None
    for attribute, changed in (("pending", object()), ("navigation", True),
                               ("gesture_intent", object()), ("annotation_drag", "radius")):
        setattr(owner, attribute, changed)
        viewport._update_reuse_hover(owner, event)
        assert owner.reuse_hover is None, attribute
        setattr(owner, attribute, False if attribute == "navigation" else None)
    for mutate in (
        lambda: setattr(owner.commands, "revision", 1),
        lambda: setattr(owner.draft, "ui_revision", 1),
        lambda: setattr(owner.rv3d, "perspective_matrix", Matrix.Scale(2, 4)),
        lambda: setattr(owner.region, "width", 700),
        lambda: setattr(owner.region, "x", 1),
        lambda: setattr(owner.region, "y", 1),
        lambda: setattr(owner.draft, "point_input_phase", ("line", "end")),
    ):
        viewport._update_reuse_hover(owner, event)
        assert owner.reuse_hover is not None
        mutate()
        assert viewport._reuse_hover_position(owner) is None
    owner.label_bounds = (("dim", (90, 90, 110, 110)),)
    viewport._update_reuse_hover(owner, event)
    assert owner.reuse_hover is None
    owner.label_bounds = ()
    sketch["points"][1]["u"] = 100
    current = geometry.build_geometry(sketch, source="authored")
    viewport._update_reuse_hover(owner, event)
    assert owner.reuse_hover is None  # distinct overlapping IDs
with patch.object(viewport, "_project", return_value=None):
    viewport._update_reuse_hover(owner, event)
    assert owner.reuse_hover is None  # not visible
print("REUSE_HOVER_SMOKE_OK")
