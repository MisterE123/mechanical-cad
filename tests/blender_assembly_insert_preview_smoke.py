"""Native atomic insertion preview; no GUI gestures or slider motion operations."""

import copy
import json
import math
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
sys.path.insert(0, str(ROOT / "tests"))
from unittest.mock import patch  # noqa: E402

from blender_async_helpers import replay_assembly  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    assembly_pending,
    assembly_state,
    document_state,  # noqa: E402
    execution_lease,
    register,  # noqa: E402
)
from mechanical_cad_blender import assembly_source_update_preview as source_preview  # noqa: E402
from mechanical_cad_blender.assembly_insert_preview import (  # noqa: E402
    InsertPreviewSession,
    MCAD_OT_assembly_insert_preview,
)  # noqa: E402
from mechanical_cad_blender.assembly_insert_preview_draft import InsertPreviewDraft  # noqa: E402

register()
checks = []
OUT = Path(
    os.environ.get(
        "MCAD_INSERT_PREVIEW_OUT",
        str(ROOT / "evidence/assembly-insert-preview-20261026/native"),
    )
)
OUT.mkdir(exist_ok=True)
MODE = os.environ.get("MCAD_INSERT_PREVIEW_MODE", "create")


def check(value, label):
    assert value, label
    checks.append(label)
    print("INSERT_PREVIEW_CHECK", label, flush=True)


def call(op, **kwargs):
    check(op(**kwargs) == {"FINISHED"}, op.idname() if hasattr(op, "idname") else op.__name__)


def data():
    return assembly_state.read_assembly(bpy.context.scene.mechanical_cad_assembly)


@contextmanager
def viewport():
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        yield bpy.context


def accepted():
    state = bpy.context.scene.mechanical_cad_assembly
    bpy.context.view_layer.update()
    return (
        tuple(getattr(state, field) for field in assembly_state._STATE_FIELDS),
        bpy.context.scene.mechanical_cad.document_json,
        [
            (
                o.as_pointer(),
                o.data.as_pointer() if o.data is not None else 0,
                list(o.location),
                list(o.rotation_quaternion),
            )
            for o in assembly_display.owned_objects(bpy.context.scene, state.owner_id)
        ],
    )


def finish(owner, context):
    deadline = time.monotonic() + 60
    while not owner.ready() and not owner.error and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.02)
    check(owner.ready(), "Exact insertion preview ready: " + owner.error)


def reap():
    deadline = time.monotonic() + 20
    while execution_lease.is_busy() and time.monotonic() < deadline:
        assembly_pending.reap(bpy.context)
        time.sleep(0.02)
    check(not execution_lease.is_busy(), "Cancelled native lease reaped")


def watch(owner):
    show = owner._show_response

    def capture(response):
        owner.test_response = copy.deepcopy(response)
        show(response)

    owner._show_response = capture
    return owner


def geometry(response, candidate):
    result = response["result"]
    check(result["canonical_assembly"] == candidate, "Replay retains exact candidate and IDs")
    check(set(response["report"]["base_pose"]["transforms"]) == {
        i["id"] for i in candidate["instances"]
    }, "Ghost includes every candidate instance")
    check(all(math.isclose(p["geometry_check"]["brep"]["volume"], 1000, abs_tol=1e-8)
              for p in result["parts"]), "All inserted/reused blocks have exact volume 1000")


def draft_for(original, working=None):
    return InsertPreviewDraft(
        original, "block", working_part=working, parent="root",
        parent_frame="origin", child_frame="origin", kind="fixed",
        name="Captured preview child" if working else "Reused preview child",
        joint_name="Named origin attachment",
    )


def cancel_case(context, draft):
    baseline = accepted()
    owner = watch(InsertPreviewSession(context, draft)).start(context)
    check(not owner.ready() and owner.pending is not None, "Insertion starts pending")
    check(accepted() == baseline, "Pending insertion preserves accepted objects and canonical state")
    finish(owner, context)
    geometry(owner.test_response, draft.candidate())
    check(bool(owner.ghost_positions), "Ready insertion has full geometry ghost")
    check(accepted() == baseline, "Ready insertion does not publish child, joint or source")
    owner.cancel()
    reap()
    check(accepted() == baseline, "Cancel leaves no accepted orphan or display remnant")
    check(source_preview.active() is None and not owner.ghost_positions,
          "Cancel removes transient owner and ghost")


def apply_case(context, draft):
    original = draft.original()
    owner = watch(InsertPreviewSession(context, draft)).start(context)
    finish(owner, context)
    geometry(owner.test_response, draft.candidate())
    with patch.object(assembly_state, "commit_candidate", wraps=assembly_state.commit_candidate) as commit:
        check(owner.apply(context), "Explicit insertion Apply succeeds: " + owner.error)
        check(not owner.apply(context) and commit.call_count == 1, "Insertion applies once only")
        check(commit.call_args.kwargs["expected_source_preview"] is not None,
              "Apply binds fresh full replay to displayed exact geometry")
    current = data()
    check(current == draft.candidate(), "Child and incoming joint publish atomically with stable IDs")
    check(current["instances"][:-1] == original["instances"]
          and current["joints"][:-1] == original["joints"], "Existing instances and all joint coordinates retained")
    check(current["part_sources"][:len(original["part_sources"])] == original["part_sources"],
          "Accepted source revisions are unchanged by insertion")
    geometry(assembly_state.current_display_response(context), current)


if MODE == "reopen":
    call(bpy.ops.wm.open_mainfile, filepath=str(OUT / "insert-preview.blend"))
    check(bpy.context.scene.mechanical_cad_assembly.document_json == (OUT / "accepted.json").read_text(),
          "Fresh process preserves exact saved insertion IDs and canonical data")
    check(source_preview.active() is None, "No transient insertion owner restored")
    check(not assembly_state.display_is_current(bpy.context), "Saved insertion requires explicit Replay")
    call(replay_assembly)
    geometry(assembly_state.current_display_response(bpy.context), data())
    check(len(data()["instances"]) == 5 and len(data()["joints"]) == 4
          and len(data()["parts"]) == 2 and len(data()["part_sources"]) == 2,
          "Both reused and captured insertions persist without orphans")
    marker = "INSERT_PREVIEW_REOPEN_OK"
else:
    call(bpy.ops.mcad.assembly_load, filepath=str(ROOT / "examples/reused_blocks.mcad-assembly.json"))
    original = copy.deepcopy(data())
    with viewport() as context:
        baseline = accepted()
        # Headless Blender rejects INVOKE_DEFAULT before Python invocation.
        # Exercise the real no-handoff method with only its report port supplied.
        from types import SimpleNamespace
        reports = []
        port = SimpleNamespace(report=lambda level, text: reports.append(text))
        result = MCAD_OT_assembly_insert_preview.invoke(port, context, None)
        check(result == {"CANCELLED"} and any("Open Insert" in text for text in reports),
              "Real invoke method refuses absent handoff (report-only native test port)")
        check(accepted() == baseline and source_preview.active() is None,
              "Absent handoff cannot create owner or mutate accepted Assembly")
        reused = draft_for(original)
        cancel_case(context, reused)
        apply_case(context, reused)
    captured = copy.deepcopy(original["part_sources"][0]["document"])
    captured["id"] = "qa_independent_capture"
    captured["name"] = "Independent capture QA"
    check(document_state._commit_candidate(bpy.context, captured), "Prepare independent canonical Working Part")
    with viewport() as context:
        new_part = draft_for(data(), captured)
        check(len(new_part.candidate()["parts"]) == 2
              and len(new_part.candidate()["part_sources"]) == 2, "Capture draft contains exactly one new source and definition")
        cancel_case(context, new_part)
        apply_case(context, new_part)
        changed = copy.deepcopy(original["part_sources"][0]["document"])
        changed["parameters"]["width"] = 20
        baseline = accepted()
        try:
            draft_for(data(), changed)
        except Exception as exc:
            check("update available" in str(exc), "Divergent accepted Part requires separate source update")
        else:
            raise AssertionError("Divergent accepted source allowed")
        check(accepted() == baseline, "Divergent source refusal leaves accepted state untouched")
    # Existing source-update owner remains available after insertion ownership ends.
    check(document_state._commit_candidate(bpy.context, changed), "Prepare separate source-update regression input")
    with viewport() as context:
        baseline = accepted()
        owner = watch(source_preview.SourceUpdatePreview(context)).start(context)
        finish(owner, context)
        check(len(owner.test_response["result"]["instances"]) == 5,
              "Existing source-update preview still includes all instances")
        check(accepted() == baseline, "Source-update regression remains nonpublishing")
        owner.cancel()
        reap()
        check(accepted() == baseline, "Source-update Cancel retains inserted accepted Assembly")
    (OUT / "accepted.json").write_text(bpy.context.scene.mechanical_cad_assembly.document_json)
    call(bpy.ops.wm.save_as_mainfile, filepath=str(OUT / "insert-preview.blend"))
    marker = "INSERT_PREVIEW_OWNER_OK"
check({j["id"]: j["coordinate"] for j in data()["joints"] if j["kind"] == "slider"}
      == {"slide_a": 100, "slide_b": 100}, "No existing slider coordinate changed")
check(not any(k == "OCP" or k.startswith("OCP.") for k in sys.modules), "No OCP in Blender")
(OUT / (MODE + "-checks.json")).write_text(json.dumps(checks, indent=2))
print(marker, len(checks), flush=True)
