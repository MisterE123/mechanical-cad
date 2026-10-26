"""Resolve accepted assembly tessellation to semantic planar support, never save indices."""

from .bridge import BridgeError


def resolve_face(part, index):
    mesh = part.get("mesh") or {}
    ids = mesh.get("triangle_face_ids", [])
    if (
        type(index) is not int
        or not 0 <= index < len(ids)
        or len(ids) != len(mesh.get("triangles", []))
    ):
        raise BridgeError("No exact face mapping under the pointer. Rebuild Assembly.")
    matches = [f for f in part.get("topology", []) if f.get("id") == ids[index]]
    if not ids[index] or len(matches) != 1:
        raise BridgeError(
            "This face has no unambiguous CAD identity. Use literal placement instead."
        )
    face = matches[0]
    if face.get("kind") != "face" or face.get("provenance", {}).get("semantic_status") != "stable":
        raise BridgeError(
            "This face has no stable semantic identity. Use literal placement instead."
        )
    if face.get("signature", {}).get("surface") != "plane":
        raise BridgeError("Choose a planar face, not a curved surface.")
    return face["id"]
