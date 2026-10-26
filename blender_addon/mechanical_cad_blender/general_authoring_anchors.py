"""Pure point-anchor intent shared by authoring and unfinished input."""

from .general_sketch_commands import PointRef, PointSeed, _identifier, _keys, _point, _require


def _anchor_payload(anchor):
    if type(anchor) is PointRef:
        return {"kind": "existing", "point_id": _identifier(anchor.id)}
    _require(type(anchor) is PointSeed, "Choose an explicit point ID or new XY coordinate.")
    return {"kind": "new", "position": _point((anchor.u, anchor.v))}


def _validate_anchor(anchor, bindings):
    _require(type(anchor) is dict, "Invalid proposal anchor.")
    if anchor.get("kind") == "existing":
        _keys(anchor, {"kind", "point_id"})
        bindings.require_identity("point", anchor["point_id"])
    else:
        _keys(anchor, {"kind", "position"})
        _require(anchor["kind"] == "new", "Unsupported proposal anchor kind.")
        _require(type(anchor["position"]) is list, "Expected stored XY coordinates.")
        _point(anchor["position"])
