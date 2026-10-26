"""Detached complete pair candidates and native-free contract parity."""

import importlib
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_gear_pair_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
pair = importlib.import_module(PACKAGE + ".gear_pair")
contracts = importlib.import_module(PACKAGE + ".operation_contracts")


@pytest.mark.parametrize("teeth_a,teeth_b", [(20, 40), (19, 37), (20, 37), (19, 40)])
def test_complete_rooted_pair_phase_and_axis_sign(teeth_a, teeth_b):
    candidate = pair.build_pair(teeth_a=teeth_a, teeth_b=teeth_b)
    model = AssemblyDocument.from_dict(candidate)
    assert contracts.result_version_for_assembly(candidate) == 2
    assert len(model.parts) == 3 and len(model.joints) == 2
    for part in candidate["part_sources"]:
        doc = part["document"]
        assert part["source_digest"] == pair.canonical_digest(doc)
        assert contracts.result_version_for(doc) == 2
    for angle in (0, 0.13, -0.25, 2 * math.pi):
        pose = evaluate(model, {"shaft_a": angle}).to_dict()
        assert pose["status"] == "evaluated"
        assert pose["structural_dof"] == 1
        assert pose["effective_coordinates"]["shaft_b"] == pytest.approx(
            -teeth_a / teeth_b * angle + math.pi + math.pi / teeth_b
        )
        assert pose["transforms"]["instance_2"]["xyz_mm"] == [teeth_a + teeth_b, 0, 0]
        assert pose["transforms"]["instance_1"]["wxyz"][1:3] == [0, 0]
    parameters = [s["document"]["parameters"] for s in candidate["part_sources"]][1:]
    assert sum(p["backlash"] for p in parameters) == pytest.approx(0.2)
    assert all(p["clearance"] == 0.25 for p in parameters)
    # B's inward ray is midway between adjacent tooth centerlines, even for odd z.
    phase = candidate["gear_relations"][0]["offset_rad"]
    assert ((math.pi - phase) * teeth_b / (2 * math.pi)) % 1 == pytest.approx(0.5)


@pytest.mark.parametrize(
    "change",
    [
        {"module": float("nan")},
        {"teeth_a": True},
        {"teeth_b": 17},
        {"bore_a": 1000},
        {"pair_backlash": -0.1},
        {"pair_backlash": 3},
        {"clearance": 0.6},
        {"profile_tolerance": 0},
        {"module": 0.01},
    ],
)
def test_invalid_inputs_reject_before_candidate_or_mutation(change):
    with pytest.raises(ValueError):
        pair.build_pair(**change)


def test_repeated_builds_have_independent_source_identity():
    a, b = pair.build_pair(), pair.build_pair()
    assert a["id"] != b["id"]
    assert {s["source_document_id"] for s in a["part_sources"]}.isdisjoint(
        {s["source_document_id"] for s in b["part_sources"]}
    )


def test_edit_pair_retains_identity_names_pose_and_recomputes_all_dependents():
    import copy

    accepted = AssemblyDocument.from_dict(pair.build_pair()).to_dict()
    accepted["joints"][0]["coordinate"] = 0.37
    accepted["parts"][1]["name"] = "My driver"
    original = copy.deepcopy(accepted)
    assert pair.recognize_pair(accepted)["teeth_b"] == 40
    candidate = pair.edit_pair(accepted, module=1.5, teeth_a=24, teeth_b=36, bore_b=6)
    assert accepted == original
    assert candidate["id"] == accepted["id"]
    assert [s["source_document_id"] for s in candidate["part_sources"]] == [
        s["source_document_id"] for s in accepted["part_sources"]
    ]
    assert candidate["parts"][1]["name"] == "My driver"
    assert candidate["joints"][0]["coordinate"] == 0.37
    assert pair.recognize_pair(candidate)["teeth_a"] == 24
    pose = evaluate(AssemblyDocument.from_dict(candidate)).to_dict()
    assert pose["transforms"]["instance_2"]["xyz_mm"] == [45, 0, 0]
    assert pose["effective_coordinates"]["shaft_b"] == pytest.approx(
        -24 / 36 * 0.37 + math.pi + math.pi / 36
    )
    assert candidate["part_sources"][0] == accepted["part_sources"][0]
    assert (
        candidate["part_sources"][1]["source_digest"]
        != accepted["part_sources"][1]["source_digest"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x.update(id="arbitrary_assembly"),
        lambda x: x["part_sources"][1]["document"]["parameters"].update(module=3),
        lambda x: x["part_sources"][2]["document"]["parameters"].update(backlash=0.12),
        lambda x: x["parts"][0]["mate_frames"][1]["placement"]["xyz_mm"].__setitem__(0, 70),
        lambda x: x["joints"][0].update(limits=[-1, 1]),
        lambda x: x["joints"][1].update(coordinate=0),
        lambda x: x["joints"][0].update(coordinate=True),
        lambda x: x["gear_relations"][0].update(ratio=0.5),
        lambda x: x["gear_relations"][0].update(offset_rad=0),
        lambda x: x["instances"].append(dict(x["instances"][1], id="extra")),
        lambda x: x["ground"]["xyz_mm"].__setitem__(0, 1),
        lambda x: x["parts"][1].update(extra="unknown"),
    ],
)
def test_customized_pairs_fail_closed_without_mutation(mutation):
    import copy

    candidate = pair.build_pair()
    mutation(candidate)
    original = copy.deepcopy(candidate)
    with pytest.raises(ValueError, match="customized or not recognized"):
        pair.edit_pair(candidate, teeth_a=24)
    assert candidate == original


def test_edit_invalid_parameter_preserves_accepted_pair():
    import copy

    accepted = pair.build_pair()
    original = copy.deepcopy(accepted)
    with pytest.raises(ValueError):
        pair.edit_pair(accepted, bore_a=1000)
    assert accepted == original


def test_saved_verification_intent_retained_without_aliasing_and_default_names_updated():
    from mechanical_cad.assembly_requirements import ClearanceRequirement, VerificationPreset

    accepted = pair.build_pair()
    accepted["verification_presets"] = [
        VerificationPreset(
            "fit",
            "Print fit",
            (ClearanceRequirement("gap", "Gap", ("instance_1", "instance_2"), 0.1),),
        ).to_dict()
    ]
    accepted["active_verification_preset"] = "fit"
    accepted = AssemblyDocument.from_dict(accepted).to_dict()
    assert pair.recognize_pair(accepted)["module"] == 2
    changed = pair.edit_pair(accepted, teeth_a=24)
    assert changed["parts"][1]["name"] == "Gear A (24 teeth)"
    assert changed["instances"][1]["name"] == "Gear A (24 teeth)"
    assert changed["part_sources"][1]["document"]["name"] == "Gear A (24 teeth)"
    assert changed["verification_presets"] == accepted["verification_presets"]
    assert changed["active_verification_preset"] == "fit"
    assert pair.recognize_pair(changed)["teeth_a"] == 24
    changed["verification_presets"][0]["name"] = "Changed"
    assert accepted["verification_presets"][0]["name"] == "Print fit"
