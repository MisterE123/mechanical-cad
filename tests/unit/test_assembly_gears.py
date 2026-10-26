"""Bounded directed gear-coordinate contracts, including independent Blender validation."""

import copy
import importlib
import math
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.assembly_kinematics import effective_coordinate_map, evaluate
from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Frame,
    GearRelation,
    Instance,
    Joint,
    MateFrame,
    PartDefinition,
    PartSource,
)
from mechanical_cad.assembly_policy import sample_request
from mechanical_cad.errors import CADException
from mechanical_cad.model import Document

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_gear_contract_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
edit = importlib.import_module(PACKAGE + ".assembly_edit")
evidence = importlib.import_module(PACKAGE + ".assembly_validation_evidence")
gears = importlib.import_module(PACKAGE + ".assembly_gears")


def mechanism(*, relations=True):
    doc = Document.from_json((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
    part = PartDefinition(
        "p",
        doc.content_hash,
        doc.id,
        doc.active_feature,
        (
            MateFrame("axis"),
            MateFrame("left", Frame((100, 0, 0))),
            MateFrame("right", Frame((200, 0, 0))),
        ),
    )
    return AssemblyDocument(
        "gear_assembly",
        "Explicit coordinate gears",
        (PartSource.from_document(doc),),
        (part,),
        (Instance("base", "p"), Instance("a", "p"), Instance("b", "p"), Instance("c", "p")),
        (
            Joint("driver", "revolute", "base", "a", "axis", "axis", 0.25),
            Joint(
                "follower",
                "revolute",
                "base",
                "b",
                "left",
                "axis",
                None if relations else 0.75,
                (-2, 2),
            ),
            Joint("tail", "revolute", "base", "c", "right", "axis", None if relations else 0.125),
        ),
        "base",
        gear_relations=(
            GearRelation("g2", "follower", "tail", 0.5, -0.25),
            GearRelation("g1", "driver", "follower", -2, 1.25),
        )
        if relations
        else (),
    )


def test_derived_coordinates_chain_signed_ratio_phase_and_independent_dof():
    model = mechanism()
    pose = evaluate(model)
    assert pose.status == "evaluated"
    assert dict(pose.effective_coordinates) == {"driver": 0.25, "follower": 0.75, "tail": 0.125}
    assert pose.structural_dof == 1
    assert pose.dof_method == "rooted_tree_independent_coordinate_count"
    moved = evaluate(model, {"driver": 0.5})
    assert moved.effective_coordinates == {"driver": 0.5, "follower": 0.25, "tail": -0.125}
    assert moved.transforms["b"].point((1, 0, 0)) == pytest.approx(
        (100 + math.cos(0.25), math.sin(0.25), 0)
    )
    assert moved.transforms["c"].point((1, 0, 0)) == pytest.approx(
        (200 + math.cos(-0.125), math.sin(-0.125), 0)
    )
    assert model.joints[1].coordinate is None


def test_old_snapshots_hash_and_independent_coordinate_behavior_preserved():
    model = mechanism(relations=False)
    assert "gear_relations" not in model.to_dict()
    assert AssemblyDocument.from_json(model.to_json()).content_hash == model.content_hash
    assert evaluate(model, {"follower": 1.1}).effective_coordinates["tail"] == 0.125
    assert evaluate(model).structural_dof == 3
    assert evaluate(model).dof_method == "rooted_tree_joint_count"


def test_saved_null_only_for_controlled_revolute_and_no_duplicate_independent_value():
    data = mechanism().to_dict()
    for mutate in (
        lambda d: d["joints"][1].update(coordinate=0.75),
        lambda d: d.pop("gear_relations"),
        lambda d: d["joints"][0].update(coordinate=None),
    ):
        broken = copy.deepcopy(data)
        mutate(broken)
        with pytest.raises(CADException, match="coordinate"):
            AssemblyDocument.from_dict(broken)


@pytest.mark.parametrize("ratio", [0, 1e-7, 1e7, True, None, "2", math.nan, math.inf])
def test_invalid_ratio_rejected(ratio):
    with pytest.raises(CADException):
        GearRelation("g", "driver", "follower", ratio)


@pytest.mark.parametrize(
    "change,code",
    [
        ({"driver_joint": "missing"}, "missing_gear_joint"),
        ({"driver_joint": "follower"}, "cyclic_gear_relation"),
        ({"driver_joint": "tail"}, "cyclic_gear_relation"),
    ],
)
def test_invalid_reference_graphs_rejected(change, code):
    data = mechanism().to_dict()
    data["gear_relations"][1].update(change)
    with pytest.raises(CADException) as exc:
        AssemblyDocument.from_dict(data)
    assert exc.value.code == code


def test_wrong_kind_multiple_drivers_and_unknown_fields_rejected():
    data = mechanism().to_dict()
    bad = copy.deepcopy(data)
    bad["joints"][0]["kind"] = "slider"
    with pytest.raises(CADException, match="revolute"):
        AssemblyDocument.from_dict(bad)
    bad = copy.deepcopy(data)
    bad["gear_relations"].append({**bad["gear_relations"][1], "id": "duplicate"})
    with pytest.raises(CADException, match="one gear driver"):
        AssemblyDocument.from_dict(bad)
    bad = copy.deepcopy(data)
    bad["gear_relations"][0]["hidden_tooth_count"] = 2
    with pytest.raises(CADException, match="unknown keys"):
        AssemblyDocument.from_dict(bad)


def test_limit_violation_is_atomic_and_controlled_overrides_never_accepted():
    model = mechanism()
    saved = model.to_json()
    for coordinates in ({"driver": 2}, {"follower": 0.75}, {"tail": 0.125}):
        pose = evaluate(model, coordinates)
        assert pose.status == "blocked" and not pose.transforms and not pose.effective_coordinates
    with pytest.raises(CADException, match="outside"):
        replace(model, joints=(replace(model.joints[0], coordinate=2), *model.joints[1:]))
    assert model.to_json() == saved
    assert evaluate(model, {"driver": -0.375}).effective_coordinates["follower"] == 2
    assert evaluate(model, {"driver": 1.625}).effective_coordinates["follower"] == -2


def test_creation_alignment_explicit_phase_remove_and_downstream_pose_preservation():
    original = mechanism(relations=False).to_dict()
    aligned = edit.edit_gear_relation(
        original,
        driver_joint="driver",
        driven_joint="follower",
        ratio=-2,
        offset_rad=123,
        keep_alignment=True,
    )
    assert aligned["gear_relations"][0]["offset_rad"] == 1.25
    before = effective_coordinate_map(AssemblyDocument.from_dict(aligned))
    explicit = edit.edit_gear_relation(
        aligned,
        relation_id=aligned["gear_relations"][0]["id"],
        driver_joint="driver",
        driven_joint="follower",
        ratio=-3,
        offset_rad=1,
        keep_alignment=False,
    )
    assert explicit["gear_relations"][0]["offset_rad"] == 1
    assert gears.saved_coordinates(explicit)["follower"] == 0.25
    chained = mechanism().to_dict()
    released = edit.remove_gear_relation(chained, "g1")
    assert released["joints"][1]["coordinate"] == 0.75
    assert effective_coordinate_map(AssemblyDocument.from_dict(released)) == before
    assert len(released["gear_relations"]) == 1
    released_all = edit.remove_gear_relation(released, "g2")
    assert "gear_relations" not in released_all
    assert original["joints"][1]["coordinate"] == 0.75


def test_sampling_requires_independent_map_and_rejects_driven_axis():
    model = mechanism()
    assert sample_request(model, {"joint_id": "driver", "values": [0, 1]}, {"driver": 0.25}) == (
        "driver",
        (0, 1),
    )
    for key in ("follower", "tail"):
        with pytest.raises(CADException, match="movable"):
            sample_request(model, {"joint_id": key, "values": [0]}, {"driver": 0.25})
    with pytest.raises(CADException, match="independent"):
        sample_request(
            model, {"joint_id": "driver", "values": [0]}, effective_coordinate_map(model)
        )


def test_native_free_contract_independently_derives_values_and_rejects_controlled_input():
    model = mechanism()
    data = model.to_dict()
    joints = {j["id"]: j for j in data["joints"]}
    assert evidence._effective(joints, {"driver": 0.5}, data["gear_relations"]) == {
        "driver": 0.5,
        "follower": 0.25,
        "tail": -0.125,
    }
    assert evidence._effective(joints, {"follower": 0.75}, data["gear_relations"]) is None
    assert evidence._effective(joints, {"driver": 2}, data["gear_relations"]) is None
    assert AssemblyDocument.from_json(model.to_json()).to_dict() == data
    source = model.part_sources[0].document
    updated = model.replace_source(source.id, replace(source, name="Updated source"))
    assert updated.gear_relations == model.gear_relations
    assert effective_coordinate_map(updated) == effective_coordinate_map(model)


def test_unchanged_relation_edit_retains_exact_record_order_and_snapshot():
    data = mechanism().to_dict()
    row = data["gear_relations"][0]
    same = edit.edit_gear_relation(
        data,
        relation_id=row["id"],
        name=row["name"],
        driver_joint=row["driver_joint"],
        driven_joint=row["driven_joint"],
        ratio=row["ratio"],
        offset_rad=row["offset_rad"],
    )
    assert same == data


def test_component_removal_requires_explicit_related_relation_removal():
    data = mechanism().to_dict()
    for key in ("a", "b", "c"):
        with pytest.raises(edit.BridgeError, match="Remove these gear relations"):
            edit.remove_component(data, key)
    released = edit.remove_gear_relation(data, "g1")
    removed, _ = edit.remove_component(released, "a")
    assert removed["gear_relations"] == [data["gear_relations"][0]]
    assert effective_coordinate_map(AssemblyDocument.from_dict(removed)) == {
        "follower": 0.75,
        "tail": 0.125,
    }
    assert data["joints"][1]["coordinate"] is None


def test_zero_driver_phase_and_bounds_do_not_imply_physical_ratio_inference():
    model = mechanism()
    pose = evaluate(model, {"driver": 0})
    assert pose.effective_coordinates == {"driver": 0.0, "follower": 1.25, "tail": 0.375}
    for offset in (True, "0", None, 10001, math.inf):
        with pytest.raises(CADException):
            GearRelation("g", "driver", "follower", 1, offset)
    high = replace(
        model,
        gear_relations=(
            GearRelation("g2", "follower", "tail", 1e6, 0),
            GearRelation("g1", "driver", "follower", 1, -0.25),
        ),
    )
    result = evaluate(high, {"driver": 0.5})
    assert result.status == "blocked" and result.effective_coordinates == {}
