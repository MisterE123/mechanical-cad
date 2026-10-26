"""Explicit Up to Face reference replacement from fresh, guarded replay data.

The catalog is a convenience, not a geometry receipt or a face-identity guess.
Only authored target/face intent is changed; full native replay still decides.
"""

import copy
import math

from .assembly_frame_evidence import _rotate
from .solid_feature_edit import SOLID_KINDS


def terminated_feature(document, feature_id):
    matches = [f for f in document["features"] if f["id"] == feature_id]
    if len(matches) != 1 or matches[0].get("kind") != "extrude_to_face":
        raise ValueError("Choose an existing Up to Face extrusion.")
    return matches[0]


def eligible_target_ids(document, feature_id):
    """Earlier solids only, excluding self and dependants even in reordered DAGs."""
    terminated_feature(document, feature_id)
    excluded = {feature_id}
    while True:
        found = {
            f["id"]
            for f in document["features"]
            if any(source in excluded for source in f.get("inputs", {}).values())
        }
        if found <= excluded:
            break
        excluded.update(found)
    allowed = set()
    for feature in document["features"]:
        if feature["id"] == feature_id:
            break
        if feature["kind"] in SOLID_KINDS and feature["id"] not in excluded:
            allowed.add(feature["id"])
    return allowed


def _profile_plane(document, feature, rows):
    source = next(f for f in document["features"] if f["id"] == feature["inputs"]["profile"])
    profile = rows.get(source["id"], {})
    output = profile.get("output") or {}
    if profile.get("status") != "ok" or not (
        output.get("kind") == "profile"
        or output.get("kind") == "sketch"
        and output.get("profile", {}).get("state") == "available"
    ):
        raise ValueError("The original profile needs a successful closed-profile replay.")
    if source["kind"] == "sketch_constrained":
        # This solved world plane already includes current support intent. A
        # profile's outward face orientation is not its authored travel normal.
        plane = profile["sketch"]["solved"]["plane"]
        return plane["origin"], _rotate(plane["quaternion"], [0, 0, 1])
    if source["kind"] in {"sketch_rectangle", "sketch_circle"}:
        return [0, 0, profile["resolved_params"].get("z", 0)], [0, 0, 1]
    if source["kind"] in {"sketch_face_rectangle", "sketch_face_circle"}:
        faces = profile.get("topology", [])
        if len(faces) == 1 and faces[0]["signature"]["surface"] == "plane":
            signature = faces[0]["signature"]
            return signature["centroid"], signature["normal"]
    raise ValueError("This profile has no supported current planar construction frame.")


def end_face_candidates(document, feature_id, result):
    """Offer exact stable parallel planes with valid saved direction/offset reach.

    Result must be projected from the current guarded full replay by the caller.
    No saved signature, centroid distance ranking or old display is consulted.
    """
    feature = terminated_feature(document, feature_id)
    rows = {row["id"]: row for row in result["features"]}
    origin, normal = _profile_plane(document, feature, rows)
    params = rows.get(feature_id, {}).get("resolved_params", {})
    direction, offset = params.get("direction"), params.get("offset", 0)
    if (
        type(direction) not in (int, float)
        or direction not in (-1, 1)
        or type(offset) not in (int, float)
        or not math.isfinite(offset)
    ):
        raise ValueError(
            "The saved direction and offset need a current successful parameter evaluation."
        )
    allowed = eligible_target_ids(document, feature_id)
    candidates = []
    for source in document["features"]:
        row = rows.get(source["id"], {})
        if (
            source["id"] not in allowed
            or row.get("status") != "ok"
            or (row.get("output") or {}).get("kind") != "solid"
        ):
            continue
        topology = row.get("topology", [])
        counts = {}
        for face in topology:
            counts[face["id"]] = counts.get(face["id"], 0) + 1
        for face in topology:
            signature = face["signature"]
            if (
                counts[face["id"]] != 1
                or face.get("provenance", {}).get("semantic_status") != "stable"
                or signature["surface"] != "plane"
            ):
                continue
            target_normal = signature["normal"]
            cross = (
                normal[1] * target_normal[2] - normal[2] * target_normal[1],
                normal[2] * target_normal[0] - normal[0] * target_normal[2],
                normal[0] * target_normal[1] - normal[1] * target_normal[0],
            )
            reach = direction * sum(
                (signature["centroid"][i] - origin[i]) * normal[i] for i in range(3)
            )
            length = reach + offset
            if math.hypot(*cross) <= 1e-9 and reach >= 1e-6 and 1e-6 <= length <= 1e6:
                candidates.append(
                    {
                        "target": source["id"],
                        "face": face["id"],
                        "role": face["role"],
                        "reach": reach,
                        "length": length,
                    }
                )
    return candidates


def replace_end_face(document, feature_id, target, face, result):
    if not any(
        row["target"] == target and row["face"] == face
        for row in end_face_candidates(document, feature_id, result)
    ):
        raise ValueError(
            "Select an earlier solid and a current stable parallel face ahead in the saved direction with a valid offset."
        )
    candidate = copy.deepcopy(document)
    feature = terminated_feature(candidate, feature_id)
    feature["inputs"]["target"] = target
    feature["end_face"] = face
    return candidate
