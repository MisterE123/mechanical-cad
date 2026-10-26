"""Detached Remove Fillet trial with guarded retained-point placement checks."""

import math
from dataclasses import dataclass, replace

from . import backend_runtime, draft_dispatch
from .general_sketch_commands import RemoveCornerFillet, _json, _require
from .general_sketch_draft import read_guarded_operation
from .sketch_remove_fillet import retain_removal_ui, validate_annotation_attachments


@dataclass(frozen=True)
class RemovalAttempt:
    source: str
    candidate: str
    baseline: tuple
    solved: tuple | None = None


def same_retained_points(before, after, retained):
    """Never repair placement by changing expressions, seeds or hidden anchors."""
    expected = {p["id"]: (p["u"], p["v"]) for p in before["points"]}
    actual = {p["id"]: (p["u"], p["v"]) for p in after["points"]}
    _require(set(actual) == set(retained), "Removal solve changed the retained point identities.")
    for identifier in retained:
        _require(identifier in expected and all(math.isfinite(v) for v in actual[identifier])
                 and math.dist(actual[identifier], expected[identifier]) <= 1e-7,
                 "Remove Fillet would move another point. Constrain the sketch placement first, then retry; the original fillet is unchanged.")


class RemoveFilletSession:
    def _removal_read(self, pair, action="solve_sketch"):
        return read_guarded_operation(
            pair[0], pair[1], self._backend_current_selection(),
            owner_token=self.owner_token, action=action, require_success=True,
        )

    def _removal_current(self):
        attempt = getattr(self, "removal_attempt", None)
        _require(type(attempt) is RemovalAttempt and attempt.source == draft_dispatch.dumps(self.draft),
                 "The fillet removal source changed; reopen Remove Sketch Fillet.")
        _require(self.current_solution_response() is not None
                 and self.guarded_evidence is attempt.baseline[0]
                 and self.expected_prepared is attempt.baseline[1],
                 "The original Check is no longer current; Check again before removing the fillet.")
        return attempt

    def request_fillet_removal(self, context, arc_id):
        self._require_idle()
        _require(getattr(self, "removal_attempt", None) is None,
                 "This fillet removal is already being checked.")
        _require(self.current_solution_response() is not None,
                 "Check the sketch before removing its fillet.")
        baseline = (self.guarded_evidence, self.expected_prepared)
        self._removal_read(baseline)
        candidate = draft_dispatch.clone(self.draft)
        record = validate_annotation_attachments(candidate, arc_id)
        candidate.command_draft.execute(RemoveCornerFillet(arc_id))
        retain_removal_ui(candidate, record)
        self.removal_attempt = RemovalAttempt(
            draft_dispatch.dumps(self.draft), draft_dispatch.dumps(candidate), baseline,
        )
        try:
            self._start_job(context, candidate.command_draft.solve_request(), "remove_fillet_solve")
        except Exception:
            self.removal_attempt = None
            raise
        self.message = "Checking sharp-corner placement; the original fillet stays unchanged until validation succeeds."

    def complete_fillet_removal(self, context, evidence, prepared, response, *, kind="remove_fillet_solve"):
        attempt = self._removal_current()
        if not response["ok"]:
            _require(False, response["error"]["message"])
        _require(kind in {"remove_fillet_solve", "remove_fillet_replay"}, "Unexpected removal result.")
        action = "solve_sketch" if kind == "remove_fillet_solve" else "replay"
        evidence.publication.consume(
            self._backend_current_selection(), owner_token=self.owner_token,
            expected_action=action,
            expected_result_version=prepared.operation_request()["result_version"],
            require_success=True,
        )
        candidate = draft_dispatch.restore(attempt.candidate, self.draft.document_json)
        commands = candidate.command_draft
        baseline = self._removal_read(attempt.baseline)["result"]["sketch"]["solved"]
        checked = self._removal_read((evidence, prepared), action)
        _require(_json(prepared.operation_request()["document"]) == _json(commands.candidate()),
                 "Removal result belongs to a different canonical candidate.")
        retained = {p["id"] for p in commands.sketch["points"]}
        replay_pair = None
        if kind == "remove_fillet_solve":
            same_retained_points(baseline, checked["result"]["sketch"]["solved"], retained)
            attempt = replace(attempt, solved=(evidence, prepared))
            self.removal_attempt = attempt
            if commands.consumed_by:
                selection, tolerance = backend_runtime.configuration(context)
                self._start_job(context, commands.replay_request(options={"linear_deflection": tolerance}),
                                "remove_fillet_replay", selection=selection)
                return
        else:
            _require(attempt.solved is not None, "The original removal solve was retired.")
            feature = next((f for f in checked["result"]["features"] if f["id"] == commands.feature_id), None)
            _require(feature is not None and feature["status"] == "ok", "Removal replay did not retain the sketch.")
            same_retained_points(baseline, feature["sketch"]["solved"], retained)
            replay_pair = (evidence, prepared)
        solve_evidence, solve_prepared = attempt.solved
        solved_response = self._removal_read(attempt.solved)
        same_retained_points(baseline, solved_response["result"]["sketch"]["solved"], retained)
        self._bind_commands(commands)
        _require(commands.record_guarded_solution(solve_evidence, commands.revision, expected_prepared=solve_prepared),
                 "Remove Fillet needs a successful native solve.")
        if replay_pair is not None:
            # The existing same-candidate solve/replay authority chain is retained,
            # including backend/owner revocation and distinct prepared nonces.
            commands._solution_evidence = (solve_evidence, replay_pair[0])
            commands._solution_prepared = (solve_prepared, replay_pair[1])
            _require(commands.has_current_solution, "Removal downstream evidence was revoked.")
        environment = self._input_environment()
        self._removal_current()

        def postcheck():
            self._require_input_environment(environment)
            _require(self.removal_attempt is attempt
                     and draft_dispatch.dumps(self.draft) == attempt.candidate,
                     "The fillet removal acceptance changed.")
            self._removal_read(attempt.baseline)
            _require(commands.has_current_solution, "Removal solve evidence was revoked.")
            solved = self._removal_read(attempt.solved)["result"]["sketch"]["solved"]
            same_retained_points(baseline, solved, retained)
            if replay_pair is not None:
                result = self._removal_read(replay_pair, "replay")
                feature = next(f for f in result["result"]["features"] if f["id"] == commands.feature_id)
                same_retained_points(baseline, feature["sketch"]["solved"], retained)

        self.replace_authoring(candidate, postcheck=postcheck)
        self.guarded_evidence, self.expected_prepared = solve_evidence, solve_prepared
        self.evidence_request = solve_prepared.operation_request()
        self.evidence_response = solved_response
        self.removal_attempt = None
        self._retain_outline()
        self.error = ""
        self.message = "Sharp corner restored without moving retained points. Undo restores the fillet; Finish validates the Part."
