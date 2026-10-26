"""Primitive circle intent changes exact radii, never converts them as diameters."""

import copy
import importlib
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document

package = types.ModuleType("radius_geometry_addon")
package.__path__ = [str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
radius_edit = importlib.import_module(package.__name__ + ".parameter_radius_edit")
feature_edit = importlib.import_module(package.__name__ + ".solid_feature_edit")


def circle_document(kind):
    features = [
        {"id": "base_profile", "kind": "sketch_rectangle", "params": {"width": 50, "height": 30}},
        {"id": "base", "kind": "extrude", "params": {"length": 10}, "inputs": {"profile": "base_profile"}},
    ]
    for index in (1, 2):
        profile = {
            "id": f"circle{index}", "kind": kind, "label": f"Circle {index}",
            "params": {"radius": "hole_radius", "x": 10 * index, "y": 10}, "inputs": {},
        }
        if kind == "sketch_face_circle":
            profile["inputs"] = {"support": "base"}
            profile["support_face"] = "base/face/cap.end"
        features.extend([profile, {
            "id": f"boss{index}", "kind": "extrude", "params": {"length": 2},
            "inputs": {"profile": f"circle{index}"},
        }])
    return Document.from_dict({
        "schema_version": 1, "id": "radius-intent", "name": "Circle radius intent", "units": "mm",
        "parameters": {"hole_radius": 3}, "features": features, "active_feature": "boss2",
    }).to_dict()


def assert_exact_radii(document, first_radius, second_radius, z):
    replay = regenerate(Document.from_dict(document), OCPKernel())
    assert replay.ok, replay.result
    rows = {f["id"]: f for f in replay.result["features"]}
    for index, radius in enumerate((first_radius, second_radius), start=1):
        boss = rows[f"boss{index}"]
        assert boss["stats"]["valid"] and boss["stats"]["solids"] == 1
        assert boss["stats"]["volume"] == pytest.approx(math.pi * radius**2 * 2)
        vertices = boss["mesh"]["vertices"]
        assert min(v[2] for v in vertices) == pytest.approx(z)
        assert max(v[2] for v in vertices) == pytest.approx(z + 2)


@pytest.mark.parametrize("kind,z", [("sketch_circle", 0), ("sketch_face_circle", 10)])
def test_shared_radius_then_local_replacement_geometry(kind, z):
    original = circle_document(kind)
    before = copy.deepcopy(original)
    assert_exact_radii(original, 3, 3, z)
    shared = radius_edit.edit_shared_radius(
        original, copy.deepcopy(original), "circle1", "hole_radius", "0.6 cm"
    )
    assert float(shared["parameters"]["hole_radius"]) == 6
    assert [f["params"]["radius"] for f in shared["features"] if f["kind"] == kind] == ["hole_radius"] * 2
    assert_exact_radii(shared, 6, 6, z)
    circle = next(f for f in shared["features"] if f["id"] == "circle1")
    local = feature_edit.edit_feature(
        shared, "circle1", label=circle["label"],
        params={**circle["params"], "radius": "5"}, inputs=circle["inputs"],
    )
    assert local["parameters"] == shared["parameters"]
    assert next(f for f in local["features"] if f["id"] == "circle2")["params"]["radius"] == "hole_radius"
    assert_exact_radii(local, 5, 6, z)
    assert original == before
    assert original["active_feature"] == shared["active_feature"] == local["active_feature"] == "boss2"


@pytest.mark.parametrize("kind", ["sketch_circle", "sketch_face_circle"])
def test_invalid_radius_candidate_fails_without_mutating_original(kind):
    original = circle_document(kind)
    before = copy.deepcopy(original)
    invalid = radius_edit.edit_shared_radius(original, copy.deepcopy(original), "circle1", "hole_radius", "-1")
    replay = regenerate(Document.from_dict(invalid), OCPKernel())
    assert not replay.ok
    assert original == before
    assert_exact_radii(original, 3, 3, 10 if kind == "sketch_face_circle" else 0)


@pytest.mark.parametrize("support,z", [("base", -2), ("base2", 18)])
def test_shared_radius_keeps_simultaneous_new_support_face_geometry(support, z):
    original = circle_document("sketch_face_circle")
    original["features"][2:2] = [
        {"id": "base2_profile", "kind": "sketch_rectangle", "label": "Raised base profile",
         "params": {"width": 50, "height": 30, "z": 20}, "inputs": {}},
        {"id": "base2", "kind": "extrude", "label": "Raised base",
         "params": {"length": 10}, "inputs": {"profile": "base2_profile"}},
    ]
    before = copy.deepcopy(original)
    source = next(f for f in original["features"] if f["id"] == "circle1")
    candidate = feature_edit.edit_feature(
        original, "circle1", label=source["label"], params=source["params"],
        inputs={"support": support},
    )
    prior_target = next(f for f in candidate["features"] if f["id"] == "circle1")
    candidate = radius_edit.edit_shared_radius(original, candidate, "circle1", "hole_radius", "6")
    target = next(f for f in candidate["features"] if f["id"] == "circle1")
    assert target is not prior_target  # set_parameter returns a copied candidate.
    target["support_face"] = support + "/face/cap.start"
    replay = regenerate(Document.from_dict(candidate), OCPKernel())
    assert replay.ok, replay.result
    rows = {f["id"]: f for f in replay.result["features"]}
    for identifier, minimum_z in (("boss1", z), ("boss2", 10)):
        row = rows[identifier]
        assert row["stats"]["valid"] and row["stats"]["solids"] == 1
        assert row["stats"]["volume"] == pytest.approx(math.pi * 6**2 * 2)
        coords = [p[2] for p in row["mesh"]["vertices"]]
        assert min(coords) == pytest.approx(minimum_z)
        assert max(coords) == pytest.approx(minimum_z + 2)
    assert target["inputs"]["support"] == support
    assert target["params"]["radius"] == "hole_radius"
    assert original == before
