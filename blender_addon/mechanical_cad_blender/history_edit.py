"""Detached graph editing helpers; never remove dependants implicitly."""

import copy
import re


def feature_dependants(document, identifier):
    features = document["features"]
    if identifier not in {f["id"] for f in features}:
        raise ValueError("Select an existing feature")
    removed = {identifier}
    while True:
        expanded = removed | {
            f["id"] for f in features if removed.intersection(f.get("inputs", {}).values())
        }
        if expanded == removed:
            return [f["id"] for f in features if f["id"] in removed and f["id"] != identifier]
        removed = expanded


def remove_feature(document, identifier, *, include_dependants=False):
    dependants = feature_dependants(document, identifier)
    if dependants and not include_dependants:
        raise ValueError(
            "Dependent features must be kept or explicitly removed together: "
            + ", ".join(dependants)
        )
    candidate = copy.deepcopy(document)
    removed = {identifier, *dependants}
    candidate["features"] = [f for f in candidate["features"] if f["id"] not in removed]
    if candidate.get("active_feature") in removed:
        candidate["active_feature"] = (
            candidate["features"][-1]["id"] if candidate["features"] else None
        )
    # Named parameters are intentionally preserved: another expression may use them.
    return candidate


def set_parameter(document, name, expression, *, replace_existing=False):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(
            "Parameter name must start with a letter or underscore and contain only letters, digits and underscores"
        )
    if not expression.strip():
        raise ValueError("Enter a number or formula")
    candidate = copy.deepcopy(document)
    if name in candidate["parameters"] and not replace_existing:
        raise ValueError("That parameter exists; choose Replace existing to change it")
    candidate["parameters"][name] = expression
    return candidate


def rename_feature(document, identifier, label):
    """Change only the label, preserving identity and all authored content.

    Match model._text's feature-label contract; canonical replay remains the
    authority. Do not trim or normalize labels or reinterpret them as IDs.
    """
    if not isinstance(label, str) or not label or len(label) > 256:
        raise ValueError("Feature label must be nonempty text up to 256 characters.")
    candidate = copy.deepcopy(document)
    matches = [feature for feature in candidate["features"] if feature["id"] == identifier]
    if len(matches) != 1:
        raise ValueError("Select an existing feature")
    matches[0]["label"] = label
    return candidate
