"""Useful repeated-part assemblies remain bounded by graph and query budgets."""

from dataclasses import replace

import pytest
from test_assembly_model import assembly

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument, Instance, Joint
from mechanical_cad.errors import CADException


def repeated(count):
    base = assembly("fixed")
    instances = tuple(Instance(f"i{i}", "p") for i in range(count))
    joints = tuple(Joint(f"j{i}", "fixed", "i0", f"i{i}", "axis", "axis") for i in range(1, count))
    return replace(base, instances=instances, joints=joints, grounded_instance="i0")


def test_64_named_instances_roundtrip_and_pose():
    value = repeated(64)
    parsed = AssemblyDocument.from_json(value.to_json())
    assert len(parsed.instances) == 64
    result = evaluate(parsed)
    assert result.status == "evaluated"
    assert len(result.transforms) == 64


def test_65_instances_remain_rejected():
    with pytest.raises(CADException):
        repeated(65)
