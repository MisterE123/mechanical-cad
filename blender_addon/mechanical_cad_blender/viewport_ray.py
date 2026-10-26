"""Ray hits against evaluated geometry visible in the owning viewport.

Scene.ray_cast ignores Local View, so unrelated hidden geometry must not occlude
CAD picking. Visible foreign geometry still participates and blocks selection.
"""

import math


def ray_cast(context, depsgraph, origin, direction):
    if not math.isfinite(direction.length) or direction.length <= 0:
        raise ValueError("The viewport did not provide a finite picking ray.")
    direction = direction.normalized()
    visible = {obj.original for obj in context.visible_objects}
    nonsurfaces = {"EMPTY", "CAMERA", "LIGHT", "LIGHT_PROBE", "ARMATURE", "LATTICE", "SPEAKER"}
    if any(obj.type not in nonsurfaces | {"MESH"} for obj in visible):
        raise ValueError(
            "A visible non-mesh surface cannot be tested safely. Isolate the CAD solid."
        )
    closest = None
    for instance in depsgraph.object_instances:
        obj = instance.object
        owner = instance.parent if instance.is_instance else obj
        if owner is not None and owner.original not in visible:
            continue
        if instance.is_instance:
            raise ValueError(
                "Visible generated instances cannot be picked safely. Isolate the CAD solid."
            )
        if obj.type != "MESH":
            continue
        matrix = instance.matrix_world.copy()
        inverse = matrix.inverted()
        local_origin = inverse @ origin
        local_direction = inverse.to_3x3() @ direction
        if not math.isfinite(local_direction.length) or local_direction.length <= 0:
            raise ValueError("A visible mesh has an invalid picking transform.")
        hit, location, normal, index = obj.ray_cast(local_origin, local_direction.normalized())
        if not hit:
            continue
        location = matrix @ location
        distance = (location - origin).dot(direction)
        if distance < 0 or (closest is not None and distance >= closest[0]):
            continue
        normal = inverse.transposed().to_3x3() @ normal
        normal.normalize()
        closest = (distance, location, normal, index, obj, matrix)
    if closest is None:
        return False, None, None, -1, None, None
    return (True, *closest[1:])
