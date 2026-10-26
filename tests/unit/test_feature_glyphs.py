"""Family glyph policy is pure presentation and never replaces replay status."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "feature_glyphs_test", ROOT / "blender_addon/mechanical_cad_blender/feature_glyphs.py"
)
glyphs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(glyphs)


@pytest.mark.parametrize("kind,icon", [
    ("sketch_constrained", "CURVE_DATA"),
    ("sketch_face_circle", "CURVE_DATA"),
    ("extrude", "MOD_SOLIDIFY"),
    ("extrude_to_face", "MOD_SOLIDIFY"),
    ("cut", "MOD_BOOLEAN"),
    ("revolve", "MOD_SCREW"),
    ("fillet", "MOD_BEVEL"),
    ("mirror", "MOD_MIRROR"),
    ("circular_cut_pattern", "MOD_ARRAY"),
    ("import_step", "IMPORT"),
    ("future_operation", "FILE_BLANK"),
    ("sketch_future_operation", "FILE_BLANK"),
    ("", "FILE_BLANK"),
])
def test_known_families_and_neutral_unknowns(kind, icon):
    assert glyphs.feature_glyph(kind) == icon


def test_family_icons_never_claim_status():
    for icon in glyphs._GLYPHS.values():
        assert icon not in {"CHECKMARK", "ERROR", "CANCEL", "DOT", "HIDE_OFF"}
