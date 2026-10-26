"""Explicit face-plane intent: native geometry, exact dependencies and failure gates."""

import copy
import importlib
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.errors import CADException
from mechanical_cad.kernel_ocp import KernelError, OCPKernel, _shape_bounds
from mechanical_cad.model import Document, Feature
from mechanical_cad.sidecar import process_request

PACKAGE = "up_to_face_native_addon"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package
linked = importlib.import_module(PACKAGE + ".linked_extrusion_edit")
build = importlib.import_module(PACKAGE + ".extrusion_candidate").extrusion_candidate


def document(target_z=10, profile_z=0, direction=1, offset="gap", target="stop"):
    return Document.from_dict(
        Document(
            "up_to_face",
            "Explicit planar stop",
            {"stop_z": target_z, "gap": 0},
            (
                Feature(
                    "p",
                    "sketch_rectangle",
                    "Stop outline",
                    {
                        "width": 10,
                        "height": 10,
                        "x": 50,
                        "z": "stop_z-2",
                    },
                ),
                Feature("stop", "extrude", "Stop solid", {"length": 2}, {"profile": "p"}),
                Feature(
                    "shifted",
                    "transform",
                    "Other source, same face IDs",
                    {"z": 5},
                    {"base": "stop"},
                ),
                Feature("q", "sketch_circle", "Profile", {"radius": 1, "z": profile_z}),
                Feature(
                    "tool",
                    "extrude_to_face",
                    "Up to planar face",
                    {
                        "direction": direction,
                        "offset": offset,
                    },
                    {"profile": "q", "target": target},
                    end_face="stop/face/cap.end",
                ),
            ),
            "tool",
        ).to_dict()
    )


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize("height", [3, 10, 37])
def test_replay_tracks_source_plane_not_a_frozen_depth(version, height):
    original = document().to_dict()
    original["parameters"]["stop_z"] = height
    original["parameters"]["gap"] = -0.5
    restored = Document.from_json(Document.from_dict(original).to_json())
    replay = regenerate(restored, OCPKernel(), result_version=version)
    assert replay.ok, replay.result
    stats = replay.result["features"][-1]["stats"]
    assert stats["valid"] and stats["solids"] == 1
    assert stats["volume"] == pytest.approx(math.pi * (height - 0.5))
    assert _shape_bounds(replay.shapes["tool"])[5] == pytest.approx(height - 0.5)
    assert restored.features[-1].params == {"direction": 1, "offset": "gap"}
    assert restored.features[-1].inputs == {"profile": "q", "target": "stop"}
    assert restored.features[-1].end_face == "stop/face/cap.end"
    assert "length" not in replay.result["features"][-1]["resolved_params"]
    # The resulting cap belongs to this extrusion, never to the target face.
    faces = replay.result["features"][-1]["topology"]
    assert {row["id"] for row in faces} == {
        "tool/face/cap.start",
        "tool/face/cap.end",
        "tool/face/side.circle",
    }


@pytest.mark.parametrize(
    "direction,z,offset,height", [(1, 0, 2, 12), (1, 0, -2, 8), (-1, 20, 2, 12), (-1, 20, -2, 8)]
)
def test_offset_sign_is_relative_to_explicit_travel(direction, z, offset, height):
    replay = regenerate(document(profile_z=z, direction=direction, offset=offset), OCPKernel())
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * height)
    bounds = _shape_bounds(replay.shapes["tool"])
    assert bounds[2] == pytest.approx(z if direction == 1 else z - height)
    assert bounds[5] == pytest.approx(z + height if direction == 1 else z)


def test_same_semantic_id_on_two_solids_never_changes_exact_source():
    original = document()
    first = regenerate(original, OCPKernel())
    second = regenerate(document(target="shifted"), OCPKernel())
    assert first.ok and second.ok
    assert first.result["features"][-1]["stats"]["volume"] == pytest.approx(10 * math.pi)
    assert second.result["features"][-1]["stats"]["volume"] == pytest.approx(15 * math.pi)
    assert original.features[-1].inputs["target"] == "stop"


@pytest.mark.parametrize("version", [2, 3])
def test_real_sidecar_response_is_bound_to_end_target_and_face(version):
    request = {"protocol_version": 1, "result_version": version, "document": document().to_dict()}
    response = process_request(request)
    assert response["ok"], response
    validator = importlib.import_module(
        PACKAGE + (".result_v3" if version == 3 else ".part_result_bridge")
    )
    assert validator.validate_response(request, response) == response


@pytest.mark.parametrize(
    "change,message",
    [
        ({"end_face": "stop/face/missing"}, "missing, split, or ambiguous"),
        ({"end_face": "stop/face/side.x_min"}, "parallel"),
        ({"params": {"direction": -1, "offset": 0}}, "not ahead"),
        ({"params": {"direction": 1, "offset": -10}}, "positive reach"),
    ],
)
def test_invalid_end_condition_fails_without_altering_canonical_source(change, message):
    original = document().to_dict()
    candidate = copy.deepcopy(original)
    candidate["features"][-1].update(change)
    saved = Document.from_dict(candidate).to_json()
    replay = regenerate(Document.from_json(saved), OCPKernel())
    assert not replay.ok
    item = replay.result["features"][-1]
    assert item["status"] == "failed" and message in item["error"]["message"]
    assert Document.from_dict(candidate).to_json() == saved
    assert original == document().to_dict()


def test_behind_plane_cannot_be_rescued_by_large_offset():
    replay = regenerate(document(direction=-1, offset=100), OCPKernel())
    assert not replay.ok
    assert "not ahead" in replay.result["features"][-1]["error"]["message"]


def test_native_nonplanar_and_ambiguous_faces_are_not_promoted():
    kernel = OCPKernel()
    base = kernel.extrude(kernel.circle(3), 10)
    kernel.topology(base, "base", "extrude", {})
    profile = kernel.circle(1)
    with pytest.raises(KernelError, match="planar"):
        kernel.extrude_to_face(profile, base, "base/face/side.circle", 1)
    operation = kernel._operations[id(base)]
    face = next(pair for pair in operation.faces if pair[1]["id"] == "base/face/cap.end")
    operation.faces.append(face)
    with pytest.raises(KernelError, match="ambiguous"):
        kernel.extrude_to_face(profile, base, "base/face/cap.end", 1)


def test_real_split_of_named_end_face_fails_closed():
    kernel = OCPKernel()
    base = kernel.extrude(kernel.rectangle(10, 10), 10)
    kernel.topology(base, "base", "extrude", {})
    cutter = kernel.extrude(kernel.rectangle(2, 12, x=4, y=-1, z=5), 6)
    kernel.topology(cutter, "slot", "extrude", {})
    split = kernel.cut(base, cutter)
    topology = kernel.topology(split, "split", "cut", {})
    assert any(face["provenance"]["semantic_status"] == "split" for face in topology)
    with pytest.raises(KernelError, match="missing, split, or ambiguous"):
        kernel.extrude_to_face(kernel.circle(1, z=20), split, "base/face/cap.end", -1)


def test_rotated_profile_and_target_follow_native_plane_not_world_z():
    kernel = OCPKernel()
    base = kernel.extrude(kernel.rectangle(10, 10), 8)
    kernel.topology(base, "base", "extrude", {})
    profile = kernel.face_circle(base, "base/face/side.x_min", 1)
    tool = kernel.extrude_to_face(profile, base, "base/face/side.x_max", -1, -2)
    assert kernel.inspect(tool)["volume"] == pytest.approx(8 * math.pi)
    bounds = _shape_bounds(tool)
    assert bounds[0] == pytest.approx(0) and bounds[3] == pytest.approx(8)


@pytest.mark.parametrize("direction", [True, 0, 2, "1", "direction"])
def test_direction_is_explicit_literal(direction):
    data = document().to_dict()
    data["features"][-1]["params"]["direction"] = direction
    with pytest.raises(CADException):
        Document.from_dict(data)


def test_target_must_be_earlier_and_legacy_roundtrip_is_unchanged():
    data = document().to_dict()
    data["features"].insert(1, data["features"].pop())
    with pytest.raises(CADException, match="earlier"):
        Document.from_dict(data)
    data = document().to_dict()
    data["features"].pop()
    data["active_feature"] = "stop"
    old = Document.from_dict(data).to_json()
    assert Document.from_json(old).to_json() == old
    assert all("end_face" not in f for f in Document.from_json(old).to_dict()["features"])


@pytest.mark.parametrize(
    "operation,plane,direction,expected", [("union", 15, 1, 1020), ("cut", 5, -1, 980)]
)
def test_linked_add_remove_edits_independent_target_and_offset_formula(
    operation, plane, direction, expected
):
    doc = Document(
        "linked",
        "Linked",
        {"stop_z": plane, "gap": 0, "old_depth": 2},
        (
            Feature("p", "sketch_rectangle", "Base profile", {"width": 10, "height": 10}),
            Feature("base", "extrude", "Base", {"length": 10}, {"profile": "p"}),
            Feature(
                "target_p",
                "sketch_rectangle",
                "Target profile",
                {"width": 3, "height": 3, "x": 50, "z": "stop_z-1"},
            ),
            Feature(
                "target", "extrude", "Independent stop", {"length": 1}, {"profile": "target_p"}
            ),
            Feature(
                "q",
                "sketch_rectangle",
                "Profile",
                {"width": 2, "height": 2, "x": 4, "y": 4, "z": 10},
            ),
        ),
        "base",
    ).to_dict()
    tool = Feature(
        "tool",
        "extrude_to_face",
        "Stop",
        {"direction": direction, "offset": "gap"},
        {"profile": "q", "target": "target"},
        end_face="target/face/cap.end",
    ).to_dict()
    boolean = Feature("result", operation, "Result", {}, {"base": "base", "tool": "tool"}).to_dict()
    candidate = build(doc, tool, boolean)
    assert candidate["parameters"] == doc["parameters"]
    replay = regenerate(Document.from_dict(candidate), OCPKernel(), result_version=2)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(expected)
    edited = linked.edit_linked_extrusion(
        candidate,
        candidate,
        "result",
        tool_id="tool",
        length="old_depth",
        profile="q",
        offset="gap+1",
    )
    restored = Document.from_json(Document.from_dict(edited).to_json())
    assert restored.features[-2].params["offset"] == "gap+1"
    assert restored.features[-2].inputs == {"profile": "q", "target": "target"}
    again = regenerate(restored, OCPKernel())
    assert again.ok, again.result
    assert again.result["features"][-1]["stats"]["volume"] == pytest.approx(
        expected + (4 if operation == "union" else -4)
    )
    assert edited["parameters"] == candidate["parameters"] == doc["parameters"]
    blind = linked.edit_linked_extrusion(
        edited,
        edited,
        "result",
        tool_id="tool",
        length="old_depth",
        profile="q",
        end_condition="BLIND",
    )
    assert "end_face" not in blind["features"][-2]
    assert blind["features"][-2]["params"] == {"length": "old_depth"}
    assert blind["features"][-2]["inputs"] == {"profile": "q"}


def test_assembly_requires_complete_end_face_source_evidence():
    from mechanical_cad.assembly_model import AssemblyDocument
    from mechanical_cad.assembly_service import run_assembly_action

    capture = importlib.import_module(PACKAGE + ".assembly_edit").new_from_part
    assembly = AssemblyDocument.from_dict(capture(document().to_dict()))
    for version in (1, 2):
        result = run_assembly_action(assembly, result_version=version)
        assert not result["ok"]
        assert result["error"]["code"] == "unsupported_result_version"
    result = run_assembly_action(assembly, result_version=3)
    assert result["ok"], result["error"]
    assert (
        result["result"]["canonical_assembly"]["part_sources"][0]["document"]["features"][-1][
            "end_face"
        ]
        == "stop/face/cap.end"
    )
