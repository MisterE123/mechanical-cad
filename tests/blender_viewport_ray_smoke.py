"""Native Local View edge-pick occlusion regression; run with --python-exit-code 1."""

import importlib.util
from pathlib import Path

import bpy
from mathutils import Vector

source = (
    Path(__file__).resolve().parents[1] / "blender_addon/mechanical_cad_blender/viewport_ray.py"
)
spec = importlib.util.spec_from_file_location("viewport_ray_smoke", source)
ray = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ray)

# An ordinary millimetre CAD display sits inside the unrelated default Cube.
# Local View excludes Cube visually; scene.ray_cast nevertheless hits it.
bpy.ops.mesh.primitive_cube_add(size=0.02, location=(0, 0, 0))
cad = bpy.context.object
cad.name = "CAD display"
for obj in bpy.context.scene.objects:
    obj.select_set(obj == cad)
bpy.context.view_layer.objects.active = cad
area = next(area for area in bpy.context.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(area=area, region=region):
    bpy.ops.view3d.localview(frame_selected=False)
    assert area.spaces.active.local_view is not None
    assert cad in bpy.context.visible_objects
    assert bpy.data.objects["Cube"] not in bpy.context.visible_objects
    graph = bpy.context.evaluated_depsgraph_get()
    origin, direction = Vector((0, 0.009999, 10)), Vector((0, 0, -1))
    assert bpy.context.scene.ray_cast(graph, origin, direction)[4].name == "Cube"
    hit = ray.ray_cast(bpy.context, graph, origin, direction)
    assert hit[0] and hit[4].original == cad
    assert abs(hit[1].z - 0.01) < 1e-6
    # Face and two-face pickers retain their exact polygon-map and matrix guards.
    assert 0 <= hit[3] < len(cad.data.polygons)
    assert hit[5] == cad.matrix_world
    assert hit[2].dot(direction) < -0.99
    bpy.ops.view3d.localview(frame_selected=False)
    # Visible non-CAD geometry remains a real occluder, never ignored by owner ID.
    hit = ray.ray_cast(bpy.context, graph, origin, direction)
    assert hit[0] and hit[4].original.name == "Cube"
print("VIEWPORT_RAY_LOCAL_VIEW_OCCLUSION_PASS")
