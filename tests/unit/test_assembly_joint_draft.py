"""Pure visual candidates agree with the existing canonical tree evaluator."""

import copy
import importlib.util
import json
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument, Frame

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
PACKAGE = "mcad_joint_draft_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(
    PACKAGE + ".assembly_joint_draft", ADDON / "assembly_joint_draft.py"
)
draft_api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = draft_api
spec.loader.exec_module(draft_api)


def fixture():
    return json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())


def poses(assembly):
    result = evaluate(AssemblyDocument.from_dict(assembly))
    assert result.status == "evaluated"
    return {key: frame.to_dict() for key, frame in result.transforms.items()}


def draft(assembly=None, parent="root", child="a", **kwargs):
    assembly = fixture() if assembly is None else assembly
    return draft_api.JointDraft(assembly, poses(assembly), parent, child, **kwargs)


def same_frame(left, right):
    assert left["xyz_mm"] == pytest.approx(right["xyz_mm"], abs=1e-8)
    for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        assert draft_api.rotate(left["wxyz"], axis) == pytest.approx(
            draft_api.rotate(right["wxyz"], axis), abs=1e-10
        )


def agrees_with_core(session):
    candidate = session.candidate()
    preview, expected = session.preview_transforms(), poses(candidate)
    assert preview.keys() == expected.keys()
    for key in expected:
        same_frame(preview[key], expected[key])
    return candidate, preview


def test_exact_noop_preserves_inputs_source_ids_and_quaternion_signs():
    assembly = fixture()
    assembly["ground"]["wxyz"] = [-1.0, 0.0, 0.0, 0.0]
    assembly["parts"][0]["mate_frames"][0]["placement"]["wxyz"] = [-1.0, 0.0, 0.0, 0.0]
    original = copy.deepcopy(assembly)
    transforms = poses(assembly)
    saved_transforms = copy.deepcopy(transforms)
    session = draft_api.JointDraft(assembly, transforms, "root", "a", "slide_a")
    session.translate_connector("parent", "X", 0)
    session.turn_connector("child", "Z", 4)
    session.align_connector("parent", "+Z")
    session.set_connector_world("child", session.connector_world("child"))
    assert session.candidate() == original
    assert session.preview_transforms() == saved_transforms
    assert assembly == original and transforms == saved_transforms
    assert session.joint_id == "slide_a"
    assert session.subtree_ids == ("a",)
    leaked = session.original
    leaked["parts"].clear()
    session.original_joint["name"] = "Not saved"
    assert session.candidate() == original


def test_fixed_selection_identity_and_subtree_are_read_only():
    session = draft()
    for key in ("parent_id", "child_id", "joint_id", "subtree_ids"):
        with pytest.raises(AttributeError):
            setattr(session, key, "Changed")


def test_name_limits_and_noop_legacy_defaults_do_not_roundtrip_saved_frames_or_pose():
    assembly = fixture()
    assembly["parts"][0]["mate_frames"][0]["placement"]["wxyz"] = [-1.0, 1e-12, 0.0, 0.0]
    del assembly["joints"][0]["limits"]
    session = draft(assembly)
    assert session.candidate() == assembly
    session.name = "Renamed"
    session.limits = [0, 400]
    candidate = session.candidate()
    assert candidate["parts"] == assembly["parts"]
    assert candidate["joints"][0]["name"] == "Renamed"
    assert candidate["joints"][0]["limits"] == [0, 400]
    assert session.preview_transforms() == poses(assembly)


def test_shared_origin_copy_on_write_keeps_reused_sibling_pose_and_source():
    session = draft()
    session.translate_connector("parent", "X", 10)
    session.translate_connector("child", "Y", -3)
    candidate, preview = agrees_with_core(session)
    assert candidate["parts"][0]["mate_frames"][:2] == fixture()["parts"][0]["mate_frames"]
    assert len(candidate["parts"][0]["mate_frames"]) == 4
    joint = candidate["joints"][0]
    assert joint["parent_frame"] != joint["child_frame"]
    assert joint["parent_frame"] != "origin" != joint["child_frame"]
    assert preview["b"] == poses(fixture())["b"]
    assert candidate["joints"][1] == fixture()["joints"][1]
    assert candidate["part_sources"] == fixture()["part_sources"]
    assert candidate["instances"] == fixture()["instances"]
    assert candidate == session.candidate() == session.candidate()
    candidate["parts"][0]["mate_frames"][2]["placement"]["xyz_mm"][0] = 999
    assert session.candidate()["parts"][0]["mate_frames"][2]["placement"]["xyz_mm"][0] == 10


def test_repeated_edit_reuses_exclusive_connectors_without_frame_growth():
    first = draft()
    first.translate_connector("parent", "X", 10)
    first.translate_connector("child", "Y", -3)
    candidate = first.candidate()
    ids = [frame["id"] for frame in candidate["parts"][0]["mate_frames"]]
    second = draft(candidate, joint_id="slide_a")
    second.translate_connector("parent", "X", 5)
    second.turn_connector("child", "Z")
    updated, _preview = agrees_with_core(second)
    assert [frame["id"] for frame in updated["parts"][0]["mate_frames"]] == ids
    assert updated["joints"][0]["parent_frame"] == candidate["joints"][0]["parent_frame"]
    assert updated["joints"][0]["child_frame"] == candidate["joints"][0]["child_frame"]


def test_other_joint_reference_clones_an_existing_non_origin_frame():
    assembly = fixture()
    assembly["joints"][0]["parent_frame"] = "offset"
    session = draft(assembly)
    session.translate_connector("parent", "Z", 11)
    candidate, preview = agrees_with_core(session)
    assert candidate["parts"][0]["mate_frames"][1] == assembly["parts"][0]["mate_frames"][1]
    assert candidate["joints"][0]["parent_frame"] != "offset"
    assert preview["b"] == poses(assembly)["b"]


def test_rotated_parent_connector_slider_and_descendants_match_core():
    assembly = fixture()
    assembly["ground"] = Frame((31, -17, 9), (0.5, 0.5, 0.5, 0.5)).to_dict()
    assembly["instances"].append({"id": "tip", "name": "Tip", "part_id": "block"})
    assembly["joints"].append(
        {
            "id": "tip_fixed",
            "name": "Tip fixed",
            "kind": "fixed",
            "parent": "a",
            "child": "tip",
            "parent_frame": "offset",
            "child_frame": "origin",
        }
    )
    session = draft(assembly)
    session.coordinate = 175
    session.turn_connector("parent", "Y")
    session.turn_connector("child", "X", -1)
    session.translate_connector("child", "Z", 7)
    _candidate, preview = agrees_with_core(session)
    assert session.subtree_ids == ("a", "tip")
    assert preview["root"] == poses(assembly)["root"]
    assert preview["b"] == poses(assembly)["b"]


def test_reparent_starts_without_jump_and_changes_only_existing_incoming_edge():
    assembly = fixture()
    session = draft(assembly, parent="b", child="a")
    candidate, preview = agrees_with_core(session)
    for key in preview:
        same_frame(preview[key], poses(assembly)[key])
    assert len(candidate["joints"]) == len(assembly["joints"])
    assert candidate["joints"][0]["id"] == "slide_a"
    assert candidate["joints"][0]["parent"] == "b"
    assert candidate["joints"][0]["kind"] == assembly["joints"][0]["kind"]
    assert candidate["joints"][0]["coordinate"] == assembly["joints"][0]["coordinate"]
    assert candidate["joints"][0]["limits"] == assembly["joints"][0]["limits"]
    session.kind, session.coordinate = "slider", 25
    session.align_connector("parent", "-X")
    agrees_with_core(session)


@pytest.mark.parametrize("parent,child", [("a", "root"), ("a", "a"), ("missing", "a")])
def test_invalid_instance_pair_rejected(parent, child):
    with pytest.raises(draft_api.BridgeError):
        draft(parent=parent, child=child)


def test_descendant_parent_and_wrong_incoming_joint_rejected():
    assembly = fixture()
    assembly["joints"][1]["parent"] = "a"
    with pytest.raises(draft_api.BridgeError, match="descendant"):
        draft(assembly, parent="b", child="a")
    with pytest.raises(draft_api.BridgeError, match="incoming"):
        draft(joint_id="slide_b")


@pytest.mark.parametrize("coordinate", [True, float("nan"), float("inf"), 1_000_001, -1, 301])
def test_slider_coordinate_rejected_without_clamping(coordinate):
    session = draft()
    session.coordinate = coordinate
    with pytest.raises(draft_api.BridgeError):
        session.candidate()
    with pytest.raises(draft_api.BridgeError):
        session.preview_transforms()


@pytest.mark.parametrize("coordinate", [0, 300])
def test_inclusive_slider_limit_endpoints(coordinate):
    session = draft()
    session.coordinate = coordinate
    agrees_with_core(session)


@pytest.mark.parametrize("limits", [[1, 1], [3, 2], [0], [False, 300], [0, float("inf")]])
def test_slider_limits_rejected(limits):
    session = draft()
    session.limits = limits
    with pytest.raises(draft_api.BridgeError):
        session.candidate()


def test_fixed_conversion_removes_incompatible_limits_and_coordinate():
    session = draft()
    session.kind = "fixed"
    candidate, _preview = agrees_with_core(session)
    assert "limits" not in candidate["joints"][0]
    assert "coordinate" not in candidate["joints"][0]
    assert candidate["joints"][1] == fixture()["joints"][1]


def test_geometry_helpers_agree_with_frame_and_preserve_noops():
    left = Frame((12, -8, 5), (0.5, 0.5, -0.5, 0.5))
    right = Frame((3, 7, -2), (math.sqrt(0.5), 0, 0, -math.sqrt(0.5)))
    same_frame(draft_api.compose(left.to_dict(), right.to_dict()), left.then(right).to_dict())
    same_frame(draft_api.inverse(left.to_dict()), left.inverse().to_dict())
    world = draft_api.local_to_world(left.to_dict(), right.to_dict())
    same_frame(draft_api.world_to_local(left.to_dict(), world), right.to_dict())
    negative = {"xyz_mm": [2, 3, 4], "wxyz": [-1.0, 0.0, 0.0, 0.0]}
    assert draft_api.quarter_turn(negative, 0, 0) == negative
    assert draft_api.quarter_turn(negative, "X", 4) == negative


def test_batch_mesh_transform_matches_core_and_is_detached():
    frame = Frame((12, -8, 5), (0.5, 0.5, -0.5, 0.5))
    points = [[2, 3, 4], [-8.5, 9, -7], [0, 0, 0]]
    saved = copy.deepcopy(points)
    result = draft_api.transform_points(frame.to_dict(), points)
    for point, transformed in zip(points, result, strict=True):
        assert transformed == pytest.approx(frame.point(point))
    result[0][0] = 99
    assert points == saved
    for invalid in ([[]], [[True, 0, 0]], [[float("nan"), 0, 0]], [[0, 0, 0]] * 100_001):
        with pytest.raises(draft_api.BridgeError):
            draft_api.transform_points(frame.to_dict(), invalid)


@pytest.mark.parametrize(
    "axis,expected",
    [
        ("+X", [1, 0, 0]),
        ("-X", [-1, 0, 0]),
        ("+Y", [0, 1, 0]),
        ("-Y", [0, -1, 0]),
        ("+Z", [0, 0, 1]),
        ("-Z", [0, 0, -1]),
    ],
)
def test_axis_choices_align_z(axis, expected):
    assert draft_api.rotate(draft_api.axis_orientation(axis), [0, 0, 1]) == pytest.approx(expected)


def test_world_translation_uses_instance_rotation_and_local_uses_connector_rotation():
    assembly = fixture()
    assembly["ground"] = Frame.rz(math.pi / 2).to_dict()
    session = draft(assembly)
    before = session.connector_world("parent")
    session.translate_connector("parent", "X", 10, space="world")
    after = session.connector_world("parent")
    assert after["xyz_mm"] == pytest.approx([before["xyz_mm"][0] + 10, *before["xyz_mm"][1:]])
    session.align_connector("parent", "+X")
    before_local = copy.deepcopy(session.parent_frame)
    session.translate_connector("parent", "Z", 7)
    assert session.parent_frame["xyz_mm"] == pytest.approx(
        [before_local["xyz_mm"][0] + 7, *before_local["xyz_mm"][1:]]
    )
    agrees_with_core(session)


def test_invalid_frame_complete_pose_and_frame_limit_are_rejected():
    assembly = fixture()
    with pytest.raises(draft_api.BridgeError, match="complete"):
        draft_api.JointDraft(assembly, {}, "root", "a")
    session = draft()
    session.parent_frame["wxyz"] = [2, 0, 0, 0]
    with pytest.raises(draft_api.BridgeError):
        session.candidate()
    assembly["parts"][0]["mate_frames"].extend(
        {"id": f"extra_{n}", "name": f"Extra {n}", "placement": draft_api.origin_frame()}
        for n in range(126)
    )
    session = draft(assembly)
    session.translate_connector("parent", "X", 1)
    with pytest.raises(draft_api.BridgeError, match="128"):
        session.candidate()


@pytest.mark.parametrize(
    "method,args",
    [
        ("translate_connector", ("parent", "X", True)),
        ("translate_connector", ("parent", "X", 1_000_001)),
        ("translate_connector", ("parent", "bad", 1)),
        ("turn_connector", ("parent", "X", 0.5)),
        ("turn_connector", ("parent", True, 1)),
        ("align_connector", ("parent", "bad")),
        ("connector_world", ("bad",)),
        ("set_connector_world", ("child", {"xyz_mm": [0, 0, 0], "wxyz": [0, 0, 0, 0]})),
    ],
)
def test_failed_manipulation_preserves_draft(method, args):
    session = draft()
    before = session.candidate()
    with pytest.raises(draft_api.BridgeError):
        getattr(session, method)(*args)
    assert session.candidate() == before


def test_final_placement_bounds_not_intermediate_composition_bounds():
    assembly = fixture()
    assembly["ground"]["xyz_mm"] = [1e6, 0, 0]
    assembly["parts"][0]["mate_frames"][0]["placement"]["xyz_mm"] = [1e6, 0, 0]
    assembly["parts"][0]["mate_frames"][1]["placement"]["xyz_mm"] = [1e6, 0, 0]
    session = draft(assembly)
    session.coordinate = 101
    agrees_with_core(session)
    session.parent_frame["xyz_mm"][0] -= 1
    agrees_with_core(session)
    session.child_frame["xyz_mm"][0] -= 2
    with pytest.raises(draft_api.BridgeError):
        session.preview_transforms()


@pytest.mark.parametrize("angle", [-math.pi, -0.25, 0, math.pi / 2, 2 * math.pi])
def test_revolute_preview_matches_canonical_tree(angle):
    session = draft()
    session.kind = "revolute"
    session.coordinate = angle
    session.limits = [-2 * math.pi, 2 * math.pi]
    session.translate_connector("parent", "X", 12)
    session.translate_connector("child", "Y", 3)
    session.align_connector("parent", "+Y")
    candidate, _ = agrees_with_core(session)
    joint = next(j for j in candidate["joints"] if j["id"] == session.joint_id)
    reopened = draft(candidate, joint_id=joint["id"])
    assert reopened.coordinate == angle
    assert reopened.candidate() == candidate
    agrees_with_core(reopened)


@pytest.mark.parametrize("normal", [(1, 0, 0), (0, 1, 0), (0, 0, -1), (1, 2, 3)])
def test_surface_suggestion_is_literal_local_frame(normal):
    frame = draft_api.surface_frame([12, 13, 14], normal)
    length = math.sqrt(sum(v * v for v in normal))
    assert draft_api.rotate(frame["wxyz"], [0, 0, 1]) == pytest.approx(
        [v / length for v in normal], abs=1e-10
    )
    session = draft()
    session.set_connector_world("child", frame)
    candidate, _ = agrees_with_core(session)
    assert set(frame) == {"xyz_mm", "wxyz"}
    assert "face" not in json.dumps(candidate)
    same_frame(session.connector_world("child"), frame)


def test_revolute_bounds_and_surface_degeneracy_fail_closed():
    session = draft()
    session.kind, session.coordinate, session.limits = "revolute", 10001, None
    with pytest.raises(draft_api.BridgeError):
        session.candidate()
    with pytest.raises(draft_api.BridgeError):
        draft_api.surface_frame([0, 0, 0], [0, 0, 0])
