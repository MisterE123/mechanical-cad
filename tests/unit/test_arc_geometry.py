"""Native-free directed-arc policy, including exact computed-double boundaries."""

import math
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mechanical_cad.arc_geometry import (
    MAX_ARC_COORDINATE_MM,
    MAX_ARC_RADIUS_MM,
    MAX_ARC_RADIUS_RELATIVE_RESIDUAL,
    MAX_ARC_RADIUS_RESIDUAL_MM,
    MIN_ARC_CHORD_MM,
    MIN_ARC_RADIUS_MM,
    MIN_ARC_SWEEP_RADIANS,
    ArcGeometryError,
    arc_geometry,
)

ROOT = Path(__file__).resolve().parents[2]


def rejected(center, start, end, direction="ccw", *, code, equal=False):
    with pytest.raises(ArcGeometryError) as error:
        arc_geometry(center, start, end, direction, require_equal_radii=equal)
    assert error.value.code == code
    assert error.value.message == str(error.value)


def test_policy_constants_are_the_reviewed_contract():
    assert MIN_ARC_RADIUS_MM == MIN_ARC_CHORD_MM == 1e-6
    assert MAX_ARC_COORDINATE_MM == MAX_ARC_RADIUS_MM == 1e6
    assert MIN_ARC_SWEEP_RADIANS == 1e-8
    assert MAX_ARC_RADIUS_RESIDUAL_MM == 1e-7
    assert MAX_ARC_RADIUS_RELATIVE_RESIDUAL == 1e-8


def test_policy_import_requires_no_site_packages_or_native_backend():
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); "
            "from mechanical_cad.arc_geometry import arc_geometry; "
            "arc_geometry((0, 0), (1, 0), (0, 1), 'ccw'); "
            "assert not any(n.split('.')[0] in {'OCP', 'slvs', 'numpy', 'bpy'} "
            "for n in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "end,direction,sweep",
    [
        ((0, 5), "ccw", math.pi / 2),
        ((0, 5), "cw", -3 * math.pi / 2),
        ((0, -5), "ccw", 3 * math.pi / 2),
        ((0, -5), "cw", -math.pi / 2),
        ((-5, 0.0), "ccw", math.pi),
        ((-5, -0.0), "ccw", math.pi),
        ((-5, 0.0), "cw", -math.pi),
        ((-5, -0.0), "cw", -math.pi),
    ],
)
def test_uv_direction_quarters_major_arcs_and_signed_zero_semicircles(end, direction, sweep):
    geometry = arc_geometry((0, 0), (5, 0), end, direction, require_equal_radii=True)
    assert geometry.sweep_radians == sweep
    assert geometry.start_radius == geometry.end_radius == 5
    assert geometry.chord == math.dist((5, 0), end)
    with pytest.raises(FrozenInstanceError):
        geometry.start_radius = 123


@pytest.mark.parametrize("offset", [(0, 0), (999990, -999990), (-999990, 999990)])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_translated_and_rotated_axis_arcs_keep_direction_and_canonical_start(offset, direction):
    cx, cy = offset
    for start, end in [((5, 0), (0, 5)), ((0, 5), (-5, 0)), ((-5, 0), (0, -5))]:
        result = arc_geometry(
            offset,
            (cx + start[0], cy + start[1]),
            (cx + end[0], cy + end[1]),
            direction,
            require_equal_radii=True,
        )
        assert result.start_radius == result.end_radius == 5
        assert result.sweep_radians == (math.pi / 2 if direction == "ccw" else -3 * math.pi / 2)


@pytest.mark.parametrize(
    "radius", [1e-6, math.nextafter(1e-6, math.inf), math.nextafter(1e6, 0), 1e6]
)
@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_radius_domain_accepts_exact_endpoints_and_inner_neighbors(radius, direction):
    result = arc_geometry((0, 0), (radius, 0), (0, radius), direction, require_equal_radii=True)
    assert result.start_radius == result.end_radius == radius


@pytest.mark.parametrize("radius", [0, math.nextafter(1e-6, 0), math.nextafter(1e6, math.inf)])
@pytest.mark.parametrize("role", ["start", "end"])
def test_either_radius_rejects_outer_nextafter_without_coordinate_gate_masking_it(radius, role):
    # Center/end coordinates remain in bounds even when a derived radius exceeds 1e6.
    center = (-1.0, -1.0)
    points = {"start": (radius - 1, -1.0), "end": (-1.0, radius - 1)}
    if radius < 1e-6:
        center = (0.0, 0.0)
        points = {"start": (radius, 0.0), "end": (0.0, radius)}
    points["end" if role == "start" else "start"] = (
        (center[0], center[1] + 1) if role == "start" else (center[0] + 1, center[1])
    )
    rejected(center, points["start"], points["end"], code="invalid_number")


@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("chord", [math.nextafter(1e-6, 0), 1e-6, math.nextafter(1e-6, math.inf)])
def test_chord_boundary_is_inclusive_without_hidden_epsilon(direction, chord):
    center, start, end = (0, 0), (1, 0), (1, chord)
    assert math.dist(start, end) == chord
    if chord < MIN_ARC_CHORD_MM:
        rejected(center, start, end, direction, code="degenerate_arc", equal=True)
    else:
        result = arc_geometry(center, start, end, direction, require_equal_radii=True)
        assert result.chord == chord
        assert result.start_radius == 1  # No average with the slightly larger end radius.


@pytest.mark.parametrize("direction,sign", [("ccw", 1), ("cw", -1)])
@pytest.mark.parametrize("angle", [math.nextafter(1e-8, 0), 1e-8, math.nextafter(1e-8, math.inf)])
def test_near_zero_angle_boundary_exact_and_nextafter_with_large_valid_chord(
    direction, sign, angle
):
    radius = 1e6
    end = (radius, sign * radius * math.tan(angle))
    computed = math.atan2(radius * end[1], radius * end[0])
    assert abs(computed) == angle
    assert math.dist((radius, 0), end) > 1e-6
    if angle < 1e-8:
        rejected((0, 0), (radius, 0), end, direction, code="degenerate_arc", equal=True)
    else:
        result = arc_geometry((0, 0), (radius, 0), end, direction, require_equal_radii=True)
        assert result.sweep_radians == sign * angle


@pytest.mark.parametrize("direction,sign", [("ccw", -1), ("cw", 1)])
@pytest.mark.parametrize(
    "sweep,accepted",
    [
        (math.nextafter(math.tau - 1e-8, 0), True),
        (math.tau - 1e-8, False),
        (math.nextafter(math.tau - 1e-8, math.inf), False),
    ],
)
def test_full_turn_gate_uses_computed_distance_without_epsilon(direction, sign, sweep, accepted):
    # tau - 1e-8 rounds to a double whose distance from tau is BELOW 1e-8.
    gap = math.tau - sweep
    end = (1e6, sign * 1e6 * math.tan(gap))
    computed = math.tau - abs(math.atan2(1e6 * end[1], 1e6 * end[0]))
    assert computed == sweep
    assert (math.tau - computed >= 1e-8) is accepted
    if accepted:
        result = arc_geometry((0, 0), (1e6, 0), end, direction, require_equal_radii=True)
        assert result.sweep_radians == -sign * sweep
    else:
        rejected((0, 0), (1e6, 0), end, direction, code="degenerate_arc", equal=True)


@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_chord_does_not_substitute_for_angular_gate_even_for_unequal_authored_radii(direction):
    rejected((0, 0), (1, 0), (2, 0), direction, code="degenerate_arc")


@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_angular_gate_does_not_substitute_for_spatial_gate_at_small_radius(direction):
    rejected((0, 0), (1e-6, 0), (1e-6, 0.5e-6), direction, code="degenerate_arc")


@pytest.mark.parametrize("radius", [2**-46 / 1e-8, 2**-28 / 1e-8])
@pytest.mark.parametrize("neighbor", [-1, 0, 1])
def test_relative_radial_residual_accepts_exact_limit_and_rejects_nextafter(radius, neighbor):
    # These radii make the relative allowance an exactly representable power of two.
    allowance = radius * 1e-8
    end_radius = radius + allowance
    assert end_radius - radius == allowance < 1e-7
    if neighbor:
        end_radius = math.nextafter(end_radius, 0 if neighbor < 0 else math.inf)
    start, end = (radius, 0), (0, end_radius)
    if neighbor > 0:
        rejected((0, 0), start, end, code="unequal_arc_radii", equal=True)
    else:
        result = arc_geometry((0, 0), start, end, "ccw", require_equal_radii=True)
        assert result.start_radius == radius
        assert result.end_radius == end_radius
        assert abs(result.start_radius - result.end_radius) <= allowance
        assert result.start_radius != (result.start_radius + result.end_radius) / 2


@pytest.mark.parametrize("radius", [16.0, 100000.0])
@pytest.mark.parametrize("sign", [-1, 1])
def test_absolute_radial_limit_rejects_first_representable_outside_value(radius, sign):
    limit = 1e-7
    boundary = radius + sign * limit
    # An absolute allowance of 1e-7 cannot itself be the exact difference of these
    # two large doubles. Exercise the immediately adjacent accepted/rejected radii.
    inside = boundary
    if abs(inside - radius) > limit:
        inside = math.nextafter(inside, radius)
    outside = math.nextafter(inside, math.inf if sign > 0 else -math.inf)
    assert abs(inside - radius) <= limit < abs(outside - radius)
    result = arc_geometry((0, 0), (radius, 0), (0, inside), "ccw", require_equal_radii=True)
    assert result.start_radius == radius
    assert result.end_radius == inside
    rejected((0, 0), (radius, 0), (0, outside), code="unequal_arc_radii", equal=True)


def test_micrometre_geometry_cannot_use_the_absolute_residual_alone():
    radius, end_radius = 1e-6, 1e-6 + 1e-9
    assert end_radius - radius < 1e-7
    assert end_radius - radius > radius * 1e-8
    authored = arc_geometry((0, 0), (radius, 0), (0, end_radius), "ccw")
    assert authored.start_radius == radius and authored.end_radius == end_radius
    rejected((0, 0), (radius, 0), (0, end_radius), code="unequal_arc_radii", equal=True)


def test_authored_and_solved_geometry_never_repair_seeds_or_average_radii():
    center, start, end = (10, 20), (13, 20), (10, 24)
    result = arc_geometry(center, start, end, "ccw")
    assert (center, start, end) == ((10, 20), (13, 20), (10, 24))
    assert result.start_radius == 3 and result.end_radius == 4
    assert result.chord == 5 and result.sweep_radians == math.pi / 2
    rejected(center, start, end, code="unequal_arc_radii", equal=True)
    assert (center, start, end) == ((10, 20), (13, 20), (10, 24))


def test_far_origin_small_radius_uses_actual_subtraction_and_does_not_snap_to_limit():
    center = (1e6, 1e6)
    inward = 1e6 - 1e-6
    radius = 1e6 - inward
    assert radius > 1e-6
    result = arc_geometry(center, (inward, 1e6), (1e6, inward), "ccw", require_equal_radii=True)
    assert result.start_radius == result.end_radius == radius
    closer = math.nextafter(inward, 1e6)
    assert 1e6 - closer < 1e-6
    rejected(center, (closer, 1e6), (1e6, inward), code="invalid_number", equal=True)
    # One far-origin coordinate ULP is already larger than the permitted radial residual.
    farther = math.nextafter(inward, -math.inf)
    rejected(center, (inward, 1e6), (1e6, farther), code="unequal_arc_radii", equal=True)


def test_far_origin_chord_straddles_policy_at_neighboring_representable_coordinates():
    center, start = (999999, 999999), (999998, 999999)
    endpoint = 999999 - 1e-6
    assert 999999 - endpoint > 1e-6
    result = arc_geometry(center, start, (999998, endpoint), "ccw", require_equal_radii=True)
    assert result.chord == 999999 - endpoint
    closer = math.nextafter(endpoint, 999999)
    assert 999999 - closer < 1e-6
    rejected(center, start, (999998, closer), code="degenerate_arc", equal=True)


@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_explicit_endpoint_reversal_changes_radius_authority_without_averaging(direction):
    radius = 2**-28 / 1e-8
    end_radius = radius + radius * 1e-8
    start, end = (radius, 0), (0, end_radius)
    original = arc_geometry((0, 0), start, end, direction, require_equal_radii=True)
    reversed_record = arc_geometry(
        (0, 0), end, start, "cw" if direction == "ccw" else "ccw", require_equal_radii=True
    )
    assert reversed_record.sweep_radians == -original.sweep_radians
    assert reversed_record.start_radius == original.end_radius
    assert reversed_record.start_radius != original.start_radius


@pytest.mark.parametrize("role", [0, 1, 2])
@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        None,
        "1",
        [],
        {},
        math.nan,
        math.inf,
        -math.inf,
        pytest.param(10**1000, id="oversized-integer"),
    ],
)
def test_every_point_coordinate_rejects_bool_nonnumeric_and_nonfinite(role, value):
    points = [(0, 0), (1, 0), (0, 1)]
    points[role] = (value, points[role][1])
    rejected(*points, code="invalid_number")


@pytest.mark.parametrize("role", [0, 1, 2])
@pytest.mark.parametrize("point", [None, [], [0, 0], (0,), (0, 0, 0), {"u": 0, "v": 0}])
def test_point_shapes_are_strict_immutable_pairs(role, point):
    points = [(0, 0), (1, 0), (0, 1)]
    points[role] = point
    rejected(*points, code="invalid_arc")


@pytest.mark.parametrize("sign", [-1, 1])
def test_coordinate_boundaries_are_inclusive_and_nextafter_is_rejected(sign):
    center = (sign * 1e6, 0)
    start, end = (sign * (1e6 - 1), 0), (sign * 1e6, 1)
    result = arc_geometry(center, start, end, "ccw", require_equal_radii=True)
    assert result.start_radius == result.end_radius == 1
    outside = sign * math.nextafter(1e6, math.inf)
    rejected((outside, 0), start, end, code="invalid_number")
    rejected(center, (outside, 0), end, code="invalid_number")
    rejected(center, start, (outside, 1), code="invalid_number")


@pytest.mark.parametrize("direction", [None, True, 1, [], {}, "", "CCW", "CW", "ccw ", "clockwise"])
def test_direction_is_exact_and_never_coerced(direction):
    rejected((0, 0), (1, 0), (0, 1), direction, code="invalid_arc")


@pytest.mark.parametrize("policy", [None, 0, 1, "true", [], {}])
def test_equal_radius_policy_requires_actual_boolean(policy):
    with pytest.raises(ArcGeometryError) as error:
        arc_geometry((0, 0), (1, 0), (0, 1), "ccw", require_equal_radii=policy)
    assert error.value.code == "invalid_arc"


@pytest.mark.parametrize(
    "center,start,end,code",
    [
        ((0, 0), (0, 0), (1, 0), "invalid_number"),
        ((0, 0), (1, 0), (0, 0), "invalid_number"),
        ((0, 0), (1, 0), (1, 0), "degenerate_arc"),
    ],
)
def test_degenerate_endpoints_never_become_a_full_circle(center, start, end, code):
    rejected(center, start, end, code=code)
