"""Atomic assembly publication and explicitly scoped verification evidence.

Part and assembly canonical JSON have separate owners. Only a fresh sidecar
response may publish an assembly. Persisted response bytes cannot restore trust:
load/history/rebind require fresh display replay and a separate explicit check.
"""

from __future__ import annotations

import copy
import json
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import bpy

from . import (
    assembly_bridge,
    assembly_display,
    backend_contracts,
    backend_runtime,
    bridge,
    execution_lease,
    guarded_evidence,
    guarded_transport,
    operation_contracts,
    part_snapshot_bridge,
    workspace,
)
from .assembly_coordinates import authored_coordinates

_STATE_FIELDS = (
    "owner_id",
    "document_json",
    "document_path",
    "document_name",
    "status",
    "error",
    "last_action_error",
    "display_status",
    "verification_status",
    "verification_message",
    "report_json",
    "report_document_json",
    "report_request_json",
    "report_working_part_json",
    "report_preset_id",
    "selected_part_id",
    "selected_instance_id",
    "selected_joint_id",
)
_RUNTIME = {}
_RUNTIME_EPOCH = uuid.uuid4().hex
_EPOCHS = {}
_BUSY = set()
_STATE_LOCK = 0
_INTERACTION_REVISION = 0


def interaction_revision():
    """Admission clock for transient automatic display restoration, not model Undo."""
    return _INTERACTION_REVISION


def begin_interaction():
    global _INTERACTION_REVISION
    _INTERACTION_REVISION += 1


def _key(scene):
    return scene.as_pointer()


def _state(context):
    scene = getattr(context, "scene", None)
    if scene is None or not hasattr(scene, "mechanical_cad_assembly"):
        raise bridge.BridgeError("Assembly scene storage is not registered.")
    return scene.mechanical_cad_assembly


def _json(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _working_part(scene):
    return getattr(getattr(scene, "mechanical_cad", None), "document_json", "")


def read_assembly(state):
    """Read detached JSON only; the sidecar remains the complete schema authority."""
    content = state.document_json
    if not content:
        raise bridge.BridgeError(
            "Create an assembly from a current Part or load an assembly first."
        )
    if len(content.encode("utf-8")) > bridge.MAX_DOCUMENT_BYTES:
        raise bridge.BridgeError("Assembly document exceeds the 2 MiB input limit.")
    result = bridge.parse_document_json(content)
    if result.get("kind") != "assembly":
        raise bridge.BridgeError("The saved document is not an assembly envelope.")
    return result


def _preflight_assembly(assembly, action="assembly_replay"):
    """Reject every unsupported source before leases, display changes or recovery."""
    try:
        return operation_contracts.result_version_for_assembly(assembly, action=action)
    except ValueError as exc:
        raise bridge.BridgeError(str(exc)) from exc


def _require_no_draft(context):
    # A modal session may belong to another window. Suspended drafts retain their
    # own canonical bindings; none may be silently stranded by assembly editing.
    if workspace.active_draft() or workspace.has_draft(context):
        raise bridge.BridgeError(
            "Finish, cancel, or discard the sketch draft before editing an assembly."
        )
    if any(
        getattr(getattr(scene, "mechanical_cad", None), "sketch_draft_json", "")
        for scene in bpy.data.scenes
    ):
        raise bridge.BridgeError(
            "Resume and finish, or discard the saved sketch draft before editing an assembly."
        )


def _backend_context(context=None):
    """Scene-only handlers still compare actual configured Blender preferences."""
    if context is not None and getattr(context, "preferences", None) is not None:
        return context
    return SimpleNamespace(preferences=bpy.context.preferences)


def _configuration(context):
    return backend_runtime.configuration(_backend_context(context))


def _current_selection(context, snapshot):
    return backend_runtime.assert_current(snapshot["selection"], _backend_context(context))


def _projection(context, snapshot, evidence, *, actions, success=False, consume=False):
    if type(evidence) is not guarded_evidence.GuardedEvidence:
        raise bridge.BridgeError("Assembly publication requires guarded backend evidence.")
    validate = evidence.publication.consume if consume else evidence.revalidate
    try:
        prepared = snapshot.get("prepared")
        if type(prepared) is not backend_contracts.PreparedRequest or assembly_bridge.fingerprint(
            evidence.guarded_request()
        ) != assembly_bridge.fingerprint(prepared.guarded_request()):
            raise bridge.BridgeError("Assembly evidence differs from the exact captured request.")
        operation = prepared.operation_request()
        result_version = _preflight_assembly(operation.get("assembly"), operation.get("action"))
        return validate(
            _current_selection(context, snapshot),
            owner_token=snapshot["owner_token"],
            expected_action=actions,
            expected_result_version=result_version,
            require_success=success,
        )
    except ValueError as exc:
        raise bridge.BridgeError(str(exc)) from exc


def _prepare_operation(snapshot, assembly, action="assembly_replay", **arguments):
    """Bind the exact G/O operation before the replaceable transport boundary."""
    result_version = _preflight_assembly(assembly, action)
    if "prepared" in snapshot:
        raise bridge.BridgeError("An assembly transaction already owns a captured operation.")
    # A configured preset owns its numerical policy. Unconfigured replay uses
    # the tessellation preference captured alongside this operation's selection.
    if action == "assembly_replay" and "policy" not in arguments:
        arguments["policy"] = {
            **assembly_bridge.DEFAULT_POLICY,
            "linear_tolerance_mm": assembly.get("replay_tolerance_mm", 1e-6),
            "linear_deflection_mm": snapshot["deflection"],
        }
    request = assembly_bridge.build_request(
        assembly, action, result_version=result_version, **arguments
    )
    prepared = backend_contracts.prepare_request(request)
    snapshot["prepared"] = prepared
    return prepared


def _run_sidecar(context, *, snapshot):
    operation = snapshot["prepared"].operation_request()
    _preflight_assembly(operation.get("assembly"), operation.get("action"))
    token = execution_lease.try_acquire()
    if token is None:
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    try:
        with execution_lease.synchronous(token):
            return guarded_transport.execute(
                snapshot["prepared"],
                snapshot["selection"],
                owner_token=snapshot["owner_token"],
                current_selection=lambda: _current_selection(context, snapshot),
            )
    finally:
        execution_lease.release(token)


@contextmanager
def _locked():
    global _STATE_LOCK
    _STATE_LOCK += 1
    try:
        yield
    finally:
        _STATE_LOCK -= 1


def _write_fields(state, values):
    """Single fault-injection boundary; restoration deliberately does not use it."""
    with _locked():
        for name, value in values.items():
            setattr(state, name, value)


def _restore_fields(state, snapshot):
    with _locked():
        for name, value in snapshot.items():
            setattr(state, name, value)


def _window_key(context):
    window = getattr(context, "window", None)
    return window.as_pointer() if window is not None else None


def _capture(context, scene):
    if context.scene != scene:
        raise bridge.BridgeError("The active scene changed before the assembly request started.")
    selection, deflection = _configuration(context)
    state = scene.mechanical_cad_assembly
    return {
        "scene_key": _key(scene),
        "window_key": _window_key(context),
        "fields": {name: getattr(state, name) for name in _STATE_FIELDS},
        "working_part": _working_part(scene),
        "epoch": _EPOCHS.get(_key(scene), 0),
        "runtime_epoch": _RUNTIME_EPOCH,
        "scale": float(scene.unit_settings.scale_length),
        "runtime": copy.copy(_RUNTIME.get(_key(scene))),
        "selection": selection,
        "deflection": deflection,
        "owner_token": object(),
    }


def _assert_current(context, snapshot, *, drafts=False, published=None):
    _current_selection(context, snapshot)
    scene = getattr(context, "scene", None)
    if scene is None or _key(scene) != snapshot["scene_key"]:
        raise bridge.BridgeError(
            "The active scene changed while the assembly request ran. "
            "The late result was rejected; retry in the intended scene."
        )
    if snapshot["window_key"] is not None and _window_key(context) != snapshot["window_key"]:
        raise bridge.BridgeError(
            "The active window changed while the assembly request ran. "
            "The late result was rejected; retry in the intended window."
        )
    state = _state(context)
    expected_document, expected_owner = published or (
        snapshot["fields"]["document_json"],
        snapshot["fields"]["owner_id"],
    )
    if (
        state.document_json != expected_document
        or state.owner_id != expected_owner
        or _working_part(scene) != snapshot["working_part"]
        or _EPOCHS.get(_key(scene), 0) != snapshot["epoch"]
        or _RUNTIME_EPOCH != snapshot["runtime_epoch"]
        or float(scene.unit_settings.scale_length) != snapshot["scale"]
    ):
        raise bridge.BridgeError(
            "Assembly, working Part, scene units, or history changed while the request ran. "
            "The late result was rejected; retry against the current revision."
        )
    if drafts:
        _require_no_draft(context)


def _failure(state, exc):
    state.status = "ERROR"
    state.last_action_error = str(exc)
    state.error = "Last attempt failed. The previously accepted assembly is retained. " + str(exc)


def _recover_failure(
    scene,
    state,
    snapshot,
    transaction,
    wrote_state,
    primary,
    *,
    written_fields=None,
    preserve_newer=False,
):
    """Recover independent resources even when another recovery step itself fails.

    In particular, orphan cleanup must never skip canonical restoration. Any
    incomplete recovery drops runtime trust, even if the visible old objects were
    successfully relinked before cleanup raised.
    """
    key = _key(scene)
    failures = []
    foreign_authority = False
    try:
        if transaction is not None:
            transaction.discard()
    except Exception as exc:
        failures.append("Display rollback/cleanup failed: " + str(exc))
    finally:
        try:
            if wrote_state:
                fields = snapshot["fields"]
                if preserve_newer and written_fields is not None:
                    actual, original = _RUNTIME.get(key), snapshot["runtime"]
                    changed_runtime = actual is not None and (
                        original is None
                        or any(
                            actual.get(name) is not original.get(name)
                            for name in ("display_evidence", "display_owner_token")
                        )
                    )
                    foreign_authority = changed_runtime or any(
                        getattr(state, name) not in (fields[name], written_fields[name])
                        for name in ("document_json", "owner_id")
                    )
                if foreign_authority:
                    # A newer canonical/runtime owner owns its complete bundle,
                    # even fields whose values happen to equal this candidate's.
                    fields = {}
                elif written_fields is not None:
                    # A late external edit is never rewound by candidate rollback.
                    fields = {
                        name: fields[name]
                        for name, value in written_fields.items()
                        if getattr(state, name) == value
                    }
                _restore_fields(state, fields)
        except Exception as exc:
            failures.append("Canonical state restoration failed: " + str(exc))
        finally:
            # Restoring or revoking runtime capability does not depend on a
            # successful Blender datablock/RNA cleanup path.
            current = bool(
                snapshot is not None
                and _EPOCHS.get(key, 0) == snapshot["epoch"]
                and _RUNTIME_EPOCH == snapshot["runtime_epoch"]
                and backend_runtime.is_current(snapshot["selection"], _backend_context())
            )
            if preserve_newer and snapshot is not None:
                original, actual = snapshot["runtime"], _RUNTIME.get(key)
                owns_runtime = actual is None or (
                    original is not None
                    and all(
                        actual.get(name) is original.get(name)
                        for name in (
                            "display_evidence",
                            "display_owner_token",
                        )
                    )
                )
                # This sink assigns runtime only after all guards succeed. Never
                # overwrite a newer runtime installed by another owner on failure.
                if owns_runtime and (
                    failures
                    or not current
                    or state.document_json != snapshot["fields"]["document_json"]
                    or state.owner_id != snapshot["fields"]["owner_id"]
                ):
                    _RUNTIME.pop(key, None)
                    _EPOCHS[key] = _EPOCHS.get(key, 0) + 1
            else:
                if wrote_state and current:
                    if snapshot["runtime"] is None:
                        _RUNTIME.pop(key, None)
                    else:
                        _RUNTIME[key] = snapshot["runtime"]
                if failures or snapshot is not None and not current:
                    _RUNTIME.pop(key, None)
                    _EPOCHS[key] = _EPOCHS.get(key, 0) + 1
    if (
        preserve_newer
        and snapshot is not None
        and (
            foreign_authority
            or not owns_runtime
            or any(
                getattr(state, name) != snapshot["fields"][name]
                for name in (
                    "document_json",
                    "owner_id",
                    "report_json",
                    "report_document_json",
                    "report_request_json",
                    "report_working_part_json",
                    "report_preset_id",
                )
            )
            or _working_part(scene) != snapshot["working_part"]
        )
    ):
        # Display cleanup is ours; newer canonical/report/runtime diagnostics are
        # not. Report a rollback problem to the caller without annotating them.
        return (
            bridge.BridgeError(str(primary) + " Recovery is incomplete. " + " ".join(failures))
            if failures
            else None
        )
    if failures:
        message = str(primary) + " Recovery is incomplete. " + " ".join(failures)
        state.status = "FAILED"
        state.last_action_error = message
        state.error = message
        state.display_status = "STALE" if state.document_json else "EMPTY"
        state.verification_status = "STALE" if state.report_json else "UNCHECKED"
        state.verification_message = (
            "Rollback could not be completed. Display and evidence are untrusted; "
            "inspect the recovery diagnostics, then replay the accepted snapshot."
        )
        return bridge.BridgeError(message)
    _failure(state, primary)
    if snapshot is not None and not current:
        state.display_status = "STALE" if state.document_json else "EMPTY"
        state.verification_status = "STALE" if state.report_json else "UNCHECKED"
        state.verification_message = "Backend or history changed; retained evidence is historical."
    return None


def _error(response):
    error = response.get("error") or {}
    report = response.get("report", {})
    diagnostics = list(report.get("diagnostics", []))
    if not diagnostics:
        diagnostics = [d for pose in report.get("poses", []) for d in pose.get("diagnostics", [])]
    # Preserve the exact admission reason instead of hiding pose failures behind
    # a generic replay error. Bound repeated instance messages in the operator UI.
    messages = list(dict.fromkeys(d.get("message", "") for d in diagnostics))[:3]
    return (
        error.get("message")
        or "; ".join(messages)
        or ("The assembly could not be freshly replayed completely.")
    )


def _evidence_fields(response, document_json, working_part):
    basis = response["report"].get("verification_basis") or {}
    return {
        "report_json": _json(dict(response)),
        "report_document_json": document_json,
        "report_request_json": _json(response.request_snapshot()),
        "report_working_part_json": working_part,
        "report_preset_id": basis.get("preset_id") or "",
    }


def commit_candidate(
    context, candidate, expected_json=None, *, expected_preview=None, expected_source_preview=None
):
    """Freshly replay then atomically publish, retaining synchronous edit semantics."""
    if expected_source_preview is not None:
        from .assembly_source_preview_contract import validate_source_preview_digest

        validate_source_preview_digest(expected_source_preview)
    begin_interaction()
    candidate = (
        bridge.parse_document_json(candidate)
        if isinstance(candidate, str)
        else copy.deepcopy(candidate)
    )
    _preflight_assembly(candidate)
    state, scene = _state(context), context.scene
    key = _key(scene)
    if key in _BUSY:
        raise bridge.BridgeError("An assembly transaction is already running in this scene.")
    snapshot = None
    _BUSY.add(key)
    try:
        try:
            _require_no_draft(context)
            if expected_json is not None and state.document_json != expected_json:
                raise bridge.BridgeError(
                    "The accepted assembly changed since this edit opened. Reopen the edit."
                )
            snapshot = _capture(context, scene)
            _prepare_operation(snapshot, candidate)
            evidence = _run_sidecar(context, snapshot=snapshot)
        except Exception as exc:
            recovery_error = _recover_failure(scene, state, snapshot, None, False, exc)
            if recovery_error is not None:
                raise recovery_error from exc
            raise
        return _commit_candidate_evidence(
            context, snapshot, evidence, scene=scene, expected_preview=expected_preview,
            expected_source_preview=expected_source_preview,
        )
    finally:
        _BUSY.discard(key)


def _commit_candidate_evidence(
    context,
    snapshot,
    evidence,
    *,
    scene,
    expected_preview=None,
    expected_source_preview=None,
    publication_guard=None,
    clear_path=False,
):
    """Shared guarded commit sink, called only while the transaction owns _BUSY.

    The prepared request is independently captured before native work. Saved
    response JSON and transient preview projections cannot enter this sink.
    An async candidate supplies stricter admission guards through the final write.
    """
    state = scene.mechanical_cad_assembly
    key = _key(scene)
    if key not in _BUSY:
        raise bridge.BridgeError("Assembly candidate publication requires its transaction owner.")
    transaction, wrote_state, values = None, False, None

    def validate(published=None):
        _assert_current(
            context,
            snapshot,
            drafts=True,
            published=(published["document_json"], published["owner_id"]) if published else None,
        )
        if publication_guard is not None:
            publication_guard(published)

    try:
        validate()
        response = _projection(context, snapshot, evidence, actions="assembly_replay")
        if not response["ok"]:
            raise bridge.BridgeError(_error(response))
        if expected_preview is not None and response["report"]["base_pose"] != expected_preview:
            raise bridge.BridgeError(
                "The exact replay differs from the displayed motion preview. Preview again before Apply."
            )
        if expected_source_preview is not None:
            from .assembly_source_preview_contract import require_source_preview

            require_source_preview(response, expected_source_preview)
        canonical_json = _json(response["result"]["canonical_assembly"])
        owner_id = state.owner_id or uuid.uuid4().hex
        transaction = assembly_display.stage(
            scene,
            owner_id,
            evidence,
            owner_token=snapshot["owner_token"],
            current_selection=lambda: _current_selection(context, snapshot),
        )
        validate()
        transaction.publish()
        validate()
        values = {
            "owner_id": owner_id,
            "document_json": canonical_json,
            "document_name": response["result"]["canonical_assembly"]["name"],
            "status": "READY",
            "error": "",
            "last_action_error": "",
            "display_status": "CURRENT",
            "verification_status": "UNCHECKED",
            "verification_message": "Geometry replayed. Run an explicit check; replay is not verification.",
            **_evidence_fields(response, canonical_json, snapshot["working_part"]),
        }
        if clear_path:
            values["document_path"] = ""
        wrote_state = True
        _write_fields(state, values)
        validate(values)
        _projection(context, snapshot, evidence, actions="assembly_replay", success=True)
        validate(values)
        _RUNTIME[key] = {
            "owner_id": owner_id,
            "display_document_json": canonical_json,
            "display_response": response,
            "display_evidence": evidence,
            "display_owner_token": snapshot["owner_token"],
            "report_binding": None,
        }
    except Exception as exc:
        recovery_error = _recover_failure(
            scene,
            state,
            snapshot,
            transaction,
            wrote_state,
            exc,
            written_fields=values if publication_guard is not None else None,
            preserve_newer=publication_guard is not None,
        )
        if recovery_error is not None:
            raise recovery_error from exc
        raise
    # Canonical/display publication is complete. Old orphan cleanup cannot undo
    # that acceptance; retain any cleanup diagnostic rather than misreport failure.
    try:
        transaction.finalize()
        if transaction.cleanup_warnings:
            state.last_action_error = "Assembly accepted; " + "; ".join(
                transaction.cleanup_warnings
            )
    except Exception as exc:
        state.last_action_error = "Assembly accepted; old display cleanup needs attention: " + str(
            exc
        )
    return response


def publish_restored_display(context, snapshot, evidence, *, validate_publication):
    """Replace only an accepted Assembly's disposable cache after file Open.

    This is not commit_candidate or report publication: exact saved canonical,
    embedded source and report text remains untouched. The saved report has no
    live binding. Reuse the same reversible display transaction and receipt.
    """
    state, scene = _state(context), context.scene
    key = _key(scene)
    if key in _BUSY:
        raise bridge.BridgeError("An assembly transaction is already running in this scene.")
    transaction = None
    runtime = _RUNTIME.get(key)
    written = {}
    before = {
        name: getattr(state, name)
        for name in (
            "status",
            "error",
            "display_status",
            "verification_status",
            "verification_message",
        )
    }
    _BUSY.add(key)
    try:
        validate_publication()
        _assert_current(context, snapshot)
        if snapshot["prepared"].operation_request()["assembly"] != read_assembly(state):
            raise bridge.BridgeError("Display restoration cannot accept a proposed Assembly edit.")
        response = _projection(context, snapshot, evidence, actions="assembly_replay", success=True)
        transaction = assembly_display.stage(
            scene,
            snapshot["fields"]["owner_id"],
            evidence,
            owner_token=snapshot["owner_token"],
            current_selection=lambda: _current_selection(context, snapshot),
        )
        validate_publication()
        transaction.publish()
        validate_publication()
        written = {
            "status": "READY",
            "error": "",
            "display_status": "CURRENT",
            "verification_status": "STALE" if state.report_json else "UNCHECKED",
            "verification_message": (
                "Accepted assembly display rebuilt. Saved checks remain historical; run Check explicitly."
                if state.report_json
                else "Accepted assembly display rebuilt. Run Check explicitly."
            ),
        }
        _write_fields(state, written)
        validate_publication()
        _RUNTIME[key] = {
            "owner_id": state.owner_id,
            "display_document_json": state.document_json,
            "display_response": response,
            "display_evidence": evidence,
            "display_owner_token": snapshot["owner_token"],
            "report_binding": None,
        }
    except Exception:
        try:
            if transaction is not None:
                transaction.discard()
        finally:
            # Never restore canonical/report fields: this sink never wrote them.
            # Do not overwrite a newer operation's diagnostics or runtime owner.
            for name, value in written.items():
                if getattr(state, name) == value:
                    setattr(state, name, before[name])
            if _RUNTIME.get(key) is runtime:
                _RUNTIME.pop(key, None)
        raise
    finally:
        _BUSY.discard(key)
    try:
        transaction.finalize()
        if transaction.cleanup_warnings:
            state.last_action_error = "Assembly display rebuilt; " + "; ".join(
                transaction.cleanup_warnings
            )
    except Exception as exc:
        state.last_action_error = (
            "Assembly display rebuilt; old cache cleanup needs attention: " + str(exc)
        )
    return response


def require_idle(context, *, admit=True):
    """Preflight live input, or inspect availability without admitting an edit."""
    if admit:
        begin_interaction()
    _state(context)
    if _key(context.scene) in _BUSY:
        raise bridge.BridgeError("An assembly transaction is already running in this scene.")
    _require_no_draft(context)


def validate_snapshot(context):
    """Freshly validate accepted JSON for explicit save, without publishing it.

    The result is a detached validation outcome, not renewed display/report trust.
    A caller must keep the remaining file publication synchronous.
    """
    require_idle(context)
    state, scene = _state(context), context.scene
    assembly = read_assembly(state)
    _preflight_assembly(assembly)
    key = _key(scene)
    snapshot = _capture(context, scene)
    _BUSY.add(key)
    try:
        _prepare_operation(snapshot, assembly)
        evidence = _run_sidecar(context, snapshot=snapshot)
        _assert_current(context, snapshot, drafts=True)
        response = _projection(context, snapshot, evidence, actions="assembly_replay")
        if not response["ok"]:
            raise bridge.BridgeError(_error(response))
        _projection(
            context, snapshot, evidence, actions="assembly_replay", success=True, consume=True
        )
        _assert_current(context, snapshot, drafts=True)
        return response
    except Exception as exc:
        _failure(state, exc)
        raise
    finally:
        _BUSY.discard(key)


def replay(context):
    """Rebuild from accepted canonical JSON, invalidating any earlier check."""
    state = _state(context)
    return commit_candidate(context, read_assembly(state), expected_json=state.document_json)


def invalidate(scene, reason):
    """Invalidate report trust without destroying accepted canonical/display data."""
    if not hasattr(scene, "mechanical_cad_assembly"):
        return
    state = scene.mechanical_cad_assembly
    _EPOCHS[_key(scene)] = _EPOCHS.get(_key(scene), 0) + 1
    runtime = _RUNTIME.get(_key(scene))
    if runtime:
        runtime["report_binding"] = None
    state.verification_status = "STALE" if state.report_json else "UNCHECKED"
    state.verification_message = str(reason)


def document_changed(state, context):
    """Direct RNA changes can invalidate trust, never import mesh edits as CAD."""
    if _STATE_LOCK:
        return
    scene = state.id_data
    invalidate(scene, "Assembly snapshot changed. Replay and check the current revision.")
    state.display_status = "STALE" if state.document_json else "EMPTY"
    state.status = "DIRTY" if state.document_json else "EMPTY"
    state.error = "Replay the changed assembly to rebuild its display."


def display_is_current(context, *, update=False):
    """Read-only cache query by default; update=True visibly revokes stale trust."""
    state, scene = _state(context), context.scene
    runtime = _RUNTIME.get(_key(scene))
    valid = bool(
        runtime
        and runtime["owner_id"] == state.owner_id
        and runtime["display_document_json"] == state.document_json
        and assembly_display.trusted_display(
            scene,
            state.owner_id,
            runtime.get("display_evidence"),
            owner_token=runtime.get("display_owner_token"),
            current_selection=lambda: backend_runtime.capture(_backend_context(context)),
        )
    )
    if not valid and state.document_json and update:
        if (
            state.display_status != "STALE"
            or state.verification_status == "CURRENT"
            or runtime
            and runtime.get("report_binding")
        ):
            state.display_status = "STALE"
            invalidate(
                scene, "Assembly display is untrusted or changed. Replay it before checking."
            )
    elif valid and update and state.display_status != "CURRENT":
        state.display_status = "CURRENT"
    return valid


def current_display_response(context):
    """Return live display evidence for a detached, nonauthoritative UI preview.

    Saved report JSON and Blender object transforms are not a pose source. The
    caller may retain this detached projection of immutable evidence for drawing, but an edit still
    needs its opening-context checks and a fresh commit_candidate operation.
    """
    if not display_is_current(context):
        raise bridge.BridgeError("Replay the Assembly before placing a visual joint.")
    state = _state(context)
    key = _key(context.scene)
    runtime = _RUNTIME[key]
    owner, document = state.owner_id, state.document_json
    response = assembly_display._validated(
        runtime.get("display_evidence"),
        runtime.get("display_owner_token"),
        lambda: backend_runtime.capture(_backend_context(context)),
    )
    if (
        _RUNTIME.get(key) is not runtime
        or state.owner_id != owner
        or state.document_json != document
    ):
        raise bridge.BridgeError("Assembly display changed while opening the visual joint tool.")
    return response


def _binding(state):
    return tuple(
        getattr(state, name)
        for name in (
            "report_json",
            "report_document_json",
            "report_request_json",
            "report_working_part_json",
            "report_preset_id",
        )
    )


def report_is_current(context, *, update=False):
    """Current means this exact evidence belongs to this intact accepted snapshot.

    Read-only by default for Panel.draw; update=True revokes obsolete bindings.
    It does not mean passed, complete, continuous clearance, or physical safety.
    """
    state, scene = _state(context), context.scene
    if not display_is_current(context, update=update):
        return False
    runtime = _RUNTIME.get(_key(scene))
    valid = bool(
        runtime
        and runtime.get("report_binding")
        and runtime["report_binding"] == _binding(state)
        and state.report_document_json == state.document_json
        and state.report_working_part_json == _working_part(scene)
    )
    if valid:
        try:
            evidence = runtime.get("report_evidence")
            if type(evidence) is not guarded_evidence.GuardedEvidence:
                raise bridge.BridgeError("Saved assembly reports are historical.")
            result_version = _preflight_assembly(
                read_assembly(state), evidence.operation_request().get("action")
            )
            evidence.revalidate(
                backend_runtime.capture(_backend_context(context)),
                owner_token=runtime.get("report_owner_token"),
                expected_action={"assembly_check", "assembly_sample"},
                expected_result_version=result_version,
            )
        except (ValueError, bridge.BridgeError):
            valid = False
    if not valid and state.verification_status == "CURRENT" and update:
        invalidate(
            scene, "Verification inputs or working Part changed. Check the current snapshot again."
        )
    return valid


def _verification_message(response):
    report = response["report"]
    basis = report.get("verification_basis") or {}
    messages = []
    if report.get("known_interference"):
        messages.append("Known interference found.")
    if report.get("known_clearance_violation"):
        messages.append("Known clearance violation found.")
    if not report.get("complete"):
        messages.append("Evidence is incomplete; unknown outcomes remain.")
    elif report.get("has_threshold_contacts"):
        messages.append("Threshold contact remains; no pass.")
    elif report.get("passed"):
        messages.append("The explicit verification preset passed at the checked poses.")
    if report.get("policy_accepted") is True:
        messages.append(
            "Explicit named-pair tolerance-band policy accepted; not a clearance pass or proof of zero penetration."
        )
    if not basis.get("configured"):
        messages.append(
            "Measurements only: select an explicit verification preset for a pass verdict."
        )
    if response["action"] == "assembly_sample":
        messages.append(
            "Only the listed discrete poses were checked; continuous motion is not verified."
        )
    messages.append("This is not physical-fit, load, or manufacturing certification.")
    return " ".join(messages)


def _prepare_report(context, action="assembly_check", *, transient=False):
    """Capture and lock the original target for either report transport.

    The returned transaction is private to a single main-thread operation. Keep
    its original scene/state references even when the active context changes.
    """
    begin_interaction()
    state, scene = _state(context), context.scene
    assembly = read_assembly(state)
    _preflight_assembly(assembly, action)
    key = _key(scene)
    if key in _BUSY:
        raise bridge.BridgeError("An assembly transaction is already running in this scene.")
    transaction = {
        "state": state,
        "scene": scene,
        "key": key,
        "snapshot": None,
        "wrote_state": False,
    }
    _BUSY.add(key)
    try:
        _require_no_draft(context)
        if not display_is_current(context, update=not transient):
            raise bridge.BridgeError("Replay the current assembly before checking its display.")
        transaction["snapshot"] = _capture(context, scene)
        transaction["assembly"] = assembly
        return transaction
    except Exception as exc:
        try:
            if not transient:
                _recover_report(transaction, exc)
        finally:
            _BUSY.discard(key)
        raise


def _assert_report_display(context, transaction, *, transient=False):
    """The exact replay owner captured for this report must survive publication."""
    runtime = _RUNTIME.get(transaction["key"])
    captured = transaction["snapshot"]["runtime"]
    if (
        runtime is None
        or captured is None
        or runtime.get("display_evidence") is not captured.get("display_evidence")
        or runtime.get("display_owner_token") is not captured.get("display_owner_token")
        or not display_is_current(context, update=not transient)
    ):
        raise bridge.BridgeError(
            "Assembly display changed during the check. Replay and check again."
        )


def _publish_report(context, transaction, evidence):
    """Shared final guards and reversible RNA writes; caller owns recovery/unlock."""
    state = transaction["state"]
    snapshot = transaction["snapshot"]
    _assert_current(context, snapshot, drafts=True)
    _assert_report_display(context, transaction)
    # A complete or partial exact report can be retained; no check publishes
    # its native mesh or changes canonical pose, including sample base poses.
    response = _projection(
        context, snapshot, evidence, actions={"assembly_check", "assembly_sample"}, consume=True
    )
    values = {
        **_evidence_fields(response, state.document_json, snapshot["working_part"]),
        "verification_status": "CURRENT",
        "verification_message": _verification_message(response),
        "status": "READY",
        "error": "",
        "last_action_error": "",
    }
    transaction["wrote_state"] = True
    _write_fields(state, values)
    _assert_current(context, snapshot, drafts=True)
    _projection(context, snapshot, evidence, actions={"assembly_check", "assembly_sample"})
    _assert_report_display(context, transaction)
    runtime = _RUNTIME[transaction["key"]]
    runtime["report_binding"] = _binding(state)
    runtime["report_evidence"] = evidence
    runtime["report_owner_token"] = snapshot["owner_token"]
    return response


def _recover_report(transaction, exc):
    recovery_error = _recover_failure(
        transaction["scene"],
        transaction["state"],
        transaction["snapshot"],
        None,
        transaction["wrote_state"],
        exc,
    )
    if recovery_error is not None:
        raise recovery_error from exc


def _sample_arguments(assembly, joint_id, values):
    """The complete authored base map is shared by synchronous and async sampling."""
    from .assembly_gears import controlling_joint

    driver = controlling_joint(assembly, joint_id)
    if driver != joint_id:
        raise bridge.BridgeError(
            "This angle is gear-controlled. Sample the independent driver: " + driver
        )
    return {
        "coordinates": authored_coordinates(assembly["joints"]),
        "samples": {"joint_id": joint_id, "values": list(values)},
    }


def _report_only(context, action, **arguments):
    transaction = _prepare_report(context, action)
    try:
        _prepare_operation(transaction["snapshot"], transaction["assembly"], action, **arguments)
        evidence = _run_sidecar(context, snapshot=transaction["snapshot"])
        return _publish_report(context, transaction, evidence)
    except Exception as exc:
        _recover_report(transaction, exc)
        raise
    finally:
        _BUSY.discard(transaction["key"])


def check(context, preset_id=None):
    """Check only an explicitly selected/active preset; absent intent cannot pass."""
    return _report_only(context, "assembly_check", preset_id=preset_id)


def sample(context, joint_id, values):
    """Sample exact listed values against the complete authored base coordinate map."""
    assembly = read_assembly(_state(context))
    _preflight_assembly(assembly, "assembly_sample")
    return _report_only(context, "assembly_sample", **_sample_arguments(assembly, joint_id, values))


def source_updates(context, *, update=False):
    """Read-only source notices; update=True also revokes superseded evidence."""
    state = _state(context)
    if not state.document_json or not _working_part(context.scene):
        return []
    assembly = read_assembly(state)
    part = bridge.parse_document_json(_working_part(context.scene))
    try:
        _preflight_assembly(assembly)
        operation_contracts.result_version_for(part, action="canonical_snapshot")
    except (ValueError, bridge.BridgeError):
        # Unsupported working sources are not update candidates and cannot revoke
        # the accepted Assembly or its report merely because UI queried this list.
        return []
    digest = assembly_bridge.canonical_digest(part)
    updates = []
    for source in assembly["part_sources"]:
        if source["source_document_id"] != part.get(
            "id"
        ) or part_snapshot_bridge.canonical_equivalent(part, source["document"]):
            continue
        parts = [p["id"] for p in assembly["parts"] if p["source_document_id"] == part["id"]]
        updates.append(
            {
                "source_document_id": part["id"],
                "accepted_digest": source["source_digest"],
                "working_digest": digest,
                "working_digest_scope": "raw_editor_draft",
                "part_ids": parts,
                "instance_ids": [i["id"] for i in assembly["instances"] if i["part_id"] in parts],
            }
        )
    if updates and state.verification_status == "CURRENT" and update:
        invalidate(
            context.scene,
            "Working Part has an update available. The assembly still uses its accepted source revision.",
        )
    return updates


def _scenes():
    return [s for s in bpy.data.scenes if hasattr(s, "mechanical_cad_assembly")]


def _reset_scene(scene, reason):
    _RUNTIME.pop(_key(scene), None)
    invalidate(scene, reason)
    state = scene.mechanical_cad_assembly
    if state.document_json:
        state.status = "DIRTY"
        state.display_status = "STALE"
        state.error = reason


def invalidate_backend(reason):
    """Shared lifetime hook; retain authored bytes, reports and display caches."""
    for scene in _scenes():
        _reset_scene(scene, str(reason))


def after_file_load(*_args):
    clear_runtime()
    for scene in _scenes():
        _reset_scene(scene, "Saved assembly loaded. Replay its display, then check again.")


def before_history_change(*_args):
    for scene in _scenes():
        _reset_scene(scene, "History is changing. Replay the resulting assembly before checking.")


def after_history_change(*_args):
    for scene in _scenes():
        _reset_scene(scene, "Assembly history changed. Replay its display, then check again.")


def rebind_existing():
    if not hasattr(bpy.data, "scenes") or not hasattr(bpy.types.Scene, "mechanical_cad_assembly"):
        return False
    for scene in _scenes():
        _reset_scene(scene, "Assembly storage rebound. Replay its display, then check again.")
    return True


def depsgraph_update(scene, *_args):
    """Registration may call this from depsgraph_update_post; no native work."""
    if _key(scene) in _BUSY or not hasattr(scene, "mechanical_cad_assembly"):
        return
    state = scene.mechanical_cad_assembly
    if not state.document_json:
        return

    # Avoid global context/window assumptions for multiple scenes.
    class SceneContext:
        pass

    context = SceneContext()
    context.scene = scene
    if display_is_current(context, update=True):
        report_is_current(context, update=True)


def before_file_save(*_args):
    for scene in _scenes():
        depsgraph_update(scene)


def clear_runtime():
    """Unregister/reload cleanup only; never delete canonical or cache data."""
    global _RUNTIME_EPOCH
    _RUNTIME_EPOCH = uuid.uuid4().hex
    _RUNTIME.clear()
    _EPOCHS.clear()
