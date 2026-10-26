"""Pending Line length owner path, separate from editing an accepted driver.

Every candidate is detached until baseline and candidate solve are freshly
guarded. Full downstream replay remains the existing Finish publication gate.
Raw checkpoints contain none of these capabilities.
"""

import math
import uuid
from dataclasses import dataclass, replace

from . import dimension_input, draft_dispatch, operation_contracts
from .general_sketch_commands import DraftError, _require
from .general_sketch_draft import read_guarded_operation


@dataclass(frozen=True)
class LengthAttempt:
    source: str
    candidate: str
    token: str
    baseline: tuple | None = None
    solved: tuple | None = None


def _points(solved):
    return {p["id"]: (p["u"], p["v"]) for p in solved["points"]}


def _same_points(actual, expected):
    for identifier, position in expected.items():
        _require(
            identifier in actual and math.dist(actual[identifier], position) <= 1e-7,
            "This length would move an existing point or the captured placement. "
            "Cancel the field and place a new endpoint, or use Dimension after creation.",
        )


class LineLengthSession:
    """Mixin using the existing scene owner, checkpoint CAS and job supervisor."""

    def open_line_length(self, context, endpoint=None, position=(100, 100), *, axis=None):
        self.require_gesture_context(context)
        self._require_idle()
        if self.draft.pending_length is None:
            _require(self.proposal_capture, "Continue the Line before entering its length.")
            candidate = draft_dispatch.clone(self.draft)
            candidate.begin_pending_length(endpoint, self.geometry().points, axis=axis)
            captured = self._input_environment()
            self._replace_ui_intent(
                candidate, postcheck=lambda: self._require_input_environment(captured)
            )
        self.proposal_capture = False
        self.input_token = uuid.uuid4().hex
        self.length_attempt = None
        pending = self.draft.pending_length
        self.input_controller = dimension_input.DimensionInput(
            pending["raw_text"],
            lease=dimension_input.EditLease(
                self.session_id,
                "pending_line_length",
                pending["input_revision"],
                int(self.input_token[:12], 16),
            ),
            select_all=True,
        )
        self.field_position = position
        self.field_layout = None
        self.field_drag = False
        self.error = ""
        axis_label = "" if pending["axis"] is None else f" · {pending['axis'].title()} retained"
        self.message = (
            "Driving length: number or unit literal · Enter creates · Esc returns to Line"
            + axis_label
        )

    def update_line_length_raw(self, raw):
        self._require_idle()
        candidate = draft_dispatch.clone(self.draft)
        candidate.update_pending_length(raw)
        captured = self._input_environment()
        self._replace_ui_intent(
            candidate, postcheck=lambda: self._require_input_environment(captured)
        )

    def cancel_line_length(self):
        self.cancel_native()
        self._require_current()
        candidate = draft_dispatch.clone(self.draft)
        candidate.cancel_pending_length()
        self._replace_ui_intent(candidate, cancelled_input=True)
        self.input_token = ""
        if self.input_controller is not None:
            self.input_controller.close()
        self.proposal_capture = False
        self.error = ""
        self.message = "Length cancelled; original Line retained. Continue to place its endpoint."

    def cancel_line_proposal(self):
        self.cancel_native()
        self._require_current()
        candidate = draft_dispatch.clone(self.draft)
        candidate.cancel_proposal()
        self._replace_ui_intent(candidate, cancelled_input=True)
        self.input_token = ""
        if self.input_controller is not None:
            self.input_controller.close()
        self.proposal_capture = False

    def request_line_length_accept(self, context):
        from .pending_line_length import prepare_length_candidate

        self._require_idle()
        _require(
            self.draft.pending_length is not None
            and self.input_token
            and self.input_controller is not None
            and not self.input_controller.closed,
            "Reopen Driving length before accepting the retained input.",
        )
        _require(
            self.input_controller.raw == self.draft.pending_length["raw_text"]
            and self.input_controller.lease.owner_id == self.session_id
            and self.input_controller.lease.field_id == "pending_line_length"
            and self.input_controller.lease.token == int(self.input_token[:12], 16),
            "Driving length text lease changed; reopen the field.",
        )
        _require(
            getattr(self, "length_attempt", None) is None, "This length is already being checked."
        )
        candidate, _receipt = prepare_length_candidate(self.draft)
        operation_contracts.validate_authoring_candidate(candidate.command_draft.candidate())
        attempt = LengthAttempt(
            draft_dispatch.dumps(self.draft), draft_dispatch.dumps(candidate), self.input_token
        )
        self.length_attempt = attempt
        try:
            if self.commands.sketch["points"]:
                self._start_job(context, self.commands.solve_request(), "length_baseline")
            else:
                self._start_job(context, candidate.command_draft.solve_request(), "length_solve")
        except Exception:
            self.length_attempt = None
            raise
        self.message = "Checking driving length; nothing is added until validation succeeds."

    def _length_current(self):
        attempt = getattr(self, "length_attempt", None)
        _require(
            attempt is not None
            and attempt.token == self.input_token
            and attempt.source == draft_dispatch.dumps(self.draft)
            and self.draft.pending_length is not None,
            "Driving length input changed; reopen it and retry.",
        )
        return attempt

    def _length_read(self, pair, action="solve_sketch"):
        return read_guarded_operation(
            pair[0],
            pair[1],
            self._backend_current_selection(),
            owner_token=self.owner_token,
            action=action,
            require_success=True,
        )

    def _length_expected_points(self, attempt, candidate):
        pending = self.draft.pending_length
        before = (
            {}
            if attempt.baseline is None
            else _points(self._length_read(attempt.baseline)["result"]["sketch"]["solved"])
        )
        # Captured positions are intent only. A fresh baseline must agree for
        # reused points; resumed raw input never supplies native proof.
        original = pending["original_proposal"]["anchor"]
        captured = {}
        if original["kind"] == "existing":
            captured[original["point_id"]] = pending["anchor_position"]
        if pending["endpoint"]["kind"] == "existing":
            captured[pending["endpoint"]["point_id"]] = pending["endpoint_position"]
        _same_points(before, captured)
        expected = dict(before)
        original_ids = {p["id"] for p in self.commands.sketch["points"]}
        expected.update(
            {
                p["id"]: (p["u"], p["v"])
                for p in candidate.command_draft.sketch["points"]
                if p["id"] not in original_ids
            }
        )
        return expected

    def complete_line_length(self, context, kind, evidence, prepared, response):
        """Called only after the ordinary pending-owner poll/CAS has completed."""
        attempt = self._length_current()
        if not response["ok"]:
            raise DraftError(response["error"]["message"])
        evidence.publication.consume(
            self._backend_current_selection(),
            owner_token=self.owner_token,
            expected_action="solve_sketch",
            expected_result_version=prepared.operation_request()["result_version"],
            require_success=True,
        )
        candidate = draft_dispatch.restore(attempt.candidate, self.draft.document_json)
        if kind == "length_baseline":
            attempt = replace(attempt, baseline=(evidence, prepared))
            self._length_expected_points(attempt, candidate)
            self.length_attempt = attempt
            self._start_job(context, candidate.command_draft.solve_request(), "length_solve")
            return
        expected = self._length_expected_points(attempt, candidate)
        _require(kind == "length_solve", "Unexpected Line-length completion.")
        _same_points(_points(response["result"]["sketch"]["solved"]), expected)
        attempt = replace(attempt, solved=(evidence, prepared))
        self.length_attempt = attempt
        _require(attempt.solved is not None, "Driving length solve evidence was retired.")
        solve_response = self._length_read(attempt.solved)
        _same_points(_points(solve_response["result"]["sketch"]["solved"]), expected)
        commands = candidate.command_draft
        self._bind_commands(commands)
        _require(
            commands.record_guarded_solution(
                attempt.solved[0], commands.revision, expected_prepared=attempt.solved[1]
            ),
            "Driving length needs a successful native solve.",
        )
        environment = self._input_environment()
        self._length_current()

        def postcheck():
            self._require_input_environment(environment)
            _require(self.input_token == attempt.token, "The length input lease was retired.")
            _require(
                draft_dispatch.dumps(self.draft) == attempt.candidate,
                "The length candidate changed.",
            )
            if attempt.baseline is not None:
                self._length_read(attempt.baseline)
            _require(commands.has_current_solution, "Driving length evidence was revoked.")
            self._length_read(attempt.solved)

        self.replace_authoring(candidate, postcheck=postcheck)
        self.guarded_evidence, self.expected_prepared = attempt.solved
        self.evidence_request = self.expected_prepared.operation_request()
        self.evidence_response = solve_response
        self._retain_outline()
        self.length_attempt = None
        self.input_token = ""
        self.input_controller.close()
        self.proposal_capture = False
        self.error = ""
        self.message = (
            "Line and driving length created together. Finish validates and updates the Part."
        )
