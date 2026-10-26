"""Pure directed-arc numerical policy shared by model and geometry boundaries.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_ARC_COORDINATE_MM = 1e6
MIN_ARC_RADIUS_MM = 1e-6
MAX_ARC_RADIUS_MM = 1e6
MIN_ARC_CHORD_MM = 1e-6
MIN_ARC_SWEEP_RADIANS = 1e-8
MAX_ARC_RADIUS_RESIDUAL_MM = 1e-7
MAX_ARC_RADIUS_RELATIVE_RESIDUAL = 1e-8


class ArcGeometryError(ValueError):
    """Expected pure-policy failure, independent of model or native imports."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ArcGeometry:
    """Derived evidence; canonical start is the sole radius authority."""

    start_radius: float
    end_radius: float
    chord: float
    sweep_radians: float


def _point(value: tuple[float, float], label: str) -> tuple[float, float]:
    if type(value) is not tuple or len(value) != 2:
        raise ArcGeometryError("invalid_arc", f"Arc {label} must be a numeric 2-tuple")
    result = []
    for coordinate in value:
        if type(coordinate) not in (int, float):
            raise ArcGeometryError("invalid_number", f"Arc {label} coordinates must be numeric")
        try:
            number = float(coordinate)
        except (OverflowError, ValueError) as exc:
            raise ArcGeometryError(
                "invalid_number", f"Arc {label} coordinate is outside double range"
            ) from exc
        if not math.isfinite(number) or abs(number) > MAX_ARC_COORDINATE_MM:
            raise ArcGeometryError(
                "invalid_number", f"Arc {label} coordinate is outside the ±1e6 mm domain"
            )
        result.append(number)
    return result[0], result[1]


def arc_geometry(
    center: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    direction: str,
    *,
    require_equal_radii: bool = False,
) -> ArcGeometry:
    """Validate and measure one directed arc without repairing its input.

    Authored seeds may have unequal radii. Solved/output consumers must request
    the additional radial residual gate. All bounds are inclusive comparisons on
    computed doubles, without epsilon expansion, projection or radius averaging.
    """
    center, start, end = _point(center, "center"), _point(start, "start"), _point(end, "end")
    if type(direction) is not str or direction not in ("ccw", "cw"):
        raise ArcGeometryError("invalid_arc", "Arc direction must be exactly 'ccw' or 'cw'")
    if type(require_equal_radii) is not bool:
        raise ArcGeometryError("invalid_arc", "Arc equal-radius policy must be a boolean")
    su, sv = start[0] - center[0], start[1] - center[1]
    eu, ev = end[0] - center[0], end[1] - center[1]
    start_radius, end_radius = math.hypot(su, sv), math.hypot(eu, ev)
    if not (
        MIN_ARC_RADIUS_MM <= start_radius <= MAX_ARC_RADIUS_MM
        and MIN_ARC_RADIUS_MM <= end_radius <= MAX_ARC_RADIUS_MM
    ):
        raise ArcGeometryError("invalid_number", "Arc radii must be within 1e-6 to 1e6 mm")
    chord = math.hypot(end[0] - start[0], end[1] - start[1])
    if chord < MIN_ARC_CHORD_MM:
        raise ArcGeometryError("degenerate_arc", "Arc endpoint chord must be at least 1e-6 mm")
    sweep = math.atan2(su * ev - sv * eu, su * eu + sv * ev)
    if direction == "ccw" and sweep <= 0:
        sweep += math.tau
    elif direction == "cw" and sweep >= 0:
        sweep -= math.tau
    if abs(sweep) < MIN_ARC_SWEEP_RADIANS or math.tau - abs(sweep) < MIN_ARC_SWEEP_RADIANS:
        raise ArcGeometryError(
            "degenerate_arc", "Arc sweep must be at least 1e-8 radians from zero and a full turn"
        )
    residual_limit = min(
        MAX_ARC_RADIUS_RESIDUAL_MM, MAX_ARC_RADIUS_RELATIVE_RESIDUAL * start_radius
    )
    if require_equal_radii and abs(start_radius - end_radius) > residual_limit:
        raise ArcGeometryError(
            "unequal_arc_radii", "Arc solved radii exceed the absolute/relative residual limit"
        )
    return ArcGeometry(start_radius, end_radius, chord, sweep)
