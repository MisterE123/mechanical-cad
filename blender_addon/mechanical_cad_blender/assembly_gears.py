"""Native-free gear relation contract and deterministic coordinate derivation."""

import math

from .assembly_validation_common import (
    MAX_JOINTS,
    _identifier,
    _keys,
    _number,
    _records,
    _require,
    _text,
)


def ordered_relations(assembly):
    joints = {joint["id"]: joint for joint in assembly["joints"]}
    relations = _records(assembly.get("gear_relations", []), MAX_JOINTS)
    incoming = {}
    for row in relations.values():
        _keys(row, {"id", "name", "driver_joint", "driven_joint", "ratio", "offset_rad"})
        for key in ("id", "driver_joint", "driven_joint"):
            _identifier(row[key])
        _text(row["name"])
        _require(
            all(
                key in joints and joints[key]["kind"] == "revolute"
                for key in (row["driver_joint"], row["driven_joint"])
            ),
            "Gear relations require two existing revolute joints",
        )
        _require(row["driver_joint"] != row["driven_joint"], "A gear cannot drive itself")
        _require(row["driven_joint"] not in incoming, "Multiple gear drivers are unsupported")
        _number(row["ratio"], bound=1e6)
        _require(abs(row["ratio"]) >= 1e-6, "Gear ratio magnitude must be 1e-6 through 1e6")
        _number(row["offset_rad"], bound=1e4)
        incoming[row["driven_joint"]] = row
    for joint in joints.values():
        _require(
            (joint.get("coordinate", 0.0) is None) == (joint["id"] in incoming),
            "Only gear-driven coordinates must be null",
        )
    reached, pending, ordered = set(joints) - set(incoming), list(relations.values()), []
    while pending:
        ready = [row for row in pending if row["driver_joint"] in reached]
        _require(ready, "Cyclic gear relations are unsupported")
        for row in ready:
            reached.add(row["driven_joint"])
            ordered.append(row)
            pending.remove(row)
    return ordered


def derive_coordinates(assembly, values):
    """Return complete coordinates or None for an invalid derived range/limit."""
    result = dict(values)
    joints = {joint["id"]: joint for joint in assembly["joints"]}
    for row in ordered_relations(assembly):
        value = row["ratio"] * result[row["driver_joint"]] + row["offset_rad"]
        limits = joints[row["driven_joint"]].get("limits")
        if not math.isfinite(value) or abs(value) > 1e4:
            return None
        if limits is not None and not limits[0] <= value <= limits[1]:
            return None
        result[row["driven_joint"]] = value
    return result


def saved_coordinates(assembly):
    from .assembly_coordinates import authored_coordinates

    return derive_coordinates(assembly, authored_coordinates(assembly["joints"]))


def controlling_joint(assembly, joint_id):
    incoming = {r["driven_joint"]: r["driver_joint"] for r in assembly.get("gear_relations", [])}
    visited = set()
    while joint_id in incoming:
        if joint_id in visited:
            raise ValueError("Cyclic gear relation")
        visited.add(joint_id)
        joint_id = incoming[joint_id]
    return joint_id
