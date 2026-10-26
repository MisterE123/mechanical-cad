"""Pure, bounded unshifted external gear design and legacy polygon reference.

Lengths are mm; pressure angle is degrees; clearance is a module multiplier.
Original implementation from published formulae, not copied gear-generator code.
See docs/SPUR_GEARS.md for geometry, error bound and manufacturing limitations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import CADException

MAX_PROFILE_POINTS = 6000


@dataclass(frozen=True)
class GearSpec:
    module: float
    tooth_count: int
    thickness: float
    pressure_angle: float
    bore_diameter: float
    backlash: float
    clearance: float
    profile_tolerance: float
    pitch_radius: float
    base_radius: float
    root_radius: float
    tip_radius: float
    min_tooth_count: int
    half_tooth_angle: float
    base_half_angle: float
    root_half_angle: float
    tip_half_angle: float
    start_parameter: float
    end_parameter: float


def gear_spec(
    *,
    module,
    tooth_count,
    thickness,
    pressure_angle=20,
    bore_diameter=0,
    backlash=0.1,
    clearance=0.25,
    profile_tolerance=0.01,
) -> GearSpec:
    """Validate numerical parameters, rejecting rather than correcting designs."""
    values = locals().copy()
    for name, value in values.items():
        if type(value) not in (int, float) or not math.isfinite(value):
            raise CADException("invalid_gear", f"{name} must be a finite number.")
    if not 0.1 <= module <= 100:
        raise CADException("invalid_gear", "Module must be between 0.1 and 100 mm.")
    if not 14.5 <= pressure_angle <= 30:
        raise CADException("invalid_gear", "Pressure angle must be between 14.5 and 30 degrees.")
    alpha = math.radians(pressure_angle)
    minimum = math.ceil(2 / math.sin(alpha) ** 2 - 1e-12)
    if tooth_count != int(tooth_count) or not minimum <= tooth_count <= 200:
        raise CADException(
            "invalid_gear",
            f"Tooth count must be an integer from {minimum} to 200; undercut/profile shift is unsupported.",
        )
    if not 0.1 <= thickness <= 1000:
        raise CADException("invalid_gear", "Thickness must be between 0.1 and 1000 mm.")
    if not 0 <= clearance <= 0.5:
        raise CADException("invalid_gear", "Clearance must be between 0 and 0.5 times module.")
    if not 0 <= backlash <= 0.5 * module:
        raise CADException(
            "invalid_gear",
            "Per-gear pitch tooth-thickness reduction must be between 0 and 0.5 times module.",
        )
    if not 0.0001 <= profile_tolerance <= min(0.1, 0.05 * module):
        raise CADException(
            "invalid_gear",
            "Profile tolerance must be >= 0.0001 mm and <= min(0.1 mm, 0.05 * module).",
        )
    z = int(tooth_count)
    rp = module * z / 2
    rb = rp * math.cos(alpha)
    rr = rp - module * (1 + clearance)
    ra = rp + module
    # Retain at least one module of radial material, with allowance for inward
    # polygon approximation. This is a geometry guard, not a strength rating.
    if not 0 <= bore_diameter <= 2 * (rr - module - profile_tolerance):
        raise CADException(
            "invalid_gear",
            "Bore must leave at least one module of radial material inside the approximated root.",
        )
    half = (math.pi * module / 2 - backlash) / (2 * rp)
    base_half = half + math.tan(alpha) - alpha
    t0 = math.sqrt(max(0, (rr / rb) ** 2 - 1))
    t1 = math.sqrt((ra / rb) ** 2 - 1)
    root_half = base_half - (t0 - math.atan(t0))
    tip_half = base_half - (t1 - math.atan(t1))
    if not 0 < tip_half < root_half < math.pi / z:
        raise CADException(
            "invalid_gear", "Tooth flanks overlap, have no root gap, or have a pointed tip."
        )
    if 2 * ra * math.sin(tip_half) <= 4 * profile_tolerance:
        raise CADException(
            "invalid_gear", "Tooth tip is too thin for the requested profile tolerance."
        )
    spec = GearSpec(
        module,
        z,
        thickness,
        pressure_angle,
        bore_diameter,
        backlash,
        clearance,
        profile_tolerance,
        rp,
        rb,
        rr,
        ra,
        minimum,
        half,
        base_half,
        root_half,
        tip_half,
        t0,
        t1,
    )
    # Retain the original conservative polygon-work preflight for compatibility.
    # The native curved path also checks its own edge count before construction.
    nf, nt, nr = _segment_counts(spec)
    if z * (2 * nf + nt + nr + 2) > MAX_PROFILE_POINTS:
        raise CADException(
            "gear_complexity_limit",
            "Gear profile exceeds 6000 segments; increase profile tolerance or reduce tooth count/size.",
        )
    return spec


def _segment_counts(s):
    # Vector linear interpolation error <= max||f''|| * delta^2 / 8.
    # Involute f(t)=rb*(cos(t)+t*sin(t),sin(t)-t*cos(t));
    # ||f''||=rb*sqrt(1+t*t). Rotation/reflection preserve the bound.
    nf = max(
        1,
        math.ceil(
            (s.end_parameter - s.start_parameter)
            * math.sqrt(
                s.base_radius * math.sqrt(1 + s.end_parameter**2) / (8 * s.profile_tolerance)
            )
        ),
    )
    nt = max(
        1, math.ceil(2 * s.tip_half_angle * math.sqrt(s.tip_radius / (8 * s.profile_tolerance)))
    )
    nr = max(
        1,
        math.ceil(
            (2 * math.pi / s.tooth_count - 2 * s.root_half_angle)
            * math.sqrt(s.root_radius / (8 * s.profile_tolerance))
        ),
    )
    return nf, nt, nr


def profile_points(spec: GearSpec) -> tuple[tuple[float, float], ...]:
    """CCW simple polygon, tooth zero on +X, without a duplicate closing point.

    Involute, tip and root chords meet the requested absolute positional bound.
    Straight radial extensions below the base circle are intentional, not a
    generated trochoidal root fillet. Angular monotonicity proves no crossings.
    """
    s = spec
    nf, nt, nr = _segment_counts(s)
    points = []

    def polar(r, a):
        p = (r * math.cos(a), r * math.sin(a))
        if not points or math.dist(points[-1], p) > 1e-9:
            points.append(p)

    for tooth in range(s.tooth_count):
        center = 2 * math.pi * tooth / s.tooth_count
        polar(s.root_radius, center - s.root_half_angle)
        for i in range(nf + 1):
            t = s.start_parameter + (s.end_parameter - s.start_parameter) * i / nf
            half = s.base_half_angle - (t - math.atan(t))
            polar(s.base_radius * math.sqrt(1 + t * t), center - half)
        for i in range(1, nt + 1):
            polar(s.tip_radius, center - s.tip_half_angle + 2 * s.tip_half_angle * i / nt)
        for i in range(1, nf + 1):
            t = s.end_parameter - (s.end_parameter - s.start_parameter) * i / nf
            half = s.base_half_angle - (t - math.atan(t))
            polar(s.base_radius * math.sqrt(1 + t * t), center + half)
        polar(s.root_radius, center + s.root_half_angle)
        gap = 2 * math.pi / s.tooth_count - 2 * s.root_half_angle
        for i in range(1, nr):
            polar(s.root_radius, center + s.root_half_angle + gap * i / nr)
    return tuple(points)
