# Sketch relations

The active general Sketch editor now supports explicit Coincident, Parallel,
Perpendicular, Equal, Tangent, Circle-line Tangent, Point on line, Midpoint
Concentric and Symmetry actions in addition to Horizontal, Vertical and fixed points.
See [current capabilities and limits](INTEGRATED_MODELING.md). Shift-select two
entities and use the contextual relation controls (Symmetry uses three selections).
The controls only enable relations supported by the exact selection:

- Coincident: two distinct point identities. Joining endpoints cannot collapse a
  line. Already-connected points do not add a redundant connectivity equation.
- Parallel / Perpendicular: two distinct lines.
- Equal: two line lengths, or two circle radii. Mixed line/circle pairs are not
  meaningful equal relations and are rejected.
- Tangent (arc-line): one arc and one line with exactly one explicitly shared endpoint.
  Either arc endpoint and either clockwise/counterclockwise sweep is supported.
  Merely overlapping points are not silently merged.
- Circle-line Tangent: one circle and one line. Contact is with the infinite
  supporting line and may lie beyond its finite endpoints. Existing geometry and
  constraints seed which valid side the solver uses; this is not arc tangency.
- Point on line: one point and a line not containing that point as an endpoint.
  The point lies on the infinite supporting line, not necessarily the segment.
- Midpoint: the same selection places the point halfway between the endpoints.
- Symmetry: two distinct points and one ordinary or construction straight axis
  line, selected in any order. Neither point may be an endpoint of that axis.
  The points are exact reflections across the infinite axis, at any angle in the
  sketch plane: their midpoint lies on it and their connector is perpendicular.
  The axis may move unless separately constrained. A collapsed axis seed is
  rejected; this relation creates neither mirrored curves nor copied geometry.
- Concentric: two circles with distinct center-point identities. Their radii
  remain independent; use Equal separately to match them.

General curve-curve tangency is not implemented. The contextual position-relation
help explains these supporting-line and identity assumptions before Apply.

Relations are canonical saved sketch records, not Blender mesh modifiers.
Changes use the ordinary asynchronous native SolveSpace path, error display,
local sketch Undo/Redo journal, and suspended-draft persistence. Solver failure
leaves a recoverable draft; it does not certify stale geometry. Select the exact
relation in the inspector to remove it. Failed sketches retain the explicit
"Remove using authored positions" recovery action.

Select a fixed relation to open **Edit fixed coordinates**. Coordinates are in
millimetres in the sketch's own plane. Apply can move connected geometry; Cancel
makes no change. Untouched coordinate values retain their original precision.

Arc profile availability is separate from constraint solving. A successfully
solved sketch does not imply that its particular closed/open curve arrangement
is supported as an extrudable region. Construction curves can be toggled explicitly and remain available to the solver,
while being excluded from solid profile boundaries. Select two lines to set an
angle in degrees, including formulas; select its relation to edit it. Select a
circle or arc to set diameter: the canonical driving value remains radius =
diameter / 2, disclosed in the dialog. Angle annotations display measured degrees with explicit degree symbols and
leaders to the selected lines. Construction geometry displays as cyan dashed
curves, separately from solid profile boundaries.

Read-only [reference dimensions](REFERENCE_DIMENSIONS.md) support line length
and circle/arc radius/diameter without adding solver relations. Reference
point-distance/angle and arbitrary relation reference retargeting remain absent.

Focused checks use the actual pinned slvs backend, independent Blender-side
residual validation, sidecar request/response acceptance, and journal save,
Undo and Redo. GUI interaction remains a separate integration check.

## Explicit symmetry contract

The canonical relation is `Constraint(id, "symmetry", (point_a, point_b, axis_line))`.
It has no dimension value or target. It adds two native equations and no helper
points, using SolveSpace `SYMMETRIC_LINE` with `ptA`, `ptB`, and `entityA` as the
axis. See the [upstream constraint equations](https://github.com/solvespace/solvespace/blob/master/src/constrainteq.cpp).
Independent core and Blender response checks reject either a midpoint-off-axis
or a nonperpendicular connector, including forged successful solve results.
Only point order is interchangeable for exact-duplicate classification; the axis
role is never sorted into the point roles. Stored references and IDs are unchanged.

Existing embedded schemas accept this explicitly named relation without migrating
unrelated records. Older software that does not implement the kind rejects it,
rather than dropping it. Constraint removal, recovery, checkpoints and local
Undo/Redo retain the ordinary sketch transaction contracts.

Focused coverage: `test_sketch_symmetry.py` checks pure contracts and local history;
`test_sketch_symmetry_solver.py` exercises the pinned native solver. The existing
`blender_position_relations_smoke.py` includes selection, Apply, removal and history
for symmetry. Native and Blender execution evidence is recorded separately;
adding a test is not a claim of GUI qualification.

Validation on 2026-10-24: 78 focused pure selection/history/schema tests passed;
31 focused native solver and sidecar/response-contract tests passed using the
shared pinned Linux CPython 3.12/slvs 3.2 runtime. Symmetry cases establish DoF
0 with axis and one point fixed, 2 with only the axis fixed, and 6 with a free
axis and point pair; all accepted cases have residual below 1e-7 mm. Oblique,
vertical, horizontal, reversed-axis, duplicate and conflicting-pin cases are
included. The expanded Blender smoke and interactive symmetry GUI have not yet
been executed; no broad-suite or cross-platform qualification is claimed here.
