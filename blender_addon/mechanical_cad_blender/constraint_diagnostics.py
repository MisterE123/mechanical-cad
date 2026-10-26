"""Detached, exact-bound failed-solve diagnostics for a future sketch inspector.

These are inspection candidates, never current solve evidence or permission to
release a relation, Finish, or export. The existing session remains responsible
for retiring diagnostics when its owner, source, input, or pending work changes.
No Blender, transport, native solver, persistence, or lifecycle code belongs here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import operation_contracts, part_contracts
from . import sketch_action_bridge as sketch_action_bridge
from .general_sketch_draft import read_guarded_operation
from .guarded_evidence import GuardedEvidence

MAX_BINDING_TEXT_CHARS = 256
MAX_COMMAND_REVISION = (1 << 63) - 1


class ConstraintDiagnosticsError(ValueError):
    """No trustworthy failed-solve diagnostic snapshot can be constructed."""


def _binding(session_id, command_revision, input_token, input_revision):
    for value, empty_allowed in ((session_id, False), (input_token, True)):
        if (
            type(value) is not str
            or len(value) > MAX_BINDING_TEXT_CHARS
            or (not value and not empty_allowed)
        ):
            raise ValueError("diagnostic session/input binding must be bounded text")
        value.encode("utf-8")
    if type(command_revision) is not int or not 0 <= command_revision <= MAX_COMMAND_REVISION:
        raise ValueError("diagnostic command revision must be a bounded nonnegative integer")
    if input_revision is not None and (
        type(input_revision) is not int or not 0 <= input_revision <= MAX_COMMAND_REVISION
    ):
        raise ValueError("diagnostic input revision must be a bounded nonnegative integer or None")
    return session_id, command_revision, input_token, input_revision


def _require_utf8(snapshot):
    # Only call after the shared resource preflight/validator has bounded this
    # JSON tree. Reject escaped lone surrogates even in source names or errors;
    # the ordinary fingerprint encoder intentionally uses ASCII JSON escaping.
    json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8")


@dataclass(frozen=True, slots=True, init=False)
class FailureDiagnostics:
    """Immutable failure-only information, constructed through strict validation.

    ``response`` must include an actual failed native report, not merely an
    action/transport error. Every retained field is a scalar or tuple of strings;
    neither the request nor the response remains reachable through this object.
    The constructor is deliberately not a field-wise dataclass initializer.
    """

    request_fingerprint: str
    session_id: str
    command_revision: int
    input_token: str
    input_revision: int | None
    document_id: str
    document_hash: str
    feature_id: str
    sketch_id: str
    solver_status: str
    candidate_constraint_ids: tuple[str, ...]
    redundant_constraint_ids: tuple[str, ...]
    error_code: str
    error_message: str

    def __init__(
        self, response, request, *, session_id, command_revision, input_token, input_revision
    ):
        try:
            bindings = _binding(session_id, command_revision, input_token, input_revision)
            request = part_contracts.snapshot_request(request)
            _require_utf8(request)
            # This reuses the entire action/envelope AND nested sketch validator:
            # raw fingerprint, canonical source, authored constraint IDs, status,
            # exact fields and the absence of failed-solve geometry/DoF/profile.
            if request.get("action") != "solve_sketch":
                raise ValueError("constraint diagnostics require solve_sketch")
            validated = operation_contracts.validate_response(request, response)
            if validated["ok"] or validated["result"] is None:
                raise ValueError("constraint diagnostics require a failed native solve report")
            _require_utf8(validated)
            result = validated["result"]
            report = result["sketch"]
            source = next(
                feature
                for feature in request["document"]["features"]
                if feature["id"] == result["feature_id"]
            )
            values = {
                "request_fingerprint": validated["input_fingerprint"],
                "session_id": bindings[0],
                "command_revision": bindings[1],
                "input_token": bindings[2],
                "input_revision": bindings[3],
                "document_id": result["document_id"],
                "document_hash": result["document_hash"],
                "feature_id": result["feature_id"],
                "sketch_id": source["sketch"]["id"],
                "solver_status": report["status"],
                "candidate_constraint_ids": tuple(report["failed_constraints"]),
                "redundant_constraint_ids": tuple(report["redundant_constraints"]),
                "error_code": validated["error"]["code"],
                "error_message": validated["error"]["message"],
            }
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            raise ConstraintDiagnosticsError(
                f"Cannot retain constraint diagnostics: {exc}"
            ) from exc
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @classmethod
    def from_guarded(
        cls, evidence, *, expected_prepared, current_selection, owner_token, **bindings
    ):
        """Production failure diagnostics retain the original same-owner receipt."""
        if type(evidence) is not GuardedEvidence:
            raise ConstraintDiagnosticsError("Diagnostics require guarded operation evidence.")
        response = read_guarded_operation(
            evidence,
            expected_prepared,
            current_selection,
            owner_token=owner_token,
            action="solve_sketch",
        )
        snapshot = cls(response, expected_prepared.operation_request(), **bindings)
        return GuardedFailureDiagnostics(snapshot, evidence, expected_prepared, owner_token)

    def for_current(
        self,
        request,
        *,
        session_id,
        command_revision,
        input_token,
        input_revision,
        current_selection=None,
        owner_token=None,
    ):
        """Return this snapshot only for exactly matching current bindings.

        A mismatch or malformed current binding returns ``None`` (unavailable).
        Callers must supply the current exact request and owner/input identities,
        not replay the identities saved on this object. A matching snapshot still
        supplies no solved geometry, degrees of freedom, or editing authority.
        """
        try:
            if current_selection is not None or owner_token is not None:
                return None  # A legacy diagnostic cannot enter a production current predicate.
            if type(self) is not FailureDiagnostics or _binding(
                session_id, command_revision, input_token, input_revision
            ) != (self.session_id, self.command_revision, self.input_token, self.input_revision):
                return None
            request = part_contracts.snapshot_request(request)
            _require_utf8(request)
            if part_contracts.input_fingerprint(request) != self.request_fingerprint:
                return None
        except (
            ValueError,
            RuntimeError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
            RecursionError,
        ):
            return None
        return self


@dataclass(frozen=True, slots=True)
class GuardedFailureDiagnostics:
    """Runtime ownership wrapper, kept separate from the scalar-only diagnostic.

    Only the detached failure snapshot is exposed to inspection UI. Retaining
    this wrapper does not grant solved-seed, Finish or publication authority.
    """

    snapshot: FailureDiagnostics
    _evidence: GuardedEvidence
    _expected_prepared: object
    _owner_token: object

    def for_current(self, request, *, current_selection, owner_token, **bindings):
        try:
            if (
                type(self.snapshot) is not FailureDiagnostics
                or owner_token is not self._owner_token
            ):
                return None
            if type(self._evidence) is not GuardedEvidence:
                return None
            response = read_guarded_operation(
                self._evidence,
                self._expected_prepared,
                current_selection,
                owner_token=owner_token,
                action="solve_sketch",
            )
            if response["ok"]:
                return None
            validated = FailureDiagnostics(
                response,
                self._expected_prepared.operation_request(),
                session_id=self.snapshot.session_id,
                command_revision=self.snapshot.command_revision,
                input_token=self.snapshot.input_token,
                input_revision=self.snapshot.input_revision,
            )
            if validated != self.snapshot:
                return None
            return self.snapshot.for_current(request, **bindings)
        except (
            ValueError,
            RuntimeError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
            RecursionError,
        ):
            return None


@dataclass(frozen=True, slots=True)
class NativeBuildFailure:
    """Only labeled attempt facts, never coordinates or driver/Part authority."""

    solver_status: str
    remaining_dof: int
    profile_ready: bool
    failed_features: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class GuardedBuildFailure:
    """Runtime-only successful-solve/failed-replay association with exact G pairs."""

    snapshot: NativeBuildFailure
    _solve_evidence: tuple
    _solve_prepared: tuple
    _replay_evidence: GuardedEvidence
    _replay_prepared: object
    _owner_token: object
    _bindings: tuple

    @staticmethod
    def _snapshot(solves, prepared, replay, replay_prepared, selection, owner):
        if (
            type(solves) is not tuple
            or type(prepared) is not tuple
            or not (1 <= len(solves) <= 2 and len(solves) == len(prepared))
        ):
            raise ConstraintDiagnosticsError("The complete solve chain is required.")
        first = None
        document = None
        for index, (evidence, expected) in enumerate(zip(solves, prepared, strict=True)):
            response = read_guarded_operation(
                evidence,
                expected,
                selection,
                owner_token=owner,
                action="solve_sketch" if index == 0 else "replay",
                require_success=True,
            )
            current = expected.operation_request()["document"]
            encoded = json.dumps(current, sort_keys=True, separators=(",", ":"), allow_nan=False)
            if index == 0:
                first, document = response, encoded
            elif encoded != document:
                raise ConstraintDiagnosticsError("The successful evidence chain changed candidate.")
        failed = read_guarded_operation(
            replay, replay_prepared, selection, owner_token=owner, action="replay"
        )
        if failed["ok"] or failed.get("result") is None:
            raise ConstraintDiagnosticsError("A typed failed native replay is required.")
        if (
            json.dumps(
                replay_prepared.operation_request()["document"],
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            != document
        ):
            raise ConstraintDiagnosticsError("The failed replay belongs to another candidate.")
        if replay_prepared.request_id in {item.request_id for item in prepared}:
            raise ConstraintDiagnosticsError("The failed replay needs its own fresh request.")
        failures = tuple(
            (item["id"], item["error"]["code"], item["error"]["message"])
            for item in failed["result"]["features"]
            if item["status"] == "failed"
        )
        if not failures:
            raise ConstraintDiagnosticsError("No failed native feature report is available.")
        solve = first["result"]
        return NativeBuildFailure(
            solve["sketch"]["status"],
            solve["sketch"]["remaining_dof"],
            solve["profile_check"]["ready"],
            failures,
        )

    @classmethod
    def from_guarded(
        cls,
        solve_evidence,
        solve_prepared,
        replay_evidence,
        replay_prepared,
        *,
        current_selection,
        owner_token,
        session_id,
        command_revision,
        input_token,
        input_revision,
    ):
        bindings = _binding(session_id, command_revision, input_token, input_revision)
        snapshot = cls._snapshot(
            solve_evidence,
            solve_prepared,
            replay_evidence,
            replay_prepared,
            current_selection,
            owner_token,
        )
        return cls(
            snapshot,
            solve_evidence,
            solve_prepared,
            replay_evidence,
            replay_prepared,
            owner_token,
            bindings,
        )

    def for_current(
        self,
        request,
        *,
        current_selection,
        owner_token,
        session_id,
        command_revision,
        input_token,
        input_revision,
    ):
        try:
            if (
                owner_token is not self._owner_token
                or _binding(session_id, command_revision, input_token, input_revision)
                != self._bindings
            ):
                return None
            request = part_contracts.snapshot_request(request)
            if json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False) != (
                json.dumps(
                    self._solve_prepared[0].operation_request(),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            ):
                return None
            snapshot = self._snapshot(
                self._solve_evidence,
                self._solve_prepared,
                self._replay_evidence,
                self._replay_prepared,
                current_selection,
                owner_token,
            )
            return self.snapshot if snapshot == self.snapshot else None
        except (
            ValueError,
            RuntimeError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
            RecursionError,
        ):
            return None
