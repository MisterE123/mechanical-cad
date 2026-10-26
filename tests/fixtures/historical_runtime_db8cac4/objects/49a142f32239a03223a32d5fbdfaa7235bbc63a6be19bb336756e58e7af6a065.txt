"""Strict detached native observations; no record grants native authority.

Field equality transfers the freshly checked mathematical equation bounds.
Evaluated endpoints, validity and masses are separate empirical observations.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields

from .arc_profile_intervals import IntervalContext
from .arc_profile_native_plan import NativeActualSupport, NativePlan, _number, _require, transform
from .arc_profile_primitives import Dyadic, DyadicInterval, PrimitiveContext


@dataclass(frozen=True, slots=True)
class NativeMassCheck:
    area: float
    height: float | None
    volume: float | None
    area_allowance: DyadicInterval
    volume_allowance: DyadicInterval | None
    consistency_allowance: DyadicInterval | None
    area_distance: Dyadic
    volume_distance: Dyadic | None
    consistency_residual: Dyadic | None


def _keys(record, names):
    _require(type(record) is dict and len(record) == len(names), "native_evidence_incomplete")
    _require(all(type(key) is str for key in record), "native_evidence_incomplete")
    _require(set(record) == set(names), "native_evidence_incomplete")


def _finite(value):
    _require(type(value) is float and math.isfinite(value), "invalid_native_observation")


def _vector(value, count):
    _require(type(value) is tuple and len(value) == count, "invalid_native_observation")
    for component in value:
        _finite(component)


def _yes(value, code):
    _require(type(value) is bool and value, code)


def _validate_curve_fields(plan: NativePlan, role: str, record: dict, *, dimensions, initial):
    """Strict coefficients; initial support inspection never establishes acceptance."""
    _require(type(plan) is NativePlan, "invalid_native_plan")
    if not initial:
        _require(type(plan.accepted_support) is NativeActualSupport, "unproved_native_support")
        _require(
            all(
                hasattr(plan.accepted_support, field.name) for field in fields(NativeActualSupport)
            ),
            "invalid_native_support_record",
        )
    _require(type(dimensions) is int and dimensions in (2, 3), "invalid_native_observation")
    _require(type(role) is str and 1 <= len(role) <= 300, "native_identity_changed")
    _keys(
        record,
        (
            "kind",
            "location",
            "direction",
            "u",
            "v",
            "normal",
            "radius",
            "range",
            "identity_location",
        ),
    )
    _yes(record["identity_location"], "native_location_changed")
    _vector(record["location"], dimensions)
    _vector(record["range"], 2)
    arc = plan.source.incidence.arc
    if role == f"arc.{arc.id}":
        expected = {
            "kind": "circle",
            "location": transform(plan.frame, plan.center) if dimensions == 3 else plan.center,
            "direction": None,
            "u": plan.frame.u if dimensions == 3 else (1.0, 0.0),
            "v": plan.frame.v if dimensions == 3 else (0.0, 1.0),
            "normal": plan.frame.normal if dimensions == 3 else None,
            "radius": plan.radius,
            "range": plan.increasing_parameters,
            "identity_location": True,
        }
    else:
        lines = plan.lines if initial else plan.accepted_support.lines
        matches = [line for line in lines if role == f"line.{line.entity_id}"]
        _require(len(matches) == 1, "native_identity_changed")
        line = matches[0]
        expected = {
            "kind": "line",
            "location": transform(plan.frame, plan.center) if dimensions == 3 else plan.center,
            "direction": transform(plan.frame, line.direction)
            if dimensions == 3
            else line.direction,
            "u": None,
            "v": None,
            "normal": None,
            "radius": None,
            "range": (0.0, line.trim_parameter),
            "identity_location": True,
        }
    for key in ("direction", "u", "v", "normal"):
        if record[key] is not None:
            _vector(record[key], dimensions)
    if record["radius"] is not None:
        _finite(record["radius"])
    if initial and expected["kind"] == "line":
        # The one actual direction is observed here, not accepted. Its strict
        # zero/sign/envelope and complete geometry proof happen in the private
        # fresh continuation before any face assembly.
        _vector(record["direction"], dimensions)
        expected["direction"] = record["direction"]
    _require(
        type(record["kind"]) is str and record == expected,
        "native_surface_trace_mismatch" if dimensions == 2 else "native_curve_fields_changed",
    )


def validate_initial_curve_fields(plan, role, record):
    """Pre-proof support metadata only; never a native acceptance validator."""
    _validate_curve_fields(plan, role, record, dimensions=3, initial=True)


def validate_curve_fields(plan, role, record, *, dimensions=3):
    """Require the freshly proved actual support; no fallback to intended lines."""
    _validate_curve_fields(plan, role, record, dimensions=dimensions, initial=False)


def expected_edge_metadata(plan, role, traversal):
    """Support order and positive-cycle order are independent of authored direction."""
    _require(
        type(traversal) is str and traversal in ("support", "boundary"), "invalid_native_stage"
    )
    arc = plan.source.incidence.arc
    if role == f"arc.{arc.id}":
        ids = (
            (arc.start_id, arc.end_id)
            if plan.parameters[1] > plan.parameters[0]
            else (arc.end_id, arc.start_id)
        )
    else:
        lines = [line for line in plan.lines if role == f"line.{line.entity_id}"]
        _require(len(lines) == 1, "native_identity_changed")
        ids = (arc.center_id, lines[0].point_id)
    if traversal == "support":
        return ids, 0
    uses = [use for use in plan.source.boundary if role == f"{use.kind}.{use.entity_id}"]
    _require(len(uses) == 1, "native_identity_changed")
    boundary_ids = (uses[0].start_id, uses[0].end_id)
    _require(boundary_ids in (ids, tuple(reversed(ids))), "native_boundary_plan_mismatch")
    return boundary_ids, int(boundary_ids != ids)


def _stored_curve_grammar(record, dimensions):
    _keys(
        record,
        (
            "kind",
            "location",
            "direction",
            "u",
            "v",
            "normal",
            "radius",
            "range",
            "identity_location",
        ),
    )
    _require(
        type(record["kind"]) is str and record["kind"] in ("circle", "line"),
        "invalid_native_representation",
    )
    _require(type(record["identity_location"]) is bool, "invalid_native_representation")
    _vector(record["location"], dimensions)
    _vector(record["range"], 2)
    _require(record["range"][0] < record["range"][1], "invalid_native_representation")
    if record["kind"] == "line":
        _vector(record["direction"], dimensions)
        _require(
            all(record[key] is None for key in ("u", "v", "normal", "radius")),
            "invalid_native_representation",
        )
    else:
        _require(record["direction"] is None, "invalid_native_representation")
        _vector(record["u"], dimensions)
        _vector(record["v"], dimensions)
        if dimensions == 3:
            _vector(record["normal"], 3)
        else:
            _require(record["normal"] is None, "invalid_native_representation")
        _finite(record["radius"])
        _require(record["radius"] > 0, "invalid_native_representation")


def validate_representation_inventory(plan, role, record, *, pcurve_required):
    """Strict detached inventory; native ownership flags remain empirical observations."""
    _require(type(pcurve_required) is bool, "invalid_native_stage")
    _require(type(plan) is NativePlan and hasattr(plan, "frame"), "invalid_native_plan")
    _require(type(record) is dict and len(record) <= 32, "native_evidence_incomplete")
    _require(all(type(key) is str for key in record), "native_evidence_incomplete")
    _require(
        {
            "representations",
            "curve",
            "pcurve",
            "stored_representation_count",
            "stored_pcurve_count",
            "retained_pcurve_count",
            "selected_pcurve_index",
            "pcurve_surface_matches",
        }
        <= record.keys(),
        "native_evidence_incomplete",
    )
    entries = record["representations"]
    _require(type(entries) is tuple and 1 <= len(entries) <= 8, "native_representation_limit")
    surfaces, curves, pcurves, retained = {}, [], [], []
    identity = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))
    for index, item in enumerate(entries):
        _keys(
            item,
            (
                "index",
                "representation_type",
                "is_curve3d",
                "is_on_surface",
                "is_closed_surface",
                "surface_index",
                "surface_is_retained",
                "surface_fields",
                "location",
                "range",
                "curve3d",
                "pcurves",
            ),
        )
        _require(
            type(item["index"]) is int and item["index"] == index, "invalid_native_representation"
        )
        _require(
            all(
                type(item[key]) is bool
                for key in (
                    "is_curve3d",
                    "is_on_surface",
                    "is_closed_surface",
                    "surface_is_retained",
                )
            ),
            "invalid_native_representation",
        )
        _require(type(item["representation_type"]) is str, "invalid_native_representation")
        flags = (
            item["is_curve3d"],
            item["is_on_surface"],
            item["is_closed_surface"],
            item["representation_type"],
        )
        _require(
            flags
            in (
                (True, False, False, "BRep_Curve3D"),
                (False, True, False, "BRep_CurveOnSurface"),
                (False, True, True, "BRep_CurveOnClosedSurface"),
            ),
            "invalid_native_representation",
        )
        location = item["location"]
        _keys(location, ("identity", "matrix"))
        _require(type(location["identity"]) is bool, "invalid_native_representation")
        _require(
            type(location["matrix"]) is tuple and len(location["matrix"]) == 3,
            "invalid_native_representation",
        )
        for row in location["matrix"]:
            _vector(row, 4)
        _require(
            not location["identity"] or location["matrix"] == identity, "native_location_changed"
        )
        _vector(item["range"], 2)
        _require(item["range"][0] < item["range"][1], "invalid_native_representation")
        branches = item["pcurves"]
        _require(type(branches) is tuple and len(branches) <= 2, "invalid_native_representation")
        if item["is_curve3d"]:
            _require(
                item["surface_index"] is None
                and item["surface_fields"] is None
                and not item["surface_is_retained"]
                and not branches,
                "invalid_native_representation",
            )
            _stored_curve_grammar(item["curve3d"], 3)
            curves.append(item)
        else:
            _require(
                item["curve3d"] is None
                and len(branches) == (2 if item["is_closed_surface"] else 1),
                "invalid_native_representation",
            )
            owner = item["surface_index"]
            _require(type(owner) is int and 0 <= owner < 8, "invalid_native_representation")
            surface = item["surface_fields"]
            _keys(surface, ("kind", "origin", "u", "v", "normal", "radius"))
            _require(
                type(surface["kind"]) is str
                and surface["kind"] in ("Geom_Plane", "Geom_CylindricalSurface"),
                "invalid_native_representation",
            )
            for key in ("origin", "u", "v", "normal"):
                _vector(surface[key], 3)
            if surface["kind"] == "Geom_Plane":
                _require(surface["radius"] is None, "invalid_native_representation")
            else:
                _finite(surface["radius"])
                _require(surface["radius"] > 0, "invalid_native_representation")
            association = (item["surface_is_retained"], surface)
            if owner in surfaces:
                _require(surfaces[owner] == association, "invalid_native_representation")
            else:
                _require(owner == len(surfaces), "invalid_native_representation")
                surfaces[owner] = association
            for branch in branches:
                _stored_curve_grammar(branch, 2)
            pcurves.append(item)
            if item["surface_is_retained"]:
                retained.append(item)
        coefficients = (item["curve3d"],) if item["is_curve3d"] else branches
        for curve in coefficients:
            _require(
                curve["range"] == item["range"]
                and curve["identity_location"] == location["identity"],
                "native_representation_mismatch",
            )
    for name, count in (
        ("stored_representation_count", len(entries)),
        ("stored_pcurve_count", len(pcurves)),
        ("retained_pcurve_count", len(retained)),
    ):
        _require(
            type(record[name]) is int and record[name] == count,
            "native_representation_count_mismatch",
        )
    _require(
        len(curves) == 1 and curves[0]["curve3d"] == record["curve"],
        "native_representation_mismatch",
    )
    _require(
        curves[0]["location"] == {"identity": True, "matrix": identity}, "native_location_changed"
    )
    selected_index = record["selected_pcurve_index"]
    _require(
        selected_index is None
        or (type(selected_index) is int and 0 <= selected_index < len(entries)),
        "invalid_native_representation",
    )
    expected_index = retained[0]["index"] if len(retained) == 1 else None
    _require(selected_index == expected_index, "native_pcurve_selection_mismatch")
    _require(
        type(record["pcurve_surface_matches"]) is bool
        and record["pcurve_surface_matches"] == (len(retained) == 1),
        "native_pcurve_owner_changed",
    )
    # Uniqueness uses only the genuine surface association. A second association
    # can never be hidden by its bad location, range, coefficients or seam flag.
    _require(len(retained) == (1 if pcurve_required else 0), "native_pcurve_owner_ambiguous")
    if not pcurve_required:
        _require(record["pcurve"] is None, "native_representation_mismatch")
        return
    selected = retained[0]
    _require(
        not selected["is_closed_surface"] and len(selected["pcurves"]) == 1,
        "native_retained_pcurve_seam",
    )
    _require(
        selected["location"] == {"identity": True, "matrix": identity}, "native_location_changed"
    )
    _require(
        selected["surface_fields"]
        == {
            "kind": "Geom_Plane",
            "origin": plan.frame.origin,
            "u": plan.frame.u,
            "v": plan.frame.v,
            "normal": plan.frame.normal,
            "radius": None,
        },
        "native_face_fields_changed",
    )
    _stored_curve_grammar(record["pcurve"], 2)
    _require(record["pcurve"] == selected["pcurves"][0], "native_representation_mismatch")
    validate_curve_fields(plan, role, selected["pcurves"][0], dimensions=2)


def validate_edge_observation(
    plan,
    role,
    record,
    *,
    context: PrimitiveContext,
    traversal,
    pcurve_required=False,
    representatives=None,
):
    """Data validation only. The kernel itself supplies all identity observations."""
    _keys(
        record,
        (
            "role",
            "curve",
            "pcurve",
            "stored_pcurve_count",
            "stored_representation_count",
            "retained_pcurve_count",
            "selected_pcurve_index",
            "representations",
            "pcurve_surface_matches",
            "orientation",
            "expected_orientation",
            "endpoint_ids",
            "expected_endpoint_ids",
            "vertex_identity_matches",
            "edge_identity_matches",
            "vertex_coordinates",
            "vertex_parameters",
            "edge_tolerance",
            "vertex_tolerances",
            "locations_identity",
            "evaluated_endpoints",
            "observed_distances",
            "equation_bounds_transfer",
        )
        + (("curve_support_identity_matches",) if representatives is not None else ()),
    )
    _require(type(role) is str and 1 <= len(role) <= 300, "native_identity_changed")
    _require(type(record["role"]) is str and record["role"] == role, "native_identity_changed")
    for key in ("endpoint_ids", "expected_endpoint_ids"):
        value = record[key]
        _require(type(value) is tuple and len(value) == 2, "native_identity_changed")
        _require(
            all(type(identifier) is str and 1 <= len(identifier) <= 256 for identifier in value),
            "native_identity_changed",
        )
    validate_curve_fields(plan, role, record["curve"])
    validate_representation_inventory(plan, role, record, pcurve_required=pcurve_required)
    for key in (
        "vertex_identity_matches",
        "edge_identity_matches",
        "locations_identity",
        "equation_bounds_transfer",
    ):
        _yes(record[key], "native_identity_changed")
    if representatives is not None:
        _yes(record["curve_support_identity_matches"], "native_curve_support_identity_changed")
    expected_ids, orientation = expected_edge_metadata(plan, role, traversal)
    _require(
        type(record["orientation"]) is int
        and type(record["expected_orientation"]) is int
        and record["orientation"] == record["expected_orientation"] == orientation,
        "native_orientation_changed",
    )
    _require(
        type(expected_ids) is tuple
        and len(expected_ids) == 2
        and record["endpoint_ids"] == record["expected_endpoint_ids"] == expected_ids,
        "native_identity_changed",
    )
    authored_vertices = dict(plan.vertices)
    vertices = authored_vertices
    if representatives is not None:
        from .arc_profile_native_plan import validate_native_vertex_representation

        validate_native_vertex_representation(plan, representatives, context=context)
        vertices = dict(representatives.vertices)
    _require(
        type(record["vertex_coordinates"]) is tuple and len(record["vertex_coordinates"]) == 2,
        "native_evidence_incomplete",
    )
    for identifier, point in zip(expected_ids, record["vertex_coordinates"], strict=True):
        _vector(point, 3)
        _require(identifier in vertices and point == vertices[identifier], "native_vertex_changed")
    _vector(record["vertex_parameters"], 2)
    expected_parameters = record["curve"]["range"]
    if record["expected_orientation"] == 1:
        expected_parameters = tuple(reversed(expected_parameters))
    _require(record["vertex_parameters"] == expected_parameters, "native_vertex_parameter_changed")
    _finite(record["edge_tolerance"])
    _vector(record["vertex_tolerances"], 2)
    # Binary64 1e-7 is below the exact rational ceiling, so this is conservative.
    for tolerance in (record["edge_tolerance"], *record["vertex_tolerances"]):
        _require(0 <= tolerance <= 1e-7, "native_tolerance_exceeded")
    _require(
        type(record["evaluated_endpoints"]) is tuple and len(record["evaluated_endpoints"]) == 2,
        "native_evidence_incomplete",
    )
    for identifier, point in zip(expected_ids, record["evaluated_endpoints"], strict=True):
        _vector(point, 3)
        squared = context._make(0, 0)
        for actual, original in zip(point, authored_vertices[identifier], strict=True):
            # Exact float equality needs no arithmetic witness; unequal coordinates
            # are decoded and compared as exact binary rationals in this context.
            if actual != original:
                difference = context._sub(_number(context, actual), _number(context, original))
                squared = context._add(squared, context._mul(difference, difference))
        _require(
            context._compare(context._mul(squared, context._make(10**18, 0)), Dyadic(1, 0)) <= 0,
            "native_evaluation_discrepancy",
        )
    if representatives is not None:
        for identifier, point in zip(expected_ids, record["evaluated_endpoints"], strict=True):
            squared = context._make(0, 0)
            for actual, representative in zip(point, vertices[identifier], strict=True):
                if actual != representative:
                    difference = context._sub(
                        _number(context, actual), _number(context, representative)
                    )
                    squared = context._add(squared, context._mul(difference, difference))
            _require(
                context._compare(context._mul(squared, context._make(10**18, 0)), Dyadic(1, 0))
                <= 0,
                "native_representative_evaluation_discrepancy",
            )
            if role == f"arc.{plan.source.incidence.arc.id}":
                _require(point == vertices[identifier], "native_circle_evaluation_changed")
    _vector(record["observed_distances"], 2)
    for value in record["observed_distances"]:
        _require(value >= 0, "invalid_native_observation")
        exact = _number(context, value)
        _require(
            context._compare(context._mul(exact, context._make(10**9, 0)), Dyadic(1, 0)) <= 0,
            "native_evaluation_discrepancy",
        )


def _distance(c, value, interval):
    if c._compare(value, interval.lower) < 0:
        return c._sub(interval.lower, value)
    if c._compare(value, interval.upper) > 0:
        return c._sub(value, interval.upper)
    return c._make(0, 0)


def native_height(height):
    """Shared strict height-only gate; no perpendicular native-height claim."""
    _require(type(height) in (int, float) and 1 <= height <= 1000, "unsupported_profile_scale")
    _require(math.isfinite(height), "invalid_native_number")
    return float(height)


def validate_end_cap_observation(plan, record, *, height, context):
    """Check only the retained-face translated instance; data grants no authority."""
    _require(type(plan) is NativePlan and type(context) is PrimitiveContext, "invalid_native_plan")
    _require(all(hasattr(plan, field.name) for field in fields(NativePlan)), "invalid_native_plan")
    _require(type(plan.accepted_support) is NativeActualSupport, "unproved_native_support")
    _require(
        all(hasattr(plan.accepted_support, field.name) for field in fields(NativeActualSupport)),
        "invalid_native_support_record",
    )
    _keys(
        record,
        (
            "shape_type",
            "is_null",
            "orientation",
            "profile_orientation",
            "first_is_equal",
            "shape_location",
            "surface_location",
            "surface_type",
            "surface_fields",
            "surface_is_retained",
            "is_partner",
            "is_same",
            "is_equal",
            "actual_vector",
            "height",
        ),
    )
    code = "native_end_cap_fields_changed"
    for key, expected in (("shape_type", 4), ("orientation", 0), ("profile_orientation", 0)):
        _require(type(record[key]) is int and record[key] == expected, code)
    for key, expected in (
        ("is_null", False),
        ("first_is_equal", True),
        ("surface_is_retained", True),
        ("is_partner", True),
        ("is_same", False),
        ("is_equal", False),
    ):
        _require(type(record[key]) is bool and record[key] is expected, code)
    height = native_height(height)
    _finite(record["height"])
    _require(record["height"] == height, code)
    _vector(record["actual_vector"], 3)
    _require(type(record["surface_type"]) is str and record["surface_type"] == "Geom_Plane", code)
    plane = record["surface_fields"]
    _keys(plane, ("kind", "origin", "u", "v", "normal", "radius"))
    _require(type(plane["kind"]) is str and plane["kind"] == "Geom_Plane", code)
    for key in ("origin", "u", "v", "normal"):
        _vector(plane[key], 3)
    _require(
        plane["radius"] is None
        and plane["origin"] == (0.0, 0.0, 0.0)
        and plane["u"] == plan.frame.u
        and plane["v"] == plan.frame.v
        and plane["normal"] == plan.frame.normal,
        code,
    )
    # The supplied height and fresh frame, never a caller expected vector, bind t.
    c = context
    exact_height = _number(c, height)
    for actual, normal in zip(record["actual_vector"], plan.frame.normal, strict=True):
        expected = c._mul(exact_height, _number(c, normal))
        _require(c._compare(_number(c, actual), expected) == 0, code)
    for key in ("shape_location", "surface_location"):
        location = record[key]
        _keys(location, ("identity", "matrix"))
        _require(type(location["identity"]) is bool and not location["identity"], code)
        matrix = location["matrix"]
        _require(type(matrix) is tuple and len(matrix) == 3, "invalid_native_observation")
        for row in matrix:
            _vector(row, 4)
        _require(
            matrix
            == (
                (1.0, 0.0, 0.0, record["actual_vector"][0]),
                (0.0, 1.0, 0.0, record["actual_vector"][1]),
                (0.0, 0.0, 1.0, record["actual_vector"][2]),
            ),
            code,
        )
    _require(record["shape_location"]["matrix"] == record["surface_location"]["matrix"], code)
    # Surface_s already returns the complete placement. Apply it once: the
    # corroborating shape location is not a second transform. Local origin is 0.
    return {
        "origin": tuple(row[3] for row in record["surface_location"]["matrix"]),
        "u": plane["u"],
        "v": plane["v"],
        "normal": plane["normal"],
        "placement_rule": "checked_surface_translation_applied_once",
    }


def mass_limits(plan, height, *, context):
    """Freeze source R0/C0 limits before the sole prism constructor."""
    height = native_height(height)
    c = context
    i = IntervalContext(c, plan.area_allowance.precision)
    h = _number(c, height)
    ea = plan.area_allowance
    ev = i._add(
        i._add(
            i._mul(i.point(h), ea),
            i.point(c._mul(c._mul(Dyadic(3, -46), plan.local_scale_squared), h)),
        ),
        i._mul(i.point(c._mul(Dyadic(1, -49), plan.world_scale)), plan.source_area_midpoint),
    )
    target = i._mul(plan.source_comparison_area, i.point(h))
    consistency = i._add(ev, i._mul(i.point(h), ea))
    return target, ev, consistency


def mass_check_record(check):
    """Detached exact comparison evidence, with no native authority."""
    from dataclasses import asdict

    return asdict(check)


def check_masses(plan, area, *, context, height=None, volume=None):
    """Unchanged fixed source R0/C0 comparisons on observed binary64 masses."""
    _require(type(plan) is NativePlan and type(context) is PrimitiveContext, "invalid_native_plan")
    _finite(area)
    _require(area > 0, "native_nonpositive_mass")
    c = context
    exact_area = _number(c, area)
    area_distance = _distance(c, exact_area, plan.source_comparison_area)
    _require(c._compare(area_distance, plan.area_allowance.upper) <= 0, "native_area_r0_failure")
    if height is None:
        _require(volume is None, "invalid_native_observation")
        return NativeMassCheck(
            area, None, None, plan.area_allowance, None, None, area_distance, None, None
        )
    height = native_height(height)
    _finite(volume)
    _require(volume > 0, "native_nonpositive_mass")
    h, exact_volume = _number(c, height), _number(c, volume)
    ea = plan.area_allowance
    target, ev, consistency = mass_limits(plan, height, context=c)
    volume_distance = _distance(c, exact_volume, target)
    _require(c._compare(volume_distance, ev.upper) <= 0, "native_volume_r0_failure")
    residual = c._sub(exact_volume, c._mul(exact_area, h))
    if residual.mantissa < 0:
        residual = c._neg(residual)
    _require(c._compare(residual, consistency.upper) <= 0, "native_mass_c0_failure")
    return NativeMassCheck(
        area, height, volume, ea, ev, consistency, area_distance, volume_distance, residual
    )


def bounded_evidence_bytes(record):
    """Bound complete detached evidence; this encoding never grants native authority."""
    _require(type(record) is dict and len(record) <= 7, "invalid_native_evidence")
    allowed = {
        "events",
        "operation",
        "operations_start",
        "operations_end",
        "source_json",
        "source_sha256",
        "failure",
    }
    _require(
        all(type(key) is str and key in allowed for key in record)
        and {"events", "operation", "operations_start"} <= record.keys(),
        "invalid_native_evidence",
    )
    _require(
        type(record["operation"]) is str and record["operation"] == "curve_profile",
        "invalid_native_evidence",
    )
    _require(type(record["events"]) is list, "invalid_native_evidence")
    _require(len(record["events"]) <= 64, "native_evidence_limit")
    nodes = 0
    limit = 1_048_576

    def inspect(value, depth=0):
        nonlocal nodes
        nodes += 1
        _require(depth <= 16 and nodes <= 8192, "native_evidence_limit")
        kind = type(value)
        if value is None or kind is bool:
            return
        if kind is str:
            _require(len(value) <= limit, "native_evidence_limit")
        elif kind is int:
            _require(value.bit_length() <= 65_536, "native_evidence_limit")
        elif kind is float:
            _require(math.isfinite(value), "invalid_native_evidence")
        elif kind in (tuple, list):
            _require(len(value) <= 256, "native_evidence_limit")
            for child in value:
                inspect(child, depth + 1)
        elif kind is dict:
            _require(len(value) <= 64, "native_evidence_limit")
            for key, child in value.items():
                _require(type(key) is str and len(key) <= 256, "invalid_native_evidence")
                inspect(child, depth + 1)
        else:
            _require(False, "invalid_native_evidence")

    inspect(record)
    output = bytearray()
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    try:
        for chunk in encoder.iterencode(record):
            encoded = chunk.encode("ascii")
            _require(len(output) + len(encoded) <= limit, "native_evidence_limit")
            output.extend(encoded)
    except (ValueError, OverflowError):
        # Includes Python's bounded decimal integer encoding limit. Never replace
        # an unencodable required value with a shortened or approximate record.
        _require(False, "native_evidence_limit")
    return bytes(output)


def _generated_vector(c, values):
    return tuple(_number(c, value) for value in values)


def _generated_add(c, left, right):
    return tuple(c._add(a, b) for a, b in zip(left, right, strict=True))


def _generated_sub(c, left, right):
    return tuple(c._sub(a, b) for a, b in zip(left, right, strict=True))


def _generated_scale(c, value, vector):
    return tuple(c._mul(value, component) for component in vector)


def _generated_dot(c, left, right):
    result = c._make(0, 0)
    for a, b in zip(left, right, strict=True):
        result = c._add(result, c._mul(a, b))
    return result


def _generated_cross(c, left, right):
    return tuple(
        c._sub(c._mul(left[a], right[b]), c._mul(left[b], right[a]))
        for a, b in ((1, 2), (2, 0), (0, 1))
    )


def _generated_equal(c, left, right, code):
    _require(all(c._compare(a, b) == 0 for a, b in zip(left, right, strict=True)), code)


def _generated_delta(c, numerator, denominator=None):
    """Exact denominator-cleared Delta; no new square root or tolerance."""
    denominator = Dyadic(1, 0) if denominator is None else denominator
    _require(denominator.mantissa > 0, "native_generated_invalid_denominator")
    squared = _generated_dot(c, numerator, numerator)
    _require(
        c._compare(c._mul(c._make(10**18, 0), squared), c._mul(denominator, denominator)) <= 0,
        "native_generated_trace_discrepancy",
    )
    return squared


def _generated_cell(c, numerator, denominator, radius):
    """Strict original-cell membership of a homogeneous displacement."""
    n, k = radius.numerator, radius.denominator
    _require(n.mantissa > 0 and k.mantissa > 0, "native_generated_invalid_cell")
    squared = _generated_dot(c, numerator, numerator)
    left = c._mul(c._mul(k, k), squared)
    right = c._mul(c._mul(n, n), c._mul(denominator, denominator))
    _require(c._compare(left, right) < 0, "native_generated_projected_cell_failure")
    return c._sub(right, left)


def _generated_location(c, record):
    _keys(record, ("identity", "matrix"))
    _require(type(record["identity"]) is bool, "invalid_native_representation")
    matrix = record["matrix"]
    _require(type(matrix) is tuple and len(matrix) == 3, "invalid_native_representation")
    for index, row in enumerate(matrix):
        _vector(row, 4)
        _require(
            row[:3] == tuple(float(index == column) for column in range(3)),
            "native_generated_location_changed",
        )
    translation = tuple(row[3] for row in matrix)
    _require(
        record["identity"] == (translation == (0.0, 0.0, 0.0)),
        "native_generated_location_changed",
    )
    return _generated_vector(c, translation)


def _generated_surface_grammar(surface):
    _keys(surface, ("kind", "origin", "u", "v", "normal", "radius"))
    _require(
        type(surface["kind"]) is str
        and surface["kind"] in ("Geom_Plane", "Geom_CylindricalSurface"),
        "invalid_native_representation",
    )
    for key in ("origin", "u", "v", "normal"):
        _vector(surface[key], 3)
    if surface["kind"] == "Geom_Plane":
        _require(surface["radius"] is None, "invalid_native_representation")
    else:
        _finite(surface["radius"])
        _require(surface["radius"] > 0, "invalid_native_representation")


def _generated_regularity_grammar(item, surfaces, owner_roles):
    """Keep the exact two-owner advisory variant separate from geometric records."""
    _require(
        item["range"] == ()
        and type(item["range"]) is tuple
        and item["curve3d"] is None
        and type(item["pcurves"]) is tuple
        and item["pcurves"] == ()
        and item["owner_roles"] == ()
        and item["surface_index"] is None
        and item["surface_fields"] is None
        and not item["surface_is_retained"],
        "invalid_native_representation",
    )
    record = item["regularity"]
    _keys(
        record,
        (
            "surface1",
            "surface2",
            "location2",
            "continuity_value",
            "continuity_name",
            "continuity_type",
        ),
    )
    value, name = record["continuity_value"], record["continuity_name"]
    names = (
        "GeomAbs_C0",
        "GeomAbs_G1",
        "GeomAbs_C1",
        "GeomAbs_G2",
        "GeomAbs_C2",
        "GeomAbs_C3",
        "GeomAbs_CN",
    )
    _require(
        type(value) is int
        and 0 <= value < len(names)
        and type(name) is str
        and name == names[value],
        "invalid_native_regularity",
    )
    native_type = record["continuity_type"]
    _keys(native_type, ("module", "qualname"))
    _require(
        all(type(text) is str and 1 <= len(text) <= 128 for text in native_type.values()),
        "invalid_native_regularity",
    )
    for key in ("surface1", "surface2"):
        slot = record[key]
        _keys(slot, ("surface_index", "owner_roles", "surface_fields"))
        owner, roles = slot["surface_index"], slot["owner_roles"]
        _require(type(owner) is int and 0 <= owner < 8, "invalid_native_representation")
        _require(
            type(roles) is tuple
            and len(roles) == 1
            and type(roles[0]) is str
            and roles[0] in owner_roles,
            "native_generated_owner_changed",
        )
        _generated_surface_grammar(slot["surface_fields"])
        association = (roles, slot["surface_fields"])
        if owner in surfaces:
            _require(surfaces[owner] == association, "native_generated_owner_changed")
        else:
            # Check before either slot is inserted, including malformed inputs.
            _require(len(surfaces) < 8, "native_representation_limit")
            _require(owner == len(surfaces), "invalid_native_representation")
            surfaces[owner] = association
    _require(
        record["surface1"]["surface_index"] != record["surface2"]["surface_index"]
        and record["surface1"]["owner_roles"] != record["surface2"]["owner_roles"],
        "native_generated_owner_changed",
    )


def _generated_regularity_placement(c, item, edge, faces, radial_roles):
    """Match both actual incident planes without making a continuity claim.

    The five decodes, five zero comparisons, two compositions and two paired
    comparisons fit the 372-tick conservative supplementary schedule. Identity
    data make the accepted-path cost smaller; all arithmetic uses the continuing
    context. No coplanarity, straightness, root or trigonometric gate is added.
    """
    record = item["regularity"]
    slots = tuple(record[key] for key in ("surface1", "surface2"))
    roles = tuple(slot["owner_roles"][0] for slot in slots)
    _require(set(roles) == set(radial_roles), "native_generated_owner_changed")
    paired = tuple(faces[role] for role in roles)
    for slot, face in zip(slots, paired, strict=True):
        _require(
            slot["surface_fields"]["kind"] == "Geom_Plane"
            and slot["surface_fields"] == face["surface_fields"]
            and sum(occurrence["edge_role"] == edge["role"] for occurrence in face["occurrences"])
            == 1,
            "native_generated_owner_changed",
        )
    locations = (
        edge["location"],
        item["location"],
        record["location2"],
        paired[0]["surface_location"],
        paired[1]["surface_location"],
    )
    translations = []
    zero = (Dyadic(0, 0),) * 3
    for location in locations:
        _keys(location, ("identity", "matrix"))
        _yes(location["identity"], "native_generated_location_changed")
        translation = _generated_location(c, location)
        _generated_equal(c, translation, zero, "native_generated_location_changed")
        translations.append(translation)
    edge_placement, first, second, face_first, face_second = translations
    for placement, actual_face in ((first, face_first), (second, face_second)):
        _generated_equal(
            c,
            _generated_add(c, edge_placement, placement),
            actual_face,
            "native_generated_location_changed",
        )


def _generated_inventory(c, edge, owner_roles):
    """Inspect every entry before owner/placement selection, including foreigners."""
    entries = edge["representations"]
    _require(type(entries) is tuple and 1 <= len(entries) <= 8, "native_representation_limit")
    surfaces, curves, observed, metadata = {}, [], [], []
    edge_location = _generated_location(c, edge["location"])
    for index, item in enumerate(entries):
        _keys(
            item,
            (
                "index",
                "representation_type",
                "is_curve3d",
                "is_on_surface",
                "is_closed_surface",
                "is_regularity",
                "regularity",
                "surface_index",
                "surface_is_retained",
                "surface_fields",
                "location",
                "range",
                "curve3d",
                "pcurves",
                "owner_roles",
            ),
        )
        _require(
            type(item["index"]) is int and item["index"] == index, "invalid_native_representation"
        )
        _require(
            all(
                type(item[key]) is bool
                for key in (
                    "is_curve3d",
                    "is_on_surface",
                    "is_closed_surface",
                    "is_regularity",
                    "surface_is_retained",
                )
            ),
            "invalid_native_representation",
        )
        _require(type(item["representation_type"]) is str, "invalid_native_representation")
        _require(
            (
                item["is_curve3d"],
                item["is_on_surface"],
                item["is_closed_surface"],
                item["is_regularity"],
                item["representation_type"],
            )
            in (
                (True, False, False, False, "BRep_Curve3D"),
                (False, True, False, False, "BRep_CurveOnSurface"),
                (False, True, True, True, "BRep_CurveOnClosedSurface"),
                (False, False, False, True, "BRep_CurveOn2Surfaces"),
            ),
            "invalid_native_representation",
        )
        roles = item["owner_roles"]
        _require(
            type(roles) is tuple
            and len(roles) <= 4
            and all(type(role) is str and role in owner_roles for role in roles)
            and len(set(roles)) == len(roles),
            "invalid_native_representation",
        )
        _require(
            item["surface_is_retained"] == ("retained_profile_plane" in roles),
            "native_generated_owner_changed",
        )
        if item["representation_type"] == "BRep_CurveOn2Surfaces":
            _require(not metadata, "native_generated_regularity_ambiguous")
            _generated_regularity_grammar(item, surfaces, owner_roles)
            metadata.append(item)
            # Advisory metadata contributes no support, branch, range or pcurve
            # candidate. Its two placements are checked after all old geometry.
            continue
        _require(item["regularity"] is None, "invalid_native_representation")
        location = _generated_location(c, item["location"])
        composed = _generated_add(c, edge_location, location)
        _vector(item["range"], 2)
        _require(item["range"][0] < item["range"][1], "invalid_native_representation")
        branches = item["pcurves"]
        _require(type(branches) is tuple and len(branches) <= 2, "invalid_native_representation")
        if item["is_curve3d"]:
            _require(
                item["surface_index"] is None
                and item["surface_fields"] is None
                and not roles
                and not branches,
                "invalid_native_representation",
            )
            _stored_curve_grammar(item["curve3d"], 3)
            coefficients = (item["curve3d"],)
            curves.append((item, composed))
        else:
            _require(
                item["curve3d"] is None
                and len(branches) == (2 if item["is_closed_surface"] else 1),
                "invalid_native_representation",
            )
            owner = item["surface_index"]
            _require(type(owner) is int and 0 <= owner < 8, "invalid_native_representation")
            _generated_surface_grammar(item["surface_fields"])
            association = (roles, item["surface_fields"])
            if owner in surfaces:
                _require(surfaces[owner] == association, "native_generated_owner_changed")
            else:
                _require(owner == len(surfaces), "invalid_native_representation")
                surfaces[owner] = association
            for branch in branches:
                _stored_curve_grammar(branch, 2)
            coefficients = branches
        for curve in coefficients:
            _require(
                curve["range"] == item["range"]
                and curve["identity_location"] == item["location"]["identity"],
                "native_representation_mismatch",
            )
        observed.append((item, composed))
    _require(len(curves) == 1, "native_generated_curve_ambiguous")
    for item in metadata:
        for key in ("surface1", "surface2"):
            slot = item["regularity"][key]
            role = slot["owner_roles"][0]
            _require(
                all(
                    role not in association[0] or owner == slot["surface_index"]
                    for owner, association in surfaces.items()
                ),
                "native_generated_owner_changed",
            )
    return curves[0], tuple(observed), tuple(metadata)


def _generated_orientation(value):
    _require(type(value) is int and value in (0, 1), "native_generated_orientation_changed")


def _generated_tolerance(value):
    _finite(value)
    _require(0 <= value <= 1e-7, "native_tolerance_exceeded")


def _generated_exact_record(value):
    return (value.mantissa, value.exponent)


def _generated_projection(c, x, origin, u, v, a):
    w = _generated_sub(c, x, origin)
    b, vertical = _generated_dot(c, w, u), _generated_dot(c, w, v)
    residual = _generated_sub(
        c,
        _generated_sub(c, _generated_scale(c, a, w), _generated_scale(c, b, u)),
        _generated_scale(c, c._mul(a, vertical), v),
    )
    _generated_delta(c, residual, a)
    return residual, vertical


def _generated_plane_endpoint(
    c, x, trace_numerator, denominator, representative, authored, outer, radius
):
    _generated_delta(c, _generated_sub(c, x, representative))
    _generated_delta(
        c, _generated_sub(c, trace_numerator, _generated_scale(c, denominator, x)), denominator
    )
    _generated_delta(
        c,
        _generated_sub(c, trace_numerator, _generated_scale(c, denominator, representative)),
        denominator,
    )
    if outer:
        # This is an independent projected/stored endpoint obligation, not a
        # consequence inferred from membership of q and the radial endpoint.
        displacement = _generated_sub(
            c, trace_numerator, _generated_scale(c, denominator, authored)
        )
        _generated_cell(c, displacement, denominator, radius)
    else:
        _generated_equal(c, x, representative, "native_generated_center_changed")
        _generated_equal(
            c,
            trace_numerator,
            _generated_scale(c, denominator, representative),
            "native_generated_center_changed",
        )


def validate_generated_trace_observation(plan, representatives, record, *, height, context):
    """Fixed detached three-side proof in the original checked context.

    Identity booleans are observations supplied by the live collector. This
    mathematical checker neither manufactures native identity nor registers any
    shape. Exact support correspondence and bounded affine residuals are distinct.
    """
    from .arc_profile_native_plan import validate_native_vertex_representation

    _require(type(context) is PrimitiveContext, "native_context_discontinuity")
    c, start = context, context.operations
    validate_native_vertex_representation(plan, representatives, context=c)
    # The existing whole-evidence grammar rejects callback-capable values before
    # dictionary equality, membership, arithmetic, or JSON encoding uses them.
    bounded_evidence_bytes(
        {"operation": "curve_profile", "operations_start": start, "events": [record]}
    )
    _keys(record, ("height", "actual_vector", "vertices", "edges", "faces"))
    height = native_height(height)
    _finite(record["height"])
    _require(record["height"] == height, "native_generated_height_changed")
    _vector(record["actual_vector"], 3)
    h = _number(c, height)
    zero = (Dyadic(0, 0),) * 3
    normal = _generated_vector(c, plan.frame.normal)
    translation = _generated_scale(c, h, normal)
    _generated_equal(
        c,
        _generated_vector(c, record["actual_vector"]),
        translation,
        "native_generated_height_changed",
    )
    arc = plan.source.incidence.arc
    point_ids = (arc.center_id, arc.start_id, arc.end_id)
    profile_roles = tuple(f"{use.kind}.{use.entity_id}" for use in plan.source.boundary)
    side_roles = tuple(f"side.{role}" for role in profile_roles)
    vertex_ids = tuple(f"{level}.{point_id}" for level in ("base", "top") for point_id in point_ids)
    edge_roles = tuple(
        f"{level}.{role}" for level in ("base", "top") for role in profile_roles
    ) + tuple(f"vertical.{point_id}" for point_id in point_ids)
    raw_vertices, raw_edges, raw_faces = (record[key] for key in ("vertices", "edges", "faces"))
    for sequence, count in ((raw_vertices, 6), (raw_edges, 9), (raw_faces, 3)):
        _require(
            type(sequence) is tuple and len(sequence) == count,
            "native_generated_cardinality_changed",
        )
    frozen = {
        identifier: _generated_vector(c, point) for identifier, point in representatives.vertices
    }
    authored = {identifier: _generated_vector(c, point) for identifier, point in plan.vertices}
    vertices, authored_at_height = {}, {}
    for item, identifier in zip(raw_vertices, vertex_ids, strict=True):
        _keys(item, ("id", "point", "tolerance", "location", "history_matches"))
        _require(
            type(item["id"]) is str and item["id"] == identifier,
            "native_generated_identity_changed",
        )
        _yes(item["history_matches"], "native_generated_identity_changed")
        _vector(item["point"], 3)
        _generated_tolerance(item["tolerance"])
        level, point_id = identifier.split(".", 1)
        offset = translation if level == "top" else zero
        _generated_equal(
            c, _generated_location(c, item["location"]), offset, "native_generated_location_changed"
        )
        expected = _generated_add(c, frozen[point_id], offset)
        _generated_equal(
            c, _generated_vector(c, item["point"]), expected, "native_generated_vertex_changed"
        )
        vertices[identifier] = expected
        authored_at_height[identifier] = _generated_add(c, authored[point_id], offset)
    center = transform(plan.frame, plan.center)
    lines = {f"line.{line.entity_id}": line for line in plan.accepted_support.lines}
    supports, inventory, edges, regularities = {}, {}, {}, []
    for item, role in zip(raw_edges, edge_roles, strict=True):
        _keys(
            item,
            (
                "role",
                "location",
                "range",
                "endpoint_ids",
                "tolerance",
                "representations",
                "identity_matches",
            ),
        )
        _require(
            type(item["role"]) is str and item["role"] == role, "native_generated_identity_changed"
        )
        _yes(item["identity_matches"], "native_generated_identity_changed")
        _generated_tolerance(item["tolerance"])
        _vector(item["range"], 2)
        ids = item["endpoint_ids"]
        _require(
            type(ids) is tuple and len(ids) == 2 and all(type(value) is str for value in ids),
            "native_generated_identity_changed",
        )
        if role.startswith("vertical."):
            point_id = role.removeprefix("vertical.")
            expected_ids, parameter_range = (f"base.{point_id}", f"top.{point_id}"), (0.0, height)
            location, direction, offset = (
                dict(representatives.vertices)[point_id],
                plan.frame.normal,
                zero,
            )
            kind, u, v, axis, radius = "line", None, None, None, None
        else:
            level, profile_role = role.split(".", 1)
            ids0, _ = expected_edge_metadata(plan, profile_role, "support")
            expected_ids = tuple(f"{level}.{point_id}" for point_id in ids0)
            offset = translation if level == "top" else zero
            location = center
            if profile_role == f"arc.{arc.id}":
                parameter_range, direction = plan.increasing_parameters, None
                kind, u, v, axis, radius = (
                    "circle",
                    plan.frame.u,
                    plan.frame.v,
                    plan.frame.normal,
                    plan.radius,
                )
            else:
                line = lines[profile_role]
                parameter_range, direction = (
                    (0.0, line.trim_parameter),
                    transform(plan.frame, line.direction),
                )
                kind, u, v, axis, radius = "line", None, None, None, None
        _require(
            ids == expected_ids and item["range"] == parameter_range,
            "native_generated_finite_domain_changed",
        )
        _generated_equal(
            c, _generated_location(c, item["location"]), offset, "native_generated_location_changed"
        )
        (curve_item, composed), entries, metadata = _generated_inventory(
            c, item, (*side_roles, "retained_profile_plane")
        )
        regularities.extend((role, entry) for entry in metadata)
        _require(len(regularities) <= 1, "native_generated_regularity_ambiguous")
        _generated_equal(c, composed, offset, "native_generated_location_changed")
        expected_curve = {
            "kind": kind,
            "location": location,
            "direction": direction,
            "u": u,
            "v": v,
            "normal": axis,
            "radius": radius,
            "range": parameter_range,
            "identity_location": True,
        }
        _require(
            curve_item["curve3d"] == expected_curve and curve_item["range"] == parameter_range,
            "native_generated_curve_fields_changed",
        )
        # Affine endpoints are exact checked arithmetic on the observed raw
        # coefficients. Circle endpoints retain the existing certified boxes.
        if kind == "line":
            origin = _generated_add(c, _generated_vector(c, location), composed)
            d = _generated_vector(c, direction)
            endpoints = tuple(
                _generated_add(c, origin, _generated_scale(c, _number(c, t), d))
                for t in parameter_range
            )
            for identifier, x in zip(ids, endpoints, strict=True):
                _generated_delta(c, _generated_sub(c, x, vertices[identifier]))
            supports[role] = endpoints
        edges[role], inventory[role] = item, entries
        _require(c.operations - start <= 32768, "native_generated_trace_operation_limit")
    inferred, cycle_indices = [], []
    occurrence_counts = {role: 0 for role in edge_roles}
    for face, side_role, use in zip(raw_faces, side_roles, plan.source.boundary, strict=True):
        _keys(
            face,
            (
                "role",
                "generated_is_same",
                "generated_is_partner",
                "generated_is_equal",
                "generated_orientation",
                "orientation",
                "shape_location",
                "surface_location",
                "surface_fields",
                "wire_local_orientation",
                "wire_orientation",
                "occurrences",
            ),
        )
        _require(
            type(face["role"]) is str and face["role"] == side_role,
            "native_generated_identity_changed",
        )
        for key in ("generated_is_same", "generated_is_partner"):
            _yes(face[key], "native_generated_identity_changed")
        for key in (
            "generated_orientation",
            "orientation",
            "wire_local_orientation",
            "wire_orientation",
        ):
            _generated_orientation(face[key])
        _require(
            type(face["generated_is_equal"]) is bool
            and face["generated_is_equal"]
            == (face["generated_orientation"] == face["orientation"]),
            "native_generated_identity_changed",
        )
        _require(
            face["wire_orientation"] == (face["orientation"] ^ face["wire_local_orientation"]),
            "native_generated_orientation_changed",
        )
        _generated_equal(
            c,
            _generated_location(c, face["shape_location"]),
            zero,
            "native_generated_location_changed",
        )
        placement = _generated_location(c, face["surface_location"])
        _generated_equal(c, placement, zero, "native_generated_location_changed")
        surface = face["surface_fields"]
        _generated_surface_grammar(surface)
        is_cylinder = use.kind == "arc"
        u = (
            plan.frame.u
            if is_cylinder
            else transform(plan.frame, lines[f"line.{use.entity_id}"].direction)
        )
        v = plan.frame.v if is_cylinder else tuple(-value for value in plan.frame.normal)
        expected_surface = {
            "kind": "Geom_CylindricalSurface" if is_cylinder else "Geom_Plane",
            "origin": center,
            "u": u,
            "v": v,
            "normal": tuple(-value for value in plan.frame.normal)
            if is_cylinder
            else surface["normal"],
            "radius": plan.radius if is_cylinder else None,
        }
        _require(surface == expected_surface, "native_generated_surface_fields_changed")
        if not is_cylinder:
            origin, du, dv, axis = (
                _generated_vector(c, surface[key]) for key in ("origin", "u", "v", "normal")
            )
            a = _generated_dot(c, du, du)
            cross = _generated_cross(c, du, dv)
            _require(
                a.mantissa > 0 and any(value.mantissa for value in cross),
                "native_generated_surface_fields_changed",
            )
            _require(
                _generated_dot(c, du, dv).mantissa == 0
                and c._compare(_generated_dot(c, dv, dv), Dyadic(1, 0)) == 0
                and all(value.mantissa == 0 for value in _generated_cross(c, axis, cross))
                and _generated_dot(c, axis, cross).mantissa > 0,
                "native_generated_surface_fields_changed",
            )
        expected_cycle = (
            (f"base.{use.kind}.{use.entity_id}", (f"base.{use.start_id}", f"base.{use.end_id}")),
            (f"vertical.{use.end_id}", (f"base.{use.end_id}", f"top.{use.end_id}")),
            (f"top.{use.kind}.{use.entity_id}", (f"top.{use.end_id}", f"top.{use.start_id}")),
            (f"vertical.{use.start_id}", (f"top.{use.start_id}", f"base.{use.start_id}")),
        )
        occurrences = face["occurrences"]
        _require(
            type(occurrences) is tuple and len(occurrences) == 4,
            "native_generated_cardinality_changed",
        )
        cycle, joins = [], {}
        for occurrence in occurrences:
            _keys(occurrence, ("edge_role", "local_orientation", "orientation", "endpoint_ids"))
            role = occurrence["edge_role"]
            _require(
                type(role) is str and role in {entry[0] for entry in expected_cycle},
                "native_generated_identity_changed",
            )
            for key in ("local_orientation", "orientation"):
                _generated_orientation(occurrence[key])
            _require(
                occurrence["orientation"]
                == (face["wire_orientation"] ^ occurrence["local_orientation"]),
                "native_generated_orientation_changed",
            )
            ids = occurrence["endpoint_ids"]
            _require(
                type(ids) is tuple and len(ids) == 2 and all(type(value) is str for value in ids),
                "native_generated_identity_changed",
            )
            support_ids = edges[role]["endpoint_ids"]
            expected_ids = (
                tuple(reversed(support_ids)) if occurrence["orientation"] else support_ids
            )
            _require(ids == expected_ids, "native_generated_identity_changed")
            cycle.append((role, ids))
            occurrence_counts[role] += 1
            # Select strictly on observed owner and complete composed placement.
            # No coefficient, range, seam or branch predicate can hide a second
            # owner/placement candidate.
            candidates = [
                item
                for item, located in inventory[role]
                if side_role in item["owner_roles"]
                and all(
                    c._compare(actual, expected) == 0
                    for actual, expected in zip(located, placement, strict=True)
                )
            ]
            _require(len(candidates) <= 1, "native_generated_pcurve_ambiguous")
            _require(not is_cylinder or len(candidates) == 1, "native_generated_pcurve_missing")
            selected = candidates[0] if candidates else None
            branch = None
            if selected is not None:
                _require(
                    not selected["is_closed_surface"] and len(selected["pcurves"]) == 1,
                    "native_generated_pcurve_ambiguous",
                )
                _require(selected["surface_fields"] == surface, "native_generated_owner_changed")
                _require(
                    selected["range"] == edges[role]["range"],
                    "native_generated_finite_domain_changed",
                )
                branch = selected["pcurves"][0]
                _require(branch["kind"] == "line", "native_generated_nonaffine_trace")
            if is_cylinder:
                if role.startswith("vertical."):
                    point_id = role.removeprefix("vertical.")
                    _require(
                        point_id in (arc.start_id, arc.end_id), "native_generated_identity_changed"
                    )
                    theta = plan.parameters[(arc.start_id, arc.end_id).index(point_id)]
                    uv_origin, uv_direction = (theta, 0.0), (0.0, -1.0)
                else:
                    uv_origin = (0.0, -height if role.startswith("top.") else 0.0)
                    uv_direction = (1.0, 0.0)
                _require(
                    branch
                    == {
                        "kind": "line",
                        "location": uv_origin,
                        "direction": uv_direction,
                        "u": None,
                        "v": None,
                        "normal": None,
                        "radius": None,
                        "range": edges[role]["range"],
                        "identity_location": selected["location"]["identity"],
                    },
                    "native_generated_cylinder_pcurve_changed",
                )
                # The exact circle coefficients and fixed theta transfer the
                # already checked q-to-circle bound to the entire ruling. No H
                # factor and no new evaluation, trig enclosure, or root occurs.
                continue
            for endpoint_index, (identifier, x) in enumerate(
                zip(support_ids, supports[role], strict=True)
            ):
                height_value = h if identifier.startswith("top.") else Dyadic(0, 0)
                expected_v = c._neg(height_value)
                residual, projected_v = _generated_projection(c, x, origin, du, dv, a)
                _require(
                    c._compare(projected_v, expected_v) == 0, "native_generated_height_changed"
                )
                if branch is None:
                    denominator = a
                    numerator = _generated_sub(c, _generated_scale(c, a, x), residual)
                    inferred.append(
                        {
                            "side_role": side_role,
                            "edge_role": role,
                            "endpoint_id": identifier,
                            "kind": "inferred_plane_projection",
                            "residual_numerator": tuple(
                                _generated_exact_record(value) for value in residual
                            ),
                            "denominator": _generated_exact_record(a),
                        }
                    )
                else:
                    parameter = _number(c, edges[role]["range"][endpoint_index])
                    uv = _generated_add(
                        c,
                        _generated_vector(c, branch["location"]),
                        _generated_scale(c, parameter, _generated_vector(c, branch["direction"])),
                    )
                    _require(c._compare(uv[1], expected_v) == 0, "native_generated_height_changed")
                    denominator = Dyadic(1, 0)
                    numerator = _generated_add(
                        c,
                        origin,
                        _generated_add(
                            c, _generated_scale(c, uv[0], du), _generated_scale(c, uv[1], dv)
                        ),
                    )
                point_id = identifier.split(".", 1)[1]
                _generated_plane_endpoint(
                    c,
                    x,
                    numerator,
                    denominator,
                    vertices[identifier],
                    authored_at_height[identifier],
                    point_id != arc.center_id,
                    plan.final_cell_radius,
                )
                joins.setdefault(identifier, []).append((numerator, denominator))
            _require(c.operations - start <= 32768, "native_generated_trace_operation_limit")
        # Native iterator order is retained in the observation. Derive the
        # unique oriented adjacency cycle from all four actual incidences;
        # never sort, normalize orientations, or discard an occurrence.
        indices, remaining = [0], set(range(1, 4))
        while remaining:
            end_id = cycle[indices[-1]][1][1]
            successors = [index for index in remaining if cycle[index][1][0] == end_id]
            _require(len(successors) == 1, "native_generated_cycle_changed")
            indices.append(successors[0])
            remaining.remove(successors[0])
        _require(
            cycle[indices[-1]][1][1] == cycle[indices[0]][1][0], "native_generated_cycle_changed"
        )
        actual_cycle = tuple(cycle[index] for index in indices)
        _require(
            any(
                actual_cycle == expected_cycle[offset:] + expected_cycle[:offset]
                for offset in range(4)
            ),
            "native_generated_cycle_changed",
        )
        cycle_indices.append({"side_role": side_role, "occurrence_indices": tuple(indices)})
        if not is_cylinder:
            _require(
                len(joins) == 4 and all(len(values) == 2 for values in joins.values()),
                "native_generated_cycle_changed",
            )
            for values in joins.values():
                (left, ld), (right, rd) = values
                _generated_delta(
                    c,
                    _generated_sub(
                        c, _generated_scale(c, rd, left), _generated_scale(c, ld, right)
                    ),
                    c._mul(ld, rd),
                )
    _require(
        all(
            count == (2 if role.startswith("vertical.") else 1)
            for role, count in occurrence_counts.items()
        ),
        "native_generated_cardinality_changed",
    )
    for role, item in regularities:
        _require(role == f"vertical.{arc.center_id}", "native_generated_regularity_edge_changed")
        radial_roles = tuple(
            f"side.line.{use.entity_id}"
            for use in plan.source.boundary
            if use.kind == "line" and arc.center_id in (use.start_id, use.end_id)
        )
        _require(len(radial_roles) == 2, "native_generated_owner_changed")
        _generated_regularity_placement(
            c, item, edges[role], {face["role"]: face for face in raw_faces}, radial_roles
        )
    _require(c.operations - start <= 32768, "native_generated_trace_operation_limit")
    return {
        "side_roles": side_roles,
        "analytic_supports": "exact_checked_coefficients_and_ranges",
        "affine_trace_policy": "bounded_endpoint_residuals",
        "inferred_planar_projections": tuple(inferred),
        "oriented_cycle_indices": tuple(cycle_indices),
        "operations_start": start,
        "operations_end": c.operations,
    }
