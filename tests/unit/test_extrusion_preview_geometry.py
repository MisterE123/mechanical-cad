"""Preview outlines suppress tessellation diagonals without inventing identity."""

import copy
import importlib.util
import math
from pathlib import Path

import pytest

PATH = (
    Path(__file__).resolve().parents[2]
    / "blender_addon/mechanical_cad_blender/extrusion_preview_geometry.py"
)
spec = importlib.util.spec_from_file_location("preview_geometry", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_same_face_diagonal_is_not_an_outline():
    mesh = {"triangles": [[0, 1, 2], [0, 2, 3]], "triangle_face_ids": ["plane", "plane"]}
    assert set(module.boundary_edges(mesh)) == {(0, 1), (1, 2), (2, 3), (0, 3)}


def test_face_boundary_stays_visible_on_shared_vertices():
    mesh = {"triangles": [[0, 1, 2], [0, 2, 3]], "triangle_face_ids": ["one", "two"]}
    assert (0, 2) in module.boundary_edges(mesh)


def test_unknown_face_identity_does_not_suppress_edges():
    mesh = {"triangles": [[0, 1, 2], [0, 2, 3]], "triangle_face_ids": [None, None]}
    assert (0, 2) in module.boundary_edges(mesh)



def test_preview_bounds_are_detached_and_include_all_vertices():
    vertices = [[-2, 8, 1], [4, -3, 9], [0, 0, 0]]
    before = copy.deepcopy(vertices)
    assert module.preview_bounds(vertices) == ((-2.0, -3.0, 0.0), (4.0, 8.0, 9.0))
    assert vertices == before


@pytest.mark.parametrize("vertices", [
    [], None, [[0, 0]], [[0, 0, 0, 1]], [[0, 0, "1"]], [[0, False, 0]],
    [[0, 0, math.nan]], [[0, 0, math.inf]], [[0, 0, -math.inf]],
    [[0, 0, 1e13]], [[0, 0, 0]], [[0, 0, 0], [1e-10, 0, 0]],
    [[-1e12, 0, 0], [1e12, 0, 0]],
])
def test_invalid_preview_bounds_refuse(vertices):
    with pytest.raises(ValueError):
        module.preview_bounds(vertices)


@pytest.mark.parametrize("mode", ["PERSP", "ORTHO"])
@pytest.mark.parametrize("aspect", [0.25, 1, 4])
def test_focus_preserves_center_and_encloses_bounds_with_margin(mode, aspect):
    bounds = ((-2, -4, -6), (6, 8, 10))
    before = copy.deepcopy(bounds)
    center, distance = module.focus_parameters(bounds, 50, aspect, mode)
    assert center == (2, 2, 2) and bounds == before
    radius = math.dist(*bounds) / 2
    tangent = 16 * min(1, aspect, 1 / aspect) / 50
    available_radius = distance * (math.sin(math.atan(tangent)) if mode == "PERSP" else tangent)
    assert available_radius == pytest.approx(1.25 * radius)
    assert distance > radius


def test_planar_and_linear_previews_can_be_focused():
    for vertices in ([[0, 0, 0], [10, 10, 0]], [[0, 0, 0], [0, 0, 10]]):
        bounds = module.preview_bounds(vertices)
        assert module.focus_parameters(bounds, 50, 1, "PERSP")[1] > 0


def test_focus_scales_with_geometry_and_uses_more_distance_for_telephoto():
    small = ((0, 0, 0), (2, 2, 2))
    large = ((0, 0, 0), (4, 4, 4))
    for mode in ("PERSP", "ORTHO"):
        distance = module.focus_parameters(small, 50, 1, mode)[1]
        assert module.focus_parameters(large, 50, 1, mode)[1] == pytest.approx(distance * 2)
        assert module.focus_parameters(small, 100, 1, mode)[1] > distance
        assert module.focus_parameters(small, 50, 0.5, mode)[1] > distance
        assert module.focus_parameters(small, 50, 2, mode)[1] > distance


@pytest.mark.parametrize(("bounds", "lens", "aspect", "mode"), [
    (((0, 0, 0), (1, 1, 1)), 50, 1, "CAMERA"),
    (((0, 0, 0), (1, 1, 1)), 50, 1, []),
    (((0, 0, 0), (1, 1, 1)), 0, 1, "PERSP"),
    (((0, 0, 0), (1, 1, 1)), 251, 1, "PERSP"),
    (((0, 0, 0), (1, 1, 1)), math.nan, 1, "PERSP"),
    (((0, 0, 0), (1, 1, 1)), 50, math.inf, "PERSP"),
    (((0, 0, 0), (1, 1, 1)), 50, 0.01, "PERSP"),
    (((0, 0, 0), (1, 1, 1)), 50, 21, "PERSP"),
    (((0, 0, 0), (1, 1, 1)), True, 1, "PERSP"),
    (((1, 0, 0), (0, 1, 1)), 50, 1, "PERSP"),
    (((0, 0, 0), (0, 0, 0)), 50, 1, "PERSP"),
    (((0, 0, 0), (1e12, 0, 0)), 250, 0.05, "PERSP"),
    (None, 50, 1, "PERSP"),
])
def test_invalid_focus_request_refuses_without_mutation(bounds, lens, aspect, mode):
    before = copy.deepcopy(bounds)
    with pytest.raises(ValueError):
        module.focus_parameters(bounds, lens, aspect, mode)
    assert bounds == before
