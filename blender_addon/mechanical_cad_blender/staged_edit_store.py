"""Lower-level proposal ownership and intent checkpoints; no replay/publication.

Native evidence is validated by the caller. A captured binding-check capability
revokes stale storage without importing the canonical document coordinator.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, replace

import bpy

from . import backend_runtime, bridge, repair_intent

_PENDING = {}
_RESUME_OWNER = None  # Input reservation only, never a native publication claim.
_SAVE_PENDING = {}
_RESUME_OWNER = None  # Input reservation only, never a native publication claim.
_CHECKPOINTS = {}  # Exact raw bytes written by this live owner, never external slots.
_DORMANT_SAVES = {}  # Workspace recovery save notices; never live/native authority.
_INTERACTION_REVISION = 0


@dataclass(frozen=True)
class ProposedEdit:
    token: str
    candidate_json: str
    feature_id: str
    failed_json: str
    binding: dict
    base_hash: str
    assert_binding: object
    annotation_before: str | None = None
    annotation_after: str | None = None
    repairs: tuple = ()
    accepted_annotations: str | None = None  # Runtime-only recovery compatibility snapshot.

    @property
    def document(self):
        return json.loads(self.candidate_json)

    @property
    def failures(self):
        return json.loads(self.failed_json)

    @property
    def base_json(self):
        return self.binding["document_json"]


def _key(context):
    return context.scene.as_pointer()


def _notify_changed():
    """Refresh Python-only proposal presentation, without changing model/context.

    An operator returning CANCELLED need not emit an RNA update or redraw the
    sidebar. Tag every open 3D view (including its UI region), also on retirement
    so old banners and disabled parameter controls cannot linger. Cleanup can
    run while windows are closing; redraw failure must never affect ownership.
    """
    try:
        windows = tuple(bpy.context.window_manager.windows)
    except (AttributeError, ReferenceError, RuntimeError):
        return
    for window in windows:
        try:
            areas = tuple(window.screen.areas)
        except (AttributeError, ReferenceError, RuntimeError):
            continue
        for area in areas:
            try:
                if area.type != "VIEW_3D":
                    continue
                area.tag_redraw()
                regions = tuple(area.regions)
            except (AttributeError, ReferenceError, RuntimeError):
                continue
            for region in regions:
                try:
                    region.tag_redraw()
                except (AttributeError, ReferenceError, RuntimeError):
                    continue


def _workspace_intent(context, key, proposal):
    """Checkpoint intent only when workspace is the sole binding change.

    The comparison copy is never installed or used for replay/publication. The
    original binding and token stay invalid. Codec/slot failure is disclosed;
    it cannot overwrite another checkpoint or preserve a stale capability.
    """
    binding = proposal.binding
    workspace = getattr(context, "workspace", None)
    if (
        _PENDING.get(key) is not proposal
        or "workspace" not in binding
        or workspace == binding["workspace"]
        or workspace is None
        or "view_layer" not in binding
        or context.scene != binding["scene"]
        or getattr(context, "window", None) != binding["window"]
        or context.view_layer != binding["view_layer"]
        or proposal.accepted_annotations is None
    ):
        return None
    try:
        window = binding["window"]
        if window not in context.window_manager.windows[:] or window.scene != binding["scene"]:
            return None
        comparison = dict(binding, workspace=workspace)
        proposal.assert_binding(context, comparison)
        if backend_runtime.configuration(context)[1] != binding["deflection"]:
            return None
        if hashlib.sha256(proposal.base_json.encode()).hexdigest() != proposal.base_hash:
            return None
        state = binding["scene"].mechanical_cad
        if (
            getattr(state, "sketch_annotation_json", "") != proposal.accepted_annotations
            or proposal.annotation_after is not None
            and state.sketch_annotation_json != proposal.annotation_before
            or _PENDING.get(key) is not proposal
        ):
            return None
    except Exception:
        return None
    try:
        old = state.repair_intent_json
        if old != _CHECKPOINTS.get(key, ""):
            raise ValueError(
                "The saved repair slot changed; its original text was not overwritten."
            )
        raw = repair_intent.encode(proposal)
        # Backend validation may synchronously revoke owners. Serialization is
        # not permission to write for an owner that no longer exists.
        if _PENDING.get(key) is not proposal:
            return None
        if state.repair_intent_json != old:
            raise ValueError("The saved repair slot changed during checkpoint validation.")
        state.repair_intent_json = raw
    except Exception as exc:
        return "", (
            "Workspace change expired the live edit; its new proposal was NOT saved: "
            + str(exc)
            + " Existing saved intent and accepted model were left unchanged."
        )
    return raw, (
        "Workspace changed; unapplied repair intent preserved in memory. "
        "Resume Repair revalidates it; save the Blender file to keep it on disk."
    )


def _retire_stale(key, proposal, notice, recovery=None):
    if _PENDING.get(key) is not proposal:
        return
    _PENDING.pop(key)
    _CHECKPOINTS.pop(key, None)
    _SAVE_PENDING.pop(key, None)
    _DORMANT_SAVES.pop(key, None)
    state = proposal.binding["scene"].mechanical_cad
    if recovery is not None:
        raw, notice = recovery
        if raw:
            _DORMANT_SAVES[key] = (state, raw, notice)
    state.last_action_error = notice


def _supervise():
    changed = False
    for key, proposal in tuple(_PENDING.items()):
        binding = proposal.binding
        try:
            window = binding["window"]
            if (
                window not in bpy.context.window_manager.windows[:]
                or window.scene != binding["scene"]
            ):
                raise ValueError("Proposal window changed")
            with bpy.context.temp_override(window=window):
                proposal.assert_binding(bpy.context, binding)
                if backend_runtime.configuration(bpy.context)[1] != binding["deflection"]:
                    raise ValueError("Proposal tessellation settings changed")
        except Exception:
            changed = True
            try:
                with bpy.context.temp_override(window=binding["window"]):
                    recovery = _workspace_intent(bpy.context, key, proposal)
            except Exception:
                recovery = None
            try:
                _retire_stale(
                    key,
                    proposal,
                    "Unapplied edit discarded because its context changed; accepted model unchanged.",
                    recovery,
                )
            except (ReferenceError, AttributeError):
                _PENDING.pop(key, None)
    if changed:
        _notify_changed()
    return 0.2 if _PENDING else None


def cancel_all(reason=""):
    changed = bool(_PENDING)
    for proposal in tuple(_PENDING.values()):
        if reason:
            try:
                proposal.binding["scene"].mechanical_cad.last_action_error = reason
            except (ReferenceError, AttributeError):
                pass
    _PENDING.clear()
    _SAVE_PENDING.clear()
    _CHECKPOINTS.clear()
    _DORMANT_SAVES.clear()
    if bpy.app.timers.is_registered(_supervise):
        bpy.app.timers.unregister(_supervise)
    if changed:
        _notify_changed()


def current(context):
    """Observe retained work, not current authority; safe in panel draw/poll.

    Even binding checks can notify backend revocation and write Blender ID data.
    Only explicit actions/admission and the lifecycle timer may validate or
    retire ownership. A briefly stale card is harmless: actions call require().
    """
    return _PENDING.get(_key(context))


def _validated_current(context):
    """Action-only stale cleanup, with bounded workspace-only intent recovery."""
    proposal = current(context)
    if proposal is None:
        return None
    try:
        proposal.assert_binding(context, proposal.binding)
        if backend_runtime.configuration(context)[1] != proposal.binding["deflection"]:
            raise ValueError("Proposal tessellation settings changed")
        if hashlib.sha256(proposal.base_json.encode()).hexdigest() != proposal.base_hash:
            raise ValueError("Proposal base changed")
    except Exception:
        key = _key(context)
        _retire_stale(
            key,
            proposal,
            "Unapplied edit discarded because its document, context, units or backend changed.",
            _workspace_intent(context, key, proposal),
        )
        _notify_changed()
        return None
    return proposal if _PENDING.get(_key(context)) is proposal else None


def require(context, token):
    observed = current(context)
    proposal = _validated_current(context)
    if proposal is None or proposal.token != token:
        notice = context.scene.mechanical_cad.last_action_error
        if observed is not None and proposal is None and notice.startswith("Workspace change"):
            raise bridge.BridgeError("This proposed edit expired. " + notice)
        raise bridge.BridgeError("This proposed edit expired. Reopen and retry the upstream edit.")
    return proposal


def saved_raw(context):
    return getattr(context.scene.mechanical_cad, "repair_intent_json", "")


def resume_reserved():
    return _RESUME_OWNER is not None


def interaction_revision():
    """Runtime-only admission stamp; cancelled input cannot revive old work."""
    return _INTERACTION_REVISION


def require_no_resume():
    if resume_reserved():
        raise bridge.BridgeError(
            "Repair Resume is in progress. Cancel Resume before other CAD operations."
        )


def require_resume(token):
    if token is None or _RESUME_OWNER is not token:
        raise bridge.BridgeError("This repair Resume reservation expired.")


def reserve_resume(context, raw, token):
    global _RESUME_OWNER, _INTERACTION_REVISION
    require_none(context, resuming_raw=raw)
    if not raw or saved_raw(context) != raw or token is None:
        raise bridge.BridgeError("Saved repair intent changed before Resume.")
    _RESUME_OWNER = token
    _INTERACTION_REVISION += 1


def release_resume(token):
    global _RESUME_OWNER
    if _RESUME_OWNER is token:
        _RESUME_OWNER = None


def require_no_live_edit(context, *, resuming_token=None):
    """Accepted-only cache replay may coexist with dormant saved intent.

    This cannot authorize Resume, editing or acceptance of a proposal. Stale
    workspace-only ownership may be checkpointed before this admission check.
    """
    _validated_current(context)  # Explicit admission retires stale live ownership.
    if _RESUME_OWNER is not None and _RESUME_OWNER is not resuming_token:
        raise bridge.BridgeError(
            "Repair Resume is in progress. Cancel Resume before other editing."
        )
    if _PENDING:
        raise bridge.BridgeError(
            "An unapplied edit is retained for repair. Repair and accept it, or Discard proposed edit first."
        )


def require_none(context, *, resuming_raw=None, resuming_token=None):
    require_no_live_edit(context, resuming_token=resuming_token)
    raw = saved_raw(context)
    if raw and raw != resuming_raw:
        raise bridge.BridgeError(
            "Saved unapplied repair intent exists. Resume Repair or Discard Saved Repair first."
        )


def discard(context, token=None):
    if token is not None:
        require(context, token)
    key = _key(context)
    if _PENDING.pop(key, None) is not None:
        if saved_raw(context) and saved_raw(context) == _CHECKPOINTS.get(key):
            context.scene.mechanical_cad.repair_intent_json = ""
        _CHECKPOINTS.pop(key, None)
        _SAVE_PENDING.pop(key, None)
        _notify_changed()


def discard_saved(context):
    if resume_reserved():
        raise bridge.BridgeError("Cancel Resume before discarding saved repair intent.")
    if _validated_current(context) is not None:
        raise bridge.BridgeError("Discard the live proposed edit first.")
    context.scene.mechanical_cad.repair_intent_json = ""
    _CHECKPOINTS.pop(_key(context), None)
    _SAVE_PENDING.pop(_key(context), None)
    _DORMANT_SAVES.pop(_key(context), None)
    _notify_changed()


def before_save():
    """Checkpoint valid live work; suspend workspace-only stale work as intent."""
    _SAVE_PENDING.clear()
    for key, proposal in tuple(_PENDING.items()):
        state = proposal.binding["scene"].mechanical_cad
        try:
            with bpy.context.temp_override(window=proposal.binding["window"]):
                proposal.assert_binding(bpy.context, proposal.binding)
                if backend_runtime.configuration(bpy.context)[1] != proposal.binding["deflection"]:
                    raise ValueError("Proposal settings changed.")
            old = state.repair_intent_json
            if old != _CHECKPOINTS.get(key, ""):
                raise ValueError(
                    "Saved repair slot changed; its original text was not overwritten."
                )
            if (
                proposal.annotation_after is not None
                and state.sketch_annotation_json != proposal.annotation_before
            ):
                raise ValueError("Annotation layout changed.")
            if _PENDING.get(key) is not proposal:
                raise ValueError("Proposal ownership expired during checkpoint validation.")
            raw = repair_intent.encode(proposal)
            if _PENDING.get(key) is not proposal or state.repair_intent_json != old:
                raise ValueError("Proposal ownership or saved slot changed during serialization.")
            state.repair_intent_json = raw
            _CHECKPOINTS[key] = raw
            _SAVE_PENDING[key] = (proposal.token, raw)
            # The saved-repair card explains Resume. Success is not an error,
            # and save_pre must clear obsolete diagnostics before serialization.
            state.last_action_error = ""
        except Exception as exc:
            try:
                with bpy.context.temp_override(window=proposal.binding["window"]):
                    recovery = _workspace_intent(bpy.context, key, proposal)
            except Exception:
                recovery = None
            if recovery is not None:
                _retire_stale(key, proposal, "", recovery)
                continue
            message = (
                "Repair checkpoint failed; live work retained. This save may not contain the latest repair: "
                if _PENDING.get(key) is proposal
                else "Repair checkpoint failed; live ownership expired and no new checkpoint was saved: "
            )
            state.last_action_error = message + str(exc)
            print("Mechanical CAD repair checkpoint:", exc)
    for key, (state, raw, notice) in tuple(_DORMANT_SAVES.items()):
        try:
            if key in _PENDING or state.repair_intent_json != raw:
                _DORMANT_SAVES.pop(key, None)
                continue
            # Serialize no obsolete "memory only" warning on a successful Save.
            # Collision/foreign diagnostics are never owned by this receipt.
            if state.last_action_error == notice:
                state.last_action_error = ""
                _DORMANT_SAVES[key] = (state, raw, "")
            _SAVE_PENDING[key] = (None, raw)
        except (ReferenceError, AttributeError):
            # Dormant intent has no live supervisor; its scene may be deleted.
            _DORMANT_SAVES.pop(key, None)


def after_save(*, succeeded):
    """Only a confirmed successful Save may retire its exact checkpointed owner."""
    for key, (token, raw) in tuple(_SAVE_PENDING.items()):
        proposal = _PENDING.get(key)
        if token is None:
            dormant = _DORMANT_SAVES.get(key)
            if proposal is not None or dormant is None:
                continue
            state, expected, notice = dormant
            try:
                if state.repair_intent_json != raw or expected != raw:
                    continue
                if succeeded:
                    _DORMANT_SAVES.pop(key, None)
                    if state.last_action_error == notice:
                        state.last_action_error = ""
                else:
                    warning = "Blender Save failed; workspace repair intent remains in memory only. Save again to preserve it on disk."
                    state.last_action_error = warning
                    _DORMANT_SAVES[key] = (state, raw, warning)
            except (ReferenceError, AttributeError):
                _DORMANT_SAVES.pop(key, None)
            continue
        if proposal is None or proposal.token != token:
            continue
        state = proposal.binding["scene"].mechanical_cad
        if state.repair_intent_json != raw:
            continue
        if succeeded:
            _PENDING.pop(key, None)
            _CHECKPOINTS.pop(key, None)
            state.last_action_error = ""
        else:
            state.last_action_error = "Blender Save failed; live repair and in-memory intent checkpoint retained. Save again to preserve it on disk."
    _SAVE_PENDING.clear()
    _notify_changed()


def restore_validated(context, raw, value, results, binding, *, assert_binding, reservation=None):
    """Install freshly checked history atomically; saved data never carries authority."""
    global _INTERACTION_REVISION
    if reservation is not None:
        require_resume(reservation)
    require_none(context, resuming_raw=raw, resuming_token=reservation)
    assert_binding(context, binding)
    if saved_raw(context) != raw:
        raise bridge.BridgeError("Saved repair intent changed during Resume.")
    failures = [
        json.dumps([r for r in result["features"] if r["status"] == "failed"], allow_nan=False)
        for result in results
    ]
    proposal = ProposedEdit(
        uuid.uuid4().hex,
        value["states"][-1],
        value["feature_id"],
        failures[-1],
        dict(binding),
        value["base_hash"],
        assert_binding,
        value["annotation_before"],
        value["annotation_after"],
        tuple(zip(value["states"][:-1], failures[:-1], strict=True)),
        getattr(context.scene.mechanical_cad, "sketch_annotation_json", ""),
    )
    if not bpy.app.timers.is_registered(_supervise):
        bpy.app.timers.register(_supervise, first_interval=0.2)
    # Clearing happens last, after all validation and fallible setup. On failure
    # the caller still owns the untouched raw intent and no transient proposal.
    assert_binding(context, binding)
    if saved_raw(context) != raw:
        raise bridge.BridgeError("Saved repair intent changed during owner setup.")
    if reservation is not None:
        require_resume(reservation)
    require_none(context, resuming_raw=raw, resuming_token=reservation)
    context.scene.mechanical_cad.repair_intent_json = ""
    _DORMANT_SAVES.pop(_key(context), None)
    _PENDING[_key(context)] = proposal
    _INTERACTION_REVISION += 1
    _notify_changed()
    return proposal


def advance_validated(context, token, document, result):
    """Keep validated partial progress, never canonical state or native receipts."""
    proposal = require(context, token)
    if (
        len(proposal.repairs) + 1 >= repair_intent.MAX_STATES
        or sum(len(candidate) + len(failed) for candidate, failed in proposal.repairs)
        + len(proposal.candidate_json)
        + len(proposal.failed_json)
        > 16 * 1024 * 1024
    ):
        raise bridge.BridgeError(
            "Proposal repair history is full. Undo repairs or discard the proposal."
        )
    _PENDING[_key(context)] = replace(
        proposal,
        token=uuid.uuid4().hex,
        candidate_json=json.dumps(document, allow_nan=False),
        failed_json=json.dumps(
            [row for row in result["features"] if row["status"] == "failed"],
            allow_nan=False,
        ),
        repairs=proposal.repairs + ((proposal.candidate_json, proposal.failed_json),),
    )
    _notify_changed()


def undo_repair(context, token):
    """Explicit proposal-local reversal; ordinary Blender Undo remains untouched."""
    proposal = require(context, token)
    if not proposal.repairs:
        raise bridge.BridgeError("There is no proposal repair to undo.")
    candidate_json, failed_json = proposal.repairs[-1]
    _PENDING[_key(context)] = replace(
        proposal,
        token=uuid.uuid4().hex,
        candidate_json=candidate_json,
        failed_json=failed_json,
        repairs=proposal.repairs[:-1],
    )
    _notify_changed()


def repairable_failures(document, feature_id, result, *, ancestry_document=None):
    """Conservative reference-only failure closure; no solver/kernel recovery."""
    features = {row["id"]: row for row in document["features"]}
    original = {row["id"]: row for row in (ancestry_document or document)["features"]}

    def ancestors(identifier, graph=features):
        pending = list(graph[identifier].get("inputs", {}).values())
        found = set()
        while pending:
            source = pending.pop()
            if source not in found:
                found.add(source)
                pending.extend(graph.get(source, {}).get("inputs", {}).values())
        return found

    failures = [row for row in result["features"] if row["status"] == "failed"]
    for row in failures:
        feature = features[row["id"]]
        code = (row.get("error") or {}).get("code")
        sketch_reference = feature.get("kind") == "sketch_constrained" and (
            code == "invalid_sketch_support"
            and "support" in feature.get("inputs", {})
            or code == "invalid_sketch_projection"
            and feature.get("projections")
        )
        end_reference = (
            feature.get("kind") == "extrude_to_face"
            and code == "invalid_extrusion_end_face"
            and set(feature.get("inputs", {})) == {"profile", "target"}
            and bool(feature.get("end_face"))
        )
        # Explicit replacement may sever the edited source's dependency. Keep
        # the initial failed branch eligible, not arbitrary newly failing rows.
        if feature_id not in ancestors(row["id"], original) or not (
            sketch_reference or end_reference
        ):
            return False
    failed_ids = {row["id"] for row in failures}
    return bool(failures) and all(
        row["status"] != "blocked" or ancestors(row["id"]) & failed_ids
        for row in result["features"]
    )


def retain_validated(
    context,
    document,
    feature_id,
    result,
    binding,
    *,
    assert_binding,
    annotation_before=None,
    annotation_after=None,
):
    """Store an already validated failed replay; never validate or publish geometry.

    The document coordinator supplies its captured binding validator. This
    capability is used only to revoke the transient proposal, not to authorize
    a candidate publication. Publication still requires fresh native evidence.
    """
    global _INTERACTION_REVISION
    require_none(context)
    assert_binding(context, binding)
    rows = {row["id"]: row for row in result["features"]}
    if rows.get(feature_id, {}).get("status") != "ok":
        return False
    base = json.loads(binding["document_json"])
    original = {f["id"]: f for f in base["features"]}
    proposed = {f["id"]: f for f in document["features"]}
    # Only a same-graph edit, never an add/delete/import or active-output change.
    if set(original) != set(proposed) or any(
        base.get(key) != document.get(key) for key in set(base) | set(document) if key != "features"
    ):
        return False

    if not repairable_failures(document, feature_id, result):
        return False
    if any(
        (row.get("error") or {}).get("code") == "invalid_extrusion_end_face"
        for row in result["features"]
    ):
        try:
            # This slice retains one authorized upstream feature edit only.
            # Its immutable first graph later bounds partial-repair eligibility.
            repair_intent.original_scope(base, document, feature_id)
        except ValueError:
            return False
    _PENDING[_key(context)] = ProposedEdit(
        uuid.uuid4().hex,
        json.dumps(document, allow_nan=False),
        feature_id,
        json.dumps(
            [row for row in result["features"] if row.get("status") == "failed"], allow_nan=False
        ),
        dict(binding),
        hashlib.sha256(binding["document_json"].encode()).hexdigest(),
        assert_binding,
        annotation_before,
        annotation_after,
        accepted_annotations=getattr(context.scene.mechanical_cad, "sketch_annotation_json", ""),
    )
    _DORMANT_SAVES.pop(_key(context), None)
    _INTERACTION_REVISION += 1
    try:
        if not bpy.app.timers.is_registered(_supervise):
            bpy.app.timers.register(_supervise, first_interval=0.2)
    except Exception:
        _PENDING.pop(_key(context), None)
        raise
    _notify_changed()
    return True
