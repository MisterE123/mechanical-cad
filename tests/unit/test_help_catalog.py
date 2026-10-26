"""Pure help search and source wiring, without importing Blender or native CAD."""

import ast
import importlib.util
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon" / "mechanical_cad_blender"


def test_build_and_check_distinction_fits_first_help_page(catalog):
    title, paragraphs = catalog.HELP_TOPICS["verification.geometry"]
    assert title == "Build status and geometry checks"
    assert "not a Geometry Check report" in paragraphs[0]
    assert len(textwrap.wrap(paragraphs[0], width=64)) <= 2
    assert "no explicit Check report" in paragraphs[1]
    assert len(textwrap.wrap(paragraphs[1], width=64)) <= 2


@pytest.fixture
def catalog(monkeypatch):
    package = ModuleType("help_test_package")
    package.__path__ = [str(ADDON)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    for name in ("solid_help_topics", "help_topics", "help_catalog"):
        full_name = package.__name__ + "." + name
        spec = importlib.util.spec_from_file_location(full_name, ADDON / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, full_name, module)
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "query, expected",
    [
        ("USE solid EDGE", "sketch.projection"),
        ("facing normals", "assembly.faces"),
        ("unchecked contact", "assembly.faces"),
        ("guess override", "intent.suggestion"),
        ("pocket", "feature.cut"),
        ("watertight stl", "geometry.actions"),
        ("blocked timeout", "error.rebuild"),
        ("through-all", "feature.extrude_through"),
        ("sweep arc", "feature.sweep"),
        ("import step", "feature.import"),
        ("several sources", "sketch.projection"),
        ("circle line tangent", "sketch.position_relations"),
        ("diameter", "sketch.general"),
    ],
)
def test_common_action_and_error_search(catalog, query, expected):
    assert expected in catalog.search_topics(query)


def test_all_categories_are_populated_and_cover_topics_once(catalog):
    all_topics = catalog.search_topics()
    grouped = [
        topic for group in catalog.CATEGORIES for topic in catalog.search_topics(category=group)
    ]
    assert len(grouped) == len(set(grouped)) == len(all_topics)
    assert set(grouped) == set(catalog.HELP_TOPICS) - {"error.details"}
    assert all(catalog.search_topics(category=group) for group in catalog.CATEGORIES)
    assert catalog.search_topics("no_matching_help_word") == []
    assert catalog.search_topics("facing normals", "Sketch") == []
    assert catalog.search_topics("   ") == all_topics


def test_pages_are_bounded_and_preserve_all_explanations(catalog):
    for topic in catalog.search_topics():
        pages = catalog.topic_pages(topic)
        assert all(1 <= len(page) <= 6 for page in pages)
        assert all(len(line) <= 68 for page in pages for line in page)
        actual = " ".join(" ".join(line for page in pages for line in page).split())
        expected = " ".join(" ".join(catalog.HELP_TOPICS[topic][1]).split())
        assert actual == expected


def test_projection_help_describes_source_choice_and_preserves_limits(catalog):
    text = " ".join(catalog.HELP_TOPICS["sketch.projection"][1])
    assert "several earlier sketches and solids" in text
    assert "Source solid" in text and "Pick Edge" in text
    assert "without Finish or reopening" in text
    assert "each reference retains its own source" in text.lower()
    assert "source and analytic kind" in text
    assert "partial arcs" in text and "parallel" in text
    assert "not both" not in text and "one external source" not in text


def test_current_sketch_help_distinguishes_dimensions_arcs_and_solid_output(catalog):
    text = " ".join(catalog.HELP_TOPICS["sketch.general"][1])
    assert "Set Diameter" in text and "radius = diameter / 2" in text
    assert "Circle-line tangent is a separate relation" in text
    assert "infinite supporting line" in text
    assert "closed line/arc loops" in text.lower()
    assert "Length/Radius/Diameter (REF)" in text
    assert "Arbitrary relation retargeting remains unavailable" in text
    assert "Profile-only output is not a solid export or Assembly source" in text
    assert "Sketch on Face" in text and "unapplied repair proposal" in text


def test_browser_registered_and_available_in_all_workspace_roles():
    registration = ast.parse((ADDON / "registration.py").read_text())
    classes = next(
        node
        for node in registration.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CLASSES" for target in node.targets)
    )
    assert any(
        isinstance(node, ast.Name) and node.id == "MCAD_OT_help_browser"
        for node in ast.walk(classes.value)
    )
    source = (ADDON / "workspace_ui.py").read_text().split("class MCAD_MT_workspace(")[1]
    assert source.index('"mcad.help_browser"') < source.index('== "ASSEMBLY"')
    assert '"mcad.help_browser"' in (ADDON / "panels.py").read_text()


def test_unit_help_describes_typed_literals_without_expanding_formulas(catalog):
    text = " ".join(catalog.HELP_TOPICS["units"][1])
    assert "10 mm" in text and "1 rad" in text
    assert "Global project parameters remain untyped" in text
    assert "one number and one unit" in text
    assert "Counts, ratios, axes and quaternion" in text
    rectangle = " ".join(catalog.HELP_TOPICS["sketch.viewport_rectangle"][1])
    assert "60 mm or 6 cm" in rectangle
    assert "conversion are unsupported" not in rectangle


def test_reference_help_distinguishes_read_only_measurement_and_undo_limit(catalog):
    text = " ".join(catalog.HELP_TOPICS["sketch.reference_dimensions"][1])
    assert "(REF)" in text and "unsolved estimate" in text
    assert "never opens a value field" in text
    assert "Local Undo/Redo edits sketch geometry" in text
    assert ".mcad.json does not carry" in text
    assert "no reference distance" in text
    assert "sketch.reference_dimensions" in catalog.search_topics("reference measurement")
