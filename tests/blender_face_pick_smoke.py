"""Native display binding and ray picking; not a substitute for real GUI exercise."""

import copy
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from bpy_extras import view3d_utils
from mathutils import Quaternion, Vector

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    edge_pick,
    face_pick,
    general_session,
    general_viewport,
    register,
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
    assert bpy.ops.mcad.new_document(name="Direct face pick") == {"FINISHED"}
    assert bpy.ops.mcad.add_rectangle(width=20, height=30) == {"FINISHED"}
    assert bpy.ops.mcad.add_extrude(profile=state.active_feature, length=10) == {"FINISHED"}
    result = document_state.current_part_result(context)
    obj = _owned_objects(context.scene)[0]
    feature = face_pick.bound_feature(context, obj, result)
    index = feature["mesh"]["triangle_face_ids"].index(feature["id"] + "/face/cap.end")
    face = face_pick.resolve_triangle(feature, index)
    for i in range(len(feature["mesh"]["triangles"])):
        assert (
            face_pick.resolve_triangle(feature, i)["id"] == feature["mesh"]["triangle_face_ids"][i]
        )
    rejects(lambda: face_pick.resolve_triangle(feature, -1), "No exact")
    for mutation, expected in [
        ("unknown", "stable identity"),
        ("curved", "planar"),
        ("missing", "unambiguous"),
    ]:
        changed = copy.deepcopy(feature)
        target = next(f for f in changed["topology"] if f["id"] == face["id"])
        if mutation == "unknown":
            target["provenance"]["semantic_status"] = "unknown"
        elif mutation == "curved":
            target["signature"]["surface"] = "cylinder"
        else:
            changed["mesh"]["triangle_face_ids"][index] = None
        rejects(lambda changed=changed: face_pick.resolve_triangle(changed, index), expected)
    original = obj.data.vertices[0].co.copy()
    obj.data.vertices[0].co.x += 0.001
    rejects(lambda: face_pick.bound_feature(context, obj, result), "edited or transformed")
    obj.data.vertices[0].co = original
    obj.location.x += 0.001
    context.view_layer.update()
    rejects(lambda: face_pick.bound_feature(context, obj, result), "edited or transformed")
    obj.location.x -= 0.001
    context.view_layer.update()
    modifier = obj.modifiers.new("Unsafe display deformation", "SUBSURF")
    rejects(lambda: face_pick.bound_feature(context, obj, result), "current exact")
    obj.modifiers.remove(modifier)
    obj["mechanical_cad_stale"] = True
    rejects(lambda: face_pick.bound_feature(context, obj, result), "current exact")
    obj["mechanical_cad_stale"] = False
    # Reset float32 transform via replay rather than guessing a tolerance.
    document_state.regenerate(context)
    result = document_state.current_part_result(context)
    obj = _owned_objects(context.scene)[0]
    face_pick.bound_feature(context, obj, result)
    before = state.document_json
    snapshot = face_pick.HoverSnapshot(context)
    with patch.object(
        document_state, "current_part_result", wraps=document_state.current_part_result
    ) as fresh:
        snapshot.result(context)
        assert fresh.call_count == 0
        snapshot.result(context, accepting=True)
        assert fresh.call_count == 1, "Acceptance must fully revalidate replay evidence"
    with patch.object(document_state, "current_part_result", return_value=None):
        rejects(lambda: snapshot.result(context, accepting=True), "evidence is unavailable")
    state.status = "DIRTY"
    assert not snapshot.current(context)
    state.status = "READY"
    state.document_json = before + " "
    assert not snapshot.current(context)
    state.document_json = before
    old_scale = context.scene.unit_settings.scale_length
    context.scene.unit_settings.scale_length = old_scale * 2
    assert not snapshot.current(context)
    context.scene.unit_settings.scale_length = old_scale
    key = document_state._scene_key(context.scene)
    original_record = document_state._RUNTIME[key]
    document_state._RUNTIME[key] = dict(original_record)
    assert not snapshot.current(context)
    document_state._RUNTIME[key] = original_record
    with patch.object(
        face_pick.backend_runtime, "assert_current", side_effect=RuntimeError("revoked")
    ):
        assert not snapshot.current(context)
    assert snapshot.current(context)
    acceptance_checks = []
    stub = SimpleNamespace(
        current=lambda context: True,
        hover=lambda context, event, *, accepting=False: (
            acceptance_checks.append(accepting) or True
        ),
        choose=lambda: False,
        hit=None,
    )
    operator = SimpleNamespace(_picker=stub)
    click = SimpleNamespace(type="LEFTMOUSE", value="PRESS")
    assert general_viewport.MCAD_OT_new_face_sketch.modal(operator, context, click) == {
        "RUNNING_MODAL"
    }
    for _ in range(2):
        assert edge_pick.MCAD_OT_pick_blend_faces.modal(operator, context, click) == {
            "RUNNING_MODAL"
        }
    assert acceptance_checks == [True, True, True], (
        "Both blend clicks and sketch click require full replay validation"
    )
    selected = tuple(context.selected_objects)
    picker = face_pick.FacePicker(context)
    assert picker.current(context)
    rv = area.spaces.active.region_3d
    rv.view_rotation = Quaternion((1, 0, 0, 0))
    rv.view_perspective = "ORTHO"
    rv.view_location = Vector((0.01, 0.015, 0.01))
    rv.view_distance = 0.1
    area.spaces.active.clip_start = 0.00001
    context.view_layer.update()
    # Real scene ray cast independently checks triangle-to-face mapping.
    hit, _, _, triangle, hit_obj, _ = context.scene.ray_cast(
        context.evaluated_depsgraph_get(), Vector((0.01, 0.015, 1)), Vector((0, 0, -1))
    )
    assert hit and hit_obj.original == obj
    assert (
        face_pick.resolve_triangle(face_pick.bound_feature(context, obj, result), triangle)["id"]
        == face["id"]
    )
    point = view3d_utils.location_3d_to_region_2d(region, rv, Vector((0.01, 0.015, 0.01)))
    if point is not None:
        event = SimpleNamespace(mouse_x=region.x + point.x, mouse_y=region.y + point.y)
        if picker.hover(context, event):
            assert picker.hit == (feature["id"], face["id"]), picker.message
            assert picker.message == "Click to sketch on this planar face. Esc cancels."
    with patch.object(face_pick.workspace_ui, "is_palette_event", return_value=True):
        assert not picker.hover(context, SimpleNamespace(mouse_x=0, mouse_y=0))
        assert picker.hit is None and not picker.points
        assert picker.message == "Click a planar CAD face to sketch. Esc cancels."
    picker.close()
    assert not face_pick._PICKERS and state.document_json == before
    assert tuple(context.selected_objects) == selected
    owner = general_session.GeneralSession(
        context, support={"feature_id": feature["id"], "face_id": face["id"]}
    )
    owner.start()
    assert all(
        abs(a - b) < 1e-9
        for a, b in zip(owner.geometry().plane.origin_mm, (10, 15, 10), strict=True)
    )
    assert tuple(owner.geometry().plane.normal) == (0, 0, 1)
    assert not picker.current(context)
    owner.suspend("Native test")
    state.sketch_draft_json = ""
    picker = face_pick.FacePicker(context)
    face_pick.cancel_all()
    assert picker.handler is None
unregister()
print("FACE_PICK_NATIVE_OK", flush=True)
