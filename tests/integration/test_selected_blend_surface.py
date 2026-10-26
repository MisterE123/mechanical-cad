"""Exact selected-edge blend surfaces become reusable, never index-based names."""

import copy
import importlib
import math
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel, TopAbs_FACE, _subshapes
from mechanical_cad.model import Document, Feature, load_document, save_document
from mechanical_cad.sidecar import process_request

package = types.ModuleType("selected_blend_client")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package


def document(kind="chamfer", *, attached=False, selected=True, circular=False):
    profile = (
        Feature("p", "sketch_circle", "P", {"radius": "width"})
        if circular
        else Feature("p", "sketch_rectangle", "P", {"width": "width", "height": 30})
    )
    faces = ("b/face/cap.end", "b/face/side.circle" if circular else "b/face/side.y_min")
    features = [
        profile,
        Feature("b", "extrude", "B", {"length": 10}, {"profile": "p"}),
        Feature(
            "blend",
            kind,
            "Selected blend",
            {"radius" if kind == "fillet" else "distance": "size"},
            {"base": "b"},
            edge_faces=faces if selected else None,
        ),
    ]
    if attached:
        features.append(
            Feature(
                "s",
                "sketch_face_circle",
                "On bevel",
                {"radius": 0.3},
                {"support": "blend"},
                support_face="blend/face/blend.surface",
            )
        )
    return Document(
        "d", "Reusable bevel", {"width": 40, "size": 2}, tuple(features), features[-1].id
    )


@pytest.mark.parametrize("version", [2, 3])
def test_planar_chamfer_attachment_edit_save_replay(tmp_path, version):
    doc = document(attached=True)
    path = tmp_path / "bevel.mcad.json"
    save_document(doc, path)
    restored = load_document(path)
    validator = importlib.import_module(
        package.__name__ + (".part_result_bridge" if version == 2 else ".result_v3")
    )
    for width, size in [(40, 2), (60, 3)]:
        edited = replace(restored, parameters={"width": width, "size": size})
        request = {"protocol_version": 1, "result_version": version, "document": edited.to_dict()}
        response = process_request(request)
        assert response["ok"], response
        validator.validate_response(request, response)
        rows = response["result"]["features"]
        blend = rows[2]
        face = next(f for f in blend["topology"] if f["role"] == "blend.surface")
        assert face["id"] == "blend/face/blend.surface"
        assert face["signature"]["surface"] == "plane"
        assert face["provenance"]["source_faces"] == ["b/face/cap.end", "b/face/side.y_min"]
        assert blend["stats"]["volume"] == pytest.approx(width * (300 - size * size / 2))
        assert rows[-1]["status"] == "ok"
        kernel = OCPKernel()
        replay = regenerate(edited, kernel, result_version=version)
        shape = replay.shapes["blend"]
        operation = kernel._operations[id(shape)]
        native = next(f for f, c in operation.faces if c["role"] == "blend.surface")
        assert any(native.IsSame(f) for f in operation.builder.Generated(operation.blend_edge))
        # The new boundary is a usable straight projected reference with stable endpoints.
        edge = kernel.projected_edge_endpoints(shape, [["b/face/cap.end", face["id"]]])[0]
        assert math.dist(*edge["points"]) == pytest.approx(width)
        assert edge["endpoint_faces"] == [["b/face/side.x_max"], ["b/face/side.x_min"]]


def test_circular_fillet_surface_supports_circle_reference_not_planar_sketch():
    kernel = OCPKernel()
    replay = regenerate(document("fillet", circular=True), kernel, result_version=3)
    assert replay.ok
    shape = replay.shapes["blend"]
    pair = ["b/face/cap.end", "blend/face/blend.surface"]
    circle = kernel.projected_circle(shape, pair)
    assert circle["radius"] == pytest.approx(38)
    with pytest.raises(ValueError, match="planar"):
        kernel.support_face_signature(shape, pair[1])
    request = {
        "protocol_version": 1,
        "result_version": 3,
        "document": document("fillet", circular=True).to_dict(),
    }
    response = process_request(request)
    importlib.import_module(package.__name__ + ".result_v3").validate_response(request, response)


@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
@pytest.mark.parametrize("version,selected", [(1, True), (3, False)])
def test_legacy_and_all_edge_do_not_promote_surface(kind, version, selected):
    replay = regenerate(document(kind, selected=selected), OCPKernel(), result_version=version)
    assert replay.ok
    assert all(f["role"] != "blend.surface" for f in replay.result["features"][-1]["topology"])


@pytest.mark.parametrize("ambiguity", ["split", "competing_edge", "inherited_face"])
def test_nonunique_native_generation_stays_unknown(ambiguity):
    kernel = OCPKernel()
    replay = regenerate(document(), kernel, result_version=3)
    operation = kernel._operations[id(replay.shapes["blend"])]
    faces = _subshapes(operation.shape, TopAbs_FACE)
    generated = next(f for f, c in operation.faces if c["role"] == "blend.surface")
    original = operation.builder

    class AmbiguousHistory:
        def Generated(self, source):
            if source.IsSame(operation.blend_edge):
                return faces[:2] if ambiguity == "split" else [generated]
            return [generated] if ambiguity == "competing_edge" else original.Generated(source)

    operation.builder = AmbiguousHistory()
    inherited = [(generated, {})] if ambiguity == "inherited_face" else []
    assert kernel._selected_blend_topology(operation, faces, "blend", inherited) == []


@pytest.mark.parametrize("mutation", ["pair", "count", "all_edges", "missing_source"])
def test_client_rejects_forged_blend_identity(mutation):
    request = {"protocol_version": 1, "result_version": 3, "document": document().to_dict()}
    response = process_request(request)
    assert response["ok"]
    forged = copy.deepcopy(response)
    row = forged["result"]["features"][-1]
    face = next(f for f in row["topology"] if f["role"] == "blend.surface")
    if mutation == "pair":
        face["provenance"]["source_faces"][0] = "b/face/cap.start"
    elif mutation == "count":
        face["provenance"]["image_count"] = 2
    elif mutation == "missing_source":
        # Keep source identity syntax valid but remove it from the actual replay ancestry.
        forged["result"]["features"][1]["topology"] = []
    else:
        evidence = importlib.import_module(package.__name__ + ".topology_evidence")
        with pytest.raises(ValueError):
            evidence.validate_topology(
                row["topology"],
                feature_id="blend",
                kind="chamfer",
                mesh=row["mesh"],
                source_features=document(selected=False).to_dict()["features"],
            )
        return
    with pytest.raises(ValueError):
        importlib.import_module(package.__name__ + ".result_v3").validate_response(request, forged)


@pytest.mark.parametrize("circular", [False, True])
def test_blend_boundary_projection_persists_and_drives_solved_reference(tmp_path, circular):
    from mechanical_cad.sketch_model import Circle, Constraint, Line, Point, SketchDefinition

    doc = document("fillet" if circular else "chamfer", circular=circular)
    pair = ["b/face/cap.end", "blend/face/blend.surface"]
    sketch = SketchDefinition(
        "reference_sketch",
        (Point("a", 0, 0), Point("b", 1, 0), Point("c", 0, 0)),
        () if circular else (Line("ref", "a", "b", construction=True),),
        (
            Constraint("a_fixed", "fixed", ("a",), target=(0, 0)),
            Constraint("b_fixed", "fixed", ("b",), target=(1, 0)),
            Constraint("c_fixed", "fixed", ("c",), target=(0, 0)),
            Constraint("profile_radius", "radius", ("profile",), 1),
        )
        + ((Constraint("reference_radius", "radius", ("ref",), 1),) if circular else ()),
        schema_version=2,
        circles=(Circle("profile", "c", 1),)
        + ((Circle("ref", "a", 1, construction=True),) if circular else ()),
    )
    row = (
        {"kind": "circle", "faces": pair, "target": "ref"}
        if circular
        else {
            "faces": pair,
            "endpoint_faces": [["b/face/side.x_max"], ["b/face/side.x_min"]],
            "target": "ref",
        }
    )
    projected = Feature(
        "projected",
        "sketch_constrained",
        "Blend edge reference",
        {},
        {"external": "blend"},
        sketch=sketch,
        projections=(row,),
    )
    doc = replace(
        doc, features=(*doc.features, projected), active_feature="projected", schema_version=2
    )
    path = tmp_path / "blend_reference.mcad.json"
    save_document(doc, path)
    for width, size in [(40, 2), (60, 3)]:
        edited = replace(load_document(path), parameters={"width": width, "size": size})
        request = {"protocol_version": 1, "result_version": 3, "document": edited.to_dict()}
        response = process_request(request)
        assert response["ok"], response
        importlib.import_module(package.__name__ + ".result_v3").validate_response(
            request, response
        )
        result = response["result"]["features"][-1]
        if circular:
            reference = next(c for c in result["sketch"]["solved"]["circles"] if c["id"] == "ref")
            assert reference["radius"] == pytest.approx(width - size)
        else:
            points = {p["id"]: p for p in result["sketch"]["solved"]["points"]}
            assert abs(points["a"]["u"] - points["b"]["u"]) == pytest.approx(width)
            assert points["a"]["v"] == pytest.approx(size)
        assert edited.features[-1].to_dict()["projections"] == [row]
