"""TNP.SUPPORT.001: an ordinary upstream slot splits a face, not its workplane."""

import copy
import importlib
import math
import sys
import types
from pathlib import Path

import pytest
from test_associative_sketch_support import attached_document

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document
from mechanical_cad.sidecar import process_request
from mechanical_cad.support_intent import resolve_support_signature


def split_document(*, split=True, preserve=True):
    data = attached_document().to_dict()
    data["features"] = data["features"][:3]
    attached = data["features"].pop()
    data["features"] += [
        {
            "id": "slot_profile",
            "kind": "sketch_rectangle",
            "params": {"width": 2, "height": 22, "x": 9, "y": -1, "z": 7},
        },
        {
            "id": "slot_tool",
            "kind": "extrude",
            "params": {"length": 5 if split else 1},
            "inputs": {"profile": "slot_profile"},
        },
        {"id": "slotted", "kind": "cut", "inputs": {"base": "block", "tool": "slot_tool"}},
    ]
    attached["inputs"]["support"] = "slotted"
    if preserve:
        attached["support_intent"] = {
            "version": 1,
            "policy": "preserve_plane",
            "signature": {
                "surface": "plane",
                "area": 400,
                "centroid": [10, 10, 10],
                "normal": [0, 0, 1],
            },
        }
    data["features"] += [
        attached,
        {
            "id": "boss",
            "kind": "extrude",
            "params": {"length": 2},
            "inputs": {"profile": "attached"},
        },
    ]
    data["active_feature"] = "boss"
    return Document.from_dict(data)


def rows(replay):
    return {row["id"]: row for row in replay.result["features"]}


def test_slot_split_keeps_original_anchor_and_downstream_geometry_after_save():
    before = regenerate(split_document(split=False), OCPKernel(), result_version=3)
    assert before.ok, before.result
    document = Document.from_json(split_document().to_json())
    canonical = document.to_json()
    replay = regenerate(document, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    result = rows(replay)
    assert result["slotted"]["stats"]["volume"] == pytest.approx(3880)
    assert result["attached"]["support_plane"] == rows(before)["attached"]["support_plane"]
    assert result["attached"]["support_plane"]["origin"] == pytest.approx([10, 10, 10])
    assert result["boss"]["stats"]["volume"] == pytest.approx(8 * math.pi)
    source = document.to_dict()["features"][-2]
    signature, decision = resolve_support_signature(
        source["support_face"],
        source["support_intent"],
        result["slotted"]["topology"],
        result["block"]["topology"],
    )
    assert decision["status"] == "assumed"
    assert decision["descendant_count"] == 2
    assert signature["centroid"] == [10, 10, 10]
    descendants = [
        f
        for f in result["slotted"]["topology"]
        if f["provenance"].get("source_id") == source["support_face"]
    ]
    assert all(
        f["provenance"]["semantic_status"] == "split" and f["id"].startswith("snapshot:")
        for f in descendants
    )
    assert document.to_json() == canonical  # replay does not mutate or silently accept a new face
    restored = regenerate(Document.from_json(canonical), OCPKernel(), result_version=3)
    assert rows(restored)["attached"]["support_plane"] == result["attached"]["support_plane"]


def test_legacy_strict_then_explicit_repair_and_undo():
    original = split_document(preserve=False)
    strict = regenerate(original, OCPKernel(), result_version=3)
    assert rows(strict)["attached"]["status"] == "failed"
    assert rows(strict)["boss"]["status"] == "blocked"
    repaired = split_document()
    assert regenerate(repaired, OCPKernel(), result_version=3).ok
    assert not regenerate(Document.from_json(original.to_json()), OCPKernel(), result_version=3).ok
    changed = repaired.to_dict()
    attached = changed["features"][-2]
    attached["support_face"] = "block/face/cap.start"
    attached.pop("support_intent")
    corrected = regenerate(Document.from_dict(changed), OCPKernel(), result_version=3)
    assert corrected.ok, corrected.result
    assert rows(corrected)["attached"]["support_plane"]["origin"][2] == pytest.approx(0)


def test_reordering_snapshot_ids_does_not_change_logical_plane():
    document = split_document()
    replay = regenerate(document, OCPKernel(), result_version=3)
    topology = rows(replay)["slotted"]["topology"]
    source = document.to_dict()["features"][-2]
    expected = resolve_support_signature(
        source["support_face"],
        source["support_intent"],
        topology,
        rows(replay)["block"]["topology"],
    )
    reordered = copy.deepcopy(list(reversed(topology)))
    for i, row in enumerate(reordered):
        if row["id"].startswith("snapshot:"):
            row["id"] = f"snapshot:slotted:face:{i}"
    assert (
        resolve_support_signature(
            source["support_face"],
            source["support_intent"],
            reordered,
            rows(replay)["block"]["topology"],
        )
        == expected
    )


def test_saved_anchor_follows_plane_normal_offset_not_fragment_centroid():
    data = split_document().to_dict()
    data["parameters"]["depth"] = 11
    replay = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert rows(replay)["attached"]["support_plane"]["origin"] == pytest.approx([10, 10, 11])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows.pop(),
        lambda rows: rows[0]["signature"]["normal"].__setitem__(2, -1),
        lambda rows: rows[0]["signature"]["centroid"].__setitem__(2, 12),
        lambda rows: rows[0]["provenance"].__setitem__("relation", "generated"),
        lambda rows: rows[0]["provenance"].__setitem__("source_count", 2),
        lambda rows: rows[0]["provenance"].__setitem__("operation", "fillet"),
    ],
)
def test_no_arbitrary_plane_choice_for_ambiguous_or_incomplete_descendants(mutate):
    document = split_document()
    replay = regenerate(document, OCPKernel(), result_version=3)
    source = document.to_dict()["features"][-2]
    descendants = copy.deepcopy(
        [
            r
            for r in rows(replay)["slotted"]["topology"]
            if r["provenance"].get("source_id") == source["support_face"]
        ]
    )
    mutate(descendants)
    with pytest.raises(ValueError):
        resolve_support_signature(
            source["support_face"],
            source["support_intent"],
            descendants,
            rows(replay)["block"]["topology"],
        )


def test_blender_contract_accepts_real_split_and_rejects_changed_plane():
    package = types.ModuleType("mcad_split_intent_contracts")
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    sys.modules[package.__name__] = package
    operations = importlib.import_module(package.__name__ + ".operation_contracts")
    request = {
        "protocol_version": 1,
        "action": "replay",
        "document": split_document().to_dict(),
        "result_version": 3,
    }
    response = process_request(request)
    assert response["ok"], response
    # Use the same public request-response validator exercised by attached sketches.
    operations.validate_response(request, response)
    forged = copy.deepcopy(response)
    row = next(f for f in forged["result"]["features"] if f["id"] == "attached")
    row["support_plane"]["origin"][0] += 1
    with pytest.raises(ValueError):
        operations.validate_response(request, forged)


def tilted_document(*, split=True):
    data = split_document(split=split, preserve=False).to_dict()
    data["features"].insert(
        2,
        {
            "id": "tilted_block",
            "kind": "transform",
            "params": {"rx": 30},
            "inputs": {"base": "block"},
        },
    )
    slot_index = next(i for i, row in enumerate(data["features"]) if row["id"] == "slotted")
    data["features"].insert(
        slot_index,
        {
            "id": "tilted_tool",
            "kind": "transform",
            "params": {"rx": 30},
            "inputs": {"base": "slot_tool"},
        },
    )
    next(row for row in data["features"] if row["id"] == "slotted")["inputs"] = {
        "base": "tilted_block",
        "tool": "tilted_tool",
    }
    return data


def test_non_xy_plane_survives_split_with_same_world_frame():
    data = tilted_document(split=False)
    before = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    assert before.ok, before.result
    signature = next(
        f["signature"]
        for f in rows(before)["tilted_block"]["topology"]
        if f["id"] == "block/face/cap.end"
    )
    data["features"][-2]["support_intent"] = {
        "version": 1,
        "policy": "preserve_plane",
        "signature": signature,
    }
    next(row for row in data["features"] if row["id"] == "slot_tool")["params"]["length"] = 5
    after = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    assert after.ok, after.result
    assert rows(after)["attached"]["support_plane"]["origin"] == pytest.approx(
        rows(before)["attached"]["support_plane"]["origin"]
    )
    assert rows(after)["attached"]["support_plane"]["quaternion"] == pytest.approx(
        rows(before)["attached"]["support_plane"]["quaternion"]
    )
    assert rows(after)["boss"]["stats"]["volume"] == pytest.approx(8 * math.pi)


@pytest.mark.parametrize("change", [{"rx": 40}, {"x": 3}])
def test_source_frame_change_follows_proven_base_workplane(change):
    data = tilted_document(split=False)
    before = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    signature = next(
        f["signature"]
        for f in rows(before)["tilted_block"]["topology"]
        if f["id"] == "block/face/cap.end"
    )
    data["features"][-2]["support_intent"] = {
        "version": 1,
        "policy": "preserve_plane",
        "signature": signature,
    }
    next(row for row in data["features"] if row["id"] == "slot_tool")["params"]["length"] = 5
    for row in data["features"]:
        if row["id"] in {"tilted_block", "tilted_tool"}:
            row["params"].update(change)
    replay = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    current = next(
        f["signature"]
        for f in rows(replay)["tilted_block"]["topology"]
        if f["id"] == "block/face/cap.end"
    )
    from mechanical_cad.support_plane import resolve_plane

    expected = resolve_plane(current, data["features"][-2]["sketch"]["plane"])
    assert rows(replay)["attached"]["support_plane"] == expected
    assert rows(replay)["boss"]["stats"]["volume"] == pytest.approx(8 * math.pi)


def test_intent_is_deeply_immutable_and_serializes_without_aliases():
    document = split_document()
    feature = document.features[-2]
    with pytest.raises(TypeError):
        feature.support_intent["signature"]["centroid"][0] = 100
    detached = document.to_dict()
    detached["features"][-2]["support_intent"]["signature"]["centroid"][0] = 100
    assert feature.support_intent["signature"]["centroid"][0] == 10


@pytest.mark.parametrize("version", [2, 3])
def test_split_support_solve_context_matches_full_replay(version):
    document = split_document()
    solved = process_request(
        {
            "protocol_version": 1,
            "result_version": version,
            "action": "solve_sketch",
            "feature_id": "attached",
            "document": document.to_dict(),
        }
    )
    assert solved["ok"], solved
    replay = regenerate(document, OCPKernel(), result_version=version)
    assert solved["result"]["support_context"]["plane"] == rows(replay)["attached"]["support_plane"]


def test_width_change_follows_original_source_centroid_not_piece_centroid():
    data = split_document().to_dict()
    data["features"][0]["params"]["width"] = 24
    replay = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    assert rows(replay)["attached"]["support_plane"]["origin"] == pytest.approx([12, 10, 10])


def test_saved_offset_from_source_frame_survives_rotation_and_translation():
    from mechanical_cad.support_plane import resolve_plane

    data = tilted_document(split=False)
    before = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    source = next(
        f["signature"]
        for f in rows(before)["tilted_block"]["topology"]
        if f["id"] == "block/face/cap.end"
    )
    signature = copy.deepcopy(source)
    signature["centroid"][0] -= 2  # A selected, already trimmed face's original anchor.
    data["features"][-2]["support_intent"] = {
        "version": 1,
        "policy": "preserve_plane",
        "signature": signature,
        "source_signature": source,
    }
    next(row for row in data["features"] if row["id"] == "slot_tool")["params"]["length"] = 5
    for row in data["features"]:
        if row["id"] in {"tilted_block", "tilted_tool"}:
            row["params"].update(rx=40, x=3)
    canonical = Document.from_dict(data)
    restored = Document.from_json(canonical.to_json())
    replay = regenerate(restored, OCPKernel(), result_version=3)
    assert replay.ok, replay.result
    current = next(
        f["signature"]
        for f in rows(replay)["tilted_block"]["topology"]
        if f["id"] == "block/face/cap.end"
    )
    local = copy.deepcopy(data["features"][-2]["sketch"]["plane"])
    local["origin"][0] -= 2
    expected = resolve_plane(current, local)
    actual = rows(replay)["attached"]["support_plane"]
    assert actual["origin"] == pytest.approx(expected["origin"])
    assert actual["quaternion"] == pytest.approx(expected["quaternion"])


def test_modified_split_unsplit_keeps_saved_nonzero_source_relative_anchor():
    data = split_document(preserve=False).to_dict()
    profile = next(row for row in data["features"] if row["id"] == "slot_profile")
    profile["params"].update(x=4, height=10)
    initial = regenerate(Document.from_dict(data), OCPKernel(), result_version=3)
    assert initial.ok, initial.result
    selected = next(
        f["signature"]
        for f in rows(initial)["slotted"]["topology"]
        if f["id"] == "block/face/cap.end"
    )
    baseline = next(
        f["signature"]
        for f in rows(initial)["block"]["topology"]
        if f["id"] == "block/face/cap.end"
    )
    assert selected["centroid"] != pytest.approx(baseline["centroid"])
    source = data["features"][-2]
    source["support_intent"] = {
        "version": 1,
        "policy": "preserve_plane",
        "signature": selected,
        "source_signature": baseline,
    }
    expected = rows(initial)["attached"]["support_plane"]
    seen_identity = []
    for height in (10, 14, 22, 14, 10):
        profile["params"]["height"] = height
        document = Document.from_json(Document.from_dict(data).to_json())
        replay = regenerate(document, OCPKernel(), result_version=3)
        assert replay.ok, replay.result
        result = rows(replay)
        actual = result["attached"]["support_plane"]
        assert actual["origin"] == pytest.approx(expected["origin"]), (height, actual, expected)
        assert actual["quaternion"] == pytest.approx(expected["quaternion"])
        assert result["boss"]["stats"]["volume"] == pytest.approx(8 * math.pi)
        exact = [f for f in result["slotted"]["topology"] if f["id"] == source["support_face"]]
        seen_identity.append("stable" if exact else "split")
        _, decision = resolve_support_signature(
            source["support_face"],
            source["support_intent"],
            result["slotted"]["topology"],
            result["block"]["topology"],
        )
        assert decision["policy"] == "preserve_plane" and decision["status"] == "assumed"
        assert decision["identity_status"] == ("stable" if exact else "split")
        if height == 14:
            strict_data = document.to_dict()
            strict_data["features"][-2].pop("support_intent")
            strict = regenerate(Document.from_dict(strict_data), OCPKernel(), result_version=3)
            assert strict.ok
            assert rows(strict)["attached"]["support_plane"]["origin"] == pytest.approx(
                exact[0]["signature"]["centroid"]
            )
            assert rows(strict)["attached"]["support_plane"]["origin"] != pytest.approx(
                expected["origin"]
            )
    assert seen_identity == ["stable", "stable", "split", "stable", "stable"]
