"""Native edge-set authoring, picker retention, edit and two-process persistence.

Headless checks are not interactive GPU/usability qualification.
"""

import json
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Vector

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    direct_edge_pick,
    register,
    solid_operators,
    solid_review,
    unregister,
)

register()
state = bpy.context.scene.mechanical_cad
path = os.environ["MCAD_MULTI_BLEND"]


def run(op, **values):
    result = op(**values)
    assert result == {"FINISHED"}, (result, state.last_action_error)
    assert state.status == "READY", (state.status, state.last_action_error)
    return state.active_feature


def reject(op, **values):
    before = state.document_json
    try:
        result = op(**values)
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"} and state.document_json == before


if os.environ.get("MCAD_MULTI_PHASE") == "reopen":
    bpy.ops.wm.open_mainfile(filepath=path)
    state = bpy.context.scene.mechanical_cad
    run(bpy.ops.mcad.regenerate)
    feature = json.loads(state.document_json)["features"][-1]
    assert len(feature["edge_pairs"]) == 2
    assert abs(state.volume - (12000 - 40 * 9)) < 1e-3
    print("MCAD_MULTIPLE_EDGE_BLEND_REOPEN_OK")
else:
    run(bpy.ops.mcad.new_document, name="Explicit multiple edge blends")
    profile = run(bpy.ops.mcad.add_rectangle, width=40, height=30)
    base = run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
    pairs = [
        [base + "/face/cap.end", base + "/face/side.y_max"],
        [base + "/face/cap.end", base + "/face/side.y_min"],
    ]
    before = state.document_json
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        context = bpy.context
        picker = direct_edge_pick.BlendEdgePicker(context, "chamfer")
        deadline = time.monotonic() + 40
        while picker.pending is not None:
            assert time.monotonic() < deadline
            picker.poll_catalog(context)
            time.sleep(0.01)
        for pair in pairs:
            entry = next(e for e in picker.catalog[base] if sorted(e["faces"]) == sorted(pair))
            picker.hit = (base, *pair)
            picker.points = [Vector(p) * 0.001 for p in entry["points"]]
            picker.hit_obj = next(
                o for o in context.scene.objects if o.get("mechanical_cad_feature_id") == base
            )
            with patch.object(picker, "hover", return_value=True):
                assert (
                    picker.collect_event(
                        context, SimpleNamespace(type="LEFTMOUSE", value="PRESS", shift=True)
                    )
                    == "TOGGLE"
                )
        assert len(picker.selected_edges) == 2
        arguments = picker.selected_arguments(context)
        assert json.loads(arguments["picked_edge_pairs_json"]) == pairs
        vertex = picker.selected_obj.data.vertices[0]
        original_vertex = vertex.co.copy()
        vertex.co.x += 0.01
        try:
            picker.selected_arguments(context)
        except ValueError:
            pass
        else:
            raise AssertionError("Changed display mesh must invalidate retained edge set")
        vertex.co = original_vertex
        assert picker.collect_event(context, SimpleNamespace(type="RET", value="PRESS")) == "REVIEW"
        assert json.loads(picker.selected_arguments(context)["picked_edge_pairs_json"]) == pairs
        picker.toggle_edge()
        assert len(picker.selected_edges) == 1
        picker.toggle_edge()
        assert len(picker.selected_edges) == 2
        owner = SimpleNamespace(_picker=picker, kind="chamfer")
        result = direct_edge_pick.MCAD_OT_pick_blend_edge.modal(
            owner, context, SimpleNamespace(type="ESC", value="PRESS")
        )
        assert result == {"CANCELLED"} and state.document_json == before
        assert not picker.selected_edges and picker.handler is None
    for kind in ["fillet", "chamfer"]:
        blend = run(
            bpy.ops.mcad.add_solid_feature,
            kind=kind,
            base=base,
            edge_mode="MULTI",
            edge_pairs_json=json.dumps(pairs),
            radius="2",
            distance="2",
            original_json=state.document_json,
        )
        removed = 160 if kind == "chamfer" else 320 * (1 - math.pi / 4)
        assert abs(state.volume - (12000 - removed)) < 1e-3
        assert json.loads(state.document_json)["features"][-1]["edge_pairs"] == pairs
    feature = json.loads(state.document_json)["features"][-1]
    before = state.document_json

    # Real editor invoke, substituting only the modal dialog's window-manager entry.
    class Manager:
        def invoke_props_dialog(self, op, **kw):
            assert op.edge_mode == "MULTI" and json.loads(op.edge_pairs_json) == pairs
            return {"RUNNING_MODAL"}

    class Context:
        window_manager = Manager()

        def __getattr__(self, name):
            return getattr(bpy.context, name)

    editor = SimpleNamespace(feature_id=blend, resume_json="", report=lambda *args: None)
    assert solid_operators.MCAD_OT_edit_solid_feature.invoke(editor, Context(), None) == {
        "RUNNING_MODAL"
    }
    assert state.document_json == before  # Dismissing the detached editor changes nothing.
    # Reselection cancellation keeps every retained editor value, including the entire set.
    values = {"original_json": before, "edge_pairs_json": json.dumps(pairs), "edge_mode": "MULTI"}
    fake_picker = SimpleNamespace(current=lambda c: True, close=lambda: None)
    returns = []
    owner = SimpleNamespace(
        _picker=fake_picker, values=values, _return_editor=lambda: returns.append(dict(values))
    )
    assert solid_review.MCAD_OT_reselect_solid_input.modal(
        owner, bpy.context, SimpleNamespace(type="ESC")
    ) == {"CANCELLED"}
    assert returns == [values] and state.document_json == before
    run(
        bpy.ops.mcad.edit_solid_feature,
        feature_id=blend,
        original_json=before,
        kind="chamfer",
        feature_label=feature["label"],
        base=base,
        edge_mode="MULTI",
        edge_pairs_json=json.dumps(pairs),
        distance="3",
    )
    assert abs(state.volume - 11640) < 1e-3
    reject(
        bpy.ops.mcad.add_solid_feature,
        kind="chamfer",
        base=base,
        edge_mode="MULTI",
        edge_pairs_json=json.dumps([pairs[0], [base + "/face/cap.end", "missing/face/a"]]),
        distance="2",
    )
    reject(
        bpy.ops.mcad.add_solid_feature,
        kind="chamfer",
        base=base,
        edge_mode="MULTI",
        edge_pairs_json=json.dumps(pairs),
        distance="100",
    )
    assert bpy.ops.wm.save_as_mainfile(filepath=path) == {"FINISHED"}
    print("MCAD_MULTIPLE_EDGE_BLEND_NATIVE_OK")
unregister()
