"""Fresh-process open/revert and accepted-only automatic cache rebuilding.

Run twice with MCAD_LOAD_DIRECTORY set to an existing temporary directory;
MCAD_LOAD_REOPEN=1 selects the reader. Background Blender pumps the registered
app timer on its main thread. This is not GUI or installed-package qualification.
"""

import json
import math
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    backend_runtime,
    display,
    draft_dispatch,
    execution_lease,
    general_authoring,
    general_session,
    register,
    repair_intent,
    repair_resume,
    sketch_pending,
    sketch_session,
    staged_edit,
    staged_edit_store,
    unregister,
    workspace,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    history_rebuild as rebuild,
)
from mechanical_cad_blender.general_sketch_commands import AddCircle, PointSeed  # noqa: E402
from mechanical_cad_blender.general_sketch_draft import GeneralSketchDraft  # noqa: E402
from staged_edit_cases import projection_case  # noqa: E402

DIRECTORY = Path(os.environ["MCAD_LOAD_DIRECTORY"])
FIELDS = ("document_json", "repair_intent_json", "sketch_draft_json", "sketch_annotation_json")
checks = []


def check(value, message):
    assert value, message
    checks.append(message)
    print("LOAD_CHECK=" + message, flush=True)


def snapshot():
    return {key: getattr(bpy.context.scene.mechanical_cad, key) for key in FIELDS}


def drain():
    deadline = time.monotonic() + 60
    while rebuild._PENDING is not None or execution_lease.is_busy():
        assert time.monotonic() < deadline, "Load replay/cleanup timed out"
        rebuild._tick()
        sketch_pending.reap()
        time.sleep(0.01)
    if bpy.app.timers.is_registered(rebuild._tick):
        bpy.app.timers.unregister(rebuild._tick)


def fresh(expected, label):
    state = bpy.context.scene.mechanical_cad
    check(snapshot() == expected, label + ": canonical/dormant/annotation bytes unchanged")
    check(state.status == "READY" and doc.part_is_current(bpy.context), label + ": fresh authority")
    result = doc.current_part_result(bpy.context)
    volume = next(row for row in result["features"] if row["id"] == "solid")["stats"]["volume"]
    check(abs(volume - 45 * math.pi) < 1e-7, label + ": exact accepted radius-3 volume")
    check(math.isclose(state.volume, volume, rel_tol=1e-6), label + ": UI volume agrees")
    check(
        any(not o.hide_get() for o in display._owned_objects(bpy.context.scene)),
        label + ": visible cache",
    )
    check(staged_edit.current(bpy.context) is None, label + ": no live repair created")
    check(sketch_session.active_session() is None, label + ": no draft resumed")
    check(
        tuple(bpy.data.objects["Unrelated mesh"].location) == (7, 8, 9),
        label + ": unrelated object preserved",
    )
    check(
        bpy.data.scenes["Other Part"].mechanical_cad.status == "DIRTY",
        label + ": other Part not replayed",
    )
    assembly = bpy.data.objects["Assembly-owned fixture"]
    check(
        tuple(assembly.location) == (2, 4, 6)
        and len(assembly.data.vertices) == 3
        and assembly.get(assembly_display.OWNER_KEY) == "assembly-fixture",
        label + ": assembly-owned geometry preserved",
    )


register()
assert bpy.app.background and bpy.app.version[:3] == (5, 2, 2)
bpy.context.preferences.edit.use_global_undo = True

if not os.environ.get("MCAD_LOAD_REOPEN"):
    base, proposed = projection_case()
    check(doc._commit_candidate(bpy.context, base), "Create accepted Part")
    state = bpy.context.scene.mechanical_cad
    # Noncanonical formatting detects even an equivalent JSON rewrite.
    state.document_json = json.dumps(base, indent=3) + "\n"
    check(doc.regenerate(bpy.context), "Build nonnormalized accepted JSON")
    mesh = bpy.data.meshes.new("Unrelated mesh data")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("Unrelated mesh", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (7, 8, 9)
    assembly = bpy.data.objects.new("Assembly-owned fixture", mesh.copy())
    bpy.context.scene.collection.objects.link(assembly)
    assembly.location = (2, 4, 6)
    assembly[assembly_display.OWNER_KEY] = "assembly-fixture"
    bpy.context.scene.mechanical_cad_assembly.owner_id = "assembly-fixture"
    other = bpy.data.scenes.new("Other Part")
    doc._populate_document(other, doc.demo_document())
    expected = {}

    def save(name):
        assert bpy.ops.wm.save_as_mainfile(filepath=str(DIRECTORY / (name + ".blend"))) == {
            "FINISHED"
        }
        expected[name] = snapshot()

    save("plain")
    try:
        doc._commit_candidate(bpy.context, proposed, stage_feature_id="source")
    except Exception:
        pass
    check(staged_edit.current(bpy.context) is not None, "Create real failed edit for saved repair")
    save("repair")
    check(
        bool(state.repair_intent_json) and staged_edit.current(bpy.context) is None,
        "Save leaves only dormant repair",
    )
    staged_edit_store.discard_saved(bpy.context)
    commands = GeneralSketchDraft(state.document_json)
    commands.execute(AddCircle(PointSeed(2, 3), 7))
    wrapper = general_authoring.GeneralSketchAuthoringState(commands)
    state.sketch_draft_json = draft_dispatch.dumps(wrapper)
    save("draft")
    # Unknown/malformed slots are deliberately retained; accepted replay must
    # not even consult their codecs, much less migrate/accept either record.
    state.repair_intent_json = "  { unsupported repair Ω\n"
    state.sketch_draft_json = ' {"schema_version":999, "unknown":"Ω"} \n'
    state.sketch_annotation_json = '  {"future annotations": [1, 2]}\n'
    save("unknown")
    bpy.context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    bpy.context.workspace[workspace.ROLE_KEY] = "ASSEMBLY"
    save("assembly")
    (DIRECTORY / "expected.json").write_text(json.dumps(expected))
else:
    expected = json.loads((DIRECTORY / "expected.json").read_text())

    def open_file(name):
        assert bpy.ops.wm.open_mainfile(filepath=str(DIRECTORY / (name + ".blend"))) == {"FINISHED"}
        check(
            rebuild._PENDING is not None and rebuild._PENDING.after_load,
            name + ": load queues accepted-only replay",
        )
        check(not doc.part_is_current(bpy.context), name + ": saved cache not trusted")

    for name in ("plain", "repair", "draft", "unknown"):
        with (
            patch.object(
                sketch_pending, "prepare_guarded", wraps=sketch_pending.prepare_guarded
            ) as launch,
            patch.object(
                repair_intent, "decode", side_effect=AssertionError("Must not parse repair")
            ),
            patch.object(
                staged_edit, "ResumeValidation", side_effect=AssertionError("Must not Resume")
            ),
            patch.object(
                draft_dispatch, "inspect", side_effect=AssertionError("Must not parse draft")
            ),
        ):
            open_file(name)
            check(launch.call_count == 0, name + ": load handler never launches a process")
            drain()
            check(launch.call_count == 1, name + ": one asynchronous replay")
        fresh(expected[name], name)

    # The actual revert operator follows the same load hooks.
    bpy.context.scene.mechanical_cad.document_json += " "
    assert bpy.ops.wm.revert_mainfile() == {"FINISHED"}
    drain()
    fresh(expected["unknown"], "Native Revert")

    # Loading another file while the previous job runs detaches old RNA first.
    open_file("plain")
    old = rebuild._PENDING
    rebuild._tick()
    check(old.pending is not None, "Prior load replay owns native work")
    open_file("repair")
    check(old.binding is None and old.document is None, "New load revokes prior publication")
    check(rebuild._PENDING is not old, "New file has its own one-shot ticket")
    drain()
    fresh(expected["repair"], "Load over prior running job")

    # A real Resume interaction can start during debounce, then cancel before
    # the timer observes it. The admission stamp still forbids resurrection.
    open_file("repair")
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        owner = repair_resume.ResumeOwner(bpy.context)
        owner.close("Test user cancelled Resume")
    drain()
    check(
        not doc.part_is_current(bpy.context),
        "Cancelled intervening Resume still retires queued rebuild",
    )
    check(snapshot() == expected["repair"], "Resume interruption preserves saved repair bytes")

    # Same boundary for a real restored sketch interaction and local draft edit.
    open_file("draft")
    restored = draft_dispatch.restore(
        expected["draft"]["sketch_draft_json"], expected["draft"]["document_json"]
    )
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        owner = general_session.GeneralSession(bpy.context, restored=restored)
        owner.start()
        owner.commands.execute(AddCircle(PointSeed(8, 9), 2))
        rebuild._tick()
        owner.cleanup()
    drain()
    check(not doc.part_is_current(bpy.context), "Live sketch edit retires queued rebuild")
    check(snapshot() == expected["draft"], "Sketch interruption never consumes saved draft")

    # Actual ready response is rejected if saved text/units/canonical input changes.
    for field in (
        "repair_intent_json",
        "sketch_draft_json",
        "sketch_annotation_json",
        "document_json",
        "units",
        "backend",
    ):
        open_file("plain")
        ticket = rebuild._PENDING
        rebuild._tick()
        pending = ticket.pending
        deadline = time.monotonic() + 30
        while not pending._job.done:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        check(execution_lease.is_busy(), field + ": ready response retains lease")
        if field == "units":
            bpy.context.scene.unit_settings.scale_length = 0.01
        elif field == "backend":
            backend_runtime.revoke("Test backend changed after ready")
        else:
            state = bpy.context.scene.mechanical_cad
            setattr(state, field, getattr(state, field) + " ")
        with patch.object(doc, "_apply_result", wraps=doc._apply_result) as publish:
            drain()
            check(publish.call_count == 0, field + ": stale ready response never published")
        check(ticket.binding is None, field + ": publication capability retired")

    # Not-ready bundled setup never starts setup or waits for later readiness.
    with (
        patch.object(backend_runtime, "_BUNDLE_REQUIRED", True),
        patch.object(backend_runtime, "_BUNDLE_ENABLED", True),
        patch.object(backend_runtime, "_BUNDLE_POLICY", None),
        patch.object(backend_runtime, "_BUNDLE_MESSAGE", "Bundled backend preparing"),
        patch.object(
            backend_runtime, "begin_bundled_setup", side_effect=AssertionError("No setup")
        ),
        patch.object(
            sketch_pending, "prepare_guarded", wraps=sketch_pending.prepare_guarded
        ) as launch,
    ):
        bpy.ops.wm.open_mainfile(filepath=str(DIRECTORY / "plain.blend"))
        check(
            rebuild._PENDING is None and launch.call_count == 0,
            "Not-ready backend launches nothing",
        )
        check(
            "Regenerate" in bpy.context.scene.mechanical_cad.error,
            "Not-ready backend has manual fallback",
        )
    drain()
    check(not doc.part_is_current(bpy.context), "Later readiness cannot silently retry")
    check(doc.regenerate(bpy.context), "Manual Regenerate fallback succeeds")

    # Cancellation stays reachable, terminal and has no canonical side effect.
    open_file("plain")
    rebuild._tick()
    check(bpy.ops.mcad.cancel_history_rebuild() == {"FINISHED"}, "Cancel Rebuild remains reachable")
    drain()
    check(
        snapshot() == expected["plain"] and not doc.part_is_current(bpy.context),
        "Cancel keeps accepted bytes and cannot publish",
    )

    # Native Undo/Redo demonstrates cache publication does not insert a step.
    open_file("plain")
    bpy.context.scene["user_marker"] = "before"
    bpy.ops.ed.undo_push(message="Before user change")
    bpy.context.scene["user_marker"] = "after"
    bpy.ops.ed.undo_push(message="User change")
    drain()
    fresh(expected["plain"], "Before Undo check")
    check(
        bpy.ops.ed.undo() == {"FINISHED"} and bpy.context.scene["user_marker"] == "before",
        "No extra Undo step for load cache publication",
    )
    drain()
    check(
        bpy.ops.ed.redo() == {"FINISHED"} and bpy.context.scene["user_marker"] == "after",
        "Load cache publication preserves Redo",
    )
    drain()
    check(snapshot() == expected["plain"], "Undo/Redo keeps exact canonical bytes")

    # An Assembly workspace can retain accepted Part source, but must not show
    # an unrelated auto-rebuilt Part beside its own separately owned instances.
    with patch.object(
        sketch_pending, "prepare_guarded", wraps=sketch_pending.prepare_guarded
    ) as launch:
        bpy.ops.wm.open_mainfile(filepath=str(DIRECTORY / "assembly.blend"))
        drain()
        check(
            rebuild._PENDING is None and launch.call_count == 0,
            "Assembly workspace skips Part auto-replay",
        )
    check(snapshot() == expected["assembly"], "Assembly skip preserves Part and saved intent bytes")
    check(
        bpy.context.scene.mechanical_cad.status == "DIRTY" and not doc.part_is_current(bpy.context),
        "Inactive stored Part remains dirty for explicit manual rebuilding",
    )
    check(
        all(o.hide_get() for o in display._owned_objects(bpy.context.scene)),
        "Assembly workspace does not reveal stored Part cache",
    )
    check(
        len(bpy.data.objects["Assembly-owned fixture"].data.vertices) == 3,
        "Assembly-owned object survives skipped Part replay",
    )

    open_file("plain")
    bpy.context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    bpy.context.workspace[workspace.ROLE_KEY] = "ASSEMBLY"
    drain()
    check(
        not doc.part_is_current(bpy.context),
        "Switching to Assembly role retires queued Part rebuild",
    )

check(
    not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules),
    "No kernel imported into Blender",
)
unregister()
print(
    "LOAD_REBUILD_SMOKE_OK="
    + json.dumps({"checks": len(checks), "reopen": bool(os.environ.get("MCAD_LOAD_REOPEN"))}),
    flush=True,
)
