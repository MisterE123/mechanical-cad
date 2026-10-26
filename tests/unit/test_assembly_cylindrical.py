"""Independent cylindrical coordinates, strict limits, and complete sample bases."""

import math
from dataclasses import replace

import pytest
from test_assembly_model import assembly

from mechanical_cad.assembly_kinematics import effective_coordinate_map, evaluate
from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.assembly_policy import sample_request
from mechanical_cad.errors import CADException


def cylinder():
    original = assembly("cylindrical")
    return replace(
        original,
        joints=(
            replace(
                original.joints[0],
                coordinate=12,
                limits=(0, 20),
                rotation=math.pi / 2,
                rotation_limits=(-math.pi, math.pi),
            ),
        ),
    )


def test_roundtrip_and_independent_motion():
    a = cylinder()
    assert AssemblyDocument.from_json(a.to_json()) == a
    pose = evaluate(a)
    assert pose.status == "evaluated"
    assert pose.structural_dof == 2
    assert pose.effective_coordinates == {"joint": 12, "joint:rotation": math.pi / 2}
    assert pose.transforms["child"].xyz_mm == (0, 0, 12)
    assert pose.transforms["child"].rotate((1, 0, 0)) == pytest.approx((0, 1, 0))
    moved = evaluate(a, {"joint:rotation": 0, "joint": 5})
    assert moved.transforms["child"].xyz_mm == (0, 0, 5)
    assert moved.transforms["child"].wxyz == (1, 0, 0, 0)
    assert moved.pose_digest != pose.pose_digest


@pytest.mark.parametrize(
    "override",
    [
        {"joint:rotation": 4},
        {"joint": 21},
        {"joint:rotation": True},
        {"joint:rotation": float("nan")},
        {"joint:rotation:oops": 0},
    ],
)
def test_invalid_motion_has_no_fallback(override):
    pose = evaluate(cylinder(), override)
    assert pose.status == "blocked"
    assert not pose.transforms and not pose.effective_coordinates


def test_sampling_both_axes_requires_complete_base():
    a = cylinder()
    base = effective_coordinate_map(a)
    assert sample_request(a, {"joint_id": "joint:rotation", "values": [0, 1]}, base) == (
        "joint:rotation",
        (0, 1),
    )
    assert sample_request(a, {"joint_id": "joint", "values": [0, 10]}, base) == ("joint", (0, 10))
    with pytest.raises(CADException):
        sample_request(a, {"joint_id": "joint", "values": [0, 10]}, {"joint": 12})


@pytest.mark.parametrize(
    "changes",
    [
        {"rotation": True},
        {"rotation_limits": (1, 1)},
        {"rotation_limits": (2, 3)},
        {"kind": "slider"},
    ],
)
def test_bad_authored_rotation_rejected(changes):
    with pytest.raises(CADException):
        replace(cylinder().joints[0], **changes)
