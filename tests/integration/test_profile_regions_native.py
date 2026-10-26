"""Real exact faces/solids and authored hole provenance, not mesh approximations."""

import math

import pytest

pytest.importorskip("OCP")

from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.profile_region import ProfileRegion, validate_circle, validate_polygon


def test_plate_holes_native_volume_topology_and_negative_extrusion():
    outer = validate_polygon(
        ((0, 0), (40, 0), (40, 30), (0, 30)), ("bottom", "right", "top", "left")
    )
    holes = (validate_circle((10, 15), 3, "hole_a"), validate_circle((30, 15), 3, "hole_b"))
    for length in (5, -5):
        kernel = OCPKernel()
        face = kernel.region_profile((ProfileRegion(outer, holes),))
        shape = kernel.extrude(face, length)
        stats = kernel.inspect(shape)
        assert stats["valid"] and stats["solids"] == 1
        assert stats["volume"] == pytest.approx((1200 - 18 * math.pi) * 5)
        roles = {item["role"] for item in kernel.topology(shape, "pad", "extrude", {})}
        assert {"side.circle.hole_a", "side.circle.hole_b", "side.line.bottom"} <= roles


def test_enclosure_wall_and_annulus_native_volume():
    outer = validate_polygon(((0, 0), (40, 0), (40, 30), (0, 30)), ("a", "b", "c", "d"))
    hole = validate_polygon(((2, 2), (38, 2), (38, 28), (2, 28)), ("e", "f", "g", "h"))
    kernel = OCPKernel()
    shape = kernel.extrude(kernel.region_profile((ProfileRegion(outer, (hole,)),)), 20)
    assert kernel.inspect(shape)["volume"] == pytest.approx((1200 - 36 * 26) * 20)
    annulus = ProfileRegion(
        validate_circle((0, 0), 10, "outer"), (validate_circle((0, 0), 4, "inner"),)
    )
    shape = kernel.extrude(kernel.region_profile((annulus,)), 5)
    assert kernel.inspect(shape)["volume"] == pytest.approx(84 * math.pi * 5)


def test_disjoint_native_regions_preserve_separate_solids():
    kernel = OCPKernel()
    regions = (
        ProfileRegion(validate_circle((0, 0), 2, "a")),
        ProfileRegion(validate_circle((10, 0), 2, "b")),
    )
    face = kernel.region_profile(regions)
    assert kernel.inspect(kernel.extrude(face, 4))["solids"] == 2


def _annulus_document(*, schema=2, separate=False):
    from mechanical_cad.model import Document, Feature
    from mechanical_cad.sketch_model import Circle, Constraint, Point, SketchDefinition

    second = (30, 0) if separate else (0, 0)
    sketch = SketchDefinition(
        "annulus",
        (Point("center", 0, 0), Point("other", *second)),
        (),
        (
            Constraint("anchor", "fixed", ("center",), target=(0, 0)),
            Constraint("other_anchor", "fixed", ("other",), target=second),
            Constraint("outer_size", "radius", ("outer",), "outer_radius"),
            Constraint("bore_size", "radius", ("bore",), 4),
        ),
        schema_version=schema,
        circles=(Circle("outer", "center", 10), Circle("bore", "other", 4)),
    )
    return Document(
        "washer",
        "Washer",
        {"outer_radius": 10},
        (
            Feature("sketch", "sketch_constrained", "Annulus", sketch=sketch),
            Feature("pad", "extrude", "Pad", {"length": 5}, {"profile": "sketch"}),
        ),
        "pad",
        schema_version=2,
    )


@pytest.mark.parametrize("schema", [2, 3])
def test_saved_parametric_annulus_replays_with_real_solver_and_hole(schema):
    from dataclasses import replace

    from mechanical_cad.engine import regenerate
    from mechanical_cad.model import Document

    document = _annulus_document(schema=schema)
    document = Document.from_dict(document.to_dict())
    replay = regenerate(document, OCPKernel(), result_version=schema)
    assert replay.ok, replay.result
    sketch, pad = replay.result["features"]
    assert sketch["output"]["profile"]["region_kind"] == "regions"
    assert pad["stats"]["volume"] == pytest.approx(84 * math.pi * 5)
    edited = replace(document, parameters={"outer_radius": 12})
    replay = regenerate(edited, OCPKernel(), result_version=schema)
    assert replay.ok, replay.result
    assert replay.result["features"][1]["stats"]["volume"] == pytest.approx(128 * math.pi * 5)


def test_disjoint_part_feature_fails_explicitly_not_silently_selected():
    from mechanical_cad.engine import regenerate

    replay = regenerate(_annulus_document(separate=True), OCPKernel(), result_version=2)
    assert not replay.ok
    assert replay.result["features"][0]["status"] == "ok"
    assert replay.result["features"][1]["error"]["code"] == "unsupported_solid_count"


@pytest.mark.parametrize("schema", [2, 3])
def test_multi_loop_replay_crosses_strict_blender_bridge(schema):
    import importlib
    import sys
    import types
    from pathlib import Path

    from mechanical_cad.sidecar import process_request

    package = "mcad_region_native_bridge"
    module = types.ModuleType(package)
    module.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    sys.modules[package] = module
    bridge = importlib.import_module(
        package + (".result_v3" if schema == 3 else ".part_result_bridge")
    )
    request = {
        "protocol_version": 1,
        "result_version": schema,
        "document": _annulus_document(schema=schema).to_dict(),
    }
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_response(request, response)
