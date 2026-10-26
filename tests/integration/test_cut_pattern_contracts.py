"""Patterned holes retain current base provenance through strict replay/capture."""

import copy
import importlib
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_cut_pattern_contracts")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
operations = importlib.import_module(package.__name__ + ".operation_contracts")


def document(kind):
    circular = kind == "circular_cut_pattern"
    return {
        "schema_version": 1,
        "id": "part",
        "name": "Patterned holes",
        "units": "mm",
        "parameters": {},
        "active_feature": "holes",
        "features": [
            {
                "id": "plate",
                "kind": "sketch_rectangle",
                "params": {"width": 50, "height": 50, "x": -25, "y": -25},
            },
            {
                "id": "base",
                "kind": "extrude",
                "inputs": {"profile": "plate"},
                "params": {"length": 10},
            },
            {
                "id": "drill",
                "kind": "sketch_circle",
                "params": {"radius": 2, "x": 10 if circular else -10},
            },
            {
                "id": "tool",
                "kind": "extrude",
                "inputs": {"profile": "drill"},
                "params": {"length": 10},
            },
            {
                "id": "holes",
                "kind": kind,
                "inputs": {"base": "base", "tool": "tool"},
                "params": {"count": 4, "angle": 360} if circular else {"count": 3, "dx": 10},
            },
        ],
    }


@pytest.mark.parametrize("kind", ["linear_cut_pattern", "circular_cut_pattern"])
@pytest.mark.parametrize("version", [2, 3])
def test_cut_pattern_replay_binds_base_history(kind, version):
    source = document(kind)
    req = {"protocol_version": 1, "result_version": version, "document": source}
    response = process_request(req)
    assert response["ok"], response
    operations.validate_response(req, response)
    final = response["result"]["features"][-1]
    count = 4 if kind == "circular_cut_pattern" else 3
    assert final["stats"]["volume"] == pytest.approx(25000 - count * math.pi * 4 * 10)
    assert any(face["provenance"]["semantic_status"] == "stable" for face in final["topology"])
    forged = copy.deepcopy(response)
    stable = next(
        face
        for face in forged["result"]["features"][-1]["topology"]
        if face["provenance"]["semantic_status"] == "stable"
    )
    stable["provenance"]["source_id"] = "tool/face/cap.end"
    with pytest.raises(ValueError):
        operations.validate_response(req, forged)


@pytest.mark.parametrize("kind", ["linear_cut_pattern", "circular_cut_pattern"])
def test_cut_pattern_assembly_capture_and_associative_face(kind):
    source = document(kind)
    source["features"] += [
        {
            "id": "top",
            "kind": "sketch_face_circle",
            "params": {"radius": 1},
            "inputs": {"support": "holes"},
            "support_face": "base/face/cap.end",
        },
        {"id": "boss", "kind": "extrude", "params": {"length": 2}, "inputs": {"profile": "top"}},
    ]
    source["active_feature"] = "boss"
    snapshots = importlib.import_module(package.__name__ + ".part_contracts_v3")
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
    assembly = edit.new_from_part(snapshots._expected_document(source))
    req = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 3,
        "action": "assembly_replay",
        "assembly": assembly,
    }
    response = process_request(req)
    assert response["ok"], response
    operations.validate_response(req, response)
