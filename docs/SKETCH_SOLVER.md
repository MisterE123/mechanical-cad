# Constrained sketch model and solver boundary

The bounded line/circle sketch backend uses the real SolveSpace solver through the pinned
optional `slvs==3.2` package. Geometry records and parsing remain independent of
Blender, OCP, and the native binding. Loading documents requires no solver import.

## API and persistence

`mechanical_cad.sketch_model` exports immutable records:

- `Point(id, u, v)` and `Line(id, start, end)`; references use stable point IDs.
- `Circle(id, center, radius)` in embedded sketch schema 2; `center` refers to a
  point ID, and `radius` is a positive numeric seed in millimetres, never a formula.
- `Plane(origin=(0,0,0), quaternion=(1,0,0,0), id="workplane")`; quaternion order
  is w/x/y/z and sketch coordinates use its local u/v axes.
- `Constraint(id, kind, refs, value=None, target=None)`; kinds currently supported
  are coincident, horizontal, vertical, distance, fixed, and (in embedded schema 2)
  radius. Radius takes exactly one circle ID. Fixed targets are numeric u/v pairs;
  fixing a circle center fixes its position only. Driving distance/radius values
  can be numbers or formulas in a descriptive definition, but must be numbers at
  the native solver boundary.
- `SketchDefinition(id, points, lines, constraints, plane=Plane(), units="mm",
  *, schema_version=1, circles=())` is the authoritative, expression-preserving
  definition. The new fields are keyword-only; old positional calls are unchanged.
- `Sketch(...)` has the same fields and is strictly numeric solver input.
- `resolve_sketch(definition, project_values)` evaluates dimensions through the
  existing bounded arithmetic evaluator and produces a detached numeric Sketch.
  Resolution errors identify the relevant constraint. It never changes source
  expressions, point/radius seeds, or the owning document.

Both sketch types have strict `from_dict`, `from_json`, `to_dict`, and `to_json`.
Both embedded versions require a stable `plane.id`. Dictionary outputs are detached,
JSON-compatible data. Parsers never mutate caller data. Canonical serialization
sorts records by ID and normalizes numeric sketch values to doubles, preserving
expression strings exactly.

The default remains embedded `schema_version: 1`, whose exact serializer and Part
hashes are unchanged. V1 omits `circles`, even when empty. Embedded schema 2 requires
`circles`, with each record containing exactly `id`, `center`, and `radius`. Plane,
point, line, circle, and constraint IDs share one namespace. Unknown fields and
versions fail closed. Document schema 2 remains the enclosing format; document
schema 1 still requires its existing explicit migration before adding any typed sketch.

`migrate_to_v2(sketch)` or `sketch.migrate_to_v2()` explicitly opts a numeric or
expression-preserving sketch into the new version. It keeps the same record type,
IDs, ordering, plane, source expressions, and seeds, and validates the new limits.
Loading, solving, serializing, or reopening a v1 sketch never migrates it. Repeating
migration on v2 returns that snapshot unchanged. An explicit nested migration
intentionally changes its owning Part hash; accepted assembly sources remain
unchanged until their explicit source-update transaction.

At the document boundary the payload belongs in a typed `Feature.sketch` object
for `sketch_constrained`, never inside scalar `params`. Document schema migration
and existing primitive feature behavior are owned by the document layer.

## Solve transaction

```python
from mechanical_cad.sketch_model import resolve_sketch
from mechanical_cad.sketch_solver import solve

numeric = resolve_sketch(feature.sketch, resolved_project_parameters)
report = solve(numeric, diagnose=True)
if report.success:
    solved = report.sketch
```

`SolveReport` has `status`, `success`, `remaining_dof`, `failed_constraints`,
`sketch`, `max_residual`, and `redundant_constraints`. A failed solve returns the original numeric sketch;
DoF is exposed only on success. The caller commits a successful candidate through
its normal document transaction. Rebuilding a document must not silently rewrite
saved seed positions or replace formulas with literals. Solve reports are
transient build output, not authoritative document/hash fields.

A successful but underconstrained closed profile can be extruded with a visible
DoF warning. `REDUNDANT_OKAY` is also successful geometry, but should produce a UI
redundancy warning. Neither success status alone proves a profile is closed,
non-self-intersecting, or valid for a kernel face. Profile validation is separate.

Before native solving, a conservative guard rejects cyclic active-coordinate
equalities with `solver_dof_indeterminate`. The pinned solver can otherwise return
`OKAY` and zero residual with an incorrect DoF, including a false zero. The guard
preserves the complete authored sketch and reports no current solved geometry or
DoF. It does not replace a cycle by a spanning tree, suggest a particular relation
to delete, or claim that the geometry is infeasible. See the
[bounded guard and minimal reproduction](SOLVER_DOF_GUARD.md).

`drag(sketch, point_id, target)` performs an exact-target trial preserving all
persistent constraints. Successful trials are re-solved without the temporary
pin so structural DoF is reported. Unreachable targets preserve original geometry
and identify the transient pin as `@drag`. This is not nearest-feasible smooth
dragging. The current persistent-constraint cap also applies during that trial;
a sketch already at the cap receives an explicit resource-limit error.

## Analytic circle solve contract

```python
from mechanical_cad.sketch_model import Circle, Constraint, Point, SketchDefinition

sketch = SketchDefinition(
    "shaft-profile",
    (Point("center", 3, 4),),
    (),
    (Constraint("shaft-radius", "radius", ("shaft-circle",), "shaft_radius + clearance"),),
    schema_version=2,
    circles=(Circle("shaft-circle", "center", 7),),
)
```

The source dimension is a radius. The native adapter compiles it through
`slvs.diameter(group, circle, 2 * radius)` but retains the authored constraint and
reports the resolved radius, never the doubled internal value. Its circle seed
is not a driving equation. A free circle has native DoF 3; adding its radius
constraint gives 2, fixing only the center gives 1, and both give 0. Extra points,
even unused by a curve, still contribute real native unknowns/DoF.

Circle entities compile in stable-ID order after the existing point/line families,
so old line-only compilation order remains unchanged. Native radius values come
from each distance entity's parameter, not the circle's empty parameter array.
Output positions and radii are validated before success; invalid, negative,
zero, nonfinite or out-of-domain radii fail atomically and are never repaired with
`abs()`. Independent radius residuals use `abs(solved_radius - target_radius)` in
millimetres and the same `1e-7` threshold. A reported native DoF must be an integer
within the particular candidate's `2 * point_count + circle_count` ceiling.

Different formulas that currently evaluate to identical equations retain their
separate source records. Only their exact current native equation is deduplicated;
a later parameter edit resolves them again and can correctly produce a conflict.
No inference of equal, concentric, tangent or diameter constraints is implemented.

## Defensive boundaries

- 256 KiB UTF-8 per standalone sketch JSON, depth 8, numeric tokens at most 128
  characters, 256 points, 256 lines, and 512 constraints.
- Embedded v2 also permits at most 256 circles, with `lines + circles <= 256`
  and `2 * points + circles <= 512`. These aggregate limits bound active scalar
  unknowns before native execution. They do not add a circle-bounding-box rule:
  center coordinates and radius are validated independently.
- V2 direct dictionaries and typed serialization obey the same compact JSON byte,
  depth, and numeric policy. Cycles reject; shared-container trees are memoized
  while their expanded serialized size is counted. An enclosing document with an
  embedded v2 sketch additionally enforces its 2 MiB/depth-32 tree budget and the
  128-character numeric-token/finite `±1e12` policy across all literal numbers.
  Original wire number spellings are checked by `Document.from_json`/`load_document`;
  direct inputs can only check their canonical spelling. Pretty-printed v2
  document JSON must also fit 2 MiB, so serialization cannot emit a size-invalid
  document. Legacy v1-only document acceptance and hashes remain unchanged.
- Strict duplicate-key rejection at JSON parse time, including nested/escaped
  names. The enclosing document parser must also reject duplicates before
  passing an already parsed object to `SketchDefinition.from_dict`.
- Strict record field sets, required fields, types, exact integer schema version,
  immutable tuples, and reference validation. IDs follow the core 1–128 character
  ASCII pattern. Unknown schema versions, booleans as numbers, NaN/Inf, and hidden
  JSON payloads in numeric values are rejected.
- Coordinates/fixed targets within ±1e6 mm; driving distances/radii and circle
  radius seeds within 1e-6..1e6 mm.
  Unit quaternion checked with absolute tolerance 1e-9. Solved residual acceptance
  is 1e-7 mm for this supported constraint subset. These input bounds do not
  guarantee native face/mesh resolution: extremely thin profiles near the
  1e-6 mm (one-nanometre) minimum can fail region or OCCT tessellation checks.
  Such failures block downstream solids; tolerances are not silently loosened.
- All validation runs before touching native state. The convenience binding owns
  global sketch state, protected by a shared lock and cleared before/finally.
  Unrelated direct `slvs` callers can bypass that lock; keep use behind this API
  and the sidecar boundary. Input limits do not provide a native solve timeout.
- `SketchError` subclasses `CADException` with stable machine-readable codes.
  A missing binding raises `solver_unavailable` only at solve time and explains
  how to install `mechanical-cad[sketch]` into the sidecar environment. Any version
  other than 3.2 raises `solver_version` because its runtime ABI is unqualified.

## Binding quirks and diagnostics

The tested 3.2 Python wheel returns `(info, failed_handles)` when diagnostics are
requested and an `info` dictionary when disabled. Actual info keys are result,
dof, and nbad. Bundled type stubs do not correctly describe both branches.

A zero-length seed for an otherwise feasible positive-length line can return
`INCONSISTENT`; failed constraint IDs are diagnostic candidates, not proof of
impossible user intent or a guaranteed minimal conflict set. Keep the previous
valid model after failure, distinguish degeneracy from proven conflicting
numbers, and never automatically delete user constraints based only on this list.
Diagnostic search can be considerably more expensive than an ordinary solve.

## Verification and remaining scope

The legacy suite retains its line behavior and adds expression, parser,
immutability, malformed-input and resource-limit tests. Native cases cover
an eight-point rectangle with explicit coincident endpoints, horizontal/vertical
constraints, dimensions, 0/2/4 remaining DoF, inconsistent dimensions, successful
and rejected drags, dimension edits, canonical reload/re-solve, arbitrary planes,
and serialized concurrent callers. Record-limit acceptance tests are schema tests,
not large-model native performance claims. `test_sketch_v2.py` locks exact old
constrained Part and accepted assembly hashes, explicit migration, strict version
and reference dispatch, formula intent, direct/wire input budgets and input
immutability. `test_sketch_circle_solver.py` exercises actual 3/2/1/0 DoF, radius
edits and diameter compilation, duplicate/formula divergence, arbitrary workplanes,
reordering, endpoint seeds, concurrent cleanup, hard-target center dragging and
independent rejection of malformed native success/radius/DoF output.

Only the Linux x86-64 CPython 3.12 runtime was qualified during this implementation.
Other platform wheels still need release tests. Arcs, tangency, generalized
smooth dragging, assembly constraints and broad model-size performance are not
implemented by this adapter. The backend circle model/solver does not by itself
establish a delivered general-circle viewport editor or GUI-qualified workflow.

## Dependency licensing and primary sources

- [Official slvs 3.2 package](https://pypi.org/project/slvs/3.2/)
- [Official SolveSpace library/licensing page](https://solvespace.com/library.pl)
- [Official C API](https://github.com/solvespace/solvespace/blob/master/include/slvs.h)
- [Upstream source/license](https://github.com/solvespace/solvespace)

The wheel has an MIT package classifier but includes GPLv3 COPYING text, and
upstream identifies SolveSpace as GPLv3-or-later. Treat the linked solver as
GPL-3.0-or-later, not MIT. Commercial use/charging is permitted under GPL terms;
that does not authorize a proprietary closed-source linked distribution. Preserve
notices and meet corresponding-source obligations when distributing a combined
product. Audit actual bundled components and the source-provision path before
release. No native solver binary is vendored in these source modules.

### Exact duplicate relations and diagnostic limits

The native solver can report `INCONSISTENT` for a mathematically consistent
rectangle when an exact duplicate horizontal, vertical or coincidence relation
is added while saved seeds are still unsolved. Its failed-constraint list may
then name the anchor rather than the repeated relation.

The adapter now classifies **exactly identical current equations** before native
compilation: kind, entity IDs, numeric value and fixed target must match exactly;
point order is immaterial only for symmetric distance/coincidence relations.
Symmetric endpoint order and unique equation compile order are canonicalized in
temporary native records, so adding a lower-ID reversed duplicate cannot translate
an underconstrained sketch by changing solver ordering. Only the duplicate native
equation is omitted. Every original saved
constraint, expression and stable ID stays intact, independent residual checking
still evaluates every relation, and success reports `REDUNDANT_OKAY` with
`redundant_constraints`. This is not a general redundancy or consistency proof.
No tolerance-based, transitive or geometric-equivalence merging is performed.
Equal formulas are compared after evaluation; if their values diverge on a later
edit, they are separately compiled and may correctly conflict.

The UI should treat applying an already-present identical relation as idempotent.
Native failed IDs are **diagnostic candidates, not proven causes** or instructions
to delete a particular dimension/anchor. Other seed-dependent convergence and
algebraic-redundancy limitations remain; failure never publishes a partial solid.

### Workplane construction

The saved quaternion is checked as near-unit within the documented tolerance and
is never rewritten. The kernel normalizes a temporary copy and constructs the
face on the explicit known plane instead of fitting a plane to its wire. This
avoids a reproduced long/thin rotated-profile fitting failure without relaxing
B-rep validity or residual checks.

### Explicit arbitrary-axis symmetry

The current adapter also accepts `symmetry` with exactly two distinct point IDs
followed by one straight line ID. The selected points may not be that line's own
endpoints. Both ordinary and construction axes are supported in any sketch plane.
The direct native `SYMMETRIC_LINE` primitive contributes two equations, with no
auxiliary unknowns: perpendicular connector and equal/opposite signed axis
distances. Independent residuals check both, normalized in millimetres. A
collapsed seed axis is explicitly rejected; a collapsed solved axis cannot pass
residual acceptance. See [selection and persistence contract](SKETCH_RELATIONS.md).
