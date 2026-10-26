"""Host harness tests use subprocess ports, never native install or downloads."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/qualify_standalone_candidate.py"
spec = importlib.util.spec_from_file_location("standalone_candidate_host", PATH)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    blender, archive, script = (tmp_path / name for name in ("blender", "candidate.zip", "native.py"))
    for path in (blender, archive, script):
        path.write_bytes(b"local test bytes")
    args = {"blender": blender, "archive": archive, "script": script,
                "source_commit": "a" * 40, "version": "1.30.0", "work_root": tmp_path / "new-run"}
    fixture = tmp_path / "fixtures/standalone_constrained_plate.mcad.json"
    fixture.parent.mkdir()
    fixture.write_text("{\"fixture\": true}")
    calls = []
    behavior = {}

    def run(command, **options):
        calls.append((command, options))
        env = options["env"]
        mode = env["MCAD_VERIFY_MODE"]
        result = {"ok": True, "mode": mode, "archive_sha256": host.file_identity(archive)[0],
                      "source_commit": args["source_commit"], "version": args["version"], "checks": ["mocked native check"],
                      "blender": "5.2.2", "interactive_gui": False}
        result.update(behavior.get("payload", {}))
        base = Path(env["MCAD_VERIFY_BASE"])
        receipt = base / "receipts" / (mode + ".json")
        if behavior.get("timeout"):
            options["stdout"].write(b"retained partial output\n")
            raise subprocess.TimeoutExpired(command, options["timeout"])
        if not behavior.get("missing_receipt"):
            receipt.write_text(behavior.get("receipt_text", json.dumps(result)), encoding="utf-8")
        marker = host.MARKER + behavior.get("marker_text", json.dumps(result)) + "\n"
        if behavior.get("missing_marker"):
            marker = "no result here\n"
        if behavior.get("duplicate_marker"):
            marker += marker
        options["stdout"].write(marker.encode())
        return SimpleNamespace(returncode=behavior.get("returncode", 0))

    monkeypatch.setattr(host.subprocess, "run", run)
    return SimpleNamespace(args=args, calls=calls, behavior=behavior)


def test_three_separate_processes_isolated_environment_and_identity(harness, monkeypatch):
    h = harness
    for key in ("MCAD_ROOT", "MCAD_PYTHON", "PYTHONPATH", "BLENDER_USER_SCRIPTS"):
        monkeypatch.setenv(key, "forbidden source path")
    original_env = os.environ.copy()
    result = host.qualify(**h.args)
    assert result["ok"] and len(h.calls) == 3
    assert [call[1]["env"]["MCAD_VERIFY_MODE"] for call in h.calls] == list(host.MODES)
    base = h.args["work_root"]
    for command, options in h.calls:
        assert command == [str(h.args["blender"]), "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(h.args["script"])]
        assert options["timeout"] == 900 and options["check"] is False
        assert options["cwd"] == str(base)
        env = options["env"]
        assert all(key not in env for key in ("MCAD_ROOT", "MCAD_PYTHON", "PYTHONPATH", "BLENDER_USER_SCRIPTS"))
        assert env["BLENDER_USER_CONFIG"] == str(base / "profile/config")
        assert env["BLENDER_USER_EXTENSIONS"] == str(base / "profile/extensions")
        assert env["MCAD_VERIFY_BLENDER_VERSION"] == "5.2.2"
        assert env["TMPDIR"] == env["TMP"] == env["TEMP"] == str(base / "tmp")
        if os.name == "posix":
            assert options["umask"] == 0o022
    assert os.environ == original_env
    assert (base / "artifacts").is_dir()
    assert json.loads((base / "summary.json").read_text()) == result
    assert result["script_sha256"] == host.file_identity(h.args["script"])[0]
    assert result["fixture_sha256"] == host.file_identity(Path(result["fixture"]))[0]
    assert result["archive_bytes"] == len(b"local test bytes") and result["limits"]


@pytest.mark.parametrize("fault", [
    {"missing_receipt": True}, {"missing_marker": True}, {"duplicate_marker": True},
    {"receipt_text": "not-json"}, {"marker_text": "[]"},
    {"receipt_text": '{"ok":true,"ok":true}'}, {"marker_text": '{"ok":NaN}'},
    {"payload": {"ok": False}}, {"payload": {"ok": 1}},
    {"payload": {"mode": "wrong"}}, {"payload": {"archive_sha256": "0" * 64}},
    {"payload": {"source_commit": "b" * 40}}, {"payload": {"version": "9.0.0"}},
    {"payload": {"blender": "4.3.2"}}, {"payload": {"interactive_gui": True}},
    {"payload": {"interactive_gui": 0}},
    {"returncode": 7}, {"timeout": True},
])
def test_fail_closed_and_retain_failure_evidence(harness, fault):
    h = harness
    h.behavior.update(fault)
    result = host.qualify(**h.args)
    assert not result["ok"] and len(h.calls) == 1
    assert result["error"] and not result["modes"][0]["ok"]
    assert (h.args["work_root"] / "logs/install.log").is_file()
    assert (h.args["work_root"] / "summary.json").is_file()
    if fault.get("returncode"):
        assert result["modes"][0]["returncode"] == 7  # Even after a success marker.
    if fault.get("timeout"):
        assert result["modes"][0]["timed_out"] is True


def test_existing_root_refused_without_touching_contents(harness):
    root = harness.args["work_root"]
    root.mkdir()
    witness = root / "keep"
    witness.write_text("untouched")
    with pytest.raises(FileExistsError):
        host.qualify(**harness.args)
    assert witness.read_text() == "untouched" and not harness.calls


def test_windows_branch_omits_posix_umask(harness, monkeypatch):
    monkeypatch.setattr(host, "os", SimpleNamespace(name="nt", environ=os.environ))
    assert host.qualify(**harness.args)["ok"]
    assert all("umask" not in options for _, options in harness.calls)


@pytest.mark.parametrize("timeout", [True, 0, -1, float("inf"), float("nan"), 86401])
def test_invalid_host_timeout_rejected_before_work_root(harness, timeout):
    with pytest.raises(ValueError, match="timeout"):
        host.qualify(**harness.args, timeout=timeout)
    assert not harness.args["work_root"].exists() and not harness.calls


def test_receipt_marker_disagreement_rejected(harness):
    harness.behavior["receipt_text"] = json.dumps({"ok": True, "mode": "other"})
    result = host.qualify(**harness.args)
    assert not result["ok"] and "disagree" in result["error"]


def test_archive_mutation_after_all_modes_prevents_success(harness, monkeypatch):
    run = host.subprocess.run

    def changed(*args, **kwargs):
        result = run(*args, **kwargs)
        if kwargs["env"]["MCAD_VERIFY_MODE"] == "read":
            harness.args["archive"].write_bytes(b"changed candidate")
        return result

    monkeypatch.setattr(host.subprocess, "run", changed)
    result = host.qualify(**harness.args)
    assert len(harness.calls) == 3 and not result["ok"]
    assert "changed during" in result["error"]


@pytest.mark.parametrize("target", ["script", "fixture"])
def test_test_definition_mutation_prevents_success(harness, monkeypatch, target):
    run = host.subprocess.run

    def changed(*args, **kwargs):
        result = run(*args, **kwargs)
        if kwargs["env"]["MCAD_VERIFY_MODE"] == "read":
            path = harness.args["script"] if target == "script" else harness.args["script"].parent / "fixtures/standalone_constrained_plate.mcad.json"
            path.write_bytes(b"changed test definition")
        return result

    monkeypatch.setattr(host.subprocess, "run", changed)
    result = host.qualify(**harness.args)
    assert not result["ok"] and "script or fixture changed" in result["error"]


@pytest.mark.parametrize("version", ["1.30.0-rc1", "1.30.0+build", "01.30.0", "1.030.0", "1.30.00", "v1.30.0", "1.30", "1.30.0.1", "1.30.0\n"])
def test_version_matches_builder_plain_release_contract(harness, version):
    harness.args["version"] = version
    with pytest.raises(ValueError, match="three-component release version"):
        host.qualify(**harness.args)
    assert not harness.args["work_root"].exists() and not harness.calls
