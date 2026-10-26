"""Bounded display-only retirement intent; never geometry or solve authority."""

from .general_sketch_validation import _identifier, _keys, _point, _require


def validate_retirement(identifier, binding):
    """Validate the complete exceptional binding, including its versioned reason."""
    _identifier(identifier)
    _keys(binding, {"kind", "refs", "display", "offset", "retirement"})
    _require(binding["kind"] == "radius", "Only a removed fillet radius can be retired.")
    _require(type(binding["refs"]) is list and len(binding["refs"]) == 1,
             "Retired radius needs one exact arc ID.")
    _identifier(binding["refs"][0])
    _require(identifier != binding["refs"][0], "Retired binding IDs must be distinct.")
    _require(binding["display"] in ("radius", "diameter"), "Invalid retired radius display.")
    _require(type(binding["offset"]) is list, "Expected stored annotation offsets.")
    _point(binding["offset"])
    value = binding["retirement"]
    _keys(value, {"schema_version", "reason"})
    _require(type(value["schema_version"]) is int and value["schema_version"] == 1
             and value["reason"] == "restore_sharp_corner", "Unsupported annotation retirement.")


def retired_status(identifier, binding, occupied):
    """Only absence of both named identities is an expected retirement.

    Reappearance, even with an equivalent signature, requires explicit recovery;
    UI metadata cannot establish that a reused identity is the original fillet.
    """
    validate_retirement(identifier, binding)
    return "changed" if identifier in occupied or binding["refs"][0] in occupied else "retired"


def mark_retired(binding):
    return {**binding, "retirement": {"schema_version": 1, "reason": "restore_sharp_corner"}}
