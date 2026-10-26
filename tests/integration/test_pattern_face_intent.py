"""Authored occurrence intent uses exact native history, not physical proximity."""

import copy
import importlib
import sys
import types
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel, TopAbs_FACE, _subshapes
from mechanical_cad.model import Document, Feature, load_document, save_document
from mechanical_cad.sidecar import process_request

package = types.ModuleType("pattern_face_client")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package


def face_id(occurrence, source="tool/face/side.circle"):
    return f"holes/face/pattern.copy.{occurrence}." + sha256(source.encode()).hexdigest()


def document(kind="linear_cut_pattern", *, blind=False, attached=False):
    circular = kind == "circular_cut_pattern"
    features = (
        Feature(
            "p", "sketch_rectangle", "Plate", {"width": 100, "height": 100, "x": -50, "y": -50}
        ),
        Feature("base", "extrude", "Base", {"length": "height"}, {"profile": "p"}),
        Feature(
            "c",
            "sketch_circle",
            "Hole",
            {"radius": "radius", "x": 15 if circular else -15, "z": 2 if blind else -2},
        ),
        Feature("tool", "extrude", "Tool", {"length": 20}, {"profile": "c"}),
        Feature(
            "holes",
            kind,
            "Holes",
            {"count": "count", **({"angle": "angle"} if circular else {"dx": "pitch"})},
            {"base": "base", "tool": "tool"},
        ),
    )
    if attached:
        features += (
            Feature(
                "on_floor",
                "sketch_face_circle",
                "On copy 3 floor",
                {"radius": 0.5},
                {"support": "holes"},
                support_face=face_id(2, "tool/face/cap.start"),
            ),
        )
    return Document(
        "d",
        "Pattern intent",
        {"height": 8, "radius": 2, "pitch": 15, "count": 3, "angle": 360},
        features,
        features[-1].id,
        schema_version=2,
    )


def validated(doc, version=3):
    request = {"protocol_version": 1, "result_version": version, "document": doc.to_dict()}
    response = process_request(request)
    importlib.import_module(
        package.__name__ + (".result_v3" if version == 3 else ".part_result_bridge")
    ).validate_response(request, response)
    return request, response


@pytest.mark.parametrize("kind", ["linear_cut_pattern", "circular_cut_pattern"])
@pytest.mark.parametrize("version", [2, 3])
def test_occurrence_floor_sketch_survives_edit_save_replay(tmp_path, kind, version):
    doc = document(kind, blind=True, attached=True)
    path = tmp_path / "pattern.mcad.json"
    save_document(doc, path)
    for updates in ({}, {"height": 10, "radius": 3, "pitch": 18, "count": 4, "angle": 270}):
        edited = replace(load_document(path), parameters={**doc.parameters, **updates})
        _, response = validated(edited, version)
        assert response["ok"], response
        row = response["result"]["features"][4]
        floor = next(f for f in row["topology"] if f["id"] == face_id(2, "tool/face/cap.start"))
        assert floor["signature"]["surface"] == "plane"
        assert floor["signature"]["centroid"][2] == pytest.approx(2)
        assert floor["provenance"]["occurrence"] == 2
        assert response["result"]["features"][-1]["status"] == "ok"
        assert row["stats"]["solids"] == 1


def test_wall_circle_reference_and_selected_blend_are_reusable():
    doc = document()
    kernel = OCPKernel()
    replay = regenerate(doc, kernel, result_version=3)
    pair = ["base/face/cap.end", face_id(1)]
    circle = kernel.projected_circle(replay.shapes["holes"], pair)
    assert circle["radius"] == pytest.approx(2)
    blend = Feature(
        "blend",
        "fillet",
        "Round hole 2",
        {"radius": 0.3},
        {"base": "holes"},
        edge_faces=tuple(pair),
    )
    doc = replace(doc, features=(*doc.features, blend), active_feature="blend")
    _, response = validated(doc)
    assert response["ok"], response
    assert any(f["id"] == face_id(1) for f in response["result"]["features"][-1]["topology"])


@pytest.mark.parametrize("change", [{"count": 2}, {"pitch": 100}, {"pitch": 3}])
def test_removed_noop_or_overlapping_occurrence_fails_closed(change):
    doc = document(blind=True, attached=True)
    doc = replace(doc, parameters={**doc.parameters, **change})
    _, response = validated(doc)
    assert not response["ok"]
    assert response["result"]["features"][-1]["status"] == "failed"
    assert not any(
        f["id"] == face_id(2, "tool/face/cap.start")
        for f in response["result"]["features"][4]["topology"]
    )


@pytest.mark.parametrize("kind", ["linear_cut_pattern", "circular_cut_pattern"])
def test_legacy_keeps_pattern_walls_snapshot_only(kind):
    replay = regenerate(document(kind), OCPKernel(), result_version=1)
    assert replay.ok
    assert all(
        not f["role"].startswith("pattern.copy.") for f in replay.result["features"][-1]["topology"]
    )


@pytest.mark.parametrize(
    "mutation",
    ["source", "occurrence", "count", "role", "missing_source", "unstable_source", "extra_field"],
)
def test_native_free_validator_rejects_forged_occurrence(mutation):
    request, response = validated(document())
    forged = copy.deepcopy(response)
    rows = forged["result"]["features"]
    face = next(f for f in rows[-1]["topology"] if f["id"] == face_id(1))
    if mutation == "source":
        face["provenance"]["source_id"] = "base/face/cap.end"
    elif mutation == "occurrence":
        face["provenance"]["occurrence"] = True
    elif mutation == "count":
        # Keep role/hash internally consistent but cite a nonexistent copy.
        old = face["id"]
        face["id"], face["role"] = face_id(3), face_id(3).split("/face/")[1]
        face["provenance"]["occurrence"] = 3
        rows[-1]["mesh"]["triangle_face_ids"] = [
            face["id"] if x == old else x for x in rows[-1]["mesh"]["triangle_face_ids"]
        ]
    elif mutation == "role":
        face["role"] = face["role"][:-1] + "0"
    elif mutation == "missing_source":
        rows[3]["topology"] = []
    elif mutation == "unstable_source":
        source = next(f for f in rows[3]["topology"] if f["role"] == "side.circle")
        source["provenance"]["semantic_status"] = "unknown"
    else:
        face["provenance"]["nearest_face"] = 1
    with pytest.raises(ValueError):
        importlib.import_module(package.__name__ + ".result_v3").validate_response(request, forged)


@pytest.mark.parametrize("ambiguity", ["split", "competing", "unknown", "generated"])
def test_nonunique_native_pattern_history_is_not_promoted(ambiguity):
    kernel = OCPKernel()
    replay = regenerate(document(), kernel, result_version=3)
    op = kernel._operations[id(replay.shapes["holes"])]
    faces = _subshapes(op.shape, TopAbs_FACE)
    target = next(f for f, c in op.faces if c["id"] == face_id(1))
    entry = next(x for x in op.pattern_sources if x[0] == 1 and x[2]["role"] == "side.circle")
    source = entry[1]
    original = op.builder
    if ambiguity in {"competing", "unknown"}:
        candidate = copy.deepcopy(entry[2])
        candidate["id"] = "other/face/side.circle"
        if ambiguity == "unknown":
            candidate["provenance"]["semantic_status"] = "unknown"
        op.pattern_sources.append((1, source, candidate, True))

    class History:
        def Modified(self, shape):
            if ambiguity == "split" and shape.IsSame(source):
                return [target, next(f for f in faces if not f.IsSame(target))]
            return original.Modified(shape)

        def Generated(self, shape):
            if ambiguity == "generated" and shape.IsSame(source):
                return [target]
            return original.Generated(shape)

        def IsDeleted(self, shape):
            return original.IsDeleted(shape)

    op.builder = History()
    result = kernel._pattern_face_topology(op, faces, "holes", [])
    assert not any(c["id"] == face_id(1) for _, c in result)


def test_native_split_wall_retains_only_snapshot_handles():
    doc = document()
    slot = (
        Feature(
            "slot",
            "sketch_rectangle",
            "Cross slot",
            {"width": 40, "height": 1, "x": -20, "y": -0.5, "z": -2},
        ),
        Feature("slot_tool", "extrude", "Slot tool", {"length": 20}, {"profile": "slot"}),
        Feature("slotted", "cut", "Slotted plate", {}, {"base": "base", "tool": "slot_tool"}),
    )
    holes = replace(doc.features[-1], inputs={"base": "slotted", "tool": "tool"})
    doc = replace(doc, features=(*doc.features[:-1], *slot, holes))
    _, response = validated(doc)
    assert response["ok"], response
    row = response["result"]["features"][-1]
    assert not any(f["role"].startswith("pattern.copy.") for f in row["topology"])
    assert len([f for f in row["topology"] if f["signature"]["surface"] == "cylinder"]) == 6


def test_labels_show_human_occurrence_and_original_tool_face():
    _, response = validated(document())
    face = next(f for f in response["result"]["features"][-1]["topology"] if f["id"] == face_id(1))
    label = importlib.import_module(package.__name__ + ".topology_labels").face_label(face)
    assert label == "Hole copy 2 from tool / side.circle"
