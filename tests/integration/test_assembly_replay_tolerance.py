"""Stored B-rep tolerance admission is distinct from requested check precision."""

from dataclasses import replace
from pathlib import Path

import pytest
from OCP.BRep import BRep_Builder
from OCP.TopAbs import TopAbs_VERTEX
from OCP.TopoDS import TopoDS

from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.assembly_requirements import NumericalPolicy, VerificationPreset
from mechanical_cad.assembly_service import run_assembly_action
from mechanical_cad.kernel_ocp import OCPKernel, _subshapes

pytestmark = pytest.mark.kernel
ROOT = Path(__file__).resolve().parents[2]


class StoredToleranceKernel(OCPKernel):
    """Real valid solids with known native tolerance, not a synthetic success report."""

    def manufacturing_check(self, shape, linear_deflection=0.1):
        builder = BRep_Builder()
        for vertex in _subshapes(shape, TopAbs_VERTEX):
            builder.UpdateVertex(TopoDS.Vertex(vertex), 5.000001e-6)
        return super().manufacturing_check(shape, linear_deflection)


def test_explicit_replay_admission_does_not_widen_verification():
    legacy = AssemblyDocument.from_json(
        (ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()
    )
    loose_check = VerificationPreset(
        "loose", "Explicit coarse check", (), NumericalPolicy(1e-5), kind="interference_only"
    )
    legacy = replace(
        legacy, verification_presets=(loose_check,), active_verification_preset="loose"
    )
    blocked = run_assembly_action(legacy, kernel=StoredToleranceKernel())
    assert not blocked["ok"]
    assert blocked["report"]["effective_policy"]["linear_tolerance_mm"] == 1e-6
    assert any(
        "Stored B-rep tolerance" in d["message"]
        for d in blocked["report"]["poses"][0]["diagnostics"]
    )
    explicit = replace(legacy, replay_tolerance_mm=1e-5)
    accepted = run_assembly_action(explicit, kernel=StoredToleranceKernel())
    assert accepted["ok"] and not accepted["report"]["passed"]
    assert accepted["report"]["effective_policy"]["linear_tolerance_mm"] == 1e-5
    assert all(p["geometry_check"]["brep"]["valid"] for p in accepted["result"]["parts"])
    # A stricter explicit request still refuses the very same valid geometry.
    strict = run_assembly_action(
        explicit, policy={"linear_tolerance_mm": 1e-6}, kernel=StoredToleranceKernel()
    )
    assert not strict["ok"] and not strict["report"]["passed"]
    # Removing selected check intent restores default measurement precision, not replay policy.
    check = run_assembly_action(
        replace(explicit, active_verification_preset=None),
        "assembly_check",
        kernel=StoredToleranceKernel(),
    )
    assert not check["ok"] and not check["report"]["passed"]
    assert check["report"]["effective_policy"]["linear_tolerance_mm"] == 1e-6
    assert explicit.source_hashes == legacy.source_hashes
    assert accepted["request_fingerprint"] != blocked["request_fingerprint"]
