"""Scene-only annotation persistence cannot rewrite canonical modeling intent."""

import copy
import importlib
import json
import math
import subprocess
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mechanical_cad.model import Document

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_sketch_annotation_store_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
s = importlib.import_module(PACKAGE + ".sketch_annotation_store")


def sketch():
    return {
        "schema_version": 2,
        "id": "embedded_sketch",
        "units": "mm",
        "plane": {"id": "plane", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [
            {"id": "p", "u": 0, "v": 0},
            {"id": "q", "u": 3, "v": 4},
            {"id": "center", "u": 12, "v": 8},
        ],
        "lines": [{"id": "line", "start": "p", "end": "q"}],
        "circles": [{"id": "circle", "center": "center", "radius": 4.125}],
        "constraints": [
            {"id": "length", "kind": "distance", "refs": ["p", "q"], "value": "5  + 0 "},
            {"id": "radius", "kind": "radius", "refs": ["circle"], "value": "radius  + 0 "},
        ],
    }


def placement(kind="distance", offset=None):
    return {
        "kind": kind,
        "refs": ["p", "q"] if kind == "distance" else ["circle"],
        "display": kind,
        "offset": [2.123456789123456, -0.0] if offset is None else offset,
    }


def placements():
    return {"length": placement(), "radius": placement("radius", [12, -4.125])}


def envelope(documents=None):
    return {
        "schema_version": s.VERSION,
        "kind": s.KIND,
        "documents": {} if documents is None else documents,
    }


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_empty_store_is_explicit_and_validated_even_when_no_placements_exist():
    assert s.validate("") is None
    assert s.validate(compact(envelope())) is None
    result = s.annotations_for("", "Part", "sketch_feature", sketch())
    assert result.annotations == result.unavailable == result.all_annotations == {}
    assert s.replace_annotations("", "Part", "sketch_feature", {}) == compact(envelope())
    malformed = sketch()
    malformed["schema_version"] = 99
    with pytest.raises(s.AnnotationStoreError, match="unsupported sketch schema"):
        s.annotations_for("", "Part", "sketch_feature", malformed)


def test_two_parts_two_features_preserve_unrelated_records_and_exact_ids():
    raw = ""
    originals = {}
    for document in ("Part A 🛠", "Part B"):
        for feature in ("profile", "other_profile"):
            value = placements()
            value["length"]["offset"] = [len(originals), 1]
            originals[(document, feature)] = copy.deepcopy(value)
            raw = s.replace_annotations(raw, document, feature, value)
    before = json.loads(raw)
    replacement = placements()
    replacement["length"]["offset"] = [-15, 28]
    updated = s.replace_annotations(raw, "Part A 🛠", "profile", replacement)
    assert json.loads(raw) == before
    for key, original in originals.items():
        lookup = s.annotations_for(updated, *key, sketch())
        assert lookup.annotations == (replacement if key == ("Part A 🛠", "profile") else original)
        assert not lookup.unavailable
    assert s.annotations_for(updated, "Part A", "profile", sketch()).all_annotations == {}
    assert s.annotations_for(updated, "Part A 🛠", "embedded_sketch", sketch()).annotations == {}


def test_deterministic_exact_roundtrip_without_numeric_or_identifier_coercion():
    original = placements()
    raw = s.replace_annotations("", " Part 🛠 ", "feature.1", original)
    result = s.annotations_for(raw, " Part 🛠 ", "feature.1", sketch())
    assert s.replace_annotations(raw, " Part 🛠 ", "feature.1", result.all_annotations) == raw
    assert result.annotations == original
    assert type(result.annotations["radius"]["offset"][0]) is int
    assert math.copysign(1, result.annotations["length"]["offset"][1]) == -1
    assert " Part 🛠 " in raw


def test_result_and_conflicts_are_frozen_and_every_accessor_is_detached():
    original = placements()
    raw = s.replace_annotations("", "Part", "feature", original)
    current = sketch()
    current["constraints"].pop()
    result = s.annotations_for(raw, "Part", "feature", current)
    original["length"]["offset"][0] = 99
    result.annotations["length"]["refs"].clear()
    result.all_annotations["radius"]["offset"].clear()
    conflict = result.unavailable["radius"]
    conflict.binding["offset"].clear()
    result.unavailable.clear()
    current["constraints"].clear()
    assert result.annotations == {"length": placement()}
    assert result.all_annotations == placements()
    assert conflict.binding == placements()["radius"]
    with pytest.raises(FrozenInstanceError):
        result._states = ()
    with pytest.raises(FrozenInstanceError):
        conflict.state = "available"


def test_missing_relation_equal_geometry_new_id_and_exact_restoration():
    raw = s.replace_annotations("", "Part", "feature", placements())
    current = sketch()
    current["constraints"][0]["id"] = "replacement_length"
    result = s.annotations_for(raw, "Part", "feature", current)
    assert set(result.annotations) == {"radius"}
    assert result.unavailable["length"].state == "missing"
    assert result.unavailable["length"].binding == placement()
    assert result.all_annotations == placements()
    assert s.replace_annotations(raw, "Part", "feature", result.all_annotations) == raw
    restored = s.annotations_for(raw, "Part", "feature", sketch())
    assert restored.annotations == placements()
    assert not restored.unavailable


@pytest.mark.parametrize("change", ["reversed_refs", "different_refs", "kind", "entity_kind"])
def test_rebound_signatures_are_conflicts_without_remapping(change):
    raw = s.replace_annotations("", "Part", "feature", placements())
    current = sketch()
    relation = current["constraints"][0]
    if change == "reversed_refs":
        relation["refs"].reverse()
    elif change == "different_refs":
        relation["refs"] = ["p", "center"]
    elif change == "kind":
        relation.update(kind="radius", refs=["circle"], value=5)
    else:
        current["constraints"].pop(0)
        current["points"].append({"id": "length", "u": 3, "v": 4})
    result = s.annotations_for(raw, "Part", "feature", current)
    assert result.unavailable["length"].state == "changed"
    assert result.unavailable["length"].binding == placement()
    assert set(result.annotations) == {"radius"}
    assert result.all_annotations == placements()


def test_only_explicit_replacement_drops_unavailable_records_or_removes_feature():
    raw = s.replace_annotations("", "Part", "feature", placements())
    raw = s.replace_annotations(raw, "Part", "other", placements())
    raw = s.replace_annotations(raw, "Other Part", "feature", placements())
    current = sketch()
    current["constraints"].pop()
    result = s.annotations_for(raw, "Part", "feature", current)
    retained = result.all_annotations
    retained["length"]["offset"] = [30, -40]
    retained_raw = s.replace_annotations(raw, "Part", "feature", retained)
    assert set(s.annotations_for(retained_raw, "Part", "feature", sketch()).annotations) == {
        "length",
        "radius",
    }
    explicit_drop = s.replace_annotations(raw, "Part", "feature", result.annotations)
    assert set(s.annotations_for(explicit_drop, "Part", "feature", sketch()).annotations) == {
        "length"
    }
    removed = s.replace_annotations(raw, "Part", "feature", {})
    assert json.loads(removed)["documents"]["Part"] == {"other": placements()}
    removed = s.replace_annotations(removed, "Part", "other", {})
    assert json.loads(removed)["documents"] == {"Other Part": {"feature": placements()}}


def test_source_hash_geometry_literal_expressions_and_command_history_are_independent():
    d = importlib.import_module(PACKAGE + ".general_sketch_draft")
    base = Document.from_dict(
        {
            "schema_version": 2,
            "id": "Part",
            "name": "Test",
            "units": "mm",
            "parameters": {"radius": "4 + 0.125"},
            "features": [
                {
                    "id": "feature",
                    "kind": "sketch_constrained",
                    "label": "Profile",
                    "params": {},
                    "inputs": {},
                    "sketch": sketch(),
                }
            ],
            "active_feature": "feature",
        }
    )
    canonical, source_hash = base.to_json(), base.content_hash
    draft = d.GeneralSketchDraft(canonical, "feature", True)
    checkpoint = draft.checkpoint_payload()
    source = draft.sketch
    original = copy.deepcopy(source)
    raw = s.replace_annotations("", base.id, "feature", placements())
    edited = s.annotations_for(raw, base.id, "feature", source).all_annotations
    edited["length"]["offset"] = [-1e6, 1e6]
    raw = s.replace_annotations(raw, base.id, "feature", edited)
    assert source == original
    assert draft.checkpoint_payload() == checkpoint
    assert base.to_json() == canonical and base.content_hash == source_hash
    assert source["constraints"][0]["value"] == "5  + 0 "
    assert source["constraints"][1]["value"] == "radius  + 0 "
    assert not any(key in raw for key in ("value", "target", "source_hash", "journal", "points"))
    # Valid geometry/expression edits do not invalidate an unchanged ID signature.
    current = copy.deepcopy(source)
    current["points"][1]["u"] = 100
    current["constraints"][0]["value"] = "3 * 7"
    current["circles"][0]["radius"] = 12
    current["plane"]["origin"] = [4, 5, 6]
    assert s.annotations_for(raw, base.id, "feature", current).annotations == edited


def test_structural_v1_sketches_are_supported_without_implicit_migration():
    current = sketch()
    current["schema_version"] = 1
    current.pop("circles")
    current["constraints"].pop()
    before = copy.deepcopy(current)
    raw = s.replace_annotations("", "Part", "feature", {"length": placement()})
    assert s.annotations_for(raw, "Part", "feature", current).annotations == {"length": placement()}
    assert current == before


@pytest.mark.parametrize(
    "raw",
    [
        None,
        b"",
        " ",
        "null",
        "[]",
        "{}",
        "{",
        "[" * 33 + "]" * 33,
        '{"schema_version":1,"schema_version":1,"kind":"sketch_annotation_layout","documents":{}}',
        '{"schema_version":NaN,"kind":"sketch_annotation_layout","documents":{}}',
        '{"schema_version":Infinity,"kind":"sketch_annotation_layout","documents":{}}',
        '{"schema_version":1e999,"kind":"sketch_annotation_layout","documents":{}}',
        '{"schema_version":' + "1" * 129 + ',"kind":"sketch_annotation_layout","documents":{}}',
        '{"schema_version":1,"kind":"sketch_annotation_layout","documents":{"\\ud800":{}}}',
        '{"schema_version":1,"kind":"sketch_annotation_layout","documents":{"\ud800":{}}}',
    ],
)
def test_bad_raw_store_is_typed_and_atomic_for_read_and_write(raw):
    before = raw
    for operation in (
        lambda: s.validate(raw),
        lambda: s.annotations_for(raw, "Part", "feature", sketch()),
        lambda: s.replace_annotations(raw, "Part", "feature", placements()),
    ):
        with pytest.raises(s.AnnotationStoreError, match="retain the original text"):
            operation()
    assert raw == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 3),
        ("schema_version", True),
        ("schema_version", 1.0),
        ("kind", "general"),
        ("extra", 0),
        ("documents", []),
    ],
)
def test_unknown_envelope_fields_and_versions_are_not_migrated(field, value):
    data = envelope()
    data[field] = value
    raw = compact(data)
    with pytest.raises(s.AnnotationStoreError):
        s.replace_annotations(raw, "Part", "feature", placements())
    assert compact(data) == raw


@pytest.mark.parametrize("identifier", [None, True, 1, "", "x" * 129, "\ud800"])
def test_document_ids_are_strict(identifier):
    with pytest.raises(s.AnnotationStoreError):
        s.replace_annotations("", identifier, "feature", placements())


@pytest.mark.parametrize("identifier", [None, True, 1, "", "x" * 129, "has space", "é", "\ud800"])
def test_feature_ids_are_strict(identifier):
    with pytest.raises(s.AnnotationStoreError):
        s.replace_annotations("", "Part", identifier, placements())


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "angle"),
        ("kind", []),
        ("display", "diameter"),
        ("display", True),
        ("refs", []),
        ("refs", ["p"]),
        ("refs", ["p", "q", "center"]),
        ("refs", ["p", "p"]),
        ("refs", ["length", "q"]),
        ("refs", ["p", "bad ID"]),
        ("refs", ["p", "\ud800"]),
        ("refs", ("p", "q")),
        ("offset", []),
        ("offset", [0]),
        ("offset", [0, 0, 0]),
        ("offset", (0, 0)),
        ("offset", [True, 0]),
        ("offset", ["2", 0]),
        ("offset", [float("nan"), 0]),
        ("offset", [float("inf"), 0]),
        ("offset", [-float("inf"), 0]),
        ("offset", [1_000_001, 0]),
        ("offset", [-1_000_001, 0]),
        ("offset", [10**10000, 0]),
        ("geometry", {}),
        ("expression", "4 + 1"),
    ],
)
def test_malformed_replacements_fail_atomically(field, value):
    raw = s.replace_annotations("", "Part", "feature", placements())
    changed = placements()
    changed["length"][field] = value
    with pytest.raises(s.AnnotationStoreError):
        s.replace_annotations(raw, "Part", "feature", changed)
    assert s.annotations_for(raw, "Part", "feature", sketch()).all_annotations == placements()


@pytest.mark.parametrize("field", ["kind", "refs", "display", "offset"])
def test_missing_binding_fields_are_not_defaulted(field):
    changed = placements()
    del changed["length"][field]
    with pytest.raises(s.AnnotationStoreError):
        s.replace_annotations("", "Part", "feature", changed)


def test_duplicate_nested_keys_are_rejected_even_outside_the_requested_feature():
    raw = compact(envelope({"Other Part": {"feature": {"length": placement()}}}))
    for token in ('"Other Part":', '"feature":', '"length":', '"kind":'):
        # The duplicate has a different value; accepting last-wins would lose data.
        duplicated = raw.replace(token, token + "null," + token, 1)
        with pytest.raises(s.AnnotationStoreError, match="Duplicate"):
            s.replace_annotations(duplicated, "Part", "feature", placements())


def test_bad_unrelated_metadata_blocks_writes_without_discarding_it():
    data = envelope({"Other Part": {"feature": {"length": placement()}}})
    data["documents"]["Other Part"]["feature"]["length"]["unknown"] = "keep me"
    raw = compact(data)
    with pytest.raises(s.AnnotationStoreError):
        s.replace_annotations(raw, "Part", "feature", placements())
    assert "keep me" in raw
    with pytest.raises(s.AnnotationStoreError):
        s.validate(raw)


@pytest.mark.parametrize("hazard", ["record_cycle", "refs_cycle", "offset_cycle", "aliases", "dag"])
def test_cycles_and_shared_container_hazards_are_rejected_before_encoding(hazard, monkeypatch):
    value = {"length": placement()}
    if hazard == "record_cycle":
        value["length"] = value
    elif hazard == "refs_cycle":
        value["length"]["refs"] = [value, "q"]
    elif hazard == "offset_cycle":
        value["length"]["offset"] = [value, 0]
    elif hazard == "aliases":
        value["other_length"] = value["length"]
    else:
        huge = [0]
        for _ in range(80):
            huge = [huge, huge]
        value["length"]["offset"] = huge
    monkeypatch.setattr(s, "_json", lambda _: pytest.fail("Unsafe object reached JSON encoding"))
    with pytest.raises(s.AnnotationStoreError):
        s.replace_annotations("", "Part", "feature", value)


def test_shared_reference_lists_are_rejected_even_when_their_values_are_valid():
    one, two = placement(), placement()
    two["refs"] = one["refs"]
    with pytest.raises(s.AnnotationStoreError, match="aliased"):
        s.replace_annotations("", "Part", "feature", {"one": one, "two": two})


@pytest.mark.parametrize("count", [s.MAX_DOCUMENTS, s.MAX_DOCUMENTS + 1])
def test_document_count_limit_without_eviction(count):
    raw = compact(envelope({f"part_{index}": {} for index in range(count)}))
    if count == s.MAX_DOCUMENTS:
        updated = s.replace_annotations(raw, "part_0", "feature", placements())
        assert len(json.loads(updated)["documents"]) == count
        with pytest.raises(s.AnnotationStoreError, match="128"):
            s.replace_annotations(raw, "new_part", "feature", placements())
    else:
        with pytest.raises(s.AnnotationStoreError, match="128"):
            s.annotations_for(raw, "part_0", "feature", sketch())


def test_per_document_feature_count_limit_without_eviction():
    features = {f"feature_{index}": {} for index in range(s.MAX_FEATURES_PER_DOCUMENT)}
    raw = compact(envelope({"Part": features}))
    assert s.replace_annotations(raw, "Part", "feature_0", placements())
    with pytest.raises(s.AnnotationStoreError, match="256"):
        s.replace_annotations(raw, "Part", "new_feature", placements())
    assert json.loads(raw)["documents"]["Part"] == features


def test_aggregate_feature_count_limit_without_eviction():
    documents = {
        f"part_{index}": {f"feature_{item}": {} for item in range(s.MAX_FEATURES_PER_DOCUMENT)}
        for index in range(s.MAX_FEATURES // s.MAX_FEATURES_PER_DOCUMENT)
    }
    raw = compact(envelope(documents))
    assert s.replace_annotations(raw, "part_0", "feature_0", placements())
    with pytest.raises(s.AnnotationStoreError, match="1024"):
        s.replace_annotations(raw, "new_part", "new_feature", placements())


def test_per_feature_and_aggregate_annotation_limits_without_eviction():
    full = {f"r_{index}": placement() for index in range(s.MAX_ANNOTATIONS_PER_FEATURE)}
    raw = s.replace_annotations("", "Part", "feature_0", full)
    too_many = {**full, "extra": placement()}
    with pytest.raises(s.AnnotationStoreError, match="512"):
        s.replace_annotations(raw, "Part", "feature_0", too_many)
    for index in range(1, s.MAX_ANNOTATIONS // s.MAX_ANNOTATIONS_PER_FEATURE):
        raw = s.replace_annotations(raw, "Part", f"feature_{index}", full)
    assert sum(len(items) for items in json.loads(raw)["documents"]["Part"].values()) == 4096
    with pytest.raises(s.AnnotationStoreError, match="4096"):
        s.replace_annotations(raw, "Part", "extra", {"length": placement()})


def test_byte_limit_counts_utf8_and_replacement_failure_is_atomic(monkeypatch):
    raw = s.replace_annotations("", "Part 🛠", "feature", placements())
    monkeypatch.setattr(s, "MAX_STORE_BYTES", len(raw.encode("utf-8")))
    assert s.replace_annotations(raw, "Part 🛠", "feature", placements()) == raw
    with pytest.raises(s.AnnotationStoreError, match="byte limit"):
        s.replace_annotations(raw, "Other", "feature", placements())
    monkeypatch.setattr(s, "MAX_STORE_BYTES", len(raw))
    with pytest.raises(s.AnnotationStoreError, match="byte limit"):
        s.annotations_for(raw, "Part 🛠", "feature", sketch())


def test_actual_input_byte_limit_is_bounded_before_parsing():
    raw = " " * (s.MAX_STORE_BYTES + 1)
    with pytest.raises(s.AnnotationStoreError, match="byte limit"):
        s.replace_annotations(raw, "Part", "feature", {})


def test_actual_output_byte_limit_can_precede_all_count_limits_without_eviction():
    def identifier(prefix, index):
        return (f"{prefix}_{index}_" + "x" * 128)[:128]

    full = {
        identifier("constraint", index): {
            "kind": "distance",
            "refs": [identifier("p", index), identifier("q", index)],
            "display": "distance",
            "offset": [999999.1234567891, -999999.1234567891],
        }
        for index in range(s.MAX_ANNOTATIONS_PER_FEATURE)
    }
    documents = {
        f"{index:03}" + "🛠" * 125: {identifier("feature", item): {} for item in range(8)}
        for index in range(s.MAX_DOCUMENTS)
    }
    document_id = next(iter(documents))
    for index in range(7):
        documents[document_id][identifier("feature", index)] = full
    raw = compact(envelope(documents))
    assert len(raw.encode("utf-8")) < s.MAX_STORE_BYTES
    assert s.validate(raw) is None
    # Counts would be exactly 128 documents, 1024 features and 4096 placements.
    # The valid 1.87 MiB original must survive the oversized 2.11 MiB replacement.
    with pytest.raises(s.AnnotationStoreError, match="2 MiB byte limit"):
        s.replace_annotations(raw, document_id, identifier("feature", 7), full)
    assert s.validate(raw) is None
    assert json.loads(raw)["documents"][document_id][identifier("feature", 7)] == {}


@pytest.mark.parametrize("change", ["unknown", "missing_ref", "duplicate_id", "unicode", "cycle"])
def test_invalid_structural_sketch_fails_closed_without_mutating_the_store(change):
    raw = s.replace_annotations("", "Part", "feature", placements())
    current = sketch()
    if change == "unknown":
        current["unknown"] = 1
    elif change == "missing_ref":
        current["points"].pop(1)
    elif change == "duplicate_id":
        current["points"][0]["id"] = "length"
    elif change == "unicode":
        current["constraints"][0]["value"] = "\ud800"
    else:
        current["constraints"][0]["refs"] = [current, "q"]
    with pytest.raises(s.AnnotationStoreError):
        s.annotations_for(raw, "Part", "feature", current)
    assert s.annotations_for(raw, "Part", "feature", sketch()).annotations == placements()


def test_import_is_pure_without_blender_core_or_native_libraries():
    code = f"""
import importlib, importlib.abc, sys, types
class BlockNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'bpy', 'bmesh', 'mathutils', 'mechanical_cad', 'OCP', 'slvs'}}:
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, BlockNative())
package = types.ModuleType('pure_annotations')
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules['pure_annotations'] = package
store = importlib.import_module('pure_annotations.sketch_annotation_store')
assert store.replace_annotations('', 'Part', 'feature', {{}})
print('PURE_ANNOTATIONS_OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "PURE_ANNOTATIONS_OK"


def test_diameter_presentation_preserves_canonical_radius_and_formula():
    authored = sketch()
    before = copy.deepcopy(authored)
    values = placements()
    values["radius"]["display"] = "diameter"
    raw = s.replace_annotations("", "Part", "profile", values)
    lookup = s.annotations_for(raw, "Part", "profile", authored)
    assert lookup.annotations == values
    assert not lookup.unavailable
    assert authored == before
    assert authored["constraints"][1]["kind"] == "radius"
    assert authored["constraints"][1]["value"] == "radius  + 0 "
    assert s.replace_annotations(raw, "Part", "profile", lookup.annotations) == raw
