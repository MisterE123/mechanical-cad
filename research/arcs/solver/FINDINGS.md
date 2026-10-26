# Circular-arc contract findings

Planning-only spike against source `1a27e74a8f30aeb3fadac8edec935bcf12e3c304`
and its installed `slvs==3.2`, Linux/CPython 3.12. No production changes,
installation, GUI work, commits, or publication.

## Recommendation

Use `Arc(id, center, start, end, direction)` with required `direction` exactly
`ccw` or `cw`. The three references identify existing sketch `Point` records;
all three references must be distinct. They may be shared with other curves.
Use the existing plane-local U/V basis: center (0,0), start (1,0), end
(0,1) selects +90 degrees CCW or -270 degrees CW.
Store neither an independent radius scalar nor a sweep-angle seed. Radius,
minor/major classification, and sweep come from solved points. Full circles
remain the existing `Circle` family. Never silently convert, merge, or rename.

This recommendation is an engineering contract, not implemented schema/UI.

For vectors `a = start-center` and `b = end-center`, calculate
`principal = atan2(cross(a,b), dot(a,b))`. CCW sweep is `principal mod 2π`;
CW sweep is `-((-principal) mod 2π)`. This gives a directed sweep strictly
between zero and a full turn once the degeneracy gates below pass. For equal
radii, endpoints and direction uniquely choose the minor, semicircular, or
major locus. `abs(sweep) < π` is minor; `> π` is major. The semicircle is valid;
do not reject all collinear center/start/end arrangements.

## Verified native contract

Runtime inspection and execution confirm these signatures (the installed stub
uses different parameter names, so use positional calls):

- `add_arc(grouph, normal, center, start, end, workplane)` returns type `80004`.
  Its `point` array contains center/start/end handles; its `param` array is all
  zero, and it has no distance entity. Read point parameters, then derive radius.
- `diameter(grouph, arc, 2 * radius)` works for an arc. Keep the canonical
  `radius` constraint, value/expression, ID, and reported units unchanged.
- `solve_sketch(2, True)` returns `(info, failed_handles)`, with actual info keys
  `result`, `dof`, `nbad`; the shipped `.pyi` is not the complete runtime contract.
- Compile CCW with canonical start/end; compile CW with the two temporary native
  endpoint arguments swapped. Keep the plane normal unchanged and preserve the
  canonical endpoint references. Returned handles verify the mapping. SolveSpace
  direction semantics are documented as CCW start-to-end; this probe does not
  sample native curve geometry or test an OCCT adapter.

A native arc imposes equality of its two center-to-endpoint distances. A free
arc therefore has five DoF, compared with six for its three free points without
the arc. Do not add a second saved equal-radius equation. Unequal initial radii
are solvable numeric seeds: the tested 5/8 mm seeds solved to 6.543126164 mm on
both sides, moving all three points. Source seeds need not already satisfy
driving equations; solved output must pass an independent equal-radius residual.

One line sharing the arc's start uses the exact same native point handle. Two
arcs sharing one endpoint also work (five points, two implicit equations,
eight DoF). Geometry with equal coordinates but different IDs is not identity.
Do not infer coincidence from proximity or use an arc center as a profile edge.

## Radius-edit evidence

The matrix covers authored +90°, -90°, +180°, -180°, +270°, and -270°, including
reversed native endpoint order for CW. All initially have radius 5 mm.

| Fixed points | Driving radius | Result | DoF |
|---|---:|---|---:|
| Center only | 5 or 7 mm | OK; tested directed sweep retained | 2 |
| Center and start | 5 mm | REDUNDANT_OKAY | 1 |
| Center and start | 7 mm | INCONSISTENT | unavailable |
| Center, start, end | 5 mm | REDUNDANT_OKAY | 0 |
| Center, start, end | 7 mm | INCONSISTENT | unavailable |

The endpoint constraints here are existing fixed-point relations, not tangent
or angle constraints. Center plus one fixed endpoint geometrically fixes the
radius, so a changed target is genuinely impossible. On failure ignore the
native numeric DoF and preserve the input, as the current adapter does.

Without fixing the center, radius alone leaves four DoF: changing 5→7 mm moved
the center and changed a 90° sweep to 74.230086737°. A radius edit is not a
promise to keep position or sweep. Do not add hidden position/angle constraints.

For a shared-endpoint sector, fixing the center and adding two radial lines
(center→start horizontal, center→end vertical) plus one radius driver produced
exactly zero DoF. The four authored ±90°/±270° variants all changed 5→7 mm,
retaining their sweep and the same point handles across lines and arc.

Two complementary arcs sharing center and both endpoint IDs generate the same
intrinsic radius-equality equation twice. Both 90°+270° and 180°+180° disks
returned REDUNDANT_OKAY: five DoF free, four with radius, two with center+radius.
Radius editing also succeeded from tested unequal-radius seeds. All eight cases
had `nbad=0` and no failed authored constraint handles. This redundancy is not a
user-authored removable relation; existing authored-equation deduplication will
not see it. Report intrinsic redundancy honestly without inventing an ID or
silently deleting either arc. Region acceptance remains separately untested.

For fixed endpoints (-3,0)/(3,0), radius 4 mm has two solutions. Center seeds
(0,+4)/(0,-4) respectively solved to `(0, ±sqrt(7))`, retaining the tested minor
97.1808° / major 262.8192° branch. Radius 2 mm failed, correctly, because it is
smaller than half the chord. At target radius 3 mm, native success yielded
center offsets ±0.000169792822 mm and angles 179.993514° / 180.006486°, despite
radius residual only about 4.8e-9 mm. Small radius residual does not imply
well-conditioned center position near this singularity.

Starting exactly at the semicircle and increasing that fixed-chord radius to
5 mm failed; perturbations ±1e-10 mm also failed. Valid branches exist, but the
native solver does not reliably leave that singular seed. Do not describe every
native failure as mathematical impossibility or silently invent a center side.

## Degeneracy and branch policy

Verified native success accepts distinct endpoint IDs at identical coordinates,
an explicit endpoint-coincidence relation, sweeps as small as 1e-12 radians,
and nearly full sweeps. A collinear same-ray 3/5 mm seed collapsed its endpoints
and still returned success. Center=start produced failure; all-zero input failed.
Using one native handle as both endpoints produced REDUNDANT_OKAY and an
unhelpful DoF, not a safe full-circle representation.

Recommended bounded acceptance gates, to be finalized with profile/kernel tests:

1. Before native work: bounded finite coordinates, three distinct point IDs,
   nonzero center-to-endpoint distances, and no intended full-circle arc.
   Source expressions remain only in existing driving constraints.
2. After native success: validate both radii within the existing 1e-6–1e6 mm
   domain; independently check equal radii, every authored relation, finite
   coordinates, and integer DoF within `2*points + circles`.
3. Reject coincident or effectively coincident endpoints, zero-length arcs,
   and almost-full arcs. Proposed initial guards are chord length at least
   1e-6 mm and `1e-6 <= abs(sweep) <= 2π-1e-6` radians. These exact guard values
   are policy proposals, not qualified kernel tolerances. Sweep must use the
   same pure helper in solve validation, preview, profile, and export.
4. Antipodal endpoints are valid semicircles. A collinearity/cross-product test
   alone must not choose the major branch or reject the arc. Same-ray endpoints
   with unequal seed radii may solve to a collapsed arc and must fail output
   validation. Never snap solved geometry to a semicircle or repair with abs().
5. Preserve failure atomically. Native OK does not bypass these gates or imply
   a usable closed region. Keep the recoverable draft and explicit diagnosis.

The existing 1e-7 mm absolute residual limit is a compatibility baseline, not a
complete new arc accuracy policy: at radius 1e-6 mm that limit is a large relative
error. Small-scale exact-radius edits passed at radii 1e-6, 1e-3, 1, 1e3, 5e5 mm,
but adversarial relative-tolerance and kernel-boundary testing remains required.

Direction is not a native inequality and minor/major is not locked. No branch
flips occurred in this matrix; arbitrary constraint graphs are unqualified.
For the bounded radius-edit operation, an unexpected sweep jump across the
zero/full-turn seam should fail closed. A proposed deterministic guard is to
reject `abs(abs(new_sweep)-abs(seed_sweep)) > π` and request an explicit reseed
or edit review. This is an operation policy that needs regression coverage,
not a saved equation. Blanket rejection of every minor/major change would
incorrectly reject legitimate continuous motion through a semicircle.

## Compatibility and integration boundaries

- Add arcs through an explicitly opted-in new embedded capability/version.
  Freeze existing v1/v2 parse/serialize/default/hash behavior; the released v2
  parser currently requires exactly its existing fields and has no arcs.
- Keep positional constructors intact with a keyword-only family field. Preserve
  all old IDs, source expressions, point seeds, plane values, and existing circle
  radii. Expressions resolve into detached numeric constraints as today.
- Share the existing entity-ID namespace. Count arcs in the 256-curve aggregate;
  arcs add no scalar beyond their existing points. Do not subtract an assumed
  equation count to manufacture DoF; return actual validated native DoF.
- Add an explicit native-equation resource budget for the new capability.
  A conservative pre-dedup upper bound is `2*(fixed + coincident) + horizontal +
  vertical + distance + radius + arcs`: fixed/coincident each contribute two
  local-coordinate equations; every arc contributes one intrinsic equation,
  even when another arc makes it redundant. Existing 512 authored constraints
  can already imply 1024 equations, and 256 shared-point arcs can add 256 more
  without many new scalars. A proposed new-version ceiling is 1024 equations
  pending stress qualification. Keep old-version acceptance unchanged, and
  reject explicitly rather than clipping constraints. Native limits/performance
  at these caps were not stress-tested in this spike.
- Append sorted arc compilation after current points/lines/circles. Retain
  existing deterministic constraint ordering and exact-equation deduplication.
  Preserve the global lock and clear native state before/after each solve.
- Every rebuild starts from canonical seeds, never the last solved cache.
  An explicit accepted edit may update canonical seeds through its transaction;
  ordinary resolution/replay must not do so. No random branch perturbation.
- Pure schema, expression resolution, solver residuals, drag-ID collision checks,
  strict request/response evidence, and profile boundary dispatch all need an arc
  audit. Current `_residual` indexes radius targets only in circles.
- This is not profile, extrusion, topology, UI, save/reopen, or release evidence.
  The next slice must separately establish those boundaries and old-data tests.

## Reproduction and sources

From the repository root, follow [the portable commands](../README.md).
`reference/evidence.json` retains the original 89 subprocess-isolated cases,
native handles and outputs, source hashes, and native-binary SHA-256. All 65
explicit checks passed. The original complete repeat was byte-identical; this
establishes same-build repeatability for these cases only. A fresh run writes to
an explicit output path rather than modifying the tracked reference evidence.

Primary sources inspected:

- Installed `slvs/solvespace.pyi`, exported functions and runtime signatures;
  `slvs-3.2.dist-info/METADATA` identifies package version 3.2.
- [SolveSpace reference: Arc of a Circle and Distance / Diameter](https://solvespace.com/ref.pl):
  center/endpoints/normal, workplane-only arc, CCW direction, diameter constraint.
- [SolveSpace v3.2 entity.cpp](https://raw.githubusercontent.com/solvespace/solvespace/v3.2/src/entity.cpp),
  `CircleGetRadiusExpr`, `ArcGetAngles`, `GenerateEquations`: arc radius comes
  from center/start distance; endpoint radius equality is intrinsic; the source
  suppresses that equation for an explicit endpoint-coincidence relation and
  treats equal endpoint angles as a full turn. This is not our proposed bounded
  zero/full-turn policy.
- [SolveSpace v3.2 public header](https://raw.githubusercontent.com/solvespace/solvespace/v3.2/include/slvs.h)
  and [official C demo](https://raw.githubusercontent.com/solvespace/solvespace/v3.2/exposed/CDemo.c)
  confirm the arc entity and center/start/end handle convention.
