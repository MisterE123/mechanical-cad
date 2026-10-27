import io
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from process_source_binding import require_source_binding, source_bound_script

from mechanical_cad.cli import main
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import save_document

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "drilled_plate.mcad.json"
pytestmark = pytest.mark.kernel


def test_validate_cli(capsys):
    assert main(["validate", str(EXAMPLE)]) == 0
    assert "Valid schema and DAG" in capsys.readouterr().out


def test_replay_cli_output_is_reviewable_json(tmp_path):
    output = tmp_path / "replay.json"
    assert main(["replay", str(EXAMPLE), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["status"] == "ok"


@pytest.mark.parametrize(("command", "suffix"), [("export-step", "step"), ("export-stl", "stl")])
def test_geometry_exports_produce_real_files(command, suffix, tmp_path):
    output = tmp_path / f"plate.{suffix}"
    assert main([command, str(EXAMPLE), str(output)]) == 0
    assert output.stat().st_size > 1000


def test_geometry_check_cli_is_machine_readable(capsys):
    assert main(["check-geometry", str(EXAMPLE)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert isinstance(result, dict)


def test_failed_model_cannot_export(plate, tmp_path, capsys):
    invalid = tmp_path / "invalid.mcad.json"
    output = tmp_path / "invalid.step"
    save_document(plate.with_parameter("width", -1), invalid)
    assert main(["export-step", str(invalid), str(output)]) == 1
    assert not output.exists()
    assert "regeneration_failed" in capsys.readouterr().err


def test_cli_parameter_edit_does_not_modify_original(tmp_path):
    original = EXAMPLE.read_text()
    output = tmp_path / "edited.mcad.json"
    assert main(["set-parameter", str(EXAMPLE), "width", "20 * 3", str(output)]) == 0
    assert json.loads(output.read_text())["parameters"]["width"] == "20 * 3"
    assert EXAMPLE.read_text() == original


@pytest.mark.parametrize("command,suffix", [("export-step", ".step"), ("export-stl", ".stl")])
def test_cli_partial_writer_failure_preserves_previous_export(
    plate, tmp_path, monkeypatch, capsys, command, suffix
):
    document = tmp_path / "source.mcad.json"
    destination = tmp_path / ("previous" + suffix)
    save_document(plate, document)
    destination.write_bytes(b"previous valid export")

    def fail(self, shape, path, **kwargs):
        assert path != destination and path.parent == destination.parent
        path.write_bytes(b"partial new bytes")
        raise OSError("simulated disk failure")

    monkeypatch.setattr(OCPKernel, command.replace("-", "_"), fail)
    assert main([command, str(document), str(destination)]) == 1
    assert "io_error: simulated disk failure" in capsys.readouterr().err
    assert destination.read_bytes() == b"previous valid export"
    assert set(tmp_path.iterdir()) == {document, destination}


def test_cli_current_document_edit_controls_exported_geometry(plate, tmp_path):
    document = tmp_path / "changed.mcad.json"
    destination = tmp_path / "changed.step"
    save_document(plate.with_parameter("width", 60), document)
    assert main(["export-step", str(document), str(destination)]) == 0
    kernel = OCPKernel()
    assert kernel.inspect(kernel.import_step(destination))["volume"] == pytest.approx(
        (60 * 30 - math.pi * 4**2) * 10, rel=1e-12
    )


def _cli_process(arguments, *, console_entry=False):
    entry = (
        "import sys\nsys.argv[0] = '-c'\n"
        "from mechanical_cad.cli import main; raise SystemExit(main())\n"
        if console_entry
        else "import runpy\nrunpy.run_module('mechanical_cad.cli', run_name='__main__', alter_sys=True)\n"
    )
    proof = Path(tempfile.mkdtemp(prefix="cli-source-")) / "binding.json"
    child = proof.with_name("entry.py")
    child.write_bytes(source_bound_script(ROOT, entry, proof, historical_pins={}).encode("utf-8"))
    process = subprocess.run(
        [sys.executable, "-B", str(child), *arguments],
        capture_output=True,
        timeout=60,
        cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
    )
    # Reject wrong-source output before decoding or treating it as CLI evidence.
    require_source_binding(process, proof)
    return subprocess.CompletedProcess(
        process.args,
        process.returncode,
        _cli_text(process.stdout),
        _cli_text(process.stderr),
    )


def _cli_text(raw):
    # Match text=True's existing universal-newline semantics with the CLI's
    # explicit UTF-8 encoding, independent of the parent's Windows locale.
    return io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8", errors="strict").read()


@pytest.mark.parametrize("console_entry", [False, True])
@pytest.mark.parametrize("command,suffix", [("export-step", ".step"), ("export-stl", ".stl")])
def test_cli_export_process_stdout_contains_only_confirmation(
    tmp_path, command, suffix, console_entry
):
    destination = tmp_path / ("pièce selected" + suffix)
    process = _cli_process([command, str(EXAMPLE), str(destination)], console_entry=console_entry)
    assert process.returncode == 0, process.stderr
    assert process.stdout == f"Exported {destination}\n"
    assert destination.stat().st_size > 1000
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("console_entry", [False, True])
def test_cli_check_process_stdout_is_single_json(console_entry):
    process = _cli_process(["check-geometry", str(EXAMPLE)], console_entry=console_entry)
    assert process.returncode == 0, process.stderr
    checks = json.loads(process.stdout)
    assert checks["brep"]["volume"] == pytest.approx((40 * 30 - math.pi * 4**2) * 10)
    assert checks["mesh"]["watertight"] is True


def test_cli_help_still_uses_stdout():
    process = _cli_process(["--help"])
    assert process.returncode == 0
    assert "check-geometry" in process.stdout and "export-step" in process.stdout
    assert process.stderr == ""


def test_cli_failed_draft_process_preserves_destination(plate, tmp_path):
    document = tmp_path / "invalid.mcad.json"
    destination = tmp_path / "previous.step"
    save_document(plate.with_parameter("width", -1), document)
    destination.write_bytes(b"previous")
    process = _cli_process(["export-step", str(document), str(destination)])
    assert process.returncode == 1
    assert process.stdout == ""
    assert "regeneration_failed" in process.stderr
    assert destination.read_bytes() == b"previous"
    assert set(tmp_path.iterdir()) == {document, destination}
