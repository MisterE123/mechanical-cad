"""Pending Circle diameter owner path, separate from editing an accepted driver.

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
class DiameterAttempt:
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
            "This diameter would move an existing point or the captured placement. "
            "Cancel the field and place a new center, or use Dimension after creation.",
        )


def _radii(solved):
    return {circle["id"]: circle["radius"] for circle in solved.get("circles", [])}


def _same_radii(actual, expected):
    _require(set(actual) == set(expected), "Circle identities changed during diameter validation.")
    for identifier, radius in expected.items():
        _require(
            math.isfinite(actual[identifier]) and abs(actual[identifier] - radius) <= 1e-7,
            "This diameter would change an existing circle or the requested diameter.",
        )


class CircleDiameterSession:
    """Mixin using the existing scene owner, checkpoint CAS and job supervisor."""

    def open_circle_diameter(self, context, position=(100, 100)):
        self.require_gesture_context(context)
        self._require_idle()
        if self.draft.pending_diameter is None:
            _require(self.proposal_capture, "Continue the Circle before entering its diameter.")
            candidate = draft_dispatch.clone(self.draft)
            candidate.begin_pending_diameter(self.geometry().points)
            captured = self._input_environment()
            self._replace_ui_intent(
                candidate, postcheck=lambda: self._require_input_environment(captured)
            )
        self.proposal_capture = False
        self.input_token = uuid.uuid4().hex
        self.diameter_attempt = None
        pending = self.draft.pending_diameter
        self.input_controller = dimension_input.DimensionInput(
            pending["raw_text"],
            lease=dimension_input.EditLease(
                self.session_id,
                "pending_circle_diameter",
                pending["input_revision"],
                int(self.input_token[:12], 16),
            ),
            select_all=True,
        )
        self.field_position = position
        self.field_layout = None
        self.field_drag = False
        self.error = ""
        self.message = (
            "Driving diameter: number or unit literal · Enter creates · Esc returns to Circle"
        )

    def update_circle_diameter_raw(self, raw):
        self._require_idle()
        candidate = draft_dispatch.clone(self.draft)
        candidate.update_pending_diameter(raw)
        captured = self._input_environment()
        self._replace_ui_intent(
            candidate, postcheck=lambda: self._require_input_environment(captured)
        )

    def cancel_circle_diameter(self):
        self.cancel_native()
        self._require_current()
        candidate = draft_dispatch.clone(self.draft)
        candidate.cancel_pending_diameter()
        self._replace_ui_intent(candidate, cancelled_input=True)
        self.input_token = ""
        if self.input_controller is not None:
            self.input_controller.close()
        self.proposal_capture = False
        self.error = ""
        self.message = "Diameter cancelled; original Circle retained. Continue to place its radius."

    def request_circle_diameter_accept(self, context):
        from .pending_circle_diameter import prepare_diameter_candidate

        self._require_idle()
        _require(
            self.draft.pending_diameter is not None
            and self.input_token
            and self.input_controller is not None
            and not self.input_controller.closed,
            "Reopen Driving diameter before accepting the retained input.",
        )
        _require(
            self.input_controller.raw == self.draft.pending_diameter["raw_text"]
            and self.input_controller.lease.owner_id == self.session_id
            and self.input_controller.lease.field_id == "pending_circle_diameter"
            and self.input_controller.lease.token == int(self.input_token[:12], 16),
            "Driving diameter text lease changed; reopen the field.",
        )
        _require(
            getattr(self, "diameter_attempt", None) is None,
            "This diameter is already being checked.",
        )
        candidate, _receipt = prepare_diameter_candidate(self.draft)
        operation_contracts.validate_authoring_candidate(candidate.command_draft.candidate())
        attempt = DiameterAttempt(
            draft_dispatch.dumps(self.draft), draft_dispatch.dumps(candidate), self.input_token
        )
        self.diameter_attempt = attempt
        try:
            if self.commands.sketch["points"]:
                self._start_job(context, self.commands.solve_request(), "diameter_baseline")
            else:
                self._start_job(context, candidate.command_draft.solve_request(), "diameter_solve")
        except Exception:
            self.diameter_attempt = None
            raise
        self.message = "Checking driving diameter; nothing is added until validation succeeds."

    def _diameter_current(self):
        attempt = getattr(self, "diameter_attempt", None)
        _require(
            type(attempt) is DiameterAttempt
            and self.draft.tool == "Circle"
            and self.draft.proposal is not None
            and self.draft.proposal["kind"] == "circle"
            and attempt.token == self.input_token
            and attempt.source == draft_dispatch.dumps(self.draft)
            and self.draft.pending_diameter is not None,
            "Driving diameter input changed; reopen it and retry.",
        )
        return attempt

    def _diameter_read(self, pair, action="solve_sketch"):
        return read_guarded_operation(
            pair[0],
            pair[1],
            self._backend_current_selection(),
            owner_token=self.owner_token,
            action=action,
            require_success=True,
        )

    def _diameter_expected_points(self, attempt, candidate):
        pending = self.draft.pending_diameter
        before = (
            {}
            if attempt.baseline is None
            else _points(self._diameter_read(attempt.baseline)["result"]["sketch"]["solved"])
        )
        # Captured positions are intent only. A fresh baseline must agree for
        # reused points; resumed raw input never supplies native proof.
        original = pending["original_proposal"]["anchor"]
        captured = {}
        if original["kind"] == "existing":
            captured[original["point_id"]] = pending["center_position"]
        _same_points(before, captured)
        expected = dict(before)
        original_ids = {p["id"] for p in self.commands.sketch["points"]}
        _require(set(before) == original_ids, "Baseline point identities changed.")
        expected.update(
            {
                p["id"]: (p["u"], p["v"])
                for p in candidate.command_draft.sketch["points"]
                if p["id"] not in original_ids
            }
        )
        return expected

    def _diameter_expected_radii(self, attempt, candidate):
        before = (
            {}
            if attempt.baseline is None
            else _radii(self._diameter_read(attempt.baseline)["result"]["sketch"]["solved"])
        )
        original_ids = {c["id"] for c in self.commands.sketch.get("circles", [])}
        _require(set(before) == original_ids, "Baseline circle identities changed.")
        expected = dict(before)
        expected.update(
            {
                c["id"]: c["radius"]
                for c in candidate.command_draft.sketch.get("circles", [])
                if c["id"] not in original_ids
            }
        )
        return expected

    def complete_circle_diameter(self, context, kind, evidence, prepared, response):
        """Called only after the ordinary pending-owner poll/CAS has completed."""
        _require(
            kind in {"diameter_baseline", "diameter_solve"},
            "Unexpected Circle-diameter completion.",
        )
        attempt = self._diameter_current()
        _require(
            (kind == "diameter_baseline")
            == (attempt.baseline is None and bool(self.commands.sketch["points"])),
            "Circle-diameter completion phase changed.",
        )
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
        if kind == "diameter_baseline":
            attempt = replace(attempt, baseline=(evidence, prepared))
            self._diameter_expected_points(attempt, candidate)
            self.diameter_attempt = attempt
            self._start_job(context, candidate.command_draft.solve_request(), "diameter_solve")
            return
        expected = self._diameter_expected_points(attempt, candidate)
        expected_radii = self._diameter_expected_radii(attempt, candidate)
        _same_radii(_radii(response["result"]["sketch"]["solved"]), expected_radii)
        _require(kind == "diameter_solve", "Unexpected Circle-diameter completion.")
        _same_points(_points(response["result"]["sketch"]["solved"]), expected)
        attempt = replace(attempt, solved=(evidence, prepared))
        self.diameter_attempt = attempt
        _require(attempt.solved is not None, "Driving diameter solve evidence was retired.")
        solve_response = self._diameter_read(attempt.solved)
        _same_points(_points(solve_response["result"]["sketch"]["solved"]), expected)
        _same_radii(_radii(solve_response["result"]["sketch"]["solved"]), expected_radii)
        commands = candidate.command_draft
        self._bind_commands(commands)
        _require(
            commands.record_guarded_solution(
                attempt.solved[0], commands.revision, expected_prepared=attempt.solved[1]
            ),
            "Driving diameter needs a successful native solve.",
        )
        environment = self._input_environment()
        self._diameter_current()

        def postcheck():
            self._require_input_environment(environment)
            _require(self.input_token == attempt.token, "The diameter input lease was retired.")
            _require(
                draft_dispatch.dumps(self.draft) == attempt.candidate,
                "The diameter candidate changed.",
            )
            if attempt.baseline is not None:
                self._diameter_read(attempt.baseline)
            _require(commands.has_current_solution, "Driving diameter evidence was revoked.")
            self._diameter_read(attempt.solved)

        self.replace_authoring(candidate, postcheck=postcheck)
        self.guarded_evidence, self.expected_prepared = attempt.solved
        self.evidence_request = self.expected_prepared.operation_request()
        self.evidence_response = solve_response
        self._retain_outline()
        self.diameter_attempt = None
        self.input_token = ""
        self.input_controller.close()
        self.proposal_capture = False
        self.error = ""
        self.message = (
            "Circle and driving diameter created together. Finish validates and updates the Part."
        )
