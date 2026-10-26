# Candidate numerical policy for analytic curve profiles

Status: **proposed, with native comparison envelopes still an activation blocker**.
This document fixes candidate support limits for review; it is not a claim that
all accepted core arcs already produce qualified OCCT faces. See [the slice
proposal](PROPOSAL.md) and its frozen source baseline. The subsequent
[bounded measurement review](NUMERICAL_REVIEW.md) records fixed empirical R0/C0
comparisons and an additional unresolved endpoint-incidence decision; it does not
authorize production activation or silently revise this proposed pure policy.
The subsequent [transverse-join review](TRANSVERSE_JOIN_REVIEW.md) explicitly
adopts a narrower provisional reference-region interpretation for the first
one-arc closed forms. Its complete root ledger and conditional cell-area theorem
replace literal exact-endpoint-contact assumptions only for that proposed slice.
The classifier, native conversion and service paths remain unimplemented.

## 1. Four distinct budgets

| Quantity | Candidate value | Meaning |
| --- | --- | --- |
| Core arc geometry | Unchanged ADR 0007 | Inclusive comparisons on computed doubles; no expanded epsilon |
| Contact ambiguity band, τ | 1e-7 mm | Conservative profile support, never a snap/weld distance |
| Native vertex/edge ceiling, Tnative | 1e-7 mm | Maximum stored tolerance after construction, subject to qualification |
| Usable curved area floor, Amin | 1e-12 mm² | Minimum certified positive area |
| Nonjoin clearance, Dclear | 2τ = 2e-7 mm | Strictly greater separation required outside declared join collars |
| Declared join collar, Ljoin | 4τ = 4e-7 mm | Arc-length distance on each incident boundary from its endpoint |

The frozen core domain remains: coordinates within ±1e6 mm; both endpoint radii
within [1e-6, 1e6] mm; chord ≥1e-6 mm; sweep distance from zero/full turn ≥1e-8 rad;
radial residual ≤`min(1e-7 mm, 1e-8 * start_radius)`. The residual's relative/absolute
transition is radius 10 mm. Later profile/kernel rejection cannot relax these
limits, average radii or alter a solved point. Bounds and their `nextafter`
neighbors are explicit test inputs.

The contact band does not determine equality of IDs or algebraic intersections.
Exact contacts, certified separation and an uncertainty band are different
outcomes. Never insert a length epsilon directly into a squared or fourth-power
discriminant. Use dimensionally appropriate distance/interval evidence.

## 2. Certified arithmetic prerequisite and work limits

Treat accepted binary64 coordinates as exact dyadic inputs. Use exact polynomial
sign predicates where practical; use outward-rounded intervals with proved
remainder/root-isolation bounds for algebraic and transcendental calculations.
The exact input predicate must not silently become a predicate on rounded,
translated coordinates.

The proposed numerical work ceiling is **256-bit interval significand precision
and 256 refinement/series steps per primitive**. Exhaustion produces
`numerically_ambiguous_profile`, never an unbounded refinement loop or a looser
acceptance margin. Retain the 256-total-curve cap: at most 32,640 unordered boundary
pairs. Bound intermediate exact-arithmetic size from the accepted binary64 input
and polynomial degree, and test the worst case before enabling the primitive.
This last implementation bound must be stated in code and reviewed, not left as
an unlimited arbitrary-integer computation.

These are computational limits, not geometric tolerances. Ordinary `math.sin`,
`cos`, `atan2` or `sqrt` plus a guessed number of ULPs is not a certified interval.
Adding `nextafter` around an unproved libm error is also insufficient. Exact
polynomial signs, interval operations, series remainder bounds, branch selection
and resource exhaustion require independent review and high-precision or exact
reference tests. No new native import is allowed in this pure policy.

## 3. Intersections, uncertainty and local slivers

Classify every analytic pair globally before making any endpoint exemption.
Retain both roots where they exist, isolate them separately, and determine their
finite line/arc membership. Cocircular interval overlap and seam wrap require
explicit handling. A second root cannot disappear into an endpoint tolerance.

Only a declared common endpoint can be an allowed contact. At that endpoint,
certify one-sided orientation: ordinary corners and smooth continuation are
allowed; overlap, tangent reversal/cusp and uncertain orientation reject. A
closed two-edge loop may declare both endpoints in common.

For closed mixed profiles, additionally apply this conservative local support
restriction:

1. A join collar has arc length Ljoin on each incident curve, measured from the
   exact declared endpoint. It is a test domain, not model geometry.
2. Exempt from clearance only pairs of positions that are **both** within the
   collars of the **same** declared endpoint.
3. Outside those paired collars, certify separation **strictly greater than
   Dclear**. Nonadjacent pairs have no exemption. Two-edge loops may use one
   exemption at each of their two declared joins.
4. The global intersection test still applies inside a collar. A second crossing,
   contact or overlap is never excused by proximity to the legitimate endpoint.
5. If a distance enclosure touches/straddles the clearance threshold and cannot
   resolve it within the work bound, return `numerically_ambiguous_profile`.
   A certified violation is a supported-domain rejection, not a solver failure.

Dclear keeps two separate 1e-7 mm tolerance neighborhoods from overlapping away
from a join. Ljoin is less than half the 1e-6 mm minimum boundary length/chord,
so the two endpoint collars cannot hide an entire minimum-sized boundary. This
rule intentionally excludes sufficiently acute, narrow or near-touching profiles,
even when their total area is large. It is a bounded first-slice support policy,
not a general theorem of OCCT robustness. It needs threshold-neighbor and local
thin-appendage tests before acceptance.

Open chains retain global contact and ambiguity tests. They have no area, closed-
region sliver or native-solid claim; this slice does not construct an open native
wire merely to establish editable-sketch success.

## 4. Exact-circle Green integrals and endpoint gaps

Choose one deterministic nearby origin o, such as the first solved boundary
vertex, and use it for the whole loop. Translate only inside arithmetic; retain
all original coordinates and identities.

For an oriented line from p0 to p1:

    Gline = 1/2 * cross(p0 - o, p1 - o)

For an arc with original center c, canonical-start radius r, start parameter a
and signed traversal sweep δ, let b = a + δ and C = c - o:

    Garc = 1/2 * [r*Cx*(sin(b) - sin(a))
                 + r*Cy*(cos(a) - cos(b)) + r*r*δ]

Reversing the boundary walk negates its integral without changing r, the authored
arc, or its endpoint roles. Evaluate these expressions with certified intervals;
for cancellation-prone expressions use an equivalent bounded stable form/series.
Do not assume the familiar endpoint polygon plus `r²*(δ-sin δ)/2` expression is
exact when the permitted radial residual makes the solved endpoints off-circle.

The exact analytic circle has endpoints q0/q1, while the incident solved vertices
are p0/p1. For each endpoint incidence, enclose the actual discrepancy d=|q-p|.
The q values are mathematical curve evaluations for validation, **not projected
replacement points**. Do not substitute the maximum radial allowance for the
actual discrepancy when a tighter enclosure is available.

The conceptual segment between q and p contributes:

    J = 1/2 * cross(q - o, p - o)
      = 1/2 * cross(q - p, p - o)
    |J| <= 1/2 * d * |p - o|

If the sum of exact curve integrals is enclosed by [Glo,Ghi] and

    Egap = 1/2 * sum_incidents(d * |p - o|) <= Ehi,

then use the area enclosure:

    Iarea = [Glo - Ehi, Ghi + Ehi]        (mm²)

It encloses closure through the exact solved vertices and translates with the
chosen origin. Conceptual segments are never inserted into a model or native
wire. This does not bound arbitrary native healing, which is prohibited, nor
does it by itself establish the numerical accuracy of OCCT mass properties.

Native parameter conversion has its own bound: when exact parameter expressions
are rounded for the native call, enclose the resulting endpoint/integral changes.
Do not silently equate a rounded native interval with the requested sweep or use
parameter conversion to relax zero/full-turn admission.

### Area and winding decision

After all contact and local-clearance checks:

- If `Iarea.lower >= Amin`, accept positive winding.
- If `Iarea.upper <= -Amin`, reverse temporary traversal and negate the interval.
- Otherwise, reject. Use `degenerate_profile` when the interval certifies unusable
  area; use `numerically_ambiguous_profile` when it straddles a decision boundary.

The accepted positive interval [Alo,Ahi] must have Alo ≥1e-12 mm². Area and winding
cannot be accepted when endpoint or arithmetic uncertainty consumes their margin.

## 5. Native postflight and the unresolved comparison envelopes

Construct one native vertex per exact endpoint ID at its explicitly transformed
solved coordinate. Verify those supplied coordinate doubles after wire/face
insertion; retain the actual inserted edge/vertex handles and intended incidence.
Every relevant stored vertex and edge tolerance must be ≤Tnative. Do not increase
tolerance, project points, weld different IDs or call a healing operation to make
a case pass. Native coordinate changes, collapsed required vertices, unintended
circle span, full-circle substitution and excessive tolerances reject.

The proposed 1e-7 mm ceiling is an activation gate. Earlier isolated probes do not
qualify it over the entire core domain, especially transformed far-origin and
maximum residual cases.

Let [Alo,Ahi] be the accepted analytic area interval. Enclose the actual extrusion
height perpendicular to the authoritative plane, including frame/vector arithmetic,
as positive [Hlo,Hhi]. The predicted volume is:

    Ivolume = [Alo*Hlo, Ahi*Hhi]         (mm³)

Postflight requires one valid solid, positive native area/volume, the intended
analytic edge types/trims/provenance, native face area consistent with Iarea,
native volume consistent with Ivolume, and consistency between native volume and
checked face area times perpendicular height. Mesh measurements cannot satisfy
these conditions.

**Unresolved, blocking:** a defensible, explicit native mass-property error
allowance has not been established for the complete proposed domain. Do not
invent a universal absolute/relative epsilon from the existing small probe set.
Before enabling the kernel/service path, independently review and freeze the
native area/volume comparison formulas, numerical bounds and supported subdomain.
They cannot be fitted or widened per failing request. Kernel failure can remain
stricter than pure core admission; it must be an honest, recoverable failure.

## 6. Bounded qualification to resolve the blocker

Run a new isolated probe, serially and with immutable per-case evidence, without
changing production sources or advertising a capability. Initial measurement may
use independently reviewed isolated reference oracles for the bounded fixtures;
a higher-precision approximate result must not be labeled a certified enclosure.
After the pure policy is implemented and reviewed, rerun the authoritative native
gate against its actual certified intervals before service activation. Record
for every case:

- requested/stored endpoint coordinates and vertex identity before/after insertion;
- vertex/edge tolerances before/after wire and face construction;
- actual curve-to-vertex discrepancies, circle radius, trim interval and arc length;
- face area against the certified analytic interval;
- local-reference native volume against Ivolume and face-area-times-height;
- global-reference existing stats versus local-reference calculations;
- complete success/failure reason, fixture bytes, source/runtime hashes and native
  version, without treating expected rejection as successful geometry.

Required parameter coverage:

- radii 1e-6, 10, ordinary engineering sizes and 1e6 mm;
- chord/sweep/residual boundaries and `nextafter` neighbors;
- zero and largest accepted positive/negative radial discrepancy;
- minor/major/semicircle/seam-crossing, both authored directions and reversed walk;
- identity, axis-rotated, arbitrary and near-unit accepted workplanes;
- zero and near ±1e6 mm origins; minimum/ordinary/maximum positive extrusion height;
- sectors, arc/chord segments, two-arc disks/lenses, rounded boundaries;
- clearance/collar threshold neighbors and thin appendages on large-area loops.

The independent review must decide whether the proposed native ceiling and fixed
comparison envelope can be qualified, or whether a narrower explicit supported
subdomain is required. If not, keep curved kernel/service activation disabled.
A measurement matrix is evidence for a bounded contract, never a proof about
arbitrary CAD kernels, platforms or unconstrained nonlinear solves.
