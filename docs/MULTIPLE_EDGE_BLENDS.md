# Explicit multiple-edge Fillet and Chamfer

In the viewport Fillet or Chamfer picker, click one edge for the existing single-edge
workflow. Shift-click instead to start an explicit set on one input body. Further
clicks toggle edges, orange lines retain the selected set, Enter opens the size
preview/dialog, and Esc discards the uncommitted selection. Up to 64 edges share
one Radius or Distance. F switches to the existing single-edge two-face fallback
and discards the pending set.

Edit Feature retains the complete set and size expression. Choose Reselect to
review the saved input body and replace the set using Shift-click and Enter.
Cancel keeps the old set and other pending editor values. Switching to All edges
or One edge is an explicit change of modeling intent. Preview and Apply use the
same candidate construction; failed native blends never publish a partial part.

## Identity and failure contract

The optional `edge_pairs` field records 1–64 distinct pairs of stable semantic
face IDs. Both each pair and the set are canonically sorted. It cannot coexist
with legacy `edge_faces`. Every pair must resolve against retained source
provenance to exactly one shared native edge, and pairs may not resolve to the
same native edge. All selections are resolved before any edge is added to the
native builder. A missing, split, ambiguous, nonadjacent or duplicate member
rejects the entire feature and blocks downstream dependents.

The old omitted-selection all-edge behavior and single `edge_faces` serialization
are unchanged. Old readers reject the new explicit field rather than dropping it.
No mesh index, geometry hash, nearest-edge recovery, or automatic selection
replacement is used. Kernel tangent propagation remains the existing blend
behavior; this does not introduce a general chain-selection tool.

Typed v2/v3 replay names a generated surface only when native Generated(selected
edge) proves exactly one output face, with no competing face, edge or vertex
claim. Unnamed input faces also participate in collision rejection. Split,
merged, tangent-chain-shared, corner and unknown generated histories stay
snapshot-only. Legacy v1 remains unchanged.

A singleton selection (legacy `edge_faces` or one `edge_pairs` member) owns the
existing `blend.surface` role. For two or more selections, each proven surface
owns `blend.surface.<SHA-256 of canonical JSON face pair>`. The digest encodes
source identity, not geometry or a native index. Reordering selections cannot
exchange surfaces; adding/removing another member while remaining in multiple
mode does not rename a retained pair. Removing its own pair removes its
reference, rather than rebinding it to another bevel. Switching between single
and multiple modes may require explicit downstream reference repair.

The visible assumption is “the surface made by this feature at this named face
pair.” Radius/distance and upstream dimension edits follow that construction
only while the unique native lineage survives. Edit Feature changes selection
intent. Proven planar chamfers may support associative sketches; curved fillets
are not planar supports. Supported line/full-circle boundaries still require
unique adjacency and exact endpoint identity for projected references. This is
not a general fillet-chain naming or automatic reference-repair guarantee.

## Verification

Focused native tests cover two opposite edges for Fillet and Chamfer, exact
volume/validity, upstream size edits, deterministic serialization, strict v2/v3
transport, malformed/partly invalid selection rejection, blocked dependents,
and preservation of legacy selected-surface behavior. The generated-face extension
passed a focused 13-test native batch: v1/v2/v3 two-edge geometry and source
Generated correspondence, v2/v3 client validation, planar chamfer support and
exact boundary projection across width/size edits and serialization, forged
role/pair/count rejection, singleton identity and removal failure. Eight pure
tests cover deterministic pair naming and missing/split/merged/competing claims.
These counts describe the bounded extension check, not a full-suite release.
The earlier selection-workflow Blender smoke covers
native authoring, editing, real native picker evidence with retained selection,
cancellation, invalid size/selection refusal and separate-process save/replay.
These headless checks do not establish interactive GPU usability, Undo/Redo,
ZIP-install qualification or Windows support for this change.
