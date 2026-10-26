"""Multiple explicit planar openings: native geometry and strict transport."""

import copy
from dataclasses import replace
from hashlib import sha256

import pytest
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT
from test_open_shell import document
from test_open_shell_lineage import validator, validator3

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import KernelError, OCPKernel
from mechanical_cad.model import CADException, Document, Feature
from mechanical_cad.sidecar import process_request

OPPOSITE = ("b/face/cap.start", "b/face/cap.end")
ADJACENT = ("b/face/cap.end", "b/face/side.x_max")


@pytest.mark.parametrize(
    "openings,volume",
    [
        (OPPOSITE, 660),
        (ADJACENT, 777),
        ((*ADJACENT, "b/face/side.y_max"), 606),
    ],
)
@pytest.mark.parametrize("version", [1, 2, 3])
def test_native_multiple_planar_openings(openings, volume, version):
    kernel = OCPKernel()
    replay = regenerate(
        Document.from_json(document(openings).to_json()), kernel, result_version=version
    )
    assert replay.ok, replay.result
    stats = kernel.inspect(replay.shapes["s"])
    assert stats["valid"] and stats["solids"] == 1
    assert stats["volume"] == pytest.approx(volume)
    # Both ends of the through sleeve are empty; retained wall is material.
    if openings == OPPOSITE:
        for point, state in [
            ((10, 7, 0.5), TopAbs_OUT),
            ((10, 7, 9.5), TopAbs_OUT),
            ((0.5, 7, 5), TopAbs_IN),
        ]:
            assert (
                BRepClass3d_SolidClassifier(replay.shapes["s"], gp_Pnt(*point), 1e-7).State()
                == state
            )
    if version >= 2:
        row = replay.result["features"][-1]
        lips = [f for f in row["topology"] if f["role"].startswith("shell.opening_lip.")]
        assert {f["provenance"]["source_id"] for f in lips} == set(openings)
        assert len({f["id"] for f in row["topology"]}) == len(row["topology"])
        for face in lips:
            assert (
                face["role"]
                == "shell.opening_lip."
                + sha256(face["provenance"]["source_id"].encode()).hexdigest()
            )


@pytest.mark.parametrize("version", [2, 3])
def test_strict_transport_and_forged_lip_refusal(version):
    request = {
        "protocol_version": 1,
        "result_version": version,
        "document": document(OPPOSITE).to_dict(),
    }
    response = process_request(request)
    assert response["ok"], response
    validate = validator.validate_response if version == 2 else validator3.validate_response
    validate(request, response)
    forged = copy.deepcopy(response)
    row = forged["result"]["features"][-1]
    lips = [f for f in row["topology"] if f["role"].startswith("shell.opening_lip.")]
    lips[0]["provenance"]["source_id"] = lips[1]["provenance"]["source_id"]
    with pytest.raises(ValueError):
        validate(request, forged)


def test_edits_order_and_round_trip_keep_source_bound_lips():
    doc = document(OPPOSITE)
    original = regenerate(doc, OCPKernel(), result_version=3)
    edited = replace(
        doc,
        parameters={"wall": 2},
        features=(
            replace(doc.features[0], params={"width": 30, "height": 15}),
            doc.features[1],
            replace(doc.features[-1], opening_faces=tuple(reversed(OPPOSITE))),
        ),
    )
    restored = Document.from_json(edited.to_json())
    replay = regenerate(restored, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(4500 - 26 * 11 * 10)
    for result in (original, replay):
        assert {f["id"] for f in result.result["features"][-1]["topology"]} == {
            f["id"] for f in original.result["features"][-1]["topology"]
        }
    assert restored.features[-1].opening_faces == tuple(reversed(OPPOSITE))


@pytest.mark.parametrize("bad", ["missing/face/lid", "snapshot:b:face:0"])
def test_one_bad_opening_never_silently_uses_good_subset(bad):
    if bad.startswith("snapshot:"):
        with pytest.raises(CADException):
            Document.from_json(document((OPPOSITE[0], bad)).to_json())
        return
    doc = document((OPPOSITE[0], bad))
    doc = replace(
        doc,
        features=doc.features + (Feature("t", "transform", "Dependent", {"x": 5}, {"base": "s"}),),
        active_feature="t",
    )
    replay = regenerate(doc, OCPKernel(), result_version=3)
    assert not replay.ok and not {"s", "t"} & replay.shapes.keys()
    assert [f["status"] for f in replay.result["features"]][-2:] == ["failed", "blocked"]
    assert bad in replay.result["features"][-2]["error"]["message"]


@pytest.mark.parametrize("value", [["a", "a"], [str(i) for i in range(65)], [["a"]]])
def test_duplicate_oversized_and_malformed_lists_refused(value):
    raw = document().to_dict()
    raw["features"][-1]["opening_faces"] = value
    with pytest.raises(CADException):
        Document.from_dict(raw)


def test_ambiguous_second_opening_and_native_alias_refused():
    kernel = OCPKernel()
    doc = document(OPPOSITE)
    base = regenerate(
        replace(doc, features=doc.features[:2], active_feature="b"), kernel, result_version=3
    )
    shape = base.shapes["b"]
    operation = kernel._operations[id(shape)]
    face, candidate = next((f, c) for f, c in operation.faces if c["id"] == OPPOSITE[1])
    duplicate = copy.deepcopy(candidate)
    duplicate["provenance"]["semantic_status"] = "unknown"
    operation.faces.append((face, duplicate))
    with pytest.raises(KernelError, match="ambiguous"):
        kernel.shell(shape, 1, opening_faces=OPPOSITE)
    operation.faces.pop()
    duplicate["id"] = "alias/face/lid"
    duplicate["provenance"]["semantic_status"] = "stable"
    operation.faces.append((face, duplicate))
    with pytest.raises(KernelError, match="alias"):
        kernel.shell(shape, 1, opening_faces=(OPPOSITE[1], duplicate["id"]))


def test_actual_split_second_opening_fails_closed():
    doc = document(OPPOSITE)
    features = doc.features[:2] + (
        Feature(
            "tp", "sketch_rectangle", "Channel", {"width": 2, "height": 20, "x": 9, "y": -2, "z": 8}
        ),
        Feature("tool", "extrude", "Tool", {"length": 4}, {"profile": "tp"}),
        Feature("cut", "cut", "Split lid", {}, {"base": "b", "tool": "tool"}),
        replace(doc.features[-1], inputs={"base": "cut"}),
    )
    replay = regenerate(replace(doc, features=features), OCPKernel(), result_version=3)
    assert not replay.ok and "s" not in replay.shapes
    assert "split" in replay.result["features"][-1]["error"]["message"]


def test_planar_circular_end_openings_make_valid_tube_but_curved_opening_fails():
    doc = document(OPPOSITE)
    doc = replace(
        doc, features=(Feature("p", "sketch_circle", "Circle", {"radius": 10}), *doc.features[1:])
    )
    replay = regenerate(doc, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    import math

    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
        math.pi * (100 - 81) * 10
    )
    curved = next(
        f["id"]
        for f in replay.result["features"][1]["topology"]
        if f["signature"]["surface"] != "plane"
    )
    invalid = replace(
        doc,
        features=(
            *doc.features[:2],
            replace(doc.features[-1], opening_faces=(OPPOSITE[0], curved)),
        ),
    )
    failure = regenerate(invalid, OCPKernel(), result_version=3)
    assert not failure.ok and "s" not in failure.shapes
    assert "planar" in failure.result["features"][-1]["error"]["message"]


def test_impossible_multi_opening_wall_never_publishes_geometry():
    replay = regenerate(document(OPPOSITE, thickness=20), OCPKernel(), result_version=3)
    assert not replay.ok and "s" not in replay.shapes
    assert replay.result["features"][-1]["mesh"] is None
