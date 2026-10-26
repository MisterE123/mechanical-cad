"""Exact-v3 dispatch controls with fake kernels and denied native imports."""

import builtins
import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_assembly_bridge_v3 import make as make_assembly3  # noqa: F401
from test_geometry3_dispatch import recovered_69d0_sidecar

from mechanical_cad import backend_contract as bc
from mechanical_cad import engine, profile_adapter_v3, sidecar, sketch_protocol_v3
from mechanical_cad.errors import CADException
from mechanical_cad.model import Document
from mechanical_cad.sketch_model import resolve_sketch

ROOT = Path(__file__).resolve().parents[2]
OWNERS = (
    ("profile_adapter_v3", "mcad.sketch-arcs/1"),
    ("sketch_service_v3", "mcad.solve-result/3"),
    ("sketch_protocol_v3", "mcad.part-result/3"),
)


def source():
    return Document.from_dict(
        json.loads((ROOT / "examples/sector_profile_data_only.mcad.json").read_text())
    )


def operation(action="replay"):
    request = {
        "protocol_version": 1,
        "action": action,
        "result_version": 3,
        "document": source().to_dict(),
    }
    if action == "solve_sketch":
        request["feature_id"] = "profile"
    return request


def guarded(action="replay", *, all_markers=False):
    request = operation(action)
    required = bc.minimum_capabilities(request)
    if all_markers:
        required |= {capability for _, capability in OWNERS}
    return {
        **request,
        "backend_contract": {
            "version": 1,
            "request_id": "1" * 32,
            "required_capabilities": sorted(required),
        },
    }


def evaluated(sketch, values):
    solved = resolve_sketch(sketch, values)
    return SimpleNamespace(success=True, sketch=solved), {
        "status": "okay",
        "remaining_dof": 0,
        "solved": solved.to_dict(),
    }


class FakeKernel:
    def __init__(self):
        self.calls = []

    def sector_profile(self, sketch):
        self.calls.append(("sector", sketch))
        return "profile-handle"

    def extrude_sector(self, profile, length):
        self.calls.append(("sector_extrusion", profile, length))
        return "solid-handle"

    def extrude(self, *args):
        pytest.fail("sector used legacy extrusion")

    def topology(self, *args):
        return []

    def inspect(self, shape):
        return {"solids": 1}

    def tessellate(self, *args, **kwargs):
        return {"vertices": [], "triangles": []}


def test_common_replay_loop_uses_checked_sector_methods_and_preserves_schema(monkeypatch):
    document = source()
    original = document.to_json()
    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    kernel = FakeKernel()
    replay = engine.regenerate(document, kernel, result_version=3)
    assert replay.ok and document.to_json() == original
    assert replay.result["result_version"] == 3
    profile, pad = replay.result["features"]
    assert profile["output"]["profile"] == {"state": "available", "region_kind": "curve_loop"}
    assert profile["sketch"]["solved"]["schema_version"] == 3
    assert kernel.calls[0][0] == "sector" and kernel.calls[0][1].schema_version == 3
    assert kernel.calls[1] == ("sector_extrusion", "profile-handle", 10.0)
    assert pad["output"] == {"kind": "solid", "display": "mesh"}


@pytest.mark.parametrize("stage", ["profile", "extrusion"])
@pytest.mark.parametrize(
    "code", ["unsupported_native_frame", "unsupported_native_signature", "bad code", None]
)
def test_sector_failure_preserves_solver_report_and_common_failure_algebra(
    stage, code, monkeypatch
):
    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    kernel = FakeKernel()
    failure = type(
        "_CurveProfileError", (ValueError,), {"__module__": "mechanical_cad.kernel_ocp"}
    )("native failure")
    failure.code = code

    def fail(*args):
        raise failure

    monkeypatch.setattr(kernel, "sector_profile" if stage == "profile" else "extrude_sector", fail)
    replay = engine.regenerate(source(), kernel, result_version=3)
    profile, pad = replay.result["features"]
    assert not replay.ok
    assert profile["sketch"]["status"] == "okay" and profile["sketch"]["solved"] is not None
    failed = profile if stage == "profile" else pad
    assert failed["status"] == "failed" and failed["output"] is None
    assert failed["mesh"] is None and failed["topology"] == []
    assert failed["error"]["code"] == (code if code and " " not in code else "kernel_error")
    if stage == "profile":
        assert pad["status"] == "blocked" and pad["error"]["code"] == "upstream_failed"


@pytest.mark.parametrize("version", [True, 3.0, "3", None, 4])
def test_non_exact_three_never_enters_new_engine_adapter(version, monkeypatch):
    monkeypatch.setattr(engine, "_sketch_output_v3", lambda *args: pytest.fail("v3 selected"))
    with pytest.raises(CADException) as exc:
        engine.regenerate(source(), FakeKernel(), result_version=version)
    assert exc.value.code == "unsupported_result_version"


@pytest.mark.parametrize(
    "action",
    [
        "check_geometry",
        "export_step",
        "export_stl",
        "assembly_replay",
        "assembly_check",
        "assembly_sample",
        "canonical_snapshot",
        [],
        None,
    ],
)
def test_recovered_69d0_unsupported_three_actions_reject_before_operation_import(
    action, monkeypatch
):
    historical = recovered_69d0_sidecar()
    imported = []
    original = builtins.__import__

    def checked(name, *args, **kwargs):
        imported.append(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", checked)
    with pytest.raises(CADException) as exc:
        historical.process_request({**operation(), "action": action})
    assert exc.value.code == "invalid_action"
    assert not {"sketch_protocol_v3", "assembly_protocol", "actions", "kernel_ocp"}.intersection(
        imported
    )


@pytest.mark.parametrize("action", ["replay", "solve_sketch"])
def test_exact_three_dispatch_calls_only_new_protocol_once(action, monkeypatch):
    request = operation(action)
    seen = []
    name = "process_sketch_request_v3" if action == "solve_sketch" else "process_replay_request_v3"
    monkeypatch.setattr(
        sketch_protocol_v3, name, lambda value: seen.append(value) or {"sentinel": 3}
    )
    assert sidecar.process_request(request) == {"sentinel": 3}
    assert seen == [request] and seen[0] is request


@pytest.mark.parametrize("owner,capability", OWNERS)
@pytest.mark.parametrize("marker_kind", ["none", "list", "set", "empty", "wrong", "subclass"])
def test_each_new_marker_requires_exact_frozenset_and_own_capability(
    owner, capability, marker_kind, monkeypatch
):
    monkeypatch.chdir(ROOT)
    module = importlib.import_module("mechanical_cad." + owner)

    class Derived(frozenset):
        pass

    marker = {
        "none": None,
        "list": [capability],
        "set": {capability},
        "empty": frozenset(),
        "wrong": frozenset({"other/1"}),
        "subclass": Derived({capability}),
    }[marker_kind]
    monkeypatch.setattr(module, "BACKEND_CAPABILITIES", marker)
    response = sidecar.process_request(guarded(all_markers=True))
    assert response["error"]["code"] == "backend_capability_missing"
    assert response["backend_receipt"]["missing_capabilities"] == [capability]
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch"


@pytest.mark.parametrize("owner,capability", OWNERS)
@pytest.mark.parametrize(
    "origin_kind", ["missing", "foreign", "same_basename", "different_core_file", "import_failure"]
)
def test_marker_must_come_from_its_exact_selected_core_file(
    owner, capability, origin_kind, monkeypatch, tmp_path
):
    monkeypatch.chdir(ROOT)
    foreign = tmp_path / (owner + ".py")
    foreign.write_text("# foreign module\n")
    origin = {
        "missing": None,
        "foreign": str(ROOT / "README.md"),
        "same_basename": str(foreign),
        "different_core_file": str(ROOT / "src/mechanical_cad/sketch_solver.py"),
        "import_failure": None,
    }[origin_kind]
    fake = SimpleNamespace(__file__=origin, BACKEND_CAPABILITIES=frozenset({capability}))
    original = bc.importlib.import_module

    def replaced(name, package):
        if name == "." + owner:
            if origin_kind == "import_failure":
                raise ImportError("module absent")
            return fake
        return original(name, package)

    monkeypatch.setattr(bc.importlib, "import_module", replaced)
    response = sidecar.process_request(guarded(all_markers=True))
    expected = (
        "backend_capability_missing"
        if origin_kind in {"missing", "import_failure"}
        else "backend_identity_mismatch"
    )
    assert response["error"]["code"] == expected
    assert capability in response["backend_receipt"]["missing_capabilities"]
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch"


@pytest.mark.parametrize(
    "version,action",
    [
        (2, "replay"),
        (3.0, "replay"),
        (True, "replay"),
        (3, "check_geometry"),
        (3, "assembly_replay"),
        (3, "canonical_snapshot"),
    ],
)
def test_marker_imports_are_confined_to_exact_three_supported_actions(version, action, monkeypatch):
    monkeypatch.chdir(ROOT)
    original = bc.importlib.import_module

    def checked(name, package):
        assert name not in {"." + owner for owner, _ in OWNERS}
        return original(name, package)

    monkeypatch.setattr(bc.importlib, "import_module", checked)
    request = {"result_version": version, "action": action}
    if action == "canonical_snapshot":
        with pytest.raises(CADException, match="no result-version argument") as exc:
            bc.observe_backend(request)
        assert exc.value.code == "backend_contract_invalid"
        return
    _, supported, _ = bc.observe_backend(request)
    assert not {capability for _, capability in OWNERS}.intersection(supported)


def test_actual_three_markers_advertise_without_native_or_operation_imports():
    script = """
import builtins, importlib.abc, sys
blocked = {'OCP', 'slvs', 'bpy', 'kernel_ocp', 'engine', 'actions', 'assembly_protocol'}
original = builtins.__import__
def checked(name, *args, **kwargs):
    if blocked.intersection(name.split('.')):
        raise AssertionError('forbidden import: ' + name)
    return original(name, *args, **kwargs)
class Blocked(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if blocked.intersection(fullname.split('.')):
            raise AssertionError('forbidden import: ' + fullname)
builtins.__import__ = checked
sys.meta_path.insert(0, Blocked())
from mechanical_cad.backend_contract import observe_backend
for action in ('solve_sketch', 'replay'):
    identity, supported, mismatch = observe_backend({'result_version': 3, 'action': action})
    assert not mismatch
    assert {'mcad.sketch-arcs/1', 'mcad.solve-result/3', 'mcad.part-result/3'} <= supported
assert not blocked.intersection(sys.modules)
print('V3_MARKERS_NATIVE_FREE')
"""
    result = subprocess.run(
        [sys.executable, "-B", "-S", "-c", script],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "V3_MARKERS_NATIVE_FREE"


def test_guarded_three_failures_keep_receipt_and_exact_version_stamp(monkeypatch):
    monkeypatch.chdir(ROOT)
    request = guarded()
    before = copy.deepcopy(request)

    def fail(value):
        raise RuntimeError("dispatch failed")

    monkeypatch.setattr(sidecar, "_process_legacy_request", fail)
    response = sidecar.process_request(request)
    assert request == before and response["result_version"] == 3
    assert response["result"] is None and response["error"]["code"] == "sidecar_error"
    assert response["backend_receipt"]["phase"] == "dispatched"


# A display cache must never mutate a checked profile before its continuation.


class DisplayMutationKernel(FakeKernel):
    def __init__(self, *, fail_display=None, fail_extrusion=False):
        super().__init__()
        self.events = []
        self.meshed = set()
        self.fail_display = fail_display
        self.fail_extrusion = fail_extrusion

    def sector_profile(self, sketch):
        self.events.append("sector_profile")
        return super().sector_profile(sketch)

    def extrude_sector(self, profile, length):
        self.events.append("extrude_sector")
        assert profile not in self.meshed, "checked profile was mutated by display"
        if self.fail_extrusion:
            raise RuntimeError("checked extrusion failure")
        return super().extrude_sector(profile, length)

    def topology(self, shape, *args):
        self.events.append("topology:" + shape)
        return []

    def inspect(self, shape):
        self.events.append("inspect:" + shape)
        return {"solids": 1}

    def tessellate(self, shape, **kwargs):
        self.events.append("mesh:" + shape)
        self.meshed.add(shape)
        if self.fail_display == shape:
            raise RuntimeError("display failure")
        return {"vertices": [], "triangles": []}


def test_checked_sector_continuation_precedes_all_display_mutation(monkeypatch):
    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    kernel = DisplayMutationKernel()
    replay = engine.regenerate(source(), kernel, result_version=3)
    assert replay.ok
    assert kernel.events == [
        "sector_profile",
        "topology:profile-handle",
        "extrude_sector",
        "topology:solid-handle",
        "inspect:solid-handle",
        "mesh:profile-handle",
        "mesh:solid-handle",
    ]
    assert set(replay.shapes) == set(replay.outputs) == {"profile", "pad"}


def test_profile_only_sector_is_meshed_before_return(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    document = source()
    document = replace(document, features=document.features[:1], active_feature="profile")
    kernel = DisplayMutationKernel()
    replay = engine.regenerate(document, kernel, result_version=3)
    assert replay.ok and replay.result["features"][0]["mesh"] is not None
    assert kernel.events == ["sector_profile", "topology:profile-handle", "mesh:profile-handle"]


def test_deferred_profile_display_failure_removes_every_provisional_handle(monkeypatch):
    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    kernel = DisplayMutationKernel(fail_display="profile-handle")
    replay = engine.regenerate(source(), kernel, result_version=3)
    profile, pad = replay.result["features"]
    assert not replay.ok
    assert profile["status"] == "failed" and profile["error"]["code"] == "kernel_error"
    assert profile["sketch"]["status"] == "okay" and profile["sketch"]["solved"] is not None
    assert pad["status"] == "blocked" and pad["error"]["code"] == "upstream_failed"
    assert pad["resolved_params"] == {}
    assert replay.shapes == replay.outputs == {}
    for item in (profile, pad):
        assert item["mesh"] is item["stats"] is item["output"] is None
        assert item["topology"] == []
    assert kernel.events.count("sector_profile") == kernel.events.count("extrude_sector") == 1
    assert kernel.events.count("mesh:profile-handle") == 1
    assert "mesh:solid-handle" not in kernel.events


def test_deferred_solid_display_failure_retains_only_valid_profile(monkeypatch):
    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    kernel = DisplayMutationKernel(fail_display="solid-handle")
    replay = engine.regenerate(source(), kernel, result_version=3)
    profile, pad = replay.result["features"]
    assert not replay.ok and profile["status"] == "ok" and profile["mesh"] is not None
    assert pad["status"] == "failed" and pad["error"]["code"] == "kernel_error"
    assert pad["mesh"] is pad["stats"] is pad["output"] is None and pad["topology"] == []
    assert set(replay.shapes) == set(replay.outputs) == {"profile"}
    assert kernel.events.count("mesh:solid-handle") == 1


def test_checked_extrusion_failure_still_returns_meshed_profile(monkeypatch):
    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    kernel = DisplayMutationKernel(fail_extrusion=True)
    replay = engine.regenerate(source(), kernel, result_version=3)
    profile, pad = replay.result["features"]
    assert not replay.ok and profile["status"] == "ok" and profile["mesh"] is not None
    assert pad["status"] == "failed" and pad["output"] is None
    assert set(replay.shapes) == set(replay.outputs) == {"profile"}
    assert kernel.events[-1] == "mesh:profile-handle"
    assert "mesh:solid-handle" not in kernel.events


@pytest.mark.parametrize(
    "kind,version",
    [(kind, version) for kind in ("primitive", "legacy_sketch") for version in (1, 2, 3)]
    + [("arc_empty_sketch", 3)],
)
def test_nonsector_profiles_keep_eager_display_order(kind, version, monkeypatch):
    from dataclasses import replace

    from mechanical_cad import sketch_evaluation
    from mechanical_cad.model import Feature

    if kind == "primitive":
        document = replace(
            source(),
            features=(
                Feature("profile", "sketch_rectangle", "Rectangle", {"width": 5, "height": 5}),
                Feature("pad", "extrude", "Pad", {"length": 10}, {"profile": "profile"}),
            ),
        )
    else:
        document = Document.from_dict(
            json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
        )
        if kind == "arc_empty_sketch":
            profile = document.features[0]
            profile = replace(profile, sketch=replace(profile.sketch, schema_version=3, arcs=()))
            document = replace(document, features=(profile, *document.features[1:]))
    monkeypatch.setattr(sketch_evaluation, "evaluate_sketch", evaluated)
    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)

    class LegacyOrderKernel(DisplayMutationKernel):
        def rectangle(self, **kwargs):
            self.events.append("legacy_profile")
            return "profile-handle"

        def polygon(self, *args, **kwargs):
            self.events.append("legacy_profile")
            return "profile-handle"

        def extrude(self, profile, length):
            assert profile in self.meshed, "nonsector display order changed"
            self.events.append("legacy_extrude")
            return "solid-handle"

    kernel = LegacyOrderKernel()
    replay = engine.regenerate(document, kernel, result_version=version)
    assert replay.ok
    assert kernel.events == [
        "legacy_profile",
        "topology:profile-handle",
        "mesh:profile-handle",
        "legacy_extrude",
        "topology:solid-handle",
        "inspect:solid-handle",
        "mesh:solid-handle",
    ]


@pytest.mark.parametrize("shape", ["profile-handle", "solid-handle"])
@pytest.mark.parametrize(
    "code,status", [("display_limit", "failed"), ("profile_unavailable", "blocked")]
)
def test_deferred_display_preserves_cad_exception_diagnostic(shape, code, status, monkeypatch):
    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    kernel = DisplayMutationKernel()
    original = kernel.tessellate

    def display(value, **kwargs):
        if value == shape:
            raise CADException(code, "The exact display diagnostic.")
        return original(value, **kwargs)

    monkeypatch.setattr(kernel, "tessellate", display)
    replay = engine.regenerate(source(), kernel, result_version=3)
    failed = replay.result["features"][0 if shape == "profile-handle" else 1]
    assert failed["status"] == status
    assert failed["error"] == {"code": code, "message": "The exact display diagnostic."}
    assert failed["output"] is None and failed["id"] not in replay.shapes
    assert failed["id"] not in replay.outputs


def test_late_profile_failure_invalidates_previously_failed_dependent(monkeypatch):
    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    kernel = DisplayMutationKernel(fail_extrusion=True, fail_display="profile-handle")
    replay = engine.regenerate(source(), kernel, result_version=3)
    profile, pad = replay.result["features"]
    assert profile["status"] == "failed" and pad["status"] == "blocked"
    assert pad["error"]["code"] == "upstream_failed" and pad["resolved_params"] == {}
    assert replay.shapes == replay.outputs == {}
    assert kernel.events.count("extrude_sector") == 1


def test_selected_profile_remains_meshed_with_downstream_extrusion(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(profile_adapter_v3, "evaluate_sketch", evaluated)
    document = replace(source(), active_feature="profile")
    kernel = DisplayMutationKernel()
    replay = engine.regenerate(document, kernel, result_version=3)
    assert replay.ok and replay.result["active_feature"] == "profile"
    assert all(item["mesh"] is not None for item in replay.result["features"])
    assert set(replay.shapes) == set(replay.outputs) == {"profile", "pad"}


ASSEMBLY_NO_EVALUATION_SCRIPT = """
import builtins, importlib.abc, sys
blocked = {'OCP', 'slvs', 'bpy', 'cadquery', 'kernel_ocp', 'actions', 'sketch_protocol_v3'}
original_import = builtins.__import__
def forbidden(*args, **kwargs):
    raise AssertionError('Assembly invalid version reached operation evaluation')
def bind_sentinels():
    for name, attributes in {
        'mechanical_cad.engine': ('regenerate',),
        'mechanical_cad.assembly_service': ('regenerate', 'evaluate', '_build_parts'),
        'mechanical_cad.sketch_evaluation': ('evaluate_sketch', 'solve'),
        'mechanical_cad.sketch_solver': ('solve', '_load_backend'),
    }.items():
        module = sys.modules.get(name)
        if module is not None:
            for attribute in attributes:
                if hasattr(module, attribute):
                    setattr(module, attribute, forbidden)
def checked_import(name, *args, **kwargs):
    if blocked.intersection(name.split('.')):
        raise AssertionError('forbidden Assembly rejection import: ' + name)
    result = original_import(name, *args, **kwargs)
    bind_sentinels()
    return result
class Blocked(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if blocked.intersection(fullname.split('.')):
            raise AssertionError('forbidden Assembly rejection import: ' + fullname)
builtins.__import__ = checked_import
sys.meta_path.insert(0, Blocked())
"""


def assembly_differential_helpers():
    """Reuse the frozen two-module baseline differential, without native imports."""
    spec = importlib.util.spec_from_file_location(
        "_sector_assembly_differential", ROOT / "tests/integration/test_backend_contract_process.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("action", ["assembly_replay", "assembly_check", "assembly_sample"])
def test_unsupported_assembly_four_preserves_bound_old_wire_without_native_or_evaluation(action):
    helpers = assembly_differential_helpers()
    directory, manifest = helpers.sector_pre_service_fixtures()
    request = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "action": action,
        "assembly": json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()),
        "result_version": 4,
    }
    raw = json.dumps(request)
    scripts = (
        "from mechanical_cad.sidecar import main\nraise SystemExit(main())\n",
        helpers.sector_pre_service_script(directory, manifest),
    )
    observed = [
        helpers.run(raw=raw, no_site=True, script=ASSEMBLY_NO_EVALUATION_SCRIPT + script)
        for script in scripts
    ]
    assert observed[0][0].returncode == observed[1][0].returncode == 1
    assert observed[0][0].stdout == observed[1][0].stdout
    for process, response in observed:
        assert not process.stderr
        assert response["error"]["code"] == "unsupported_result_version"
        assert response["input_fingerprint"] == helpers.digest(request)
        assert response["request"]["result_version"] == 4
        assert response["request_fingerprint"] == helpers.digest(response["request"])
        assert not response["result"]["source_replays"]
        assert not response["result"]["parts"] and not response["report"]["poses"]
        assert "native_runtime_versions" not in response["report"]
        assert "result_version" not in response


@pytest.mark.parametrize("action", ["assembly_replay", "assembly_check", "assembly_sample"])
def test_supported_assembly_three_accepts_recorded_full_source_replays(
    action,
    make_assembly3,  # noqa: F811
):
    from test_assembly_bridge_v3 import bridge

    # Genuine retained replay-3 packets, synthetic pose/query ports. This
    # exercises strict transport validation, not fresh native qualification.
    request, response, calls = make_assembly3(
        action,
        requirements=None if action == "assembly_replay" else [],
        coordinates={"slide_a": 100, "slide_b": 100},
        samples={"joint_id": "slide_a", "values": [100, 200]}
        if action == "assembly_sample"
        else None,
    )
    accepted = bridge.validate_response(request, response)
    assert response["ok"], response["error"]
    assert accepted == response and accepted is not response
    assert response["result_version"] == response["request"]["result_version"] == 3
    assert calls == [
        (source["source_document_id"], 3) for source in request["assembly"]["part_sources"]
    ]
    for row in response["result"]["source_replays"]:
        assert row["replay"] == make_assembly3.replays[row["source_document_id"]]
        assert row["replay"]["result_version"] == 3
    assert len(response["result"]["parts"]) == 2
    assert len(response["report"]["poses"]) == (2 if action == "assembly_sample" else 1)


def test_kind_bearing_three_retains_original_numeric_and_failure_stamp_order():
    helpers = assembly_differential_helpers()
    directory, manifest = helpers.sector_pre_service_fixtures()
    raw = '{"protocol_version":1,"kind":"other","result_version":3,"unknown":0.' + "0" * 150 + "}"
    scripts = (
        "from mechanical_cad.sidecar import main\nraise SystemExit(main())\n",
        helpers.sector_pre_service_script(directory, manifest),
    )
    observed = [
        helpers.run(raw=raw, no_site=True, script=ASSEMBLY_NO_EVALUATION_SCRIPT + script)
        for script in scripts
    ]
    assert observed[0][0].returncode == observed[1][0].returncode == 1
    assert observed[0][0].stdout == observed[1][0].stdout
    assert observed[0][1]["error"]["code"] == "invalid_request"
    assert "result_version" not in observed[0][1]
