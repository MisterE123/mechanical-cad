# Explicit sketch relations and recovery

The general Line/Circle sketch editor exposes contextual Horizontal and Vertical
relations for one selected line, plus Fix here and Fix at origin for one explicitly
selected point. Coincident creation remains unavailable in the production UI.

## Picking and inspection

- The Point selection tool restricts viewport picking to points. Distinct
  overlapping points remain ambiguous.
- In Sketch relations, a selected line has explicit Start point / End point
  buttons. A selected circle has Center point. These buttons bind the displayed
  curve and its exact point ID; a stale curve selection is rejected.
- Incident relations are listed six at a time with their kind, value or fixed
  target, and references. Select a row for its full stable ID and authored value.
  Pagination is transient and changes no saved draft fields.
- An intentionally removed relation is cleared from selection within the same
  accepted draft transaction. Other selection and annotation records stay exact.
  Undo/Redo does not invent or remap a selection. Externally missing selections
  and unavailable annotation bindings stay explicit for recovery.
- Applying an already-existing relation inspects its identity. Existing fixed
  targets are not silently rewritten by either Fix action.

Fix here requires a current successful native Check and uses its exact solved
point coordinates. Fix at origin is separate: its Apply/Cancel dialog names the
point and sketch-plane target (0, 0) mm and discloses possible geometry movement.
Both origin and recovery confirmation retain the original frozen prepared action;
changing the selection, owner, source, input, or other binding invalidates it.
A direct operator execute cannot bypass these confirmations.

## Release and conflict recovery

Remove relation releases only the named relation using the current validated
solved placement. A current successful Check is required for this ordinary path.

Failed native Checks may expose **Conflict candidates**. These IDs are inspection
candidates, not a diagnosis of which relation should be deleted, and grant no
geometry, DoF, Finish, or export authority. There is no automatic deletion.

Without a current solution, select an exact relation and choose **Remove using
authored positions**. Its separate confirmation identifies the relation and states
that no current solved placement exists. Authored point positions and circle
radius seeds remain exact. Geometry may move after the next Check, and the result
stays unverified until that Check succeeds. This is a relation-only recovery
command, not an unrestricted geometry deletion tool.

Undo sketch and Redo sketch use the existing local sketch journal and Check path.
They do not substitute Blender's global Undo or publish changes to the Part.

## Ownership and verification

`constraint_ui.py` supplies `CLASSES`, `draw_inspector`, `action_available`, and
`select_bindings`. It does not own timers, native solver work, registration, or
viewport lifecycle. Every command delegates through `constraint_actions` to the
existing GeneralSession transaction and asynchronous execution path.

UI-only selection prepares a detached wrapper over the same live command draft,
validates serialization, and checkpoints through the existing saved-slot CAS.
Failure restores the original wrapper. Accepted solution objects, diagnostic
snapshots, command revisions, allocation ledger, and local history are preserved.

`tests/blender_constraint_ui_smoke.py` exercises normal registered operators and
real native sidecar checks on Blender 5.2.2 LTS. It separately observes the popup
invoke/execute/cancel seam using a test window-manager adapter. This establishes
programmatic confirmation binding and operator behavior; it does not establish
actual GUI focus, popup usability, icon legibility, or ordinary/enlarged UI-scale
acceptance. Those remain independent native GUI review requirements.
