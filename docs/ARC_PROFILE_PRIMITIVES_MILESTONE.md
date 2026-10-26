# Isolated exact arc-profile primitives

Status: **implemented and independently accepted as an unused pure leaf** at
`cbb4dd2c9969b0cc7aa2bfbeb0704dcf9422ff5b`. Curved profile, native kernel,
result-v3 service, capability, publisher and UI integration remain unavailable.
The latest usable release is still the immutable 0.5.2 compatibility safety
preview; no release artifact was rebuilt.

This record describes the first `cbb4dd2` boundary. The subsequent
[exact finite-arc membership extension](ARC_PROFILE_MEMBERSHIP_MILESTONE.md) is
qualified separately at `362f13b` and preserves this implementation as an exact
source prefix. The original limits below refer to this first milestone.

This is the first implementation step under the
[reviewed provisional transverse policy](architecture/arc_profile_service/TRANSVERSE_JOIN_REVIEW.md).
It does not change general arc geometry, its canonical-start radius, computed
sweep, solver guards or the production v2-only evidence/publication boundary.

## Implemented boundary

The new `arc_profile_primitives.py` leaf provides:

- Exact binary64 dyadic decoding and exact translation, including subnormals.
  Bounded built-in integer coordinates are also accepted because they are exactly
  representable in binary64. Bool, subclasses and other numeric types reject.
- Checked exact dot, cross, discriminant and single-radical sign predicates.
- Verified outward square-root and rational-division enclosures with normalized
  64/128/256-bit significands and explicit exponent limits.
- A complete immutable line/circle support-root ledger: no real roots, one
  multiplicity-two tangent, or separately ordered MINUS/PLUS simple roots.
- Exact finite-line membership at, between and outside the endpoints, independent
  of interval width. An unresolved 256-bit isolation retains both roots in the
  separate `UnresolvedSupportRoots` type; it cannot establish an isolated join.

One shared context has a non-resetting 100,000-operation budget and a checked
65,536-bit exact-intermediate cap. Ordinary reinitialization/deletion, oversized
shift/precision arguments and resource exhaustion fail before the relevant
allocation. These are finite computational limits, not a wall-clock guarantee or
a Python sandbox. Future aggregate calculations must share one context.

The primitive support helper's radius domain [1e-6,1e6] mm is distinct from the
provisional future profile domain [1,1000] mm. It establishes neither finite-arc
membership nor profile admission. Public immutable record constructors are not
validators for caller-fabricated evidence, and no production consumer accepts
these records.

## Qualification

The owner froze an exact Git archive and tested its Git-free 948-file snapshot.
All recorded source hashes matched before and after the gates.

| Gate | Result |
| --- | --- |
| Whole-project Ruff and formatting | Pass; 368 Python files formatted |
| Whole-project pytest | 4,156 passed and 19,597 subtests passed; exit 0 |
| New primitive tests | 138 passed |
| Independent adversarial tests | 21 passed, with deterministic exact-reference loops |
| Independent existing pure boundary tests | 379 passed |
| Independent site-packages-disabled import | Pass; no solver/kernel/service imports |
| Existing runtime preservation | All 105 baseline Python files byte-exact |

The independent audit reviewed the arithmetic formulas and bounds, not only
sampled outcomes. Its separate oracle checked cancellation and Pell cases,
subnormal endpoint offsets, normalized rounding carries, exact boundary
membership, resource exhaustion and distinct but unisolatable roots. The four
pre-freeze hardening findings and their resolutions remain in the
[sealed review](audits/arc_profile_primitives_cbb4dd2/PRIMITIVE_REVIEW.md).

The full regression suite includes existing backend integration. It is not new
curved-profile/native-join qualification. No new Blender gate, installed package,
GUI arc workflow or native arc-profile implementation is claimed here.

## Frozen identities

- Source archive SHA-256:
  `6b425dfb3d3ca4e504ff7119c8f4abd0ecdab4b6ce6586e65169f195d043f091`.
- Source manifest SHA-256:
  `e767b0d3d6d893c4a8cde39b9a74c26e53c0c9c3d59b143e0fc4f281e7544151`.
- New leaf SHA-256:
  `1a92f9f68fef5f8284efc91f3431abf00d0b0fdab371646303680421a540553a`.
- New tests SHA-256:
  `6837a5600461bc15c65fcf4601249a988ecff4220062da6e12d1c9510fcc5379`.
- Independent report SHA-256:
  `4df49c30b1833681c6bd38447d79ae47345afb321d79270da523a4b6c1eef374`.
- Independent receipt SHA-256:
  `65f85fe12622589c395371e0f516a21f93651afc6854efdd1ff56ef0a0440fc6`.
- Owner completion receipt SHA-256:
  `92893701c0fa1150efaaea4c2ebb53e8f673783a37eef4954bfd8fc621b3b3a3`.

Per-gate logs, exact commands, completion markers, retained pre-freeze findings,
source maps and oracle scripts are preserved under `cad_arc_join_design` in the
engineering evidence workspace. The documentation record may advance after the
tested implementation commit; its source and test bytes remain fixed above.

## Next boundary remains separate

Finite-arc membership, cell exits/assignment, clearance, angle/area evaluation,
parameter/frame conversion and native postflight still require their own
implementation and independent review. The reference-region design has not
become a classifier merely because its lowest-level arithmetic is available.
No service/result-v3 or production owner may consume the new leaf in this slice.
