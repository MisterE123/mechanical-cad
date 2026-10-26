# Independent review: bounded transverse endpoint-incidence proposal

Disposition: accept the revised pure mathematical design. The parent explicitly approved exact-ray/local-completion semantics, the exact-dot support restriction, and the discrepancy-derived cell rule as provisional supported-profile semantics only. This is design-only acceptance, not implementation approval, product activation, or continuous-domain kernel qualification.

Source baseline: `b4cdbfeb9afa945a7cc207e15ff71d16b16b6bf1`.
Frozen `arc_geometry.py` SHA-256: `b2017ca26300712cdaece7325fcd12fd1330d650896a5494dea56967fa1a82aa`.
No repository file was edited. No OCP, Blender, installer, network publication, or native test was run.

## Main finding

A practical, genuinely bounded reference-closure rule exists for exactly one arc with either its chord or two radial lines. It does not require a general curve arrangement solver. It does require a visible change in profile semantics: the original finite analytic pieces may have a gap or a small overshoot crossing at an authored common vertex. A proof-only simple completion inside a tiny join cell gives the region meaning. The original untrimmed pieces are not thereby proved to form an exact Jordan boundary.

The proposed exact-authored-ray target and exact endpoint-vector dot-product restriction are explicit owner decisions, not changes already authorized by the frozen core. The source arc keeps canonical-start radius and authored direction; frozen computed sweep/admission remain unchanged and native parameter conversion must be independently bounded.

## Independently exercised exact examples

`exact_join_examples.py` uses exact dyadic inputs, Fraction arithmetic, and integer-square-root outward intervals. Decimal/float renderings are descriptive only. Its square-root oracle uses an absolute 2^-192 grid and verifies its returned rational endpoint squares. This is independent reference arithmetic, not an implementation of the proposed production normalized-significand cap; absolute fractional bits and significand bits are different limits. It imports only the frozen pure arc module via `runpy`, plus Python standard-library modules. The resulting JSON contains all root enclosures and memberships; it is a diagnostic oracle, not a production classifier.

For center (0,0), start (10,0), end (0,10±5e-10), both perturbations have exact represented discrepancy approximately 5.000000413701855e-10 mm. The second support-line/circle root has all four possible original finite-membership combinations:

| Directed source arc | End perturbation | Finite chord | Finite source arc |
| --- | --- | --- | --- |
| 90° CCW | outward | in | in |
| 90° CCW | inward | out | out |
| 270° CW | outward | in | out |
| 270° CW | inward | out | in |

Each is a distinct classification, not numerical noise. A reference-root assignment cannot replace these membership facts. In the outward minor case, the literal original circle/chord plus a straight Q→P endpoint connector has a tiny local loop. It is not Jordan. Reference trimming inside the cell can remove that loop only in the mathematical proof object, never in authored/native coordinates or trims.

The rounded-hypot fixture v0=(13,29), v1=(-29,13) has canonical radius slightly greater than sqrt(1010), with endpoint discrepancy approximately 1.6569641887314944e-15 mm. Its quarter-segment roots are both outside the original finite chord and outside the original finite source arc. For the major arc, both roots remain outside the finite chord but are inside the source arc. Requiring one original finite intersection at every join would reject this ordinary radius-rounding example.

Threshold examples, comparing to exact rational 1/10^9 mm:

- The double represented by 10+1e-9 has discrepancy 1.000000082740371e-9 mm: reject.
- Its immediately lower binary64 neighbor has discrepancy 9.999983063835316e-10 mm: local exact-ray ceiling passes.
- At local coordinate 999910 mm, an eight-ULP radial offset is 9.313225746154785e-10 mm: local ceiling passes.
- Nine ULPs give 1.0477378964424133e-9 mm: reject.

These are local exact-ray results only. None establishes the transformed inserted-curve equation or native-evaluation ceiling. Earlier retained supplemental controls show that a local or even measured endpoint-ceiling pass can still fail unchanged C0.

The script also checks exact quarter/semicircle examples, rejects a (10,0)/(6,8) exact-circle segment under the proposed dot restriction, and exercises an accepted subnormal-coordinate case. The last has a 1074-bit numerator and 1075-bit denominator already in an exact coordinate difference; a 256-bit interval significand does not cap exact predicate integer size.

## Minimal mathematical construction

### Segment

Use the original solved endpoint support line. Isolate both support-line/circle roots globally. Assign one distinct root to each declared endpoint cell by certified enclosure and separation; never select the numerically nearest root without uniqueness. Retain finite-line and finite-source-arc membership separately for each root. The reference chord is the segment between those two roots. Its open interior lies strictly inside the support-circle disk, and the chosen proper directed reference arc lies on its boundary, so their union is a Jordan curve.

The reference-arc branch must agree with the source outside the two cells. Selecting the complementary arc just because its endpoints match is not valid. The original exact-ray dot restriction is on authored vectors, not reference-root vectors: an outward-perturbed source quarter arc can have a reference sweep just below 90°.

### Sector

The reference uses the support-circle endpoints and radial segments to the exact authored center. The radial interiors lie strictly inside the circle disk and are disjoint except at the center. Opposite rays at 180° are permitted as exact collinear continuation, not overlapping interiors. The term transverse applies to the arc/line joins. The other root of each radial support-line/circle equation is retained even when it lies at the opposite arc endpoint in a semicircle; it is outside that radial finite segment.

### Cell and clearance certificate

A positive cell radius must derive from certified endpoint/parameter/transform discrepancy, be far smaller than Ljoin, and contain the entire source/reference trim difference, not only its endpoint. There must be an explicit exact-zero-discrepancy path; a radius-zero disk cannot be passed through an ordinary two-exit proof as though it had an interior.

Line/disk and circle/disk intersection equations suffice to identify the unique local circle component and certify every branch exit and added/removed portion. The positive-radius disk must contain q and its assigned root strictly, and source/reference common exterior branches must match in orientation. Reject an unisolated root, uncertain branch assignment, a second assigned incidence root, a foreign finite branch, failed disjointness, or unresolved exit count.

For clearance, split finite boundaries at their collar endpoints into at most three intervals each. The nonexempt pair domain is a finite small union of parameter rectangles. For line/line and line/circle distances enumerate intersection, endpoint, perpendicular-foot, and interior stationary candidates with certified finite membership. Require the closed-domain distance infimum to be strictly greater than Dclear. A pointwise strict inequality outside an open collar can still have infimum equal to Dclear; that supplies no uniform positive margin and is not sufficient.

## Area statement and its limits

Let J and Jref be consistently oriented simple Jordan curves agreeing exactly outside disjoint disks. Within each disk their differences close locally. The winding-number difference is zero outside the disks. Since each positively oriented simple Jordan curve has winding 0 or 1 almost everywhere, the symmetric difference of their interiors is confined to those disks, giving |area(J)-area(Jref)| ≤ sum πρ_i².

This theorem is conditional on simplicity, orientation, and exact exterior agreement. It says nothing comparable for arbitrary winding: repeatedly traversing a small square within one disk produces an arbitrarily large signed Green integral without leaving the disk. It is not a proof about the literal straight-connector closure, native B-rep healing, internal kernel tolerance behavior, or native mass integration.

The reference region has a direct stable formula: sector area r²δ/2; segment area r²(δ-sin δ)/2, with reference-root δ, exact branch choice, and certified transcendental intervals. Using solved endpoint cross products as if they were exactly r² sin δ is invalid for perturbed endpoints. Native transformed supports/axes and rounded trims can differ along the whole curve, not only inside cells. Their area and perpendicular-height effects need separate bounded evidence; the disk budget cannot absorb them.

## Required future implementation and qualification gates

1. Explicit owner approval of new exact-ray/local-completion semantics and the dot≤0 support restriction.
2. Independently reviewed production predicates, root isolation, exact branch rules, error classification, interval enclosures, and bounded resource accounting. Every intermediate integer size and candidate count must have a checked limit; refinement exhaustion fails closed.
3. Exact same-source testing of the eventual shared pure implementation: core/client source equality and hashes, installed-package equality, deterministic fixtures, an independent oracle, branch and threshold adversaries, and actual production-path resource exhaustion. This independent script is not a substitute.
4. Actual inserted native curve/vertex identity, coordinates, circle/radius/trims, endpoint-equation bounds, separately retained native evaluations, native tolerances, face/solid validity, and actual perpendicular height.
5. Frozen R0 and C0 unchanged. Cell, endpoint, parameter, and transform uncertainty must not become an added C0 allowance or a rescue for retained residual controls. Same-source production intervals must be run against the retained qualification matrix before any activation.
6. No implementation, production activation, service/capability advertisement, UI, release, GitHub changes, radius reassignment, coordinate projection, identity welding, tolerance increase, or native healing follows from this design review.

## Final designer review

The revised designer contract resolves the material review questions:

- It explicitly defines exact-authored-ray source semantics and proof-only local completion; the literal untrimmed connector walk is not declared Jordan.
- Both original support roots and their independent finite-line/finite-arc memberships survive every join assignment.
- Antipodal sectors are admitted as exact collinear center continuation with disjoint finite interiors.
- Delta is the exact rational 1/10^9. After an independent proof of d<=Delta, eta=min(U_dyadic,Delta) is a valid upper bound; this avoids requiring a dyadic number to equal a non-dyadic threshold.
- Rho=16 eta is capped at 1.6e-8 mm, but every required containment, root assignment, exit, foreign-branch and disjointness fact is still checked rather than inferred from that factor.
- Before any future native call, both source and intended-parameter endpoint discrepancies contribute to the final local cell bound. The rule covers both zero and nonzero source gaps and is frozen before construction. Global transform effects remain separate.
- Precision is normalized signed dyadic m*2^e with at most 64, 128 or 256 significant bits, outward rounding at each operation, and exponent range [-32768,32768]. Integer/shift prechecks are separate. This preserves the original 256-significand-bit ceiling.
- The Jordan area argument is conditional and correct. It does not authorize native healing or loosen R0/C0.

### Clearance completeness and cardinality

For two closed line intervals, a minimum of squared distance occurs at a pair of endpoints, at an endpoint's orthogonal projection onto the other interval, or at an interior intersection. Parallel/coincident supports are handled explicitly; collinear finite overlap gives zero distance, and otherwise endpoint/projection candidates suffice. At most 4 endpoint pairs + 4 projections + 1 isolated intersection = 9 point candidates are necessary. The coincident-overlap test is an exact branch, not a fictitious unique support root.

For one closed line interval x(t) and one closed circle-arc interval q(s), squared distance F=|x-q|^2 has these possibilities:

1. Both parameters are at boundaries: 4 endpoint pairs.
2. The arc parameter is at a boundary and line parameter is interior: at most 2 perpendicular projections.
3. The line parameter is at a boundary and arc parameter is interior: q-c is parallel or antiparallel to x-c, at most 4 radial-direction candidates. If x=c, every arc point has the same squared distance r^2; existing endpoints or that fixed scalar cover the case without normalizing a zero vector.
4. Both parameters are interior and x=q: at most 2 support intersections, each retaining exact membership.
5. Both parameters are interior and x!=q: stationarity requires x-q perpendicular to the line tangent and to the circle tangent. In the plane it is therefore parallel to the circle radius and the line normal. The circle point is one of the two normal directions, and the line point is the foot of c on the support. At most 2 candidates.

Thus 14 point candidates suffice for line-circle patches. Degenerate memberships must be decided exactly or boundedly; uncertainty cannot remove a candidate. The proposed limit of 24 is conservative for both pair types. At most two proxy exits split each finite boundary into three intervals. Three boundary pairs times nine patch products gives at most 27 patches. Closed patch minima, rather than only samples or pointwise strict exterior separation, supply the required uniform positive margin.

The proxy-disk collar bound is valid for the certified short connected component: if chord distance from q is at most z=b+d, the arc length is 2r asin(z/(2r)) <= z/sqrt(1-z^2/(4r^2)). The final strict comparison to L must still be certified. No long-arc branch can use this inequality without the short-component check.

### Resource disposition

The 65,536-bit intermediate, 100,000-operation, fixed candidate/root, 1 MiB certificate, 256 refinement-step and 256-significand-bit caps are acceptable fail-closed operational limits for this isolated design. They are not yet proven ordinary-case completion or wall-clock guarantees. Input-grid numerators at most 1094 bits, differences at most 1095 bits, base quadratic coefficients below 2200 bits and base discriminants below 4400 bits are consistent with the frozen binary64 magnitude domain.

The degree-16 formula claim and every later radical/sign transformation still require a formula-by-formula implementation audit. Enforce numerator, denominator, addition, product, exponent-alignment and shift bounds before allocation; count lower-level work consistently and include any refinement/serialization cost. A bounded operation count is meaningful only if a single counted operation does not invoke an unbounded search. Same-source tests must demonstrate accepted ordinary examples and bounded adversarial rejection. No arbitrary-precision Fraction expression is authorized merely because the reference oracle uses Fraction.

The smallest proposed first implementation is appropriate: an isolated native-free leaf for exact dyadic decoding, bounded arithmetic, exact polynomial signs, outward normalized square root, and immutable quadratic roots with finite-line membership. It must not expose profile readiness, import native code, alter frozen runtime files, dispatch services, or claim the later angular/cell/clearance/area certificates already exist. The parent subsequently assigned this isolated implementation scope, with a fresh independent primitive audit required before any integration. This mathematical design review is not that primitive implementation audit.

### Verification receipt

The independent script completed all 14 diagnostic examples with its explicit assertions and marker EXACT_JOIN_EXAMPLES_COMPLETE. Every one of the 105 runtime hashes in the existing proposal BASELINE.json matched. The frozen arc policy hash matched and the repository working tree remained clean. No native process or production code modification occurred.

Final contract SHA-256 is befbd79b5105535b3c0fa3efcdadca2433559d2dbd0ba76927b584de6c918fe8; correspondence is also recorded in INDEPENDENT_RECEIPT.json. The final added r*abs(theta_exact-sweep_core)<=Delta condition is only an unresolved future conversion proposal, explicitly outside the three approved policy choices and the first-primitive scope. Its mathematical form is coherent, but this review does not adopt or activate it; separate conversion review remains required. Subsequent semantic edits require re-review. The empirical native conversion, actual inserted representation, discrepancy/height certificate, R0/C0 interval evaluation and same-source native qualification gates remain open; service/capability/UI/release activation remains blocked.
