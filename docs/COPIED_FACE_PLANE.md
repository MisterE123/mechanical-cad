# Sketch on Copied Face Plane (Unlinked)

Development-only additive workflow after the immutable 1.19 checkpoint. The
named CAD menu entry is separate from **Sketch on Face** and adds no permanent
palette icon. Its confirmation and picking instruction state:

> Fixed plane copied from this face. Does not follow source edits.

After confirmation, select a planar face on the current exact CAD display.
Escape/right-click cancels without a canonical edit. The new ordinary drawn
sketch receives a literal plane: current native face centroid plus a unit
quaternion from the native oriented analytic normal and the deterministic
projected-world-axis convention. This does **not** recover the original STEP
UV origin or UV axes. Nonplanar or incomplete geometry is rejected.

## Identity and lifecycle boundary

Imported STEP faces remain `unknown`. This action does not establish stable
imported-face naming and does not relax the attached-sketch resolver. A viewport
triangle selects a candidate only inside one current verified replay's exact
triangle map. It provides no plane geometry: only the native signature supplies
centroid and normal. Missing/duplicate map targets fail closed.

The original receipt, accepted runtime record, document, backend, scene/window,
draft eligibility and entire displayed mesh are checked at the pick, after the
workspace transition and immediately inside draft creation. Even replaying an
identical document expires the capture. No cross-rebuild matching, ordinal
fallback, proximity lookup or persistent capture is permitted.

The sketch saves no `support_face`, support input, support intent, projection
link, face ID or triangle index. Once creation succeeds it is deliberately an
ordinary fixed plane; later source edits do not move it. Edit the sketch as an
ordinary literal-plane sketch. Cancel discards the draft through the existing
owner lifecycle. Save/reopen uses the existing canonical Plane schema unchanged.

## Focused evidence

`tests/create_copied_plane_fixtures.py` generates an oblique native box and a
translated replacement asset. `blender_copied_face_plane_smoke.py` exercises
native ray selection, unknown imported IDs, analytic plane copying, malformed
and stale capture rejection (including delayed workspace callbacks), cancel, the
actual sketch-owner creation/Finish path, native Undo/Redo, source replacement
without reassociation, and `.blend` save.
`blender_copied_face_plane_reopen_smoke.py` checks replay in a second process.
These are bounded native/headless checks, not interactive GUI, Windows,
installed ZIP or full historical-suite qualification. No release is modified.

Verified in the cloud source worktree on 2026-10-24 with the pinned Python runtime
and native Blender 5.2.2: the new native smoke and second-process reopen markers
passed, as did the unchanged attached-face picking smoke. Focused principal
plane, general draft, native principal-plane authoring and help-catalog tests:
107 passed. Changed Python files passed Ruff; `git diff --check` passed.
The headless delayed-callback test invokes its production callback with the
workspace transition mocked. A separate bounded cloud desktop GUI pass then
exercised the actual named menu, readable disclosure dialog, dialog Cancel,
confirmation, oblique imported-face hover highlight, pointer click, actual
workspace transition and oriented literal-plane draft creation. Draft telemetry
showed empty inputs and no support/projection fields. Clicking Cancel removed
the draft and preserved the exact canonical document hash. No layout defect was
observed in this fixture. This is not broad GUI, installed-package or Windows
qualification; native Finish/save/reopen/Undo/Redo evidence remains separate.

The retained cloud evidence consists of `copied-plane-gui-menu.png`,
`copied-plane-gui-disclosure.png`, `copied-plane-gui-hover.png`,
`copied-plane-gui-draft.png`, `copied-plane-gui-cancelled.png` and
`cad_copied_gui.log` in the shared task workspace. The GUI fixture imports the
same oblique box using a dedicated copied STEP file; it does not overwrite the
native save/reopen fixture.

## Offset an existing fixed plane

Select a saved, unlinked constrained sketch in Feature History, then choose
**Offset Fixed Sketch Plane**. Enter one signed literal length (millimetres by
default, or `mm`, `cm`, `m`, `in`, `ft`). Apply moves its origin once along the
plane's own positive normal; a negative value moves in the opposite direction.
This works for copied-face and ordinary principal literal planes alike. It does
not follow the former source and does not create a named-parameter association.
Formulas, attached sketches and linked projections are rejected, not detached.

The plane ID, saved quaternion, local geometry, constraints, and all other model
fields remain unchanged. The temporary normal uses existing double-precision
plane math, not Blender RNA vectors or mesh normals. Zero preserves exact plane
values without replay/publication. Cancel leaves the accepted model unchanged.
Apply replays the whole candidate through the existing guarded atomic publication
boundary and supports Blender Undo/Redo. A failed replay or publication preserves
the accepted model. Changed document/context/selection, drafts, running CAD work,
and staged repairs require reopening or completing that work first. No preview,
arbitrary rotation, generic datum architecture or new backend protocol is added.

Focused cloud source evidence on 2026-10-24: 72 helper/unit-input tests passed.
`tests/blender_fixed_plane_offset_smoke.py` passed with native Blender 5.2.2 on
the saved oblique copied-plane fixture, covering negative inch input, zero,
Cancel, stale document/selection, busy/draft/staged rejection, injected publication
failure rollback, actual offset/replay, Undo/Redo and save. The existing copied
plane second-process reopen smoke passed on that offset result. The background
harness simulates the dialog dispatch, not interactive GUI use; this is not
installed-package, Windows, exhaustive-suite or real GUI qualification. No frozen
release or publication artifact is changed.

A subsequent bounded cloud GUI pass used the real Feature History button and
actual dialog in a separate disposable Blender process. The fixed/one-time
labels and both buttons were readable. Cancel preserved the exact canonical
hash; reopening, typing `2 mm`, and clicking Apply Fixed Offset produced a READY
model exactly equal to the expected detached document (only origin changed).
No dialog layout defect was observed. The initial pass exposed that existing
publication behavior selected the active imported solid after replay. A scoped
follow-up now retains the edited sketch's history selection inside the atomic
publication callback, without changing the active output or global replay
behavior. Native checks cover selection after Apply, Cancel/failure and Undo/Redo,
and reopening the offset action immediately without manual reselection. An
injected failure after reselection also restores the prior canonical document,
history selection and current replay evidence. The final source-loaded native
check and independent saved-file reopen passed, alongside 23 focused unit tests
and Ruff. Full pytest was interrupted after early inherited-suite failures;
it is not a full-suite pass. Final installer qualification remains separate.
The disposable process was closed without saving over the fixture.
Receipts `gui-cancelled.json` and `gui-applied.json`, screenshots `gui-dialog.jpg`,
`gui-cancelled.jpg`, `gui-2mm-input.jpg`, `gui-applied.jpg`, and `gui.log` are retained
in the shared fixed-plane-offset evidence directory. This does not expand the
separate headless/native qualification into broad GUI or platform coverage.
