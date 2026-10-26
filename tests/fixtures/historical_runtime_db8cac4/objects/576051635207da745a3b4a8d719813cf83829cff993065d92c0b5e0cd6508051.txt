"""Independent source grammar and qualified-incidence cross-checks.

Only tests convert this leaf's geometry to a real Sketch. Production source
preflight has no Sketch, incidence, solver, service or native dependency.
"""

from __future__ import annotations

import ast
import json
import math
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import mechanical_cad.arc_profile_incidence as qualified
import mechanical_cad.arc_profile_sector_source as source_module
from mechanical_cad.arc_geometry import ArcGeometryError
from mechanical_cad.arc_profile_primitives import (
    ArcSupportRoot,
    ArcSupportRoots,
    Dyadic,
    PrimitiveContext,
    PrimitiveError,
    UnresolvedArcSupportRoots,
    UnresolvedSupportRoots,
)
from mechanical_cad.arc_profile_sector_source import (
    SectorArc,
    SectorCircle,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
    SourceInputError,
    geometry_json,
    geometry_preflight,
)
from mechanical_cad.sketch_model import Arc, Circle, Line, Point, Sketch

ROOT = Path(__file__).resolve().parents[2]


def source(*, center=(0, 0), start=(5, 0), end=(0, 5), direction="ccw"):
    return SectorGeometrySource(
        (SectorPoint("center", *center), SectorPoint("start", *start), SectorPoint("end", *end)),
        (SectorLine("radius_start", "center", "start"), SectorLine("radius_end", "center", "end")),
        (SectorArc("arc", "center", "start", "end", direction),),
    )


def real_sketch(value):
    return Sketch(
        "test_geometry",
        tuple(Point(point.id, point.u, point.v) for point in value.points),
        tuple(Line(line.id, line.start, line.end) for line in value.lines),
        (),
        schema_version=3,
        circles=tuple(Circle(circle.id, circle.center, circle.radius) for circle in value.circles),
        arcs=tuple(
            Arc(arc.id, arc.center, arc.start, arc.end, arc.direction) for arc in value.arcs
        ),
    )


def assert_matches_qualified(value, *, max_bits=65_536, max_operations=100_000):
    actual = geometry_preflight(
        value, PrimitiveContext(max_bits=max_bits, max_operations=max_operations)
    )
    reference = qualified.incidence_preflight(
        real_sketch(value),
        1,
        context=PrimitiveContext(max_bits=max_bits, max_operations=max_operations),
    )
    assert {field.name for field in fields(actual)} == {field.name for field in fields(reference)}
    # Independently owned container classes and source bindings deliberately differ.
    # Counters are implementation details; every recomputed geometric field agrees.
    excluded = {"source_json", "operations_start", "operations_end"}
    assert {key: item for key, item in asdict(actual).items() if key not in excluded} == {
        key: item for key, item in asdict(reference).items() if key not in excluded
    }
    assert actual.source_json == geometry_json(value)
    assert type(actual) is not type(reference)
    assert type(actual.height) is int and actual.height == 1
    return actual


@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("end", [(0, 5), (-5, 0), (0, -5), (-3, 4)])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("permute", [False, True])
def test_all_recomputed_fields_match_qualified_exact_sectors(direction, end, reverse, permute):
    value = source(end=end, direction=direction)
    if reverse:
        value = replace(
            value,
            lines=tuple(replace(line, start=line.end, end=line.start) for line in value.lines),
        )
    if permute:
        value = replace(value, points=value.points[::-1], lines=value.lines[::-1])
    before = geometry_json(value)
    report = assert_matches_qualified(value)
    assert report.status == "exact_endpoint_incidence"
    assert geometry_json(value) == before
    for boundary in report.boundaries:
        line = next(item for item in value.lines if item.id == boundary.line_id)
        assert (boundary.stored_start_id, boundary.stored_end_id) == (line.start, line.end)
        assert boundary.support_start_id == "center"
        assert tuple(root.support.branch for root in boundary.roots.roots) == ("MINUS", "PLUS")
        assert all(root.support.multiplicity == 1 for root in boundary.roots.roots)
        assert all(
            root.support is original
            for root, original in zip(
                boundary.roots.roots, boundary.roots.support.roots, strict=True
            )
        )


@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize(
    "end,expected",
    [
        ((0, math.nextafter(5.0, math.inf)), "requires_incidence_cells"),
        ((0, 5 + 0.5e-9), "requires_incidence_cells"),
        ((0, 5 + 2e-9), "unsupported_endpoint_discrepancy"),
        ((0, 5 - 2e-9), "unsupported_endpoint_discrepancy"),
        ((math.ulp(0.0), 5), "unsupported_profile_sweep"),
        ((-math.ulp(0.0), 5), "requires_incidence_cells"),
        ((3, 4), "unsupported_profile_sweep"),
    ],
)
def test_nonexact_and_unsupported_fields_match_qualified(direction, end, expected):
    report = assert_matches_qualified(source(end=end, direction=direction))
    assert report.code == expected


@pytest.mark.parametrize(
    "radius", [math.nextafter(1.0, 0.0), 1, 1000, math.nextafter(1000.0, math.inf)]
)
def test_inclusive_canonical_radius_domain(radius):
    report = assert_matches_qualified(source(start=(radius, 0), end=(0, radius)))
    assert report.status == ("exact_endpoint_incidence" if 1 <= radius <= 1000 else "unsupported")


def test_translated_geometry_exact_gap_matches_independent_fraction_reference():
    value = source(center=(999_000, -999_000), start=(999_013, -998_971), end=(998_971, -998_987))
    report = assert_matches_qualified(value)
    assert report.status == "requires_incidence_cells"
    radius = Fraction(report.core_arcs[0][1].start_radius)
    points = {point.id: point for point in value.points}
    center = points["center"]
    for gap in report.gaps:
        point = points[gap.point_id]
        norm = (Fraction(point.u) - Fraction(center.u)) ** 2 + (
            Fraction(point.v) - Fraction(center.v)
        ) ** 2
        exact = Fraction(gap.squared_norm.mantissa) * Fraction(2) ** gap.squared_norm.exponent
        delta = Fraction(1, 10**9)
        assert exact == norm
        assert gap.exact_zero == (norm == radius * radius)
        assert gap.within_bound == ((radius - delta) ** 2 <= norm <= (radius + delta) ** 2)


@pytest.mark.parametrize("offset", [-2e-9, -1e-9, -0.5e-9, 0, 0.5e-9, 1e-9, 2e-9])
def test_gap_boundary_uses_exact_squared_comparison(offset):
    value = source(end=(0, 5 + offset))
    report = geometry_preflight(value)
    gap = report.gaps[1]
    n = 10**9
    s = Fraction(5 + offset) ** 2
    assert gap.within_bound == ((n * 5 - 1) ** 2 <= n * n * s <= (n * 5 + 1) ** 2)
    assert gap.exact_zero == (s == 25)
    assert report.ledgers_complete and len(report.boundaries) == 2


def test_geometry_json_is_sorted_type_preserving_and_keeps_unused_points():
    value = replace(source(), points=(*source().points, SectorPoint("unused", -0.0, 1.0)))
    encoded = geometry_json(value)
    permuted = replace(value, points=value.points[::-1], lines=value.lines[::-1])
    assert geometry_json(permuted) == encoded
    payload = json.loads(encoded)
    assert set(payload) == {"version", "points", "lines", "arcs", "circles"}
    assert [point["id"] for point in payload["points"]] == ["center", "end", "start", "unused"]
    assert type(payload["points"][2]["u"]) is int
    unused = payload["points"][3]
    assert type(unused["u"]) is float and math.copysign(1, unused["u"]) == -1
    assert type(unused["v"]) is float
    integer_change = replace(value, points=(*value.points[:-1], SectorPoint("unused", 0, 1)))
    assert geometry_json(integer_change) != encoded
    assert geometry_preflight(value).source_json == encoded
    assert geometry_preflight(value).status == "exact_endpoint_incidence"


def test_json_preserves_all_circle_numeric_data_even_for_unsupported_form():
    value = replace(
        source(),
        circles=(SectorCircle("z_circle", "center", 5.0), SectorCircle("a_circle", "start", 1)),
    )
    payload = json.loads(geometry_json(value))
    assert [circle["id"] for circle in payload["circles"]] == ["a_circle", "z_circle"]
    assert type(payload["circles"][0]["radius"]) is int
    assert type(payload["circles"][1]["radius"]) is float
    assert_matches_qualified(value)


@pytest.mark.parametrize("bad", [None, {}, True, (), object()])
def test_exact_source_type_required(bad):
    for call in (geometry_json, geometry_preflight):
        with pytest.raises(SourceInputError, match="invalid_source"):
            call(bad)


@pytest.mark.parametrize("version", [True, False, 1.0, 0, 2, "1", None])
def test_own_version_one_only(version):
    with pytest.raises(SourceInputError, match="unsupported_version"):
        geometry_preflight(replace(source(), version=version))


@pytest.mark.parametrize("field", ["points", "lines", "arcs", "circles"])
def test_only_exact_tuples_and_exact_record_types(field):
    value = source()
    for bad in ([], list(getattr(value, field)), {}, None, (object(),)):
        with pytest.raises(SourceInputError):
            geometry_preflight(replace(value, **{field: bad}))

    class TupleSubclass(tuple):
        pass

    with pytest.raises(SourceInputError, match="invalid_records"):
        geometry_json(replace(value, **{field: TupleSubclass(getattr(value, field))}))


def test_source_record_and_primitive_subclasses_reject():
    class SourceSubclass(SectorGeometrySource):
        pass

    class PointSubclass(SectorPoint):
        pass

    class LineSubclass(SectorLine):
        pass

    class ArcSubclass(SectorArc):
        pass

    class CircleSubclass(SectorCircle):
        pass

    class IntSubclass(int):
        pass

    class FloatSubclass(float):
        pass

    class StringSubclass(str):
        pass

    value = source()
    invalid = [
        SourceSubclass(value.points, value.lines, value.arcs),
        replace(value, points=(PointSubclass("center", 0, 0), *value.points[1:])),
        replace(value, lines=(LineSubclass("radius_start", "center", "start"), value.lines[1])),
        replace(value, arcs=(ArcSubclass("arc", "center", "start", "end", "cw"),)),
        replace(value, circles=(CircleSubclass("circle", "center", 5),)),
        replace(value, version=IntSubclass(1)),
        replace(value, points=(SectorPoint("center", IntSubclass(0), 0), *value.points[1:])),
        replace(value, points=(SectorPoint("center", FloatSubclass(0), 0), *value.points[1:])),
        replace(value, arcs=(replace(value.arcs[0], direction=StringSubclass("ccw")),)),
        replace(
            value, lines=(replace(value.lines[0], start=StringSubclass("center")), value.lines[1])
        ),
        replace(
            value, points=(replace(value.points[0], id=StringSubclass("center")), *value.points[1:])
        ),
    ]
    for item in invalid:
        with pytest.raises(SourceInputError):
            geometry_preflight(item)


@pytest.mark.parametrize(
    "bad", [True, False, "0", None, math.nan, math.inf, -math.inf, 1_000_001, -1_000_001, 10**1000]
)
def test_strict_finite_coordinate_domain(bad):
    value = source()
    for field in ("u", "v"):
        malformed = replace(
            value, points=(replace(value.points[0], **{field: bad}), *value.points[1:])
        )
        with pytest.raises(SourceInputError, match="invalid_number"):
            geometry_json(malformed)


@pytest.mark.parametrize("value", [-1_000_000, 1_000_000, -1_000_000.0, 1_000_000.0, math.ulp(0.0)])
def test_coordinate_endpoints_and_subnormal_are_retained(value):
    item = replace(source(), points=(*source().points, SectorPoint("unused", value, value)))
    assert json.loads(geometry_json(item))["points"][-1]["u"] == value


@pytest.mark.parametrize(
    "radius",
    [
        True,
        "5",
        0,
        -1,
        math.nextafter(1e-6, 0),
        math.nextafter(1e6, math.inf),
        math.nan,
        math.inf,
        10**1000,
    ],
)
def test_circle_radius_domain(radius):
    with pytest.raises(SourceInputError, match="invalid_number"):
        geometry_json(replace(source(), circles=(SectorCircle("circle", "center", radius),)))


@pytest.mark.parametrize("radius", [1e-6, 1e6])
def test_circle_radius_inclusive_endpoints(radius):
    assert (
        geometry_preflight(
            replace(source(), circles=(SectorCircle("circle", "center", radius),))
        ).code
        == "unsupported_profile_form"
    )


@pytest.mark.parametrize(
    "identity", ["", ".start", "-start", "has space", "a\n", "é", "a" * 129, 1, True]
)
def test_strict_ascii_identifier_grammar(identity):
    with pytest.raises(SourceInputError, match="invalid_id"):
        geometry_json(replace(source(), points=(*source().points, SectorPoint(identity, 0, 0))))


@pytest.mark.parametrize("identity", ["0", "_", "A.a-z_0", "a" * 128])
def test_identifier_grammar_boundaries(identity):
    assert geometry_json(replace(source(), points=(*source().points, SectorPoint(identity, 0, 0))))


@pytest.mark.parametrize(
    "change",
    [
        {"lines": (SectorLine("start", "center", "start"),)},
        {"arcs": (SectorArc("center", "center", "start", "end", "ccw"),)},
        {"circles": (SectorCircle("arc", "center", 5),)},
        {"points": (*source().points, SectorPoint("center", 99, 99))},
    ],
)
def test_all_point_curve_ids_globally_unique(change):
    with pytest.raises(SourceInputError, match="duplicate_id"):
        geometry_preflight(replace(source(), **change))


@pytest.mark.parametrize(
    "change",
    [
        {"lines": (SectorLine("line", "missing", "start"),)},
        {"lines": (SectorLine("line", "start", "start"),)},
        {"arcs": (SectorArc("arc", "center", "start", "missing", "ccw"),)},
        {"arcs": (SectorArc("arc", "center", "start", "center", "ccw"),)},
        {"circles": (SectorCircle("circle", "missing", 5),)},
    ],
)
def test_references_exist_and_roles_are_distinct(change):
    with pytest.raises(SourceInputError, match="missing_reference"):
        geometry_preflight(replace(source(), **change))


@pytest.mark.parametrize("direction", ["CCW", "CW", "", 1, None])
def test_direction_exact_lowercase_only(direction):
    value = source()
    with pytest.raises(SourceInputError, match="invalid_direction"):
        geometry_preflight(replace(value, arcs=(replace(value.arcs[0], direction=direction),)))


def test_counts_checked_before_contents_and_exact_resource_boundaries():
    value = source()
    points = (*value.points, *(SectorPoint(f"unused_{i}", i, i) for i in range(253)))
    curves = tuple(SectorLine(f"line_{i}", "center", "start") for i in range(256))
    at_limit = replace(value, points=points, lines=curves, arcs=())
    assert len(json.loads(geometry_json(at_limit))["points"]) == 256
    for bad in (
        replace(at_limit, points=(*points, object())),
        replace(at_limit, lines=(*curves, object())),
        replace(at_limit, arcs=value.arcs),
        replace(value, points=points, circles=(SectorCircle("circle", "center", 5),)),
    ):
        with pytest.raises(SourceInputError, match="resource_limit"):
            geometry_json(bad)
    active_limit = replace(
        value,
        points=points[:-1],
        circles=(SectorCircle("c1", "center", 5), SectorCircle("c2", "center", 5)),
    )
    assert geometry_json(active_limit)


def test_incomplete_forged_records_fail_with_source_error():
    for bad in (
        object.__new__(SectorGeometrySource),
        replace(source(), points=(object.__new__(SectorPoint),)),
        replace(source(), lines=(object.__new__(SectorLine),)),
    ):
        with pytest.raises(SourceInputError, match="invalid_source"):
            geometry_json(bad)


@pytest.mark.parametrize(
    "key", ["coincidence_pairs", "constraints", "plane", "schema_version", "height", "report"]
)
def test_no_alias_constraint_plane_or_evidence_proxy(key):
    with pytest.raises(TypeError):
        SectorGeometrySource(source().points, source().lines, source().arcs, **{key: ()})


def test_equal_coordinate_alias_is_not_repaired_or_diagnosed_as_connectivity():
    value = replace(
        source(),
        points=(*source().points, SectorPoint("alias", 5, 0)),
        lines=(SectorLine("radius_start", "center", "alias"), source().lines[1]),
    )
    report = geometry_preflight(value, PrimitiveContext(max_operations=1))
    assert report.status == "unsupported" and report.code == "unsupported_profile_form"
    assert report.stage == "GRAPH" and report.operations_end == 0
    assert report.intended_ledger_count == 0 and not report.boundaries
    assert '"alias"' in report.source_json


@pytest.mark.parametrize(
    "lines",
    [
        (),
        (SectorLine("chord", "start", "end"),),
        (SectorLine("a", "center", "start"), SectorLine("b", "center", "start")),
        (*source().lines, SectorLine("extra", "start", "end")),
    ],
)
def test_chord_extra_and_wrong_graphs_stop_before_arithmetic(lines):
    report = geometry_preflight(replace(source(), lines=lines), PrimitiveContext(max_operations=1))
    assert report.code == "unsupported_profile_form" and report.stage == "GRAPH"
    assert report.operations_end == 0 and not report.boundaries


def test_core_arc_equal_radius_gate_precedes_context_and_graph_gate():
    value = source(end=(0, 6))
    value = replace(
        value, lines=(), arcs=(replace(value.arcs[0], id="z"), replace(value.arcs[0], id="a"))
    )
    with pytest.raises(ArcGeometryError) as failure:
        geometry_preflight(value, False)
    assert failure.value.code == "unequal_arc_radii"


def test_all_arcs_checked_in_stable_id_order_before_unsupported_form(monkeypatch):
    value = source()
    value = replace(
        value,
        points=(*value.points, SectorPoint("other", -5, 0)),
        arcs=(replace(value.arcs[0], id="z"), replace(value.arcs[0], id="a", end="other")),
    )
    original = source_module.arc_geometry
    calls = []

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(source_module, "arc_geometry", record)
    report = geometry_preflight(value)
    assert [identity for identity, _ in report.core_arcs] == ["a", "z"]
    assert [args[2] for args, _ in calls] == [(-5, 0), (0, 5)]
    assert [kwargs for _, kwargs in calls] == [{"require_equal_radii": True}] * 2
    assert report.code == "unsupported_profile_form"


@pytest.mark.parametrize("context", [False, 1, {}, object()])
def test_invalid_context_rejects(context):
    with pytest.raises(SourceInputError, match="invalid_context"):
        geometry_preflight(source(), context)


def test_derived_context_cannot_supply_fake_arithmetic():
    class Derived(PrimitiveContext):
        pass

    with pytest.raises(SourceInputError, match="invalid_context"):
        geometry_preflight(source(), Derived())


@pytest.mark.parametrize("max_operations", [1, 10, 100, 500, 1000])
def test_partial_resource_fields_match_qualified(max_operations):
    assert_matches_qualified(source(), max_operations=max_operations)


@pytest.mark.parametrize("max_bits", [1, 16, 64, 128, 512])
def test_integer_limits_match_qualified_without_hiding_partial_records(max_bits):
    report = assert_matches_qualified(source(end=(-math.ulp(0.0), 5)), max_bits=max_bits)
    assert report.code == "integer_limit" and report.status == "numerical_ambiguity"


def test_context_is_reused_without_reset_or_limit_increase():
    cost = geometry_preflight(source()).operations_end
    context = PrimitiveContext(max_operations=cost * 2 - 1)
    first = geometry_preflight(source(), context)
    second = geometry_preflight(source(), context)
    assert first.status == "exact_endpoint_incidence"
    assert second.operations_start == first.operations_end
    assert second.code == "operation_limit"
    assert second.operations_end == context.operations == context.max_operations


def test_failed_second_support_keeps_exact_first_ledger(monkeypatch):
    original = PrimitiveContext.line_arc_roots
    returned = []
    contexts = []

    def fail_second(context, *args, **kwargs):
        contexts.append(context)
        if returned:
            raise PrimitiveError("operation_limit")
        ledger = original(context, *args, **kwargs)
        returned.append(ledger)
        return ledger

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", fail_second)
    context = PrimitiveContext()
    report = geometry_preflight(source(), context)
    assert contexts == [context, context]
    assert report.code == "operation_limit" and report.stage == "SUPPORT"
    assert report.intended_ledger_count == 2 and not report.ledgers_complete
    assert len(report.boundaries) == 1 and report.boundaries[0].roots is returned[0]


def test_failure_after_supports_keeps_complete_ledgers(monkeypatch):
    def fail(*args):
        raise PrimitiveError("integer_limit")

    monkeypatch.setattr(source_module, "_gap", fail)
    report = geometry_preflight(source())
    assert report.stage == "DISCREPANCY" and report.code == "integer_limit"
    assert report.ledgers_complete and len(report.boundaries) == 2 and not report.gaps


def test_unresolved_ledgers_retained_in_full(monkeypatch):
    original = PrimitiveContext.line_arc_roots
    returned = []

    def unresolved(context, *args, **kwargs):
        ledger = original(context, *args, **kwargs)
        base = ledger.support
        ledger = UnresolvedArcSupportRoots(
            UnresolvedSupportRoots(base.a, base.b, base.c, base.discriminant, base.roots),
            ledger.roots,
        )
        returned.append(ledger)
        return ledger

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", unresolved)
    report = geometry_preflight(source())
    assert report.status == "numerical_ambiguity" and report.code == "unresolved_isolation"
    assert report.ledgers_complete
    assert all(
        boundary.roots is original
        for boundary, original in zip(report.boundaries, returned, strict=True)
    )


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "double",
        "incomplete",
        "duplicate",
        "membership",
        "line_position",
        "foreign_member",
    ],
)
def test_no_filtered_or_repaired_root_can_pass_defensive_gate(monkeypatch, kind):
    original = PrimitiveContext.line_arc_roots
    returned = []

    def change(context, *args, **kwargs):
        ledger = original(context, *args, **kwargs)
        roots, members = ledger.support.roots, ledger.roots
        if kind == "missing":
            roots, members = (), ()
        elif kind == "double":
            root = replace(roots[0], branch="DOUBLE", multiplicity=2)
            roots, members = (root,), (ArcSupportRoot(root, "OUTSIDE"),)
        elif kind == "incomplete":
            members = members[:1]
        elif kind == "duplicate":
            roots, members = (roots[0], roots[0]), (members[0], members[0])
        elif kind == "membership":
            members = tuple(replace(root, arc_position="OUTSIDE") for root in members)
        elif kind == "line_position":
            roots = tuple(replace(root, position="INTERIOR") for root in roots)
            members = tuple(
                replace(member, support=root) for member, root in zip(members, roots, strict=True)
            )
        else:
            members = tuple(replace(member, support=replace(member.support)) for member in members)
        changed = ArcSupportRoots(replace(ledger.support, roots=roots), members)
        returned.append(changed)
        return changed

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", change)
    report = geometry_preflight(source())
    assert report.status == "unsupported" and report.stage == "ROOTS"
    assert report.code == (
        "unsupported_endpoint_incidence"
        if kind in ("membership", "line_position")
        else "unsupported_profile_contact"
    )
    assert len(report.boundaries) == 2 and report.ledgers_complete
    assert all(
        boundary.roots is item for boundary, item in zip(report.boundaries, returned, strict=True)
    )


def test_nonresource_primitive_failure_is_not_disguised(monkeypatch):
    def invalid(*args, **kwargs):
        raise PrimitiveError("invalid_point")

    monkeypatch.setattr(PrimitiveContext, "line_arc_roots", invalid)
    with pytest.raises(PrimitiveError, match="invalid_point"):
        geometry_preflight(source())


def test_records_frozen_slotted_and_do_not_advertise_admission():
    value = source()
    report = geometry_preflight(value)
    for item in (
        value,
        *value.points,
        *value.lines,
        *value.arcs,
        SectorCircle("circle", "center", 5),
        report,
        report.arc,
        *report.gaps,
        *report.boundaries,
        *report.nominal_joins,
    ):
        assert not hasattr(item, "__dict__")
        with pytest.raises((FrozenInstanceError, AttributeError)):
            setattr(item, fields(item)[0].name, "changed")
    assert not any(
        hasattr(report, name)
        for name in ("valid", "accepted", "solved", "closed", "profile", "capability")
    )
    assert isinstance(report.ray_dot, Dyadic)


def test_native_and_runtime_import_traps_under_no_site_packages():
    script = """
import sys
class BlockRuntime:
    def find_spec(self, fullname, *args):
        allowed = {'mechanical_cad', 'mechanical_cad.arc_geometry',
                   'mechanical_cad.arc_profile_primitives',
                   'mechanical_cad.arc_profile_sector_source'}
        if fullname.split('.')[0] in {'OCP', 'slvs', 'bpy'} or (
            fullname.startswith('mechanical_cad.') and fullname not in allowed):
            raise AssertionError(fullname)
sys.meta_path.insert(0, BlockRuntime())
from mechanical_cad.arc_profile_sector_source import (
    SectorPoint, SectorLine, SectorArc, SectorGeometrySource,
    geometry_json, geometry_preflight)
s = SectorGeometrySource(
    (SectorPoint('c',0,0),SectorPoint('a',5,0),SectorPoint('b',0,5)),
    (SectorLine('la','a','c'),SectorLine('lb','c','b')),
    (SectorArc('arc','c','a','b','cw'),))
r = geometry_preflight(s)
assert r.status == 'exact_endpoint_incidence'
assert r.source_json == geometry_json(s)
assert r.height == 1 and len(r.boundaries) == 2
print('SECTOR_SOURCE_NATIVE_FREE_OK')
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.stdout.strip() == "SECTOR_SOURCE_NATIVE_FREE_OK" and not result.stderr


def test_dependency_closure_and_checked_math_only():
    tree = ast.parse((ROOT / "src/mechanical_cad/arc_profile_sector_source.py").read_text())
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert {node.module for node in imports if isinstance(node, ast.ImportFrom)} == {
        "__future__",
        "dataclasses",
        "arc_geometry",
        "arc_profile_primitives",
    }
    assert {
        alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names
    } == {"json", "math", "re"}
    assert not any(
        isinstance(node, ast.BinOp)
        and isinstance(node.op, (ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.LShift, ast.RShift))
        for node in ast.walk(tree)
    )
