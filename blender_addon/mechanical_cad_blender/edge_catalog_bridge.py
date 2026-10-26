"""Strict opt-in transient edge-catalog evidence, independent of replay schemas."""

import copy
import math

from . import part_contracts, part_result_bridge, result_v3
from .sketch_bridge import _keys, _require


def validate_response(request, response):
    request = part_contracts.snapshot_request(request)
    part_contracts._bounded_response(response)
    _keys(request, {"protocol_version", "result_version", "action", "document", "options"})
    _require(request["action"] == "edge_catalog", "wrong catalog action")
    _require(
        type(request["result_version"]) is int and request["result_version"] in (2, 3),
        "catalog requires typed replay",
    )
    _keys(request["options"], {"linear_deflection", "projection_arcs"}, {"linear_deflection"})
    arcs = request["options"].get("projection_arcs", False)
    _require(type(arcs) is bool, "arc projection admission must be explicit boolean")
    _keys(
        response,
        {
            "protocol_version",
            "result_version",
            "action",
            "input_fingerprint",
            "ok",
            "error",
            "result",
        },
    )
    _require(
        response["action"] == "edge_catalog"
        and response["ok"] is True
        and response["error"] is None,
        "no successful edge catalog",
    )
    _require(
        response["input_fingerprint"] == part_contracts.input_fingerprint(request),
        "edge catalog belongs to another request",
    )
    _keys(response["result"], {"replay", "catalogs"})
    replay_request = {**request, "action": "replay",
                      "options": {"linear_deflection": request["options"]["linear_deflection"]}}
    replay_response = {
        key: response[key] for key in ("protocol_version", "result_version", "ok", "error")
    }
    replay_response.update(
        input_fingerprint=part_contracts.input_fingerprint(replay_request),
        result=response["result"]["replay"],
    )
    # Catalogs embed only replay, not arbitrary operations. Validate at the
    # lower-level replay boundary rather than recursively importing dispatch.
    validator = result_v3 if request["result_version"] == 3 else part_result_bridge
    validator.validate_response(replay_request, replay_response)
    solids = {
        f["id"]: f
        for f in response["result"]["replay"]["features"]
        if (f.get("output") or {}).get("kind") == "solid"
    }
    catalogs = response["result"]["catalogs"]
    _keys(catalogs, set(solids))
    for identifier, entries in catalogs.items():
        _require(type(entries) is list and len(entries) <= 2048, "invalid edge count")
        stable = {
            f["id"]
            for f in solids[identifier]["topology"]
            if f["kind"] == "face" and f["provenance"]["semantic_status"] == "stable"
        }
        seen, count = set(), 0
        for entry in entries:
            _keys(entry, {"faces", "points", "endpoint_faces", "circle"} | ({"arc"} if arcs else set()), {"faces", "points"})
            faces, points = entry["faces"], entry["points"]
            _require(
                type(faces) is list
                and len(faces) == 2
                and all(type(f) is str and f in stable for f in faces)
                and faces == sorted(set(faces)),
                "edge requires two stable source faces",
            )
            _require(tuple(faces) not in seen, "multiple edges share the same face pair")
            seen.add(tuple(faces))
            _require(type(points) is list and 2 <= len(points) <= 4097, "invalid edge polyline")
            count += len(points)
            _require(count <= 100000, "edge display budget exceeded")
            for point in points:
                _require(
                    type(point) is list
                    and len(point) == 3
                    and all(
                        type(v) in (int, float) and math.isfinite(v) and abs(v) <= 1e9
                        for v in point
                    ),
                    "invalid edge display coordinate",
                )
            _require(any(p != points[0] for p in points[1:]), "degenerate edge polyline")
            if "arc" in entry:
                from .sketch_projection import validate_solid_edges

                _require("circle" not in entry and "endpoint_faces" not in entry,
                         "conflicting edge analytic kinds")
                _keys(entry["arc"], {"endpoint_faces", "points", "center", "normal", "radius", "sweep"})
                analytic = {"kind": "arc", "faces": faces, **entry["arc"]}
                row = {"kind": "arc", "faces": faces,
                       "endpoint_faces": entry["arc"]["endpoint_faces"], "target": "probe"}
                validate_solid_edges([analytic], [row], solids[identifier]["topology"])
            if "circle" in entry:
                from .sketch_projection import validate_circle

                validate_circle(entry["circle"])
                _require(
                    "endpoint_faces" not in entry and len(points) > 2,
                    "conflicting edge analytic kinds",
                )
            if "endpoint_faces" in entry:
                from .sketch_projection import validate_endpoint_faces

                validate_endpoint_faces(entry["endpoint_faces"], faces)
                _require(
                    len(points) == 2
                    and all(f in stable for group in entry["endpoint_faces"] for f in group),
                    "straight edge endpoint identities must resolve to stable source faces",
                )
    return copy.deepcopy(response)


def nearest_segment(pointer, a, b):
    """Return pixel distance and clamped segment fraction; no CAD identity inference."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = (
        max(0.0, min(1.0, ((pointer[0] - a[0]) * dx + (pointer[1] - a[1]) * dy) / length))
        if length
        else 0.0
    )
    return math.hypot(pointer[0] - a[0] - t * dx, pointer[1] - a[1] - t * dy), t
