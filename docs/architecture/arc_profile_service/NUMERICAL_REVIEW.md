# Bounded kernel measurements and remaining endpoint-incidence decision

Status: **isolated numerical evidence; production profile/service activation is
still blocked**. Runtime source tested: `e3d83544510aa07b99dc638665c91b91b1e6bce7`.
All 105 runtime Python files match the proposal baseline. No implementation,
capability advertisement, production owner, release artifact or UI changed.

This report supplements [the proposal](PROPOSAL.md) and [candidate numerical
policy](NUMERICAL_POLICY.md). The exact [independent review](../../audits/arc_profile_numerics_e3d8354.md)
retains its bounded disposition and all control failures. It does not replace their unresolved proof/review
obligations with native observations. Fixed contact/collar rules are conservative
software support limits, not physical design tolerances.

## Result and qualification scope

Three serialized isolated CPython/OCP processes completed and were collected with
exit 0 and explicit terminal markers:

| Gate | Retained cases | Ordinary positive targets | Purpose |
| --- | ---: | ---: | --- |
| Calibration | 205 | 128 | Initial scale, transform, direction and boundary measurements |
| Disjoint holdout | 48 | 40 | Unseen radii/heights, nonzero centers, new frames and normalized winding |
| Rounded-hypot supplement | 20 | 8 | Unavoidable canonical-radius rounding and fixed discrepancy-threshold controls |
| Total | 273 | 176 | Every case, including rejected/failed controls, retained |

All 176 ordinary positive targets passed the predeclared native structural checks,
unchanged-coordinate/identity checks, the 1e-7 mm stored vertex/edge tolerance
ceiling, the fixed empirical mass comparisons R0, and native face/volume
consistency C0. R0 was frozen before calibration outcomes were inspected. C0 adds
no fitted coefficient and was frozen before independent holdout mass inspection.
The original calibration, holdout and supplemental evidence remain separate.

The full 273-case set also retains 32 core rejections, two native arc-constructor
rejections and six thin-profile nonpositive-mass controls. These are not successful
geometry. Some other raw native successes fail the area floor or later proposed
comparison gates. Process completion does not make every input a supported profile.

The measured runtime was Linux x86_64, CPython 3.12.14,
`cadquery-ocp-novtk==8.0.1.1.0`, with `OCP.__version__ == 8.0.1.1`. The binding does
not expose the underlying OCCT runtime version. No Blender GUI was involved.

### What the positive matrix actually covers

- Quarter and 270-degree sectors and arc/chord segments, both authored directions
  and temporary traversal reversal. The holdout explicitly normalizes positive
  winding before native construction.
- Selected radii 1, 2, 5, 7, 10, 25, sqrt(1010), 100, 250, 750 and 1000 mm;
  selected positive heights from 1 through 1000 mm. This is a finite fixture set,
  not proof of every value in a continuous interval.
- Identity, axis, several non-axis and accepted near-unit workplanes; zero,
  modest and near ±1e6 mm origins.
- Local centers (0,0), (17,-29) and (100000,-200000), with exactly perpendicular
  dyadic endpoint offsets, including (13,29) whose rounded canonical radius is
  not the exact square root of the endpoint squared norm.
- Actual inserted-edge lineage, endpoint identity, stored tolerances, analytic
  circle kind/radius/trim/length, B-rep validity and single-solid construction.

Arbitrary sweeps, arbitrary many-edge mixed loops, arc/arc tangencies or lenses,
all transforms, nonlinear solver outcomes, other platforms and continuous-domain
robustness are not established by this matrix.

## Fixed empirical kernel comparisons

The exact frozen definitions are retained in `FROZEN_R0.json` and
`FROZEN_CONSISTENCY_C0.json`. Let u=2^-53, n be authored boundary count, W the
maximum absolute transformed endpoint/center coordinate with a 1 mm floor, L the
maximum local boundary endpoint bounding-box diagonal/canonical radius with a
1 mm floor, P analytic perimeter, A the independent analytic interval midpoint
and H positive perpendicular height. Full arc extrema are not substituted for
endpoint bounds in this frozen definition.

    E_A = 128*u*n*L^2 + 16*u*W*P                    (mm²)
    E_V = H*E_A + 128*u*n*L^2*H + 16*u*W*A          (mm³)

R0 compares distance from the native local-reference mass to its independent
analytic reference interval against the corresponding E. Endpoint-gap and
parameter-conversion allowances belong to the analytic interval, not a per-case
increase in these empirical constants.

C0 separately requires:

    |V_native_local - A_native_face*H| <= E_V + |H|*E_A

C0 is the triangle-inequality combination of the R0 allowances, with no added
endpoint-gap area allowance. A broad interval around an imperfect join must not
conceal native inconsistency between face area and prism volume. A future
production comparison needs an explicitly bounded actual perpendicular-height
interval and inserted-curve postflight; a stored reported height double is not a
universal certificate.

**These are empirically qualified engineering comparisons, not proved error
bounds for OCCT's internal algorithms.** Their operation-count/sensitivity form
and coefficients were fixed in advance, not fitted or widened for individual
failures. The ordinary holdout's largest area error used 4.686% of R0, largest
local-volume error used 1.818%, and largest C0 residual used 1.466%.

## What was mathematically certified

The independent reviewer used exact `Fraction` arithmetic and a bounded Machin
alternating-series enclosure for pi to certify the nominal areas of the exact
perpendicular fixtures. Rotated arc/chord fixtures use canonical radius squared
for the circular term and the actual dyadic endpoint cross product for the chord;
these must not be silently equated when `hypot` rounds the radius.

Separate exact comparisons covered the existing normalized-quaternion coordinate
conversion. For those finite examples they prove bounds on the arithmetic result
relative to the exact normalized input quaternion, before native axis conversion.
They do not prove an all-input transform bound.

A further bounded rational Taylor audit used the recorded native circle
center/axes/radius/trim and stored endpoint doubles to enclose the described
analytic endpoint. This certifies the serialized equations, not the ownership or
internal execution of the native curve. In particular, a pre-constructor circle
record alone does not prove that the final inserted edge retains an identical
curve representation. Actual inserted-curve metadata and native evaluation checks
remain separate postflight requirements.

The pure mathematical bounds, exact fixture comparisons, empirical native checks
and unimplemented general classifier are distinct evidence categories. None may
be presented as another.

## Boundary findings that change the next design

### Shared graph endpoints do not imply exact curve endpoint equality

With center (0,0), start (10,0) and end (0,10.00000005), the core radial budget
passes. The canonical circle ends at (0,10), while a radial line starts at the
solved point (0,10.00000005). Their contact is inside that line rather than exactly
at its declared endpoint. Even a perfectly perpendicular integer-vector fixture
can have a nonzero circle/vertex discrepancy because canonical `hypot` is rounded.

Thus literal exact-contact wording is incomplete. Requiring accidental exact-zero
residual would wrongly reject ordinary solved data and is not an acceptable fix.
The existing 4e-7 mm clearance collar is not permission to ignore these contacts.

### Large accepted core residuals are not qualified native joins

Two negative-residual far-origin calibration controls rejected native edge
construction, while altered placements in holdout constructed successfully. Two
positive near-1e-7 mm far-origin controls exceeded even the independently enclosed
Green-plus-endpoint-gap area interval plus R0, and failed C0. Placement sensitivity
is retained honestly; no tolerance repair or retry was used.

### A stricter endpoint discrepancy limit is necessary, not sufficient

A candidate future profile limit of **1e-9 mm actual endpoint discrepancy** is
plausible as a conservative support restriction, separate from the unchanged core
radial budget and OCCT's 1e-7 mm stored tolerance ceiling. It is not a mathematical
kernel guarantee or a change to canonical arc admission.

The fixed supplemental threshold controls distinguish neighboring values without
an expanded epsilon. At zero origin, the inward neighbor measured
9.9999830638e-10 mm while the rounded nominal threshold measured
1.0000000827e-9 mm. At the arbitrary far-origin placement all six controls measured
1.0014424644e-9 mm, even when the local radial residual alone was below 1e-9.
Local radial residual cannot stand in for transformed curve/vertex discrepancy.

Only two of the twelve controls satisfy that hypothetical measured limit. All six
zero-origin controls nevertheless fail C0, including controls just below it.
Therefore the discrepancy ceiling must remain only a necessary gate; independent
native consistency and validity checks must still reject unsuitable cases.

### Clearance is deliberately restrictive

For two straight incident rays, the proposed Ljoin=4e-7 mm and Dclear=2e-7 mm
require an acute opening greater than 30 degrees for a strict positive clearance
margin. An ordinary minor arc/chord segment consequently needs roughly more than
60 degrees of sweep near its joins; actual curved clearance still needs checking.
The policy excludes sufficiently acute/slender geometry rather than silently
snapping it. Native success alone cannot override that support restriction.

At radius 1e-6 mm, quarter sectors and segments can pass raw native checks while
having certified areas about 7.854e-13 and 2.854e-13 mm², below Amin=1e-12 mm².
They are not supported profiles merely because the kernel returns a shape.

## Recommendation and remaining activation blocker

Retain R0 and C0 unchanged as candidate empirical postflight criteria. Concentrate
the next implementation design on an explicitly bounded engineering-scale range
of radius and positive extrusion height **1–1000 mm**, with the existing authored
coordinate/workplane limits. These are proposed support limits, not a claim that
all members of that interval have been qualified. Keep the stricter candidate
actual-discrepancy limit of 1e-9 mm, plus all independent validity/consistency gates;
allow honest recoverable rejection inside those outer bounds.

The next **pure design** should address transverse sector/arc-chord joins first.
A possible separately reviewed endpoint-incidence certificate would require:

1. One exact shared point ID and a cell radius derived from certified actual
   endpoint/parameter/transform discrepancy, substantially below the clearance
   collar; no fixed collar-sized forgiveness.
2. Disjoint join cells, exactly one exit from each incident one-sided branch, no
   foreign branch, and separately isolated finite-curve roots.
3. At most one uniquely assigned incidence root per join. A bounded zero-root gap
   has explicit semantics; a second root is never merged or hidden. Two declared
   joins in a two-edge loop remain separate.
4. No point projection, coordinate rewrite, identity welding, radius averaging or
   native tolerance increase.
5. A separately proved area-variation bound for any admitted within-cell closure.
   The current Egap proves only the stated straight-connector integral. A sum of
   cell-disk areas is justified only after proving simple Jordan closures that
   agree outside the cells, without multiple winding.

This is a proposed tolerant-incidence interpretation and therefore a visible
contract revision, not an implementation detail authorized by native success.
Do not begin production profile/service code until its exact rule and bounded
predicate implementation are independently reviewed. Tangent joins, arc/arc lens
cases and wider mixed-profile claims need their own corresponding proofs/tests.
The broad activation blocker is therefore **not closed** by this measurement
milestone. The ordinary native construction and fixed empirical comparison
questions have useful bounded evidence; pure incidence semantics remain open.

## Evidence preservation

The durable evidence set is `cad_arc_profile_probe/e3d8354` in the engineering
workspace. It contains all per-case logs/JSON, exact fixture manifests, scripts,
three process-exit receipts, runtime/library hashes, independent pure/native-data
reviews, and `OWNER_GATE_RECONCILIATION.json`. The owner independently verified all
273 case hashes, all 105 runtime source hashes and the delivered 0.5.2 archive SHA.
A sealed whole-evidence archive/manifest is recorded alongside this report's
handoff receipt; release artifacts remain unchanged.
