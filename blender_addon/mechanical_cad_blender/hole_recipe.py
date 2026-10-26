"""Round-hole recipes made exclusively from existing canonical feature kinds.

The reserved ID family is only a UI grouping hint. Recognition verifies the whole
recipe and refuses shared intermediate features; it never grants topology authority.
"""

import copy
import math
import re

from .unit_input import normalize_unit_input

ROOT = re.compile(r"^hole_[0-9a-f]{32}$")


def dimension(value, name, *, positive=True):
    value = normalize_unit_input(value, "length")
    if isinstance(value, bool):
        raise ValueError(f"{name} needs a literal length")
    try:
        value = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} needs a literal length (mm, cm or in), not a formula") from exc
    if not math.isfinite(value) or abs(value) > 1e6 or (positive and value < 1e-6):
        raise ValueError(f"{name} must be {'positive and ' if positive else ''}within 1,000,000 mm")
    return value


def hole_candidate(
    document,
    root,
    *,
    base,
    face,
    diameter,
    depth,
    x=0,
    y=0,
    counterbore=False,
    counter_diameter=10,
    counter_depth=2,
    label="Hole",
    editing=False,
):
    if not ROOT.fullmatch(root) or not face or face == "NONE":
        raise ValueError("Choose an explicit stable planar entry face")
    diameter = dimension(diameter, "Hole diameter")
    depth = dimension(depth, "Hole depth")
    x, y = dimension(x, "Center X", positive=False), dimension(y, "Center Y", positive=False)
    if not label.strip():
        raise ValueError("Enter a hole name")
    if counterbore:
        counter_diameter = dimension(counter_diameter, "Counterbore diameter")
        counter_depth = dimension(counter_depth, "Counterbore depth")
        if counter_diameter <= diameter or counter_depth >= depth:
            raise ValueError(
                "Counterbore must be wider than the hole and shallower than its total depth"
            )
    candidate = copy.deepcopy(document)
    old = inspect_hole(document, root) if editing else None
    if editing and old is None:
        raise ValueError(
            "Hole recipe changed or an intermediate is shared; edit individual features instead"
        )
    if old and old["counterbore"] != counterbore:
        raise ValueError("Keep this hole type when editing; create a new hole to change type")
    entries = []

    def add(suffix, kind, params, inputs, title):
        feature = {
            "id": root + suffix,
            "kind": kind,
            "label": title,
            "params": params,
            "inputs": inputs,
        }
        entries.append(feature)
        return feature

    def profile(suffix, radius, title):
        f = add(
            suffix,
            "sketch_face_circle",
            {"radius": radius, "x": x, "y": y, "z": 0, "angle": 0},
            {"support": base},
            title,
        )
        f["support_face"] = face

    profile("_profile", diameter / 2, label + " • circle")
    add("_tool", "extrude", {"length": -depth}, {"profile": root + "_profile"}, label + " • depth")
    add(
        "_bore" if counterbore else "",
        "cut",
        {},
        {"base": base, "tool": root + "_tool"},
        label + " • bore" if counterbore else label,
    )
    if counterbore:
        profile("_counter_profile", counter_diameter / 2, label + " • counterbore circle")
        add(
            "_counter_tool",
            "extrude",
            {"length": -counter_depth},
            {"profile": root + "_counter_profile"},
            label + " • counterbore depth",
        )
        add("", "cut", {}, {"base": root + "_bore", "tool": root + "_counter_tool"}, label)
    ids = {f["id"] for f in entries}
    if base in ids or not any(f["id"] == base for f in document["features"]):
        raise ValueError("Choose an existing input solid outside this hole recipe")
    if old:
        by_id = {f["id"]: f for f in entries}
        candidate["features"] = [by_id.get(f["id"], f) for f in candidate["features"]]
    else:
        if any(f["id"] in ids for f in candidate["features"]):
            raise ValueError("Hole identifiers already exist")
        candidate["features"].extend(entries)
        candidate["active_feature"] = root
    return candidate


def inspect_hole(document, root):
    """Return editable values only for an intact, literal, unshared recipe."""
    if not ROOT.fullmatch(root):
        return None
    features = {f["id"]: f for f in document["features"]}
    try:
        final, circle, tool = (features[root + suffix] for suffix in ("", "_profile", "_tool"))
        counterbore = root + "_bore" in features
        values = dict(
            base=circle["inputs"]["support"],
            face=circle["support_face"],
            diameter=circle["params"]["radius"] * 2,
            depth=-tool["params"]["length"],
            x=circle["params"]["x"],
            y=circle["params"]["y"],
            counterbore=counterbore,
            label=final["label"],
        )
        if counterbore:
            values.update(
                counter_diameter=features[root + "_counter_profile"]["params"]["radius"] * 2,
                counter_depth=-features[root + "_counter_tool"]["params"]["length"],
            )
        # Reconstruct on an empty recipe-free copy, then compare all semantic data.
        owned = {root + suffix for suffix in ("", "_profile", "_tool")}
        if counterbore:
            owned.update(root + suffix for suffix in ("_bore", "_counter_profile", "_counter_tool"))
        stripped = copy.deepcopy(document)
        stripped["features"] = [f for f in stripped["features"] if f["id"] not in owned]
        expected = hole_candidate(stripped, root, **values)["features"][-len(owned) :]
        for f in expected:
            actual = dict(features[f["id"]])
            actual["label"] = f["label"]  # Renaming individual steps is harmless.
            if actual != f:
                return None
        for f in document["features"]:
            if f["id"] not in owned and set(f["inputs"].values()) & (owned - {root}):
                return None
        return values
    except (KeyError, TypeError, ValueError):
        return None
