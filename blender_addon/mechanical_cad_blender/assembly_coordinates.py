"""Native-free named joint coordinate schemas and authored complete base maps."""

EXTRA_COORDINATES = {
    "cylindrical": ("rotation",),
    "planar": ("translation_x", "translation_y", "rotation"),
    "spherical": ("rotation_x", "rotation_y", "rotation"),
}
NO_SCALAR_COORDINATE = {"fixed", "planar", "spherical"}


def extra_names(kind):
    return EXTRA_COORDINATES.get(kind, ())


def coordinate_specs(joint):
    result = {
        joint["id"]: (
            joint.get("coordinate", 0.0),
            joint.get("limits"),
            1e4 if joint["kind"] == "revolute" else 1e6,
        )
    }
    for field in extra_names(joint["kind"]):
        result[joint["id"] + ":" + field] = (
            joint[field],
            joint[field + "_limits"],
            1e6 if field.startswith("translation") else 1e4,
        )
    return result


def authored_coordinates(joints):
    return {
        key: value
        for joint in joints
        for key, (value, _, _) in coordinate_specs(joint).items()
        if value is not None
    }


def structural_dof(joint):
    return {"fixed": 0, "cylindrical": 2, "planar": 3, "spherical": 3}.get(joint["kind"], 1)
