"""Focus is owner-bound view navigation, never preview acceptance/publication."""

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


class Vector(tuple):
    def __add__(self, other):
        return Vector(a + b for a, b in zip(self, other, strict=True))

    def __mul__(self, scalar):
        return Vector(value * scalar for value in self)


class Rotation:
    """Only the camera-right basis used by production, never scene rotation."""
    def __init__(self, right=(1, 0, 0)):
        self.right = right

    def __matmul__(self, vector):
        assert vector == (1, 0, 0)
        return Vector(self.right)


@pytest.fixture
def host(monkeypatch):
    package_name = "focus_preview_tests"
    package = types.ModuleType(package_name)
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")]
    monkeypatch.setitem(sys.modules, package_name, package)

    def stub(name, **values):
        module = types.ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    stub("bpy")
    stub("mathutils", Vector=Vector)
    for name in ("assembly_job_ui", "backend_contracts", "execution_lease", "operation_contracts", "sketch_pending", "staged_edit_store"):
        stub(package_name + "." + name)
    stub(package_name + ".feature_guidance", feature_error=lambda *args: "")
    stub(package_name + ".part_publication", PartPublicationIntent=object)
    calls = []
    backend = ["original"]

    class Selection:
        def assert_current(self, current):
            if current != "original":
                raise ValueError("Backend changed")

    def configuration(context):
        calls.append("configuration")
        return backend[0], 0.1

    stub(package_name + ".backend_runtime", capture=lambda ctx: Selection(), configuration=configuration)
    monkeypatch.delitem(sys.modules, package_name + ".extrusion_preview", raising=False)
    module = importlib.import_module(package_name + ".extrusion_preview")
    scene = NS(mechanical_cad=NS(document_json='{"active_feature":"accepted"}'), unit_settings=NS(scale_length=1))
    view = NS(view_location=(99, 99, 99), view_distance=99, view_rotation=Rotation(), view_perspective="PERSP", window_matrix=((3.0, 0, 0, 0),))
    space = NS(type="VIEW_3D", region_quadviews=[], region_3d=view, lens=50, clip_start=0.01, clip_end=1000)
    region = NS(type="WINDOW", width=1000, height=800)
    area = NS(type="VIEW_3D", spaces=NS(active=space), regions=[region], tag_redraw=lambda: calls.append("redraw"))
    workspace, layer = object(), object()
    window = NS(scene=scene, workspace=workspace, view_layer=layer, screen=NS(areas=[area]))
    context = NS(window=window, area=area, scene=scene, workspace=workspace, view_layer=layer,
                 mode="OBJECT", window_manager=NS(windows=[window]), selected_objects=["kept"], active_object="kept")
    candidate = {"features": [], "active_feature": "draft"}

    def preview_candidate(ctx):
        calls.append("candidate")
        return candidate

    operator = NS(preview_candidate=preview_candidate)
    owner = module.Preview(operator, context)
    owner.batch = object()
    owner.bounds = ((-1, -2, -3), (3, 4, 5))
    owner.key = module._key(candidate)
    owner.completed = True
    return NS(module=module, context=context, owner=owner, view=view, space=space, region=region,
              candidate=candidate, backend=backend, calls=calls)


@pytest.mark.parametrize("mode", ["PERSP", "ORTHO"])
@pytest.mark.parametrize("right", [(1, 0, 0), (0, 1, 0)])
@pytest.mark.parametrize(("scale", "old_distance"), [(3.0, 99), (0.25, 5)])
def test_only_current_owner_view_changes(host, mode, right, scale, old_distance):
    host.view.view_perspective = mode
    rotation = host.view.view_rotation = Rotation(right)
    host.view.window_matrix = ((scale, 0, 0, 0),)
    host.view.view_distance = old_distance
    original_json = host.context.scene.mechanical_cad.document_json
    key, batch, bounds = host.owner.key, host.owner.batch, host.owner.bounds
    host.module.focus(host.context)
    offset = 0.44 * host.view.view_distance / scale
    if mode == "ORTHO":
        offset /= old_distance
    # Native projection gives the requested center NDC independent of lens fit.
    new_scale = scale * old_distance / host.view.view_distance if mode == "ORTHO" else scale
    projected_x = -offset * new_scale / (host.view.view_distance if mode == "PERSP" else 1)
    assert projected_x == pytest.approx(-0.44)
    assert host.view.view_location == pytest.approx(tuple(1 + axis * offset for axis in right))
    assert host.view.view_distance == pytest.approx(host.module.focus_parameters(
        bounds, host.space.lens, 0.45 * host.region.width / host.region.height, mode,
    )[1])
    assert host.view.view_distance > 0 and host.view.view_distance != 99
    assert host.view.view_rotation is rotation and host.view.view_perspective == mode
    assert host.context.selected_objects == ["kept"] and host.context.active_object == "kept"
    assert host.context.scene.mechanical_cad.document_json == original_json
    assert (host.owner.key, host.owner.batch, host.owner.bounds) == (key, batch, bounds)
    assert not host.owner.accepted and host.owner.publication is None
    assert host.calls == ["configuration", "candidate", "redraw"]


@pytest.mark.parametrize("change", [
    "window", "area", "closed", "document", "scale", "mode", "applying", "pending",
    "incomplete", "batch", "bounds", "stale-key", "backend", "quad", "camera", "region", "duplicate",
])
def test_unavailable_or_changed_preview_never_moves_view(host, change):
    if change == "window":
        host.context.window = object()
    elif change == "area":
        host.context.area = object()
    elif change == "closed":
        host.owner.closed = True
    elif change == "document":
        host.context.scene.mechanical_cad.document_json += " "
    elif change == "scale":
        host.context.scene.unit_settings.scale_length = 2
    elif change == "mode":
        host.context.mode = "EDIT_MESH"
    elif change == "applying":
        host.owner.applying = True
    elif change == "pending":
        host.owner.pending = object()
    elif change == "incomplete":
        host.owner.completed = False
    elif change in {"batch", "bounds"}:
        setattr(host.owner, change, None)
    elif change == "stale-key":
        host.candidate["active_feature"] = "changed"
    elif change == "backend":
        host.backend[0] = "changed"
    elif change == "quad":
        host.space.region_quadviews = [object()]
    elif change == "camera":
        host.view.view_perspective = "CAMERA"
    elif change == "region":
        host.region.width = 0
    else:
        host.module._OWNERS.append(host.owner)
    before = dict(vars(host.view))
    original_json = host.context.scene.mechanical_cad.document_json
    with pytest.raises(ValueError):
        host.module.focus(host.context)
    assert vars(host.view) == before
    assert host.context.scene.mechanical_cad.document_json == original_json
    assert host.context.selected_objects == ["kept"] and host.context.active_object == "kept"
    assert not host.owner.accepted and host.owner.publication is None
    if change == "backend":
        assert host.owner.closed and host.owner not in host.module._OWNERS


@pytest.mark.parametrize("right", [(float("nan"), 0, 0), (1e15, 0, 0)])
def test_invalid_offset_refuses_before_either_view_setter(host, right):
    host.view.view_rotation = Rotation(right)
    before = dict(vars(host.view))
    with pytest.raises(ValueError, match="framing"):
        host.module.focus(host.context)
    assert vars(host.view) == before
    assert not host.owner.accepted and host.owner.publication is None
    assert host.calls == ["configuration", "candidate"]


@pytest.mark.parametrize("field", ["projection", "distance"])
@pytest.mark.parametrize("value", [0, float("nan"), float("inf"), -float("inf")])
def test_invalid_native_projection_refuses_before_view_changes(host, field, value):
    if field == "projection":
        host.view.window_matrix = ((value, 0, 0, 0),)
    else:
        host.view.view_distance = value
    before = dict(vars(host.view))
    with pytest.raises(ValueError, match="projection"):
        host.module.focus(host.context)
    assert vars(host.view) == before
    assert host.calls == ["configuration", "candidate"]
    assert not host.owner.accepted and host.owner.publication is None


def test_negative_old_distance_refuses(host):
    host.view.view_distance = -1
    before = dict(vars(host.view))
    with pytest.raises(ValueError, match="projection"):
        host.module.focus(host.context)
    assert vars(host.view) == before
