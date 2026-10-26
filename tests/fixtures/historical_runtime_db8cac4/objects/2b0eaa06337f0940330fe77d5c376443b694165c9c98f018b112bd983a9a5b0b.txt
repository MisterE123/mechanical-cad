"""Integrated mixed-source wire validation; no native kernel or Blender launch.

Retained Part replay packets exercise the existing genuine replay-3 schema.
Assembly checks/poses use synthetic host ports and are not native qualification.
"""

import copy
import importlib
import json
from types import SimpleNamespace

import pytest
from test_assembly_bridge import Kernel as PoseKernel
from test_assembly_bridge_v2 import ROOT, bridge

from mechanical_cad import assembly_service
from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.model import Document
from mechanical_cad.outputs import ProfileOutput, SolidOutput
from mechanical_cad.sidecar import process_request

policy = importlib.import_module(bridge.__package__ + ".operation_contracts")
snapshots = bridge.part_snapshot_bridge
FIXTURES = ROOT / "tests/fixtures/arc_authoring_evidence"


def recorded_sources():
    pairs = []
    for request, response in (
        ("rectangle_replay3.request.raw", "rectangle_replay3.response.raw"),
        ("radius_edit_5_0_replay.operation.json", "radius_edit_5_0_replay.response"),
    ):
        source = json.loads((FIXTURES / request).read_text())["document"]
        replay = json.loads((FIXTURES / response).read_text())["result"]
        pairs.append((Document.from_dict(source), replay))
    return pairs


def mixed_assembly():
    raw = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    pairs = recorded_sources()
    raw["part_sources"] = [
        {
            "source_document_id": document.id,
            "source_digest": document.content_hash,
            "document": document.to_dict(),
        }
        for document, _ in pairs
    ]
    definition = raw["parts"][0]
    raw["parts"] = [
        {
            **copy.deepcopy(definition),
            "id": identifier,
            "source_document_id": document.id,
            "source_digest": document.content_hash,
            "output_feature_id": document.active_feature,
        }
        for identifier, (document, _) in zip(("block", "sector"), pairs, strict=True)
    ]
    raw["instances"][1]["part_id"] = "sector"
    return AssemblyDocument.from_dict(raw)


class Kernel(PoseKernel):
    def __init__(self, replays):
        self.replays = replays

    def manufacturing_check(self, shape, deflection):
        document_id, feature_id = shape
        feature = next(f for f in self.replays[document_id]["features"] if f["id"] == feature_id)
        mesh = feature["mesh"]
        return {
            "brep": copy.deepcopy(feature["stats"]),
            "mesh": {
                "watertight": True,
                "consistently_oriented": True,
                "vertex_manifold": True,
                "vertices": len(mesh["vertices"]),
                "triangles": len(mesh["triangles"]),
                "signed_volume": feature["stats"]["volume"],
                "weld_tolerance": 1e-7,
            },
            "linear_deflection_mm": deflection,
        }


@pytest.fixture
def make(monkeypatch):
    replays = {document.id: result for document, result in recorded_sources()}
    calls = []

    def regenerate(document, kernel, **kwargs):
        calls.append((document.id, kwargs["result_version"]))
        result = copy.deepcopy(replays[document.id])
        return SimpleNamespace(
            ok=result["status"] == "ok",
            result=result,
            outputs={
                feature.id: SolidOutput((document.id, feature.id))
                if feature.kind == "extrude"
                else ProfileOutput((document.id, feature.id))
                for feature in document.features
            },
        )

    monkeypatch.setattr(assembly_service, "regenerate", regenerate)

    def make(action="assembly_replay", **arguments):
        candidate = mixed_assembly()
        request = bridge.build_request(candidate.to_dict(), action, result_version=3, **arguments)
        response = assembly_service.run_assembly_action(
            candidate, action, result_version=3, kernel=Kernel(replays), **arguments
        )
        response.update(
            protocol_version=1,
            kind="assembly",
            assembly_protocol_version=1,
            input_fingerprint=bridge.fingerprint(request),
        )
        return request, response, calls

    make.replays = replays
    return make


def seal(response):
    response["request_fingerprint"] = bridge.fingerprint(response["request"])
    response["report"]["request_fingerprint"] = response["request_fingerprint"]
    response["report_fingerprint"] = bridge.fingerprint(
        {
            "request": response["request"],
            "report": response["report"],
            "error": response["error"],
            "source_replays": response["result"]["source_replays"],
        }
    )


def test_mixed_sources_use_genuine_replay3_and_detached_strict_assembly_dispatch(make):
    request, response, calls = make()
    before = copy.deepcopy((request, response))
    assert policy.result_version_for_assembly(request["assembly"]) == 3
    accepted = policy.validate_response(request, response)
    assert accepted == response and accepted is not response
    assert calls == [
        (source["source_document_id"], 3) for source in request["assembly"]["part_sources"]
    ]
    assert (request, response) == before
    assert (
        accepted["result"]["source_replays"][1]["features"][0]["output"]["profile"]["region_kind"]
        == "curve_loop"
    )


def test_mixed_check_and_explicit_samples_reuse_existing_pose_evidence_contract(make):
    request, response, _ = make("assembly_check", requirements=[])
    assert bridge.validate_response(request, response)["report"]["complete"]
    request, response, _ = make(
        "assembly_sample",
        requirements=[],
        coordinates={"slide_a": 100, "slide_b": 100},
        samples={"joint_id": "slide_a", "values": [100, 200]},
    )
    assert len(bridge.validate_response(request, response)["report"]["poses"]) == 2


@pytest.mark.parametrize("target", ["envelope", "echo", "replay"])
def test_result3_is_exact_at_each_wire_boundary(make, target):
    request, response, _ = make()
    value = (
        response
        if target == "envelope"
        else response["request"]
        if target == "echo"
        else response["result"]["source_replays"][0]["replay"]
    )
    value["result_version"] = 2
    seal(response)
    with pytest.raises(bridge.bridge.BridgeError):
        bridge.validate_response(request, response)


@pytest.mark.parametrize(
    "change",
    ["source", "projection", "output", "swapped", "mesh", "topology", "provenance", "stats"],
)
def test_resealed_mixed_payload_cannot_substitute_source_projection_or_geometry(make, change):
    request, response, _ = make()
    replay = response["result"]["source_replays"][1]
    part = response["result"]["parts"][1]
    if change == "source":
        replay["replay"]["document_hash"] = "0" * 64
    elif change == "projection":
        replay["features"] = copy.deepcopy(replay["features"])
        replay["features"][-1]["stats"]["volume"] += 1
    elif change == "output":
        replay["features"] = copy.deepcopy(replay["features"])
        replay["features"][-1]["output"] = {"kind": "profile", "display": "mesh"}
    elif change == "swapped":
        replays = response["result"]["source_replays"]
        replays[0]["replay"], replays[1]["replay"] = replays[1]["replay"], replays[0]["replay"]
    elif change == "mesh":
        part["mesh"] = copy.deepcopy(part["mesh"])
        part["mesh"]["vertices"][0][0] += 1
    elif change == "topology":
        part["topology"] = copy.deepcopy(part["topology"])
        part["topology"][0]["signature"]["area"] += 1
    elif change == "provenance":
        replay["replay"]["features"][-1]["topology"][-1]["provenance"]["source_boundary"] = (
            "arc.wrong"
        )
    else:
        part["geometry_check"]["brep"]["volume"] += 1
    seal(response)
    with pytest.raises(bridge.bridge.BridgeError):
        bridge.validate_response(request, response)


def test_failed_complete_replay_retains_diagnostics_and_never_publishes_parts(make):
    failed = list(make.replays.values())[-1]
    failed["status"] = "failed"
    failed["features"][-1].update(
        status="failed",
        error={"code": "kernel_error", "message": "Synthetic solid failure"},
        output=None,
        stats=None,
        mesh=None,
        topology=[],
    )
    request, response, _ = make()
    assert response["result"]["parts"] == []
    assert bridge.validate_response(request, response)["ok"] is False
    response["result"]["source_replays"][-1]["features"][-1]["error"] = None
    seal(response)
    with pytest.raises(bridge.bridge.BridgeError):
        bridge.validate_response(request, response)


def test_sector_snapshot_preserves_formulas_seeds_and_has_no_result_version():
    document = recorded_sources()[1][0].to_dict()
    document["features"][0]["sketch"]["points"][1]["u"] = 7.25
    document["features"][0]["sketch"]["constraints"].reverse()
    before = copy.deepcopy(document)
    request = {"protocol_version": 1, "action": "canonical_snapshot", "document": document}
    response = process_request(request)
    accepted = policy.validate_response(request, response)
    assert "result_version" not in response
    assert policy.result_version_for(document, action="canonical_snapshot") is None
    assert snapshots.canonical_equivalent(document, accepted["canonical_document"])
    assert document == before
    canonical = accepted["canonical_document"]
    assert canonical["features"][1]["params"]["length"] == "height"
    canonical["parameters"]["radius"] += 1
    assert not snapshots.canonical_equivalent(document, canonical)


def test_legacy_snapshot_normalizer_still_rejects_schema3():
    from test_result_v3_client import legacy

    with pytest.raises(ValueError):
        legacy._expected_document(recorded_sources()[1][0].to_dict())


def test_malformed_schema3_equivalence_is_false_without_throwing():
    document = recorded_sources()[1][0].to_dict()
    canonical = copy.deepcopy(document)
    document["parameters"]["oversized"] = "x" * (2 * 1024 * 1024)
    assert snapshots.canonical_equivalent(document, canonical) is False
