"""General closed analytic sketches replay into true native rounded solids."""

import importlib
import math
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("OCP")
pytest.importorskip("slvs")

from mechanical_cad.analytic_profile import classify_analytic_profile
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Arc, Circle, Line, Point, SketchDefinition, resolve_sketch


def rounded_plate():
    return SketchDefinition(
        "rounded_plate",
        (
            Point("a", 0, -5),
            Point("b", 20, -5),
            Point("c", 20, 5),
            Point("d", 0, 5),
            Point("left", 0, 0),
            Point("right", 20, 0),
            Point("bore", 10, 0),
        ),
        (Line("lower", "a", "b"), Line("upper", "c", "d")),
        (),
        schema_version=3,
        arcs=(Arc("right_arc", "right", "b", "c", "ccw"), Arc("left_arc", "left", "d", "a", "ccw")),
        circles=(Circle("hole", "bore", 2),),
    )


def rounded_document(*, downstream=False):
    features = (
        Feature("sketch", "sketch_constrained", "Rounded mounting plate", sketch=rounded_plate()),
        Feature("pad", "extrude", "Plate", {"length": 5}, {"profile": "sketch"}),
    )
    if downstream:
        features += (Feature("moved", "transform", "Placed plate", {"x": 20}, {"base": "pad"}),)
    return Document("rounded", "Rounded plate", {}, features, features[-1].id, schema_version=2)


def test_actual_rounded_plate_hole_native_volume_and_provenance():
    sketch = resolve_sketch(rounded_plate(), {})
    regions = classify_analytic_profile(sketch)
    kernel = OCPKernel()
    solid = kernel.extrude(kernel.analytic_region_profile(regions.regions), 5)
    assert kernel.inspect(solid)["volume"] == pytest.approx((200 + 21 * math.pi) * 5)
    roles = {item["role"] for item in kernel.topology(solid, "pad", "extrude", {})}
    assert {"side.arc.right_arc", "side.arc.left_arc", "side.circle.hole"} <= roles


@pytest.mark.parametrize("downstream", [False, True])
def test_generic_arc_sketch_real_solver_replay_and_save(downstream):
    doc = Document.from_dict(rounded_document(downstream=downstream).to_dict())
    replay = regenerate(doc, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert replay.result["features"][0]["output"]["profile"]["region_kind"] == "analytic_regions"
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
        (200 + 21 * math.pi) * 5
    )
    sketch = doc.features[0].sketch
    sketch = replace(sketch, circles=(Circle("hole", "bore", 3),))
    edited = replace(doc, features=(replace(doc.features[0], sketch=sketch), *doc.features[1:]))
    replay = regenerate(edited, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
        (200 + 16 * math.pi) * 5
    )


def result_bridge():
    package = "mcad_analytic_regions_bridge"
    module = types.ModuleType(package)
    module.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    sys.modules[package] = module
    return importlib.import_module(package + ".result_v3")


def test_rounded_profile_actual_bridge_and_solve_readiness():
    bridge = result_bridge()
    request = {"protocol_version": 1, "result_version": 3, "document": rounded_document().to_dict()}
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_response(request, response)
    request = {**request, "action": "solve_sketch", "feature_id": "sketch"}
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_solve_response(response, request)


def quarter_arc(lines):
    return SketchDefinition(
        "quarter_arc",
        (Point("o", 0, 0), Point("a", 5, 0), Point("b", 0, 5)),
        lines,
        (),
        schema_version=3,
        arcs=(Arc("rim", "o", "a", "b", "ccw"),),
    )


def test_mixed_sector_graph_actual_replay_and_solve_bridge():
    sector = quarter_arc((Line("oa", "o", "a"), Line("ob", "o", "b")))
    doc = Document(
        "mixed",
        "Mixed sector and ordinary graph",
        {},
        (
            Feature("sketch", "sketch_constrained", "Sector", sketch=sector),
            Feature("pad", "extrude", "Sector pad", {"length": 7}, {"profile": "sketch"}),
            Feature("other", "sketch_circle", "Independent circle", {"radius": 3}),
            Feature("other_pad", "extrude", "Circle pad", {"length": 2}, {"profile": "other"}),
            Feature("pad2", "extrude", "Second sector pad", {"length": 4}, {"profile": "sketch"}),
            Feature("moved", "transform", "Moved sector pad", {"x": 20}, {"base": "pad"}),
        ),
        "moved",
        schema_version=2,
    )
    bridge = result_bridge()
    request = {"protocol_version": 1, "result_version": 3, "document": doc.to_dict()}
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_response(request, response)
    features = {item["id"]: item for item in response["result"]["features"]}
    assert features["sketch"]["output"]["profile"]["region_kind"] == "curve_loop"
    for identifier, volume in {
        "pad": 25 * math.pi * 7 / 4,
        "other_pad": 9 * math.pi * 2,
        "pad2": 25 * math.pi,
        "moved": 25 * math.pi * 7 / 4,
    }.items():
        stats = features[identifier]["stats"]
        assert stats["valid"] and stats["solids"] == 1
        assert stats["volume"] == pytest.approx(volume)
    solve_request = {**request, "action": "solve_sketch", "feature_id": "sketch"}
    solve_response = process_request(solve_request)
    assert solve_response["ok"], solve_response
    bridge.validate_response(solve_request, solve_response)
    assert solve_response["result"]["profile_check"] == {"ready": True, "error": None}


@pytest.mark.parametrize(
    "lines,code",
    [
        ((Line("chord", "a", "b"),), None),
        ((), "open_profile"),
        ((Line("chord", "a", "b"), Line("duplicate", "a", "b")), "unsupported_profile_form"),
    ],
    ids=["closed_arc_chord", "open_arc", "branched_overlap"],
)
def test_actual_arc_boundary_readiness_and_chord_solid(lines, code):
    doc = Document(
        "arc",
        "Quarter arc boundary",
        {},
        (
            Feature("sketch", "sketch_constrained", "Arc", sketch=quarter_arc(lines)),
            Feature("pad", "extrude", "Pad", {"length": 7}, {"profile": "sketch"}),
        ),
        "pad",
        schema_version=2,
    )
    bridge = result_bridge()
    request = {
        "protocol_version": 1,
        "result_version": 3,
        "document": doc.to_dict(),
        "action": "solve_sketch",
        "feature_id": "sketch",
    }
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_response(request, response)
    check = response["result"]["profile_check"]
    if code is not None:
        assert check["ready"] is False and check["error"]["code"] == code
        return
    assert check == {"ready": True, "error": None}
    request.pop("feature_id")
    request["action"] = "replay"
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_response(request, response)
    profile, solid = response["result"]["features"]
    assert profile["output"]["profile"]["region_kind"] == "analytic_regions"
    assert solid["stats"]["valid"] and solid["stats"]["solids"] == 1
    assert solid["stats"]["volume"] == pytest.approx((25 * math.pi / 4 - 25 / 2) * 7)
    assert {item["role"] for item in solid["topology"]} == {
        "cap.start",
        "cap.end",
        "side.line.chord",
        "side.arc.rim",
    }


def test_analytic_profile_rotated_plane_extrudes_along_plane_normal():
    from mechanical_cad.sketch_model import Plane

    sketch = resolve_sketch(
        replace(rounded_plate(), plane=Plane((2, 3, 4), (math.sqrt(0.5), math.sqrt(0.5), 0, 0))), {}
    )
    region = classify_analytic_profile(sketch)
    kernel = OCPKernel()
    shape = kernel.extrude(
        kernel.analytic_region_profile(
            region.regions, origin=sketch.plane.origin, quaternion=sketch.plane.quaternion
        ),
        5,
    )
    stats = kernel.inspect(shape)
    assert stats["volume"] == pytest.approx((200 + 21 * math.pi) * 5)
    assert stats["valid"]


def test_rounded_part_step_export_after_downstream_transform(tmp_path):
    request = {
        "protocol_version": 1,
        "result_version": 3,
        "document": rounded_document(downstream=True).to_dict(),
        "action": "export_step",
        "destination": str(tmp_path / "rounded.step"),
    }
    response = process_request(request)
    assert response["ok"], response
    assert (tmp_path / "rounded.step").stat().st_size > 0
