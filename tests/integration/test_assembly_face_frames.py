"""Associative datums resolve fresh exact faces, never display triangles."""

from dataclasses import replace

import pytest
from test_assembly_service import assembly

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import Frame, MateFrame
from mechanical_cad.assembly_service import preflight_source_update, run_assembly_action
from mechanical_cad.model import Document

pytestmark = pytest.mark.kernel


def face_assembly(face="pad/face/cap.end"):
    value = assembly()
    part = replace(
        value.parts[0],
        mate_frames=(MateFrame("origin"), MateFrame("offset", Frame((2, 0, 3)), support_face=face)),
    )
    return replace(value, parts=(part,))


def test_face_frame_follows_explicit_source_update():
    value = face_assembly()
    assert evaluate(value).status == "blocked"
    first = run_assembly_action(value, result_version=3)
    assert first["ok"], first["error"]
    placement = first["result"]["parts"][0]["resolved_mate_frames"]["offset"]
    assert placement["xyz_mm"] == pytest.approx([7, 5, 13])
    document = value.part_sources[0].document.to_dict()
    document["features"][1]["params"]["length"] = 20
    updated = preflight_source_update(
        value, value.part_sources[0].id, Document.from_dict(document), result_version=3
    )
    assert updated["ok"], updated["error"]
    assert updated["result"]["parts"][0]["resolved_mate_frames"]["offset"][
        "xyz_mm"
    ] == pytest.approx([7, 5, 23])
    before = first["report"]["base_pose"]["transforms"]["b"]["xyz_mm"]
    after = updated["report"]["base_pose"]["transforms"]["b"]["xyz_mm"]
    assert after[2] - before[2] == pytest.approx(10)
    assert value.parts[0].mate_frames[1].placement.xyz_mm == (2, 0, 3)
    assert (
        updated["update"]["candidate"]["parts"][0]["mate_frames"][1]["support_face"]
        == "pad/face/cap.end"
    )


def test_missing_face_fails_with_repair_and_no_current_pose():
    result = run_assembly_action(face_assembly("pad/face/deleted"), result_version=3)
    assert not result["ok"]
    assert result["error"]["code"] == "unresolved_mate_face"
    assert "repair" in result["error"]["message"].lower()
    assert not result["report"]["poses"]


def test_literal_serialization_stays_unchanged_and_face_requires_v3():
    assert MateFrame("origin").to_dict() == {
        "id": "origin",
        "name": "origin",
        "placement": Frame().to_dict(),
    }
    assert (
        run_assembly_action(face_assembly(), result_version=2)["error"]["code"]
        == "unsupported_result_version"
    )


def test_nonplanar_support_is_rejected_without_literal_fallback():
    from mechanical_cad.assembly_model import PartSource
    from mechanical_cad.engine import regenerate
    from mechanical_cad.kernel_ocp import OCPKernel

    value = assembly()
    raw = value.part_sources[0].document.to_dict()
    raw["features"][0]["kind"] = "sketch_circle"
    raw["features"][0]["params"] = {"radius": 5, "x": 0, "y": 0, "z": 0}
    source = PartSource.from_document(Document.from_dict(raw))
    replay = regenerate(source.document, OCPKernel(), result_version=3)
    side = next(
        face["id"]
        for face in replay.result["features"][-1]["topology"]
        if face["signature"]["surface"] == "cylinder"
    )
    part = replace(
        value.parts[0],
        source_digest=source.source_digest,
        mate_frames=(MateFrame("origin"), MateFrame("offset", support_face=side)),
    )
    value = replace(value, part_sources=(source,), parts=(part,))
    result = run_assembly_action(value, result_version=3)
    assert not result["ok"]
    assert result["error"]["code"] == "unresolved_mate_face"
    assert "planar" in result["error"]["message"].lower()
