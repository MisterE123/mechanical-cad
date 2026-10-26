"""Pure, bounded assembly-check policy and evidence aggregation.

A known collision remains visible even when a different query is incomplete.
Fingerprints bind the exact request, including rejected coordinates and samples.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations

from .assembly_model import AssemblyDocument, AssemblyError

POLICY_VERSION = "assembly-exact-pose-v1"
MAX_SAMPLES = 32
MAX_PAIR_QUERIES = 4096


@dataclass(frozen=True)
class CheckPolicy:
    linear_tolerance_mm: float = 1e-6
    volume_tolerance_mm3: float = 1e-9
    linear_deflection_mm: float = 0.1

    def __post_init__(self):
        for name, lower, upper in (
            ("linear_tolerance_mm", 1e-9, 1),
            ("volume_tolerance_mm3", 1e-15, 1),
            ("linear_deflection_mm", 0.001, 10),
        ):
            value = getattr(self, name)
            if type(value) not in (int, float) or not lower <= value <= upper:
                raise AssemblyError("invalid_tolerance", f"{name} must be {lower:g}–{upper:g}.")

    @classmethod
    def from_dict(cls, value):
        fields = {"linear_tolerance_mm", "volume_tolerance_mm3", "linear_deflection_mm"}
        if type(value) is not dict or set(value) - fields:
            raise AssemblyError("invalid_policy", "Unknown or malformed assembly check policy.")
        return cls(**value)

    def to_dict(self):
        return {
            "linear_tolerance_mm": self.linear_tolerance_mm,
            "volume_tolerance_mm3": self.volume_tolerance_mm3,
            "linear_deflection_mm": self.linear_deflection_mm,
        }


def clearance_requirements(assembly: AssemblyDocument, values=None) -> dict:
    """Strict explicit pair requirements; missing pairs default to zero clearance."""
    if values is None:
        values = []
    possible = set(combinations(sorted(i.id for i in assembly.instances), 2))
    if type(values) is not list or len(values) > len(possible):
        raise AssemblyError("invalid_requirements", "Provide a bounded list of pair clearances.")
    result = {}
    for row in values:
        if type(row) is not dict or set(row) != {"instances", "minimum_mm"}:
            raise AssemblyError("invalid_requirements", "Each pair needs instances and minimum_mm.")
        pair, minimum = row["instances"], row["minimum_mm"]
        if type(pair) is not list or len(pair) != 2 or any(type(i) is not str for i in pair):
            raise AssemblyError("invalid_clearance_pair", "Choose exactly two instance IDs.")
        pair = tuple(sorted(pair))
        if pair not in possible or pair in result:
            raise AssemblyError("invalid_clearance_pair", "Unknown or duplicate instance pair.")
        if type(minimum) not in (int, float) or not 0 <= minimum <= 1e6:
            raise AssemblyError("invalid_clearance", "Minimum clearance must be 0–1e6 mm.")
        result[pair] = minimum
    return result


def sample_request(assembly: AssemblyDocument, value, coordinates):
    """Require a complete base pose, never silently reset another joint override."""
    if type(value) is not dict or set(value) != {"joint_id", "values"}:
        raise AssemblyError("invalid_samples", "Sampling needs joint_id and explicit values.")
    joints = {key: joint for joint in assembly.joints for key in joint.coordinate_specs()}
    joint_id, values = value["joint_id"], value["values"]
    if (
        type(joint_id) is not str
        or joint_id not in joints
        or joint_id in {r.driven_joint for r in assembly.gear_relations}
        or (
            joint_id == joints[joint_id].id
            and joints[joint_id].kind in {"fixed", "planar", "spherical"}
        )
    ):
        raise AssemblyError("invalid_motion_joint", "Select an existing movable joint.")
    keys = set(joints) - {r.driven_joint for r in assembly.gear_relations}
    if type(coordinates) is not dict or set(coordinates) != keys:
        raise AssemblyError(
            "incomplete_base_pose",
            "Sampling requires every independent joint coordinate (not gear-driven values).",
        )
    if type(values) is not list or not 1 <= len(values) <= MAX_SAMPLES:
        raise AssemblyError("invalid_samples", f"Provide 1–{MAX_SAMPLES} explicit sample values.")
    bound = joints[joint_id].coordinate_specs()[joint_id][2]
    if any(type(v) not in (int, float) or not -bound <= v <= bound for v in values):
        raise AssemblyError("invalid_samples", "Sample coordinates must be finite and bounded.")
    queries = len(assembly.instances) * (len(assembly.instances) - 1) // 2 * len(values)
    if queries > MAX_PAIR_QUERIES:
        raise AssemblyError("query_budget", "Sample request exceeds the exact pair-query budget.")
    return joint_id, tuple(values)


def aggregate_evidence(rows, *, complete=True):
    """Completeness and known violations are independent, including for motion."""
    rows = tuple(rows)
    complete = bool(complete and all(row.get("complete") is True for row in rows))
    interference = any(row.get("known_interference") is True for row in rows)
    clearance = any(row.get("known_clearance_violation") is True for row in rows)
    threshold = any(
        row.get("has_threshold_contacts") is True or row.get("clearance_verdict") == "at_threshold"
        for row in rows
    )
    if interference or clearance:
        status = "violations_found"
    elif not complete:
        status = "indeterminate"
    elif threshold:
        status = "checked_with_threshold_contacts"
    else:
        status = "no_violations_at_listed_poses"
    return {
        "status": status,
        "complete": complete,
        "known_interference": interference,
        "known_clearance_violation": clearance,
        "has_threshold_contacts": threshold,
        "passed": complete and not (interference or clearance or threshold),
    }


def request_snapshot(value, _depth=0, _seen=None, _path="$", _budget=None):
    """Bounded forensic JSON for invalid direct calls, without type collisions.

    Valid request containers are copied by value. Repeated container references
    are explicit, so a small cyclic/shared Python graph cannot expand exponentially.
    JSON wire input cannot express such references. Unsupported tuples retain a
    type tag rather than colliding with accepted JSON lists.
    """
    if _seen is None:
        _seen = {}
    if _budget is None:
        _budget = [200000]
    _budget[0] -= 1
    if _budget[0] < 0 or _depth > 20:
        raise AssemblyError("resource_limit", "Assembly request snapshot exceeds its bounds.")
    if value is None or type(value) in (str, bool):
        return value
    if type(value) in (int, float):
        if type(value) is int and value.bit_length() > 425:
            return {"invalid_integer_hex": hex(value)}
        try:
            if math.isfinite(value):
                return value
        except OverflowError:
            pass
        return {"invalid_numeric_value": str(value)}
    container = type(value) in (list, tuple) or isinstance(value, Mapping)
    if container:
        identity = id(value)
        if identity in _seen:
            return {"python_container_reference": _seen[identity]}
        _seen[identity] = _path
    if type(value) in (list, tuple):
        items = [
            request_snapshot(item, _depth + 1, _seen, f"{_path}[{index}]", _budget)
            for index, item in enumerate(value)
        ]
        return items if type(value) is list else {"invalid_type": "tuple", "items": items}
    if isinstance(value, Mapping):
        if all(type(key) is str for key in value):
            return {
                key: request_snapshot(item, _depth + 1, _seen, f"{_path}.{key}", _budget)
                for key, item in value.items()
            }
        return {
            "invalid_type": "nonstring_mapping_keys",
            "entries": [
                [
                    request_snapshot(key, _depth + 1, _seen, f"{_path}.key{index}", _budget),
                    request_snapshot(item, _depth + 1, _seen, f"{_path}.value{index}", _budget),
                ]
                for index, (key, item) in enumerate(value.items())
            ],
        }
    return {"invalid_type": type(value).__name__}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def typed_request_fingerprint(value):
    """Unforgeable type-tagged identity alongside human-readable invalid inputs.

    Literal dictionaries are always encoded as mapping nodes, so they cannot
    impersonate the explanatory sentinels produced by request_snapshot.
    """
    seen, budget = {}, [200000]

    def node(item, path, depth):
        budget[0] -= 1
        if budget[0] < 0 or depth > 20:
            raise AssemblyError("resource_limit", "Assembly request identity exceeds its bounds.")
        if item is None:
            return ["null"]
        if type(item) is bool:
            return ["bool", item]
        if type(item) is str:
            return ["str", item]
        if type(item) is int:
            return ["int", hex(item)]
        if type(item) is float:
            return ["float", item.hex()]
        if isinstance(item, Mapping) or type(item) in (list, tuple):
            if id(item) in seen:
                return ["reference", seen[id(item)]]
            seen[id(item)] = path
            if isinstance(item, Mapping):
                # Accepted mappings have string keys; preserve invalid keys as
                # typed entries rather than silently converting them to strings.
                entries = list(item.items())
                if all(type(key) is str for key, _ in entries):
                    entries.sort(key=lambda row: row[0])
                return [
                    "mapping",
                    [
                        [
                            node(key, f"{path}.key{index}", depth + 1),
                            node(child, f"{path}.value{index}", depth + 1),
                        ]
                        for index, (key, child) in enumerate(entries)
                    ],
                ]
            return [
                type(item).__name__,
                [node(child, f"{path}[{index}]", depth + 1) for index, child in enumerate(item)],
            ]
        raise AssemblyError(
            "invalid_request", "Request values must be JSON-like scalar/container data."
        )

    return fingerprint(node(value, "$", 0))


def intended_contact_acceptance(report, instance_ids):
    """Separate authored acceptance, never a clearance/physical-contact proof.

    None preserves legacy report serialization. The selected canonical preset is
    the only source of intent; the native measurements are never relabeled.
    """
    basis = report.get("verification_basis") or {}
    preset = basis.get("preset") or {}
    intended = {
        tuple(r["instances"])
        for r in preset.get("requirements", ())
        if r.get("contact_policy") == "accept_tolerance_band" and r["minimum_mm"] == 0
    }
    if not intended:
        return None
    if (
        basis.get("configured") is not True
        or basis.get("preset_id") != preset.get("id")
        or report.get("complete") is not True
        or report.get("known_interference") is not False
        or report.get("known_clearance_violation") is not False
        or not report.get("poses")
    ):
        return False
    expected_pairs = set(combinations(sorted(instance_ids), 2))
    requirements = {tuple(r["instances"]): r["minimum_mm"] for r in preset["requirements"]}
    policy = report.get("effective_policy") or {}
    linear = policy.get("linear_tolerance_mm")
    if type(linear) not in (int, float) or not math.isfinite(linear) or linear <= 0:
        return False
    for pose in report["poses"]:
        if pose.get("complete") is not True or pose.get("diagnostics") != []:
            return False
        found = set()
        for row in pose.get("pairs", ()):
            pair = tuple(row.get("instances", ()))
            volume, distance = row.get("common_volume_mm3"), row.get("minimum_distance_mm")
            minimum = row.get("minimum_required_mm")
            if (
                pair in found
                or pair not in expected_pairs
                or minimum != requirements.get(pair, 0.0)
                or row.get("complete") is not True
                or row.get("known_interference") is not False
                or row.get("known_clearance_violation") is not False
                or row.get("diagnostics") != []
                or type(volume) not in (int, float)
                or volume != 0
                or type(distance) not in (int, float)
                or not math.isfinite(distance)
                or distance < 0
                or type(minimum) not in (int, float)
                or not math.isfinite(minimum)
                or minimum < 0
            ):
                return False
            witnesses = row.get("witness_points_mm")
            try:
                if (
                    type(witnesses) is not list
                    or len(witnesses) != 2
                    or any(type(p) is not list or len(p) != 3 for p in witnesses)
                    or any(
                        type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e8
                        for p in witnesses
                        for v in p
                    )
                    or abs(math.dist(*witnesses) - distance) > linear + 1e-9
                ):
                    return False
            except (TypeError, ValueError, OverflowError):
                return False
            found.add(pair)
            if pair in intended:
                if not (
                    minimum == 0
                    and distance <= linear
                    and row.get("relation") == "contact_or_near"
                    and row.get("clearance_verdict") == "at_threshold"
                ):
                    return False
            elif not (
                row.get("relation") == "separated"
                and row.get("clearance_verdict") == "pass_at_pose"
                and distance > minimum + linear
            ):
                return False
        if found != expected_pairs or not intended <= found:
            return False
    return True
