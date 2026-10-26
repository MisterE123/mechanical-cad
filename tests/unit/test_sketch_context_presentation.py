"""Context presentation removes tessellation clutter, not reference geometry."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "context_presentation",
    Path(__file__).resolve().parents[2]
    / "blender_addon/mechanical_cad_blender/sketch_view_presentation.py",
)
presentation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(presentation)


def space(shading="WIREFRAME", wire=True, visible=False):
    return SimpleNamespace(
        type="VIEW_3D",
        show_object_viewport_mesh=visible,
        shading=SimpleNamespace(
            type=shading,
            show_cavity=False,
            cavity_type="SCREEN",
            curvature_ridge_factor=0.5,
            curvature_valley_factor=0.75,
            cavity_ridge_factor=1.25,
            cavity_valley_factor=1.5,
        ),
        overlay=SimpleNamespace(show_wireframes=wire),
    )


@pytest.mark.parametrize("shading", ["WIREFRAME", "SOLID", "MATERIAL", "RENDERED"])
@pytest.mark.parametrize("wire", [False, True])
@pytest.mark.parametrize("visible", [False, True])
def test_context_and_exact_restore(shading, wire, visible):
    view = space(shading, wire, visible)
    original_shading = vars(view.shading).copy()
    lease = presentation.SketchContextLease(view)
    assert view.shading.show_cavity and view.shading.cavity_type == "BOTH"
    assert view.shading.curvature_valley_factor == 2
    assert view.shading.cavity_valley_factor == 3
    assert view.show_object_viewport_mesh
    assert view.shading.type == ("SOLID" if shading == "WIREFRAME" else shading)
    assert not view.overlay.show_wireframes
    assert lease.restore() == ""
    assert (view.shading.type, view.overlay.show_wireframes, view.show_object_viewport_mesh) == (
        shading,
        wire,
        visible,
    )
    assert vars(view.shading) == original_shading
    assert lease._space is None and lease._original is None and not lease._presentation
    view.shading.type = "MATERIAL"
    assert lease.restore() == ""
    assert view.shading.type == "MATERIAL"


def test_external_changes_win_independently():
    view = space()
    lease = presentation.SketchContextLease(view)
    view.shading.type = "MATERIAL"
    view.shading.cavity_valley_factor = 4
    view.shading.show_cavity = False
    view.overlay.show_wireframes = True
    view.show_object_viewport_mesh = False
    assert lease.restore() == ""
    assert view.shading.type == "MATERIAL"
    assert view.overlay.show_wireframes
    assert view.shading.cavity_valley_factor == 4
    assert not view.shading.show_cavity
    assert not view.show_object_viewport_mesh


class FailingOverlay:
    def __init__(self):
        self.value = True
        self.fail = True

    @property
    def show_wireframes(self):
        return self.value

    @show_wireframes.setter
    def show_wireframes(self, value):
        self.value = value
        if self.fail:
            self.fail = False
            raise RuntimeError("partial native write")


def test_partial_acquisition_restores_all_values():
    view = space()
    view.overlay = FailingOverlay()
    with pytest.raises(RuntimeError, match="partial native write") as error:
        presentation.SketchContextLease(view)
    assert error.value.__context__ is None
    assert view.shading.type == "WIREFRAME"
    assert view.overlay.show_wireframes
    assert not view.show_object_viewport_mesh


def test_failed_cleanup_still_restores_mesh_visibility_and_shading():
    view = space()
    overlay = FailingOverlay()
    overlay.fail = False
    view.overlay = overlay
    lease = presentation.SketchContextLease(view)
    overlay.fail = True
    assert "Could not restore sketch show_wireframes" in lease.restore()
    assert view.shading.type == "WIREFRAME"
    assert not view.show_object_viewport_mesh
    assert lease.restore() == ""
