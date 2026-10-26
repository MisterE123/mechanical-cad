"""Self-contained saved-perspective/native-ray regression from a generated demo.

The canonical Part and exact saved view parameters are repository fixtures.
Blender background mode cannot safely recompute viewport matrices, so immutable
copies of the saved matrices feed unmodified view3d_utils projection functions.
All scene raycasts, display binding and guarded catalog checks remain native.
"""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import direct_edge_pick, document_state, register, unregister  # noqa: E402

register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    # This factory-startup script never needs a user .blend or private state.
    for obj in list(context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    fixture = json.loads((ROOT / "examples/edge_projection_demo.mcad.json").read_text())
    saved_view = json.loads((ROOT / "examples/edge_projection_view.json").read_text())
    document_state._populate_document(context.scene, fixture)
    document_state.regenerate(context)
    before = context.scene.mechanical_cad.document_json
    picker = direct_edge_pick.BlendEdgePicker(context, "fillet")
    deadline = time.monotonic() + 30
    while picker.pending is not None:
        assert time.monotonic() < deadline
        picker.poll_catalog(context)
        time.sleep(0.01)
    # Restore actual saved camera matrices, not a mocked projection algorithm.
    # Region routing is outside this regression and still uses the real area.
    projection_region = SimpleNamespace(**saved_view["region"])
    view = dict(saved_view["view"])
    for name in ("view_matrix", "perspective_matrix", "window_matrix"):
        view[name] = Matrix(view[name])
    picker.region = projection_region
    picker.rv3d = SimpleNamespace(**view)
    # This surviving native edge is a genuine silhouette in the saved view.
    faces = ["extrude_1/face/cap.end", "extrude_1/face/side.line.l_d8"]
    entry = next(e for e in picker.catalog["fillet_1"] if e["faces"] == faces)
    point = (Vector(entry["points"][0]) + Vector(entry["points"][-1])) * 0.0005
    pixel = view3d_utils.location_3d_to_region_2d(projection_region, picker.rv3d, point)
    assert pixel is not None

    def hover():
        picker.hit, picker.points = None, []
        # Only event-region routing is bypassed. Projection, clipping, perspective
        # interpolation, world tolerances, native scene rays and evidence are real.
        with patch.object(picker, "hover_coordinates", return_value=pixel):
            assert picker.hover(context, None, accepting=True)
        return picker.hit

    # A different object behind a missed exact silhouette ray must not block the
    # valid subpixel adjacent-face hit. A true foreground object must still block.
    origin = view3d_utils.region_2d_to_origin_3d(projection_region, picker.rv3d, pixel)
    direction = view3d_utils.region_2d_to_vector_3d(projection_region, picker.rv3d, pixel)
    bpy.ops.mesh.primitive_cube_add(size=0.004, location=point + direction * 0.02)
    background = context.object
    context.view_layer.update()
    hit, _, _, _, hit_obj, _ = context.scene.ray_cast(
        context.evaluated_depsgraph_get(), origin, direction
    )
    assert hit and hit_obj.original == background, "Fixture must reproduce center-ray miss"
    assert hover() == ("fillet_1", *faces), picker.message
    bpy.ops.mesh.primitive_cube_add(size=0.004, location=point - direction * 0.01)
    blocker = context.object
    context.view_layer.update()
    assert hover() is None, "Foreground occluder must not expose the CAD edge behind it"
    bpy.data.objects.remove(blocker, do_unlink=True)
    context.view_layer.update()
    assert hover() == ("fillet_1", *faces)
    assert context.scene.mechanical_cad.document_json == before
    picker.close()
    bpy.data.objects.remove(background, do_unlink=True)
unregister()
print("DIRECT_EDGE_REAL_PROJECTION_OK", flush=True)
