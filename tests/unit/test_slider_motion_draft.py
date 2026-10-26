"""Slider motion drafts preserve canonical millimetres and all authored structure."""

import copy
import importlib

import pytest
from test_assembly_gears import PACKAGE, mechanism

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument

MotionDraft = importlib.import_module(PACKAGE + ".assembly_motion_draft").MotionDraft


@pytest.fixture
def slider():
    data = mechanism(relations=False).to_dict()
    data["joints"][0].update(kind="slider", coordinate=5.0, limits=[-20, 80])
    return data


def test_slider_moves_exact_canonical_mm_without_changing_frames_links_limits(slider):
    before = copy.deepcopy(slider)
    draft = MotionDraft(slider, "driver")
    assert draft.kind == "slider"
    draft.coordinate = 25.5
    candidate = draft.candidate()
    expected = copy.deepcopy(before)
    expected["joints"][0]["coordinate"] = 25.5
    assert candidate == expected and slider == before
    assert draft.effective_coordinates() == {"driver": 25.5, "follower": 0.75, "tail": 0.125}
    original_pose = evaluate(AssemblyDocument.from_dict(before))
    moved_pose = evaluate(AssemblyDocument.from_dict(candidate))
    assert original_pose.transforms["a"].point((0, 0, 0)) == pytest.approx((0, 0, 5))
    assert moved_pose.transforms["a"].point((0, 0, 0)) == pytest.approx((0, 0, 25.5))
    assert moved_pose.transforms["a"].point((1, 0, 0)) == pytest.approx((1, 0, 25.5))
    for instance in ("base", "b", "c"):
        assert moved_pose.transforms[instance] == original_pose.transforms[instance]
    candidate["joints"][0]["name"] = "Detached edit"
    slider["joints"][0]["limits"][1] = 6
    assert draft.candidate() == expected


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), -float("inf"), "10", None, -21, 81])
def test_slider_rejects_invalid_or_out_of_limit_coordinate_without_mutation(slider, value):
    before = copy.deepcopy(slider)
    draft = MotionDraft(slider, "driver")
    draft.coordinate = value
    with pytest.raises(ValueError, match="Slider displacement"):
        draft.candidate()
    assert slider == before


@pytest.mark.parametrize("value", [-1e6, 1e6])
def test_slider_uses_canonical_mm_range_not_revolute_angle_bound(slider, value):
    slider["joints"][0].pop("limits")
    draft = MotionDraft(slider, "driver")
    draft.coordinate = value
    candidate = draft.candidate()
    assert candidate["joints"][0]["coordinate"] == value
    assert "limits" not in candidate["joints"][0]
    AssemblyDocument.from_dict(candidate)  # Independently agrees with canonical schema.
    draft.coordinate = value * 1.000001
    with pytest.raises(ValueError, match="1000000 mm"):
        draft.candidate()


@pytest.mark.parametrize("kind", ["fixed", "cylindrical", "planar", "spherical"])
def test_non_pilot_joint_kinds_still_reject(slider, kind):
    slider["joints"][0]["kind"] = kind
    with pytest.raises(ValueError, match="independent revolute or slider"):
        MotionDraft(slider, "driver")


def test_slider_requires_independent_coordinate(slider):
    slider["joints"][0]["coordinate"] = None
    with pytest.raises(ValueError, match="independent numeric"):
        MotionDraft(slider, "driver")


def test_slider_cannot_be_reinterpreted_as_a_gear_endpoint():
    data = mechanism().to_dict()
    data["joints"][0]["kind"] = "slider"
    with pytest.raises(ValueError, match="revolute"):
        MotionDraft(data, "driver")


def test_independent_slider_keeps_existing_revolute_gear_derivation():
    data = mechanism().to_dict()
    instance = copy.deepcopy(data["instances"][-1])
    instance["id"] = "slide"
    data["instances"].append(instance)
    joint = copy.deepcopy(data["joints"][0])
    joint.update(id="slider", child="slide", kind="slider", coordinate=10, limits=[0, 50])
    data["joints"].append(joint)
    before = copy.deepcopy(data)
    draft = MotionDraft(data, "slider")
    draft.coordinate = 20
    result = draft.candidate()
    assert result["joints"][:-1] == before["joints"][:-1]
    assert result["gear_relations"] == before["gear_relations"]
    assert draft.effective_coordinates() == {"driver": 0.25, "slider": 20, "follower": 0.75, "tail": 0.125}
    assert data == before
