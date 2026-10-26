"""Explicit staged repair service above canonical document transactions.

Storage/lifecycle live below document_state. This service prepares and publishes
only a complete, successful repair through the unchanged canonical coordinator.
"""

import copy
import json

from . import (
    backend_runtime,
    bridge,
    document_state,
    repair_intent,
    repair_scope,
    staged_edit_store,
)
from .staged_edit_store import (
    _supervise as _supervise,
)
from .staged_edit_store import after_save as after_save
from .staged_edit_store import before_save as before_save
from .staged_edit_store import (
    cancel_all as cancel_all,
)
from .staged_edit_store import (
    current as current,
)
from .staged_edit_store import (
    discard as discard,
)
from .staged_edit_store import discard_saved as discard_saved
from .staged_edit_store import (
    require as require,
)
from .staged_edit_store import (
    require_none as require_none,
)
from .staged_edit_store import saved_raw as saved_raw


class _RepairKept(Exception):
    """Internal control flow: stop before canonical publication."""


def retain(context, document, feature_id, evidence, binding):
    """Compatibility service entry: validate authority before transient storage."""
    require_none(context)
    document_state._assert_binding(context, binding)
    accepted = document_state.current_part_result(context)
    if accepted is None or accepted.get("status") != "ok":
        return False
    response = document_state._evidence_projection(context, document, evidence, binding)
    return staged_edit_store.retain_validated(
        context,
        document,
        feature_id,
        response["result"],
        binding,
        assert_binding=document_state._assert_binding,
    )


def _binding_succeeds(context, candidate, feature_id, target, rows):
    row = rows.get(feature_id, {})
    if row.get("status") == "ok":
        return True
    if next(f for f in candidate["features"] if f["id"] == feature_id)["kind"] == "extrude_to_face":
        # A target catalog or resolved plane cannot prove a completed extrusion.
        # End-face repairs never use the sketch-only partial binding probe.
        return False
    if target is None:
        # Native replay resolves support before projection. A failed projection
        # with an actual resolved support plane proves this support-only repair.
        return (
            bool(row.get("support_plane"))
            and (row.get("error") or {}).get("code") == "invalid_sketch_projection"
        )
    probe = _binding_probe(candidate, feature_id, target)
    probe_binding = document_state._capture_binding(context)
    evidence = document_state._run_sidecar(context, probe, binding=probe_binding)
    try:
        result = document_state._evidence_projection(context, probe, evidence, probe_binding)[
            "result"
        ]
        return next(f for f in result["features"] if f["id"] == feature_id)["status"] == "ok"
    finally:
        evidence.publication.cancel()


def _binding_probe(candidate, feature_id, target):
    # A validation-only probe evaluates this exact binding natively even when
    # another reference in the same sketch fails first. Never publish the probe.
    probe = copy.deepcopy(candidate)
    feature = next(f for f in probe["features"] if f["id"] == feature_id)
    feature["projections"] = [p for p in feature["projections"] if p["target"] == target]
    from .sketch_projection import projection_input_types

    ports = set(projection_input_types(feature["projections"])) | {"support"}
    feature["inputs"] = {p: source for p, source in feature["inputs"].items() if p in ports}
    sketch = feature["sketch"]
    points = set()
    for collection in ("lines", "circles", "arcs"):
        if collection not in sketch:
            continue
        sketch[collection] = [e for e in sketch.get(collection, []) if e["id"] == target]
        for entity in sketch[collection]:
            points.update(entity[k] for k in ("start", "end", "center") if k in entity)
    sketch["points"] = [p for p in sketch["points"] if p["id"] in points]
    sketch["constraints"] = [
        c
        for c in sketch["constraints"]
        if c.get("kind") == "fixed"
        and c.get("refs") in [[p] for p in points]
        or c.get("kind") == "radius"
        and c.get("refs") == [target]
    ]
    # Do not solve dependent relations against stale, unresolved drivers. This
    # minimal construction-only sketch proves only the selected binding; every
    # real constraint remains in candidate and must pass before publication.
    return probe


def undo_repair(context, token):
    document_state.require_no_sketch_draft(context)
    staged_edit_store.undo_repair(context, token)


def accept(context, token, candidate):
    """Return True on publication, None on proposal-only progress, False on failure."""
    document_state.require_no_sketch_draft(context)
    proposal = require(context, token)
    before = proposal.document
    ancestry_document = json.loads(proposal.repairs[0][0]) if proposal.repairs else before
    try:
        repaired_id, target = repair_scope.validate_transition(
            before, candidate, proposal.feature_id, {row["id"] for row in proposal.failures}
        )
    except ValueError as exc:
        raise bridge.BridgeError(str(exc)) from exc

    def validate_layout():
        if (
            proposal.annotation_after is not None
            and context.scene.mechanical_cad.sketch_annotation_json != proposal.annotation_before
        ):
            raise bridge.BridgeError(
                "Saved annotation layout changed; discard and retry the sketch edit."
            )

    def publish_layout():
        validate_layout()
        context.scene.mechanical_cad.sketch_annotation_json = proposal.annotation_after

    def validate_result(_evidence, _binding):
        require(context, token)
        validate_layout()
        response = document_state._evidence_projection(context, candidate, _evidence, _binding)
        result = response["result"]
        if result.get("status") == "ok":
            return
        rows = {row["id"]: row for row in result["features"]}
        if (
            rows.get(proposal.feature_id, {}).get("status") == "ok"
            and staged_edit_store.repairable_failures(
                candidate, proposal.feature_id, result, ancestry_document=ancestry_document
            )
            and _binding_succeeds(context, candidate, repaired_id, target, rows)
        ):
            validate_layout()
            staged_edit_store.advance_validated(context, token, candidate, result)
            raise _RepairKept()

    def _accept_replayed():
        with document_state.replay_guard(context):
            require(context, token)
            validate_layout()
            success = document_state._commit_candidate_locked(
                context,
                copy.deepcopy(candidate),
                context.scene.mechanical_cad.document_path,
                validate_result=validate_result,
                **(
                    {"validate_publication": publish_layout}
                    if proposal.annotation_after is not None
                    else {}
                ),
                staged_token=token,
            )
        if success:
            discard(context)
        return success

    try:
        return _accept_replayed()
    except _RepairKept:
        return None


class ResumeValidation:
    """Main-thread validation plan shared by synchronous and modal execution.

    It yields exact replay/probe documents, never transport handles or authority.
    The runner must project genuine guarded evidence against each exact document
    before advance(). Only install() consumes saved intent after all steps pass.
    """

    def __init__(self, context):
        self.retired = False
        self.reservation = None
        self.raw = staged_edit_store.saved_raw(context)
        if not self.raw:
            raise bridge.BridgeError("There is no saved repair intent to resume.")
        staged_edit_store.require_none(context, resuming_raw=self.raw)
        self.value = repair_intent.decode(self.raw)
        self.binding = document_state._capture_binding(context)
        self.results = []
        self._diagnostic_bytes = 0
        self.complete = False
        self.document = None
        self.label = ""
        self.completed_requests = 0
        self.assert_current(context)
        self._iterator = self._steps()
        try:
            self.advance(context)
        except Exception:
            self.retire()
            raise

    def retire(self):
        """Sever RNA immediately, including the generator's self-reference cycle."""
        self.retired = True
        iterator = getattr(self, "_iterator", None)
        self._iterator = None
        self.binding = self.document = self.value = None
        self.results = []
        self.raw = ""
        if iterator is not None:
            try:
                iterator.close()
            except ValueError:
                # A backend observation may revoke us from inside advance().
                # Its subsequent owner check rejects; RNA is already detached.
                pass

    def assert_current(self, context):
        from . import workspace

        if self.retired:
            raise bridge.BridgeError("Repair Resume validation was retired.")

        document_state._assert_binding(context, self.binding)
        document_state.require_no_sketch_draft(context)
        if workspace.active_draft() is not None:
            raise bridge.BridgeError("Finish or cancel the active sketch before Resume Repair.")
        if self.reservation is not None:
            staged_edit_store.require_resume(self.reservation)
        staged_edit_store.require_none(
            context, resuming_raw=self.raw, resuming_token=self.reservation
        )
        state = context.scene.mechanical_cad
        if (
            state.repair_intent_json != self.raw
            or self.binding["document_json"] != self.value["base_json"]
            or self.binding["owner_id"] != self.value["owner_id"]
            or self.binding["scale"] != self.value["scale"]
            or backend_runtime.configuration(context)[1] != self.binding["deflection"]
            or self.value["annotation_after"] is not None
            and state.sketch_annotation_json != self.value["annotation_before"]
        ):
            raise bridge.BridgeError(
                "Saved repair base, units, annotations, settings or intent changed; no saved text overwritten."
            )

        # Backend configuration observation can synchronously revoke a modal owner.
        if self.reservation is not None:
            staged_edit_store.require_resume(self.reservation)

    def _steps(self):
        result = yield repair_intent.document(self.value["base_json"]), "Checking accepted base"
        if result["status"] != "ok":
            raise bridge.BridgeError(
                "Accepted base no longer validates; saved repair text retained."
            )
        candidates = [repair_intent.document(text) for text in self.value["states"]]
        for index, candidate in enumerate(candidates):
            result = yield candidate, f"Checking proposal {index + 1} of {len(candidates)}"
            rows = {row["id"]: row for row in result["features"]}
            if rows.get(self.value["feature_id"], {}).get(
                "status"
            ) != "ok" or not staged_edit_store.repairable_failures(
                candidate, self.value["feature_id"], result, ancestry_document=candidates[0]
            ):
                raise bridge.BridgeError(
                    "Saved proposal is no longer an eligible reference-only repair; original text retained."
                )
            if index:
                repaired_id, target = repair_scope.validate_transition(
                    candidates[index - 1],
                    candidate,
                    self.value["feature_id"],
                    {
                        row["id"]
                        for row in self.results[-1]["features"]
                        if row["status"] == "failed"
                    },
                )
                row = rows.get(repaired_id, {})
                if row.get("status") != "ok":
                    repaired = next(f for f in candidate["features"] if f["id"] == repaired_id)
                    if repaired["kind"] == "extrude_to_face":
                        valid = False
                    elif target is None:
                        valid = (
                            bool(row.get("support_plane"))
                            and (row.get("error") or {}).get("code") == "invalid_sketch_projection"
                        )
                    else:
                        proof = yield (
                            _binding_probe(candidate, repaired_id, target),
                            f"Checking repaired binding {index}",
                        )
                        valid = (
                            next(f for f in proof["features"] if f["id"] == repaired_id)["status"]
                            == "ok"
                        )
                    if not valid:
                        raise bridge.BridgeError(
                            "Saved repair transition no longer validates; original text retained."
                        )
            failures = [row for row in result["features"] if row["status"] == "failed"]
            self._diagnostic_bytes += len(json.dumps(failures, allow_nan=False).encode())
            if self._diagnostic_bytes > 16 * 1024 * 1024:
                raise bridge.BridgeError(
                    "Fresh repair diagnostics exceed the 16 MiB history limit; saved intent retained."
                )
            self.results.append({"features": failures})
            # Successful tessellations are not proposal history. Keep only the
            # freshly validated failure rows needed by repair UI and local Undo.
            result = rows = row = proof = None

    def advance(self, context, result=None):
        self.assert_current(context)
        if self.complete:
            raise bridge.BridgeError("Repair Resume already completed.")
        try:
            self.document, self.label = self._iterator.send(result)
        except StopIteration:
            self.complete = True
            self.document = None
            self.label = "Repair history validated"
        if result is not None:
            self.completed_requests += 1
        self.assert_current(context)

    def install(self, context):
        self.assert_current(context)
        if not self.complete:
            raise bridge.BridgeError("Repair Resume validation is incomplete.")
        return staged_edit_store.restore_validated(
            context,
            self.raw,
            self.value,
            self.results,
            self.binding,
            assert_binding=document_state._assert_binding,
            reservation=self.reservation,
        )


def resume(context):
    """Synchronous script/EXEC API; user Invoke uses the guarded modal runner."""
    plan = None
    try:
        plan = ResumeValidation(context)
        with document_state.replay_guard(context):
            while not plan.complete:
                plan.assert_current(context)
                evidence = document_state._run_sidecar(context, plan.document, binding=plan.binding)
                try:
                    result = document_state._evidence_projection(
                        context, plan.document, evidence, plan.binding
                    )["result"]
                    plan.advance(context, result)
                finally:
                    evidence.publication.cancel()
            return plan.install(context)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise bridge.BridgeError(
            "Cannot resume saved repair; original text retained: " + str(exc)
        ) from exc
    finally:
        if plan is not None:
            plan.retire()
