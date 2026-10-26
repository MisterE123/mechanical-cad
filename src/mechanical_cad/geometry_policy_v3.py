"""Source admission for schema-3 Part geometry; replay owns shape evidence."""

from .errors import CADException
from .model import Document, output_type
from .result_policy_v3 import validate_replay_v3


def validate_geometry_v3(document: Document, result_version: int) -> None:
    """Admit typed feature DAGs, never infer a valid solid from source alone."""
    validate_replay_v3(document, result_version)
    if document.active_feature is None:
        raise CADException(
            "missing_active_feature", "Choose an active solid before checking or exporting."
        )
    active = next(feature for feature in document.features if feature.id == document.active_feature)
    if output_type(active.kind) != "solid":
        raise CADException(
            "not_a_solid", "Geometry checks and export require a selected solid feature."
        )
