# Unreleased directed-arc core checkpoint

Qualified on 2026-10-17 over the immutable 0.5.1 source commit
`d6f13afbda1dbae5516e5fe53cda533902c595b2`. This is a development checkpoint,
not a new installable release or a claim of arc authoring in Blender.

## Implemented boundary

- Explicit schema-3 arc records and migration, pure directed arc measurements,
  bounded native compilation and independent solved-output validation.
- Shared native point identities, CW mapping, radius drivers and intrinsic
  equation accounting, with no saved derived radius/sweep authority.
- Exact preservation of the audited 0.5.1 equality-cycle guard and existing
  schema-1/2 canonical bytes and supported result semantics.
- Explicit rejection of schema 3 by consumers whose profile/result contracts
  are not implemented yet. Snapshot capture remains engine/solver/native-free.

The original 14-file development draft was preserved before integration.
Independent review caught and repaired an accidental snapshot-to-engine import
and made the old profile test fixture explicitly schema 1. Native ceiling probes
closed the previously unqualified 1,024-row resource-control boundary.

See [ADR 0007](adr/0007-directed-arc-core.md) for the accepted design and
[the independent audit](../research/arcs/core_audit/REVIEW.md) for findings,
dispositions, exact reviewed file hashes and portable probes. The audit's
original full-suite failures describe the preserved draft, not this repaired
checkpoint.

## Completed qualification

With the pinned CPython 3.12 environment, `slvs==3.2`,
`cadquery-ocp-novtk==8.0.1.1.0`, and native Blender 5.2.2 LTS on Linux x86_64:

- Ruff lint and format pass.
- Full pytest: **3,609 passed; 19,597 subtests passed**.
- All **41** entry points in `scripts/run_checks.sh` passed, including existing
  separate-process persistence tests and the 70-check DoF cycle/recovery gate.
- Both Linux owned-sidecar exit gates passed; unrelated processes survive.
- Independent compatibility probes match all 11 existing Part fixtures and 80
  seeded legacy solves byte-for-byte against the pre-arc core.
- Independent native numerical, branch, ceiling and injected false-success
  probes pass within the bounded cases stated in their report.

Reproduce the full gate with `MCAD_PYTHON=/path/to/sidecar/python` and
`BLENDER=/path/to/blender` set, then run `bash scripts/run_checks.sh`.
The source tree does not embed a native dependency environment.

## Still unavailable

Mixed line/arc profile classification, B-rep construction and lineage, result 3,
arc assembly consumption, saved arc editing commands and viewport drawing remain
separate work. No exact ZIP-installed arc GUI test was performed because those
paths are not enabled. Windows/macOS and arbitrary nonlinear branch continuity
are not qualified. Backend capability negotiation is the next reviewed boundary;
this checkpoint does not change the delivered 0.5.1 mixed-install limitation.

The delivered 0.4, 0.5 and 0.5.1 archives remain unchanged.
