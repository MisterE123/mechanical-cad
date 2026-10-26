"""Actual sidecar reports agree with the Blender-only protocol validator."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("slvs")
pytest.importorskip("OCP")
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "mcad_live_bridge", ROOT / "blender_addon/mechanical_cad_blender/bridge.py"
)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


@pytest.mark.parametrize(
    "variant", ["canonical", "omitted_null_defaults", "redundant", "conflicting", "bad_expression"]
)
def test_real_sidecar_sketch_diagnostics_cross_strict_display_boundary(variant):
    source = json.loads((ROOT / "examples/constrained_plate.mcad.json").read_text())
    constraints = source["features"][0]["sketch"]["constraints"]
    if variant == "omitted_null_defaults":
        for item in constraints:
            for key in ("value", "target"):
                if item.get(key) is None:
                    item.pop(key, None)
    elif variant == "redundant":
        constraints.append(
            {**next(c for c in constraints if c["id"] == "axis0"), "id": "duplicate"}
        )
    elif variant == "conflicting":
        constraints.append(
            {"id": "conflict", "kind": "distance", "refs": ["p0", "p1"], "value": 41}
        )
    elif variant == "bad_expression":
        source["parameters"]["width"] = "unknown_parameter"
    before = json.dumps(source)
    if variant == "bad_expression":
        with pytest.raises(bridge.BridgeError, match="unknown_parameter"):
            bridge.replay(source, project_root=str(ROOT), python_executable=sys.executable)
    else:
        result = bridge.replay(source, project_root=str(ROOT), python_executable=sys.executable)
        report = result["features"][0]["sketch"]
        if variant == "conflicting":
            assert result["status"] == "failed"
            assert report["failed_constraints"] and report["remaining_dof"] is None
            assert result["features"][-1]["status"] == "blocked"
        else:
            assert result["status"] == "ok" and report["remaining_dof"] == 0
            assert report["status"] == ("redundant_okay" if variant == "redundant" else "okay")
    assert json.dumps(source) == before
