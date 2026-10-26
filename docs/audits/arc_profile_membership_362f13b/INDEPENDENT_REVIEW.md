# Independent exact finite-arc membership review

Disposition: ACCEPT the isolated primitive extension at commit `362f13b330639d256c18d6a3599b281ae631df27`, limited to exact finite-arc membership attached to the already reviewed complete line/circle support-root ledger. The frozen independent gates pass and no primitive blocker remains. This is not approval of any profile, cell, clearance, classifier, service, native, UI, capability, or release activation.

## Frozen scope and identity

The approved delta from `cf47a4fbd04d87fe5d5649d2c1b02e1cee596d8e` is exactly:

- Modify `src/mechanical_cad/arc_profile_primitives.py` by adding two methods and three immutable composition records.
- Add `tests/unit/test_arc_profile_arc_membership.py`.

The source archive has 952 files. The independent preservation script compared every source file with its SHA-256 manifest entry, its ZIP content, and its Git blob identity. It checked the exact two-file Git delta, all 105 original runtime SHA-256 entries, and the delivered 0.5.2 archive. The same whole-source checks ran before and after each independent frozen gate.

- Source ZIP SHA-256: `a4d384d5eeca6de045c2bf8ece6b11eff68ca1af926e5aecdb2eb50e39a8dad3`.
- Source manifest SHA-256: `f1906e4d705d5777f029bf7cab85075f8fab3ad22ed5e448c2287eac371cb57a`.
- Extended leaf SHA-256: `ebd60e4dd35c98459dd6d688e81322f88adcb1766c0864e16d10b9defea738bd`.
- New implementation tests SHA-256: `25177d066c87fe501a34a6627c87de2c5b8a8107d124303c7838c22e549ed504`.
- Original primitive-test SHA-256 remains `6837a5600461bc15c65fcf4601249a988ecff4220062da6e12d1c9510fcc5379`.
- Delivered 0.5.2 ZIP SHA-256 remains `d644fbce66b843047a6cb3e3cd775c1af8517a7ff82e3f22ce3888b710d1971f`.

Every pre-existing module declaration/class and each original `PrimitiveContext` member has byte-identical source spans and identical ASTs. Existing methods, constants, imports, context limits and arithmetic remain unchanged. Neither existing production source tree imports this leaf.

## Mathematical assessment

### The mathematical trim is explicitly authored-ray based

The public operation accepts authored arc points and an independently supplied canonical radius. It computes each ray as the exact difference of separately decoded coordinates. It neither uses rounded translated coordinates nor derives the radius from the endpoint lengths. A nonzero pair of distinct positive rays plus the exact built-in direction `CW` or `CCW` selects a proper directed arc.

A zero ray rejects. For two nonzero planar vectors, zero cross product and positive dot product mean the same positive ray, which is rejected because it leaves zero/full-turn ambiguity. Zero cross product with negative dot product means opposite rays and defines an exact semicircle. Zero cross and zero dot cannot occur for two admitted nonzero planar rays, so the implementation needs no additional geometric case.

The arc-ray validation precedes the support calculation. Therefore an empty support ledger cannot bypass invalid direction, invalid point, zero-ray, or same-positive-ray rejection. The unchanged support operation independently validates every line/circle input.

### Algebraic root direction is exact

Let `h=end-start`, `o=start-center`, and let the unchanged support coefficients be `A=h·h`, `B=2h·o`, `C=o·o-r²`, and `D=B²-4AC`. For a valid line `A>0`. At the corresponding algebraic root,

`2A*(x-center) = (2A*o-B*h) + branch*sqrt(D)*h`.

The branch is -1, +1, or 0 for MINUS, PLUS, or DOUBLE. Multiplication by positive `2A` preserves every cross-product sign, dot-product sign, and ray relation. This direction cannot be zero: a real support root is at distance `r>0` from the center. No normalization, root-coordinate rounding, trigonometric evaluation, or additional square root is needed.

The implementation forms only the dyadic rational and radical coefficient vectors, using the existing checked operations. All exact algebraic determinant/dot signs pass through the previously reviewed single-radical predicate. The proof therefore uses the exact root, including when its output interval straddles an endpoint or fails isolation.

### Endpoint and interior partition is complete

A zero cross product with an endpoint ray is endpoint membership only if its dot product with that ray is positive. The opposite direction is never mislabeled an endpoint. These two endpoint tests run before interior tests and are independent of direction.

For a CCW minor span, strict interior is the intersection of the two directed open half-planes: after the start and before the end. For a CCW major span it is their union. When the endpoints are antipodal, the two half-plane signs agree and their intersection describes the appropriate open semicircle. Changing direction negates both root-determinant signs and the span sign, selecting the complementary open arc while retaining the same named endpoints. Since endpoint equality was handled first, strict signs correctly distinguish outside from interior even on the negative extensions of endpoint rays.

This is a ray-membership proof, not a theorem that the mathematical trim equals an existing floating sweep or a native parameter trim.

## Ledger, resources, and trust boundary

`line_arc_roots` calls `line_circle_roots` on the same `PrimitiveContext`. It does not accept caller-supplied support evidence or create a replacement context. It composes each exact original `SupportRoot` object with one of `OUTSIDE`, `AT_START`, `INTERIOR`, or `AT_END`. Branch, multiplicity, line position, interval, ordering, and original support coefficients are preserved. Empty ledgers remain empty; tangencies remain one DOUBLE of multiplicity two; simple roots remain MINUS then PLUS. Neither primitive outcome establishes a transverse join.

The unresolved result is a distinct non-subclass type, with `isolated=False` and `unresolved_isolation`. Both original roots and their overlapping 256-bit enclosures survive. Exact memberships do not turn failed isolation into ordinary success. Line and arc positions stay independent, including all four finite-membership combinations.

All added arithmetic goes through the existing checked dyadic/sign operations and the same non-resetting budget. Other new allocations are bounded collections of at most two roots, fixed strings/branch choices, and frozen slot-backed records. The constants remain 100,000 operations and 65,536 exact-intermediate bits. Exhaustion raises a nonpassing primitive error. This remains a finite operational bound, not a wall-clock guarantee or Python sandbox. Ordinary immutable records are not validators for fabricated evidence; no production consumer accepts them.

## Independent oracle and adversarial coverage

The external oracle uses standard-library `Fraction`, exact quadratic-polynomial evaluation at rational thresholds, and global cyclic polar ordering. It does not call production private arithmetic, evaluate radicals, repeat the production minor/major half-plane decision, or use angle/epsilon/interval-width membership.

A positive-leading quadratic has positive sign outside its roots and negative sign between them. Its rational vertex distinguishes the left and right regions. This gives exact order of either root against any rational threshold. An affine expression of the root is then ordered by comparison with its rational zero. These signs order the root ray in the global upper/lower polar half-planes. A cyclic interval from the start ray to the end ray gives membership. A separate combinatorial eight-ray cycle checks this reference ordering; known rational-root polynomials check the reference comparator itself.

The final 57 external tests include:

- 896 exhaustive eight-ray start/end/root/direction cases with a separate cyclic-index expectation.
- 1,200 deterministic rational-coordinate line/circle/arc cases against the independent polynomial oracle.
- Every one of the 14 previously retained diagnostic examples, preserving the supplied canonical binary64 radius.
- Exact endpoints, opposite rays, unequal antipodal ray lengths, major/minor/seam arcs, both directions, and exact endpoints with irrational support parameters.
- Quarter/major endpoint perturbations of ±5e-10 and all four line/arc finite-membership combinations.
- Rounded hypot authority, line reversal, paired arc/direction reversal, and exact power-of-two scale transformations.
- Tangents, no real roots, short lines, domain extrema, subnormal cancellation, an exponent grid down to 2^-1074, and the distinct but unresolved near-tangent pair.
- Strict built-in types, malformed coordinates/directions/radii, rejected number/tuple/string subclasses, zero/same-ray rejection even without real support roots, and degenerate line rejection.
- Same-context instrumentation, no new context construction, accumulated operation exhaustion, exact-budget success and failure, bit-cap rejection, immutable nested composition, and absence of angle/rounding calls in the new methods.
- A fresh site-packages-disabled import/process with no native, solver, service, or model import by the leaf.

These finite fixtures reinforce the reviewed formulas and invariant arguments; they are not an exhaustive proof by sampling.

## Frozen results and reproducibility

All commands, source identities, timestamps, terminal markers and log hashes are retained in `FROZEN_GATE_RECEIPTS.json`. The external test script, original leaf reference, preservation script, native-import-trapping launcher and serial runner are retained beside this review.

- Independent exact-reference suite: 57 passed.
- Unchanged original primitive suite: 138 passed.
- New implementation membership suite: 191 passed.
- Existing pure arc geometry/schema-v3/unsupported-consumer boundary suite: 379 passed.
- Existing DoF guard suite: 18 passed.

Every gate exited 0 with `PURE_NATIVE_IMPORT_TRAP_CLEAN` and `PURE_AUDIT_TERMINAL exit=0`. The runner ended with `ALL_INDEPENDENT_FROZEN_GATES_PASS`. All 952 frozen files matched before and after each gate. No OCP, SolveSpace or Blender process was launched by this audit. The reviewer did not run the whole project or any native integration gate; owner-run whole-project regression evidence is separate and can be verified without rerunning it.

## Explicit exclusions and disposition

There were no pre-freeze mathematical or API/resource defects found in this additive extension. The frozen independent result is accepted only for exact authored-ray arc positions attached to complete support ledgers.

No profile-domain admission, exact shared-ID topology, discrepancy/cell construction, exit count, root assignment, foreign-boundary exclusion, clearance, angle, area, reference-region closure, frame/parameter conversion, native geometry, service/result-v3 handling, capability, publisher, UI or release qualification follows from this acceptance. The existing core arc policy and all 105 baseline runtime files remain unchanged. The immutable 0.5.2 delivery is untouched.
