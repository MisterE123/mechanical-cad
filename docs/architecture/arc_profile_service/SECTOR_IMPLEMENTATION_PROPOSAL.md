# One end-to-end sector milestone after incidence qualification

Design only, 2026-10-17. Read baseline: `306820456a3b63c5e3c412f59b1b5c3be6fe13f3`.
No implementation, native execution, activation, or release approval is implied.
The parent subsequently reported the incidence freeze at
`94acd98f97e4fb9848bbf19eee5052fec232a83a`; its running full regression and
independent audit are not assumed complete or qualified by this design artifact.

## Decision in one paragraph

Approve one bounded integration milestone: a **single arc with its two shared-ID
radii**, exact authored-ray sweep in **[90,270] degrees**, canonical radius and
positive extrusion height in **[1,1000] mm**, through a certified pure sector
result, one checked native face/extrusion, and explicit **data-only solve/Part
result 3** tests. Include the reviewed small positive gaps in this milestone.
Use sector-specific cells and a short uniform clearance proof instead of a
general arrangement or the generic 27-patch distance enumerator. First native
placements have zero workplane origin and a separately certified exact
signed-permutation frame. Other placements fail native preflight explicitly.
The milestone ends with an independently reviewed, frozen core/service artifact
and a reproducible sector/radius-edit example, not another unused leaf. There is
no UI, production v3 evidence, export/geometry-v3 service, Assembly-v3 service, or
release rebuild in this proposed scope.

This visibly narrows the dormant service proposal. It does not claim its chord,
multi-arc, open-arc, arbitrary-frame, Assembly, or export outcomes. It preserves
the broader already-reviewed *source* transverse semantics for the sector form.

## Why this domain, rather than only exact-zero quadrants

An exact-zero 90/180/270-degree sector is a useful positive-control family.
Exact dot zero with nonzero cross gives 90 or 270 according to direction; zero
cross with negative dot gives 180. Its reference area is `k*pi*r^2/4`, for
`k=1,2,3`. It needs no arbitrary source-angle enclosure or source gap cells.

That restriction is meaningful but narrow:

- At center zero, cardinal points `(r,0)`, `(0,r)` work for ordinary stored
  binary64 radii, including the binary64 value written as 5.1. This does not
  require the decimal 5.1 to be an exact real input.
- Pythagorean dyadics also work, for example `(3,4)`, `(-4,3)`, canonical r=5.
  Exact-zero is not synonymous with axis alignment.
- `(13,29)`, `(-29,13)` has exactly perpendicular equal-norm rays, but canonical
  rounded hypot is not exactly sqrt(1010). It needs the positive-gap path.
- `(1,1)`, `(-1,1)` has the same issue. Equal computed radii and zero *computed
  residual* do not establish `S_i=r^2`.
- Translating authored coordinates, applying a general frame, or solving a
  radius edit can introduce tiny representational discrepancies. No solver
  promise makes exact-zero or exact orthogonality automatic.

Most importantly, exact source endpoints still do not equal arbitrary rounded
native trigonometric endpoints. The sealed native contract requires separate
conversion cells/checks even for an exact quarter sector. Thus exact-zero alone
does not eliminate the difficult native integration work. Since sector source
cells and clearance have very small fixed constructions, completing the whole
reviewed sector source domain now is more useful than installing an exact-zero
acceptance flag and postponing ordinary rounded-hypot sectors again.

If implementation review cannot qualify the native representation gate below,
do not silently shrink the milestone to cardinal examples. Return the exact
failed gate and retained evidence for a new owner decision.

## 1. Source admission and pure result

The new explicit pure entry point, provisionally
`classify_sector(sketch, *, context)`, accepts the existing immutable numeric
Sketch, not caller-fabricated incidence evidence. It recomputes the qualified
incidence prerequisites using the **same non-resetting arithmetic context**.
Its function name/status must distinguish a complete region result from the
existing prerequisite report. A separate extrusion preflight checks height;
solve-only profile readiness must not invent a requested height. If the current
incidence API requires height, an adapter's documented fixed value 1 is only a
way to invoke that prerequisite, never evidence about an extrusion height.

Requirements, in fixed diagnostic order:

1. Unchanged typed validation, unchanged core equal-radius geometry, exact source
   bytes/IDs/direction and canonical binary64 start radius.
2. Exactly one arc and two radial lines, one center ID and the arc's own start/end
   IDs shared at the required joins. Distinct-ID coordinate equality or a
   coincidence relation cannot repair missing incidence. No circles, chord,
   extra boundary, hole, branch, second loop or alternative center.
3. r in [1,1000], exact authored-ray dot <= 0, and the preflight's exact necessary
   endpoint discrepancy comparisons. Preserve every support root, multiplicity,
   original line/arc membership and unresolved outcome.
4. Source incidence cells (or exact-zero path), proof-only reference closure,
   paired-proxy collar/clearance proof, winding, and certified positive area.
5. A complete immutable sector result containing ordered boundary uses, original
   identities/core result, root ledgers, all certificate fields and operation
   counters. An unsupported or ambiguous result never masquerades as a region.

The result is a pure mathematical reference-region certificate, not solver
evidence, a native shape, GuardedEvidence, publication authority or wire receipt.
Kernel/service consumers must recompute or independently validate it against the
bound numeric Sketch; public dataclass construction is not validation.

### Cells: the sector specialization is finite

Let `a_i=sqrt(S_i)`, `q_i=c+(r/a_i)*v_i`, `d_i=|a_i-r|` and Delta=1/10^9 mm.
Use precisely the reviewed `eta_i=min(U_i,Delta)` after independent `d_i<=Delta`
proof, `rho=16*max(eta_i)`, and 64/128/256 precision schedule. Preserve exact-zero
separately; when both gaps are zero there are no source cells and E_source=0.

For positive rho, each own positive radial root q_i is strictly inside its cell.
Prove the cell/circle intersection is one short arc with two transverse support
exits, while the selected finite source arc has one endpoint portion and one
exit. The finite radial segment has one endpoint portion and one transverse exit.
Retain both support exits and use exact direction signs to select the finite one.
Show the trim change from p_i to q_i lies in the same cell. This is proof geometry
only. No connector is inserted or claimed literally simple.

Auxiliary circle/disk exits must use exact coefficients, not rounded auxiliary
points passed through the public binary64 line-input API. With v=p_i-c and
S=v.v, write an exit as `c+alpha*v +/- beta*perp(v)`, where
`alpha=(r^2+S-rho^2)/(2*S)` and `beta^2=r^2/S-alpha^2`. Use a fixed homogeneous
quadratic-radical representation with checked denominators; rho may contain the
exact rational Delta cap. This is one bounded circle/disk formula, not a second
unbounded rational engine. Its strict positive radicand, angular membership and
inside/outside tests require independent review.

The source inequalities make the remaining checks particularly small: each
`a_i >= 1-Delta`; exact nonpositive ray dot gives
`|p0-p1|^2 >= a0^2+a1^2`, and the other outward radius is at distance at least a_i
from p_i. Thus center exclusion, foreign-radius exclusion and disjoint outer
cells/proxies have large fixed margins. Still encode and test the inequalities,
circle/disk exit multiplicity, selected branch and cell containment. The negative
root is always outside its own finite radial line, including a semicircle where
it equals the other outer endpoint; its arc membership remains recorded.

The reference region is the source circle arc plus the radii c->q_i. The two
finite radial interiors meet only at c and lie strictly inside the circle. This
gives the Jordan proof, including the straight-continuation semicircle center.
The reviewed same-exterior/simple-closure theorem then supplies `2*pi*rho^2`.

### A short sector clearance lemma replaces generic patch enumeration

Use the existing exact values `b=7L/8=3.5e-7`, `L=4e-7`, `D=2e-7` mm. First prove
the same proxy portions/one-exit conditions and their inclusion in length-L
collars; the existing short-circle-arc bound with `b+d_i` suffices.

For one radius, write q0=r*u, a circle point q, and a point p=s*u on its outward
radial segment, in coordinates centered at c. Set x=|q-q0| and y=|s-r|. Exactly:

    |q-p|^2 = y^2 + (s/r)*x^2.

If s<r/2, the reverse triangle inequality gives |q-p|>r/2>D. Otherwise
`|q-p|^2 >= (x^2+y^2)/2`. If either original point lies outside the common proxy
disk centered on the authored endpoint, triangle inequality gives
`max(x,y)>=b-d_i>=b-Delta`. Finally,

    (b-Delta)^2 - 2*D^2 = 4.1801e-14 mm^2 > 0,
    r/2 >= 1/2 mm > D.

Thus every such nonexempt line/circle pair has distance strictly greater than D.
The argument works on the entire circle, so restricting it to the chosen minor,
major or semicircular arc cannot invalidate it. It does not suppress roots.

For the two radii, exact nonpositive ray dot implies
`|s*u0-t*u1|^2 >= s^2+t^2`. Outside their common center proxy, one parameter is
at least b, hence separation >=b>D. This covers the antipodal case as well.

This is a proposed independently reviewable *specialization* of the existing
paired-collar policy, not a new distance tolerance or a sampled approximation.
Review the identity, collar inclusion, disk exit conditions and all strict versus
inclusive boundaries. Generic line/circle stationary-point enumeration is not
required for this three-edge source form.

### Area and bounded arithmetic are part of the same milestone

Compute theta from exact cross/dot, exact quadrant/direction and the reviewed
bounded atan/pi construction: reciprocal reduction, two half-angle reductions,
128 alternating terms and explicit remainders, Machin pi, outward rounding.
Theta is signed in the authored direction throughout source/core/native
comparisons; absolute theta is used only where area or perimeter requires it.
Special-case exact quadrants without evaluating an arbitrary angle. Source area
is `r^2*|theta|/2 +/- E_source`, with E_source the proved cell-area upper bound.
The normalized lower endpoint must be >=1e-12 mm^2. Keep authored direction and
temporary positive boundary traversal separate.

Add only the finite interval operations needed by these formulas. Reuse checked
dyadics/signs/sqrt and the existing context; no unbounded Fraction implementation,
new generic algebra package or reset between cells/area/native checks. Keep
65,536-bit intermediates, 100,000 aggregate operations, precision 64/128/256,
bounded exponents, 256 refinement steps and the 1 MiB certificate ceiling. The
reviewed small counts of curves, cells, proxy disks and auxiliary roots remain
hard caps. A cap hit is an explicit nonpassing numerical result.

## 2. Native conversion is a deliverable with a pass/fail gate

### Fixed first placement domain

Require zero workplane origin. Certify that both the exact normalized authored
quaternion and the actual existing `_profile_plane(..., strict=True)` result are
the same orientation-preserving signed-permutation frame. This allows identity
and explicitly tested exact axis permutations, such as quaternion
`(0.5,0.5,0.5,0.5)`. It does not admit an arbitrary near-unit frame merely because
its computed axes look close. Local centers may be nonzero and near the unchanged
coordinate limits. Signed permutation maps stored coordinates exactly; no
translation sum or global rotational approximation is hidden in source cells.

Other core-valid frames and nonzero origins return
`unsupported_native_frame`; their core and pure source result remain valid.
No authoring coordinate or workplane is normalized in the saved model. Require
inserted circle/plane axes and center/radius to retain the planned mathematical
support exactly, otherwise reject this first adapter. This deliberately avoids
a general global-circle deformation bound.

### Before construction: freeze the intended representation

Keep workplane +U as circle parameter zero. Freeze a single construction rule:
candidate start parameter from the original binary64 start-minus-center and
atan2; candidate end from its binary64 sum with the unchanged core sweep. For CW,
use an increasing interval with temporary orientation reversal. Keep one explicit
unwrapped branch; no modulo-turn comparison can conceal a full turn. Libm values
are proposed native parameters, never certificates.

Use independent outward trig/angle enclosures to prove the actual candidate
parameters represent the selected source branch and endpoint distances <=Delta.
For this bounded path, require the unwrapped candidate parameters in [-8,8].
An explicit finite trig implementation can use 128 sine/cosine Taylor terms,
with Lagrange remainder bounds `|t|^257/257!` and `|t|^256/256!` respectively,
and outward rounding at the shared precision. No guessed libm ULP envelope or
unbounded range reduction is needed. Review those remainder and work bounds.
Explicitly adopt, only with this proposal's approval, the previously unresolved
additional gate `r*|theta-sweep_core|<=Delta`. Do not redefine sweep_core or use
this gate instead of the endpoint tests.

Prepare explicit native radial support candidates from c and each authored ray,
with the original vertex doubles c/p_i and a deterministic binary64 direction/
parameter construction. No projection or alternative endpoint is supplied.
Concretely, propose one candidate using the unchanged binary64 p_i-c subtraction,
its computed hypot ell_i, binary64 component/ell_i direction, and parameters
0/ell_i. Pass those planned supports and original vertices explicitly. Treat
any native re-normalization/change of the planned fields as postflight failure,
not permission to choose a different candidate after observing the kernel.
Certify before construction that both each outer equation endpoint and its own
circle-support root are at distance <=Delta from the same authored p_i. These
are separate conditions, not consequences of the source gap bound.
The line-support direction can be slightly different from the exact authored ray
because normalization rounded. This is a **whole-trace** change requiring its own
area analysis, even with an exact frame.

Freeze the final local cell radius using the sealed source/intended-arc endpoint
rule before any native constructor. In addition, require every planned radial
equation endpoint and its intended own circle root to lie strictly in the
corresponding already-frozen outer cell. Failure rejects; do not enlarge that
cell to accommodate a line. Verify the two planned radial supports originate
exactly at c, are outward, have nonpositive exact mutual dot, meet only at c, and
retain the expected finite parameter orientation. The same source cell/exit and
clearance specialization now applies to this planned radial-sector reference.

The native reference angle theta_N is the exact directed angle between these
planned radial supports. Separately bound
`E_rep >= r^2*|theta_N-theta|/2`. Impose the fixed additional support budget
`r*|theta_N-theta| <= 2*Delta` before construction, and bound each planned
radial segment's entire-trace displacement by Delta, using its affine endpoint
error bound. These proposed fixed budgets require approval/review; they are not
new R0/C0 coefficients and cannot be enlarged for a failing request. Per-line
direction, norm, parameter and displacement formulas must be explicit in the
implementation review.

Keep E_rep and the native-reference area enclosure as separately reported
mathematical evidence and necessary representation checks. **Do not add E_rep,
the angle budget, or a whole-trace allowance to the R0 comparison interval.**
The R0 target remains the previously reviewed source analytic reference interval
with only its already-approved local closure allowance. Apply the sealed final
conversion-cell rule once; do not add source and native cell budgets twice.
Freeze that source-based comparison target before construction. A displaced
native radial trace must still satisfy the original R0 window; if it does not,
the case fails even when its representation checks pass. Widening that window
would be a separate, presently unapproved numerical-policy change.

No disk term is claimed to bound the displaced full radial trace. The unchanged
source radius, authored points and source certificate remain separate from the
native plan and its own reference-area interpretation. The native-reference
sector construction proves a simple closure exists for the planned equation
traces, not that their literal endpoint-connector walk is simple. Its certified
area enclosure is not substituted for the fixed source-based R0 target.

### After construction: verify the actual inserted representation

Construct one vertex per endpoint ID at the planned transformed authored doubles,
one intended three-edge wire, one explicit-plane face and one extrusion. Retain
actual inserted edges and later face-owned edge/vertex handles. No healing,
welding, radius averaging, tolerance increase or alternative-geometry retry.

Pass only if the actual inserted curve/plane/pcurve representations can be
inspected and shown to match the frozen plan, including line supports/parameters,
circle center/axes/radius, oriented unwrapped trim and the exact edge/vertex
incidence. Require the supplied vertex doubles unchanged, all expected distinct
IDs still distinct, no extra edge/loop/split/merged boundary, and tolerance <=1e-7
mm at every insertion stage. Missing or changed representation is a rejection,
not permission to fit a new post-hoc plan.

Evaluate both separately:

- A certified mathematical bound for each serialized final curve equation's
  endpoint versus its stored vertex, <=Delta.
- The observed native curve.Value endpoint discrepancy versus that vertex,
  <=Delta. This is empirical native behavior, not established by the first bound.

For the face-owned pcurve traces, verify the same single-loop orientation,
within-cell endpoint portions, exactly matching exterior traces to the planned
native reference class, and no additional traversal/loop. A B-rep-valid result
alone cannot establish these hypotheses. The independent review must approve
this precise reference-class interpretation of the inspected face boundary;
if the binding does not expose enough information, reject with
`native_evidence_incomplete`. Do not describe the native internal face algorithm
as mathematically proved by a certificate about its reported fields.

Extrude along the retained exact frame normal by nominal h in [1,1000]. Verify
the actual vector and face normal so the perpendicular interval is [h,h] in this
restricted domain. Require exactly one valid positive solid; intended circular
side, radial sides and caps; actual inserted-edge Generated history and actual
FirstShape/LastShape; no unexpected split/merged role. The semicircle still
retains the two authored radial boundaries, and any native merging is an honest
unsupported result, not an identity rewrite.

### R0/C0 remain fixed empirical tests

Use the frozen n=3, W from requested transformed endpoint/center coordinates,
and L from the original local endpoint bounding-box diagonal/canonical radius.
Do not substitute full arc extrema or count proof joins. Match the retained
independent oracle's perimeter definition: source radial lengths a0+a1 plus
r*|theta|, evaluated with a certified upper bound. A remains the midpoint of the
fixed source-based analytic comparison interval; H=h after its verified frame
and vector check. Specify directed rounding once for all cases.

Require R0 distance-to-the-fixed-source-area/volume intervals and independent C0
`|V_native_local-A_native_face*H| <= E_V+|H|*E_A` with the unchanged coefficients.
Never add E_rep to the R0 interval or its allowances, and never add cell or
representation allowance to C0. Preserve failing supplemental
controls. Mesh area/volume cannot satisfy any analytic/native-mass condition.
Mass properties, validity, curve.Value and any later export roundtrip are
empirical qualification observations. They are not proofs of OCCT arithmetic.

### Concrete completion / stopping condition for this gate

The adapter is complete only when a predeclared positive matrix including
noncardinal, nonzero-gap and nonquadrantal sectors passes this exact implemented
representation contract, and all predeclared negative controls reject correctly.
Include the final serialized curve fields, pre-native plan and all separately
named mathematical/empirical checks in per-case evidence. Cardinal controls are
necessary but cannot justify broader acceptance. A missing final pcurve, modified
planned support, unresolved interval, budget exhaustion, excess discrepancy,
R0/C0 failure or identity change stops that case with no successful native output.

If ordinary noncardinal positive targets cannot pass without modifying the fixed
plan/budgets or changing the reviewed face interpretation, the integration gate
has failed. Stop for a precise domain/boundary decision; do not spend successive
milestones building more disconnected numerical leaves or advertise broad
success from only the cardinal subset.

## 3. Explicit service end point and protected-file approval

### Request/result boundary

Implement only explicit result-3 `solve_sketch` and Part `replay` for this first
milestone. For a document containing arcs, limit replay to one constrained sector
sketch with zero or one directly dependent positive extrusion and no other
features. Unsupported arc-containing graphs reject before native work. A
solve-only successful solve retains its solved sketch and failed profile
readiness for unsupported forms; it never calls them open chains or solver
failures. Failure/ambiguity supplies no available profile/solid evidence.

For arc-empty schema 3, preserve unchanged legacy line/circle/coincidence geometry
semantics through an explicit internal geometry-only view, after validating the
original schema-3 data. Never serialize, solve, fingerprint or return that view
as schema 2. Existing `classify_profile`/`closed_profile` stay gated as before.
Legacy-document result-3 replay can reuse the existing feature behavior, with the
explicit v3 envelope; existing result 1/2 operations retain byte-identical output,
errors, accepted fields and omission behavior.

The v3 envelope and replay result stamp 3; solved source schema/IDs/direction and
document/input fingerprints remain exact. `curve_loop` appears only after full
pure profile admission, and an available native profile only after native
postflight. Require the strict source/output/dependency/mesh/topology algebra in
new native-free v3 validators. A correct nonce or receipt never proves geometry.
The numeric certificate is internal data and test evidence, not a second saved
radius/sweep authority or an unreviewed additional wire field.

Keep geometry/export-v3, Assembly-v3 and snapshot-sketch3 capabilities absent;
reject their requests before launch/replay. Canonical snapshot remains schema-3
closed. No result-version inference, downgrade, chord approximation or retry.

### Files needing a new explicit edit boundary

All 105 baseline runtime hashes and delivered 0.5.2 are immutable under the
*current* authorization. Full service integration cannot honestly be done while
pretending those runtime files were untouched. Request an explicit additive-
integration exception for these exact existing core seams before implementation:

- `src/mechanical_cad/kernel_ocp.py`: new curve-profile construction/postflight,
  operation registration, profile role and extrusion postflight/provenance.
- `src/mechanical_cad/engine.py`: explicit v3 admission/sector branch, checked
  extrusion consumption, result stamp/output fields; leave v1/v2 paths identical.
- `src/mechanical_cad/sidecar.py`: explicit v3 dispatch and common-failure stamps.
- `src/mechanical_cad/backend_contract.py`: origin-checked implementation marker
  discovery for only completed solve/Part-v3 capabilities, and dispatched v3
  failure stamping. Do not change minimum-capability algebra or existing receipts.

Prefer new pure `sector_profile.py`, interval/sector-certificate modules, a new
`result_policy_v3.py`, and new solve/protocol-v3 modules. Existing
`result_policy.py`, `sketch_service.py`, `sketch_protocol.py`, `profile_region.py`
and `outputs.py` can remain unchanged by explicit v3 dispatch/new adapters;
do not widen their defaults. If a minimal shared-helper extraction is necessary,
name that exact additional file and diff for a boundary revision first.

The canonical/model/expressions/snapshot/arc-geometry/solver/evaluation leaves,
all old add-on modules, current publisher/reader/owner code, and the delivered
archives remain byte-exact. New add-on v3 validators may compose unchanged strict
leaf helpers and byte-exact shared pure policy copies; no wholesale v2-validator
fork and no refactor of protected `_expected_document` without separate approval.
If those helpers cannot support the new contracts cleanly, pause for a bounded
extraction proposal rather than weakening validation.

### No production publication authority

Use one fresh PreparedRequest and its captured selection per integration test.
Recheck selection immediately before launch and consumption, validate same-
process receipt, remove only the receipt field, and run strict v3 validation.
Return detached data. The unchanged GuardedEvidence factory and every live
Part/Rectangle/General/Assembly publisher must reject even a genuine valid v3
response. No accepted draft, CURRENT marker, owner state, migration, journal,
saved envelope, UI controls or capability-driven automatic activation.

Advertise only actual imported, origin-checked `mcad.sketch-arcs/1`,
`mcad.solve-result/3` and `mcad.part-result/3` implementations after their
independent core/client gate. Recognizing those names today is not implementing
them. Public v3-owner admission requires its own later atomic consumer review.

## 4. Predeclared fixtures and evidence

All source fixtures use exact shared IDs unless stated. These are expected
mathematical classifications, not newly run native results.

| Fixture | Pure expectation | Native/service qualification target |
| --- | --- | --- |
| c=0, (5,0)->(0,5), ccw/cw, h=7 | Quarter/major, exact-zero | Positive identity-frame controls, areas 25*pi/4 and 75*pi/4 |
| c=0, (5,0)->(-5,0), both directions | Semicircle, exact center continuation | Positive three-boundary identity/provenance control, area 25*pi/2 |
| r=stored 5.1, cardinal endpoints | Exact-zero | Positive ordinary noninteger radius control |
| (3,4)->(-4,3), r=5 | Exact-zero rotated quadrant | Positive noncardinal native-line representation control |
| (13,29)->(-29,13) | Positive rounded-hypot gap | Required noncardinal/positive-gap positive target |
| (5,0)->(-3,4), either direction | Nonquadrantal exact-zero; 90–270 domain | Required arbitrary-angle positive target |
| (10,0)->(0,10 +/- 2^-31) | Positive cells; own end root inside/outside radial trim respectively | Required small inward/outward-gap targets; all R0/C0 checks still mandatory |
| Previous fixtures, nonzero local c and exact half-component axis-permutation frame | Same exact source tests, recomputed from actual stored values | Required admitted-frame/nonzero-center targets, no assumed exact translation of local offsets |
| r/h=1,1000 and just outside | Inclusive endpoints pass corresponding bound; neighbors reject | Positive boundary controls only if all other gates pass |
| (10,0)->(6,8) | Dot>0, reject both directions | No native construction |
| (10,0)->(0,10+2^-24) | Core may pass; discrepancy rejects | No native construction |
| Same coordinate, different required endpoint ID | Unsupported incidence, even with coincidence | No weld or successful profile |
| Chord, second arc, extra line, circle, branch/hole | Unsupported first-milestone form | No native construction |
| Any core-valid nonzero world origin/arbitrary quaternion | Source may pass | Explicit unsupported native frame |
| Altered final axis/line/trim/ID, full turn, missing pcurve, tolerance over ceiling | Not a source admission issue | Native postflight failure; no output |
| Retained below-Delta supplemental C0 failures | Pure may pass | Native failure remains failure |

Include start/end swaps with authored-direction handling, line storage reversal,
all stable record permutations, seam crossings, negative-root major membership,
near-antipodal and 90/270 dot-sign neighbors, rounding-threshold neighbors,
subnormal differences and aggregate-budget exhaustion. Test the universal
clearance proof independently with exact identities/inequalities, not only
sampled distances. Compare area/angle enclosures to a separately structured
rational/series oracle. Fuzzing/high precision finds bugs but is not the proof.

Required service adversaries: exact legacy bytes, arc-empty schema-3 legacy
coincidence behavior, malformed/boolean versions, v1/v2 rejection before native,
unsupported graph and placement, solve-success/readiness-failure, forged source
IDs/direction/roles and recomputed hashes, v3 rejected by all unchanged publishers,
missing capabilities/receipt/selection mismatch, source budgets and missing
native dependencies. No Blender/native UI tests or GUI claims are needed here.

## 5. Finite implementation sequence and owner decision

One milestone, four auditable gates, with useful end-to-end success as the exit:

1. Freeze and independently accept the incidence preflight. Review this precise
   sector specialization, native plan, proposed fixed representation budgets,
   result/API restriction and runtime edit exception before implementing them.
2. Implement the whole pure sector certificate and independent checker together:
   cells/exits, clearance lemma, angle/area and finite resource controls. Freeze
   for independent mathematical review. This gate does not activate a service.
3. Implement the native representation plan, actual-inserted-geometry verifier,
   single extrusion and provenance as one adapter. Execute the predeclared
   positive/negative matrix against the actual pure certificates, serially.
   Stop on the specific blocker described above, without changing margins.
4. Wire explicit data-only solve/Part result 3, strict client validation and
   cross-version/adversarial tests. Freeze a Git-free exact source archive and
   run full Ruff/format/pytest, serialized native/service gates and independent
   numerical/protocol review. Include a canonical sector plus extrusion example
   and a radius 5->7 edit preserving IDs; report actual solve/readiness/native
   outcomes, including a recoverable failure if the solver leaves the domain.

Every native run has a durable predeclared case list, exact commit/source/runtime
identity, command, start/end, log hash, explicit terminal marker and process exit
receipt. Reap the process before releasing the one native slot. Keep calibration,
holdout, controls and every failed/unknown run. No repeated native launch merely
to turn an inconclusive or negative gate into a claimed pass.

The immediate owner questions are bounded:

1. Approve this complete sector-only source domain and restricted native placement
   / solve+Part-v3 service end point, rather than exact-zero-only or the dormant
   broader chord/Assembly/export plan?
2. Approve the four named existing core-file integration exceptions while all
   canonical/solver/add-on production-owner protections remain intact?
3. Approve independent review of the explicit conversion/representation budgets
   and face-boundary reference-class criterion before native implementation?

Until those decisions and incidence qualification are complete, only this design
exists. No classifier/service/native activation is authorized.

## Source notes

Read AGENTS, README, ARCHITECTURE, ADR 0007, NEXT_SKETCH_ARCS, the arc membership
milestone, arc-profile PROPOSAL/BASELINE/NUMERICAL_POLICY/NUMERICAL_REVIEW,
TRANSVERSE_JOIN_CONTRACT/REVIEW, INCIDENCE_PREFLIGHT_PROPOSAL, and relevant
profile_region/arc_geometry/primitives/sketch_model/engine/outputs/kernel/sidecar/
result-policy/sketch-service/protocol/backend-contract/action/client source.
The retained numerical oracle's source perimeter definition was checked in
`cad_arc_profile_probe/e3d8354/independent_review/evaluate_native_r0.py`.
No production/test files were changed by this design task and no native process
was launched. Concurrent incidence-worker edits are outside this artifact's
ownership and have not been represented as qualified evidence.
