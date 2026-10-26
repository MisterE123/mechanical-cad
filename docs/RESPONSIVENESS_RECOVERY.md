# Responsiveness reconstruction after workspace loss

These commits reconstruct the post-1.18 changes from retained conversation source
and descriptions. They are equivalent reimplementations, not recovered historical
Git objects. Historical acceptance and timing measurements do not qualify this
new code; fresh focused review and validation are required.

## Combined receipt and projection

One full bounded detached response snapshot is shared in a dispatched read.
Receipt validation and action validators remain unchanged. The existing
receipt-only bounded snapshot is retained as an independent output, preventing
cross-output aliases even when the original JSON-like input has a shared DAG.
Standalone APIs remain bounded and detached. Pre-dispatch rejection intentionally
retains its separate common-failure projection traversal.

At reconstruction commit time: syntax/diff checks only; pytest/runtime recovery
was pending. No new native timing or GUI qualification is claimed.

## Synchronous feature-history rows

Recovered row scope derives immutable ID/icon/assumed-plane tuples from one proof
and its associated fresh guard. The full retained identity leaf and publication
revocation check remain in that guard. Exact scene/state/items/READY binding is
checked before and after every row guard, including changes during inspection.
Nested scopes restore their own outer frame; finally cleanup prevents reuse after
exceptions. Standalone/deferred rows and all action readers prove independently.
Launcher placement tests now inspect the wrapper call without dropping ordering.
Fresh focused tests are running; no restored native UI timing is claimed.

## Panel-local display snapshot

Recovered parent panel sharing carries only immutable feature detail/status/icon
strings and formatted volume. Status, selected detail and volume consumption each
recheck the captured proof's original guard; selected-feature binding is checked
before and after. Conflict details retain ERROR while redundancy retains INFO.
Support and geometry-report authority remain independent at this stage.

Fresh stage 1+2 run: 93 targeted tests passed (combined receipt/projection, row
scope, launcher placement and existing current-reader regression matrix). Fresh
independent stage 1 review accepted the receipt leaf, with 15 parity/resource/
alias tests passed. Panel tests are pending at this preservation checkpoint.

## Selected attached-sketch support sharing

Support disclosure now takes the explicit panel-local snapshot. It contains only
the selected attached constrained sketch's immutable status/icon/full Why/error
strings plus exact source serialization (including policy and orientation).
Selection and supplied source are checked before and after the original guard.
Stale bindings fall back to unverified. Draft support and standalone disclosure
retain their previous behavior; Review Support and other actions remain fresh.

The compact support-disclosure base is recovered separately as 564618d (locally
cherry-picked b93f40d). The mocked disclosure fixture now wires its support-decision
mock to the extracted pure formatter. This does not change production behavior.
Stage 3 fresh focused run passed 18 tests. Stage 4 tests and fresh independent
review are pending at this source-preservation checkpoint.

## Fresh recovered-code evidence (2026-10-24)

- Stage 4 support/panel/disclosure run: 45 passed in 11.94 s.
- Independent reviewer: 48 focused tests plus five additional late-mutation cases
  passed, with the final selected-support set still being checked at this note.
- Ruff checks and `git diff --check` clean on changed code/tests.
- Restored official Blender 5.2.2 background callback diagnostic completed with
  `RECOVERED_SUPPORT_PRESENTATION_PROFILE_OK` and process exit 0. Same saved
  repository model `examples/topology_support/two_cut_source_bound.mcad.json`,
  11 nodes, selected feature `attached`, same process before/after:
  - Standard sidebar: 0.1090 s / two proofs → 0.0594 s / one proof.
  - Workspace history: 0.0982 s / two proofs → 0.0551 s / one proof.
  - Every emitted label and operator property, including complete Why strings,
    matched exactly.

This last comparison isolates recovered selected-support sharing against its
immediate parent panel implementation (b93f40d), not against release 1.18. It is a
single native callback diagnostic with a non-rendering layout sink, not a GUI
responsiveness guarantee. Historical 39-node timings were not reused: that graph
used face-circle recipes and was ineligible for constrained-support disclosure.
No saved model or desktop window was modified. Local diagnostic artifacts are
under `recovery_inputs/latency_native/`; existing tests provide durable guard and
proof-count regression coverage. No full-suite or packaged-release claim is made.
