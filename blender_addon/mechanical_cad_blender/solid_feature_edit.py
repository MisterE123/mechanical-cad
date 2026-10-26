"""Detached feature-history edits, shared by dialogs and tests. No native imports."""

import copy

from .unit_input import feature_dimension, normalize_unit_input

SOLID_KINDS = frozenset(
    {
        "import_step",
        "spur_gear",
        "extrude",
        "extrude_through",
        "extrude_to_face",
        "extrude_symmetric",
        "cut",
        "union",
        "intersection",
        "revolve",
        "fillet",
        "chamfer",
        "transform",
        "mirror",
        "linear_pattern",
        "circular_pattern",
        "linear_cut_pattern",
        "circular_cut_pattern",
        "shell",
        "loft",
        "sweep",
    }
)
FEATURE_FIELDS = {
    "spur_gear": (
        "module",
        "tooth_count",
        "thickness",
        "pressure_angle",
        "bore_diameter",
        "backlash",
        "clearance",
        "profile_tolerance",
    ),
    "sketch_face_rectangle": ("width", "height", "x", "y", "z", "angle"),
    "sketch_face_circle": ("radius", "x", "y", "z", "angle"),
    "sketch_rectangle": ("width", "height", "x", "y", "z"),
    "sketch_circle": ("radius", "x", "y", "z"),
    "extrude": ("length",),
    "extrude_symmetric": ("length",),
    "extrude_through": ("direction",),
    "extrude_to_face": ("direction", "offset"),
    "cut": (),
    "union": (),
    "intersection": (),
    "revolve": ("angle", "axis_x", "axis_y", "axis_z", "x", "y", "z"),
    "fillet": ("radius",),
    "chamfer": ("distance",),
    "mirror": ("axis_x", "axis_y", "axis_z", "x", "y", "z"),
    "transform": ("x", "y", "z", "rx", "ry", "rz"),
    "linear_pattern": ("count", "dx", "dy", "dz"),
    "circular_pattern": ("count", "angle", "axis_x", "axis_y", "axis_z", "x", "y", "z"),
    "linear_cut_pattern": ("count", "dx", "dy", "dz"),
    "circular_cut_pattern": ("count", "angle", "axis_x", "axis_y", "axis_z", "x", "y", "z"),
    "shell": ("thickness",),
    "loft": ("ruled",),
    "sweep": (),
}
FEATURE_INPUTS = {
    "sketch_face_rectangle": ("support",),
    "sketch_face_circle": ("support",),
    "extrude": ("profile",),
    "extrude_symmetric": ("profile",),
    "extrude_through": ("profile", "base"),
    "extrude_to_face": ("profile", "target"),
    "revolve": ("profile",),
    "cut": ("base", "tool"),
    "union": ("base", "tool"),
    "intersection": ("base", "tool"),
    "fillet": ("base",),
    "chamfer": ("base",),
    "mirror": ("base",),
    "transform": ("base",),
    "linear_pattern": ("base",),
    "circular_pattern": ("base",),
    "linear_cut_pattern": ("base", "tool"),
    "circular_cut_pattern": ("base", "tool"),
    "shell": ("base",),
    "loft": ("start", "end"),
    "sweep": ("profile", "path"),
}


def edit_feature(document, identifier, *, label, params, inputs):
    """Return an independent candidate; preserve untouched numeric types exactly."""
    candidate = copy.deepcopy(document)
    matches = [f for f in candidate["features"] if f["id"] == identifier]
    if len(matches) != 1:
        raise ValueError("Select one existing feature to edit")
    feature = matches[0]
    kind = feature["kind"]
    if kind not in FEATURE_FIELDS:
        raise ValueError("Edit this sketch with the Sketch workspace instead")
    if set(params) != set(feature["params"]) or set(inputs) != set(feature["inputs"]):
        raise ValueError("Feature fields changed while the dialog was open")
    if not label.strip():
        raise ValueError("Feature label cannot be empty")
    for name, value in params.items():
        old = feature["params"][name]
        if (
            kind in {"extrude_through", "extrude_to_face"}
            and name == "direction"
            and float(old) == float(value)
        ):
            continue
        if str(old) != str(value):
            if not str(value).strip():
                raise ValueError(f"{name} needs a number or formula")
            feature["params"][name] = (
                int(value)
                if kind in {"extrude_through", "extrude_to_face"} and name == "direction"
                else normalize_unit_input(value, feature_dimension(kind, name))
            )
    feature["label"] = label
    feature["inputs"] = dict(inputs)
    # Editing upstream history does not change the chosen final output.
    return candidate


def set_sweep_placement(feature, mode, *, reverse=False, roll="0"):
    """Write an explicitly reviewed intent; omission remains the old authored mode."""
    from .sweep_placement import validate_placement

    if feature["kind"] != "sweep":
        raise ValueError("Section placement is only available for Sweep")
    if mode == "AUTHORED":
        feature.pop("sweep_placement", None)
        return
    if mode != "AUTO":
        raise ValueError("Unsupported Sweep placement choice")
    old = feature.get("sweep_placement", {})
    angle = old.get("roll_degrees", 0)
    if str(angle) != str(roll):
        normalized = normalize_unit_input(roll, "angle")
        try:
            angle = float(normalized)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Sweep roll needs a literal angle in degrees, not a formula") from exc
    placement = {
        "version": 1,
        "mode": "path_start_centroid",
        "reverse": reverse,
        "roll_degrees": angle,
    }
    validate_placement(placement)
    feature["sweep_placement"] = placement
