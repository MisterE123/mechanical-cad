"""Versioned, inspectable logical-plane intent; never grants a face identity.

This native-free rule is mirrored in Blender for independent result validation.
Split preservation requires complete Cut ancestry with an explicit stable source.
Exact planar supports can also carry an explicit baseline-relative orientation.
No proximity score, face index, largest-fragment guess or probability is used.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping


def validate_intent(intent):
    required = {"version", "policy", "signature"}
    if (
        not isinstance(intent, Mapping)
        or not required <= set(intent)
        or set(intent) - required - {"source_signature", "orientation", "source_feature"}
    ):
        raise ValueError("Support intent requires version, policy and saved signature.")
    if type(intent["version"]) is not int or intent["version"] != 1:
        raise ValueError("Unsupported support intent version.")
    if intent["policy"] != "preserve_plane":
        raise ValueError("Unsupported support intent policy.")
    if "source_feature" in intent:
        if (
            not isinstance(intent["source_feature"], str)
            or re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", intent["source_feature"]) is None
            or "source_signature" not in intent
        ):
            raise ValueError(
                "Source-bound support requires an authored feature ID and source signature."
            )
    _validate_signature(intent["signature"])
    if "source_signature" in intent:
        _validate_signature(intent["source_signature"])
    if "orientation" in intent:
        orientation = intent["orientation"]
        if (
            not isinstance(orientation, Mapping)
            or set(orientation) != {"policy", "tangent"}
            or orientation["policy"] != "minimal_twist"
        ):
            raise ValueError("Unsupported support orientation intent.")
        _validate_tangent(
            orientation["tangent"], intent.get("source_signature", intent["signature"])["normal"]
        )


def _validate_tangent(tangent, normal):
    if (
        not isinstance(tangent, (list, tuple))
        or len(tangent) != 3
        or any(
            type(v) not in (int, float) or abs(v) > 1.0000001 or not math.isfinite(v)
            for v in tangent
        )
        or not math.isclose(math.hypot(*tangent), 1, abs_tol=1e-7)
        or abs(math.fsum(tangent[i] * normal[i] for i in range(3))) > 1e-7
    ):
        raise ValueError(
            "Saved support tangent must be finite, unit and perpendicular to its baseline normal."
        )


def _validate_signature(signature):
    if not isinstance(signature, Mapping) or set(signature) != {
        "surface",
        "area",
        "centroid",
        "normal",
    }:
        raise ValueError("Support intent requires an original planar face signature.")
    if signature["surface"] != "plane":
        raise ValueError("Only planar support intent is supported.")

    def number(value, bound):
        return type(value) in (int, float) and abs(value) <= bound and math.isfinite(value)

    if not number(signature["area"], 1e100) or signature["area"] <= 0:
        raise ValueError("Saved support area must be positive and finite.")
    for name, bound in (("centroid", 1e12), ("normal", 1.0000001)):
        vector = signature[name]
        if (
            not isinstance(vector, (list, tuple))
            or len(vector) != 3
            or not all(number(v, bound) for v in vector)
        ):
            raise ValueError("Invalid saved support " + name + ".")
    if not math.isclose(sum(v * v for v in signature["normal"]), 1, abs_tol=1e-7):
        raise ValueError("Saved support normal must be unit length.")


def _basis(signature):
    """Same deterministic projected-world-axis convention as face_frame/resolve_plane."""
    n = signature["normal"]
    reference = (0, 1, 0) if abs(n[0]) > 0.9 else (1, 0, 0)
    dot = math.fsum(reference[i] * n[i] for i in range(3))
    u = [reference[i] - dot * n[i] for i in range(3)]
    length = math.hypot(*u)
    u = [value / length for value in u]
    v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    return u, v, n


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def frame_basis(signature):
    """Resolve a logical frame only; optional tangent never enters native topology."""
    if "tangent" not in signature:
        return _basis(signature)
    n = signature["normal"]
    _validate_tangent(signature["tangent"], n)
    u = list(signature["tangent"])
    return u, _cross(n, u), n


def capture_orientation(intent):
    """Explicit new authoring baseline, never implicitly upgrades a saved record."""
    baseline = intent.get("source_signature", intent["signature"])
    _validate_signature(baseline)
    return {"policy": "minimal_twist", "tangent": list(_basis(baseline)[0])}


def _minimal_tangent(tangent, old_normal, current_normal):
    # Shortest normal-to-normal rotation, evaluated from the saved baseline on
    # every replay. No cumulative history/path dependence or inferred material spin.
    old_n = [v / math.hypot(*old_normal) for v in old_normal]
    new_n = [v / math.hypot(*current_normal) for v in current_normal]
    cosine = max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(old_n, new_n, strict=True))))
    if 1 + cosine <= 1e-8:
        raise ValueError(
            "Source normal is antiparallel or nearly antiparallel to the saved frame. Minimal twist has no reliable unique axis; choose World axes or Reset saved frame here."
        )
    axis = _cross(old_n, new_n)
    once = _cross(axis, tangent)
    twice = _cross(axis, once)
    transported = [tangent[i] + once[i] + twice[i] / (1 + cosine) for i in range(3)]
    residual = math.fsum(transported[i] * new_n[i] for i in range(3))
    transported = [transported[i] - residual * new_n[i] for i in range(3)]
    length = math.hypot(*transported)
    if not math.isfinite(length) or length < 1e-10:
        raise ValueError(
            "Transported support tangent is degenerate; reset the saved frame or choose World axes."
        )
    return [v / length for v in transported]


def _transport_signature(intent, current_source, descendants):
    saved = intent["signature"]
    baseline = intent.get("source_signature", saved)
    orientation = intent.get("orientation")
    old_u, old_v, old_n = _basis(baseline)
    if orientation:
        old_u = list(orientation["tangent"])
        old_v = _cross(old_n, old_u)
    delta = [saved["centroid"][i] - baseline["centroid"][i] for i in range(3)]
    if (
        math.dist(saved["normal"], old_n) > 1e-7
        or abs(math.fsum(delta[i] * old_n[i] for i in range(3))) > 1e-7
    ):
        raise ValueError(
            "Saved anchor and source frame are not on the same oriented plane. Choose a new supporting face."
        )
    local_u = math.fsum(delta[i] * old_u[i] for i in range(3))
    local_v = math.fsum(delta[i] * old_v[i] for i in range(3))
    new_u, new_v, normal = _basis(current_source)
    if orientation:
        new_u = _minimal_tangent(old_u, old_n, normal)
        new_v = _cross(normal, new_u)
    anchor = [
        current_source["centroid"][i] + local_u * new_u[i] + local_v * new_v[i] for i in range(3)
    ]
    for row in descendants:
        signature = row["signature"]
        if math.dist(normal, signature["normal"]) > 1e-7:
            raise ValueError(
                "Support descendants have different orientations. Choose a new supporting face or datum plane."
            )
        if (
            abs(math.fsum((signature["centroid"][i] - anchor[i]) * normal[i] for i in range(3)))
            > 1e-7
        ):
            raise ValueError(
                "Support descendants define different planes. Choose a new supporting face or datum plane."
            )
    return {
        "surface": "plane",
        "area": saved["area"],
        "normal": list(normal),
        "centroid": anchor,
        **({"tangent": new_u} if orientation else {}),
    }


def reset_frame_intent(face_id, intent, topology, source_topology=None):
    """Deliberate correction: adopt current world-axis frame, never an automatic reset."""
    validate_intent(intent)
    legacy = {key: value for key, value in intent.items() if key != "orientation"}
    anchor, decision = resolve_support_signature(face_id, legacy, topology, source_topology)
    sources = [
        row
        for row in (source_topology or [])
        if row["id"] == face_id and row["provenance"].get("semantic_status") == "stable"
    ]
    exact = [
        row
        for row in topology
        if row["id"] == face_id and row["provenance"].get("semantic_status") == "stable"
    ]
    use_base = decision["policy"] == "preserve_plane"
    baseline = (
        sources[0]["signature"]
        if use_base and len(sources) == 1
        else exact[0]["signature"]
        if len(exact) == 1
        else None
    )
    if baseline is None:
        raise ValueError("No proven current source frame is available to reset.")

    def clone(signature):
        return {
            key: list(value) if isinstance(value, (list, tuple)) else value
            for key, value in signature.items()
            if key != "tangent"
        }

    result = {
        "version": 1,
        "policy": "preserve_plane",
        "signature": clone(anchor),
        "source_signature": clone(baseline),
    }
    result["orientation"] = capture_orientation(result)
    validate_intent(result)
    return result


def resolve_support_signature(face_id, intent, topology, source_topology=None):
    """Return current support signature and an auditable decision, or ValueError.

    The returned centroid for an assumption is a logical-plane anchor, NOT a
    native face centroid. It may lie over a removed patch. This is intentional:
    sketch support is an infinite construction plane, not a material/contact test.
    """
    if intent is not None:
        validate_intent(intent)
        if "source_feature" in intent:
            raise ValueError("Source-bound support requires complete current replay ancestry.")
    exact = [row for row in topology if row["id"] == face_id]
    stable = len(exact) == 1 and exact[0]["provenance"]["semantic_status"] == "stable"
    # Identity and placement intent are separate. A single Modified Cut face can
    # move its centroid before splitting; do not abandon saved placement intent
    # merely because exact semantic identity still exists.
    follows_cut_source = (
        stable
        and intent is not None
        and exact[0]["provenance"].get("operation") == "cut"
        and exact[0]["provenance"].get("source_id") == face_id
        and exact[0]["provenance"].get("relation") in {"modified", "unchanged"}
    )
    if stable and not follows_cut_source:
        signature = exact[0]["signature"]
        if signature["surface"] != "plane":
            raise ValueError("Sketch support must be a planar face.")
        if intent is not None and "orientation" in intent:
            return _transport_signature(intent, signature, exact), {
                "status": "assumed",
                "source_face": face_id,
                "descendant_count": 1,
                "policy": "preserve_plane",
                "identity_status": "stable",
                "orientation_policy": "minimal_twist",
                "reason": "Face identity remains exact. The saved tangent follows the shortest rotation between original and current normals (minimal twist), not material spin. Change Orientation or reset the saved frame to correct this assumption.",
            }
        return signature, {
            "status": "exact",
            "reason": "Unique stable planar face.",
            "source_face": face_id,
            "descendant_count": 1,
            "policy": "exact",
        }
    if intent is None:
        raise ValueError(
            "Support face is missing or split. Choose Preserve logical plane or change the supporting face."
        )
    # Do not throw away unfavorable descendants and then select a favorable subset.
    descendants = [row for row in topology if row["provenance"].get("source_id") == face_id]
    count = len(descendants)
    if count < (1 if follows_cut_source else 2):
        raise ValueError(
            "No complete proven split ancestry. Change the supporting face; no automatic alternative is justified."
        )
    operations = set()
    for row in descendants:
        provenance = row["provenance"]
        operations.add(provenance.get("operation_id"))
        if (
            provenance.get("semantic_status") != ("stable" if follows_cut_source else "split")
            or provenance.get("operation") != "cut"
            or provenance.get("relation") not in {"modified", "unchanged"}
            or type(provenance.get("source_count")) is not int
            or provenance["source_count"] != 1
            or type(provenance.get("image_count")) is not int
            or provenance["image_count"] != count
            or row["signature"].get("surface") != "plane"
        ):
            raise ValueError(
                "Split ancestry is incomplete, generated or nonplanar. Change the supporting face."
            )
    if len(operations) != 1 or not next(iter(operations)):
        raise ValueError("Split descendants do not share one proven operation.")
    sources = [row for row in (source_topology or []) if row["id"] == face_id]
    if (
        len(sources) != 1
        or sources[0]["provenance"].get("semantic_status") != "stable"
        or sources[0]["signature"].get("surface") != "plane"
    ):
        raise ValueError(
            "The original stable source plane is unavailable. Change the supporting face."
        )
    current_source = sources[0]["signature"]
    signature = _transport_signature(intent, current_source, descendants)
    return signature, {
        "status": "assumed",
        "policy": "preserve_plane",
        "source_face": face_id,
        "descendant_count": count,
        "identity_status": "stable" if follows_cut_source else "split",
        **({"orientation_policy": "minimal_twist"} if "orientation" in intent else {}),
        "reason": (
            "Face identity remains exact; placement follows the saved original source workplane, not the Modified face centroid. The same local anchor is retained before and after a split."
            if follows_cut_source
            else "Followed the original stable source workplane, preserving the saved local anchor across proven coplanar Cut descendants; no fragment was chosen. This construction plane may span removed material."
        )
        + (
            " Orientation uses the saved tangent and shortest normal-to-normal rotation (minimal twist), not material spin; it can be changed or reset."
            if "orientation" in intent
            else ""
        ),
    }
