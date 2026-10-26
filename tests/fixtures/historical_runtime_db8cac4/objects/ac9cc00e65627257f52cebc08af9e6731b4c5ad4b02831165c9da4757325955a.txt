"""Focus clipping and workspace isolation without requiring a bpy installation.

The actual workspace ownership predicate and display functions run against a
small native-API double. Native viewport rendering remains a separate GUI gate.
"""

import importlib.util
import math
import sys
from contextlib import nullcontext
from itertools import product
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ADDON = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"


@pytest.fixture
def display(monkeypatch):
    package_name = "mcad_view_clipping_test"
    package = ModuleType(package_name)
    package.__path__ = [str(ADDON)]
    monkeypatch.setitem(sys.modules, package_name, package)
    bpy = ModuleType("bpy")
    bpy.app = SimpleNamespace(background=False)
    handlers = ModuleType("bpy.app.handlers")
    handlers.persistent = lambda function: function
    mathutils = ModuleType("mathutils")
    mathutils.Quaternion = mathutils.Vector = tuple
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.setitem(sys.modules, "bpy.app.handlers", handlers)
    monkeypatch.setitem(sys.modules, "mathutils", mathutils)
    for name in ("common", "bridge", "workspace", "display"):
        spec = importlib.util.spec_from_file_location(
            package_name + "." + name, ADDON / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        setattr(package, name, module)
        spec.loader.exec_module(module)
    return package.display


class DisplayObject:
    def __init__(self, dimensions_mm=(12, 8, 4), *, scene_scale=1, origin=(0, 0, 0)):
        half_sizes = [value * 0.001 / scene_scale / 2 for value in dimensions_mm]
        self.bound_box = list(product(*[(-half, half) for half in half_sizes]))
        self.matrix_world = [
            [1, 0, 0, origin[0]],
            [0, 1, 0, origin[1]],
            [0, 0, 1, origin[2]],
            [0, 0, 0, 1],
        ]
        self.selected = False
        self.local = None

    def select_set(self, value):
        self.selected = value

    def local_view_set(self, space, value):
        self.local = value


class LayerObjects(list):
    active = None


def context_for(display, objects, *, role="PART", local_view=False, clip_start=0.01):
    space = SimpleNamespace(
        clip_start=clip_start,
        clip_end=1000,
        local_view=local_view,
        bl_rna=SimpleNamespace(properties={"clip_start": SimpleNamespace(hard_min=1e-6)}),
    )
    area = SimpleNamespace(
        type="VIEW_3D",
        spaces=SimpleNamespace(active=space),
        regions=[SimpleNamespace(type="WINDOW")],
    )
    tags = {
        display.workspace.OWNER_KEY: display.workspace.OWNER,
        display.workspace.ROLE_KEY: role,
    }
    context = SimpleNamespace(
        workspace=tags,
        screen=SimpleNamespace(areas=[area]),
        area=area,
        scene=SimpleNamespace(unit_settings=SimpleNamespace(scale_length=1)),
        selected_objects=[],
        view_layer=SimpleNamespace(objects=LayerObjects(objects)),
        temp_override=lambda **kwargs: nullcontext(),
    )
    calls = []
    context.view_layer.update = lambda: calls.append(("update", {}, space.clip_start))

    def operator(name, **kwargs):
        calls.append((name, kwargs, space.clip_start))
        if name == "localview":
            space.local_view = not space.local_view

    display.bpy.ops = SimpleNamespace(
        view3d=SimpleNamespace(
            localview=lambda **kwargs: operator("localview", **kwargs),
            view_selected=lambda **kwargs: operator("view_selected", **kwargs),
            view_all=lambda **kwargs: operator("view_all", **kwargs),
        )
    )
    return context, space, calls


@pytest.mark.parametrize("role", ["SKETCH", "PART", "ASSEMBLY"])
@pytest.mark.parametrize("local_view", [False, True])
def test_millimetre_part_lowers_clip_before_native_framing(display, role, local_view):
    obj = DisplayObject()
    unrelated = DisplayObject((1000, 1000, 1000))
    context, space, calls = context_for(display, [obj, unrelated], role=role, local_view=local_view)
    assert display._focus_objects(context, [obj])
    expected = math.hypot(0.012, 0.008, 0.004) / 1000
    assert space.clip_start == pytest.approx(expected)
    assert space.clip_end == 1000
    assert calls[0][0] == "update"
    assert calls[-1][0] == ("view_selected" if local_view else "localview")
    assert calls[-1][2] == pytest.approx(expected)
    assert obj.selected and context.view_layer.objects.active is obj
    assert not unrelated.selected
    if local_view:
        assert obj.local and not unrelated.local


@pytest.mark.parametrize("scene_scale", [0.001, 0.01, 1, 10, 1000])
@pytest.mark.parametrize("size_mm", [0.001, 0.012, 12, 1000, 1e6])
def test_tiny_normal_and_large_geometry_respects_display_units_and_rna_floor(
    display, scene_scale, size_mm
):
    obj = DisplayObject((size_mm, size_mm / 2, size_mm / 3), scene_scale=scene_scale)
    context, space, _ = context_for(display, [obj])
    context.scene.unit_settings.scale_length = scene_scale
    assert display._focus_objects(context, [obj])
    extent = math.hypot(size_mm, size_mm / 2, size_mm / 3) * 0.001 / scene_scale
    assert space.clip_start == pytest.approx(min(0.01, max(1e-6, extent / 1000)))
    assert context.scene.unit_settings.scale_length == scene_scale


@pytest.mark.parametrize("origin", [(1000, -1000, 500), (1e12, -1e12, 1e12)])
def test_far_origin_does_not_erase_local_extent_or_enlarge_near_plane(display, origin):
    obj = DisplayObject(origin=origin)
    context, space, _ = context_for(display, [obj])
    assert display._focus_objects(context, [obj])
    assert space.clip_start == pytest.approx(math.hypot(0.012, 0.008, 0.004) / 1000)


def test_bounds_include_instance_transform_and_separation(display):
    first = DisplayObject(origin=(1000, 1000, 1000))
    second = DisplayObject(origin=(1000.1, 1000, 1000))
    # A scaled, 90-degree-rotated instance: world half-extents 8, 6, 2 mm.
    second.matrix_world[0][:3] = [0, -2, 0]
    second.matrix_world[1][:3] = [1, 0, 0]
    context, space, _ = context_for(display, [first, second])
    assert display._focus_objects(context, [first, second])
    assert space.clip_start == pytest.approx(math.hypot(0.114, 0.012, 0.004) / 1000)


def test_finer_existing_near_plane_is_preserved(display):
    obj = DisplayObject()
    context, space, _ = context_for(display, [obj], clip_start=2e-6)
    assert display._focus_objects(context, [obj])
    assert space.clip_start == 2e-6


@pytest.mark.parametrize("role", ["PART", "UNKNOWN", None])
def test_unowned_or_unrecognized_workspace_retains_clipping(display, role):
    obj = DisplayObject()
    context, space, _ = context_for(display, [obj], role=role)
    if role == "PART":
        context.workspace[display.workspace.OWNER_KEY] = "another_addon"
    assert display._focus_objects(context, [obj])
    assert space.clip_start == 0.01


@pytest.mark.parametrize("local_view", [False, True])
def test_whole_scene_keeps_clip_settings_and_native_exit_behavior(display, local_view):
    context, space, calls = context_for(display, [], local_view=local_view, clip_start=0.003)
    assert display._focus_objects(context, [], whole_scene=True)
    assert space.clip_start == 0.003 and space.clip_end == 1000
    assert [call[0] for call in calls] == (
        ["localview", "view_all"] if local_view else ["view_all"]
    )
    assert not space.local_view


def test_other_viewports_are_unchanged(display):
    obj = DisplayObject()
    context, space, _ = context_for(display, [obj])
    other_space = SimpleNamespace(clip_start=0.02)
    context.screen.areas.append(
        SimpleNamespace(type="VIEW_3D", spaces=SimpleNamespace(active=other_space))
    )
    assert display._focus_objects(context, [obj])
    assert space.clip_start < 0.01 and other_space.clip_start == 0.02


def test_empty_focus_and_degenerate_bounds_do_not_change_clipping(display):
    context, space, calls = context_for(display, [])
    assert not display._focus_objects(context, [])
    assert space.clip_start == 0.01 and not calls
    obj = DisplayObject((0, 0, 0))
    context, space, _ = context_for(display, [obj])
    assert display._focus_objects(context, [obj])
    assert space.clip_start == 0.01


def test_background_focus_is_a_noop(display):
    obj = DisplayObject()
    context, space, calls = context_for(display, [obj])
    display.bpy.app.background = True
    assert not display._focus_objects(context, [obj])
    assert space.clip_start == 0.01 and not calls
