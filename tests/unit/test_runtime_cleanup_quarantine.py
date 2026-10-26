"""Pure quarantine/scope/async lifecycle ports; no CAD or Blender execution."""

import ast
import importlib
import itertools
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
_NAMES = itertools.count()


def function(path, name, namespace):
    node = next(
        node
        for node in ast.parse((ADDON / path).read_bytes()).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(ADDON / path), "exec"), namespace)
    return namespace[name]


@pytest.fixture
def harness(monkeypatch):
    name = "mcad_cleanup_quarantine_" + str(next(_NAMES))
    package = types.ModuleType(name)
    package.__path__ = [str(ADDON)]
    monkeypatch.setitem(sys.modules, name, package)
    # Cleanup owns no Blender interaction or new admission. These explicit ports
    # let the real Assembly cleanup code load without importing the host UI.
    def forbidden_admission(*args, **kwargs):
        pytest.fail("cleanup unexpectedly entered Blender interaction/admission")

    for leaf, methods in (
        ("sketch_session", ("interaction_revision",)),
        ("staged_edit_store", ("interaction_revision", "require_no_live_edit", "require_no_resume")),
        ("workspace", ("get_role",)),
    ):
        module = types.ModuleType(name + "." + leaf)
        for method in methods:
            setattr(module, method, forbidden_admission)
        monkeypatch.setitem(sys.modules, module.__name__, module)
    lease = importlib.import_module(name + ".execution_lease")
    guarded = importlib.import_module(name + ".guarded_transport")
    managed = importlib.import_module(name + ".sidecar_job")
    contracts = importlib.import_module(name + ".backend_contracts")
    selection = importlib.import_module(name + ".backend_selection").BackendSelection.capture(
        str(ROOT), sys.executable, generation=0, lifetime_id="quarantine-test", environment={}
    )
    yield types.SimpleNamespace(
        name=name,
        lease=lease,
        guarded=guarded,
        managed=managed,
        contracts=contracts,
        selection=selection,
    )
    # Quarantine has no reset API. Each test's isolated module lifetime ends here;
    # the pure test ports own no actual process, OS lock, or descriptor resources.
    for key in list(sys.modules):
        if key.startswith(name + "."):
            del sys.modules[key]


def request(h, action="canonical_snapshot"):
    ordinary = {"protocol_version": 1, "action": action, "document": {}}
    if action.startswith("export_"):
        ordinary.update(result_version=2, destination="/unused/never-written.step")
    return h.contracts.prepare_request(ordinary)


def run(h, action="canonical_snapshot", current=None):
    return h.guarded.execute(
        request(h, action),
        h.selection,
        owner_token=object(),
        current_selection=current or (lambda: h.selection),
    )


def port(h, monkeypatch, *, uncertain=False, initial_error=None, cancel_uncertain=False):
    original = h.guarded.GuardedJob
    jobs = []
    value = object()  # Lifecycle-only port result; never represents CAD evidence.

    class Job:
        def __init__(self, prepared, selected, *, owner_token):
            assert h.lease.is_busy() and h.lease._BOUND_TOKEN is h.lease._TOKEN
            self.token = h.lease._TOKEN
            self._action = prepared.action
            self._start_attempted = False
            self._historical_export = None
            self.state = "created"
            self.done = False
            self.cancel_calls = self.wait_calls = self.result_calls = 0
            self.cleanup_diagnostic = ""
            self.original_resources = object()
            jobs.append(self)
            if initial_error == "constructor":
                raise RuntimeError("constructor failed")

        _error = original._error

        def start(self, selected):
            self._start_attempted = True
            self.state = "cleanup_uncertain" if uncertain else "ready"
            self.done = not uncertain
            self.cleanup_diagnostic = h.lease.QUARANTINE_MESSAGE if uncertain else ""
            if initial_error == "start":
                raise RuntimeError("start failed after acquiring resources")

        def wait(self, timeout=None):
            self.wait_calls += 1
            return self.done

        def cancel(self):
            self.cancel_calls += 1
            if self.state == "created":
                self.state, self.done = "cancelled", True
            if cancel_uncertain:
                self.state, self.done = "cleanup_uncertain", False
                self.cleanup_diagnostic = h.lease.QUARANTINE_MESSAGE

        def result(self, current, *, owner_token):
            self.result_calls += 1
            if initial_error == "result":
                raise RuntimeError("result failed")
            self.state = "consumed"
            return value

    monkeypatch.setattr(h.guarded, "GuardedJob", Job)
    return jobs, value


@pytest.mark.parametrize("borrowed", [False, True])
def test_successful_transport_owns_or_borrows_exact_token(harness, monkeypatch, borrowed):
    h = harness
    jobs, result = port(h, monkeypatch)
    if borrowed:
        token = h.lease.try_acquire()
        with h.lease.synchronous(token):
            assert run(h) is result
            assert jobs[0].token is token
            assert h.lease._TOKEN is token and h.lease.is_busy()
            assert h.lease._BOUND_TOKEN is None
        assert h.lease.release(token)
    else:
        assert run(h) is result
        assert not h.lease.is_busy() and h.lease._BOUND_TOKEN is None
    assert jobs[0].result_calls == 1
    assert h.lease._QUARANTINE is None


@pytest.mark.parametrize("borrowed", [False, True])
@pytest.mark.parametrize("initial_error", ["constructor", "start", "current", "result"])
def test_clean_constructor_start_currentness_result_failures_release_only_owned_token(
    harness, monkeypatch, borrowed, initial_error
):
    h = harness
    jobs, _ = port(h, monkeypatch, initial_error=initial_error)

    def current():
        if initial_error == "current":
            raise RuntimeError("current selection failed")
        return h.selection

    token = h.lease.try_acquire() if borrowed else None
    scope = h.lease.synchronous(token) if borrowed else nullcontext()
    with scope:
        with pytest.raises(RuntimeError, match="failed"):
            run(h, current=current)
        assert h.lease._BOUND_TOKEN is None
        assert h.lease.is_busy() is borrowed
        if borrowed:
            assert h.lease._TOKEN is token
    if borrowed:
        assert h.lease.release(token)
    assert h.lease._QUARANTINE is None
    if initial_error != "constructor":
        assert jobs[0].cancel_calls == 1 and jobs[0].wait_calls >= 1


@pytest.mark.parametrize("action", ["canonical_snapshot", "export_step", "export_stl"])
@pytest.mark.parametrize("borrowed", [False, True])
def test_uncertainty_returns_error_quarantines_original_owner_and_never_constructs_successor(
    harness, monkeypatch, action, borrowed
):
    h = harness
    jobs, _ = port(h, monkeypatch, uncertain=True)
    token = h.lease.try_acquire() if borrowed else None
    scope = h.lease.synchronous(token) if borrowed else nullcontext()
    with scope:
        started = time.monotonic()
        with pytest.raises(h.guarded.GuardedOperationError, match="restart Blender") as error:
            run(h, action)
        assert time.monotonic() - started < 1
        assert error.value.outcome_unknown is action.startswith("export_")
    original = jobs[0]
    assert h.lease._QUARANTINE == (original.token, original)
    assert original.result_calls == 0 and not original.done
    assert h.lease._TOKEN is original.token
    assert not h.lease.release(original.token)
    assert h.lease.try_acquire() is None
    for _ in range(3):
        with pytest.raises(h.guarded.GuardedOperationError, match="restart Blender"):
            run(h, action)
        assert len(jobs) == 1
        assert not original.wait(0)
        assert not h.lease.release(original.token)
    backend = importlib.import_module(h.name + ".backend_runtime")
    backend.new_lifetime("disable lifecycle")
    backend.new_lifetime("enable lifecycle")
    assert h.lease._QUARANTINE == (original.token, original)
    assert h.lease.try_acquire() is None


@pytest.mark.parametrize("initial_error", ["start", "current_after_start", "result"])
@pytest.mark.parametrize("action", ["canonical_snapshot", "export_step"])
def test_cleanup_uncertainty_supersedes_earlier_error_without_releasing_lease(
    harness, monkeypatch, initial_error, action
):
    h = harness
    jobs, _ = port(h, monkeypatch, initial_error=initial_error, cancel_uncertain=True)
    calls = []

    def current():
        calls.append(True)
        if initial_error == "current_after_start" and len(calls) == 2:
            raise RuntimeError("earlier currentness error")
        return h.selection

    with pytest.raises(h.guarded.GuardedOperationError, match="restart Blender") as error:
        run(h, action, current)
    assert error.value.outcome_unknown is action.startswith("export_")
    assert h.lease._QUARANTINE[1] is jobs[0]
    assert h.lease.is_busy() and not jobs[0].done
    assert jobs[0].cancel_calls == 1
    assert not h.lease.release(jobs[0].token)


def test_unmanaged_busy_rejects_before_job_construction(harness, monkeypatch):
    h = harness
    jobs, _ = port(h, monkeypatch)
    token = h.lease.try_acquire()
    with pytest.raises(h.guarded.GuardedOperationError, match="Another CAD"):
        run(h)
    assert not jobs and h.lease._TOKEN is token
    assert h.lease.release(token)


def test_bound_transport_blocks_reentrant_execute_and_release(harness, monkeypatch):
    h = harness
    jobs, value = port(h, monkeypatch)
    calls = []

    def current():
        calls.append(True)
        assert not h.lease.release(h.lease._TOKEN)
        with pytest.raises(h.guarded.GuardedOperationError, match="Another CAD"):
            run(h)
        assert len(jobs) == 1
        return h.selection

    assert run(h, current=current) is value
    assert len(calls) == 2 and len(jobs) == 1 and not h.lease.is_busy()


def test_scopes_are_exact_main_thread_bounded_and_cannot_inherit_stale_token(harness):
    lease = harness.lease
    token = lease.try_acquire()
    with pytest.raises(lease.LeaseError):
        with lease.synchronous(object()):
            pytest.fail("wrong owner entered")
    with ThreadPoolExecutor(max_workers=1) as pool:

        def other_thread():
            with lease.synchronous(token):
                pytest.fail("worker entered main-thread scope")

        with pytest.raises(lease.LeaseError, match="main thread"):
            pool.submit(other_thread).result(5)
    with lease.synchronous(token):
        with pytest.raises(lease.LeaseError):
            with lease.synchronous(token):
                pytest.fail("nested scope entered")
        assert lease.release(token)
        with pytest.raises(lease.LeaseError):
            lease.bind_transport()
    assert not lease.is_busy()


def test_injected_token_mismatch_retains_original_owner_and_leaves_successor_unchanged(harness):
    lease = harness.lease
    original, owned = lease.bind_transport()
    owner, successor = object(), object()
    lease._TOKEN = successor  # Unsupported corruption, not a public release operation.
    assert not lease.quarantine(original, owner)
    assert lease._TOKEN is successor
    assert lease._QUARANTINE[0] is original and lease._QUARANTINE[1] is owner
    assert not lease.finish_transport(original, transport_owned=owned)
    assert not lease.release(original) and not lease.release(successor)
    assert lease.try_acquire() is None
    with pytest.raises(lease.LeaseError, match="restart Blender"):
        lease.bind_transport()
    assert not lease.quarantine(original, owner)  # Idempotent; no cleanup retry.


def test_real_worker_stop_event_wakes_uncertainty_without_cleanup_success(harness, monkeypatch):
    h = harness
    resources = object()
    calls = []

    def uncertain(job):
        calls.append(job)
        job._launched = True
        job._bundle_owner = resources
        job._cleanup_uncertain = True
        raise RuntimeError("injected bounded worker uncertainty")

    monkeypatch.setattr(h.managed.SidecarJob, "_exchange", uncertain)
    started = time.monotonic()
    with pytest.raises(h.guarded.GuardedOperationError, match="restart Blender") as error:
        run(h, "export_step")
    assert time.monotonic() - started < 2 and error.value.outcome_unknown
    original = h.lease._QUARANTINE[1]
    managed = original._job
    managed._worker.join(5)
    assert not managed._worker.is_alive() and managed._worker_stopped.is_set()
    assert not managed._finished.is_set() and not managed.done
    assert managed._bundle_owner is resources
    for _ in range(3):
        assert not managed.wait()  # No timeout; must return immediately, not spin.
        assert not managed.cancel()
        with pytest.raises(h.managed.bridge.BridgeError, match="not ready"):
            managed.result()
    assert calls == [managed]


@pytest.mark.parametrize("kind", ["sketch", "assembly"])
@pytest.mark.parametrize("prior", ["running", "cancelled", "stale"])
@pytest.mark.parametrize("observe", ["poll", "reap", "cancel", "cancel_all"])
def test_async_uncertainty_replaces_prior_reason_and_retains_exact_owner(
    harness, monkeypatch, kind, prior, observe
):
    h = harness
    token = h.lease.try_acquire()

    class Job:
        state = "running"
        done = False
        cleanup_diagnostic = ""
        calls = 0

        def cancel(self):
            self.calls += 1
            self.state = "cancelling"

        def wait(self, timeout=None):
            return False

        def poll(self, *args):
            return self.state

        def result(self, *args, **kwargs):
            pytest.fail("uncertain owner attempted result/publication")

    job = Job()
    if kind == "sketch":
        module = importlib.import_module(h.name + ".sketch_pending")
        pending = module.PendingSketch({"action": "replay"}, {}, job, token)
        module._ACTIVE[id(pending)] = pending
        if prior != "running":
            module._retire(pending, "Earlier " + prior, cancelled=prior == "cancelled")
            pending._notified = True
        context = None
    else:
        state = types.ModuleType(h.name + ".assembly_state")
        state._scenes = lambda: []
        state._key = lambda scene: 1
        state._BUSY = {1}
        state._RUNTIME = {}
        state._recover_report = lambda *a, **k: pytest.fail("uncertain owner recovered RNA")
        monkeypatch.setitem(sys.modules, state.__name__, state)
        module = importlib.import_module(h.name + ".assembly_pending")
        prepared = types.SimpleNamespace(
            operation_request=lambda: {
                "action": "assembly_check",
                "assembly": {"joints": [], "instances": []},
                "coordinates": None,
                "samples": None,
                "preset_id": None,
            }
        )
        transaction = {"key": 1, "snapshot": {"scene_key": 1, "window_key": 1}}
        pending = module.PendingReport(transaction, prepared, job, token)
        module._ACTIVE[1] = pending
        if prior != "running":
            module._abort(pending, ValueError("Earlier " + prior), cancelled=prior == "cancelled")
            pending._notified = True
        context = types.SimpleNamespace(scene=object())
    old_calls = job.calls
    job.state = "cleanup_uncertain"
    job.cleanup_diagnostic = h.lease.QUARANTINE_MESSAGE
    if observe == "poll":
        with pytest.raises(h.managed.bridge.BridgeError, match="restart Blender"):
            module.poll(pending, {}) if kind == "sketch" else module.poll(context, pending)
        again = module.poll(pending, {}) if kind == "sketch" else module.poll(context, pending)
        assert again is None
    elif observe == "reap":
        assert module.reap()
    elif observe == "cancel":
        module.cancel(pending, "Later cancellation")
    else:
        assert not module.cancel_all("Later disable", wait_timeout=0)
    assert pending._error == h.lease.QUARANTINE_MESSAGE
    assert pending._job is job and pending._lease_token is token
    assert pending in module._ACTIVE.values() and not pending.done
    assert h.lease._TOKEN is token and h.lease.is_busy()
    assert job.calls == old_calls
    assert module.reap()
    assert pending.status()["message"] == h.lease.QUARANTINE_MESSAGE
    assert not module.cancel_all("Later reenable", wait_timeout=0)
    assert pending._error == h.lease.QUARANTINE_MESSAGE
    assert h.lease.try_acquire() is None


def test_live_replay_guard_lends_and_preserves_its_existing_token(harness, monkeypatch):
    h = harness
    jobs, value = port(h, monkeypatch)
    resume_checks = []
    monkeypatch.setattr(
        sys.modules[h.name + ".staged_edit_store"],
        "require_no_resume",
        lambda: resume_checks.append("checked"),
    )
    namespace = {
        "__name__": h.name + ".document_state",
        "__package__": h.name,
        "contextmanager": contextmanager,
        "execution_lease": h.lease,
        "bridge": h.managed.bridge,
        "_REPLAY_RUNNING": False,
    }
    guard = function("document_state.py", "replay_guard", namespace)
    with guard(types.SimpleNamespace(mode="OBJECT")):
        token = h.lease._TOKEN
        assert run(h) is value
        assert jobs[0].token is token and h.lease._TOKEN is token
        assert namespace["_REPLAY_RUNNING"]
    assert not h.lease.is_busy() and not namespace["_REPLAY_RUNNING"]

    assert resume_checks == ["checked"]


def test_live_assembly_run_lends_and_releases_its_existing_token(harness, monkeypatch):
    h = harness
    jobs, value = port(h, monkeypatch)
    namespace = {
        "execution_lease": h.lease,
        "bridge": h.managed.bridge,
        "guarded_transport": h.guarded,
        "_preflight_assembly": lambda *a: None,
        "_current_selection": lambda *a: h.selection,
    }
    execute = function("assembly_state.py", "_run_sidecar", namespace)
    snapshot = {"prepared": request(h), "selection": h.selection, "owner_token": object()}
    assert execute(object(), snapshot=snapshot) is value
    assert len(jobs) == 1 and not h.lease.is_busy()


def test_live_canonical_capture_scope_wraps_only_existing_transport_and_releases_on_error(harness):
    h = harness
    calls = []

    class Expected(Exception):
        pass

    def canonical(*args, **kwargs):
        token, owned = h.lease.bind_transport()
        assert token is h.lease._TOKEN and not owned
        calls.append(token)
        assert h.lease.finish_transport(token, transport_owned=owned)
        raise Expected("after scoped transport")

    part = types.SimpleNamespace(document_json="{}", owner_id="owner")
    scene = types.SimpleNamespace(
        as_pointer=lambda: 1,
        mechanical_cad=part,
        mechanical_cad_assembly=types.SimpleNamespace(document_json="assembly"),
    )
    context = types.SimpleNamespace(scene=scene, window=None, view_layer=object())
    namespace = {
        "execution_lease": h.lease,
        "bridge": h.managed.bridge,
        "working_part": lambda context: {},
        "operation_contracts": types.SimpleNamespace(result_version_for=lambda *a, **k: None),
        "backend_runtime": types.SimpleNamespace(capture=lambda context: h.selection),
        "guarded_operations": types.SimpleNamespace(canonical_snapshot_guarded=canonical),
    }
    capture = function("assembly_operator_helpers.py", "canonical_working_part", namespace)
    with pytest.raises(Expected):
        capture(context)
    assert len(calls) == 1 and not h.lease.is_busy()


def test_dormant_service_rejects_bundled_before_validation_or_job_construction(
    harness, monkeypatch
):
    h = harness
    service = importlib.import_module(h.name + ".service_v3")
    selected = h.selection
    # Exact-class injected setup field suffices to test admission order; no real
    # bundle is selected or executed and there is no bypass flag in production.
    object.__setattr__(selected, "bundled_policy", object())
    monkeypatch.setattr(service.result_v3, "validate_request", lambda *a: pytest.fail("validated"))
    monkeypatch.setattr(service.SidecarJob, "from_selection", lambda *a: pytest.fail("constructed"))
    with pytest.raises(h.managed.bridge.BridgeError, match="dormant"):
        service.DataOnlyJob({}, selected, current_selection=lambda: selected)


def test_wrong_thread_cannot_borrow_main_scope_before_job_construction(harness, monkeypatch):
    h = harness
    jobs, _ = port(h, monkeypatch)
    token = h.lease.try_acquire()
    with h.lease.synchronous(token), ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(h.guarded.GuardedOperationError, match="Another CAD"):
            pool.submit(run, h).result(5)
        assert not jobs and h.lease._TOKEN is token and h.lease._BOUND_TOKEN is None
    assert h.lease.release(token)


def test_uncertainty_through_live_replay_guard_cannot_release_or_clear_gate(harness, monkeypatch):
    h = harness
    jobs, _ = port(h, monkeypatch, uncertain=True)
    resume_checks = []
    monkeypatch.setattr(
        sys.modules[h.name + ".staged_edit_store"],
        "require_no_resume",
        lambda: resume_checks.append("checked"),
    )
    namespace = {
        "__name__": h.name + ".document_state",
        "__package__": h.name,
        "contextmanager": contextmanager,
        "execution_lease": h.lease,
        "bridge": h.managed.bridge,
        "_REPLAY_RUNNING": False,
    }
    guard = function("document_state.py", "replay_guard", namespace)
    with pytest.raises(h.guarded.GuardedOperationError, match="restart Blender"):
        with guard(types.SimpleNamespace(mode="OBJECT")):
            run(h, "export_step")
    assert not namespace["_REPLAY_RUNNING"]
    assert h.lease._QUARANTINE[1] is jobs[0]
    assert h.lease.is_busy() and h.lease.try_acquire() is None

    assert resume_checks == ["checked"]


def test_uncertainty_through_live_assembly_scope_preserves_original_job(harness, monkeypatch):
    h = harness
    jobs, _ = port(h, monkeypatch, uncertain=True)
    namespace = {
        "execution_lease": h.lease,
        "bridge": h.managed.bridge,
        "guarded_transport": h.guarded,
        "_preflight_assembly": lambda *a: None,
        "_current_selection": lambda *a: h.selection,
    }
    execute = function("assembly_state.py", "_run_sidecar", namespace)
    snapshot = {"prepared": request(h), "selection": h.selection, "owner_token": object()}
    with pytest.raises(h.guarded.GuardedOperationError, match="restart Blender"):
        execute(object(), snapshot=snapshot)
    assert h.lease._QUARANTINE[1] is jobs[0]
    assert not h.lease.release(jobs[0].token)


@pytest.mark.parametrize("failure", [SystemExit, KeyboardInterrupt])
@pytest.mark.parametrize("action", ["canonical_snapshot", "export_step"])
def test_unexpected_baseexception_wakes_sync_retains_owner_and_blocks_successor(
    harness, monkeypatch, failure, action
):
    h = harness
    original_resources = object()
    calls = []

    def abrupt(job):
        calls.append(job)
        job._launched = True
        job._bundle_owner = original_resources
        raise failure("private unexpected worker details")

    monkeypatch.setattr(h.managed.SidecarJob, "_exchange", abrupt)
    started = time.monotonic()
    with pytest.raises(h.guarded.GuardedOperationError, match="Save your work") as error:
        run(h, action)
    assert time.monotonic() - started < 2
    assert "private unexpected worker details" not in str(error.value)
    assert error.value.outcome_unknown is action.startswith("export_")
    retained = h.lease._QUARANTINE[1]
    job = retained._job
    job._worker.join(5)
    assert not job._worker.is_alive() and job._worker_stopped.is_set()
    assert job.state == "cleanup_uncertain" and not job.done
    assert not job._finished.is_set() and not job.wait()
    assert job._bundle_owner is original_resources
    assert "Save your work" in retained.cleanup_diagnostic
    for _ in range(3):
        assert not job.cancel() and not job.wait()
        with pytest.raises(h.guarded.GuardedOperationError, match="restart Blender"):
            run(h, action)
    assert calls == [job]
    assert h.lease._QUARANTINE[1] is retained
    assert not h.lease.release(h.lease._TOKEN)


@pytest.mark.parametrize("failure", [SystemExit, KeyboardInterrupt])
@pytest.mark.parametrize("kind", ["sketch", "assembly"])
def test_unexpected_baseexception_updates_async_status_after_prior_cancel(
    harness, monkeypatch, failure, kind
):
    h = harness
    token = h.lease.try_acquire()
    resources = object()
    entered, proceed = threading.Event(), threading.Event()

    def abrupt(job):
        job._launched = True
        job._bundle_owner = resources
        entered.set()
        assert proceed.wait(5)
        raise failure("private worker details")

    monkeypatch.setattr(h.managed.SidecarJob, "_exchange", abrupt)
    job = h.guarded.GuardedJob(request(h), h.selection, owner_token=object())
    if kind == "sketch":
        module = importlib.import_module(h.name + ".sketch_pending")
        pending = module.PendingSketch({"action": "replay"}, {}, job, token)
        module._ACTIVE[id(pending)] = pending
    else:
        state = types.ModuleType(h.name + ".assembly_state")
        state._scenes = lambda: []
        state._key = lambda scene: 1
        state._BUSY = {1}
        state._RUNTIME = {}
        state._recover_report = lambda *a, **k: pytest.fail("uncertain owner recovered RNA")
        monkeypatch.setitem(sys.modules, state.__name__, state)
        module = importlib.import_module(h.name + ".assembly_pending")
        prepared = types.SimpleNamespace(
            operation_request=lambda: {
                "action": "assembly_check",
                "assembly": {"joints": [], "instances": []},
                "coordinates": None,
                "samples": None,
                "preset_id": None,
            }
        )
        pending = module.PendingReport(
            {"key": 1, "snapshot": {"scene_key": 1, "window_key": 1}},
            prepared,
            job,
            token,
        )
        module._ACTIVE[1] = pending
    job.start(h.selection)
    assert entered.wait(5)
    try:
        module.cancel(pending, "Earlier cancellation")
        pending._notified = True
    finally:
        proceed.set()
    job._job._worker.join(5)
    assert not job._job._worker.is_alive()
    assert not job.wait() and not job.done
    assert job.state == "cleanup_uncertain"
    assert module.reap()
    assert "Save your work" in pending.status()["message"]
    assert pending in module._ACTIVE.values() and pending._job is job
    assert pending._lease_token is token and h.lease._TOKEN is token
    assert job._job._bundle_owner is resources
    assert not module.cancel_all("Later lifecycle", wait_timeout=0)
    assert h.lease.try_acquire() is None
    with pytest.raises(h.guarded.GuardedOperationError, match="Another CAD"):
        run(h)
