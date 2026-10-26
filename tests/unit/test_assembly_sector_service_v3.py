"""Pure mixed-source Assembly/snapshot admission and genuine replay-3 transport.

The replay and query doubles below establish service wiring only. They never
claim native geometry or solver qualification.
"""

import copy
import importlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad import assembly_service, backend_contract, part_snapshot, sidecar
from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Instance,
    Joint,
    MateFrame,
    PartDefinition,
    PartSource,
)
from mechanical_cad.assembly_policy import fingerprint
from mechanical_cad.engine import Replay
from mechanical_cad.model import Document, Feature
from mechanical_cad.outputs import SolidOutput
from mechanical_cad.sketch_model import Arc, Line, Point, SketchDefinition

ROOT = Path(__file__).resolve().parents[2]


def sector_document(*, height=10):
    sketch = SketchDefinition(
        "sector_sketch",
        (Point("end", 0, 10), Point("center", 0, 0), Point("start", 10, 0)),
        (Line("radial_start", "center", "start"), Line("radial_end", "end", "center")),
        (),
        schema_version=3,
        arcs=(Arc("rim", "center", "start", "end", "ccw"),),
    )
    return Document(
        "sector",
        "Sector",
        {},
        (
            Feature("profile", "sketch_constrained", "Sector sketch", sketch=sketch),
            Feature("pad", "extrude", "Sector solid", {"length": height}, {"profile": "profile"}),
        ),
        "pad",
        schema_version=2,
    )


def box_document():
    return Document(
        "box",
        "Box",
        {},
        (
            Feature(
                "profile",
                "sketch_rectangle",
                "Rectangle",
                {"width": 10, "height": 10, "x": 0, "y": 0, "z": 0},
            ),
            Feature("pad", "extrude", "Box solid", {"length": 10}, {"profile": "profile"}),
        ),
        "pad",
    )


def mixed_assembly(sector=None):
    sources = tuple(
        PartSource.from_document(doc) for doc in (box_document(), sector or sector_document())
    )
    parts = tuple(
        PartDefinition(source.id, source.source_digest, source.id, "pad", (MateFrame("origin"),))
        for source in sources
    )
    return AssemblyDocument(
        "mixed",
        "Box and sector",
        sources,
        parts,
        (Instance("base", "box"), Instance("moving", "sector"), Instance("reused", "sector")),
        (
            Joint("slide", "slider", "base", "moving", "origin", "origin", 25),
            Joint("fixed", "fixed", "moving", "reused", "origin", "origin"),
        ),
        "base",
    )


def operation(assembly=None, **extra):
    return {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "action": "assembly_replay",
        "result_version": 3,
        "assembly": (assembly or mixed_assembly()).to_dict(),
        **extra,
    }


def guarded(request):
    return {
        **request,
        "backend_contract": {
            "version": 1,
            "request_id": "0123456789abcdef0123456789abcdef",
            "required_capabilities": sorted(backend_contract.minimum_capabilities(request)),
        },
    }


class QueryDouble:
    """No geometry is calculated; only expected service call routing is recorded."""

    def __init__(self):
        self.checks = []

    def runtime_versions(self):
        return {"adapter": "test-double"}

    def manufacturing_check(self, shape, deflection):
        self.checks.append(shape)
        return {"brep": {"solids": 1}, "mesh": {}, "linear_deflection_mm": deflection}

    def transformed(self, shape, frame, **kwargs):
        return shape

    def pair_check(self, *args, **kwargs):
        return {
            "complete": True,
            "known_interference": False,
            "known_clearance_violation": False,
            "clearance_verdict": "pass_at_pose",
        }


def install_replay_double(monkeypatch, *, failed_source=None):
    calls, bodies = [], {}

    def replay(document, kernel, *, linear_deflection, result_version):
        calls.append((document.id, result_version))
        failed = document.id == failed_source
        features = [
            {
                "id": source.id,
                "status": "failed" if failed else "ok",
                "error": {"code": "test_failure", "message": "Test failure"} if failed else None,
                "stats": None if source.id == "profile" else {"solids": 1, "volume": 1.0},
                "output": None if failed else {"kind": "solid", "display": "mesh"},
                "mesh": {"vertices": [], "triangles": [], "triangle_face_ids": []},
                "topology": [],
            }
            for source in document.features
        ]
        body = {
            "document_id": document.id,
            "document_hash": document.content_hash,
            "active_feature": document.active_feature,
            "units": "mm",
            "parameters": {},
            "status": "failed" if failed else "ok",
            "features": features,
            "result_version": result_version,
        }
        bodies[document.id] = copy.deepcopy(body)
        return Replay(body, {}, {"pad": SolidOutput(document.id)})

    monkeypatch.setattr(assembly_service, "regenerate", replay)
    return calls, bodies


def test_sector_snapshot_preserves_unresolved_formulas_and_unsolved_seed_bytes():
    raw = sector_document(height="not_resolved + 2").to_dict()
    sketch = raw["features"][0]["sketch"]
    sketch["points"].reverse()
    sketch["lines"].reverse()
    sketch["constraints"] = [
        {"id": "radius", "kind": "radius", "refs": ["rim"], "value": "not_resolved"},
    ]
    before = copy.deepcopy(raw)
    request = {"protocol_version": 1, "action": "canonical_snapshot", "document": raw}
    response = sidecar.process_request(request)
    canonical = Document.from_dict(raw)
    assert response["ok"] and "result_version" not in response
    assert response["result"]["canonical_document"] == canonical.to_dict()
    assert response["result"]["canonical_json"] == canonical.to_json()
    assert response["result"]["content_hash"] == canonical.content_hash
    assert response["input_fingerprint"] == part_snapshot.input_fingerprint(request)
    assert raw == before


@pytest.mark.parametrize(
    "change",
    ["arc_empty", "missing_radius", "profile_only", "inactive", "frame", "height", "extra_branch"],
)
def test_general_schema3_snapshot_admission_is_not_geometry_qualification(change, monkeypatch):
    raw = sector_document().to_dict()
    sketch = raw["features"][0]["sketch"]
    if change == "arc_empty":
        sketch["arcs"] = []
    elif change == "missing_radius":
        sketch["lines"].pop()
    elif change == "profile_only":
        raw["features"].pop()
        raw["active_feature"] = "profile"
    elif change == "inactive":
        raw["active_feature"] = "profile"
    elif change == "frame":
        sketch["plane"]["origin"] = [1, 0, 0]
    elif change == "height":
        raw["features"][1]["params"]["length"] = 0.5
    else:
        raw["features"].append({"id": "extra", "kind": "sketch_circle", "params": {"radius": 2}})
    before = copy.deepcopy(raw)
    snapshot = part_snapshot.canonical_snapshot(raw)
    assert raw == before
    assert snapshot["canonical_document"] == Document.from_dict(raw).to_dict()
    if change == "height":
        # Snapshot serialization is independent of native sector scale limits.
        monkeypatch.setattr(
            assembly_service, "regenerate", lambda *a, **k: pytest.fail("replayed source")
        )
        response = assembly_service.run_assembly_action(
            mixed_assembly(Document.from_dict(raw)), result_version=3, kernel=object()
        )
        assert not response["ok"] and response["error"]["code"] == "unsupported_profile_scale"
        assert response["result"]["source_replays"] == []


def test_resolved_height_policy_remains_before_native_but_after_snapshot(monkeypatch):
    document = sector_document(height="missing + 2")
    assert part_snapshot.canonical_snapshot(document.to_dict())["content_hash"]
    monkeypatch.setattr(
        assembly_service, "regenerate", lambda *a, **k: pytest.fail("replayed source")
    )
    response = assembly_service.run_assembly_action(
        mixed_assembly(document), result_version=3, kernel=object()
    )
    assert not response["ok"] and response["error"]["code"] == "unknown_parameter"
    assert response["result"]["source_replays"] == []


@pytest.mark.parametrize("action", sorted(assembly_service.ASSEMBLY_ACTIONS))
def test_mixed_replay_check_and_sample_carry_full_version3_source_evidence(action, monkeypatch):
    calls, bodies = install_replay_double(monkeypatch)
    kernel, candidate = QueryDouble(), mixed_assembly()
    response = assembly_service.run_assembly_action(
        candidate,
        action,
        result_version=3,
        kernel=kernel,
        coordinates={"slide": 25, "fixed": 0},
        requirements=None if action == "assembly_replay" else [],
        samples={"joint_id": "slide", "values": [25, 30]} if action == "assembly_sample" else None,
    )
    assert response["ok"], response["error"]
    assert response["result_version"] == response["request"]["result_version"] == 3
    assert calls == [("box", 3), ("sector", 3)]
    assert kernel.checks == ["box", "sector"]
    assert len(response["report"]["poses"]) == (2 if action == "assembly_sample" else 1)
    for row in response["result"]["source_replays"]:
        assert set(row) == {"source_document_id", "source_digest", "status", "features", "replay"}
        assert row["replay"] == bodies[row["source_document_id"]]
        assert row["features"] == [
            {key: feature[key] for key in ("id", "status", "error", "stats", "output")}
            for feature in row["replay"]["features"]
        ]
    assert response["request_fingerprint"] == fingerprint(response["request"])
    assert AssemblyDocument.from_json(candidate.to_json()).to_json() == candidate.to_json()


def test_failed_source_retains_full_replay_but_never_publishes_any_part(monkeypatch):
    calls, bodies = install_replay_double(monkeypatch, failed_source="sector")
    response = assembly_service.run_assembly_action(
        mixed_assembly(), result_version=3, kernel=QueryDouble()
    )
    assert not response["ok"] and response["error"]["code"] == "source_replay_failed"
    assert calls == [("box", 3), ("sector", 3)]
    assert response["result"]["source_replays"][-1]["replay"] == bodies["sector"]
    assert response["result"]["parts"] == response["report"]["poses"] == []


def test_source_update_replays_complete_candidate_and_preserves_all_literal_identity(monkeypatch):
    install_replay_double(monkeypatch)
    original = mixed_assembly()
    before = original.to_json()
    response = assembly_service.preflight_source_update(
        original,
        "sector",
        sector_document(height=20),
        result_version=3,
        kernel=QueryDouble(),
    )
    assert response["ok"] and response["update"]["affected_instances"] == ["moving", "reused"]
    candidate = AssemblyDocument.from_dict(response["update"]["candidate"])
    assert candidate.joints == original.joints and candidate.instances == original.instances
    assert [p.mate_frames for p in candidate.parts] == [p.mate_frames for p in original.parts]
    assert candidate.source_hashes["sector"] != original.source_hashes["sector"]
    assert original.to_json() == before


@pytest.mark.parametrize("version", [1, 2])
def test_old_versions_retain_summary_only_and_reject_mixed_sources(version, monkeypatch):
    install_replay_double(monkeypatch)
    candidate = mixed_assembly()
    denied = assembly_service.run_assembly_action(
        candidate, result_version=version, kernel=object()
    )
    assert not denied["ok"] and denied["error"]["code"] == "unsupported_result_version"
    assert denied["result"]["source_replays"] == []
    legacy = replace(
        candidate,
        part_sources=tuple(
            PartSource.from_document(replace(box_document(), id=source.id))
            for source in candidate.part_sources
        ),
        parts=tuple(
            replace(
                part, source_digest=replace(box_document(), id=part.source_document_id).content_hash
            )
            for part in candidate.parts
        ),
    )
    response = assembly_service.run_assembly_action(
        legacy, result_version=version, kernel=QueryDouble()
    )
    assert response["ok"]
    assert ("result_version" in response) is (version == 2)
    assert ("result_version" in response["request"]) is (version == 2)
    for row in response["result"]["source_replays"]:
        assert set(row) == {"source_document_id", "source_digest", "status", "features"}
        assert all(
            set(feature)
            == {"id", "status", "error", "stats"} | ({"output"} if version == 2 else set())
            for feature in row["features"]
        )


@pytest.mark.parametrize(
    "owner",
    [
        "part_snapshot",
        "assembly_service",
        "assembly_protocol",
        "profile_adapter_v3",
        "sketch_protocol_v3",
    ],
)
def test_assembly3_requires_each_actual_owner_and_companion_marker(owner, monkeypatch):
    monkeypatch.chdir(ROOT)
    module = importlib.import_module("mechanical_cad." + owner)
    monkeypatch.setattr(module, "BACKEND_CAPABILITIES", frozenset())
    monkeypatch.setattr(
        sidecar, "_process_legacy_request", lambda request: pytest.fail("dispatched")
    )
    response = sidecar.process_request(guarded(operation()))
    assert response["error"]["code"] == "backend_capability_missing"
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch"
    assert "mcad.assembly-result/3" in response["backend_receipt"]["missing_capabilities"]


@pytest.mark.parametrize(
    "owner,entrypoint,action",
    [
        ("part_snapshot", "canonical_snapshot", "canonical_snapshot"),
        ("part_snapshot", "validate_snapshot_source", "canonical_snapshot"),
        ("assembly_service", "run_assembly_action", "assembly_replay"),
        ("assembly_protocol", "process_assembly_request", "assembly_replay"),
    ],
)
def test_copied_capability_marker_cannot_relabel_foreign_functions(
    owner, entrypoint, action, monkeypatch
):
    monkeypatch.chdir(ROOT)
    module = importlib.import_module("mechanical_cad." + owner)
    monkeypatch.setattr(module, entrypoint, lambda *args, **kwargs: None)
    request = (
        operation()
        if action == "assembly_replay"
        else {
            "protocol_version": 1,
            "action": action,
            "document": sector_document().to_dict(),
        }
    )
    monkeypatch.setattr(
        sidecar, "_process_legacy_request", lambda request: pytest.fail("dispatched")
    )
    response = sidecar.process_request(guarded(request))
    assert response["error"]["code"] == "backend_capability_missing"
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch"


def test_snapshot3_real_process_is_native_free_and_assembly3_preflight_error_is_stamped():
    script = """
import builtins, runpy
original = builtins.__import__
blocked = {'OCP', 'slvs', 'bpy', 'engine', 'actions', 'kernel_ocp', 'sketch_solver',
           'profile_region', 'profile_adapter_v3', 'assembly_service'}
def isolated(name, *args, **kwargs):
    if any(piece in blocked for piece in name.split('.')):
        raise AssertionError('snapshot imported geometry: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = isolated
runpy.run_module('mechanical_cad.sidecar', run_name='__main__')
"""
    request = guarded(
        {
            "protocol_version": 1,
            "action": "canonical_snapshot",
            "document": sector_document(height="unresolved + 1").to_dict(),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-S", "-B", "-c", script],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    response = json.loads(completed.stdout)
    assert response["ok"] and "result_version" not in response
    assert response["backend_receipt"]["confirmed_capabilities"] == sorted(
        {
            "mcad.backend-contract/1",
            "mcad.snapshot-sketch3/1",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-S", "-B", "-m", "mechanical_cad.sidecar"],
        input=json.dumps(operation(unexpected=True)),
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        timeout=10,
    )
    response = json.loads(completed.stdout)
    assert completed.returncode == 1 and response["result_version"] == 3
    assert response["result"] is None and response["error"]["code"] == "invalid_request"
