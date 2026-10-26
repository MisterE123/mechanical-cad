"""One-time literal workplane translation; no topology or parameter association."""

import copy
import math

from .general_view_geometry import Workplane
from .unit_input import normalize_unit_input


def fixed_sketch(document, identifier):
    matches = [f for f in document["features"] if f["id"] == identifier]
    if len(matches) != 1 or matches[0].get("kind") != "sketch_constrained":
        raise ValueError("Choose a saved unlinked constrained sketch.")
    feature = matches[0]
    if (
        feature.get("inputs")
        or "support_face" in feature
        or "support_intent" in feature
        or feature.get("projections")
    ):
        raise ValueError("Attached sketches and linked projections cannot use a fixed plane offset.")
    Workplane.from_saved(feature["sketch"]["plane"])
    return feature


def offset_candidate(document, identifier, text):
    """Return a detached candidate, retaining all untouched canonical values."""
    original = fixed_sketch(document, identifier)
    try:
        distance = float(normalize_unit_input(text, "length"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Enter one signed literal length, not a formula or parameter.") from exc
    if not math.isfinite(distance) or abs(distance) > 1e6:
        raise ValueError("Offset must be finite and within ±1000000 mm.")
    candidate = copy.deepcopy(document)
    if distance == 0:
        return candidate  # Even integer types and signed zeros remain untouched.
    frame = Workplane.from_saved(original["sketch"]["plane"])
    plane = fixed_sketch(candidate, identifier)["sketch"]["plane"]
    plane["origin"] = [
        math.fsum((origin, distance * normal))
        for origin, normal in zip(frame.origin_mm, frame.normal, strict=True)
    ]
    Workplane.from_saved(plane)  # Range check before replay/publication.
    return candidate
