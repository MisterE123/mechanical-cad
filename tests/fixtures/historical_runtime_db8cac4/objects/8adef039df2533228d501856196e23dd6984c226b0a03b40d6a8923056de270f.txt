"""Pure same-invocation export wiring; no native geometry qualification implied."""

import builtins
import copy
import inspect
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import FunctionType

import pytest

from mechanical_cad import assembly_export, assembly_protocol, assembly_service, backend_contract
from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Frame,
    Instance,
    Joint,
    MateFrame,
    PartDefinition,
    PartSource,
)
from mechanical_cad.assembly_policy import fingerprint
from mechanical_cad.assembly_requirements import VerificationPreset
from mechanical_cad.engine import Replay
from mechanical_cad.errors import CADException
from mechanical_cad.outputs import SolidOutput

ROOT = Path(__file__).resolve().parents[2]
CAPABILITY = "mcad.assembly-step-export/1"


@pytest.fixture
def assembly(plate):
    sources = tuple(PartSource.from_document(doc) for doc in (plate, replace(plate, id="other")))
    parts = tuple(
        PartDefinition(
            name,
            source.source_digest,
            source.id,
            source.document.active_feature,
            (MateFrame("origin"),),
            f"Definition {name}",
        )
        for name, source in (("first", sources[0]), ("second", sources[1]), ("unused", sources[0]))
    )
    return AssemblyDocument(
        "assembly",
        "Shared assembly",
        sources,
        parts,
        (Instance("base", "first"), Instance("moving", "second"), Instance("reused", "second")),
        (
            Joint("slide", "slider", "base", "moving", "origin", "origin", 25),
            Joint("rotate", "revolute", "moving", "reused", "origin", "origin", 0.7),
        ),
        "base",
        ground=Frame((3, 4, 5)),
        verification_presets=(
            VerificationPreset("clear", "Interference only", (), kind="interference_only"),
        ),
        active_verification_preset="clear",
    )


def operation(assembly, path, *, version=2):
    return {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "assembly": assembly.to_dict(),
        "action": "assembly_export_step",
        "path": str(path),
        "result_version": version,
    }


class KernelDouble:
    def __init__(self, *, verdict="pass", writer="success"):
        self.verdict, self.writer = verdict, writer
        self.checks, self.placements, self.exports = [], [], []

    def runtime_versions(self):
        return {"adapter": "pure-test-double"}

    def manufacturing_check(self, shape, deflection):
        self.checks.append(shape)
        return {"brep": {"solids": 1}, "mesh": {}, "linear_deflection_mm": deflection}

    def transformed(self, shape, frame, **kwargs):
        self.placements.append((shape, frame.to_dict()))
        return shape

    def pair_check(self, *args, **kwargs):
        if self.verdict == "error":
            raise CADException("query_failed", "Test query failure.")
        return {
            "complete": self.verdict != "incomplete",
            "known_interference": self.verdict == "fail",
            "known_clearance_violation": False,
            "clearance_verdict": "pass_at_pose" if self.verdict == "pass" else "indeterminate",
        }

    def export_assembly_step(self, name, parts, instances, path):
        self.exports.append((name, parts, instances, path))
        if self.writer != "empty":
            path.write_bytes(b"STEP assembly test double")
        if self.writer == "failure":
            raise CADException("write_failed", "Test writer failure.")


@pytest.fixture
def replay_double(monkeypatch):
    calls, shapes = [], {}

    def replay(document, kernel, *, linear_deflection, result_version):
        calls.append((document.id, kernel, result_version))
        shape = shapes.setdefault(document.id, object())
        features = [
            {
                "id": feature.id,
                "status": "ok",
                "error": None,
                "stats": {"solids": 1},
                "output": {"kind": "solid", "display": "mesh"},
                "mesh": {"vertices": [], "triangles": [], "triangle_face_ids": []},
                "topology": [],
            }
            for feature in document.features
        ]
        body = {
            "document_id": document.id,
            "document_hash": document.content_hash,
            "active_feature": document.active_feature,
            "units": "mm",
            "parameters": {},
            "status": "ok",
            "features": features,
            "result_version": result_version,
        }
        return Replay(body, {}, {document.active_feature: SolidOutput(shape)})

    monkeypatch.setattr(assembly_service, "regenerate", replay)
    monkeypatch.setattr(assembly_service, "runtime_versions", lambda: {"test": "pure"})
    return calls, shapes


@pytest.mark.parametrize("version", [2, 3])
def test_fresh_check_once_shared_definitions_exact_pose_and_complete_nested_response(
    assembly, tmp_path, replay_double, version
):
    calls, shapes = replay_double
    kernel = KernelDouble()
    path = tmp_path / "assembly.step"
    request = operation(assembly, path, version=version)
    before = copy.deepcopy(request)
    response = assembly_export.run_assembly_step_export(request, kernel=kernel)
    assert request == before
    assert response["ok"] is True and response["error"] is None
    assert set(response) == {
        "protocol_version",
        "kind",
        "assembly_protocol_version",
        "action",
        "result_version",
        "input_fingerprint",
        "ok",
        "error",
        "result",
        "export",
    }
    assert response["input_fingerprint"] == fingerprint(request)
    assert len(calls) == 2 and all(call[1] is kernel for call in calls)
    assert len(kernel.checks) == 2 and len(kernel.placements) == 3
    assert len(kernel.exports) == 1
    name, parts, instances, temporary = kernel.exports[0]
    assert name == assembly.name and temporary.parent == path.parent and temporary != path
    assert {part["id"] for part in parts} == {"first", "second"}
    assert parts[0]["shape"] is shapes[assembly.part_sources[0].id]
    assert parts[1]["shape"] is shapes[assembly.part_sources[1].id]
    assert [instance["part_id"] for instance in instances] == ["first", "second", "second"]
    nested = response["result"]
    check_request = {key: value for key, value in request.items() if key != "path"}
    check_request["action"] = "assembly_check"
    assert nested["input_fingerprint"] == fingerprint(check_request)
    assert nested["action"] == "assembly_check" and nested["report"]["passed"] is True
    pose = nested["report"]["poses"][0]["pose"]
    assert pose == nested["report"]["base_pose"]
    assert {row["id"]: row["frame"] for row in instances} == pose["transforms"]
    assert [row["frame"] for row in instances] == [row[1] for row in kernel.placements]
    assert response["export"] == {
        "format": "STEP",
        "units": "mm",
        "path": str(path),
        "atomic_write": True,
        "bytes_written": path.stat().st_size,
        "definition_count": 2,
        "instance_count": 3,
        "assembly_digest": assembly.content_hash,
        "pose_digest": pose["pose_digest"],
        "preset_id": "clear",
        "request_fingerprint": nested["request_fingerprint"],
        "report_fingerprint": nested["report_fingerprint"],
    }
    assert path.read_bytes() == b"STEP assembly test double"
    assert list(tmp_path.iterdir()) == [path]
    ordinary = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "input_fingerprint": fingerprint(check_request),
        **assembly_service.run_assembly_action(
            assembly, "assembly_check", result_version=version, kernel=KernelDouble()
        ),
    }
    assert nested == ordinary


@pytest.mark.parametrize("verdict", ["fail", "incomplete", "error"])
def test_failed_or_incomplete_current_check_never_writes(
    assembly, tmp_path, replay_double, verdict
):
    path = tmp_path / "existing.step"
    path.write_bytes(b"old")
    kernel = KernelDouble(verdict=verdict)
    response = assembly_export.run_assembly_step_export(operation(assembly, path), kernel=kernel)
    assert response["ok"] is False and response["export"] is None
    assert response["error"]["code"] == "assembly_export_blocked"
    assert response["result"]["action"] == "assembly_check"
    assert response["result"]["report"]["passed"] is False
    assert not kernel.exports and path.read_bytes() == b"old"


@pytest.mark.parametrize("writer,code", [("failure", "write_failed"), ("empty", "empty_export")])
def test_atomic_writer_failures_preserve_destination_and_check(
    assembly, tmp_path, replay_double, writer, code
):
    path = tmp_path / "existing.step"
    path.write_bytes(b"old")
    response = assembly_export.run_assembly_step_export(
        operation(assembly, path), kernel=KernelDouble(writer=writer)
    )
    assert response["ok"] is False and response["export"] is None
    assert response["error"]["code"] == code
    assert response["result"]["report"]["passed"] is True
    assert path.read_bytes() == b"old" and list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "path", [None, True, 5, "", " ", "file.step", "/", "/tmp/", "/tmp/.", "/tmp/..", "/tmp/a\0b"]
)
def test_invalid_destination_rejected_before_replay(assembly, replay_double, path):
    request = operation(assembly, "/tmp/output.step")
    request["path"] = path
    with pytest.raises(CADException) as exc:
        assembly_export.run_assembly_step_export(request, kernel=KernelDouble())
    assert exc.value.code == "invalid_destination" and replay_double[0] == []


@pytest.mark.parametrize("version", [None, 1, True, 2.0, "3", 4])
def test_result_version_requires_typed_two_or_three(assembly, replay_double, version):
    with pytest.raises(CADException) as exc:
        assembly_export.run_assembly_step_export(
            operation(assembly, "/tmp/output.step", version=version), kernel=KernelDouble()
        )
    assert exc.value.code == "unsupported_result_version" and replay_double[0] == []


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("surprise", None, "invalid_request"),
        ("protocol_version", True, "unsupported_protocol"),
        ("kind", "other", "unsupported_protocol"),
        ("assembly_protocol_version", True, "unsupported_protocol"),
        ("action", "assembly_check", "invalid_action"),
        ("result_version", 4, "unsupported_result_version"),
        ("path", None, "invalid_destination"),
        ("path", "/tmp/", "invalid_destination"),
    ],
)
def test_export_rejects_invalid_envelope_before_part_export_import(
    assembly, replay_double, monkeypatch, field, value, code
):
    request = operation(assembly, "/tmp/output.step")
    request[field] = value
    original_import = builtins.__import__

    def isolated(name, *args, **kwargs):
        if "actions" in name.split("."):
            raise AssertionError("Rejected export imported Part export helpers")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", isolated)
    with pytest.raises(CADException) as exc:
        assembly_export.run_assembly_step_export(request, kernel=KernelDouble())
    assert exc.value.code == code and replay_double[0] == []


@pytest.mark.parametrize(
    "field",
    ["coordinates", "requirements", "policy", "samples", "preset_id", "destination", "surprise"],
)
def test_export_envelope_rejects_overrides_and_unknown_fields(assembly, replay_double, field):
    request = operation(assembly, "/tmp/output.step")
    request[field] = None
    with pytest.raises(CADException) as exc:
        assembly_protocol.process_assembly_request(request)
    assert exc.value.code == "invalid_request" and replay_double[0] == []


def test_export_envelope_requires_every_field(assembly, replay_double):
    request = operation(assembly, "/tmp/output.step")
    for field in request:
        reduced = {key: value for key, value in request.items() if key != field}
        with pytest.raises(CADException):
            assembly_export.run_assembly_step_export(reduced, kernel=KernelDouble())
    assert replay_double[0] == []


def test_active_preset_and_file_destination_required_before_native(
    assembly, tmp_path, replay_double
):
    with pytest.raises(CADException, match="active verification preset"):
        assembly_export.run_assembly_step_export(
            operation(replace(assembly, active_verification_preset=None), tmp_path / "out.step"),
            kernel=KernelDouble(),
        )
    with pytest.raises(CADException, match="absolute export file"):
        assembly_export.run_assembly_step_export(
            operation(assembly, tmp_path), kernel=KernelDouble()
        )
    assert replay_double[0] == []


@pytest.mark.parametrize(
    "action,kwargs",
    [
        ("assembly_replay", {}),
        ("assembly_check", {"coordinates": {}}),
        ("assembly_check", {"coordinates": {"slide": 25, "rotate": 0.7}}),
    ],
)
def test_private_native_bundle_only_for_saved_current_configured_check(
    assembly, replay_double, action, kwargs
):
    response, native = assembly_service._run_assembly_action_with_native(
        assembly, action, result_version=2, kernel=KernelDouble(), **kwargs
    )
    assert response["ok"] is True and native is None


def test_public_service_signature_and_action_set_unchanged(assembly, replay_double):
    assert list(inspect.signature(assembly_service.run_assembly_action).parameters) == [
        "assembly",
        "action",
        "coordinates",
        "requirements",
        "policy",
        "samples",
        "preset_id",
        "result_version",
        "kernel",
    ]
    assert assembly_service.ASSEMBLY_ACTIONS == {
        "assembly_replay",
        "assembly_check",
        "assembly_sample",
    }
    response = assembly_service.run_assembly_action(
        assembly, "assembly_export_step", kernel=KernelDouble()
    )
    assert response["error"]["code"] == "invalid_action" and replay_double[0] == []
    request = operation(assembly, "/tmp/out.step")
    request["action"] = "assembly_check"
    with pytest.raises(CADException) as exc:
        assembly_protocol.process_assembly_request(request)
    assert exc.value.code == "invalid_request"


def test_public_service_preserves_non_json_action_rejection(assembly, replay_double):
    class InvalidAction:
        def __eq__(self, other):
            raise AssertionError("Rejected action must not be evaluated")

    with pytest.raises(CADException) as exc:
        assembly_service.run_assembly_action(assembly, InvalidAction(), kernel=KernelDouble())
    assert exc.value.code == "invalid_request" and replay_double[0] == []


@pytest.mark.parametrize("version", [2, 3])
def test_capability_minimum_and_observed_owner_links(assembly, monkeypatch, version):
    monkeypatch.chdir(ROOT)
    request = operation(assembly, "/tmp/output.step", version=version)
    required = backend_contract.minimum_capabilities(request)
    assert {
        backend_contract.CONTRACT_CAPABILITY,
        backend_contract.SOLVER_CAPABILITY,
        CAPABILITY,
    } <= required
    if version == 3:
        assert {"mcad.sketch-arcs/1", "mcad.part-result/3", "mcad.assembly-result/3"} <= required
    _, supported, mismatch = backend_contract.observe_backend(request)
    assert required <= supported and mismatch is False


@pytest.mark.parametrize(
    "module,name",
    [
        (assembly_export, "run_assembly_step_export"),
        (assembly_protocol, "process_assembly_request"),
        (assembly_service, "_run_assembly_action_with_native"),
    ],
)
def test_marker_or_reexport_cannot_advertise_export_owner(assembly, monkeypatch, module, name):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(module, name, lambda *args, **kwargs: None)
    _, supported, _ = backend_contract.observe_backend(operation(assembly, "/tmp/out.step"))
    assert CAPABILITY not in supported


def test_missing_capability_rejects_before_dispatch(assembly, monkeypatch):
    monkeypatch.chdir(ROOT)
    request = operation(assembly, "/tmp/output.step")
    guarded = {
        **request,
        "backend_contract": {
            "version": 1,
            "request_id": "1" * 32,
            "required_capabilities": sorted(backend_contract.minimum_capabilities(request)),
        },
    }
    monkeypatch.setattr(assembly_export, "BACKEND_CAPABILITIES", frozenset())
    calls = []
    response = backend_contract.process_guarded_request(
        guarded, lambda request: calls.append(request)
    )
    assert response["error"]["code"] == "backend_capability_missing"
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch" and not calls


def test_omitted_new_minimum_is_rejected(assembly):
    request = operation(assembly, "/tmp/output.step")
    with pytest.raises(CADException) as exc:
        backend_contract.prepare_request(
            {
                **request,
                "backend_contract": {
                    "version": 1,
                    "request_id": "1" * 32,
                    "required_capabilities": sorted(
                        backend_contract.minimum_capabilities(request) - {CAPABILITY}
                    ),
                },
            }
        )
    assert exc.value.code == "backend_contract_invalid"


def test_exact_early_protocol_branch_uses_export_service(
    assembly, tmp_path, replay_double, monkeypatch
):
    kernel = KernelDouble()
    monkeypatch.setattr(
        assembly_protocol,
        "run_assembly_step_export",
        lambda request: assembly_export.run_assembly_step_export(request, kernel=kernel),
    )
    response = assembly_protocol.process_assembly_request(
        operation(assembly, tmp_path / "out.step")
    )
    assert response["ok"] is True and len(kernel.exports) == 1


def test_source_failure_retains_complete_nested_check_and_old_destination(
    assembly, tmp_path, replay_double, monkeypatch
):
    def failed(*args, **kwargs):
        raise CADException("source_failed", "Synthetic replay failure.")

    monkeypatch.setattr(assembly_service, "regenerate", failed)
    path = tmp_path / "out.step"
    path.write_bytes(b"old")
    kernel = KernelDouble()
    response = assembly_export.run_assembly_step_export(operation(assembly, path), kernel=kernel)
    assert response["ok"] is False and response["export"] is None
    assert response["result"]["error"]["code"] == "source_failed"
    assert response["result"]["report_fingerprint"]
    assert response["result"]["result"]["canonical_assembly"] == assembly.to_dict()
    assert not kernel.exports and path.read_bytes() == b"old"


@pytest.mark.parametrize(
    "module,name",
    [
        (assembly_export, "run_assembly_step_export"),
        (assembly_protocol, "process_assembly_request"),
        (assembly_service, "_run_assembly_action_with_native"),
    ],
)
def test_export_capability_requires_exact_code_origin(assembly, monkeypatch, module, name):
    monkeypatch.chdir(ROOT)
    original = getattr(module, name)
    foreign = FunctionType(
        original.__code__.replace(co_filename=__file__), original.__globals__, original.__name__
    )
    monkeypatch.setattr(module, name, foreign)
    _, supported, mismatch = backend_contract.observe_backend(operation(assembly, "/tmp/out.step"))
    assert CAPABILITY not in supported and mismatch is True


def test_export_observation_is_native_free_in_fresh_process(assembly):
    script = """
import builtins, json, sys
original = builtins.__import__
def isolated(name, *args, **kwargs):
    if any(piece in {'OCP', 'slvs', 'bpy', 'kernel_ocp', 'actions'} for piece in name.split('.')):
        raise AssertionError('forbidden observation import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = isolated
from mechanical_cad.backend_contract import minimum_capabilities, observe_backend
request = json.load(sys.stdin)
for version in (2, 3):
    request['result_version'] = version
    _, supported, mismatch = observe_backend(request)
    assert not mismatch
    assert minimum_capabilities(request) <= supported
assert not {'OCP', 'slvs', 'bpy', 'mechanical_cad.kernel_ocp', 'mechanical_cad.actions'} & set(sys.modules)
print('PURE_EXPORT_OBSERVATION_OK')
"""
    completed = subprocess.run(
        [sys.executable, "-S", "-B", "-c", script],
        input=json.dumps(operation(assembly, "/tmp/output.step")),
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "PURE_EXPORT_OBSERVATION_OK"


# Captured from c405435's unmodified public service with this deterministic double.
@pytest.mark.parametrize(
    "version,action,expected",
    [
        (1, "assembly_replay", "fdfd278dfd5d173feae8850ea96f2a09bfc387b50b1eca08b2641cf95b919be8"),
        (1, "assembly_check", "02fe5b8a97c24fc3fff897cc6ea6e860b9cecf95e5925d49a2e5f7dfc55b0a50"),
        (1, "assembly_sample", "86504c7d8ac60c0792f5dbf547fe338265a7981e7b9fa80dc6b931db8df5d1ae"),
        (2, "assembly_replay", "1ad3ca26de54930c8013e8b5cedb6472a8765382f0b1654f5bd4dec97a912995"),
        (2, "assembly_check", "2235b55b5d64d6c8aacc933f9e92f8a5a43d865406ee6ea97ba620fe741c3195"),
        (2, "assembly_sample", "ede91b8b3d6a23fbddcd6bb1221e873a3ddcafa9f67f2e966f9faa3a3d65e636"),
        (3, "assembly_replay", "720b2613c62006cbc5a675542279f9233ce03eb8c7a5b5dddd6dc81304102531"),
        (3, "assembly_check", "4c3bd7d3ff6b43fac3cdb8f885013ac8807c8e2e41b0adf97f7630ffb2d9167d"),
        (3, "assembly_sample", "02602d71dad2559c62ea3c95372d09fa136a184eb0323b43250a7527311a3e72"),
    ],
)
def test_original_service_response_fingerprints_unchanged(
    assembly, replay_double, version, action, expected
):
    options = (
        {
            "coordinates": {"slide": 25, "rotate": 0.7},
            "samples": {"joint_id": "slide", "values": [25, 30]},
        }
        if action == "assembly_sample"
        else {}
    )
    response = assembly_service.run_assembly_action(
        assembly, action, result_version=version, kernel=KernelDouble(), **options
    )
    assert fingerprint(response) == expected


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("writer_failure", [False, True])
def test_actual_export_service_packets_pass_independent_strict_client(
    monkeypatch, tmp_path, version, writer_failure
):
    from test_assembly_export_contracts import export_bridge, pair

    kernels = []
    original = assembly_service.run_assembly_action

    def capture_kernel(*args, **kwargs):
        kernels.append(kwargs["kernel"])
        return original(*args, **kwargs)

    monkeypatch.setattr(assembly_service, "run_assembly_action", capture_kernel)
    request, _ = pair(monkeypatch, version=version, path=str(tmp_path / "actual.step"))
    writes = []

    def write(name, parts, instances, path):
        writes.append(path)
        path.write_bytes(b"Strictly validated synthetic Assembly STEP")
        if writer_failure:
            raise CADException("test_write_failure", "Synthetic writer failed.")

    monkeypatch.setattr(kernels[-1], "export_assembly_step", write, raising=False)
    response = assembly_export.run_assembly_step_export(request, kernel=kernels[-1])
    assert response["ok"] is (not writer_failure)
    assert len(writes) == 1 and response["result"]["report"]["passed"] is True
    if writer_failure:
        assert response["error"]["code"] == "test_write_failure"
    assert export_bridge.validate_response(request, response) == response
