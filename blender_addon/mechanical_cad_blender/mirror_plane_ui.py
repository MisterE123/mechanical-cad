"""Non-destructive Mirror plane presets over existing canonical scalar fields."""

import math

PRESETS = {
    "XY": (("0", "0", "1"), "z", "Offset Z (mm)"),
    "XZ": (("0", "1", "0"), "y", "Offset Y (mm)"),
    "YZ": (("1", "0", "0"), "x", "Offset X (mm)"),
}


def _literal(value, parameters):
    """Recognize literals / direct literal parameters only; never evaluate text."""
    if isinstance(value, str) and value in parameters:
        value = parameters[value]
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def initialize(operator, parameters):
    """Choose display controls without changing any authored normal/origin value."""
    if operator.kind != "mirror":
        return
    values = [
        _literal(getattr(operator, key), parameters) for key in ("axis_x", "axis_y", "axis_z")
    ]
    mode = "CUSTOM"
    if all(value is not None for value in values):
        nonzero = [index for index, value in enumerate(values) if value != 0]
        if len(nonzero) == 1 and abs(values[nonzero[0]]) >= 1e-12:
            mode = ("YZ", "XZ", "XY")[nonzero[0]]
    operator.mirror_initializing = True
    try:
        operator.mirror_plane = mode
    finally:
        operator.mirror_initializing = False


def changed(operator, context):
    """Only an explicit preset selection replaces normal components."""
    if operator.mirror_initializing or operator.kind != "mirror":
        return
    if operator.mirror_plane in PRESETS:
        normal, _, _ = PRESETS[operator.mirror_plane]
        for key, value in zip(("axis_x", "axis_y", "axis_z"), normal, strict=True):
            setattr(operator, key, value)
    # Origin components, including hidden tangential values, stay untouched.
    # Switching to Custom therefore exposes the actual current canonical plane.


def draw(layout, operator):
    layout.prop(operator, "mirror_plane", text="Mirror plane")
    if operator.mirror_plane in PRESETS:
        _, key, label = PRESETS[operator.mirror_plane]
        layout.prop(operator, key, text=label)
        layout.label(text="Signed offset from the world origin; formulas are kept.")
    else:
        for keys, label in (
            (("axis_x", "axis_y", "axis_z"), "Plane normal (world coordinates)"),
            (("x", "y", "z"), "Plane origin (mm)"),
        ):
            box = layout.box()
            box.label(text=label)
            row = box.row(align=True)
            for key, axis in zip(keys, "XYZ", strict=True):
                row.prop(operator, key, text=axis)
        layout.label(text="Custom normal must be nonzero; its length does not matter.")
