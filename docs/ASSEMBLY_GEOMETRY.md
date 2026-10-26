# Assembly B-rep geometry adapter

This document describes the bounded native geometry primitives added after the
0.2 baseline. These primitives alone do not establish an assembly-authoring UI,
a complete assembly service, continuous collision detection, or manufacturing
certification. Native shapes stay inside the existing CPython sidecar. No OCP
import belongs in Blender or the pure assembly model/kinematics modules.

## API

All methods are on the existing `mechanical_cad.kernel_ocp.OCPKernel`.

### Independent rigid placement

```python
placed = kernel.transformed(shape, frame, linear_tolerance_mm=1e-6)
```

`frame` exposes `xyz_mm` and `wxyz`, or is a dictionary containing exactly those
two keys. Coordinates are three finite numbers in ±1e6 mm. WXYZ has four finite
numbers, each bounded by 1.00000001, and squared length must differ from one by at
most 1e-9. Booleans and numeric strings are rejected. Translation and rotation
follow `placed_point = R * source_point + xyz_mm`, rotating around the part
coordinate origin, including when the original solid is far from that origin.

An accepted near-unit quaternion is normalized only for the temporary transform.
The source frame and canonical authored values are never modified. The OCCT
transform copies geometry and does not copy mesh caches. Its result must pass
the same single-solid gate as the source. Identity placement also creates an
independent shape. Original geometry and construction records stay unchanged.

Transformed shapes are deliberately not registered with operation history.
Calling `topology()` on a transformed result produces unknown, snapshot-local
face descriptors. This operation does not promise persistent transformed-face
provenance, mates attached to faces, or assembly-scoped face identities.

Malformed parameters and failed transformations raise `KernelError`. The service
must surface that failure and must not reuse a previous transformed display as
current geometry.

### Static pair query

```python
pair = kernel.pair_check(
    a,
    b,
    minimum_required_mm=0.0,
    linear_tolerance_mm=1e-6,
    volume_tolerance_mm3=1e-9,
)
```

Requirements are finite nonnegative numbers up to 1e6 mm. Both tolerances must be
finite positive numbers no greater than one, in their respective mm/mm³ units.
Booleans and strings are rejected. Malformed query parameters raise `KernelError`
before native work. Invalid input geometry and native failures instead return a
structured, JSON-safe incomplete pair result.

Result fields:

- `relation`: `separated`, `contact_or_near`, `interference`,
  `indeterminate_small_overlap`, `indeterminate_kernel_disagreement`, or `unknown`.
- `common_volume_mm3`: actual measured sum of valid common-solid volumes, zero
  for a successful common with no solids, or null if no reliable value exists.
- `minimum_distance_mm`: nonnegative minimum **boundary/surface** distance, or
  null on a failed measurement. This is not signed distance or penetration depth.
- `witness_points_mm`: one pair of finite world-space XYZ points, respectively on
  the first and second boundaries, or null. The pair is a numerical witness;
  there can be many equivalent minima and no stable witness identity is promised.
- `minimum_required_mm`: the checked clearance requirement.
- `clearance_verdict`: `pass_at_pose`, `at_threshold`, `fail_interference`,
  `fail_clearance`, or `indeterminate`.
- `complete`: all native measurements and applicable consistency checks
  succeeded, with no small-positive-overlap ambiguity or diagnostic. This means
  computational completeness, not proof that the measured relationship is safely
  away from a threshold. An `at_threshold` result can be complete.
- `known_interference` and `known_clearance_violation`: separately retain proven
  violations. Consumers must not let an incomplete pair/pose hide known violations
  elsewhere or in the same result.
- `diagnostics`: code/message objects. Native exception text is bounded to 500
  characters. Diagnostics are not permission to substitute zero or stale data.

`pass_at_pose` requires successful measurements, no positive common volume, and
surface distance greater than the requirement plus the linear tolerance.
A gap less than the requirement minus that tolerance is a known clearance
violation. The intervening band is `at_threshold`, never a pass. Face, edge and
vertex contact, and a gap no greater than the tolerance, are `contact_or_near`.
With zero requested clearance, such contact is still `at_threshold`.

A common volume greater than the volume threshold establishes interference.
A positive common volume at or below the threshold remains present in the report
and yields `indeterminate_small_overlap`; it is never rounded to zero. A
separately proven clearance violation can still produce `fail_clearance` for
such an incomplete pair. The thresholds are policy guardrails, not statistically
or mathematically certified error bounds for arbitrary CAD geometry.

A failed distance query does not erase a successfully established overlap.
That result retains `interference`, positive common volume,
`known_interference=true`, and `fail_interference`, with `complete=false` and a
diagnostic. Conversely, a common failure can coexist with a measured distance and
proven clearance violation, while its common volume remains null.

## Surface distance and containment

OCCT whole-solid distance can return zero when one solid is entirely inside
another. Reporting that value as minimum surface distance would be incorrect.
The adapter computes its reported distance on compounds of boundary faces.
For example, a 2 mm cube inside a 10 mm cube, with its near corner at (2,2,2),
has common volume 8 mm³ and minimum surface distance 2 mm. It still fails for
interference. A pin inside the void of a hollow tube can instead have positive
surface distance and zero common volume.

For boundaries separated by more than the linear tolerance, an additional
whole-solid distance check verifies containment/separation consistency against
the common result. Contradictory successful measurements produce
`indeterminate_kernel_disagreement`, preserve the raw measurements for diagnosis,
and do not claim proven interference. This cross-check's whole-solid distance is
never substituted into the surface-distance field. Distance witness coordinates
must be finite, inside the corresponding shape bounds, and mutually consistent
with the measured distance.

## Shared solid validation and numerical handling

Part export and assembly operations reuse `_require_single_solid`; there is no
second permissive assembly validator. It requires:

- A non-null native B-rep passing OCCT's exact validity analyzer.
- Exactly one solid occurrence, either direct or in compound/compsolid wrappers.
  A valid single-solid Boolean wrapper is accepted; loose faces, edges, vertices,
  duplicate occurrences and multiple solids are rejected.
- Every shell closed, finite geometric bounds, finite positive oriented exact
  volume, and finite positive surface area. Reversed or open solids fail.

Assembly calls additionally require every stored face/edge/vertex tolerance to
be finite, nonnegative and no greater than the requested linear tolerance.
World-coordinate magnitude must leave at least a conservative 32-ULP margin
inside the requested linear resolution; otherwise `coordinate_resolution`
prevents a false precise claim. This check is a guardrail, not a full conditioning
analysis of arbitrary spline geometry.

Pair computations use independent copies translated to a shared local origin.
Witnesses are restored to world coordinates. Volume properties use a local
reference point and exact underlying surfaces, with `OnlyClosed=true` and
triangulation disabled. Boolean Common runs non-destructively, serially, without
increasing fuzzy tolerance. Each common solid is validated independently; common
geometry can legitimately contain multiple solid pieces. Their finite positive
volumes are summed and checked against the input volumes for gross inconsistency.

These operations are exact B-rep algorithms within OCCT numerical tolerances,
not symbolic exact arithmetic. Tiny features can remain unresolved, difficult
Booleans can fail or take substantial time, and inputs do not provide a hard CPU
or memory bound. The service's existing worker isolation/timeouts and separate
bounded logical-pair budget remain necessary. A single logical pair invokes
multiple native algorithms. No tessellated-mesh collision surrogate is used.

## Runtime and binding details

`OCPKernel.runtime_versions()` reports actual OCP binding, installed no-VTK
distribution, Python interpreter and adapter versions. It explicitly reports
`occt_runtime: not_exposed_by_binding`, rather than guessing a separate OCCT
runtime build from the wrapper version. Current exercised versions are:

- Adapter `assembly-brep-1`
- `cadquery-ocp-novtk` 8.0.1.1.0
- OCP binding 8.0.1.1
- CPython 3.12.14 on Linux

OCP 8 imports `List_TopoDS_Shape` from `OCP.collections`. Its Common binding does
not expose `HasErrors`, `HasWarnings`, or a report accessor: the adapter checks
`IsDone`, validates resulting geometry and checks measurement consistency; it
cannot claim to have inspected an unavailable warning report. `Bnd_Box.Get()`
returns an unregistered `Bnd_Box::Limits` binding type in this runtime, so bounds
use `CornerMin()` and `CornerMax()`.

Reproducibility also depends on canonical assembly/source hashes, complete pose
coordinates, policy/requirement/tolerance values, evaluator version, and exact
sample lists. Binding those into reports and rejecting stale reports belongs to
the service. This adapter receives native solids only and cannot establish that
they came from the current source revision.

## Verification evidence and limits

`tests/integration/test_assembly_kernel.py` exercises actual OCCT boxes,
cylinders, through-cut solids, independent transformations, arbitrary rotations,
nonzero local origins, near-unit quaternions, near and far placements, cavity
clearance, containment, multiple common pieces, coplanar overlap, face/edge/vertex
contact, analytic volume and distance, numerical threshold bands, malformed
inputs, shared export rejection, tolerance/precision gates, and deliberate native
failure/inconsistency injection. Original B-reps and authored frames are checked
for preservation. The existing kernel and geometry-action suites also exercise
the strengthened shared validator.

These tests do not qualify Windows/macOS, all imported or pathological B-reps,
continuous swept motion, physical fit, stress/strength, or manufacturing safety.
No release archive, previously released source revision or publication is changed
by this adapter work.
