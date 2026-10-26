"""Explicit data-only result-3 admission; canonical models remain unchanged."""

from __future__ import annotations

from .errors import CADException
from .expressions import evaluate, resolve_parameters
from .model import Document


def validate_result_version_v3(document: Document, result_version: int) -> None:
    """Select this policy explicitly, without weakening the legacy result policy."""
    if type(result_version) is not int or result_version != 3:
        raise CADException("unsupported_result_version", "This service requires result_version 3.")
    if not isinstance(document, Document):
        raise CADException("invalid_document", "Expected a canonical Document snapshot.")
    document.validate()


def validate_replay_v3(document: Document, result_version: int) -> None:
    """Bound arc-containing replay before solving, importing OCCT or constructing.

    Solve-only uses the version check above. It neither invents an extrusion
    height nor rejects a selected sketch because of unrelated downstream intent.
    """
    validate_result_version_v3(document, result_version)
    from .analytic_profile_geometry import is_sector_form

    arc_features = [
        feature
        for feature in document.features
        if feature.sketch is not None
        and feature.sketch.arcs
        and is_sector_form(feature.sketch.to_dict())
    ]
    sector_ids = {feature.id for feature in arc_features}
    for extrusion in document.features:
        if extrusion.kind != "extrude" or extrusion.inputs.get("profile") not in sector_ids:
            continue
        height = evaluate(extrusion.params["length"], resolve_parameters(document.parameters))
        if not 1 <= height <= 1000:
            raise CADException(
                "unsupported_profile_scale",
                f"{extrusion.id}.length must be between 1 and 1000 mm for a sector.",
            )
