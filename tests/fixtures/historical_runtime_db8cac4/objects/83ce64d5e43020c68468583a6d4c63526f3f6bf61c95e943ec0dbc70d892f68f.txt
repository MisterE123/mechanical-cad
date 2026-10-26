"""Finite fixture-based Gate C registered-operator gate; no manual-GUI claim.

Run only in the controller's serial native slot, using explicit MCAD_ROOT,
MCAD_PYTHON, MCAD_GEOMETRY3_DIRECTORY and Blender --python-exit-code 1.
Order/ceiling: OWNER_ROWS below, one sidecar each, one Blender lifetime, zero
separate readers/replays/retries. The same file's worker mode observes the actual
writer's temporary output in that sidecar, following Gate B's same-invocation
readback pattern. No marker, action/protocol link, source origin or wire changes.
The persistence gate imports these helpers, without running this owner matrix.
"""

import copy
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
import time
from collections import Counter
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
FIXTURE = ROOT / "tests/fixtures/arc_authoring_evidence/radius_edit_5_0_replay.operation.json"
ACTIONS = ("check_geometry", "export_step", "export_stl")
PUBLICATION_CASES = (
    "display",
    "report_before",
    "report_after",
    "remember_part",
    "remember_geometry",
    "final_binding",
    "preapply_projection",
    "failure_report",
)
OWNER_ROWS = (
    *(f"r{radius}_{action}" for radius in (5, 7, 1000) for action in ACTIONS),
    *("unknown_" + case for case in ("malformed", "missing", "nonce", "earlier_completion")),
    *("stale_" + case for case in ("backend_aba", "owner", "scene")),
    *("publication_" + case for case in PUBLICATION_CASES),
    "failed_replay",
    "failed_check",
    "failed_writer",
    *("ordinary_" + action for action in ACTIONS),
)
assert len(OWNER_ROWS) == 30


def persist(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def writer_worker():
    """One actual sidecar main; observation hooks delegate each original once.

    This branch executes in isolated CPython, before importing bpy. STEP reader
    uses the very temporary file written by export_step. STL comparison uses the
    last tessellate return inside the original export_stl, never another replay.
    Explicit failure injections occur AFTER the original check/writer returns.
    """
    packet = Path(sys.argv[sys.argv.index("--geometry3-worker") + 1]).resolve()
    fault = sys.argv[sys.argv.index("--geometry3-worker") + 2]
    sys.path.insert(0, str(ROOT / "src"))
    from mechanical_cad import actions, geometry_protocol_v3, kernel_ocp, sidecar

    assert geometry_protocol_v3.run_geometry_action is actions.run_geometry_action
    assert "bpy" not in sys.modules, "Native observer must run only in isolated CPython"
    for module in (actions, geometry_protocol_v3, kernel_ocp, sidecar):
        assert Path(module.__file__).resolve() == ROOT / "src/mechanical_cad" / (
            module.__name__.rsplit(".", 1)[-1] + ".py"
        )
    observed = {"replays": 0, "checks": 0, "writers": [], "phase": "replay"}
    active = [None]
    meshes = []
    original_replay = actions.regenerate
    original_check = kernel_ocp.OCPKernel.manufacturing_check
    original_mesh = kernel_ocp.OCPKernel.tessellate
    original_step = kernel_ocp.OCPKernel.export_step
    original_stl = kernel_ocp.OCPKernel.export_stl

    def measure(kernel, shape):
        return {
            "shape_token": id(shape),
            "stats": kernel._require_single_solid(shape),
            "bounds_mm": list(kernel_ocp._shape_bounds(shape)),
        }

    def replay(document, *args, **kwargs):
        observed["replays"] += 1
        assert observed["replays"] == 1, "Separate replay cannot supply the readback oracle"
        result = original_replay(document, *args, **kwargs)
        active[0] = result.shapes.get(document.active_feature)
        observed["replay_result"] = result.result
        return result

    def mesh(kernel, shape, *args, **kwargs):
        result = original_mesh(kernel, shape, *args, **kwargs)
        if observed["phase"] == "export_stl":
            assert shape is active[0]
            meshes.append(copy.deepcopy(result))
        return result

    def manufacturing(kernel, shape, *args, **kwargs):
        assert shape is active[0]
        observed["checks"] += 1
        result = original_check(kernel, shape, *args, **kwargs)
        observed["source"] = measure(kernel, shape)
        if fault == "check_after_original":
            raise RuntimeError("Gate C injected check failure after actual native check")
        return result

    def step(kernel, shape, path):
        assert shape is active[0] and observed["replays"] == 1
        observed["writers"].append("STEP")
        observed["source"] = measure(kernel, shape)
        result = original_step(kernel, shape, path)
        payload = Path(path).read_bytes()
        (packet / "actual_writer.step").write_bytes(payload)
        # This reader is IN the existing sidecar, not another native process.
        readback = measure(kernel, kernel.import_step(path))
        observed["step_readback"] = readback
        persist(packet / "actual_step_reader_observation.json", readback)
        assert readback["stats"]["valid"] and readback["stats"]["solids"] == 1
        assert math.isclose(
            readback["stats"]["volume"],
            observed["source"]["stats"]["volume"],
            rel_tol=1e-10,
            abs_tol=1e-9,
        )
        assert (
            max(
                abs(a - b)
                for a, b in zip(readback["bounds_mm"], observed["source"]["bounds_mm"], strict=True)
            )
            <= 1e-7
        )
        if fault == "writer_after_original":
            raise RuntimeError("Gate C injected writer failure after actual native writer")
        return result

    def stl(kernel, shape, path, *args, **kwargs):
        assert shape is active[0] and observed["replays"] == 1
        observed["writers"].append("STL")
        observed["phase"] = "export_stl"
        observed["source"] = measure(kernel, shape)
        try:
            result = original_stl(kernel, shape, path, *args, **kwargs)
            payload = Path(path).read_bytes()
            (packet / "actual_writer.stl").write_bytes(payload)
            assert len(meshes) == 2
            packed = [struct.pack("<3f", *v) for v in meshes[-1]["vertices"]]
            expected = Counter(
                tuple(sorted(packed[i] for i in tri)) for tri in meshes[-1]["triangles"]
            )
            count = struct.unpack_from("<I", payload, 80)[0]
            assert len(payload) == 84 + count * 50
            actual = Counter(
                tuple(
                    sorted(
                        payload[84 + i * 50 + 12 + j * 12 : 84 + i * 50 + 24 + j * 12]
                        for j in range(3)
                    )
                )
                for i in range(count)
            )
            assert actual == expected
            observed["stl_exact_writer_mesh"] = True
            return result
        finally:
            if meshes:
                observed["stl_source_mesh"] = meshes[-1]
                errors = [
                    math.dist(v, struct.unpack("<3f", struct.pack("<3f", *v)))
                    for v in meshes[-1]["vertices"]
                ]
                observed["binary32_maximum_error_mm"] = max(errors, default=0)
                observed["binary32_allowed_error_mm"] = min(
                    1e-5, float(kwargs.get("linear_deflection", args[0] if args else 0.1)) * 0.1
                )
            observed["phase"] = "complete"

    actions.regenerate = replay
    kernel_ocp.OCPKernel.manufacturing_check = manufacturing
    kernel_ocp.OCPKernel.tessellate = mesh
    kernel_ocp.OCPKernel.export_step = step
    kernel_ocp.OCPKernel.export_stl = stl
    try:
        return sidecar.main()
    finally:
        observed["fault"] = fault
        observed["python_executable"] = sys.executable
        observed["python_version"] = sys.version
        observed["origins"] = {
            name: {"path": module.__file__, "sha256": digest(module.__file__)}
            for name, module in (
                ("actions", actions),
                ("geometry_protocol_v3", geometry_protocol_v3),
                ("kernel_ocp", kernel_ocp),
                ("sidecar", sidecar),
            )
        }
        observed["action_protocol_identity_preserved"] = (
            geometry_protocol_v3.run_geometry_action is actions.run_geometry_action
        )
        persist(packet / "writer_observations.json", observed)


if __name__ == "__main__" and "--geometry3-worker" in sys.argv:
    raise SystemExit(writer_worker())

import bpy  # noqa: E402

os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    assembly_operator_helpers,
    backend_runtime,
    execution_lease,
    geometry_operations,
    guarded_transport,
    operation_contracts,
    sidecar_job,
    workspace,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402


def require(value, label):
    assert value, label
    print("GEOMETRY3_CHECK", label, flush=True)


def rejects(callback, label):
    try:
        callback()
    except (ValueError, RuntimeError):
        return
    raise AssertionError(label)


def sector(radius=5, height=10):
    document = json.loads(FIXTURE.read_text())["document"]
    document["parameters"].update(radius=float(radius), height=float(height))
    return document


def shape(document):
    sketch = document["features"][0]["sketch"]
    return {key: copy.deepcopy(sketch[key]) for key in ("points", "lines", "arcs", "circles")}


def state():
    return bpy.context.scene.mechanical_cad


def report():
    return json.loads(state().geometry_report_json)


def unverified(context=None):
    context = context or bpy.context
    require(not doc.part_is_current(context), "Rejected Part has no current authority")
    require(
        not doc.geometry_report_is_current(context), "Rejected geometry has no current authority"
    )
    require(doc.current_part_result(context) is None, "Rejected current result is unavailable")


class NativeGate:
    """Finite serial transport inventory; every registered call owns one launch."""

    def __init__(self, directory, rows):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.rows = tuple(rows)
        self.completed = []
        self.evidence = []
        self.jobs = []
        persist(
            self.directory / "DECLARED.json",
            {
                "rows": self.rows,
                "sidecar_ceiling": len(self.rows),
                "separate_reader_processes": 0,
                "automatic_retries": 0,
                "fixture_sha256": digest(FIXTURE),
                "harness_sha256": digest(__file__),
                "same_invocation_hooks": [
                    "actions.regenerate",
                    "OCPKernel.manufacturing_check",
                    "OCPKernel.tessellate",
                    "OCPKernel.export_step",
                    "OCPKernel.export_stl",
                ],
                "gui_qualification": False,
            },
        )

    def call(
        self,
        label,
        action,
        *,
        destination=None,
        fault="none",
        returned=None,
        execute=None,
        expected_operator="FINISHED",
    ):
        require(label == self.rows[len(self.completed)], "Predeclared serial row order: " + label)
        packet = self.directory / label
        packet.mkdir()
        jobs, processes, accepted = [], [], []
        process_facts = []
        start_times = []
        original_start = sidecar_job.SidecarJob.start
        original_read = sidecar_job.SidecarJob._read_response
        original_result = sidecar_job.SidecarJob.result
        original_popen = subprocess.Popen
        original_accept = guarded_transport.accept_response
        original_execute = guarded_transport.execute

        def start(job):
            require(not jobs, label + " has exactly one sidecar start and no retry")
            jobs.append(job)
            start_times.append(time.monotonic_ns())
            self.jobs.append(job)
            (packet / "request.raw").write_bytes(job._payload)
            return original_start(job)

        def popen(command, *args, **kwargs):
            require(
                command == [str(jobs[0]._executable), "-m", "mechanical_cad.sidecar"],
                "Only the original explicit sidecar command is instrumented",
            )
            require(not processes, "One actual child per declared operator")
            require(
                Path(jobs[0]._root).resolve() == ROOT,
                "Instrument only the explicitly selected source root",
            )
            require(
                kwargs["env"]["PYTHONPATH"] == str(ROOT / "src"),
                "Retain the production selected source import path",
            )
            command = [
                command[0],
                "-B",
                str(Path(__file__).resolve()),
                "--geometry3-worker",
                str(packet),
                fault,
            ]
            persist(packet / "command.json", command)
            before_ns, before_utc_ns = time.monotonic_ns(), time.time_ns()
            child = original_popen(command, *args, **kwargs)
            after_ns, after_utc_ns = time.monotonic_ns(), time.time_ns()
            processes.append(child)
            facts = {
                "pid": child.pid,
                "pgid": os.getpgid(child.pid),
                "sid": os.getsid(child.pid),
                "popen_before_monotonic_ns": before_ns,
                "popen_after_monotonic_ns": after_ns,
                "popen_before_utc_ns": before_utc_ns,
                "popen_after_utc_ns": after_utc_ns,
                "configured_timeout_seconds": jobs[0]._timeout,
                # Production computes its private deadline between start() and Popen.
                # These are measured bounds, never a fabricated exact local value.
                "production_deadline_monotonic_ns_bounds": [
                    start_times[0] + int(jobs[0]._timeout * 1e9),
                    before_ns + int(jobs[0]._timeout * 1e9),
                ],
            }
            process_facts.append(facts)
            persist(packet / "process_started.json", facts)
            return child

        def read(job, process, stdout, stderr):
            stdout.seek(0)
            stderr.seek(0)
            raw = stdout.read(sidecar_job.MAX_RESPONSE_BYTES + 1)
            diagnostics = stderr.read(sidecar_job.MAX_STDERR_BYTES + 1)
            (packet / "stdout.raw").write_bytes(raw)
            (packet / "stderr.raw").write_bytes(diagnostics)
            stdout.seek(0)
            stderr.seek(0)
            return original_read(job, process, stdout, stderr)

        def result(job):
            response = original_result(job)
            return response if returned is None else returned(response)

        def accept(*args, **kwargs):
            evidence = original_accept(*args, **kwargs)
            if hasattr(evidence, "publication"):
                accepted.append((evidence, kwargs["owner_token"]))
                self.evidence.append((evidence, kwargs["owner_token"]))
            return evidence

        def run(*args, **kwargs):
            evidence = original_execute(*args, **kwargs)
            return evidence if execute is None else execute(evidence)

        before = state().document_json
        outcome, error = None, None
        try:
            with (
                patch.object(sidecar_job.SidecarJob, "start", start),
                patch.object(sidecar_job.SidecarJob, "_read_response", read),
                patch.object(sidecar_job.SidecarJob, "result", result),
                patch.object(subprocess, "Popen", popen),
                patch.object(guarded_transport, "accept_response", accept),
                patch.object(guarded_transport, "execute", run),
            ):
                operator = getattr(bpy.ops.mcad, action)
                if destination is None:
                    outcome = operator()
                else:
                    outcome = operator(filepath=str(destination), check_existing=False)
        except RuntimeError as exc:
            error = str(exc)
            if expected_operator != "CANCELLED" or "Gate C injected" not in error:
                raise
        finally:
            terminal = {
                "label": label,
                "starts": len(jobs),
                "processes": len(processes),
                "returncodes": [p.poll() for p in processes],
                "process_facts": process_facts,
                "collected_monotonic_ns": time.monotonic_ns(),
                "collected_utc_ns": time.time_ns(),
                "job_states": [j.state for j in jobs],
                "cleanup_complete": all(j.done and not j.cleanup_diagnostic for j in jobs),
                "lease_busy": execution_lease.is_busy(),
                "operator": sorted(outcome or []),
                "operator_error": error,
                "canonical_before": before,
                "canonical_after": state().document_json,
            }
            persist(packet / "terminal.json", terminal)
        require(len(jobs) == len(processes) == 1, label + " starts exactly one real process")
        raw_response = json.loads((packet / "stdout.raw").read_text())
        expected_exit = 0 if raw_response["ok"] else 1
        require(
            all(p.returncode == expected_exit for p in processes),
            label + " actual sidecar exit matches its unmodified wire outcome",
        )
        require(
            all(j.done and not j.cleanup_diagnostic for j in jobs), label + " cleanup collected"
        )
        require(not execution_lease.is_busy(), label + " lease released")
        require(
            outcome == {expected_operator} or (error and expected_operator == "CANCELLED"),
            label + " has expected registered operator outcome",
        )
        observed = json.loads((packet / "writer_observations.json").read_text())
        require(observed["replays"] == 1, label + " performs one original canonical replay")
        require(
            observed["action_protocol_identity_preserved"], "Actual guarded admission unchanged"
        )
        self.completed.append(label)
        return observed, accepted

    def finish(self):
        require(tuple(self.completed) == self.rows, "Exact declared matrix completed")
        require(len(self.jobs) == len(self.rows), "Exact sidecar total, no hidden retry")
        require(not execution_lease.is_busy(), "No final lease")
        require(
            not any(n == "OCP" or n.startswith("OCP.") or n == "slvs" for n in sys.modules),
            "Native CAD remains outside Blender",
        )
        persist(
            self.directory / "RESULT.json",
            {
                "ok": True,
                "rows": self.completed,
                "sidecars": len(self.jobs),
                "separate_reader_processes": 0,
                "gui_qualification": False,
            },
        )


def current(action, version=3):
    require(doc.part_is_current(bpy.context), "Fresh Part is current")
    require(doc.geometry_report_is_current(bpy.context), "Fresh geometry report is current")
    evidence, owner = doc.current_part_evidence(bpy.context)
    operation = evidence.operation_request()
    require(
        operation["action"] == action
        and type(operation["result_version"]) is int
        and operation["result_version"] == version,
        "Exact explicit owner/action/version",
    )
    require(
        evidence.response_snapshot()["backend_receipt"]["phase"] == "dispatched",
        "Actual guarded dispatch receipt retained",
    )
    record = doc._RUNTIME[doc._scene_key(bpy.context.scene)]
    require(
        evidence.guarded_request() == record["prepared"].guarded_request(),
        "Complete G equals independently retained original prepared request",
    )
    rejects(
        lambda: evidence.publication.consume(
            evidence.selection, owner_token=owner, expected_result_version=version
        ),
        "Already published evidence cannot be consumed twice",
    )
    return evidence, owner


def context_parts():
    window = bpy.context.window
    area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
    region = next(item for item in area.regions if item.type == "WINDOW")
    window.workspace[workspace.OWNER_KEY] = workspace.OWNER
    window.workspace[workspace.ROLE_KEY] = "PART"
    return window, area, region


@contextmanager
def publication_failure(case, packet=None):
    """Only Blender publication/report seams; native result is not replaced."""
    original_report = geometry_operations._record_report
    original_remember = doc._remember_evidence
    original_binding = doc._assert_binding
    original_display = doc._display_feature
    original_projection = doc._evidence_projection
    report_calls = [0]

    def fail():
        raise RuntimeError("Gate C injected " + case)

    def display(*args, **kwargs):
        original_display(*args, **kwargs)
        later = doc._read_document(state())
        later["name"] = "Gate C later canonical edit"
        state().document_json = json.dumps(later, allow_nan=False)
        fail()

    def record(*args, **kwargs):
        report_calls[0] += 1
        if case == "report_before" and report_calls[0] == 1:
            fail()
        original_report(*args, **kwargs)
        if (case in ("report_before", "report_after") and report_calls[0] == 1) or (
            case == "failure_report" and kwargs.get("status") == "OUTDATED"
        ):
            fail()

    def remember(*args, **kwargs):
        original_remember(*args, **kwargs)
        if case == "failure_report" and kwargs.get("geometry", False):
            context, evidence, captured = args
            source = captured["scene"]
            key = doc._scene_key(source)
            observations = {
                "synthetic_scene_wrapper": False,
                "binding_scene_pointer": source.as_pointer(),
                "current_scene_pointer": context.scene.as_pointer(),
                "current_scene_is_binding": context.scene is source,
                "current_scene_equals_binding": context.scene == source,
                "records": {},
            }
            for label, records in (("part", doc._RUNTIME), ("geometry", doc._GEOMETRY_RUNTIME)):
                record = records[key]
                observations["records"][label] = {
                    "scene_is_binding": record["scene"] is source,
                    "scene_equals_binding": record["scene"] == source,
                    "scene_pointer": record["scene"].as_pointer(),
                    "exact_completion": record["evidence"] is evidence,
                    "exact_owner_token": record["owner_token"] is captured["owner_token"],
                    "prepared_equal": record["prepared"] == captured["prepared"],
                }
            persist(packet / "native_rna_before_injected_failure.json", observations)
        if kwargs.get("geometry", False) == (case in ("remember_geometry", "failure_report")):
            fail()

    def binding(*args, **kwargs):
        original_binding(*args, **kwargs)
        if state().geometry_status == "PASSED":
            fail()

    def projection(*args, **kwargs):
        if case == "preapply_projection":
            fail()
        return original_projection(*args, **kwargs)

    with ExitStack() as stack:
        if case == "display":
            stack.enter_context(patch.object(doc, "_display_feature", display))
        elif case in ("report_before", "report_after", "failure_report"):
            stack.enter_context(patch.object(geometry_operations, "_record_report", record))
            if case == "failure_report":
                # Actual RNA records are inserted first. The second exception is
                # failure-report rendering, with no synthetic Scene wrapper.
                stack.enter_context(patch.object(doc, "_remember_evidence", remember))
        elif case in ("remember_part", "remember_geometry"):
            stack.enter_context(patch.object(doc, "_remember_evidence", remember))
        elif case == "final_binding":
            stack.enter_context(patch.object(doc, "_assert_binding", binding))
        elif case == "preapply_projection":
            stack.enter_context(patch.object(doc, "_evidence_projection", projection))
        else:
            raise AssertionError(case)
        yield


def authority_zero_launch_controls(window):
    """Same native evidence, foreign owner/context and saved-label controls."""
    scene = window.scene
    key = doc._scene_key(scene)
    evidence, owner = doc.current_part_evidence(bpy.context)
    records = (doc._RUNTIME[key], doc._GEOMETRY_RUNTIME[key])
    original = doc._snapshot_fields(state())
    binding = doc._capture_binding(bpy.context, owner_token=owner)
    binding.update(
        prepared=records[0]["prepared"],
        result_version=3,
        request_fingerprint=records[0]["request_fingerprint"],
    )
    document = doc._read_document(state())

    def trap(*args, **kwargs):
        raise AssertionError("Authority reader/control launched work")

    with (
        patch.object(execution_lease, "try_acquire", trap),
        patch.object(sidecar_job.SidecarJob, "start", trap),
    ):
        rejects(
            lambda: evidence.revalidate(
                evidence.selection,
                owner_token=object(),
                expected_action="check_geometry",
                expected_result_version=3,
            ),
            "A foreign owner cannot reuse current evidence",
        )
        target = bpy.data.scenes.new("Geometry3 foreign authority reader")
        try:
            window.scene = target
            doc._populate_document(target, document)
            before = doc._snapshot_fields(state())
            rejects(
                lambda: doc._apply_result(bpy.context, document, evidence, binding),
                "A completion cannot publish into a different current scene",
            )
            require(
                doc._snapshot_fields(state()) == before, "Foreign scene fields remain untouched"
            )
            gate_key = doc._scene_key(target)
            doc._RUNTIME[gate_key], doc._GEOMETRY_RUNTIME[gate_key] = records
            try:
                unverified()
            finally:
                doc._RUNTIME.pop(gate_key, None)
                doc._GEOMETRY_RUNTIME.pop(gate_key, None)
        finally:
            window.scene = scene
            bpy.data.scenes.remove(target)
        doc._RUNTIME.pop(key)
        doc._GEOMETRY_RUNTIME.pop(key)
        try:
            require(state().geometry_status == "PASSED", "Saved label is genuinely a success label")
            unverified()
        finally:
            doc._RUNTIME[key], doc._GEOMETRY_RUNTIME[key] = records
        require(doc._snapshot_fields(state()) == original, "Readers preserve original scene fields")
        current("check_geometry")


def unsupported_controls(window):
    original_scene = window.scene
    original_json = state().document_json
    original_fields = doc._snapshot_fields(state())
    source = sector()
    variants = {}
    variants["profile_only"] = copy.deepcopy(source)
    variants["profile_only"]["features"] = variants["profile_only"]["features"][:1]
    variants["profile_only"]["active_feature"] = "profile"
    variants["selected_profile"] = copy.deepcopy(source)
    variants["selected_profile"]["active_feature"] = "profile"
    for name in (
        "arc_empty",
        "nonzero_origin",
        "nearzero_origin",
        "quaternion",
        "wrong_ids",
        "extra_extrusion",
        "inactive_schema3",
        "second_arc",
    ):
        variants[name] = copy.deepcopy(source)
    variants["arc_empty"]["features"][0]["sketch"].update(arcs=[], constraints=[])
    variants["nonzero_origin"]["features"][0]["sketch"]["plane"]["origin"][0] = 1
    variants["nearzero_origin"]["features"][0]["sketch"]["plane"]["origin"][0] = 1e-15
    variants["quaternion"]["features"][0]["sketch"]["plane"]["quaternion"][0] = -1
    variants["wrong_ids"]["features"][0]["sketch"]["lines"][0]["end"] = "start"
    extra = copy.deepcopy(source["features"][1])
    extra["id"] = "second_pad"
    variants["extra_extrusion"]["features"].append(extra)
    extra = copy.deepcopy(source["features"][0])
    extra["id"] = "inactive"
    variants["inactive_schema3"]["features"].append(extra)
    extra = copy.deepcopy(source["features"][0]["sketch"]["arcs"][0])
    extra["id"] = "second_rim"
    variants["second_arc"]["features"][0]["sketch"]["arcs"].append(extra)

    def trap(*args, **kwargs):
        raise AssertionError("Zero-launch control crossed lease/transport boundary")

    with (
        patch.object(execution_lease, "try_acquire", trap),
        patch.object(sidecar_job.SidecarJob, "start", trap),
    ):
        for name, document in variants.items():
            target = bpy.data.scenes.new("Geometry3 unsupported " + name)
            try:
                window.scene = target
                doc._populate_document(target, document)
                before = doc._snapshot_fields(state())
                for action in ACTIONS:
                    rejects(
                        lambda action=action: geometry_operations.run_geometry_action(
                            bpy.context,
                            action,
                            destination=None
                            if action == "check_geometry"
                            else "/never-written/geometry3.step",
                        ),
                        name + " must reject",
                    )
                require(doc._snapshot_fields(state()) == before, name + " retains exact fields")
                require(
                    not any(getattr(bpy.ops.mcad, a).poll() for a in ACTIONS),
                    name + " operator polls remain unavailable",
                )
            finally:
                window.scene = original_scene
                bpy.data.scenes.remove(target)
        for role in ("general", "rectangle"):
            for action in ACTIONS:
                rejects(
                    lambda role=role, action=action: operation_contracts.result_version_for(
                        source, action=action, owner_role=role
                    ),
                    "Non-Part owner rejects before work",
                )
        rejects(
            lambda: assembly_operator_helpers.canonical_working_part(bpy.context),
            "Assembly capture remains unavailable",
        )
    require(
        state().document_json == original_json and doc._snapshot_fields(state()) == original_fields,
        "Zero-launch controls preserve original scene state and authority fields",
    )


def main():
    addon.register()
    gate = NativeGate(os.environ["MCAD_GEOMETRY3_DIRECTORY"], OWNER_ROWS)
    window, area, region = context_parts()
    with bpy.context.temp_override(window=window, area=area, region=region):
        scene = bpy.context.scene
        unrelated = bpy.data.objects.new("Geometry3 unrelated sentinel", None)
        scene.collection.objects.link(unrelated)
        unrelated.location = (1.25, -2.5, 3.75)
        unrelated_identity = (
            unrelated.as_pointer(),
            tuple(unrelated.location),
            unrelated.hide_viewport,
        )
        old = None
        prior_export = None
        for radius in (5, 7, 1000):
            document = sector(radius, 1000 if radius == 1000 else 10)
            authored = shape(document)
            if radius == 7:
                # Existing parameter callback edits the same document/feature/entity IDs.
                next(row for row in state().parameters if row.key == "radius").value = 7
                unverified()
                require(
                    shape(doc._read_document(state())) == authored, "Same-ID R7 retains all seeds"
                )
                require(state().geometry_status == "OUTDATED", "Edit revokes the prior report")
                require(
                    doc.current_part_evidence(bpy.context) is None, "Prior Part evidence detached"
                )
                require(old is not None, "Prior R5 completion retained only as history")
            else:
                doc._populate_document(scene, document)
            for action in ACTIONS:
                label = f"r{radius}_{action}"
                path = (
                    None
                    if action == "check_geometry"
                    else gate.directory / (label + (".step" if action == "export_step" else ".stl"))
                )
                sentinel = b"Gate C preexisting large STL destination\n"
                if radius == 1000 and action == "export_stl":
                    path.write_bytes(sentinel)
                before = state().document_json
                observed, _ = gate.call(label, action, destination=path)
                require(
                    state().document_json == before,
                    "Native output does not rewrite canonical intent",
                )
                require(
                    shape(doc._read_document(state())) == authored,
                    "Seeds and stable IDs remain exact",
                )
                if radius == 1000 and action == "export_stl":
                    require(
                        state().geometry_status == "FAILED" and state().status == "READY",
                        "STL encoding failure retains valid Part, no geometry success",
                    )
                    require(
                        report()["error"]["code"] == "export_failed"
                        and "STL binary32 coordinate error" in report()["error"]["message"]
                        and "exceeds allowed" in report()["error"]["message"],
                        "Exact unchanged float32 precision failure",
                    )
                    require(path.read_bytes() == sentinel, "Float32 rejection preserves sentinel")
                    require(
                        observed["binary32_maximum_error_mm"]
                        > observed["binary32_allowed_error_mm"],
                        "Actual writer's source mesh exceeds unchanged ceiling",
                    )
                    require(
                        not doc.geometry_report_is_current(bpy.context),
                        "No failed export authority",
                    )
                else:
                    old = current(action)
                    if radius == 5 and action == "check_geometry":
                        authority_zero_launch_controls(window)
                    if radius == 5 and action == "export_step":
                        prior_export = old[0]
                    volume = math.pi * radius * radius * document["parameters"]["height"] / 4
                    require(
                        math.isclose(
                            report()["geometry_check"]["brep"]["volume"],
                            volume,
                            rel_tol=1e-10,
                            abs_tol=1e-9,
                        ),
                        "Actual solved sector dimensions",
                    )
                    if path:
                        require(
                            path.is_file() and report()["export"]["destination"] == str(path),
                            "Exact requested real export is confirmed",
                        )
                        writer = gate.directory / label / ("actual_writer" + path.suffix)
                        require(
                            path.read_bytes() == writer.read_bytes(),
                            "Atomic destination equals actual writer bytes",
                        )

        doc._populate_document(scene, sector(7))
        for corruption in ("malformed", "missing", "nonce", "earlier_completion"):
            path = gate.directory / ("unknown_" + corruption + ".step")
            sentinel = b"prior file\n"
            path.write_bytes(sentinel)

            def returned(response, corruption=corruption):
                if corruption == "malformed":
                    return {"lost": "reply"}
                if corruption == "missing":
                    response.pop("backend_receipt")
                if corruption == "nonce":
                    response["backend_receipt"]["request_id"] = "0" * 32
                return response

            gate.call(
                "unknown_" + corruption,
                "export_step",
                destination=path,
                returned=returned,
                execute=(lambda evidence: prior_export)
                if corruption == "earlier_completion"
                else None,
            )
            require(path.read_bytes() != sentinel, "UNKNOWN test actually wrote its selected file")
            require(
                state().geometry_status == "UNKNOWN" and report()["export"] is None,
                "Rejected post-write reply grants no confirmed export",
            )
            require(report()["requested_destination"] == str(path), "UNKNOWN keeps selected path")
            unverified()

        for change in ("backend_aba", "owner", "scene"):
            path = gate.directory / ("stale_" + change + ".step")
            owner_id = state().owner_id
            other = (
                bpy.data.scenes.new("Geometry3 stale current scene") if change == "scene" else None
            )

            def stale(evidence, change=change, owner_id=owner_id, other=other):
                if change == "backend_aba":
                    backend_runtime.revoke("Gate C A to B")
                    backend_runtime.revoke("Gate C B to A")
                elif change == "owner":
                    state().owner_id = owner_id + "_successor"
                else:
                    window.scene = other
                return evidence

            gate.call("stale_" + change, "export_step", destination=path, execute=stale)
            if other is not None:
                require(
                    not other.mechanical_cad.document_json,
                    "Late completion never writes foreign scene",
                )
                window.scene = scene
                bpy.data.scenes.remove(other)
            require(
                state().geometry_status == "OUTDATED",
                "Same-request stale completion remains historical",
            )
            require(
                report()["export"]["destination"] == str(path),
                "OUTDATED preserves confirmed file fact",
            )
            unverified()
            state().owner_id = owner_id

        for case in PUBLICATION_CASES:
            path = gate.directory / ("publication_" + case + ".step")
            before = state().document_json
            with publication_failure(case, gate.directory / ("publication_" + case)):
                _, accepted = gate.call(
                    "publication_" + case,
                    "export_step",
                    destination=path,
                    expected_operator="CANCELLED" if case == "failure_report" else "FINISHED",
                )
            unverified()
            key = doc._scene_key(scene)
            require(
                key not in doc._RUNTIME and key not in doc._GEOMETRY_RUNTIME,
                "Both rejected native publication associations are retired",
            )
            statuses = state().status, state().geometry_status
            state().status, state().geometry_status = "READY", "PASSED"
            try:
                unverified()
            finally:
                state().status, state().geometry_status = statuses
            if case == "failure_report":
                require(
                    "Confirmed STEP written:" in state().last_action_error,
                    "Registered double failure still discloses the confirmed write",
                )
            if case == "display":
                later = json.loads(before)
                later["name"] = "Gate C later canonical edit"
                require(
                    state().document_json == json.dumps(later, allow_nan=False),
                    "Failed post-display publication never overwrites a later canonical edit",
                )
            else:
                require(
                    state().document_json == before,
                    "Failed publication preserves canonical document",
                )
            require(
                state().geometry_status == "OUTDATED", "Publication failure cannot retain PASSED"
            )
            require(
                report()["export"]["destination"] == str(path),
                "Failed publication retains actual write history",
            )
            for evidence, owner in accepted:
                rejects(
                    lambda evidence=evidence, owner=owner: evidence.publication.consume(
                        evidence.selection, owner_token=owner, expected_result_version=3
                    ),
                    "Rejected completion cannot publish again",
                )
            require(
                (unrelated.as_pointer(), tuple(unrelated.location), unrelated.hide_viewport)
                == unrelated_identity,
                "Publication injection preserves unrelated datablock",
            )

        for phase in ("replay", "check", "writer"):
            document = sector(-1 if phase == "replay" else 5)
            doc._populate_document(scene, document)
            path = gate.directory / ("failed_" + phase + ".step")
            path.write_bytes(b"failure sentinel")
            gate.call(
                "failed_" + phase,
                "export_step",
                destination=path,
                fault={
                    "replay": "none",
                    "check": "check_after_original",
                    "writer": "writer_after_original",
                }[phase],
            )
            require(
                state().geometry_status == "FAILED" and report()["export"] is None,
                "Distinct " + phase + " failure has no export receipt",
            )
            require(
                report()["error"]["code"]
                == {
                    "replay": "regeneration_failed",
                    "check": "geometry_check_failed",
                    "writer": "export_failed",
                }[phase],
                "Failure phase keeps its specific diagnostic",
            )
            if phase != "replay":
                require(
                    "Gate C injected " + phase + " failure" in report()["error"]["message"],
                    "Explicit post-original fault is the observed failure",
                )
            require(path.read_bytes() == b"failure sentinel", "Failed action preserves destination")
            require(
                doc.part_is_current(bpy.context) == (phase != "replay"),
                "Part validity remains distinct from check/writer failure",
            )

        doc._populate_document(scene, sector())
        unsupported_controls(window)
        doc._populate_document(scene, addon.demo_document())
        for action in ACTIONS:
            path = (
                None
                if action == "check_geometry"
                else gate.directory
                / ("ordinary" + (".step" if action == "export_step" else ".stl"))
            )
            gate.call("ordinary_" + action, action, destination=path)
            current(action, 2)
        gate.finish()
    addon.unregister()
    print(
        "GEOMETRY3_OWNER_RESULT="
        + json.dumps(
            {
                "ok": True,
                "rows": 30,
                "sidecars": 30,
                "reader_processes": 0,
                "gui_qualification": False,
            }
        )
    )


if __name__ == "__main__":
    main()
