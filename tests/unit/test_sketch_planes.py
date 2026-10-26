"""Principal workplanes retain local authoring, picking and persisted intent."""

import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

PACKAGE = "mcad_plane_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package
planes = importlib.import_module(PACKAGE + ".sketch_planes")
g = importlib.import_module(PACKAGE + ".general_view_geometry")
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
store = importlib.import_module(PACKAGE + ".general_draft_store")
presentation = importlib.import_module(PACKAGE + ".sketch_view_presentation")


@pytest.mark.parametrize(
    "kind,world,normal",
    [
        ("XY", (3, 4, 12), (0, 0, 1)),
        ("XZ", (3, -12, 4), (0, -1, 0)),
        ("YZ", (12, 3, 4), (1, 0, 0)),
    ],
)
def test_principal_plane_ray_and_coordinates(kind, world, normal):
    plane = g.Workplane.from_saved(planes.principal_plane(kind, 12))
    assert plane.local_to_world((3, 4)) == pytest.approx(world)
    assert plane.normal == pytest.approx(normal)
    origin = tuple(p + 20 * n for p, n in zip(world, normal, strict=True))
    hit = g.intersect_ray(plane, origin, tuple(-n for n in normal))
    assert hit.local_mm == pytest.approx((3, 4))
    assert plane.world_to_local(world) == pytest.approx((3, 4, 0))


@pytest.mark.parametrize("kind", ["XY", "XZ", "YZ"])
def test_new_sketch_plane_survives_commands_and_draft_roundtrip(kind):
    document = json.dumps(
        {
            "schema_version": 1,
            "id": "doc",
            "name": "Part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
    )
    plane = planes.principal_plane(kind, -25)
    draft = d.GeneralSketchDraft(document, plane=plane)
    draft.execute(d.AddCircle(d.PointSeed(3, 4), 5))
    assert draft.sketch["plane"] == plane
    restored = store.restore(store.dumps(draft), document)
    assert restored.sketch == draft.sketch
    geometry = g.build_geometry(restored.sketch, source="authored")
    assert geometry.plane.local_to_world((3, 4)) == pytest.approx(
        g.Workplane.from_saved(plane).local_to_world((3, 4))
    )


def test_visible_context_is_local_reversible_and_preserves_user_changes():
    space = SimpleNamespace(type="VIEW_3D", show_object_viewport_mesh=False)
    lease = presentation.MeshVisibilityLease(space, visible=True)
    assert space.show_object_viewport_mesh is True
    assert lease.restore() == ""
    assert space.show_object_viewport_mesh is False
    space.show_object_viewport_mesh = True
    lease = presentation.MeshVisibilityLease(space, visible=True)
    space.show_object_viewport_mesh = False
    assert lease.restore() == ""
    assert space.show_object_viewport_mesh is False


@pytest.mark.parametrize("kind,offset", [("FACE", 0), ("XY", float("nan")), ("XZ", 1e7)])
def test_invalid_plane_rejected(kind, offset):
    with pytest.raises(ValueError):
        planes.principal_plane(kind, offset)
