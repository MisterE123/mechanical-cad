"""Native-free canonical vertex mapping and independent rational controls.

Every q here is an explicitly SYNTHETIC interval-midpoint witness, never a
native Circle.Value observation and never a permitted production fallback.
These tests do not establish live handle identity or native mass accuracy.
"""

from __future__ import annotations

import hashlib
import importlib.abc
import inspect
import math
import sys
from dataclasses import FrozenInstanceError, asdict, replace
from fractions import Fraction as F

import pytest

import mechanical_cad.arc_profile_native_evidence as evidence
import mechanical_cad.arc_profile_native_plan as native
from mechanical_cad.arc_profile_primitives import Dyadic, PrimitiveContext, PrimitiveError
from mechanical_cad.arc_profile_sector_policy import ExactRatio
from mechanical_cad.arc_profile_sector_source import (
    SectorArc,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
)


class NoNativeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (
            fullname.split(".")[0]
            in {"OCP", "OCC", "cadquery", "slvs", "bpy", "bmesh", "mathutils"}
            or fullname == "mechanical_cad.kernel_ocp"
        ):
            raise AssertionError(f"native import forbidden in mapping tests: {fullname}")
        return None


@pytest.fixture(autouse=True)
def no_native_imports():
    blocker = NoNativeImports()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


def fraction(value):
    if type(value) is Dyadic:
        return F(value.mantissa) * F(2) ** value.exponent
    if type(value) is ExactRatio:
        return fraction(value.numerator) / fraction(value.denominator)
    return F(value)


def source(*, center=(0.0, 0.0), start=(5.0, 0.0), end=(0.0, 5.0), direction="ccw"):
    return SectorGeometrySource(
        (SectorPoint("c", *center), SectorPoint("a", *start), SectorPoint("b", *end)),
        (SectorLine("radius_a", "c", "a"), SectorLine("radius_b", "c", "b")),
        (SectorArc("arc", "c", "a", "b", direction),),
    )


def radial_observations(plan, *, normalize=False):
    records = []
    for line in plan.lines:
        d = line.direction
        if normalize:
            divisor = math.sqrt(sum(x * x for x in d))
            d = tuple(x / divisor for x in d)
        records.append(
            native.NativeRadialDirection(line.entity_id, native.transform(plan.frame, d))
        )
    return tuple(records)


def synthetic_midpoint_observations(plan, *, frozen_vectors=None):
    """Detached test-only q. Production must observe its sole native candidate."""
    vectors = plan.circle_vectors if frozen_vectors is None else frozen_vectors
    observations = []
    for line, parameter, vector in zip(plan.lines, plan.parameters, vectors, strict=True):
        local = tuple(
            float(F(center) + (fraction(component.lower) + fraction(component.upper)) / 2)
            for center, component in zip(plan.center, vector, strict=True)
        )
        observations.append(
            native.NativeEndpointObservation(
                line.point_id, parameter, native.transform(plan.frame, local)
            )
        )
    return tuple(observations)


_CONTINUATIONS = {}


def continue_mapping(plan, observations, context):
    return native._continue_vertex_representation(
        plan, observations, context, continuation=_CONTINUATIONS[id(plan)]
    )


def prepare_support(value=None, plane=None, *, normalize=False, context=None):
    value = source() if value is None else value
    plane = native.NativePlane() if plane is None else plane
    c = native.entry_context(context)
    intended = native.prepare_native_geometry(value, plane, context=c)
    directions = radial_observations(intended, normalize=normalize)
    accepted, continuation = native._continue_actual_support_for_vertices(intended, directions, c)
    _CONTINUATIONS[id(accepted)] = continuation
    return value, plane, intended, accepted, directions, c


def prepare(value=None, plane=None, *, normalize=False, context=None):
    value, plane, intended, plan, directions, c = prepare_support(
        value, plane, normalize=normalize, context=context
    )
    observations = synthetic_midpoint_observations(plan)
    before = native.plan_bytes(plan)
    representation = continue_mapping(plan, observations, c)
    assert native.plan_bytes(plan) == before
    return value, plane, intended, plan, directions, observations, representation, c


def inverse(frame, world):
    return tuple(
        sum(F(x) * F(a) for x, a in zip(world, axis, strict=True))
        for axis in (frame.u, frame.v, frame.normal)
    )


def independent_mapping_oracle(plan, observations):
    """Fraction-only coordinate, Delta, frozen-cell, and finite-line checks."""
    n = fraction(plan.final_cell_radius.numerator)
    k = fraction(plan.final_cell_radius.denominator)
    assert n > 0 and k > 0
    arc = plan.source.incidence.arc
    rows = []
    for index, (record, authored) in enumerate(
        zip(observations, (arc.start, arc.end), strict=True)
    ):
        local = inverse(plan.frame, record.world_point)
        assert local[2] == 0
        q = tuple(x - F(y) for x, y in zip(local[:2], plan.center, strict=True))
        p = tuple(F(x) - F(y) for x, y in zip(authored, plan.center, strict=True))
        delta = tuple(x - y for x, y in zip(q, p, strict=True))
        auth2 = sum(x * x for x in delta)
        assert 10**18 * auth2 <= 1
        assert k * k * auth2 < n * n
        box2 = sum(
            max(abs(x - fraction(interval.lower)), abs(x - fraction(interval.upper))) ** 2
            for x, interval in zip(q, plan.circle_vectors[index], strict=True)
        )
        g = fraction(plan.circle_gaps[index].upper)
        assert box2 <= F(1, 10**18)
        assert n / k - g > 0 and box2 < (n / k - g) ** 2
        line2 = []
        for line in (plan.lines[index], plan.accepted_support.lines[index]):
            a = tuple(F(plan.radius) * F(d) for d in line.direction)
            displacement2 = sum((x - y) ** 2 for x, y in zip(q, a, strict=True))
            assert 10**18 * displacement2 <= 1
            error2 = sum((x - y) ** 2 for x, y in zip(a, p, strict=True))
            assert fraction(line.affine_error_squared) == error2
            assert k * k * error2 < n * n
            line2.append(displacement2)
        rows.append((q, delta, auth2, box2, tuple(line2)))
    return tuple(rows)


def assert_witness_oracle(plan, observations, representation, oracle=None):
    oracle = independent_mapping_oracle(plan, observations) if oracle is None else oracle
    n = fraction(plan.final_cell_radius.numerator)
    k = fraction(plan.final_cell_radius.denominator)
    for index, (record, witness, row) in enumerate(
        zip(observations, representation.endpoints, oracle, strict=True)
    ):
        q, authored_delta, auth2, box2, line2 = row
        assert witness.observation is record
        assert (
            tuple(map(fraction, witness.local_point)) == inverse(plan.frame, record.world_point)[:2]
        )
        assert fraction(witness.local_normal) == 0
        assert tuple(map(fraction, witness.centered_point)) == q
        assert tuple(map(fraction, witness.authored_delta)) == authored_delta
        assert fraction(witness.authored_distance_squared) == auth2
        assert fraction(witness.authored_cell_margin) == n * n - k * k * auth2 > 0
        for component, circle, delta in zip(
            q, plan.circle_vectors[index], witness.circle_delta, strict=True
        ):
            assert fraction(delta.lower) <= component - fraction(circle.upper)
            assert fraction(delta.upper) >= component - fraction(circle.lower)
        error = fraction(witness.circle_error.upper)
        assert error >= 0 and error * error >= box2
        assert 10**9 * error <= 1
        assert (
            fraction(witness.circle_cell_margin)
            == n - k * (fraction(plan.circle_gaps[index].upper) + error)
            > 0
        )
        assert witness.authored_resources.operations_start == witness.resources.operations_start
        assert (
            witness.authored_resources.operations_end == witness.circle_resources.operations_start
        )
        assert (
            witness.circle_resources.operations_end
            == witness.intended_line.resources.operations_start
        )
        assert (
            witness.intended_line.resources.operations_end
            == witness.actual_line.resources.operations_start
        )
        assert witness.actual_line.resources.operations_end == witness.resources.operations_end
        for role, line, proof, expected in zip(
            ("intended", "actual"),
            (plan.lines[index], plan.accepted_support.lines[index]),
            (witness.intended_line, witness.actual_line),
            line2,
            strict=True,
        ):
            endpoint = tuple(F(plan.radius) * F(d) for d in line.direction)
            assert (proof.role, proof.entity_id, proof.point_id) == (
                role,
                line.entity_id,
                line.point_id,
            )
            assert tuple(map(fraction, proof.endpoint_vector)) == endpoint
            assert tuple(map(fraction, proof.representative_delta)) == tuple(
                x - y for x, y in zip(q, endpoint, strict=True)
            )
            assert fraction(proof.distance_squared) == expected
            assert fraction(proof.authored_distance_squared) == fraction(line.affine_error_squared)
            assert (
                fraction(proof.cell_margin)
                == n * n - k * k * fraction(line.affine_error_squared)
                > 0
            )
    assert (
        representation.endpoints[0].resources.operations_end
        == representation.endpoints[1].resources.operations_start
    )
    assert (
        representation.endpoints[-1].resources.operations_end
        == representation.resources.operations_end
    )


CASES = (
    ("cardinal_zero", {}, (1.0, 0.0, 0.0, 0.0)),
    ("pythagorean", {"start": (3.0, 4.0), "end": (-4.0, 3.0)}, (1.0, 0.0, 0.0, 0.0)),
    ("rounded_noncardinal", {"start": (13.0, 29.0), "end": (-29.0, 13.0)}, (1.0, 0.0, 0.0, 0.0)),
    ("positive_gap", {"end": (0.0, 5.0 + 2**-31)}, (1.0, 0.0, 0.0, 0.0)),
    ("inward_gap", {"end": (0.0, 5.0 - 2**-31)}, (1.0, 0.0, 0.0, 0.0)),
    (
        "nonzero_center",
        {"center": (17.0, -29.0), "start": (20.0, -25.0), "end": (13.0, -26.0)},
        (0.5, 0.5, 0.5, 0.5),
    ),
    (
        "near_coordinate_limit",
        {
            "center": (999000.0, 999000.0),
            "start": (999003.0, 999004.0),
            "end": (998996.0, 999003.0),
        },
        (1.0, 0.0, 0.0, 0.0),
    ),
    ("decimal_radius", {"start": (5.1, 0.0), "end": (0.0, 5.1)}, (0.5, -0.5, 0.5, 0.5)),
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case[0])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("normalize", [False, True], ids=["intended", "synthetic_once"])
def test_synthetic_mapping_exact_oracles_and_unchanged_plan(case, direction, normalize):
    _, options, quaternion = case
    result = prepare(
        source(**options, direction=direction),
        native.NativePlane(quaternion=quaternion),
        normalize=normalize,
    )
    _, _, intended, plan, _, observations, representation, c = result
    independent_mapping_oracle(plan, observations)
    assert_witness_oracle(plan, observations, representation)
    assert plan.vertices is intended.vertices
    assert plan.source is intended.source
    assert plan.final_source_cells is intended.final_source_cells
    assert plan.circle_vectors is intended.circle_vectors
    assert plan.circle_gaps is intended.circle_gaps
    assert representation.source_geometry_sha256 == plan.source.geometry_sha256
    assert (
        representation.intended_plan_sha256
        == hashlib.sha256(native.plan_bytes(intended)).hexdigest()
    )
    assert (
        representation.accepted_plan_sha256 == hashlib.sha256(native.plan_bytes(plan)).hexdigest()
    )
    assert representation.precision == plan.source.area.precision == plan.accepted_support.precision
    assert (
        representation.resources.operations_start == plan.accepted_support.resources.operations_end
    )
    assert representation.resources.operations_end == c.operations <= 200_000
    assert (
        0
        < representation.resources.operations_end - representation.resources.operations_start
        <= 4096
    )
    assert representation.resources.max_bits == c.max_bits
    assert representation.resources.max_operations == c.max_operations
    assert len(representation.endpoints) == 2
    assert len(native.vertex_representation_bytes(representation)) <= 1_048_576
    assert len(native.plan_bytes(plan)) <= 1_048_576
    assert native.root_counts(plan) == ((60, 4, 64) if plan.source.cells else (52, 4, 56))
    center = plan.source.incidence.arc.center_id
    assert (
        native.native_vertex_coordinates(plan, representation, center)
        == dict(plan.vertices)[center]
    )
    for observation in observations:
        returned = native.native_vertex_coordinates(plan, representation, observation.point_id)
        assert returned is observation.world_point
        assert tuple(x.hex() for x in returned) == tuple(x.hex() for x in observation.world_point)


def test_zero_source_cell_does_not_invent_a_source_disk():
    _, _, _, plan, _, observations, representation, _ = prepare()
    assert fraction(plan.source.source_cell_radius) == 0
    assert plan.source.cells == ()
    assert fraction(plan.final_cell_radius) > 0
    independent_mapping_oracle(plan, observations)
    assert native.retained_root_count(plan) == 56
    assert len(representation.vertices) == 3


def test_positive_source_cell_keeps_all_64_roots_and_mass_limits():
    value = source(end=(0.0, 5.0 - 2**-31))
    _, _, intended, plan, _, observations, _, c = prepare(value)
    assert fraction(plan.source.source_cell_radius) > 0
    assert native.retained_root_count(plan) == 64
    independent_mapping_oracle(plan, observations)
    before = native.plan_bytes(plan)
    limits = evidence.mass_limits(plan, 1000.0, context=c)
    independent_context = native.entry_context()
    expected = evidence.mass_limits(plan, 1000.0, context=independent_context)
    assert limits == expected and native.plan_bytes(plan) == before
    midpoint = float(
        (fraction(plan.source_comparison_area.lower) + fraction(plan.source_comparison_area.upper))
        / 2
    )
    checked = evidence.check_masses(
        plan, midpoint, height=1000.0, volume=midpoint * 1000.0, context=c
    )
    assert checked.area_allowance == plan.area_allowance
    assert c.operations <= 200_000
    actual = plan.accepted_support
    roots = actual.lines[0].support_circle_roots
    extra = replace(roots, parameters=roots.parameters + roots.parameters[:1])
    lines = (replace(actual.lines[0], support_circle_roots=extra), actual.lines[1])
    with pytest.raises(native.NativePlanError, match="^auxiliary_root_limit$"):
        native.retained_root_count(
            intended, actual.radial_disk_roots, actual.center_proxy_roots, lines
        )


def test_existing_small_profile_rejection_is_preserved_before_mapping():
    with pytest.raises(native.NativePlanError, match="^unsupported_profile_scale$"):
        prepare(source(start=(0.0001, 0.0), end=(0.0, 0.0001)))


@pytest.mark.parametrize("normalize", [False, True])
def test_public_entry_recomputes_source_and_support_once_without_caller_cache(
    monkeypatch, normalize
):
    (
        value,
        plane,
        _,
        plan,
        directions,
        _,
    ) = prepare_support(normalize=normalize)
    records = synthetic_midpoint_observations(plan)
    original = native.classify_sector_geometry
    calls = []

    def counted(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(native, "classify_sector_geometry", counted)
    c = native.entry_context()
    for _ in range(17):
        c._tick()
    result, representation = native.prepare_native_vertex_representation(
        value, plane, directions, records, context=c
    )
    assert len(calls) == 1 and calls[0][0] == (value,)
    assert calls[0][1]["context"] is c
    assert result is not plan and result.source is not plan.source
    assert result.source.resources.operations_start == 17
    assert representation.resources.operations_end == c.operations
    parameters = inspect.signature(native.prepare_native_vertex_representation).parameters
    assert not set(parameters) & {
        "plan",
        "certificate",
        "cache",
        "representation",
        "distance",
        "sha256",
    }


@pytest.mark.parametrize("kind", ["plan", "certificate", "representation", "dictionary"])
def test_public_entry_rejects_caller_proof_as_source(kind):
    value, plane, _, plan, directions, records, representation, _ = prepare()
    authority = {
        "plan": plan,
        "certificate": plan.source,
        "representation": representation,
        "dictionary": asdict(plan),
    }[kind]
    with pytest.raises(ValueError):
        native.prepare_native_vertex_representation(authority, plane, directions, records)
    assert value is not authority


@pytest.mark.parametrize("mutation", ["reversed", "foreign", "duplicate", "center"])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_exact_authored_owner_order_is_required(mutation, direction):
    _, _, _, plan, _, c = prepare_support(source(direction=direction))
    records = synthetic_midpoint_observations(plan)
    if mutation == "reversed":
        records = records[::-1]
    else:
        wrong = {"foreign": "other", "duplicate": records[1].point_id, "center": "c"}[mutation]
        records = (replace(records[0], point_id=wrong), records[1])
    with pytest.raises(native.NativePlanError, match="^native_vertex_owner_changed$"):
        continue_mapping(plan, records, c)


@pytest.mark.parametrize("mutation", ["neighbor", "period", "swapped", "negative_zero"])
def test_exact_parameter_and_binary64_sign_are_required(mutation):
    _, _, _, plan, _, c = prepare_support()
    records = synthetic_midpoint_observations(plan)
    wrong = {
        "neighbor": math.nextafter(records[0].parameter, math.inf),
        "period": records[0].parameter + math.tau,
        "swapped": records[1].parameter,
        "negative_zero": -0.0,
    }[mutation]
    assert wrong.hex() != records[0].parameter.hex()
    records = (replace(records[0], parameter=wrong), records[1])
    with pytest.raises(native.NativePlanError, match="^native_vertex_parameter_changed$"):
        continue_mapping(plan, records, c)


@pytest.mark.parametrize(
    "mutation", ["off_plane", "wrong_frame", "missing_center", "double_center"]
)
def test_inverse_frame_and_exact_single_center_subtraction(mutation):
    value = source(center=(17.0, -29.0), start=(20.0, -25.0), end=(13.0, -26.0))
    _, _, _, plan, _, c = prepare_support(
        value, native.NativePlane(quaternion=(0.5, 0.5, 0.5, 0.5))
    )
    records = synthetic_midpoint_observations(plan)
    local = inverse(plan.frame, records[0].world_point)[:2]
    if mutation == "off_plane":
        q = tuple(
            x + math.ulp(0.0) * n
            for x, n in zip(records[0].world_point, plan.frame.normal, strict=True)
        )
        code = "native_vertex_off_plane"
    elif mutation == "wrong_frame":
        q = (float(local[0]), float(local[1]), 0.0)
        code = "native_vertex_off_plane"
    else:
        sign = -1 if mutation == "missing_center" else 1
        q = native.transform(
            plan.frame,
            tuple(float(x + sign * F(y)) for x, y in zip(local, plan.center, strict=True)),
        )
        code = "native_vertex_authored_discrepancy"
    records = (replace(records[0], world_point=q), records[1])
    with pytest.raises(native.NativePlanError, match=f"^{code}$"):
        continue_mapping(plan, records, c)


class DerivedFloat(float):
    pass


class DerivedString(str):
    pass


class DerivedTuple(tuple):
    pass


BAD_FIELDS = (
    ("point_id", ""),
    ("point_id", "x" * 257),
    ("point_id", True),
    ("point_id", DerivedString("a")),
    ("parameter", 0),
    ("parameter", True),
    ("parameter", F(0)),
    ("parameter", math.nan),
    ("parameter", math.inf),
    ("parameter", DerivedFloat(0.0)),
    ("world_point", [5.0, 0.0, 0.0]),
    ("world_point", (5.0, 0.0)),
    ("world_point", (5.0, 0.0, 0.0, 0.0)),
    ("world_point", DerivedTuple((5.0, 0.0, 0.0))),
    ("world_point", (5, 0.0, 0.0)),
    ("world_point", (True, 0.0, 0.0)),
    ("world_point", (math.nan, 0.0, 0.0)),
    ("world_point", (math.inf, 0.0, 0.0)),
    ("world_point", (DerivedFloat(5.0), 0.0, 0.0)),
    ("world_point", (1 << 100_000, 0.0, 0.0)),
    ("world_point", (math.nextafter(1_000_000.0, math.inf), 0.0, 0.0)),
    ("world_point", (math.nextafter(-1_000_000.0, -math.inf), 0.0, 0.0)),
)


@pytest.mark.parametrize(
    "field,bad", BAD_FIELDS, ids=[f"{name}-{i}" for i, (name, _) in enumerate(BAD_FIELDS)]
)
def test_observation_has_exact_bounded_scalar_and_container_grammar(field, bad):
    _, _, _, plan, _, c = prepare_support()
    records = synthetic_midpoint_observations(plan)
    records = (replace(records[0], **{field: bad}), records[1])
    with pytest.raises(native.NativePlanError, match="^invalid_native_endpoint_observation$"):
        continue_mapping(plan, records, c)


@pytest.mark.parametrize(
    "kind", ["list", "short", "long", "subclass", "generator", "none", "mapping"]
)
def test_endpoint_table_is_exact_two_tuple(kind):
    _, _, _, plan, _, c = prepare_support()
    records = synthetic_midpoint_observations(plan)
    bad = {
        "list": list(records),
        "short": records[:1],
        "long": records + records[:1],
        "subclass": DerivedTuple(records),
        "generator": iter(records),
        "none": None,
        "mapping": {r.point_id: r for r in records},
    }[kind]
    with pytest.raises(native.NativePlanError, match="^invalid_native_endpoint_observation$"):
        continue_mapping(plan, bad, c)


@pytest.mark.parametrize(
    "missing", ["point_id", "parameter", "world_point", "all", "subclass", "dict"]
)
def test_endpoint_record_is_exact_and_has_all_slots(missing):
    _, _, _, plan, _, c = prepare_support()
    records = synthetic_midpoint_observations(plan)
    if missing == "dict":
        bad = asdict(records[0])
    elif missing == "subclass":

        class Derived(native.NativeEndpointObservation):
            pass

        bad = Derived(records[0].point_id, records[0].parameter, records[0].world_point)
    else:
        bad = object.__new__(native.NativeEndpointObservation)
        for name in ("point_id", "parameter", "world_point"):
            if missing not in (name, "all"):
                object.__setattr__(bad, name, getattr(records[0], name))
    with pytest.raises(native.NativePlanError, match="^invalid_native_endpoint_observation$"):
        continue_mapping(plan, (bad, records[1]), c)


@pytest.mark.parametrize("which", ["inside", "outside"])
def test_exact_rational_delta_neighbors_without_rounded_epsilon(which):
    # Delta=1/10**9 is not dyadic. Its neighboring binary64 values, rather than
    # a mislabeled "exact float boundary", exercise the exact <= predicate.
    above = 1e-9
    below = math.nextafter(above, 0.0)
    assert F(below) < F(1, 10**9) < F(above)
    value = source(end=(0.0, 5.0 + 2**-31))
    _, _, _, plan, _, c = prepare_support(value)
    records = synthetic_midpoint_observations(plan)
    displacement = below if which == "inside" else above
    records = (replace(records[0], world_point=(5.0, displacement, 0.0)), records[1])
    if which == "inside":
        continue_mapping(plan, records, c)
        independent_mapping_oracle(plan, records)
    else:
        with pytest.raises(native.NativePlanError, match="^native_vertex_authored_discrepancy$"):
            continue_mapping(plan, records, c)


@pytest.mark.parametrize("mutation", ["spent", "reset", "clone", "limits", "subclass", "none"])
def test_private_continuation_requires_identical_unspent_context(mutation):
    _, _, _, plan, _, c = prepare_support()
    records = synthetic_midpoint_observations(plan)
    if mutation == "spent":
        c._tick()
    elif mutation == "reset":
        object.__setattr__(c, "_operations", 0)
    elif mutation in ("clone", "limits"):
        replacement = PrimitiveContext(max_operations=200_000 if mutation == "clone" else 199_999)
        object.__setattr__(replacement, "_operations", c.operations)
        c = replacement
    elif mutation == "subclass":

        class Derived(PrimitiveContext):
            pass

        replacement = Derived(max_operations=200_000)
        object.__setattr__(replacement, "_operations", c.operations)
        c = replacement
    elif mutation == "none":
        c = None
    with pytest.raises(native.NativePlanError, match="^native_context_discontinuity$"):
        continue_mapping(plan, records, c)


def test_lower_cap_exhaustion_preserves_every_spent_tick():
    _, _, _, reference, _, _ = prepare_support()
    cap = reference.accepted_support.resources.operations_end + 1
    c = PrimitiveContext(max_operations=cap)
    _, _, _, plan, _, c = prepare_support(context=c)
    records = synthetic_midpoint_observations(plan)
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        continue_mapping(plan, records, c)
    assert c.operations == c.max_operations == cap < 200_000


def test_public_entry_does_not_reset_exhausted_caller_budget():
    value, plane, _, plan, directions, _ = prepare_support()
    records = synthetic_midpoint_observations(plan)
    c = PrimitiveContext(max_operations=1)
    c._tick()
    with pytest.raises(ValueError):
        native.prepare_native_vertex_representation(value, plane, directions, records, context=c)
    assert c.operations == c.max_operations == 1


def test_mapping_record_is_frozen_and_mutated_coordinates_cannot_be_rebound():
    _, _, _, plan, _, observations, representation, _ = prepare()
    with pytest.raises(FrozenInstanceError):
        representation.vertices = ()
    changed = list(representation.vertices)
    outer_index = next(
        i for i, (point_id, _) in enumerate(changed) if point_id == observations[0].point_id
    )
    old_id, old_point = changed[outer_index]
    changed[outer_index] = (old_id, (math.nextafter(old_point[0], math.inf), *old_point[1:]))
    forged = replace(representation, vertices=tuple(changed))
    with pytest.raises(native.NativePlanError):
        native.native_vertex_coordinates(plan, forged, old_id)


@pytest.mark.parametrize(
    "field", ["source_geometry_sha256", "intended_plan_sha256", "accepted_plan_sha256", "precision"]
)
def test_mapping_digest_binds_source_plans_and_precision(field):
    _, _, _, plan, _, observations, representation, _ = prepare()
    old = getattr(representation, field)
    forged = replace(representation, **{field: ("0" * 64 if type(old) is str else old + 1)})
    with pytest.raises(native.NativePlanError):
        native.native_vertex_coordinates(plan, forged, observations[0].point_id)


@pytest.mark.parametrize(
    "side", [-1, 0, 1], ids=["positive-margin", "zero-margin", "negative-margin"]
)
def test_exact_strict_circle_cell_margin_has_no_epsilon(side):
    c = native.entry_context()
    # rho=1/2, g=1/4; e is exactly at or either side of the remaining margin.
    numerator, denominator = Dyadic(1, 0), Dyadic(1, 1)
    gap = Dyadic(1, -2)
    error = Dyadic(1, -2) if side == 0 else Dyadic((1 << 52) + side, -54)
    assert fraction(numerator) - fraction(denominator) * (
        fraction(gap) + fraction(error)
    ) == -side * F(1, 2**53)
    if side < 0:
        margin = native._vertex_circle_margin(c, numerator, denominator, gap, error)
        assert fraction(margin) == F(1, 2**53)
    else:
        with pytest.raises(native.NativePlanError, match="^native_vertex_circle_cell_margin$"):
            native._vertex_circle_margin(c, numerator, denominator, gap, error)
    assert c.operations > 0


@pytest.mark.parametrize("side", [-1, 0, 1], ids=["inside", "boundary", "outside"])
@pytest.mark.parametrize("code", ["native_vertex_outside_cell", "native_vertex_line_outside_cell"])
def test_exact_disk_boundary_is_strict_for_q_and_both_line_targets(side, code):
    c = native.entry_context()
    squared = Dyadic(1, 0) if side == 0 else Dyadic((1 << 52) + side, -52)
    if side < 0:
        result = native._vertex_disk_margin(c, squared, Dyadic(1, 0), Dyadic(1, 0), code)
        assert fraction(result) == F(1, 2**52)
    else:
        with pytest.raises(native.NativePlanError, match=f"^{code}$"):
            native._vertex_disk_margin(c, squared, Dyadic(1, 0), Dyadic(1, 0), code)
    assert c.operations > 0


def test_circle_discrepancy_is_checked_independently_from_authored_distance():
    value = source(end=(0.0, 5.0 + 2**-31))
    _, _, _, plan, _, c = prepare_support(value)
    records = synthetic_midpoint_observations(plan)
    q = (0.0, value.points[2].v + 0.75e-9, 0.0)
    authored = F(value.points[2].v)
    assert (F(q[1]) - authored) ** 2 < F(1, 10**18)
    assert (F(q[1]) - F(plan.radius)) ** 2 > F(1, 10**18)
    records = (records[0], replace(records[1], world_point=q))
    with pytest.raises(native.NativePlanError, match="^native_vertex_circle_discrepancy$"):
        continue_mapping(plan, records, c)


def test_mapping_does_no_trig_refinement_or_new_intersection_roots(monkeypatch):
    _, _, _, plan, _, c = prepare_support(source(start=(13.0, 29.0), end=(-29.0, 13.0)))
    records = synthetic_midpoint_observations(plan)
    before = native.plan_bytes(plan)

    def forbidden(*args, **kwargs):
        raise AssertionError("mapping must reuse the frozen circle, cells and intersections")

    for name in (
        "_support_circle_roots",
        "_radial_disk",
        "_actual_center_roots",
        "_actual_angle",
        "_common_cell_radius",
        "_periodic_trim",
    ):
        monkeypatch.setattr(native, name, forbidden)
    for name in ("sin", "cos", "atan2", "hypot"):
        monkeypatch.setattr(native.math, name, forbidden)
    representation = continue_mapping(plan, records, c)
    assert native.plan_bytes(plan) == before
    assert_witness_oracle(plan, records, representation)


@pytest.mark.parametrize("kind", ["missing", "foreign", "dictionary", "missing_slots"])
def test_live_continuation_ticket_is_required_and_not_serialized(kind):
    _, _, _, plan, _, c = prepare_support()
    records = synthetic_midpoint_observations(plan)
    ticket = _CONTINUATIONS[id(plan)]
    if kind == "missing":
        bad = None
    elif kind == "foreign":
        _, _, _, other, _, _ = prepare_support()
        bad = _CONTINUATIONS[id(other)]
    elif kind == "dictionary":
        bad = {"plan": plan, "context": c}
    else:
        bad = object.__new__(type(ticket))
    with pytest.raises(native.NativePlanError, match="^native_context_discontinuity$"):
        native._continue_vertex_representation(plan, records, c, continuation=bad)
    with pytest.raises(ValueError):
        native.vertex_representation_bytes(ticket)


def test_two_fresh_calls_have_identical_deterministic_proof_bytes():
    value, plane, _, plan, directions, _ = prepare_support()
    records = synthetic_midpoint_observations(plan)
    left_plan, left = native.prepare_native_vertex_representation(value, plane, directions, records)
    right_plan, right = native.prepare_native_vertex_representation(
        value, plane, directions, records
    )
    assert left is not right and left_plan is not right_plan
    assert native.plan_bytes(left_plan) == native.plan_bytes(right_plan)
    assert native.vertex_representation_bytes(left) == native.vertex_representation_bytes(right)


def test_original_seam_crossing_cw_accepts_canonical_parameter_above_eight():
    value = source(start=(-3.0, -4.0), end=(4.0, -3.0), direction="cw")
    value, plane, _, plan, directions, _ = prepare_support(value)
    assert max(plan.parameters) > 8
    assert all(0 <= parameter < 12 for parameter in plan.parameters)
    records = synthetic_midpoint_observations(plan)
    left_plan, left = native.prepare_native_vertex_representation(value, plane, directions, records)
    right_plan, right = native.prepare_native_vertex_representation(
        value, plane, directions, records
    )
    assert tuple(item.observation.parameter for item in left.endpoints) == plan.parameters
    assert native.plan_bytes(left_plan) == native.plan_bytes(right_plan)
    assert native.vertex_representation_bytes(left) == native.vertex_representation_bytes(right)
    assert_witness_oracle(left_plan, records, left)


def test_observed_world_signed_zero_is_preserved_without_coordinate_regeneration():
    _, _, _, plan, _, c = prepare_support()
    records = synthetic_midpoint_observations(plan)
    q = (5.0, -0.0, -0.0)
    records = (replace(records[0], world_point=q), records[1])
    representation = continue_mapping(plan, records, c)
    actual = native.native_vertex_coordinates(plan, representation, records[0].point_id)
    assert actual is q
    assert tuple(x.hex() for x in actual) == ("0x1.4000000000000p+2", "-0x0.0p+0", "-0x0.0p+0")
    assert b'"-0x0.0p+0"' in native.vertex_representation_bytes(representation)


@pytest.mark.parametrize("mutation", ["missing_slots", "float_counter", "bool_bits", "float_cap"])
def test_context_exact_type_does_not_waive_missing_slots_or_scalar_grammar(mutation):
    _, _, _, plan, _, c = prepare_support()
    records = synthetic_midpoint_observations(plan)
    if mutation == "missing_slots":
        c = object.__new__(PrimitiveContext)
    elif mutation == "float_counter":
        object.__setattr__(c, "_operations", float(c.operations))
    elif mutation == "bool_bits":
        object.__setattr__(c, "_max_bits", True)
    else:
        object.__setattr__(c, "_max_operations", float(c.max_operations))
    with pytest.raises(native.NativePlanError, match="^native_context_discontinuity$"):
        continue_mapping(plan, records, c)


@pytest.mark.parametrize(
    "mutation", ["precision", "authored_vertices", "circle_vectors", "source_hash"]
)
def test_ticket_rejects_changed_plan_before_representative_proof(mutation):
    _, _, _, plan, _, c = prepare_support()
    records = synthetic_midpoint_observations(plan)
    if mutation == "precision":
        changed = replace(plan, accepted_support=replace(plan.accepted_support, precision=128))
    elif mutation == "authored_vertices":
        changed = replace(plan, vertices=plan.vertices[::-1])
    elif mutation == "circle_vectors":
        changed = replace(plan, circle_vectors=plan.circle_vectors[::-1])
    else:
        changed = replace(plan, source=replace(plan.source, geometry_sha256="0" * 64))
    with pytest.raises(native.NativePlanError, match="^native_context_discontinuity$"):
        native._continue_vertex_representation(
            changed, records, c, continuation=_CONTINUATIONS[id(plan)]
        )
