# Explicit automatic Sweep section placement

New Sweep dialogs default to **Center at path start**. This is a visible,
versioned construction rule, not an assertion that inferred geometry is authored
face identity. **Keep authored placement** is always available in the same dialog.
Older Sweeps still use their original section coordinates and are never migrated
when opened or edited without changing that choice.

## Everyday workflow

1. Draw one closed section and a separate solved open planar line/arc path. The
   section may be anywhere and on a different workplane. One filled section with
   holes is supported; multiple disconnected section islands are not.
2. Choose Sweep, select the section and path, and review **Section placement**.
3. **Center at path start** rigidly moves the section's filled-area centroid onto
   the selected path endpoint and rotates its normal onto the initial tangent.
   This is the area centroid including holes, not the bounding-box center, sketch
   origin or a chosen point. An asymmetric section or off-center hole therefore
   moves differently from a bounding-box-centered section.
4. At zero roll, section local +U aligns with the path workplane normal. Positive
   **Section roll** rotates +U toward +V around the initial travel tangent. Roll
   is a literal angle in degrees, bounded to -360 through 360, not an expression.
5. The normal start is the lexicographically smallest endpoint point ID after
   explicitly authored coincidence equivalences. **Start at other end (reverse
   path traversal)** reverses the entire path and uses the other endpoint and its
   inward tangent. This is not merely a section-normal flip. It can change the
   resulting orientation of an asymmetric section.
6. Apply rebuilds the whole canonical candidate. Failed geometry keeps the old
   model. Edit Feature exposes the same placement, roll and traversal choices.
   Source section/path sketches are not moved, rewritten or reidentified.

**Keep authored placement** makes no translation or rotation. As before, the
user is responsible for placing the original section at the path start and normal
to its initial tangent. It also retains the original bounded line-loop path
behavior; automatic placement requires an open path with two endpoints.

## Canonical and process boundary

The optional `sweep_placement` field is accepted only on a `sweep` feature:

```json
{
  "version": 1,
  "mode": "path_start_centroid",
  "reverse": false,
  "roll_degrees": 0
}
```

All four keys are required; unknown keys, modes, versions, non-boolean traversal,
formula roll and nonfinite/out-of-range angles fail closed. Omission means the
original authored placement; no defaults are injected into older documents.
The core freezes this intent and both native-free Blender canonical validators
check it independently. The feature, not a UI scene property or Blender mesh,
is authoritative for replay, save/reopen and export. Native profiles retain their
explicit construction +U direction in process-local metadata, never by fitting
an axis from tessellation or guessing an edge.

The automatic frame is recomputed from current solved geometry on each rebuild.
Changing section shape follows its new area centroid, changing a path follows
its new endpoint/tangent, and changing path endpoint IDs can change the default
traversal. These are the saved logical rule, not a guarantee of physical point
identity. Sweep faces remain evaluation-snapshot-only. No stable face, mesh index,
nearest match, downstream repair or new topological naming claim is introduced.

## Limits and evidence

Paths remain connected, nonbranching planar open line/arc chains. Whole-circle
paths, closed curved paths and 3D splines are unsupported. Tight bends, sharp
corners or oversized sections can fail exact native solid construction. This is
initial placement plus the existing OCCT pipe frame transport, not arbitrary
user-authored twist control along the whole path.

### Creation-time exact boundary preview

Creating a Sweep now uses the existing debounced, guarded feature-preview owner.
After input settles, a cyan boundary outline shows the exact sidecar result for
centroid placement, literal roll, traversal and input selections. The accepted
geometry stays visible and unchanged. The outline is neither selectable topology
nor saved/exportable geometry. Live status at the top of the viewport distinguishes
pending, failed and ready preview; failed or edited input removes the old outline.

Apply always requests fresh exact work for the current fields and uses the existing
atomic publication transaction. It never accepts a cached preview. Cancel, Undo,
source edits, lost context, unit/view-layer changes and changed backend selection
retire the work. Native cleanup retains the shared execution lease until confirmed.
No second process-launch or publication path is introduced.

This increment previews creation only. Edit Feature still exposes all placement
choices but does not preview them. The outline is bounded to 200,000 triangles;
larger or invalid results explain why there is no current preview. A preview is
initial placement plus the same exact sweep operation, not manufacturing approval.
The source-loaded `blender_sweep_preview_smoke.py` checks fresh Apply, native
ready-response retirement, in-flight Cancel/Undo, backend/context/source changes,
recovery and preservation of accepted geometry. GPU appearance, dialog focus and
pointer interaction still require separate GUI qualification.

Focused evidence is in `test_sweep_placement.py`,
`test_sweep_section_geometry.py` and `blender_sweep_placement_smoke.py`.
It covers strict persistence, legacy omission, asymmetric/off-origin/rotated
sections, literal roll, reversed traversal, directed arc-start tangents, holes,
exact volume and cap geometry, conservative naming, operator add/edit/failed
Apply and two-process `.blend` reopen. These source-loaded checks do not establish
interactive GUI usability, installer qualification or other platforms.
