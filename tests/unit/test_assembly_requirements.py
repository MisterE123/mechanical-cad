"""Persisted engineering intent stays separate from numerical resolution and poses."""

import json
import math
from dataclasses import FrozenInstanceError, replace
from itertools import combinations

import pytest

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Instance,
    Joint,
    MateFrame,
    PartDefinition,
    PartSource,
)
from mechanical_cad.assembly_requirements import (
    MAX_REQUIREMENTS_PER_PRESET,
    MAX_TOTAL_CLEARANCE_REQUIREMENTS,
    MAX_VERIFICATION_PRESETS,
    ClearanceRequirement,
    NumericalPolicy,
    VerificationPreset,
)
from mechanical_cad.errors import CADException


def requirement(pair=("i0", "i1"), minimum=0.5):
    return ClearanceRequirement("clearance", "Pin-to-leaf running clearance", pair, minimum)


def preset():
    return VerificationPreset("normal", "Normal operation", (requirement(),))


def assembly(doc, count=2):
    source = PartSource.from_document(doc)
    part = PartDefinition(
        "part", source.source_digest, source.id, doc.active_feature, (MateFrame("axis"),)
    )
    return AssemblyDocument(
        "assembly",
        "Test mechanism",
        (source,),
        (part,),
        tuple(Instance(f"i{i}", "part") for i in range(count)),
        tuple(Joint(f"j{i}", "fixed", "i0", f"i{i}", "axis", "axis") for i in range(1, count)),
        "i0",
    )


def test_explicit_units_conservative_defaults_and_roundtrip():
    p = preset()
    assert p.policy.to_dict() == {
        "linear_tolerance_mm": 1e-6,
        "volume_tolerance_mm3": 1e-9,
        "linear_deflection_mm": 0.1,
    }
    assert p.requirements[0].minimum_mm == 0.5
    assert VerificationPreset.from_dict(json.loads(json.dumps(p.to_dict()))) == p
    assert p.to_dict()["kind"] == "clearance"
    assert set(p.to_dict()) == {"id", "name", "requirements", "policy", "kind"}
    assert set(p.requirements[0].to_dict()) == {"id", "name", "instances", "minimum_mm"}


def test_pair_order_normalizes_without_aliasing_input():
    pair = ["i1", "i0"]
    r = requirement(pair)
    pair[0] = "different"
    assert r.instances == ("i0", "i1")
    assert r == requirement()
    assert r.to_dict()["instances"] == ["i0", "i1"]
    with pytest.raises(FrozenInstanceError):
        r.minimum_mm = 1
    requirements = [r]
    p = VerificationPreset("preset", "Named", requirements)
    requirements.clear()
    assert p.requirements == (r,)
    data = p.to_dict()
    data["requirements"][0]["instances"][0] = "changed"
    data["policy"]["linear_tolerance_mm"] = 1
    assert p.requirements == (r,) and p.policy.linear_tolerance_mm == 1e-6


@pytest.mark.parametrize(
    "value",
    [True, False, "0.5", "0.5 mm", None, math.nan, math.inf, -math.inf, -0.001, 1000001, 10**1000],
)
def test_minimum_clearance_requires_finite_nonnegative_bounded_number(value):
    with pytest.raises(CADException) as exc:
        requirement(minimum=value)
    assert exc.value.code == "invalid_clearance"


@pytest.mark.parametrize("minimum", [0, 1e6])
def test_minimum_clearance_inclusive_bounds(minimum):
    assert requirement(minimum=minimum).minimum_mm == minimum


@pytest.mark.parametrize(
    "pair",
    [(), ("i0",), ("i0", "i1", "i2"), ("i0", "i0"), ("../i0", "i1"), (True, "i1"), "i0,i1", None],
)
def test_pair_requires_exactly_two_distinct_stable_instance_ids(pair):
    with pytest.raises(CADException):
        requirement(pair)


@pytest.mark.parametrize(
    "field,lower,upper",
    [
        ("linear_tolerance_mm", 1e-9, 1),
        ("volume_tolerance_mm3", 1e-15, 1),
        ("linear_deflection_mm", 0.001, 10),
    ],
)
def test_policy_boundaries_match_service_contract(field, lower, upper):
    for value in (lower, upper):
        assert getattr(replace(NumericalPolicy(), **{field: value}), field) == value
    for value in (
        0,
        lower / 2,
        upper * 2,
        True,
        "1",
        None,
        math.nan,
        math.inf,
        -math.inf,
        10**1000,
    ):
        with pytest.raises(CADException) as exc:
            replace(NumericalPolicy(), **{field: value})
        assert exc.value.code == "invalid_tolerance"


@pytest.mark.parametrize("factory", [requirement, preset])
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", ""),
        ("id", "../bad"),
        ("id", "x" * 129),
        ("name", ""),
        ("name", None),
        ("name", "n" * 257),
        ("name", "\ud800"),
    ],
)
def test_stable_ids_and_explicit_names(factory, field, value):
    with pytest.raises(CADException):
        replace(factory(), **{field: value})


@pytest.mark.parametrize("record", [requirement(), preset(), NumericalPolicy()])
def test_unknown_missing_or_wrong_record_keys_rejected(record):
    data = record.to_dict()
    for key in data:
        incomplete = dict(data)
        del incomplete[key]
        with pytest.raises(CADException):
            type(record).from_dict(incomplete)
    for invalid in ({**data, "surprise": True}, None, [], {1: "bad"}):
        with pytest.raises(CADException):
            type(record).from_dict(invalid)


def test_duplicate_pair_reversed_pair_and_scoped_requirement_ids_rejected():
    first = requirement()
    with pytest.raises(CADException) as exc:
        VerificationPreset(
            "preset", "Duplicates", (first, replace(first, id="other", instances=("i1", "i0")))
        )
    assert exc.value.code == "invalid_clearance_pair"
    with pytest.raises(CADException) as exc:
        VerificationPreset(
            "preset", "Duplicate IDs", (first, replace(first, instances=("i0", "i2")))
        )
    assert exc.value.code == "duplicate_id"


def test_clearance_intent_and_explicit_interference_only_are_distinct():
    with pytest.raises(CADException):
        VerificationPreset("empty", "Empty clearance", ())
    p = VerificationPreset("interference", "Interference only", (), kind="interference_only")
    assert VerificationPreset.from_dict(p.to_dict()) == p
    with pytest.raises(CADException):
        replace(p, requirements=(requirement(),))
    for kind in ("default", "all", "ignore_interference", True, [], None):
        with pytest.raises(CADException):
            replace(p, kind=kind)
    with pytest.raises(CADException):
        replace(preset(), policy={})
    with pytest.raises(CADException):
        replace(preset(), requirements=[requirement().to_dict()])


def test_json_record_arrays_are_strict():
    data = requirement().to_dict()
    data["instances"] = ("i0", "i1")
    with pytest.raises(CADException):
        ClearanceRequirement.from_dict(data)
    data = preset().to_dict()
    data["requirements"] = tuple(data["requirements"])
    with pytest.raises(CADException):
        VerificationPreset.from_dict(data)


def test_assembly_no_preset_default_is_explicit_and_never_auto_selects(plate):
    a = assembly(plate)
    assert a.verification_presets == () and a.active_verification_preset is None
    data = a.to_dict()
    assert data["verification_presets"] == [] and data["active_verification_preset"] is None
    del data["verification_presets"]
    del data["active_verification_preset"]
    assert AssemblyDocument.from_dict(data).to_json() == a.to_json()
    with_one = replace(a, verification_presets=(preset(),))
    assert with_one.active_verification_preset is None
    assert AssemblyDocument.from_json(with_one.to_json()).active_verification_preset is None


def test_assembly_presets_validate_instance_references_and_active_selection(plate):
    a = assembly(plate)
    p = preset()
    good = replace(a, verification_presets=(p,), active_verification_preset=p.id)
    assert AssemblyDocument.from_json(good.to_json()) == good
    for active in ("missing", "", True, [], 0):
        with pytest.raises(CADException):
            replace(good, active_verification_preset=active)
    with pytest.raises(CADException) as exc:
        replace(
            a, verification_presets=(replace(p, requirements=(requirement(("i0", "missing")),)),)
        )
    assert exc.value.code == "invalid_clearance_pair"
    with pytest.raises(CADException) as exc:
        replace(a, verification_presets=(p, p))
    assert exc.value.code == "duplicate_id"
    with pytest.raises(CADException):
        replace(good, verification_presets=())  # Never silently clear a dangling selection.


def test_all_pair_and_preset_resource_caps(plate):
    a = assembly(plate, count=16)
    requirements = tuple(
        ClearanceRequirement(f"r{i}", f"Clearance {i}", pair, 0)
        for i, pair in enumerate(combinations([f"i{j}" for j in range(16)], 2))
    )
    assert len(requirements) == MAX_REQUIREMENTS_PER_PRESET == 120
    p = VerificationPreset("preset", "All named pairs", requirements)
    presets = tuple(replace(p, id=f"p{i}") for i in range(MAX_VERIFICATION_PRESETS))
    complete = replace(a, verification_presets=presets)
    assert (
        sum(len(p.requirements) for p in complete.verification_presets)
        == MAX_TOTAL_CLEARANCE_REQUIREMENTS
    )
    assert AssemblyDocument.from_json(complete.to_json()) == complete
    with pytest.raises(CADException) as exc:
        replace(p, requirements=(*requirements, replace(requirements[0], id="overflow")))
    assert exc.value.code == "resource_limit"
    with pytest.raises(CADException) as exc:
        replace(a, verification_presets=(*presets, replace(p, id="extra")))
    assert exc.value.code == "resource_limit"
    data = p.to_dict()
    data["requirements"] *= 2
    with pytest.raises(CADException):
        VerificationPreset.from_dict(data)


def test_preset_edits_invalidate_hashes_without_changing_geometry_or_physical_pose(plate):
    a = replace(
        assembly(plate), verification_presets=(preset(),), active_verification_preset="normal"
    )
    base = evaluate(a)
    variants = [
        replace(a, active_verification_preset=None),
        replace(a, verification_presets=(replace(preset(), name="Renamed operation"),)),
        replace(
            a, verification_presets=(replace(preset(), requirements=(requirement(minimum=1),)),)
        ),
        replace(
            a,
            verification_presets=(
                replace(preset(), policy=NumericalPolicy(linear_tolerance_mm=2e-6)),
            ),
        ),
        replace(
            a,
            verification_presets=(
                VerificationPreset("normal", "Interference only", (), kind="interference_only"),
            ),
        ),
    ]
    for edited in variants:
        result = evaluate(edited)
        assert edited.content_hash != a.content_hash and result.pose_digest != base.pose_digest
        assert (
            result.transforms == base.transforms
            and result.effective_coordinates == base.effective_coordinates
        )
        assert edited.source_hashes == a.source_hashes
        assert (
            edited.parts == a.parts
            and edited.instances == a.instances
            and edited.joints == a.joints
        )
    assert a.verification_presets[0].requirements[0].minimum_mm == 0.5


def test_source_update_retains_preset_ids_values_and_selected_intent(plate):
    a = replace(
        assembly(plate), verification_presets=(preset(),), active_verification_preset="normal"
    )
    b = a.replace_source(plate.id, plate.with_parameter("width", 50))
    assert b.verification_presets == a.verification_presets
    assert b.active_verification_preset == a.active_verification_preset
    assert b.content_hash != a.content_hash
