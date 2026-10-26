"""Read-only, geometry-derived reference annotation identity and validation.

This metadata never becomes a solver constraint or stores a measured value.
Absent entity IDs stay unavailable. A label key is only a deterministic UI key;
its explicit source kind and stable authored entity ID are the binding authority.
"""

import hashlib

from .general_sketch_commands import _identifier, _keys, _point, _require

REFERENCE_FIELDS = {"role", "kind", "source_kind", "refs", "display", "offset"}
READ_ONLY_MESSAGE = (
    "Read-only reference measurement. Use Dimension for driving length/radius, "
    "or Set diameter for a driving diameter."
)


def is_reference(binding):
    return type(binding) is dict and binding.get("role") == "reference"


def reference_id(kind, source_kind, source_id):
    _require(kind in {"length", "radius", "diameter"}, "Unsupported reference measurement.")
    _require(source_kind in {"line", "circle", "arc"}, "Unsupported reference source kind.")
    _identifier(source_id)
    digest = hashlib.sha256((kind + "\0" + source_kind + "\0" + source_id).encode()).hexdigest()
    return "ref_" + digest[:24]


def validate_reference(identifier, binding):
    _identifier(identifier)
    _keys(binding, REFERENCE_FIELDS)
    _require(binding["role"] == "reference", "Expected an explicit reference role.")
    kind, source_kind, refs = binding["kind"], binding["source_kind"], binding["refs"]
    _require(
        type(kind) is str and type(source_kind) is str,
        "Reference kinds must be text.",
    )
    _require(
        (kind == "length" and source_kind == "line")
        or (kind in {"radius", "diameter"} and source_kind in {"circle", "arc"}),
        "Use line length or circle/arc radius or diameter.",
    )
    _require(type(refs) is list and len(refs) == 1, "Reference requires one authored entity ID.")
    _identifier(refs[0])
    _require(identifier == reference_id(kind, source_kind, refs[0]), "Reference identity mismatch.")
    _require(binding["display"] == kind, "Reference display must match its measurement kind.")
    _require(type(binding["offset"]) is list, "Reference placement must be an array.")
    _point(binding["offset"])


def reference_status(binding, entities):
    """entities maps authored ID to kind; do not search by location or shape."""
    actual = entities.get(binding["refs"][0])
    return (
        "missing"
        if actual is None
        else "available"
        if actual == binding["source_kind"]
        else "changed"
    )


def make_reference(kind, source_kind, source_id, offset):
    identifier = reference_id(kind, source_kind, source_id)
    binding = {
        "role": "reference",
        "kind": kind,
        "source_kind": source_kind,
        "refs": [source_id],
        "display": kind,
        "offset": _point(offset),
    }
    validate_reference(identifier, binding)
    return identifier, binding
