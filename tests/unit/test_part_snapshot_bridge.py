"""Canonical capture receipts are native-free, detached, and fail closed."""

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.model import Document
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
PACKAGE = "mcad_part_snapshot_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(
    PACKAGE + ".part_snapshot_bridge", ADDON / "part_snapshot_bridge.py"
)
snapshot = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = snapshot
spec.loader.exec_module(snapshot)
bridge = snapshot.bridge


LINUX_LEGACY_PROFILE = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux legacy real-process or mocked decoder/admission integration"
)


def raw_document():
    return json.loads(
        (ROOT / "examples/regressions/viewport_schema2_capture.mcad.json").read_text()
    )


def request(document=None):
    return {
        "protocol_version": 1,
        "action": "canonical_snapshot",
        "document": raw_document() if document is None else document,
    }


def reseal(response):
    """Even a self-consistent forged hash cannot authorize changed source intent."""
    result = response["result"]
    result["canonical_json"] = (
        json.dumps(result["canonical_document"], sort_keys=True, indent=2) + "\n"
    )
    result["content_hash"] = hashlib.sha256(result["canonical_json"].encode()).hexdigest()


def test_capture_uses_existing_transport_and_returns_detached_authoritative_receipt(monkeypatch):
    raw = raw_document()
    before = copy.deepcopy(raw)
    calls = []
    replies = []

    def exchange(candidate, **kwargs):
        calls.append((candidate, kwargs))
        reply = process_request(candidate)
        replies.append(reply)
        return reply

    monkeypatch.setattr(bridge, "_exchange_raw", exchange)
    receipt = snapshot.canonical_snapshot(
        raw, project_root="root", python_executable="python", timeout=37
    )
    assert calls == [
        (request(raw), {"project_root": "root", "python_executable": "python", "timeout": 37})
    ]
    assert set(receipt) == {
        "canonical_document",
        "canonical_json",
        "content_hash",
        "document_id",
        "schema_version",
        "input_fingerprint",
    }
    assert receipt["canonical_json"] == Document.from_dict(raw).to_json()
    assert receipt["content_hash"] == Document.from_dict(raw).content_hash
    assert snapshot.canonical_equivalent(raw, receipt["canonical_document"])
    receipt["canonical_document"]["name"] = "changed detached copy"
    assert raw == before
    assert replies[0]["result"]["canonical_document"]["name"] == before["name"]
    assert calls[0][0]["document"] is not raw


@LINUX_LEGACY_PROFILE
def test_real_process_capture_with_current_interpreter():
    raw = raw_document()
    receipt = snapshot.canonical_snapshot(
        raw, project_root=str(ROOT), python_executable=sys.executable
    )
    assert receipt["content_hash"] == Document.from_dict(raw).content_hash
    assert snapshot.canonical_equivalent(raw, receipt["canonical_document"])


@pytest.mark.parametrize(
    "change",
    [
        "fingerprint",
        "action",
        "protocol",
        "bool_protocol",
        "document_id",
        "schema",
        "bool_schema",
        "hash",
        "json_whitespace",
        "json_duplicate",
        "extra_envelope",
        "missing_envelope",
        "ok",
        "error",
        "extra_result",
        "missing_result",
    ],
)
def test_wrong_or_malformed_envelope_identity_and_bytes_are_rejected(change):
    candidate = request()
    response = process_request(candidate)
    result = response["result"]
    if change == "fingerprint":
        response["input_fingerprint"] = "0" * 64
    elif change == "action":
        response["action"] = "replay"
    elif change == "protocol":
        response["protocol_version"] = 2
    elif change == "bool_protocol":
        response["protocol_version"] = True
    elif change == "document_id":
        result["document_id"] = "another document"
    elif change == "schema":
        result["schema_version"] = 1
    elif change == "bool_schema":
        result["schema_version"] = True
    elif change == "hash":
        result["content_hash"] = "f" * 64
    elif change == "json_whitespace":
        result["canonical_json"] += " "
        result["content_hash"] = hashlib.sha256(result["canonical_json"].encode()).hexdigest()
    elif change == "json_duplicate":
        result["canonical_json"] = result["canonical_json"].replace(
            '"schema_version": 2', '"schema_version": 1, "schema_version": 2'
        )
        result["content_hash"] = hashlib.sha256(result["canonical_json"].encode()).hexdigest()
    elif change == "extra_envelope":
        response["geometry"] = {}
    elif change == "missing_envelope":
        del response["action"]
    elif change == "ok":
        response["ok"] = 1
    elif change == "error":
        response["error"] = {"code": "contradiction", "message": "should not be here"}
    elif change == "extra_result":
        result["solver"] = "unrequested"
    else:
        del result["canonical_document"]
    with pytest.raises(bridge.BridgeError, match="Invalid canonical Part snapshot"):
        snapshot.validate_response(candidate, response)


@pytest.mark.parametrize(
    "change",
    [
        "id",
        "name",
        "parameters",
        "expression",
        "parameter_type",
        "seed",
        "point_id",
        "constraint_id",
        "constraint_refs",
        "feature_order",
        "record_order",
        "numeric_type",
        "extra",
        "schema",
    ],
)
def test_self_consistent_forged_documents_never_silently_change_authored_intent(change):
    candidate = request()
    response = process_request(candidate)
    canonical = response["result"]["canonical_document"]
    sketch = canonical["features"][0]["sketch"]
    if change == "id":
        canonical["id"] = response["result"]["document_id"] = "another"
    elif change == "name":
        canonical["name"] = "renamed without permission"
    elif change == "parameters":
        canonical["parameters"]["sketch_1_width"] = "13"
    elif change == "expression":
        canonical["features"][1]["params"]["length"] = "extrude_1_length + 0"
    elif change == "parameter_type":
        canonical["parameters"]["extrude_1_length"] = 4
    elif change == "seed":
        sketch["points"][0]["u"] += 1
    elif change == "point_id":
        sketch["points"][0]["id"] = "new_point"
    elif change == "constraint_id":
        sketch["constraints"][0]["id"] = "new_constraint"
    elif change == "constraint_refs":
        sketch["constraints"][-1]["refs"].reverse()
    elif change == "feature_order":
        canonical["features"].reverse()
    elif change == "record_order":
        sketch["constraints"].reverse()
    elif change == "numeric_type":
        sketch["points"][0]["v"] = 0
    elif change == "extra":
        canonical["unrecognized"] = True
    else:
        canonical["schema_version"] = response["result"]["schema_version"] = 1
    reseal(response)
    with pytest.raises(bridge.BridgeError):
        snapshot.validate_response(candidate, response)
    assert not snapshot.canonical_equivalent(candidate["document"], canonical)


def test_stale_raw_fingerprint_rejected_even_when_both_inputs_have_same_canonical_hash():
    raw_request = request()
    response = process_request(raw_request)
    canonical_request = request(response["result"]["canonical_document"])
    assert (
        process_request(canonical_request)["result"]["content_hash"]
        == response["result"]["content_hash"]
    )
    with pytest.raises(bridge.BridgeError, match="raw request fingerprint"):
        snapshot.validate_response(canonical_request, response)


def test_known_optional_defaults_and_numeric_conversions_are_allowed_only_where_core_uses_them():
    raw = raw_document()
    del raw["active_feature"]
    for feature in raw["features"]:
        del feature["label"]
    del raw["features"][0]["params"]
    del raw["features"][0]["inputs"]
    sketch = raw["features"][0]["sketch"]
    sketch["plane"]["origin"] = [0, 0, 0]
    sketch["plane"]["quaternion"] = [1, 0, 0, 0]
    sketch["points"][0]["v"] = 0
    sketch["constraints"][0]["target"][1] = 0
    sketch["constraints"][-1]["value"] = 8
    for field in ("points", "lines", "constraints"):
        sketch[field].reverse()
    candidate = request(raw)
    receipt = snapshot.validate_response(candidate, process_request(candidate))
    assert snapshot.canonical_equivalent(raw, receipt["canonical_document"])
    assert receipt["canonical_document"]["active_feature"] is None
    assert type(receipt["canonical_document"]["features"][0]["sketch"]["points"][0]["v"]) is float
    primitive = {
        "schema_version": 1,
        "id": "primitive",
        "name": "Primitive",
        "units": "mm",
        "parameters": {},
        "features": [
            {"id": "rectangle", "kind": "sketch_rectangle", "params": {"width": 12, "height": 8}}
        ],
    }
    receipt = snapshot.validate_response(request(primitive), process_request(request(primitive)))
    assert snapshot.canonical_equivalent(primitive, receipt["canonical_document"])
    assert receipt["canonical_document"]["features"][0]["params"]["x"] == 0


def test_pure_equivalence_does_not_use_transport_cache_or_mutate_inputs(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("pure comparator must never start a process")

    monkeypatch.setattr(bridge, "_exchange_raw", forbidden)
    raw = raw_document()
    canonical = Document.from_dict(raw).to_dict()
    before = copy.deepcopy((raw, canonical))
    assert snapshot.canonical_equivalent(raw, canonical)
    assert (raw, canonical) == before
    raw["parameters"]["sketch_1_width"] = "36"
    assert not snapshot.canonical_equivalent(raw, canonical)
    raw["parameters"]["sketch_1_width"] = "12"
    assert snapshot.canonical_equivalent(raw, canonical)


@pytest.mark.parametrize("malformation", [None, [], {"id": "incomplete"}, "text"])
def test_malformed_documents_are_not_equivalent_and_never_enter_transport(
    monkeypatch, malformation
):
    monkeypatch.setattr(
        bridge, "_exchange_raw", lambda *args, **kwargs: pytest.fail("unexpected process")
    )
    canonical = Document.from_dict(raw_document()).to_dict()
    assert not snapshot.canonical_equivalent(malformation, canonical)
    assert not snapshot.canonical_equivalent(canonical, malformation)
    with pytest.raises(bridge.BridgeError):
        snapshot.canonical_snapshot(malformation)


def test_failure_response_is_actionable_but_cannot_create_receipt():
    response = {
        "protocol_version": 1,
        "ok": False,
        "result": None,
        "error": {"code": "invalid_document", "message": "Unknown authored field"},
    }
    with pytest.raises(bridge.BridgeError, match="invalid_document: Unknown authored field"):
        snapshot.validate_response(request(), response)
    response["result"] = {}
    with pytest.raises(bridge.BridgeError, match="invalid snapshot failure"):
        snapshot.validate_response(request(), response)


@pytest.mark.parametrize("duplicate", ["envelope", "nested"])
@LINUX_LEGACY_PROFILE
def test_duplicate_wire_response_keys_are_rejected_by_existing_transport(monkeypatch, duplicate):
    candidate = request()
    raw = json.dumps(process_request(candidate))
    if duplicate == "envelope":
        raw = raw.replace('"ok": true', '"ok": false, "ok": true', 1)
    else:
        raw = raw.replace('"schema_version": 2', '"schema_version": 1, "schema_version": 2', 1)
    monkeypatch.setattr(
        bridge.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, raw, ""),
    )
    with pytest.raises(bridge.BridgeError, match="invalid JSON"):
        snapshot.canonical_snapshot(
            candidate["document"], project_root=str(ROOT), python_executable=sys.executable
        )


@pytest.mark.parametrize("duplicate", ["envelope", "nested"])
def test_duplicate_wire_keys_reject_in_real_parser_after_clean_snapshot_positive(duplicate):
    candidate = request()
    before = copy.deepcopy(candidate)
    clean = json.dumps(process_request(candidate), allow_nan=False)
    decoded = bridge.parse_document_json(clean, require_object=False)
    receipt = snapshot.validate_response(candidate, decoded)
    assert receipt["content_hash"] == Document.from_dict(candidate["document"]).content_hash
    if duplicate == "envelope":
        key, original, replacement = "ok", '"ok": true', '"ok": false, "ok": true'
    else:
        key, original, replacement = (
            "schema_version",
            '"schema_version": 2',
            '"schema_version": 1, "schema_version": 2',
        )
    assert original in clean
    ambiguous = clean.replace(original, replacement, 1)
    assert ambiguous != clean
    with pytest.raises(bridge.BridgeError, match="^Duplicate JSON key: " + key + "$"):
        bridge.parse_document_json(ambiguous, require_object=False)
    assert candidate == before


def test_bridge_import_never_imports_bpy_or_core_even_without_site_packages(tmp_path):
    script = f"""
import builtins, importlib.util, sys, types
original = builtins.__import__
def isolated(name, *args, **kwargs):
    if name.split(".")[0] in ("bpy", "OCP", "slvs", "cadquery", "mechanical_cad"):
        raise AssertionError("forbidden Blender-side native/core import: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = isolated
package = types.ModuleType("isolated_addon")
package.__path__ = [{str(ADDON)!r}]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location("isolated_addon.part_snapshot_bridge", {str(ADDON / "part_snapshot_bridge.py")!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.canonical_equivalent(None, None) is False
print("NATIVE_FREE_SNAPSHOT_BRIDGE")
"""
    result = subprocess.run(
        [sys.executable, "-S", "-B", "-c", script],
        cwd=tmp_path,
        env=dict(os.environ),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "NATIVE_FREE_SNAPSHOT_BRIDGE"


def hostile_tree(kind):
    if kind == "cycle":
        value = []
        value.append(value)
        return value
    if kind == "shared_dag":
        value = [0]
        for _ in range(20):
            value = [value] * 16
        return value
    if kind == "deep":
        value = 0
        for _ in range(80):
            value = [value]
        return value
    if kind == "huge_integer":
        return 1 << 20_000
    return "\u2603" * 400_000


@pytest.mark.parametrize("kind", ["cycle", "shared_dag", "deep", "huge_integer", "escaped_bytes"])
def test_raw_preflight_rejects_resource_attacks_before_transport_or_encoding(monkeypatch, kind):
    raw = raw_document()
    canonical = Document.from_dict(raw).to_dict()
    raw["parameters"]["hostile"] = hostile_tree(kind)
    monkeypatch.setattr(snapshot, "_json", lambda *a, **kw: pytest.fail("unbounded encoding"))
    monkeypatch.setattr(bridge, "_exchange_raw", lambda *a, **kw: pytest.fail("unexpected process"))
    with pytest.raises(bridge.BridgeError):
        snapshot.canonical_snapshot(raw)
    with pytest.raises(bridge.BridgeError):
        snapshot.input_fingerprint(request(raw))
    assert not snapshot.canonical_equivalent(raw, canonical)
    with pytest.raises(bridge.BridgeError):
        snapshot.validate_response(request(raw), {})


@pytest.mark.parametrize("kind", ["cycle", "shared_dag", "deep", "huge_integer"])
def test_direct_response_resource_guard_precedes_recursion_copy_and_encoding(monkeypatch, kind):
    candidate = request()
    response = process_request(candidate)
    response["result"]["canonical_document"]["parameters"]["hostile"] = hostile_tree(kind)
    monkeypatch.setattr(snapshot, "_json", lambda *a, **kw: pytest.fail("unbounded encoding"))
    with pytest.raises(bridge.BridgeError):
        snapshot.validate_response(candidate, response)


def test_response_budget_is_deliberately_larger_than_request_budget():
    # Canonical indented text/object can be larger than raw compact input.
    # Resource preflight uses the actual response limit; shape/intent validation
    # still rejects unsupported content afterward.
    oversized_for_request = {"text": "a" * (bridge.MAX_DOCUMENT_BYTES + 100)}
    snapshot._bounded_response(oversized_for_request)
    with pytest.raises(bridge.BridgeError, match="input limit"):
        snapshot.sidecar_job.snapshot_request(oversized_for_request)


def test_response_expanded_size_bound_rejects_large_shared_strings():
    shared = {"text": "a" * (1024 * 1024)}
    response = {"copies": [shared] * 65}
    with pytest.raises(ValueError, match="64 MiB"):
        snapshot._bounded_response(response)
