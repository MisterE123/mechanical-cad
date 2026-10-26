"""Explicit edge sets resolve completely; legacy intent and strict naming stay intact."""

import copy
import importlib
import math
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.blend_selection import selected_surface_role
from mechanical_cad.engine import regenerate
from mechanical_cad.errors import CADException
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.part_snapshot import input_fingerprint
from mechanical_cad.sidecar import process_request

package = types.ModuleType("multi_blend_client")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
PAIRS = (("b/face/cap.end", "b/face/side.y_min"), ("b/face/cap.end", "b/face/side.y_max"))


def document(kind="chamfer", pairs=PAIRS):
    return Document(
        "d",
        "Explicit edge set",
        {"width": 40, "size": 2},
        (
            Feature("p", "sketch_rectangle", "P", {"width": "width", "height": 30}),
            Feature("b", "extrude", "B", {"length": 10}, {"profile": "p"}),
            Feature(
                "blend",
                kind,
                "Blend",
                {"radius" if kind == "fillet" else "distance": "size"},
                {"base": "b"},
                edge_pairs=pairs,
            ),
        ),
        "blend",
    )


@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
@pytest.mark.parametrize("version", [1, 2, 3])
def test_two_edges_native_volume_edit_roundtrip(kind, version):
    for width, size in [(40, 2), (60, 3)]:
        doc = replace(document(kind), parameters={"width": width, "size": size})
        restored = Document.from_json(doc.to_json())
        kernel = OCPKernel()
        replay = regenerate(restored, kernel, result_version=version)
        assert replay.ok, replay.result
        stats = kernel.inspect(replay.shapes["blend"])
        removed = size * size * (1 if kind == "chamfer" else 2 * (1 - math.pi / 4))
        assert stats["valid"] and stats["solids"] == 1
        assert stats["volume"] == pytest.approx(width * (300 - removed))
        generated = [
            f
            for f in replay.result["features"][-1]["topology"]
            if f["role"].startswith("blend.surface")
        ]
        assert {f["role"] for f in generated} == (
            {selected_surface_role(pair, 2) for pair in PAIRS} if version > 1 else set()
        )
        if version > 1:
            operation = kernel._operations[id(replay.shapes["blend"])]
            for edge, pair in operation.blend_selections:
                native = next(
                    face
                    for face, item in operation.faces
                    if item["role"] == selected_surface_role(pair, 2)
                )
                assert any(native.IsSame(face) for face in operation.builder.Generated(edge))
        assert restored.features[-1].edge_pairs == tuple(sorted(PAIRS))


@pytest.mark.parametrize("version", [2, 3])
def test_strict_clients_accept_complete_edge_set(version):
    validator = importlib.import_module(
        package.__name__ + (".part_result_bridge" if version == 2 else ".result_v3")
    )
    request = {"protocol_version": 1, "result_version": version, "document": document().to_dict()}
    response = process_request(request)
    assert response["ok"], response
    validator.validate_response(request, response)
    # Existing single-edge surface cannot be forged onto a multi-edge operation.
    forged = copy.deepcopy(response)
    row = forged["result"]["features"][-1]
    face = row["topology"][-1]
    face["id"] = "blend/face/blend.surface"
    face["role"] = "blend.surface"
    face["provenance"].update(
        semantic_status="stable",
        relation="generated_from_selected_edge",
        source_faces=list(PAIRS[0]),
        image_count=1,
    )
    with pytest.raises(ValueError):
        validator.validate_response(request, forged)


@pytest.mark.parametrize(
    "pair", [("missing/face/a", "b/face/cap.end"), ("b/face/cap.start", "b/face/cap.end")]
)
def test_bad_member_blocks_whole_blend_and_dependents(pair):
    doc = document(pairs=(PAIRS[0], pair))
    doc = replace(
        doc,
        features=doc.features + (Feature("move", "transform", "Move", {}, {"base": "blend"}),),
        active_feature="move",
    )
    replay = regenerate(doc, OCPKernel(), result_version=3)
    assert not replay.ok
    assert [f["status"] for f in replay.result["features"]][-2:] == ["failed", "blocked"]
    assert "blend" not in replay.shapes and "move" not in replay.shapes


def test_canonical_set_order_and_legacy_serialization():
    doc = document()
    reversed_doc = replace(
        doc,
        features=doc.features[:-1]
        + (
            replace(
                doc.features[-1], edge_pairs=tuple(tuple(reversed(p)) for p in reversed(PAIRS))
            ),
        ),
    )
    assert reversed_doc.to_json() == doc.to_json()
    for pair in (None, PAIRS[0]):
        legacy = replace(doc.features[-1], edge_pairs=None, edge_faces=pair)
        assert "edge_pairs" not in legacy.to_dict()
        assert Feature.from_dict(legacy.to_dict()) == legacy


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        "bad",
        [list(PAIRS[0])] * 2,
        [list(PAIRS[0]), list(reversed(PAIRS[0]))],
        [["same", "same"]],
        [["snapshot:b:face:0", "b/face/cap.end"]],
        [["a", "b", "c"]],
        [["a", str(i)] for i in range(65)],
    ],
)
def test_invalid_saved_selection_rejected_everywhere(value):
    data = document().to_dict()
    data["features"][-1]["edge_pairs"] = value
    with pytest.raises(CADException):
        Document.from_dict(data)
    for module in ("part_contracts", "part_contracts_v3"):
        validator = importlib.import_module(package.__name__ + "." + module)
        with pytest.raises(ValueError):
            validator._expected_document(data)


def test_dual_intent_and_non_blend_rejected():
    data = document().to_dict()
    data["features"][-1]["edge_faces"] = list(PAIRS[0])
    with pytest.raises(CADException):
        Document.from_dict(data)
    with pytest.raises(CADException):
        Feature("bad", "transform", "Bad", {}, {"base": "b"}, edge_pairs=PAIRS)


def test_real_cut_split_in_one_member_cannot_rebind_to_a_fragment():
    doc = document()
    features = doc.features[:2] + (
        Feature(
            "tool_p",
            "sketch_rectangle",
            "Notch",
            {"width": 5, "height": 40, "x": 15, "y": -5, "z": 5},
        ),
        Feature("tool", "extrude", "Notch tool", {"length": 10}, {"profile": "tool_p"}),
        Feature("cut", "cut", "Split top", {}, {"base": "b", "tool": "tool"}),
        replace(
            doc.features[-1],
            inputs={"base": "cut"},
            edge_pairs=(
                ("b/face/cap.start", "b/face/side.y_min"),
                PAIRS[0],
            ),
        ),
    )
    replay = regenerate(replace(doc, features=features), OCPKernel(), result_version=3)
    assert not replay.ok
    cut = next(row for row in replay.result["features"] if row["id"] == "cut")
    assert cut["status"] == "ok"
    assert not any(
        face["id"] == "b/face/cap.end" and face["provenance"]["semantic_status"] == "stable"
        for face in cut["topology"]
    )
    assert replay.result["features"][-1]["status"] == "failed"
    assert "blend" not in replay.shapes


@pytest.mark.parametrize("version", [2, 3])
def test_multi_chamfer_support_projection_survive_edits_and_roundtrip(version):
    doc = document()
    identifier = "blend/face/" + selected_surface_role(PAIRS[0], 2)
    doc = replace(
        doc,
        features=doc.features
        + (
            Feature(
                "support",
                "sketch_face_circle",
                "On chosen bevel",
                {"radius": 0.3},
                {"support": "blend"},
                support_face=identifier,
            ),
        ),
        active_feature="support",
    )
    validator = importlib.import_module(
        package.__name__ + (".part_result_bridge" if version == 2 else ".result_v3")
    )
    for width, size in [(40, 2), (60, 3)]:
        edited = Document.from_json(
            replace(doc, parameters={"width": width, "size": size}).to_json()
        )
        kernel = OCPKernel()
        replay = regenerate(edited, kernel, result_version=version)
        assert replay.ok, replay.result
        request = {"protocol_version": 1, "result_version": version, "document": edited.to_dict()}
        # Validate the replay without a second native rebuild.
        response = {
            "protocol_version": 1,
            "result_version": version,
            "input_fingerprint": input_fingerprint(request),
            "ok": True,
            "result": replay.result,
            "error": None,
        }
        validator.validate_response(request, response)
        pair = ["b/face/cap.end", identifier]
        edge = kernel.projected_edge_endpoints(replay.shapes["blend"], [pair])[0]
        assert math.dist(*edge["points"]) == pytest.approx(width)
        assert edge["endpoint_faces"] == [["b/face/side.x_max"], ["b/face/side.x_min"]]
        for mutation in ("role", "pair", "count"):
            forged = copy.deepcopy(response)
            face = next(
                f for f in forged["result"]["features"][2]["topology"] if f["id"] == identifier
            )
            if mutation == "role":
                face["role"] = selected_surface_role(["other", "pair"], 2)
                face["id"] = "blend/face/" + face["role"]
            elif mutation == "pair":
                face["provenance"]["source_faces"] = list(PAIRS[1])
            else:
                face["provenance"]["image_count"] = 2
            with pytest.raises(ValueError):
                validator.validate_response(request, forged)


def test_singleton_set_owns_legacy_role_and_removing_pair_blocks_support():
    singleton = document(pairs=(PAIRS[0],))
    replay = regenerate(singleton, OCPKernel(), result_version=3)
    assert replay.ok
    assert sum(f["role"] == "blend.surface" for f in replay.result["features"][-1]["topology"]) == 1
    doc = document(pairs=(PAIRS[1], ("b/face/cap.start", "b/face/side.y_min")))
    identifier = "blend/face/" + selected_surface_role(PAIRS[0], 2)
    doc = replace(
        doc,
        features=doc.features
        + (
            Feature(
                "support",
                "sketch_face_circle",
                "Removed bevel",
                {"radius": 0.3},
                {"support": "blend"},
                support_face=identifier,
            ),
        ),
        active_feature="support",
    )
    replay = regenerate(doc, OCPKernel(), result_version=3)
    assert not replay.ok
    assert replay.result["features"][-2]["status"] == "ok"
    assert replay.result["features"][-1]["status"] == "failed"
