"""Bounded unit-bearing UI literals, not a new canonical expression language.

Only a complete numeric literal plus an explicit supported suffix is converted.
Bare numbers and existing formula text retain their exact value/type. Lengths
normalize to millimetres, angles to UI degrees; existing radians seams stay in
their callers. No named parameter is implicitly assigned a physical dimension.
"""

import ast
import math
import re

LENGTH_INPUT_HELP = "Length: number/formula in mm, or a literal (1/8 in) with mm, cm, m, in or ft"
ANGLE_INPUT_HELP = "Angle: number/formula in degrees, or a literal (1/2 deg) with deg or rad"
UNIT_INPUT_LIMIT = 256
MAX_MAGNITUDE = 1e12
_NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_LITERAL = re.compile(rf"^\s*({_NUMBER})\s*([A-Za-z]+)\s*$")
# Fraction tokens use ASCII digits and horizontal spacing only. A mixed number
# has an unsigned whole part and a proper fraction; one leading sign covers both.
_FRACTION = re.compile(
    r"^[ \t]*([+-]?)(?:([0-9]+)[ \t]+)?([0-9]+)[ \t]*/[ \t]*"
    r"([0-9]+)[ \t]*([A-Za-z]+)[ \t]*$"
)
_NONFINITE = re.compile(r"^\s*[+-]?(?:nan|inf|infinity)\s+[A-Za-z]+\s*$", re.I)
# An adjacent suffix is not legal legacy arithmetic. An explicit multiplication
# such as '2 * mm' is still a formula using a parameter named mm, not a unit.
_EMBEDDED = re.compile(rf"(?<![\w.])(?:{_NUMBER})\s*[A-Za-z]+\b")
_UNITS = {
    "mm": ("length", 1.0),
    "cm": ("length", 10.0),
    "m": ("length", 1000.0),
    "in": ("length", 25.4),
    "ft": ("length", 304.8),
    "deg": ("angle", 1.0),
    "rad": ("angle", 180.0 / math.pi),
}


def normalize_unit_input(value, dimension):
    """Convert an explicit literal, or return unitless input without rewriting.

    dimension is length, angle or scalar. Scalar deliberately excludes untyped
    project parameters, counts, flags, ratios, axes and quaternion components.
    Field-specific positivity/ranges remain enforced by their existing validators.
    """
    if dimension not in {"length", "angle", "scalar"}:
        raise ValueError("Unknown input dimension")
    if not isinstance(value, str):
        return value
    if len(value) > UNIT_INPUT_LIMIT:
        raise ValueError("Enter a number or formula of at most 256 characters.")
    fraction = _FRACTION.fullmatch(value)
    # A complete fraction with a supported suffix cannot be a legacy Python
    # expression. Recognize it before ast.parse to avoid warnings for '1/8in'.
    # Unknown suffixes still pass syntax recognition (e.g. legacy '1/2j').
    if fraction is None or fraction.group(5) not in _UNITS:
        try:
            ast.parse(value.strip(), mode="eval")
        except (SyntaxError, ValueError, RecursionError):
            pass
        else:
            # Syntax recognition is not evaluation or permission. Leave every legacy
            # expression (including hex literals and unit-like names) to the unchanged
            # canonical allowlist evaluator, even if it will reject that expression.
            return value
    if _NONFINITE.fullmatch(value):
        raise ValueError("Unit values must be finite real numbers.")
    match = _LITERAL.fullmatch(value)
    if match is None and fraction is None:
        if _EMBEDDED.search(value):
            raise ValueError(
                "Use one number and one unit, such as 10 mm or 45 deg. "
                "Units inside formulas and mixed-unit arithmetic are not supported; "
                "keep formulas in the field's existing units."
            )
        return value
    if fraction is not None:
        sign, whole, numerator, denominator, suffix = fraction.groups()
        numerator, denominator = int(numerator), int(denominator)
        if denominator == 0:
            raise ValueError("A fraction denominator must be greater than zero.")
        if whole is not None and numerator >= denominator:
            raise ValueError("Use a proper fraction after the whole number, such as 1 1/2 in.")
        number = (int(whole or 0) + numerator / denominator) * (-1 if sign == "-" else 1)
    else:
        number, suffix = match.groups()
    if suffix not in _UNITS:
        raise ValueError("Unknown unit. Use mm, cm, m, in, ft, deg or rad (lowercase).")
    actual, factor = _UNITS[suffix]
    if dimension == "scalar":
        raise ValueError(
            "This field has no declared length or angle unit. "
            "Use a unitless number or its existing parameter formula."
        )
    if dimension != actual:
        accepted = "mm, cm, m, in or ft" if dimension == "length" else "deg or rad"
        raise ValueError(f"This is a {dimension} field; use {accepted}, not {suffix}.")
    result = float(number) * factor
    if not math.isfinite(result) or abs(result) > MAX_MAGNITUDE:
        raise ValueError("Converted unit value must be finite and within ±1e12.")
    return result


_LENGTH_FIELDS = {
    "spur_gear": {"module", "thickness", "bore_diameter", "backlash", "profile_tolerance"},
    "sketch_rectangle": {"width", "height", "x", "y", "z"},
    "sketch_circle": {"radius", "x", "y", "z"},
    "sketch_face_rectangle": {"width", "height", "x", "y", "z"},
    "sketch_face_circle": {"radius", "x", "y", "z"},
    "extrude": {"length"},
    "extrude_symmetric": {"length"},
    "extrude_to_face": {"offset"},
    "fillet": {"radius"},
    "chamfer": {"distance"},
    "shell": {"thickness"},
    "revolve": {"x", "y", "z"},
    "mirror": {"x", "y", "z"},
    "transform": {"x", "y", "z"},
    "linear_pattern": {"dx", "dy", "dz"},
    "linear_cut_pattern": {"dx", "dy", "dz"},
    "circular_pattern": {"x", "y", "z"},
    "circular_cut_pattern": {"x", "y", "z"},
}
_ANGLE_FIELDS = {
    "spur_gear": {"pressure_angle"},
    "sketch_face_rectangle": {"angle"},
    "sketch_face_circle": {"angle"},
    "revolve": {"angle"},
    "transform": {"rx", "ry", "rz"},
    "circular_pattern": {"angle"},
    "circular_cut_pattern": {"angle"},
}


def feature_dimension(kind, field):
    if field in _LENGTH_FIELDS.get(kind, ()):
        return "length"
    if field in _ANGLE_FIELDS.get(kind, ()):
        return "angle"
    return "scalar"


def normalize_feature_inputs(kind, params):
    return {
        name: normalize_unit_input(value, feature_dimension(kind, name))
        for name, value in params.items()
    }


def normalize_driver_input(value, kind):
    dimension = (
        "angle" if kind == "angle" else "length" if kind in {"distance", "radius"} else "scalar"
    )
    return normalize_unit_input(value, dimension)
