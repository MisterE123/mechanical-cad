"""Dormant, bounded result-3 service transport returning detached JSON data.

Nothing imports this module from the live add-on. It grants no current, owner,
publication, display or export authority. Callers own any external execution
slot until cleanup has completed. The same captured selection is rechecked at
launch, polling, consumption and after strict validation; it never selects a
replacement backend or retries an operation.
"""

from __future__ import annotations

import json

from . import backend_contracts as contracts
from . import bridge, result_v3
from .backend_selection import BackendSelection
from .sidecar_job import SidecarJob


class DataOnlyJob:
    """One fresh guarded request with copied data as its only completion value.

    ``current_selection`` is a comparison supplier, never launch configuration.
    A failed observation cancels and reaps before returning. This data-service
    harness is deliberately separate from UI/modal process supervision.
    """

    def __init__(self, operation, selection, *, current_selection):
        if type(selection) is not BackendSelection or not callable(current_selection):
            raise bridge.BridgeError("Data-only service requires a captured backend selection.")
        if selection.bundled_policy is not None:
            raise bridge.BridgeError(
                "Bundled backends are unavailable to the dormant data-only service."
            )
        ordinary = result_v3.validate_request(operation)
        if (
            type(ordinary.get("result_version")) is not int
            or ordinary["result_version"] != 3
            or ordinary.get("action", "replay") not in {"solve_sketch", "replay"}
        ):
            raise bridge.BridgeError("Data-only service supports only solve/replay result 3.")
        self._selection = selection
        self._current_selection = current_selection
        self.prepared = contracts.prepare_request(ordinary)
        self._wire_payload = self.prepared.payload
        self._job = None
        self._assert_current()
        self._job = SidecarJob.from_selection(self._verified_prepared(), selection)

    def _verified_prepared(self):
        prepared = contracts.prepare_guarded_request(json.loads(self._wire_payload))
        if type(self.prepared) is not contracts.PreparedRequest or self.prepared != prepared:
            raise contracts.BackendContractError("Prepared request differs from captured bytes.")
        return prepared

    def _assert_current(self):
        self.selection.assert_current(self._current_selection())

    def _cleanup(self):
        if self._job is not None:
            try:
                self._job.cancel()
            finally:
                self._job.wait()

    @property
    def selection(self):
        """The original launch selection cannot be replaced through the API."""
        return self._selection

    @property
    def state(self):
        return self._job.state

    @property
    def done(self):
        """Process cleanup only; this property never implies CAD authority."""
        return self._job.done

    def request_snapshot(self):
        return json.loads(self._wire_payload)

    def start(self):
        try:
            self._assert_current()
            self._verified_prepared()
            if self._job.state != "created":
                raise bridge.BridgeError("Data-only service can only be started once.")
            self._job.start()
            return self
        except BaseException:
            self._cleanup()
            raise

    def poll(self):
        try:
            self._assert_current()
            return self._job.poll()
        except BaseException:
            self._cleanup()
            raise

    def wait(self, timeout=None):
        """Wait for cleanup, without consuming data or claiming it is current."""
        return self._job.wait(timeout)

    def cancel(self):
        """Invalidate unconsumed data and finish owned process/file cleanup."""
        try:
            return self._job.cancel()
        finally:
            self._job.wait()

    def result(self):
        """Consume once, validate receipt and original inner source, then copy."""
        try:
            self._assert_current()
            prepared = self._verified_prepared()
            response = self._job.result()
            receipt = contracts.validate_receipt(
                prepared.guarded_request(), response, self.selection
            )
            projected = contracts.project_response(response)
            ordinary = prepared.operation_request()
            if receipt["phase"] == "rejected_before_dispatch":
                validated = contracts.common_failure(ordinary, projected, contract_level=True)
            elif projected.get("result") is None and "input_fingerprint" not in projected:
                validated = contracts.common_failure(ordinary, projected)
            else:
                validated = result_v3.validate_response(ordinary, projected)
            detached = contracts.response_snapshot(validated)
            self._verified_prepared()
            self._assert_current()
            return detached
        except BaseException:
            self._cleanup()
            raise


def execute(operation, selection, *, current_selection):
    """Run once through the same bounded job, holding no owner/publication token."""
    job = DataOnlyJob(operation, selection, current_selection=current_selection)
    try:
        job.start()
        while not job.wait(0.05):
            job.poll()
        return job.result()
    except BaseException:
        job.cancel()
        raise
