"""Pure, formula-preserving values for solid authoring dialogs."""

import math

from .solid_feature_edit import SOLID_KINDS
from .unit_input import normalize_unit_input


def selected_history_id(state):
    """Read an explicit history selection; never infer a mesh identity."""
    rows = getattr(state, "features", ())
    index = getattr(state, "feature_index", -1)
    return rows[index].feature_id if 0 <= index < len(rows) else None


def solid_dialog_defaults(document, selected_id=None):
    """Prefer selected history, then explicit support, then the current output.

    A face sketch carries its intended supporting solid in canonical inputs.
    Other profiles do not authorize a geometric guess about which solid to use.
    All returned choices remain visible and editable in the dialog.
    """
    features = {feature["id"]: feature for feature in document["features"]}
    solids = [key for key, feature in features.items() if feature["kind"] in SOLID_KINDS]
    profiles = [key for key, feature in features.items() if feature["kind"].startswith("sketch_")]
    profile = selected_id if selected_id in profiles else (profiles[-1] if profiles else None)
    support = features.get(profile, {}).get("inputs", {}).get("support")
    base = next(
        (key for key in (selected_id, support, document.get("active_feature")) if key in solids),
        solids[-1] if solids else None,
    )
    return {"profile": profile, "base": base}


def extrusion_depth(depth, direction):
    """Convert an explicit direction to canonical signed length, not a float.

    SIGNED retains the existing scripting/formula interface unchanged. Directional
    depths must be positive; expressions are retained, with their sign chosen by
    the author rather than evaluated or rewritten by an approximate UI parser.
    """
    if direction not in {"NORMAL", "REVERSE", "SIGNED"}:
        raise ValueError("Choose an extrusion direction")
    if not depth.strip():
        raise ValueError("Enter a depth or project parameter formula")
    normalized = normalize_unit_input(depth, "length")
    if not isinstance(normalized, str):
        if direction != "SIGNED" and normalized <= 0:
            raise ValueError("Depth must be positive; use Direction to reverse the extrusion")
        return -normalized if direction == "REVERSE" else normalized
    if direction == "SIGNED":
        return depth
    try:
        value = float(depth)
    except ValueError:
        value = None
    if value is not None and (not math.isfinite(value) or value <= 0):
        raise ValueError("Depth must be positive; use Direction to reverse the extrusion")
    # Parenthesize the entire expression so a sum remains a sum when reversed.
    return f"-({depth})" if direction == "REVERSE" else depth


def outward_support_profile(document, profile_id, base_id):
    """Prove the standard outward face frame from canonical intent alone.

    Free, tilted, flipped, offset or formula-defined frames are deliberately not
    interpreted. A dialog may offer the inward default only for this narrow case.
    """
    profile = next((f for f in document["features"] if f["id"] == profile_id), {})
    if not profile.get("support_face") or profile.get("inputs", {}).get("support") != base_id:
        return False
    if profile.get("kind") in {"sketch_face_rectangle", "sketch_face_circle"}:
        try:
            return float(profile.get("params", {}).get("z", 0)) == 0
        except (ValueError, TypeError):
            return False
    if profile.get("kind") != "sketch_constrained":
        return False
    plane = profile.get("sketch", {}).get("plane", {})
    return plane.get("origin") == [0, 0, 0] and plane.get("quaternion") in (
        [1, 0, 0, 0],
        [-1, 0, 0, 0],
    )


def picked_blend_faces(document, result, base, face_a, face_b):
    """Validate a handoff's stable identities, not geometric edge adjacency."""
    if not result or face_a == face_b or not all((base, face_a, face_b)):
        raise ValueError("Pick two different faces on the current solid")
    source = next((f for f in document["features"] if f["id"] == base), {})
    if source.get("kind") not in SOLID_KINDS:
        raise ValueError("The picked base is no longer a solid feature")
    rows = [f for f in result.get("features", []) if f.get("id") == base]
    if len(rows) != 1 or rows[0].get("status") != "ok":
        raise ValueError("Rebuild the picked solid before choosing an edge")
    for identifier in (face_a, face_b):
        faces = [f for f in rows[0].get("topology", []) if f.get("id") == identifier]
        if (
            len(faces) != 1
            or faces[0].get("kind") != "face"
            or faces[0].get("provenance", {}).get("semantic_status") != "stable"
        ):
            raise ValueError("A picked face no longer has a stable identity; pick again")
    return base, face_a, face_b


def picked_shell_face(document, result, base, opening):
    """A direct opening pick must still be stable, planar and in this replay."""
    source = next((f for f in document["features"] if f["id"] == base), {})
    rows = [] if not result else [f for f in result.get("features", []) if f.get("id") == base]
    if source.get("kind") not in SOLID_KINDS or len(rows) != 1 or rows[0].get("status") != "ok":
        raise ValueError("Rebuild the picked solid before choosing an opening")
    faces = [f for f in rows[0].get("topology", []) if f.get("id") == opening]
    if (
        len(faces) != 1
        or faces[0].get("kind") != "face"
        or faces[0].get("provenance", {}).get("semantic_status") != "stable"
        or faces[0].get("signature", {}).get("surface") != "plane"
    ):
        raise ValueError("The opening no longer has a stable planar identity; pick again")
    return base, opening


CONSENT_RESUME_FIELDS = frozenset({
    "feature_id", "original_json", "feature_label", "base", "tool",
    "linked_profile", "linked_end_condition", "linked_direction", "linked_length",
    "linked_depth_scope", "depth_parameter_value", "target", "end_face", "offset",
})


def consent_resume_values(operator):
    """Copy bounded authored strings only; never carry permission or RNA."""
    values = {key: getattr(operator, key) for key in CONSENT_RESUME_FIELDS}
    validate_consent_resume(values, operator.original_json, operator.feature_id, operator.linked_tool_id)
    return values


def validate_consent_resume(values, original_json, feature_id, tool_id):
    if (
        not isinstance(values, dict)
        or set(values) != CONSENT_RESUME_FIELDS
        or any(not isinstance(v, str) for v in values.values())
        or any(len(v) > 4096 for k, v in values.items() if k != "original_json")
        or values["original_json"] != original_json
        or values["feature_id"] != feature_id
        or not tool_id or values["tool"] != tool_id
        or values["linked_depth_scope"] not in {"FEATURE", "PARAMETER"}
        or values["linked_end_condition"] not in {"BLIND", "SYMMETRIC", "THROUGH_ALL", "UP_TO_FACE"}
        or values["linked_direction"] not in {"1", "-1"}
    ):
        raise ValueError("The retained tool edit is stale or unsupported; reopen Edit Feature")


CIRCLE_RESUME_FIELDS = frozenset({
    "feature_id", "original_json", "feature_label", "radius", "x", "y", "z",
    "radius_edit_scope", "radius_parameter_value",
})


def circle_expression_fields(kind):
    if kind == "sketch_circle":
        return CIRCLE_RESUME_FIELDS
    if kind == "sketch_face_circle":
        return CIRCLE_RESUME_FIELDS | {"angle", "support", "support_face"}
    raise ValueError("Expression draft return only supports primitive circles")


def circle_expression_resume_values(operator):
    values = {key: getattr(operator, key) for key in circle_expression_fields(operator.kind)}
    validate_circle_expression_resume(
        values, operator.original_json, operator.feature_id, operator.kind,
        operator.radius_parameter_name,
    )
    return values


def validate_circle_expression_resume(values, original_json, feature_id, kind, parameter_name):
    if (
        not isinstance(values, dict)
        or set(values) != circle_expression_fields(kind)
        or any(not isinstance(v, str) for v in values.values())
        or len(original_json) > 2 * 1024 * 1024
        or any(len(v) > 4096 for k, v in values.items() if k != "original_json")
        or values["original_json"] != original_json
        or values["feature_id"] != feature_id
        or values["radius_edit_scope"] not in {"FEATURE", "PARAMETER"}
        or (values["radius_edit_scope"] == "PARAMETER" and not parameter_name)
    ):
        raise ValueError("The retained circle edit is stale or unsupported; reopen Edit Feature")
