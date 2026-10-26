"""Native Undo/Redo + guarded asynchronous fresh Part replay, no GUI qualification.

Run isolated Blender --background --factory-startup --python-exit-code 1.
The background harness pumps the registered app-timer callback on the main thread.
It never calls the manual Regenerate operator after Undo/Redo.
"""

import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    backend_runtime,
    display,
    execution_lease,
    register,
    registration,
    sketch_pending,
    unregister,
)
from mechanical_cad_blender import (  # noqa: E402
    document_state as doc,
)
from mechanical_cad_blender import (  # noqa: E402
    history_rebuild as rebuild,
)

assert bpy.app.background, "Use an isolated background Blender"
checks = []


def check(value, label):
    assert value, label
    checks.append(label)
    print("HISTORY_CHECK=" + label, flush=True)


def drain():
    deadline = time.monotonic() + 30
    while rebuild._PENDING is not None:
        assert time.monotonic() < deadline, "History replay timed out"
        rebuild._tick()
        sketch_pending.reap()
        time.sleep(0.02)
    # Direct pumping does not let Blender unregister the completed callback.
    if bpy.app.timers.is_registered(rebuild._tick):
        bpy.app.timers.unregister(rebuild._tick)
    deadline = time.monotonic() + 10
    while execution_lease.is_busy():
        assert time.monotonic() < deadline, "Native cleanup timed out"
        sketch_pending.reap()
        time.sleep(0.02)


def fresh(width):
    state = bpy.context.scene.mechanical_cad
    check(state.status == "READY", "Restored Part is freshly READY")
    check(doc.part_is_current(bpy.context), "Fresh current evidence is bound")
    expected = (width * 30 - math.pi * 16) * 10
    check(
        math.isclose(state.volume, expected, rel_tol=1e-6), f"Native volume matches width {width}"
    )
    check(
        any(not obj.hide_get() for obj in display._owned_objects(bpy.context.scene)),
        "Fresh mesh is visible",
    )


register()
bpy.context.preferences.edit.use_global_undo = True
scene = bpy.context.scene
unrelated = bpy.data.objects.new("History unrelated object", None)
scene.collection.objects.link(unrelated)
unrelated.location = (7, 8, 9)
other = bpy.data.scenes.new("History unrelated scene")
other["untouched"] = "sentinel"
document = doc.demo_document()
doc._populate_document(scene, document)
check(doc.regenerate(bpy.context), "Initial native geometry built")
base = scene.mechanical_cad.document_json
bpy.ops.ed.undo_push(message="History width 40")
document["parameters"]["width"] = 60.0
doc._populate_document(scene, document)
check(doc.regenerate(bpy.context), "Changed native geometry built")
changed = scene.mechanical_cad.document_json
bpy.ops.ed.undo_push(message="History width 60")
check(bpy.ops.ed.undo() == {"FINISHED"}, "Native Undo succeeds")
check(bpy.context.scene.mechanical_cad.document_json == base, "Undo restores exact original JSON")
check(rebuild._PENDING is not None, "Post-handler schedules rebuild")
check(bpy.app.timers.is_registered(rebuild._tick), "Rebuild uses registered app timer")
check(not doc.part_is_current(bpy.context), "Old display is not current before replay")
drain()
fresh(40)
check(
    bpy.context.scene.mechanical_cad.document_json == base,
    "Replay never reserializes canonical JSON",
)
check(bpy.ops.ed.redo() == {"FINISHED"}, "Cache publication adds no Undo step: Redo succeeds")
drain()
fresh(60)
check(bpy.context.scene.mechanical_cad.document_json == changed, "Redo keeps exact changed JSON")

# Repeated history before launch coalesces to one guarded process.
with patch.object(
    sketch_pending, "prepare_guarded", wraps=sketch_pending.prepare_guarded
) as launch:
    for _ in range(4):
        bpy.ops.ed.undo()
        bpy.ops.ed.redo()
    check(launch.call_count == 0, "History handlers never launch native work")
    drain()
    check(launch.call_count == 1, "Rapid Undo/Redo coalesces into one fresh replay")
fresh(60)

# Revoke a running job, then undo again; original request cannot publish.
bpy.ops.ed.undo()
old = rebuild._PENDING
rebuild._tick()
check(old.pending is not None, "Async history replay launched")
bpy.ops.ed.redo()
check(old.binding is None and old.document is None, "Next history drops old RNA and input")
drain()
fresh(60)

# Context mutation after start must cancel, never publish late completion.
for change, restore, label in (
    (
        lambda: setattr(bpy.context.scene.unit_settings, "scale_length", 0.01),
        lambda: setattr(bpy.context.scene.unit_settings, "scale_length", 1.0),
        "units",
    ),
    (
        lambda: setattr(bpy.context.scene.mechanical_cad, "document_json", base),
        lambda: setattr(bpy.context.scene.mechanical_cad, "document_json", changed),
        "base",
    ),
    (
        lambda: setattr(bpy.context.window, "scene", bpy.data.scenes["History unrelated scene"]),
        lambda: setattr(bpy.context.window, "scene", bpy.data.scenes["Scene"]),
        "active scene",
    ),
    (lambda: backend_runtime.revoke("Test backend changed"), lambda: None, "backend"),
):
    doc.invalidate_backend("Test restored state", bpy.context.scene)
    rebuild.schedule()
    check(rebuild._PENDING is not None, label + " interruption scheduled")
    ticket = rebuild._PENDING
    rebuild._tick()
    change()
    drain()
    check(ticket.binding is None, label + " interruption retires publication")
    restore()
    check(
        not doc.part_is_current(bpy.context), label + " interruption cannot publish stale evidence"
    )

# Failure is a single attempt; explicit manual recovery remains available.
doc.invalidate_backend("Test restored state", bpy.context.scene)
with patch.object(
    sketch_pending, "prepare_guarded", side_effect=RuntimeError("test launch failure")
) as launch:
    rebuild.schedule()
    drain()
    for _ in range(3):
        rebuild._tick()
    check(launch.call_count == 1, "Failure never auto-retries")
check("Regenerate" in bpy.context.scene.mechanical_cad.error, "Failure gives visible manual retry")
check(doc.regenerate(bpy.context), "Manual recovery still works")
fresh(60)

# Lifecycle cancellation, no user document/cache authority retained.
for stop, label in (
    (lambda: bpy.ops.mcad.cancel_history_rebuild(), "explicit cancel"),
    (lambda: registration._before_blend_load(None), "load"),
):
    doc.invalidate_backend("Test restored state", bpy.context.scene)
    rebuild.schedule()
    ticket = rebuild._PENDING
    rebuild._tick()
    stop()
    drain()
    check(ticket.binding is None and rebuild._PENDING is None, label + " cannot resurrect work")

# A real file load retires the old history job before RNA is destroyed. Its
# distinct load-origin ticket freshly rebuilds only the opened accepted Part.
with tempfile.TemporaryDirectory(prefix="mcad-history-") as directory:
    filepath = str(Path(directory) / "history.blend")
    bpy.ops.wm.save_as_mainfile(filepath=filepath)
    doc.invalidate_backend("Test restored state", bpy.context.scene)
    rebuild.schedule()
    ticket = rebuild._PENDING
    rebuild._tick()
    bpy.ops.wm.open_mainfile(filepath=filepath)
    check(
        rebuild._PENDING is not ticket and rebuild._PENDING.after_load,
        "Real file load schedules a distinct accepted-Part rebuild",
    )
    drain()
    check(
        ticket.binding is None and rebuild._PENDING is None,
        "Real file load retires old history authority",
    )
    fresh(60)

# An explicit successful manual rebuild during debounce is not invalidated or repeated.
doc.invalidate_backend("Test restored state", bpy.context.scene)
rebuild.schedule()
check(doc.regenerate(bpy.context), "Manual rebuild can finish before debounce")
with patch.object(
    sketch_pending, "prepare_guarded", wraps=sketch_pending.prepare_guarded
) as launch:
    drain()
    check(launch.call_count == 0, "Completed manual rebuild suppresses automatic duplicate")
fresh(60)

check(
    tuple(bpy.data.objects["History unrelated object"].location) == (7, 8, 9),
    "Unrelated object untouched",
)
check(
    bpy.data.scenes["History unrelated scene"]["untouched"] == "sentinel",
    "Unrelated scene untouched",
)
check(
    not bpy.data.scenes["History unrelated scene"].mechanical_cad.document_json,
    "No CAD state created in unrelated scene",
)
check(
    not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules),
    "No native kernel imported into Blender",
)
doc.invalidate_backend("Test restored state", bpy.context.scene)
rebuild.schedule()
ticket = rebuild._PENDING
rebuild._tick()
unregister()
check(ticket.binding is None, "Disable retires a running publication")
check(
    rebuild._PENDING is None and not bpy.app.timers.is_registered(rebuild._tick),
    "Disable removes rebuild capability",
)
print("HISTORY_REBUILD_SMOKE_OK=" + json.dumps({"checks": len(checks)}), flush=True)
