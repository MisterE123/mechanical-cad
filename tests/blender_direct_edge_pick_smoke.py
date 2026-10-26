"""Native invocation/async/cancel/intent smoke; interactive qualification is separate."""

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
from mechanical_cad_blender import (  # noqa: E402  # noqa: E402
    direct_edge_pick,
    document_state,
    execution_lease,
    face_pick,
    register,
    sketch_pending,
    unregister,
)


def complete(picker, context):
    deadline = time.monotonic() + 30
    while picker.pending is not None:
        assert picker.current(context), "Lost current binding during preparation"
        assert time.monotonic() < deadline, "Edge preparation timed out"
        picker.poll_catalog(context)
        time.sleep(0.01)


def reaped():
    deadline = time.monotonic() + 10
    while sketch_pending.reap():
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert not execution_lease.is_busy()


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    for obj in context.scene.objects:
        obj.hide_set(True)
    state = context.scene.mechanical_cad
    assert bpy.ops.mcad.new_document(name="Direct edges") == {"FINISHED"}
    assert bpy.ops.mcad.add_rectangle(width=20, height=30) == {"FINISHED"}
    assert bpy.ops.mcad.add_extrude(profile=state.active_feature, length=10) == {"FINISHED"}
    before = state.document_json

    # Background Blender has no input event for bpy.ops INVOKE_DEFAULT. Exercise
    # the actual invoke method with only modal-handler registration substituted.
    class Manager:
        def modal_handler_add(self, owner):
            pass

        def __getattr__(self, name):
            return getattr(context.window_manager, name)

    class InvokeContext:
        window_manager = Manager()

        def __getattr__(self, name):
            return getattr(context, name)

    owner = SimpleNamespace(kind="fillet", report=lambda levels, text: print(text))
    assert direct_edge_pick.MCAD_OT_pick_blend_edge.invoke(owner, InvokeContext(), None) == {
        "RUNNING_MODAL"
    }
    picker = next(p for p in face_pick._PICKERS if isinstance(p, direct_edge_pick.BlendEdgePicker))
    assert picker.pending is not None and execution_lease.is_busy()
    complete(picker, context)
    assert picker.current(context) and not execution_lease.is_busy()
    solid = next(
        f
        for f in document_state.current_part_result(context)["features"]
        if (f.get("output") or {}).get("kind") == "solid"
    )
    entries = picker.catalog[solid["id"]]
    assert len(entries) == 12

    # Deterministic orthographic projection in background, but actual scene rays,
    # exact display binding, native catalog, ambiguity/visibility and click gates.
    def project(region, rv, point):
        return Vector((100 + point.x * 10000, 100 + point.y * 10000))

    def origin(region, rv, pixel):
        return Vector(((pixel[0] - 100) / 10000, (pixel[1] - 100) / 10000, 1))

    def location(region, rv, pixel, point):
        value = origin(region, rv, pixel)
        value.z = point.z
        return value

    picker.rv3d.view_perspective = "ORTHO"
    geometry = direct_edge_pick.view3d_utils
    with (
        patch.object(geometry, "location_3d_to_region_2d", side_effect=project),
        patch.object(geometry, "region_2d_to_origin_3d", side_effect=origin),
        patch.object(geometry, "region_2d_to_vector_3d", return_value=Vector((0, 0, -1))),
        patch.object(geometry, "region_2d_to_location_3d", side_effect=location),
    ):
        for pixel, should_pick in [((200, 100), True), ((200, 250), False), ((100, 100), False)]:
            picker.hit, picker.points = None, []
            with patch.object(picker, "hover_coordinates", return_value=pixel):
                assert picker.hover(context, None, accepting=True)
            assert bool(picker.hit) == should_pick, (pixel, picker.hit, picker.message)
            if should_pick:
                assert solid["id"] + "/face/cap.end" in picker.hit
                assert solid["id"] + "/face/cap.start" not in picker.hit
        picker.hit, picker.points = None, []
        with patch.object(picker, "hover_coordinates", return_value=(200, 100)):
            assert picker.hover(context, None, accepting=True)
    assert picker.hit is not None

    assert picker.choose()
    arguments = picker.dialog_arguments()
    assert arguments["picked_document_json"] == before
    assert arguments["picked_face_a"] != arguments["picked_face_b"]
    picker.close()
    assert state.document_json == before and not face_pick._PICKERS
    # Cancel immediately while a real native process may still be starting.
    owner = SimpleNamespace(kind="chamfer", report=lambda levels, text: print(text))
    assert direct_edge_pick.MCAD_OT_pick_blend_edge.invoke(owner, InvokeContext(), None) == {
        "RUNNING_MODAL"
    }
    picker = next(iter(face_pick._PICKERS))
    owner = SimpleNamespace(_picker=picker)
    assert direct_edge_pick.MCAD_OT_pick_blend_edge.modal(
        owner, context, SimpleNamespace(type="ESC")
    ) == {"CANCELLED"}
    assert picker.handler is None and picker.timer is None
    reaped()
    assert state.document_json == before
    # Stale canonical state cannot accept a prepared catalog.
    picker = direct_edge_pick.BlendEdgePicker(context, "fillet")
    state.status = "DIRTY"
    assert not picker.current(context)
    picker.close()
    reaped()
    state.status = "READY"
    # Lifecycle cancellation handles preparation, not just hover resources.
    picker = direct_edge_pick.BlendEdgePicker(context, "fillet")
    face_pick.cancel_all()
    reaped()
    assert not direct_edge_pick._PREPARING and not face_pick._PICKERS
unregister()
print("DIRECT_EDGE_PICK_NATIVE_OK", flush=True)
