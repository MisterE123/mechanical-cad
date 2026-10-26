# Replace a projected reference

Select a saved constrained sketch in Feature History, then **Replace Reference**.
This history-level operation works outside Edit Sketch; finish or cancel any live
draft first. Choose the existing construction line/circle and its replacement
from readable, freshly evaluated source choices. The source feature cannot change.
For lines, review the displayed existing start/end point IDs and resulting local
coordinates; **Flip start and end** explicitly changes endpoint correspondence.
Circles show the new center and radius.

**Replace** changes one projection binding and only its evaluated managed fixed
point/radius drivers. It retains construction entity IDs, point IDs, dependent
constraints and dimensions, all other reference bindings, and unrelated features.
A complete exact Part rebuild must pass before anything is published. Cancel
changes nothing; Blender Undo restores the accepted document edit.

## Bounded recovery and safety

- Both solid analytic lines/full circles and authored sketch lines/circles are
  supported. Replacement must retain the analytic kind and external source.
- A fresh, read-only source-ancestry catalog is evaluated separately. A failed
  downstream projection therefore does not hide valid upstream choices. Neither
  the ordinary edge-catalog validator nor full-Part publication is weakened.
- Attached sketches additionally require a currently resolved support plane.
  Repair the support first when that plane is unresolved.
- This is explicit reselection, not nearest-edge matching or a general TNP solver.
  Changed endpoint signatures still fail on ordinary replay until explicitly repaired.
- The bounded [unapplied-edit review](STAGED_EDIT_REPAIR.md) can retain one
  rejected solid edit for explicit repair. Without an active retained proposal,
  this command still reviews only the accepted graph. Within an unapplied proposal,
  Cancel closes only the review and retains the upstream edit and all previously
  kept repairs, including after saved-intent Resume. Discard Proposed Edit is the
  separate action that abandons that work.
- All existing dependent relations remain authoritative. A replacement can move
  geometry outside a Cut, or make dimensions inconsistent; in that case Replace
  fails without deleting relations or publishing partial geometry. No hidden
  dependent-point reseeding is performed to force a desired solver branch.
- The initial UI is a reviewable source-selection dialog, not a viewport picker.
  Ordinary accepted-model replacement requires a fully valid candidate. Within
  an eligible unapplied upstream edit, multiple repairs may accumulate only in
  the proposal, with explicit Undo Proposal Repair; the accepted Part changes
  only after a complete successful replay.

## Saved endpoint direction

Projection rows may carry optional boolean `reverse`. Omission preserves existing
start-to-start correspondence. A line with `reverse: true` maps its original start
point to the source end and its end to the source start. Stable native endpoint
signatures remain canonical and are checked unchanged. Circles reject endpoint
orientation. This field persists through save/reopen and replay; no line or point
identity is swapped. Older runtimes reject the new field rather than infer it.

## Evidence

Targeted native tests cover line replacement in both orientations, dependent
extrusion volume, retained dimension/relation IDs, JSON save/reopen, strict v2/v3
bridge validation, explicit repair of failed native endpoint identity, circle and
sketch-source replacement. Host seam tests cover stale-dialog rejection, failed
complete rebuild and read-only cancellation. These are not interactive Blender
GUI, Undo, installer or two-process `.blend` qualification.

Dynamic reference/source choices and their initial selections are carried as
hidden, non-saved RNA presentation data. Blender may create a fresh Python
wrapper for enum/update callbacks, so those callbacks must not depend on
invoke-only Python attributes. Apply still validates the original guarded native
receipt and full candidate; the presentation JSON cannot authorize geometry.

`tests/blender_repair_rna_smoke.py` exercises the invoke path with genuine
registered RNA operators and enum/update callbacks, plus resumed solid-editor
fields. Only background dispatch and final popup presentation are shimmed. The
unfixed projection callback reproduces `reference` missing from `NONE`; the fixed
path passes. This does not replace actual GUI popup/gesture qualification.

## Source-development circular arcs

The [solid arc projection extension](SOLID_ARC_PROJECTION.md) adds same-source,
same-kind arc replacement with explicit start/end flip. Target center/start/end
IDs and dependent relations remain unchanged; the native interval determines
minor/major branch and target direction. Oblique or ambiguous arc candidates are
refused. Focused native repair checks pass; Blender/GUI repair qualification is pending.
