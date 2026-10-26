"""Exact single-solid reflection, handedness, strict lineage and transport."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import KernelError, OCPKernel, _shape_bounds
from mechanical_cad.model import Document, Feature
from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_mirror_contracts")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
bridge = importlib.import_module(package.__name__ + ".operation_contracts")
edit = importlib.import_module(package.__name__ + ".solid_feature_edit")


def document(**plane):
    return Document(
        "part",
        "Mirrored part",
        {"plane_height": 1},
        (
            Feature(
                "p",
                "sketch_rectangle",
                "Profile",
                {"width": 10, "height": 7, "x": 2, "y": 3, "z": 4},
            ),
            Feature("pad", "extrude", "Pad", {"length": 5}, {"profile": "p"}),
            Feature("mirror", "mirror", "Mirror Result", plane, {"base": "pad"}),
        ),
        "mirror",
    )


@pytest.mark.parametrize(
    "normal,origin,bounds",
    [
        ((0, 0, 1), (0, 0, 0), (2, 3, -9, 12, 10, -4)),
        ((0, 1, 0), (0, 1, 0), (2, -8, 4, 12, -1, 9)),
        ((1, 0, 0), (1, 0, 0), (-10, 3, 4, 0, 10, 9)),
        ((1, 1, 0), (0, 0, 0), (-10, -12, 4, -3, -2, 9)),
        ((0, 0, -5), (0, 0, 2), (2, 3, -5, 12, 10, 0)),
    ],
)
def test_exact_plane_reflection_is_single_solid_with_outward_normals(normal, origin, bounds):
    kernel = OCPKernel()
    base = kernel.extrude(kernel.rectangle(10, 7, x=2, y=3, z=4), 5)
    kernel.topology(base, "pad", "extrude", {})
    reflected = kernel.mirror(
        base,
        **dict(zip(("axis_x", "axis_y", "axis_z", "x", "y", "z"), (*normal, *origin), strict=True)),
    )
    assert _shape_bounds(reflected) == pytest.approx(bounds)
    assert kernel.inspect(reflected)["volume"] == pytest.approx(350)
    assert kernel.inspect(reflected)["valid"] and kernel.inspect(reflected)["solids"] == 1
    topology = kernel.topology(reflected, "mirror", "mirror", {})
    center = [(bounds[i] + bounds[i + 3]) / 2 for i in range(3)]
    for item in topology:
        sig = item["signature"]
        assert sum((sig["centroid"][i] - center[i]) * sig["normal"][i] for i in range(3)) > 0
        assert item["provenance"]["semantic_status"] == "stable"
        assert item["provenance"]["source_count"] == item["provenance"]["image_count"] == 1
    restored = kernel.mirror(
        reflected,
        **dict(zip(("axis_x", "axis_y", "axis_z", "x", "y", "z"), (*normal, *origin), strict=True)),
    )
    assert _shape_bounds(restored) == pytest.approx(_shape_bounds(base))


@pytest.mark.parametrize("version", [2, 3])
def test_sidecar_replay_edit_and_forged_lineage(version):
    doc = Document.from_json(document(z="plane_height").to_json()).to_dict()
    req = {"protocol_version": 1, "result_version": version, "document": doc}
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)
    mirror = response["result"]["features"][-1]
    assert mirror["stats"]["volume"] == pytest.approx(350)
    assert {face["id"] for face in mirror["topology"]} == {
        face["id"] for face in response["result"]["features"][-2]["topology"]
    }
    forged = copy.deepcopy(response)
    forged["result"]["features"][-1]["topology"][0]["provenance"]["source_id"] = (
        "wrong/face/cap.end"
    )
    with pytest.raises(ValueError):
        bridge.validate_response(req, forged)
    edited = edit.edit_feature(
        doc,
        "mirror",
        label="Offset mirror",
        params={**doc["features"][-1]["params"], "z": "3 mm"},
        inputs={"base": "pad"},
    )
    assert doc["features"][-1]["params"]["z"] == "plane_height"
    replay = regenerate(Document.from_dict(edited), OCPKernel())
    assert replay.ok, replay.result
    vertices = replay.result["features"][-1]["mesh"]["vertices"]
    assert min(v[2] for v in vertices) == pytest.approx(-3)
    assert max(v[2] for v in vertices) == pytest.approx(2)


def test_zero_normal_rejected_and_downstream_blocked():
    doc = document(axis_x=0, axis_y=0, axis_z=0).to_dict()
    doc["features"].append(
        {"id": "later", "kind": "transform", "params": {}, "inputs": {"base": "mirror"}}
    )
    doc["active_feature"] = "later"
    result = regenerate(Document.from_dict(doc), OCPKernel())
    assert not result.ok
    assert [f["status"] for f in result.result["features"]][-2:] == ["failed", "blocked"]
    kernel = OCPKernel()
    with pytest.raises(KernelError, match="nonzero"):
        kernel.mirror(kernel.extrude(kernel.rectangle(1, 1), 1), axis_z=0)


def test_reflected_face_support_extrudes_outward_and_survives_plane_edit():
    for plane_z in (0, 2):
        doc = document(z=plane_z).to_dict()
        doc["features"] += [
            {
                "id": "face_profile",
                "kind": "sketch_face_rectangle",
                "params": {"width": 1, "height": 1},
                "inputs": {"support": "mirror"},
                "support_face": "pad/face/cap.end",
            },
            {
                "id": "boss",
                "kind": "extrude",
                "params": {"length": 2},
                "inputs": {"profile": "face_profile"},
            },
        ]
        doc["active_feature"] = "boss"
        req = {"protocol_version": 1, "result_version": 3, "document": doc}
        response = process_request(req)
        assert response["ok"], response
        bridge.validate_response(req, response)
        vertices = response["result"]["features"][-1]["mesh"]["vertices"]
        assert min(v[2] for v in vertices) == pytest.approx(2 * plane_z - 11)
        assert max(v[2] for v in vertices) == pytest.approx(2 * plane_z - 9)


def test_mirror_does_not_promote_split_source_faces():
    kernel = OCPKernel()
    base = kernel.extrude(kernel.rectangle(20, 20), 10)
    kernel.topology(base, "base", "extrude", {})
    slot = kernel.extrude(kernel.rectangle(4, 22, x=8, y=-1, z=5), 6)
    kernel.topology(slot, "slot", "extrude", {})
    cut = kernel.cut(base, slot)
    original = kernel.topology(cut, "cut", "cut", {})
    split = [f for f in original if f["role"] == "cap.end" and f["feature_id"] == "base"]
    assert len(split) == 2 and all(f["provenance"]["semantic_status"] == "split" for f in split)
    reflected = kernel.mirror(cut)
    faces = kernel.topology(reflected, "mirror", "mirror", {})
    assert not any(f["id"] == "base/face/cap.end" for f in faces)
    with pytest.raises(KernelError, match="missing, split, or ambiguous"):
        kernel.supported_workplane(reflected, "base/face/cap.end")


def test_mirrored_step_stl_and_saved_replay(tmp_path):
    from mechanical_cad.actions import run_geometry_action

    saved = tmp_path / "mirror.mcad.json"
    saved.write_text(document(axis_x=1, axis_y=1, axis_z=0).to_json())
    restored = Document.from_json(saved.read_text())
    for action, extension in (
        ("check_geometry", None),
        ("export_step", "step"),
        ("export_stl", "stl"),
    ):
        target = tmp_path / ("mirror." + extension) if extension else None
        result = run_geometry_action(restored, action, destination=target, kernel=OCPKernel())
        assert result["ok"], result
        if target:
            assert target.stat().st_size > 100
    kernel = OCPKernel()
    shape = kernel.import_step(tmp_path / "mirror.step")
    assert kernel.inspect(shape)["volume"] == pytest.approx(350)
    assert _shape_bounds(shape) == pytest.approx((-10, -12, 4, -3, -2, 9))


def test_mirrored_part_assembly_capture():
    snapshots = importlib.import_module(package.__name__ + ".part_contracts_v3")
    assembly_edit = importlib.import_module(package.__name__ + ".assembly_edit")
    assembly = assembly_edit.new_from_part(snapshots._expected_document(document().to_dict()))
    req = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 3,
        "action": "assembly_replay",
        "assembly": assembly,
    }
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)


@pytest.mark.parametrize("version", [2, 3])
def test_picked_blend_after_mirror_follows_upstream_edits(version):
    for width, offset in ((10, 0), (14, 3)):
        doc = document(z=offset).to_dict()
        doc["features"][0]["params"]["width"] = width
        doc["features"].append(
            {
                "id": "blend",
                "kind": "fillet",
                "params": {"radius": 0.5},
                "inputs": {"base": "mirror"},
                "edge_faces": ["pad/face/cap.end", "pad/face/side.y_min"],
            }
        )
        doc["active_feature"] = "blend"
        request = {"protocol_version": 1, "result_version": version, "document": doc}
        response = process_request(request)
        assert response["ok"], response
        bridge.validate_response(request, response)
        result = response["result"]["features"][-1]
        assert result["stats"]["valid"] and result["stats"]["solids"] == 1
        assert 0 < width * 7 * 5 - result["stats"]["volume"] < 5
