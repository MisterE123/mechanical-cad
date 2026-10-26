import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]


pytestmark = pytest.mark.kernel


def run_sidecar(request=None, raw=None):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    process = subprocess.run(
        [sys.executable, "-m", "mechanical_cad.sidecar"],
        input=json.dumps(request) if raw is None else raw,
        text=True,
        capture_output=True,
        timeout=60,
        env=env,
    )
    return process, json.loads(process.stdout)


def test_legacy_protocol_request_and_response_are_unchanged(plate):
    request = {
        "protocol_version": 1,
        "document": plate.to_dict(),
        "options": {"linear_deflection": 0.1},
    }
    old = {
        "protocol_version": 1,
        "ok": True,
        "result": regenerate(plate, OCPKernel()).result,
        "error": None,
    }
    assert process_request(request) == old
    assert process_request({**request, "action": "replay"}) == old
    assert set(old) == {"protocol_version", "ok", "result", "error"}


def test_geometry_check_action_is_read_only_and_machine_readable(plate, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    process, result = run_sidecar(
        {
            "protocol_version": 1,
            "action": "check_geometry",
            "document": plate.to_dict(),
            "options": {"linear_deflection": 0.03},
        }
    )
    assert process.returncode == 0, process.stderr
    assert result["protocol_version"] == 1 and result["ok"]
    assert result["result"]["document_hash"] == plate.content_hash
    assert result["geometry_check"]["brep"]["solids"] == 1
    assert result["geometry_check"]["mesh"]["watertight"] is True
    assert result["export"] is None and result["error"] is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("action,suffix", [("export_step", ".step"), ("export_stl", ".stl")])
def test_explicit_export_writes_exact_selected_path_and_returns_single_json(
    plate, tmp_path, action, suffix
):
    destination = tmp_path / ("pièce selected 1" + suffix)
    process, result = run_sidecar(
        {
            "protocol_version": 1,
            "action": action,
            "document": plate.to_dict(),
            "destination": str(destination),
            "options": {"linear_deflection": 0.03},
        }
    )
    assert process.returncode == 0, process.stderr
    assert result["ok"] and result["action"] == action
    assert result["export"]["destination"] == str(destination)
    assert result["export"]["document_hash"] == plate.content_hash
    assert destination.stat().st_size == result["export"]["bytes"]
    assert list(tmp_path.iterdir()) == [destination]


def test_failed_replay_response_keeps_current_per_feature_diagnostics_and_existing_file(
    plate, tmp_path
):
    destination = tmp_path / "part.step"
    destination.write_bytes(b"keep")
    process, result = run_sidecar(
        {
            "protocol_version": 1,
            "action": "export_step",
            "document": plate.with_parameter("width", -1).to_dict(),
            "destination": str(destination),
        }
    )
    assert process.returncode == 1
    assert result["error"]["code"] == "regeneration_failed"
    assert result["result"]["status"] == "failed"
    assert result["result"]["features"][-1]["status"] == "blocked"
    assert result["export"] is None
    assert destination.read_bytes() == b"keep"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize(
    "update,code",
    [
        ({"action": "run_python"}, "invalid_action"),
        ({"action": []}, "invalid_action"),
        ({"action": None}, "invalid_action"),
        ({"action": "replay", "destination": "anything.step"}, "invalid_request"),
        ({"destination": "anything.step"}, "invalid_request"),
        ({"action": "check_geometry", "destination": None}, "invalid_request"),
        ({"action": "export_step"}, "invalid_destination"),
        ({"action": "export_stl", "destination": ""}, "invalid_destination"),
        ({"action": "export_step", "destination": 123}, "invalid_destination"),
        ({"action": "export_step", "destination": "bad\0path"}, "invalid_destination"),
        ({"command": "echo secret"}, "invalid_request"),
        ({"script": "print('hello')"}, "invalid_request"),
        ({"options": {"overwrite": True}}, "invalid_request"),
        ({"options": {"destination": "path.step"}}, "invalid_request"),
        ({"options": {"action": "export_step"}}, "invalid_request"),
    ],
)
def test_unknown_actions_fields_and_implicit_writes_fail_closed(plate, tmp_path, update, code):
    process, result = run_sidecar({"protocol_version": 1, "document": plate.to_dict(), **update})
    assert process.returncode == 1
    assert not result["ok"] and result["error"]["code"] == code
    assert result["result"] is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "field,value",
    [("action", "export_step"), ("destination", "part.step"), ("command", "python -c pass")],
)
def test_canonical_document_cannot_request_export(plate, tmp_path, field, value):
    document = {**plate.to_dict(), field: value}
    process, result = run_sidecar({"protocol_version": 1, "document": document})
    assert process.returncode == 1
    assert result["error"]["code"] == "invalid_document"
    assert result["result"] is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "raw",
    [
        '{"protocol_version":1,"protocol_version":1}',
        '{"protocol_version":1,"action":"replay","action":"export_step"}',
        "not JSON",
    ],
)
def test_duplicate_fields_are_rejected_before_actions(raw):
    process, result = run_sidecar(raw=raw)
    assert process.returncode == 1
    assert result["error"]["code"] == "invalid_json"


def test_new_action_invalid_schema_preserves_existing_destination(plate, tmp_path):
    destination = tmp_path / "previous.step"
    destination.write_bytes(b"preserve")
    process, result = run_sidecar(
        {
            "protocol_version": 1,
            "action": "export_step",
            "destination": str(destination),
            "document": {**plate.to_dict(), "unexpected": "not allowed"},
        }
    )
    assert process.returncode == 1
    assert result["error"]["code"] == "invalid_document" and result["result"] is None
    assert destination.read_bytes() == b"preserve"
    assert list(tmp_path.iterdir()) == [destination]
