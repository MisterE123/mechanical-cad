"""New explicit assembly requests preserve the existing Part process contract."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.assembly_policy import fingerprint
from mechanical_cad.errors import CADException
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.kernel


def request():
    assembly = AssemblyDocument.from_json(
        (ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()
    )
    return {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "assembly": assembly.to_dict(),
        "action": "assembly_check",
        "coordinates": {"slide_a": 100, "slide_b": 200},
        "requirements": [],  # Explicit interference-only intent, not an inferred pass policy.
    }


def process(raw):
    result = subprocess.run(
        [sys.executable, "-m", "mechanical_cad.sidecar"],
        input=raw,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    return result, json.loads(result.stdout)


def test_new_assembly_process_exact_request_and_single_json_response():
    candidate = request()
    result, response = process(json.dumps(candidate))
    assert result.returncode == 0, result.stderr
    assert response["ok"] and response["kind"] == "assembly"
    assert response["assembly_protocol_version"] == 1
    assert response["input_fingerprint"] == fingerprint(candidate)
    canonical = AssemblyDocument.from_dict(response["result"]["canonical_assembly"])
    assert canonical.content_hash == response["result"]["assembly_digest"]
    assert response["report"]["complete"] and response["report"]["passed"]
    assert response["report"]["base_pose"]["effective_coordinates"] == candidate["coordinates"]
    assert len(response["request_fingerprint"]) == len(response["report_fingerprint"]) == 64


@pytest.mark.parametrize(
    "key,value",
    [
        ("assembly_protocol_version", True),
        ("assembly_protocol_version", 2),
        ("kind", "part"),
        ("destination", "/tmp/unrequested.step"),
        ("document", {}),
        ("options", {}),
        ("action", "export_step"),
        ("action", None),
    ],
)
def test_assembly_envelope_strict_and_no_hidden_file_output(key, value):
    candidate = request()
    candidate[key] = value
    with pytest.raises(CADException):
        process_request(candidate)


def test_invalid_full_base_is_blocked_before_native_replay_and_fingerprinted():
    candidate = request()
    candidate.update(
        action="assembly_sample",
        coordinates={"slide_a": 100},
        samples={"joint_id": "slide_a", "values": [0, 10]},
    )
    result, response = process(json.dumps(candidate))
    assert result.returncode == 1
    assert response["error"]["code"] == "incomplete_base_pose"
    assert response["request"]["requested_coordinates"] == {"slide_a": 100}
    assert response["request"]["samples"] == candidate["samples"]
    assert response["report_fingerprint"] and not response["result"]["source_replays"]


def test_duplicate_embedded_json_keys_rejected_at_process_boundary():
    candidate = json.dumps(request())
    candidate = candidate.replace('"slide_a": 100', '"slide_a": 99, "slide_a": 100')
    result, response = process(candidate)
    assert result.returncode == 1 and not response["ok"]
    assert response["error"]["code"] in {"duplicate_key", "invalid_json"}


def test_legacy_part_envelope_still_uses_original_response_without_assembly_fields():
    candidate = request()
    original = copy.deepcopy(candidate["assembly"]["part_sources"][0]["document"])
    response = process_request({"protocol_version": 1, "document": original})
    assert response["ok"] and response["result"]["document_hash"]
    assert "kind" not in response and "assembly_protocol_version" not in response
    assert original == candidate["assembly"]["part_sources"][0]["document"]


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_nonfinite_wire_numbers_are_invalid_json_not_generic_sidecar_error(token):
    raw = json.dumps(request()).replace('"slide_a": 100', '"slide_a": ' + token)
    result, response = process(raw)
    assert result.returncode == 1
    assert response["error"]["code"] == "invalid_json"


def test_assembly_wire_numeric_tokens_obey_same_loader_limit():
    raw = json.dumps(request()).replace('"slide_a": 100', '"slide_a": 1.' + "0" * 129)
    result, response = process(raw)
    assert result.returncode == 1
    assert response["error"]["code"] == "resource_limit"
