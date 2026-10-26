"""Typed sketches opt into schema 2 without changing schema-1 history/hash."""

import copy
from pathlib import Path

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.model import Document, Feature, load_document

ROOT = Path(__file__).resolve().parents[2]


def constrained_document():
    return load_document(ROOT / "examples" / "constrained_plate.mcad.json")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("drilled_plate", "777d634152cce17a17247b347e433b311410ee2c67fcc70927176e02d8ac59e9"),
        ("parameter_chain", "c1e2022c53181e464b61eca691ab48dadf33fe3e7326b6ae7da4da295b604ace"),
    ],
)
def test_schema_one_matches_delivered_689a414_hash(name, expected):
    document = load_document(ROOT / "examples" / f"{name}.mcad.json")
    assert document.schema_version == 1
    assert document.content_hash == expected
    assert "sketch" not in document.features[0].to_dict()


def test_explicit_migration_preserves_all_feature_intent_and_old_snapshot(plate):
    before = plate.to_json()
    migrated = plate.migrate_to_v2()
    expected = plate.to_dict()
    expected["schema_version"] = 2
    assert migrated.to_dict() == expected
    assert migrated.migrate_to_v2() is migrated
    assert migrated.content_hash != plate.content_hash
    assert plate.to_json() == before


def test_schema_two_roundtrip_keeps_typed_payload_and_driving_expressions():
    document = constrained_document()
    loaded = Document.from_json(document.to_json())
    assert loaded.to_json() == document.to_json()
    dimensions = {c.id: c.value for c in loaded.features[0].sketch.constraints}
    assert dimensions["width"] == "width"
    assert dimensions["height"] == "depth"
    source = document.to_dict()
    original = copy.deepcopy(source)
    Document.from_dict(source)
    assert source == original


def test_constrained_feature_requires_explicit_schema_migration():
    data = constrained_document().to_dict()
    data["schema_version"] = 1
    with pytest.raises(CADException) as raised:
        Document.from_dict(data)
    assert raised.value.code == "migration_required"


def test_existing_feature_cannot_hide_sketch_payload(plate):
    data = plate.to_dict()
    data["features"][0]["sketch"] = constrained_document().features[0].sketch.to_dict()
    with pytest.raises(CADException, match="Only constrained sketch"):
        Document.from_dict(data)


@pytest.mark.parametrize("change", ["missing", "unknown_nested", "wrong_type", "wrong_params"])
def test_invalid_typed_sketch_feature_fails_closed(change):
    data = constrained_document().to_dict()
    feature = data["features"][0]
    if change == "missing":
        del feature["sketch"]
    elif change == "unknown_nested":
        feature["sketch"]["run_python"] = "not executable"
    elif change == "wrong_type":
        feature["sketch"] = "opaque JSON is not a typed record"
    else:
        feature["params"]["arbitrary_payload"] = "bad"
    with pytest.raises(CADException):
        Document.from_dict(data)


def test_direct_feature_constructor_rejects_untyped_payload():
    feature = Feature("sketch", "sketch_constrained", "Sketch", sketch={})
    with pytest.raises(CADException, match="typed SketchDefinition"):
        feature.to_dict()


def test_reordering_sketch_records_has_same_canonical_hash():
    document = constrained_document()
    data = document.to_dict()
    for field in ("points", "lines", "constraints"):
        data["features"][0]["sketch"][field].reverse()
    assert Document.from_dict(data).content_hash == document.content_hash
