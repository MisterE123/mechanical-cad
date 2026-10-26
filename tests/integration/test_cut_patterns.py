"""Everyday repeated holes need no disconnected intermediate Part feature."""

import math

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature


def hole_pattern_document(kind="linear_cut_pattern", count=3):
    circular = kind == "circular_cut_pattern"
    return Document(
        "holes",
        "Repeated holes",
        {"thickness": 5},
        (
            Feature(
                "plate",
                "sketch_rectangle",
                "Plate",
                {"width": 60, "height": 60, "x": -30, "y": -30},
            ),
            Feature("base", "extrude", "Base", {"length": "thickness"}, {"profile": "plate"}),
            Feature(
                "hole",
                "sketch_circle",
                "Tool profile",
                {"radius": 2, "x": 15 if circular else -15, "y": 0},
            ),
            Feature("tool", "extrude", "Tool", {"length": 20}, {"profile": "hole"}),
            Feature(
                "holes",
                kind,
                "Repeated holes",
                {"count": count, **({"angle": 360} if circular else {"dx": 15})},
                {"base": "base", "tool": "tool"},
            ),
        ),
        "holes",
        schema_version=2,
    )


@pytest.mark.parametrize("kind,count", [("linear_cut_pattern", 3), ("circular_cut_pattern", 6)])
def test_repeated_separated_tools_cut_one_manufacturable_solid(kind, count):
    document = Document.from_json(hole_pattern_document(kind, count).to_json())
    for thickness in (5, 8):
        document = document.with_parameter("thickness", thickness)
        kernel = OCPKernel()
        replay = regenerate(document, kernel, result_version=2)
        assert replay.ok, replay.result
        row = replay.result["features"][-1]
        assert row["stats"]["solids"] == 1
        assert row["stats"]["volume"] == pytest.approx(
            3600 * thickness - count * math.pi * 4 * thickness
        )
        stable = [f for f in row["topology"] if f["provenance"]["semantic_status"] == "stable"]
        assert len(stable) == 6 + count
        assert {f["id"] for f in stable if f["feature_id"] == "base"} == {
            f["id"] for f in replay.result["features"][1]["topology"]
        }
        assert all(f["provenance"]["operation"] == kind for f in stable)
        assert kernel.manufacturing_check(replay.shapes["holes"])["mesh"]["watertight"]
        # A real downstream face sketch still resolves the edited perforated top.
        face = kernel.face_circle(replay.shapes["holes"], "base/face/cap.end", 1, x=0, y=10)
        assert face is not None


def test_noop_placements_allowed_but_total_noop_rejected():
    data = hole_pattern_document().to_dict()
    data["features"][-1]["params"]["dx"] = 100
    replay = regenerate(Document.from_dict(data), OCPKernel(), result_version=2)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
        18000 - math.pi * 4 * 5
    )
    data["features"][2]["params"]["x"] = 100
    replay = regenerate(Document.from_dict(data), OCPKernel(), result_version=2)
    assert not replay.ok
    assert "measurable material" in replay.result["features"][-1]["error"]["message"]
