"""Detached Add/Remove Extrusion composed from existing canonical features."""

import copy

from .extrusion_end_condition import EXTRUSION_KINDS
from .solid_feature_edit import SOLID_KINDS


def extrusion_candidate(document, extrusion, boolean):
    """Keep source untouched; both editable history nodes enter one transaction."""
    candidate = copy.deepcopy(document)
    extrusion, boolean = copy.deepcopy(extrusion), copy.deepcopy(boolean)
    features = {feature["id"]: feature for feature in candidate["features"]}
    if extrusion["kind"] not in EXTRUSION_KINDS or boolean["kind"] not in {
        "union",
        "cut",
    }:
        raise ValueError("Add/Remove Extrusion requires an extrusion and a union or cut")
    ids = (extrusion["id"], boolean["id"])
    if len(set(ids)) != 2 or any(identifier in features for identifier in ids):
        raise ValueError("Feature identity collision; reopen Add/Remove Extrusion")
    profile = features.get(extrusion["inputs"].get("profile"))
    base = features.get(boolean["inputs"].get("base"))
    if profile is None or not profile["kind"].startswith("sketch_"):
        raise ValueError("Select an existing closed sketch profile")
    if base is None or base["kind"] not in SOLID_KINDS:
        raise ValueError("Select an existing base solid")
    if boolean["inputs"].get("tool") != extrusion["id"]:
        raise ValueError("Boolean tool must reference this extrusion")
    if extrusion["kind"] == "extrude_to_face":
        target = features.get(extrusion["inputs"].get("target"))
        if target is None or target["kind"] not in SOLID_KINDS:
            raise ValueError("Up to planar face requires an explicit earlier target solid")
        candidate["features"].extend((extrusion, boolean))
        candidate["active_feature"] = boolean["id"]
        return candidate
    if extrusion["kind"] == "extrude_through":
        if boolean["kind"] != "cut" or extrusion["inputs"].get("base") != base["id"]:
            raise ValueError("Through All must remove from its explicitly selected target")
        if extrusion["params"].get("direction") not in (-1, 1):
            raise ValueError("Choose Along or Opposite sketch normal for Through All")
        candidate["features"].extend((extrusion, boolean))
        candidate["active_feature"] = boolean["id"]
        return candidate
    length = extrusion["params"].get("length")
    if isinstance(length, str) and not length.strip():
        raise ValueError("Enter a signed depth or project parameter formula")
    parameter = f"{extrusion['id']}_length"
    if parameter in candidate["parameters"]:
        raise ValueError(f"Parameter {parameter} already exists")
    candidate["parameters"][parameter] = length
    extrusion["params"]["length"] = parameter
    candidate["features"].extend((extrusion, boolean))
    candidate["active_feature"] = boolean["id"]
    return candidate
