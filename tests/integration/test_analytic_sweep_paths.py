"""Open analytic paths remain editable sketches and feed exact native sweeps."""

import copy
import importlib
import math
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.analytic_profile_geometry import classify
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Arc, Circle, Line, Plane, Point, SketchDefinition


def path_definition(*, mixed=False, reverse=False):
    return SketchDefinition(
        "rail",
        (Point("a", 20, 0), Point("b", 0, 20), Point("c", 0, 0), Point("z", -10, 20)),
        (Line("tail", "b", "z"),) if mixed else (),
        (),
        schema_version=3,
        arcs=(Arc("bend", "c", "b", "a", "cw") if reverse else Arc("bend", "c", "a", "b", "ccw"),),
    )


def document(*, mixed=False, reverse=False):
    section = SketchDefinition(
        "section",
        (Point("center", 0, 0),),
        (),
        (),
        plane=Plane((20, 0, 0), (math.sqrt(0.5), math.sqrt(0.5), 0, 0)),
        schema_version=2,
        circles=(Circle("section_circle", "center", 1),),
    )
    return Document(
        "pipe",
        "Bent rod",
        {},
        (
            Feature("section", "sketch_constrained", "Section", sketch=section),
            Feature(
                "rail",
                "sketch_constrained",
                "Path",
                sketch=path_definition(mixed=mixed, reverse=reverse),
            ),
            Feature("sweep", "sweep", "Bent rod", {}, {"profile": "section", "path": "rail"}),
        ),
        "sweep",
        schema_version=2,
    )


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_native_sweep_roundtrip_and_exact_volume(mixed, reverse):
    doc = Document.from_json(document(mixed=mixed, reverse=reverse).to_json())
    replay = regenerate(doc, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert replay.result["features"][1]["output"]["profile"]["state"] == "unavailable"
    stats = replay.result["features"][-1]["stats"]
    assert stats["valid"] and stats["solids"] == 1
    assert stats["volume"] == pytest.approx(
        math.pi * (10 * math.pi + (10 if mixed else 0)), rel=1e-6
    )
    assert Document.from_json(doc.to_json()).to_json() == doc.to_json()


def bridge_module():
    package = "mcad_analytic_path_bridge"
    module = types.ModuleType(package)
    module.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    sys.modules[package] = module
    return importlib.import_module(package + ".result_v3")


def test_solve_finish_replay_bridge_and_export(tmp_path):
    doc = document(mixed=True).to_dict()
    bridge = bridge_module()
    request = {"protocol_version": 1, "result_version": 3, "document": doc}
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_response(request, response)
    solve = {**request, "action": "solve_sketch", "feature_id": "rail"}
    response = process_request(solve)
    assert response["ok"], response
    assert response["result"]["profile_check"]["error"]["code"] == "open_profile"
    bridge.validate_solve_response(response, solve)
    # Finish publishes the same standalone sketch before a sweep exists.
    standalone = copy.deepcopy(doc)
    standalone["features"].pop()
    standalone["active_feature"] = "rail"
    req = {**request, "document": standalone}
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)
    export = process_request(
        {**request, "action": "export_step", "destination": str(tmp_path / "bend.step")}
    )
    assert export["ok"], export
    assert (tmp_path / "bend.step").stat().st_size > 100


def test_open_path_cannot_be_extruded():
    doc = document()
    doc = replace(
        doc,
        features=(
            *doc.features[:-1],
            Feature("sweep", "extrude", "Wrong", {"length": 2}, {"profile": "rail"}),
        ),
    )
    replay = regenerate(doc, OCPKernel(), result_version=3)
    assert not replay.ok
    assert replay.result["features"][-1]["error"]["code"] == "profile_unavailable"


@pytest.mark.parametrize("case", ["branch", "disconnected", "cross", "circle", "bad_radius"])
def test_path_rejects_invalid_geometry(case):
    data = path_definition(mixed=True).to_dict()
    if case == "branch":
        data["lines"].append({"id": "branch", "start": "b", "end": "c"})
    elif case == "disconnected":
        data["points"] += [{"id": "x", "u": 50, "v": 50}, {"id": "y", "u": 60, "v": 50}]
        data["lines"].append({"id": "other", "start": "x", "end": "y"})
    elif case == "cross":
        data["points"].append({"id": "zz", "u": 25, "v": 0})
        data["lines"].append({"id": "crossing", "start": "z", "end": "zz"})
    elif case == "circle":
        data["circles"] = [{"id": "disk", "center": "c", "radius": 2}]
    else:
        next(p for p in data["points"] if p["id"] == "b")["v"] = 21
    with pytest.raises(ValueError):
        classify(data, open_path=True)


def test_saved_path_keeps_radius_expression_and_constraint_edit(tmp_path):
    from mechanical_cad.model import load_document, save_document
    from mechanical_cad.sketch_model import Constraint

    path = replace(
        path_definition(),
        constraints=(
            Constraint("radius", "radius", ("bend",), "bend_radius"),
            Constraint("anchor", "fixed", ("c",), target=(0, 0)),
        ),
    )
    doc = Document(
        "editable",
        "Editable arc",
        {"bend_radius": 20},
        (Feature("rail", "sketch_constrained", "Rail", sketch=path),),
        "rail",
        schema_version=2,
    )
    destination = tmp_path / "editable.mcad.json"
    save_document(doc, destination)
    restored = load_document(destination)
    for radius in (20, 25):
        edited = replace(restored, parameters={"bend_radius": radius})
        replay = regenerate(edited, OCPKernel(), result_version=3)
        assert replay.ok, replay.result
        points = {
            p["id"]: (p["u"], p["v"])
            for p in replay.result["features"][0]["sketch"]["solved"]["points"]
        }
        assert math.dist(points["a"], points["c"]) == pytest.approx(radius)
        assert (
            next(c for c in edited.features[0].sketch.constraints if c.id == "radius").value
            == "bend_radius"
        )
        assert edited.features[0].sketch.arcs == path.arcs


def test_major_clockwise_arc_remains_exact_not_shortest_arc():
    doc = document()
    path = replace(doc.features[1].sketch, arcs=(Arc("bend", "c", "a", "b", "cw"),))
    doc = replace(
        doc, features=(doc.features[0], replace(doc.features[1], sketch=path), doc.features[2])
    )
    replay = regenerate(doc, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(30 * math.pi**2)
