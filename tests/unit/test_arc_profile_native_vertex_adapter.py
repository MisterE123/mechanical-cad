"""Native-free adapter sequencing and fixed generated-graph collector controls.

The kernel is parsed, never imported. Extracted source runs only against explicit
identity-bearing doubles; these tests do not establish real native behavior.
"""

from __future__ import annotations

import ast
import copy
import importlib.abc
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import mechanical_cad.arc_profile_native_evidence as evidence
import mechanical_cad.arc_profile_native_plan as native

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / "src/mechanical_cad/kernel_ocp.py"
KERNEL_BYTES = KERNEL.read_bytes()
TREE = ast.parse(KERNEL_BYTES)
KERNEL_CLASS = next(
    node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "OCPKernel"
)
METHODS = {node.name: node for node in KERNEL_CLASS.body if isinstance(node, ast.FunctionDef)}
FUNCTIONS = {node.name: node for node in TREE.body if isinstance(node, ast.FunctionDef)}


class NoNativeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (
            fullname.split(".")[0] in {"OCP", "OCC", "cadquery", "slvs", "bpy", "bmesh"}
            or fullname == "mechanical_cad.kernel_ocp"
        ):
            raise AssertionError(f"native import forbidden in adapter controls: {fullname}")
        return None


@pytest.fixture(autouse=True)
def no_native_imports():
    blocker = NoNativeImports()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


def calls(node, name):
    return [
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Call) and ast.unparse(item.func) == name
    ]


def assignment(body, target):
    return next(
        item
        for item in body
        if isinstance(item, ast.Assign)
        and any(ast.unparse(value) == target for value in item.targets)
    )


def profile_body():
    return next(node for node in METHODS["sector_profile"].body if isinstance(node, ast.Try)).body


def test_public_native_entries_accept_no_detached_plan_or_representative_authority():
    for name, positional, keyword in (
        ("sector_profile", ("self", "sketch"), ("context", "evidence_sink")),
        ("extrude_sector", ("self", "profile", "height"), ("evidence_sink",)),
    ):
        arguments = METHODS[name].args
        assert tuple(arg.arg for arg in arguments.args) == positional
        assert tuple(arg.arg for arg in arguments.kwonlyargs) == keyword
        assert arguments.vararg is arguments.kwarg is None


def test_supports_then_actual_proof_then_two_authored_values_then_mapping_then_vertices():
    method = METHODS["sector_profile"]
    names = (
        "_continue_native_plan",
        "Geom_Plane",
        "Geom_Circle",
        "Geom_Line",
        "_continue_actual_support_for_vertices",
        "circle.Value",
        "_continue_vertex_representation",
        "BRepBuilderAPI_MakeVertex",
    )
    sites = [calls(method, name) for name in names]
    assert all(len(items) == 1 for items in sites)
    assert [items[0].lineno for items in sites] == sorted(items[0].lineno for items in sites)
    value_loop = next(
        node
        for node in ast.walk(method)
        if isinstance(node, ast.For) and calls(node, "circle.Value")
    )
    assert (
        ast.unparse(value_loop.iter)
        == "zip((arc.start_id, arc.end_id), plan.parameters, strict=True)"
    )
    assert ast.unparse(calls(value_loop, "circle.Value")[0]) == "circle.Value(parameter)"
    assert not any(isinstance(node, (ast.While, ast.Try)) for node in ast.walk(value_loop))
    assert len(calls(value_loop, "NativeEndpointObservation")) == 1
    mapping = calls(method, "_continue_vertex_representation")[0]
    assert (
        ast.unparse(mapping)
        == "_continue_vertex_representation(plan, observations, c, continuation=continuation)"
    )
    vertices = assignment(profile_body(), "vertices").value
    assert isinstance(vertices, ast.DictComp)
    assert ast.unparse(vertices.generators[0].iter) == "representatives.vertices"
    assert len(vertices.generators) == 1 and not vertices.generators[0].ifs


def test_explicit_vertex_parameter_edge_overloads_and_fixed_supports_remain():
    method = METHODS["sector_profile"]
    constructors = calls(method, "BRepBuilderAPI_MakeEdge")
    assert len(constructors) == 2
    assert [ast.unparse(item) for item in constructors] == [
        "BRepBuilderAPI_MakeEdge(circle, vertices[ids[0]], vertices[ids[1]], *plan.increasing_parameters)",
        "BRepBuilderAPI_MakeEdge(curve, vertices[arc.center_id], vertices[line.point_id], 0.0, line.trim_parameter)",
    ]
    line = calls(method, "Geom_Line")[0]
    assert (
        ast.unparse(line)
        == "Geom_Line(gp_Pnt(*transform(plan.frame, plan.center)), gp_Dir(*transform(plan.frame, line.direction)))"
    )
    names = {node.attr for node in ast.walk(method) if isinstance(node, ast.Attribute)}
    assert not names & {
        "UpdateVertex",
        "SetTolerance",
        "SameParameter",
        "SameRange",
        "BuildCurves3d",
    }
    assert not calls(method, "prepare_native_vertex_representation")
    assert len(calls(method, "BRepGProp.SurfaceProperties_s")) == 1


def test_every_profile_stage_checks_the_frozen_representatives():
    total = 0
    for method_name, expected in (
        ("sector_profile", "representatives"),
        ("extrude_sector", "state.representatives"),
    ):
        for call in calls(METHODS[method_name], "validate_edge_observation"):
            keywords = {item.arg: ast.unparse(item.value) for item in call.keywords}
            assert keywords["representatives"] == expected
            assert keywords["context"] == "c"
            total += 1
    assert total == 6


def test_retained_live_ticket_context_and_record_continue_into_extrusion():
    profile = ast.unparse(METHODS["sector_profile"])
    extrusion = ast.unparse(METHODS["extrude_sector"])
    assert "state.representatives = representatives" in profile
    assert "state.representative_continuation = continuation" in profile
    assert "state.circle = retained_circle" in profile
    assert "state.representative_points = representative_points" in profile
    for fragment in (
        "state.representative_continuation.plan is plan",
        "state.representative_continuation.context is c",
        "state.representative_continuation.operations_end == state.representatives.resources.operations_start",
        "c.operations >= state.representatives.resources.operations_end",
        "c.max_bits == state.representative_continuation.max_bits",
        "c.max_operations == state.representative_continuation.max_operations",
        "solid_state.representatives = state.representatives",
        "solid_state.representative_continuation = state.representative_continuation",
        "solid_state.circle = state.circle",
        "solid_state.representative_points = state.representative_points",
    ):
        assert fragment in extrusion
    assert (
        calls(METHODS["extrude_sector"], "validate_generated_trace_observation")[0].args[1].attr
        == "representatives"
    )


def test_generated_gate_precedes_the_single_mass_and_registration():
    method = METHODS["extrude_sector"]
    names = (
        "validate_end_cap_observation",
        "_curve_profile_generated_trace_record",
        "validate_generated_trace_observation",
        "_exact_volume",
        "check_masses",
        "self._remember",
    )
    sites = [calls(method, name) for name in names]
    assert all(len(items) == 1 for items in sites)
    assert [items[0].lineno for items in sites] == sorted(items[0].lineno for items in sites)
    assert len(calls(method, "BRepPrimAPI_MakePrism")) == 1


class Point:
    def __init__(self, *values):
        self.values = tuple(values[0]) if len(values) == 1 else tuple(values)
        self.coord_calls = 0

    def Coord(self):
        self.coord_calls += 1
        return self.values

    def Distance(self, other):
        return math.dist(self.values, other.values)


def run_preconstruction(*, value_failure=None, proof_failure=None, wrong_point_type=False):
    """Execute the actual fixed constructor/value/mapping prefix with doubles."""
    body = profile_body()
    first = body.index(assignment(body, "axes"))
    last = body.index(assignment(body, "vertices"))
    statements = copy.deepcopy(body[first : last + 1])
    log, events, built, observed = [], [], [], []
    arc = NS(id="arc", center_id="c", start_id="a", end_id="b")
    frame = NS(origin=(0.0, 0.0, 0.0), u=(1.0, 0.0, 0.0), v=(0.0, 1.0, 0.0), normal=(0.0, 0.0, 1.0))
    lines = tuple(
        NS(
            entity_id=f"r{identifier}",
            point_id=identifier,
            direction=direction,
            trim_parameter=10.0,
        )
        for identifier, direction in (("a", (1.0, 0.0)), ("b", (0.0, 1.0)))
    )
    plan = NS(
        source=NS(incidence=NS(arc=arc)),
        frame=frame,
        center=(17.0, -29.0),
        radius=10.0,
        parameters=(0.0, 1.5707963267948966),
        increasing_parameters=(0.0, 1.5707963267948966),
        lines=lines,
    )
    context, ticket = object(), object()
    candidates = ((27.0, -29.0, 0.0), (17.0, -19.0, -0.0))

    class DifferentPoint(Point):
        pass

    class Circle:
        def Value(self, parameter):
            index = len(observed)
            log.append(("value", parameter))
            observed.append(parameter)
            if value_failure == index:
                raise RuntimeError("synthetic native Value failure")
            return (DifferentPoint if wrong_point_type else Point)(candidates[index])

    circle = Circle()

    def make_circle(*args):
        log.append(("circle",))
        return circle

    def make_line(origin, direction):
        log.append(("line", direction))
        return NS(direction=direction)

    def actual_support(received, directions, c):
        assert received is plan and c is context and len(directions) == 2
        log.append(("actual_proof",))
        if proof_failure == "support":
            raise native.NativePlanError("synthetic_support_failure")
        return plan, ticket

    def mapping(received, observations, c, *, continuation):
        assert received is plan and c is context and continuation is ticket
        assert tuple(value.parameter for value in observations) == plan.parameters
        assert tuple(value.point_id for value in observations) == ("a", "b")
        assert tuple(value.world_point for value in observations) == candidates
        log.append(("mapping",))
        if proof_failure == "mapping":
            raise native.NativePlanError("synthetic_mapping_failure")
        return NS(
            vertices=(
                ("c", (17.0, -29.0, 0.0)),
                *(tuple((value.point_id, value.world_point) for value in observations)),
            )
        )

    def make_vertex(point):
        log.append(("vertex", point.values))
        built.append(point.values)
        return NS(Vertex=lambda: point)

    namespace = {
        "plan": plan,
        "c": context,
        "gp_Ax3": lambda *args: args,
        "gp_Pnt": Point,
        "gp_Dir": lambda *args: args,
        "gp_Ax2": lambda *args: args,
        "gp_Circ": lambda *args: args,
        "Geom_Plane": lambda *args: log.append(("plane",)),
        "Geom_Circle": make_circle,
        "Geom_Line": make_line,
        "transform": native.transform,
        "NativeEndpointObservation": native.NativeEndpointObservation,
        "NativeRadialDirection": native.NativeRadialDirection,
        "_curve_profile_curve_record": lambda curve, *args: {
            "direction": getattr(curve, "direction", None)
        },
        "validate_initial_curve_fields": lambda *args: log.append(("inspect",)),
        "event": lambda stage, value: events.append((stage, value)),
        "_continue_actual_support_for_vertices": actual_support,
        "_continue_vertex_representation": mapping,
        "plan_bytes": lambda value: b"plan",
        "vertex_representation_bytes": lambda value: b"representation",
        "BRepBuilderAPI_MakeVertex": make_vertex,
        "_require": native._require,
    }
    extract_function("_curve_profile_native_type_record", namespace)
    error = None
    try:
        exec(compile(ast.Module(statements, type_ignores=[]), str(KERNEL), "exec"), namespace)
    except Exception as exc:
        error = exc
    return NS(
        log=log,
        events=events,
        built=built,
        observed=observed,
        error=error,
        namespace=namespace,
        circle=circle,
    )


def test_exactly_two_same_circle_values_precede_all_three_vertices():
    result = run_preconstruction()
    assert result.error is None
    assert len(result.observed) == 2 and len(result.built) == 3
    kinds = [row[0] for row in result.log]
    assert kinds.count("plane") == kinds.count("circle") == 1 and kinds.count("line") == 2
    assert (
        kinds.index("actual_proof")
        < kinds.index("value")
        < kinds.index("mapping")
        < kinds.index("vertex")
    )
    assert result.built[-1][-1].hex() == "-0x0.0p+0"
    raw = [value for stage, value in result.events if stage == "raw_canonical_vertex_candidate"]
    assert [item["point_id"] for item in raw] == ["a", "b"]
    assert [item["parameter"] for item in raw] == result.observed
    held = result.namespace["representative_points"]
    assert type(held) is tuple and len(held) == 2 and held[0] is not held[1]
    assert all(type(point) is Point and point.coord_calls == 1 for point in held)
    assert result.namespace["retained_circle"] is result.circle
    for item, point in zip(raw, held, strict=True):
        assert item["point_object_id"] == id(point)
        assert item["circle_object_id"] == id(result.circle)
        assert item["point_type"] == {"module": Point.__module__, "qualname": Point.__qualname__}
        assert item["circle_type"] == {
            "module": type(result.circle).__module__,
            "qualname": type(result.circle).__qualname__,
        }
        assert item["circle_is_verified_support"] is True
        assert item["parameter_hex"] == item["parameter"].hex()
        assert item["world_point_hex"] == tuple(value.hex() for value in point.values)


def test_wrong_native_point_type_preserves_raw_observation_and_constructs_nothing():
    result = run_preconstruction(wrong_point_type=True)
    assert isinstance(result.error, native.NativePlanError)
    assert result.error.code == "native_circle_evaluation_type_changed"
    assert len(result.observed) == 1 and result.built == []
    raw = [value for stage, value in result.events if stage == "raw_canonical_vertex_candidate"]
    assert len(raw) == 1 and raw[0]["point_type"]["qualname"].endswith("DifferentPoint")
    assert raw[0]["point_object_id"] == id(result.namespace["representative_points"][0])
    assert not any(row[0] == "mapping" for row in result.log)


def test_every_native_profile_edge_and_face_inspection_receives_the_held_circle():
    direct, snapshots = 0, 0
    for method_name, expected in (
        ("sector_profile", "retained_circle"),
        ("extrude_sector", "state.circle"),
    ):
        for helper, label in (
            ("_curve_profile_edge_record", "edge"),
            ("_curve_profile_face_snapshot", "face"),
        ):
            for call in calls(METHODS[method_name], helper):
                keywords = {item.arg: ast.unparse(item.value) for item in call.keywords}
                assert keywords["retained_circle"] == expected
                direct += label == "edge"
                snapshots += label == "face"
    assert direct == 3 and snapshots == 3
    calls_from_snapshot = calls(
        FUNCTIONS["_curve_profile_face_snapshot"], "_curve_profile_edge_record"
    )
    assert len(calls_from_snapshot) == 1
    assert {item.arg: ast.unparse(item.value) for item in calls_from_snapshot[0].keywords}[
        "retained_circle"
    ] == "retained_circle"


@pytest.mark.parametrize(
    "failure,expected_values,expected_raw", [("support", 0, 0), ("mapping", 2, 2)]
)
def test_support_or_mapping_failure_constructs_no_vertex(failure, expected_values, expected_raw):
    result = run_preconstruction(proof_failure=failure)
    assert isinstance(result.error, native.NativePlanError)
    assert len(result.observed) == expected_values and result.built == []
    assert (
        len([row for row in result.events if row[0] == "raw_canonical_vertex_candidate"])
        == expected_raw
    )


@pytest.mark.parametrize("index", [0, 1])
def test_value_failure_preserves_already_observed_raw_prefix_without_retry(index):
    result = run_preconstruction(value_failure=index)
    assert isinstance(result.error, RuntimeError)
    assert len(result.observed) == index + 1 and result.built == []
    assert (
        len([row for row in result.events if row[0] == "raw_canonical_vertex_candidate"]) == index
    )
    assert not any(row[0] == "mapping" for row in result.log)


class Location:
    def IsIdentity(self):
        return True


class Shape:
    def __init__(
        self,
        identity,
        kind,
        *,
        endpoints=(),
        point=None,
        children=(),
        partner=None,
        orientation=0,
        surface=None,
    ):
        self.identity = identity
        self.kind = {"vertex": 7, "edge": 6, "wire": 5, "face": 4}.get(kind, kind)
        self.endpoints = endpoints
        self.point, self.children = point, tuple(children)
        self.partner = identity if partner is None else partner
        self.orientation, self.surface = orientation, surface

    def IsNull(self):
        return False

    def ShapeType(self):
        return self.kind

    def IsSame(self, other):
        return self.identity == other.identity

    def IsPartner(self, other):
        return self.partner == other.partner

    def IsEqual(self, other):
        return self.IsSame(other) and self.orientation == other.orientation

    def Orientation(self):
        return self.orientation

    def Location(self):
        return Location()


class Iterator:
    def __init__(self, shape, cumulative_orientation, cumulative_location):
        self.values, self.index = shape.children, 0
        self.flags = (cumulative_orientation, cumulative_location)

    def More(self):
        return self.index < len(self.values)

    def Value(self):
        return self.values[self.index]

    def Next(self):
        self.index += 1


def extract_function(name, namespace):
    node = copy.deepcopy(FUNCTIONS[name])

    class StripNativeImports(ast.NodeTransformer):
        def visit_ImportFrom(self, item):
            if item.module and item.module.startswith("OCP."):
                return None
            return item

    node = StripNativeImports().visit(node)
    namespace["__package__"] = "mechanical_cad"
    exec(
        compile(
            ast.fix_missing_locations(ast.Module([node], type_ignores=[])), str(KERNEL), "exec"
        ),
        namespace,
    )
    return namespace[name]


def generated_fixture(*, split_vertical=False, duplicate_face=False, extra_edge=False):
    base = {
        pid: Shape(f"base.{pid}", "vertex", point=point)
        for pid, point in (("c", (0.0, 0.0, 0.0)), ("a", (5.0, 0.0, 0.0)), ("b", (0.0, 5.0, 0.0)))
    }
    top = {
        pid: Shape(
            f"top.{pid}",
            "vertex",
            point=(value.point[0], value.point[1], 7.0),
            partner=value.partner,
        )
        for pid, value in base.items()
    }
    roles_and_ids = (("arc.arc", "a", "b"), ("line.ra", "c", "a"), ("line.rb", "c", "b"))
    base_edges = {
        role: Shape(f"base.{role}", "edge", endpoints=(base[a], base[b]))
        for role, a, b in roles_and_ids
    }
    top_edges = {
        role: Shape(
            f"top.{role}", "edge", endpoints=(top[a], top[b]), partner=base_edges[role].partner
        )
        for role, a, b in roles_and_ids
    }
    vertical = {
        pid: Shape(f"vertical.{pid}", "edge", endpoints=(base[pid], top[pid])) for pid in base
    }
    faces, generated = [], {}
    for role, a, b in roles_and_ids:
        surface = NS(
            DynamicType=lambda role=role: NS(
                Name=lambda: "Geom_CylindricalSurface" if role.startswith("arc.") else "Geom_Plane"
            )
        )
        edges = [base_edges[role], vertical[b], top_edges[role], vertical[a]]
        if split_vertical and role == "line.ra":
            edges[1] = Shape("different.vertical.a", "edge", endpoints=(base["a"], top["a"]))
        if extra_edge and role == "arc.arc":
            edges.append(vertical["c"])
        wire = Shape(f"wire.{role}", "wire", children=edges)
        face = Shape(f"face.{role}", "face", children=(wire,), surface=surface)
        faces.append(face)
        generated[f"side.{role}"] = Shape(
            face.identity, "face", partner=face.partner, orientation=1
        )
    if duplicate_face:
        faces.append(faces[0])
    by_original = {value.identity: top[pid] for pid, value in base.items()}
    by_original.update({value.identity: top_edges[role] for role, value in base_edges.items()})
    state = NS(vertices=base, edges=base_edges, surface=object())
    builder = NS(
        FirstShape=lambda original: original,
        LastShape=lambda original: by_original[original.identity],
    )
    arc = NS(center_id="c", start_id="a", end_id="b")
    uses = tuple(
        NS(kind=role.split(".")[0], entity_id=role.split(".")[1]) for role, _, _ in roles_and_ids
    )
    plan = NS(source=NS(incidence=NS(arc=arc), boundary=uses))
    events, traversed, inventories = [], [], []

    def iterator(shape, *flags):
        traversed.append(shape.identity)
        return Iterator(shape, *flags)

    namespace = {
        "TopAbs_VERTEX": 7,
        "TopAbs_EDGE": 6,
        "TopAbs_WIRE": 5,
        "TopoDS": NS(
            Vertex=lambda value: value, Edge=lambda value: value, Face=lambda value: value
        ),
        "TopoDS_Iterator": iterator,
        "TopLoc_Location": Location,
        "TopExp": NS(
            FirstVertex_s=lambda edge, oriented: edge.endpoints[0],
            LastVertex_s=lambda edge, oriented: edge.endpoints[1],
        ),
        "BRep_Tool": NS(
            Pnt_s=lambda vertex: Point(vertex.point),
            Tolerance_s=lambda item: 1e-7,
            Surface_s=lambda face, location: face.surface,
            Range_s=lambda edge: (0.0, 1.0),
        ),
        "_curve_profile_location_record": lambda location: {"identity": True},
        "_curve_profile_surface_record": lambda surface: {"kind": surface.DynamicType().Name()},
        "_curve_profile_generated_inventory": lambda edge, owners, **kwargs: (
            inventories.append((edge.identity, tuple(owners))) or ()
        ),
    }
    extract_function("_curve_profile_generated_children", namespace)
    collector = extract_function("_curve_profile_generated_trace_record", namespace)

    def collect():
        return collector(
            plan,
            state,
            builder,
            object(),
            faces,
            generated,
            7.0,
            (0.0, 0.0, 7.0),
            lambda stage, value: events.append((stage, value)),
        )

    return NS(
        collect=collect,
        events=events,
        traversed=traversed,
        inventories=inventories,
        faces=faces,
        generated=generated,
    )


def test_fixed_collector_keeps_six_vertices_nine_edges_twelve_occurrences_and_real_orientation():
    fixture = generated_fixture()
    record = fixture.collect()
    assert len(record["vertices"]) == 6 and len(record["edges"]) == 9 and len(record["faces"]) == 3
    assert sum(len(face["occurrences"]) for face in record["faces"]) == 12
    assert all(
        face["generated_is_same"]
        and face["generated_is_partner"]
        and not face["generated_is_equal"]
        for face in record["faces"]
    )
    assert all(
        face["generated_orientation"] == 1 and face["orientation"] == 0 for face in record["faces"]
    )
    assert len(fixture.inventories) == 9
    assert all(len(owners) == 4 for _, owners in fixture.inventories)
    assert all(item["identity_matches"] for item in record["edges"])


def test_equal_endpoint_coordinates_do_not_allow_a_distinct_vertical_handle_to_replace_the_first():
    fixture = generated_fixture(split_vertical=True)
    with pytest.raises(native.NativePlanError, match="^native_generated_identity_changed$"):
        fixture.collect()
    assert fixture.inventories == []
    stage, raw = fixture.events[-1]
    assert stage == "raw_generated_split_vertical"
    assert raw == {
        "role": "vertical.a",
        "endpoint_ids": ("base.a", "top.a"),
        "existing_is_same": False,
    }
    assert any(stage == "raw_generated_face" for stage, _ in fixture.events)


def test_generated_to_actual_face_association_rejects_before_side_traversal():
    fixture = generated_fixture(duplicate_face=True)
    with pytest.raises(native.NativePlanError, match="^native_generated_identity_changed$"):
        fixture.collect()
    assert fixture.traversed == [] and fixture.inventories == []
    assert fixture.events[-1][0] == "raw_generated_face_association"
    assert fixture.events[-1][1]["actual_face_match_count"] == 2


def test_fifth_side_edge_preserves_bounded_overflow_raw_and_stops_before_inventory():
    fixture = generated_fixture(extra_edge=True)
    with pytest.raises(native.NativePlanError, match="^native_generated_cardinality_changed$"):
        fixture.collect()
    assert fixture.inventories == []
    assert fixture.events[-1] == (
        "raw_generated_collection_overflow",
        {"label": "side.arc.arc", "limit": 4},
    )


def test_generated_inventory_uses_only_raw_read_accessors_and_fixed_branch_bounds():
    node = FUNCTIONS["_curve_profile_generated_inventory"]
    source = ast.unparse(node)
    assert "if index == 8:" in source
    assert "(rep.PCurve(), rep.PCurve2()) if closed else (rep.PCurve(),)" in source
    assert "known is owner" in source
    assert "owner_roles" in source and "representations" in source
    assert not calls(node, "BRep_Tool.CurveOnSurface_s")
    assert not any(
        isinstance(value, ast.Attribute)
        and value.attr
        in {"UpdateEdge", "UpdateVertex", "BuildCurves3d", "SameParameter", "SameRange"}
        for value in ast.walk(node)
    )


def observed_arc_with_expected_circle(*, distinct=False, supplied=True, role="arc.arc"):
    """Run the unchanged actual edge reader with one held or field-equal circle."""
    parameters = (0.0, math.pi / 2)
    points = ((5.0, 0.0, 0.0), (0.0, 5.0, 0.0))

    class Circle:
        fields = {"kind": "circle", "radius": 5.0, "range": parameters}

        def Value(self, parameter):
            return Point(points[parameters.index(parameter)])

    actual = Circle()
    retained = Circle() if distinct else actual
    assert actual.fields == retained.fields
    vertices = {
        identifier: Shape(identifier, "vertex", point=point)
        for identifier, point in zip(("a", "b"), points, strict=True)
    }
    edge = Shape("arc.edge", "edge", endpoints=tuple(vertices.values()))
    representation = NS(Curve3D=lambda: actual, Range=lambda: parameters, Location=Location)
    inventory = ({"index": 0, "is_curve3d": True, "is_on_surface": False},)
    namespace = {
        "TopExp": NS(
            FirstVertex_s=lambda edge, oriented: edge.endpoints[0],
            LastVertex_s=lambda edge, oriented: edge.endpoints[1],
        ),
        "BRep_Tool": NS(
            Parameter_s=lambda vertex, edge: parameters[("a", "b").index(vertex.identity)],
            Pnt_s=lambda vertex: Point(vertex.point),
            Tolerance_s=lambda value: 1e-7,
        ),
        "_curve_profile_representation_inventory": lambda edge, surface: (
            inventory,
            (representation,),
        ),
        "_curve_profile_curve_record": lambda curve, *args: dict(curve.fields),
    }
    collector = extract_function("_curve_profile_edge_record", namespace)
    plan = NS(source=NS(incidence=NS(arc=NS(id="arc"))))
    keywords = {"retained_circle": retained} if supplied else {}
    record = collector(plan, role, edge, edge, vertices, ("a", "b"), 0, object(), **keywords)
    return plan, record, actual, retained


@pytest.mark.parametrize("distinct", [False, True])
def test_actual_circle_handle_identity_is_observed_separately_from_identical_coefficients(distinct):
    _, record, actual, retained = observed_arc_with_expected_circle(distinct=distinct)
    assert actual.fields == retained.fields
    assert (actual is retained) == (not distinct)
    assert record["curve_support_identity_matches"] is (not distinct)
    assert record["evaluated_endpoints"] == record["vertex_coordinates"]
    assert record["observed_distances"] == (0.0, 0.0)


def test_field_equal_distinct_circle_observation_is_rejected_before_mapping_or_arithmetic(
    monkeypatch,
):
    plan, record, _, _ = observed_arc_with_expected_circle(distinct=True)
    # Isolate the new observed-identity gate. This is not a positive support or
    # inventory proof: their separate tests and mathematical gates stay intact.
    monkeypatch.setattr(evidence, "validate_curve_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(evidence, "validate_representation_inventory", lambda *args, **kwargs: None)
    with pytest.raises(native.NativePlanError, match="^native_curve_support_identity_changed$"):
        evidence.validate_edge_observation(
            plan, "arc.arc", record, context=object(), traversal="support", representatives=object()
        )


def test_optional_circle_observation_preserves_old_detached_grammar_and_does_not_test_lines_as_arcs():
    _, old, _, _ = observed_arc_with_expected_circle(supplied=False)
    assert "curve_support_identity_matches" not in old
    _, radial, _, _ = observed_arc_with_expected_circle(distinct=True, role="line.ra")
    assert radial["curve_support_identity_matches"] is True
