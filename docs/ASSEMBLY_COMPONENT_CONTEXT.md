# Component selection and contextual actions

Post-1.29 development makes Assembly component context follow the actual selected
component, not a stale remembered history row. This is a source-only change;
frozen installers remain unchanged.

## Behavior

Clicking one current component in the viewport highlights its named instance row
and exposes that component's Place/Edit and Remove actions. Reuse a Part defaults
to that component as parent and its reusable definition. Clicking a named history
row still selects the corresponding owned mesh and mate-frame helpers.

The resolver is read-only: no timer, handler, schema, canonical JSON, geometry,
selection or persisted UI-state writes. It requires one actively selected mesh,
matching scene/window/view-layer membership, visibility and selectability, valid
owner/Assembly/definition/instance identity, and the existing complete trusted
current display. Display tags alone are not authority. Valid owned frame helpers
can coexist with the selected mesh; frames alone are not component context.

Multiple components, unrelated objects, no selection, active-but-unselected
objects, hidden objects, stale/tampered/duplicate display tags and changed native
context never fall back to an old component row. The UI asks for one current
component without clearing the user's selection. Implicit Remove/Joint editing
refuses absent component context; explicit named buttons retain their named
intent and existing dialog/currentness/atomic commit safeguards.

Generic Insert remains available without a unique component: its visible parent
field starts at the grounded root, never the old row. Reusable-definition
selection remains a separate browser choice. After reopening, explicit Rebuild
must reestablish trusted display before viewport selection supplies context.

## Evidence (2026-10-26)

Baseline GUI on e5a3c51: row `a` selected, then only viewport mesh `b` selected;
canonical/current display remained intact, but history/actions stayed on `a` and
Reuse a Part opened parent `a`. Corrected GUI highlights `b` and opens parent `b`
even while the stored old row remains `a`. Cancel preserves exact canonical JSON.
Actual Shift-selection of `a` and `b` shows no single-target actions or highlight,
retains both selected meshes and shows guidance; no geometry operation was applied.

- 44 focused selection, routing and workflow tests pass; changed-file Ruff passes.
- Real Blender 5.2.2/OCP sidecar: 21 selection checks and 7 separate-process reopen
  checks pass, including unchanged canonical JSON, reports, mesh and pose digests.
- Expanded relevant UI subset: 109 passed, 31 failed. All 31 failures are in
  `test_arc_ui_availability.py`; the untouched e5a3c51 baseline reproduces exactly
  the same failing IDs and primary signatures (31 failed, 32 passed in that file).
  No assertions were changed or skipped. Retained attribution describes old
  action/capture expectations, palette/layout/test-port and diagnostic-label cases.
- No whole-suite pass, Windows, new installer, geometric Apply/Undo or manufacturing
  qualification is claimed. The separately denied slider GUI Apply remains paused.

Evidence lives in `evidence/assembly-selection-20261026/`, including baseline and
corrected screenshots, native receipts and exact baseline-failure attribution.
