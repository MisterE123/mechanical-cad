"""Native viewport adapter checks; no independent geometry or solver path."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import general_viewport as v  # noqa: E402
from mechanical_cad_blender.general_sketch_commands import DraftError, PointRef, PointSeed  # noqa: E402

points = {"on": (10, 0), "off": (10, 1)}
draft = SimpleNamespace(proposal={"kind": "line", "anchor": {"kind": "new", "position": (0, 0)}},
                        point_input_phase=("line", "end"), tool="Line", ui_revision=0)
owner = SimpleNamespace(draft=draft, geometry=lambda: SimpleNamespace(points=points),
                        label_bounds=(), region=SimpleNamespace(x=0,y=0), proposal_capture=True,
                        commands=SimpleNamespace(revision=0), message="")
event = SimpleNamespace(mouse_x=10,mouse_y=1,shift=True,value="PRESS")
accepted = []
owner.accept_point_input = lambda *args, **kwargs: accepted.append((args,kwargs))
with patch.object(v, "_pointer", return_value=(10,1)), patch.object(v, "_pick", return_value=None):
    assert v._line_endpoint(owner,event) == (PointSeed(10,0),"horizontal","")
    v._click(owner,None,event)
    assert accepted[-1][0][-1] == PointSeed(10,0)
    assert accepted[-1][1]["axis"] == "horizontal"
with patch.object(v, "_pointer", return_value=(10,1)), patch.object(v, "_pick", return_value=SimpleNamespace(identifier="on")):
    assert v._line_endpoint(owner,event) == (PointRef("on"),"horizontal","")
with patch.object(v, "_pointer", return_value=(10,1)), patch.object(v, "_pick", return_value=SimpleNamespace(identifier="off")):
    endpoint,axis,blocked = v._line_endpoint(owner,event)
    assert endpoint == PointSeed(10,0) and axis == "horizontal" and "off axis" in blocked
    count=len(accepted)
    try:
        v._click(owner,None,event)
        raise AssertionError("Off-axis click was accepted")
    except DraftError:
        pass
    assert len(accepted)==count
    event.shift=False
    assert v._line_endpoint(owner,event) == (PointRef("off"),None,"")
    v._click(owner,None,event)
    assert accepted[-1][1]["axis"] is None
# Modifier release recomputes the proposal without creating an accepted command.
print("LINE_AXIS_SMOKE_OK")
