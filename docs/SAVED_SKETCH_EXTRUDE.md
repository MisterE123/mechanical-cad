# Saved sketch extrusion shortcut

Source milestone `fead282` adds **Extrude Selected Sketch** to the Sketch/Part
history sidebar. It opens the existing Extrude dialog with the selected saved
sketch's stable ID, without switching workspaces or adding another geometry path.

The shortcut requires current replay evidence of an available profile and the
existing whole-graph operation policy. Open or unsupported profiles retain their
boundary explanation; stale/unverified results request Rebuild. Solver success
or zero degrees of freedom alone is not a profile-readiness claim. Drafts and
staged repairs retain their existing completion gates.

## Bounded evidence, 2026-10-24

- 117 focused tests passed across saved-sketch extrusion, compact status and
  feature-history presentation. Changed-file Ruff passed. This was not the full
  historical suite.
- Native Blender 5.2.2 with the native sidecar passed
  `tests/blender_saved_sketch_extrude_smoke.py`, marker
  `SAVED_SKETCH_EXTRUDE_SMOKE_OK`: a saved constrained rectangle kept its original
  sketch data/ID and produced a 12,000 mm³ extrusion through the existing operator.
  Open-line and stale-result shortcut states were disabled.
- Actual cloud GUI, source-loaded: in the Sketch workspace the selected saved
  sketch showed a readable **Extrude Selected Sketch** button and **Closed profile
  available** label at the observed sidebar width. One click opened the existing
  Extrude dialog, prefilled with `Mounting plate outline [sketch_1]`.
- Clicking **Cancel** restored the sidebar and removed the cyan preview. The
  fixture's observer verified byte-identical canonical JSON, `READY` status,
  an empty last-action error and zero remaining preview owners.

The initial GUI launch failed before fixture entry with `free(): invalid pointer`.
A foreground retry succeeded. The first log was overwritten by the retry; its
observed text is preserved in the task transcript and evidence receipt. The
successful retry does not establish that the startup failure was fixed.

The local evidence directory is
`cad_engineering_evidence/saved_sketch_extrude_20261024` in the parent workspace:
`shortcut.png`, `dialog.png`, `cancelled.png`, `gui.log`, `initial.json`, and
`cancel-receipt.json`. Generated evidence is not part of source Git.

No new interactive Apply/Undo/Redo, installed-archive, Windows or exhaustive GUI
qualification is claimed. Native Apply and actual GUI Cancel are distinct checks.
