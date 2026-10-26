"""Pure owner guards; fake jobs below provide no native-solver evidence."""

import importlib
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

PACKAGE = "mcad_pending_diameter_session_guard_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package
s = importlib.import_module(PACKAGE + ".circle_diameter_session")
a = importlib.import_module(PACKAGE + ".general_authoring")
c = importlib.import_module(PACKAGE + ".general_sketch_commands")
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
p = importlib.import_module(PACKAGE + ".pending_circle_diameter")
BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}'


class Owner(s.CircleDiameterSession):
    def __init__(self, state):
        self.draft = state
        self.commands = state.command_draft
        self.input_token = "abc123456789"
        self.session_id = "session"
        self.diameter_attempt = None
        self.input_controller = SimpleNamespace(
            closed=False,
            raw=state.pending_diameter["raw_text"],
            lease=SimpleNamespace(
                owner_id=self.session_id,
                field_id="pending_circle_diameter",
                token=int(self.input_token[:12], 16),
            ),
        )
        self.input_controller.close = lambda: setattr(self.input_controller, "closed", True)
        self.jobs = []
        self.proposal_capture = False

    def _require_idle(self):
        pass

    def _require_current(self):
        pass

    def _start_job(self, context, request, kind):
        self.jobs.append((request, kind))

    def cancel_native(self):
        self.diameter_attempt = None

    def _replace_ui_intent(self, candidate, **kwargs):
        self.draft = candidate
        self.commands = candidate.command_draft


def owner(*, existing=False, raw="5"):
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))
    if existing:
        anchor = state.command_draft.execute(c.AddPoint(c.PointSeed(0, 0))).entity_ids[0]
        state.command_draft.execute(c.AddPoint(c.PointSeed(30, 40)))
        state.begin_circle(c.PointRef(anchor))
    else:
        state.begin_circle(c.PointSeed(0, 0))
    points = {p["id"]: (p["u"], p["v"]) for p in state.command_draft.sketch["points"]}
    state.begin_pending_diameter(points)
    state.update_pending_diameter(raw)
    return Owner(state)


def test_diameter_attempt_binding_is_frozen():
    attempt = s.DiameterAttempt("source", "candidate", "token")
    with pytest.raises(FrozenInstanceError):
        attempt.token = "replacement"
    assert attempt.baseline is None and attempt.solved is None


@pytest.mark.parametrize("actual", [{}, {"a": (0, 1e-6)}, {"a": (float("nan"), 0)}])
def test_missing_moved_or_nonfinite_expected_point_is_rejected(actual):
    with pytest.raises(c.DraftError, match="move an existing point"):
        s._same_points(actual, {"a": (0, 0)})


def test_every_expected_point_is_checked_not_only_reused_anchor():
    with pytest.raises(c.DraftError):
        s._same_points(
            {"anchor": (0, 0), "unrelated": (30, 40.001)}, {"anchor": (0, 0), "unrelated": (30, 40)}
        )
    s._same_points({"anchor": (0, 1e-8), "extra": (4, 5)}, {"anchor": (0, 0)})


@pytest.mark.parametrize("change", ["token", "raw", "source", "missing_pending", "no_attempt"])
def test_stale_diameter_lease_or_exact_source_is_rejected(change):
    session = owner()
    session.request_circle_diameter_accept(None)
    if change == "token":
        session.input_token = "different"
    elif change == "raw":
        session.draft.update_pending_diameter("6")
    elif change == "source":
        session.draft.command_draft.execute(c.AddPoint(c.PointSeed(50, 60)))
    elif change == "missing_pending":
        session.draft.cancel_pending_diameter()
    else:
        session.diameter_attempt = None
    with pytest.raises(c.DraftError, match="input changed"):
        session._diameter_current()


@pytest.mark.parametrize("existing,kind", [(False, "diameter_solve"), (True, "diameter_baseline")])
def test_acceptance_starts_only_one_job_and_preserves_live_intent(existing, kind):
    session = owner(existing=existing)
    before = s.draft_dispatch.dumps(session.draft)
    session.request_circle_diameter_accept(None)
    assert len(session.jobs) == 1 and session.jobs[0][1] == kind
    assert session.diameter_attempt.source == before
    assert session.diameter_attempt.candidate != before
    assert s.draft_dispatch.dumps(session.draft) == before
    with pytest.raises(c.DraftError, match="already being checked"):
        session.request_circle_diameter_accept(None)
    assert len(session.jobs) == 1


def test_failed_job_start_retires_attempt_without_changing_raw_intent():
    session = owner()
    before = s.draft_dispatch.dumps(session.draft)

    def fail(*args):
        raise RuntimeError("job unavailable")

    session._start_job = fail
    with pytest.raises(RuntimeError, match="job unavailable"):
        session.request_circle_diameter_accept(None)
    assert session.diameter_attempt is None
    assert s.draft_dispatch.dumps(session.draft) == before


@pytest.mark.parametrize("raw", ["width", "2 + 3", "5/2"])
def test_formula_rejection_stays_pending_then_cancel_restores_circle(raw):
    session = owner(raw=raw)
    before = s.draft_dispatch.dumps(session.draft)
    original = session.draft.pending_diameter["original_proposal"]
    with pytest.raises(c.DraftError, match="Dimension"):
        session.request_circle_diameter_accept(None)
    assert s.draft_dispatch.dumps(session.draft) == before
    assert session.diameter_attempt is None and not session.jobs
    session.cancel_circle_diameter()
    assert session.draft.pending_diameter is None
    assert session.draft.resume_proposal() == original
    assert not session.commands.sketch.get("circles", [])
    assert session.input_controller.closed and not session.input_token
    with pytest.raises(c.DraftError, match="Reopen"):
        session.request_circle_diameter_accept(None)


def test_expected_positions_include_entire_baseline_with_reused_center():
    session = owner(existing=True)
    candidate, _ = p.prepare_diameter_candidate(session.draft)
    prior = session.commands.sketch["points"]
    baseline = {"result": {"sketch": {"solved": {"points": prior}}}}
    session._diameter_read = lambda pair: baseline
    attempt = s.DiameterAttempt("source", "candidate", "token", baseline=(object(), object()))
    expected = session._diameter_expected_points(attempt, candidate)
    assert expected == {p["id"]: (p["u"], p["v"]) for p in candidate.command_draft.sketch["points"]}
    assert len(expected) == 2  # Reused center and unrelated existing point.
    baseline["result"]["sketch"]["solved"]["points"][0]["u"] = 0.01
    with pytest.raises(c.DraftError, match="captured placement"):
        session._diameter_expected_points(attempt, candidate)


@pytest.mark.parametrize(
    "field,value", [("raw", "6"), ("owner_id", "other"), ("field_id", "driver"), ("token", 42)]
)
def test_mismatched_controller_text_or_lease_never_starts_job(field, value):
    session = owner()
    target = session.input_controller if field == "raw" else session.input_controller.lease
    setattr(target, field, value)
    with pytest.raises(c.DraftError, match="text lease changed"):
        session.request_circle_diameter_accept(None)
    assert not session.jobs and session.diameter_attempt is None


def test_reused_anchor_requires_fresh_baseline_not_only_retained_positions():
    session = owner(existing=True)
    candidate, _ = p.prepare_diameter_candidate(session.draft)
    attempt = s.DiameterAttempt("source", "candidate", "token")
    with pytest.raises(c.DraftError, match="captured placement"):
        session._diameter_expected_points(attempt, candidate)


@pytest.mark.parametrize("actual", [{}, {"old": 4.1}, {"old": float("nan")}, {"old": float("inf")}, {"old": 4, "extra": 2}])
def test_missing_moved_nonfinite_or_extra_circle_radius_rejected(actual):
    with pytest.raises(c.DraftError):
        s._same_radii(actual, {"old": 4})


def test_existing_radii_and_new_requested_radius_both_checked():
    session = owner()
    session.commands.execute(c.AddCircle(c.PointSeed(30, 40), 7))
    candidate, _ = p.prepare_diameter_candidate(session.draft)
    prior = session.commands.sketch["circles"]
    baseline = {"result": {"sketch": {"solved": {"circles": prior}}}}
    session._diameter_read = lambda pair: baseline
    attempt = s.DiameterAttempt("source", "candidate", "token", baseline=(object(), object()))
    expected = session._diameter_expected_radii(attempt, candidate)
    assert len(expected) == 2 and sorted(expected.values()) == [2.5, 7]
    s._same_radii(expected, expected)
    actual = dict(expected)
    actual[prior[0]["id"]] += 0.01
    with pytest.raises(c.DraftError, match="existing circle"):
        s._same_radii(actual, expected)
    with pytest.raises(c.DraftError, match="Baseline circle identities"):
        session._diameter_expected_radii(s.DiameterAttempt("source", "candidate", "token"), candidate)


@pytest.mark.parametrize("existing,kind", [(False, "diameter_baseline"), (True, "diameter_solve"), (False, "length_solve")])
def test_wrong_completion_phase_rejected_before_consuming_evidence(existing, kind):
    session = owner(existing=existing)
    session.request_circle_diameter_accept(None)
    before = s.draft_dispatch.dumps(session.draft)
    with pytest.raises(c.DraftError, match="phase changed|Unexpected"):
        session.complete_circle_diameter(None, kind, None, None, {"ok": True})
    assert s.draft_dispatch.dumps(session.draft) == before


def test_duplicate_baseline_completion_rejected_before_consuming_evidence():
    from dataclasses import replace
    session = owner(existing=True)
    session.request_circle_diameter_accept(None)
    session.diameter_attempt = replace(session.diameter_attempt, baseline=(object(), object()))
    with pytest.raises(c.DraftError, match="phase changed"):
        session.complete_circle_diameter(None, "diameter_baseline", None, None, {"ok": True})
