# Edit Feature selection continuity

A successful explicit Edit Feature now keeps the edited history row selected,
resolved by stable feature ID in the freshly populated collection. The canonical
active output and displayed final body are unchanged. A missing ID leaves the
publication-selected row untouched. Failure/refusal does not run reselection.
General population/load behavior, filter ordering and ownership are unchanged.

Verification on source with Blender 5.2.2: 85 focused unit tests, native radius
and linked-tool dispatch scripts, and Ruff passed. Native cases cover reordered
and missing rows, false commits, stale context and independent consent refusal.
Actual GUI covers shared radius6, local radius5, immediate repeated edit, Cancel,
unknown-parameter refusal, local Undo/Redo, and Apply while filtered to one row
(canonical index2, not visible position0). Selection stays Hole profile while
output stays body. Saved file independently reopened and rebuilt with correct
selection/output and volume11214.6015625. An isolated shared cycle then verified
parameter6 → Apply7 → Undo6 → Redo7, including exact expected body volumes
and unchanged selection/output. Early insufficiently synchronized captures remain
in evidence; the explicit cycle closes that ambiguity. Latest shared7 save also
independently reopened and rebuilt.

This is a source-only increment after frozen1.28, not a new qualified installer.
Full aggregate and outstanding historical/Windows failures were not rerun/waived.
