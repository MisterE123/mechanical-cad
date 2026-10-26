"""Detached support-policy authoring; no Blender or native kernel authority.

Callers provide freshly validated upstream evidence and publish candidates through
existing canonical replay. This module never chooses a replacement face itself.
"""

import copy

from .cut_support_ancestry import replay_rows, resolve_replay_support
from .support_intent import (
    capture_orientation,
    reset_frame_intent,
    resolve_support_signature,
    validate_intent,
)

POLICY_ITEMS = (
    (
        "PRESERVE_PLANE",
        "Preserve logical plane",
        "Default: keep the original in-plane anchor only across proven coplanar Cut descendants",
    ),
    (
        "STRICT",
        "Strict exact face",
        "Stop when the selected face no longer has one stable identity; never assume a plane",
    ),
)

ORIENTATION_ITEMS = (
    (
        "MINIMAL_TWIST",
        "Minimal twist",
        "Keep the saved in-plane direction by the shortest rotation of the source normal; not material spin",
    ),
    (
        "WORLD_AXES",
        "World axes",
        "Legacy projected-world-axis frame; may turn abruptly when its reference axis changes",
    ),
)


def orientation_choice(intent):
    """Read the saved choice without upgrading a legacy preserve-plane intent."""
    return "MINIMAL_TWIST" if intent is None or "orientation" in intent else "WORLD_AXES"


def attached_feature(document, feature_id):
    feature = next((f for f in document["features"] if f["id"] == feature_id), None)
    if feature is None or feature["kind"] != "sketch_constrained" or "support_face" not in feature:
        raise ValueError("Choose a saved face-attached constrained sketch.")
    return feature


def support_topology(result, source_id):
    source = next((f for f in (result or {}).get("features", ()) if f["id"] == source_id), None)
    if (
        source is None
        or source["status"] != "ok"
        or source.get("output", {}).get("kind") != "solid"
    ):
        raise ValueError("The supporting solid needs a current successful replay.")
    return source["topology"]


def construction_source(result, source_id, face_id):
    """Find an explicit stable baseline on the consecutive Cut base path only."""
    rows = replay_rows(result["features"])
    current, seen = rows.get(source_id), set()
    while current is not None and current["id"] not in seen:
        seen.add(current["id"])
        exact = [face for face in current.get("topology", []) if face["id"] == face_id]
        stable = len(exact) == 1 and exact[0]["provenance"].get("semantic_status") == "stable"
        if stable and (
            current["kind"] != "cut"
            or exact[0]["provenance"].get("relation") not in {"modified", "unchanged"}
        ):
            return current["id"], exact[0]["signature"]
        if current["kind"] != "cut":
            break
        current = rows.get(current.get("inputs", {}).get("base"))
    raise ValueError("No original stable source plane is available along the Cut base chain.")


def capture_support_intent(result, source_id, face_id):
    """Capture a selected exact face plus its explicit authored baseline feature."""
    signature, _ = resolve_support_signature(face_id, None, support_topology(result, source_id))
    baseline_id, baseline = construction_source(result, source_id, face_id)
    intent = {
        "version": 1,
        "policy": "preserve_plane",
        "signature": copy.deepcopy(signature),
        "source_signature": copy.deepcopy(baseline),
        "source_feature": baseline_id,
    }
    intent["orientation"] = capture_orientation(intent)
    validate_intent(intent)
    resolve_replay_support(face_id, intent, source_id, result["features"])
    return intent


def support_decision(feature, result):
    support_topology(result, feature["inputs"]["support"])
    return resolve_replay_support(
        feature["support_face"],
        feature.get("support_intent"),
        feature["inputs"]["support"],
        result["features"],
    )[1]


def eligible_support_ids(document, feature_id):
    """Exclude self and all dependants; no new dependency cycle can be offered."""
    excluded = {feature_id}
    while True:
        found = {
            f["id"]
            for f in document["features"]
            if any(source in excluded for source in f["inputs"].values())
        }
        if found <= excluded:
            break
        excluded.update(found)
    return {f["id"] for f in document["features"] if f["id"] not in excluded}


def edit_support_candidate(
    document, feature_id, policy, source_id, face_id, result, orientation=None, reset_frame=False
):
    """Make an explicit, reversible candidate; preserve local sketch coordinates."""
    original = attached_feature(document, feature_id)
    if policy not in {item[0] for item in POLICY_ITEMS}:
        raise ValueError("Choose Strict exact face or Preserve logical plane.")
    if orientation is not None and orientation not in {item[0] for item in ORIENTATION_ITEMS}:
        raise ValueError("Choose Minimal twist or World axes for the support orientation.")
    if type(reset_frame) is not bool:
        raise ValueError("Choose whether to reset the saved frame here.")
    if source_id not in eligible_support_ids(document, feature_id):
        raise ValueError("Support cannot be this sketch or a feature that depends on it.")
    same_support = (
        source_id == original["inputs"]["support"] and face_id == original["support_face"]
    )
    candidate = copy.deepcopy(document)
    feature = attached_feature(candidate, feature_id)
    feature["inputs"]["support"] = source_id
    feature["support_face"] = face_id
    if policy == "STRICT":
        feature.pop("support_intent", None)
    elif same_support and original.get("support_intent") is not None:
        # Reopening or accepting the dialog must not silently move the saved anchor.
        validate_intent(original["support_intent"])
    else:
        try:
            feature["support_intent"] = capture_support_intent(result, source_id, face_id)
        except ValueError:
            if not same_support or any(
                face["id"] == face_id and face["provenance"].get("semantic_status") == "stable"
                for face in support_topology(result, source_id)
            ):
                # A failed proof for an exact selected face must never fall
                # back to weaker legacy intent (for example for an aliased tool).
                raise
            # Explicit legacy repair only: no historical anchor exists. Adopt
            # the current original Cut source, then prove the entire split rule.
            # New authoring never takes this branch and saved anchors never move.
            support = next(row for row in result["features"] if row["id"] == source_id)
            if support.get("kind") != "cut":
                raise ValueError("No original Cut source plane is available.") from None
            try:
                baseline, _ = resolve_support_signature(
                    face_id, None, support_topology(result, support["inputs"]["base"])
                )
                # Legacy explicit single-stage repair deliberately adopts the
                # immediate source, not an earlier Cut's distinct saved anchor.
                binding = {"source_feature": support["inputs"]["base"]}
            except ValueError:
                baseline_id, baseline = construction_source(result, source_id, face_id)
                binding = {"source_feature": baseline_id}
            feature["support_intent"] = {
                "version": 1,
                "policy": "preserve_plane",
                "signature": copy.deepcopy(baseline),
                "source_signature": copy.deepcopy(baseline),
                **binding,
            }
            feature["support_intent"]["orientation"] = capture_orientation(
                feature["support_intent"]
            )
    if policy == "PRESERVE_PLANE":
        intent = feature["support_intent"]
        if orientation == "WORLD_AXES":
            intent.pop("orientation", None)
        elif orientation == "MINIMAL_TWIST" and "orientation" not in intent:
            intent["orientation"] = capture_orientation(intent)
        if reset_frame:
            if "orientation" not in intent:
                raise ValueError("Choose Minimal twist before resetting the saved frame here.")
            if "source_feature" in intent:
                legacy = {key: value for key, value in intent.items() if key != "orientation"}
                anchor, _ = resolve_replay_support(face_id, legacy, source_id, result["features"])
                baseline_id = intent["source_feature"]
                baseline, _ = resolve_support_signature(
                    face_id, None, support_topology(result, baseline_id)
                )
                reset = {
                    "version": 1,
                    "policy": "preserve_plane",
                    "signature": copy.deepcopy(anchor),
                    "source_signature": copy.deepcopy(baseline),
                    "source_feature": baseline_id,
                }
                reset["orientation"] = capture_orientation(reset)
                feature["support_intent"] = reset
            else:
                rows = {row["id"]: row for row in result["features"]}
                support = rows.get(source_id, {})
                base = rows.get(support.get("inputs", {}).get("base"), {})
                feature["support_intent"] = reset_frame_intent(
                    face_id, intent, support_topology(result, source_id), base.get("topology")
                )
    # Authoring new support needs an exact selected face. Existing preserve intent
    # may retain its logical plane, but cannot invent unsupported alternatives.
    support_decision(feature, result)
    return candidate
