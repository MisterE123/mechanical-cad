"""All-instance occlusion is geometric first; transient mesh copies are detached."""

import copy
import importlib

import pytest
from test_assembly_edit import PACKAGE
from test_assembly_insert_face_pick import IDENTITY, part

projection = importlib.import_module(PACKAGE + ".assembly_insert_pick_projection")
contract = importlib.import_module(PACKAGE + ".assembly_source_preview_contract")


def response(other_depth=0, curved=False, unstable=False):
    parts = [dict(part(), id="targetpart"), dict(part((other_depth,)), id="otherpart")]
    if curved:
        parts[1]["topology"][0]["signature"]["surface"] = "cylinder"
    if unstable:
        parts[1]["topology"][0]["provenance"]["semantic_status"] = "split"
    instances = [
        {"id": "newchild", "part_id": "targetpart"},
        {"id": "root", "part_id": "otherpart"},
    ]
    candidate = {
        "id": "assembly",
        "parts": [{"id": p["id"]} for p in parts],
        "instances": instances,
    }
    return {
        "ok": True,
        "result": {
            "canonical_assembly": copy.deepcopy(candidate),
            "assembly_digest": "a" * 64,
            "source_hashes": {"source": "b" * 64},
            "instances": instances,
            "parts": parts,
            "source_replays": [{"id": "source"}],
        },
        "report": {
            "base_pose": {
                "status": "evaluated",
                "transforms": {i["id"]: copy.deepcopy(IDENTITY) for i in instances},
            }
        },
    }


def build(value, **kw):
    return projection.PickProjection(
        value,
        contract.source_preview_fingerprint(value),
        value["result"]["canonical_assembly"],
        **kw,
    )


def test_coincident_root_child_refuse_default_but_explicit_target_only_succeeds():
    model = build(response())
    with pytest.raises(projection.BridgeError, match="occludes or overlaps"):
        model.pick("newchild", [0.5, 0.5, 5], [0, 0, -1])
    assert model.pick("newchild", [0.5, 0.5, 5], [0, 0, -1], target_only=True) == {
        "instance_id": "newchild",
        "face_id": "face0",
        "point_mm": (0.5, 0.5, 0),
        "distance_mm": 5,
    }


@pytest.mark.parametrize("kind", ["curved", "unstable"])
@pytest.mark.parametrize("depth", [-2, 2])
def test_unqualified_non_target_geometry_only_blocks_when_in_front(kind, depth):
    model = build(response(depth, **{kind: True}))
    if depth > 0:
        with pytest.raises(projection.BridgeError, match="occludes"):
            model.pick("newchild", [0.5, 0.5, 5], [0, 0, -1])
    else:
        assert model.pick("newchild", [0.5, 0.5, 5], [0, 0, -1])["face_id"] == "face0"


def test_mutated_response_candidate_and_exposed_geometry_cannot_change_projection():
    value = response(-2)
    model = build(value)
    vertices, triangles = model.target_geometry("newchild")
    assert type(vertices) is tuple and type(vertices[0]) is tuple and type(triangles) is tuple
    value["result"]["parts"][0]["mesh"]["vertices"][0][2] = 99
    value["report"]["base_pose"]["transforms"]["newchild"]["xyz_mm"][2] = 99
    value["result"]["canonical_assembly"]["instances"][0]["part_id"] = "otherpart"
    assert model.target_geometry("newchild") == (vertices, triangles)
    assert model.pick("newchild", [0.5, 0.5, 5], [0, 0, -1])["distance_mm"] == 5


@pytest.mark.parametrize("changed", ["digest", "candidate"])
def test_wrong_seed_or_candidate_rejects(changed):
    value = response()
    digest = contract.source_preview_fingerprint(value)
    candidate = copy.deepcopy(value["result"]["canonical_assembly"])
    if changed == "digest":
        digest = "c" * 64
    else:
        candidate["id"] = "other"
    with pytest.raises(projection.BridgeError):
        projection.PickProjection(value, digest, candidate)


@pytest.mark.parametrize(
    "changed",
    [
        "instance",
        "duplicate_instance",
        "missing_part",
        "extra_part",
        "missing_pose",
        "extra_pose",
        "pose_status",
        "unknown_part",
    ],
)
def test_incomplete_or_rebound_mapping_rejects_even_with_matching_digest(changed):
    value = response()
    result, pose = value["result"], value["report"]["base_pose"]
    if changed == "instance":
        result["instances"][0]["id"] = "other"
    if changed == "duplicate_instance":
        result["instances"].append(copy.deepcopy(result["instances"][0]))
    if changed == "missing_part":
        result["parts"].pop()
    if changed == "extra_part":
        result["parts"].append(dict(part(), id="extra"))
    if changed == "missing_pose":
        pose["transforms"].pop("root")
    if changed == "extra_pose":
        pose["transforms"]["extra"] = IDENTITY
    if changed == "pose_status":
        pose["status"] = "blocked"
    if changed == "unknown_part":
        result["instances"][0]["part_id"] = "unknown"
        result["canonical_assembly"]["instances"][0]["part_id"] = "unknown"
    with pytest.raises(projection.BridgeError):
        build(value)


def test_total_budget_counts_reused_instances_and_never_subsamples():
    value = response()
    value["result"]["instances"][1]["part_id"] = "targetpart"
    value["result"]["canonical_assembly"]["instances"][1]["part_id"] = "targetpart"
    with pytest.raises(projection.BridgeError, match="total mesh budget"):
        build(value, triangle_budget=1)
    assert build(value, triangle_budget=2)


def test_target_only_does_not_relax_semantic_nearest_or_face_ties():
    value = response()
    value["result"]["parts"][0] = dict(part((0, 2)), id="targetpart")
    value["result"]["parts"][0]["topology"][1]["signature"]["surface"] = "cylinder"
    with pytest.raises(projection.BridgeError, match="planar"):
        build(value).pick("newchild", [0.5, 0.5, 5], [0, 0, -1], target_only=True)
    value["result"]["parts"][0] = dict(part((0, 0)), id="targetpart")
    with pytest.raises(projection.BridgeError, match="multiple semantic"):
        build(value).pick("newchild", [0.5, 0.5, 5], [0, 0, -1], target_only=True)


def test_unknown_target_nonboolean_isolation_and_miss():
    model = build(response(-2))
    with pytest.raises(projection.BridgeError):
        model.target_geometry("unknown")
    with pytest.raises(projection.BridgeError):
        model.pick("unknown", [0, 0, 5], [0, 0, -1])
    with pytest.raises(projection.BridgeError):
        model.pick("newchild", [0, 0, 5], [0, 0, -1], target_only="yes")
    assert model.pick("newchild", [9, 9, 5], [0, 0, -1]) is None


def test_each_reused_instance_gets_its_exact_pose_and_immutable_geometry():
    value = response()
    value["result"]["instances"][1]["part_id"] = "targetpart"
    value["result"]["canonical_assembly"]["instances"][1]["part_id"] = "targetpart"
    value["report"]["base_pose"]["transforms"]["root"]["xyz_mm"] = [10, 0, 0]
    model = build(value)
    assert model.target_geometry("newchild")[0][0] == (0, 0, 0)
    assert model.target_geometry("root")[0][0] == (10, 0, 0)
    assert model.pick("newchild", [0.5, 0.5, 5], [0, 0, -1])["instance_id"] == "newchild"
    with pytest.raises(projection.BridgeError, match="different component"):
        model.pick("newchild", [10.5, 0.5, 5], [0, 0, -1])


def test_near_coincident_instances_refuse_without_silent_target_only_fallback():
    model = build(response(-5e-8))
    with pytest.raises(projection.BridgeError, match="overlaps"):
        model.pick("newchild", [0.5, 0.5, 5], [0, 0, -1])
