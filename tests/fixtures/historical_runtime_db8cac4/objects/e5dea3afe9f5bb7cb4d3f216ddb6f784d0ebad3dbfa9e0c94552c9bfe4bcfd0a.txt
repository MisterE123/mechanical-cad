"""Pinned native button glyphs; pure Python, no Blender imports or UI changes.

Only ``load_shape(action)`` produces application-ready bytes. Unknown actions or
missing/corrupt resources return None so a caller can retain its PNG/native icon.
The manifest is pinned in code; it is not an editable source of trusted hashes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

_ROOT = Path(__file__).resolve().parent / "assets" / "palette_shapes"
_MANIFEST_SHA256 = "7546a6c97fdd2b0d51eb4841ce84572a4a5f0810bfb9cc48da68682bd15a81a3"
_MAX_MANIFEST_BYTES = 32768
_MAX_SOURCE_BYTES = 8192
_MAX_PAYLOAD_BYTES = 2048
_MAX_POLYGONS = 192
_MAX_POLYGON_VERTICES = 8
_MAX_VERTICES = 576
_FILES = MappingProxyType(
    {
        "NEW": "sketch_rectangle",
        "EDIT": "sketch_rectangle",
        "DIMENSIONS": "sketch_dimension",
        "FINISH": "edit_apply",
        "CANCEL": "edit_cancel",
        "EXTRUDE": "feature_extrude",
        "CUT": "feature_cut",
        "CHECK": "verify_model",
        "EXPORT": "file_export",
    }
)
ACTIONS = tuple(_FILES)


def _read_verified(path: Path, expected: str, budget: int) -> bytes:
    # Bounded read even if a resource is replaced between stat/open/read.
    with path.open("rb") as stream:
        data = stream.read(budget + 1)
    if len(data) > budget or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Glyph resource exceeds budget or has a different hash")
    return data


def _validate_payload(data: bytes) -> dict:
    """Check decoder framing and bounded geometry; NOT a public trust boundary.

    Coordinates are unsigned byte pairs (0..255). The C++ decoder looks ahead
    one pair and consumes a repeated FINAL vertex as the polygon terminator.
    Repeating the first vertex instead is neither closure nor a valid sentinel.
    """
    if type(data) is not bytes or not 8 <= len(data) <= _MAX_PAYLOAD_BYTES or len(data) % 2:
        raise ValueError("Expected bounded, immutable uint8 XY pairs")
    cursor = polygons = vertices = area = 0
    xmin = ymin = 255
    xmax = ymax = 0
    while cursor < len(data):
        polygons += 1
        if polygons > _MAX_POLYGONS:
            raise ValueError("Too many polygons")
        polygon = []
        while True:
            if cursor + 4 > len(data):
                raise ValueError("Missing final-vertex sentinel")
            point = (data[cursor], data[cursor + 1])
            polygon.append(point)
            cursor += 2
            if len(polygon) > _MAX_POLYGON_VERTICES:
                raise ValueError("Too many polygon vertices")
            if data[cursor : cursor + 2] == bytes(point):
                cursor += 2
                break
        if len(polygon) < 3 or len(set(polygon)) != len(polygon):
            raise ValueError("Polygon needs at least three distinct vertices")
        signed_area = sum(
            a[0] * b[1] - b[0] * a[1]
            for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True)
        )
        if signed_area <= 0:
            raise ValueError("Polygon must have nonzero counterclockwise area")
        vertices += len(polygon)
        if vertices > _MAX_VERTICES:
            raise ValueError("Too many total vertices")
        area += signed_area
        for x, y in polygon:
            xmin, ymin = min(xmin, x), min(ymin, y)
            xmax, ymax = max(xmax, x), max(ymax, y)
    return {
        "bytes": len(data),
        "encoded_polygons": polygons,
        "encoded_vertices": vertices,
        "signed_area2": area,
        "bounds": [xmin, ymin, xmax, ymax],
    }


def load_shape(action: str) -> bytes | None:
    """Return this allowlisted palette action's validated shape, or None.

    Revalidate on every call, including source SVG identity. No cache can mask a
    missing/corrupt replacement. Call during gizmo creation, not every draw.
    Failure is local to the requested glyph; this function never sets an icon,
    creates a gizmo, imports bpy, converts SVGs, or changes action availability.
    """
    if not isinstance(action, str) or action not in _FILES:
        return None
    name = _FILES[action]
    try:
        manifest = json.loads(
            _read_verified(_ROOT / "manifest.json", _MANIFEST_SHA256, _MAX_MANIFEST_BYTES)
        )
        if manifest["schema_version"] != 1 or manifest["actions"] != dict(_FILES):
            return None
        asset = manifest["assets"][name]
        # Paths are constructed from code-owned names, never caller/manifest paths.
        _read_verified(
            _ROOT.parent / "icons" / "svg" / f"{name}.svg",
            asset["source_sha256"],
            _MAX_SOURCE_BYTES,
        )
        data = _read_verified(_ROOT / f"{name}.bin", asset["shape_sha256"], _MAX_PAYLOAD_BYTES)
        if any(value != asset[key] for key, value in _validate_payload(data).items()):
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None
