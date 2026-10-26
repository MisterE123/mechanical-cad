"""One-shot main-thread publication of an exact, already completed Part replay.

Capture starts no native work. The async owner launches the returned request and
retires this RNA-bearing intent before load/history/disable can invalidate it.
A response is revalidated here; neither cached meshes nor a previous validation
boolean authorize publication. Failed publication leaves the caller's draft alone.
"""

import json
import threading

from . import (
    backend_contracts,
    backend_runtime,
    bridge,
    document_state,
    draft_dispatch,
    sketch_annotation_store,
    staged_edit_store,
    workspace,
)
from .guarded_evidence import GuardedEvidence
from .request_contracts import snapshot_request


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise bridge.BridgeError("Part publication is only available on Blender's main thread.")


def _configuration(context):
    return backend_runtime.configuration(context)


def _owner_snapshot(context, *, require_original_base=True):
    owner = workspace.active_draft(context)
    if owner is None:
        return None
    if not owner.alive or (require_original_base and not owner.valid_context()):
        raise bridge.BridgeError("The original sketch owner is no longer available.")
    return owner.session_id, draft_dispatch.dumps(owner.draft)


class PartPublicationIntent:
    """Captured native bindings; transient, never serialized or handed to a worker.

    Call ``retire`` before its owner is invalidated, regardless of job state.
    Transport workers receive only detached request/configuration dictionaries.
    Publication is one-shot, including busy rejection; retry is an explicit fresh
    action, never a queued acceptance of an old completion.
    """

    def __init__(
        self, context, operation, selection, path, annotation_layout=None, *, owner_token=None
    ):
        # Every intent owns a newly minted G. Accepting a caller's PreparedRequest
        # would let a replacement intent adopt a retired intent's completion.
        if type(operation) is not dict:
            raise bridge.BridgeError(
                "Part publication requires an ordinary replay operation, not a prepared replay."
            )
        try:
            request = snapshot_request(operation)
            if (
                set(request)
                != {"protocol_version", "action", "result_version", "document", "options"}
                or type(request["protocol_version"]) is not int
                or request["protocol_version"] != 1
                or request["action"] != "replay"
                or type(request["result_version"]) is not int
                or type(request["options"]) is not dict
                or set(request["options"]) != {"linear_deflection"}
                or type(request["options"]["linear_deflection"]) not in (int, float)
                or not 0.001 <= request["options"]["linear_deflection"] <= 10
            ):
                raise ValueError("Part publication requires an explicit typed replay operation.")
            version = document_state._result_version(
                request["document"], request["result_version"], action="replay"
            )
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            raise bridge.BridgeError(f"Cannot capture this Part operation: {exc}") from exc
        self.selection = selection
        self.owner_token = object() if owner_token is None else owner_token
        self._binding = document_state._capture_binding(
            context, selection=selection, owner_token=self.owner_token
        )
        if request["options"]["linear_deflection"] != self._binding["deflection"]:
            raise bridge.BridgeError("Part operation differs from the captured mesh tolerance.")
        prepared = backend_contracts.prepare_request(request)
        self.prepared = prepared
        self._request_json = json.dumps(request, allow_nan=False)
        self._candidate_json = json.dumps(request["document"], allow_nan=False)
        self._path = path
        self._binding["prepared"] = prepared
        self._binding["request_fingerprint"] = prepared.fingerprint
        self._binding["result_version"] = version
        self._workspace = getattr(context, "workspace", None)
        self._draft_slot = context.scene.mechanical_cad.sketch_draft_json
        self._owner_snapshot = _owner_snapshot(context)
        self._retired = False
        self._annotation_before = context.scene.mechanical_cad.sketch_annotation_json
        self._annotation_after = annotation_layout

    @property
    def retired(self):
        return self._retired

    @property
    def request(self):
        return json.loads(self._request_json)

    def retire(self):
        """Idempotently drop all captured RNA references, even before cleanup ends."""
        self._retired = True
        self._binding = None
        self._workspace = None
        self._owner_snapshot = None

    def _assert_current(self, context):
        if self._retired:
            raise bridge.BridgeError(
                "This Part publication intent was retired; request Finish again."
            )
        document_state._assert_binding(context, self._binding)
        self._assert_editor_current(context)

    def _assert_editor_current(self, context, *, publishing=False, layout_written=False):
        # The canonical candidate has already changed at the post-publication
        # check. All editor/configuration intent must still be the captured one.
        if self._retired:
            raise bridge.BridgeError("The sketch publication intent was retired.")
        if (
            getattr(context, "workspace", None) != self._workspace
            or context.scene.mechanical_cad.sketch_draft_json != self._draft_slot
            or _owner_snapshot(context, require_original_base=not publishing)
            != self._owner_snapshot
        ):
            raise bridge.BridgeError(
                "The sketch owner, workspace or saved draft changed; retry Finish."
            )
        if (
            self._annotation_after is not None
            and context.scene.mechanical_cad.sketch_annotation_json
            != (self._annotation_after if layout_written else self._annotation_before)
        ):
            raise bridge.BridgeError(
                "Saved annotation layout changed; retry Finish without overwriting it."
            )
        backend_runtime.assert_current(self.selection, context)

    def _publish_layout(self, context):
        """UI-only metadata write remains inside the common rollback boundary."""
        self._assert_editor_current(context, publishing=True)
        if self._annotation_after is not None:
            self._write_layout(context.scene.mechanical_cad, self._annotation_after)
            self._assert_editor_current(context, publishing=True, layout_written=True)

    @staticmethod
    def _write_layout(state, serialized):
        state.sketch_annotation_json = serialized

    def retain_failed_edit(self, context, evidence, feature_id):
        """Transfer a complete existing sketch candidate, never a partial draft.

        This uses the Finish operation's original exact evidence and editor
        snapshot. The caller still owns its draft until this returns True, and
        must discard this proposal if releasing the saved draft fails.
        """
        _main_thread()
        with document_state.replay_guard(context):
            self._assert_current(context)
            owner = workspace.active_draft(context)
            if (
                owner is None
                or not owner.commands.is_edit
                or owner.commands.feature_id != feature_id
                or not owner.can_finish
                or self.request["document"] != owner.commands.candidate()
            ):
                return False
            accepted = document_state.current_part_result(context)
            if accepted is None or accepted.get("status") != "ok":
                return False
            response = document_state._evidence_projection(
                context, self.request["document"], evidence, self._binding
            )
            if response["ok"] or response["result"].get("status") == "ok":
                return False
            # A solved sketch followed by an unrelated kernel/constraint error
            # is still an editable draft, not a reference-repair proposal.
            if any(
                row.get("status") == "failed"
                and (row.get("error") or {}).get("code")
                not in {
                    "invalid_sketch_projection",
                    "invalid_sketch_support",
                    "nonplanar_support",
                    "invalid_support_plane",
                }
                for row in response["result"]["features"]
            ):
                return False
            self._assert_current(context)
            retained = staged_edit_store.retain_validated(
                context,
                self.request["document"],
                feature_id,
                response["result"],
                self._binding,
                assert_binding=document_state._assert_binding,
                annotation_before=self._annotation_before,
                annotation_after=self._annotation_after,
            )
            if retained:
                evidence.publication.cancel()
            return retained

    def publish(self, context, evidence):
        """Reacquire execution, revalidate exact evidence, then use shared rollback.

        The transport must already be reaped and its lease released. This method
        performs no sidecar launch. Its synchronous main-thread guard covers both
        freshness checks and canonical/display publication, with no queued retry.
        """
        _main_thread()
        try:
            with document_state.replay_guard(context):
                self._assert_current(context)
                request = self.request
                if type(evidence) is not GuardedEvidence:
                    raise bridge.BridgeError(
                        "Part replay evidence was rejected: guarded evidence is required."
                    )
                if (
                    backend_contracts.request_fingerprint(evidence.guarded_request())
                    != self.prepared.fingerprint
                ):
                    raise bridge.BridgeError(
                        "Part replay evidence was rejected: different guarded operation."
                    )
                document_state._evidence_projection(
                    context, request["document"], evidence, self._binding
                )
                self._assert_current(context)
                return document_state._publish_candidate_locked(
                    context,
                    request["document"],
                    evidence,
                    self._binding,
                    self._candidate_json,
                    self._path,
                    validate_publication=lambda: self._publish_layout(context),
                    verify_publication=lambda: self._assert_editor_current(
                        context, publishing=True, layout_written=True
                    ),
                )
        finally:
            # A rejected exact completion cannot be recycled through a fresh
            # intent. Consumed claims stay consumed; unrelated G is untouched.
            try:
                if type(evidence) is GuardedEvidence and (
                    backend_contracts.request_fingerprint(evidence.guarded_request())
                    == self.prepared.fingerprint
                ):
                    evidence.publication.cancel()
            finally:
                self.retire()


def prepare(
    context, document, path="", *, annotation_layout=None, selection=None, owner_token=None
):
    """Capture an explicit typed replay request and all original publication bindings."""
    _main_thread()
    if context.mode != "OBJECT":
        raise bridge.BridgeError("Return to Object Mode before requesting Finish.")
    if type(path) is not str:
        raise bridge.BridgeError("The retained Part path must be text.")
    if annotation_layout is not None:
        try:
            sketch_annotation_store.validate(annotation_layout)
        except (TypeError, ValueError) as exc:
            raise bridge.BridgeError(f"Cannot capture annotation layout: {exc}") from exc
    document_state._preflight_owned_display(context.scene)
    current, deflection = _configuration(context)
    if selection is None:
        selection = current
    else:
        selection.assert_current(current)
    try:
        request = snapshot_request(
            {
                "protocol_version": 1,
                "action": "replay",
                "result_version": document_state._result_version(document, action="replay"),
                "document": document,
                "options": {"linear_deflection": deflection},
            }
        )
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise bridge.BridgeError(f"Cannot capture this Part candidate: {exc}") from exc
    return PartPublicationIntent(
        context, request, selection, path, annotation_layout, owner_token=owner_token
    )
