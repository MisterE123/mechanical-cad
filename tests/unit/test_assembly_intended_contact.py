"""Synthetic evidence tests; tolerance acceptance is not a native fit proof."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_assembly_bridge import Kernel, bridge, seal
from test_assembly_bridge import make as source_make

from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.assembly_policy import intended_contact_acceptance
from mechanical_cad.assembly_requirements import ClearanceRequirement
from mechanical_cad.assembly_service import _run_assembly_action_with_native
from mechanical_cad.errors import CADException

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def make(monkeypatch):
    return source_make.__wrapped__(monkeypatch)


def model(*, pair=("a", "root"), enabled=True):
    raw = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    raw["verification_presets"] = [
        {
            "id": "seat_policy",
            "name": "Intended seat",
            "kind": "clearance",
            "policy": copy.deepcopy(bridge.DEFAULT_POLICY),
            "requirements": [
                {
                    "id": "seat",
                    "name": "Housing cover seat",
                    "instances": list(pair),
                    "minimum_mm": 0,
                    **({"contact_policy": "accept_tolerance_band"} if enabled else {}),
                }
            ],
        }
    ]
    raw["active_verification_preset"] = raw["verification_presets"][0]["id"]
    return raw


class ContactKernel(Kernel):
    def __init__(self, changes=None, contact_indices=(1,)):
        self.index = 0
        self.changes = changes or {}
        self.contact_indices = contact_indices

    def pair_check(self, *args, **kwargs):
        row = super().pair_check(*args, **kwargs)
        if self.index % 3 in self.contact_indices:
            row.update(
                relation="contact_or_near",
                minimum_distance_mm=0.0,
                minimum_required_mm=kwargs["minimum_required_mm"],
                common_volume_mm3=0.0,
                clearance_verdict="at_threshold",
                witness_points_mm=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
                known_clearance_violation=False,
            )
            row.update(self.changes)
        self.index += 1
        return row


def test_roundtrip_opt_in_changes_digest_not_sources_or_legacy_serialization():
    strict = AssemblyDocument.from_dict(model(enabled=False))
    contact = AssemblyDocument.from_dict(model())
    assert strict.content_hash != contact.content_hash
    assert strict.source_hashes == contact.source_hashes
    assert contact == AssemblyDocument.from_json(contact.to_json())
    assert "contact_policy" not in strict.verification_presets[0].requirements[0].to_dict()
    assert (
        replace(contact.verification_presets[0].requirements[0], contact_policy=None).to_dict()
        == strict.verification_presets[0].requirements[0].to_dict()
    )


@pytest.mark.parametrize("value", [None, True, False, "", "allow_overlap", 1, []])
def test_unknown_or_null_persisted_contact_policy_rejected(value):
    raw = model()
    raw["verification_presets"][0]["requirements"][0]["contact_policy"] = value
    with pytest.raises(CADException):
        AssemblyDocument.from_dict(raw)


def test_contact_nonzero_clearance_rejected():
    with pytest.raises(CADException, match="zero minimum"):
        ClearanceRequirement("seat", "Seat", ("a", "root"), 0.1, "accept_tolerance_band")


def test_contact_acceptance_is_separate_from_measured_pass_and_native_export_gate(make):
    request, response = make(raw=model(), kernel=ContactKernel())
    accepted = bridge.validate_response(request, response)
    report = accepted["report"]
    assert report["policy_accepted"] is True and report["complete"] is True
    assert report["passed"] is False and report["has_threshold_contacts"] is True
    assert report["status"] == "checked_with_threshold_contacts"
    assert report["poses"][0]["pairs"][1]["clearance_verdict"] == "at_threshold"
    _, native = _run_assembly_action_with_native(
        AssemblyDocument.from_dict(model()), "assembly_check", kernel=ContactKernel()
    )
    assert native is not None


def test_legacy_contact_remains_blocked_without_new_flag(make):
    request, response = make(raw=model(enabled=False), kernel=ContactKernel())
    assert not bridge.validate_response(request, response)["report"]["passed"]
    assert "policy_accepted" not in response["report"]
    _, native = _run_assembly_action_with_native(
        AssemblyDocument.from_dict(model(enabled=False)), "assembly_check", kernel=ContactKernel()
    )
    assert native is None


@pytest.mark.parametrize(
    "changes",
    [
        {"complete": False, "clearance_verdict": "indeterminate"},
        {
            "common_volume_mm3": 1e-12,
            "complete": False,
            "relation": "indeterminate_small_overlap",
            "clearance_verdict": "indeterminate",
        },
        {
            "common_volume_mm3": 1,
            "known_interference": True,
            "relation": "interference",
            "clearance_verdict": "fail_interference",
        },
        {
            "diagnostics": [{"code": "uncertain", "message": "Synthetic ambiguity"}],
            "complete": False,
            "clearance_verdict": "indeterminate",
        },
    ],
)
def test_incomplete_positive_volume_and_diagnostics_cannot_be_accepted(make, changes):
    request, response = make(raw=model(), kernel=ContactKernel(changes))
    assert response["report"]["policy_accepted"] is False
    assert bridge.validate_response(request, response)["report"]["policy_accepted"] is False
    forged = copy.deepcopy(response)
    forged["report"]["policy_accepted"] = True
    seal(forged)
    with pytest.raises(bridge.bridge.BridgeError, match="policy acceptance"):
        bridge.validate_response(request, forged)


@pytest.mark.parametrize(
    "changes",
    [
        {"common_volume_mm3": 1e-12},
        {"known_interference": True},
        {"minimum_distance_mm": None},
        {"minimum_required_mm": 0.1},
        {"relation": "unknown"},
        {"witness_points_mm": None},
    ],
)
def test_contradictory_complete_evidence_cannot_mint_acceptance(make, changes):
    request, response = make(raw=model(), kernel=ContactKernel(changes))
    assert response["report"]["policy_accepted"] is False
    _, native = _run_assembly_action_with_native(
        AssemblyDocument.from_dict(model()), "assembly_check", kernel=ContactKernel(changes)
    )
    assert native is None
    with pytest.raises(bridge.bridge.BridgeError):
        bridge.validate_response(request, response)


@pytest.mark.parametrize("pair,indices", [(("a", "b"), (1,)), (("a", "root"), (0, 1))])
def test_wrong_pair_or_unrelated_contact_is_not_authorized(make, pair, indices):
    request, response = make(raw=model(pair=pair), kernel=ContactKernel(contact_indices=indices))
    assert bridge.validate_response(request, response)["report"]["policy_accepted"] is False
    response["report"]["policy_accepted"] = True
    seal(response)
    with pytest.raises(bridge.bridge.BridgeError, match="policy acceptance"):
        bridge.validate_response(request, response)


def test_missing_unrelated_pair_cannot_mint_acceptance(make):
    _, response = make(raw=model(), kernel=ContactKernel())
    response["report"]["poses"][0]["pairs"].pop(0)
    assert intended_contact_acceptance(response["report"], ["a", "b", "root"]) is False


def test_forged_opt_in_on_legacy_preset_is_rejected(make):
    request, response = make(raw=model(enabled=False), kernel=ContactKernel())
    response["report"]["policy_accepted"] = True
    seal(response)
    with pytest.raises(bridge.bridge.BridgeError, match="unauthored"):
        bridge.validate_response(request, response)


def test_changed_policy_rejects_old_report_and_changes_all_binding(make):
    request, response = make(raw=model(), kernel=ContactKernel())
    changed, fresh = make(raw=model(enabled=False), kernel=ContactKernel())
    for key in ("request_fingerprint", "report_fingerprint"):
        assert response[key] != fresh[key]
    with pytest.raises(bridge.bridge.BridgeError):
        bridge.validate_response(changed, response)
    request["assembly"]["verification_presets"][0]["policy"]["linear_tolerance_mm"] *= 2
    with pytest.raises(bridge.bridge.BridgeError):
        bridge.validate_response(request, response)


@pytest.mark.parametrize("distance", [0.0, 0.5e-6, 1e-6])
def test_tolerance_band_acceptance_retains_actual_measured_distance(make, distance):
    request, response = make(
        raw=model(),
        kernel=ContactKernel(
            {
                "minimum_distance_mm": distance,
                "witness_points_mm": [[0.0, 0.0, 0.0], [distance, 0.0, 0.0]],
            }
        ),
    )
    accepted = bridge.validate_response(request, response)
    assert accepted["report"]["policy_accepted"] is True
    assert accepted["report"]["poses"][0]["pairs"][1]["minimum_distance_mm"] == distance
    assert accepted["report"]["passed"] is False


def test_all_listed_poses_must_accept_no_continuous_claim(make):
    class SecondPoseIncomplete(ContactKernel):
        def pair_check(self, *args, **kwargs):
            if self.index >= 3:
                self.changes = {"complete": False, "clearance_verdict": "indeterminate"}
            return super().pair_check(*args, **kwargs)

    request, response = make(
        "assembly_sample",
        raw=model(),
        kernel=SecondPoseIncomplete(),
        coordinates={"slide_a": 20, "slide_b": 50},
        samples={"joint_id": "slide_a", "values": [20, 21]},
    )
    accepted = bridge.validate_response(request, response)
    assert accepted["report"]["policy_accepted"] is False
    assert accepted["report"]["continuous_collision_guarantee"] is False
    assert len(accepted["report"]["poses"]) == 2


def test_authoring_contact_only_updates_selected_pair_and_rejects_positive_minimum():
    from test_assembly_edit import edit

    raw = model()
    saved = copy.deepcopy(raw)
    preset = raw["verification_presets"][0]
    candidate = edit.edit_verification_preset(
        raw,
        preset_id=preset["id"],
        name=preset["name"],
        kind="clearance",
        policy=preset["policy"],
        pair=["a", "b"],
        minimum_mm=0,
        contact_policy="accept_tolerance_band",
    )
    assert raw == saved
    assert candidate["verification_presets"][0]["requirements"][0] == preset["requirements"][0]
    assert len(AssemblyDocument.from_dict(candidate).verification_presets[0].requirements) == 2
    with pytest.raises(edit.BridgeError, match="zero minimum"):
        edit.edit_verification_preset(
            raw,
            name="Bad",
            kind="clearance",
            policy=preset["policy"],
            pair=["a", "b"],
            minimum_mm=1,
            contact_policy="accept_tolerance_band",
        )


@pytest.mark.parametrize("version", [2, 3])
def test_export_receipt_revalidates_intent_and_preserves_failed_destination(
    monkeypatch, tmp_path, version
):
    from test_assembly_bridge_v2 import Kernel as LegacyKernel
    from test_assembly_bridge_v2 import make as legacy_source
    from test_assembly_bridge_v3 import Kernel as MixedKernel
    from test_assembly_bridge_v3 import make as mixed_source
    from test_assembly_export_contracts import export_bridge

    from mechanical_cad.assembly_export import run_assembly_step_export

    if version == 2:
        raw_request, _, _ = legacy_source.__wrapped__(monkeypatch)(new_sketch=False)
        geometry_kernel = LegacyKernel(new_sketch=False)
    else:
        source = mixed_source.__wrapped__(monkeypatch)
        raw_request, _, _ = source()
        geometry_kernel = MixedKernel(source.replays)
    candidate = copy.deepcopy(raw_request["assembly"])
    candidate["verification_presets"] = model()["verification_presets"]
    candidate["active_verification_preset"] = model()["active_verification_preset"]
    kernel = ContactKernel()
    kernel.manufacturing_check = geometry_kernel.manufacturing_check
    kernel.export_assembly_step = lambda name, parts, instances, path: path.write_bytes(
        b"synthetic STEP"
    )
    path = tmp_path / "assembly.step"
    operation = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "action": "assembly_export_step",
        "result_version": version,
        "assembly": candidate,
        "path": str(path),
    }
    response = run_assembly_step_export(operation, kernel=kernel)
    assert response["ok"] is True, response.get("error")
    assert export_bridge.validate_response(operation, response)["ok"] is True
    assert response["result"]["report"]["passed"] is False
    assert response["result"]["report"]["policy_accepted"] is True
    assert path.read_bytes() == b"synthetic STEP"

    candidate["verification_presets"][0]["requirements"][0].pop("contact_policy")
    kernel.index = 0
    failed = run_assembly_step_export(operation, kernel=kernel)
    assert failed["ok"] is False and failed["export"] is None
    assert path.read_bytes() == b"synthetic STEP"
    with pytest.raises(export_bridge.bridge.BridgeError):
        export_bridge.validate_response(operation, response)
