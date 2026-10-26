# Proposed next bounded incidence slice

Status: this narrow prerequisite scope was approved, implemented and independently accepted at `94acd98`, after exact finite-arc membership at `362f13b`. See the [incidence milestone](../../ARC_PROFILE_INCIDENCE_MILESTONE.md) for the actual API, deliberate one-import test extension, qualification and limits. This design record does not authorize any later region/native/service activation.

## Outcome

Build one isolated, data-only incidence-preflight module for exactly one arc plus its chord, or one arc plus two radial lines. It composes the reviewed arithmetic and complete membership ledgers. Its output is a prerequisite report, never a closed profile, export source, capability, or publication receipt. No existing classifier, service, solver, kernel, or Blender module imports it.

The report can distinguish (a) exact endpoint incidence established, (b) a positive discrepancy within the fixed necessary bound that still requires the separately reviewed cell proof, and (c) explicit unsupported or bounded-numerical failure. Neither (a) nor (b) is profile admission: clearance, reference closure, angle/area, global conversion, and native postflight remain outstanding.

## Input and topology boundary

Use the existing immutable typed sketch representation and its unchanged validation; do not introduce a parallel permissive parser. The prospective adapter must call the unchanged core arc-geometry validation with equal-radius enforcement and retain its exact binary64 output. It must never infer geometry from saved status, mutate coordinates, derive an alternative radius, or treat the new data-only record as GuardedEvidence. The exact public API and import graph require review before code.

- Exactly one arc and one chord, or exactly one arc and two radii; no extra boundary, hole, full circle, or arbitrary multi-arc loop.
- Required joins use the same endpoint IDs. Geometrically equal or coincidence-constrained distinct IDs fail with an explicit unsupported-coincidence-join result. No coordinate welding or constraint-based representative rewriting.
- A sector's shared center ID is the arc's authored center ID. Endpoint roles are explicit, never inferred from proximity.
- Canonical core radius and requested positive extrusion height are inclusively 1–1000 mm. Preserve all earlier core/domain checks first. These are provisional profile-support limits, not general arc-geometry changes.
- Exact authored-ray dot product must be <= 0. Antipodal sector rays are an allowed straight center continuation; positive collinear rays and overlapping finite radial interiors reject.

## New arithmetic needed, narrowly bounded

For each authored endpoint v=p-c, S=v·v, canonical radius r, and N=10^9, decide the necessary local discrepancy bound without evaluating an angle or rounding a distance:

    |sqrt(S)-r| <= 1/N

Within the reviewed radius domain r > 1/N, this is exactly equivalent to:

    (N*r-1)^2 <= N^2*S <= (N*r+1)^2.

All quantities use the existing checked dyadic operations and one non-resetting context. An exact S=r^2 comparison establishes zero discrepancy. No epsilon, ULP widening, per-case tolerance, or empirically widened envelope is permitted. Exact equality at the bound passes. Resource exhaustion is a separate nonpassing numerical result.

If needed for a later cell consumer, expose only the existing 64/128/256-bit outward sqrt enclosure and a rigorously derived nonnegative gap enclosure, retaining exact zero separately. Do not implement cells or a second rational arithmetic framework in this slice. The previously reviewed eta=min(U,Delta) and rho=16*max(eta) rules remain the later cell contract; a finite upper bound alone never establishes that contract.

For a chord, parameterize its support explicitly from the arc's authored start point to its authored end point, regardless of the stored line endpoint order. Preserve the stored line order and identity separately; this temporary parameter convention does not mutate or relabel the authored line. Use its complete MINUS/PLUS line/arc ledger, require positive discriminant, and compare the exact transversality inequality 9*disc >= 16*A*r^2. Retain the prescribed MINUS-to-start and PLUS-to-end nominal association; do not call a positive-gap association geometrically proved until a cell test establishes it. Never try a reversed or nearest-root assignment to rescue a case.

For each sector radius c→p_i, retain both support roots. The PLUS root is the nominal own-join root; the MINUS root remains in the ledger even when it lies outside the finite line and on a major arc. Normal radial crossing is exact, while finite-line and finite-arc membership remain independent fields. A tangent, duplicate, unresolved, absent, or incomplete root ledger cannot pass an exact-incidence prerequisite.

The exact-zero path may verify the two endpoints are the prescribed support roots and that each prescribed endpoint root's finite memberships are endpoints. Retained negative sector roots remain outside their finite lines and keep their independent arc memberships. It still returns only an incidence prerequisite, with no clearance/profile/Jordan/area conclusion.

## Concrete expected results

1. r=5, c=(0,0), p0=(5,0), p1=(0,5), one shared-ID chord, either direction: exact endpoint incidence; both roots retained, exact transversality passes. The chord's prescribed endpoint labels are the same in CCW quarter and CW major cases. For sectors, the retained negative radial roots distinguish quarter and major arc membership while remaining outside the finite lines.
2. r=5, p1=(-5,0), shared-ID chord or two radial lines: exact semicircle endpoints; the sector center is a valid straight continuation in both directions.
3. r=5, p1=(0,5+5e-10): if unchanged core validation passes, the local bound can pass but the report remains `requires_incidence_cells`. Retain every line/arc membership combination and never create a literal connector or snap the endpoint.
4. r=5, p1=(0,5+2e-9): the fixed local-discrepancy prerequisite rejects even if the broader unchanged core radial residual admits it.
5. p0=(1,1), p1=(-1,1), canonical r=the unchanged rounded hypot result: equal authored norms do not establish zero discrepancy; exact S versus r^2 decides, and a positive gap still requires cells.
6. r=5, p1=(4,3): exact dot is positive, so the provisional support restriction rejects both directions regardless of core admission.
7. Exact same coordinates but distinct required endpoint IDs, even with a coincidence constraint: explicit unsupported-coincidence join; authored data unchanged.

## Independent review and stopping condition

Before any code, review the exact input/API boundary and the gap-equivalence proof. Implementation must retain all existing primitive source spans and all 105 baseline runtime hashes; any additive helper is separately tested. Use independent rational references for threshold equality and one-step neighbors, rounded-hypot and subnormal differences, every ledger membership combination, chord transversality boundaries, strict topology, budget exhaustion, and all rejection examples above.

Freeze an exact commit and Git-free archive, independently audit the preflight's limited claims, and run full Ruff/format/pytest with durable receipts. No new native jobs are needed for this pure prerequisite layer. A later proposal must separately define and implement positive-radius cells, exits, root assignment, foreign-branch exclusion and clearance before any profile admission. Production result-v2 GuardedEvidence and exact v1/v2 service bytes remain unchanged throughout.
