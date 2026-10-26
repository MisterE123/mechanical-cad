"""Exact placement on off-origin, asymmetric, rolled and reversed sections/paths."""

import math
from dataclasses import replace

import pytest
from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_VERTEX
from OCP.TopoDS import TopoDS

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import KernelError, OCPKernel, _subshapes
from mechanical_cad.model import Document, Feature, load_document, save_document
from mechanical_cad.profile_region import CircleProfile, ProfileRegion, validate_polygon
from mechanical_cad.sketch_model import (
    Arc,
    Line,
    Plane,
    Point,
    Sketch,
    SketchDefinition,
)

INTENT = {"version": 1, "mode": "path_start_centroid", "reverse": False, "roll_degrees": 0}


def line_path(schema=2):
    return Sketch(
        "path",
        (Point("a", 10, 20), Point("b", 40, 20)),
        (Line("rail", "a", "b"),),
        (),
        schema_version=schema,
    )


def centroid(shape, surface=True):
    prop = GProp_GProps()
    (BRepGProp.SurfaceProperties_s if surface else BRepGProp.VolumeProperties_s)(shape, prop)
    point = prop.CentreOfMass()
    return point.X(), point.Y(), point.Z()


def vertices(shape):
    return sorted(
        tuple(BRep_Tool.Pnt_s(TopoDS.Vertex(v)).Coord()) for v in _subshapes(shape, TopAbs_VERTEX)
    )


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("roll", [0, 90, -35])
def test_asymmetric_off_origin_triangle_exact_section_frame_roll_and_reverse(reverse, roll):
    kernel = OCPKernel()
    # Area centroid (102, 201), neither sketch origin nor bounds center (103, 201.5).
    points = ((100, 200), (106, 200), (100, 203))
    profile = kernel.polygon(
        points,
        ("ab", "bc", "ca"),
        origin=(15, -9, 40),
        quaternion=(math.sqrt(0.5), math.sqrt(0.5), 0, 0),
    )
    original = vertices(profile)
    solid = kernel.sweep(
        profile, line_path(), placement={**INTENT, "reverse": reverse, "roll_degrees": roll}
    )
    assert kernel.inspect(solid)["volume"] == pytest.approx(9 * 30)
    assert kernel.inspect(solid)["valid"]
    placed = kernel._operations[id(solid)].inputs["profile"]
    start = (40 if reverse else 10, 20, 0)
    assert centroid(placed) == pytest.approx(start, abs=1e-8)
    # Path +X (or -X); zero U=+Z, zero V=-Y (or +Y).
    direction = -1 if reverse else 1
    c, s = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    expected = sorted(
        (start[0], 20 - direction * (s * (u - 102) + c * (v - 201)), c * (u - 102) - s * (v - 201))
        for u, v in points
    )
    for observed, target in zip(vertices(placed), expected, strict=True):
        assert observed == pytest.approx(target, abs=1e-8)
    assert vertices(profile) == original
    topology = kernel.topology(solid, "s", "sweep", {})
    assert topology and all(f["provenance"]["semantic_status"] != "stable" for f in topology)


@pytest.mark.parametrize("reverse", [False, True])
def test_arc_start_uses_directed_tangent_with_asymmetric_offset_section(reverse):
    kernel = OCPKernel()
    profile = kernel.polygon(((100, 200), (106, 200), (100, 203)), ("a", "b", "c"))
    path = Sketch(
        "path",
        (Point("a", 20, 0), Point("z", 0, 20), Point("center", 0, 0)),
        (),
        (),
        arcs=(Arc("curve", "center", "a", "z", "ccw"),),
        schema_version=3,
        plane=Plane(origin=(4, 7, 9)),
    )
    original = path.to_json()
    solid = kernel.sweep(profile, path, placement={**INTENT, "reverse": reverse})
    assert kernel.inspect(solid)["volume"] == pytest.approx(9 * 20 * math.pi / 2, rel=1e-7)
    assert kernel.manufacturing_check(solid)["mesh"]["watertight"]
    placed = kernel._operations[id(solid)].inputs["profile"]
    assert centroid(placed) == pytest.approx((4, 27, 9) if reverse else (24, 7, 9))
    # Exact cap normal plane: +Y at first endpoint, +X at reverse endpoint.
    constant_axis = 0 if reverse else 1
    assert all(v[constant_axis] == pytest.approx(4 if reverse else 7) for v in vertices(placed))
    assert path.to_json() == original


def test_off_center_hole_uses_filled_area_centroid_not_outline_or_bounds():
    kernel = OCPKernel()
    outer = validate_polygon(((100, 200), (110, 200), (110, 206), (100, 206)), ("a", "b", "c", "d"))
    profile = kernel.region_profile(
        (ProfileRegion(outer, (CircleProfile((108, 203), 0.5, "hole"),)),)
    )
    old_center = centroid(profile)
    assert old_center[0] != pytest.approx(105, abs=1e-3)
    solid = kernel.sweep(profile, line_path(), placement=INTENT)
    assert kernel.inspect(solid)["volume"] == pytest.approx((60 - math.pi * 0.25) * 30)
    assert centroid(kernel._operations[id(solid)].inputs["profile"]) == pytest.approx((10, 20, 0))


@pytest.mark.parametrize("schema", [2, 3])
def test_saved_replay_edits_and_legacy_preservation(tmp_path, schema):
    path = line_path(schema)
    definition = SketchDefinition.from_dict(
        {
            **path.to_dict(),
            "constraints": [
                {"id": "fix_a", "kind": "fixed", "refs": ["a"], "target": [10, 20]},
                {"id": "fix_b", "kind": "fixed", "refs": ["b"], "target": [40, 20]},
            ],
        }
    )
    doc = Document(
        "d",
        "Sweep",
        {},
        (
            Feature(
                "p", "sketch_rectangle", "Section", {"width": 6, "height": 3, "x": 100, "y": 200}
            ),
            Feature("path", "sketch_constrained", "Path", sketch=definition),
            Feature(
                "s", "sweep", "Sweep", {}, {"profile": "p", "path": "path"}, sweep_placement=INTENT
            ),
        ),
        "s",
        schema_version=2,
    )
    doc = Document.from_dict(doc.to_dict())
    saved = tmp_path / "sweep.mcad.json"
    save_document(doc, saved)
    reopened = load_document(saved)
    assert reopened.to_json() == doc.to_json()
    replay = regenerate(reopened, OCPKernel(), result_version=schema)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(18 * 30)
    edited = replace(
        doc,
        features=(
            *doc.features[:-1],
            replace(
                doc.features[-1], sweep_placement={**INTENT, "reverse": True, "roll_degrees": 40}
            ),
        ),
    )
    assert regenerate(edited, OCPKernel(), result_version=schema).ok
    legacy = replace(doc.features[-1], sweep_placement=None)
    assert "sweep_placement" not in legacy.to_dict()
    assert Feature.from_dict(legacy.to_dict()).to_dict() == legacy.to_dict()


def test_automatic_placement_rejects_closed_path_and_multiple_section_islands():
    kernel = OCPKernel()
    closed = Sketch(
        "path",
        (Point("a", 0, 0), Point("b", 20, 0), Point("c", 20, 20)),
        (Line("ab", "a", "b"), Line("bc", "b", "c"), Line("ca", "c", "a")),
        (),
    )
    with pytest.raises(KernelError, match="open path"):
        kernel.sweep(kernel.circle(1), closed, placement=INTENT)
    islands = kernel.region_profile(
        (ProfileRegion(CircleProfile((0, 0), 1, "a")), ProfileRegion(CircleProfile((4, 0), 1, "b")))
    )
    with pytest.raises(KernelError, match="one filled planar region"):
        kernel.sweep(islands, line_path(), placement=INTENT)


def test_rotated_path_plane_and_endpoint_record_order_do_not_guess_orientation():
    kernel = OCPKernel()
    profile = kernel.rectangle(6, 3, x=100, y=200)
    q = (math.sqrt(0.5), 0, math.sqrt(0.5), 0)
    path = replace(line_path(), plane=Plane(origin=(5, 8, 11), quaternion=q))
    solid = kernel.sweep(profile, path, placement=INTENT)
    placed = kernel._operations[id(solid)].inputs["profile"]
    # Local path +U is world -Z, local plane normal is +X; +V of section is -Y.
    assert centroid(placed) == pytest.approx((5, 28, 1), abs=1e-8)
    expected = sorted(
        (5 + du, 28 - dv, 1) for du, dv in ((-3, -1.5), (3, -1.5), (3, 1.5), (-3, 1.5))
    )
    for actual, target in zip(vertices(placed), expected, strict=True):
        assert actual == pytest.approx(target, abs=1e-8)
    reordered = replace(path, points=tuple(reversed(path.points)), lines=(Line("rail", "b", "a"),))
    again = kernel.sweep(profile, reordered, placement=INTENT)
    assert vertices(kernel._operations[id(again)].inputs["profile"]) == vertices(placed)
    assert kernel.inspect(again)["volume"] == pytest.approx(540)


def test_clockwise_arc_travel_uses_negative_tangent_without_changing_seeds():
    kernel = OCPKernel()
    profile = kernel.rectangle(6, 3, x=100, y=200)
    path = Sketch(
        "path",
        (Point("a", 20, 0), Point("z", 0, -20), Point("center", 0, 0)),
        (),
        (),
        arcs=(Arc("curve", "center", "a", "z", "cw"),),
        schema_version=3,
    )
    solid = kernel.sweep(profile, path, placement=INTENT)
    placed = kernel._operations[id(solid)].inputs["profile"]
    # Start tangent is -Y, so section +V points -X, +U points +Z.
    expected = sorted((20 - dv, 0, du) for du, dv in ((-3, -1.5), (3, -1.5), (3, 1.5), (-3, 1.5)))
    for actual, target in zip(vertices(placed), expected, strict=True):
        assert actual == pytest.approx(target, abs=1e-8)
    assert kernel.inspect(solid)["volume"] == pytest.approx(18 * 20 * math.pi / 2)
