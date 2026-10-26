"""Exact independent references for isolated shared-ID incidence prerequisites.

Fraction is test-only. The production comparison uses checked dyadics; these
references directly compare rational squared distances to rational thresholds.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction as F
from pathlib import Path

import pytest
from historical_runtime_source import historical_runtime_root

import mechanical_cad.arc_profile_incidence as incidence
from mechanical_cad.arc_geometry import ArcGeometryError, arc_geometry
from mechanical_cad.arc_profile_incidence import IncidenceInputError, incidence_preflight
from mechanical_cad.arc_profile_primitives import (
    ArcSupportRoot,
    ArcSupportRoots,
    Dyadic,
    PrimitiveContext,
    PrimitiveError,
    SupportRoots,
    UnresolvedArcSupportRoots,
    UnresolvedSupportRoots,
)
from mechanical_cad.sketch_model import (
    Arc,
    Circle,
    Constraint,
    Line,
    Plane,
    Point,
    Sketch,
    SketchDefinition,
    SketchError,
)

ROOT = Path(__file__).resolve().parents[2]
TRUSTED_GUARD_ROOT = ROOT
DELTA = F(1, 10**9)


def sketch(
    form="chord",
    *,
    start=(5.0, 0.0),
    end=(0.0, 5.0),
    center=(0.0, 0.0),
    direction="ccw",
    reversed_lines=False,
    permuted=False,
):
    lines = (
        (Line("chord", "start", "end"),)
        if form == "chord"
        else (Line("radial_start", "center", "start"), Line("radial_end", "center", "end"))
    )
    if reversed_lines:
        lines = tuple(Line(line.id, line.end, line.start) for line in lines)
    points = (
        Point("center", *center),
        Point("start", *start),
        Point("end", *end),
    )
    if permuted:
        lines, points = lines[::-1], points[::-1]
    return Sketch(
        "incidence_input",
        points,
        lines,
        (),
        schema_version=3,
        arcs=(Arc("arc", "center", "start", "end", direction),),
    )


def rational(value):
    if type(value) is Dyadic:
        return F(value.mantissa) * F(2) ** value.exponent
    return F(value)


def oracle_gap(center, point, radius):
    s = sum((F(p) - F(c)) ** 2 for p, c in zip(point, center, strict=True))
    r = F(radius)
    return s, s == r * r, (r - DELTA) ** 2 <= s <= (r + DELTA) ** 2


@pytest.mark.parametrize("form", ["chord", "sector"])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("end", [(0.0, 5.0), (-5.0, 0.0), (0.0, -5.0), (-3.0, 4.0)])
@pytest.mark.parametrize("reversed_lines", [False, True])
@pytest.mark.parametrize("permuted", [False, True])
def test_exact_endpoints_and_authored_order(form, direction, end, reversed_lines, permuted):
    source = sketch(
        form,
        end=end,
        direction=direction,
        reversed_lines=reversed_lines,
        permuted=permuted,
    )
    before = source.to_json()
    result = incidence_preflight(source, 1)
    assert result.status == result.code == "exact_endpoint_incidence"
    assert result.stage == "ROOTS"
    assert result.source_json == before == source.to_json()
    assert result.arc.direction == direction
    assert result.arc.start == (5.0, 0.0) and result.arc.end == end
    assert result.core_arcs == (
        ("arc", arc_geometry((0.0, 0.0), (5.0, 0.0), end, direction, require_equal_radii=True)),
    )
    assert len(result.boundaries) == result.intended_ledger_count == len(source.lines)
    assert result.ledgers_complete and all(gap.exact_zero for gap in result.gaps)
    for boundary in result.boundaries:
        line = next(item for item in source.lines if item.id == boundary.line_id)
        assert (boundary.stored_start_id, boundary.stored_end_id) == (line.start, line.end)
        assert boundary.support_start_id == ("start" if form == "chord" else "center")
        assert tuple(root.support.branch for root in boundary.roots.roots) == ("MINUS", "PLUS")
        assert all(root.support.multiplicity == 1 for root in boundary.roots.roots)
        assert all(
            root.support is original
            for root, original in zip(
                boundary.roots.roots, boundary.roots.support.roots, strict=True
            )
        )
    assert result.nominal_joins[0].branch == ("MINUS" if form == "chord" else "PLUS")
    assert [join.point_id for join in result.nominal_joins] == ["start", "end"]
    assert 0 == result.operations_start < result.operations_end < result.max_operations


@pytest.mark.parametrize("direction,negative_label", [("ccw", "OUTSIDE"), ("cw", "INTERIOR")])
def test_major_radial_negative_roots_are_retained(direction, negative_label):
    result = incidence_preflight(sketch("sector", direction=direction), 1)
    for boundary, own_endpoint in zip(result.boundaries, ("AT_START", "AT_END"), strict=True):
        minus, plus = boundary.roots.roots
        assert minus.support.position == "BEFORE_START"
        assert minus.arc_position == negative_label
        assert plus.support.position == "AT_END" and plus.arc_position == own_endpoint


@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_semicircle_radial_negative_roots_are_other_endpoints(direction):
    result = incidence_preflight(sketch("sector", end=(-5.0, 0.0), direction=direction), 1)
    assert result.status == "exact_endpoint_incidence"
    assert rational(result.ray_dot) == -25
    assert [item.roots.roots[0].arc_position for item in result.boundaries] == [
        "AT_END",
        "AT_START",
    ]
    assert all(item.roots.roots[0].support.position == "BEFORE_START" for item in result.boundaries)


@pytest.mark.parametrize("form", ["chord", "sector"])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("gap", [0.0, 2**-31])
def test_authored_arc_reversal_preserves_roles_without_inventing_radius_invariance(
    form, direction, gap
):
    original = sketch(form, end=(0.0, 5.0 + gap), direction=direction)
    reversed_arc = replace(
        original.arcs[0], start="end", end="start", direction="cw" if direction == "ccw" else "ccw"
    )
    reversed_source = replace(original, arcs=(reversed_arc,))
    before = incidence_preflight(original, 1)
    after = incidence_preflight(reversed_source, 1)
    assert (
        before.status
        == after.status
        == ("exact_endpoint_incidence" if gap == 0 else "requires_incidence_cells")
    )
    assert after.arc.start_id == "end" and after.arc.end_id == "start"
    assert [join.point_id for join in after.nominal_joins] == ["end", "start"]
    assert after.source_json == reversed_source.to_json()
    assert before.core_arcs[0][1].start_radius == 5.0
    assert after.core_arcs[0][1].start_radius == 5.0 + gap
    if gap == 0:
        assert before.core_arcs[0][1].sweep_radians == -after.core_arcs[0][1].sweep_radians
    else:
        # Canonical radius follows the new authored start; a positive-gap
        # reversal is not the same radius-r mathematical support circle.
        assert before.core_arcs[0][1].start_radius != after.core_arcs[0][1].start_radius


@pytest.mark.parametrize("form", ["chord", "sector"])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("sign", [-1, 1])
def test_binary64_threshold_neighbors(form, direction, sign):
    nominal = 5.0 + sign * 1e-9
    neighbors = [math.nextafter(nominal, -math.inf), nominal, math.nextafter(nominal, math.inf)]
    decisions = set()
    for value in neighbors:
        source = sketch(form, end=(0.0, value), direction=direction)
        result = incidence_preflight(source, 1)
        s, exact, within = oracle_gap((0.0, 0.0), (0.0, value), 5.0)
        assert rational(result.gaps[1].squared_norm) == s
        assert result.gaps[1].exact_zero == exact is False
        assert result.gaps[1].within_bound == within
        assert result.ledgers_complete
        assert len(result.boundaries) == len(source.lines)
        assert result.status == ("requires_incidence_cells" if within else "unsupported")
        if not within:
            assert result.code == "unsupported_endpoint_discrepancy"
        decisions.add(within)
    assert decisions == {False, True}


def test_rational_reference_threshold_equality_is_inclusive_but_not_binary64():
    # A dyadic radius +/- 1/10^9 has a factor-5 denominator. Its square cannot
    # be dyadic S, so exact equality is an algebraic reference fixture only.
    radius = F(5)
    for sign in (-1, 1):
        distance = radius + sign * DELTA
        square = distance**2
        assert square.denominator % 5 == 0
        assert (radius - DELTA) ** 2 <= square <= (radius + DELTA) ** 2
        outside = radius + sign * (DELTA + F(1, 10**30))
        inside = radius + sign * (DELTA - F(1, 10**30))
        assert not (radius - DELTA) ** 2 <= outside**2 <= (radius + DELTA) ** 2
        assert (radius - DELTA) ** 2 <= inside**2 <= (radius + DELTA) ** 2


@pytest.mark.parametrize("form", ["chord", "sector"])
@pytest.mark.parametrize("start,end", [((13.0, 29.0), (-29.0, 13.0)), ((1.0, 1.0), (-1.0, 1.0))])
def test_rounded_hypot_zero_core_residual_is_not_exact_incidence(form, start, end):
    result = incidence_preflight(sketch(form, start=start, end=end), 1)
    core = result.core_arcs[0][1]
    assert core.start_radius == core.end_radius
    assert result.status == "requires_incidence_cells"
    assert all(gap.within_bound and not gap.exact_zero for gap in result.gaps)
    assert all(rational(gap.squared_norm) != rational(gap.radius_squared) for gap in result.gaps)


@pytest.mark.parametrize("form", ["chord", "sector"])
@pytest.mark.parametrize("sign", [-1, 1])
def test_positive_gap_never_changes_input_or_claims_exact_endpoints(form, sign):
    end = (0.0, 5.0 + sign * 2**-31)
    source = sketch(form, end=end)
    before = source.to_json()
    result = incidence_preflight(source, 1)
    assert result.status == "requires_incidence_cells"
    assert result.arc.end == end
    assert result.source_json == before == source.to_json()
    assert result.gaps[0].exact_zero and not result.gaps[1].exact_zero
    own_end = result.boundaries[-1].roots.roots[1]
    assert own_end.support.position == ("AFTER_END" if sign == -1 else "INTERIOR")


def test_all_four_finite_line_arc_membership_combinations_survive():
    combinations = set()
    for form in ("chord", "sector"):
        for direction in ("ccw", "cw"):
            for sign in (-1, 1):
                result = incidence_preflight(
                    sketch(form, end=(0.0, 5.0 + sign * 2**-31), direction=direction), 1
                )
                assert result.status == "requires_incidence_cells"
                for boundary in result.boundaries:
                    for root in boundary.roots.roots:
                        line_member = root.support.position in ("AT_START", "INTERIOR", "AT_END")
                        combinations.add((line_member, root.arc_position != "OUTSIDE"))
    assert combinations == {(False, False), (False, True), (True, False), (True, True)}


@pytest.mark.parametrize("form", ["chord", "sector"])
@pytest.mark.parametrize(
    "alias_mode", ["same_coordinate", "constraint", "constraint_chain", "mixed_chain"]
)
def test_distinct_required_ids_are_explicit_coincidence_failure(form, alias_mode):
    source = sketch(form)
    alias = Point("alias", 5.0 if alias_mode == "same_coordinate" else 4.0, 0.0)
    points = (*source.points, alias)
    constraints = ()
    if alias_mode == "constraint":
        constraints = (Constraint("join", "coincident", ("alias", "start")),)
    elif alias_mode in ("constraint_chain", "mixed_chain"):
        points += (Point("middle", 5.0 if alias_mode == "mixed_chain" else 3.0, 0.0),)
        constraints = (Constraint("join", "coincident", ("alias", "middle")),)
        if alias_mode == "constraint_chain":
            constraints += (Constraint("join2", "coincident", ("middle", "start")),)
    lines = tuple(
        replace(
            line,
            start="alias" if line.start == "start" else line.start,
            end="alias" if line.end == "start" else line.end,
        )
        for line in source.lines
    )
    source = replace(source, points=points, lines=lines, constraints=constraints)
    before = source.to_json()
    result = incidence_preflight(source, 1)
    assert (result.status, result.stage, result.code) == (
        "unsupported",
        "GRAPH",
        "unsupported_profile_coincidence",
    )
    assert result.source_json == before == source.to_json()
    assert not result.ledgers_complete and not result.boundaries


def test_sector_center_alias_is_rejected_even_with_same_coordinates():
    source = sketch("sector")
    source = replace(
        source,
        points=(*source.points, Point("alias", 0.0, 0.0)),
        lines=(Line("radial_start", "alias", "start"), source.lines[1]),
    )
    assert incidence_preflight(source, 1).code == "unsupported_profile_coincidence"


def test_exact_ids_ignore_unrelated_aliases_and_do_not_certify_constraints():
    source = sketch()
    source = replace(
        source,
        points=(*source.points, Point("unused", 5.0, 0.0)),
        constraints=(
            Constraint("unsatisfied", "distance", ("start", "end"), 999.0),
            Constraint("alias", "coincident", ("unused", "start")),
        ),
    )
    result = incidence_preflight(source, 1)
    assert result.status == "exact_endpoint_incidence"
    assert '"unsatisfied"' in result.source_json and '"unused"' in result.source_json
    assert not hasattr(result, "solved") and not hasattr(result, "profile")


def test_near_entity_limit_alias_diagnostic_is_bounded_separately_from_arithmetic():
    source = sketch()
    additions = tuple(Point(f"extra_{index}", 100 + index, 200) for index in range(253))
    constraints = tuple(
        Constraint(
            f"join_{index}",
            "coincident",
            (f"extra_{index}", "start" if index == 0 else f"extra_{index - 1}"),
        )
        for index in range(253)
    )
    source = replace(
        source,
        points=(*source.points, *additions),
        constraints=constraints,
        lines=(Line("chord", "extra_252", "end"),),
    )
    assert len(source.points) == 256
    context = PrimitiveContext(max_operations=1)
    result = incidence_preflight(source, 1, context=context)
    assert result.code == "unsupported_profile_coincidence"
    assert result.operations_start == result.operations_end == 0
    assert result.source_json == source.to_json()
    # This exercises the finite entity bound, not a claimed elapsed-time bound.
    exact = replace(source, lines=(Line("chord", "start", "end"),))
    assert incidence_preflight(exact, 1).status == "exact_endpoint_incidence"


@pytest.mark.parametrize(
    "lines",
    [
        (),
        (Line("wrong", "center", "end"),),
        (Line("a", "center", "start"), Line("b", "center", "start")),
        (Line("a", "center", "start"), Line("b", "center", "end"), Line("c", "start", "end")),
    ],
)
def test_other_connectivity_and_extra_boundaries_are_unsupported(lines):
    assert incidence_preflight(replace(sketch(), lines=lines), 1).code == "unsupported_profile_form"


def test_circle_or_missing_arc_is_not_reinterpreted():
    assert (
        incidence_preflight(replace(sketch(), circles=(Circle("circle", "center", 5),)), 1).code
        == "unsupported_profile_form"
    )
    assert incidence_preflight(replace(sketch(), arcs=()), 1).code == "unsupported_profile_form"


@pytest.mark.parametrize("form", ["chord", "sector"])
@pytest.mark.parametrize(
    "radius", [math.nextafter(1.0, 0.0), 1.0, 1000.0, math.nextafter(1000.0, math.inf)]
)
def test_radius_support_domain_inclusive(form, radius):
    result = incidence_preflight(sketch(form, start=(radius, 0.0), end=(0.0, radius)), 1)
    assert result.status == ("exact_endpoint_incidence" if 1 <= radius <= 1000 else "unsupported")
    if not 1 <= radius <= 1000:
        assert result.code == "unsupported_profile_scale"


@pytest.mark.parametrize(
    "height", [-1, 0, math.nextafter(1.0, 0.0), 1, 1000, math.nextafter(1000.0, math.inf)]
)
def test_height_support_domain_inclusive(height):
    result = incidence_preflight(sketch(), height)
    assert result.height is height
    assert result.status == ("exact_endpoint_incidence" if 1 <= height <= 1000 else "unsupported")
    if not 1 <= height <= 1000:
        assert result.code == "unsupported_profile_scale"


@pytest.mark.parametrize("form", ["chord", "sector"])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("x", [-math.ulp(0.0), 0.0, math.ulp(0.0), 3.0])
def test_exact_dot_sign_neighbors(form, direction, x):
    end = (x, 4.0 if x == 3.0 else 5.0)
    result = incidence_preflight(sketch(form, end=end, direction=direction), 1)
    if x > 0:
        assert result.code == "unsupported_profile_sweep"
    elif x == 0:
        assert result.status == "exact_endpoint_incidence"
    else:
        assert result.status == "requires_incidence_cells"
        assert rational(result.ray_dot) < 0
        assert not result.gaps[1].exact_zero


def test_exact_subtraction_near_coordinate_limit_matches_rational_oracle():
    center = (999_000.0, -999_000.0)
    start, end = (999_013.0, -998_971.0), (998_971.0, -998_987.0)
    result = incidence_preflight(sketch("sector", center=center, start=start, end=end), 1)
    assert result.status == "requires_incidence_cells"
    for gap, point in zip(result.gaps, (start, end), strict=True):
        s, exact, within = oracle_gap(center, point, result.core_arcs[0][1].start_radius)
        assert (
            rational(gap.squared_norm) == s
            and gap.exact_zero == exact
            and gap.within_bound == within
        )


def test_checked_gap_against_independent_rational_samples():
    randomizer = random.Random(0x1AC1D3)
    for _ in range(200):
        radius = randomizer.randint(1, 1000)
        perturbation = randomizer.choice((-1, 1)) * randomizer.randint(0, 64) * 2**-35
        point = (0.0, radius + perturbation)
        context = PrimitiveContext()
        ray = context.vector((0.0, 0.0), point)
        r = context.coordinate(radius)
        r2 = context._mul(r, r)
        gap = incidence._gap(context, "point", context.dot(ray, ray), r, r2)
        s, exact, within = oracle_gap((0.0, 0.0), point, radius)
        assert rational(gap.squared_norm) == s
        assert (gap.exact_zero, gap.within_bound) == (exact, within)


@pytest.mark.parametrize(
    "height", [True, False, "1", None, (), [], float("nan"), float("inf"), 10**1000]
)
def test_malformed_height_rejects(height):
    with pytest.raises(IncidenceInputError, match="invalid_height"):
        incidence_preflight(sketch(), height)


@pytest.mark.parametrize("context", [True, 1, {}, object()])
def test_malformed_context_rejects(context):
    with pytest.raises(IncidenceInputError, match="invalid_context"):
        incidence_preflight(sketch(), 1, context=context)


def test_subclass_context_rejects():
    class Derived(PrimitiveContext):
        pass

    with pytest.raises(IncidenceInputError, match="invalid_context"):
        incidence_preflight(sketch(), 1, context=Derived())


@pytest.mark.parametrize("bad", [None, {}, True, (), SketchDefinition("x", (), (), ())])
def test_exact_sketch_type_required(bad):
    with pytest.raises(SketchError, match="Expected a Sketch"):
        incidence_preflight(bad, 1)


@pytest.mark.parametrize(
    "change",
    [
        {"points": [Point("center", 0, 0)]},
        {"plane": Plane(quaternion=(2.0, 0.0, 0.0, 0.0))},
        {"lines": (Line("line", "missing", "end"),)},
        {"arcs": (Arc("arc", "center", "start", "end", "CCW"),)},
        {"constraints": (Constraint("distance", "distance", ("start", "end"), "5"),)},
    ],
)
def test_unchanged_core_validation_precedes_adapter_errors(change):
    with pytest.raises(SketchError):
        incidence_preflight(replace(sketch(), **change), False, context=False)


def test_equal_radius_core_gate_precedes_support_and_preserves_exception():
    with pytest.raises(ArcGeometryError) as failure:
        incidence_preflight(sketch(end=(0.0, 6.0)), 0)
    assert failure.value.code == "unequal_arc_radii"


def test_all_arcs_core_checked_in_stable_authored_id_order(monkeypatch):
    source = sketch()
    source = replace(
        source, arcs=(replace(source.arcs[0], id="z"), replace(source.arcs[0], id="a"))
    )
    observed = []
    original = incidence.arc_geometry

    def record(*args, **kwargs):
        observed.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(incidence, "arc_geometry", record)
    result = incidence_preflight(source, 1)
    assert observed == [{"require_equal_radii": True}, {"require_equal_radii": True}]
    assert [identity for identity, _ in result.core_arcs] == ["a", "z"]
    assert result.code == "unsupported_profile_form"


def test_unequal_second_arc_is_not_hidden_by_unsupported_multiarc_form():
    source = sketch()
    source = replace(
        source,
        points=(*source.points, Point("bad", 0.0, 6.0)),
        arcs=(*source.arcs, Arc("second", "center", "start", "bad", "ccw")),
    )
    with pytest.raises(ArcGeometryError) as failure:
        incidence_preflight(source, 1)
    assert failure.value.code == "unequal_arc_radii"


def test_one_nonresetting_context_and_aggregate_operation_exhaustion():
    cost = incidence_preflight(sketch("sector"), 1).operations_end
    context = PrimitiveContext(max_operations=2 * cost - 1)
    first = incidence_preflight(sketch("sector"), 1, context=context)
    assert first.status == "exact_endpoint_incidence"
    second = incidence_preflight(sketch("sector"), 1, context=context)
    assert second.operations_start == first.operations_end
    assert second.status == "numerical_ambiguity" and second.code == "operation_limit"
    assert context.operations == second.operations_end == context.max_operations


@pytest.mark.parametrize("max_bits", [1, 16, 64, 128, 512])
def test_shared_bit_caps_reject_boundedly(max_bits):
    result = incidence_preflight(
        sketch("sector", end=(-math.ulp(0.0), 5.0)),
        1,
        context=PrimitiveContext(max_bits=max_bits),
    )
    assert result.status == "numerical_ambiguity" and result.code == "integer_limit"
    assert result.max_bits == max_bits and result.operations_end <= result.max_operations


def test_resource_failure_retains_only_completed_prior_support_calls(monkeypatch):
    original = PrimitiveContext.line_arc_roots
    returned = []

    def stop_second(context, *args, **kwargs):
        if returned:
            raise PrimitiveError("operation_limit")
        result = original(context, *args, **kwargs)
        returned.append(result)
        return result

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", stop_second)
    result = incidence_preflight(sketch("sector"), 1)
    assert result.status == "numerical_ambiguity" and result.code == "operation_limit"
    assert not result.ledgers_complete and result.intended_ledger_count == 2
    assert len(result.boundaries) == 1 and result.boundaries[0].roots is returned[0]


def test_resource_failure_after_all_ledgers_preserves_completeness(monkeypatch):
    def exhaust(*args):
        raise PrimitiveError("integer_limit")

    monkeypatch.setattr(incidence, "_gap", exhaust)
    result = incidence_preflight(sketch("sector"), 1)
    assert result.stage == "DISCREPANCY" and result.code == "integer_limit"
    assert result.ledgers_complete and len(result.boundaries) == 2 and not result.gaps


def test_unresolved_ledger_stays_intact_and_cannot_pass(monkeypatch):
    original = PrimitiveContext.line_arc_roots
    returned = []

    def unresolved(context, *args, **kwargs):
        ledger = original(context, *args, **kwargs)
        base = ledger.support
        support = UnresolvedSupportRoots(base.a, base.b, base.c, base.discriminant, base.roots)
        result = UnresolvedArcSupportRoots(support, ledger.roots)
        returned.append(result)
        return result

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", unresolved)
    result = incidence_preflight(sketch("sector"), 1)
    assert result.status == "numerical_ambiguity" and result.code == "unresolved_isolation"
    assert result.ledgers_complete and len(result.boundaries) == 2
    assert all(
        boundary.roots is old for boundary, old in zip(result.boundaries, returned, strict=True)
    )


@pytest.mark.parametrize("kind", ["missing", "double", "incomplete", "duplicate"])
def test_absent_tangent_incomplete_or_duplicate_ledger_never_passes(monkeypatch, kind):
    # Defensive injected control, not a ledger reachable through valid geometry.
    original = PrimitiveContext.line_arc_roots

    def invalid(context, *args, **kwargs):
        ledger = original(context, *args, **kwargs)
        base = ledger.support
        roots = base.roots
        members = ledger.roots
        if kind == "missing":
            roots, members = (), ()
        elif kind == "incomplete":
            members = members[:1]
        elif kind == "duplicate":
            roots, members = (roots[0], roots[0]), (members[0], members[0])
        else:
            root = replace(roots[0], branch="DOUBLE", multiplicity=2)
            roots, members = (root,), (ArcSupportRoot(root, members[0].arc_position),)
        return ArcSupportRoots(
            SupportRoots(base.a, base.b, base.c, base.discriminant, roots), members
        )

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", invalid)
    result = incidence_preflight(sketch("sector"), 1)
    assert result.status == "unsupported" and result.code == "unsupported_profile_contact"
    assert len(result.boundaries) == 2


def test_prescribed_exact_root_membership_cannot_be_substituted(monkeypatch):
    original = PrimitiveContext.line_arc_roots

    def swapped(context, *args, **kwargs):
        ledger = original(context, *args, **kwargs)
        return replace(
            ledger, roots=tuple(replace(root, arc_position="OUTSIDE") for root in ledger.roots)
        )

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", swapped)
    result = incidence_preflight(sketch(), 1)
    assert result.code == "unsupported_endpoint_incidence"


@pytest.mark.parametrize(
    "discriminant,expected",
    [
        (-1, "unsupported_profile_nontransverse"),
        (0, "unsupported_profile_nontransverse"),
        (F(16 * 50 * 25, 9), "exact_endpoint_incidence"),
    ],
)
def test_chord_transversality_gate_is_positive_and_inclusive(monkeypatch, discriminant, expected):
    # Defensive synthetic discriminants do not describe the input chord.
    # The equality case is tested through a separate rational comparison below:
    # its denominator nine is not representable by the dyadic ledger record.
    if isinstance(discriminant, F):
        a, r = F(50), F(5)
        assert 9 * discriminant == 16 * a * r * r
        assert 9 * (discriminant - F(1, 10**20)) < 16 * a * r * r
        assert incidence_preflight(sketch(), 1).status == expected
        return
    original = PrimitiveContext.line_arc_roots

    def changed(context, *args, **kwargs):
        ledger = original(context, *args, **kwargs)
        return replace(
            ledger, support=replace(ledger.support, discriminant=context._make(discriminant, 0))
        )

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", changed)
    assert incidence_preflight(sketch(), 1).code == expected


@pytest.mark.parametrize("d", [math.nextafter(400.0, 0.0), 400.0, math.nextafter(400.0, math.inf)])
def test_defensive_chord_transversality_exact_equality_and_neighbors(monkeypatch, d):
    # Injected gate-only control: A=9, r=5 makes D=400 exactly the dyadic
    # transversality boundary. These substituted coefficients are not claimed
    # to describe the original geometric chord or establish a valid profile.
    original = PrimitiveContext.line_arc_roots

    def changed(context, *args, **kwargs):
        ledger = original(context, *args, **kwargs)
        return replace(
            ledger,
            support=replace(
                ledger.support, a=context.coordinate(9), discriminant=context.coordinate(d)
            ),
        )

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", changed)
    result = incidence_preflight(sketch(), 1)
    assert result.code == (
        "unsupported_profile_nontransverse"
        if F(9) * F(d) < F(16 * 9 * 25)
        else "exact_endpoint_incidence"
    )


def test_unexpected_primitive_input_failure_is_not_hidden(monkeypatch):
    def invalid(*args, **kwargs):
        raise PrimitiveError("invalid_point")

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", invalid)
    with pytest.raises(PrimitiveError, match="invalid_point"):
        incidence_preflight(sketch(), 1)


def test_all_output_records_are_frozen_and_detached():
    result = incidence_preflight(sketch(), 1)
    for value in (
        result,
        result.arc,
        result.gaps[0],
        result.boundaries[0],
        result.nominal_joins[0],
    ):
        with pytest.raises((FrozenInstanceError, AttributeError)):
            setattr(value, fields(value)[0].name, "changed")
        assert not hasattr(value, "__dict__")
    assert not any(
        hasattr(result, name) for name in ("closed", "valid", "capability", "geometry", "accepted")
    )


def test_import_and_execution_are_native_free_without_site_packages():
    script = """
import sys
class BlockNative:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'OCP', 'slvs', 'bpy'} or fullname in {
            'mechanical_cad.engine', 'mechanical_cad.sketch_solver',
            'mechanical_cad.kernel_ocp', 'mechanical_cad.sketch_service',
            'mechanical_cad.profile_region', 'mechanical_cad.sidecar'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, BlockNative())
from mechanical_cad.arc_profile_incidence import incidence_preflight
from mechanical_cad.sketch_model import Sketch, Point, Line, Arc
s = Sketch('s', (Point('c',0,0),Point('a',5,0),Point('b',0,5)),
           (Line('l','b','a'),), (), schema_version=3,
           arcs=(Arc('arc','c','a','b','cw'),))
assert incidence_preflight(s,1).status == 'exact_endpoint_incidence'
print('INCIDENCE_NATIVE_FREE_OK')
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.stdout.strip() == "INCIDENCE_NATIVE_FREE_OK" and not result.stderr


def test_104_runtime_files_and_primitives_unchanged_with_reviewed_additive_kernel():
    """Retain historical revision proofs and the live primitive resource ceiling."""
    historical = historical_runtime_root()

    def reviewed_authoring_originals(root):
        """Load only the pinned inverse guard, without importing a test module."""
        path = TRUSTED_GUARD_ROOT / "tests/unit/test_arc_profile_native_end_cap.py"
        constants = {
            "VISUAL_JOINT_FIXTURE",
            "VISUAL_JOINT_SHA256",
            "RELEASE_071_FIXTURE",
            "RELEASE_071_SHA256",
            "ASSEMBLY_STEP_FIXTURE",
            "ASSEMBLY_STEP_SHA256",
            "RELEASE_070_FIXTURE",
            "RELEASE_070_SHA256",
            "ASSEMBLY_SOURCE_FIXTURE",
            "ASSEMBLY_SOURCE_SHA256",
            "ASSEMBLY_HARNESS_FIXTURE",
            "ASSEMBLY_HARNESS_SHA256",
            "GATE_C_OWNER_SOURCE_FIXTURE",
            "GATE_C_OWNER_SOURCE_SHA256",
            "GATE_C_OWNER_HARNESS_FIXTURE",
            "GATE_C_OWNER_HARNESS_SHA256",
            "INVENTORY_GUARD_HARNESS_FIXTURE",
            "INVENTORY_GUARD_HARNESS_SHA256",
            "REDUNDANT_SOLVE_SOURCE_FIXTURE",
            "REDUNDANT_SOLVE_SOURCE_SHA256",
            "REDUNDANT_SOLVE_HARNESS_FIXTURE",
            "REDUNDANT_SOLVE_HARNESS_SHA256",
            "INTEGRATION_SOURCE_FIXTURE",
            "INTEGRATION_SOURCE_SHA256",
            "INTEGRATION_HARNESS_FIXTURE",
            "STANDALONE_INTEGRATION_HARNESS_SHA256",
            "GEOMETRY_REVISION_FIXTURE",
            "GEOMETRY_REVISION_SHA256",
            "AUTHORING_REVISION_FIXTURE",
            "AUTHORING_REVISION_SHA256",
            "STANDALONE_REVISION_FIXTURE",
            "STANDALONE_REVISION_SHA256",
            "STANDALONE_LIVE_FIXTURE",
            "STANDALONE_LIVE_SHA256",
            "STANDALONE_HARNESS_FIXTURE",
            "STANDALONE_HARNESS_SHA256",
            "WINDOWS_TRANSPORT_REVISION_FIXTURE",
            "WINDOWS_TRANSPORT_REVISION_SHA256",
            "WINDOWS_TRANSPORT_HARNESS_FIXTURE",
            "WINDOWS_TRANSPORT_HARNESS_SHA256",
            "WINDOWS_CACHE_REVISION_FIXTURE",
            "WINDOWS_CACHE_REVISION_SHA256",
            "WINDOWS_CACHE_HARNESS_FIXTURE",
            "WINDOWS_CACHE_HARNESS_SHA256",
            "WINDOWS_RUNTIME_CACHE_REVISION_FIXTURE",
            "WINDOWS_RUNTIME_CACHE_REVISION_SHA256",
            "WINDOWS_RUNTIME_CACHE_HARNESS_FIXTURE",
            "WINDOWS_RUNTIME_CACHE_HARNESS_SHA256",
        }
        finite_sets = {
            "VISUAL_JOINT_ADDED",
            "ASSEMBLY_STEP_ADDED",
            "ASSEMBLY_SOURCE_ADDED",
            "GATE_C_OWNER_SOURCE_ADDED",
            "INTEGRATION_SOURCE_ADDED",
            "STANDALONE_LIVE_CHANGED",
            "STANDALONE_LIVE_ADDED",
            "WINDOWS_TRANSPORT_REVISION_CHANGED",
            "WINDOWS_TRANSPORT_REVISION_ADDED",
            "WINDOWS_CACHE_REVISION_CHANGED",
            "WINDOWS_CACHE_REVISION_ADDED",
            "WINDOWS_RUNTIME_CACHE_REVISION_CHANGED",
            "WINDOWS_RUNTIME_CACHE_REVISION_ADDED",
        }
        mappings = {
            "VISUAL_JOINT_ORIGINALS",
            "RELEASE_071_ORIGINALS",
            "ASSEMBLY_STEP_ORIGINALS",
            "RELEASE_070_ORIGINALS",
            "ASSEMBLY_SOURCE_ORIGINALS",
            "ASSEMBLY_HARNESS_ORIGINALS",
            "GATE_C_OWNER_SOURCE_ORIGINALS",
            "GATE_C_OWNER_HARNESS_ORIGINALS",
            "INVENTORY_GUARD_HARNESS_ORIGINALS",
            "REDUNDANT_SOLVE_SOURCE_ORIGINALS",
            "REDUNDANT_SOLVE_HARNESS_ORIGINALS",
            "INTEGRATION_SOURCE_ORIGINALS",
            "INTEGRATION_HARNESS_ORIGINALS",
            "STANDALONE_HARNESS_ORIGINALS",
            "WINDOWS_TRANSPORT_HARNESS_ORIGINALS",
            "WINDOWS_CACHE_HARNESS_ORIGINALS",
            "WINDOWS_CACHE_REVISION_ORIGINALS",
            "WINDOWS_RUNTIME_CACHE_HARNESS_ORIGINALS",
            "WINDOWS_RUNTIME_CACHE_REVISION_ORIGINALS",
        }
        functions = {
            "_visual_joint_revision",
            "_visual_joint_bytes",
            "visual_joint_originals",
            "_release_071_bytes",
            "_assembly_step_revision",
            "_assembly_step_bytes",
            "assembly_step_originals",
            "_release_070_bytes",
            "assembly_source_originals",
            "assembly_harness_originals",
            "gate_c_owner_source_originals",
            "gate_c_owner_harness_originals",
            "inventory_guard_harness_originals",
            "redundant_solve_source_originals",
            "redundant_solve_harness_originals",
            "_integration_restore_entry",
            "standalone_integration_source_originals",
            "standalone_integration_harness_originals",
            "_geometry_recovered_harness_bytes",
            "geometry_revision_originals",
            "standalone_harness_originals",
            "windows_transport_originals",
            "windows_transport_harness_originals",
            "windows_cache_harness_originals",
            "windows_cache_originals",
            "windows_runtime_cache_harness_originals",
            "windows_runtime_cache_originals",
            "standalone_live_originals",
            "authoring_revision_originals",
        }
        selected = {}
        for node in ast.parse(path.read_bytes()).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id in constants | finite_sets | mappings:
                    if target.id in constants:
                        assert isinstance(node.value, ast.Constant)
                        assert type(node.value.value) is str
                    elif target.id in finite_sets:
                        assert isinstance(node.value, ast.Call)
                        assert isinstance(node.value.func, ast.Name)
                        assert node.value.func.id == "frozenset"
                        assert len(node.value.args) == 1 and not node.value.keywords
                        value = ast.literal_eval(node.value.args[0])
                        assert type(value) is set and all(type(item) is str for item in value)
                    else:
                        assert type(ast.literal_eval(node.value)) is dict
                    assert target.id not in selected
                    selected[target.id] = node
            elif isinstance(node, ast.FunctionDef) and node.name in functions:
                assert node.name not in selected
                selected[node.name] = node
        assert set(selected) == constants | finite_sets | mappings | functions
        namespace = {"hashlib": hashlib, "json": json}
        exec(
            compile(ast.Module(body=list(selected.values()), type_ignores=[]), str(path), "exec"),
            namespace,
        )
        return namespace["authoring_revision_originals"](root)

    def assert_primitive_resource_boundary(original: bytes, current: bytes) -> None:
        """Permit only the sealed hard-ceiling/default split from qualified bytes."""
        assert hashlib.sha256(original).hexdigest() == (
            "ebd60e4dd35c98459dd6d688e81322f88adcb1766c0864e16d10b9defea738bd"
        ), "changed historical primitive bytes"
        old_limit = b"MAX_OPERATIONS = 100_000\n"
        new_limits = b"MAX_OPERATIONS = 200_000\nDEFAULT_OPERATIONS = 100_000\n"
        old_signature = (
            b"    def __init__(self, *, max_bits: int = MAX_INTEGER_BITS, "
            b"max_operations: int = MAX_OPERATIONS):\n"
        )
        new_signature = (
            b"    def __init__(\n"
            b"        self, *, max_bits: int = MAX_INTEGER_BITS, "
            b"max_operations: int = DEFAULT_OPERATIONS\n"
            b"    ):\n"
        )
        assert original.count(old_limit) == original.count(old_signature) == 1
        expected = original.replace(old_limit, new_limits).replace(old_signature, new_signature)
        assert current == expected, "primitive bytes changed beyond the sealed resource revision"

    def assert_kernel_additive_boundary(original: bytes, current: bytes) -> None:
        """Keep old behavior byte-exact except the one reviewed topology constant.

        This helper is deliberately test-local and AST/filesystem-only. Mutation
        controls extract its AST without importing this test module or the kernel.
        Added definitions are separately reviewed, never permission to replace or
        shadow an original helper, class, method, import binding, or class body.
        """
        original_tree = ast.parse(original)
        current_tree = ast.parse(current)
        assert ast.dump(original_tree.body[0]) == ast.dump(current_tree.body[0]), (
            "changed original module docstring position"
        )
        definition_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        import_types = (ast.Import, ast.ImportFrom)

        def definitions(body):
            result = {}
            for node in body:
                if isinstance(node, definition_types):
                    assert node.name not in result, ("duplicate definition", node.name)
                    result[node.name] = node
            return result

        def span(data, node):
            start = min(
                [node.lineno] + [item.lineno for item in getattr(node, "decorator_list", ())]
            )
            return b"".join(data.splitlines(keepends=True)[start - 1 : node.end_lineno])

        def import_bindings(body):
            result = {}
            for node in body:
                if not isinstance(node, import_types):
                    continue
                for alias in node.names:
                    assert alias.name != "*", "wildcard imports can replace old bindings"
                    if isinstance(node, ast.Import):
                        binding = alias.asname or alias.name.split(".")[0]
                        target = ("import", alias.name, alias.asname)
                    else:
                        binding = alias.asname or alias.name
                        target = ("from", node.level, node.module, alias.name, alias.asname)
                    assert binding not in result or result[binding] == target, (
                        "replaced import binding",
                        binding,
                    )
                    result[binding] = target
            return result

        def skeleton(body, original_names):
            return [
                ("definition", node.name)
                if isinstance(node, definition_types)
                else ("statement", ast.dump(node, include_attributes=False))
                for node in body
                if not isinstance(node, import_types)
                and (not isinstance(node, definition_types) or node.name in original_names)
            ]

        old_definitions = definitions(original_tree.body)
        new_definitions = definitions(current_tree.body)
        assert old_definitions.keys() <= new_definitions.keys(), "deleted original definition"
        old_imports = import_bindings(original_tree.body)
        new_imports = import_bindings(current_tree.body)
        assert all(new_imports.get(name) == target for name, target in old_imports.items()), (
            "deleted or replaced original import"
        )
        assert not new_definitions.keys() & new_imports.keys(), "definition shadows an import"
        assert skeleton(original_tree.body, old_definitions) == skeleton(
            current_tree.body, old_definitions
        ), "changed original module statements or definition order"

        for name, old_definition in old_definitions.items():
            new_definition = new_definitions[name]
            assert type(new_definition) is type(old_definition), ("replaced definition", name)
            if name != "OCPKernel":
                assert span(original, old_definition) == span(current, new_definition), name
                continue
            old_header = ast.ClassDef(
                **{
                    field: getattr(old_definition, field)
                    for field in old_definition._fields
                    if field != "body"
                },
                body=[],
            )
            new_header = ast.ClassDef(
                **{
                    field: getattr(new_definition, field)
                    for field in new_definition._fields
                    if field != "body"
                },
                body=[],
            )
            assert ast.dump(old_header) == ast.dump(new_header), "changed OCPKernel metadata"
            assert ast.dump(old_definition.body[0]) == ast.dump(new_definition.body[0]), (
                "changed original OCPKernel docstring position"
            )
            assert b"".join(
                original.splitlines(keepends=True)[
                    old_definition.lineno - 1 : old_definition.body[0].lineno - 1
                ]
            ) == b"".join(
                current.splitlines(keepends=True)[
                    new_definition.lineno - 1 : new_definition.body[0].lineno - 1
                ]
            ), "changed original OCPKernel header bytes"
            old_members = definitions(old_definition.body)
            new_members = definitions(new_definition.body)
            assert old_members.keys() <= new_members.keys(), "deleted original kernel method"
            # Class-level imports are not an additive extension: they could
            # overwrite existing methods or change original class statements.
            assert not any(isinstance(node, import_types) for node in new_definition.body)
            assert skeleton(old_definition.body, old_members) == skeleton(
                new_definition.body, old_members
            ), "changed original OCPKernel body statements or method order"
            old_statements = [
                node for node in old_definition.body if not isinstance(node, definition_types)
            ]
            new_statements = [
                node for node in new_definition.body if not isinstance(node, definition_types)
            ]
            assert len(old_statements) == len(new_statements)
            assert all(
                span(original, old) == span(current, new)
                for old, new in zip(old_statements, new_statements, strict=True)
            ), "changed original OCPKernel body statement bytes"
            for method, old_method in old_members.items():
                new_method = new_members[method]
                assert type(new_method) is type(old_method), ("replaced method", method)
                if span(original, old_method) == span(current, new_method):
                    continue
                assert method == "topology", ("modified original kernel method", method)
                # Exactly one reviewed Ruff-format expansion of the original
                # kind-set line is allowed. AST equivalence alone would also
                # waive unrelated whitespace and comments elsewhere in topology.
                old_kind_line = (
                    b"        if operation and operation.kind in "
                    b'{"rectangle", "circle", "polygon", "circle_profile"}:\n'
                )
                new_kind_lines = (
                    b"        if operation and operation.kind in {\n"
                    b'            "rectangle",\n'
                    b'            "circle",\n'
                    b'            "polygon",\n'
                    b'            "circle_profile",\n'
                    b'            "curve_profile",\n'
                    b"        }:\n"
                )
                old_span = span(original, old_method)
                assert old_span.count(old_kind_line) == 1
                assert span(current, new_method) == old_span.replace(
                    old_kind_line, new_kind_lines
                ), "topology bytes changed beyond the exact reviewed set-line replacement"
                profile_kinds = [
                    node
                    for node in ast.walk(old_method)
                    if isinstance(node, ast.Set)
                    and all(isinstance(item, ast.Constant) for item in node.elts)
                    and [item.value for item in node.elts]
                    == ["rectangle", "circle", "polygon", "circle_profile"]
                ]
                assert len(profile_kinds) == 1, "historical topology set is not unique"
                additions = [
                    (node, item)
                    for node in ast.walk(new_method)
                    if isinstance(node, ast.Set)
                    for item in node.elts
                    if isinstance(item, ast.Constant) and item.value == "curve_profile"
                ]
                assert len(additions) == 1, "expected exactly one curve_profile addition"
                target_set, addition = additions[0]
                target_set.elts.remove(addition)
                assert ast.dump(target_set) == ast.dump(profile_kinds[0]), (
                    "changed the original profile-kind set"
                )
                assert ast.dump(old_method) == ast.dump(new_method), (
                    "topology changed beyond the reviewed curve_profile constant"
                )

    baseline = json.loads(
        (historical / "docs/architecture/arc_profile_service/BASELINE.json").read_text()
    )
    hashes = baseline["source_sha256"]
    assert len(hashes) == 105
    kernel_path = "src/mechanical_cad/kernel_ocp.py"
    kernel_hash = "bd06d4b5372758bfd02cf89eebcb1a1385e8222fb36aba06b55764fd449bcbfc"
    assert hashes[kernel_path] == kernel_hash
    assert len({path for path in hashes if path != kernel_path}) == 104
    # First undo the complete SHA-pinned authoring revision. The original 104
    # byte expectations and the three reviewed service-dispatch expectations
    # remain unchanged; no path is waived or assigned a new baseline hash.
    _, authoring_originals = reviewed_authoring_originals(historical)
    dispatch_raw = (historical / "tests/fixtures/result_v3/dispatch_extension_30383a1.json").read_bytes()
    assert (
        hashlib.sha256(dispatch_raw).hexdigest()
        == "4eed9a50153d2c4b3d0ea8fda5e48cd378e050287ca374241b56ee0481b497c8"
    )
    dispatch = json.loads(dispatch_raw)["files"]
    assert set(dispatch) == {
        "src/mechanical_cad/engine.py",
        "src/mechanical_cad/sidecar.py",
        "src/mechanical_cad/backend_contract.py",
    }
    assert all(hashes[path] == entry["original_sha256"] for path, entry in dispatch.items())
    assert all(
        hashlib.sha256(authoring_originals.get(path, (historical / path).read_bytes())).hexdigest()
        == (dispatch[path]["reviewed_sha256"] if path in dispatch else expected)
        for path, expected in hashes.items()
        if path != kernel_path
    )
    original_kernel = (historical / "tests/fixtures/arc_sector/kernel_ocp-a05626e.py.txt").read_bytes()
    assert hashlib.sha256(original_kernel).hexdigest() == kernel_hash
    assert_kernel_additive_boundary(
        original_kernel, authoring_originals.get(kernel_path, (historical / kernel_path).read_bytes())
    )
    assert_primitive_resource_boundary(
        (historical / "tests/fixtures/arc_sector/arc_profile_primitives-a05626e.py.txt").read_bytes(),
        (ROOT / "src/mechanical_cad/arc_profile_primitives.py").read_bytes(),
    )


def test_leaf_dependency_and_no_duplicate_arithmetic_boundary():
    tree = ast.parse((ROOT / "src/mechanical_cad/arc_profile_incidence.py").read_text())
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert {node.module for node in imports if isinstance(node, ast.ImportFrom)} == {
        "__future__",
        "dataclasses",
        "arc_geometry",
        "arc_profile_primitives",
        "sketch_model",
    }
    assert [
        alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names
    ] == ["math"]
    assert not any(
        isinstance(node, ast.BinOp)
        and isinstance(node.op, (ast.Mult, ast.Div, ast.Pow, ast.LShift, ast.RShift))
        for node in ast.walk(tree)
    )
