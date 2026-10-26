"""Shared-owner integration for explicit general-sketch commands and async work.

This module owns one transient Blender session, never a second lifecycle registry.
The pure wrapper owns intent; sketch_pending owns detached native work. No pointer
operation runs a solver. Finish alone publishes canonical Part data.
"""

import copy
import hashlib
import json
import uuid
import weakref
from dataclasses import dataclass, replace
from types import MappingProxyType

from . import (
    assembly_job_ui,
    backend_contracts,
    backend_runtime,
    bridge,
    constraint_diagnostics,
    dimension_input,
    document_state,
    draft_dispatch,
    execution_lease,
    general_authoring,
    general_proposals,
    general_sketch_draft,
    general_view_geometry,
    operation_contracts,
    part_publication,
    sketch_annotation_store,
    sketch_pending,
    sketch_projection,
    sketch_support_evidence,
    sketch_view_presentation,
    staged_edit_store,
    workspace,
)
from .circle_diameter_session import CircleDiameterSession
from .common import _state
from .display import _focus_display
from .general_sketch_commands import (
    AddProjectionGeometry,
    CornerFillet,
    MovePoint,
    PointRef,
    PointSeed,
    RemoveCornerFillet,
    ReverseArcSweep,
)
from .line_length_session import LineLengthSession
from .recovery_capture import settled_transaction
from .sketch_remove_fillet_session import RemoveFilletSession
from .sketch_session import SketchSession, _discard_stored, _tag_redraw

DraftError = general_sketch_draft.DraftError


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


POINT_PICKER_EMPTY = ((":choose_point:", "Choose an exact point ID", "No point selected"),)
POINT_SOURCE_EMPTY = (("point", "Choose a point first", "No point selected"),)


@dataclass(frozen=True)
class _PointPickerCatalog:
    """Frozen presentation strings; the gesture, not its token, admits input."""

    token: str
    sentinel: str
    point_items: tuple
    source_items: MappingProxyType
    source_bindings: MappingProxyType


def _point_picker_catalog(sketch, points):
    if not 0 < len(points) <= 256:
        raise DraftError("The exact-point picker supports between 1 and 256 points.")
    sentinel = POINT_PICKER_EMPTY[0][0]
    while sentinel in points:
        sentinel += ":"
    point_items = ((sentinel, *POINT_PICKER_EMPTY[0][1:]),) + tuple(
        (identifier, identifier, "Reuse exact point " + identifier) for identifier in points
    )
    source_items = {sentinel: POINT_SOURCE_EMPTY}
    source_bindings = {"point": (None, None, None)}
    for identifier in points:
        options = [
            (
                "point",
                "Point identity: " + identifier,
                "Use this exact point without a curve-role label",
            )
        ]
        for kind, collection, roles in (
            ("line", "lines", ("start", "end")),
            ("circle", "circles", ("center",)),
            ("arc", "arcs", ("center", "start", "end")),
        ):
            for curve in sketch.get(collection, ()):
                for role in roles:
                    if curve[role] == identifier:
                        token = f"{kind}:{curve['id']}:{role}"
                        source_bindings[token] = (kind, curve["id"], role)
                        options.append(
                            (
                                token,
                                f"{kind.title()} {curve['id']} · {role}",
                                "Exact source role for " + identifier,
                            )
                        )
        source_items[identifier] = tuple(options)
    return _PointPickerCatalog(
        uuid.uuid4().hex,
        sentinel,
        point_items,
        MappingProxyType(source_items),
        MappingProxyType(source_bindings),
    )


@dataclass(frozen=True)
class _GestureIntent:
    """One owner-bound dialog; pure authored intent, never native authority."""

    kind: str
    owner_token: object
    draft: object
    commands: object
    snapshot: str
    saved_slot: str
    identity: str
    selection: object
    phase: tuple | None
    capture: bool
    points: tuple
    point_catalog: _PointPickerCatalog | None = None


class GeneralSession(RemoveFilletSession, CircleDiameterSession, LineLengthSession, SketchSession):
    """One exact-base owner with unverified pointer intent and explicit work."""

    def __init__(
        self,
        context,
        feature_id="",
        *,
        restored=None,
        plane=None,
        support=None,
        support_intent=None,
    ):
        annotation_notice = ""
        if restored is None:
            source = _state(context).document_json
            version = operation_contracts.result_version_for(
                json.loads(source), action="solve_sketch", owner_role="general"
            )
            restored = general_authoring.GeneralSketchAuthoringState(
                general_sketch_draft.GeneralSketchDraft(
                    source,
                    feature_id,
                    bool(feature_id),
                    journal_version=3 if version == 3 else 2,
                    plane=plane,
                    support=support,
                    support_intent=support_intent,
                ),
                ui_version=2 if version == 3 else 1,
            )
            if feature_id:
                lookup = sketch_annotation_store.annotations_for(
                    _state(context).sketch_annotation_json,
                    json.loads(restored.document_json)["id"],
                    feature_id,
                    restored.command_draft.sketch,
                )
                ui = restored.ui_payload()
                ui["annotations"] = lookup.annotations
                from .reference_dimensions import is_reference

                ui["annotations"].update(
                    {
                        key: conflict.binding
                        for key, conflict in lookup.unavailable.items()
                        if is_reference(conflict.binding) or "retirement" in conflict.binding
                    }
                )
                restored = general_authoring.GeneralSketchAuthoringState(
                    restored.command_draft, ui, ui_version=restored.ui_version
                )
                conflicts = [item for item in lookup.unavailable.values() if item.state != "retired"]
                if conflicts:
                    annotation_notice = f"{len(conflicts)} saved annotation placements are unavailable; retained for recovery."
        elif type(restored) is general_sketch_draft.GeneralSketchDraft:
            restored = general_authoring.GeneralSketchAuthoringState.from_v1_draft(restored)
        if type(restored) is not general_authoring.GeneralSketchAuthoringState:
            raise DraftError("Choose a general sketch draft with a supported explicit version.")
        self.display_plane = restored.command_draft.sketch["plane"]
        source_feature = next(
            f
            for f in restored.command_draft.candidate()["features"]
            if f["id"] == restored.feature_id
        )
        self.support_face = source_feature.get("support_face", "")
        self.support_notice = ""
        self.support_decision = None
        if sketch_support_evidence.attached(source_feature):
            result = document_state.current_part_result(context)
            if result is None:
                raise DraftError(
                    "Rebuild the Part before opening its attached sketch; the saved draft is retained."
                )
            self.display_plane = sketch_support_evidence.world_plane(
                source_feature, result["features"]
            )
            from .support_intent_edit import support_decision

            self.support_decision = support_decision(source_feature, result)
            orientation = (
                "Minimal twist"
                if "orientation" in source_feature.get("support_intent", {})
                else "World axes"
            )
            self.support_notice = (
                f"ASSUMED: Preserve logical plane; {orientation}; no fragment selected."
                if self.support_decision["status"] == "assumed"
                else f"Support: Preserve logical plane; {orientation} orientation."
                if "support_intent" in source_feature
                else "Support policy: Strict exact face; stop if identity is lost."
            )
        super().__init__(context, restored, restored=bool(_state(context).sketch_draft_json))
        self.owner_token = object()
        self._backend_context = context
        self._bound_commands = weakref.WeakSet()
        self.guarded_evidence = None
        self.expected_prepared = None
        self._bind_commands(self.commands)
        self.pending = None
        self.pending_kind = ""
        self.pending_prepared = None
        self.publication = None
        self.evidence_request = self.evidence_response = None
        self.trial_evidence = None
        self.trial_prepared = None
        self.length_attempt = None
        self.diameter_attempt = None
        self.removal_attempt = None
        self._failure_diagnostics = None
        self._build_failure = None
        self.input_token = ""
        self.input_controller = None
        self.message = "Unverified sketch. Choose Line, Circle or Center Arc to draw."
        self.annotation_notice = annotation_notice
        self.error = ""
        self.finished = False
        self.retained_for_repair = False
        self.command = ""
        self.navigation = False
        self.proposal_capture = False
        self.gesture_intent = None
        self.annotation_drag = None
        self.point_drag = None
        self.selection_mode = "geometry"  # transient, never a saved intent field
        self.field_position = (100, 100)
        self.geometry_cache = None
        self.geometry_key = None
        self.retained_outline = None
        self.retained_revision = None
        self.mesh_visibility = None

    @property
    def commands(self):
        return self.draft.command_draft

    @property
    def current_diagnostics(self):
        """Failure candidates for this exact live request; never solve authority."""
        diagnostics = self._failure_diagnostics
        if diagnostics is None:
            return None
        try:
            self._require_current()
            current_selection = self._backend_current_selection()
            edit = self.commands.pending_edit
            current = diagnostics.for_current(
                self.commands.solve_request(trial=edit is not None),
                session_id=self.session_id,
                command_revision=self.commands.revision,
                input_token=self.input_token,
                input_revision=edit.input_revision if edit is not None else None,
                current_selection=current_selection,
                owner_token=self.owner_token,
            )
            if current is None:
                self._failure_diagnostics = None
            return current
        except (DraftError, ValueError, RuntimeError, TypeError, KeyError, ReferenceError):
            # Once an owner observes a broken source/context/input binding, the
            # old diagnostic is retired even if those bytes later reappear.
            self._failure_diagnostics = None
            return None

    @property
    def can_finish(self):
        if not (
            self.alive
            and self.pending is None
            and not self.draft.proposal
            and self.commands.pending_edit is None
        ):
            return False
        response = self.current_solution_response()
        return response is not None and (
            not any(
                not arc.get("construction", False) for arc in self.commands.sketch.get("arcs", [])
            )
            or response["result"]["profile_check"]["ready"]
            or (response["result"]["profile_check"].get("error") or {}).get("code")
            == "open_profile"
        )

    @property
    def current_build_failure(self):
        """Read labeled solve/native-attempt facts without exposing seed authority."""
        attempt = self._build_failure
        if attempt is None:
            return None
        try:
            self._require_current()
            edit = self.commands.pending_edit
            snapshot = attempt.for_current(
                self.commands.solve_request(trial=edit is not None),
                current_selection=self._backend_current_selection(),
                owner_token=self.owner_token,
                session_id=self.session_id,
                command_revision=self.commands.revision,
                input_token=self.input_token,
                input_revision=edit.input_revision if edit is not None else None,
            )
            if snapshot is None:
                self._build_failure = None
            return snapshot
        except (ValueError, RuntimeError, TypeError, KeyError, AttributeError, ReferenceError):
            self._build_failure = None
            return None

    def _bind_commands(self, commands):
        commands.bind_guarded(self.owner_token, self._backend_current_selection)
        self._bound_commands.add(commands)

    def _backend_current_selection(self):
        self._require_current()
        if self._backend_context is None:
            raise DraftError("The sketch backend owner was retired.")
        return backend_runtime.capture(self._backend_context)

    def backend_stamp(self):
        """Observe defaults even for authored-only prepared constraint intents."""
        try:
            self._backend_current_selection()
        except (bridge.BridgeError, DraftError, ReferenceError):
            self.invalidate_backend("Backend settings unavailable; Check again.")
        return backend_runtime.stamp()

    def current_solution_response(self):
        """Fresh detached projection only; saved dictionaries are never authority."""
        evidence = self.guarded_evidence
        if evidence is None:
            return None
        try:
            self._require_current()
            if not self.commands.has_current_solution:
                return None
            if (
                self.commands._solution_evidence[0] is not evidence
                or self.commands._solution_prepared[0] is not self.expected_prepared
            ):
                raise DraftError("The original solve association changed.")
            response = general_sketch_draft.read_guarded_operation(
                evidence,
                self.expected_prepared,
                self._backend_current_selection(),
                owner_token=self.owner_token,
                action="solve_sketch",
                require_success=True,
            )
            if sketch_pending._exact_json(response) != sketch_pending._exact_json(
                self.evidence_response
            ):
                raise DraftError("The public sketch response changed.")
            if sketch_pending._exact_json(
                evidence.operation_request()
            ) != sketch_pending._exact_json(self.commands.solve_request()):
                raise DraftError("The checked sketch request changed.")
            return response
        except (ValueError, RuntimeError, TypeError, AttributeError, ReferenceError):
            self.invalidate_backend("Sketch evidence is stale; Check again.")
            return None

    @property
    def current_native_build_status(self):
        """Separate a checked downstream build from a successful solve alone."""
        if self.current_solution_response() is None:
            return "not_checked"
        chain = self.commands._solution_prepared
        return (
            "succeeded"
            if chain is not None
            and len(chain) == 2
            and chain[1].operation_request().get("action") == "replay"
            else "not_checked"
        )

    def invalidate_backend(self, reason="Backend settings changed; Check again."):
        """Revoke runtime authority, preserving all authored/draft/layout bytes."""
        self.gesture_intent = None
        self.proposal_capture = False
        cached = self.geometry_cache
        if cached is not None and cached.source == "solved":
            self.retained_outline = general_view_geometry.retained_outline(cached)
            self.retained_revision = self.commands.revision
        for commands in tuple(self._bound_commands):
            commands.invalidate_solution()
        self._clear_display_evidence()
        self.cancel_native(reason)
        if self.alive:
            _tag_redraw(self)

    @property
    def can_edit_dimensions(self):
        return False  # The rectangle-specific popup must never receive this owner.

    def can_use_tool(self, tool):
        """Shared capability predicate for operators and contextual controls."""
        if not self.valid_context() or getattr(self, "solid_projection_picker", None) is not None:
            return False
        line_edit = getattr(self, "line_edit", None)
        if line_edit is not None:
            return tool == "CancelLineEdit" or (
                tool == "ApplyLineEdit"
                and line_edit.get("preview") is not None
                and self.pending is None
                and line_edit["revision"] == self.commands.revision
            )
        if tool in {"ApplyLineEdit", "CancelLineEdit"}:
            return False
        if getattr(self, "point_drag", None) is not None:
            return False
        pending_input = self.commands.pending_edit is not None or self.draft.pending_length is not None or self.draft.pending_diameter is not None
        proposal = self.draft.proposal is not None
        if tool == "CancelCheck":
            return self.pending is not None
        if tool == "CancelInput":
            return pending_input
        if self.pending is not None or getattr(self, "gesture_intent", None) is not None:
            return False
        if tool == "Reopen":
            controller = self.input_controller
            return pending_input and (controller is None or controller.closed)
        if tool == "CancelProposal":
            return proposal
        if tool == "Continue":
            return proposal and not pending_input and self.draft.status.proposal.available
        if tool in {"Arc", "Reverse", "UsePoint", "Trim", "Extend"} and (
            self.annotation_drag is not None or self.publication is not None
        ):
            return False
        if tool == "UsePoint":
            return (
                not pending_input
                and self.draft.point_input_phase is not None
                and (not proposal or self.draft.status.proposal.available)
                and 0 < len(self.commands.sketch["points"]) <= 256
            )
        if tool == "Reverse":
            if pending_input:
                return False
            if proposal:
                return self.draft.proposal["kind"] == "arc" and self.draft.status.proposal.available
            selected = self.draft.selection
            return (
                len(selected) == 1
                and selected[0]["kind"] == "arc"
                and any(
                    item["id"] == selected[0]["id"] for item in self.commands.sketch.get("arcs", ())
                )
            )
        if pending_input or proposal:
            return False
        sketch = self.commands.sketch
        if tool == "RemoveFillet":
            # Presentation hint only. Current guarded evidence is checked by the
            # review invocation and Apply, never on each palette/pointer redraw.
            selected = self.draft.selection
            return (len(selected) == 1 and selected[0]["kind"] == "arc"
                    and any(a["id"] == selected[0]["id"] and "fillet_intent" in a
                            for a in sketch.get("arcs", [])))
        if tool == "CornerFillet":
            selected = self.draft.selection
            return (len(selected) == 2 and all(item["kind"] == "line" for item in selected)
                    and self.current_solution_response() is not None)
        if tool == "Arc":
            return sum(len(sketch.get(name, [])) for name in ("lines", "circles", "arcs")) < 256
        if tool in {"Check", "Finish"}:
            return (
                not execution_lease.is_busy()
                and not document_state._REPLAY_RUNNING
                and (tool == "Check" or self.can_finish)
            )
        return tool in {
            "Select",
            "Points",
            "Line",
            "Rectangle",
            "Circle",
            "Dimension",
            "Trim",
            "Extend",
        }

    def start(self, callbacks=()):
        try:
            if not self.valid_context():
                raise DraftError("The original sketch viewport is no longer available.")
            self.start_resources(
                callbacks,
                "In-context CAD sketch: Line / Circle / Center Arc / Dimension; local Ctrl-Z; Finish commits; Esc suspends",
            )
            self.mesh_visibility = sketch_view_presentation.SketchContextLease(
                self.area.spaces.active
            )
        except Exception:
            self.cleanup()
            raise

    def valid_context(self):
        valid = super().valid_context()
        if not valid:
            self.gesture_intent = None
            self.proposal_capture = False
            self._failure_diagnostics = None
            self._build_failure = None
        return valid

    def checkpoint(self):
        # Shared persistence may run directly during suspension/history changes.
        # It must still retain recoverable draft bytes when context is stale,
        # while diagnostic currency is permanently retired on observation.
        self.valid_context()
        try:
            return super().checkpoint()
        except Exception:
            self.gesture_intent = None
            self.proposal_capture = False
            self._failure_diagnostics = None
            self._build_failure = None
            raise

    def _require_current(self):
        try:
            if not self.alive or not self.valid_context():
                raise DraftError("The original sketch scene, workspace or document changed.")
            if self.scene.mechanical_cad.sketch_draft_json != self.stored_snapshot:
                raise DraftError("The saved draft changed externally; no draft was overwritten.")
            self.draft.require_current(self.scene.mechanical_cad.document_json)
        except (DraftError, ReferenceError):
            self.gesture_intent = None
            self.proposal_capture = False
            # Every observed owner rejection retires diagnostic currency, not
            # only an inspector query. A later A→B→A restoration needs new work.
            self._failure_diagnostics = None
            self._build_failure = None
            raise

    def _require_idle(self):
        self._require_current()
        if getattr(self, "point_drag", None) is not None:
            raise DraftError("Release or cancel the point drag before another action.")
        if self.pending is not None:
            raise DraftError("A sketch check is running. Cancel it or wait before editing.")
        if execution_lease.is_busy() or document_state._REPLAY_RUNNING:
            raise DraftError(execution_lease.BUSY_MESSAGE)

    def _retain_outline(self):
        # This is a display-only copy of the accepted geometry, with its solver
        # fingerprint deliberately removed. Raw edits must not jump to old seeds.
        if self.commands.has_current_solution and self.evidence_response is not None:
            self.retained_outline = general_view_geometry.retained_outline(self.geometry())
            self.retained_revision = self.commands.revision

    def _clear_display_evidence(self):
        self._failure_diagnostics = None
        self._build_failure = None
        self.evidence_request = self.evidence_response = None
        self.guarded_evidence = None
        self.expected_prepared = None
        self.geometry_cache = self.geometry_key = None

    def identity(self, context, selection):
        """Detached exact acceptance bindings; no native reference enters a job."""
        self._require_current()
        return {
            "session": self.session_id,
            "scene": self.scene_uid,
            "window": self.window.as_pointer(),
            "view_layer": self.window.view_layer.as_pointer(),
            "workspace": self.workspace.as_pointer(),
            "area": self.area.as_pointer(),
            "base": _digest(self.scene.mechanical_cad.document_json),
            "saved_slot": _digest(self.scene.mechanical_cad.sketch_draft_json),
            "intent": _digest(draft_dispatch.dumps(self.draft)),
            "input_token": self.input_token,
            "configuration": {
                "lifetime": selection.lifetime_id,
                "generation": selection.generation,
                "root": selection.project_root,
                "python": selection.python_executable,
                "target": selection.python_executable_target,
                "timeout": selection.timeout,
            },
            "unit_scale": float(self.scene.unit_settings.scale_length),
        }

    def _start_job(self, context, request, kind, *, selection=None, prepared=None):
        self._require_idle()
        if selection is None:
            selection = backend_runtime.capture(context)
        else:
            backend_runtime.assert_current(selection, context)
        if prepared is None:
            prepared = backend_contracts.prepare_request(request)
        if sketch_pending._exact_json(prepared.operation_request()) != sketch_pending._exact_json(
            request
        ):
            raise DraftError("Prepared sketch request changed before launch.")
        # Register cleanup before acquiring a lease or creating a child. Native
        # timers cannot run during this main-thread call; failed setup starts no
        # process and therefore cannot strand an unreachable cancelling handle.
        assembly_job_ui.ensure_supervisor()
        self.pending = sketch_pending.prepare_guarded(
            prepared,
            self.identity(context, selection),
            selection=selection,
            owner_token=self.owner_token,
        )
        self.pending_kind = kind
        self.pending_prepared = prepared
        self._failure_diagnostics = None
        self._build_failure = None
        self.error = ""
        self.message = (
            "Checking "
            + ("downstream features" if kind in {"downstream", "finish"} else "sketch")
            + ". Navigate or Cancel Check."
        )
        _tag_redraw(self)

    def cancel_native(self, reason="Sketch check cancelled; draft retained."):
        self._failure_diagnostics = None
        self._build_failure = None
        publication, self.publication = self.publication, None
        if publication is not None:
            publication.retire()
        pending, self.pending = self.pending, None
        self.pending_kind = ""
        self.pending_prepared = None
        self.trial_evidence = None
        self.trial_prepared = None
        self.length_attempt = None
        self.diameter_attempt = None
        self.removal_attempt = None
        if self.commands.pending_edit is not None:
            self.commands.invalidate_solution()
        try:
            if pending is not None:
                sketch_pending.cancel(pending, reason)
                assembly_job_ui.ensure_supervisor()
        finally:
            # A cancelled trial cannot remain latched as a pending acceptance.
            # Raw text and its edit lease remain available for an explicit retry.
            if self.input_controller is not None:
                self.input_controller.reject_accept()
        self.message = reason

    def _detach_input(self):
        # This hook runs after the shared owner is retired, before RNA teardown.
        self.input_token = ""
        for commands in tuple(self._bound_commands):
            commands.retire_guarded()
        self._bound_commands.clear()
        self._backend_context = None
        controller, self.input_controller = self.input_controller, None
        self.proposal_capture = False
        self.gesture_intent = None
        self.annotation_drag = None
        self.point_drag = None
        picker = getattr(self, "solid_projection_picker", None)
        self.solid_projection_picker = None
        if picker is not None:
            try:
                picker.close()
            except Exception as exc:
                self.cleanup_errors.append(f"solid edge picker: {exc}")
        try:
            self.cancel_native("Sketch owner retired; pending result cannot be accepted.")
        finally:
            self._clear_display_evidence()
            self.retained_outline = self.retained_revision = None
            try:
                if controller is not None:
                    controller.retire()
            finally:
                visibility, self.mesh_visibility = self.mesh_visibility, None
                if visibility is not None:
                    diagnostic = visibility.restore()
                    if diagnostic:
                        self.cleanup_errors.append(diagnostic)

    def check(self, context):
        self._require_idle()
        if self.draft.proposal:
            raise DraftError("Continue or Cancel the unfinished line/circle first.")
        if self.commands.pending_edit is not None:
            raise DraftError("Reopen the dimension and Accept or Cancel its retained text.")
        self._retain_outline()
        self.commands.invalidate_solution()
        self._clear_display_evidence()
        try:
            self._start_job(context, self.commands.solve_request(), "solve")
        except Exception as exc:
            self.error = "Check could not start: " + str(exc)
            self.message = (
                "Unverified sketch. Correct backend settings and Check, or edit the draft."
            )
            if self.alive:
                _tag_redraw(self)
            raise

    def request_finish(self, context):
        self._require_idle()
        if not self.can_finish:
            raise DraftError(
                "Finish needs a current successful Check, a supported profile or open line/arc path, "
                "and no unfinished input."
            )
        raw = self.scene.mechanical_cad.sketch_annotation_json
        document_id = json.loads(self.draft.document_json)["id"]
        lookup = sketch_annotation_store.annotations_for(
            raw, document_id, self.draft.feature_id, self.commands.sketch
        )
        from .reference_dimensions import is_reference

        # Reference and retired entries, including missing targets, were loaded into the UI.
        # Their explicit removal must not be undone by merging old scene metadata.
        annotations = {
            key: conflict.binding
            for key, conflict in lookup.unavailable.items()
            if not is_reference(conflict.binding) and "retirement" not in conflict.binding
        }
        annotations.update(self.draft.annotations)
        layout = sketch_annotation_store.replace_annotations(
            raw, document_id, self.draft.feature_id, annotations
        )
        selection = backend_runtime.capture(context)
        self.publication = part_publication.prepare(
            context,
            self.commands.candidate(),
            self.scene.mechanical_cad.document_path,
            annotation_layout=layout,
            selection=selection,
            owner_token=self.owner_token,
        )
        try:
            self._start_job(
                context,
                self.publication.request,
                "finish",
                selection=self.publication.selection,
                prepared=self.publication.prepared,
            )
        except Exception:
            self.publication.retire()
            self.publication = None
            raise

    def request_driver_accept(self, context):
        self._require_idle()
        if self.commands.pending_edit is None or not self.input_token:
            raise DraftError("Reopen this retained dimension before accepting it.")
        self._clear_display_evidence()
        self._start_job(context, self.commands.solve_request(trial=True), "trial")

    def tick(self, context):
        """Consume exact responses on the main thread; no worker calls the owner."""
        if self.pending is None:
            return
        pending, kind = self.pending, self.pending_kind
        prepared = self.pending_prepared
        request = pending.request_snapshot()
        evidence = None
        try:
            selection = backend_runtime.assert_current(pending.selection, context)
            evidence = sketch_pending.poll(
                pending, self.identity(context, selection), current_selection=selection
            )
            if evidence is None:
                return
            response = general_sketch_draft.read_guarded_operation(
                evidence,
                prepared,
                self._backend_current_selection(),
                owner_token=self.owner_token,
                action=request["action"],
            )
            if sketch_pending._exact_json(request) != sketch_pending._exact_json(
                prepared.operation_request()
            ):
                raise DraftError(
                    "The completed sketch operation differs from its prepared request."
                )
            self.pending = None
            self.pending_kind = ""
            self.pending_prepared = None
            self._require_current()
            if kind in {"remove_fillet_solve", "remove_fillet_replay"}:
                self.complete_fillet_removal(context, evidence, prepared, response, kind=kind)
                return
            if kind in {"diameter_baseline", "diameter_solve"}:
                self.complete_circle_diameter(context, kind, evidence, prepared, response)
                return
            if kind in {"length_baseline", "length_solve"}:
                self.complete_line_length(context, kind, evidence, prepared, response)
                return
            if kind == "finish":
                intent, self.publication = self.publication, None
                if intent is None:
                    raise DraftError("Finish intent was retired; the draft is retained.")
                if not response["ok"]:
                    try:
                        if intent.retain_failed_edit(context, evidence, self.commands.feature_id):
                            try:
                                _discard_stored(self.scene)
                            except Exception:
                                staged_edit_store.discard(context)
                                self.scene.mechanical_cad.sketch_draft_json = self.stored_snapshot
                                raise
                            # The complete candidate and layout now have one
                            # proposal owner; never checkpoint this draft again.
                            self.retained_for_repair = True
                            self.scene.mechanical_cad.last_action_error = (
                                "Unapplied sketch edit retained for repair; accepted model unchanged. "
                                "Use Replace Reference or Review Support in Feature History here. "
                                "Switching workspace discards this live proposal; Save first to preserve intent. "
                                "Cancel closes only the review. Discard Proposed Edit abandons all proposed sketch edits."
                            )
                            self.cleanup()
                            return
                        self._record_build_failure(evidence, prepared, trial=False)
                    finally:
                        intent.retire()
                    return
                if not intent.publish(context, evidence):
                    raise DraftError("The Part publication did not complete.")
                _discard_stored(self.scene)
                self.finished = True
                self.cleanup()
                workspace.request_workspace(context, "PART", on_ready=_focus_display)
                return
            if kind == "downstream":
                if not response["ok"]:
                    self._record_build_failure(evidence, prepared, trial=True)
                    return
                evidence.publication.consume(
                    self._backend_current_selection(),
                    owner_token=self.owner_token,
                    expected_action="replay",
                    expected_result_version=request["result_version"],
                    require_success=True,
                )
                self._accepted_driver(
                    self.trial_evidence,
                    expected_prepared=self.trial_prepared,
                    replay_evidence=evidence,
                    replay_prepared=prepared,
                )
                return
            response = evidence.publication.consume(
                self._backend_current_selection(),
                owner_token=self.owner_token,
                expected_action="solve_sketch",
                expected_result_version=request["result_version"],
            )
            trial = kind == "trial"
            pending_edit = self.commands.pending_edit
            if not self.commands.record_guarded_solution(
                evidence,
                self.commands.revision,
                expected_prepared=prepared,
                expected_input_revision=pending_edit.input_revision
                if trial and pending_edit
                else None,
            ):
                # Expression/transport failures have no native report. Preserve
                # their ordinary error without inventing conflict candidates.
                if response.get("result") is not None:
                    self._failure_diagnostics = (
                        constraint_diagnostics.FailureDiagnostics.from_guarded(
                            evidence,
                            expected_prepared=prepared,
                            current_selection=self._backend_current_selection(),
                            owner_token=self.owner_token,
                            session_id=self.session_id,
                            command_revision=self.commands.revision,
                            input_token=self.input_token,
                            input_revision=pending_edit.input_revision
                            if trial and pending_edit is not None
                            else None,
                        )
                    )
                self.error = response["error"]["message"]
                self.message = "Check failed; all authored input is retained."
                if self.input_controller is not None:
                    self.input_controller.reject_accept()
                return
            if trial:
                if self.commands.consumed_by:
                    self.trial_evidence = evidence
                    self.trial_prepared = prepared
                    selection, tolerance = backend_runtime.configuration(context)
                    general_sketch_draft.read_guarded_operation(
                        evidence,
                        prepared,
                        selection,
                        owner_token=self.owner_token,
                        action="solve_sketch",
                        require_success=True,
                    )
                    self._start_job(
                        context,
                        self.commands.replay_request(
                            trial=True, options={"linear_deflection": tolerance}
                        ),
                        "downstream",
                        selection=selection,
                    )
                else:
                    self._accepted_driver(evidence, expected_prepared=prepared)
            else:
                self.guarded_evidence = evidence
                self.expected_prepared = prepared
                self.evidence_request, self.evidence_response = request, response
                # Snapshot display-only geometry while evidence is current.
                # Settings may revoke it before the first viewport draw.
                self._retain_outline()
                self.message = (
                    "Sketch checked. Finish saves editable geometry and rebuilds dependents."
                )
                self.error = ""
        except Exception as exc:
            if type(evidence) is general_sketch_draft.GuardedEvidence:
                try:
                    evidence.publication.cancel()
                except (ValueError, TypeError, AttributeError):
                    pass
            self.cancel_native("Check stopped; draft retained.")
            self.error = str(exc)
            if self.input_controller is not None:
                self.input_controller.reject_accept()
        finally:
            self.geometry_cache = self.geometry_key = None
            if self.alive:
                _tag_redraw(self)

    def _record_build_failure(self, evidence, prepared, *, trial):
        commands = self.commands
        selected = self._backend_current_selection()
        solve_evidence = commands._trial_evidence if trial else commands._solution_evidence
        solve_prepared = commands._trial_prepared if trial else commands._solution_prepared
        edit = commands.pending_edit
        report = constraint_diagnostics.GuardedBuildFailure.from_guarded(
            solve_evidence,
            solve_prepared,
            evidence,
            prepared,
            current_selection=selected,
            owner_token=self.owner_token,
            session_id=self.session_id,
            command_revision=commands.revision,
            input_token=self.input_token,
            input_revision=edit.input_revision if trial and edit is not None else None,
        )
        evidence.publication.consume(
            selected,
            owner_token=self.owner_token,
            expected_action="replay",
            expected_result_version=prepared.operation_request()["result_version"],
            require_success=False,
        )
        if trial:
            commands.invalidate_solution()
        self.trial_evidence = self.trial_prepared = None
        self._build_failure = report
        snapshot = report.snapshot
        self.error = "; ".join(message for _, _, message in snapshot.failed_features)
        self.message = (
            f"{'Trial solve' if trial else 'Check'} succeeded: {snapshot.remaining_dof} DoF. "
            "Native construction failed; the editable draft is retained."
        )
        if self.input_controller is not None:
            self.input_controller.reject_accept()

    def _accepted_driver(self, evidence, *, expected_prepared, **replay):
        # Keep invalid/raw pending intent until the complete accepted wrapper is
        # serializable and its original scene slot has passed the same CAS.
        if (
            not self.commands.has_verified_trial
            or self.commands._trial_evidence[0] is not evidence
            or self.commands._trial_prepared[0] is not expected_prepared
        ):
            raise DraftError("The original trial solve association was retired or replaced.")
        candidate = draft_dispatch.clone(self.draft)
        commands = candidate.command_draft
        self._bind_commands(commands)
        commands.record_guarded_solution(
            evidence,
            commands.revision,
            expected_prepared=expected_prepared,
            expected_input_revision=commands.pending_edit.input_revision,
        )
        commands.accept_driver(**replay)
        response = None

        def verify_acceptance():
            nonlocal response
            self._require_current()
            if not commands.has_current_solution:
                raise DraftError(
                    "The complete driver evidence chain was revoked during checkpoint."
                )
            response = general_sketch_draft.read_guarded_operation(
                evidence,
                expected_prepared,
                self._backend_current_selection(),
                owner_token=self.owner_token,
                action="solve_sketch",
                require_success=True,
            )

        self.replace_authoring(candidate, postcheck=verify_acceptance)
        self.guarded_evidence = evidence
        self.expected_prepared = expected_prepared
        self.evidence_request = expected_prepared.operation_request()
        self.evidence_response = response
        self._retain_outline()
        self.trial_evidence = None
        self.trial_prepared = None
        self.length_attempt = None
        self.diameter_attempt = None
        self.removal_attempt = None
        self.input_token = ""
        if self.input_controller is not None:
            self.input_controller.close()
        self.message = "Dimension accepted once. Finish updates the Part."
        self.error = ""

    def _display_authored_sketch(self, commands=None):
        """Recompute source-linked construction geometry without rewriting intent."""
        commands = self.commands if commands is None else commands
        sketch = copy.deepcopy(commands.sketch)
        sketch["plane"] = copy.deepcopy(self.display_plane)
        feature = next(
            f for f in commands.candidate()["features"] if f["id"] == commands.feature_id
        )
        if feature.get("projections"):
            result = document_state.current_part_result(self._backend_context)
            if result is None:
                raise DraftError("Rebuild the current Part to resolve its external references.")
            sketch_projection.validate_projection_ownership(sketch, feature["projections"])
            for port, rows in sketch_projection.projection_groups(feature["projections"]).items():
                if sketch_projection.is_solid_projection(rows):
                    edges = self._solid_projection_edges(feature, result, port, rows)
                    if edges is not None:
                        sketch = sketch_projection.project_solid_edges(sketch, edges, rows)
                    # Restored unfinished drafts may have no published target yet.
                    # Their authored seeds are unverified display only; Check freshly
                    # derives the source before Finish can acquire any authority.
                else:
                    source = next(
                        (f for f in result["features"] if f["id"] == feature["inputs"][port]),
                        None,
                    )
                    if source is None or source.get("status") != "ok" or not source.get("sketch"):
                        raise DraftError("The external sketch has no current solved geometry.")
                    sketch = sketch_projection.project_sketch(
                        sketch, source["sketch"]["solved"], rows
                    )
        return sketch

    def _solid_projection_edges(self, feature, result, port, rows):
        binding = getattr(self, "_solid_projection_catalog", None)
        if binding is not None:
            evidence, token, version = binding
            accepted = evidence.revalidate(
                self._backend_current_selection(),
                owner_token=token,
                expected_action="edge_catalog",
                expected_result_version=version,
                require_success=True,
            )["result"]
            if accepted["replay"] != result:
                raise DraftError("Solid projection source changed; rebuild and pick again.")
            required = {tuple(row["faces"]) for row in rows}
            return [
                self._solid_projection_entry(entry)
                for entry in accepted["catalogs"].get(feature["inputs"][port], [])
                if tuple(entry["faces"]) in required
            ]
        current = self.current_solution_response()
        if current is not None:
            edges = (current["result"].get("support_context") or {}).get("projection_edges")
            if edges is not None:
                return (
                    edges.get(port)
                    if type(edges) is dict
                    else edges
                    if port == "external"
                    else None
                )
        row = next((f for f in result["features"] if f["id"] == feature["id"]), None)
        if (
            row is not None
            and row.get("status") == "ok"
            and row.get("inputs", {}).get(port) == feature["inputs"][port]
            and "projection_edges" in row
        ):
            required = {tuple(r["faces"]) for r in rows}
            groups = row["projection_edges"]
            evidence = (
                groups.get(port) if type(groups) is dict else groups if port == "external" else None
            )
            if evidence is not None:
                edges = [e for e in evidence if tuple(e["faces"]) in required]
                if {tuple(e["faces"]) for e in edges} == required:
                    return edges
        return None

    @staticmethod
    def _solid_projection_entry(entry):
        """Keep native analytic evidence separate from display tessellation."""
        if "arc" in entry:
            return {"kind": "arc", "faces": entry["faces"], **entry["arc"]}
        if "circle" in entry:
            return {"kind": "circle", "faces": entry["faces"], **entry["circle"]}
        if len(entry["points"]) == 2 and "endpoint_faces" in entry:
            return {key: entry[key] for key in ("faces", "endpoint_faces", "points")}
        raise DraftError("The referenced edge is no longer a supported straight edge or circle.")

    def project_solid_edge(
        self, context, source_id, faces, endpoint_faces, evidence, token, version
    ):
        self.require_gesture_context(context)
        self._require_idle()
        if self.draft.proposal is not None or self.commands.pending_edit is not None:
            raise DraftError("Finish or cancel sketch input before using a solid edge.")
        accepted = evidence.revalidate(
            self._backend_current_selection(),
            owner_token=token,
            expected_action="edge_catalog",
            expected_result_version=version,
            require_success=True,
        )["result"]
        result = document_state.current_part_result(context)
        if result is None or accepted["replay"] != result:
            raise DraftError("The source Part changed; rebuild and pick again.")
        matches = [
            entry
            for entry in accepted["catalogs"].get(source_id, [])
            if entry["faces"] == list(faces)
        ]
        if len(matches) != 1:
            raise DraftError("Use one exact edge with a unique stable face pair.")
        entry = self._solid_projection_entry(matches[0])
        is_circle = entry.get("kind") == "circle"
        is_arc = entry.get("kind") == "arc"
        if not is_circle and (entry["endpoint_faces"] != endpoint_faces or endpoint_faces is None):
            raise DraftError("Edge endpoints lack current stable identity; pick another edge.")
        # Seeds are exact projected pick coordinates, not a new source authority.
        # The shared projection helper validates circle normals before publication.
        plane = self.display_plane
        inverse = [plane["quaternion"][0], *(-v for v in plane["quaternion"][1:])]
        points = [
            sketch_projection._rotate(inverse, [point[i] - plane["origin"][i] for i in range(3)])[
                :2
            ]
            for point in ([entry["center"]] if is_circle else
                          [entry["center"], *entry["points"]] if is_arc else entry["points"])
        ]
        command = AddProjectionGeometry(
            "circle" if is_circle else "arc" if is_arc else "line",
            tuple(PointSeed(*point) for point in points),
            entry["radius"] if is_circle else 1,
            "ccw" if not is_arc or entry["sweep"] * sketch_projection._rotate(inverse, entry["normal"])[2] > 0 else "cw",
        )
        candidate = (self.draft.promote_arc_capability()
                     if is_arc and self.draft.ui_version != 2 else draft_dispatch.clone(self.draft))
        if is_arc:
            outcome = candidate.command_draft.project_solid_arc(source_id, faces, endpoint_faces, command)
        elif is_circle:
            outcome = candidate.command_draft.project_solid_circle(source_id, faces, command)
        else:
            outcome = candidate.command_draft.project_solid_edge(
                source_id, faces, endpoint_faces, command
            )
        old = getattr(self, "_solid_projection_catalog", None)
        self._solid_projection_catalog = (evidence, token, version)
        try:
            self._display_authored_sketch(candidate.command_draft)
            operation_contracts.validate_authoring_candidate(candidate.command_draft.candidate())
            self.replace_authoring(candidate)
        except Exception:
            self._solid_projection_catalog = old
            raise
        self._check_authored_change(context)
        return outcome

    def project_external(self, context, source_id, source_entity):
        self.require_gesture_context(context)
        self._require_idle()
        if self.draft.proposal is not None or self.commands.pending_edit is not None:
            raise DraftError(
                "Finish or cancel the current sketch input before projecting geometry."
            )
        result = document_state.current_part_result(context)
        source = next((f for f in (result or {}).get("features", []) if f["id"] == source_id), None)
        if source is None or source.get("status") != "ok" or not source.get("sketch"):
            raise DraftError("Choose a current solved source sketch.")
        solved = source["sketch"]["solved"]
        kind = next(
            (
                kind
                for kind, collection in (("line", "lines"), ("circle", "circles"))
                if any(e["id"] == source_entity for e in solved.get(collection, []))
            ),
            None,
        )
        if kind is None:
            raise DraftError("Choose one exact source line or circle.")
        command = AddProjectionGeometry(
            kind, (PointSeed(0, 0), PointSeed(1, 0)) if kind == "line" else (PointSeed(0, 0),), 1
        )
        candidate = draft_dispatch.clone(self.draft)
        outcome = candidate.command_draft.project_external(source_id, source_entity, command)
        self._display_authored_sketch(
            candidate.command_draft
        )  # Validate projection before publishing intent.
        operation_contracts.validate_authoring_candidate(candidate.command_draft.candidate())
        self.replace_authoring(candidate)
        self._check_authored_change(context)
        return outcome

    def geometry(self):
        current = self.current_solution_response() is not None
        retained = (
            not current
            and self.retained_outline is not None
            and self.retained_revision == self.commands.revision
        )
        key = (self.commands.revision, current, retained, self.commands.pending_edit is not None)
        if key != self.geometry_key:
            self.geometry_cache = (
                self.retained_outline
                if retained
                else (
                    general_view_geometry.build_guarded_geometry(
                        self.commands.sketch,
                        self.guarded_evidence,
                        expected_prepared=self.expected_prepared,
                        current_selection=self._backend_current_selection(),
                        owner_token=self.owner_token,
                    )
                    if current
                    else general_view_geometry.build_geometry(
                        self._display_authored_sketch(), source="authored"
                    )
                )
            )
            if self.geometry_cache.source == "authored":
                self.geometry_cache = replace(
                    self.geometry_cache,
                    plane=general_view_geometry.Workplane.from_saved(self.display_plane),
                )
            self.geometry_key = key
        return self.geometry_cache

    @settled_transaction
    def replace_authoring(self, replacement, *, postcheck=None, cancelled_input=False):
        """Publish prepared pure intent only after full serializability/CAS checks."""
        if cancelled_input:
            # Cancelling our detached native job may retain the global lease
            # until process cleanup. Raw/proposal cancellation must still work;
            # this exception cannot add a command, change IDs or touch the Part.
            self._require_current()
            if (
                self.pending is not None
                or self.draft.proposal is None
                or replacement.pending_length is not None
                or replacement.pending_diameter is not None
                or replacement.command_draft.checkpoint_payload() != self.commands.checkpoint_payload()
            ):
                raise DraftError("Only unchanged-command input cancellation may bypass cleanup.")
            expected_cancel = draft_dispatch.clone(self.draft)
            if replacement.proposal is None:
                expected_cancel.cancel_proposal()
            elif self.draft.pending_diameter is not None:
                expected_cancel.cancel_pending_diameter()
            else:
                expected_cancel.cancel_pending_length()
            if draft_dispatch.dumps(expected_cancel) != draft_dispatch.dumps(replacement):
                raise DraftError("Input cancellation cannot change unrelated authoring intent.")
        else:
            self._require_idle()
        serialized = draft_dispatch.dumps(replacement)
        annotation_history = self._retained_annotation_history(replacement.command_draft)
        if replacement.command_draft not in self._bound_commands:
            self._bind_commands(replacement.command_draft)
        old = self.draft
        old_snapshot = self.stored_snapshot
        self.draft = replacement
        try:
            self.checkpoint()
            if postcheck is not None:
                postcheck()
        except Exception as exc:
            self.draft = old
            # Roll back only the slot written by this exact attempt. An external
            # replacement belongs to its writer and must remain recoverable.
            try:
                state = self.scene.mechanical_cad
                if state.sketch_draft_json == serialized:
                    state.sketch_draft_json = old_snapshot
                self.stored_snapshot = old_snapshot
            except Exception as rollback:
                raise DraftError(
                    f"Draft acceptance failed: {exc}; saved-slot recovery failed: {rollback}"
                ) from exc
            raise
        self._clear_display_evidence()
        self.retained_outline = self.retained_revision = None
        self._history_annotations = annotation_history
        self.error = ""
        return serialized

    def _check_authored_change(self, context):
        """A saved local command survives an automatic Check-start failure.

        Acceptance of reversible authoring intent and successful native solve
        are separate outcomes. Never return a cancelled action after its journal
        and checkpoint already committed, or leave an earlier success caption.
        """
        try:
            self.check(context)
            return True
        except Exception as exc:
            cleanup_error = ""
            if self.pending is not None:
                try:
                    self.cancel_native("Check startup failed; authored draft retained.")
                except Exception as cleanup:
                    cleanup_error = "; cleanup: " + str(cleanup)
            self._clear_display_evidence()
            self.error = "Draft change retained. Check could not start: " + str(exc) + cleanup_error
            self.message = (
                "Unverified draft change. Correct backend settings and Check, or Undo sketch."
            )
            if self.alive:
                _tag_redraw(self)
            return False

    def _replace_ui_intent(self, candidate, *, postcheck=None, cancelled_input=False):
        """Retain the whole original solve chain across geometry-neutral clones."""
        self._bind_commands(candidate.command_draft)
        current = self.current_solution_response() is not None
        association = (
            self.guarded_evidence,
            self.expected_prepared,
            self.evidence_request,
            self.evidence_response,
        )
        if current:
            candidate.command_draft.transfer_guarded_solution(self.commands)
        self.replace_authoring(candidate, postcheck=postcheck, cancelled_input=cancelled_input)
        if current and candidate.command_draft.has_current_solution:
            (
                self.guarded_evidence,
                self.expected_prepared,
                self.evidence_request,
                self.evidence_response,
            ) = association

    def require_gesture_context(self, context):
        """Point gestures belong to the caller's original viewport and view layer."""
        if (
            context.window != self.window
            or context.scene != self.scene
            or context.area != self.area
            or context.workspace != self.workspace
            or context.view_layer != self.window.view_layer
        ):
            self.gesture_intent = None
            self.proposal_capture = False
            raise DraftError("Use the original sketch viewport for this gesture.")
        self._require_current()

    def prepare_gesture(self, kind):
        """Capture one explicit dialog, pausing pointer input without saving it."""
        tool = {"arc": "Arc", "point": "UsePoint", "reverse": "Reverse", "fillet": "CornerFillet", "remove_fillet": "RemoveFillet"}.get(kind)
        self._require_idle()
        if tool is None or not self.can_use_tool(tool):
            raise DraftError("This gesture action is unavailable; resolve the current input first.")
        selected = self._backend_current_selection()
        # Do not restore prior capture on Cancel, acceptance, or a stale dialog.
        # A retained or resumed proposal needs an explicit Continue for the pointer.
        self.proposal_capture = False
        points = tuple(item["id"] for item in self.commands.sketch["points"])
        if kind == "point" and not 0 < len(points) <= 256:
            raise DraftError("The exact-point picker supports between 1 and 256 points.")
        binding = _GestureIntent(
            kind,
            self.owner_token,
            self.draft,
            self.commands,
            draft_dispatch.dumps(self.draft),
            self.stored_snapshot,
            sketch_pending._exact_json(self.identity(self._backend_context, selected)),
            selected,
            self.draft.point_input_phase,
            self.proposal_capture,
            points,
            _point_picker_catalog(self.commands.sketch, points) if kind == "point" else None,
        )
        self.gesture_intent = binding
        return binding

    def point_picker_catalog(self, token, context=None):
        """Read only the original gesture's display data, never current geometry.

        RNA callbacks receive OperatorProperties, not the Python operator. The
        transient token bridges presentation only; execution still needs the
        original binding object and every existing one-use acceptance guard.
        """
        if context is None:
            return None
        binding = self.gesture_intent
        if (
            not self.alive
            or type(token) is not str
            or type(binding) is not _GestureIntent
            or binding.kind != "point"
            or binding.owner_token is not self.owner_token
            or binding.draft is not self.draft
            or binding.commands is not self.commands
            or binding.point_catalog is None
            or token != binding.point_catalog.token
        ):
            return None
        if (
            context.window != self.window
            or context.scene != self.scene
            or context.area != self.area
            or context.workspace != self.workspace
            or context.view_layer != self.window.view_layer
        ):
            return None
        return binding.point_catalog

    def cancel_gesture(self, binding):
        if self.gesture_intent is binding:
            self.corner_fillet_preview = None
            self.gesture_intent = None
            self.proposal_capture = False

    def _accept_gesture(self, binding, kind):
        """Recheck every captured binding once, and retire before applying intent."""
        if type(binding) is not _GestureIntent or self.gesture_intent is not binding:
            raise DraftError("This gesture confirmation is no longer active; reopen it.")
        self.gesture_intent = None
        capture, self.proposal_capture = self.proposal_capture, False
        self._require_idle()
        selected = self._backend_current_selection()
        if (
            binding.kind != kind
            or binding.owner_token is not self.owner_token
            or binding.draft is not self.draft
            or binding.commands is not self.commands
            or binding.snapshot != draft_dispatch.dumps(self.draft)
            or binding.saved_slot != self.stored_snapshot
            or binding.selection != selected
            or binding.identity
            != sketch_pending._exact_json(self.identity(self._backend_context, selected))
            or binding.phase != self.draft.point_input_phase
            or binding.capture != capture
        ):
            raise DraftError(
                "The sketch, input phase, viewport or backend changed; reopen this action."
            )
        return binding

    def _input_environment(self):
        selected = self._backend_current_selection()
        identity = self.identity(self._backend_context, selected)
        identity.pop("intent")
        identity.pop("saved_slot")
        return selected, sketch_pending._exact_json(identity)

    def _require_input_environment(self, captured):
        if self._input_environment() != captured:
            self.gesture_intent = None
            self.proposal_capture = False
            raise DraftError("The sketch context or backend changed during checkpoint; retry.")

    def enable_arc(self, binding):
        self._accept_gesture(binding, "arc")
        captured = self._input_environment()
        if not self.can_use_tool("Arc"):
            raise DraftError(
                "The sketch curve limit has been reached, or another input is unfinished."
            )
        candidate = self.draft.promote_arc_capability()
        candidate.select_tool("Arc")
        self._replace_ui_intent(
            candidate, postcheck=lambda: self._require_input_environment(captured)
        )
        self.message = (
            "Center Arc: choose center, start and end. Observations stay unsolved until Check."
        )

    def accept_point_input(
        self,
        context,
        point,
        *,
        expected_phase,
        source_kind=None,
        source_id=None,
        role=None,
        picker=None,
        axis=None,
    ):
        """The sole Line/Arc point path for pointer input and exact-ID dialogs."""
        self.require_gesture_context(context)
        if picker is not None:
            binding = self._accept_gesture(picker, "point")
            if type(point) is not PointRef or point.id not in binding.points:
                raise DraftError("Choose an exact point from this picker.")
        else:
            self._require_idle()
            if self.gesture_intent is not None:
                raise DraftError("Resolve the open gesture dialog first.")
            if self.draft.proposal is not None and not self.proposal_capture:
                raise DraftError(
                    "This retained proposal is not capturing input. Choose Continue or Use existing point."
                )
        tool = "Arc" if expected_phase and expected_phase[0] == "arc" else "Line"
        if self.draft.proposal is None and not self.can_use_tool(tool):
            raise DraftError("This sketch is outside the bounded drawing-tool scope.")
        if axis is not None:
            from .line_axis import anchor_position, point_position, require_axis

            if expected_phase != ("line", "end") or self.draft.point_input_phase != expected_phase:
                raise DraftError("Axis lock needs the current Line endpoint.")
            points = self.geometry().points
            require_axis(anchor_position(self.draft.proposal, points), point_position(point, points), axis)
        captured = self._input_environment()
        try:
            prepared = general_proposals.prepare_point_input(
                self.draft,
                point,
                expected_phase=expected_phase,
                source_kind=source_kind,
                source_id=source_id,
                role=role,
                axis=axis,
            )
        except DraftError:
            # An explicit pointer choice remains the rejected observation, never
            # a projected replacement or accepted role. A stale/invalid picker
            # instead leaves its original intent byte-exact.
            if (
                picker is None
                and expected_phase == self.draft.point_input_phase
                and expected_phase in {("arc", "start"), ("arc", "end")}
            ):
                observed = draft_dispatch.clone(self.draft)
                observed.observe_arc(point)
                self._replace_ui_intent(
                    observed, postcheck=lambda: self._require_input_environment(captured)
                )
            raise
        replacement = prepared.replacement(self.draft)
        terminal = bool(prepared.entity_ids)
        if terminal:
            # The existing candidate validator is the authoritative replay graph
            # barrier. No capability promotion can admit an incompatible Part.
            operation_contracts.validate_authoring_candidate(replacement.command_draft.candidate())
            self.replace_authoring(
                replacement, postcheck=lambda: self._require_input_environment(captured)
            )
            self.proposal_capture = False
            self._check_authored_change(context)
        else:
            self._replace_ui_intent(
                replacement, postcheck=lambda: self._require_input_environment(captured)
            )
            self.proposal_capture = picker is None
            phase = self.draft.point_input_phase[1]
            self.message = f"Choose the {phase} point" + (
                " with Use existing point, or Continue pointer input."
                if picker is not None
                else "."
            )
        return prepared.entity_ids

    def reverse_arc(self, context, binding):
        self.require_gesture_context(context)
        self._accept_gesture(binding, "reverse")
        if not self.can_use_tool("Reverse"):
            raise DraftError("Select one available arc, or continue its unfinished proposal.")
        if self.draft.proposal is not None:
            captured = self._input_environment()
            candidate = draft_dispatch.clone(self.draft)
            candidate.reverse_arc_proposal()
            self._replace_ui_intent(
                candidate, postcheck=lambda: self._require_input_environment(captured)
            )
            self.message = "Proposal direction reversed. Use Continue or an exact point to finish."
        else:
            self.execute(context, ReverseArcSweep(self.draft.selection[0]["id"]))
            self.message = "Arc sweep reversed; endpoint roles are unchanged. The complementary sector may have a different area."

    def accept_proposal(self, context, endpoint=None):
        self._require_idle()
        prepared = general_proposals.prepare_proposal(self.draft, endpoint=endpoint)
        self.replace_authoring(prepared.replacement(self.draft))
        self.proposal_capture = False
        self._check_authored_change(context)
        return prepared.entity_ids

    def _clear_removed_relation_selection(self, candidate):
        before = {item["id"] for item in self.commands.sketch["constraints"]}
        after = {item["id"] for item in candidate.command_draft.sketch["constraints"]}
        removed = before - after
        # Only this transaction's proven removals: imported unknown bindings
        # remain visible diagnostics rather than being silently discarded.
        for identifier in removed & candidate.annotations.keys():
            candidate.remove_annotation(identifier)
        candidate.discard_selection(
            tuple(
                (item["kind"], item["id"])
                for item in candidate.selection
                if item["kind"] == "constraint" and item["id"] in removed
            )
        )

    def begin_point_drag(self, point_id, screen, pointer):
        """Capture only transient intent. No geometry or checkpoint changes on press."""
        self._require_idle()
        if self.commands.pending_edit is not None or self.draft.proposal:
            raise DraftError("Finish or cancel the current input before dragging a point.")
        point = self.geometry().points.get(point_id)
        if point is None:
            raise DraftError("This point is no longer available.")
        self.point_drag = {
            "commands": self.commands,
            "revision": self.commands.revision,
            "point_id": point_id,
            "screen": tuple(screen),
            "pointer": tuple(pointer),
            "start": tuple(point),
            "target": tuple(point),
            "moved": False,
        }
        self.message = "Drag point; release to solve with existing constraints. Esc cancels."

    def update_point_drag(self, screen, pointer):
        drag = self.point_drag
        if drag is None:
            return
        if drag["commands"] is not self.commands or drag["revision"] != self.commands.revision:
            self.cancel_point_drag()
            raise DraftError("Sketch changed; drag the point again.")
        if sum((a - b) ** 2 for a, b in zip(screen, drag["screen"], strict=True)) >= 16:
            drag["moved"] = True
        if drag["moved"]:
            drag["target"] = tuple(
                origin + value - anchor
                for origin, value, anchor in zip(
                    drag["start"], pointer, drag["pointer"], strict=True
                )
            )

    def cancel_point_drag(self):
        self.point_drag = None
        self.message = "Point drag cancelled; geometry unchanged."

    def finish_point_drag(self, context):
        drag, self.point_drag = self.point_drag, None
        if drag is None or not drag["moved"] or drag["target"] == drag["start"]:
            return
        if drag["commands"] is not self.commands or drag["revision"] != self.commands.revision:
            raise DraftError("Sketch changed; drag the point again.")
        return self.execute(
            context, MovePoint(drag["point_id"], drag["target"], preserve_constraints=True)
        )

    def execute(self, context, command, *, annotation_offset=None, dimension_position=None):
        self._require_idle()
        if isinstance(command, RemoveCornerFillet):
            raise DraftError("Use the guarded Remove Sketch Fillet review to preserve current placement.")
        candidate = (self.draft.promote_arc_capability()
                     if isinstance(command, CornerFillet) and self.draft.ui_version != 2
                     else draft_dispatch.clone(self.draft))
        self._bind_commands(candidate.command_draft)
        if self.current_solution_response() is not None:
            candidate.command_draft.transfer_guarded_solution(self.commands)
        outcome = candidate.command_draft.execute(command)
        if not outcome.changed and annotation_offset is None:
            # An exact duplicate relation is already represented by its existing
            # stable ID. Keep the original owner, checkpoint and solve authority;
            # do not turn a no-op into a new native request or a history change.
            return outcome
        if isinstance(command, CornerFillet) and annotation_offset is None:
            candidate.place_annotation(outcome.constraint_id, (0.0, -max(8.0, command.radius * 2)))
        if annotation_offset is not None:
            candidate.place_annotation(outcome.constraint_id, annotation_offset)
        self._clear_removed_relation_selection(candidate)
        self.replace_authoring(candidate)
        if dimension_position is not None:
            # Capture typing synchronously in the placement event, not from an
            # asynchronous completion callback that could steal a later focus.
            # The normal Enter trial validates the new relation and exact value
            # together. Esc retains the authored relation for Check or Undo.
            self.open_dimension_field(outcome.constraint_id, dimension_position, select_all=True)
        else:
            self._check_authored_change(context)
        return outcome

    @staticmethod
    def _annotation_history_key(commands, entry):
        # Sequence alone is not identity: Undo followed by another command may
        # reuse that position. Bind the full exact entry and original document.
        payload = [commands.base_hash, commands.feature_id, entry]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _retained_annotation_history(self, commands):
        entries = commands.checkpoint_payload()["journal"]["entries"]
        retained = {self._annotation_history_key(commands, entry) for entry in entries}
        return {
            key: value
            for key, value in getattr(self, "_history_annotations", {}).items()
            if key in retained
        }

    def local_history(self, context, *, redo=False):
        self._require_idle()
        candidate = draft_dispatch.clone(self.draft)
        journal = self.commands.checkpoint_payload()["journal"]
        index = journal["cursor"] if redo else journal["cursor"] - 1
        # Let the draft own empty-history errors before selecting any cache key.
        (candidate.command_draft.redo if redo else candidate.command_draft.undo)()
        key = self._annotation_history_key(self.commands, journal["entries"][index])
        cache = self._retained_annotation_history(candidate.command_draft)
        if redo:
            relations = {item["id"]: item for item in candidate.command_draft.sketch["constraints"]}
            for identifier, binding in cache.pop(key, {}).items():
                relation = relations.get(identifier)
                if (
                    identifier not in candidate.annotations
                    and relation is not None
                    and relation["kind"] == binding["kind"]
                    and relation["refs"] == binding["refs"]
                ):
                    candidate.place_annotation(identifier, binding["offset"], display=binding["display"])
        else:
            before = {item["id"]: item for item in self.commands.sketch["constraints"]}
            after = {item["id"] for item in candidate.command_draft.sketch["constraints"]}
            removed = {
                identifier: binding
                for identifier, binding in self.draft.annotations.items()
                if identifier in before
                and identifier not in after
                and before[identifier]["kind"] == binding["kind"]
                and before[identifier]["refs"] == binding["refs"]
            }
            if removed:
                cache[key] = removed
        if journal["entries"][index]["command"]["op"] == "remove_corner_fillet":
            if redo:
                from .sketch_remove_fillet import retain_removal_ui

                retain_removal_ui(candidate, journal["entries"][index]["command"])
            else:
                from .sketch_remove_fillet import restore_removal_ui

                restore_removal_ui(candidate, journal["entries"][index]["command"])
        else:
            self._clear_removed_relation_selection(candidate)
        self.replace_authoring(candidate)
        # Commit the transient cache only after the authoring/checkpoint succeeds.
        self._history_annotations = cache
        self._check_authored_change(context)

    def begin_dimension(self, constraint_id):
        self._require_idle()
        if self.draft.proposal:
            raise DraftError("Finish or Cancel the unfinished proposal first.")
        if self.commands.pending_edit is None:
            self._retain_outline()
            self.commands.begin_edit(constraint_id)
        elif self.commands.pending_edit.constraint_id != constraint_id:
            raise DraftError("Resolve the other retained dimension first.")
        self.input_token = uuid.uuid4().hex
        self._clear_display_evidence()
        self.checkpoint()
        return self.commands.pending_edit.raw_text

    def open_dimension_field(self, constraint_id, position, *, select_all=False):
        raw = self.begin_dimension(constraint_id)
        lease = dimension_input.EditLease(
            self.session_id, constraint_id, self.commands.revision, int(self.input_token[:12], 16)
        )
        self.input_controller = dimension_input.DimensionInput(
            raw, lease=lease, select_all=select_all
        )
        self.field_position = position
        self.field_layout = None
        self.field_drag = False
        self.error = ""
        self.message = "Type a value, unit literal or formula · Enter accepts · Esc cancels."

    def update_raw(self, raw):
        if self.draft.pending_diameter is not None:
            return self.update_circle_diameter_raw(raw)
        if self.draft.pending_length is not None:
            return self.update_line_length_raw(raw)
        self._require_idle()
        self.commands.update_edit(raw)
        self._clear_display_evidence()

    def cancel_dimension(self):
        if self.draft.pending_diameter is not None:
            return self.cancel_circle_diameter()
        if self.draft.pending_length is not None:
            return self.cancel_line_length()
        self.cancel_native()
        self._require_current()
        self.commands.cancel_edit()
        self.input_token = ""
        if self.input_controller is not None:
            self.input_controller.close()
        self._clear_display_evidence()
        self.checkpoint()
        self.error = ""
        self.message = (
            "Dimension edit cancelled; accepted outline retained. Check to verify it again."
        )
