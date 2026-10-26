"""Accepted local intent has explicit unverified state if automatic Check cannot start."""

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
    assembly_job_ui,
    constraint_ui,
    document_state,
    execution_lease,
    general_session,
    register,
    sidecar_job,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import AddLine, PointSeed  # noqa: E402

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def wait(owner, context):
    deadline = time.monotonic() + 20
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not owner.error, "Explicit retry completes native work")


def retained(owner, before, canonical):
    check(
        owner.commands.revision == before + 1, "Accepted action advances exactly one local revision"
    )
    check(
        owner.stored_snapshot == owner.scene.mechanical_cad.sketch_draft_json,
        "Accepted draft checkpoint is retained",
    )
    check(
        owner.error.startswith("Draft change retained. Check could not start:"),
        "Startup error is persistent and truthful",
    )
    check(
        "Unverified" in owner.message and "Sketch checked" not in owner.message,
        "Old success caption is gone",
    )
    check(
        not owner.can_finish and not owner.commands.has_current_solution,
        "Failed startup grants no current solve or Finish",
    )
    check(
        owner.evidence_request is None
        and owner.evidence_response is None
        and owner.current_diagnostics is None,
        "No geometry or conflict evidence is invented",
    )
    check(
        owner.pending is None and not execution_lease.is_busy(),
        "Failed startup strands no native execution",
    )
    check(owner.scene.mechanical_cad.document_json == canonical, "Canonical Part stays unchanged")


register()
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    document_state._populate_document(
        context.scene,
        dict(
            schema_version=1,
            id="launch_failure",
            name="Startup recovery",
            units="mm",
            parameters={},
            features=[],
            active_feature=None,
        ),
    )
    canonical = context.scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(context)
    owner.start()
    line = owner.execute(context, AddLine(PointSeed(2, 3), PointSeed(12, 3))).entity_ids[-1]
    wait(owner, context)
    constraint_ui.select_bindings(owner, (("line", line),), context=context)
    before = owner.commands.revision
    with patch.dict(os.environ, {"MCAD_PYTHON": "/nonexistent/mcad-test-python"}):
        check(
            bpy.ops.mcad.constraint_action("EXEC_DEFAULT", action="horizontal") == {"FINISHED"},
            "Committed local relation returns authored success rather than Cancelled",
        )
    retained(owner, before, canonical)
    check(
        any(item["kind"] == "horizontal" for item in owner.commands.sketch["constraints"]),
        "Named relation remains recoverable local intent",
    )
    owner.check(context)
    wait(owner, context)
    check(owner.can_finish, "Explicit Check restores real solve authority")
    # History action also commits exactly once if its automatic check setup fails.
    before = owner.commands.revision
    with patch.object(
        assembly_job_ui, "ensure_supervisor", side_effect=RuntimeError("setup refused")
    ):
        check(
            bpy.ops.mcad.constraint_history("EXEC_DEFAULT", direction="UNDO") == {"FINISHED"},
            "Committed Undo does not falsely return Cancelled",
        )
    retained(owner, before, canonical)
    check(
        not owner.commands.sketch["constraints"],
        "Undo intent is retained despite check-start failure",
    )
    owner.check(context)
    wait(owner, context)
    # A pointer proposal follows the same post-commit reporting policy.
    owner.draft.begin_line(PointSeed(20, 0))
    owner.draft.update_line((30, 0))
    owner.proposal_capture = True
    before = owner.commands.revision
    with patch.object(
        assembly_job_ui, "ensure_supervisor", side_effect=RuntimeError("setup refused")
    ):
        ids = owner.accept_proposal(context)
    retained(owner, before, canonical)
    check(
        bool(ids) and owner.draft.proposal is None and not owner.proposal_capture,
        "Committed proposal retires gesture but retains exact geometry",
    )
    owner.check(context)
    wait(owner, context)
    # Configuration passes, but the actual worker cannot spawn its owned child.
    constraint_ui.select_bindings(owner, (("line", ids[-1]),), context=context)
    before = owner.commands.revision
    with patch.object(
        sidecar_job.subprocess, "Popen", side_effect=OSError("spawn refused")
    ) as spawn:
        check(
            bpy.ops.mcad.constraint_action("EXEC_DEFAULT", action="horizontal") == {"FINISHED"},
            "Accepted relation returns success before asynchronous spawn failure",
        )
        deadline = time.monotonic() + 20
        while owner.pending is not None and time.monotonic() < deadline:
            owner.tick(context)
            time.sleep(0.01)
        check(spawn.call_count == 1, "The actual transport attempts one process launch")
    check(owner.commands.revision == before + 1, "Spawn failure retains one local command")
    check("spawn refused" in owner.error, "Asynchronous spawn error remains visible")
    check(
        "retained" in owner.message and "Sketch checked" not in owner.message,
        "Spawn failure does not retain stale success wording",
    )
    check(
        owner.pending is None and not execution_lease.is_busy(),
        "Failed spawn leaves no owned native handle or execution lease",
    )
    check(
        not owner.can_finish and not owner.commands.has_current_solution,
        "Failed spawn never grants Finish or solve authority",
    )
    check(
        owner.scene.mechanical_cad.document_json == canonical,
        "Spawn failure preserves the canonical Part",
    )
    check(
        owner.stored_snapshot == owner.scene.mechanical_cad.sketch_draft_json,
        "Spawn failure keeps the authored checkpoint",
    )
    owner.check(context)
    wait(owner, context)
    check(owner.can_finish, "Explicit retry after spawn failure restores solve authority")
    horizontal = next(
        item["id"] for item in owner.commands.sketch["constraints"] if item["kind"] == "horizontal"
    )
    constraint_ui.select_bindings(owner, (("constraint", horizontal),), context=context)
    saved = owner.stored_snapshot
    before = owner.commands.revision
    check(
        owner.geometry_cache is None
        and owner.retained_outline is not None
        and owner.retained_outline.source == "retained"
        and owner.retained_outline.request_fingerprint is None,
        "Completed solve retains an authority-free outline before the first draw",
    )
    with patch.dict(os.environ, {"MCAD_PYTHON": "/nonexistent/mcad-test-python"}):
        check(
            bpy.ops.mcad.general_tool("EXEC_DEFAULT", tool="Check") == {"CANCELLED"},
            "Explicit failed recheck returns cancellation without authored changes",
        )
    check(
        owner.commands.revision == before and owner.stored_snapshot == saved,
        "Explicit recheck changes no command or saved draft bytes",
    )
    check(
        not owner.commands.has_current_solution and not owner.can_finish,
        "Recheck startup failure retires command and Finish authority together",
    )
    check(
        owner.evidence_request is None and owner.evidence_response is None,
        "Recheck startup failure retires complete owner evidence",
    )
    check(
        owner.error and "Unverified" in owner.message and "Sketch checked" not in owner.message,
        "Direct Check failure remains persistently unverified",
    )
    check(
        not constraint_ui.action_available(context, "remove_relation")
        and constraint_ui.action_available(context, "recover_remove_relation"),
        "Unverified recheck permits only explicit authored recovery",
    )
    check(owner.retained_outline is not None, "Recheck retains a display-only outline")
    owner.check(context)
    wait(owner, context)
    check(
        owner.can_finish and constraint_ui.action_available(context, "remove_relation"),
        "Fresh explicit successful Check restores ordinary release authority",
    )
    # A cancelled real replacement Check must not revive the older command solve.
    owner.check(context)
    owner.cancel_native()
    check(
        not owner.commands.has_current_solution and not owner.can_finish,
        "Cancelling a replacement Check does not revive retired solve authority",
    )
    deadline = time.monotonic() + 20
    while execution_lease.is_busy() and time.monotonic() < deadline:
        assembly_job_ui._supervise()
        time.sleep(0.01)
    check(not execution_lease.is_busy(), "Cancelled replacement child is reaped")
    owner.check(context)
    wait(owner, context)
    owner.cleanup()
unregister()
print("CONSTRAINT_LAUNCH_FAILURE_SMOKE_OK", len(checks))
