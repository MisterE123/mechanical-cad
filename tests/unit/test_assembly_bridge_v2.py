"""Native-free negotiation, typed-solid selection and adversarial v2 replies."""

import copy
import importlib.util
import math
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from mechanical_cad import assembly_service
from mechanical_cad.assembly_model import AssemblyDocument, PartSource, replace_source
from mechanical_cad.assembly_policy import fingerprint
from mechanical_cad.model import Document, Feature
from mechanical_cad.outputs import OpenProfile, ProfileOutput, SketchOutput, SolidOutput
from mechanical_cad.sketch_model import Circle, Constraint, Line, Point, SketchDefinition

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
PACKAGE = "mcad_assembly_bridge_v2_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(
    PACKAGE + ".assembly_bridge", ADDON / "assembly_bridge.py"
)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

# Synthetic protocol evidence only; real shape fidelity is covered by native integration tests.
MESH = {
    "vertices": [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 0],
        [0, 1, 0],
        [0, 0, 1],
        [1, 0, 1],
        [1, 1, 1],
        [0, 1, 1],
    ],
    "triangles": [
        [0, 2, 1],
        [0, 3, 2],
        [4, 5, 6],
        [4, 6, 7],
        [0, 1, 5],
        [0, 5, 4],
        [1, 2, 6],
        [1, 6, 5],
        [2, 3, 7],
        [2, 7, 6],
        [3, 0, 4],
        [3, 4, 7],
    ],
    "triangle_face_ids": [None] * 12,
}


def assembly(*, new_sketch=True):
    candidate = AssemblyDocument.from_json(
        (ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()
    )
    if not new_sketch:
        return candidate
    sketch = SketchDefinition(
        "round",
        (Point("center", 0, 0),),
        (),
        (Constraint("size", "radius", ("rim",), "radius"),),
        circles=(Circle("rim", "center", 5),),
        schema_version=2,
    )
    raw = candidate.part_sources[0].document.to_dict()
    raw["schema_version"] = 2
    raw["parameters"] = {"radius": 5}
    raw["features"][0] = Feature("profile", "sketch_constrained", "Round", sketch=sketch).to_dict()
    return replace_source(candidate, "user_part", Document.from_dict(raw))


def synthetic_evidence(*, new_sketch):
    # Deliberately synthetic signatures and tessellation. They exercise schema
    # consistency; no test claims this box tessellation is a circle extrusion.
    roles = (
        ["cap.start", "cap.end", "side.circle.rim"]
        if new_sketch
        else ["cap.start", "cap.end", "side.x_min", "side.x_max", "side.y_min", "side.y_max"]
    )
    topology = []
    for role in roles:
        relation = {"cap.start": "first_shape", "cap.end": "last_shape"}.get(
            role, "generated_from_profile_edge"
        )
        topology.append(
            {
                "id": "pad/face/" + role,
                "feature_id": "pad",
                "role": role,
                "kind": "face",
                "signature": {
                    "surface": "cylinder" if role.startswith("side.circle") else "plane",
                    "area": 1.0,
                    "centroid": [0.0, 0.0, 0.0],
                    **(
                        {"radius": 5.0, "axis": [0.0, 0.0, 1.0]}
                        if role.startswith("side.circle")
                        else {"normal": [0.0, 0.0, 1.0]}
                    ),
                },
                "provenance": {
                    "semantic_status": "stable",
                    "kernel": "OCCT",
                    "operation": "extrude",
                    "operation_id": "pad",
                    "relation": relation,
                    "evolution": relation,
                    **(
                        {"source_boundary": role.removeprefix("side.")}
                        if role.startswith("side.")
                        else {}
                    ),
                },
            }
        )
    mesh = copy.deepcopy(MESH)
    mesh["triangle_face_ids"] = [
        topology[index % len(topology)]["id"] for index in range(len(mesh["triangles"]))
    ]
    stats = {
        "valid": True,
        "solids": 1,
        "volume": 1.0,
        "area": float(len(roles)),
        "faces": len(roles),
    }
    checks = {
        "brep": copy.deepcopy(stats),
        "mesh": {
            "watertight": True,
            "consistently_oriented": True,
            "vertex_manifold": True,
            "vertices": 8,
            "triangles": 12,
            "signed_volume": 1.0,
            "weld_tolerance": 1e-7,
        },
        "linear_deflection_mm": 0.1,
    }
    return stats, topology, mesh, checks


class Kernel:
    def __init__(self, *, new_sketch=True):
        self.new_sketch = new_sketch

    def runtime_versions(self):
        return {"adapter": "test-only", "ocp": "not-loaded"}

    def manufacturing_check(self, shape, deflection):
        assert shape == "solid:pad"
        checks = synthetic_evidence(new_sketch=self.new_sketch)[3]
        checks["linear_deflection_mm"] = deflection
        return checks

    def transformed(self, shape, frame, **kwargs):
        return frame


@pytest.fixture
def make(monkeypatch):
    calls = []

    def regenerate(document, kernel, **kwargs):
        calls.append(kwargs)
        new_sketch = document.features[0].kind == "sketch_constrained"
        stats, topology, mesh, _ = synthetic_evidence(new_sketch=new_sketch)
        features = [
            {
                "id": f.id,
                "status": "ok",
                "error": None,
                "stats": copy.deepcopy(stats) if f.kind in {"extrude", "cut"} else None,
                "mesh": copy.deepcopy(mesh),
                "topology": copy.deepcopy(topology),
                "output": (
                    {"kind": "solid", "display": "mesh"}
                    if f.kind in {"extrude", "cut"}
                    else {
                        "kind": "sketch",
                        "display": "solved_sketch",
                        "profile": {"state": "available", "region_kind": "circle"},
                    }
                    if f.kind == "sketch_constrained"
                    else {"kind": "profile", "display": "mesh"}
                ),
            }
            for f in document.features
        ]
        outputs = {
            f.id: SolidOutput("solid:" + f.id)
            if f.kind in {"extrude", "cut"}
            else ProfileOutput("profile:" + f.id)
            for f in document.features
        }
        return SimpleNamespace(
            ok=True,
            result={"status": "ok", "features": features},
            outputs=outputs,
            # Deliberately incompatible values prove consumers use typed output.
            shapes={f.id: "legacy-shape:" + f.id for f in document.features},
        )

    monkeypatch.setattr(assembly_service, "regenerate", regenerate)

    def make(*, new_sketch=True, result_version=2):
        candidate = assembly(new_sketch=new_sketch)
        request = bridge.build_request(candidate.to_dict(), result_version=result_version)
        response = assembly_service.run_assembly_action(
            candidate, result_version=result_version, kernel=Kernel(new_sketch=new_sketch)
        )
        response.update(
            protocol_version=1,
            kind="assembly",
            assembly_protocol_version=1,
            input_fingerprint=fingerprint(request),
        )
        return request, response, calls

    return make


def seal(response):
    response["request_fingerprint"] = fingerprint(response["request"])
    response["report"]["request_fingerprint"] = response["request_fingerprint"]
    response["report_fingerprint"] = fingerprint(
        {
            "request": response["request"],
            "report": response["report"],
            "error": response["error"],
            "source_replays": response["result"]["source_replays"],
        }
    )


def test_matching_v2_response_uses_typed_solid_and_exact_snapshot(make, monkeypatch):
    request, response, calls = make()
    assert response["ok"], response["error"]
    assert calls == [{"linear_deflection": 0.1, "result_version": 2}]
    accepted = bridge.validate_response(request, response)
    assert accepted.request_snapshot() == request
    exchanges = []

    def exchange(raw, **kwargs):
        exchanges.append(raw)
        return response

    monkeypatch.setattr(bridge.bridge, "_exchange_raw", exchange)
    assert bridge.assembly_action(request["assembly"], result_version=2) == accepted
    assert exchanges == [request]
    accepted["result_version"] = 1
    with pytest.raises(bridge.bridge.BridgeError, match="was changed"):
        accepted.assert_unchanged()


def test_default_one_request_bytes_and_service_identity_remain_legacy(make):
    raw = assembly(new_sketch=False).to_dict()
    request = bridge.build_request(raw)
    assert request == bridge.build_request(raw, result_version=1)
    assert set(request) == {
        "protocol_version",
        "kind",
        "assembly_protocol_version",
        "assembly",
        "action",
        "coordinates",
        "requirements",
        "policy",
        "samples",
        "preset_id",
    }
    default_request, default, _ = make(new_sketch=False, result_version=1)
    assert "result_version" not in default and "result_version" not in default["request"]
    assert bridge.validate_response(default_request, default)["ok"]
    v2_request, v2, _ = make(new_sketch=False)
    assert bridge.validate_response(v2_request, v2)["ok"]
    legacy_result = copy.deepcopy(v2["result"])
    for replay in legacy_result["source_replays"]:
        for feature in replay["features"]:
            feature.pop("output")
    assert default["result"] == legacy_result
    assert default["request_fingerprint"] != v2["request_fingerprint"]
    assert default["report_fingerprint"] != v2["report_fingerprint"]


def test_new_payload_needs_explicit_v2_before_transport(monkeypatch):
    monkeypatch.setattr(
        bridge.bridge, "_exchange_raw", lambda *a, **k: pytest.fail("must not launch")
    )
    with pytest.raises(bridge.bridge.BridgeError, match="matching add-on and sidecar"):
        bridge.assembly_action(assembly().to_dict())


@pytest.mark.parametrize("value", [None, True, False, 0, 4, 2.0, "2", [], {}])
def test_invalid_client_version_fails_before_transport(value, monkeypatch):
    monkeypatch.setattr(
        bridge.bridge, "_exchange_raw", lambda *a, **k: pytest.fail("must not launch")
    )
    with pytest.raises(bridge.bridge.BridgeError, match="result versions 1, 2 and 3"):
        bridge.assembly_action(assembly(new_sketch=False).to_dict(), result_version=value)


@pytest.mark.parametrize("version", [None, True, 1, 2.0, 3])
def test_missing_or_mismatched_response_version_never_downgrades(make, monkeypatch, version):
    request, response, _ = make()
    if version is None:
        response.pop("result_version")
    else:
        response["result_version"] = version
    exchanges = []

    def exchange(raw, **kwargs):
        exchanges.append(raw)
        return response

    monkeypatch.setattr(bridge.bridge, "_exchange_raw", exchange)
    with pytest.raises(bridge.bridge.BridgeError, match="matching add-on and sidecar"):
        bridge.assembly_action(request["assembly"], result_version=2)
    assert exchanges == [request]


def test_old_backend_error_gives_upgrade_guidance_and_never_retries(make, monkeypatch):
    request, _, _ = make()
    exchanges = []

    def exchange(raw, **kwargs):
        exchanges.append(raw)
        return {
            "protocol_version": 1,
            "ok": False,
            "result": None,
            "error": {"code": "invalid_request", "message": "Unknown assembly request fields."},
        }

    monkeypatch.setattr(bridge.bridge, "_exchange_raw", exchange)
    with pytest.raises(bridge.bridge.BridgeError, match="Upgrade both"):
        bridge.assembly_action(request["assembly"], result_version=2)
    assert len(exchanges) == 1 and exchanges[0] == request


@pytest.mark.parametrize("value", [None, True, 1, 2.0, "2"])
def test_tampered_service_version_is_rejected_even_after_rehash(make, value):
    request, response, _ = make()
    if value is None:
        response["request"].pop("result_version")
    else:
        response["request"]["result_version"] = value
    seal(response)
    with pytest.raises(bridge.bridge.BridgeError, match="Malformed assembly"):
        bridge.validate_response(request, response)


def test_late_version_one_reply_rejected_even_if_raw_fingerprint_rebound(make):
    old_request, response, _ = make(new_sketch=False, result_version=1)
    request = {**old_request, "result_version": 2}
    response["input_fingerprint"] = fingerprint(request)
    with pytest.raises(bridge.bridge.BridgeError, match="matching add-on and sidecar"):
        bridge.validate_response(request, response)


def test_late_raw_request_and_report_tampering_rejected(make):
    request, response, _ = make()
    changed = copy.deepcopy(request)
    changed["coordinates"] = {"slide_a": 101}
    with pytest.raises(bridge.bridge.BridgeError, match="raw request fingerprint"):
        bridge.validate_response(changed, response)
    response["report"]["manufacturing_or_load_certification"] = True
    with pytest.raises(bridge.bridge.BridgeError, match="report fingerprint"):
        bridge.validate_response(request, response)


def test_v2_uses_shared_snapshot_normalizer(make, monkeypatch):
    request, response, _ = make()
    calls = []
    normalize = bridge.part_snapshot_bridge.canonical_equivalent

    def canonical_equivalent(raw, canonical):
        calls.append((raw, canonical))
        return normalize(raw, canonical)

    monkeypatch.setattr(bridge.part_snapshot_bridge, "canonical_equivalent", canonical_equivalent)
    assert bridge.validate_response(request, response)["ok"]
    assert len(calls) == 1
    # Source hash and report rehashing cannot authorize a fabricated serializer field.
    response["result"]["canonical_assembly"]["part_sources"][0]["document"]["features"][0][
        "sketch"
    ]["surprise"] = 1
    with pytest.raises(bridge.bridge.BridgeError):
        bridge.validate_response(request, response)


def test_typed_open_sketch_cannot_impersonate_selected_solid(monkeypatch):
    sketch = SketchDefinition(
        "open",
        (Point("a", 0, 0), Point("b", 5, 0)),
        (Line("edge", "a", "b"),),
        (),
        schema_version=2,
    )
    output = SketchOutput(sketch, OpenProfile())

    def regenerate(document, kernel, **kwargs):
        return SimpleNamespace(
            ok=True,
            result={
                "status": "ok",
                "features": [
                    {
                        "id": f.id,
                        "status": "ok",
                        "error": None,
                        "stats": {},
                        "mesh": copy.deepcopy(MESH),
                        "topology": [],
                    }
                    for f in document.features
                ],
            },
            shapes={"pad": "solid:pad"},
            outputs={"pad": output},
        )

    monkeypatch.setattr(assembly_service, "regenerate", regenerate)
    response = assembly_service.run_assembly_action(assembly(), result_version=2, kernel=Kernel())
    assert response["error"]["code"] == "not_a_solid"
    assert not response["ok"] and not response["result"]["parts"]


def test_all_embedded_versions_checked_before_any_native_work(monkeypatch):
    candidate = assembly(new_sketch=False)
    new_document = replace(assembly().part_sources[0].document, id="second_source")
    candidate = replace(
        candidate, part_sources=(*candidate.part_sources, PartSource.from_document(new_document))
    )
    monkeypatch.setattr(
        assembly_service,
        "regenerate",
        lambda *a, **k: pytest.fail("must validate every source first"),
    )
    response = assembly_service.run_assembly_action(candidate, kernel=object())
    assert response["error"]["code"] == "unsupported_result_version"
    assert not response["result"]["source_replays"]
    assert "native_runtime_versions" not in response["report"]


def test_invalid_direct_versions_have_type_separated_forensic_identity():
    values = [
        True,
        1.0,
        4,
        "4",
        math.nan,
        {"invalid_numeric_value": "nan"},
        (2,),
        {"invalid_type": "tuple", "items": [2]},
        10**5000,
    ]
    results = [
        assembly_service.run_assembly_action(
            assembly(new_sketch=False), result_version=value, kernel=object()
        )
        for value in values
    ]
    assert all(row["error"]["code"] == "unsupported_result_version" for row in results)
    assert all("native_runtime_versions" not in row["report"] for row in results)
    assert len({row["request_fingerprint"] for row in results}) == len(results)
    assert len({row["report_fingerprint"] for row in results}) == len(results)
    assert results[4]["request"]["result_version"] == results[5]["request"]["result_version"]
    assert results[6]["request"]["result_version"] == results[7]["request"]["result_version"]
    assert results[-1]["request"]["result_version"] == {"invalid_integer_hex": hex(10**5000)}


def test_v2_bridge_import_remains_native_and_blender_free():
    code = f"""
import sys, types
package = types.ModuleType('isolated')
package.__path__ = [{str(ADDON)!r}]
sys.modules['isolated'] = package
from isolated import assembly_bridge
assert not {{'bpy', 'OCP', 'slvs', 'mechanical_cad', 'cadquery'}}.intersection(sys.modules)
"""
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", code], check=True, capture_output=True, text=True
    )


def test_frozen_legacy_blocked_response_retains_exact_hashes(monkeypatch):
    # Captured from the unmodified service at a8ce39d with fixed distribution
    # metadata, avoiding machine-specific package versions in the golden receipt.
    monkeypatch.setattr(
        assembly_service,
        "runtime_versions",
        lambda: {"mechanical_cad": "test-stable", "evaluator": "rooted_tree_v1"},
    )
    response = assembly_service.run_assembly_action(
        assembly(new_sketch=False), coordinates={"slide_a": 999}, kernel=object()
    )
    assert (
        response["request_fingerprint"]
        == "30743e9098f3e8353b3ec599b0f0f563c797f30acb9eeb8f2d10eaec799de624"
    )
    assert (
        response["report_fingerprint"]
        == "e8c22d1a9c0ac320a0323102907a75d15e8d3a1e866a3181b8c8b2cd27cb0dca"
    )
    assert (
        fingerprint(response) == "23307922d15f7c0a452dc3bdb52c0bd182e165cc2fe567a495f6d621a6ca8abe"
    )


@pytest.mark.parametrize("response", [None, [], "invalid", 2])
def test_malformed_v2_envelope_is_a_bounded_bridge_error(response):
    request = bridge.build_request(assembly().to_dict(), result_version=2)
    with pytest.raises(bridge.bridge.BridgeError, match="Malformed assembly"):
        bridge.accept_response(request, response)


def test_default_version_failure_for_new_source_remains_readable(make):
    request, _, calls = make()
    calls.clear()
    request.pop("result_version")
    response = assembly_service.run_assembly_action(assembly(), kernel=Kernel())
    response.update(
        protocol_version=1,
        kind="assembly",
        assembly_protocol_version=1,
        input_fingerprint=fingerprint(request),
    )
    accepted = bridge.validate_response(request, response)
    assert not accepted["ok"]
    assert accepted["error"]["code"] == "unsupported_result_version"
    assert not calls


def test_matching_backend_common_error_retains_actionable_original_diagnostic():
    request = bridge.build_request(assembly().to_dict(), result_version=2)
    response = {
        "protocol_version": 1,
        "result_version": 2,
        "ok": False,
        "result": None,
        "error": {"code": "invalid_request", "message": "Unknown assembly request fields."},
    }
    with pytest.raises(bridge.bridge.BridgeError) as caught:
        bridge.accept_response(request, response)
    assert str(caught.value) == "invalid_request: Unknown assembly request fields."
