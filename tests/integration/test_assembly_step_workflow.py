"""One actual box/sector project exported through the strict Assembly service.

The optional command-line reader inspects existing operator output only; it
does not rebuild, change or re-export the model. Tolerances below are readback
comparisons, not changed construction or verification tolerances.
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest
from test_assembly_step_kernel import _read_assembly

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.assembly_protocol import process_assembly_request

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/box_sector/assembly.mcad-assembly.json"


def verify_project_step(path, raw):
    from mechanical_cad.kernel_ocp import OCPKernel, _shape_bounds

    canonical = AssemblyDocument.from_dict(raw)
    pose = evaluate(canonical)
    kernel = OCPKernel()
    _, name, occurrences = _read_assembly(path)
    assert name == canonical.name
    assert set(occurrences) == {row.name for row in canonical.instances}
    assert occurrences["Sector A"]["label"].IsEqual(occurrences["Sector B"]["label"])
    assert not occurrences["Sector A"]["label"].IsEqual(occurrences["Box base"]["label"])
    parts = {row.id: row for row in canonical.parts}
    observations = []
    for instance in canonical.instances:
        record = occurrences[instance.name]
        assert record["name"] == parts[instance.part_id].name
        frame = pose.transforms[instance.id]
        assert frame.wxyz == (1, 0, 0, 0)
        location = record["location"]
        actual_translation = tuple(location.Value(i, 4) for i in range(1, 4))
        assert actual_translation == pytest.approx(frame.xyz_mm, abs=1e-7)
        for i in range(1, 4):
            for j in range(1, 4):
                assert location.Value(i, j) == pytest.approx(int(i == j), abs=1e-10)
        size = (40, 30, 10) if instance.part_id == "box" else (5, 5, 10)
        volume = 12000 if instance.part_id == "box" else math.pi * 25 * 10 / 4
        expected_bounds = (*frame.xyz_mm, *(a + b for a, b in zip(frame.xyz_mm, size, strict=True)))
        bounds = _shape_bounds(record["shape"])
        stats = kernel.inspect(record["shape"])
        assert stats["valid"] and stats["solids"] == 1
        assert abs(stats["volume"] - volume) <= max(1e-9, 1e-10 * volume)
        assert bounds == pytest.approx(expected_bounds, abs=1e-7)
        observations.append(
            {"instance": instance.id, "volume_mm3": stats["volume"], "bounds_mm": bounds}
        )
    return {"assembly": name, "definitions": 2, "instances": observations}


@pytest.mark.kernel
def test_saved_project_pose_exports_reused_parts_and_changed_joint(tmp_path):
    raw = json.loads(EXAMPLE.read_text())
    before = json.dumps(raw, sort_keys=True)
    path = tmp_path / "assembly.step"
    for coordinate in (10.0, 12.0):
        raw["joints"][0]["coordinate"] = coordinate
        request = {
            "protocol_version": 1,
            "kind": "assembly",
            "assembly_protocol_version": 1,
            "action": "assembly_export_step",
            "assembly": raw,
            "result_version": 3,
            "path": str(path),
        }
        response = process_assembly_request(request)
        assert response["ok"], response
        assert response["export"]["bytes_written"] == path.stat().st_size
        assert response["result"]["report"]["complete"] and response["result"]["report"]["passed"]
        verify_project_step(path, raw)
        assert len(list(tmp_path.iterdir())) == 1
    raw["joints"][0]["coordinate"] = 10.0
    assert json.dumps(raw, sort_keys=True) == before


@pytest.mark.kernel
def test_interfering_pose_preserves_existing_destination(tmp_path):
    raw = json.loads(EXAMPLE.read_text())
    raw["joints"][0]["coordinate"] = -5.0
    path = tmp_path / "keep.step"
    path.write_bytes(b"previous user file")
    response = process_assembly_request(
        {
            "protocol_version": 1,
            "kind": "assembly",
            "assembly_protocol_version": 1,
            "action": "assembly_export_step",
            "assembly": raw,
            "result_version": 3,
            "path": str(path),
        }
    )
    assert not response["ok"] and response["export"] is None
    assert response["result"]["report"]["known_interference"]
    assert path.read_bytes() == b"previous user file"
    assert list(tmp_path.iterdir()) == [path]


if __name__ == "__main__":
    assert len(sys.argv) == 3 and sys.argv[1] == "--read-owner"
    directory = Path(sys.argv[2]).resolve()
    expected = json.loads((directory / "expected.json").read_text())
    observations = {}
    for name, digest in expected["files"].items():
        path = directory / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        observations[name] = verify_project_step(path, expected["assembly"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    retained = json.loads((directory / "reopened-export.json").read_text())
    assert retained["file"] == "assembly-reopened.step"
    assert retained["receipt"]["outcome"] == "WRITTEN"
    reopened = directory / retained["file"]
    assert retained["receipt"]["export"]["bytes_written"] == reopened.stat().st_size
    assert hashlib.sha256(reopened.read_bytes()).hexdigest() == retained["sha256"]
    observations[reopened.name] = verify_project_step(reopened, expected["assembly"])
    assert hashlib.sha256(reopened.read_bytes()).hexdigest() == retained["sha256"]
    with (directory / "readback.json").open("x") as stream:
        json.dump(observations, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print("ASSEMBLY_STEP_OWNER_READBACK_OK", flush=True)
