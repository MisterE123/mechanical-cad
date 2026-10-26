"""Persisted verification intent survives process replay and invalidates evidence."""

from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.assembly_requirements import (
    ClearanceRequirement,
    NumericalPolicy,
    VerificationPreset,
)
from mechanical_cad.assembly_service import run_assembly_action
from mechanical_cad.sidecar import process_request

pytestmark = pytest.mark.kernel
ROOT = Path(__file__).resolve().parents[2]


def candidate(*, minimum=5, active=None):
    model = AssemblyDocument.from_json(
        (ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()
    )
    fit = VerificationPreset(
        "running_fit",
        "Block running clearance",
        (ClearanceRequirement("gap", "Root-to-moving gap", ("root", "a"), minimum),),
        NumericalPolicy(1e-6, 1e-9, 0.2),
    )
    interference = VerificationPreset("overlap", "Interference only", (), kind="interference_only")
    return replace(
        model, verification_presets=(fit, interference), active_verification_preset=active
    )


def check(model, **kwargs):
    return run_assembly_action(
        model, "assembly_check", coordinates={"slide_a": 20, "slide_b": 100}, **kwargs
    )


def test_no_selection_produces_measurements_without_inventing_a_pass_policy():
    result = check(candidate())
    assert result["ok"] and result["report"]["complete"]
    assert result["report"]["verification_basis"] == {
        "kind": "unconfigured",
        "preset_id": None,
        "preset": None,
        "configured": False,
    }
    assert not result["report"]["passed"]
    assert all(not row["passed"] for row in result["report"]["poses"])
    assert result["report"]["poses"][0]["pairs"]
    assert all(
        p["clearance_verdict"] == "measurement_only" for p in result["report"]["poses"][0]["pairs"]
    )


def test_selected_saved_requirement_is_distinct_from_numerical_resolution():
    model = candidate(minimum=11, active="running_fit")
    saved = AssemblyDocument.from_json(model.to_json())
    result = check(saved)
    report = result["report"]
    assert result["ok"] and report["known_clearance_violation"] and not report["passed"]
    assert report["verification_basis"]["preset"] == model.verification_presets[0].to_dict()
    assert report["effective_policy"] == model.verification_presets[0].policy.to_dict()
    pair = next(p for p in report["poses"][0]["pairs"] if p["instances"] == ["a", "root"])
    assert pair["minimum_required_mm"] == 11
    assert pair["minimum_distance_mm"] == pytest.approx(10)
    assert report["effective_policy"]["linear_tolerance_mm"] == 1e-6


def test_explicit_saved_preset_selection_and_interference_only_are_visible():
    model = candidate(minimum=11, active="running_fit")
    result = check(model, preset_id="overlap")
    assert result["report"]["passed"]
    assert result["report"]["verification_basis"]["kind"] == "interference_only"
    assert result["report"]["verification_basis"]["preset_id"] == "overlap"
    assert all(p["minimum_required_mm"] == 0 for p in result["report"]["poses"][0]["pairs"])


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"preset_id": ""}, "invalid_preset"),
        ({"preset_id": False}, "invalid_preset"),
        ({"preset_id": "missing"}, "missing_preset"),
        ({"requirements": []}, "conflicting_policy"),
        ({"policy": {}}, "conflicting_policy"),
    ],
)
def test_invalid_selection_and_hidden_overrides_are_blocked_before_native_work(kwargs, code):
    result = check(candidate(active="running_fit"), kernel=object(), **kwargs)
    assert not result["ok"] and result["error"]["code"] == code
    assert not result["result"]["source_replays"]
    assert result["request_fingerprint"] and result["report_fingerprint"]


def test_requirement_edit_invalidates_report_without_changing_geometry_or_placement():
    old, new = (
        candidate(minimum=5, active="running_fit"),
        candidate(minimum=11, active="running_fit"),
    )
    before, after = check(old), check(new)
    assert before["report"]["passed"] and not after["report"]["passed"]
    assert old.source_hashes == new.source_hashes
    assert before["result"]["parts"] == after["result"]["parts"]
    assert before["report"]["base_pose"]["transforms"] == after["report"]["base_pose"]["transforms"]
    for key in ("request_fingerprint", "report_fingerprint"):
        assert before[key] != after[key]
    assert old.verification_presets[0].id == new.verification_presets[0].id
    assert (
        old.verification_presets[0].requirements[0].id
        == new.verification_presets[0].requirements[0].id
    )


def test_protocol_binds_explicit_selection_to_saved_named_policy():
    model = candidate(minimum=11)
    request = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "assembly": model.to_dict(),
        "action": "assembly_check",
        "preset_id": "running_fit",
        "coordinates": {"slide_a": 20, "slide_b": 100},
    }
    result = process_request(request)
    assert result["ok"] and not result["report"]["passed"]
    assert result["request"]["preset_id"] == "running_fit"
    assert (
        result["report"]["verification_basis"]["preset"] == model.verification_presets[0].to_dict()
    )
    assert result["result"]["canonical_assembly"] == model.to_dict()


def test_replay_keeps_saved_intent_but_never_claims_to_have_checked_it():
    model = candidate(active="running_fit")
    result = run_assembly_action(model)
    assert result["ok"] and result["report"]["status"] == "replayed"
    assert result["report"]["verification_basis"]["kind"] == "not_requested"
    assert not result["report"]["passed"]
    rejected = run_assembly_action(model, preset_id="running_fit", kernel=object())
    assert not rejected["ok"] and rejected["error"]["code"] == "invalid_request"
