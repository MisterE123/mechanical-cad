"""Native async preview ownership; headless does not certify GPU/dialog usability."""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402  # noqa: E402  # noqa: E402
    document_state,
    execution_lease,
    register,
    registration,
    sketch_pending,
    unregister,
)
from mechanical_cad_blender import extrusion_preview as preview  # noqa: E402
from mechanical_cad_blender.solid_operators import MCAD_OT_add_solid_feature  # noqa: E402

register()
assert bpy.ops.mcad.new_document() == {"FINISHED"}
assert bpy.ops.mcad.add_rectangle(width=40, height=30) == {"FINISHED"}
state = bpy.context.scene.mechanical_cad
profile = state.active_feature
assert bpy.ops.mcad.add_extrude(profile=profile, length=10) == {"FINISHED"}
base = state.active_feature
result = document_state.current_part_result(bpy.context)
feature = next(f for f in result["features"] if f["id"] == base)
top = base + "/face/cap.end"
side = next(f["id"] for f in feature["topology"] if f["role"].startswith("side."))
area = next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D")


def reap():
    deadline = time.monotonic() + 15
    while execution_lease.is_busy() and time.monotonic() < deadline:
        sketch_pending.reap()
        time.sleep(0.02)
    assert not execution_lease.is_busy()


def operator():
    op = SimpleNamespace(
        kind="fillet",
        base=base,
        edge_mode="PAIR",
        face_a=top,
        face_b=side,
        radius="1",
        distance="1",
        feature_label="Preview blend",
        original_json=state.document_json,
    )
    op.preview_candidate = lambda context: MCAD_OT_add_solid_feature.preview_candidate(op, context)
    return op


def complete(owner, context):
    owner.changed = 0
    deadline = time.monotonic() + 40
    while not owner.completed and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.02)
    assert owner.completed, owner.message


with bpy.context.temp_override(area=area):
    context = bpy.context
    before = state.document_json
    objects = [(o.as_pointer(), o.hide_viewport) for o in context.scene.objects]
    op = operator()
    owner = preview.Preview(op, context)
    op._extrusion_preview = owner
    captured = []
    owner.overlay = lambda response, candidate: captured.append(response)
    complete(owner, context)
    assert owner.completed and owner.pending is None
    # Passive status/help redraw must not cancel or reschedule exact geometry.
    preview.changed(op, context)
    assert owner.completed and owner.pending is None and len(captured) == 1
    assert state.document_json == before
    assert [(o.as_pointer(), o.hide_viewport) for o in context.scene.objects] == objects
    result = captured[-1]["result"]
    active = next(f for f in result["features"] if f["id"] == result["active_feature"])
    assert active["mesh"] and active["stats"]["volume"] < 12000
    # A changed radius launches a different exact replay, not old evidence.
    op.radius = "2"
    preview.changed(op, context)
    complete(owner, context)
    assert len(captured) == 2 and state.document_json == before
    op.kind = "chamfer"
    preview.changed(op, context)
    complete(owner, context)
    chamfer = captured[-1]["result"]["features"][-1]
    assert chamfer["mesh"] and 0 < chamfer["stats"]["volume"] < 12000
    assert state.document_json == before
    op.kind = "fillet"
    # Cancel during native work cannot publish, and its lease eventually reaps.
    op.radius = "3"
    preview.changed(op, context)
    owner.changed = 0
    owner.tick(context)
    owner.changed = 0
    owner.tick(context)
    assert owner.pending is not None
    owner.close()
    reap()
    assert state.document_json == before
    # Blender's actual Undo pre-handler retires preview owners before RNA changes.
    op = operator()
    owner = preview.Preview(op, context)
    owner.changed = 0
    owner.tick(context)
    owner.changed = 0
    owner.tick(context)
    assert owner.pending is not None
    registration._before_history_change(None)
    assert owner.closed and owner not in preview._OWNERS
    reap()
    assert state.document_json == before
    # Stale document is rejected before launching.
    op = operator()
    owner = preview.Preview(op, context)
    state.document_json = before + " "
    try:
        owner.tick(context)
        raise AssertionError("Stale preview accepted")
    except ValueError:
        pass
    finally:
        owner.close()
        state.document_json = before
    # A lost modal window is still supervised without accepting ready work.
    op = operator()
    timers = []
    with patch.object(
        bpy.app.timers, "register", side_effect=lambda callback, **kw: timers.append(callback)
    ):
        owner = preview.start(op, context)
    owner.applying = True
    owner.tick(context)
    owner.window = None
    assert timers[0]() is None
    assert owner.closed and owner not in preview._OWNERS
    reap()
    assert state.document_json == before
    # Exact kernel rejection never turns an impossible radius into a current preview.
    op = operator()
    op.radius = "1000"
    owner = preview.Preview(op, context)
    owner.overlay = lambda *args: (_ for _ in ()).throw(AssertionError("Invalid preview drawn"))
    try:
        complete(owner, context)
        raise AssertionError("Invalid native result accepted")
    except ValueError as exc:
        assert "smaller radius" in str(exc), str(exc)
        assert "successful authority" not in str(exc), str(exc)
    finally:
        owner.close()
    reap()
    assert state.document_json == before
    # Apply takes a fresh request and atomically publishes without sync replay.
    op = operator()
    owner = preview.Preview(op, context)
    op._extrusion_preview = owner
    owner.overlay = lambda response, candidate: None
    complete(owner, context)
    assert state.document_json == before

    # The real Apply transition retires the completed preview and starts fresh work.
    class ApplyContext:
        window_manager = SimpleNamespace(
            windows=context.window_manager.windows,
            event_timer_add=context.window_manager.event_timer_add,
            modal_handler_add=lambda operator: None,
        )

        def __getattr__(self, name):
            return getattr(context, name)

    assert preview.apply(op, ApplyContext()) == {"RUNNING_MODAL"}
    assert owner.pending is None and not owner.completed and owner.applying
    complete(owner, context)
    assert state.document_json != before
    assert json.loads(state.document_json)["features"][-1]["kind"] == "fillet"
    assert json.loads(state.document_json)["parameters"]["fillet_1_radius"] == "1"
    owner.close()
    assert not execution_lease.is_busy()
    applied = state.document_json
    save_path = "/tmp/mcad_blend_preview_smoke.blend"
    assert bpy.ops.wm.save_as_mainfile(filepath=save_path) == {"FINISHED"}
    assert bpy.ops.wm.open_mainfile(filepath=save_path) == {"FINISHED"}
    assert bpy.context.scene.mechanical_cad.document_json == applied

unregister()
print("MCAD_BLEND_PREVIEW_SMOKE_OK", flush=True)
