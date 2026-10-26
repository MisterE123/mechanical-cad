# 1.5 development checkpoint

This checkpoint continues the usable-CAD work; it is not a declaration of full
Onshape parity or a general solution to topological naming. The delivered 1.4
files remain unchanged. A development source version alone does not mean a new
installer has been built or qualified.

## Practical changes

- Distinct command-specific toolbar glyphs, including Line, Dimension, Reverse
  Arc, Extend, Check and Finish. Shared artwork is also used in tool menus.
- Creation-time exact boundary previews for selected-edge Fillet and Chamfer;
  Cancel preserves the accepted model, and Apply evaluates the current intent.
- A uniquely proven generated selected-edge blend surface can own a reusable
  reference. Planar chamfers can support sketches; curved fillet faces cannot.
- Open Shell exposes uniquely proven inner-wall and opening-lip references.
  Inner walls follow their source wall. The lip explicitly follows the Shell's
  current selected opening, including deliberate opening changes.
- Drawn face sketches can explicitly preserve their source-relative logical
  plane through proven same-source coplanar Cut splits. The saved placement also
  remains consistent before and after the split, avoiding centroid drift.
- New saved orientation uses an explicit baseline-relative Minimal twist rule,
  avoiding the projected-world-axis jump as source normals change. Review
  Support offers World axes or a warned reset; near-opposite normals require
  correction rather than an arbitrary rotation axis. This is not material spin.
- Review Support explains the assumption and allows Strict or another support.
  Existing sketches without saved intent retain their previous semantics.

The logical plane is a saved construction decision, not a claim that an arbitrary
split fragment is the original face. Missing or competing provenance still
requires correction. Generated surfaces require unique native history, not a
nearest-geometry match. Relevant rules and refusal cases are indexed under
[the topology regression catalog](regressions/catalog.json).

## Editable examples

[Topology walkthroughs](../examples/topology_walkthroughs/README.md) includes a
slotted plate with a source-relative attached pad, and an open enclosure with a
pad on its inner wall. Named parameters and exercises show what changes, which
assumption is used, and what must fail rather than silently reattach.

## Verification boundaries

Source/native checks, real Blender GUI observations, and installed-package checks
are separate evidence. Consult the exact package's verification note for its
commit, actual installed checks, screenshots and remaining limitations. Do not
infer a full historical-suite pass from targeted checks.

Linux x86_64 and Blender 5.2.2 LTS remain the qualified development target;
Windows testing is deferred. Existing runtime/source provenance declarations and
unresolved material statements remain in the package, without new legal or
recipient-rebuild claims. No source or model history is published to GitHub.
