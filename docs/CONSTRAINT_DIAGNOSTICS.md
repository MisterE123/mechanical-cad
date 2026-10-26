# Failed sketch diagnostics contract

This is a pure foundation for the proposed next constraint UI. Session storage
and inspector integration are separate from this module, which owns no rendering,
commands, persistence, or registration. The immutable 0.4 release is unchanged.

## Capture and consume

After the existing owner has accepted a completed `solve_sketch` job against its
current exact execution identity, it may construct:

```python
diagnostics = FailureDiagnostics(
    response,
    exact_request,
    session_id=owner.session_id,
    command_revision=owner.commands.revision,
    input_token=owner.input_token,
    input_revision=(
        owner.commands.pending_edit.input_revision
        if owner.commands.pending_edit is not None
        else None
    ),
)
```

Construction always runs `sketch_action_bridge.validate_solve_response`, including
the existing strict `sketch_bridge` nested report validator. It accepts only a
failed native report: `inconsistent`, `didnt_converge`, or `too_many_unknowns`.
A successful solve, even one with an unavailable profile, is not a constraint
failure. Malformed or contradictory evidence is rejected. Process/action errors
without a native report are rejected here and remain ordinary owner error text.
The response's raw request fingerprint, canonical document identity/hash, selected
feature, report and diagnostic IDs must all pass the existing validator.

Before displaying any candidates, ask for an exact match using the current
request and bindings:

```python
current = diagnostics.for_current(
    current_exact_request,
    session_id=owner.session_id,
    command_revision=owner.commands.revision,
    input_token=owner.input_token,
    input_revision=(
        owner.commands.pending_edit.input_revision
        if owner.commands.pending_edit is not None
        else None
    ),
)
if current is not None:
    # Inspector labels these as diagnostic candidates, not proven causes.
    candidate_ids = current.candidate_constraint_ids
```

Any mismatch or malformed current binding returns `None`. Reusing the identities
stored on the snapshot instead of obtaining current owner values defeats the
caller contract. A canonically equivalent but differently expressed raw request
does not match. Changes to source IDs, kinds, refs, expressions, targets, point or
radius seeds, parameter values, selected feature or document metadata therefore
cannot silently reuse diagnostics. The request fingerprint covers the complete
request rather than only the currently selected relation.

The session ID is nonempty UTF-8 text up to 256 characters; the input token is
UTF-8 text up to 256 characters and may initially be empty. Command revisions are
integers from 0 through 2^63-1, excluding booleans. `input_revision` is an integer
in the same range for pending input, or `None` for an ordinary solve. The input
token identifies the editing lease; every raw edit must advance the independent
input revision even if the exact request later repeats (A → B → A). Existing
request/response resource limits and exact report schema limits apply. Lone
Unicode surrogates are rejected. All retained members are immutable scalars,
`None`, or tuples, with no mutable input aliases.

## Meaning and limits

`candidate_constraint_ids` preserves the report's failed-ID list exactly. Every
ID refers to an authored constraint in the exact request. These are inspection
candidates, never proof that deleting a particular relation will fix the sketch.
Empty candidates do not mean the sketch is consistent. In particular,
`didnt_converge` may be a native nonconvergence result or the core's rejection of
out-of-domain solved data, invalid DoF, or excessive residual after nominal
native success. Do not relabel it as a proven conflicting relation.

`redundant_constraint_ids` separately preserves the existing report's redundancy
list. The core records exact duplicate relations during compilation, including
when the solve subsequently fails. Those IDs are not automatically additional
failure candidates and are not a deletion recommendation. The two lists are not
combined, sorted, deduplicated, or heuristically expanded by this adapter.

The snapshot retains status, error code/text, stable source IDs, canonical source
hash, raw request fingerprint and owner bindings. It retains no request payload,
response payload, solved geometry, current DoF, residual, resolved dimensions,
profile readiness, or release seeds. It supplies no Finish/export permission and
does not relax the existing validated-solution gate for relation deletion.
There is no persistence codec or restored-draft authority for diagnostics.

## Owner integration and clear points

The shared session and existing pending-job lifecycle remain the only owners.
This module does not cancel work, register callbacks, mutate a draft, or decide
whether an asynchronous result is still live. Before capture, the owner must
perform its normal exact execution-identity and current-context acceptance gate;
the matcher is an additional display check, not an alternate acceptance path.

The owner must drop its stored snapshot:

- Before starting any new Check/Finish or replacing pending work, and on Check
  cancellation, timeout, transport failure, malformed result, or stale result.
- On any authored command, Undo/Redo, source edit, document/base replacement,
  selected source feature change, or raw-input edit/apply/cancel. If a diagnostic
  presentation is tied to a narrower UI selection, changing that selection also
  invalidates that presentation. A true unchanged-command no-op need not clear it.
- On accepting a successful solve or a result without a native failure report.
- On Suspend/Resume or draft restoration, Finish, Cancel Sketch, scene/window/
  workspace replacement, owner retirement/cleanup, file load, and add-on disable.

Cancellation and retirement can leave the exact request/revision unchanged, so
the matcher intentionally cannot detect them by itself. Dropping the snapshot is
mandatory at those boundaries. Reopening or restoring an identical draft needs
a new session identity and a fresh Check. Never rebind old diagnostics to a new
owner merely because the canonical document or geometry looks the same.
