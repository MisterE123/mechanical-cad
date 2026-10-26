"""Real replay checks for associative viewport-joint candidates."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.assembly_service import run_assembly_action

ROOT = Path(__file__).resolve().parents[2]
package = types.ModuleType("face_mating_test_addon")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
api = importlib.import_module(package.__name__ + ".assembly_joint_draft")
picker = importlib.import_module(package.__name__ + ".assembly_face_pick")
pytestmark = pytest.mark.kernel


def replay(value):
    result = run_assembly_action(AssemblyDocument.from_dict(value), result_version=3)
    assert result["ok"], result["error"]
    return result


def make(value, result):
    return api.JointDraft(
        value,
        result["report"]["base_pose"]["transforms"],
        "root",
        "a",
        parts={p["id"]: p for p in result["result"]["parts"]},
    )


def test_face_pair_preview_copy_on_write_and_reopen():
    value = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    before = copy.deepcopy(value)
    result = replay(value)
    session = make(value, result)
    part = result["result"]["parts"][0]
    faces = [f for f in part["topology"] if f["signature"]["surface"] == "plane"]
    parent, child = faces[:2]
    index = part["mesh"]["triangle_face_ids"].index(parent["id"])
    assert picker.resolve_face(part, index) == parent["id"]
    session.attach_face("parent", parent["id"])
    session.attach_face("child", child["id"])
    session.kind, session.coordinate, session.limits = "fixed", 0, None
    session.turn_connector("child", "X", 2)
    session.turn_connector("parent", "Z", 1)
    session.translate_connector("parent", "Z", 2.5)
    candidate = session.candidate()
    assert value == before
    assert candidate["joints"][1] == before["joints"][1]
    assert len(candidate["joints"]) == len(value["joints"])
    assert candidate["parts"][0]["mate_frames"][0] == value["parts"][0]["mate_frames"][0]
    checked = replay(candidate)
    for key, frame in session.preview_transforms().items():
        expected = checked["report"]["base_pose"]["transforms"][key]
        assert frame["xyz_mm"] == pytest.approx(expected["xyz_mm"])
        assert abs(
            sum(a * b for a, b in zip(frame["wxyz"], expected["wxyz"], strict=True))
        ) == pytest.approx(1)
    reopened = make(json.loads(json.dumps(candidate)), checked)
    assert reopened.candidate() == candidate
    reopened.translate_connector("child", "X", 1.25)
    edited = reopened.candidate()
    assert {
        f["support_face"] for f in edited["parts"][0]["mate_frames"] if "support_face" in f
    } == {parent["id"], child["id"]}
    replay(edited)
    # A named attached frame reused by another joint stays unchanged on edit.
    shared = copy.deepcopy(candidate)
    shared["joints"][1]["parent_frame"] = shared["joints"][0]["parent_frame"]
    shared_result = replay(shared)
    shared_edit = make(shared, shared_result)
    shared_edit.translate_connector("parent", "X", 4)
    detached = shared_edit.candidate()
    assert detached["joints"][1] == shared["joints"][1]
    assert detached["joints"][0]["parent_frame"] != shared["joints"][0]["parent_frame"]
    old_id = shared["joints"][0]["parent_frame"]
    assert next(f for f in detached["parts"][0]["mate_frames"] if f["id"] == old_id) == next(
        f for f in shared["parts"][0]["mate_frames"] if f["id"] == old_id
    )
    replay(detached)
    malformed = copy.deepcopy(part)
    malformed["topology"][0]["provenance"]["semantic_status"] = "unknown"
    with pytest.raises(api.BridgeError, match="stable"):
        picker.resolve_face(
            malformed, malformed["mesh"]["triangle_face_ids"].index(malformed["topology"][0]["id"])
        )
    with pytest.raises(api.BridgeError, match="mapping"):
        picker.resolve_face(part, -1)


@pytest.mark.parametrize("kind", ["cylindrical", "planar", "spherical"])
def test_named_motion_survives_face_edit_reparent_and_reopen(kind):
    value = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    joint = value["joints"][0]
    joint.update(
        kind=kind,
        coordinate=3 if kind == "cylindrical" else 0,
        limits=[-5, 5] if kind == "cylindrical" else None,
    )
    if kind != "cylindrical":
        joint.pop("coordinate")
        joint.pop("limits")
    for n, name in enumerate(api.extra_names(kind)):
        joint[name], joint[name + "_limits"] = (n + 1) * 0.2, [-2, 2]
    result = replay(value)
    session = make(value, result)
    assert (
        session.candidate() == value or kind != "cylindrical"
    )  # no-scalar omission is legacy-compatible
    part = result["result"]["parts"][0]
    faces = [f for f in part["topology"] if f["signature"]["surface"] == "plane"]
    session.attach_face("parent", faces[0]["id"])
    session.attach_face("child", faces[1]["id"])
    session.turn_connector("child", "X", 2)
    session.translate_connector("parent", "Z", 1.5)
    candidate = session.candidate()
    for name in api.extra_names(kind):
        assert candidate["joints"][0][name] == joint[name]
        assert candidate["joints"][0][name + "_limits"] == joint[name + "_limits"]
    native = replay(candidate)
    for key, frame in session.preview_transforms().items():
        expected = native["report"]["base_pose"]["transforms"][key]
        assert frame["xyz_mm"] == pytest.approx(expected["xyz_mm"])
        assert abs(
            sum(a * b for a, b in zip(frame["wxyz"], expected["wxyz"], strict=True))
        ) == pytest.approx(1)
    reopened = make(candidate, native)
    assert reopened.candidate() == candidate
    with pytest.raises(api.BridgeError, match="discard"):
        reopened.change_kind("fixed")
    reparent = api.JointDraft(
        candidate,
        native["report"]["base_pose"]["transforms"],
        "b",
        "a",
        parts={p["id"]: p for p in native["result"]["parts"]},
    )
    reparented = reparent.candidate()
    assert reparented["joints"][0]["kind"] == kind
    for name in api.extra_names(kind):
        assert reparented["joints"][0][name] == joint[name]
        assert reparented["joints"][0][name + "_limits"] == joint[name + "_limits"]
    replay(reparented)
    for key, frame in reparent.preview_transforms().items():
        expected = native["report"]["base_pose"]["transforms"][key]
        assert frame["xyz_mm"] == pytest.approx(expected["xyz_mm"])


def test_new_pair_opposes_normals_and_support_edit_preserves_flip_offset():
    value = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    result = replay(value)
    session = make(value, result)
    part = result["result"]["parts"][0]
    faces = [f for f in part["topology"] if f["signature"]["surface"] == "plane"]
    face = faces[0]
    session.coordinate, session.limits = 0, None
    session.change_kind("fixed")
    session.attach_face_pair(face["id"], face["id"])
    candidate = session.candidate()
    native = replay(candidate)
    pose = native["report"]["base_pose"]["transforms"]
    support_frame = api.face_frame(face["signature"])
    assert api.local_to_world(pose["root"], support_frame)["xyz_mm"] == pytest.approx(
        api.local_to_world(pose["a"], support_frame)["xyz_mm"]
    )
    parent_normal = api.rotate(pose["root"]["wxyz"], face["signature"]["normal"])
    child_normal = api.rotate(pose["a"]["wxyz"], face["signature"]["normal"])
    assert sum(a * b for a, b in zip(parent_normal, child_normal, strict=True)) == pytest.approx(-1)
    reopened = make(candidate, native)
    assert reopened.candidate() == candidate
    reopened.turn_connector("child", "X", 2)  # Explicit Flip chooses aligned normals.
    reopened.translate_connector("child", "Z", 2.25)
    old_offset = api.world_to_local(api.face_frame(face["signature"]), reopened.child_frame)
    reopened.attach_face("child", faces[1]["id"], preserve_offset=True)
    new_offset = api.world_to_local(api.face_frame(faces[1]["signature"]), reopened.child_frame)
    assert new_offset["xyz_mm"] == pytest.approx(old_offset["xyz_mm"])
    assert abs(
        sum(a * b for a, b in zip(new_offset["wxyz"], old_offset["wxyz"], strict=True))
    ) == pytest.approx(1)
    replay(reopened.candidate())
