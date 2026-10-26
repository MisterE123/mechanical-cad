# Explicit preview framing (development source)

Extrusion preview dialogs offer **Focus Preview**. It moves only the owning
viewport's center and distance, with margin and a left-side bias to leave room
for the editor. It does not select objects, change the displayed output, run
geometry evaluation, or accept the proposal. Preview bounds are cached once
when the completed overlay is built, not traversed during UI drawing or polling.

Only one valid, completed, current proposal in its original window/area can be
focused. Pending, applying, closed, stale, invalid/extreme bounds and invalid
projection states refuse without view mutation. Camera and quad views are not
supported. Perspective and orthographic projection/rotation are preserved.
The left-side framing accommodates the tested standard dialog layout, not every
possible manually moved dialog or customized viewport arrangement.

Cancel removes the overlay and leaves the model unchanged. Explicit view
navigation remains, just like other user navigation; Cancel does not undo it.
Normal Apply retains the existing acceptance and post-publication framing path.

## Verification

- 74 focused pure geometry/owner lifecycle tests; 20 registration tests pass.
- Actual Blender 5.2.2 source GUI: previously offscreen circle extrusion becomes
  fully visible beside the modal in perspective; orthographic focus also keeps
  the full outline visible. Focus and Cancel leave document, output, volume,
  selected objects and active object unchanged; Cancel clears preview owners.
- Revised 12 mm proposal explicitly applied once: radius 4 mm cylinder volume
  603.18579 mm³. Actual Undo removes that feature; Redo restores it. Saved model
  reopened/regenerated independently with seven features and the same volume.
- Evidence: `evidence/focus-preview-20261025/`. Earlier unsuccessful framing
  iteration screenshots/logs are retained and clearly named separately.

No whole-suite rerun or new exact-installed archive qualification for this source
change. Frozen 1.28 remains unchanged; earlier aggregate/Windows limitations in
`TEST_HARNESS_MAINTENANCE.md` remain open.
