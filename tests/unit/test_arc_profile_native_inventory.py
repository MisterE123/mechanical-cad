"""Owner-aware stored-pcurve inventory, without importing a native binding.

Collector functions are extracted verbatim from the additive kernel source. Only
its local TopExp import is removed, so the names resolve to explicit binding
doubles. The mathematical plan and detached validators are genuine pure leaves.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.abc
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from historical_runtime_source import historical_runtime_root

import mechanical_cad.arc_profile_native_evidence as evidence
from mechanical_cad.arc_profile_native_plan import (
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

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / "src/mechanical_cad/kernel_ocp.py"
IDENTITY = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))


class NoNativeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"OCP", "OCC", "cadquery", "slvs", "bpy"}:
            raise AssertionError(f"native import forbidden: {fullname}")
        if fullname == "mechanical_cad.kernel_ocp":
            raise AssertionError("the real native kernel must be parsed, never imported")
        return None


@pytest.fixture(autouse=True)
def no_native_imports():
    blocker = NoNativeImports()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


class Coord:
    def __init__(self, values):
        self.values = tuple(values)

    def Coord(self):
        return self.values

    def Distance(self, other):
        return math.dist(self.values, other.values)


class Location:
    def __init__(self, matrix=IDENTITY, *, identity=None):
        self.matrix = matrix
        self.identity = matrix == IDENTITY if identity is None else identity

    def IsIdentity(self):
        return self.identity

    def Transformation(self):
        return self

    def Value(self, row, column):
        return self.matrix[row - 1][column - 1]


class Axes:
    def __init__(self, dimensions=3):
        self.dimensions = dimensions

    def XDirection(self):
        return Coord((1.0, 0.0, 0.0)[: self.dimensions])

    def YDirection(self):
        return Coord((0.0, 1.0, 0.0)[: self.dimensions])

    def Direction(self):
        return Coord((0.0, 0.0, 1.0))

    def Location(self):
        return Coord((0.0, 0.0, 0.0)[: self.dimensions])


class Surface:
    """Distinct handles deliberately compare geometrically equal."""

    def __init__(self, kind="Geom_Plane", *, label="retained"):
        self.kind, self.label = kind, label

    def __eq__(self, other):
        return type(other) is Surface and self.kind == other.kind

    def DynamicType(self):
        return SimpleNamespace(Name=lambda: self.kind)

    def Pln(self):
        return self

    def Cylinder(self):
        return self

    def Position(self):
        return Axes()

    def Location(self):
        return Coord((0.0, 0.0, 0.0))

    def Axis(self):
        return SimpleNamespace(Direction=lambda: Coord((0.0, 0.0, 1.0)))

    def Radius(self):
        return 5.0


class Curve:
    def __init__(self, dimensions, *, kind="line", location=None, direction=None, radius=5.0):
        self.dimensions, self.kind = dimensions, kind
        self.location = (0.0,) * dimensions if location is None else location
        self.direction = (1.0, *([0.0] * (dimensions - 1))) if direction is None else direction
        self.radius = radius

    def DynamicType(self):
        prefix = "Geom_" if self.dimensions == 3 else "Geom2d_"
        return SimpleNamespace(Name=lambda: prefix + self.kind.title())

    def Lin(self):
        return self

    def Lin2d(self):
        return self

    def Circ(self):
        return self

    def Circ2d(self):
        return self

    def Location(self):
        return Coord(self.location)

    def Direction(self):
        return Coord(self.direction)

    def Position(self):
        return Axes(self.dimensions)

    def Radius(self):
        return self.radius

    def Value(self, parameter):
        if self.kind == "line":
            return Coord(
                tuple(x + parameter * d for x, d in zip(self.location, self.direction, strict=True))
            )
        return Coord((self.radius * math.cos(parameter), self.radius * math.sin(parameter), 0.0))


class Representation:
    def __init__(
        self,
        surface=None,
        *,
        curve3d=False,
        closed=False,
        location=None,
        parameter_range=(0.0, 5.0),
        curve=None,
        second=None,
    ):
        self.surface, self.curve3d, self.closed = surface, curve3d, closed
        self.location = Location() if location is None else location
        self.parameter_range = parameter_range
        self.curve = Curve(3 if curve3d else 2) if curve is None else curve
        self.second = Curve(2, direction=(-1.0, 0.0)) if second is None else second
        self.calls = []

    def DynamicType(self):
        kind = (
            "BRep_Curve3D"
            if self.curve3d
            else ("BRep_CurveOnClosedSurface" if self.closed else "BRep_CurveOnSurface")
        )
        return SimpleNamespace(Name=lambda: kind)

    def IsCurve3D(self):
        return self.curve3d

    def IsCurveOnSurface(self):
        return not self.curve3d

    def IsCurveOnClosedSurface(self):
        return self.closed

    def Surface(self):
        self.calls.append("surface")
        return self.surface

    def Curve3D(self):
        self.calls.append("curve3d")
        return self.curve

    def PCurve(self):
        self.calls.append("pcurve")
        return self.curve

    def PCurve2(self):
        self.calls.append("pcurve2")
        return self.second

    def Range(self):
        self.calls.append("range")
        return self.parameter_range

    def Location(self):
        self.calls.append("location")
        return self.location


class Representations:
    def __init__(self, values, *, size=None):
        self.values = tuple(values)
        self.size = len(self.values) if size is None else size
        self.iterations = 0
        self.yielded = 0

    def Size(self):
        return self.size

    def __iter__(self):
        self.iterations += 1
        for value in self.values:
            self.yielded += 1
            yield value


class Vertex:
    def __init__(self, name, point, parameter):
        self.name, self.point, self.parameter = name, Coord(point), parameter
        self.location = Location()

    def IsSame(self, other):
        return self is other

    def Location(self):
        return self.location


class Edge:
    def __init__(self, representations, *, first=None, last=None):
        self.representations = (
            representations
            if type(representations) is Representations
            else Representations(representations)
        )
        self.first = Vertex("c", (0.0, 0.0, 0.0), 0.0) if first is None else first
        self.last = Vertex("a", (5.0, 0.0, 0.0), 5.0) if last is None else last
        self.orientation, self.location = 0, Location()

    def TShape(self):
        return self

    def Curves(self):
        return self.representations

    def IsSame(self, other):
        return self is other

    def Orientation(self):
        return self.orientation

    def Location(self):
        return self.location


TOP_EXP = SimpleNamespace(
    FirstVertex_s=lambda edge, cumulative: edge.first,
    LastVertex_s=lambda edge, cumulative: edge.last,
)
BREP_TOOL = SimpleNamespace(
    Parameter_s=lambda vertex, edge: vertex.parameter,
    Pnt_s=lambda vertex: vertex.point,
    Tolerance_s=lambda shape: 1e-7,
)


@pytest.fixture(scope="module")
def collectors():
    names = {
        "_curve_profile_curve_record",
        "_curve_profile_location_record",
        "_curve_profile_surface_record",
        "_curve_profile_representation_inventory",
        "_curve_profile_edge_record",
    }
    tree = ast.parse(KERNEL.read_text())
    selected = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in selected} == names

    class BindTopExp(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == "OCP.TopExp":
                assert [(item.name, item.asname) for item in node.names] == [("TopExp", None)]
                return None
            assert not (node.module or "").startswith("OCP"), (
                "new native import needs an explicit double"
            )
            return node

    module = BindTopExp().visit(ast.Module(body=selected, type_ignores=[]))
    ast.fix_missing_locations(module)
    namespace = {
        "__name__": "mechanical_cad._pure_inventory_doubles",
        "__package__": "mechanical_cad",
        "TopExp": TOP_EXP,
        "BRep_Tool": BREP_TOOL,
    }
    exec(compile(module, str(KERNEL), "exec"), namespace)
    return SimpleNamespace(
        **{name.removeprefix("_curve_profile_"): namespace[name] for name in names}
    )


@pytest.fixture(scope="module")
def plan():
    source = SectorGeometrySource(
        (SectorPoint("c", 0.0, 0.0), SectorPoint("a", 5.0, 0.0), SectorPoint("b", 0.0, 5.0)),
        (SectorLine("ra", "c", "a"), SectorLine("rb", "c", "b")),
        (SectorArc("arc", "c", "a", "b", "ccw"),),
    )
    context = entry_context()
    prepared = prepare_native_geometry(source, NativePlane(), context=context)
    observed = tuple(
        NativeRadialDirection(line.entity_id, transform(prepared.frame, line.direction))
        for line in prepared.lines
    )
    return _continue_actual_support(prepared, observed, context)


def collect_edge(collectors, plan, entries, retained, *, mutate=None):
    edge = Edge(entries)
    vertices = {"c": edge.first, "a": edge.last}
    expected = edge
    if mutate:
        expected = mutate(edge, vertices) or edge
    return collectors.edge_record(
        plan, "line.ra", edge, expected, vertices, ("c", "a"), 0, retained
    )


def validate(plan, record, *, pcurve_required=True):
    evidence.validate_edge_observation(
        plan,
        "line.ra",
        record,
        context=PrimitiveContext(),
        traversal="support",
        pcurve_required=pcurve_required,
    )


@pytest.mark.parametrize("selected_index", range(8))
def test_retained_owner_selected_at_every_inventory_index(collectors, plan, selected_index):
    retained = Surface()
    entries = [Representation(Surface(label=f"foreign_{index}")) for index in range(8)]
    entries[selected_index] = Representation(retained)
    entries[(selected_index + 1) % 8] = Representation(curve3d=True)
    record = collect_edge(collectors, plan, entries, retained)
    assert record["stored_representation_count"] == 8
    assert record["stored_pcurve_count"] == 7
    assert record["retained_pcurve_count"] == 1
    assert record["selected_pcurve_index"] == selected_index
    assert tuple(item["index"] for item in record["representations"]) == tuple(range(8))
    assert record["pcurve"] is record["representations"][selected_index]["pcurves"][0]
    assert record["pcurve_surface_matches"] is True
    validate(plan, record)


def test_foreign_seam_retains_both_branches_without_becoming_a_candidate(collectors, plan):
    retained, foreign = Surface(), Surface("Geom_CylindricalSurface", label="cylinder")
    seam = Representation(foreign, closed=True)
    record = collect_edge(
        collectors, plan, [Representation(curve3d=True), seam, Representation(retained)], retained
    )
    assert record["stored_pcurve_count"] == 2
    assert record["retained_pcurve_count"] == 1
    assert record["selected_pcurve_index"] == 2
    observed = record["representations"][1]
    assert observed["is_closed_surface"] is True
    assert len(observed["pcurves"]) == 2
    assert observed["pcurves"][0]["direction"] == (1.0, 0.0)
    assert observed["pcurves"][1]["direction"] == (-1.0, 0.0)
    assert observed["surface_fields"]["kind"] == "Geom_CylindricalSurface"
    assert "pcurve2" in seam.calls
    validate(plan, record)


def test_geometrically_equal_different_handles_are_foreign(collectors, plan):
    retained, foreign = Surface(), Surface(label="same_geometry_other_handle")
    assert retained == foreign and retained is not foreign
    record = collect_edge(
        collectors,
        plan,
        [Representation(foreign), Representation(curve3d=True), Representation(retained)],
        retained,
    )
    assert record["retained_pcurve_count"] == 1
    assert record["selected_pcurve_index"] == 2
    assert (
        record["representations"][0]["surface_fields"]
        == record["representations"][2]["surface_fields"]
    )
    assert (
        record["representations"][0]["surface_index"]
        != record["representations"][2]["surface_index"]
    )
    assert record["representations"][0]["surface_is_retained"] is False
    validate(plan, record)


@pytest.mark.parametrize(
    "change", ["identical", "wrong_range", "wrong_location", "wrong_direction"]
)
def test_duplicate_retained_owner_is_not_filtered_by_desired_fields(collectors, plan, change):
    retained = Surface()
    altered = Representation(retained)
    if change == "wrong_range":
        altered.parameter_range = (0.0, 6.0)
    elif change == "wrong_location":
        altered.location = Location(((1.0, 0.0, 0.0, 1.0), *IDENTITY[1:]))
    elif change == "wrong_direction":
        altered.curve.direction = (-1.0, 0.0)
    record = collect_edge(
        collectors,
        plan,
        [Representation(curve3d=True), Representation(retained), altered],
        retained,
    )
    assert record["stored_pcurve_count"] == 2
    assert record["retained_pcurve_count"] == 2
    assert record["selected_pcurve_index"] is None
    assert record["pcurve"] is None
    assert record["pcurve_surface_matches"] is False
    assert (
        record["representations"][1]["surface_index"]
        == record["representations"][2]["surface_index"]
    )
    with pytest.raises(NativePlanError):
        validate(plan, record)


def test_missing_retained_owner_rejects_after_insertion_but_before_insertion_is_valid(
    collectors, plan
):
    retained = Surface()
    record = collect_edge(collectors, plan, [Representation(curve3d=True)], retained)
    assert record["stored_pcurve_count"] == record["retained_pcurve_count"] == 0
    assert record["selected_pcurve_index"] is None and record["pcurve"] is None
    validate(plan, record, pcurve_required=False)
    with pytest.raises(NativePlanError):
        validate(plan, record)


def test_foreign_only_surface_cannot_stand_in_for_retained_handle(collectors, plan):
    retained = Surface()
    record = collect_edge(
        collectors, plan, [Representation(curve3d=True), Representation(Surface())], retained
    )
    assert record["stored_pcurve_count"] == 1
    assert record["retained_pcurve_count"] == 0
    assert record["selected_pcurve_index"] is None
    with pytest.raises(NativePlanError):
        validate(plan, record)


def test_selected_seam_is_retained_as_ambiguous_without_choosing_its_good_branch(collectors, plan):
    retained = Surface()
    record = collect_edge(
        collectors,
        plan,
        [Representation(curve3d=True), Representation(retained, closed=True)],
        retained,
    )
    assert record["retained_pcurve_count"] == 1
    assert record["selected_pcurve_index"] == 1
    assert len(record["representations"][1]["pcurves"]) == 2
    assert record["pcurve"] is None
    with pytest.raises(NativePlanError):
        validate(plan, record)


@pytest.mark.parametrize("change", ["range", "location", "direction", "center"])
def test_unique_owner_changed_equation_or_location_is_not_repaired(collectors, plan, change):
    retained, rep = Surface(), Representation()
    rep.surface = retained
    if change == "range":
        rep.parameter_range = (0.0, 6.0)
    elif change == "location":
        rep.location = Location(((1.0, 0.0, 0.0, 1.0), *IDENTITY[1:]))
    elif change == "direction":
        rep.curve.direction = (-1.0, 0.0)
    else:
        rep.curve.location = (1.0, 0.0)
    record = collect_edge(collectors, plan, [Representation(curve3d=True), rep], retained)
    assert record["retained_pcurve_count"] == 1
    assert record["selected_pcurve_index"] == 1
    with pytest.raises(NativePlanError):
        validate(plan, record)


@pytest.mark.parametrize("count", [9, 100])
def test_inventory_limit_stops_before_ninth_entry_metadata_and_never_materializes_tail(
    collectors, count
):
    retained = Surface()
    entries = [Representation(curve3d=True), *[Representation(Surface()) for _ in range(count - 1)]]
    collection = Representations(entries)
    with pytest.raises(NativePlanError, match="^native_representation_limit$"):
        collectors.representation_inventory(Edge(collection), retained)
    assert collection.yielded <= 9
    assert all(not entry.calls for entry in entries[8:])
    assert collection.iterations <= 1


def test_foreign_order_is_serialized_without_changing_selected_equation(collectors, plan):
    retained = Surface()
    first = Representation(Surface(label="first"), parameter_range=(11.0, 12.0))
    second = Representation(Surface(label="second"), parameter_range=(21.0, 22.0))
    curve, selected = Representation(curve3d=True), Representation(retained)
    before = collect_edge(collectors, plan, [curve, first, selected, second], retained)
    after = collect_edge(collectors, plan, [second, selected, first, curve], retained)
    assert before["pcurve"] == after["pcurve"]
    assert before["selected_pcurve_index"] == 2 and after["selected_pcurve_index"] == 1
    assert tuple(item["range"] for item in before["representations"]) == (
        (0.0, 5.0),
        (11.0, 12.0),
        (0.0, 5.0),
        (21.0, 22.0),
    )
    assert tuple(item["range"] for item in after["representations"]) == (
        (21.0, 22.0),
        (0.0, 5.0),
        (11.0, 12.0),
        (0.0, 5.0),
    )
    validate(plan, before)
    validate(plan, after)


def test_unknown_foreign_surface_metadata_cannot_vanish(collectors, plan):
    retained = Surface()
    entries = [
        Representation(curve3d=True),
        Representation(retained),
        Representation(Surface("Geom_BSplineSurface")),
    ]
    with pytest.raises(NativePlanError, match="^unsupported_native_surface_metadata$"):
        collect_edge(collectors, plan, entries, retained)


@pytest.mark.parametrize(
    "change", ["edge", "vertex", "orientation", "edge_location", "vertex_location"]
)
def test_owner_aware_inventory_does_not_waive_occurrence_identity(collectors, plan, change):
    retained = Surface()

    def mutate(edge, vertices):
        if change == "edge":
            return Edge(edge.representations)
        if change == "vertex":
            vertices["a"] = Vertex("a", (5.0, 0.0, 0.0), 5.0)
        elif change == "orientation":
            edge.orientation = 1
        elif change == "edge_location":
            edge.location = Location(identity=False)
        else:
            edge.last.location = Location(identity=False)
        return edge

    record = collect_edge(
        collectors,
        plan,
        [Representation(curve3d=True), Representation(retained)],
        retained,
        mutate=mutate,
    )
    assert record["retained_pcurve_count"] == 1
    with pytest.raises(NativePlanError):
        validate(plan, record)


@pytest.fixture
def complete_record(collectors, plan):
    retained = Surface()
    return collect_edge(
        collectors,
        plan,
        [Representation(curve3d=True), Representation(Surface()), Representation(retained)],
        retained,
    )


@pytest.mark.parametrize(
    "field", ["stored_representation_count", "stored_pcurve_count", "retained_pcurve_count"]
)
@pytest.mark.parametrize(
    "value",
    [True, False, 0, -1, 1.0, 9, "1", None, 1 << 100_000],
    ids=["true", "false", "zero", "negative", "float", "overcap", "string", "none", "huge"],
)
def test_detached_global_and_selected_counts_are_strict_and_consistent(
    plan, complete_record, field, value
):
    complete_record[field] = value
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


@pytest.mark.parametrize(
    "value",
    [True, False, -1, 0, 1, 3, 2.0, "2", None, 1 << 100_000],
    ids=[
        "true",
        "false",
        "negative",
        "curve3d",
        "foreign",
        "pastend",
        "float",
        "string",
        "missing",
        "huge",
    ],
)
def test_selected_index_must_be_exact_actual_unique_owner_index(plan, complete_record, value):
    complete_record["selected_pcurve_index"] = value
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("index", True),
        ("index", 1.0),
        ("index", 0),
        ("representation_type", "BRep_Unknown"),
        ("representation_type", 0),
        ("is_curve3d", 0),
        ("is_curve3d", True),
        ("is_on_surface", 1),
        ("is_on_surface", False),
        ("is_closed_surface", 0),
        ("is_closed_surface", True),
        ("surface_is_retained", 1),
        ("surface_is_retained", False),
        ("surface_index", True),
        ("surface_index", -1),
        ("surface_index", 8),
        ("surface_index", 1.0),
        ("surface_index", "retained"),
        ("surface_index", None),
        ("pcurves", []),
        ("pcurves", ()),
        ("range", [0.0, 5.0]),
        ("range", (0.0,)),
        ("range", (0, 5.0)),
        ("range", (0.0, math.inf)),
        ("range", (5.0, 0.0)),
        ("range", (0.0, 6.0)),
        ("curve3d", {}),
    ],
)
def test_selected_inventory_record_fields_cannot_be_forged(plan, complete_record, field, value):
    complete_record["representations"][2][field] = value
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


@pytest.mark.parametrize("where", ["root", "entry", "location", "surface", "branch"])
@pytest.mark.parametrize("change", ["missing", "unknown", "nonstring"])
def test_inventory_schema_keys_are_exact_at_every_level(plan, complete_record, where, change):
    record = complete_record
    if where != "root":
        record = record["representations"][2]
        if where == "location":
            record = record["location"]
        elif where == "surface":
            record = record["surface_fields"]
        elif where == "branch":
            record = record["pcurves"][0]
    if change == "missing":
        del record[next(iter(record))]
    elif change == "unknown":
        record["unapproved"] = True
    else:
        record[1] = record.pop(next(iter(record)))
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


@pytest.mark.parametrize("container", [None, [], {}, (), (None,), tuple({} for _ in range(9))])
def test_inventory_container_cardinality_and_entry_types_are_strict(
    plan, complete_record, container
):
    complete_record["representations"] = container
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("identity", 1),
        ("identity", False),
        ("matrix", list(IDENTITY)),
        ("matrix", IDENTITY[:2]),
        ("matrix", ((1.0, 0.0, 0.0), *IDENTITY[1:])),
        ("matrix", ((1, 0.0, 0.0, 0.0), *IDENTITY[1:])),
        ("matrix", ((math.nan, 0.0, 0.0, 0.0), *IDENTITY[1:])),
        ("matrix", ((1.0, 0.0, 0.0, math.ulp(0.0)), *IDENTITY[1:])),
    ],
)
def test_selected_location_scalar_shape_and_exact_identity_are_mandatory(
    plan, complete_record, field, value
):
    complete_record["representations"][2]["location"][field] = value
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "Geom_CylindricalSurface"),
        ("kind", "Geom_BSplineSurface"),
        ("origin", (0.0, 0.0)),
        ("origin", [0.0, 0.0, 0.0]),
        ("origin", (0, 0.0, 0.0)),
        ("origin", (math.inf, 0.0, 0.0)),
        ("origin", (math.ulp(0.0), 0.0, 0.0)),
        ("u", (0.0, 1.0, 0.0)),
        ("v", (1.0, 0.0, 0.0)),
        ("normal", (0.0, 0.0, -1.0)),
        ("radius", 5.0),
    ],
)
def test_selected_surface_metadata_must_match_the_frozen_plane(plan, complete_record, field, value):
    complete_record["representations"][2]["surface_fields"][field] = value
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "spline"),
        ("direction", (True, 0.0)),
        ("direction", (math.nan, 0.0)),
        ("direction", (-1.0, 0.0)),
        ("location", (1.0, 0.0)),
        ("range", (0.0, 6.0)),
        ("identity_location", 1),
        ("identity_location", False),
        ("radius", 5.0),
        ("normal", (0.0, 0.0, 1.0)),
    ],
)
def test_selected_branch_fields_and_outer_record_agreement_are_strict(
    plan, complete_record, field, value
):
    # Deep-copy breaks the collector's harmless alias, so selected-entry and
    # top-level agreement are independently exercised by this mutation.
    complete_record["pcurve"] = copy.deepcopy(complete_record["pcurve"])
    complete_record["representations"][2]["pcurves"][0][field] = value
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


def test_detached_selected_branch_count_cannot_exceed_two(plan, complete_record):
    item = complete_record["representations"][2]
    item["pcurves"] = item["pcurves"] * 3
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


def test_surface_identity_indices_cannot_merge_foreign_with_retained(plan, complete_record):
    complete_record["representations"][2]["surface_index"] = 0
    with pytest.raises(NativePlanError, match="^invalid_native_representation$"):
        validate(plan, complete_record)


def test_surface_identity_first_seen_order_is_checked(plan, complete_record):
    complete_record["representations"][1]["surface_index"] = 1
    complete_record["representations"][2]["surface_index"] = 0
    with pytest.raises(NativePlanError, match="^invalid_native_representation$"):
        validate(plan, complete_record)


def test_inventory_reordering_requires_consistent_original_indices(plan, complete_record):
    complete_record["representations"] = complete_record["representations"][::-1]
    with pytest.raises(NativePlanError, match="^invalid_native_representation$"):
        validate(plan, complete_record)


def test_nonmatching_surface_records_are_still_strictly_validated(plan, complete_record):
    complete_record["representations"][1]["pcurves"][0]["direction"] = (math.nan, 0.0)
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


def test_foreign_fields_are_retained_without_a_second_sector_equation_requirement(collectors, plan):
    retained = Surface()
    foreign = Representation(
        Surface(),
        parameter_range=(-12.0, -1.0),
        curve=Curve(2, location=(42.0, 17.0), direction=(0.0, -1.0)),
    )
    record = collect_edge(
        collectors,
        plan,
        [Representation(curve3d=True), foreign, Representation(retained)],
        retained,
    )
    assert record["representations"][1]["pcurves"][0]["location"] == (42.0, 17.0)
    validate(plan, record)


def test_before_insertion_rejects_an_existing_retained_association(plan, complete_record):
    with pytest.raises(NativePlanError, match="^native_pcurve_owner_ambiguous$"):
        validate(plan, complete_record, pcurve_required=False)


@pytest.mark.parametrize("stage", [None, 0, 1, "true"])
def test_inventory_stage_flag_is_exact_bool(plan, complete_record, stage):
    with pytest.raises(NativePlanError, match="^invalid_native_stage$"):
        evidence.validate_representation_inventory(
            plan, "line.ra", complete_record, pcurve_required=stage
        )


def test_complete_inventory_evidence_overflow_never_truncates(complete_record):
    record = {
        "events": [{"stage": "synthetic_inventory", "observation": complete_record, "padding": ""}],
        "operation": "curve_profile",
        "operations_start": 0,
    }
    overhead = len(evidence.bounded_evidence_bytes(record))
    record["events"][0]["padding"] = "x" * (1_048_576 - overhead)
    assert len(evidence.bounded_evidence_bytes(record)) == 1_048_576
    record["events"][0]["padding"] += "x"
    before = copy.deepcopy(record)
    with pytest.raises(NativePlanError, match="^native_evidence_limit$"):
        evidence.bounded_evidence_bytes(record)
    assert record == before


def test_all_historical_kernel_spans_and_protected_runtime_files_stay_unchanged():
    # Execute the existing exact additive-boundary/hash guard without importing
    # either its unit-test module or any native-backed production module.
    path = ROOT / "tests/unit/test_arc_profile_incidence.py"
    tree = ast.parse(path.read_bytes())
    name = "test_104_runtime_files_and_primitives_unchanged_with_reviewed_additive_kernel"
    node = next(
        item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name
    )
    namespace = {
        "ROOT": ROOT,
        "TRUSTED_GUARD_ROOT": ROOT,
        "historical_runtime_root": historical_runtime_root,
        "ast": ast,
        "hashlib": hashlib,
        "json": json,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    namespace[name]()


def test_complete_evidence_limit_still_dominates_shape_registration():
    tree = ast.parse(KERNEL.read_text())
    kernel = next(
        item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "OCPKernel"
    )
    for name in ("sector_profile", "extrude_sector"):
        method = next(
            item for item in kernel.body if isinstance(item, ast.FunctionDef) and item.name == name
        )
        bounds, registrations = [], []
        for node in ast.walk(method):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "bounded_evidence_bytes":
                    bounds.append(node.lineno)
                if isinstance(node.func, ast.Attribute) and node.func.attr == "_remember":
                    registrations.append(node.lineno)
        assert bounds and len(registrations) == 1 and max(bounds) < registrations[0]


def test_foreign_identity_true_requires_exact_identity_matrix(plan, complete_record):
    location = complete_record["representations"][1]["location"]
    assert location["identity"] is True
    location["matrix"] = ((1.0, 0.0, 0.0, math.ulp(0.0)), *IDENTITY[1:])
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


def test_foreign_nonempty_location_chain_may_have_identity_matrix(collectors, plan):
    retained = Surface()
    foreign = Representation(Surface(), location=Location(identity=False))
    record = collect_edge(
        collectors,
        plan,
        [Representation(curve3d=True), foreign, Representation(retained)],
        retained,
    )
    assert record["representations"][1]["location"] == {"identity": False, "matrix": IDENTITY}
    validate(plan, record)


def test_repeated_foreign_handle_reuses_its_observed_identity_index(collectors, plan):
    retained, foreign = Surface(), Surface()
    record = collect_edge(
        collectors,
        plan,
        [
            Representation(foreign),
            Representation(curve3d=True),
            Representation(retained),
            Representation(foreign, closed=True),
        ],
        retained,
    )
    assert tuple(item["surface_index"] for item in record["representations"]) == (0, None, 1, 0)
    assert record["retained_pcurve_count"] == 1
    validate(plan, record)


@pytest.mark.parametrize("count", [0, 2])
def test_inventory_requires_exactly_one_actual_3d_representation(collectors, plan, count):
    retained = Surface()
    with pytest.raises(NativePlanError, match="^native_evidence_incomplete$"):
        collect_edge(
            collectors,
            plan,
            [*[Representation(curve3d=True) for _ in range(count)], Representation(retained)],
            retained,
        )


def test_unrecognized_stored_representation_is_not_dropped(collectors):
    retained = Surface()
    rep = Representation(curve3d=True)
    rep.DynamicType = lambda: SimpleNamespace(Name=lambda: "BRep_Polygon3D")
    with pytest.raises(NativePlanError, match="^unsupported_native_representation_metadata$"):
        collectors.representation_inventory(Edge([rep, Representation(retained)]), retained)


@pytest.mark.parametrize("where", ["root", "entry", "tuple", "float"])
def test_detached_inventory_rejects_container_and_scalar_subclasses(plan, complete_record, where):
    class Dict(dict):
        pass

    class Tuple(tuple):
        pass

    class Float(float):
        pass

    if where == "root":
        complete_record = Dict(complete_record)
    elif where == "entry":
        complete_record["representations"] = (
            *complete_record["representations"][:2],
            Dict(complete_record["representations"][2]),
        )
    elif where == "tuple":
        complete_record["representations"] = Tuple(complete_record["representations"])
    else:
        complete_record["representations"][1]["surface_fields"]["origin"] = (Float(0), 0.0, 0.0)
    with pytest.raises(NativePlanError):
        validate(plan, complete_record)


@pytest.mark.parametrize("correct_occurrence", [False, True])
def test_first_cap_genuine_occurrence_guard_remains_before_inventory(correct_occurrence):
    from mechanical_cad.arc_profile_native_plan import _require

    tree = ast.parse(KERNEL.read_text())
    kernel = next(
        item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "OCPKernel"
    )
    method = next(
        item
        for item in kernel.body
        if isinstance(item, ast.FunctionDef) and item.name == "extrude_sector"
    )
    guard = next(
        item
        for item in ast.walk(method)
        if isinstance(item, ast.Expr)
        and isinstance(item.value, ast.Call)
        and any(
            isinstance(arg, ast.Constant) and arg.value == "native_cap_history_changed"
            for arg in item.value.args
        )
    )
    snapshot = next(
        item
        for item in ast.walk(method)
        if isinstance(item, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "post_snapshot" for target in item.targets
        )
    )
    assert guard.lineno < snapshot.lineno
    profile = object()
    first = SimpleNamespace(
        ShapeType=lambda: 4, IsSame=lambda other: correct_occurrence and other is profile
    )
    last = SimpleNamespace(ShapeType=lambda: 4)
    namespace = {
        "_require": _require,
        "first": first,
        "last": last,
        "profile": profile,
        "TopAbs_FACE": 4,
    }
    code = compile(ast.Module(body=[guard], type_ignores=[]), str(KERNEL), "exec")
    if correct_occurrence:
        exec(code, namespace)
    else:
        with pytest.raises(NativePlanError, match="^native_cap_history_changed$"):
            exec(code, namespace)


@pytest.mark.parametrize("face_orientation,wire_orientation", [(1, 0), (0, 1), (0, 0)])
def test_actual_face_orientation_guard_is_still_mandatory(face_orientation, wire_orientation):
    from mechanical_cad.arc_profile_native_plan import _require

    tree = ast.parse(KERNEL.read_text())
    function = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_curve_profile_face_snapshot"
    )
    guard = next(
        item
        for item in function.body
        if isinstance(item, ast.Expr)
        and isinstance(item.value, ast.Call)
        and "face.Orientation()" in ast.unparse(item)
    )
    namespace = {
        "_require": _require,
        "face": SimpleNamespace(Orientation=lambda: face_orientation),
        "children": [SimpleNamespace(Orientation=lambda: wire_orientation)],
    }
    code = compile(ast.Module(body=[guard], type_ignores=[]), str(KERNEL), "exec")
    if face_orientation == wire_orientation == 0:
        exec(code, namespace)
    else:
        with pytest.raises(NativePlanError, match="^native_material_side_ambiguous$"):
            exec(code, namespace)


@pytest.fixture
def circle_record(collectors, plan):
    retained = Surface()
    circle_range = plan.increasing_parameters
    entries = [
        Representation(curve3d=True, curve=Curve(3, kind="circle"), parameter_range=circle_range),
        Representation(Surface("Geom_CylindricalSurface"), closed=True),
        Representation(retained, curve=Curve(2, kind="circle"), parameter_range=circle_range),
        Representation(Surface()),
    ]
    first = Vertex("a", (5.0, 0.0, 0.0), circle_range[0])
    last = Vertex("b", (0.0, 5.0, 0.0), circle_range[1])
    edge = Edge(entries, first=first, last=last)
    return collectors.edge_record(
        plan, "arc.arc", edge, edge, {"a": first, "b": last}, ("a", "b"), 0, retained
    )


def test_circle_with_three_total_surface_associations_keeps_unique_original_equation(
    plan, circle_record
):
    assert circle_record["stored_representation_count"] == 4
    assert circle_record["stored_pcurve_count"] == 3
    assert circle_record["retained_pcurve_count"] == 1
    assert circle_record["selected_pcurve_index"] == 2
    assert circle_record["pcurve"]["kind"] == "circle"
    assert circle_record["pcurve"]["radius"] == plan.radius
    assert len(circle_record["representations"][1]["pcurves"]) == 2
    evidence.validate_edge_observation(
        plan,
        "arc.arc",
        circle_record,
        context=PrimitiveContext(),
        traversal="support",
        pcurve_required=True,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("radius", math.nextafter(5.0, math.inf)),
        ("location", (math.ulp(0.0), 0.0)),
        ("u", (-1.0, 0.0)),
        ("v", (0.0, -1.0)),
        ("normal", (0.0, 0.0, 1.0)),
        ("range", (0.0, math.pi)),
        ("direction", (1.0, 0.0)),
    ],
)
def test_selected_circle_fields_stay_exact_despite_foreign_representations(
    plan, circle_record, field, value
):
    circle_record["pcurve"][field] = value
    with pytest.raises(NativePlanError):
        evidence.validate_edge_observation(
            plan,
            "arc.arc",
            circle_record,
            context=PrimitiveContext(),
            traversal="support",
            pcurve_required=True,
        )
