"""Native Blender assembly boundary smoke; no native CAD modules enter Blender.

blender --background --factory-startup --python-exit-code 1 \
    --python tests/blender_assembly_display_smoke.py
"""

import copy
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import assembly_bridge as bridge  # noqa: E402
from mechanical_cad_blender import assembly_display as display  # noqa: E402
from mechanical_cad_blender import backend_runtime, guarded_operations, register, unregister  # noqa: E402
from mechanical_cad_blender.common import OWNER_KEY as PART_OWNER_KEY  # noqa: E402

checks = []


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def reject(operation, label):
    try:
        operation()
    except (bridge.bridge.BridgeError, RuntimeError):
        checks.append(label)
        return
    raise AssertionError(label)


class GuardedFixture(dict):
    """Presentation bytes plus fresh process evidence for each publication."""

    def __init__(self, assembly, action="assembly_replay", **arguments):
        self.assembly, self.action, self.arguments = assembly, action, arguments
        self.refresh()
        super().__init__(self.evidence.revalidate(self.current(), owner_token=self.token))

    def current(self):
        return backend_runtime.capture(bpy.context)

    def refresh(self):
        if self:
            self.evidence.revalidate(self.current(), owner_token=self.token, projection=dict(self))
        self.token = object()
        self.evidence = guarded_operations.assembly_action_guarded(
            self.assembly,
            self.action,
            **self.arguments,
            selection=self.current(),
            owner_token=self.token,
            current_selection=self.current,
        )

    def __deepcopy__(self, memo):
        return copy.deepcopy(dict(self), memo)


def stage(scene, owner, response, **arguments):
    if not isinstance(response, GuardedFixture):
        return display.stage(scene, owner, response, **arguments)
    # Every publication is a fresh operation, never a second token from saved bytes.
    response.refresh()
    return display.stage(
        scene,
        owner,
        response.evidence,
        owner_token=response.token,
        current_selection=response.current,
        **arguments,
    )


def trusted(scene, owner, response, **arguments):
    return display.trusted_display(
        scene,
        owner,
        response.evidence,
        owner_token=response.token,
        current_selection=response.current,
        **arguments,
    )


def replace_display(scene, owner, response, **arguments):
    transaction = stage(scene, owner, response, **arguments)
    try:
        transaction.publish()
        return transaction.finalize()
    except Exception:
        transaction.discard()
        raise


def request(far=False):
    raw = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    angle = math.pi / 2
    raw["ground"] = {
        "xyz_mm": [12.3456789, -23.456789, 34.56789],
        "wxyz": [math.cos(angle / 2), 0, 0, math.sin(angle / 2)],
    }
    source = raw["part_sources"][0]
    params = source["document"]["features"][0]["params"]
    params.update(x=123.456789, y=-23.456789, z=8.125)
    if far:
        params.update(x=900000.125, y=-800000.25, height=0.03)
        source["document"]["parameters"]["width"] = 0.01
        source["document"]["features"][1]["params"]["length"] = 0.02
    source["source_digest"] = bridge.canonical_digest(source["document"])
    raw["parts"][0]["source_digest"] = source["source_digest"]
    return raw


scene = bpy.context.scene
owner = "assembly-smoke-owner"
original_objects = {obj.as_pointer() for obj in scene.objects}
register()
response = GuardedFixture(request())
verified = GuardedFixture(request(), "assembly_check", requirements=[])
check(verified["ok"] and verified["report"]["passed"], "real sidecar check is validated end to end")
sampled = GuardedFixture(
    request(),
    "assembly_sample",
    coordinates={"slide_a": 100, "slide_b": 200},
    samples={"joint_id": "slide_a", "values": [50, 60]},
    requirements=[],
)
check(
    sampled["ok"] and sampled["report"]["passed"],
    "real sidecar sampling retains full base and finite witness evidence",
)
for row in sampled["report"]["poses"]:
    check(
        row["pose"]["effective_coordinates"]["slide_b"] == 200,
        "sample retains nonsampled joint override",
    )
canonical_bytes = json.dumps(response["result"]["canonical_assembly"], sort_keys=True)
for scene_scale in (1.0, 0.01, 2.5):
    scene.unit_settings.scale_length = scene_scale
    actual_scale = float(scene.unit_settings.scale_length)
    tx = stage(scene, owner, response)
    check(
        not display.owned_objects(scene, owner) or tx.old_objects,
        "staging does not replace existing scene display",
    )
    objects = tx.publish()
    check(tx.status == "published", "publication remains reversible")
    tx.finalize()
    check(len(objects) == 9, "three instances and six independently tagged datum axes")
    instances = [o for o in objects if o.get(display.ROLE_KEY) == "instance"]
    check(
        len({o.data.as_pointer() for o in instances}) == 1,
        "repeated instances share one recentered definition mesh",
    )
    check(
        trusted(scene, owner, response),
        "current scene-scale display matches validated snapshot",
    )
    check(
        all(PART_OWNER_KEY not in o for o in objects),
        "assembly ownership is disjoint from Part cleanup",
    )
    bpy.context.view_layer.update()
    for axis in (item for item in objects if item.get(display.ROLE_KEY) == "frame"):
        pose = response["report"]["base_pose"]["transforms"][axis[display.INSTANCE_KEY]]
        offset_y = 30 if axis[display.FRAME_KEY] == "offset" else 0
        expected_axis = [
            value * 0.001 / actual_scale
            for value in (
                pose["xyz_mm"][0],
                pose["xyz_mm"][1] + offset_y,
                pose["xyz_mm"][2],
            )
        ]
        check(
            all(
                math.isclose(a, b, abs_tol=2e-5, rel_tol=1e-6)
                for a, b in zip(axis.location, expected_axis, strict=True)
            ),
            "literal datum axis independently follows rotated local frame",
        )
    native_vertices = response["result"]["parts"][0]["mesh"]["vertices"]
    for obj in instances:
        pose = response["report"]["base_pose"]["transforms"][obj[display.INSTANCE_KEY]]
        for local, point in zip(obj.data.vertices, native_vertices, strict=True):
            rotated = display._rotate(pose["wxyz"], point)
            expected = tuple(
                0.001 / actual_scale * (v + t) for v, t in zip(rotated, pose["xyz_mm"], strict=True)
            )
            actual = obj.matrix_world @ local.co
            check(
                all(
                    math.isclose(a, b, abs_tol=2e-5, rel_tol=1e-6)
                    for a, b in zip(actual, expected, strict=True)
                ),
                "recentered rotated world point agrees with canonical mm",
            )
check(
    json.dumps(response["result"]["canonical_assembly"], sort_keys=True) == canonical_bytes,
    "display never changes canonical coordinates",
)
check(
    original_objects <= {obj.as_pointer() for obj in scene.objects},
    "unrelated scene objects survive replacement",
)

# Explicit sampled pose and base pose have different cache identities.
tx = stage(scene, owner, sampled, pose_index=0)
tx.publish()
check(
    trusted(scene, owner, sampled, pose_index=0),
    "explicit sample display binds its selected pose",
)
check(
    not trusted(scene, owner, sampled),
    "sample display cannot masquerade as full requested base pose",
)
tx.rollback()
check(
    trusted(scene, owner, response),
    "sample preview rollback restores requested replay display",
)

# Trusted cache rejects each independent Blender-only edit.
obj = next(o for o in display.owned_objects(scene, owner) if o.type == "MESH")
location = tuple(obj.location)
obj.location.x += 1
check(
    not trusted(scene, owner, response),
    "manual transform invalidates display trust",
)
obj.location = location
obj.delta_scale = (2, 1, 1)
check(not trusted(scene, owner, response), "delta scale invalidates display trust")
obj.delta_scale = (1, 1, 1)
parent = bpy.data.objects.new("unrelated parent", None)
scene.collection.objects.link(parent)
obj.parent = parent
check(not trusted(scene, owner, response), "parenting invalidates display trust")
obj.parent = None
modifier = obj.modifiers.new("manual deformation", "BEVEL")
check(not trusted(scene, owner, response), "modifier invalidates display trust")
obj.modifiers.remove(modifier)
point = tuple(obj.data.vertices[0].co)
obj.data.vertices[0].co += Vector((0.01, 0, 0))
check(
    not trusted(scene, owner, response),
    "manual mesh edit invalidates all shared-instance display trust",
)
obj.data.vertices[0].co = point
check(
    trusted(scene, owner, response),
    "restoring exact display channels restores cache match",
)

# A source/display transaction can undo publication after canonical commit fails.
old = {o.as_pointer() for o in display.owned_objects(scene, owner)}
tx = stage(scene, owner, response)
tx.publish()
tx.rollback()
check(
    {o.as_pointer() for o in display.owned_objects(scene, owner)} == old,
    "post-publication canonical failure restores original objects",
)
check(trusted(scene, owner, response), "rollback restores trusted old display")

original_configure = display._configure
count = [0]


def fail_configure(*args):
    count[0] += 1
    if count[0] == 3:
        raise RuntimeError("injected object staging failure")
    return original_configure(*args)


display._configure = fail_configure
counts = len(bpy.data.objects), len(bpy.data.meshes)
reject(lambda: stage(scene, owner, response), "injected staging failure is rejected")
display._configure = original_configure
check(
    (len(bpy.data.objects), len(bpy.data.meshes)) == counts,
    "staging failure cleans every new object and mesh",
)
check(
    {o.as_pointer() for o in display.owned_objects(scene, owner)} == old,
    "staging failure leaves old scene untouched",
)

tx = stage(scene, owner, response)
original_unlink = display._unlink
count[0] = 0


def fail_unlink(*args):
    count[0] += 1
    if count[0] == 2:
        raise RuntimeError("injected swap failure")
    return original_unlink(*args)


display._unlink = fail_unlink
reject(tx.publish, "injected swap failure is rejected")
display._unlink = original_unlink
tx.discard()
check(
    {o.as_pointer() for o in display.owned_objects(scene, owner)} == old,
    "swap failure restores all old scene links",
)

# Cleanup is post-commit: a partial deletion cannot undo an accepted Apply.
tx = stage(scene, owner, response)
tx.publish()
original_cleanup = display._remove_orphans


def fail_cleanup(objects, meshes, owner_id):
    original_cleanup(objects[:1], [], owner_id)
    raise RuntimeError("injected post-commit cleanup failure")


display._remove_orphans = fail_cleanup
tx.finalize()
display._remove_orphans = original_cleanup
check(
    tx.status == "finalized" and tx.cleanup_warnings,
    "post-commit cleanup failure is a warning on accepted display",
)
check(
    trusted(scene, owner, response),
    "partial orphan cleanup cannot invalidate accepted new geometry",
)
reject(tx.rollback, "accepted finalized display cannot attempt impossible rollback")
original_cleanup(tx.old_objects, tx.old_meshes, owner)

# Linked objects in a different scene survive our unlink and finalization.
other = bpy.data.scenes.new("Other scene")
shared_object = display.owned_objects(scene, owner)[0]
other.collection.objects.link(shared_object)
other_pointer = shared_object.as_pointer()
old_mesh_pointer = shared_object.data.as_pointer() if shared_object.type == "MESH" else None
replace_display(scene, owner, response)
check(
    any(o.as_pointer() == other_pointer for o in other.objects),
    "other scene retains its linked object",
)
if old_mesh_pointer:
    check(
        shared_object.data.as_pointer() == old_mesh_pointer,
        "other scene retains untouched old mesh datablock",
    )
check(
    shared_object.name not in scene.objects,
    "replaced linked object is detached only from requested scene",
)

shared_collection = bpy.data.collections.new("Shared assembly collection")
scene.collection.children.link(shared_collection)
other.collection.children.link(shared_collection)
obj = display.owned_objects(scene, owner)[0]
shared_collection.objects.link(obj)
old = {o.as_pointer() for o in display.owned_objects(scene, owner)}
reject(
    lambda: stage(scene, owner, response),
    "shared-collection cross-scene replacement blocked before mutation",
)
check(
    {o.as_pointer() for o in display.owned_objects(scene, owner)} == old,
    "shared collection rejection leaves scene intact",
)
shared_collection.objects.unlink(obj)

# Existing Part cleanup/regeneration cannot consume assembly siblings.
old = {o.as_pointer() for o in display.owned_objects(scene, owner)}
check(bpy.ops.mcad.new_demo() == {"FINISHED"}, "ordinary Part demo replay succeeds beside assembly")
check(
    bpy.ops.mcad.regenerate() == {"FINISHED"}, "ordinary Part regeneration succeeds beside assembly"
)
check(
    {o.as_pointer() for o in display.owned_objects(scene, owner)} == old,
    "Part regenerate preserves every assembly sibling and datum",
)

# Tiny geometry at large canonical coordinates retains local mesh dimensions.
far = GuardedFixture(request(far=True))
scene.unit_settings.scale_length = 0.01
replace_display(scene, owner, far)
obj = next(o for o in display.owned_objects(scene, owner) if o.type == "MESH")
scale = 0.001 / float(scene.unit_settings.scale_length)
for axis, dimension in enumerate((0.01, 0.03, 0.02)):
    coordinates = [v.co[axis] for v in obj.data.vertices]
    check(
        math.isclose(max(coordinates) - min(coordinates), dimension * scale, rel_tol=5e-6),
        "far-origin tiny local dimension preserved",
    )
check(bool(obj[display.PRECISION_KEY]), "far-origin placement precision limitation remains visible")
check(trusted(scene, owner, far), "far-origin recentered cache remains trustworthy")
scene.unit_settings.scale_length = 1
check(not trusted(scene, owner, far), "scene unit changes invalidate cached display")
changed = copy.deepcopy(far)
changed["result"]["parts"][0]["mesh"]["vertices"][0][0] += 1
reject(
    lambda: stage(scene, owner, changed),
    "mutated formerly-validated response cannot be displayed",
)
blocked = GuardedFixture(request(), coordinates={"slide_a": 999})
reject(lambda: stage(scene, owner, blocked), "blocked base pose cannot become current display")
check(
    not any(
        name.split(".")[0] in {"OCP", "cadquery", "mechanical_cad", "slvs"} for name in sys.modules
    ),
    "Blender imported no native CAD or core modules",
)
unregister()
print(
    "ASSEMBLY_DISPLAY_SMOKE_OK",
    json.dumps({"checks": len(checks), "blender": bpy.app.version_string}),
)
