"""Native-free Gate C owner matrix using real guarded publication and test host ports.

Synthetic packets exercise owner contracts, never native geometry or installed UI.
No sidecar process runs and no export destination is written by these ports.
"""

import copy
import importlib
import importlib.util
import itertools
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_arc_guarded_evidence import synthetic_outer
from test_geometry_result_v3 import ACTIONS, failed_replay, pair

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "geometry3_host_ports", ROOT / "tests/integration/service_v3_owner_fakes.py"
)
ports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ports)
NAMES = itertools.count()


@pytest.fixture
def host(monkeypatch, tmp_path):
    ports.PACKAGE = "mcad_geometry3_owner_tests_" + str(next(NAMES))
    modules = ports.load_owners()
    lease = importlib.import_module(ports.PACKAGE + ".execution_lease")
    assert not lease.is_busy()
    selected = modules.backend_selection.BackendSelection.capture(
        str(ROOT), sys.executable, generation=2, lifetime_id="geometry3-pure-port", environment={}
    )
    current = [selected]
    monkeypatch.setattr(modules.backend_runtime, "capture", lambda _context: current[0])
    monkeypatch.setattr(
        modules.backend_runtime, "configuration", lambda _context: (current[0], 0.1)
    )
    modules.document_state._RUNTIME.clear()
    modules.document_state._GEOMETRY_RUNTIME.clear()
    request, _ = pair(options={"linear_deflection": 0.1})
    context = ports.context_for(modules, request["document"], selected)
    result = SimpleNamespace(
        modules=modules,
        doc=modules.document_state,
        geometry=modules.geometry_operations,
        selected=selected,
        current=current,
        context=context,
        lease=lease,
        prepared=[],
        evidence=[],
        owners=[],
        jobs=[],
        shown=[],
        hidden=[],
        cleanup=True,
        mutate=lambda raw: None,
        after_wait=lambda: None,
        destination=str(tmp_path / "selected-sector.step"),
    )
    monkeypatch.setattr(
        result.doc, "_display_feature", lambda *args, **kwargs: result.shown.append((args, kwargs))
    )
    monkeypatch.setattr(result.geometry, "_hide_owned", lambda scene: result.hidden.append(scene))

    class Port:
        cleanup_diagnostic = ""
        done = True

        @classmethod
        def from_selection(cls, prepared, selection):
            port = cls()
            port.prepared, port.selection, port.state = prepared, selection, "created"
            port.starts = port.waits = port.cancels = 0
            result.jobs.append(port)
            result.prepared.append(prepared)
            return port

        def request_snapshot(self):
            return self.prepared.guarded_request()

        def start(self):
            self.starts += 1
            self.state = "ready"

        def wait(self, timeout=None):
            self.waits += 1
            result.after_wait()
            self.done = result.cleanup
            return result.cleanup

        def cancel(self):
            self.cancels += 1
            self.state = "cancelled"
            return True

        def result(self):
            self.state = "consumed"
            operation = self.prepared.operation_request()
            _, inner = pair(
                operation["action"],
                destination=operation.get("destination"),
                options=operation["options"],
            )
            raw = synthetic_outer(self.prepared, inner, self.selection)
            result.mutate(raw)
            return raw

    monkeypatch.setattr(modules.guarded_transport, "SidecarJob", Port)
    accept = modules.guarded_transport.accept_response

    def capture(prepared, raw, selection, *, owner_token):
        evidence = accept(prepared, raw, selection, owner_token=owner_token)
        if type(evidence) is modules.guarded_evidence.GuardedEvidence:
            result.evidence.append(evidence)
            result.owners.append(owner_token)
        return evidence

    monkeypatch.setattr(modules.guarded_transport, "accept_response", capture)
    yield result
    assert not result.doc._REPLAY_RUNNING
    assert lease.is_busy() is (not result.cleanup)
    modules.document_state._RUNTIME.clear()
    modules.document_state._GEOMETRY_RUNTIME.clear()
    # Only synthetic ports are retired here; production quarantine has no reset.
    for name in list(sys.modules):
        if name == ports.PACKAGE or name.startswith(ports.PACKAGE + "."):
            del sys.modules[name]


def run(host, action="check_geometry"):
    return host.geometry.run_geometry_action(
        host.context, action, destination=None if action == "check_geometry" else host.destination
    )


def assert_unverified(host):
    assert not host.doc.part_is_current(host.context)
    assert not host.doc.geometry_report_is_current(host.context)
    assert host.doc.current_part_result(host.context) is None


def assert_once(host):
    assert len(host.jobs) == 1
    assert host.jobs[0].starts == 1 and host.jobs[0].waits >= 1
    assert not host.lease.is_busy()


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("dof", [0, 5])
def test_selected_geometry3_publishes_once_and_retains_only_historical_saved_metadata(
    host, action, dof
):
    host.mutate = lambda raw: raw["result"]["features"][0]["sketch"].update(remaining_dof=dof)
    before = host.context.scene.mechanical_cad.document_json
    assert run(host, action)
    state = host.context.scene.mechanical_cad
    assert state.document_json == before and state.status == "READY"
    assert host.doc.part_is_current(host.context) and host.doc.geometry_report_is_current(
        host.context
    )
    assert host.prepared[0].operation_request()["result_version"] == 3
    report = json.loads(state.geometry_report_json)
    assert report["result_version"] == 3 and report["ok"] is True
    evidence, owner = host.evidence[0], host.owners[0]
    assert evidence.revalidate(
        host.selected, owner_token=owner, expected_action=action, expected_result_version=3
    )
    with pytest.raises(ValueError, match="no longer available"):
        evidence.publication.consume(host.selected, owner_token=owner, expected_result_version=3)
    assert_once(host)
    host.doc._RUNTIME.clear()
    host.doc._GEOMETRY_RUNTIME.clear()
    assert state.geometry_status == "PASSED" and state.geometry_report_json
    assert_unverified(host)
    assert not Path(host.destination).exists()


@pytest.mark.parametrize(
    "action,failure",
    [
        (action, failure)
        for action in ACTIONS
        for failure in ("replay", "check", "writer")
        if (action, failure) != ("check_geometry", "writer")
    ],
)
def test_distinct_failure_phases_keep_valid_part_replay_without_geometry_success(
    host, action, failure
):
    def mutate(raw):
        raw["ok"], raw["export"] = False, None
        if failure == "replay":
            failed_replay(raw["result"])
        if failure != "writer":
            raw["geometry_check"] = None
        else:
            raw["geometry_check"].pop("encoded_mesh", None)
            raw["geometry_check"].pop("encoding", None)
        raw["error"] = {
            "code": {
                "replay": "regeneration_failed",
                "check": "geometry_check_failed",
                "writer": "export_io_error",
            }[failure],
            "message": "Synthetic " + failure + " failure",
        }

    host.mutate = mutate
    assert not run(host, action)
    state = host.context.scene.mechanical_cad
    assert state.geometry_status == "FAILED"
    assert not host.doc.geometry_report_is_current(host.context)
    assert host.doc.part_is_current(host.context) is (failure != "replay")
    assert json.loads(state.geometry_report_json)["export"] is None
    assert_once(host)


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize(
    "mutation",
    ["missing_receipt", "nonce", "fingerprint", "result_stamp", "projection", "missing_reply"],
)
def test_invalid_postlaunch_completion_is_unknown_for_export_and_never_retried(
    host, action, mutation
):
    def mutate(raw):
        if mutation == "missing_receipt":
            raw.pop("backend_receipt")
        elif mutation == "nonce":
            raw["backend_receipt"]["request_id"] = "0" * 32
        elif mutation == "fingerprint":
            raw["input_fingerprint"] = "0" * 64
        elif mutation == "result_stamp":
            raw["result_version"] = 2
        elif mutation == "projection":
            raw["result"]["document_id"] = "foreign"
        else:
            raw.clear()

    host.mutate = mutate
    assert not run(host, action)
    assert host.context.scene.mechanical_cad.geometry_status == (
        "FAILED" if action == "check_geometry" else "UNKNOWN"
    )
    assert json.loads(host.context.scene.mechanical_cad.geometry_report_json)["export"] is None
    assert_unverified(host)
    assert_once(host)


@pytest.mark.parametrize("action", ACTIONS)
def test_genuine_pre_dispatch_rejection_is_definite_failure(host, action):
    def mutate(raw):
        receipt = raw["backend_receipt"]
        required = receipt["required_capabilities"]
        receipt.update(
            phase="rejected_before_dispatch",
            confirmed_capabilities=[c for c in required if c != "mcad.geometry-result/3"],
            missing_capabilities=["mcad.geometry-result/3"],
        )
        raw.clear()
        raw.update(
            protocol_version=1,
            ok=False,
            result=None,
            error={"code": "backend_capability_missing", "message": "Missing geometry3"},
            backend_receipt=receipt,
        )

    host.mutate = mutate
    assert not run(host, action)
    assert host.context.scene.mechanical_cad.geometry_status == "FAILED"
    assert_unverified(host)
    assert_once(host)


@pytest.mark.parametrize("mutation", ["generation", "lifetime"])
@pytest.mark.parametrize("action", ["export_step", "export_stl"])
def test_genuine_write_with_stale_backend_keeps_outdated_file_fact(host, action, mutation):
    host.after_wait = lambda: host.current.__setitem__(
        0,
        replace(
            host.selected,
            **({"generation": 4} if mutation == "generation" else {"lifetime_id": "new-lifetime"}),
        ),
    )
    assert not run(host, action)
    state = host.context.scene.mechanical_cad
    assert state.geometry_status == "OUTDATED"
    assert json.loads(state.geometry_report_json)["export"]["destination"] == host.destination
    assert "written" in state.geometry_message
    assert_unverified(host)
    assert_once(host)


def binding_for(host, action="export_step"):
    request, inner = pair(action, destination=host.destination, options={"linear_deflection": 0.1})
    prepared = host.modules.backend_contracts.prepare_request(request)
    binding = host.doc._capture_binding(host.context)
    binding.update(prepared=prepared, request_fingerprint=prepared.fingerprint, result_version=3)
    raw = synthetic_outer(prepared, inner, host.selected)
    evidence = host.modules.guarded_evidence.accept_response(
        prepared, raw, host.selected, owner_token=binding["owner_token"]
    )
    return prepared, binding, evidence


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_version",
        "missing_version",
        "coerced_version",
        "missing_prepared",
        "missing_fingerprint",
        "other_nonce",
        "action",
        "owner",
        "generation",
        "lifetime",
        "document",
        "options",
        "path",
        "numeric_type",
    ],
)
def test_exact_independent_geometry_binding_rejects_substitution(host, mutation):
    prepared, binding, evidence = binding_for(host)
    if mutation == "wrong_version":
        binding["result_version"] = 2
    elif mutation == "missing_version":
        binding.pop("result_version")
    elif mutation == "coerced_version":
        binding["result_version"] = 3.0
    elif mutation == "missing_prepared":
        binding.pop("prepared")
    elif mutation == "missing_fingerprint":
        binding.pop("request_fingerprint")
    elif mutation == "owner":
        binding["owner_token"] = object()
    elif mutation in {"generation", "lifetime"}:
        binding["selection"] = replace(
            host.selected,
            **({"generation": 4} if mutation == "generation" else {"lifetime_id": "retired"}),
        )
    else:
        operation = prepared.operation_request()
        if mutation == "action":
            operation["action"] = "export_stl"
        elif mutation == "document":
            operation["document"]["name"] = "Changed source"
        elif mutation == "options":
            operation.pop("options")
        elif mutation == "path":
            operation["destination"] += "/./sector.step"
        elif mutation == "numeric_type":
            operation["document"]["features"][1]["params"]["length"] = float(
                operation["document"]["features"][1]["params"]["length"]
            )
        if mutation == "other_nonce":
            prepared = host.modules.backend_contracts.prepare_request(operation)
        else:
            original_nonce = prepared.request_id
            original_fingerprint = prepared.fingerprint
            prepared = host.modules.backend_contracts.prepare_guarded_request(
                {
                    **operation,
                    "backend_contract": prepared.guarded_request()["backend_contract"],
                }
            )
            assert prepared.request_id == original_nonce
            assert prepared.fingerprint != original_fingerprint
        binding.update(prepared=prepared, request_fingerprint=prepared.fingerprint)
    with pytest.raises((ValueError, RuntimeError)):
        host.geometry._historical_projection(evidence, prepared, binding, "export_step")
    assert_unverified(host)
    assert not host.jobs


@pytest.mark.parametrize(
    "seam",
    [
        "pre_apply_evidence",
        "pre_apply_binding",
        "display",
        "post_display_binding",
        "post_apply_evidence",
        "report_before",
        "report_after",
        "part_remember_before",
        "part_remember_after",
        "geometry_remember_before",
        "geometry_remember_after",
        "final_binding",
    ],
)
def test_publication_exceptions_never_retain_current_success_or_reusable_claim(
    host, monkeypatch, seam
):
    original_report = host.geometry._record_report
    original_remember = host.doc._remember_evidence
    original_assert = host.doc._assert_binding
    original_projection = host.doc._evidence_projection
    counts = {"binding": 0, "projection": 0}

    def fail():
        raise RuntimeError("Injected " + seam)

    if seam == "display":
        monkeypatch.setattr(host.doc, "_display_feature", lambda *_a, **_k: fail())
    elif seam.startswith("report_"):

        def report(*args, **kwargs):
            if kwargs.get("status") != "OUTDATED":
                if seam == "report_after":
                    original_report(*args, **kwargs)
                fail()
            return original_report(*args, **kwargs)

        monkeypatch.setattr(host.geometry, "_record_report", report)
    elif "remember" in seam:

        def remember(*args, **kwargs):
            target = bool(kwargs.get("geometry")) == seam.startswith("geometry")
            if target and seam.endswith("before"):
                fail()
            original_remember(*args, **kwargs)
            if target:
                fail()

        monkeypatch.setattr(host.doc, "_remember_evidence", remember)
    elif seam in {"pre_apply_evidence", "post_apply_evidence"}:

        def projection(*args, **kwargs):
            counts["projection"] += 1
            if counts["projection"] == (1 if seam == "pre_apply_evidence" else 3):
                fail()
            return original_projection(*args, **kwargs)

        monkeypatch.setattr(host.doc, "_evidence_projection", projection)
    else:

        def check(*args, **kwargs):
            counts["binding"] += 1
            if (
                counts["binding"]
                == {"pre_apply_binding": 1, "post_display_binding": 3, "final_binding": 4}[seam]
            ):
                fail()
            return original_assert(*args, **kwargs)

        monkeypatch.setattr(host.doc, "_assert_binding", check)
    assert not run(host, "export_step")
    assert_unverified(host)
    assert (
        json.loads(host.context.scene.mechanical_cad.geometry_report_json)["export"]["destination"]
        == host.destination
    )
    evidence, owner = host.evidence[0], host.owners[0]
    with pytest.raises(ValueError, match="no longer available|cancelled"):
        evidence.publication.consume(host.selected, owner_token=owner, expected_result_version=3)
    assert_once(host)


@pytest.mark.parametrize(
    "mutation", ["document", "owner", "window", "workspace", "view_layer", "scale", "backend"]
)
def test_context_changes_during_publication_preserve_later_edits_and_unrelated_objects(
    host, monkeypatch, mutation
):
    state = host.context.scene.mechanical_cad
    unrelated = {"name": "unrelated", "mesh": [1, 2, 3], "hidden": False}
    host.context.scene.objects.append(unrelated)
    original = copy.deepcopy(unrelated)
    edited = []

    def display(*_args, **_kwargs):
        if mutation == "document":
            document = json.loads(state.document_json)
            document["name"] = "Later user edit"
            state.document_json = json.dumps(document)
            edited.append(state.document_json)
        elif mutation == "owner":
            state.owner_id = "later-owner"
        elif mutation == "scale":
            host.context.scene.unit_settings.scale_length = 0.01
        elif mutation == "backend":
            host.current[0] = replace(host.selected, generation=4)
        else:
            setattr(host.context, mutation, object())

    monkeypatch.setattr(host.doc, "_display_feature", display)
    assert not run(host, "export_step")
    assert_unverified(host)
    assert unrelated == original
    if edited:
        assert state.document_json == edited[0]
    assert json.loads(state.geometry_report_json)["export"]["destination"] == host.destination
    assert_once(host)


def test_failure_report_exception_after_geometry_insertion_cannot_leave_current_success(
    host, monkeypatch
):
    original = host.doc._remember_evidence

    def remember(*args, **kwargs):
        original(*args, **kwargs)
        if kwargs.get("geometry"):
            raise RuntimeError("Injected after geometry runtime insertion")

    original_report = host.geometry._record_report

    def report(*args, **kwargs):
        if kwargs.get("status") == "OUTDATED":
            raise RuntimeError("Injected failure-report rendering")
        return original_report(*args, **kwargs)

    monkeypatch.setattr(host.doc, "_remember_evidence", remember)
    monkeypatch.setattr(host.geometry, "_record_report", report)
    with pytest.raises(RuntimeError, match="failure-report"):
        run(host, "export_step")
    assert_unverified(host)
    assert (
        json.loads(host.context.scene.mechanical_cad.geometry_report_json)["export"]["destination"]
        == host.destination
    )
    assert_once(host)


@pytest.mark.parametrize("action", ACTIONS)
def test_geometry3_uncertain_cleanup_retains_original_owner_and_blocks_successor(host, action):
    host.cleanup = False
    assert not run(host, action)
    assert_unverified(host)
    assert host.lease.is_busy() and host.lease.cleanup_message()
    token = host.lease._TOKEN
    retained = host.lease._QUARANTINE
    assert retained is not None and len(host.jobs) == 1
    assert host.jobs[0].starts == 1
    assert host.context.scene.mechanical_cad.geometry_status == (
        "FAILED" if action == "check_geometry" else "UNKNOWN"
    )
    assert not host.geometry.MCAD_OT_check_geometry.poll(host.context)
    with pytest.raises(RuntimeError):
        run(host, action)
    assert host.lease._TOKEN is token and host.lease._QUARANTINE is retained
    assert not host.lease.release(token)
    assert len(host.jobs) == 1


@pytest.mark.parametrize("action", ACTIONS)
def test_saved_raw_geometry_dict_never_becomes_owner_authority(host, action):
    prepared, binding, evidence = binding_for(host, action)
    projected = host.modules.backend_contracts.project_response(evidence.response_snapshot())
    for value in (projected, evidence.response_snapshot(), json.loads(json.dumps(projected))):
        with pytest.raises(RuntimeError):
            host.geometry._historical_projection(value, prepared, binding, action)
    assert evidence.publication.cancel()
    with pytest.raises(ValueError, match="cancelled"):
        evidence.revalidate(
            host.selected, owner_token=binding["owner_token"], expected_result_version=3
        )


@pytest.mark.parametrize("value", [None, True, 2.0, 3.0, "3", 1, 4])
def test_historical_report_metadata_only_retains_exact_supported_integer_versions(host, value):
    _, response = pair()
    response["result_version"] = value
    host.geometry._record_report(host.context.scene.mechanical_cad, "historical", response)
    assert "result_version" not in json.loads(
        host.context.scene.mechanical_cad.geometry_report_json
    )
    assert_unverified(host)


@pytest.mark.parametrize(
    "replacement", ["other_nonce", "other_owner", "other_scene", "other_evidence", "foreign_record"]
)
def test_rejection_revokes_only_its_exact_scene_request_and_owner_records(
    host, monkeypatch, replacement
):
    original = host.doc._remember_evidence
    key = host.doc._scene_key(host.context.scene)
    unrelated_key = key + 1
    unrelated = {"scene": object(), "prepared": object(), "owner_token": object()}
    host.doc._RUNTIME[unrelated_key] = unrelated
    host.doc._GEOMETRY_RUNTIME[unrelated_key] = unrelated
    retained = []
    foreign = []

    def remember(context, evidence, binding, **kwargs):
        original(context, evidence, binding, **kwargs)
        if kwargs.get("geometry"):
            if replacement == "other_evidence":
                foreign.append(
                    host.modules.guarded_evidence.accept_response(
                        binding["prepared"],
                        evidence.response_snapshot(),
                        binding["selection"],
                        owner_token=binding["owner_token"],
                    )
                )
                assert foreign[0] is not evidence
                assert foreign[0] == evidence
            for records in (host.doc._RUNTIME, host.doc._GEOMETRY_RUNTIME):
                successor = records[key].copy()
                if replacement == "other_nonce":
                    prepared = host.modules.backend_contracts.prepare_request(
                        binding["prepared"].operation_request()
                    )
                    successor.update(prepared=prepared, request_fingerprint=prepared.fingerprint)
                elif replacement == "other_owner":
                    successor["owner_token"] = object()
                elif replacement == "other_scene":
                    successor["scene"] = object()
                elif replacement == "other_evidence":
                    successor["evidence"] = foreign[0]
                else:
                    successor = object()
                records[key] = successor
                retained.append(successor)
            raise RuntimeError("Injected after another record replaced this launch")

    monkeypatch.setattr(host.doc, "_remember_evidence", remember)
    assert not run(host, "export_step")
    assert host.doc._RUNTIME[key] is retained[0]
    assert host.doc._GEOMETRY_RUNTIME[key] is retained[1]
    assert host.doc._RUNTIME[unrelated_key] is unrelated
    assert host.doc._GEOMETRY_RUNTIME[unrelated_key] is unrelated
    assert (
        json.loads(host.context.scene.mechanical_cad.geometry_report_json)["export"]["destination"]
        == host.destination
    )
    if foreign:
        assert foreign[0].publication.consume(
            host.selected, owner_token=host.owners[0], expected_result_version=3
        )
    assert_once(host)


def test_failure_cleanup_uses_captured_scene_key_after_rna_identity_is_revoked(host, monkeypatch):
    original = host.doc._remember_evidence
    key = host.doc._scene_key(host.context.scene)

    def remember(*args, **kwargs):
        original(*args, **kwargs)
        if kwargs.get("geometry"):

            def revoked(*_args):
                raise ReferenceError("Scene RNA identity is no longer readable")

            monkeypatch.setattr(host.doc, "_scene_key", revoked)
            raise RuntimeError("Injected after scene identity revocation")

    monkeypatch.setattr(host.doc, "_remember_evidence", remember)
    assert not run(host, "export_step")
    assert key not in host.doc._RUNTIME and key not in host.doc._GEOMETRY_RUNTIME
    assert host.context.scene.mechanical_cad.geometry_status == "OUTDATED"
    assert (
        json.loads(host.context.scene.mechanical_cad.geometry_report_json)["export"]["destination"]
        == host.destination
    )
    assert_once(host)


@pytest.mark.parametrize("report_phase", ["before", "partial", "after"])
def test_double_report_failure_still_preserves_confirmed_export_and_revokes_authority(
    host, monkeypatch, report_phase
):
    original = host.geometry._record_report

    def report(*args, **kwargs):
        if report_phase == "partial":
            args[0].geometry_report_json = '{"partial":true}'
        elif report_phase == "after":
            original(*args, **kwargs)
        raise RuntimeError("Injected report failure")

    monkeypatch.setattr(host.geometry, "_record_report", report)
    with pytest.raises(RuntimeError, match="report failure"):
        run(host, "export_step")
    assert_unverified(host)
    report = json.loads(host.context.scene.mechanical_cad.geometry_report_json)
    assert report["export"]["destination"] == host.destination
    assert_once(host)


def test_foreign_completion_is_rejected_without_cancelling_its_publication_claim(host, monkeypatch):
    prepared, binding, foreign = binding_for(host)
    monkeypatch.setattr(
        host.modules.guarded_transport, "execute", lambda *_args, **_kwargs: foreign
    )
    assert not run(host, "export_step")
    assert_unverified(host)
    assert host.context.scene.mechanical_cad.geometry_status == "UNKNOWN"
    assert foreign.publication.consume(
        host.selected,
        owner_token=binding["owner_token"],
        expected_action=prepared.action,
        expected_result_version=3,
    )


def test_prepared_wrong_version_is_rejected_before_transport(host, monkeypatch):
    legacy = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
    wrong = host.modules.backend_contracts.prepare_request(
        {
            "protocol_version": 1,
            "action": "check_geometry",
            "result_version": 2,
            "document": legacy,
            "options": {"linear_deflection": 0.1},
        }
    )
    monkeypatch.setattr(host.geometry, "_prepare_action", lambda *_args: wrong)
    assert not run(host)
    assert not host.jobs
    assert "selected result version" in host.context.scene.mechanical_cad.geometry_message
    assert_unverified(host)


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize(
    "variant",
    [
        "profile",
        "selected_profile",
        "empty",
        "inactive",
        "second_extrude",
        "shared_ids",
        "origin",
        "near_origin",
        "quaternion",
        "near_quaternion",
        "second_arc",
        "circle",
    ],
)
def test_unsupported_source_rejects_before_lease_or_any_owner_state_change(
    host, monkeypatch, action, variant
):
    state = host.context.scene.mechanical_cad
    document = json.loads(state.document_json)
    sketch = document["features"][0]["sketch"]
    if variant in {"profile", "selected_profile"}:
        document["active_feature"] = document["features"][0]["id"]
        if variant == "profile":
            document["features"].pop()
    elif variant == "empty":
        sketch.update(arcs=[], constraints=[])
    elif variant == "inactive":
        feature = copy.deepcopy(document["features"][0])
        feature["id"] = "inactive_schema3"
        feature["sketch"].update(arcs=[], constraints=[])
        document["features"].append(feature)
    elif variant == "second_extrude":
        document["features"].append({**copy.deepcopy(document["features"][1]), "id": "second"})
    elif variant == "shared_ids":
        arc = sketch["arcs"][0]
        sketch["lines"][0].update(start=arc["start"], end=arc["end"])
    elif variant in {"origin", "near_origin"}:
        sketch["plane"]["origin"] = [1 if variant == "origin" else 1e-300, 0, 0]
    elif variant in {"quaternion", "near_quaternion"}:
        sketch["plane"]["quaternion"] = (
            [-1, 0, 0, 0] if variant == "quaternion" else [1, 0, 0, 1e-15]
        )
    elif variant == "second_arc":
        sketch["arcs"].append({**sketch["arcs"][0], "id": "second_arc"})
    else:
        sketch["circles"].append(
            {"id": "circle", "center": sketch["arcs"][0]["center"], "radius": 5}
        )
    state.document_json = json.dumps(document)
    state.status, state.geometry_status = "READY", "PASSED"
    state.geometry_report_json = '{"older_history":true}'
    key = host.doc._scene_key(host.context.scene)
    old_part, old_geometry = object(), object()
    host.doc._RUNTIME[key], host.doc._GEOMETRY_RUNTIME[key] = old_part, old_geometry
    before = host.doc._snapshot_fields(state)
    monkeypatch.setattr(
        host.lease, "try_acquire", lambda: pytest.fail("unsupported source acquired lease")
    )
    with pytest.raises((ValueError, RuntimeError)):
        run(host, action)
    assert host.doc._snapshot_fields(state) == before
    assert host.doc._RUNTIME[key] is old_part and host.doc._GEOMETRY_RUNTIME[key] is old_geometry
    assert not host.jobs and not host.hidden and not host.shown


@pytest.mark.parametrize(
    "write_field", ["geometry_report_json", "geometry_document_json", "geometry_status"]
)
def test_unwritable_history_keeps_exact_confirmed_export_in_error_without_authority(
    host, monkeypatch, write_field
):
    original = host.doc._remember_evidence
    state = host.context.scene.mechanical_cad
    setter = ports.Storage.__setattr__
    revoked = [False]

    def set_value(self, name, value):
        if self is state and revoked[0] and name == write_field:
            raise ReferenceError("Historical RNA storage is unavailable")
        return setter(self, name, value)

    def remember(*args, **kwargs):
        original(*args, **kwargs)
        if kwargs.get("geometry"):
            revoked[0] = True
            raise RuntimeError("Injected publication rejection")

    monkeypatch.setattr(ports.Storage, "__setattr__", set_value)
    monkeypatch.setattr(host.doc, "_remember_evidence", remember)
    with pytest.raises(host.modules.guarded_transport.GuardedOperationError) as failure:
        run(host, "export_step")
    error = failure.value
    assert "Confirmed STEP written:" in str(error)
    assert "Historical report storage or rendering failed" in str(error)
    assert "The file is not undone" in str(error)
    assert not error.outcome_unknown
    assert error.historical_export is host.evidence[0]
    response = error.historical_export.response_snapshot()
    assert response["export"]["destination"] == host.destination
    assert response["backend_receipt"]["request_fingerprint"] == host.prepared[0].fingerprint
    assert_unverified(host)
    assert_once(host)


def test_failed_render_cannot_rewrite_the_frozen_validated_file_fact(host, monkeypatch):
    def report(_state, _snapshot, response, **_kwargs):
        response["export"]["destination"] = "/foreign/never-authorized.step"
        raise RuntimeError("Injected mutation during failed report rendering")

    monkeypatch.setattr(host.geometry, "_record_report", report)
    with pytest.raises(host.modules.guarded_transport.GuardedOperationError) as failure:
        run(host, "export_step")
    state = host.context.scene.mechanical_cad
    assert json.loads(state.geometry_report_json)["export"]["destination"] == host.destination
    assert host.destination in str(failure.value)
    assert "/foreign/never-authorized.step" not in str(failure.value)
    assert (
        failure.value.historical_export.response_snapshot()["export"]["destination"]
        == host.destination
    )
    assert_unverified(host)
    assert_once(host)


def scene_wrapper_port(host, *, distinct):
    """Conditional RNA-wrapper port, not a claim about native Blender aliasing."""
    original_context = host.context
    original_scene = original_context.scene
    control = SimpleNamespace(
        key=host.doc._scene_key(original_scene),
        pointer_revoked=False,
        equality_revoked=False,
        failed_pointer_calls=0,
        pointer_calls=0,
    )

    class SceneWrapper(ports.Storage):
        def as_pointer(self):
            control.pointer_calls += 1
            if control.pointer_revoked:
                control.failed_pointer_calls += 1
                raise ReferenceError("Scene RNA pointer is unavailable")
            return control.key

        def __eq__(self, other):
            if control.equality_revoked:
                raise ReferenceError("Scene RNA equality is unavailable")
            return super().__eq__(other)

        def __ne__(self, other):
            if control.equality_revoked:
                raise ReferenceError("Scene RNA inequality is unavailable")
            return super().__ne__(other)

    identity_wrapper = SceneWrapper(**vars(original_scene))

    class ContextWrappers:
        @property
        def scene(self):
            return SceneWrapper(**vars(original_scene)) if distinct else identity_wrapper

        def __getattr__(self, name):
            return getattr(original_context, name)

    host.context = ContextWrappers()
    assert host.context.scene == host.context.scene
    assert (host.context.scene is host.context.scene) is (not distinct)
    return control


@pytest.mark.parametrize("distinct,revoke_pointer", [(True, False), (True, True), (False, True)])
@pytest.mark.parametrize("consumed", [False, True])
def test_equal_scene_wrappers_revoke_exact_completion_before_first_history_write_failure(
    host, monkeypatch, distinct, revoke_pointer, consumed
):
    control = scene_wrapper_port(host, distinct=distinct)
    state = host.context.scene.mechanical_cad
    original_remember = host.doc._remember_evidence
    original_setattr = ports.Storage.__setattr__
    original_cancel = host.modules.guarded_evidence.EvidencePublication.cancel
    storage_revoked = [False]
    pointer_calls_at_rejection = []
    cancellations = []

    def cancel(publication):
        result = original_cancel(publication)
        cancellations.append(result)
        return result

    def set_value(self, name, value):
        if self is state and storage_revoked[0] and name == "geometry_report_json":
            raise ReferenceError("First historical RNA storage write is unavailable")
        return original_setattr(self, name, value)

    def remember(context, evidence, binding, **kwargs):
        original_remember(context, evidence, binding, **kwargs)
        if kwargs.get("geometry"):
            assert host.doc.part_is_current(context)
            assert host.doc.geometry_report_is_current(context)
            assert host.doc._GEOMETRY_RUNTIME[control.key]["evidence"] is evidence
            storage_revoked[0] = True
            control.pointer_revoked = revoke_pointer
            # The identity fast path must also work without invoking equality.
            control.equality_revoked = not distinct
            pointer_calls_at_rejection.append(control.pointer_calls)
            raise RuntimeError("Injected rejection after exact runtime insertion")

    if not consumed:

        def unpublished(context, _document, evidence, binding):
            state.status = "READY"
            host.geometry._record_report(
                state, binding["document_json"], evidence.response_snapshot()
            )
            remember(context, evidence, binding)
            remember(context, evidence, binding, geometry=True)
            pytest.fail("Injected unpublished rejection was not reached")

        monkeypatch.setattr(host.doc, "_apply_result", unpublished)
    monkeypatch.setattr(host.doc, "_remember_evidence", remember)
    monkeypatch.setattr(ports.Storage, "__setattr__", set_value)
    monkeypatch.setattr(host.modules.guarded_evidence.EvidencePublication, "cancel", cancel)
    with pytest.raises(host.modules.guarded_transport.GuardedOperationError) as failure:
        run(host, "export_step")
    assert failure.value.historical_export is host.evidence[0]
    assert not failure.value.outcome_unknown
    assert "Confirmed STEP written:" in str(failure.value)
    assert state.status == "READY" and state.geometry_status == "PASSED"
    assert control.pointer_calls == pointer_calls_at_rejection[0]
    assert control.failed_pointer_calls == 0
    assert control.key not in host.doc._RUNTIME
    assert control.key not in host.doc._GEOMETRY_RUNTIME
    assert cancellations == [not consumed]
    assert_unverified(host)
    with pytest.raises(ValueError, match="no longer available|cancelled"):
        host.evidence[0].publication.consume(
            host.selected, owner_token=host.owners[0], expected_result_version=3
        )
    assert_once(host)


def test_unreadable_scene_equality_preserves_record_but_readers_fail_closed(host, monkeypatch):
    control = scene_wrapper_port(host, distinct=True)
    state = host.context.scene.mechanical_cad
    original_remember = host.doc._remember_evidence
    original_setattr = ports.Storage.__setattr__
    retained = []
    pointer_calls_at_rejection = []

    def set_value(self, name, value):
        if self is state and control.equality_revoked and name == "geometry_report_json":
            raise ReferenceError("First historical RNA storage write is unavailable")
        return original_setattr(self, name, value)

    def remember(*args, **kwargs):
        original_remember(*args, **kwargs)
        if kwargs.get("geometry"):
            retained.extend(
                records[control.key] for records in (host.doc._RUNTIME, host.doc._GEOMETRY_RUNTIME)
            )
            control.equality_revoked = True
            pointer_calls_at_rejection.append(control.pointer_calls)
            raise RuntimeError("Injected invalid RNA after runtime insertion")

    monkeypatch.setattr(ports.Storage, "__setattr__", set_value)
    monkeypatch.setattr(host.doc, "_remember_evidence", remember)
    with pytest.raises(host.modules.guarded_transport.GuardedOperationError) as failure:
        run(host, "export_step")
    assert failure.value.historical_export is host.evidence[0]
    assert control.pointer_calls == pointer_calls_at_rejection[0]
    assert host.doc._RUNTIME[control.key] is retained[0]
    assert host.doc._GEOMETRY_RUNTIME[control.key] is retained[1]
    assert state.status == "READY" and state.geometry_status == "PASSED"
    assert_unverified(host)
    assert_once(host)


@pytest.mark.parametrize("reject", [False, True])
def test_result2_owner_publication_and_rejection_semantics_are_unchanged(host, monkeypatch, reject):
    fixtures = ROOT / "tests/fixtures/geometry_v3/legacy_recovered_69d0f81"
    operation = json.loads((fixtures / "05_v2_export_step.request.raw").read_bytes())
    inner = json.loads((fixtures / "05_v2_export_step.response.raw").read_bytes())
    state = host.context.scene.mechanical_cad
    state.document_json = json.dumps(operation["document"])
    monkeypatch.setattr(
        host.modules.backend_runtime, "configuration", lambda _context: (host.selected, 0.03)
    )
    snapshots = importlib.import_module(ports.PACKAGE + ".part_contracts_v3")

    def result(port):
        port.state = "consumed"
        response = copy.deepcopy(inner)
        response["input_fingerprint"] = snapshots.input_fingerprint(
            port.prepared.operation_request()
        )
        response["export"]["destination"] = host.destination
        return synthetic_outer(port.prepared, response, port.selection)

    monkeypatch.setattr(host.modules.guarded_transport.SidecarJob, "result", result)
    retained = []
    if reject:

        def reject_unpublished(context, _document, evidence, binding):
            # A synthetic pre-consume insertion checks that the v3 correction
            # does not silently change legacy cleanup/cancellation semantics.
            host.doc._remember_evidence(context, evidence, binding)
            host.doc._remember_evidence(context, evidence, binding, geometry=True)
            key = host.doc._scene_key(context.scene)
            retained.extend(
                records[key] for records in (host.doc._RUNTIME, host.doc._GEOMETRY_RUNTIME)
            )
            raise RuntimeError("Injected legacy pre-consume rejection")

        monkeypatch.setattr(host.doc, "_apply_result", reject_unpublished)
    assert run(host, "export_step") is (not reject)
    assert host.prepared[0].operation_request()["result_version"] == 2
    assert json.loads(state.geometry_report_json)["result_version"] == 2
    evidence = host.evidence[0]
    if reject:
        key = host.doc._scene_key(host.context.scene)
        assert host.doc._RUNTIME[key] is retained[0]
        assert host.doc._GEOMETRY_RUNTIME[key] is retained[1]
        assert state.geometry_status == "OUTDATED"
        assert_unverified(host)
        assert evidence.publication.consume(
            host.selected, owner_token=host.owners[0], expected_result_version=2
        )
    else:
        assert host.doc.part_is_current(host.context)
        assert host.doc.geometry_report_is_current(host.context)
        with pytest.raises(ValueError, match="no longer available"):
            evidence.publication.consume(
                host.selected, owner_token=host.owners[0], expected_result_version=2
            )
    assert_once(host)
