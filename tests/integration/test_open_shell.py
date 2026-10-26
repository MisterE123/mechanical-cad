"""Exact open enclosure geometry and conservative persistent opening references."""

from dataclasses import replace

import pytest
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import CADException, Document, Feature


def document(opening=("b/face/cap.end",), thickness="wall"):
    return Document(
        "part",
        "Open enclosure",
        {"wall": 1},
        (
            Feature("p", "sketch_rectangle", "Rectangle", {"width": 20, "height": 15}),
            Feature("b", "extrude", "Box", {"length": 10}, {"profile": "p"}),
            Feature(
                "s",
                "shell",
                "Enclosure",
                {"thickness": thickness},
                {"base": "b"},
                opening_faces=opening,
            ),
        ),
        "s",
    )


@pytest.mark.parametrize("version", [1, 2, 3])
def test_open_shell_is_one_exact_valid_enclosure(version):
    doc = Document.from_json(document().to_json())
    kernel = OCPKernel()
    replay = regenerate(doc, kernel, result_version=version)
    assert replay.ok, replay.result
    stats = kernel.inspect(replay.shapes["s"])
    assert stats["valid"] and stats["solids"] == 1
    assert stats["volume"] == pytest.approx(20 * 15 * 10 - 18 * 13 * 9)
    shape = replay.shapes["s"]
    for point, expected in [
        ((10, 7, 9.5), TopAbs_OUT),
        ((10, 7, 0.5), TopAbs_IN),
        ((0.5, 7, 9.5), TopAbs_IN),
    ]:
        assert BRepClass3d_SolidClassifier(shape, gp_Pnt(*point), 1e-7).State() == expected


def test_upstream_dimensions_and_thickness_edit_keep_same_opening():
    doc = document()
    edited = replace(
        doc,
        parameters={"wall": 2},
        features=(replace(doc.features[0], params={"width": 30, "height": 15}), *doc.features[1:]),
    )
    restored = Document.from_json(edited.to_json())
    replay = regenerate(restored, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(4500 - 26 * 11 * 8)
    assert restored.features[-1].params["thickness"] == "wall"
    assert restored.features[-1].opening_faces == ("b/face/cap.end",)


def test_side_opening_and_closed_legacy_are_distinct():
    for opening, volume in [
        (("b/face/side.x_max",), 3000 - 19 * 13 * 8),
        (None, 3000 - 18 * 13 * 8),
    ]:
        doc = document(opening)
        replay = regenerate(doc, OCPKernel())
        assert replay.ok, replay.result
        assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(volume)
        if opening is None:
            assert "opening_faces" not in doc.to_dict()["features"][-1]


@pytest.mark.parametrize("opening", ["missing/face/cap.end", "b/face/side.unknown"])
def test_unresolved_opening_fails_and_blocks_dependents(opening):
    doc = document((opening,))
    doc = replace(
        doc,
        features=doc.features + (Feature("t", "transform", "Dependent", {"x": 5}, {"base": "s"}),),
        active_feature="t",
    )
    replay = regenerate(doc, OCPKernel(), result_version=3)
    assert not replay.ok
    assert [f["status"] for f in replay.result["features"]] == ["ok", "ok", "failed", "blocked"]
    assert not {"s", "t"} & replay.shapes.keys()
    assert "ambiguous" in replay.result["features"][2]["error"]["message"]


def test_impossible_thickness_does_not_publish_a_solid():
    replay = regenerate(document(thickness=20), OCPKernel(), result_version=3)
    assert not replay.ok and "s" not in replay.shapes
    assert replay.result["features"][-1]["mesh"] is None


@pytest.mark.parametrize(
    "value", [[], ["a", "a"], ["snapshot:face"], ["pending:face"], [None], None, "a"]
)
def test_invalid_opening_payload_rejected_before_geometry(value):
    raw = document().to_dict()
    raw["features"][-1]["opening_faces"] = value
    with pytest.raises(CADException, match="distinct stable planar"):
        Document.from_dict(raw)


def test_curved_opening_fails_instead_of_guessing():
    doc = document(("b/face/side.circle",))
    doc = replace(
        doc, features=(Feature("p", "sketch_circle", "Circle", {"radius": 10}), *doc.features[1:])
    )
    base = regenerate(replace(doc, features=doc.features[:2], active_feature="b"), OCPKernel())
    side = next(
        f["id"]
        for f in base.result["features"][-1]["topology"]
        if f["signature"]["surface"] != "plane"
    )
    doc = replace(
        doc, features=(*doc.features[:2], replace(doc.features[-1], opening_faces=(side,)))
    )
    replay = regenerate(doc, OCPKernel())
    assert not replay.ok and "planar" in replay.result["features"][-1]["error"]["message"]


def test_actual_split_opening_lineage_is_not_rebound():
    # A channel cuts across the lid, dividing its one stable face into two.
    doc = document(("b/face/cap.end",))
    features = doc.features[:2] + (
        Feature(
            "tool_profile",
            "sketch_rectangle",
            "Channel",
            {"width": 2, "height": 20, "x": 9, "y": -2, "z": 8},
        ),
        Feature("tool", "extrude", "Channel tool", {"length": 4}, {"profile": "tool_profile"}),
        Feature("cut", "cut", "Split lid", {}, {"base": "b", "tool": "tool"}),
        replace(doc.features[-1], inputs={"base": "cut"}),
    )
    replay = regenerate(replace(doc, features=features), OCPKernel(), result_version=3)
    assert not replay.ok
    assert replay.result["features"][-2]["status"] == "ok"
    assert replay.result["features"][-1]["status"] == "failed"
    assert "split" in replay.result["features"][-1]["error"]["message"]


def test_deleted_opening_lineage_is_not_rebound():
    # Removing the whole lid region generates a different face lower down.
    doc = document()
    features = doc.features[:2] + (
        Feature(
            "tool_profile",
            "sketch_rectangle",
            "Slice",
            {"width": 24, "height": 19, "x": -2, "y": -2, "z": 8},
        ),
        Feature("tool", "extrude", "Slice tool", {"length": 4}, {"profile": "tool_profile"}),
        Feature("cut", "cut", "Remove lid", {}, {"base": "b", "tool": "tool"}),
        replace(doc.features[-1], inputs={"base": "cut"}),
    )
    replay = regenerate(replace(doc, features=features), OCPKernel(), result_version=3)
    assert not replay.ok and replay.result["features"][-2]["status"] == "ok"
    assert "missing" in replay.result["features"][-1]["error"]["message"]
