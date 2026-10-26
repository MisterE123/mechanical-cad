# ADR 0008: per-operation backend capability evidence

Status: accepted for staged implementation, 2026-10-17. Not implemented or
release-qualified by this decision. The 0.5.1 installation limitation is unchanged.

Implementation status: the [unreleased boundary](../BACKEND_CAPABILITY_MILESTONE.md)
provides the server/client wire, evidence and bounded transport leaves, and now
converts the Blender owners and current-evidence readers. The frozen functional
source passed independent and automated native qualification; exact installed
0.5.2 package GUI qualification remains a separate gate.

## Decision

Freeze the reviewed [capability contract](../architecture/backend_capability/CAPABILITY_PROPOSAL.md)
and its exact capability names. Every new production backend operation must send
an explicit `backend_contract` and validate a receipt made by the same sidecar
process before admitting its operation evidence. Older sidecars reject the
unknown field. A separate cached handshake, version string or fallback to an
unguarded request cannot authorize an operation.

The contract composes around existing operation validators. It binds the full
guarded request, while existing operation fingerprints still bind the exact
inner request. Canonical schemas, formulas, IDs, saved draft bytes and legacy
unguarded responses remain unchanged. Production operations use explicit typed
result 2 for schema-1/2 data. Arc/result-3 capabilities are advertised only when
their separately reviewed implementations are complete.

Potentially solving actions require the safeguard marker from the actual
imported solver adapter. Pure canonical snapshots require the contract but do
not import the solver, engine or native dependencies. Snapshot evidence cannot
be promoted into solve, solid, export or Finish authority.

The first identity policy supports direct Linux Python executables: preserve
the virtualenv invocation path and compare its child-observed resolved target
as well. Bind the selected source/import origins. Prefix and version fields are
bounded diagnostics, not authentication or inferred dependency correctness.

The guarded envelope gets a fixed 4 KiB and 36-value/container-node metadata
allowance. The inner operation independently retains its previous budgets.
Unknown variants, fields and unsatisfied requirements fail closed before
dispatch. A missing or invalid reply after export launch still leaves the file
outcome unknown; there is no automatic retry.

## Publication and lifecycle

Carry immutable guarded evidence through every Part, geometry, Rectangle,
general-sketch, snapshot and assembly consumer. A matching legacy dictionary or
saved CURRENT label is not authority. Keep reusable same-session evidence
separate from one-shot completion and publication tokens.

One shared configuration/lifetime generation revokes pending and completed
evidence on supported preference changes, including A→B→A. Rebind, rollback,
Undo/load and cleanup cannot restore revoked authority. Preserve authored state
and visibly stale display. Observe effective environment defaults at the named
boundaries; do not claim to detect invisible environment mutations between them.

Reuse the existing execution lease and cleanup supervisor. Guarded synchronous
execution uses the bounded managed transport. Do not add a background handshake
service, second lifecycle owner or native code inside Blender.

## Implementation gates

1. Pure core/client contracts and exact compatibility fixtures.
2. Same-process core admission, with old unguarded behavior preserved.
3. Shared backend selection/evidence and bounded transport adapters.
4. Convert every production sink and lifetime boundary before any cutover.
5. Independent mutation/bypass audit, full native tests, deliberately mismatched
   installed backends, corrected-settings GUI recovery and exact package checks.

The [wire review](../architecture/backend_capability/CAPABILITY_WIRE_REVIEW.md)
and [publication review](../architecture/backend_capability/CAPABILITY_PUBLICATION_REVIEW.md)
contain the required negative cases and explicit consumer inventory. Their
approval is architectural only. No partially converted add-on may be presented
as mixed-install safe.
