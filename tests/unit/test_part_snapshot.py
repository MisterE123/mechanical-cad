"""The Part snapshot service serializes intent without geometry or migration."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Frame,
    Instance,
    Joint,
    MateFrame,
    PartDefinition,
    PartSource,
)
from mechanical_cad.errors import CADException
from mechanical_cad.model import Document
from mechanical_cad.part_snapshot import canonical_snapshot, input_fingerprint
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples/regressions/viewport_schema2_capture.mcad.json"


def viewport_part():
    return json.loads(FIXTURE.read_text())


def test_exact_viewport_capture_becomes_authoritative_without_rewriting_authoring_buffer():
    raw = viewport_part()
    saved = copy.deepcopy(raw)
    before = FIXTURE.read_bytes()
    snapshot = canonical_snapshot(raw)
    document = Document.from_dict(raw)
    assert snapshot["canonical_json"] == document.to_json()
    assert snapshot["canonical_document"] == document.to_dict()
    assert snapshot["content_hash"] == document.content_hash
    assert snapshot["document_id"] == raw["id"]
    assert snapshot["schema_version"] == raw["schema_version"] == 2
    assert (
        snapshot["content_hash"]
        != hashlib.sha256((json.dumps(raw, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
    )
    constraints = snapshot["canonical_document"]["features"][0]["sketch"]["constraints"]
    assert all(set(record) == {"id", "kind", "refs", "value", "target"} for record in constraints)
    assert [record["id"] for record in constraints] == sorted(
        record["id"] for record in constraints
    )
    assert raw == saved and FIXTURE.read_bytes() == before
    assert canonical_snapshot(snapshot["canonical_document"]) == snapshot
    assert canonical_snapshot(json.loads(snapshot["canonical_json"])) == snapshot


def test_snapshot_preserves_formulas_stable_ids_and_unsolved_seed_coordinates():
    raw = viewport_part()
    snapshot = canonical_snapshot(raw)["canonical_document"]
    assert snapshot["parameters"] == raw["parameters"]
    assert [f["id"] for f in snapshot["features"]] == [f["id"] for f in raw["features"]]
    source_sketch, result_sketch = raw["features"][0]["sketch"], snapshot["features"][0]["sketch"]
    for field in ("points", "lines"):
        assert {record["id"]: record for record in source_sketch[field]} == {
            record["id"]: record for record in result_sketch[field]
        }
    for record in source_sketch["constraints"]:
        result = next(item for item in result_sketch["constraints"] if item["id"] == record["id"])
        assert all(result[key] == value for key, value in record.items())
    assert snapshot["features"][1]["params"]["length"] == "extrude_1_length"
    snapshot["parameters"]["sketch_1_width"] = 999
    assert raw["parameters"]["sketch_1_width"] == "12"


@pytest.mark.parametrize(
    "name,digest",
    [
        ("drilled_plate", "777d634152cce17a17247b347e433b311410ee2c67fcc70927176e02d8ac59e9"),
        ("parameter_chain", "c1e2022c53181e464b61eca691ab48dadf33fe3e7326b6ae7da4da295b604ace"),
    ],
)
def test_existing_schema_one_serialized_bytes_and_hashes_stay_unchanged(name, digest):
    raw = json.loads((ROOT / f"examples/{name}.mcad.json").read_text())
    receipt = canonical_snapshot(raw)
    assert receipt["schema_version"] == 1 and receipt["content_hash"] == digest
    assert receipt["canonical_json"] == Document.from_dict(raw).to_json()


def test_only_known_defaults_and_sketch_numeric_representation_normalize():
    raw = viewport_part()
    raw.pop("active_feature")
    for feature in raw["features"]:
        feature.pop("label")
    raw["features"][0].pop("inputs")
    raw["features"][0].pop("params")
    sketch = raw["features"][0]["sketch"]
    sketch["plane"]["quaternion"] = [1, 0, 0, 0]
    sketch["points"][0]["u"] = -1
    sketch["constraints"][-1]["value"] = 8
    result = canonical_snapshot(raw)["canonical_document"]
    assert result["active_feature"] is None and result["features"][0]["label"] == "sketch_1"
    canonical_sketch = result["features"][0]["sketch"]
    assert type(canonical_sketch["plane"]["quaternion"][0]) is float
    assert type(canonical_sketch["points"][0]["u"]) is float
    assert (
        type(next(c for c in canonical_sketch["constraints"] if c["id"] == "height")["value"])
        is float
    )
    assert type(raw["features"][0]["sketch"]["points"][0]["u"]) is int


def test_input_fingerprint_binds_raw_tree_before_canonical_defaults_numbers_and_order():
    raw = viewport_part()
    request = {"protocol_version": 1, "action": "canonical_snapshot", "document": raw}
    response = process_request(request)
    assert response["input_fingerprint"] == input_fingerprint(request)
    canonical_request = {**request, "document": response["result"]["canonical_document"]}
    assert input_fingerprint(request) != input_fingerprint(canonical_request)
    assert input_fingerprint({"value": 1}) != input_fingerprint({"value": 1.0})
    assert input_fingerprint({"a": 1, "b": 2}) == input_fingerprint({"b": 2, "a": 1})


@pytest.mark.parametrize(
    "malformation", ["unknown", "schema", "boolean", "nonfinite", "duplicate", "refs", "missing"]
)
def test_invalid_documents_never_receive_an_authoritative_receipt(malformation):
    raw = viewport_part()
    sketch = raw["features"][0]["sketch"]
    if malformation == "unknown":
        sketch["constraints"][0]["execute"] = "anything"
    elif malformation == "schema":
        raw["schema_version"] = True
    elif malformation == "boolean":
        sketch["points"][0]["u"] = True
    elif malformation == "nonfinite":
        sketch["points"][0]["u"] = float("inf")
    elif malformation == "duplicate":
        sketch["points"][1]["id"] = sketch["points"][0]["id"]
    elif malformation == "refs":
        sketch["lines"][0]["end"] = "missing"
    else:
        del raw["units"]
    with pytest.raises(CADException):
        canonical_snapshot(raw)


def test_capture_save_reload_parameter_edit_updates_two_instances_and_preserves_identity(tmp_path):
    original = viewport_part()
    receipt = canonical_snapshot(original)
    source = PartSource.from_dict(
        {
            "source_document_id": receipt["document_id"],
            "source_digest": receipt["content_hash"],
            "document": receipt["canonical_document"],
        }
    )
    part = PartDefinition(
        "block",
        source.source_digest,
        source.id,
        "extrude_1",
        (
            MateFrame("origin"),
            MateFrame("end", Frame((12, 0, 0))),
        ),
    )
    assembly = AssemblyDocument(
        "capture",
        "Viewport source",
        (source,),
        (part,),
        (
            Instance("fixed", "block"),
            Instance("moving", "block"),
        ),
        (Joint("slide", "slider", "fixed", "moving", "origin", "end", 20),),
        "fixed",
    )
    saved = tmp_path / "captured.mcad-assembly.json"
    saved.write_text(assembly.to_json())
    loaded = AssemblyDocument.from_json(saved.read_text())
    assert loaded.content_hash == assembly.content_hash
    assert loaded.source_hashes[source.id] == receipt["content_hash"]
    edited = Document.from_dict(receipt["canonical_document"]).with_parameter(
        "sketch_1_width", "24"
    )
    edited_receipt = canonical_snapshot(edited.to_dict())
    updated = loaded.replace_source(source.id, edited)
    assert (
        updated.source_hashes[source.id] == edited_receipt["content_hash"] != source.source_digest
    )
    assert updated.instances == loaded.instances and updated.joints == loaded.joints
    assert updated.parts[0].mate_frames == loaded.parts[0].mate_frames
    assert updated.parts[0].output_feature_id == loaded.parts[0].output_feature_id
    assert all(updated.parts[0].source_digest == edited.content_hash for _ in updated.instances)
    assert loaded.source_hashes[source.id] == receipt["content_hash"]
    assert viewport_part() == original
    assert AssemblyDocument.from_json(updated.to_json()).content_hash == updated.content_hash
    forged = source.to_dict()
    forged["document"]["parameters"]["sketch_1_width"] = "24"
    with pytest.raises(CADException, match="identity/hash"):
        PartSource.from_dict(forged)


def hostile_tree(kind):
    if kind == "cycle":
        value = []
        value.append(value)
        return value
    if kind == "shared_dag":
        value = [0]
        for _ in range(20):
            value = [value] * 16
        return value
    if kind == "deep":
        value = 0
        for _ in range(40):
            value = [value]
        return value
    if kind == "huge_integer":
        return 1 << 20_000
    return "\u2603" * 400_000  # <2 MiB in Python chars; >2 MiB in escaped JSON.


@pytest.mark.parametrize("kind", ["cycle", "shared_dag", "deep", "huge_integer", "escaped_bytes"])
def test_direct_core_input_resource_guard_precedes_json_encoding(monkeypatch, kind):
    import mechanical_cad.part_snapshot as service

    raw = viewport_part()
    raw["parameters"]["hostile"] = hostile_tree(kind)
    monkeypatch.setattr(service.json, "dumps", lambda *a, **kw: pytest.fail("unbounded encoding"))
    with pytest.raises(CADException):
        service.input_fingerprint(raw)
    with pytest.raises(CADException):
        service.canonical_snapshot(raw)
    with pytest.raises(CADException):
        process_request({"protocol_version": 1, "action": "canonical_snapshot", "document": raw})


def test_benign_shared_containers_have_exact_expanded_wire_fingerprint():
    shared = {"ordinary": [1, 2, "formula"]}
    raw = {"a": shared, "b": shared}
    expected = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert input_fingerprint(raw) == hashlib.sha256(expected.encode()).hexdigest()
