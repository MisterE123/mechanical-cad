"""Edit an explicitly bound Boolean extrusion without hiding its canonical nodes."""

import copy

from .extrusion_end_condition import EXTRUSION_KINDS, set_up_to_face
from .unit_input import normalize_unit_input


class SharedToolConsentRequired(ValueError):
    """Preflight refusal; no candidate was published or geometry failure inferred."""


def linked_extrusion(document, feature_id):
    """Return the exact tool and its other direct consumers, never a history guess."""
    features = {feature["id"]: feature for feature in document["features"]}
    feature = features.get(feature_id, {})
    if feature.get("kind") not in {"union", "cut"}:
        return None
    tool = features.get(feature.get("inputs", {}).get("tool"), {})
    if tool.get("kind") not in EXTRUSION_KINDS:
        return None
    consumers = [
        item
        for item in document["features"]
        if item["id"] != feature_id and tool["id"] in item.get("inputs", {}).values()
    ]
    return tool, consumers


def edit_linked_extrusion(
    document,
    candidate,
    feature_id,
    *,
    tool_id,
    length,
    profile,
    allow_shared=False,
    end_condition=None,
    direction=None,
    target=None,
    end_face=None,
    offset=None,
):
    """Update a detached candidate; named parameter definitions are never modified.

    The caller binds document to the dialog's exact original JSON before calling.
    Replacing the Boolean tool and editing its old tool simultaneously is rejected.
    """
    linked = linked_extrusion(document, feature_id)
    if linked is None or linked[0]["id"] != tool_id:
        raise ValueError("Extrusion tool changed; reopen Edit Feature")
    tool, consumers = linked
    boolean = next(item for item in candidate["features"] if item["id"] == feature_id)
    through = (
        tool["kind"] == "extrude_through"
        if end_condition is None
        else end_condition == "THROUGH_ALL"
    )
    symmetric = (
        tool["kind"] == "extrude_symmetric"
        if end_condition is None
        else end_condition == "SYMMETRIC"
    )
    up_to_face = (
        tool["kind"] == "extrude_to_face"
        if end_condition is None
        else end_condition == "UP_TO_FACE"
    )
    if end_condition not in {None, "BLIND", "THROUGH_ALL", "SYMMETRIC", "UP_TO_FACE"}:
        raise ValueError("Choose Blind, Symmetric, Through All or Up to planar face")
    desired = copy.deepcopy(tool)
    desired["inputs"] = {"profile": profile}
    if up_to_face:
        set_up_to_face(
            desired,
            profile=profile,
            target=tool["inputs"].get("target") if target is None else target,
            end_face=tool.get("end_face") if end_face is None else end_face,
            offset=tool["params"].get("offset", 0) if offset is None else offset,
            direction=tool["params"].get("direction", 1) if direction is None else direction,
        )
    elif through:
        if boolean["kind"] != "cut":
            raise ValueError("Through All is available for Remove only")
        value = tool["params"].get("direction", 1) if direction is None else direction
        if str(value) not in {"1", "-1", "1.0", "-1.0"}:
            raise ValueError("Choose Along or Opposite sketch normal")
        desired["kind"] = "extrude_through"
        desired["params"] = {"direction": int(float(value))}
        desired["inputs"]["base"] = boolean["inputs"]["base"]
    else:
        if not str(length).strip():
            raise ValueError("Extrusion requires a profile and signed depth")
        desired["kind"] = "extrude_symmetric" if symmetric else "extrude"
        old = tool["params"].get("length")
        desired["params"] = {
            "length": old if str(old) == str(length) else normalize_unit_input(length, "length")
        }
    if not up_to_face:
        desired.pop("end_face", None)
    if desired == tool:
        return candidate
    if boolean["inputs"]["tool"] != tool_id:
        raise ValueError("Tool changed; Apply that change, then reopen to edit its extrusion")
    if consumers and not allow_shared:
        names = ", ".join(f"{item['label']} ({item['id']})" for item in consumers)
        raise SharedToolConsentRequired(f"Shared extrusion also changes {names}; explicitly allow shared edits")
    if not profile or profile == "NONE":
        raise ValueError("Extrusion requires a profile and signed depth")
    result = copy.deepcopy(candidate)
    edited = next(item for item in result["features"] if item["id"] == tool_id)
    edited.clear()
    edited.update(desired)
    return result
