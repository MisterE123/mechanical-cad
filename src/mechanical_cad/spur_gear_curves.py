"""Tolerance-bounded cubic Hermite involute flanks, without native imports.

The canonical gear parameters and sharp radial roots remain unchanged. See
docs/SPUR_GEARS.md for the vector remainder proof and approximation limits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import CADException
from .spur_gear import GearSpec


@dataclass(frozen=True)
class FlankSpan:
    start: float
    end: float
    poles: tuple[tuple[float, float], ...]
    error_bound: float


def involute(radius: float, t: float) -> tuple[float, float]:
    return radius * (math.cos(t) + t * math.sin(t)), radius * (math.sin(t) - t * math.cos(t))


def _span(radius: float, a: float, b: float) -> FlankSpan:
    p, q = involute(radius, a), involute(radius, b)
    h = b - a
    poles = (
        p,
        (p[0] + h * radius * a * math.cos(a) / 3, p[1] + h * radius * a * math.sin(a) / 3),
        (q[0] - h * radius * b * math.cos(b) / 3, q[1] - h * radius * b * math.sin(b) / 3),
        q,
    )
    # A positive Bernstein combination stays within the control-point cone.
    # Ordered polar angles and increasing positive X/Y prove that the flank
    # turns forward, increases radius, and cannot cross itself or a tooth sector.
    # Reject a failed proof rather than accepting an arbitrary fitted spline.
    if not (0 <= a < b < math.pi / 2):
        raise CADException("invalid_gear", "Involute parameter interval is unsupported.")
    for i, left in enumerate(poles):
        if any(not math.isfinite(v) or v < 0 for v in left):
            raise CADException("invalid_gear", "Involute control polygon is invalid.")
        for right in poles[i + 1 :]:
            if right[0] < left[0] or right[1] < left[1] or left[0] * right[1] < left[1] * right[0]:
                raise CADException("invalid_gear", "Involute control polygon is not monotone.")
    bound = radius * math.sqrt(9 + b * b) * h**4 / 384
    return FlankSpan(a, b, poles, bound)


def flank_spans(spec: GearSpec) -> tuple[FlankSpan, ...]:
    """One canonical flank before rotation/reflection, base/root through tip.

    Include the pitch circle exactly so editing backlash changes the authored
    pitch tooth thickness without a sampling-dependent pitch-circle error.
    On [a,b], ||f''''|| <= rb*sqrt(9+b*b). Cubic Hermite's positive Peano
    kernel gives a vector positional error <= M*(b-a)^4/384, not a separate
    per-coordinate tolerance or an empirical dense-sample error estimate.
    """
    # Near nominal contact, interpolation error can dominate a tiny backlash.
    # Refine, never loosen, the authored upper bound. The 1e-6 mm accuracy budget
    # remains subject to native tolerances, not a continuous contact guarantee.
    tolerance = min(spec.profile_tolerance, max(1e-6, spec.backlash / 10))
    pitch = math.tan(math.radians(spec.pressure_angle))
    breaks = (spec.start_parameter, pitch, spec.end_parameter)
    spans = []
    for a, b in zip(breaks, breaks[1:], strict=False):
        maximum = spec.base_radius * math.sqrt(9 + b * b)
        count = max(1, math.ceil((b - a) * (maximum / (384 * tolerance)) ** 0.25))
        # Recheck the bound after floating-point subdivision, before native work.
        while True:
            # Reuse each knot and force both authored endpoints exactly. In
            # particular, arithmetic roundoff must not leave a gap at pitch.
            knots = [a, *(a + (b - a) * i / count for i in range(1, count)), b]
            candidates = [
                _span(spec.base_radius, left, right)
                for left, right in zip(knots, knots[1:], strict=False)
            ]
            if all(span.error_bound <= tolerance for span in candidates):
                spans.extend(candidates)
                break
            count += 1
    edges = spec.tooth_count * (2 * len(spans) + 2 + 2 * (spec.root_radius < spec.base_radius))
    if edges > 6000:
        raise CADException("gear_complexity_limit", "Curved gear profile exceeds 6000 edges.")
    return tuple(spans)
