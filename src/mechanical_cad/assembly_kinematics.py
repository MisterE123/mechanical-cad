"""Forward kinematics for rooted mechanical joint trees, without natives.

This is not a general mate solver. Every outcome is bound to assembly and source
revisions and the complete request. Invalid input never produces fallback poses.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .assembly_model import MAX_JOINTS, AssemblyDocument, AssemblyError, Frame, _qmul, number
from .errors import CADException

EVALUATOR_VERSION = "rooted-tree-v1"
DOF_METHOD = "rooted_tree_joint_count"


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


def _requested_value(value: Any) -> Any:
    """JSON-safe forensic value for invalid direct Python calls (never a fallback)."""
    if type(value) in (str, bool) or value is None:
        return value
    if type(value) in (int, float):
        try:
            if math.isfinite(value):
                # Huge integers cannot be accepted as coordinates or encoded as doubles.
                if type(value) is int and value.bit_length() > 425:
                    return {"invalid_type": "oversized_integer", "hex": hex(value)}
                return value
        except OverflowError:
            return {"invalid_type": "oversized_integer", "hex": hex(value)}
        return {"invalid_type": "nonfinite_number", "value": str(value)}
    # Non-scalar coordinate values are never valid. A bounded JSON encoding retains
    # their contents where possible without running arbitrary object methods.
    if type(value) in (list, tuple, dict):
        try:
            encoded = json.dumps(value, sort_keys=True, allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            encoded = None
        return {"invalid_type": type(value).__name__, "json": encoded}
    return {"invalid_type": type(value).__name__}


def _requested_snapshot(coordinates: Any) -> dict:
    if coordinates is None:
        return {}
    if not isinstance(coordinates, Mapping):
        return {"invalid_request": _requested_value(coordinates)}
    if any(type(key) is not str for key in coordinates):
        return {
            "invalid_request": {
                "invalid_type": "nonstring_coordinate_keys",
                "entries": [
                    [_requested_value(k), _requested_value(v)] for k, v in coordinates.items()
                ],
            }
        }
    return {key: _requested_value(value) for key, value in coordinates.items()}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    subject: str | None = None

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "subject": self.subject}


@dataclass(frozen=True)
class PoseResult:
    status: str
    assembly_digest: str
    source_hashes: Mapping[str, str]
    pose_digest: str
    transforms: Mapping[str, Frame]
    requested_coordinates: Mapping[str, Any]
    effective_coordinates: Mapping[str, float]
    structural_dof: int | None
    dof_method: str
    diagnostics: tuple[Diagnostic, ...]
    evaluator_version: str = EVALUATOR_VERSION

    def __post_init__(self) -> None:
        for field in (
            "source_hashes",
            "transforms",
            "requested_coordinates",
            "effective_coordinates",
        ):
            object.__setattr__(self, field, _freeze(dict(getattr(self, field))))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def coordinates(self) -> Mapping[str, float]:
        """Compatibility alias: only complete, validated effective values are current."""
        return self.effective_coordinates

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "assembly_digest": self.assembly_digest,
            "source_hashes": dict(self.source_hashes),
            "pose_digest": self.pose_digest,
            "transforms": {key: frame.to_dict() for key, frame in self.transforms.items()},
            "requested_coordinates": _thaw(self.requested_coordinates),
            "effective_coordinates": dict(self.effective_coordinates),
            "structural_dof": self.structural_dof,
            "dof_method": self.dof_method,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "evaluator_version": self.evaluator_version,
        }


def effective_coordinate_map(
    assembly: AssemblyDocument, overrides: Mapping[str, float] | None = None
) -> dict[str, float]:
    """Return ALL joint values (including fixed zeroes), or raise; never clamp.

    Sampling must resolve its complete base map once and vary one entry in a copy.
    A rejected request has no effective map, so cannot imply a saved-value fallback.
    """
    if type(assembly) is not AssemblyDocument:
        raise AssemblyError("invalid_assembly", "Expected an AssemblyDocument")
    assembly.validate()
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, Mapping) or len(overrides) > MAX_JOINTS * 4:
        raise AssemblyError("invalid_coordinates", "Coordinates require a bounded joint-value map")
    if any(type(key) is not str for key in overrides):
        raise AssemblyError("invalid_coordinates", "Coordinate keys must be joint IDs")
    keys = {key for j in assembly.joints for key in j.coordinate_specs()}
    unknown = set(overrides) - keys
    if unknown:
        raise AssemblyError(
            "unknown_coordinate", f"Coordinate targets unknown joints {sorted(unknown)}"
        )
    driven = {relation.driven_joint for relation in assembly.gear_relations}
    if set(overrides) & driven:
        raise AssemblyError(
            "controlled_coordinate", "Gear-driven coordinates cannot be overridden; edit the driver"
        )
    values = {}
    for joint in assembly.joints:
        if joint.id in driven:
            continue
        for key, (saved, limits, bound) in joint.coordinate_specs().items():
            value = number(overrides.get(key, saved), "Joint coordinate", bound)
            if key == joint.id and joint.kind in {"fixed", "planar", "spherical"} and value != 0:
                raise AssemblyError(
                    "invalid_coordinate", f"Joint {joint.id} has no scalar coordinate"
                )
            if limits is not None and not limits[0] <= value <= limits[1]:
                raise AssemblyError(
                    "limit_violation",
                    f"Joint {joint.id}: {value} outside {limits}"
                    if key == joint.id
                    else f"Joint coordinate {key} outside limits",
                )
            values[key] = value
    values.update(assembly.gear_coordinates(values))
    return values


def _instance_placement(parent: Frame, a: Frame, motion: Frame, b: Frame) -> Frame:
    """Compose in temporary arithmetic, bounding only the completed placement.

    Individually legal mate frames may temporarily leave the world-coordinate
    domain before the child's local frame cancels that offset. Constructing a
    bounded Frame at each multiplication would reject valid final placements.
    """
    translation, rotation = parent.xyz_mm, parent._rotation()
    for local in (a, motion):
        offset = Frame(wxyz=rotation).rotate(local.xyz_mm)
        translation = tuple(x + y for x, y in zip(translation, offset, strict=True))
        rotation = _qmul(rotation, local._rotation())
    bw, bx, by, bz = b._rotation()
    rotation = _qmul(rotation, (bw, -bx, -by, -bz))
    offset = Frame(wxyz=rotation).rotate(b.xyz_mm)
    translation = tuple(x - y for x, y in zip(translation, offset, strict=True))
    return Frame(translation, rotation)


def evaluate(
    assembly: AssemblyDocument,
    coordinates: Mapping[str, float] | None = None,
    *,
    resolved_frames: Mapping[tuple[str, str], Frame] | None = None,
) -> PoseResult:
    """A failed input/range check yields no current transforms or effective map."""
    if type(assembly) is not AssemblyDocument:
        raise AssemblyError("invalid_assembly", "Expected an AssemblyDocument")
    requested = _requested_snapshot(coordinates)
    assembly_digest = assembly.content_hash
    source_hashes = dict(assembly.source_hashes)
    effective, transforms, diagnostics = {}, {}, ()
    dof = sum(joint.structural_dof for joint in assembly.joints) - len(assembly.gear_relations)
    try:
        effective = effective_coordinate_map(assembly, coordinates)
        parts = {part.id: part for part in assembly.parts}
        instances = {instance.id: instance for instance in assembly.instances}
        transforms[assembly.grounded_instance] = assembly.ground

        def frame(part_id, frame_id):
            if resolved_frames is not None and (part_id, frame_id) in resolved_frames:
                return resolved_frames[(part_id, frame_id)]
            return parts[part_id].frame(frame_id)

        for joint in assembly.ordered_joints():
            a = frame(instances[joint.parent].part_id, joint.parent_frame)
            b = frame(instances[joint.child].part_id, joint.child_frame)
            transforms[joint.child] = _instance_placement(
                transforms[joint.parent],
                a,
                joint.motion(
                    effective[joint.id], effective.get(joint.rotation_key), coordinates=effective
                ),
                b,
            )
        status = "evaluated"
    except CADException as exc:
        status, transforms = "blocked", {}
        diagnostics = (Diagnostic(exc.code, str(exc)),)
    fingerprint = {
        "assembly_digest": assembly_digest,
        "source_hashes": source_hashes,
        "requested_coordinates": requested,
        "effective_coordinates": effective,
        "evaluator_version": EVALUATOR_VERSION,
        "status": status,
        "diagnostics": [d.to_dict() for d in diagnostics],
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return PoseResult(
        status,
        assembly_digest,
        source_hashes,
        digest,
        transforms,
        requested,
        effective,
        dof,
        "rooted_tree_independent_coordinate_count" if assembly.gear_relations else DOF_METHOD,
        diagnostics,
    )
