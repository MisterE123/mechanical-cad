"""Real GeneralSession visible-context presentation/exit paths; native headless evidence only."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    execution_lease,
    general_session,
    register,
    sketch_session,
    sketch_view_presentation,
    unregister,
    workspace,
)
from mechanical_cad_blender.general_sketch_commands import PointSeed  # noqa: E402
from mechanical_cad_blender.sketch_view_presentation import MeshVisibilityLease  # noqa: E402

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def override(target=None):
    target = area if target is None else target
    region = next(region for region in target.regions if region.type == "WINDOW")
    return bpy.context.temp_override(window=window, area=target, region=region)


def unrelated_snapshot():
    return (
        tuple(
            (
                obj.as_pointer(),
                obj.data.as_pointer(),
                obj.hide_viewport,
                obj.hide_render,
                obj.hide_select,
                obj.hide_get(),
                obj.select_get(),
                tuple(tuple(row) for row in obj.matrix_world),
                tuple(item.as_pointer() for item in obj.users_collection),
            )
            for obj in unrelated
        ),
        tuple(tuple(vertex.co) for vertex in mesh.vertices),
        tuple(tuple(face.vertices) for face in mesh.polygons),
        collection.as_pointer(),
        collection.hide_viewport,
        collection.hide_render,
        collection.hide_select,
        tuple(obj.as_pointer() for obj in collection.objects),
        tuple(child.as_pointer() for child in collection.children),
        scene.unit_settings.system,
        scene.unit_settings.scale_length,
    )


def no_draw(_owner):
    pass


def start(original=True):
    space.show_object_viewport_mesh = original
    space.shading.type = "WIREFRAME"
    space.shading.show_cavity = False
    space.shading.cavity_type = "SCREEN"
    space.shading.curvature_ridge_factor = 0.5
    space.shading.curvature_valley_factor = 0.75
    space.shading.cavity_ridge_factor = 1.25
    space.shading.cavity_valley_factor = 1.5
    space.overlay.show_wireframes = True
    other_space.show_object_viewport_mesh = True
    with override():
        owner = general_session.GeneralSession(bpy.context)
        owner.start(((no_draw, "POST_PIXEL"),))
    check(sketch_session.active_session() is owner, "GeneralSession owns the shared registry")
    check(owner.timer is not None and len(owner.handles) == 1, "Real owner resources are acquired")
    check(owner.mesh_visibility is not None, "Production start acquires mesh visibility")
    check(space.show_object_viewport_mesh is True, "Production start retains mesh references")
    check(space.shading.type == "SOLID", "Triangulated solid context uses solid shading")
    check(not space.overlay.show_wireframes, "Artificial mesh diagonals are not overlaid")
    check(
        space.shading.show_cavity
        and space.shading.cavity_type == "BOTH"
        and space.shading.curvature_ridge_factor == 2
        and space.shading.curvature_valley_factor == 2
        and space.shading.cavity_ridge_factor == 3
        and space.shading.cavity_valley_factor == 3,
        "Depth and curvature cues distinguish blind pocket rims without wire triangles",
    )
    check(visible.visible_get(viewport=space), "Owned viewport keeps reference mesh visible")
    check(
        other_space.show_object_viewport_mesh and visible.visible_get(viewport=other_space),
        "Second native viewport retains visible mesh context",
    )
    check(unrelated_snapshot() == baseline, "Production start preserves unrelated native data")
    return owner


def cleaned(owner, captured, expected, label):
    check(not owner.alive and sketch_session.active_session() is None, f"{label}: owner retired")
    check(
        owner.timer is None
        and not owner.handles
        and not owner._cursor_owned
        and not owner._status_owned,
        f"{label}: timer, draw handlers, cursor and status ownership cleared",
    )
    check(owner.mesh_visibility is None, f"{label}: owner releases presentation resource")
    check(space.shading.type == "WIREFRAME", f"{label}: prior shading restored")
    check(space.overlay.show_wireframes, f"{label}: prior wire overlay restored")
    check(
        not space.shading.show_cavity
        and space.shading.cavity_type == "SCREEN"
        and space.shading.curvature_ridge_factor == 0.5
        and space.shading.curvature_valley_factor == 0.75
        and space.shading.cavity_ridge_factor == 1.25
        and space.shading.cavity_valley_factor == 1.5,
        f"{label}: exact prior cavity settings restored",
    )
    if captured is not None:
        check(
            captured._space is None and captured._original is None, f"{label}: lease releases RNA"
        )
    check(space.show_object_viewport_mesh is expected, f"{label}: exact captured viewport restored")
    check(unrelated_snapshot() == baseline, f"{label}: unrelated data and visibility remain exact")
    space.show_object_viewport_mesh = not expected
    owner.cleanup()
    check(
        space.show_object_viewport_mesh is not expected,
        f"{label}: repeated cleanup preserves new edit",
    )
    space.show_object_viewport_mesh = expected


def wait(owner, context):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None, "Actual sidecar completes before the test deadline")
    check(not owner.error, f"Actual sidecar succeeds: {owner.error}")
    check(
        not execution_lease.is_busy(), "Completed native work releases its separate execution lease"
    )


register()
window = bpy.context.window
area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
other_area = next(item for item in window.screen.areas if item.type != "VIEW_3D")
other_area.type = "VIEW_3D"
space, other_space = area.spaces.active, other_area.spaces.active
check(space.as_pointer() != other_space.as_pointer(), "Two native viewport spaces are independent")
scene = bpy.context.scene
document_state._populate_document(
    scene,
    {
        "schema_version": 1,
        "id": "view_isolation_native",
        "name": "General viewport isolation",
        "units": "mm",
        "parameters": {},
        "features": [],
        "active_feature": None,
    },
)
collection = bpy.data.collections.new("Unrelated visibility fixture")
scene.collection.children.link(collection)
mesh = bpy.data.meshes.new("Unrelated isolation mesh")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
unrelated = []
for name in ("Visible context mesh", "Hidden context mesh", "Disabled context mesh"):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    unrelated.append(obj)
visible, hidden, disabled = unrelated
hidden.hide_set(True)
hidden.hide_render = True
hidden.hide_select = True
disabled.hide_viewport = True
collection.hide_render = True
scene.unit_settings.system = "IMPERIAL"
scene.unit_settings.scale_length = 0.03125
bpy.context.view_layer.update()
baseline = unrelated_snapshot()

# Real native solve/full replay and production Finish publication retire the owner.
owner = start()
captured = owner.mesh_visibility
canonical = scene.mechanical_cad.document_json
with override():
    owner.draft.begin_circle(PointSeed(0, 0), 5)
    owner.accept_proposal(bpy.context)
    wait(owner, bpy.context)
    check(owner.can_finish, "Real circle solve enables production Finish")
    check(space.show_object_viewport_mesh is True, "Check keeps reference meshes visible")
    check(scene.mechanical_cad.document_json == canonical, "Check does not commit canonical edits")
    with patch.object(workspace, "request_workspace") as request_workspace:
        owner.request_finish(bpy.context)
        wait(owner, bpy.context)
    check(request_workspace.call_count == 1, "Finish requests Part workspace after cleanup")
check(owner.finished, "Production Finish publishes successfully")
check(
    scene.mechanical_cad.document_json != canonical, "Successful Finish commits the checked sketch"
)
check(not scene.mechanical_cad.sketch_draft_json, "Finish clears its saved draft")
cleaned(owner, captured, True, "Finish")

for original in (True, False):
    canonical = scene.mechanical_cad.document_json
    owner = start(original)
    captured = owner.mesh_visibility
    owner.discard()
    cleaned(owner, captured, original, f"Discard original={original}")
    check(not scene.mechanical_cad.sketch_draft_json, "Discard leaves no saved draft")
    check(scene.mechanical_cad.document_json == canonical, "Discard never changes canonical data")

    owner = start(original)
    captured = owner.mesh_visibility
    check(owner.suspend("Native isolation smoke"), "Production Suspend saves its draft")
    cleaned(owner, captured, original, f"Suspend original={original}")
    check(bool(scene.mechanical_cad.sketch_draft_json), "Suspend retains a recoverable draft")
    check(scene.mechanical_cad.document_json == canonical, "Suspend never changes canonical data")
    sketch_session._discard_stored(scene)


# Both finally layers must release the viewport when earlier teardown fails.
class FailingController:
    def __init__(self):
        self.calls = 0

    def retire(self):
        self.calls += 1
        raise RuntimeError("Injected controller retirement failure")


for failure in ("controller", "cancel", "both"):
    owner = start()
    captured = owner.mesh_visibility
    owner.input_token = "must-be-revoked"
    controller = FailingController() if failure in {"controller", "both"} else None
    owner.input_controller = controller
    if failure in {"cancel", "both"}:
        with patch.object(
            owner, "cancel_native", side_effect=RuntimeError("Injected cancel failure")
        ):
            owner.discard()
    else:
        owner.discard()
    cleaned(owner, captured, True, f"Teardown failure {failure}")
    check(not owner.input_token and owner.input_controller is None, "Failed teardown revokes input")
    check(bool(owner.cleanup_errors), "Failed teardown remains an explicit cleanup diagnostic")
    if controller is not None:
        check(controller.calls == 1, "Controller retirement is attempted exactly once")
    check(
        not execution_lease.is_busy(), "Injected teardown failure starts or strands no native work"
    )

# Fail after the real native true write; the actual resource performs rollback.
native_writes = []


class PartialAcquisitionSpace:
    type = "VIEW_3D"

    def __init__(self, target):
        self.target = target
        self.failed = False

    @property
    def show_object_viewport_mesh(self):
        return self.target.show_object_viewport_mesh

    @show_object_viewport_mesh.setter
    def show_object_viewport_mesh(self, value):
        self.target.show_object_viewport_mesh = value
        native_writes.append(value)
        if not self.failed:
            self.failed = True
            raise RuntimeError("Injected acquisition failure after native write")


space.show_object_viewport_mesh = False
with override():
    owner = general_session.GeneralSession(bpy.context)
    with patch.object(
        sketch_view_presentation,
        "SketchContextLease",
        side_effect=lambda target: MeshVisibilityLease(
            PartialAcquisitionSpace(target), visible=True
        ),
    ):
        try:
            owner.start(((no_draw, "POST_PIXEL"),))
        except RuntimeError as exc:
            check(
                "after native write" in str(exc),
                "Failed start reports the actual acquisition error",
            )
        else:
            raise AssertionError("Expected partial acquisition failure")
check(native_writes == [True, False], "Partial native acquisition writes true then restores false")
cleaned(owner, None, False, "Partial acquisition failure")

for original in (True, False):
    owner = start(original)
    captured = owner.mesh_visibility
    space.show_object_viewport_mesh = False
    owner.discard()
    cleaned(owner, captured, False, f"External filter override original={original}")

# Replace the native editor, then clean up while another viewport owns context.
owner = start()
captured = owner.mesh_visibility
captured_pointer = space.as_pointer()
other_space.show_object_viewport_mesh = False
area.type = "TEXT_EDITOR"
with override(other_area):
    check(bpy.context.space_data == other_space, "Cleanup runs in replacement viewport context")
    check(not owner.valid_context(), "Changed native editor invalidates the original owner")
    check(owner.suspend("Original viewport replaced"), "Invalidated owner still saves its draft")
check(area.type == "TEXT_EDITOR", "Owner cleanup leaves replacement editor type unchanged")
check(space.as_pointer() == captured_pointer, "Cleanup remains bound to the exact captured space")
check(
    other_space.show_object_viewport_mesh is False, "Owner cleanup preserves other viewport filter"
)
cleaned(owner, captured, True, "Editor/context replacement")
sketch_session._discard_stored(scene)
area.type = "VIEW_3D"

check(unrelated_snapshot() == baseline, "All owner exits preserve unrelated object/collection data")
check(not execution_lease.is_busy(), "No native execution remains after owner integration smoke")
unregister()
print("GENERAL_VIEW_ISOLATION_SMOKE_OK", len(checks), bpy.app.version_string)
