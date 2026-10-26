# Simple and counterbored round holes

In the Part workspace choose **Hole**, select the target solid and explicitly
choose a stable planar entry face. Enter the hole diameter and total depth.
Enable **Counterbore** to add a larger, shallower concentric recess. Both depths
are measured inward from that same entry plane, not from the recess bottom.
Lengths accept literals in millimetres or explicit units such as `0.25 in`.
This dialog deliberately does not accept expressions or thread/fastener tables.

Center X/Y are offsets from the entry face's current area centroid, in the same
deterministic local frame as Circle on Face: local X is projected world X,
except on nearly X-facing faces where world Y is used; local Y completes the
outward-normal right-handed frame. A changed upstream face centroid therefore
moves the hole with it. Zero offsets center the hole; this is not an edge-distance
or picked-point constraint. A face with a hole may have its centroid outside its
material. Review the exact preview rather than assuming the center is inside.

The cyan proposed-result outline uses the existing detached sidecar preview.
Apply freshly replays and atomically publishes the whole graph. Cancel retires
the preview without changing canonical geometry. Select the final Hole history
row and **Edit Feature** to reopen the compact Hole dialog. Its hole type stays
fixed during editing; its dimensions, center, name and explicit support may be
changed. Individual circle/extrusion/cut steps remain visible and editable.
Editing an individual step into a nonstandard recipe, or sharing an intermediate
with another feature, disables grouped Hole editing rather than silently changing
the shared dependency. Ordinary final-result downstream consumers are supported.

## Exact representation and limits

No new document schema or mesh-only geometry is introduced. The recipe stores an
ordinary face-circle, inward signed Extrude and Cut; a counterbore adds a second
circle/extrusion on the original entry face and a second Cut. The reserved ID
family is a UI grouping hint only. Grouped editing checks the entire structure,
literal dimensions and external consumers. It grants no topology authority.
Legacy documents and strict native face resolution remain unchanged. Split,
missing or ambiguous entry faces fail closed; there is no nearest-face fallback.
Normal exact Cut tool lineage remains available for later supported operations.

Diameters/depths must be positive bounded lengths; the counterbore must be wider
than the hole and shallower than its total depth. No-material-removal and invalid
solid results fail through the existing exact kernel. **Finite depth may break
through and edge breakouts are allowed.** There is no automatic thickness limit,
entry-circle containment check, Through All, Up to Next, countersink, drill tip,
thread or manufacturing-fit/strength certification. Each Cut must remove material;
a recess wholly beyond the remaining solid fails rather than becoming a no-op.

Focused tests cover exact volumes and single-solid validity, top and side entry
faces, arbitrary rotated and mirrored support normals, upstream thickness/diameter
edits, JSON persistence, strict recipe grouping,
input guards, stale/snapshot/curved face refusal and missing-face/no-removal failure. Native Blender 5.2.2 source checks also passed creation, grouped dimension editing,
atomic invalid-counterbore refusal, real asynchronous preview generation and
cancellation during native work, plus saving and independently reopening the
`.blend`, replaying and editing again. The headless preview captures geometry
rather than rendering its GPU overlay. This does not establish actual dialog
usability, GPU overlays, Undo/Redo, installed-package or full-suite quality.

Evidence: `tests/unit/test_hole_recipe.py`, `tests/unit/test_hole_operator.py`,
`tests/integration/test_round_hole_recipe.py`, and
`tests/blender_round_hole_smoke.py` (run once with `MCAD_SMOKE_OUTPUT`, then in a
fresh Blender process with `MCAD_SMOKE_INPUT` and a new output). Both native
processes require `--python-exit-code 1` and explicit result markers
`MCAD_ROUND_HOLE_SMOKE_OK` / `MCAD_ROUND_HOLE_REOPEN_OK`.

When opening a new Hole, an unselected Entry face asks you to choose one before
previewing. This is not a lost-reference warning. A captured face that is missing,
ambiguous, curved or no longer stable still fails closed with the existing
reselection diagnostic. Focused checks distinguish these cases; the normal
exact geometry and publication gates are unchanged.
