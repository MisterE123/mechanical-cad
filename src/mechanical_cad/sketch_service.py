"""Authored-sketch solving, with exact upstream replay for face attachments.

Successful solving and availability of a supported profile are independent.
Independent sketches remain kernel-free. Attached sketches resolve only their
support ancestry; native handles never enter returned evidence. This service
never writes a document, commits a draft, or exports geometry.
"""

from __future__ import annotations

from .errors import CADException
from .expressions import resolve_parameters
from .model import Document, check_persisted_document_budget
from .profile_region import OpenChainProfile, classify_profile
from .result_policy import validate_result_version
from .sketch_evaluation import evaluate_sketch

# Only deliberate profile-policy failures become a separate readiness result.
# Unexpected exceptions retain their failure instead of becoming an open sketch.
PROFILE_ERRORS = frozenset(
    {
        "open_profile",
        "invalid_profile",
        "degenerate_profile",
        "self_intersecting_profile",
        "unresolved_coincidence",
        "branched_profile",
        "mixed_profile_regions",
        "multiple_profile_regions",
    }
)


def profile_check(solved_sketch) -> dict:
    """Pure boundary readiness, explicitly not kernel validity or exportability."""
    try:
        region = classify_profile(solved_sketch)
        if isinstance(region, OpenChainProfile):
            return {
                "ready": False,
                "error": {"code": region.reason_code, "message": region.message},
            }
    except CADException as exc:
        if exc.code not in PROFILE_ERRORS:
            raise
        return {"ready": False, "error": exc.to_dict()}
    return {"ready": True, "error": None}


def solve_sketch(document: Document, feature_id: str) -> dict:
    """Evaluate one selected sketch without replaying downstream features.

    The detached candidate contains the authoritative parameter expressions. Native
    seed changes stay in the returned evidence, never in that candidate snapshot.
    """
    if not isinstance(document, Document):
        raise CADException("invalid_document", "Expected a canonical Document snapshot.")
    document.validate()
    # Core record/solver support can precede the matching profile/result schema.
    # Never publish newer embedded semantics through the existing v2 envelope.
    validate_result_version(document, 2)
    # The new action's bounded sketch payload policy applies even when the
    # selected candidate contains legacy embedded-v1 sketches. Legacy replay
    # and from_dict acceptance deliberately remain unchanged.
    for candidate in document.features:
        if candidate.sketch is not None:
            candidate.sketch.to_json()
    check_persisted_document_budget(document.to_dict())
    if type(feature_id) is not str or not feature_id:
        raise CADException("invalid_feature", "Select one constrained sketch feature ID.")
    feature = next((item for item in document.features if item.id == feature_id), None)
    if feature is None:
        raise CADException("missing_feature", "The selected sketch feature does not exist.")
    if feature.kind != "sketch_constrained":
        raise CADException("invalid_feature", "Solve Sketch requires a constrained sketch.")
    # Establish persistable canonical identity before invoking any native solve.
    # A compact input may expand under the canonical indented serializer.
    document_hash = document.content_hash
    support_context = None
    if feature.support_face is not None or feature.projections:
        from .sketch_support import prepare_solve_support

        feature, support_context = prepare_solve_support(document, feature, 2)
    values = resolve_parameters(document.parameters)
    report, evidence = evaluate_sketch(feature.sketch, values)
    result = {
        "document_id": document.id,
        "document_hash": document_hash,
        "feature_id": feature.id,
        "sketch": evidence,
        "profile_check": profile_check(report.sketch) if report.success else None,
    }
    if support_context is not None:
        result["support_context"] = support_context
    error = None
    if not report.success:
        error = {
            "code": "sketch_solve_failed",
            "message": (
                f"{feature.id}: {report.status.name.lower()}. Diagnostic constraint IDs are "
                "candidates for inspection, not proven causes. Keep the draft to correct it."
            ),
        }
    return {"ok": report.success, "result": result, "error": error}
