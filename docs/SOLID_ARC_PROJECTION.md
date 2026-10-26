# Solid circular-arc projection (source development)

Use Solid Edge is extended to planar partial circular arcs whose planes are
parallel to the target sketch. This is source development, not a change to the
frozen 1.26 installer. Focused native replay is qualified below; Blender/GUI qualification is pending.

## Persistent identity and geometry

A projection row uses `kind: "arc"`, `faces`, `endpoint_faces`, `target`, and the
existing optional `input` and `reverse` fields. Faces are the unique stable
semantic pair defining one native edge. Endpoint signatures are the sorted,
distinct sets of stable incident faces excluding that pair. Missing, split,
merged, aliased, unstable or equal endpoint signatures are refused. Native
vertex incidence establishes identity; point proximity and mesh indices do not.

Fresh native evidence contains the two endpoints in signature order, circle
center, unit normal, radius and signed partial sweep. Native vertex parameters
identify which already-proven endpoint is at each end of the curve interval.
They determine geometry, not persistent identity. The sweep retains major versus
minor branches and is independent of face traversal orientation. Projection
transforms the normal to the target frame; a reversed frame flips direction.
Explicit `reverse` swaps correspondence and flips direction without swapping the
saved target point IDs or changing which circular branch is represented.

The local target is an ordinary construction arc with independent center, start
and end points and exactly three managed fixed constraints. No source fillet
intent is copied. Existing dependent relations remain authoritative. Solve and
replay replace managed seeds and direction from fresh source evidence. Files and
recovery checkpoints contain raw intent only and cannot restore native authority.

## Compatibility boundary

Normal replay and legacy edge-catalog requests retain their old display records.
Only an edge-catalog request with `options.projection_arcs: true` may receive an
`arc` analytic record alongside a display polyline. The opt-in query and any
canonical arc projection require `mcad.solid-arc-projection/1` at the guarded
backend boundary. The query retains existing replay result versions and does not
introduce arc metadata into ordinary mesh results. An authored `kind: "arc"`
projection explicitly admits matching replay/solve evidence. Older strict readers
reject the new row/opcode instead of reinterpreting it as a line or circle.

Use Solid Edge keeps the existing source chooser and picker. Replace Reference
keeps the exact source and analytic kind, supports explicit endpoint flip, and
retains target IDs and dependent relations. The staged-repair probe and transition
allowlist admit only the repaired arc's managed points and direction. Complete
candidate replay remains necessary for publication.

## Limits and evidence

Only exact circular intervals with two uniquely identifiable native vertices
are admitted. Full circles keep the existing circle path. Oblique projections,
ellipses, splines, degenerate intervals and ambiguous endpoint roles are refused.
This does not assign identity to generated blend faces or broaden arbitrary
imported/boolean topology naming. A filleted outline is eligible only when its
extrusion retains stable authored side-face identity and distinct endpoint faces.
A chord-only circular segment has identical endpoint incident faces and is
explicitly refused, even though its exact major arc is geometrically available.

Focused pure tests currently cover minor/major signed sweeps, parallel reversed
frames, explicit flip, bad evidence and oblique refusal, compound authoring,
strict checkpoint restore, Undo/Redo, managed-arc edit rejection and explicit
replacement. Existing targeted owner/repair tests remain passing. Sixteen focused native tests now cover filleted extrusion arc references,
JSON save/reopen, radius/width edits, exact source volume/validity, endpoint flips,
reversed target normals (including persisted replay after a plane-normal edit),
reversed native edge/face traversal, major sweep with distinct radial walls,
missing/split/merged/aliased endpoint refusal, opt-in versus legacy catalogs,
guarded capability admission, explicit repair retaining a dependent circle and
exact extrusion, and solve-only evidence validation. Eleven existing line/full-
circle projection cases also pass. These tests are in
`tests/integration/test_arc_edge_projection.py`, `test_solid_edge_projection.py`
and `test_circular_edge_projection.py`.

Source-loaded Blender 5.2.2 qualification now includes the registered picker/owner
handoff, local Undo/Redo, suspended draft .blend save and second-process restore,
fresh native validation before Finish, and subsequent radius editing. The smoke
asserts no OCP/slvs imports inside Blender; see
`tests/blender_arc_projection_smoke.py`.

Actual cloud GUI gestures passed source selection, oblique-view arc picking,
Finish, Replace Reference with explicit endpoint flip, native Save As and a fresh
GUI process reopening the exact canonical document. The live owner showed an R2
construction arc with three managed anchors; repair preserved every target ID and
changed CCW to CW. An initial top-down ambiguous pick was described as “coincident cap edges,”
but that was an imprecise interpretation, not established candidate identity.
Subsequent real-hover observation established a near-cap arc plus its adjacent
near-cap line at their tangent endpoint. At the arc midpoint, unchanged occlusion
policy uniquely admits the near cap; hidden/back-cap selection was not proved.
Rotating the original fixture avoided the ambiguous screen region. Screenshots and saved
scratch scenes are retained in the private engineering evidence directory
`arc_projection_20261025`. `scripts/blender_arc_projection_gui.py` only prepares a
fixture and reads state; it does not simulate gestures.

Installed-package and cross-platform behavior remain unqualified. Source-edit
radius/size and identity failure cases are covered by exact native/registered tests,
not claimed as actual GUI edit/refusal workflows. No broad historical suite was run.
