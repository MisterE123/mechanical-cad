"""Pure owner guards; fake jobs below provide no native-solver evidence."""

import importlib
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

PACKAGE = "mcad_pending_length_session_guard_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package
s = importlib.import_module(PACKAGE + ".line_length_session")
a = importlib.import_module(PACKAGE + ".general_authoring")
c = importlib.import_module(PACKAGE + ".general_sketch_commands")
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
p = importlib.import_module(PACKAGE + ".pending_line_length")
BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}'


class Owner(s.LineLengthSession):
    def __init__(self, state):
        self.draft = state
        self.commands = state.command_draft
        self.input_token = "abc123456789"
        self.session_id = "session"
        self.length_attempt = None
        self.input_controller = SimpleNamespace(
            closed=False,
            raw=state.pending_length["raw_text"],
            lease=SimpleNamespace(
                owner_id=self.session_id,
                field_id="pending_line_length",
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
        self.length_attempt = None

    def _replace_ui_intent(self, candidate, **kwargs):
        self.draft = candidate
        self.commands = candidate.command_draft


def owner(*, existing=False, raw="5"):
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))
    if existing:
        anchor = state.command_draft.execute(c.AddPoint(c.PointSeed(0, 0))).entity_ids[0]
        state.command_draft.execute(c.AddPoint(c.PointSeed(30, 40)))
        state.begin_line(c.PointRef(anchor))
    else:
        state.begin_line(c.PointSeed(0, 0))
    points = {p["id"]: (p["u"], p["v"]) for p in state.command_draft.sketch["points"]}
    state.begin_pending_length(c.PointSeed(3, 4), points)
    state.update_pending_length(raw)
    return Owner(state)


def test_length_attempt_binding_is_frozen():
    attempt = s.LengthAttempt("source", "candidate", "token")
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
def test_stale_length_lease_or_exact_source_is_rejected(change):
    session = owner()
    session.request_line_length_accept(None)
    if change == "token":
        session.input_token = "different"
    elif change == "raw":
        session.draft.update_pending_length("6")
    elif change == "source":
        session.draft.command_draft.execute(c.AddPoint(c.PointSeed(50, 60)))
    elif change == "missing_pending":
        session.draft.cancel_pending_length()
    else:
        session.length_attempt = None
    with pytest.raises(c.DraftError, match="input changed"):
        session._length_current()


@pytest.mark.parametrize("existing,kind", [(False, "length_solve"), (True, "length_baseline")])
def test_acceptance_starts_only_one_job_and_preserves_live_intent(existing, kind):
    session = owner(existing=existing)
    before = s.draft_dispatch.dumps(session.draft)
    session.request_line_length_accept(None)
    assert len(session.jobs) == 1 and session.jobs[0][1] == kind
    assert session.length_attempt.source == before
    assert session.length_attempt.candidate != before
    assert s.draft_dispatch.dumps(session.draft) == before
    with pytest.raises(c.DraftError, match="already being checked"):
        session.request_line_length_accept(None)
    assert len(session.jobs) == 1


def test_failed_job_start_retires_attempt_without_changing_raw_intent():
    session = owner()
    before = s.draft_dispatch.dumps(session.draft)

    def fail(*args):
        raise RuntimeError("job unavailable")

    session._start_job = fail
    with pytest.raises(RuntimeError, match="job unavailable"):
        session.request_line_length_accept(None)
    assert session.length_attempt is None
    assert s.draft_dispatch.dumps(session.draft) == before


@pytest.mark.parametrize("raw", ["width", "2 + 3", "5/2"])
def test_formula_rejection_stays_pending_then_cancel_restores_line(raw):
    session = owner(raw=raw)
    before = s.draft_dispatch.dumps(session.draft)
    original = session.draft.pending_length["original_proposal"]
    with pytest.raises(c.DraftError, match="Dimension"):
        session.request_line_length_accept(None)
    assert s.draft_dispatch.dumps(session.draft) == before
    assert session.length_attempt is None and not session.jobs
    session.cancel_line_length()
    assert session.draft.pending_length is None
    assert session.draft.resume_proposal() == original
    assert not session.commands.sketch["lines"]
    assert session.input_controller.closed and not session.input_token
    with pytest.raises(c.DraftError, match="Reopen"):
        session.request_line_length_accept(None)


def test_expected_positions_include_entire_baseline_and_new_endpoint():
    session = owner(existing=True)
    candidate, _ = p.prepare_length_candidate(session.draft)
    prior = session.commands.sketch["points"]
    baseline = {"result": {"sketch": {"solved": {"points": prior}}}}
    session._length_read = lambda pair: baseline
    attempt = s.LengthAttempt("source", "candidate", "token", baseline=(object(), object()))
    expected = session._length_expected_points(attempt, candidate)
    assert expected == {p["id"]: (p["u"], p["v"]) for p in candidate.command_draft.sketch["points"]}
    assert len(expected) == 3  # Reused anchor, unrelated existing point, new endpoint.
    baseline["result"]["sketch"]["solved"]["points"][0]["u"] = 0.01
    with pytest.raises(c.DraftError, match="captured placement"):
        session._length_expected_points(attempt, candidate)


@pytest.mark.parametrize(
    "field,value", [("raw", "6"), ("owner_id", "other"), ("field_id", "driver"), ("token", 42)]
)
def test_mismatched_controller_text_or_lease_never_starts_job(field, value):
    session = owner()
    target = session.input_controller if field == "raw" else session.input_controller.lease
    setattr(target, field, value)
    with pytest.raises(c.DraftError, match="text lease changed"):
        session.request_line_length_accept(None)
    assert not session.jobs and session.length_attempt is None


def test_reused_anchor_requires_fresh_baseline_not_only_retained_positions():
    session = owner(existing=True)
    candidate, _ = p.prepare_length_candidate(session.draft)
    attempt = s.LengthAttempt("source", "candidate", "token")
    with pytest.raises(c.DraftError, match="captured placement"):
        session._length_expected_points(attempt, candidate)
