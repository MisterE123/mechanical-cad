"""Genuine schema-3 profile adapter, independent of OCCT and replay imports.

The only schema view is the reviewed geometry-only arc-empty legacy view. It is
never solved, serialized, fingerprinted, returned, or offered as source evidence.
Native calls consume the original solved Sketch and freshly certify it themselves.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .analytic_profile import (
    AnalyticOpenPath,
    AnalyticRegions,
    classify_analytic_path,
    classify_analytic_profile,
)
from .analytic_profile_geometry import is_sector_form
from .arc_profile_sector import classify_sector
from .errors import CADException
from .outputs import AvailableProfile, OpenProfile, SketchOutput
from .profile_region import CircleProfile, OpenChainProfile, ProfileRegions, classify_profile
from .sketch_evaluation import evaluate_sketch
from .sketch_model import validate
from .sketch_service import PROFILE_ERRORS

BACKEND_CAPABILITIES = frozenset({"mcad.sketch-arcs/1"})
SECTOR_PROFILE_ERRORS = frozenset(
    {
        "unsupported_profile_form",
        "unsupported_profile_coincidence",
        "unsupported_profile_scale",
        "unsupported_profile_sweep",
        "unsupported_profile_nontransverse",
        "unsupported_profile_contact",
        "unsupported_endpoint_discrepancy",
        "unsupported_endpoint_incidence",
        "numerically_ambiguous_profile",
    }
)
_DIAGNOSTIC = re.compile(r"[a-z][a-z0-9_]{0,95}\Z", re.ASCII)


def classify_profile_v3(sketch):
    """Validate real numeric source, then classify the exact authored geometry."""
    validate(sketch)
    if sketch.schema_version != 3:
        return classify_profile(sketch)
    if not any(not getattr(arc, "construction", False) for arc in sketch.arcs):
        return classify_profile(replace(sketch, schema_version=2))
    if not is_sector_form(sketch.to_dict()):
        try:
            return classify_analytic_path(sketch)
        except CADException:
            return classify_analytic_profile(sketch)
    result = classify_sector(sketch)
    if result.status == "certified_sector":
        return result
    if result.status == "numerical_ambiguity":
        raise CADException(
            "numerically_ambiguous_profile",
            f"Sector readiness is unresolved at {result.stage}: {result.code}.",
        )
    if result.status == "unsupported" and result.code in SECTOR_PROFILE_ERRORS:
        raise CADException(result.code, f"Unsupported sector at {result.stage}: {result.code}.")
    raise CADException("invalid_profile", "The sector classifier did not produce a region.")


def profile_check_v3(sketch) -> dict:
    """Pure readiness only; arbitrary valid workplanes can be pure-ready."""
    try:
        region = classify_profile_v3(sketch)
        if isinstance(region, (OpenChainProfile, AnalyticOpenPath)):
            return {
                "ready": False,
                "error": {"code": region.reason_code, "message": region.message},
            }
    except CADException as exc:
        if exc.code not in PROFILE_ERRORS | SECTOR_PROFILE_ERRORS:
            raise
        return {"ready": False, "error": exc.to_dict()}
    return {"ready": True, "error": None}


def sector_native_call(operation, *args):
    """Keep only the qualified sector adapter's bounded diagnostic codes.

    Ordinary kernel exceptions, malformed codes and unrelated coded exceptions
    retain the existing replay exception path. No native module is imported here.
    """
    try:
        return operation(*args)
    except Exception as exc:
        if (
            type(exc).__module__ == f"{__package__}.kernel_ocp"
            and type(exc).__name__ == "_CurveProfileError"
        ):
            code = exc.__dict__.get("code")
            if type(code) is str and _DIAGNOSTIC.fullmatch(code):
                raise CADException(code, f"Sector construction failed: {code}.") from exc
        raise


def sketch_output_v3(feature, values, kernel, item, *, legacy_output):
    """One exact-v3 replay adapter; old schemas delegate on their original data."""
    if feature.sketch.schema_version in (1, 2):
        return legacy_output(feature, values, kernel, item)
    report, item["sketch"] = evaluate_sketch(feature.sketch, values)
    if not report.success:
        detail = (
            "Diagnostic candidates (not proven causes): " + ", ".join(report.failed_constraints)
            if report.failed_constraints
            else "Inspect the sketch relations and seed geometry."
        )
        raise CADException(
            "sketch_solve_failed", f"{feature.id}: {report.status.name.lower()}. {detail}"
        )
    if any(
        not getattr(arc, "construction", False) for arc in report.sketch.arcs
    ) and is_sector_form(report.sketch.to_dict()):
        # sector_profile owns fresh classification and the native continuation in
        # its single retained context. Do not run a second full classification.
        shape = sector_native_call(kernel.sector_profile, report.sketch)
        boundary = tuple(line.id for line in report.sketch.lines) + tuple(
            arc.id for arc in report.sketch.arcs
        )
        return SketchOutput(report.sketch, AvailableProfile(shape, "curve_loop", boundary))
    region = classify_profile_v3(report.sketch)
    if isinstance(region, (OpenChainProfile, AnalyticOpenPath)):
        return SketchOutput(report.sketch, OpenProfile(region.reason_code, region.message))
    if isinstance(region, AnalyticRegions):
        shape = kernel.analytic_region_profile(
            region.regions,
            origin=report.sketch.plane.origin,
            quaternion=report.sketch.plane.quaternion,
        )
        return SketchOutput(
            report.sketch, AvailableProfile(shape, "analytic_regions", region.boundary_ids)
        )
    if isinstance(region, ProfileRegions):
        shape = kernel.region_profile(
            region.regions,
            origin=report.sketch.plane.origin,
            quaternion=report.sketch.plane.quaternion,
        )
        return SketchOutput(report.sketch, AvailableProfile(shape, "regions", region.boundary_ids))
    if isinstance(region, CircleProfile):
        shape = kernel.circle_profile(
            region.center,
            region.radius,
            region.circle_id,
            origin=report.sketch.plane.origin,
            quaternion=report.sketch.plane.quaternion,
        )
        return SketchOutput(report.sketch, AvailableProfile(shape, "circle", (region.circle_id,)))
    shape = kernel.polygon(
        region.points,
        region.edge_ids,
        origin=report.sketch.plane.origin,
        quaternion=report.sketch.plane.quaternion,
    )
    return SketchOutput(report.sketch, AvailableProfile(shape, "line_loop", region.edge_ids))
