"""Script-generated editable scene plus separate literal-geometry presentation.

Isolated Blender only. Set MCAD_ROOT, MCAD_PYTHON, MCAD_ADAPTER_OUTPUT; the output
must already contain the generator model and native presentation_meshes.json.
No native kernel is imported into Blender. Does not establish GUI authoring.
"""

import json
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

assert bpy.app.background, "Use an isolated background process"
root = Path(os.environ["MCAD_ROOT"])
out = Path(os.environ["MCAD_ADAPTER_OUTPUT"])
sys.path.insert(0, str(root / "blender_addon"))
from mechanical_cad_blender import register, unregister  # noqa: E402

bpy.ops.wm.read_homefile(use_empty=True)
register()
editable = bpy.context.scene
editable.name = "Editable adapter Part"
editable.unit_settings.system = "METRIC"
editable.unit_settings.scale_length = 0.001
editable.unit_settings.length_unit = "MILLIMETERS"
assert bpy.ops.mcad.load_document(
    filepath=str(out / "imported_mounting_adapter.mcad.json")
) == {"FINISHED"}
assert editable.mechanical_cad.status == "READY", editable.mechanical_cad.error
editable.mechanical_cad.document_path = ""
scene = bpy.data.scenes.new("Presentation - true 2 mm gap")
bpy.context.window.scene = scene
scene.unit_settings.system = "METRIC"
scene.render.engine = "CYCLES"
scene.cycles.samples = 32
scene.cycles.use_denoising = True
scene.render.resolution_x = 1400
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.world = bpy.data.worlds.new("Presentation world")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.12, 0.15, 0.22, 1)
scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.5
scene.view_settings.view_transform = "AgX"


def material(name, color, metallic=0):
    value = bpy.data.materials.new(name)
    value.diffuse_color = (*color, 1)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = 0.3
    return value


meshes = json.loads((out / "presentation_meshes.json").read_text())
for name, color in (("base", (0.045, 0.20, 0.38)), ("adapter", (0.9, 0.32, 0.055))):
    native = meshes[name]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([[v * 0.001 for v in point] for point in native["vertices"]], [],
                     native["triangles"])
    mesh.update()
    obj = bpy.data.objects.new(name.title() + " - exact replay display", mesh)
    scene.collection.objects.link(obj)
    obj.data.materials.append(material(name, color, 0.35))
    obj["purpose"] = "Presentation mesh from native replay, not canonical CAD identity"

camera_data = bpy.data.cameras.new("Presentation camera")
camera = bpy.data.objects.new("Presentation camera", camera_data)
scene.collection.objects.link(camera)
camera.location = (0.135, -0.18, 0.14)
camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
camera_data.type = "ORTHO"
camera_data.ortho_scale = 0.18
camera_data.clip_start = 0.001
camera_data.clip_end = 10
scene.camera = camera
for name, location, power, size in [
    ("Key", (0.06, -0.10, 0.18), 0.7, 0.12),
    ("Fill", (-0.12, -0.02, 0.10), 0.3, 0.10),
    ("Rim", (0.04, 0.12, 0.12), 0.8, 0.08),
]:
    light = bpy.data.lights.new(name, "AREA")
    light.energy, light.shape, light.size = power, "DISK", size
    obj = bpy.data.objects.new(name, light)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (-Vector(location)).to_track_quat("-Z", "Y").to_euler()

# Camera-facing labels describe measured nominal geometry, not an exploded view.
orientation = camera.rotation_euler.to_quaternion()
text_mat = material("Label", (0.85, 0.9, 1))
shader = text_mat.node_tree.nodes.get("Principled BSDF")
shader.inputs["Emission Color"].default_value = (0.85, 0.9, 1, 1)
shader.inputs["Emission Strength"].default_value = 1
for name, body, y, size in [
    ("Title", "IMPORTED BASE / FIXED ADAPTER", 0.056, 0.0043),
    ("Subtitle", "60 x 40 x 6 mm adapter  |  4 x diameter 6 + diameter 14 mm", 0.048, 0.0022),
    ("Gap", "TRUE 2 mm GAP   /   No source-edit association", -0.052, 0.0026),
    ("Boundary", "Script-generated CAD example. Illustrative geometry, not manufacturing qualification.",
     -0.060, 0.0018),
]:
    curve = bpy.data.curves.new(name, "FONT")
    curve.body, curve.align_x, curve.size = body, "CENTER", size
    obj = bpy.data.objects.new(name, curve)
    scene.collection.objects.link(obj)
    obj.location = orientation @ Vector((0, y, 0.08))
    obj.rotation_euler = camera.rotation_euler
    curve.materials.append(text_mat)
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(out / "imported_adapter.png")
scene["scope"] = "Script-generated presentation; physical placement is not exploded"
# Save opening on the presentation; editable canonical Part is a separate scene.
assert bpy.ops.wm.save_as_mainfile(filepath=str(out / "Imported mounting adapter.blend")) == {"FINISHED"}
bpy.ops.render.render(write_still=True)
print("IMPORTED_ADAPTER_BLENDER_VISUAL_OK", flush=True)
unregister()
