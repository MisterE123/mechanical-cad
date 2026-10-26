"""Independent source-sector references, exact disk identities and hostile records.

Fraction and high precision Decimal are test-only. The circle checks expand both
support equations as polynomials in a formal radical. Angular membership uses a
single global cyclic ray order; area uses a positive Euler arctangent series and
Gauss-Legendre pi, rather than the implementation's alternating/Machin formulas.
"""

from __future__ import annotations

import ast
import math
import os
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from fractions import Fraction as F
from pathlib import Path

import pytest

import mechanical_cad.arc_profile_sector as sector
import mechanical_cad.arc_profile_sector_policy as policy
from mechanical_cad.arc_profile_primitives import Dyadic, PrimitiveContext
from mechanical_cad.arc_profile_sector import (
    MAX_CERTIFICATE_BYTES,
    SectorInputError,
    certificate_bytes,
    check_sector_certificate,
    classify_sector,
    extrusion_preflight,
)
from mechanical_cad.arc_profile_sector_source import geometry_preflight
from mechanical_cad.sketch_model import (
    Arc,
    Circle,
    Constraint,
    Line,
    Plane,
    Point,
    Sketch,
    SketchError,
)

ROOT = Path(__file__).resolve().parents[2]
DELTA, B, L, D = F(1, 10**9), F(350, 10**9), F(400, 10**9), F(200, 10**9)


def sketch(
    start=(5.0, 0.0),
    end=(0.0, 5.0),
    *,
    center=(0.0, 0.0),
    direction="ccw",
    reversed_lines=False,
    permuted=False,
    plane=None,
):
    lines = (Line("radial_start", "center", "start"), Line("radial_end", "center", "end"))
    if reversed_lines:
        lines = tuple(Line(line.id, line.end, line.start) for line in lines)
    points = (Point("center", *center), Point("start", *start), Point("end", *end))
    if permuted:
        points, lines = points[::-1], lines[::-1]
    return Sketch(
        "sector_input",
        points,
        lines,
        (),
        Plane() if plane is None else plane,
        schema_version=3,
        arcs=(Arc("arc", "center", "start", "end", direction),),
    )


def fraction(value):
    if type(value) is Dyadic:
        return F(value.mantissa) * F(2) ** value.exponent
    if type(value) is sector.ExactRatio:
        return fraction(value.numerator) / fraction(value.denominator)
    return F(value)


def change(cert, **changes):
    direct = {"version", "source_json", "source_sha256", "incidence", "geometry", "resources"}
    assert set(changes) <= direct or not set(changes).intersection(direct)
    return (
        replace(cert, **changes)
        if set(changes) <= direct
        else replace(cert, geometry=replace(cert.geometry, **changes))
    )


def decimal(value):
    value = fraction(value)
    return Decimal(value.numerator) / Decimal(value.denominator)


def enclosed(interval, value):
    assert decimal(interval.lower) <= value <= decimal(interval.upper)


def dot(left, right):
    return left[0] * right[0] + left[1] * right[1]


def cross(left, right):
    return left[0] * right[1] - left[1] * right[0]


def sub(left, right):
    return tuple(a - b for a, b in zip(left, right, strict=True))


def sign(value):
    return (value > 0) - (value < 0)


def radical_sign(p, q, h):
    if not q or not h:
        return sign(p)
    if q < 0:
        return -radical_sign(-p, -q, h)
    if p >= 0:
        return 1
    return sign(h - (p / q) ** 2)


def ray_half(x, y):
    return 0 if y > 0 or (y == 0 and x > 0) else 1


def ray_order(a, b):
    ah, bh = ray_half(*map(sign, a)), ray_half(*map(sign, b))
    return sign(ah - bh) if ah != bh else -sign(cross(a, b))


def ray_root_order(ray, p, q, h):
    rh = ray_half(*map(sign, ray))
    ah = ray_half(*(radical_sign(x, y, h) for x, y in zip(p, q, strict=True)))
    return sign(rh - ah) if rh != ah else -radical_sign(cross(ray, p), cross(ray, q), h)


def cyclic_membership(start, end, p, q, h, direction):
    # One total circular order, independent of minor/major half-plane formulas.
    if direction == "cw":
        start, end = end, start
    before_end = ray_root_order(end, p, q, h)
    after_start = ray_root_order(start, p, q, h)
    if after_start == 0:
        return "AT_START" if direction == "ccw" else "AT_END"
    if before_end == 0:
        return "AT_END" if direction == "ccw" else "AT_START"
    selected = (
        after_start < 0 and before_end > 0
        if ray_order(start, end) < 0
        else after_start < 0 or before_end > 0
    )
    return "INTERIOR" if selected else "OUTSIDE"


def reference_pi():
    a, b, t, p = Decimal(1), Decimal(1) / Decimal(2).sqrt(), Decimal(1) / 4, Decimal(1)
    for _ in range(12):
        following = (a + b) / 2
        b = (a * b).sqrt()
        t -= p * (a - following) ** 2
        a, p = following, p * 2
    return (a + b) ** 2 / (4 * t)


def reference_atan(x):
    # Euler's all-positive series: x/(1+x²) sum (2n)!!/(2n+1)!! z^n,
    # z=x²/(1+x²)<=1/2. 360 terms make the tail <2^-359 for x<=1.
    z, term, total = x * x / (1 + x * x), Decimal(1), Decimal(1)
    for n in range(1, 360):
        term *= Decimal(2 * n) / Decimal(2 * n + 1) * z
        total += term
    return x / (1 + x * x) * total


def reference_angle(v0, v1, direction):
    pi = reference_pi()
    det, scalar = cross(v0, v1), dot(v0, v1)
    if not det:
        angle = pi
    elif not scalar:
        angle = pi / 2
    else:
        ratio = abs(decimal(det) / decimal(scalar))
        acute = reference_atan(ratio) if ratio <= 1 else pi / 2 - reference_atan(1 / ratio)
        angle = pi - acute if scalar < 0 else acute
    if det < 0:
        angle = -angle
    if direction == "ccw" and angle <= 0:
        angle += 2 * pi
    elif direction == "cw" and angle >= 0:
        angle -= 2 * pi
    return angle


POSITIVES = [
    ((5.0, 0.0), (0.0, 5.0)),
    ((5.0, 0.0), (-5.0, 0.0)),
    ((5.1, 0.0), (0.0, 5.1)),
    ((3, 4), (-4, 3)),
    ((13, 29), (-29, 13)),
    ((1, 1), (-1, 1)),
    ((5, 0), (-3, 4)),
    ((10, 0), (0, 10 + 2**-31)),
    ((10, 0), (0, 10 - 2**-31)),
    ((5, 0), (-5, 2**-40)),
    ((-4, 3), (-3, -4)),
    ((-3, -4), (3, 4)),
]


@pytest.mark.parametrize("start,end", POSITIVES)
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("reversed_lines,permuted", [(False, False), (True, True)])
def test_complete_source_matrix_and_independent_area(
    start, end, direction, reversed_lines, permuted
):
    source = sketch(
        start, end, direction=direction, reversed_lines=reversed_lines, permuted=permuted
    )
    before = source.to_json()
    result = classify_sector(source)
    assert result.status == result.code == "certified_sector"
    assert result.stage == "COMPLETE"
    cert = result.certificate
    assert cert.incidence.source_json == before == source.to_json()
    assert cert.incidence.height == 1  # Prerequisite adapter only.
    assert cert.incidence.ledgers_complete
    assert len(cert.assignments) == 4 and len(cert.outer_proxies) == 2
    assert len(cert.cells) == (0 if all(g.exact_zero for g in cert.incidence.gaps) else 2)
    assert len(certificate_bytes(cert)) < MAX_CERTIFICATE_BYTES
    assert result.resources.operations_end < 50_000
    assert check_sector_certificate(source, cert).accepted
    v0, v1 = tuple(map(F, start)), tuple(map(F, end))
    radius = F(cert.incidence.core_arcs[0][1].start_radius)
    with localcontext() as precision:
        precision.prec = 100
        theta = reference_angle(v0, v1, direction)
        enclosed(cert.area.signed_angle, theta)
        enclosed(cert.area.reference_area, decimal(radius**2) * abs(theta) / 2)
        enclosed(cert.area.signed_reference_area, decimal(radius**2) * theta / 2)
        enclosed(
            cert.area.source_cell_allowance,
            2 * reference_pi() * decimal(fraction(cert.source_cell_radius) ** 2),
        )
        enclosed(
            cert.area.perimeter,
            decimal(radius) * abs(theta)
            + decimal(dot(v0, v0)).sqrt()
            + decimal(dot(v1, v1)).sqrt(),
        )
    assert fraction(cert.area.source_area.lower) >= F(1, 10**12)
    assert cert.jordan.radial_interiors_disjoint and cert.jordan.same_exterior_simple_closure
    assert cert.jordan.center_continuation == (
        "straight_continuation" if not cross(v0, v1) else "ordinary_corner"
    )
    boundary = cert.boundary
    assert all(boundary[i].end_id == boundary[(i + 1) % 3].start_id for i in range(3))
    assert boundary[0].reversed_from_authored == (direction == "cw")


@pytest.mark.parametrize("start,end", POSITIVES)
@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_exact_circle_disk_equations_and_complete_exit_membership(start, end, direction):
    cert = classify_sector(sketch(start, end, direction=direction)).certificate
    rays = (tuple(map(F, start)), tuple(map(F, end)))
    radius = F(cert.incidence.core_arcs[0][1].start_radius)
    assert 0 <= fraction(cert.source_cell_radius) <= 16 * DELTA
    for disk in cert.cells + cert.outer_proxies:
        v = rays[0 if disk.point_id == "start" else 1]
        rho = fraction(disk.radius)
        assert len(disk.circle_exits) == len(disk.radial_exits) == 2
        assert sum(exit.retained for exit in disk.circle_exits) == 1
        assert sum(exit.retained for exit in disk.radial_exits) == 1
        for inequality in disk.inequalities:
            assert fraction(inequality.lhs) < fraction(inequality.rhs)
        for exit in disk.circle_exits:
            p, q = tuple(map(fraction, exit.rational)), tuple(map(fraction, exit.radical))
            h, z = fraction(exit.radicand), fraction(exit.denominator)
            assert h > 0 and z > 0 and exit.multiplicity == 1
            assert dot(p, q) == 0
            assert dot(p, p) + h * dot(q, q) == radius**2 * z**2
            offset = sub(p, tuple(z * coordinate for coordinate in v))
            assert dot(offset, q) == 0
            assert dot(offset, offset) + h * dot(q, q) == rho**2 * z**2
            assert cyclic_membership(*rays, p, q, h, direction) == exit.original_arc_position
            assert exit.retained == (exit.original_arc_position == "INTERIOR")
        assert fraction(disk.circle_exits[0].angular_parameter.upper) < 0
        assert fraction(disk.circle_exits[1].angular_parameter.lower) > 0
        for exit in disk.radial_exits:
            p, q, h, z = map(
                fraction, (exit.rational, exit.radical, exit.radicand, exit.denominator)
            )
            s = dot(v, v)
            assert s * ((p - z) ** 2 + q**2 * h) == rho**2 * z**2
            assert 2 * s * (p - z) * q == 0
        assert disk.radial_exits[0].retained and not disk.radial_exits[1].retained
    for _, exits in cert.center_proxy.line_exits:
        assert len(exits) == 2 and exits[0].original_line_position == "BEFORE_START"
        assert exits[1].retained and exits[1].original_line_position == "INTERIOR"


@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("sign_gap,position", [(1, "INTERIOR"), (-1, "AFTER_END")])
def test_root_membership_and_original_perimeter_for_positive_gap(direction, sign_gap, position):
    source = sketch((10, 0), (0, 10 + sign_gap * 2**-31), direction=direction)
    cert = classify_sector(source).certificate
    own = [item for item in cert.assignments if item.assigned_join_id == "end"][0]
    assert own.original_line_position == position and own.original_arc_position == "AT_END"
    assert own.original_finite_crossing == (sign_gap == 1)
    assert own.reference_line_position == "AT_END"
    for ledger in cert.incidence.boundaries:
        negative, positive = ledger.roots.roots
        assert negative.support.position == "BEFORE_START"
        assert negative.arc_position == ("OUTSIDE" if direction == "ccw" else "INTERIOR")
        assert positive.support.branch == "PLUS"
    with localcontext() as p:
        p.prec = 100
        theta = reference_pi() * (Decimal(1) / 2 if direction == "ccw" else Decimal(3) / 2)
        original = 20 + Decimal(sign_gap) / Decimal(2**31) + 10 * theta
        enclosed(cert.area.perimeter, original)
        reference_perimeter = 20 + 10 * theta
        assert (
            not decimal(cert.area.perimeter.lower)
            <= reference_perimeter
            <= decimal(cert.area.perimeter.upper)
        )


def test_exact_zero_and_zero_residual_are_distinct():
    exact = classify_sector(sketch((3, 4), (-4, 3))).certificate
    rounded = classify_sector(sketch((13, 29), (-29, 13))).certificate
    assert not exact.cells and fraction(exact.area.source_cell_allowance.upper) == 0
    assert len(rounded.cells) == 2 and fraction(rounded.area.source_cell_allowance.lower) > 0
    assert (
        rounded.incidence.core_arcs[0][1].start_radius
        == rounded.incidence.core_arcs[0][1].end_radius
    )
    assert all(not gap.exact_zero for gap in rounded.incidence.gaps)


@pytest.mark.parametrize("center", [(100, -100), (999990, -999990), (-999990, 999990)])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize(
    "plane", [Plane(), Plane(origin=(1, 2, 3)), Plane(quaternion=(0.5, 0.5, 0.5, 0.5))]
)
def test_exact_translation_near_limits_and_core_valid_frames(center, direction, plane):
    source = sketch(
        (center[0] + 3, center[1] + 4),
        (center[0] - 4, center[1] + 3),
        center=center,
        direction=direction,
        plane=plane,
    )
    cert = classify_sector(source).certificate
    assert cert is not None and not cert.cells
    assert check_sector_certificate(source, cert).accepted
    assert cert.incidence.arc.center == center


@pytest.mark.parametrize("radius", [1, 1000])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_radius_inclusive_boundary(radius, direction):
    assert (
        classify_sector(sketch((radius, 0), (0, radius), direction=direction)).status
        == "certified_sector"
    )


@pytest.mark.parametrize("radius", [math.nextafter(1.0, 0.0), math.nextafter(1000.0, math.inf)])
def test_radius_neighbor_rejection(radius):
    result = classify_sector(sketch((radius, 0), (0, radius)))
    assert result.status == "unsupported" and result.code == "unsupported_profile_scale"
    assert result.certificate is None


@pytest.mark.parametrize("height", [1, 1000, 1.0, 1000.0])
def test_height_separate_from_source(height):
    assert extrusion_preflight(height).supported
    assert classify_sector(sketch()).incidence.height == 1


@pytest.mark.parametrize(
    "height", [0, -1, math.nextafter(1.0, 0.0), math.nextafter(1000.0, math.inf)]
)
def test_height_outside_domain(height):
    result = extrusion_preflight(height)
    assert not result.supported and result.code == "unsupported_profile_scale"


@pytest.mark.parametrize(
    "height",
    [True, False, None, "1", math.nan, math.inf, pytest.param(10**10000, id="huge_integer")],
)
def test_malformed_height(height):
    with pytest.raises(SectorInputError, match="invalid_height"):
        extrusion_preflight(height)


@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("end", [(6, 8), (2**-40, 10)])
def test_positive_dot_rejected_before_gap(direction, end):
    result = classify_sector(sketch((10, 0), end, direction=direction))
    assert result.stage == "SUPPORT" and result.code == "unsupported_profile_sweep"


@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_negative_dot_neighbor_passes(direction):
    assert classify_sector(sketch((10, 0), (-(2**-40), 10), direction=direction)).certificate


def test_core_accepted_large_gap_rejected_with_all_roots():
    result = classify_sector(sketch((10, 0), (0, 10 + 2**-24)))
    assert result.code == "unsupported_endpoint_discrepancy" and result.stage == "DISCREPANCY"
    assert result.incidence.ledgers_complete and len(result.incidence.boundaries) == 2
    assert not result.cells and result.certificate is None


@pytest.mark.parametrize("sign_gap", [-1, 1])
def test_exact_rational_gap_threshold_neighbors(sign_gap):
    nominal = 10.0 + sign_gap * 1e-9
    for end in (math.nextafter(nominal, -math.inf), nominal, math.nextafter(nominal, math.inf)):
        source = sketch((10, 0), (0, end))
        result = classify_sector(source)
        actual_gap = abs(F(end) - 10)
        assert (result.status == "certified_sector") == (actual_gap <= DELTA)
        assert actual_gap != DELTA


@pytest.mark.parametrize("extra", ["alias", "coincidence", "line", "circle", "arc", "chord"])
def test_unsupported_forms_and_identity(extra):
    source = sketch()
    if extra in ("alias", "coincidence"):
        source = replace(
            source,
            points=source.points + (Point("alias", 5, 0),),
            lines=(Line("radial_start", "center", "alias"), source.lines[1]),
        )
        if extra == "coincidence":
            source = replace(
                source, constraints=(Constraint("coincide", "coincident", ("start", "alias")),)
            )
    elif extra == "line":
        source = replace(source, lines=source.lines + (Line("extra", "start", "end"),))
    elif extra == "circle":
        source = replace(source, circles=(Circle("circle", "center", 5),))
    elif extra == "arc":
        source = replace(source, arcs=source.arcs + (Arc("other", "center", "end", "start", "cw"),))
    else:
        source = replace(source, lines=(Line("chord", "start", "end"),))
    result = classify_sector(source)
    assert result.stage == "GRAPH" and result.status == "unsupported"
    assert result.code == (
        "unsupported_profile_coincidence"
        if extra in ("alias", "coincidence")
        else "unsupported_profile_form"
    )
    assert result.certificate is None


def test_graph_chord_precedes_later_support_rejection():
    source = sketch((10, 0), (6, 8))
    source = replace(source, lines=(Line("chord", "start", "end"),))
    result = classify_sector(source)
    assert result.stage == "GRAPH" and result.code == "unsupported_profile_form"


def test_model_errors_remain_distinct():
    with pytest.raises(SketchError):
        classify_sector(replace(sketch(), points=()))
    with pytest.raises(SectorInputError, match="invalid_context"):
        classify_sector(sketch(), context=object())


def test_universal_sector_clearance_identity_and_strict_constants():
    assert (B - DELTA) ** 2 - 2 * D**2 == F(41801, 10**18) > 0
    assert B > D and F(1, 2) > D
    rng = random.Random(7319)
    # Independent exact rational identity: choose a rational unit circle point
    # via Pythagorean parametrization, not angular sampling or sqrt rounding.
    for _ in range(200):
        r, s, t = (
            F(rng.randrange(1, 1001)),
            F(rng.randrange(2001), 2),
            F(rng.randrange(-100, 101), 17),
        )
        q = (r * (1 - t * t) / (1 + t * t), r * 2 * t / (1 + t * t))
        p, q0 = (s, F(0)), (r, F(0))
        x2, y2 = dot(sub(q, q0), sub(q, q0)), (s - r) ** 2
        assert dot(sub(q, p), sub(q, p)) == y2 + (s / r) * x2
        if s >= r / 2:
            assert dot(sub(q, p), sub(q, p)) >= (x2 + y2) / 2
        else:
            assert dot(sub(q, p), sub(q, p)) > r * r / 4
    for r in (F(1), F(5), F(1000)):
        x = B + DELTA
        assert 4 * r * r * x * x < L * L * (4 * r * r - x * x)


def test_shared_budget_checker_offsets_and_continuing_context():
    context = PrimitiveContext()
    context.coordinate(7)
    source = sketch((5, 0), (-3, 4))
    first = classify_sector(source, context=context)
    assert first.resources.operations_start > 0
    before = context.operations
    checked = check_sector_certificate(source, first.certificate, context=context)
    assert checked.accepted
    assert checked.recomputed.resources.operations_start == before
    assert context.operations == checked.recomputed.resources.operations_end
    before = context.operations
    failed = classify_sector(source, context=context)
    assert failed.status == "numerical_ambiguity" and failed.code == "operation_limit"
    assert failed.resources.operations_start == before and context.operations == 100_000
    assert failed.certificate is None


@pytest.mark.parametrize("budget", [1, 50, 500, 1000, 2000, 4000, 30_000])
def test_aggregate_exhaustion_retains_only_completed_evidence(budget):
    context = PrimitiveContext(max_operations=budget)
    result = classify_sector(sketch((13, 29), (-29, 13)), context=context)
    assert result.status == "numerical_ambiguity" and result.code == "operation_limit"
    assert result.certificate is None and context.operations == budget
    assert result.incidence.ledgers_complete == (len(result.incidence.boundaries) == 2)


@pytest.mark.parametrize("bits", [16, 32, 64, 128])
def test_checked_integer_budget_rejection(bits):
    result = classify_sector(sketch((13, 29), (-29, 13)), context=PrimitiveContext(max_bits=bits))
    assert result.status == "numerical_ambiguity" and result.code == "integer_limit"
    assert result.certificate is None


def test_subnormal_difference_is_exact_or_explicit_bounded_rejection():
    source = sketch((1, 0), (0, 1), center=(math.ulp(0.0), 0))
    result = classify_sector(source)
    assert result.status in ("certified_sector", "numerical_ambiguity")
    assert result.incidence.gaps and not result.incidence.gaps[0].exact_zero
    if result.certificate:
        assert result.certificate.cells and fraction(result.certificate.source_cell_radius) > 0
        assert check_sector_certificate(source, result.certificate).accepted
    else:
        assert result.code in (
            "integer_limit",
            "operation_limit",
            "unresolved_disk_exits",
            "exponent_limit",
        )


@pytest.fixture
def ordinary():
    source = sketch((13, 29), (-29, 13))
    return source, classify_sector(source).certificate


@pytest.mark.parametrize(
    "target",
    [
        "version_bool",
        "semantics",
        "hash",
        "source",
        "direction",
        "root",
        "exit",
        "gap",
        "cell",
        "jordan",
        "area",
        "order",
        "counter",
        "counter_bool",
        "precision",
        "extra_root",
        "missing_root",
    ],
)
def test_checker_rejects_forged_complete_records(ordinary, target):
    source, cert = ordinary
    if target == "version_bool":
        changed = change(cert, version=True)
    elif target == "semantics":
        changed = change(cert, semantics="literal_simple_connectors")
    elif target == "hash":
        changed = change(cert, source_sha256="0" * 64)
    elif target == "source":
        changed = change(
            cert, incidence=replace(cert.incidence, source_json=cert.incidence.source_json + " ")
        )
    elif target == "direction":
        changed = change(
            cert, incidence=replace(cert.incidence, arc=replace(cert.incidence.arc, direction="cw"))
        )
    elif target == "root":
        changed = change(
            cert,
            assignments=(replace(cert.assignments[0], original_finite_crossing=True),)
            + cert.assignments[1:],
        )
    elif target == "exit":
        disk = cert.cells[0]
        disk = replace(
            disk,
            circle_exits=(
                replace(disk.circle_exits[0], retained=not disk.circle_exits[0].retained),
                disk.circle_exits[1],
            ),
        )
        changed = change(cert, cells=(disk, cert.cells[1]))
    elif target == "gap":
        changed = change(
            cert,
            gap_enclosures=(
                replace(cert.gap_enclosures[0], eta=sector.ExactRatio(Dyadic(0, 0), Dyadic(1, 0))),
                cert.gap_enclosures[1],
            ),
        )
    elif target == "cell":
        changed = change(cert, source_cell_radius=sector.ExactRatio(Dyadic(1, 0), Dyadic(1, 0)))
    elif target == "jordan":
        changed = change(cert, jordan=replace(cert.jordan, normalized_winding=True))
    elif target == "area":
        changed = change(cert, area=replace(cert.area, source_area=cert.area.reference_area))
    elif target == "order":
        changed = change(cert, boundary=cert.boundary[::-1])
    elif target == "counter":
        changed = change(
            cert,
            resources=replace(cert.resources, operations_end=cert.resources.operations_end + 1),
        )
    elif target == "counter_bool":
        changed = change(cert, resources=replace(cert.resources, refinements=True))
    elif target == "precision":
        changed = change(cert, area=replace(cert.area, precision=128))
    elif target == "extra_root":
        changed = change(cert, assignments=cert.assignments + (cert.assignments[0],))
    else:
        changed = change(cert, assignments=cert.assignments[:-1])
    assert not check_sector_certificate(source, changed).accepted


def test_checker_rejects_mutated_bound_sketch(ordinary):
    source, cert = ordinary
    changed = replace(source, arcs=(replace(source.arcs[0], direction="cw"),))
    assert not check_sector_certificate(changed, cert).accepted
    with pytest.raises(FrozenInstanceError):
        cert.version = 2


def test_serialization_caps_and_hostile_types_before_recomputation(ordinary):
    source, cert = ordinary
    for changed in (
        change(cert, semantics="x" * (MAX_CERTIFICATE_BYTES + 1)),
        change(cert, assignments=(cert.assignments[0],) * 257),
        change(cert, version=1 << 65536),
        change(cert, boundary=list(cert.boundary)),
        change(cert, area=object()),
    ):
        context = PrimitiveContext()
        assert not check_sector_certificate(source, changed, context=context).accepted
        assert context.operations == 0
    assert not check_sector_certificate(source, object()).accepted


def test_cap_failure_is_nonpassing_not_silently_truncated(monkeypatch):
    monkeypatch.setattr(sector, "MAX_CERTIFICATE_BYTES", 1024)
    result = classify_sector(sketch())
    assert result.status == "numerical_ambiguity" and result.code == "certificate_limit"
    assert result.certificate is None and result.incidence.ledgers_complete


@pytest.mark.parametrize(
    "mutation", ["double", "missing", "wrong_arc", "wrong_finite", "duplicate"]
)
def test_root_helper_never_suppresses_extra_or_malformed_roots(monkeypatch, mutation):
    source = sketch()
    geometry = sector.sector_geometry_source(source)
    report = geometry_preflight(geometry)
    ledger = report.boundaries[0]
    minus, plus = ledger.roots.roots
    if mutation == "double":
        roots = (replace(minus, support=replace(minus.support, multiplicity=2)), plus)
    elif mutation == "missing":
        roots = (plus,)
    elif mutation == "wrong_arc":
        roots = (minus, replace(plus, arc_position="OUTSIDE"))
    elif mutation == "wrong_finite":
        roots = (replace(minus, support=replace(minus.support, position="INTERIOR")), plus)
    else:
        roots = (plus, plus)
    forged = replace(
        report,
        boundaries=(
            replace(ledger, roots=replace(ledger.roots, roots=roots)),
            report.boundaries[1],
        ),
    )
    monkeypatch.setattr(policy, "geometry_preflight", lambda *a, **k: forged)
    result = policy.classify_sector_geometry(geometry)
    assert result.status == "unsupported" and result.code == "unsupported_profile_contact"


def test_pure_import_dependencies_and_live_native_traps():
    allowed = {
        "__future__",
        "hashlib",
        "json",
        "math",
        "dataclasses",
        "arc_geometry",
        "arc_profile_incidence",
        "arc_profile_intervals",
        "arc_profile_primitives",
        "arc_profile_sector_policy",
        "arc_profile_sector_source",
        "sketch_model",
    }
    tree = ast.parse((ROOT / "src/mechanical_cad/arc_profile_sector.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed
    script = """
import builtins, sys
real = builtins.__import__
forbidden = {'OCP','slvs','bpy','numpy','sympy','fractions','mechanical_cad.kernel_ocp','mechanical_cad.sketch_solver','mechanical_cad.engine','mechanical_cad.sidecar','mechanical_cad.sketch_service','mechanical_cad.profile_region'}
def trapped(name, *args, **kwargs):
    if name in forbidden or name.split('.')[0] in forbidden:
        raise AssertionError('FORBIDDEN:'+name)
    return real(name,*args,**kwargs)
builtins.__import__=trapped
from mechanical_cad.arc_profile_sector import classify_sector,check_sector_certificate
from mechanical_cad.sketch_model import Sketch,Point,Line,Arc
s=Sketch('s',(Point('c',0,0),Point('a',13,29),Point('b',-29,13)),(Line('a_line','c','a'),Line('b_line','c','b')),(),schema_version=3,arcs=(Arc('arc','c','a','b','ccw'),))
r=classify_sector(s)
assert r.status=='certified_sector'
assert check_sector_certificate(s,r.certificate).accepted
assert not forbidden.intersection(sys.modules)
print('SECTOR_PURE_TRAP_PASS')
"""
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    process = subprocess.run(
        [sys.executable, "-S", "-c", script],
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert "SECTOR_PURE_TRAP_PASS" in process.stdout


def test_geometry_digest_is_separate_from_full_sketch_binding():
    first_source = sketch()
    changed_plane = replace(first_source, plane=Plane(origin=(1, 2, 3)))
    first, second = (
        classify_sector(first_source).certificate,
        classify_sector(changed_plane).certificate,
    )
    assert first.source_sha256 != second.source_sha256
    assert first.geometry.geometry_sha256 == second.geometry.geometry_sha256
    assert first.source_json == first.incidence.source_json
    assert first.geometry.incidence.source_json != first.source_json
    assert not check_sector_certificate(changed_plane, first).accepted
    with_unused = replace(first_source, points=first_source.points + (Point("unused", 1, 2),))
    third = classify_sector(with_unused).certificate
    assert third.geometry.geometry_sha256 != first.geometry.geometry_sha256


def test_exactly_one_full_geometry_classification(monkeypatch):
    calls = []
    original = sector.classify_sector_geometry

    def counted(*args, **kwargs):
        calls.append(kwargs["context"].operations)
        return original(*args, **kwargs)

    monkeypatch.setattr(sector, "classify_sector_geometry", counted)
    result = classify_sector(sketch((5, 0), (-3, 4)))
    assert result.certificate and len(calls) == 1
    assert result.certificate.incidence.operations_end == calls[0]
    assert result.certificate.geometry.resources.operations_start == calls[0]
    assert result.resources.operations_end == result.certificate.geometry.resources.operations_end


def test_shared_policy_copies_without_model_or_original_package(tmp_path):
    package = tmp_path / "shared_sector_policy"
    package.mkdir()
    (package / "__init__.py").write_text("")
    for name in (
        "arc_geometry",
        "arc_profile_primitives",
        "arc_profile_intervals",
        "arc_profile_sector_source",
        "arc_profile_sector_policy",
    ):
        original = ROOT / "src" / "mechanical_cad" / (name + ".py")
        (package / (name + ".py")).write_bytes(original.read_bytes())
    script = """
import builtins, sys
real=builtins.__import__
def trapped(name,*args,**kwargs):
    if name.startswith('mechanical_cad') or name.split('.')[0] in {'OCP','slvs','bpy','numpy','fractions','sympy'} or any(x in name for x in ('sketch_model','arc_profile_incidence','expressions')):
        raise AssertionError('FORBIDDEN:'+name)
    return real(name,*args,**kwargs)
builtins.__import__=trapped
from shared_sector_policy.arc_profile_sector_source import SectorGeometrySource,SectorPoint,SectorLine,SectorArc
from shared_sector_policy.arc_profile_sector_policy import classify_sector_geometry,check_sector_geometry_certificate
s=SectorGeometrySource(points=(SectorPoint('c',0,0),SectorPoint('a',13,29),SectorPoint('b',-29,13)),lines=(SectorLine('a_line','c','a'),SectorLine('b_line','c','b')),arcs=(SectorArc('arc','c','a','b','ccw'),))
r=classify_sector_geometry(s)
assert r.status=='certified_sector', (r.status,r.code)
assert check_sector_geometry_certificate(s,r.certificate).accepted
assert not any(name.startswith('mechanical_cad') for name in sys.modules)
print('BYTE_EXACT_SHARED_POLICY_TRAP_PASS')
"""
    process = subprocess.run(
        [sys.executable, "-S", "-c", script],
        env=dict(os.environ, PYTHONPATH=str(tmp_path)),
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert "BYTE_EXACT_SHARED_POLICY_TRAP_PASS" in process.stdout


def test_geometry_projection_rejects_duck_typed_and_subclass_inputs():
    class Counterfeit:
        def to_json(self):
            raise AssertionError("counterfeit serializer must not run")

    class DerivedSketch(Sketch):
        pass

    for value in (Counterfeit(), DerivedSketch("derived", (), (), ())):
        with pytest.raises(SketchError):
            sector.sector_geometry_source(value)
