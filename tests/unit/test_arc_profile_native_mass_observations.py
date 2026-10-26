"""Synthetic-only raw mass diagnostics; these tests do not qualify native geometry.

Only the mass tail, existing event collector and exception handler are extracted
from the real kernel. All geometry/registration bindings are explicit doubles;
the pure mass checker and bounded evidence encoder remain real and unchanged.
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
from test_arc_profile_native_end_cap import _assembly_step_bytes

from mechanical_cad.arc_profile_native_evidence import (
    bounded_evidence_bytes,
    check_masses,
    mass_check_record,
)
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
EVIDENCE = ROOT / "src/mechanical_cad/arc_profile_native_evidence.py"
METHODS = ("sector_profile", "extrude_sector")
AREA = math.pi * 25.0 / 4.0
HEIGHT = 7.0
RAW_FACE = b'            event("raw_face_empirical_area", {"area": area})\n'
RAW_PRISM = (
    b"            event(\n"
    b'                "raw_prism_empirical_masses",\n'
    b'                {"area": state.area, "height": height, "volume": volume},\n'
    b"            )\n"
)
# Recorded from revised_pure_snapshot5/source, not read from an external checkout
# at test time. Exact reviewed vertex hunks, radial-range substitutions and the
# two raw statements are inverted; every untouched old byte remains observable.
SNAPSHOT5_KERNEL = "b3ec010510819043ecf6563a08d311985752d6b73610bb37f52d55d76903d9c9"
SNAPSHOT5_EVIDENCE = "6c4eda77118b6a9e7ea31a12b4720741bc9575094f08c54ad7fbc43a0a3363be"


class NoNativeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"OCP", "OCC", "cadquery", "slvs", "bpy"}:
            raise AssertionError(f"native import forbidden: {fullname}")
        if fullname == "mechanical_cad.kernel_ocp":
            raise AssertionError("extract the mass statements; never import the native kernel")
        return None


@pytest.fixture(autouse=True)
def no_native_imports():
    blocker = NoNativeImports()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


@pytest.fixture(scope="module")
def plan():
    source = SectorGeometrySource(
        (SectorPoint("c", 0.0, 0.0), SectorPoint("a", 5.0, 0.0), SectorPoint("b", 0.0, 5.0)),
        (SectorLine("ra", "c", "a"), SectorLine("rb", "c", "b")),
        (SectorArc("arc", "c", "a", "b", "ccw"),),
    )
    context = entry_context()
    prepared = prepare_native_geometry(source, NativePlane(), context=context)
    directions = tuple(
        NativeRadialDirection(line.entity_id, transform(prepared.frame, line.direction))
        for line in prepared.lines
    )
    return _continue_actual_support(prepared, directions, context)


def context_with_prior_work():
    context = PrimitiveContext()
    context._make(7, 0)
    assert context.operations > 0
    return context


def kernel_method(name):
    kernel = next(
        node
        for node in ast.parse(KERNEL.read_bytes()).body
        if isinstance(node, ast.ClassDef) and node.name == "OCPKernel"
    )
    return next(
        node for node in kernel.body if isinstance(node, ast.FunctionDef) and node.name == name
    )


def assigned(node, name):
    return isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == name for target in node.targets
    )


def call_name(node):
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def mass_tail(name):
    """Keep the real collector, complete postmeasurement tail and failure handler."""
    method = kernel_method(name)
    event = next(
        node for node in method.body if isinstance(node, ast.FunctionDef) and node.name == "event"
    )
    block = next(node for node in method.body if isinstance(node, ast.Try))
    start = next(
        index
        for index, node in enumerate(block.body)
        if assigned(node, "mass" if name == "sector_profile" else "volume")
    )
    block.body = block.body[start:]
    method.name = "run_mass_tail"
    method.args = ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[])
    method.body = [event, block]
    classes = [
        node
        for node in ast.parse(KERNEL.read_bytes()).body
        if isinstance(node, ast.ClassDef) and node.name in {"KernelError", "_CurveProfileError"}
    ]
    module = ast.fix_missing_locations(ast.Module(body=[*classes, method], type_ignores=[]))
    return compile(module, str(KERNEL), "exec")


class MassTailHarness:
    def __init__(self, name, plan, *, area=AREA, volume=AREA * HEIGHT):
        self.name, self.area, self.volume = name, area, volume
        self.context = context_with_prior_work()
        self.start = self.context.operations
        self.record = {"operation": "curve_profile", "operations_start": self.start, "events": []}
        self.trace, self.sent, self.calls, self.failures, self.publications = [], [], [], [], []
        self.registered_states = []
        self.profile, self.shape = object(), object()
        # The extracted tail starts after the genuine mapping/trace gates. These
        # inert tokens test retention identity, not geometry or native authority.
        self.representatives, self.continuation = object(), object()
        self.retained_circle = object()
        self.representative_points = (object(), object())
        self.owner = SimpleNamespace(_remember=self.remember)
        state = SimpleNamespace(
            source=object(),
            vertices={},
            edges={},
            surface=object(),
            area=area,
            representatives=self.representatives,
            representative_continuation=self.continuation,
            circle=self.retained_circle,
            representative_points=self.representative_points,
        )
        self.states = {id(self.profile): state}
        self.namespace = {
            "self": self.owner,
            "plan": plan,
            "c": self.context,
            "evidence": self.record,
            "evidence_sink": self.sink,
            "bounded_evidence_bytes": bounded_evidence_bytes,
            "check_masses": self.check,
            "mass_check_record": mass_check_record,
            "GProp_GProps": self.mass_properties,
            "BRepGProp": SimpleNamespace(SurfaceProperties_s=self.surface_properties),
            "_exact_volume": self.exact_volume,
            "_CurveProfileState": self.make_state,
            "_Operation": lambda *args, **kwargs: (args, kwargs),
            "face": self.profile,
            "profile": self.profile,
            "shape": self.shape,
            "height": HEIGHT,
            "state": state,
            "states": self.states,
            "certificate": state.source,
            "vertices": state.vertices,
            "edges": state.edges,
            "surface": state.surface,
            "expected": {},
            "wire": object(),
            "builder": object(),
            "representatives": self.representatives,
            "continuation": self.continuation,
            "retained_circle": self.retained_circle,
            "representative_points": self.representative_points,
        }
        exec(mass_tail(name), self.namespace)
        self.error = self.namespace["_CurveProfileError"]

    def mass_properties(self):
        self.trace.append("mass_properties")
        return SimpleNamespace(Mass=self.mass)

    def surface_properties(self, face, mass):
        assert face is self.profile and callable(mass.Mass)
        self.trace.append("area_integration")

    def mass(self):
        self.trace.append("area_measurement")
        return self.area

    def exact_volume(self, shape):
        assert shape is self.shape
        self.trace.append("volume_integration")
        return self.volume

    def sink(self, item):
        self.trace.append(item["stage"])
        self.sent.append(item)

    def check(self, *args, **kwargs):
        self.trace.append("check_masses")
        self.calls.append((args, kwargs))
        try:
            return check_masses(*args, **kwargs)
        except Exception as exc:
            self.failures.append(exc)
            raise

    def make_state(self, *args):
        self.trace.append("state_registration")
        assert args[3] is self.context and args[8] is self.record
        state = SimpleNamespace(shape=args[0], context=args[3], evidence=args[8])
        self.registered_states.append(state)
        return state

    def remember(self, operation):
        self.trace.append("operation_registration")
        self.publications.append(operation)

    def run(self):
        return self.namespace["run_mass_tail"]()

    @property
    def stages(self):
        if self.name == "sector_profile":
            return "raw_face_empirical_area", "face_empirical_area"
        return "raw_prism_empirical_masses", "prism_empirical_masses"

    @property
    def raw_value(self):
        if self.name == "sector_profile":
            return {"area": self.area}
        return {"area": self.area, "height": HEIGHT, "volume": self.volume}

    def assert_one_measurement(self):
        assert self.trace.count("area_measurement") == int(self.name == "sector_profile")
        assert self.trace.count("area_integration") == int(self.name == "sector_profile")
        assert self.trace.count("volume_integration") == int(self.name == "extrude_sector")

    def assert_unpublished(self):
        assert not self.publications
        assert not self.registered_states
        assert "state_registration" not in self.trace
        assert not hasattr(self.owner, "_curve_profile_states")
        assert set(self.states) == {id(self.profile)}


@pytest.mark.parametrize("name", METHODS)
def test_measurement_raw_event_checker_and_success_order_is_exact(name):
    method = kernel_method(name)
    block = next(node for node in method.body if isinstance(node, ast.Try))
    index = next(
        i
        for i, node in enumerate(block.body)
        if assigned(node, "area" if name == METHODS[0] else "volume")
    )
    expected = (
        [
            "area = mass.Mass()",
            "event('raw_face_empirical_area', {'area': area})",
            "area_check = check_masses(plan, area, context=c)",
        ]
        if name == "sector_profile"
        else [
            "volume = _exact_volume(shape)",
            "event('raw_prism_empirical_masses', {'area': state.area, 'height': height, 'volume': volume})",
            "mass_check = check_masses(plan, state.area, context=c, height=height, volume=volume)",
        ]
    )
    assert [ast.unparse(node) for node in block.body[index : index + 3]] == expected
    success = block.body[index + 3].value
    assert call_name(success) == "event"
    assert success.args[0].value == (
        "face_empirical_area" if name == "sector_profile" else "prism_empirical_masses"
    )
    calls = [call_name(node) for node in ast.walk(method) if isinstance(node, ast.Call)]
    assert calls.count("check_masses") == 1
    assert calls.count("Mass") == calls.count("SurfaceProperties_s") == int(name == METHODS[0])
    assert calls.count("_exact_volume") == int(name == METHODS[1])


@pytest.mark.parametrize(
    ("name", "area", "volume", "code"),
    [
        ("sector_profile", AREA + 0.001, AREA * HEIGHT, "native_area_r0_failure"),
        ("sector_profile", -1.0, AREA * HEIGHT, "native_nonpositive_mass"),
        ("extrude_sector", AREA, AREA * HEIGHT + 0.001, "native_volume_r0_failure"),
        ("extrude_sector", AREA + 0.001, AREA * HEIGHT, "native_area_r0_failure"),
        ("extrude_sector", AREA, -1.0, "native_nonpositive_mass"),
    ],
)
def test_real_rejection_retains_raw_observation_original_failure_and_counter(
    plan, name, area, volume, code
):
    harness = MassTailHarness(name, plan, area=area, volume=volume)
    reference = context_with_prior_work()
    extra = {} if name == "sector_profile" else {"height": HEIGHT, "volume": volume}
    with pytest.raises(NativePlanError, match=code) as original:
        check_masses(plan, area, context=reference, **extra)
    with pytest.raises(harness.error, match=code) as caught:
        harness.run()
    assert caught.value.__cause__ is harness.failures[0]
    assert caught.value.evidence is harness.record
    assert harness.record["failure"] == {
        "code": code,
        "type": type(original.value).__name__,
        "message": str(original.value),
    }
    assert harness.context.operations == reference.operations
    assert harness.record["operations_end"] == reference.operations
    raw = {"stage": harness.stages[0], "value": harness.raw_value, "operations": harness.start}
    assert harness.record["events"] == [
        raw,
        {
            "stage": "failure",
            "value": harness.record["failure"],
            "operations": reference.operations,
        },
    ]
    assert harness.sent == harness.record["events"]
    assert harness.trace.index(harness.stages[0]) < harness.trace.index("check_masses")
    assert harness.stages[1] not in harness.trace
    assert harness.calls == [((plan, area), {"context": harness.context, **extra})]
    harness.assert_one_measurement()
    harness.assert_unpublished()


@pytest.mark.parametrize("name", METHODS)
def test_success_evidence_is_emitted_only_after_real_mass_comparison(plan, name):
    harness = MassTailHarness(name, plan)
    assert harness.run() is (harness.profile if name == "sector_profile" else harness.shape)
    raw, checked = harness.record["events"]
    assert raw == {
        "stage": harness.stages[0],
        "value": harness.raw_value,
        "operations": harness.start,
    }
    assert all(type(value) is float for value in raw["value"].values())
    assert checked["stage"] == harness.stages[1]
    assert checked["value"]["r0_pass"] is True
    if name == "extrude_sector":
        assert checked["value"]["c0_pass"] is True
    assert checked["operations"] == harness.context.operations > harness.start
    assert harness.record["operations_end"] == harness.context.operations
    assert harness.trace.index(raw["stage"]) < harness.trace.index("check_masses")
    assert harness.trace.index("check_masses") < harness.trace.index(checked["stage"])
    assert harness.trace.index(checked["stage"]) < harness.trace.index("state_registration")
    assert harness.trace.index(checked["stage"]) < harness.trace.index("operation_registration")
    assert len(harness.publications) == len(harness.calls) == 1
    assert len(harness.registered_states) == 1
    assert harness.registered_states[0].representatives is harness.representatives
    assert harness.registered_states[0].representative_continuation is harness.continuation
    assert harness.registered_states[0].circle is harness.retained_circle
    assert harness.registered_states[0].representative_points is harness.representative_points
    assert not harness.failures and "failure" not in harness.record
    harness.assert_one_measurement()
    # The actual event collector gives its sink a detached copy, including raw values.
    harness.sent[0]["value"]["area"] = -999.0
    assert raw["value"] == harness.raw_value


@pytest.mark.parametrize("name", METHODS)
@pytest.mark.parametrize("limit", ["bytes", "events", "nonfinite"])
def test_raw_collector_failure_stops_before_comparison_and_publication(plan, name, limit):
    kwargs = {}
    if limit == "nonfinite":
        kwargs["area" if name == "sector_profile" else "volume"] = math.nan
    harness = MassTailHarness(name, plan, **kwargs)
    if limit == "bytes":
        harness.record["events"] = [{"stage": "synthetic_padding", "value": "", "operations": 0}]
        overhead = len(bounded_evidence_bytes(harness.record))
        harness.record["events"][0]["value"] = "x" * (1_048_576 - overhead)
        assert len(bounded_evidence_bytes(harness.record)) == 1_048_576
    elif limit == "events":
        harness.record["events"] = [
            {"stage": "synthetic_existing", "value": index, "operations": 0} for index in range(64)
        ]
        bounded_evidence_bytes(harness.record)
    before = copy.deepcopy(harness.record)
    code = "invalid_native_evidence" if limit == "nonfinite" else "native_evidence_limit"
    with pytest.raises(NativePlanError, match=code):
        harness.run()
    assert harness.record == before
    assert not harness.calls and not harness.sent and not harness.failures
    assert harness.context.operations == harness.start
    harness.assert_one_measurement()
    harness.assert_unpublished()


def undo_regularity_metadata_revision(data, relative):
    """Apply only exact reviewed hunks; leave every other old byte observable."""
    path = ROOT / "tests/fixtures/arc_sector/regularity_metadata_inverse.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "86b0357993ac11c4c885d1b4eaf6d78cc1adbcacd89281a1e361ffe03b3b0c9f"
    )
    fixture = json.loads(raw)
    assert fixture["schema"] == 1
    lines = data.splitlines(keepends=True)
    for hunk in reversed(fixture["files"][relative]["hunks"]):
        start = hunk["line"]
        current = hunk["current"].encode().splitlines(keepends=True)
        assert current and lines[start : start + len(current)] == current
        lines[start : start + len(current)] = hunk["historical"].encode().splitlines(keepends=True)
    return b"".join(lines)


def undo_canonical_vertex_revision(data, relative):
    """Apply only exact reviewed hunks; leave every other old byte observable."""
    path = ROOT / "tests/fixtures/arc_sector/canonical_vertex_inverse.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "0c6f93e8e6defd7398a011249ff2c7b4302798a25374a1d0194eba72a41bafae"
    )
    fixture = json.loads(raw)
    assert fixture["schema"] == 1
    lines = data.splitlines(keepends=True)
    for hunk in reversed(fixture["files"][relative]["hunks"]):
        start = hunk["line"]
        current = hunk["current"].encode().splitlines(keepends=True)
        assert current and lines[start : start + len(current)] == current
        lines[start : start + len(current)] = hunk["historical"].encode().splitlines(keepends=True)
    return b"".join(lines)


def test_vertex_inverse_rejects_an_altered_fixture(monkeypatch):
    fixture = ROOT / "tests/fixtures/arc_sector/canonical_vertex_inverse.json"
    original = Path.read_bytes
    monkeypatch.setattr(
        Path, "read_bytes", lambda path: original(path) + (b" " if path == fixture else b"")
    )
    with pytest.raises(AssertionError):
        undo_canonical_vertex_revision(KERNEL.read_bytes(), "src/mechanical_cad/kernel_ocp.py")


def test_regularity_inverse_rejects_an_altered_fixture(monkeypatch):
    fixture = ROOT / "tests/fixtures/arc_sector/regularity_metadata_inverse.json"
    original = Path.read_bytes
    monkeypatch.setattr(
        Path, "read_bytes", lambda path: original(path) + (b" " if path == fixture else b"")
    )
    with pytest.raises(AssertionError):
        undo_regularity_metadata_revision(KERNEL.read_bytes(), "src/mechanical_cad/kernel_ocp.py")


def original_kernel_bytes(data):
    data = undo_regularity_metadata_revision(data, "src/mechanical_cad/kernel_ocp.py")
    data = undo_canonical_vertex_revision(data, "src/mechanical_cad/kernel_ocp.py")
    # Undo only the two sealed radial finite-range substitutions.
    replacements = (
        (b"(curve, (0.0, line.trim_parameter), True, 3)", b"(curve, (0.0, line.length), True, 3)"),
        (
            b"                maker = BRepBuilderAPI_MakeEdge(\n                    curve,\n                    vertices[arc.center_id],\n                    vertices[line.point_id],\n                    0.0,\n                    line.trim_parameter,\n                )",
            b"                maker = BRepBuilderAPI_MakeEdge(\n                    curve, vertices[arc.center_id], vertices[line.point_id], 0.0, line.length\n                )",
        ),
    )
    for current, historical in replacements:
        assert data.count(current) == 1
        data = data.replace(current, historical)
    for statement in (RAW_FACE, RAW_PRISM):
        assert data.count(statement) == 1
        data = data.replace(statement, b"")
    return data


def test_every_original_kernel_and_mass_comparator_byte_matches_snapshot5():
    source = _assembly_step_bytes(ROOT, "src/mechanical_cad/kernel_ocp.py")
    assert hashlib.sha256(original_kernel_bytes(source)).hexdigest() == SNAPSHOT5_KERNEL
    current = undo_regularity_metadata_revision(
        EVIDENCE.read_bytes(), "src/mechanical_cad/arc_profile_native_evidence.py"
    )
    current = undo_canonical_vertex_revision(
        current, "src/mechanical_cad/arc_profile_native_evidence.py"
    )
    assert current.count(b'"range": (0.0, line.trim_parameter),') == 1
    historical = current.replace(
        b'"range": (0.0, line.trim_parameter),', b'"range": (0.0, line.length),'
    )
    assert hashlib.sha256(historical).hexdigest() == SNAPSHOT5_EVIDENCE


@pytest.mark.parametrize(
    "relative",
    ["src/mechanical_cad/kernel_ocp.py", "src/mechanical_cad/arc_profile_native_evidence.py"],
)
def test_vertex_inverse_is_exact_portable_and_rejects_every_changed_hunk(relative):
    fixture = json.loads(
        (ROOT / "tests/fixtures/arc_sector/canonical_vertex_inverse.json").read_text()
    )["files"][relative]
    current = undo_regularity_metadata_revision(_assembly_step_bytes(ROOT, relative), relative)
    assert hashlib.sha256(current).hexdigest() == fixture["current_sha256"]
    restored = undo_canonical_vertex_revision(current, relative)
    assert hashlib.sha256(restored).hexdigest() == fixture["historical_sha256"]
    lines = current.splitlines(keepends=True)
    end = 0
    for hunk in fixture["hunks"]:
        start = hunk["line"]
        assert start >= end
        expected = hunk["current"].encode().splitlines(keepends=True)
        end = start + len(expected)
        assert expected and lines[start:end] == expected
        altered = list(lines)
        altered[start] = b"# changed reviewed hunk: " + altered[start]
        with pytest.raises(AssertionError):
            undo_canonical_vertex_revision(b"".join(altered), relative)


@pytest.mark.parametrize(
    "relative",
    ["src/mechanical_cad/kernel_ocp.py", "src/mechanical_cad/arc_profile_native_evidence.py"],
)
def test_regularity_inverse_is_exact_portable_and_rejects_every_changed_hunk(relative):
    fixture = json.loads(
        (ROOT / "tests/fixtures/arc_sector/regularity_metadata_inverse.json").read_text()
    )["files"][relative]
    current = _assembly_step_bytes(ROOT, relative)
    assert hashlib.sha256(current).hexdigest() == fixture["current_sha256"]
    restored = undo_regularity_metadata_revision(current, relative)
    assert hashlib.sha256(restored).hexdigest() == fixture["historical_sha256"]
    lines = current.splitlines(keepends=True)
    end = 0
    for hunk in fixture["hunks"]:
        start = hunk["line"]
        assert start >= end
        expected = hunk["current"].encode().splitlines(keepends=True)
        end = start + len(expected)
        assert expected and lines[start:end] == expected
        altered = list(lines)
        altered[start] = b"# changed reviewed hunk: " + altered[start]
        with pytest.raises(AssertionError):
            undo_regularity_metadata_revision(b"".join(altered), relative)


@pytest.mark.parametrize("statement", [RAW_FACE, RAW_PRISM])
def test_byte_guard_rejects_missing_duplicate_or_enlarged_raw_observations(statement):
    source = _assembly_step_bytes(ROOT, "src/mechanical_cad/kernel_ocp.py")
    for replacement in (
        b"",
        statement * 2,
        statement.replace(b'"area":', b'"r0_pass": True, "area":'),
    ):
        with pytest.raises(AssertionError):
            original_kernel_bytes(source.replace(statement, replacement))


def test_byte_guard_preserves_comparator_registration_and_existing_diagnostics():
    # Restore the exact reviewed parent before exercising its original mutations.
    source = _assembly_step_bytes(ROOT, "src/mechanical_cad/kernel_ocp.py")
    for old, new in (
        (b"area_check = check_masses(plan, area, context=c)", b"area_check = None"),
        (b"context=c, height=height, volume=volume", b"context=c, height=height, volume=0.0"),
        (b'event("failure", evidence["failure"])', b'event("failure", {})'),
        (b'evidence["operations_end"] = c.operations', b'evidence["operations_end"] = 0'),
        (b"self._remember(", b"self._unexpected_publication("),
    ):
        assert old in source
        changed = original_kernel_bytes(source.replace(old, new, 1))
        assert hashlib.sha256(changed).hexdigest() != SNAPSHOT5_KERNEL
