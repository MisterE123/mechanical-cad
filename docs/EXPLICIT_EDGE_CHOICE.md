# Explicit overlapping-edge choice (source development)

Use Solid Edge retains its one-click path for a unique supported visible edge.
When multiple independently proven selectable edges overlap within the existing
screen-distance tolerance, clicking opens **Choose Edge** instead of guessing.
Click a row (or press its number) to preview, then click **Apply** or press Enter.
There is no default selection. The opening click cannot choose or apply a row.
Cancel/Esc leaves both the authored draft and canonical model unchanged.

Compact primary rows identify the source label and analytic curve kind. A
secondary line keeps start/end cap and straight/curved side context visible.
When friendly labels collide, the secondary line expands to the exact source
and face IDs instead of hiding the distinction. Unknown face suffixes remain
visible, and long labels wrap without truncation. The panel sizes to its text
within 336–480 pixels rather than occupying a fixed wide column. This compact
presentation has pure layout coverage and a source-loaded GUI check: both
compact rows fit, mouse selection previews the matching edge, mouse Apply
authors the arc, and mouse Cancel after line preview leaves draft/model
unchanged. Separate compact screenshots and receipts are preserved alongside
the original wide-panel evidence.
The selected edge uses the existing depth-tested highlight. Faces remain the
identity; screen distance, list ordering, and preview geometry never establish
persistent topology identity. The existing center-ray foreground occlusion test
is unchanged: this is not hidden-edge selection.

The list is bounded to six candidates. Overflow asks the user to zoom/orbit;
unsupported or non-unique provenance never becomes a selectable row. Labels wrap
without truncation. A viewport too small to show the complete list refuses with
an enlargement instruction. Navigation cancels the open list rather than carrying
choices into a changed view. This is a source-development interaction, not a
change to the frozen 1.27 archive.

## Ownership and evidence

The existing registered picker owns a one-shot choice object, with immutable
serialized copies of the exact catalog rows and source IDs. No new RNA operator
property, global token lookup, persistent schema, or recovery field is added.
The active sketch owner must still own that exact picker. A copied choice, another
picker/owner, a retired choice, or a replaced catalog token/evidence cannot use it.

Selection and Apply each revalidate the guarded catalog receipt against the
current backend; compare the complete catalog/replay; and rebind each source to
the unchanged disposable review mesh. Existing owner checks bind draft revision,
stored draft bytes, canonical document, window, screen, area, scene, view layer,
mode, and source snapshot. The chooser additionally freezes view projection and
region size. Captured display membership, visibility, and mesh datablock identity
are frozen for review and legacy displayed-body paths alike. Cheap current checks
permanently retire a choice on observed loss; full display geometry is still
compared during selection/Apply. Apply consumes its authority before forwarding the explicitly chosen
raw edge to the existing independently validating authoring sink. No nearest-
geometry resolver, canonical geometry, or topology naming behavior changes.

Save/load/unregister close the existing review/picker lifecycle and retire the
choice and overlay. Only a successfully chosen raw reference enters the normal
sketch draft and recovery path, where fresh validation remains mandatory.
Poll/draw do not capture full transactions or serialize the authoring journal.
The overlay reads its bounded frozen labels and cheap context currency only.

## Evidence boundaries

`tests/unit/test_projection_edge_choice.py` exercises frozen identities, explicit
selection, release gating, copy/owner/generation rejection, one-shot consumption,
all supported curve categories, unsupported endpoints, duplicate identities and
overflow. `test_solid_projection_owner.py` additionally tests controller preview,
no default Enter, exact Apply handoff, and stale scene/view/catalog/replay/display
binding refusal alongside the existing authoring invariants.

`tests/blender_projection_edge_choice_smoke.py` passed under registered Blender
5.2.2 with real guarded catalog evidence and explicit success marker. Its injected
cap candidates establish ownership/authoring/lifecycle behavior only, not native
ray eligibility or hidden-edge selection.

Actual source-loaded GUI observation establishes a near-cap arc plus adjacent
near-cap line at their tangent endpoint as the admitted overlap. At the arc
midpoint the unchanged occlusion policy uniquely admits the near-cap arc. Real
pointer clicks opened the bounded list; mouse selection previewed the arc and
Apply authored its exact reference. After local Undo, the number shortcut selected
the line and Enter authored its distinct exact reference. Preview left raw draft
bytes unchanged. Cancel after selection left raw draft and canonical document
exactly unchanged. These observations do not prove hidden/back-cap selection.
Resizing the viewport after an explicit choice caused Apply to refuse visibly;
the exact draft and canonical document remained unchanged. The suspended draft
was saved through native Save As and retained as a small fixture. A separate
Blender process reopened that exact file, asserted matching raw draft/canonical
bytes and no transient pickers/reviews, required a fresh Check, and reproduced
the candidate. `tests/blender_projection_edge_choice_reopen.py` records that
readback contract. Registered tests also rejected hidden, unlinked, and identical
mesh-datablock replacement in the legacy displayed-body path, including attempted
restoration. These are source-loaded observations, not installed-package or
cross-platform qualification.
