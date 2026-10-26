"""Exact picked-edge references drive ordinary sketch constraints after reopening."""

import copy
import importlib
import math
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature, load_document, save_document
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Circle, Constraint, Line, Plane, Point, SketchDefinition

FACES = ["base/face/cap.end", "base/face/side.y_min"]
ENDPOINTS = [["base/face/side.x_max"], ["base/face/side.x_min"]]


def document():
    sketch = SketchDefinition(
        "hole",
        (
            Point("a", 20, -15),
            Point("b", -20, -15),
            Point("foot", 10, -15),
            Point("center", 10, -10),
        ),
        (
            Line("reference", "a", "b", construction=True),
            Line("offset_line", "foot", "center", construction=True),
        ),
        (
            Constraint("managed_a", "fixed", ("a",), target=(20, -15)),
            Constraint("managed_b", "fixed", ("b",), target=(-20, -15)),
            Constraint("on_edge", "point_on_line", ("foot", "reference")),
            Constraint("normal", "perpendicular", ("reference", "offset_line")),
            Constraint("from_corner", "distance", ("a", "foot"), "corner_offset"),
            Constraint("from_edge", "distance", ("foot", "center"), "edge_offset"),
            Constraint("radius", "radius", ("bore",), 2),
        ),
        schema_version=2,
        circles=(Circle("bore", "center", 2),),
        plane=Plane(),
    )
    return Document(
        "plate",
        "Plate with located hole",
        {"width": 40, "height": 10, "corner_offset": 10, "edge_offset": 5},
        (
            Feature(
                "outline", "sketch_rectangle", "Plate outline", {"width": "width", "height": 30}
            ),
            Feature("base", "extrude", "Plate", {"length": "height"}, {"profile": "outline"}),
            Feature(
                "hole",
                "sketch_constrained",
                "Hole position",
                {},
                {"support": "base", "external": "base"},
                sketch=sketch,
                support_face="base/face/cap.end",
                projections=({"faces": FACES, "endpoint_faces": ENDPOINTS, "target": "reference"},),
            ),
            Feature("tool", "extrude", "Hole tool", {"length": "-height"}, {"profile": "hole"}),
            Feature("cut", "cut", "Drilled plate", {}, {"base": "base", "tool": "tool"}),
        ),
        "cut",
        schema_version=2,
    )


def bridge():
    name = "mcad_solid_projection_test"
    package = types.ModuleType(name)
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    sys.modules[name] = package
    return importlib.import_module(name + ".part_result_bridge"), importlib.import_module(
        name + ".result_v3"
    )


@pytest.mark.parametrize("version", [2, 3])
def test_projected_edge_hole_constraint_edit_save_and_bridge(tmp_path, version):
    doc = document()
    location = tmp_path / "plate.mcad.json"
    save_document(doc, location)
    restored = load_document(location)
    validator = bridge()[0 if version == 2 else 1]
    for width, height, edge_offset in [(40, 10, 5), (60, 20, 7)]:
        edited = replace(
            restored,
            parameters={
                **restored.parameters,
                "width": width,
                "height": height,
                "edge_offset": edge_offset,
            },
        )
        request = {"protocol_version": 1, "result_version": version, "document": edited.to_dict()}
        response = process_request(request)
        assert response["ok"], response
        validator.validate_response(request, response)
        result = response["result"]
        hole = next(row for row in result["features"] if row["id"] == "hole")
        center = next(p for p in hole["sketch"]["solved"]["points"] if p["id"] == "center")
        assert center["u"] == pytest.approx(width / 2 - 10)
        assert center["v"] == pytest.approx(edge_offset - 15)
        assert hole["support_plane"]["origin"][2] == pytest.approx(height)
        assert result["features"][-1]["stats"]["volume"] == pytest.approx(
            (width * 30 - 4 * math.pi) * height
        )
        assert edited.features[2].to_dict()["projections"] == [
            {"faces": FACES, "endpoint_faces": ENDPOINTS, "target": "reference"}
        ]
        solve = {**request, "action": "solve_sketch", "feature_id": "hole"}
        solved = process_request(solve)
        assert solved["ok"], solved
        if version == 3:
            validator.validate_solve_response(solved, solve)
        else:
            importlib.import_module(
                validator.__package__ + ".sketch_action_bridge"
            ).validate_solve_response(solved, solve)


def test_missing_pair_stops_without_rebinding():
    data = document().to_dict()
    data["features"][2]["projections"][0]["faces"] = ["base/face/cap.end", "base/face/side.missing"]
    response = process_request({"protocol_version": 1, "result_version": 3, "document": data})
    assert not response["ok"]
    row = next(f for f in response["result"]["features"] if f["id"] == "hole")
    assert row["error"]["code"] == "invalid_sketch_projection"
    assert row["projection_edges"] is None
    assert response["result"]["features"][-1]["status"] == "blocked"
    bridge()[1].validate_response(
        {"protocol_version": 1, "result_version": 3, "document": data}, response
    )


def test_split_and_nonadjacent_pairs_reject():
    kernel = OCPKernel()
    base = kernel.extrude(kernel.rectangle(40, 30), 10)
    kernel.topology(base, "base", "extrude", {})
    # A slot through the top splits its original support face.
    slot = kernel.extrude(kernel.rectangle(50, 2, x=-5, y=14, z=5), 10)
    kernel.topology(slot, "slot", "extrude", {})
    cut = kernel.cut(base, slot)
    kernel.topology(cut, "cut", "cut", {})
    with pytest.raises(ValueError):
        kernel.projected_edge_endpoints(cut, [FACES])
    with pytest.raises(ValueError):
        kernel.projected_edge_endpoints(base, [["base/face/cap.end", "base/face/cap.start"]])


def test_projection_evidence_and_mixed_variants_reject():
    from mechanical_cad.sketch_projection import project_solid_edges, validate_projections

    data = document().to_dict()["features"][2]
    with pytest.raises(ValueError):
        validate_projections(data["projections"] + [{"source": "oldline", "target": "other"}])
    with pytest.raises(ValueError, match="collapses"):
        project_solid_edges(
            data["sketch"],
            [{"faces": FACES, "endpoint_faces": ENDPOINTS, "points": [[0, 0, 0], [0, 0, 10]]}],
            data["projections"],
        )
    assert copy.deepcopy(data) == data


def test_endpoint_identity_survives_rotation_without_swapping():
    kernel = OCPKernel()
    base = kernel.extrude(kernel.rectangle(40, 30), 10)
    kernel.topology(base, "base", "extrude", {})
    original = kernel.projected_edge_endpoints(base, [FACES])[0]
    placed = kernel.transform(base, rz=180)
    kernel.topology(placed, "placed", "transform", {})
    current = kernel.projected_edge_endpoints(placed, [FACES])[0]
    assert original["endpoint_faces"] == current["endpoint_faces"] == ENDPOINTS
    for before, after in zip(original["points"], current["points"], strict=True):
        assert after == pytest.approx([-before[0], -before[1], before[2]], abs=1e-9)


def test_changed_endpoint_identity_is_not_reassigned():
    data = document().to_dict()
    data["features"][2]["projections"][0]["endpoint_faces"] = [
        ["base/face/cap.start"],
        ["base/face/side.x_min"],
    ]
    response = process_request({"protocol_version": 1, "result_version": 3, "document": data})
    assert not response["ok"]
    row = next(f for f in response["result"]["features"] if f["id"] == "hole")
    assert row["error"]["code"] == "invalid_sketch_projection"
    assert "identity changed" in row["error"]["message"]
