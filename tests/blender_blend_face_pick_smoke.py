"""Exact face picking for blends, native replay authority, and modal cleanup."""

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Vector

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    edge_pick,
    face_pick,
    register,
    solid_operators,  # noqa: E402
    unregister,
)
from mechanical_cad_blender.display import _owned_objects  # noqa: E402


def rejects(action, text):
    try:
        action()
    except ValueError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError("Unsafe pick was accepted")


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    for obj in context.scene.objects:
        obj.hide_set(True)
    state = context.scene.mechanical_cad
    assert bpy.ops.mcad.new_document(name="Direct blend faces") == {"FINISHED"}
    assert bpy.ops.mcad.add_rectangle(width=20, height=30) == {"FINISHED"}
    assert bpy.ops.mcad.add_extrude(profile=state.active_feature, length=10) == {"FINISHED"}
    result = document_state.current_part_result(context)
    obj = _owned_objects(context.scene)[0]
    feature = face_pick.bound_feature(context, obj, result)
    base_id = feature["id"]
    top = base_id + "/face/cap.end"
    bottom = base_id + "/face/cap.start"
    side = next(f["id"] for f in feature["topology"] if f["role"].startswith("side."))
    indices = feature["mesh"]["triangle_face_ids"]
    # Every triangle of a face resolves to the same identity: no diagonal is an edge.
    assert sum(v == top for v in indices) >= 2
    assert all(edge_pick.resolve_face(feature, i)["id"] == v for i, v in enumerate(indices))
    altered = copy.deepcopy(feature)
    target = next(f for f in altered["topology"] if f["id"] == top)
    target["signature"]["surface"] = "cylinder"
    assert edge_pick.resolve_face(altered, indices.index(top))["id"] == top
    target["provenance"]["semantic_status"] = "unknown"
    rejects(lambda: edge_pick.resolve_face(altered, indices.index(top)), "stable identity")
    altered["mesh"]["triangle_face_ids"].pop()
    rejects(lambda: edge_pick.resolve_face(altered, 0), "incomplete")
    rejects(lambda: edge_pick.resolve_face(feature, -1), "No exact")
    before = state.document_json
    picker = edge_pick.BlendFacePicker(context, "fillet")
    assert picker.current(context)
    picker.hit, picker.hit_obj = (base_id, top), obj
    picker.points = edge_pick.face_points(obj, feature, top)
    assert not picker.choose()
    assert picker.first_points and picker.first == (base_id, top)
    with patch.object(face_pick.workspace_ui, "is_palette_event", return_value=True):
        assert not picker.hover(context, SimpleNamespace(mouse_x=0, mouse_y=0))
        assert picker.first == (base_id, top) and picker.first_points
        assert picker.hit is None and not picker.points
        assert picker.message == "Click a second face beside the same edge. Esc cancels."
    picker.hit, picker.hit_obj = (base_id, top), obj
    rejects(picker.choose, "different faces")
    picker.hit, picker.hit_obj = (base_id, side), obj
    assert picker.choose()
    arguments = picker.dialog_arguments()
    assert arguments == dict(
        kind="fillet",
        picked_base=base_id,
        picked_face_a=top,
        picked_face_b=side,
        picked_document_json=before,
    )

    # Exercise the actual dialog invoke using the real scene/evidence while
    # replacing only window-manager dialog display in this headless test.
    class DialogContext:
        window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})

        def __getattr__(self, name):
            return getattr(context, name)

    reports = []
    dialog = SimpleNamespace(
        **arguments,
        properties=SimpleNamespace(is_property_set=lambda key: False),
        report=lambda level, message: reports.append(message),
    )
    assert solid_operators.MCAD_OT_add_solid_feature.invoke(dialog, DialogContext(), None) == {
        "RUNNING_MODAL"
    }
    assert (dialog.base, dialog.edge_mode, dialog.face_a, dialog.face_b) == (
        base_id,
        "PAIR",
        top,
        side,
    )
    assert dialog.original_json == before
    dialog.picked_document_json = before + " "
    assert solid_operators.MCAD_OT_add_solid_feature.invoke(dialog, DialogContext(), None) == {
        "CANCELLED"
    }
    assert "Document changed" in reports[-1] and state.document_json == before
    # Scene ray casting uses the same exact face identity as the picker.
    hit, _, _, triangle, hit_obj, _ = context.scene.ray_cast(
        context.evaluated_depsgraph_get(), Vector((0.01, 0.015, 1)), Vector((0, 0, -1))
    )
    assert hit and hit_obj.original == obj
    assert edge_pick.resolve_face(feature, triangle)["id"] == top
    old = obj.data.vertices[0].co.copy()
    obj.data.vertices[0].co.x += 0.001
    assert not picker.current(context)
    obj.data.vertices[0].co = old
    assert picker.current(context)
    picker.close()
    assert not face_pick._PICKERS and state.document_json == before
    # Modal Escape after the first selection cannot mutate canonical data.
    picker = edge_pick.BlendFacePicker(context, "chamfer")
    owner = SimpleNamespace(_picker=picker)
    assert edge_pick.MCAD_OT_pick_blend_faces.modal(
        owner, context, SimpleNamespace(type="ESC")
    ) == {"CANCELLED"}
    assert picker.handler is None and state.document_json == before
    # Native adjacency checks, not graphics, decide whether two faces define one edge.
    try:
        status = bpy.ops.mcad.add_solid_feature(
            kind="fillet", base=base_id, edge_mode="PAIR", face_a=top, face_b=bottom, radius="1"
        )
        assert status == {"CANCELLED"}
    except RuntimeError as exc:
        assert "share exactly one edge" in str(exc), str(exc)
    assert state.document_json == before
    for kind, dimension in [("fillet", "radius"), ("chamfer", "distance")]:
        assert bpy.ops.mcad.add_solid_feature(
            kind=kind, base=base_id, edge_mode="PAIR", face_a=top, face_b=side, **{dimension: "1"}
        ) == {"FINISHED"}
        document = json.loads(state.document_json)
        added = document["features"][-1]
        assert added["edge_faces"] == [top, side]
        assert added["inputs"]["base"] == base_id
        result = document_state.current_part_result(context)
        assert result and result["features"][-1]["status"] == "ok"
    picker = edge_pick.BlendFacePicker(context, "fillet")
    face_pick.cancel_all()
    assert picker.handler is None and picker.timer is None
unregister()
print("BLEND_FACE_PICK_NATIVE_OK", flush=True)
