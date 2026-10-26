"""Pure Assembly STEP receipt contracts, using explicitly synthetic geometry.

No export writer, native kernel, sidecar or Blender process is launched here.
Result-3 fixtures retain real recorded Part replay schemas; pair distances remain
synthetic and do not qualify native STEP geometry or installed-package behavior.
"""

import copy
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_arc_operation_contracts import arc_empty, legacy, sector
from test_assembly_bridge import Kernel as PairKernel
from test_assembly_bridge_v2 import Kernel as LegacyKernel
from test_assembly_bridge_v2 import bridge
from test_assembly_bridge_v2 import make as legacy_source
from test_assembly_bridge_v3 import Kernel as MixedKernel
from test_assembly_bridge_v3 import make as mixed_source
from test_assembly_bridge_v3 import seal

from mechanical_cad import assembly_service
from mechanical_cad.assembly_model import AssemblyDocument

export_bridge = importlib.import_module(bridge.__package__ + ".assembly_export_bridge")
operations = importlib.import_module(bridge.__package__ + ".operation_contracts")
contracts = importlib.import_module(bridge.__package__ + ".backend_contracts")
transport = importlib.import_module(bridge.__package__ + ".guarded_transport")


class Kernel(LegacyKernel, PairKernel):
    """Legacy strict typed-solid payloads with synthetic pair evidence."""


def _packet_factory(monkeypatch, version):
    if version == 2:
        raw_request, _, _ = legacy_source.__wrapped__(monkeypatch)(new_sketch=False)
        kernel = Kernel(new_sketch=False)
    else:
        source = mixed_source.__wrapped__(monkeypatch)
        raw_request, _, _ = source()
        kernel = MixedKernel(source.replays)
    raw = copy.deepcopy(raw_request["assembly"])
    # An unused definition is deliberately present: STEP counts only the distinct
    # Part identities actually referenced by instances, never all definitions.
    raw["parts"].append({**copy.deepcopy(raw["parts"][0]), "id": "unused"})
    raw["verification_presets"] = [
        {
            "id": "current",
            "name": "Current saved verification",
            "kind": "interference_only",
            "requirements": [],
            "policy": copy.deepcopy(bridge.DEFAULT_POLICY),
        }
    ]
    raw["active_verification_preset"] = "current"

    def make(*, state="passed", path="/tmp/requested assembly.step"):
        candidate = copy.deepcopy(raw)
        active_kernel = kernel
        if state == "unconfigured":
            candidate["active_verification_preset"] = None
        elif state == "clearance_failure":
            candidate["verification_presets"][0].update(
                kind="clearance",
                requirements=[
                    {
                        "id": "space",
                        "name": "Saved running clearance",
                        "instances": ["a", "root"],
                        "minimum_mm": 20,
                    }
                ],
            )
        elif state in {"incomplete", "geometry_failure"}:
            active_kernel = copy.copy(kernel)

            def unavailable(*args, **kwargs):
                raise RuntimeError("Synthetic geometry query unavailable.")

            if state == "incomplete":
                active_kernel.pair_check = unavailable
            else:
                active_kernel.manufacturing_check = unavailable
        operation = export_bridge.build_request(candidate, path, result_version=version)
        nested_request = export_bridge.check_request(operation)
        check = assembly_service.run_assembly_action(
            AssemblyDocument.from_dict(candidate),
            "assembly_check",
            result_version=version,
            kernel=active_kernel,
        )
        check.update(
            protocol_version=1,
            kind="assembly",
            assembly_protocol_version=1,
            input_fingerprint=bridge.fingerprint(nested_request),
        )
        result = {
            "protocol_version": 1,
            "kind": "assembly",
            "assembly_protocol_version": 1,
            "action": "assembly_export_step",
            "result_version": version,
            "input_fingerprint": bridge.fingerprint(operation),
            "ok": True,
            "error": None,
            "result": check,
            "export": {
                "format": "STEP",
                "units": "mm",
                "path": path,
                "atomic_write": True,
                "bytes_written": 1000,
                "definition_count": len({row["part_id"] for row in candidate["instances"]}),
                "instance_count": len(candidate["instances"]),
                "assembly_digest": check["result"]["assembly_digest"],
                "pose_digest": check["report"]["base_pose"]["pose_digest"],
                "preset_id": candidate["active_verification_preset"],
                "request_fingerprint": check["request_fingerprint"],
                "report_fingerprint": check["report_fingerprint"],
            },
        }
        return operation, result

    return make


def pair(monkeypatch, *, version=2, state="passed", path="/tmp/requested assembly.step"):
    """Reusable strict synthetic request/response for pure owner contract tests."""
    return _packet_factory(monkeypatch, version)(state=state, path=path)


@pytest.fixture(params=[2, 3], ids=["result2", "result3"])
def packet(request, monkeypatch):
    return _packet_factory(monkeypatch, request.param)


def reseal(response):
    """Update the public hash claims without repairing tampered semantic data."""
    seal(response["result"])
    if response["export"] is not None:
        for key in ("request_fingerprint", "report_fingerprint"):
            response["export"][key] = response["result"][key]


def test_exact_request_selection_and_nested_current_pose_check(packet):
    request, response = packet()
    assert set(request) == {
        "protocol_version",
        "kind",
        "assembly_protocol_version",
        "assembly",
        "action",
        "path",
        "result_version",
    }
    assert export_bridge.result_version_for(request["assembly"]) == request["result_version"]
    assert export_bridge.build_request(request["assembly"], request["path"]) == request
    nested = export_bridge.check_request(request)
    assert nested == {
        **{k: v for k, v in request.items() if k != "path"},
        "action": "assembly_check",
    }
    assert response["result"]["input_fingerprint"] == bridge.fingerprint(nested)
    assert response["export"]["request_fingerprint"] != bridge.fingerprint(nested)
    nested["assembly"]["name"] = "Detached nested request"
    assert request["assembly"]["name"] != "Detached nested request"


def test_validated_projection_is_plain_detached_json_without_display_authority(packet):
    request, response = packet()
    original = copy.deepcopy((request, response))
    accepted = operations.validate_response(request, response)
    assert type(accepted) is dict and type(accepted["result"]) is dict
    assert not hasattr(accepted, "request_snapshot")
    assert not hasattr(accepted["result"], "request_snapshot")
    assert accepted == response and accepted is not response
    assert (request, response) == original
    assert accepted["export"]["definition_count"] == len(request["assembly"]["parts"]) - 1
    accepted["result"]["result"]["canonical_assembly"]["name"] = "Detached response"
    assert response["result"]["result"]["canonical_assembly"]["name"] != "Detached response"


@pytest.mark.parametrize(
    "key", ["coordinates", "requirements", "policy", "samples", "preset_id", "extra"]
)
def test_request_forbids_even_null_overrides_and_extra_fields(packet, key):
    request, response = packet()
    request[key] = None
    response["input_fingerprint"] = bridge.fingerprint(request)
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)


@pytest.mark.parametrize("key", ["protocol_version", "assembly_protocol_version", "result_version"])
@pytest.mark.parametrize("value", [True, False, 1.0, "2", None])
def test_request_version_fields_require_exact_integers(packet, key, value):
    request, _ = packet()
    request[key] = value
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_request(request)


@pytest.mark.parametrize(
    "path",
    [
        None,
        True,
        Path("/tmp/model.step"),
        "",
        " ",
        "relative.step",
        "~/model.step",
        "/",
        "/tmp/",
        "/tmp/.",
        "/tmp/..",
        "/tmp/bad\0.step",
    ],
)
def test_export_path_must_be_an_explicit_absolute_string(packet, path):
    request, _ = packet()
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.build_request(request["assembly"], path)


def test_path_text_is_never_resolved_expanded_or_changed(packet):
    request, response = packet(path="/tmp/export/../exact name.STEP")
    assert export_bridge.validate_response(request, response)["export"]["path"] == request["path"]
    response["export"]["path"] = "/tmp/exact name.STEP"
    with pytest.raises(bridge.bridge.BridgeError, match="destination changed"):
        export_bridge.validate_response(request, response)


@pytest.mark.parametrize(
    "key,value",
    [
        ("protocol_version", True),
        ("assembly_protocol_version", True),
        ("result_version", True),
        ("kind", "part"),
        ("action", "assembly_check"),
        ("input_fingerprint", "0" * 64),
        ("ok", 1),
        ("extra", None),
        ("error", {"code": "failed", "message": "Contradiction"}),
        ("result", None),
        ("export", None),
    ],
)
def test_outer_reply_is_exact_and_request_bound(packet, key, value):
    request, response = packet()
    response[key] = value
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)


@pytest.mark.parametrize(
    "key,value",
    [
        ("format", "STL"),
        ("units", "m"),
        ("path", "/tmp/substituted.step"),
        ("path", True),
        ("atomic_write", 1),
        ("atomic_write", False),
        ("bytes_written", True),
        ("bytes_written", 0),
        ("bytes_written", 1.0),
        ("definition_count", True),
        ("definition_count", 99),
        ("instance_count", True),
        ("instance_count", 2),
        ("instance_count", 3.0),
        ("assembly_digest", "0" * 64),
        ("pose_digest", "0" * 64),
        ("preset_id", "substitute"),
        ("request_fingerprint", "0" * 64),
        ("report_fingerprint", "0" * 64),
        ("extra", None),
    ],
)
def test_receipt_fields_cannot_launder_another_export(packet, key, value):
    request, response = packet()
    response["export"][key] = value
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)


@pytest.mark.parametrize("key", ["result", "export", "error", "input_fingerprint"])
def test_outer_reply_cannot_omit_required_fields(packet, key):
    request, response = packet()
    del response[key]
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)


@pytest.mark.parametrize("state", ["unconfigured", "clearance_failure"])
def test_failed_or_unconfigured_check_cannot_be_masked_by_export_success(packet, state):
    request, response = packet(state=state)
    assert response["result"]["ok"] is True
    assert response["result"]["report"]["complete"] is True
    assert response["result"]["report"]["passed"] is False
    with pytest.raises(bridge.bridge.BridgeError, match="complete passed"):
        export_bridge.validate_response(request, response)
    response.update(
        ok=False,
        error={"code": "assembly_export_blocked", "message": "Check did not pass."},
        export=None,
    )
    assert export_bridge.validate_response(request, response) == response


def test_write_failure_keeps_the_complete_successful_check(packet):
    request, response = packet()
    response.update(
        ok=False,
        error={"code": "assembly_export_failed", "message": "Destination is unavailable."},
        export=None,
    )
    accepted = export_bridge.validate_response(request, response)
    assert accepted["result"]["report"]["passed"] is True
    assert accepted["export"] is None
    response["result"]["result"]["parts"][0]["geometry_check"]["brep"]["valid"] = False
    reseal(response)
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)


@pytest.mark.parametrize("state", ["incomplete", "geometry_failure"])
def test_failed_nested_check_stays_diagnostic_and_cannot_mint_export_success(packet, state):
    request, response = packet(state=state)
    assert response["result"]["ok"] is False
    assert response["result"]["report"]["complete"] is False
    with pytest.raises(bridge.bridge.BridgeError, match="complete passed"):
        export_bridge.validate_response(request, response)
    response.update(
        ok=False,
        error={"code": "assembly_export_blocked", "message": "No complete current check."},
        export=None,
    )
    assert export_bridge.validate_response(request, response) == response


@pytest.mark.parametrize(
    "error",
    [
        None,
        {},
        {"code": "failed"},
        {"code": True, "message": "bad"},
        {"code": "failed", "message": ""},
        {"code": "failed", "message": "bad", "extra": None},
    ],
)
def test_failure_requires_exact_bounded_code_message_without_receipt(packet, error):
    request, response = packet()
    response.update(ok=False, error=error, export=None)
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)


def test_failed_response_must_not_claim_a_written_export(packet):
    request, response = packet()
    response.update(ok=False, error={"code": "failed", "message": "Contradictory receipt."})
    with pytest.raises(bridge.bridge.BridgeError, match="contains an export"):
        export_bridge.validate_response(request, response)


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "geometry",
        "preset",
        "saved_pose",
        "nested_action",
        "nested_input",
        "nested_version",
        "pose_count",
        "pose_transforms",
    ],
)
def test_resealed_nested_check_cannot_substitute_sources_geometry_intent_or_pose(packet, change):
    request, response = packet()
    check = response["result"]
    if change == "source":
        check["result"]["source_replays"][0]["source_digest"] = "0" * 64
    elif change == "geometry":
        check["result"]["parts"][0]["geometry_check"]["brep"]["valid"] = False
    elif change == "preset":
        check["report"]["verification_basis"]["preset_id"] = "substitute"
    elif change == "saved_pose":
        check["report"]["poses"][0]["pose"]["effective_coordinates"]["slide_a"] += 1
    elif change == "nested_action":
        check["action"] = "assembly_replay"
    elif change == "nested_input":
        check["input_fingerprint"] = bridge.fingerprint(request)
    elif change == "nested_version":
        check["result_version"] = 3 if request["result_version"] == 2 else 2
    elif change == "pose_count":
        check["report"]["poses"].append(copy.deepcopy(check["report"]["poses"][0]))
    else:
        check["report"]["poses"][0]["pose"]["transforms"]["root"]["xyz_mm"][0] += 1
    reseal(response)
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)


def test_client_capabilities_require_new_export_gate_for_both_result_versions(packet):
    request, _ = packet()
    required = set(contracts.minimum_capabilities(request))
    expected = {contracts.BASELINE, contracts.SOLVER_GUARD, contracts.ASSEMBLY_STEP_EXPORT}
    if request["result_version"] == 3:
        expected |= {contracts.SKETCH_ARCS, "mcad.part-result/3", "mcad.assembly-result/3"}
    assert required == expected
    with pytest.raises(contracts.BackendContractError, match="minimum capabilities"):
        contracts.prepare_request(
            request, required_capabilities=sorted(required - {contracts.ASSEMBLY_STEP_EXPORT})
        )


def test_all_embedded_sources_require_explicit_result3_even_when_unused(monkeypatch):
    request, _ = pair(monkeypatch, version=3)
    request["assembly"]["instances"][1]["part_id"] = "block"
    assert export_bridge.result_version_for(request["assembly"]) == 3
    request["result_version"] = 2
    with pytest.raises(bridge.bridge.BridgeError, match="sources require result 3"):
        export_bridge.validate_request(request)


@pytest.mark.parametrize(
    "factories,expected", [([legacy], 2), ([sector], 3), ([legacy, sector], 3)]
)
def test_export_source_selection_matches_ordinary_assembly_policy(factories, expected):
    candidate = {
        "kind": "assembly",
        "assembly_schema_version": 1,
        "part_sources": [{"document": factory()} for factory in factories],
    }
    before = copy.deepcopy(candidate)
    assert export_bridge.result_version_for(candidate) == expected
    assert operations.result_version_for_assembly(candidate, action="assembly_check") == expected
    assert candidate == before


@pytest.mark.parametrize(
    "change",
    [
        "arc_empty",
        "profile_only",
        "second_arc",
        "full_circle",
        "third_line",
        "second_extrude",
        "wrong_source",
        "legacy_missing_source",
        "schema_bool",
        "schema_float",
    ],
)
def test_export_source_admission_matches_ordinary_assembly_policy(change):
    document = sector()
    sketch = document["features"][0]["sketch"]
    if change == "arc_empty":
        document = arc_empty()
    elif change == "profile_only":
        document["features"].pop()
        document["active_feature"] = document["features"][0]["id"]
    elif change == "second_arc":
        sketch["arcs"].append({**sketch["arcs"][0], "id": "second_arc"})
    elif change == "full_circle":
        sketch["circles"].append({"id": "circle", "center": "center", "radius": 5})
    elif change == "third_line":
        sketch["lines"].append({"id": "chord", "start": "start", "end": "end"})
    elif change == "second_extrude":
        document["features"].append({**copy.deepcopy(document["features"][1]), "id": "second"})
    elif change == "wrong_source":
        document["features"][1]["inputs"]["profile"] = "missing"
    elif change == "legacy_missing_source":
        document = legacy()
        document["features"][1]["inputs"]["profile"] = "missing"
    else:
        sketch["schema_version"] = True if change == "schema_bool" else 3.0
    candidate = {
        "kind": "assembly",
        "assembly_schema_version": 1,
        "part_sources": [{"document": legacy()}, {"document": document}],
    }
    before = copy.deepcopy(candidate)
    for selector in (export_bridge.result_version_for, operations.result_version_for_assembly):
        if change in {"arc_empty", "second_arc", "full_circle", "third_line", "second_extrude"}:
            # Version admission is not a geometry-validity or export receipt.
            assert selector(candidate) == 3
        else:
            with pytest.raises((ValueError, bridge.bridge.BridgeError)):
                selector(candidate)
    assert candidate == before


@pytest.mark.parametrize(
    "mutation",
    [
        {"kind": "part"},
        {"assembly_schema_version": True},
        {"assembly_schema_version": 1.0},
        {"part_sources": {}},
        {"part_sources": [None]},
        {"part_sources": [{}]},
    ],
)
def test_export_source_envelope_refusal_matches_ordinary_assembly_policy(mutation):
    candidate = {
        "kind": "assembly",
        "assembly_schema_version": 1,
        "part_sources": [{"document": legacy()}],
        **mutation,
    }
    for selector in (export_bridge.result_version_for, operations.result_version_for_assembly):
        with pytest.raises((ValueError, bridge.bridge.BridgeError)):
            selector(candidate)


def test_result3_nested_full_source_replay_cannot_be_forged(monkeypatch):
    request, response = pair(monkeypatch, version=3)
    response["result"]["result"]["source_replays"][1]["replay"]["document_hash"] = "0" * 64
    reseal(response)
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)


@pytest.mark.parametrize("version", [0, 1, 4, 2.0, "2", True])
def test_export_builder_refuses_legacy_or_untyped_result_versions(packet, version):
    request, _ = packet()
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.build_request(request["assembly"], request["path"], result_version=version)


@pytest.mark.parametrize("action", ["assembly_export_stl", "assembly_export_step_extra"])
def test_operation_dispatch_does_not_admit_other_assembly_export_actions(packet, action):
    request, response = packet()
    request["action"] = action
    with pytest.raises(ValueError, match="unsupported operation action"):
        operations.validate_response(request, response)


def test_legacy_assembly_action_sets_stay_closed(packet):
    request, _ = packet()
    old = {"assembly_replay", "assembly_check", "assembly_sample"}
    assert operations._ASSEMBLY_ACTIONS == old
    assert bridge.ACTIONS == old
    with pytest.raises(ValueError, match="unsupported Assembly action"):
        operations.result_version_for_assembly(request["assembly"], action="assembly_export_step")
    with pytest.raises(bridge.bridge.BridgeError):
        bridge.build_request(
            request["assembly"], "assembly_export_step", result_version=request["result_version"]
        )


@pytest.mark.parametrize(
    "action,uncertain",
    [
        ("assembly_export_step", True),
        ("export_step", True),
        ("export_stl", True),
        ("assembly_check", False),
        ("assembly_export_stl", False),
        ("assembly_export_step_extra", False),
    ],
)
def test_only_exact_export_actions_retain_unknown_write_outcome(action, uncertain):
    assert (
        bridge.bridge._transport_error({"action": action}, "Lost reply.").outcome_unknown
        is uncertain
    )
    job = object.__new__(transport.GuardedJob)
    job._action = action
    job._start_attempted = True
    job._historical_export = None
    assert job._error("Lost reply.").outcome_unknown is uncertain
    assert (
        job._error("Rejected.", failure=SimpleNamespace(definite_no_dispatch=True)).outcome_unknown
        is False
    )
    job._start_attempted = False
    assert job._error("Never launched.").outcome_unknown is False


def test_recursive_and_non_json_response_containers_fail_closed(packet):
    request, response = packet()
    response["loop"] = response
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)
    del response["loop"]
    response["export"]["bytes_written"] = float("nan")
    with pytest.raises(bridge.bridge.BridgeError):
        export_bridge.validate_response(request, response)
