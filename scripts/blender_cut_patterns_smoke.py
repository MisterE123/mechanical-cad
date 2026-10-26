"""Native Blender operator verification for separated linear/circular cutting tools."""

import json
import math
import os
import sys
import tempfile
from pathlib import Path

import bpy

if not bpy.app.background:
    raise RuntimeError("Use isolated background Blender")
root = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(root / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402

addon.register()
state = bpy.context.scene.mechanical_cad
results = []
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "holes.mcad.json"
    for kind, count in [("linear_cut_pattern", 3), ("circular_cut_pattern", 6)]:
        document = dict(
            schema_version=1,
            id="holes",
            name="Native holes",
            units="mm",
            parameters={},
            active_feature="base",
            features=[
                dict(
                    id="plate",
                    label="Plate",
                    kind="sketch_rectangle",
                    params=dict(width=60, height=60, x=-30, y=-30),
                    inputs={},
                ),
                dict(
                    id="base",
                    label="Base",
                    kind="extrude",
                    params=dict(length=5),
                    inputs=dict(profile="plate"),
                ),
                dict(
                    id="circle",
                    label="Hole",
                    kind="sketch_circle",
                    params=dict(radius=2, x=15 if kind == "circular_cut_pattern" else -15),
                    inputs={},
                ),
                dict(
                    id="tool",
                    label="Tool",
                    kind="extrude",
                    params=dict(length=20),
                    inputs=dict(profile="circle"),
                ),
            ],
        )
        path.write_text(json.dumps(document))
        assert bpy.ops.mcad.load_document(filepath=str(path)) == {"FINISHED"}
        assert state.status == "READY", state.error
        assert bpy.ops.mcad.add_solid_feature(
            kind=kind,
            base="base",
            tool="tool",
            count=str(count),
            dx="15",
            angle="360",
            axis_y="0",
            axis_z="1",
        ) == {"FINISHED"}
        assert state.status == "READY", state.error
        assert abs(state.volume - (18000 - count * math.pi * 4 * 5)) < 0.01
        assert bpy.ops.mcad.edit_solid_feature(
            feature_id="base",
            kind="extrude",
            feature_label="Thicker plate",
            original_json=state.document_json,
            profile="plate",
            length="8",
        ) == {"FINISHED"}
        assert state.status == "READY", state.error
        assert abs(state.volume - (28800 - count * math.pi * 4 * 8)) < 0.01
        path.write_text(state.document_json)
        assert bpy.ops.mcad.load_document(filepath=str(path)) == {"FINISHED"}
        assert state.status == "READY", state.error
        assert abs(state.volume - (28800 - count * math.pi * 4 * 8)) < 0.01
        results.append(dict(kind=kind, count=count, volume=state.volume))
assert not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules)
print(
    "MCAD_CUT_PATTERNS_RESULT="
    + json.dumps(dict(ok=True, blender=bpy.app.version_string, cases=results))
)
addon.unregister()
