"""Pure Gate-B Part owner ports, using recorded geometry and synthetic receipts.

These tests launch no native solver, kernel, sidecar, or Blender. Request hashes
are rebound only by this explicitly synthetic test port when adding the owner's
mesh option or selecting the recorded profile. This is owner/transaction coverage,
not fresh native execution or Blender display qualification.
"""

import copy
import importlib
import importlib.util
import json
import sys
import types
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from captured_backend_fixture import captured_backend as captured_backend

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/arc_authoring_evidence"
_spec = importlib.util.spec_from_file_location(
    "arc_part_owner_host_ports", ROOT / "tests/integration/service_v3_owner_fakes.py"
)
ports = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ports)
# This helper is also loaded independently by other owner suites. Give this
# suite its own cached production-module namespace so its display recorder and
# the modules under test always belong to the same host port.
ports.PACKAGE = "mcad_arc_part_owner_boundary_tests"


def recorded(label="radius_edit_5_0_replay", *, profile=False, selected_profile=False):
    if label.startswith("rectangle"):
        request = json.loads((FIXTURES / (label + ".request.raw")).read_text(encoding="utf-8"))
        request.pop("backend_contract")
        response = json.loads((FIXTURES / (label + ".response.raw")).read_text(encoding="utf-8"))
        response.pop("backend_receipt")
    else:
        request = json.loads((FIXTURES / (label + ".operation.json")).read_text(encoding="utf-8"))
        response = json.loads((FIXTURES / (label + ".response")).read_text(encoding="utf-8"))
    request["options"] = {"linear_deflection": 0.1}
    if profile:
        request["document"]["features"] = request["document"]["features"][:1]
        response["result"]["features"] = response["result"]["features"][:1]
    if profile or selected_profile:
        identifier = request["document"]["features"][0]["id"]
        request["document"]["active_feature"] = identifier
        response["result"]["active_feature"] = identifier
    return request, response


def blank():
    return dict(
        schema_version=1,
        id="blank",
        name="Blank",
        units="mm",
        parameters={},
        features=[],
        active_feature=None,
    )


def synthetic_evidence(owners, prepared, response, selected, owner):
    """Adapt exact request identity around recorded inner geometry, explicitly synthetic."""
    snapshots = importlib.import_module(ports.PACKAGE + ".part_contracts_v3")
    request = prepared.operation_request()
    response = copy.deepcopy(response)
    response["input_fingerprint"] = snapshots.input_fingerprint(request)
    response["result"]["document_hash"] = snapshots.document_hash(
        snapshots._expected_document(request["document"])
    )
    required = prepared.guarded_request()["backend_contract"]["required_capabilities"]
    response["backend_receipt"] = dict(
        version=1,
        request_id=prepared.request_id,
        request_fingerprint=prepared.fingerprint,
        required_capabilities=required,
        confirmed_capabilities=required[:],
        missing_capabilities=[],
        phase="dispatched",
        backend=dict(
            core_version="synthetic-part-owner-port",
            project_root=selected.project_root,
            core_origin=selected.core_origin,
            solver_origin=str(Path(selected.core_origin) / "sketch_solver.py"),
            python_executable=selected.python_executable,
            python_executable_target=selected.python_executable_target,
            python_prefix="/synthetic/prefix",
            python_base_prefix="/synthetic/base",
            python_version=[3, 12, 14],
        ),
    )
    return owners.guarded_evidence.accept_response(prepared, response, selected, owner_token=owner)


def real_display(owners):
    name = "arc_part_disposable_display_port"
    if name + ".display" in sys.modules:
        return sys.modules[name + ".display"]
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
    sys.modules[name] = package
    with patch.dict(sys.modules, {"bpy": owners.bpy, name + ".workspace": owners.workspace}):
        module = importlib.import_module(name + ".display")
        retained = {key: value for key, value in sys.modules.items() if key.startswith(name + ".")}
    sys.modules.update(retained)
    return module


@pytest.fixture
def owner(monkeypatch, captured_backend):
    modules = ports.load_owners()
    assert modules.document_state._CandidateDisplay is ports.CandidateDisplay
    selected = captured_backend(
        modules.backend_selection, generation=2, lifetime_id="pure-gate-b-part-port"
    )
    current = [selected]
    monkeypatch.setattr(modules.backend_runtime, "capture", lambda _context: current[0])
    monkeypatch.setattr(
        modules.backend_runtime, "configuration", lambda _context: (current[0], 0.1)
    )
    context = ports.context_for(modules, blank(), selected)
    doc = modules.document_state
    doc._RUNTIME.clear()
    doc._GEOMETRY_RUNTIME.clear()
    ports.CandidateDisplay.events = []
    display = real_display(modules)
    monkeypatch.setattr(doc, "_mesh_payload", display._mesh_payload)
    shown = []

    def show(_context, document, feature, *, result_version=2):
        source = next(item for item in document["features"] if item["id"] == feature["id"])
        shown.append(
            (
                feature["id"],
                result_version,
                display._mesh_payload(feature, source=source, result_version=result_version),
            )
        )

    monkeypatch.setattr(doc, "_display_feature", show)
    monkeypatch.setattr(
        modules.guarded_transport,
        "execute",
        lambda *_args, **_kwargs: pytest.fail("No native/transport launch in publication tests"),
    )
    yield types.SimpleNamespace(
        modules=modules,
        doc=doc,
        context=context,
        selected=selected,
        current=current,
        display=display,
        shown=shown,
    )
    doc._RUNTIME.clear()
    doc._GEOMETRY_RUNTIME.clear()


def prepare(owner, label="radius_edit_5_0_replay", **variant):
    request, response = recorded(label, **variant)
    intent = owner.modules.part_publication.prepare(owner.context, request["document"])
    evidence = synthetic_evidence(
        owner.modules, intent.prepared, response, owner.current[0], intent.owner_token
    )
    return intent, evidence


def publish(owner, label="radius_edit_5_0_replay", **variant):
    intent, evidence = prepare(owner, label, **variant)
    assert intent.publish(owner.context, evidence)
    return evidence


@pytest.mark.parametrize("variant", [{}, {"profile": True}, {"selected_profile": True}])
def test_whole_candidate_profile_solid_and_selected_upstream_publish_once(owner, variant):
    intent, evidence = prepare(owner, **variant)
    prepared = intent.prepared
    assert prepared.operation_request()["result_version"] == 3
    assert intent.publish(owner.context, evidence)
    assert intent.retired
    assert owner.doc.part_is_current(owner.context)
    assert owner.doc.current_part_result(owner.context)["result_version"] == 3
    assert owner.doc.current_part_evidence(owner.context)[0] is evidence
    record = owner.doc._RUNTIME[owner.context.scene.as_pointer()]
    assert record["prepared"] is prepared and record["result_version"] == 3
    assert record["request_fingerprint"] == prepared.fingerprint
    assert owner.shown[-1][1] == 3 and owner.shown[-1][2][1]
    with pytest.raises(owner.modules.bridge.BridgeError, match="retired"):
        intent.publish(owner.context, evidence)
    with pytest.raises(ValueError, match="no longer available"):
        evidence.publication.consume(
            owner.selected, owner_token=record["owner_token"], expected_result_version=3
        )


def test_same_id_radius_edit_retains_authored_points_and_constraint_expression(owner):
    publish(owner)
    original = json.loads(owner.context.scene.mechanical_cad.document_json)
    old_volume = owner.context.scene.mechanical_cad.volume
    publish(owner, "radius_edit_7_0_replay")
    updated = json.loads(owner.context.scene.mechanical_cad.document_json)
    assert original["features"] == updated["features"]
    assert original["parameters"]["radius"] == 5
    assert updated["parameters"]["radius"] == 7
    assert old_volume == pytest.approx(196.34954084936206)
    assert owner.context.scene.mechanical_cad.volume == pytest.approx(384.84510006474966)
    assert owner.doc.part_is_current(owner.context)


def test_legacy_control_stays_explicit_v2(owner):
    publish(owner, "rectangle_replay2")
    assert owner.doc.current_part_result(owner.context)["result_version"] == 2
    assert owner.shown[-1][1] == 2


@pytest.mark.parametrize("requested", [1, 2, True, False, 3.0, "3", [], {}])
def test_schema3_explicit_mismatch_rejects_before_launch(owner, requested):
    document = recorded()[0]["document"]
    before = owner.doc._snapshot_fields(owner.context.scene.mechanical_cad)
    with pytest.raises(owner.modules.bridge.BridgeError, match="result version"):
        owner.doc._run_sidecar(owner.context, document, result_version=requested)
    assert owner.doc._snapshot_fields(owner.context.scene.mechanical_cad) == before


def test_schema3_empty_and_inactive_select3_and_real_undo_selects2(owner):
    document = recorded()[0]["document"]
    sketch = document["features"][0]["sketch"]
    sketch["arcs"], sketch["constraints"] = [], []
    legacy = recorded("rectangle_replay2")[0]["document"]
    old = copy.deepcopy(legacy)
    feature = document["features"][0]
    feature["id"] = "inactive_schema3"
    legacy["features"].append(feature)
    assert owner.doc._result_version(legacy) == 3
    legacy["features"].pop()
    assert legacy == old and owner.doc._result_version(legacy) == 2
    with pytest.raises(owner.modules.bridge.BridgeError):
        owner.doc._result_version(legacy, 3)


@pytest.mark.parametrize(
    "action", ["check_geometry", "export_step", "export_stl", "canonical_snapshot"]
)
def test_action_specific_version_barrier_keeps_only_eligible_sector_output(owner, action):
    assert owner.doc._result_version(recorded()[0]["document"], action=action) == (
        None if action == "canonical_snapshot" else 3
    )
    for options in ({"profile": True}, {"selected_profile": True}):
        with pytest.raises(owner.modules.bridge.BridgeError):
            owner.doc._result_version(recorded(**options)[0]["document"], action=action)


@pytest.mark.parametrize("consumer", ["projection", "apply", "intent"])
def test_same_operation_wrong_fresh_G_cannot_enter_any_part_sink(owner, consumer):
    intent, exact = prepare(owner)
    other = owner.modules.backend_contracts.prepare_request(intent.request)
    assert other.fingerprint != intent.prepared.fingerprint
    wrong = synthetic_evidence(
        owner.modules, other, recorded()[1], owner.selected, intent.owner_token
    )
    before = owner.doc._snapshot_fields(owner.context.scene.mechanical_cad)

    def action():
        if consumer == "intent":
            return intent.publish(owner.context, wrong)
        if consumer == "apply":
            return owner.doc._apply_result(
                owner.context, intent.request["document"], wrong, intent._binding
            )
        return owner.doc._evidence_projection(
            owner.context, intent.request["document"], wrong, intent._binding, consume=True
        )

    with pytest.raises(owner.modules.bridge.BridgeError, match="operation"):
        action()
    assert owner.doc._snapshot_fields(owner.context.scene.mechanical_cad) == before
    assert not ports.CandidateDisplay.events
    assert exact.publication.consume(
        owner.selected, owner_token=intent.owner_token, expected_result_version=3
    )


@pytest.mark.parametrize(
    "mutation",
    ["other_G", "version", "missing_prepared", "missing_version", "owner", "epoch", "document"],
)
def test_current_readers_recheck_original_G_version_source_and_owner(owner, mutation):
    evidence = publish(owner)
    record = owner.doc._RUNTIME[owner.context.scene.as_pointer()]
    if mutation == "other_G":
        other = owner.modules.backend_contracts.prepare_request(evidence.operation_request())
        record["evidence"] = synthetic_evidence(
            owner.modules, other, recorded()[1], owner.selected, record["owner_token"]
        )
    elif mutation == "version":
        record["result_version"] = 2
    elif mutation == "missing_prepared":
        del record["prepared"]
    elif mutation == "missing_version":
        del record["result_version"]
    elif mutation == "owner":
        record["owner_token"] = object()
    elif mutation == "epoch":
        owner.current[0] = replace(owner.selected, generation=owner.selected.generation + 2)
    else:
        owner.context.scene.mechanical_cad.document_json += " "
    assert not owner.doc.part_is_current(owner.context)
    assert owner.doc.current_part_result(owner.context) is None
    assert owner.doc.current_part_evidence(owner.context) is None


def test_public_projection_cannot_replace_evidence(owner):
    intent, evidence = prepare(owner)
    with pytest.raises(owner.modules.bridge.BridgeError, match="guarded evidence"):
        intent.publish(owner.context, evidence.response_snapshot())
    assert not ports.CandidateDisplay.events


@pytest.mark.parametrize("phase", ["display", "layout", "post_apply"])
@pytest.mark.parametrize("revoke", [False, True])
def test_rollback_preserves_old_part_but_cannot_revive_ABA(owner, monkeypatch, phase, revoke):
    original = publish(owner)
    before = owner.context.scene.mechanical_cad.document_json
    intent, evidence = prepare(owner, "radius_edit_7_0_replay")
    doc = owner.doc

    def fail():
        if revoke:
            owner.current[0] = replace(owner.selected, generation=owner.selected.generation + 2)
        raise RuntimeError("injected publication failure")

    if phase == "display":
        monkeypatch.setattr(doc, "_display_feature", lambda *_args, **_kwargs: fail())
    elif phase == "layout":
        monkeypatch.setattr(intent, "_publish_layout", lambda _context: fail())
    else:
        original_apply = doc._apply_result

        def after_apply(*args, **kwargs):
            original_apply(*args, **kwargs)
            fail()

        monkeypatch.setattr(doc, "_apply_result", after_apply)
    with pytest.raises(RuntimeError, match="injected publication"):
        intent.publish(owner.context, evidence)
    assert owner.context.scene.mechanical_cad.document_json == before
    assert "rollback" in ports.CandidateDisplay.events
    assert doc.part_is_current(owner.context) is (not revoke)
    assert (doc.current_part_evidence(owner.context) or [None])[0] is (None if revoke else original)
    assert intent.retired
    with pytest.raises(ValueError, match="no longer available"):
        evidence.publication.consume(
            owner.selected, owner_token=intent.owner_token, expected_result_version=3
        )


def test_layout_callback_cannot_read_new_current_before_CAS(owner, monkeypatch):
    publish(owner)
    intent, evidence = prepare(owner, "radius_edit_7_0_replay")
    checked = []

    def layout(_context):
        checked.append(owner.doc.current_part_result(owner.context))

    monkeypatch.setattr(intent, "_publish_layout", layout)
    assert intent.publish(owner.context, evidence)
    assert checked == [None]
    assert owner.doc.part_is_current(owner.context)


@pytest.mark.parametrize(
    "field", ["workspace", "window", "view_layer", "owner_id", "units", "draft", "layout"]
)
def test_finish_exact_context_and_layout_CAS_rejects_before_mutation(owner, field):
    intent, evidence = prepare(owner)
    state = owner.context.scene.mechanical_cad
    if field in {"workspace", "window", "view_layer"}:
        setattr(owner.context, field, object())
    elif field == "owner_id":
        state.owner_id = "new-owner"
    elif field == "units":
        owner.context.scene.unit_settings.scale_length = 0.1
    elif field == "draft":
        state.sketch_draft_json = "newer raw draft"
    else:
        # Layout CAS is relevant only when this Finish will publish layout.
        intent._annotation_after = "pending layout"
        state.sketch_annotation_json = "newer independent layout"
    before = owner.doc._snapshot_fields(state)
    with pytest.raises(owner.modules.bridge.BridgeError):
        intent.publish(owner.context, evidence)
    assert owner.doc._snapshot_fields(state) == before
    assert not ports.CandidateDisplay.events


@pytest.mark.parametrize("mutation", ["source", "region", "mesh", "version", "solved_arc"])
def test_result3_profile_display_is_strict_and_does_not_reconstruct_v2(owner, mutation):
    request, response = recorded()
    source, feature = request["document"]["features"][0], response["result"]["features"][0]
    version = 3
    if mutation == "source":
        source["id"] = "wrong-source"
    elif mutation == "region":
        feature["output"]["profile"]["region_kind"] = "line_loop"
    elif mutation == "mesh":
        feature["mesh"] = None
    elif mutation == "version":
        version = 2
    else:
        feature["sketch"]["solved"]["arcs"][0]["direction"] = "cw"
    with pytest.raises(owner.display.bridge.BridgeError):
        owner.display._mesh_payload(feature, source=source, result_version=version)


def test_rejected_exact_finish_cancels_available_claim(owner):
    intent, evidence = prepare(owner)
    owner.context.scene.mechanical_cad.sketch_draft_json = "newer intent"
    with pytest.raises(owner.modules.bridge.BridgeError):
        intent.publish(owner.context, evidence)
    assert intent.retired
    with pytest.raises(ValueError, match="cancelled"):
        evidence.revalidate(
            owner.selected, owner_token=intent.owner_token, expected_result_version=3
        )


def test_sync_commit_captures_one_prepared3_and_keeps_original_request(owner, monkeypatch):
    request, response = recorded()
    captured = []

    def execute(prepared, selected, *, owner_token, current_selection):
        assert current_selection() == selected
        assert prepared.operation_request() == request
        captured.append(prepared)
        return synthetic_evidence(owner.modules, prepared, response, selected, owner_token)

    monkeypatch.setattr(owner.modules.guarded_transport, "execute", execute)
    assert owner.doc._commit_candidate(owner.context, request["document"])
    assert len(captured) == 1
    assert owner.doc._RUNTIME[owner.context.scene.as_pointer()]["prepared"] is captured[0]


def test_arc_empty3_open_chain_keeps_typed_wire_and_legacy_defaults(owner):
    path = ROOT / "tests/fixtures/result_v3/legacy_30383a1"
    request = json.loads((path / "replay_open_line_sketch.request.txt").read_text(encoding="utf-8"))
    response = json.loads((path / "replay_open_line_sketch.stdout.txt").read_text(encoding="utf-8"))
    source, feature = request["document"]["features"][0], response["result"]["features"][0]
    for sketch in (source["sketch"], feature["sketch"]["solved"]):
        sketch["schema_version"] = 3
        sketch["arcs"] = []
    wire = owner.display.solved_line_wire(feature, source, result_version=3)
    assert wire["triangles"] == [] and len(wire["edges"]) == 2
    assert owner.display._mesh_payload(feature, source=source, result_version=3) == (
        wire["vertices"],
        wire["triangles"],
        wire["edges"],
    )
    with pytest.raises(ValueError):
        owner.display.solved_line_wire(feature, source)
    assert source["sketch"]["schema_version"] == 3


def test_display_imports_and_owner_predicates_never_launch_native(owner, monkeypatch):
    publish(owner)
    monkeypatch.setattr(
        owner.doc, "_run_sidecar", lambda *_args, **_kwargs: pytest.fail("reader launched native")
    )
    for _ in range(3):
        assert owner.doc.part_is_current(owner.context)
        assert owner.doc.current_part_result(owner.context)
        assert owner.doc.current_part_evidence(owner.context)
    for module in (owner.display, owner.doc):
        assert "service_v3" not in vars(module)


@pytest.mark.parametrize("action", ["solve_sketch", "check_geometry"])
def test_publication_intent_constructor_refuses_nonreplay_prepared_action(owner, action):
    request = recorded()[0]
    if action == "check_geometry":
        request = recorded("rectangle_replay2")[0]
    request["action"] = action
    if action == "solve_sketch":
        request.pop("options")
        request["feature_id"] = request["document"]["features"][0]["id"]
    prepared = owner.modules.backend_contracts.prepare_request(request)
    with pytest.raises(owner.modules.bridge.BridgeError, match="prepared replay"):
        owner.modules.part_publication.PartPublicationIntent(
            owner.context, prepared, owner.selected, ""
        )


def test_sync_rejected_candidate_callback_cancels_unconsumed_replay(owner, monkeypatch):
    request, response = recorded()
    captured = []

    def execute(prepared, selected, *, owner_token, current_selection):
        evidence = synthetic_evidence(owner.modules, prepared, response, selected, owner_token)
        captured.append((evidence, owner_token))
        return evidence

    def reject(_evidence, _binding):
        raise RuntimeError("candidate callback rejection")

    monkeypatch.setattr(owner.modules.guarded_transport, "execute", execute)
    with owner.doc.replay_guard(owner.context):
        with pytest.raises(RuntimeError, match="candidate callback"):
            owner.doc._commit_candidate_locked(
                owner.context, request["document"], validate_result=reject
            )
    evidence, token = captured[0]
    with pytest.raises(ValueError, match="cancelled"):
        evidence.revalidate(owner.selected, owner_token=token, expected_result_version=3)


def test_retired_intent_G_cannot_be_adopted_by_second_same_operation_and_owner(owner):
    original, evidence = prepare(owner)
    original.retire()
    constructor = owner.modules.part_publication.PartPublicationIntent
    with pytest.raises(owner.modules.bridge.BridgeError, match="not a prepared replay"):
        constructor(
            owner.context, original.prepared, owner.selected, "", owner_token=original.owner_token
        )
    second = constructor(
        owner.context, original.request, owner.selected, "", owner_token=original.owner_token
    )
    assert second.request == original.request
    assert second.prepared.request_id != original.prepared.request_id
    assert second.prepared.fingerprint != original.prepared.fingerprint
    before = owner.doc._snapshot_fields(owner.context.scene.mechanical_cad)
    with pytest.raises(owner.modules.bridge.BridgeError, match="different guarded operation"):
        second.publish(owner.context, evidence)
    assert second.retired
    assert evidence.publication._state == "available"
    assert evidence.revalidate(
        owner.selected, owner_token=original.owner_token, expected_result_version=3
    )
    assert owner.doc._snapshot_fields(owner.context.scene.mechanical_cad) == before
    assert not ports.CandidateDisplay.events
    with pytest.raises(owner.modules.bridge.BridgeError, match="retired"):
        original.publish(owner.context, evidence)
    assert evidence.publication._state == "cancelled"
    with pytest.raises(ValueError, match="cancelled"):
        evidence.revalidate(
            owner.selected, owner_token=original.owner_token, expected_result_version=3
        )


def test_constructor_new_nonce_is_launched_and_publishes_its_own_completion(owner):
    request, response = recorded()
    constructor = owner.modules.part_publication.PartPublicationIntent
    token = object()
    first = constructor(owner.context, request, owner.selected, "", owner_token=token)
    second = constructor(owner.context, request, owner.selected, "", owner_token=token)
    assert first.prepared.operation_request() == second.prepared.operation_request() == request
    assert first.prepared.request_id != second.prepared.request_id
    request["document"]["name"] = "changed caller snapshot"
    assert second.request["document"]["name"] != request["document"]["name"]
    evidence = synthetic_evidence(owner.modules, second.prepared, response, owner.selected, token)
    assert second.publish(owner.context, evidence)
    assert owner.doc.part_is_current(owner.context)
    first.retire()


@pytest.mark.parametrize(
    "mutation", ["action", "protocol", "version", "extra", "options", "deflection"]
)
def test_constructor_validates_operation_before_minting_fresh_G(owner, monkeypatch, mutation):
    operation = recorded()[0]
    if mutation == "action":
        operation["action"] = "solve_sketch"
    elif mutation == "protocol":
        operation["protocol_version"] = True
    elif mutation == "version":
        operation["result_version"] = 2
    elif mutation == "extra":
        operation["backend_contract"] = {}
    elif mutation == "options":
        operation["options"]["extra"] = True
    else:
        operation["options"]["linear_deflection"] = 0.2
    monkeypatch.setattr(
        owner.modules.backend_contracts,
        "prepare_request",
        lambda *_args, **_kwargs: pytest.fail("invalid operation minted G"),
    )
    with pytest.raises(owner.modules.bridge.BridgeError):
        owner.modules.part_publication.PartPublicationIntent(
            owner.context, operation, owner.selected, ""
        )
