"""Transient CPU ray picks never skip foreground blockers or infer face identity."""

import copy
import importlib
import math

import pytest
from test_assembly_edit import PACKAGE

pick = importlib.import_module(PACKAGE + ".assembly_insert_face_pick")
IDENTITY = {"xyz_mm": [0, 0, 0], "wxyz": [1, 0, 0, 0]}


def part(depths=(0,), ids=None):
    ids = list(ids or (f"face{i}" for i in range(len(depths))))
    vertices = [[x, y, z] for z in depths for x, y in ((0, 0), (2, 0), (0, 2))]
    return {
        "mesh": {
            "vertices": vertices,
            "triangles": [[3 * i, 3 * i + 1, 3 * i + 2] for i in range(len(depths))],
            "triangle_face_ids": ids,
        },
        "topology": [
            {
                "id": name,
                "kind": "face",
                "provenance": {"semantic_status": "stable"},
                "signature": {"surface": "plane"},
            }
            for name in dict.fromkeys(ids)
        ],
    }


def test_nearest_hit_is_semantic_world_mm_and_does_not_mutate():
    value = part((0, 2))
    before = copy.deepcopy(value)
    result = pick.pick_face(value, IDENTITY, [0.5, 0.5, 5], [0, 0, -7])
    assert result == {"face_id": "face1", "point_mm": (0.5, 0.5, 2.0), "distance_mm": 3.0}
    assert value == before
    assert set(result) == {"face_id", "point_mm", "distance_mm"}


def test_rigid_pose_rotation_translation_and_backface():
    pose = {"xyz_mm": [10, 20, 30], "wxyz": [math.sqrt(0.5), math.sqrt(0.5), 0, 0]}
    hit = pick.pick_face(part(), pose, [10.5, 15, 30.5], [0, 1, 0])
    assert hit["face_id"] == "face0"
    assert hit["distance_mm"] == pytest.approx(5)
    assert hit["point_mm"] == pytest.approx((10.5, 20, 30.5))
    reverse = pick.pick_face(part(), IDENTITY, [0.5, 0.5, -5], [0, 0, 1])
    assert reverse["distance_mm"] == 5


@pytest.mark.parametrize(
    "origin,direction",
    [([4, 4, 5], [0, 0, -1]), ([0.5, 0.5, 5], [0, 0, 1]), ([0.5, 0.5, 5], [1, 0, 0])],
)
def test_miss_behind_or_parallel_returns_none(origin, direction):
    assert pick.pick_face(part(), IDENTITY, origin, direction) is None


@pytest.mark.parametrize(
    "origin,direction",
    [
        ([0, 0, math.nan], [0, 0, 1]),
        ([0, 0, 0], [0, math.inf, 1]),
        ([0, 0], [0, 0, 1]),
        ([False, 0, 0], [0, 0, 1]),
        ([0, 0, 0], [0, 0, 0]),
        ([0, 0, 0], ["1", 0, 1]),
    ],
)
def test_invalid_ray_refuses(origin, direction):
    with pytest.raises(pick.BridgeError):
        pick.pick_face(part(), IDENTITY, origin, direction)


@pytest.mark.parametrize("triangle", [[0, 1, 6], [-1, 0, 1], [0, True, 2], [0, 1], [0, 0, 1]])
def test_invalid_or_degenerate_triangle_refuses_even_off_ray(triangle):
    value = part((0, 10))
    value["mesh"]["triangles"][1] = triangle
    with pytest.raises(pick.BridgeError):
        pick.pick_face(value, IDENTITY, [40, 40, 5], [0, 0, -1])


@pytest.mark.parametrize("blocker", ["curved", "unstable", "missing", "duplicate"])
def test_nearest_invalid_face_blocks_valid_plane_behind(blocker):
    value = part((0, 2))
    front = value["topology"][1]
    if blocker == "curved":
        front["signature"]["surface"] = "cylinder"
    elif blocker == "unstable":
        front["provenance"]["semantic_status"] = "split"
    elif blocker == "missing":
        value["mesh"]["triangle_face_ids"][1] = None
    else:
        value["topology"].append(copy.deepcopy(front))
    with pytest.raises(pick.BridgeError):
        pick.pick_face(value, IDENTITY, [0.5, 0.5, 5], [0, 0, -1])


def test_tied_distinct_semantic_faces_refuse_but_same_face_seam_is_allowed():
    with pytest.raises(pick.BridgeError, match="multiple semantic faces"):
        pick.pick_face(part((0, 0)), IDENTITY, [0.5, 0.5, 5], [0, 0, -1])
    value = part((0, 0), ["same", "same"])
    value["mesh"]["vertices"][3:] = [[2, 2, 0], [0, 2, 0], [2, 0, 0]]
    hit = pick.pick_face(value, IDENTITY, [1, 1, 5], [0, 0, -1])
    assert hit["face_id"] == "same"


def test_near_tie_fails_closed_independent_of_triangle_order():
    for depths in ((0, 5e-8), (5e-8, 0)):
        with pytest.raises(pick.BridgeError, match="multiple semantic faces"):
            pick.pick_face(part(depths), IDENTITY, [0.5, 0.5, 5], [0, 0, -1])


@pytest.mark.parametrize("budget", [0, True, 200001, 1.5])
def test_invalid_budget_refuses(budget):
    with pytest.raises(pick.BridgeError, match="budget"):
        pick.pick_face(part(), IDENTITY, [0.5, 0.5, 5], [0, 0, -1], max_triangles=budget)


def test_over_budget_refuses_without_decimation_and_exact_limit_passes():
    with pytest.raises(pick.BridgeError, match="budget"):
        pick.pick_face(part((0, 2)), IDENTITY, [0.5, 0.5, 5], [0, 0, -1], max_triangles=1)
    assert (
        pick.pick_face(part((0, 2)), IDENTITY, [0.5, 0.5, 5], [0, 0, -1], max_triangles=2)[
            "face_id"
        ]
        == "face1"
    )


def test_invalid_mapping_pose_and_vertex_refuse():
    value = part()
    value["mesh"]["triangle_face_ids"] = []
    with pytest.raises(pick.BridgeError):
        pick.pick_face(value, IDENTITY, [0.5, 0.5, 5], [0, 0, -1])
    with pytest.raises(pick.BridgeError):
        pick.pick_face(
            part(), {"xyz_mm": [0, 0, 0], "wxyz": [2, 0, 0, 0]}, [0.5, 0.5, 5], [0, 0, -1]
        )
    value = part()
    value["mesh"]["vertices"][0][0] = math.nan
    with pytest.raises(pick.BridgeError):
        pick.pick_face(value, IDENTITY, [0.5, 0.5, 5], [0, 0, -1])


def test_invalid_face_behind_nearest_valid_face_does_not_block():
    value = part((0, 2))
    value["topology"][0]["signature"]["surface"] = "cylinder"
    assert pick.pick_face(value, IDENTITY, [0.5, 0.5, 5], [0, 0, -1])["face_id"] == "face1"


def test_vertex_budget_is_checked_before_transform(monkeypatch):
    monkeypatch.setattr(pick, "MAX_VERTICES", 2)
    with pytest.raises(pick.BridgeError, match="vertex budget"):
        pick.pick_face(part(), IDENTITY, [0.5, 0.5, 5], [0, 0, -1])


def test_origin_on_surface_is_a_zero_distance_hit():
    assert pick.pick_face(part(), IDENTITY, [0.5, 0.5, 0], [0, 0, 1])["distance_mm"] == 0


@pytest.mark.parametrize("surface", ["curved", "unstable", "missing"])
def test_surface_probe_keeps_unqualified_foreground_geometry(surface):
    value = part((2,))
    if surface == "curved":
        value["topology"][0]["signature"]["surface"] = "cylinder"
    elif surface == "unstable":
        value["topology"][0]["provenance"]["semantic_status"] = "split"
    else:
        value["mesh"]["triangle_face_ids"][0] = None
    hit = pick.pick_surface(value, IDENTITY, [0.5, 0.5, 5], [0, 0, -1])
    assert hit.distance_mm == 3 and hit.point_mm == (0.5, 0.5, 2)
    with pytest.raises(pick.BridgeError):
        pick.resolve_surface_face(value, hit)


@pytest.mark.parametrize("occluder_depth", [-2, 2])
@pytest.mark.parametrize("surface", ["curved", "unstable"])
def test_caller_can_compare_all_instances_before_qualifying_target(
    occluder_depth, surface, monkeypatch
):
    target, other = part(), part((occluder_depth,))
    if surface == "curved":
        other["topology"][0]["signature"]["surface"] = "cylinder"
    else:
        other["topology"][0]["provenance"]["semantic_status"] = "split"
    ray = ([0.5, 0.5, 5], [0, 0, -1])
    # Neither probe may ask semantic questions, even for an unrelated curve.
    real_resolve = pick.resolve_face
    monkeypatch.setattr(
        pick, "resolve_face", lambda *a: pytest.fail("premature semantic resolution")
    )
    target_hit = pick.pick_surface(target, IDENTITY, *ray)
    other_hit = pick.pick_surface(other, IDENTITY, *ray)
    monkeypatch.setattr(pick, "resolve_face", real_resolve)
    blocked = other_hit.distance_mm <= target_hit.distance_mm + pick.distance_tolerance(
        target_hit.distance_mm
    )
    assert blocked is (occluder_depth > 0)
    if not blocked:
        assert pick.resolve_surface_face(target, target_hit) == "face0"


def test_surface_ties_defer_semantic_ambiguity_until_target_resolution():
    value = part((0, 0))
    hit = pick.pick_surface(value, IDENTITY, [0.5, 0.5, 5], [0, 0, -1])
    assert hit.distance_mm == 5
    with pytest.raises(pick.BridgeError, match="multiple semantic faces"):
        pick.resolve_surface_face(value, hit)


def test_transient_surface_record_cannot_accidentally_resolve_against_another_part():
    from dataclasses import FrozenInstanceError

    value = part()
    hit = pick.pick_surface(value, IDENTITY, [0.5, 0.5, 5], [0, 0, -1])
    with pytest.raises(pick.BridgeError, match="different transient part"):
        pick.resolve_surface_face(copy.deepcopy(value), hit)
    with pytest.raises(FrozenInstanceError):
        hit.distance_mm = 1
    assert "triangle" not in repr(hit) and "mesh" not in repr(hit)


@pytest.mark.parametrize("distance", [-1, math.nan, math.inf, True, "1"])
def test_invalid_surface_distance_comparison_refuses(distance):
    with pytest.raises(pick.BridgeError):
        pick.distance_tolerance(distance)
