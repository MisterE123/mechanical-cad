"""Actual Windows public capture with real owners and finite fake OS APIs.

These are composition controls, not native Windows process or geometry proof.
The reused runtime fixture also doubles _verify_cached_tree, _read_launch_inputs
and pin acquisition/lifetime; it does not verify a real filesystem inventory.
"""

import ctypes
import hashlib
import importlib
import json
import ntpath
import os
import sys
import types
import uuid
from dataclasses import replace

import pytest
import test_windows_runtime as fixture

WINDOWS_PUBLIC = pytest.mark.skipif(
    sys.platform != "win32", reason="Actual Windows public bundled transport composition"
)


@pytest.fixture
def public(monkeypatch, tmp_path_factory):
    assert sys.platform == "win32" and os.name == "nt"
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("native API, process or private qualification capture")
        pytest.fail(attempts[-1])

    monkeypatch.setattr(ctypes, "WinDLL", forbidden, raising=False)
    monkeypatch.setattr(fixture.cache, "_WindowsAPI", forbidden)
    monkeypatch.setattr(fixture.jobs.subprocess, "Popen", forbidden)
    monkeypatch.setattr(
        fixture.selection.BackendSelection,
        "_capture_windows_bundled_transport",
        classmethod(forbidden),
    )
    values = fixture.Fixture()
    root = tmp_path_factory.mktemp("wp")
    values.package = str(root / "package")
    (root / "package").mkdir()
    values.known_folder = str(root / "Local")
    values.location = fixture.cache.WindowsCacheLocation(
        values.known_folder, ntpath.join(values.known_folder, "MechanicalCAD", "r")
    )
    values.cache = values.location.cache_root
    values.root = ntpath.join(values.cache, values.bundle_id)
    values.descriptor = replace(
        values.descriptor,
        root=values.root,
        python_path=ntpath.join(values.root, "python", "python.exe"),
        bootstrap_path=ntpath.join(values.root, "bootstrap.py"),
    )
    for relative, data in values.contents.items():
        path = root.joinpath("Local", "MechanicalCAD", "r", values.bundle_id, *relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)  # Inert bytes make receipt paths real; never execute them.
    env = fixture.install(monkeypatch, values)
    policy = env.fixture.policy()
    selected = fixture.selection.BackendSelection.capture_bundled(
        policy, 10, generation=0, lifetime_id="public-windows-composition"
    )
    assert (
        type(selected) is fixture.selection.BackendSelection and selected.bundled_policy is policy
    )
    assert selected.launch_environment() == {}
    with pytest.raises(fixture.jobs.bridge.BridgeError, match="Windows.*not yet qualified"):
        fixture.jobs.SidecarJob({}, project_root=selected.project_root)
    assert env.events == []

    # Reuse the real transport and exact dependency classes. Only its real lease
    # module gets a fresh namespace, so absorbing quarantine cannot poison peers.
    name = "mcad_public_windows_" + uuid.uuid4().hex
    package = types.ModuleType(name)
    package.__path__ = [str(fixture.ROOT / "blender_addon/mechanical_cad_blender")]
    sys.modules[name] = package
    for leaf in (
        "backend_contracts",
        "bridge",
        "backend_selection",
        "guarded_evidence",
        "sidecar_job",
    ):
        sys.modules[name + "." + leaf] = importlib.import_module(fixture.PACKAGE + "." + leaf)
    transport = importlib.import_module(name + ".guarded_transport")
    assert transport.SidecarJob is fixture.jobs.SidecarJob
    assert not transport.execution_lease.is_busy()
    yield types.SimpleNamespace(env=env, selected=selected, transport=transport)
    assert attempts == []


def prepared():
    return fixture.contracts.prepare_request(
        {
            "protocol_version": 1,
            "action": "canonical_snapshot",
            "document": {
                "schema_version": 1,
                "id": "public_snapshot",
                "name": "Public capture fixture",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            },
        }
    )


def response(request, selected):
    guarded, ordinary = request.guarded_request(), request.operation_request()
    document = ordinary["document"]
    canonical = json.dumps(document, sort_keys=True, indent=2) + "\n"

    def encode(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

    required = guarded["backend_contract"]["required_capabilities"]
    return fixture.encode(
        {
            "protocol_version": 1,
            "action": "canonical_snapshot",
            "input_fingerprint": hashlib.sha256(encode(ordinary)).hexdigest(),
            "ok": True,
            "error": None,
            "result": {
                "document_id": document["id"],
                "schema_version": 1,
                "canonical_document": document,
                "canonical_json": canonical,
                "content_hash": hashlib.sha256(canonical.encode()).hexdigest(),
            },
            "backend_receipt": {
                "version": 1,
                "request_id": request.request_id,
                "request_fingerprint": hashlib.sha256(encode(guarded)).hexdigest(),
                "required_capabilities": required,
                "confirmed_capabilities": required,
                "missing_capabilities": [],
                "phase": "dispatched",
                "backend": {
                    "core_version": "synthetic-composition-only",
                    "project_root": selected.project_root,
                    "core_origin": selected.core_origin,
                    "solver_origin": None,
                    "python_executable": selected.python_executable,
                    "python_executable_target": selected.python_executable_target,
                    "python_prefix": ntpath.join(selected.project_root, "diagnostic"),
                    "python_base_prefix": ntpath.join(selected.project_root, "base"),
                    "python_version": [3, 12, 10],
                },
            },
        }
    )


def start(public, request, owner):
    public.env.process.response = response(request, public.selected)
    job = public.transport.GuardedJob(request, public.selected, owner_token=owner)
    assert type(job._job) is fixture.jobs.SidecarJob
    job.start(public.selected)
    assert job.wait(5) and job.state == "ready"
    return job


@WINDOWS_PUBLIC
def test_public_request_nonce_exact_bytes_cleanup_and_single_consumption(public):
    request, owner = prepared(), object()
    assert request.request_id != prepared().request_id
    job = start(public, request, owner)
    assert public.env.process.contents["file0"] == request.payload
    assert job.request_snapshot() == request.guarded_request()
    evidence = job.result(public.selected, owner_token=owner)
    assert evidence.receipt_snapshot()["request_id"] == request.request_id
    with pytest.raises(public.transport.GuardedOperationError, match="consumed"):
        job.result(public.selected, owner_token=owner)
    options = dict(
        owner_token=owner, expected_action="canonical_snapshot", expected_result_version=None
    )
    projected = evidence.publication.consume(public.selected, **options)
    assert projected["document_id"] == "public_snapshot"
    with pytest.raises(fixture.contracts.BackendContractError, match="available"):
        evidence.publication.consume(public.selected, **options)
    env = public.env
    assert env.pin.releases == 1 and not env.pin.held
    assert env.events.index("read_file1") < env.events.index("close_file1")
    assert env.events.index("read_file2") < env.events.index("close_file2")
    assert env.events.index("rmdir") < env.events.index("pin_release")
    assert len(env.process.close_calls) == len(set(env.process.close_calls))
    assert env.events.count("create") == 1


@WINDOWS_PUBLIC
def test_public_cancel_before_launch_never_acquires_or_consumes(public):
    owner = object()
    job = public.transport.GuardedJob(prepared(), public.selected, owner_token=owner)
    assert job.cancel() and job.wait(0)
    with pytest.raises(public.transport.GuardedOperationError, match="once"):
        job.start(public.selected)
    with pytest.raises(public.transport.GuardedOperationError, match="cancelled"):
        job.result(public.selected, owner_token=owner)
    assert public.env.events == [] and public.env.pin.releases == 0


@WINDOWS_PUBLIC
@pytest.mark.parametrize("fault", ["wrong_owner", "stale_selection", "ready_cancel"])
def test_public_ready_completion_cannot_cross_owner_or_lifetime(public, fault):
    owner = object()
    job = start(public, prepared(), owner)
    if fault == "wrong_owner":
        with pytest.raises(public.transport.GuardedOperationError, match="another owner"):
            job.result(public.selected, owner_token=object())
    elif fault == "stale_selection":
        with pytest.raises(public.transport.GuardedOperationError, match="changed"):
            job.poll(replace(public.selected, generation=1))
    else:
        assert job.cancel()
    assert job.state == "cancelled" and job._job._response is None
    with pytest.raises(public.transport.GuardedOperationError, match="cancelled"):
        job.result(public.selected, owner_token=owner)
    assert public.env.pin.releases == 1 and public.env.events.count("create") == 1


@WINDOWS_PUBLIC
def test_public_cleanup_uncertainty_retains_original_lease_and_never_publishes(public):
    request, owner = prepared(), object()
    public.env.process.response = response(request, public.selected)
    public.env.process.fault = "close_file1"
    published = []
    with pytest.raises(public.transport.GuardedOperationError, match="restart Blender"):
        published.append(
            public.transport.execute(
                request,
                public.selected,
                owner_token=owner,
                current_selection=lambda: public.selected,
            )
        )
    lease = public.transport.execution_lease
    token, original = lease._QUARANTINE
    assert published == [] and not original.done
    assert original._job.state == "cleanup_uncertain" and original._job._response is None
    assert original._job._bundle_owner.pin is public.env.pin
    assert lease.is_busy() and lease.try_acquire() is None and not lease.release(token)
    assert public.env.pin.held and public.env.pin.releases == 0
    assert public.env.runtime.closed == [] and "rmdir" not in public.env.events
    before = list(public.env.events)
    with pytest.raises(public.transport.GuardedOperationError, match="restart Blender"):
        public.transport.execute(
            request, public.selected, owner_token=owner, current_selection=lambda: public.selected
        )
    assert public.env.events == before
    assert len(public.env.process.close_calls) == len(set(public.env.process.close_calls))


@WINDOWS_PUBLIC
@pytest.mark.parametrize(
    "fault,match",
    [
        ("bool_protocol", "protocol mismatch"),
        ("wrong_protocol", "protocol mismatch"),
        ("float_protocol", "protocol mismatch"),
        ("string_protocol", "protocol mismatch"),
        ("ok_type", "success flag"),
        ("nonce", "operation nonce"),
        ("fingerprint", "complete guarded request"),
        ("document", "different document identity"),
    ],
)
def test_public_protocol_and_receipt_rejection_keeps_owner_cleanup(public, fault, match):
    request, owner = prepared(), object()
    value = json.loads(response(request, public.selected))
    positive = public.transport.accept_response(request, value, public.selected, owner_token=owner)
    assert type(positive) is public.transport.GuardedEvidence
    assert positive.publication.cancel()
    if fault.endswith("protocol"):
        value["protocol_version"] = {
            "bool_protocol": True,
            "wrong_protocol": 2,
            "float_protocol": 1.0,
            "string_protocol": "1",
        }[fault]
    elif fault == "ok_type":
        value["ok"] = "yes"
    elif fault == "nonce":
        value["backend_receipt"]["request_id"] = "f" * 32
    elif fault == "fingerprint":
        value["backend_receipt"]["request_fingerprint"] = "0" * 64
    else:
        value["result"]["document_id"] = "foreign_document"
    public.env.process.response = fixture.encode(value)
    job = public.transport.GuardedJob(request, public.selected, owner_token=owner)
    job.start(public.selected)
    assert job.wait(5)
    with pytest.raises(public.transport.GuardedOperationError, match=match):
        job.result(public.selected, owner_token=owner)
    assert public.env.pin.releases == 1 and not public.env.pin.held
    assert public.env.events.count("create") == 1
    assert len(public.env.process.close_calls) == len(set(public.env.process.close_calls))
    before = list(public.env.events)
    with pytest.raises(public.transport.GuardedOperationError, match="consumed"):
        job.result(public.selected, owner_token=owner)
    assert public.env.events == before


def record_public_jobs(monkeypatch, public):
    jobs = []
    original = public.transport.GuardedJob.__init__

    def observe(self, *args, **kwargs):
        original(self, *args, **kwargs)
        jobs.append(self)

    monkeypatch.setattr(public.transport.GuardedJob, "__init__", observe)
    return jobs


def assert_failed_public_owner_retired_once(public, job):
    env, lease = public.env, public.transport.execution_lease
    assert job.done and job._job._response is None
    assert env.pin.releases == 1 and not env.pin.held
    assert env.events.count("create") == env.events.count("rmdir") == 1
    assert env.events.count("pin_release") == 1
    assert env.events.index("rmdir") < env.events.index("pin_release")
    assert set(env.process.acquired) == set(env.process.closed)
    assert len(env.process.close_calls) == len(set(env.process.close_calls))
    assert not lease.is_busy() and lease._QUARANTINE is None
    before = list(env.events)
    with pytest.raises(public.transport.GuardedOperationError, match="consumed"):
        job.result(public.selected, owner_token=job._owner_token)
    with pytest.raises(public.transport.GuardedOperationError, match="once"):
        job.start(public.selected)
    assert env.events == before


@WINDOWS_PUBLIC
@pytest.mark.parametrize("duplicate", ["envelope", "nested"])
def test_public_raw_duplicate_response_rejects_without_evidence_or_retry(
    public, monkeypatch, duplicate
):
    request = prepared()
    clean = response(request, public.selected)
    decoded = fixture.jobs.bridge.parse_document_json(clean.decode("utf-8"), require_object=False)
    positive = public.transport.accept_response(
        request, decoded, public.selected, owner_token=object()
    )
    assert type(positive) is public.transport.GuardedEvidence
    assert positive.publication.cancel()
    if duplicate == "envelope":
        original, replacement = b'"ok":true', b'"ok":false,"ok":true'
    else:
        original, replacement = (
            b'"document_id":"public_snapshot"',
            b'"document_id":"foreign","document_id":"public_snapshot"',
        )
    assert clean.count(original) == 1
    ambiguous = clean.replace(original, replacement, 1)
    public.env.process.response = ambiguous  # Raw bytes reach the real decoder.
    jobs, evidence = record_public_jobs(monkeypatch, public), []
    with pytest.raises(public.transport.GuardedOperationError, match="invalid JSON"):
        evidence.append(
            public.transport.execute(
                request,
                public.selected,
                owner_token=object(),
                current_selection=lambda: public.selected,
            )
        )
    assert evidence == [] and len(jobs) == 1
    assert public.env.process.contents["file1"] == ambiguous
    assert_failed_public_owner_retired_once(public, jobs[0])
