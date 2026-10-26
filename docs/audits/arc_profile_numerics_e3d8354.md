# Independent bounded numeric review

Source: `e3d83544510aa07b99dc638665c91b91b1e6bce7`.
Disposition: **accept the isolated measurement evidence; do not activate production arc profiles/services.** A narrow transverse-join design revision is justified. The endpoint-incidence meaning, certified production primitives and final native postflight still block activation.

This reviewer launched no OCP/Blender process, installed nothing, and changed no repository production or release file. Analysis is pure Python/Fraction arithmetic over frozen source and the separately authored native records.

## 1. What passed, and what did not

All **176 intended engineering-scale positives** passed the unchanged, independently predeclared R0 area/volume comparison and the separate C0 face/volume consistency check:

- Calibration: 128 ordinary/paired fixtures. Maximum R0 area ratio 0.032035; volume ratio 0.025782; C0 ratio 0.027771.
- Holdout: 40 disjoint positives. Maximum R0 area ratio 0.046853; volume ratio 0.018171; C0 ratio 0.014652.
- Supplement: 8 rounded-hypot positives with exact center-relative vectors (13,29), squared norm 1010, and the frozen rounded canonical radius. Maximum R0 area ratio 0.005739; volume ratio 0.001321; C0 ratio 0.001642.

These include quarter/major sectors and arc/chord segments, both authored directions, traversal reversal, new frames, nonzero local centers, far world origins, and selected radii/heights in 1–1000 mm. They are finite-fixture qualification, not continuous-domain proof.

All **273 native records**, including **97 controls**, are retained: 233 old fixed-check passes, 6 old fixed-check failures, 32 frozen-core rejections, and 2 native constructor rejections. A native fixed-check pass is not profile admission.

Important retained exclusions:

- At radius 1e-6 mm, quarter-sector/quarter-segment ideal areas are approximately 7.854e-13 / 2.854e-13 mm². Their native shapes can pass structural checks while failing Amin=1e-12 mm². The same distinction holds for the tested immediately-above radius neighbors.
- Six tiny chord/sweep controls have nonpositive native face/volume quantities. Their ordinary libm small-area references are cancellation-prone; these are failures, not evidence of usable geometry.
- Two core-accepted near-maximum negative radial residuals at far origins fail native MakeEdge. No tolerance increase or retry-to-repair is justified.
- Two positive near-1e-7 far-origin residual controls exceed the certified **ideal** Green-plus-gap area interval plus R0, and fail C0 at about 2.166 times its allowance. Native validity and stored tolerances alone do not make them usable.
- C0 fails 21 calibration residual controls and 6 zero-origin supplemental ±1e-9 controls. Two of those six supplemental controls are below the proposed 1e-9 endpoint ceiling in both the recorded equation and recorded native evaluation. The stricter endpoint ceiling is therefore necessary at most, never sufficient.
- All 12 supplement threshold controls pass the ideal Green-plus-gap area/volume comparisons plus R0, while the six zero-origin ones fail C0. Broad endpoint-gap area uncertainty must not be reused to excuse native face/volume inconsistency.

See `calibration_gap_consistency_results.json`, `holdout_gap_consistency_results.json`, and `supplement_gap_consistency_results.json` for every evaluated pass/failure. Nonorthogonal cancellation-prone controls are not silently included in the orthogonal oracle.

## 2. Frozen empirical envelopes

`FROZEN_R0.json` SHA-256:
`ae573f070c65dd68998290f05c49499a206cb8961f695e3012487c661e3fd20a`.

R0 was sent and fixed before this reviewer inspected calibration results:

- u = 2^-53; n = authored boundary count.
- W = max(1 mm, absolute transformed requested endpoint/center coordinate).
- L = max(1 mm, local endpoint bounding-box diagonal, canonical radii).
- P = analytic perimeter; A = independent analytic interval midpoint; H = positive perpendicular height.
- E_A = 128 u n L² + 16 u W P.
- E_V = H E_A + 128 u n L² H + 16 u W A.

The coefficients are fixed **empirical engineering comparison margins**, not a proved OCCT error theorem. They were not fitted or widened for individual outcomes. Pure area/endpoint/parameter uncertainty belongs in its own interval. R0 is not independently qualified here for arbitrary 256-edge profiles, slivers, lenses, all sweeps, arbitrary native versions/platforms, or every continuous input between tested fixtures.

`FROZEN_CONSISTENCY_C0.json` independently fixes:

`|V_native_local − A_native_face H| <= E_V + |H| E_A`.

This is triangle-inequality propagation of R0's two allowances, with no additional fitted constant and **no endpoint-gap interval-width term**. It was fixed after calibration identified the separate consistency issue and before this reviewer inspected holdout mass results. All subsequent outcomes, including failures, are retained.

## 3. Which statements are mathematically certified

The small exact oracles establish only their explicitly stated mathematical objects:

- Exact dyadic endpoint differences establish orthogonality, branch selection, and endpoint cross-products.
- A rational alternating-series Machin enclosure establishes π. For the orthogonal fixtures, this yields rigorous nominal ideal-circle/straight-radial-connector areas using the frozen canonical radius. Segment area uses the actual endpoint cross-product, not an unjustified substitution of r_canonical².
- A separate bounded calculation implements the proposed ideal Green integral and Egap enclosure. It does not establish contact topology, arbitrary within-cell closure, or native healing.
- Exact Fraction rotation comparisons establish per-record coordinate-conversion errors against the mathematically normalized authored quaternion. The first 135 pure fixtures have maximum L1 error 4.656612873077393e-10 mm. The recorded calibration endpoint conversions have maximum 1.1647613124636754e-10 mm. Neither is a universal bound over every allowed quaternion/input.
- Forty-eight-term rational sin/cos Taylor polynomials with rigorous Lagrange remainder and outward square-root intervals bound the **serialized circle equation** q(t)=C+r(U cos t+V sin t). They also bound the perpendicular height for the recorded mathematical plane equation.

These do not prove that the native inserted edge retained the pre-constructor circle representation, or certify native mass integration. That equivalence still requires production postflight. Calibration did not record the normalized native plane direction, so its height use remains approximate.

## 4. Recorded equation versus native evaluation

For the 40 holdout positives, the maximum certified recorded-equation endpoint discrepancy is 2.328375178965164e-10 mm. The maximum distance between **recorded native curve.Value output** and the vertex is larger: 3.292722539913597e-10 mm. In holdout_035, recorded native evaluation differs from the recorded equation by about 1.291935856043136e-10 mm.

The smaller equation bound is **not a bound on all native evaluations**. The audit explicitly preserves both values. Roundoff and possible representation changes must not be conflated.

The 8 rounded-hypot positives also pass the equation-model 1e-9 bound; maximum is approximately 5.2063e-11 mm. Several far-origin negative threshold controls pass the equation-model ceiling but fail the recorded native-evaluation ceiling. Production must not substitute the easier measurement.

Evidence: `holdout_parameter_model_evaluation_audit.json` and `supplement_parameter_model_results.json`. Each contains source-record hashes and the axis-normalization defects instead of assuming exact unit/orthogonal double vectors.

## 5. Contact/collar and endpoint-incidence blockers

The collar policy has substantial geometric effect. For two acute incident straight rays, with s,t measured from their shared endpoint, the distance infimum outside the paired collar is Ljoin sin(theta). Dclear/Ljoin=1/2 therefore excludes openings below 30 degrees. Equality has no positive uniform margin and needs explicit treatment. A minor arc/chord segment has endpoint opening delta/2, so ordinary-radius segments below roughly 60 degrees are excluded near the collar even when their total area is large. Finite curvature still requires the actual certified distance calculation.

Quarter/major sectors and segments are sensible first positives: their relevant openings are 45, 90 or 135 degrees. Ljoin must not become permission to merge roots. Every additional root, including one inside a collar, remains separately classified.

More fundamentally, an exact shared solved point p is not always the mathematical curve endpoint q. Example: center (0,0), start (10,0), end (0,10.00000005), ccw. The frozen radial gate passes, but the end of the radius-10 circle is (0,10); a radial closing line meets it strictly inside the line rather than at its declared solved endpoint. Even the authored start generally differs from an exact circle whose radius is rounded hypot. Requiring exactly zero discrepancy would reject ordinary valid binary64 data for accidental rounding.

The current phrase “only declared endpoint contact” therefore lacks a complete meaning for allowed residuals. Native success and Egap do not fix that semantic issue.

## 6. Smallest sensible next design boundary

Recommend a **visible pure-policy revision and independent review**, initially limited to one arc plus its chord or two radial lines, transverse joins, and an ordinary engineering scale such as radius/positive height 1–1000 mm. Preserve all frozen core admission and authored bytes. Do not claim every point in that range is constructible; all certified pure and native postflight conditions still apply.

A separately defined join cell is a reasonable bounded next design:

1. Exact shared point ID p; actual curve endpoints q remain unchanged.
2. Cell size derives from certified actual endpoint/parameter/transform discrepancy, is much smaller than Ljoin, and cells are disjoint.
3. Each incident one-sided branch exits once; no foreign boundary enters.
4. Every finite-curve root is isolated and counted. At most one root is uniquely assigned to a declared join; a zero-root bounded gap has explicit semantics. A second root is never merged or excused.
5. Restrict the first proof to transverse joins. Smooth tangent continuations, lenses and general tangent/cusp cases need separate later work.
6. Any area interpretation allowing arbitrary simple within-cell closure needs its own proof. For two consistently oriented Jordan boundaries identical outside disjoint disk cells, their area difference is at most the sum of disk areas. Without simplicity and a no-multiple-winding argument, that claim does not follow from the present straight-connector Egap bound.

A fixed **actual endpoint-discrepancy ceiling of 1e-9 mm** is a defensible candidate support restriction: 1% of stored Tnative and 1/400 of Ljoin leaves geometric separation between the concepts. It is a new conservative product limit, not an inferred kernel theorem or a replacement for C0. All ordinary positives tested here satisfy it; the threshold controls show why remaining checks are essential. A future implementation must specify the exact numerical comparison, include certified arithmetic/native-evaluation error, preserve threshold ambiguity, and permit honest unsupported failures at far origins. No point projection, tolerance raising, hidden endpoint welding or repair is authorized.

Keep Tnative=1e-7 as the independently checked stored-tolerance ceiling. The supported interval/primitive resource bound must be implemented and reviewed; 256-bit interval precision alone does not cap exact predicate integer size. Binary64 input magnitude and fixed polynomial degree permit an explicit bit bound, recorded in `pure_review_results.json`.

## 7. Final recommendation

**Proceed only to the narrow endpoint-incidence/pure numeric design review. Do not enable production classification, kernel service dispatch, v3 capability advertisement, UI or releases from these measurements.**

There is now credible finite-matrix evidence for ordinary sector/segment construction with fixed R0/C0 and strict postflight. The remaining blocker is meaningful and bounded: define the join semantics, implement and independently certify the chosen pure primitives and actual discrepancy/height budgets, prove inserted native representation/identity, then rerun the same fixed comparison policy against those production intervals. Do not widen envelopes to rescue controls.
