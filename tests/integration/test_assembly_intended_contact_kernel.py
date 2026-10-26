"""Bounded real OCCT seated-box policy/export regression, not physical-fit proof."""

import copy
import json
from pathlib import Path

import pytest
from test_assembly_step_kernel import _read_assembly

from mechanical_cad.assembly_protocol import process_assembly_request
from mechanical_cad.assembly_requirements import NumericalPolicy


@pytest.mark.kernel
def test_seated_contact_opt_in_exports_without_changing_measurements(tmp_path):
    root = Path(__file__).resolve().parents[2]
    raw = json.loads((root / "examples/reused_blocks.mcad-assembly.json").read_text())
    raw["joints"][0]["coordinate"] = 10.0
    raw["verification_presets"] = [
        {
            "id": "seat",
            "name": "Intended block seat",
            "kind": "clearance",
            "policy": NumericalPolicy().to_dict(),
            "requirements": [
                {
                    "id": "seat_pair",
                    "name": "Root and first block seat",
                    "instances": ["a", "root"],
                    "minimum_mm": 0,
                }
            ],
        }
    ]
    raw["active_verification_preset"] = "seat"
    path = tmp_path / "seated.step"
    request = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "action": "assembly_export_step",
        "result_version": 3,
        "assembly": raw,
        "path": str(path),
    }
    strict = process_assembly_request(copy.deepcopy(request))
    assert strict["ok"] is False and not path.exists()
    assert strict["result"]["report"]["complete"] is True
    assert strict["result"]["report"]["passed"] is False
    assert "policy_accepted" not in strict["result"]["report"]

    raw["verification_presets"][0]["requirements"][0]["contact_policy"] = "accept_tolerance_band"
    accepted = process_assembly_request(copy.deepcopy(request))
    assert accepted["ok"] is True, accepted
    report = accepted["result"]["report"]
    assert report["policy_accepted"] is True and report["passed"] is False
    assert report["status"] == "checked_with_threshold_contacts"
    assert report["complete"] is True and report["has_threshold_contacts"] is True
    pair = next(p for p in report["poses"][0]["pairs"] if p["instances"] == ["a", "root"])
    assert pair["common_volume_mm3"] == 0 and pair["minimum_distance_mm"] == 0
    assert pair["clearance_verdict"] == "at_threshold" and pair["relation"] == "contact_or_near"
    assert report["poses"][0]["pairs"] == strict["result"]["report"]["poses"][0]["pairs"]
    assert report["manufacturing_or_load_certification"] is False
    _, _, occurrences = _read_assembly(path)
    assert set(occurrences) == {"a", "b", "root"}

    before = path.read_bytes()
    raw["joints"][0]["coordinate"] = 9.99
    interference = process_assembly_request(copy.deepcopy(request))
    assert interference["ok"] is False
    assert interference["result"]["report"]["known_interference"] is True
    assert interference["result"]["report"]["policy_accepted"] is False
    assert path.read_bytes() == before
