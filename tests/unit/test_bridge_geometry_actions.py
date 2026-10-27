"""Geometry action transport contracts, independently of Blender/native CAD."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "mcad_test_action_bridge", ROOT / "blender_addon" / "mechanical_cad_blender" / "bridge.py"
)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
DOCUMENT = {"id": "doc", "active_feature": "pad", "units": "mm"}
DESTINATION = "/tmp/part with spaces.step"


LINUX_LEGACY_BRIDGE = pytest.mark.skipif(
    sys.platform != "linux",
    reason="Linux legacy bridge admission and mocked-transport integration contract",
)


@pytest.fixture
def configuration(tmp_path):
    (tmp_path / "src" / "mechanical_cad").mkdir(parents=True)
    executable = tmp_path / "sidecar-python"
    executable.touch()
    return {"project_root": str(tmp_path), "python_executable": str(executable)}


def response(action="check_geometry"):
    brep = {"valid": True, "solids": 1, "volume": 125.1234567890123}
    mesh = {"watertight": True, "consistently_oriented": True, "vertex_manifold": True}
    result = {
        "document_id": "doc",
        "document_hash": "a" * 64,
        "active_feature": "pad",
        "status": "ok",
        "units": "mm",
        "features": [{"id": "pad", "status": "ok", "stats": dict(brep)}],
    }
    checks = {"brep": brep, "mesh": mesh, "linear_deflection_mm": 0.1}
    exported = None
    if action != "check_geometry":
        exported = {
            "format": "STEP" if action == "export_step" else "STL",
            "destination": DESTINATION,
            "bytes": 128,
            "units": "mm",
            "atomic_replace": True,
            "document_hash": "a" * 64,
            "active_feature": "pad",
            "linear_deflection_mm": 0.1,
        }
    if action == "export_stl":
        checks.update(
            encoded_mesh=dict(mesh),
            encoding={
                "maximum_vertex_error_mm": 1e-7,
                "allowed_vertex_error_mm": 1e-5,
            },
        )
    return {
        "protocol_version": 1,
        "ok": True,
        "action": action,
        "result": result,
        "geometry_check": checks,
        "export": exported,
        "error": None,
    }


def install_response(monkeypatch, value, returncode=0):
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], returncode, json.dumps(value), "")

    monkeypatch.setattr(bridge.subprocess, "run", run)
    return calls


def invoke(configuration, action="check_geometry"):
    kwargs = {} if action == "check_geometry" else {"destination": DESTINATION}
    return bridge.geometry_action(DOCUMENT, action, **kwargs, **configuration)


@LINUX_LEGACY_BRIDGE
@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_success_keeps_full_precision_and_explicit_request(monkeypatch, configuration, action):
    expected = response(action)
    calls = install_response(monkeypatch, expected)
    actual = invoke(configuration, action)
    assert actual == expected
    assert actual["geometry_check"]["brep"]["volume"] == 125.1234567890123
    args, kwargs = calls[0]
    request = json.loads(kwargs["input"])
    assert request["document"] == DOCUMENT
    assert request["action"] == action
    assert ("destination" in request) is (action != "check_geometry")
    assert args[0][1:] == ["-m", "mechanical_cad.sidecar"]
    assert "shell" not in kwargs and kwargs["env"]["PYTHONNOUSERSITE"] == "1"


@pytest.mark.parametrize(
    "action,destination",
    [
        ("arbitrary_command", None),
        ([], None),
        ("replay", None),
        ("check_geometry", DESTINATION),
        ("export_step", None),
        ("export_step", "relative.step"),
        ("export_stl", ""),
        ("export_stl", "/tmp/part\0.stl"),
        ("export_step", 123),
    ],
)
def test_invalid_request_never_launches_process(monkeypatch, configuration, action, destination):
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k: pytest.fail("must not launch"))
    with pytest.raises(bridge.BridgeError) as raised:
        bridge.geometry_action(DOCUMENT, action, destination=destination, **configuration)
    assert not raised.value.outcome_unknown


@LINUX_LEGACY_BRIDGE
@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_structured_early_failure_is_known_not_transport_uncertainty(
    monkeypatch, configuration, action
):
    value = {
        "protocol_version": 1,
        "ok": False,
        "result": None,
        "error": {"code": "invalid_document", "message": "Correct the feature input."},
    }
    install_response(monkeypatch, value, 1)
    assert invoke(configuration, action) == value


@LINUX_LEGACY_BRIDGE
def test_replay_diagnostics_survive_failed_action(monkeypatch, configuration):
    value = response("export_step")
    value.update(
        ok=False,
        export=None,
        geometry_check=None,
        error={"code": "regeneration_failed", "message": "Correct width."},
    )
    value["result"]["status"] = "failed"
    value["result"]["features"][0].update(status="failed", stats=None)
    install_response(monkeypatch, value, 1)
    assert invoke(configuration, "export_step") == value


@LINUX_LEGACY_BRIDGE
@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_timeout_reports_export_outcome_unknown_without_retry(monkeypatch, configuration, action):
    calls = []

    def run(*args, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired("sidecar", 60)

    monkeypatch.setattr(bridge.subprocess, "run", run)
    with pytest.raises(bridge.BridgeError, match="timed out") as raised:
        invoke(configuration, action)
    assert raised.value.outcome_unknown is (action != "check_geometry")
    assert calls == [1]


@LINUX_LEGACY_BRIDGE
def test_launch_failure_cannot_have_written_export(monkeypatch, configuration):
    def run(*args, **kwargs):
        raise OSError("Interpreter unavailable")

    monkeypatch.setattr(bridge.subprocess, "run", run)
    with pytest.raises(bridge.BridgeError, match="Could not start") as raised:
        invoke(configuration, "export_step")
    assert not raised.value.outcome_unknown


@LINUX_LEGACY_BRIDGE
@pytest.mark.parametrize(
    "path,value",
    [
        (("action",), "check_geometry"),
        (("ok",), "yes"),
        (("protocol_version",), True),
        (("error",), {"code": "unexpected", "message": "error"}),
        (("result", "document_id"), "other"),
        (("result", "active_feature"), "other"),
        (("result", "status"), "failed"),
        (("result", "units"), "inch"),
        (("result", "features"), []),
        (("geometry_check",), None),
        (("geometry_check", "brep", "valid"), False),
        (("geometry_check", "brep", "solids"), True),
        (("geometry_check", "brep", "volume"), -1),
        (("geometry_check", "mesh", "watertight"), False),
        (("geometry_check", "mesh", "vertex_manifold"), 1),
        (("geometry_check", "linear_deflection_mm"), 0.2),
        (("export", "format"), "STL"),
        (("export", "destination"), "/tmp/other.step"),
        (("export", "bytes"), True),
        (("export", "bytes"), 0),
        (("export", "units"), "inch"),
        (("export", "atomic_replace"), False),
        (("export", "document_hash"), "other"),
        (("export", "active_feature"), "other"),
        (("export", "linear_deflection_mm"), 0.2),
    ],
)
def test_inconsistent_export_response_is_unconfirmed(monkeypatch, configuration, path, value):
    data = response("export_step")
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    install_response(monkeypatch, data)
    with pytest.raises(bridge.BridgeError) as raised:
        invoke(configuration, "export_step")
    assert raised.value.outcome_unknown


@LINUX_LEGACY_BRIDGE
@pytest.mark.parametrize(
    "change", ["missing_active", "duplicate_active", "volume_mismatch", "invalid_active"]
)
def test_successful_check_requires_consistent_active_solid(monkeypatch, configuration, change):
    data = response()
    feature = data["result"]["features"][0]
    if change == "missing_active":
        feature["id"] = "other"
    elif change == "duplicate_active":
        data["result"]["features"].append(copy.deepcopy(feature))
    elif change == "volume_mismatch":
        feature["stats"]["volume"] = 9999
    else:
        feature["stats"]["valid"] = False
    install_response(monkeypatch, data)
    with pytest.raises(bridge.BridgeError):
        invoke(configuration)


@LINUX_LEGACY_BRIDGE
@pytest.mark.parametrize(
    "path,value",
    [
        (("encoded_mesh",), None),
        (("encoded_mesh", "watertight"), False),
        (("encoding",), None),
        (("encoding", "maximum_vertex_error_mm"), 0.01),
        (("encoding", "maximum_vertex_error_mm"), True),
        (("encoding", "allowed_vertex_error_mm"), 0.1),
    ],
)
def test_stl_requires_encoded_mesh_and_precision_gates(monkeypatch, configuration, path, value):
    data = response("export_stl")
    target = data["geometry_check"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    install_response(monkeypatch, data)
    with pytest.raises(bridge.BridgeError) as raised:
        invoke(configuration, "export_stl")
    assert raised.value.outcome_unknown


@LINUX_LEGACY_BRIDGE
def test_lost_export_reply_never_claims_file_preservation(monkeypatch, configuration):
    monkeypatch.setattr(
        bridge.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            [], -11, "", "Native worker failed after write"
        ),
    )
    with pytest.raises(bridge.BridgeError, match="may already have been replaced") as raised:
        invoke(configuration, "export_step")
    assert raised.value.outcome_unknown
