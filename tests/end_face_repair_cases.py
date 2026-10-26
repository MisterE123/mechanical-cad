"""Shared canonical native/host cases for explicit staged extrusion-end repair."""

import copy


def _row(identifier, kind, label, params, inputs=None, *, end_face=None):
    defaults = {}
    if kind in {"sketch_rectangle", "sketch_circle", "transform"}:
        defaults = {"x": 0, "y": 0, "z": 0}
    if kind == "transform":
        defaults.update(rx=0, ry=0, rz=0)
    row = {
        "id": identifier,
        "kind": kind,
        "label": label,
        "params": {**defaults, **params},
        "inputs": inputs or {},
    }
    if end_face is not None:
        row["end_face"] = end_face
    return row


def feature(document, identifier):
    return next(row for row in document["features"] if row["id"] == identifier)


def end_face_case(*, failure="split", consumers=2):
    """Return accepted/proposed Parts; the latter changes just one Cut tool size.

    Both independent Up to Face consumers name the Cut's original block cap.
    The earlier replacement solid deliberately retains the same semantic face
    ID at a different height, so a correction must bind the exact source too.
    """
    if failure not in {"split", "missing"} or consumers not in {1, 2}:
        raise ValueError("Choose split/missing and one or two consumers")
    slot = (
        {"width": 2, "height": 12, "x": 4, "y": -1, "z": 5}
        if failure == "split"
        else {"width": 2, "height": 12, "x": -1, "y": -1, "z": 8}
    )
    rows = [
        _row("block_profile", "sketch_rectangle", "Block profile", {"width": 10, "height": 10}),
        _row("block", "extrude", "Block", {"length": 10}, {"profile": "block_profile"}),
        _row(
            "replacement", "transform", "Independent replacement plane", {"z": 3}, {"base": "block"}
        ),
        _row("slot_profile", "sketch_rectangle", "Upstream slot profile", slot),
        _row(
            "slot_tool",
            "extrude",
            "Upstream slot depth",
            {"length": 2 if failure == "split" else 3},
            {"profile": "slot_profile"},
        ),
        _row("slotted", "cut", "Slotted block", {}, {"base": "block", "tool": "slot_tool"}),
        _row("profile", "sketch_circle", "First profile", {"radius": 1, "x": 2, "y": 2, "z": 20}),
        _row(
            "tool",
            "extrude_to_face",
            "First Up to Face",
            {"direction": -1, "offset": "gap"},
            {"profile": "profile", "target": "slotted"},
            end_face="block/face/cap.end",
        ),
    ]
    if consumers == 2:
        rows.extend(
            [
                _row("profile2", "sketch_circle", "Second profile", {"radius": 1, "x": 8, "y": 2}),
                _row(
                    "tool2",
                    "extrude_to_face",
                    "Second Up to Face",
                    {"direction": 1, "offset": "gap + allowance"},
                    {"profile": "profile2", "target": "slotted"},
                    end_face="block/face/cap.end",
                ),
            ]
        )
    rows.append(
        _row(
            "downstream",
            "transform",
            "Dependent solid",
            {"x": 20},
            {"base": "tool2" if consumers == 2 else "tool"},
        )
    )
    accepted = {
        "schema_version": 1,
        "id": "staged_end_face_repair",
        "name": "Explicit end-face correction",
        "units": "mm",
        "parameters": {"gap": -0.5, "allowance": 0.25},
        "features": rows,
        "active_feature": "downstream",
    }
    proposed = copy.deepcopy(accepted)
    if failure == "split":
        feature(proposed, "slot_tool")["params"]["length"] = 6
    else:
        feature(proposed, "slot_profile")["params"]["width"] = 12
    return accepted, proposed
