"""Gate-B General owners with unchanged recorded inners and synthetic transport.

No OCP, SolveSpace, Blender or native child is launched. Modified failure reports
below are explicitly synthetic protocol controls, never native failure evidence.
"""

import copy
import importlib
import json
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_general_arc_owner_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package


def module(name):
    return importlib.import_module(PACKAGE + "." + name)


contracts = module("backend_contracts")
selections = module("backend_selection")
e = module("guarded_evidence")
d = module("general_sketch_draft")
p = module("sketch_pending")
g = module("general_view_geometry")
diagnostics = module("constraint_diagnostics")
policy = module("operation_contracts")
dispatch = module("draft_dispatch")
authoring = module("general_authoring")


def recorded(version, action="solve_sketch"):
    if version == 3:
        root = ROOT / "tests/fixtures/arc_authoring_evidence"
        name = "radius_edit_5_0_" + action
        request = json.loads((root / (name + ".operation.json")).read_text())
        response = json.loads((root / (name + ".response")).read_text())
    elif action == "replay":
        root = ROOT / "tests/fixtures/arc_authoring_evidence"
        request = json.loads((root / "rectangle_replay2.request.raw").read_text())
        request.pop("backend_contract")
        response = json.loads((root / "rectangle_replay2.response.raw").read_text())
    else:
        root = ROOT / "tests/fixtures/result_v3/legacy_30383a1"
        name = ("solve" if action == "solve_sketch" else "replay") + "_viewport_rectangle"
        request = json.loads((root / (name + ".request.txt")).read_text())
        response = json.loads((root / (name + ".stdout.txt")).read_text())
    return request, contracts.project_response(response)


def selection():
    return selections.BackendSelection.capture(
        str(ROOT),
        sys.executable,
        generation=5,
        lifetime_id="synthetic-general-test-port",
        environment={},
    )


def accepted(request, inner, selected, owner, *, prepared=None):
    prepared = contracts.prepare_request(request) if prepared is None else prepared
    required = prepared.guarded_request()["backend_contract"]["required_capabilities"]
    response = {
        **copy.deepcopy(inner),
        "backend_receipt": {
            "version": 1,
            "request_id": prepared.request_id,
            "request_fingerprint": prepared.fingerprint,
            "required_capabilities": required,
            "confirmed_capabilities": required[:],
            "missing_capabilities": [],
            "phase": "dispatched",
            "backend": {
                "core_version": "synthetic-port-only",
                "project_root": selected.project_root,
                "core_origin": selected.core_origin,
                "solver_origin": str(Path(selected.core_origin) / "sketch_solver.py"),
                "python_executable": selected.python_executable,
                "python_executable_target": selected.python_executable_target,
                "python_prefix": "/synthetic/prefix",
                "python_base_prefix": "/synthetic/base",
                "python_version": [3, 12, 14],
            },
        },
    }
    return prepared, e.accept_response(prepared, response, selected, owner_token=owner)


def draft_case(version):
    request, inner = recorded(version)
    draft = d.GeneralSketchDraft(
        json.dumps(request["document"]),
        request["feature_id"],
        True,
        journal_version=3 if version == 3 else 2,
    )
    current, owner = [selection()], object()
    draft.bind_guarded(owner, lambda: current[0])
    assert draft.solve_request() == request
    return draft, request, inner, current, owner


def trial_case(version):
    draft, request, inner, current, owner = draft_case(version)
    relation = next(
        item for item in draft.sketch["constraints"] if item["kind"] in {"radius", "distance"}
    )
    draft.begin_edit(relation["id"])
    draft.update_edit(" " + draft.pending_edit.raw_text + " ")
    assert draft.solve_request(trial=True) == request
    prepared, evidence = accepted(request, inner, current[0], owner)
    evidence.publication.consume(
        current[0],
        owner_token=owner,
        expected_action="solve_sketch",
        expected_result_version=version,
    )
    assert draft.record_guarded_solution(
        evidence,
        draft.revision,
        expected_prepared=prepared,
        expected_input_revision=draft.pending_edit.input_revision,
    )
    return draft, current, owner, prepared, evidence


@pytest.mark.parametrize("version", [2, 3])
def test_initial_exact_G_positive_and_same_O_new_nonce_rejection(version):
    draft, request, inner, current, owner = draft_case(version)
    expected = contracts.prepare_request(request)
    other, substitute = accepted(request, inner, current[0], owner)
    before = draft.checkpoint_payload()
    assert expected.request_id != other.request_id
    with pytest.raises(d.DraftError, match="exact prepared"):
        draft.record_guarded_solution(substitute, draft.revision, expected_prepared=expected)
    assert not draft.has_current_solution and draft.checkpoint_payload() == before
    _, evidence = accepted(request, inner, current[0], owner, prepared=expected)
    assert draft.record_guarded_solution(evidence, draft.revision, expected_prepared=expected)
    assert draft.has_current_solution and draft._solution_prepared[0] is expected
    with pytest.raises(TypeError):
        draft.record_guarded_solution(evidence, draft.revision)


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("substitution", ["solve", "replay", "owner", "generation"])
def test_entire_clone_chain_preserves_original_G_and_retires_substitution(version, substitution):
    draft, current, owner, prepared, evidence = trial_case(version)
    replay, inner = recorded(version, "replay")
    expected2, evidence2 = accepted(replay, inner, current[0], owner)
    evidence2.publication.consume(
        current[0],
        owner_token=owner,
        expected_action="replay",
        expected_result_version=version,
        require_success=True,
    )
    before_points = draft.sketch["points"]
    draft.accept_driver(replay_evidence=evidence2, replay_prepared=expected2)
    assert draft.has_current_solution and draft.sketch["points"] == before_points
    clone = d.GeneralSketchDraft.from_checkpoint_payload(
        draft.checkpoint_payload(), expected_journal_version=draft.journal_version
    )
    clone.bind_guarded(owner, lambda: current[0])
    clone.transfer_guarded_solution(draft)
    assert clone._solution_evidence is draft._solution_evidence
    assert clone._solution_prepared is draft._solution_prepared
    assert clone._solution is draft._solution
    if substitution in {"solve", "replay", "owner"}:
        index = int(substitution == "replay")
        request, inner = recorded(version, "replay" if index else "solve_sketch")
        _, changed = accepted(
            request, inner, current[0], object() if substitution == "owner" else owner
        )
        chain = list(clone._solution_evidence)
        chain[index] = changed
        clone._solution_evidence = tuple(chain)
    else:
        old = current[0]
        current[0] = replace(old, generation=old.generation + 1)
    assert not clone.has_current_solution
    assert clone._solution_evidence is clone._solution_prepared is None
    if substitution == "generation":
        current[0] = old
    assert not clone.has_current_solution


@pytest.mark.parametrize("version", [2, 3])
def test_wrong_downstream_nonce_retains_raw_driver_without_acceptance(version):
    draft, current, owner, _, _ = trial_case(version)
    replay, inner = recorded(version, "replay")
    expected = contracts.prepare_request(replay)
    _, other = accepted(replay, inner, current[0], owner)
    before = draft.checkpoint_payload()
    with pytest.raises(d.DraftError, match="exact prepared"):
        draft.accept_driver(replay_evidence=other, replay_prepared=expected)
    assert draft.checkpoint_payload() == before and draft.pending_edit is not None
    assert not draft.has_current_solution


class CompletionPort:
    """Returns typed recorded evidence for a configured captured G, no process."""

    returned = None

    def __init__(self, prepared, selected, *, owner_token):
        self.prepared, self.selected, self.owner = prepared, selected, owner_token
        self.state, self.done = "created", False

    def start(self, selected):
        self.state, self.done = "ready", True

    def poll(self, selected):
        return self.state

    def request_snapshot(self):
        return self.prepared.guarded_request()

    def result(self, selected, *, owner_token):
        self.state = "consumed"
        return self.returned

    def cancel(self):
        self.state, self.done = "cancelled", True


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("action", ["solve_sketch", "replay"])
@pytest.mark.parametrize("substitute", [False, True])
def test_pending_compares_returned_full_G_before_owner_claim(
    monkeypatch, version, action, substitute
):
    request, inner = recorded(version, action)
    selected, owner = selection(), object()
    prepared = contracts.prepare_request(request)
    _, evidence = accepted(
        request, inner, selected, owner, prepared=None if substitute else prepared
    )
    monkeypatch.setattr(CompletionPort, "returned", evidence)
    monkeypatch.setattr(p, "_GUARDED_JOB_FACTORY", CompletionPort)
    pending = p.prepare_guarded(prepared, {"owner": "same"}, selection=selected, owner_token=owner)
    if substitute:
        with pytest.raises(p.bridge.BridgeError, match="exact prepared"):
            p.poll(pending, {"owner": "same"}, current_selection=selected)
    else:
        assert p.poll(pending, {"owner": "same"}, current_selection=selected) is evidence
        assert p.poll(pending, {"owner": "same"}, current_selection=selected) is None
    assert pending.done and not p.execution_lease.is_busy()
    if not substitute:
        evidence.publication.consume(
            selected, owner_token=owner, expected_action=action, expected_result_version=version
        )
    with pytest.raises(ValueError, match="no longer available"):
        evidence.publication.consume(
            selected, owner_token=owner, expected_action=action, expected_result_version=version
        )


@pytest.mark.parametrize("version", [2, 3])
def test_display_requires_exact_G_and_retained_outline_has_no_fingerprint(version):
    draft, request, inner, current, owner = draft_case(version)
    prepared, evidence = accepted(request, inner, current[0], owner)
    display = g.build_guarded_geometry(
        draft.sketch,
        evidence,
        expected_prepared=prepared,
        current_selection=current[0],
        owner_token=owner,
    )
    assert display.source == "solved" and display.request_fingerprint
    retained = g.retained_outline(display)
    assert retained.source == "retained" and retained.request_fingerprint is None
    if version == 3:
        assert display.arcs["rim"].radius_mm == 5 and display.arcs["rim"].end_id == "end"
        assert display.arcs["rim"].direction == "ccw"
    with pytest.raises(ValueError, match="exact prepared"):
        g.build_guarded_geometry(
            draft.sketch,
            evidence,
            expected_prepared=contracts.prepare_request(request),
            current_selection=current[0],
            owner_token=owner,
        )


def synthetic_failed_replay(version):
    """Synthetic native-build failure shape; no native failure is asserted here."""
    request, inner = recorded(version, "replay")
    inner["ok"], inner["result"]["status"] = False, "failed"
    for index, item in enumerate(inner["result"]["features"]):
        item.update(
            status="failed" if index == 0 else "blocked",
            stats=None,
            mesh=None,
            topology=[],
            output=None,
            error={
                "code": "synthetic_native_failure" if index == 0 else "upstream_failed",
                "message": "Synthetic native interval failure" if index == 0 else "Upstream failed",
            },
        )
    assert policy.validate_response(request, inner) == inner
    return request, inner


@pytest.mark.parametrize("version", [2, 3])
def test_runtime_build_attempt_keeps_truthful_solve_facts_without_seed_authority(version):
    draft, current, owner, prepared, evidence = trial_case(version)
    request, inner = synthetic_failed_replay(version)
    replay_prepared, failed = accepted(request, inner, current[0], owner)
    binding = dict(
        session_id="session",
        command_revision=draft.revision,
        input_token="input",
        input_revision=draft.pending_edit.input_revision,
    )
    report = diagnostics.GuardedBuildFailure.from_guarded(
        (evidence,),
        (prepared,),
        failed,
        replay_prepared,
        current_selection=current[0],
        owner_token=owner,
        **binding,
    )
    failed.publication.consume(
        current[0],
        owner_token=owner,
        expected_action="replay",
        expected_result_version=version,
        require_success=False,
    )
    draft.invalidate_solution()
    snapshot = report.for_current(
        draft.solve_request(trial=True), current_selection=current[0], owner_token=owner, **binding
    )
    assert snapshot.remaining_dof == 0 and snapshot.solver_status == "okay"
    assert snapshot.profile_ready and snapshot.failed_features[0][1] == "synthetic_native_failure"
    assert not hasattr(snapshot, "points") and not hasattr(snapshot, "publication")
    assert not draft.has_verified_trial and not draft.has_current_solution
    assert (
        report.for_current(
            draft.solve_request(trial=True),
            current_selection=current[0],
            owner_token=owner,
            **{**binding, "input_token": "changed"},
        )
        is None
    )
    assert (
        report.for_current(
            draft.solve_request(trial=True),
            current_selection=replace(current[0], generation=99),
            owner_token=owner,
            **binding,
        )
        is None
    )


def unexpected_recovery_discard(*_args, **_kwargs):
    raise AssertionError("Evidence-owner tests must not discard recovery storage")


@pytest.fixture
def session_module(monkeypatch):
    """Import the real owner with inert Blender integration ports, no bpy import."""
    stubs = {
        "assembly_job_ui": {"ensure_supervisor": lambda: None},
        "backend_runtime": {
            "assert_current": lambda selected, context: selected,
            "configuration": lambda context: (context.selection, 0.1),
        },
        "document_state": {"_REPLAY_RUNNING": False},
        "part_publication": {},
        # Recovery storage is outside these evidence-owner tests. Fail loudly
        # if a tested path unexpectedly tries to mutate a recovery checkpoint.
        "staged_edit_store": {"discard": unexpected_recovery_discard},
        "sketch_view_presentation": {},
        "workspace": {},
        "common": {"_state": lambda context: context.scene.mechanical_cad},
        "display": {"_focus_display": lambda *args: None},
        "sketch_session": {
            "SketchSession": type("SketchSession", (), {}),
            "_discard_stored": lambda *args: None,
            "_tag_redraw": lambda *args: None,
        },
    }
    for name, fields in stubs.items():
        stub = types.ModuleType(PACKAGE + "." + name)
        stub.__dict__.update(fields)
        monkeypatch.setitem(sys.modules, stub.__name__, stub)
        monkeypatch.setattr(package, name, stub, raising=False)
    sys.modules.pop(PACKAGE + ".general_session", None)
    return module("general_session")


def owner_for(session_module, draft, current, token, *, wrapped=False):
    import weakref

    owner = object.__new__(session_module.GeneralSession)
    if wrapped:
        wrapper = authoring.GeneralSketchAuthoringState(
            draft, ui_version=2 if draft.journal_version == 3 else 1
        )
    else:
        wrapper = types.SimpleNamespace(
            command_draft=draft, proposal=None, document_json=draft.document_json
        )
    owner.draft, owner.owner_token = wrapper, token
    owner._bound_commands = weakref.WeakSet()
    owner._backend_current_selection = lambda: current[0]
    owner._bind_commands(owner.commands)
    owner.alive, owner.session_id = False, "test-session"
    owner.pending, owner.pending_kind, owner.pending_prepared = None, "", None
    owner.guarded_evidence = owner.expected_prepared = None
    owner.evidence_request = owner.evidence_response = None
    owner.trial_evidence = owner.trial_prepared = None
    owner.publication = owner.input_controller = None
    owner._failure_diagnostics = owner._build_failure = None
    owner.input_token, owner.message, owner.error = "test-input", "", ""
    owner.geometry_cache = owner.geometry_key = None
    owner.retained_outline = owner.retained_revision = None
    owner.stored_snapshot = dispatch.dumps(wrapper) if wrapped else "original-slot"
    state = types.SimpleNamespace(
        sketch_draft_json=owner.stored_snapshot, document_json=draft.document_json
    )
    owner.scene = types.SimpleNamespace(mechanical_cad=state)

    def require_current():
        if state.sketch_draft_json != owner.stored_snapshot:
            raise d.DraftError("Saved slot changed")

    owner._require_current = require_current
    owner._require_idle = require_current
    owner.identity = lambda context, selection: {"owner": "test-session"}
    return owner


@pytest.mark.parametrize("version", [2, 3])
def test_session_checks_its_prepared_G_even_if_completion_adapter_is_bypassed(
    session_module, monkeypatch, version
):
    draft, request, inner, current, token = draft_case(version)
    owner = owner_for(session_module, draft, current, token)
    expected = contracts.prepare_request(request)
    _, substitute = accepted(request, inner, current[0], token)
    owner.pending = types.SimpleNamespace(selection=current[0], request_snapshot=lambda: request)
    owner.pending_kind, owner.pending_prepared = "solve", expected
    monkeypatch.setattr(p, "poll", lambda *args, **kwargs: substitute)
    monkeypatch.setattr(p, "cancel", lambda *args, **kwargs: None)
    owner.tick(types.SimpleNamespace(selection=current[0]))
    assert not owner.commands.has_current_solution and owner.guarded_evidence is None
    assert "exact prepared" in owner.error
    # Unaccepted available claims are revoked rather than recycled.
    with pytest.raises(ValueError, match="cancelled"):
        substitute.revalidate(current[0], owner_token=token, expected_result_version=version)


@pytest.mark.parametrize("version", [2, 3])
def test_session_failed_downstream_retains_raw_and_only_attempt_report(
    session_module, monkeypatch, version
):
    draft, current, token, prepared, evidence = trial_case(version)
    owner = owner_for(session_module, draft, current, token)
    # Binding the owner retires prior command authority; reacquire the exact original association.
    owner.commands.record_guarded_solution(
        evidence,
        draft.revision,
        expected_prepared=prepared,
        expected_input_revision=draft.pending_edit.input_revision,
    )
    request, inner = synthetic_failed_replay(version)
    expected2, failed = accepted(request, inner, current[0], token)
    before = owner.commands.checkpoint_payload()
    owner.pending = types.SimpleNamespace(selection=current[0], request_snapshot=lambda: request)
    owner.pending_kind, owner.pending_prepared = "downstream", expected2
    owner.trial_evidence, owner.trial_prepared = evidence, prepared
    monkeypatch.setattr(p, "poll", lambda *args, **kwargs: failed)
    owner.tick(types.SimpleNamespace(selection=current[0]))
    assert owner.commands.checkpoint_payload() == before
    assert owner.commands.pending_edit is not None and not owner.commands.has_verified_trial
    assert owner.trial_evidence is owner.trial_prepared is None
    assert owner.current_build_failure.remaining_dof == 0
    assert (
        "Trial solve succeeded" in owner.message and "Native construction failed" in owner.message
    )
    assert owner.evidence_response is None and owner.guarded_evidence is None
    owner.commands.update_edit("changed")
    assert owner.current_build_failure is None
    owner.commands.update_edit(before["pending_edit"]["raw_text"])
    assert owner.current_build_failure is None


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("external_slot", [False, True])
def test_checkpoint_backend_ABA_restores_pending_bytes_without_overwriting_external_slot(
    session_module, version, external_slot
):
    draft, current, token, prepared, evidence = trial_case(version)
    owner = owner_for(session_module, draft, current, token, wrapped=True)
    commands = owner.commands
    commands.record_guarded_solution(
        evidence,
        commands.revision,
        expected_prepared=prepared,
        expected_input_revision=commands.pending_edit.input_revision,
    )
    replay, inner = recorded(version, "replay")
    expected2, evidence2 = accepted(replay, inner, current[0], token)
    old_draft, old_slot = owner.draft, owner.stored_snapshot
    old_commands = commands.checkpoint_payload()

    def checkpoint():
        value = dispatch.dumps(owner.draft)
        owner.scene.mechanical_cad.sketch_draft_json = value
        owner.stored_snapshot = value
        current[0] = replace(current[0], generation=current[0].generation + 2)
        if external_slot:
            owner.scene.mechanical_cad.sketch_draft_json = "external replacement"
        return value

    owner.checkpoint = checkpoint
    with pytest.raises(ValueError):
        owner._accepted_driver(
            evidence,
            expected_prepared=prepared,
            replay_evidence=evidence2,
            replay_prepared=expected2,
        )
    assert owner.draft is old_draft and owner.commands.checkpoint_payload() == old_commands
    assert owner.commands.pending_edit is not None and owner.stored_snapshot == old_slot
    assert owner.scene.mechanical_cad.sketch_draft_json == (
        "external replacement" if external_slot else old_slot
    )
    assert not owner.commands.has_verified_trial and not owner.commands.has_current_solution


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("target", ["evidence", "prepared"])
def test_incomplete_exact_class_reconstruction_fails_closed(version, target):
    draft, request, inner, current, owner = draft_case(version)
    expected, evidence = accepted(request, inner, current[0], owner)
    draft.record_guarded_solution(evidence, draft.revision, expected_prepared=expected)
    if target == "evidence":
        draft._solution_evidence = (object.__new__(e.GuardedEvidence),)
    else:
        draft._solution_prepared = (object.__new__(contracts.PreparedRequest),)
    assert not draft.has_current_solution
    assert draft._solution_evidence is draft._solution_prepared is None


@pytest.mark.parametrize("version", [2, 3])
def test_guarded_failed_solve_diagnostics_require_independent_G_and_no_intrinsic_arc_id(version):
    draft, request, inner, current, owner = draft_case(version)
    report = inner["result"]["sketch"]
    failed_id = request["document"]["features"][0]["sketch"]["constraints"][0]["id"]
    inner.update(
        ok=False, error={"code": "sketch_solve_failed", "message": "Synthetic inconsistent solver"}
    )
    inner["result"]["profile_check"] = None
    report.update(
        status="inconsistent",
        remaining_dof=None,
        solved=None,
        max_residual_mm=None,
        failed_constraints=[failed_id],
    )
    prepared, evidence = accepted(request, inner, current[0], owner)
    bindings = dict(
        session_id="session", command_revision=draft.revision, input_token="", input_revision=None
    )
    diagnostic = diagnostics.FailureDiagnostics.from_guarded(
        evidence,
        expected_prepared=prepared,
        current_selection=current[0],
        owner_token=owner,
        **bindings,
    )
    snapshot = diagnostic.for_current(
        request, current_selection=current[0], owner_token=owner, **bindings
    )
    assert (
        snapshot.candidate_constraint_ids == (failed_id,)
        and snapshot.solver_status == "inconsistent"
    )
    assert not hasattr(snapshot, "remaining_dof") and not hasattr(snapshot, "points")
    with pytest.raises(ValueError, match="exact prepared"):
        diagnostics.FailureDiagnostics.from_guarded(
            evidence,
            expected_prepared=contracts.prepare_request(request),
            current_selection=current[0],
            owner_token=owner,
            **bindings,
        )
    assert (
        diagnostic.for_current(
            request, current_selection=current[0], owner_token=object(), **bindings
        )
        is None
    )
    if version == 3:
        report["failed_constraints"] = ["rim"]
        with pytest.raises(ValueError, match="constraint IDs"):
            accepted(request, inner, current[0], owner)


def test_explicit_capability_alone_never_selects3_and_undo_follows_embedded_schema():
    base = {
        "schema_version": 1,
        "id": "part",
        "name": "Draft",
        "units": "mm",
        "parameters": {},
        "features": [],
        "active_feature": None,
    }
    draft = d.GeneralSketchDraft(json.dumps(base), journal_version=3)
    assert draft.solve_request()["result_version"] == 2
    draft.execute(d.AddArc(d.PointSeed(0, 0), d.PointSeed(5, 0), d.PointSeed(0, 7), "ccw"))
    assert draft.solve_request()["result_version"] == draft.replay_request()["result_version"] == 3
    before = draft.sketch
    display = g.build_geometry(before, source="authored")
    arc = next(iter(display.arcs.values()))
    assert arc.end_mm == (0, 7) and arc.radius_mm == 5  # Raw endpoint was never projected.
    assert draft.sketch == before
    draft.undo()
    assert draft.journal_version == 3 and draft.solve_request()["result_version"] == 2
    draft.redo()
    assert draft.sketch == before and draft.solve_request()["result_version"] == 3


def test_arc_empty_schema3_still_selects3():
    request, _ = recorded(3)
    sketch = request["document"]["features"][0]["sketch"]
    sketch["arcs"], sketch["constraints"] = [], []
    draft = d.GeneralSketchDraft(
        json.dumps(request["document"]), request["feature_id"], True, journal_version=3
    )
    assert draft.solve_request()["result_version"] == draft.replay_request()["result_version"] == 3
    assert not g.build_geometry(draft.sketch, source="authored").arcs


@pytest.mark.parametrize(
    "arcs,ready,finishable", [(True, False, False), (True, True, True), (False, False, True)]
)
def test_finish_requires_arc_profile_readiness_but_legacy_open_sketch_is_unchanged(
    session_module, arcs, ready, finishable
):
    owner = object.__new__(session_module.GeneralSession)
    owner.alive, owner.pending = True, None
    commands = types.SimpleNamespace(
        pending_edit=None, sketch={"arcs": [{"id": "arc"}] if arcs else []}
    )
    owner.draft = types.SimpleNamespace(command_draft=commands, proposal=None)
    owner.current_solution_response = lambda: {"result": {"profile_check": {"ready": ready}}}
    assert owner.can_finish is finishable


def test_finish_admits_checked_open_analytic_path(session_module):
    owner = object.__new__(session_module.GeneralSession)
    owner.alive, owner.pending = True, None
    commands = types.SimpleNamespace(pending_edit=None, sketch={"arcs": [{"construction": False}]})
    owner.draft = types.SimpleNamespace(command_draft=commands, proposal=None)
    owner.current_solution_response = lambda: {
        "result": {"profile_check": {"ready": False, "error": {"code": "open_profile"}}}
    }
    assert owner.can_finish
    owner.draft.proposal = {"kind": "arc"}
    assert not owner.can_finish


@pytest.mark.parametrize("version", [2, 3])
def test_session_exact_initial_completion_is_current_and_reusable(
    session_module, monkeypatch, version
):
    draft, request, inner, current, token = draft_case(version)
    owner = owner_for(session_module, draft, current, token)
    prepared, evidence = accepted(request, inner, current[0], token)
    owner.pending = types.SimpleNamespace(selection=current[0], request_snapshot=lambda: request)
    owner.pending_kind, owner.pending_prepared = "solve", prepared
    monkeypatch.setattr(p, "poll", lambda *args, **kwargs: evidence)
    owner.tick(types.SimpleNamespace(selection=current[0]))
    assert not owner.error and owner.commands.has_current_solution
    assert owner.expected_prepared is prepared and owner.guarded_evidence is evidence
    assert owner.current_solution_response() == inner
    assert owner.geometry().source == "solved"
    assert owner.retained_outline.source == "retained"
    with pytest.raises(ValueError, match="no longer available"):
        evidence.publication.consume(current[0], owner_token=token, expected_result_version=version)


@pytest.mark.parametrize("version", [2, 3])
def test_session_exact_driver_chain_checkpoints_once_and_retains_both_original_Gs(
    session_module, version
):
    draft, current, token, prepared, evidence = trial_case(version)
    owner = owner_for(session_module, draft, current, token, wrapped=True)
    commands = owner.commands
    commands.record_guarded_solution(
        evidence,
        commands.revision,
        expected_prepared=prepared,
        expected_input_revision=commands.pending_edit.input_revision,
    )
    replay, inner = recorded(version, "replay")
    expected2, evidence2 = accepted(replay, inner, current[0], token)
    count = []

    def checkpoint():
        count.append(True)
        owner.stored_snapshot = dispatch.dumps(owner.draft)
        owner.scene.mechanical_cad.sketch_draft_json = owner.stored_snapshot
        return owner.stored_snapshot

    owner.checkpoint = checkpoint
    owner._accepted_driver(
        evidence, expected_prepared=prepared, replay_evidence=evidence2, replay_prepared=expected2
    )
    assert count == [True] and owner.commands.pending_edit is None
    assert owner.commands.has_current_solution and owner.current_solution_response()
    assert owner.commands._solution_evidence == (evidence, evidence2)
    assert owner.commands._solution_prepared == (prepared, expected2)
    assert json.loads(owner.stored_snapshot)["schema_version"] == (3 if version == 3 else 2)
    with pytest.raises(ValueError, match="original trial"):
        owner._accepted_driver(
            evidence,
            expected_prepared=prepared,
            replay_evidence=evidence2,
            replay_prepared=expected2,
        )
    assert count == [True]


def test_open_arc_successful_solve_stays_current_and_can_finish(session_module, monkeypatch):
    request, inner = recorded(3)
    source = request["document"]["features"][0]["sketch"]
    source["lines"], source["constraints"] = [], []
    solved = inner["result"]["sketch"]["solved"]
    solved["lines"], solved["constraints"] = [], []
    inner["result"]["sketch"].update(dimensions={}, remaining_dof=5)
    inner["result"]["profile_check"] = {
        "ready": False,
        "error": {"code": "open_profile", "message": "Open analytic path"},
    }
    snapshots = module("part_contracts_v3")
    inner["input_fingerprint"] = snapshots.input_fingerprint(request)
    inner["result"]["document_hash"] = snapshots.document_hash(
        snapshots._expected_document(request["document"])
    )
    draft = d.GeneralSketchDraft(
        json.dumps(request["document"]), request["feature_id"], True, journal_version=3
    )
    current, token = [selection()], object()
    owner = owner_for(session_module, draft, current, token)
    prepared, evidence = accepted(request, inner, current[0], token)
    owner.pending = types.SimpleNamespace(selection=current[0], request_snapshot=lambda: request)
    owner.pending_kind, owner.pending_prepared = "solve", prepared
    monkeypatch.setattr(p, "poll", lambda *args, **kwargs: evidence)
    owner.tick(types.SimpleNamespace(selection=current[0]))
    owner.alive = True
    assert (
        owner.commands.has_current_solution
        and owner.current_solution_response()["result"]["sketch"]["remaining_dof"] == 5
    )
    assert owner.can_finish
    # Native replay still blocks the existing downstream extrusion; admission
    # alone does not publish it or silently discard the dependent feature.


@pytest.mark.parametrize("version", [2, 3])
def test_observed_candidate_change_then_restore_cannot_revive_solve(version):
    draft, request, inner, current, owner = draft_case(version)
    prepared, evidence = accepted(request, inner, current[0], owner)
    draft.record_guarded_solution(evidence, draft.revision, expected_prepared=prepared)
    original = draft._base["name"]
    draft._base["name"] = "Changed candidate"
    assert not draft.has_current_solution
    draft._base["name"] = original
    assert not draft.has_current_solution
    assert draft._solution_evidence is draft._solution_prepared is None
