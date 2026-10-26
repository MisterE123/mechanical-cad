"""Combined response validation preserves bounds and detached output ownership."""
import copy

import pytest
from test_backend_contract_client import client, operation, receipt_response, selection


@pytest.mark.parametrize("rejected", [False, True])
def test_combined_matches_standalone_apis(rejected):
    guarded = client.prepare_request(operation()).guarded_request()
    response = receipt_response(guarded, rejected=rejected)
    response["extra"] = {"preserved": []}
    # Unknown result fields survive stripping for the action validator to reject.
    if rejected:
        response.pop("extra")
    receipt, projected = client.validate_receipt_and_project(guarded, response, selection())
    assert receipt == client.validate_receipt(guarded, response, selection())
    assert projected == client.project_response(response)


def test_shared_input_dag_does_not_alias_receipt_projection_or_input():
    guarded = client.prepare_request(operation()).guarded_request()
    response = receipt_response(guarded)
    version = response["backend_receipt"]["backend"]["python_version"]
    response["result"] = {"aliased": version}
    receipt, projected = client.validate_receipt_and_project(guarded, response, selection())
    receipt["backend"]["python_version"][0] = 99
    assert projected["result"]["aliased"] == version == [3, 12, 14]
    projected["result"]["aliased"][1] = 99
    assert receipt["backend"]["python_version"] == [99, 12, 14]
    assert version == [3, 12, 14]
    version[2] = 99
    assert projected["result"]["aliased"] == [3, 99, 14]


def test_dispatched_combined_walks_full_response_once(monkeypatch):
    guarded = client.prepare_request(operation()).guarded_request()
    response = receipt_response(guarded)
    calls = []
    original = client.response_snapshot
    def counted(value):
        calls.append(1)
        return original(value)
    monkeypatch.setattr(client, "response_snapshot", counted)
    client.validate_receipt_and_project(guarded, response, selection())
    assert calls == [1]


@pytest.mark.parametrize("damage", ["cycle", "non_json", "depth", "bytes", "receipt_bytes"])
def test_combined_retains_original_resource_checks(monkeypatch, damage):
    guarded = client.prepare_request(operation()).guarded_request()
    response = receipt_response(guarded)
    if damage == "cycle":
        response["extra"] = response
    elif damage == "non_json":
        response["extra"] = object()
    elif damage == "depth":
        nested = response
        for _ in range(40):
            nested["extra"] = {}
            nested = nested["extra"]
    elif damage == "bytes":
        monkeypatch.setattr(client.request_contracts, "MAX_RESPONSE_BYTES", 32)
    else:
        monkeypatch.setattr(client, "MAX_RECEIPT_BYTES", 32)
    with pytest.raises(client.BackendContractError):
        client.validate_receipt_and_project(guarded, response, selection())


def test_response_mutation_cannot_change_detached_projection():
    guarded = client.prepare_request(operation()).guarded_request()
    response = receipt_response(guarded)
    response["extra"] = [1]
    receipt, projection = client.validate_receipt_and_project(guarded, response, selection())
    expected = copy.deepcopy((receipt, projection))
    response["extra"].append(2)
    response["backend_receipt"]["backend"]["python_version"].append(9)
    assert (receipt, projection) == expected
