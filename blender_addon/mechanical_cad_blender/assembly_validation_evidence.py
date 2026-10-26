"""Pose, pair-query and aggregate evidence validation for assembly replies."""

from __future__ import annotations

import json
import math

from .assembly_coordinates import NO_SCALAR_COORDINATE, coordinate_specs, structural_dof
from .assembly_gears import derive_coordinates
from .assembly_validation_common import (
    EVALUATOR_VERSION,
    FLAGS,
    _diagnostics,
    _frame,
    _keys,
    _number,
    _require,
    _vector,
    fingerprint,
)


def _coordinate_snapshot(value):
    if value is None:
        return {}
    if type(value) is dict:
        return {key: _coordinate_value(item) for key, item in value.items()}
    return {"invalid_request": _coordinate_value(value)}


def _coordinate_value(value):
    if value is None or type(value) in (str, bool, int, float):
        return value
    return {
        "invalid_type": type(value).__name__,
        "json": json.dumps(value, sort_keys=True, allow_nan=False),
    }


def _effective(joints, requested, relations=()):
    if requested is None:
        requested = {}
    keys = {key for joint in joints.values() for key in coordinate_specs(joint)}
    if type(requested) is not dict or set(requested) - keys:
        return None
    driven = {row["driven_joint"] for row in relations}
    if set(requested) & driven:
        return None
    values = {}
    for joint in joints.values():
        if joint["id"] in driven:
            continue
        for key, (saved, limits, bound) in coordinate_specs(joint).items():
            value = requested.get(key, saved)
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > bound:
                return None
            if key == joint["id"] and joint["kind"] in NO_SCALAR_COORDINATE and value != 0:
                return None
            if limits is not None and not limits[0] <= value <= limits[1]:
                return None
            values[key] = float(value)
    return derive_coordinates(
        {"joints": list(joints.values()), "gear_relations": list(relations)}, values
    )


def _pose(pose, expected_request, result, joints, instances):
    fields = {
        "status",
        "assembly_digest",
        "source_hashes",
        "pose_digest",
        "transforms",
        "requested_coordinates",
        "effective_coordinates",
        "structural_dof",
        "dof_method",
        "diagnostics",
        "evaluator_version",
    }
    relations = result["canonical_assembly"].get("gear_relations", [])
    _keys(pose, fields)
    _require(
        pose["assembly_digest"] == result["assembly_digest"]
        and pose["source_hashes"] == result["source_hashes"],
        "pose revision mismatch",
    )
    _require(
        fingerprint(pose["requested_coordinates"])
        == fingerprint(_coordinate_snapshot(expected_request)),
        "pose silently changed requested coordinates",
    )
    _require(
        pose["evaluator_version"] == EVALUATOR_VERSION
        and pose["dof_method"]
        == ("rooted_tree_independent_coordinate_count" if relations else "rooted_tree_joint_count"),
        "unsupported pose evaluator or DoF method",
    )
    _require(
        type(pose["structural_dof"]) is int
        and pose["structural_dof"]
        == sum(structural_dof(j) for j in joints.values()) - len(relations),
        "incorrect structural DoF",
    )
    _diagnostics(pose["diagnostics"])
    _require(pose["status"] in {"evaluated", "blocked"}, "invalid pose status")
    effective = _effective(joints, expected_request, relations)
    _require(type(pose["effective_coordinates"]) is dict, "invalid effective coordinate map")
    for value in pose["effective_coordinates"].values():
        _number(value, bound=1e6)
    if pose["status"] == "evaluated":
        _require(
            effective is not None
            and pose["effective_coordinates"] == effective
            and not pose["diagnostics"],
            "invalid or incomplete effective coordinates",
        )
        _require(
            type(pose["transforms"]) is dict and set(pose["transforms"]) == set(instances),
            "missing or extra instance transform",
        )
        for transform in pose["transforms"].values():
            _frame(transform)
        from .assembly_frame_evidence import validate_associative_pose

        validate_associative_pose(pose, result, joints, instances)
    else:
        _require(
            pose["transforms"] == {} and pose["diagnostics"],
            "blocked pose publishes current transforms",
        )
        _require(
            pose["effective_coordinates"] == {}
            or effective is not None
            and pose["effective_coordinates"] == effective,
            "blocked pose published fallback coordinates",
        )
    bound = {
        key: pose[key]
        for key in (
            "assembly_digest",
            "source_hashes",
            "requested_coordinates",
            "effective_coordinates",
            "evaluator_version",
            "status",
            "diagnostics",
        )
    }
    _require(pose["pose_digest"] == fingerprint(bound), "pose fingerprint mismatch")


def _flags(row):
    _require(all(type(row.get(key)) is bool for key in FLAGS), "missing or invalid evidence flags")
    _require(
        not row["passed"]
        or row["complete"]
        and not any(
            row[k]
            for k in ("known_interference", "known_clearance_violation", "has_threshold_contacts")
        ),
        "incomplete or violated report claims pass",
    )


def _aggregate(row, children, *, complete, replay=False, blocked=False, configured=True):
    _flags(row)
    known = {
        key: any(child[key] for child in children)
        for key in ("known_interference", "known_clearance_violation")
    }
    threshold = any(
        child.get("has_threshold_contacts") is True
        or child.get("clearance_verdict") == "at_threshold"
        for child in children
    )
    expected_complete = complete and all(child["complete"] for child in children)
    _require(
        row["complete"] == expected_complete
        and all(row[k] == v for k, v in known.items())
        and row["has_threshold_contacts"] == threshold,
        "aggregate erased evidence or completeness",
    )
    status = (
        "violations_found"
        if any(known.values())
        else "indeterminate"
        if not expected_complete
        else "checked_with_threshold_contacts"
        if threshold
        else "no_violations_at_listed_poses"
    )
    if blocked:
        status = "blocked"
    elif replay and expected_complete:
        status = "replayed"
    _require(row["status"] == status, "aggregate status contradicts evidence")
    passed = expected_complete and configured and not (any(known.values()) or threshold or replay)
    _require(row["passed"] == passed, "aggregate pass contradicts evidence")


def _pair(row, pair, minimum, policy, *, configured):
    _keys(
        row,
        {
            "instances",
            "relation",
            "common_volume_mm3",
            "minimum_distance_mm",
            "minimum_required_mm",
            "clearance_verdict",
            "witness_points_mm",
            "complete",
            "known_interference",
            "known_clearance_violation",
            "diagnostics",
        },
    )
    _require(row["instances"] == list(pair), "unexpected or duplicate pair ordering")
    _number(row["minimum_required_mm"], bound=1e6, minimum=0)
    _require(row["minimum_required_mm"] == minimum, "clearance requirement changed")
    _require(
        all(
            type(row[k]) is bool
            for k in ("complete", "known_interference", "known_clearance_violation")
        ),
        "invalid pair flags",
    )
    _diagnostics(row["diagnostics"])
    volume, distance = row["common_volume_mm3"], row["minimum_distance_mm"]
    for value in (volume, distance):
        if value is not None:
            _number(value, minimum=0)
    linear, threshold = policy["linear_tolerance_mm"], policy["volume_tolerance_mm3"]
    witnesses = row["witness_points_mm"]
    if witnesses is not None:
        _require(
            type(witnesses) is list and len(witnesses) == 2 and distance is not None,
            "invalid distance witnesses",
        )
        for point in witnesses:
            _vector(point, 3, 1e8)
        _require(
            abs(math.dist(*witnesses) - distance) <= linear + 1e-9, "distance witnesses disagree"
        )
    if row["complete"]:
        _require(
            volume is not None
            and distance is not None
            and witnesses is not None
            and not row["diagnostics"],
            "complete pair lacks native evidence",
        )
    _require(
        row["relation"]
        in {
            "unknown",
            "separated",
            "contact_or_near",
            "interference",
            "indeterminate_small_overlap",
            "indeterminate_kernel_disagreement",
        },
        "unsupported pair relation",
    )
    if row["known_interference"]:
        _require(
            volume is not None and volume > threshold and row["relation"] == "interference",
            "unsubstantiated interference",
        )
    if row["complete"]:
        _require(row["known_interference"] == (volume > threshold), "interference evidence hidden")
        _require(not (0 < volume <= threshold), "small overlap misreported as complete")
        expected_relation = (
            "interference"
            if volume > threshold
            else "contact_or_near"
            if distance <= linear
            else "separated"
        )
        _require(
            row["relation"] == expected_relation, "complete pair relation contradicts measurements"
        )
    _require(
        row["known_clearance_violation"] == (distance is not None and distance + linear < minimum),
        "clearance evidence contradicted",
    )
    expected = (
        "fail_interference"
        if row["known_interference"]
        else "fail_clearance"
        if row["known_clearance_violation"]
        else "indeterminate"
        if not row["complete"]
        else "at_threshold"
        if distance <= minimum + linear
        else "pass_at_pose"
    )
    if not configured and expected == "pass_at_pose":
        expected = "measurement_only"
    _require(row["clearance_verdict"] == expected, "pair verdict contradicts evidence")


def _contact_acceptance(report):
    """Independently recompute policy acceptance after all native rows validate."""
    basis = report.get("verification_basis") or {}
    preset = basis.get("preset") or {}
    intended = {
        tuple(r["instances"])
        for r in preset.get("requirements", ())
        if r.get("contact_policy") == "accept_tolerance_band"
    }
    if not intended:
        _require("policy_accepted" not in report, "unauthored contact policy acceptance")
        return
    expected = (
        basis.get("configured") is True
        and report["complete"]
        and not report["known_interference"]
        and not report["known_clearance_violation"]
        and bool(report["poses"])
    )
    for pose in report["poses"]:
        seen = set()
        for row in pose["pairs"]:
            pair = tuple(row["instances"])
            seen.add(pair)
            expected = expected and row["complete"] and not row["diagnostics"]
            if pair in intended:
                expected = expected and (
                    row["minimum_required_mm"] == 0
                    and row["common_volume_mm3"] == 0
                    and row["minimum_distance_mm"] is not None
                    and 0
                    <= row["minimum_distance_mm"]
                    <= report["effective_policy"]["linear_tolerance_mm"]
                    and row["relation"] == "contact_or_near"
                    and row["clearance_verdict"] == "at_threshold"
                    and not row["known_interference"]
                    and not row["known_clearance_violation"]
                )
            else:
                expected = expected and row["clearance_verdict"] == "pass_at_pose"
        expected = expected and intended <= seen
    _require(
        type(report.get("policy_accepted")) is bool and report["policy_accepted"] == expected,
        "contact policy acceptance contradicts selected intent or measured evidence",
    )
