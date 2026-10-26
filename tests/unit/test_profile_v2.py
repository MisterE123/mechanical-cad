"""Pure profile availability never confuses unsupported regions with open chains."""

from dataclasses import replace

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.profile_region import (
    CircleProfile,
    ClosedProfile,
    OpenChainProfile,
    ProfileRegions,
    classify_profile,
    closed_profile,
    validate_circle,
)
from mechanical_cad.sketch_model import Circle, Constraint, Line, Point, Sketch


def line_sketch(coordinates, *, closed=False):
    points = tuple(Point(f"p{i}", *coordinate) for i, coordinate in enumerate(coordinates))
    count = len(points) if closed else len(points) - 1
    return Sketch(
        "sketch",
        points,
        tuple(
            Line(f"line{i}", points[i].id, points[(i + 1) % len(points)].id) for i in range(count)
        ),
        (),
        schema_version=2,
    )


def assert_profile_error(sketch, code):
    with pytest.raises(CADException) as raised:
        classify_profile(sketch)
    assert raised.value.code == code


def test_single_analytic_circle_keeps_identity_and_unused_point_evidence():
    sketch = Sketch(
        "sketch",
        (Point("center", 3, 4), Point("unused", 10, 11)),
        (),
        (),
        circles=(Circle("bore", "center", 7),),
        schema_version=2,
    )
    assert classify_profile(sketch) == CircleProfile((3.0, 4.0), 7.0, "bore")
    assert len(sketch.points) == 2
    assert classify_profile(
        replace(sketch, points=tuple(reversed(sketch.points)))
    ) == classify_profile(sketch)
    edited = replace(sketch, circles=(replace(sketch.circles[0], radius=8),))
    assert classify_profile(edited).circle_id == "bore"
    assert classify_profile(edited).radius == 8
    assert sketch.circles[0].radius == 7


@pytest.mark.parametrize(
    "coordinates",
    [((0, 0), (4, 0)), ((0, 0), (4, 0), (8, 0)), ((0, 0), (4, 0), (4, 3))],
)
def test_only_supported_chain_returns_open_with_deterministic_identity(coordinates):
    sketch = line_sketch(coordinates)
    result = classify_profile(sketch)
    assert isinstance(result, OpenChainProfile)
    assert result.points == coordinates
    assert result.edge_ids == tuple(line.id for line in sketch.lines)
    assert result.reason_code == "open_profile"
    assert result.message
    reordered = replace(
        sketch,
        points=tuple(reversed(sketch.points)),
        lines=tuple(
            replace(line, start=line.end, end=line.start) for line in reversed(sketch.lines)
        ),
    )
    assert classify_profile(reordered) == result


def test_closed_classification_preserves_legacy_winding_and_boundary_mapping():
    for coordinates in (
        ((0, 0), (0, 3), (4, 3), (4, 0)),
        ((0, 0), (4, 0), (4, 3), (2, 1), (0, 3)),
        ((0, 0), (2, 0), (4, 0), (4, 3), (0, 3)),
    ):
        sketch = line_sketch(coordinates, closed=True)
        assert isinstance(classify_profile(sketch), ClosedProfile)
        assert classify_profile(sketch) == closed_profile(sketch)
        legacy = replace(sketch, schema_version=1)
        assert classify_profile(legacy) == closed_profile(legacy)


def test_shared_ids_and_explicit_coincidence_are_the_only_connectivity():
    sketch = Sketch(
        "sketch",
        (Point("a", 0, 0), Point("b", 4, 0), Point("c", 4, 0), Point("d", 4, 3)),
        (Line("first", "a", "b"), Line("second", "c", "d")),
        (),
        schema_version=2,
    )
    assert_profile_error(sketch, "multiple_profile_regions")
    joined = replace(sketch, constraints=(Constraint("join", "coincident", ("b", "c")),))
    assert classify_profile(joined).edge_ids == ("first", "second")
    unresolved = replace(joined, points=(*joined.points[:2], Point("c", 4.01, 0), joined.points[3]))
    assert_profile_error(unresolved, "unresolved_coincidence")


def test_branch_is_a_profile_failure_and_never_open():
    sketch = line_sketch(((0, 0), (4, 0), (4, 3)))
    sketch = replace(
        sketch,
        points=(*sketch.points, Point("branch_end", 8, 0)),
        lines=(*sketch.lines, Line("branch", "p1", "branch_end")),
    )
    assert_profile_error(sketch, "branched_profile")
    with pytest.raises(CADException) as legacy:
        closed_profile(sketch)
    assert legacy.value.code == "open_profile"  # Frozen old extractor behavior.


@pytest.mark.parametrize("closed", [False, True])
def test_crossing_and_nonadjacent_touch_are_never_open(closed):
    assert_profile_error(
        line_sketch(((0, 0), (4, 4), (0, 4), (4, 0)), closed=closed),
        "self_intersecting_profile",
    )
    assert_profile_error(
        line_sketch(((0, 0), (4, 0), (4, 3), (2, 0)), closed=closed),
        "self_intersecting_profile",
    )


def test_geometric_closed_touch_without_identity_is_not_saveable_open():
    sketch = line_sketch(((0, 0), (4, 0), (4, 3), (0, 3), (0, 0)))
    assert_profile_error(sketch, "self_intersecting_profile")
    closed = replace(sketch, constraints=(Constraint("close", "coincident", ("p0", "p4")),))
    assert isinstance(classify_profile(closed), ClosedProfile)


def test_open_adjacent_overlap_and_tiny_segment_are_rejected():
    assert_profile_error(line_sketch(((0, 0), (4, 0), (2, 0))), "self_intersecting_profile")
    assert_profile_error(line_sketch(((0, 0), (1e-8, 0))), "degenerate_profile")
    assert_profile_error(line_sketch(((0, 0), (0, 0))), "degenerate_profile")
    collapsed = line_sketch(((0, 0), (0, 0)))
    collapsed = replace(collapsed, constraints=(Constraint("join", "coincident", ("p0", "p1")),))
    assert_profile_error(collapsed, "degenerate_profile")


@pytest.mark.parametrize("closed", [False, True])
def test_disconnected_line_regions_cannot_be_selected_implicitly(closed):
    sketch = line_sketch(((0, 0), (4, 0), (4, 3), (0, 3)), closed=closed)
    sketch = replace(
        sketch,
        points=(*sketch.points, Point("a", 10, 10), Point("b", 11, 10)),
        lines=(*sketch.lines, Line("separate", "a", "b")),
    )
    assert_profile_error(sketch, "multiple_profile_regions")


def test_nested_circles_are_regions_but_mixed_open_boundary_is_not():
    circle = Sketch(
        "sketch",
        (Point("center", 0, 0),),
        (),
        (),
        circles=(Circle("one", "center", 2), Circle("two", "center", 1)),
        schema_version=2,
    )
    assert isinstance(classify_profile(circle), ProfileRegions)
    mixed = line_sketch(((0, 0), (4, 0)))
    mixed = replace(mixed, circles=(Circle("circle", "p0", 2),))
    assert_profile_error(mixed, "mixed_profile_regions")


def test_no_curves_and_duplicate_backtracking_boundary_are_not_open():
    assert_profile_error(Sketch("empty", (), (), (), schema_version=2), "invalid_profile")
    sketch = line_sketch(((0, 0), (4, 0)), closed=True)
    assert_profile_error(sketch, "degenerate_profile")


@pytest.mark.parametrize("radius", [0, -1, 1e-7, 1e6 + 1, True, "1", float("nan"), float("inf")])
def test_circle_invalid_radius_fails_purely(radius):
    with pytest.raises(CADException) as raised:
        validate_circle((0, 0), radius, "circle")
    assert raised.value.code == "degenerate_profile"


@pytest.mark.parametrize("center", [None, [0], [True, 0], [1e6 + 1, 0], [float("nan"), 0]])
def test_circle_center_bounds_are_independent_from_radius(center):
    with pytest.raises(CADException):
        validate_circle(center, 1, "circle")
    assert validate_circle((1e6, -1e6), 1e6, "circle").radius == 1e6


@pytest.mark.parametrize("identifier", [None, "", "a/b", "a" * 129, "not ascii ç"])
def test_circle_boundary_identity_is_not_inferred_or_sanitized(identifier):
    with pytest.raises(CADException) as raised:
        validate_circle((0, 0), 1, identifier)
    assert raised.value.code == "invalid_profile"
