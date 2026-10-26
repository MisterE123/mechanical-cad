"""Through All is replayed design intent, never a persisted guessed depth."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature

PACKAGE = "through_all_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package
build = importlib.import_module(PACKAGE + ".extrusion_candidate").extrusion_candidate


def document(thickness=10, direction=-1, z="thickness"):
    return Document(
        "through",
        "Through All",
        {"thickness": thickness},
        (
            Feature("p", "sketch_rectangle", "Base profile", {"width": 10, "height": 10}),
            Feature("base", "extrude", "Base", {"length": "thickness"}, {"profile": "p"}),
            Feature("q", "sketch_circle", "Hole", {"radius": 1, "x": 5, "y": 5, "z": z}),
            Feature(
                "tool",
                "extrude_through",
                "Through All",
                {"direction": direction},
                {"profile": "q", "base": "base"},
            ),
            Feature("cut", "cut", "Remove", {}, {"base": "base", "tool": "tool"}),
        ),
        "cut",
    )


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize("thickness", [2, 10, 125])
def test_through_all_tracks_thickness_and_roundtrips(version, thickness):
    import math

    original = document().to_dict()
    original["parameters"]["thickness"] = thickness
    restored = Document.from_json(Document.from_dict(original).to_json())
    replay = regenerate(restored, OCPKernel(), result_version=version)
    assert replay.ok, replay.result
    stats = replay.result["features"][-1]["stats"]
    assert stats["valid"] and stats["solids"] == 1
    assert stats["volume"] == pytest.approx((100 - math.pi) * thickness)
    assert restored.features[-2].params == {"direction": -1}
    assert restored.features[-2].inputs == {"profile": "q", "base": "base"}
    assert replay.result["features"][-2]["resolved_params"] == {"direction": -1}


def test_direction_and_one_sided_semantics():
    import math

    positive = regenerate(document(direction=1, z=0), OCPKernel())
    assert positive.ok, positive.result
    partial = regenerate(document(direction=1, z=5), OCPKernel())
    assert partial.ok, partial.result
    assert partial.result["features"][-1]["stats"]["volume"] == pytest.approx(1000 - 5 * math.pi)
    away = regenerate(document(direction=1), OCPKernel())
    assert not away.ok
    assert away.result["features"][-1]["status"] in {"failed", "blocked"}
    from mechanical_cad.errors import CADException

    with pytest.raises(CADException, match="literal"):
        regenerate(document(direction=0), OCPKernel())


def test_candidate_is_atomic_and_does_not_invent_depth():
    source = document().to_dict()
    tool, boolean = source["features"][-2:]
    source["features"] = source["features"][:-2]
    source["active_feature"] = "base"
    before = copy.deepcopy(source)
    candidate = build(source, tool, boolean)
    assert source == before
    assert candidate["parameters"] == source["parameters"]
    assert candidate["features"][-2]["params"] == {"direction": -1}
    tool["inputs"]["base"] = "missing"
    with pytest.raises(ValueError, match="target"):
        build(source, tool, boolean)
    assert source == before


@pytest.mark.parametrize("version", [2, 3])
def test_real_sidecar_evidence_and_provenance(version):
    from mechanical_cad.sidecar import process_request

    validator = importlib.import_module(
        PACKAGE + (".result_v3" if version == 3 else ".part_result_bridge")
    )
    request = {
        "protocol_version": 1,
        "result_version": version,
        "document": document().to_dict(),
        "options": {"linear_deflection": 0.1},
    }
    response = process_request(request)
    assert response["ok"], response
    assert validator.validate_response(request, response) == response
    faces = response["result"]["features"][-1]["topology"]
    assert any(
        face["provenance"]["semantic_status"] == "stable"
        and face["provenance"].get("relation") in {"tool_modified", "tool_unchanged"}
        for face in faces
    )


@pytest.mark.parametrize("thickness", [5, 30])
@pytest.mark.parametrize("tilt", [0, 37, 90])
def test_associative_rotated_face_uses_exact_bounds_and_normal(thickness, tilt):
    import math

    doc = Document(
        "angled",
        "Angled hole",
        {},
        (
            Feature("p", "sketch_rectangle", "Profile", {"width": 10, "height": 10}),
            Feature("base", "extrude", "Base", {"length": thickness}, {"profile": "p"}),
            Feature(
                "placed",
                "transform",
                "Placed",
                {"rx": tilt, "ry": 23, "x": 100, "y": -20},
                {"base": "base"},
            ),
            Feature(
                "q",
                "sketch_face_circle",
                "Hole",
                {"radius": 1},
                {"support": "placed"},
                support_face="base/face/cap.end",
            ),
            Feature(
                "tool",
                "extrude_through",
                "Through All",
                {"direction": -1},
                {"profile": "q", "base": "placed"},
            ),
            Feature("cut", "cut", "Remove", {}, {"base": "placed", "tool": "tool"}),
        ),
        "cut",
    )
    replay = regenerate(doc, OCPKernel(), result_version=2)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
        (100 - math.pi) * thickness
    )
