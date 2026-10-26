"""Planar and ball joints retain explicit named axes and independent bounds."""

import math
from dataclasses import replace

import pytest
from test_assembly_model import assembly

from mechanical_cad.assembly_kinematics import effective_coordinate_map, evaluate
from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.assembly_policy import sample_request
from mechanical_cad.errors import CADException


def test_planar_motion_in_parent_xy_and_z_rotation():
    a = assembly("planar")
    a = replace(
        a, joints=(replace(a.joints[0], translation_x=12, translation_y=-7, rotation=math.pi / 2),)
    )
    assert AssemblyDocument.from_json(a.to_json()) == a
    assert "coordinate" not in a.to_dict()["joints"][0]
    pose = evaluate(a)
    assert pose.status == "evaluated" and pose.structural_dof == 3
    assert pose.transforms["child"].xyz_mm == (12, -7, 0)
    assert pose.transforms["child"].rotate((1, 0, 0)) == pytest.approx((0, 1, 0))
    base = effective_coordinate_map(a)
    assert (
        sample_request(a, {"joint_id": "joint:translation_y", "values": [-10, 0, 10]}, base)[0]
        == "joint:translation_y"
    )


def test_ball_rotates_xyz_without_translating_center():
    a = assembly("spherical")
    a = replace(
        a,
        joints=(
            replace(
                a.joints[0], rotation_x=math.pi / 2, rotation_y=math.pi / 2, rotation=math.pi / 2
            ),
        ),
    )
    assert AssemblyDocument.from_json(a.to_json()) == a
    pose = evaluate(a)
    assert pose.status == "evaluated" and pose.structural_dof == 3
    assert pose.transforms["child"].xyz_mm == (0, 0, 0)
    assert pose.transforms["child"].rotate((0, 0, 1)) == pytest.approx((1, 0, 0))
    base = effective_coordinate_map(a)
    for name in ("rotation_x", "rotation_y", "rotation"):
        assert (
            sample_request(a, {"joint_id": "joint:" + name, "values": [0, 1]}, base)[0]
            == "joint:" + name
        )


@pytest.mark.parametrize(
    "kind, axis",
    [
        ("planar", "translation_x"),
        ("planar", "translation_y"),
        ("planar", "rotation"),
        ("spherical", "rotation_x"),
        ("spherical", "rotation_y"),
        ("spherical", "rotation"),
    ],
)
def test_axis_limits_and_nonfinite_reject_without_fallback(kind, axis):
    a = assembly(kind)
    a = replace(a, joints=(replace(a.joints[0], **{axis + "_limits": (-1, 1)}),))
    for value in (2, True, float("nan")):
        pose = evaluate(a, {"joint:" + axis: value})
        assert pose.status == "blocked" and not pose.transforms and not pose.effective_coordinates
    with pytest.raises(CADException):
        replace(a.joints[0], **{axis: 2})


@pytest.mark.parametrize("kind", ["planar", "spherical"])
def test_no_implicit_scalar_motion_or_cross_kind_fields(kind):
    a = assembly(kind)
    assert evaluate(a, {"joint": 1}).status == "blocked"
    with pytest.raises(CADException):
        replace(a.joints[0], coordinate=1)
    with pytest.raises(CADException):
        sample_request(a, {"joint_id": "joint", "values": [0, 1]}, effective_coordinate_map(a))
    data = a.to_dict()
    data["joints"][0]["coordinate"] = 0
    with pytest.raises(CADException):
        AssemblyDocument.from_dict(data)
    with pytest.raises(CADException):
        replace(a.joints[0], **({"rotation_x": 1} if kind == "planar" else {"translation_x": 1}))
