"""User-facing examples retain their documented intent through saved edits."""

import math
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import load_document, save_document
from mechanical_cad.support_intent import resolve_support_signature

EXAMPLES = Path(__file__).resolve().parents[2] / "examples/topology_walkthroughs"


def saved_replay(document, tmp_path):
    path = tmp_path / "edited.mcad.json"
    save_document(document, path)
    restored = load_document(path)
    assert restored.to_json() == document.to_json()
    canonical = restored.to_json()
    replay = regenerate(restored, OCPKernel(), result_version=3)
    assert restored.to_json() == canonical
    return replay, {row["id"]: row for row in replay.result["features"]}


@pytest.mark.parametrize("width,slot_length", [(20, 22), (24, 22), (20, 10)])
def test_slotted_plate_saved_edits(width, slot_length, tmp_path):
    document = load_document(EXAMPLES / "source_relative_slotted_plate.mcad.json")
    document = document.with_parameter("plate_width", width).with_parameter(
        "slot_length", slot_length
    )
    replay, rows = saved_replay(document, tmp_path)
    assert replay.ok, replay.result
    assert all(row["status"] == "ok" for row in rows.values())
    expected = width * 200 - 2 * min(slot_length - 1, 20) * 3 + 8 * math.pi
    assert rows["finished_plate"]["stats"]["volume"] == pytest.approx(expected)
    assert rows["finished_plate"]["stats"]["valid"]
    assert rows["pad_sketch"]["support_plane"]["origin"] == pytest.approx([width / 2, 10, 10])
    sketch = document.features[5]
    _, decision = resolve_support_signature(
        sketch.support_face,
        sketch.support_intent,
        rows["slotted_plate"]["topology"],
        rows["plate"]["topology"],
    )
    assert decision["status"] == "assumed"
    assert decision["identity_status"] == ("split" if slot_length == 22 else "stable")
    if slot_length == 22:
        assert decision["descendant_count"] == 2


def test_slotted_plate_strict_reference_does_not_pick_a_fragment(tmp_path):
    document = load_document(EXAMPLES / "source_relative_slotted_plate.mcad.json")
    features = list(document.features)
    features[5] = replace(features[5], support_intent=None)
    replay, rows = saved_replay(replace(document, features=tuple(features)), tmp_path)
    assert not replay.ok
    assert rows["slotted_plate"]["status"] == "ok"
    assert rows["pad_sketch"]["status"] == "failed"
    assert rows["finished_plate"]["status"] == "blocked"


@pytest.mark.parametrize("width,wall", [(20, 1), (30, 2)])
def test_inner_wall_pad_saved_edits(width, wall, tmp_path):
    document = load_document(EXAMPLES / "shell_inner_wall_pad.mcad.json")
    document = document.with_parameter("box_width", width).with_parameter("wall_thickness", wall)
    replay, rows = saved_replay(document, tmp_path)
    assert replay.ok, replay.result
    assert all(row["status"] == "ok" for row in rows.values())
    shell_volume = width * 150 - (width - 2 * wall) * (15 - 2 * wall) * (10 - wall)
    assert rows["enclosure"]["stats"]["volume"] == pytest.approx(shell_volume)
    assert rows["finished_enclosure"]["stats"]["volume"] == pytest.approx(
        shell_volume + 12 * math.pi
    )
    assert rows["finished_enclosure"]["stats"]["valid"]
    assert rows["inner_pad_sketch"]["support_plane"]["origin"] == pytest.approx(
        [wall, 7.5, (10 + wall) / 2]
    )
    support = next(
        face
        for face in rows["enclosure"]["topology"]
        if face["id"] == document.features[3].support_face
    )
    assert support["signature"]["surface"] == "plane"
    assert support["provenance"]["source_id"] == "blank/face/side.x_min"
    assert support["provenance"]["semantic_status"] == "stable"


def test_removing_supported_inner_wall_requires_correction(tmp_path):
    document = load_document(EXAMPLES / "shell_inner_wall_pad.mcad.json")
    features = list(document.features)
    features[2] = replace(features[2], opening_faces=("blank/face/side.x_min",))
    replay, rows = saved_replay(replace(document, features=tuple(features)), tmp_path)
    assert not replay.ok
    assert rows["enclosure"]["status"] == "ok"
    assert rows["inner_pad_sketch"]["status"] == "failed"
    assert rows["finished_enclosure"]["status"] == "blocked"
