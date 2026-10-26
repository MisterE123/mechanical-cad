"""Pure drawing/picking contracts; synthetic reports do not establish native solving."""

import copy
import importlib
import math
import subprocess
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_general_view_geometry_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
g = importlib.import_module(PACKAGE + ".general_view_geometry")
bridge = importlib.import_module(PACKAGE + ".sketch_action_bridge")


def sketch():
    return {
        "schema_version": 2,
        "id": "sketch",
        "units": "mm",
        "plane": {"id": "plane", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [{"id": "a", "u": 0, "v": 0}, {"id": "b", "u": 30, "v": 40}],
        "lines": [{"id": "line", "start": "a", "end": "b"}],
        "circles": [{"id": "circle", "center": "a", "radius": 5}],
        "constraints": [
            {"id": "length", "kind": "distance", "refs": ["a", "b"], "value": 50},
            {"id": "radius", "kind": "radius", "refs": ["circle"], "value": "size / 2"},
        ],
    }


def geometry(value=None):
    return g.build_geometry(sketch() if value is None else value, source="authored")


def projection(world):
    return world[:2]


def solve_fixture():
    """Build a valid protocol fixture without importing or running any native code."""
    authored = sketch()
    authored["points"] = authored["points"][:1]
    authored["lines"] = []
    authored["constraints"] = authored["constraints"][1:]
    document = {
        "schema_version": 2,
        "id": "part",
        "name": "Part",
        "units": "mm",
        "parameters": {"size": 12},
        "features": [
            {
                "id": "profile",
                "kind": "sketch_constrained",
                "label": "Circle",
                "params": {},
                "inputs": {},
                "sketch": authored,
            }
        ],
        "active_feature": "profile",
    }
    request = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "document": document,
        "feature_id": "profile",
    }
    canonical = bridge.snapshots._expected_document(document)
    solved = g._normalized_sketch(authored)
    solved["points"][0].update(u=17, v=-9)
    solved["circles"][0]["radius"] = 6
    solved["constraints"][0]["value"] = 6
    response = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "input_fingerprint": bridge.snapshots.input_fingerprint(request),
        "ok": True,
        "error": None,
        "result": {
            "document_id": "part",
            "feature_id": "profile",
            "document_hash": bridge.snapshots.document_hash(canonical),
            "sketch": {
                "solver": "libslvs",
                "solver_version": "3.2",
                "status": "okay",
                "remaining_dof": 2,
                "failed_constraints": [],
                "redundant_constraints": [],
                "max_residual_mm": 0,
                "solved": solved,
                "dimensions": {"radius": 6},
            },
            "profile_check": {"ready": True, "error": None},
        },
    }
    return authored, request, response


def test_authored_geometry_is_exact_detached_analytic_and_stable_id_keyed():
    source = sketch()
    before = copy.deepcopy(source)
    result = geometry(source)
    assert result.source == "authored" and result.request_fingerprint is None
    assert result.sketch_id == "sketch"
    assert result.points == {"a": (0, 0), "b": (30, 40)}
    assert result.lines["line"] == g.LineGeometry("a", "b", (0, 0), (30, 40))
    assert result.circles["circle"] == g.CircleGeometry("a", (0, 0), 5)
    assert result.dimensions["radius"].value == "size / 2"
    assert type(result.dimensions["length"].value) is int
    assert source == before
    with pytest.raises(TypeError):
        result.points["a"] = (9, 9)
    with pytest.raises(FrozenInstanceError):
        result.circles["circle"].radius_mm = 9
    source["points"][0]["u"] = 123
    assert result.points["a"] == (0, 0)


def test_solved_geometry_requires_exact_request_and_preserves_source_values():
    authored, request, response = solve_fixture()
    before = copy.deepcopy((authored, request, response))
    solved = g.build_geometry(
        authored, source="solved", solve_request=request, solve_response=response
    )
    assert solved.points["a"] == (17, -9)
    assert solved.circles["circle"].radius_mm == 6
    assert solved.dimensions["radius"].value == "size / 2"
    assert solved.request_fingerprint == response["input_fingerprint"]
    assert geometry(authored).circles["circle"].radius_mm == 5
    assert (authored, request, response) == before


def test_missing_failed_stale_and_wrong_authoring_evidence_never_falls_back():
    authored, request, response = solve_fixture()
    with pytest.raises(ValueError):
        g.build_geometry(authored, source="solved")
    with pytest.raises(TypeError):
        g.build_geometry(authored)
    for source in (None, True, "cache", "last_good", 1):
        with pytest.raises(ValueError):
            g.build_geometry(authored, source=source)
    with pytest.raises(ValueError, match="does not consume"):
        g.build_geometry(authored, source="authored", solve_response=response)
    changed = copy.deepcopy(authored)
    changed["points"][0]["u"] += 1
    with pytest.raises(ValueError, match="differs"):
        g.build_geometry(changed, source="solved", solve_request=request, solve_response=response)
    stale_request = copy.deepcopy(request)
    stale_request["document"]["parameters"]["size"] = 14
    with pytest.raises(ValueError, match="fingerprint"):
        g.build_geometry(
            authored, source="solved", solve_request=stale_request, solve_response=response
        )
    failed = {
        "protocol_version": 1,
        "result_version": 2,
        "ok": False,
        "result": None,
        "error": {"code": "bad_request", "message": "Unavailable"},
    }
    with pytest.raises(ValueError, match="successful"):
        g.build_geometry(authored, source="solved", solve_request=request, solve_response=failed)
    response["result"]["sketch"]["solved"]["circles"][0]["center"] = "missing"
    with pytest.raises(ValueError):
        g.build_geometry(authored, source="solved", solve_request=request, solve_response=response)


@pytest.mark.parametrize("factor", [1, 1 + 2e-10])
def test_arbitrary_wxyz_plane_round_trip_normal_distance_and_far_origin(factor):
    saved = {
        "id": "plane",
        "origin": [1e6, -1e6, 999999],
        "quaternion": [factor * v / math.sqrt(30) for v in (1, 2, 3, 4)],
    }
    before = copy.deepcopy(saved)
    plane = g.Workplane.from_saved(saved)
    assert plane.u_axis == pytest.approx((-2 / 3, 2 / 3, 1 / 3))
    assert plane.v_axis == pytest.approx((2 / 15, -1 / 3, 14 / 15))
    local = (123.125, -234.75)
    world = plane.local_to_world(local)
    assert plane.world_to_local(world) == pytest.approx((*local, 0), abs=3e-10)
    off_plane = tuple(a + 77 * n for a, n in zip(world, plane.normal, strict=True))
    assert plane.world_to_local(off_plane) == pytest.approx((*local, 77), abs=3e-10)
    assert saved == before
    origin = tuple(a + 1e8 * n for a, n in zip(world, plane.normal, strict=True))
    hit = g.intersect_ray(plane, origin, tuple(-900 * n for n in plane.normal))
    assert hit.local_mm == pytest.approx(local, abs=3e-8)
    assert hit.world_mm == pytest.approx(world, abs=3e-8)
    assert hit.distance_mm == pytest.approx(1e8)


@pytest.mark.parametrize(
    "origin,direction",
    [
        ((0, 0, 2), (1, 0, 0)),
        ((0, 0, 0), (1, 0, 0)),
        ((0, 0, 2), (0, 0, 1)),
        ((0, 0, 2), (1, 0, -1e-13)),
    ],
)
def test_parallel_coplanar_behind_and_near_parallel_rays_miss(origin, direction):
    assert g.intersect_ray(geometry().plane, origin, direction) is None


def test_ray_on_plane_with_a_transverse_direction_has_zero_distance():
    hit = g.intersect_ray(geometry().plane, (3, 4, 0), (0, 0, -2))
    assert hit.local_mm == (3, 4) and hit.distance_mm == 0


@pytest.mark.parametrize("bad", [True, float("inf"), float("nan"), 10**1000])
def test_bad_numbers_reject_in_geometry_plane_ray_and_projection(bad):
    source = sketch()
    source["points"][0]["u"] = bad
    with pytest.raises(ValueError):
        geometry(source)
    with pytest.raises(ValueError):
        g.intersect_ray(geometry().plane, (bad, 0, 1), (0, 0, -1))
    with pytest.raises(ValueError):
        g.pick_geometry(geometry(), (0, 0), lambda world: (bad, 0))
    with pytest.raises(ValueError):
        g.pick_geometry(geometry(), (0, 0), projection, radius_px=bad)


def test_bad_planes_vectors_and_zero_rays_reject():
    for quaternion in ([0, 0, 0, 0], [1.001, 0, 0, 0], [1, 0, 0], [True, 0, 0, 0]):
        saved = sketch()["plane"]
        saved["quaternion"] = quaternion
        with pytest.raises(ValueError):
            g.Workplane.from_saved(saved)
    with pytest.raises(ValueError):
        g.intersect_ray(geometry().plane, (0, 0, 1), (0, 0, 0))
    with pytest.raises(ValueError):
        geometry().plane.world_to_local([0, 1])


def test_circle_extent_is_not_restricted_to_the_seed_coordinate_bound():
    source = sketch()
    source["points"][0].update(u=1e6, v=1e6)
    source["circles"][0]["radius"] = 1e6
    result = geometry(source)
    hit = g.pick_geometry(
        result, (2e6, 1e6), projection, kinds=("circle",), max_circle_segments=8, circle_error_px=4
    )
    assert hit.status == "incomplete"  # Scale needs more sampling; input itself is valid.
    assert result.plane.local_to_world((2e6, 1e6)) == (2e6, 1e6, 0)


def test_line_nearest_clamps_to_endpoints_and_includes_pixel_radius_boundary():
    result = geometry()
    endpoint = g.pick_geometry(result, (33, 44), projection, kinds=("line",), radius_px=5)
    assert endpoint.unique.identifier == "line"
    assert endpoint.unique.nearest_screen == (30, 40)
    assert endpoint.unique.distance_px == pytest.approx(5)
    beyond = g.pick_geometry(result, (33.1, 44.1), projection, kinds=("line",), radius_px=5)
    assert beyond.status == "miss"
    middle = g.pick_geometry(result, (12, 21), projection, kinds=("line",))
    assert middle.unique.nearest_screen == pytest.approx((14.4, 19.2))
    assert middle.unique.distance_px == pytest.approx(3)


def test_endpoint_point_and_line_tie_has_no_automatic_priority_or_binding():
    result = g.pick_geometry(geometry(), (30, 40), projection, kinds=("point", "line"))
    assert result.status == "ambiguous" and result.unique is None
    assert [(hit.kind, hit.identifier) for hit in result.nearest] == [
        ("line", "line"),
        ("point", "b"),
    ]
    assert all(hit.distance_px == 0 for hit in result.nearest)


def test_overlapping_distinct_points_remain_distinct_deterministic_candidates():
    source = sketch()
    source["points"].append({"id": "other", "u": 0, "v": 0})
    result = g.pick_geometry(geometry(source), (0, 0), projection, kinds=("point",))
    assert result.status == "ambiguous"
    assert [hit.identifier for hit in result.nearest] == ["a", "other"]


def test_reordering_records_does_not_change_geometry_ids_or_proposals():
    source = sketch()
    source["circles"].append({"id": "second_circle", "center": "b", "radius": 8})
    before = geometry(source)
    for collection in ("points", "lines", "circles", "constraints"):
        source[collection].reverse()
    after = geometry(source)
    assert before == after
    assert g.pick_geometry(before, (5, 0), projection) == g.pick_geometry(after, (5, 0), projection)


@pytest.mark.parametrize("angle", [0, 1e-8, math.tau - 1e-8])
def test_circle_seam_is_closed_and_has_one_analytic_identity(angle):
    query = (5 * math.cos(angle), 5 * math.sin(angle))
    result = g.pick_geometry(geometry(), query, projection, kinds=("circle",))
    assert result.status == "unique"
    assert len(result.candidates) == 1 and result.unique.identifier == "circle"
    assert result.unique.method == "sampled_circle"
    assert result.unique.distance_px < 1e-7
    assert 0 < result.unique.observed_error_px <= 0.25


def test_circle_sampling_reports_refinement_error_and_near_threshold_ambiguity():
    result = g.pick_geometry(geometry(), (13, 0), projection, kinds=("circle",), radius_px=8)
    assert result.status == "ambiguous" and result.unique is None
    assert result.nearest[0].distance_px == pytest.approx(8)
    assert result.nearest[0].observed_error_px > 0
    coarse = g.pick_geometry(
        geometry(), (5, 0), projection, kinds=("circle",), circle_error_px=0.25
    )
    fine = g.pick_geometry(geometry(), (5, 0), projection, kinds=("circle",), circle_error_px=0.01)
    assert fine.unique.observed_error_px < coarse.unique.observed_error_px
    assert fine.projection_calls > coarse.projection_calls


def test_circle_refinement_budget_cannot_choose_a_nearest_entity():
    result = g.pick_geometry(
        geometry(),
        (5, 0),
        projection,
        kinds=("circle",),
        circle_error_px=0.001,
        max_circle_segments=8,
    )
    assert result.status == "incomplete" and result.unique is None
    assert {issue.reason for issue in result.unavailable} == {"refinement_budget"}
    assert all(
        issue.identifier == "circle" and issue.turns is not None for issue in result.unavailable
    )


def test_tilted_perspective_circle_remains_an_explicit_sampled_proposal():
    source = sketch()
    source["plane"]["quaternion"] = [math.cos(math.pi / 6), math.sin(math.pi / 6), 0, 0]
    selected = geometry(source)

    def perspective(world):
        depth = 10 + world[2]
        return None if depth <= 0 else (100 * world[0] / depth, 100 * world[1] / depth)

    local = (5 * math.cos(0.31), 5 * math.sin(0.31))
    query = perspective(selected.plane.local_to_world(local))
    result = g.pick_geometry(selected, query, perspective, kinds=("circle",), circle_error_px=0.01)
    assert result.unique.identifier == "circle"
    assert result.unique.method == "sampled_circle"
    assert result.unique.distance_px < 0.01
    assert 0 < result.unique.observed_error_px <= 0.01


def test_equal_projected_circles_keep_both_stable_ids():
    source = sketch()
    source["circles"].insert(0, {"id": "another", "center": "a", "radius": 5})
    result = g.pick_geometry(geometry(source), (5, 0), projection, kinds=("circle",))
    assert result.status == "ambiguous" and result.unique is None
    assert [hit.identifier for hit in result.nearest] == ["another", "circle"]


def test_invisible_endpoints_and_circle_spans_never_bridge_a_camera_plane():
    def clipped(world):
        return None if world[0] < 1 else world[:2]

    line = g.pick_geometry(geometry(), (30, 40), clipped, kinds=("line",))
    assert line.status == "incomplete" and line.unique is None and not line.candidates
    assert line.unavailable == (g.ProjectionIssue("line", "line", "invisible_endpoint"),)
    circle = g.pick_geometry(geometry(), (5, 0), clipped, kinds=("circle",))
    assert circle.status == "incomplete" and circle.unique is None
    assert any(issue.reason == "invisible_span" for issue in circle.unavailable)
    points = g.pick_geometry(geometry(), (0, 0), lambda world: None, kinds=("point",))
    assert points.status == "miss" and not points.candidates


def test_global_projection_budget_is_hard_and_reports_incomplete_result():
    calls = []
    result = g.pick_geometry(
        geometry(), (5, 0), lambda world: calls.append(world) or world[:2], max_project_calls=4
    )
    assert len(calls) == result.projection_calls == 4
    assert result.status == "incomplete" and result.unique is None
    assert any(issue.reason == "projection_budget" for issue in result.unavailable)


def test_pixel_radius_does_not_depend_on_millimetres_scene_scale_or_plane_origin():
    source = sketch()
    source["plane"]["origin"] = [900000, -800000, 700000]
    result = geometry(source)

    def zoomed(world):
        u, v, _ = result.plane.world_to_local(world)
        return (u * 100 + 500, v * 100 + 200)

    hit = g.pick_geometry(result, (500 + 7, 200), zoomed, kinds=("point",), radius_px=8)
    miss = g.pick_geometry(result, (500 + 9, 200), zoomed, kinds=("point",), radius_px=8)
    assert hit.unique.identifier == "a" and hit.unique.distance_px == 7
    assert miss.status == "miss"


def test_projected_zero_length_line_is_a_display_point_without_new_identity():
    result = g.pick_geometry(geometry(), (0, 0), lambda world: (0, 0), kinds=("line",))
    assert result.unique.identifier == "line" and result.unique.distance_px == 0


@pytest.mark.parametrize(
    "options",
    [
        {"max_circle_segments": 7},
        {"max_circle_segments": 2049},
        {"max_circle_segments": True},
        {"max_project_calls": 0},
        {"max_project_calls": 65537},
        {"max_project_calls": True},
        {"kinds": ["point", "point"]},
        {"kinds": ["constraint"]},
        {"kinds": "point"},
        {"circle_error_px": 0},
        {"circle_error_px": 5},
        {"tie_tolerance_px": -1},
    ],
)
def test_invalid_pick_caps_and_policy_reject_before_projection(options):
    calls = []
    with pytest.raises(ValueError):
        g.pick_geometry(geometry(), (0, 0), lambda world: calls.append(world), **options)
    assert not calls


@pytest.mark.parametrize("projected", [True, 5, [0], [0, 0, 0], "xy", {"x": 0, "y": 0}])
def test_malformed_projection_output_is_not_treated_as_invisible(projected):
    with pytest.raises(ValueError):
        g.pick_geometry(geometry(), (0, 0), lambda world: projected)


def placement(kind, refs, offset):
    return {"kind": kind, "refs": refs, "display": kind, "offset": offset}


def test_radius_annotation_retains_formula_full_radius_and_exact_id():
    data = placement("radius", ["circle"], [0, 12])
    result = g.annotation_geometry(geometry(), "radius", data)
    assert result.constraint_id == "radius" and result.refs == ("circle",)
    assert result.value == "size / 2" and result.kind == "radius"
    assert result.anchors_mm == ((0, 0), (0, 5))
    assert result.label_mm == (0, 12)
    assert result.segments_mm == (((0, 0), (0, 5)), ((0, 5), (0, 12)))
    assert data == placement("radius", ["circle"], [0, 12])
    zero = g.annotation_geometry(geometry(), "radius", placement("radius", ["circle"], [0, 0]))
    assert zero.anchors_mm == ((0, 0), (5, 0))


def test_solved_annotation_uses_solved_radius_and_unrounded_authored_value():
    authored, request, response = solve_fixture()
    selected = g.build_geometry(
        authored, source="solved", solve_request=request, solve_response=response
    )
    annotation = g.annotation_geometry(selected, "radius", placement("radius", ["circle"], [10, 0]))
    assert annotation.anchors_mm == ((17, -9), (23, -9))
    assert annotation.value == "size / 2"
    source = sketch()
    source["constraints"][1]["value"] = 7.123456789012345
    result = g.annotation_geometry(
        geometry(source), "radius", placement("radius", ["circle"], [10, 0])
    )
    assert result.value == source["constraints"][1]["value"]


def test_aligned_distance_annotation_keeps_order_and_exact_integer_value():
    result = g.annotation_geometry(geometry(), "length", placement("distance", ["a", "b"], [-8, 6]))
    assert result.value == 50 and type(result.value) is int
    assert result.refs == ("a", "b") and result.anchors_mm == ((0, 0), (30, 40))
    assert result.label_mm == (7, 26)
    assert result.segments_mm == (((0, 0), (-8, 6)), ((-8, 6), (22, 46)), ((22, 46), (30, 40)))


@pytest.mark.parametrize(
    "identifier,data",
    [
        ("missing", placement("radius", ["circle"], [1, 2])),
        ("radius", placement("radius", ["other_circle"], [1, 2])),
        ("radius", {"kind": "radius", "refs": ["circle"], "display": "unsupported", "offset": [1, 2]}),
        ("length", placement("distance", ["b", "a"], [1, 2])),
        ("radius", placement("radius", ["circle"], [float("nan"), 2])),
        ("radius", placement("radius", ["circle"], [1e6 + 1, 2])),
    ],
)
def test_unavailable_changed_diameter_and_invalid_annotations_fail_closed(identifier, data):
    with pytest.raises(ValueError):
        g.annotation_geometry(geometry(), identifier, data)


def test_malformed_sketch_shapes_and_resource_limits_reject():
    invalid = []
    source = sketch()
    source["points"] = [{"id": f"p{n}", "u": 0, "v": 0} for n in range(257)]
    invalid.append(source)
    source = sketch()
    source["points"].extend({"id": f"p{n}", "u": 0, "v": 0} for n in range(254))
    invalid.append(source)  # 256 points plus a circle exceeds the active-scalar budget.
    source = sketch()
    source["circles"] = [{"id": f"c{n}", "center": "a", "radius": 1} for n in range(256)]
    invalid.append(source)  # Aggregate curves include the existing line.
    source = sketch()
    source["lines"][0]["start"] = "circle"
    invalid.append(source)
    source = sketch()
    source["points"][0]["extra"] = 1
    invalid.append(source)
    source = sketch()
    source["circles"][0]["radius"] = 0
    invalid.append(source)
    for source in invalid:
        with pytest.raises(ValueError):
            geometry(source)


def test_fresh_import_and_basic_geometry_need_no_core_blender_or_native_library():
    script = f"""
import importlib, importlib.abc, sys, types
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'mechanical_cad', 'bpy', 'mathutils', 'slvs', 'OCP'}}:
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Block())
package = types.ModuleType('isolated_view')
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules['isolated_view'] = package
module = importlib.import_module('isolated_view.general_view_geometry')
result = module.build_geometry({sketch()!r}, source='authored')
assert result.circles['circle'].radius_mm == 5
print('NATIVE_FREE_GENERAL_VIEW_OK')
"""
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    assert "NATIVE_FREE_GENERAL_VIEW_OK" in run.stdout


def test_retained_outline_explicitly_drops_all_current_solver_authority():
    authored, request, response = solve_fixture()
    solved = g.build_geometry(
        authored, source="solved", solve_request=request, solve_response=response
    )
    retained = g.retained_outline(solved)
    assert retained.source == "retained" and retained.request_fingerprint is None
    assert retained.circles == solved.circles and retained.points == solved.points
    assert retained.dimensions == solved.dimensions
    assert retained.circles["circle"].radius_mm == 6
    assert authored["circles"][0]["radius"] == 5
    assert solved.source == "solved" and solved.request_fingerprint is not None
    with pytest.raises(TypeError):
        retained.points["a"] = (0, 0)
    for invalid in (None, {}, geometry(), retained):
        with pytest.raises(ValueError):
            g.retained_outline(invalid)
    with pytest.raises(ValueError):
        g.build_geometry(authored, source="retained")


def arc_sketch(*, start_degrees=0, sweep_degrees=90, radius=50, end_radius=None):
    """Raw authored seeds only; no synthetic solved result or native invocation."""
    start = math.radians(start_degrees)
    end = start + math.radians(sweep_degrees)
    end_radius = radius if end_radius is None else end_radius
    return {
        "schema_version": 3,
        "id": "sketch",
        "units": "mm",
        "plane": {"id": "plane", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [
            {"id": "center", "u": 0, "v": 0},
            {"id": "start", "u": radius * math.cos(start), "v": radius * math.sin(start)},
            {"id": "end", "u": end_radius * math.cos(end), "v": end_radius * math.sin(end)},
        ],
        "lines": [],
        "circles": [],
        "arcs": [
            {
                "id": "arc",
                "center": "center",
                "start": "start",
                "end": "end",
                "direction": "ccw" if sweep_degrees > 0 else "cw",
            }
        ],
        "constraints": [{"id": "radius", "kind": "radius", "refs": ["arc"], "value": "size / 2"}],
    }


@pytest.mark.parametrize("sweep", [-270, -180, -90, 90, 180, 270])
@pytest.mark.parametrize("start", [0, 10, 170, 350])
def test_arc_sampler_and_picking_cover_only_directed_finite_interval(start, sweep):
    source = arc_sketch(start_degrees=start, sweep_degrees=sweep)
    before = copy.deepcopy(source)
    selected = geometry(source)
    arc = selected.arcs["arc"]
    assert arc.sweep_radians == pytest.approx(math.radians(sweep))
    sampler = g._Projection(selected.plane, projection, g.MAX_PROJECT_CALLS)
    segments, error, issues = g._curve_segments(arc, sampler, 0.01, 512)
    assert not issues and 0 < error <= 0.01 and 8 <= len(segments) <= 512
    assert segments[0][0] == arc.start_mm
    assert segments[-1][-1] == pytest.approx(arc.end_mm)
    assert segments[0][0] != segments[-1][-1]
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        query = g._arc_point(arc, fraction)
        picked = g.pick_geometry(
            selected, query, projection, kinds=("arc",), radius_px=0.5, circle_error_px=0.01
        )
        assert picked.status == "unique" and picked.unique.identifier == "arc"
        assert picked.unique.method == "sampled_arc"
        assert picked.unique.distance_px < 0.01
    complement_angle = math.radians(start + sweep + math.copysign((360 - abs(sweep)) / 2, sweep))
    complement = (50 * math.cos(complement_angle), 50 * math.sin(complement_angle))
    miss = g.pick_geometry(
        selected, complement, projection, kinds=("arc",), radius_px=0.5, circle_error_px=0.01
    )
    assert miss.status == "miss" and not miss.candidates and not miss.unavailable
    assert source == before


@pytest.mark.parametrize("endpoint", ["start", "end"])
@pytest.mark.parametrize("sweep", [-270, -180, -90, 90, 180, 270])
def test_arc_endpoint_ties_keep_point_and_curve_without_priority(endpoint, sweep):
    selected = geometry(arc_sketch(sweep_degrees=sweep))
    picked = g.pick_geometry(
        selected, selected.points[endpoint], projection, kinds=("point", "arc"), radius_px=0.5
    )
    assert picked.status == "ambiguous" and picked.unique is None
    assert {(hit.kind, hit.identifier) for hit in picked.nearest} == {
        ("point", endpoint),
        ("arc", "arc"),
    }


def test_circle_and_arc_share_one_projection_budget_and_arc_refinement_is_bounded():
    source = arc_sketch()
    source["circles"] = [{"id": "circle", "center": "center", "radius": 5}]
    calls = []
    selected = geometry(source)
    picked = g.pick_geometry(
        selected,
        (50, 0),
        lambda world: calls.append(world) or world[:2],
        kinds=("circle", "arc"),
        max_project_calls=40,
    )
    assert len(calls) == picked.projection_calls == 40
    assert picked.status == "incomplete" and picked.unique is None
    assert any(
        issue.kind == "arc" and issue.reason == "projection_budget" for issue in picked.unavailable
    )
    refined = g.pick_geometry(
        selected,
        (50, 0),
        projection,
        kinds=("arc",),
        max_circle_segments=8,
        circle_error_px=1e-6,
    )
    assert refined.status == "incomplete" and refined.unique is None
    assert {issue.reason for issue in refined.unavailable} == {"refinement_budget"}
    assert all(
        issue.turns is not None and 0 <= issue.turns[0] < issue.turns[1] <= 1
        for issue in refined.unavailable
    )


def test_invisible_arc_spans_are_omitted_without_connecting_across_them():
    selected = geometry(arc_sketch(sweep_degrees=180))
    picked = g.pick_geometry(
        selected, (50, 0), lambda world: None if world[0] < 1 else world[:2], kinds=("arc",)
    )
    assert picked.status == "incomplete" and picked.unique is None
    assert any(issue.reason == "invisible_span" for issue in picked.unavailable)


@pytest.mark.parametrize("sweep", [-270, -180, -90, 90, 180, 270])
def test_zero_offset_arc_radius_leader_uses_swept_midpoint_and_keeps_saved_layout(sweep):
    selected = geometry(arc_sketch(start_degrees=350, sweep_degrees=sweep, end_radius=70))
    saved = placement("radius", ["arc"], [0, 0])
    before = copy.deepcopy(saved)
    annotation = g.annotation_geometry(selected, "radius", saved)
    assert annotation.anchors_mm[1] == g._arc_point(selected.arcs["arc"], 0.5)
    assert math.dist(*annotation.anchors_mm) == pytest.approx(50)
    assert annotation.label_mm == (0, 0)
    assert annotation.value == "size / 2" and saved == before


def test_arc_radius_leader_finite_clamping_and_exact_endpoint_tie_stay_unchanged():
    source = arc_sketch(radius=5)
    source["points"][2].update(u=0, v=5)
    selected = geometry(source)
    outside = g.annotation_geometry(selected, "radius", placement("radius", ["arc"], [-10, 0]))
    assert outside.anchors_mm[1] == pytest.approx((0, 5))
    inside = g.annotation_geometry(selected, "radius", placement("radius", ["arc"], [10, 10]))
    assert inside.anchors_mm[1] == pytest.approx((5 / math.sqrt(2), 5 / math.sqrt(2)))
    # Symmetric endpoints around -U make their distances exactly equal in binary64.
    source["points"][1].update(u=3, v=-4)
    source["points"][2].update(u=3, v=4)
    selected = geometry(source)
    tie = g.annotation_geometry(selected, "radius", placement("radius", ["arc"], [-10, 0]))
    assert tie.anchors_mm[1] == selected.arcs["arc"].start_mm
    source["arcs"][0]["direction"] = "cw"
    reverse = g.annotation_geometry(
        geometry(source), "radius", placement("radius", ["arc"], [-10, 0])
    )
    assert reverse.label_mm == tie.label_mm == (-10, 0)
    assert reverse.anchors_mm[1] == pytest.approx((-5, 0))


def test_unequal_raw_end_is_not_moved_or_picked_as_support_circle_endpoint():
    source = arc_sketch(radius=50, end_radius=70)
    selected = geometry(source)
    assert selected.arcs["arc"].end_mm == selected.points["end"]
    assert math.dist(selected.arcs["arc"].center_mm, selected.arcs["arc"].end_mm) == 70
    raw = g.pick_geometry(selected, selected.points["end"], projection, kinds=("arc",), radius_px=1)
    assert raw.status == "miss"
    support = g.pick_geometry(
        selected, g._arc_point(selected.arcs["arc"], 1), projection, kinds=("arc",), radius_px=1
    )
    assert support.unique.identifier == "arc"


def test_default_pick_kinds_include_arc_and_near_threshold_remains_ambiguous():
    selected = geometry(arc_sketch())
    midpoint = g._arc_point(selected.arcs["arc"], 0.5)
    assert g.pick_geometry(selected, midpoint, projection).unique.kind == "arc"
    edge = g.pick_geometry(selected, (58, 0), projection, kinds=("arc",), radius_px=8)
    assert edge.status == "ambiguous" and edge.unique is None
    assert edge.nearest[0].distance_px == 8 and edge.nearest[0].observed_error_px > 0


def test_identical_finite_arcs_keep_both_stable_ids_in_a_near_tie():
    source = arc_sketch()
    source["arcs"].append({**source["arcs"][0], "id": "another"})
    selected = geometry(source)
    picked = g.pick_geometry(
        selected, g._arc_point(selected.arcs["arc"], 0.5), projection, kinds=("arc",)
    )
    assert picked.status == "ambiguous" and picked.unique is None
    assert [hit.identifier for hit in picked.nearest] == ["another", "arc"]
