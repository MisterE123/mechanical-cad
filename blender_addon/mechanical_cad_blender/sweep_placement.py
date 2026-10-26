"""Explicit versioned automatic Sweep placement, not persistent face identity.

Version 1 centers the section's filled-area centroid at the first path endpoint,
aligns its authored +U with the path workplane normal, and its normal with the
initial path tangent. Positive roll turns +U toward +V about that tangent.
Reverse traverses from the other endpoint. Omission preserves authored placement.
"""

import math
from collections.abc import Mapping


def validate_placement(placement):
    if not isinstance(placement, Mapping) or set(placement) != {
        "version",
        "mode",
        "reverse",
        "roll_degrees",
    }:
        raise ValueError("Sweep placement needs version, mode, reverse and roll_degrees.")
    if type(placement["version"]) is not int or placement["version"] != 1:
        raise ValueError("Unsupported Sweep placement version.")
    if placement["mode"] != "path_start_centroid":
        raise ValueError("Unsupported Sweep placement mode.")
    if type(placement["reverse"]) is not bool:
        raise ValueError("Sweep reverse must be a boolean path traversal choice.")
    roll = placement["roll_degrees"]
    if type(roll) not in (int, float) or abs(roll) > 360 or not math.isfinite(roll):
        raise ValueError("Sweep roll must be a finite literal angle from -360 to 360 degrees.")
