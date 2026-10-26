"""Pinned historical inputs, independent of the evolving working source tree."""

import hashlib
from pathlib import Path

SOURCE_COMMIT = "69d0f8164e73bfbbcdf0c48d6546f97803d12f58"
SOURCE = Path(__file__).resolve().parents[1] / "fixtures/geometry_v3/source_69d0f81"
# Existing INTEGRATION_SOURCE_ORIGINALS pins, not newly generated expectations.
EXPECTED = {
    "sidecar": (10301, "ae6180f7ff15efe54cb8a50db1e80349a58f940f7a00d3aa51dcd0c1e12d91e3"),
    "actions": (8172, "e85b03a54aefb171100252a8a6aa57f00cf0705b84d7e2005918a2dcef2c1649"),
}


def historical_geometry_source(name, *, root=SOURCE):
    """Read only an allowlisted, exact historical source file; fail on mutation."""
    size, digest = EXPECTED[name]
    raw = (root / f"{name}.py.txt").read_bytes()
    assert len(raw) == size
    assert hashlib.sha256(raw).hexdigest() == digest
    return raw
