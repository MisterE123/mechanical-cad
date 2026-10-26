"""Actual guarded schema-3 Part/General ownership before visible arc tools.

Uses a declared fully constrained source fixture, not GUI drawing. Native geometry
qualification and later installed/manual authoring remain separate gates.
"""

import copy
import hashlib
import json
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
    assembly_operator_helpers,
    assembly_state,
    backend_runtime,
    draft_dispatch,
    execution_lease,
    general_session,
    geometry_operations,
    guarded_transport,
    part_contracts_v3,
    part_publication,
    register,
    unregister,
)
from mechanical_cad_blender import (  # noqa: E402
    document_state as doc,
)

checks, packets = [], {}
EVIDENCE = None
if os.environ.get("MCAD_ARC_OWNER_EVIDENCE"):
    EVIDENCE = Path(os.environ["MCAD_ARC_OWNER_EVIDENCE"])
    EVIDENCE.mkdir(parents=True, exist_ok=False)


def check(value, message):
    assert value, message
    checks.append(message)
    print("ARC_OWNER_CHECK", len(checks), message, flush=True)


def rejects(callback, message):
    try:
        callback()
    except (ValueError, RuntimeError):
        check(True, message)
    else:
        raise AssertionError(message)


def wait(owner, context, *, success=True):
    deadline = time.monotonic() + 60
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not execution_lease.is_busy(), "Native owner work collected")
    check(bool(owner.error) is not success, "Expected native owner action outcome: " + owner.error)


def capture(label, evidence):
    packets[label] = {
        "request": evidence.guarded_request(),
        "response": evidence.response_snapshot(),
    }
    if EVIDENCE is not None:
        with (EVIDENCE / (label + ".json")).open("x") as stream:
            json.dump(packets[label], stream, sort_keys=True, indent=2)
            stream.write("\n")


def current_part(label):
    current = doc.current_part_evidence(bpy.context)
    result = doc.current_part_result(bpy.context)
    check(current is not None and doc.part_is_current(bpy.context), label + " is current")
    evidence, _owner_token = current
    check(evidence.operation_request()["result_version"] == 3, label + " explicitly requests 3")
    check(result["result_version"] == 3, label + " retains typed result 3")
    check(not doc.geometry_report_is_current(bpy.context), label + " is no Geometry Check receipt")
    capture(label, evidence)
    return result


def authored_shape(document):
    sketch = document["features"][0]["sketch"]
    return copy.deepcopy({key: sketch[key] for key in ("points", "lines", "arcs", "circles")})


def trap(*_args, **_kwargs):
    raise AssertionError("Unsupported action reached mutable/native boundary")


register()
window = bpy.context.window
area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
region = next(item for item in area.regions if item.type == "WINDOW")
source_path = ROOT / "tests/fixtures/arc_authoring_evidence/radius_edit_5_0_replay.operation.json"
source = json.loads(source_path.read_text())["document"]
profile = copy.deepcopy(source)
profile["features"] = profile["features"][:1]
profile["active_feature"] = "profile"

with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    check(doc._commit_candidate(context, profile), "Fresh schema-3 profile publishes")
    result = current_part("profile")
    check(result["features"][0]["output"]["kind"] == "sketch", "Profile remains a typed sketch")
    check(doc._commit_candidate(context, source), "Sole schema-3 extrusion publishes")
    result = current_part("extrusion_radius5")
    check(
        abs(result["features"][1]["stats"]["volume"] - 196.34954084936206) < 1e-10,
        "Radius 5 native volume",
    )
    selected_profile = copy.deepcopy(source)
    selected_profile["active_feature"] = "profile"
    check(
        doc._commit_candidate(context, selected_profile),
        "Selected profile with downstream extrusion publishes",
    )
    result = current_part("selected_profile")
    check(
        result["active_feature"] == "profile" and result["features"][1]["status"] == "ok",
        "Selected profile does not discard downstream replay",
    )
    check(doc._commit_candidate(context, source), "Active extrusion restored by fresh replay")

    owner = general_session.GeneralSession(context, "profile")
    owner.start()
    owner.check(context)
    wait(owner, context)
    response = owner.current_solution_response()
    check(response["result_version"] == 3, "General retains genuine result-3 Check")
    check(
        response["result"]["sketch"]["remaining_dof"] == 0,
        "Declared constrained sector has real zero DoF",
    )
    check(owner.can_finish, "Checked ready sector may request distinct Finish")
    original = authored_shape(owner.commands.candidate())
    capture("general_check", owner.guarded_evidence)
    owner.begin_dimension("sector_radius")
    owner.update_raw("7")
    owner.request_driver_accept(context)
    wait(owner, context)
    check(
        owner.commands.pending_edit is None and owner.can_finish,
        "Radius accepted through complete solve/replay chain",
    )
    check(
        authored_shape(owner.commands.candidate()) == original,
        "Radius edit preserves every authored point and curve identity",
    )
    check(
        len(owner.commands._solution_evidence) == len(owner.commands._solution_prepared) == 2,
        "Consumed profile retains complete independently bound chain",
    )
    for index, evidence in enumerate(owner.commands._solution_evidence):
        prepared = owner.commands._solution_prepared[index]
        check(
            evidence.guarded_request() == prepared.guarded_request(),
            "Chain element retains exact prepared G",
        )
        capture("radius7_chain_" + str(index), evidence)
    clone = draft_dispatch.clone(owner.draft).command_draft
    owner._bind_commands(clone)
    clone.transfer_guarded_solution(owner.commands)
    check(
        all(
            left is right
            for left, right in zip(
                clone._solution_evidence, owner.commands._solution_evidence, strict=True
            )
        ),
        "Clone transfers original evidence objects",
    )
    check(
        all(
            left is right
            for left, right in zip(
                clone._solution_prepared, owner.commands._solution_prepared, strict=True
            )
        ),
        "Clone transfers original prepared G objects",
    )
    owner.request_finish(context)
    finish_prepared = owner.publication.prepared
    wait(owner, context)
    check(owner.finished, "Distinct fresh Finish closes accepted owner")
    result = current_part("extrusion_radius7")
    check(
        abs(result["features"][1]["stats"]["volume"] - 384.84510006474966) < 1e-10,
        "Radius 7 native volume",
    )
    check(
        doc.current_part_evidence(context)[0].guarded_request()
        == finish_prepared.guarded_request(),
        "Part Finish uses original prepared object without nonce remint",
    )
    check(
        authored_shape(doc._read_document(context.scene.mechanical_cad)) == original,
        "Committed radius edit preserves seeds and IDs",
    )
    check(not clone.has_current_solution, "Finished owner retires detached clone authority")

    state = context.scene.mechanical_cad
    before = doc._snapshot_fields(state)
    runtime = doc._RUNTIME[context.scene.as_pointer()]
    with (
        patch.object(guarded_transport, "execute", side_effect=trap),
        patch.object(execution_lease, "try_acquire", side_effect=trap),
    ):
        for action in ("check_geometry", "export_step", "export_stl"):
            check(
                doc._result_version(doc._read_document(state), action=action) == 3,
                "Eligible sector " + action + " selects explicit result3 without work",
            )
            check(
                doc._snapshot_fields(state) == before,
                "Geometry eligibility preserves all Part fields",
            )
            check(
                doc._RUNTIME[context.scene.as_pointer()] is runtime,
                "Geometry eligibility preserves the current replay association",
            )
        check(
            not doc.geometry_report_is_current(context),
            "Eligibility never upgrades replay to Geometry Check authority",
        )
        check(
            doc._result_version(doc._read_document(state), action="canonical_snapshot") is None,
            "Eligible sector capture has no result-version argument",
        )
    check(doc._snapshot_fields(state) == before, "Capture eligibility preserves Part state")

    # Actual RNA source variants cover profile-only, empty arcs and an inactive schema3
    # sketch. They have no prior authority and never launch native work.
    arc_empty = copy.deepcopy(source)
    arc_empty["features"][0]["sketch"]["arcs"] = []
    arc_empty["features"][0]["sketch"]["constraints"] = []
    inactive = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
    inactive["features"].append(copy.deepcopy(arc_empty["features"][0]))
    profile_only = copy.deepcopy(source)
    profile_only["features"].pop()
    profile_only["active_feature"] = profile_only["features"][0]["id"]
    original_scene = window.scene
    for label, variant in (
        ("profile_only", profile_only),
        ("arc_empty", arc_empty),
        ("inactive_schema3", inactive),
    ):
        target = bpy.data.scenes.new("Arc owner preflight " + label)
        try:
            window.scene = target
            doc._populate_document(target, variant)
            fields = doc._snapshot_fields(target.mechanical_cad)
            with (
                patch.object(guarded_transport, "execute", side_effect=trap),
                patch.object(execution_lease, "try_acquire", side_effect=trap),
            ):
                for action in ("check_geometry", "export_step", "export_stl"):
                    rejects(
                        lambda action=action: geometry_operations.run_geometry_action(
                            bpy.context,
                            action,
                            destination="/never-written/variant-negative.step"
                            if action != "check_geometry"
                            else None,
                        ),
                        label + " blocks " + action,
                    )
                rejects(
                    lambda: assembly_operator_helpers.canonical_working_part(bpy.context),
                    label + " blocks snapshot before lease",
                )
            check(
                doc._snapshot_fields(target.mechanical_cad) == fields,
                label + " preflight preserves all authored/report fields",
            )
        finally:
            window.scene = original_scene
            bpy.data.scenes.remove(target)

    assembly = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    unsupported_source = part_contracts_v3._expected_document(profile_only)
    assembly["part_sources"].append(
        {
            "source_document_id": unsupported_source["id"],
            "source_digest": part_contracts_v3.document_hash(unsupported_source),
            "document": unsupported_source,
        }
    )
    assembly_state_before = {
        field: getattr(context.scene.mechanical_cad_assembly, field)
        for field in assembly_state._STATE_FIELDS
    }
    with (
        patch.object(guarded_transport, "execute", side_effect=trap),
        patch.object(execution_lease, "try_acquire", side_effect=trap),
    ):
        rejects(
            lambda: assembly_state.commit_candidate(context, assembly),
            "Unused profile-only schema3 Assembly source rejects before work",
        )
    check(
        {
            field: getattr(context.scene.mechanical_cad_assembly, field)
            for field in assembly_state._STATE_FIELDS
        }
        == assembly_state_before,
        "Rejected Assembly candidate preserves accepted state/report",
    )

    candidate = doc._read_document(state)
    shared_owner = object()
    first = part_publication.prepare(context, candidate, owner_token=shared_owner)
    second = part_publication.prepare(context, candidate, owner_token=shared_owner)
    with doc.replay_guard(context):
        completion = guarded_transport.execute(
            first.prepared,
            first.selection,
            owner_token=shared_owner,
            current_selection=lambda: backend_runtime.capture(context),
        )
    check(
        first.prepared.operation_request() == second.prepared.operation_request(),
        "Wrong-nonce control has exactly identical O",
    )
    check(
        first.prepared.request_id != second.prepared.request_id,
        "Wrong-nonce control has distinct G",
    )
    before = state.document_json
    rejects(
        lambda: second.publish(context, completion),
        "Same-owner result3 completion cannot enter another prepared Finish",
    )
    check(state.document_json == before, "Wrong-nonce Finish preserves canonical bytes")
    check(completion.publication._state == "available", "Wrong G cannot consume another claim")
    first.retire()
    rejects(
        lambda: part_publication.PartPublicationIntent(
            context, first.prepared, first.selection, "", owner_token=shared_owner
        ),
        "A retired intent's PreparedRequest cannot be rewrapped",
    )
    rebuilt = part_publication.PartPublicationIntent(
        context, first.request, first.selection, "", owner_token=shared_owner
    )
    check(
        rebuilt.prepared.request_id != first.prepared.request_id,
        "Rebuilding identical O creates a distinct intent nonce",
    )
    rejects(
        lambda: rebuilt.publish(context, completion),
        "New intent cannot publish the retired intent's available completion",
    )
    check(completion.publication._state == "available", "Rebuilt intent leaves foreign claim alone")
    rejects(
        lambda: first.publish(context, completion), "Original retired intent rejects completion"
    )
    check(completion.publication._state == "cancelled", "Retired matching intent cancels its claim")
    check(state.document_json == before, "Retired-intent failures preserve canonical bytes")

    # A real schema3 publication reaches RNA/display and then observes settings
    # ABA. Rollback restores authored bytes without restoring revoked authority.
    rollback_intent = part_publication.prepare(context, candidate)
    with doc.replay_guard(context):
        rollback_evidence = guarded_transport.execute(
            rollback_intent.prepared,
            rollback_intent.selection,
            owner_token=rollback_intent.owner_token,
            current_selection=lambda: backend_runtime.capture(context),
        )
    original_display = doc._display_feature

    def revoke_after_display(*args, **kwargs):
        original_display(*args, **kwargs)
        backend_runtime.revoke("Arc publication A to B")
        backend_runtime.revoke("Arc publication B to A")

    with patch.object(doc, "_display_feature", side_effect=revoke_after_display):
        rejects(
            lambda: rollback_intent.publish(context, rollback_evidence),
            "Schema3 post-display ABA rejects publication",
        )
    check(state.document_json == before, "Schema3 ABA rollback preserves exact canonical bytes")
    check(
        doc.current_part_result(context) is None and not doc.part_is_current(context),
        "Rollback cannot revive revoked schema3 Part evidence",
    )
    check(
        doc._commit_candidate(context, candidate),
        "Fresh explicit replay recovers schema3 Part after rollback",
    )

    owner = general_session.GeneralSession(context, "profile")
    owner.start()
    owner.check(context)
    wait(owner, context)
    # Solver success and unsupported native radius are distinct outcomes. This
    # failed build keeps raw edit intent but cannot accept a driver or seeds.
    committed_before_failure = state.document_json
    owner.begin_dimension("sector_radius")
    owner.update_raw(" 0.5 ")
    raw_before_failure = owner.commands.pending_edit.raw_text
    owner.request_driver_accept(context)
    wait(owner, context, success=False)
    failure = owner.current_build_failure
    check(
        failure is not None and failure.solver_status == "okay" and failure.remaining_dof == 0,
        "Failed downstream retains genuine successful trial solve report",
    )
    check(bool(failure.failed_features), "Failed downstream retains exact native failure detail")
    capture("failed_radius_trial", owner._build_failure._solve_evidence[0])
    capture("failed_radius_replay", owner._build_failure._replay_evidence)
    check(
        owner.commands.pending_edit.raw_text == raw_before_failure,
        "Failed downstream preserves exact pending raw radius",
    )
    check(
        not owner.commands.has_current_solution
        and not owner.commands.has_verified_trial
        and not owner.can_finish,
        "Failed downstream supplies no seed, driver or Finish authority",
    )
    check(
        state.document_json == committed_before_failure,
        "Failed downstream does not publish candidate Part",
    )
    authored = draft_dispatch.dumps(owner.draft)
    backend_runtime.revoke("Arc owner ABA A to B")
    backend_runtime.revoke("Arc owner ABA B to A")
    check(
        owner.current_solution_response() is None and not owner.can_finish,
        "Arc owner ABA revokes solve and Finish",
    )
    check(owner.current_build_failure is None, "ABA retires the successful-trial failure report")
    check(
        draft_dispatch.dumps(owner.draft) == authored,
        "Arc owner revocation preserves exact envelope3 bytes",
    )
    check(not doc.part_is_current(context), "Arc Part association is revoked")
    owner.cleanup()

unregister()
check(not execution_lease.is_busy(), "All native owner leases collected")
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Native CAD remains outside Blender",
)
if EVIDENCE is not None:
    destination = EVIDENCE
    (destination / "packets.json").write_text(json.dumps(packets, sort_keys=True, indent=2) + "\n")
    (destination / "RESULT.json").write_text(
        json.dumps(
            {
                "checks": checks,
                "source_fixture_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "packet_count": len(packets),
                "gui_qualification": False,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
print("ARC_OWNER_SMOKE_OK", len(checks), flush=True)
