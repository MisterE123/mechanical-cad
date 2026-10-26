"""Exact ordinary Cut tool ancestry, including reversed faces and closed failures."""

import copy
import importlib
import math
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("OCP")
from OCP.TopAbs import TopAbs_FACE

from mechanical_cad.kernel_ocp import KernelError, OCPKernel
from mechanical_cad.model import load_document
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_cut_lineage_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
validator = importlib.import_module(PACKAGE + ".part_result_bridge")


def build(radius=2, height=12, z=-1):
    kernel = OCPKernel(cut_tool_lineage=True)
    base = kernel.extrude(kernel.rectangle(20, 20), 10)
    kernel.topology(base, "base", "", {})
    tool = kernel.extrude(kernel.circle(radius, 10, 10, z), height)
    kernel.topology(tool, "tool", "", {})
    result = kernel.cut(base, tool)
    topology = kernel.topology(result, "cut", "", {})
    return kernel, tool, result, topology


@pytest.mark.parametrize("radius,height,z", [(2, 12, -1), (3, 14, -2), (2, 5, 5), (2, 10, 0)])
def test_native_tool_face_history_and_orientation_reversal(radius, height, z):
    kernel, tool, result, topology = build(radius, height, z)
    source = next(
        face for face, item in kernel._operations[id(tool)].faces if item["role"] == "side.circle"
    )
    operation = kernel._operations[id(result)]
    outputs = [face for face, item in operation.faces if item["id"] == "tool/face/side.circle"]
    assert len(outputs) == 1
    output = outputs[0]
    assert output.Orientation() != source.Orientation()
    modified = list(operation.builder.Modified(source))
    generated_faces = [
        face for face in operation.builder.Generated(source) if face.ShapeType() == TopAbs_FACE
    ]
    assert generated_faces == []
    assert len(modified) == (1 if z < 0 else 0)
    assert any(output.IsSame(face) for face in modified) if z < 0 else output.IsSame(source)
    wall = next(item for item in topology if item["id"] == "tool/face/side.circle")
    assert wall["provenance"]["semantic_status"] == "stable"
    assert wall["provenance"]["relation"] == ("tool_modified" if z < 0 else "tool_unchanged")
    assert kernel.inspect(result)["volume"] == pytest.approx(
        4000 - math.pi * radius**2 * min(height, 10)
    )


@pytest.mark.parametrize("kind,param", [("fillet", "radius"), ("chamfer", "distance")])
def test_picked_hole_edge_replays_and_validates_across_radius_height_edits(kind, param):
    for radius, height in [(3, 10), (4, 14)]:
        document = load_document(ROOT / "examples/drilled_plate.mcad.json").to_dict()
        document["parameters"].update(hole_radius=radius, height=height)
        document["features"].append(
            {
                "id": "blend",
                "kind": kind,
                "params": {param: 0.5},
                "inputs": {"base": "body"},
                "edge_faces": ["pad/face/cap.end", "hole_tool/face/side.circle"],
            }
        )
        document["active_feature"] = "blend"
        request = {"protocol_version": 1, "result_version": 2, "document": document}
        response = process_request(request)
        assert response["ok"], response
        validator.validate_response(request, response)
        result = response["result"]["features"][-1]
        assert result["stats"]["valid"] and result["stats"]["solids"] == 1
        assert 0 < 40 * 30 * height - math.pi * radius**2 * height - result["stats"]["volume"] < 30
        assert any(
            face["id"] == "hole_tool/face/side.circle"
            and face["provenance"]["semantic_status"] == "stable"
            for face in result["topology"]
        )


def test_multi_image_tool_wall_is_snapshot_only_and_cannot_be_blended():
    kernel = OCPKernel(cut_tool_lineage=True)
    base = kernel.extrude(kernel.rectangle(20, 20), 20)
    kernel.topology(base, "base", "", {})
    slot = kernel.extrude(kernel.rectangle(15, 22, 0, -1, 8), 4)
    kernel.topology(slot, "slot", "", {})
    base = kernel.cut(base, slot)
    kernel.topology(base, "slotted", "", {})
    tool = kernel.extrude(kernel.circle(2, 5, 10, -1), 22)
    kernel.topology(tool, "tool", "", {})
    cut = kernel.cut(base, tool)
    faces = kernel.topology(cut, "cut", "", {})
    walls = [item for item in faces if item["role"] == "cut.wall"]
    assert len(walls) == 2
    assert all(item["id"].startswith("snapshot:") for item in walls)
    with pytest.raises(KernelError, match="missing, split, or ambiguous"):
        kernel.fillet(cut, 0.2, edge_faces=("base/face/cap.end", "tool/face/side.circle"))


def test_patterned_cut_does_not_promote_tool_face():
    kernel, tool, _, _ = build()
    base = kernel.extrude(kernel.rectangle(40, 20), 10)
    kernel.topology(base, "base", "", {})
    result = kernel.linear_cut_pattern(base, tool, 2, dx=10)
    faces = kernel.topology(result, "pattern", "", {})
    assert not any(item["feature_id"] == "tool" for item in faces)
    assert any(item["provenance"]["semantic_status"] != "stable" for item in faces)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda wall: wall["provenance"].update(image_count=2),
        lambda wall: wall["provenance"].update(source_count=2),
        lambda wall: wall["provenance"].update(source_id="pad/face/cap.end"),
        lambda wall: wall["provenance"].update(relation="modified", evolution="modified"),
        lambda wall: wall["provenance"].update(
            relation="tool_generated", evolution="tool_generated"
        ),
    ],
)
def test_client_rejects_false_tool_ancestry(mutation):
    request = {
        "protocol_version": 1,
        "result_version": 2,
        "document": load_document(ROOT / "examples/drilled_plate.mcad.json").to_dict(),
    }
    response = process_request(request)
    validator.validate_response(request, response)
    bad = copy.deepcopy(response)
    wall = next(
        face
        for face in bad["result"]["features"][-1]["topology"]
        if face["feature_id"] == "hole_tool"
    )
    mutation(wall)
    with pytest.raises(ValueError):
        validator.validate_response(request, bad)


def test_blind_cut_planar_tool_cap_uses_current_reversed_normal():
    for radius, bottom in [(2, 5), (3, 4)]:
        kernel, tool, cut, _ = build(radius, 10 - bottom, bottom)
        before = kernel.support_face_signature(tool, "tool/face/cap.start")
        after = kernel.support_face_signature(cut, "tool/face/cap.start")
        assert after["normal"] == pytest.approx([-value for value in before["normal"]])
        assert after["centroid"][2] == pytest.approx(bottom)
        profile = kernel.face_circle(cut, "tool/face/cap.start", 0.5)
        assert kernel.inspect(profile)["area"] == pytest.approx(math.pi * 0.5**2)


def test_transformed_alias_tool_cannot_claim_base_identity():
    kernel = OCPKernel(cut_tool_lineage=True)
    base = kernel.extrude(kernel.rectangle(20, 20), 10)
    kernel.topology(base, "base", "", {})
    tool = kernel.transform(base, x=10)
    kernel.topology(tool, "move", "", {})
    cut = kernel.cut(base, tool)
    faces = kernel.topology(cut, "cut", "", {})
    walls = [face for face in faces if face["role"] == "cut.wall"]
    assert len(walls) == 1
    assert walls[0]["provenance"]["semantic_status"] == "generated"
    assert walls[0]["id"].startswith("snapshot:")
    assert not any(
        face["provenance"]["relation"].startswith("tool_")
        and face["provenance"]["semantic_status"] == "stable"
        for face in faces
    )


def test_reused_kernel_resets_legacy_topology_policy_and_current_ui_selects_v2():
    from mechanical_cad.engine import regenerate

    contracts = importlib.import_module(PACKAGE + ".operation_contracts")
    document = load_document(ROOT / "examples/drilled_plate.mcad.json")
    assert contracts.result_version_for(document.to_dict()) == 2
    kernel = OCPKernel()
    for version in (1, 2, 1):
        replay = regenerate(document, kernel, result_version=version)
        assert replay.ok
        faces = replay.result["features"][-1]["topology"]
        if version == 1:
            wall = next(face for face in faces if face["role"] == "cut.wall")
            assert wall["id"] == "snapshot:body:face:6"
            assert wall["provenance"]["semantic_status"] == "generated"
        else:
            wall = next(face for face in faces if face["feature_id"] == "hole_tool")
            assert wall["id"] == "hole_tool/face/side.circle"
            assert wall["provenance"]["semantic_status"] == "stable"


def test_merged_base_ancestry_cannot_be_resurrected_by_tool_or_forged_client():
    document = {
        "schema_version": 1,
        "id": "d",
        "name": "Alias guard",
        "units": "mm",
        "parameters": {},
        "active_feature": "cut",
        "features": [
            {"id": "p", "kind": "sketch_rectangle", "params": {"width": 10, "height": 10}},
            {"id": "a", "kind": "extrude", "params": {"length": 10}, "inputs": {"profile": "p"}},
            {"id": "b", "kind": "transform", "params": {"x": 5}, "inputs": {"base": "a"}},
            {"id": "union", "kind": "union", "inputs": {"base": "a", "tool": "b"}},
            {"id": "cut", "kind": "cut", "inputs": {"base": "union", "tool": "a"}},
        ],
    }
    request = {"protocol_version": 1, "result_version": 2, "document": document}
    response = process_request(request)
    assert response["ok"], response
    validator.validate_response(request, response)
    output = response["result"]["features"][-1]
    assert not any(face["provenance"]["semantic_status"] == "stable" for face in output["topology"])
    wall = next(face for face in output["topology"] if face["role"] == "cut.wall")
    old_id = wall["id"]
    source_id = wall["provenance"]["sources"][0]
    feature_id, role = source_id.split("/face/")
    wall.update(id=source_id, feature_id=feature_id, role=role)
    wall["provenance"] = {
        "semantic_status": "stable",
        "kernel": "OCCT",
        "operation": "cut",
        "operation_id": "cut",
        "relation": "tool_unchanged",
        "evolution": "tool_unchanged",
        "source_id": source_id,
        "modifying_feature_id": "cut",
        "source_count": 1,
        "image_count": 1,
    }
    output["mesh"]["triangle_face_ids"] = [
        source_id if identifier == old_id else identifier
        for identifier in output["mesh"]["triangle_face_ids"]
    ]
    with pytest.raises(ValueError, match="exact and unambiguous"):
        validator.validate_response(request, response)
