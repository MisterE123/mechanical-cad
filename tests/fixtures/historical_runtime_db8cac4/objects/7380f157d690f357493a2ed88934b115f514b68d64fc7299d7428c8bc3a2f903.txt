"""Production general owner async command/driver/Finish seam, no modal GUI claims."""

import json
import math
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
    sketch_pending,
    sketch_session,
    unregister,
    workspace,
)
from mechanical_cad_blender.general_sketch_draft import (  # noqa: E402
    AddRelation,
    PointRef,
    PointSeed,
)

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def wait(owner, context):
    deadline = time.monotonic() + 20
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None, "Async operation completes within bounded test deadline")
    check(not execution_lease.is_busy(), "Actual completed process releases shared lease")
    return not owner.error


def blank():
    return {
        "schema_version": 1,
        "id": "general_native",
        "name": "General sketch native test",
        "units": "mm",
        "parameters": {"radius": 5},
        "features": [],
        "active_feature": None,
    }


register()
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    scene = context.scene
    document_state._populate_document(scene, blank())
    base = scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(context)
    owner.start()
    check(sketch_session.active_session() is owner, "Production general owner uses shared registry")
    owner.draft.begin_circle(PointSeed(0, 0), 5)
    owner.proposal_capture = True
    ids = owner.accept_proposal(context)
    check(owner.pending is not None, "Accepted circle schedules async solve only")
    check(scene.mechanical_cad.document_json == base, "Local command never changes canonical Part")
    check(
        owner.draft.proposal is None and not owner.proposal_capture,
        "Accepted gesture clears capture",
    )
    check(wait(owner, context), owner.error)
    check(
        owner.commands.has_current_solution and owner.can_finish,
        "Real native solution enables Finish",
    )
    check(owner.geometry().source == "solved", "Current geometry uses strict native response")
    circle_id = ids[-1]
    relation = owner.execute(context, AddRelation("radius", (circle_id,), value="radius"))
    check(wait(owner, context), owner.error)
    prior_draft = owner.draft
    prior_commands = owner.commands
    prior_revision = owner.commands.revision
    prior_snapshot = scene.mechanical_cad.sketch_draft_json
    prior_request, prior_response = owner.evidence_request, owner.evidence_response
    prior_geometry = owner.geometry()
    with patch.object(owner, "_start_job", side_effect=AssertionError("No-op started native work")):
        duplicate = owner.execute(context, AddRelation("radius", (circle_id,), value="radius"))
    check(
        not duplicate.changed and duplicate.constraint_id == relation.constraint_id,
        "Duplicate relation returns its original stable identity",
    )
    check(
        owner.draft is prior_draft and owner.commands is prior_commands,
        "No-op retains owner intent",
    )
    check(owner.commands.revision == prior_revision, "No-op creates no command revision")
    check(
        scene.mechanical_cad.sketch_draft_json == prior_snapshot
        and owner.stored_snapshot == prior_snapshot,
        "No-op preserves exact saved draft and CAS ownership",
    )
    check(
        owner.evidence_request is prior_request and owner.evidence_response is prior_response,
        "No-op preserves exact current evidence",
    )
    check(
        owner.geometry() is prior_geometry
        and owner.commands.has_current_solution
        and owner.can_finish,
        "No-op preserves current geometry and Finish qualification",
    )
    check(
        owner.pending is None and not execution_lease.is_busy(), "No-op acquires no execution lease"
    )
    owner.draft.place_annotation(relation.constraint_id, (8, 8))
    owner.checkpoint()
    revision = owner.commands.revision
    raw = owner.begin_dimension(relation.constraint_id)
    check(raw == "radius", "Compact field starts with exact formula")
    owner.update_raw("  radius * 2  ")
    owner.request_driver_accept(context)
    check(wait(owner, context), owner.error)
    check(owner.commands.pending_edit is None, "One checked Enter accepts pending driver")
    check(owner.commands.revision == revision + 1, "Driver creates exactly one command revision")
    check(owner.geometry().circles[circle_id].radius_mm == 10, "Native circle doubles to 10 mm")
    check(
        owner.draft.annotations[relation.constraint_id]["display"] == "radius",
        "Radius annotation binding retained",
    )
    check(scene.mechanical_cad.document_json == base, "Dimension remains local until Finish")
    before = owner.commands.revision
    owner.begin_dimension(relation.constraint_id)
    check(
        owner.geometry().source == "retained",
        "Opening changed driver keeps an explicit retained outline",
    )
    check(
        owner.geometry().request_fingerprint is None,
        "Retained outline has no current solver fingerprint",
    )
    check(
        owner.geometry().circles[circle_id].radius_mm == 10,
        "Opening input never jumps to authored radius 5",
    )
    check(
        not owner.commands.has_current_solution,
        "Pending field has no current command solve authority",
    )
    owner.update_raw(" radius / 0 ")
    owner.request_driver_accept(context)
    check(not wait(owner, context), "Invalid arithmetic remains an explicit failed check")
    check(
        owner.commands.pending_edit.raw_text == " radius / 0 ", "Invalid raw input retained exactly"
    )
    check(owner.commands.revision == before, "Failed driver creates no command")
    check(not owner.can_finish, "Invalid pending field blocks Finish")
    check(
        owner.geometry().circles[circle_id].radius_mm == 10,
        "Invalid raw input retains the accepted outline",
    )
    check(owner.geometry().source == "retained", "Failed input outline stays visibly unverified")
    owner.cancel_dimension()
    check(
        owner.geometry().circles[circle_id].radius_mm == 10,
        "Cancel retains shape instead of reverting to seeds",
    )
    check(not owner.error, "Cancel removes obsolete validation error")
    owner.check(context)
    check(wait(owner, context), owner.error)
    check(owner.geometry().circles[circle_id].radius_mm == 10, "Cancel restores accepted radius")
    with patch.object(workspace, "request_workspace") as switch:
        owner.request_finish(context)
        check(wait(owner, context), owner.error)
    check(owner.finished and not owner.alive, "Exact full replay Finish retires editor")
    check(switch.call_count == 1, "Successful Finish requests Part once")
    check(scene.mechanical_cad.status == "READY", "Finished circle is a current profile")
    check(not scene.mechanical_cad.sketch_draft_json, "Finish clears only its owned saved draft")
    accepted = json.loads(scene.mechanical_cad.document_json)
    feature_id = accepted["features"][0]["id"]
    check(
        accepted["features"][0]["sketch"]["constraints"][0]["value"] == "radius * 2",
        "Accepted formula preserved",
    )
    accepted["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "label": "Pad",
            "params": {"length": 7},
            "inputs": {"profile": feature_id},
        }
    )
    accepted["active_feature"] = "pad"
    document_state._commit_candidate(context, accepted, result_version=2)
    check(
        math.isclose(scene.mechanical_cad.volume, math.pi * 100 * 7, rel_tol=1e-6),
        "Canonical circle extrudes analytically",
    )
    source_before = scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(context, feature_id)
    owner.start()
    owner.check(context)
    check(wait(owner, context), owner.error)
    owner.begin_dimension(relation.constraint_id)
    owner.update_raw("radius + 2")
    owner.request_driver_accept(context)
    check(wait(owner, context), owner.error)
    check(
        owner.commands.pending_edit is None and owner.geometry().circles[circle_id].radius_mm == 7,
        "Consumed driver passes solve and downstream replay",
    )
    check(
        scene.mechanical_cad.document_json == source_before,
        "Downstream validation does not publish automatically",
    )
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        check(wait(owner, context), owner.error)
    check(
        math.isclose(scene.mechanical_cad.volume, math.pi * 49 * 7, rel_tol=1e-6),
        "Same extrusion follows accepted upstream edit",
    )
    check(
        json.loads(scene.mechanical_cad.document_json)["active_feature"] == "pad",
        "Downstream feature identity retained",
    )

    # A stale in-flight owner must not publish even when its real result is ready.
    owner = general_session.GeneralSession(context, feature_id)
    owner.start()
    owner.check(context)
    scene.mechanical_cad.document_json += " "
    owner.tick(context)
    check(
        bool(owner.error) and owner.pending is None, "Changed exact base rejects pending evidence"
    )
    check(
        scene.mechanical_cad.document_json.endswith(" "),
        "Rejection preserves newer canonical bytes",
    )
    owner.suspend("Injected base change")
    check(
        bool(scene.mechanical_cad.sketch_draft_json), "Stale draft retained for explicit recovery"
    )
    sketch_pending.cancel_all("Test cleanup")
    scene.mechanical_cad.sketch_draft_json = ""

    # A separate open chain can be saved as successful editable data.
    document_state._populate_document(scene, blank())
    owner = general_session.GeneralSession(context)
    owner.start()
    owner.draft.begin_line(PointSeed(0, 0), (30, 0))
    first = owner.accept_proposal(context)
    check(wait(owner, context), owner.error)
    owner.draft.begin_line(PointRef(first[1]), (30, 40))
    owner.accept_proposal(context)
    check(wait(owner, context), owner.error)
    check(owner.commands.has_current_solution, "Open chain has a successful solve")
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        check(wait(owner, context), owner.error)
    check(
        scene.mechanical_cad.volume == 0 and scene.mechanical_cad.status == "READY",
        "Open chain Finish is ready without a manufactured solid",
    )
    check(not scene.mechanical_cad.sketch_draft_json, "Open chain saved canonically")

check(not execution_lease.is_busy(), "All native work reaped at completion")
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "CAD libraries remain outside Blender",
)
unregister()
print("GENERAL_SESSION_SMOKE_OK", len(checks))
