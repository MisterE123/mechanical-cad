"""Real-process transport tests with a trusted dummy module, no native CAD/bpy."""

import ast
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
PACKAGE = "mcad_sidecar_job_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(PACKAGE + ".sidecar_job", ADDON / "sidecar_job.py")
transport = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = transport
spec.loader.exec_module(transport)
BridgeError = transport.bridge.BridgeError

DUMMY_SIDECAR = """
import json
import os
import sys
import time
from pathlib import Path

request = json.load(sys.stdin)
Path('started').write_text(str(os.getpid()), encoding='ascii')
mode = request.get('mode', 'success')
if mode == 'sleep':
    time.sleep(30)
elif mode in ('stdout_overflow', 'stderr_overflow'):
    stream = sys.stdout.buffer if mode == 'stdout_overflow' else sys.stderr.buffer
    stream.write(b'x' * request['bytes'])
    stream.flush()
    time.sleep(30)
elif mode == 'invalid':
    sys.stdout.write(request.get('raw', 'not JSON'))
    sys.stderr.write(request.get('stderr', 'native crash'))
    sys.exit(request.get('exit', 2))
elif mode == 'raw':
    sys.stdout.write(request['raw'])
    sys.exit(request.get('exit', 0))
response = request.get('response', {
    'protocol_version': 1,
    'ok': True,
    'echo': request,
    'environment': {
        key: os.environ.get(key)
        for key in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONNOUSERSITE', 'PYTHONIOENCODING')
    },
    'cwd': os.getcwd(),
})
json.dump(response, sys.stdout, allow_nan=False)
Path('completed').write_text('yes', encoding='ascii')
sys.exit(request.get('exit', 0))
"""


@pytest.fixture
def configuration(tmp_path):
    module = tmp_path / "src/mechanical_cad"
    module.mkdir(parents=True)
    (module / "__init__.py").write_text("", encoding="utf-8")
    (module / "sidecar.py").write_text(DUMMY_SIDECAR, encoding="utf-8")
    return {"project_root": str(tmp_path), "python_executable": sys.executable}


@pytest.fixture
def resources(monkeypatch):
    """Verify every process is reaped and every tempfile closes, even on error."""
    processes, files, arguments = [], [], []
    popen, temporary_file = transport.subprocess.Popen, transport.tempfile.TemporaryFile

    def launch(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        arguments.append((args, kwargs))
        return process

    def opened(*args, **kwargs):
        file = temporary_file(*args, **kwargs)
        files.append(file)
        return file

    monkeypatch.setattr(transport.subprocess, "Popen", launch)
    monkeypatch.setattr(transport.tempfile, "TemporaryFile", opened)
    yield processes, files, arguments
    for process in processes:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
            pytest.fail("sidecar process was left running")
    assert all(file.closed for file in files)


def finished(job, expected="ready"):
    assert job.wait(5), "job did not finish and clean up"
    assert job.done
    assert job.poll() == expected
    return job


def wait_until(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, "condition was not reached"
        time.sleep(0.005)


def started(configuration):
    path = Path(configuration["project_root"]) / "started"
    wait_until(path.exists)


def test_explicit_start_exact_snapshot_and_single_consumption(configuration, resources):
    request = {"action": "assembly_check", "document": {"dimensions": [2.5, 3], "name": "板"}}
    expected = json.loads(json.dumps(request))
    job = transport.SidecarJob(request, **configuration)
    assert job.state == "created"
    assert job.poll() == "created"
    assert not job.done
    assert not job.wait(0)
    assert resources[0] == []
    with pytest.raises(BridgeError, match="not ready"):
        job.result()
    request["document"]["dimensions"][0] = 999
    request["action"] = "export_step"
    detached = job.request_snapshot()
    detached["document"]["dimensions"].append(123)
    assert job.request_snapshot() == expected
    assert job.start() is job
    response = finished(job).result()
    assert response["echo"] == expected
    assert job.state == "consumed"
    assert job.done
    assert job.cancel() is False
    with pytest.raises(BridgeError, match="already been consumed"):
        job.result()
    with pytest.raises(BridgeError, match="only be started once"):
        job.start()
    assert job.request_snapshot() == expected


def test_safe_command_and_environment_isolation(monkeypatch, configuration, resources):
    monkeypatch.setenv("PYTHONHOME", "/wrong/blender/python")
    monkeypatch.setenv("PYTHONPATH", "/wrong/source")
    job = transport.SidecarJob({}, **configuration)
    result = finished(job.start()).result()
    args, kwargs = resources[2][0]
    assert args[0] == [sys.executable, "-m", "mechanical_cad.sidecar"]
    assert not kwargs.get("shell", False)
    assert kwargs["close_fds"] is True
    assert result["environment"] == {
        "PYTHONHOME": None,
        "PYTHONPATH": str(Path(configuration["project_root"]) / "src"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    assert result["cwd"] == configuration["project_root"]


@pytest.mark.parametrize(
    "invalid_request",
    [
        {"v": float("nan")},
        {"v": float("inf")},
        {"v": object()},
        {"v": (1, 2)},
        {1: "coerced key"},
        [],
    ],
)
def test_nonfinite_or_nonexact_json_rejected_before_launch(
    invalid_request, configuration, resources
):
    with pytest.raises(BridgeError, match="finite JSON"):
        transport.SidecarJob(invalid_request, **configuration)
    assert resources[0] == []


def test_cyclic_request_rejected_before_launch(configuration, resources):
    request = {}
    request["cycle"] = request
    with pytest.raises(BridgeError, match="finite JSON"):
        transport.SidecarJob(request, **configuration)
    assert resources[0] == []


def test_oversized_request_rejected_before_launch(monkeypatch, configuration, resources):
    monkeypatch.setattr(transport, "MAX_DOCUMENT_BYTES", 128)
    with pytest.raises(BridgeError, match="2 MiB input limit"):
        transport.SidecarJob({"value": "x" * 129}, **configuration)
    assert resources[0] == []


@pytest.mark.parametrize("case", ["shared_dag", "cycle", "string", "integer"])
def test_resource_preflight_runs_before_full_json_encoding(monkeypatch, configuration, case):
    if case == "shared_dag":
        value = [0]
        for _ in range(32):
            value = [value, value]
    elif case == "cycle":
        value = []
        value.append(value)
    elif case == "string":
        value = "x" * (transport.MAX_DOCUMENT_BYTES + 1)
    else:
        value = 1 << (transport.MAX_INTEGER_BITS + 1)

    def must_not_encode(*args, **kwargs):
        pytest.fail("unbounded input reached full JSON encoding")

    monkeypatch.setattr(transport.json, "dumps", must_not_encode)
    with pytest.raises(BridgeError):
        transport.SidecarJob({"value": value}, **configuration)


@pytest.mark.parametrize(
    "value",
    [
        "".join(chr(number) for number in range(128)),
        "板\u007f\u0080\u0100\uffff\ud800\udfff\U0001f9ca\U0010ffff",
        [True, False, None, 0, -1, 1 << 512, 0.0, -0.0, 1.2e100, 1.2e-100, 0.0000012],
        {"": [], 'a\\"\t板': {"nested": [[], {}, ""]}},
    ],
)
def test_preflight_size_matches_exact_default_json_bytes(monkeypatch, configuration, value):
    request = {"value": value}
    expected = json.dumps(request, allow_nan=False).encode("utf-8")
    monkeypatch.setattr(transport, "MAX_DOCUMENT_BYTES", len(expected))
    job = transport.SidecarJob(request, **configuration)
    assert job._payload == expected
    monkeypatch.setattr(transport, "MAX_DOCUMENT_BYTES", len(expected) - 1)
    with pytest.raises(BridgeError, match="2 MiB input limit"):
        transport.SidecarJob(request, **configuration)


def test_benign_shared_containers_are_detached_without_changing_wire_bytes(configuration):
    shared = {"coordinates": [1.5, 2.5, None], "label": "板"}
    request = {"left": shared, "right": shared, "list": [shared, shared]}
    expected = json.dumps(request, allow_nan=False).encode("utf-8")
    snapshot = transport.snapshot_request(request)
    job = transport.SidecarJob(request, **configuration)
    assert snapshot == request
    assert snapshot["left"] is not shared
    assert snapshot["left"]["coordinates"] is not shared["coordinates"]
    assert job._payload == expected
    shared["coordinates"].append(999)
    assert json.dumps(snapshot, allow_nan=False).encode("utf-8") == expected
    assert job.request_snapshot() == snapshot


def test_preflight_detaches_before_the_final_encoder_runs(monkeypatch, configuration):
    request = {"values": [1, 2, 3]}
    encode = transport.json.dumps
    expected = encode(request, allow_nan=False).encode("utf-8")

    def mutate_caller_then_encode(snapshot, **kwargs):
        value = [0]
        for _ in range(32):
            value = [value, value]
        request["values"] = value
        return encode(snapshot, **kwargs)

    monkeypatch.setattr(transport.json, "dumps", mutate_caller_then_encode)
    assert transport.SidecarJob(request, **configuration)._payload == expected


def test_node_limit_counts_the_expansion_of_shared_containers(monkeypatch):
    monkeypatch.setattr(transport, "MAX_REQUEST_NODES", 8)
    shared = [0, 1]
    with pytest.raises(BridgeError, match="JSON node limit"):
        transport.snapshot_request({"first": shared, "second": shared, "third": shared})


def test_cached_subtree_height_is_checked_at_every_reference(monkeypatch):
    monkeypatch.setattr(transport, "MAX_REQUEST_DEPTH", 3)
    shared = {"a": {"b": 0}}
    assert transport.snapshot_request({"first": shared}) == {"first": shared}
    with pytest.raises(BridgeError, match="JSON nesting limit"):
        transport.snapshot_request({"first": shared, "second": {"deeper": shared}})


@pytest.mark.skipif(os.name == "nt", reason="resource limits require POSIX")
@pytest.mark.parametrize(
    "case",
    ["shared_dag", "cycle", "string", "integer", "depth", "shared_large_keys", "ordinary_shared"],
)
def test_adversarial_input_preflight_in_time_and_memory_capped_process(configuration, case):
    # If a regression expands the DAG, converts the giant integer, or recursively
    # follows a cycle, only this child can exhaust its 256 MiB / 2 CPU seconds.
    # The parent also imposes a wall-time limit and reaps a timed-out child.
    script = textwrap.dedent(
        f"""
        import importlib
        import json
        import resource
        import sys
        import types

        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (2, 3))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        sys.set_int_max_str_digits(0)
        package = types.ModuleType('bounded_job_test')
        package.__path__ = [{str(ADDON)!r}]
        sys.modules[package.__name__] = package
        transport = importlib.import_module('bounded_job_test.sidecar_job')
        case = {case!r}
        if case == 'shared_dag':
            value = [0]
            for _ in range(32):
                value = [value, value]
        elif case == 'cycle':
            value = {{}}
            value['cycle'] = value
        elif case == 'string':
            value = 'x' * (transport.MAX_DOCUMENT_BYTES + 1)
        elif case == 'integer':
            value = 1 << (transport.MAX_INTEGER_BITS * 4096)
        elif case == 'depth':
            value = 0
            for _ in range(200):
                value = [value]
        elif case == 'shared_large_keys':
            key = 'x' * (transport.MAX_DOCUMENT_BYTES // 2)
            value = 0
            for _ in range(60):
                value = {{key: value}}
        else:
            shared = {{'coordinates': [1.5, 2.5, None], 'label': '板'}}
            value = {{'left': shared, 'right': shared, 'list': [shared, shared]}}
        request = {{'value': value}}
        try:
            job = transport.SidecarJob(request, **{configuration!r})
        except transport.bridge.BridgeError:
            assert case != 'ordinary_shared'
            print('BOUNDED_REJECTION')
        else:
            assert case == 'ordinary_shared'
            assert job.state == 'created'
            assert job._payload == json.dumps(request, allow_nan=False).encode('utf-8')
            assert job.request_snapshot() == request
            print('EXACT_SHARED_SNAPSHOT')
        """
    )
    process = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=5, check=False
    )
    assert process.returncode == 0, process.stderr
    expected = "EXACT_SHARED_SNAPSHOT" if case == "ordinary_shared" else "BOUNDED_REJECTION"
    assert process.stdout.strip() == expected


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), None, "invalid"])
def test_invalid_timeout_is_actionable(timeout, configuration):
    with pytest.raises(BridgeError, match="Invalid sidecar timeout"):
        transport.SidecarJob({}, timeout=timeout, **configuration)


@pytest.mark.parametrize(
    "response,exit_code,message",
    [
        ([], 0, "protocol mismatch"),
        ({"protocol_version": 2, "ok": True}, 0, "protocol mismatch"),
        ({"protocol_version": True, "ok": True}, 0, "protocol mismatch"),
        ({"protocol_version": 1.0, "ok": True}, 0, "protocol mismatch"),
        ({"protocol_version": "1", "ok": True}, 0, "protocol mismatch"),
        ({"protocol_version": 1}, 0, "success flag"),
        ({"protocol_version": 1, "ok": "yes"}, 0, "success flag"),
        ({"protocol_version": 1, "ok": True}, 7, "despite reporting success"),
    ],
)
def test_common_protocol_fails_closed(response, exit_code, message, configuration, resources):
    job = transport.SidecarJob({"response": response, "exit": exit_code}, **configuration)
    finished(job.start(), "failed")
    with pytest.raises(BridgeError, match=message):
        job.result()
    assert job.state == "consumed"
    with pytest.raises(BridgeError, match="already been consumed"):
        job.result()


def test_valid_cad_failure_envelope_remains_available(configuration, resources):
    response = {
        "protocol_version": 1,
        "ok": False,
        "result": None,
        "error": {"code": "bad_model", "message": "Invalid model"},
    }
    job = transport.SidecarJob({"response": response, "exit": 1}, **configuration)
    assert finished(job.start()).result() == response


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        '{"protocol_version":1,"ok":true,"ok":false}',
        '{"protocol_version":1,"ok":true,"v":NaN}',
        '{"protocol_version":1,"ok":true,"v":1e999}',
        "",
    ],
)
def test_invalid_response_json(raw, configuration, resources):
    job = transport.SidecarJob({"mode": "invalid", "raw": raw}, **configuration)
    finished(job.start(), "failed")
    with pytest.raises(BridgeError, match=r"invalid JSON \(exit 2\).*native crash"):
        job.result()


def test_stderr_diagnostic_is_bounded(configuration, resources):
    job = transport.SidecarJob(
        {"mode": "invalid", "stderr": "private-prefix" + "x" * 4096 + "TAIL"}, **configuration
    )
    finished(job.start(), "failed")
    with pytest.raises(BridgeError) as error:
        job.result()
    assert str(error.value).endswith("TAIL")
    assert "private-prefix" not in str(error.value)
    assert len(str(error.value)) < transport.MAX_DIAGNOSTIC_CHARS + 100


def test_timeout_kills_and_reaps_its_process(configuration, resources):
    job = transport.SidecarJob({"mode": "sleep"}, timeout=0.01, **configuration)
    assert job._timeout == 1.0  # Match the synchronous bridge's lower clamp.
    finished(job.start(), "failed")
    with pytest.raises(BridgeError, match="timed out"):
        job.result()
    assert resources[0][0].returncode is not None
    assert not (Path(configuration["project_root"]) / "completed").exists()


def test_cancel_before_start_never_launches(configuration, resources):
    job = transport.SidecarJob({}, **configuration)
    assert job.cancel() is True
    assert job.cancel() is False
    assert job.start() is job
    finished(job, "cancelled")
    with pytest.raises(BridgeError, match="cancelled before") as error:
        job.result()
    assert error.value.outcome_unknown is False
    assert not resources[0]
    assert not resources[1]


def test_cancel_during_run_is_nonblocking_and_reaped(configuration, resources):
    job = transport.SidecarJob({"mode": "sleep"}, **configuration).start()
    started(configuration)
    before = time.monotonic()
    assert job.cancel() is True
    assert time.monotonic() - before < 0.5
    assert job.state in {"cancelling", "cancelled"}
    finished(job, "cancelled")
    assert job.cancel() is False
    with pytest.raises(BridgeError, match="cancelled"):
        job.result()
    assert resources[0][0].returncode is not None
    assert all(file.closed for file in resources[1])


def test_cancel_ready_response_wins_before_consumption(configuration, resources):
    job = finished(transport.SidecarJob({}, **configuration).start())
    assert resources[0][0].returncode == 0
    assert all(file.closed for file in resources[1])
    assert job.cancel() is True
    assert job.state == "cancelled"
    with pytest.raises(BridgeError, match="cancelled"):
        job.result()
    assert job._response is None


def test_cancel_during_validation_prevents_late_publication(monkeypatch, configuration, resources):
    entered, resume = threading.Event(), threading.Event()
    original = transport.SidecarJob._read_response

    def paused(self, *args):
        entered.set()
        assert resume.wait(5)
        return original(self, *args)

    monkeypatch.setattr(transport.SidecarJob, "_read_response", paused)
    job = transport.SidecarJob({}, **configuration).start()
    try:
        assert entered.wait(5)
        assert resources[0][0].returncode == 0
        assert job.cancel() is True
        assert job.state == "cancelling"
        assert not job.done
        assert not job.wait(0.01)
        with pytest.raises(BridgeError, match="not ready"):
            job.result()
    finally:
        resume.set()
    finished(job, "cancelled")
    with pytest.raises(BridgeError, match="cancelled"):
        job.result()
    assert job._response is None


def test_cancel_during_process_launch_prevents_late_publication(
    monkeypatch, configuration, resources
):
    entered, resume = threading.Event(), threading.Event()
    launch = transport.subprocess.Popen

    def paused(*args, **kwargs):
        entered.set()
        assert resume.wait(5)
        return launch(*args, **kwargs)

    monkeypatch.setattr(transport.subprocess, "Popen", paused)
    job = transport.SidecarJob({}, **configuration).start()
    try:
        assert entered.wait(5)
        assert job.cancel() is True
        assert job.state == "cancelling"
    finally:
        resume.set()
    finished(job, "cancelled")
    with pytest.raises(BridgeError, match="cancelled"):
        job.result()
    assert resources[0][0].returncode is not None


def test_concurrent_start_and_cancel_always_leave_cancelled_job(configuration, resources):
    for _ in range(12):
        job = transport.SidecarJob({}, **configuration)
        gate = threading.Barrier(3)
        failures = []

        def start(gate=gate, job=job, failures=failures):
            try:
                gate.wait(5)
                job.start()
            except Exception as exc:
                failures.append(exc)

        def cancel(gate=gate, job=job, failures=failures):
            try:
                gate.wait(5)
                assert job.cancel()
            except Exception as exc:
                failures.append(exc)

        callers = [threading.Thread(target=start), threading.Thread(target=cancel)]
        for caller in callers:
            caller.start()
        gate.wait(5)
        for caller in callers:
            caller.join(5)
            assert not caller.is_alive()
        assert not failures
        finished(job, "cancelled")
        with pytest.raises(BridgeError, match="cancelled"):
            job.result()


def test_ready_result_and_cancellation_have_one_atomic_winner(configuration, resources):
    for _ in range(12):
        job = finished(transport.SidecarJob({}, **configuration).start())
        gate = threading.Barrier(3)
        outcomes = {}

        def consume(gate=gate, job=job, outcomes=outcomes):
            gate.wait(5)
            try:
                outcomes["response"] = job.result()
            except BridgeError as error:
                outcomes["error"] = error

        def cancel(gate=gate, job=job, outcomes=outcomes):
            gate.wait(5)
            outcomes["cancelled"] = job.cancel()

        callers = [threading.Thread(target=consume), threading.Thread(target=cancel)]
        for caller in callers:
            caller.start()
        gate.wait(5)
        for caller in callers:
            caller.join(5)
            assert not caller.is_alive()
        assert job.state == "consumed"
        if outcomes["cancelled"]:
            assert "response" not in outcomes
            assert "cancelled" in str(outcomes["error"])
        else:
            assert outcomes["response"]["ok"] is True
            assert "error" not in outcomes


@pytest.mark.parametrize(
    "mode,constant,message",
    [
        ("stdout_overflow", "MAX_RESPONSE_BYTES", "64 MiB display limit"),
        ("stderr_overflow", "MAX_STDERR_BYTES", "64 KiB limit"),
    ],
)
def test_output_limit_is_enforced_while_process_is_running(
    monkeypatch, configuration, resources, mode, constant, message
):
    monkeypatch.setattr(transport, constant, 2048)
    job = transport.SidecarJob({"mode": mode, "bytes": 4096}, **configuration).start()
    finished(job, "failed")  # The dummy would sleep 30 seconds if not killed.
    with pytest.raises(BridgeError, match=message):
        job.result()
    assert resources[0][0].returncode is not None
    assert all(file.closed for file in resources[1])
    assert not (Path(configuration["project_root"]) / "completed").exists()


def test_output_limit_is_checked_after_fast_exit(monkeypatch, configuration, resources):
    monkeypatch.setattr(transport, "MAX_RESPONSE_BYTES", 128)
    job = transport.SidecarJob({"mode": "raw", "raw": "x" * 256}, **configuration).start()
    finished(job, "failed")
    with pytest.raises(BridgeError, match="64 MiB display limit"):
        job.result()


def test_executable_start_failure_closes_all_tempfiles(configuration, resources, tmp_path):
    invalid = tmp_path / "not-executable"
    invalid.write_text("not executable", encoding="utf-8")
    configuration["python_executable"] = str(invalid)
    job = transport.SidecarJob({}, **configuration).start()
    finished(job, "failed")
    with pytest.raises(BridgeError, match="Could not start sidecar Python"):
        job.result()
    assert resources[0] == []
    assert len(resources[1]) == 3
    assert all(file.closed for file in resources[1])


def test_thread_start_failure_is_consumable(monkeypatch, configuration, resources):
    def fail_start(self):
        raise RuntimeError("thread unavailable")

    monkeypatch.setattr(transport.threading.Thread, "start", fail_start)
    job = transport.SidecarJob({}, **configuration).start()
    finished(job, "failed")
    with pytest.raises(BridgeError, match="Could not start sidecar worker"):
        job.result()
    assert resources[0] == []
    assert resources[1] == []


def test_partial_tempfile_setup_failure_closes_previous_files(
    monkeypatch, configuration, resources
):
    opened = transport.tempfile.TemporaryFile
    count = 0

    def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("disk unavailable")
        return opened(*args, **kwargs)

    monkeypatch.setattr(transport.tempfile, "TemporaryFile", fail_second)
    job = transport.SidecarJob({}, **configuration).start()
    finished(job, "failed")
    with pytest.raises(BridgeError, match="Sidecar communication failed: disk unavailable"):
        job.result()
    assert not resources[0]
    assert len(resources[1]) == 1
    assert resources[1][0].closed


@pytest.mark.parametrize("phase", ["before", "running", "ready"])
def test_export_cancellation_reports_uncertain_outcome_only_after_launch(
    phase, configuration, resources
):
    request = {"action": "export_step", "mode": "sleep" if phase == "running" else "success"}
    job = transport.SidecarJob(request, **configuration)
    if phase == "running":
        job.start()
        started(configuration)
    elif phase == "ready":
        finished(job.start())
    assert job.cancel()
    finished(job, "cancelled")
    with pytest.raises(BridgeError, match="cancelled") as error:
        job.result()
    assert error.value.outcome_unknown == (phase != "before")


def test_nonstring_action_does_not_break_error_cleanup(configuration, resources):
    job = transport.SidecarJob({"action": [], "mode": "invalid"}, **configuration).start()
    finished(job, "failed")
    with pytest.raises(BridgeError, match="invalid JSON"):
        job.result()


def test_repeated_jobs_cleanup_without_descriptor_growth(configuration, resources):
    descriptors = Path("/proc/self/fd")
    before = len(list(descriptors.iterdir())) if descriptors.is_dir() else None
    for index in range(12):
        job = transport.SidecarJob({"iteration": index}, **configuration).start()
        finished(job)
        if index % 2:
            assert job.cancel()
            with pytest.raises(BridgeError, match="cancelled"):
                job.result()
        else:
            assert job.result()["echo"]["iteration"] == index
        assert all(file.closed for file in resources[1])
        assert all(process.returncode is not None for process in resources[0])
    if before is not None:
        assert len(list(descriptors.iterdir())) <= before


def test_transport_imports_no_blender_or_native_cad():
    tree = ast.parse((ADDON / "sidecar_job.py").read_text(encoding="utf-8"))
    forbidden = {"bpy", "OCP", "cadquery", "mechanical_cad", "slvs"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not forbidden.intersection(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert node.module.split(".")[0] not in forbidden


@pytest.mark.skipif(os.name == "nt", reason="POSIX process reaping proof")
def test_finished_process_has_already_been_reaped(configuration, resources):
    job = finished(transport.SidecarJob({}, **configuration).start())
    job.result()
    with pytest.raises(ChildProcessError):
        os.waitpid(resources[0][0].pid, os.WNOHANG)
