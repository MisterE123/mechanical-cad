"""Portable data leaves; legacy process/admission integration stays Linux-owned."""

import json

import pytest
import test_bridge_sketch_reports as reports
import test_sidecar_job as manual


def parameters(function):
    return next(mark for mark in function.pytestmark if mark.name == "parametrize")


def validate(document, response):
    return reports.bridge._validate_sketch_report(
        response["result"]["features"][0], document["features"][0]
    )


@pytest.mark.parametrize(*parameters(reports.test_malformed_success_report_fails_closed).args)
def test_portable_sketch_report_mutations_reject_after_clean_positive(change):
    document, response, report = reports.payload()
    validate(document, response)
    change(report)
    with pytest.raises((ValueError, TypeError, KeyError)):
        validate(document, response)


def test_portable_sketch_failure_and_missing_diagnostics_keep_original_rules():
    document, response, report = reports.payload()
    validate(document, response)
    feature = response["result"]["features"][0]
    feature["status"] = "failed"
    report.update(
        status="inconsistent",
        remaining_dof=None,
        solved=None,
        max_residual_mm=None,
        failed_constraints=["width"],
    )
    validate(document, response)
    report["remaining_dof"] = 3
    with pytest.raises(ValueError, match="failed sketch"):
        validate(document, response)
    feature["sketch"] = None
    validate(document, response)
    feature["status"] = "ok"
    with pytest.raises(ValueError, match="missing its solve report"):
        validate(document, response)


@pytest.mark.parametrize(
    *parameters(manual.test_nonfinite_or_nonexact_json_rejected_before_launch).args
)
def test_portable_request_snapshot_rejects_nonfinite_or_nonexact_json(invalid_request):
    assert manual.transport.snapshot_request({"value": 1}) == {"value": 1}
    with pytest.raises(manual.BridgeError):
        manual.transport.snapshot_request(invalid_request)


@pytest.mark.parametrize(
    *parameters(manual.test_preflight_size_matches_exact_default_json_bytes).args
)
def test_portable_request_snapshot_keeps_exact_byte_limit(monkeypatch, value):
    request = {"value": value}
    expected = json.dumps(request, allow_nan=False).encode("utf-8")
    monkeypatch.setattr(manual.transport, "MAX_DOCUMENT_BYTES", len(expected))
    snapshot = manual.transport.snapshot_request(request)
    assert json.dumps(snapshot, allow_nan=False).encode("utf-8") == expected
    monkeypatch.setattr(manual.transport, "MAX_DOCUMENT_BYTES", len(expected) - 1)
    with pytest.raises(manual.BridgeError, match="2 MiB input limit"):
        manual.transport.snapshot_request(request)


@pytest.mark.parametrize("case", ["cycle", "shared_dag", "string", "integer"])
def test_portable_request_preflight_rejects_bounded_resources(case):
    value = [0]
    if case == "cycle":
        value.append(value)
    elif case == "shared_dag":
        for _ in range(32):
            value = [value, value]
    elif case == "string":
        value = "x" * (manual.transport.MAX_DOCUMENT_BYTES + 1)
    else:
        value = 1 << (manual.transport.MAX_INTEGER_BITS + 1)
    assert manual.transport.snapshot_request({"value": [0]}) == {"value": [0]}
    with pytest.raises(manual.BridgeError):
        manual.transport.snapshot_request({"value": value})


def test_portable_request_snapshot_detaches_shared_containers_without_wire_changes():
    shared = {"coordinates": [1.5, 2.5, None], "label": "\u677f"}
    request = {"left": shared, "right": shared}
    expected = json.dumps(request, allow_nan=False).encode("utf-8")
    snapshot = manual.transport.snapshot_request(request)
    assert snapshot == request and snapshot["left"] is not shared
    assert snapshot["left"]["coordinates"] is not shared["coordinates"]
    shared["coordinates"].append(999)
    assert json.dumps(snapshot, allow_nan=False).encode("utf-8") == expected
