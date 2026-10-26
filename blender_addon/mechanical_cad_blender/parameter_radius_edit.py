"""Explicit radius parameter intent for primitive circle sketches, never diameter."""

from .history_edit import set_parameter
from .unit_input import normalize_unit_input

CIRCLE_KINDS = frozenset({"sketch_circle", "sketch_face_circle"})


def radius_parameter(document, feature):
    if feature.get("kind") not in CIRCLE_KINDS:
        return ""
    value = feature.get("params", {}).get("radius")
    return value if isinstance(value, str) and value in document.get("parameters", {}) else ""


def edit_shared_radius(original, candidate, feature_id, name, value):
    for document in (original, candidate):
        if sum(f["id"] == feature_id for f in document["features"]) != 1:
            raise ValueError("Ambiguous circle binding; reopen Edit Feature")
    source = next(f for f in original["features"] if f["id"] == feature_id)
    target = next(f for f in candidate["features"] if f["id"] == feature_id)
    if not name or radius_parameter(original, source) != name:
        raise ValueError("The radius parameter link changed; reopen Edit Feature")
    if target["kind"] != source["kind"] or target["params"].get("radius") != name:
        raise ValueError("Shared editing must keep the circle radius linked")
    if str(original["parameters"][name]) == value:
        return candidate
    return set_parameter(
        candidate, name, str(normalize_unit_input(value, "length")), replace_existing=True
    )
