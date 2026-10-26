"""Native viewport-filter isolation; headless evidence only, no GUI qualification."""

import gc
import os
import sys
import weakref
from pathlib import Path

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender.sketch_view_presentation import MeshVisibilityLease  # noqa: E402

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def data_snapshot():
    """Exact unrelated native data and visibility, including per-layer hide state."""
    return {
        "objects": tuple(
            (
                obj.as_pointer(),
                obj.name,
                obj.type,
                obj.data.as_pointer() if obj.data else None,
                obj.hide_viewport,
                obj.hide_render,
                obj.hide_select,
                tuple(tuple(row) for row in obj.matrix_world),
                tuple(collection.as_pointer() for collection in obj.users_collection),
                tuple(
                    (
                        layer.as_pointer(),
                        obj.hide_get(view_layer=layer),
                        obj.select_get(view_layer=layer),
                    )
                    for scene in bpy.data.scenes
                    for layer in scene.view_layers
                    if obj.name in layer.objects
                ),
            )
            for obj in bpy.data.objects
        ),
        "meshes": tuple(
            (
                mesh.as_pointer(),
                mesh.name,
                tuple(tuple(vertex.co) for vertex in mesh.vertices),
                tuple(tuple(edge.vertices) for edge in mesh.edges),
                tuple(tuple(face.vertices) for face in mesh.polygons),
                tuple(material.as_pointer() if material else None for material in mesh.materials),
            )
            for mesh in bpy.data.meshes
        ),
        "collections": tuple(
            (
                collection.as_pointer(),
                collection.name,
                collection.hide_viewport,
                collection.hide_render,
                collection.hide_select,
                tuple(obj.as_pointer() for obj in collection.objects),
                tuple(child.as_pointer() for child in collection.children),
            )
            for collection in bpy.data.collections
        ),
        "scenes": tuple(
            (
                scene.as_pointer(),
                scene.name,
                scene.unit_settings.system,
                scene.unit_settings.scale_length,
                tuple(obj.as_pointer() for obj in scene.objects),
            )
            for scene in bpy.data.scenes
        ),
    }


def other_filters(space):
    return {
        prop.identifier: getattr(space, prop.identifier)
        for prop in space.bl_rna.properties
        if prop.identifier.startswith("show_object_")
        and prop.identifier != "show_object_viewport_mesh"
    }


window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
other_area = next(area for area in window.screen.areas if area.type != "VIEW_3D")
other_area.type = "VIEW_3D"
space = area.spaces.active
other_space = other_area.spaces.active
check(space.as_pointer() != other_space.as_pointer(), "Two distinct native VIEW_3D spaces exist")

# Visibility differences are fixture setup only. The resource may never write
# these object/scene/collection settings, even for CAD-owned-looking objects.
scene = bpy.context.scene
mesh = bpy.data.meshes.new("Unrelated mesh data")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
visible = bpy.data.objects.new("Unrelated visible mesh", mesh)
scene.collection.objects.link(visible)
hidden = bpy.data.objects.new("Unrelated hidden mesh", mesh)
scene.collection.objects.link(hidden)
hidden.hide_render = True
hidden.hide_select = True
hidden.hide_set(True)
disabled = bpy.data.objects.new("Unrelated disabled mesh", mesh)
scene.collection.objects.link(disabled)
disabled.hide_viewport = True
empty = bpy.data.objects.new("Unrelated empty", None)
scene.collection.objects.link(empty)
scene.unit_settings.system = "IMPERIAL"
scene.unit_settings.scale_length = 0.03125
bpy.context.view_layer.update()
baseline = data_snapshot()

for original in (True, False):
    for other_original in (True, False):
        space.show_object_viewport_mesh = original
        other_space.show_object_viewport_mesh = other_original
        filters_before = other_filters(space), other_filters(other_space)
        other_visibility = tuple(obj.visible_get(viewport=other_space) for obj in scene.objects)
        lease = MeshVisibilityLease(space)
        check(space.show_object_viewport_mesh is False, "Owned native mesh filter is disabled")
        check(
            not visible.visible_get(viewport=space), "Mesh is actually excluded in owned viewport"
        )
        check(empty.visible_get(viewport=space), "Non-mesh context remains visible")
        check(
            other_space.show_object_viewport_mesh is other_original
            and other_visibility
            == tuple(obj.visible_get(viewport=other_space) for obj in scene.objects),
            "Second viewport filter and actual object visibility stay exact",
        )
        check(data_snapshot() == baseline, "Acquisition leaves unrelated native data exact")
        check(
            filters_before == (other_filters(space), other_filters(other_space)),
            "All other object-type viewport filters stay exact",
        )
        check(lease.restore() == "", "Native restore returns no diagnostic")
        check(
            space.show_object_viewport_mesh is original, "Exact original true/false filter restored"
        )
        check(lease._space is None and lease._original is None, "Restoration drops captured state")
        check(data_snapshot() == baseline, "Restoration leaves unrelated native data exact")
        # A second restore must not undo a later native user edit.
        space.show_object_viewport_mesh = not original
        check(lease.restore() == "", "Repeated native restoration is a no-op")
        check(
            space.show_object_viewport_mesh is not original, "Later native edits remain untouched"
        )

for original in (True, False):
    space.show_object_viewport_mesh = original
    lease = MeshVisibilityLease(space)
    space.show_object_viewport_mesh = True
    check(lease.restore() == "", "External native override restores without error")
    check(space.show_object_viewport_mesh is True, "External true wins over captured true or false")

# Replacing the editor and moving current context cannot redirect the resource.
space.show_object_viewport_mesh = True
other_space.show_object_viewport_mesh = False
lease = MeshVisibilityLease(space)
original_pointer = space.as_pointer()
area.type = "TEXT_EDITOR"
with bpy.context.temp_override(window=window, area=other_area):
    check(bpy.context.space_data == other_space, "Current viewport ownership moved elsewhere")
    check(lease.restore() == "", "Inactive captured VIEW_3D space restores successfully")
check(area.type == "TEXT_EDITOR", "Restoration does not change the replacement editor")
check(
    space.as_pointer() == original_pointer and space.show_object_viewport_mesh is True,
    "Only the exact retained original space is restored",
)
check(
    other_space.show_object_viewport_mesh is False, "Replacement/current viewport stays unchanged"
)
check(data_snapshot() == baseline, "Editor replacement cleanup leaves unrelated data exact")


class FakeSpace:
    """Fault boundary for invalidated RNA and partial native setter failure."""

    type = "VIEW_3D"

    def __init__(self, original=True):
        self.value = original
        self.reads = 0
        self.writes = 0
        self.read_error = False
        self.write_error = ""
        self.ignore_write = False
        self.destroy_after_write = False

    @property
    def show_object_viewport_mesh(self):
        self.reads += 1
        if self.read_error:
            raise ReferenceError("StructRNA of type SpaceView3D has been removed")
        return self.value

    @show_object_viewport_mesh.setter
    def show_object_viewport_mesh(self, value):
        self.writes += 1
        if self.write_error == "before":
            raise RuntimeError("Native setter failed before write")
        if not self.ignore_write:
            self.value = value
        if self.destroy_after_write:
            self.read_error = True
            raise ReferenceError("Native space disappeared after write")
        if self.write_error == "after":
            self.write_error = ""
            raise RuntimeError("Native setter failed after write")


def failed_acquisition(fake):
    # Keep the instance so failed __init__ reference release can be asserted.
    resource = MeshVisibilityLease.__new__(MeshVisibilityLease)
    try:
        resource.__init__(fake)
    except RuntimeError as exc:
        diagnostic = str(exc)
        check(exc.__context__ is None, "Acquisition error does not retain a native traceback")
    else:
        raise AssertionError("Expected acquisition failure")
    check(resource._space is None and resource._original is None, "Failed acquisition drops RNA")
    touched = fake.reads, fake.writes
    check(resource.restore() == "", "Failed acquisition cleanup is idempotent")
    check(touched == (fake.reads, fake.writes), "Failed acquisition never revisits old RNA")
    return diagnostic


for failure in ("before", "after"):
    fake = FakeSpace()
    fake.write_error = failure
    diagnostic = failed_acquisition(fake)
    check(
        "Could not set sketch mesh visibility" in diagnostic,
        "Acquisition failure has a useful diagnostic",
    )
    check(fake.value is True, "Failed and partially failed acquisition preserve original value")

fake = FakeSpace()
fake.read_error = True
check("ReferenceError" in failed_acquisition(fake), "Removed native space cannot be acquired")
check(fake.writes == 0, "Read failure never writes native state")
fake = FakeSpace()
fake.type = "TEXT_EDITOR"
check("VIEW_3D" in failed_acquisition(fake), "Wrong editor fails safely")
check(fake.reads == fake.writes == 0, "Wrong editor never accesses the mesh filter")
fake = FakeSpace()
fake.ignore_write = True
check("did not accept" in failed_acquisition(fake), "An ignored native write is detected")
check(fake.value is True, "An ignored native write preserves original state")
fake = FakeSpace()
fake.destroy_after_write = True
check(
    "Cleanup also failed" in failed_acquisition(fake),
    "Acquisition plus rollback failure reports both diagnostics and drops RNA",
)

for failure in ("read", "write"):
    fake = FakeSpace()
    lease = MeshVisibilityLease(fake)
    if failure == "read":
        fake.read_error = True
    else:
        fake.write_error = "before"
    diagnostic = lease.restore()
    check("Could not restore" in diagnostic, "Cleanup returns a native-failure diagnostic")
    check(lease._space is None and lease._original is None, "Failed cleanup drops captured RNA")
    touched = fake.reads, fake.writes
    check(lease.restore() == "", "Failed cleanup is still idempotent")
    check(touched == (fake.reads, fake.writes), "Repeated cleanup never revisits destroyed RNA")
    reference = weakref.ref(fake)
    del fake
    gc.collect()
    check(reference() is None, "Released resource retains no native-owner stand-in")

check(
    data_snapshot() == baseline, "All visibility and native-data preservation checks remain exact"
)
print("SKETCH_VIEW_PRESENTATION_SMOKE_OK", len(checks), bpy.app.version_string)
