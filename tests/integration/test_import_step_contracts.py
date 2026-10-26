"""Embedded STEP source identity survives replay, modifiers and export."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_step_contracts")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
operations = importlib.import_module(package.__name__ + ".operation_contracts")


def document(tmp_path):
    from mechanical_cad.step_asset import encode_step

    kernel = OCPKernel()
    path = tmp_path / "source.step"
    kernel.export_step(kernel.extrude(kernel.rectangle(10, 20), 5), path)
    return {
        "schema_version": 1,
        "id": "part",
        "name": "Imported standard part",
        "units": "mm",
        "parameters": {},
        "active_feature": "moved",
        "features": [
            {"id": "imported", "kind": "import_step", "step_data": encode_step(path.read_bytes())},
            {
                "id": "moved",
                "kind": "transform",
                "params": {"x": 3},
                "inputs": {"base": "imported"},
            },
        ],
    }


@pytest.mark.parametrize("version", [2, 3])
def test_embedded_import_replay_transform_and_export(version, tmp_path):
    source = document(tmp_path)
    for action in ("replay", "export_step"):
        req = {
            "protocol_version": 1,
            "result_version": version,
            "action": action,
            "document": source,
        }
        if action == "export_step":
            req["destination"] = str(tmp_path / "output.step")
        response = process_request(req)
        assert response["ok"], response
        operations.validate_response(req, response)
        if action == "replay":
            row = response["result"]["features"][0]
            assert row["stats"]["volume"] == pytest.approx(1000)
            assert all(
                face["provenance"]["semantic_status"] == "unknown" for face in row["topology"]
            )
            forged = copy.deepcopy(response)
            forged["result"]["features"][0]["topology"][0]["id"] = "imported/face/cap.end"
            with pytest.raises(ValueError):
                operations.validate_response(req, forged)


@pytest.mark.parametrize(
    "field,value", [("sha256", "0" * 64), ("encoding", "url"), ("data", "not base64")]
)
def test_embedded_source_checksum_and_encoding_fail_closed(field, value, tmp_path):
    source = document(tmp_path)
    source["features"][0]["step_data"][field] = value
    snapshots = importlib.import_module(package.__name__ + ".part_contracts_v3")
    with pytest.raises(ValueError):
        snapshots._expected_document(source)


def test_embedded_import_roundtrip_and_assembly_capture(tmp_path):
    source = document(tmp_path)
    snapshots = importlib.import_module(package.__name__ + ".part_contracts_v3")
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
    canonical = snapshots._expected_document(source)
    req = {"protocol_version": 1, "action": "canonical_snapshot", "document": source}
    response = process_request(req)
    assert response["ok"], response
    operations.validate_response(req, response)
    assembly = edit.new_from_part(canonical)
    for version in (2, 3):
        req = {
            "protocol_version": 1,
            "kind": "assembly",
            "assembly_protocol_version": 1,
            "result_version": version,
            "action": "assembly_replay",
            "assembly": assembly,
        }
        response = process_request(req)
        assert response["ok"], response
        operations.validate_response(req, response)


def test_import_asset_helper_matches_and_bounds_source():
    assets = importlib.import_module(package.__name__ + ".step_asset")
    root = Path(__file__).resolve().parents[2]
    assert (root / "src/mechanical_cad/step_asset.py").read_text() == (
        root / "blender_addon/mechanical_cad_blender/step_asset.py"
    ).read_text()
    with pytest.raises(ValueError):
        assets.encode_step(b"ISO-10303-21;" + b" " * assets.MAX_STEP_BYTES + b"END-ISO-10303-21;")
