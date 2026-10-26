"""Pure result contracts do not depend on their transport compatibility adapters."""

import copy
import hashlib
import importlib
import json
import sys
import types
import uuid
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"


@pytest.fixture
def package():
    name = "mcad_pure_contracts_" + uuid.uuid4().hex
    module = types.ModuleType(name)
    module.__path__ = [str(ADDON)]
    sys.modules[name] = module
    yield name
    for imported in list(sys.modules):
        if imported == name or imported.startswith(name + "."):
            del sys.modules[imported]


def document():
    return {
        "schema_version": 1,
        "id": "document",
        "name": "Part",
        "units": "mm",
        "parameters": {},
        "features": [
            {"id": "profile", "kind": "sketch_rectangle", "params": {"width": 10, "height": 5}},
            {
                "id": "pad",
                "kind": "extrude",
                "params": {"length": 2},
                "inputs": {"profile": "profile"},
            },
        ],
        "active_feature": "pad",
    }


def test_pure_result_boundaries_do_not_import_transports(package):
    for name in (
        "request_contracts",
        "part_contracts",
        "sketch_action_bridge",
        "part_result_bridge",
    ):
        importlib.import_module(package + "." + name)
    assert all(
        package + "." + name not in sys.modules
        for name in ("bridge", "sidecar_job", "part_snapshot_bridge")
    )


def test_snapshot_compatibility_reexports_share_one_serializer_and_normalizer(package):
    contracts = importlib.import_module(package + ".part_contracts")
    snapshot = importlib.import_module(package + ".part_snapshot_bridge")
    for name in (
        "_json",
        "_keys",
        "_normalize_sketch",
        "_normalize_sketch_v1",
        "_numeric",
        "_require",
        "_vector",
        "normalize_sketch_v2",
    ):
        assert getattr(snapshot, name) is getattr(contracts, name)
    raw = document()
    canonical = contracts._expected_document(raw)
    assert canonical == snapshot._expected_document(raw)
    assert "label" not in raw["features"][0]
    assert canonical["features"][0]["label"] == "profile"
    encoded = json.dumps(canonical, sort_keys=True, indent=2, allow_nan=False) + "\n"
    assert contracts.document_hash(canonical) == hashlib.sha256(encoded.encode()).hexdigest()
    assert contracts.input_fingerprint(raw) == snapshot.input_fingerprint(raw)
    assert snapshot.contracts is contracts
    assert snapshot.canonical_equivalent(raw, canonical)
    assert contracts.canonical_equivalent(raw, canonical)
    changed = copy.deepcopy(canonical)
    changed["features"][1]["params"]["length"] += 1
    assert not snapshot.canonical_equivalent(raw, changed)
    assert not contracts.canonical_equivalent(raw, changed)


def test_legacy_equivalence_dispatches_to_the_identical_leaf_implementation(package, monkeypatch):
    contracts = importlib.import_module(package + ".part_contracts")
    snapshot = importlib.import_module(package + ".part_snapshot_bridge")
    raw, canonical = document(), contracts._expected_document(document())
    calls, sentinel = [], object()

    def leaf(actual_raw, actual_canonical):
        assert actual_raw is raw and actual_canonical is canonical
        calls.append((actual_raw, actual_canonical))
        return sentinel

    monkeypatch.setattr(contracts, "canonical_equivalent", leaf)
    assert snapshot.canonical_equivalent(raw, canonical) is sentinel
    assert calls == [(raw, canonical)]


def test_sector_equivalence_is_bounded_and_keeps_legacy_leaf_schema_limit(package):
    contracts = importlib.import_module(package + ".part_contracts")
    snapshot = importlib.import_module(package + ".part_snapshot_bridge")
    path = (
        ADDON.parents[1]
        / "tests/fixtures/arc_authoring_evidence/radius_edit_5_0_replay.operation.json"
    )
    raw = json.loads(path.read_text())["document"]
    raw["features"][0]["sketch"]["points"].reverse()
    before = copy.deepcopy(raw)
    canonical = snapshot._expected_document(raw)
    assert snapshot.canonical_equivalent(raw, canonical)
    assert raw == before
    assert not contracts.canonical_equivalent(raw, canonical)
    with pytest.raises(ValueError):
        contracts._expected_document(raw)
    changed = copy.deepcopy(canonical)
    changed["parameters"]["radius"] += 1
    assert not snapshot.canonical_equivalent(raw, changed)
    for unsupported in ("profile_only", "arc_empty"):
        candidate = copy.deepcopy(raw)
        if unsupported == "profile_only":
            candidate["features"] = candidate["features"][:1]
            candidate["active_feature"] = candidate["features"][0]["id"]
        else:
            candidate["features"][0]["sketch"]["arcs"] = []
            candidate["features"][0]["sketch"]["constraints"] = []
        assert not snapshot.canonical_equivalent(candidate, candidate)


@pytest.mark.parametrize(
    "entry_point",
    (
        "snapshot_request",
        "input_fingerprint",
        "_expected_document",
        "canonical_snapshot",
        "validate_response",
    ),
)
def test_legacy_request_resource_failures_keep_bridge_error(package, entry_point):
    contracts = importlib.import_module(package + ".request_contracts")
    snapshot = importlib.import_module(package + ".part_snapshot_bridge")
    request = {}
    request["cycle"] = request
    with pytest.raises(contracts.RequestError) as pure_error:
        contracts.snapshot_request(request)
    function = getattr(
        snapshot.sidecar_job if entry_point == "snapshot_request" else snapshot, entry_point
    )
    arguments = (request, {}) if entry_point == "validate_response" else (request,)
    with pytest.raises(snapshot.bridge.BridgeError) as legacy_error:
        function(*arguments)
    assert type(legacy_error.value) is snapshot.bridge.BridgeError
    assert str(legacy_error.value) == str(pure_error.value)
    assert not snapshot.canonical_equivalent(request, document())


def test_snapshot_response_compatibility_keeps_transport_limits(package, monkeypatch):
    snapshot = importlib.import_module(package + ".part_snapshot_bridge")
    monkeypatch.setattr(snapshot.bridge, "MAX_RESPONSE_BYTES", 20)
    with pytest.raises(ValueError, match="response limit"):
        snapshot._bounded_response({"text": "x" * 21})
    monkeypatch.setattr(snapshot.sidecar_job, "MAX_INTEGER_BITS", 4)
    with pytest.raises(ValueError, match="numeric resource limit"):
        snapshot._bounded_response({"number": 32})
