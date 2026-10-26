"""Fresh reconstruction contracts; all geometry/solver ports here are synthetic.

These tests establish protocol and atomic-action behavior, never native geometry.
Current typed-graph admission is independent of solved solid readiness.
"""

from __future__ import annotations

import copy
import importlib
import math
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_geometry3_dispatch import recovered_69d0_sidecar

from mechanical_cad import actions, backend_contract, geometry_protocol_v3, sidecar
from mechanical_cad.errors import CADException
from mechanical_cad.geometry_policy_v3 import validate_geometry_v3
from mechanical_cad.model import Document, Feature
from mechanical_cad.outputs import SolidOutput
from mechanical_cad.part_snapshot import input_fingerprint
from mechanical_cad.sketch_model import Arc, Circle, Line, Plane, Point, SketchDefinition

ROOT = Path(__file__).resolve().parents[2]
CAPABILITY = "mcad.geometry-result/3"
COMPANIONS = frozenset(
    {"mcad.solver-dof-cycle-guard/1", "mcad.sketch-arcs/1", "mcad.part-result/3"}
)


@pytest.fixture(autouse=True)
def forbid_native_imports(monkeypatch):
    class NoNative:
        def find_spec(self, fullname, *_args):
            if {"OCP", "OCC", "cadquery", "slvs", "bpy", "kernel_ocp"}.intersection(
                fullname.split(".")
            ):
                pytest.fail("Pure geometry3 contracts attempted native import: " + fullname)

    monkeypatch.setattr(sys, "meta_path", [NoNative(), *sys.meta_path])


def source(*, sketch=None, height=10):
    sketch = sketch or SketchDefinition(
        "sector",
        (Point("center", 0, 0), Point("start", 5, 0), Point("end", 0, 5)),
        (Line("radial_start", "center", "start"), Line("radial_end", "end", "center")),
        (),
        schema_version=3,
        arcs=(Arc("rim", "center", "start", "end", "ccw"),),
    )
    profile = Feature("profile", "sketch_constrained", "Sector", sketch=sketch)
    pad = Feature("pad", "extrude", "Pad", {"length": height}, {"profile": "profile"})
    return Document(
        "part", "Geometry3 contracts", {"height": 7}, (profile, pad), "pad", schema_version=2
    )


def request(action="check_geometry", *, document=None, destination="./out//part.step"):
    operation = {
        "protocol_version": 1,
        "result_version": 3,
        "action": action,
        "document": (document or source()).to_dict(),
    }
    if action in actions.EXPORT_ACTIONS:
        operation["destination"] = destination
    return operation


def replay(document, *, okay=True):
    shape = object()
    return SimpleNamespace(
        ok=okay,
        result={
            "status": "ok" if okay else "failed",
            "document_hash": document.content_hash,
            "active_feature": "pad",
            "features": [
                {"id": "profile", "sketch": {"remaining_dof": 6}},
                {"id": "pad", "stats": {"solids": 1, "valid": True, "volume": 1.0}},
            ],
        },
        shapes={"pad": shape},
        outputs={"pad": SolidOutput(shape)},
    )


class RecordingKernel:
    """Synthetic writer records the actual shape received from this invocation."""

    def __init__(self, *, failure=None):
        self.calls = []
        self.failure = failure
        self.checks = {"synthetic": "base-checks"}

    def manufacturing_check(self, shape, *, linear_deflection):
        self.calls.append(("check", shape, linear_deflection))
        if self.failure == "check":
            raise RuntimeError("synthetic check failure")
        return self.checks

    def export_step(self, shape, path):
        self.calls.append(("step", shape, path))
        if self.failure == "empty":
            return
        path.write_bytes(b"synthetic STEP, not geometry")
        if self.failure == "write":
            raise RuntimeError("synthetic writer failure after partial write")
        if self.failure == "io":
            raise OSError("synthetic writer I/O failure")

    def export_stl(self, shape, path, *, linear_deflection):
        self.calls.append(("stl", shape, path, linear_deflection))
        self.export_step(shape, path)
        return {"synthetic": "encoded-checks"}


@pytest.mark.parametrize("version", [None, True, False, 1, 2, 3.0, "3", 4])
def test_policy_requires_exact_explicit_integer_three(version):
    with pytest.raises(CADException, match="requires result_version 3"):
        validate_geometry_v3(source(), version)


@pytest.mark.parametrize("height", [1, 1000, "height", "height + 1"])
def test_policy_composes_replay_height_and_preserves_source(height):
    document = source(height=height)
    before = document.to_json()
    validate_geometry_v3(document, 3)
    assert document.to_json() == before


@pytest.mark.parametrize("height", [0, -1, math.nextafter(1, 0), math.nextafter(1000, math.inf)])
def test_policy_retains_replay_height_bounds(height):
    with pytest.raises(CADException) as error:
        validate_geometry_v3(source(height=height), 3)
    assert error.value.code == "unsupported_profile_scale"


@pytest.mark.parametrize(
    "active,code", [(None, "missing_active_feature"), ("profile", "not_a_solid")]
)
def test_selected_profile_is_never_geometry_output(active, code):
    with pytest.raises(CADException) as error:
        validate_geometry_v3(replace(source(), active_feature=active), 3)
    assert error.value.code == code


def test_profile_only_rejects_but_connected_branches_are_structurally_admitted():
    document = source()
    alternatives = (
        replace(document, features=document.features[:1], active_feature="profile"),
        replace(
            document,
            features=document.features
            + (Feature("other", "sketch_circle", "Other", {"radius": 2}),),
        ),
        replace(
            document,
            features=document.features
            + (Feature("pad2", "extrude", "Pad2", {"length": 2}, {"profile": "profile"}),),
        ),
    )
    with pytest.raises(CADException) as error:
        validate_geometry_v3(alternatives[0], 3)
    assert error.value.code == "not_a_solid"
    for alternative in alternatives[1:]:
        before = alternative.to_json()
        validate_geometry_v3(alternative, 3)
        assert alternative.to_json() == before
        # Admission does not generate replay, B-rep or valid solid evidence.


@pytest.mark.parametrize("variant", ["empty", "legacy", "two_arcs", "circle", "chord", "alias"])
def test_general_typed_sketch_intent_is_admitted_without_inventing_a_sector(variant):
    sketch = source().features[0].sketch
    if variant in {"empty", "legacy"}:
        sketch = replace(sketch, arcs=(), schema_version=2 if variant == "legacy" else 3)
    elif variant == "two_arcs":
        sketch = replace(sketch, arcs=sketch.arcs + (replace(sketch.arcs[0], id="second"),))
    elif variant == "circle":
        sketch = replace(sketch, circles=(Circle("circle", "center", 2),))
    elif variant == "chord":
        sketch = replace(sketch, lines=(Line("chord", "start", "end"), sketch.lines[1]))
    else:
        sketch = replace(
            sketch,
            points=sketch.points + (Point("alias", 5, 0),),
            lines=(replace(sketch.lines[0], end="alias"), sketch.lines[1]),
        )
    document = source(sketch=sketch)
    before = document.to_json()
    validate_geometry_v3(document, 3)
    assert document.to_json() == before


@pytest.mark.parametrize("direction", ["cw", "ccw"])
def test_radial_orientation_unused_points_and_unconstrained_source_remain_allowed(direction):
    sketch = source().features[0].sketch
    sketch = replace(
        sketch,
        arcs=(replace(sketch.arcs[0], direction=direction),),
        lines=tuple(replace(line, start=line.end, end=line.start) for line in sketch.lines),
        points=sketch.points + (Point("unused", 10, 20),),
    )
    assert sketch.constraints == ()
    validate_geometry_v3(source(sketch=sketch), 3)


@pytest.mark.parametrize(
    "plane",
    [
        Plane(origin=(1, 0, 0)),
        Plane(origin=(0, 0, math.nextafter(0, 1))),
        Plane(quaternion=(-1, 0, 0, 0)),
        Plane(quaternion=(1, 0, 0, 1e-15)),
        Plane(quaternion=(0.5, 0.5, 0.5, 0.5)),
    ],
)
def test_authored_general_frames_are_preserved_without_source_normalization(plane):
    sketch = replace(source().features[0].sketch, plane=plane)
    document = source(sketch=sketch)
    before = document.to_json()
    validate_geometry_v3(document, 3)
    assert document.to_json() == before
    assert document.features[0].sketch.plane == plane


@pytest.mark.parametrize(
    "mutation", ["duplicate_feature", "missing_endpoint", "feature_cycle", "unknown_kind"]
)
def test_general_geometry_source_still_rejects_invalid_graphs_before_native(mutation):
    raw = source().to_dict()
    if mutation == "duplicate_feature":
        raw["features"].append(copy.deepcopy(raw["features"][0]))
    elif mutation == "missing_endpoint":
        raw["features"][0]["sketch"]["arcs"][0]["end"] = "missing"
    elif mutation == "feature_cycle":
        raw["features"][1]["inputs"]["profile"] = "pad"
    else:
        raw["features"][1]["kind"] = "unknown_solid"
    before = copy.deepcopy(raw)
    with pytest.raises(CADException):
        validate_geometry_v3(Document.from_dict(raw), 3)
    assert raw == before


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol_version": True},
        {"protocol_version": 1.0},
        {"protocol_version": 2},
        {"result_version": True},
        {"result_version": 3.0},
        {"result_version": 2},
        {"action": "replay"},
        {"action": "canonical_snapshot"},
        {"action": "assembly_check"},
        {"action": []},
        {"kind": "assembly"},
        {"destination": None},
        {"extra": 1},
        {"options": None},
        {"options": []},
        {"options": {"unknown": 1}},
        {"options": {"linear_deflection": True}},
        {"options": {"linear_deflection": 0}},
        {"options": {"linear_deflection": 11}},
    ],
)
def test_protocol_rejects_before_model_or_action(monkeypatch, changes):
    monkeypatch.setattr(geometry_protocol_v3.Document, "from_dict", lambda _: pytest.fail("parsed"))
    monkeypatch.setattr(
        geometry_protocol_v3, "run_geometry_action", lambda *_a, **_k: pytest.fail("ran")
    )
    with pytest.raises(CADException):
        geometry_protocol_v3.process_geometry_request_v3({**request(), **changes})


@pytest.mark.parametrize("missing", ["protocol_version", "result_version", "action", "document"])
def test_request_fields_are_never_inferred(missing):
    operation = request()
    operation.pop(missing)
    with pytest.raises(CADException):
        geometry_protocol_v3.process_geometry_request_v3(operation)


@pytest.mark.parametrize("value", [None, [], True, 3])
def test_request_is_exact_object(value):
    with pytest.raises(CADException) as error:
        geometry_protocol_v3.process_geometry_request_v3(value)
    assert error.value.code == "invalid_request"


@pytest.mark.parametrize("variant", ["cycle", "dag", "deep", "nan", "large", "integer"])
def test_budgets_precede_model_and_action(monkeypatch, variant):
    operation = request()
    if variant == "cycle":
        operation["probe"] = operation
    elif variant == "dag":
        shared = [0]
        for _ in range(24):
            shared = [shared, shared]
        operation["probe"] = shared
    elif variant == "deep":
        deep = 0
        for _ in range(40):
            deep = [deep]
        operation["probe"] = deep
    else:
        operation["probe"] = {
            "nan": math.nan,
            "large": "x" * (2 * 1024 * 1024),
            "integer": 10**200,
        }[variant]
    monkeypatch.setattr(geometry_protocol_v3.Document, "from_dict", lambda _: pytest.fail("parsed"))
    with pytest.raises(CADException) as error:
        geometry_protocol_v3.process_geometry_request_v3(operation)
    assert error.value.code in {"invalid_json", "document_too_large", "resource_limit"}


@pytest.mark.parametrize(
    "destination", [None, True, 1, "", " ", "\0", "/", ".", "..", "out/", "out/.", "out/.."]
)
def test_export_destination_precedes_replay(monkeypatch, destination):
    operation = request("export_step", destination=destination)
    monkeypatch.setattr(geometry_protocol_v3.Document, "from_dict", lambda _: pytest.fail("parsed"))
    with pytest.raises(CADException) as error:
        geometry_protocol_v3.process_geometry_request_v3(operation)
    assert error.value.code == "invalid_destination"


@pytest.mark.parametrize("action", sorted(actions.GEOMETRY_ACTIONS))
def test_action_uses_fresh_replay_once_same_shape_and_exact_wire_binding(
    monkeypatch, tmp_path, action
):
    destination = str(tmp_path) + "/./part.step"
    operation = request(action, destination=destination)
    before, calls = copy.deepcopy(operation), []

    def regenerate(document, kernel, **options):
        assert options == {"linear_deflection": 0.1, "result_version": 3}
        result = replay(document)
        calls.append(result)
        return result

    monkeypatch.setattr(actions, "regenerate", regenerate)
    kernel = RecordingKernel()
    response = geometry_protocol_v3.process_geometry_request_v3(operation, kernel=kernel)
    assert operation == before and len(calls) == 1
    assert response["ok"] is True and response["error"] is None
    assert set(response) == {
        "protocol_version",
        "result_version",
        "input_fingerprint",
        "ok",
        "action",
        "result",
        "geometry_check",
        "export",
        "error",
    }
    assert response["result_version"] == 3 and response["protocol_version"] == 1
    assert response["input_fingerprint"] == input_fingerprint(operation)
    assert response["result"] is calls[0].result
    assert response["result"]["features"][0]["sketch"]["remaining_dof"] == 6
    assert all(call[1] is calls[0].shapes["pad"] for call in kernel.calls)
    if action == "check_geometry":
        assert response["export"] is None and not Path(destination).exists()
    else:
        assert response["export"]["destination"] == destination
        assert response["export"]["bytes"] == Path(destination).stat().st_size
        assert response["export"]["atomic_replace"] is True
        assert response["geometry_check"] == (
            {"synthetic": "encoded-checks"} if action == "export_stl" else kernel.checks
        )
    second = geometry_protocol_v3.process_geometry_request_v3(operation, kernel=kernel)
    assert second["ok"] and len(calls) == 2
    assert calls[0].shapes["pad"] is not calls[1].shapes["pad"]


@pytest.mark.parametrize(
    "failure,code,has_checks",
    [
        ("check", "geometry_check_failed", False),
        ("write", "export_failed", True),
        ("empty", "empty_export", True),
        ("io", "export_io_error", True),
    ],
)
@pytest.mark.parametrize("action", sorted(actions.EXPORT_ACTIONS))
def test_failures_preserve_destination_and_closed_partial_evidence(
    monkeypatch, tmp_path, failure, code, has_checks, action
):
    path = tmp_path / "preserved.step"
    path.write_bytes(b"original destination")
    monkeypatch.setattr(actions, "regenerate", lambda document, *_a, **_k: replay(document))
    response = geometry_protocol_v3.process_geometry_request_v3(
        request(action, destination=str(path)), kernel=RecordingKernel(failure=failure)
    )
    assert response["ok"] is False and response["error"]["code"] == code
    assert response["result"]["status"] == "ok" and response["export"] is None
    assert (response["geometry_check"] is not None) is has_checks
    assert path.read_bytes() == b"original destination"
    assert list(tmp_path.iterdir()) == [path]


def test_failed_replay_is_retained_without_check_or_export(monkeypatch, tmp_path):
    path = tmp_path / "preserved.stl"
    path.write_bytes(b"original")
    monkeypatch.setattr(
        actions, "regenerate", lambda document, *_a, **_k: replay(document, okay=False)
    )
    kernel = RecordingKernel()
    response = geometry_protocol_v3.process_geometry_request_v3(
        request("export_stl", destination=str(path)), kernel=kernel
    )
    assert response["error"]["code"] == "regeneration_failed"
    assert response["result"]["status"] == "failed"
    assert response["geometry_check"] is response["export"] is None
    assert kernel.calls == [] and path.read_bytes() == b"original"


@pytest.mark.parametrize(
    "exception,code",
    [(RuntimeError("broken replay"), "replay_failed"), (OSError("broken read"), "io_error")],
)
def test_replay_runtime_failure_retains_admitted_null_result(monkeypatch, exception, code):
    def fail(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr(actions, "regenerate", fail)
    response = geometry_protocol_v3.process_geometry_request_v3(request(), kernel=RecordingKernel())
    assert response["error"]["code"] == code and response["result_version"] == 3
    assert response["result"] is response["geometry_check"] is response["export"] is None


@pytest.mark.parametrize("port", ["fsync", "replace"])
def test_atomic_flush_and_replace_failure_preserve_destination(monkeypatch, tmp_path, port):
    destination = tmp_path / "preserved.step"
    destination.write_bytes(b"original")
    monkeypatch.setattr(actions, "regenerate", lambda document, *_a, **_k: replay(document))

    def fail(*_args):
        raise OSError("synthetic atomic " + port + " failure")

    monkeypatch.setattr(actions.os, port, fail)
    response = geometry_protocol_v3.process_geometry_request_v3(
        request("export_step", destination=str(destination)), kernel=RecordingKernel()
    )
    assert response["error"]["code"] == "export_io_error" and response["export"] is None
    assert response["geometry_check"] is not None
    assert destination.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [destination]


def test_real_replay_control_flow_retains_nonzero_dof_and_original_schema(monkeypatch):
    from mechanical_cad import profile_adapter_v3
    from mechanical_cad.sketch_model import resolve_sketch

    document = source()
    solved = resolve_sketch(document.features[0].sketch, {})
    evidence = {"remaining_dof": 6, "solved": solved.to_dict()}
    report = SimpleNamespace(success=True, sketch=solved)
    evaluations = []

    def evaluate(*args):
        evaluations.append(args)
        return report, evidence

    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluate)

    class ReplayKernel(RecordingKernel):
        def sector_profile(self, sketch):
            assert sketch is solved
            return "profile-shape"

        def extrude_sector(self, profile, length):
            assert profile == "profile-shape" and length == 10
            return "solid-shape"

        def topology(self, *_args):
            return []

        def inspect(self, shape):
            assert shape == "solid-shape"
            return {"solids": 1, "valid": True, "volume": 1.0}

        def tessellate(self, *_args, **_kwargs):
            return {"vertices": [], "triangles": []}

    response = geometry_protocol_v3.process_geometry_request_v3(request(), kernel=ReplayKernel())
    assert response["ok"] and response["result"]["result_version"] == 3
    assert len(evaluations) == 1
    assert response["result"]["features"][0]["sketch"] is evidence
    assert evidence["remaining_dof"] == 6 and evidence["solved"]["schema_version"] == 3
    assert response["result"]["features"][1]["output"]["kind"] == "solid"


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_action_keeps_path_projection_and_result_stamping(monkeypatch, tmp_path, version):
    document = Document(
        "legacy",
        "Legacy",
        {},
        (
            Feature("profile", "sketch_circle", "Circle", {"radius": 2}),
            Feature("pad", "extrude", "Pad", {"length": 10}, {"profile": "profile"}),
        ),
        "pad",
    )
    monkeypatch.setattr(actions, "regenerate", lambda document, *_a, **_k: replay(document))
    destination = str(tmp_path) + "/./legacy.step"
    response = actions.run_geometry_action(
        document,
        "export_step",
        destination=destination,
        kernel=RecordingKernel(),
        result_version=version,
    )
    assert response["ok"] and response["export"]["destination"] == str(Path(destination))
    assert ("result_version" in response) is (version == 2)
    if version == 2:
        assert response["result_version"] == 2


@pytest.mark.parametrize("document", [None, replace(source(), active_feature="profile")])
def test_direct_action_preflight_never_replays_invalid_source(monkeypatch, document):
    monkeypatch.setattr(actions, "regenerate", lambda *_a, **_k: pytest.fail("replayed"))
    response = actions.run_geometry_action(document, "check_geometry", result_version=3)
    assert not response["ok"] and response["result"] is None
    assert response["error"]["code"] in {"invalid_document", "not_a_solid"}


def activate_markers(monkeypatch):
    for module in (actions, geometry_protocol_v3):
        monkeypatch.setattr(module, "BACKEND_CAPABILITIES", frozenset({CAPABILITY}))


def test_recovered_69d0_service_admission_was_disabled():
    historical = recovered_69d0_sidecar()
    with pytest.raises(CADException) as error:
        historical.process_request(request())
    assert error.value.code == "invalid_action"


def test_live_markers_and_explicit_missing_marker_pre_dispatch_rejection(monkeypatch):
    assert (
        actions.BACKEND_CAPABILITIES
        == geometry_protocol_v3.BACKEND_CAPABILITIES
        == frozenset({CAPABILITY})
    )
    monkeypatch.setattr(actions, "BACKEND_CAPABILITIES", frozenset())
    supported, mismatch = backend_contract._observe_geometry_v3(ROOT / "src/mechanical_cad")
    assert supported == COMPANIONS and mismatch is False
    operation = request()
    operation["backend_contract"] = {
        "version": 1,
        "request_id": "a" * 32,
        "required_capabilities": sorted(backend_contract.minimum_capabilities(operation)),
    }
    monkeypatch.chdir(ROOT)
    response = sidecar.process_request(operation)
    assert response["error"]["code"] == "backend_capability_missing"
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch"
    assert CAPABILITY in response["backend_receipt"]["missing_capabilities"]


def test_observer_requires_actual_definitions_and_all_companions(monkeypatch):
    activate_markers(monkeypatch)
    supported, mismatch = backend_contract._observe_geometry_v3(ROOT / "src/mechanical_cad")
    assert supported == COMPANIONS | {CAPABILITY} and mismatch is False


@pytest.mark.parametrize(
    "name",
    [
        "actions",
        "geometry_protocol_v3",
        "sketch_solver",
        "profile_adapter_v3",
        "sketch_protocol_v3",
    ],
)
@pytest.mark.parametrize("marker", [None, [], set(), frozenset(), frozenset({"other/1"})])
def test_copied_or_missing_companion_marker_cannot_advertise_geometry(monkeypatch, name, marker):
    activate_markers(monkeypatch)
    module = importlib.import_module("mechanical_cad." + name)
    monkeypatch.setattr(module, "BACKEND_CAPABILITIES", marker)
    supported, mismatch = backend_contract._observe_geometry_v3(ROOT / "src/mechanical_cad")
    assert CAPABILITY not in supported and mismatch is False


@pytest.mark.parametrize("name", ["actions", "geometry_protocol_v3", "profile_adapter_v3"])
def test_foreign_module_origin_fails_identity(monkeypatch, name):
    activate_markers(monkeypatch)
    module = importlib.import_module("mechanical_cad." + name)
    monkeypatch.setattr(module, "__file__", str(ROOT / "src/mechanical_cad/model.py"))
    supported, mismatch = backend_contract._observe_geometry_v3(ROOT / "src/mechanical_cad")
    assert CAPABILITY not in supported and mismatch is True


def test_importer_marker_cannot_relabel_a_foreign_action(monkeypatch):
    activate_markers(monkeypatch)
    monkeypatch.setattr(actions, "run_geometry_action", lambda *_a, **_k: None)
    monkeypatch.setattr(geometry_protocol_v3, "run_geometry_action", actions.run_geometry_action)
    supported, _ = backend_contract._observe_geometry_v3(ROOT / "src/mechanical_cad")
    assert CAPABILITY not in supported


def test_protocol_must_call_the_observed_action_function(monkeypatch):
    activate_markers(monkeypatch)
    monkeypatch.setattr(geometry_protocol_v3, "run_geometry_action", lambda *_a, **_k: None)
    supported, _ = backend_contract._observe_geometry_v3(ROOT / "src/mechanical_cad")
    assert CAPABILITY not in supported
