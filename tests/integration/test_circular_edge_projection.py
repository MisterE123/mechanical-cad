"""Exact boss-rim references drive concentric geometry through save/replay."""

import copy
import importlib
import math
from dataclasses import replace

import pytest
from test_solid_edge_projection import bridge

from mechanical_cad.kernel_ocp import KernelError, OCPKernel
from mechanical_cad.model import Document, Feature, load_document, save_document
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Circle, Constraint, Plane, Point, SketchDefinition
from mechanical_cad.sketch_projection import project_solid_edges, validate_projections

FACES = ["base/face/cap.end", "base/face/side.circle"]
ROW = {"kind": "circle", "faces": FACES, "target": "reference"}


def document():
    sketch = SketchDefinition(
        "hole",
        (Point("ref_center", 0, 0), Point("center", 0, 0)),
        (),
        (
            Constraint("managed_center", "fixed", ("ref_center",), target=(0, 0)),
            Constraint("managed_radius", "radius", ("reference",), 10),
            Constraint("concentric", "concentric", ("reference", "bore")),
            Constraint("size", "radius", ("bore",), "hole_radius"),
        ),
        schema_version=2,
        circles=(
            Circle("reference", "ref_center", 10, construction=True),
            Circle("bore", "center", 2),
        ),
        plane=Plane(),
    )
    return Document(
        "boss",
        "Concentric boss",
        {"radius": 10, "height": 10, "hole_radius": 2, "x": -12},
        (
            Feature("outline", "sketch_circle", "Boss outline", {"radius": "radius", "x": "x"}),
            Feature("base", "extrude", "Boss", {"length": "height"}, {"profile": "outline"}),
            Feature(
                "hole",
                "sketch_constrained",
                "Concentric bore",
                {},
                {"support": "base", "external": "base"},
                sketch=sketch,
                support_face="base/face/cap.end",
                projections=(ROW,),
            ),
            Feature("tool", "extrude", "Bore tool", {"length": "-height"}, {"profile": "hole"}),
            Feature("cut", "cut", "Bored boss", {}, {"base": "base", "tool": "tool"}),
        ),
        "cut",
        schema_version=2,
    )


@pytest.mark.parametrize("version", [2, 3])
def test_circle_save_edit_replay_and_solve(tmp_path, version):
    path = tmp_path / "boss.mcad.json"
    save_document(document(), path)
    restored = load_document(path)
    assert restored.features[2].to_dict()["projections"] == [ROW]
    validator = bridge()[version - 2]
    for radius, height, hole_radius, x in ((10, 10, 2, -12), (15, 20, 3, 7)):
        doc = replace(
            restored,
            parameters={"radius": radius, "height": height, "hole_radius": hole_radius, "x": x},
        )
        request = {"protocol_version": 1, "result_version": version, "document": doc.to_dict()}
        response = process_request(request)
        assert response["ok"], response
        validator.validate_response(request, response)
        hole = response["result"]["features"][2]
        assert hole["projection_edges"] == [
            {
                "kind": "circle",
                "faces": FACES,
                "center": [x, 0, height],
                "normal": [0, 0, 1],
                "radius": radius,
            }
        ]
        solved = hole["sketch"]["solved"]
        circles = {c["id"]: c for c in solved["circles"]}
        assert circles["reference"]["radius"] == pytest.approx(radius)
        assert circles["bore"]["radius"] == pytest.approx(hole_radius)
        assert response["result"]["features"][-1]["stats"]["volume"] == pytest.approx(
            math.pi * (radius**2 - hole_radius**2) * height
        )
        solve = {**request, "action": "solve_sketch", "feature_id": "hole"}
        result = process_request(solve)
        assert result["ok"], result
        if version == 3:
            validator.validate_solve_response(result, solve)
        else:
            importlib.import_module(
                validator.__package__ + ".sketch_action_bridge"
            ).validate_solve_response(result, solve)


def test_circle_projection_rejects_tilt_and_wrong_variant():
    sketch = document().features[2].sketch.to_dict()
    evidence = {
        "kind": "circle",
        "faces": FACES,
        "center": [0, 0, 10],
        "normal": [1, 0, 0],
        "radius": 10,
    }
    with pytest.raises(ValueError, match="parallel"):
        project_solid_edges(sketch, [evidence], [ROW])
    bad = copy.deepcopy(ROW)
    bad["endpoint_faces"] = [["a"], ["b"]]
    with pytest.raises(ValueError):
        validate_projections([bad])
    missing = document().to_dict()
    missing["features"][2]["projections"][0]["faces"] = ["base/face/cap.end", "base/face/missing"]
    response = process_request({"protocol_version": 1, "result_version": 3, "document": missing})
    assert not response["ok"]
    assert response["result"]["features"][2]["error"]["code"] == "invalid_sketch_projection"


def test_native_partial_circle_is_not_admitted(monkeypatch):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt

    edge = BRepBuilderAPI_MakeEdge(
        gp_Circ(gp_Ax2(gp_Pnt(), gp_Dir(0, 0, 1)), 10), 0, math.pi
    ).Edge()
    kernel = OCPKernel()
    monkeypatch.setattr(kernel, "_selected_edges", lambda shape, faces: [edge])
    with pytest.raises(KernelError, match="full circle"):
        kernel.projected_circle(None, FACES)
