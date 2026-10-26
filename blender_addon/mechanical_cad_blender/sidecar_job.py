"""Cancellable, bounded, native-free transport for one isolated sidecar request.

Construction captures an immutable JSON request; only ``start()`` launches work.
The worker owns its process and temporary files and never accesses Blender/RNA.
Stdout (64 MiB) and stderr (64 KiB) are file-backed and size-checked every 10 ms
while the process runs. A writer can overshoot between checks, but neither stream
is ever captured into unbounded memory. Only the final 1500 diagnostic characters
are exposed. This is a trusted-software transport, not a process sandbox.

``poll()``/``state`` are nonblocking: created -> running -> ready/failed, or
created/running/ready/failed -> cancelling/cancelled. Terminal states are visible
only after process reaping and file cleanup. ``result()`` consumes a terminal
response or error exactly once, moving to consumed. Cancellation invalidates any
unconsumed completion, including an already-ready response. The lock orders a
concurrent cancel/result pair; cancellation cannot revoke a consumed response.

The main-thread adapter must bind its own scene/window/revision identity, apply
action-specific validation (for example assembly_bridge.validate_response), and
publish only on the main thread. A transport-ready response is not CAD evidence.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from . import bridge, request_contracts

MAX_DOCUMENT_BYTES = bridge.MAX_DOCUMENT_BYTES
MAX_RESPONSE_BYTES = bridge.MAX_RESPONSE_BYTES
MAX_STDERR_BYTES = 64 * 1024
MAX_DIAGNOSTIC_CHARS = 1500
MAX_REQUEST_DEPTH = request_contracts.MAX_REQUEST_DEPTH
MAX_REQUEST_NODES = request_contracts.MAX_REQUEST_NODES
MAX_INTEGER_BITS = request_contracts.MAX_INTEGER_BITS
POLL_INTERVAL = 0.01
_TERMINAL_STATES = frozenset({"ready", "failed", "cancelled", "consumed"})


class _Cancelled(Exception):
    """Internal control flow; callers receive bridge.BridgeError instead."""


def snapshot_request(request: dict[str, Any]) -> dict[str, Any]:
    """Detach bounded finite JSON, preserving transport errors and local limits."""
    try:
        return request_contracts.snapshot_request(
            request,
            max_bytes=MAX_DOCUMENT_BYTES,
            max_depth=MAX_REQUEST_DEPTH,
            max_nodes=MAX_REQUEST_NODES,
            max_integer_bits=MAX_INTEGER_BITS,
        )
    except request_contracts.RequestError as exc:
        raise bridge.BridgeError(str(exc)) from exc


class SidecarJob:
    """One-shot background transport with explicit start and nonblocking result.

    Configuration and finite JSON are checked during construction. Like the
    synchronous bridge, timeout is clamped to 1..300 seconds. ``cancel()`` never
    waits for native work: running jobs enter cancelling until the worker kills
    and reaps its own process. ``wait(timeout)`` is a cleanup helper for tests or
    shutdown; UI/modal code should only poll. A cancelled unstarted job cannot
    subsequently launch, even if ``start()`` is called.
    """

    def __init__(
        self,
        request: dict[str, Any],
        project_root: str = "",
        python_executable: str = "",
        timeout: float = 60.0,
    ):
        if sys.platform == "win32" or os.name == "nt":
            raise bridge.BridgeError("Windows backend execution is not yet qualified.")
        root, executable = bridge.resolve_configuration(project_root, python_executable)
        snapshot = snapshot_request(request)
        try:
            payload = json.dumps(snapshot, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise bridge.BridgeError(f"Document cannot be encoded as finite JSON: {exc}") from exc
        if len(payload) > MAX_DOCUMENT_BYTES:
            raise bridge.BridgeError("Document exceeds the 2 MiB input limit.")
        self._initialize(snapshot, payload, root, executable, timeout)

    @classmethod
    def from_selection(cls, request, selection):
        """Prepare guarded transport from one already captured backend selection.

        This opt-in constructor does not select a backend again, acquire an
        execution lease or make a response authoritative. The guarded owner
        still checks lifetime/current selection before launch and consumption.
        """
        from .backend_contracts import (
            MAX_GUARDED_REQUEST_BYTES,
            BackendContractError,
            PreparedRequest,
            prepare_guarded_request,
        )
        from .backend_selection import BackendSelection

        if type(request) is not PreparedRequest or type(selection) is not BackendSelection:
            raise bridge.BridgeError("Guarded transport requires a prepared request and selection.")
        try:
            snapshot = request.guarded_request()
            if prepare_guarded_request(snapshot) != request:
                raise bridge.BridgeError("Guarded prepared request fields differ from its bytes.")
            payload = json.dumps(snapshot, allow_nan=False).encode("utf-8")
            if payload != request.payload or len(payload) > MAX_GUARDED_REQUEST_BYTES:
                raise bridge.BridgeError(
                    "Guarded transport request bytes changed or exceed limits."
                )
        except (BackendContractError, TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise bridge.BridgeError(str(exc)) from exc
        result = cls.__new__(cls)
        result._initialize(
            snapshot,
            payload,
            Path(selection.project_root),
            Path(selection.python_executable),
            selection.timeout,
            environment=selection.launch_environment(),
            bundled_policy=selection.bundled_policy,
        )
        return result

    def _initialize(
        self, snapshot, payload, root, executable, timeout, *, environment=None, bundled_policy=None
    ):
        """Shared bounded process ownership; callers already bound the input bytes."""
        self._root, self._executable = root, executable
        self._payload = payload
        try:
            seconds = float(timeout)
            if not math.isfinite(seconds):
                raise ValueError("timeout must be finite")
        except (TypeError, ValueError, OverflowError) as exc:
            raise bridge.BridgeError(f"Invalid sidecar timeout: {exc}") from exc
        self._timeout = max(1.0, min(seconds, 300.0))
        action = snapshot.get("action")
        self._action = action if type(action) is str else None
        if environment is None:
            self._environment = dict(os.environ)
            self._environment.pop("PYTHONHOME", None)
            self._environment["PYTHONPATH"] = str(self._root / "src")
            self._environment["PYTHONNOUSERSITE"] = "1"
            self._environment["PYTHONIOENCODING"] = "utf-8"
        else:
            self._environment = dict(environment)
        self._lock = threading.Lock()
        self._cancel_requested = threading.Event()
        self._finished = threading.Event()
        self._worker_stopped = threading.Event()
        self._state = "created"
        self._worker = None
        self._response = None
        self._error = None
        self._launched = False
        self._bundled_policy = bundled_policy
        self._bundle_owner = None
        self._owned_process = None
        self._owned_files = []
        self._cleanup_uncertain = False

    def request_snapshot(self) -> dict[str, Any]:
        """Return a detached exact JSON copy of the immutable transmitted input."""
        return bridge.parse_document_json(self._payload.decode("utf-8"))

    @property
    def state(self) -> str:
        """Current state; ready/failed/cancelled mean cleanup has finished."""
        with self._lock:
            return self._state

    @property
    def cleanup_diagnostic(self) -> str:
        """Bounded non-consuming status; uncertain owners must remain supervised."""
        with self._lock:
            if self._state == "cleanup_uncertain":
                return (
                    "Bundled backend cleanup could not be confirmed. Native operations remain "
                    "disabled. Save your work and restart Blender before trying again."
                )
            return ""

    @property
    def done(self) -> bool:
        return self.state in _TERMINAL_STATES

    def poll(self) -> str:
        """Read state without waiting, consuming a result, or touching Blender."""
        return self.state

    def start(self) -> SidecarJob:
        """Launch once; cancellation before start prevents any process creation."""
        with self._lock:
            if self._state == "cancelled":
                return self
            if self._state != "created":
                raise bridge.BridgeError("Sidecar job can only be started once.")
            self._state = "running"
            try:
                self._worker = threading.Thread(
                    target=self._run, name="mechanical-cad-sidecar", daemon=True
                )
                self._worker.start()
            except (RuntimeError, OSError) as exc:
                self._error = bridge.BridgeError(f"Could not start sidecar worker: {exc}")
                self._state = "failed"
                self._finished.set()
                self._worker_stopped.set()
        return self

    def cancel(self) -> bool:
        """Invalidate unpublished work; return False if already cancelled/consumed.

        A running process is killed/reaped by its worker, never by the UI thread.
        Cancellation wins over success or failure until result() consumes it.
        """
        with self._lock:
            if self._state in {"cancelling", "cancelled", "consumed", "cleanup_uncertain"}:
                return False
            self._cancel_requested.set()
            self._response = None
            self._error = None
            if self._state == "running":
                self._state = "cancelling"
            else:
                self._state = "cancelled"
                self._error = self._cancellation_error()
                self._finished.set()
                self._worker_stopped.set()
            return True

    def result(self) -> dict[str, Any]:
        """Consume once, raising BridgeError for cancellation/failure/not-ready.

        Calling before completion does not consume the result. A reported CAD
        failure (ok=False) with a valid common envelope is returned unchanged;
        the action-specific main-thread validator decides how to display it.
        """
        with self._lock:
            if self._state == "consumed":
                raise bridge.BridgeError("Sidecar job result has already been consumed.")
            if self._state not in _TERMINAL_STATES:
                raise bridge.BridgeError("Sidecar job result is not ready.")
            response, error = self._response, self._error
            self._response = None
            self._error = None
            self._state = "consumed"
        if error is not None:
            raise error
        return response

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for worker stop; True still means confirmed cleanup, never uncertainty.

        An uncertain worker wakes synchronous owners without claiming completion.
        They must retain its original resources and execution lease in quarantine.
        """
        return self._worker_stopped.wait(timeout) and self.done

    def _transport_error(self, message):
        return bridge._transport_error({"action": self._action}, message)

    def _cancellation_error(self):
        if not self._launched:
            return bridge.BridgeError("CAD operation cancelled before the sidecar started.")
        return self._transport_error("CAD operation cancelled; the sidecar was stopped.")

    def _check_limits(self, stdout, stderr):
        if os.fstat(stdout.fileno()).st_size > MAX_RESPONSE_BYTES:
            raise self._transport_error("Sidecar response exceeds the 64 MiB display limit.")
        if os.fstat(stderr.fileno()).st_size > MAX_STDERR_BYTES:
            raise self._transport_error("Sidecar diagnostic output exceeds the 64 KiB limit.")

    def _read_response(self, process, stdout, stderr):
        self._check_limits(stdout, stderr)
        stdout.seek(0)
        raw = stdout.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise self._transport_error("Sidecar response exceeds the 64 MiB display limit.")

        def read_diagnostics():
            stderr.seek(0)
            return stderr.read(MAX_STDERR_BYTES + 1)

        return self._decode_response(process.returncode, raw, read_diagnostics)

    def _decode_response(self, returncode, raw, read_diagnostics):
        """The existing common envelope rules, shared by both byte transports."""
        content = raw.decode("utf-8", errors="replace")
        try:
            response = bridge.parse_document_json(content, require_object=False)
        except (ValueError, TypeError, bridge.BridgeError) as exc:
            diagnostics = read_diagnostics()
            if len(diagnostics) > MAX_STDERR_BYTES:
                raise self._transport_error(
                    "Sidecar diagnostic output exceeds the 64 KiB limit."
                ) from exc
            detail = (
                diagnostics.decode("utf-8", errors="replace").strip()[-MAX_DIAGNOSTIC_CHARS:]
                or content.strip()[-MAX_DIAGNOSTIC_CHARS:]
                or "No output."
            )
            raise self._transport_error(
                f"Sidecar returned invalid JSON (exit {returncode}). {detail}"
            ) from exc
        if (
            not isinstance(response, dict)
            or type(response.get("protocol_version")) is not int
            or response.get("protocol_version") != bridge.PROTOCOL_VERSION
        ):
            raise self._transport_error(
                "Sidecar protocol mismatch; use the Python environment and source "
                "from the same repository."
            )
        if not isinstance(response.get("ok"), bool):
            raise self._transport_error("Sidecar response is missing its success flag.")
        if returncode and response["ok"]:
            raise self._transport_error(
                f"Sidecar exited with status {returncode} despite reporting success."
            )
        return response

    def _exchange_legacy(self):
        process = None
        with (
            tempfile.TemporaryFile(mode="w+b") as stdin,
            tempfile.TemporaryFile(mode="w+b") as stdout,
            tempfile.TemporaryFile(mode="w+b") as stderr,
        ):
            stdin.write(self._payload)
            stdin.seek(0)
            if self._cancel_requested.is_set():
                raise _Cancelled
            deadline = time.monotonic() + self._timeout
            try:
                try:
                    process = subprocess.Popen(
                        [str(self._executable), "-m", "mechanical_cad.sidecar"],
                        stdin=stdin,
                        stdout=stdout,
                        stderr=stderr,
                        cwd=str(self._root),
                        env=self._environment,
                        close_fds=True,
                    )
                except OSError as exc:
                    raise bridge.BridgeError(f"Could not start sidecar Python: {exc}") from exc
                self._launched = True
                while True:
                    if self._cancel_requested.is_set():
                        raise _Cancelled
                    self._check_limits(stdout, stderr)
                    if time.monotonic() >= deadline:
                        raise self._transport_error(
                            "CAD operation timed out; the sidecar was stopped. Reduce model "
                            "complexity or increase the timeout in preferences."
                        )
                    if process.poll() is not None:
                        break
                    self._cancel_requested.wait(POLL_INTERVAL)
                return self._read_response(process, stdout, stderr)
            finally:
                if process is not None:
                    try:
                        if process.poll() is None:
                            try:
                                process.kill()
                            except ProcessLookupError:
                                pass
                    finally:
                        process.wait()

    def _exchange_windows(self):
        from .windows_runtime import WindowsOperationOwner

        owner = self._bundle_owner = WindowsOperationOwner(self._bundled_policy, self._payload)
        try:
            owner.acquire(timeout=self._timeout, cancelled=self._cancel_requested.is_set)
            return owner.exchange(
                lambda code, raw, diagnostics: self._decode_response(code, raw, lambda: diagnostics)
            )
        except Exception:
            if owner.failure_code == "timeout":
                raise self._transport_error(
                    "CAD operation timed out; the sidecar was stopped. Reduce model "
                    "complexity or increase the timeout in preferences."
                ) from None
            raise
        finally:
            self._launched = owner.attempted_start
            try:
                owner.cleanup()
            finally:
                self._cleanup_uncertain = owner.cleanup_uncertain

    def _exchange(self):
        if self._bundled_policy is None:
            return self._exchange_legacy()
        if self._bundled_policy.constants.PLATFORM == "windows-x64":
            return self._exchange_windows()
        from .runtime_bundle_launch import BundleCleanupUncertain, BundledOperationOwner

        # Publish resource ownership before any acquisition can fail. The existing
        # supervisor retains this job and its execution lease until done is true.
        owner = self._bundle_owner = BundledOperationOwner(self._bundled_policy)
        process = None
        try:
            owner.acquire(timeout=self._timeout, cancelled=self._cancel_requested.is_set)
            for _ in range(3):
                self._owned_files.append(tempfile.TemporaryFile(mode="w+b"))
            stdin, stdout, stderr = self._owned_files
            stdin.write(self._payload)
            stdin.seek(0)
            if self._cancel_requested.is_set():
                raise _Cancelled
            owner.pin.assert_held()
            deadline = time.monotonic() + self._timeout
            try:
                process = self._owned_process = subprocess.Popen(
                    owner.command(),
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                    cwd=str(self._root),
                    env=self._environment,
                    close_fds=True,
                    pass_fds=owner.pass_fds,
                )
            except OSError as exc:
                raise bridge.BridgeError("Could not start the verified bundled Python.") from exc
            self._launched = True
            while True:
                if self._cancel_requested.is_set():
                    raise _Cancelled
                self._check_limits(stdout, stderr)
                if time.monotonic() >= deadline:
                    raise self._transport_error(
                        "CAD operation timed out; the sidecar was stopped. Reduce model "
                        "complexity or increase the timeout in preferences."
                    )
                if process.poll() is not None:
                    break
                self._cancel_requested.wait(POLL_INTERVAL)
            return self._read_response(process, stdout, stderr)
        finally:
            uncertain = owner.cleanup_uncertain
            if process is not None:
                try:
                    try:
                        if process.poll() is None:
                            try:
                                process.kill()
                            except ProcessLookupError:
                                pass
                    finally:
                        process.wait()
                except BaseException:
                    uncertain = True
            # Every original stream gets exactly one close attempt, including
            # partial construction. Never release the pin before all are closed.
            for stream in reversed(self._owned_files):
                try:
                    stream.close()
                except BaseException:
                    uncertain = True
            if not uncertain:
                try:
                    owner.cleanup()
                except BaseException:
                    uncertain = True
            if uncertain:
                owner.cleanup_uncertain = self._cleanup_uncertain = True
                raise BundleCleanupUncertain(
                    "Bundled cleanup is uncertain. Save your work and restart Blender before trying again."
                )

    def _run(self):
        """Always wake waiters; abrupt worker exits retain fail-closed ownership."""
        try:
            self._run_exchange()
        except BaseException:
            # Unexpected SystemExit/KeyboardInterrupt must neither hang a sync
            # owner nor leave an async owner displaying an endless running state.
            # Do not retry cleanup or discard the original process/file/pin owner.
            with self._lock:
                self._cleanup_uncertain = True
                self._response = None
                self._error = self._transport_error(
                    "Bundled cleanup is uncertain. Save your work and restart Blender before trying again."
                )
                self._state = "cleanup_uncertain"
                self._finished.clear()
        finally:
            # This is only a worker-stop notification. done/_finished remain the
            # independent proof of successful resource cleanup.
            self._worker_stopped.set()

    def _run_exchange(self):
        response, error = None, None
        try:
            response = self._exchange()
        except _Cancelled:
            pass
        except bridge.BridgeError as exc:
            error = exc
        except Exception as exc:
            if self._bundled_policy is not None:
                error = self._transport_error(
                    "Bundled backend verification or communication failed. "
                    "Check the installed extension and its private runtime."
                )
            else:
                error = self._transport_error(f"Sidecar communication failed: {exc}")
        with self._lock:
            if self._cleanup_uncertain:
                self._response = None
                self._error = self._transport_error(
                    "Bundled cleanup is uncertain. Save your work and restart Blender before trying again."
                )
                self._state = "cleanup_uncertain"
                return
            if self._cancel_requested.is_set():
                self._response = None
                self._error = self._cancellation_error()
                self._state = "cancelled"
            elif error is not None:
                self._error = error
                self._state = "failed"
            else:
                self._response = response
                self._state = "ready"
            self._finished.set()
