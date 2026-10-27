"""CLI child-source and decoding controls using inert, generated Python only."""

import json

import pytest
import test_cli as cli_tests
from process_source_binding import SourceBindingError, require_source_binding


def _source_tree(tmp_path, name, body):
    root = tmp_path / name
    package = root / "src/mechanical_cad"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    (package / "cli.py").write_text(body, encoding="utf-8")
    return root


def _cli_body(output=b"intended pi\xc3\xa8ce\r\n", *, tamper_origin=False):
    return (
        "import sys\n"
        "def main():\n"
        "    import mechanical_cad\n"
        + ("    mechanical_cad.__spec__.origin = 'foreign/package.py'\n" if tamper_origin else "")
        + f"    sys.stdout.buffer.write({output!r})\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


@pytest.mark.parametrize("console_entry", [False, True])
def test_cli_process_binds_current_tree_over_ambient_older_source(
    tmp_path, monkeypatch, console_entry
):
    root = _source_tree(tmp_path, "current", _cli_body())
    older = _source_tree(tmp_path, "older", "raise AssertionError('ambient old CLI ran')\n")
    monkeypatch.setattr(cli_tests, "ROOT", root)
    clean = cli_tests._cli_process([], console_entry=console_entry)
    assert clean.returncode == 0 and clean.stdout == "intended pi\u00e8ce\n"
    assert clean.stderr == ""

    original = cli_tests.source_bound_script

    def with_ambient(*args, **kwargs):
        return f"import sys\nsys.path.insert(0, {str(older / 'src')!r})\n" + original(
            *args, **kwargs
        )

    monkeypatch.setattr(cli_tests, "source_bound_script", with_ambient)
    selected = cli_tests._cli_process([], console_entry=console_entry)
    assert selected.returncode == 0 and selected.stdout == clean.stdout
    assert selected.stderr == ""


@pytest.mark.parametrize("console_entry", [False, True])
@pytest.mark.parametrize("fault", ["preloaded", "origin", "hash"])
def test_cli_process_rejects_bad_source_before_decoding(
    tmp_path, monkeypatch, console_entry, fault
):
    root = _source_tree(tmp_path, "current", _cli_body())
    monkeypatch.setattr(cli_tests, "ROOT", root)
    clean = cli_tests._cli_process([], console_entry=console_entry)
    assert clean.returncode == 0 and clean.stdout == "intended pi\u00e8ce\n"
    assert clean.stderr == ""
    package = root / "src/mechanical_cad"
    original = cli_tests.source_bound_script
    if fault == "origin":
        # Invalid output would raise UnicodeDecodeError if decoded before proof.
        (package / "cli.py").write_text(_cli_body(b"\xff", tamper_origin=True), encoding="utf-8")
        expected = "module origin mismatch"
    else:
        older = _source_tree(tmp_path, "older", _cli_body())

        def bad_binding(*args, **kwargs):
            script = original(*args, **kwargs)
            if fault == "hash":
                # Capture intended hashes first, then change only fixture bytes.
                (package / "cli.py").write_bytes(b"raise AssertionError('changed source ran')\n")
                return script
            return (
                f"import sys\nsys.path.insert(0, {str(older / 'src')!r})\n"
                "import mechanical_cad\n" + script
            )

        monkeypatch.setattr(cli_tests, "source_bound_script", bad_binding)
        expected = "source bytes mismatch" if fault == "hash" else "preloaded project module"
    with pytest.raises(SourceBindingError, match=expected) as error:
        cli_tests._cli_process([], console_entry=console_entry)
    assert error.value.process.returncode != 0
    assert error.value.process.stdout == (b"\xff" if fault == "origin" else b"")
    assert json.loads(error.value.report_path.read_bytes())["status"] == "failed"


def test_cli_text_uses_utf8_instead_of_locale_and_preserves_text_newlines():
    raw = b"pi\xc3\xa8ce \xce\xbb \xe4\xb8\xad\r\nsecond\rline\n"
    expected = "pi\u00e8ce \u03bb \u4e2d\nsecond\nline\n"
    assert cli_tests._cli_text(raw) == expected
    assert raw.decode("cp1252") != expected
    assert raw.endswith(b"\r\nsecond\rline\n")


@pytest.mark.parametrize("console_entry", [False, True])
def test_cli_process_strictly_rejects_invalid_utf8_after_source_proof(
    tmp_path, monkeypatch, console_entry
):
    root = _source_tree(tmp_path, "current", _cli_body())
    monkeypatch.setattr(cli_tests, "ROOT", root)
    clean = cli_tests._cli_process([], console_entry=console_entry)
    assert clean.returncode == 0 and clean.stdout == "intended pi\u00e8ce\n"
    (root / "src/mechanical_cad/cli.py").write_text(_cli_body(b"\xff"), encoding="utf-8")
    proofs = []

    def observed_proof(process, path):
        report = require_source_binding(process, path)
        proofs.append(report)
        return report

    monkeypatch.setattr(cli_tests, "require_source_binding", observed_proof)
    with pytest.raises(UnicodeDecodeError):
        cli_tests._cli_process([], console_entry=console_entry)
    assert len(proofs) == 1 and proofs[0]["status"] == "verified"
