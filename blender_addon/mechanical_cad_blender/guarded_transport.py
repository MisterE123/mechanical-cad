"""Opt-in bounded transport for one captured, guarded backend operation.

This adapter accesses no Blender data. Synchronous execution binds the existing
lease or owns an empty slot; async owners retain their own lease and fresh selection
comparison at each observation boundary. Transport completion is one-shot;
retained operation evidence has a separate publication claim.
"""

from __future__ import annotations

from . import backend_contracts, bridge, execution_lease
from .backend_selection import BackendSelection, SelectionError
from .guarded_evidence import GuardedEvidence, GuardedFailure, accept_response
from .sidecar_job import SidecarJob

_EXPORT_ACTIONS = frozenset({"export_step", "export_stl", "assembly_export_step"})


class GuardedOperationError(bridge.BridgeError):
    """A bounded operation error, optionally retaining historical file evidence.

    The historical evidence cannot authorize current display or publication. Its
    normal revalidation still requires the original owner and a current selection.
    """

    def __init__(self, message, *, outcome_unknown=False, historical_export=None, failure=None):
        super().__init__(message, outcome_unknown=outcome_unknown)
        self.historical_export = historical_export
        self.failure = failure


class GuardedJob:
    """One managed process launched from exactly one immutable selection."""

    def __init__(self, prepared, selection, *, owner_token):
        if type(prepared) is not backend_contracts.PreparedRequest:
            raise bridge.BridgeError("Guarded transport requires a prepared request.")
        if type(selection) is not BackendSelection or owner_token is None:
            raise bridge.BridgeError("Guarded transport requires selection and owner identity.")
        self.prepared = prepared
        self.selection = selection
        self._owner_token = owner_token
        self._job = SidecarJob.from_selection(prepared, selection)
        # File-outcome policy belongs to the exact transmitted bytes. Even an
        # illicit mutation of a frozen caller object after launch cannot turn
        # an export's missing/invalid receipt into a definite no-write result.
        self._action = self._job.request_snapshot().get("action", "replay")
        self._start_attempted = False
        self._historical_export = None

    def _error(self, message, *, failure=None, already_uncertain=False):
        # Once start is attempted, a process may have executed before its worker
        # updates a launch flag. Only validated pre-dispatch rejection proves
        # that no operation ran. A typed successful export proves its historical
        # write, independently of current scene/configuration authority.
        if self._historical_export is not None:
            return GuardedOperationError(
                message
                + " The earlier export has a validated write receipt; its file was written."
                + " Current CAD verification remains stale.",
                historical_export=self._historical_export,
                failure=failure,
            )
        if (
            self._start_attempted
            and self._action in _EXPORT_ACTIONS
            and not (failure is not None and failure.definite_no_dispatch)
        ):
            if already_uncertain:
                return GuardedOperationError(message, outcome_unknown=True, failure=failure)
            error = bridge._transport_error({"action": self._action}, message)
            return GuardedOperationError(str(error), outcome_unknown=True, failure=failure)
        return GuardedOperationError(message, failure=failure)

    def _assert_current(self, current_selection):
        try:
            self.selection.assert_current(current_selection)
        except SelectionError as exc:
            self.cancel()
            raise self._error(str(exc)) from exc

    @property
    def state(self):
        """Process-only cleanup observation; it grants no evidence authority."""
        return self._job.state

    @property
    def done(self):
        """Cleanup completion, safe for the existing context-free supervisor."""
        return self._job.done

    @property
    def cleanup_diagnostic(self):
        """Bounded process-only error; reading it never consumes completion."""
        return self._job.cleanup_diagnostic

    def request_snapshot(self):
        return self._job.request_snapshot()

    def start(self, current_selection):
        self._assert_current(current_selection)
        if self._job.state != "created":
            raise self._error("Guarded sidecar job can only be started once.")
        self._start_attempted = True
        try:
            self._job.start()
        except bridge.BridgeError as exc:
            raise self._error(str(exc)) from exc
        return self

    def poll(self, current_selection):
        """Check live settings without blocking; stale work is cancelled."""
        self._assert_current(current_selection)
        return self._job.poll()

    def cancel(self):
        return self._job.cancel()

    def wait(self, timeout=None):
        """Cleanup wait for shutdown/tests/synchronous owners, never UI polling."""
        return self._job.wait(timeout)

    def result(self, current_selection, *, owner_token):
        if owner_token is not self._owner_token:
            self.cancel()
            raise self._error("Guarded completion belongs to another owner.")
        try:
            response = self._job.result()
            accepted = accept_response(
                self.prepared, response, self.selection, owner_token=self._owner_token
            )
        except (bridge.BridgeError, backend_contracts.BackendContractError) as exc:
            # Do not turn a malformed/missing export receipt into a definite
            # no-write error. No fallback or automatic retry is attempted.
            raise self._error(
                str(exc), already_uncertain=getattr(exc, "outcome_unknown", False)
            ) from exc
        if type(accepted) is GuardedFailure:
            raise self._error(accepted.message, failure=accepted)
        if type(accepted) is not GuardedEvidence:
            raise self._error("Guarded operation did not produce validated evidence.")
        if self._action in _EXPORT_ACTIONS and accepted.successful:
            self._historical_export = accepted
        self._assert_current(current_selection)
        # Recheck the retained projection and owner at this handoff. This does
        # not consume its separate publication token.
        try:
            accepted.revalidate(
                current_selection,
                owner_token=owner_token,
                expected_action=self.prepared.action,
                expected_result_version=self.prepared.operation_request().get("result_version"),
            )
        except (SelectionError, backend_contracts.BackendContractError) as exc:
            raise self._error(str(exc)) from exc
        return accepted


def execute(prepared, selection, *, owner_token, current_selection):
    """Run under one atomic execution binding, retaining uncertainty without hanging.

    Live synchronous owners expose their existing token through synchronous().
    An otherwise empty slot is owned here. Busy unscoped/reentrant calls fail
    before constructing a job. No exceptional path may release an uncertain owner.
    """
    try:
        token, transport_owned = execution_lease.bind_transport()
    except execution_lease.LeaseError as exc:
        raise GuardedOperationError(str(exc)) from None
    job = None
    try:
        job = GuardedJob(prepared, selection, owner_token=owner_token)
        try:
            job.start(current_selection())
            if not job.wait():
                raise job._error(job.cleanup_diagnostic or execution_lease.QUARANTINE_MESSAGE)
            try:
                current = current_selection()
            except (ValueError, RuntimeError, OSError) as exc:
                raise job._error(f"Backend selection could not be rechecked: {exc}") from exc
            return job.result(current, owner_token=owner_token)
        except BaseException:
            try:
                job.cancel()
            finally:
                try:
                    cleaned = job.wait()
                except BaseException:
                    cleaned = False
                if not cleaned:
                    execution_lease.quarantine(token, job)
                    raise job._error(
                        job.cleanup_diagnostic or execution_lease.QUARANTINE_MESSAGE
                    ) from None
            raise
    finally:
        execution_lease.finish_transport(token, transport_owned=transport_owned)
