"""Gate-B downstream barriers with native-free production owner host ports.

Recorded inner packets retain their historical provenance. Outer receipts below
are explicitly synthetic portable test ports, not fresh native qualification.
"""

import copy
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from test_arc_guarded_evidence import recorded, synthetic_outer
from test_assembly_bridge_v3 import make as make_assembly3  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "arc_downstream_host_ports", ROOT / "tests/integration/service_v3_owner_fakes.py"
)
ports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ports)


def legacy():
    return json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())


def source3(kind="sector"):
    document = recorded("radius_edit_5_0_replay")[0]["document"]
    if kind in {"profile", "selected"}:
        document["active_feature"] = document["features"][0]["id"]
        if kind == "profile":
            document["features"].pop()
    if kind in {"empty", "inactive"}:
        document["features"][0]["sketch"]["arcs"] = []
        document["features"][0]["sketch"]["constraints"] = []
    if kind == "inactive":
        feature = copy.deepcopy(document["features"][0])
        feature["id"] = "inactive_schema3"
        document = legacy()
        document["features"].append(feature)
    return document


def malformed_source3(kind="sector"):
    """Unknown embedded schema must fail even in an inactive/unused source.

    Empty and mixed schema-3 sketches are supported now; their presence alone
    is no longer a reason to reject canonical capture or geometry preflight.
    """
    document = source3(kind)
    sketch = next(
        feature["sketch"] for feature in reversed(document["features"]) if "sketch" in feature
    )
    sketch["schema_version"] = 999
    return document


def assembly(source=None, *, unused=False):
    result = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    if source is not None:
        if unused:
            result["part_sources"].append(
                {"source_document_id": source["id"], "source_digest": "0" * 64, "document": source}
            )
        else:
            result["part_sources"][0]["document"] = source
    return result


@pytest.fixture
def owners(monkeypatch):
    result = ports.load_owners()
    package = ports.PACKAGE
    # Assembly operators now import the shared job UI. This suite never draws,
    # but its existing inert help module must expose that UI's wrapping port.
    monkeypatch.setattr(sys.modules[package + ".help_ui"], "_panel_wrap", ports.noop, raising=False)
    bpy_types = ports.module("bpy.types", Operator=type("Operator", (), {}))
    monkeypatch.setattr(result.bpy, "types", bpy_types, raising=False)
    with patch.dict(
        sys.modules,
        {
            "bpy": result.bpy,
            "bpy.props": ports.module(
                "bpy.props",
                **{
                    name: ports.noop
                    for name in ("BoolProperty", "StringProperty", "EnumProperty", "IntProperty")
                },
            ),
            "bpy.types": bpy_types,
            "bpy_extras": ports.module("bpy_extras"),
            "bpy_extras.io_utils": ports.module(
                "bpy_extras.io_utils",
                ExportHelper=type("ExportHelper", (), {}),
                ImportHelper=type("ImportHelper", (), {}),
            ),
        },
    ):
        for name in (
            "assembly_pending",
            "assembly_operator_helpers",
            "assembly_files",
            "assembly_operators",
            "guarded_operations",
            "operation_contracts",
            "execution_lease",
        ):
            setattr(result, name, importlib.import_module(package + "." + name))
        loaded = {key: value for key, value in sys.modules.items() if key.startswith(package + ".")}
    sys.modules.update(loaded)
    selected = result.backend_selection.BackendSelection.capture(
        str(ROOT),
        sys.executable,
        generation=0,
        lifetime_id="downstream-synthetic-port",
        environment={},
    )
    result.selected = selected
    monkeypatch.setattr(result.backend_runtime, "capture", lambda _context: selected)
    monkeypatch.setattr(result.backend_runtime, "configuration", lambda _context: (selected, 0.1))
    monkeypatch.setattr(
        result.backend_runtime, "assert_current", lambda original, _context: selected
    )
    monkeypatch.setattr(
        result.backend_runtime, "is_current", lambda original, _context: original == selected
    )
    for module in (result.document_state, result.assembly_state):
        module._RUNTIME.clear()
    result.document_state._GEOMETRY_RUNTIME.clear()
    result.assembly_state._BUSY.clear()
    ports.CandidateDisplay.events = []
    yield result
    result.assembly_state._BUSY.clear()
    result.document_state._RUNTIME.clear()
    result.document_state._GEOMETRY_RUNTIME.clear()
    result.assembly_state._RUNTIME.clear()


def context(owners, document=None, assembly_document=None):
    result = ports.context_for(owners, document or legacy(), owners.selected)
    state = result.scene.mechanical_cad_assembly
    for name in owners.assembly_state._STATE_FIELDS:
        setattr(state, name, "accepted:" + name)
    state.document_json = json.dumps(assembly_document or assembly())
    state.status = "READY"
    state.display_status = state.verification_status = "CURRENT"
    return result


def trap(monkeypatch, module, name, calls):
    def unexpected(*_args, **_kwargs):
        calls.append(name)
        raise AssertionError("Unexpected work before source rejection: " + name)

    monkeypatch.setattr(module, name, unexpected)


def guarded(owners, label, *, owner=None):
    operation, inner = recorded(label)
    prepared = owners.backend_contracts.prepare_request(operation)
    owner = owner or object()
    raw = synthetic_outer(prepared, inner, owners.selected)
    evidence = owners.guarded_evidence.accept_response(
        prepared, raw, owners.selected, owner_token=owner
    )
    return prepared, evidence, owner


@pytest.mark.parametrize("kind", ["profile", "selected", "empty", "inactive"])
@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_malformed_schema_rejects_before_lease_runtime_hide_or_transport(
    owners, monkeypatch, kind, action
):
    ctx = context(owners, malformed_source3(kind))
    state = ctx.scene.mechanical_cad
    state.status, state.geometry_status = "READY", "PASSED"
    state.geometry_report_json = '{"accepted":true}'
    key = owners.document_state._scene_key(ctx.scene)
    part_runtime, geometry_runtime = object(), object()
    owners.document_state._RUNTIME[key] = part_runtime
    owners.document_state._GEOMETRY_RUNTIME[key] = geometry_runtime
    before = copy.deepcopy(vars(state))
    calls = []
    for module, name in (
        (owners.execution_lease, "try_acquire"),
        (owners.geometry_operations, "_preflight_owned_display"),
        (owners.geometry_operations, "_hide_owned"),
        (owners.geometry_operations, "_prepare_action"),
        (owners.guarded_transport, "execute"),
    ):
        trap(monkeypatch, module, name, calls)
    with pytest.raises((ValueError, RuntimeError)):
        owners.geometry_operations.run_geometry_action(
            ctx,
            action,
            destination=None if action == "check_geometry" else "/never-written/arc.step",
        )
    assert vars(state) == before and calls == []
    assert owners.document_state._RUNTIME[key] is part_runtime
    assert owners.document_state._GEOMETRY_RUNTIME[key] is geometry_runtime


@pytest.mark.parametrize("kind", ["profile", "selected", "empty", "inactive"])
def test_snapshot_capture_update_block_before_lease_or_prepare(owners, monkeypatch, kind):
    document = malformed_source3(kind)
    ctx = context(owners, document)
    state = ctx.scene.mechanical_cad_assembly
    before = copy.deepcopy(vars(state))
    calls = []
    for module, name in (
        (owners.execution_lease, "try_acquire"),
        (owners.backend_contracts, "prepare_request"),
        (owners.guarded_transport, "execute"),
    ):
        trap(monkeypatch, module, name, calls)
    with pytest.raises((ValueError, RuntimeError)):
        owners.guarded_operations.canonical_snapshot_guarded(
            document,
            selection=owners.selected,
            owner_token=object(),
            current_selection=lambda: owners.selected,
        )
    with pytest.raises((ValueError, RuntimeError)):
        owners.assembly_operator_helpers.canonical_working_part(ctx)
    assert vars(state) == before and calls == []
    for cls in (
        owners.assembly_operators.MCAD_OT_assembly_new,
        owners.assembly_operators.MCAD_OT_assembly_update_source,
    ):
        operator = cls()
        operator.grounded, operator.name, operator.instance_name = True, "Assembly", "Base"
        operator.report = lambda *_args: None
        assert operator.execute(ctx) == {"CANCELLED"}
        after = vars(state).copy()
        assert after.pop("last_action_error")
        expected = before.copy()
        expected.pop("last_action_error")
        assert after == expected and calls == []


@pytest.mark.parametrize("kind", ["profile", "selected", "empty", "inactive"])
@pytest.mark.parametrize("unused", [False, True])
@pytest.mark.parametrize("action", ["assembly_replay", "assembly_check", "assembly_sample"])
def test_all_assembly_sources_preflight_before_sync_and_async_recovery(
    owners, monkeypatch, kind, unused, action
):
    data = assembly(malformed_source3(kind), unused=unused)
    ctx = context(owners, assembly_document=data)
    before = copy.deepcopy(vars(ctx.scene.mechanical_cad_assembly))
    calls = []
    for module, name in (
        (owners.execution_lease, "try_acquire"),
        (owners.assembly_state, "_capture"),
        (owners.assembly_state, "display_is_current"),
        (owners.assembly_state, "_recover_failure"),
        (owners.assembly_state, "_failure"),
        (owners.guarded_transport, "execute"),
    ):
        trap(monkeypatch, module, name, calls)
    sinks = [
        lambda: owners.guarded_operations.assembly_action_guarded(
            data,
            action,
            selection=owners.selected,
            owner_token=object(),
            current_selection=lambda: owners.selected,
        )
    ]
    if action == "assembly_replay":
        sinks += [
            lambda: owners.assembly_state.commit_candidate(ctx, data),
            lambda: owners.assembly_state.replay(ctx),
            lambda: owners.assembly_state.validate_snapshot(ctx),
        ]
    else:
        sinks += [
            lambda: owners.assembly_state._report_only(ctx, action),
            lambda: owners.assembly_pending.prepare(ctx, action, joint_id="slide_a", values=[0]),
        ]
    for sink in sinks:
        with pytest.raises((ValueError, RuntimeError)):
            sink()
        assert vars(ctx.scene.mechanical_cad_assembly) == before
        assert owners.assembly_state._BUSY == set() and calls == []


@pytest.mark.parametrize("kind", ["profile", "empty", "inactive"])
def test_assembly_save_stops_before_tempfile_and_keeps_accepted_report(owners, monkeypatch, kind):
    ctx = context(owners, assembly_document=assembly(malformed_source3(kind), unused=True))
    state = ctx.scene.mechanical_cad_assembly
    before = copy.deepcopy(vars(state))
    calls = []
    trap(monkeypatch, owners.assembly_files.tempfile, "NamedTemporaryFile", calls)
    trap(monkeypatch, owners.assembly_files.os, "replace", calls)
    trap(monkeypatch, owners.assembly_state, "_failure", calls)
    operator = owners.assembly_files.MCAD_OT_assembly_save()
    operator.filepath = "/never-written/arc-assembly.json"
    operator.report = lambda *_args: None
    assert operator.execute(ctx) == {"CANCELLED"}
    after = vars(state).copy()
    assert after.pop("last_action_error")
    before.pop("last_action_error")
    assert after == before and calls == []


@pytest.mark.parametrize("kind", ["sector", "empty", "inactive"])
def test_source_update_query_is_nonmutating_for_schema3(owners, kind):
    ctx = context(owners, source3(kind))
    before = copy.deepcopy(vars(ctx.scene.mechanical_cad_assembly))
    assert owners.assembly_state.source_updates(ctx, update=True) == []
    assert vars(ctx.scene.mechanical_cad_assembly) == before


@pytest.mark.parametrize("consume", [False, True])
@pytest.mark.parametrize("label", ["rectangle_replay3", "rectangle_solve3"])
def test_genuine_recorded_rectangle3_rejected_by_accept_alias_and_seeds(owners, consume, label):
    prepared, evidence, owner = guarded(owners, label)
    document = prepared.operation_request()["document"]
    draft = owners.sketch_draft.RectangleDraft(json.dumps(document), "sketch_1", is_edit=True)
    with pytest.raises(ValueError, match="action|result version"):
        draft.accept_guarded_replay(
            document, evidence, owners.selected, owner_token=owner, consume=consume
        )
    draft._guarded_evidence, draft._guarded_owner = evidence, owner
    draft._guarded_candidate = json.dumps(draft.candidate(), sort_keys=True, allow_nan=False)
    with pytest.raises(ValueError, match="action|result version"):
        draft.guarded_seed_points(owners.selected)
    assert not draft.guarded_is_current(owners.selected)
    assert evidence.publication.consume(
        owners.selected,
        owner_token=owner,
        expected_action=prepared.action,
        expected_result_version=3,
    )


def test_rectangle2_preview_seed_and_single_consume_remain_supported(owners):
    prepared, evidence, owner = guarded(owners, "rectangle_replay2")
    document = prepared.operation_request()["document"]
    draft = owners.sketch_draft.RectangleDraft(json.dumps(document), "sketch_1", is_edit=True)
    assert draft.accept_guarded_replay(
        document, evidence, owners.selected, owner_token=owner, consume=True
    )
    assert draft.guarded_is_current(owners.selected)
    assert len(draft.guarded_seed_points(owners.selected)) == 4
    with pytest.raises(ValueError, match="no longer available"):
        draft.accept_guarded_replay(
            document, evidence, owners.selected, owner_token=owner, consume=True
        )


@pytest.mark.parametrize("label", ["rectangle_replay3", "rectangle_solve3"])
def test_rectangle_preview_and_fresh_finish_cannot_inherit_rectangle3(owners, monkeypatch, label):
    prepared, evidence, owner = guarded(owners, label)
    document = prepared.operation_request()["document"]
    ctx = context(owners, document)
    session = owners.viewport_sketch.RectangleSession(ctx, "sketch_1")
    monkeypatch.setattr(
        owners.document_state, "current_part_evidence", lambda _context: (evidence, owner)
    )
    assert not session.initialize_preview(ctx)
    calls = []

    def substitute(_context, candidate, *, binding, result_version):
        calls.append(result_version)
        return evidence

    monkeypatch.setattr(owners.document_state, "_run_sidecar", substitute)
    before = ctx.scene.mechanical_cad.document_json
    assert not session.finish(ctx)
    assert calls == [2] and ctx.scene.mechanical_cad.document_json == before
    assert session.alive and not ports.CandidateDisplay.events


@pytest.mark.parametrize("kind", ["sector", "empty", "inactive"])
def test_rectangle_cannot_start_in_any_schema3_part(owners, monkeypatch, kind):
    ctx = context(owners, source3(kind))
    calls = []
    trap(monkeypatch, owners.execution_lease, "try_acquire", calls)
    with pytest.raises(ValueError):
        owners.sketch_draft.RectangleDraft(ctx.scene.mechanical_cad.document_json)
    with pytest.raises(ValueError):
        owners.viewport_sketch.RectangleSession(ctx)
    assert calls == []


@pytest.mark.parametrize(
    "label", ["rectangle_replay3", "radius_edit_5_0_replay", "radius_edit_5_0_solve_sketch"]
)
def test_downstream_aliases_reject_real_v3_inner_evidence(owners, label):
    prepared, evidence, owner = guarded(owners, label)
    ctx = context(owners)
    snapshot = {"prepared": prepared, "selection": owners.selected, "owner_token": owner}
    with pytest.raises((ValueError, RuntimeError)):
        owners.assembly_state._projection(
            ctx, snapshot, evidence, actions="assembly_replay", consume=True
        )
    with pytest.raises((ValueError, RuntimeError)):
        owners.assembly_display._validated(evidence, owner, lambda: owners.selected, consume=True)
    with pytest.raises((ValueError, RuntimeError)):
        owners.geometry_operations._historical_projection(
            evidence, prepared, snapshot, prepared.action
        )
    assert evidence.publication.consume(
        owners.selected,
        owner_token=owner,
        expected_action=prepared.action,
        expected_result_version=3,
    )


@pytest.mark.parametrize("kind", ["profile", "selected", "empty", "inactive"])
def test_geometry_poll_and_export_invoke_are_read_only_rejections(owners, kind):
    ctx = context(owners, malformed_source3(kind))
    state = ctx.scene.mechanical_cad
    before = copy.deepcopy(vars(state))
    assert not owners.geometry_operations.MCAD_OT_check_geometry.poll(ctx)
    for cls in (
        owners.geometry_operations.MCAD_OT_export_step,
        owners.geometry_operations.MCAD_OT_export_stl,
    ):
        assert not cls.poll(ctx)
        operator = cls()
        reports = []
        operator.report = lambda level, message, reports=reports: reports.append(message)
        assert operator.invoke(ctx, None) == {"CANCELLED"}
        assert reports
    assert vars(state) == before
    assert owners.geometry_operations.MCAD_OT_check_geometry.poll(context(owners))


def synthetic_geometry(owners, prepared, owner):
    """Host-port action/check/export facts; no destination is written by this test."""
    _, inner = recorded("rectangle_replay2")
    operation = prepared.operation_request()
    action = operation["action"]
    active = next(
        row for row in inner["result"]["features"] if row["id"] == inner["result"]["active_feature"]
    )
    mesh = {
        "watertight": True,
        "consistently_oriented": True,
        "vertex_manifold": True,
        "vertices": 8,
        "triangles": len(active["mesh"]["triangles"]),
        "signed_volume": active["stats"]["volume"],
        "weld_tolerance": 1e-7,
    }
    checks = {"brep": active["stats"], "mesh": mesh, "linear_deflection_mm": 0.1}
    if action == "export_stl":
        checks.update(
            encoded_mesh=copy.deepcopy(mesh),
            encoding={
                "maximum_vertex_error_mm": 0.0,
                "allowed_vertex_error_mm": 1e-5,
                "independent_precision_ceiling_mm": 1e-5,
            },
        )
    exported = None
    if action != "check_geometry":
        exported = {
            "format": "STL" if action == "export_stl" else "STEP",
            "destination": operation["destination"],
            "bytes": 84 + 50 * mesh["triangles"] if action == "export_stl" else 1234,
            "units": "mm",
            "document_hash": inner["result"]["document_hash"],
            "active_feature": inner["result"]["active_feature"],
            "linear_deflection_mm": 0.1,
            "atomic_replace": True,
        }
    inner.update(
        action=action,
        geometry_check=checks,
        export=exported,
        input_fingerprint=owners.part_result_bridge.snapshots.input_fingerprint(operation),
    )
    return owners.guarded_evidence.accept_response(
        prepared,
        synthetic_outer(prepared, inner, owners.selected),
        owners.selected,
        owner_token=owner,
    )


@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_legacy_geometry_current_positive_preserves_part_binding(
    owners, monkeypatch, action, tmp_path
):
    operation, _ = recorded("rectangle_replay2")
    ctx = context(owners, operation["document"])
    calls = []
    destination = tmp_path / ("part.stl" if action == "export_stl" else "part.step")
    destination.write_text("existing destination sentinel")

    def execute(prepared, selected, *, owner_token, current_selection):
        calls.append(prepared)
        return synthetic_geometry(owners, prepared, owner_token)

    monkeypatch.setattr(owners.guarded_transport, "execute", execute)
    assert owners.geometry_operations.run_geometry_action(
        ctx, action, destination=None if action == "check_geometry" else str(destination)
    ), ctx.scene.mechanical_cad.geometry_message
    state = ctx.scene.mechanical_cad
    assert len(calls) == 1 and state.status == "READY" and state.geometry_status == "PASSED"
    assert owners.document_state.part_is_current(ctx)
    assert owners.document_state.geometry_report_is_current(ctx)
    assert destination.read_text() == "existing destination sentinel"


@pytest.mark.parametrize("action", ["export_step", "export_stl"])
@pytest.mark.parametrize(
    "failure",
    ["stale_publish", "historical_exception", "lost_reply", "malformed_reply", "predispatch"],
)
def test_legacy_export_outdated_written_vs_unknown_never_retries(
    owners, monkeypatch, action, failure, tmp_path
):
    operation, _ = recorded("rectangle_replay2")
    ctx = context(owners, operation["document"])
    destination = tmp_path / ("part.stl" if action == "export_stl" else "part.step")
    destination.write_text("existing destination sentinel")
    calls = []

    def execute(prepared, selected, *, owner_token, current_selection):
        calls.append(prepared)
        if failure in {"lost_reply", "malformed_reply", "predispatch"}:
            raise owners.guarded_transport.GuardedOperationError(
                failure, outcome_unknown=failure != "predispatch"
            )
        evidence = synthetic_geometry(owners, prepared, owner_token)
        if failure == "historical_exception":
            raise owners.guarded_transport.GuardedOperationError(
                "stale", historical_export=evidence
            )
        return evidence

    monkeypatch.setattr(owners.guarded_transport, "execute", execute)
    if failure == "stale_publish":

        def reject_publication(*_args, **_kwargs):
            raise owners.bridge.BridgeError("Current publication no longer matches")

        monkeypatch.setattr(owners.document_state, "_evidence_projection", reject_publication)
    assert not owners.geometry_operations.run_geometry_action(
        ctx, action, destination=str(destination)
    )
    state = ctx.scene.mechanical_cad
    report = json.loads(state.geometry_report_json)
    expected = (
        "OUTDATED"
        if failure in {"stale_publish", "historical_exception"}
        else ("FAILED" if failure == "predispatch" else "UNKNOWN")
    )
    assert state.geometry_status == expected and len(calls) == 1, state.geometry_message
    assert bool(report.get("export")) == (expected == "OUTDATED")
    assert ("written:" in state.geometry_message) == (expected == "OUTDATED")
    assert destination.read_text() == "existing destination sentinel"


def test_legacy_snapshot_capture_returns_only_detached_canonical_data(owners, monkeypatch):
    root = ROOT / "tests/fixtures/result_v3/legacy_30383a1"
    operation = json.loads((root / "snapshot_viewport_rectangle.request.txt").read_text())
    inner = json.loads((root / "snapshot_viewport_rectangle.stdout.txt").read_text())
    ctx = context(owners, operation["document"])
    calls = []

    def execute(prepared, selected, *, owner_token, current_selection):
        calls.append(prepared)
        assert prepared.action == "canonical_snapshot"
        assert "result_version" not in prepared.operation_request()
        return owners.guarded_evidence.accept_response(
            prepared, synthetic_outer(prepared, inner, selected), selected, owner_token=owner_token
        )

    monkeypatch.setattr(owners.guarded_transport, "execute", execute)
    before = copy.deepcopy(vars(ctx.scene.mechanical_cad_assembly))
    captured = owners.assembly_operator_helpers.canonical_working_part(ctx)
    assert captured == inner["result"]["canonical_document"] and type(captured) is dict
    assert not hasattr(captured, "publication") and len(calls) == 1
    assert vars(ctx.scene.mechanical_cad_assembly) == before


def test_eligible_sector_geometry_poll_and_export_selector_are_available(owners, monkeypatch):
    ctx = context(owners, source3())
    before = copy.deepcopy(vars(ctx.scene.mechanical_cad))
    assert owners.geometry_operations.MCAD_OT_check_geometry.poll(ctx)
    invoked = []
    monkeypatch.setattr(
        owners.geometry_operations.ExportHelper,
        "invoke",
        lambda op, context, event: invoked.append(op.filepath) or {"RUNNING_MODAL"},
        raising=False,
    )
    for cls in (
        owners.geometry_operations.MCAD_OT_export_step,
        owners.geometry_operations.MCAD_OT_export_stl,
    ):
        assert cls.poll(ctx)
        operator = cls()
        operator.filepath = "/explicit/sector" + cls.filename_ext
        assert operator.invoke(ctx, None) == {"RUNNING_MODAL"}
        assert "UNDO" not in cls.bl_options
    assert len(invoked) == 2 and vars(ctx.scene.mechanical_cad) == before


def test_supported_sector_capture_and_mixed_assembly_keep_guarded_authority(
    owners,
    monkeypatch,
    make_assembly3,  # noqa: F811
):
    from mechanical_cad.sidecar import process_request

    request, assembly_inner, _ = make_assembly3()
    owner = object()
    launches = []

    def execute(prepared, selection, *, owner_token, current_selection):
        operation = prepared.operation_request()
        launches.append(operation)
        inner = (
            process_request(operation)
            if operation["action"] == "canonical_snapshot"
            else assembly_inner
        )
        raw = synthetic_outer(prepared, inner, selection)
        return owners.guarded_evidence.accept_response(
            prepared, raw, selection, owner_token=owner_token
        )

    monkeypatch.setattr(owners.guarded_transport, "execute", execute)
    source = request["assembly"]["part_sources"][1]["document"]
    snapshot = owners.guarded_operations.canonical_snapshot_guarded(
        source,
        selection=owners.selected,
        owner_token=owner,
        current_selection=lambda: owners.selected,
    )
    assert "result_version" not in launches[-1]
    snapshot.publication.consume(
        owners.selected,
        owner_token=owner,
        expected_action="canonical_snapshot",
        expected_result_version=None,
        require_success=True,
    )
    with pytest.raises(ValueError, match="no longer available"):
        snapshot.publication.consume(
            owners.selected, owner_token=owner, expected_result_version=None
        )
    assembly_evidence = owners.guarded_operations.assembly_action_guarded(
        request["assembly"],
        selection=owners.selected,
        owner_token=owner,
        current_selection=lambda: owners.selected,
    )
    assert launches[-1]["result_version"] == 3
    assert (
        assembly_evidence.revalidate(
            owners.selected,
            owner_token=owner,
            expected_action="assembly_replay",
            expected_result_version=3,
            require_success=True,
        )
        == assembly_inner
    )
    before = len(launches)
    with pytest.raises(owners.bridge.BridgeError, match="selected from every source"):
        owners.guarded_operations.assembly_action_guarded(
            request["assembly"],
            selection=owners.selected,
            owner_token=owner,
            current_selection=lambda: owners.selected,
            result_version=3,
        )
    assert len(launches) == before
