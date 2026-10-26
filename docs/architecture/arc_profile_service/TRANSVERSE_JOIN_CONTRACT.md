# Proposed bounded transverse-join contract

Design only, 2026-10-17. Source read at `b4cdbfeb9afa945a7cc207e15ff71d16b16b6bf1`.
No runtime edits, native execution, service activation, UI or release work.

## Decision requested

Approve, reject, or revise the following *new profile interpretation* before any
implementation. It is narrower than the dormant general profile proposal:

* One authored arc and its one straight chord, or one authored arc and two
  straight radii to its authored center, using exact shared endpoint IDs.
* Canonical radius and positive extrusion height in [1,1000] mm, inclusive;
  all frozen core admission, coordinate, solver, identity and workplane rules
  still apply unchanged.
* Proposed additional first-domain restriction: exact center-relative endpoint
  vectors have dot product <= 0. Thus either directed sweep is between 90 and
  270 degrees. This is a proposed restriction, not an already approved rule.
* Transverse arc/line joins only. Both forms may be semicircular. At a sector
  center, exactly opposite radial rays are explicitly allowed as an ordinary
  straight continuation, with disjoint finite interiors and no tangent reversal.
  The transversality requirement applies to the outer arc/line joins.
* Actual endpoint discrepancy <= 1/10^9 mm is necessary, never sufficient.
* Tiny gaps and within-cell support intersections receive the explicit
  reference-region meaning below. They are not exact equality, snapping, or
  permission to suppress a root.

Do not activate anything from this document. In particular, an approved design
would still need implementation, independent pure review, and separately
approved native qualification against the implemented certificates. All 105
existing runtime Python files remain outside this work's edit scope.

## 1. Authorities and mathematical target

Read the unchanged `arc_geometry(..., require_equal_radii=True)` result first.
Its radius, chord, sweep and admission comparisons remain exactly as frozen.
Store its exact binary64 result and preserve every authored/solved coordinate,
ID and direction. Traversal reversal is a separate temporary flag.

For this proposed profile interpretation only, regard input binary64 values as
exact dyadic numbers. Let c be the authored center, p0/p1 the solved start/end,
v_i = p_i-c computed as an exact difference, S_i = dot(v_i,v_i), and r the exact
value of the frozen binary64 canonical start radius. Define

    q_i = c + r v_i / sqrt(S_i).
    d_i = |q_i-p_i| = |r-sqrt(S_i)|.

The mathematical source arc is the radius-r circle from ray v0 to ray v1 in the
authored direction. Its exact directed angle is theta; it is not declared equal
to the binary64 `sweep_radians`. This explicitly chooses exact endpoint rays as
new derived profile semantics. It does not rewrite core output, recompute the
canonical radius from exact S0, or pretend rounded subtraction/hypot/atan2 is
exact. Exact dyadic vector differences are not rounded translated inputs.

This interpretation needs owner approval. If the owner instead requires the
binary64 core sweep to be an exact mathematical trim authority, this document
must be revised before implementation. Silently switching between those two
arc definitions is prohibited.

Source q_i are mathematical validation values, never replacement solved/native
vertices. In particular, r may differ from sqrt(S0) even when both endpoint
norms agree and the frozen radial residual is zero. No exact-zero-residual gate
is imposed.

Separately certify the difference between theta and the frozen sweep and between
the source arc and intended native parameterization. Choose one unwrapped angle
branch; no comparison modulo a turn may conceal a full-turn change. The intended
rounded trim must have the same direction/branch, differ from the source trim
only in the associated end cells, and pass the conversion rules in section 8.

## 2. Shape and support gates

Use endpoint identity before geometry. No geometric coincidence class supplies
a missing join. Reject different IDs at a needed join, multiple components,
additional boundaries, holes, a full-circle boundary, constraints requiring a
hidden representative, or a line-to-line coincidence alias.

Segment: the sole line has endpoints p0 and p1 with the same IDs as the arc.
Sector: the two sole lines are c--p0 and c--p1 and use the arc center's ID at their
common line endpoint. The center being an arc center alone creates no incidence.
No other role or center is inferred.

Require exact v0 dot v1 <= 0. A sector with zero exact cross product must
certify v0 dot v1 < 0, hence opposite rays and no finite-line overlap.
Neither exact sign uses a length epsilon. The frozen core gate runs first, so
this restriction cannot rescue an arc rejected by the core.

Let Delta = 1/10^9 mm, L = 1/2500000 mm (4e-7), and D = 1/5000000 mm (2e-7).
Require a certified d_i <= Delta for each endpoint. Use exact algebraic
comparison to Delta where possible; otherwise refine bounded intervals. A lower
bound greater than Delta is a definite support rejection. An enclosure still
straddling Delta at the resource limit is numerical ambiguity, never a pass.
Inclusive mathematical equality passes; no ULP expansion is allowed.

Obtain certified nonnegative dyadic upper bounds U_i >= d_i. After the Delta
gate has independently proved d_i <= Delta, define eta_i = min(U_i,Delta).
This remains a certified upper bound and preserves inclusive equality when
d_i=Delta, since no dyadic upper approximation can equal that non-dyadic rational.
If both gaps are proved exactly zero, section 3's exact-join path applies.
Otherwise set eta = max(eta0,eta1) and the common cell radius rho = 16 eta.
Thus 0 < rho <= 1.6e-8 mm, at most L/25. The bound is deterministic at the
smallest successful precision in the schedule 64,128,256 bits, with the stated
exact rational cap applied only after the discrepancy gate has proved it valid. A tiny true gap
must not be rounded down to zero. It is acceptable for an exceptionally tiny or
threshold-touching case to fail the bounded computation.

Cell disks B_i are centered at the exact solved p_i with radius rho. Prove their
closures disjoint, q_i strictly inside, and every root assigned to join i strictly
inside B_i. These are real geometric tests, not assumptions inferred from the
factor 16. A failed strict margin rejects or is ambiguous. Source cells depend on
source discrepancy. They are not enlarged later to cover global transform error.

For each segment support intersection additionally require the exact normalized
crossing-sine lower bound 2/3 from section 4. This leaves margin below the ideal
45-degree minimum imposed by the proposed sweep restriction. Sector outer joins
are exactly normal intersections of circle and radial support.

## 3. What a cell proves, and the exact-zero path

A positive-radius cell must satisfy all of the following:

1. Its incident finite source arc and finite source line each have one connected
   endpoint portion in the cell and exactly one exit from the cell into the
   retained exterior portion. Each exit is transverse to the disk boundary.
2. The full support circle intersects the disk in one short connected circular
   arc, of angle strictly less than pi, containing the source endpoint and the
   assigned support root. This rules out the other side of the circle.
3. The interval from each original trim endpoint to the reference trim endpoint
   lies inside the cell on that same support branch. Check this even when the
   reference trim extends beyond the original finite edge.
4. No foreign boundary enters the closed cell. Two incident exterior exits are
   distinct. No other join cell or center vertex lies in it.
5. All original finite-curve roots have already been counted under section 4.
   Cell membership is never an exemption from root counting.

Disk/support intersections are closed-form line/circle or circle/circle
intersections with exact dyadic centers, exact rational radii and algebraic roots. Exact angular
membership is determined by determinant/dot signs and the selected direction,
not by an angle tolerance. Count exit multiplicity and tangent cases explicitly.

At a join whose source endpoints and intended reference root coincide exactly,
there is no uncertainty to patch. When both d_i are exactly zero, set the source
cell-area allowance to zero and use the exact transverse join proof directly;
do not attempt two-exit tests on a radius-zero disk. Preserve both support roots
and test clearance just as for positive cells. If only one d_i is zero, the
common positive rho gives both joins ordinary cells without changing that exact
join's data. Native parameter/transform errors still have their own later gates.

The center join of an admitted sector is exact and has no incidence cell or gap
allowance. Its finite rays have nonpositive dot product, so their interiors are
disjoint. Exactly antipodal rays have coincident supporting lines but opposite
finite interiors and form a straight continuation; this is explicitly allowed.
Near-antipodal noncollinear rays still pass the exact sign and clearance tests.
No unstable line-line solve is needed because their common center is an exact ID.

## 4. Complete support roots and strict assignment

Every root record contains pair IDs, algebraic root ID, multiplicity, a disjoint
isolating enclosure, original finite-line membership, original finite-arc
membership, reference-trim membership, and assigned join or NONE. Endpoint
membership is inclusive and exact. INSIDE, OUTSIDE, ENDPOINT and UNRESOLVED are
separate states. UNRESOLVED cannot pass. Records are retained even when no
original finite intersection exists.

### Segment

Parameterize the *supporting* line x(t)=p0+t h, h=p1-p0, with original line trim
0 <= t <= 1. Put

    A = h dot h,
    B = 2 h dot (p0-c),
    C = |p0-c|^2-r^2,
    disc = B^2-4 A C.
    t_minus = (-B-sqrt(disc))/(2 A),
    t_plus  = (-B+sqrt(disc))/(2 A).

Require A>0 and disc>0. Keep both roots, with separate IDs MINUS and PLUS; no
clustering, nearest-root deletion, rounded discriminant or length epsilon.
Require x(t_minus) strictly inside B0 and x(t_plus) strictly inside B1 (or exact
equality on the exact-join path). The opposite assignment is not tried to make
a case pass. Verify each root lies outside the other cell, and each cell owns
exactly one root. This uses the authored p0->p1 support parameter; reversal of
boundary traversal never relabels the roots.

The exact crossing-sine condition is

    disc / (4 A r^2) >= 4/9, equivalently 9 disc >= 16 A r^2.

For each root independently, test t in [0,1] and whether its circle direction
lies on the original directed source arc. A root is an original finite crossing
iff BOTH are true. A support root outside either trim remains in the record; it
is not an extra crossing, and it is not erased. Each join may own zero or one
original finite crossing. Both joins owning one is the expected two-edge-loop
case. Any original finite crossing not uniquely owned by its prescribed cell,
multiple distinct roots at one join, or a root shared between cells rejects.

The reference chord is the support segment from x(t_plus) back to x(t_minus)
when the reference arc traverses MINUS to PLUS. Reference arc endpoints are the
two support roots; extend/trim only their inside-cell branch portions. Keep the
original authored direction and unwrapped arc branch. Verify the reference arc
has no additional full turn and all source/reference arc differences lie in
B0 union B1. This is temporary proof geometry only.

### Sector

For radial support i, retain BOTH roots

    c + (r/sqrt(S_i)) v_i = q_i,
    c - (r/sqrt(S_i)) v_i.

The original radial line c+s v_i has 0 <= s <= 1. The positive root is assigned
to its own outer join only and must be in that cell. The negative root has s<0
and is outside that finite line; retain its arc membership, which may be true
on a major arc. It is not a hidden crossing. Test the positive root's original
finite-line and finite-arc membership separately as well.

The two original finite radial lines meet exactly at c and nowhere else,
including the antipodal case of coincident supports with opposite finite rays. The other
radial line must not enter an outer cell. The reference sector uses the unchanged
source arc and radial segments from c to q0/q1. A q_i beyond p_i extends only the
proof-only radial trim inside B_i; a q_i before p_i trims only that portion.

### Consequence

There is no generic zero-root allowance: a join with no original finite crossing
must still have its unique prescribed support root in its cell and a verified
simple reference closure. An absent, tangent, doubled, unresolved, misassigned,
or out-of-cell support root fails. This specifically prevents a second crossing
from disappearing inside the older 4e-7 collar.

## 5. Bounded clearance without an arrangement framework

The original Ljoin/Dclear policy still applies. Use a stronger, algebraic
sufficient test rather than weakening its arclength requirement:

* At each graph join use a **clearance-proxy disk** of radius b = 7L/8 = 3.5e-7 mm
  centered at the solved vertex. These are not incidence cells or repair zones.
* Check each incident source branch's intersection with that disk is one endpoint
  portion with one transverse exit. Prove every such portion is inside its
  original length-L collar. For a line this is immediate. For an arc, the chord
  from q_i is at most b+d_i, and the short-circle-arc bound

      length <= (b+d_i)/sqrt(1-(b+d_i)^2/(4r^2)) < L

  supplies an explicit check. For a sector center the incident curves are lines.
* Exempt a pair of positions only when both lie in the same join's proxy disk.
  Everywhere else certify distance strictly greater than D.

Because these proxy portions are subsets of the original collars, this test is
conservative. It may reject geometry the older collar condition would accept.
No analytic crossing is exempted by this distance test.

Partition each finite boundary at the relevant proxy exits. Each boundary has
at most three subintervals, hence each boundary pair has at most nine rectangular
parameter patches, and the sector has at most 27 patches. Discard only patches
where both intervals are inside the same proxy disk. Compute the exact minimum
candidate set on the closure of every retained patch; checking the closure is
intentionally stricter at the collar boundary.

For line-line patches the finite candidate set consists of endpoints, clamped
orthogonal projections, and any interior intersection. For line-circle patches
it consists of: all endpoint pairs; projection of each arc endpoint onto the
line interval; circle directions parallel/antiparallel to each line endpoint's
center-relative vector when within the arc interval; every support intersection
with both memberships; and the circle directions normal to the line through the
foot of the center on its support, with that foot inside the line interval.
Include degenerate zero-vector candidates by their fixed squared-distance
value r^2. For coincident line supports, test finite interval overlap explicitly;
otherwise endpoint/projection candidates still supply the minimum.
These enumerate boundary and interior stationary points of squared distance.
No sampled curve, mesh, numerical optimizer or arbitrary subdivision proves
clearance. Compare squared distance to exact D^2, retaining dimensions.

Enclose algebraic candidate distances with the finite arithmetic below. Every
lower bound must be strictly greater than D^2. A certified candidate <= D^2 is
unsupported clearance; a threshold not resolved within the bound is ambiguity.
This direct finite enumeration avoids relying on an approximate small-angle
clearance argument. Its completeness needs an independently checked lemma in
the implementation review.

## 6. Reference-region/Jordan and area meaning

The accepted mathematical object is a **reference-region class**, not the claim
that unequal q and p are literally a closed exact boundary.

The reference segment is simple: two distinct support-circle intersections,
the straight chord between them, and exactly one nonfull directed circle arc
form a Jordan boundary. The chord's open interior lies inside the circle and
cannot meet that arc. The reference sector is simple: two distinct radial
segments have no common point except c, their interiors are strictly inside the
circle, and a nonfull circle arc joins their distinct outer ends. The
antipodal sector is included: its two radii form a diameter with no overlapping
finite interiors, and the same Jordan proof applies.

Cell checks prove that source and reference traces agree exactly outside the
closed disjoint B_i, each has the same two ordered exits per cell, and the
reference interior replacement stays in the disk. Thus at least one simple
closure exists. A self-intersecting straight p--q connector is not assumed to be
a valid closure merely because its Green integral is small.

An admissible member of the reference-region class is any consistently oriented
Jordan closure with the same exterior traces and one simple inside-disk arc
between the same two exits in each B_i, without extra loops, repeated traversal,
or another disk-boundary crossing. This is a definition for uncertainty, not
permission to construct such geometry in the model or kernel.

For two such closures, the difference of winding numbers is zero outside the
disks: their differing pieces close entirely inside each disk, and a point
outside a disk has winding zero around any closed curve contained in that disk.
Jordan interiors have indicator winding 0 or 1 after common positive orientation.
Their symmetric difference is therefore contained in the disk union. Consequently

    |area(member)-area(reference)| <= sum_i pi rho^2.

This supplies the missing Jordan argument; simplicity and the same exterior
traces are mandatory hypotheses. The older Egap only bounds its particular
connector integral and is not substituted for this theorem. A multiply wound
closure has no certificate here.

Compute reference area with origin c, avoiding a far-origin cancellation:

    sector:  A_ref = r^2 |theta|/2.
    segment: A_ref = (r^2 |theta_ref| - cross(w0,w1))/2

where w_i = assigned reference root_i-c and the segment formula is evaluated in
the normalized positive traversal order, so cross has the corresponding sign.
For a major arc the sine/cross term is negative. This is the support-root chord
cross product, not the authored p0/p1 cross product unless they are exactly the
same endpoints. The nominal source-curve Green integral is a separately named
quantity if reported; do not label it the region's exact area.

Certify [Rlo,Rhi] for A_ref and E_cell = 2*pi*rho^2 (zero on the exact-join path).
The source-area interval is [Rlo-E_cell_hi, Rhi+E_cell_hi]. Require its lower
bound >= 1e-12 mm^2. Compute signed reference area before normalization, and
reverse temporary traversal if negative. Original coordinates, IDs, start-radius
authority and direction are unchanged. Unresolved winding or area is ambiguity;
a certified nonpositive/unusable area is degeneracy. The sweep restriction makes
ordinary supported reference areas large (the ideal smallest segment is
(pi/4-1/2) r^2), but that fact does not bypass interval tests.

## 7. Fixed pure primitive set and finite work

No native import, generic symbolic algebra system, unbounded root-refinement
loop, generic curve arrangement, or sampling-based certificate is required.
The proposed implementation has only fixed-form dot/cross predicates,
line/circle and circle/disk intersections, angular membership, algebraic square
roots, the clearance candidate list, and a reduced atan/pi area evaluation.

Resource contract:

* **Precision means normalized significand bits, not fractional bits.** Each
  interval endpoint is a directed-rounded dyadic m*2^e with integer |m|<2^p,
  p in {64,128,256}, and a separately stored signed exponent. Remove trailing
  factors of two from m for its canonical encoding; exact zero is explicit.
  Round lower endpoints down and upper endpoints up after every operation.
  Keep e in [-32768,32768]; exponent overflow, underflow beyond that range, or
  an unsafe alignment shift fails closed. In particular, a fixed denominator
  2^256 grid is not a 256-significand-bit interval when magnitude exceeds 1.
  All exponent-induced integer shifts are checked against the exact-integer
  cap before allocation. Exact input dyadics and exact rational thresholds
  are separate from this interval format and may require more than p bits.
* At most 3 boundaries, 3 graph joins, 2 positive-radius incidence cells,
  3 clearance-proxy disks, 6 support-pair root records, 64 total auxiliary
  intersection-root records, 27 clearance patches and 24 candidates per patch.
  A redundant candidate is permitted; exceeding a cap fails closed.
* Exact input dyadics use common denominator 2^1074. With |coordinate| <= 1e6,
  integer numerators have at most 1094 bits; coordinate differences at most
  1095 bits. Basic support quadratic coefficients are below 2200 bits and
  its discriminant below 4400 bits. Do not round these exact predicates.
* Allow at most 65,536 bits in every integer numerator/denominator/intermediate,
  checked before multiplication/shift/allocation; at most 100,000 scalar exact
  or interval operations for the entire profile; 1 MiB serialized certificate.
  Cancellation is not needed to fit an operation that exceeds the bound.
* Algebraic roots use fixed quadratic-radical representations and exact sign
  tests where a single radical suffices; otherwise outward dyadic intervals at
  precision 64,128,256. Maximum 256 refinement/bisection steps per root.
  Fixed formula nesting is at most degree 16; interval arithmetic does not
  manufacture ever-higher-degree expression trees. An implementation must
  audit those bounds per formula rather than invoking unlimited Fraction work.
* Square-root enclosures use exponent-normalized scaled integer square root,
  round each output endpoint to at most p significand bits, and verify its
  squared lower/upper inequalities against the exact radicand. Scale and
  denominator shifts are guarded before allocation. Exact angular-sector
  membership uses signs, without atan.
* For area only, compute atan2 from exact/algebraic cross and dot with exact
  quadrant selection. Reduce a nonnegative ratio by reciprocal to <=1, then
  use two half-angle reductions x/(1+sqrt(1+x^2)), giving x<=1/4. Bound atan(x)
  with the first 128 alternating terms and the explicit next-term remainder.
  Recombine with rigorously enclosed pi. Pi uses Machin's
  16 atan(1/5)-4 atan(1/239), with 128 terms each and signed remainders.
  All evaluation is outward rounded at the selected precision.
* No ordinary libm return value plus guessed ULP padding is a certificate.
  Do not run a fourth precision or increase a limit because a case failed.

The bit and operation ceilings are fail-closed computational limits, not a claim
that all binary64 inputs finish. The first implementation review must demonstrate
ordinary positive completion and worst-case bounded rejection, including tiny
subnormal offsets; it must independently check the finite candidate enumeration
and arithmetic remainder proofs. A cap hit returns numerical ambiguity. The
65,536-bit ceiling is deliberately above the roughly 4,400-bit base discriminant and its fixed-degree sign-test
products; it also leaves room for interval scaling and exact rational constants.
It is an explicit operational bound rather than an assertion that every formula
on every binary64 input fits. All additions use max-bitlength+1 prechecks,
multiplications use summed bitlength prechecks, and shifts use operand length
plus shift count before allocation. No unchecked Fraction multiplication is used.

### Smallest proposed first implementation commit

Subject to separate authorization, implement only an isolated native-free leaf:
exact binary64-to-dyadic decoding, exact polynomial dot/cross/discriminant signs,
checked integer-bit/operation budgets, outward bounded sqrt, and immutable
quadratic support-root records with exact finite-line membership. Do not import
production services, publishers, solver execution, kernel modules, or client
owners. Do not classify or advertise a profile in that commit.

Its independent tests should include ordinary binary64 and subnormal coordinate
differences, exact zero and threshold equality, two disjoint roots, tangent/double
roots, negative discriminants, integer overflow-budget rejection, interval
exhaustion, and exact-reference comparisons. A subnormal difference may require
thousands of bits for an exact polynomial even though the returned interval is
limited to 256 significand bits. Root-result variants are explicit: negative
exact discriminant returns an empty real-root set; zero returns one record with
multiplicity two; positive returns two separately ordered multiplicity-one
records. Exact sign of a+b*sqrt(disc) supplies finite-line membership independently
of interval width, including exact endpoints. Failure to isolate distinct roots
within the output/work bounds is ambiguity, never a merged record. A primitive's
successful tangent classification does not make it an acceptable profile join;
the higher layer rejects the multiplicity-two case.

Subsequent separately reviewed commits may add angular membership, cell/exit and
clearance lemmas, then reference area. This ordering avoids shipping an
uncertified acceptance flag behind a nominally small primitive addition.

## 8. Native obligations, kept separate from the pure theorem

The pure result is necessary evidence, not a promise of native construction.
No native probes are authorized by this design artifact.

Before a future native call, preserve the one vertex per exact endpoint ID at
its explicitly transformed solved binary64 coordinate. Preserve the original
circle center/radius and requested authored-direction trim construction. Never
send the reference support roots, reference chord endpoints, or reference radial
lengths in place of authored/native input. No projection, tolerance escalation,
welding, radius averaging, healing, or retry with altered geometry is permitted.

**Unresolved additional proposal, outside the adopted first-primitive scope:**
a future classifier/native conversion review should consider
r*abs(theta-sweep_core) <= Delta, with both signed angles on the same unwrapped
branch and sweep_core treated as its exact binary64 value. This would bound
endpoint arc-length departure attributable to the frozen sweep mismatch by Delta,
separately from all actual q-to-p gates. It is not an adopted profile decision or
an authorization to implement classifier/native integration. The final conversion
policy must approve this or specify another explicit reviewed bound.

The preflight parameter-conversion certificate must explicitly bind its rounded
unwrapped native parameters to the proposed source arc, including core-sweep
rounding, start-parameter conversion, and seam handling. Before any native call,
compute the source-plane endpoint distances to p_i for both the source arc and
the intended rounded-parameter arc. Each must independently be <= Delta. Use
16 times the maximum certified distance bound, with the exact rational clipping
rule of section 2, as the final local cell radius. This applies to both previously
zero-gap and nonzero-gap source cases. Recheck all root/exit/disjoint/clearance
conditions and require changed trim pieces entirely inside these final cells.
Recompute the area allowance and freeze the certificate before native construction;
never enlarge a cell retrospectively to rescue an observed native failure.

Global frame/axis/radius conversion is different. Its entire-curve and
area-integral effects need separate certified enclosures computed from the actual
intended representation. A source disk-area allowance cannot absorb a rotated,
shifted, distorted, or differently parameterized arc along its full length.
Support for a workplane remains conditional on that finite conversion certificate;
absence of one is an honest unsupported/ambiguous native preflight, not evidence
that the unchanged core workplane is invalid. There is no assumption that an
accepted near-unit quaternion is exactly normalized in binary64 arithmetic.

Future native postflight must independently establish all of:

1. Actual inserted wire/face edge and vertex handles, exact endpoint-ID incidence,
   unchanged supplied coordinate doubles, no collapsed required vertices, and
   no split/merged/substituted boundary or face role.
2. Actual inserted curve and face-plane/pcurve representations, circle/line kinds,
   canonical radius, oriented unwrapped trims, length and parameter endpoints.
   A pre-constructor record is insufficient. Full-turn substitution or unintended
   span fails. Missing inspectable final representation fails.
3. For each actual final arc endpoint, separately bound the discrepancy of the
   serialized mathematical curve equation to the stored vertex and the observed
   native curve.Value result to that vertex. Both must be <= Delta; preserve
   their separate numbers. Never use the easier equation bound as a bound on
   native evaluation. Native evaluation remains observed numerical evidence.
4. Relevant stored vertex/edge tolerances <= 1e-7 mm after every insertion stage.
   This is a ceiling, not a root-merging or equality distance.
5. One valid simple intended planar face and exactly one valid positive solid;
   correct edge types, trims, cap/side provenance, no foreign loops or missing
   branches. B-rep validity alone is insufficient.
6. A separately certified actual perpendicular positive-height interval [Hlo,Hhi],
   with [1,1000] nominal feature-height support and all frame/vector arithmetic
   accounted for. A reported scalar height is not a certificate.
7. An analytic comparison-area interval that combines source reference-class
   uncertainty with separately proved conversion/insertion representation area
   effects. To use a disk-area term for an actual final face, establish the same
   simple-Jordan/exterior-agreement hypotheses in the actual face plane; otherwise
   compute a separate global integral/region bound or reject. A Green integral
   of unclosed native edges alone does not establish a face-area interval.
8. Predicted volume interval from the checked positive area and perpendicular
   height intervals, native local-reference positive face area/volume, and the
   unchanged R0 and C0 comparisons below.

These obligations deliberately leave implementation/qualification work before
native activation. They do not introduce a generic certificate search: a first
adapter must implement a reviewed finite representation/conversion path for
these 2/3-edge forms or reject that placement. This document does not claim a
mathematical error theorem for OCCT or all accepted workplanes.

### Unchanged empirical comparisons

Retain frozen R0 quantities and definitions: u=2^-53; n authored boundary count;
W=max(1 mm, absolute transformed requested endpoint/center coordinates);
L_R0=max(1 mm, local endpoint bounding-box diagonal, canonical radii);
P analytic perimeter; A analytic interval midpoint; H positive perpendicular
height as defined by the frozen comparison policy. Do not substitute full arc
extrema for endpoint bounds or enlarge n with conceptual joins.

    E_A = 128 u n L_R0^2 + 16 u W P
    E_V = H E_A + 128 u n L_R0^2 H + 16 u W A
    C0: |V_native_local-A_native_face H| <= E_V+|H|E_A

R0 compares distance to the independently certified analytic area/volume
intervals with these fixed allowances. Certified interval evaluation of uncertain
H/A/P must be specified before native implementation, without new coefficients
or per-case margin fitting. No cell-gap width is added to C0. Both comparisons
remain empirical engineering gates, independently necessary after all pure and
structural checks. Passing the proposed Delta gate does not excuse a C0 failure.

## 9. Stages, deterministic outcomes and codes

Do not turn a failed profile check into a failed solve or a successful open
profile. A solve-only report can retain successful solved data and failed
readiness. No stage below creates mesh/solid evidence on failure.

Proposed diagnostic tags below are new design tags, not permission to extend an
existing wire error allowlist. An implementation proposal must map them explicitly.
Evaluate in the following fixed order, then stable boundary/root-ID order:

| Stage | Definite rejection | Unresolved/resource result |
| --- | --- | --- |
| CORE | unchanged frozen core error | unchanged core behavior |
| GRAPH/FORM | unsupported_profile_form; unsupported_profile_coincidence | invalid input remains input failure |
| SUPPORT | unsupported_profile_scale; unsupported_profile_sweep; unsupported_profile_nontransverse | numerically_ambiguous_profile |
| DISCREPANCY | unsupported_endpoint_discrepancy | numerically_ambiguous_profile |
| ROOTS | unsupported_profile_contact (multiplicity/assignment/extra finite root) | numerically_ambiguous_profile |
| CELLS | unsupported_endpoint_incidence | numerically_ambiguous_profile |
| CLEARANCE | unsupported_profile_clearance | numerically_ambiguous_profile |
| AREA | degenerate_profile | numerically_ambiguous_profile |
| NATIVE_PREFLIGHT | unsupported_native_parameterization / unsupported_native_frame | numerically_ambiguous_profile |
| NATIVE_BUILD | native construction failure, preserving cause | unknown completion is not success |
| NATIVE_POSTFLIGHT | native_profile_mismatch / native_tolerance_exceeded / native_mass_inconsistent | native_evidence_incomplete |

A pure certificate includes source bytes/hash, unchanged core output, exact form,
chosen target semantics, precise constants, ordered traversal, support/auxiliary
root records, source finite membership, assigned cells, exit/order/clearance
certificates, reference-area and cell-area intervals, resource counters and stage.
It is data for independent validation, not a new canonical geometry authority.

## 10. Concrete acceptance/rejection examples and required tests

These are mathematical source expectations, not newly executed native results.
All examples have c=(0,0), height 1 mm unless specified, and exact shared IDs.

1. **Exact quarter segment/sector:** p0=(10,0), p1=(0,10), ccw. Frozen r=10;
   d0=d1=0. Segment roots t=0 and 1 are retained and independently bound to both
   joins. Positive areas are 25*pi-50 and 25*pi. Exact-zero source path applies;
   there is no required numerical gap. Native conversion still needs its checks.
2. **Major forms:** same points, cw. Exact sweep magnitude 3*pi/2. Areas are
   75*pi+50 (segment) and 75*pi (sector), with positive traversal normalized
   separately. For sectors, negative support-ray roots can lie on the major arc
   but remain outside their finite radial lines; preserve those root records.
3. **Unavoidable hypot rounding:** p0=(13,29), p1=(-29,13), ccw. Exact S0=S1=1010;
   frozen r is the binary64 hypot result. d=|r-sqrt(1010)| is nonzero but far below
   Delta. Exact vector dot is zero. Both segment and sector are legitimate pure
   candidates; no exact-circle incidence assumption or residual-zero rejection.
4. **Small outward end discrepancy:** p0=(10,0), p1=(0,10+2^-31), ccw. The actual
   end discrepancy is exactly 2^-31 mm, about 4.6566e-10. Sector's positive end
   root q1=(0,10) lies inside the original radial line, so it is a finite contact
   close to the declared endpoint; the proof-only line is shortened within B1.
   The segment keeps t_minus=0 and t_plus<1, separately assigned. Test the latter
   root's exact source-arc membership instead of assuming the line result means
   a finite crossing. Pure success never predicts native C0 success.
5. **Small inward end discrepancy:** p1=(0,10-2^-31), other data as above.
   Sector's positive end root is outside the finite radial line. The join has no
   original finite line/arc crossing but a unique assigned support root in B1;
   reference-only extension supplies the simple closure. Segment's second root
   lies beyond t=1 and remains recorded. No original trim is changed in native
   input. These are explicit zero-finite-root semantics.
6. **Too-large but core-accepted gap:** p1=(0,10+2^-24). Its discrepancy is about
   5.9605e-8, within the core 1e-7 residual but above Delta. Reject at DISCREPANCY;
   no cell, native probe, or enlarged allowance makes it supported.
7. **Small gap but wrong sweep domain:** p0=(10,0), p1=(6,8), ccw. Radius residual
   is zero but exact dot=60>0. Reject at SUPPORT (about 53 degrees). The same
   endpoint rays in cw select about 307 degrees and reject as well.
8. **Semicircle distinction:** p0=(10,0), p1=(-10,0). Both segment and sector are
   eligible; outer arc/line joins are transverse. The sector center is the
   explicit straight-continuation case, with opposite rays and disjoint finite
   interiors. Each radial support has a second circle root at the other outer
   join, outside that finite radial segment; retain it rather than claiming a
   foreign finite branch or erasing the support root.
9. **Distinct IDs at equal coordinates:** a chord endpoint at (10,0) with a
   different point ID is a GRAPH failure, regardless of zero geometric distance.
10. **Two roots hidden in one join:** inject/construct a support case where both
    roots are in B0, a double root, or overlapping isolating intervals cannot be
    resolved. ROOTS rejects or returns ambiguity. The second root is never
    collapsed into one tolerated contact. Outer form/sweep gates may reject the
    ordinary geometric construction earlier; a root-helper adversarial test is
    still mandatory to prove it cannot be suppressed internally.
11. **Tiny outward/inward threshold neighbors:** test actual algebraic d below
    and above rational 1/10^9, plus binary64 inputs adjacent to a nominal decimal
    1e-9 displacement. At the primitive comparator level, test exact rational
    equality and an unresolved enclosure as separate synthetic inputs. Do not
    pretend a binary64 radial displacement can equal non-dyadic 1/10^9 exactly.
    The nominal input spelling is not the discrepancy. Certified <= passes
    this gate only; uncertainty rejects.
12. **Far-transform gate:** a local d below Delta does not pass a placement whose
    actual transformed final equation or native endpoint evaluation exceeds
    Delta. The previously recorded far-origin controls near 1.0014424644e-9 mm
    remain native rejections; local radial residual cannot replace either check.
13. **Native negative controls stay negative:** preserve the existing supplemental
    zero-origin controls below Delta that fail frozen C0. They must remain native
    failures even if the new pure cells/area intervals pass.

Also require permutation, reversal, both authored directions, 90/270 exact
boundaries and their dot-sign neighbors, near-antipodal sectors, centers near
coordinate limits, threshold cells/root exits, every support-root finite-membership
combination, tangent/support multiplicity rejection, no-transform versus parameter
versus global-transform error attribution, midpoint/interval provenance, and
explicit bounded-work exhaustion. Fuzzing or high-precision approximations can
find bugs; they do not replace the stated exact/interval proofs.

## Sources and scope receipt

Read `AGENTS.md`, `docs/architecture/arc_profile_service/PROPOSAL.md`,
`NUMERICAL_POLICY.md`, `NUMERICAL_REVIEW.md`,
`docs/audits/arc_profile_numerics_e3d8354.md`, and the frozen
`src/mechanical_cad/arc_geometry.py` at the source commit above.

This artifact proposes a bounded replacement for the unresolved literal-endpoint
contact sentence. It neither adopts the former general mixed-loop support claims
nor upgrades finite empirical native measurements into a continuous-domain proof.
