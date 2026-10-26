"""Native-free result negotiation and disposable, source-bound solved linework.

This is display conversion only: it neither solves nor builds a profile, and its
vertices/indices are never canonical sketch identity or geometry/export evidence.
"""

from __future__ import annotations

import math

from .sketch_bridge import validate_output
from .sketch_contracts_v3 import validate_output_v3

_FLOAT32_MAX = 3.4028234663852886e38


def negotiated_result_version(document, requested=None):
    """Leave legacy requests unchanged; new embedded data cannot silently downgrade."""
    if requested is not None and (type(requested) is not int or requested not in (1, 2)):
        raise ValueError("Only Part result versions 1 and 2 are supported.")
    if type(document) is not dict or type(document.get("features")) is not list:
        raise ValueError("A Part document requires a feature array.")
    requires_typed = False
    for feature in document["features"]:
        if type(feature) is not dict:
            raise ValueError("Part features must be objects.")
        if "sketch" not in feature:
            continue
        sketch = feature["sketch"]
        version = sketch.get("schema_version") if type(sketch) is dict else None
        if type(version) is not int or version not in (1, 2):
            raise ValueError(
                "Unsupported embedded sketch schema version; use matching add-on and backend versions."
            )
        requires_typed |= version == 2
    if requires_typed and requested == 1:
        raise ValueError("Embedded sketch schema 2 requires Part result version 2.")
    return 2 if requires_typed else (requested or 1)


def solved_line_wire(feature, source, scale=0.001, *, result_version=2):
    """Convert a strictly validated open sketch into bounded, oriented line display.

    Sorted stable IDs make the returned mapping explicit and deterministic. Never
    weld distinct authored points or infer connectivity from equal coordinates.
    Accepted near-unit WXYZ quaternions are normalized temporarily, as in OCCT;
    source seeds, expressions, endpoint orientation and workplane bytes are untouched.
    """
    if type(result_version) is not int or result_version not in (2, 3):
        raise ValueError("Solved line display requires explicit typed result 2 or 3.")
    if result_version == 3:
        validate_output_v3(feature, source)
    else:
        validate_output(feature, source)
    output = feature["output"]
    if (
        feature["status"] != "ok"
        or output.get("kind") != "sketch"
        or output["profile"]["state"] != "unavailable"
    ):
        raise ValueError("Solved line display requires a current typed open sketch.")
    if type(scale) not in (int, float) or not 0 < scale <= 1.7976931348623157e308:
        raise ValueError("Display scale must be finite and positive.")
    solved = feature["sketch"]["solved"]
    points = sorted(solved["points"], key=lambda point: point["id"])
    lines = sorted(solved["lines"], key=lambda line: line["id"])
    plane = solved["plane"]
    norm = math.sqrt(sum(value * value for value in plane["quaternion"]))
    w, x, y, z = (value / norm for value in plane["quaternion"])
    u_axis = (1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y))
    v_axis = (2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x))
    vertices = [
        tuple(
            math.fsum((plane["origin"][axis], point["u"] * u_axis[axis], point["v"] * v_axis[axis]))
            * scale
            for axis in range(3)
        )
        for point in points
    ]
    if not all(
        math.isfinite(value) and abs(value) <= _FLOAT32_MAX for p in vertices for value in p
    ):
        raise ValueError("Solved sketch display exceeds Blender's finite coordinate limits.")
    point_ids = [point["id"] for point in points]
    indices = {identifier: index for index, identifier in enumerate(point_ids)}
    return {
        "vertices": vertices,
        "triangles": [],
        "edges": [(indices[line["start"]], indices[line["end"]]) for line in lines],
        "point_ids": point_ids,
        "line_ids": [line["id"] for line in lines],
    }
