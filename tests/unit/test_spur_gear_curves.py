"""Vector error, pitch anchoring and monotone control hulls of curved gears."""

import math

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.spur_gear import gear_spec
from mechanical_cad.spur_gear_curves import flank_spans, involute


def bezier(poles, u):
    weights = ((1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u**2 * (1 - u), u**3)
    return tuple(math.fsum(w * p[k] for w, p in zip(weights, poles, strict=True)) for k in (0, 1))


@pytest.mark.parametrize("module", [0.1, 2, 100])
@pytest.mark.parametrize("angle,z", [(14.5, 32), (20, 18), (20, 19), (20, 200), (30, 8), (30, 200)])
@pytest.mark.parametrize("tolerance", [0.0001, 0.01])
def test_dense_vector_error_is_bounded_and_control_hulls_are_simple(module, angle, z, tolerance):
    try:
        s = gear_spec(
            module=module,
            tooth_count=z,
            thickness=8,
            pressure_angle=angle,
            profile_tolerance=min(tolerance, 0.001 * module),
            backlash=0,
            clearance=0.25,
        )
    except CADException as exc:
        assert exc.code == "gear_complexity_limit"
        pytest.skip("Design exceeds the preserved legacy profile complexity bound")
    spans = flank_spans(s)
    assert spans[0].start == s.start_parameter and spans[-1].end == s.end_parameter
    assert all(a.end == b.start for a, b in zip(spans, spans[1:], strict=False))
    for span in spans:
        maximum = s.base_radius * math.sqrt(9 + span.end**2)
        assert span.error_bound == maximum * (span.end - span.start) ** 4 / 384
        assert span.error_bound <= min(s.profile_tolerance, 1e-6)
        for i in range(101):
            u = i / 100
            nominal = involute(s.base_radius, span.start + u * (span.end - span.start))
            error = math.dist(bezier(span.poles, u), nominal)
            assert error <= span.error_bound * (1 + 1e-7) + 64 * math.ulp(s.tip_radius)
        angles = [math.atan2(y, x) for x, y in span.poles]
        radii = [math.hypot(x, y) for x, y in span.poles]
        assert angles == sorted(angles) and radii == sorted(radii)
        assert math.hypot(*span.poles[0]) >= s.root_radius - 64 * math.ulp(s.tip_radius)
        assert math.hypot(*span.poles[-1]) <= s.tip_radius + 64 * math.ulp(s.tip_radius)


@pytest.mark.parametrize("backlash", [0, 1e-5, 0.05, 0.1, 0.8])
def test_pitch_anchor_preserves_editable_tooth_thickness_and_refines_small_backlash(backlash):
    s = gear_spec(module=2, tooth_count=20, thickness=8, backlash=backlash)
    spans = flank_spans(s)
    pitch = math.tan(math.radians(s.pressure_angle))
    endpoint = next(span.poles[-1] for span in spans if span.end == pitch)
    half_angle = s.base_half_angle - math.atan2(endpoint[1], endpoint[0])
    assert math.hypot(*endpoint) == pytest.approx(s.pitch_radius, abs=1e-12)
    assert 2 * s.pitch_radius * half_angle == pytest.approx(math.pi * s.module / 2 - backlash)
    assert max(span.error_bound for span in spans) <= min(
        s.profile_tolerance, max(1e-6, backlash / 10)
    )


def test_hermite_vector_peano_kernel_is_nonnegative_and_has_the_stated_mass():
    # Independent quadrature of the two polynomial branches. A scalar
    # mean-value remainder alone would not justify a shared vector norm bound.
    nodes = (0.06943184420297371, 0.33000947820757187, 0.6699905217924281, 0.9305681557970262)
    weights = (0.17392742256872692, 0.32607257743127307, 0.32607257743127307, 0.17392742256872692)
    for x in (0.01, 0.17, 0.5, 0.83, 0.99):

        def kernel(s, x=x):
            if s <= x:
                return s**2 * (1 - x) ** 2 * (3 * x - (1 + 2 * x) * s) / 6
            return x**2 * (1 - s) ** 2 * ((3 - 2 * x) * s - x) / 6

        assert min(kernel(i / 100) for i in range(101)) >= 0
        integral = 0
        for a, b in ((0, x), (x, 1)):
            integral += (b - a) * sum(
                w * kernel(a + (b - a) * u) for w, u in zip(weights, nodes, strict=True)
            )
        assert integral == pytest.approx(x**2 * (1 - x) ** 2 / 24, rel=1e-13)
        assert integral <= 1 / 384


def test_original_invalid_tip_and_bore_guards_remain_active():
    with pytest.raises(CADException):
        gear_spec(
            module=2, tooth_count=8, thickness=8, pressure_angle=30, backlash=1, clearance=0.5
        )
    with pytest.raises(CADException):
        gear_spec(module=2, tooth_count=20, thickness=8, bore_diameter=32)
