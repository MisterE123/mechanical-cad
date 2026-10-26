"""Native-free controls for the bounded, advisory regularity collector.

Only the actual kernel functions' AST is executed, against explicit doubles.
No native module or kernel module is imported, and no geometry is constructed.
These controls establish collection semantics, not native execution or proof.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.abc
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from historical_runtime_source import historical_runtime_root
from test_arc_profile_native_end_cap import _assembly_step_bytes

from mechanical_cad.arc_profile_native_plan import NativePlanError

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / "src/mechanical_cad/kernel_ocp.py"
IDENTITY = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))
ENUM_NAMES = (
    "GeomAbs_C0",
    "GeomAbs_G1",
    "GeomAbs_C1",
    "GeomAbs_G2",
    "GeomAbs_C2",
    "GeomAbs_C3",
    "GeomAbs_CN",
)
GENERATED_KEYS = {
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
}
REGULARITY_KEYS = {
    "surface1",
    "surface2",
    "location2",
    "continuity_value",
    "continuity_name",
    "continuity_type",
}
SURFACE_KEYS = {"surface_index", "owner_roles", "surface_fields"}
SNAPSHOT8_CLASS_SHA256 = "db48fc00268e1adbd682797935a7ecebd8b2f71e43e53b769c06b95d7a4ae53d"
SNAPSHOT8_UNCHANGED_NODES_SHA256 = (
    "0b2894351bdfff69c21e86893b976ef4512ab6828dd8f84b650b134a9f3e5cee"
)


class NoNativeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (
            fullname.split(".")[0] in {"OCP", "OCC", "cadquery", "slvs", "bpy", "bmesh"}
            or fullname == "mechanical_cad.kernel_ocp"
        ):
            raise AssertionError(f"native/kernel import forbidden: {fullname}")
        return None


@pytest.fixture(autouse=True)
def no_native_imports():
    blocker = NoNativeImports()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


class GeomAbs_Shape:
    """The explicitly substituted native enum class, with observed conversion."""

    def __init__(self, value, calls):
        self.value, self.calls = value, calls

    def __int__(self):
        self.calls.append("enum.int")
        return self.value


GeomAbs_Shape.__module__ = "OCP.OCP.GeomAbs"


class Coord:
    def __init__(self, values):
        self.values = tuple(values)

    def Coord(self):
        return self.values


class Location:
    def __init__(self, matrix=IDENTITY, *, identity=True):
        self.matrix, self.identity = matrix, identity

    def Transformation(self):
        return self

    def IsIdentity(self):
        return self.identity

    def Value(self, row, column):
        return self.matrix[row - 1][column - 1]


class Surface:
    """Identity alone associates handles; geometric equality is poisonous."""

    def __init__(self, *, origin=(0.0, 0.0, 0.0), kind="Geom_Plane"):
        self.origin, self.kind = origin, kind

    def __eq__(self, other):
        raise AssertionError("surface association must use native handle identity")

    def DynamicType(self):
        return NS(Name=lambda: self.kind)

    def Pln(self):
        return self

    def Cylinder(self):
        return self

    def Position(self):
        return self

    def Location(self):
        return Coord(self.origin)

    def XDirection(self):
        return Coord((1.0, 0.0, 0.0))

    def YDirection(self):
        return Coord((0.0, 1.0, 0.0))

    def Direction(self):
        return Coord((0.0, 0.0, 1.0))

    def Radius(self):
        return 5.0


class Curve:
    def __init__(self, dimensions, *, direction=None):
        self.dimensions = dimensions
        self.direction = (1.0,) + (0.0,) * (dimensions - 1) if direction is None else direction

    def DynamicType(self):
        return NS(Name=lambda: "Geom_Line" if self.dimensions == 3 else "Geom2d_Line")

    def Lin(self):
        return self

    def Lin2d(self):
        return self

    def Location(self):
        return Coord((0.0,) * self.dimensions)

    def Direction(self):
        return Coord(self.direction)


class GetterFailure(RuntimeError):
    pass


class Representation:
    def __init__(
        self,
        surface1=None,
        surface2=None,
        *,
        kind="BRep_CurveOn2Surfaces",
        flags=(False, False, False, True),
        value=0,
        fail=None,
        location=None,
        location2=None,
    ):
        self.surface1, self.surface2 = surface1, surface2
        self.kind, self.flags, self.fail = kind, flags, fail
        self.calls = []
        self.value = GeomAbs_Shape(value, self.calls)
        self.location = Location() if location is None else location
        self.location2 = Location() if location2 is None else location2
        self.curve = Curve(3 if flags[0] is True else 2)
        self.second = Curve(2, direction=(-1.0, 0.0))

    def _get(self, name, value):
        self.calls.append(name)
        if self.fail == name:
            raise GetterFailure(f"unavailable {name}")
        return value

    def DynamicType(self):
        self.calls.append("DynamicType")
        return NS(Name=lambda: self.kind)

    def IsCurve3D(self):
        return self._get("IsCurve3D", self.flags[0])

    def IsCurveOnSurface(self):
        return self._get("IsCurveOnSurface", self.flags[1])

    def IsCurveOnClosedSurface(self):
        return self._get("IsCurveOnClosedSurface", self.flags[2])

    def IsRegularity(self):
        return self._get("IsRegularity", self.flags[3])

    def Location(self):
        return self._get("Location", self.location)

    def Surface(self):
        return self._get("Surface", self.surface1)

    def Surface2(self):
        return self._get("Surface2", self.surface2)

    def Location2(self):
        return self._get("Location2", self.location2)

    def Continuity(self):
        return self._get("Continuity", self.value)

    def _geometric(self, name, value):
        if self.kind == "BRep_CurveOn2Surfaces":
            self.calls.append(f"PROHIBITED:{name}")
            raise AssertionError(f"regularity getter {name} must never be invoked")
        return self._get(name, value)

    def Range(self):
        return self._geometric("Range", (0.0, 5.0))

    def Curve3D(self):
        return self._geometric("Curve3D", self.curve)

    def PCurve(self):
        return self._geometric("PCurve", self.curve)

    def PCurve2(self):
        return self._geometric("PCurve2", self.second)

    def Value(self, *args):
        return self._geometric("Value", None)

    def D0(self, *args):
        return self._geometric("D0", None)


class Representations:
    def __init__(self, values):
        self.values = tuple(values)
        self.iterations = self.yielded = 0

    def __iter__(self):
        self.iterations += 1
        for item in self.values:
            self.yielded += 1
            yield item


class Edge:
    def __init__(self, values):
        self.representations = Representations(values)

    def TShape(self):
        return self

    def Curves(self):
        return self.representations


def geometric(surface=None, *, closed=False):
    return Representation(
        surface,
        kind=(
            "BRep_Curve3D"
            if surface is None
            else ("BRep_CurveOnClosedSurface" if closed else "BRep_CurveOnSurface")
        ),
        flags=(surface is None, surface is not None, closed, closed),
    )


@pytest.fixture
def collectors():
    names = {
        "_curve_profile_curve_record",
        "_curve_profile_location_record",
        "_curve_profile_surface_record",
        "_curve_profile_native_type_record",
        "_curve_profile_regularity_type_record",
        "_curve_profile_generated_inventory",
        "_curve_profile_generated_regularity_record",
    }
    selected = [
        node
        for node in ast.parse(KERNEL.read_bytes()).body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in selected} == names

    class BindNativeEnum(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == "OCP.GeomAbs":
                assert [(item.name, item.asname) for item in node.names] == [
                    ("GeomAbs_Shape", None),
                ]
                return None
            assert not (node.module or "").startswith("OCP"), (
                "new native import needs an explicit audited double"
            )
            return node

        def visit_Import(self, node):
            assert not any(item.name.split(".")[0] == "OCP" for item in node.names)
            return node

    module = BindNativeEnum().visit(ast.Module(body=selected, type_ignores=[]))
    ast.fix_missing_locations(module)
    namespace = {
        "__name__": "mechanical_cad._pure_regularity_adapter_doubles",
        "__package__": "mechanical_cad",
        "GeomAbs_Shape": GeomAbs_Shape,
    }
    exec(compile(module, str(KERNEL), "exec"), namespace)
    return NS(**{name.removeprefix("_curve_profile_"): namespace[name] for name in names})


def collect(collectors, entries, owners=None, *, events=None):
    events = [] if events is None else events
    edge = Edge(entries)
    result = collectors.generated_inventory(
        edge,
        {} if owners is None else owners,
        event=lambda name, value: events.append((name, copy.deepcopy(value))),
        label="vertical.c",
    )
    return result, edge, events


def owner_fields(surface):
    return {
        "kind": surface.kind,
        "origin": surface.origin,
        "u": (1.0, 0.0, 0.0),
        "v": (0.0, 1.0, 0.0),
        "normal": (0.0, 0.0, 1.0),
        "radius": 5.0 if surface.kind == "Geom_CylindricalSurface" else None,
    }


@pytest.mark.parametrize("value", range(7))
@pytest.mark.parametrize("reverse", (False, True))
def test_complete_owner_orders_and_every_advisory_enum(collectors, value, reverse):
    first, second = Surface(), Surface(origin=(0.0, 1.0, 0.0))
    owners = {"side.line.ra": first, "side.line.rb": second}
    pair = (second, first) if reverse else (first, second)
    rep = Representation(*pair, value=value)
    result, edge, events = collect(collectors, [geometric(), rep], owners)
    assert events == []
    assert edge.representations.iterations == 1
    assert tuple(item["index"] for item in result) == (0, 1)
    assert all(set(item) == GENERATED_KEYS for item in result)
    assert result[0]["is_regularity"] is False and result[0]["regularity"] is None
    item = result[1]
    assert item["is_regularity"] is True
    assert item["range"] == () and item["curve3d"] is None and item["pcurves"] == ()
    assert item["surface_index"] is None and item["surface_fields"] is None
    assert item["surface_is_retained"] is False and item["owner_roles"] == ()
    assert item["location"] == {"identity": True, "matrix": IDENTITY}
    metadata = item["regularity"]
    assert type(metadata) is dict and set(metadata) == REGULARITY_KEYS
    assert metadata["location2"] == {"identity": True, "matrix": IDENTITY}
    for index, surface in enumerate(pair):
        slot = metadata[f"surface{index + 1}"]
        assert type(slot) is dict and set(slot) == SURFACE_KEYS
        assert slot["surface_index"] == index
        assert slot["owner_roles"] == tuple(
            role for role, known in owners.items() if known is surface
        )
        assert slot["surface_fields"] == owner_fields(surface)
    assert type(metadata["continuity_value"]) is int
    assert metadata["continuity_value"] == value
    assert type(metadata["continuity_name"]) is str
    assert metadata["continuity_name"] == ENUM_NAMES[value]
    assert metadata["continuity_type"] == {
        "module": "OCP.OCP.GeomAbs",
        "qualname": "GeomAbs_Shape",
    }
    assert [
        call
        for call in rep.calls
        if call
        in {
            "Location",
            "Surface",
            "Surface2",
            "Location2",
            "Continuity",
            "enum.int",
        }
    ] == ["Location", "Surface", "Surface2", "Location2", "Continuity", "enum.int"]
    assert not any(call.startswith("PROHIBITED:") for call in rep.calls)


def test_existing_closed_surface_keeps_geometric_branches(collectors):
    surface = Surface()
    rep = geometric(surface, closed=True)
    result, _, events = collect(collectors, [rep], {"side.arc.arc": surface})
    assert events == []
    item = result[0]
    assert item["is_regularity"] is True and item["regularity"] is None
    assert item["range"] == (0.0, 5.0)
    assert item["curve3d"] is None
    assert item["surface_index"] == 0
    assert item["owner_roles"] == ("side.arc.arc",)
    assert len(item["pcurves"]) == 2
    assert [branch["direction"] for branch in item["pcurves"]] == [
        (1.0, 0.0),
        (-1.0, 0.0),
    ]
    assert all(branch["range"] == (0.0, 5.0) for branch in item["pcurves"])
    assert not set(rep.calls) & {"Surface2", "Location2", "Continuity", "enum.int"}


def test_plain_surface_and_3d_keep_false_null_metadata(collectors):
    surface = Surface()
    result, _, events = collect(collectors, [geometric(), geometric(surface)])
    assert events == []
    assert all(item["is_regularity"] is False for item in result)
    assert all(item["regularity"] is None for item in result)
    assert result[0]["curve3d"] is not None and result[0]["pcurves"] == ()
    assert result[1]["curve3d"] is None and len(result[1]["pcurves"]) == 1


@pytest.mark.parametrize(
    ("getter", "field", "available"),
    (
        ("IsRegularity", "IsRegularity", ()),
        ("Surface", "surface1", ()),
        ("Surface2", "surface2", ("surface1",)),
        ("Location2", "location2", ("surface1", "surface2")),
        ("Continuity", "continuity", ("surface1", "surface2", "location2")),
    ),
)
def test_each_permitted_getter_failure_retains_exact_prefix(
    collectors,
    getter,
    field,
    available,
):
    first, second = Surface(), Surface()
    rep = Representation(first, second, fail=getter)
    after = Representation(Surface(), Surface())
    events = []
    with pytest.raises(GetterFailure, match=f"unavailable {getter}"):
        collect(collectors, [geometric(), rep, after], events=events)
    assert after.calls == []
    assert len(events) == 1
    name, raw = events[0]
    assert name == "raw_generated_regularity_metadata_failure"
    assert set(raw) == {"role", "unavailable_field", "exception_type", "representations"}
    assert raw["role"] == "vertical.c" and raw["unavailable_field"] == field
    assert raw["exception_type"] == {
        "module": __name__,
        "qualname": "GetterFailure",
    }
    assert len(raw["representations"]) == 2
    complete, partial = raw["representations"]
    assert complete["index"] == 0 and complete["curve3d"] is not None
    assert partial["index"] == 1 and set(partial) == GENERATED_KEYS
    assert partial["location"] == {"identity": True, "matrix": IDENTITY}
    assert partial["range"] == () and partial["curve3d"] is None
    assert partial["pcurves"] == () and partial["owner_roles"] == ()
    if getter == "IsRegularity":
        assert partial["is_regularity"] is None and partial["regularity"] is None
    else:
        assert partial["is_regularity"] is True
        metadata = partial["regularity"]
        assert set(metadata) == REGULARITY_KEYS
        assert {key for key, value in metadata.items() if value is not None} == set(available)
        for index, key in enumerate(key for key in available if key.startswith("surface")):
            assert metadata[key] == {
                "surface_index": index,
                "owner_roles": (),
                "surface_fields": owner_fields((first, second)[index]),
            }
    getters = ["IsRegularity", "Surface", "Surface2", "Location2", "Continuity", "enum.int"]
    assert [name for name in rep.calls if name in getters] == getters[: getters.index(getter) + 1]
    assert not any(name.startswith("PROHIBITED:") for name in rep.calls)


class CoercibleEnum:
    def __init__(self):
        self.callbacks = []

    def __int__(self):
        self.callbacks.append("int")
        raise AssertionError("wrong enum must reject before conversion")

    def __str__(self):
        self.callbacks.append("str")
        raise AssertionError("wrong enum must not stringify")

    def __repr__(self):
        self.callbacks.append("repr")
        raise AssertionError("wrong enum must not repr")


class EnumSubclass(GeomAbs_Shape):
    def __int__(self):
        self.calls.append("forbidden.subclass.int")
        raise AssertionError("subclass must reject before conversion")


@pytest.mark.parametrize("variant", ("bool", "int", "coercible", "subclass", "none", "string"))
def test_native_enum_exact_class_precedes_any_conversion(collectors, variant):
    rep = Representation(Surface(), Surface())
    values = {
        "bool": True,
        "int": 0,
        "coercible": CoercibleEnum(),
        "subclass": EnumSubclass(0, rep.calls),
        "none": None,
        "string": "GeomAbs_C0",
    }
    rep.value = values[variant]
    events = []
    after = geometric()
    with pytest.raises(NativePlanError, match="invalid_native_regularity_enum"):
        collect(collectors, [rep, after], events=events)
    assert after.calls == []
    assert "enum.int" not in rep.calls and "forbidden.subclass.int" not in rep.calls
    if variant == "coercible":
        assert rep.value.callbacks == []
    assert len(events) == 1
    name, raw = events[0]
    assert name == "raw_generated_regularity_metadata_failure"
    assert raw["unavailable_field"] == "continuity_type"
    metadata = raw["representations"][0]["regularity"]
    assert metadata["continuity_value"] is None and metadata["continuity_name"] is None
    assert metadata["surface1"] is not None and metadata["surface2"] is not None
    assert metadata["location2"] is not None
    assert metadata["continuity_type"] == {
        "module": type(rep.value).__module__,
        "qualname": type(rep.value).__qualname__,
    }


@pytest.mark.parametrize("value", (-1, 7, 1 << 100))
def test_unknown_native_enum_keeps_observed_value_without_name(collectors, value):
    rep = Representation(Surface(), Surface(), value=value)
    events = []
    with pytest.raises(NativePlanError, match="invalid_native_regularity_enum"):
        collect(collectors, [rep], events=events)
    assert rep.calls.count("enum.int") == 1
    raw = events[0][1]
    assert raw["unavailable_field"] == "continuity_value"
    metadata = raw["representations"][0]["regularity"]
    assert metadata["continuity_value"] == value and metadata["continuity_name"] is None


def test_wrong_enum_metaclass_cannot_supply_callbacks(collectors):
    callbacks = []

    class PoisonMeta(type):
        def __getattribute__(cls, name):
            if name in {"__module__", "__qualname__"}:
                callbacks.append(name)
                raise AssertionError("foreign enum metaclass hook must not run")
            return super().__getattribute__(name)

    class ForeignEnum(metaclass=PoisonMeta):
        def __int__(self):
            callbacks.append("int")
            raise AssertionError("foreign enum conversion must not run")

    rep, events = Representation(Surface(), Surface()), []
    rep.value = ForeignEnum()
    with pytest.raises(NativePlanError, match="invalid_native_regularity_enum"):
        collect(collectors, [rep], events=events)
    assert callbacks == []
    metadata = events[0][1]["representations"][0]["regularity"]
    assert metadata["continuity_type"] == {
        "module": __name__,
        "qualname": "test_wrong_enum_metaclass_cannot_supply_callbacks.<locals>.ForeignEnum",
    }
    assert metadata["continuity_value"] is None


def test_enum_conversion_failure_retains_type_and_does_not_retry(collectors, monkeypatch):
    rep, events = Representation(Surface(), Surface()), []

    def failing_int(self):
        self.calls.append("enum.int")
        raise GetterFailure("unavailable enum conversion")

    monkeypatch.setattr(GeomAbs_Shape, "__int__", failing_int)
    with pytest.raises(GetterFailure, match="unavailable enum conversion"):
        collect(collectors, [rep], events=events)
    assert rep.calls.count("enum.int") == 1
    raw = events[0][1]
    assert raw["unavailable_field"] == "continuity_value"
    metadata = raw["representations"][0]["regularity"]
    assert metadata["continuity_type"] == {
        "module": "OCP.OCP.GeomAbs",
        "qualname": "GeomAbs_Shape",
    }
    assert metadata["continuity_value"] is None and metadata["continuity_name"] is None


@pytest.mark.parametrize("attribute", ("__module__", "__qualname__"))
@pytest.mark.parametrize("size", (0, 128, 129))
def test_native_enum_type_observation_has_exact_bounds(collectors, attribute, size):
    original = getattr(GeomAbs_Shape, attribute)
    try:
        setattr(GeomAbs_Shape, attribute, "x" * size)
        rep = Representation(Surface(), Surface())
        events = []
        if size == 128:
            result, _, _ = collect(collectors, [rep], events=events)
            assert result[0]["regularity"]["continuity_type"][attribute.strip("_")] == "x" * size
            assert rep.calls.count("enum.int") == 1
            assert events == []
        else:
            with pytest.raises(NativePlanError, match="native_type_metadata_unavailable"):
                collect(collectors, [rep], events=events)
            assert "enum.int" not in rep.calls
            assert events[0][1]["unavailable_field"] == "continuity_type"
            assert events[0][1]["representations"][0]["regularity"]["continuity_type"] is None
    finally:
        setattr(GeomAbs_Shape, attribute, original)


class StringSubclass(str):
    pass


class EqualityPoison:
    def __eq__(self, other):
        raise AssertionError("flag/type equality callback must never execute")

    def __bool__(self):
        raise AssertionError("flag truth callback must never execute")


@pytest.mark.parametrize("value", (None, 0, StringSubclass("OCP.OCP.GeomAbs"), EqualityPoison()))
def test_enum_module_metadata_requires_exact_builtin_string(collectors, value):
    original = GeomAbs_Shape.__module__
    try:
        GeomAbs_Shape.__module__ = value
        rep, events = Representation(Surface(), Surface()), []
        with pytest.raises(NativePlanError, match="native_type_metadata_unavailable"):
            collect(collectors, [rep], events=events)
        assert "enum.int" not in rep.calls
        assert events[0][1]["unavailable_field"] == "continuity_type"
        assert events[0][1]["representations"][0]["regularity"]["continuity_type"] is None
    finally:
        GeomAbs_Shape.__module__ = original


@pytest.mark.parametrize("position", range(4))
@pytest.mark.parametrize("value", (0, 1, None, "false", EqualityPoison()))
def test_non_bool_flags_reject_before_owner_or_enum_getters(collectors, position, value):
    flags = [False, False, False, True]
    flags[position] = value
    rep = Representation(Surface(), Surface(), flags=tuple(flags))
    events = []
    with pytest.raises(NativePlanError, match="unsupported_native_representation_metadata"):
        collect(collectors, [rep], events=events)
    assert len(events) == 1 and events[0][0] == "raw_generated_unsupported_representation"
    assert not set(rep.calls) & {
        "Surface",
        "Surface2",
        "Location2",
        "Continuity",
        "enum.int",
        "Range",
    }
    assert events[0][1]["representations"][0]["regularity"] is None


@pytest.mark.parametrize(
    ("kind", "flags"),
    (
        ("BRep_CurveOn2Surfaces", (False, False, False, False)),
        ("BRep_CurveOn2Surfaces", (True, False, False, True)),
        ("BRep_CurveOn2Surfaces", (False, True, False, True)),
        ("BRep_CurveOn2Surfaces", (False, False, True, True)),
        ("BRep_CurveOn2Surfaces", (True, True, True, True)),
        ("BRep_Unknown", (False, False, False, True)),
        ("BRep_Curve3D", (False, False, False, True)),
        (StringSubclass("BRep_CurveOn2Surfaces"), (False, False, False, True)),
        (EqualityPoison(), (False, False, False, True)),
        ("BRep_Curve3D", (True, False, False, True)),
        ("BRep_CurveOnSurface", (False, True, False, True)),
        ("BRep_CurveOnClosedSurface", (False, True, True, False)),
    ),
)
def test_contradictory_flags_and_wrong_kind_reject_before_owner_getters(collectors, kind, flags):
    rep = Representation(Surface(), Surface(), kind=kind, flags=flags)
    events = []
    with pytest.raises(NativePlanError, match="unsupported_native_representation_metadata"):
        collect(collectors, [rep], events=events)
    assert events[0][0] == "raw_generated_unsupported_representation"
    assert not set(rep.calls) & {
        "Surface",
        "Surface2",
        "Location2",
        "Continuity",
        "enum.int",
        "Range",
        "Curve3D",
        "PCurve",
        "PCurve2",
    }


@pytest.mark.parametrize("metadata_index", range(8))
def test_all_eight_raw_indices_and_eight_surface_handles_are_retained(collectors, metadata_index):
    surfaces = [Surface(origin=(float(index), 0.0, 0.0)) for index in range(8)]
    metadata = Representation(*surfaces[-2:])
    entries = [geometric(surface) for surface in surfaces[:-2]]
    entries.insert(metadata_index % 7, geometric())
    entries.insert(metadata_index, metadata)
    owners = {f"owner{index}": surface for index, surface in enumerate(surfaces)}
    result, edge, events = collect(collectors, entries, owners)
    assert events == [] and edge.representations.yielded == 8
    assert tuple(item["index"] for item in result) == tuple(range(8))
    assert result[metadata_index]["regularity"] is not None
    observed = []
    for item in result:
        if item["regularity"] is not None:
            observed.extend(item["regularity"][key] for key in ("surface1", "surface2"))
        elif item["surface_index"] is not None:
            observed.append(item)
    assert [slot["surface_index"] for slot in observed] == list(range(8))
    assert {slot["surface_fields"]["origin"] for slot in observed} == {
        surface.origin for surface in surfaces
    }


def test_ninth_entry_retains_first_eight_without_invoking_the_ninth(collectors):
    entries = [geometric() for _ in range(10)]
    edge, events = Edge(entries), []
    with pytest.raises(NativePlanError, match="native_representation_limit"):
        collectors.generated_inventory(
            edge,
            {},
            label="vertical.c",
            event=lambda name, value: events.append((name, copy.deepcopy(value))),
        )
    assert edge.representations.iterations == 1 and edge.representations.yielded == 9
    assert entries[8].calls == [] and entries[9].calls == []
    assert len(events) == 1 and events[0][0] == "raw_generated_inventory_overflow"
    assert tuple(item["index"] for item in events[0][1]["representations"]) == tuple(range(8))


@pytest.mark.parametrize("new_slot", (1, 2))
def test_surface_cap_precedes_append_for_each_regularity_owner(collectors, new_slot):
    surfaces = [Surface() for _ in range(9 - new_slot)]
    before = tuple(surfaces)
    rep = Representation(Surface(), Surface())
    item, records, events = {"index": 7}, [{"index": 0}], []
    with pytest.raises(NativePlanError, match="native_representation_limit"):
        collectors.generated_regularity_record(
            rep,
            {},
            surfaces,
            item,
            records,
            label="vertical.c",
            event=lambda name, value: events.append((name, copy.deepcopy(value))),
        )
    assert len(surfaces) == 8
    assert all(held is original for held, original in zip(surfaces, before, strict=False))
    assert records == [{"index": 0}]
    assert events[0][1]["unavailable_field"] == f"surface{new_slot}.surface_index"
    metadata = events[0][1]["representations"][-1]["regularity"]
    assert metadata[f"surface{new_slot}"]["surface_index"] is None
    assert metadata[f"surface{new_slot}"]["surface_fields"] is not None
    assert not set(rep.calls) & {"Location2", "Continuity", "enum.int"}
    if new_slot == 1:
        assert "Surface2" not in rep.calls and metadata["surface2"] is None
    else:
        assert surfaces[-1] is rep.surface1 and metadata["surface1"]["surface_index"] == 7


@pytest.mark.parametrize("metadata_first", (False, True))
def test_ninth_surface_handle_rejects_within_eight_entry_inventory(collectors, metadata_first):
    entries = [geometric(Surface()) for _ in range(7)]
    rep = Representation(Surface(), Surface())
    entries.insert(0 if metadata_first else 7, rep)
    events = []
    with pytest.raises(NativePlanError, match="native_representation_limit"):
        collect(collectors, entries, events=events)
    name, raw = events[0]
    assert len(raw["representations"]) == 8
    assert tuple(item["index"] for item in raw["representations"]) == tuple(range(8))
    if metadata_first:
        assert name == "raw_generated_inventory_overflow"
        assert raw["representations"][-1]["surface_index"] is None
    else:
        assert name == "raw_generated_regularity_metadata_failure"
        assert raw["unavailable_field"] == "surface2.surface_index"
        assert raw["representations"][-1]["regularity"]["surface1"]["surface_index"] == 7
        assert raw["representations"][-1]["regularity"]["surface2"]["surface_index"] is None


def test_shared_registry_reuses_identity_and_preserves_all_raw_owner_matches(collectors):
    known, foreign = Surface(), Surface()
    owners = {"side.line.ra": known, "alias.same.handle": known}
    rep = Representation(known, foreign)
    result, _, events = collect(collectors, [geometric(known), rep, geometric(foreign)], owners)
    assert events == []
    metadata = result[1]["regularity"]
    assert result[0]["surface_index"] == metadata["surface1"]["surface_index"] == 0
    assert result[2]["surface_index"] == metadata["surface2"]["surface_index"] == 1
    assert metadata["surface1"]["owner_roles"] == ("side.line.ra", "alias.same.handle")
    assert metadata["surface2"]["owner_roles"] == ()
    assert metadata["surface1"]["surface_fields"] == metadata["surface2"]["surface_fields"]


def test_duplicate_owner_slots_stay_explicit_for_detached_rejection(collectors):
    surface = Surface()
    result, _, events = collect(
        collectors,
        [Representation(surface, surface)],
        {"side.line.ra": surface},
    )
    assert events == []
    metadata = result[0]["regularity"]
    assert metadata["surface1"] == metadata["surface2"]
    assert metadata["surface1"]["surface_index"] == 0
    assert metadata["surface1"]["owner_roles"] == ("side.line.ra",)


@pytest.mark.parametrize("slot", (1, 2))
@pytest.mark.parametrize("kind", (None, "Geom_BSplineSurface"))
def test_null_or_unsupported_owner_retains_raw_kind_and_prefix(collectors, slot, kind):
    pair = [Surface(), Surface()]
    pair[slot - 1] = None if kind is None else Surface(kind=kind)
    rep, events = Representation(*pair), []
    with pytest.raises(NativePlanError, match="unsupported_native_surface_metadata"):
        collect(collectors, [rep], events=events)
    raw = events[0][1]
    assert raw["unavailable_field"] == f"surface{slot}.type"
    metadata = raw["representations"][0]["regularity"]
    assert metadata[f"surface{slot}"] == {
        "surface_index": None,
        "owner_roles": (),
        "surface_fields": {"kind": kind},
    }
    assert metadata["location2"] is None and metadata["continuity_type"] is None
    if slot == 2:
        assert metadata["surface1"]["surface_index"] == 0
    else:
        assert metadata["surface2"] is None and "Surface2" not in rep.calls


@pytest.mark.parametrize("slot", (1, 2))
@pytest.mark.parametrize(
    "getter",
    (
        "DynamicType",
        "Pln",
        "Position",
        "Location",
        "XDirection",
        "YDirection",
        "Direction",
    ),
)
def test_each_owner_field_failure_preserves_completed_slots(collectors, slot, getter):
    calls = []

    class FailingSurface(Surface):
        pass

    def fail(self):
        calls.append(getter)
        raise GetterFailure(f"unavailable surface {getter}")

    setattr(FailingSurface, getter, fail)
    pair = [Surface(), Surface()]
    pair[slot - 1] = FailingSurface()
    rep, events = Representation(*pair), []
    with pytest.raises(GetterFailure, match=f"unavailable surface {getter}"):
        collect(collectors, [rep], events=events)
    assert calls == [getter]
    raw = events[0][1]
    expected_field = "type" if getter == "DynamicType" else "fields"
    assert raw["unavailable_field"] == f"surface{slot}.{expected_field}"
    metadata = raw["representations"][0]["regularity"]
    partial = metadata[f"surface{slot}"]
    assert partial["surface_index"] is None and partial["owner_roles"] == ()
    assert partial["surface_fields"] == (
        None
        if getter == "DynamicType"
        else {
            "kind": "Geom_Plane",
        }
    )
    assert metadata["location2"] is None and metadata["continuity_type"] is None
    if slot == 2:
        assert metadata["surface1"]["surface_fields"] == owner_fields(pair[0])
    else:
        assert metadata["surface2"] is None
    assert not set(rep.calls) & {"Location2", "Continuity", "enum.int"}


@pytest.mark.parametrize("getter", ("Transformation", "IsIdentity", "Value"))
def test_each_second_location_failure_retains_both_owners(collectors, getter):
    calls = []

    class FailingLocation(Location):
        pass

    def fail(self, *args):
        calls.append(getter)
        raise GetterFailure(f"unavailable location {getter}")

    setattr(FailingLocation, getter, fail)
    rep = Representation(Surface(), Surface(), location2=FailingLocation())
    events = []
    with pytest.raises(GetterFailure, match=f"unavailable location {getter}"):
        collect(collectors, [rep], events=events)
    assert calls == [getter]
    raw = events[0][1]
    assert raw["unavailable_field"] == "location2"
    metadata = raw["representations"][0]["regularity"]
    assert metadata["surface1"] is not None and metadata["surface2"] is not None
    assert metadata["location2"] is None and metadata["continuity_type"] is None
    assert not set(rep.calls) & {"Continuity", "enum.int"}


@pytest.mark.parametrize("kind", (StringSubclass("Geom_Plane"), EqualityPoison()))
def test_surface_kind_exact_string_precedes_equality_and_field_getters(collectors, kind):
    class PoisonSurface(Surface):
        def Pln(self):
            raise AssertionError("wrong type metadata must reject before field getter")

    rep, events = Representation(PoisonSurface(kind=kind), Surface()), []
    with pytest.raises(NativePlanError, match="unsupported_native_surface_metadata"):
        collect(collectors, [rep], events=events)
    assert events[0][1]["unavailable_field"] == "surface1.type"
    assert "Surface2" not in rep.calls


def test_nonidentity_record_placements_are_recorded_without_silent_repair(collectors):
    matrix = ((1.0, 0.0, 0.0, 3.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))
    first, second = Location(IDENTITY, identity=False), Location(matrix, identity=False)
    rep = Representation(Surface(), Surface(), location=first, location2=second)
    result, _, _ = collect(collectors, [rep])
    assert result[0]["location"] == {"identity": False, "matrix": IDENTITY}
    assert result[0]["regularity"]["location2"] == {"identity": False, "matrix": matrix}
    assert rep.location is first and rep.location2 is second


def test_historical_snapshot8_source_and_ocpkernel_methods_are_exact():
    raw = _assembly_step_bytes(historical_runtime_root(), "src/mechanical_cad/kernel_ocp.py")
    lines = raw.splitlines(keepends=True)
    kept = []
    for node in ast.parse(raw).body:
        start = min(
            [node.lineno, *[decorator.lineno for decorator in getattr(node, "decorator_list", [])]]
        )
        span = b"".join(lines[start - 1 : node.end_lineno])
        if isinstance(node, ast.ClassDef) and node.name == "OCPKernel":
            assert hashlib.sha256(span).hexdigest() == SNAPSHOT8_CLASS_SHA256
        if isinstance(node, ast.FunctionDef) and node.name in {
            "_curve_profile_generated_inventory",
            "_curve_profile_generated_regularity_record",
            "_curve_profile_regularity_type_record",
        }:
            continue
        kept.append(span)
    assert hashlib.sha256(b"\0".join(kept)).hexdigest() == SNAPSHOT8_UNCHANGED_NODES_SHA256
