"""Real libslvs -> identity-connected profile -> OCCT -> edit/export continuity."""

from pathlib import Path

import pytest

pytest.importorskip("slvs")
pytest.importorskip("OCP")

from mechanical_cad.actions import run_geometry_action
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, load_document
from mechanical_cad.topology import resolve_reference

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def constrained():
    return load_document(ROOT / "examples/constrained_plate.mcad.json")


def test_real_constrained_rectangle_rebuild_is_exact_and_does_not_rewrite_seeds(constrained):
    before, digest = constrained.to_json(), constrained.content_hash
    result = regenerate(constrained, OCPKernel())
    assert result.ok
    sketch, pad = result.result["features"]
    assert sketch["sketch"]["status"] == "okay"
    assert sketch["sketch"]["remaining_dof"] == 0
    assert sketch["sketch"]["max_residual_mm"] < 1e-7
    assert sketch["sketch"]["dimensions"] == {"height": 30, "width": 40}
    assert pad["stats"]["volume"] == pytest.approx(12000)
    assert constrained.to_json() == before and constrained.content_hash == digest
    assert (
        sketch["sketch"]["solved"]["points"] != constrained.features[0].sketch.to_dict()["points"]
    )


def test_dimension_edit_rebuilds_same_extrusion_and_stable_line_references(constrained):
    before = regenerate(constrained, OCPKernel()).result["features"][-1]
    edited = constrained.with_parameter("width", 60)
    result = regenerate(edited, OCPKernel())
    assert result.ok and result.result["features"][-1]["id"] == "pad"
    assert result.result["features"][-1]["stats"]["volume"] == pytest.approx(18000)
    assert {c.id: c.value for c in edited.features[0].sketch.constraints}["width"] == "width"
    after = result.result["features"][-1]["topology"]
    for candidate in before["topology"]:
        reference = {key: candidate[key] for key in ("feature_id", "role", "kind")}
        assert resolve_reference(reference, after).status == "resolved"


def test_serialized_entity_and_feature_reordering_preserves_solution_and_provenance(constrained):
    data = constrained.to_dict()
    for key in ("points", "lines", "constraints"):
        data["features"][0]["sketch"][key].reverse()
    data["features"].reverse()
    before = regenerate(constrained, OCPKernel()).result
    after = regenerate(Document.from_dict(data), OCPKernel()).result
    before_by_id = {item["id"]: item for item in before["features"]}
    assert {item["id"]: item for item in after["features"]} == before_by_id


def test_underconstrained_closed_sketch_reports_real_remaining_freedom(constrained):
    data = constrained.to_dict()
    constraints = data["features"][0]["sketch"]["constraints"]
    constraints[:] = [c for c in constraints if c["id"] != "anchor"]
    result = regenerate(Document.from_dict(data), OCPKernel())
    assert result.ok
    assert result.result["features"][0]["sketch"]["remaining_dof"] == 2
    assert result.result["features"][-1]["stats"]["volume"] == pytest.approx(12000)


def test_conflicting_dimension_reports_constraint_ids_and_blocks_downstream(constrained):
    data = constrained.to_dict()
    data["features"][0]["sketch"]["constraints"].append(
        {"id": "conflicting_width", "kind": "distance", "refs": ["p0", "p1"], "value": 50}
    )
    result = regenerate(Document.from_dict(data), OCPKernel())
    assert not result.ok
    sketch, pad = result.result["features"]
    assert sketch["error"]["code"] == "sketch_solve_failed"
    assert sketch["sketch"]["failed_constraints"]
    assert sketch["sketch"]["remaining_dof"] is None and sketch["sketch"]["solved"] is None
    assert pad["status"] == "blocked" and pad["mesh"] is None
    assert "pad" not in result.shapes


def test_open_solved_linework_is_not_silently_filled(constrained):
    data = constrained.to_dict()
    sketch = data["features"][0]["sketch"]
    sketch["lines"].pop()
    sketch["constraints"] = []
    result = regenerate(Document.from_dict(data), OCPKernel())
    assert not result.ok
    assert result.result["features"][0]["error"]["code"] == "open_profile"
    assert result.result["features"][-1]["status"] == "blocked"


def test_bad_driving_expression_names_its_constraint(constrained):
    data = constrained.to_dict()
    for constraint in data["features"][0]["sketch"]["constraints"]:
        if constraint["id"] == "width":
            constraint["value"] = "missing_dimension"
    result = regenerate(Document.from_dict(data), OCPKernel())
    assert not result.ok
    assert "width" in result.result["features"][0]["error"]["message"]


def test_fresh_solved_dimension_exports_precise_current_part(constrained, tmp_path):
    path = tmp_path / "constrained.step"
    result = run_geometry_action(
        constrained.with_parameter("width", 60), "export_step", destination=path
    )
    assert result["ok"]
    kernel = OCPKernel()
    assert kernel.inspect(kernel.import_step(path))["volume"] == pytest.approx(18000)
    assert result["geometry_check"]["mesh"]["watertight"]


def test_missing_optional_solver_is_an_actionable_feature_failure(constrained, monkeypatch):
    import mechanical_cad.sketch_solver as adapter

    def missing(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(adapter, "import_module", missing)
    result = regenerate(constrained, OCPKernel())
    assert not result.ok
    assert result.result["features"][0]["error"]["code"] == "solver_unavailable"
    assert result.result["features"][-1]["status"] == "blocked"


@pytest.mark.parametrize("dimension", ["width", "depth"])
def test_nanometre_profile_boundary_fails_closed_at_native_resolution(constrained, dimension):
    # The 1e-6 mm guard is an input limit, not a promise that every aspect ratio
    # has a usable OCCT triangulation. Do not loosen validation to force success.
    result = regenerate(constrained.with_parameter(dimension, 1e-6), OCPKernel())
    assert not result.ok
    assert result.result["features"][0]["error"]["code"] in {"degenerate_profile", "kernel_error"}
    assert result.result["features"][-1]["status"] == "blocked"
    assert result.result["features"][-1]["mesh"] is None and "pad" not in result.shapes


def test_redundant_relation_keeps_ids_and_rebuilds_real_solid(constrained):
    data = constrained.to_dict()
    constraints = data["features"][0]["sketch"]["constraints"]
    source = next(c for c in constraints if c["id"] == "axis0")
    constraints.append({**source, "id": "redundant"})
    document = Document.from_dict(data)
    before = document.to_json()
    result = regenerate(document, OCPKernel())
    assert result.ok
    report = result.result["features"][0]["sketch"]
    assert report["status"] == "redundant_okay"
    assert report["redundant_constraints"] == ["redundant"]
    assert report["failed_constraints"] == []
    assert result.result["features"][-1]["stats"]["volume"] == pytest.approx(12000)
    assert document.to_json() == before


def test_equal_resolved_formulas_remain_distinct_after_parameter_edit(constrained):
    data = constrained.to_dict()
    data["parameters"]["other_width"] = 40
    data["features"][0]["sketch"]["constraints"].append(
        {"id": "other_width", "kind": "distance", "refs": ["p1", "p0"], "value": "other_width"}
    )
    document = Document.from_dict(data)
    result = regenerate(document, OCPKernel())
    assert result.ok
    assert result.result["features"][0]["sketch"]["status"] == "redundant_okay"
    edited = document.with_parameter("other_width", 41)
    failed = regenerate(edited, OCPKernel())
    assert not failed.ok
    assert failed.result["features"][0]["sketch"]["redundant_constraints"] == []
    assert (
        "Diagnostic candidates (not proven causes)"
        in failed.result["features"][0]["error"]["message"]
    )
    assert failed.result["features"][-1]["status"] == "blocked"


@pytest.mark.parametrize("norm_squared_offset", [0.0, 5e-10, -5e-10, 9.9e-10])
def test_long_thin_rotated_profile_uses_authoritative_plane(constrained, norm_squared_offset):
    import math

    data = constrained.to_dict()
    plane = data["features"][0]["sketch"]["plane"]
    plane["origin"] = [3.0, 4.0, 5.0]
    scale = math.sqrt(1 + norm_squared_offset) / math.sqrt(87)
    plane["quaternion"] = [component * scale for component in (2, -3, 5, 7)]
    data["parameters"]["width"] = 1e6
    document = Document.from_dict(data)
    before = document.to_json()
    result = regenerate(document, OCPKernel())
    assert result.ok, result.result["features"]
    assert result.result["features"][0]["sketch"]["max_residual_mm"] <= 1e-7
    assert result.result["features"][-1]["stats"]["volume"] == pytest.approx(3e8, rel=1e-9)
    assert document.to_json() == before
    assert result.result["features"][0]["sketch"]["solved"]["plane"] == plane
