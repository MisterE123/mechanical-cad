import math
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad import actions
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel, check_watertight_mesh
from mechanical_cad.model import Document, Feature

pytestmark = pytest.mark.kernel


def expected_volume(width=40):
    return (width * 30 - math.pi * 4**2) * 10


def test_read_only_geometry_check_reports_exact_solid_and_closed_mesh(plate, tmp_path, monkeypatch):
    monkeypatch.setattr(
        actions.tempfile, "mkstemp", lambda **kw: pytest.fail("check must not write")
    )
    original = plate.to_json()
    result = actions.run_geometry_action(plate, "check_geometry", linear_deflection=0.03)
    assert result["ok"], result
    assert result["export"] is None and result["error"] is None
    assert result["result"]["document_hash"] == plate.content_hash
    checks = result["geometry_check"]
    assert checks["brep"]["valid"] is True
    assert checks["brep"]["solids"] == 1
    assert checks["brep"]["volume"] == pytest.approx(expected_volume(), rel=1e-12)
    assert checks["mesh"]["watertight"] is True
    assert checks["mesh"]["consistently_oriented"] is True
    assert checks["mesh"]["vertex_manifold"] is True
    assert checks["linear_deflection_mm"] == 0.03
    assert "manufacturable" not in checks and "certified" not in checks
    assert plate.to_json() == original
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("action,extension", [("export_step", ".step"), ("export_stl", ".stl")])
def test_dirty_document_exports_fresh_geometry_with_utf8_and_spaces(
    plate, tmp_path, action, extension
):
    # A previous successful replay is intentionally not supplied to the helper.
    old = regenerate(plate, OCPKernel())
    document = plate.with_parameter("width", 60)
    destination = tmp_path / ("pièce neuve é 60" + extension)
    destination.write_bytes(b"previous export to replace")
    result = actions.run_geometry_action(
        document, action, destination=destination, linear_deflection=0.03
    )
    assert result["ok"], result
    assert old.result["document_hash"] != result["result"]["document_hash"]
    assert result["result"]["document_hash"] == document.content_hash
    assert result["geometry_check"]["brep"]["volume"] == pytest.approx(expected_volume(60))
    assert result["export"]["document_hash"] == document.content_hash
    assert result["export"]["destination"] == str(destination)
    assert result["export"]["active_feature"] == "body"
    assert result["export"]["units"] == "mm"
    assert result["export"]["atomic_replace"] is True
    assert result["export"]["bytes"] == destination.stat().st_size
    assert list(tmp_path.iterdir()) == [destination]
    if action == "export_step":
        kernel = OCPKernel()
        assert kernel.inspect(kernel.import_step(destination))["volume"] == pytest.approx(
            expected_volume(60), rel=1e-12
        )
    else:
        payload = destination.read_bytes()
        count = struct.unpack_from("<I", payload, 80)[0]
        assert len(payload) == 84 + 50 * count
        vertices = []
        for index in range(count):
            floats = struct.unpack_from("<9f", payload, 84 + index * 50 + 12)
            vertices.extend([floats[offset : offset + 3] for offset in (0, 3, 6)])
        mesh = {
            "vertices": vertices,
            "triangles": [[3 * i, 3 * i + 1, 3 * i + 2] for i in range(count)],
        }
        check = check_watertight_mesh(mesh)
        assert check["signed_volume"] == pytest.approx(expected_volume(60), rel=0.001)
        assert max(point[0] for point in vertices) == 60
        assert result["geometry_check"]["encoded_mesh"]["watertight"]
        assert result["geometry_check"]["encoding"]["maximum_vertex_error_mm"] <= 1e-5


@pytest.mark.parametrize("action", sorted(actions.EXPORT_ACTIONS))
def test_failed_draft_preserves_destination_and_reports_blocked_features(plate, tmp_path, action):
    destination = tmp_path / "part existing.export"
    destination.write_bytes(b"previous valid part")
    invalid = plate.with_parameter("hole_radius", -1)
    result = actions.run_geometry_action(invalid, action, destination=destination)
    assert not result["ok"]
    assert result["error"]["code"] == "regeneration_failed"
    assert result["result"]["document_hash"] == invalid.content_hash
    features = {item["id"]: item for item in result["result"]["features"]}
    assert features["hole_profile"]["status"] == "failed"
    assert features["hole_profile"]["error"]["code"] == "invalid_dimension"
    assert features["body"]["status"] == "blocked" and features["body"]["mesh"] is None
    assert result["export"] is None and result["geometry_check"] is None
    assert destination.read_bytes() == b"previous valid part"
    assert list(tmp_path.iterdir()) == [destination]


def test_successful_active_branch_cannot_hide_independent_failure(plate, tmp_path):
    document = plate.with_feature(
        Feature("unrelated", "sketch_circle", "Bad independent profile", {"radius": -1}),
        make_active=False,
    )
    destination = tmp_path / "previous.step"
    destination.write_bytes(b"preserve")
    result = actions.run_geometry_action(document, "export_step", destination=destination)
    assert not result["ok"]
    assert next(x for x in result["result"]["features"] if x["id"] == "body")["status"] == "ok"
    assert result["error"]["code"] == "regeneration_failed"
    assert destination.read_bytes() == b"preserve"


@pytest.mark.parametrize(
    "active,code", [(None, "missing_active_feature"), ("profile", "not_a_solid")]
)
@pytest.mark.parametrize("action", sorted(actions.GEOMETRY_ACTIONS))
def test_no_active_or_sketch_active_fails_closed(plate, tmp_path, active, code, action):
    document = replace(plate, active_feature=active)
    destination = tmp_path / "keep.export"
    destination.write_bytes(b"keep")
    result = actions.run_geometry_action(
        document, action, destination=destination if action in actions.EXPORT_ACTIONS else None
    )
    assert not result["ok"] and result["error"]["code"] == code
    assert result["result"]["status"] == "ok"
    assert result["export"] is None
    assert destination.read_bytes() == b"keep"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize(
    "tolerance", [True, False, 0, 0.0009, 10.01, float("nan"), float("inf"), "0.1", None]
)
def test_deflection_bounds_preserve_existing_destination(plate, tmp_path, tolerance):
    destination = tmp_path / "keep.step"
    destination.write_bytes(b"keep")
    result = actions.run_geometry_action(
        plate, "export_step", destination=destination, linear_deflection=tolerance
    )
    assert not result["ok"] and result["error"]["code"] == "invalid_tolerance"
    assert result["result"] is None
    assert destination.read_bytes() == b"keep"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("tolerance", [0.001, 10])
def test_deflection_endpoints_are_valid(plate, tolerance):
    result = actions.run_geometry_action(plate, "check_geometry", linear_deflection=tolerance)
    assert result["ok"], result


def test_invalid_canonical_snapshot_has_structured_validation_error(plate, tmp_path):
    destination = tmp_path / "keep.step"
    destination.write_bytes(b"keep")
    invalid = replace(plate, parameters={**plate.parameters, "width": "unknown + 1"})
    result = actions.run_geometry_action(invalid, "export_step", destination=destination)
    assert not result["ok"] and result["result"] is None
    assert result["error"]["code"] == "unknown_parameter"
    assert destination.read_bytes() == b"keep"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("action", sorted(actions.EXPORT_ACTIONS))
@pytest.mark.parametrize("failure", [RuntimeError("kernel crashed"), OSError("disk full")])
def test_partial_kernel_writer_failure_is_atomic_and_cleans_temp(plate, tmp_path, action, failure):
    destination = tmp_path / "keep.step"
    destination.write_bytes(b"previous valid part")
    kernel = OCPKernel()
    seen = []

    def failing_writer(shape, path, **kwargs):
        seen.append(path)
        assert path != destination and path.parent == destination.parent
        path.write_bytes(b"incomplete new export")
        raise failure

    setattr(kernel, action, failing_writer)
    result = actions.run_geometry_action(plate, action, destination=destination, kernel=kernel)
    assert not result["ok"]
    assert len(seen) == 1
    assert result["result"]["status"] == "ok"
    assert result["geometry_check"]["brep"]["volume"] == pytest.approx(expected_volume())
    assert result["export"] is None
    assert destination.read_bytes() == b"previous valid part"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("fault", ["fsync", "replace"])
def test_io_failure_during_atomic_commit_preserves_destination(plate, tmp_path, monkeypatch, fault):
    destination = tmp_path / "keep.step"
    destination.write_bytes(b"keep")

    def fail(*args):
        raise OSError("injected commit failure")

    monkeypatch.setattr(actions.os, fault, fail)
    result = actions.run_geometry_action(plate, "export_step", destination=destination)
    assert not result["ok"]
    assert result["error"]["code"] == "export_io_error"
    assert result["result"]["status"] == "ok"
    assert destination.read_bytes() == b"keep"
    assert list(tmp_path.iterdir()) == [destination]


def test_empty_writer_does_not_replace_destination(plate, tmp_path, monkeypatch):
    destination = tmp_path / "keep.step"
    destination.write_bytes(b"keep")
    kernel = OCPKernel()
    monkeypatch.setattr(kernel, "export_step", lambda *args: None)
    result = actions.run_geometry_action(
        plate, "export_step", destination=destination, kernel=kernel
    )
    assert not result["ok"] and result["error"]["code"] == "empty_export"
    assert destination.read_bytes() == b"keep"
    assert list(tmp_path.iterdir()) == [destination]


def test_mesh_check_failure_creates_no_temporary_file(plate, tmp_path, monkeypatch):
    destination = tmp_path / "keep.step"
    destination.write_bytes(b"keep")
    kernel = OCPKernel()

    def fail(*args, **kwargs):
        raise ValueError("non-manifold mesh")

    monkeypatch.setattr(kernel, "manufacturing_check", fail)
    monkeypatch.setattr(actions.tempfile, "mkstemp", lambda **kw: pytest.fail("must not write"))
    result = actions.run_geometry_action(
        plate, "export_step", destination=destination, kernel=kernel
    )
    assert not result["ok"] and result["error"]["code"] == "geometry_check_failed"
    assert result["result"]["status"] == "ok"
    assert destination.read_bytes() == b"keep"


def test_real_stl_precision_failure_preserves_destination(tmp_path):
    document = Document.from_dict(
        {
            "schema_version": 1,
            "id": "tiny-far",
            "name": "Tiny far part",
            "units": "mm",
            "parameters": {},
            "active_feature": "pad",
            "features": [
                {
                    "id": "profile",
                    "kind": "sketch_rectangle",
                    "params": {"width": 0.1, "height": 0.1, "x": 1e6, "y": 1e6, "z": 1e6},
                },
                {
                    "id": "pad",
                    "kind": "extrude",
                    "params": {"length": 0.1},
                    "inputs": {"profile": "profile"},
                },
            ],
        }
    )
    destination = tmp_path / "keep.stl"
    destination.write_bytes(b"keep")
    result = actions.run_geometry_action(
        document, "export_stl", destination=destination, linear_deflection=0.001
    )
    assert not result["ok"] and "coordinate error" in result["error"]["message"]
    assert result["result"]["status"] == "ok"
    assert destination.read_bytes() == b"keep"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize(
    "action,destination,code",
    [
        ("shell", None, "invalid_action"),
        ([], None, "invalid_action"),
        ("export_step", None, "invalid_destination"),
        ("export_stl", "", "invalid_destination"),
        ("export_step", "bad\0name", "invalid_destination"),
        ("check_geometry", "unexpected.step", "invalid_request"),
    ],
)
def test_invalid_action_requests_fail_without_replay(plate, action, destination, code):
    result = actions.run_geometry_action(plate, action, destination=destination)
    assert not result["ok"] and result["error"]["code"] == code
    assert result["result"] is None


def test_multiple_solids_rejected_with_current_feature_diagnostic(plate, tmp_path):
    data = plate.to_dict()
    data["features"][2] = {
        "id": "hole_profile",
        "kind": "sketch_rectangle",
        "params": {"width": 2, "height": 32, "x": 19, "y": -1},
    }
    document = Document.from_dict(data)
    destination = tmp_path / "keep.step"
    destination.write_bytes(b"keep")
    result = actions.run_geometry_action(document, "export_step", destination=destination)
    assert not result["ok"] and result["error"]["code"] == "regeneration_failed"
    active = next(item for item in result["result"]["features"] if item["id"] == "body")
    assert active["error"]["code"] == "unsupported_solid_count"
    assert active["mesh"] is None
    assert destination.read_bytes() == b"keep"
    assert list(tmp_path.iterdir()) == [destination]


def test_missing_destination_directory_is_not_created(plate, tmp_path):
    destination = tmp_path / "missing" / "part.step"
    result = actions.run_geometry_action(plate, "export_step", destination=destination)
    assert not result["ok"] and result["error"]["code"] == "export_io_error"
    assert result["result"]["status"] == "ok"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("action", sorted(actions.EXPORT_ACTIONS))
def test_successful_export_replaces_destination_symlink_not_its_referent(plate, tmp_path, action):
    referent = tmp_path / "do not modify.original"
    referent.write_bytes(b"unrelated original bytes")
    destination = tmp_path / "part linked.export"
    try:
        destination.symlink_to(referent.name)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"This environment cannot create symlinks: {exc}")
    assert destination.is_symlink()
    result = actions.run_geometry_action(plate, action, destination=destination)
    assert result["ok"], result
    assert not destination.is_symlink()
    assert destination.is_file() and destination.stat().st_size == result["export"]["bytes"]
    assert referent.read_bytes() == b"unrelated original bytes"
    assert set(tmp_path.iterdir()) == {referent, destination}


def test_failed_export_keeps_destination_symlink_and_referent(plate, tmp_path, monkeypatch):
    referent = tmp_path / "do not modify.original"
    referent.write_bytes(b"original bytes")
    destination = tmp_path / "part linked.step"
    try:
        destination.symlink_to(referent.name)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"This environment cannot create symlinks: {exc}")
    kernel = OCPKernel()

    def fail(shape, path):
        path.write_bytes(b"partial export")
        raise OSError("injected writer failure")

    monkeypatch.setattr(kernel, "export_step", fail)
    result = actions.run_geometry_action(
        plate, "export_step", destination=destination, kernel=kernel
    )
    assert not result["ok"] and result["error"]["code"] == "export_io_error"
    assert destination.is_symlink() and destination.readlink() == Path(referent.name)
    assert referent.read_bytes() == b"original bytes"
    assert set(tmp_path.iterdir()) == {referent, destination}
