"""Semantic glyph identity, safe native encoding and deterministic menu artwork."""

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


glyphs = load("tool_glyphs", ADDON / "tool_glyphs.py")
validator = load("palette_shapes", ADDON / "palette_shapes.py")


@pytest.mark.parametrize("action", glyphs.STROKES)
def test_native_glyph_is_bounded_counterclockwise_and_available_in_both_themes(action):
    payload = glyphs.shape(action)
    validator._validate_payload(payload)
    assert type(payload) is bytes
    for theme in ("dark", "light"):
        image = ADDON / "assets/tool_glyphs" / theme / f"{action}.png"
        assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_distinct_commands_never_share_the_same_custom_glyph():
    shapes = [glyphs.shape(action) for action in glyphs.STROKES]
    assert len(set(shapes)) == len(shapes)


def test_advanced_routes_share_only_the_same_underlying_operation():
    for alias, action in glyphs.ALIASES.items():
        assert glyphs.shape(alias) == glyphs.shape(action)
    assert glyphs.shape("not_an_action") is None


def test_former_collision_pairs_have_different_geometry():
    for left, right in (
        ("REVERSE", "EXTEND"),
        ("LINE", "EXTEND"),
        ("LINE", "DIMENSION"),
        ("SKETCH_CHECK", "APPLY_LINE_EDIT"),
        ("FILLET", "CHAMFER"),
        ("UNION", "CUT"),
        ("UNION", "INTERSECTION"),
        ("LINEAR_PATTERN", "CIRCULAR_PATTERN"),
        ("LINEAR_PATTERN", "LINEAR_CUT_PATTERN"),
        ("CIRCULAR_PATTERN", "CIRCULAR_CUT_PATTERN"),
        ("NEW_FACE_SKETCH", "FACE_RECTANGLE"),
        ("CONCENTRIC", "DIAMETER"),
        ("TANGENT", "CIRCLE_TANGENT"),
        ("POINT_ON_LINE", "MIDPOINT"),
    ):
        assert glyphs.shape(left) != glyphs.shape(right)


def test_dimension_tooltip_describes_current_gestures_and_numeric_input():
    tree = ast.parse((ADDON / "workspace_ui.py").read_text())
    actions = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_ACTIONS" for target in node.targets)
    )
    tooltip = actions["DIMENSION"][4]
    for gesture in (
        "Press D",
        "line interior",
        "circle/arc perimeter",
        "two points",
        "straight-line distance",
        "point/center",
        "straight reference line",
        "unsigned perpendicular offset",
        "Place the label",
        "millimetre value",
        "named formula",
        "Double-click",
    ):
        assert gesture in tooltip
    assert "Circles use radius only" not in tooltip


@pytest.mark.parametrize("action", ("LOFT", "SWEEP", "HOLE", "SHELL"))
def test_original_svg_exports_match_runtime_polygons_and_manifest(action):
    import hashlib
    import json
    import xml.etree.ElementTree as ET

    root = ADDON / "assets/tool_glyphs"
    manifest = json.loads((root / "design_manifest.json").read_text())
    entry = next(item for item in manifest["assets"] if item["action"] == action)
    assert entry["license"] == "GPL-3.0-or-later"
    assert entry["author"] == "Mechanical CAD contributors"
    assert (root / entry["source"]).resolve() == (ADDON / "tool_glyphs.py").resolve()
    for relative, expected in entry["files"].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected
    svg = ET.parse(root / "svg" / f"{action}.svg").getroot()
    assert svg.attrib["viewBox"] == "0 0 24 24"
    group = svg.find("{http://www.w3.org/2000/svg}g")
    assert group.attrib == {"fill": "currentColor"}
    drawn = group.findall("{http://www.w3.org/2000/svg}polygon")
    expected = glyphs.polygons(action)
    assert len(drawn) == len(expected)
    for node, polygon in zip(drawn, expected, strict=True):
        points = [tuple(map(float, pair.split(","))) for pair in node.attrib["points"].split()]
        for actual, (x, y) in zip(points, polygon, strict=True):
            assert actual == pytest.approx((x, 24 - y), abs=0.000001)


def test_focused_designs_do_not_alias_different_operations():
    for left, right in (("LOFT", "SWEEP"), ("HOLE", "SHELL"), ("HOLE", "FACE_CIRCLE")):
        assert glyphs.shape(left) != glyphs.shape(right)
