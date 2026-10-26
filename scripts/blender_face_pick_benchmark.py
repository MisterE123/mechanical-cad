"""Bounded native picker measurement on a real 25 mm rounded cylindrical housing.

Reports warmed 25-call distributions, not a whole-viewport FPS benchmark.
Run with MCAD_ROOT/MCAD_PYTHON and Blender --background --factory-startup.
"""

import json
import os
import statistics
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(os.environ["MCAD_ROOT"]) / "blender_addon"))
from mechanical_cad_blender import document_state, face_pick, register, unregister
from mechanical_cad_blender.display import _owned_objects

register()
context = bpy.context
state = context.scene.mechanical_cad
assert bpy.ops.mcad.new_document(name="Rounded housing benchmark") == {"FINISHED"}
assert bpy.ops.mcad.add_circle(radius=25) == {"FINISHED"}
assert bpy.ops.mcad.add_extrude(profile=state.active_feature, length=30) == {"FINISHED"}
assert bpy.ops.mcad.add_solid_feature(kind="fillet", base=state.active_feature, radius="2") == {
    "FINISHED"
}
result = document_state.current_part_result(context)
obj = _owned_objects(context.scene)[0]
feature = face_pick.bound_feature(context, obj, result)


def measure(fn):
    fn()
    times = []
    for _ in range(25):
        start = time.perf_counter()
        fn()
        times.append(1000 * (time.perf_counter() - start))
    return dict(median_ms=statistics.median(times), p95_ms=sorted(times)[23], max_ms=max(times))


snapshot = face_pick.HoverSnapshot(context)
print(
    "PICK_BENCHMARK "
    + json.dumps(
        dict(
            vertices=len(obj.data.vertices),
            triangles=len(obj.data.polygons),
            topology=len(feature["topology"]),
            snapshot_guard=measure(lambda: snapshot.current(context)),
            cached_hover_binding=measure(
                lambda: face_pick.bound_feature(context, obj, snapshot.result(context))
            ),
            bound_feature=measure(lambda: face_pick.bound_feature(context, obj, result)),
            current_result=measure(lambda: document_state.current_part_result(context)),
            combined=measure(
                lambda: face_pick.bound_feature(
                    context, obj, document_state.current_part_result(context)
                )
            ),
        )
    ),
    flush=True,
)
unregister()
