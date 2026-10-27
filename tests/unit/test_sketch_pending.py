"""Pure exact-input adapter gates; synthetic CAD evidence is a protocol fixture.

Real subprocess tests use the existing SidecarJob with a trusted dummy sidecar,
assert actual child exit and tempfile cleanup, and never import native CAD/bpy.
"""

import ast
import copy
import importlib
import json
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
PACKAGE = "mcad_sketch_pending_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
p = importlib.import_module(PACKAGE + ".sketch_pending")
BridgeError = p.bridge.BridgeError
contracts = p.sketch_action_bridge.snapshots

LINUX_MANUAL_PROCESS = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux manual SidecarJob process and worker contract"
)


def request(action="solve_sketch"):
    document = {
        "schema_version": 2,
        "id": "part",
        "name": "Part",
        "units": "mm",
        "parameters": {},
        "features": [],
        "active_feature": None,
    }
    result = {"protocol_version": 1, "result_version": 2, "action": action, "document": document}
    if action == "solve_sketch":
        document["features"] = [
            {
                "id": "sketch",
                "kind": "sketch_constrained",
                "sketch": {
                    "schema_version": 2,
                    "id": "geometry",
                    "units": "mm",
                    "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
                    "points": [{"id": "center", "u": 0, "v": 0}],
                    "lines": [],
                    "circles": [{"id": "rim", "center": "center", "radius": 5}],
                    "constraints": [],
                },
            }
        ]
        document["active_feature"] = result["feature_id"] = "sketch"
    else:
        result["options"] = {"linear_deflection": 0.1}
    return result


def response_for(candidate):
    """A complete strict success fixture, not a claim that native solving ran."""
    canonical = contracts._expected_document(candidate["document"])
    response = {
        "protocol_version": 1,
        "result_version": 2,
        "input_fingerprint": contracts.input_fingerprint(candidate),
        "ok": True,
        "error": None,
    }
    result = {
        "document_id": canonical["id"],
        "document_hash": contracts.document_hash(canonical),
    }
    if candidate["action"] == "solve_sketch":
        response["action"] = "solve_sketch"
        result.update(
            feature_id="sketch",
            sketch={
                "solver": "libslvs",
                "solver_version": "3.2",
                "status": "okay",
                "remaining_dof": 3,
                "failed_constraints": [],
                "redundant_constraints": [],
                "max_residual_mm": 0.0,
                "solved": canonical["features"][0]["sketch"],
                "dimensions": {},
            },
            profile_check={"ready": True, "error": None},
        )
    else:
        result.update(
            result_version=2,
            active_feature=None,
            status="ok",
            units="mm",
            parameters={},
            features=[],
        )
    response["result"] = result
    return response


def identity():
    return {
        "session": "owner-1",
        "owner_generation": 3,
        "scene_pointer": 1234567,
        "window_pointer": 7654321,
        "base_json": '{"exact":1}\n',
        "base_hash": "base",
        "command_revision": 2,
        "input_revision": 5,
        "raw": "5 + invalid",
        "workspace": 234,
        "configuration": {"python": "/python", "deflection": 0.1, "timeout": 60.0},
    }


class ControlledJob:
    def __init__(self, candidate, **configuration):
        assert p.execution_lease.is_busy(), "acquire before constructing the transport"
        self.request = copy.deepcopy(candidate)
        self.configuration = copy.deepcopy(configuration)
        self.response = response_for(candidate)
        self.state = "created"
        self.cleaned = False
        self.result_calls = 0
        self.cancel_calls = 0
        self.wait_calls = []
        self.start_error = None
        self.poll_error = None
        self.result_error = None
        self.cancel_errors = 0
        self.done_errors = 0
        self.wait_error = None
        self.wait_cleanup = False

    @property
    def done(self):
        if self.done_errors:
            self.done_errors -= 1
            raise RuntimeError("injected done failure")
        return self.cleaned

    def start(self):
        assert p.execution_lease.is_busy()
        self.state = "running"
        if self.start_error:
            raise self.start_error
        return self

    def request_snapshot(self):
        return copy.deepcopy(self.request)

    def poll(self):
        if self.poll_error:
            raise self.poll_error
        return self.state

    def ready(self):
        self.state, self.cleaned = "ready", True

    def result(self):
        assert self.cleaned
        self.result_calls += 1
        assert self.result_calls == 1
        self.state = "consumed"
        if self.result_error:
            raise self.result_error
        return self.response

    def cancel(self):
        self.cancel_calls += 1
        if self.cancel_errors:
            self.cancel_errors -= 1
            raise RuntimeError("injected cancellation failure")
        self.state = "cancelled" if self.cleaned else "cancelling"

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        if self.wait_error:
            raise self.wait_error
        if self.wait_cleanup:
            self.cleaned, self.state = True, "cancelled"
        return self.cleaned


@pytest.fixture(autouse=True)
def no_leaked_work():
    assert not p._ACTIVE and not p.execution_lease.is_busy()
    yield
    active = list(p._ACTIVE.values())
    for pending in active:
        job = pending._job
        if type(job) is ControlledJob:
            job.cleaned = True
            job.cancel_errors = job.done_errors = 0
            job.wait_error = None
    assert p.cancel_all(wait_timeout=5)
    assert not p._ACTIVE and not p.execution_lease.is_busy()


@pytest.fixture
def jobs(monkeypatch):
    created = []

    def factory(*args, **kwargs):
        job = ControlledJob(*args, **kwargs)
        created.append(job)
        return job

    monkeypatch.setattr(p, "_JOB_FACTORY", factory)
    return created


@pytest.mark.parametrize("action", ["solve_sketch", "replay"])
def test_exact_valid_complete_response_detached_once_and_no_authoring_mutation(jobs, action):
    candidate, current = request(action), identity()
    before = copy.deepcopy((candidate, current))
    pending = p.prepare(candidate, current)
    assert not pending.done
    assert p.poll(pending, current) is None
    jobs[0].ready()
    assert p.reap() and jobs[0].result_calls == 0 and p.execution_lease.is_busy()
    accepted = p.poll(pending, current)
    assert accepted == response_for(candidate)
    assert accepted is not jobs[0].response
    assert (candidate, current) == before
    accepted["result"]["document_id"] = "caller edit"
    assert jobs[0].response["result"]["document_id"] == "part"
    assert pending.done and p.status(pending)["phase"] == "finished"
    assert p.poll(pending, current) is None
    assert not p.cancel(pending) and not p.reap() and not p.execution_lease.is_busy()
    assert jobs[0].result_calls == 1


def test_input_and_public_snapshot_mutations_cannot_change_captured_identity(jobs):
    candidate, current = request(), identity()
    original_request, original_identity = copy.deepcopy((candidate, current))
    pending = p.prepare(candidate, current)
    candidate["document"]["name"] = "Changed"
    current["configuration"]["python"] = "/changed"
    pending.request_snapshot()["document"]["name"] = "Accessor changed"
    pending.identity_snapshot()["configuration"]["python"] = "/accessor-changed"
    p.status(pending)["phase"] = "pretend finished"
    p.status().clear()
    assert pending.request_snapshot() == original_request
    assert pending.identity_snapshot() == original_identity
    assert p.status(pending)["phase"] == "running"
    jobs[0].ready()
    assert p.poll(pending, original_identity)["ok"]


@pytest.mark.parametrize("ready", [False, True])
@pytest.mark.parametrize("field", list(identity()))
def test_every_identity_change_cancels_before_result_consumption(jobs, ready, field):
    current = identity()
    pending = p.prepare(request(), current)
    if ready:
        jobs[0].ready()
    current[field] = "different"
    if ready:
        with pytest.raises(BridgeError, match="identity changed"):
            p.poll(pending, current)
    else:
        assert p.poll(pending, current) is None
        assert p.execution_lease.is_busy()
        assert p.status(pending)["cleanup_pending"]
        jobs[0].cleaned = True
        with pytest.raises(BridgeError, match="identity changed"):
            p.poll(pending, current)
    assert p.status(pending)["phase"] == "cancelled"
    assert not p.execution_lease.is_busy() and jobs[0].result_calls == 0
    assert p.poll(pending, current) is None


@pytest.mark.parametrize("old,new", [(True, 1), (1, 1.0), (0.0, -0.0), ("01", "1")])
def test_identity_comparison_preserves_exact_json_scalar_type_and_spelling(jobs, old, new):
    pending = p.prepare(request(), {"value": old})
    jobs[0].ready()
    with pytest.raises(BridgeError, match="identity changed"):
        p.poll(pending, {"value": new})
    assert jobs[0].result_calls == 0


def test_object_key_order_is_not_identity_but_array_order_is(jobs):
    pending = p.prepare(request(), {"a": 1, "b": [2, 3]})
    jobs[0].ready()
    assert p.poll(pending, {"b": [2, 3], "a": 1})["ok"]
    other = p.prepare(request(), {"a": 1, "b": [2, 3]})
    jobs[1].ready()
    with pytest.raises(BridgeError):
        p.poll(other, {"b": [3, 2], "a": 1})


@pytest.mark.parametrize("ready", [False, True])
def test_cancel_before_or_after_ready_never_consumes_and_holds_until_reaped(jobs, ready):
    pending = p.prepare(request(), identity())
    if ready:
        jobs[0].ready()
    assert p.cancel(pending, "User cancelled")
    assert not p.cancel(pending)
    assert jobs[0].result_calls == 0
    assert p.execution_lease.is_busy() is (not ready)
    if not ready:
        assert p.reap()
        jobs[0].cleaned = True
        assert not p.reap()
    assert p.status(pending)["phase"] == "cancelled"
    with pytest.raises(BridgeError, match="User cancelled"):
        p.poll(pending, identity())
    assert p.poll(pending, identity()) is None


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {"v": object()},
        {"v": lambda: None},
        {"v": RuntimeError("RNA")},
        {"v": (1, 2)},
        {1: "wrong key"},
        {"v": float("nan")},
        {"v": float("inf")},
        {"v": "x" * p.MAX_IDENTITY_BYTES},
        {"v": [0] * p.MAX_IDENTITY_NODES},
        {"v": 2**20000},
    ],
)
def test_identity_is_bounded_finite_plain_json_before_transport_construction(jobs, bad):
    with pytest.raises(BridgeError, match="identity"):
        p.prepare(request(), bad)
    assert not jobs and not p.execution_lease.is_busy()


def test_identity_depth_cycles_and_expanded_shared_nodes_are_rejected(jobs):
    nested = {}
    for _ in range(17):
        nested = {"child": nested}
    cycle = {}
    cycle["child"] = cycle
    shared = [0] * 40
    for bad in (nested, cycle, {"shared": [shared] * 103}):
        with pytest.raises(BridgeError, match="identity"):
            p.prepare(request(), bad)
    assert not jobs


def test_identity_limits_accept_exact_boundary_and_unicode_counts_escaped_bytes(jobs):
    # Default JSON encoding: {"v": "..."} is 9 bytes plus string contents.
    pending = p.prepare(request(), {"v": "x" * (p.MAX_IDENTITY_BYTES - 9)})
    assert len(json.dumps(pending.identity_snapshot())) == p.MAX_IDENTITY_BYTES
    jobs[0].ready()
    assert p.poll(pending, pending.identity_snapshot())["ok"]
    with pytest.raises(BridgeError, match="identity"):
        p.prepare(request(), {"v": "界" * (p.MAX_IDENTITY_BYTES // 6)})


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.pop("action"),
        lambda r: r.update(action="check_geometry"),
        lambda r: r.update(action="export_step"),
        lambda r: r.update(protocol_version=True),
        lambda r: r.update(result_version=True),
        lambda r: r.update(result_version=1),
        lambda r: r.pop("result_version"),
        lambda r: r.update(destination="/tmp/file"),
        lambda r: r.update(extra=True),
        lambda r: r.update(options={}),
        lambda r: r.update(document=[]),
        lambda r: r.update(feature_id=""),
        lambda r: r.update(feature_id=1),
        lambda r: r.pop("feature_id"),
    ],
)
def test_only_explicit_narrow_typed_requests_are_admitted(jobs, change):
    candidate = request()
    change(candidate)
    with pytest.raises(BridgeError):
        p.prepare(candidate, identity())
    assert not jobs and not p.execution_lease.is_busy()


@pytest.mark.parametrize("action", ["solve_sketch", "replay"])
@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(protocol_version=True),
        lambda r: r.update(result_version=1),
        lambda r: r.update(ok=1),
        lambda r: r.update(extra="unknown"),
        lambda r: r.update(input_fingerprint="wrong"),
        lambda r: r["result"].update(document_hash="wrong"),
        lambda r: r["result"].update(document_id="wrong"),
        lambda r: r.update(result=None),
        lambda r: r.update(error={"code": "x", "message": "x"}),
    ],
)
def test_real_strict_validators_reject_malformed_or_stale_response(jobs, action, change):
    pending = p.prepare(request(action), identity())
    change(jobs[0].response)
    jobs[0].ready()
    with pytest.raises(BridgeError):
        p.poll(pending, identity())
    assert p.status(pending)["phase"] == "failed"
    assert p.poll(pending, identity()) is None
    assert not p.execution_lease.is_busy() and jobs[0].result_calls == 1
    assert not any(isinstance(value, BaseException) for value in vars(pending).values())


@pytest.mark.parametrize("action", ["solve_sketch", "replay"])
def test_valid_failure_envelope_is_returned_for_current_diagnostics_only(jobs, action):
    pending = p.prepare(request(action), identity())
    error = {"code": "invalid_request", "message": "Invalid native request"}
    jobs[0].response = {
        "protocol_version": 1,
        "result_version": 2,
        "ok": False,
        "result": None,
        "error": error,
    }
    jobs[0].ready()
    accepted = p.poll(pending, identity())
    assert accepted["ok"] is False and accepted["error"] == error
    assert p.status(pending)["phase"] == "finished"


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_transport_request_exact_binding_rejects_type_coercion_before_consumption(jobs, value):
    candidate = request()
    candidate["document"]["parameters"] = {"n": 1}
    pending = p.prepare(candidate, identity())
    jobs[0].request["document"]["parameters"]["n"] = value
    jobs[0].ready()
    with pytest.raises(BridgeError, match="exact sketch transport request changed"):
        p.poll(pending, identity())
    assert jobs[0].result_calls == 0 and not p.execution_lease.is_busy()


def test_cross_lease_exclusion_and_stale_finalizer_cannot_release_newer_work(jobs):
    external = p.execution_lease.try_acquire()
    with pytest.raises(BridgeError, match="Another CAD operation"):
        p.prepare(request(), identity())
    assert not jobs
    assert p.execution_lease.release(external)
    old = p.prepare(request(), identity())
    old_token = old._lease_token
    assert p.execution_lease.try_acquire() is None
    with pytest.raises(BridgeError, match="Another CAD operation"):
        p.prepare(request(), identity())
    assert len(jobs) == 1
    jobs[0].ready()
    assert p.poll(old, identity())["ok"]
    new = p.prepare(request(), identity())
    assert not p.execution_lease.release(old_token)
    assert p._release(old) and p.execution_lease.is_busy()
    assert p.poll(old, identity()) is None and not p.cancel(old)
    assert p.reap() and jobs[1].result_calls == 0
    jobs[1].ready()
    assert p.poll(new, identity())["ok"]


@pytest.mark.parametrize(
    "configuration",
    [
        {"project_root": object()},
        {"python_executable": 12},
        {"timeout": True},
        {"timeout": "1"},
        {"timeout": float("nan")},
        {"timeout": float("inf")},
        {"timeout": 10**1000},
    ],
)
def test_invalid_configuration_releases_before_constructing(jobs, configuration):
    with pytest.raises(BridgeError):
        p.prepare(request(), identity(), **configuration)
    assert not jobs and not p.execution_lease.is_busy()


def test_constructor_failure_releases_and_start_failure_retains_until_cleanup(monkeypatch):
    def bad_constructor(*args, **kwargs):
        assert p.execution_lease.is_busy()
        raise RuntimeError("constructor failed")

    monkeypatch.setattr(p, "_JOB_FACTORY", bad_constructor)
    with pytest.raises(BridgeError, match="constructor failed"):
        p.prepare(request(), identity())
    assert not p.execution_lease.is_busy()
    created = []

    def bad_start(*args, **kwargs):
        job = ControlledJob(*args, **kwargs)
        job.start_error = RuntimeError("start failed after launch")
        created.append(job)
        return job

    monkeypatch.setattr(p, "_JOB_FACTORY", bad_start)
    with pytest.raises(BridgeError, match="start failed after launch"):
        p.prepare(request(), identity())
    assert p.execution_lease.is_busy() and p.reap()
    assert created[0].result_calls == 0
    assert p.status()[0]["cleanup_pending"]
    created[0].cleaned = True
    assert not p.reap() and not p.execution_lease.is_busy()


def test_poll_exception_cancel_failure_and_repeated_cleanup_are_safe(jobs):
    pending = p.prepare(request(), identity())
    jobs[0].poll_error = RuntimeError("poll failure")
    jobs[0].cancel_errors = 1
    with pytest.raises(BridgeError, match="poll failure.*Cancellation failed"):
        p.poll(pending, identity())
    assert p.execution_lease.is_busy() and p.reap()
    assert p.poll(pending, identity()) is None
    jobs[0].cleaned = True
    assert not p.reap() and not p.execution_lease.is_busy()
    assert p.poll(pending, identity()) is None
    assert jobs[0].result_calls == 0


def test_reap_never_consumes_ready_success_but_retires_failed_transport(jobs):
    pending = p.prepare(request(), identity())
    jobs[0].ready()
    for _ in range(5):
        assert p.reap()
    assert jobs[0].result_calls == 0 and p.execution_lease.is_busy()
    jobs[0].state = "failed"
    assert not p.reap() and not p.execution_lease.is_busy()
    assert jobs[0].result_calls == 0
    with pytest.raises(BridgeError, match="before acceptance"):
        p.poll(pending, identity())


def test_transport_error_raised_once_without_retaining_exception_tracebacks(jobs):
    pending = p.prepare(request(), identity())
    jobs[0].ready()
    jobs[0].state = "failed"
    jobs[0].result_error = RuntimeError("Native process failed")
    with pytest.raises(BridgeError, match="Native process failed"):
        p.poll(pending, identity())
    assert p.poll(pending, identity()) is None
    assert not any(isinstance(v, BaseException) for v in vars(pending).values())


def test_unconfirmed_cleanup_and_done_property_failure_never_release_lease(jobs):
    pending = p.prepare(request(), identity())
    jobs[0].state = "ready"
    assert p.poll(pending, identity()) is None
    assert p.execution_lease.is_busy() and jobs[0].result_calls == 0
    jobs[0].done_errors = 1
    assert p.poll(pending, identity()) is None
    assert p.status(pending)["cleanup_pending"]
    assert p.reap() and jobs[0].cancel_calls
    jobs[0].cleaned = True
    assert not p.reap()
    with pytest.raises(BridgeError, match="cleanup"):
        p.poll(pending, identity())


@pytest.mark.parametrize("wait_cleanup", [False, True])
def test_cancel_all_bounded_wait_and_cleanup_retention(jobs, wait_cleanup):
    pending = p.prepare(request(), identity())
    jobs[0].wait_cleanup = wait_cleanup
    assert p.cancel_all("Load invalidation", wait_timeout=0.02) is wait_cleanup
    assert 0 <= jobs[0].wait_calls[0] <= 0.02
    assert p.execution_lease.is_busy() is (not wait_cleanup)
    assert jobs[0].result_calls == 0
    if not wait_cleanup:
        assert p.status(pending)["cleanup_pending"]
        jobs[0].cleaned = True
        assert not p.reap()
    assert p.cancel_all(wait_timeout=0)


def test_cancel_all_wait_exception_retains_until_later_reap(jobs):
    pending = p.prepare(request(), identity())
    jobs[0].wait_error = RuntimeError("wait failed")
    assert not p.cancel_all(wait_timeout=0)
    assert p.execution_lease.is_busy() and "wait failed" in p.status(pending)["message"]
    jobs[0].cleaned = True
    assert not p.reap() and not p.execution_lease.is_busy()


def test_every_public_entry_and_handle_accessor_is_main_thread_only(jobs):
    pending = p.prepare(request(), identity())
    calls = [
        lambda: p.prepare(request(), identity()),
        lambda: p.poll(pending, identity()),
        lambda: p.cancel(pending),
        p.reap,
        p.cancel_all,
        p.status,
        lambda: p.status(pending),
        pending.request_snapshot,
        pending.identity_snapshot,
        pending.status,
        lambda: pending.done,
    ]
    failures = []

    def off_thread():
        for call in calls:
            try:
                call()
            except BridgeError as exc:
                failures.append(str(exc))

    thread = threading.Thread(target=off_thread)
    thread.start()
    thread.join(5)
    assert not thread.is_alive() and len(failures) == len(calls)
    assert all("main thread" in message for message in failures)
    assert jobs[0].result_calls == jobs[0].cancel_calls == 0


def test_import_is_native_free_and_module_has_no_timers_or_handlers():
    code = f"""
import builtins, importlib, sys, types
old = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}:
        raise AssertionError('forbidden import: ' + name)
    return old(name, *args, **kwargs)
builtins.__import__ = guarded
package = types.ModuleType('isolated_sketch_pending')
package.__path__ = [{str(ADDON)!r}]
sys.modules[package.__name__] = package
module = importlib.import_module(package.__name__ + '.sketch_pending')
assert callable(module.prepare) and module.status() == []
"""
    process = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    tree = ast.parse((ADDON / "sketch_pending.py").read_text(encoding="utf-8"))
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {"timers", "handlers", "bpy", "RNA"}


@pytest.fixture
def real_configuration(tmp_path):
    module = tmp_path / "src/mechanical_cad"
    module.mkdir(parents=True)
    (module / "__init__.py").write_text("")
    (module / "sidecar.py").write_text(
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        "json.load(sys.stdin)\n"
        "Path('started').write_text(str(os.getpid()))\n"
        "if Path('sleep').exists(): time.sleep(30)\n"
        "sys.stdout.write(Path('response.json').read_text())\n"
    )
    (tmp_path / "response.json").write_text(json.dumps(response_for(request())))
    return {"project_root": str(tmp_path), "python_executable": sys.executable}


@pytest.fixture
def real_resources(monkeypatch):
    processes, files = [], []
    popen, temporary = p.sidecar_job.subprocess.Popen, p.sidecar_job.tempfile.TemporaryFile

    def launch(*args, **kwargs):
        result = popen(*args, **kwargs)
        processes.append(result)
        return result

    def tempfile(*args, **kwargs):
        result = temporary(*args, **kwargs)
        files.append(result)
        return result

    monkeypatch.setattr(p.sidecar_job.subprocess, "Popen", launch)
    monkeypatch.setattr(p.sidecar_job.tempfile, "TemporaryFile", tempfile)
    yield processes, files
    for process in processes:
        if process.poll() is None:
            process.kill()
            process.wait(5)
            pytest.fail("actual child was left running")
    assert all(file.closed for file in files)


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "condition was not reached"
        time.sleep(0.005)


@LINUX_MANUAL_PROCESS
def test_real_sidecar_delivers_validated_solve_only_after_actual_cleanup(
    real_configuration,
    real_resources,
):
    pending = p.prepare(request(), identity(), **real_configuration)
    assert pending._job.wait(5)
    assert all(process.returncode is not None for process in real_resources[0])
    assert all(file.closed for file in real_resources[1])
    assert p.reap() and pending._job.state == "ready"
    assert p.poll(pending, identity())["ok"]
    assert pending._job.state == "consumed" and not p.execution_lease.is_busy()


@pytest.mark.parametrize("ready", [False, True])
@LINUX_MANUAL_PROCESS
def test_real_sidecar_late_identity_and_sleeping_child_cancel_without_consumption(
    real_configuration,
    real_resources,
    ready,
):
    root = Path(real_configuration["project_root"])
    if not ready:
        (root / "sleep").touch()
    pending = p.prepare(request(), identity(), **real_configuration)
    wait_until(lambda: (root / "started").exists())
    if ready:
        assert pending._job.wait(5)
    changed = identity()
    changed["input_revision"] += 1
    try:
        assert p.poll(pending, changed) is None
    except BridgeError:
        assert pending.done
    assert p.cancel_all("Lifecycle cleanup", wait_timeout=5)
    assert pending._job.state == "cancelled"
    assert real_resources[0] and all(proc.returncode is not None for proc in real_resources[0])
    assert all(file.closed for file in real_resources[1])
    assert not p.execution_lease.is_busy()


@LINUX_MANUAL_PROCESS
def test_real_invalid_configuration_releases_execution_lease(tmp_path):
    with pytest.raises(BridgeError, match="Project Root"):
        p.prepare(
            request(), identity(), project_root=str(tmp_path), python_executable=sys.executable
        )
    assert not p.execution_lease.is_busy() and not p.status()


@pytest.mark.skipif(sys.platform != "win32", reason="Actual Windows legacy admission order")
def test_windows_legacy_admission_releases_lease_before_configuration_or_io(tmp_path, monkeypatch):
    assert os.name == "nt" and p.sidecar_job.sys is sys and p.sidecar_job.os is os
    assert p._JOB_FACTORY is p.sidecar_job.SidecarJob
    assert not p._ACTIVE and not p.status() and not p.execution_lease.is_busy()
    events, acquired, released = [], [], []
    acquire, release = p.execution_lease.try_acquire, p.execution_lease.release

    def tracked_acquire():
        token = acquire()
        assert token is not None and p.execution_lease.is_busy()
        acquired.append(token)
        return token

    def tracked_release(token):
        assert p.execution_lease.is_busy()
        result = release(token)
        released.append(token)
        return result

    def forbidden(*args, **kwargs):
        events.append("unexpected configuration, IO or worker")
        raise AssertionError(events[-1])

    monkeypatch.setattr(p.execution_lease, "try_acquire", tracked_acquire)
    monkeypatch.setattr(p.execution_lease, "release", tracked_release)
    monkeypatch.setattr(p.bridge, "resolve_configuration", forbidden)
    monkeypatch.setattr(p.bridge, "Path", forbidden)
    monkeypatch.setattr(p.bridge, "subprocess", types.SimpleNamespace(run=forbidden))
    monkeypatch.setattr(p.sidecar_job, "Path", forbidden)
    monkeypatch.setattr(p.sidecar_job.SidecarJob, "_initialize", forbidden)
    monkeypatch.setattr(p.sidecar_job, "subprocess", types.SimpleNamespace(Popen=forbidden))
    monkeypatch.setattr(p.sidecar_job, "tempfile", types.SimpleNamespace(TemporaryFile=forbidden))
    monkeypatch.setattr(
        p.sidecar_job,
        "threading",
        types.SimpleNamespace(Thread=forbidden, Lock=forbidden, Event=forbidden),
    )
    with pytest.raises(BridgeError, match="Windows backend execution is not yet qualified"):
        p.prepare(
            request(), identity(), project_root=str(tmp_path), python_executable=sys.executable
        )
    assert len(acquired) == len(released) == 1 and acquired[0] is released[0]
    assert events == []
    assert not p._ACTIVE and not p.status() and not p.execution_lease.is_busy()


@pytest.mark.parametrize("bad", [None, {"live": object()}, {"v": float("nan")}])
def test_invalid_current_identity_revokes_ready_result_without_consumption(jobs, bad):
    pending = p.prepare(request(), identity())
    jobs[0].ready()
    with pytest.raises(BridgeError, match="identity"):
        p.poll(pending, bad)
    assert jobs[0].result_calls == 0 and pending.done
    assert p.status(pending)["phase"] == "cancelled"


@pytest.mark.parametrize("bad", [None, True, "1", float("nan"), float("inf"), 10**1000])
def test_invalid_cleanup_timeout_does_not_change_existing_operation(jobs, bad):
    pending = p.prepare(request(), identity())
    with pytest.raises(BridgeError, match="timeout"):
        p.cancel_all(wait_timeout=bad)
    assert not pending.done and jobs[0].cancel_calls == 0
    assert p.execution_lease.is_busy()


def test_spontaneous_transport_cancellation_reports_once_without_consumption(jobs):
    pending = p.prepare(request(), identity())
    jobs[0].state, jobs[0].cleaned = "cancelled", True
    with pytest.raises(BridgeError, match="cancelled"):
        p.poll(pending, identity())
    assert p.poll(pending, identity()) is None
    assert jobs[0].result_calls == 0 and not p.execution_lease.is_busy()


@LINUX_MANUAL_PROCESS
def test_thread_start_failure_real_transport_is_reaped_before_release(
    monkeypatch,
    real_configuration,
    real_resources,
):
    def fail_start(self):
        raise RuntimeError("worker launch failure")

    monkeypatch.setattr(p.sidecar_job.threading.Thread, "start", fail_start)
    pending = p.prepare(request(), identity(), **real_configuration)
    assert pending._job.done and p.execution_lease.is_busy()
    with pytest.raises(BridgeError, match="worker launch failure"):
        p.poll(pending, identity())
    assert not p.execution_lease.is_busy() and not real_resources[0] and not real_resources[1]


@pytest.mark.parametrize("action", ["solve_sketch", "replay"])
@LINUX_MANUAL_PROCESS
def test_real_repository_sidecar_passes_existing_strict_boundary(action, real_resources):
    # Optional native dependency discovery does not import it into this process.
    dependency = "slvs" if action == "solve_sketch" else "OCP"
    if importlib.util.find_spec(dependency) is None:
        pytest.skip("The repository sidecar native dependency is not installed")
    pending = p.prepare(
        request(action),
        identity(),
        project_root=str(ROOT),
        python_executable=sys.executable,
    )
    assert pending._job.wait(15)
    accepted = p.poll(pending, identity())
    assert accepted["ok"] is True
    if action == "solve_sketch":
        assert accepted["result"]["sketch"]["solver"] == "libslvs"
        assert accepted["result"]["sketch"]["remaining_dof"] == 3
    else:
        assert accepted["result"]["status"] == "ok"
    assert not p.execution_lease.is_busy()
    assert real_resources[0] and all(proc.returncode == 0 for proc in real_resources[0])
    assert all(file.closed for file in real_resources[1])
