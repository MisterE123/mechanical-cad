"""Native exact direction, stale-dialog rejection and expression-preserving UI checks.

Headless operator evidence only; not a claim about mouse-based GUI usability.
"""

import json
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    register,
    solid_operators,  # noqa: E402
    unregister,
)
from mechanical_cad_blender.document_state import _append_feature, _commit_candidate, _new_feature  # noqa: E402
from mechanical_cad_blender.extrusion_operators import MCAD_OT_extrude_boolean  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad


def run(operator, **kwargs):
    result = operator(**kwargs)
    assert result == {"FINISHED"}, (result, state.last_action_error)
    assert state.status == "READY", (state.status, state.last_action_error)
    return state.active_feature


def rejected(operator, **kwargs):
    before = state.document_json
    try:
        result = operator(**kwargs)
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"}, result
    assert state.document_json == before


run(bpy.ops.mcad.new_document, name="Everyday solid dialogs")
profile = run(bpy.ops.mcad.add_rectangle, width=40, height=30)
base = run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
run(
    bpy.ops.mcad.named_parameter,
    parameter_name="pocket_depth",
    expression="3",
    original_json=state.document_json,
)
circle = _new_feature(
    bpy.context, "sketch_circle", {"radius": 2, "x": 10, "y": 10, "z": 10}, {}, "Pocket sketch"
)
assert _append_feature(bpy.context, circle)
run(
    bpy.ops.mcad.extrude_boolean,
    mode="REMOVE",
    base=base,
    profile=circle["id"],
    depth="pocket_depth + 2",
    direction="REVERSE",
    feature_label="Pocket",
)
assert abs(state.volume - (12000 - 20 * math.pi)) < 1e-3
source = json.loads(state.document_json)
depth_parameter = source["features"][-2]["params"]["length"]
assert source["parameters"][depth_parameter] == "-(pocket_depth + 2)"
# Changing the underlying parameter still drives the canonical extrusion.
run(
    bpy.ops.mcad.named_parameter,
    parameter_name="pocket_depth",
    expression="4",
    replace_existing=True,
    original_json=state.document_json,
)
assert abs(state.volume - (12000 - 24 * math.pi)) < 1e-3
rejected(
    bpy.ops.mcad.extrude_boolean,
    mode="REMOVE",
    base=base,
    profile=circle["id"],
    depth="-3",
    direction="REVERSE",
)
assert "Depth must be positive" in state.last_action_error
rejected(
    bpy.ops.mcad.add_solid_feature,
    kind="fillet",
    base=base,
    radius="1",
    original_json=state.document_json + " ",
)
assert "Document changed" in state.last_action_error

# The actual invoke methods receive the real document and selection, without
# opening a modal window in background mode. Capture their dialog request.
state.feature_index = next(
    i for i, row in enumerate(state.features) if row.feature_id == circle["id"]
)
context = SimpleNamespace(
    scene=bpy.context.scene,
    window_manager=SimpleNamespace(invoke_props_dialog=lambda *args, **kwargs: {"RUNNING_MODAL"}),
)
operator = SimpleNamespace(
    mode="REMOVE", properties=SimpleNamespace(is_property_set=lambda key: False)
)
assert MCAD_OT_extrude_boolean.invoke(operator, context, None) == {"RUNNING_MODAL"}
assert operator.profile == circle["id"] and operator.direction == "NORMAL"
assert operator.original_json == state.document_json
solid = SimpleNamespace(kind="revolve", properties=operator.properties)
assert solid_operators.MCAD_OT_add_solid_feature.invoke(solid, context, None) == {"RUNNING_MODAL"}
assert solid.profile == circle["id"] and solid.original_json == state.document_json


# A canonical outward face sketch gives Remove a safe, visible inward default.
attached = "attached_profile"
face_sketch = json.loads((ROOT / "examples/circle_sketch_part.mcad.json").read_text())["features"][
    0
]
face_sketch.update(id=attached, inputs={"support": base}, support_face=base + "/face/cap.end")
face_sketch["sketch"]["circles"][0]["radius"] = 2
face_sketch["sketch"]["constraints"][1]["value"] = 2
candidate = json.loads(state.document_json)
candidate["schema_version"] = 2
candidate["features"].append(face_sketch)
candidate["active_feature"] = attached
assert _commit_candidate(bpy.context, candidate)
state.feature_index = next(i for i, row in enumerate(state.features) if row.feature_id == attached)
assert MCAD_OT_extrude_boolean.invoke(operator, context, None) == {"RUNNING_MODAL"}
assert operator.profile == attached and operator.base == base and operator.direction == "REVERSE"
run(
    bpy.ops.mcad.extrude_boolean,
    mode="REMOVE",
    base=operator.base,
    profile=operator.profile,
    direction=operator.direction,
    depth="5",
    original_json=operator.original_json,
)
assert abs(state.volume - (12000 - 20 * math.pi)) < 1e-3


# Draw must leave expressions and authored fields alone, including help paging.
class Layout:
    def __init__(self):
        self.labels = []
        self.fields = []

    def prop(self, operator, name, **kwargs):
        self.fields.append((name, kwargs.get("text")))

    def label(self, **kwargs):
        self.labels.append(kwargs.get("text"))

    def row(self, **kwargs):
        return self

    def box(self):
        return self


layout = Layout()
solid.layout = layout
solid.kind = "transform"
solid.feature_id = "selected"
solid.feature_label = "Move precisely"
solid.x, solid.y, solid.z = "wall + gap", "0", "0"
solid.rx, solid.ry, solid.rz = "0", "0", "angle_parameter"
solid.show_help, solid.help_page = False, 1
solid.help_summary = ("Help does not replace fields.", "Apply remains explicit.")
solid.help_topic = "feature.transform"
before = (solid.x, solid.rz, solid.feature_label)
solid_operators._SolidDialog.draw(solid, bpy.context)
solid.show_help = True
solid_operators._SolidDialog.draw(solid, bpy.context)
assert before == (solid.x, solid.rz, solid.feature_label)
assert "Move by (mm)" in layout.labels and "Rotate (degrees)" in layout.labels
assert ("x", "X") in layout.fields and ("rz", "Z") in layout.fields
assert "Replacing a parameter name changes this feature's link only." in layout.labels
for kind, fields in solid_operators.FEATURE_FIELDS.items():
    layout = Layout()
    solid.kind = kind
    solid_operators._draw_dimensions(layout, solid)
    assert sorted(name for name, _label in layout.fields) == sorted(fields), kind
    if kind in {"circular_pattern", "circular_cut_pattern"}:
        assert ("angle", "Total pattern angle (degrees)") in layout.fields
print("MCAD_SOLID_DIALOG_ERGONOMICS_SMOKE_OK", flush=True)
unregister()
