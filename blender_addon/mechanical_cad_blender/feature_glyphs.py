"""Stable feature-family hints, independent of replay status or action authority."""

# Reuse the native glyphs of the corresponding authoring tools. These identify
# operation families, not a claim that geometry is current or valid.
_GLYPHS = {
    "datum_plane": "MESH_PLANE",
    "import_step": "IMPORT",
    "spur_gear": "PREFERENCES",
    "extrude": "MOD_SOLIDIFY",
    "extrude_through": "MOD_SOLIDIFY",
    "extrude_to_face": "MOD_SOLIDIFY",
    "extrude_symmetric": "MOD_SOLIDIFY",
    "cut": "MOD_BOOLEAN",
    "union": "MOD_BOOLEAN",
    "intersection": "MOD_BOOLEAN",
    "revolve": "MOD_SCREW",
    "fillet": "MOD_BEVEL",
    "chamfer": "MOD_BEVEL",
    "transform": "ORIENTATION_GLOBAL",
    "mirror": "MOD_MIRROR",
    "linear_pattern": "MOD_ARRAY",
    "circular_pattern": "MOD_ARRAY",
    "linear_cut_pattern": "MOD_ARRAY",
    "circular_cut_pattern": "MOD_ARRAY",
    "shell": "MOD_SOLIDIFY",
    "loft": "MOD_SKIN",
    "sweep": "MOD_CURVE",
}


def feature_glyph(kind):
    """Unknown kinds stay neutral; presentation must never enable an action."""
    if kind in {
        "sketch_constrained", "sketch_rectangle", "sketch_circle",
        "sketch_face_rectangle", "sketch_face_circle",
    }:
        return "CURVE_DATA"
    return _GLYPHS.get(kind, "FILE_BLANK")
