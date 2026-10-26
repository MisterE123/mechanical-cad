"""Detached branch removal never weakens remaining clearance requirements."""

import copy

import pytest
from test_assembly_edit import document, edit

from mechanical_cad.assembly_model import AssemblyDocument


def branched():
    a = edit.new_from_part(document())
    root = a["grounded_instance"]
    part = a["parts"][0]["id"]
    for parent, name in [(root, "Arm"), (None, "Finger"), (root, "Sibling")]:
        parent = parent or a["instances"][-1]["id"]
        a = edit.insert_instance(
            a,
            part,
            parent=parent,
            parent_frame="origin",
            child_frame="origin",
            kind="fixed",
            name=name,
            joint_name=name + " mount",
        )
    root, arm, finger, sibling = [r["id"] for r in a["instances"]]
    policy = {
        "linear_tolerance_mm": 1e-6,
        "volume_tolerance_mm3": 1e-9,
        "linear_deflection_mm": 0.1,
    }
    a = edit.edit_verification_preset(
        a,
        name="Keep some",
        kind="clearance",
        policy=policy,
        pair=[root, arm],
        minimum_mm=2,
        requirement_name="Arm clearance",
    )
    first = a["verification_presets"][-1]["id"]
    a = edit.edit_verification_preset(
        a,
        preset_id=first,
        name="Keep some",
        kind="clearance",
        policy=policy,
        pair=[root, sibling],
        minimum_mm=3,
        requirement_name="Sibling clearance",
    )
    a = edit.edit_verification_preset(
        a,
        name="Remove empty",
        kind="clearance",
        policy=policy,
        pair=[arm, finger],
        minimum_mm=4,
        requirement_name="Finger clearance",
    )
    return AssemblyDocument.from_dict(a).to_dict(), arm


def test_remove_branch_preserves_parts_and_remaining_policy():
    a, arm = branched()
    original = copy.deepcopy(a)
    candidate, impact = edit.remove_component(a, arm)
    AssemblyDocument.from_dict(candidate)
    assert a == original
    assert [r["name"] for r in impact["instances"]] == ["Arm", "Finger"]
    assert [r["name"] for r in impact["joints"]] == ["Arm mount", "Finger mount"]
    assert {r["name"] for r in impact["requirements"]} == {"Arm clearance", "Finger clearance"}
    assert impact["deleted_presets"][0]["name"] == "Remove empty"
    assert impact["active_preset_cleared"] and candidate["active_verification_preset"] is None
    assert candidate["parts"] == a["parts"] and candidate["part_sources"] == a["part_sources"]
    assert candidate["verification_presets"][0]["requirements"][0]["name"] == "Sibling clearance"
    assert candidate["verification_presets"][0]["requirements"][0]["minimum_mm"] == 3
    candidate["parts"][0]["name"] = "Detached"
    assert a == original


def test_root_and_unknown_rejected():
    a, _ = branched()
    for target in [a["grounded_instance"], "missing"]:
        with pytest.raises(RuntimeError):
            edit.remove_component(a, target)
