"""Linux venv invocation, immutable launch capture, and runtime currency seam."""

import importlib
import os
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

LINUX = pytest.mark.skipif(
    sys.platform != "linux", reason="qualified Linux external/venv backend identity"
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_backend_selection_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
selection = importlib.import_module(PACKAGE + ".backend_selection")


def capture(**kwargs):
    values = {
        "project_root": str(ROOT),
        "python_executable": sys.executable,
        "generation": 0,
        "lifetime_id": "live",
        "environment": {},
    }
    values.update(kwargs)
    return selection.BackendSelection.capture(**values)


@LINUX
def test_captured_environment_is_detached_nonlogging_and_matches_launch_policy():
    environment = {"SECRET_TEST_VALUE": "do-not-show-this", "PYTHONHOME": "/wrong", "PATH": "/bin"}
    value = capture(environment=environment)
    environment["PATH"] = "/changed"
    launch = value.launch_environment()
    assert "PYTHONHOME" not in launch
    assert launch["PYTHONPATH"] == str(ROOT / "src")
    assert launch["PYTHONNOUSERSITE"] == "1"
    assert launch["PYTHONIOENCODING"] == "utf-8"
    assert launch["PATH"] == "/bin"
    launch["PATH"] = "/other"
    assert value.launch_environment()["PATH"] == "/bin"
    assert "do-not-show-this" not in repr(value)
    assert "SECRET_TEST_VALUE" not in repr(value)
    with pytest.raises((AttributeError, TypeError)):
        value.timeout = 2


@LINUX
def test_defaults_captured_once_and_explicit_values_override_environment(monkeypatch):
    defaults = {"MCAD_ROOT": str(ROOT), "MCAD_PYTHON": sys.executable}
    value = capture(project_root="", python_executable="", environment=defaults)
    assert value.project_root == str(ROOT)
    defaults["MCAD_ROOT"] = "/changed"
    monkeypatch.setenv("MCAD_PYTHON", "/wrong")
    assert value.python_executable == os.path.abspath(sys.executable)
    explicit = capture(environment={"MCAD_ROOT": "/bad", "MCAD_PYTHON": "/bad"})
    assert explicit.project_root == str(ROOT)


@LINUX
def test_symlink_venv_invocation_is_not_collapsed_to_shared_base(tmp_path):
    a, b = tmp_path / "venv a \u00e9", tmp_path / "venv b"
    a.mkdir()
    b.mkdir()
    (a / "python").symlink_to(sys.executable)
    (b / "python").symlink_to(sys.executable)
    first = capture(python_executable=str(a / "python"))
    second = capture(python_executable=str(b / "python"))
    assert first.python_executable_target == second.python_executable_target
    assert first.python_executable == str(a / "python")
    assert first.python_executable != second.python_executable
    with pytest.raises(selection.SelectionError):
        first.assert_current(second)
    lexical = capture(python_executable=str(a / ".." / a.name / "python"))
    assert lexical == first


@LINUX
def test_root_symlink_resolves_and_linux_case_is_not_folded(tmp_path):
    link = tmp_path / "project link"
    link.symlink_to(ROOT, target_is_directory=True)
    assert capture(project_root=str(link)).project_root == str(ROOT)
    assert selection.lexical_path("/tmp/Python") != selection.lexical_path("/tmp/python")


@LINUX
@pytest.mark.parametrize(
    "changes",
    [
        {"generation": 1},
        {"lifetime_id": "new lifetime"},
        {"timeout": 25},
        {"environment": {"MCAD_ROOT": "/different observed default"}},
    ],
)
def test_current_selection_checks_generation_epoch_timeout_and_effective_environment(changes):
    first = capture()
    first.assert_current(capture())
    with pytest.raises(selection.SelectionError):
        first.assert_current(capture(**changes))
    with pytest.raises(selection.SelectionError):
        first.assert_current(replace(first, generation=2))  # A -> B -> A still differs.


@LINUX
@pytest.mark.parametrize("timeout,expected", [(-1, 1), (0, 1), (30, 30), (500, 300)])
def test_timeout_clamps_once(timeout, expected):
    assert capture(timeout=timeout).timeout == expected


@LINUX
@pytest.mark.parametrize(
    "changes",
    [
        {"generation": True},
        {"generation": -1},
        {"lifetime_id": ""},
        {"timeout": True},
        {"timeout": float("nan")},
        {"timeout": float("inf")},
        {"environment": {"BAD=KEY": "value"}},
        {"environment": {"KEY": "nul\0value"}},
        {"python_executable": "/missing/python"},
        {"project_root": "/missing/root"},
    ],
)
def test_invalid_capture_is_before_launch_failure(changes):
    with pytest.raises(selection.SelectionError):
        capture(**changes)


@LINUX
def test_nonexecutable_file_rejected_on_linux(tmp_path):
    executable = tmp_path / "python"
    executable.write_text("not executable")
    with pytest.raises(selection.SelectionError):
        capture(python_executable=str(executable))


@LINUX
def test_tilde_defaults_use_supplied_environment_without_rereading_live_home(tmp_path, monkeypatch):
    home = tmp_path / "captured home"
    home.mkdir()
    (home / "project").symlink_to(ROOT, target_is_directory=True)
    (home / "python").symlink_to(sys.executable)
    monkeypatch.setenv("HOME", "/wrong-live-home")
    selected = capture(
        project_root="~/project", python_executable="~/python", environment={"HOME": str(home)}
    )
    assert selected.project_root == str(ROOT)
    assert selected.python_executable == str(home / "python")


@pytest.mark.parametrize(
    "platform,expected", [(None, 60.0), ("linux-x64", 60.0), ("windows-x64", 240.0)]
)
def test_platform_defaults_are_portable_data(platform, expected):
    assert selection.default_timeout_seconds(bundled_platform=platform) == expected


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows manual-backend admission guard")
def test_native_windows_external_backend_is_rejected_before_configuration_or_path_io(monkeypatch):
    class UnreadableEnvironment:
        def keys(self):
            pytest.fail("unqualified manual backend read its environment")

    monkeypatch.setattr(selection, "Path", lambda *a: pytest.fail("unqualified path lookup"))
    with pytest.raises(selection.SelectionError, match="Linux only"):
        capture(environment=UnreadableEnvironment())
