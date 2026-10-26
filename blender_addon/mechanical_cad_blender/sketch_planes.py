"""Explicit principal datum planes; all lengths are canonical millimetres.

These are literal workplanes, not associative references to tessellated faces.
XZ uses +X/+Z local axes, hence its positive extrusion normal is -Y.
"""

import math


def principal_plane(kind="XY", offset=0.0):
    if kind not in {"XY", "XZ", "YZ"}:
        raise ValueError("Choose an XY, XZ or YZ sketch plane.")
    if type(offset) not in (int, float) or not math.isfinite(offset) or abs(offset) > 1e6:
        raise ValueError("Plane offset must be a finite millimetre value within ±1000000.")
    half = math.sqrt(0.5)
    quaternion, normal = {
        "XY": ([1, 0, 0, 0], (0, 0, 1)),
        "XZ": ([half, half, 0, 0], (0, -1, 0)),
        "YZ": ([0.5, 0.5, 0.5, 0.5], (1, 0, 0)),
    }[kind]
    return {
        "id": kind.lower(),
        "origin": [float(offset) * value for value in normal],
        "quaternion": quaternion,
    }
