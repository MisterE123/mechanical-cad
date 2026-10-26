# Bounded sector native normalization and work limits

Status: the final bounded native implementation is independently qualified on
frozen snapshot9. The useful release remains 0.5.2. See the
[native milestone](../../ARC_SECTOR_NATIVE_MILESTONE.md) for exact positive,
negative and full-regression evidence. Sector services and Blender publishers
remain inactive. This policy does not change general arc geometry.

The sections below retain the reviewed implementation sequence and earlier
failures. Prospective wording describes the decision at that stage; the final
qualification summary is in the linked milestone.

This narrowly revises the native conversion gate described in
`SECTOR_IMPLEMENTATION_PROPOSAL.md`. The domain remains one arc and two
shared-endpoint-ID radii, the approved 1–1000 mm radius/height range, exact
signed-permutation placement and zero world origin. All authored coordinates,
analytic roots, geometric discrepancy bounds, incidence cells and source mass
comparison bounds remain authoritative.

## Why the original native gate failed

Two distinct failures were retained rather than reclassified as success:

- With the original 100,000-operation cap, one of the 70 required preparation
  cases exhausted the budget before geometry construction. Other cases had
  insufficient room for the required postflight checks.
- In the rounded-hypot case, the prescribed `gp_Dir` constructor changed both
  nonzero radial components by one binary64 neighbor. The original exact-field
  gate rejected this observation. That diagnostic stopped before any face,
  prism or shape registration.

The original source snapshot, strategy, process receipts and failed comparisons
remain separate from every subsequent revised-policy result.

## Observe once, then prove the actual radial support

Let `u = 2^-53`, and retain the existing source-derived direction `d0` and length
`ell`. Before construction, prove exactly that `|d0·d0 - 1| <= 4u`. Freeze the
component bound `|d_actual[i] - d0[i]| <= 8u = 2^-50`; exact zeros stay zero and
nonzero component signs stay unchanged.

This fixed envelope is a conservative supported-constructor policy. An ordinary
round-to-nearest normalization model, including gradual underflow, motivates the
bound. It is not an assumption about OCCT's implementation or an extra physical
design tolerance.

Construct each prescribed support once. Decode its actual coefficients and
check the frozen envelope. Then, in the same continuing checked context:

1. Reprove actual affine-trace and circle-root endpoint discrepancies against the
   original authored points.
2. Reprove the actual ray pair, winding branch, angle and representation-area
   bounds.
3. Preserve both roots and every finite-membership record for each actual
   endpoint cell and proxy, including all four center-proxy roots.
4. Reprove separation, exclusion, collar and exterior-trace obligations and
   regenerate the actual reference/class-area records.
5. Retain intended and actual witnesses, count every retained root against the
   unchanged limit of 64, and enforce the unchanged 1 MiB record bound.

All of this must finish before face assembly. The source/circle-derived common
cells, source area window and `R0`/`C0` limits cannot grow in response to an
observed radial direction. An in-envelope direction can still fail any geometry
gate. No retry, averaging or alternative support construction follows. The
separately reviewed endpoint-representative policy below explicitly permits
bounded native projection; it does not change this radial-support policy.

Both the 3D and 2D constructors receive `d0`, not a previous observation. The
actual stored 2D direction must equal the mapped actual 3D direction exactly,
with exact corresponding center, range, plane and identity. Otherwise reject
`native_surface_trace_mismatch`. Freeze accepted fields and require exact
preservation at subsequent edge, wire, face and prism stages. Actual evaluated
endpoints, tolerances, topology, provenance and masses remain separate required
native observations.

## Explicit work ceiling, unchanged pure default

The primitive resource policy now distinguishes:

- `DEFAULT_OPERATIONS = 100_000`: unchanged ordinary pure-context default.
- `MAX_OPERATIONS = 200_000`: explicit hard ceiling that a caller may request.

Only a new native/shared entry with no supplied context requests the larger
ceiling. Supplied contexts keep their exact identity, limits and prior charges.
Every continuation and extrusion uses that same context. There is no budget
reset, subclass, hidden constructor bypass or mutable upgrade.

Fresh source classification must finish at an **absolute** counter no greater
than 100,000, including prior caller work and genuine core incidence work. Reject
before conversion if it exceeds that readiness limit. A larger enclosing context
does not imply classification stops exactly at 100,000; the total hard ceiling
still applies. Original default pure classification retains its actual 100,000
stopping bound.

The protected primitive exception is exactly the ceiling/default constants and
the constructor's default expression, with required signature formatting. Its
arithmetic, bit guards, interval precisions and read-only counter remain exact.
Tests explicitly distinguish the old default from the new hard ceiling; the
historical primitive fixture and unrelated-byte mutation checks are retained.

## Evidence limits and next gate

An isolated, native-free diagnostic copy completed 70 cost paths. Its maximum
was 139,107 charged operations: 115,207 preparation, 3,650 synthetic endpoint/mass
checks and 20,250 synthetic support reproof. The run took 7.43 seconds and peaked
at 17,208 KiB RSS. These figures exclude native C++ work and are neither native
acceptance nor a completion guarantee.

The independently reviewed fixed-call-graph planning allowance is deliberately
larger, 524,288 operations, and must be reconciled with the final implementation.
The enforced 200,000 limit is a fail-closed support limit, not a promise that every
mathematically valid input completes. Missing implementation checks cannot be
omitted to fit it. Every required positive case must pass the complete actual
native path before this gate can be qualified.

The sealed independent revision contract is
`NORMALIZATION_AND_RESOURCE_REVISION_CONTRACT.md`, SHA-256
`5f01f40d67e929dbf6ff3eeabd72ae50eb9e398b17fec35353ba39b6ccaa770b`.
The separately sealed failed-gate review is `FAILED_NATIVE_GATE_REVIEW.md`,
SHA-256 `844d8a127afa58e60f83451a9bdce7961a755ddb4e2100b4dd27cc55df669eff`.
Qualification artifacts are preserved outside the source tree.

Detached observed-support records remain data. Future client validators must
recompute them from strict original source, plane and observed coefficients.
They cannot use caller-supplied plans or caches as authority. Production
`GuardedEvidence` remains v2-only; service and owner integration require their
separate reviews.

## Retained native representations

The native gate also distinguishes a retained face's own pcurve from additional
legitimate representations on a shared edge. The bounded collector inventories
every stored representation before selecting the unique retained-surface owner.
Location, range and analytic-field predicates cannot hide a second owner. Missing
or ambiguous ownership fails; the collector never silently chooses the first
matching-looking representation. Exact selected 2D/3D correspondence, orientation,
edge/vertex identity and later-stage preservation remain mandatory.

The prescribed prism may retain the source end-cap plane and place it with a
location. The supported last-cap form is narrowly the same underlying face and
retained local plane, forward orientation and exact translation `H * normal`.
Both observed shape and surface-location matrices must match that translation.
Apply the surface location exactly once when interpreting the raw plane. Baked
coordinates, general affine placements, foreign faces, wrong normals/heights and
double application fail. This does not change construction or source/mass bounds.

These corrections have separately frozen pure reviews and actual observations.
One cardinal CCW case subsequently passed the complete face/prism path. The next
cardinal CW case failed because the edge constructor stored a periodic range
different from the requested range. The remaining 68 positive cases were unrun.
This partial result does not qualify the complete native matrix.

## Predeclared periodic trim policy

The next approved correction selects one candidate before construction. It does
not accept an observed range modulo a period or retry after a failed comparison.
Retain the original authored-order parameters `(a, b)`, computed from principal
`atan2` and the existing signed core sweep. Keep the original Taylor admission
domain `[-8, 8]`, authored coordinates, IDs, direction and canonical radius.

Let `tau` be the exact binary64 value `0x1.921fb54442d18p+2`, distinguished from
mathematical `2*pi`. For `l = min(a, b)`, choose the sole supported common shift:

- `k = 0` for `l >= 0`;
- `k = 1` for `-tau <= l < 0`;
- `k = 2` for `-2*tau <= l < -tau`.

Require `l < tau`. Compute each new authored-order parameter with one prescribed
binary64 addition, `a' = RN(a + k*tau)` and `b' = RN(b + k*tau)`. The increasing
pair `(L, U)` must satisfy `0 <= L < tau`, `L < U < 12`, and a nonzero span below
both `tau` and certified mathematical `2*pi`. A tiny negative lower parameter
that rounds to `L = tau` rejects. There is no snapping, independent endpoint
shift, alternate turn count or fallback construction.

The same continuing checked context records both exact addition residuals and
the signed period residual using freshly certified pi. For each endpoint,

    e_t = t' - t - k*tau
    delta_t = e_t + k*(tau - 2*pi)

The exact signed-span change is `e_b - e_a`; binary64 period addition does not
promise literal equality of the old and new spans. Preserve the directed source
branch through the existing signed-angle/error and full finite-membership
obligations. Do not add a literal minor/major label test that rejects supported
semicircles. Reversed, complementary and full-circle substitutions still fail.

Only the original `(a, b)` enter the unchanged 128-term trigonometric evaluator.
Transport those certified component intervals to the new parameters using the
bounded phase residual and the sine/cosine derivative bound of one. Reprove the
canonical endpoint gaps and every affected cell/root/membership/collar obligation
before construction. All actual stored 3D and 2D ranges and vertex parameters
must then match the one frozen canonical range exactly at every required stage.

### Preserve numerical source and mass references

The previous plan's native conversion radius also widened its source comparison
area. Therefore preserving its formulas alone would not preserve its numerical
source reference. Compute the original unwrapped radius from the same old
endpoint/gap proof and retain the exact old arithmetic sequence for
`2*pi*old_rho^2`, `source_comparison_area`, its area-floor check and midpoint.
These old values remain the only source comparison and mass targets.

Compute the canonical native radius once from the existing `16 * max(...)`
recipe using the new prospective circle gaps, with the same cap and no observed
kernel input. This new radius applies only to canonical native cells, their
complete root ledger, native class area and accepted-support continuation. Retain
old/new intervals, gap witnesses and scalar cell bounds in the record. Do not
duplicate an obsolete root ledger. The source certificate, Delta, clearance,
source comparison, EA, EV and C0 cannot change or grow.

The contract is `PREDECLARED_PERIODIC_TRIM_CONTRACT.md`, SHA-256
`13b863853538207079cb98df359db644bc6b1e3f75da8118384160a476ec1116`.
Its 70-input independent rational check is design evidence, not native acceptance.
Implementation must separately prove exact snapshot4 source/mass-reference
identity for all 70 inputs, pass the complete synthetic pipeline under the
unchanged 200,000 ceiling, and receive independent frozen-source review. Only
then can the original serialized native matrix resume, in the original order
with stop-on-first-failure. Neither this policy nor a mathematical interval proof
establishes empirical OCCT validity before that gate completes.

## Historical empirical stop: positive-gap prism volume

The frozen periodic implementation passed the first eight required complete
native solids, including both CW/CCW noncardinal and nonquadrantal controls. The
ninth input, `inward_gap_ccw`, has radius 10 mm, height 7 mm and an exact inward
endpoint gap of `2^-31` mm. Its profile area, retained representations and prism
provenance passed, but its measured volume failed the unchanged source R0 gate.
The remaining 61 required positives were unrun. No solid was registered for the
failed case; its previously accepted profile remained.

A separately reviewed observation-only replay retained the already-computed
failure values at the same guard. Area was 78.53981633974483 mm² and volume was
549.7787143745921 mm³. The exact volume distance from the fixed source window was
approximately `3.621672906e-9` mm³, compared with EV upper bound
`1.252064329e-10` mm³. C0 was not executed because volume R0 rejected first.
The original run lacked the rejected scalar; the later diagnostic is separate
evidence, not a replacement for that historical receipt.

This is an empirical native inconsistency under the prescribed construction and
measurement rules. It neither changes the source interval proof nor licenses
larger tolerances, mass allowances or substitution of analytic mass for the
native observation. A tolerated gap between finite analytic endpoints is a
possible explanation, not an established internal kernel mechanism. At that stage the native
milestone remained unqualified, with result-v3 services inactive pending a
reviewed resolution and complete qualification.

## Prospective canonical-radius radial trim

The next approved representation policy selects a separate finite radial end
parameter `T = r`, where `r` is the already frozen canonical binary64 circle
radius. It keeps `NativeLine.length` as the original rounded authored-ray
normalization divisor. The existing subtraction, `hypot` and division sequence
that produces `d0` is unchanged. In particular, do not normalize the authored
vector by `r` or choose a trim from observed kernel output.

Both prescribed radial edges and their pcurves use the single predeclared range
`[0, r]`. Snapshot 7 kept the original authored vertex handles, IDs, coordinates
and tolerances, using the existing explicit-vertex, explicit-parameter
constructor. That snapshot did not project or replace vertices, heal, or retry.
Its native-vertex rule is explicitly revised by the endpoint policy below;
the radial normalization and trim stay unchanged. Every actual range, vertex
parameter, curve coefficient and mapped 2D/3D field still requires inspection
at the existing stages.

For each intended and actually observed direction `d`, prove in the same checked
context that `A = d·d > 0`, alignment is positive and
`|r*d - v|^2 <= Delta^2`, where `v` is the exact authored ray. This endpoint
inequality bounds the entire corresponding affine trace. Reprove all disk,
proxy, collar, exclusion, finite-membership and reference-class obligations
against the unchanged source and canonical native cells. An otherwise admissible
source can fail this native representation check; it cannot trigger larger cells
or another trim candidate.

Preserve both simple roots of `A*t^2 - r^2 = 0` in distinct intended and actual
support-circle records. The negative root is before the finite edge. Classify
the positive root exactly from the sign of `A - 1`:

- `A > 1`: the positive root is interior to `[0, r]`;
- `A = 1`: it is the endpoint;
- `A < 1`: it is after the finite edge.

All three classes remain possible. The endpoint `r*d` differs from the positive
circle intersection `r*d/sqrt(A)` by `r*|sqrt(A)-1|`; retain its certified bound.
Do not infer literal analytic closure from a nominal unit-direction type or a
tolerance-closed shared vertex. Directed finite-arc membership is a separate
existing obligation, not implied by these finite-line classifications. Original
source roots and their memberships remain unchanged.

The historical counter named `retained_root_count` counted only auxiliary roots.
The revised record explicitly reports auxiliary roots, the four original source
support roots, and their full sum. Positive-source-cell cases have 60 auxiliary
plus four source roots, for 64 logical branches; zero-source-cell cases have
52 plus four, for 56. Enforce the unchanged 64 ceiling on the full sum, including
at intended-prefix and actual-support stages. Cross-checked nested views of a
source branch are not extra logical roots, but every encoded copy remains under
the unchanged 1 MiB bound. Historical receipts retain their original meaning.

The source certificates, normalization divisors/directions, periodic records,
old/canonical gaps and cells, original source comparison/midpoint/floor, EA, EV
and C0 must remain exactly equal for all 70 required inputs. The native ceiling
stays 200,000 and source completion stays absolute 100,000. A conditional 8,192
additional checked-operation planning allowance is separate from those enforced
limits; complete final-path counters and resource tests remain mandatory.

The sealed independent contract is `CANONICAL_RADIUS_RADIAL_TRIM_CONTRACT.md`,
SHA-256 `81147e77d4082a6edf836307cc3e468db314e59fc1ddbc5c7334bad7e195087a`.
Its 149-path rational check includes all three positive-root classes. The frozen
implementation subsequently passed its pure review, but the actual matrix again
stopped at `inward_gap_ccw` after eight successful solids. The prescribed radius
trim was observed and its rejected volume was bit-identical to the earlier
result. The trim alone was therefore not a remedy. All original failures remain
separate evidence; the full native matrix remains unqualified.

## Captured generated-edge inconsistency

A separately reviewed diagnostic applied four predeclared mass measurements to
the same rejected shape and reference point. Their results remained outside the
unchanged bounds. Those numerical estimates do not justify replacing the mass
method or enlarging an allowance.

One bounded read-only inventory then captured the three generated side faces,
their stored representations and shared vertices. For the inward-gap endpoint,
with `delta = 2^-31`, the generated vertical 3D line is
`(0, 10-delta, t)`, for `0 <= t <= 7`. The recorded cylinder has radius 10, so the
line's exact cylinder-equation residual is the nonzero constant
`-20*delta + delta^2 = -42949672959/2^62`. Its stored cylindrical trace instead
follows the radius-10 generator. The radial bottom/top trims end at 10, while
their shared vertex and vertical ruling remain at `10-delta`.

No stored face-owned planar pcurves were present on the radial sides. Exact
detached projection of the radius-b line coefficients gives two inferred UV
joins with gaps `+delta` and `-delta`. These are explicitly inferred boundaries,
not observations of the integrator's internal parameterization. Generated-face
orientation can differ from the actual prism occurrence and was kept separate.

This is a demonstrated whole-trace and finite-boundary representation mismatch.
It does not prove the complete mechanism or magnitude of the volume error. The
sealed review is `SIDE_FACE_INVENTORY_TERMINAL_REVIEW.md`, SHA-256
`474b7ee1c291c19f259d3716aac63fcbdb77747394433e0626ec0d4660e5b2b2`.

## Explicit bounded native endpoint representatives

The approved endpoint policy is **native projection/representation**.
Authored sketch coordinates and IDs remain unchanged; native outer-vertex
coordinates intentionally change. Do not describe this as unchanged native
coordinates, exact analytic closure, automatic repair, or a qualified mass fix.

Construct and inspect the same one circle and two radial supports before any
native vertex. Finish the existing actual-support proof in the same continuing
context. Evaluate the retained circle exactly once at each frozen authored-order
endpoint parameter. These two observed binary64 points are the sole candidates;
no snap, average, alternative evaluation, q-derived radial normalization or
retry is allowed. Preserve their raw observations before interpreting them.

Keep authored vertices in the plan and store native representatives in a
separate immutable record bound to source, plan, endpoint IDs/parameters and
context. Let `Q` be an observed world point, `F` the exact signed-permutation
frame and `c` the possibly nonzero local center. Compute
`qbar = F^-1(Q) - c` and `pbar = p - c` with checked exact subtraction. Retain the
original absolute `Q`; do not reconstruct it with floating addition. This makes
center-addition rounding part of the proof.

Using the unchanged positive canonical cell radius `rho = n/k`, original gap
upper bound `g`, and certified relative circle endpoint interval:

- Require exact squared distance to the authored endpoint to be at most
  `Delta^2`, and strictly inside its existing cell.
- Bound the distance from `qbar` to the mathematical circle endpoint by `e`;
  require `e <= Delta` and the strict checked margin `n-k*(g+e) > 0`.
- Bound distance to each intended and accepted radial endpoint `r*d` by Delta,
  retaining both witnesses and their existing strict cell inclusion.
- Preserve exact-zero source-gap semantics. The positive canonical conversion
  cell is not a newly invented source disk. No minimum cell radius is added.

These are bounds on the observed point relative to the exact serialized
equations, not a general accuracy guarantee for the native evaluator. Both
points must pass before constructing one shared native vertex per authored ID.
The center remains unchanged. Reuse the same handles across arc, radial edges
and cap, and require one corresponding top history vertex for each ID.

Radial directions, normalization divisors, `[0,r]` trims, the entire root ledger
with maximum 64 structural roots, cells, source comparison and all mass bounds
remain unchanged. Additional
profile checks bind every observed vertex to its representative and retain the
old evaluated-curve-to-authored Delta checks. Generated-side checks must bind
history to the unique actual prism occurrence before using its orientation.
Inspect the complete bounded stored-representation inventory and require exact
owner, placement, analytic coefficient, finite-range and branch correspondence.
Use the fixed support table from the contract; a new noncardinal plane
normalization is a rejection, not another application of the radial envelope.

For a vertical generator, the representative-to-circle or radial-end discrepancy
is constant over the whole height. For a verified affine planar trace, checked
endpoint residual bounds cover the full interval by convexity. Establish the
analytic type and coefficients before using this fact. Inferred projected joins
must themselves lie inside the same unchanged translated cells. Preserve the
distinction between stored and inferred planar traces, exact identity and
bounded geometric correspondence. All original validity, tolerance, area/volume
R0 and C0 gates still apply.

The source ceiling remains absolute 100,000 and the full ceiling remains
200,000; supplied contexts are never replaced or raised. The conditional added
planning reserve is 45,056 operations, not a new cap or completion promise.
Record/evidence limits remain 1 MiB with their existing production grammar.

The sealed contract is `CANONICAL_NATIVE_VERTEX_CONTRACT.md`, SHA-256
`0afaea94d6a500dfbd98be0706ece39f3eb9d9f2707e678931470e43e62cf429`.
Independent exact-rational feasibility checks passed 280 endpoint mapping
checks across 140 synthetic direction paths, including all 26 offset-center
cases in the unchanged 70-case matrix.
This shows no necessary binary64 representability blocker; it neither observes
the actual native evaluator nor selects its candidate.

Implementation requires a fresh pure freeze and independent review before the
same serialized 70-case native matrix, with stop-on-first-failure. All existing
and new negative controls follow the required positive gate. Any failed
representative, generated-field, trace, resource or mass check remains a failed
gate, without repair, retry, widened margins or a replacement fixture matrix.
Result-v3 services and Blender owner/UI activation remain gated separately.

## Snapshot8 native observations

The frozen endpoint implementation passed 4,220 native-trapped tests and an
independent replay of all 140 synthetic full paths. Its subsequent single native
run completed the first 12 original cases, including both inward/outward-gap
directions, with all trace, original R0 and C0 checks. In `inward_gap_ccw`, the
observed volume was `549.7787143782139`, under the unchanged allowances. This
resolves that observed failure; it is not a claim about all supported inputs.

The run stopped at index 12, `semicircle_ccw`, on an unsupported
`BRep_CurveOn2Surfaces` inventory record at the center vertical edge. It had one
accepted profile and no registered solid; 57 cases remained unrun. The collector
retained the type, three false geometric flags and first identity location, but
did not observe the two surface associations, second location, regularity flag
or continuity value. No generated proof or volume measurement followed the stop.
The terminal review is `CANONICAL_NATIVE_VERTEX_TERMINAL_REVIEW.md`, SHA-256
`155cae793035078d276a480bce62c6acd6323973d9f48551ac475d930396329e`.

## Advisory-only generated regularity metadata

The next reviewed collector extension treats this documented two-surface
continuity record as advisory metadata. The exact type and flag combination
selects a separate branch before geometric getters. It must never call Range,
Curve3D, PCurve, PCurve2, Value or D0 on that record. Existing closed-surface
pcurves also report regularity, but retain their distinct geometric two-branch
grammar. See the official [OCCT class reference](https://occt3d.com/dev/doc/refman/html/class_b_rep___curve_on2_surfaces.html).

Admit zero or one metadata record across the existing nine-edge graph, only on
the center vertical edge. Its two distinct native-handle associations must be
the actual adjacent radial-plane faces, with each complete plane observation and
paired placement checked exactly. Both native record locations must report
identity and carry exact identity matrices, alongside the existing identity
edge and side placements. Preserve both complete pair orders, all fields and
the original inventory index. Wrong owners, placements or malformed data reject.

All seven documented continuity enum values are retained with exact type/name/
value checks and have no geometric authority. In particular, the enum proves no
exact straightness, coplanarity or continuity. Near-antipodal inputs retain the
same geometric checks whether this metadata is present or absent. The record
cannot satisfy or replace a 3D support, pcurve, branch, range, trace, validity or
mass obligation. No construction, native plan, representative mapping, source,
root, cell or mass criterion changes.

The record counts toward the existing eight-entry/eight-handle inventory and
complete evidence limits. Source 100,000, total 200,000, generated-stage 32,768,
64 roots, 1 MiB, 8,192 nodes and 64 events remain unchanged. The supplementary
372-tick schedule is within a 1,024-tick planning reserve, not an increased cap;
actual implementation accounting and full-path qualification are still required.

The sealed design is `REGULARITY_METADATA_CONTRACT.md`, SHA-256
`5b95315093ed99b834f2a45062a818a0e68883f6c5e4d6bc3eedf1cd5cadd01a`.
It required a new pure freeze and independent review before the explicitly
authorized original-order native matrix. Snapshot8's failure remains preserved.
The final snapshot9 passed all 70 original positive cases, the fixed companion
and every prescribed negative disposition. Its optional metadata remains
advisory only; all trace and fixed mass checks retain their original authority.
The complete Git-free regression then passed 9,687 tests and 19,597 subtests,
with Ruff/format clean. See the linked milestone for bounded coverage, exact
receipt hashes and the separate remaining result-v3 service boundary.
