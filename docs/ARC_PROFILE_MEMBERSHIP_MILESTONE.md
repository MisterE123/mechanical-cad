# Isolated exact finite-arc membership

Status: implemented and independently accepted as an unused pure leaf at
`362f13b330639d256c18d6a3599b281ae631df27`. This is an additive extension to the
[first exact primitive milestone](ARC_PROFILE_PRIMITIVES_MILESTONE.md), under the
[reviewed provisional transverse policy](architecture/arc_profile_service/TRANSVERSE_JOIN_REVIEW.md).
The latest usable release remains immutable 0.5.2.

This record describes the `362f13b` boundary. The subsequent
[shared-ID incidence prerequisite](ARC_PROFILE_INCIDENCE_MILESTONE.md) is qualified
separately at `94acd98`; it adds the sole reviewed isolated consumer and narrowly
extends two static import guards while preserving all behavioral assertions.

## Implemented boundary

`PrimitiveContext.line_arc_roots` recomputes a complete line/circle support-root
ledger within the same non-resetting arithmetic context, then attaches exact
finite-arc membership to every original root. It accepts authored start/end
points defining exact center-relative rays and an explicit built-in `CW` or
`CCW` string. This detached primitive convention is not a new service or model
wire format.

- Every root retains its original branch, multiplicity, finite-line position,
  parameter enclosure, and identity within its owning support ledger.
- Arc position is exactly `OUTSIDE`, `AT_START`, `INTERIOR`, or `AT_END`.
  Line and arc membership remain independent: all four combinations survive.
- Negative discriminant retains an empty ledger. Tangency retains its one root
  with multiplicity two; it does not become a transverse join.
- CW/CCW minor, major, seam-crossing and semicircular arcs use exact signs.
  Endpoint equality requires both a zero determinant and positive ray dot
  product. An opposite ray is not mistaken for an endpoint.
- Zero rays and coincident positive rays reject. The latter cannot distinguish
  a zero arc from a full turn. Antipodal rays describe an exact semicircle.
- Unisolated roots remain in the separate `UnresolvedArcSupportRoots` type,
  preserving both root branches, overlapping bounds and exact memberships.
  It is never an instance of the successful isolated result type.

For line direction h, offset p-c and support coefficients A, B, D, the exact
root direction multiplied by positive 2A is

    (2A*(p-c) - B*h) +/- sqrt(D)*h.

The implementation reuses the existing checked dot/cross/single-radical sign
operations. It does not evaluate an angle, inspect a rounded root coordinate, or
use interval overlap as a membership test. All new work shares the existing
65,536-bit intermediate cap and 100,000-operation aggregate budget. Malformed arc
inputs reject even when the supporting line has no real roots.

## Preserved boundaries

The entire previous 22,793-byte primitive source is an exact prefix of the new
module. All 40 original PrimitiveContext method source spans/ASTs, the original
138-test file, and all 105 baseline runtime Python files remain unchanged.
The added immutable records remain detached data containers: their public
constructors do not validate caller-fabricated evidence. No production publisher
accepts them, and the audited GuardedEvidence boundary remains result-v2 only.

The helper retains the support-root radius domain [1e-6,1e6] mm. It does not
apply or establish the narrower future profile domain, the dot<=0 profile
restriction, shared-ID topology, cell exits/root assignment, clearance, reference
closure, angle/area, core-sweep correspondence, parameter/frame conversion, or
native postflight. There is no classifier/service/UI integration.

## Qualification

The exact Git-free 952-file snapshot matched Git, ZIP and manifest byte-for-byte.
Whole-source hashes stayed unchanged before and after every frozen gate.

| Gate | Result |
| --- | --- |
| Whole-project Ruff and formatting | Pass; 371 Python files formatted |
| Whole-project pytest | 4,347 passed and 19,597 subtests passed; exit 0 |
| New membership tests | 191 passed |
| Unchanged original primitive tests | 138 passed |
| Independent exact-reference suite | 57 passed |
| Independent existing pure boundary / DoF suites | 379 / 18 passed |
| Native-import-trapping and site-packages-disabled checks | Pass |
| Existing runtime preservation | All 105 baseline Python files byte-exact |

The independent oracle uses exact rational quadratic-polynomial comparisons and
global cyclic ray ordering, separate from the implementation's radical-sign and
minor/major half-plane logic. It includes 896 exhaustive eight-ray direction
cases, 1,200 deterministic algebraic comparisons, all 14 prior reviewed examples,
and resource, malformed-input, seam, reversal, tiny-gap and subnormal controls.
Its formulas and ledger invariants were reviewed alongside the sampled tests.
The [sealed independent review](audits/arc_profile_membership_362f13b/INDEPENDENT_REVIEW.md)
records the bounded acceptance and explicit exclusions.

Existing full-regression native backend tests are distinct from new
curved-profile/native qualification; no new native arc implementation or
Blender/installed/GUI gate is claimed.

## Frozen identities

- Source archive SHA-256:
  `a4d384d5eeca6de045c2bf8ece6b11eff68ca1af926e5aecdb2eb50e39a8dad3`.
- Source manifest SHA-256:
  `f1906e4d705d5777f029bf7cab85075f8fab3ad22ed5e448c2287eac371cb57a`.
- Additive leaf SHA-256:
  `ebd60e4dd35c98459dd6d688e81322f88adcb1766c0864e16d10b9defea738bd`.
- New tests SHA-256:
  `25177d066c87fe501a34a6627c87de2c5b8a8107d124303c7838c22e549ed504`.
- Independent review SHA-256:
  `b5c5a330642872587fa4a6c4358e162e4f11b71e473cfb9b219cf71a9a1aff04`.
- Independent receipt SHA-256:
  `308f12e19bdc720f9f059ccb6c29bc925688c1f5ca84afbfe5956b3af75a5423`.
- Owner completion receipt SHA-256:
  `d71cad3eff9a3a14140a66f73a241ce186a46faf2edbb66a950fc5ebc6345d1c`.

Per-gate logs, exact commands, complete source maps, pure reference scripts and
retained pre-freeze receipts are preserved under `cad_arc_membership` in the
engineering evidence workspace. The documentation record may advance after the
tested implementation commit; source and test identities remain fixed above.

The [next incidence-preflight proposal](architecture/arc_profile_service/INCIDENCE_PREFLIGHT_PROPOSAL.md)
is a separate review boundary. A necessary endpoint-discrepancy test or a complete membership ledger cannot, by itself,
prove a simple supported profile.
