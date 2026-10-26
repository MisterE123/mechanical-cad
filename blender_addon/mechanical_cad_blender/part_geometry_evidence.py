"""Strict successful/partial check and export evidence for Part result version 2."""

from __future__ import annotations

from .geometry_evidence import validate_geometry_check
from .sketch_bridge import _keys, _number, _require


def validate_geometry_action(request, response):
    """A complete replay is necessary but does not imply a completed check/export."""
    action, result = request["action"], response["result"]
    checks, exported = response["geometry_check"], response["export"]
    if not response["ok"]:
        _require(exported is None, "failed action claims a completed export")
        if checks is None:
            return
    _require(
        result is not None and result["status"] == "ok", "geometry evidence lacks complete replay"
    )
    active = next(
        (item for item in result["features"] if item["id"] == result["active_feature"]), None
    )
    _require(
        active is not None and active["status"] == "ok" and active["output"]["kind"] == "solid",
        "geometry evidence requires the actual selected solid",
    )
    linear_deflection = request.get("options", {}).get("linear_deflection", 0.1)
    validate_geometry_check(
        checks,
        linear_deflection=linear_deflection,
        stats=active["stats"],
        mesh=active["mesh"],
        encoded=action == "export_stl",
        allow_partial_encoded=action == "export_stl" and not response["ok"],
    )
    if not response["ok"]:
        return
    if action == "check_geometry":
        _require(exported is None, "read-only geometry check claims an export")
        return
    _keys(
        exported,
        {
            "format",
            "destination",
            "bytes",
            "units",
            "document_hash",
            "active_feature",
            "linear_deflection_mm",
            "atomic_replace",
        },
    )
    _require(
        exported["format"] == ("STEP" if action == "export_step" else "STL")
        and type(exported["destination"]) is str
        and exported["destination"] == request.get("destination")
        and exported["units"] == "mm"
        and exported["document_hash"] == result["document_hash"]
        and exported["active_feature"] == result["active_feature"]
        and exported["linear_deflection_mm"] == linear_deflection
        and exported["atomic_replace"] is True,
        "export receipt differs from the exact requested output",
    )
    _require(
        type(exported["bytes"]) is int and 0 < exported["bytes"] <= 2**63 - 1,
        "invalid export byte count",
    )
    _number(exported["linear_deflection_mm"], minimum=0.001, bound=10)
    if action == "export_stl":
        _require(
            exported["bytes"] == 84 + 50 * checks["encoded_mesh"]["triangles"],
            "binary STL byte count differs from encoded triangle evidence",
        )
