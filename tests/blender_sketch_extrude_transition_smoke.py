"""Native sidecar Apply/Cancel/failure, with navigation request recorded.

Headless checks request ordering; interactive workspace transition is separate.
"""
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    execution_lease,
    extrusion_preview,
    register,
    sketch_pending,
    unregister,
    workspace,
)
from mechanical_cad_blender.operators import MCAD_OT_extrude  # noqa: E402

register()
assert bpy.ops.mcad.new_document() == {"FINISHED"}
assert bpy.ops.mcad.add_rectangle(width=40, height=30) == {"FINISHED"}
state = bpy.context.scene.mechanical_cad
profile = state.active_feature
area = next(a for a in bpy.context.screen.areas if a.type == "VIEW_3D")
bpy.context.workspace[workspace.ROLE_KEY] = "SKETCH"
bpy.context.workspace[workspace.OWNER_KEY] = workspace.OWNER


def reap():
    deadline = time.monotonic() + 15
    while execution_lease.is_busy() and time.monotonic() < deadline:
        sketch_pending.reap()
        time.sleep(.02)
    assert not execution_lease.is_busy()


def operator(context, depth):
    op = SimpleNamespace(
        profile=profile, end_condition="BLIND", length=depth,
        length_input=str(depth), properties=SimpleNamespace(is_property_set=lambda *a: False),
        enter_part_after_apply=True, report=lambda *a: None,
        _shortcut_origin=(context.window, context.workspace, context.scene),
    )
    op.preview_candidate = lambda ctx: MCAD_OT_extrude.preview_candidate(op, ctx)
    op._open_part_after_apply = lambda ctx: MCAD_OT_extrude._open_part_after_apply(op, ctx)
    op._extrusion_preview = extrusion_preview.Preview(op, context)
    op._extrusion_preview.applying = True
    return op


with bpy.context.temp_override(area=area):
    before = state.document_json
    original_workspace = bpy.context.workspace
    requests = []

    def request(ctx, role, **kwargs):
        assert state.document_json != before, "Navigation preceded publication"
        assert state.status == "READY" and abs(state.volume - 12000) < .001
        requests.append(role)

    with patch.object(workspace, "request_workspace", side_effect=request):
        # Cancellation cannot publish or navigate.
        op = operator(bpy.context, 10)
        op._extrusion_preview.tick(bpy.context)
        assert MCAD_OT_extrude.modal(op, bpy.context, SimpleNamespace(type="ESC")) == {"CANCELLED"}
        reap()
        assert not requests and state.document_json == before
        assert bpy.context.workspace == original_workspace
        # Real failed native Apply cannot publish or navigate.
        op = operator(bpy.context, 0)
        deadline = time.monotonic() + 40
        result = {"RUNNING_MODAL"}
        while result == {"RUNNING_MODAL"} and time.monotonic() < deadline:
            result = MCAD_OT_extrude.modal(op, bpy.context, SimpleNamespace(type="TIMER"))
            time.sleep(.02)
        assert result == {"CANCELLED"}
        reap()
        assert not requests and state.document_json == before
        assert bpy.context.workspace == original_workspace
        # Native successful Apply requests navigation only after atomic publication.
        op = operator(bpy.context, 10)
        deadline = time.monotonic() + 40
        result = {"RUNNING_MODAL"}
        while result == {"RUNNING_MODAL"} and time.monotonic() < deadline:
            result = MCAD_OT_extrude.modal(op, bpy.context, SimpleNamespace(type="TIMER"))
            time.sleep(.02)
        assert result == {"FINISHED"}
        assert requests == ["PART"]
        assert op._extrusion_preview.accepted and op._extrusion_preview.closed
        reap()
assert not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules)
unregister()
print("SKETCH_EXTRUDE_TRANSITION_SMOKE_OK", flush=True)
