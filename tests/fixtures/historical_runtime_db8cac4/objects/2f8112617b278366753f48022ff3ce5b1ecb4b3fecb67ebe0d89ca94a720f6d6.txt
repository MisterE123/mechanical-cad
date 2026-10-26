"""Reconstructed pure geometry-3 contracts; synthetic evidence is not native QA."""

from __future__ import annotations

import ast
import copy
import importlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from test_result_v3_client import ADDON, PACKAGE, replay_pair, sector_document, snapshots

geometry = importlib.import_module(PACKAGE + ".geometry_result_v3")
result_v3 = importlib.import_module(PACKAGE + ".result_v3")
ACTIONS = ("check_geometry", "export_step", "export_stl")


def pair(action="check_geometry", *, destination="./sector//part.step", options=None):
    """A data-only fixture, deliberately sharing existing replay-3 adversaries."""
    request, response = replay_pair()
    request["action"] = action
    if options is not None:
        request["options"] = options
    if action != "check_geometry":
        request["destination"] = destination
    response["input_fingerprint"] = snapshots.input_fingerprint(request)
    response["action"] = action
    active = response["result"]["features"][-1]
    # Synthetic triangulation/counts validate transport semantics only. The
    # unchanged kernel is responsible for constructing and measuring geometry.
    active["mesh"] = {
        "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]],
        "triangles": [[0, 1, 2] for _ in range(8)],
        "triangle_face_ids": [active["topology"][i % 5]["id"] for i in range(8)],
    }
    report = {
        "watertight": True,
        "consistently_oriented": True,
        "vertex_manifold": True,
        "vertices": 5,
        "triangles": 8,
        "signed_volume": active["stats"]["volume"],
        "weld_tolerance": 1e-7,
    }
    deflection = request.get("options", {}).get("linear_deflection", 0.1)
    checks = {
        "brep": copy.deepcopy(active["stats"]),
        "mesh": report,
        "linear_deflection_mm": deflection,
    }
    if action == "export_stl":
        checks.update(
            encoded_mesh=copy.deepcopy(report),
            encoding={
                "maximum_vertex_error_mm": 0,
                "allowed_vertex_error_mm": min(1e-5, 0.1 * deflection),
                "independent_precision_ceiling_mm": 1e-5,
            },
        )
    response["geometry_check"] = checks
    response["export"] = (
        None
        if action == "check_geometry"
        else {
            "format": "STEP" if action == "export_step" else "STL",
            "destination": destination,
            "bytes": 84 + 50 * 8 if action == "export_stl" else 1234,
            "units": "mm",
            "document_hash": response["result"]["document_hash"],
            "active_feature": response["result"]["active_feature"],
            "linear_deflection_mm": deflection,
            "atomic_replace": True,
        }
    )
    return request, response


def failed_replay(result):
    result["status"] = "failed"
    for index, feature in enumerate(result["features"]):
        feature.update(
            status="failed" if index == 0 else "blocked",
            error={
                "code": "unsupported_native_frame" if index == 0 else "upstream_failed",
                "message": "Synthetic failure retained from fresh replay.",
            },
            output=None,
            stats=None,
            mesh=None,
            topology=[],
        )


def set_path(data, path, value):
    for key in path[:-1]:
        data = data[key]
    data[path[-1]] = value


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize(
    "options", [None, {}, {"linear_deflection": 0.001}, {"linear_deflection": 10}]
)
def test_full_operation_evidence_is_validated_and_detached(action, options):
    request, response = pair(action, options=options)
    before = copy.deepcopy((request, response))
    accepted = geometry.validate_response(request, response)
    assert accepted == response and accepted is not response
    assert accepted["result"] is not response["result"]
    assert accepted["result"]["result_version"] == 3
    assert accepted["result"]["features"][0]["sketch"]["solved"]["schema_version"] == 3
    assert (request, response) == before
    assert geometry.validate_request(request) == request
    assert geometry.validate_source(request["document"]) == request["document"]


def test_source_is_structural_admission_without_a_new_dof_or_seed_gate():
    request, response = pair()
    response["result"]["features"][0]["sketch"]["remaining_dof"] = 5
    geometry.validate_response(request, response)
    source = request["document"]
    source["features"][0]["sketch"]["points"].append({"id": "unused", "u": 30, "v": 20})
    source["features"][1]["params"]["length"] = "H"
    source["parameters"] = {"H": 7}
    # The solver may move unequal-radius authored seeds. Admission must not
    # substitute a numerical readiness test for fresh native solve evidence.
    source["features"][0]["sketch"]["points"][1]["u"] = 7
    before = copy.deepcopy(source)
    assert geometry.validate_source(source) == before
    assert source == before


@pytest.mark.parametrize("version", [None, True, False, 1, 2, 3.0, "3", 4])
@pytest.mark.parametrize("target", ["request", "response", "body"])
def test_explicit_integer_three_required_at_every_layer(version, target):
    request, response = pair()
    container = request if target == "request" else response
    if target == "body":
        container = response["result"]
    container["result_version"] = version
    with pytest.raises(ValueError):
        geometry.validate_response(request, response)


@pytest.mark.parametrize("version", [None, True, False, 0, 1.0, "1", 2])
@pytest.mark.parametrize("target", ["request", "response"])
def test_exact_protocol_one_required(version, target):
    request, response = pair()
    (request if target == "request" else response)["protocol_version"] = version
    with pytest.raises(ValueError):
        geometry.validate_response(request, response)


@pytest.mark.parametrize(
    "action", [None, True, [], "replay", "solve_sketch", "canonical_snapshot", "assembly_replay"]
)
def test_no_other_action_family_is_admitted(action):
    request, _ = pair()
    request["action"] = action
    with pytest.raises(ValueError):
        geometry.validate_request(request)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(kind="assembly"),
        lambda d: d.update(active_feature=None),
        lambda d: d.update(active_feature="sketch"),
        lambda d: d["features"].pop(),
        lambda d: d["features"].append(
            {"id": "other", "kind": "sketch_circle", "params": {"radius": 2}}
        ),
        lambda d: d["features"].append(
            {
                "id": "other",
                "kind": "extrude",
                "params": {"length": 2},
                "inputs": {"profile": "sketch"},
            }
        ),
        lambda d: d["features"][1].update(inputs={"profile": "extrude"}),
        lambda d: d["features"][1].update(
            kind="cut", params={}, inputs={"base": "sketch", "tool": "sketch"}
        ),
        lambda d: d["features"][0]["sketch"].update(arcs=[]),
        lambda d: d["features"][0]["sketch"].update(schema_version=2, arcs=[]),
        lambda d: d["features"][0]["sketch"]["arcs"].append(
            {"id": "other", "center": "o", "start": "a", "end": "b", "direction": "ccw"}
        ),
        lambda d: d["features"][0]["sketch"]["circles"].append(
            {"id": "circle", "center": "o", "radius": 5}
        ),
        lambda d: d["features"][0]["sketch"]["lines"].pop(),
        lambda d: d["features"][0]["sketch"]["lines"].append(
            {"id": "chord", "start": "a", "end": "b"}
        ),
        lambda d: d["features"][0]["sketch"]["lines"][0].update(start="a", end="b"),
        lambda d: d["features"][0]["sketch"]["plane"].update(origin=[1e-12, 0, 0]),
        lambda d: d["features"][0]["sketch"]["plane"].update(quaternion=[-1, 0, 0, 0]),
        lambda d: d["features"][0]["sketch"]["plane"].update(quaternion=[0, 0, 0, 1]),
        lambda d: d["features"][1]["params"].update(length=0.999999999),
        lambda d: d["features"][1]["params"].update(length=1000.000001),
    ],
)
def test_unsupported_sources_fail_before_response_validation(change):
    source = sector_document()
    change(source)
    with pytest.raises(ValueError):
        geometry.validate_source(source)


def test_coordinate_and_coincident_aliases_do_not_replace_shared_ids():
    source = sector_document()
    sketch = source["features"][0]["sketch"]
    sketch["points"].append({"id": "alias", "u": 5, "v": 0})
    sketch["lines"][0]["end"] = "alias"
    for constraints in ([], [{"id": "join", "kind": "coincident", "refs": ["a", "alias"]}]):
        sketch["constraints"] = constraints
        with pytest.raises(ValueError, match="endpoint IDs"):
            geometry.validate_source(source)


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize(
    "options",
    [
        None,
        [],
        {"future": 1},
        {"linear_deflection": True},
        {"linear_deflection": "0.1"},
        {"linear_deflection": 0},
        {"linear_deflection": 0.000999},
        {"linear_deflection": 10.001},
    ],
)
def test_options_are_action_specific_and_strict(action, options):
    request, _ = pair(action)
    request["options"] = options
    with pytest.raises(ValueError):
        geometry.validate_request(request)


@pytest.mark.parametrize(
    "field,value",
    [
        ("feature_id", "sketch"),
        ("backend_contract", {}),
        ("authority", True),
        ("kind", "part"),
        ("future", 1),
    ],
)
def test_request_has_no_unbound_extensions(field, value):
    request, _ = pair()
    request[field] = value
    with pytest.raises(ValueError):
        geometry.validate_request(request)


@pytest.mark.parametrize(
    "destination",
    [None, True, 4, "", " ", "\x00file", "/", ".", "..", "./", "a/..", "a/.", "/tmp/file.step/"],
)
def test_invalid_export_destinations_are_not_normalized(destination):
    request, _ = pair("export_step")
    request["destination"] = destination
    with pytest.raises(ValueError):
        geometry.validate_request(request)


def test_check_has_no_destination_and_export_requires_one():
    request, _ = pair()
    request["destination"] = None
    with pytest.raises(ValueError):
        geometry.validate_request(request)
    request["action"] = "export_step"
    request.pop("destination")
    with pytest.raises(ValueError):
        geometry.validate_request(request)


@pytest.mark.parametrize(
    "destination",
    [
        "./part.step",
        "dir//part.step",
        "dir/../part.step",
        " part with spaces.step ",
        "/tmp/part.step",
    ],
)
def test_export_receipts_preserve_exact_requested_path(destination):
    request, response = pair("export_step", destination=destination)
    assert geometry.validate_response(request, response)["export"]["destination"] == destination
    response["export"]["destination"] = destination + ".other"
    with pytest.raises(ValueError, match="exact requested output"):
        geometry.validate_response(request, response)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(options={}),
        lambda r: r.update(options={"linear_deflection": 0.1}),
        lambda r: r.update(destination="sector/part.step"),
        lambda r: r["document"].update(name="changed"),
        lambda r: r["document"]["features"][0].update(label="new label"),
    ],
)
def test_complete_raw_request_binds_even_semantically_equivalent_changes(change):
    request, response = pair("export_step")
    change(request)
    with pytest.raises(ValueError, match="operation identity"):
        geometry.validate_response(request, response)


@pytest.mark.parametrize(
    "path,value",
    [
        (("input_fingerprint",), "0" * 64),
        (("action",), "export_stl"),
        (("ok",), 1),
        (("error",), {"code": "export_failed", "message": "failed"}),
        (("result", "document_hash"), "0" * 64),
        (("result", "active_feature"), "sketch"),
        (("result", "features", 0, "sketch", "solver"), "fake"),
        (("result", "features", 0, "sketch", "solved", "schema_version"), 2),
        (("result", "features", 0, "sketch", "solved", "arcs", 0, "direction"), "cw"),
        (("result", "features", 0, "sketch", "remaining_dof"), True),
        (("result", "features", 1, "inputs"), {"profile": "other"}),
        (("result", "features", 1, "resolved_params", "length"), 8),
        (("result", "features", 1, "topology", 4, "signature", "radius"), 7),
        (("geometry_check", "brep", "volume"), 1),
        (("geometry_check", "mesh", "triangles"), 10),
        (("geometry_check", "mesh", "watertight"), 1),
        (("geometry_check", "linear_deflection_mm"), 0.2),
        (("export", "destination"), "sector/part.step"),
        (("export", "format"), "STL"),
        (("export", "bytes"), True),
        (("export", "bytes"), 0),
        (("export", "atomic_replace"), 1),
        (("export", "document_hash"), "0" * 64),
        (("export", "active_feature"), "sketch"),
        (("export", "linear_deflection_mm"), 0.2),
    ],
)
def test_success_requires_genuine_bound_replay_and_geometry(path, value):
    request, response = pair("export_step")
    set_path(response, path, value)
    with pytest.raises(ValueError):
        geometry.validate_response(request, response)


@pytest.mark.parametrize(
    "path", [(), ("result",), ("geometry_check",), ("geometry_check", "brep"), ("export",)]
)
@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_each_geometry_envelope_layer_is_closed(path, mutation):
    request, response = pair("export_step")
    target = response
    for key in path:
        target = target[key]
    if mutation == "extra":
        target["future"] = True
    else:
        target.pop(next(iter(target)))
    with pytest.raises(ValueError):
        geometry.validate_response(request, response)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_encoding",
        "missing_encoded_mesh",
        "excess_precision",
        "changed_ceiling",
        "changed_count",
        "changed_size",
    ],
)
def test_stl_requires_complete_actual_encoded_contract(mutation):
    request, response = pair("export_stl")
    checks = response["geometry_check"]
    if mutation.startswith("missing_"):
        checks.pop(mutation.removeprefix("missing_"))
    elif mutation == "excess_precision":
        checks["encoding"]["maximum_vertex_error_mm"] = 1.00001e-5
    elif mutation == "changed_ceiling":
        checks["encoding"]["independent_precision_ceiling_mm"] = 1e-4
    elif mutation == "changed_count":
        checks["encoded_mesh"]["triangles"] = 10
    else:
        response["export"]["bytes"] += 1
    with pytest.raises(ValueError):
        geometry.validate_response(request, response)


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("body", ["none", "failed", "ok"])
@pytest.mark.parametrize("check", ["none", "base", "encoded"])
@pytest.mark.parametrize(
    "code",
    [
        "replay_failed",
        "io_error",
        "regeneration_failed",
        "geometry_check_failed",
        "export_failed",
        "export_io_error",
        "empty_export",
        "invented",
    ],
)
def test_failed_action_algebra_is_finite(action, body, check, code):
    request, response = pair(action)
    response.update(ok=False, export=None, error={"code": code, "message": "Synthetic failure."})
    if body == "none":
        response["result"] = None
    elif body == "failed":
        failed_replay(response["result"])
    if check == "none":
        response["geometry_check"] = None
    else:
        _, encoded_response = pair("export_stl")
        response["geometry_check"] = encoded_response["geometry_check"]
        if check == "base":
            response["geometry_check"].pop("encoding")
            response["geometry_check"].pop("encoded_mesh")
    allowed = (
        (body == "none" and check == "none" and code in {"replay_failed", "io_error"})
        or (body == "failed" and check == "none" and code == "regeneration_failed")
        or (body == "ok" and check == "none" and code in {"geometry_check_failed", "io_error"})
        or (
            body == "ok"
            and check == "base"
            and action != "check_geometry"
            and code in {"export_failed", "export_io_error", "empty_export"}
        )
    )
    if allowed:
        assert geometry.validate_response(request, response) == response
    else:
        with pytest.raises(ValueError):
            geometry.validate_response(request, response)


@pytest.mark.parametrize("action", ACTIONS)
def test_failure_never_retains_export_or_success_authority(action):
    request, response = pair(action)
    response.update(ok=False, error={"code": "export_failed", "message": "failure"})
    if action == "export_stl":
        response["geometry_check"].pop("encoding")
        response["geometry_check"].pop("encoded_mesh")
    with pytest.raises(ValueError):
        geometry.validate_response(request, response)


def test_common_preflight_failure_is_diagnostic_only_and_detached():
    request, _ = pair()
    response = {
        "protocol_version": 1,
        "result_version": 3,
        "ok": False,
        "result": None,
        "error": {"code": "unsupported_profile_scale", "message": "Correct the resolved height."},
    }
    assert geometry.validate_response(request, response) == response
    assert geometry.validate_response(request, response) is not response
    for field, value in (
        ("action", "check_geometry"),
        ("export", None),
        ("geometry_check", None),
        ("ok", True),
        ("result", {}),
    ):
        with pytest.raises(ValueError):
            geometry.validate_response(request, {**response, field: value})


@pytest.mark.parametrize("code", sorted(geometry._PREFLIGHT_ERRORS))
def test_known_preflight_codes_are_diagnostics_with_no_output(code):
    request, _ = pair("export_step")
    response = {
        "protocol_version": 1,
        "result_version": 3,
        "ok": False,
        "result": None,
        "error": {"code": code, "message": "Request rejected before replay."},
    }
    assert geometry.validate_response(request, response) == response


@pytest.mark.parametrize(
    "code",
    [
        "sidecar_error",
        "invalid_json",
        "document_too_large",
        "export_failed",
        "export_io_error",
        "empty_export",
        "replay_failed",
        "regeneration_failed",
        "geometry_check_failed",
        "io_error",
        "invented",
    ],
)
def test_common_envelope_does_not_turn_ambiguous_post_launch_errors_into_known_failure(code):
    request, _ = pair("export_step")
    response = {
        "protocol_version": 1,
        "result_version": 3,
        "ok": False,
        "result": None,
        "error": {"code": code, "message": "No pre-replay guarantee."},
    }
    with pytest.raises(ValueError, match="pre-replay"):
        geometry.validate_response(request, response)


@pytest.mark.parametrize(
    "variant,code",
    [
        ("nonfinite", "invalid_json"),
        ("budget", "document_too_large"),
        ("malformed", "sidecar_error"),
    ],
)
def test_actual_guarded_serialization_failure_after_fake_write_is_not_validated(
    monkeypatch, tmp_path, variant, code
):
    # Use the actual native-free wrapper/catch. Admission/identity is an explicit
    # test port; this is not a valid GuardedEvidence or a real kernel export.
    from mechanical_cad import backend_contract

    request, successful = pair("export_step")
    destination = tmp_path / "fake-completed-export.step"
    prepared = SimpleNamespace(
        operation=request,
        contract={
            "request_id": "synthetic-prepared",
            "required_capabilities": ["mcad.geometry-result/3"],
        },
        request_fingerprint="synthetic-fingerprint",
    )
    monkeypatch.setattr(backend_contract, "prepare_request", lambda _: prepared)
    monkeypatch.setattr(
        backend_contract,
        "observe_backend",
        lambda _: ({}, frozenset({"mcad.geometry-result/3"}), False),
    )
    if variant == "budget":
        monkeypatch.setattr(backend_contract, "MAX_RESPONSE_BYTES", 128)

    def dispatch(_operation):
        destination.write_bytes(b"synthetic output already replaced")
        if variant == "malformed":
            return None
        if variant == "nonfinite":
            successful["unserializable"] = float("nan")
        return successful

    response = backend_contract.process_guarded_request({}, dispatch)
    assert destination.read_bytes() == b"synthetic output already replaced"
    assert response.pop("backend_receipt")["phase"] == "dispatched"
    assert response["ok"] is False and response["result"] is None
    assert response["error"]["code"] == code
    with pytest.raises(ValueError, match="pre-replay"):
        geometry.validate_response(request, response)


@pytest.mark.parametrize("target", ["request", "response"])
@pytest.mark.parametrize("variant", ["cycle", "dag", "nonfinite", "large_integer"])
def test_resource_abuse_is_rejected_before_recursion_or_semantic_walk(target, variant):
    request, response = pair()
    container = request if target == "request" else response
    if variant == "cycle":
        value = container
    elif variant == "dag":
        value = [0]
        for _ in range(30):
            value = [value, value]
    elif variant == "nonfinite":
        value = float("nan")
    else:
        value = 1 << 20_000
    container["hostile"] = value
    with pytest.raises(ValueError):
        geometry.validate_response(request, response)


def test_geometry_requests_do_not_activate_the_original_replay_validator():
    for action in ACTIONS:
        request, response = pair(action)
        with pytest.raises(ValueError):
            result_v3.validate_response(request, response)
    request, response = replay_pair()
    assert result_v3.validate_response(request, response) == response


def test_new_client_import_and_validation_have_no_core_native_or_authority_dependency():
    request, response = pair("export_stl")
    script = f"""
import importlib, importlib.abc, json, sys, types
blocked = {{'mechanical_cad', 'OCP', 'slvs', 'bpy', 'operation_contracts',
           'guarded_evidence', 'guarded_operations', 'service_v3', 'sidecar_job'}}
class Blocked(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if blocked.intersection(fullname.split('.')):
            raise AssertionError('forbidden import: ' + fullname)
sys.meta_path.insert(0, Blocked())
package = types.ModuleType('standalone_geometry3')
package.__path__ = [{str(ADDON)!r}]
sys.modules[package.__name__] = package
validator = importlib.import_module(package.__name__ + '.geometry_result_v3')
request, response = json.loads({json.dumps([request, response])!r})
assert validator.validate_response(request, response) == response
assert not any(blocked.intersection(name.split('.')) for name in sys.modules)
print('GEOMETRY3_NATIVE_FREE')
"""
    child = subprocess.run(
        [sys.executable, "-B", "-S", "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
        env={**os.environ, "PYTHONPATH": str(ADDON.parent)},
    )
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == "GEOMETRY3_NATIVE_FREE"
    tree = ast.parse((ADDON / "geometry_result_v3.py").read_bytes())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".")[0] not in {"mechanical_cad", "bpy", "OCP", "slvs"}
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in {"mechanical_cad", "bpy", "OCP", "slvs"}
