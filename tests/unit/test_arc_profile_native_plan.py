"""Native-free preparation contracts and independent exact root references.

The Fraction oracle expands each quadratic in a formal radical and compares its
roots without floating-point square roots. These tests never construct native
geometry or import a native kernel, including in the isolated import check.
"""

from __future__ import annotations

import hashlib
import importlib.abc
import math
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction as F
from pathlib import Path

import pytest

import mechanical_cad.arc_profile_native_plan as native
from mechanical_cad.arc_profile_primitives import Dyadic, PrimitiveContext, PrimitiveError
from mechanical_cad.arc_profile_sector_policy import (
    ExactRatio,
    SectorInputError,
    classify_sector_geometry,
)
from mechanical_cad.arc_profile_sector_source import (
    SectorArc,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
    SourceInputError,
)

ROOT = Path(__file__).resolve().parents[2]
NATIVE_ROOTS = {"OCP", "OCC", "cadquery", "slvs", "bpy"}


class _NoNativeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in NATIVE_ROOTS or fullname == "mechanical_cad.kernel_ocp":
            raise AssertionError(f"native import forbidden in pure-plan tests: {fullname}")
        return None


@pytest.fixture(autouse=True)
def block_native_imports():
    blocker = _NoNativeImports()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


def source(*, center=(0.0, 0.0), start=(5.0, 0.0), end=(0.0, 5.0), direction="ccw"):
    return SectorGeometrySource(
        (SectorPoint("c", *center), SectorPoint("a", *start), SectorPoint("b", *end)),
        (SectorLine("radius_a", "c", "a"), SectorLine("radius_b", "c", "b")),
        (SectorArc("arc", "c", "a", "b", direction),),
    )


def fraction(value):
    if type(value) is Dyadic:
        return F(value.mantissa) * F(2) ** value.exponent
    if type(value) is ExactRatio:
        return fraction(value.numerator) / fraction(value.denominator)
    return F(value)


def sign(value):
    return (value > 0) - (value < 0)


def radical_sign(p, q, h):
    """Sign of p + q sqrt(h), using only rational comparisons and squares."""
    assert h >= 0
    if q == 0 or h == 0:
        return sign(p)
    if p == 0 or sign(p) == sign(q):
        return sign(q)
    return sign(q) * sign(q * q * h - p * p)


def assert_radical_enclosed(interval, p, q, h):
    lo, hi = fraction(interval.lower), fraction(interval.upper)
    assert lo <= hi
    assert radical_sign(p - lo, q, h) >= 0
    assert radical_sign(p - hi, q, h) <= 0


def dot(left, right):
    return sum(a * b for a, b in zip(left, right, strict=True))


def fresh_certificate(value=None, *, context=None):
    context = native.entry_context() if context is None else context
    result = classify_sector_geometry(source() if value is None else value, context=context)
    assert result.status == "certified_sector", result.code
    return result.certificate, context


@pytest.fixture(scope="module")
def cardinal_plan():
    return native.prepare_native_geometry(source(), native.NativePlane())


@pytest.mark.parametrize("bad", [None, {}, (), True, object()])
def test_plane_requires_exact_record_type(bad):
    with pytest.raises(native.NativePlanError, match="^invalid_native_plane$"):
        native.prepare_native_geometry(source(), bad)


def test_plane_subclass_is_not_an_authorized_record():
    class DerivedPlane(native.NativePlane):
        pass

    with pytest.raises(native.NativePlanError, match="^invalid_native_plane$"):
        native.prepare_native_geometry(source(), DerivedPlane())


@pytest.mark.parametrize(
    "plane",
    [
        native.NativePlane(origin=[0, 0, 0]),
        native.NativePlane(origin=(0, 0)),
        native.NativePlane(origin=(0, 0, 0, 0)),
        native.NativePlane(quaternion=[1, 0, 0, 0]),
        native.NativePlane(quaternion=(1, 0, 0)),
        native.NativePlane(quaternion=(1, 0, 0, 0, 0)),
        native.NativePlane(origin=(True, 0, 0)),
        native.NativePlane(quaternion=(True, 0, 0, 0)),
        native.NativePlane(origin=("0", 0, 0)),
        native.NativePlane(quaternion=(F(1), 0, 0, 0)),
        native.NativePlane(origin=(math.inf, 0, 0)),
        native.NativePlane(origin=(math.nan, 0, 0)),
        native.NativePlane(quaternion=(math.inf, 0, 0, 0)),
        native.NativePlane(quaternion=(math.nan, 0, 0, 0)),
    ],
)
def test_plane_strict_container_and_scalar_grammar(plane):
    with pytest.raises(native.NativePlanError, match="^invalid_native_plane$"):
        native.prepare_native_geometry(source(), plane)


@pytest.mark.parametrize("slot", ["origin", "quaternion"])
@pytest.mark.parametrize("huge", [1 << 100_000, -(1 << 100_000)], ids=["positive", "negative"])
def test_plane_bounds_huge_integer_before_any_float_conversion(slot, huge):
    plane = (
        native.NativePlane(origin=(huge, 0, 0))
        if slot == "origin"
        else native.NativePlane(quaternion=(huge, 0, 0, 0))
    )
    with pytest.raises(native.NativePlanError, match="^invalid_native_plane$"):
        native.prepare_native_geometry(source(), plane)


@pytest.mark.parametrize("missing", ["origin", "quaternion", "both"])
def test_plane_missing_slots_fail_closed(missing):
    plane = object.__new__(native.NativePlane)
    if missing not in ("origin", "both"):
        object.__setattr__(plane, "origin", (0, 0, 0))
    if missing not in ("quaternion", "both"):
        object.__setattr__(plane, "quaternion", (1, 0, 0, 0))
    with pytest.raises(native.NativePlanError, match="^invalid_native_plane$"):
        native.prepare_native_geometry(source(), plane)


@pytest.mark.parametrize(
    "plane",
    [
        native.NativePlane(origin=(math.ulp(0.0), 0, 0)),
        native.NativePlane(origin=(0, 1, 0)),
        native.NativePlane(origin=(0, 0, -1)),
        native.NativePlane(quaternion=(0, 0, 0, 0)),
        native.NativePlane(quaternion=(1, 0, 0, math.ulp(0.0))),
        native.NativePlane(quaternion=(math.cos(0.1), 0, 0, math.sin(0.1))),
        native.NativePlane(quaternion=(2, 0, 0, 0)),
    ],
)
def test_finite_but_unsupported_frames_are_not_rounded_to_a_supported_frame(plane):
    with pytest.raises(native.NativePlanError, match="^unsupported_native_frame$"):
        native.prepare_native_geometry(source(), plane)


@pytest.mark.parametrize(
    "quaternion,expected",
    [
        ((1, 0, 0, 0), ((1, 0, 0), (0, 1, 0), (0, 0, 1))),
        ((-1, 0, 0, 0), ((1, 0, 0), (0, 1, 0), (0, 0, 1))),
        ((0, 1, 0, 0), ((1, 0, 0), (0, -1, 0), (0, 0, -1))),
        ((0.5, 0.5, 0.5, 0.5), ((0, 1, 0), (0, 0, 1), (1, 0, 0))),
    ],
)
def test_exact_signed_permutation_frames_and_vertices(quaternion, expected):
    plane = native.NativePlane(origin=(-0.0, 0, 0.0), quaternion=quaternion)
    plan = native.prepare_native_geometry(source(), plane)
    assert plan.plane is plane
    assert (plan.frame.u, plan.frame.v, plan.frame.normal) == expected
    assert all(
        type(component) is float
        for vector in (plan.frame.u, plan.frame.v, plan.frame.normal)
        for component in vector
    )
    for name, point in plan.vertices:
        local = {"c": (0, 0), "a": (5, 0), "b": (0, 5)}[name]
        assert point == tuple(
            local[0] * u + local[1] * v for u, v in zip(*expected[:2], strict=True)
        )
        assert all(type(component) is float for component in point)


def test_entry_context_preserves_exact_object_and_never_resets_usage():
    context = PrimitiveContext(max_bits=4096, max_operations=90_000)
    context.coordinate(5)
    before = context.operations
    assert native.entry_context(context) is context
    assert context.operations == before
    assert context.max_bits == 4096 and context.max_operations == 90_000
    assert native.entry_context() is not native.entry_context()
    with pytest.raises(AttributeError):
        context.operations = 0


@pytest.mark.parametrize("bad", [True, {}, (), object()])
def test_entry_context_rejects_unqualified_context(bad):
    with pytest.raises(SectorInputError, match="^invalid_context$"):
        native.entry_context(bad)


def test_context_subclass_is_rejected_before_overridden_arithmetic_runs():
    class DerivedContext(PrimitiveContext):
        def coordinate(self, value):
            raise AssertionError("unqualified override must not execute")

    with pytest.raises(SectorInputError, match="^invalid_context$"):
        native.prepare_native_geometry(source(), native.NativePlane(), context=DerivedContext())


def test_exhausted_context_is_not_replaced_by_a_fresh_budget():
    context = PrimitiveContext(max_operations=1)
    context._tick()
    with pytest.raises(native.NativePlanError, match="^operation_limit$"):
        native.prepare_native_geometry(source(), native.NativePlane(), context=context)
    assert context.operations == context.max_operations == 1
    assert native.entry_context(context) is context


def test_source_and_native_preparation_charge_one_continuous_context():
    context = PrimitiveContext()
    context.coordinate(17)
    start = context.operations
    certificate, context = fresh_certificate(context=context)
    source_end = context.operations
    assert certificate.resources.operations_start == start
    assert certificate.resources.operations_end == source_end
    plan = native._continue_native_plan(certificate, native.NativePlane(), context)
    assert plan.source is certificate
    assert plan.resources.operations_start == start
    assert plan.resources.operations_end == context.operations > source_end > start
    assert plan.resources.max_operations == certificate.resources.max_operations
    assert plan.resources.max_bits == certificate.resources.max_bits
    assert plan.resources.refinements == certificate.resources.refinements
    assert plan.source.resources.operations_end == source_end


def test_public_prepare_recomputes_source_and_passes_the_identical_context(monkeypatch):
    original = native.classify_sector_geometry
    seen = []

    def observe(value, *, context):
        seen.append((value, context, context.operations))
        return original(value, context=context)

    monkeypatch.setattr(native, "classify_sector_geometry", observe)
    value = source()
    first_context, second_context = native.entry_context(), native.entry_context()
    first_context.coordinate(23)
    first = native.prepare_native_geometry(value, native.NativePlane(), context=first_context)
    second = native.prepare_native_geometry(value, native.NativePlane(), context=second_context)
    assert [(item[0], item[1]) for item in seen] == [
        (value, first_context),
        (value, second_context),
    ]
    assert first.source is not second.source
    assert first.resources.operations_start == seen[0][2] > 0
    assert second.resources.operations_start == 0
    assert first.resources.operations_end == first_context.operations
    assert second.resources.operations_end == second_context.operations


def test_public_prepare_does_not_accept_detached_certificate_as_source(cardinal_plan):
    with pytest.raises(SourceInputError, match="^invalid_source$"):
        native.prepare_native_geometry(cardinal_plan.source, native.NativePlane())


@pytest.mark.parametrize("advance", [False, True])
def test_stale_or_already_consumed_continuation_rejects_without_more_work(advance):
    certificate, context = fresh_certificate()
    if advance:
        context.coordinate(1)
    else:
        native._continue_native_plan(certificate, native.NativePlane(), context)
    before = context.operations
    with pytest.raises(native.NativePlanError, match="^native_context_discontinuity$"):
        native._continue_native_plan(certificate, native.NativePlane(), context)
    assert context.operations == before


def test_continuation_cannot_substitute_a_fresh_context():
    certificate, _ = fresh_certificate()
    context = native.entry_context()
    with pytest.raises(native.NativePlanError, match="^native_context_discontinuity$"):
        native._continue_native_plan(certificate, native.NativePlane(), context)
    assert context.operations == 0


@pytest.mark.parametrize("start", [-1, True, 0.0, "0", 1])
def test_continuation_rejects_invalid_or_forward_source_operation_start(start):
    certificate, context = fresh_certificate()
    before = context.operations
    with pytest.raises(native.NativePlanError, match="^native_context_discontinuity$"):
        native._continue_native_plan(
            certificate, native.NativePlane(), context, operations_start=start
        )
    assert context.operations == before


def test_continuation_accepts_earlier_genuine_entry_counter():
    context = native.entry_context()
    context.coordinate(42)
    certificate, context = fresh_certificate(context=context)
    assert certificate.resources.operations_start > 0
    plan = native._continue_native_plan(
        certificate, native.NativePlane(), context, operations_start=0
    )
    assert plan.resources.operations_start == 0
    assert plan.source.resources.operations_start > 0


def test_continuation_fails_when_source_consumes_the_remaining_operation_budget():
    reference, _ = fresh_certificate()
    context = PrimitiveContext(max_operations=reference.resources.operations_end)
    certificate, context = fresh_certificate(context=context)
    assert context.operations == context.max_operations
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        native._continue_native_plan(certificate, native.NativePlane(), context)
    assert context.operations == context.max_operations


def test_continuation_revalidates_cached_pi_precision():
    certificate, context = fresh_certificate()
    pi = replace(certificate.area.pi, precision=128)
    altered = replace(certificate, area=replace(certificate.area, pi=pi))
    with pytest.raises(PrimitiveError, match="^precision_mismatch$"):
        native._continue_native_plan(altered, native.NativePlane(), context)


@pytest.mark.parametrize(
    "start,end,center",
    [
        ((5.0, 0.0), (0.0, 5.0), (0.0, 0.0)),
        ((3.0, 4.0), (-4.0, 3.0), (0.0, 0.0)),
        ((13.0, 29.0), (-29.0, 13.0), (0.0, 0.0)),
        ((5.0, 0.0), (-3.0, 4.0), (0.0, 0.0)),
        ((5.0, 0.0), (0.0, 5.0 + 0.5e-9), (0.0, 0.0)),
        ((5.0, 0.0), (0.0, 5.0 - 0.5e-9), (0.0, 0.0)),
        ((-3.0, -4.0), (4.0, -3.0), (0.0, 0.0)),
        ((5.0, 0.0), (-5.0, 0.0), (0.0, 0.0)),
        ((1027.0, 15.0), (985.0, -1.0), (1014.0, -14.0)),
    ],
    ids=[
        "cardinal",
        "pythagorean",
        "rounded_hypot",
        "nonquadrantal",
        "outward_gap",
        "inward_gap",
        "seam",
        "semicircle",
        "translated",
    ],
)
@pytest.mark.parametrize("direction", ["ccw", "cw"])
def test_roots_and_frozen_cell_margins_match_independent_fraction_oracle(
    start, end, center, direction
):
    value = source(start=start, end=end, center=center, direction=direction)
    plan = native.prepare_native_geometry(value, native.NativePlane())
    rays = {
        "a": tuple(F(x) - F(c) for x, c in zip(start, center, strict=True)),
        "b": tuple(F(x) - F(c) for x, c in zip(end, center, strict=True)),
    }
    lines = {line.entity_id: line for line in plan.lines}
    radius = F(plan.radius)
    assert len(plan.radial_disk_roots) == 4
    assert len(plan.center_proxy_roots) == 2
    assert F(0) < fraction(plan.final_cell_radius) < F(350, 10**9)
    assert all(cell.radius == plan.final_cell_radius for cell in plan.final_source_cells)
    for line in plan.lines:
        d = tuple(map(F, line.direction))
        v = rays[line.point_id]
        a = dot(d, d)
        error = tuple(
            F(line.trim_parameter) * part - endpoint for part, endpoint in zip(d, v, strict=True)
        )
        assert fraction(line.squared_norm) == a
        assert fraction(line.affine_error_squared) == dot(error, error) <= F(1, 10**18)
        for interval, component in zip(line.root_vector, d, strict=True):
            assert_radical_enclosed(interval, 0, radius * component / a, a)
        # |r*d/sqrt(a)-v|^2 = r^2+v.v - 2r(d.v)sqrt(a)/a.
        constant, coefficient = radius * radius + dot(v, v), -2 * radius * dot(d, v) / a
        lo, hi = fraction(line.root_gap.lower), fraction(line.root_gap.upper)
        assert 0 <= lo <= hi <= F(1, 10**9)
        assert radical_sign(constant - lo * lo, coefficient, a) >= 0
        assert radical_sign(constant - hi * hi, coefficient, a) <= 0
    for roots in plan.radial_disk_roots:
        line = lines[roots.line_id]
        other = next(item for item in plan.lines if item.entity_id != line.entity_id)
        d, foreign_d = tuple(map(F, line.direction)), tuple(map(F, other.direction))
        v = rays[roots.point_id]
        n, k = fraction(roots.radius.numerator), fraction(roots.radius.denominator)
        a, b, c = dot(d, d) * k * k, -2 * dot(d, v) * k * k, dot(v, v) * k * k - n * n
        discriminant, denominator = b * b - 4 * a * c, 2 * a
        assert tuple(map(fraction, (roots.a, roots.b, roots.c))) == (a, b, c)
        assert fraction(roots.discriminant) == discriminant > 0
        assert fraction(roots.denominator) == denominator > 0
        assert roots.memberships == ("INTERIOR", "AFTER_END")
        for branch, interval, expected in zip(
            (-1, 1), roots.parameters, ((1, -1), (1, 1)), strict=True
        ):
            p, q = -b / denominator, F(branch) / denominator
            assert a * (p * p + q * q * discriminant) + b * p + c == 0
            assert (2 * a * p + b) * q == 0
            assert_radical_enclosed(interval, p, q, discriminant)
            assert (
                radical_sign(p, q, discriminant),
                radical_sign(p - F(line.trim_parameter), q, discriminant),
            ) == expected
        assert fraction(roots.parameters[0].upper) < fraction(roots.parameters[1].lower)
        error2 = fraction(line.affine_error_squared)
        assert fraction(roots.endpoint_inside_margin) == n * n - error2 * k * k > 0
        q = (radius * radius + dot(v, v)) * k * k - n * n
        j = 2 * radius * dot(d, v) * k * k
        assert q > 0 and j > 0
        assert fraction(roots.circle_root_inside_margin) == j * j - q * q * dot(d, d) > 0
        assert fraction(roots.negative_circle_root_exclusion) == q
        projection = max(F(0), dot(foreign_d, v))
        exclusion = c * dot(foreign_d, foreign_d) - projection * projection * k * k
        assert fraction(roots.foreign_ray_exclusion_margin) == exclusion > 0
    for roots in plan.center_proxy_roots:
        line = lines[roots.line_id]
        a, rho = fraction(roots.squared_norm), fraction(roots.radius)
        assert roots.memberships == ("BEFORE_START", "INTERIOR")
        assert roots.multiplicities == (1, 1)
        for branch, interval in zip((-1, 1), roots.parameters, strict=True):
            assert_radical_enclosed(interval, 0, F(branch), rho * rho / a)
        assert fraction(roots.parameters[0].upper) < 0 < fraction(roots.parameters[1].lower)
        assert fraction(roots.parameters[1].upper) < F(line.trim_parameter)
        n, k = fraction(roots.radius.numerator), fraction(roots.radius.denominator)
        assert (
            fraction(roots.finite_exit_margin)
            == F(line.trim_parameter) ** 2 * a * k * k - n * n
            > 0
        )
    assert plan.increasing_parameters == tuple(sorted(plan.parameters))
    assert (plan.parameters[1] > plan.parameters[0]) == (direction == "ccw")
    assert all(
        memberships.count("INTERIOR") == 1
        for _, _, memberships in plan.native_circle_exit_memberships
    )


def test_plan_bytes_bind_binary64_signed_zero_and_number_type(cardinal_plan):
    original = native.plan_bytes(cardinal_plan)
    changed_zero = replace(
        cardinal_plan, plane=replace(cardinal_plan.plane, origin=(-0.0, 0.0, 0.0))
    )
    changed_type = replace(cardinal_plan, plane=replace(cardinal_plan.plane, origin=(0, 0.0, 0.0)))
    assert len({original, native.plan_bytes(changed_zero), native.plan_bytes(changed_type)}) == 3
    assert b'"binary64":"-0x0.0p+0"' in native.plan_bytes(changed_zero)
    assert b'"integer":"0x0"' in native.plan_bytes(changed_type)
    assert native.plan_bytes(cardinal_plan) == original


def test_plan_source_binding_keeps_signed_zero_and_integer_float_distinctions():
    values = [source(center=(0.0, 0.0)), source(center=(-0.0, 0.0)), source(center=(0, 0.0))]
    plans = [native.prepare_native_geometry(value, native.NativePlane()) for value in values]
    assert len({plan.source.geometry_sha256 for plan in plans}) == 3
    assert len({plan.source.incidence.source_json for plan in plans}) == 3
    assert len({native.plan_bytes(plan) for plan in plans}) == 3
    assert len({plan.radius for plan in plans}) == 1


def test_plan_records_are_frozen_but_bytes_are_diagnostic_data_only(cardinal_plan):
    with pytest.raises(FrozenInstanceError):
        cardinal_plan.radius = 99
    changed = replace(cardinal_plan, radius=99.0)
    assert native.plan_bytes(changed) != native.plan_bytes(cardinal_plan)
    with pytest.raises(native.NativePlanError, match="^invalid_native_plan$"):
        native.plan_bytes({"radius": 5})


def test_plan_import_and_preparation_are_native_free_in_isolated_process():
    script = r"""
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'OCP', 'OCC', 'cadquery', 'slvs', 'bpy'} or fullname == 'mechanical_cad.kernel_ocp':
            raise AssertionError('blocked native import: ' + fullname)
sys.meta_path.insert(0, Block())
from mechanical_cad.arc_profile_native_plan import NativePlane, prepare_native_geometry
from mechanical_cad.arc_profile_sector_source import SectorPoint, SectorLine, SectorArc, SectorGeometrySource
source = SectorGeometrySource(
    (SectorPoint('c', 0, 0), SectorPoint('a', 5, 0), SectorPoint('b', 0, 5)),
    (SectorLine('ra', 'c', 'a'), SectorLine('rb', 'c', 'b')),
    (SectorArc('arc', 'c', 'a', 'b', 'ccw'),),
)
plan = prepare_native_geometry(source, NativePlane())
assert plan.resources.operations_end > plan.source.resources.operations_end
assert not any(name.split('.')[0] in {'OCP', 'OCC', 'cadquery', 'slvs', 'bpy'} for name in sys.modules)
assert 'mechanical_cad.kernel_ocp' not in sys.modules
print('PURE_NATIVE_PLAN_OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "PURE_NATIVE_PLAN_OK"


@pytest.mark.parametrize("component_type", [int, float])
def test_plane_rejects_numeric_subclasses(component_type):
    class Number(component_type):
        pass

    for plane in (
        native.NativePlane(origin=(Number(0), 0, 0)),
        native.NativePlane(quaternion=(Number(1), 0, 0, 0)),
    ):
        with pytest.raises(native.NativePlanError, match="^invalid_native_plane$"):
            native.prepare_native_geometry(source(), plane)


def test_plane_rejects_tuple_subclasses():
    class Tuple(tuple):
        pass

    for plane in (
        native.NativePlane(origin=Tuple((0, 0, 0))),
        native.NativePlane(quaternion=Tuple((1, 0, 0, 0))),
    ):
        with pytest.raises(native.NativePlanError, match="^invalid_native_plane$"):
            native.prepare_native_geometry(source(), plane)


def test_public_prepare_does_not_expand_an_insufficient_integer_budget():
    context = PrimitiveContext(max_bits=128)
    with pytest.raises(native.NativePlanError, match="^integer_limit$"):
        native.prepare_native_geometry(source(), native.NativePlane(), context=context)
    assert context.max_bits == 128
    assert 0 < context.operations < context.max_operations


def test_continuation_reuses_fresh_source_pi_instead_of_recomputing_it(monkeypatch):
    certificate, context = fresh_certificate()

    def forbidden(*args, **kwargs):
        raise AssertionError("continuation must reuse the freshly classified source")

    monkeypatch.setattr(native.IntervalContext, "pi", forbidden)
    monkeypatch.setattr(native, "classify_sector_geometry", forbidden)
    plan = native._continue_native_plan(certificate, native.NativePlane(), context)
    assert plan.source is certificate
    assert plan.native_angle is certificate.area.signed_angle
    assert plan.resources.operations_end == context.operations


def test_plan_budget_boundary_is_continuous_including_all_native_preparation(cardinal_plan):
    required = cardinal_plan.resources.operations_end
    exact_context = PrimitiveContext(max_operations=required)
    complete = native.prepare_native_geometry(source(), native.NativePlane(), context=exact_context)
    assert complete.resources.operations_end == exact_context.operations == required
    short_context = PrimitiveContext(max_operations=required - 1)
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        native.prepare_native_geometry(source(), native.NativePlane(), context=short_context)
    assert short_context.operations == required - 1


@pytest.mark.parametrize(
    "value,code",
    [
        (source(end=(3.0, 4.0)), "unsupported_profile_sweep"),
        (source(end=(0.0, 5.0 + 2e-9)), "unsupported_endpoint_discrepancy"),
        (source(start=(0.5, 0.0), end=(0.0, 0.5)), "unsupported_profile_scale"),
        (source(start=(1001.0, 0.0), end=(0.0, 1001.0)), "unsupported_profile_scale"),
    ],
)
def test_unsupported_geometry_never_reaches_private_continuation(monkeypatch, value, code):
    def forbidden(*args, **kwargs):
        raise AssertionError("uncertified geometry reached native preparation")

    monkeypatch.setattr(native, "_continue_native_plan", forbidden)
    with pytest.raises(native.NativePlanError, match=f"^{code}$"):
        native.prepare_native_geometry(value, native.NativePlane())


def test_native_entry_explicitly_expands_only_a_new_context():
    assert PrimitiveContext().max_operations == 100_000
    assert native.entry_context().max_operations == 200_000
    for limit in (1, 100_000, 100_001, 200_000):
        context = PrimitiveContext(max_operations=limit)
        context._tick()
        assert native.entry_context(context) is context
        assert context.max_operations == limit
        assert context.operations == 1


def test_source_completion_allows_exact_absolute_100k_boundary():
    certificate, _ = fresh_certificate()
    context = PrimitiveContext(max_operations=200_000)
    for _ in range(100_000 - certificate.resources.operations_end):
        context._tick()
    plan = native.prepare_native_geometry(source(), native.NativePlane(), context=context)
    assert plan.source.resources.operations_end == 100_000
    assert 100_000 < plan.resources.operations_end == context.operations <= 200_000


def test_source_completion_over_100k_rejects_before_native_frame(monkeypatch):
    certificate, _ = fresh_certificate()
    context = PrimitiveContext(max_operations=200_000)
    for _ in range(100_001 - certificate.resources.operations_end):
        context._tick()

    def forbidden(*args, **kwargs):
        raise AssertionError("source absolute work cap must reject before conversion")

    monkeypatch.setattr(native, "_frame", forbidden)
    with pytest.raises(native.NativePlanError, match="^source_operation_limit$"):
        native.prepare_native_geometry(source(), native.NativePlane(), context=context)
    assert context.operations == 100_001


def observed_directions(plan, *, normalize=False):
    """Synthetic observed fields only; this helper never constructs a native object."""
    records = []
    for line in plan.lines:
        local = line.direction
        if normalize:
            length = math.sqrt(local[0] * local[0] + local[1] * local[1])
            local = tuple(component / length for component in local)
        world = tuple(
            float(local[0] * u if u else local[1] * v if v else 0.0)
            for u, v in zip(plan.frame.u, plan.frame.v, strict=True)
        )
        records.append(native.NativeRadialDirection(line.entity_id, world))
    return tuple(records)


def fresh_plan(value=None, *, plane=None, context=None):
    context = native.entry_context() if context is None else context
    plan = native.prepare_native_geometry(
        source() if value is None else value,
        native.NativePlane() if plane is None else plane,
        context=context,
    )
    assert plan.accepted_support is None
    return plan, context


def assert_actual_root_oracle(plan):
    actual = plan.accepted_support
    arc = plan.source.incidence.arc
    rays = {
        arc.start_id: tuple(F(x) - F(c) for x, c in zip(arc.start, arc.center, strict=True)),
        arc.end_id: tuple(F(x) - F(c) for x, c in zip(arc.end, arc.center, strict=True)),
    }
    lines = {line.entity_id: line for line in actual.lines}
    for line in actual.lines:
        intended = next(item for item in plan.lines if item.entity_id == line.entity_id)
        assert line.length == intended.length
        assert line.trim_parameter == intended.trim_parameter == plan.radius
        d, v, ell = tuple(map(F, line.direction)), rays[line.point_id], F(line.trim_parameter)
        a = dot(d, d)
        error = tuple(ell * x - y for x, y in zip(d, v, strict=True))
        assert fraction(line.squared_norm) == a > 0
        assert dot(d, v) > 0
        assert fraction(line.affine_error_squared) == dot(error, error) <= F(1, 10**18)
        radius = F(plan.radius)
        for interval, component in zip(line.root_vector, d, strict=True):
            assert_radical_enclosed(interval, 0, radius * component / a, a)
        lo, hi = fraction(line.root_gap.lower), fraction(line.root_gap.upper)
        constant, coefficient = radius * radius + dot(v, v), -2 * radius * dot(d, v) / a
        assert 0 <= lo <= hi <= F(1, 10**9)
        assert radical_sign(constant - lo * lo, coefficient, a) >= 0
        assert radical_sign(constant - hi * hi, coefficient, a) <= 0
    for roots in actual.radial_disk_roots:
        line = lines[roots.line_id]
        d, v = tuple(map(F, line.direction)), rays[roots.point_id]
        n, k = fraction(roots.radius.numerator), fraction(roots.radius.denominator)
        a, b, c = dot(d, d) * k * k, -2 * dot(d, v) * k * k, dot(v, v) * k * k - n * n
        h, denominator = b * b - 4 * a * c, 2 * a
        assert tuple(map(fraction, (roots.a, roots.b, roots.c))) == (a, b, c)
        assert fraction(roots.discriminant) == h > 0
        assert fraction(roots.denominator) == denominator > 0
        for branch, interval, signs in zip(
            (-1, 1), roots.parameters, ((1, -1), (1, 1)), strict=True
        ):
            p, q = -b / denominator, F(branch) / denominator
            assert a * (p * p + q * q * h) + b * p + c == 0
            assert (2 * a * p + b) * q == 0
            assert_radical_enclosed(interval, p, q, h)
            assert (radical_sign(p, q, h), radical_sign(p - F(line.trim_parameter), q, h)) == signs
        assert roots.memberships == ("INTERIOR", "AFTER_END")
        radius = F(plan.radius)
        q = (radius * radius + dot(v, v)) * k * k - n * n
        j = 2 * radius * dot(d, v) * k * k
        assert q > 0 and j > 0
        assert fraction(roots.circle_root_inside_margin) == j * j - q * q * dot(d, d) > 0
        assert (
            fraction(roots.endpoint_inside_margin)
            == (n * n - fraction(line.affine_error_squared) * k * k)
            > 0
        )
        other = next(item for item in actual.lines if item.entity_id != roots.line_id)
        other_d = tuple(map(F, other.direction))
        projection = max(F(0), dot(other_d, v))
        assert (
            fraction(roots.foreign_ray_exclusion_margin)
            == (c * dot(other_d, other_d) - projection * projection * k * k)
            > 0
        )
        assert fraction(roots.negative_circle_root_exclusion) == q
    for roots in actual.center_proxy_roots:
        a, rho = fraction(roots.squared_norm), fraction(roots.radius)
        line = lines[roots.line_id]
        for branch, interval in zip((-1, 1), roots.parameters, strict=True):
            assert_radical_enclosed(interval, 0, F(branch), rho * rho / a)
        assert roots.memberships == ("BEFORE_START", "INTERIOR")
        assert roots.multiplicities == (1, 1)
        n, k = fraction(roots.radius.numerator), fraction(roots.radius.denominator)
        assert (
            fraction(roots.finite_exit_margin)
            == F(line.trim_parameter) ** 2 * a * k * k - n * n
            > 0
        )
    directions = [tuple(map(F, line.direction)) for line in actual.lines]
    assert fraction(actual.ray_dot) == dot(*directions) <= 0
    assert fraction(actual.ray_cross) == (
        directions[0][0] * directions[1][1] - directions[0][1] * directions[1][0]
    )
    source_count = sum(
        len(d.circle_exits) + len(d.radial_exits)
        for d in plan.source.cells + plan.source.outer_proxies + plan.final_source_cells
    ) + sum(len(roots) for _, roots in plan.source.center_proxy.line_exits)
    intended_count = sum(
        len(r.parameters) for r in plan.radial_disk_roots + plan.center_proxy_roots
    )
    actual_count = sum(
        len(r.parameters) for r in actual.radial_disk_roots + actual.center_proxy_roots
    )
    assert actual_count == 12
    support_count = sum(
        len(boundary.roots.support.roots) for boundary in plan.source.incidence.boundaries
    )
    native_circle_count = sum(
        len(line.support_circle_roots.parameters) for line in plan.lines + actual.lines
    )
    assert (
        actual.auxiliary_root_count
        == source_count + intended_count + actual_count + native_circle_count
    )
    assert actual.source_support_root_count == support_count == 4
    assert actual.retained_root_count == actual.auxiliary_root_count + support_count <= 64
    assert actual.retained_root_count == (64 if plan.source.cells else 56)


@pytest.mark.parametrize(
    "start,end",
    [
        ((5.0, 0.0), (0.0, 5.0)),
        ((3.0, 4.0), (-4.0, 3.0)),
        ((13.0, 29.0), (-29.0, 13.0)),
        ((5.0, 0.0), (-3.0, 4.0)),
        ((5.0, 0.0), (0.0, 5.0 + 0.5e-9)),
        ((5.0, 0.0), (0.0, 5.0 - 0.5e-9)),
    ],
    ids=["cardinal", "pythagorean", "rounded_hypot", "nonquadrantal", "outward_gap", "inward_gap"],
)
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("quaternion", [(1.0, 0.0, 0.0, 0.0), (0.5, 0.5, 0.5, 0.5)])
def test_synthetic_normalized_support_reproof_preserves_frozen_intent(
    start, end, direction, quaternion
):
    value = source(start=start, end=end, direction=direction)
    intended, context = fresh_plan(value, plane=native.NativePlane(quaternion=quaternion))
    before = native.plan_bytes(intended)
    observations = observed_directions(intended, normalize=True)
    prepared = native._continue_actual_support(intended, observations, context)
    actual = prepared.accepted_support
    assert actual is not None
    assert actual.directions is observations
    assert actual.intended_plan_sha256 == hashlib.sha256(before).hexdigest()
    assert actual.resources.operations_start == intended.resources.operations_end
    assert actual.resources.operations_end == context.operations > intended.resources.operations_end
    assert actual.resources.max_operations == 200_000
    assert prepared.resources == intended.resources
    assert native.plan_bytes(intended) == before
    assert actual.frozen_cell_radius is intended.final_cell_radius
    for field in (
        "source",
        "plane",
        "frame",
        "center",
        "vertices",
        "radius",
        "parameters",
        "increasing_parameters",
        "lines",
        "circle_vectors",
        "circle_gaps",
        "final_cell_radius",
        "final_source_cells",
        "radial_disk_roots",
        "center_proxy_roots",
        "source_comparison_area",
        "area_allowance",
        "source_area_midpoint",
        "local_scale_squared",
        "world_scale",
    ):
        assert getattr(prepared, field) is getattr(intended, field)
    assert actual.precision == intended.source.area.precision
    for error, line in zip(intended.intent_norm_errors, intended.lines, strict=True):
        norm_error = abs(sum(F(component) ** 2 for component in line.direction) - 1)
        assert fraction(error) == norm_error <= F(1, 2**51)
    assert all(fraction(margin) > 0 for margin in actual.line_collar_margins)
    assert_actual_root_oracle(prepared)


@pytest.mark.parametrize(
    "bad", [None, [], {}, True, (), (object(),), (object(), object(), object())]
)
def test_actual_direction_collection_grammar_is_strict(bad):
    plan, context = fresh_plan()
    with pytest.raises(native.NativePlanError, match="^invalid_native_direction_record$"):
        native._continue_actual_support(plan, bad, context)


@pytest.mark.parametrize(
    "bad_direction",
    [
        None,
        [],
        (1.0, 0.0),
        (1.0, 0.0, 0.0, 0.0),
        (1, 0.0, 0.0),
        (True, 0.0, 0.0),
        (F(1), 0.0, 0.0),
        (math.nan, 0.0, 0.0),
        (math.inf, 0.0, 0.0),
        (3.0, 0.0, 0.0),
        (1 << 100_000, 0.0, 0.0),
    ],
    ids=[
        "missing",
        "list",
        "short",
        "long",
        "int",
        "bool",
        "fraction",
        "nan",
        "infinite",
        "range",
        "huge_int",
    ],
)
def test_actual_direction_scalar_and_container_grammar(bad_direction):
    plan, context = fresh_plan()
    records = observed_directions(plan)
    bad = replace(records[0], direction=bad_direction)
    with pytest.raises(native.NativePlanError, match="^invalid_native_direction_record$"):
        native._continue_actual_support(plan, (bad, records[1]), context)


@pytest.mark.parametrize("missing", ["entity_id", "direction", "both"])
def test_actual_direction_missing_slots_reject(missing):
    plan, context = fresh_plan()
    records = observed_directions(plan)
    bad = object.__new__(native.NativeRadialDirection)
    if missing not in ("entity_id", "both"):
        object.__setattr__(bad, "entity_id", records[0].entity_id)
    if missing not in ("direction", "both"):
        object.__setattr__(bad, "direction", records[0].direction)
    with pytest.raises(native.NativePlanError, match="^invalid_native_direction_record$"):
        native._continue_actual_support(plan, (bad, records[1]), context)


@pytest.mark.parametrize("change", ["unknown", "swapped", "duplicate", "non_string"])
def test_actual_direction_ownership_cannot_be_forged(change):
    plan, context = fresh_plan()
    records = observed_directions(plan)
    if change == "swapped":
        records = records[::-1]
    else:
        owner = {"unknown": "unknown", "duplicate": records[1].entity_id, "non_string": True}[
            change
        ]
        records = (replace(records[0], entity_id=owner), records[1])
    with pytest.raises(native.NativePlanError, match="^native_direction_owner_changed$"):
        native._continue_actual_support(plan, records, context)


@pytest.mark.parametrize("axis", [1, 2])
@pytest.mark.parametrize("tiny", [math.ulp(0.0), -math.ulp(0.0)])
def test_actual_zero_components_must_remain_exactly_zero(axis, tiny):
    plan, context = fresh_plan()
    records = observed_directions(plan)
    direction = list(records[0].direction)
    direction[axis] = tiny
    records = (replace(records[0], direction=tuple(direction)), records[1])
    with pytest.raises(native.NativePlanError, match="^native_zero_direction_changed$"):
        native._continue_actual_support(plan, records, context)


@pytest.mark.parametrize("replacement", [0.0, -0.0, -(2**-55 / 5.0)])
def test_actual_small_nonzero_component_preserves_strict_sign_within_envelope(replacement):
    plan, context = fresh_plan(source(end=(-5.0, 2**-55)))
    records = observed_directions(plan)
    before = records[1].direction[1]
    assert 0 < before < 2**-50
    assert abs(F(replacement) - F(before)) <= F(1, 2**50)
    direction = (records[1].direction[0], replacement, records[1].direction[2])
    records = (records[0], replace(records[1], direction=direction))
    with pytest.raises(native.NativePlanError, match="^native_direction_sign_changed$"):
        native._continue_actual_support(plan, records, context)


@pytest.mark.parametrize("side", [-1, 1])
@pytest.mark.parametrize("location", ["inside", "boundary", "outside"])
def test_actual_direction_absolute_8u_envelope_boundary(side, location):
    plan, context = fresh_plan()
    records = observed_directions(plan)
    boundary = 1.0 + side * 2**-50
    changed = {
        "inside": math.nextafter(boundary, 1.0),
        "boundary": boundary,
        "outside": math.nextafter(boundary, math.copysign(math.inf, side)),
    }[location]
    difference = abs(F(changed) - 1)
    assert (difference <= F(1, 2**50)) == (location != "outside")
    records = (replace(records[0], direction=(changed, 0.0, 0.0)), records[1])
    if location == "outside":
        with pytest.raises(native.NativePlanError, match="^native_direction_envelope_exceeded$"):
            native._continue_actual_support(plan, records, context)
    else:
        accepted = native._continue_actual_support(plan, records, context)
        assert accepted.accepted_support.directions[0].direction[0] == changed
        assert_actual_root_oracle(accepted)


def test_actual_signed_zero_is_geometrically_preserved_and_binary_bound():
    ordinary, ordinary_context = fresh_plan()
    signed, signed_context = fresh_plan()
    ordinary_records = observed_directions(ordinary)
    signed_records = tuple(
        replace(
            record, direction=tuple(-0.0 if value == 0 else value for value in record.direction)
        )
        for record in observed_directions(signed)
    )
    first = native._continue_actual_support(ordinary, ordinary_records, ordinary_context)
    second = native._continue_actual_support(signed, signed_records, signed_context)
    assert first.accepted_support.lines == second.accepted_support.lines
    assert native.plan_bytes(first) != native.plan_bytes(second)
    assert b'"binary64":"-0x0.0p+0"' in native.plan_bytes(second)
    assert any(
        value == 0 and math.copysign(1, value) == -1
        for record in second.accepted_support.directions
        for value in record.direction
    )


@pytest.mark.parametrize("stale", ["consumed", "fresh_context", "accepted_plan"])
def test_actual_continuation_rejects_stale_or_already_accepted_plan(stale):
    plan, context = fresh_plan()
    records = observed_directions(plan)
    code = "native_context_discontinuity"
    if stale == "consumed":
        context._tick()
    elif stale == "fresh_context":
        context = native.entry_context()
    else:
        plan = native._continue_actual_support(plan, records, context)
        code = "invalid_native_plan"
    before = context.operations
    with pytest.raises(native.NativePlanError, match=f"^{code}$"):
        native._continue_actual_support(plan, records, context)
    assert context.operations == before


def test_actual_continuation_checks_context_limits_as_well_as_counter():
    plan, _ = fresh_plan()
    changed_context = PrimitiveContext(max_operations=199_999)
    for _ in range(plan.resources.operations_end):
        changed_context._tick()
    assert changed_context.operations == plan.resources.operations_end
    with pytest.raises(native.NativePlanError, match="^native_context_discontinuity$"):
        native._continue_actual_support(plan, observed_directions(plan), changed_context)
    assert changed_context.operations == plan.resources.operations_end


def test_public_representation_freshly_recomputes_and_rejects_plan_as_source(monkeypatch):
    intended, _ = fresh_plan()
    records = observed_directions(intended, normalize=True)
    real = native.classify_sector_geometry
    seen = []

    def observe(value, *, context):
        seen.append((value, context))
        return real(value, context=context)

    monkeypatch.setattr(native, "classify_sector_geometry", observe)
    value, context = source(), native.entry_context()
    accepted = native.prepare_native_representation(
        value, native.NativePlane(), records, context=context
    )
    assert seen == [(value, context)]
    assert accepted.source is not intended.source
    assert accepted.accepted_support.resources.operations_end == context.operations
    for forged in (intended, accepted, intended.source, accepted.accepted_support):
        with pytest.raises(SourceInputError, match="^invalid_source$"):
            native.prepare_native_representation(forged, native.NativePlane(), records)


def test_actual_support_preserves_smaller_context_cap_and_exhaustion():
    value = source(end=(-3.0, 4.0))
    intended, context = fresh_plan(value, context=PrimitiveContext())
    assert context.max_operations == 100_000
    with pytest.raises(PrimitiveError, match="^operation_limit$"):
        native._continue_actual_support(intended, observed_directions(intended), context)
    assert context.operations == 100_000
    larger, larger_context = fresh_plan(value)
    accepted = native._continue_actual_support(larger, observed_directions(larger), larger_context)
    assert 100_000 < accepted.accepted_support.resources.operations_end <= 200_000


@pytest.mark.parametrize("where", ["record", "direction_tuple", "component_float"])
def test_actual_direction_rejects_subclass_hooks(where):
    class Record(native.NativeRadialDirection):
        pass

    class Tuple(tuple):
        pass

    class Float(float):
        pass

    plan, context = fresh_plan()
    first, second = observed_directions(plan)
    if where == "record":
        first = Record(first.entity_id, first.direction)
    elif where == "direction_tuple":
        first = replace(first, direction=Tuple(first.direction))
    else:
        first = replace(first, direction=(Float(1), 0.0, 0.0))
    with pytest.raises(native.NativePlanError, match="^invalid_native_direction_record$"):
        native._continue_actual_support(plan, (first, second), context)


@pytest.mark.parametrize("at_boundary", [True, False])
def test_intended_norm_precondition_4u_boundary_is_exact(monkeypatch, at_boundary):
    # Replace one internal arithmetic record solely to isolate the norm gate.
    # The boundary path stops before any such forged record can produce a plan.
    original = native._line
    squared_norm = Dyadic((1 << 51) + 1, -51) if at_boundary else Dyadic((1 << 50) + 1, -50)

    def altered(*args, **kwargs):
        return replace(original(*args, **kwargs), squared_norm=squared_norm)

    def stop_after_norm(*args, **kwargs):
        raise RuntimeError("passed_exact_norm_boundary")

    monkeypatch.setattr(native, "_line", altered)
    monkeypatch.setattr(native, "_outer_disk", stop_after_norm)
    if at_boundary:
        assert fraction(squared_norm) - 1 == F(1, 2**51)
        with pytest.raises(RuntimeError, match="^passed_exact_norm_boundary$"):
            native.prepare_native_geometry(source(), native.NativePlane())
    else:
        assert fraction(squared_norm) - 1 > F(1, 2**51)
        with pytest.raises(native.NativePlanError, match="^native_normalization_precondition$"):
            native.prepare_native_geometry(source(), native.NativePlane())


def test_actual_direction_within_8u_can_still_fail_fresh_geometry_gate():
    plan, context = fresh_plan(source(start=(3.0, 4.0), end=(-4.0, 3.0)))
    first, second = observed_directions(plan)
    changed = math.nextafter(first.direction[0], -math.inf)
    assert abs(F(changed) - F(first.direction[0])) < F(1, 2**50)
    first = replace(first, direction=(changed, first.direction[1], first.direction[2]))
    before = native.plan_bytes(plan)
    with pytest.raises(native.NativePlanError, match="^native_ray_pair_unsupported$"):
        native._continue_actual_support(plan, (first, second), context)
    assert native.plan_bytes(plan) == before
    assert plan.accepted_support is None


def test_actual_continuation_revalidates_source_pi_precision():
    plan, context = fresh_plan()
    pi = replace(plan.source.area.pi, precision=128)
    forged_source = replace(plan.source, area=replace(plan.source.area, pi=pi))
    altered = replace(plan, source=forged_source)
    with pytest.raises(PrimitiveError, match="^precision_mismatch$"):
        native._continue_actual_support(altered, observed_directions(plan), context)


def test_actual_representation_rejects_unsupported_source_before_observation(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unsupported source reached observed-support proof")

    monkeypatch.setattr(native, "_continue_actual_support", forbidden)
    with pytest.raises(native.NativePlanError, match="^unsupported_profile_sweep$"):
        native.prepare_native_representation(source(end=(3.0, 4.0)), native.NativePlane(), ())
