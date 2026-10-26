"""Real OCP source replay determinism: changed geometry need not change poses."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
package = types.ModuleType("source_preview_geometry_addon")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
contract = importlib.import_module(package.__name__ + ".assembly_source_preview_contract")
bridge = importlib.import_module(package.__name__ + ".assembly_bridge")
edit = importlib.import_module(package.__name__ + ".assembly_edit")


def replay(assembly):
    request = {
        "protocol_version": 1,
        "assembly_protocol_version": 1,
        "kind": "assembly",
        "action": "assembly_replay",
        "result_version": 3,
        "assembly": assembly,
    }
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_response(request, response)
    return response


def test_repeated_exact_source_update_projection_is_deterministic_and_geometry_sensitive():
    original = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    before = copy.deepcopy(original)
    source = copy.deepcopy(original["part_sources"][0]["document"])
    source["parameters"]["width"] = 20
    candidate, affected = edit.update_source(original, source)
    assert set(affected) == {"root", "a", "b"}
    initial, preview, repeated = replay(original), replay(candidate), replay(candidate)
    expected = contract.source_preview_fingerprint(preview)
    assert contract.source_preview_fingerprint(repeated) == expected
    contract.require_source_preview(repeated, expected)
    assert initial["report"]["base_pose"]["transforms"] == preview["report"]["base_pose"]["transforms"]
    assert initial["report"]["base_pose"]["effective_coordinates"] == preview["report"]["base_pose"]["effective_coordinates"]
    assert initial["result"]["parts"][0]["geometry_check"]["brep"]["volume"] == pytest.approx(1000)
    assert preview["result"]["parts"][0]["geometry_check"]["brep"]["volume"] == pytest.approx(2000)
    assert contract.source_preview_fingerprint(initial) != expected
    with pytest.raises(bridge.bridge.BridgeError, match="differs"):
        contract.require_source_preview(initial, expected)
    assert original == before
    # A second source edit leaves the same pose but cannot borrow the first preview.
    source["parameters"]["width"] = 25
    later, _ = edit.update_source(original, source)
    changed = replay(later)
    assert changed["report"]["base_pose"]["transforms"] == preview["report"]["base_pose"]["transforms"]
    assert changed["report"]["base_pose"]["effective_coordinates"] == preview["report"]["base_pose"]["effective_coordinates"]
    with pytest.raises(bridge.bridge.BridgeError, match="differs"):
        contract.require_source_preview(changed, expected)
    assert original == before
