"""Protocol failure testing without importing Blender or a native CAD library."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "mcad_test_bridge", ROOT / "blender_addon" / "mechanical_cad_blender" / "bridge.py"
)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


@pytest.fixture
def configuration(tmp_path):
    (tmp_path / "src" / "mechanical_cad").mkdir(parents=True)
    executable = tmp_path / "sidecar-python"
    executable.touch()
    return {"project_root": str(tmp_path), "python_executable": str(executable)}


def response(**updates):
    value = {
        "protocol_version": 1,
        "ok": True,
        "result": {"document_id": "doc", "status": "ok", "features": []},
        "error": None,
    }
    value.update(updates)
    return value


def process(value, returncode=0):
    return subprocess.CompletedProcess([], returncode, json.dumps(value), "")


def test_subprocess_arguments_are_safe_and_isolated(monkeypatch, configuration):
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return process(response())

    monkeypatch.setattr(bridge.subprocess, "run", run)
    monkeypatch.setenv("PYTHONHOME", "/wrong/blender/python")
    result = bridge.replay({"id": "doc"}, **configuration)
    assert result["status"] == "ok"
    args, kwargs = calls[0]
    assert args[0][1:] == ["-m", "mechanical_cad.sidecar"]
    assert "shell" not in kwargs
    assert "PYTHONHOME" not in kwargs["env"]
    assert kwargs["env"]["PYTHONNOUSERSITE"] == "1"
    assert kwargs["timeout"] == 60
    assert json.loads(kwargs["input"])["document"]["id"] == "doc"


@pytest.mark.parametrize(
    "exception,match",
    [
        (subprocess.TimeoutExpired("sidecar", 1), "timed out"),
        (OSError("not executable"), "Could not start"),
    ],
)
def test_process_failures_are_actionable(monkeypatch, configuration, exception, match):
    def run(*args, **kwargs):
        raise exception

    monkeypatch.setattr(bridge.subprocess, "run", run)
    with pytest.raises(bridge.BridgeError, match=match):
        bridge.replay({"id": "doc"}, **configuration)


@pytest.mark.parametrize(
    "value,match",
    [
        ([], "protocol mismatch"),
        (response(protocol_version=2), "protocol mismatch"),
        (response(ok="yes"), "success flag"),
        (response(result=None), "malformed replay"),
        (response(result={"document_id": "other", "features": []}), "different document"),
        (
            response(
                ok=False,
                result=None,
                error={"code": "invalid_dimension", "message": "width negative"},
            ),
            "width negative",
        ),
        (response(ok=False, result=None, error="bad"), "malformed error"),
    ],
)
def test_malformed_response_fails_closed(monkeypatch, configuration, value, match):
    monkeypatch.setattr(bridge.subprocess, "run", lambda *args, **kwargs: process(value))
    with pytest.raises(bridge.BridgeError, match=match):
        bridge.replay({"id": "doc"}, **configuration)


def test_failed_replay_can_return_per_feature_diagnostics(monkeypatch, configuration):
    result = {
        "document_id": "doc",
        "status": "failed",
        "features": [{"id": "bad", "status": "failed"}],
    }
    monkeypatch.setattr(
        bridge.subprocess,
        "run",
        lambda *args, **kwargs: process(response(ok=False, result=result), 1),
    )
    assert bridge.replay({"id": "doc"}, **configuration) == result


def test_success_with_nonzero_exit_is_rejected(monkeypatch, configuration):
    monkeypatch.setattr(bridge.subprocess, "run", lambda *args, **kwargs: process(response(), 1))
    with pytest.raises(bridge.BridgeError, match="despite reporting success"):
        bridge.replay({"id": "doc"}, **configuration)


def test_invalid_json_reports_bounded_stderr(monkeypatch, configuration):
    monkeypatch.setattr(
        bridge.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], -11, "", "native crash"),
    )
    with pytest.raises(bridge.BridgeError, match="native crash"):
        bridge.replay({"id": "doc"}, **configuration)


@pytest.mark.parametrize("payload", ['{"width":1,"width":2}', '{"width":NaN}', "[]", "not json"])
def test_file_parser_rejects_ambiguous_or_nonfinite_json(payload):
    with pytest.raises(bridge.BridgeError):
        bridge.parse_document_json(payload)


def test_missing_source_path_is_actionable(tmp_path):
    with pytest.raises(bridge.BridgeError, match="Project Root"):
        bridge.resolve_configuration(str(tmp_path), str(tmp_path / "python"))


def test_nonfinite_document_does_not_launch_process(monkeypatch, configuration):
    monkeypatch.setattr(
        bridge.subprocess, "run", lambda *args, **kwargs: pytest.fail("must not launch")
    )
    with pytest.raises(bridge.BridgeError, match="finite JSON"):
        bridge.replay({"id": "doc", "value": float("nan")}, **configuration)


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_response_version_requires_an_integer(monkeypatch, configuration, version):
    monkeypatch.setattr(
        bridge.subprocess,
        "run",
        lambda *args, **kwargs: process(response(protocol_version=version)),
    )
    with pytest.raises(bridge.BridgeError, match="protocol mismatch"):
        bridge.replay({"id": "doc"}, **configuration)
