"""V2 receipts normalize only intended fields and preserve frozen legacy hashes."""

import copy
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Instance,
    MateFrame,
    PartDefinition,
    PartSource,
)
from mechanical_cad.model import Document
from mechanical_cad.part_snapshot import canonical_snapshot
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
PACKAGE = "mcad_part_snapshot_v2_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
SPEC = importlib.util.spec_from_file_location(
    PACKAGE + ".part_snapshot_bridge", ADDON / "part_snapshot_bridge.py"
)
snapshot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = snapshot
SPEC.loader.exec_module(snapshot)


def raw_document():
    return {
        "schema_version": 2,
        "id": "circle_part",
        "name": "Circle Part",
        "units": "mm",
        "parameters": {"shaft_radius": 4, "clearance": "0.25"},
        "active_feature": "pad",
        "features": [
            {
                "id": "profile",
                "kind": "sketch_constrained",
                "sketch": {
                    "schema_version": 2,
                    "id": "disk",
                    "units": "mm",
                    "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
                    "points": [{"id": "center", "u": 3, "v": 4}],
                    "lines": [],
                    "circles": [{"id": "rim", "center": "center", "radius": 7}],
                    "constraints": [
                        {
                            "id": "size",
                            "kind": "radius",
                            "refs": ["rim"],
                            "value": "shaft_radius + clearance",
                        },
                        {"id": "anchor", "kind": "fixed", "refs": ["center"], "target": [3, 4]},
                    ],
                },
            },
            {
                "id": "pad",
                "kind": "extrude",
                "params": {"length": 10},
                "inputs": {"profile": "profile"},
            },
        ],
    }


def request(document=None):
    return {
        "protocol_version": 1,
        "action": "canonical_snapshot",
        "document": raw_document() if document is None else document,
    }


def reseal(response):
    result = response["result"]
    result["canonical_json"] = (
        json.dumps(result["canonical_document"], sort_keys=True, indent=2) + "\n"
    )
    result["content_hash"] = hashlib.sha256(result["canonical_json"].encode()).hexdigest()


def test_circle_snapshot_matches_authoritative_bytes_without_solving_or_mutation():
    raw = raw_document()
    before = copy.deepcopy(raw)
    candidate = request(raw)
    response = process_request(candidate)
    receipt = snapshot.validate_response(candidate, response)
    document = Document.from_dict(raw)
    assert receipt["canonical_json"] == document.to_json()
    assert receipt["canonical_document"] == document.to_dict()
    assert receipt["content_hash"] == document.content_hash
    assert snapshot.canonical_equivalent(raw, receipt["canonical_document"])
    assert raw == before
    canonical = receipt["canonical_document"]["features"][0]["sketch"]
    assert canonical["schema_version"] == 2
    assert canonical["circles"] == [{"id": "rim", "center": "center", "radius": 7.0}]
    assert type(canonical["circles"][0]["radius"]) is float
    assert (
        next(c for c in canonical["constraints"] if c["id"] == "size")["value"]
        == "shaft_radius + clearance"
    )
    assert all(
        set(c) == {"id", "kind", "refs", "value", "target"} for c in canonical["constraints"]
    )
    receipt["canonical_document"]["features"][0]["sketch"]["circles"][0]["radius"] = 99
    assert (
        response["result"]["canonical_document"]["features"][0]["sketch"]["circles"][0]["radius"]
        == 7
    )


def test_multiple_circle_records_normalize_stable_order_and_numeric_seeds():
    raw = raw_document()
    sketch = raw["features"][0]["sketch"]
    sketch["points"].insert(0, {"id": "z_center", "u": -2, "v": 0})
    sketch["circles"].insert(0, {"id": "z_rim", "center": "z_center", "radius": 2})
    candidate = request(raw)
    receipt = snapshot.validate_response(candidate, process_request(candidate))
    actual = receipt["canonical_document"]["features"][0]["sketch"]
    assert [circle["id"] for circle in actual["circles"]] == ["rim", "z_rim"]
    assert all(type(circle["radius"]) is float for circle in actual["circles"])
    # Canonical snapshots describe intent; mixed/multiple regions are a replay gate.
    assert receipt["content_hash"] == Document.from_dict(raw).content_hash


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.update(schema_version=1),
        lambda s: s.update(schema_version=3),
        lambda s: s.update(schema_version=True),
        lambda s: s.pop("circles"),
        lambda s: s.update(extra=True),
        lambda s: s["circles"][0].update(id="center"),
        lambda s: s["circles"][0].update(id="xy"),
        lambda s: s["circles"][0].update(id="size"),
        lambda s: s["circles"][0].update(id="invalid id"),
        lambda s: s["circles"][0].update(center="rim"),
        lambda s: s["circles"][0].update(center="missing"),
        lambda s: s["circles"][0].update(center=True),
        lambda s: s["circles"][0].update(radius="shaft_radius"),
        lambda s: s["circles"][0].update(radius=True),
        lambda s: s["circles"][0].update(radius=0),
        lambda s: s["circles"][0].update(radius=-1),
        lambda s: s["circles"][0].update(radius=1e-7),
        lambda s: s["circles"][0].update(radius=1e6 + 1),
        lambda s: s["circles"][0].update(radius=float("nan")),
        lambda s: s["circles"][0].update(radius=float("inf")),
        lambda s: s["circles"][0].update(seam_angle=0),
        lambda s: s["constraints"][0].update(refs=["center"]),
        lambda s: s["constraints"][0].update(kind="diameter"),
        lambda s: s["constraints"][0].update(value=True),
        lambda s: s["constraints"][0].update(target=[0, 0]),
        lambda s: s["points"][0].update(u=1e6 + 1),
    ],
)
def test_v2_malformed_circle_identity_seed_or_constraint_fails_closed(change):
    raw = raw_document()
    change(raw["features"][0]["sketch"])
    with pytest.raises((ValueError, snapshot.bridge.BridgeError)):
        snapshot._expected_document(raw)
    assert not snapshot.canonical_equivalent(raw, raw)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s["circles"][0].update(id="renamed"),
        lambda s: s["circles"][0].update(radius=4.25),  # Solved state must not overwrite seed.
        lambda s: s["circles"][0].update(radius=7),  # Canonical wire bytes require doubles.
        lambda s: s["circles"][0].update(center="another"),
        lambda s: s["points"][0].update(u=4.0),
        lambda s: s["constraints"][1].update(value=4.25),
        lambda s: s["constraints"][1].update(value="shaft_radius + clearance + 0"),
        lambda s: s["constraints"].reverse(),
        lambda s: s.update(schema_version=1),
    ],
)
def test_resealed_forged_receipt_cannot_change_v2_authored_intent(change):
    candidate = request()
    response = process_request(candidate)
    change(response["result"]["canonical_document"]["features"][0]["sketch"])
    reseal(response)
    with pytest.raises(snapshot.bridge.BridgeError, match="Invalid canonical Part snapshot"):
        snapshot.validate_response(candidate, response)


@pytest.mark.parametrize(
    "name,digest",
    [
        ("drilled_plate", "777d634152cce17a17247b347e433b311410ee2c67fcc70927176e02d8ac59e9"),
        ("parameter_chain", "c1e2022c53181e464b61eca691ab48dadf33fe3e7326b6ae7da4da295b604ace"),
        ("viewport_rectangle", "c01ff8fc476f9eaf9d314df4c3aae607cca15da6a6075d902b5aa30054ba48c7"),
        (
            "regressions/viewport_schema2_capture",
            "bdc884a1fc0f481623657749a30716e78ea82529a070b32b5c94fd90b041b173",
        ),
    ],
)
def test_exact_legacy_hashes_measured_from_prechange_git_source(name, digest):
    raw = json.loads((ROOT / f"examples/{name}.mcad.json").read_text())
    candidate = request(raw)
    receipt = snapshot.validate_response(candidate, process_request(candidate))
    assert receipt["content_hash"] == digest
    assert receipt["canonical_json"] == Document.from_dict(raw).to_json()
    for feature in receipt["canonical_document"]["features"]:
        if "sketch" in feature:
            assert feature["sketch"]["schema_version"] == 1
            assert "circles" not in feature["sketch"]


def test_old_accepted_assembly_snapshot_hash_is_unchanged_and_source_update_is_explicit():
    raw = json.loads((ROOT / "examples/regressions/viewport_schema2_capture.mcad.json").read_text())
    receipt = canonical_snapshot(raw)
    source = PartSource.from_dict(
        {
            "source_document_id": receipt["document_id"],
            "source_digest": receipt["content_hash"],
            "document": receipt["canonical_document"],
        }
    )
    part = PartDefinition(
        "block", source.source_digest, source.id, "extrude_1", (MateFrame("origin"),)
    )
    assembly = AssemblyDocument(
        "frozen_capture",
        "Frozen capture",
        (source,),
        (part,),
        (Instance("fixed", "block"),),
        (),
        "fixed",
    )
    assert (
        assembly.content_hash == "f2ed58c5659413443a526f060e5393fdea14940bd972cb126450023a0bdb477f"
    )
    assert AssemblyDocument.from_json(assembly.to_json()).to_json() == assembly.to_json()
    migrated = copy.deepcopy(receipt["canonical_document"])
    migrated["features"][0]["sketch"].update(schema_version=2, circles=[])
    newer = snapshot.validate_response(request(migrated), process_request(request(migrated)))
    assert newer["content_hash"] != receipt["content_hash"]
    updated = assembly.replace_source(source.id, Document.from_dict(migrated))
    assert updated.source_hashes[source.id] == newer["content_hash"]
    assert assembly.source_hashes[source.id] == receipt["content_hash"]
    assert not snapshot.canonical_equivalent(raw, newer["canonical_document"])
    assert snapshot.canonical_equivalent(raw, receipt["canonical_document"])


def test_v2_scalar_budget_is_candidate_specific_and_no_extra_center_radius_limit():
    raw = raw_document()
    sketch = raw["features"][0]["sketch"]
    sketch["points"][0].update(u=1e6, v=-1e6)
    sketch["circles"][0]["radius"] = 1e6
    candidate = request(raw)
    assert snapshot.validate_response(candidate, process_request(candidate))["content_hash"]
    sketch["points"].extend({"id": f"unused{i}", "u": 0, "v": 0} for i in range(255))
    with pytest.raises(ValueError, match="scalar"):
        snapshot._expected_document(raw)
