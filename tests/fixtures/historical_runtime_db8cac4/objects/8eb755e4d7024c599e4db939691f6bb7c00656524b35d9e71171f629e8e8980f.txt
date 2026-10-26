"""Line-region extraction is identity-driven, bounded and conservative."""

from types import SimpleNamespace as Record

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.profile_region import closed_profile, validate_polygon


def rectangle():
    return Record(
        schema_version=1,
        points=[
            Record(id=f"p{i}", u=u, v=v)
            for i, (u, v) in enumerate(((0, 0), (40, 0), (40, 30), (0, 30)))
        ],
        lines=[Record(id=f"line{i}", start=f"p{i}", end=f"p{(i + 1) % 4}") for i in range(4)],
        constraints=[],
    )


def test_shared_point_identity_builds_deterministic_counterclockwise_profile():
    sketch = rectangle()
    expected = closed_profile(sketch)
    sketch.points.reverse()
    sketch.lines.reverse()
    for line in sketch.lines:
        line.start, line.end = line.end, line.start
    assert closed_profile(sketch) == expected
    assert expected.edge_ids == ("line0", "line1", "line2", "line3")


def test_clockwise_winding_preserves_each_line_boundary_identity():
    region = validate_polygon(
        [(0, 0), (0, 30), (40, 30), (40, 0)], ["left", "top", "right", "bottom"]
    )
    assert region.points == ((0, 0), (40, 0), (40, 30), (0, 30))
    assert region.edge_ids == ("bottom", "right", "top", "left")


def test_explicit_coincidence_connects_separate_endpoint_ids():
    sketch = rectangle()
    sketch.points += [Record(id="separate", u=0, v=0)]
    sketch.lines[-1].end = "separate"
    with pytest.raises(CADException, match="closed line loop"):
        closed_profile(sketch)
    sketch.constraints.append(Record(kind="coincident", refs=("p0", "separate")))
    assert closed_profile(sketch).edge_ids == ("line0", "line1", "line2", "line3")
    sketch.points[-1].u = 0.01
    with pytest.raises(CADException) as raised:
        closed_profile(sketch)
    assert raised.value.code == "unresolved_coincidence"


@pytest.mark.parametrize("variant", ["open", "branch", "multiple", "collapsed"])
def test_unsupported_connectivity_is_not_silently_repaired(variant):
    sketch = rectangle()
    if variant == "open":
        sketch.lines.pop()
    elif variant == "branch":
        sketch.lines.append(Record(id="diagonal", start="p0", end="p2"))
    elif variant == "multiple":
        other = rectangle()
        for point in other.points:
            point.id += "b"
            point.u += 100
        for line in other.lines:
            line.id += "b"
            line.start += "b"
            line.end += "b"
        sketch.points += other.points
        sketch.lines += other.lines
    else:
        sketch.constraints.append(Record(kind="coincident", refs=("p0", "p1")))
        sketch.points[1].u = 0
    with pytest.raises(CADException):
        closed_profile(sketch)


@pytest.mark.parametrize(
    "points,ids",
    [
        ([(0, 0), (40, 30), (0, 30), (40, 0)], ["a", "b", "c", "d"]),
        ([(0, 0), (40, 0), (20, 0), (20, 30), (0, 30)], ["a", "b", "c", "d", "e"]),
        ([(0, 0), (1e-8, 0), (0, 30)], ["a", "b", "c"]),
        ([(0, 0), (40, 0), (0, 30)], ["same", "same", "c"]),
        ([(0, 0), (float("nan"), 0), (0, 30)], ["a", "b", "c"]),
        ([(0, 0), (True, 0), (0, 30)], ["a", "b", "c"]),
        (None, []),
        ([(0, 0), (10**10000, 0), (0, 30)], ["a", "b", "c"]),
        ([None, (1, 0), (0, 1)], ["a", "b", "c"]),
        ([(0, 0), (1, 0), (0, 1)], [[], "b", "c"]),
    ],
)
def test_invalid_polygon_fails_before_native_geometry(points, ids):
    with pytest.raises(CADException):
        validate_polygon(points, ids)


def test_collinear_subdivision_can_keep_distinct_boundary_ids():
    region = validate_polygon(
        [(0, 0), (10, 0), (40, 0), (40, 30), (0, 30)], ["a", "b", "c", "d", "e"]
    )
    assert region.edge_ids == ("a", "b", "c", "d", "e")


def test_far_origin_small_region_uses_translation_invariant_area():
    region = validate_polygon(
        [(1e6, 1e6), (1e6 - 0.1, 1e6), (1e6 - 0.1, 1e6 - 0.1), (1e6, 1e6 - 0.1)],
        ["a", "b", "c", "d"],
    )
    assert len(region.points) == 4
