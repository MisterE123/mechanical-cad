"""Retained immutable guarded evidence and a separate one-shot publication claim.

A receipt is only the outer boundary. Every read reruns the existing strict
operation validator against the exact inner request. Nothing here reads Blender,
imports the core, launches native work, or restores authority from saved JSON.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field

from . import backend_contracts as contracts
from . import operation_contracts
from .backend_selection import BackendSelection


@dataclass(frozen=True, slots=True, init=False)
class GuardedFailure:
    """Readable failure-only data with no operation/publication methods."""

    code: str
    message: str
    phase: str
    _response_payload: bytes = field(repr=False)
    _receipt_payload: bytes = field(repr=False)

    @property
    def definite_no_dispatch(self):
        return self.phase == "rejected_before_dispatch"

    @property
    def rejected_before_dispatch(self):
        return self.definite_no_dispatch

    def response_snapshot(self):
        return json.loads(self._response_payload)

    def receipt_snapshot(self):
        return json.loads(self._receipt_payload)


def _prepared(request):
    if type(request) is contracts.PreparedRequest:
        try:
            verified = contracts.prepare_guarded_request(request.guarded_request())
            if verified != request:
                raise ValueError("Prepared request fields differ from its immutable wire bytes.")
            return verified
        except (AttributeError, TypeError, ValueError) as exc:
            raise contracts.BackendContractError("Invalid prepared guarded request.") from exc
    return contracts.prepare_guarded_request(request)


def _failure(response, receipt):
    failure = object.__new__(GuardedFailure)
    for name, value in {
        "code": response["error"]["code"],
        "message": response["error"]["message"],
        "phase": receipt["phase"],
        "_response_payload": contracts._encode(response),
        "_receipt_payload": contracts._encode(receipt),
    }.items():
        object.__setattr__(failure, name, value)
    return failure


def _validate(prepared, response, selection):
    guarded = prepared.guarded_request()
    ordinary = prepared.operation_request()
    receipt, projected = contracts.validate_receipt_and_project(guarded, response, selection)
    if receipt["phase"] == "rejected_before_dispatch":
        return _failure(projected, receipt), receipt
    # A common early failure lacks action/input identity and cannot mint CAD
    # evidence. Its exact action-specific result stamp must still be present.
    if projected.get("result") is None and "input_fingerprint" not in projected:
        try:
            contracts.common_failure(ordinary, projected)
        except contracts.BackendContractError as exc:
            raise contracts.BackendContractError(str(exc), code="backend_response_invalid") from exc
        return _failure(projected, receipt), receipt
    action = prepared.action
    try:
        validated = operation_contracts.validate_response(ordinary, projected)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, RuntimeError) as exc:
        raise contracts.BackendContractError(
            f"Invalid guarded {action} operation evidence: {exc}", code="backend_response_invalid"
        ) from exc
    if projected.get("result") is None:
        return _failure(projected, receipt), receipt
    return validated, receipt


@dataclass(frozen=True, slots=True, init=False)
class GuardedEvidence:
    """Validated immutable bytes; a detached public projection is never authority.

    Only accept_response() constructs a complete record. Revalidation checks
    bytes again, so class identity or a success flag cannot replace validation.
    The owner token uses identity, not user-defined equality or serialization.
    """

    _prepared: contracts.PreparedRequest
    _response_payload: bytes = field(repr=False)
    _projection_payload: bytes = field(repr=False)
    selection: BackendSelection
    _owner_token: object = field(repr=False)
    _publication: EvidencePublication = field(repr=False, compare=False)

    @property
    def action(self):
        return self._prepared.action

    @property
    def phase(self):
        return "dispatched"

    @property
    def successful(self):
        """Historical result status only; current authority requires revalidate()."""
        return json.loads(self._response_payload)["ok"]

    @property
    def publication(self):
        """The same one-shot claim on every access; rereading evidence is reusable."""
        return self._publication

    def guarded_request(self):
        return self._prepared.guarded_request()

    def operation_request(self):
        return self._prepared.operation_request()

    def response_snapshot(self):
        return json.loads(self._response_payload)

    def receipt_snapshot(self):
        return self.response_snapshot()["backend_receipt"]

    def revalidate(
        self,
        current_selection,
        *,
        owner_token,
        projection=None,
        expected_action=None,
        expected_result_version=2,
        require_success=False,
    ):
        """Reread current same-owner evidence, optionally checking a public copy.

        Sinks should specify expected_action (or a collection of allowed actions).
        Old sinks default to result 2. A capable sink must explicitly select 3
        from its exact candidate. Snapshot requires explicit None and its exact
        expected action; None is never a wildcard for potentially-solving work.
        Partial/failed diagnostics are retained but fail require_success=True.
        """
        self._publication._assert_retained_current()
        self.selection.assert_current(current_selection)
        if owner_token is not self._owner_token:
            raise contracts.BackendContractError("Guarded evidence belongs to another owner.")
        if expected_action is not None:
            allowed = {expected_action} if type(expected_action) is str else set(expected_action)
            if self.action not in allowed:
                raise contracts.BackendContractError("Guarded evidence belongs to another action.")
        verified = _prepared(self._prepared)
        ordinary = verified.operation_request()
        if verified.action == "canonical_snapshot":
            if (
                expected_result_version is not None
                or type(expected_action) is not str
                or expected_action != "canonical_snapshot"
            ):
                raise contracts.BackendContractError(
                    "Snapshot evidence requires its explicit action and no result version."
                )
        elif (
            type(expected_result_version) is not int
            or expected_result_version not in (2, 3)
            or expected_result_version != ordinary["result_version"]
        ):
            raise contracts.BackendContractError(
                "Guarded evidence result version differs from owner."
            )
        validated, _ = _validate(verified, self.response_snapshot(), self.selection)
        if type(validated) is GuardedFailure:
            raise contracts.BackendContractError(
                "Failure-only data cannot become operation evidence."
            )
        # Compare encoded tokens, not Python equality (True == 1 == 1.0).
        if contracts._encode(validated, compact=True) != self._projection_payload:
            raise contracts.BackendContractError("Retained operation projection was changed.")
        if projection is not None:
            candidate = _projection_snapshot(projection, verified)
            if contracts._encode(candidate, compact=True) != self._projection_payload:
                raise contracts.BackendContractError("Public operation projection was changed.")
        if require_success and not self.successful:
            raise contracts.BackendContractError(
                "Failed or partial evidence is not successful authority."
            )
        self.selection.assert_current(current_selection)
        self._publication._assert_retained_current()
        return validated


def _projection_snapshot(projection, prepared):
    # The existing assembly validator returns a legacy dict subclass. Retain
    # that public API, but do not trust its flag, class, or response-only seal.
    if prepared.action.startswith("assembly_"):
        from .assembly_bridge import AssemblyResponse

        if type(projection) is AssemblyResponse:
            candidate = contracts.response_snapshot(dict(projection))
            try:
                private_request = contracts._snapshot(projection._request)
                projection.assert_unchanged()
            except (ValueError, TypeError, AttributeError, RuntimeError) as exc:
                raise contracts.BackendContractError(
                    "Assembly operation projection was changed.", code="backend_response_invalid"
                ) from exc
            if contracts._encode(private_request, compact=True) != contracts._encode(
                prepared.operation_request(), compact=True
            ):
                raise contracts.BackendContractError("Assembly projection request was changed.")
            return candidate
    return contracts.response_snapshot(projection)


class EvidencePublication:
    """One claim per accepted operation, independent from immutable rereads.

    Created only by acceptance; attempting to manufacture a second token is an
    invalid claim because consume() checks its association with the evidence.
    Cancellation revokes current retained reads without mutating historical
    response bytes or claiming file undo. Consumed claims remain readable.
    """

    __slots__ = ("_evidence", "_lock", "_state")

    def __init__(self, evidence):
        self._evidence = evidence
        self._lock = threading.RLock()
        self._state = "available"

    def _assert_retained_current(self):
        with self._lock:
            if (
                type(self._evidence) is not GuardedEvidence
                or self._evidence.publication is not self
                or self._state == "cancelled"
            ):
                raise contracts.BackendContractError("Guarded evidence was cancelled.")

    def cancel(self):
        """Revoke an unpublished claim and its current retained authority.

        A consumed publication is no longer pending: its owner's generation or
        lifetime invalidation revokes it, without erasing historical file outcome.
        """
        with self._lock:
            if self._state != "available":
                return False
            self._state = "cancelled"
            return True

    def consume(
        self,
        current_selection,
        *,
        owner_token,
        projection=None,
        expected_action=None,
        expected_result_version=2,
        require_success=False,
    ):
        with self._lock:
            if (
                type(self._evidence) is not GuardedEvidence
                or self._evidence.publication is not self
                or self._state != "available"
            ):
                raise contracts.BackendContractError("Guarded publication is no longer available.")
            result = self._evidence.revalidate(
                current_selection,
                owner_token=owner_token,
                projection=projection,
                expected_action=expected_action,
                expected_result_version=expected_result_version,
                require_success=require_success,
            )
            self._state = "consumed"
            return result


def accept_response(request, response, selection, *, owner_token):
    """Validate both boundaries and retain bytes, or return strict failure-only data."""
    if type(selection) is not BackendSelection:
        raise contracts.BackendContractError("Acceptance requires a captured backend selection.")
    if owner_token is None:
        raise contracts.BackendContractError("Acceptance requires a runtime owner identity.")
    prepared = _prepared(request)
    detached = contracts.response_snapshot(response)
    validated, _ = _validate(prepared, detached, selection)
    if type(validated) is GuardedFailure:
        return validated
    evidence = object.__new__(GuardedEvidence)
    for name, value in {
        "_prepared": prepared,
        "_response_payload": contracts._encode(detached),
        "_projection_payload": contracts._encode(validated, compact=True),
        "selection": selection,
        "_owner_token": owner_token,
    }.items():
        object.__setattr__(evidence, name, value)
    object.__setattr__(evidence, "_publication", EvidencePublication(evidence))
    return evidence
