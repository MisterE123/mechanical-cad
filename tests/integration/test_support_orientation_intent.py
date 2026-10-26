"""MCAD-TNP-SUPPORT-002: saved minimal twist crosses the old world-axis threshold."""

import copy
import importlib
import math
import sys
import types
from pathlib import Path

import pytest
from test_associative_sketch_support import attached_document
from test_split_support_intent import rows, tilted_document

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document
from mechanical_cad.sidecar import process_request
from mechanical_cad.support_intent import capture_orientation, reset_frame_intent
from mechanical_cad.support_plane import rotate


def oriented_document(angle=64, *, split=True, orientation=True):
    data = tilted_document(split=True)
    profile = next(row for row in data["features"] if row["id"] == "slot_profile")
    profile["params"].update(x=4, height=10)
    for row in data["features"]:
        if row["id"] in {"tilted_block", "tilted_tool"}:
            row["params"] = {"ry": angle}
    # Asymmetric rectangle, not a rotation-invariant circle; add a nonzero local offset.
    sketch = attached_document(lines=True).to_dict()["features"][2]["sketch"]
    for point in sketch["points"]:
        point["u"] *= 1.5
    for constraint in sketch["constraints"]:
        constraint["target"][0] *= 1.5
    sketch["plane"]["origin"] = [2, 1, 0]
    data["features"][-2]["sketch"] = sketch
    # Capture a real asymmetric notch's exact retained top face, whose centroid
    # has a nonzero offset relative to its original stable source workplane.
    upstream = copy.deepcopy(data)
    upstream["features"] = upstream["features"][:-2]
    upstream["active_feature"] = "slotted"
    initial = regenerate(Document.from_dict(upstream), OCPKernel(), result_version=3)
    assert initial.ok, initial.result
    baseline = next(
        f["signature"]
        for f in rows(initial)["tilted_block"]["topology"]
        if f["id"] == "block/face/cap.end"
    )
    chosen = next(
        f["signature"]
        for f in rows(initial)["slotted"]["topology"]
        if f["id"] == "block/face/cap.end"
    )
    assert chosen["centroid"] != pytest.approx(baseline["centroid"])
    profile["params"]["height"] = 22 if split else 10
    intent = {
        "version": 1,
        "policy": "preserve_plane",
        "signature": chosen,
        "source_signature": baseline,
    }
    if orientation:
        intent["orientation"] = capture_orientation(intent)
    data["features"][-2]["support_intent"] = intent
    return data


def set_angle(data, angle):
    for row in data["features"]:
        if row["id"] in {"tilted_block", "tilted_tool"}:
            row["params"]["ry"] = angle


@pytest.mark.parametrize("split", [False, True])
def test_threshold_crossing_keeps_saved_tangent_and_asymmetric_geometry(split):
    data = oriented_document(split=split)
    saved = data["features"][-2]["support_intent"]
    delta = [
        saved["signature"]["centroid"][i] - saved["source_signature"]["centroid"][i]
        for i in range(3)
    ]
    old_u = saved["orientation"]["tangent"]
    offset_u = sum(delta[i] * old_u[i] for i in range(3))
    offset_v = delta[1]
    for angle in (64, 64.3, 65, 90, 110, 64):
        set_angle(data, angle)
        canonical = Document.from_json(Document.from_dict(data).to_json())
        replay = regenerate(canonical, OCPKernel(), result_version=3)
        assert replay.ok, replay.result
        result = rows(replay)
        plane = result["attached"]["support_plane"]
        theta = math.radians(angle)
        u = [math.cos(theta), 0, -math.sin(theta)]
        v = [0, 1, 0]
        normal = [math.sin(theta), 0, math.cos(theta)]
        assert rotate(plane["quaternion"], (1, 0, 0)) == pytest.approx(u, abs=1e-8)
        assert rotate(plane["quaternion"], (0, 1, 0)) == pytest.approx(v, abs=1e-8)
        assert rotate(plane["quaternion"], (0, 0, 1)) == pytest.approx(normal, abs=1e-8)
        baseline = next(
            f["signature"]
            for f in result["tilted_block"]["topology"]
            if f["id"] == "block/face/cap.end"
        )
        expected_origin = [
            baseline["centroid"][i] + (2 + offset_u) * u[i] + (1 + offset_v) * v[i]
            for i in range(3)
        ]
        assert plane["origin"] == pytest.approx(expected_origin)
        assert result["boss"]["stats"]["volume"] == pytest.approx(48)
        assert result["attached"]["sketch"]["solved"]["plane"] == plane


def test_omitted_orientation_retains_existing_serialized_world_axis_behavior():
    data = oriented_document(orientation=False)
    set_angle(data, 65)
    before = Document.from_dict(data).to_json()
    replay = regenerate(Document.from_json(before), OCPKernel(), result_version=3)
    assert replay.ok
    assert rotate(
        rows(replay)["attached"]["support_plane"]["quaternion"], (1, 0, 0)
    ) == pytest.approx([0, 1, 0])
    assert Document.from_json(before).to_json() == before
    assert "orientation" not in data["features"][-2]["support_intent"]


@pytest.mark.parametrize("angle", [244, 243.999])
def test_antiparallel_rejects_without_silent_axis_choice_and_reset_corrects(angle):
    data = oriented_document()
    set_angle(data, angle)
    document = Document.from_dict(data)
    failed = regenerate(document, OCPKernel(), result_version=3)
    assert rows(failed)["attached"]["status"] == "failed"
    assert "antiparallel" in rows(failed)["attached"]["error"]["message"]
    assert rows(failed)["boss"]["status"] == "blocked"
    old = copy.deepcopy(data["features"][-2]["support_intent"])
    new = reset_frame_intent(
        "block/face/cap.end",
        old,
        rows(failed)["slotted"]["topology"],
        rows(failed)["tilted_block"]["topology"],
    )
    data["features"][-2]["support_intent"] = new
    fixed = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    assert fixed.ok, fixed.result
    assert old == document.to_dict()["features"][-2]["support_intent"]
    assert new != old
    # Restoring the prior canonical intent restores the explicit unresolved condition.
    assert not regenerate(document, OCPKernel(), result_version=3).ok


def test_exact_non_cut_face_uses_minimal_twist_without_fabricating_split_lineage():
    data = oriented_document()
    data["features"][-2]["inputs"]["support"] = "tilted_block"
    set_angle(data, 65)
    replay = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert rotate(
        rows(replay)["attached"]["support_plane"]["quaternion"], (1, 0, 0)
    ) == pytest.approx([math.cos(math.radians(65)), 0, -math.sin(math.radians(65))])


def test_client_validates_transported_plane_and_rejects_world_axis_substitution():
    package = types.ModuleType("mcad_orientation_contracts")
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    sys.modules[package.__name__] = package
    operations = importlib.import_module(package.__name__ + ".operation_contracts")
    data = oriented_document()
    set_angle(data, 65)
    for action in ("replay", "solve_sketch"):
        request = {"protocol_version": 1, "action": action, "document": data, "result_version": 3}
        if action == "solve_sketch":
            request["feature_id"] = "attached"
        response = process_request(request)
        assert response["ok"], response
        operations.validate_response(request, response)
        forged = copy.deepcopy(response)
        plane = (
            next(f for f in forged["result"]["features"] if f["id"] == "attached")["support_plane"]
            if action == "replay"
            else forged["result"]["support_context"]["plane"]
        )
        plane["quaternion"] = [1, 0, 0, 0]
        with pytest.raises(ValueError):
            operations.validate_response(request, forged)


def test_saved_tangent_is_immutable_and_never_promoted_into_native_face_metadata():
    document = Document.from_dict(oriented_document())
    intent = document.features[-2].support_intent
    with pytest.raises(TypeError):
        intent["orientation"]["tangent"][0] = 0
    detached = document.to_dict()
    detached["features"][-2]["support_intent"]["orientation"]["tangent"][0] = 0
    assert document.to_dict()["features"][-2]["support_intent"]["orientation"]["tangent"][0] != 0
    replay = regenerate(document, OCPKernel(), result_version=3)
    assert replay.ok
    assert all(
        "tangent" not in face["signature"]
        for row in replay.result["features"]
        for face in row["topology"]
    )
