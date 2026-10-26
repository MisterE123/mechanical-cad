"""Native automatic/authored Sweep operators, disclosures, atomic edit and reopen.

This is source-loaded headless coverage, not GUI or package qualification.
Run with MCAD_ROOT, MCAD_PYTHON, MCAD_SMOKE_OUTPUT; second process MCAD_SMOKE_INPUT.
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
from mechanical_cad_blender import register, unregister  # noqa: E402
from mechanical_cad_blender.document_state import _commit_candidate  # noqa: E402
from mechanical_cad_blender.solid_operators import MCAD_OT_edit_solid_feature, _SolidDialog  # noqa: E402

register()
if os.environ.get("MCAD_SMOKE_INPUT"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad


def run(op, **kwargs):
    result = op(**kwargs)
    assert result == {"FINISHED"}, (result, state.last_action_error)
    assert state.status == "READY", state.last_action_error
    return state.active_feature


def capture(identifier):
    op = SimpleNamespace(feature_id=identifier, resume_json="")
    context = SimpleNamespace(
        scene=bpy.context.scene,
        window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"}),
    )
    assert MCAD_OT_edit_solid_feature.invoke(op, context, None) == {"RUNNING_MODAL"}
    return op, {
        key: getattr(op, key)
        for key in (
            "feature_id",
            "kind",
            "feature_label",
            "original_json",
            "profile",
            "path",
            "sweep_placement_mode",
            "sweep_roll",
            "sweep_reverse",
        )
    }


class Layout:
    def __init__(self):
        self.fields, self.labels = [], []

    def prop(self, op, name, **kwargs):
        self.fields.append(name)

    def label(self, **kwargs):
        self.labels.append(kwargs.get("text", ""))

    def box(self):
        return self

    def column(self):
        return self

    def row(self, **kwargs):
        return self


def inputs(*, legacy=False):
    q = [math.sqrt(0.5), 0, -math.sqrt(0.5), 0] if legacy else [1, 0, 0, 0]
    return [
        dict(
            id="p",
            kind="sketch_rectangle",
            label="Section",
            params={"width": 6, "height": 3, "x": 0 if legacy else 100, "y": 0 if legacy else 200},
            inputs={},
        ),
        dict(
            id="path",
            kind="sketch_constrained",
            label="Path",
            params={},
            inputs={},
            sketch={
                "schema_version": 2,
                "id": "path",
                "units": "mm",
                "plane": {"id": "plane", "origin": [0, 0, 0], "quaternion": q},
                "points": [{"id": "a", "u": 0, "v": 0}, {"id": "b", "u": 30, "v": 0}],
                "lines": [{"id": "rail", "start": "a", "end": "b"}],
                "circles": [],
                "constraints": [
                    {"id": "fixa", "kind": "fixed", "refs": ["a"], "target": [0, 0]},
                    {"id": "fixb", "kind": "fixed", "refs": ["b"], "target": [30, 0]},
                ],
            },
        ),
    ]


if os.environ.get("MCAD_SMOKE_INPUT"):
    run(bpy.ops.mcad.regenerate)
    op, args = capture(state.active_feature)
    assert args["sweep_placement_mode"] == "AUTO"
    assert args["sweep_reverse"] is True and float(args["sweep_roll"]) == 90
    assert abs(state.volume - 540) < 1e-6
    doc = json.loads(state.document_json)
    doc["features"][0]["params"]["width"] = 8
    assert _commit_candidate(bpy.context, doc, state.document_path)
    assert abs(state.volume - 720) < 1e-6
    marker = "MCAD_SWEEP_PLACEMENT_REOPEN_OK"
else:
    run(bpy.ops.mcad.new_document, name="Sweep placement")
    doc = json.loads(state.document_json)
    doc.update(schema_version=2, features=inputs(legacy=True), active_feature="p")
    assert _commit_candidate(bpy.context, doc, state.document_path)
    legacy = run(
        bpy.ops.mcad.add_solid_feature,
        kind="sweep",
        profile="p",
        path="path",
        sweep_placement_mode="AUTHORED",
        feature_label="Authored Sweep",
    )
    assert "sweep_placement" not in json.loads(state.document_json)["features"][-1]
    op, args = capture(legacy)
    assert args["sweep_placement_mode"] == "AUTHORED"
    before = state.document_json
    run(bpy.ops.mcad.edit_solid_feature, **args)
    assert state.document_json == before
    # Distinct, off-origin section and in-plane path need automatic placement.
    doc.update(features=inputs(), active_feature="p")
    assert _commit_candidate(bpy.context, doc, state.document_path)
    sweep = run(
        bpy.ops.mcad.add_solid_feature,
        kind="sweep",
        profile="p",
        path="path",
        feature_label="Automatic Sweep",
    )
    assert abs(state.volume - 540) < 1e-6
    saved = json.loads(state.document_json)["features"][-1]
    assert saved["sweep_placement"] == {
        "version": 1,
        "mode": "path_start_centroid",
        "reverse": False,
        "roll_degrees": 0,
    }
    op, args = capture(sweep)
    op.layout = Layout()
    op.show_help, op.help_page = False, 1
    op.help_summary, op.help_topic = ("Sweep", "Atomic Apply"), "feature.sweep"
    _SolidDialog.draw(op, bpy.context)
    assert {"sweep_placement_mode", "sweep_roll", "sweep_reverse"} <= set(op.layout.fields)
    assert any("filled-area centroid" in label for label in op.layout.labels)
    assert any("no stable face identity" in label for label in op.layout.labels)
    # A failed literal roll must not publish a changed label or placement.
    before = state.document_json
    try:
        failed = bpy.ops.mcad.edit_solid_feature(
            **{**args, "sweep_roll": "formula", "feature_label": "Rejected"}
        )
    except RuntimeError:
        failed = {"CANCELLED"}
    assert failed == {"CANCELLED"} and state.document_json == before
    # The same section in authored coordinates is incompatible with this path.
    try:
        failed = bpy.ops.mcad.edit_solid_feature(**{**args, "sweep_placement_mode": "AUTHORED"})
    except RuntimeError:
        failed = {"CANCELLED"}
    assert failed == {"CANCELLED"} and state.document_json == before
    run(bpy.ops.mcad.edit_solid_feature, **{**args, "sweep_reverse": True, "sweep_roll": "90"})
    assert abs(state.volume - 540) < 1e-6
    assert json.loads(state.document_json)["features"][:2] == json.loads(before)["features"][:2]
    bpy.ops.wm.save_as_mainfile(filepath=os.environ["MCAD_SMOKE_OUTPUT"])
    assert Path(os.environ["MCAD_SMOKE_OUTPUT"]).is_file()
    marker = "MCAD_SWEEP_PLACEMENT_SMOKE_OK"
assert not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules)
print(marker, state.volume, flush=True)
unregister()
