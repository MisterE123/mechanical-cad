# Edit the diameter that is displayed

Double-click a driving **⌀** label created by direct Circle diameter placement to
open the explicit **Diameter (mm)** dialog. Enter the full diameter, such as
`30`, `3 cm`, or `size + 4`; do not halve it yourself. The existing Dimension tool
also retains diameter display when repositioning that label and opens the same
dialog. Reference **(REF)** labels remain read-only. Ordinary **R** labels still
open their existing radius field.

This reuses the existing Set/Edit diameter transaction. The canonical constraint
remains a radius; the dialog converts a changed diameter to radius exactly once.
Numeric literal sources reopen as full diameter numbers; newly entered literals
are converted once without an unnecessary symbolic wrapper. A stored radius
formula is displayed as `2*(original formula)`. Untouched Apply
and dialog dismissal leave the original formula byte-for-byte unchanged. Changed
formulas describe diameter in mm; named parameters keep their original meaning.
The field has display room for doubling a maximum-length stored formula, but
changed input and canonical expressions retain their existing bounded validators.
There is no new expression language, saved dimension mode or schema migration.

The exact annotation driver ID is resolved without changing selection. Apply
rechecks the existing full owner/source/saved-slot/backend binding; stale dialogs
cannot edit a different selected curve. Native solve, consumed Part full replay,
atomic local Undo/Redo and canonical Finish gates are unchanged. No conversion
runs in the canonical replay or persistence layers.

Already-retained raw dimension edits are deliberately not redirected or doubled.
They reopen in the original radius field with the explicit heading **Driving
radius · diameter / 2**. This also applies to the canonical-radius raw text retained
after a failed native diameter Apply: recover or cancel that edit before reopening
the diameter dialog. Canceling the dialog before Apply makes no command or edit;
Cancel on a submitted/retained trial follows the existing dimension cancellation.

## Verification boundary

Targeted pure tests cover exact-ID routing, legacy radius and retained raw input,
read-only invocation/cancel and no-op, named formulas, literal/unit conversion,
stale rejection, maximum-length source display and preserving diameter on label
repositioning. The final focused pure selection passes 455 tests and 113 subtests; scoped Ruff
and whitespace checks pass. Native Blender 5.2.2 passes the actual owner, stale
binding, unit/formula, local Undo/Redo, retained-raw serialization and consumed
full downstream replay smoke. A real registered RNA field retains a 260-character
doubled maximum-length source. The popup adapter itself is not GUI evidence.

Separately, source-loaded real GUI double-click opens Diameter at 20.0, accepts
`3 cm` as displayed ⌀30/canonical radius 15, and reopens the literal as 30.0.
Ordinary R5 still opens the raw radius field at 5. Initial GUI unchanged Apply
preserves the exact source; changing the field to 40 and then Cancel preserves radius 15 and leaves no pending
edit. Both disposable fixtures are preserved before closing. These are bounded Linux checks, not exhaustive
focus, enlarged-scale or accessibility coverage.
This is not a full historical-suite, packaged-install, Windows, manufacturing or
native allocator-stability qualification.
