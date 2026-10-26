"""Native replacement keeps authored dependants and does not weaken default replay."""

import copy
import math

import pytest
from test_associative_projection import projected_document
from test_circular_edge_projection import document as circular_document
from test_solid_edge_projection import bridge, document

from mechanical_cad.model import Document, load_document, save_document
from mechanical_cad.projection_repair import replace_reference, source_document
from mechanical_cad.sidecar import process_request


def replay(data, version=3):
    return process_request({"protocol_version": 1, "result_version": version, "document": data})


def catalog(data, feature_id, version):
    request = {
        "protocol_version": 1,
        "result_version": version,
        "action": "edge_catalog",
        "document": source_document(data, feature_id),
        "options": {"linear_deflection": 0.1},
    }
    result = process_request(request)
    # Independently exercise Blender's strict transport boundary, including source ancestry.
    import importlib

    validator = bridge()[0]
    importlib.import_module(validator.__package__ + ".edge_catalog_bridge").validate_response(
        request, result
    )
    return result["result"]


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("reverse", [False, True])
def test_replace_native_line_retains_constraints_and_saves(tmp_path, version, reverse):
    data = document().to_dict()
    # The dependent extrusion remains; a boolean can separately reject an outside hole.
    data["features"] = data["features"][:-1]
    data["active_feature"] = "tool"
    original = copy.deepcopy(data)
    review = replay(data, version)
    plane = review["result"]["features"][2]["support_plane"]
    entries = catalog(data, "hole", version)["catalogs"]["base"]
    edge = next(e for e in entries if e["faces"] == ["base/face/cap.end", "base/face/side.y_max"])
    row = {k: edge[k] for k in ("faces", "endpoint_faces")}
    candidate = replace_reference(
        data, "hole", "reference", row, source_id="base", edge=edge, plane=plane, reverse=reverse
    )
    assert data == original
    old, new = data["features"][2], candidate["features"][2]
    assert new["sketch"]["lines"] == old["sketch"]["lines"]
    assert [c["id"] for c in new["sketch"]["constraints"]] == [
        c["id"] for c in old["sketch"]["constraints"]
    ]
    assert [c for c in new["sketch"]["constraints"] if not c["id"].startswith("managed_")] == [
        c for c in old["sketch"]["constraints"] if not c["id"].startswith("managed_")
    ]
    assert new["sketch"]["plane"] == old["sketch"]["plane"]
    expected = [-20 if reverse else 20, 15]
    assert next(c for c in new["sketch"]["constraints"] if c["id"] == "managed_a")[
        "target"
    ] == pytest.approx(expected)
    result = replay(candidate, version)
    assert result["ok"], result
    bridge()[version - 2].validate_response(
        {"protocol_version": 1, "result_version": version, "document": candidate}, result
    )
    assert result["result"]["features"][-1]["stats"]["volume"] == pytest.approx(4 * math.pi * 10)
    path = tmp_path / "repaired.mcad.json"
    save_document(Document.from_dict(candidate), path)
    assert load_document(path).to_dict() == Document.from_dict(candidate).to_dict()
    assert replay(load_document(path).to_dict(), version)["ok"]


@pytest.mark.parametrize("version", [2, 3])
def test_failed_downstream_stays_failed_until_explicit_native_repair(version):
    data = document().to_dict()
    data["features"][2]["projections"][0]["endpoint_faces"] = [
        ["base/face/missing.a"],
        ["base/face/missing.b"],
    ]
    broken = replay(data, version)
    assert not broken["ok"]
    edge = next(
        e
        for e in catalog(data, "hole", version)["catalogs"]["base"]
        if e["faces"] == data["features"][2]["projections"][0]["faces"]
    )
    candidate = replace_reference(
        data,
        "hole",
        "reference",
        {k: edge[k] for k in ("faces", "endpoint_faces")},
        source_id="base",
        edge=edge,
        plane=broken["result"]["features"][2]["support_plane"],
    )
    assert replay(candidate, version)["ok"]
    assert not replay(data, version)["ok"]


def test_circle_repair_preserves_concentric_relation_and_rejects_line():
    data = circular_document().to_dict()
    result = replay(data)
    entry = next(
        e
        for e in catalog(data, "hole", 3)["catalogs"]["base"]
        if e["faces"][0] == "base/face/cap.start"
    )
    edge = {"kind": "circle", "faces": entry["faces"], **entry["circle"]}
    row = {"kind": "circle", "faces": edge["faces"]}
    candidate = replace_reference(
        data,
        "hole",
        "reference",
        row,
        source_id="base",
        edge=edge,
        plane=result["result"]["features"][2]["support_plane"],
    )
    assert [
        c
        for c in candidate["features"][2]["sketch"]["constraints"]
        if not c["id"].startswith("managed_")
    ] == [
        c
        for c in data["features"][2]["sketch"]["constraints"]
        if not c["id"].startswith("managed_")
    ]
    assert replay(candidate)["ok"]
    for kwargs in ({"source_id": "other"}, {"reverse": True}):
        args = dict(
            source_id="base", edge=edge, plane=result["result"]["features"][2]["support_plane"]
        )
        args.update(kwargs)
        with pytest.raises(ValueError):
            replace_reference(data, "hole", "reference", row, **args)


def test_sketch_circle_repair_does_not_remove_equal_dimension():
    data = projected_document().to_dict()
    source = data["features"][0]["sketch"]
    source["points"].append({"id": "new_center", "u": 8, "v": 9})
    source["circles"].append(
        {"id": "new_ring", "center": "new_center", "radius": 4, "construction": True}
    )
    source["constraints"].extend(
        [
            {"id": "new_anchor", "kind": "fixed", "refs": ["new_center"], "target": [8, 9]},
            {"id": "new_radius", "kind": "radius", "refs": ["new_ring"], "value": 4},
        ]
    )
    solved = catalog(data, "target", 3)["replay"]["features"][0]["sketch"]["solved"]
    candidate = replace_reference(
        data,
        "target",
        "reference",
        {"source": "new_ring"},
        source_id="source",
        source_solved=solved,
    )
    assert next(
        c for c in candidate["features"][1]["sketch"]["constraints"] if c["id"] == "match"
    ) == next(c for c in data["features"][1]["sketch"]["constraints"] if c["id"] == "match")
    result = replay(candidate)
    assert result["ok"], result
    assert result["result"]["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 16 * 5)


def test_sketch_line_flip_retains_target_ids_and_unrelated_geometry():
    from dataclasses import replace

    from mechanical_cad.sketch_model import Constraint, Line, Point, SketchDefinition

    doc = projected_document()
    source = SketchDefinition(
        "source",
        (Point("a", 2, 3), Point("b", 8, 3)),
        (Line("edge", "a", "b"),),
        (
            Constraint("fa", "fixed", ("a",), target=(2, 3)),
            Constraint("fb", "fixed", ("b",), target=(8, 3)),
        ),
        schema_version=2,
    )
    target = replace(
        doc.features[1].sketch,
        points=(*doc.features[1].sketch.points, Point("a", 0, 0), Point("b", 1, 0)),
        lines=(Line("guide", "a", "b", True),),
        constraints=(
            *doc.features[1].sketch.constraints,
            Constraint("fa", "fixed", ("a",), target=(0, 0)),
            Constraint("fb", "fixed", ("b",), target=(1, 0)),
        ),
    )
    doc = replace(
        doc,
        features=(
            replace(doc.features[0], sketch=source),
            replace(
                doc.features[1], sketch=target, projections=({"source": "edge", "target": "guide"},)
            ),
            doc.features[2],
        ),
    )
    data = doc.to_dict()
    solved = catalog(data, "target", 3)["replay"]["features"][0]["sketch"]["solved"]
    candidate = replace_reference(
        data,
        "target",
        "guide",
        {"source": "edge"},
        source_id="source",
        source_solved=solved,
        reverse=True,
    )
    result = replay(candidate)
    assert result["ok"], result
    points = {p["id"]: p for p in result["result"]["features"][1]["sketch"]["solved"]["points"]}
    assert (points["a"]["u"], points["a"]["v"]) == pytest.approx((7, 1))
    assert (points["b"]["u"], points["b"]["v"]) == pytest.approx((1, 1))
    assert candidate["features"][1]["sketch"]["circles"] == data["features"][1]["sketch"]["circles"]
    with pytest.raises(ValueError, match="existing projected target"):
        replace_reference(
            data,
            "target",
            "reference",
            {"source": "edge"},
            source_id="source",
            source_solved=solved,
        )
