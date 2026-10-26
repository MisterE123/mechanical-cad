"""Detached synthetic observations are data tests, never native success evidence."""

from __future__ import annotations

import ast
import copy
import math
from dataclasses import fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

from mechanical_cad.arc_profile_native_evidence import (
    bounded_evidence_bytes,
    check_masses,
    expected_edge_metadata,
    mass_limits,
    native_height,
    validate_edge_observation,
)
from mechanical_cad.arc_profile_native_plan import (
    NativeActualSupport,
    NativePlane,
    NativePlanError,
    NativeRadialDirection,
    _continue_actual_support,
    entry_context,
    prepare_native_geometry,
    transform,
)
from mechanical_cad.arc_profile_primitives import PrimitiveContext
from mechanical_cad.arc_profile_sector_source import (
    SectorArc,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
)


def frac(value):
    return Fraction(value.mantissa) * Fraction(2) ** value.exponent


@pytest.fixture(scope="module")
def plan():
    source = SectorGeometrySource(
        (
            SectorPoint("center", 0.0, 0.0),
            SectorPoint("start", 5.0, 0.0),
            SectorPoint("end", 0.0, 5.0),
        ),
        (SectorLine("radial_start", "center", "start"), SectorLine("radial_end", "center", "end")),
        (SectorArc("arc", "center", "start", "end", "ccw"),),
    )
    c = entry_context()
    plan = prepare_native_geometry(source, NativePlane(), context=c)
    directions = tuple(
        NativeRadialDirection(line.entity_id, transform(plan.frame, line.direction))
        for line in plan.lines
    )
    return _continue_actual_support(plan, directions, c)


def observation(plan, role="arc.arc", traversal="support"):
    """Deliberately synthetic field record, not an OCP observation."""
    ids, orientation = expected_edge_metadata(plan, role, traversal)
    arc = role.startswith("arc.")
    line = None if arc else next(line for line in plan.lines if role == f"line.{line.entity_id}")
    curve = {
        "kind": "circle" if arc else "line",
        "location": (*plan.center, 0.0),
        "direction": None if arc else (*line.direction, 0.0),
        "u": plan.frame.u if arc else None,
        "v": plan.frame.v if arc else None,
        "normal": plan.frame.normal if arc else None,
        "radius": plan.radius if arc else None,
        "range": plan.increasing_parameters if arc else (0.0, line.trim_parameter),
        "identity_location": True,
    }
    pcurve = copy.deepcopy(curve)
    for key in ("location", "direction", "u", "v"):
        if pcurve[key] is not None:
            pcurve[key] = pcurve[key][:2]
    pcurve["normal"] = None
    points = tuple(dict(plan.vertices)[identifier] for identifier in ids)
    location = {
        "identity": True,
        "matrix": ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0)),
    }
    representations = (
        {
            "index": 0,
            "representation_type": "BRep_Curve3D",
            "is_curve3d": True,
            "is_on_surface": False,
            "is_closed_surface": False,
            "surface_index": None,
            "surface_is_retained": False,
            "surface_fields": None,
            "location": location,
            "range": curve["range"],
            "curve3d": curve,
            "pcurves": (),
        },
        {
            "index": 1,
            "representation_type": "BRep_CurveOnSurface",
            "is_curve3d": False,
            "is_on_surface": True,
            "is_closed_surface": False,
            "surface_index": 0,
            "surface_is_retained": True,
            "surface_fields": {
                "kind": "Geom_Plane",
                "origin": plan.frame.origin,
                "u": plan.frame.u,
                "v": plan.frame.v,
                "normal": plan.frame.normal,
                "radius": None,
            },
            "location": location,
            "range": pcurve["range"],
            "curve3d": None,
            "pcurves": (pcurve,),
        },
    )
    return {
        "role": role,
        "curve": curve,
        "pcurve": pcurve,
        "stored_pcurve_count": 1,
        "stored_representation_count": 2,
        "retained_pcurve_count": 1,
        "selected_pcurve_index": 1,
        "representations": representations,
        "pcurve_surface_matches": True,
        "orientation": orientation,
        "expected_orientation": orientation,
        "endpoint_ids": ids,
        "expected_endpoint_ids": ids,
        "vertex_identity_matches": True,
        "edge_identity_matches": True,
        "vertex_coordinates": points,
        "vertex_parameters": curve["range"]
        if orientation == 0
        else tuple(reversed(curve["range"])),
        "edge_tolerance": 1e-7,
        "vertex_tolerances": (1e-7, 1e-7),
        "locations_identity": True,
        "evaluated_endpoints": points,
        "observed_distances": (0.0, 0.0),
        "equation_bounds_transfer": True,
    }


def check(plan, record, traversal="support"):
    validate_edge_observation(
        plan,
        "arc.arc",
        record,
        context=PrimitiveContext(),
        traversal=traversal,
        pcurve_required=True,
    )


@pytest.mark.parametrize("traversal", ["support", "boundary"])
def test_detached_synthetic_record_is_checked(plan, traversal):
    check(plan, observation(plan, traversal=traversal), traversal)


@pytest.mark.parametrize(
    "field,value",
    [
        ("orientation", 1),
        ("expected_orientation", 1),
        ("endpoint_ids", ("end", "start")),
        ("expected_endpoint_ids", ("end", "start")),
        ("vertex_identity_matches", False),
        ("edge_identity_matches", False),
        ("locations_identity", False),
        ("equation_bounds_transfer", False),
        ("stored_pcurve_count", 0),
        ("pcurve_surface_matches", False),
        ("edge_tolerance", math.nextafter(1e-7, math.inf)),
        ("vertex_tolerances", (1e-7, math.nextafter(1e-7, math.inf))),
        ("vertex_parameters", (0.0, 10.0)),
        ("evaluated_endpoints", ((5.000001, 0.0, 0.0), (0.0, 5.0, 0.0))),
        ("observed_distances", (1e-8, 0.0)),
        ("vertex_coordinates", ((5.0, 1.0, 0.0), (0.0, 5.0, 0.0))),
    ],
)
def test_forged_observation_rejects(plan, field, value):
    record = observation(plan)
    record[field] = value
    with pytest.raises(NativePlanError):
        check(plan, record)


def test_forging_both_expected_and_actual_metadata_rejects(plan):
    record = observation(plan)
    record["orientation"] = record["expected_orientation"] = 1
    record["endpoint_ids"] = record["expected_endpoint_ids"] = ("end", "start")
    record["vertex_coordinates"] = tuple(reversed(record["vertex_coordinates"]))
    record["vertex_parameters"] = tuple(reversed(record["vertex_parameters"]))
    with pytest.raises(NativePlanError, match="native_orientation_changed"):
        check(plan, record)


@pytest.mark.parametrize("target", ["curve", "pcurve"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("radius", math.nextafter(5.0, math.inf)),
        ("u", (0.0, 1.0, 0.0)),
        ("range", (math.tau, math.tau + math.pi / 2)),
        ("identity_location", False),
        ("location", (1.0, 0.0, 0.0)),
        ("kind", "spline"),
    ],
)
def test_actual_field_changes_are_not_fitted(plan, target, field, value):
    record = observation(plan)
    if target == "pcurve" and field in ("u", "location"):
        value = value[:2]
    record[target][field] = value
    with pytest.raises(NativePlanError):
        check(plan, record)


def test_exact_endpoint_check_does_not_trust_observed_distance(plan):
    record = observation(plan)
    record["evaluated_endpoints"] = ((6.0, 0.0, 0.0), (0.0, 5.0, 0.0))
    record["observed_distances"] = (0.0, 0.0)
    with pytest.raises(NativePlanError, match="native_evaluation_discrepancy"):
        check(plan, record)


class Hostile:
    def __eq__(self, other):
        raise AssertionError("custom equality must not run")

    def __hash__(self):
        return 1


@pytest.mark.parametrize("field", ["role", "endpoint_ids", "expected_endpoint_ids"])
def test_custom_metadata_is_not_compared(plan, field):
    record = observation(plan)
    record[field] = Hostile() if field == "role" else (Hostile(), "end")
    with pytest.raises(NativePlanError):
        check(plan, record)


def test_hostile_keys_and_oversized_record_reject(plan):
    record = observation(plan)
    record[Hostile()] = record.pop("role")
    with pytest.raises(NativePlanError):
        check(plan, record)
    record = observation(plan)
    record.update({f"extra{i}": 0 for i in range(1000)})
    with pytest.raises(NativePlanError):
        check(plan, record)


@pytest.mark.parametrize("traversal", [None, "authored", 0, Hostile()])
def test_stage_is_strict(plan, traversal):
    with pytest.raises(NativePlanError):
        expected_edge_metadata(plan, "arc.arc", traversal)


@pytest.mark.parametrize("height", [True, False, 0, -1, 1001, math.nan, math.inf, 1 << 10000, "1"])
def test_height_policy_is_strict(height):
    with pytest.raises(NativePlanError):
        native_height(height)


def test_fixed_r0_c0_formulas(plan):
    c = PrimitiveContext()
    target, ev, consistency = mass_limits(plan, 7, context=c)
    h, u, n = Fraction(7), Fraction(1, 2**53), 3
    ea = 128 * u * n * frac(plan.local_scale_squared) + 16 * u * frac(plan.world_scale) * frac(
        plan.source.area.perimeter.upper
    )
    assert frac(plan.area_allowance.lower) <= ea <= frac(plan.area_allowance.upper)
    a = (frac(plan.source_comparison_area.lower) + frac(plan.source_comparison_area.upper)) / 2
    ev_reference = (
        h * ea
        + 128 * u * n * frac(plan.local_scale_squared) * h
        + 16 * u * frac(plan.world_scale) * a
    )
    assert frac(ev.lower) <= ev_reference <= frac(ev.upper)
    assert frac(consistency.lower) <= ev_reference + h * ea <= frac(consistency.upper)
    assert frac(target.lower) <= h * frac(plan.source_comparison_area.lower)
    assert frac(target.upper) >= h * frac(plan.source_comparison_area.upper)
    actual_area = float(a)
    checked = check_masses(plan, actual_area, context=c, height=7, volume=actual_area * 7)
    assert checked.height == 7.0
    with pytest.raises(NativePlanError, match="native_volume_r0_failure"):
        check_masses(plan, actual_area, context=c, height=7, volume=actual_area * 7 + 1)


def test_kernel_accepts_only_source_and_freshly_classifies_before_continuation():
    tree = ast.parse(
        (Path(__file__).resolve().parents[2] / "src/mechanical_cad/kernel_ocp.py").read_text()
    )
    kernel = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OCPKernel"
    )
    method = next(
        node
        for node in kernel.body
        if isinstance(node, ast.FunctionDef) and node.name == "sector_profile"
    )
    assert [a.arg for a in method.args.args] == ["self", "sketch"]
    assert [a.arg for a in method.args.kwonlyargs] == ["context", "evidence_sink"]
    calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    classifiers = [node for node in calls if node.func.id == "classify_sector"]
    continuations = [node for node in calls if node.func.id == "_continue_native_plan"]
    assert len(classifiers) == len(continuations) == 1
    assert classifiers[0].lineno < continuations[0].lineno
    assert ast.unparse(classifiers[0]) == "classify_sector(sketch, context=c)"
    assert ast.unparse(continuations[0].args[0]) == "certificate.geometry"
    assert ast.unparse(continuations[0].args[2]) == "c"
    assert all(
        "entry_context" not in ast.unparse(node)
        for node in kernel.body
        if isinstance(node, ast.FunctionDef) and node.name in ("extrude_sector", "sector_evidence")
    )


def test_native_observation_never_falls_back_to_unproved_intent(plan):
    unproved = replace(plan, accepted_support=None)
    with pytest.raises(NativePlanError, match="unproved_native_support"):
        check(unproved, observation(plan))


def test_stored_pcurve_must_equal_proved_actual_3d(plan):
    record = observation(plan, "line.radial_start")
    record["pcurve"]["direction"] = (math.nextafter(1.0, 0.0), 0.0)
    with pytest.raises(NativePlanError, match="native_surface_trace_mismatch"):
        validate_edge_observation(
            plan,
            "line.radial_start",
            record,
            context=PrimitiveContext(),
            traversal="support",
            pcurve_required=True,
        )


@pytest.mark.parametrize("missing", [field.name for field in fields(NativeActualSupport)])
def test_incomplete_actual_support_record_rejects_controlled(plan, missing):
    incomplete = object.__new__(NativeActualSupport)
    for field in fields(NativeActualSupport):
        if field.name != missing:
            object.__setattr__(incomplete, field.name, getattr(plan.accepted_support, field.name))
    malformed = replace(plan, accepted_support=incomplete)
    with pytest.raises(NativePlanError, match="invalid_native_support_record"):
        check(malformed, observation(plan))


def test_actual_reproof_dominates_face_and_registration_with_one_context():
    tree = ast.parse(
        (Path(__file__).resolve().parents[2] / "src/mechanical_cad/kernel_ocp.py").read_text()
    )
    kernel = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OCPKernel"
    )
    method = next(
        node
        for node in kernel.body
        if isinstance(node, ast.FunctionDef) and node.name == "sector_profile"
    )
    calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)]
    proofs = [
        node
        for node in calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "_continue_actual_support_for_vertices"
    ]
    assert len(proofs) == 1
    proof = proofs[0]
    assert (
        ast.unparse(proof)
        == "_continue_actual_support_for_vertices(plan, tuple(actual_directions), c)"
    )
    faces = [
        node
        for node in calls
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"MakeFace", "_remember"}
    ]
    assert len(faces) == 2 and all(proof.lineno < node.lineno for node in faces)
    constructors = [
        node
        for node in calls
        if isinstance(node.func, ast.Name) and node.func.id == "NativeRadialDirection"
    ]
    assert len(constructors) == 1
    assert (
        ast.unparse(constructors[0])
        == "NativeRadialDirection(line.entity_id, support['direction'])"
    )
    assert constructors[0].lineno < proof.lineno


def detached_record(value=""):
    return {
        "events": [{"stage": "synthetic", "value": value, "operations": 0}],
        "operation": "curve_profile",
        "operations_start": 0,
    }


def test_complete_evidence_limit_is_exact_and_never_truncates():
    record = detached_record()
    overhead = len(bounded_evidence_bytes(record))
    value = "x" * (1_048_576 - overhead)
    record["events"][0]["value"] = value
    assert len(bounded_evidence_bytes(record)) == 1_048_576
    record["events"][0]["value"] += "x"
    with pytest.raises(NativePlanError, match="native_evidence_limit"):
        bounded_evidence_bytes(record)
    assert record["events"][0]["value"] == value + "x"


@pytest.mark.parametrize("value", [math.inf, math.nan, Hostile(), {Hostile(): 1}])
def test_complete_evidence_rejects_nonfinite_or_hook_values(value):
    with pytest.raises(NativePlanError, match="invalid_native_evidence"):
        bounded_evidence_bytes(detached_record(value))


@pytest.mark.parametrize("kind", ["events", "depth", "nodes", "integer", "keys", "string"])
def test_complete_evidence_collection_is_bounded(kind):
    record = detached_record()
    if kind == "events":
        record["events"] *= 65
    elif kind == "depth":
        value = []
        value.append(value)
        record["events"][0]["value"] = value
    elif kind == "nodes":
        record["events"][0]["value"] = [[0] * 256] * 256
    elif kind == "integer":
        record["events"][0]["value"] = 1 << 65536
    elif kind == "keys":
        record["events"][0]["value"] = {str(i): i for i in range(65)}
    else:
        record["events"][0]["value"] = "x" * 1_048_577
    with pytest.raises(NativePlanError, match="native_evidence_limit"):
        bounded_evidence_bytes(record)


def test_complete_evidence_root_unknown_fields_reject():
    record = detached_record()
    record["unapproved"] = True
    with pytest.raises(NativePlanError, match="invalid_native_evidence"):
        bounded_evidence_bytes(record)


def test_evidence_bound_dominates_registration_and_detached_return():
    tree = ast.parse(
        (Path(__file__).resolve().parents[2] / "src/mechanical_cad/kernel_ocp.py").read_text()
    )
    kernel = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OCPKernel")
    for name in ("sector_profile", "extrude_sector", "sector_evidence"):
        method = next(n for n in kernel.body if isinstance(n, ast.FunctionDef) and n.name == name)
        checks = [
            n.lineno
            for n in ast.walk(method)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "bounded_evidence_bytes"
        ]
        assert checks
        if name == "sector_evidence":
            result = next(n for n in ast.walk(method) if isinstance(n, ast.Return))
            assert min(checks) < result.lineno
        else:
            registration = next(
                n
                for n in ast.walk(method)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "_remember"
            )
            assert max(checks) < registration.lineno


def test_event_bound_precedes_collection_and_callback_and_does_not_recurse_on_overflow():
    tree = ast.parse(
        (Path(__file__).resolve().parents[2] / "src/mechanical_cad/kernel_ocp.py").read_text()
    )
    kernel = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OCPKernel")
    for name in ("sector_profile", "extrude_sector"):
        method = next(n for n in kernel.body if isinstance(n, ast.FunctionDef) and n.name == name)
        event = next(n for n in method.body if isinstance(n, ast.FunctionDef) and n.name == "event")
        calls = [n for n in ast.walk(event) if isinstance(n, ast.Call)]
        bound = next(
            n
            for n in calls
            if isinstance(n.func, ast.Name) and n.func.id == "bounded_evidence_bytes"
        )
        append = next(
            n for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr == "append"
        )
        callback = next(
            n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "evidence_sink"
        )
        assert bound.lineno < append.lineno < callback.lineno
        handler = next(n for n in ast.walk(method) if isinstance(n, ast.ExceptHandler))
        assert isinstance(handler.body[0], ast.If)
        assert "native_evidence_limit" in ast.unparse(handler.body[0].test)
        assert isinstance(handler.body[0].body[0], ast.Raise)


@pytest.fixture
def mapped_vertex_observations():
    """Synthetic q values only; this does not establish native identity."""
    from mechanical_cad.arc_profile_native_plan import (
        NativeEndpointObservation,
        _continue_actual_support_for_vertices,
        _continue_vertex_representation,
    )

    source = SectorGeometrySource(
        (
            SectorPoint("center", 0.0, 0.0),
            SectorPoint("start", 5.0, 0.0),
            SectorPoint("end", 0.0, 5.0 - 2**-31),
        ),
        (SectorLine("radial_start", "center", "start"), SectorLine("radial_end", "center", "end")),
        (SectorArc("arc", "center", "start", "end", "ccw"),),
    )
    context = entry_context()
    intended = prepare_native_geometry(source, NativePlane(), context=context)
    directions = tuple(
        NativeRadialDirection(line.entity_id, transform(intended.frame, line.direction))
        for line in intended.lines
    )
    plan, continuation = _continue_actual_support_for_vertices(intended, directions, context)
    observations = tuple(
        NativeEndpointObservation(
            line.point_id,
            parameter,
            transform(
                plan.frame,
                tuple(
                    float(Fraction(center) + (frac(box.lower) + frac(box.upper)) / 2)
                    for center, box in zip(plan.center, vector, strict=True)
                ),
            ),
        )
        for line, parameter, vector in zip(
            plan.lines, plan.parameters, plan.circle_vectors, strict=True
        )
    )
    representatives = _continue_vertex_representation(
        plan, observations, context, continuation=continuation
    )
    return plan, representatives, context


def mapped_observation(plan, representatives, role):
    value = observation(plan, role)
    value["curve_support_identity_matches"] = True
    value["vertex_coordinates"] = tuple(
        dict(representatives.vertices)[identifier] for identifier in value["endpoint_ids"]
    )
    value["evaluated_endpoints"] = value["vertex_coordinates"]
    return value


@pytest.mark.parametrize("role", ("arc.arc", "line.radial_start", "line.radial_end"))
def test_representative_bound_observation_preserves_authored_and_native_checks(
    mapped_vertex_observations, role
):
    plan, representatives, context = mapped_vertex_observations
    value = mapped_observation(plan, representatives, role)
    validate_edge_observation(
        plan,
        role,
        value,
        context=context,
        traversal="support",
        pcurve_required=True,
        representatives=representatives,
    )
    assert dict(plan.vertices)["end"] != dict(representatives.vertices)["end"]


def test_authored_vertex_substitution_cannot_replace_frozen_q(mapped_vertex_observations):
    plan, representatives, context = mapped_vertex_observations
    value = mapped_observation(plan, representatives, "arc.arc")
    value["vertex_coordinates"] = tuple(
        dict(plan.vertices)[identifier] for identifier in value["endpoint_ids"]
    )
    with pytest.raises(NativePlanError, match="native_vertex_changed"):
        validate_edge_observation(
            plan,
            "arc.arc",
            value,
            context=context,
            traversal="support",
            pcurve_required=True,
            representatives=representatives,
        )


def test_arc_repeated_evaluation_must_reproduce_frozen_q_exactly(mapped_vertex_observations):
    plan, representatives, context = mapped_vertex_observations
    value = mapped_observation(plan, representatives, "arc.arc")
    point = value["evaluated_endpoints"][1]
    value["evaluated_endpoints"] = (
        value["evaluated_endpoints"][0],
        (point[0], math.nextafter(point[1], math.inf), point[2]),
    )
    with pytest.raises(NativePlanError, match="native_circle_evaluation_changed"):
        validate_edge_observation(
            plan,
            "arc.arc",
            value,
            context=context,
            traversal="support",
            pcurve_required=True,
            representatives=representatives,
        )


@pytest.mark.parametrize(
    "target,code",
    (
        ("authored", "native_evaluation_discrepancy"),
        ("representative", "native_representative_evaluation_discrepancy"),
    ),
)
def test_both_endpoint_distance_checks_are_independent_of_zero_reported_distance(
    mapped_vertex_observations, target, code
):
    plan, representatives, context = mapped_vertex_observations
    value = mapped_observation(plan, representatives, "line.radial_end")
    authored = dict(plan.vertices)["end"]
    q = dict(representatives.vertices)["end"]
    changed = (
        (q[0], q[1] + 9e-10, q[2])
        if target == "authored"
        else (authored[0], authored[1] - 9e-10, authored[2])
    )
    value["evaluated_endpoints"] = (value["evaluated_endpoints"][0], changed)
    value["observed_distances"] = (0.0, 0.0)
    with pytest.raises(NativePlanError, match=code):
        validate_edge_observation(
            plan,
            "line.radial_end",
            value,
            context=context,
            traversal="support",
            pcurve_required=True,
            representatives=representatives,
        )


@pytest.mark.parametrize("value", [False, 1, None, "true"])
def test_representative_arc_requires_strict_observed_retained_support_identity(
    mapped_vertex_observations, value
):
    plan, representatives, context = mapped_vertex_observations
    record = mapped_observation(plan, representatives, "arc.arc")
    record["curve_support_identity_matches"] = value
    with pytest.raises(NativePlanError, match="native_curve_support_identity_changed"):
        validate_edge_observation(
            plan,
            "arc.arc",
            record,
            context=context,
            traversal="support",
            pcurve_required=True,
            representatives=representatives,
        )


def test_representative_arc_rejects_missing_support_identity(mapped_vertex_observations):
    plan, representatives, context = mapped_vertex_observations
    record = mapped_observation(plan, representatives, "arc.arc")
    del record["curve_support_identity_matches"]
    with pytest.raises(NativePlanError, match="native_evidence_incomplete"):
        validate_edge_observation(
            plan,
            "arc.arc",
            record,
            context=context,
            traversal="support",
            pcurve_required=True,
            representatives=representatives,
        )
