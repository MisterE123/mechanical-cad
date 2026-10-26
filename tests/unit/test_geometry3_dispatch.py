"""Gate B unguarded dispatch controls, with no native or sidecar process launches.

Synthetic action ports establish routing only. Historical rejection assertions
use the exact inverse-restored recovered 0.6 sidecar in its own module namespace.
The real main function is exercised with in-memory streams and fake descriptors;
this establishes wire/error behavior, never native geometry or installed output.
"""

from __future__ import annotations

import builtins
import copy
import hashlib
import importlib.abc
import io
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_arc_profile_native_end_cap import geometry_revision_originals

from mechanical_cad import (
    actions,
    backend_contract,
    geometry_protocol_v3,
    sidecar,
    sketch_protocol_v3,
)
from mechanical_cad.errors import CADException
from mechanical_cad.model import Document
from mechanical_cad.part_snapshot import input_fingerprint

ROOT = Path(__file__).resolve().parents[2]
GEOMETRY_ACTIONS = ("check_geometry", "export_step", "export_stl")
CAPABILITY = "mcad.geometry-result/3"
OMITTED = object()


def recovered_69d0_sidecar():
    """Load sealed original bytes, without Git, an external tree, or live patching."""
    _, originals = geometry_revision_originals(ROOT)
    raw = originals["src/mechanical_cad/sidecar.py"]
    assert hashlib.sha256(raw).hexdigest() == (
        "ae6180f7ff15efe54cb8a50db1e80349a58f940f7a00d3aa51dcd0c1e12d91e3"
    )
    module = ModuleType("mechanical_cad._recovered_69d0_sidecar")
    module.__package__ = "mechanical_cad"
    module.__file__ = "recovered69d0:src/mechanical_cad/sidecar.py"
    exec(compile(raw, module.__file__, "exec"), vars(module))
    return module


@pytest.fixture(autouse=True)
def no_native_imports(monkeypatch):
    class NoNative(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, *_args):
            if {"OCP", "OCC", "cadquery", "slvs", "bpy", "kernel_ocp"}.intersection(
                fullname.split(".")
            ):
                pytest.fail("Pure geometry3 dispatch attempted native import: " + fullname)

    monkeypatch.setattr(sys, "meta_path", [NoNative(), *sys.meta_path])


def operation(action="check_geometry", *, version=3, legacy=False):
    example = "drilled_plate" if legacy else "sector_profile_data_only"
    request = {
        "protocol_version": 1,
        "action": action,
        "document": json.loads((ROOT / f"examples/{example}.mcad.json").read_bytes()),
    }
    if version is not OMITTED:
        request["result_version"] = version
    if action in GEOMETRY_ACTIONS[1:]:
        request["destination"] = "./unused//synthetic.step"
    return request


def in_memory_main(module, raw, monkeypatch):
    """Execute the real parser and envelopes, without touching real descriptors."""

    class Output(io.StringIO):
        def __exit__(self, *_args):
            self.flush()

    output, descriptors = Output(), []
    with monkeypatch.context() as patch:
        patch.setattr(
            module,
            "sys",
            SimpleNamespace(stdout=io.StringIO(), stdin=SimpleNamespace(buffer=io.BytesIO(raw))),
        )
        patch.setattr(
            module,
            "os",
            SimpleNamespace(
                dup=lambda descriptor: descriptors.append(("dup", descriptor)) or 123,
                dup2=lambda source, target: descriptors.append(("dup2", source, target)),
                fdopen=lambda descriptor, mode, encoding: output,
            ),
        )
        status = module.main()
    assert descriptors == [("dup", 1), ("dup2", 2, 1)]
    return status, output.getvalue().encode("utf-8")


def encoded(request):
    return json.dumps(request, allow_nan=False, separators=(",", ":")).encode("utf-8")


@pytest.mark.parametrize("action", GEOMETRY_ACTIONS)
def test_exact_three_geometry_dispatches_once_with_same_request(action, monkeypatch):
    request, seen = operation(action), []
    before = copy.deepcopy(request)
    sentinel = {"synthetic_dispatch": action}
    monkeypatch.setattr(
        geometry_protocol_v3,
        "process_geometry_request_v3",
        lambda value: seen.append(value) or sentinel,
    )
    for name in ("process_sketch_request_v3", "process_replay_request_v3"):
        monkeypatch.setattr(sketch_protocol_v3, name, lambda *_a: pytest.fail("wrong route"))
    assert sidecar.process_request(request) is sentinel
    assert seen == [request] and seen[0] is request and request == before


@pytest.mark.parametrize("action", GEOMETRY_ACTIONS)
def test_live_dispatch_runs_full_protocol_preflight_before_synthetic_action(action, monkeypatch):
    request, seen = operation(action), []
    request["options"] = {"linear_deflection": 0.25}
    before = copy.deepcopy(request)
    synthetic = {"ok": False, "error": {"code": "synthetic_only"}, "result": None}

    def run(document, selected, **options):
        assert isinstance(document, Document) and document.to_dict() == request["document"]
        seen.append((selected, options))
        return synthetic

    monkeypatch.setattr(geometry_protocol_v3, "run_geometry_action", run)
    response = sidecar.process_request(request)
    assert response == {
        "protocol_version": 1,
        "result_version": 3,
        "input_fingerprint": input_fingerprint(request),
        **synthetic,
    }
    assert seen == [
        (
            action,
            {
                "destination": request.get("destination"),
                "linear_deflection": 0.25,
                "kernel": None,
                "result_version": 3,
            },
        )
    ]
    assert request == before


@pytest.mark.parametrize("version", [OMITTED, 1, 2])
@pytest.mark.parametrize("action", GEOMETRY_ACTIONS)
def test_legacy_and_omitted_versions_keep_old_action_route_and_response(
    version, action, monkeypatch
):
    request, seen = operation(action, version=version, legacy=True), []
    monkeypatch.setattr(
        geometry_protocol_v3, "process_geometry_request_v3", lambda *_a: pytest.fail("v3 route")
    )

    def run(document, selected, **options):
        seen.append((selected, options))
        return {"ok": True, "action": selected, "synthetic_legacy": True}

    monkeypatch.setattr(actions, "run_geometry_action", run)
    response = sidecar.process_request(request)
    expected = {"protocol_version": 1, "ok": True, "action": action, "synthetic_legacy": True}
    if version == 2:
        expected.update(result_version=2, input_fingerprint=input_fingerprint(request))
    assert response == expected
    assert seen == [
        (
            action,
            {
                "destination": request.get("destination"),
                "linear_deflection": 0.1,
                "result_version": 1 if version is OMITTED else version,
            },
        )
    ]
    current = in_memory_main(sidecar, encoded(request), monkeypatch)
    historical = in_memory_main(recovered_69d0_sidecar(), encoded(request), monkeypatch)
    assert current == historical == (0, encoded(response) + b"\n")


@pytest.mark.parametrize("version", [True, False, 3.0, "3", None, 0, 4, [], {}])
@pytest.mark.parametrize("action", GEOMETRY_ACTIONS)
def test_nonexact_versions_never_enter_geometry3(version, action, monkeypatch):
    monkeypatch.setattr(
        geometry_protocol_v3, "process_geometry_request_v3", lambda *_a: pytest.fail("v3 route")
    )
    with pytest.raises(CADException) as error:
        sidecar.process_request(operation(action, version=version))
    assert error.value.code == "unsupported_result_version"


@pytest.mark.parametrize("version", [None, True, 1.0, 2, [], {}])
def test_protocol_version_fails_before_geometry_dispatch(version, monkeypatch):
    monkeypatch.setattr(
        geometry_protocol_v3, "process_geometry_request_v3", lambda *_a: pytest.fail("v3 route")
    )
    with pytest.raises(CADException) as error:
        sidecar.process_request({**operation(), "protocol_version": version})
    assert error.value.code == "unsupported_protocol"


@pytest.mark.parametrize(
    "action",
    [
        "assembly_replay",
        "assembly_check",
        "assembly_sample",
        "canonical_snapshot",
        "unknown",
        [],
        {},
        None,
        True,
        3,
    ],
)
def test_other_exact_three_actions_reject_before_protocol_import(action, monkeypatch):
    imported, original = [], builtins.__import__

    def checked(name, *args, **kwargs):
        imported.append(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", checked)
    with pytest.raises(CADException) as error:
        sidecar.process_request({**operation(), "action": action})
    assert error.value.code == "invalid_action"
    assert not {
        "geometry_protocol_v3",
        "sketch_protocol_v3",
        "assembly_protocol",
        "actions",
        "kernel_ocp",
    }.intersection(imported)


def test_action_and_result_version_subclasses_are_not_exact_dispatch():
    class Version(int):
        pass

    class Action(str):
        pass

    for changes, expected in (
        ({"result_version": Version(3)}, "unsupported_result_version"),
        ({"action": Action("check_geometry")}, "invalid_action"),
    ):
        with pytest.raises(CADException) as error:
            sidecar.process_request({**operation(), **changes})
        assert error.value.code == expected


@pytest.mark.parametrize("action", ["replay", "solve_sketch", OMITTED])
def test_existing_exact_three_solve_and_default_replay_routes_are_unchanged(action, monkeypatch):
    request, seen = operation(), []
    if action is OMITTED:
        request.pop("action")
    else:
        request["action"] = action
    selected = (
        "process_sketch_request_v3" if action == "solve_sketch" else "process_replay_request_v3"
    )
    monkeypatch.setattr(sketch_protocol_v3, selected, lambda value: seen.append(value) or {})
    monkeypatch.setattr(
        geometry_protocol_v3, "process_geometry_request_v3", lambda *_a: pytest.fail("v3 geometry")
    )
    assert sidecar.process_request(request) == {}
    assert seen == [request] and seen[0] is request


@pytest.mark.parametrize("kind", ["assembly", "other", None])
@pytest.mark.parametrize("action", [*GEOMETRY_ACTIONS, "assembly_replay"])
def test_kind_bearing_three_preserves_assembly_dispatch(kind, action, monkeypatch):
    from mechanical_cad import assembly_protocol

    request, seen = {**operation(action), "kind": kind}, []
    monkeypatch.setattr(
        assembly_protocol, "process_assembly_request", lambda value: seen.append(value) or {}
    )
    monkeypatch.setattr(
        geometry_protocol_v3, "process_geometry_request_v3", lambda *_a: pytest.fail("v3 geometry")
    )
    assert sidecar.process_request(request) == {}
    assert seen == [request] and seen[0] is request


@pytest.mark.parametrize("action", GEOMETRY_ACTIONS)
@pytest.mark.parametrize("missing", ["actions", "geometry_protocol_v3"])
def test_guarded_geometry_missing_marker_rejects_before_dispatch(action, monkeypatch, missing):
    request = operation(action)
    assert (
        actions.BACKEND_CAPABILITIES
        == geometry_protocol_v3.BACKEND_CAPABILITIES
        == frozenset({CAPABILITY})
    )
    monkeypatch.setattr(
        sys.modules["mechanical_cad." + missing], "BACKEND_CAPABILITIES", frozenset()
    )
    request["backend_contract"] = {
        "version": 1,
        "request_id": "b" * 32,
        "required_capabilities": sorted(backend_contract.minimum_capabilities(request)),
    }
    prepared = backend_contract.prepare_request(request)
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sidecar, "_process_legacy_request", lambda *_a: pytest.fail("dispatch"))
    response = sidecar.process_request(request)
    assert response["error"]["code"] == "backend_capability_missing"
    assert {key: value for key, value in response.items() if key != "backend_receipt"} == {
        "protocol_version": 1,
        "ok": False,
        "result": None,
        "error": {
            "code": "backend_capability_missing",
            "message": "Backend does not implement every requested capability.",
        },
    }
    assert response["backend_receipt"]["request_id"] == request["backend_contract"]["request_id"]
    assert response["backend_receipt"]["request_fingerprint"] == prepared.request_fingerprint
    assert response["backend_receipt"]["phase"] == "rejected_before_dispatch"
    assert CAPABILITY in response["backend_receipt"]["missing_capabilities"]


@pytest.mark.parametrize("version", [OMITTED, 1, 2, 3, True, 3.0, "3", None])
@pytest.mark.parametrize("kind", [OMITTED, "other"])
@pytest.mark.parametrize("long_number", [False, True])
def test_main_failure_bytes_and_stamps_match_recovered_original(
    version, kind, long_number, monkeypatch
):
    request = {"protocol_version": 1, "action": "canonical_snapshot", "extra": 1}
    if version is not OMITTED:
        request["result_version"] = version
    if kind is not OMITTED:
        request["kind"] = kind
    raw = encoded(request)
    if long_number:
        raw = raw[:-1] + b',"long":0.' + b"0" * 150 + b"}"
    current = in_memory_main(sidecar, raw, monkeypatch)
    historical = in_memory_main(recovered_69d0_sidecar(), raw, monkeypatch)
    assert current == historical and current[0] == 1
    response = json.loads(current[1])
    stamped = type(version) is int and (version == 2 or (version == 3 and kind is OMITTED))
    assert ("result_version" in response) is stamped
    if stamped:
        assert response["result_version"] == version


@pytest.mark.parametrize("action", GEOMETRY_ACTIONS)
def test_main_live_geometry_failure_has_exact_three_stamp_and_common_envelope(action, monkeypatch):
    request = operation(action)
    request["document"] = {}
    status, raw = in_memory_main(sidecar, encoded(request), monkeypatch)
    response = json.loads(raw)
    assert status == 1
    assert set(response) == {"protocol_version", "result_version", "ok", "result", "error"}
    assert response["result_version"] == 3 and response["protocol_version"] == 1
    assert response["ok"] is False and response["result"] is None
    assert response["error"]["code"] == "invalid_document"


@pytest.mark.parametrize("action", GEOMETRY_ACTIONS)
def test_live_geometry_raw_numeric_guard_precedes_dispatch(action, monkeypatch):
    monkeypatch.setattr(
        geometry_protocol_v3, "process_geometry_request_v3", lambda *_a: pytest.fail("dispatch")
    )
    raw = encoded(operation(action))[:-1] + b',"extra":0.' + b"0" * 150 + b"}"
    status, response = in_memory_main(sidecar, raw, monkeypatch)
    assert status == 1
    assert json.loads(response)["error"]["code"] == "resource_limit"
    assert json.loads(response)["result_version"] == 3


def test_historical_module_does_not_replace_live_dispatch_or_modules():
    live = sidecar.process_request
    historical = recovered_69d0_sidecar()
    assert historical is not sidecar and historical.process_request is not live
    assert historical.process_request.__globals__ is vars(historical)
    assert sidecar.process_request is live
    assert sys.modules["mechanical_cad.sidecar"] is sidecar


@pytest.mark.parametrize("action", GEOMETRY_ACTIONS)
def test_live_guarded_geometry_observes_all_companions_and_dispatches_once(action, monkeypatch):
    request = operation(action)
    request["backend_contract"] = {
        "version": 1,
        "request_id": "c" * 32,
        "required_capabilities": sorted(backend_contract.minimum_capabilities(request)),
    }
    prepared = backend_contract.prepare_request(request)
    monkeypatch.chdir(ROOT)
    calls = []
    monkeypatch.setattr(
        sidecar, "_process_legacy_request", lambda value: calls.append(value) or {"ok": True}
    )
    response = sidecar.process_request(request)
    assert calls == [prepared.operation]
    assert response["result_version"] == 3
    receipt = response["backend_receipt"]
    assert receipt["phase"] == "dispatched" and receipt["missing_capabilities"] == []
    assert receipt["confirmed_capabilities"] == request["backend_contract"]["required_capabilities"]
    assert receipt["request_id"] == prepared.contract["request_id"]
    assert receipt["request_fingerprint"] == prepared.request_fingerprint


@pytest.mark.parametrize("version", [None, True, 3.0, "3", 1, 2])
@pytest.mark.parametrize("action", [*GEOMETRY_ACTIONS, "canonical_snapshot", "assembly_replay"])
def test_observer_never_infers_geometry3_from_nonexact_versions(version, action, monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(
        backend_contract,
        "_observe_geometry_v3",
        lambda *_: pytest.fail("unexpected geometry3 observation"),
    )
    request = {"action": action, "result_version": version}
    if action == "canonical_snapshot":
        with pytest.raises(CADException, match="no result-version argument") as exc:
            backend_contract.observe_backend(request)
        assert exc.value.code == "backend_contract_invalid"
        return
    _, supported, _ = backend_contract.observe_backend(request)
    assert CAPABILITY not in supported


@pytest.mark.parametrize("legacy", [False, True])
def test_snapshot_observation_uses_source_schema_without_geometry_owner(legacy, monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(
        backend_contract,
        "_observe_geometry_v3",
        lambda *_: pytest.fail("snapshot observed a geometry owner"),
    )
    request = operation("canonical_snapshot", legacy=legacy)
    del request["result_version"]
    _, supported, mismatch = backend_contract.observe_backend(request)
    assert not mismatch and CAPABILITY not in supported
    assert ("mcad.snapshot-sketch3/1" in supported) is (not legacy)
