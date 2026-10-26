"""The real Check invoke path starts async without a redundant confirmation."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "blender_addon/mechanical_cad_blender/assembly_verification_ui.py"
)


def invoke_method(*, busy=False):
    tree = ast.parse(SOURCE.read_text())
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MCAD_OT_assembly_check"
    )
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "invoke")
    namespace = {
        "execution_lease": SimpleNamespace(is_busy=lambda: busy, BUSY_MESSAGE="Busy"),
        "bridge": SimpleNamespace(BridgeError=RuntimeError),
        "reject": Mock(return_value={"CANCELLED"}),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


def test_check_click_captures_then_executes_asynchronously_without_dialog():
    ns = invoke_method()
    operator = SimpleNamespace(capture_dialog=Mock(), _asynchronous=False)

    def execute(context):
        assert operator._asynchronous is True
        operator.capture_dialog.assert_called_once_with(context)
        return {"RUNNING_MODAL"}

    operator.execute = execute
    assert ns["invoke"](operator, object(), None) == {"RUNNING_MODAL"}
    ns["reject"].assert_not_called()


def test_repeated_check_does_not_admit_new_interaction_or_execute():
    ns = invoke_method(busy=True)
    operator = SimpleNamespace(capture_dialog=Mock(), execute=Mock())
    assert ns["invoke"](operator, object(), None) == {"CANCELLED"}
    operator.capture_dialog.assert_not_called()
    operator.execute.assert_not_called()


@pytest.mark.parametrize("failure", ["capture", "execute"])
def test_check_start_failure_is_reported_not_retried(failure):
    ns = invoke_method()
    operator = SimpleNamespace(capture_dialog=Mock(), execute=Mock())
    target = operator.capture_dialog if failure == "capture" else operator.execute
    target.side_effect = RuntimeError("unavailable")
    assert ns["invoke"](operator, object(), None) == {"CANCELLED"}
    target.assert_called_once()
    ns["reject"].assert_called_once()
