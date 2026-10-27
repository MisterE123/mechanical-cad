"""Deterministic cleanup budgets with one publicly admitted pending job."""

import time
import types

import pytest
from test_sketch_pending import (
    identity,
    p,
    request,
)
from test_sketch_pending import (
    jobs as jobs,
)
from test_sketch_pending import (
    no_leaked_work as no_leaked_work,
)


def _clock(monkeypatch, ticks):
    original = time.monotonic
    values = iter(ticks)
    observed = []

    def monotonic():
        value = next(values, ticks[-1])
        observed.append(value)
        return value

    monkeypatch.setattr(p, "time", types.SimpleNamespace(monotonic=monotonic))
    assert time.monotonic is original and p.time is not time
    return observed


def _retained_until_reaped(pending, job):
    assert p.execution_lease.is_busy() and p.status(pending)["cleanup_pending"]
    assert not job.cleaned and not pending.done and job.result_calls == 0
    job.cleaned = True
    assert not p.reap() and not p.execution_lease.is_busy()
    assert pending.done and p.status(pending)["phase"] == "cancelled"
    assert job.result_calls == 0 and not p.status()


def test_cancel_all_large_unchanged_clock_never_exceeds_strict_budget(jobs, monkeypatch):
    now = float(2**20)
    assert (now + 0.02) - now > 0.02  # The original deadline arithmetic overshoots.
    observed = _clock(monkeypatch, [now])
    pending = p.prepare(request(), identity())
    assert not p.cancel_all(wait_timeout=0.02)
    assert jobs[0].wait_calls == [0.02]
    assert 0 <= jobs[0].wait_calls[0] <= 0.02
    assert observed[:3] == [now, now, now]
    _retained_until_reaped(pending, jobs[0])


@pytest.mark.parametrize(
    "ticks,timeout,expected",
    [
        ([1024.0, 1024.0, 1024.125], 1.0, 0.875),
        ([1024.0, 1024.0, 1026.0], 1.0, 0.0),
        ([1024.0, 1024.0, 1024.0], 0.0, 0.0),
    ],
    ids=["elapsed", "expired", "zero"],
)
@pytest.mark.parametrize("wait_error", [False, True], ids=["pending", "wait-exception"])
def test_cancel_all_clock_keeps_only_remaining_budget_and_retains_ownership(
    jobs, monkeypatch, ticks, timeout, expected, wait_error
):
    observed = _clock(monkeypatch, ticks)
    pending = p.prepare(request(), identity())
    if wait_error:
        jobs[0].wait_error = RuntimeError("injected cleanup wait failure")
    assert not p.cancel_all(wait_timeout=timeout)
    assert jobs[0].wait_calls == [expected]
    assert 0 <= jobs[0].wait_calls[0] <= timeout
    assert observed[:3] == ticks
    if wait_error:
        assert "cleanup wait failed" in p.status(pending)["message"]
        assert "injected cleanup wait failure" in p.status(pending)["message"]
    _retained_until_reaped(pending, jobs[0])
