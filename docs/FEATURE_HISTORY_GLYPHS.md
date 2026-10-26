# Feature-family glyphs in history

Development source after Linux 1.27, not a new packaged release.

History rows now show the operation family beside the feature name: sketches,
extrusions, booleans, edge blends, patterns and other supported families reuse
the corresponding native authoring glyphs. Unknown feature kinds remain neutral.
These are family hints, not a full vocabulary of unique operation symbols.

The separate replay-status indicator still uses fresh qualified presentation:
current checks, unverified dots, errors and blocked markers retain their existing
guards. The displayed-output eye, assumed-plane disclosure and guarded pencil
remain unchanged. Family glyphs do not validate geometry or enable an action.

## Bounded verification, October 25, 2026

- 51 focused glyph/history/dispatch tests passed; full Ruff passed.
- Blender 5.2.2 LTS native row smoke passed for all four status indicators,
  assumed support, active output, explicit feature targeting and no state mutation.
- A real development ZIP was installed into an isolated scripts directory.
  Actual mouse/keyboard review confirmed readable glyphs and controls in the
  approximately 240-pixel sidebar, row-pencil editing, Cancel, a depth change
  from the `height` parameter to literal `12`, and Undo/Redo. The recorded
  volume changed from 11,497.345 to 13,897.345 mm³ and back as expected.
  During asynchronous rebuild the operation families remain visible while
  status markers revert to unverified dots.
- Saved evidence is under `evidence/feature-glyphs-20261025/` in the private
  development workspace. Generated evidence and runtime binaries are not source.
- The broader installed smoke passed blank/demo/Part/assembly operations before
  failing the general-palette expectation at `blender_general_dispatch_smoke.py:157`.
  The identical failure was reproduced on clean baseline `5d4f650`; this is not
  a full installed-suite pass. Aggregate pytest is being reported separately.

No Windows qualification, new self-contained installer, full-suite pass or
manufacturing assurance is implied by this presentation change.

## Build versus explicit geometry check

Successful history replay now reads `Build: Up to date`; absent explicit validation
reads `Geometry check: not run`. Adjacent help distinguishes row rebuild checks
from a Geometry Check report; no validation or export guards changed.

- 145 focused status/history/help tests and full Ruff passed on combined code.
- Installed Blender 5.2.2 GUI showed both labels legibly and the short first help
  page without sentence truncation. Explicit Check changed the geometry label to
  `Geometry check passed` while the independent build label stayed current.
- Two-process saved-model reopening passed with `FEATURE_GLYPHS_REOPEN_OK`.
- Backend lifecycle smoke hit an earlier `Remaining DoF: 0` expectation; the
  identical failure was reproduced on the clean original source baseline.
- Complete pytest on glyph commit 4920872 finished with 17,014 passed, 782 failed,
  353 errors, 12 skipped and 19,597 subtests passed (901.85 seconds). Its log has
  213 `No space left on device` mentions and early `bpy.props.IntProperty` import
  errors. Those are observed causes, not proof every failure predates this change.
  Status wording was tested separately while this aggregate was running.
- Subsequent shell launches failed during sandbox setup despite 28 GB free in
  the shared source workspace; no files were deleted to work around this.

This remains a bounded development checkpoint, not a release qualification.
