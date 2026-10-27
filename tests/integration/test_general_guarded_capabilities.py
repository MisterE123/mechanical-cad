"""General draft authority through fresh guarded native subprocesses.

These exercise runtime evidence and exact authoring bytes without importing bpy;
Blender owner/UI qualification remains in the dedicated native smoke scripts.
"""

import dataclasses
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("slvs")
pytest.importorskip("OCP")

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_general_guarded_native_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
contracts = importlib.import_module(PACKAGE + ".backend_contracts")
selection_module = importlib.import_module(PACKAGE + ".backend_selection")
transport = importlib.import_module(PACKAGE + ".guarded_transport")
diagnostics = importlib.import_module(PACKAGE + ".constraint_diagnostics")
geometry = importlib.import_module(PACKAGE + ".general_view_geometry")
pending = importlib.import_module(PACKAGE + ".sketch_pending")

LINUX_MANUAL_PROCESS = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux manual capture and native guarded subprocess contract"
)


def selection(generation=0):
    return selection_module.BackendSelection.capture(
        str(ROOT),
        sys.executable,
        generation=generation,
        lifetime_id="general-guarded-tests",
    )


def circle(*, consumed=False):
    base = json.dumps(
        {
            "schema_version": 1,
            "id": "general_guarded",
            "name": "Guarded tests",
            "units": "mm",
            "parameters": {"radius": 5},
            "features": [],
            "active_feature": None,
        }
    )
    draft = d.GeneralSketchDraft(base)
    center, rim = draft.execute(d.AddCircle(d.PointSeed(2, 3), 8)).entity_ids
    driver = draft.execute(d.AddRelation("radius", (rim,), value="radius")).constraint_id
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(10, 20))).constraint_id
    if consumed:
        document = draft.candidate()
        document["features"].append(
            {
                "id": "pad",
                "kind": "extrude",
                "params": {"length": 10},
                "inputs": {"profile": draft.feature_id},
            }
        )
        document["active_feature"] = "pad"
        draft = d.GeneralSketchDraft(json.dumps(document), draft.feature_id, True)
    return draft, driver, fixed


def bind(draft, current=None, owner=None):
    current = [selection()] if current is None else current
    owner = object() if owner is None else owner
    draft.bind_guarded(owner, lambda: current[0])
    return current, owner


def execute(request, current, owner):
    prepared = contracts.prepare_request(request)
    evidence = transport.execute(
        prepared,
        current[0],
        owner_token=owner,
        current_selection=lambda: current[0],
    )
    return prepared, evidence


def solve(draft, current, owner, *, trial=False):
    prepared, evidence = execute(draft.solve_request(trial=trial), current, owner)
    options = {"expected_input_revision": draft.pending_edit.input_revision} if trial else {}
    success = draft.record_guarded_solution(
        evidence, draft.revision, expected_prepared=prepared, **options
    )
    return prepared, evidence, success


def checkpoint(draft):
    return json.dumps(draft.checkpoint_payload(), sort_keys=True, separators=(",", ":"))


def clone(draft):
    return d.GeneralSketchDraft.from_checkpoint_payload(draft.checkpoint_payload())


@LINUX_MANUAL_PROCESS
def test_bound_draft_rejects_matching_legacy_success_without_authored_changes():
    draft, _, _ = circle()
    current, owner = bind(draft)
    prepared, evidence = execute(draft.solve_request(), current, owner)
    before = checkpoint(draft)
    response = evidence.revalidate(current[0], owner_token=owner)
    with pytest.raises(d.DraftError, match="guarded evidence"):
        draft.record_validated_solution(evidence.operation_request(), response, draft.revision)
    assert not draft.has_current_solution
    assert checkpoint(draft) == before
    assert draft.record_guarded_solution(evidence, draft.revision, expected_prepared=prepared)
    assert checkpoint(draft) == before
    assert draft.has_current_solution
    with pytest.raises(d.DraftError, match="guarded evidence"):
        draft.record_validated_solution(evidence.operation_request(), response, draft.revision)
    draft.invalidate_solution()
    with pytest.raises(d.DraftError, match="guarded evidence"):
        draft.record_validated_solution(evidence.operation_request(), response, draft.revision)
    assert not draft.has_current_solution and checkpoint(draft) == before


@LINUX_MANUAL_PROCESS
def test_same_owner_clone_retains_original_evidence_and_rejects_other_owner():
    draft, _, _ = circle()
    current, owner = bind(draft)
    prepared, evidence, success = solve(draft, current, owner)
    assert success
    copy = clone(draft)
    bind(copy, current, owner)
    copy.transfer_guarded_solution(draft)
    assert copy._solution_evidence[0] is evidence
    assert copy._solution is draft._solution
    assert copy.has_current_solution
    assert checkpoint(copy) == checkpoint(draft)
    other = clone(draft)
    bind(other, current)
    with pytest.raises(d.DraftError, match="another owner"):
        other.transfer_guarded_solution(draft)
    with pytest.raises(ValueError, match="owner"):
        other.record_guarded_solution(evidence, other.revision, expected_prepared=prepared)
    assert not other.has_current_solution
    assert not clone(draft).has_current_solution
    copy.retire_guarded()
    assert copy._current_selection is None
    assert not copy.has_current_solution
    with pytest.raises(d.DraftError, match="guarded evidence"):
        copy.record_validated_solution(
            evidence.operation_request(),
            evidence.revalidate(current[0], owner_token=owner),
            copy.revision,
        )


@LINUX_MANUAL_PROCESS
def test_generation_aba_retires_solved_seed_and_preserves_every_authored_byte():
    draft, _, fixed = circle()
    current, owner = bind(draft)
    prepared, evidence, _ = solve(draft, current, owner)
    copy = clone(draft)
    bind(copy, current, owner)
    copy.transfer_guarded_solution(draft)
    before = checkpoint(draft), checkpoint(copy)
    current[0] = dataclasses.replace(current[0], generation=2)
    assert not draft.has_current_solution and not copy.has_current_solution
    with pytest.raises(d.DraftError):
        draft.execute(d.DeleteBatch(draft.preview_delete((("constraint", fixed),))))
    assert (checkpoint(draft), checkpoint(copy)) == before
    assert draft._solution_evidence is None and copy._solution_evidence is None
    with pytest.raises(ValueError, match="settings|lifetime"):
        geometry.build_guarded_geometry(
            draft.sketch,
            evidence,
            expected_prepared=prepared,
            current_selection=current[0],
            owner_token=owner,
        )


@LINUX_MANUAL_PROCESS
def test_generation_change_during_acceptance_cannot_retain_current_solution():
    draft, _, _ = circle()
    current, owner = bind(draft)
    prepared, evidence = execute(draft.solve_request(), current, owner)
    selected = current[0]
    observations = iter((selected, dataclasses.replace(selected, generation=1)))
    draft._current_selection = lambda: next(observations)
    before = checkpoint(draft)
    with pytest.raises(ValueError):
        draft.record_guarded_solution(evidence, draft.revision, expected_prepared=prepared)
    draft._current_selection = lambda: selected
    assert not draft.has_current_solution
    assert checkpoint(draft) == before


@LINUX_MANUAL_PROCESS
def test_failed_guarded_diagnostics_keep_scalar_snapshot_and_revoke_on_aba():
    draft, _, _ = circle()
    rim = draft.sketch["circles"][0]["id"]
    draft.execute(d.AddRelation("radius", (rim,), value=9))
    current, owner = bind(draft)
    prepared, evidence, success = solve(draft, current, owner)
    assert not success
    bindings = dict(
        session_id="native-owner",
        command_revision=draft.revision,
        input_token="",
        input_revision=None,
    )
    wrapper = diagnostics.FailureDiagnostics.from_guarded(
        evidence,
        expected_prepared=prepared,
        current_selection=current[0],
        owner_token=owner,
        **bindings,
    )
    snapshot = wrapper.for_current(
        draft.solve_request(),
        current_selection=current[0],
        owner_token=owner,
        **bindings,
    )
    assert type(snapshot) is diagnostics.FailureDiagnostics
    assert snapshot.candidate_constraint_ids
    assert all(
        type(getattr(snapshot, field.name)) in (str, int, tuple, type(None))
        for field in dataclasses.fields(snapshot)
    )
    assert (
        snapshot.for_current(
            draft.solve_request(),
            current_selection=current[0],
            owner_token=owner,
            **bindings,
        )
        is None
    )
    altered = evidence.revalidate(current[0], owner_token=owner)
    altered["error"]["message"] = "A different unguarded diagnostic"
    injected = diagnostics.FailureDiagnostics(altered, draft.solve_request(), **bindings)
    forged = dataclasses.replace(wrapper, snapshot=injected)
    assert (
        forged.for_current(
            draft.solve_request(),
            current_selection=current[0],
            owner_token=owner,
            **bindings,
        )
        is None
    )
    current[0] = dataclasses.replace(current[0], generation=2)
    assert (
        wrapper.for_current(
            draft.solve_request(),
            current_selection=current[0],
            owner_token=owner,
            **bindings,
        )
        is None
    )
    assert not draft.has_current_solution


@LINUX_MANUAL_PROCESS
def test_downstream_trial_mixed_generations_reject_without_changing_raw_input():
    draft, driver, _ = circle(consumed=True)
    current, owner = bind(draft)
    draft.begin_edit(driver)
    draft.update_edit("  radius + 2  ")
    _, _, success = solve(draft, current, owner, trial=True)
    assert success and draft.has_verified_trial
    before = checkpoint(draft)
    current[0] = dataclasses.replace(current[0], generation=1)
    replay_prepared, replay = execute(draft.replay_request(trial=True), current, owner)
    with pytest.raises(d.DraftError, match="Check this exact"):
        draft.accept_driver(replay_evidence=replay, replay_prepared=replay_prepared)
    assert checkpoint(draft) == before
    assert draft.pending_edit.raw_text == "  radius + 2  "
    assert not draft.has_current_solution and not draft.has_verified_trial


@LINUX_MANUAL_PROCESS
def test_downstream_chain_survives_exact_clone_and_is_revalidated_together():
    draft, driver, _ = circle(consumed=True)
    current, owner = bind(draft)
    draft.begin_edit(driver)
    draft.update_edit("radius + 2")
    trial_prepared, trial, success = solve(draft, current, owner, trial=True)
    assert success
    replay_prepared, replay = execute(draft.replay_request(trial=True), current, owner)
    with pytest.raises(d.DraftError, match="retained guarded"):
        draft.accept_driver(
            replay_request=replay.operation_request(),
            replay_response=replay.revalidate(current[0], owner_token=owner),
        )
    draft.accept_driver(replay_evidence=replay, replay_prepared=replay_prepared)
    copy = clone(draft)
    bind(copy, current, owner)
    copy.transfer_guarded_solution(draft)
    assert copy._solution_evidence == (trial, replay)
    assert copy._solution_prepared == (trial_prepared, replay_prepared)
    assert copy._solution_prepared[0] is trial_prepared
    assert copy._solution_prepared[1] is replay_prepared
    assert copy._solution_evidence[0] is trial and copy._solution_evidence[1] is replay
    assert copy._solution is draft._solution
    assert copy.has_current_solution and draft.has_current_solution
    before = checkpoint(draft), checkpoint(copy)
    replay.publication.cancel()
    assert not copy.has_current_solution and not draft.has_current_solution
    assert (checkpoint(draft), checkpoint(copy)) == before


@LINUX_MANUAL_PROCESS
def test_snapshot_and_type_changed_authored_numbers_cannot_enter_solved_sink():
    draft, _, _ = circle()
    current, owner = bind(draft)
    snapshot_prepared, snapshot = execute(
        {"protocol_version": 1, "action": "canonical_snapshot", "document": draft.candidate()},
        current,
        owner,
    )
    with pytest.raises(ValueError, match="action"):
        draft.record_guarded_solution(snapshot, draft.revision, expected_prepared=snapshot_prepared)
    prepared, evidence, _ = solve(draft, current, owner)
    authored = draft.sketch
    value = authored["points"][0]["u"]
    authored["points"][0]["u"] = float(value) if type(value) is int else int(value)
    with pytest.raises(ValueError, match="authored sketch"):
        geometry.build_guarded_geometry(
            authored,
            evidence,
            expected_prepared=prepared,
            current_selection=current[0],
            owner_token=owner,
        )


@LINUX_MANUAL_PROCESS
def test_guarded_pending_old_cleanup_cannot_consume_or_release_new_lease():
    draft, _, _ = circle()
    current, owner = bind(draft)
    prepared = contracts.prepare_request(draft.solve_request())
    old = pending.prepare_guarded(
        prepared, {"owner": "old"}, selection=current[0], owner_token=owner
    )
    try:
        assert old._job.wait(15)
        newer_selection = dataclasses.replace(current[0], generation=2)
        with pytest.raises(pending.bridge.BridgeError, match="settings|lifetime"):
            pending.poll(old, {"owner": "old"}, current_selection=newer_selection)
        assert not pending.execution_lease.is_busy()
        fresh = pending.prepare_guarded(
            contracts.prepare_request(draft.solve_request()),
            {"owner": "fresh"},
            selection=newer_selection,
            owner_token=owner,
        )
        assert not pending.cancel(old)
        pending.reap()
        assert pending.execution_lease.is_busy()
        assert fresh._job.wait(15)
        accepted = pending.poll(fresh, {"owner": "fresh"}, current_selection=newer_selection)
        assert accepted.revalidate(newer_selection, owner_token=owner)["ok"]
        assert not pending.execution_lease.is_busy()
    finally:
        assert pending.cancel_all(wait_timeout=15)
