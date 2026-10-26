"""Actual owner constraint transactions and native solves; no GUI usability claim."""

import copy
import json
import math
import os
import sys
import time
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    constraint_actions as actions,
)
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    execution_lease,
    general_authoring_store,
    general_session,
    register,
    sketch_session,
    unregister,
    workspace,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddRelation,
    DraftError,
    PointRef,
    PointSeed,
)

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def unchanged(owner):
    return (
        id(owner.draft),
        id(owner.commands),
        owner.commands.revision,
        general_authoring_store.dumps(owner.draft),
        owner.stored_snapshot,
        owner.scene.mechanical_cad.document_json,
        owner.scene.mechanical_cad.sketch_draft_json,
        id(owner.evidence_request),
        id(owner.evidence_response),
        owner.pending,
    )


def rejected(owner, operation, message):
    before = unchanged(owner)
    try:
        operation()
    except (DraftError, ValueError):
        pass
    else:
        raise AssertionError(message + ": unexpectedly accepted")
    check(unchanged(owner) == before, message + "; rejected without mutation")


def wait(owner, context, *, success=True):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None, "Actual native request completes")
    check(not execution_lease.is_busy(), "Actual completed process releases shared lease")
    if success:
        check(not owner.error, "Native request succeeds: " + owner.error)
        check(owner.commands.has_current_solution or owner.finished, "Current solve or Finish")
    else:
        check(bool(owner.error) and not owner.commands.has_current_solution, "Native solve fails")


def select(owner, kind, identifier):
    owner.draft.select(((kind, identifier),))
    owner.checkpoint()


def perform(owner, context, name, *, confirmed=False):
    intent = actions.prepare(owner, name)
    result = actions.apply(owner, context, intent, confirmed=confirmed)
    check(result.changed, name + " delegates a real command")
    wait(owner, context)
    return result


def solved_points(owner):
    return {
        item["id"]: (item["u"], item["v"])
        for item in owner.evidence_response["result"]["sketch"]["solved"]["points"]
    }


def same_points(left, right):
    return left.keys() == right.keys() and all(
        math.dist(left[key], right[key]) < 1e-8 for key in left
    )


def dof(owner):
    return owner.evidence_response["result"]["sketch"]["remaining_dof"]


register()
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    scene = context.scene
    document_state._populate_document(
        scene,
        {
            "schema_version": 1,
            "id": "constraint_transactions_native",
            "name": "Explicit constraint transactions",
            "units": "mm",
            "parameters": {"width": 30, "depth": 20},
            "features": [],
            "active_feature": None,
        },
    )
    canonical = scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(context)
    owner.start()
    # Four joined lines use ordinary general-editor proposals, no Rectangle tool.
    owner.draft.begin_line(PointSeed(7, 9), (35, 10))
    a, b, bottom = owner.accept_proposal(context)
    wait(owner, context)
    owner.draft.begin_line(PointRef(b), (34, 28))
    c, right = owner.accept_proposal(context)
    wait(owner, context)
    owner.draft.begin_line(PointRef(c), (8, 29))
    d, top = owner.accept_proposal(context)
    wait(owner, context)
    owner.draft.begin_line(PointRef(d))
    (left,) = owner.accept_proposal(context, endpoint=PointRef(a))
    wait(owner, context)
    initial_points = solved_points(owner)
    relation_ids = []
    for line, action in (
        (bottom, "horizontal"),
        (right, "vertical"),
        (top, "horizontal"),
        (left, "vertical"),
    ):
        select(owner, "line", line)
        outcome = perform(owner, context, action)
        relation_ids.append(outcome.constraint_id)
        old = unchanged(owner)
        geometry = owner.geometry()
        duplicate = actions.prepare(owner, action)
        check(duplicate.state == "existing", "Duplicate action exposes existing relation")
        with (
            patch.object(owner, "execute", side_effect=AssertionError("Duplicate executed")),
            patch.object(
                owner, "_start_job", side_effect=AssertionError("Duplicate started native work")
            ),
        ):
            result = actions.apply(owner, context, duplicate)
        check(
            not result.changed and result.relation_ids == (outcome.constraint_id,),
            "Duplicate exact ID",
        )
        check(
            unchanged(owner) == old and owner.geometry() is geometry,
            "Duplicate preserves all authority",
        )

    select(owner, "point", a)
    origin = actions.prepare(owner, "fix_origin")
    check(
        origin.target == (0, 0) and origin.requires_confirmation,
        "Origin has explicit movement target",
    )
    check("move" in origin.disclosure, "Origin action discloses geometry movement")
    try:
        origin.target = (10, 20)
    except FrozenInstanceError:
        check(True, "Prepared intent is immutable")
    else:
        raise AssertionError("Intent is mutable")
    rejected(owner, lambda: actions.apply(owner, context, origin), "Cancelled/unconfirmed origin")
    rejected(
        owner,
        lambda: actions.apply(owner, context, origin, confirmed=1),
        "Truthy value is not confirmation",
    )
    rejected(
        owner,
        lambda: actions.apply(owner, context, replace(origin, target=(1, 2)), True),
        "Forged target",
    )
    anchor = actions.apply(owner, context, origin, confirmed=True).constraint_id
    wait(owner, context)
    check(
        solved_points(owner)[a] == (0, 0), "Native origin constraint moves selected point to zero"
    )
    check(
        not same_points(initial_points, solved_points(owner)),
        "Origin can intentionally move geometry",
    )
    rejected(
        owner, lambda: actions.apply(owner, context, origin, True), "Reusing accepted origin intent"
    )
    for action in ("fix_here", "fix_origin"):
        existing = actions.prepare(owner, action)
        check(
            existing.state == "existing" and existing.relation_ids == (anchor,),
            "Existing fixed target is inspectable",
        )
        old = unchanged(owner)
        with patch.object(owner, "execute", side_effect=AssertionError("Existing fixed executed")):
            result = actions.apply(owner, context, existing)
        check(not result.changed and unchanged(owner) == old, "Existing fixed is never retargeted")

    width = owner.execute(context, AddRelation("distance", (a, b), value="width")).constraint_id
    wait(owner, context)
    owner.execute(context, AddRelation("distance", (b, c), value="depth"))
    wait(owner, context)
    check(dof(owner) == 0, "Actual four-line H/V plus fixed and dimensions reaches zero DoF")
    check(
        owner.evidence_response["result"]["profile_check"]["ready"],
        "Actual loop is a closed valid profile",
    )

    owner.begin_dimension(width)
    owner.update_raw("  width * 2  ")
    owner.request_driver_accept(context)
    wait(owner, context)
    before_release = solved_points(owner)
    check(
        math.isclose(math.dist(before_release[a], before_release[b]), 60),
        "Actual driver edit updates width",
    )
    select(owner, "constraint", anchor)
    released = perform(owner, context, "remove_relation")
    check(released.relation_ids == (anchor,), "Release reports exact removed fixed ID")
    check(dof(owner) == 2, "Anchor release exposes real two translational DoF")
    check(
        same_points(solved_points(owner), before_release),
        "Release preserves solved placement after dimension edit",
    )
    select(owner, "point", c)
    with patch.object(owner, "geometry", side_effect=AssertionError("Display is not authority")):
        fixed_here = actions.prepare(owner, "fix_here")
    check(fixed_here.target == before_release[c], "Fix here uses exact validated solved point")
    here = actions.apply(owner, context, fixed_here).constraint_id
    wait(owner, context)
    check(
        dof(owner) == 0 and same_points(before_release, solved_points(owner)),
        "Fix here has no position jump",
    )
    select(owner, "point", c)
    fixed_at_other_target = actions.prepare(owner, "fix_origin")
    check(
        fixed_at_other_target.state == "existing" and fixed_at_other_target.relation_ids == (here,),
        "Origin inspects nonzero existing target",
    )
    check(
        not actions.apply(owner, context, fixed_at_other_target).changed,
        "Origin never retargets existing nonzero lock",
    )
    check(solved_points(owner)[c] == before_release[c], "Nonzero fixed target remains exact")

    # Bindings reject selection A-B-A, raw input, external bytes/slots, and busy work.
    select(owner, "point", a)
    stale = actions.prepare(owner, "fix_origin")
    select(owner, "point", b)
    rejected(owner, lambda: actions.apply(owner, context, stale, True), "Changed selection")
    select(owner, "point", a)
    rejected(owner, lambda: actions.apply(owner, context, stale, True), "Selection A-B-A")
    stale = actions.prepare(owner, "fix_origin")
    owner.begin_dimension(width)
    owner.update_raw("width +")
    rejected(owner, lambda: actions.apply(owner, context, stale, True), "New raw dimension input")
    owner.cancel_dimension()
    rejected(
        owner,
        lambda: actions.apply(owner, context, stale, True),
        "Input Begin/Cancel cannot revive confirmation",
    )
    # Repeat from no solve evidence, so only checkpoint-generation binding can
    # detect that an identical-byte input Begin/Cancel cycle happened.
    stale = actions.prepare(owner, "fix_origin")
    owner.begin_dimension(width)
    owner.cancel_dimension()
    rejected(
        owner,
        lambda: actions.apply(owner, context, stale, True),
        "Unverified input Begin/Cancel generation",
    )
    owner.check(context)
    rejected(owner, lambda: actions.prepare(owner, "fix_origin"), "Pending native work")
    wait(owner, context)
    stale = actions.prepare(owner, "fix_origin")
    original_source = scene.mechanical_cad.document_json
    scene.mechanical_cad.document_json = original_source + " "
    rejected(
        owner, lambda: actions.apply(owner, context, stale, True), "External raw source-byte edit"
    )
    scene.mechanical_cad.document_json = original_source
    original_slot = scene.mechanical_cad.sketch_draft_json
    scene.mechanical_cad.sketch_draft_json = original_slot + " "
    rejected(owner, lambda: actions.apply(owner, context, stale, True), "External saved-slot edit")
    scene.mechanical_cad.sketch_draft_json = original_slot
    token = execution_lease.try_acquire()
    check(token is not None, "Test acquires independent busy lease")
    try:
        rejected(
            owner, lambda: actions.apply(owner, context, stale, True), "Other native operation busy"
        )
    finally:
        execution_lease.release(token)
    with patch.object(document_state, "_REPLAY_RUNNING", True):
        rejected(owner, lambda: actions.apply(owner, context, stale, True), "Canonical replay busy")
    owner.draft.begin_line(PointRef(a), (-5, 0))
    rejected(owner, lambda: actions.apply(owner, context, stale, True), "Unfinished proposal")
    owner.draft.cancel_proposal()
    owner.checkpoint()
    rejected(
        owner,
        lambda: actions.apply(owner, context, stale, True),
        "Proposal cancellation invalidates old confirmation",
    )
    rejected(owner, lambda: actions.prepare(owner, "coincident"), "No production Coincident action")

    # Neither a geometry cache nor a valid-looking response for an old request
    # can supply FixHere coordinates.
    select(owner, "point", a)
    valid_response = owner.evidence_response
    owner.evidence_response = copy.deepcopy(valid_response)
    owner.evidence_response["input_fingerprint"] = "0" * 64
    authored_before = unchanged(owner)[:7]
    try:
        actions.prepare(owner, "fix_here")
    except DraftError:
        pass
    else:
        raise AssertionError("Strict evidence fingerprint rejection")
    check(unchanged(owner)[:7] == authored_before, "Strict rejection preserves all authored bytes")
    check(not owner.commands.has_current_solution, "Malformed projection revokes current solve")
    owner.evidence_response = valid_response
    check(not owner.can_finish, "Restoring saved response cannot revive guarded authority")
    owner.check(context)
    wait(owner, context)
    stale = actions.prepare(owner, "fix_here")
    owner.cancel_native()
    # Cancelling with no live process does not clear accepted evidence; no fake
    # cancellation generation is claimed. Explicit UI cancellation drops intent.
    check(owner.commands.has_current_solution, "No-op Cancel Check retains accepted solve")

    # Deliberately conflict with the bottom horizontal + nonzero width.
    select(owner, "line", bottom)
    conflict_intent = actions.prepare(owner, "vertical")
    conflict = actions.apply(owner, context, conflict_intent).constraint_id
    wait(owner, context, success=False)
    check(
        owner.current_diagnostics is not None,
        "Actual conflict has separately bound diagnostic candidates",
    )
    select(owner, "constraint", conflict)
    rejected(
        owner,
        lambda: actions.prepare(owner, "remove_relation"),
        "Normal Remove never falls back to recovery",
    )
    recovery = actions.prepare(owner, "recover_remove_relation")
    owner.cancel_native()
    rejected(
        owner,
        lambda: actions.apply(owner, context, recovery, True),
        "Retired conflict diagnostic invalidates its prepared recovery disclosure",
    )
    restored_conflict = general_authoring_store.dumps(owner.draft)
    owner.suspend("restore inconsistent draft")
    owner = general_session.GeneralSession(
        context, restored=general_authoring_store.restore(restored_conflict, canonical)
    )
    owner.start()
    check(
        owner.current_diagnostics is None and not owner.commands.has_current_solution,
        "Restored inconsistent draft starts without diagnostics or solve authority",
    )
    rejected(
        owner,
        lambda: actions.prepare(owner, "remove_relation"),
        "Restored inconsistency does not weaken ordinary Remove",
    )
    recovery = actions.prepare(owner, "recover_remove_relation")
    check(
        recovery.requires_confirmation and "authored positions" in recovery.disclosure,
        "Recovery discloses authored seed policy",
    )
    rejected(owner, lambda: actions.apply(owner, context, recovery), "Unconfirmed recovery")
    authored = copy.deepcopy(owner.commands.sketch)
    preview = recovery._preview
    rejected(
        owner,
        lambda: actions.apply(
            owner, context, replace(recovery, _preview=replace(preview, points=(a,))), True
        ),
        "Recovery cannot include geometry cascade",
    )
    outcome = actions.apply(owner, context, recovery, confirmed=True)
    check(
        outcome.changed and outcome.relation_ids == (conflict,),
        "Explicit recovery removes exact relation",
    )
    after = owner.commands.sketch
    check(
        after["points"] == authored["points"] and after.get("circles") == authored.get("circles"),
        "Recovery preserves exact authored positions/radii",
    )
    check(after["lines"] == authored["lines"], "Recovery preserves all line IDs and references")
    check(
        after["constraints"]
        == [item for item in authored["constraints"] if item["id"] != conflict],
        "Recovery preserves every surviving relation/source",
    )
    check(not owner.commands.has_current_solution, "Recovery stays unverified before actual Check")
    wait(owner, context)
    check(dof(owner) == 0, "Native recovery returns actual zero DoF")
    select(owner, "constraint", here)
    rejected(
        owner,
        lambda: actions.prepare(owner, "recover_remove_relation"),
        "Current solution excludes recovery policy",
    )
    owner.local_history(context)
    wait(owner, context, success=False)
    owner.local_history(context, redo=True)
    wait(owner, context)
    check(
        scene.mechanical_cad.document_json == canonical,
        "All constraint actions leave canonical bytes unchanged before Finish",
    )

    # A new owner for an exact restored draft cannot inherit confirmation.
    select(owner, "point", a)
    stale = actions.prepare(owner, "fix_origin")
    saved = general_authoring_store.dumps(owner.draft)
    owner.suspend("transaction test restore")
    rejected(
        owner,
        lambda: actions.apply(owner, context, stale, True),
        "Retired owner rejects confirmation",
    )
    replacement = general_session.GeneralSession(
        context, restored=general_authoring_store.restore(saved, canonical)
    )
    replacement.start()
    check(
        sketch_session.active_session() is replacement,
        "Restored owner uses existing shared registry",
    )
    rejected(
        replacement,
        lambda: actions.apply(replacement, context, stale, True),
        "Replacement owner rejects prior confirmation",
    )
    replacement.check(context)
    wait(replacement, context)
    check(dof(replacement) == 0, "Restored authored draft revalidates through existing Check")
    with patch.object(workspace, "request_workspace"):
        replacement.request_finish(context)
        wait(replacement, context)
    check(
        replacement.finished and not replacement.alive,
        "Existing Finish path publishes and retires owner",
    )
    document = json.loads(scene.mechanical_cad.document_json)
    feature_id = document["features"][0]["id"]
    check(
        document["features"][0]["sketch"]["lines"] == after["lines"],
        "Finish preserves line identities",
    )
    document["features"].append(
        {
            "id": "constraint_pad",
            "kind": "extrude",
            "label": "Pad",
            "params": {"length": 7},
            "inputs": {"profile": feature_id},
        }
    )
    document["active_feature"] = "constraint_pad"
    document_state._commit_candidate(context, document, result_version=2)
    check(
        math.isclose(scene.mechanical_cad.volume, 60 * 20 * 7, rel_tol=1e-7),
        "Actual closed loop extrudes to analytic volume",
    )

    # Far-origin circle release also carries its current solved radius. The
    # current width formula deliberately differs from its original radius seed.
    document_state._populate_document(
        scene,
        {
            "schema_version": 1,
            "id": "constraint_circle_native",
            "name": "Far-origin circle constraints",
            "units": "mm",
            "parameters": {"radius": 5},
            "features": [],
            "active_feature": None,
        },
    )
    circle_canonical = scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(context)
    owner.start()
    owner.draft.begin_circle(PointSeed(800000, -900000), 8)
    center, circle = owner.accept_proposal(context)
    wait(owner, context)
    radius = owner.execute(context, AddRelation("radius", (circle,), value="radius")).constraint_id
    wait(owner, context)
    select(owner, "point", center)
    circle_fixed = perform(owner, context, "fix_here").constraint_id
    check(
        solved_points(owner)[center] == (800000, -900000), "Far-origin FixHere retains exact center"
    )
    owner.begin_dimension(radius)
    owner.update_raw("radius * 2")
    owner.request_driver_accept(context)
    wait(owner, context)
    select(owner, "constraint", circle_fixed)
    perform(owner, context, "remove_relation")
    check(dof(owner) == 2, "Circle center release exposes real translational DoF")
    check(
        solved_points(owner)[center] == (800000, -900000),
        "Circle release preserves far-origin center",
    )
    check(
        owner.commands.sketch["circles"][0]["radius"] == 10,
        "Circle release journals current solved radius",
    )
    check(
        next(item for item in owner.commands.sketch["constraints"] if item["id"] == radius)["value"]
        == "radius * 2",
        "Circle release preserves exact driving expression",
    )
    select(owner, "point", center)
    perform(owner, context, "fix_origin", confirmed=True)
    check(
        solved_points(owner)[center] == (0, 0) and dof(owner) == 0,
        "Explicit origin moves circle center with zero DoF",
    )
    check(
        scene.mechanical_cad.document_json == circle_canonical,
        "Circle actions remain local until Finish",
    )
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        wait(owner, context)
    circle_document = json.loads(scene.mechanical_cad.document_json)
    circle_feature = circle_document["features"][0]["id"]
    circle_document["features"].append(
        {
            "id": "circle_pad",
            "kind": "extrude",
            "params": {"length": 3},
            "inputs": {"profile": circle_feature},
        }
    )
    circle_document["active_feature"] = "circle_pad"
    document_state._commit_candidate(context, circle_document, result_version=2)
    check(
        math.isclose(scene.mechanical_cad.volume, math.pi * 100 * 3, rel_tol=1e-7),
        "Anchored circle retains analytic disk extrusion",
    )

unregister()
print("CONSTRAINT_ACTIONS_SMOKE_OK", len(checks))
