# Unreleased backend capability boundary

This development checkpoint implements the wire/evidence foundation and Blender
owner conversion of [ADR 0008](adr/0008-per-operation-backend-capabilities.md).
The functional source is qualified as recorded below; the 0.5.2 candidate still
requires exact installed-package GUI review. The delivered 0.5.1 package
is unchanged and still requires its documented manual backend verification.

## Implemented

- Optional per-operation admission around the unchanged legacy dispatcher, with
  actual imported solver capability, strict same-process receipts, independent
  inner/outer budgets, exact fingerprints and Linux executable/source identity.
- Native-free client requirements, captured launch settings, immutable retained
  evidence and a separate one-shot publication claim. Cancelled unpublished
  evidence cannot supply current seed/DoF authority; consumed evidence can be
  reread while its owner, generation and lifetime remain current.
- A guarded job and synchronous adapter over the existing file-backed,
  bounded, cancellable process transport. No new native process owner or lease.
- One shared generation/lifetime, including observed effective-setting changes,
  explicit preference A→B→A revocation, and load/history/disable/re-enable wiring.
- Guarded production Part, Rectangle, general-sketch, geometry/export, canonical
  capture and Assembly paths. Fresh completion is bound to its exact captured
  guarded request, including nonce; same-owner evidence for another operation
  cannot be substituted even when the ordinary document bytes are identical.
- Current UI, solved seeds, prepared constraint actions, failed-solve diagnostics
  and formula conversion read live immutable evidence. Persisted status/report
  fields remain historical caches. Drawing never launches native work.
- Generation-aware rollback and same-owner transfer of the full General
  solve/downstream evidence chain. Saved bytes cannot recreate publication claims.

All nine production action families use the guarded route. Canonical snapshots remain solver/native
free and never provide solve, solid, export or Finish authority. Future arc and
result-3 requirements are recognized but remain unadvertised and unsupported.
The audited DoF guard functions are unchanged. Legacy unguarded requests remain
available for compatibility and explicit tooling; they are not guarded evidence.

## Important provenance boundary

The low-level `guarded_evidence.accept_response` validator is stateless. Calling
it repeatedly on saved request/response bytes can create separate validation
objects; it is not a durable replay-prevention service. Production constructs
evidence only through a fresh `GuardedJob.result` or `execute`, then retains that
same object. Clones, rollback and saved data may not mint new
publication claims by calling the low-level factory. No global nonce registry or
security-attestation claim is introduced.

A missing or invalid receipt after an export launch leaves the file outcome
unknown. A valid typed successful export followed by a stale handoff retains
historical proof of the write while rejecting current display authority. No
automatic retry or file rollback is implied.

## Qualification and next gate

Foundation tests cover real-process interoperability, all nine native actions,
resource/identity mutations, native-free snapshot/client imports, old-sidecar
rejection, transport cleanup, export uncertainty and generation revocation.
The exact foundation at `9f6fce6e45feb84b4cf65b9b2140b69b4c227fe0` passed 245
independent cases, including unavailable-RNA revocation, with all 919 archived
files verified unchanged. The portable compatibility fixtures retain exact
historical source bytes and hashes; Git is not needed to run their assertions.
Foundation results do not qualify the later owner conversion.

The owner cutover adds dedicated native Part, General, Assembly and lifecycle/UI
gates. They join the existing regression suite, including two-process persistence
and process-exit cleanup. The frozen functional commit `61b59fc889b6a772cd24abc662ae0a6384543de0` passed
Ruff, formatting, 4,018 pytest cases with 19,597 subtests, all 45 serial native
gates and both real process-exit gates on Blender 5.2.2 Linux. All 930 frozen
source files remained unchanged. An independent exact-source audit passed 117
owner-bypass checks across ten sections/all nine actions, plus 67 independent
cleanup and retained-outline correction checks.

The 0.5.2 packaging commit changes release metadata, verification expectations
and documentation only. Exact installed-ZIP GUI mismatch/recovery remains open;
this record makes no final package or GUI qualification claim.

The mandatory production cutover inventory is in the frozen
[publication review](architecture/backend_capability/CAPABILITY_PUBLICATION_REVIEW.md).
The conversion is reviewed against every Part, geometry, Rectangle, general
sketch, snapshot and Assembly sink, with preference/lifecycle/rollback
invalidation. Actual installed mismatch/recovery GUI checks remain required
before a release can claim the boundary is qualified.
