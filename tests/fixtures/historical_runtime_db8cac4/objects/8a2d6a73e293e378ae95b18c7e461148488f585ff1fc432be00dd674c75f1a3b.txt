import json
from dataclasses import replace

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.model import Document, Feature, load_document, save_document


def test_document_round_trip_is_canonical_and_deterministic(plate, tmp_path):
    path = tmp_path / "plate.mcad.json"
    save_document(plate, path)
    loaded = load_document(path)
    assert loaded.to_json() == plate.to_json()
    assert loaded.content_hash == plate.content_hash
    assert path.read_text().endswith("\n")


def test_document_and_feature_snapshots_do_not_alias_mutable_input(plate):
    source = plate.to_dict()
    document = Document.from_dict(source)
    source["parameters"]["width"] = 99
    source["features"][0]["params"]["width"] = 99
    assert document.parameters["width"] == 40
    assert document.features[0].params["width"] == "width"
    with pytest.raises(TypeError):
        document.parameters["width"] = 1
    with pytest.raises(TypeError):
        document.features[0].params["width"] = 1


def test_parameter_edit_preserves_old_document_and_feature_ids(plate):
    edited = plate.with_parameter("width", 60)
    assert plate.parameters["width"] == 40
    assert edited.parameters["width"] == 60
    assert edited.content_hash != plate.content_hash
    assert [f.id for f in edited.features] == [f.id for f in plate.features]


def test_feature_order_is_not_dependency_order(plate):
    data = plate.to_dict()
    data["features"].reverse()
    document = Document.from_dict(data)
    order = [f.id for f in document.topological_features()]
    assert order.index("profile") < order.index("pad") < order.index("body")
    assert order.index("hole_profile") < order.index("hole_tool") < order.index("body")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("schema_version", 3, "unsupported_schema"),
        ("schema_version", True, "unsupported_schema"),
        ("units", "m", "unsupported_units"),
        ("active_feature", "absent", "missing_active_feature"),
        ("active_feature", [], "invalid_document"),
        ("active_feature", {}, "invalid_document"),
        ("active_feature", 2, "invalid_document"),
        ("features", {}, "invalid_document"),
        ("parameters", [], "invalid_document"),
        ("name", "", "invalid_document"),
    ],
)
def test_document_rejects_invalid_header(plate, field, value, code):
    data = plate.to_dict()
    data[field] = value
    with pytest.raises(CADException) as error:
        Document.from_dict(data)
    assert error.value.code == code


def test_duplicate_feature_ids_rejected(plate):
    data = plate.to_dict()
    data["features"].append(data["features"][0])
    with pytest.raises(CADException) as error:
        Document.from_dict(data)
    assert error.value.code == "duplicate_feature"


def test_dangling_reference_rejected(plate):
    data = plate.to_dict()
    data["features"][1]["inputs"]["profile"] = "missing"
    with pytest.raises(CADException) as error:
        Document.from_dict(data)
    assert error.value.code == "missing_reference"


def test_feature_cycle_rejected(plate):
    data = plate.to_dict()
    data["features"][-1]["inputs"]["base"] = "body"
    with pytest.raises(CADException) as error:
        Document.from_dict(data)
    assert error.value.code == "feature_cycle"


def test_wrong_reference_type_rejected(plate):
    data = plate.to_dict()
    data["features"][1]["inputs"]["profile"] = "hole_tool"
    with pytest.raises(CADException) as error:
        Document.from_dict(data)
    assert error.value.code == "input_type_mismatch"


@pytest.mark.parametrize("name", ["pi", "sqrt", "two words", "4width", "a" * 65])
def test_invalid_parameter_names_rejected(plate, name):
    data = plate.to_dict()
    data["parameters"][name] = 2
    with pytest.raises(CADException):
        Document.from_dict(data)


@pytest.mark.parametrize("text", ['{"x":NaN}', "not json", "{}", "[]", "null"])
def test_invalid_json_and_documents_rejected(text):
    with pytest.raises(CADException):
        Document.from_json(text)


def test_missing_required_dimension_rejected():
    with pytest.raises(CADException):
        Feature.from_dict({"id": "profile", "kind": "sketch_circle"})


def test_unknown_features_and_fields_fail_closed(plate):
    data = plate.to_dict()
    data["features"][0]["kind"] = "python_script"
    with pytest.raises(CADException) as error:
        Document.from_dict(data)
    assert error.value.code == "unsupported_feature"
    data = plate.to_dict()
    data["execute"] = "ignored?"
    with pytest.raises(CADException):
        Document.from_dict(data)


def test_remove_refuses_dependencies_and_can_remove_leaf(plate):
    with pytest.raises(CADException) as error:
        plate.without_feature("profile")
    assert error.value.code == "feature_in_use"
    changed = plate.without_feature("body")
    assert len(changed.features) == 4
    assert changed.active_feature == "hole_tool"


def test_feature_replacement_preserves_identity(plate):
    changed = plate.with_feature(
        Feature.from_dict(
            {"id": "profile", "kind": "sketch_rectangle", "params": {"width": 20, "height": 15}}
        )
    )
    assert len(changed.features) == len(plate.features)
    assert changed.features[0].params["width"] == 20
    assert plate.features[0].params["width"] == "width"


def test_direct_constructor_revalidated_before_saving(plate, tmp_path):
    invalid = replace(plate, units="inch")
    with pytest.raises(CADException):
        save_document(invalid, tmp_path / "no.mcad.json")
    assert not (tmp_path / "no.mcad.json").exists()


def test_failed_atomic_replace_preserves_existing_document(plate, tmp_path, monkeypatch):
    path = tmp_path / "plate.mcad.json"
    save_document(plate, path)
    old = path.read_text()

    def fail(*args):
        raise OSError("simulated interruption")

    monkeypatch.setattr("mechanical_cad.model.os.replace", fail)
    with pytest.raises(OSError):
        save_document(plate.with_parameter("width", 50), path)
    assert path.read_text() == old
    assert list(tmp_path.iterdir()) == [path]


def test_content_hash_matches_semantic_canonical_serialization(plate):
    data = json.loads(plate.to_json())
    assert Document.from_dict(data).content_hash == plate.content_hash


def test_duplicate_json_keys_are_rejected(plate):
    ambiguous = plate.to_json().replace('"width": 40', '"width": 40, "width": 99')
    with pytest.raises(CADException, match="Duplicate JSON key"):
        Document.from_json(ambiguous)
