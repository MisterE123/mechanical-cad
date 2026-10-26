"""Native-free source-bound resolution and kinematics for associative datums."""

import math

from .assembly_validation_common import _frame, _keys, _require
from .topology_evidence import validate_signature


def _multiply(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return [
        w * v - x * i - y * j - z * k,
        w * i + x * v + y * k - z * j,
        w * j - x * k + y * v + z * i,
        w * k + x * j - y * i + z * v,
    ]


def _unit(q):
    length = math.sqrt(sum(v * v for v in q))
    return [v / length for v in q]


def _rotate(q, p):
    q = _unit(q)
    return _multiply(_multiply(q, [0, *p]), [q[0], -q[1], -q[2], -q[3]])[1:]


def compose(a, b):
    offset = _rotate(a["wxyz"], b["xyz_mm"])
    return {
        "xyz_mm": [x + y for x, y in zip(a["xyz_mm"], offset, strict=True)],
        "wxyz": _unit(_multiply(_unit(a["wxyz"]), _unit(b["wxyz"]))),
    }


def _inverse(a):
    w, x, y, z = _unit(a["wxyz"])
    q = [w, -x, -y, -z]
    return {"xyz_mm": _rotate(q, [-v for v in a["xyz_mm"]]), "wxyz": q}


def same_frame(actual, expected):
    _frame(actual)
    return (
        all(
            math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-7)
            for a, b in zip(actual["xyz_mm"], expected["xyz_mm"], strict=True)
        )
        and abs(
            sum(a * b for a, b in zip(_unit(actual["wxyz"]), _unit(expected["wxyz"]), strict=True))
        )
        >= 1 - 1e-12
    )


def _basis_quaternion(u, v, n):
    m = [[u[i], v[i], n[i]] for i in range(3)]
    trace = sum(m[i][i] for i in range(3))
    if trace > 0:
        s = 2 * math.sqrt(1 + trace)
        return _unit(
            [s / 4, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s]
        )
    i = max(range(3), key=lambda axis: m[axis][axis])
    j, k = (i + 1) % 3, (i + 2) % 3
    s = 2 * math.sqrt(1 + m[i][i] - m[j][j] - m[k][k])
    xyz = [0.0] * 3
    xyz[i] = s / 4
    xyz[j] = (m[j][i] + m[i][j]) / s
    xyz[k] = (m[k][i] + m[i][k]) / s
    return _unit([(m[k][j] - m[j][k]) / s, *xyz])


def face_frame(signature):
    validate_signature(signature)
    _require(signature["surface"] == "plane", "associative datum requires a planar face")
    n = signature["normal"]
    reference = [0, 1, 0] if abs(n[0]) > 0.9 else [1, 0, 0]
    dot = sum(a * b for a, b in zip(reference, n, strict=True))
    u = [reference[i] - dot * n[i] for i in range(3)]
    length = math.hypot(*u)
    u = [v / length for v in u]
    v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    return {"xyz_mm": signature["centroid"], "wxyz": _basis_quaternion(u, v, n)}


def validate_resolved_frames(row, definition):
    frames = definition["mate_frames"]
    resolved = row["resolved_mate_frames"]
    _keys(resolved, {frame["id"] for frame in frames})
    topology = {face["id"]: face for face in row["topology"]}
    for frame in frames:
        expected = frame["placement"]
        if "support_face" in frame:
            support = topology.get(frame["support_face"])
            _require(
                support is not None and support["provenance"]["semantic_status"] == "stable",
                "associative datum support is missing or ambiguous",
            )
            expected = compose(face_frame(support["signature"]), expected)
        _require(
            same_frame(resolved[frame["id"]], expected),
            "resolved datum differs from its current support face and local offset",
        )


def validate_associative_pose(pose, result, joints, instances):
    canonical = result["canonical_assembly"]
    associative = any(
        "support_face" in frame for part in canonical["parts"] for frame in part["mate_frames"]
    )
    if not canonical.get("gear_relations") and not associative:
        return
    if associative:
        parts = {part["id"]: part for part in result["parts"]}
        _require(
            set(parts) == {part["id"] for part in canonical["parts"]},
            "associative pose lacks resolved part evidence",
        )
    else:
        # Literal geared kinematics are fully determined by canonical frames.
        # The service intentionally evaluates this base pose before building
        # Parts, so a genuine source/mesh failure can have no native parts yet.
        # Never infer face-attached frames or grant geometry/display authority.
        parts = {part["id"]: part for part in canonical["parts"]}

    def frame(instance, identifier):
        part = parts[instances[instance]["part_id"]]
        if "resolved_mate_frames" in part:
            return part["resolved_mate_frames"][identifier]
        return next(
            value["placement"] for value in part["mate_frames"] if value["id"] == identifier
        )

    transforms = {canonical["grounded_instance"]: canonical["ground"]}
    pending = dict(joints)
    while pending:
        ready = [key for key, joint in pending.items() if joint["parent"] in transforms]
        _require(ready, "associative pose graph is disconnected")
        for key in ready:
            joint = pending.pop(key)
            value = pose["effective_coordinates"][key]
            values = pose["effective_coordinates"]
            kind = joint["kind"]
            angle = (
                values[key + ":rotation"]
                if kind in {"cylindrical", "planar", "spherical"}
                else value
            )
            rotation = (
                [math.cos(angle / 2), 0, 0, math.sin(angle / 2)]
                if kind in {"revolute", "cylindrical", "planar", "spherical"}
                else [1, 0, 0, 0]
            )
            translation = [0, 0, value if kind in {"slider", "cylindrical"} else 0]
            if kind == "planar":
                translation = [values[key + ":translation_x"], values[key + ":translation_y"], 0]
            elif kind == "spherical":
                x, y = values[key + ":rotation_x"] / 2, values[key + ":rotation_y"] / 2
                rotation = _multiply(
                    rotation,
                    _multiply([math.cos(y), 0, math.sin(y), 0], [math.cos(x), math.sin(x), 0, 0]),
                )
            motion = {"xyz_mm": translation, "wxyz": rotation}
            transforms[joint["child"]] = compose(
                compose(
                    compose(
                        transforms[joint["parent"]], frame(joint["parent"], joint["parent_frame"])
                    ),
                    motion,
                ),
                _inverse(frame(joint["child"], joint["child_frame"])),
            )
    _require(
        set(transforms) == set(pose["transforms"])
        and all(same_frame(pose["transforms"][key], value) for key, value in transforms.items()),
        "pose transforms contradict the verified resolved mate frames",
    )
