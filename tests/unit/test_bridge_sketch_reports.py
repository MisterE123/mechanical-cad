"""Never present malformed native sketch diagnostics as current Blender truth."""

import copy
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "mcad_sketch_bridge", ROOT / "blender_addon/mechanical_cad_blender/bridge.py"
)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


def payload():
    sketch = {
        "schema_version": 1,
        "id": "geometry",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [{"id": "a", "u": 0, "v": 0}, {"id": "b", "u": 40, "v": 0}],
        "lines": [{"id": "line", "start": "a", "end": "b"}],
        "constraints": [{"id": "width", "kind": "distance", "refs": ["a", "b"], "value": "width"}],
    }
    document = {
        "id": "doc",
        "features": [{"id": "sketch", "kind": "sketch_constrained", "sketch": sketch}],
    }
    solved = copy.deepcopy(sketch)
    solved["constraints"][0]["value"] = 40.0
    solved["constraints"][0]["target"] = None
    report = {
        "solver": "libslvs",
        "solver_version": "3.2",
        "status": "okay",
        "remaining_dof": 3,
        "max_residual_mm": 0.0,
        "failed_constraints": [],
        "redundant_constraints": [],
        "solved": solved,
        "dimensions": {"width": 40.0},
    }
    response = {
        "protocol_version": 1,
        "ok": True,
        "error": None,
        "result": {
            "document_id": "doc",
            "status": "ok",
            "features": [
                {"id": "sketch", "kind": "sketch_constrained", "status": "ok", "sketch": report}
            ],
        },
    }
    return document, response, report


@pytest.fixture
def invoke(monkeypatch, tmp_path):
    (tmp_path / "src/mechanical_cad").mkdir(parents=True)
    executable = tmp_path / "python"
    executable.touch()

    def run(document, response):
        monkeypatch.setattr(
            bridge.subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess([], 0, json.dumps(response), ""),
        )
        return bridge.replay(
            document, project_root=str(tmp_path), python_executable=str(executable)
        )

    return run


def test_current_solver_report_accepts_real_contract_without_core_imports(invoke):
    document, response, _ = payload()
    assert invoke(document, response) == response["result"]


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(solver="invented"),
        lambda r: r.update(solver_version="99"),
        lambda r: r.update(status=[]),
        lambda r: r.update(status="invented"),
        lambda r: r.update(remaining_dof=True),
        lambda r: r.update(remaining_dof=-1),
        lambda r: r.update(remaining_dof=513),
        lambda r: r.update(remaining_dof=None),
        lambda r: r.update(max_residual_mm=None),
        lambda r: r.update(max_residual_mm=True),
        lambda r: r.update(max_residual_mm=1e-6),
        lambda r: r.update(failed_constraints=["missing"]),
        lambda r: r.update(failed_constraints=[{}]),
        lambda r: r.update(failed_constraints=["width", "width"]),
        lambda r: r.update(redundant_constraints=["width"]),
        lambda r: r.update(solved=None),
        lambda r: r.update(dimensions={"width": True}),
        lambda r: r.update(dimensions={"width": -40}),
        lambda r: r.update(dimensions={"missing": 40}),
        lambda r: r["solved"].update(schema_version=True),
        lambda r: r["solved"].update(id="other"),
        lambda r: r["solved"]["plane"].update(origin=[5, 0, 0]),
        lambda r: r["solved"]["points"][0].update(u=10**1000),
        lambda r: r["solved"]["points"][0].update(id="b"),
        lambda r: r["solved"]["lines"][0].update(end="a"),
        lambda r: r["solved"]["constraints"][0].update(value="width"),
        lambda r: r["solved"]["constraints"][0].update(refs=["b", "a"]),
    ],
)
def test_malformed_success_report_fails_closed(invoke, change):
    document, response, report = payload()
    change(report)
    with pytest.raises(bridge.BridgeError, match="Malformed sketch replay report"):
        invoke(document, response)


def test_failed_report_retains_diagnostics_but_no_current_dof_or_solution(invoke):
    document, response, report = payload()
    report.update(
        status="inconsistent",
        remaining_dof=None,
        solved=None,
        max_residual_mm=None,
        failed_constraints=["width"],
    )
    response["ok"] = False
    response["result"]["status"] = "failed"
    response["result"]["features"][0]["status"] = "failed"
    assert invoke(document, response)["features"][0]["sketch"]["failed_constraints"] == ["width"]
    report["remaining_dof"] = 3
    with pytest.raises(bridge.BridgeError, match="failed sketch"):
        invoke(document, response)


def test_failed_expression_or_missing_solver_may_have_no_solve_report(invoke):
    document, response, _ = payload()
    response["result"]["features"][0].update(status="failed", sketch=None)
    response["ok"] = False
    response["result"]["status"] = "failed"
    assert invoke(document, response)["features"][0]["sketch"] is None


def test_successful_sketch_cannot_omit_diagnostics(invoke):
    document, response, _ = payload()
    response["result"]["features"][0].pop("sketch")
    with pytest.raises(bridge.BridgeError, match="missing its solve report"):
        invoke(document, response)
