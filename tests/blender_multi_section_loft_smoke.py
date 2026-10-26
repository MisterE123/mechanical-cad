"""Source-loaded native Loft operators and independent .blend reopen, not GUI QA."""

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
from mechanical_cad_blender.solid_operators import (  # noqa: E402
    MCAD_OT_edit_solid_feature,
    _loft_action,
)

register()
if os.environ.get("MCAD_SMOKE_INPUT"):
    bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_SMOKE_INPUT"])
state = bpy.context.scene.mechanical_cad


def run(op, **kwargs):
    result = op(**kwargs)
    assert result == {"FINISHED"}, (result, state.last_action_error)
    assert state.status == "READY", state.last_action_error
    return state.active_feature


class Rows(list):
    def add(self):
        row = SimpleNamespace(profile="NONE")
        self.append(row)
        return row

    def remove(self, index):
        self.pop(index)

    def move(self, source, target):
        self.insert(target, self.pop(source))


def capture(identifier):
    op = SimpleNamespace(feature_id=identifier, resume_json="", loft_section_rows=Rows())
    context = SimpleNamespace(
        scene=bpy.context.scene,
        window_manager=SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"}),
    )
    assert MCAD_OT_edit_solid_feature.invoke(op, context, None) == {"RUNNING_MODAL"}
    return op


def edit_args(op):
    return {
        key: getattr(op, key)
        for key in (
            "feature_id",
            "kind",
            "feature_label",
            "original_json",
            "ruled",
            "start",
            "end",
            "loft_mode",
        )
    }


def rows(ids):
    return [{"name": f"section_{i + 1}", "profile": identifier} for i, identifier in enumerate(ids)]


if os.environ.get("MCAD_SMOKE_INPUT"):
    run(bpy.ops.mcad.regenerate)
    op = capture(state.active_feature)
    assert op.loft_mode == "ORDERED"
    assert [r.profile for r in op.loft_section_rows] == ["p2", "p1", "p0"]
    before = state.volume
    document = json.loads(state.document_json)
    document["features"][1]["params"]["radius"] = 4
    assert _commit_candidate(bpy.context, document, state.document_path)
    assert state.volume < before
    marker = "MCAD_MULTI_SECTION_LOFT_REOPEN_OK"
else:
    run(bpy.ops.mcad.new_document, name="Ordered Loft")
    document = json.loads(state.document_json)
    document.update(
        features=[
            {
                "id": f"p{i}",
                "kind": "sketch_circle",
                "label": f"Section {i + 1}",
                "params": {"radius": r, "z": z},
                "inputs": {},
            }
            for i, (r, z) in enumerate([(2, 0), (5, 5), (3, 13)])
        ],
        active_feature="p0",
    )
    assert _commit_candidate(bpy.context, document, state.document_path)
    legacy = run(
        bpy.ops.mcad.add_solid_feature,
        kind="loft",
        feature_label="Legacy Loft",
        ruled="1",
        start="p0",
        end="p2",
    )
    assert "loft_sections" not in json.loads(state.document_json)["features"][-1]
    assert capture(legacy).loft_mode == "LEGACY"
    loft = run(
        bpy.ops.mcad.add_solid_feature,
        kind="loft",
        feature_label="Ordered Loft",
        ruled="1",
        start="p0",
        end="p2",
        loft_mode="ORDERED",
        loft_section_rows=rows(["p0", "p1", "p2"]),
    )
    assert abs(state.volume - math.pi / 3 * (5 * 39 + 8 * 49)) < 1e-3, state.volume
    op = capture(loft)
    assert [r.profile for r in op.loft_section_rows] == ["p0", "p1", "p2"]
    op.loft_section_index, op.loft_action = 1, "UP"
    _loft_action(op, bpy.context)
    assert [r.profile for r in op.loft_section_rows] == ["p1", "p0", "p2"]
    op.loft_action = "REMOVE"
    _loft_action(op, bpy.context)
    assert [r.profile for r in op.loft_section_rows] == ["p0", "p2"]
    op.loft_action = "ADD"
    _loft_action(op, bpy.context)
    assert [r.profile for r in op.loft_section_rows] == ["p0", "p2", "p1"]
    op.loft_action = "UP"
    _loft_action(op, bpy.context)
    assert [r.profile for r in op.loft_section_rows] == ["p0", "p1", "p2"]
    before = state.document_json
    try:
        result = bpy.ops.mcad.edit_solid_feature(
            **edit_args(op), loft_section_rows=rows(["p0", "p0"])
        )
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"} and state.document_json == before
    run(
        bpy.ops.mcad.edit_solid_feature, **edit_args(op), loft_section_rows=rows(["p2", "p1", "p0"])
    )
    saved = json.loads(state.document_json)["features"][-1]
    assert list(saved["inputs"].values()) == ["p2", "p1", "p0"]
    assert saved["loft_sections"] == {
        "version": 1,
        "ports": ["section_1", "section_2", "section_3"],
    }
    bpy.ops.wm.save_as_mainfile(filepath=os.environ["MCAD_SMOKE_OUTPUT"])
    marker = "MCAD_MULTI_SECTION_LOFT_SMOKE_OK"
assert not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules)
print(marker, state.volume, flush=True)
unregister()
