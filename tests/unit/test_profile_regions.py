"""Closed multi-loop plates, enclosures, islands and contact rejection."""

from dataclasses import replace

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.profile_region import ProfileRegions, classify_profile
from mechanical_cad.sketch_model import Circle, Line, Point, Sketch


def region_sketch(polygons=(), circles=()):
    points, lines, disks = [], [], []
    for index, polygon in enumerate(polygons):
        ids = [f"p{index}_{vertex}" for vertex in range(len(polygon))]
        points.extend(Point(identifier, *xy) for identifier, xy in zip(ids, polygon, strict=True))
        lines.extend(
            Line(f"l{index}_{i}", point, ids[(i + 1) % len(ids)]) for i, point in enumerate(ids)
        )
    for index, (x, y, radius) in enumerate(circles):
        points.append(Point(f"c{index}", x, y))
        disks.append(Circle(f"circle{index}", f"c{index}", radius))
    return Sketch(
        "regions", tuple(points), tuple(lines), (), schema_version=2, circles=tuple(disks)
    )


BOX = ((0, 0), (40, 0), (40, 30), (0, 30))
INNER = ((2, 2), (38, 2), (38, 28), (2, 28))


def test_plate_two_holes_is_order_and_winding_independent():
    sketch = region_sketch((BOX,), ((10, 15, 3), (30, 15, 3)))
    regions = classify_profile(sketch)
    assert isinstance(regions, ProfileRegions)
    assert len(regions.regions) == 1
    assert len(regions.regions[0].holes) == 2
    assert len(regions.boundary_ids) == 6
    assert (
        classify_profile(
            replace(
                sketch,
                points=tuple(reversed(sketch.points)),
                lines=tuple(reversed(sketch.lines)),
                circles=tuple(reversed(sketch.circles)),
            )
        )
        == regions
    )


def test_enclosure_nested_island_and_disjoint_regions():
    enclosure = classify_profile(region_sketch((BOX, INNER)))
    assert len(enclosure.regions) == 1
    assert len(enclosure.regions[0].holes) == 1
    island = classify_profile(region_sketch((BOX, INNER), ((10, 10, 2),)))
    assert len(island.regions) == 2
    assert sorted(len(region.holes) for region in island.regions) == [0, 1]
    separate = classify_profile(region_sketch(circles=((0, 0, 2), (10, 0, 2))))
    assert len(separate.regions) == 2


@pytest.mark.parametrize(
    "circles",
    [
        ((5, 5, 5),),
        ((0, 15, 3),),
        ((10, 15, 3), (16, 15, 3)),
        ((10, 15, 3), (15, 15, 3)),
        ((10, 15, 3), (10, 15, 3)),
    ],
)
def test_touching_overlapping_and_identical_boundaries_fail(circles):
    with pytest.raises(CADException, match="cross, overlap or touch"):
        classify_profile(region_sketch((BOX,), circles))


def test_concentric_annulus_is_hole_not_two_disks():
    regions = classify_profile(region_sketch(circles=((0, 0, 10), (0, 0, 4))))
    assert len(regions.regions) == 1
    assert regions.regions[0].outer.radius == 10
    assert regions.regions[0].holes[0].radius == 4


def test_native_free_bridge_agrees_and_rejects_forged_contacts():
    import importlib
    import sys
    import types
    from pathlib import Path

    package = "mcad_region_bridge_tests"
    module = types.ModuleType(package)
    module.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    sys.modules[package] = module
    bridge = importlib.import_module(package + ".region_profile_bridge")
    assert bridge.expected_region_kind(region_sketch((BOX,), ((10, 15, 3),)).to_dict()) == "regions"
    assert bridge.expected_region_kind(region_sketch((BOX, INNER)).to_dict()) == "regions"
    assert bridge.expected_region_kind(region_sketch(circles=((0, 0, 5),)).to_dict()) == "circle"
    with pytest.raises(ValueError):
        bridge.expected_region_kind(region_sketch((BOX,), ((0, 15, 3),)).to_dict())
