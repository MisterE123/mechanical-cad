# Provisional transverse profile semantics and isolated primitive boundary

Status: **design reviewed; isolated primitives independently qualified; no profile
or service activation**. See the [primitive milestone](../../ARC_PROFILE_PRIMITIVES_MILESTONE.md)
for exact implementation scope and receipts. The latest usable release remains the delivered 0.5.2 compatibility
safety preview. General arc geometry, canonical records, solver guards and the
production v2-only evidence system are unchanged.

The [sealed contract](TRANSVERSE_JOIN_CONTRACT.md) governs the first curved closed
profile slice, narrowing the broader dormant [proposal](PROPOSAL.md). The
[independent review](../../audits/arc_transverse_join_b4cdbfe/INDEPENDENT_REVIEW.md)
accepts its pure mathematical construction and finite clearance proof. This is
design acceptance, not an implemented classifier or a kernel qualification claim.

## Adopted provisional decisions

1. Support exactly one arc plus its chord or two radial lines, with shared point
   IDs, canonical radius and positive nominal extrusion height in [1,1000] mm.
   Exact center-relative endpoint dot product must be nonpositive, restricting
   either authored direction to 90–270 degrees. The outer arc/line joins are
   transverse. Opposite radial rays at a semicircle's center are permitted as an
   exact straight continuation with disjoint finite interiors.
2. The new profile reference uses exact authored endpoint rays, the unchanged
   binary64 canonical-start radius and authored direction. It is distinct from
   the frozen computed core sweep and eventual rounded native trim. This does
   not redefine general arc geometry or change any core admission comparison.
3. Prove each local endpoint discrepancy d <= the exact rational 1/10^9 mm.
   Given a certified upper bound U, eta=min(U,1/10^9) is used only after that
   independent proof. The shared cell radius is 16*max(eta), capped at 1.6e-8 mm.
   Exactly zero discrepancies use the exact-join path. Cells still need every
   containment, root assignment, exit, foreign-branch and disjointness check.

Every support root remains recorded with its multiplicity and separate original
finite-line/finite-arc membership. A tiny inward gap may have no finite crossing
but a unique nearby support root. A tiny outward gap may contain a crossing; it
is retained. A proof-only simple completion inside the cells gives region meaning.
The literal straight endpoint-connector walk is not claimed to be simple, and
neither authored coordinates nor native input trims are repaired.

The disk-area bound applies only to consistently oriented simple Jordan closures
with exact exterior agreement. Global frame changes and rounded native geometry
need separate bounds. The 1e-9 discrepancy ceiling remains necessary but
insufficient: unchanged R0/C0 and all structural/native checks remain independent.

## First implementation boundary

Only a new native-free leaf and its tests may be added for checked binary64
dyadics, exact polynomial/radical signs, bounded outward square roots and complete
quadratic support-root records with exact finite-line membership. Negative,
tangent and two-distinct-root outcomes must remain explicit. Unresolved disjoint
isolation retains its root ledger as an explicitly ambiguous result.

The numerical ceilings are 65,536 bits for checked exact intermediates, 100,000
scalar operations, normalized interval significands of 64/128/256 bits and
exponents in [-32768,32768]. These are fail-closed computational limits, not
ordinary-case performance guarantees. Checks must precede large allocation.

No import into a classifier, service, kernel, publisher or UI is authorized by
this boundary. Finite-arc membership, cells, clearance, angle/area evaluation,
frame conversion and result-v3 dispatch are later implementation gates. A fresh
independent primitive audit and concrete boundary-rejection tests precede any
integration. Existing runtime source hashes remain protected by BASELINE.json.

The additional candidate conversion check r*|theta_exact-sweep_core| <= 1e-9 mm
appears only in the contract's unresolved future conversion section. It was not
adopted as part of the three decisions above and is outside the primitive scope.

## Exact evidence

- Sealed contract SHA-256:
  `befbd79b5105535b3c0fa3efcdadca2433559d2dbd0ba76927b584de6c918fe8`.
- Independent receipt SHA-256:
  `54c6b7016e66dc34ffd97212995acff482cc260ae3fbf2cf118be905f9084041`.
- Designer receipt SHA-256:
  `25375d5b589becb2eafa3e788bf882fccfbb2d528fa2e6f30ee65b1c326a7d16`.
- Fourteen exact independent examples retain all four finite-root membership
  combinations, rounded-hypot gaps, threshold neighbors, a subnormal offset and
  ordinary quarter/major/semicircle cases.
- All 105 baseline runtime Python hashes matched; no native process ran during
  this design review. The delivered 0.5.2 handoff hash remained unchanged.

The exact independent report, receipts, JSON and oracle source are retained in
`docs/audits/arc_transverse_join_b4cdbfe/`. The oracle is archived as
`exact_join_examples.py.txt` to preserve its exact reviewed bytes; its paths and
receipt refer to the original isolated workspace. Its absolute 2^-192 arithmetic
grid is an independent diagnostic oracle, not the production significand policy.
