"""Genuine packets respect version, expected-G and owner-specific admission.

The session fixture performs serialized native sidecar work. Owner methods run
against small native-free host ports; these tests make no Blender GUI claim.
No result is downgraded for acceptance and no production module is modified.
These are Linux/manual-backend process cases. The dormant service rejects
bundled profiles; portable and Windows public-profile admission controls live in
tests/unit/test_service_v3_lifecycle.py.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import sys
import types
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from service_v3_owner_fakes import (
    PACKAGE,
    ROOT,
    CandidateDisplay,
    context_for,
    forge_evidence,
    load_owners,
)

pytestmark = [
    pytest.mark.kernel,
    pytest.mark.skipif(
        sys.platform != "linux", reason="Linux manual-backend native owner-rejection packets"
    ),
]


def sector_document():
    return {
        "schema_version": 2,
        "id": "sector_owner_boundary",
        "name": "Genuine sector owner-boundary fixture",
        "units": "mm",
        "parameters": {},
        "active_feature": "pad",
        "features": [
            {
                "id": "profile",
                "kind": "sketch_constrained",
                "label": "Sector",
                "params": {},
                "inputs": {},
                "sketch": {
                    "schema_version": 3,
                    "id": "sector",
                    "units": "mm",
                    "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
                    "points": [
                        {"id": "center", "u": 0, "v": 0},
                        {"id": "start", "u": 5, "v": 0},
                        {"id": "end", "u": 0, "v": 5},
                    ],
                    "lines": [
                        {"id": "radial_start", "start": "center", "end": "start"},
                        {"id": "radial_end", "start": "end", "end": "center"},
                    ],
                    "circles": [],
                    "arcs": [
                        {
                            "id": "rim",
                            "center": "center",
                            "start": "start",
                            "end": "end",
                            "direction": "ccw",
                        }
                    ],
                    "constraints": [],
                },
            },
            {
                "id": "pad",
                "kind": "extrude",
                "label": "Pad",
                "params": {"length": 10},
                "inputs": {"profile": "profile"},
            },
        ],
    }


def request(document, action="replay", version=3):
    operation = {
        "protocol_version": 1,
        "action": action,
        "result_version": version,
        "document": copy.deepcopy(document),
    }
    if action == "solve_sketch":
        operation["feature_id"] = document["features"][0]["id"]
    else:
        operation["options"] = {"linear_deflection": 0.1}
    return operation


def capture_wire(job, prepared, evidence_root, label):
    packet = evidence_root / (label + "_" + uuid.uuid4().hex)
    packet.mkdir()
    (packet / "request.raw").write_bytes(prepared.payload)
    captured = {}
    original = job._read_response

    def capture(process, stdout, stderr):
        stdout.seek(0)
        stderr.seek(0)
        (packet / "stdout.raw").write_bytes(stdout.read(64 * 1024 * 1024 + 1))
        (packet / "stderr.raw").write_bytes(stderr.read(64 * 1024 + 1))
        captured["returncode"] = process.returncode
        result = original(process, stdout, stderr)
        captured["raw"] = copy.deepcopy(result)
        return result

    job._read_response = capture
    return packet, captured


def seal_wire(packet, captured, selected, job):
    error = sys.exc_info()[1]
    metadata = {
        "returncode": captured.get("returncode"),
        "cleanup_complete": job.done,
        "validation_error": None if error is None else str(error),
        "project_root": selected.project_root,
        "command": [selected.python_executable, "-m", "mechanical_cad.sidecar"],
        "python_executable_target": selected.python_executable_target,
        "digests": {
            name: hashlib.sha256((packet / name).read_bytes()).hexdigest()
            for name in ("request.raw", "stdout.raw", "stderr.raw")
            if (packet / name).is_file()
        },
        "core_source_hashes": {
            name: hashlib.sha256((ROOT / "src/mechanical_cad" / name).read_bytes()).hexdigest()
            for name in (
                "sidecar.py",
                "engine.py",
                "backend_contract.py",
                "result_policy_v3.py",
                "sketch_protocol_v3.py",
                "sketch_service_v3.py",
                "profile_adapter_v3.py",
            )
        },
    }
    (packet / "terminal.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")


@pytest.fixture(scope="module")
def real_cases(tmp_path_factory):
    owners = load_owners()
    service = importlib.import_module(PACKAGE + ".service_v3")
    selected = owners.backend_selection.BackendSelection.capture(
        str(ROOT), sys.executable, generation=0, lifetime_id="real-v3-owner-controls"
    )
    evidence_root = Path(
        os.environ.get("MCAD_V3_EVIDENCE_DIR", tmp_path_factory.mktemp("v3-owner-wire"))
    )
    evidence_root.mkdir(parents=True, exist_ok=True)
    rectangle = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
    cases = {}
    for label, document in (("sector", sector_document()), ("rectangle", rectangle)):
        for action in ("solve_sketch", "replay"):
            operation = request(document, action)
            job = service.DataOnlyJob(operation, selected, current_selection=lambda: selected)
            packet, captured = capture_wire(
                job._job, job.prepared, evidence_root, label + "_" + action
            )
            try:
                job.start()
                assert job.wait(90), "native fixture must complete cleanup"
                projected = job.result()
                assert projected["ok"] is True, projected
            finally:
                job.cancel()
                seal_wire(packet, captured, selected, job)
                assert job.wait(5)
            assert captured["returncode"] == 0
            cases[label + "_" + action] = types.SimpleNamespace(
                operation=operation,
                prepared=job.prepared,
                raw=captured["raw"],
                projected=projected,
                selected=selected,
            )
    # A separately requested v2 control supports positive live-authority and
    # rollback tests. This is fresh native work, never relabelled v3 data.
    operation = request(rectangle, version=2)
    prepared = owners.backend_contracts.prepare_request(operation)
    job = owners.sidecar_job.SidecarJob.from_selection(prepared, selected)
    packet, captured = capture_wire(job, prepared, evidence_root, "rectangle_replay_v2_control")
    try:
        job.start()
        assert job.wait(90)
        raw = job.result()
        owner = object()
        accepted = owners.guarded_evidence.accept_response(
            prepared, raw, selected, owner_token=owner
        )
        assert accepted.revalidate(selected, owner_token=owner, require_success=True)
    finally:
        job.cancel()
        assert job.wait(5)
        seal_wire(packet, captured, selected, job)
    cases["rectangle_v2"] = types.SimpleNamespace(
        operation=operation, prepared=prepared, raw=raw, selected=selected
    )
    return owners, cases


@pytest.fixture
def owners(real_cases, monkeypatch):
    modules, cases = real_cases
    selected = cases["rectangle_replay"].selected
    current = [selected]
    monkeypatch.setattr(modules.backend_runtime, "capture", lambda _context: current[0])
    monkeypatch.setattr(
        modules.backend_runtime, "configuration", lambda _context: (current[0], 0.1)
    )

    def assert_current(original, _context):
        original.assert_current(current[0])
        return current[0]

    monkeypatch.setattr(modules.backend_runtime, "assert_current", assert_current)
    monkeypatch.setattr(
        modules.backend_runtime, "is_current", lambda original, _context: original == current[0]
    )
    modules.document_state._RUNTIME.clear()
    modules.document_state._GEOMETRY_RUNTIME.clear()
    modules.assembly_state._RUNTIME.clear()
    CandidateDisplay.events = []
    modules.current_selection = current
    yield modules
    modules.document_state._RUNTIME.clear()
    modules.document_state._GEOMETRY_RUNTIME.clear()
    modules.assembly_state._RUNTIME.clear()


def forged(owners, case, owner):
    return forge_evidence(owners, case.prepared, case.raw, case.selected, owner)


def rectangle_session(owners, case):
    context = context_for(owners, case.operation["document"], case.selected)
    session = owners.viewport_sketch.RectangleSession(context, "sketch_1")
    return context, session


def guarded_binding(owners, context, case, owner):
    binding = owners.document_state._capture_binding(context, owner_token=owner)
    binding["prepared"] = case.prepared
    binding["request_fingerprint"] = case.prepared.fingerprint
    binding["result_version"] = case.prepared.operation_request()["result_version"]
    return binding


def inject_invalid_runtime_for_reader_control(
    owners, context, evidence, binding, *, geometry=False
):
    """Test-only corrupt association; the real insertion boundary must reject it first."""
    state = context.scene.mechanical_cad
    record = {
        "scene": context.scene,
        "owner_id": state.owner_id,
        "document_json": state.document_json,
        "scale": float(context.scene.unit_settings.scale_length),
        "evidence": evidence,
        **{
            key: binding[key]
            for key in (
                "owner_token",
                "selection",
                "deflection",
                "prepared",
                "request_fingerprint",
                "result_version",
            )
        },
    }
    target = owners.document_state._RUNTIME
    if geometry:
        record["report_json"] = state.geometry_report_json
        target = owners.document_state._GEOMETRY_RUNTIME
    target[owners.document_state._scene_key(context.scene)] = record


@pytest.mark.parametrize(
    "name", ["sector_replay", "sector_solve_sketch", "rectangle_replay", "rectangle_solve_sketch"]
)
def test_genuine_v3_factory_keeps_default_v2_and_reconstructed_owner_barriers(
    real_cases, owners, name
):
    case = real_cases[1][name]
    owner = object()
    owners.backend_contracts.validate_receipt(
        case.prepared.guarded_request(), case.raw, case.selected
    )
    accepted = owners.guarded_evidence.accept_response(
        case.prepared, case.raw, case.selected, owner_token=owner
    )
    assert (
        accepted.revalidate(
            case.selected,
            owner_token=owner,
            expected_action=case.prepared.action,
            expected_result_version=3,
            require_success=True,
        )
        == case.projected
    )
    for evidence in (accepted, forged(owners, case, owner)):
        for method in (evidence.revalidate, evidence.publication.consume):
            with pytest.raises(
                owners.backend_contracts.BackendContractError, match="result version"
            ):
                method(case.selected, owner_token=owner)


@pytest.mark.parametrize("name", ["sector_replay", "rectangle_replay"])
def test_public_negotiation_and_strict_legacy_validators_remain_closed(
    real_cases, owners, monkeypatch, name
):
    case = real_cases[1][name]
    document = case.operation["document"]
    monkeypatch.setattr(
        owners.bridge, "_exchange_raw", lambda *_a, **_k: pytest.fail("unsupported public launch")
    )
    calls = [
        lambda: owners.bridge.replay(document, result_version=3),
        lambda: owners.bridge.geometry_action(document, "check_geometry", result_version=3),
        lambda: owners.part_result_bridge.validate_response(case.operation, case.projected),
        lambda: owners.part_snapshot_bridge.validate_response(
            {"protocol_version": 1, "action": "canonical_snapshot", "document": document},
            case.projected,
        ),
    ]
    assembly = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    assembly_request = owners.assembly_bridge.build_request(
        assembly, "assembly_replay", result_version=2
    )
    calls.append(lambda: owners.assembly_bridge.validate_response(assembly_request, case.projected))
    for call in calls:
        with pytest.raises((ValueError, RuntimeError)):
            call()
    # Capable Part selection now explicitly adopts schema3. The public legacy
    # bridges above remain closed; legacy-only owners still reject requested3.
    if name == "sector_replay":
        assert owners.document_state._result_version(document, 3) == 3
    else:
        with pytest.raises((ValueError, RuntimeError)):
            owners.document_state._result_version(document, 3)
    solve = real_cases[1][name.replace("replay", "solve_sketch")]
    with pytest.raises(ValueError):
        owners.sketch_action_bridge.validate_solve_response(solve.projected, solve.operation)


@pytest.mark.parametrize("name", ["sector_replay", "rectangle_replay"])
def test_injected_v3_reply_cannot_replace_fresh_v2_transport(real_cases, owners, monkeypatch, name):
    case = real_cases[1][name]
    v2 = real_cases[1]["rectangle_v2"]
    fresh = owners.backend_contracts.prepare_request(v2.operation)
    owner = object()
    job = owners.guarded_transport.GuardedJob(fresh, case.selected, owner_token=owner)
    monkeypatch.setattr(job._job, "result", lambda: copy.deepcopy(case.raw))
    with pytest.raises(owners.guarded_transport.GuardedOperationError, match="nonce"):
        job.result(case.selected, owner_token=owner)
    job.cancel()
    assert job.wait(0)


def test_private_legacy_tooling_reads_rectangle3_without_current_or_seed_authority(
    real_cases, owners, monkeypatch
):
    case = real_cases[1]["rectangle_replay"]
    context, session = rectangle_session(owners, case)
    candidate = session.draft.candidate()
    monkeypatch.setattr(
        owners.bridge, "_exchange_raw", lambda *_a, **_k: copy.deepcopy(case.projected)
    )
    historical = owners.bridge._exchange(
        case.operation, project_root="unused", python_executable="unused", timeout=1
    )
    assert historical["result_version"] == 3
    assert session.draft.accept_replay(candidate, historical["result"])
    assert session.draft.solver_report is not None and session.draft.validated_json
    assert session.draft.last_solved_points is not None
    assert not session.draft.guarded_is_current(case.selected)
    for read in (session.draft._guarded_report, session.draft.guarded_seed_points):
        with pytest.raises(ValueError):
            read(case.selected)
    assert session.current_solver_report() is None and not session.has_current_solution
    assert owners.document_state.current_part_result(context) is None
    assert owners.document_state.current_part_evidence(context) is None
    assert not owners.document_state.part_is_current(context)
    assert not owners.document_state.geometry_report_is_current(context)


def test_dimensions_operator_rejects_tooling_seed_before_any_authored_change(
    real_cases, owners, monkeypatch
):
    case = real_cases[1]["rectangle_replay"]
    context, session = rectangle_session(owners, case)
    assert session.draft.accept_replay(session.draft.candidate(), case.projected["result"])
    before = owners.draft_store.dumps(session.draft)
    monkeypatch.setattr(owners.viewport_sketch, "active_session", lambda _context: session)
    monkeypatch.setattr(session, "solve", lambda *_: pytest.fail("fresh native launch"))
    closed = []
    popup = types.SimpleNamespace(
        session=session,
        width="999",
        height="888",
        fix_position=not session.draft.fix_corner,
        _close_later=lambda: closed.append(True),
    )
    with pytest.raises(ValueError):
        owners.viewport_sketch.MCAD_OT_sketch_dimensions.execute(popup, context)
    assert owners.draft_store.dumps(session.draft) == before
    assert closed == [True]


@pytest.mark.parametrize("name", ["sector_replay", "rectangle_replay"])
@pytest.mark.parametrize("form", ["raw", "forged"])
@pytest.mark.parametrize("consume", [False, True])
def test_rectangle_guarded_acceptance_rejects_genuine3_before_tooling_call(
    real_cases, owners, monkeypatch, name, form, consume
):
    case = real_cases[1][name]
    context, session = rectangle_session(owners, real_cases[1]["rectangle_replay"])
    before = owners.draft_store.dumps(session.draft)
    owner = session._backend_owner
    value = case.projected if form == "raw" else forged(owners, case, owner)
    monkeypatch.setattr(
        session.draft, "accept_replay", lambda *_args: pytest.fail("tooling seam reached")
    )
    with pytest.raises(ValueError, match="guarded Part evidence|result version"):
        session.draft.accept_guarded_replay(
            case.operation["document"], value, case.selected, owner_token=owner, consume=consume
        )
    assert owners.draft_store.dumps(session.draft) == before
    assert not session.has_current_solution
    assert owners.document_state.current_part_evidence(context) is None


def test_valid_v2_association_overwrites_corrupted_tooling_seed(real_cases, owners, monkeypatch):
    case = real_cases[1]["rectangle_v2"]
    context, session = rectangle_session(owners, case)
    owner = session._backend_owner
    evidence = owners.guarded_evidence.accept_response(
        case.prepared, case.raw, case.selected, owner_token=owner
    )
    assert session.draft.accept_guarded_replay(
        session.draft.candidate(), evidence, case.selected, owner_token=owner
    )
    good = session.draft.guarded_seed_points(case.selected)
    session.draft.last_solved_points = [{**point, "u": 9999} for point in good]
    monkeypatch.setattr(owners.viewport_sketch, "active_session", lambda _context: session)
    monkeypatch.setattr(session, "solve", lambda *_: False)
    popup = types.SimpleNamespace(
        session=session,
        width=session.draft.width_text,
        height=session.draft.height_text,
        fix_position=False,
        _close_later=lambda: None,
    )
    assert owners.viewport_sketch.MCAD_OT_sketch_dimensions.execute(popup, context) == {"FINISHED"}
    assert session.draft.seed_override == good
    assert all(point["u"] != 9999 for point in session.draft.seed_override)


def test_finish_after_tooling_cache_runs_fresh_v2_and_rejects_v3_without_commit(
    real_cases, owners, monkeypatch
):
    case = real_cases[1]["rectangle_replay"]
    context, session = rectangle_session(owners, case)
    assert session.draft.accept_replay(session.draft.candidate(), case.projected["result"])
    original = context.scene.mechanical_cad.document_json
    calls = []

    def execute(prepared, selected, *, owner_token, current_selection):
        calls.append(prepared)
        assert prepared.operation_request()["result_version"] == 2
        return owners.guarded_evidence.accept_response(
            prepared, case.raw, selected, owner_token=owner_token
        )

    monkeypatch.setattr(owners.guarded_transport, "execute", execute)
    assert not session.finish(context)
    assert len(calls) == 1 and calls[0].request_id != case.prepared.request_id
    assert context.scene.mechanical_cad.document_json == original
    assert not CandidateDisplay.events
    assert not session.has_current_solution and not owners.document_state.part_is_current(context)


def test_tooling_save_restore_history_and_aba_never_restore_authority(real_cases, owners):
    case = real_cases[1]["rectangle_replay"]
    context, session = rectangle_session(owners, case)
    assert session.draft.accept_replay(session.draft.candidate(), case.projected["result"])
    serialized = owners.draft_store.dumps(session.draft)
    payload = json.loads(serialized)
    assert payload["draft"]["solver_report"] is None and payload["draft"]["validated_json"] == ""
    for field, value in (
        ("solver_report", session.draft.solver_report),
        ("validated_json", session.draft.validated_json),
    ):
        modified = copy.deepcopy(payload)
        modified["draft"][field] = value
        with pytest.raises(ValueError):
            owners.draft_store.loads(json.dumps(modified))
    restored = owners.draft_store.restore(
        serialized, session.draft.document_json, owners.sketch_draft.RectangleDraft
    )
    assert restored.last_solved_points and restored._guarded_evidence is None
    resumed = owners.viewport_sketch.RectangleSession(context, restored=restored)
    for generation, lifetime in (
        (0, case.selected.lifetime_id),
        (2, case.selected.lifetime_id),
        (0, "load-new-lifetime"),
    ):
        owners.current_selection[0] = replace(
            case.selected, generation=generation, lifetime_id=lifetime
        )
        assert resumed.current_solver_report() is None and not resumed.has_current_solution
        with pytest.raises(ValueError):
            restored.guarded_seed_points(owners.current_selection[0])


@pytest.mark.parametrize("name", ["sector_replay", "rectangle_replay"])
def test_part_sinks_reject_raw_or_wrong_expected_G_v3_without_publication(real_cases, owners, name):
    case = real_cases[1][name]
    context = context_for(owners, case.operation["document"], case.selected)
    owner = object()
    evidence = forged(owners, case, owner)
    # Capture a distinct exact request before touching the receiving owner. A
    # fully reconstructed class with valid same-O evidence cannot choose its G.
    expected = owners.backend_contracts.prepare_request(case.operation)
    assert expected.operation_request() == case.prepared.operation_request()
    assert expected.request_id != case.prepared.request_id
    binding = guarded_binding(owners, context, case, owner)
    binding["prepared"] = expected
    binding["request_fingerprint"] = expected.fingerprint
    before = owners.document_state._snapshot_fields(context.scene.mechanical_cad)
    for value in (case.projected, evidence):
        for sink in (
            lambda value=value: owners.document_state._evidence_projection(
                context, case.operation["document"], value, binding
            ),
            lambda value=value: owners.document_state._apply_result(
                context, case.operation["document"], value, binding
            ),
        ):
            with pytest.raises((ValueError, RuntimeError)):
                sink()
        with owners.document_state.replay_guard(context):
            with pytest.raises((ValueError, RuntimeError)):
                owners.document_state._publish_candidate_locked(
                    context,
                    case.operation["document"],
                    value,
                    binding,
                    json.dumps(case.operation["document"], allow_nan=False),
                )
        intent = None
        with pytest.raises((ValueError, RuntimeError)):
            intent = owners.part_publication.PartPublicationIntent(
                context, expected.operation_request(), case.selected, "", owner_token=owner
            )
            assert intent.prepared.operation_request() == expected.operation_request()
            assert intent.prepared.request_id not in (expected.request_id, case.prepared.request_id)
            intent.publish(context, value)
        if intent is not None:
            assert intent.retired
    assert owners.document_state._snapshot_fields(context.scene.mechanical_cad) == before
    assert not CandidateDisplay.events
    for geometry in (False, True):
        with pytest.raises((ValueError, RuntimeError)):
            owners.document_state._remember_evidence(context, evidence, binding, geometry=geometry)
        inject_invalid_runtime_for_reader_control(
            owners, context, evidence, binding, geometry=geometry
        )
    context.scene.mechanical_cad.status = "READY"
    context.scene.mechanical_cad.geometry_status = "PASSED"
    assert not owners.document_state.part_is_current(context)
    assert not owners.document_state.geometry_report_is_current(context)
    assert owners.document_state.current_part_result(context) is None
    assert owners.document_state.current_part_evidence(context) is None


def test_general_draft_and_geometry_diagnostic_views_reject_genuine3(real_cases, owners):
    for label in ("rectangle", "sector"):
        solve = real_cases[1][label + "_solve_sketch"]
        document = real_cases[1]["rectangle_replay"].operation["document"]
        draft = owners.general_sketch_draft.GeneralSketchDraft(
            json.dumps(document), "sketch_1", True
        )
        before = draft.checkpoint_payload()
        with pytest.raises(ValueError):
            draft.record_validated_solution(solve.operation, solve.projected, draft.revision)
        owner = object()
        draft.bind_guarded(owner, lambda solve=solve: solve.selected)
        evidence = forged(owners, solve, owner)
        with pytest.raises(ValueError):
            draft.record_guarded_solution(
                evidence, draft.revision, expected_prepared=solve.prepared
            )
        with pytest.raises(ValueError):
            owners.general_view_geometry.build_guarded_geometry(
                draft.sketch,
                evidence,
                expected_prepared=solve.prepared,
                current_selection=solve.selected,
                owner_token=owner,
            )
        assert draft.checkpoint_payload() == before and not draft.has_current_solution


@pytest.mark.parametrize("form", ["raw", "forged"])
def test_geometry_historical_and_error_attributes_cannot_make_v3_current(
    real_cases, owners, monkeypatch, form
):
    case = real_cases[1]["rectangle_replay"]
    context = context_for(owners, case.operation["document"], case.selected)
    original = context.scene.mechanical_cad.document_json
    calls = []

    def fail(prepared, selected, *, owner_token, current_selection):
        calls.append(prepared)
        value = case.projected if form == "raw" else forged(owners, case, owner_token)
        raise owners.guarded_transport.GuardedOperationError(
            "Injected historical result3", historical_export=value
        )

    monkeypatch.setattr(owners.guarded_transport, "execute", fail)
    assert not owners.geometry_operations.run_geometry_action(
        context, "export_step", destination="/never-written/owner-negative.step"
    )
    state = context.scene.mechanical_cad
    assert len(calls) == 1 and calls[0].operation_request()["result_version"] == 2
    assert state.document_json == original
    assert state.status == "FAILED" and state.geometry_status in {"FAILED", "UNKNOWN"}
    assert not owners.document_state.part_is_current(context)
    assert not owners.document_state.geometry_report_is_current(context)
    assert json.loads(state.geometry_report_json)["ok"] is False


@pytest.mark.parametrize("name", ["sector_replay", "rectangle_replay"])
def test_assembly_admission_and_display_reject_genuine_v3(real_cases, owners, name):
    case = real_cases[1][name]
    context = context_for(owners, case.operation["document"], case.selected)
    owner = object()
    evidence = forged(owners, case, owner)
    snapshot = {"prepared": case.prepared, "selection": case.selected, "owner_token": owner}
    for value in (case.projected, evidence):
        with pytest.raises((ValueError, RuntimeError)):
            owners.assembly_state._projection(
                context, snapshot, value, actions="assembly_replay", consume=True
            )
        with pytest.raises((ValueError, RuntimeError)):
            owners.assembly_display._validated(value, owner, lambda: case.selected, consume=True)
        assert not owners.assembly_display.trusted_display(
            context.scene,
            "assembly-owner",
            value,
            owner_token=owner,
            current_selection=lambda: case.selected,
        )

    state = context.scene.mechanical_cad_assembly
    state.document_json = json.dumps(
        json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    )
    state.owner_id = "assembly-owner"
    state.display_status = state.verification_status = "CURRENT"
    owners.assembly_state._RUNTIME[context.scene.as_pointer()] = {
        "owner_id": state.owner_id,
        "display_document_json": state.document_json,
        "display_evidence": evidence,
        "display_owner_token": owner,
        "report_binding": owners.assembly_state._binding(state),
        "report_evidence": evidence,
        "report_owner_token": owner,
    }
    assert not owners.assembly_state.display_is_current(context)
    assert not owners.assembly_state.report_is_current(context)


@pytest.mark.parametrize("name", ["sector_replay", "rectangle_replay"])
@pytest.mark.parametrize("form", ["raw", "forged"])
def test_full_assembly_commit_rejects_v3_before_staging_or_canonical_write(
    real_cases, owners, monkeypatch, name, form
):
    case = real_cases[1][name]
    context = context_for(owners, case.operation["document"], case.selected)
    state = context.scene.mechanical_cad_assembly
    original_part, original_assembly = (
        context.scene.mechanical_cad.document_json,
        state.document_json,
    )
    calls = []

    def execute(prepared, selected, *, owner_token, current_selection):
        calls.append(prepared)
        assert prepared.operation_request()["action"] == "assembly_replay"
        assert prepared.operation_request()["result_version"] == 2
        assert current_selection() == selected
        return case.projected if form == "raw" else forged(owners, case, owner_token)

    monkeypatch.setattr(owners.guarded_transport, "execute", execute)
    monkeypatch.setattr(
        owners.assembly_display, "stage", lambda *_a, **_k: pytest.fail("assembly staged")
    )
    candidate = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    with pytest.raises(
        owners.bridge.BridgeError, match="guarded backend evidence|exact captured request"
    ):
        owners.assembly_state.commit_candidate(context, candidate)
    assert len(calls) == 1
    assert state.document_json == original_assembly
    assert context.scene.mechanical_cad.document_json == original_part
    assert state.display_status != "CURRENT" and state.verification_status != "CURRENT"
    assert not owners.assembly_state.display_is_current(context)
    assert not owners.assembly_state.report_is_current(context)
    assert not owners.assembly_state._RUNTIME


@pytest.mark.parametrize("failure", ["pre_publication", "staged_display", "rollback", "aba"])
def test_v2_transaction_errors_never_restore_injected_v3_runtime(
    real_cases, owners, monkeypatch, failure
):
    v2 = real_cases[1]["rectangle_v2"]
    v3 = real_cases[1]["rectangle_replay"]
    context = context_for(owners, v2.operation["document"], v2.selected)
    owner = object()
    good = owners.guarded_evidence.accept_response(
        v2.prepared, v2.raw, v2.selected, owner_token=owner
    )
    binding = guarded_binding(owners, context, v2, owner)
    bad = forged(owners, v3, owner)
    with pytest.raises((ValueError, RuntimeError)):
        owners.document_state._remember_evidence(context, bad, binding)
    inject_invalid_runtime_for_reader_control(owners, context, bad, binding)
    context.scene.mechanical_cad.status = "READY"
    original = context.scene.mechanical_cad.document_json
    if failure == "pre_publication":
        candidate = v3.operation["document"]
        value, actual_binding = bad, guarded_binding(owners, context, v3, owner)
    else:
        candidate, value, actual_binding = v2.operation["document"], good, binding

        def fail_display(*_args, **_kwargs):
            if failure == "aba":
                owners.current_selection[0] = replace(v2.selected, generation=2)
            raise RuntimeError("staged display fault")

        monkeypatch.setattr(owners.document_state, "_display_feature", fail_display)
        if failure == "rollback":
            monkeypatch.setattr(
                CandidateDisplay,
                "rollback",
                lambda _self: (_ for _ in ()).throw(RuntimeError("rollback fault")),
            )
    with owners.document_state.replay_guard(context):
        with pytest.raises((ValueError, RuntimeError)):
            owners.document_state._publish_candidate_locked(
                context, candidate, value, actual_binding, json.dumps(candidate, allow_nan=False)
            )
    assert context.scene.mechanical_cad.document_json == original
    assert not owners.document_state.part_is_current(context)
    assert owners.document_state.current_part_result(context) is None
    assert not owners.document_state.geometry_report_is_current(context)
