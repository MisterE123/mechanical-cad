"""Local journal edits reject global busy/cleanup before changing draft intent."""

import copy
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    backend_contracts,
    backend_runtime,
    constraint_ui,
    document_state,
    execution_lease,
    general_session,
    register,
    sketch_pending,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import AddLine, AddRelation, PointSeed  # noqa: E402

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def wait(owner, context):
    deadline = time.monotonic() + 20
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not owner.error, "Actual native request completed")


def snapshot(owner):
    return (
        owner.draft,
        owner.commands,
        json.dumps(owner.commands.checkpoint_payload(), sort_keys=True),
        owner.stored_snapshot,
        owner.scene.mechanical_cad.sketch_draft_json,
        owner.scene.mechanical_cad.document_json,
        owner.evidence_request,
        owner.evidence_response,
        owner.geometry(),
        owner.commands.has_current_solution,
    )


def unchanged(owner, before):
    after = snapshot(owner)
    check(
        all(a is b for a, b in zip(after[:2], before[:2], strict=True)),
        "Busy preserves owner intent objects",
    )
    check(
        after[2:6] == before[2:6], "Busy preserves complete journal, saved slot and canonical bytes"
    )
    check(
        all(a is b for a, b in zip(after[6:9], before[6:9], strict=True)),
        "Busy preserves evidence and display identities",
    )
    check(
        after[9] == before[9] and owner.pending is None,
        "Busy preserves solve authority and launches no work",
    )


def reject_mutations(owner, context):
    before = snapshot(owner)
    for direction in ("UNDO", "REDO"):
        reports = []
        operator = SimpleNamespace(
            direction=direction, report=lambda kind, text, reports=reports: reports.append(text)
        )
        check(
            constraint_ui.MCAD_OT_constraint_history.execute(operator, context) == {"CANCELLED"},
            "Busy inspector history cancels normally",
        )
        check(
            len(reports) == 1 and reports[0] == execution_lease.BUSY_MESSAGE,
            "Busy reports explicit retry guidance",
        )
        unchanged(owner, before)
    for callback in (
        lambda: owner.local_history(context),
        lambda: owner.local_history(context, redo=True),
        lambda: owner.check(context),
        lambda: owner.execute(context, AddLine(PointSeed(1, 1), PointSeed(5, 6))),
    ):
        try:
            callback()
        except ValueError as error:
            check(
                str(error) == execution_lease.BUSY_MESSAGE,
                "Direct owner rejects busy before mutation",
            )
        else:
            raise AssertionError("Busy owner mutation accepted")
        unchanged(owner, before)


class CleanupTail:
    """Detached deterministic cleanup tail; never supplies accepted solve data."""

    def __init__(self, prepared, selection, *, owner_token):
        self.request = prepared.guarded_request()
        self.selection = selection
        self.owner_token = owner_token
        self.state = "running"

    @property
    def done(self):
        return self.state == "cancelled"

    def start(self, current_selection):
        self.selection.assert_current(current_selection)
        return self

    def cancel(self):
        if not self.done:
            self.state = "cancelling"
        return True

    def poll(self, current_selection):
        self.selection.assert_current(current_selection)
        return self.state

    def wait(self, timeout=None):
        return self.done

    def result(self, current_selection, *, owner_token):
        raise AssertionError("Retired cleanup must never accept a result")

    def request_snapshot(self):
        return copy.deepcopy(self.request)


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
            id="history_busy",
            name="History gate",
            units="mm",
            parameters={},
            features=[],
            active_feature=None,
        ),
    )
    owner = general_session.GeneralSession(context)
    owner.start()
    line = owner.execute(context, AddLine(PointSeed(2, 3), PointSeed(12, 3))).entity_ids[-1]
    wait(owner, context)
    owner.execute(context, AddRelation("horizontal", (line,)))
    wait(owner, context)
    token = execution_lease.try_acquire()
    check(token is not None, "Independent native operation acquires lease")
    try:
        reject_mutations(owner, context)
        check(
            execution_lease.is_busy(), "Rejected history never releases another operation's lease"
        )
    finally:
        execution_lease.release(token)
    with patch.object(document_state, "_REPLAY_RUNNING", True):
        reject_mutations(owner, context)
    # Global lease outlives cancellation until detached cleanup confirms done.
    with patch.object(sketch_pending, "_GUARDED_JOB_FACTORY", CleanupTail):
        retired = sketch_pending.prepare_guarded(
            backend_contracts.prepare_request(owner.commands.solve_request()),
            {"foreign": "cleanup"},
            selection=backend_runtime.capture(context),
            owner_token=object(),
        )
    sketch_pending.cancel(retired, "Deterministic delayed cleanup")
    check(
        execution_lease.is_busy() and not retired.done, "Cancelled cleanup retains the global lease"
    )
    reject_mutations(owner, context)
    retired._job.state = "cancelled"
    sketch_pending.reap()
    check(not execution_lease.is_busy() and retired.done, "Only confirmed cleanup releases lease")
    before = owner.commands.revision
    owner.local_history(context)
    wait(owner, context)
    check(owner.commands.revision == before + 1, "Explicit retry performs Undo once after cleanup")
    owner.local_history(context, redo=True)
    wait(owner, context)
    check(
        any(item["kind"] == "horizontal" for item in owner.commands.sketch["constraints"]),
        "Explicit Redo restores the relation",
    )
    owner.cleanup()
unregister()
print("CONSTRAINT_HISTORY_BUSY_SMOKE_OK", len(checks))
